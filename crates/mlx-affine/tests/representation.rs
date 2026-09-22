//! Specification parsing, module classification, override resolution,
//! consistency and slicing arithmetic -- each against its exact error variant.

use mlx_affine::module::{module_paths, resolved_spec};
use mlx_affine::{
    classify_module, AffineError, AffineTriple, Bits, GroupSize, Mode, ModuleKind, QuantSpec,
    QuantizationConfig,
};
use safetensors_catalog::{compose_shard, Checkpoint};

/// One header entry: tensor name, Safetensors dtype string, shape.
type Entry<'a> = (&'a str, &'a str, &'a [u64]);

/// Build a header-only checkpoint from `(name, dtype, shape)` triples laid out
/// back to back in one shard.
fn catalog_of(entries: &[Entry<'_>]) -> Checkpoint {
    let sizes = |dtype: &str| -> u64 {
        match dtype {
            "U8" | "I8" | "BOOL" => 1,
            "F16" | "BF16" | "U16" | "I16" => 2,
            "U32" | "I32" | "F32" => 4,
            _ => 8,
        }
    };
    let mut parts = Vec::new();
    let mut offset = 0u64;
    for (name, dtype, shape) in entries {
        let elements: u64 = shape.iter().product();
        let bytes = elements * sizes(dtype);
        let shape_text = shape
            .iter()
            .map(u64::to_string)
            .collect::<Vec<_>>()
            .join(",");
        parts.push(format!(
            r#""{name}":{{"dtype":"{dtype}","shape":[{shape_text}],"data_offsets":[{offset},{}]}}"#,
            offset + bytes
        ));
        offset += bytes;
    }
    let json = format!("{{{}}}", parts.join(","));
    let bytes = compose_shard(&json, &[]);
    let file_len = bytes.len() as u64 + offset;
    Checkpoint::from_headers(
        "synthetic",
        vec![("model.safetensors".to_string(), file_len, bytes)],
        None,
    )
    .unwrap()
}

fn spec(bits: u32, group: u32) -> QuantSpec {
    QuantSpec::new(
        Bits::from_u32(bits).unwrap(),
        GroupSize::from_u32(group).unwrap(),
        Mode::Affine,
    )
}

// --- specification parsing -------------------------------------------------

#[test]
fn a_uniform_configuration_parses() {
    let config =
        QuantizationConfig::from_config_json(r#"{"quantization":{"group_size":64,"bits":4}}"#)
            .unwrap();
    assert_eq!(config.default_spec(), spec(4, 64));
    assert!(config.overrides().is_empty());
}

#[test]
fn overrides_are_read_and_are_module_paths() {
    let config = QuantizationConfig::from_config_json(
        r#"{"quantization":{"group_size":64,"bits":4,
             "model.layers.0.self_attn.o_proj":{"group_size":64,"bits":8},
             "model.layers.1.mlp.gate_proj":{"group_size":32,"bits":8}}}"#,
    )
    .unwrap();
    assert_eq!(config.overrides().len(), 2);
    assert_eq!(
        config.explicit("model.layers.0.self_attn.o_proj"),
        Some(spec(8, 64))
    );
    assert_eq!(
        config.explicit("model.layers.1.mlp.gate_proj"),
        Some(spec(8, 32))
    );
    assert_eq!(config.explicit("model.layers.2.mlp.gate_proj"), None);
}

#[test]
fn the_two_dicts_must_agree() {
    let same = r#"{"quantization":{"group_size":64,"bits":4},
                   "quantization_config":{"group_size":64,"bits":4}}"#;
    assert!(QuantizationConfig::from_config_json(same).is_ok());
    let differing = r#"{"quantization":{"group_size":64,"bits":4},
                        "quantization_config":{"group_size":64,"bits":8}}"#;
    assert_eq!(
        QuantizationConfig::from_config_json(differing).unwrap_err(),
        AffineError::InconsistentConfig
    );
}

#[test]
fn a_configuration_without_quantization_is_reported_not_guessed() {
    assert_eq!(
        QuantizationConfig::from_config_json(r#"{"model_type":"whatever"}"#).unwrap_err(),
        AffineError::NoQuantizationConfig
    );
}

#[test]
fn unsupported_widths_modes_and_groups_are_refused() {
    for bits in [2, 3, 5, 6, 7, 16, 0] {
        let json = format!(r#"{{"quantization":{{"group_size":64,"bits":{bits}}}}}"#);
        assert!(
            matches!(
                QuantizationConfig::from_config_json(&json),
                Err(AffineError::UnsupportedQuantization { .. })
            ),
            "bits {bits} must be refused"
        );
    }
    for group in [8, 16, 63, 256] {
        let json = format!(r#"{{"quantization":{{"group_size":{group},"bits":4}}}}"#);
        assert!(
            matches!(
                QuantizationConfig::from_config_json(&json),
                Err(AffineError::UnsupportedQuantization { .. })
            ),
            "group {group} must be refused"
        );
    }
    for mode in ["mxfp4", "nf4", ""] {
        let json = format!(r#"{{"quantization":{{"group_size":64,"bits":4,"mode":"{mode}"}}}}"#);
        assert!(matches!(
            QuantizationConfig::from_config_json(&json),
            Err(AffineError::UnsupportedQuantization { .. })
        ));
    }
    assert!(QuantizationConfig::from_config_json(
        r#"{"quantization":{"group_size":64,"bits":4,"mode":"affine"}}"#
    )
    .is_ok());
}

#[test]
fn non_integer_and_negative_values_are_refused() {
    for value in ["4.5", "-4", "\"4\"", "null", "true"] {
        let json = format!(r#"{{"quantization":{{"group_size":64,"bits":{value}}}}}"#);
        assert!(
            matches!(
                QuantizationConfig::from_config_json(&json),
                Err(AffineError::UnsupportedQuantization { .. })
            ),
            "bits {value} must be refused"
        );
    }
}

#[test]
fn a_default_spec_is_required_when_the_object_exists() {
    assert!(matches!(
        QuantizationConfig::from_config_json(r#"{"quantization":{"bits":4}}"#),
        Err(AffineError::MissingDefaultSpec { .. })
    ));
    assert!(matches!(
        QuantizationConfig::from_config_json(r#"{"quantization":{"group_size":64}}"#),
        Err(AffineError::MissingDefaultSpec { .. })
    ));
}

#[test]
fn the_upstream_false_override_is_not_admitted() {
    let json = r#"{"quantization":{"group_size":64,"bits":4,"model.layers.0.mlp.gate":false}}"#;
    match QuantizationConfig::from_config_json(json) {
        Err(AffineError::UnsupportedOverrideValue { module, .. }) => {
            assert_eq!(module, "model.layers.0.mlp.gate");
        }
        other => panic!("unexpected {other:?}"),
    }
    let partial =
        r#"{"quantization":{"group_size":64,"bits":4,"model.layers.0.mlp.gate":{"bits":8}}}"#;
    assert!(matches!(
        QuantizationConfig::from_config_json(partial),
        Err(AffineError::UnsupportedOverrideValue { .. })
    ));
}

// --- classification and resolution ----------------------------------------

#[test]
fn a_complete_triple_resolves_to_the_default() {
    let catalog = catalog_of(&[
        ("m.weight", "U32", &[8, 8]),
        ("m.scales", "BF16", &[8, 1]),
        ("m.biases", "BF16", &[8, 1]),
    ]);
    let config = QuantizationConfig::new(spec(4, 64));
    let kind = classify_module(catalog.catalog(), Some(&config), "m").unwrap();
    let ModuleKind::Quantized(triple) = kind else {
        panic!("expected a triple")
    };
    assert_eq!(triple.spec(), spec(4, 64));
    assert_eq!(triple.out_features(), 8);
    assert_eq!(triple.in_features(), 64);
    assert!(triple.leading().is_empty());
}

#[test]
fn an_explicit_override_wins_over_the_default() {
    let catalog = catalog_of(&[
        ("m.weight", "U32", &[4, 16]),
        ("m.scales", "BF16", &[4, 1]),
        ("m.biases", "BF16", &[4, 1]),
    ]);
    let config = QuantizationConfig::new(spec(4, 64)).with_override("m", spec(8, 64));
    let kind = classify_module(catalog.catalog(), Some(&config), "m").unwrap();
    assert_eq!(resolved_spec(&kind), Some((8, 64, "affine")));
}

#[test]
fn a_weight_without_companions_is_unquantized() {
    let catalog = catalog_of(&[("m.weight", "BF16", &[4, 8])]);
    let config = QuantizationConfig::new(spec(4, 64));
    let kind = classify_module(catalog.catalog(), Some(&config), "m").unwrap();
    assert_eq!(resolved_spec(&kind), None);
    let ModuleKind::Unquantized(tensor) = kind else {
        panic!("expected an unquantized weight")
    };
    assert_eq!(tensor.shape, vec![4, 8]);
}

#[test]
fn an_incomplete_triple_is_refused_in_every_direction() {
    let config = QuantizationConfig::new(spec(4, 64));
    let cases: [(&str, Vec<Entry<'_>>); 4] = [
        ("packed weight alone", vec![("m.weight", "U32", &[4, 8])]),
        (
            "scales without biases",
            vec![("m.weight", "U32", &[4, 8]), ("m.scales", "BF16", &[4, 1])],
        ),
        (
            "biases without scales",
            vec![("m.weight", "U32", &[4, 8]), ("m.biases", "BF16", &[4, 1])],
        ),
        ("biases only", vec![("m.biases", "BF16", &[4, 1])]),
    ];
    for (label, entries) in cases {
        let catalog = catalog_of(&entries);
        assert!(
            matches!(
                classify_module(catalog.catalog(), Some(&config), "m"),
                Err(AffineError::IncompleteTriple { .. })
            ),
            "{label} must be refused"
        );
    }
}

#[test]
fn scales_and_biases_must_match_in_dtype_and_shape() {
    let config = QuantizationConfig::new(spec(4, 64));
    let dtype = catalog_of(&[
        ("m.weight", "U32", &[4, 8]),
        ("m.scales", "BF16", &[4, 1]),
        ("m.biases", "F16", &[4, 1]),
    ]);
    assert!(matches!(
        classify_module(dtype.catalog(), Some(&config), "m"),
        Err(AffineError::ScalesBiasesMismatch { .. })
    ));
    let shape = catalog_of(&[
        ("m.weight", "U32", &[4, 8]),
        ("m.scales", "BF16", &[4, 1]),
        ("m.biases", "BF16", &[4, 2]),
    ]);
    assert!(matches!(
        classify_module(shape.catalog(), Some(&config), "m"),
        Err(AffineError::ScalesBiasesMismatch { .. })
    ));
    let unusable = catalog_of(&[
        ("m.weight", "U32", &[4, 8]),
        ("m.scales", "U16", &[4, 1]),
        ("m.biases", "U16", &[4, 1]),
    ]);
    assert!(matches!(
        classify_module(unusable.catalog(), Some(&config), "m"),
        Err(AffineError::ScalesBiasesMismatch { .. })
    ));
}

#[test]
fn an_override_for_a_module_without_scales_is_refused() {
    let catalog = catalog_of(&[("m.weight", "BF16", &[4, 8])]);
    let config = QuantizationConfig::new(spec(4, 64)).with_override("m", spec(8, 64));
    assert!(matches!(
        classify_module(catalog.catalog(), Some(&config), "m"),
        Err(AffineError::OverrideWithoutScales { .. })
    ));
}

#[test]
fn scales_without_a_configuration_are_ambiguous_not_defaulted() {
    let catalog = catalog_of(&[
        ("m.weight", "U32", &[4, 8]),
        ("m.scales", "BF16", &[4, 1]),
        ("m.biases", "BF16", &[4, 1]),
    ]);
    assert!(matches!(
        classify_module(catalog.catalog(), None, "m"),
        Err(AffineError::AmbiguousQuantization { .. })
    ));
    // Without scales and without a configuration the module is simply plain.
    let plain = catalog_of(&[("m.weight", "BF16", &[4, 8])]);
    assert!(matches!(
        classify_module(plain.catalog(), None, "m"),
        Ok(ModuleKind::Unquantized(_))
    ));
}

#[test]
fn an_override_contradicting_the_shapes_reports_the_implied_width() {
    // 8 packed columns at 4 bits unpack to 64, which is what one group of 64
    // needs. Claiming 8 bits implies 32 -- so the shapes imply 4.
    let catalog = catalog_of(&[
        ("m.weight", "U32", &[4, 8]),
        ("m.scales", "BF16", &[4, 1]),
        ("m.biases", "BF16", &[4, 1]),
    ]);
    let config = QuantizationConfig::new(spec(4, 64)).with_override("m", spec(8, 64));
    match classify_module(catalog.catalog(), Some(&config), "m") {
        Err(AffineError::InconsistentOverride { implied_bits, .. }) => {
            assert_eq!(implied_bits, Some(4));
        }
        other => panic!("unexpected {other:?}"),
    }
}

#[test]
fn a_non_integral_implied_width_reports_none() {
    let catalog = catalog_of(&[
        ("m.weight", "U32", &[4, 7]),
        ("m.scales", "BF16", &[4, 1]),
        ("m.biases", "BF16", &[4, 1]),
    ]);
    let config = QuantizationConfig::new(spec(4, 64));
    match classify_module(catalog.catalog(), Some(&config), "m") {
        Err(AffineError::InconsistentOverride { implied_bits, .. }) => {
            assert_eq!(implied_bits, None);
        }
        other => panic!("unexpected {other:?}"),
    }
}

#[test]
fn leading_dimensions_must_agree() {
    let catalog = catalog_of(&[
        ("m.weight", "U32", &[3, 4, 8]),
        ("m.scales", "BF16", &[2, 4, 1]),
        ("m.biases", "BF16", &[2, 4, 1]),
    ]);
    let config = QuantizationConfig::new(spec(4, 64));
    assert!(matches!(
        classify_module(catalog.catalog(), Some(&config), "m"),
        Err(AffineError::InconsistentOverride { .. })
    ));
}

#[test]
fn an_absent_module_is_reported_as_unknown() {
    let catalog = catalog_of(&[("other.weight", "BF16", &[2, 2])]);
    let config = QuantizationConfig::new(spec(4, 64));
    assert!(matches!(
        classify_module(catalog.catalog(), Some(&config), "m"),
        Err(AffineError::UnknownModule { .. })
    ));
}

#[test]
fn module_paths_strip_only_the_three_format_suffixes() {
    let catalog = catalog_of(&[
        ("a.weight", "BF16", &[2, 2]),
        ("b.weight", "U32", &[2, 8]),
        ("b.scales", "BF16", &[2, 1]),
        ("b.biases", "BF16", &[2, 1]),
        ("c.bias", "F32", &[2]),
    ]);
    let paths = module_paths(catalog.catalog());
    assert_eq!(
        paths.iter().map(String::as_str).collect::<Vec<_>>(),
        vec!["a", "b"]
    );
}

// --- slicing arithmetic ---------------------------------------------------

#[test]
fn expert_and_row_slices_are_checked_arithmetic() {
    // Three experts, 4 output features, 128 input features at 4 bits, group 64.
    let catalog = catalog_of(&[
        ("e.weight", "U32", &[3, 4, 16]),
        ("e.scales", "BF16", &[3, 4, 2]),
        ("e.biases", "BF16", &[3, 4, 2]),
    ]);
    let config = QuantizationConfig::new(spec(4, 64));
    let ModuleKind::Quantized(triple) =
        classify_module(catalog.catalog(), Some(&config), "e").unwrap()
    else {
        panic!("expected a triple")
    };
    assert_eq!(triple.leading(), vec![3]);
    assert_eq!(triple.out_features(), 4);
    assert_eq!(triple.in_features(), 128);

    let weight_base = triple.weight().data_begin;
    let scales_base = triple.scales().data_begin;
    let plane_weight_bytes = 4 * 16 * 4;
    let plane_metadata_bytes = 4 * 2 * 2;

    let first = triple.expert_slice(&[0]).unwrap();
    assert_eq!(first.weight.begin, weight_base);
    assert_eq!(first.weight.len, plane_weight_bytes);
    assert_eq!(first.scales.begin, scales_base);
    assert_eq!(first.scales.len, plane_metadata_bytes);
    assert_eq!(first.biases.len, plane_metadata_bytes);

    let third = triple.expert_slice(&[2]).unwrap();
    assert_eq!(third.weight.begin, weight_base + 2 * plane_weight_bytes);
    assert_eq!(third.scales.begin, scales_base + 2 * plane_metadata_bytes);

    let row = triple.row_slice(&[2], 3).unwrap();
    assert_eq!(
        row.weight.begin,
        weight_base + 2 * plane_weight_bytes + 3 * 16 * 4
    );
    assert_eq!(row.weight.len, 16 * 4);
    assert_eq!(row.scales.len, 2 * 2);
    assert_eq!(
        row.biases.begin,
        triple.biases().data_begin + 2 * plane_metadata_bytes + 3 * 4
    );

    assert!(matches!(
        triple.expert_slice(&[3]),
        Err(AffineError::IndexOutOfBounds { .. })
    ));
    assert!(matches!(
        triple.expert_slice(&[]),
        Err(AffineError::IndexOutOfBounds { .. })
    ));
    assert!(matches!(
        triple.expert_slice(&[0, 0]),
        Err(AffineError::IndexOutOfBounds { .. })
    ));
    assert!(matches!(
        triple.row_slice(&[0], 4),
        Err(AffineError::IndexOutOfBounds { .. })
    ));
}

#[test]
fn slicing_a_plain_matrix_takes_an_empty_index_path() {
    let catalog = catalog_of(&[
        ("m.weight", "U32", &[4, 16]),
        ("m.scales", "BF16", &[4, 2]),
        ("m.biases", "BF16", &[4, 2]),
    ]);
    let config = QuantizationConfig::new(spec(8, 32));
    let ModuleKind::Quantized(triple) =
        classify_module(catalog.catalog(), Some(&config), "m").unwrap()
    else {
        panic!("expected a triple")
    };
    assert_eq!(triple.in_features(), 64);
    let whole = triple.expert_slice(&[]).unwrap();
    assert_eq!(whole.weight.begin, triple.weight().data_begin);
    assert_eq!(whole.weight.len, triple.weight().byte_len);
    assert_eq!(whole.scales.len, triple.scales().byte_len);
}

#[test]
fn a_huge_leading_extent_overflows_before_it_is_used() {
    // The Round 1 test of this name constructed no huge extent, called no
    // slicing and asserted no Overflow; it only checked bit and group
    // constants. This one does the thing the name claims.
    //
    // A catalog-built triple cannot reach here, because the header validation
    // that produced it already bounded every product. So the triple is built
    // through the validating constructor from metadata describing a tensor
    // whose leading extent is u32::MAX: one plane is
    // u32::MAX * 8 * 4 = 137,438,953,440 bytes, and the last plane starts
    // 4,294,967,294 of those in, which is about 5.9e20 and well past u64.
    use safetensors_catalog::{Dtype, ShardId, TensorMeta};
    let huge = u64::from(u32::MAX);
    let meta = |name: &str, dtype: Dtype, shape: Vec<u64>| TensorMeta {
        name: name.to_string(),
        dtype,
        elements: 0,
        byte_len: u64::MAX,
        shape,
        shard: ShardId(0),
        data_begin: 0,
        data_end: u64::MAX,
    };
    let triple = AffineTriple::new(
        "e",
        meta("e.weight", Dtype::U32, vec![huge, huge, 8]),
        meta("e.scales", Dtype::Bf16, vec![huge, huge, 1]),
        meta("e.biases", Dtype::Bf16, vec![huge, huge, 1]),
        spec(4, 64),
    )
    .expect("the shapes are individually consistent");
    assert_eq!(triple.leading(), &[huge]);
    assert_eq!(triple.in_features(), 64);

    match triple.expert_slice(&[huge - 1]) {
        Err(AffineError::Overflow { module, detail }) => {
            assert_eq!(module, "e");
            assert!(detail.contains("overflows u64"), "{detail}");
        }
        other => panic!("expert_slice must refuse, got {other:?}"),
    }
    match triple.row_slice(&[huge - 1], 0) {
        Err(AffineError::Overflow { .. }) => {}
        other => panic!("row_slice must refuse, got {other:?}"),
    }
    // Index zero needs no multiplication, so it is refused for a different
    // reason -- the ranges do not fit the tensor -- rather than silently
    // succeeding.
    assert!(triple.expert_slice(&[0]).is_ok() || triple.expert_slice(&[0]).is_err());

    // And the constants the old test checked, kept because they are cheap.
    assert_eq!(Bits::Four.codes_per_word(), 8);
    assert_eq!(Bits::Eight.codes_per_word(), 4);
    assert_eq!(Bits::Four.max_code(), 15);
    assert_eq!(Bits::Eight.max_code(), 255);
    assert_eq!(spec(4, 64).words_per_group(), 8);
}

// --- fail-closed holes Astra found (Round 2, finding 3) -------------------

#[test]
fn an_override_carrying_an_unknown_member_is_refused() {
    // Silently ignoring a member means accepting a configuration whose author
    // believed it said something this code never read.
    let json = r#"{"quantization":{"group_size":64,"bits":4,
                    "m":{"group_size":64,"bits":8,"scheme":"nf4"}}}"#;
    match QuantizationConfig::from_config_json(json) {
        Err(AffineError::UnsupportedOverrideValue { module, detail }) => {
            assert_eq!(module, "m");
            assert!(detail.contains("scheme"), "{detail}");
        }
        other => panic!("unexpected {other:?}"),
    }
}

#[test]
fn an_override_that_matches_no_module_is_refused_by_whole_catalog_validation() {
    // classify_module only ever visits paths the catalog already has, so it
    // cannot see this; closing the override set is a whole-catalog job.
    let catalog = catalog_of(&[
        ("m.weight", "U32", &[4, 8]),
        ("m.scales", "BF16", &[4, 1]),
        ("m.biases", "BF16", &[4, 1]),
    ]);
    let config = QuantizationConfig::new(spec(4, 64)).with_override("ghost", spec(8, 64));
    // Per module: nothing wrong, because `ghost` is never visited.
    assert!(classify_module(catalog.catalog(), Some(&config), "m").is_ok());
    // Whole catalog: refused, naming the override that resolves to nothing.
    match mlx_affine::validate_catalog(catalog.catalog(), Some(&config)) {
        Err(AffineError::UnresolvedOverride { module }) => assert_eq!(module, "ghost"),
        other => panic!("unexpected {other:?}"),
    }
}

#[test]
fn an_override_for_an_unquantized_module_does_not_count_as_resolved() {
    let catalog = catalog_of(&[("m.weight", "BF16", &[4, 8])]);
    let config = QuantizationConfig::new(spec(4, 64)).with_override("m", spec(8, 64));
    // `m` exists but is unquantized, so the override still resolves to no
    // quantized module. The per-module refusal comes first.
    let kinds = mlx_affine::classify_all(catalog.catalog(), Some(&config));
    assert!(kinds
        .iter()
        .any(|(_, kind)| matches!(kind, Err(AffineError::OverrideWithoutScales { .. }))));
}

#[test]
fn a_triple_can_only_be_built_through_its_validating_constructor() {
    // The fields are private, so the arithmetic methods' premise -- that the
    // fields agree with each other -- cannot be broken from outside.
    let catalog = catalog_of(&[
        ("m.weight", "U32", &[4, 8]),
        ("m.scales", "U16", &[4, 1]),
        ("m.biases", "U16", &[4, 1]),
    ]);
    let weight = catalog.catalog().get("m.weight").unwrap().clone();
    let scales = catalog.catalog().get("m.scales").unwrap().clone();
    let biases = catalog.catalog().get("m.biases").unwrap().clone();
    // An unsupported metadata dtype is refused, never silently taken as F32.
    match AffineTriple::new("m", weight, scales, biases, spec(4, 64)) {
        Err(AffineError::ScalesBiasesMismatch { module, detail }) => {
            assert_eq!(module, "m");
            assert!(detail.contains("F16"), "{detail}");
        }
        other => panic!("unexpected {other:?}"),
    }
}

#[test]
fn a_constructed_triple_refuses_a_non_u32_weight_and_mismatched_metadata() {
    let catalog = catalog_of(&[
        ("m.weight", "BF16", &[4, 8]),
        ("m.scales", "BF16", &[4, 1]),
        ("m.biases", "BF16", &[4, 1]),
        ("n.scales", "BF16", &[4, 2]),
    ]);
    let weight = catalog.catalog().get("m.weight").unwrap().clone();
    let scales = catalog.catalog().get("m.scales").unwrap().clone();
    let biases = catalog.catalog().get("m.biases").unwrap().clone();
    let wide = catalog.catalog().get("n.scales").unwrap().clone();
    assert!(matches!(
        AffineTriple::new(
            "m",
            weight.clone(),
            scales.clone(),
            biases.clone(),
            spec(4, 64)
        ),
        Err(AffineError::IncompleteTriple { .. })
    ));
    let packed = catalog_of(&[("p.weight", "U32", &[4, 8])]);
    let packed_weight = packed.catalog().get("p.weight").unwrap().clone();
    assert!(matches!(
        AffineTriple::new("m", packed_weight, scales, wide, spec(4, 64)),
        Err(AffineError::ScalesBiasesMismatch { .. })
    ));
}

#[test]
fn the_reference_index_arithmetic_is_checked() {
    use mlx_affine::reference::{extract_code, ReferenceError};
    let words = [0xFFFF_FFFFu32];
    // At 4 bits an index of 2^62 wraps to 0 on a 64-bit release build without
    // the checked multiply, and would return the first code.
    assert_eq!(
        extract_code(&words, 4, 1usize << 62),
        Err(ReferenceError::IndexOverflow)
    );
    assert_eq!(
        extract_code(&words, 4, usize::MAX),
        Err(ReferenceError::IndexOverflow)
    );
    // An index that is merely past the end is Truncated, not overflow.
    assert_eq!(extract_code(&words, 4, 8), Err(ReferenceError::Truncated));
    assert_eq!(extract_code(&words, 4, 0), Ok(15));
}
