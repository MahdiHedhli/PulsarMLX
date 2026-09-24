//! F020 Slice 2C -- selection of ONE expert plane of a synthetic stacked
//! affine tensor, through the admitted Slice 1 catalog, the Slice 1 module
//! resolution and the Slice 1 checked selection (contract
//! `specs/020-mlx-safetensors-affine/contracts/native-composition-v1.json`,
//! plan `slice2c-plan.md` section 2.2).
//!
//! Everything here is host-side and MLX-free, like the rest of this library:
//! every composition refusal (C-R-*) is decided in this module, which cannot
//! issue an MLX-C call, and the `qualify` child calls the existing Slice 2B
//! bridge only after [`compose`] / [`select_plane`] returned a plane and every
//! selection check passed.
//!
//! * [`Backing`] -- one immutable host buffer per shard (the whole file, or a
//!   manifest-declared prefix window), read through the catalog crate's
//!   admission boundary and bound to the `Checkpoint::hash_shards`
//!   provenance.
//! * [`SelectedPlane`] -- one index, one source/module binding, three borrowed
//!   ranges. Its fields are private, it is neither `Clone` nor `Default`, it
//!   has no `&mut self` method, and it is constructed only inside
//!   [`select_plane`] (which [`compose`] calls) from ONE resolved triple and
//!   ONE index path (I-PLANE-SINGLE-INDEX).
//! * [`select_plane`] (E-SELECT) never takes the caller's triple as the
//!   authority: it resolves the module through `classify_module` and requires
//!   the caller's descriptors and recipe to match (C-R-MODULE-BINDING,
//!   C-R-RECIPE-BINDING), then slices with the RESOLVED triple through the
//!   Slice 1 `AffineTriple::expert_slice`, which is reused, not re-implemented.
//! * [`resolve_range`] (E-RANGE) -- checked `u64` arithmetic and `usize`
//!   conversion (C-R-OVERFLOW), then the backing bound (C-R-BACKING), giving a
//!   borrowed slice.
//! * [`stage`] -- exactly the plane's bytes copied into Slice 2B
//!   [`HostTensor`]s; the packed U32 weight is never unpacked or widened.
//!
//! Nothing here derives an expected range or byte: the qualification compares
//! what this module produces with the manifest's independent oracle.

use std::collections::BTreeMap;
use std::os::unix::fs::FileExt;

use mlx_affine::error::AffineError;
use mlx_affine::module::{classify_module, triple_scale_dtype, AffineTriple, ModuleKind};
use mlx_affine::spec::QuantizationConfig;
use safetensors_catalog::{CatalogError, Checkpoint, OpenMode, RootDirectory};
use serde_json::{json, Value};

use crate::dtype::Dtype;
use crate::fixture::{sha256_hex, HostTensor};

// ------------------------------------------------------------- refusals --

/// Contract `composition_refusals.order`, as a type.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CompositionRefusalId {
    Catalog,
    Resolve,
    SourceBinding,
    ModuleBinding,
    RecipeBinding,
    IndexRank,
    IndexRange,
    Overflow,
    Backing,
}

impl CompositionRefusalId {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Catalog => "C-R-CATALOG",
            Self::Resolve => "C-R-RESOLVE",
            Self::SourceBinding => "C-R-SOURCE-BINDING",
            Self::ModuleBinding => "C-R-MODULE-BINDING",
            Self::RecipeBinding => "C-R-RECIPE-BINDING",
            Self::IndexRank => "C-R-INDEX-RANK",
            Self::IndexRange => "C-R-INDEX-RANGE",
            Self::Overflow => "C-R-OVERFLOW",
            Self::Backing => "C-R-BACKING",
        }
    }
}

/// A typed composition refusal: the first failing check's id, with the Slice 1
/// variant (and `implied_bits` for `InconsistentOverride`) where Slice 1
/// decided it.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CompositionRefusal {
    pub id: CompositionRefusalId,
    pub detail: String,
    pub slice1_variant: Option<String>,
    pub implied_bits: Option<u32>,
}

impl CompositionRefusal {
    fn new(id: CompositionRefusalId, detail: impl Into<String>) -> Self {
        Self {
            id,
            detail: detail.into(),
            slice1_variant: None,
            implied_bits: None,
        }
    }

    fn slice1(id: CompositionRefusalId, error: &AffineError) -> Self {
        let (variant, implied_bits) = affine_variant(error);
        Self {
            id,
            detail: error.to_string(),
            slice1_variant: Some(variant),
            implied_bits,
        }
    }

    fn catalog(error: &CatalogError) -> Self {
        let debug = format!("{error:?}");
        let variant = debug
            .split(|c: char| !c.is_ascii_alphanumeric())
            .next()
            .unwrap_or_default()
            .to_string();
        Self {
            id: CompositionRefusalId::Catalog,
            detail: error.to_string(),
            slice1_variant: Some(variant),
            implied_bits: None,
        }
    }

    pub fn to_json(&self) -> Value {
        json!({
            "id": self.id.as_str(),
            "detail": self.detail,
            "slice1_variant": self.slice1_variant,
            "implied_bits": self.implied_bits,
        })
    }
}

impl std::fmt::Display for CompositionRefusal {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}: {}", self.id.as_str(), self.detail)
    }
}

/// The Slice 1 variant name and, for `InconsistentOverride`, `implied_bits`.
fn affine_variant(error: &AffineError) -> (String, Option<u32>) {
    let name = match error {
        AffineError::UnsupportedQuantization { .. } => "UnsupportedQuantization",
        AffineError::MissingDefaultSpec { .. } => "MissingDefaultSpec",
        AffineError::InconsistentConfig => "InconsistentConfig",
        AffineError::UnresolvedOverride { .. } => "UnresolvedOverride",
        AffineError::UnsupportedOverrideValue { .. } => "UnsupportedOverrideValue",
        AffineError::InvalidConfigJson { .. } => "InvalidConfigJson",
        AffineError::DuplicateConfigKey { .. } => "DuplicateConfigKey",
        AffineError::NoQuantizationConfig => "NoQuantizationConfig",
        AffineError::IncompleteTriple { .. } => "IncompleteTriple",
        AffineError::ScalesBiasesMismatch { .. } => "ScalesBiasesMismatch",
        AffineError::OverrideWithoutScales { .. } => "OverrideWithoutScales",
        AffineError::AmbiguousQuantization { .. } => "AmbiguousQuantization",
        AffineError::InconsistentOverride { .. } => "InconsistentOverride",
        AffineError::Overflow { .. } => "Overflow",
        AffineError::UnknownModule { .. } => "UnknownModule",
        AffineError::IndexOutOfBounds { .. } => "IndexOutOfBounds",
        AffineError::InvalidTensorMeta { .. } => "InvalidTensorMeta",
        AffineError::GeometryMismatch { .. } => "GeometryMismatch",
        AffineError::NonFiniteValue { .. } => "NonFiniteValue",
        _ => "UnlistedAffineError",
    };
    let implied = match error {
        AffineError::InconsistentOverride { implied_bits, .. } => *implied_bits,
        _ => None,
    };
    (name.to_string(), implied)
}

// --------------------------------------------------------------- backing --

/// One shard's immutable host buffer.
struct ShardBuffer {
    name: String,
    file_len: u64,
    /// Full-file sha256 from `Checkpoint::hash_shards` provenance (lower-case hex).
    file_sha256: String,
    bytes: Box<[u8]>,
}

/// One immutable host buffer per shard of one checkpoint, bound to that
/// checkpoint's hashed provenance. Never mutated after [`Backing::load`].
pub struct Backing {
    root_name: String,
    shards: Vec<ShardBuffer>,
    source_identity: String,
}

/// The payload-inclusive source identity: the sha256 of the `shasum -a 256`
/// listing of the shard files in C-locale order (contract plane_identity).
fn source_identity_of(named: &[(String, String)]) -> String {
    let mut rows: Vec<&(String, String)> = named.iter().collect();
    rows.sort_by(|a, b| a.0.as_bytes().cmp(b.0.as_bytes()));
    let mut listing = String::new();
    for (name, sha) in rows {
        listing.push_str(sha);
        listing.push_str("  ");
        listing.push_str(name);
        listing.push('\n');
    }
    sha256_hex(listing.as_bytes())
}

/// `(shard file name, full-file sha256)` of a hashed checkpoint, in shard order.
fn provenance(checkpoint: &Checkpoint) -> Result<Vec<(String, String)>, CompositionRefusal> {
    checkpoint
        .shards()
        .iter()
        .map(|s| match s.sha256 {
            Some(d) => Ok((s.file_name.clone(), safetensors_catalog::hex(&d))),
            None => Err(CompositionRefusal::new(
                CompositionRefusalId::SourceBinding,
                format!("shard {} carries no hash_shards provenance", s.file_name),
            )),
        })
        .collect()
}

impl Backing {
    /// Read every shard of a hashed, file-backed checkpoint through the
    /// catalog crate's admission boundary (`RootDirectory::open_file`: one
    /// descriptor per single-component name, `O_NOFOLLOW`, bound by device
    /// and inode), require the admitted length and the full-file sha256 to
    /// equal the checkpoint's provenance, then keep either the whole file or
    /// the manifest-declared prefix `windows[name]`.
    pub fn load(
        checkpoint: &Checkpoint,
        windows: &BTreeMap<String, u64>,
    ) -> Result<Backing, CompositionRefusal> {
        let root = checkpoint.root().ok_or_else(|| {
            CompositionRefusal::new(
                CompositionRefusalId::Backing,
                "the checkpoint is header-only and has no backing",
            )
        })?;
        let named = provenance(checkpoint)?;
        for window in windows.keys() {
            if !named.iter().any(|(n, _)| n == window) {
                return Err(CompositionRefusal::new(
                    CompositionRefusalId::Backing,
                    format!("a window names shard {window}, which the checkpoint does not have"),
                ));
            }
        }
        let directory = RootDirectory::open(root).map_err(|e| CompositionRefusal::catalog(&e))?;
        let mut shards = Vec::with_capacity(named.len());
        for (shard, (name, sha)) in checkpoint.shards().iter().zip(&named) {
            let admitted = directory
                .open_file(name)
                .map_err(|e| CompositionRefusal::catalog(&e))?;
            if admitted.len != shard.file_len {
                return Err(CompositionRefusal::new(
                    CompositionRefusalId::SourceBinding,
                    format!(
                        "shard {name} is {} bytes, the checkpoint admitted {}",
                        admitted.len, shard.file_len
                    ),
                ));
            }
            let len = usize::try_from(admitted.len).map_err(|_| {
                CompositionRefusal::new(
                    CompositionRefusalId::Backing,
                    format!("shard {name} does not fit in memory on this target"),
                )
            })?;
            let mut bytes = vec![0u8; len];
            admitted.file.read_exact_at(&mut bytes, 0).map_err(|e| {
                CompositionRefusal::new(CompositionRefusalId::Backing, format!("read {name}: {e}"))
            })?;
            if sha256_hex(&bytes) != *sha {
                return Err(CompositionRefusal::new(
                    CompositionRefusalId::SourceBinding,
                    format!("shard {name} bytes differ from its hash_shards provenance"),
                ));
            }
            if let Some(&window) = windows.get(name) {
                let keep = usize::try_from(window)
                    .ok()
                    .filter(|&w| w <= bytes.len())
                    .ok_or_else(|| {
                        CompositionRefusal::new(
                            CompositionRefusalId::Backing,
                            format!("window {window} exceeds shard {name} ({len} bytes)"),
                        )
                    })?;
                bytes.truncate(keep);
            }
            shards.push(ShardBuffer {
                name: name.clone(),
                file_len: shard.file_len,
                file_sha256: sha.clone(),
                bytes: bytes.into_boxed_slice(),
            });
        }
        Ok(Backing {
            root_name: checkpoint.root_name().to_string(),
            source_identity: source_identity_of(&named),
            shards,
        })
    }

    /// Open a checkpoint directory (C-R-CATALOG on failure), hash its shards
    /// and [`Backing::load`] it: the backing of a source that is not the
    /// selection's own checkpoint (E-SELECT with another source's bytes), or
    /// a windowed backing.
    pub fn open(
        dir: &std::path::Path,
        windows: &BTreeMap<String, u64>,
    ) -> Result<Backing, CompositionRefusal> {
        let mut checkpoint =
            Checkpoint::open(dir, OpenMode::Auto).map_err(|e| CompositionRefusal::catalog(&e))?;
        checkpoint
            .hash_shards()
            .map_err(|e| CompositionRefusal::catalog(&e))?;
        Backing::load(&checkpoint, windows)
    }

    pub fn source_identity(&self) -> &str {
        &self.source_identity
    }

    /// The directory name of the checkpoint the backing was loaded from.
    pub fn root_name(&self) -> &str {
        &self.root_name
    }

    /// `(shard name, buffer length, sha256 of the buffer as held now, full-file
    /// sha256 recorded at load, full-file length)` for every shard, for the
    /// phase-labelled source records.
    pub fn buffer_records(&self) -> Vec<Value> {
        self.shards
            .iter()
            .map(|s| {
                json!({
                    "shard": s.name,
                    "len": s.bytes.len(),
                    "sha256": sha256_hex(&s.bytes),
                    "file_len": s.file_len,
                    "file_sha256_at_load": s.file_sha256,
                    "window": s.bytes.len() as u64 != s.file_len,
                })
            })
            .collect()
    }
}

// ---------------------------------------------------------------- ranges --

fn checked_bounds(begin: u64, len: u64) -> Result<(usize, usize), CompositionRefusal> {
    let overflow = |what: &str| {
        CompositionRefusal::new(
            CompositionRefusalId::Overflow,
            format!("range begin {begin} len {len}: {what}"),
        )
    };
    let end = begin
        .checked_add(len)
        .ok_or_else(|| overflow("begin + len overflows u64"))?;
    let b = usize::try_from(begin).map_err(|_| overflow("begin does not fit usize"))?;
    let e = usize::try_from(end).map_err(|_| overflow("end does not fit usize"))?;
    Ok((b, e))
}

fn borrow<'b>(
    backing: &'b Backing,
    shard: &str,
    (begin, end): (usize, usize),
) -> Result<&'b [u8], CompositionRefusal> {
    let buffer = backing
        .shards
        .iter()
        .find(|s| s.name == shard)
        .ok_or_else(|| {
            CompositionRefusal::new(
                CompositionRefusalId::Backing,
                format!("no backing for shard {shard}"),
            )
        })?;
    if end > buffer.bytes.len() {
        return Err(CompositionRefusal::new(
            CompositionRefusalId::Backing,
            format!(
                "range [{begin}, {end}) of {shard} exceeds its backing of {} bytes",
                buffer.bytes.len()
            ),
        ));
    }
    Ok(&buffer.bytes[begin..end])
}

/// E-RANGE: an absolute `(shard, begin, len)` range as a borrowed slice of the
/// backing. Checked `u64` addition and `usize` conversion first (C-R-OVERFLOW),
/// then the backing bound (C-R-BACKING). Nothing is wrapped or truncated.
pub fn resolve_range<'b>(
    backing: &'b Backing,
    shard: &str,
    begin: u64,
    len: u64,
) -> Result<&'b [u8], CompositionRefusal> {
    let bounds = checked_bounds(begin, len)?;
    borrow(backing, shard, bounds)
}

// ----------------------------------------------------------------- plane --

/// Contract `plane_identity.fields`, except `ranges`, in contract order.
pub const IDENTITY_FIELDS: [&str; 12] = [
    "source_identity",
    "checkpoint",
    "module",
    "index_path",
    "bits",
    "group_size",
    "resolved_from",
    "metadata_dtype",
    "logical_shape",
    "packed_shape",
    "metadata_shape",
    "transpose",
];

/// The three components, in contract order.
pub const COMPONENTS: [&str; 3] = ["weight", "scales", "biases"];

/// A plane's identity (contract plane_identity), as data.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PlaneIdentity {
    pub source_identity: String,
    pub checkpoint: String,
    pub module: String,
    pub index_path: Vec<u64>,
    pub bits: u32,
    pub group_size: u32,
    pub resolved_from: String,
    pub metadata_dtype: String,
    pub logical_shape: [u64; 2],
    pub packed_shape: [u64; 2],
    pub metadata_shape: [u64; 2],
    pub transpose: bool,
}

impl PlaneIdentity {
    pub fn to_json(&self) -> Value {
        json!({
            "source_identity": self.source_identity,
            "checkpoint": self.checkpoint,
            "module": self.module,
            "index_path": self.index_path,
            "bits": self.bits,
            "group_size": self.group_size,
            "resolved_from": self.resolved_from,
            "metadata_dtype": self.metadata_dtype,
            "logical_shape": self.logical_shape,
            "packed_shape": self.packed_shape,
            "metadata_shape": self.metadata_shape,
            "transpose": self.transpose,
        })
    }
}

/// One absolute range of one component.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PlaneRange {
    pub shard: String,
    pub begin: u64,
    pub len: u64,
}

impl PlaneRange {
    pub fn to_json(&self) -> Value {
        json!({"shard": self.shard, "begin": self.begin, "len": self.len})
    }
}

/// ONE selected expert plane: one index path, one source/module binding, and
/// three byte ranges borrowed from the immutable backing. There is no public
/// field, no `Clone`, no `Default`, no setter, no builder, no component-wise
/// constructor and no `&mut self` method; [`select_plane`] is the only place
/// one is made (I-PLANE-SINGLE-INDEX, I-PLANE-BORROW).
pub struct SelectedPlane<'b> {
    identity: PlaneIdentity,
    ranges: [PlaneRange; 3],
    weight: &'b [u8],
    scales: &'b [u8],
    biases: &'b [u8],
}

/// The serializable identity, ranges and byte hashes of a plane, which the
/// child reports and the parent re-decides against the oracle.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SelectionRecord {
    pub identity: PlaneIdentity,
    /// weight, scales, biases.
    pub ranges: [PlaneRange; 3],
    /// sha256 of the borrowed bytes of weight, scales, biases.
    pub sha256: [String; 3],
}

impl SelectionRecord {
    pub fn to_json(&self) -> Value {
        let mut ranges = serde_json::Map::new();
        let mut sha = serde_json::Map::new();
        for (i, c) in COMPONENTS.iter().enumerate() {
            ranges.insert(c.to_string(), self.ranges[i].to_json());
            sha.insert(c.to_string(), Value::String(self.sha256[i].clone()));
        }
        json!({"identity": self.identity.to_json(), "ranges": ranges, "sha256": sha})
    }
}

impl SelectedPlane<'_> {
    pub fn identity(&self) -> &PlaneIdentity {
        &self.identity
    }

    pub fn record(&self) -> SelectionRecord {
        SelectionRecord {
            identity: self.identity.clone(),
            ranges: self.ranges.clone(),
            sha256: [
                sha256_hex(self.weight),
                sha256_hex(self.scales),
                sha256_hex(self.biases),
            ],
        }
    }

    /// The borrowed bytes of weight, scales, biases (read-only).
    pub fn component_bytes(&self) -> [&[u8]; 3] {
        [self.weight, self.scales, self.biases]
    }
}

fn resolve(
    checkpoint: &Checkpoint,
    config: &QuantizationConfig,
    module: &str,
) -> Result<AffineTriple, CompositionRefusal> {
    match classify_module(checkpoint.catalog(), Some(config), module) {
        Ok(ModuleKind::Quantized(triple)) => Ok(*triple),
        Ok(ModuleKind::Unquantized(_)) => Err(CompositionRefusal {
            id: CompositionRefusalId::Resolve,
            detail: format!("module {module} resolves as unquantized"),
            slice1_variant: Some("Unquantized".into()),
            implied_bits: None,
        }),
        Err(e) => Err(CompositionRefusal::slice1(
            CompositionRefusalId::Resolve,
            &e,
        )),
    }
}

/// E-SELECT. The caller's `candidate` is never the authority: the module it
/// names is resolved through `classify_module` (C-R-RESOLVE), the backing
/// must be the checkpoint's own bytes (C-R-SOURCE-BINDING), the candidate's
/// three descriptors must equal the catalog's authoritative entries and the
/// resolved triple's (C-R-MODULE-BINDING), its recipe must equal the resolved
/// one (C-R-RECIPE-BINDING), and the index path must fit the RESOLVED triple
/// (C-R-INDEX-RANK, C-R-INDEX-RANGE) before the Slice 1
/// `RESOLVED.expert_slice(index_path)` and the checked borrow of each range
/// (C-R-OVERFLOW for all three, then C-R-BACKING for all three). The first
/// failing check's id is returned, in contract order.
pub fn select_plane<'b>(
    checkpoint: &Checkpoint,
    backing: &'b Backing,
    config: &QuantizationConfig,
    candidate: &AffineTriple,
    index_path: &[u64],
) -> Result<SelectedPlane<'b>, CompositionRefusal> {
    let module = candidate.module();
    // 1. C-R-RESOLVE: the resolution authority.
    let resolved = resolve(checkpoint, config, module)?;

    // 2. C-R-SOURCE-BINDING: the backing's (name, sha256) list equals the
    //    checkpoint's hash_shards provenance, shard for shard.
    let named = provenance(checkpoint)?;
    let backed: Vec<(String, String)> = backing
        .shards
        .iter()
        .map(|s| (s.name.clone(), s.file_sha256.clone()))
        .collect();
    if named != backed || source_identity_of(&named) != backing.source_identity {
        return Err(CompositionRefusal::new(
            CompositionRefusalId::SourceBinding,
            format!(
                "backing source identity {} differs from the checkpoint's {}",
                backing.source_identity,
                source_identity_of(&named)
            ),
        ));
    }

    // 3. C-R-MODULE-BINDING: name and full TensorMeta equality with both the
    //    catalog's authoritative entry and the resolved triple.
    let catalog = checkpoint.catalog();
    for (role, cand, res) in [
        ("weight", candidate.weight(), resolved.weight()),
        ("scales", candidate.scales(), resolved.scales()),
        ("biases", candidate.biases(), resolved.biases()),
    ] {
        let name = format!("{module}.{role}");
        let authoritative = catalog.get(&name);
        if authoritative != Some(cand) || cand != res {
            return Err(CompositionRefusal::new(
                CompositionRefusalId::ModuleBinding,
                format!(
                    "candidate {role} descriptor {} is not the catalog's {name}",
                    cand.name
                ),
            ));
        }
    }

    // 4. C-R-RECIPE-BINDING: bits, group size, mode and metadata dtype.
    let (cs, rs) = (candidate.spec(), resolved.spec());
    if cs != rs || triple_scale_dtype(candidate) != triple_scale_dtype(&resolved) {
        return Err(CompositionRefusal::new(
            CompositionRefusalId::RecipeBinding,
            format!(
                "candidate recipe {}-bit / group {} / {} differs from the resolved {}-bit / group {} / {}",
                cs.bits.get(),
                cs.group_size.get(),
                cs.mode.as_str(),
                rs.bits.get(),
                rs.group_size.get(),
                rs.mode.as_str()
            ),
        ));
    }

    // 5. C-R-INDEX-RANK, C-R-INDEX-RANGE against the RESOLVED triple. No
    //    index is wrapped, truncated or narrowed.
    let leading = resolved.leading();
    if index_path.len() != leading.len() {
        return Err(CompositionRefusal::new(
            CompositionRefusalId::IndexRank,
            format!(
                "{} indices supplied, the tensor has {} leading dimension(s)",
                index_path.len(),
                leading.len()
            ),
        ));
    }
    for (index, extent) in index_path.iter().zip(leading) {
        if index >= extent {
            return Err(CompositionRefusal::new(
                CompositionRefusalId::IndexRange,
                format!("index {index} is outside a leading dimension of extent {extent}"),
            ));
        }
    }

    // 6. The Slice 1 checked selection on the RESOLVED triple. A Slice 1
    //    refusal that arrives despite the pre-checks keeps its variant.
    let slice = resolved.expert_slice(index_path).map_err(|e| match e {
        AffineError::IndexOutOfBounds { .. } => {
            CompositionRefusal::slice1(CompositionRefusalId::IndexRange, &e)
        }
        AffineError::Overflow { .. } => {
            CompositionRefusal::slice1(CompositionRefusalId::Overflow, &e)
        }
        other => CompositionRefusal::slice1(CompositionRefusalId::Resolve, &other),
    })?;
    let mut ranges: Vec<PlaneRange> = Vec::with_capacity(3);
    for bs in [slice.weight, slice.scales, slice.biases] {
        let shard = checkpoint
            .shard_name(bs.shard)
            .map_err(|e| CompositionRefusal::new(CompositionRefusalId::Backing, e.to_string()))?;
        ranges.push(PlaneRange {
            shard: shard.to_string(),
            begin: bs.begin,
            len: bs.len,
        });
    }
    // C-R-OVERFLOW for all three components, then C-R-BACKING for all three.
    let mut bounds = Vec::with_capacity(3);
    for r in &ranges {
        bounds.push(checked_bounds(r.begin, r.len)?);
    }
    let weight = borrow(backing, &ranges[0].shard, bounds[0])?;
    let scales = borrow(backing, &ranges[1].shard, bounds[1])?;
    let biases = borrow(backing, &ranges[2].shard, bounds[2])?;

    let spec = resolved.spec();
    let packed_cols = resolved.weight().shape[resolved.weight().shape.len() - 1];
    let groups = resolved.groups_per_row();
    let n = resolved.out_features();
    let identity = PlaneIdentity {
        source_identity: backing.source_identity.clone(),
        checkpoint: checkpoint.root_name().to_string(),
        module: module.to_string(),
        index_path: index_path.to_vec(),
        bits: spec.bits.get(),
        group_size: spec.group_size.get(),
        resolved_from: if config.explicit(module).is_some() {
            "override".into()
        } else {
            "default".into()
        },
        metadata_dtype: resolved.scales().dtype.as_str().to_string(),
        logical_shape: [n, resolved.in_features()],
        packed_shape: [n, packed_cols],
        metadata_shape: [n, groups],
        transpose: true,
    };
    let [rw, rsc, rb]: [PlaneRange; 3] = match ranges.try_into() {
        Ok(a) => a,
        Err(_) => unreachable!("three components"),
    };
    Ok(SelectedPlane {
        identity,
        ranges: [rw, rsc, rb],
        weight,
        scales,
        biases,
    })
}

// ---------------------------------------------------------------- source --

/// P0-LOAD for one checkpoint directory: the admitted, hashed checkpoint, its
/// quantization configuration and its backing.
pub struct Source {
    checkpoint: Checkpoint,
    config: QuantizationConfig,
    backing: Backing,
}

impl Source {
    /// `Checkpoint::open` (C-R-CATALOG with the Slice 1 variant on failure),
    /// `Checkpoint::hash_shards` (C-R-CATALOG), `QuantizationConfig::from_config_json`
    /// (C-R-RESOLVE with the Slice 1 variant), then [`Backing::load`].
    pub fn open(
        dir: &std::path::Path,
        config_text: &str,
        windows: &BTreeMap<String, u64>,
    ) -> Result<Source, CompositionRefusal> {
        let mut checkpoint =
            Checkpoint::open(dir, OpenMode::Auto).map_err(|e| CompositionRefusal::catalog(&e))?;
        checkpoint
            .hash_shards()
            .map_err(|e| CompositionRefusal::catalog(&e))?;
        let config = QuantizationConfig::from_config_json(config_text)
            .map_err(|e| CompositionRefusal::slice1(CompositionRefusalId::Resolve, &e))?;
        let backing = Backing::load(&checkpoint, windows)?;
        Ok(Source {
            checkpoint,
            config,
            backing,
        })
    }

    pub fn checkpoint(&self) -> &Checkpoint {
        &self.checkpoint
    }

    pub fn config(&self) -> &QuantizationConfig {
        &self.config
    }

    pub fn backing(&self) -> &Backing {
        &self.backing
    }
}

/// E-COMPOSE from a loaded [`Source`]: resolve ONE module path through
/// `classify_module` (C-R-RESOLVE, recording the Slice 1 variant and
/// `implied_bits`), then [`select_plane`] with the resolved triple as the
/// candidate (so the recipe check is trivially satisfied, and still runs) and
/// ONE index path.
pub fn compose<'b>(
    source: &'b Source,
    module: &str,
    index_path: &[u64],
) -> Result<SelectedPlane<'b>, CompositionRefusal> {
    let resolved = resolve(&source.checkpoint, &source.config, module)?;
    select_plane(
        &source.checkpoint,
        &source.backing,
        &source.config,
        &resolved,
        index_path,
    )
}

// --------------------------------------------------------------- staging --

/// P5-STAGE: copy exactly the plane's borrowed bytes into Slice 2B
/// [`HostTensor`]s: `w` U32 `[N, K*bits/32]`, `scales` and `biases` in their
/// stored dtype `[N, K/group]`. The packed words are copied byte for byte and
/// never unpacked or widened (I-PLANE-NO-F32-WEIGHT); no unsafe
/// reinterpretation is used (I-PLANE-NO-REINTERPRET).
pub fn stage(plane: &SelectedPlane<'_>) -> Result<[HostTensor; 3], String> {
    let id = &plane.identity;
    let meta = Dtype::parse(&id.metadata_dtype)
        .ok_or_else(|| format!("metadata dtype {}", id.metadata_dtype))?;
    let dims = |s: [u64; 2]| -> Result<Vec<usize>, String> {
        s.iter()
            .map(|&d| usize::try_from(d).map_err(|_| format!("dimension {d}")))
            .collect()
    };
    let w_shape = dims(id.packed_shape)?;
    let m_shape = dims(id.metadata_shape)?;
    let tensor = |name: &str, dtype: Dtype, shape: Vec<usize>, bytes: &[u8]| {
        let want = shape.iter().product::<usize>() * dtype.size();
        if bytes.len() != want {
            return Err(format!(
                "{name}: {} borrowed bytes for {shape:?} {}",
                bytes.len(),
                dtype.name()
            ));
        }
        Ok(HostTensor {
            name: name.to_string(),
            dtype,
            shape,
            bytes: bytes.to_vec(),
        })
    };
    Ok([
        tensor("w", Dtype::U32, w_shape, plane.weight)?,
        tensor("scales", meta, m_shape.clone(), plane.scales)?,
        tensor("biases", meta, m_shape, plane.biases)?,
    ])
}

// ----------------------------------------------------- selection checks --

/// S-IDENTITY, S-RANGES and S-BYTES of a reported record against an oracle
/// (identity, ranges, sha256 objects from the manifest). Returns the exact
/// mismatch set as `S-IDENTITY:<field>`, `S-RANGES:<component>`,
/// `S-BYTES:<component>`, in that order. A missing field on either side is a
/// mismatch.
pub fn selection_mismatches(
    record: &Value,
    oracle_identity: &Value,
    oracle_ranges: &Value,
    oracle_sha256: &Value,
) -> Vec<String> {
    let mut out = Vec::new();
    for f in IDENTITY_FIELDS {
        let got = record["identity"].get(f);
        if got.is_none() || got != oracle_identity.get(f) {
            out.push(format!("S-IDENTITY:{f}"));
        }
    }
    for c in COMPONENTS {
        let got = record["ranges"].get(c);
        let want = oracle_ranges.get(c);
        let equal = match (got, want) {
            (Some(g), Some(w)) => {
                g["shard"] == w["shard"]
                    && g["begin"].as_u64().is_some()
                    && g["begin"] == w["begin"]
                    && g["len"].as_u64().is_some()
                    && g["len"] == w["len"]
            }
            _ => false,
        };
        if !equal {
            out.push(format!("S-RANGES:{c}"));
        }
    }
    for c in COMPONENTS {
        let got = record["sha256"].get(c).and_then(Value::as_str);
        if got.is_none() || got != oracle_sha256.get(c).and_then(Value::as_str) {
            out.push(format!("S-BYTES:{c}"));
        }
    }
    out
}
