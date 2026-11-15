//! The errors of the process harness.

use std::fmt;
use std::path::{Path, PathBuf};
use std::time::Duration;

/// Why the harness could not start, read or stop a process, or prepare its files.
///
/// Errors that happen while a process runs carry the output seen so far
/// (`transcript`), so a failing test can print what the server said. The errors of a
/// failed [`super::Launch::start`] also name the run directory the harness kept
/// (`run_dir`), whose `stdout.txt` and `stderr.txt` CI keeps as artifacts.
#[derive(Debug)]
pub enum ProcessError {
    /// An operating-system call failed.
    Io {
        /// What the harness was doing.
        context: String,
        /// The error.
        source: std::io::Error,
    },
    /// `PULSAR_CONSOLE_TEST_TIME_SCALE` holds a value the harness does not accept.
    BadTimeScale {
        /// The value as read.
        value: String,
    },
    /// An environment entry the harness refuses: a reserved name, a malformed name, a
    /// NUL byte or a name given twice.
    BadEnv {
        /// Where the entry came from, for example `server.env` or `server.config.env`.
        origin: String,
        /// The name.
        name: String,
        /// Why it is refused.
        reason: String,
    },
    /// A scenario cannot be turned into files.
    BadScenario {
        /// Why.
        reason: String,
    },
    /// The process ended before it printed its ready line.
    ExitedBeforeReady {
        /// The exit status as text (`exit status: 3`, `signal: 15`).
        status: String,
        /// The output seen.
        transcript: String,
        /// The run directory kept after a failed start.
        run_dir: Option<PathBuf>,
    },
    /// Standard output closed before the ready line.
    ClosedBeforeReady {
        /// The output seen.
        transcript: String,
        /// The run directory kept after a failed start.
        run_dir: Option<PathBuf>,
    },
    /// No ready line within the deadline.
    ReadyTimeout {
        /// The scaled deadline.
        deadline: Duration,
        /// The output seen.
        transcript: String,
        /// The run directory kept after a failed start.
        run_dir: Option<PathBuf>,
    },
    /// A line starts like a ready line but does not follow the contract.
    MalformedReady {
        /// The line.
        line: String,
        /// The output seen.
        transcript: String,
        /// The run directory kept after a failed start.
        run_dir: Option<PathBuf>,
    },
    /// The ready line names port 0: the server printed the requested port, not the one
    /// it bound.
    ReadyPortZero {
        /// The line.
        line: String,
        /// The output seen.
        transcript: String,
        /// The run directory kept after a failed start.
        run_dir: Option<PathBuf>,
    },
    /// The ready line names an address that is not a loopback address.
    NotLoopback {
        /// The host as printed.
        host: String,
        /// The output seen; empty when the error comes from
        /// [`super::Ready::loopback_addr`] alone.
        transcript: String,
        /// The run directory kept after a failed start.
        run_dir: Option<PathBuf>,
    },
    /// The process left descendants running after the grace period that followed
    /// `SIGTERM`, or the harness could not remove them.
    Leak {
        /// One line per process: pid, parent, group and what happened to it.
        details: Vec<String>,
    },
    /// The operation is not available on this platform.
    Unsupported {
        /// What.
        what: String,
    },
    /// A directory the harness was asked to use already exists or is not empty.
    WorkdirTaken {
        /// The path.
        path: PathBuf,
    },
}

impl ProcessError {
    pub(crate) fn io(context: impl Into<String>, source: std::io::Error) -> Self {
        ProcessError::Io {
            context: context.into(),
            source,
        }
    }

    /// The output seen before the error, when the error carries it.
    pub fn transcript(&self) -> Option<&str> {
        match self {
            ProcessError::ExitedBeforeReady { transcript, .. }
            | ProcessError::ClosedBeforeReady { transcript, .. }
            | ProcessError::ReadyTimeout { transcript, .. }
            | ProcessError::MalformedReady { transcript, .. }
            | ProcessError::ReadyPortZero { transcript, .. }
            | ProcessError::NotLoopback { transcript, .. } => Some(transcript),
            _ => None,
        }
    }

    /// The run directory the harness kept after a failed start, with its captured
    /// `stdout.txt` and `stderr.txt`.
    pub fn run_dir(&self) -> Option<&Path> {
        match self {
            ProcessError::ExitedBeforeReady { run_dir, .. }
            | ProcessError::ClosedBeforeReady { run_dir, .. }
            | ProcessError::ReadyTimeout { run_dir, .. }
            | ProcessError::MalformedReady { run_dir, .. }
            | ProcessError::ReadyPortZero { run_dir, .. }
            | ProcessError::NotLoopback { run_dir, .. } => run_dir.as_deref(),
            _ => None,
        }
    }

    /// The same error, naming `dir` as the kept run directory when the error has the
    /// place for it.
    #[cfg_attr(not(unix), allow(dead_code))]
    pub(crate) fn kept_at(mut self, dir: &Path) -> Self {
        match &mut self {
            ProcessError::ExitedBeforeReady { run_dir, .. }
            | ProcessError::ClosedBeforeReady { run_dir, .. }
            | ProcessError::ReadyTimeout { run_dir, .. }
            | ProcessError::MalformedReady { run_dir, .. }
            | ProcessError::ReadyPortZero { run_dir, .. }
            | ProcessError::NotLoopback { run_dir, .. } => *run_dir = Some(dir.to_path_buf()),
            _ => {}
        }
        self
    }
}

impl fmt::Display for ProcessError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ProcessError::Io { context, source } => write!(f, "{context}: {source}"),
            ProcessError::BadTimeScale { value } => write!(
                f,
                "{} must be a number above 0 and at most {}, not {value:?}",
                super::TIME_SCALE_ENV,
                super::MAX_TIME_SCALE
            ),
            ProcessError::BadEnv {
                origin,
                name,
                reason,
            } => write!(f, "{origin}: {name:?}: {reason}"),
            ProcessError::BadScenario { reason } => write!(f, "scenario: {reason}"),
            ProcessError::ExitedBeforeReady {
                status,
                transcript,
                run_dir,
            } => {
                write!(
                    f,
                    "the process ended ({status}) before its ready line; output:\n{transcript}"
                )?;
                kept(f, run_dir)
            }
            ProcessError::ClosedBeforeReady {
                transcript,
                run_dir,
            } => {
                write!(
                    f,
                    "the process closed its standard output before its ready line; output:\n{transcript}"
                )?;
                kept(f, run_dir)
            }
            ProcessError::ReadyTimeout {
                deadline,
                transcript,
                run_dir,
            } => {
                write!(
                    f,
                    "no ready line within {:.3} s; output:\n{transcript}",
                    deadline.as_secs_f64()
                )?;
                kept(f, run_dir)
            }
            ProcessError::MalformedReady {
                line,
                transcript,
                run_dir,
            } => {
                write!(
                    f,
                    "a ready line that does not follow contracts/cli.md: {line:?}; output:\n{transcript}"
                )?;
                kept(f, run_dir)
            }
            ProcessError::ReadyPortZero {
                line,
                transcript,
                run_dir,
            } => {
                write!(
                    f,
                    "the ready line names port 0, not the bound port: {line:?}; output:\n{transcript}"
                )?;
                kept(f, run_dir)
            }
            ProcessError::NotLoopback {
                host,
                transcript,
                run_dir,
            } => {
                write!(
                    f,
                    "the ready line names {host:?}, which is not a loopback address"
                )?;
                if !transcript.is_empty() {
                    write!(f, "; output:\n{transcript}")?;
                }
                kept(f, run_dir)
            }
            ProcessError::Leak { details } => {
                write!(f, "processes left behind:")?;
                for d in details {
                    write!(f, "\n  {d}")?;
                }
                Ok(())
            }
            ProcessError::Unsupported { what } => {
                write!(f, "not supported on this platform: {what}")
            }
            ProcessError::WorkdirTaken { path } => {
                write!(f, "{} already exists and is not empty", path.display())
            }
        }
    }
}

fn kept(f: &mut fmt::Formatter<'_>, run_dir: &Option<PathBuf>) -> fmt::Result {
    match run_dir {
        Some(dir) => write!(f, "\nrun directory kept at {}", dir.display()),
        None => Ok(()),
    }
}

impl std::error::Error for ProcessError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            ProcessError::Io { source, .. } => Some(source),
            _ => None,
        }
    }
}
