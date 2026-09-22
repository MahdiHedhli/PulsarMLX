//! `model.safetensors.index.json`: the map from tensor name to shard file.
//!
//! Shard names are treated as hostile input. They name a file *inside* the
//! checkpoint root and nothing else: no directory component, no traversal, no
//! absolute path, no NUL. The check is a whitelist, so a spelling nobody
//! anticipated is refused rather than interpreted.

use std::collections::BTreeMap;

use serde_json::Value;

use crate::error::{CatalogError, Result};

/// The parsed index.
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct Index {
    /// Tensor name to shard file name, ordered.
    pub weight_map: BTreeMap<String, String>,
    /// `metadata.total_size`, when the index declares it.
    pub total_size: Option<u64>,
}

impl Index {
    /// The distinct shard file names, sorted.
    pub fn shards(&self) -> Vec<String> {
        let mut names: Vec<String> = self.weight_map.values().cloned().collect();
        names.sort();
        names.dedup();
        names
    }
}

/// Accept a shard file name only if it is a plain `*.safetensors` file name.
///
/// Admitted: a non-empty run of ASCII letters, digits, `.`, `_` and `-` that
/// does not begin with `.` or `-`, contains no `/`, `\` or NUL, is neither
/// `.` nor `..`, and ends in `.safetensors` with at least one character before
/// the extension.
pub fn validate_shard_path(path: &str) -> Result<()> {
    let refuse = || CatalogError::InvalidShardPath {
        path: path.to_string(),
    };
    if path.is_empty() || path == "." || path == ".." {
        return Err(refuse());
    }
    if !path
        .bytes()
        .all(|byte| byte.is_ascii_alphanumeric() || byte == b'.' || byte == b'_' || byte == b'-')
    {
        return Err(refuse());
    }
    if path.starts_with('.') || path.starts_with('-') {
        return Err(refuse());
    }
    const EXTENSION: &str = ".safetensors";
    if !path.ends_with(EXTENSION) || path.len() <= EXTENSION.len() {
        return Err(refuse());
    }
    Ok(())
}

/// Parse `model.safetensors.index.json`.
pub fn parse_index(json: &str) -> Result<Index> {
    let value: Value = serde_json::from_str(json).map_err(|error| CatalogError::InvalidIndex {
        detail: error.to_string(),
    })?;
    let object = value
        .as_object()
        .ok_or_else(|| CatalogError::InvalidIndex {
            detail: "index is not an object".to_string(),
        })?;

    let map = object
        .get("weight_map")
        .ok_or_else(|| CatalogError::InvalidIndex {
            detail: "no weight_map".to_string(),
        })?
        .as_object()
        .ok_or_else(|| CatalogError::InvalidIndex {
            detail: "weight_map is not an object".to_string(),
        })?;

    let mut weight_map = BTreeMap::new();
    for (name, shard) in map {
        let shard = shard.as_str().ok_or_else(|| CatalogError::InvalidIndex {
            detail: format!("weight_map entry for {name:?} is not a string"),
        })?;
        validate_shard_path(shard)?;
        weight_map.insert(name.clone(), shard.to_string());
    }
    if weight_map.is_empty() {
        return Err(CatalogError::InvalidIndex {
            detail: "weight_map is empty".to_string(),
        });
    }

    let total_size = match object.get("metadata") {
        None => None,
        Some(Value::Object(metadata)) => match metadata.get("total_size") {
            None => None,
            Some(entry) => Some(entry.as_u64().ok_or_else(|| CatalogError::InvalidIndex {
                detail: "metadata.total_size is not a non-negative integer".to_string(),
            })?),
        },
        Some(_) => {
            return Err(CatalogError::InvalidIndex {
                detail: "metadata is not an object".to_string(),
            })
        }
    };

    Ok(Index {
        weight_map,
        total_size,
    })
}

#[cfg(test)]
mod tests {
    use super::{parse_index, validate_shard_path};
    use crate::error::CatalogError;

    #[test]
    fn plain_shard_names_are_accepted() {
        for name in [
            "model.safetensors",
            "model-00001-of-00018.safetensors",
            "a_b.safetensors",
        ] {
            validate_shard_path(name).expect(name);
        }
    }

    #[test]
    fn escaping_shard_names_are_refused() {
        for name in [
            "",
            ".",
            "..",
            "../x.safetensors",
            "/abs/x.safetensors",
            "sub/x.safetensors",
            "sub\\x.safetensors",
            "x.safetensors\u{0}",
            ".hidden.safetensors",
            "-lead.safetensors",
            "model.bin",
            ".safetensors",
        ] {
            assert!(
                matches!(
                    validate_shard_path(name),
                    Err(CatalogError::InvalidShardPath { .. })
                ),
                "{name:?} must be refused"
            );
        }
    }

    #[test]
    fn total_size_is_optional() {
        let without = parse_index(r#"{"weight_map":{"a":"model.safetensors"}}"#).unwrap();
        assert_eq!(without.total_size, None);
        let with =
            parse_index(r#"{"metadata":{"total_size":12},"weight_map":{"a":"model.safetensors"}}"#)
                .unwrap();
        assert_eq!(with.total_size, Some(12));
        assert_eq!(with.shards(), vec!["model.safetensors".to_string()]);
    }

    #[test]
    fn a_traversing_weight_map_entry_is_refused() {
        let error = parse_index(r#"{"weight_map":{"a":"../escape.safetensors"}}"#).unwrap_err();
        assert!(matches!(error, CatalogError::InvalidShardPath { .. }));
    }
}
