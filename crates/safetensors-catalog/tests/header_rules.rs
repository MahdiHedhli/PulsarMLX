//! Every header and index rule, asserted against the exact error variant.
//!
//! These build their bytes in memory. The directory-shaped negative cases,
//! which exercise the same rules through `Checkpoint::open`, live in
//! `negative_fixtures.rs` and read `fixtures/safetensors/negative/`.

use safetensors_catalog::{
    compose_shard, parse_header, parse_header_named, CatalogError, Checkpoint, Dtype,
    MAX_HEADER_BYTES,
};

fn shard(header_json: &str, data_len: usize) -> (Vec<u8>, u64) {
    let bytes = compose_shard(header_json, &vec![0u8; data_len]);
    let len = bytes.len() as u64;
    (bytes, len)
}

#[test]
fn a_minimal_header_parses() {
    let json = r#"{"a":{"dtype":"F32","shape":[2,3],"data_offsets":[0,24]}}"#;
    let (bytes, len) = shard(json, 24);
    let header = parse_header(&bytes, len).unwrap();
    assert_eq!(header.data_len, 24);
    assert_eq!(header.gap_bytes, 0);
    let tensor = &header.tensors["a"];
    assert_eq!(tensor.dtype, Dtype::F32);
    assert_eq!(tensor.elements, 6);
    assert_eq!(tensor.byte_len, 24);
}

#[test]
fn an_empty_shape_is_a_scalar() {
    let json = r#"{"s":{"dtype":"U32","shape":[],"data_offsets":[0,4]}}"#;
    let (bytes, len) = shard(json, 4);
    let header = parse_header(&bytes, len).unwrap();
    assert_eq!(header.tensors["s"].elements, 1);
    assert_eq!(header.tensors["s"].byte_len, 4);
}

#[test]
fn a_zero_element_tensor_needs_an_empty_range() {
    let json = r#"{"z":{"dtype":"F32","shape":[0,4],"data_offsets":[0,0]}}"#;
    let (bytes, len) = shard(json, 0);
    let header = parse_header(&bytes, len).unwrap();
    assert_eq!(header.tensors["z"].elements, 0);

    let json = r#"{"z":{"dtype":"F32","shape":[0,4],"data_offsets":[0,4]}}"#;
    let (bytes, len) = shard(json, 4);
    assert!(matches!(
        parse_header(&bytes, len),
        Err(CatalogError::LengthMismatch {
            declared: 4,
            expected: 0,
            ..
        })
    ));
}

#[test]
fn metadata_must_be_a_string_map() {
    let json =
        r#"{"__metadata__":{"format":"mlx"},"a":{"dtype":"U8","shape":[1],"data_offsets":[0,1]}}"#;
    let (bytes, len) = shard(json, 1);
    assert_eq!(parse_header(&bytes, len).unwrap().metadata["format"], "mlx");

    let json =
        r#"{"__metadata__":{"format":7},"a":{"dtype":"U8","shape":[1],"data_offsets":[0,1]}}"#;
    let (bytes, len) = shard(json, 1);
    assert!(matches!(
        parse_header(&bytes, len),
        Err(CatalogError::InvalidMetadata { .. })
    ));

    let json = r#"{"__metadata__":[],"a":{"dtype":"U8","shape":[1],"data_offsets":[0,1]}}"#;
    let (bytes, len) = shard(json, 1);
    assert!(matches!(
        parse_header(&bytes, len),
        Err(CatalogError::InvalidMetadata { .. })
    ));
}

#[test]
fn a_truncated_length_prefix_is_refused() {
    assert!(matches!(
        parse_header(&[0u8; 4], 4),
        Err(CatalogError::MalformedHeader { .. })
    ));
    assert!(matches!(
        parse_header(&[], 0),
        Err(CatalogError::MalformedHeader { .. })
    ));
}

#[test]
fn a_header_longer_than_the_file_is_refused() {
    let mut bytes = 4096u64.to_le_bytes().to_vec();
    bytes.extend_from_slice(b"{}");
    assert!(matches!(
        parse_header(&bytes, bytes.len() as u64),
        Err(CatalogError::MalformedHeader { .. })
    ));
}

#[test]
fn an_oversized_header_is_refused_before_it_is_read() {
    let bytes = (MAX_HEADER_BYTES + 1).to_le_bytes().to_vec();
    assert!(matches!(
        parse_header(&bytes, u64::MAX),
        Err(CatalogError::HeaderTooLarge { header_len, .. }) if header_len == MAX_HEADER_BYTES + 1
    ));
}

#[test]
fn a_non_object_header_is_refused() {
    // The byte-level check now catches this first: the format says the object
    // begins immediately after the prefix, so anything that does not start
    // with '{' is refused before a parser sees it. NotAnObject remains in the
    // vocabulary as a fallback for a document that starts with '{' and still
    // fails to deserialize as one, which the guard makes unreachable in
    // practice rather than impossible in principle.
    let (bytes, len) = shard("[1,2,3]", 0);
    match parse_header(&bytes, len) {
        Err(CatalogError::MalformedHeader { detail, .. }) => {
            assert!(detail.contains("must begin with"), "{detail}");
        }
        other => panic!("unexpected {other:?}"),
    }
}

#[test]
fn a_header_with_leading_whitespace_is_refused() {
    // Valid JSON, not valid Safetensors: admitting it means admitting a byte
    // sequence upstream would not write and might not read.
    let (bytes, len) = shard(
        " {\"a\":{\"dtype\":\"U8\",\"shape\":[1],\"data_offsets\":[0,1]}}",
        1,
    );
    assert!(matches!(
        parse_header(&bytes, len),
        Err(CatalogError::MalformedHeader { .. })
    ));
}

#[test]
fn invalid_json_is_refused() {
    let (bytes, len) = shard("{not json", 0);
    assert!(matches!(
        parse_header(&bytes, len),
        Err(CatalogError::InvalidJson { .. })
    ));
}

#[test]
fn a_duplicate_name_in_one_header_is_refused() {
    let json = concat!(
        r#"{"a":{"dtype":"U8","shape":[1],"data_offsets":[0,1]},"#,
        r#""a":{"dtype":"U8","shape":[1],"data_offsets":[1,2]}}"#
    );
    let (bytes, len) = shard(json, 2);
    // A repeated member inside one JSON object is a JSON-level defect at every
    // depth, so it reports DuplicateKey with its path. DuplicateTensor now
    // means exactly one thing: the same name in two different shards.
    match parse_header(&bytes, len) {
        Err(CatalogError::DuplicateKey { path }) => assert_eq!(path, "a"),
        other => panic!("unexpected {other:?}"),
    }
}

#[test]
fn a_duplicate_member_at_any_depth_is_refused_with_its_path() {
    // Astra's examples, in memory. Every one has a valid last occurrence,
    // which is exactly why accepting it would be wrong.
    let cases: [(&str, &str, usize); 3] = [
        (
            r#"{"a":{"dtype":"U8","dtype":"U16","shape":[2],"data_offsets":[0,4]}}"#,
            "a.dtype",
            4,
        ),
        (
            r#"{"__metadata__":{"format":7,"format":"mlx"},"a":{"dtype":"U8","shape":[1],"data_offsets":[0,1]}}"#,
            "__metadata__.format",
            1,
        ),
        (
            r#"{"a":{"dtype":"U8","shape":[1],"shape":[1],"data_offsets":[0,1]}}"#,
            "a.shape",
            1,
        ),
    ];
    for (json, expected, data) in cases {
        let (bytes, len) = shard(json, data);
        match parse_header(&bytes, len) {
            Err(CatalogError::DuplicateKey { path }) => assert_eq!(path, expected),
            other => panic!("{json}: unexpected {other:?}"),
        }
    }
}

#[test]
fn an_index_with_a_repeated_tensor_name_is_refused() {
    match safetensors_catalog::parse_index(
        r#"{"weight_map":{"a":"absent.safetensors","a":"model.safetensors"}}"#,
    ) {
        Err(CatalogError::DuplicateKey { path }) => assert_eq!(path, "weight_map.a"),
        other => panic!("unexpected {other:?}"),
    }
}

#[test]
fn overlapping_ranges_are_refused() {
    let json = concat!(
        r#"{"a":{"dtype":"U8","shape":[4],"data_offsets":[0,4]},"#,
        r#""b":{"dtype":"U8","shape":[4],"data_offsets":[2,6]}}"#
    );
    let (bytes, len) = shard(json, 6);
    assert!(matches!(
        parse_header(&bytes, len),
        Err(CatalogError::OverlappingRanges { .. })
    ));
}

#[test]
fn a_range_beyond_the_data_section_is_refused() {
    let json = r#"{"a":{"dtype":"U8","shape":[8],"data_offsets":[0,8]}}"#;
    let (bytes, len) = shard(json, 4);
    assert!(matches!(
        parse_header(&bytes, len),
        Err(CatalogError::InvalidRange {
            begin: 0,
            end: 8,
            data_len: 4,
            ..
        })
    ));
}

#[test]
fn a_reversed_range_is_refused() {
    let json = r#"{"a":{"dtype":"U8","shape":[4],"data_offsets":[8,4]}}"#;
    let (bytes, len) = shard(json, 16);
    // The exact offsets, not merely the variant: the same fixture is
    // committed as negative/header-reversed-range and asserted there too.
    assert!(matches!(
        parse_header(&bytes, len),
        Err(CatalogError::InvalidRange {
            begin: 8,
            end: 4,
            data_len: 16,
            ..
        })
    ));
}

#[test]
fn a_length_mismatch_is_refused() {
    let json = r#"{"a":{"dtype":"F32","shape":[2,3],"data_offsets":[0,20]}}"#;
    let (bytes, len) = shard(json, 20);
    assert!(matches!(
        parse_header(&bytes, len),
        Err(CatalogError::LengthMismatch {
            declared: 20,
            expected: 24,
            ..
        })
    ));
}

#[test]
fn an_unsupported_dtype_is_refused() {
    let json = r#"{"a":{"dtype":"MXFP4","shape":[4],"data_offsets":[0,4]}}"#;
    let (bytes, len) = shard(json, 4);
    assert!(matches!(
        parse_header(&bytes, len),
        Err(CatalogError::UnsupportedDtype { ref dtype, .. }) if dtype == "MXFP4"
    ));
}

#[test]
fn a_shape_product_that_overflows_is_refused_by_checked_arithmetic() {
    // Each dimension is exactly u32::MAX, so each is individually admissible
    // and only the product overflows.
    let json =
        r#"{"a":{"dtype":"F32","shape":[4294967295,4294967295,4294967295],"data_offsets":[0,4]}}"#;
    let (bytes, len) = shard(json, 4);
    assert!(matches!(
        parse_header(&bytes, len),
        Err(CatalogError::Overflow { .. })
    ));
}

#[test]
fn a_dimension_above_u32_max_is_refused() {
    let json = r#"{"a":{"dtype":"U8","shape":[4294967296],"data_offsets":[0,4]}}"#;
    let (bytes, len) = shard(json, 4);
    assert!(matches!(
        parse_header(&bytes, len),
        Err(CatalogError::InvalidShape { .. })
    ));
}

#[test]
fn a_negative_dimension_is_refused() {
    let json = r#"{"a":{"dtype":"U8","shape":[-1],"data_offsets":[0,4]}}"#;
    let (bytes, len) = shard(json, 4);
    assert!(matches!(
        parse_header(&bytes, len),
        Err(CatalogError::InvalidShape { .. })
    ));
}

#[test]
fn a_malformed_entry_is_refused() {
    for json in [
        r#"{"a":{"shape":[1],"data_offsets":[0,1]}}"#,
        r#"{"a":{"dtype":"U8","data_offsets":[0,1]}}"#,
        r#"{"a":{"dtype":"U8","shape":[1]}}"#,
        r#"{"a":{"dtype":"U8","shape":[1],"data_offsets":[0,1,2]}}"#,
        r#"{"a":7}"#,
    ] {
        let (bytes, len) = shard(json, 1);
        assert!(
            matches!(
                parse_header(&bytes, len),
                Err(CatalogError::InvalidTensorEntry { .. })
            ),
            "{json} must be refused"
        );
    }
}

#[test]
fn the_tensors_must_tile_the_data_buffer() {
    // Strict coverage. Upstream Safetensors requires the data buffer to be
    // fully covered, Round 1 admitted gaps as an extension, and all eighteen
    // shards of the real checkpoint this feature targets are gap-free, so
    // matching the format costs nothing and removes a reading in which a
    // truncated or mis-declared layout looks intentional.
    let interior = concat!(
        r#"{"a":{"dtype":"U8","shape":[4],"data_offsets":[0,4]},"#,
        r#""b":{"dtype":"U8","shape":[4],"data_offsets":[12,16]}}"#
    );
    let (bytes, len) = shard(interior, 16);
    match parse_header(&bytes, len) {
        Err(CatalogError::Gap { after, .. }) => assert_eq!(after, 4),
        other => panic!("an interior gap must be refused, got {other:?}"),
    }

    // Trailing uncovered bytes are the same defect at the end.
    let trailing = r#"{"a":{"dtype":"U8","shape":[4],"data_offsets":[0,4]}}"#;
    let (bytes, len) = shard(trailing, 8);
    match parse_header(&bytes, len) {
        Err(CatalogError::Gap { after, .. }) => assert_eq!(after, 4),
        other => panic!("trailing uncovered bytes must be refused, got {other:?}"),
    }

    // A tiled buffer passes and reports no gap.
    let tiled = concat!(
        r#"{"a":{"dtype":"U8","shape":[4],"data_offsets":[0,4]},"#,
        r#""b":{"dtype":"U8","shape":[4],"data_offsets":[4,8]}}"#
    );
    let (bytes, len) = shard(tiled, 8);
    let header = parse_header(&bytes, len).unwrap();
    assert_eq!(header.gap_bytes, 0);

    // A zero-length tensor is admitted at a boundary between tensors.
    let empty_at_boundary = concat!(
        r#"{"a":{"dtype":"U8","shape":[4],"data_offsets":[0,4]},"#,
        r#""z":{"dtype":"F32","shape":[0],"data_offsets":[4,4]},"#,
        r#""b":{"dtype":"U8","shape":[4],"data_offsets":[4,8]}}"#
    );
    let (bytes, len) = shard(empty_at_boundary, 8);
    let header = parse_header(&bytes, len).unwrap();
    assert_eq!(header.tensors.len(), 3);
    assert_eq!(header.gap_bytes, 0);
}

#[test]
fn the_shard_name_travels_into_the_refusal() {
    let json = r#"{"a":{"dtype":"U8","shape":[4],"data_offsets":[0,4]}}"#;
    let (bytes, len) = shard(json, 8);
    match parse_header_named("model-00003.safetensors", &bytes, len) {
        Err(CatalogError::Gap { shard, .. }) => {
            assert_eq!(shard, "model-00003.safetensors");
        }
        other => panic!("unexpected {other:?}"),
    }
}

#[test]
fn a_header_only_checkpoint_refuses_reads() {
    let json = r#"{"a":{"dtype":"U32","shape":[2],"data_offsets":[0,8]}}"#;
    let bytes = compose_shard(json, &[]);
    let file_len = bytes.len() as u64 + 8;
    let checkpoint = Checkpoint::from_headers(
        "census",
        vec![("model.safetensors".to_string(), file_len, bytes)],
        None,
    )
    .unwrap();
    assert!(!checkpoint.is_backed_by_files());
    // The catalog still describes the tensor; only reading it is refused.
    assert_eq!(checkpoint.catalog().get("a").unwrap().byte_len, 8);
    let mut out = [0u8; 8];
    assert!(matches!(
        checkpoint.read_tensor_bytes("a", &mut out),
        Err(CatalogError::NoBackingFile { .. })
    ));
    assert_eq!(checkpoint.payload_bytes().unwrap(), 8);
}

// --- fail-closed holes Astra found (Round 2, finding 3) -------------------

#[test]
fn an_aggregate_payload_total_that_overflows_is_refused_not_wrapped() {
    // Astra's example. Each shard declares one U8 tensor of shape
    // [u32::MAX, u32::MAX]: every dimension is admissible, the product is
    // 1.8446744e19 which still fits u64, and only the SUM of the two leaves
    // it -- where a `sum()` would panic in debug and wrap in release.
    let side = u64::from(u32::MAX);
    let bytes = side * side;
    assert!(
        bytes.checked_add(bytes).is_none(),
        "the premise of this test"
    );
    let shard = |name: &str| {
        let json = format!(
            r#"{{"{name}":{{"dtype":"U8","shape":[{side},{side}],"data_offsets":[0,{bytes}]}}}}"#
        );
        compose_shard(&json, &[])
    };
    let first = shard("a");
    let second = shard("b");
    let first_len = first.len() as u64 + bytes;
    let second_len = second.len() as u64 + bytes;
    let checkpoint = Checkpoint::from_headers(
        "aggregate",
        vec![
            ("one.safetensors".to_string(), first_len, first),
            ("two.safetensors".to_string(), second_len, second),
        ],
        Some(r#"{"weight_map":{"a":"one.safetensors","b":"two.safetensors"}}"#),
    )
    .unwrap();
    assert_eq!(checkpoint.catalog().len(), 2);
    match checkpoint.payload_bytes() {
        Err(CatalogError::Overflow { detail, .. }) => {
            assert!(detail.contains("aggregate"), "{detail}");
        }
        other => panic!("unexpected {other:?}"),
    }
}

#[test]
fn reads_are_addressed_by_name_and_ignore_a_caller_supplied_meta() {
    use safetensors_catalog::{OpenMode, TensorMeta};
    // A TensorMeta is a plain value. Before reads were name-addressed, a
    // caller could point one at offset zero, keep a valid shard and a large
    // enough byte_len, and read the header through the public API.
    let directory =
        std::env::temp_dir().join(format!("safetensors-catalog-forged-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&directory);
    std::fs::create_dir_all(&directory).unwrap();
    let json = r#"{"a":{"dtype":"U32","shape":[2],"data_offsets":[0,8]}}"#;
    let mut data = Vec::new();
    data.extend_from_slice(&7u32.to_le_bytes());
    data.extend_from_slice(&9u32.to_le_bytes());
    std::fs::write(
        directory.join("model.safetensors"),
        compose_shard(json, &data),
    )
    .unwrap();
    let checkpoint = Checkpoint::open(&directory, OpenMode::Auto).unwrap();

    let authoritative = checkpoint.catalog().get("a").unwrap().clone();
    let mut honest = [0u8; 8];
    checkpoint.read_tensor_bytes("a", &mut honest).unwrap();
    assert_eq!(u32::from_le_bytes(honest[0..4].try_into().unwrap()), 7);

    // The forged meta simply has nowhere to enter: the API takes a name.
    let forged = TensorMeta {
        data_begin: 0,
        ..authoritative.clone()
    };
    assert_ne!(forged.data_begin, authoritative.data_begin);
    let mut out = [0u8; 8];
    checkpoint
        .read_tensor_bytes(&forged.name, &mut out)
        .unwrap();
    assert_eq!(out, honest, "the authoritative entry decided the offset");

    assert!(matches!(
        checkpoint.read_tensor_bytes("absent", &mut out),
        Err(CatalogError::UnknownTensor { .. })
    ));
    assert!(matches!(
        checkpoint.read_range("absent", 0, 1, &mut out[..1]),
        Err(CatalogError::UnknownTensor { .. })
    ));
    let _ = std::fs::remove_dir_all(&directory);
}
