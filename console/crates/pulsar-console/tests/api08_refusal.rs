//! The synthetic-only rule at process start (contracts/backend-seam.md section 5.1, rule
//! 3; owner decision of 2026-11-14 on OPEN-29, lead decision LD28): an engine that does
//! not report synthetic provenance makes `pulsar-console` exit with a non-zero status
//! after one line on standard error that names the engine kind, what the engine reported
//! and `docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md`, having served nothing.
//!
//! The shipped binary cannot select such an engine: its `main` names only the scripted
//! engine's factory, and the test engine `NotSyntheticEngine` exists only behind the
//! `test-support` feature of `console-engine`, which only tests enable. So this test runs
//! the entry function `pulsar_console::run` in a child process of its own test executable
//! (the `refusal_child` test, which does nothing unless the parent sets its variable),
//! with that engine handed in as the factory. These tests pin the refusal and are not to
//! be deleted or weakened to make an engine start (seam contract section 5.1, rule 5).

use std::ffi::OsString;
use std::io::Read;
use std::process::{Command, ExitStatus, Stdio};
use std::sync::Arc;
use std::time::{Duration, Instant};

use console_engine::fake::doubles::NotSyntheticEngine;
use console_testkit::process::free_port;

/// Set by the parent test to the child mode: `declared` or `undeclared`.
const CHILD: &str = "API08_REFUSAL_CHILD";

/// The port the child is told to use.
const CHILD_PORT: &str = "API08_REFUSAL_PORT";

/// A generous bound for the child to end.
const DEADLINE: Duration = Duration::from_secs(20);

/// The child mode: runs the entry function with the engine that is not synthetic, then
/// exits with its status. Without the parent's variable it does nothing.
#[test]
fn refusal_child() {
    let Some(mode) = std::env::var_os(CHILD) else {
        return;
    };
    let port = std::env::var(CHILD_PORT).unwrap_or_else(|_| "0".to_owned());
    let engine = if mode == "undeclared" {
        NotSyntheticEngine::undeclared()
    } else {
        NotSyntheticEngine::declaring("a real model")
    };
    let args: Vec<OsString> = ["pulsar-console", "--port", &port]
        .iter()
        .map(OsString::from)
        .collect();
    let code = pulsar_console::run(args, move |_| Ok(Arc::new(engine)));
    std::process::exit(code);
}

/// Runs this test executable's `refusal_child` in `mode`; returns its status and streams.
fn child(mode: &str, port: u16) -> (ExitStatus, String, String) {
    let exe = match std::env::current_exe() {
        Ok(p) => p,
        Err(e) => panic!("current_exe: {e}"),
    };
    let mut c = Command::new(exe);
    c.args([
        "refusal_child",
        "--exact",
        "--nocapture",
        "--test-threads=1",
    ])
    .env_clear()
    .env(CHILD, mode)
    .env(CHILD_PORT, port.to_string())
    .stdin(Stdio::null())
    .stdout(Stdio::piped())
    .stderr(Stdio::piped());
    let mut proc = match c.spawn() {
        Ok(p) => p,
        Err(e) => panic!("spawn: {e}"),
    };
    let pump = |pipe: Option<Box<dyn Read + Send>>| {
        std::thread::spawn(move || {
            let mut text = String::new();
            if let Some(mut p) = pipe {
                let _ = p.read_to_string(&mut text);
            }
            text
        })
    };
    let out = pump(
        proc.stdout
            .take()
            .map(|p| Box::new(p) as Box<dyn Read + Send>),
    );
    let err = pump(
        proc.stderr
            .take()
            .map(|p| Box::new(p) as Box<dyn Read + Send>),
    );
    let started = Instant::now();
    let status = loop {
        match proc.try_wait() {
            Ok(Some(s)) => break s,
            Ok(None) if started.elapsed() < DEADLINE => {
                std::thread::sleep(Duration::from_millis(10));
            }
            _ => {
                let _ = proc.kill();
                let _ = proc.wait();
                panic!("the child did not exit within {DEADLINE:?}");
            }
        }
    };
    (
        status,
        out.join().unwrap_or_default(),
        err.join().unwrap_or_default(),
    )
}

fn assert_refused(mode: &str, reported: &str) {
    let port = match free_port() {
        Ok(p) => p,
        Err(e) => panic!("free port: {e}"),
    };
    let (status, stdout, stderr) = child(mode, port);
    assert_eq!(
        status.code(),
        Some(1),
        "stdout {stdout:?} stderr {stderr:?}"
    );
    // Exactly one line on standard error: the guard's.
    assert_eq!(
        stderr,
        format!(
            "[console] refusing to start: engine scripted reports provenance {reported}; this build serves synthetic engines only. See docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md\n"
        )
    );
    assert!(stderr.contains("engine scripted"));
    assert!(stderr.contains("docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md"));
    // Nothing was served: no engine line and no ready line on standard output, and no
    // line about binding the port on standard error. (That nothing accepted connections
    // while the engine was admitted is shown in process, by
    // `api08_start::nothing_listens_while_the_refused_engine_is_admitted`.)
    assert!(!stdout.contains("ready: "), "{stdout}");
    assert!(!stdout.contains("[console] engine:"), "{stdout}");
    assert!(!stderr.contains("could not listen"), "{stderr}");
}

#[test]
fn process_start_refuses_an_engine_that_is_not_synthetic() {
    assert_refused("declared", "not synthetic (declared \"a real model\")");
}

#[test]
fn process_start_refuses_an_engine_that_declares_no_provenance() {
    assert_refused("undeclared", "not synthetic (no declaration)");
}
