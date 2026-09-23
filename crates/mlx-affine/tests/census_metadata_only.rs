//! The header census cannot read a payload byte, checked three ways.
//!
//! 1. **By construction, at run time.** The census runs over a committed
//!    header-only fixture (`tests/census_header_only_fixture/`, written by
//!    `scripts/research/extract_safetensors_headers_v1.py` from a synthetic
//!    checkpoint that `scripts/research/tests/test_extract_safetensors_headers_v1.py`
//!    defines and regenerates). The fixture contains no shard at all. Every
//!    input goes through an instrumented source that records each name and
//!    panics on a shard name; the census asks for exactly the metadata names.
//! 2. **By the catalog it builds.** The checkpoint the census used is returned
//!    and probed: it is not backed by files, and every read accessor --
//!    whole-tensor, ranged, and shard hashing -- returns `NoBackingFile` for
//!    every tensor.
//! 3. **By its source.** The census core names no read API, no file system
//!    module and no constructor other than `Checkpoint::from_headers`; the
//!    example and the input reader name no catalog read API either.

#[path = "../examples/support/header_census_core.rs"]
#[allow(dead_code)]
mod header_census_core;
#[path = "../examples/support/header_census_source.rs"]
#[allow(dead_code)]
mod header_census_source;

use std::cell::RefCell;
use std::collections::BTreeSet;
use std::path::PathBuf;

use header_census_core::{parse_rules, run, Census, MetadataSource};
use header_census_source::{admit, DirectorySource};
use safetensors_catalog::CatalogError;
use serde_json::{json, Value};

fn fixture() -> PathBuf {
    [
        env!("CARGO_MANIFEST_DIR"),
        "tests",
        "census_header_only_fixture",
    ]
    .iter()
    .collect()
}

fn source_text(relative: &str) -> String {
    let path: PathBuf = [env!("CARGO_MANIFEST_DIR"), relative].iter().collect();
    std::fs::read_to_string(&path).unwrap_or_else(|error| panic!("{}: {error}", path.display()))
}

/// Code with `//` comments removed, so prose naming an API does not count.
fn code(text: &str) -> String {
    text.lines()
        .map(|line| match line.find("//") {
            Some(at) => &line[..at],
            None => line,
        })
        .collect::<Vec<_>>()
        .join("\n")
}

/// Records every name asked for and refuses, loudly, anything shard-like.
struct Recording {
    inner: DirectorySource,
    asked: RefCell<Vec<String>>,
}

impl Recording {
    fn new() -> Self {
        Self {
            inner: DirectorySource::new(&fixture()),
            asked: RefCell::new(Vec::new()),
        }
    }
}

impl MetadataSource for Recording {
    fn read(&self, name: &str) -> Result<Vec<u8>, String> {
        assert!(
            !name.ends_with(".safetensors"),
            "the census asked for a shard: {name}"
        );
        self.asked.borrow_mut().push(name.to_string());
        self.inner.read(name)
    }
}

fn rules() -> Vec<header_census_core::Group> {
    parse_rules(&json!({
        "schema": "pulsarmlx.f020.header-census-rules/1.1.0",
        "groups": [
            {"name": "stacked", "contains": ".stack.", "expect": "quantized"},
            {"name": "norms", "contains": "norm.", "expect": "unquantized"},
            {"name": "block0", "prefix": "blocks.0.", "contains_any": [".proj.", ".wide."]},
            {"name": "absent", "prefix": "nothing.", "expect": "absent"},
        ],
    }))
    .expect("the test rules parse")
}

fn census() -> (Census, Vec<String>) {
    let source = Recording::new();
    let census = run(&source, &rules()).expect("the census runs");
    let asked = source.asked.borrow().clone();
    (census, asked)
}

#[test]
fn the_fixture_holds_no_shard_at_all() {
    for entry in std::fs::read_dir(fixture()).unwrap() {
        let name = entry.unwrap().file_name().to_string_lossy().into_owned();
        assert!(!name.ends_with(".safetensors"), "{name} is a shard");
    }
    for entry in std::fs::read_dir(fixture().join("headers")).unwrap() {
        let name = entry.unwrap().file_name().to_string_lossy().into_owned();
        assert!(
            name.ends_with(".safetensors.header") || name.ends_with(".safetensors.header.json"),
            "{name}"
        );
    }
}

#[test]
fn the_census_asks_for_exactly_the_metadata_names() {
    let (_, asked) = census();
    let asked: BTreeSet<String> = asked.into_iter().collect();
    let expected: BTreeSet<String> = [
        "shards.json",
        "config.json",
        "model.safetensors.index.json",
        "headers/model-00001-of-00002.safetensors.header",
        "headers/model-00002-of-00002.safetensors.header",
    ]
    .iter()
    .map(|name| name.to_string())
    .collect();
    assert_eq!(asked, expected);
}

#[test]
fn the_catalog_the_census_used_has_no_payload_path() {
    let (census, _) = census();
    let mut checkpoint = census.checkpoint.expect("the fixture is admitted");
    assert!(!checkpoint.is_backed_by_files());
    assert_eq!(census.report["access"]["reads_possible"], json!(false));
    let names: Vec<String> = checkpoint.catalog().names().cloned().collect();
    assert_eq!(names.len(), 12);
    for name in &names {
        let byte_len = checkpoint.catalog().get(name).unwrap().byte_len as usize;
        let mut whole = vec![0u8; byte_len];
        assert!(
            matches!(
                checkpoint.read_tensor_bytes(name, &mut whole),
                Err(CatalogError::NoBackingFile { .. })
            ),
            "{name}: a whole-tensor read was not refused"
        );
        let mut one = [0u8; 1];
        assert!(
            matches!(
                checkpoint.read_range(name, 0, 1, &mut one),
                Err(CatalogError::NoBackingFile { .. })
            ),
            "{name}: a ranged read was not refused"
        );
    }
    assert!(matches!(
        checkpoint.hash_shards(),
        Err(CatalogError::NoBackingFile { .. })
    ));
    assert!(checkpoint
        .shards()
        .iter()
        .all(|shard| shard.sha256.is_none()));
}

#[test]
fn the_census_reports_what_the_fixture_declares() {
    let (census, _) = census();
    let report = &census.report;
    assert_eq!(report["result"], json!("OBSERVED"));
    assert_eq!(report["access"]["payload_bytes_read"], json!(0));
    assert_eq!(report["checkpoint"]["shard_count"], json!(2));
    assert_eq!(report["checkpoint"]["tensor_count"], json!(12));
    assert_eq!(report["checkpoint"]["shards_with_exact_extent"], json!(2));
    assert_eq!(
        report["checkpoint"]["file_bytes_equal_headers_plus_tensors"],
        json!(true)
    );
    for shard in report["shards"].as_array().unwrap() {
        assert_eq!(shard["header_sha256_matches_record"], json!(true));
        assert_eq!(shard["header_is_exactly_prefix_plus_n"], json!(true));
        assert_eq!(
            shard["tensor_bytes_plus_8_plus_n_equals_file_len"],
            json!(true)
        );
    }
    let index = &report["index"];
    assert_eq!(index["every_indexed_tensor_in_its_shard"], json!(true));
    assert_eq!(index["no_unindexed_tensor"], json!(true));
    assert_eq!(
        index["declared_total_size_equals_tensor_bytes"],
        json!(true)
    );
    assert_eq!(report["configuration"]["status"], json!("PARSED"));
    assert_eq!(report["configuration"]["override_count"], json!(1));

    let modules = &report["modules"];
    assert_eq!(modules["count"], json!(5));
    assert_eq!(modules["quantized"], json!(3));
    assert_eq!(modules["unquantized"], json!(2));
    assert_eq!(modules["refused"], json!(0));
    assert_eq!(
        modules["combinations"],
        json!({
            "bits 4 group_size 64 metadata BF16": 1,
            "bits 4 group_size 64 metadata F32": 1,
            "bits 8 group_size 64 metadata F16": 1,
        })
    );
    assert_eq!(
        modules["resolved_from"],
        json!({"default": 2, "explicit_override": 1})
    );
    assert_eq!(
        modules["stacked_slice_arithmetic"],
        json!({"checked": 1, "failed": []})
    );
    assert_eq!(
        report["overrides"]["status_counts"],
        json!({"QUANTIZED": 1})
    );
    assert_eq!(report["tensors_outside_any_module"]["count"], json!(1));

    let groups: Vec<&Value> = report["caller_supplied_groups"]["groups"]
        .as_array()
        .unwrap()
        .iter()
        .collect();
    let by_name = |name: &str| {
        *groups
            .iter()
            .find(|group| group["rule"]["name"] == json!(name))
            .unwrap()
    };
    assert_eq!(by_name("stacked")["quantized_modules"], json!(1));
    assert_eq!(by_name("stacked")["surprise_count"], json!(0));
    assert_eq!(by_name("norms")["unquantized_modules"], json!(1));
    assert_eq!(by_name("block0")["quantized_modules"], json!(2));
    assert_eq!(by_name("absent")["tensors"], json!(0));
    assert_eq!(by_name("absent")["surprise_count"], json!(0));
}

#[test]
fn a_header_that_disagrees_with_its_record_is_refused() {
    struct Tampered(DirectorySource);
    impl MetadataSource for Tampered {
        fn read(&self, name: &str) -> Result<Vec<u8>, String> {
            let mut bytes = self.0.read(name)?;
            if name.ends_with(".header") {
                let last = bytes.len() - 1;
                bytes[last] = b' ';
            }
            Ok(bytes)
        }
    }
    let census = run(&Tampered(DirectorySource::new(&fixture())), &[]).unwrap();
    assert_eq!(census.report["result"], json!("REFUSED"));
    assert_eq!(census.report["refused_at"], json!("header_integrity"));
    assert!(census.checkpoint.is_none());
}

#[test]
fn the_input_reader_admits_metadata_names_only() {
    for name in [
        "shards.json",
        "config.json",
        "model.safetensors.index.json",
        "headers/model-00001-of-00002.safetensors.header",
    ] {
        admit(name).unwrap_or_else(|error| panic!("{name}: {error}"));
    }
    for name in [
        "model-00001-of-00002.safetensors",
        "headers/model-00001-of-00002.safetensors",
        "headers/../model-00001-of-00002.safetensors.header",
        "headers/sub/x.safetensors.header",
        "headers/.x.safetensors.header",
        "headers/x.bin.header",
        "../config.json",
        "/config.json",
        "tokenizer.json",
        "model_code.py",
        "__pycache__/x.pyc",
    ] {
        assert!(admit(name).is_err(), "{name} must be refused");
    }
    let refused = DirectorySource::new(&fixture()).read("model-00001-of-00002.safetensors");
    assert!(refused.unwrap_err().contains("never read"));
}

#[test]
fn rules_with_an_unknown_member_or_schema_are_refused() {
    assert!(parse_rules(&json!({
        "schema": "pulsarmlx.f020.header-census-rules/1.1.0",
        "groups": [{"name": "x", "prefx": "a"}],
    }))
    .is_err());
    assert!(parse_rules(&json!({
        "schema": "pulsarmlx.f020.header-census-rules/9.0.0",
        "groups": [],
    }))
    .is_err());
    assert!(parse_rules(&json!({
        "schema": "pulsarmlx.f020.header-census-rules/1.1.0",
        "groups": [{"name": "x"}],
    }))
    .is_err());
}

#[test]
fn the_census_code_names_no_read_path() {
    let core = code(&source_text("examples/support/header_census_core.rs"));
    assert!(core.contains("Checkpoint::from_headers("));
    for (at, _) in core.match_indices("Checkpoint::") {
        assert!(
            core[at..].starts_with("Checkpoint::from_headers"),
            "header_census_core.rs names {}",
            &core[at..(at + 40).min(core.len())]
        );
    }
    for forbidden in [
        "Checkpoint::open",
        "read_tensor_bytes",
        "read_range",
        "hash_shards",
        "TensorStore",
        "std::fs",
        "fs::",
        "File::",
        "OpenOptions",
        "mmap",
        "pread",
        "read_exact_at",
        "dequantize",
        "unpack_codes",
        "std::io",
    ] {
        assert!(
            !core.contains(forbidden),
            "header_census_core.rs names {forbidden}"
        );
    }
    for file in [
        "examples/header_census.rs",
        "examples/support/header_census_source.rs",
    ] {
        let text = code(&source_text(file));
        for forbidden in [
            "Checkpoint",
            "read_tensor_bytes",
            "read_range",
            "hash_shards",
            "TensorStore",
            "mmap",
        ] {
            assert!(!text.contains(forbidden), "{file} names {forbidden}");
        }
    }
}
