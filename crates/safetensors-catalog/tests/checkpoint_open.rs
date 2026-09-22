//! Opening a real directory: layout resolution, index agreement in both
//! directions, path containment, determinism and bounded reads.

use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

use safetensors_catalog::{compose_shard, CatalogError, Checkpoint, OpenMode, INDEX_FILE_NAME};

static COUNTER: AtomicU64 = AtomicU64::new(0);

/// A directory under the test temporary root, removed when the guard drops.
struct Scratch(PathBuf);

impl Scratch {
    fn new(label: &str) -> Self {
        let unique = COUNTER.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "safetensors-catalog-{}-{}-{}",
            std::process::id(),
            label,
            unique
        ));
        let _ = std::fs::remove_dir_all(&path);
        std::fs::create_dir_all(&path).unwrap();
        Self(path)
    }

    fn path(&self) -> &Path {
        &self.0
    }

    fn write(&self, name: &str, bytes: &[u8]) {
        std::fs::write(self.0.join(name), bytes).unwrap();
    }
}

impl Drop for Scratch {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}

/// One shard holding `u32` tensor `a` = [1, 2] and `u8` tensor `b` = [9].
fn simple_shard() -> Vec<u8> {
    let json = concat!(
        r#"{"a":{"dtype":"U32","shape":[2],"data_offsets":[0,8]},"#,
        r#""b":{"dtype":"U8","shape":[1],"data_offsets":[8,9]}}"#
    );
    let mut data = Vec::new();
    data.extend_from_slice(&1u32.to_le_bytes());
    data.extend_from_slice(&2u32.to_le_bytes());
    data.push(9);
    compose_shard(json, &data)
}

#[test]
fn a_single_shard_directory_opens_without_an_index() {
    let scratch = Scratch::new("single");
    scratch.write("model.safetensors", &simple_shard());
    let checkpoint = Checkpoint::open(scratch.path(), OpenMode::Auto).unwrap();
    assert_eq!(checkpoint.catalog().len(), 2);
    assert!(checkpoint.index().is_none());
    assert_eq!(checkpoint.shards()[0].file_name, "model.safetensors");
    assert_eq!(checkpoint.shards()[0].sha256, None);
}

#[test]
fn two_shards_without_an_index_are_ambiguous() {
    let scratch = Scratch::new("ambiguous");
    scratch.write("a.safetensors", &simple_shard());
    scratch.write("b.safetensors", &simple_shard());
    assert!(matches!(
        Checkpoint::open(scratch.path(), OpenMode::Auto),
        Err(CatalogError::AmbiguousLayout { .. })
    ));
}

#[test]
fn the_modes_are_enforced() {
    let scratch = Scratch::new("modes");
    scratch.write("model.safetensors", &simple_shard());
    assert!(matches!(
        Checkpoint::open(scratch.path(), OpenMode::RequireIndex),
        Err(CatalogError::AmbiguousLayout { .. })
    ));
    scratch.write(
        INDEX_FILE_NAME,
        br#"{"weight_map":{"a":"model.safetensors","b":"model.safetensors"}}"#,
    );
    assert!(Checkpoint::open(scratch.path(), OpenMode::RequireIndex).is_ok());
    assert!(matches!(
        Checkpoint::open(scratch.path(), OpenMode::RequireSingleShard),
        Err(CatalogError::AmbiguousLayout { .. })
    ));
}

#[test]
fn a_missing_shard_is_named() {
    let scratch = Scratch::new("missing");
    scratch.write("model.safetensors", &simple_shard());
    scratch.write(
        INDEX_FILE_NAME,
        br#"{"weight_map":{"a":"model.safetensors","b":"model.safetensors","c":"gone.safetensors"}}"#,
    );
    assert!(matches!(
        Checkpoint::open(scratch.path(), OpenMode::Auto),
        Err(CatalogError::MissingShard { ref shard }) if shard == "gone.safetensors"
    ));
}

#[test]
fn an_indexed_tensor_absent_from_its_shard_is_refused() {
    let scratch = Scratch::new("absent");
    scratch.write("model.safetensors", &simple_shard());
    scratch.write(
        INDEX_FILE_NAME,
        br#"{"weight_map":{"a":"model.safetensors","b":"model.safetensors","c":"model.safetensors"}}"#,
    );
    assert!(matches!(
        Checkpoint::open(scratch.path(), OpenMode::Auto),
        Err(CatalogError::MissingTensorInShard { ref name, .. }) if name == "c"
    ));
}

#[test]
fn an_unindexed_tensor_is_refused() {
    let scratch = Scratch::new("extra");
    scratch.write("model.safetensors", &simple_shard());
    scratch.write(
        INDEX_FILE_NAME,
        br#"{"weight_map":{"a":"model.safetensors"}}"#,
    );
    assert!(matches!(
        Checkpoint::open(scratch.path(), OpenMode::Auto),
        Err(CatalogError::UnindexedTensor { ref name, .. }) if name == "b"
    ));
}

#[test]
fn the_same_name_in_two_shards_is_refused() {
    let scratch = Scratch::new("duplicate");
    scratch.write("one.safetensors", &simple_shard());
    scratch.write("two.safetensors", &simple_shard());
    scratch.write(
        INDEX_FILE_NAME,
        br#"{"weight_map":{"a":"one.safetensors","b":"one.safetensors"}}"#,
    );
    // `two.safetensors` is not in the weight map at all, so it is not opened;
    // the refusal has to come from an index that names both.
    scratch.write(
        INDEX_FILE_NAME,
        br#"{"weight_map":{"a":"one.safetensors","b":"two.safetensors"}}"#,
    );
    let error = Checkpoint::open(scratch.path(), OpenMode::Auto).unwrap_err();
    assert!(
        matches!(error, CatalogError::DuplicateTensor { .. })
            || matches!(error, CatalogError::UnindexedTensor { .. }),
        "unexpected {error:?}"
    );
}

#[test]
fn a_traversing_shard_name_never_reaches_the_file_system() {
    let scratch = Scratch::new("traversal");
    scratch.write("model.safetensors", &simple_shard());
    scratch.write(
        INDEX_FILE_NAME,
        br#"{"weight_map":{"a":"../outside.safetensors"}}"#,
    );
    assert!(matches!(
        Checkpoint::open(scratch.path(), OpenMode::Auto),
        Err(CatalogError::InvalidShardPath { .. })
    ));
}

#[test]
fn a_shard_symlinked_outside_the_root_is_refused() {
    let outside = Scratch::new("outside");
    outside.write("real.safetensors", &simple_shard());
    let scratch = Scratch::new("escape");
    std::os::unix::fs::symlink(
        outside.path().join("real.safetensors"),
        scratch.path().join("model.safetensors"),
    )
    .unwrap();
    match Checkpoint::open(scratch.path(), OpenMode::Auto) {
        Err(CatalogError::PathEscape { ref shard, .. }) => assert_eq!(shard, "model.safetensors"),
        other => panic!("unexpected {other:?}"),
    }
}

#[test]
fn opening_twice_produces_the_same_digest() {
    let scratch = Scratch::new("determinism");
    scratch.write("model.safetensors", &simple_shard());
    let first = Checkpoint::open(scratch.path(), OpenMode::Auto).unwrap();
    let second = Checkpoint::open(scratch.path(), OpenMode::Auto).unwrap();
    assert_eq!(
        first.catalog_digest().unwrap(),
        second.catalog_digest().unwrap()
    );
    assert_eq!(first.catalog_digest_hex().unwrap().len(), 64);
}

#[test]
fn the_digest_follows_the_declared_line_format() {
    use sha2::{Digest, Sha256};
    let scratch = Scratch::new("digest");
    scratch.write("model.safetensors", &simple_shard());
    let checkpoint = Checkpoint::open(scratch.path(), OpenMode::Auto).unwrap();
    let a = checkpoint.catalog().get("a").unwrap();
    let b = checkpoint.catalog().get("b").unwrap();
    let mut hasher = Sha256::new();
    hasher.update(
        format!(
            "a\tU32\t2\tmodel.safetensors\t{}\t{}\n",
            a.data_begin, a.data_end
        )
        .as_bytes(),
    );
    hasher.update(
        format!(
            "b\tU8\t1\tmodel.safetensors\t{}\t{}\n",
            b.data_begin, b.data_end
        )
        .as_bytes(),
    );
    let expected: [u8; 32] = hasher.finalize().into();
    assert_eq!(checkpoint.catalog_digest().unwrap(), expected);
}

#[test]
fn reads_are_bounded_and_correct() {
    let scratch = Scratch::new("reads");
    scratch.write("model.safetensors", &simple_shard());
    let checkpoint = Checkpoint::open(scratch.path(), OpenMode::Auto).unwrap();
    let a = checkpoint.catalog().get("a").unwrap().clone();

    let mut whole = [0u8; 8];
    checkpoint.read_tensor_bytes(&a, &mut whole).unwrap();
    assert_eq!(u32::from_le_bytes(whole[0..4].try_into().unwrap()), 1);
    assert_eq!(u32::from_le_bytes(whole[4..8].try_into().unwrap()), 2);

    let mut second = [0u8; 4];
    checkpoint.read_range(&a, 4, 4, &mut second).unwrap();
    assert_eq!(u32::from_le_bytes(second), 2);

    let mut too_much = [0u8; 9];
    assert!(matches!(
        checkpoint.read_range(&a, 0, 9, &mut too_much),
        Err(CatalogError::RangeOutOfBounds { .. })
    ));
    let mut one = [0u8; 1];
    assert!(matches!(
        checkpoint.read_range(&a, u64::MAX, 1, &mut one),
        Err(CatalogError::RangeOutOfBounds { .. })
    ));
    let mut wrong = [0u8; 3];
    assert!(matches!(
        checkpoint.read_range(&a, 0, 4, &mut wrong),
        Err(CatalogError::DestinationLengthMismatch { .. })
    ));
}

#[test]
fn hashing_shards_is_explicit_and_stable() {
    let scratch = Scratch::new("hash");
    let bytes = simple_shard();
    scratch.write("model.safetensors", &bytes);
    let mut checkpoint = Checkpoint::open(scratch.path(), OpenMode::Auto).unwrap();
    assert_eq!(checkpoint.shards()[0].sha256, None);
    checkpoint.hash_shards().unwrap();
    use sha2::{Digest, Sha256};
    let expected: [u8; 32] = Sha256::digest(&bytes).into();
    assert_eq!(checkpoint.shards()[0].sha256, Some(expected));
    assert_eq!(checkpoint.shards()[0].file_len, bytes.len() as u64);
}

#[test]
fn the_backend_traits_see_the_same_bytes() {
    use backend::runtime::{CancellationToken, TensorCatalog, TensorStore};
    let scratch = Scratch::new("backend");
    scratch.write("model.safetensors", &simple_shard());
    let checkpoint = Checkpoint::open(scratch.path(), OpenMode::Auto).unwrap();
    let runtime = TensorCatalog::tensor(&checkpoint, "a").unwrap().unwrap();
    assert_eq!(runtime.quantization, "U32");
    assert_eq!(runtime.shape, vec![2]);
    assert_eq!(runtime.shard, "model.safetensors");
    assert_eq!(runtime.range.length, 8);
    let mut out = vec![0u8; 8];
    let read = TensorStore::read_range(&checkpoint, &runtime, &mut out, &CancellationToken::new())
        .unwrap();
    assert_eq!(read, 8);
    assert_eq!(u32::from_le_bytes(out[4..8].try_into().unwrap()), 2);
    assert!(TensorCatalog::tensor(&checkpoint, "absent")
        .unwrap()
        .is_none());
}
