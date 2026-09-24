//! Frozen identities of the F020 Slice 2C composition package (frozen before
//! any observation; `docs/architecture/reviews/evidence/f020-slice2c-contract-acceptance-v1.json`).
//!
//! Every value here is quoted from the composition contract
//! `specs/020-mlx-safetensors-affine/contracts/native-composition-v1.json`
//! (sha256 `e3fc848c...`, schema `1.0.0-draft.5`), from its plan
//! `slice2c-plan.md` (draft 5) or from the freeze record. Changing one is a
//! contract revision (correction_policy rule_2), never an implementation fix.
//! The Slice 2B identities stay in [`crate::frozen`], which is unchanged.
//!
//! [`validate_population`] is the parent's before/after check of the frozen
//! population (contract `frozen_population.parent_validation`; plan section 4
//! step 1). It only reads committed bytes and compares hashes; it never
//! derives an expected range or byte.

use std::collections::{BTreeMap, BTreeSet};
use std::fmt::Write as _;
use std::path::{Path, PathBuf};

use serde_json::Value;

use crate::fixture::{self, parse_manifest, sha256_hex, FixtureError, Manifest};
use crate::frozen;

pub const CONTRACT_PATH: &str =
    "specs/020-mlx-safetensors-affine/contracts/native-composition-v1.json";
pub const CONTRACT_SHA256: &str =
    "e3fc848cea14222e0ed9f1c3c9c3c52faa044ed024d665d8767f7148e0e15c93";
pub const CONTRACT_SCHEMA: &str = "pulsarmlx.f020.native-composition-contract/1.0.0-draft.5";
pub const PLAN_PATH: &str = "specs/020-mlx-safetensors-affine/slice2c-plan.md";
pub const PLAN_SHA256: &str = "b4e23bf4500aa4082e1e7fc26f2731a1c37cc9cf122c59693b2353b62dda5dbf";
pub const GENERATOR_PATH: &str = "scripts/research/f020_native_composition_fixtures_v1.py";
pub const GENERATOR_SHA256: &str =
    "3aab90e85a64530a554e6e0d03324ea95496ac83c940734c75d7bad701830f5b";
pub const GENERATOR_TEST_PATH: &str =
    "scripts/research/tests/test_f020_native_composition_fixtures_v1.py";
pub const GENERATOR_TEST_SHA256: &str =
    "a4cbd213fa53037a5d90c564e54e97056b919b49231dca83b3d7a6e3e2265b7c";
pub const FIXTURE_DIR: &str = "fixtures/native-composition";
pub const MANIFEST_PATH: &str = "fixtures/native-composition/manifest.json";
pub const MANIFEST_SHA256: &str =
    "6f0e39e6d2c705603f3f897133d42c31837c53348aba0f4b0389dca18018fc14";
/// Inside the fixture dir: `find checkpoints mutations standalone -type f |
/// LC_ALL=C sort | xargs shasum -a 256 | shasum -a 256`.
pub const FILES_LISTING_SHA256: &str =
    "2d314e23ed061bb82d757edb1f6a9fe783d2b2da23c94f794bc07757f34058b8";
/// Files covered by the listing (the manifest makes 28).
pub const LISTED_FILE_COUNT: usize = 27;
pub const CASE_COUNT: usize = 32;
/// The manifest's own schema (it names contract draft.1, the draft under
/// which the population was generated; plan section 10 GO item 2).
pub const MANIFEST_SCHEMA: &str = "pulsarmlx.f020.native-composition-fixtures/1.0.0";

/// The inherited Slice 2B contract the child report must echo.
pub const SLICE2B_CONTRACT_SHA256: &str = frozen::CONTRACT_SHA256;

/// The child mode that runs the composition (plan section 3). The Slice 2B
/// modes `qualify` and `selftest` are unchanged.
pub const CHILD_MODE: &str = "compose";

/// Contract `composition_refusals.order`, verbatim, first failing id wins.
pub const COMPOSITION_REFUSAL_ORDER: [&str; 9] = [
    "C-R-CATALOG",
    "C-R-RESOLVE",
    "C-R-SOURCE-BINDING",
    "C-R-MODULE-BINDING",
    "C-R-RECIPE-BINDING",
    "C-R-INDEX-RANK",
    "C-R-INDEX-RANGE",
    "C-R-OVERFLOW",
    "C-R-BACKING",
];

/// Contract `selection_checks.checks` that compare against the oracle.
pub const SELECTION_CHECKS: [&str; 5] = [
    "S-IDENTITY",
    "S-RANGES",
    "S-BYTES",
    "S-STAGED-EQUAL",
    "S-SOURCE-UNCHANGED",
];

/// The phases of the source/backing hash records (contract S-SOURCE-UNCHANGED).
pub const SOURCE_PHASES: [&str; 3] = [
    "before_load",
    "after_host_selection",
    "after_native_execution",
];

/// Measured counter deltas for ONE side's bridge call (contract N-COMP-ARRAYS,
/// manifest `measured_counter_deltas.per_side`): imports, result handles
/// created, adopted, freed on an error path, array frees.
pub const PER_SIDE_COUNTERS: [(&str, u64); 5] = [
    ("imports", 4),
    ("result_handles_created", 3),
    ("result_handles_adopted", 3),
    ("result_handles_freed_on_error_path", 0),
    ("array_free_calls", 7),
];

/// MLX-C numerical calls issued by ONE executed side, pinned from the bridge
/// source before the first run (plan section 3, "the integration owner pins
/// its expected value from the bridge source"), never from an observation.
/// `bridge::qmm_inner` on BF16 metadata issues, through `ffi::numerical`:
/// two `mlx_astype` (`NativeContext::astype_f32`), one
/// `mlx_quantized_matmul`, and `NativeArray::evaluate`'s `mlx_array_eval` plus
/// `NativeContext::synchronize`'s `mlx_synchronize`. The device-fact queries,
/// the memory readings and the host-copy accessors are not counted calls.
pub const PER_SIDE_NUMERICAL_CALLS: u64 = 5;

/// Report schema written by the compose child.
pub const CHILD_REPORT_SCHEMA: &str = "pulsarmlx.f020.slice2c-child-report/1.0.0";
/// Summary schema written by the composition parent.
pub const PARENT_SUMMARY_SCHEMA: &str = "pulsarmlx.f020.slice2c-qualification/1.0.0";

/// The Slice 2B child-report volatile fields of the regression proof
/// (contract execution.slice_2b_regression.primary_b_same_run_differential
/// .volatile_fields, V1-V4), recorded here so the compare script and the
/// evidence name the same list.
pub const SLICE2B_REGRESSION_VOLATILE_FIELDS: [&str; 4] = [
    "provenance.build.qualify_executable_sha256",
    "cases[*].stats.e5_peak_memory.active_before",
    "cases[*].stats.e5_peak_memory.peak_after",
    "cases[*].stats.e5_peak_memory.peak_delta_ge_output_nbytes",
];

/// Result of the frozen-population validation.
#[derive(Clone, Debug)]
pub struct PopulationCheck {
    pub contract_sha256: String,
    pub plan_sha256: String,
    pub generator_sha256: String,
    pub generator_test_sha256: String,
    pub manifest_sha256: String,
    pub files_listing_sha256: String,
    pub listed_file_count: usize,
    pub case_count: usize,
    pub checkpoint_files_checked: usize,
    pub standalone_files_checked: usize,
    pub generator_check: Option<String>,
    pub slice2b: crate::fixture::PopulationCheck,
}

fn err<T>(msg: impl Into<String>) -> Result<T, FixtureError> {
    Err(FixtureError(msg.into()))
}

fn read(root: &Path, rel: &str) -> Result<Vec<u8>, FixtureError> {
    std::fs::read(root.join(rel)).map_err(|e| FixtureError(format!("read {rel}: {e}")))
}

fn read_frozen(root: &Path, rel: &str, want: &str) -> Result<Vec<u8>, FixtureError> {
    let raw = read(root, rel)?;
    let got = sha256_hex(&raw);
    if got != want {
        return err(format!("{rel}: sha256 {got} != frozen {want}"));
    }
    Ok(raw)
}

fn files_under(dir: &Path, rel: &Path, out: &mut Vec<String>) -> Result<(), FixtureError> {
    let rd = std::fs::read_dir(dir.join(rel))
        .map_err(|e| FixtureError(format!("{}: {e}", rel.display())))?;
    for entry in rd {
        let entry = entry.map_err(|e| FixtureError(e.to_string()))?;
        let ty = entry.file_type().map_err(|e| FixtureError(e.to_string()))?;
        let child = rel.join(entry.file_name());
        if ty.is_dir() {
            files_under(dir, &child, out)?;
        } else if ty.is_file() {
            out.push(child.to_string_lossy().into_owned());
        } else {
            return err(format!("{}: not a regular file", child.display()));
        }
    }
    Ok(())
}

/// The listing hash exactly as the contract's method computes it, over the
/// files present under `checkpoints`, `mutations` and `standalone`.
pub fn files_listing(fixture_dir: &Path) -> Result<(String, Vec<String>), FixtureError> {
    let mut files = Vec::new();
    for top in ["checkpoints", "mutations", "standalone"] {
        files_under(fixture_dir, Path::new(top), &mut files)?;
    }
    // LC_ALL=C sort: byte order.
    files.sort_by(|a, b| a.as_bytes().cmp(b.as_bytes()));
    let mut listing = String::new();
    for rel in &files {
        let data = std::fs::read(fixture_dir.join(rel)).map_err(|e| FixtureError(e.to_string()))?;
        let _ = writeln!(listing, "{}  {}", sha256_hex(&data), rel);
    }
    Ok((sha256_hex(listing.as_bytes()), files))
}

/// The raw Slice 2C manifest document (the Slice 2B parser keeps only the
/// fields it knows; composition needs the rest).
pub fn manifest_document(raw: &[u8]) -> Result<Value, FixtureError> {
    serde_json::from_slice(raw).map_err(|e| FixtureError(format!("manifest JSON: {e}")))
}

/// Validate the frozen composition population rooted at `root`, and the six
/// Slice 2B identities (contract, plan, pins, generator, manifest, case
/// listing) through the unchanged Slice 2B validation. `python` runs the
/// composition generator's `--check` when given.
pub fn validate_population(
    root: &Path,
    python: Option<&str>,
) -> Result<(Manifest, Value, PopulationCheck), FixtureError> {
    // The six Slice 2B hashes (its generator --check is not re-run here).
    let (_, slice2b) = fixture::validate_population(root, None)?;

    let contract = read_frozen(root, CONTRACT_PATH, CONTRACT_SHA256)?;
    let contract_doc: Value = serde_json::from_slice(&contract)
        .map_err(|e| FixtureError(format!("contract JSON: {e}")))?;
    if contract_doc["schema"].as_str() != Some(CONTRACT_SCHEMA) {
        return err("contract schema differs from the compiled-in identity");
    }
    let fp = &contract_doc["frozen_population"];
    if fp["manifest_sha256"].as_str() != Some(MANIFEST_SHA256)
        || fp["generator_sha256"].as_str() != Some(GENERATOR_SHA256)
        || fp["files_listing_sha256"].as_str() != Some(FILES_LISTING_SHA256)
        || fp["case_count"].as_u64() != Some(CASE_COUNT as u64)
    {
        return err("contract frozen_population differs from the compiled-in identities");
    }
    if contract_doc["inheritance"]["slice_2b_contract"]["sha256"].as_str()
        != Some(SLICE2B_CONTRACT_SHA256)
    {
        return err("contract inheritance differs from the Slice 2B contract identity");
    }
    let order: Vec<&str> = contract_doc["composition_refusals"]["order"]
        .as_array()
        .map(|a| a.iter().filter_map(|r| r["id"].as_str()).collect())
        .unwrap_or_default();
    if order != COMPOSITION_REFUSAL_ORDER {
        return err(format!("contract refusal order {order:?} differs"));
    }
    let plan_sha = sha256_hex(&read_frozen(root, PLAN_PATH, PLAN_SHA256)?);
    let generator_sha = sha256_hex(&read_frozen(root, GENERATOR_PATH, GENERATOR_SHA256)?);
    let generator_test_sha = sha256_hex(&read_frozen(
        root,
        GENERATOR_TEST_PATH,
        GENERATOR_TEST_SHA256,
    )?);
    let manifest_raw = read_frozen(root, MANIFEST_PATH, MANIFEST_SHA256)?;
    let manifest = parse_manifest(&manifest_raw)?;
    let doc = manifest_document(&manifest_raw)?;
    if doc["schema"].as_str() != Some(MANIFEST_SCHEMA)
        || manifest.generator_sha256 != GENERATOR_SHA256
        || doc["files_listing_sha256"].as_str() != Some(FILES_LISTING_SHA256)
        || doc["inherits"]["slice2b_contract_sha256"].as_str() != Some(SLICE2B_CONTRACT_SHA256)
    {
        return err("manifest header differs from the frozen identities");
    }
    if manifest.cases.len() != CASE_COUNT || doc["case_count"].as_u64() != Some(CASE_COUNT as u64) {
        return err(format!("manifest case count {}", manifest.cases.len()));
    }
    let ids: BTreeSet<&str> = manifest.cases.iter().map(|c| c.id.as_str()).collect();
    if ids.len() != CASE_COUNT {
        return err("duplicate case id in manifest");
    }
    let manifest_order: Vec<&str> = doc["composition_refusal_order"]
        .as_array()
        .map(|a| a.iter().filter_map(Value::as_str).collect())
        .unwrap_or_default();
    // The manifest omits C-R-CATALOG (no Slice 2C probe; contract evaluation_rule).
    if manifest_order != COMPOSITION_REFUSAL_ORDER[1..] {
        return err(format!("manifest refusal order {manifest_order:?} differs"));
    }

    let fixture_dir = root.join(FIXTURE_DIR);
    // Listing, and no file outside it except manifest.json.
    let (listing_sha, listed) = files_listing(&fixture_dir)?;
    if listing_sha != FILES_LISTING_SHA256 || listed.len() != LISTED_FILE_COUNT {
        return err(format!(
            "files listing sha256 {listing_sha} ({} files) != frozen",
            listed.len()
        ));
    }
    let mut top = BTreeSet::new();
    for entry in std::fs::read_dir(&fixture_dir).map_err(|e| FixtureError(e.to_string()))? {
        let entry = entry.map_err(|e| FixtureError(e.to_string()))?;
        top.insert(entry.file_name().to_string_lossy().into_owned());
    }
    let want_top: BTreeSet<String> = ["checkpoints", "manifest.json", "mutations", "standalone"]
        .iter()
        .map(|s| s.to_string())
        .collect();
    if top != want_top {
        return err(format!("unexpected entries in {FIXTURE_DIR}: {top:?}"));
    }
    // Every checkpoint file against the manifest.
    let mut accounted: BTreeSet<String> = BTreeSet::new();
    let mut checkpoint_files = 0usize;
    let cks = doc["checkpoints"]
        .as_object()
        .ok_or_else(|| FixtureError("manifest checkpoints".into()))?;
    for (ck, spec) in cks {
        let dir = spec["dir"]
            .as_str()
            .ok_or_else(|| FixtureError(format!("{ck}: dir")))?;
        let files = spec["files"]
            .as_object()
            .ok_or_else(|| FixtureError(format!("{ck}: files")))?;
        for (name, f) in files {
            let rel = format!("{dir}/{name}");
            let data = std::fs::read(fixture_dir.join(&rel))
                .map_err(|e| FixtureError(format!("{rel}: {e}")))?;
            if Some(sha256_hex(&data).as_str()) != f["sha256"].as_str()
                || Some(data.len() as u64) != f["bytes"].as_u64()
            {
                return err(format!("{rel}: sha256 or size differs from the manifest"));
            }
            accounted.insert(rel);
            checkpoint_files += 1;
        }
    }
    // Every standalone file against the manifest.
    let mut standalone = 0usize;
    for c in &manifest.cases {
        if let Some(file) = &c.file {
            let data = std::fs::read(fixture_dir.join(file))
                .map_err(|e| FixtureError(format!("{file}: {e}")))?;
            if Some(sha256_hex(&data)) != c.file_sha256 {
                return err(format!("{file}: sha256 differs from the manifest"));
            }
            accounted.insert(file.clone());
            standalone += 1;
        }
    }
    // The mutated configuration(s) named by mutation cases.
    for c in doc["cases"].as_array().into_iter().flatten() {
        if let Some(cfg) = c["composition"]["mutation"]["config"].as_str() {
            accounted.insert(cfg.to_string());
        }
    }
    let listed_set: BTreeSet<String> = listed.into_iter().collect();
    if listed_set != accounted {
        return err(format!(
            "listed files and manifest-accounted files differ: {:?}",
            listed_set
                .symmetric_difference(&accounted)
                .collect::<Vec<_>>()
        ));
    }

    let generator_check = match python {
        None => None,
        Some(py) => {
            let out = std::process::Command::new(py)
                .args(["-I", "-B", GENERATOR_PATH, "--out", FIXTURE_DIR, "--check"])
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
        contract_sha256: CONTRACT_SHA256.to_string(),
        plan_sha256: plan_sha,
        generator_sha256: generator_sha,
        generator_test_sha256: generator_test_sha,
        manifest_sha256: manifest.raw_sha256.clone(),
        files_listing_sha256: listing_sha,
        listed_file_count: listed_set.len(),
        case_count: manifest.cases.len(),
        checkpoint_files_checked: checkpoint_files,
        standalone_files_checked: standalone,
        generator_check,
        slice2b,
    };
    Ok((manifest, doc, check))
}

/// Manifest case documents by id (the raw JSON, for composition fields).
pub fn case_documents(doc: &Value) -> BTreeMap<String, Value> {
    doc["cases"]
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(|c| c["id"].as_str().map(|id| (id.to_string(), c.clone())))
        .collect()
}

/// `<root>/fixtures/native-composition`.
pub fn fixture_dir(root: &Path) -> PathBuf {
    root.join(FIXTURE_DIR)
}
