//! Starting, reading and stopping one process.
//!
//! Behavior reference: project-maya serve/test_stop.py:70-118 at 7e68a30f (`Proc`:
//! output read line by line, `until`, `close`, `rest`) and serve/test_stop.py:120-145 at
//! 7e68a30f (`gone`, `kill_all`, `descendants`).

use std::ffi::OsString;
use std::fs::File;
use std::io::{Read, Write};
use std::os::unix::process::{CommandExt, ExitStatusExt};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, Command, ExitStatus, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::mpsc::{self, Receiver, RecvTimeoutError, Sender};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

use super::env::{self, EnvDirs};
use super::ready::{parse_ready, Ready, ReadyExpect};
use super::scale::{TimeScale, DEFAULT_GRACE, DEFAULT_KILL_DEADLINE, DEFAULT_READY_DEADLINE};
use super::table::{self, ProcEntry};
use super::{ProcessError, Workdir};
use crate::scenario::Signal;

/// The longest output line kept, in bytes; the rest of a longer line is dropped and the
/// kept part ends with `...[truncated]`.
pub const MAX_LINE_BYTES: usize = 64 * 1024;

/// The most output lines kept in memory, both streams together; later lines are still
/// written to the capture files.
pub const MAX_SEEN_LINES: usize = 100_000;

/// The most output bytes kept in memory by default, both streams together
/// ([`Launch::output_budget`]). The reader threads stop passing lines on once it is
/// spent and only count them, so the lines waiting to be read never hold more than this
/// either; later lines are still written to the capture files.
pub const MAX_SEEN_BYTES: usize = 16 * 1024 * 1024;

/// The most bytes of output a transcript (and so an error) carries: the last part of the
/// output kept, after a note that earlier lines were cut.
pub const MAX_TRANSCRIPT_BYTES: usize = 1024 * 1024;

/// The most bytes written to each capture file; the rest is read and dropped, so the
/// process never blocks on a full pipe.
pub const MAX_CAPTURE_BYTES: u64 = 64 * 1024 * 1024;

/// How often the harness looks at the process table while it waits for processes to
/// end. Only ever used inside a deadline.
const POLL: Duration = Duration::from_millis(10);

/// How long, before scaling, [`ServerProcess::wait_ready`] waits for the exit status once
/// standard output has closed without a ready line, to tell an exit from a closed
/// stream. It is a deadline on an event, never a sleep.
const EXIT_AFTER_CLOSE: Duration = Duration::from_millis(500);

/// Which output stream a line came from.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Stream {
    /// Standard output.
    Stdout,
    /// Standard error.
    Stderr,
}

/// One line of output, without its line end.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct OutputLine {
    /// Where it came from.
    pub stream: Stream,
    /// The text, decoded as UTF-8 with replacement characters.
    pub text: String,
}

/// What the process gets as standard input.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum StdinMode {
    /// `/dev/null` (the default).
    #[default]
    Null,
    /// A pipe the harness holds until [`ServerProcess::close_stdin`]; the
    /// `--parent-pipe` tests close it to stop the server.
    Pipe,
}

/// How to start a process. Built with [`Launch::new`] and the setters, then
/// [`Launch::spawn`] or [`Launch::start`].
#[derive(Debug)]
pub struct Launch {
    program: PathBuf,
    args: Vec<OsString>,
    env: Vec<(String, String)>,
    vendor_dir: Option<PathBuf>,
    engine_gate: Option<PathBuf>,
    stdin: StdinMode,
    port_zero: bool,
    ready_deadline: Duration,
    grace: Duration,
    kill_deadline: Duration,
    scale: Option<TimeScale>,
    expect: ReadyExpect,
    workdir: Option<Workdir>,
    output_budget: usize,
}

impl Launch {
    /// A launch of `program` with no arguments, the default deadlines, the time scale from
    /// the environment, standard input from `/dev/null` and `--port 0` appended.
    pub fn new(program: impl Into<PathBuf>) -> Self {
        Launch {
            program: program.into(),
            args: Vec::new(),
            env: Vec::new(),
            vendor_dir: None,
            engine_gate: None,
            stdin: StdinMode::Null,
            port_zero: true,
            ready_deadline: DEFAULT_READY_DEADLINE,
            grace: DEFAULT_GRACE,
            kill_deadline: DEFAULT_KILL_DEADLINE,
            scale: None,
            expect: ReadyExpect::Server,
            workdir: None,
            output_budget: MAX_SEEN_BYTES,
        }
    }

    /// Appends one argument.
    pub fn arg(mut self, arg: impl Into<OsString>) -> Self {
        self.args.push(arg.into());
        self
    }

    /// Appends arguments.
    pub fn args<I, S>(mut self, args: I) -> Self
    where
        I: IntoIterator<Item = S>,
        S: Into<OsString>,
    {
        self.args.extend(args.into_iter().map(Into::into));
        self
    }

    /// Adds one variable after the allowlist (see [`super::env`]); checked at spawn.
    pub fn env(mut self, name: impl Into<String>, value: impl Into<String>) -> Self {
        self.env.push((name.into(), value.into()));
        self
    }

    /// Adds variables after the allowlist, in order; checked at spawn.
    pub fn envs(mut self, vars: &[(String, String)]) -> Self {
        self.env.extend(vars.iter().cloned());
        self
    }

    /// Sets `PULSAR_CONSOLE_VENDOR_DIR` for the process.
    pub fn vendor_dir(mut self, dir: impl Into<PathBuf>) -> Self {
        self.vendor_dir = Some(dir.into());
        self
    }

    /// Sets `FAKE_ENGINE_GATE` for the process.
    pub fn engine_gate(mut self, fifo: impl Into<PathBuf>) -> Self {
        self.engine_gate = Some(fifo.into());
        self
    }

    /// Chooses standard input.
    pub fn stdin(mut self, mode: StdinMode) -> Self {
        self.stdin = mode;
        self
    }

    /// Whether `--port 0` is appended (the default); turned off for a program that
    /// takes no port.
    pub fn port_zero(mut self, on: bool) -> Self {
        self.port_zero = on;
        self
    }

    /// The ready deadline before scaling.
    pub fn ready_deadline(mut self, base: Duration) -> Self {
        self.ready_deadline = base;
        self
    }

    /// The grace period after `SIGTERM`, before scaling.
    pub fn grace(mut self, base: Duration) -> Self {
        self.grace = base;
        self
    }

    /// How long to wait for the processes to vanish after `SIGKILL`, before scaling.
    pub fn kill_deadline(mut self, base: Duration) -> Self {
        self.kill_deadline = base;
        self
    }

    /// The time scale, instead of the one in the environment.
    pub fn time_scale(mut self, scale: TimeScale) -> Self {
        self.scale = Some(scale);
        self
    }

    /// Which ready forms to accept.
    pub fn expect(mut self, expect: ReadyExpect) -> Self {
        self.expect = expect;
        self
    }

    /// The most output bytes kept in memory ([`MAX_SEEN_BYTES`] by default).
    pub fn output_budget(mut self, bytes: usize) -> Self {
        self.output_budget = bytes;
        self
    }

    /// The run directory, instead of a fresh one under the system temporary directory.
    /// Scenario files ([`super::ScenarioFiles`]) are written into its data directory
    /// before the launch.
    pub fn workdir(mut self, dir: Workdir) -> Self {
        self.workdir = Some(dir);
        self
    }

    /// Starts the process in a new process group, without waiting for its ready line.
    pub fn spawn(self) -> Result<ServerProcess, ProcessError> {
        let scale = match self.scale {
            Some(s) => s,
            None => TimeScale::from_env()?,
        };
        let workdir = match self.workdir {
            Some(w) => w,
            None => Workdir::create(None)?,
        };
        let (home, tmp, runtime) = (workdir.home(), workdir.tmp(), workdir.runtime());
        let vars = env::build(
            EnvDirs {
                home: &home,
                tmp: &tmp,
                runtime: &runtime,
            },
            self.vendor_dir.as_deref(),
            self.engine_gate.as_deref(),
            &self.env,
        )?;
        let stdout_file = create_capture(&workdir.stdout_path())?;
        let stderr_file = create_capture(&workdir.stderr_path())?;

        let mut cmd = Command::new(&self.program);
        cmd.args(&self.args);
        if self.port_zero {
            cmd.args(["--port", "0"]);
        }
        cmd.env_clear()
            .envs(vars)
            .current_dir(workdir.data())
            .stdin(match self.stdin {
                StdinMode::Null => Stdio::null(),
                StdinMode::Pipe => Stdio::piped(),
            })
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .process_group(0);
        let mut child = cmd
            .spawn()
            .map_err(|e| ProcessError::io(format!("start {}", self.program.display()), e))?;
        let pid = child.id();
        let stdin = child.stdin.take();
        // unbounded, but the shared budget bounds the lines in it (see spawn_pump)
        let (tx, rx) = mpsc::channel();
        let budget = Arc::new(Budget {
            lines: AtomicU64::new(0),
            bytes: AtomicU64::new(0),
            max_bytes: u64::try_from(self.output_budget).unwrap_or(u64::MAX),
        });
        if let Some(out) = child.stdout.take() {
            spawn_pump(
                out,
                Stream::Stdout,
                stdout_file,
                Arc::clone(&budget),
                tx.clone(),
            );
        }
        if let Some(err) = child.stderr.take() {
            spawn_pump(err, Stream::Stderr, stderr_file, budget, tx.clone());
        }
        let leader = Arc::new(Mutex::new(Leader::default()));
        let (release, released) = mpsc::channel();
        spawn_waiter(child, Arc::clone(&leader), released, tx);
        Ok(ServerProcess {
            pid,
            leader,
            _release: release,
            events: rx,
            seen: Vec::new(),
            dropped_lines: 0,
            eof: [false, false],
            exit: None,
            stdin,
            workdir,
            scale,
            ready_deadline: scale.apply(self.ready_deadline),
            grace: scale.apply(self.grace),
            kill_deadline: scale.apply(self.kill_deadline),
            expect: self.expect,
            ready: None,
            report: None,
            report_returned: false,
        })
    }

    /// Starts the process and waits for its ready line. On failure the process is
    /// stopped and its run directory kept, so CI can collect its `stdout.txt` and
    /// `stderr.txt`; the error carries the output seen and names the kept directory
    /// ([`ProcessError::run_dir`]). A leak found by that stop is printed on standard
    /// error, since the start has already failed.
    pub fn start(self) -> Result<(ServerProcess, Ready), ProcessError> {
        let mut proc = self.spawn()?;
        match proc.wait_ready() {
            Ok(ready) => Ok((proc, ready)),
            Err(e) => {
                proc.keep_workdir();
                let root = proc.workdir.root().to_path_buf();
                let report = proc.stop();
                eprintln!(
                    "cnf process harness: start failed; kept {} (pid {})",
                    root.display(),
                    proc.pid
                );
                if let Err(leak) = report.check() {
                    eprintln!("cnf process harness: {leak}");
                }
                Err(e.kept_at(&root))
            }
        }
    }
}

fn create_capture(path: &Path) -> Result<File, ProcessError> {
    File::create(path).map_err(|e| ProcessError::io(format!("create {}", path.display()), e))
}

enum Event {
    Line(OutputLine),
    /// The stream closed; the number of its lines that were not passed on because the
    /// output budget was spent.
    Eof(Stream, u64),
    Exited(Result<ExitStatus, String>),
}

/// The output budget shared by the two reader threads of one process.
struct Budget {
    lines: AtomicU64,
    bytes: AtomicU64,
    max_bytes: u64,
}

impl Budget {
    /// Takes room for one line of `len` bytes; `false` once the line or byte budget is
    /// spent. The counters only grow, so once a line is refused every later one is too.
    fn take(&self, len: usize) -> bool {
        let len = u64::try_from(len).unwrap_or(u64::MAX);
        let lines = self.lines.fetch_add(1, Ordering::Relaxed);
        let bytes = self.bytes.fetch_add(len, Ordering::Relaxed);
        lines < MAX_SEEN_LINES as u64 && bytes.saturating_add(len) <= self.max_bytes
    }
}

/// Reads one output stream to its end: every byte goes to the capture file (up to
/// [`MAX_CAPTURE_BYTES`]), and each line goes to the channel while the shared budget
/// lasts. The pipe is always read to its end, so the process never blocks on it.
fn spawn_pump<R: Read + Send + 'static>(
    mut from: R,
    stream: Stream,
    mut file: File,
    budget: Arc<Budget>,
    tx: Sender<Event>,
) {
    thread::spawn(move || {
        let mut buf = [0u8; 8192];
        let mut line: Vec<u8> = Vec::new();
        let mut truncated = false;
        let mut written: u64 = 0;
        let mut dropped: u64 = 0;
        let mut emit = |line: &mut Vec<u8>, truncated: &mut bool| {
            if line.last() == Some(&b'\r') {
                line.pop();
            }
            if budget.take(line.len()) {
                let mut text = String::from_utf8_lossy(line).into_owned();
                if *truncated {
                    text.push_str("...[truncated]");
                }
                // a closed receiver means nobody reads any more; the pipe is still drained
                let _ = tx.send(Event::Line(OutputLine { stream, text }));
            } else {
                dropped += 1;
            }
            line.clear();
            *truncated = false;
        };
        loop {
            let n = match from.read(&mut buf) {
                Ok(0) => break,
                Ok(n) => n,
                Err(e) if e.kind() == std::io::ErrorKind::Interrupted => continue,
                Err(_) => break,
            };
            let chunk = buf.get(..n).unwrap_or_default();
            if written < MAX_CAPTURE_BYTES {
                let room = usize::try_from(MAX_CAPTURE_BYTES - written).unwrap_or(usize::MAX);
                let part = chunk.get(..chunk.len().min(room)).unwrap_or_default();
                if file.write_all(part).is_ok() {
                    written += part.len() as u64;
                } else {
                    written = MAX_CAPTURE_BYTES;
                }
            }
            for &b in chunk {
                if b == b'\n' {
                    emit(&mut line, &mut truncated);
                } else if line.len() < MAX_LINE_BYTES {
                    line.push(b);
                } else {
                    truncated = true;
                }
            }
        }
        if !line.is_empty() || truncated {
            emit(&mut line, &mut truncated);
        }
        let _ = file.flush();
        let _ = tx.send(Event::Eof(stream, dropped));
    });
}

/// What the waiter thread knows about the started process.
#[derive(Debug, Default)]
struct Leader {
    /// Its exit status, once it ended.
    status: Option<ExitStatus>,
    /// It has been reaped: its pid, and so the run's group id, may now be reused.
    reaped: bool,
}

/// Waits for the child to end without reaping it and publishes its exit status. Where
/// the process table can be read, the ended child is then kept as a zombie until
/// `release` is dropped (with the [`ServerProcess`], after its stop), so that neither its
/// pid nor the run's process-group id can be reused while the harness still signals and
/// inspects the group. Without the table, or when `waitid` is unavailable, the child is
/// reaped at once while holding the lock, so a signal sent under the same lock never
/// reaches a reused pid.
fn spawn_waiter(
    mut child: Child,
    leader: Arc<Mutex<Leader>>,
    release: Receiver<()>,
    tx: Sender<Event>,
) {
    thread::spawn(move || {
        let lock = || leader.lock().unwrap_or_else(|p| p.into_inner());
        let ended = wait_without_reaping(child.id());
        if let Some(status) = ended.filter(|_| table::supported()) {
            lock().status = Some(status);
            let _ = tx.send(Event::Exited(Ok(status)));
            // returns once the ServerProcess, and so its release sender, is gone
            let _ = release.recv();
            let mut guard = lock();
            let _ = child.wait();
            guard.reaped = true;
            return;
        }
        let status = {
            let mut guard = lock();
            let status = child.wait();
            guard.reaped = true;
            if let Ok(s) = &status {
                guard.status = Some(*s);
            }
            status
        };
        let _ = tx.send(Event::Exited(status.map_err(|e| e.to_string())));
    });
}

/// Waits until the child `pid` has ended, leaving it waitable (`WNOWAIT`), and returns
/// its exit status; `None` when `waitid` fails or reports a state it cannot express.
fn wait_without_reaping(pid: u32) -> Option<ExitStatus> {
    let id = libc::id_t::from(pid);
    loop {
        // SAFETY: siginfo_t is a plain C struct; all zero bytes is a valid value.
        let mut info: libc::siginfo_t = unsafe { std::mem::zeroed() };
        // SAFETY: `info` is a valid, writable siginfo_t; WNOWAIT leaves the child
        // waitable, so std's Child::wait reaps it afterwards.
        let rc = unsafe { libc::waitid(libc::P_PID, id, &mut info, libc::WEXITED | libc::WNOWAIT) };
        if rc == 0 {
            // SAFETY: waitid filled `info` for a child that ended (WEXITED), for which
            // si_status holds the exit code or the signal number.
            let value = unsafe { info.si_status() };
            // the raw value is the one waitpid would give: code << 8, or the signal
            // number (with 0x80 when a core was dumped)
            return match info.si_code {
                libc::CLD_EXITED => Some(ExitStatus::from_raw((value & 0xff) << 8)),
                libc::CLD_KILLED => Some(ExitStatus::from_raw(value & 0x7f)),
                libc::CLD_DUMPED => Some(ExitStatus::from_raw((value & 0x7f) | 0x80)),
                _ => None,
            };
        }
        if std::io::Error::last_os_error().kind() != std::io::ErrorKind::Interrupted {
            return None;
        }
    }
}

fn send(pid: libc::pid_t, sig: libc::c_int) -> bool {
    // SAFETY: kill has no memory-safety preconditions; the callers make sure `pid` names
    // a process (or, negated, a group) of this run.
    unsafe { libc::kill(pid, sig) == 0 }
}

fn group_send(pgid: libc::pid_t, sig: libc::c_int) -> bool {
    // SAFETY: killpg has no memory-safety preconditions; the callers make sure the group
    // is this run's.
    unsafe { libc::killpg(pgid, sig) == 0 }
}

/// A process found running when it should have ended.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Leftover {
    /// The process. When the platform cannot read the process table, a placeholder
    /// with pid 0 stands for "the group still has a member".
    pub entry: ProcEntry,
    /// It was still in the run's process group; `false` means it left the group (for
    /// example with `setsid`), so a signal to the group did not reach it.
    pub in_group: bool,
}

impl Leftover {
    fn describe(&self, when: &str) -> String {
        format!(
            "pid {} (parent {}, group {}{}) {when}",
            self.entry.pid,
            self.entry.ppid,
            self.entry.pgid,
            if self.in_group {
                ""
            } else {
                ", outside the run's group"
            }
        )
    }
}

/// What [`ServerProcess::stop`] found.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct StopReport {
    /// The started process's exit status, once it ended.
    pub exit: Option<ExitStatus>,
    /// The descendants (and other group members) seen when the stop began.
    pub tracked: Vec<ProcEntry>,
    /// The started process was still running when the grace period after `SIGTERM`
    /// ended.
    pub leader_after_term: bool,
    /// Descendants still running when the grace period ended; they got `SIGKILL`.
    pub after_term: Vec<Leftover>,
    /// The started process was still running after `SIGKILL` and the kill deadline.
    pub leader_after_kill: bool,
    /// Descendants still running after `SIGKILL` and the kill deadline: left behind.
    pub after_kill: Vec<Leftover>,
    /// Whether the process table could be read; when not, only the process group was
    /// checked.
    pub table: bool,
}

impl StopReport {
    /// Everything ended within the grace period that followed `SIGTERM`, and nothing
    /// was found outside the group.
    pub fn is_clean(&self) -> bool {
        !self.leader_after_term && self.after_term.is_empty() && !self.left_behind()
    }

    /// Something still ran after `SIGKILL`.
    pub fn left_behind(&self) -> bool {
        self.leader_after_kill || !self.after_kill.is_empty()
    }

    /// [`ProcessError::Leak`] unless [`StopReport::is_clean`].
    pub fn check(&self) -> Result<(), ProcessError> {
        if self.is_clean() {
            return Ok(());
        }
        let mut details = Vec::new();
        if self.leader_after_term {
            details.push("the started process outlived the grace period after SIGTERM".to_string());
        }
        for l in &self.after_term {
            details.push(l.describe("outlived the grace period after SIGTERM"));
        }
        if self.leader_after_kill {
            details.push("the started process outlived SIGKILL".to_string());
        }
        for l in &self.after_kill {
            details.push(l.describe("outlived SIGKILL"));
        }
        Err(ProcessError::Leak { details })
    }
}

/// A running (or ended) process started by [`Launch`]. Dropping it stops it, and when
/// nobody took the [`StopReport`] with [`ServerProcess::stop`], a stop that was not clean
/// fails the test: the drop panics with the leak, and the run directory is kept.
#[derive(Debug)]
pub struct ServerProcess {
    pid: u32,
    leader: Arc<Mutex<Leader>>,
    /// Dropped with the process handle; until then an ended process stays unreaped.
    _release: Sender<()>,
    events: Receiver<Event>,
    seen: Vec<OutputLine>,
    dropped_lines: u64,
    eof: [bool; 2],
    exit: Option<ExitStatus>,
    stdin: Option<ChildStdin>,
    workdir: Workdir,
    scale: TimeScale,
    ready_deadline: Duration,
    grace: Duration,
    kill_deadline: Duration,
    expect: ReadyExpect,
    ready: Option<Ready>,
    report: Option<StopReport>,
    /// The caller took the report from [`ServerProcess::stop`], so it judges it.
    report_returned: bool,
}

impl std::fmt::Debug for Event {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Event::Line(l) => write!(f, "Line({l:?})"),
            Event::Eof(s, dropped) => write!(f, "Eof({s:?}, {dropped} dropped)"),
            Event::Exited(s) => write!(f, "Exited({s:?})"),
        }
    }
}

impl ServerProcess {
    /// The process id, which is also its process group id.
    pub fn pid(&self) -> u32 {
        self.pid
    }

    /// The run directory.
    pub fn workdir(&self) -> &Workdir {
        &self.workdir
    }

    /// Keeps the run directory when the process is dropped.
    pub fn keep_workdir(&mut self) {
        self.workdir.keep();
    }

    /// The time scale in force.
    pub fn time_scale(&self) -> TimeScale {
        self.scale
    }

    /// The scaled grace period.
    pub fn grace(&self) -> Duration {
        self.grace
    }

    /// The ready line, once read.
    pub fn ready(&self) -> Option<&Ready> {
        self.ready.as_ref()
    }

    /// Every line seen so far, both streams in arrival order.
    pub fn seen(&self) -> &[OutputLine] {
        &self.seen
    }

    /// The lines seen so far, joined with `\n`, at most the last
    /// [`MAX_TRANSCRIPT_BYTES`] of them (with a note when lines were cut or not kept).
    pub fn transcript(&self) -> String {
        let mut out: Vec<&str> = self.seen.iter().map(|l| l.text.as_str()).collect();
        let note;
        if self.dropped_lines > 0 {
            note = format!(
                "...[{} more lines in the capture files]",
                self.dropped_lines
            );
            out.push(&note);
        }
        let text = out.join("\n");
        if text.len() <= MAX_TRANSCRIPT_BYTES {
            return text;
        }
        let mut cut = text.len() - MAX_TRANSCRIPT_BYTES;
        while !text.is_char_boundary(cut) {
            cut += 1;
        }
        format!(
            "...[earlier lines cut; see stdout.txt and stderr.txt]\n{}",
            text.get(cut..).unwrap_or_default()
        )
    }

    fn record(&mut self, event: Event) {
        match event {
            Event::Line(line) => {
                if self.seen.len() < MAX_SEEN_LINES {
                    self.seen.push(line);
                } else {
                    self.dropped_lines += 1;
                }
            }
            Event::Eof(stream, dropped) => {
                self.dropped_lines += dropped;
                match stream {
                    Stream::Stdout => self.eof[0] = true,
                    Stream::Stderr => self.eof[1] = true,
                }
            }
            Event::Exited(status) => {
                if let Ok(s) = status {
                    self.exit = Some(s);
                }
            }
        }
    }

    /// The next event before `deadline`, recorded; `None` on timeout or when every
    /// sender is gone.
    fn next_event(&mut self, deadline: Instant) -> Option<EventKind> {
        let left = deadline.saturating_duration_since(Instant::now());
        let event = match self.events.recv_timeout(left) {
            Ok(e) => e,
            Err(RecvTimeoutError::Timeout) | Err(RecvTimeoutError::Disconnected) => return None,
        };
        let kind = match &event {
            Event::Line(l) => EventKind::Line(l.clone()),
            Event::Eof(..) => EventKind::Eof,
            Event::Exited(_) => EventKind::Exited,
        };
        self.record(event);
        Some(kind)
    }

    fn output_closed(&self) -> bool {
        self.eof[0] && self.eof[1]
    }

    /// Reads output until the ready line, within the scaled ready deadline. A line that
    /// starts like a ready line but does not follow the contract is an error, and so is
    /// a ready line that names port 0 or an address that is not loopback
    /// (contracts/cli.md section 2.5). Standard output closing, or the process ending,
    /// before the ready line is an error too, reported as soon as it is known.
    pub fn wait_ready(&mut self) -> Result<Ready, ProcessError> {
        if let Some(r) = &self.ready {
            return Ok(r.clone());
        }
        let deadline = after(self.ready_deadline);
        loop {
            match self.next_event(deadline) {
                Some(EventKind::Line(line)) => {
                    if let Some(result) = self.accept_ready_line(line) {
                        return result;
                    }
                }
                Some(EventKind::Eof) | Some(EventKind::Exited) => {
                    if self.eof[0] || self.exit.is_some() {
                        return self.before_ready(deadline);
                    }
                }
                None => {
                    return Err(ProcessError::ReadyTimeout {
                        deadline: self.ready_deadline,
                        transcript: self.transcript(),
                        run_dir: None,
                    })
                }
            }
        }
    }

    /// Judges one line read while waiting for the ready line: `None` when it is not a
    /// claimed ready line on standard output, otherwise the ready line or the error it
    /// makes. The same rules hold whichever event arrived first.
    fn accept_ready_line(&mut self, line: OutputLine) -> Option<Result<Ready, ProcessError>> {
        if line.stream != Stream::Stdout || !self.expect.claims(&line.text) {
            return None;
        }
        let Some(ready) = parse_ready(&line.text, self.expect) else {
            return Some(Err(ProcessError::MalformedReady {
                line: line.text,
                transcript: self.transcript(),
                run_dir: None,
            }));
        };
        if ready.port() == 0 {
            return Some(Err(ProcessError::ReadyPortZero {
                line: line.text,
                transcript: self.transcript(),
                run_dir: None,
            }));
        }
        if let Err(e) = ready.loopback_addr() {
            let host = match e {
                ProcessError::NotLoopback { host, .. } => host,
                other => other.to_string(),
            };
            return Some(Err(ProcessError::NotLoopback {
                host,
                transcript: self.transcript(),
                run_dir: None,
            }));
        }
        self.ready = Some(ready.clone());
        Some(Ok(ready))
    }

    /// Standard output closed or the process ended without a ready line so far. The
    /// lines still on their way can hold it: standard output is read to its end (within
    /// the scaled kill deadline), then the exit status is awaited briefly, so that an exit
    /// is told from a closed stream.
    fn before_ready(&mut self, deadline: Instant) -> Result<Ready, ProcessError> {
        let drain = after(self.kill_deadline).min(deadline);
        while !self.eof[0] {
            match self.next_event(drain) {
                Some(EventKind::Line(line)) => {
                    if let Some(result) = self.accept_ready_line(line) {
                        return result;
                    }
                }
                Some(_) => {}
                None => break,
            }
        }
        let settle = after(self.scale.apply(EXIT_AFTER_CLOSE)).min(deadline);
        while self.exit.is_none() {
            if self.next_event(settle).is_none() {
                break;
            }
        }
        Err(match self.exit {
            Some(s) => ProcessError::ExitedBeforeReady {
                status: status_text(s),
                transcript: self.transcript(),
                run_dir: None,
            },
            None => ProcessError::ClosedBeforeReady {
                transcript: self.transcript(),
                run_dir: None,
            },
        })
    }

    /// Reads output until a line containing `needle`, for at most `timeout` scaled.
    /// `false` when both streams close or the time runs out first. Lines read are added
    /// to [`ServerProcess::seen`].
    pub fn until(&mut self, needle: &str, timeout: Duration) -> bool {
        let deadline = after(self.scale.apply(timeout));
        while !self.output_closed() {
            match self.next_event(deadline) {
                Some(EventKind::Line(line)) if line.text.contains(needle) => return true,
                Some(_) => {}
                None => return false,
            }
        }
        false
    }

    /// Reads the output that is left, for at most `timeout` scaled or until both streams
    /// close, and returns the whole transcript.
    pub fn rest(&mut self, timeout: Duration) -> String {
        let deadline = after(self.scale.apply(timeout));
        while !self.output_closed() {
            if self.next_event(deadline).is_none() {
                break;
            }
        }
        self.transcript()
    }

    /// Writes to the process's standard input (only with [`StdinMode::Pipe`]).
    pub fn write_stdin(&mut self, bytes: &[u8]) -> Result<(), ProcessError> {
        match self.stdin.as_mut() {
            Some(s) => s
                .write_all(bytes)
                .and_then(|()| s.flush())
                .map_err(|e| ProcessError::io("write to the process's stdin", e)),
            None => Err(ProcessError::io(
                "write to the process's stdin",
                std::io::Error::new(std::io::ErrorKind::NotConnected, "no stdin pipe"),
            )),
        }
    }

    /// Closes the process's standard input pipe, if it has one.
    pub fn close_stdin(&mut self) {
        self.stdin = None;
    }

    /// Sends signal `sig` to the started process alone (not its group), as the donor's
    /// tests do with `send_signal`. `Ok(false)` when it has already ended, so no signal
    /// can reach a reused pid.
    pub fn send_signal(&self, sig: libc::c_int) -> Result<bool, ProcessError> {
        let pid = self.pid_t()?;
        let guard = self.leader.lock().unwrap_or_else(|p| p.into_inner());
        if guard.status.is_some() || guard.reaped {
            return Ok(false);
        }
        if send(pid, sig) {
            Ok(true)
        } else {
            Err(ProcessError::io(
                format!("signal {sig} to pid {pid}"),
                std::io::Error::last_os_error(),
            ))
        }
    }

    /// Sends a scenario step's signal to the started process.
    pub fn signal(&self, signal: Signal) -> Result<bool, ProcessError> {
        self.send_signal(match signal {
            Signal::Term => libc::SIGTERM,
            Signal::Hup => libc::SIGHUP,
            Signal::Int => libc::SIGINT,
        })
    }

    fn pid_t(&self) -> Result<libc::pid_t, ProcessError> {
        libc::pid_t::try_from(self.pid).map_err(|_| ProcessError::Unsupported {
            what: format!("pid {}", self.pid),
        })
    }

    /// Sends `sig` to the run's process group. While the started process is not yet
    /// reaped (it is kept unreaped where the process table can be read, see
    /// `spawn_waiter`) this is one `killpg` under the lock: the group id cannot have been
    /// reused. Once it is reaped, each member the process table shows gets the signal by
    /// pid, unless the table shows the group id taken by another group (see
    /// [`own_group_members`]); `killpg` is used only when the table cannot be read.
    fn signal_group(&self, sig: libc::c_int) -> bool {
        let Ok(pgid) = self.pid_t() else { return false };
        {
            let guard = self.leader.lock().unwrap_or_else(|p| p.into_inner());
            if !guard.reaped {
                return group_send(pgid, sig);
            }
        }
        match table::snapshot() {
            Ok(t) => {
                let mut any = false;
                for m in own_group_members(&t, self.pid, self.is_reaped()) {
                    if !m.zombie {
                        any |= signal_checked(&m, sig);
                    }
                }
                any
            }
            Err(_) => group_send(pgid, sig),
        }
    }

    fn is_reaped(&self) -> bool {
        self.leader.lock().unwrap_or_else(|p| p.into_inner()).reaped
    }

    /// The exit status, if the process has ended; reads pending events without
    /// waiting.
    pub fn try_exit_status(&mut self) -> Option<ExitStatus> {
        while self.exit.is_none() {
            match self.events.try_recv() {
                Ok(e) => self.record(e),
                Err(_) => break,
            }
        }
        self.exit
    }

    /// Waits at most `timeout` scaled for the process to end.
    pub fn wait_exit(&mut self, timeout: Duration) -> Option<ExitStatus> {
        let deadline = after(self.scale.apply(timeout));
        self.wait_exit_until(deadline)
    }

    fn wait_exit_until(&mut self, deadline: Instant) -> Option<ExitStatus> {
        while self.exit.is_none() {
            if self.next_event(deadline).is_none() {
                break;
            }
        }
        self.exit
    }

    /// The process's descendants now, and any other member of its group, not counting
    /// itself; zombies count as ended and are left out.
    pub fn descendants(&self) -> Result<Vec<ProcEntry>, ProcessError> {
        let t = table::snapshot()?;
        Ok(tracked_now(&t, self.pid, self.is_reaped()))
    }

    /// The processes of `procs` still running after at most `timeout` scaled; zombies
    /// count as ended, and a reused pid is not mistaken for the process seen.
    pub fn gone(
        &self,
        procs: &[ProcEntry],
        timeout: Duration,
    ) -> Result<Vec<ProcEntry>, ProcessError> {
        gone(procs, self.scale.apply(timeout))
    }

    fn leftovers(&self, tracked: &[ProcEntry]) -> (Vec<Leftover>, bool) {
        match table::snapshot() {
            Ok(t) => {
                let mut found: Vec<ProcEntry> = table::still_running(&t, tracked);
                for m in own_group_members(&t, self.pid, self.is_reaped()) {
                    if m.pid != self.pid && !m.zombie && !found.iter().any(|f| f.same_process(&m)) {
                        found.push(m);
                    }
                }
                let out = found
                    .into_iter()
                    .map(|entry| Leftover {
                        entry,
                        in_group: entry.pgid == self.pid,
                    })
                    .collect();
                (out, true)
            }
            Err(_) => {
                let alive = self.is_reaped() && self.pid_t().is_ok_and(|g| group_send(g, 0));
                let out = if alive {
                    vec![Leftover {
                        entry: ProcEntry {
                            pid: 0,
                            ppid: 0,
                            pgid: self.pid,
                            start: 0,
                            zombie: false,
                        },
                        in_group: true,
                    }]
                } else {
                    Vec::new()
                };
                (out, false)
            }
        }
    }

    fn leftovers_until(
        &mut self,
        tracked: &[ProcEntry],
        deadline: Instant,
    ) -> (Vec<Leftover>, bool) {
        loop {
            // keep the output flowing while waiting
            self.try_exit_status();
            let (left, table_ok) = self.leftovers(tracked);
            if left.is_empty() || Instant::now() >= deadline {
                return (left, table_ok);
            }
            thread::sleep(POLL.min(deadline.saturating_duration_since(Instant::now())));
        }
    }

    /// Stops the process and checks that it left nothing behind:
    ///
    /// 1. notes its descendants and group members;
    /// 2. sends `SIGTERM` to the group;
    /// 3. waits up to the scaled grace period for the process and every noted or group
    ///    process to end;
    /// 4. sends `SIGKILL` to the group and, by pid, to any leftover outside it;
    /// 5. waits up to the scaled kill deadline, and reads the remaining output.
    ///
    /// Calling it again returns the first report. The caller judges the report (for
    /// example with [`StopReport::check`]); a handle dropped without this call checks it
    /// itself and panics when the stop was not clean.
    pub fn stop(&mut self) -> StopReport {
        self.report_returned = true;
        self.stop_inner()
    }

    fn stop_inner(&mut self) -> StopReport {
        if let Some(r) = &self.report {
            return r.clone();
        }
        let tracked = match table::snapshot() {
            Ok(t) => tracked_now(&t, self.pid, self.is_reaped()),
            Err(_) => Vec::new(),
        };
        self.signal_group(libc::SIGTERM);
        let term_deadline = after(self.grace);
        let leader_after_term = self.wait_exit_until(term_deadline).is_none();
        let (after_term, table_ok) = self.leftovers_until(&tracked, term_deadline);

        let mut leader_after_kill = false;
        let mut after_kill = Vec::new();
        if leader_after_term || !after_term.is_empty() {
            self.signal_group(libc::SIGKILL);
            for l in &after_term {
                if !l.in_group && l.entry.pid != 0 {
                    signal_checked(&l.entry, libc::SIGKILL);
                }
            }
            let kill_deadline = after(self.kill_deadline);
            leader_after_kill = self.wait_exit_until(kill_deadline).is_none();
            let still: Vec<ProcEntry> = after_term.iter().map(|l| l.entry).collect();
            after_kill = self.leftovers_until(&still, kill_deadline).0;
        }
        let drain = after(self.kill_deadline);
        while !self.output_closed() {
            if self.next_event(drain).is_none() {
                break;
            }
        }
        self.stdin = None;
        let report = StopReport {
            exit: self.exit,
            tracked,
            leader_after_term,
            after_term,
            leader_after_kill,
            after_kill,
            table: table_ok,
        };
        self.report = Some(report.clone());
        report
    }
}

#[derive(Debug)]
enum EventKind {
    Line(OutputLine),
    Eof,
    Exited,
}

impl Drop for ServerProcess {
    /// Stops the process. The run directory is kept when the test is already panicking,
    /// when something outlived `SIGKILL`, or when the stop was not clean and nobody took
    /// the report; in that last case the drop panics with the leak, so a test that relies
    /// on the drop still fails on an orphaned process. While already panicking it only
    /// prints, so the first failure is the one reported.
    fn drop(&mut self) {
        let unjudged = !self.report_returned;
        let report = self.stop_inner();
        let check = report.check();
        let panicking = thread::panicking();
        if report.left_behind() || panicking || (unjudged && check.is_err()) {
            self.workdir.keep();
            let root = self.workdir.root().display().to_string();
            eprintln!("cnf process harness: kept {root} (pid {})", self.pid);
            if let Err(e) = check {
                if unjudged && !panicking {
                    panic!("cnf process harness: {e}\nrun directory kept at {root}");
                }
                eprintln!("cnf process harness: {e}");
            }
        }
    }
}

/// The members of process group `pid` in `t`. Where the process table can be read the
/// started process stays unreaped while the handle lives, so its pid and the group id
/// cannot be reused and every member is the run's. Once it has been reaped (`reaped`,
/// only when `waitid` is unavailable), a process that now holds that pid leads another
/// group, and then no member is taken for the run's. A reused group whose new leader
/// has already ended is not detected; that residual window exists only on this
/// fallback path.
fn own_group_members(t: &[ProcEntry], pid: u32, reaped: bool) -> Vec<ProcEntry> {
    if reaped && t.iter().any(|e| e.pid == pid) {
        return Vec::new();
    }
    table::group_members(t, pid)
}

/// The descendants of `pid` and the other members of its group in `table`, without
/// `pid` itself and without zombies.
fn tracked_now(t: &[ProcEntry], pid: u32, reaped: bool) -> Vec<ProcEntry> {
    let mut out: Vec<ProcEntry> = if reaped {
        // a reaped pid has no children of its own any more; a reused one is someone else
        Vec::new()
    } else {
        table::descendants_of(t, pid)
            .into_iter()
            .filter(|e| !e.zombie)
            .collect()
    };
    for m in own_group_members(t, pid, reaped) {
        if m.pid != pid && !m.zombie && !out.iter().any(|e| e.same_process(&m)) {
            out.push(m);
        }
    }
    out
}

/// Sends `sig` to `entry` by pid if the process table still shows the same process.
fn signal_checked(entry: &ProcEntry, sig: libc::c_int) -> bool {
    let Ok(pid) = libc::pid_t::try_from(entry.pid) else {
        return false;
    };
    match table::snapshot() {
        Ok(t) if !table::still_running(&t, std::slice::from_ref(entry)).is_empty() => {
            send(pid, sig)
        }
        _ => false,
    }
}

/// The processes of `procs` still running after at most `timeout`; zombies count as
/// ended. The donor's `gone`, with the reused-pid check added.
pub fn gone(procs: &[ProcEntry], timeout: Duration) -> Result<Vec<ProcEntry>, ProcessError> {
    let deadline = after(timeout);
    loop {
        let t = table::snapshot()?;
        let left = table::still_running(&t, procs);
        if left.is_empty() || Instant::now() >= deadline {
            return Ok(left);
        }
        thread::sleep(POLL.min(deadline.saturating_duration_since(Instant::now())));
    }
}

/// Sends `SIGKILL` to each process of `procs` that still runs. The donor's `kill_all`.
pub fn kill_all(procs: &[ProcEntry]) {
    for p in procs {
        signal_checked(p, libc::SIGKILL);
    }
}

/// The instant `d` from now; a `d` too large for the clock gives a day from now, which
/// is beyond every scaled deadline the harness uses.
fn after(d: Duration) -> Instant {
    let now = Instant::now();
    now.checked_add(d)
        .or_else(|| now.checked_add(Duration::from_secs(86_400)))
        .unwrap_or(now)
}

fn status_text(s: ExitStatus) -> String {
    match (s.code(), s.signal()) {
        (Some(c), _) => format!("exit status: {c}"),
        (None, Some(sig)) => format!("signal: {sig}"),
        _ => s.to_string(),
    }
}
