//! ENG-01: the synthetic-only guard of contract section 5.1 (owner decision of
//! 2026-11-14 on OPEN-29, lead decision LD28).
//!
//! These tests pin the refusal. They must not be deleted, weakened, ignored or moved
//! behind a feature to make an engine start that is not synthetic (section 5.1, rule 5;
//! docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md). No donor test exists for this rule.

use console_core::engine::{
    require_synthetic, EngineDescriptor, EngineKind, FailureKind, Provenance, ProvenanceRefused,
    ALLOWING_NON_SYNTHETIC_ENGINES_PATH,
};

const KINDS: [EngineKind; 4] = [
    EngineKind::Scripted,
    EngineKind::LineProtocol,
    EngineKind::CoordinatorAdapter,
    EngineKind::RuntimeAdapter,
];

/// Every shape of "not synthetic" the type can carry: no declaration, and declarations
/// that are empty, real-looking, look-alikes of "synthetic", multi-line, or too long.
fn not_synthetic_values() -> Vec<Provenance> {
    let mut v = vec![Provenance::not_synthetic(None)];
    let long = "x".repeat(500);
    for declared in [
        "",
        "real",
        "native",
        "synthetic ",
        " synthetic",
        "Synthetic",
        "SYNTHETIC",
        "synthetic\nreal",
        "synth",
        "synthetic=1",
        "\u{0}",
        long.as_str(),
    ] {
        v.push(Provenance::not_synthetic(Some(declared)));
    }
    // Even the exact word, when it arrives as a declaration through `not_synthetic`, is
    // not synthetic provenance: only `Provenance::Synthetic` is.
    v.push(Provenance::not_synthetic(Some("synthetic")));
    v
}

fn descriptor(kind: EngineKind, provenance: Provenance) -> EngineDescriptor {
    let mut d = EngineDescriptor::new(kind, provenance);
    d.max_context = 4096;
    d
}

#[test]
fn the_guard_admits_synthetic_provenance_for_every_kind() {
    for kind in KINDS {
        assert_eq!(
            require_synthetic(&descriptor(kind, Provenance::Synthetic)),
            Ok(()),
            "{kind}"
        );
    }
}

#[test]
fn the_guard_refuses_every_provenance_that_is_not_synthetic() {
    for kind in KINDS {
        for provenance in not_synthetic_values() {
            let refused = require_synthetic(&descriptor(kind, provenance.clone()))
                .expect_err("a provenance that is not synthetic must be refused");
            assert_eq!(refused.kind, kind);
            assert_eq!(refused.reported, provenance);
        }
    }
}

#[test]
fn the_guard_refuses_an_engine_that_declares_no_provenance() {
    let refused = require_synthetic(&descriptor(
        EngineKind::LineProtocol,
        Provenance::not_synthetic(None),
    ))
    .expect_err("no declaration fails closed");
    assert_eq!(
        refused.reported,
        Provenance::NotSynthetic { declared: None }
    );
    assert!(refused
        .to_string()
        .contains("not synthetic (no declaration)"));
}

#[test]
fn the_guard_refuses_whatever_else_the_descriptor_says() {
    // Capabilities, facts, `INFO` entries and readiness do not change the answer.
    let mut d = descriptor(
        EngineKind::Scripted,
        Provenance::not_synthetic(Some("real")),
    );
    d.info
        .absorb_fields(["synthetic=1", "provenance=synthetic", "engine=synthetic"]);
    d.caps.apply_info(&d.info);
    d.version = Some("synthetic".into());
    d.facts.model_path = Some("synthetic".into());
    assert!(require_synthetic(&d).is_err());
    d.max_context = 0;
    assert!(require_synthetic(&d).is_err());
}

/// The guard's source file, read at compile time.
const GUARD_SRC: &str = include_str!("../src/engine/guard.rs");

/// The guard's code lines, with comment lines left out.
fn guard_code_lines() -> Vec<&'static str> {
    GUARD_SRC
        .lines()
        .filter(|l| !l.trim_start().starts_with("//"))
        .collect()
}

#[test]
fn the_guard_source_has_no_bypass() {
    // A source-level pin: the guard reads nothing but the descriptor. Any environment
    // read, conditional compilation, feature switch or configuration lookup added to the
    // guard file fails this test, whatever name it uses.
    let code = guard_code_lines().join("\n");
    for forbidden in [
        "env::",
        "env!(",
        "option_env!",
        "cfg(",
        "cfg!(",
        "var(",
        "var_os(",
        "feature",
        "std::fs",
        "static mut",
        "AtomicBool",
        "OnceLock",
        "thread_local",
    ] {
        assert!(
            !code.contains(forbidden),
            "the guard source contains {forbidden:?}"
        );
    }
    // `require_synthetic` admits on exactly one arm, the one for `Provenance::Synthetic`.
    let admitting: Vec<&str> = guard_code_lines()
        .into_iter()
        .filter(|l| l.contains("Ok(())"))
        .map(str::trim)
        .collect();
    assert_eq!(admitting, vec!["Provenance::Synthetic => Ok(()),"]);
    assert_eq!(code.matches("pub fn require_synthetic(").count(), 1);
    assert_eq!(code.matches("match &d.provenance").count(), 1);
}

/// The three required parts of the refusal line (section 5.1, rule 3): the engine kind,
/// what the engine reported, and the path of the note on allowing non-synthetic engines;
/// and it is one line.
fn assert_refusal_line(refused: &ProvenanceRefused) {
    let line = refused.to_string();
    assert!(
        !line.contains('\n') && !line.contains('\r'),
        "one line: {line:?}"
    );
    assert!(
        line.contains(&format!("engine {} ", refused.kind.as_str())),
        "names the kind: {line}"
    );
    assert!(
        line.contains(&format!("reports provenance {}", refused.reported)),
        "names what was reported: {line}"
    );
    assert!(
        line.contains(ALLOWING_NON_SYNTHETIC_ENGINES_PATH),
        "names the note: {line}"
    );
    assert!(line.starts_with("[console] refusing to start: "), "{line}");
}

#[test]
fn the_refusal_line_names_kind_report_and_note() {
    assert_eq!(
        ALLOWING_NON_SYNTHETIC_ENGINES_PATH,
        "docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md"
    );
    for kind in KINDS {
        for provenance in not_synthetic_values() {
            let refused = require_synthetic(&descriptor(kind, provenance)).expect_err("refused");
            assert_refusal_line(&refused);
        }
    }
}

#[test]
fn the_refusal_line_text() {
    let refused = require_synthetic(&descriptor(
        EngineKind::LineProtocol,
        Provenance::not_synthetic(Some("real")),
    ))
    .expect_err("refused");
    assert_eq!(
        refused.to_string(),
        "[console] refusing to start: engine line-protocol reports provenance not synthetic \
         (declared \"real\"); this build serves synthetic engines only. See \
         docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md"
    );
}

#[test]
fn a_refusal_at_restart_is_a_poisoned_start_failure_with_the_same_line() {
    let refused = require_synthetic(&descriptor(
        EngineKind::Scripted,
        Provenance::not_synthetic(None),
    ))
    .expect_err("refused");
    let failure = refused.to_failure();
    assert_eq!(failure.kind, FailureKind::StartFailed);
    assert!(failure.poisoned);
    assert_eq!(failure.after_tokens, 0);
    assert_eq!(failure.to_string(), refused.to_string());
}
