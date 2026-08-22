//! Exact six-shard, read-only checkpoint loader. Real use performs the full
//! shard rehash before attempt authority and maps each shard MAP_PRIVATE.

use crate::model::{Matrix, TensorSource};
use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fs::{self, File};
use std::io::Read;
use std::os::fd::AsRawFd;
use std::os::unix::fs::OpenOptionsExt;
use std::path::Path;

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ShardIdentity {
    pub filename: String,
    pub sha256: String,
    pub size_bytes: u64,
}

#[derive(Clone, Debug, Deserialize)]
pub struct CheckpointManifest {
    pub checkpoint_set_sha256: String,
    pub file_count: usize,
    pub total_bytes: u64,
    pub files: Vec<ShardIdentity>,
}

#[derive(Clone, Debug, Deserialize)]
pub struct TensorRecord {
    pub data_offset_abs: u64,
    pub dims: Vec<u64>,
    pub file: String,
    pub name: String,
    #[serde(rename = "type")]
    pub format: String,
    pub type_id: u32,
}

#[derive(Clone, Debug, Deserialize)]
pub struct TensorCatalog {
    pub architecture: String,
    pub kv_selected: BTreeMap<String, serde_json::Value>,
    pub tensor_count: usize,
    pub shard_count: usize,
    pub tensors: Vec<TensorRecord>,
}

pub fn load_plan_only(
    manifest_path: &Path,
    catalog_path: &Path,
) -> Result<(CheckpointManifest, TensorCatalog), String> {
    let manifest: CheckpointManifest = crate::json::parse_json_no_duplicates(
        &fs::read(manifest_path).map_err(|e| e.to_string())?,
    )?;
    let catalog: TensorCatalog =
        crate::json::parse_json_no_duplicates(&fs::read(catalog_path).map_err(|e| e.to_string())?)?;
    validate_plan(&manifest, &catalog)?;
    Ok((manifest, catalog))
}

pub fn validate_plan(manifest: &CheckpointManifest, catalog: &TensorCatalog) -> Result<(), String> {
    if manifest.file_count != 6
        || manifest.files.len() != 6
        || manifest.files.iter().map(|s| s.size_bytes).sum::<u64>() != manifest.total_bytes
        || manifest.checkpoint_set_sha256.len() != 64
        || catalog.shard_count != 6
        || catalog.tensor_count != 1809
        || catalog.tensors.len() != 1809
        || catalog.architecture != "glm-dsa"
    {
        return Err("checkpoint plan census".into());
    }
    let integer_metadata = [
        ("block_count", 79_u64),
        ("embedding_length", 6144),
        ("vocab_size", 154_880),
        ("feed_forward_length", 12_288),
        ("expert_count", 256),
        ("expert_used_count", 8),
        ("expert_feed_forward_length", 2048),
        ("attention.head_count", 64),
        ("attention.q_lora_rank", 2048),
        ("attention.kv_lora_rank", 512),
        ("attention.key_length_mla", 256),
        ("attention.value_length_mla", 256),
        ("rope.dimension_count", 64),
    ];
    if integer_metadata.iter().any(|(key, expected)| {
        catalog
            .kv_selected
            .get(*key)
            .and_then(|value| value.as_u64())
            != Some(*expected)
    }) || catalog
        .kv_selected
        .get("rope.freq_base")
        .and_then(|value| value.as_f64())
        != Some(8_000_000.0)
    {
        return Err("model metadata authority mismatch".into());
    }
    let files = manifest
        .files
        .iter()
        .map(|s| s.filename.as_str())
        .collect::<BTreeSet<_>>();
    let mut names = BTreeSet::<String>::new();
    let allowed = [
        "F32", "Q2_K", "Q3_K", "Q4_K", "Q5_K", "Q6_K", "Q8_0", "IQ2_S", "IQ2_XXS", "IQ3_XXS",
        "IQ4_XS",
    ];
    for tensor in &catalog.tensors {
        if !files.contains(tensor.file.as_str())
            || !names.insert(tensor.name.clone())
            || !allowed.contains(&tensor.format.as_str())
            || tensor.dims.is_empty()
            || tensor.dims.iter().any(|v| *v == 0)
        {
            return Err(format!("invalid tensor plan {}", tensor.name));
        }
    }
    for required in ["token_embd.weight", "output_norm.weight", "output.weight"] {
        if !names.contains(required) {
            return Err(format!("missing {required}"));
        }
    }
    let records = catalog
        .tensors
        .iter()
        .map(|tensor| (tensor.name.as_str(), tensor))
        .collect::<BTreeMap<_, _>>();
    let shape = |name: &str, expected: &[u64]| -> Result<(), String> {
        if records.get(name).map(|record| record.dims.as_slice()) != Some(expected) {
            return Err(format!("shape mismatch {name}"));
        }
        Ok(())
    };
    shape("token_embd.weight", &[6144, 154_880])?;
    shape("output_norm.weight", &[6144])?;
    shape("output.weight", &[6144, 154_880])?;
    for layer in 0..79 {
        for suffix in [
            "attn_norm.weight",
            "attn_q_a.weight",
            "attn_q_a_norm.weight",
            "attn_q_b.weight",
            "attn_kv_a_mqa.weight",
            "attn_kv_a_norm.weight",
            "attn_k_b.weight",
            "attn_v_b.weight",
            "attn_output.weight",
            "ffn_norm.weight",
        ] {
            let name = format!("blk.{layer}.{suffix}");
            if !names.contains(name.as_str()) {
                return Err(format!("missing {name}"));
            }
        }
        for (suffix, expected) in [
            ("attn_norm.weight", &[6144][..]),
            ("attn_q_a.weight", &[6144, 2048]),
            ("attn_q_a_norm.weight", &[2048]),
            ("attn_q_b.weight", &[2048, 16_384]),
            ("attn_kv_a_mqa.weight", &[6144, 576]),
            ("attn_kv_a_norm.weight", &[512]),
            ("attn_k_b.weight", &[192, 512, 64]),
            ("attn_v_b.weight", &[512, 256, 64]),
            ("attn_output.weight", &[16_384, 6144]),
            ("ffn_norm.weight", &[6144]),
        ] {
            shape(&format!("blk.{layer}.{suffix}"), expected)?;
        }
        if layer < 3 {
            for suffix in ["ffn_gate.weight", "ffn_up.weight", "ffn_down.weight"] {
                let name = format!("blk.{layer}.{suffix}");
                if !names.contains(name.as_str()) {
                    return Err(format!("missing {name}"));
                }
            }
            shape(&format!("blk.{layer}.ffn_gate.weight"), &[6144, 12_288])?;
            shape(&format!("blk.{layer}.ffn_up.weight"), &[6144, 12_288])?;
            shape(&format!("blk.{layer}.ffn_down.weight"), &[12_288, 6144])?;
        } else {
            for suffix in [
                "ffn_gate_inp.weight",
                "exp_probs_b.bias",
                "ffn_gate_exps.weight",
                "ffn_up_exps.weight",
                "ffn_down_exps.weight",
                "ffn_gate_shexp.weight",
                "ffn_up_shexp.weight",
                "ffn_down_shexp.weight",
            ] {
                let name = format!("blk.{layer}.{suffix}");
                if !names.contains(name.as_str()) {
                    return Err(format!("missing {name}"));
                }
            }
            shape(&format!("blk.{layer}.ffn_gate_inp.weight"), &[6144, 256])?;
            shape(&format!("blk.{layer}.exp_probs_b.bias"), &[256])?;
            shape(
                &format!("blk.{layer}.ffn_gate_exps.weight"),
                &[6144, 2048, 256],
            )?;
            shape(
                &format!("blk.{layer}.ffn_up_exps.weight"),
                &[6144, 2048, 256],
            )?;
            shape(
                &format!("blk.{layer}.ffn_down_exps.weight"),
                &[2048, 6144, 256],
            )?;
            shape(&format!("blk.{layer}.ffn_gate_shexp.weight"), &[6144, 2048])?;
            shape(&format!("blk.{layer}.ffn_up_shexp.weight"), &[6144, 2048])?;
            shape(&format!("blk.{layer}.ffn_down_shexp.weight"), &[2048, 6144])?;
        }
    }
    Ok(())
}

fn sha_file(path: &Path) -> Result<String, String> {
    let mut f = File::open(path).map_err(|e| e.to_string())?;
    let mut h = Sha256::new();
    let mut b = [0_u8; 1024 * 1024];
    loop {
        let n = f.read(&mut b).map_err(|e| e.to_string())?;
        if n == 0 {
            break;
        }
        h.update(&b[..n]);
    }
    Ok(format!("{:x}", h.finalize()))
}

struct MappedShard {
    _file: File,
    ptr: *mut libc::c_void,
    len: usize,
}
unsafe impl Send for MappedShard {}
impl Drop for MappedShard {
    fn drop(&mut self) {
        unsafe {
            libc::munmap(self.ptr, self.len);
        }
    }
}
impl MappedShard {
    fn open(path: &Path, expected: &ShardIdentity) -> Result<Self, String> {
        let meta = fs::symlink_metadata(path).map_err(|e| e.to_string())?;
        if meta.file_type().is_symlink() || !meta.is_file() || meta.len() != expected.size_bytes {
            return Err("unsafe shard".into());
        }
        if sha_file(path)? != expected.sha256 {
            return Err("shard hash".into());
        }
        let file = std::fs::OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW)
            .open(path)
            .map_err(|e| e.to_string())?;
        let len = usize::try_from(meta.len()).map_err(|_| "shard length")?;
        let ptr = unsafe {
            libc::mmap(
                std::ptr::null_mut(),
                len,
                libc::PROT_READ,
                libc::MAP_PRIVATE,
                file.as_raw_fd(),
                0,
            )
        };
        if ptr == libc::MAP_FAILED {
            return Err("mmap".into());
        }
        Ok(Self {
            _file: file,
            ptr,
            len,
        })
    }
    fn read(&self, offset: u64, len: usize) -> Result<&[u8], String> {
        let off = usize::try_from(offset).map_err(|_| "offset")?;
        let end = off.checked_add(len).ok_or("range")?;
        if end > self.len {
            return Err("range".into());
        }
        Ok(unsafe { std::slice::from_raw_parts((self.ptr as *const u8).add(off), len) })
    }
}

pub struct SecureCheckpoint {
    catalog: BTreeMap<String, TensorRecord>,
    shards: BTreeMap<String, MappedShard>,
    pub checkpoint_set_sha256: String,
}
impl SecureCheckpoint {
    pub fn open(
        root: &Path,
        manifest: CheckpointManifest,
        catalog: TensorCatalog,
    ) -> Result<Self, String> {
        validate_plan(&manifest, &catalog)?;
        let resolved = root.canonicalize().map_err(|e| e.to_string())?;
        if resolved != root {
            return Err("checkpoint root must be canonical absolute".into());
        }
        let meta = fs::symlink_metadata(root).map_err(|e| e.to_string())?;
        if meta.file_type().is_symlink() || !meta.is_dir() {
            return Err("checkpoint root".into());
        }
        let mut shards = BTreeMap::new();
        for expected in &manifest.files {
            let path = root.join(&expected.filename);
            shards.insert(
                expected.filename.clone(),
                MappedShard::open(&path, expected)?,
            );
        }
        // Every directory entry participates in the census. An extra
        // directory, socket, or symlink must not disappear merely because it
        // is not a regular file.
        let entries = fs::read_dir(root)
            .map_err(|e| e.to_string())?
            .map(|entry| {
                entry
                    .map(|e| e.file_name().to_string_lossy().into_owned())
                    .map_err(|e| e.to_string())
            })
            .collect::<Result<BTreeSet<_>, _>>()?;
        let expected = manifest
            .files
            .iter()
            .map(|s| s.filename.clone())
            .collect::<BTreeSet<_>>();
        if entries != expected {
            return Err("checkpoint root census".into());
        }
        Ok(Self {
            catalog: catalog
                .tensors
                .into_iter()
                .map(|t| (t.name.clone(), t))
                .collect(),
            shards,
            checkpoint_set_sha256: manifest.checkpoint_set_sha256,
        })
    }
    fn record(&self, name: &str) -> Result<&TensorRecord, String> {
        self.catalog
            .get(name)
            .ok_or_else(|| format!("missing tensor {name}"))
    }
    fn encoded(&self, record: &TensorRecord, expert: Option<usize>) -> Result<Vec<u8>, String> {
        let columns = usize::try_from(record.dims[0]).map_err(|_| "columns")?;
        let rows = usize::try_from(*record.dims.get(1).unwrap_or(&1)).map_err(|_| "rows")?;
        let ty = gguf::TensorType::from_id(record.type_id);
        let row_bytes = usize::try_from(ty.row_bytes(columns as u64).ok_or("format")?)
            .map_err(|_| "row bytes")?;
        let matrix_bytes = row_bytes.checked_mul(rows).ok_or("matrix bytes")?;
        let expert_offset = expert
            .map(|id| id.checked_mul(matrix_bytes).ok_or("expert offset"))
            .transpose()?
            .unwrap_or(0);
        if let Some(id) = expert {
            let count =
                usize::try_from(*record.dims.get(2).ok_or("not expert")?).map_err(|_| "experts")?;
            if id >= count {
                return Err("expert id".into());
            }
        }
        Ok(self
            .shards
            .get(&record.file)
            .ok_or("shard")?
            .read(record.data_offset_abs + expert_offset as u64, matrix_bytes)?
            .to_vec())
    }
}

fn decode(
    record: &TensorRecord,
    bytes: &[u8],
    rows: usize,
    columns: usize,
) -> Result<Vec<f32>, String> {
    let mut out = vec![0.0; rows.checked_mul(columns).ok_or("shape")?];
    match record.format.as_str() {
        "F32" => {
            if bytes.len() != out.len() * 4 {
                return Err("f32 bytes".into());
            }
            for (i, c) in bytes.chunks_exact(4).enumerate() {
                out[i] = f32::from_le_bytes(c.try_into().unwrap());
            }
        }
        "Q2_K" => {
            quant::decode_q2_k_matrix(bytes, rows, columns, &mut out).map_err(|e| e.to_string())?
        }
        "Q3_K" => {
            quant::decode_q3_k_matrix(bytes, rows, columns, &mut out).map_err(|e| e.to_string())?
        }
        "Q4_K" => {
            for (r, row) in bytes.chunks_exact(columns / 256 * 144).enumerate() {
                out[r * columns..(r + 1) * columns]
                    .copy_from_slice(&quant::cpu_dot::dequant_q4_k(row, columns));
            }
        }
        "Q5_K" => {
            for (r, row) in bytes.chunks_exact(columns / 256 * 176).enumerate() {
                out[r * columns..(r + 1) * columns]
                    .copy_from_slice(&quant::cpu_dot::dequant_q5_k(row, columns));
            }
        }
        "Q6_K" => {
            quant::decode_q6_k_matrix(bytes, rows, columns, &mut out).map_err(|e| e.to_string())?
        }
        "Q8_0" => {
            quant::decode_q8_0_matrix(bytes, rows, columns, &mut out).map_err(|e| e.to_string())?
        }
        "IQ2_S" => {
            quant::decode_iq2_s_matrix(bytes, rows, columns, &mut out).map_err(|e| e.to_string())?
        }
        "IQ2_XXS" => quant::decode_iq2_xxs_matrix(bytes, rows, columns, &mut out)
            .map_err(|e| format!("{e:?}"))?,
        "IQ3_XXS" => quant::decode_iq3_xxs_matrix(bytes, rows, columns, &mut out)
            .map_err(|e| format!("{e:?}"))?,
        "IQ4_XS" => quant::decode_iq4_xs_matrix(bytes, rows, columns, &mut out)
            .map_err(|e| e.to_string())?,
        other => return Err(format!("unsupported format {other}")),
    }
    if out.iter().any(|v| !v.is_finite()) {
        return Err("nonfinite decode".into());
    }
    Ok(out)
}

impl TensorSource for SecureCheckpoint {
    fn vector(&mut self, name: &str, length: usize) -> Result<Vec<f32>, String> {
        let r = self.record(name)?.clone();
        if r.dims != vec![length as u64] {
            return Err("vector shape".into());
        }
        decode(&r, &self.encoded(&r, None)?, 1, length)
    }
    fn matrix(&mut self, name: &str, rows: usize, columns: usize) -> Result<Matrix, String> {
        let r = self.record(name)?.clone();
        if r.dims != vec![columns as u64, rows as u64] {
            return Err(format!("matrix shape {name}"));
        }
        let values = decode(&r, &self.encoded(&r, None)?, rows, columns)?;
        Ok(Matrix {
            rows,
            columns,
            values,
        })
    }
    fn expert_matrix(
        &mut self,
        name: &str,
        expert: usize,
        rows: usize,
        columns: usize,
    ) -> Result<Matrix, String> {
        let r = self.record(name)?.clone();
        if r.dims.len() != 3 || r.dims[0] != columns as u64 || r.dims[1] != rows as u64 {
            return Err("expert shape".into());
        }
        let values = decode(&r, &self.encoded(&r, Some(expert))?, rows, columns)?;
        Ok(Matrix {
            rows,
            columns,
            values,
        })
    }
}

pub fn plan_summary(manifest: &CheckpointManifest, catalog: &TensorCatalog) -> serde_json::Value {
    let mut formats = BTreeMap::<String, usize>::new();
    for t in &catalog.tensors {
        *formats.entry(t.format.clone()).or_default() += 1;
    }
    serde_json::json!({"schema":"pulsarmlx.f017.native-full-checkpoint-plan-only/1.0.0","layer_count":79,"tensor_count":catalog.tensor_count,"shard_count":manifest.file_count,"total_checkpoint_bytes":manifest.total_bytes,"checkpoint_set_sha256":manifest.checkpoint_set_sha256,"quant_formats":formats,"original_checkpoint_reads":0,"original_checkpoint_shard_opens":0,"status":"PLAN_ONLY_PASS"})
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::symlink;

    fn synthetic_plan(root: &Path) -> (CheckpointManifest, TensorCatalog) {
        let files = (0..6)
            .map(|index| {
                let filename = format!("synthetic-{index}.gguf");
                let bytes = (1.25_f32 + index as f32).to_le_bytes();
                fs::write(root.join(&filename), bytes).unwrap();
                ShardIdentity {
                    filename,
                    sha256: format!("{:x}", Sha256::digest(bytes)),
                    size_bytes: bytes.len() as u64,
                }
            })
            .collect::<Vec<_>>();
        let mut names = vec![
            "token_embd.weight".to_owned(),
            "output_norm.weight".to_owned(),
            "output.weight".to_owned(),
        ];
        for layer in 0..79 {
            for suffix in [
                "attn_norm.weight",
                "attn_q_a.weight",
                "attn_q_a_norm.weight",
                "attn_q_b.weight",
                "attn_kv_a_mqa.weight",
                "attn_kv_a_norm.weight",
                "attn_k_b.weight",
                "attn_v_b.weight",
                "attn_output.weight",
                "ffn_norm.weight",
            ] {
                names.push(format!("blk.{layer}.{suffix}"));
            }
            let suffixes: &[&str] = if layer < 3 {
                &["ffn_gate.weight", "ffn_up.weight", "ffn_down.weight"]
            } else {
                &[
                    "ffn_gate_inp.weight",
                    "exp_probs_b.bias",
                    "ffn_gate_exps.weight",
                    "ffn_up_exps.weight",
                    "ffn_down_exps.weight",
                    "ffn_gate_shexp.weight",
                    "ffn_up_shexp.weight",
                    "ffn_down_shexp.weight",
                ]
            };
            names.extend(
                suffixes
                    .iter()
                    .map(|suffix| format!("blk.{layer}.{suffix}")),
            );
        }
        while names.len() < 1809 {
            names.push(format!("synthetic.unused.{}", names.len()));
        }
        let dims_for = |name: &str| -> Vec<u64> {
            if matches!(name, "token_embd.weight" | "output.weight") {
                return vec![6144, 154_880];
            }
            if name == "output_norm.weight" {
                return vec![6144];
            }
            let suffix = name.splitn(3, '.').nth(2).unwrap_or(name);
            match suffix {
                "attn_norm.weight" | "ffn_norm.weight" => vec![6144],
                "attn_q_a.weight" => vec![6144, 2048],
                "attn_q_a_norm.weight" => vec![2048],
                "attn_q_b.weight" => vec![2048, 16_384],
                "attn_kv_a_mqa.weight" => vec![6144, 576],
                "attn_kv_a_norm.weight" => vec![512],
                "attn_k_b.weight" => vec![192, 512, 64],
                "attn_v_b.weight" => vec![512, 256, 64],
                "attn_output.weight" => vec![16_384, 6144],
                "ffn_gate.weight" | "ffn_up.weight" => vec![6144, 12_288],
                "ffn_down.weight" => vec![12_288, 6144],
                "ffn_gate_inp.weight" => vec![6144, 256],
                "exp_probs_b.bias" => vec![256],
                "ffn_gate_exps.weight" | "ffn_up_exps.weight" => vec![6144, 2048, 256],
                "ffn_down_exps.weight" => vec![2048, 6144, 256],
                "ffn_gate_shexp.weight" | "ffn_up_shexp.weight" => vec![6144, 2048],
                "ffn_down_shexp.weight" => vec![2048, 6144],
                _ => vec![1],
            }
        };
        let tensors = names
            .into_iter()
            .enumerate()
            .map(|(index, name)| TensorRecord {
                data_offset_abs: 0,
                dims: dims_for(&name),
                file: files[index % files.len()].filename.clone(),
                name,
                format: "F32".into(),
                type_id: 0,
            })
            .collect::<Vec<_>>();
        (
            CheckpointManifest {
                checkpoint_set_sha256: "a".repeat(64),
                file_count: 6,
                total_bytes: files.iter().map(|file| file.size_bytes).sum(),
                files,
            },
            TensorCatalog {
                architecture: "glm-dsa".into(),
                kv_selected: BTreeMap::from([
                    ("block_count".into(), 79.into()),
                    ("embedding_length".into(), 6144.into()),
                    ("vocab_size".into(), 154_880.into()),
                    ("feed_forward_length".into(), 12_288.into()),
                    ("expert_count".into(), 256.into()),
                    ("expert_used_count".into(), 8.into()),
                    ("expert_feed_forward_length".into(), 2048.into()),
                    ("attention.head_count".into(), 64.into()),
                    ("attention.q_lora_rank".into(), 2048.into()),
                    ("attention.kv_lora_rank".into(), 512.into()),
                    ("attention.key_length_mla".into(), 256.into()),
                    ("attention.value_length_mla".into(), 256.into()),
                    ("rope.dimension_count".into(), 64.into()),
                    ("rope.freq_base".into(), 8_000_000.0.into()),
                ]),
                tensor_count: tensors.len(),
                shard_count: 6,
                tensors,
            },
        )
    }

    fn synthetic_root(label: &str) -> std::path::PathBuf {
        let root = std::env::temp_dir().join(format!(
            "f017-six-shard-{label}-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::create_dir(&root).unwrap();
        root.canonicalize().unwrap()
    }

    #[test]
    fn authoritative_plan_is_complete_without_opening_shards() {
        let (m, c) = load_plan_only(
            Path::new("../../docs/validation/glm52-checkpoint.json"),
            Path::new("../../docs/research/glm52/raw/f016-c01-catalog-0001.json"),
        )
        .unwrap();
        let s = plan_summary(&m, &c);
        assert_eq!(s["tensor_count"], 1809);
        assert_eq!(s["original_checkpoint_reads"], 0);
        assert_eq!(s["quant_formats"]["IQ2_S"], 2);
    }

    #[test]
    fn six_shard_mmap_loader_and_mutations_fail_closed() {
        let root = synthetic_root("valid");
        let (manifest, catalog) = synthetic_plan(&root);
        {
            let mut checkpoint =
                SecureCheckpoint::open(&root, manifest.clone(), catalog.clone()).unwrap();
            let filler = catalog
                .tensors
                .iter()
                .find(|tensor| tensor.name.starts_with("synthetic.unused."))
                .unwrap();
            let expected = manifest
                .files
                .iter()
                .position(|file| file.filename == filler.file)
                .unwrap() as f32
                + 1.25;
            assert_eq!(checkpoint.vector(&filler.name, 1).unwrap(), vec![expected]);
        }

        let mut duplicate = catalog.clone();
        duplicate.tensors[1].name = duplicate.tensors[0].name.clone();
        assert!(validate_plan(&manifest, &duplicate).is_err());
        let mut missing = catalog.clone();
        missing.tensors.pop();
        assert!(validate_plan(&manifest, &missing).is_err());

        let mut wrong_hash = manifest.clone();
        wrong_hash.files[0].sha256 = "0".repeat(64);
        assert!(SecureCheckpoint::open(&root, wrong_hash, catalog.clone()).is_err());
        let mut wrong_size = manifest.clone();
        wrong_size.files[0].size_bytes += 1;
        wrong_size.total_bytes += 1;
        assert!(SecureCheckpoint::open(&root, wrong_size, catalog.clone()).is_err());
        assert!(
            SecureCheckpoint::open(&root.join(".."), manifest.clone(), catalog.clone()).is_err()
        );

        let mut corrupt_offset = catalog.clone();
        corrupt_offset
            .tensors
            .iter_mut()
            .find(|tensor| tensor.name.starts_with("synthetic.unused."))
            .unwrap()
            .data_offset_abs = 4;
        let mut checkpoint =
            SecureCheckpoint::open(&root, manifest.clone(), corrupt_offset).unwrap();
        let filler = catalog
            .tensors
            .iter()
            .find(|tensor| tensor.name.starts_with("synthetic.unused."))
            .unwrap();
        assert!(checkpoint.vector(&filler.name, 1).is_err());
        drop(checkpoint);

        fs::create_dir(root.join("unexpected-directory")).unwrap();
        assert!(SecureCheckpoint::open(&root, manifest.clone(), catalog.clone()).is_err());
        fs::remove_dir(root.join("unexpected-directory")).unwrap();

        let first = root.join(&manifest.files[0].filename);
        fs::remove_file(&first).unwrap();
        symlink(root.join(&manifest.files[1].filename), &first).unwrap();
        assert!(SecureCheckpoint::open(&root, manifest.clone(), catalog.clone()).is_err());
        fs::remove_file(&first).unwrap();
        fs::write(&first, [0_u8; 3]).unwrap();
        assert!(SecureCheckpoint::open(&root, manifest, catalog).is_err());
        fs::remove_dir_all(root).unwrap();
    }
}
