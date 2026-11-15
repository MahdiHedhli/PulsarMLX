//! CNF-01: structural checks of `.github/workflows/console.yml`.
//!
//! The workflow can only be observed running on GitHub, so these tests pin the rules of
//! binding decision B12 that can be read from the file itself: the path filter, the
//! permissions, actions pinned by commit SHA, no secrets, no schedule, every Rust job run
//! from `console/` on the pinned toolchain with its version asserted, cargo always locked,
//! the summary job depending on every blocking job, and every failure class named. The
//! file is read as text with a small indentation-based reader for the subset of YAML it
//! uses; no YAML crate is added.

use std::collections::BTreeSet;
use std::path::{Path, PathBuf};

/// The blocking jobs B12 allows in M1 (the web logic job arrives with CNF-15).
const BLOCKING_JOBS: &[&str] = &["preflight", "rust-linux", "rust-macos"];
const RUST_JOBS: &[&str] = &["rust-linux", "rust-macos"];

fn repo_root() -> PathBuf {
    // console/crates/console-conformance -> repository root.
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../../..")
}

fn read(relative: &str) -> String {
    let path = repo_root().join(relative);
    match std::fs::read_to_string(&path) {
        Ok(text) => text,
        Err(err) => panic!("cannot read {}: {err}", path.display()),
    }
}

fn workflow() -> String {
    read(".github/workflows/console.yml")
}

/// Lines with comments and blank lines removed. A `#` starts a comment only at the start
/// of the trimmed line or after a space, outside quotes; good enough for this file, whose
/// shell code is checked separately on the raw text.
fn lines(text: &str) -> Vec<&str> {
    text.lines()
        .filter(|line| {
            let trimmed = line.trim_start();
            !trimmed.is_empty() && !trimmed.starts_with('#')
        })
        .collect()
}

fn indent(line: &str) -> usize {
    line.len() - line.trim_start().len()
}

/// The lines of the block under the first line equal to `header` (after trimming) at
/// indentation `level`, up to the next line at that indentation or less.
fn block<'a>(text: &'a str, header: &str, level: usize) -> Vec<&'a str> {
    let all = lines(text);
    let Some(start) = all
        .iter()
        .position(|line| indent(line) == level && line.trim() == header)
    else {
        return Vec::new();
    };
    all.iter()
        .skip(start + 1)
        .take_while(|line| indent(line) > level)
        .copied()
        .collect()
}

/// The jobs, by id, each with the lines of its block.
fn jobs(text: &str) -> Vec<(String, Vec<&str>)> {
    let body = block(text, "jobs:", 0);
    let mut out: Vec<(String, Vec<&str>)> = Vec::new();
    for line in body {
        if indent(line) == 2 {
            let id = line.trim().trim_end_matches(':').to_string();
            out.push((id, Vec::new()));
        } else if let Some((_, job_lines)) = out.last_mut() {
            job_lines.push(line);
        }
    }
    out
}

fn job<'a>(text: &'a str, id: &str) -> Vec<&'a str> {
    jobs(text)
        .into_iter()
        .find(|(job_id, _)| job_id == id)
        .map(|(_, body)| body)
        .unwrap_or_default()
}

fn list_items(block_lines: &[&str]) -> Vec<String> {
    block_lines
        .iter()
        .filter_map(|line| line.trim().strip_prefix("- "))
        .map(|item| item.trim().trim_matches('"').to_string())
        .collect()
}

#[test]
fn triggers_are_path_filtered_push_pull_request_and_manual_dispatch_only() {
    let text = workflow();
    let on = block(&text, "on:", 0);
    let triggers: Vec<&str> = on
        .iter()
        .filter(|line| indent(line) == 2)
        .map(|line| line.trim())
        .collect();
    assert_eq!(
        triggers,
        ["push:", "pull_request:", "workflow_dispatch:"],
        "only push, pull_request and workflow_dispatch may trigger console.yml"
    );
    let push = list_items(&block(&text, "push:", 2));
    let pull = list_items(&block(&text, "pull_request:", 2));
    assert!(!push.is_empty());
    assert_eq!(push, pull, "push and pull_request filter the same paths");
    for required in ["console/**", ".github/workflows/console.yml"] {
        assert!(push.iter().any(|p| p == required), "{required}");
    }
    for forbidden in [
        "schedule:",
        "pull_request_target",
        "workflow_run",
        "branches-ignore",
    ] {
        assert!(!text.contains(forbidden), "{forbidden}");
    }
}

#[test]
fn every_filtered_path_is_inside_the_boundary_allowlist() {
    // The allowlist is read from the boundary script itself, so the two cannot drift.
    let script = read("console/tools/check-boundary.sh");
    let mut allowed: Vec<String> = Vec::new();
    let mut inside = false;
    for line in script.lines() {
        if line.starts_with("ALLOW_PREFIXES='") || line.starts_with("ALLOW_EXACT='") {
            inside = true;
        }
        if inside {
            let entry = line
                .trim_start_matches("ALLOW_PREFIXES='")
                .trim_start_matches("ALLOW_EXACT='");
            let done = entry.ends_with('\'');
            let entry = entry.trim_end_matches('\'');
            if !entry.is_empty() {
                allowed.push(entry.to_string());
            }
            if done {
                inside = false;
            }
        }
    }
    assert!(allowed.iter().any(|a| a == "console/"), "{allowed:?}");
    let text = workflow();
    for path in list_items(&block(&text, "push:", 2)) {
        let ok = match path.strip_suffix("**") {
            Some(prefix) => allowed.iter().any(|a| a.ends_with('/') && a == prefix),
            None => allowed.iter().any(|a| a == &path),
        };
        assert!(ok, "{path} is filtered but not in the boundary allowlist");
    }
}

#[test]
fn permissions_are_read_only_and_no_secret_is_used() {
    let text = workflow();
    let perms = block(&text, "permissions:", 0);
    assert_eq!(
        perms.iter().map(|l| l.trim()).collect::<Vec<_>>(),
        ["contents: read"]
    );
    assert!(!text.contains("secrets."), "no secret may be referenced");
    assert!(!text.contains("GITHUB_TOKEN"), "no token may be referenced");
    assert!(!text.contains(": write"), "no write permission");
    assert!(!text.contains("write-all"));
    for line in lines(&text) {
        if line.trim_start().starts_with("permissions:") {
            assert_eq!(indent(line), 0, "no job-level permissions: {line}");
        }
    }
}

#[test]
fn every_action_is_pinned_by_a_full_commit_sha() {
    let text = workflow();
    let mut seen = 0;
    for line in lines(&text) {
        let Some(rest) = line.trim().trim_start_matches("- ").strip_prefix("uses:") else {
            continue;
        };
        seen += 1;
        let spec = rest.split_whitespace().next().unwrap_or_default();
        let (action, sha) = spec.split_once('@').unwrap_or((spec, ""));
        assert_eq!(
            action, "actions/checkout",
            "only actions/checkout is used: {line}"
        );
        assert_eq!(sha.len(), 40, "{line}");
        assert!(
            sha.bytes()
                .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase()),
            "{line}"
        );
        assert!(line.contains("# v"), "the pinned SHA names its tag: {line}");
        assert!(
            sha == "3d3c42e5aac5ba805825da76410c181273ba90b1",
            "the GOV-06 pin of actions/checkout is kept: {line}"
        );
    }
    assert_eq!(seen, 3, "one checkout per job that needs the repository");
    assert_eq!(
        text.matches("persist-credentials: false").count(),
        seen,
        "no checkout keeps credentials"
    );
}

#[test]
fn jobs_are_the_blocking_set_and_the_summary() {
    let text = workflow();
    let ids: Vec<String> = jobs(&text).into_iter().map(|(id, _)| id).collect();
    assert_eq!(ids, ["preflight", "rust-linux", "rust-macos", "summary"]);
    for (id, body) in jobs(&text) {
        let runs_on = body
            .iter()
            .find_map(|l| l.trim().strip_prefix("runs-on: "))
            .unwrap_or_default();
        assert!(
            ["ubuntu-24.04", "macos-15"].contains(&runs_on),
            "{id}: explicit runner label, got {runs_on:?}"
        );
        assert!(
            body.iter()
                .any(|l| l.trim().starts_with("timeout-minutes: ")),
            "{id}: timeout"
        );
        assert!(
            !body.iter().any(|l| l.contains("continue-on-error")),
            "{id}: no step may be allowed to fail"
        );
    }
}

#[test]
fn summary_needs_every_blocking_job_and_requires_success() {
    let text = workflow();
    let summary = job(&text, "summary");
    let needs = summary
        .iter()
        .find_map(|l| l.trim().strip_prefix("needs: "))
        .unwrap_or_default();
    let listed: BTreeSet<&str> = needs
        .trim_matches(|c| c == '[' || c == ']')
        .split(',')
        .map(str::trim)
        .collect();
    let expected: BTreeSet<&str> = BLOCKING_JOBS.iter().copied().collect();
    assert_eq!(listed, expected);
    assert!(summary.iter().any(|l| l.trim() == "if: always()"));
    for id in BLOCKING_JOBS {
        assert!(
            summary
                .iter()
                .any(|l| l.contains(&format!("${{{{ needs.{id}.result }}}}"))),
            "{id}: its result is read"
        );
    }
    assert!(summary.iter().any(|l| l.contains("!= success")));
    for id in RUST_JOBS {
        let body = job(&text, id);
        assert!(
            body.iter().any(|l| l.trim() == "needs: preflight"),
            "{id} waits for preflight"
        );
    }
}

#[test]
fn rust_jobs_run_from_console_on_the_pinned_toolchain() {
    let text = workflow();
    let pin_file = read("console/rust-toolchain.toml");
    let pinned = pin_file
        .lines()
        .find_map(|l| l.trim().strip_prefix("channel = "))
        .map(|v| v.trim_matches('"'))
        .unwrap_or_default();
    assert!(!pinned.is_empty());
    assert!(
        text.contains(&format!("CONSOLE_RUST_TOOLCHAIN: \"{pinned}\"")),
        "console.yml expects the version rust-toolchain.toml pins ({pinned})"
    );
    for id in RUST_JOBS {
        let body = job(&text, id);
        assert!(
            body.iter()
                .any(|l| l.trim() == "working-directory: console"),
            "{id}"
        );
        let joined = body.join("\n");
        let install = joined.find("rustup toolchain install \"${CONSOLE_RUST_TOOLCHAIN}\"");
        let assert_at = joined.find("console_assert_toolchain \"${CONSOLE_RUST_TOOLCHAIN}\"");
        let probe = joined.find("console_probe_mismatch tools/check-toolchain.sh");
        let first_cargo = joined.find("cargo fetch --locked");
        assert!(install.is_some(), "{id}: installs the pin");
        assert!(
            assert_at.is_some() && probe.is_some() && first_cargo.is_some(),
            "{id}"
        );
        assert!(install < assert_at, "{id}: asserts after installing");
        assert!(
            assert_at < probe,
            "{id}: probes the mismatch after asserting"
        );
        assert!(probe < first_cargo, "{id}: no cargo before the assertion");
        assert!(joined.contains("bash tools/check-toolchain.sh"), "{id}");
        assert!(joined.contains("cargo test --frozen"), "{id}");
    }
    assert!(job(&text, "rust-macos")
        .join("\n")
        .contains("\"$(uname -m)\" != arm64"));
    let linux = job(&text, "rust-linux").join("\n");
    assert!(linux.contains("cargo fmt --check"));
    assert!(linux.contains("cargo clippy --frozen --all-targets -- -D warnings"));
}

#[test]
fn every_cargo_command_is_locked_or_frozen() {
    let text = workflow();
    let mut cargo_lines = 0;
    for line in lines(&text) {
        let trimmed = line.trim();
        if trimmed.starts_with("cargo ") && !trimmed.starts_with("cargo fmt ") {
            cargo_lines += 1;
            assert!(
                trimmed.contains("--locked") || trimmed.contains("--frozen"),
                "{trimmed}"
            );
        }
    }
    assert!(cargo_lines >= 5, "fetch, clippy and test lines were found");
    // The header comment recalls the archived workflow's --manifest-path; code may not
    // use it.
    let code = lines(&text).join("\n");
    assert!(
        !code.contains("RUSTUP_AUTO_INSTALL=0 rustup"),
        "never blocks the pinned install"
    );
    assert!(
        !code.contains("--manifest-path"),
        "cargo runs from console/"
    );
}

#[test]
fn preflight_runs_both_check_tools_in_committed_mode_and_checks_the_pin() {
    let text = workflow();
    let preflight = job(&text, "preflight").join("\n");
    assert!(preflight.contains("fetch-depth: 0"));
    let body = job(&text, "preflight");
    assert!(
        body.iter()
            .any(|l| l.trim() == "working-directory: console"),
        "preflight runs from console/ like the Rust jobs"
    );
    assert!(preflight.contains("bash tools/check-boundary.sh --base \"$CONSOLE_BASE\" --committed"));
    assert!(preflight.contains("bash tools/check-hygiene.sh --base \"$CONSOLE_BASE\" --committed"));
    assert!(preflight.contains("console_classify BOUNDARY"));
    assert!(preflight.contains("console_classify HYGIENE"));
    assert!(preflight.contains("console_check_pin"));
    assert!(
        !preflight.contains("rustup"),
        "preflight installs no toolchain"
    );
    assert!(!preflight.contains("cargo "), "preflight builds nothing");
}

#[test]
fn every_run_step_loads_the_failure_reporting_and_names_its_classes() {
    let text = workflow();
    let code = lines(&text).join("\n");
    let runs = code.matches("run: |").count();
    let loads = code.matches("eval \"$CONSOLE_CI_LIB\"").count();
    assert!(runs > 0);
    assert_eq!(runs, loads, "every run step loads CONSOLE_CI_LIB first");
    let header: String = text
        .lines()
        .take_while(|line| !line.starts_with("on:"))
        .filter(|line| line.starts_with('#'))
        .collect::<Vec<_>>()
        .join("\n");
    // Every class passed to console_fail or console_classify is upper snake case.
    let mut classes = BTreeSet::new();
    for line in text.lines() {
        for marker in ["console_fail ", "console_classify "] {
            let Some(index) = line.find(marker) else {
                continue;
            };
            let rest = &line[index + marker.len()..];
            let class = rest.split_whitespace().next().unwrap_or_default();
            if class.starts_with('"') || class.starts_with('(') {
                continue; // a computed class list or the function definition
            }
            assert!(
                !class.is_empty()
                    && class
                        .bytes()
                        .all(|b| b.is_ascii_uppercase() || b.is_ascii_digit() || b == b'_'),
                "class {class:?} in: {line}"
            );
            classes.insert(class.to_string());
        }
    }
    for expected in [
        "PREFLIGHT_BASE_UNAVAILABLE",
        "TOOLCHAIN_PIN_NOT_EXACT",
        "TOOLCHAIN_PIN_MISMATCH",
        "BOUNDARY",
        "HYGIENE",
        "TOOLCHAIN_INSTALL_FAILED",
        "TOOLCHAIN_MISSING",
        "TOOLCHAIN_MISMATCH",
        "TOOLCHAIN_PROBE_ACCEPTED",
        "TOOLCHAIN_PROBE_UNCLASSIFIED",
        "ARCH_MISMATCH",
        "CARGO_FETCH_FAILED",
        "CARGO_FMT",
        "CARGO_CLIPPY",
        "CARGO_TEST",
    ] {
        assert!(classes.contains(expected), "{expected} is raised somewhere");
        assert!(
            header.contains(expected),
            "{expected} is documented in the header"
        );
    }
    // The failure report carries toolchain and image information.
    for needle in [
        "ImageOS",
        "ImageVersion",
        "rustc -V",
        "cargo -V",
        "console failure class: ",
    ] {
        assert!(text.contains(needle), "{needle}");
    }
}

#[test]
fn the_pin_is_checked_by_one_shared_function_in_preflight_and_both_rust_jobs() {
    let text = workflow();
    assert!(text.contains("console_check_pin() {"));
    for id in BLOCKING_JOBS {
        let body = job(&text, id).join("\n");
        assert!(
            body.contains("console_check_pin"),
            "{id} checks the pin with console_check_pin"
        );
    }
    assert!(
        !text.contains("grep -qx \"channel"),
        "no job keeps a stricter pin check of its own"
    );
}

#[test]
fn classification_reads_only_unindented_report_lines() {
    let text = workflow();
    assert!(text.contains("while IFS= read -r line"));
    assert!(text.contains("'FAIL '*)"));
    assert!(text.contains("^[a-z][a-z0-9-]*$"));
    assert!(!text.contains("read -r tag name rest"));
}

// ---------------------------------------------------------------------------------------
// The failure-reporting library run for real: CONSOLE_CI_LIB is extracted from the YAML
// and executed with bash, the shell every console.yml step uses.

/// The body of the `CONSOLE_CI_LIB: |` block scalar, dedented.
fn ci_lib() -> String {
    let text = workflow();
    let mut out = String::new();
    let mut inside = false;
    for line in text.lines() {
        if !inside {
            inside = line == "  CONSOLE_CI_LIB: |";
            continue;
        }
        if !line.trim().is_empty() && indent(line) < 4 {
            break;
        }
        out.push_str(line.get(4..).unwrap_or(""));
        out.push('\n');
    }
    assert!(
        out.contains("console_classify()"),
        "CONSOLE_CI_LIB was found"
    );
    out
}

struct Scratch(PathBuf);

impl Scratch {
    fn new(name: &str) -> Scratch {
        let dir = std::env::temp_dir().join(format!("cnf01-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).expect("scratch directory");
        Scratch(dir)
    }
}

impl Drop for Scratch {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}

/// Runs `call` after loading the library, in `dir`, and returns (status, stdout).
///
/// The child runs as `Command::output` runs it (standard input closed, both output
/// streams captured), but starts through the harness's spawn lock: the tests of this
/// binary run in parallel, and a child started without the lock can inherit a pipe end of
/// another test's child, which delays that test's end of file.
fn run_lib(dir: &Path, call: &str) -> (Option<i32>, String) {
    let script = format!("{}\n{call}\n", ci_lib());
    let mut command = std::process::Command::new("bash");
    command
        .arg("-c")
        .arg(script)
        .current_dir(dir)
        .env("CONSOLE_RUST_TOOLCHAIN", "1.97.1")
        .env("RUSTUP_AUTO_INSTALL", "0")
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped());
    let out = console_conformance::process::spawn_locked(&mut command)
        .and_then(|child| child.wait_with_output())
        .expect("bash runs");
    (
        out.status.code(),
        String::from_utf8_lossy(&out.stdout).into_owned(),
    )
}

fn classes(stdout: &str) -> Vec<&str> {
    stdout
        .lines()
        .filter_map(|l| l.strip_prefix("console failure class: "))
        .collect()
}

fn classify(name: &str, report: &str) -> (Option<i32>, String) {
    let scratch = Scratch::new(name);
    std::fs::write(scratch.0.join("report.out"), report).expect("report");
    run_lib(&scratch.0, "console_classify BOUNDARY 1 report.out repro")
}

#[test]
fn indented_detail_lines_never_add_a_class() {
    let report = concat!(
        "FAIL allowlist       2 path(s)\n",
        "       FAIL weird\n",
        "       FAIL x::warning%20file=forged\n",
        "       FAIL frozen-blobs\n",
        "FAIL ignored-files   1 path(s)\n",
        "       console/x.log\n",
        "FAIL allowlist       repeated\n",
        "ok   frozen-blobs    unchanged",
    );
    let (status, stdout) = classify("indented", report);
    assert_eq!(status, Some(1), "{stdout}");
    assert_eq!(
        classes(&stdout),
        ["BOUNDARY_ALLOWLIST", "BOUNDARY_IGNORED_FILES"],
        "{stdout}"
    );
    assert_eq!(
        stdout.matches("::error title=console ").count(),
        2,
        "{stdout}"
    );
    for forged in ["WEIRD", "FORGED", "warning", "FROZEN"] {
        assert!(!stdout.contains(forged), "{forged}: {stdout}");
    }
}

#[test]
fn an_unindented_report_line_with_a_strange_check_name_is_a_script_error() {
    let (status, stdout) = classify("strange", "FAIL x::y\nFAIL Upper\nFAIL \n");
    assert_eq!(status, Some(1));
    assert_eq!(classes(&stdout), ["BOUNDARY_SCRIPT_ERROR"], "{stdout}");
    assert!(!stdout.contains("x::y"), "{stdout}");
}

#[test]
fn a_failing_check_without_report_lines_is_a_script_error_and_success_is_silent() {
    let (status, stdout) = classify("none", "something went wrong\n");
    assert_eq!(status, Some(1));
    assert_eq!(classes(&stdout), ["BOUNDARY_SCRIPT_ERROR"], "{stdout}");

    let scratch = Scratch::new("ok");
    std::fs::write(scratch.0.join("report.out"), "FAIL allowlist  1\n").expect("report");
    let (status, stdout) = run_lib(
        &scratch.0,
        "console_classify BOUNDARY 0 report.out repro; echo passed",
    );
    assert_eq!(status, Some(0));
    assert_eq!(stdout.trim(), "passed");
}

#[test]
fn every_failure_class_gets_its_own_line_and_annotation() {
    let scratch = Scratch::new("many");
    let (status, stdout) = run_lib(
        &scratch.0,
        "console_fail 'SUMMARY_PREFLIGHT_FAILURE SUMMARY_RUST_MACOS_CANCELLED' detail repro",
    );
    assert_eq!(status, Some(1));
    assert_eq!(
        classes(&stdout),
        ["SUMMARY_PREFLIGHT_FAILURE", "SUMMARY_RUST_MACOS_CANCELLED"]
    );
    for line in stdout.lines() {
        if let Some(class) = line.strip_prefix("console failure class: ") {
            assert!(
                class
                    .bytes()
                    .all(|b| b.is_ascii_uppercase() || b.is_ascii_digit() || b == b'_'),
                "{line}"
            );
        }
    }
    assert!(stdout.contains("::error title=console SUMMARY_PREFLIGHT_FAILURE::detail"));
    assert!(stdout.contains("::error title=console SUMMARY_RUST_MACOS_CANCELLED::detail"));
    assert_eq!(stdout.matches("  detail:    detail").count(), 1);
    assert_eq!(stdout.matches("  reproduce: repro").count(), 1);
    assert!(stdout.contains("  toolchain: pinned 1.97.1"));
}

fn check_pin(name: &str, toml: &str) -> (Option<i32>, String) {
    let scratch = Scratch::new(name);
    std::fs::write(scratch.0.join("rust-toolchain.toml"), toml).expect("pin file");
    run_lib(&scratch.0, "console_check_pin")
}

#[test]
fn the_shared_pin_check_accepts_the_forms_check_toolchain_accepts_and_names_failures() {
    let (status, stdout) = check_pin(
        "pin-comment",
        "[toolchain]\n  channel = \"1.97.1\"  # pinned\nprofile = \"minimal\"\n",
    );
    assert_eq!(status, Some(0), "{stdout}");
    assert!(stdout.contains("ok: console/rust-toolchain.toml pins exactly 1.97.1"));

    let (status, stdout) = check_pin("pin-exact", "[toolchain]\nchannel = \"1.97.1\"");
    assert_eq!(status, Some(0), "{stdout}");

    let (status, stdout) = check_pin("pin-stable", "[toolchain]\nchannel = \"stable\"\n");
    assert_eq!(status, Some(1));
    assert_eq!(classes(&stdout), ["TOOLCHAIN_PIN_NOT_EXACT"], "{stdout}");

    // The first channel line decides, as in tools/check-toolchain.sh.
    let (status, stdout) = check_pin("pin-first", "channel = \"1.97\"\nchannel = \"1.97.1\"\n");
    assert_eq!(status, Some(1));
    assert_eq!(classes(&stdout), ["TOOLCHAIN_PIN_NOT_EXACT"], "{stdout}");

    let (status, stdout) = check_pin("pin-none", "[toolchain]\nprofile = \"minimal\"\n");
    assert_eq!(status, Some(1));
    assert_eq!(classes(&stdout), ["TOOLCHAIN_PIN_NOT_EXACT"], "{stdout}");

    let (status, stdout) = check_pin("pin-other", "[toolchain]\nchannel = \"1.96.0\"\n");
    assert_eq!(status, Some(1));
    assert_eq!(classes(&stdout), ["TOOLCHAIN_PIN_MISMATCH"], "{stdout}");
}
