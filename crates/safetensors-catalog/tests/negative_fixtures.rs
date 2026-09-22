//! Every committed negative fixture whose README names a `CatalogError`,
//! opened through `Checkpoint::open` and asserted against that exact variant.
//!
//! The README is the expectation, so a fixture cannot drift away from what it
//! claims to test without this failing.

use std::path::PathBuf;

use safetensors_catalog::{CatalogError, Checkpoint, OpenMode};

fn fixtures() -> PathBuf {
    [
        env!("CARGO_MANIFEST_DIR"),
        "../../fixtures/safetensors/negative",
    ]
    .iter()
    .collect()
}

/// The variant name, spelled as the READMEs spell it.
fn variant(error: &CatalogError) -> &'static str {
    match error {
        CatalogError::MalformedHeader { .. } => "CatalogError::MalformedHeader",
        CatalogError::HeaderTooLarge { .. } => "CatalogError::HeaderTooLarge",
        CatalogError::InvalidJson { .. } => "CatalogError::InvalidJson",
        CatalogError::DuplicateKey { .. } => "CatalogError::DuplicateKey",
        CatalogError::NotAnObject { .. } => "CatalogError::NotAnObject",
        CatalogError::InvalidMetadata { .. } => "CatalogError::InvalidMetadata",
        CatalogError::InvalidTensorEntry { .. } => "CatalogError::InvalidTensorEntry",
        CatalogError::InvalidShape { .. } => "CatalogError::InvalidShape",
        CatalogError::Overflow { .. } => "CatalogError::Overflow",
        CatalogError::InvalidRange { .. } => "CatalogError::InvalidRange",
        CatalogError::LengthMismatch { .. } => "CatalogError::LengthMismatch",
        CatalogError::UnsupportedDtype { .. } => "CatalogError::UnsupportedDtype",
        CatalogError::DuplicateTensor { .. } => "CatalogError::DuplicateTensor",
        CatalogError::Gap { .. } => "CatalogError::Gap",
        CatalogError::OverlappingRanges { .. } => "CatalogError::OverlappingRanges",
        CatalogError::InvalidIndex { .. } => "CatalogError::InvalidIndex",
        CatalogError::InvalidShardPath { .. } => "CatalogError::InvalidShardPath",
        CatalogError::AmbiguousLayout { .. } => "CatalogError::AmbiguousLayout",
        CatalogError::MissingShard { .. } => "CatalogError::MissingShard",
        CatalogError::PathEscape { .. } => "CatalogError::PathEscape",
        CatalogError::MissingTensorInShard { .. } => "CatalogError::MissingTensorInShard",
        CatalogError::UnindexedTensor { .. } => "CatalogError::UnindexedTensor",
        CatalogError::RangeOutOfBounds { .. } => "CatalogError::RangeOutOfBounds",
        CatalogError::DestinationLengthMismatch { .. } => "CatalogError::DestinationLengthMismatch",
        CatalogError::NoBackingFile { .. } => "CatalogError::NoBackingFile",
        CatalogError::UnknownTensor { .. } => "CatalogError::UnknownTensor",
        CatalogError::PrematureEof { .. } => "CatalogError::PrematureEof",
        CatalogError::Io { .. } => "CatalogError::Io",
        _ => "CatalogError::<unlisted>",
    }
}

#[test]
fn every_catalog_negative_fixture_is_refused_with_the_variant_it_declares() {
    let root = fixtures();
    let mut entries: Vec<PathBuf> = std::fs::read_dir(&root)
        .unwrap_or_else(|e| panic!("{}: {e}", root.display()))
        .map(|entry| entry.unwrap().path())
        .filter(|path| path.is_dir())
        .collect();
    entries.sort();
    assert!(
        entries.len() >= 20,
        "expected a real negative corpus, found {}",
        entries.len()
    );

    let mut exercised = 0usize;
    let mut skipped = Vec::new();
    for directory in entries {
        let name = directory
            .file_name()
            .unwrap()
            .to_string_lossy()
            .into_owned();
        let readme = std::fs::read_to_string(directory.join("README")).unwrap();
        let expected = readme.lines().next().unwrap().trim().to_string();
        if !expected.starts_with("CatalogError::") {
            skipped.push(name);
            continue;
        }
        match Checkpoint::open(&directory, OpenMode::Auto) {
            Ok(_) => panic!("{name}: opened, but the fixture declares {expected}"),
            Err(error) => assert_eq!(
                variant(&error),
                expected,
                "{name}: got {error:?}, the fixture declares {expected}"
            ),
        }
        exercised += 1;
    }
    assert!(
        exercised >= 15,
        "only {exercised} catalog negatives were exercised"
    );
    // The rest are affine cases, exercised by mlx-affine's own fixture test.
    for name in &skipped {
        assert!(
            name.starts_with("triple-") || name.starts_with("config-") || name.starts_with("json-"),
            "{name} declares neither a CatalogError nor an affine case"
        );
    }
}

#[test]
fn the_positive_fixtures_open_and_are_deterministic() {
    let root: PathBuf = [env!("CARGO_MANIFEST_DIR"), "../../fixtures/safetensors"]
        .iter()
        .collect();

    let uniform = Checkpoint::open(&root.join("uniform-affine-v1"), OpenMode::Auto).unwrap();
    assert_eq!(uniform.shards().len(), 1);
    assert_eq!(uniform.catalog().len(), 9);
    assert!(uniform.index().is_none());
    assert_eq!(uniform.headers()[0].metadata["format"], "mlx");

    let mixed = Checkpoint::open(&root.join("mixed-4-8-v1"), OpenMode::Auto).unwrap();
    assert_eq!(mixed.shards().len(), 3);
    assert_eq!(mixed.catalog().len(), 17);
    assert!(mixed.index().unwrap().total_size.is_none());
    // Coverage is strict, so every positive fixture tiles its data buffer.
    assert_eq!(mixed.headers().iter().map(|h| h.gap_bytes).sum::<u64>(), 0);

    let declared =
        Checkpoint::open(&root.join("mixed-4-8-index-total-size-v1"), OpenMode::Auto).unwrap();
    let total = declared.index().unwrap().total_size.unwrap();
    // This asserts a property of the fixture's generator, not a rule of the
    // format. `metadata.total_size` is informational and the catalog
    // constrains nothing by it -- deliberately: at least one real checkpoint
    // declares the sum of its FILE sizes, header bytes included, which is
    // more than the sum of its tensors
    // (docs/architecture/reviews/evidence/f020-slice1-metadata-compatibility-v1.json,
    // finding F1). Turning this equality into a validated invariant would
    // reject a real, correct checkpoint.
    assert_eq!(total, declared.payload_bytes().unwrap());
    assert_eq!(
        declared.catalog_digest().unwrap(),
        mixed.catalog_digest().unwrap()
    );

    let again = Checkpoint::open(&root.join("mixed-4-8-v1"), OpenMode::Auto).unwrap();
    assert_eq!(
        again.catalog_digest_hex().unwrap(),
        mixed.catalog_digest_hex().unwrap()
    );
}

#[test]
fn the_committed_escaped_key_fixtures_carry_the_decoded_path() {
    // The corpus walk above asserts the variant each README declares. These
    // three additionally assert the field inside it, because the whole point
    // of the fixture is which name the two members turned out to share --
    // and because, until Round 3, no committed fixture contained a \uXXXX
    // escape at all (Astra's round-2 finding 2).
    let root = fixtures();

    match Checkpoint::open(
        &root.join("json-escaped-duplicate-tensor-name"),
        OpenMode::Auto,
    ) {
        Err(CatalogError::DuplicateKey { path }) => assert_eq!(path, "m"),
        other => panic!("expected the decoded name, got {other:?}"),
    }

    match Checkpoint::open(
        &root.join("json-surrogate-pair-duplicate-metadata"),
        OpenMode::Auto,
    ) {
        Err(CatalogError::DuplicateKey { path }) => {
            assert_eq!(path, "__metadata__.\u{1f600}");
        }
        other => panic!("expected the combined surrogate pair, got {other:?}"),
    }

    match Checkpoint::open(
        &root.join("json-lone-surrogate-tensor-name"),
        OpenMode::Auto,
    ) {
        Err(CatalogError::InvalidJson { detail, .. }) => {
            assert!(detail.contains("lone high surrogate"), "{detail}");
        }
        other => panic!("expected a refusal, got {other:?}"),
    }
}
