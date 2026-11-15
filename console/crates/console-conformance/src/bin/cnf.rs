//! `cnf`, the conformance runner of PulsarMLX Console. Owned by CNF-01.
//!
//! This is the skeleton of the binary. It parses its arguments by hand (no argument
//! parsing crate), answers `help` and `version`, and declares the subcommands that later
//! conformance packages build. Each declared subcommand answers that it is not built yet
//! and exits with [`EXIT_NOT_BUILT`], so no script can mistake a missing runner for a
//! passing one. Nothing here runs a scenario, a server or an engine, and nothing here
//! makes a parity claim.
//!
//! Exit statuses:
//!
//! - `0`: help or version was printed.
//! - `2` ([`EXIT_USAGE`]): the arguments were not understood (class `USAGE`).
//! - `3` ([`EXIT_NOT_BUILT`]): a declared subcommand that is not built yet (class
//!   `NOT_BUILT`).
//!
//! Every failure line on standard error has the form `cnf: <CLASS>: <detail>`, followed by
//! one context line naming the binary version, operating system and architecture, so a
//! failure in CI is classified without reading the source.

use std::ffi::OsString;
use std::io::Write;
use std::process::ExitCode;

/// Exit status for arguments that were not understood.
const EXIT_USAGE: u8 = 2;

/// Exit status for a declared subcommand whose package has not landed yet.
const EXIT_NOT_BUILT: u8 = 3;

/// At most this many arguments are read. More is a usage error, so the work done per
/// invocation is bounded by a constant, not by the caller.
const MAX_ARGS: usize = 256;

/// At most this many characters of an argument are echoed back in an error message.
const MAX_ECHO_CHARS: usize = 64;

/// A subcommand that a later conformance package builds. Until then it is declared here
/// so that its name is reserved and asking for it fails with a named class.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct PlannedSubcommand {
    /// The subcommand as typed after `cnf`.
    name: &'static str,
    /// The work package of `specs/022-console-serving-parity/tasks.md` that builds it.
    package: &'static str,
    /// One line on what it will do.
    summary: &'static str,
}

/// The subcommands that later packages build, in the order `help` lists them. The names
/// come from the detail file `specs/022-console-serving-parity/tasks/conformance.md`
/// (CNF-09 and CNF-12).
const PLANNED: &[PlannedSubcommand] = &[
    PlannedSubcommand {
        name: "record",
        package: "CNF-09",
        summary: "record normalized observations of a target for every scenario",
    },
    PlannedSubcommand {
        name: "diff",
        package: "CNF-09",
        summary: "run two targets over the scenario corpus and report differences",
    },
    PlannedSubcommand {
        name: "matrix",
        package: "CNF-09",
        summary: "run line-protocol scenarios across servers and fake engines",
    },
    PlannedSubcommand {
        name: "freshness",
        package: "CNF-09",
        summary: "re-record the reference side and require byte-identical goldens",
    },
    PlannedSubcommand {
        name: "ledger-check",
        package: "CNF-12",
        summary: "resolve every parity ledger row and fail on dangling or missing rows",
    },
];

/// What one invocation decided: the exit status and the text for each stream.
#[derive(Debug, Clone, PartialEq, Eq)]
struct Outcome {
    status: u8,
    stdout: String,
    stderr: String,
}

impl Outcome {
    fn success(stdout: String) -> Self {
        Self {
            status: 0,
            stdout,
            stderr: String::new(),
        }
    }

    fn failure(status: u8, class: &str, detail: &str, hint: Option<&str>) -> Self {
        let mut stderr = format!("cnf: {class}: {detail}\n");
        if let Some(hint) = hint {
            stderr.push_str("cnf: ");
            stderr.push_str(hint);
            stderr.push('\n');
        }
        stderr.push_str(&context_line());
        Self {
            status,
            stdout: String::new(),
            stderr,
        }
    }
}

/// The context line printed after every failure.
fn context_line() -> String {
    format!(
        "cnf: context: cnf {} on {} {}\n",
        env!("CARGO_PKG_VERSION"),
        std::env::consts::OS,
        std::env::consts::ARCH
    )
}

/// The text of `cnf help`.
fn usage_text() -> String {
    let mut text = String::from(
        "cnf: conformance runner of PulsarMLX Console (skeleton; qualified on synthetic \
         backends only once built)\n\
         \n\
         Usage:\n  \
         cnf <subcommand> [arguments]\n  \
         cnf help [subcommand]\n  \
         cnf --version\n\
         \n\
         Subcommands, none of them built yet (each exits with status 3, class NOT_BUILT):\n",
    );
    let width = PLANNED.iter().map(|p| p.name.len()).max().unwrap_or(0);
    for planned in PLANNED {
        text.push_str(&format!(
            "  {:<width$}  {} ({})\n",
            planned.name, planned.summary, planned.package
        ));
    }
    text.push_str(
        "\nExit status: 0 for help and version, 2 for a usage error (class USAGE), \
         3 for a subcommand that is not built yet (class NOT_BUILT).\n",
    );
    text
}

/// Makes an argument safe to echo: control and non-printing characters are escaped and
/// the text is cut to [`MAX_ECHO_CHARS`] characters.
fn echo_arg(arg: &str) -> String {
    let mut out = String::new();
    let mut chars = arg.chars();
    for ch in chars.by_ref().take(MAX_ECHO_CHARS) {
        out.extend(ch.escape_debug());
    }
    if chars.next().is_some() {
        out.push_str("...");
    }
    out
}

fn find_planned(name: &str) -> Option<&'static PlannedSubcommand> {
    PLANNED.iter().find(|p| p.name == name)
}

fn not_built(planned: &PlannedSubcommand) -> Outcome {
    Outcome::failure(
        EXIT_NOT_BUILT,
        "NOT_BUILT",
        &format!(
            "subcommand '{}' arrives with {} and is not built yet",
            planned.name, planned.package
        ),
        None,
    )
}

fn usage_error(detail: &str) -> Outcome {
    Outcome::failure(
        EXIT_USAGE,
        "USAGE",
        detail,
        Some("run 'cnf help' for the list of subcommands"),
    )
}

/// Decides what one invocation does. `args` excludes the program name.
fn run(args: &[OsString]) -> Outcome {
    if args.len() > MAX_ARGS {
        // main() stops reading at MAX_ARGS + 1, so the real count is unknown here.
        return usage_error(&format!(
            "more than {MAX_ARGS} arguments given; at most {MAX_ARGS} are accepted"
        ));
    }
    let mut text_args: Vec<&str> = Vec::with_capacity(args.len());
    for (index, arg) in args.iter().enumerate() {
        match arg.to_str() {
            Some(text) => text_args.push(text),
            None => {
                return usage_error(&format!(
                    "argument {} is not valid UTF-8",
                    index.saturating_add(1)
                ))
            }
        }
    }
    let Some((&first, rest)) = text_args.split_first() else {
        return usage_error("no subcommand given");
    };
    match first {
        "help" | "-h" | "--help" => help(rest),
        "version" | "-V" | "--version" => {
            if let Some(extra) = rest.first() {
                return usage_error(&format!(
                    "unexpected argument '{}' after '{first}'",
                    echo_arg(extra)
                ));
            }
            Outcome::success(format!("cnf {}\n", env!("CARGO_PKG_VERSION")))
        }
        name => match find_planned(name) {
            // The arguments of a planned subcommand are its owning package's to define;
            // until it lands, every form of it answers NOT_BUILT.
            Some(planned) => not_built(planned),
            None if name.starts_with('-') => {
                usage_error(&format!("unknown option '{}'", echo_arg(name)))
            }
            None => usage_error(&format!("unknown subcommand '{}'", echo_arg(name))),
        },
    }
}

fn help(rest: &[&str]) -> Outcome {
    match rest {
        [] => Outcome::success(usage_text()),
        [name] => match find_planned(name) {
            Some(planned) => Outcome::success(format!(
                "cnf {}: {} ({}; not built yet, exits with status 3, class NOT_BUILT)\n",
                planned.name, planned.summary, planned.package
            )),
            None => usage_error(&format!("unknown subcommand '{}'", echo_arg(name))),
        },
        [_, extra, ..] => usage_error(&format!(
            "unexpected argument '{}' after 'help <subcommand>'",
            echo_arg(extra)
        )),
    }
}

fn main() -> ExitCode {
    // Collect at most one more than the limit, so an oversized argument list is refused
    // without reading all of it.
    let args: Vec<OsString> = std::env::args_os().skip(1).take(MAX_ARGS + 1).collect();
    let outcome = run(&args);
    // A closed stream (for example `cnf help | head -1`) must not turn into a panic.
    let _ = std::io::stdout().write_all(outcome.stdout.as_bytes());
    let _ = std::io::stderr().write_all(outcome.stderr.as_bytes());
    ExitCode::from(outcome.status)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn args(list: &[&str]) -> Vec<OsString> {
        list.iter().map(OsString::from).collect()
    }

    #[test]
    fn no_arguments_is_a_usage_error() {
        let out = run(&[]);
        assert_eq!(out.status, EXIT_USAGE);
        assert!(out.stdout.is_empty());
        assert!(out.stderr.starts_with("cnf: USAGE: no subcommand given\n"));
        assert!(out.stderr.contains("cnf: context: cnf "));
    }

    #[test]
    fn help_forms_print_the_usage_and_succeed() {
        for form in ["help", "-h", "--help"] {
            let out = run(&args(&[form]));
            assert_eq!(out.status, 0, "{form}");
            assert!(out.stderr.is_empty(), "{form}");
            assert_eq!(out.stdout, usage_text(), "{form}");
        }
    }

    #[test]
    fn usage_lists_every_planned_subcommand_with_its_package() {
        let text = usage_text();
        for planned in PLANNED {
            let line = text
                .lines()
                .find(|line| line.trim_start().starts_with(planned.name))
                .unwrap_or_default();
            assert!(line.contains(planned.package), "{}", planned.name);
            assert!(line.contains(planned.summary), "{}", planned.name);
        }
    }

    #[test]
    fn version_forms_print_the_package_version() {
        for form in ["version", "-V", "--version"] {
            let out = run(&args(&[form]));
            assert_eq!(out.status, 0, "{form}");
            assert_eq!(out.stdout, format!("cnf {}\n", env!("CARGO_PKG_VERSION")));
        }
        let out = run(&args(&["--version", "extra"]));
        assert_eq!(out.status, EXIT_USAGE);
        assert!(out
            .stderr
            .starts_with("cnf: USAGE: unexpected argument 'extra'"));
    }

    #[test]
    fn every_planned_subcommand_answers_not_built() {
        for planned in PLANNED {
            for extra in [&[][..], &["--target", "rust"][..]] {
                let mut list = vec![planned.name];
                list.extend_from_slice(extra);
                let out = run(&args(&list));
                assert_eq!(out.status, EXIT_NOT_BUILT, "{}", planned.name);
                assert!(out.stdout.is_empty());
                let expected = format!(
                    "cnf: NOT_BUILT: subcommand '{}' arrives with {} and is not built yet\n",
                    planned.name, planned.package
                );
                assert!(out.stderr.starts_with(&expected), "{}", out.stderr);
            }
        }
    }

    #[test]
    fn help_for_one_subcommand() {
        let out = run(&args(&["help", "ledger-check"]));
        assert_eq!(out.status, 0);
        assert!(out.stdout.starts_with("cnf ledger-check: "));
        assert!(out.stdout.contains("CNF-12"));
        let out = run(&args(&["help", "nope"]));
        assert_eq!(out.status, EXIT_USAGE);
        let out = run(&args(&["help", "diff", "more"]));
        assert_eq!(out.status, EXIT_USAGE);
        assert!(out.stderr.contains("unexpected argument 'more'"));
    }

    #[test]
    fn unknown_subcommand_and_option_are_usage_errors() {
        let out = run(&args(&["serve"]));
        assert_eq!(out.status, EXIT_USAGE);
        assert!(out
            .stderr
            .starts_with("cnf: USAGE: unknown subcommand 'serve'\n"));
        let out = run(&args(&["--frobnicate"]));
        assert_eq!(out.status, EXIT_USAGE);
        assert!(out
            .stderr
            .starts_with("cnf: USAGE: unknown option '--frobnicate'\n"));
    }

    #[test]
    fn echoed_arguments_are_escaped_and_cut() {
        assert_eq!(echo_arg("a\nb\u{7}"), "a\\nb\\u{7}");
        let long = "x".repeat(MAX_ECHO_CHARS + 10);
        let echoed = echo_arg(&long);
        assert_eq!(echoed, format!("{}...", "x".repeat(MAX_ECHO_CHARS)));
        let exact = "y".repeat(MAX_ECHO_CHARS);
        assert_eq!(echo_arg(&exact), exact);
        // Multi-byte characters are counted as characters, never split.
        let wide = "\u{e9}".repeat(MAX_ECHO_CHARS + 1);
        assert_eq!(
            echo_arg(&wide),
            format!("{}...", "\u{e9}".repeat(MAX_ECHO_CHARS))
        );
    }

    #[test]
    fn too_many_arguments_is_a_usage_error() {
        let list: Vec<OsString> = (0..=MAX_ARGS).map(|_| OsString::from("diff")).collect();
        let out = run(&list);
        assert_eq!(out.status, EXIT_USAGE);
        assert!(out.stderr.contains("more than 256 arguments given"));
        assert!(out.stderr.contains("at most 256 are accepted"));
        let list: Vec<OsString> = (0..MAX_ARGS).map(|_| OsString::from("diff")).collect();
        assert_eq!(run(&list).status, EXIT_NOT_BUILT);
    }

    #[cfg(unix)]
    #[test]
    fn non_utf8_argument_is_a_usage_error() {
        use std::os::unix::ffi::OsStringExt;
        let out = run(&[OsString::from("diff"), OsString::from_vec(vec![0xff, 0xfe])]);
        assert_eq!(out.status, EXIT_USAGE);
        assert!(out
            .stderr
            .starts_with("cnf: USAGE: argument 2 is not valid UTF-8\n"));
    }

    #[test]
    fn planned_names_are_unique_and_not_reserved_words() {
        for (i, a) in PLANNED.iter().enumerate() {
            assert!(!["help", "version"].contains(&a.name));
            assert!(!a.name.starts_with('-'));
            for b in PLANNED.iter().skip(i + 1) {
                assert_ne!(a.name, b.name);
            }
        }
    }
}
