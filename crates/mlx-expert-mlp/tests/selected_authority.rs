//! Pure synthetic provider/capsule controls, never execution authorization.
use mlx_expert_mlp::selected_authority::{review_descriptor, SCHEMA};
use mlx_native_affine::fixture::sha256_hex;
use serde_json::{json, Value};
fn docs() -> (Value, Value) {
    let text = "# synthetic authority fixture\n";
    let hash = sha256_hex(text.as_bytes());
    let hashes = json!({"source.py":hash});
    let mut encoded = serde_json::to_vec(&hashes).unwrap();
    encoded.push(b'\n');
    let d = json!({"commit":"1".repeat(40),"tree":"2".repeat(40),"source_sha256":hashes,"package_sha256":sha256_hex(&encoded),"executable_sha256":"3".repeat(64),"contract_sha256":"4".repeat(64),"population_sha256":"5".repeat(64),"input_sha256":"6".repeat(64),"build":{"test":true},"pre_review_selected_numerical_observations":0});
    let c = json!({"schema":SCHEMA,"purpose":"FINAL_EXECUTION_REVIEW","descriptor":d,"source_files":{"source.py":{"sha256":hash,"text":text}}});
    let verdict = json!({"schema":SCHEMA,"decision":"ACCEPT","blockers":0,"assessed":d});
    let p = json!({"type":"result","subtype":"success","is_error":false,"modelUsage":{"claude-opus-5-5":{"outputTokens":1}},"result":verdict.to_string()});
    (c, p)
}
fn validate(c: &Value, p: &Value) -> Result<Value, String> {
    let cr = serde_json::to_vec(c).unwrap();
    let pr = serde_json::to_vec(p).unwrap();
    review_descriptor(&cr, &pr, &sha256_hex(&cr), &sha256_hex(&pr))
}
#[test]
fn exact_synthetic_documents_parse() {
    let (c, p) = docs();
    assert_eq!(validate(&c, &p).unwrap(), c["descriptor"]);
}
#[test]
fn invalid_provider_and_preliminary_review_refused() {
    for (key, value) in [
        ("is_error", json!(true)),
        ("modelUsage", json!({})),
        ("result", json!("Not logged in")),
    ] {
        let (c, mut p) = docs();
        p[key] = value;
        assert!(validate(&c, &p).is_err());
    }
    let (mut c, p) = docs();
    c["purpose"] = json!("PRELIMINARY_HOST_REVIEW");
    assert!(validate(&c, &p).is_err());
}
#[test]
fn assessed_version_and_source_mutations_refused() {
    let (c, mut p) = docs();
    let mut v: Value = serde_json::from_str(p["result"].as_str().unwrap()).unwrap();
    v["assessed"]["executable_sha256"] = json!("7".repeat(64));
    p["result"] = json!(v.to_string());
    assert!(validate(&c, &p).is_err());
    let (mut c, p) = docs();
    c["source_files"]["source.py"]["text"] = json!("mutated");
    assert!(validate(&c, &p).is_err());
}
#[test]
fn boolean_zero_is_not_a_verdict_or_observation_count() {
    let (c, mut p) = docs();
    let mut v: Value = serde_json::from_str(p["result"].as_str().unwrap()).unwrap();
    v["blockers"] = json!(false);
    p["result"] = json!(v.to_string());
    assert!(validate(&c, &p).is_err());
    let (mut c, p) = docs();
    c["descriptor"]["pre_review_selected_numerical_observations"] = json!(false);
    assert!(validate(&c, &p).is_err());
}
