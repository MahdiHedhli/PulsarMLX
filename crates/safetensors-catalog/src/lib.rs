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
//! the header must begin with `{`, shapes are multiplied with `checked_mul`,
//! declared ranges must lie inside the data section and must equal
//! `product(shape) * dtype.size_bytes()`, the tensors must **tile** that
//! section with no gaps and no overlaps, no JSON member may repeat at any
//! depth, names may not repeat across shards, the index and the headers must
//! agree in both directions, and every file is admitted by descriptor inside
//! the root rather than by pathname.
//!
//! # What it does not do
//!
//! It does not memory-map (reads go through `pread`; a mapped reader is a
//! later addition behind these same accessors), it does not hash shards unless
//! asked, and it does not dequantize. It also carries no opinion about which
//! of the dtypes it admits a consumer may accept: it parses the fifteen
//! admitted Safetensors dtype strings and reports their sizes, and refuses the
//! rest -- including upstream's further and sub-byte types -- by name.

// `admission` needs `openat`/`fstat` to bind an opened descriptor to the
// admitted root; every other module is `unsafe`-free and this is a `deny` so
// that the one module which needs it must say so explicitly.
#![deny(unsafe_code)]

#[allow(unsafe_code)]
pub mod admission;
mod backend_impl;
pub mod checkpoint;
pub mod dtype;
pub mod error;
pub mod header;
pub mod index;
pub mod json_guard;

pub use admission::{same_object, Admitted, FileIdentity, RootDirectory};
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
pub use json_guard::{reject_duplicate_keys, reject_duplicate_keys_str, MAX_DEPTH};
