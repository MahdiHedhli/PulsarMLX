//! The header-only census itself, with no file system access of its own.
//!
//! Everything this module knows about a checkpoint arrives through a
//! [`MetadataSource`], which is asked for exactly four kinds of name:
//! `shards.json`, `config.json`, `model.safetensors.index.json`, and the
//! `header_file` of each shard that `shards.json` lists. The catalog is built
//! only by [`Checkpoint::from_headers`], which holds no file descriptor and
//! refuses every read with `NoBackingFile`. There is no path from here to a
//! payload byte: no shard is opened, and no read accessor is called.
//!
//! `tests/census_metadata_only.rs` includes this file, runs it over a
//! committed header-only fixture through an instrumented source, and scans
//! this file's code for any read API.
//!
//! Model neutrality: nothing here knows a model. Categories come from a
//! caller-supplied rules document; the only name processing is replacing
//! all-digit dot-separated components with `*` to group repeated structures,
//! which is a property of dotted paths and not of any model.

use std::collections::{BTreeMap, BTreeSet};

use mlx_affine::module::module_paths;
use mlx_affine::{classify_all, AffineError, ModuleKind, QuantizationConfig};
use safetensors_catalog::{hex, Checkpoint, INDEX_FILE_NAME, MAX_HEADER_BYTES};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};

pub const SCHEMA: &str = "pulsarmlx.f020.metadata-census/1.0.0";
pub const LABEL: &str = "header-only metadata compatibility observation; not Q0 payload \
     identity; not numerical qualification; no payload byte read";
pub const SHARDS_FILE: &str = "shards.json";
pub const CONFIG_FILE: &str = "config.json";

/// Rules documents this census understands. `1.0.0` groups carry `name`,
/// `prefix` and `expect_unquantized_dtype`; `1.1.0` adds the optional
/// matchers and expectations below. Unknown members are refused, so a typo in
/// a rule cannot silently match nothing.
pub const RULES_SCHEMAS: [&str; 2] = [
    "pulsarmlx.f020.header-census-rules/1.0.0",
    "pulsarmlx.f020.header-census-rules/1.1.0",
];
const GROUP_MEMBERS: [&str; 9] = [
    "name",
    "prefix",
    "contains",
    "contains_any",
    "expect_unquantized_dtype",
    "expect",
    "why",
    "basis",
    "note",
];

/// The only way the census obtains bytes.
pub trait MetadataSource {
    fn read(&self, name: &str) -> Result<Vec<u8>, String>;
}

/// The report, and the header-only checkpoint when the catalog admitted it.
pub struct Census {
    pub report: Value,
    /// Kept so `tests/census_metadata_only.rs` can probe every read path of
    /// the very catalog the census used; the example itself only writes the
    /// report.
    #[allow(dead_code)]
    pub checkpoint: Option<Checkpoint>,
}

/// One caller-supplied categorization rule. A prefix or substring means
/// nothing to this crate; it is only what the caller asked to be counted.
#[derive(Debug, Clone)]
pub struct Group {
    pub name: String,
    pub prefix: Option<String>,
    pub contains: Option<String>,
    pub contains_any: Vec<String>,
    pub expect_unquantized_dtype: Option<String>,
    /// `quantized`, `unquantized` or `absent`.
    pub expect: Option<String>,
}

impl Group {
    pub fn matches(&self, name: &str) -> bool {
        let prefix_ok = match &self.prefix {
            Some(prefix) => name.starts_with(prefix.as_str()),
            None => true,
        };
        let contains_ok = match &self.contains {
            Some(needle) => name.contains(needle.as_str()),
            None => true,
        };
        prefix_ok
            && contains_ok
            && (self.contains_any.is_empty()
                || self.contains_any.iter().any(|c| name.contains(c.as_str())))
    }

    fn to_json(&self) -> Value {
        json!({
            "name": self.name,
            "prefix": self.prefix,
            "contains": self.contains,
            "contains_any": self.contains_any,
            "expect_unquantized_dtype": self.expect_unquantized_dtype,
            "expect": self.expect,
        })
    }
}

fn optional_string(group: &Map<String, Value>, key: &str) -> Result<Option<String>, String> {
    match group.get(key) {
        None | Some(Value::Null) => Ok(None),
        Some(Value::String(text)) => Ok(Some(text.clone())),
        Some(other) => Err(format!("rule member {key} is not a string: {other}")),
    }
}

/// Parse a rules document. An empty list means no categorization at all.
pub fn parse_rules(document: &Value) -> Result<Vec<Group>, String> {
    let schema = document["schema"].as_str().unwrap_or("");
    if !RULES_SCHEMAS.contains(&schema) {
        return Err(format!("unknown rules schema {schema:?}"));
    }
    let mut groups = Vec::new();
    let mut names = BTreeSet::new();
    for entry in document["groups"]
        .as_array()
        .ok_or("the rules file needs a `groups` array")?
    {
        let object = entry.as_object().ok_or("a rule group is not an object")?;
        for key in object.keys() {
            if !GROUP_MEMBERS.contains(&key.as_str()) {
                return Err(format!("unknown rule member {key:?}"));
            }
        }
        let name = optional_string(object, "name")?.ok_or("a rule group has no name")?;
        if !names.insert(name.clone()) {
            return Err(format!("rule group {name:?} appears twice"));
        }
        let contains_any = match object.get("contains_any") {
            None => Vec::new(),
            Some(Value::Array(items)) => items
                .iter()
                .map(|item| {
                    item.as_str()
                        .map(str::to_string)
                        .ok_or_else(|| format!("{name}: contains_any holds a non-string"))
                })
                .collect::<Result<Vec<_>, _>>()?,
            Some(_) => return Err(format!("{name}: contains_any is not an array")),
        };
        let group = Group {
            prefix: optional_string(object, "prefix")?,
            contains: optional_string(object, "contains")?,
            contains_any,
            expect_unquantized_dtype: optional_string(object, "expect_unquantized_dtype")?,
            expect: optional_string(object, "expect")?,
            name,
        };
        if group.prefix.as_deref().unwrap_or("").is_empty()
            && group.contains.as_deref().unwrap_or("").is_empty()
            && group.contains_any.iter().all(String::is_empty)
        {
            return Err(format!("{}: a group needs a non-empty matcher", group.name));
        }
        if let Some(expect) = &group.expect {
            if !["quantized", "unquantized", "absent"].contains(&expect.as_str()) {
                return Err(format!("{}: unknown expectation {expect:?}", group.name));
            }
        }
        groups.push(group);
    }
    Ok(groups)
}

fn sha256_hex(bytes: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    hex(&hasher.finalize())
}

fn text(source: &dyn MetadataSource, name: &str) -> Result<String, String> {
    String::from_utf8(source.read(name)?).map_err(|_| format!("{name} is not UTF-8"))
}

/// Replace every all-digit dot-separated component with `*`; return the
/// pattern and the replaced components.
pub fn family(name: &str) -> (String, Vec<String>) {
    let mut indices = Vec::new();
    let parts: Vec<&str> = name
        .split('.')
        .map(|part| {
            if !part.is_empty() && part.bytes().all(|byte| byte.is_ascii_digit()) {
                indices.push(part.to_string());
                "*"
            } else {
                part
            }
        })
        .collect();
    (parts.join("."), indices)
}

/// `["0","1","2","6"]` becomes `"0-2,6"` when every index is one integer.
pub fn collapse(indices: &BTreeSet<Vec<String>>) -> Value {
    let singles: Option<Vec<u64>> = indices
        .iter()
        .map(|index| {
            if index.len() == 1 {
                index[0].parse::<u64>().ok()
            } else {
                None
            }
        })
        .collect();
    match singles {
        Some(mut numbers) if !numbers.is_empty() => {
            numbers.sort_unstable();
            let mut runs: Vec<String> = Vec::new();
            let mut start = numbers[0];
            let mut previous = numbers[0];
            for &number in &numbers[1..] {
                if number == previous + 1 {
                    previous = number;
                    continue;
                }
                runs.push(span(start, previous));
                start = number;
                previous = number;
            }
            runs.push(span(start, previous));
            json!(runs.join(","))
        }
        _ if indices.iter().all(Vec::is_empty) => Value::Null,
        _ => json!(indices
            .iter()
            .map(|index| index.join("/"))
            .collect::<Vec<_>>()),
    }
}

fn span(start: u64, end: u64) -> String {
    if start == end {
        start.to_string()
    } else {
        format!("{start}-{end}")
    }
}

fn variant(error: &AffineError) -> &'static str {
    match error {
        AffineError::UnsupportedQuantization { .. } => "UnsupportedQuantization",
        AffineError::MissingDefaultSpec { .. } => "MissingDefaultSpec",
        AffineError::InconsistentConfig => "InconsistentConfig",
        AffineError::UnresolvedOverride { .. } => "UnresolvedOverride",
        AffineError::UnsupportedOverrideValue { .. } => "UnsupportedOverrideValue",
        AffineError::InvalidConfigJson { .. } => "InvalidConfigJson",
        AffineError::DuplicateConfigKey { .. } => "DuplicateConfigKey",
        AffineError::NoQuantizationConfig => "NoQuantizationConfig",
        AffineError::IncompleteTriple { .. } => "IncompleteTriple",
        AffineError::ScalesBiasesMismatch { .. } => "ScalesBiasesMismatch",
        AffineError::OverrideWithoutScales { .. } => "OverrideWithoutScales",
        AffineError::AmbiguousQuantization { .. } => "AmbiguousQuantization",
        AffineError::InconsistentOverride { .. } => "InconsistentOverride",
        AffineError::Overflow { .. } => "Overflow",
        AffineError::UnknownModule { .. } => "UnknownModule",
        AffineError::IndexOutOfBounds { .. } => "IndexOutOfBounds",
        AffineError::InvalidTensorMeta { .. } => "InvalidTensorMeta",
        AffineError::GeometryMismatch { .. } => "GeometryMismatch",
        _ => "<unlisted>",
    }
}

const NOT_CLAIMED: [&str; 6] = [
    "not Q0: payload identity was not verified by this census",
    "not numerical qualification",
    "header sha256 identifies header bytes only",
    "no payload byte read",
    "nothing downloaded",
    "no model executed",
];

fn refused(stage: &str, detail: String, shards: Vec<Value>) -> Value {
    json!({
        "schema": SCHEMA,
        "label": LABEL,
        "not_claimed": NOT_CLAIMED,
        "result": "REFUSED",
        "refused_at": stage,
        "refusal": detail,
        "shards": shards,
    })
}

/// Tallies for one caller-supplied group.
#[derive(Default)]
struct GroupTally {
    tensors: u64,
    bytes: u64,
    dtypes: BTreeMap<String, u64>,
    modules: u64,
    quantized: u64,
    unquantized: u64,
    refused: u64,
    orphans: u64,
    surprises: Vec<String>,
}

/// A family variant key: the fields that must agree for two members to be
/// one row of the report, serialized.
type VariantKey = String;

#[derive(Default)]
struct FamilyTally {
    members: u64,
    variants: BTreeMap<VariantKey, (Value, u64, BTreeSet<Vec<String>>)>,
}

impl FamilyTally {
    fn add(&mut self, description: Value, indices: Vec<String>) {
        self.members += 1;
        let key = description.to_string();
        let entry = self
            .variants
            .entry(key)
            .or_insert_with(|| (description, 0, BTreeSet::new()));
        entry.1 += 1;
        entry.2.insert(indices);
    }

    fn to_json(&self) -> Value {
        json!({
            "members": self.members,
            "variants": self
                .variants
                .values()
                .map(|(description, count, indices)| {
                    let mut row = description.as_object().cloned().unwrap_or_default();
                    row.insert("count".into(), json!(count));
                    row.insert("indices".into(), collapse(indices));
                    Value::Object(row)
                })
                .collect::<Vec<_>>(),
        })
    }
}

fn families_json(families: &BTreeMap<String, FamilyTally>) -> Value {
    Value::Object(
        families
            .iter()
            .map(|(pattern, tally)| (pattern.clone(), tally.to_json()))
            .collect(),
    )
}

/// Run the census. `rules` is an already-parsed rules list.
pub fn run(source: &dyn MetadataSource, rules: &[Group]) -> Result<Census, String> {
    let shards_document: Value = serde_json::from_str(&text(source, SHARDS_FILE)?)
        .map_err(|error| format!("{SHARDS_FILE}: {error}"))?;
    let entries = shards_document["shards"]
        .as_array()
        .ok_or("shards.json has no shards array")?;

    let mut supplied = Vec::new();
    let mut provenance = Vec::new();
    for entry in entries {
        let file = entry["file"].as_str().ok_or("shard entry has no file")?;
        let file_len = entry["file_len"]
            .as_u64()
            .ok_or("shard entry has no file_len")?;
        let header_file = entry["header_file"]
            .as_str()
            .ok_or("shard entry has no header_file")?;
        let recorded_len = entry["header_len"].as_u64();
        let recorded_sha = entry["header_sha256"].as_str().map(str::to_string);
        let bytes = source.read(header_file)?;
        if bytes.len() as u64 > 8 + MAX_HEADER_BYTES {
            return Err(format!("{header_file}: more bytes than a bounded header"));
        }
        let declared = if bytes.len() >= 8 {
            let mut prefix = [0u8; 8];
            prefix.copy_from_slice(&bytes[..8]);
            Some(u64::from_le_bytes(prefix))
        } else {
            None
        };
        let computed = sha256_hex(&bytes);
        provenance.push(json!({
            "file": file,
            "file_len": file_len,
            "header_len_recorded": recorded_len,
            "header_len_declared": declared,
            "header_bytes_supplied": bytes.len(),
            "header_is_exactly_prefix_plus_n": declared.map(|n| n + 8 == bytes.len() as u64),
            "header_sha256_recorded": recorded_sha,
            "header_sha256": computed,
            "header_sha256_matches_record": recorded_sha.as_deref() == Some(computed.as_str()),
        }));
        supplied.push((file.to_string(), file_len, bytes));
    }

    let integrity_failures: Vec<String> = provenance
        .iter()
        .filter(|shard| {
            shard["header_sha256_matches_record"] != json!(true)
                || shard["header_is_exactly_prefix_plus_n"] != json!(true)
                || shard["header_len_recorded"] != shard["header_len_declared"]
        })
        .map(|shard| shard["file"].as_str().unwrap_or("?").to_string())
        .collect();
    if !integrity_failures.is_empty() {
        return Ok(Census {
            report: refused(
                "header_integrity",
                format!(
                    "supplied header bytes disagree with shards.json for {integrity_failures:?}"
                ),
                provenance,
            ),
            checkpoint: None,
        });
    }

    let index_text = text(source, INDEX_FILE_NAME)?;
    let config_text = text(source, CONFIG_FILE)?;

    // The one constructor. It takes bytes, holds no descriptor, and refuses
    // every read with `NoBackingFile`.
    let checkpoint = match Checkpoint::from_headers("census", supplied, Some(&index_text)) {
        Ok(checkpoint) => checkpoint,
        Err(error) => {
            return Ok(Census {
                report: refused("catalog", error.to_string(), provenance),
                checkpoint: None,
            })
        }
    };
    let catalog = checkpoint.catalog();

    // ---- per shard: the extent identity, stated as a checked fact -------
    let mut per_shard_tensors: BTreeMap<u16, (u64, u64, u64)> = BTreeMap::new();
    for (_, tensor) in catalog.iter() {
        let entry = per_shard_tensors.entry(tensor.shard.0).or_default();
        entry.0 += 1;
        entry.1 = entry
            .1
            .checked_add(tensor.byte_len)
            .ok_or("per-shard byte total overflows u64")?;
        entry.2 = entry.2.max(tensor.data_end);
    }
    let mut shard_rows = Vec::new();
    let mut extent_ok = 0u64;
    for (position, (shard, header)) in checkpoint
        .shards()
        .iter()
        .zip(checkpoint.headers())
        .enumerate()
    {
        let (tensors, bytes, max_end) = per_shard_tensors
            .get(&(position as u16))
            .copied()
            .unwrap_or_default();
        let identity = bytes
            .checked_add(8)
            .and_then(|sum| sum.checked_add(header.header_len))
            == Some(shard.file_len);
        let max_end_ok = tensors == 0 || max_end == shard.file_len;
        if identity && max_end_ok && header.gap_bytes == 0 {
            extent_ok += 1;
        }
        let mut row = provenance[position]
            .as_object()
            .cloned()
            .unwrap_or_default();
        row.insert("tensor_count".into(), json!(tensors));
        row.insert("header_len".into(), json!(header.header_len));
        row.insert("data_len".into(), json!(header.data_len));
        row.insert("tensor_bytes".into(), json!(bytes));
        row.insert(
            "tensor_bytes_plus_8_plus_n_equals_file_len".into(),
            json!(identity),
        );
        row.insert("last_tensor_end_equals_file_len".into(), json!(max_end_ok));
        row.insert("gap_bytes".into(), json!(header.gap_bytes));
        row.insert("metadata".into(), json!(header.metadata));
        shard_rows.push(Value::Object(row));
    }

    // ---- index ----------------------------------------------------------
    let index = checkpoint.index().ok_or("the index was not retained")?;
    let payload_total = checkpoint
        .payload_bytes()
        .map_err(|error| error.to_string())?;
    let header_total: u64 = checkpoint.shards().iter().map(|s| 8 + s.header_len).sum();
    let file_total: u64 = checkpoint.shards().iter().map(|s| s.file_len).sum();
    let indexed_shards: BTreeSet<String> = index.shards().into_iter().collect();
    let supplied_shards: BTreeSet<String> = checkpoint
        .shards()
        .iter()
        .map(|s| s.file_name.clone())
        .collect();
    let index_names: BTreeSet<&String> = index.weight_map.keys().collect();
    let catalog_names: BTreeSet<&String> = catalog.names().collect();

    // ---- dtypes and tensor families --------------------------------------
    let mut dtypes: BTreeMap<String, (u64, u64)> = BTreeMap::new();
    let mut tensor_families: BTreeMap<String, FamilyTally> = BTreeMap::new();
    for (name, tensor) in catalog.iter() {
        let entry = dtypes.entry(tensor.dtype.to_string()).or_default();
        entry.0 += 1;
        entry.1 += tensor.byte_len;
        let (pattern, indices) = family(name);
        tensor_families.entry(pattern).or_default().add(
            json!({"dtype": tensor.dtype.as_str(), "shape": tensor.shape}),
            indices,
        );
    }

    // ---- configuration -----------------------------------------------------
    let (config, config_json) = match QuantizationConfig::from_config_json(&config_text) {
        Ok(config) => {
            let default = config.default_spec();
            let mut values: BTreeMap<String, u64> = BTreeMap::new();
            let mut equal_to_default = 0u64;
            for spec in config.overrides().values() {
                *values
                    .entry(format!(
                        "bits {} group_size {} mode {}",
                        spec.bits.get(),
                        spec.group_size.get(),
                        spec.mode.as_str()
                    ))
                    .or_default() += 1;
                if *spec == default {
                    equal_to_default += 1;
                }
            }
            let summary = json!({
                "status": "PARSED",
                "default": {
                    "bits": default.bits.get(),
                    "group_size": default.group_size.get(),
                    "mode": default.mode.as_str(),
                },
                "override_count": config.overrides().len(),
                "override_values": values,
                "overrides_equal_to_default": equal_to_default,
            });
            (Some(config), summary)
        }
        Err(AffineError::NoQuantizationConfig) => (None, json!({"status": "ABSENT"})),
        Err(error) => (
            None,
            json!({
                "status": "REFUSED",
                "variant": variant(&error),
                "refusal": error.to_string(),
            }),
        ),
    };
    let config_refused = config_json["status"] == json!("REFUSED");

    // ---- modules -------------------------------------------------------------
    let paths = module_paths(catalog);
    let mut module_member_tensors: BTreeSet<String> = BTreeSet::new();
    for path in &paths {
        for suffix in [".weight", ".scales", ".biases"] {
            let name = format!("{path}{suffix}");
            if catalog.contains(&name) {
                module_member_tensors.insert(name);
            }
        }
    }
    let mut combos: BTreeMap<String, u64> = BTreeMap::new();
    let mut leading_shapes: BTreeMap<String, u64> = BTreeMap::new();
    let mut unquantized_dtypes: BTreeMap<String, u64> = BTreeMap::new();
    let mut refusals: BTreeMap<String, u64> = BTreeMap::new();
    let mut refusal_examples: BTreeMap<String, Vec<String>> = BTreeMap::new();
    let mut module_families: BTreeMap<String, FamilyTally> = BTreeMap::new();
    let mut resolution = BTreeMap::from([
        ("explicit_override".to_string(), 0u64),
        ("default".to_string(), 0u64),
    ]);
    let mut override_rows: BTreeMap<String, Value> = BTreeMap::new();
    let mut stacked_checked = 0u64;
    let mut stacked_failed: Vec<String> = Vec::new();
    let mut quantized = 0u64;
    let mut unquantized = 0u64;
    let mut module_refused = 0u64;
    let mut group_tally: BTreeMap<String, GroupTally> = BTreeMap::new();
    for group in rules {
        group_tally.insert(group.name.clone(), GroupTally::default());
    }

    let classified = if config_refused {
        // The configuration itself was refused, so nothing can be resolved
        // under the Slice 1 rules; the refusal above is the finding.
        Vec::new()
    } else {
        classify_all(catalog, config.as_ref())
    };
    for (module, outcome) in &classified {
        let explicit = config.as_ref().and_then(|c| c.explicit(module));
        let (pattern, indices) = family(module);
        let module_key = format!("{module}.");
        let matched: Vec<&Group> = rules.iter().filter(|g| g.matches(&module_key)).collect();
        match outcome {
            Ok(ModuleKind::Quantized(triple)) => {
                quantized += 1;
                let spec = triple.spec();
                let scale = triple.scales().dtype.as_str();
                *combos
                    .entry(format!(
                        "bits {} group_size {} metadata {}",
                        spec.bits.get(),
                        spec.group_size.get(),
                        scale
                    ))
                    .or_default() += 1;
                let leading = if triple.leading().is_empty() {
                    "plain".to_string()
                } else {
                    format!("{:?}", triple.leading())
                };
                *leading_shapes.entry(leading).or_default() += 1;
                let source = if explicit.is_some() {
                    "explicit_override"
                } else {
                    "default"
                };
                *resolution.entry(source.to_string()).or_default() += 1;
                if !triple.leading().is_empty() {
                    // Pure arithmetic over the stored shapes: the last plane of
                    // a stacked triple must end exactly where each tensor ends.
                    let last: Vec<u64> = triple.leading().iter().map(|e| e - 1).collect();
                    let ok = match triple.expert_slice(&last) {
                        Ok(slice) => {
                            slice.weight.begin + slice.weight.len == triple.weight().data_end
                                && slice.scales.begin + slice.scales.len == triple.scales().data_end
                                && slice.biases.begin + slice.biases.len == triple.biases().data_end
                                && triple.row_slice(&last, triple.out_features() - 1).is_ok()
                        }
                        Err(_) => false,
                    };
                    stacked_checked += 1;
                    if !ok {
                        stacked_failed.push(module.clone());
                    }
                }
                module_families.entry(pattern).or_default().add(
                    json!({
                        "kind": "quantized",
                        "bits": spec.bits.get(),
                        "group_size": spec.group_size.get(),
                        "metadata_dtype": scale,
                        "resolved_from": source,
                        "leading": triple.leading(),
                        "out_features": triple.out_features(),
                        "in_features": triple.in_features(),
                        "weight_shape": triple.weight().shape,
                        "scales_shape": triple.scales().shape,
                    }),
                    indices,
                );
                if explicit.is_some() {
                    override_rows.insert(
                        module.clone(),
                        json!({"status": "QUANTIZED", "bits": spec.bits.get(),
                               "group_size": spec.group_size.get()}),
                    );
                }
                for group in &matched {
                    let tally = group_tally.get_mut(&group.name).unwrap();
                    tally.modules += 1;
                    tally.quantized += 1;
                    if group.expect.as_deref() == Some("unquantized") {
                        tally.surprises.push(format!("{module} is quantized"));
                    }
                }
            }
            Ok(ModuleKind::Unquantized(tensor)) => {
                unquantized += 1;
                *unquantized_dtypes
                    .entry(tensor.dtype.to_string())
                    .or_default() += 1;
                module_families.entry(pattern).or_default().add(
                    json!({
                        "kind": "unquantized",
                        "dtype": tensor.dtype.as_str(),
                        "shape": tensor.shape,
                    }),
                    indices,
                );
                for group in &matched {
                    let tally = group_tally.get_mut(&group.name).unwrap();
                    tally.modules += 1;
                    tally.unquantized += 1;
                    if group.expect.as_deref() == Some("quantized") {
                        tally.surprises.push(format!("{module} is unquantized"));
                    }
                }
            }
            Err(error) => {
                module_refused += 1;
                let name = variant(error);
                *refusals.entry(name.to_string()).or_default() += 1;
                let examples = refusal_examples.entry(name.to_string()).or_default();
                if examples.len() < 5 {
                    examples.push(format!("{module}: {error}"));
                }
                if explicit.is_some() || matches!(error, AffineError::UnresolvedOverride { .. }) {
                    override_rows.insert(
                        module.clone(),
                        json!({"status": "REFUSED", "variant": name,
                               "refusal": error.to_string()}),
                    );
                }
                for group in &matched {
                    let tally = group_tally.get_mut(&group.name).unwrap();
                    tally.modules += 1;
                    tally.refused += 1;
                }
            }
        }
    }

    let mut override_status: BTreeMap<String, u64> = BTreeMap::new();
    for row in override_rows.values() {
        *override_status
            .entry(row["status"].as_str().unwrap_or("?").to_string())
            .or_default() += 1;
    }
    let mut override_families: BTreeMap<String, FamilyTally> = BTreeMap::new();
    for (module, row) in &override_rows {
        let (pattern, indices) = family(module);
        override_families
            .entry(pattern)
            .or_default()
            .add(row.clone(), indices);
    }

    // ---- tensors that belong to no module path -------------------------------
    let mut orphan_families: BTreeMap<String, FamilyTally> = BTreeMap::new();
    let mut orphans = 0u64;
    for (name, tensor) in catalog.iter() {
        if module_member_tensors.contains(name) {
            continue;
        }
        orphans += 1;
        let (pattern, indices) = family(name);
        orphan_families.entry(pattern).or_default().add(
            json!({"dtype": tensor.dtype.as_str(), "shape": tensor.shape}),
            indices,
        );
    }

    // ---- caller-supplied groups over tensors ---------------------------------
    let mut uncategorized: BTreeMap<String, FamilyTally> = BTreeMap::new();
    let mut uncategorized_count = 0u64;
    for (name, tensor) in catalog.iter() {
        let matched: Vec<&Group> = rules.iter().filter(|g| g.matches(name)).collect();
        if matched.is_empty() && !rules.is_empty() {
            uncategorized_count += 1;
            let (pattern, indices) = family(name);
            uncategorized.entry(pattern).or_default().add(
                json!({"dtype": tensor.dtype.as_str(), "shape": tensor.shape}),
                indices,
            );
        }
        for group in matched {
            let tally = group_tally.get_mut(&group.name).unwrap();
            tally.tensors += 1;
            tally.bytes += tensor.byte_len;
            *tally.dtypes.entry(tensor.dtype.to_string()).or_default() += 1;
            if !module_member_tensors.contains(name) {
                tally.orphans += 1;
            }
            if group.expect.as_deref() == Some("absent") {
                tally.surprises.push(format!("{name} is present"));
            }
            // As in the 1.0.0 rules: every tensor under the group is expected
            // to carry this dtype, so a quantized triple member is a surprise.
            if let Some(expected) = &group.expect_unquantized_dtype {
                if tensor.dtype.as_str() != expected {
                    tally
                        .surprises
                        .push(format!("{name} is {}, expected {expected}", tensor.dtype));
                }
            }
        }
    }
    let groups_json: Vec<Value> = rules
        .iter()
        .map(|group| {
            let tally = &group_tally[&group.name];
            json!({
                "rule": group.to_json(),
                "tensors": tally.tensors,
                "bytes": tally.bytes,
                "dtypes": tally.dtypes,
                "modules": tally.modules,
                "quantized_modules": tally.quantized,
                "unquantized_modules": tally.unquantized,
                "refused_modules": tally.refused,
                "tensors_outside_any_module": tally.orphans,
                "surprise_count": tally.surprises.len(),
                "surprises": tally.surprises.iter().take(20).collect::<Vec<_>>(),
            })
        })
        .collect();

    let report = json!({
        "schema": SCHEMA,
        "label": LABEL,
        "not_claimed": NOT_CLAIMED,
        "result": if config_refused || module_refused > 0 { "OBSERVED_WITH_REFUSALS" } else { "OBSERVED" },
        "access": {
            "catalog_constructor": "Checkpoint::from_headers",
            "reads_possible": checkpoint.is_backed_by_files(),
            "payload_bytes_read": 0,
        },
        "shards": shard_rows,
        "checkpoint": {
            "shard_count": checkpoint.shards().len(),
            "tensor_count": catalog.len(),
            "catalog_digest_sha256": checkpoint.catalog_digest_hex().map_err(|e| e.to_string())?,
            "tensor_bytes_total": payload_total,
            "header_bytes_total": header_total,
            "file_bytes_total": file_total,
            "file_bytes_equal_headers_plus_tensors": header_total.checked_add(payload_total) == Some(file_total),
            "shards_with_exact_extent": extent_ok,
            "all_shards_gap_free": checkpoint.headers().iter().all(|h| h.gap_bytes == 0),
        },
        "index": {
            "entries": index.weight_map.len(),
            "shards_named": indexed_shards.len(),
            "shards_named_equal_shards_supplied": indexed_shards == supplied_shards,
            "every_indexed_tensor_in_its_shard": index_names.is_subset(&catalog_names),
            "no_unindexed_tensor": catalog_names.is_subset(&index_names),
            "declared_total_size": index.total_size,
            "declared_total_size_equals_tensor_bytes": index.total_size == Some(payload_total),
            "declared_total_size_equals_file_bytes_total": index.total_size == Some(file_total),
        },
        "dtypes": dtypes.iter().map(|(k, (n, b))| (k.clone(), json!({"tensors": n, "bytes": b}))).collect::<Map<String, Value>>(),
        "tensor_families": families_json(&tensor_families),
        "configuration": config_json,
        "modules": {
            "count": paths.len(),
            "quantized": quantized,
            "unquantized": unquantized,
            "refused": module_refused,
            "classified_entries": classified.len(),
            "resolved_from": resolution,
            "combinations": combos,
            "quantized_leading_shapes": leading_shapes,
            "unquantized_dtypes": unquantized_dtypes,
            "refusals": refusals,
            "refusal_examples": refusal_examples,
            "stacked_slice_arithmetic": {
                "checked": stacked_checked,
                "failed": stacked_failed,
            },
            "families": families_json(&module_families),
        },
        "overrides": {
            "status_counts": override_status,
            "families": families_json(&override_families),
        },
        "tensors_outside_any_module": {
            "count": orphans,
            "families": families_json(&orphan_families),
        },
        "caller_supplied_groups": {
            "groups": groups_json,
            "uncategorized_tensors": uncategorized_count,
            "uncategorized_families": families_json(&uncategorized),
        },
    });

    Ok(Census {
        report,
        checkpoint: Some(checkpoint),
    })
}
