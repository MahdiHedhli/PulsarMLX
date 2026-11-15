//! A snapshot of the host's process table, read without `ps`.
//!
//! - Linux: every `/proc/<pid>/stat`, parsed by [`parse_proc_stat`]. The parser is
//!   platform-neutral and unit-tested everywhere; the directory walk is compiled on Linux
//!   only and is unverified until a Linux CI run exercises it.
//! - Darwin: `proc_listallpids` and `proc_pidinfo(PROC_PIDTBSDINFO)`.
//! - Elsewhere: [`snapshot`] fails with [`ProcessError::Unsupported`], and the harness
//!   falls back to checking the process group with `killpg(pgid, 0)`.
//!
//! Each entry carries the process's start time, so that a pid reused by an unrelated
//! process is never mistaken for the one the harness saw.
//!
//! Behavior reference: project-maya serve/test_stop.py:120-145 at 7e68a30f (`gone`
//! counts a zombie as ended; `descendants` walks the children recursively).

use super::ProcessError;

/// One process of a snapshot.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ProcEntry {
    /// The process id.
    pub pid: u32,
    /// The parent's process id.
    pub ppid: u32,
    /// The process group id.
    pub pgid: u32,
    /// The start time, in a platform unit: clock ticks since boot on Linux,
    /// microseconds since the epoch on Darwin. Only compared for equality.
    pub start: u64,
    /// The process has ended and waits to be reaped; it counts as ended.
    pub zombie: bool,
}

impl ProcEntry {
    /// Whether `other` is the same process: same pid and same start time.
    pub fn same_process(&self, other: &ProcEntry) -> bool {
        self.pid == other.pid && self.start == other.start
    }
}

/// Parses the content of a Linux `/proc/<pid>/stat` file. The command name sits in
/// parentheses and may itself hold spaces and parentheses, so the fields are read after
/// the last `)`: state, ppid, pgrp, and the start time as the 20th field after it.
pub fn parse_proc_stat(text: &str) -> Option<ProcEntry> {
    let open = text.find(" (")?;
    let pid: u32 = text.get(..open)?.trim().parse().ok()?;
    let close = text.rfind(')')?;
    let fields: Vec<&str> = text.get(close + 1..)?.split_whitespace().collect();
    let state = fields.first()?;
    let ppid: u32 = fields.get(1)?.parse().ok()?;
    let pgid: u32 = fields.get(2)?.parse().ok()?;
    let start: u64 = fields.get(19)?.parse().ok()?;
    Some(ProcEntry {
        pid,
        ppid,
        pgid,
        start,
        zombie: matches!(*state, "Z" | "X" | "x"),
    })
}

/// Every process the platform lets this process see.
pub fn snapshot() -> Result<Vec<ProcEntry>, ProcessError> {
    platform::snapshot()
}

/// Whether [`snapshot`] works on this platform.
pub fn supported() -> bool {
    cfg!(any(target_os = "linux", target_os = "macos"))
}

/// The processes of `table` that descend from `pid` (children, their children, and so
/// on), not counting `pid` itself, in the order found.
pub fn descendants_of(table: &[ProcEntry], pid: u32) -> Vec<ProcEntry> {
    let mut out: Vec<ProcEntry> = Vec::new();
    let mut frontier = vec![pid];
    while let Some(parent) = frontier.pop() {
        for entry in table {
            if entry.ppid == parent
                && entry.pid != pid
                && entry.pid != entry.ppid
                && !out.iter().any(|e| e.pid == entry.pid)
            {
                out.push(*entry);
                frontier.push(entry.pid);
            }
        }
    }
    out
}

/// The processes of `table` in process group `pgid`.
pub fn group_members(table: &[ProcEntry], pgid: u32) -> Vec<ProcEntry> {
    table.iter().filter(|e| e.pgid == pgid).copied().collect()
}

/// The processes of `wanted` that still run in `table`: same pid, same start time, not a
/// zombie.
pub fn still_running(table: &[ProcEntry], wanted: &[ProcEntry]) -> Vec<ProcEntry> {
    wanted
        .iter()
        .filter_map(|w| {
            table
                .iter()
                .find(|e| e.same_process(w) && !e.zombie)
                .copied()
        })
        .collect()
}

#[cfg(target_os = "linux")]
mod platform {
    use super::{parse_proc_stat, ProcEntry, ProcessError};

    pub(super) fn snapshot() -> Result<Vec<ProcEntry>, ProcessError> {
        let dir = std::fs::read_dir("/proc").map_err(|e| ProcessError::io("read /proc", e))?;
        let mut out = Vec::new();
        for entry in dir.flatten() {
            let name = entry.file_name();
            let Some(name) = name.to_str() else { continue };
            if name.is_empty() || !name.bytes().all(|b| b.is_ascii_digit()) {
                continue;
            }
            // a process that ended between the listing and the read is simply absent
            if let Ok(text) = std::fs::read_to_string(entry.path().join("stat")) {
                if let Some(e) = parse_proc_stat(&text) {
                    out.push(e);
                }
            }
        }
        Ok(out)
    }
}

#[cfg(target_os = "macos")]
mod platform {
    use super::{ProcEntry, ProcessError};

    /// The most processes the harness lists.
    const MAX_PIDS: usize = 1 << 20;

    pub(super) fn snapshot() -> Result<Vec<ProcEntry>, ProcessError> {
        // SAFETY: a null buffer with size 0 asks only for the number of pids; nothing is
        // written.
        let count = unsafe { libc::proc_listallpids(std::ptr::null_mut(), 0) };
        if count < 0 {
            return Err(ProcessError::io(
                "proc_listallpids",
                std::io::Error::last_os_error(),
            ));
        }
        let room = usize::try_from(count)
            .unwrap_or(0)
            .saturating_add(64)
            .min(MAX_PIDS);
        let mut pids: Vec<libc::c_int> = vec![0; room];
        let bytes = libc::c_int::try_from(room * std::mem::size_of::<libc::c_int>())
            .unwrap_or(libc::c_int::MAX);
        // SAFETY: `pids` holds `room` c_ints, and `bytes` is at most its size in bytes,
        // so the call writes inside the buffer.
        let got = unsafe { libc::proc_listallpids(pids.as_mut_ptr().cast(), bytes) };
        if got < 0 {
            return Err(ProcessError::io(
                "proc_listallpids",
                std::io::Error::last_os_error(),
            ));
        }
        pids.truncate(usize::try_from(got).unwrap_or(0).min(room));
        let mut out = Vec::with_capacity(pids.len());
        for pid in pids {
            if pid <= 0 {
                continue;
            }
            if let Some(e) = bsd_info(pid) {
                out.push(e);
            }
        }
        Ok(out)
    }

    fn bsd_info(pid: libc::c_int) -> Option<ProcEntry> {
        let size = std::mem::size_of::<libc::proc_bsdinfo>();
        let size_c = libc::c_int::try_from(size).ok()?;
        // SAFETY: proc_bsdinfo is a plain C struct of integers and arrays, for which all
        // zero bytes is a valid value.
        let mut info: libc::proc_bsdinfo = unsafe { std::mem::zeroed() };
        // SAFETY: the buffer is a proc_bsdinfo of exactly `size_c` bytes, which is what
        // PROC_PIDTBSDINFO writes.
        let n = unsafe {
            libc::proc_pidinfo(
                pid,
                libc::PROC_PIDTBSDINFO,
                0,
                (&mut info as *mut libc::proc_bsdinfo).cast(),
                size_c,
            )
        };
        if n != size_c {
            // ended, not ours to read, or a zombie the kernel no longer describes
            return None;
        }
        Some(ProcEntry {
            pid: info.pbi_pid,
            ppid: info.pbi_ppid,
            pgid: info.pbi_pgid,
            start: info
                .pbi_start_tvsec
                .saturating_mul(1_000_000)
                .saturating_add(info.pbi_start_tvusec),
            zombie: info.pbi_status == libc::SZOMB,
        })
    }
}

#[cfg(not(any(target_os = "linux", target_os = "macos")))]
mod platform {
    use super::{ProcEntry, ProcessError};

    pub(super) fn snapshot() -> Result<Vec<ProcEntry>, ProcessError> {
        Err(ProcessError::Unsupported {
            what: "reading the process table".to_string(),
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn e(pid: u32, ppid: u32, pgid: u32) -> ProcEntry {
        ProcEntry {
            pid,
            ppid,
            pgid,
            start: u64::from(pid) * 10,
            zombie: false,
        }
    }

    #[test]
    fn proc_stat_with_a_tricky_command_name() {
        // fields after ")": state ppid pgrp session tty tpgid flags minflt cminflt majflt
        // cmajflt utime stime cutime cstime priority nice threads itreal starttime ...
        let text = "4242 (a) b (c)) S 4000 4100 4000 0 -1 4194560 10 0 0 0 1 2 0 0 20 0 1 0 987654 1000 100 0\n";
        let p = parse_proc_stat(text).unwrap();
        assert_eq!(
            (p.pid, p.ppid, p.pgid, p.start, p.zombie),
            (4242, 4000, 4100, 987654, false)
        );
        let z = parse_proc_stat(&text.replace(" S ", " Z ")).unwrap();
        assert!(z.zombie);
        assert_eq!(parse_proc_stat("4242 (x) S 1"), None);
        assert_eq!(parse_proc_stat("garbage"), None);
        assert_eq!(parse_proc_stat(""), None);
    }

    #[test]
    fn descendants_walk_every_generation_but_not_the_root() {
        let table = vec![
            e(1, 0, 1),
            e(10, 1, 10),
            e(11, 10, 10),
            e(12, 11, 12),
            e(13, 1, 13),
            e(14, 12, 12),
        ];
        let mut d: Vec<u32> = descendants_of(&table, 10).iter().map(|p| p.pid).collect();
        d.sort_unstable();
        assert_eq!(d, vec![11, 12, 14]);
        assert!(descendants_of(&table, 14).is_empty());
        let g: Vec<u32> = group_members(&table, 10).iter().map(|p| p.pid).collect();
        assert_eq!(g, vec![10, 11]);
    }

    #[test]
    fn a_reused_pid_or_a_zombie_is_not_running() {
        let seen = vec![e(20, 1, 20), e(21, 20, 20), e(22, 20, 20)];
        let mut reused = e(21, 1, 21);
        reused.start = 1;
        let mut zombie = e(22, 1, 20);
        zombie.zombie = true;
        let now = vec![e(20, 1, 20), reused, zombie];
        let running: Vec<u32> = still_running(&now, &seen).iter().map(|p| p.pid).collect();
        assert_eq!(running, vec![20]);
    }

    #[test]
    fn this_process_is_in_the_snapshot() {
        if !supported() {
            return;
        }
        let table = snapshot().unwrap();
        let me = std::process::id();
        let entry = table.iter().find(|p| p.pid == me).expect("own entry");
        assert!(!entry.zombie);
        // SAFETY: getppid and getpgrp take no arguments and cannot fail.
        let (ppid, pgid) = unsafe { (libc::getppid(), libc::getpgrp()) };
        assert_eq!(i64::from(entry.ppid), i64::from(ppid));
        assert_eq!(i64::from(entry.pgid), i64::from(pgid));
    }
}
