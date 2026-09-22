//! The synthetic checkpoints: the owner's uniform-versus-mixed demonstration,
//! R3 against R1 over real fixture bytes, and every affine negative case.

use std::collections::BTreeMap;
use std::path::PathBuf;

use mlx_affine::decode::{dequantize_rows, words_from_bytes};
use mlx_affine::module::{module_paths, resolved_spec};
use mlx_affine::{classify_module, AffineError, ModuleKind, QuantizationConfig};
use safetensors_catalog::{Checkpoint, OpenMode};
use serde_json::Value;

fn fixtures() -> PathBuf {
    [env!("CARGO_MANIFEST_DIR"), "../../fixtures/safetensors"]
        .iter()
        .collect()
}

fn read_json(path: &std::path::Path) -> Value {
    let text = std::fs::read_to_string(path).unwrap_or_else(|e| panic!("{}: {e}", path.display()));
    serde_json::from_str(&text).unwrap()
}

fn open(name: &str) -> (Checkpoint, Option<QuantizationConfig>) {
    let root = fixtures().join(name);
    let checkpoint = Checkpoint::open(&root, OpenMode::Auto).unwrap();
    let config_path = root.join("config.json");
    let config = if config_path.is_file() {
        let text = std::fs::read_to_string(&config_path).unwrap();
        match QuantizationConfig::from_config_json(&text) {
            Ok(config) => Some(config),
            Err(AffineError::NoQuantizationConfig) => None,
            Err(other) => panic!("{name}: {other}"),
        }
    } else {
        None
    };
    (checkpoint, config)
}

/// Every module of a checkpoint, classified.
fn census(
    checkpoint: &Checkpoint,
    config: Option<&QuantizationConfig>,
) -> BTreeMap<String, ModuleKind> {
    module_paths(checkpoint.catalog())
        .into_iter()
        .map(|module| {
            let kind = classify_module(checkpoint.catalog(), config, &module)
                .unwrap_or_else(|error| panic!("{module}: {error}"));
            (module, kind)
        })
        .collect()
}

// --- the demonstration the owner asked for --------------------------------

/// One parser, one catalog, two checkpoint shapes.
///
/// `uniform-affine-v1` is a single shard with no index where every module is
/// 4-bit group 64. `mixed-4-8-v1` is three shards and an index with a default,
/// two kinds of override, an unquantized BF16 weight, an F32 vector, a stacked
/// three-expert tensor and deliberate gaps. Nothing in `safetensors-catalog`
/// or `mlx-affine` is configured differently between them: the same
/// `Checkpoint::open` and the same `classify_module` describe both.
#[test]
fn the_same_parser_describes_a_uniform_and_a_mixed_checkpoint() {
    let (uniform, uniform_config) = open("uniform-affine-v1");
    let (mixed, mixed_config) = open("mixed-4-8-v1");

    let uniform_census = census(&uniform, uniform_config.as_ref());
    let expected_uniform: BTreeMap<&str, Option<(u32, u32, &str)>> = BTreeMap::from([
        ("block.0.proj", Some((4, 64, "affine"))),
        ("block.1.proj", Some((4, 64, "affine"))),
        ("block.2.proj", Some((4, 64, "affine"))),
    ]);
    assert_eq!(uniform_census.len(), expected_uniform.len());
    for (module, kind) in &uniform_census {
        assert_eq!(
            resolved_spec(kind),
            expected_uniform[module.as_str()],
            "uniform-affine-v1: {module}"
        );
    }

    let mixed_census = census(&mixed, mixed_config.as_ref());
    let expected_mixed: BTreeMap<&str, Option<(u32, u32, &str)>> = BTreeMap::from([
        // the default, unlisted in config.json
        ("block.0.gate", Some((4, 64, "affine"))),
        ("block.0.up", Some((4, 64, "affine"))),
        // an explicit 8-bit group 64 override
        ("block.0.down", Some((8, 64, "affine"))),
        // an explicit 8-bit group 32 override
        ("block.1.attn", Some((8, 32, "affine"))),
        // unquantized: a BF16 weight with no companions
        ("block.1.router", None),
        // the stacked three-expert tensor, at the default
        ("block.2.experts", Some((4, 64, "affine"))),
    ]);
    assert_eq!(
        mixed_census.len(),
        expected_mixed.len(),
        "{:?}",
        mixed_census.keys()
    );
    for (module, kind) in &mixed_census {
        assert_eq!(
            resolved_spec(kind),
            expected_mixed[module.as_str()],
            "mixed-4-8-v1: {module}"
        );
    }

    // The stacked tensor is the only one with a leading dimension, and it is
    // the shape a residency layer slices.
    let ModuleKind::Quantized(experts) = &mixed_census["block.2.experts"] else {
        panic!("expected a triple")
    };
    assert_eq!(experts.leading(), vec![3]);
    assert_eq!(experts.out_features(), 4);
    assert_eq!(experts.in_features(), 128);
    let first = experts.expert_slice(&[0]).unwrap();
    let last = experts.expert_slice(&[2]).unwrap();
    assert_eq!(last.weight.begin - first.weight.begin, 2 * first.weight.len);

    // The unquantized F32 vector is present in the catalog and is not a module.
    assert!(mixed.catalog().contains("block.1.router.correction"));
    assert_eq!(
        mixed
            .catalog()
            .get("block.1.router.correction")
            .unwrap()
            .dtype,
        safetensors_catalog::Dtype::F32
    );

    // The declared-total-size variant classifies identically.
    let (declared, declared_config) = open("mixed-4-8-index-total-size-v1");
    let declared_census = census(&declared, declared_config.as_ref());
    assert_eq!(
        declared_census.keys().collect::<Vec<_>>(),
        mixed_census.keys().collect::<Vec<_>>()
    );
    for (module, kind) in &declared_census {
        assert_eq!(resolved_spec(kind), resolved_spec(&mixed_census[module]));
    }
}

// --- R3 against R1 over the fixture bytes ---------------------------------

#[test]
fn r3_reproduces_the_reference_expectations_of_every_positive_fixture() {
    let mut modules = 0usize;
    let mut elements = 0usize;
    for name in [
        "uniform-affine-v1",
        "mixed-4-8-v1",
        "mixed-4-8-index-total-size-v1",
    ] {
        let (checkpoint, config) = open(name);
        let expected = read_json(&fixtures().join(name).join("expected.json"));
        let expected = expected["modules"].as_object().unwrap();
        for (module, kind) in census(&checkpoint, config.as_ref()) {
            let ModuleKind::Quantized(triple) = kind else {
                assert!(
                    !expected.contains_key(&module),
                    "{name}: {module} has expectations"
                );
                continue;
            };
            let case = &expected[&module];
            let rows = case["rows"].as_u64().unwrap() as usize;
            let columns = case["columns"].as_u64().unwrap() as usize;
            assert_eq!(
                case["bits"].as_u64().unwrap() as u32,
                triple.spec().bits.get()
            );
            assert_eq!(
                case["group_size"].as_u64().unwrap() as u32,
                triple.spec().group_size.get()
            );

            let mut weight = vec![0u8; triple.weight().byte_len as usize];
            checkpoint
                .read_tensor_bytes(&triple.weight().name, &mut weight)
                .unwrap();
            let mut scales = vec![0u8; triple.scales().byte_len as usize];
            checkpoint
                .read_tensor_bytes(&triple.scales().name, &mut scales)
                .unwrap();
            let mut biases = vec![0u8; triple.biases().byte_len as usize];
            checkpoint
                .read_tensor_bytes(&triple.biases().name, &mut biases)
                .unwrap();

            let words = words_from_bytes(&weight).unwrap();
            let mut out = vec![0f32; rows * columns];
            dequantize_rows(
                "test",
                &words,
                &scales,
                &biases,
                triple.scale_dtype(),
                triple.spec(),
                rows,
                &mut out,
            )
            .unwrap();

            let reference = case["dequant"].as_array().unwrap();
            assert_eq!(reference.len(), out.len());
            assert!(
                triple.scale_dtype().is_half(),
                "{name}/{module}: the positive fixtures store half-precision metadata, \
                 so the exact invariant applies"
            );
            for (index, value) in out.iter().enumerate() {
                assert_eq!(
                    u64::from(value.to_bits()),
                    reference[index].as_u64().unwrap(),
                    "C-DEQUANT-HALF {name}/{module}[{index}]"
                );
            }
            modules += 1;
            elements += out.len();
        }
    }
    assert_eq!(modules, 13);
    assert!(elements > 3000, "{elements} elements is too thin a sample");
}

#[test]
fn an_expert_slice_reads_the_same_bytes_as_the_whole_tensor() {
    let (checkpoint, config) = open("mixed-4-8-v1");
    let ModuleKind::Quantized(triple) =
        classify_module(checkpoint.catalog(), config.as_ref(), "block.2.experts").unwrap()
    else {
        panic!("expected a triple")
    };
    let mut whole = vec![0u8; triple.weight().byte_len as usize];
    checkpoint
        .read_tensor_bytes(&triple.weight().name, &mut whole)
        .unwrap();

    for expert in 0..3u64 {
        let slice = triple.expert_slice(&[expert]).unwrap();
        let mut plane = vec![0u8; slice.weight.len as usize];
        checkpoint
            .read_range(
                &triple.weight().name,
                slice.weight.begin - triple.weight().data_begin,
                slice.weight.len,
                &mut plane,
            )
            .unwrap();
        let start = (expert * slice.weight.len) as usize;
        assert_eq!(plane, whole[start..start + plane.len()], "expert {expert}");

        // And one row of that plane is the row the whole tensor holds.
        let row = triple.row_slice(&[expert], 2).unwrap();
        let mut row_bytes = vec![0u8; row.weight.len as usize];
        checkpoint
            .read_range(
                &triple.weight().name,
                row.weight.begin - triple.weight().data_begin,
                row.weight.len,
                &mut row_bytes,
            )
            .unwrap();
        let row_start = start + 2 * (row.weight.len as usize);
        assert_eq!(row_bytes, whole[row_start..row_start + row_bytes.len()]);
    }
}

// --- the affine negative cases --------------------------------------------

fn affine_variant(error: &AffineError) -> &'static str {
    match error {
        AffineError::UnsupportedQuantization { .. } => "AffineError::UnsupportedQuantization",
        AffineError::MissingDefaultSpec { .. } => "AffineError::MissingDefaultSpec",
        AffineError::InconsistentConfig => "AffineError::InconsistentConfig",
        AffineError::UnsupportedOverrideValue { .. } => "AffineError::UnsupportedOverrideValue",
        AffineError::InvalidConfigJson { .. } => "AffineError::InvalidConfigJson",
        AffineError::DuplicateConfigKey { .. } => "AffineError::DuplicateConfigKey",
        AffineError::NoQuantizationConfig => "AffineError::NoQuantizationConfig",
        AffineError::IncompleteTriple { .. } => "AffineError::IncompleteTriple",
        AffineError::ScalesBiasesMismatch { .. } => "AffineError::ScalesBiasesMismatch",
        AffineError::OverrideWithoutScales { .. } => "AffineError::OverrideWithoutScales",
        AffineError::AmbiguousQuantization { .. } => "AffineError::AmbiguousQuantization",
        AffineError::InconsistentOverride { .. } => "AffineError::InconsistentOverride",
        AffineError::Overflow { .. } => "AffineError::Overflow",
        AffineError::UnknownModule { .. } => "AffineError::UnknownModule",
        AffineError::IndexOutOfBounds { .. } => "AffineError::IndexOutOfBounds",
        AffineError::GeometryMismatch { .. } => "AffineError::GeometryMismatch",
        _ => "AffineError::<unlisted>",
    }
}

#[test]
fn every_affine_negative_fixture_is_refused_with_the_variant_it_declares() {
    let root = fixtures().join("negative");
    let mut directories: Vec<PathBuf> = std::fs::read_dir(&root)
        .unwrap()
        .map(|entry| entry.unwrap().path())
        .filter(|path| path.is_dir())
        .collect();
    directories.sort();

    let mut exercised = 0usize;
    for directory in directories {
        let name = directory
            .file_name()
            .unwrap()
            .to_string_lossy()
            .into_owned();
        let readme = std::fs::read_to_string(directory.join("README")).unwrap();
        let expected = readme.lines().next().unwrap().trim().to_string();
        if !expected.starts_with("AffineError::") {
            continue;
        }
        let checkpoint = Checkpoint::open(&directory, OpenMode::Auto)
            .unwrap_or_else(|e| panic!("{name}: the shard itself must be well formed: {e}"));
        let config_text = std::fs::read_to_string(directory.join("config.json")).unwrap();

        let error = match QuantizationConfig::from_config_json(&config_text) {
            Err(AffineError::NoQuantizationConfig) => {
                // The configuration is silent; the refusal must come from the
                // module, which carries scales the configuration cannot explain.
                classify_all_until_error(&checkpoint, None)
                    .unwrap_or_else(|| panic!("{name}: nothing was refused"))
            }
            Err(other) => other,
            Ok(config) => classify_all_until_error(&checkpoint, Some(&config))
                .unwrap_or_else(|| panic!("{name}: nothing was refused")),
        };
        assert_eq!(
            affine_variant(&error),
            expected,
            "{name}: got {error:?}, the fixture declares {expected}"
        );
        exercised += 1;
    }
    assert!(
        exercised >= 12,
        "only {exercised} affine negatives were exercised"
    );
}

fn classify_all_until_error(
    checkpoint: &Checkpoint,
    config: Option<&QuantizationConfig>,
) -> Option<AffineError> {
    for module in module_paths(checkpoint.catalog()) {
        if let Err(error) = classify_module(checkpoint.catalog(), config, &module) {
            return Some(error);
        }
    }
    None
}
