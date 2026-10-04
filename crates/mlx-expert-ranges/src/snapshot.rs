//! Selected-content capture only. This module never performs numerical execution.
use crate::{refusal, ExpertPlan, Result};
use serde::Serialize;
use serde_json::json;
use sha2::{Digest, Sha256};
use std::fs::{OpenOptions, Permissions};
use std::io::Write;
use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
use std::path::Path;

pub const SNAPSHOT_MAGIC: &[u8; 8] = b"PLSEX001";
pub const MAX_SNAPSHOT_HEADER_BYTES: usize = 128 * 1024;

#[derive(Debug, Serialize)]
pub struct FreezeReceipt {
    pub schema: &'static str,
    pub owned: serde_json::Value,
    pub requested_payload_bytes: u64,
    pub payload_read_calls: u64,
    pub snapshot_payload_bytes_written: u64,
    pub snapshot_bytes: u64,
    pub snapshot_sha256: String,
    pub native_calls: u64,
    pub scope: &'static str,
}

/// Reserve a new private file before loading, capture nine admitted buffers,
/// flush and make the successful file read-only. Partial failures remain private
/// and are never returned as completed captures. Existing files are not replaced.
pub fn freeze_selected(
    plan: &ExpertPlan<'_>,
    expected_metadata_sha256: &str,
    output: &Path,
) -> Result<FreezeReceipt> {
    if expected_metadata_sha256.len() != 64
        || !expected_metadata_sha256
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
        || expected_metadata_sha256 != plan.record().metadata_snapshot_sha256
    {
        return Err(refusal("FREEZE_ADMISSION", "metadata identity mismatch"));
    }
    if !output.is_absolute() || output.extension().and_then(|s| s.to_str()) != Some("snapshot") {
        return Err(refusal(
            "FREEZE_ADMISSION",
            "absolute .snapshot path required",
        ));
    }
    let preflight =
        serde_json::to_vec(plan.record()).map_err(|e| refusal("FREEZE_ADMISSION", e))?;
    if preflight.len() > MAX_SNAPSHOT_HEADER_BYTES - 8192 {
        return Err(refusal("FREEZE_ADMISSION", "snapshot header budget"));
    }
    let before_bytes = plan.source.requested_payload_bytes();
    let before_calls = plan.source.payload_read_calls();
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(output)
        .map_err(|e| refusal("FREEZE_OUTPUT", e))?;
    let owned = plan.load()?;
    let receipt = owned.receipt();
    let lengths: Vec<_> = plan
        .record()
        .planes
        .iter()
        .flat_map(|p| p.ranges.iter().map(|r| r.len))
        .collect();
    let header = serde_json::to_vec(&json!({
        "schema":"pulsarmlx.selected-expert-snapshot/1",
        "owned":receipt,
        "payload_lengths":lengths,
        "scope":"selected packed content only; no numerical qualification"
    }))
    .map_err(|e| refusal("FREEZE_OUTPUT", e))?;
    if header.len() > MAX_SNAPSHOT_HEADER_BYTES {
        return Err(refusal("FREEZE_OUTPUT", "snapshot header budget"));
    }
    let mut hash = Sha256::new();
    let mut total = 0u64;
    let mut emit = |bytes: &[u8]| -> Result<()> {
        file.write_all(bytes)
            .map_err(|e| refusal("FREEZE_OUTPUT", e))?;
        hash.update(bytes);
        total += bytes.len() as u64;
        Ok(())
    };
    emit(SNAPSHOT_MAGIC)?;
    emit(&(header.len() as u64).to_le_bytes())?;
    emit(&header)?;
    let mut payload = 0u64;
    for role in 0..3 {
        for component in 0..3 {
            let bytes = owned
                .bytes(role, component)
                .ok_or_else(|| refusal("FREEZE_OUTPUT", "missing owned component"))?;
            emit(bytes)?;
            payload += bytes.len() as u64;
        }
    }
    file.sync_all().map_err(|e| refusal("FREEZE_OUTPUT", e))?;
    file.set_permissions(Permissions::from_mode(0o400))
        .map_err(|e| refusal("FREEZE_OUTPUT", e))?;
    Ok(FreezeReceipt {
        schema: "pulsarmlx.selected-expert-freeze/1",
        owned: receipt,
        requested_payload_bytes: plan.source.requested_payload_bytes() - before_bytes,
        payload_read_calls: plan.source.payload_read_calls() - before_calls,
        snapshot_payload_bytes_written: payload,
        snapshot_bytes: total,
        snapshot_sha256: format!("{:x}", hash.finalize()),
        native_calls: 0,
        scope: "selected packed host bytes and private snapshot only; no numerical qualification",
    })
}
