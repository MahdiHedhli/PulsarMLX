#[path = "support/continuation.rs"]
mod policy;
use serde_json::{json, Value};

fn freeze(ci: bool) -> Value {
    json!({"schema":policy::SCHEMA,"phase":"m1a",
        "host_role":if ci {"native-ci"} else {"m1-ultra-studio"},
        "raw_policy":if ci {"CI_FRESH_ONCE"} else {"STUDIO_RETAINED_OBSERVATION"},
        "raw_probe_budget":{"allowed":1,"used":u8::from(!ci)},"raw_execution_authorized":ci,
        "raw_provenance":{"applies_to_current_binary":ci},"M1b_released":false,"shipping_default":"copied"})
}
#[test]
fn studio_zero_raw_ci_one_selection() {
    assert_eq!(
        policy::raw_allowed(&freeze(false), Some("m1a")),
        Ok(Some(false))
    );
    assert_eq!(
        policy::raw_allowed(&freeze(true), Some("m1a")),
        Ok(Some(true))
    );
}
#[test]
fn wrong_host_policy_and_schema_refuse() {
    for (key, value) in [
        ("host_role", "macbook"),
        ("raw_policy", "skip"),
        ("schema", "unknown"),
    ] {
        let mut f = freeze(false);
        f[key] = json!(value);
        assert!(policy::raw_allowed(&f, Some("m1a")).is_err());
    }
    let mut f = freeze(false);
    f["raw_policy"] = json!("CI_FRESH_ONCE");
    assert!(policy::raw_allowed(&f, Some("m1a")).is_err());
}
#[test]
fn missing_or_timing_phase_refuses() {
    for phase in [None, Some("m1b"), Some("unknown")] {
        assert!(policy::raw_allowed(&freeze(true), phase).is_err());
    }
}
#[test]
fn ledger_and_current_binary_relabelling_refuse() {
    for ci in [true, false] {
        for key in [
            "raw_probe_budget",
            "raw_execution_authorized",
            "raw_provenance",
            "M1b_released",
            "shipping_default",
        ] {
            let mut f = freeze(ci);
            f[key] = json!(null);
            assert!(policy::raw_allowed(&f, Some("m1a")).is_err());
        }
    }
}
#[test]
fn legacy_policy_remains_distinct() {
    assert_eq!(
        policy::raw_allowed(&json!({"schema":"pulsarmlx.adoption-host-freeze/1"}), None),
        Ok(None)
    );
}
