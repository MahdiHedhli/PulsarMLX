//! R001 deterministic expert-bundle writer.
//!
//! The production path copies admitted GGUF byte ranges without decoding or
//! transforming them. The acceptance verifier is intentionally implemented in
//! Python and does not import this crate.

use serde::Deserialize;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::os::unix::fs::{FileExt, MetadataExt, OpenOptionsExt};
use std::path::{Component, Path, PathBuf};
use std::time::{Instant, SystemTime, UNIX_EPOCH};

pub const HEADER_LEN: u64 = 16_384;
pub const FOOTER_LEN: u64 = 16_384;
pub const PREAMBLE_LEN: usize = 128;
pub const FORMAT_ALIGNMENT: u64 = 16_384;
const CHUNK: usize = 8 * 1024 * 1024;
const HEADER_MAGIC: &[u8; 8] = b"PMLXEX01";
const FOOTER_MAGIC: &[u8; 8] = b"PMLXEND1";
const CHECKPOINT_EXPECTED: &str =
    "d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee";
const INVENTORY_EXPECTED: &str =
    "ca23db7459219acd39cd047eb6490c814ab40d472dd081424624ac8bf8fc5c9b";
const EXPECTED_SHARDS: [(&str, u64, &str); 6] = [
    ("GLM-5.2-UD-IQ2_XXS-00001-of-00006.gguf", 9_423_744, "7bf96eeabbe887e58b6c44364962731ddc9dc5bf46fec8d097c1dff64bea4a18"),
    ("GLM-5.2-UD-IQ2_XXS-00002-of-00006.gguf", 49_105_028_960, "d94adaa58ddd5abbcf2514192958084416b1aa36bd4d21409028a164341bac36"),
    ("GLM-5.2-UD-IQ2_XXS-00003-of-00006.gguf", 49_143_176_640, "1cd0b1a3d9d939ce5a184c548f1b1c42edafaf1856cb0d7e586a2884a366256b"),
    ("GLM-5.2-UD-IQ2_XXS-00004-of-00006.gguf", 49_143_176_640, "10f3965db697a46ba66494475045af183c1bcaf639984160930c91a377816d3e"),
    ("GLM-5.2-UD-IQ2_XXS-00005-of-00006.gguf", 49_143_176_640, "40d7d4524ff07e0f9af494fb13130dc7090184800cc5af0a1563188b076af50d"),
    ("GLM-5.2-UD-IQ2_XXS-00006-of-00006.gguf", 41_914_650_304, "eeceb9084350e64be8eebcd1f19ab14bbbb6b40132c86d77ffc65e72f425044d"),
];

pub type Result<T> = std::result::Result<T, Box<dyn std::error::Error + Send + Sync>>;

#[derive(Debug, Deserialize)]
pub struct Inventory {
    pub schema: String,
    pub checkpoint_set_sha256: String,
    pub architecture: String,
    pub expert_tensor_count: u64,
    pub logical_object_count: u64,
    pub expert_payload_bytes: u64,
    pub objects: Vec<InventoryObject>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct InventoryObject {
    pub layer: u32,
    pub expert: u32,
    #[serde(rename = "class")]
    pub expert_class: String,
    pub components: Vec<InventoryComponent>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct InventoryComponent {
    pub role: String,
    pub tensor: String,
    pub shard: String,
    #[serde(rename = "type")]
    pub gguf_type: String,
    pub dims: Vec<u64>,
    #[serde(rename = "block_elements")]
    pub type_block_elements: u64,
    #[serde(rename = "block_bytes")]
    pub type_block_bytes: u64,
    pub row_bytes: u64,
    #[serde(rename = "length")]
    pub plane_bytes: u64,
    #[serde(rename = "offset")]
    pub data_offset_abs: u64,
    #[serde(rename = "end")]
    pub data_end_abs: u64,
}

#[derive(Debug, Deserialize)]
pub struct Admission {
    pub schema: String,
    #[serde(rename = "set_sha256")]
    pub checkpoint_set_sha256: String,
    pub inventory_sha256: String,
    pub total_bytes: u64,
    pub shards: Vec<AdmissionShard>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct AdmissionShard {
    pub index: u32,
    pub name: String,
    pub size: u64,
    pub sha256: String,
    pub destination_stat: SourceStat,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
pub struct SourceStat {
    pub device: u64,
    pub size: u64,
    pub mtime_ns: i128,
    pub inode: u64,
}

#[derive(Debug, Clone)]
pub struct ScopeLayer {
    pub layer: u32,
    pub routed: Vec<u32>,
    pub shared: bool,
}

#[derive(Debug, Clone)]
pub struct ComponentPlan {
    pub role: String,
    pub tensor: String,
    pub shard: String,
    pub shard_ordinal: u32,
    pub shard_sha256: String,
    pub source_stat: SourceStat,
    pub source_offset: u64,
    pub length: u64,
    pub type_id: u32,
    pub type_name: String,
    pub dims: Vec<u64>,
    pub block_elements: u64,
    pub block_bytes: u64,
    pub row_bytes: u64,
    pub plane_bytes: u64,
    pub bundle_offset: u64,
    pub padding_after: u64,
}

#[derive(Debug, Clone)]
pub struct ObjectPlan {
    pub layer: u32,
    pub expert: u32,
    pub expert_class: String,
    pub relative_path: PathBuf,
    pub components: Vec<ComponentPlan>,
}

#[derive(Debug, Clone)]
pub struct RepackConfig {
    pub checkpoint_dir: PathBuf,
    pub admission_path: PathBuf,
    pub inventory_path: PathBuf,
    pub output_root: PathBuf,
    pub staging_root: PathBuf,
    pub scope: Vec<ScopeLayer>,
    pub summary_path: PathBuf,
    pub dry_run: bool,
    pub resume: bool,
    pub test_interrupt_after_bytes: Option<u64>,
    pub test_interrupt_after_manifest: bool,
}

#[derive(Debug)]
struct CompleteObject {
    plan: ObjectPlan,
    metadata: Value,
    stored_len: u64,
    stored_sha256: String,
    canonical_payload_len: u64,
    canonical_payload_sha256: String,
    object_identity_sha256: String,
    reused: bool,
}

fn err(msg: impl Into<String>) -> Box<dyn std::error::Error + Send + Sync> {
    msg.into().into()
}

fn checked_add(a: u64, b: u64, what: &str) -> Result<u64> {
    a.checked_add(b).ok_or_else(|| err(format!("overflow adding {what}: {a}+{b}")))
}

fn checked_mul(a: u64, b: u64, what: &str) -> Result<u64> {
    a.checked_mul(b).ok_or_else(|| err(format!("overflow multiplying {what}: {a}*{b}")))
}

fn align_up(value: u64, alignment: u64) -> Result<u64> {
    if !alignment.is_power_of_two() {
        return Err(err("alignment must be a power of two"));
    }
    checked_add(value, alignment - 1, "alignment").map(|v| v & !(alignment - 1))
}

fn sha256_bytes(bytes: &[u8]) -> String {
    let mut h = Sha256::new();
    h.update(bytes);
    hex(&h.finalize())
}

fn hex(bytes: &[u8]) -> String {
    const H: &[u8; 16] = b"0123456789abcdef";
    let mut out = String::with_capacity(bytes.len() * 2);
    for &b in bytes {
        out.push(H[(b >> 4) as usize] as char);
        out.push(H[(b & 15) as usize] as char);
    }
    out
}

fn decode_hex_32(s: &str) -> Result<[u8; 32]> {
    if s.len() != 64 || !s.bytes().all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase()) {
        return Err(err(format!("invalid lowercase sha256: {s}")));
    }
    let mut out = [0u8; 32];
    for (i, x) in out.iter_mut().enumerate() {
        *x = u8::from_str_radix(&s[i * 2..i * 2 + 2], 16)?;
    }
    Ok(out)
}

fn validate_canonical_value(v: &Value) -> Result<()> {
    match v {
        Value::Bool(_) => Ok(()),
        Value::Number(n) if n.as_u64().is_some() => Ok(()),
        Value::String(s)
            if s.bytes().all(|b| (0x20..=0x7e).contains(&b)) =>
        {
            Ok(())
        }
        Value::Array(a) => a.iter().try_for_each(validate_canonical_value),
        Value::Object(m) => {
            let mut last: Option<&str> = None;
            for (k, value) in m {
                if !k.bytes().all(|b| (0x20..=0x7e).contains(&b)) {
                    return Err(err("canonical JSON key is not printable ASCII"));
                }
                if let Some(prev) = last {
                    if prev >= k.as_str() {
                        return Err(err("canonical JSON keys are not strictly ordered"));
                    }
                }
                last = Some(k);
                validate_canonical_value(value)?;
            }
            Ok(())
        }
        _ => Err(err("canonical JSON permits only objects, arrays, ASCII strings, u64, and booleans")),
    }
}

pub fn canonical_json(v: &Value) -> Result<Vec<u8>> {
    validate_canonical_value(v)?;
    Ok(serde_json::to_vec(v)?)
}

fn domain_hash(domain: &[u8], v: &Value) -> Result<String> {
    let mut h = Sha256::new();
    h.update(domain);
    h.update([0]);
    h.update(canonical_json(v)?);
    Ok(hex(&h.finalize()))
}

pub fn parse_scope(spec: &str, shared: bool) -> Result<Vec<ScopeLayer>> {
    let mut out = BTreeMap::<u32, Vec<u32>>::new();
    for clause in spec.split(';').filter(|s| !s.is_empty()) {
        let (layer_s, experts_s) = clause
            .split_once(':')
            .ok_or_else(|| err(format!("bad scope clause {clause}")))?;
        let layer: u32 = layer_s.parse()?;
        if out.contains_key(&layer) {
            return Err(err(format!("duplicate scope layer {layer}")));
        }
        let experts: Vec<u32> = if experts_s == "*" {
            (0..256).collect()
        } else {
            let mut seen = BTreeSet::new();
            for s in experts_s.split(',').filter(|s| !s.is_empty()) {
                let e: u32 = s.parse()?;
                if e >= 256 || !seen.insert(e) {
                    return Err(err(format!("invalid or duplicate expert {e}")));
                }
            }
            seen.into_iter().collect()
        };
        if experts.is_empty() {
            return Err(err(format!("layer {layer} has no routed experts")));
        }
        out.insert(layer, experts);
    }
    Ok(out
        .into_iter()
        .map(|(layer, routed)| ScopeLayer { layer, routed, shared })
        .collect())
}

fn type_id(name: &str) -> Result<u32> {
    Ok(match name {
        "Q8_0" => 8,
        "Q2_K" => 10,
        "Q3_K" => 11,
        "Q5_K" => 13,
        "Q6_K" => 14,
        "IQ2_XXS" => 16,
        "IQ3_XXS" => 18,
        "IQ2_S" => 22,
        "IQ4_XS" => 23,
        other => return Err(err(format!("unsupported expert type {other}"))),
    })
}

fn safe_relative(path: &Path) -> Result<()> {
    if path.is_absolute()
        || path.components().any(|c| !matches!(c, Component::Normal(_)))
    {
        return Err(err(format!("unsafe relative path {}", path.display())));
    }
    Ok(())
}

fn stat_from_metadata(metadata: &fs::Metadata) -> SourceStat {
    SourceStat {
        device: metadata.dev(),
        size: metadata.len(),
        mtime_ns: metadata.mtime() as i128 * 1_000_000_000 + metadata.mtime_nsec() as i128,
        inode: metadata.ino(),
    }
}

fn open_source(path: &Path) -> Result<(File, SourceStat)> {
    let file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW)
        .open(path)?;
    let metadata = file.metadata()?;
    if !metadata.is_file() || metadata.nlink() != 1 {
        return Err(err(format!("source is not a regular unique file: {}", path.display())));
    }
    Ok((file, stat_from_metadata(&metadata)))
}

fn expected_set_hash(shards: &[AdmissionShard]) -> String {
    let mut hash = Sha256::new();
    for shard in shards {
        hash.update(shard.sha256.as_bytes());
        hash.update(shard.size.to_string().as_bytes());
    }
    hex(&hash.finalize())
}

fn load_authority(cfg: &RepackConfig) -> Result<(Inventory, Admission, String)> {
    let inventory_bytes = fs::read(&cfg.inventory_path)?;
    let inventory_sha = sha256_bytes(&inventory_bytes);
    let inventory: Inventory = serde_json::from_slice(&inventory_bytes)?;
    if inventory_sha != INVENTORY_EXPECTED
        || inventory.checkpoint_set_sha256 != CHECKPOINT_EXPECTED
        || inventory.architecture != "glm-dsa"
        || inventory.expert_tensor_count != 456
        || inventory.logical_object_count != 19_532
        || inventory.expert_payload_bytes != 224_974_307_328
    {
        return Err(err("inventory authority mismatch"));
    }
    let admission: Admission = serde_json::from_slice(&fs::read(&cfg.admission_path)?)?;
    if admission.schema != "pulsarmlx-checkpoint-admission-v3"
        || admission.checkpoint_set_sha256 != CHECKPOINT_EXPECTED
        || admission.inventory_sha256 != INVENTORY_EXPECTED
        || admission.total_bytes != 238_458_632_928
        || admission.shards.len() != 6
        || expected_set_hash(&admission.shards) != CHECKPOINT_EXPECTED
    {
        return Err(err("checkpoint admission mismatch"));
    }
    for (position, (shard, expected)) in admission.shards.iter().zip(EXPECTED_SHARDS).enumerate() {
        if shard.index != position as u32 + 1
            || shard.name != expected.0
            || shard.size != expected.1
            || shard.sha256 != expected.2
            || shard.destination_stat.size != shard.size
        {
            return Err(err(format!("checkpoint shard authority mismatch at {}", position + 1)));
        }
        let path = cfg.checkpoint_dir.join(&shard.name);
        let (_file, got) = open_source(&path)?;
        if got != shard.destination_stat {
            return Err(err(format!("source stat changed: {}", shard.name)));
        }
        decode_hex_32(&shard.sha256)?;
    }
    Ok((inventory, admission, inventory_sha))
}

fn build_plans(
    inventory: &Inventory,
    admission: &Admission,
    scope: &[ScopeLayer],
) -> Result<Vec<ObjectPlan>> {
    let mut inventoried = BTreeMap::<(u32, String, u32), &InventoryObject>::new();
    for object in &inventory.objects {
        let key = (object.layer, object.expert_class.clone(), object.expert);
        if inventoried.insert(key, object).is_some() {
            return Err(err(format!(
                "duplicate inventory object layer {} {} expert {}",
                object.layer, object.expert_class, object.expert
            )));
        }
    }
    let shard_map: BTreeMap<&str, (u32, &AdmissionShard)> = admission
        .shards
        .iter()
        .enumerate()
        .map(|(i, s)| (s.name.as_str(), (i as u32 + 1, s)))
        .collect();
    let mut objects = Vec::new();
    for layer in scope {
        for (class, ids) in [
            ("routed", layer.routed.clone()),
            ("shared", if layer.shared { vec![0] } else { vec![] }),
        ] {
            for expert in ids {
                let object = inventoried
                    .get(&(layer.layer, class.to_string(), expert))
                    .ok_or_else(|| {
                        err(format!(
                            "missing inventory object layer {} {class} expert {expert}",
                            layer.layer
                        ))
                    })?;
                let mut role_counts = [0u32; 3];
                let mut unknown_roles = BTreeSet::new();
                for component in &object.components {
                    match component.role.as_str() {
                        "gate" => role_counts[0] += 1,
                        "up" => role_counts[1] += 1,
                        "down" => role_counts[2] += 1,
                        other => {
                            unknown_roles.insert(other);
                        }
                    }
                }
                if let Some(role) = unknown_roles.first() {
                    return Err(err(format!(
                        "unknown component role layer {} {class} expert {expert} {role}",
                        layer.layer
                    )));
                }
                for (role, count) in ["gate", "up", "down"].into_iter().zip(role_counts) {
                    if count != 1 {
                        let category = if count == 0 { "missing" } else { "duplicate" };
                        return Err(err(format!(
                            "{category} component role layer {} {class} expert {expert} {role}",
                            layer.layer
                        )));
                    }
                }
                let mut components = Vec::new();
                let mut next_offset = HEADER_LEN;
                for role in ["gate", "up", "down"] {
                    let t = object
                        .components
                        .iter()
                        .find(|component| component.role == role)
                        .ok_or_else(|| {
                            err(format!(
                                "missing component layer {} {class} expert {expert} {role}",
                                layer.layer
                            ))
                        })?;
                    if t.dims.len() != 2 {
                        return Err(err(format!("bad component geometry {}", t.tensor)));
                    }
                    let mut source_dims = t.dims.clone();
                    if class == "routed" {
                        source_dims.push(256);
                    }
                    if t.dims[0] % t.type_block_elements != 0
                        || t.plane_bytes % t.type_block_bytes != 0
                    {
                        return Err(err(format!("quantization split {}", t.tensor)));
                    }
                    let source_offset = t.data_offset_abs;
                    let end = checked_add(source_offset, t.plane_bytes, "source component end")?;
                    if end != t.data_end_abs {
                        return Err(err(format!("component outside tensor {}", t.tensor)));
                    }
                    let (ordinal, shard) = shard_map
                        .get(t.shard.as_str())
                        .ok_or_else(|| err(format!("inventory shard not admitted: {}", t.shard)))?;
                    if end > shard.size {
                        return Err(err(format!("component outside shard {}", t.shard)));
                    }
                    let bundle_offset = align_up(next_offset, FORMAT_ALIGNMENT)?;
                    let end_bundle = checked_add(bundle_offset, t.plane_bytes, "bundle component end")?;
                    let next_aligned = align_up(end_bundle, FORMAT_ALIGNMENT)?;
                    components.push(ComponentPlan {
                        role: role.to_string(),
                        tensor: t.tensor.clone(),
                        shard: t.shard.clone(),
                        shard_ordinal: *ordinal,
                        shard_sha256: shard.sha256.clone(),
                        source_stat: shard.destination_stat.clone(),
                        source_offset,
                        length: t.plane_bytes,
                        type_id: type_id(&t.gguf_type)?,
                        type_name: t.gguf_type.clone(),
                        dims: source_dims,
                        block_elements: t.type_block_elements,
                        block_bytes: t.type_block_bytes,
                        row_bytes: t.row_bytes,
                        plane_bytes: t.plane_bytes,
                        bundle_offset,
                        padding_after: next_aligned - end_bundle,
                    });
                    next_offset = next_aligned;
                }
                let relative_path = PathBuf::from(format!(
                    "objects/layer-{:03}/{class}/expert-{expert:03}.pmlxexp",
                    layer.layer
                ));
                safe_relative(&relative_path)?;
                objects.push(ObjectPlan {
                    layer: layer.layer,
                    expert,
                    expert_class: class.to_string(),
                    relative_path,
                    components,
                });
            }
        }
    }
    objects.sort_by_key(|o| (o.layer, if o.expert_class == "routed" { 0 } else { 1 }, o.expert));
    let mut seen = BTreeSet::new();
    for o in &objects {
        if !seen.insert((o.layer, o.expert_class.clone(), o.expert)) {
            return Err(err("duplicate object plan"));
        }
    }
    Ok(objects)
}

fn scope_json(scope: &[ScopeLayer]) -> Value {
    Value::Array(
        scope
            .iter()
            .map(|s| json!({"layer":s.layer,"routed_experts":s.routed,"shared":s.shared}))
            .collect(),
    )
}

fn plan_component_json(c: &ComponentPlan) -> Value {
    json!({
        "block_bytes":c.block_bytes,"block_elements":c.block_elements,"dims":c.dims,
        "length":c.length,"role":c.role,"row_bytes":c.row_bytes,
        "source_length":c.length,"source_offset":c.source_offset,
        "source_shard":c.shard,"source_shard_ordinal":c.shard_ordinal,
        "tensor":c.tensor,"type_id":c.type_id,"type_name":c.type_name
    })
}

fn plan_projection(
    inventory_sha: &str,
    objects: &[ObjectPlan],
    scope: &[ScopeLayer],
) -> Value {
    let records: Vec<Value> = objects
        .iter()
        .map(|o| {
            json!({
                "class":o.expert_class,"components":o.components.iter().map(plan_component_json).collect::<Vec<_>>(),
                "expert":o.expert,"layer":o.layer,
                "relative_path":o.relative_path.to_string_lossy()
            })
        })
        .collect();
    json!({
        "alignment":FORMAT_ALIGNMENT,"architecture":"glm-dsa",
        "checkpoint_set_sha256":CHECKPOINT_EXPECTED,"format_major":1,"format_minor":0,
        "inventory_sha256":inventory_sha,"objects":records,"ordering":"layer,class,expert",
        "schema":"pulsarmlx.r001.manifest-plan.v1","scope":scope_json(scope)
    })
}

fn layout_projection(o: &ObjectPlan, c: &ComponentPlan) -> Value {
    json!({
        "architecture":"glm-dsa","block_bytes":c.block_bytes,"block_elements":c.block_elements,
        "dims":c.dims,"expert_class":o.expert_class,"plane_bytes":c.plane_bytes,
        "role":c.role,"row_bytes":c.row_bytes,"schema":"pulsarmlx.r001.layout.v1",
        "type_id":c.type_id,"type_name":c.type_name
    })
}

fn object_identity_projection(
    o: &ObjectPlan,
    inventory_sha: &str,
    plan_id: &str,
    payload_sha: &str,
    components: &[Value],
) -> Value {
    json!({
        "architecture":"glm-dsa","canonical_payload_sha256":payload_sha,
        "checkpoint_set_sha256":CHECKPOINT_EXPECTED,"components":components,
        "expert":o.expert,"expert_class":o.expert_class,"inventory_sha256":inventory_sha,
        "layer":o.layer,"manifest_plan_id":plan_id,
        "schema":"pulsarmlx.r001.object-identity.v1"
    })
}

fn read_exact_at(file: &File, mut out: &mut [u8], mut offset: u64) -> Result<()> {
    while !out.is_empty() {
        let got = file.read_at(out, offset)?;
        if got == 0 {
            return Err(err(format!("short positional read at {offset}")));
        }
        offset = checked_add(offset, got as u64, "read offset")?;
        out = &mut out[got..];
    }
    Ok(())
}

fn write_exact_at(file: &File, mut input: &[u8], mut offset: u64) -> Result<()> {
    while !input.is_empty() {
        let wrote = file.write_at(input, offset)?;
        if wrote == 0 {
            return Err(err(format!("short positional write at {offset}")));
        }
        offset = checked_add(offset, wrote as u64, "write offset")?;
        input = &input[wrote..];
    }
    Ok(())
}

fn role_code(role: &str) -> Result<u8> {
    Ok(match role {
        "gate" => 1,
        "up" => 2,
        "down" => 3,
        _ => return Err(err(format!("bad role {role}"))),
    })
}

fn put_u16(dst: &mut [u8], off: usize, value: u16) {
    dst[off..off + 2].copy_from_slice(&value.to_le_bytes());
}
fn put_u32(dst: &mut [u8], off: usize, value: u32) {
    dst[off..off + 4].copy_from_slice(&value.to_le_bytes());
}
fn put_u64(dst: &mut [u8], off: usize, value: u64) {
    dst[off..off + 8].copy_from_slice(&value.to_le_bytes());
}
fn get_u16(src: &[u8], off: usize) -> u16 {
    u16::from_le_bytes(src[off..off + 2].try_into().unwrap())
}
fn get_u32(src: &[u8], off: usize) -> u32 {
    u32::from_le_bytes(src[off..off + 4].try_into().unwrap())
}
fn get_u64(src: &[u8], off: usize) -> u64 {
    u64::from_le_bytes(src[off..off + 8].try_into().unwrap())
}

fn sync_dir(path: &Path) -> Result<()> {
    File::open(path)?.sync_all()?;
    Ok(())
}

fn nonce_hex() -> Result<String> {
    let mut b = [0u8; 16];
    File::open("/dev/urandom")?.read_exact(&mut b)?;
    Ok(hex(&b))
}

fn validate_partial_nonce(payload_name: &str, prefix: &str, nonce: &str) -> Result<()> {
    if nonce.len() != 32
        || !nonce.bytes().all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
        || payload_name != format!("{prefix}{nonce}")
    {
        return Err(err("invalid or mismatched partial nonce"));
    }
    Ok(())
}

fn prepare_abandoned_root(staging_root: &Path) -> Result<PathBuf> {
    fs::create_dir_all(staging_root)?;
    let staging_metadata = fs::symlink_metadata(staging_root)?;
    if staging_metadata.file_type().is_symlink() || !staging_metadata.is_dir() {
        return Err(err("staging root must be a real directory"));
    }
    let canonical_staging = fs::canonicalize(staging_root)?;
    let abandoned = staging_root.join("abandoned");
    match fs::symlink_metadata(&abandoned) {
        Ok(metadata) => {
            if metadata.file_type().is_symlink() || !metadata.is_dir() {
                return Err(err("abandoned root must be a real directory"));
            }
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => fs::create_dir(&abandoned)?,
        Err(error) => return Err(error.into()),
    }
    let canonical_abandoned = fs::canonicalize(&abandoned)?;
    if canonical_abandoned.parent() != Some(canonical_staging.as_path()) {
        return Err(err("abandoned root escaped canonical staging root"));
    }
    Ok(canonical_abandoned)
}

fn exclusive_publish(temp: &Path, final_path: &Path) -> Result<()> {
    if final_path.exists() {
        return Err(err(format!("refuse existing final {}", final_path.display())));
    }
    fs::hard_link(temp, final_path)?;
    sync_dir(final_path.parent().ok_or_else(|| err("final has no parent"))?)?;
    fs::remove_file(temp)?;
    sync_dir(final_path.parent().unwrap())?;
    Ok(())
}

fn partial_sidecar(
    o: &ObjectPlan,
    inventory_sha: &str,
    plan_id: &str,
    nonce: &str,
    partial_name: &str,
    final_name: &str,
) -> Value {
    let uid = unsafe { libc::getuid() } as u64;
    let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs();
    json!({
        "binary_version":env!("CARGO_PKG_VERSION"),"checkpoint_set_sha256":CHECKPOINT_EXPECTED,
        "created_utc":now,"final_basename":final_name,"inventory_sha256":inventory_sha,
        "lease_nonce_hex":nonce,"manifest_plan_id":plan_id,
        "object_key":format!("{}:{}:{}",o.layer,o.expert_class,o.expert),
        "partial_basename":partial_name,"schema":"r001.partial-owner.v1","uid_decimal":uid
    })
}

fn quarantine_partials(
    cfg: &RepackConfig,
    o: &ObjectPlan,
    parent: &Path,
    final_name: &str,
    inventory_sha: &str,
    plan_id: &str,
) -> Result<()> {
    let prefix = format!("{final_name}.partial.");
    let mut payloads = Vec::new();
    let mut sidecars = BTreeSet::new();
    for entry in fs::read_dir(parent)? {
        let entry = entry?;
        let name = entry.file_name().to_string_lossy().to_string();
        if name.starts_with(&prefix) {
            if name.ends_with(".owner.json") {
                sidecars.insert(name);
            } else {
                payloads.push(name);
            }
        }
    }
    if payloads.is_empty() && sidecars.is_empty() {
        return Ok(());
    }
    if !cfg.resume {
        return Err(err("partial state exists; explicit --resume is required"));
    }
    if payloads.len() != 1 {
        return Err(err("ambiguous partial payload state"));
    }
    let payload_name = &payloads[0];
    let sidecar_name = format!("{payload_name}.owner.json");
    if sidecars != BTreeSet::from([sidecar_name.clone()]) {
        return Err(err("partial payload/sidecar set is incomplete or unexplained"));
    }
    let payload = parent.join(payload_name);
    let sidecar = parent.join(&sidecar_name);
    let uid = unsafe { libc::getuid() };
    for path in [&payload, &sidecar] {
        let m = fs::symlink_metadata(path)?;
        if m.file_type().is_symlink() || !m.is_file() || m.nlink() != 1 || m.uid() != uid {
            return Err(err(format!("unsafe partial ownership: {}", path.display())));
        }
    }
    let sidecar_bytes = fs::read(&sidecar)?;
    let claim: Value = serde_json::from_slice(&sidecar_bytes)?;
    if canonical_json(&claim)? != sidecar_bytes
        || claim["schema"] != "r001.partial-owner.v1"
        || claim["checkpoint_set_sha256"] != CHECKPOINT_EXPECTED
        || claim["inventory_sha256"] != inventory_sha
        || claim["manifest_plan_id"] != plan_id
        || claim["object_key"] != format!("{}:{}:{}", o.layer, o.expert_class, o.expert)
        || claim["partial_basename"] != payload_name.as_str()
        || claim["final_basename"] != final_name
        || claim["uid_decimal"] != uid as u64
    {
        return Err(err("partial owner claim mismatch"));
    }
    let nonce = claim["lease_nonce_hex"].as_str().ok_or_else(|| err("partial nonce missing"))?;
    validate_partial_nonce(payload_name, &prefix, nonce)?;
    let abandoned_root = prepare_abandoned_root(&cfg.staging_root)?;
    let abandoned = abandoned_root.join(nonce);
    if abandoned.parent() != Some(abandoned_root.as_path()) {
        return Err(err("abandoned partial escaped staging root"));
    }
    fs::create_dir(&abandoned)?;
    let dst_payload = abandoned.join(payload_name);
    let dst_sidecar = abandoned.join(sidecar_name);
    if dst_payload.exists() || dst_sidecar.exists() {
        return Err(err("abandoned partial destination already exists"));
    }
    fs::hard_link(&payload, &dst_payload)?;
    fs::hard_link(&sidecar, &dst_sidecar)?;
    sync_dir(&abandoned)?;
    fs::remove_file(&payload)?;
    fs::remove_file(&sidecar)?;
    sync_dir(parent)?;
    Ok(())
}

fn verify_existing_source_mapping(
    cfg: &RepackConfig,
    path: &Path,
    o: &ObjectPlan,
    metadata: &Value,
) -> Result<()> {
    let claims = metadata["components"].as_array().ok_or_else(|| err("missing components"))?;
    if claims.len() != o.components.len() {
        return Err(err("existing component count mismatch"));
    }
    let bundle = File::open(path)?;
    let mut source_buf = vec![0u8; CHUNK];
    let mut bundle_buf = vec![0u8; CHUNK];
    for (claim, c) in claims.iter().zip(&o.components) {
        if claim["role"] != c.role
            || claim["tensor"] != c.tensor
            || claim["bundle_offset"] != c.bundle_offset
            || claim["length"] != c.length
            || claim["source"]["shard"] != c.shard
            || claim["source"]["offset"] != c.source_offset
            || claim["source"]["length"] != c.length
        {
            return Err(err("existing final does not match current plan"));
        }
        let (source, source_stat) = open_source(&cfg.checkpoint_dir.join(&c.shard))?;
        if source_stat != c.source_stat {
            return Err(err("admitted source identity changed"));
        }
        let mut done = 0u64;
        while done < c.length {
            let n = (c.length - done).min(CHUNK as u64) as usize;
            read_exact_at(&source, &mut source_buf[..n], c.source_offset + done)?;
            read_exact_at(&bundle, &mut bundle_buf[..n], c.bundle_offset + done)?;
            if source_buf[..n] != bundle_buf[..n] {
                return Err(err("existing final source-byte mismatch"));
            }
            done += n as u64;
        }
    }
    Ok(())
}

fn component_identity_json(
    c: &ComponentPlan,
    component_sha: &str,
    layout_sha: &str,
) -> Value {
    json!({
        "block_bytes":c.block_bytes,"block_elements":c.block_elements,
        "bundle_offset":c.bundle_offset,"component_sha256":component_sha,"dims":c.dims,
        "layout_class_sha256":layout_sha,"length":c.length,"role":c.role,
        "row_bytes":c.row_bytes,
        "source":{"length":c.length,"offset":c.source_offset,"sha256":component_sha,
            "shard":c.shard,"shard_ordinal":c.shard_ordinal,"shard_sha256":c.shard_sha256},
        "tensor":c.tensor,"type_id":c.type_id,"type_name":c.type_name
    })
}

fn full_hash(path: &Path) -> Result<String> {
    let mut h = Sha256::new();
    let mut f = File::open(path)?;
    let mut buf = vec![0u8; CHUNK];
    loop {
        let n = f.read(&mut buf)?;
        if n == 0 {
            break;
        }
        h.update(&buf[..n]);
    }
    Ok(hex(&h.finalize()))
}

fn write_bundle(
    cfg: &RepackConfig,
    o: &ObjectPlan,
    inventory_sha: &str,
    plan_id: &str,
) -> Result<CompleteObject> {
    let test_interrupt_after = cfg.test_interrupt_after_bytes;
    let final_path = cfg.output_root.join(&o.relative_path);
    safe_relative(&o.relative_path)?;
    if final_path.exists() {
        let verified = verify_bundle(&final_path)?;
        if verified["manifest_plan_id"] != plan_id
            || verified["layer"] != o.layer
            || verified["expert"] != o.expert
            || verified["expert_class"] != o.expert_class
        {
            return Err(err(format!("existing final conflicts: {}", final_path.display())));
        }
        verify_existing_source_mapping(cfg, &final_path, o, &verified)?;
        let metadata = verified;
        let stored_len = final_path.metadata()?.len();
        return Ok(CompleteObject {
            plan: o.clone(),
            stored_sha256: full_hash(&final_path)?,
            canonical_payload_len: metadata["canonical_payload_len"].as_u64().unwrap(),
            canonical_payload_sha256: metadata["canonical_payload_sha256"].as_str().unwrap().to_string(),
            object_identity_sha256: metadata["object_identity_sha256"].as_str().unwrap().to_string(),
            metadata,
            stored_len,
            reused: true,
        });
    }
    let parent = final_path.parent().ok_or_else(|| err("bundle has no parent"))?;
    fs::create_dir_all(parent)?;
    let final_name = final_path.file_name().unwrap().to_string_lossy().to_string();
    quarantine_partials(cfg, o, parent, &final_name, inventory_sha, plan_id)?;
    let nonce = nonce_hex()?;
    let partial_name = format!("{final_name}.partial.{nonce}");
    let partial = parent.join(&partial_name);
    let sidecar = parent.join(format!("{partial_name}.owner.json"));
    let sidecar_tmp = parent.join(format!("{partial_name}.owner.json.tmp"));
    let sidecar_bytes = canonical_json(&partial_sidecar(
        o,
        inventory_sha,
        plan_id,
        &nonce,
        &partial_name,
        &final_name,
    ))?;
    let mut sf = OpenOptions::new().write(true).create_new(true).open(&sidecar_tmp)?;
    sf.write_all(&sidecar_bytes)?;
    sf.sync_all()?;
    drop(sf);
    exclusive_publish(&sidecar_tmp, &sidecar)?;

    let mut out = OpenOptions::new().read(true).write(true).create_new(true).open(&partial)?;
    out.write_all(&vec![0u8; HEADER_LEN as usize])?;
    let mut payload_hash = Sha256::new();
    payload_hash.update(b"PULSARMLX-R001-CANONICAL-PAYLOAD-V1");
    payload_hash.update([0]);
    let mut physical_hash = Sha256::new();
    let mut complete_components = Vec::new();
    let mut cursor = HEADER_LEN;
    let mut total_copied = 0u64;
    let mut buffer = vec![0u8; CHUNK];
    for c in &o.components {
        if cursor < c.bundle_offset {
            let zeros = vec![0u8; (c.bundle_offset - cursor) as usize];
            out.write_all(&zeros)?;
            physical_hash.update(&zeros);
            cursor = c.bundle_offset;
        }
        payload_hash.update([role_code(&c.role)?]);
        payload_hash.update(c.length.to_le_bytes());
        let source_path = cfg.checkpoint_dir.join(&c.shard);
        let (source, before) = open_source(&source_path)?;
        if before != c.source_stat {
            return Err(err(format!("source identity changed: {}", c.shard)));
        }
        let mut ch = Sha256::new();
        let mut copied = 0u64;
        while copied < c.length {
            let want = (c.length - copied).min(buffer.len() as u64) as usize;
            read_exact_at(&source, &mut buffer[..want], c.source_offset + copied)?;
            out.write_all(&buffer[..want])?;
            ch.update(&buffer[..want]);
            payload_hash.update(&buffer[..want]);
            physical_hash.update(&buffer[..want]);
            copied += want as u64;
            total_copied = checked_add(total_copied, want as u64, "test interruption counter")?;
            if test_interrupt_after.is_some_and(|limit| total_copied >= limit) {
                return Err(err("injected R001 test interruption"));
            }
        }
        let after = stat_from_metadata(&source.metadata()?);
        if before != after {
            return Err(err(format!("source changed during copy: {}", c.shard)));
        }
        cursor = checked_add(cursor, c.length, "output cursor")?;
        if c.padding_after > 0 {
            let zeros = vec![0u8; c.padding_after as usize];
            out.write_all(&zeros)?;
            physical_hash.update(&zeros);
            cursor += c.padding_after;
        }
        let component_sha = hex(&ch.finalize());
        let layout_sha = domain_hash(b"PULSARMLX-R001-LAYOUT-V1", &layout_projection(o, c))?;
        complete_components.push(component_identity_json(c, &component_sha, &layout_sha));
    }
    let footer_offset = align_up(cursor, FORMAT_ALIGNMENT)?;
    if footer_offset > cursor {
        let zeros = vec![0u8; (footer_offset - cursor) as usize];
        out.write_all(&zeros)?;
        physical_hash.update(&zeros);
    }
    let payload_sha = hex(&payload_hash.finalize());
    let physical_sha = hex(&physical_hash.finalize());
    let payload_len = o.components.iter().try_fold(0u64, |a, c| checked_add(a, c.length, "payload length"))?;
    let physical_len = footer_offset - HEADER_LEN;
    let file_len = checked_add(footer_offset, FOOTER_LEN, "file length")?;
    let object_projection = object_identity_projection(o, inventory_sha, plan_id, &payload_sha, &complete_components);
    let object_id = domain_hash(b"PULSARMLX-R001-OBJECT-V1", &object_projection)?;
    let metadata = json!({
        "architecture":"glm-dsa","canonical_payload_len":payload_len,
        "canonical_payload_sha256":payload_sha,"checkpoint_set_sha256":CHECKPOINT_EXPECTED,
        "components":complete_components,"expert":o.expert,"expert_class":o.expert_class,
        "family":"pulsarmlx.r001.expert-bundle","file_len":file_len,
        "footer_offset":footer_offset,"format_major":1,"format_minor":0,
        "inventory_sha256":inventory_sha,"layer":o.layer,"manifest_plan_id":plan_id,
        "model_layout_id":"glm-dsa-ud-iq2_xxs-expert-plane-v1",
        "object_identity_sha256":object_id,"payload_alignment":FORMAT_ALIGNMENT,
        "physical_payload_region_len":physical_len,"schema":"pulsarmlx.r001.bundle-header.v1"
    });
    let metadata_bytes = canonical_json(&metadata)?;
    if metadata_bytes.len() > HEADER_LEN as usize - PREAMBLE_LEN {
        return Err(err("bundle metadata exceeds v1 header"));
    }
    let metadata_sha = Sha256::digest(&metadata_bytes);
    let mut header = vec![0u8; HEADER_LEN as usize];
    header[..8].copy_from_slice(HEADER_MAGIC);
    put_u16(&mut header, 8, 1);
    put_u16(&mut header, 10, 0);
    put_u32(&mut header, 12, PREAMBLE_LEN as u32);
    put_u32(&mut header, 16, HEADER_LEN as u32);
    put_u32(&mut header, 20, 0);
    put_u32(&mut header, 24, o.layer);
    put_u32(&mut header, 28, o.expert);
    put_u32(&mut header, 32, if o.expert_class == "routed" { 1 } else { 2 });
    put_u32(&mut header, 36, 3);
    put_u32(&mut header, 40, FORMAT_ALIGNMENT as u32);
    put_u32(&mut header, 44, 0);
    put_u64(&mut header, 48, payload_len);
    put_u64(&mut header, 56, physical_len);
    put_u64(&mut header, 64, footer_offset);
    put_u64(&mut header, 72, file_len);
    put_u64(&mut header, 80, metadata_bytes.len() as u64);
    header[88..120].copy_from_slice(&metadata_sha);
    header[PREAMBLE_LEN..PREAMBLE_LEN + metadata_bytes.len()].copy_from_slice(&metadata_bytes);
    write_exact_at(&out, &header, 0)?;
    let header_sha = Sha256::digest(&header);
    let mut footer = vec![0u8; FOOTER_LEN as usize];
    footer[..8].copy_from_slice(FOOTER_MAGIC);
    put_u16(&mut footer, 8, 1);
    put_u16(&mut footer, 10, 0);
    put_u32(&mut footer, 12, FOOTER_LEN as u32);
    put_u64(&mut footer, 16, file_len);
    footer[24..56].copy_from_slice(&header_sha);
    footer[56..88].copy_from_slice(&decode_hex_32(&physical_sha)?);
    footer[88..120].copy_from_slice(&decode_hex_32(&payload_sha)?);
    footer[120..152].copy_from_slice(&decode_hex_32(&object_id)?);
    let footer_self = Sha256::digest(&footer);
    footer[152..184].copy_from_slice(&footer_self);
    write_exact_at(&out, &footer, footer_offset)?;
    out.set_len(file_len)?;
    out.sync_all()?;
    drop(out);
    let verified = verify_bundle(&partial)?;
    if verified != metadata {
        return Err(err("internal bundle verification metadata mismatch"));
    }
    let stored_sha = full_hash(&partial)?;
    exclusive_publish(&partial, &final_path)?;
    fs::remove_file(&sidecar)?;
    sync_dir(parent)?;
    Ok(CompleteObject {
        plan: o.clone(),
        metadata,
        stored_len: file_len,
        stored_sha256: stored_sha,
        canonical_payload_len: payload_len,
        canonical_payload_sha256: payload_sha,
        object_identity_sha256: object_id,
        reused: false,
    })
}

pub fn verify_bundle(path: &Path) -> Result<Value> {
    let file = File::open(path)?;
    let actual_len = file.metadata()?.len();
    if actual_len < HEADER_LEN + FOOTER_LEN {
        return Err(err("bundle truncated before header/footer"));
    }
    let mut header = vec![0u8; HEADER_LEN as usize];
    read_exact_at(&file, &mut header, 0)?;
    if &header[..8] != HEADER_MAGIC
        || get_u16(&header, 8) != 1
        || get_u16(&header, 10) != 0
        || get_u32(&header, 12) != PREAMBLE_LEN as u32
        || get_u32(&header, 16) != HEADER_LEN as u32
        || get_u32(&header, 20) != 0
        || get_u32(&header, 36) != 3
        || get_u32(&header, 40) != FORMAT_ALIGNMENT as u32
        || get_u32(&header, 44) != 0
        || header[120..128].iter().any(|&b| b != 0)
    {
        return Err(err("invalid bundle preamble"));
    }
    let metadata_len = get_u64(&header, 80) as usize;
    if metadata_len > HEADER_LEN as usize - PREAMBLE_LEN {
        return Err(err("metadata length out of bounds"));
    }
    if header[PREAMBLE_LEN + metadata_len..].iter().any(|&b| b != 0) {
        return Err(err("nonzero header padding"));
    }
    let metadata_bytes = &header[PREAMBLE_LEN..PREAMBLE_LEN + metadata_len];
    if Sha256::digest(metadata_bytes).as_slice() != &header[88..120] {
        return Err(err("metadata hash mismatch"));
    }
    let metadata: Value = serde_json::from_slice(metadata_bytes)?;
    if canonical_json(&metadata)? != metadata_bytes {
        return Err(err("metadata is not canonical CJ-R001-1"));
    }
    let footer_offset = get_u64(&header, 64);
    let file_len = get_u64(&header, 72);
    if file_len != actual_len || file_len != footer_offset + FOOTER_LEN {
        return Err(err("bundle file length mismatch"));
    }
    let mut footer = vec![0u8; FOOTER_LEN as usize];
    read_exact_at(&file, &mut footer, footer_offset)?;
    if &footer[..8] != FOOTER_MAGIC
        || get_u16(&footer, 8) != 1
        || get_u16(&footer, 10) != 0
        || get_u32(&footer, 12) != FOOTER_LEN as u32
        || get_u64(&footer, 16) != file_len
        || footer[184..].iter().any(|&b| b != 0)
    {
        return Err(err("invalid footer"));
    }
    if Sha256::digest(&header).as_slice() != &footer[24..56] {
        return Err(err("header block hash mismatch"));
    }
    let mut footer_zero = footer.clone();
    footer_zero[152..184].fill(0);
    if Sha256::digest(&footer_zero).as_slice() != &footer[152..184] {
        return Err(err("footer self hash mismatch"));
    }
    let mut physical = Sha256::new();
    let mut offset = HEADER_LEN;
    let mut buf = vec![0u8; CHUNK];
    while offset < footer_offset {
        let n = (footer_offset - offset).min(buf.len() as u64) as usize;
        read_exact_at(&file, &mut buf[..n], offset)?;
        physical.update(&buf[..n]);
        offset += n as u64;
    }
    if physical.finalize().as_slice() != &footer[56..88] {
        return Err(err("physical payload hash mismatch"));
    }
    let components = metadata["components"].as_array().ok_or_else(|| err("missing components"))?;
    if components.len() != 3 {
        return Err(err("component count mismatch"));
    }
    let mut canonical = Sha256::new();
    canonical.update(b"PULSARMLX-R001-CANONICAL-PAYLOAD-V1");
    canonical.update([0]);
    let mut previous_end = HEADER_LEN;
    for (i, c) in components.iter().enumerate() {
        let expected_role = ["gate", "up", "down"][i];
        if c["role"] != expected_role {
            return Err(err("component order mismatch"));
        }
        let off = c["bundle_offset"].as_u64().ok_or_else(|| err("bad component offset"))?;
        let len = c["length"].as_u64().ok_or_else(|| err("bad component length"))?;
        if off % FORMAT_ALIGNMENT != 0 || off < previous_end || off + len > footer_offset {
            return Err(err("component bounds/alignment mismatch"));
        }
        if off > previous_end {
            let mut pad = vec![0u8; (off - previous_end) as usize];
            read_exact_at(&file, &mut pad, previous_end)?;
            if pad.iter().any(|&b| b != 0) {
                return Err(err("nonzero component padding"));
            }
        }
        canonical.update([role_code(expected_role)?]);
        canonical.update(len.to_le_bytes());
        let mut ch = Sha256::new();
        let mut copied = 0u64;
        while copied < len {
            let n = (len - copied).min(buf.len() as u64) as usize;
            read_exact_at(&file, &mut buf[..n], off + copied)?;
            ch.update(&buf[..n]);
            canonical.update(&buf[..n]);
            copied += n as u64;
        }
        if hex(&ch.finalize()) != c["component_sha256"].as_str().unwrap_or("") {
            return Err(err("component hash mismatch"));
        }
        previous_end = off + len;
    }
    let payload = canonical.finalize();
    if payload.as_slice() != &footer[88..120]
        || hex(&payload) != metadata["canonical_payload_sha256"].as_str().unwrap_or("")
    {
        return Err(err("canonical payload hash mismatch"));
    }
    if decode_hex_32(metadata["object_identity_sha256"].as_str().unwrap_or(""))?.as_slice()
        != &footer[120..152]
    {
        return Err(err("object identity/footer mismatch"));
    }
    let projection = json!({
        "architecture":"glm-dsa","canonical_payload_sha256":metadata["canonical_payload_sha256"],
        "checkpoint_set_sha256":metadata["checkpoint_set_sha256"],"components":metadata["components"],
        "expert":metadata["expert"],"expert_class":metadata["expert_class"],
        "inventory_sha256":metadata["inventory_sha256"],"layer":metadata["layer"],
        "manifest_plan_id":metadata["manifest_plan_id"],"schema":"pulsarmlx.r001.object-identity.v1"
    });
    if domain_hash(b"PULSARMLX-R001-OBJECT-V1", &projection)?
        != metadata["object_identity_sha256"].as_str().unwrap_or("")
    {
        return Err(err("object identity projection mismatch"));
    }
    Ok(metadata)
}

fn manifest_object_record(c: &CompleteObject) -> Value {
    json!({
        "canonical_payload_len":c.canonical_payload_len,
        "canonical_payload_sha256":c.canonical_payload_sha256,
        "components":c.metadata["components"],"expert":c.plan.expert,
        "expert_class":c.plan.expert_class,"layer":c.plan.layer,
        "object_identity_sha256":c.object_identity_sha256,
        "record_type":"object","relative_path":c.plan.relative_path.to_string_lossy(),
        "stored_len":c.stored_len,"stored_sha256":c.stored_sha256
    })
}

fn publish_manifest(
    cfg: &RepackConfig,
    inventory_sha: &str,
    plan_id: &str,
    completed: &[CompleteObject],
) -> Result<String> {
    let header = json!({
        "alignment":FORMAT_ALIGNMENT,"architecture":"glm-dsa",
        "checkpoint_set_sha256":CHECKPOINT_EXPECTED,"format_major":1,"format_minor":0,
        "inventory_sha256":inventory_sha,"manifest_plan_id":plan_id,
        "object_count":completed.len() as u64,"ordering":"layer,class,expert",
        "record_type":"manifest_header","schema":"pulsarmlx.r001.completion-manifest.v1",
        "scope":scope_json(&cfg.scope)
    });
    let mut bytes = canonical_json(&header)?;
    bytes.push(b'\n');
    for object in completed {
        bytes.extend(canonical_json(&manifest_object_record(object))?);
        bytes.push(b'\n');
    }
    let preceding_sha = sha256_bytes(&bytes);
    let logical: u64 = completed.iter().map(|x| x.canonical_payload_len).sum();
    let stored: u64 = completed.iter().map(|x| x.stored_len).sum();
    let footer = json!({
        "logical_payload_bytes":logical,"object_count":completed.len() as u64,
        "preceding_records_sha256":preceding_sha,"record_type":"manifest_footer",
        "routed_count":completed.iter().filter(|x|x.plan.expert_class=="routed").count() as u64,
        "shared_count":completed.iter().filter(|x|x.plan.expert_class=="shared").count() as u64,
        "stored_bytes":stored
    });
    bytes.extend(canonical_json(&footer)?);
    bytes.push(b'\n');
    let manifest_sha = sha256_bytes(&bytes);
    let final_path = cfg.output_root.join("manifest.jsonl");
    let detached = cfg.output_root.join("manifest.jsonl.sha256");
    let detached_bytes = format!("{manifest_sha}\n").into_bytes();
    if final_path.exists() {
        if fs::read(&final_path)? != bytes {
            return Err(err("existing completion manifest conflicts"));
        }
        if detached.exists() {
            if fs::read(&detached)? != detached_bytes {
                return Err(err("existing detached manifest hash conflicts"));
            }
        } else {
            let nonce = nonce_hex()?;
            let temp_hash = cfg.output_root.join(format!("manifest.jsonl.sha256.partial.{nonce}"));
            let mut hf = OpenOptions::new().write(true).create_new(true).open(&temp_hash)?;
            hf.write_all(&detached_bytes)?;
            hf.sync_all()?;
            drop(hf);
            exclusive_publish(&temp_hash, &detached)?;
        }
        return Ok(manifest_sha);
    }
    fs::create_dir_all(&cfg.output_root)?;
    let nonce = nonce_hex()?;
    let temp = cfg.output_root.join(format!("manifest.jsonl.partial.{nonce}"));
    let mut f = OpenOptions::new().write(true).create_new(true).open(&temp)?;
    f.write_all(&bytes)?;
    f.sync_all()?;
    drop(f);
    exclusive_publish(&temp, &final_path)?;
    if cfg.test_interrupt_after_manifest {
        return Err(err("injected R001 test interruption after manifest publication"));
    }
    let temp_hash = cfg.output_root.join(format!("manifest.jsonl.sha256.partial.{nonce}"));
    let mut hf = OpenOptions::new().write(true).create_new(true).open(&temp_hash)?;
    hf.write_all(&detached_bytes)?;
    hf.sync_all()?;
    drop(hf);
    exclusive_publish(&temp_hash, &detached)?;
    Ok(manifest_sha)
}

fn peak_rss_bytes() -> u64 {
    let mut usage = unsafe { std::mem::zeroed::<libc::rusage>() };
    if unsafe { libc::getrusage(libc::RUSAGE_SELF, &mut usage) } != 0 {
        return 0;
    }
    #[cfg(target_os = "macos")]
    {
        usage.ru_maxrss as u64
    }
    #[cfg(not(target_os = "macos"))]
    {
        (usage.ru_maxrss as u64) * 1024
    }
}

pub fn inventory_summary(inventory_path: &Path) -> Result<Value> {
    let bytes = fs::read(inventory_path)?;
    let inventory: Inventory = serde_json::from_slice(&bytes)?;
    Ok(json!({
        "checkpoint_set_sha256":inventory.checkpoint_set_sha256,
        "expert_payload_bytes":inventory.expert_payload_bytes,
        "expert_tensor_count":inventory.expert_tensor_count,
        "inventory_sha256":sha256_bytes(&bytes),
        "logical_object_count":inventory.logical_object_count,
        "schema":inventory.schema,"status":"passed"
    }))
}

pub fn run_repack(cfg: &RepackConfig) -> Result<Value> {
    let started = SystemTime::now().duration_since(UNIX_EPOCH)?.as_secs();
    let t0 = Instant::now();
    let (inventory, admission, inventory_sha) = load_authority(cfg)?;
    let plans = build_plans(&inventory, &admission, &cfg.scope)?;
    let projection = plan_projection(&inventory_sha, &plans, &cfg.scope);
    let plan_id = domain_hash(b"PULSARMLX-R001-MANIFEST-PLAN-V1", &projection)?;
    if cfg.dry_run {
        return Ok(json!({
            "dry_run":true,"inventory_sha256":inventory_sha,"manifest_plan_id":plan_id,
            "object_count":plans.len() as u64,
            "payload_bytes":plans.iter().flat_map(|o|&o.components).map(|c|c.length).sum::<u64>(),
            "scope":scope_json(&cfg.scope),"status":"passed"
        }));
    }
    fs::create_dir_all(&cfg.output_root)?;
    fs::create_dir_all(&cfg.staging_root)?;
    let mut completed = Vec::with_capacity(plans.len());
    for (i, plan) in plans.iter().enumerate() {
        let c = write_bundle(cfg, plan, &inventory_sha, &plan_id)?;
        eprintln!(
            "pulsar-repack: {}/{} layer={} class={} expert={} reused={}",
            i + 1,
            plans.len(),
            plan.layer,
            plan.expert_class,
            plan.expert,
            c.reused
        );
        completed.push(c);
    }
    let manifest_sha = publish_manifest(cfg, &inventory_sha, &plan_id, &completed)?;
    let summary = json!({
        "checkpoint_set_sha256":CHECKPOINT_EXPECTED,"completed_unix_seconds":SystemTime::now().duration_since(UNIX_EPOCH)?.as_secs(),
        "duration_seconds":t0.elapsed().as_secs_f64().round() as u64,
        "inventory_sha256":inventory_sha,"manifest_plan_id":plan_id,
        "manifest_sha256":manifest_sha,"object_count":completed.len() as u64,
        "payload_bytes":completed.iter().map(|x|x.canonical_payload_len).sum::<u64>(),
        "peak_rss_bytes":peak_rss_bytes(),"reused_objects":completed.iter().filter(|x|x.reused).count() as u64,
        "r001_git_head":std::env::var("PULSARMLX_R001_GIT_HEAD").unwrap_or_else(|_|"UNSET".into()),
        "schema":"pulsarmlx.r001.repack-summary.v1","started_unix_seconds":started,
        "status":"passed","stored_bytes":completed.iter().map(|x|x.stored_len).sum::<u64>()
        ,"tool_version":env!("CARGO_PKG_VERSION")
    });
    if cfg.summary_path.exists() {
        return Err(err(format!("refuse existing summary {}", cfg.summary_path.display())));
    }
    let mut f = OpenOptions::new().write(true).create_new(true).open(&cfg.summary_path)?;
    f.write_all(&canonical_json(&summary)?)?;
    f.write_all(b"\n")?;
    f.sync_all()?;
    Ok(summary)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn canonical_known_answers() {
        let v = json!({"a":0,"b":"x\\\"","c":[1,true]});
        assert_eq!(
            String::from_utf8(canonical_json(&v).unwrap()).unwrap(),
            r#"{"a":0,"b":"x\\\"","c":[1,true]}"#
        );
        assert_eq!(sha256_bytes(&canonical_json(&v).unwrap()), "1dc821aa6759740ae41a6a3feb610416c797f785dd200bd508a0892173f68304");
        let layout = json!({"architecture":"glm-dsa","block_bytes":66,"block_elements":256,"dims":[6144,2048,256],"expert_class":"routed","plane_bytes":3244032,"role":"gate","row_bytes":1584,"schema":"pulsarmlx.r001.layout.v1","type_id":16,"type_name":"IQ2_XXS"});
        assert_eq!(domain_hash(b"PULSARMLX-R001-LAYOUT-V1", &layout).unwrap(), "765aa7eadd6d8503feebdc5726d19e32703161bb202e207044b9296d5dbecacf");
    }

    #[test]
    fn payload_known_answer() {
        let mut h = Sha256::new();
        h.update(b"PULSARMLX-R001-CANONICAL-PAYLOAD-V1");
        h.update([0]);
        for (role, bytes) in [(1u8, &[0u8, 1][..]), (2, &[2][..]), (3, &[3, 4, 5][..])] {
            h.update([role]);
            h.update((bytes.len() as u64).to_le_bytes());
            h.update(bytes);
        }
        assert_eq!(hex(&h.finalize()), "767a766d738dd34c2012ac9ec96a10908edefdff30805a6355901544313668d7");
    }

    #[test]
    fn plan_known_answer() {
        let value = json!({"alignment":16384,"architecture":"glm-dsa","checkpoint_set_sha256":"0000000000000000000000000000000000000000000000000000000000000000","format_major":1,"format_minor":0,"inventory_sha256":"1111111111111111111111111111111111111111111111111111111111111111","objects":[],"ordering":"layer,class,expert","schema":"pulsarmlx.r001.manifest-plan.v1","scope":{"layers":[40],"shared":true}});
        assert_eq!(domain_hash(b"PULSARMLX-R001-MANIFEST-PLAN-V1", &value).unwrap(), "7cbae85aee9fcb77eae87af07705f4d291ed39cd16d91f4ecfa3194299446b35");
    }

    #[test]
    fn scope_is_sorted_and_bounded() {
        let s = parse_scope("40:*;3:255,0,37", true).unwrap();
        assert_eq!(s[0].layer, 3);
        assert_eq!(s[0].routed, vec![0, 37, 255]);
        assert_eq!(s[1].routed.len(), 256);
        assert!(parse_scope("3:256", true).is_err());
        assert!(parse_scope("3:0;3:1", true).is_err());
    }

    #[test]
    fn checked_arithmetic_fails_closed() {
        assert!(checked_add(u64::MAX, 1, "test").is_err());
        assert!(checked_mul(u64::MAX, 2, "test").is_err());
        assert!(align_up(u64::MAX, FORMAT_ALIGNMENT).is_err());
    }

    #[test]
    fn partial_nonce_is_lowercase_hex_and_bound_to_basename() {
        let nonce = "0123456789abcdef0123456789abcdef";
        let prefix = "expert-000.pmlxexp.partial.";
        assert!(validate_partial_nonce(&format!("{prefix}{nonce}"), prefix, nonce).is_ok());
        assert!(validate_partial_nonce(&format!("{prefix}{nonce}"), prefix, "../escape").is_err());
        assert!(validate_partial_nonce(&format!("{prefix}{nonce}"), prefix, "0123456789ABCDEF0123456789ABCDEF").is_err());
        assert!(validate_partial_nonce(&format!("{prefix}{nonce}"), prefix, "fedcba9876543210fedcba9876543210").is_err());
    }


    #[test]
    fn abandoned_root_symlink_is_rejected() {
        use std::os::unix::fs::symlink;
        let root = std::env::temp_dir().join(format!("r001-abandoned-root-test-{}", nonce_hex().unwrap()));
        let staging = root.join("staging");
        let outside = root.join("outside");
        fs::create_dir_all(&staging).unwrap();
        fs::create_dir(&outside).unwrap();
        symlink(&outside, staging.join("abandoned")).unwrap();
        assert!(prepare_abandoned_root(&staging).is_err());
        assert!(outside.read_dir().unwrap().next().is_none());
        fs::remove_file(staging.join("abandoned")).unwrap();
        fs::remove_dir_all(root).unwrap();
    }

    fn synthetic_component(role: &str, shard: &str, offset: u64) -> InventoryComponent {
        InventoryComponent {
            role: role.to_string(),
            tensor: format!("synthetic.{role}.{offset}"),
            shard: shard.to_string(),
            gguf_type: "IQ2_XXS".to_string(),
            dims: vec![256, 1],
            type_block_elements: 256,
            type_block_bytes: 66,
            row_bytes: 66,
            plane_bytes: 66,
            data_offset_abs: offset,
            data_end_abs: offset + 66,
        }
    }

    fn synthetic_single_object() -> (Inventory, Admission, Vec<ScopeLayer>) {
        let shard = "synthetic-001.gguf";
        let object = InventoryObject {
            layer: 3,
            expert: 0,
            expert_class: "routed".to_string(),
            components: vec![
                synthetic_component("gate", shard, 0),
                synthetic_component("up", shard, 66),
                synthetic_component("down", shard, 132),
            ],
        };
        let inventory = Inventory {
            schema: "synthetic-r001-v1".to_string(),
            checkpoint_set_sha256: CHECKPOINT_EXPECTED.to_string(),
            architecture: "glm-dsa".to_string(),
            expert_tensor_count: 3,
            logical_object_count: 1,
            expert_payload_bytes: 198,
            objects: vec![object],
        };
        let admission = Admission {
            schema: "synthetic-admission-v1".to_string(),
            checkpoint_set_sha256: CHECKPOINT_EXPECTED.to_string(),
            inventory_sha256: "11".repeat(32),
            total_bytes: 264,
            shards: vec![AdmissionShard {
                index: 1,
                name: shard.to_string(),
                size: 264,
                sha256: "22".repeat(32),
                destination_stat: SourceStat {
                    device: 1,
                    size: 264,
                    mtime_ns: 1,
                    inode: 1,
                },
            }],
        };
        let scope = vec![ScopeLayer {
            layer: 3,
            routed: vec![0],
            shared: false,
        }];
        (inventory, admission, scope)
    }

    fn role_error(roles: &[&str]) -> String {
        let (mut inventory, admission, scope) = synthetic_single_object();
        let original = inventory.objects[0].components.clone();
        inventory.objects[0].components = roles
            .iter()
            .enumerate()
            .map(|(index, role)| {
                let mut component = original[index.min(original.len() - 1)].clone();
                component.role = (*role).to_string();
                component
            })
            .collect();
        build_plans(&inventory, &admission, &scope)
            .unwrap_err()
            .to_string()
    }

    #[test]
    fn build_plans_rejects_duplicate_gate_role() {
        assert_eq!(
            role_error(&["gate", "gate", "up", "down"]),
            "duplicate component role layer 3 routed expert 0 gate"
        );
    }

    #[test]
    fn build_plans_rejects_duplicate_up_role() {
        assert_eq!(
            role_error(&["gate", "up", "up", "down"]),
            "duplicate component role layer 3 routed expert 0 up"
        );
    }

    #[test]
    fn build_plans_rejects_duplicate_down_role() {
        assert_eq!(
            role_error(&["gate", "up", "down", "down"]),
            "duplicate component role layer 3 routed expert 0 down"
        );
    }

    #[test]
    fn build_plans_rejects_unknown_role_without_ignoring_it() {
        assert_eq!(
            role_error(&["gate", "up", "down", "other"]),
            "unknown component role layer 3 routed expert 0 other"
        );
    }

    #[test]
    fn build_plans_preserves_specific_missing_role_errors() {
        for (roles, missing) in [
            (&["up", "down"][..], "gate"),
            (&["gate", "down"][..], "up"),
            (&["gate", "up"][..], "down"),
        ] {
            assert_eq!(
                role_error(roles),
                format!("missing component role layer 3 routed expert 0 {missing}")
            );
        }
    }

    #[test]
    fn build_plans_valid_exact_roles_preserve_baseline_projection() {
        let (inventory, admission, scope) = synthetic_single_object();
        let plans = build_plans(&inventory, &admission, &scope).unwrap();
        assert_eq!(plans.len(), 1);
        assert_eq!(
            plans[0]
                .components
                .iter()
                .map(|component| component.role.as_str())
                .collect::<Vec<_>>(),
            ["gate", "up", "down"]
        );
        let expected = json!({
            "alignment":FORMAT_ALIGNMENT,"architecture":"glm-dsa",
            "checkpoint_set_sha256":CHECKPOINT_EXPECTED,"format_major":1,"format_minor":0,
            "inventory_sha256":"11".repeat(32),
            "objects":[{"class":"routed","components":[
                {"block_bytes":66,"block_elements":256,"dims":[256,1,256],"length":66,"role":"gate","row_bytes":66,"source_length":66,"source_offset":0,"source_shard":"synthetic-001.gguf","source_shard_ordinal":1,"tensor":"synthetic.gate.0","type_id":16,"type_name":"IQ2_XXS"},
                {"block_bytes":66,"block_elements":256,"dims":[256,1,256],"length":66,"role":"up","row_bytes":66,"source_length":66,"source_offset":66,"source_shard":"synthetic-001.gguf","source_shard_ordinal":1,"tensor":"synthetic.up.66","type_id":16,"type_name":"IQ2_XXS"},
                {"block_bytes":66,"block_elements":256,"dims":[256,1,256],"length":66,"role":"down","row_bytes":66,"source_length":66,"source_offset":132,"source_shard":"synthetic-001.gguf","source_shard_ordinal":1,"tensor":"synthetic.down.132","type_id":16,"type_name":"IQ2_XXS"}
            ],"expert":0,"layer":3,"relative_path":"objects/layer-003/routed/expert-000.pmlxexp"}],
            "ordering":"layer,class,expert","schema":"pulsarmlx.r001.manifest-plan.v1",
            "scope":[{"layer":3,"routed_experts":[0],"shared":false}]
        });
        assert_eq!(
            canonical_json(&plan_projection(&"11".repeat(32), &plans, &scope)).unwrap(),
            canonical_json(&expected).unwrap()
        );
    }

    fn synthetic_complete_authority() -> (Inventory, Admission, Vec<ScopeLayer>) {
        let shard_names: Vec<String> = (1..=6)
            .map(|index| format!("synthetic-{index:03}.gguf"))
            .collect();
        let mut offsets = [0u64; 6];
        let mut objects = Vec::with_capacity(19_532);
        let mut scope = Vec::with_capacity(76);
        for layer in 3..=78 {
            let shard_index = (layer - 3) as usize % shard_names.len();
            for (class, experts) in [("routed", 256u32), ("shared", 1u32)] {
                for expert in 0..experts {
                    let components = ["gate", "up", "down"]
                        .into_iter()
                        .map(|role| {
                            let offset = offsets[shard_index];
                            offsets[shard_index] += 66;
                            synthetic_component(role, &shard_names[shard_index], offset)
                        })
                        .collect();
                    objects.push(InventoryObject {
                        layer,
                        expert,
                        expert_class: class.to_string(),
                        components,
                    });
                }
            }
            scope.push(ScopeLayer {
                layer,
                routed: (0..256).collect(),
                shared: true,
            });
        }
        let shards = shard_names
            .into_iter()
            .enumerate()
            .map(|(index, name)| AdmissionShard {
                index: index as u32 + 1,
                name,
                size: offsets[index],
                sha256: format!("{:064x}", index + 1),
                destination_stat: SourceStat {
                    device: 1,
                    size: offsets[index],
                    mtime_ns: 1,
                    inode: index as u64 + 1,
                },
            })
            .collect::<Vec<_>>();
        let total_bytes = shards.iter().map(|shard| shard.size).sum();
        (
            Inventory {
                schema: "synthetic-r001-complete-v1".to_string(),
                checkpoint_set_sha256: CHECKPOINT_EXPECTED.to_string(),
                architecture: "glm-dsa".to_string(),
                expert_tensor_count: 456,
                logical_object_count: 19_532,
                expert_payload_bytes: total_bytes,
                objects,
            },
            Admission {
                schema: "synthetic-admission-v1".to_string(),
                checkpoint_set_sha256: CHECKPOINT_EXPECTED.to_string(),
                inventory_sha256: "33".repeat(32),
                total_bytes,
                shards,
            },
            scope,
        )
    }

    fn plan_identity(inventory_sha: &str, plans: &[ObjectPlan], scope: &[ScopeLayer]) -> String {
        domain_hash(
            b"PULSARMLX-R001-MANIFEST-PLAN-V1",
            &plan_projection(inventory_sha, plans, scope),
        )
        .unwrap()
    }

    fn require_plan_identity(
        expected: &str,
        inventory_sha: &str,
        plans: &[ObjectPlan],
        scope: &[ScopeLayer],
    ) -> Result<()> {
        if plan_identity(inventory_sha, plans, scope) != expected {
            return Err(err("manifest plan identity mismatch"));
        }
        Ok(())
    }

    #[test]
    fn complete_scope_is_deterministic_bounded_and_block_aligned() {
        let (inventory, admission, scope) = synthetic_complete_authority();
        let plans = build_plans(&inventory, &admission, &scope).unwrap();
        assert_eq!(plans.len(), 19_532);
        assert_eq!(
            plans.iter().map(|object| object.components.len()).sum::<usize>(),
            58_596
        );
        assert!(plans.windows(2).all(|pair| {
            let key = |object: &ObjectPlan| {
                (
                    object.layer,
                    if object.expert_class == "routed" { 0 } else { 1 },
                    object.expert,
                )
            };
            key(&pair[0]) < key(&pair[1])
        }));
        let mut ranges = BTreeMap::<&str, Vec<(u64, u64)>>::new();
        for object in &plans {
            assert_eq!(
                object
                    .components
                    .iter()
                    .map(|component| component.role.as_str())
                    .collect::<Vec<_>>(),
                ["gate", "up", "down"]
            );
            assert!(object
                .components
                .iter()
                .all(|component| component.shard == object.components[0].shard));
            for component in &object.components {
                let source_end = component.source_offset.checked_add(component.length).unwrap();
                let bundle_end = component.bundle_offset.checked_add(component.length).unwrap();
                assert!(source_end <= component.source_stat.size);
                assert_eq!(component.source_offset % component.block_bytes, 0);
                assert_eq!(component.length % component.block_bytes, 0);
                assert_eq!(component.bundle_offset % FORMAT_ALIGNMENT, 0);
                assert!(bundle_end <= align_up(bundle_end, FORMAT_ALIGNMENT).unwrap());
                ranges
                    .entry(&component.shard)
                    .or_default()
                    .push((component.source_offset, source_end));
            }
        }
        for shard_ranges in ranges.values_mut() {
            shard_ranges.sort_unstable();
            assert!(shard_ranges.windows(2).all(|pair| pair[0].1 <= pair[1].0));
        }
        let identity = plan_identity(&admission.inventory_sha256, &plans, &scope);
        assert_eq!(
            identity,
            "350ee7d581b425658f800c96cc877abdebd56e945a560d615ddfb38091b8f75a"
        );
        assert!(identity.bytes().all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte)));

        let (mut reordered_inventory, reordered_admission, reordered_scope) =
            synthetic_complete_authority();
        reordered_inventory.objects.reverse();
        for object in &mut reordered_inventory.objects {
            object.components.reverse();
        }
        let reordered = build_plans(
            &reordered_inventory,
            &reordered_admission,
            &reordered_scope,
        )
        .unwrap();
        assert_eq!(
            canonical_json(&plan_projection(
                &admission.inventory_sha256,
                &plans,
                &scope
            ))
            .unwrap(),
            canonical_json(&plan_projection(
                &reordered_admission.inventory_sha256,
                &reordered,
                &reordered_scope
            ))
            .unwrap()
        );
        assert_eq!(
            identity,
            plan_identity(
                &reordered_admission.inventory_sha256,
                &reordered,
                &reordered_scope
            )
        );
    }

    #[test]
    fn complete_scope_rejects_duplicate_object_keys() {
        let (mut inventory, admission, scope) = synthetic_single_object();
        inventory.objects.push(inventory.objects[0].clone());
        assert_eq!(
            build_plans(&inventory, &admission, &scope)
                .unwrap_err()
                .to_string(),
            "duplicate inventory object layer 3 routed expert 0"
        );
    }

    #[test]
    fn complete_scope_rejects_checked_source_overflow() {
        let (mut inventory, admission, scope) = synthetic_single_object();
        inventory.objects[0].components[0].data_offset_abs = u64::MAX;
        assert!(build_plans(&inventory, &admission, &scope)
            .unwrap_err()
            .to_string()
            .starts_with("overflow adding source component end"));
    }

    #[test]
    fn complete_scope_rejects_checked_bundle_alignment_overflow() {
        let (mut inventory, mut admission, scope) = synthetic_single_object();
        let length = u64::MAX - (u64::MAX % 66);
        let component = &mut inventory.objects[0].components[0];
        component.plane_bytes = length;
        component.data_end_abs = length;
        admission.shards[0].size = u64::MAX;
        admission.shards[0].destination_stat.size = u64::MAX;
        assert!(build_plans(&inventory, &admission, &scope)
            .unwrap_err()
            .to_string()
            .starts_with("overflow adding bundle component end"));
    }

    #[test]
    fn complete_scope_rejects_component_beyond_shard() {
        let (inventory, mut admission, scope) = synthetic_single_object();
        admission.shards[0].size = 65;
        admission.shards[0].destination_stat.size = 65;
        assert_eq!(
            build_plans(&inventory, &admission, &scope)
                .unwrap_err()
                .to_string(),
            "component outside shard synthetic-001.gguf"
        );
    }

    #[test]
    fn complete_scope_rejects_stale_identity_and_incorrect_order() {
        let (inventory, admission, scope) = synthetic_single_object();
        let plans = build_plans(&inventory, &admission, &scope).unwrap();
        let identity = plan_identity(&admission.inventory_sha256, &plans, &scope);
        assert!(require_plan_identity(&identity, &admission.inventory_sha256, &plans, &scope).is_ok());
        let mut mutated = plans.clone();
        mutated[0].components.swap(0, 1);
        assert_eq!(
            require_plan_identity(&identity, &admission.inventory_sha256, &mutated, &scope)
                .unwrap_err()
                .to_string(),
            "manifest plan identity mismatch"
        );
    }

    #[test]
    fn complete_scope_rejects_unsafe_relative_paths() {
        for path in ["/absolute", ".", "..", "objects/../escape", "./objects"] {
            assert!(safe_relative(Path::new(path)).is_err(), "accepted {path}");
        }
        assert!(safe_relative(Path::new("objects/layer-003/routed/expert-000.pmlxexp")).is_ok());
    }
}
