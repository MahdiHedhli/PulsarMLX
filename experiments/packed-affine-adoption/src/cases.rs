use mlx_expert_ranges::{ExpertRequest, ExpertRole};
use mlx_native_affine::{
    dtype::Dtype,
    family,
    fixture::{sha256_hex, HostTensor},
    refusal::{check_qmm, DeviceFacts},
};
use serde::Deserialize;
use serde_json::Value;
use std::{
    fs,
    io::{Read, Seek, SeekFrom},
    path::{Component, Path, PathBuf},
};

#[derive(Debug, Clone, Deserialize)]
pub struct Case {
    pub id: String,
    pub original_id: String,
    pub population_id: String,
    pub source: String,
    pub input: String,
    pub input_sha256: String,
    pub role: String,
    pub expert: u64,
    pub experts: u64,
    #[serde(rename = "D")]
    pub d: u64,
    #[serde(rename = "H")]
    pub h: u64,
    #[serde(rename = "M")]
    pub m: usize,
    pub bits: [u32; 3],
    pub expected_hashes: [String; 3],
    pub source_kind: String,
}
pub fn confined(root: &Path, rel: &str) -> Result<PathBuf, String> {
    let p = Path::new(rel);
    if p.components().any(|c| !matches!(c, Component::Normal(_))) {
        return Err("nonrelative artifact path".into());
    }
    let base = root.canonicalize().map_err(|e| e.to_string())?;
    let result = base.join(p).canonicalize().map_err(|e| e.to_string())?;
    if !result.starts_with(base) {
        return Err("escaped artifact path".into());
    }
    Ok(result)
}
pub fn manifest(root: &Path, hash: &str) -> Result<Value, String> {
    let raw = fs::read(root.join("manifest.json")).map_err(|e| e.to_string())?;
    if raw.len() > 1024 * 1024 || sha256_hex(&raw) != hash {
        return Err("manifest identity".into());
    }
    let j: Value = serde_json::from_slice(&raw).map_err(|e| e.to_string())?;
    if j["schema"] != "pulsarmlx.adoption-fixtures/1" {
        return Err("manifest schema".into());
    }
    Ok(j)
}
impl Case {
    pub fn role(&self) -> Result<ExpertRole, String> {
        match self.role.as_str() {
            "gate" => Ok(ExpertRole::Gate),
            "up" => Ok(ExpertRole::Up),
            "down" => Ok(ExpertRole::Down),
            _ => Err("role".into()),
        }
    }
    pub fn request(&self) -> ExpertRequest {
        ExpertRequest {
            modules: [
                "synthetic.experts.gate",
                "synthetic.experts.up",
                "synthetic.experts.down",
            ]
            .map(String::from),
            expert: self.expert,
            experts: self.experts,
            d: self.d,
            h: self.h,
            bits: self.bits,
            group_size: 64,
        }
    }
    pub fn geometry(&self) -> Result<(usize, usize, u32), String> {
        let i = self.role()?.index();
        if i == 2 || self.source_kind != "indexed-tuple" {
            return Err("projection scope".into());
        }
        let admitted = match self.population_id.as_str() {
            "small-tuple-read-into-v1" => {
                self.d == 128
                    && self.h == 64
                    && self.experts == 3
                    && self.expert < 2
                    && [1, 32].contains(&self.m)
                    && [[4, 4, 4], [8, 4, 8]].contains(&self.bits)
            }
            "representative-read-into-v1" => {
                self.d == 4096
                    && self.h == 2048
                    && self.experts == 1
                    && self.expert == 0
                    && self.m == 1
                    && self.bits == [4, 4, 4]
            }
            _ => false,
        };
        if !admitted {
            return Err("frozen geometry".into());
        }
        Ok((self.h as usize, self.d as usize, self.bits[i]))
    }
    /// Original envelope bytes read independently of the candidate reader. Only
    /// qualification/preflight uses these owned tensors, never a measured fill.
    pub fn original(&self, root: &Path) -> Result<(HostTensor, [HostTensor; 3], usize), String> {
        let (n, k, bits) = self.geometry()?;
        let source = confined(root, &self.source)?;
        let mut f = fs::File::open(source.join("model.safetensors")).map_err(|e| e.to_string())?;
        let mut prefix = [0; 8];
        f.read_exact(&mut prefix).map_err(|e| e.to_string())?;
        let hlen = u64::from_le_bytes(prefix);
        if hlen > 2 * 1024 * 1024 {
            return Err("header cap".into());
        }
        let mut h = vec![0; hlen as usize];
        f.read_exact(&mut h).map_err(|e| e.to_string())?;
        let header: Value = serde_json::from_slice(&h).map_err(|e| e.to_string())?;
        let mut parts = Vec::new();
        for (i, suffix) in ["weight", "scales", "biases"].iter().enumerate() {
            let name = format!("synthetic.experts.{}.{}", self.role, suffix);
            let record = &header[&name];
            let cols = if i == 0 {
                k * bits as usize / 32
            } else {
                k / 64
            };
            let length = n * cols * if i == 0 { 4 } else { 2 };
            if record["shape"] != serde_json::json!([self.experts, n, cols])
                || record["dtype"] != if i == 0 { "U32" } else { "BF16" }
            {
                return Err("original header geometry".into());
            }
            let offset = record["data_offsets"][0]
                .as_u64()
                .ok_or("offset")?
                .checked_add(8 + hlen)
                .and_then(|v| v.checked_add(self.expert * length as u64))
                .ok_or("overflow")?;
            f.seek(SeekFrom::Start(offset)).map_err(|e| e.to_string())?;
            let mut bytes = vec![0; length];
            f.read_exact(&mut bytes).map_err(|e| e.to_string())?;
            if sha256_hex(&bytes) != self.expected_hashes[i] {
                return Err("original component hash".into());
            }
            parts.push(HostTensor {
                name: name.clone(),
                dtype: if i == 0 { Dtype::U32 } else { Dtype::BF16 },
                shape: vec![n, cols],
                bytes,
            });
        }
        let raw = fs::read(confined(root, &self.input)?).map_err(|e| e.to_string())?;
        if raw.len() != self.m * k * 4 || sha256_hex(&raw) != self.input_sha256 {
            return Err("original input hash".into());
        }
        let input = HostTensor {
            name: "x".into(),
            dtype: Dtype::F32,
            shape: vec![self.m, k],
            bytes: raw,
        };
        let parts: [HostTensor; 3] = parts.try_into().map_err(|_| "parts")?;
        let exponent = if k == 4096 {
            crate::selected_preflight::selected_preflight(self.role()?.index(), &input, &parts)?
        } else {
            let g = check_qmm(
                &DeviceFacts::GPU,
                true,
                &input,
                &parts[0],
                &parts[1],
                &parts[2],
                bits,
                64,
            )
            .map_err(|e| e.to_string())?;
            family::bound_exponent(g.m_eff, g.n, g.k, 64, bits)
        };
        Ok((input, parts, exponent))
    }
}
