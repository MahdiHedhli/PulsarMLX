use packed_affine_adoption::copied_diagnostic::{self as d, IDS, MODE, ORIGINALS, SCHEMA};
use serde_json::{json, Value};
fn pair() -> (Value, Value) {
    let mut r = json!({"schema":SCHEMA,"mode":MODE,"sequence":IDS,
        "raw_probe":{"used":1,"allowed":1,"execution_authorized":false},
        "scope":{"children":1,"timeout_seconds":300,"retry":false,"diagnostic_only":true,"M1a_acceptance":false,"performance_claim":false},
        "source_commit":"synthetic-source","source_tree":"synthetic-tree","binary_sha256":"synthetic-binary",
        "native_libraries":{},"host":{},"generator_hashes":{},"dependency_manifest_sha256":"synthetic",
        "fixture_root":"synthetic-fixtures","fixture_manifest_sha256":"synthetic-fixture-hash","metadata_identities":{},"originals":{}});
    for (name, hash) in ORIGINALS {
        r["originals"][name] = json!({"sha256":hash});
    }
    let mut c = r.clone();
    c["arm"] = json!("copied");
    (c, r)
}
#[test]
fn exact_copied_scope_is_admitted() {
    let (c, r) = pair();
    assert!(d::validate(&c, &r).is_ok());
}
#[test]
fn alternative_native_routes_are_refused() {
    let (c, r) = pair();
    for mode in [
        "raw-length",
        "adopted",
        "diagnostic",
        "inherited",
        "fill",
        "resident",
        "m1a",
        "m1b",
    ] {
        let mut changed = c.clone();
        changed["mode"] = json!(mode);
        assert!(d::validate(&changed, &r).is_err());
    }
    let mut adopted = c.clone();
    adopted["arm"] = json!("adopted");
    assert!(d::validate(&adopted, &r).is_err());
}
#[test]
fn sequence_and_raw_spending_are_exact() {
    let (c, r) = pair();
    let mut changed = c.clone();
    changed["sequence"] = json!([IDS[0]]);
    assert!(d::validate(&changed, &r).is_err());
    for raw in [
        json!({"used":0,"allowed":1,"execution_authorized":false}),
        json!({"used":1,"allowed":2,"execution_authorized":false}),
        json!({"used":true,"allowed":1,"execution_authorized":false}),
        json!({"used":1,"allowed":1,"execution_authorized":true}),
    ] {
        let mut changed = r.clone();
        changed["raw_probe"] = raw;
        assert!(d::validate(&c, &changed).is_err());
    }
}
#[test]
fn crossed_bindings_and_originals_are_refused() {
    let (c, r) = pair();
    for key in [
        "source_commit",
        "source_tree",
        "binary_sha256",
        "native_libraries",
        "host",
        "generator_hashes",
        "dependency_manifest_sha256",
        "fixture_root",
        "fixture_manifest_sha256",
        "metadata_identities",
    ] {
        let mut changed = c.clone();
        changed[key] = Value::Null;
        assert!(d::validate(&changed, &r).is_err());
    }
    for (name, _) in ORIGINALS {
        let mut changed = r.clone();
        changed["originals"][name]["sha256"] = json!("wrong");
        assert!(d::validate(&c, &changed).is_err());
    }
}
#[test]
fn no_timing_full_campaign_or_retry_fields() {
    let (c, r) = pair();
    for key in [
        "operations",
        "inherited_root",
        "case_id",
        "phase",
        "raw_probe_budget",
    ] {
        let mut changed = c.clone();
        changed[key] = json!(false);
        assert!(d::validate(&changed, &r).is_err());
    }
    for (key, val) in [
        ("retry", json!(true)),
        ("children", json!(2)),
        ("timeout_seconds", json!(301)),
        ("M1a_acceptance", json!(true)),
    ] {
        let mut changed = r.clone();
        changed["scope"][key] = val;
        assert!(d::validate(&c, &changed).is_err());
    }
}
#[test]
fn missing_evidence_is_refused_before_native_entry() {
    let (c, _) = pair();
    assert!(d::admit_child(&c).is_err());
}
