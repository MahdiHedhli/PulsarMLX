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
    {
        return Err("checkpoint plan census".into());
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
        if layer < 3 {
            for suffix in ["ffn_gate.weight", "ffn_up.weight", "ffn_down.weight"] {
                let name = format!("blk.{layer}.{suffix}");
                if !names.contains(name.as_str()) {
                    return Err(format!("missing {name}"));
                }
            }
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
        let entries = fs::read_dir(root)
            .map_err(|e| e.to_string())?
            .filter_map(Result::ok)
            .filter(|e| e.file_type().map(|t| t.is_file()).unwrap_or(false))
            .map(|e| e.file_name().to_string_lossy().into_owned())
            .collect::<BTreeSet<_>>();
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
}
