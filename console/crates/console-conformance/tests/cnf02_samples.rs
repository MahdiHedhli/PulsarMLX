//! CNF-02: the sample scenarios transcribed from donor test setups load cleanly.
//!
//! Each file under `tests/data/scenarios/` transcribes the setup of one donor test (its
//! engine, template, server settings and requests) into the scenario format. These tests
//! read them from disk; they start no server, open no socket and need no network.

use std::collections::BTreeSet;
use std::fs;
use std::path::{Path, PathBuf};

use console_conformance::scenario::{
    limits, EngineSpec, Request, Scenario, Substitutions, TemplateRef,
};

fn crate_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
}

fn repo_root() -> PathBuf {
    crate_dir().join("../../..")
}

fn sample_paths() -> Vec<PathBuf> {
    let dir = crate_dir().join("tests/data/scenarios");
    let mut paths: Vec<PathBuf> = fs::read_dir(&dir)
        .unwrap_or_else(|e| panic!("cannot list {}: {e}", dir.display()))
        .map(|entry| entry.expect("directory entry").path())
        .filter(|p| p.extension().is_some_and(|x| x == "json"))
        .collect();
    paths.sort();
    paths
}

fn load(path: &Path) -> Scenario {
    Scenario::from_path(path).unwrap_or_else(|e| panic!("{}: {e}", path.display()))
}

fn ledger_ids() -> BTreeSet<String> {
    let path = repo_root().join("console/parity/ledger.json");
    let text = fs::read_to_string(&path).expect("parity ledger");
    let ledger: serde_json::Value = serde_json::from_str(&text).expect("ledger JSON");
    ledger["rows"]
        .as_array()
        .expect("ledger rows")
        .iter()
        .filter_map(|r| r["id"].as_str().map(str::to_string))
        .collect()
}

#[test]
fn ten_samples_load_cleanly() {
    let paths = sample_paths();
    assert!(paths.len() >= 10, "only {} sample scenarios", paths.len());
    let mut ids = BTreeSet::new();
    for path in &paths {
        let s = load(path);
        assert!(ids.insert(s.id.clone()), "{} twice", s.id);
        assert!(s.description.is_some(), "{}: no description", s.id);
    }
}

#[test]
fn every_sample_names_donor_tests_that_are_ledger_rows() {
    let ledger = ledger_ids();
    let mut donors = BTreeSet::new();
    for path in sample_paths() {
        let s = load(&path);
        assert!(!s.donor.is_empty(), "{}: no donor test named", s.id);
        for d in &s.donor {
            assert!(ledger.contains(d), "{}: {d} is not a ledger row", s.id);
            donors.insert(d.clone());
        }
    }
    assert!(
        donors.len() >= 10,
        "the samples transcribe only {} donor setups",
        donors.len()
    );
}

#[test]
fn samples_cover_both_engine_kinds_and_every_step_kind() {
    let all: Vec<Scenario> = sample_paths().iter().map(|p| load(p)).collect();
    assert!(all.iter().any(|s| matches!(s.engine, EngineSpec::Mock(_))));
    assert!(all.iter().any(|s| matches!(s.engine, EngineSpec::Line(_))));
    assert!(all
        .iter()
        .any(|s| s.steps.iter().any(|st| st.disconnect.is_some())));
    assert!(all
        .iter()
        .any(|s| s.steps.iter().any(|st| st.signal.is_some())));
    assert!(all
        .iter()
        .any(|s| matches!(s.template, TemplateRef::Vendor(_))));
    assert!(all.iter().any(|s| !s.server.config.is_empty()));
    assert!(all.iter().any(|s| !s.server.env.is_empty()));
    assert!(all.iter().any(|s| s.observe.engine_tape));
    assert!(all.iter().any(|s| s.observe.exit));
    // hold, send, release inside one concurrent group, with a gate-only step
    assert!(all.iter().any(|s| s.steps.iter().any(|st| {
        st.concurrent_group.is_some() && st.wait_for_engine_step.is_some() && st.request.is_some()
    }) && s.steps.iter().any(|st| {
        st.concurrent_group.is_some() && st.release_engine_step.is_some() && st.request.is_none()
    })));
}

#[test]
fn queued_sample_holds_sends_and_releases_in_order() {
    let s = load(&crate_dir().join("tests/data/scenarios/queued-request-behind-held-engine.json"));
    let group: Vec<_> = s
        .steps
        .iter()
        .take_while(|st| st.concurrent_group.as_deref() == Some("queue"))
        .collect();
    assert_eq!(group.len(), 3);
    assert!(group[0].request.is_some() && group[0].wait_for_engine_step.is_none());
    assert_eq!(group[1].wait_for_engine_step, Some(0));
    assert!(group[1].request.is_some());
    assert_eq!(group[2].release_engine_step, Some(0));
    assert!(group[2].request.is_none());
    // the group is joined at the next step, outside it
    assert!(s.steps[3].concurrent_group.is_none() && s.steps[3].request.is_some());
}

#[test]
fn samples_expand_with_run_time_values() {
    let subs = Substitutions::new()
        .with_loopback("127.0.0.1")
        .and_then(|s| s.with_tmp("/tmp/cnf02-sample"))
        .and_then(|s| s.with_key_short("k1"))
        .map(|s| s.with_port(40000))
        .expect("substitutions");
    for path in sample_paths() {
        let s = load(&path);
        let e = s
            .expand(&subs)
            .unwrap_or_else(|err| panic!("{}: {err}", s.id));
        assert!(
            !serde_json::to_string(e.source())
                .expect("JSON")
                .contains("{{"),
            "{}: a token survived expansion",
            s.id
        );
    }
}

#[test]
fn cors_sample_keeps_its_origin_as_a_token() {
    let s = load(&crate_dir().join("tests/data/scenarios/cors-preflight-without-setting.json"));
    let Some(Request::Structured(r)) = &s.steps[0].request else {
        panic!("structured request expected")
    };
    assert_eq!(r.method, "OPTIONS");
    assert_eq!(
        r.headers[0],
        ("Origin".into(), "http://{{loopback}}:8090".into())
    );
}

#[test]
fn samples_stay_tiny_and_free_of_host_keys() {
    for path in sample_paths() {
        let text = fs::read_to_string(&path).expect("sample");
        assert!(
            text.len() <= 4096,
            "{}: {} bytes",
            path.display(),
            text.len()
        );
        assert!(text.len() <= limits::MAX_SCENARIO_BYTES);
        let lower = text.to_ascii_lowercase();
        for key in ["\"host\":", "\"hostname\":", "\"user\":", "\"username\":"] {
            assert!(!lower.contains(key), "{}: {key}", path.display());
        }
        assert!(
            !text.contains("127.0.0.1"),
            "{}: literal loopback address",
            path.display()
        );
    }
}
