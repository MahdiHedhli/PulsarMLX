//! Host-only bounded expert ownership. No native/GPU or whole-shard reads.
#![forbid(unsafe_code)]

use mlx_affine::{classify_module, ModuleKind, QuantizationConfig};
use safetensors_catalog::{parse_index, Checkpoint, Dtype, RootDirectory, INDEX_FILE_NAME};
use serde::Serialize;
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fs::{File, Metadata};
use std::os::unix::fs::{FileExt, MetadataExt};
use std::path::Path;
use std::sync::atomic::{AtomicU64, Ordering};

pub const MAX_JSON_BYTES: u64 = 4 * 1024 * 1024;
pub const MAX_SHARDS: usize = 32;
pub const MAX_ONE_HEADER_BYTES: u64 = 2 * 1024 * 1024;
pub const MAX_ALL_HEADER_BYTES: u64 = 16 * 1024 * 1024;
pub const MAX_SELECTED_BYTES: u64 = 32 * 1024 * 1024;

#[derive(Debug)]
pub struct Refusal {
    pub phase: &'static str,
    pub detail: String,
}
impl std::fmt::Display for Refusal {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "RANGE-{}: {}", self.phase, self.detail)
    }
}
impl std::error::Error for Refusal {}
type Result<T> = std::result::Result<T, Refusal>;
fn refusal(phase: &'static str, detail: impl ToString) -> Refusal {
    Refusal {
        phase,
        detail: detail.to_string(),
    }
}
fn digest(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
fn frame(h: &mut Sha256, bytes: &[u8]) {
    h.update((bytes.len() as u64).to_le_bytes());
    h.update(bytes);
}

#[derive(Debug, PartialEq, Eq)]
struct Stamp {
    dev: u64,
    ino: u64,
    len: u64,
    mtime: i64,
    mtime_ns: i64,
    ctime: i64,
    ctime_ns: i64,
}
fn stamp(m: &Metadata) -> Stamp {
    Stamp {
        dev: m.dev(),
        ino: m.ino(),
        len: m.len(),
        mtime: m.mtime(),
        mtime_ns: m.mtime_nsec(),
        ctime: m.ctime(),
        ctime_ns: m.ctime_nsec(),
    }
}
struct HeldFile {
    file: File,
    stamp: Stamp,
}
impl HeldFile {
    fn check(&self) -> Result<()> {
        let now = self.file.metadata().map_err(|e| refusal("MUTATION", e))?;
        if !now.is_file() || stamp(&now) != self.stamp {
            return Err(refusal("MUTATION", "admitted descriptor metadata changed"));
        }
        Ok(())
    }
}
fn admit(root: &RootDirectory, name: &str) -> Result<HeldFile> {
    let admitted = root.open_file(name).map_err(|e| refusal("PATH", e))?;
    let m = admitted
        .file
        .metadata()
        .map_err(|e| refusal("METADATA", e))?;
    if m.len() != admitted.len
        || m.dev() != admitted.identity.device
        || m.ino() != admitted.identity.inode
    {
        return Err(refusal("MUTATION", "descriptor changed during admission"));
    }
    Ok(HeldFile {
        file: admitted.file,
        stamp: stamp(&m),
    })
}
fn small(root: &RootDirectory, name: &str) -> Result<(Vec<u8>, HeldFile)> {
    let held = admit(root, name)?;
    if held.stamp.len > MAX_JSON_BYTES {
        return Err(refusal("LIMIT", name));
    }
    let mut bytes = vec![0; held.stamp.len as usize];
    held.file
        .read_exact_at(&mut bytes, 0)
        .map_err(|e| refusal("METADATA", e))?;
    held.check()?;
    Ok((bytes, held))
}

#[derive(Debug, Clone, Serialize)]
pub struct ExpertRequest {
    /// Declared gate/up/down semantics belong to the model binder.
    pub modules: [String; 3],
    pub expert: u64,
    pub experts: u64,
    pub d: u64,
    pub h: u64,
    pub bits: [u32; 3],
    pub group_size: u32,
}
#[derive(Debug, Clone, Serialize)]
pub struct RangeRecord {
    pub tensor: String,
    pub shard: String,
    pub begin: u64,
    pub len: u64,
}
#[derive(Debug, Clone, Serialize)]
pub struct PlaneRecord {
    pub role: String,
    pub module: String,
    pub expert: u64,
    pub bits: u32,
    pub group_size: u32,
    pub resolved_from: String,
    pub metadata_dtype: String,
    pub logical_shape: [u64; 2],
    pub ranges: [RangeRecord; 3],
}
#[derive(Debug, Clone, Serialize)]
pub struct PlanRecord {
    pub schema: String,
    pub checkpoint: String,
    pub metadata_snapshot_sha256: String,
    pub metadata_bytes_read: u64,
    pub request: ExpertRequest,
    pub planes: Vec<PlaneRecord>,
    pub selected_bytes: u64,
    pub identity_scope: String,
}

pub struct BoundedSource {
    _directory: RootDirectory,
    checkpoint: Checkpoint,
    config: QuantizationConfig,
    config_document: serde_json::Value,
    held: BTreeMap<String, HeldFile>,
    identity: String,
    metadata_bytes: u64,
    requested_payload_bytes: AtomicU64,
    payload_read_calls: AtomicU64,
}
impl BoundedSource {
    pub fn open(path: &Path) -> Result<Self> {
        let canonical = path.canonicalize().map_err(|e| refusal("PATH", e))?;
        let directory = RootDirectory::open(&canonical).map_err(|e| refusal("PATH", e))?;
        let (config_bytes, config_file) = small(&directory, "config.json")?;
        let (index_bytes, index_file) = small(&directory, INDEX_FILE_NAME)?;
        let config_text = std::str::from_utf8(&config_bytes).map_err(|e| refusal("CONFIG", e))?;
        let config =
            QuantizationConfig::from_config_json(config_text).map_err(|e| refusal("CONFIG", e))?;
        let config_document =
            serde_json::from_str(config_text).map_err(|e| refusal("CONFIG", e))?;
        let index_text = std::str::from_utf8(&index_bytes).map_err(|e| refusal("INDEX", e))?;
        let index = parse_index(index_text).map_err(|e| refusal("INDEX", e))?;
        let names = index.shards();
        if names.is_empty() || names.len() > MAX_SHARDS {
            return Err(refusal("LIMIT", "shard count"));
        }
        let mut hash = Sha256::new();
        frame(&mut hash, b"pulsarmlx.bounded-expert-metadata/1");
        frame(&mut hash, b"config.json");
        frame(&mut hash, &config_bytes);
        frame(&mut hash, INDEX_FILE_NAME.as_bytes());
        frame(&mut hash, &index_bytes);
        let mut held = BTreeMap::new();
        held.insert("config.json".to_string(), config_file);
        held.insert(INDEX_FILE_NAME.to_string(), index_file);
        let mut shards = Vec::new();
        let mut header_bytes = 0u64;
        for name in names {
            let file = admit(&directory, &name)?;
            let mut prefix = [0u8; 8];
            file.file
                .read_exact_at(&mut prefix, 0)
                .map_err(|e| refusal("HEADER", e))?;
            let len = u64::from_le_bytes(prefix);
            if len > MAX_ONE_HEADER_BYTES {
                return Err(refusal("LIMIT", "individual header"));
            }
            let total = len
                .checked_add(8)
                .ok_or_else(|| refusal("OVERFLOW", "header prefix"))?;
            header_bytes = header_bytes
                .checked_add(total)
                .ok_or_else(|| refusal("OVERFLOW", "header sum"))?;
            if header_bytes > MAX_ALL_HEADER_BYTES || total > file.stamp.len {
                return Err(refusal("LIMIT", "aggregate header or truncated file"));
            }
            let mut bytes = vec![0; total as usize];
            bytes[..8].copy_from_slice(&prefix);
            file.file
                .read_exact_at(&mut bytes[8..], 8)
                .map_err(|e| refusal("HEADER", e))?;
            file.check()?;
            frame(&mut hash, name.as_bytes());
            frame(&mut hash, &file.stamp.len.to_le_bytes());
            frame(&mut hash, &bytes);
            shards.push((name.clone(), file.stamp.len, bytes));
            held.insert(name, file);
        }
        let root_name = canonical
            .file_name()
            .and_then(|s| s.to_str())
            .ok_or_else(|| refusal("PATH", "root name"))?;
        let checkpoint = Checkpoint::from_headers(root_name, shards, Some(index_text))
            .map_err(|e| refusal("CATALOG", e))?;
        for file in held.values() {
            file.check()?;
        }
        Ok(Self {
            _directory: directory,
            checkpoint,
            config,
            config_document,
            held,
            identity: format!("{:x}", hash.finalize()),
            metadata_bytes: config_bytes.len() as u64 + index_bytes.len() as u64 + header_bytes,
            requested_payload_bytes: AtomicU64::new(0),
            payload_read_calls: AtomicU64::new(0),
        })
    }
    pub fn requested_payload_bytes(&self) -> u64 {
        self.requested_payload_bytes.load(Ordering::Relaxed)
    }
    pub fn config_document(&self) -> &serde_json::Value {
        &self.config_document
    }
    pub fn payload_read_calls(&self) -> u64 {
        self.payload_read_calls.load(Ordering::Relaxed)
    }
    pub fn plan(&self, request: ExpertRequest) -> Result<ExpertPlan<'_>> {
        if request.experts == 0
            || request.d == 0
            || request.h == 0
            || request.expert >= request.experts
        {
            return Err(refusal("INDEX", "empty geometry or expert out of range"));
        }
        if request.group_size != 64 || request.bits.iter().any(|b| ![4, 8].contains(b)) {
            return Err(refusal("RECIPE", "4/8-bit group-64 required"));
        }
        if request.modules.iter().collect::<BTreeSet<_>>().len() != 3 {
            return Err(refusal("MODULE", "three distinct declared roles required"));
        }
        let mut planes = Vec::new();
        let mut total = 0u64;
        for (role, module) in request.modules.iter().enumerate() {
            let kind = classify_module(self.checkpoint.catalog(), Some(&self.config), module)
                .map_err(|e| refusal("RESOLVE", e))?;
            let ModuleKind::Quantized(t) = kind else {
                return Err(refusal("RECIPE", "unquantized role"));
            };
            let shape = if role == 2 {
                [request.d, request.h]
            } else {
                [request.h, request.d]
            };
            if t.leading() != [request.experts] || [t.out_features(), t.in_features()] != shape {
                return Err(refusal("GEOMETRY", module));
            }
            if t.spec().bits.get() != request.bits[role]
                || t.spec().group_size.get() != request.group_size
                || t.scales().dtype != Dtype::Bf16
                || t.biases().dtype != Dtype::Bf16
            {
                return Err(refusal("RECIPE", module));
            }
            let slice = t
                .expert_slice(&[request.expert])
                .map_err(|e| refusal("RANGE", e))?;
            let mut ranges = Vec::new();
            for (component, s) in [slice.weight, slice.scales, slice.biases]
                .into_iter()
                .enumerate()
            {
                let shard = self
                    .checkpoint
                    .shard_name(s.shard)
                    .map_err(|e| refusal("RANGE", e))?
                    .to_string();
                let end = s
                    .begin
                    .checked_add(s.len)
                    .ok_or_else(|| refusal("OVERFLOW", "range end"))?;
                if end > self.held[&shard].stamp.len {
                    return Err(refusal("RANGE", "range exceeds admitted file"));
                }
                total = total
                    .checked_add(s.len)
                    .ok_or_else(|| refusal("OVERFLOW", "selected sum"))?;
                if total > MAX_SELECTED_BYTES {
                    return Err(refusal("BUDGET", "selected tuple exceeds 32 MiB"));
                }
                ranges.push(RangeRecord {
                    tensor: format!("{}.{}", module, ["weight", "scales", "biases"][component]),
                    shard,
                    begin: s.begin,
                    len: s.len,
                });
            }
            planes.push(PlaneRecord {
                role: ["gate", "up", "down"][role].into(),
                module: module.clone(),
                expert: request.expert,
                bits: t.spec().bits.get(),
                group_size: t.spec().group_size.get(),
                resolved_from: if self.config.explicit(module).is_some() {
                    "override"
                } else {
                    "default"
                }
                .into(),
                metadata_dtype: "BF16".into(),
                logical_shape: shape,
                ranges: ranges
                    .try_into()
                    .map_err(|_| refusal("RANGE", "range count"))?,
            });
        }
        Ok(ExpertPlan { source: self, record: PlanRecord { schema: "pulsarmlx.bounded-expert-plan/1".into(),
            checkpoint: self.checkpoint.root_name().into(), metadata_snapshot_sha256: self.identity.clone(),
            metadata_bytes_read: self.metadata_bytes, request, planes, selected_bytes: total,
            identity_scope: "metadata snapshot and selected ranges only; no whole-checkpoint payload identity".into() } })
    }
}

/// A plan is sealed and borrows its exact source. Its only loader takes no source argument.
pub struct ExpertPlan<'a> {
    source: &'a BoundedSource,
    record: PlanRecord,
}
impl ExpertPlan<'_> {
    pub fn record(&self) -> &PlanRecord {
        &self.record
    }
    pub fn load(&self) -> Result<OwnedExpertTuple> {
        for file in self.source.held.values() {
            file.check()?;
        }
        let mut buffers = Vec::new();
        let mut hashes = Vec::new();
        for plane in &self.record.planes {
            for range in &plane.ranges {
                let held = &self.source.held[&range.shard];
                held.check()?;
                let mut bytes = vec![
                    0;
                    usize::try_from(range.len)
                        .map_err(|_| refusal("OVERFLOW", "allocation size"))?
                ];
                self.source
                    .requested_payload_bytes
                    .fetch_add(range.len, Ordering::Relaxed);
                self.source
                    .payload_read_calls
                    .fetch_add(1, Ordering::Relaxed);
                held.file
                    .read_exact_at(&mut bytes, range.begin)
                    .map_err(|e| refusal("READ", e))?;
                held.check()?;
                hashes.push(digest(&bytes));
                buffers.push(bytes.into_boxed_slice());
            }
        }
        for file in self.source.held.values() {
            file.check()?;
        }
        Ok(OwnedExpertTuple {
            record: self.record.clone(),
            buffers,
            hashes,
        })
    }
}
/// Immutable buffers outlive all descriptors; moving this owner preserves byte addresses.
pub struct OwnedExpertTuple {
    record: PlanRecord,
    buffers: Vec<Box<[u8]>>,
    hashes: Vec<String>,
}
impl OwnedExpertTuple {
    pub fn bytes(&self, role: usize, component: usize) -> Option<&[u8]> {
        if role >= 3 || component >= 3 {
            return None;
        }
        self.buffers.get(role * 3 + component).map(|b| b.as_ref())
    }
    pub fn receipt(&self) -> serde_json::Value {
        serde_json::json!({"schema":"pulsarmlx.bounded-expert-owned/1","plan":self.record,
            "selected_range_sha256":self.hashes,"owned_bytes":self.buffers.iter().map(|b| b.len() as u64).sum::<u64>(),
            "packed_weights_unchanged":true,"native_calls":0,"whole_shard_reads":0,"whole_shard_hashes":0,
            "scope":"host owned range bytes only; no numerical or full-checkpoint qualification"})
    }
}
