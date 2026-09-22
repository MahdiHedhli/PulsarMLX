//! A whole checkpoint: shards, index, the deterministic tensor catalog built
//! from them, and bounded reads.
//!
//! Two things this module deliberately does not do. It never hashes a shard
//! implicitly -- a real shard is tens of gigabytes, so [`Checkpoint::hash_shards`]
//! is an explicit call. And it does not memory-map: reads go through
//! `pread`, which needs no address space and no unmap discipline. A mapped
//! reader is a later addition behind the same accessors, not a change to them.

use std::collections::{BTreeMap, BTreeSet};
use std::fs::File;
use std::io::Read;
use std::os::unix::fs::FileExt;
use std::path::{Path, PathBuf};

use sha2::{Digest, Sha256};

use crate::dtype::Dtype;
use crate::error::{CatalogError, Result};
use crate::header::{parse_header_named, ShardHeader, MAX_HEADER_BYTES};
use crate::index::{parse_index, Index};

/// The conventional index file name.
pub const INDEX_FILE_NAME: &str = "model.safetensors.index.json";

/// An index into a checkpoint's shard list, which is sorted by file name.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct ShardId(pub u16);

/// How a root directory may be laid out.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OpenMode {
    /// Use `model.safetensors.index.json` if it exists, otherwise accept a
    /// directory holding exactly one `*.safetensors` file.
    Auto,
    /// Require the index.
    RequireIndex,
    /// Require exactly one `*.safetensors` file and no index.
    RequireSingleShard,
}

/// One tensor, located.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TensorMeta {
    pub name: String,
    pub dtype: Dtype,
    pub shape: Vec<u64>,
    pub elements: u64,
    pub byte_len: u64,
    pub shard: ShardId,
    /// Absolute file offset, i.e. `8 + header_len + begin`.
    pub data_begin: u64,
    pub data_end: u64,
}

/// What a shard is, independently of what it contains.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ShardProvenance {
    pub file_name: String,
    pub file_len: u64,
    pub header_len: u64,
    /// Only ever `Some` after an explicit [`Checkpoint::hash_shards`].
    pub sha256: Option<[u8; 32]>,
}

/// The deterministic tensor catalog.
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct Catalog {
    tensors: BTreeMap<String, TensorMeta>,
}

impl Catalog {
    pub fn get(&self, name: &str) -> Option<&TensorMeta> {
        self.tensors.get(name)
    }

    pub fn contains(&self, name: &str) -> bool {
        self.tensors.contains_key(name)
    }

    pub fn len(&self) -> usize {
        self.tensors.len()
    }

    pub fn is_empty(&self) -> bool {
        self.tensors.is_empty()
    }

    /// Every tensor, in name order.
    pub fn iter(&self) -> impl Iterator<Item = (&String, &TensorMeta)> {
        self.tensors.iter()
    }

    /// Every tensor name, in order.
    pub fn names(&self) -> impl Iterator<Item = &String> {
        self.tensors.keys()
    }
}

/// An opened -- or header-only -- checkpoint.
pub struct Checkpoint {
    root: Option<PathBuf>,
    root_name: String,
    shards: Vec<ShardProvenance>,
    files: Vec<Option<File>>,
    headers: Vec<ShardHeader>,
    catalog: Catalog,
    index: Option<Index>,
}

impl std::fmt::Debug for Checkpoint {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("Checkpoint")
            .field("root_name", &self.root_name)
            .field("shards", &self.shards)
            .field("tensors", &self.catalog.len())
            .field("backed_by_files", &self.root.is_some())
            .finish()
    }
}

fn io_error(path: &Path, error: &std::io::Error) -> CatalogError {
    CatalogError::Io {
        path: path.display().to_string(),
        detail: error.to_string(),
    }
}

/// Read a shard's 8-byte prefix and its declared header bytes, and nothing more.
fn read_header_bytes(file: &File, shard: &str) -> Result<Vec<u8>> {
    let mut prefix = [0u8; 8];
    file.read_exact_at(&mut prefix, 0)
        .map_err(|error| CatalogError::MalformedHeader {
            shard: shard.to_string(),
            detail: format!("cannot read the length prefix: {error}"),
        })?;
    let header_len = u64::from_le_bytes(prefix);
    if header_len > MAX_HEADER_BYTES {
        return Err(CatalogError::HeaderTooLarge {
            shard: shard.to_string(),
            header_len,
        });
    }
    let total = usize::try_from(header_len + 8).map_err(|_| CatalogError::MalformedHeader {
        shard: shard.to_string(),
        detail: "header does not fit in memory on this target".to_string(),
    })?;
    let mut bytes = vec![0u8; total];
    bytes[..8].copy_from_slice(&prefix);
    file.read_exact_at(&mut bytes[8..], 8)
        .map_err(|error| CatalogError::MalformedHeader {
            shard: shard.to_string(),
            detail: format!("cannot read {header_len} header bytes: {error}"),
        })?;
    Ok(bytes)
}

fn build_catalog(
    shard_names: &[String],
    headers: &[ShardHeader],
    index: Option<&Index>,
) -> Result<Catalog> {
    let mut tensors: BTreeMap<String, TensorMeta> = BTreeMap::new();
    let mut owner: BTreeMap<String, String> = BTreeMap::new();

    // Every weight_map entry must resolve to a tensor its named shard holds.
    if let Some(index) = index {
        for (name, shard_name) in &index.weight_map {
            let position = shard_names
                .iter()
                .position(|candidate| candidate == shard_name)
                .ok_or(CatalogError::MissingShard {
                    shard: shard_name.clone(),
                })?;
            if !headers[position].tensors.contains_key(name) {
                return Err(CatalogError::MissingTensorInShard {
                    name: name.clone(),
                    shard: shard_name.clone(),
                });
            }
        }
    }

    for (position, header) in headers.iter().enumerate() {
        let shard_name = &shard_names[position];
        let shard =
            ShardId(
                u16::try_from(position).map_err(|_| CatalogError::AmbiguousLayout {
                    detail: format!(
                        "{} shards exceed the addressable shard count",
                        headers.len()
                    ),
                })?,
            );
        for (name, tensor) in &header.tensors {
            if let Some(index) = index {
                match index.weight_map.get(name) {
                    None => {
                        return Err(CatalogError::UnindexedTensor {
                            name: name.clone(),
                            shard: shard_name.clone(),
                        })
                    }
                    Some(mapped) if mapped != shard_name => {
                        // The index places this name elsewhere; the loop above
                        // already proved the other shard holds a copy, so this
                        // is the same name in two shards.
                        return Err(CatalogError::DuplicateTensor {
                            name: name.clone(),
                            first: mapped.clone(),
                            second: shard_name.clone(),
                        });
                    }
                    Some(_) => {}
                }
            }
            if let Some(previous) = owner.get(name) {
                return Err(CatalogError::DuplicateTensor {
                    name: name.clone(),
                    first: previous.clone(),
                    second: shard_name.clone(),
                });
            }
            owner.insert(name.clone(), shard_name.clone());
            let base = 8 + header.header_len;
            let data_begin =
                base.checked_add(tensor.begin)
                    .ok_or_else(|| CatalogError::Overflow {
                        shard: shard_name.clone(),
                        name: name.clone(),
                        detail: "absolute begin offset overflows u64".to_string(),
                    })?;
            let data_end = base
                .checked_add(tensor.end)
                .ok_or_else(|| CatalogError::Overflow {
                    shard: shard_name.clone(),
                    name: name.clone(),
                    detail: "absolute end offset overflows u64".to_string(),
                })?;
            tensors.insert(
                name.clone(),
                TensorMeta {
                    name: name.clone(),
                    dtype: tensor.dtype,
                    shape: tensor.shape.clone(),
                    elements: tensor.elements,
                    byte_len: tensor.byte_len,
                    shard,
                    data_begin,
                    data_end,
                },
            );
        }
    }

    Ok(Catalog { tensors })
}

impl Checkpoint {
    /// Open a checkpoint rooted at a directory.
    pub fn open(root: &Path, mode: OpenMode) -> Result<Self> {
        let metadata = std::fs::metadata(root).map_err(|error| io_error(root, &error))?;
        if !metadata.is_dir() {
            return Err(CatalogError::Io {
                path: root.display().to_string(),
                detail: "not a directory".to_string(),
            });
        }
        let canonical_root = root
            .canonicalize()
            .map_err(|error| io_error(root, &error))?;

        let index_path = canonical_root.join(INDEX_FILE_NAME);
        let index_exists = index_path.is_file();
        let index = match (mode, index_exists) {
            (OpenMode::RequireSingleShard, true) => {
                return Err(CatalogError::AmbiguousLayout {
                    detail: "an index is present but a single shard was required".to_string(),
                })
            }
            (OpenMode::RequireIndex, false) => {
                return Err(CatalogError::AmbiguousLayout {
                    detail: format!("{INDEX_FILE_NAME} is absent"),
                })
            }
            (_, true) => {
                let text = std::fs::read_to_string(&index_path)
                    .map_err(|error| io_error(&index_path, &error))?;
                Some(parse_index(&text)?)
            }
            (_, false) => None,
        };

        let shard_names: Vec<String> = match &index {
            Some(index) => index.shards(),
            None => {
                let mut found = Vec::new();
                let entries = std::fs::read_dir(&canonical_root)
                    .map_err(|error| io_error(&canonical_root, &error))?;
                for entry in entries {
                    let entry = entry.map_err(|error| io_error(&canonical_root, &error))?;
                    let name = entry.file_name().to_string_lossy().into_owned();
                    if name.ends_with(".safetensors") && validate_plain_name(&name) {
                        found.push(name);
                    }
                }
                found.sort();
                if found.len() != 1 {
                    return Err(CatalogError::AmbiguousLayout {
                        detail: format!(
                            "no {INDEX_FILE_NAME} and {} candidate shards, not exactly one",
                            found.len()
                        ),
                    });
                }
                found
            }
        };

        let mut shards = Vec::with_capacity(shard_names.len());
        let mut files = Vec::with_capacity(shard_names.len());
        let mut headers = Vec::with_capacity(shard_names.len());
        for name in &shard_names {
            crate::index::validate_shard_path(name)?;
            let path = canonical_root.join(name);
            let file = match File::open(&path) {
                Ok(file) => file,
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                    return Err(CatalogError::MissingShard {
                        shard: name.clone(),
                    })
                }
                Err(error) => return Err(io_error(&path, &error)),
            };
            let resolved = path
                .canonicalize()
                .map_err(|error| io_error(&path, &error))?;
            if !resolved.starts_with(&canonical_root) {
                return Err(CatalogError::PathEscape {
                    shard: name.clone(),
                    resolved: resolved.display().to_string(),
                });
            }
            let file_len = file
                .metadata()
                .map_err(|error| io_error(&path, &error))?
                .len();
            let bytes = read_header_bytes(&file, name)?;
            let header = parse_header_named(name, &bytes, file_len)?;
            shards.push(ShardProvenance {
                file_name: name.clone(),
                file_len,
                header_len: header.header_len,
                sha256: None,
            });
            headers.push(header);
            files.push(Some(file));
        }

        let catalog = build_catalog(&shard_names, &headers, index.as_ref())?;
        let root_name = canonical_root
            .file_name()
            .map(|name| name.to_string_lossy().into_owned())
            .unwrap_or_else(|| canonical_root.display().to_string());

        Ok(Self {
            root: Some(canonical_root),
            root_name,
            shards,
            files,
            headers,
            catalog,
            index,
        })
    }

    /// Build a catalog from header bytes alone, with no file system at all.
    ///
    /// This is what a compatibility census over a checkpoint that lives on
    /// another host uses: the headers travel, the payload does not. Reads are
    /// refused with [`CatalogError::NoBackingFile`].
    pub fn from_headers(
        root_name: &str,
        shards: Vec<(String, u64, Vec<u8>)>,
        index_json: Option<&str>,
    ) -> Result<Self> {
        let index = match index_json {
            Some(text) => Some(parse_index(text)?),
            None => None,
        };
        let mut ordered = shards;
        ordered.sort_by(|left, right| left.0.cmp(&right.0));
        for window in ordered.windows(2) {
            if window[0].0 == window[1].0 {
                return Err(CatalogError::AmbiguousLayout {
                    detail: format!("shard {} supplied twice", window[0].0),
                });
            }
        }
        if index.is_none() && ordered.len() != 1 {
            return Err(CatalogError::AmbiguousLayout {
                detail: format!("no index and {} shards, not exactly one", ordered.len()),
            });
        }
        if let Some(index) = &index {
            let declared: BTreeSet<&String> = index.weight_map.values().collect();
            for name in &declared {
                if !ordered.iter().any(|(candidate, _, _)| &candidate == name) {
                    return Err(CatalogError::MissingShard {
                        shard: (*name).clone(),
                    });
                }
            }
        }

        let mut names = Vec::with_capacity(ordered.len());
        let mut provenance = Vec::with_capacity(ordered.len());
        let mut headers = Vec::with_capacity(ordered.len());
        for (name, file_len, bytes) in &ordered {
            crate::index::validate_shard_path(name)?;
            let header = parse_header_named(name, bytes, *file_len)?;
            provenance.push(ShardProvenance {
                file_name: name.clone(),
                file_len: *file_len,
                header_len: header.header_len,
                sha256: None,
            });
            headers.push(header);
            names.push(name.clone());
        }
        let catalog = build_catalog(&names, &headers, index.as_ref())?;
        let files = names.iter().map(|_| None).collect();
        Ok(Self {
            root: None,
            root_name: root_name.to_string(),
            shards: provenance,
            files,
            headers,
            catalog,
            index,
        })
    }

    pub fn root(&self) -> Option<&Path> {
        self.root.as_deref()
    }

    pub fn root_name(&self) -> &str {
        &self.root_name
    }

    pub fn catalog(&self) -> &Catalog {
        &self.catalog
    }

    pub fn index(&self) -> Option<&Index> {
        self.index.as_ref()
    }

    pub fn shards(&self) -> &[ShardProvenance] {
        &self.shards
    }

    pub fn headers(&self) -> &[ShardHeader] {
        &self.headers
    }

    pub fn shard_name(&self, shard: ShardId) -> Result<&str> {
        self.shards
            .get(usize::from(shard.0))
            .map(|provenance| provenance.file_name.as_str())
            .ok_or_else(|| CatalogError::AmbiguousLayout {
                detail: format!("shard id {} is out of range", shard.0),
            })
    }

    /// `true` when reads are possible.
    pub fn is_backed_by_files(&self) -> bool {
        self.root.is_some()
    }

    /// The sum of every tensor's byte length.
    pub fn payload_bytes(&self) -> u64 {
        self.catalog
            .tensors
            .values()
            .map(|tensor| tensor.byte_len)
            .sum()
    }

    /// Hash every shard file. Explicit because a real shard is tens of GB.
    pub fn hash_shards(&mut self) -> Result<()> {
        for (position, provenance) in self.shards.iter_mut().enumerate() {
            let file =
                self.files[position]
                    .as_ref()
                    .ok_or_else(|| CatalogError::NoBackingFile {
                        name: provenance.file_name.clone(),
                    })?;
            let mut hasher = Sha256::new();
            let mut reader = file.try_clone().map_err(|error| CatalogError::Io {
                path: provenance.file_name.clone(),
                detail: error.to_string(),
            })?;
            let mut buffer = vec![0u8; 1 << 20];
            loop {
                let read = reader.read(&mut buffer).map_err(|error| CatalogError::Io {
                    path: provenance.file_name.clone(),
                    detail: error.to_string(),
                })?;
                if read == 0 {
                    break;
                }
                hasher.update(&buffer[..read]);
            }
            provenance.sha256 = Some(hasher.finalize().into());
        }
        Ok(())
    }

    /// The catalog's identity: sha256 over one canonical line per tensor,
    /// `name\tdtype\tshape\tshard_file\tdata_begin\tdata_end\n`, in name
    /// order, with the shape written as comma-separated decimals.
    pub fn catalog_digest(&self) -> Result<[u8; 32]> {
        let mut hasher = Sha256::new();
        for (name, tensor) in self.catalog.iter() {
            let shape = tensor
                .shape
                .iter()
                .map(u64::to_string)
                .collect::<Vec<_>>()
                .join(",");
            let shard = self.shard_name(tensor.shard)?;
            hasher.update(
                format!(
                    "{name}\t{}\t{shape}\t{shard}\t{}\t{}\n",
                    tensor.dtype.as_str(),
                    tensor.data_begin,
                    tensor.data_end
                )
                .as_bytes(),
            );
        }
        Ok(hasher.finalize().into())
    }

    /// The catalog digest as lower-case hexadecimal.
    pub fn catalog_digest_hex(&self) -> Result<String> {
        Ok(hex(&self.catalog_digest()?))
    }

    /// Read a whole tensor. `out` must be exactly `tensor.byte_len` long.
    pub fn read_tensor_bytes(&self, tensor: &TensorMeta, out: &mut [u8]) -> Result<()> {
        self.read_range(tensor, 0, tensor.byte_len, out)
    }

    /// Read `len` bytes starting `offset_within` bytes into the tensor.
    pub fn read_range(
        &self,
        tensor: &TensorMeta,
        offset_within: u64,
        len: u64,
        out: &mut [u8],
    ) -> Result<()> {
        let end = offset_within
            .checked_add(len)
            .ok_or_else(|| CatalogError::RangeOutOfBounds {
                name: tensor.name.clone(),
                offset_within,
                len,
                byte_len: tensor.byte_len,
            })?;
        if end > tensor.byte_len {
            return Err(CatalogError::RangeOutOfBounds {
                name: tensor.name.clone(),
                offset_within,
                len,
                byte_len: tensor.byte_len,
            });
        }
        let wanted = usize::try_from(len).map_err(|_| CatalogError::RangeOutOfBounds {
            name: tensor.name.clone(),
            offset_within,
            len,
            byte_len: tensor.byte_len,
        })?;
        if out.len() != wanted {
            return Err(CatalogError::DestinationLengthMismatch {
                name: tensor.name.clone(),
                expected: len,
                actual: out.len() as u64,
            });
        }
        let file = self
            .files
            .get(usize::from(tensor.shard.0))
            .and_then(|slot| slot.as_ref())
            .ok_or_else(|| CatalogError::NoBackingFile {
                name: tensor.name.clone(),
            })?;
        let offset = tensor
            .data_begin
            .checked_add(offset_within)
            .ok_or_else(|| CatalogError::Overflow {
                shard: self
                    .shard_name(tensor.shard)
                    .unwrap_or("<shard>")
                    .to_string(),
                name: tensor.name.clone(),
                detail: "absolute read offset overflows u64".to_string(),
            })?;
        if wanted == 0 {
            return Ok(());
        }
        file.read_exact_at(out, offset)
            .map_err(|error| CatalogError::Io {
                path: self
                    .shard_name(tensor.shard)
                    .unwrap_or("<shard>")
                    .to_string(),
                detail: error.to_string(),
            })
    }
}

fn validate_plain_name(name: &str) -> bool {
    crate::index::validate_shard_path(name).is_ok()
}

/// Lower-case hexadecimal, for digests in evidence.
pub fn hex(bytes: &[u8]) -> String {
    let mut out = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        out.push_str(&format!("{byte:02x}"));
    }
    out
}
