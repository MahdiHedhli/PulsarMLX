//! Bounded original packed snapshot custody. No checkpoint open or native calls.
use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::fs::{Metadata, OpenOptions};
use std::io::Read;
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
use std::path::Path;

const HEADER_MAX: usize = 128 * 1024;
pub const PAYLOAD_BYTES: usize = 14_155_776;
const LENGTHS: [usize; 9] = [
    4_194_304, 262_144, 262_144, 4_194_304, 262_144, 262_144, 4_194_304, 262_144, 262_144,
];
const PREFIX: &str = "language_model.model.layers.3.mlp.switch_mlp";

/// These bindings must come from the independently verified frozen package,
/// never from the snapshot being read. This is custody, not execution authority.
pub struct Binding {
    pub snapshot_sha256: String,
    pub snapshot_bytes: u64,
    pub metadata_sha256: String,
    pub checkpoint: String,
    pub ranges_sha256: [String; 9],
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Header {
    schema: String,
    owned: Owned,
    payload_lengths: [usize; 9],
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Owned {
    schema: String,
    plan: Plan,
    selected_range_sha256: [String; 9],
    owned_bytes: usize,
    packed_weights_unchanged: bool,
    native_calls: u64,
    whole_shard_reads: u64,
    whole_shard_hashes: u64,
    scope: String,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Plan {
    schema: String,
    checkpoint: String,
    metadata_snapshot_sha256: String,
    metadata_bytes_read: u64,
    request: Request,
    planes: [Plane; 3],
    selected_bytes: usize,
    identity_scope: String,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Request {
    modules: [String; 3],
    expert: u64,
    experts: u64,
    d: u64,
    h: u64,
    bits: [u32; 3],
    group_size: u32,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Plane {
    role: String,
    module: String,
    expert: u64,
    bits: u32,
    group_size: u32,
    resolved_from: String,
    metadata_dtype: String,
    logical_shape: [u64; 2],
    ranges: [Range; 3],
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Range {
    tensor: String,
    shard: String,
    begin: u64,
    len: u64,
}

pub struct SelectedSnapshot {
    buffers: [Box<[u8]>; 9],
    pub snapshot_sha256: String,
}

fn digest(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}
fn valid_hash(s: &str) -> bool {
    s.len() == 64
        && s.bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}
fn stamp(m: &Metadata) -> (u64, u64, u64, i64, i64, i64, i64, u32) {
    (
        m.dev(),
        m.ino(),
        m.len(),
        m.mtime(),
        m.mtime_nsec(),
        m.ctime(),
        m.ctime_nsec(),
        m.mode(),
    )
}
fn check(ok: bool, message: &str) -> Result<(), String> {
    if ok {
        Ok(())
    } else {
        Err(format!("SELECTED-R-CUSTODY: {message}"))
    }
}

impl SelectedSnapshot {
    pub fn read(path: &Path, expected: &Binding) -> Result<Self, String> {
        check(
            valid_hash(&expected.snapshot_sha256)
                && valid_hash(&expected.metadata_sha256)
                && expected.ranges_sha256.iter().all(|s| valid_hash(s)),
            "expected hashes",
        )?;
        let mut file = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW)
            .open(path)
            .map_err(|e| e.to_string())?;
        let before = file.metadata().map_err(|e| e.to_string())?;
        check(
            before.is_file()
                && before.mode() & 0o222 == 0
                && before.len() == expected.snapshot_bytes
                && before.len() <= (16 + HEADER_MAX + PAYLOAD_BYTES) as u64,
            "regular immutable bounded file",
        )?;
        let mut prefix = [0u8; 16];
        file.read_exact(&mut prefix).map_err(|e| e.to_string())?;
        check(&prefix[..8] == b"PLSEX001", "magic")?;
        let length = u64::from_le_bytes(prefix[8..].try_into().unwrap());
        check(length > 0 && length <= HEADER_MAX as u64, "header bound")?;
        check(
            16 + length + PAYLOAD_BYTES as u64 == before.len(),
            "framing size",
        )?;
        let mut raw = vec![0u8; length as usize];
        file.read_exact(&mut raw).map_err(|e| e.to_string())?;
        safetensors_catalog::json_guard::reject_duplicate_keys(&raw, "selected-snapshot")
            .map_err(|e| e.to_string())?;
        let header: Header = serde_json::from_slice(&raw).map_err(|e| e.to_string())?;
        check(
            header.schema == "pulsarmlx.selected-expert-snapshot/1"
                && header.payload_lengths == LENGTHS,
            "header schema/lengths",
        )?;
        let owned = &header.owned;
        check(
            owned.schema == "pulsarmlx.bounded-expert-owned/1"
                && owned.owned_bytes == PAYLOAD_BYTES
                && owned.packed_weights_unchanged
                && owned.native_calls == 0
                && owned.whole_shard_reads == 0
                && owned.whole_shard_hashes == 0
                && owned.scope
                    == "host owned range bytes only; no numerical or full-checkpoint qualification"
                && owned.selected_range_sha256 == expected.ranges_sha256,
            "owned binding",
        )?;
        let plan = &owned.plan;
        check(plan.schema == "pulsarmlx.bounded-expert-plan/1"
              && plan.checkpoint == expected.checkpoint && !expected.checkpoint.is_empty()
              && plan.metadata_snapshot_sha256 == expected.metadata_sha256
              && plan.metadata_bytes_read == 790_848 && plan.selected_bytes == PAYLOAD_BYTES
              && plan.identity_scope == "metadata snapshot and selected ranges only; no whole-checkpoint payload identity",
              "original source identity")?;
        let req = &plan.request;
        let modules = ["gate_proj", "up_proj", "down_proj"].map(|r| format!("{PREFIX}.{r}"));
        check(
            req.modules == modules
                && req.expert == 0
                && req.experts == 288
                && req.d == 4096
                && req.h == 2048
                && req.bits == [4, 4, 4]
                && req.group_size == 64,
            "selected model geometry",
        )?;
        for (i, p) in plan.planes.iter().enumerate() {
            check(
                p.module == modules[i]
                    && p.role == ["gate", "up", "down"][i]
                    && p.expert == 0
                    && p.bits == 4
                    && p.group_size == 64
                    && p.metadata_dtype == "BF16"
                    && p.resolved_from == "default"
                    && p.logical_shape == if i == 2 { [4096, 2048] } else { [2048, 4096] },
                "role/recipe/shape",
            )?;
            for (j, r) in p.ranges.iter().enumerate() {
                check(
                    r.tensor == format!("{}.{}", modules[i], ["weight", "scales", "biases"][j])
                        && r.len == LENGTHS[i * 3 + j] as u64
                        && r.begin.checked_add(r.len).is_some()
                        && !r.shard.is_empty()
                        && Path::new(&r.shard).components().count() == 1
                        && matches!(
                            Path::new(&r.shard).components().next(),
                            Some(std::path::Component::Normal(_))
                        ),
                    "original range identity",
                )?;
            }
        }
        let mut whole = Sha256::new();
        whole.update(prefix);
        whole.update(&raw);
        let mut buffers: Vec<Box<[u8]>> = Vec::with_capacity(9);
        for (i, n) in LENGTHS.iter().enumerate() {
            let mut buf = vec![0u8; *n];
            file.read_exact(&mut buf).map_err(|e| e.to_string())?;
            check(
                digest(&buf) == expected.ranges_sha256[i],
                "original range digest",
            )?;
            whole.update(&buf);
            buffers.push(buf.into_boxed_slice());
        }
        let mut end = [0u8; 1];
        check(
            file.read(&mut end).map_err(|e| e.to_string())? == 0,
            "trailing bytes",
        )?;
        let after = file.metadata().map_err(|e| e.to_string())?;
        check(stamp(&before) == stamp(&after), "descriptor changed")?;
        let actual = format!("{:x}", whole.finalize());
        check(
            actual == expected.snapshot_sha256,
            "original snapshot digest",
        )?;
        Ok(Self {
            buffers: buffers.try_into().map_err(|_| "nine buffers")?,
            snapshot_sha256: actual,
        })
    }
    pub fn component(&self, role: usize, component: usize) -> Option<&[u8]> {
        if role >= 3 || component >= 3 {
            return None;
        }
        self.buffers.get(role * 3 + component).map(|b| b.as_ref())
    }
}
