//! Owned by CNF-07. The process harness for the server binary and the fake engines.
//!
//! The harness starts a server process from outside, the way an operator or a black-box
//! test does, and proves that it leaves nothing behind:
//!
//! - [`Launch`] spawns the program in a new process group, with a cleared environment
//!   plus an allowlist (see [`env`]), a per-run temporary `HOME`, `XDG_*` directories,
//!   `TMPDIR` and data directory ([`Workdir`]), and `--port 0`;
//! - [`ServerProcess::wait_ready`] reads the ready line ([`ready`], documented in
//!   `specs/022-console-serving-parity/contracts/cli.md`) within a deadline that scales
//!   with `PULSAR_CONSOLE_TEST_TIME_SCALE` ([`TimeScale`]);
//! - both output streams are captured to files under the run directory, and the lines
//!   are kept in memory for [`ServerProcess::until`] and [`ServerProcess::rest`] up to a
//!   byte budget ([`MAX_SEEN_BYTES`] by default) and [`MAX_SEEN_LINES`]; a failed start
//!   keeps the run directory for the CI artifacts;
//! - [`ServerProcess::stop`] sends `SIGTERM` to the group, waits a grace period, sends
//!   `SIGKILL` to whatever is left, and reports in a [`StopReport`] every descendant still
//!   running after the grace period, whether it stayed in the group or left it. Dropping
//!   a [`ServerProcess`] stops it, so a failing test leaves no process behind, and a drop
//!   whose report nobody took panics when that stop was not clean;
//! - [`lifecycle_lock`] serializes the process-lifecycle tests of one test binary;
//! - [`ScenarioFiles`] writes the generated `bpe-bytes` tokenizer directory, the run
//!   config and the data-directory files of a scenario.
//!
//! Descendants are found without `ps`: on Linux by reading `/proc`, on Darwin through
//! `proc_listallpids` and `proc_pidinfo` ([`table`]). Elsewhere only the process group is
//! checked, with `killpg(pgid, 0)`. The Darwin path is exercised by this package's tests;
//! the Linux path is written for Linux and its parser is unit-tested on every platform,
//! but its behavior on a Linux host is unverified until a Linux CI run shows it.
//!
//! Starting and stopping processes ([`Launch`], [`ServerProcess`]) is compiled on Unix
//! only; the parsers, the environment rules and the scenario files build everywhere.
//!
//! The harness runs synthetic programs only: the test-only child `cnf_child`, the fake
//! engines and the server under test on synthetic engines. Nothing here is more than
//! qualified on synthetic backends.
//!
//! Behavior reference: project-maya serve/test_stop.py:70-145 at 7e68a30f (`Proc`,
//! `gone`, `kill_all`, `descendants`) and serve/test_glm_dsa_serve.py:220-250 at 7e68a30f
//! (start and `read_until`).

pub mod env;
mod error;
mod files;
pub mod ready;
mod scale;
#[cfg(unix)]
mod server;
pub mod table;
mod workdir;

use std::sync::{Mutex, MutexGuard};

pub use error::ProcessError;
pub use files::{ScenarioFiles, CONFIG_FILE_NAME, TOKENIZER_DIR_NAME};
pub use ready::{parse_ready, Ready, ReadyExpect, ReadyLine};
pub use scale::{
    TimeScale, DEFAULT_GRACE, DEFAULT_KILL_DEADLINE, DEFAULT_READY_DEADLINE, MAX_TIME_SCALE,
    TIME_SCALE_ENV,
};
#[cfg(unix)]
pub use server::{
    gone, kill_all, Launch, Leftover, OutputLine, ServerProcess, StdinMode, StopReport, Stream,
    MAX_CAPTURE_BYTES, MAX_LINE_BYTES, MAX_SEEN_BYTES, MAX_SEEN_LINES, MAX_TRANSCRIPT_BYTES,
};
pub use table::ProcEntry;
pub use workdir::Workdir;

static LIFECYCLE: Mutex<()> = Mutex::new(());

/// Serializes the process-lifecycle tests of one test binary: each such test holds the
/// guard for its whole run. A test that panicked while holding it does not poison it for
/// the others.
pub fn lifecycle_lock() -> MutexGuard<'static, ()> {
    LIFECYCLE
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn lifecycle_lock_survives_a_panicking_holder() {
        let result = std::thread::spawn(|| {
            let _guard = lifecycle_lock();
            panic!("a lifecycle test failed while holding the lock");
        })
        .join();
        assert!(result.is_err());
        // the lock is usable again, and is released at the end of the scope
        drop(lifecycle_lock());
        drop(lifecycle_lock());
    }
}
