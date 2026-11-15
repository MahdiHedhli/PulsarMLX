//! CNF-01: the `cnf` binary skeleton, observed as a process from outside.
//!
//! These tests run the built binary (`CARGO_BIN_EXE_cnf`) with fixed arguments and a
//! cleared environment, and check its exit status and both output streams. They start no
//! server, open no socket and need no network.

use std::process::{Command, Output, Stdio};

use console_conformance::process::spawn_locked;

/// The subcommands later packages build, with their owning package, as `cnf help` must
/// list them.
const PLANNED: &[(&str, &str)] = &[
    ("record", "CNF-09"),
    ("diff", "CNF-09"),
    ("matrix", "CNF-09"),
    ("freshness", "CNF-09"),
    ("ledger-check", "CNF-12"),
];

fn cnf(args: &[&str]) -> Output {
    let mut command = Command::new(env!("CARGO_BIN_EXE_cnf"));
    command.args(args).env_clear();
    run(command)
}

/// Runs `command` to its end as `Command::output` does (standard input closed, both
/// output streams captured), but starts it through the harness's spawn lock: the tests of
/// this binary run in parallel, and a child started without the lock can inherit a pipe
/// end of another test's child, which delays that test's end of file.
fn run(mut command: Command) -> Output {
    command
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    match spawn_locked(&mut command).and_then(|child| child.wait_with_output()) {
        Ok(output) => output,
        Err(err) => panic!("cannot run cnf: {err}"),
    }
}

fn text(bytes: &[u8]) -> String {
    String::from_utf8_lossy(bytes).into_owned()
}

#[test]
fn help_succeeds_and_lists_every_planned_subcommand() {
    let out = cnf(&["help"]);
    assert_eq!(out.status.code(), Some(0));
    assert!(out.stderr.is_empty(), "{}", text(&out.stderr));
    let stdout = text(&out.stdout);
    assert!(stdout.starts_with("cnf: conformance runner of PulsarMLX Console"));
    for (name, package) in PLANNED {
        let line = stdout
            .lines()
            .find(|line| line.trim_start().starts_with(&format!("{name} ")))
            .unwrap_or_default();
        assert!(line.ends_with(&format!("({package})")), "{name}: {line:?}");
    }
    assert_eq!(text(&cnf(&["--help"]).stdout), stdout);
    assert_eq!(text(&cnf(&["-h"]).stdout), stdout);
}

#[test]
fn version_prints_the_crate_version() {
    for form in ["--version", "-V", "version"] {
        let out = cnf(&[form]);
        assert_eq!(out.status.code(), Some(0), "{form}");
        assert_eq!(
            text(&out.stdout),
            format!("cnf {}\n", env!("CARGO_PKG_VERSION"))
        );
        assert!(out.stderr.is_empty());
    }
}

#[test]
fn every_planned_subcommand_exits_3_with_class_not_built() {
    for (name, package) in PLANNED {
        let out = cnf(&[name, "--target", "rust"]);
        assert_eq!(out.status.code(), Some(3), "{name}");
        assert!(out.stdout.is_empty(), "{name}");
        let stderr = text(&out.stderr);
        let mut lines = stderr.lines();
        assert_eq!(
            lines.next(),
            Some(format!("cnf: NOT_BUILT: subcommand '{name}' arrives with {package} and is not built yet").as_str())
        );
        let context = lines.next().unwrap_or_default();
        assert!(
            context.starts_with(&format!(
                "cnf: context: cnf {} on ",
                env!("CARGO_PKG_VERSION")
            )),
            "{context}"
        );
        assert!(context.contains(std::env::consts::OS), "{context}");
        assert!(context.contains(std::env::consts::ARCH), "{context}");
        assert_eq!(lines.next(), None);
    }
}

#[test]
fn usage_errors_exit_2_with_class_usage() {
    for (args, first_line) in [
        (&[][..], "cnf: USAGE: no subcommand given"),
        (&["run"][..], "cnf: USAGE: unknown subcommand 'run'"),
        (&["--frozen"][..], "cnf: USAGE: unknown option '--frozen'"),
        (&["help", "run"][..], "cnf: USAGE: unknown subcommand 'run'"),
        (
            &["--version", "x"][..],
            "cnf: USAGE: unexpected argument 'x' after '--version'",
        ),
    ] {
        let out = cnf(args);
        assert_eq!(out.status.code(), Some(2), "{args:?}");
        assert!(out.stdout.is_empty(), "{args:?}");
        let stderr = text(&out.stderr);
        assert_eq!(stderr.lines().next(), Some(first_line), "{args:?}");
        assert!(stderr.contains("cnf: run 'cnf help' for the list of subcommands\n"));
        assert!(stderr.contains("cnf: context: cnf "));
    }
}

#[test]
fn hostile_arguments_are_escaped_cut_and_never_panic() {
    let long = format!("a\u{1b}[31m{}", "z".repeat(500));
    let out = cnf(&[&long]);
    assert_eq!(out.status.code(), Some(2));
    let stderr = text(&out.stderr);
    let first = stderr.lines().next().unwrap_or_default();
    assert!(first.contains("a\\u{1b}[31m"), "{first}");
    assert!(first.ends_with("...'"), "{first}");
    assert!(first.len() < 120, "{first}");
    assert!(!stderr.contains("panicked"));
}

#[test]
fn an_oversized_argument_list_is_refused() {
    let many: Vec<&str> = std::iter::repeat_n("diff", 300).collect();
    let out = cnf(&many);
    assert_eq!(out.status.code(), Some(2));
    let stderr = text(&out.stderr);
    assert!(
        stderr.starts_with("cnf: USAGE: more than 256 arguments given; at most 256 are accepted"),
        "{stderr}"
    );
    assert!(!stderr.contains("257"), "no count is invented: {stderr}");
    assert!(!stderr.contains("300"), "{stderr}");
}

#[cfg(unix)]
#[test]
fn a_non_utf8_argument_is_a_usage_error() {
    use std::ffi::OsStr;
    use std::os::unix::ffi::OsStrExt;
    let mut command = Command::new(env!("CARGO_BIN_EXE_cnf"));
    command.arg(OsStr::from_bytes(b"\xff\xfe")).env_clear();
    let out = run(command);
    assert_eq!(out.status.code(), Some(2));
    assert!(text(&out.stderr).starts_with("cnf: USAGE: argument 1 is not valid UTF-8\n"));
}
