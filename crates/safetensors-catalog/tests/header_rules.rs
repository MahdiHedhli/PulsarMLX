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
    let (bytes, len) = shard("[1,2,3]", 0);
    assert!(matches!(
        parse_header(&bytes, len),
        Err(CatalogError::NotAnObject { .. })
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
    assert!(matches!(
        parse_header(&bytes, len),
        Err(CatalogError::DuplicateTensor { .. })
    ));
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
    assert!(matches!(
        parse_header(&bytes, len),
        Err(CatalogError::InvalidRange { .. })
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
fn gaps_are_allowed_and_counted() {
    let json = concat!(
        r#"{"a":{"dtype":"U8","shape":[4],"data_offsets":[0,4]},"#,
        r#""b":{"dtype":"U8","shape":[4],"data_offsets":[12,16]}}"#
    );
    let (bytes, len) = shard(json, 16);
    let header = parse_header(&bytes, len).unwrap();
    assert_eq!(header.gap_bytes, 8);
}

#[test]
fn the_shard_name_travels_into_the_refusal() {
    let (bytes, len) = shard("[1]", 0);
    match parse_header_named("model-00003.safetensors", &bytes, len) {
        Err(CatalogError::NotAnObject { shard }) => {
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
    let tensor = checkpoint.catalog().get("a").unwrap().clone();
    let mut out = [0u8; 8];
    assert!(matches!(
        checkpoint.read_tensor_bytes(&tensor, &mut out),
        Err(CatalogError::NoBackingFile { .. })
    ));
    assert_eq!(checkpoint.payload_bytes(), 8);
}
