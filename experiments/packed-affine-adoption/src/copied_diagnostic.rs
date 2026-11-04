//! Admission for one prospective copied diagnostic. No native calls or launches.
use serde_json::{json, Value};
use std::path::Path;
pub const MODE: &str = "copied-diagnostic-v1";
pub const SCHEMA: &str = "pulsarmlx.copied-diagnostic-receipt/1";
pub const IDS: [&str; 3] = [
    "mlp-d128-h64-m1-e0-default-gate",
    "mlp-d128-h64-m1-e1-default-gate",
    "mlp-d128-h64-m1-e0-default-gate",
];
pub const ORIGINALS: [(&str, &str); 4] = [
    (
        "freeze",
        "3066d1259eff69f174854f26656ef35980365063710709090939cba2adde668a",
    ),
    (
        "failure",
        "92df14656fc1ba9fee6407e46e5b086d022dbed80e3530a616bee9fc8e0e9607",
    ),
    (
        "raw_intent",
        "3f51c7ec0dbf97f454a8290005eb1810148af1986c33f6d9c13ec9fa26a7d5a2",
    ),
    (
        "raw_report",
        "32bd5be256ee4ee58b62c085527e80e455ce777ae3875aa3f461a7ec29dbc086",
    ),
];
pub fn validate(config: &Value, receipt: &Value) -> Result<(), String> {
    if receipt["schema"] != SCHEMA
        || receipt["mode"] != MODE
        || config["mode"] != MODE
        || config["arm"] != "copied"
        || config["sequence"] != json!(IDS)
        || receipt["sequence"] != json!(IDS)
        || receipt["raw_probe"] != json!({"used":1,"allowed":1,"execution_authorized":false})
        || receipt["scope"]
            != json!({"children":1,"timeout_seconds":300,"retry":false,"diagnostic_only":true,"M1a_acceptance":false,"performance_claim":false})
    {
        return Err("copied-only diagnostic scope/raw ledger".into());
    }
    for forbidden in [
        "operations",
        "inherited_root",
        "case_id",
        "phase",
        "raw_probe_budget",
    ] {
        if config.get(forbidden).is_some() || receipt.get(forbidden).is_some() {
            return Err("full campaign/timing field in diagnostic".into());
        }
    }
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
        if receipt[key].is_null() || config[key] != receipt[key] {
            return Err(format!("diagnostic config/receipt binding: {key}"));
        }
    }
    for (name, hash) in ORIGINALS {
        if receipt["originals"][name]["sha256"] != hash {
            return Err("original receipt identity".into());
        }
    }
    Ok(())
}
/// Called before native preparation. The parent separately verifies full source,
/// installation and fixture inventories immediately before its single launch.
pub fn admit_child(config: &Value) -> Result<(), String> {
    let path = Path::new(
        config["diagnostic_receipt"]
            .as_str()
            .ok_or("diagnostic receipt path")?,
    );
    if path.metadata().map_err(|e| e.to_string())?.len() > 1024 * 1024 {
        return Err("diagnostic receipt size bound".into());
    }
    let bytes = std::fs::read(path).map_err(|e| e.to_string())?;
    if mlx_native_affine::fixture::sha256_hex(&bytes) != config["diagnostic_receipt_sha256"] {
        return Err("diagnostic receipt changed".into());
    }
    let receipt: Value = serde_json::from_slice(&bytes).map_err(|e| e.to_string())?;
    validate(config, &receipt)?;
    for (name, expected) in ORIGINALS {
        let original = receipt["originals"][name]["path"]
            .as_str()
            .ok_or("original path")?;
        if crate::file_sha256(original)? != expected {
            return Err("original local receipt changed/missing".into());
        }
    }
    Ok(())
}
