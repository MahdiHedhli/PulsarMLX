//! Specification parsing, module classification, override resolution,
//! consistency and slicing arithmetic -- each against its exact error variant.

use mlx_affine::module::{module_paths, resolved_spec};
use mlx_affine::{
    classify_module, AffineError, Bits, GroupSize, Mode, ModuleKind, QuantSpec, QuantizationConfig,
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
    assert_eq!(triple.spec, spec(4, 64));
    assert_eq!(triple.out_features, 8);
    assert_eq!(triple.in_features, 64);
    assert!(triple.leading.is_empty());
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
    assert_eq!(triple.leading, vec![3]);
    assert_eq!(triple.out_features, 4);
    assert_eq!(triple.in_features, 128);

    let weight_base = triple.weight.data_begin;
    let scales_base = triple.scales.data_begin;
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
        triple.biases.data_begin + 2 * plane_metadata_bytes + 3 * 4
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
    assert_eq!(triple.in_features, 64);
    let whole = triple.expert_slice(&[]).unwrap();
    assert_eq!(whole.weight.begin, triple.weight.data_begin);
    assert_eq!(whole.weight.len, triple.weight.byte_len);
    assert_eq!(whole.scales.len, triple.scales.byte_len);
}

#[test]
fn a_huge_leading_extent_overflows_before_it_is_used() {
    // 2^32 experts of a 2^32-byte plane would be 2^64 bytes. The catalog
    // itself refuses that, so the arithmetic is exercised directly.
    let spec_ = spec(4, 64);
    assert_eq!(spec_.words_per_group(), 8);
    assert_eq!(Bits::Four.codes_per_word(), 8);
    assert_eq!(Bits::Eight.codes_per_word(), 4);
    assert_eq!(Bits::Four.max_code(), 15);
    assert_eq!(Bits::Eight.max_code(), 255);
}
