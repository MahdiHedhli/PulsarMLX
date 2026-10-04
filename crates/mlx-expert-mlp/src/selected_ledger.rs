//! Canonical identities for the fixed one-real-attempt ledger.
use mlx_native_affine::fixture::sha256_hex;
use serde_json::{json, Value};
pub const RELATIVE_ROOT: &str = "Library/Application Support/PulsarMLX-handoff/20261004-real-expert-numerical-execution/native-attempt-04/real-ledgers";
fn digest(value: &Value) -> Result<String, String> {
    let mut raw = serde_json::to_vec(value).map_err(|e| e.to_string())?;
    raw.push(b'\n');
    Ok(sha256_hex(&raw))
}
pub fn key(descriptor: &Value, binding: &Value) -> Result<String, String> {
    digest(
        &json!({"commit":descriptor["commit"],"contract_sha256":descriptor["contract_sha256"],"snapshot_sha256":binding["snapshot_sha256"]}),
    )
}
pub fn capability_sha(cap: &Value) -> Result<String, String> {
    let mut issued = cap.as_object().ok_or("real capability object")?.clone();
    issued.remove("pre_admission");
    digest(&Value::Object(issued))
}
pub fn validate(
    record: &Value,
    cap: &Value,
    descriptor: &Value,
    binding: &Value,
) -> Result<(), String> {
    if record["schema"] != "pulsarmlx.selected-real-attempt/2"
        || record["capability_sha256"] != capability_sha(cap)?
        || record["commit"] != descriptor["commit"]
        || record["contract_sha256"] != descriptor["contract_sha256"]
        || record["snapshot_sha256"] != binding["snapshot_sha256"]
    {
        return Err("SELECTED-R-AUTHORITY: issued real capability ledger".into());
    }
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn out_changes_authority_but_admission_receipt_does_not() {
        let cap = json!({"kind":"real","out":"/fixed","snapshot_path":"/original"});
        let mut changed = cap.clone();
        changed["out"] = json!("/fresh");
        assert_ne!(
            capability_sha(&cap).unwrap(),
            capability_sha(&changed).unwrap()
        );
        changed = cap.clone();
        changed["pre_admission"] = json!({"sha256":"later"});
        assert_eq!(
            capability_sha(&cap).unwrap(),
            capability_sha(&changed).unwrap()
        );
    }
    #[test]
    fn ledger_binds_all_three_identities() {
        let d = json!({"commit":"a","contract_sha256":"b"});
        let b = json!({"snapshot_sha256":"c"});
        let cap = json!({"kind":"real"});
        let r = json!({"schema":"pulsarmlx.selected-real-attempt/2","commit":"a","contract_sha256":"b","snapshot_sha256":"c","capability_sha256":capability_sha(&cap).unwrap()});
        validate(&r, &cap, &d, &b).unwrap();
        for field in [
            "commit",
            "contract_sha256",
            "snapshot_sha256",
            "capability_sha256",
        ] {
            let mut bad = r.clone();
            bad[field] = json!("changed");
            assert!(validate(&bad, &cap, &d, &b).is_err());
        }
    }
}
