//! CNF-07: the process harness, proven with the test-only child `cnf_child`.
//!
//! Every test here starts real processes, so each one holds the lifecycle lock for its
//! whole run and stops what it started, also when it fails (dropping a
//! `ServerProcess` stops it). Processes bind loopback port 0 only. The only waits are the
//! harness's own deadlines, scaled by `PULSAR_CONSOLE_TEST_TIME_SCALE`; a test that
//! waits for a deadline to pass uses a short base deadline.
//!
//! These tests are new (the package owns no donor test method). The harness they prove
//! takes its shape from project-maya serve/test_stop.py:70-145 at 7e68a30f (`Proc`,
//! `gone`, `descendants`).

#![cfg(unix)]

use std::io::Read;
use std::net::TcpStream;
use std::os::unix::process::ExitStatusExt;
use std::time::{Duration, Instant};

use console_conformance::process::table::{self, ProcEntry};
use console_conformance::process::{
    lifecycle_lock, Launch, ProcessError, Ready, ReadyExpect, ServerProcess, StdinMode, TimeScale,
    MAX_TRANSCRIPT_BYTES,
};

const CHILD: &str = env!("CARGO_BIN_EXE_cnf_child");

/// A short base deadline for the tests that must wait one out.
const SHORT: Duration = Duration::from_millis(300);

fn child(args: &[&str]) -> Launch {
    Launch::new(CHILD).arg("serve").args(args.iter().copied())
}

fn start(args: &[&str]) -> (ServerProcess, Ready) {
    match child(args).start() {
        Ok(started) => started,
        Err(e) => panic!("cnf_child did not start: {e}"),
    }
}

/// The error of a start that must fail. A failed start keeps its run directory with both
/// capture files for the CI artifacts; this checks that and then removes it.
fn start_err(launch: Launch) -> ProcessError {
    let err = match launch.start() {
        Ok((p, _)) => panic!("the start should have failed:\n{}", p.transcript()),
        Err(e) => e,
    };
    let dir = err
        .run_dir()
        .unwrap_or_else(|| panic!("no kept run directory in: {err}"))
        .to_path_buf();
    assert!(dir.join("stdout.txt").is_file(), "{}", dir.display());
    assert!(dir.join("stderr.txt").is_file(), "{}", dir.display());
    assert!(err.to_string().contains("run directory kept at"), "{err}");
    std::fs::remove_dir_all(&dir).unwrap();
    err
}

/// The pid `cnf_child` printed for its grandchild.
fn grandchild_pid(p: &ServerProcess) -> u32 {
    p.seen()
        .iter()
        .find_map(|l| l.text.strip_prefix("grandchild pid="))
        .and_then(|n| n.parse().ok())
        .unwrap_or_else(|| panic!("no grandchild line in:\n{}", p.transcript()))
}

/// Whether `pid` still names a running (not zombie) process, by the process table, or
/// by `kill(pid, 0)` where the table cannot be read.
fn running(pid: u32) -> bool {
    match table::snapshot() {
        Ok(t) => t.iter().any(|e| e.pid == pid && !e.zombie),
        Err(_) => {
            let Ok(p) = libc::pid_t::try_from(pid) else {
                return false;
            };
            // SAFETY: kill with signal 0 only checks that the process exists.
            unsafe { libc::kill(p, 0) == 0 }
        }
    }
}

fn entry_of(p: &ServerProcess, pid: u32) -> ProcEntry {
    match p.descendants() {
        Ok(d) => d
            .into_iter()
            .find(|e| e.pid == pid)
            .unwrap_or_else(|| panic!("pid {pid} is not a descendant of {}", p.pid())),
        Err(e) => panic!("cannot read the process table: {e}"),
    }
}

#[test]
fn the_ready_line_names_the_bound_port_and_the_port_answers() {
    let _lock = lifecycle_lock();
    let (mut p, ready) = start(&[]);
    let Ready::Server(line) = &ready else {
        panic!("not the server form: {ready:?}")
    };
    // the harness passed --port 0 and read the port the child bound
    assert_ne!(line.port, 0);
    assert_eq!(line.host, "127.0.0.1");
    assert_eq!(line.context_tokens, 32768);
    assert!(!line.images_on && !line.api_key_required);
    assert_eq!(line.suffix, None);
    assert_eq!(p.ready(), Some(&ready));
    let addr = ready.loopback_addr().unwrap();
    let mut conn = TcpStream::connect(addr).unwrap();
    let mut answer = String::new();
    conn.read_to_string(&mut answer).unwrap();
    assert_eq!(answer, "cnf_child\n");
    // the browser hint follows the ready line
    assert!(
        p.until("in a browser to chat", Duration::from_secs(5)),
        "{}",
        p.transcript()
    );
    let report = p.stop();
    report.check().unwrap();
    assert!(report.table == table::supported());
    // the default SIGTERM disposition ended it
    assert_eq!(report.exit.and_then(|s| s.signal()), Some(libc::SIGTERM));
}

#[test]
fn optional_clauses_and_the_proposed_suffix_are_read() {
    let _lock = lifecycle_lock();
    // PLAN-1 / FR-050 / OPEN-35: the synthetic marker is only proposed; the harness
    // accepts the ready line with it and without it
    let (mut p, ready) = start(&[
        "--context",
        "65536",
        "--images",
        "--api-key-required",
        "--ready-suffix",
        "[synthetic backend]",
    ]);
    let Ready::Server(line) = ready else {
        panic!("not the server form")
    };
    assert_eq!(line.context_tokens, 65536);
    assert!(line.images_on && line.api_key_required);
    assert_eq!(line.suffix.as_deref(), Some("[synthetic backend]"));
    p.stop().check().unwrap();
}

#[test]
fn the_oracle_form_is_accepted_only_when_asked() {
    let _lock = lifecycle_lock();
    let (mut p, ready) = match child(&["--oracle-ready"])
        .expect(ReadyExpect::Oracle)
        .start()
    {
        Ok(s) => s,
        Err(e) => panic!("{e}"),
    };
    assert!(matches!(ready, Ready::Oracle { port } if port != 0));
    p.stop().check().unwrap();

    let err = start_err(child(&["--oracle-ready"]).ready_deadline(SHORT));
    assert!(matches!(err, ProcessError::ReadyTimeout { .. }), "{err}");
    assert!(
        err.transcript().unwrap_or("").contains("CNF-READY port="),
        "{err}"
    );
}

#[test]
fn a_malformed_ready_line_is_an_error_with_the_output() {
    let _lock = lifecycle_lock();
    let err = start_err(child(&["--malformed-ready", "--print-env", "TZ"]));
    match &err {
        ProcessError::MalformedReady {
            line, transcript, ..
        } => {
            assert!(line.starts_with("ready: http://127.0.0.1:"), "{line}");
            // the stdout lines before it, in order (stderr can arrive later: two pipes)
            assert!(
                transcript.starts_with("env TZ=UTC\nready: http://"),
                "{transcript}"
            );
        }
        other => panic!("{other}"),
    }
}

#[test]
fn a_ready_line_with_port_zero_is_refused() {
    let _lock = lifecycle_lock();
    // the donor prints the requested port (serve/server.py:7387 at 7e68a30f); under
    // --port 0 that is 0, which no client can reach
    let err = start_err(child(&["--ready-port-zero"]));
    assert!(matches!(err, ProcessError::ReadyPortZero { .. }), "{err}");
}

#[test]
fn a_ready_line_that_names_a_non_loopback_host_is_refused() {
    let _lock = lifecycle_lock();
    // the donor prints a non-wildcard --host as given (serve/server.py:7385-7387 at
    // 7e68a30f); the harness talks to loopback only (contracts/cli.md section 2.5)
    let err = start_err(child(&["--ready-host", "192.0.2.7"]));
    match &err {
        ProcessError::NotLoopback {
            host, transcript, ..
        } => {
            assert_eq!(host, "192.0.2.7");
            assert!(
                transcript.contains("ready: http://192.0.2.7:"),
                "{transcript}"
            );
        }
        other => panic!("{other}"),
    }
    // `localhost` is loopback
    let (mut p, ready) = start(&["--ready-host", "localhost"]);
    assert!(ready.loopback_addr().unwrap().ip().is_loopback());
    p.stop().check().unwrap();
}

#[test]
fn a_bad_ready_line_just_before_an_exit_is_judged_the_same_way() {
    let _lock = lifecycle_lock();
    // the exit event and the stdout lines come from different threads; whichever comes
    // first, a claimed ready line is judged by the same rules
    for _ in 0..10 {
        let err = start_err(child(&["--malformed-ready", "--exit-after-ready", "0"]));
        assert!(matches!(err, ProcessError::MalformedReady { .. }), "{err}");
        let err = start_err(child(&["--ready-port-zero", "--exit-after-ready", "0"]));
        assert!(matches!(err, ProcessError::ReadyPortZero { .. }), "{err}");
        let err = start_err(child(&[
            "--ready-host",
            "192.0.2.7",
            "--exit-after-ready",
            "0",
        ]));
        assert!(matches!(err, ProcessError::NotLoopback { .. }), "{err}");
    }
}

#[test]
fn closing_stdout_before_the_ready_line_is_reported_at_once() {
    let _lock = lifecycle_lock();
    let base = Duration::from_secs(10);
    let t0 = Instant::now();
    let err =
        start_err(child(&["--close-stdout", "--stderr", "stdout is gone"]).ready_deadline(base));
    match &err {
        ProcessError::ClosedBeforeReady { transcript, .. } => {
            assert!(transcript.contains("stdout is gone"), "{transcript}");
        }
        other => panic!("{other}"),
    }
    let scale = TimeScale::from_env().unwrap();
    assert!(
        t0.elapsed() < scale.apply(base / 2),
        "took {:?}",
        t0.elapsed()
    );
}

#[test]
fn an_exit_before_the_ready_line_reports_status_and_output() {
    let _lock = lifecycle_lock();
    let err = start_err(child(&[
        "--exit-before-ready",
        "3",
        "--stderr",
        "cannot start",
    ]));
    match &err {
        ProcessError::ExitedBeforeReady {
            status, transcript, ..
        } => {
            assert_eq!(status, "exit status: 3");
            assert!(transcript.contains("cannot start"), "{transcript}");
        }
        other => panic!("{other}"),
    }
}

#[test]
fn the_ready_deadline_is_scaled() {
    let _lock = lifecycle_lock();
    let scale = TimeScale::new(2.0).unwrap();
    let t0 = Instant::now();
    let err = start_err(
        child(&["--no-ready"])
            .ready_deadline(Duration::from_millis(150))
            .time_scale(scale),
    );
    match err {
        ProcessError::ReadyTimeout { deadline, .. } => {
            assert_eq!(deadline, Duration::from_millis(300))
        }
        other => panic!("{other}"),
    }
    assert!(t0.elapsed() >= Duration::from_millis(300));
}

#[test]
fn the_environment_is_the_allowlist_and_the_scenario_variables() {
    let _lock = lifecycle_lock();
    let inherited = std::env::vars()
        .map(|(k, _)| k)
        .find(|k| not_allowlisted(k));
    let mut args = vec![
        "--print-cwd",
        "--print-env",
        "HOME",
        "--print-env",
        "TZ",
        "--print-env",
        "LC_ALL",
        "--print-env",
        "LANG",
        "--print-env",
        "TMPDIR",
        "--print-env",
        "XDG_CONFIG_HOME",
        "--print-env",
        "XDG_RUNTIME_DIR",
        "--print-env",
        "PULSAR_CONSOLE_DEBUG",
        "--print-env",
        "FAKE_ENGINE_GATE",
    ];
    if let Some(name) = &inherited {
        args.push("--print-env");
        args.push(name);
    }
    let (mut p, _) = match child(&args)
        .env("PULSAR_CONSOLE_DEBUG", "1")
        .engine_gate("/nonexistent/gate")
        .start()
    {
        Ok(s) => s,
        Err(e) => panic!("{e}"),
    };
    let root = p.workdir().root().to_path_buf();
    let real_root = root.canonicalize().unwrap();
    let text = p.transcript();
    let has = |line: String| assert!(text.lines().any(|l| l == line), "{line:?} not in:\n{text}");
    let home = root.join("home");
    has(format!("env HOME={}", home.display()));
    has("env TZ=UTC".to_string());
    has("env LC_ALL=C.UTF-8".to_string());
    has("env LANG=C.UTF-8".to_string());
    has(format!("env TMPDIR={}", root.join("tmp").display()));
    has(format!(
        "env XDG_CONFIG_HOME={}",
        home.join(".config").display()
    ));
    has(format!(
        "env XDG_RUNTIME_DIR={}",
        root.join("run").display()
    ));
    has("env PULSAR_CONSOLE_DEBUG=1".to_string());
    has("env FAKE_ENGINE_GATE=/nonexistent/gate".to_string());
    has(format!("cwd {}", real_root.join("data").display()));
    if let Some(name) = inherited {
        has(format!("env {name} unset"));
    }
    p.stop().check().unwrap();
}

/// A variable of the test process that the allowlist does not pass on.
fn not_allowlisted(k: &str) -> bool {
    !matches!(k, "PATH" | "HOME" | "TZ" | "LC_ALL" | "LANG" | "TMPDIR")
        && !k.starts_with("XDG_")
        && k.bytes().all(|b| b.is_ascii_uppercase() || b == b'_')
        && !k.is_empty()
}

#[test]
fn a_reserved_variable_is_refused_before_anything_starts() {
    let _lock = lifecycle_lock();
    for name in [
        "LD_PRELOAD",
        "DYLD_INSERT_LIBRARIES",
        "HOME",
        "FAKE_ENGINE_GATE",
    ] {
        let err = child(&[]).env(name, "x").spawn().map(|_| ()).unwrap_err();
        assert!(
            matches!(&err, ProcessError::BadEnv { name: n, .. } if n == name),
            "{err}"
        );
    }
}

#[test]
fn both_streams_are_captured_to_files() {
    let _lock = lifecycle_lock();
    let (mut p, _) = start(&["--stderr", "a line on stderr"]);
    p.stop().check().unwrap();
    let out = std::fs::read_to_string(p.workdir().stdout_path()).unwrap();
    let err = std::fs::read_to_string(p.workdir().stderr_path()).unwrap();
    assert!(
        out.lines().any(|l| l.starts_with("ready: http://")),
        "{out}"
    );
    assert_eq!(err, "a line on stderr\n");
    let root = p.workdir().root().to_path_buf();
    drop(p);
    // a clean run's directory is removed
    assert!(!root.exists());
}

#[test]
fn a_grandchild_in_the_group_ends_with_it() {
    let _lock = lifecycle_lock();
    let (mut p, _) = start(&["--grandchild", "in-group"]);
    let gc = grandchild_pid(&p);
    if table::supported() {
        let e = entry_of(&p, gc);
        assert_eq!(e.pgid, p.pid());
    }
    let report = p.stop();
    report.check().unwrap();
    if report.table {
        assert!(report.tracked.iter().any(|e| e.pid == gc), "{report:?}");
    }
    assert!(!running(gc));
}

#[test]
fn a_grandchild_that_ignores_sigterm_is_reported_and_killed() {
    let _lock = lifecycle_lock();
    let (mut p, _) = match child(&["--grandchild", "in-group", "--grandchild-on-term", "ignore"])
        .grace(SHORT)
        .start()
    {
        Ok(s) => s,
        Err(e) => panic!("{e}"),
    };
    let gc = grandchild_pid(&p);
    let report = p.stop();
    assert!(!report.leader_after_term, "{report:?}");
    assert!(!report.left_behind(), "{report:?}");
    if report.table {
        assert_eq!(report.after_term.len(), 1, "{report:?}");
        assert_eq!(report.after_term[0].entry.pid, gc);
        assert!(report.after_term[0].in_group);
    } else {
        assert!(!report.after_term.is_empty());
    }
    let err = report.check().unwrap_err();
    assert!(
        err.to_string().contains("grace period after SIGTERM"),
        "{err}"
    );
    assert!(!running(gc));
}

#[test]
fn a_grandchild_that_left_the_group_is_found_and_killed() {
    let _lock = lifecycle_lock();
    if !table::supported() {
        // without a process table a process outside the group cannot be seen
        return;
    }
    let (mut p, _) = match child(&["--grandchild", "escape"]).grace(SHORT).start() {
        Ok(s) => s,
        Err(e) => panic!("{e}"),
    };
    let gc = grandchild_pid(&p);
    let e = entry_of(&p, gc);
    assert_ne!(e.pgid, p.pid(), "the grandchild should have its own group");
    let report = p.stop();
    assert!(!report.leader_after_term, "{report:?}");
    assert_eq!(report.after_term.len(), 1, "{report:?}");
    assert_eq!(report.after_term[0].entry.pid, gc);
    assert!(!report.after_term[0].in_group);
    assert!(!report.left_behind(), "{report:?}");
    let err = report.check().unwrap_err();
    assert!(err.to_string().contains("outside the run's group"), "{err}");
    assert!(!running(gc));
}

#[test]
fn a_grandchild_outside_the_group_that_ends_with_its_input_is_clean() {
    let _lock = lifecycle_lock();
    // the shape of a line engine: it ends when its parent's end closes its stdin
    let (mut p, _) = start(&["--grandchild", "escape", "--grandchild-stdin-eof-exits"]);
    let gc = grandchild_pid(&p);
    let report = p.stop();
    report.check().unwrap();
    assert!(!running(gc));
}

#[test]
fn a_process_that_ignores_sigterm_gets_sigkill() {
    let _lock = lifecycle_lock();
    let (mut p, _) = match child(&["--on-term", "ignore"]).grace(SHORT).start() {
        Ok(s) => s,
        Err(e) => panic!("{e}"),
    };
    let report = p.stop();
    assert!(
        report.leader_after_term && !report.leader_after_kill,
        "{report:?}"
    );
    assert_eq!(report.exit.and_then(|s| s.signal()), Some(libc::SIGKILL));
    assert!(report.check().is_err());
}

#[test]
fn a_graceful_exit_on_sigterm_is_clean_with_status_zero() {
    let _lock = lifecycle_lock();
    let (mut p, _) = start(&["--on-term", "exit0", "--grandchild", "in-group"]);
    let report = p.stop();
    report.check().unwrap();
    assert_eq!(report.exit.and_then(|s| s.code()), Some(0));
    // a second stop returns the first report
    assert_eq!(p.stop(), report);
}

#[test]
fn closing_stdin_reaches_the_process() {
    let _lock = lifecycle_lock();
    let (mut p, _) = match child(&["--exit-on-stdin-eof"])
        .stdin(StdinMode::Pipe)
        .start()
    {
        Ok(s) => s,
        Err(e) => panic!("{e}"),
    };
    p.write_stdin(b"ignored\n").unwrap();
    assert_eq!(p.try_exit_status(), None);
    p.close_stdin();
    let status = p.wait_exit(Duration::from_secs(10));
    assert_eq!(status.and_then(|s| s.code()), Some(0));
    assert!(p.rest(Duration::from_secs(5)).contains("stdin closed"));
    p.stop().check().unwrap();
}

#[test]
fn a_signal_to_the_process_alone_and_after_it_was_reaped() {
    let _lock = lifecycle_lock();
    let (mut p, _) = start(&["--grandchild", "in-group"]);
    let gc = grandchild_pid(&p);
    assert!(p.send_signal(libc::SIGTERM).unwrap());
    let status = p.wait_exit(Duration::from_secs(10));
    assert_eq!(status.and_then(|s| s.signal()), Some(libc::SIGTERM));
    // the grandchild got nothing: the signal went to the process alone
    assert!(running(gc));
    // once it has ended, no signal is sent to its pid
    assert!(!p.send_signal(libc::SIGTERM).unwrap());
    // the group's SIGTERM still reaches the grandchild
    let report = p.stop();
    report.check().unwrap();
    assert!(!running(gc));
}

#[test]
fn descendants_and_gone_follow_the_donor_helpers() {
    let _lock = lifecycle_lock();
    if !table::supported() {
        return;
    }
    let (mut p, _) = start(&["--grandchild", "in-group"]);
    let gc = grandchild_pid(&p);
    let tree = p.descendants().unwrap();
    assert_eq!(tree.iter().map(|e| e.pid).collect::<Vec<_>>(), vec![gc]);
    // still running: gone() returns it once its (short) deadline passes
    assert_eq!(p.gone(&tree, Duration::from_millis(50)).unwrap(), tree);
    console_conformance::process::kill_all(&tree);
    assert!(p.gone(&tree, Duration::from_secs(10)).unwrap().is_empty());
    p.stop().check().unwrap();
}

#[test]
fn dropping_a_process_during_a_panic_leaves_nothing_behind() {
    let _lock = lifecycle_lock();
    let mut seen = None;
    let outcome = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        let (p, _) = match child(&["--on-term", "ignore", "--grandchild", "escape"])
            .grace(SHORT)
            .start()
        {
            Ok(s) => s,
            Err(e) => panic!("{e}"),
        };
        seen = Some((
            grandchild_pid(&p),
            p.pid(),
            p.workdir().root().to_path_buf(),
        ));
        // a failing assertion in a test, with the process still running
        panic!("a test failed while its server ran");
    }));
    assert!(outcome.is_err());
    let (gc, pid, root) = seen.expect("the process started");
    assert!(!running(gc), "the grandchild {gc} outlived the drop");
    assert!(!running(pid), "the process {pid} outlived the drop");
    // a failing run keeps its directory for the CI artifacts
    assert!(root.join("stdout.txt").is_file());
    std::fs::remove_dir_all(root).unwrap();
}

#[test]
fn output_kept_in_memory_stays_within_the_budget() {
    let _lock = lifecycle_lock();
    let budget = 64 * 1024;
    let (mut p, _) = match child(&["--spam-after-ready", "2000", "--exit-after-ready", "0"])
        .output_budget(budget)
        .start()
    {
        Ok(s) => s,
        Err(e) => panic!("{e}"),
    };
    assert_eq!(
        p.wait_exit(Duration::from_secs(10)).and_then(|s| s.code()),
        Some(0)
    );
    let transcript = p.rest(Duration::from_secs(10));
    let held: usize = p.seen().iter().map(|l| l.text.len()).sum();
    assert!(held <= budget, "{held} bytes held");
    assert!(
        transcript.contains("more lines in the capture files"),
        "{transcript}"
    );
    assert!(transcript.len() <= MAX_TRANSCRIPT_BYTES + 128);
    // the capture file still has every line
    let captured = std::fs::metadata(p.workdir().stdout_path()).unwrap().len();
    assert!(captured >= 2000 * 100, "{captured}");
    p.stop().check().unwrap();
}

#[test]
fn a_drop_without_stop_fails_on_a_process_that_ignored_sigterm() {
    let _lock = lifecycle_lock();
    let mut seen = None;
    let outcome = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        let (p, _) = match child(&["--grandchild", "in-group", "--grandchild-on-term", "ignore"])
            .grace(SHORT)
            .start()
        {
            Ok(s) => s,
            Err(e) => panic!("{e}"),
        };
        seen = Some((grandchild_pid(&p), p.workdir().root().to_path_buf()));
        // the test relies on the drop to stop the server
        drop(p);
    }));
    let (gc, root) = seen.expect("the process started");
    let message = match outcome {
        Ok(()) => panic!("the drop did not fail on the leak"),
        Err(payload) => payload
            .downcast_ref::<String>()
            .cloned()
            .unwrap_or_default(),
    };
    assert!(message.contains("grace period after SIGTERM"), "{message}");
    assert!(message.contains("run directory kept at"), "{message}");
    assert!(!running(gc), "the grandchild {gc} outlived the drop");
    assert!(root.join("stderr.txt").is_file());
    std::fs::remove_dir_all(root).unwrap();

    // a leader that ignores SIGTERM fails the drop the same way, and still ends
    let mut pid = None;
    let outcome = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        let (p, _) = match child(&["--on-term", "ignore"]).grace(SHORT).start() {
            Ok(s) => s,
            Err(e) => panic!("{e}"),
        };
        pid = Some((p.pid(), p.workdir().root().to_path_buf()));
    }));
    assert!(outcome.is_err(), "the drop did not fail on the leak");
    let (pid, root) = pid.expect("the process started");
    assert!(!running(pid), "the process {pid} outlived the drop");
    std::fs::remove_dir_all(root).unwrap();
}

#[test]
fn a_drop_after_a_judged_stop_does_not_fail_again() {
    let _lock = lifecycle_lock();
    let (mut p, _) = match child(&["--on-term", "ignore"]).grace(SHORT).start() {
        Ok(s) => s,
        Err(e) => panic!("{e}"),
    };
    // the caller took the report and judged it; the drop leaves it at that
    assert!(p.stop().check().is_err());
    let root = p.workdir().root().to_path_buf();
    drop(p);
    assert!(!root.exists());
}

#[test]
fn an_ended_process_stays_unreaped_while_its_handle_lives() {
    let _lock = lifecycle_lock();
    if !table::supported() {
        // without a process table the harness reaps at once
        return;
    }
    let (mut p, _) = start(&["--exit-after-ready", "0"]);
    assert_eq!(
        p.wait_exit(Duration::from_secs(10)).and_then(|s| s.code()),
        Some(0)
    );
    let pid = libc::pid_t::try_from(p.pid()).unwrap();
    // a zombie still holds the pid, and so the run's group id: neither can be reused
    // while the harness signals and inspects the group
    // SAFETY: kill with signal 0 only checks that the process exists.
    assert_eq!(unsafe { libc::kill(pid, 0) }, 0);
    p.stop().check().unwrap();
    drop(p);
    // the drop releases it; the waiter thread reaps it
    let deadline = Instant::now()
        + TimeScale::from_env()
            .unwrap()
            .apply(Duration::from_secs(10));
    // SAFETY: as above.
    while unsafe { libc::kill(pid, 0) } == 0 && Instant::now() < deadline {
        std::thread::sleep(Duration::from_millis(10));
    }
    // SAFETY: as above.
    assert_ne!(
        unsafe { libc::kill(pid, 0) },
        0,
        "pid {pid} was never reaped"
    );
}
