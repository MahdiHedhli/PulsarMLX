//! A header-only census of a checkpoint that stays where it is.
//!
//! `Checkpoint::from_headers` builds the catalog from header bytes alone, so a
//! compatibility observation over a real checkpoint needs its headers and
//! nothing else: **no payload byte is read, and the checkpoint does not move.**
//! Reads are refused in that mode, which is what makes the claim checkable
//! rather than promised.
//!
//! This is an observation tool, not a gate. It runs by hand, against a
//! directory of header bytes that is never committed, and what it produces is
//! labelled a compatibility observation and not a qualification.
//!
//! Input directory layout:
//!
//! ```text
//! <dir>/shards.json                  [{ file, file_len, header_file, header_len, header_sha256 }]
//! <dir>/headers/<shard>.header       the 8-byte prefix and the header JSON, verbatim
//! <dir>/config.json                  the checkpoint's configuration
//! <dir>/model.safetensors.index.json the shard index
//! ```
//!
//! ```text
//! cargo run -p mlx-affine --example header_census -- <dir> <output.json>
//! ```

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

use mlx_affine::module::module_paths;
use mlx_affine::{classify_module, AffineError, ModuleKind, QuantizationConfig};
use safetensors_catalog::{Checkpoint, Dtype};
use serde_json::{json, Map, Value};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut arguments = std::env::args().skip(1);
    let directory = PathBuf::from(
        arguments
            .next()
            .ok_or("usage: header_census <dir> <output.json>")?,
    );
    let output = PathBuf::from(
        arguments
            .next()
            .ok_or("usage: header_census <dir> <output.json>")?,
    );

    let shards: Value =
        serde_json::from_str(&std::fs::read_to_string(directory.join("shards.json"))?)?;
    let mut supplied = Vec::new();
    let mut provenance = Vec::new();
    for entry in shards["shards"]
        .as_array()
        .ok_or("shards.json has no shards array")?
    {
        let file = entry["file"]
            .as_str()
            .ok_or("shard entry has no file")?
            .to_string();
        let file_len = entry["file_len"]
            .as_u64()
            .ok_or("shard entry has no file_len")?;
        let bytes = std::fs::read(directory.join(entry["header_file"].as_str().unwrap()))?;
        provenance.push(json!({
            "file": file,
            "file_len": file_len,
            "header_len": entry["header_len"],
            "header_sha256": entry["header_sha256"],
            "header_bytes_supplied": bytes.len(),
        }));
        supplied.push((file, file_len, bytes));
    }

    let index = std::fs::read_to_string(directory.join("model.safetensors.index.json"))?;
    let config_text = std::fs::read_to_string(directory.join("config.json"))?;

    let root_name = directory
        .file_name()
        .map(|name| name.to_string_lossy().into_owned())
        .unwrap_or_else(|| "checkpoint".to_string());

    let checkpoint = match Checkpoint::from_headers(&root_name, supplied, Some(&index)) {
        Ok(checkpoint) => checkpoint,
        Err(error) => {
            // A refusal on real metadata is a finding, recorded, not hidden.
            let report = json!({
                "schema": "pulsarmlx.f020.metadata-compatibility/1.0.0",
                "label": "compatibility observation; not Q0; no payload read",
                "result": "REFUSED",
                "refusal": error.to_string(),
                "shards": provenance,
            });
            write(&output, &report)?;
            eprintln!("header_census: the catalog refused this checkpoint: {error}");
            return Ok(());
        }
    };

    let config = match QuantizationConfig::from_config_json(&config_text) {
        Ok(config) => Some(config),
        Err(AffineError::NoQuantizationConfig) => None,
        Err(error) => {
            let report = json!({
                "schema": "pulsarmlx.f020.metadata-compatibility/1.0.0",
                "label": "compatibility observation; not Q0; no payload read",
                "result": "REFUSED",
                "refusal": error.to_string(),
                "shards": provenance,
            });
            write(&output, &report)?;
            eprintln!("header_census: the configuration was refused: {error}");
            return Ok(());
        }
    };

    let mut specs: BTreeMap<String, u64> = BTreeMap::new();
    let mut unquantized_dtypes: BTreeMap<String, u64> = BTreeMap::new();
    let mut refusals: BTreeMap<String, u64> = BTreeMap::new();
    let mut refusal_examples: BTreeMap<String, String> = BTreeMap::new();
    let mut leading_shapes: BTreeMap<String, u64> = BTreeMap::new();
    let mut vision_unquantized = 0u64;
    let mut vision_total = 0u64;
    let mut modules = 0u64;

    for module in module_paths(checkpoint.catalog()) {
        modules += 1;
        let is_vision = module.starts_with("vision_model");
        if is_vision {
            vision_total += 1;
        }
        match classify_module(checkpoint.catalog(), config.as_ref(), &module) {
            Ok(ModuleKind::Quantized(triple)) => {
                *specs
                    .entry(format!(
                        "{}-bit group {}",
                        triple.spec.bits.get(),
                        triple.spec.group_size.get()
                    ))
                    .or_default() += 1;
                let leading = if triple.leading.is_empty() {
                    "plain".to_string()
                } else {
                    format!("{:?}", triple.leading)
                };
                *leading_shapes.entry(leading).or_default() += 1;
            }
            Ok(ModuleKind::Unquantized(tensor)) => {
                *unquantized_dtypes
                    .entry(tensor.dtype.to_string())
                    .or_default() += 1;
                if is_vision {
                    vision_unquantized += 1;
                }
            }
            Err(error) => {
                let name = variant(&error);
                *refusals.entry(name.to_string()).or_default() += 1;
                refusal_examples
                    .entry(name.to_string())
                    .or_insert_with(|| format!("{module}: {error}"));
            }
        }
    }

    let mut dtypes: BTreeMap<String, u64> = BTreeMap::new();
    let mut vision_tensors = 0u64;
    let mut vision_bytes = 0u64;
    for (name, tensor) in checkpoint.catalog().iter() {
        *dtypes.entry(tensor.dtype.to_string()).or_default() += 1;
        if name.starts_with("vision_model") {
            vision_tensors += 1;
            vision_bytes += tensor.byte_len;
            if tensor.dtype != Dtype::Bf16 {
                eprintln!("header_census: vision tensor {name} is {}", tensor.dtype);
            }
        }
    }

    let declared_total = checkpoint.index().and_then(|index| index.total_size);
    let mut report = Map::new();
    report.insert(
        "schema".into(),
        json!("pulsarmlx.f020.metadata-compatibility/1.0.0"),
    );
    report.insert(
        "label".into(),
        json!("compatibility observation; not Q0; no payload read"),
    );
    report.insert("result".into(), json!("OBSERVED"));
    report.insert("payload_bytes_read".into(), json!(0));
    report.insert(
        "reads_possible".into(),
        json!(checkpoint.is_backed_by_files()),
    );
    report.insert("shard_count".into(), json!(checkpoint.shards().len()));
    report.insert("tensor_count".into(), json!(checkpoint.catalog().len()));
    report.insert("module_count".into(), json!(modules));
    report.insert(
        "catalog_digest_sha256".into(),
        json!(checkpoint.catalog_digest_hex()?),
    );
    report.insert("declared_total_size".into(), json!(declared_total));
    report.insert(
        "catalog_payload_bytes".into(),
        json!(checkpoint.payload_bytes()),
    );
    report.insert(
        "declared_total_size_matches_catalog".into(),
        json!(declared_total == Some(checkpoint.payload_bytes())),
    );
    report.insert("dtype_census".into(), json!(dtypes));
    report.insert("resolved_specs".into(), json!(specs));
    report.insert("quantized_leading_shapes".into(), json!(leading_shapes));
    report.insert("unquantized_dtypes".into(), json!(unquantized_dtypes));
    report.insert("refusals".into(), json!(refusals));
    report.insert("refusal_examples".into(), json!(refusal_examples));
    report.insert(
        "vision".into(),
        json!({
            "tensors": vision_tensors,
            "bytes": vision_bytes,
            "modules": vision_total,
            "unquantized_modules": vision_unquantized,
        }),
    );
    report.insert(
        "configuration".into(),
        json!({
            "default": config.as_ref().map(|c| json!({
                "bits": c.default_spec().bits.get(),
                "group_size": c.default_spec().group_size.get(),
                "mode": c.default_spec().mode.as_str(),
            })),
            "override_count": config.as_ref().map(|c| c.overrides().len()),
        }),
    );
    report.insert(
        "gap_bytes_per_shard".into(),
        json!(checkpoint
            .headers()
            .iter()
            .map(|header| header.gap_bytes)
            .collect::<Vec<_>>()),
    );
    report.insert(
        "shard_metadata".into(),
        json!(checkpoint
            .headers()
            .iter()
            .map(|header| header.metadata.clone())
            .collect::<Vec<_>>()),
    );
    report.insert("shards".into(), json!(provenance));

    write(&output, &Value::Object(report))?;
    println!("header_census: wrote {}", output.display());
    Ok(())
}

fn write(output: &Path, report: &Value) -> std::io::Result<()> {
    std::fs::write(output, serde_json::to_string_pretty(report).unwrap() + "\n")
}

fn variant(error: &AffineError) -> &'static str {
    match error {
        AffineError::UnsupportedQuantization { .. } => "UnsupportedQuantization",
        AffineError::MissingDefaultSpec { .. } => "MissingDefaultSpec",
        AffineError::InconsistentConfig => "InconsistentConfig",
        AffineError::UnsupportedOverrideValue { .. } => "UnsupportedOverrideValue",
        AffineError::InvalidConfigJson { .. } => "InvalidConfigJson",
        AffineError::NoQuantizationConfig => "NoQuantizationConfig",
        AffineError::IncompleteTriple { .. } => "IncompleteTriple",
        AffineError::ScalesBiasesMismatch { .. } => "ScalesBiasesMismatch",
        AffineError::OverrideWithoutScales { .. } => "OverrideWithoutScales",
        AffineError::AmbiguousQuantization { .. } => "AmbiguousQuantization",
        AffineError::InconsistentOverride { .. } => "InconsistentOverride",
        AffineError::Overflow { .. } => "Overflow",
        AffineError::UnknownModule { .. } => "UnknownModule",
        AffineError::IndexOutOfBounds { .. } => "IndexOutOfBounds",
        AffineError::GeometryMismatch { .. } => "GeometryMismatch",
        _ => "<unlisted>",
    }
}
