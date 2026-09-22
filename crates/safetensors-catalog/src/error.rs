//! Every way this crate refuses a checkpoint.
//!
//! The variants are the vocabulary the negative fixtures assert against, so
//! they are deliberately narrow: one variant per distinct refusal, never a
//! catch-all that would let two different defects look alike.

use std::fmt;

/// The shard file name a refusal is about, when one applies.
pub type ShardName = String;

#[derive(Debug)]
#[non_exhaustive]
pub enum CatalogError {
    /// The 8-byte length prefix is absent or truncated, the declared header
    /// length does not fit inside the file, or the header bytes are short.
    MalformedHeader { shard: ShardName, detail: String },
    /// The declared header length exceeds [`crate::MAX_HEADER_BYTES`].
    HeaderTooLarge { shard: ShardName, header_len: u64 },
    /// The header bytes are not valid JSON.
    InvalidJson { shard: ShardName, detail: String },
    /// A JSON object declares the same member twice, at any depth. The input
    /// has two readings and is refused rather than resolved to the last one.
    DuplicateKey { path: String },
    /// The header JSON is valid but is not a JSON object.
    NotAnObject { shard: ShardName },
    /// `__metadata__` is present but is not a map of string to string.
    InvalidMetadata { shard: ShardName, detail: String },
    /// A tensor entry is missing a required field or has one of the wrong type.
    InvalidTensorEntry {
        shard: ShardName,
        name: String,
        detail: String,
    },
    /// A shape entry is absent, negative, non-integral or above `u32::MAX`.
    InvalidShape {
        shard: ShardName,
        name: String,
        detail: String,
    },
    /// A checked multiplication overflowed `u64` while sizing a tensor.
    Overflow {
        shard: ShardName,
        name: String,
        detail: String,
    },
    /// `data_offsets` is not an ordered pair inside the data section.
    InvalidRange {
        shard: ShardName,
        name: String,
        begin: u64,
        end: u64,
        data_len: u64,
    },
    /// `end - begin` is not `product(shape) * dtype.size_bytes()`.
    LengthMismatch {
        shard: ShardName,
        name: String,
        declared: u64,
        expected: u64,
    },
    /// The dtype string is not a standard Safetensors dtype.
    UnsupportedDtype { name: String, dtype: String },
    /// The same tensor name appears twice in one header, or in two shards.
    DuplicateTensor {
        name: String,
        first: ShardName,
        second: ShardName,
    },
    /// The tensors do not tile the data buffer. Upstream Safetensors requires
    /// complete coverage; `after` is the first uncovered offset.
    Gap { shard: ShardName, after: u64 },
    /// Two tensors in one shard claim overlapping byte ranges.
    OverlappingRanges {
        shard: ShardName,
        first: String,
        second: String,
    },
    /// The index JSON is malformed or missing a required member.
    InvalidIndex { detail: String },
    /// A shard file name in the index is empty, not a plain file name, or does
    /// not end in `.safetensors`.
    InvalidShardPath { path: String },
    /// The root has neither an index nor exactly one `*.safetensors` file.
    AmbiguousLayout { detail: String },
    /// A shard named by the index does not exist under the root.
    MissingShard { shard: ShardName },
    /// A shard path resolved outside the canonicalized root.
    PathEscape { shard: ShardName, resolved: String },
    /// The index maps a tensor to a shard whose header does not contain it.
    MissingTensorInShard { name: String, shard: ShardName },
    /// A shard header contains a tensor the index does not map. No silent extras.
    UnindexedTensor { name: String, shard: ShardName },
    /// A read asked for bytes outside the tensor.
    RangeOutOfBounds {
        name: String,
        offset_within: u64,
        len: u64,
        byte_len: u64,
    },
    /// The destination buffer length does not match the requested read length.
    DestinationLengthMismatch {
        name: String,
        expected: u64,
        actual: u64,
    },
    /// A read was attempted on a catalog built from headers alone.
    NoBackingFile { name: String },
    /// A tensor name is not in the catalog.
    UnknownTensor { name: String },
    /// A shard ended before the length it was admitted with. The file changed
    /// under the open, so any digest over it would describe neither version.
    PrematureEof {
        shard: ShardName,
        declared: u64,
        at: u64,
    },
    /// The root is not a directory, or a file operation failed.
    Io { path: String, detail: String },
}

impl fmt::Display for CatalogError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::MalformedHeader { shard, detail } => {
                write!(f, "{shard}: malformed safetensors header: {detail}")
            }
            Self::HeaderTooLarge { shard, header_len } => {
                write!(f, "{shard}: header length {header_len} exceeds the admitted maximum")
            }
            Self::InvalidJson { shard, detail } => write!(f, "{shard}: header is not JSON: {detail}"),
            Self::DuplicateKey { path } => {
                write!(f, "duplicate JSON member {path:?}: the document has two readings")
            }
            Self::NotAnObject { shard } => write!(f, "{shard}: header JSON is not an object"),
            Self::InvalidMetadata { shard, detail } => {
                write!(f, "{shard}: __metadata__ is not a string map: {detail}")
            }
            Self::InvalidTensorEntry { shard, name, detail } => {
                write!(f, "{shard}: tensor {name}: {detail}")
            }
            Self::InvalidShape { shard, name, detail } => {
                write!(f, "{shard}: tensor {name}: invalid shape: {detail}")
            }
            Self::Overflow { shard, name, detail } => {
                write!(f, "{shard}: tensor {name}: checked arithmetic overflowed: {detail}")
            }
            Self::InvalidRange { shard, name, begin, end, data_len } => write!(
                f,
                "{shard}: tensor {name}: range [{begin}, {end}) is not inside a {data_len}-byte data section"
            ),
            Self::LengthMismatch { shard, name, declared, expected } => write!(
                f,
                "{shard}: tensor {name}: declared range is {declared} bytes, shape and dtype require {expected}"
            ),
            Self::UnsupportedDtype { name, dtype } => {
                write!(f, "tensor {name}: unsupported dtype {dtype:?}")
            }
            Self::DuplicateTensor { name, first, second } => {
                write!(f, "tensor {name} appears in both {first} and {second}")
            }
            Self::Gap { shard, after } => write!(
                f,
                "{shard}: the data buffer is not fully covered; nothing claims offset {after}"
            ),
            Self::OverlappingRanges { shard, first, second } => {
                write!(f, "{shard}: tensors {first} and {second} overlap")
            }
            Self::InvalidIndex { detail } => write!(f, "invalid index: {detail}"),
            Self::InvalidShardPath { path } => write!(f, "invalid shard path {path:?}"),
            Self::AmbiguousLayout { detail } => write!(f, "ambiguous checkpoint layout: {detail}"),
            Self::MissingShard { shard } => write!(f, "shard {shard} is missing"),
            Self::PathEscape { shard, resolved } => {
                write!(f, "shard {shard} resolves outside the root, to {resolved}")
            }
            Self::MissingTensorInShard { name, shard } => {
                write!(f, "index maps {name} to {shard}, whose header does not contain it")
            }
            Self::UnindexedTensor { name, shard } => {
                write!(f, "{shard} contains {name}, which the index does not map")
            }
            Self::RangeOutOfBounds { name, offset_within, len, byte_len } => write!(
                f,
                "tensor {name}: read of {len} bytes at {offset_within} exceeds its {byte_len} bytes"
            ),
            Self::DestinationLengthMismatch { name, expected, actual } => write!(
                f,
                "tensor {name}: destination holds {actual} bytes, the read needs exactly {expected}"
            ),
            Self::NoBackingFile { name } => {
                write!(f, "tensor {name}: this catalog was built from headers alone and cannot read")
            }
            Self::UnknownTensor { name } => write!(f, "tensor {name} is not in the catalog"),
            Self::PrematureEof { shard, declared, at } => write!(
                f,
                "{shard} was admitted as {declared} bytes but ended at {at}"
            ),
            Self::Io { path, detail } => write!(f, "{path}: {detail}"),
        }
    }
}

impl std::error::Error for CatalogError {}

pub type Result<T> = std::result::Result<T, CatalogError>;
