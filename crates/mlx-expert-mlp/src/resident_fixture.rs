//! Fixed origin and exact selected ranges for the small resident comparison.
use crate::expert_tuple::ROLES;
use mlx_expert_ranges::{
    residency::{parse_hash, ContentAuthority, CopiedResidency, Hash256, TupleHashes},
    BoundedSource, ExpertPlan, ExpertRequest,
};
use mlx_native_affine::{
    dtype::Dtype,
    fixture::{sha256_hex, HostTensor},
};
use serde_json::{json, Value};
use std::{
    fs,
    path::{Path, PathBuf},
};

pub const INPUT_SHA: &str = "3c563f14ae18c17c9365324c2fd265ee96251a3448d5ae43e0fee1474cd5233c";
pub const VIEW_SHA: &str = "23bad0b4c40086dfec75eda1273a7af999c3cca98027f17aed0d4a61690507d8";
const VIEW: &[u8] = include_bytes!("../../../fixtures/resident-expert-mlp/manifest.json");
pub const LAYER: u32 = 0;
pub const PARTS: [&str; 3] = ["weight", "scales", "biases"];
pub type Result<T> = std::result::Result<T, String>;
pub fn ensure(ok: bool, reason: &str) -> Result<()> {
    if ok {
        Ok(())
    } else {
        Err(reason.to_string())
    }
}
pub fn text(v: &Value) -> Result<&str> {
    v.as_str().ok_or_else(|| "string field".into())
}
pub fn digest(v: &Value) -> Result<Hash256> {
    parse_hash(text(v)?).map_err(|e| e.to_string())
}
pub fn hex(b: &Hash256) -> String {
    b.iter().map(|x| format!("{x:02x}")).collect()
}
pub fn checked_file(p: &Path, limit: usize) -> Result<Vec<u8>> {
    use std::io::Read;
    ensure(
        p.canonicalize().map_err(|e| e.to_string())? == p,
        "noncanonical fixture",
    )?;
    let mut f = fs::File::open(p).map_err(|e| e.to_string())?;
    let m = f.metadata().map_err(|e| e.to_string())?;
    ensure(
        m.is_file() && m.len() <= limit as u64,
        "bounded regular file required",
    )?;
    let mut b = Vec::new();
    let len = m.len() as usize;
    b.try_reserve_exact(len).map_err(|e| e.to_string())?;
    b.resize(len, 0);
    f.read_exact(&mut b).map_err(|e| e.to_string())?;
    ensure(
        f.read(&mut [0u8]).map_err(|e| e.to_string())? == 0,
        "file grew",
    )?;
    Ok(b)
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Arm {
    Cached,
    Allocating,
}
impl Arm {
    pub fn name(self) -> &'static str {
        match self {
            Self::Cached => "cached",
            Self::Allocating => "allocating",
        }
    }
}
pub struct Population {
    pub profile: &'static str,
    pub name: String,
    pub bits: [u32; 3],
    pub content: Hash256,
    pub metadata: String,
    pub shard_sha: String,
    pub hashes: [TupleHashes; 3],
    pub ranges: [[[[u64; 2]; 3]; 3]; 3],
}
impl Population {
    pub fn load(profile: &str) -> Result<Self> {
        let (profile, bits) = match profile {
            "default" => ("default", [4, 4, 4]),
            "mixed" => ("mixed", [8, 4, 8]),
            _ => return Err("unknown recipe".into()),
        };
        ensure(sha256_hex(VIEW) == VIEW_SHA, "compiled view manifest")?;
        let v: Value = serde_json::from_slice(VIEW).map_err(|e| e.to_string())?;
        let r = &v["recipes"][profile];
        let mut hashes = [[[[0u8; 32]; 3]; 3]; 3];
        let mut ranges = [[[[0u64; 2]; 3]; 3]; 3];
        for e in 0..3 {
            for i in 0..3 {
                let p = &r["planes"][e][i];
                ensure(
                    p["module"] == ROLES[i] && p["bits"] == bits[i] && p["group_size"] == 64,
                    "fixed recipe",
                )?;
                for c in 0..3 {
                    hashes[e][i][c] = digest(&p["sha256"][c])?;
                    let rr = &p["ranges"][c];
                    ensure(
                        rr["tensor"] == format!("{}.{}", ROLES[i], PARTS[c])
                            && rr["shard"] == "model.safetensors",
                        "range role",
                    )?;
                    ranges[e][i][c] = [
                        rr["begin"].as_u64().ok_or("offset")?,
                        rr["len"].as_u64().ok_or("length")?,
                    ];
                }
            }
        }
        Ok(Self {
            profile,
            name: text(&r["name"])?.into(),
            bits,
            content: digest(&r["content"])?,
            metadata: text(&r["metadata"])?.into(),
            shard_sha: text(&r["files"]["shard"])?.into(),
            hashes,
            ranges,
        })
    }
    pub fn request(&self, e: u32) -> ExpertRequest {
        ExpertRequest {
            expert: e.into(),
            experts: 3,
            d: 128,
            h: 64,
            bits: self.bits,
            group_size: 64,
            modules: ROLES.map(str::to_owned),
        }
    }
    pub fn open(&self, repo: &Path, arm: Arm) -> Result<(CopiedResidency, Option<BoundedSource>)> {
        let path = repo.join("fixtures/resident-expert-mlp").join(&self.name);
        ensure(
            path.canonicalize().map_err(|e| e.to_string())? == path,
            "fixture root",
        )?;
        let source = BoundedSource::open(&path).map_err(|e| e.to_string())?;
        let cache = CopiedResidency::new(
            source,
            LAYER,
            &self.request(0),
            ContentAuthority {
                checkpoint: &self.name,
                metadata: &self.metadata,
                content: self.content,
                hashes: &self.hashes,
            },
            4 << 20,
            0,
        )
        .map_err(|e| e.to_string())?;
        let control = if arm == Arm::Allocating {
            let s = BoundedSource::open(&path).map_err(|e| e.to_string())?;
            ensure(
                s.metadata_snapshot() == self.metadata,
                "control source snapshot",
            )?;
            for e in 0..3 {
                let plan = s.plan(self.request(e)).map_err(|e| e.to_string())?;
                self.verify_plan(&plan, e)?;
            }
            Some(s)
        } else {
            None
        };
        Ok((cache, control))
    }
    pub fn verify_plan(&self, plan: &ExpertPlan<'_>, expert: u32) -> Result<()> {
        let r = plan.record();
        let e = expert as usize;
        ensure(
            e < 3
                && r.checkpoint == self.name
                && r.metadata_snapshot_sha256 == self.metadata
                && r.planes.len() == 3
                && r.request.expert == expert as u64
                && r.request.experts == 3
                && r.request.d == 128
                && r.request.h == 64
                && r.request.group_size == 64
                && r.request.bits == self.bits
                && r.request.modules == ROLES,
            "control plan identity",
        )?;
        for (i, p) in r.planes.iter().enumerate() {
            ensure(
                p.role == ["gate", "up", "down"][i]
                    && p.module == ROLES[i]
                    && p.logical_shape == if i == 2 { [128, 64] } else { [64, 128] }
                    && p.metadata_dtype == "BF16"
                    && p.group_size == 64
                    && p.bits == self.bits[i]
                    && p.expert == e as u64
                    && p.resolved_from
                        == if self.bits[i] == 8 {
                            "override"
                        } else {
                            "default"
                        },
                "control plane",
            )?;
            for (c, b) in p.ranges.iter().enumerate() {
                ensure(
                    b.tensor == format!("{}.{}", ROLES[i], PARTS[c])
                        && b.shard == "model.safetensors"
                        && [b.begin, b.len] == self.ranges[e][i][c],
                    "control ranges",
                )?;
            }
        }
        plan.validate_source().map_err(|e| e.to_string())
    }
    pub fn input(&self, repo: &Path, e: usize) -> PathBuf {
        repo.join("fixtures/expert-mlp-composition/inputs")
            .join(format!("mlp-d128-h64-m1-e{e}-{}.f32", self.profile))
    }
    pub fn binding(&self) -> Value {
        json!({"profile":self.profile,"checkpoint":self.name,"content":hex(&self.content),"metadata":self.metadata,"shard_sha256":self.shard_sha,"input_sha256":INPUT_SHA,"view_sha256":VIEW_SHA})
    }
}
#[derive(Clone, Copy)]
pub struct Geometry {
    pub bits: [u32; 3],
}
impl Geometry {
    pub fn from_cache(c: &CopiedResidency, p: &Population) -> Result<Self> {
        let (layer, r) = c.admitted_class();
        ensure(
            layer == LAYER
                && r.modules == ROLES
                && [r.d, r.h, r.experts] == [128, 64, 3]
                && r.group_size == 64
                && r.bits == p.bits,
            "admitted class",
        )?;
        Ok(Self { bits: r.bits })
    }
    pub fn shape(&self, i: usize, c: usize) -> [usize; 2] {
        let (n, k) = if i == 2 { (128, 64) } else { (64, 128) };
        [
            n,
            if c == 0 {
                k * self.bits[i] as usize / 32
            } else {
                k / 64
            },
        ]
    }
}
pub type Planes = [[HostTensor; 3]; 3];
pub type Slices<'a> = [[&'a [u8]; 3]; 3];
pub fn verify_parts(bytes: Slices<'_>, geo: Geometry, expected: &TupleHashes) -> Result<()> {
    for i in 0..3 {
        for j in 0..3 {
            let [n, k] = geo.shape(i, j);
            let part = bytes[i][j];
            ensure(
                part.len() == n * k * if j == 0 { 4 } else { 2 }
                    && sha256_hex(part) == hex(&expected[i][j]),
                "component length or hash",
            )?;
        }
    }
    Ok(())
}
pub fn stage_parts(
    parts: Slices<'_>,
    geo: Geometry,
    expected: &TupleHashes,
) -> Result<(Planes, usize)> {
    verify_parts(parts, geo, expected)?;
    let mut capacity = 0;
    let mut roles = Vec::with_capacity(3);
    for (i, row) in parts.into_iter().enumerate() {
        let mut tensors = Vec::with_capacity(3);
        for (j, slice) in row.into_iter().enumerate() {
            let mut bytes = Vec::new();
            bytes
                .try_reserve_exact(slice.len())
                .map_err(|e| e.to_string())?;
            bytes.extend_from_slice(slice);
            let t = HostTensor {
                name: format!("{}.{}", ROLES[i], PARTS[j]),
                dtype: if j == 0 { Dtype::U32 } else { Dtype::BF16 },
                shape: geo.shape(i, j).to_vec(),
                bytes,
            };
            capacity +=
                t.bytes.capacity() + t.name.capacity() + t.shape.capacity() * size_of::<usize>();
            tensors.push(t);
        }
        roles.push(tensors.try_into().map_err(|_| "three components")?);
    }
    Ok((roles.try_into().map_err(|_| "three roles")?, capacity))
}
