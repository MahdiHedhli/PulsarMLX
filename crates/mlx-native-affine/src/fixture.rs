//! The frozen fixture population: manifest parsing, case-file loading and
//! hash validation (contract frozen_population).
//!
//! Each case file is the concatenation of its tensors' little-endian bytes in
//! manifest order (manifest `encoding`). Nothing here generates or predicts
//! data; it only reads the committed bytes and checks them against the hashes
//! the manifest and the contract freeze.

use std::collections::BTreeSet;
use std::fmt::Write as _;
use std::path::{Path, PathBuf};

use serde_json::Value;
use sha2::{Digest, Sha256};

use crate::dtype::Dtype;
use crate::frozen;

pub fn sha256_hex(bytes: &[u8]) -> String {
    let digest = Sha256::digest(bytes);
    let mut s = String::with_capacity(64);
    for b in digest {
        let _ = write!(s, "{b:02x}");
    }
    s
}

#[derive(Debug)]
pub struct FixtureError(pub String);

impl std::fmt::Display for FixtureError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for FixtureError {}

fn err<T>(msg: impl Into<String>) -> Result<T, FixtureError> {
    Err(FixtureError(msg.into()))
}

#[derive(Clone, Debug)]
pub struct TensorMeta {
    pub name: String,
    pub dtype_name: String,
    pub shape: Vec<usize>,
    pub offset: usize,
    pub nbytes: usize,
    pub sha256: String,
}

#[derive(Clone, Debug)]
pub struct CaseSpec {
    pub id: String,
    pub family: String,
    pub op: String,
    pub params: Value,
    pub expected: Value,
    pub references: Vec<String>,
    pub file: Option<String>,
    pub file_sha256: Option<String>,
    pub tensors: Vec<TensorMeta>,
}

impl CaseSpec {
    pub fn param_u64(&self, key: &str) -> Option<u64> {
        self.params.get(key).and_then(Value::as_u64)
    }
    pub fn param_str(&self, key: &str) -> Option<&str> {
        self.params.get(key).and_then(Value::as_str)
    }
    pub fn param_bool(&self, key: &str) -> Option<bool> {
        self.params.get(key).and_then(Value::as_bool)
    }
    pub fn is_refusal(&self) -> bool {
        self.expected.get("outcome").and_then(Value::as_str) == Some("refuse")
    }
    pub fn expected_refusal(&self) -> Option<&str> {
        self.expected.get("refusal_id").and_then(Value::as_str)
    }
    pub fn has_reference(&self, kind: &str) -> bool {
        self.references.iter().any(|r| r == kind)
    }
    /// The N-QMM-BOUND gamma exponent the contract assigns to this case: the
    /// largest exponent over the candidate families recorded in the manifest
    /// (acceptance_implementation G-QMM-EXACT `n`).
    pub fn manifest_gamma_n(&self) -> Option<u64> {
        let fams = self.expected.get("families_0_31_2")?.as_array()?;
        fams.iter()
            .filter_map(|f| f.get("gamma_n").and_then(Value::as_u64))
            .max()
    }
}

#[derive(Clone, Debug)]
pub struct Manifest {
    pub raw_sha256: String,
    pub generator_sha256: String,
    pub cases: Vec<CaseSpec>,
}

fn as_str(v: &Value, key: &str, ctx: &str) -> Result<String, FixtureError> {
    match v.get(key).and_then(Value::as_str) {
        Some(s) => Ok(s.to_string()),
        None => err(format!("{ctx}: missing string {key}")),
    }
}

pub fn parse_manifest(raw: &[u8]) -> Result<Manifest, FixtureError> {
    let doc: Value =
        serde_json::from_slice(raw).map_err(|e| FixtureError(format!("manifest JSON: {e}")))?;
    let generator_sha256 = as_str(&doc, "generator_sha256", "manifest")?;
    let cases_v = match doc.get("cases").and_then(Value::as_array) {
        Some(c) => c,
        None => return err("manifest: no cases array"),
    };
    let mut cases = Vec::with_capacity(cases_v.len());
    for c in cases_v {
        let id = as_str(c, "id", "case")?;
        let mut tensors = Vec::new();
        if let Some(ts) = c.get("tensors").and_then(Value::as_array) {
            for t in ts {
                let shape = match t.get("shape").and_then(Value::as_array) {
                    Some(s) => s
                        .iter()
                        .map(|d| d.as_u64().map(|d| d as usize))
                        .collect::<Option<Vec<_>>>()
                        .ok_or_else(|| FixtureError(format!("{id}: bad shape")))?,
                    None => return err(format!("{id}: tensor without shape")),
                };
                tensors.push(TensorMeta {
                    name: as_str(t, "name", &id)?,
                    dtype_name: as_str(t, "dtype", &id)?,
                    shape,
                    offset: t
                        .get("offset")
                        .and_then(Value::as_u64)
                        .ok_or_else(|| FixtureError(format!("{id}: offset")))?
                        as usize,
                    nbytes: t
                        .get("nbytes")
                        .and_then(Value::as_u64)
                        .ok_or_else(|| FixtureError(format!("{id}: nbytes")))?
                        as usize,
                    sha256: as_str(t, "sha256", &id)?,
                });
            }
        }
        let references = c
            .get("references")
            .and_then(Value::as_array)
            .map(|a| {
                a.iter()
                    .filter_map(|r| r.as_str().map(str::to_string))
                    .collect()
            })
            .unwrap_or_default();
        cases.push(CaseSpec {
            family: as_str(c, "family", &id)?,
            op: as_str(c, "op", &id)?,
            params: c.get("params").cloned().unwrap_or(Value::Null),
            expected: c.get("expected").cloned().unwrap_or(Value::Null),
            references,
            file: c.get("file").and_then(Value::as_str).map(str::to_string),
            file_sha256: c
                .get("file_sha256")
                .and_then(Value::as_str)
                .map(str::to_string),
            tensors,
            id,
        });
    }
    Ok(Manifest {
        raw_sha256: sha256_hex(raw),
        generator_sha256,
        cases,
    })
}

impl Manifest {
    pub fn case(&self, id: &str) -> Option<&CaseSpec> {
        self.cases.iter().find(|c| c.id == id)
    }
    pub fn ids(&self) -> Vec<String> {
        self.cases.iter().map(|c| c.id.clone()).collect()
    }
}

/// A host tensor exactly as stored: dtype, shape and little-endian bytes.
#[derive(Clone, Debug)]
pub struct HostTensor {
    pub name: String,
    pub dtype: Dtype,
    pub shape: Vec<usize>,
    pub bytes: Vec<u8>,
}

impl HostTensor {
    pub fn elements(&self) -> usize {
        self.shape.iter().product()
    }
    /// Element `i` as a raw bit pattern (u32 for 4-byte types, u16 widened).
    pub fn bits(&self, i: usize) -> u32 {
        match self.dtype.size() {
            4 => u32::from_le_bytes(self.bytes[4 * i..4 * i + 4].try_into().unwrap()),
            _ => u16::from_le_bytes(self.bytes[2 * i..2 * i + 2].try_into().unwrap()) as u32,
        }
    }
    pub fn words_u32(&self) -> Vec<u32> {
        self.bytes
            .chunks_exact(4)
            .map(|c| u32::from_le_bytes(c.try_into().unwrap()))
            .collect()
    }
    pub fn halves_u16(&self) -> Vec<u16> {
        self.bytes
            .chunks_exact(2)
            .map(|c| u16::from_le_bytes(c.try_into().unwrap()))
            .collect()
    }
}

/// A loaded case: its spec and its tensors (hash-checked).
#[derive(Clone, Debug)]
pub struct LoadedCase {
    pub spec: CaseSpec,
    pub tensors: Vec<HostTensor>,
}

impl LoadedCase {
    pub fn tensor(&self, name: &str) -> Option<&HostTensor> {
        self.tensors.iter().find(|t| t.name == name)
    }
}

/// Load a case's tensors from `fixture_dir`, verifying the file hash and every
/// tensor's hash, offset and size against the manifest. FX-CAST cases carry
/// no file: they reuse `params.input_case`, which the caller resolves.
pub fn load_case(fixture_dir: &Path, spec: &CaseSpec) -> Result<LoadedCase, FixtureError> {
    let Some(file) = &spec.file else {
        return Ok(LoadedCase {
            spec: spec.clone(),
            tensors: Vec::new(),
        });
    };
    let path = fixture_dir.join(file);
    let data = std::fs::read(&path)
        .map_err(|e| FixtureError(format!("{}: read {}: {e}", spec.id, file)))?;
    let got = sha256_hex(&data);
    if Some(&got) != spec.file_sha256.as_ref() {
        return err(format!("{}: case file sha256 {got} != manifest", spec.id));
    }
    let mut tensors = Vec::new();
    let mut cursor = 0usize;
    for t in &spec.tensors {
        let dtype = Dtype::parse(&t.dtype_name)
            .ok_or_else(|| FixtureError(format!("{}: dtype {}", spec.id, t.dtype_name)))?;
        let count: usize = t.shape.iter().product();
        if t.offset != cursor
            || t.nbytes != count * dtype.size()
            || t.offset + t.nbytes > data.len()
        {
            return err(format!("{}: tensor {} layout", spec.id, t.name));
        }
        let bytes = data[t.offset..t.offset + t.nbytes].to_vec();
        if sha256_hex(&bytes) != t.sha256 {
            return err(format!("{}: tensor {} sha256", spec.id, t.name));
        }
        cursor += t.nbytes;
        tensors.push(HostTensor {
            name: t.name.clone(),
            dtype,
            shape: t.shape.clone(),
            bytes,
        });
    }
    if cursor != data.len() {
        return err(format!("{}: trailing bytes", spec.id));
    }
    Ok(LoadedCase {
        spec: spec.clone(),
        tensors,
    })
}

/// Result of the frozen-population validation (contract
/// frozen_population.parent_validation, acceptance B10).
#[derive(Clone, Debug)]
pub struct PopulationCheck {
    pub contract_sha256: String,
    pub plan_sha256: String,
    pub source_pins_sha256: String,
    pub manifest_sha256: String,
    pub generator_sha256: String,
    pub cases_listing_sha256: String,
    pub case_count: usize,
    pub case_file_count: usize,
    pub generator_check: Option<String>,
}

fn read(root: &Path, rel: &str) -> Result<Vec<u8>, FixtureError> {
    std::fs::read(root.join(rel)).map_err(|e| FixtureError(format!("read {rel}: {e}")))
}

/// Validate the frozen population rooted at `root` (a repository checkout, or
/// a copy of the relevant paths). `generator_check` runs the generator's
/// `--check` when an interpreter is given.
pub fn validate_population(
    root: &Path,
    python: Option<&str>,
) -> Result<(Manifest, PopulationCheck), FixtureError> {
    let contract = read(root, frozen::CONTRACT_PATH)?;
    let contract_sha = sha256_hex(&contract);
    if contract_sha != frozen::CONTRACT_SHA256 {
        return err(format!("contract sha256 {contract_sha} != frozen"));
    }
    let contract_doc: Value = serde_json::from_slice(&contract)
        .map_err(|e| FixtureError(format!("contract JSON: {e}")))?;
    let fp = &contract_doc["frozen_population"];
    if fp["manifest_sha256"].as_str() != Some(frozen::MANIFEST_SHA256)
        || fp["generator_sha256"].as_str() != Some(frozen::GENERATOR_SHA256)
        || fp["case_count"].as_u64() != Some(frozen::CASE_COUNT as u64)
    {
        return err("contract frozen_population differs from the compiled-in identities");
    }
    let plan_sha = sha256_hex(&read(root, frozen::PLAN_PATH)?);
    if plan_sha != frozen::PLAN_SHA256 {
        return err(format!("plan sha256 {plan_sha} != frozen"));
    }
    let pins_sha = sha256_hex(&read(root, frozen::SOURCE_PINS_PATH)?);
    if pins_sha != frozen::SOURCE_PINS_SHA256 {
        return err(format!("source pins sha256 {pins_sha} != frozen"));
    }
    let generator = read(root, frozen::GENERATOR_PATH)?;
    let generator_sha = sha256_hex(&generator);
    if generator_sha != frozen::GENERATOR_SHA256 {
        return err(format!("generator sha256 {generator_sha} != frozen"));
    }
    let manifest_raw = read(root, frozen::MANIFEST_PATH)?;
    let manifest = parse_manifest(&manifest_raw)?;
    if manifest.raw_sha256 != frozen::MANIFEST_SHA256 {
        return err(format!(
            "manifest sha256 {} != contract",
            manifest.raw_sha256
        ));
    }
    if manifest.generator_sha256 != frozen::GENERATOR_SHA256 {
        return err("manifest generator_sha256 differs");
    }
    if manifest.cases.len() != frozen::CASE_COUNT {
        return err(format!("manifest case count {}", manifest.cases.len()));
    }
    let ids: BTreeSet<&str> = manifest.cases.iter().map(|c| c.id.as_str()).collect();
    if ids.len() != manifest.cases.len() {
        return err("duplicate case id in manifest");
    }
    // Every case file hash against the manifest; no extra and no missing file.
    let fixture_dir = root.join(frozen::FIXTURE_DIR);
    let mut expected_files = BTreeSet::new();
    for c in &manifest.cases {
        if let Some(file) = &c.file {
            let data = std::fs::read(fixture_dir.join(file))
                .map_err(|e| FixtureError(format!("{file}: {e}")))?;
            if Some(sha256_hex(&data)) != c.file_sha256 {
                return err(format!("{file}: sha256 differs from manifest"));
            }
            expected_files.insert(file.clone());
        }
    }
    let mut present = BTreeSet::new();
    let cases_dir = fixture_dir.join("cases");
    for entry in
        std::fs::read_dir(&cases_dir).map_err(|e| FixtureError(format!("cases dir: {e}")))?
    {
        let entry = entry.map_err(|e| FixtureError(e.to_string()))?;
        let name = entry.file_name().to_string_lossy().to_string();
        present.insert(format!("cases/{name}"));
    }
    if present != expected_files || present.len() != frozen::CASE_FILE_COUNT {
        return err(format!(
            "case file set differs: {} present, {} expected",
            present.len(),
            expected_files.len()
        ));
    }
    // The listing hash exactly as `LC_ALL=C shasum -a 256 cases/*.bin | shasum -a 256`.
    let mut listing = String::new();
    for rel in &present {
        let data = std::fs::read(fixture_dir.join(rel)).map_err(|e| FixtureError(e.to_string()))?;
        let _ = writeln!(listing, "{}  {}", sha256_hex(&data), rel);
    }
    let listing_sha = sha256_hex(listing.as_bytes());
    if listing_sha != frozen::CASES_LISTING_SHA256 {
        return err(format!("cases listing sha256 {listing_sha} != frozen"));
    }
    let generator_check = match python {
        None => None,
        Some(py) => {
            let out = std::process::Command::new(py)
                .args([
                    "-I",
                    "-B",
                    frozen::GENERATOR_PATH,
                    "--out",
                    frozen::FIXTURE_DIR,
                    "--check",
                ])
                .current_dir(root)
                .output()
                .map_err(|e| FixtureError(format!("generator --check spawn: {e}")))?;
            if !out.status.success() {
                return err(format!(
                    "generator --check failed: {} {}",
                    String::from_utf8_lossy(&out.stdout),
                    String::from_utf8_lossy(&out.stderr)
                ));
            }
            Some("PASS".to_string())
        }
    };
    let check = PopulationCheck {
        contract_sha256: contract_sha,
        plan_sha256: plan_sha,
        source_pins_sha256: pins_sha,
        manifest_sha256: manifest.raw_sha256.clone(),
        generator_sha256: generator_sha,
        cases_listing_sha256: listing_sha,
        case_count: manifest.cases.len(),
        case_file_count: present.len(),
        generator_check,
    };
    Ok((manifest, check))
}

/// The repository root of this checkout (two levels above the crate).
pub fn repo_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .expect("repository root")
}
