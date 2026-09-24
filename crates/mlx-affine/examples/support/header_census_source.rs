//! The census's only file access: a directory of extracted metadata, read by
//! name through an allowlist.
//!
//! A name is admitted only if it is one of the three fixed JSON files or a
//! `headers/<name>.header` file. Anything ending in `.safetensors` -- a shard
//! -- is refused by name, as is any other path, so pointing the census at a
//! real checkpoint directory cannot make it open a shard. Every read is
//! bounded by a length checked on the open descriptor before any byte is read.

use std::io::Read;
use std::path::{Path, PathBuf};

use super::header_census_core::{MetadataSource, CONFIG_FILE, SHARDS_FILE};
use safetensors_catalog::{INDEX_FILE_NAME, MAX_HEADER_BYTES};

/// The largest JSON input the census reads.
pub const MAX_JSON_BYTES: u64 = 64 * 1024 * 1024;
const HEADER_DIRECTORY: &str = "headers/";
const HEADER_SUFFIX: &str = ".header";

/// Why a name is admitted, and so how many bytes it may hold.
pub fn admit(name: &str) -> Result<u64, String> {
    if name.ends_with(".safetensors") {
        return Err(format!("{name}: a shard is never read by the census"));
    }
    if name == SHARDS_FILE || name == CONFIG_FILE || name == INDEX_FILE_NAME {
        return Ok(MAX_JSON_BYTES);
    }
    if let Some(rest) = name.strip_prefix(HEADER_DIRECTORY) {
        if let Some(stem) = rest.strip_suffix(HEADER_SUFFIX) {
            if !stem.is_empty()
                && stem.ends_with(".safetensors")
                && !stem.starts_with('.')
                && stem
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b == b'.' || b == b'_' || b == b'-')
            {
                return Ok(8 + MAX_HEADER_BYTES);
            }
        }
    }
    Err(format!("{name}: not an admitted census input"))
}

/// Reads admitted names under one directory.
pub struct DirectorySource {
    root: PathBuf,
}

impl DirectorySource {
    pub fn new(root: &Path) -> Self {
        Self {
            root: root.to_path_buf(),
        }
    }
}

impl MetadataSource for DirectorySource {
    fn read(&self, name: &str) -> Result<Vec<u8>, String> {
        let limit = admit(name)?;
        let path = self.root.join(name);
        let file = std::fs::File::open(&path).map_err(|error| format!("{name}: {error}"))?;
        let metadata = file
            .metadata()
            .map_err(|error| format!("{name}: {error}"))?;
        if !metadata.is_file() {
            return Err(format!("{name}: not a regular file"));
        }
        if metadata.len() > limit {
            return Err(format!("{name}: {} bytes exceeds {limit}", metadata.len()));
        }
        let mut bytes = Vec::with_capacity(metadata.len() as usize);
        file.take(limit + 1)
            .read_to_end(&mut bytes)
            .map_err(|error| format!("{name}: {error}"))?;
        if bytes.len() as u64 > limit {
            return Err(format!("{name}: grew past {limit} bytes while reading"));
        }
        Ok(bytes)
    }
}
