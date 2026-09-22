//! A model-neutral reader for sharded Safetensors checkpoints.
//!
//! The scope is deliberately small and deliberately blind to any particular
//! model: headers, the shard index, a deterministic tensor catalog, checked
//! byte-range arithmetic and bounded reads. There are no tensor-name
//! conventions here, no architecture constants and no regular expressions over
//! names. Anything that knows what a name *means* belongs above this crate.
//!
//! # What it refuses
//!
//! Every refusal is a distinct [`CatalogError`] variant, so a test can assert
//! which defect it found rather than that something went wrong. The whole
//! header of every shard is validated before a byte of payload is readable:
//! shapes are multiplied with `checked_mul`, declared ranges must lie inside
//! the data section and must equal `product(shape) * dtype.size_bytes()`,
//! tensors may not overlap, names may not repeat inside a shard or across
//! shards, the index and the headers must agree in both directions, and a
//! shard file name must be a plain name inside the root.
//!
//! # What it does not do
//!
//! It does not memory-map (reads go through `pread`; a mapped reader is a
//! later addition behind these same accessors), it does not hash shards unless
//! asked, and it does not dequantize. It also carries no opinion about which
//! dtypes a consumer may accept: it parses every standard Safetensors dtype
//! and reports its size.

#![forbid(unsafe_code)]

mod backend_impl;
pub mod checkpoint;
pub mod dtype;
pub mod error;
pub mod header;
pub mod index;

pub use checkpoint::{
    hex, Catalog, Checkpoint, OpenMode, ShardId, ShardProvenance, TensorMeta, INDEX_FILE_NAME,
};
pub use dtype::Dtype;
pub use error::{CatalogError, Result};
pub use header::{
    compose_shard, parse_header, parse_header_named, HeaderTensor, ShardHeader, MAX_HEADER_BYTES,
    METADATA_KEY,
};
pub use index::{parse_index, validate_shard_path, Index};
