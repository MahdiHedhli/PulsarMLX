//! Pure exact-version review gate. Synthetic tests do not issue capabilities.
use mlx_native_affine::fixture::sha256_hex;
use serde_json::Value;

pub const SCHEMA: &str = "pulsarmlx.selected-execution-review/2";
const MAX_DOCUMENT: usize = 16 * 1024 * 1024;

pub fn strict(raw: &[u8]) -> Result<Value, String> {
    if raw.len() > MAX_DOCUMENT {
        return Err("AUTHORITY: document budget".into());
    }
    safetensors_catalog::json_guard::reject_duplicate_keys(raw, "selected-review")
        .map_err(|e| e.to_string())?;
    serde_json::from_slice(raw).map_err(|e| e.to_string())
}
fn require(ok: bool, why: &str) -> Result<(), String> {
    if ok {
        Ok(())
    } else {
        Err(format!("AUTHORITY: {why}"))
    }
}

/// Return the original descriptor only after actual raw provider response and
/// capsule file bytes have independently matched. The native entrypoint must
/// additionally bind current source/build and mode-specific admission evidence.
pub fn review_descriptor(
    capsule_raw: &[u8],
    review_raw: &[u8],
    capsule_sha: &str,
    review_sha: &str,
) -> Result<Value, String> {
    require(
        sha256_hex(capsule_raw) == capsule_sha && sha256_hex(review_raw) == review_sha,
        "raw capsule/review digest",
    )?;
    let capsule = strict(capsule_raw)?;
    require(
        capsule["schema"] == SCHEMA && capsule["purpose"] == "FINAL_EXECUTION_REVIEW",
        "final execution review required",
    )?;
    let provider = strict(review_raw)?;
    require(
        provider["type"] == "result"
            && provider["subtype"] == "success"
            && provider["is_error"] == false,
        "invalid provider response",
    )?;
    let usage = provider["modelUsage"]
        .as_object()
        .ok_or("AUTHORITY: modelUsage")?;
    require(
        usage.len() == 1
            && usage.contains_key("claude-opus-5-5")
            && usage["claude-opus-5-5"]["outputTokens"]
                .as_u64()
                .is_some_and(|n| n > 0),
        "actual reviewer model",
    )?;
    let result = provider["result"]
        .as_str()
        .ok_or("AUTHORITY: provider result")?
        .trim();
    let result = result
        .strip_prefix("```json\n")
        .and_then(|s| s.strip_suffix("\n```"))
        .unwrap_or(result);
    let verdict = strict(result.as_bytes())?;
    require(
        verdict["schema"] == SCHEMA
            && verdict["decision"] == "ACCEPT"
            && verdict["blockers"].as_u64() == Some(0),
        "final ACCEPT/zero blockers",
    )?;
    let descriptor = &capsule["descriptor"];
    require(
        descriptor.is_object()
            && descriptor["pre_review_selected_numerical_observations"].as_u64() == Some(0),
        "pre-review observation boundary",
    )?;
    require(
        verdict["assessed"] == *descriptor,
        "exact assessed version/build",
    )?;
    let source = capsule["source_files"]
        .as_object()
        .ok_or("AUTHORITY: source files")?;
    let hashes = descriptor["source_sha256"]
        .as_object()
        .ok_or("AUTHORITY: source hashes")?;
    require(
        !source.is_empty() && source.keys().eq(hashes.keys()),
        "source coverage",
    )?;
    for (name, record) in source {
        let raw = record["text"].as_str().ok_or("AUTHORITY: source text")?;
        require(
            record["sha256"] == sha256_hex(raw.as_bytes()) && record["sha256"] == hashes[name],
            "source bytes/hash",
        )?;
    }
    let mut encoded = serde_json::to_vec(hashes).map_err(|e| e.to_string())?;
    encoded.push(b'\n');
    require(
        descriptor["package_sha256"] == sha256_hex(&encoded),
        "package digest",
    )?;
    for key in [
        "commit",
        "tree",
        "executable_sha256",
        "contract_sha256",
        "population_sha256",
        "input_sha256",
        "build",
    ] {
        require(descriptor.get(key).is_some(), "missing descriptor field")?;
    }
    Ok(descriptor.clone())
}
