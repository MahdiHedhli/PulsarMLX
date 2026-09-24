//! The parent side of the child-process design (plan §8.1-8.2; contract
//! error_handling.child_process).
//!
//! The parent launches the `qualify` child with a fixed environment, enforces
//! the frozen watchdog (SIGKILL, reap, TIMEOUT, no retry), and accepts a report
//! only if the child exited 0, the report exists and parses, it echoes the
//! frozen hashes, and its case-id set equals the manifest's exactly. Every
//! other outcome is a reported failure -- never a harness abort, never a
//! silent pass.

use std::collections::{BTreeMap, BTreeSet};
use std::os::unix::process::ExitStatusExt;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

use serde_json::Value;

use crate::fixture::Manifest;
use crate::frozen;

/// How a child process ended.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ChildOutcome {
    /// Exited normally with this status.
    Exited(i32),
    /// Terminated by this signal.
    Signaled(i32),
    /// The watchdog fired: SIGKILL was sent and the child reaped.
    Timeout {
        elapsed_ms: u128,
        reaped_signal: Option<i32>,
    },
    /// The child could not be started.
    SpawnFailed(String),
}

impl ChildOutcome {
    pub fn describe(&self) -> String {
        match self {
            ChildOutcome::Exited(c) => format!("EXIT_STATUS {c}"),
            ChildOutcome::Signaled(s) => format!("SIGNAL {s}"),
            ChildOutcome::Timeout {
                elapsed_ms,
                reaped_signal,
            } => {
                format!("TIMEOUT after {elapsed_ms} ms (SIGKILL sent; reaped with signal {reaped_signal:?})")
            }
            ChildOutcome::SpawnFailed(e) => format!("SPAWN_FAILED {e}"),
        }
    }
}

#[derive(Clone, Debug)]
pub struct ChildRun {
    pub outcome: ChildOutcome,
    pub elapsed_ms: u128,
    pub stdout_path: PathBuf,
    pub stderr_path: PathBuf,
}

/// The fixed child environment (plan §8.1): the environment is cleared, then
/// MLX_ENABLE_TF32=0, DYLD_LIBRARY_PATH = the native prefix's lib directory
/// only, the native prefix itself (so the child can prove the loaded
/// libraries come from it), and a minimal PATH/HOME/TMPDIR. The three
/// forbidden MLX variables are therefore absent.
pub fn child_env(native_prefix: &Path, tmpdir: &Path) -> Vec<(String, String)> {
    vec![
        ("MLX_ENABLE_TF32".into(), "0".into()),
        (
            "DYLD_LIBRARY_PATH".into(),
            native_prefix.join("lib").to_string_lossy().into_owned(),
        ),
        (
            "PULSAR_F020_NATIVE_PREFIX".into(),
            native_prefix.to_string_lossy().into_owned(),
        ),
        ("PATH".into(), "/usr/bin:/bin".into()),
        ("HOME".into(), tmpdir.to_string_lossy().into_owned()),
        ("TMPDIR".into(), tmpdir.to_string_lossy().into_owned()),
    ]
}

/// Run one child with a cleared environment plus `env`, stdout/stderr to
/// files in `log_dir`, under a watchdog of `timeout`. There is no retry.
pub fn run_child(
    program: &Path,
    args: &[String],
    env: &[(String, String)],
    timeout: Duration,
    log_dir: &Path,
    label: &str,
) -> ChildRun {
    let stdout_path = log_dir.join(format!("{label}.stdout"));
    let stderr_path = log_dir.join(format!("{label}.stderr"));
    let started = Instant::now();
    let files = (
        std::fs::File::create(&stdout_path),
        std::fs::File::create(&stderr_path),
    );
    let (out, err) = match files {
        (Ok(o), Ok(e)) => (o, e),
        (Err(e), _) | (_, Err(e)) => {
            return ChildRun {
                outcome: ChildOutcome::SpawnFailed(format!("log files: {e}")),
                elapsed_ms: 0,
                stdout_path,
                stderr_path,
            }
        }
    };
    let mut cmd = Command::new(program);
    cmd.args(args)
        .env_clear()
        .stdin(Stdio::null())
        .stdout(Stdio::from(out))
        .stderr(Stdio::from(err));
    for (k, v) in env {
        cmd.env(k, v);
    }
    let mut child = match cmd.spawn() {
        Ok(c) => c,
        Err(e) => {
            return ChildRun {
                outcome: ChildOutcome::SpawnFailed(e.to_string()),
                elapsed_ms: started.elapsed().as_millis(),
                stdout_path,
                stderr_path,
            }
        }
    };
    let outcome = loop {
        match child.try_wait() {
            Ok(Some(status)) => {
                break match (status.code(), status.signal()) {
                    (Some(c), _) => ChildOutcome::Exited(c),
                    (None, Some(s)) => ChildOutcome::Signaled(s),
                    (None, None) => ChildOutcome::SpawnFailed("unknown wait status".into()),
                };
            }
            Ok(None) => {}
            Err(e) => break ChildOutcome::SpawnFailed(format!("waitpid: {e}")),
        }
        if started.elapsed() >= timeout {
            // SIGKILL, then reap with waitpid (Child::wait). No retry.
            let _ = child.kill();
            let reaped = child.wait().ok().and_then(|s| s.signal());
            break ChildOutcome::Timeout {
                elapsed_ms: started.elapsed().as_millis(),
                reaped_signal: reaped,
            };
        }
        std::thread::sleep(Duration::from_millis(20));
    };
    ChildRun {
        outcome,
        elapsed_ms: started.elapsed().as_millis(),
        stdout_path,
        stderr_path,
    }
}

/// The frozen watchdog.
pub fn frozen_timeout() -> Duration {
    Duration::from_secs(frozen::CHILD_TIMEOUT_SECONDS)
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ReportError {
    ChildFailed(String),
    Missing(String),
    Unparsable(String),
    Schema(String),
    HashEcho(String),
    CaseSet {
        missing: Vec<String>,
        unexpected: Vec<String>,
        duplicated: Vec<String>,
    },
    Incomplete(String),
    /// A cleanup (teardown) MLX-C status failed; the child preserved it.
    Cleanup(Vec<String>),
    /// The handle or result-handle census does not balance after teardown.
    HandleCensus(String),
    /// The report was produced under a test-only fault mode.
    TestFault(String),
}

impl std::fmt::Display for ReportError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{self:?}")
    }
}

/// Accept a child's report under the parent failure conditions: the child
/// must have exited 0, the report must exist and parse, echo the frozen
/// contract/manifest/generator hashes, be complete, and carry exactly the
/// manifest's case ids (missing or duplicate ids fail).
pub fn accept_report(
    run: &ChildRun,
    report_path: &Path,
    manifest: &Manifest,
) -> Result<Value, ReportError> {
    match &run.outcome {
        ChildOutcome::Exited(0) => {}
        other => return Err(ReportError::ChildFailed(other.describe())),
    }
    let raw = std::fs::read(report_path)
        .map_err(|e| ReportError::Missing(format!("{}: {e}", report_path.display())))?;
    let report: Value =
        serde_json::from_slice(&raw).map_err(|e| ReportError::Unparsable(e.to_string()))?;
    if report["schema"].as_str() != Some(frozen::CHILD_REPORT_SCHEMA) {
        return Err(ReportError::Schema(format!("{:?}", report["schema"])));
    }
    for (key, want) in [
        ("contract_sha256", frozen::CONTRACT_SHA256),
        ("manifest_sha256", frozen::MANIFEST_SHA256),
        ("generator_sha256", frozen::GENERATOR_SHA256),
    ] {
        if report[key].as_str() != Some(want) {
            return Err(ReportError::HashEcho(format!("{key} = {:?}", report[key])));
        }
    }
    if report["completed"].as_bool() != Some(true) {
        return Err(ReportError::Incomplete("completed != true".into()));
    }
    // Cleanup failures are preserved by the child and fail qualification
    // after teardown (contract error_handling.status_calls).
    let cleanup = &report["cleanup"];
    let errors = cleanup["errors"]
        .as_array()
        .ok_or_else(|| ReportError::Schema("cleanup.errors".into()))?;
    if !errors.is_empty() {
        return Err(ReportError::Cleanup(
            errors.iter().map(|e| e.to_string()).collect(),
        ));
    }
    let rh = &cleanup["result_handles"];
    if rh["balanced"].as_bool() != Some(true) {
        return Err(ReportError::HandleCensus(format!("result handles {rh}")));
    }
    let h = &report["handles"];
    if h["live_array_handles_after_context_drop"].as_u64() != Some(0)
        || h["live_arrays_in_context_at_drop"].as_i64() != Some(0)
        || h["double_free_attempts"].as_u64() != Some(0)
    {
        return Err(ReportError::HandleCensus(format!("handles {h}")));
    }
    if !report["test_fault"].is_null() {
        return Err(ReportError::TestFault(report["test_fault"].to_string()));
    }
    let cases = report["cases"]
        .as_array()
        .ok_or_else(|| ReportError::Schema("cases".into()))?;
    let mut counts: BTreeMap<String, usize> = BTreeMap::new();
    for c in cases {
        let id = c["id"]
            .as_str()
            .ok_or_else(|| ReportError::Schema("case id".into()))?;
        *counts.entry(id.to_string()).or_default() += 1;
    }
    let want: BTreeSet<String> = manifest.cases.iter().map(|c| c.id.clone()).collect();
    let got: BTreeSet<String> = counts.keys().cloned().collect();
    let missing: Vec<String> = want.difference(&got).cloned().collect();
    let unexpected: Vec<String> = got.difference(&want).cloned().collect();
    let duplicated: Vec<String> = counts
        .iter()
        .filter(|(_, &n)| n > 1)
        .map(|(k, _)| k.clone())
        .collect();
    if !missing.is_empty() || !unexpected.is_empty() || !duplicated.is_empty() {
        return Err(ReportError::CaseSet {
            missing,
            unexpected,
            duplicated,
        });
    }
    Ok(report)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sh(script: &str, timeout: Duration) -> ChildRun {
        let dir = std::env::temp_dir().join(format!(
            "f020-harness-{}-{}",
            std::process::id(),
            script.len()
        ));
        std::fs::create_dir_all(&dir).unwrap();
        run_child(
            Path::new("/bin/sh"),
            &["-c".into(), script.into()],
            &[],
            timeout,
            &dir,
            "t",
        )
    }

    #[test]
    fn exit_status_and_signal_are_reported() {
        assert_eq!(
            sh("exit 0", Duration::from_secs(30)).outcome,
            ChildOutcome::Exited(0)
        );
        assert_eq!(
            sh("exit 3", Duration::from_secs(30)).outcome,
            ChildOutcome::Exited(3)
        );
        assert_eq!(
            sh("kill -ABRT $$", Duration::from_secs(30)).outcome,
            ChildOutcome::Signaled(libc::SIGABRT)
        );
        assert_eq!(
            sh("kill -SEGV $$", Duration::from_secs(30)).outcome,
            ChildOutcome::Signaled(libc::SIGSEGV)
        );
    }

    #[test]
    fn watchdog_kills_and_reaps_a_hung_child() {
        let run = sh("sleep 600", Duration::from_millis(300));
        match run.outcome {
            ChildOutcome::Timeout {
                elapsed_ms,
                reaped_signal,
            } => {
                assert!(elapsed_ms >= 300);
                assert_eq!(reaped_signal, Some(libc::SIGKILL));
            }
            other => panic!("expected TIMEOUT, got {other:?}"),
        }
        assert!(run.elapsed_ms < 10_000);
    }

    #[test]
    fn environment_is_cleared() {
        std::env::set_var("F020_HARNESS_LEAK_PROBE", "1");
        let run = sh(
            "test -z \"$F020_HARNESS_LEAK_PROBE\" && test -z \"$MLX_ENABLE_TF32\"",
            Duration::from_secs(30),
        );
        assert_eq!(run.outcome, ChildOutcome::Exited(0));
    }

    #[test]
    fn frozen_timeout_is_1800_seconds() {
        assert_eq!(frozen_timeout(), Duration::from_secs(1800));
    }
}
