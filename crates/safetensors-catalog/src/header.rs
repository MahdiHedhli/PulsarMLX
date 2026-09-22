//! Safetensors shard headers: the 8-byte length prefix and the JSON that
//! follows it, validated to the last byte before anything is read.
//!
//! The parser is pure: it is given the header bytes and the file length and
//! touches no file system. That is what lets the same code qualify synthetic
//! fixtures, a header-only compatibility census and a real open.

use std::collections::BTreeMap;

use serde::de::{MapAccess, Visitor};
use serde::{Deserialize, Deserializer};
use serde_json::Value;

use crate::dtype::Dtype;
use crate::error::{CatalogError, Result};

/// The largest header this crate will look at. A header is metadata; a real
/// 20 GB shard still declares well under a megabyte of it.
pub const MAX_HEADER_BYTES: u64 = 100 * 1024 * 1024;

/// The reserved key that carries free-form string metadata.
pub const METADATA_KEY: &str = "__metadata__";

/// One tensor as its shard's header declares it. Offsets are relative to the
/// start of the data section, exactly as the format writes them.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct HeaderTensor {
    pub name: String,
    pub dtype: Dtype,
    pub shape: Vec<u64>,
    pub elements: u64,
    pub byte_len: u64,
    pub begin: u64,
    pub end: u64,
}

/// A whole validated shard header.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ShardHeader {
    /// The declared JSON length, i.e. the `n` of the 8-byte prefix.
    pub header_len: u64,
    /// `file_len - 8 - header_len`.
    pub data_len: u64,
    pub metadata: BTreeMap<String, String>,
    pub tensors: BTreeMap<String, HeaderTensor>,
    /// Bytes of the data section no tensor claims. Gaps are legal; they are
    /// recorded rather than tolerated silently.
    pub gap_bytes: u64,
}

/// A JSON object kept as an ordered list of pairs, so that duplicate keys
/// survive to be refused instead of being collapsed by a map.
struct Pairs(Vec<(String, Value)>);

impl<'de> Deserialize<'de> for Pairs {
    fn deserialize<D>(deserializer: D) -> std::result::Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        struct PairsVisitor;

        impl<'de> Visitor<'de> for PairsVisitor {
            type Value = Pairs;

            fn expecting(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
                f.write_str("a JSON object")
            }

            fn visit_map<A>(self, mut access: A) -> std::result::Result<Pairs, A::Error>
            where
                A: MapAccess<'de>,
            {
                let mut pairs = Vec::with_capacity(access.size_hint().unwrap_or(0));
                while let Some((key, value)) = access.next_entry::<String, Value>()? {
                    pairs.push((key, value));
                }
                Ok(Pairs(pairs))
            }
        }

        deserializer.deserialize_map(PairsVisitor)
    }
}

fn shape_entry(shard: &str, name: &str, value: &Value) -> Result<u64> {
    let number = value.as_u64().ok_or_else(|| CatalogError::InvalidShape {
        shard: shard.to_string(),
        name: name.to_string(),
        detail: format!("dimension {value} is not a non-negative integer"),
    })?;
    if number > u64::from(u32::MAX) {
        return Err(CatalogError::InvalidShape {
            shard: shard.to_string(),
            name: name.to_string(),
            detail: format!("dimension {number} exceeds u32::MAX"),
        });
    }
    Ok(number)
}

fn checked_product(shard: &str, name: &str, shape: &[u64]) -> Result<u64> {
    let mut product: u64 = 1;
    for dimension in shape {
        product = product
            .checked_mul(*dimension)
            .ok_or_else(|| CatalogError::Overflow {
                shard: shard.to_string(),
                name: name.to_string(),
                detail: format!("element count overflows u64 at dimension {dimension}"),
            })?;
    }
    Ok(product)
}

fn parse_metadata(shard: &str, value: &Value) -> Result<BTreeMap<String, String>> {
    let object = value
        .as_object()
        .ok_or_else(|| CatalogError::InvalidMetadata {
            shard: shard.to_string(),
            detail: "not an object".to_string(),
        })?;
    let mut out = BTreeMap::new();
    for (key, entry) in object {
        let text = entry
            .as_str()
            .ok_or_else(|| CatalogError::InvalidMetadata {
                shard: shard.to_string(),
                detail: format!("value for {key:?} is not a string"),
            })?;
        out.insert(key.clone(), text.to_string());
    }
    Ok(out)
}

fn parse_tensor(shard: &str, name: &str, value: &Value, data_len: u64) -> Result<HeaderTensor> {
    let object = value
        .as_object()
        .ok_or_else(|| CatalogError::InvalidTensorEntry {
            shard: shard.to_string(),
            name: name.to_string(),
            detail: "entry is not an object".to_string(),
        })?;

    let dtype_text = object.get("dtype").and_then(Value::as_str).ok_or_else(|| {
        CatalogError::InvalidTensorEntry {
            shard: shard.to_string(),
            name: name.to_string(),
            detail: "missing or non-string dtype".to_string(),
        }
    })?;
    let dtype = Dtype::parse(dtype_text).ok_or_else(|| CatalogError::UnsupportedDtype {
        name: name.to_string(),
        dtype: dtype_text.to_string(),
    })?;

    let shape_value = object
        .get("shape")
        .and_then(Value::as_array)
        .ok_or_else(|| CatalogError::InvalidTensorEntry {
            shard: shard.to_string(),
            name: name.to_string(),
            detail: "missing or non-array shape".to_string(),
        })?;
    let mut shape = Vec::with_capacity(shape_value.len());
    for entry in shape_value {
        shape.push(shape_entry(shard, name, entry)?);
    }

    let offsets = object
        .get("data_offsets")
        .and_then(Value::as_array)
        .ok_or_else(|| CatalogError::InvalidTensorEntry {
            shard: shard.to_string(),
            name: name.to_string(),
            detail: "missing or non-array data_offsets".to_string(),
        })?;
    if offsets.len() != 2 {
        return Err(CatalogError::InvalidTensorEntry {
            shard: shard.to_string(),
            name: name.to_string(),
            detail: format!("data_offsets has {} entries, not 2", offsets.len()),
        });
    }
    let mut bounds = [0u64; 2];
    for (slot, entry) in bounds.iter_mut().zip(offsets) {
        *slot = entry
            .as_u64()
            .ok_or_else(|| CatalogError::InvalidTensorEntry {
                shard: shard.to_string(),
                name: name.to_string(),
                detail: format!("data_offsets entry {entry} is not a non-negative integer"),
            })?;
    }
    let [begin, end] = bounds;
    if begin > end || end > data_len {
        return Err(CatalogError::InvalidRange {
            shard: shard.to_string(),
            name: name.to_string(),
            begin,
            end,
            data_len,
        });
    }

    let elements = checked_product(shard, name, &shape)?;
    let byte_len =
        elements
            .checked_mul(dtype.size_bytes())
            .ok_or_else(|| CatalogError::Overflow {
                shard: shard.to_string(),
                name: name.to_string(),
                detail: "element count times dtype size overflows u64".to_string(),
            })?;
    let declared = end - begin;
    if declared != byte_len {
        return Err(CatalogError::LengthMismatch {
            shard: shard.to_string(),
            name: name.to_string(),
            declared,
            expected: byte_len,
        });
    }

    Ok(HeaderTensor {
        name: name.to_string(),
        dtype,
        shape,
        elements,
        byte_len,
        begin,
        end,
    })
}

/// Parse and fully validate one shard header.
///
/// `bytes` must start at the file's first byte and hold at least the prefix
/// and the declared JSON; `file_len` is the whole file's length, which is what
/// bounds the data section.
pub fn parse_header(bytes: &[u8], file_len: u64) -> Result<ShardHeader> {
    parse_header_named("<shard>", bytes, file_len)
}

/// [`parse_header`] with a shard name attached to every refusal.
pub fn parse_header_named(shard: &str, bytes: &[u8], file_len: u64) -> Result<ShardHeader> {
    if bytes.len() < 8 {
        return Err(CatalogError::MalformedHeader {
            shard: shard.to_string(),
            detail: format!("{} bytes cannot hold the 8-byte length prefix", bytes.len()),
        });
    }
    if file_len < 8 {
        return Err(CatalogError::MalformedHeader {
            shard: shard.to_string(),
            detail: format!("a {file_len}-byte file cannot hold the length prefix"),
        });
    }
    let mut prefix = [0u8; 8];
    prefix.copy_from_slice(&bytes[..8]);
    let header_len = u64::from_le_bytes(prefix);
    if header_len > MAX_HEADER_BYTES {
        return Err(CatalogError::HeaderTooLarge {
            shard: shard.to_string(),
            header_len,
        });
    }
    let consumed = 8u64
        .checked_add(header_len)
        .ok_or_else(|| CatalogError::MalformedHeader {
            shard: shard.to_string(),
            detail: "header length overflows u64".to_string(),
        })?;
    if consumed > file_len {
        return Err(CatalogError::MalformedHeader {
            shard: shard.to_string(),
            detail: format!("prefix and header need {consumed} bytes, the file holds {file_len}"),
        });
    }
    let available = u64::try_from(bytes.len()).unwrap_or(u64::MAX);
    if available < consumed {
        return Err(CatalogError::MalformedHeader {
            shard: shard.to_string(),
            detail: format!("{available} bytes supplied, the header needs {consumed}"),
        });
    }
    let data_len = file_len - consumed;

    let json = &bytes[8..usize::try_from(consumed).map_err(|_| CatalogError::MalformedHeader {
        shard: shard.to_string(),
        detail: "header does not fit in memory on this target".to_string(),
    })?];
    let pairs: Pairs = serde_json::from_slice(json).map_err(|error| {
        if error.is_data() {
            CatalogError::NotAnObject {
                shard: shard.to_string(),
            }
        } else {
            CatalogError::InvalidJson {
                shard: shard.to_string(),
                detail: error.to_string(),
            }
        }
    })?;

    let mut metadata = BTreeMap::new();
    let mut tensors: BTreeMap<String, HeaderTensor> = BTreeMap::new();
    let mut seen_metadata = false;
    for (key, value) in &pairs.0 {
        if key == METADATA_KEY {
            if seen_metadata {
                return Err(CatalogError::InvalidMetadata {
                    shard: shard.to_string(),
                    detail: "__metadata__ appears twice".to_string(),
                });
            }
            seen_metadata = true;
            metadata = parse_metadata(shard, value)?;
            continue;
        }
        let tensor = parse_tensor(shard, key, value, data_len)?;
        if tensors.insert(key.clone(), tensor).is_some() {
            return Err(CatalogError::DuplicateTensor {
                name: key.clone(),
                first: shard.to_string(),
                second: shard.to_string(),
            });
        }
    }

    let mut ordered: Vec<&HeaderTensor> = tensors.values().collect();
    ordered.sort_by_key(|tensor| (tensor.begin, tensor.end, tensor.name.clone()));
    let mut covered: u64 = 0;
    for window in ordered.windows(2) {
        let (first, second) = (window[0], window[1]);
        if first.end > second.begin {
            return Err(CatalogError::OverlappingRanges {
                shard: shard.to_string(),
                first: first.name.clone(),
                second: second.name.clone(),
            });
        }
    }
    for tensor in &ordered {
        covered += tensor.byte_len;
    }
    let gap_bytes = data_len - covered;

    Ok(ShardHeader {
        header_len,
        data_len,
        metadata,
        tensors,
        gap_bytes,
    })
}

/// Build the bytes of a shard file from a header JSON string and a data
/// section. Used by the fixture generator's Rust-side tests and by the
/// negative-case unit tests; it performs no validation of its own.
pub fn compose_shard(header_json: &str, data: &[u8]) -> Vec<u8> {
    let json = header_json.as_bytes();
    let mut out = Vec::with_capacity(8 + json.len() + data.len());
    out.extend_from_slice(&(json.len() as u64).to_le_bytes());
    out.extend_from_slice(json);
    out.extend_from_slice(data);
    out
}
