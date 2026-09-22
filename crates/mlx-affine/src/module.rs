//! Associating a module path with its stored tensors, and resolving what
//! quantization it is in.
//!
//! Module paths are **opaque strings**. Nothing here matches on a model's
//! naming conventions, and there is no regular expression over a tensor name
//! anywhere in this library crate. The caller supplies the paths, or derives them from
//! the catalog with [`module_paths`], which does nothing but strip the three
//! suffixes the format itself defines.

use std::collections::BTreeSet;

use safetensors_catalog::{Catalog, Dtype, ShardId, TensorMeta};

use crate::decode::ScaleDtype;
use crate::error::{AffineError, Result};
use crate::spec::{Bits, GroupSize, Mode, QuantSpec, QuantizationConfig};

/// The three suffixes an affine triple is stored under.
pub const WEIGHT_SUFFIX: &str = ".weight";
pub const SCALES_SUFFIX: &str = ".scales";
pub const BIASES_SUFFIX: &str = ".biases";

/// One quantized module, fully located and fully resolved.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AffineTriple {
    module: String,
    weight: TensorMeta,
    scales: TensorMeta,
    biases: TensorMeta,
    scale_dtype: ScaleDtype,
    spec: QuantSpec,
    out_features: u64,
    in_features: u64,
    /// The dimensions in front of `[out_features, in_features]`, e.g. `[E]`
    /// for a stacked expert tensor.
    leading: Vec<u64>,
}

impl AffineTriple {
    /// The only way to make one.
    ///
    /// The fields are private because every arithmetic method on this type is
    /// checked *given that the fields agree with each other*. Public fields
    /// made that premise something a caller could break: an empty shape could
    /// panic on a `last()`, and an unsupported metadata dtype silently fell
    /// back to F32 and decoded the wrong number of bytes. Validation now
    /// happens once, here, and the invariants hold for the value's lifetime.
    pub fn new(
        module: &str,
        weight: TensorMeta,
        scales: TensorMeta,
        biases: TensorMeta,
        spec: QuantSpec,
    ) -> Result<Self> {
        build_triple(module, &weight, &scales, &biases, spec)
    }

    pub fn module(&self) -> &str {
        &self.module
    }

    pub fn weight(&self) -> &TensorMeta {
        &self.weight
    }

    pub fn scales(&self) -> &TensorMeta {
        &self.scales
    }

    pub fn biases(&self) -> &TensorMeta {
        &self.biases
    }

    pub fn spec(&self) -> QuantSpec {
        self.spec
    }

    pub fn out_features(&self) -> u64 {
        self.out_features
    }

    pub fn in_features(&self) -> u64 {
        self.in_features
    }

    pub fn leading(&self) -> &[u64] {
        &self.leading
    }
}

/// What a module turned out to be.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ModuleKind {
    Quantized(Box<AffineTriple>),
    Unquantized(TensorMeta),
}

impl ModuleKind {
    pub fn spec(&self) -> Option<QuantSpec> {
        match self {
            Self::Quantized(triple) => Some(triple.spec),
            Self::Unquantized(_) => None,
        }
    }

    pub fn is_quantized(&self) -> bool {
        matches!(self, Self::Quantized(_))
    }
}

/// One contiguous byte range inside one shard.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ByteSlice {
    pub shard: ShardId,
    pub begin: u64,
    pub len: u64,
}

/// The three ranges that make up one slice of a triple.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct TripleSlice {
    pub weight: ByteSlice,
    pub scales: ByteSlice,
    pub biases: ByteSlice,
}

/// Every module path the catalog implies, by stripping the three suffixes.
pub fn module_paths(catalog: &Catalog) -> BTreeSet<String> {
    let mut paths = BTreeSet::new();
    for name in catalog.names() {
        for suffix in [WEIGHT_SUFFIX, SCALES_SUFFIX, BIASES_SUFFIX] {
            if let Some(stem) = name.strip_suffix(suffix) {
                if !stem.is_empty() {
                    paths.insert(stem.to_string());
                }
            }
        }
    }
    paths
}

fn mul(module: &str, left: u64, right: u64) -> Result<u64> {
    left.checked_mul(right)
        .ok_or_else(|| AffineError::Overflow {
            module: module.to_string(),
            detail: format!("{left} * {right} overflows u64"),
        })
}

fn scale_dtype_of(module: &str, tensor: &TensorMeta) -> Result<ScaleDtype> {
    ScaleDtype::from_catalog(tensor.dtype).ok_or_else(|| AffineError::ScalesBiasesMismatch {
        module: module.to_string(),
        detail: format!("dtype {} is not one of F16, BF16, F32", tensor.dtype),
    })
}

/// The dtype the scales and biases of a triple are stored in.
///
/// No fallback: the dtype was admitted when the triple was built, so this is
/// a lookup of a decided fact rather than a guess with a default.
pub fn triple_scale_dtype(triple: &AffineTriple) -> ScaleDtype {
    triple.scale_dtype
}

/// Classify one module path against a catalog and a configuration.
///
/// `config` is `None` when the checkpoint declares no `quantization` object at
/// all. In that case a module that nevertheless carries `.scales` is
/// [`AffineError::AmbiguousQuantization`]: the shards say quantized and the
/// configuration says nothing, and guessing a width is exactly the failure
/// mode this crate exists to prevent.
///
/// Resolution, in order:
/// 1. an explicit override for this path wins;
/// 2. otherwise the default spec applies **iff** `<path>.scales` exists;
/// 3. otherwise the module is unquantized.
///
/// The resolved spec is then checked against the stored shapes, and a
/// disagreement is refused rather than reconciled.
pub fn classify_module(
    catalog: &Catalog,
    config: Option<&QuantizationConfig>,
    module: &str,
) -> Result<ModuleKind> {
    let weight = catalog.get(&format!("{module}{WEIGHT_SUFFIX}"));
    let scales = catalog.get(&format!("{module}{SCALES_SUFFIX}"));
    let biases = catalog.get(&format!("{module}{BIASES_SUFFIX}"));

    let weight = match (weight, scales, biases) {
        (None, None, None) => {
            return Err(AffineError::UnknownModule {
                module: module.to_string(),
            })
        }
        (None, _, _) => {
            return Err(AffineError::IncompleteTriple {
                module: module.to_string(),
                detail: "companions are present but .weight is absent".to_string(),
            })
        }
        (Some(weight), _, _) => weight,
    };

    let explicit = config.and_then(|config| config.explicit(module));

    match (scales, biases) {
        (None, None) => {
            if explicit.is_some() {
                return Err(AffineError::OverrideWithoutScales {
                    module: module.to_string(),
                });
            }
            if weight.dtype == Dtype::U32 {
                return Err(AffineError::IncompleteTriple {
                    module: module.to_string(),
                    detail: "packed U32 weight with neither .scales nor .biases".to_string(),
                });
            }
            Ok(ModuleKind::Unquantized(weight.clone()))
        }
        (Some(_), None) => Err(AffineError::IncompleteTriple {
            module: module.to_string(),
            detail: ".scales is present but .biases is not".to_string(),
        }),
        (None, Some(_)) => Err(AffineError::IncompleteTriple {
            module: module.to_string(),
            detail: ".biases is present but .scales is not".to_string(),
        }),
        (Some(scales), Some(biases)) => {
            let config = match config {
                None => {
                    return Err(AffineError::AmbiguousQuantization {
                        module: module.to_string(),
                    })
                }
                Some(config) => config,
            };
            if weight.dtype != Dtype::U32 {
                return Err(AffineError::IncompleteTriple {
                    module: module.to_string(),
                    detail: format!(
                        "a quantized weight must be U32, this one is {}",
                        weight.dtype
                    ),
                });
            }
            if scales.dtype != biases.dtype {
                return Err(AffineError::ScalesBiasesMismatch {
                    module: module.to_string(),
                    detail: format!(
                        "scales are {} and biases are {}",
                        scales.dtype, biases.dtype
                    ),
                });
            }
            scale_dtype_of(module, scales)?;
            if scales.shape != biases.shape {
                return Err(AffineError::ScalesBiasesMismatch {
                    module: module.to_string(),
                    detail: format!(
                        "scales are {:?} and biases are {:?}",
                        scales.shape, biases.shape
                    ),
                });
            }
            let spec = explicit.unwrap_or_else(|| config.default_spec());
            let triple = build_triple(module, weight, scales, biases, spec)?;
            Ok(ModuleKind::Quantized(Box::new(triple)))
        }
    }
}

fn build_triple(
    module: &str,
    weight: &TensorMeta,
    scales: &TensorMeta,
    biases: &TensorMeta,
    spec: QuantSpec,
) -> Result<AffineTriple> {
    // Everything the arithmetic methods later assume is decided here, once.
    if weight.dtype != Dtype::U32 {
        return Err(AffineError::IncompleteTriple {
            module: module.to_string(),
            detail: format!(
                "a quantized weight must be U32, this one is {}",
                weight.dtype
            ),
        });
    }
    if scales.dtype != biases.dtype {
        return Err(AffineError::ScalesBiasesMismatch {
            module: module.to_string(),
            detail: format!(
                "scales are {} and biases are {}",
                scales.dtype, biases.dtype
            ),
        });
    }
    if scales.shape != biases.shape {
        return Err(AffineError::ScalesBiasesMismatch {
            module: module.to_string(),
            detail: format!(
                "scales are {:?} and biases are {:?}",
                scales.shape, biases.shape
            ),
        });
    }
    let scale_dtype = scale_dtype_of(module, scales)?;
    if weight.shape.len() < 2 {
        return Err(AffineError::InconsistentOverride {
            module: module.to_string(),
            implied_bits: None,
            detail: format!(
                "a packed weight needs rank 2 or more, this one is {:?}",
                weight.shape
            ),
        });
    }
    if scales.shape.len() != weight.shape.len() {
        return Err(AffineError::InconsistentOverride {
            module: module.to_string(),
            implied_bits: None,
            detail: format!(
                "weight rank {} and metadata rank {} differ",
                weight.shape.len(),
                scales.shape.len()
            ),
        });
    }
    let rank = weight.shape.len();
    if weight.shape[..rank - 1] != scales.shape[..rank - 1] {
        return Err(AffineError::InconsistentOverride {
            module: module.to_string(),
            implied_bits: None,
            detail: format!(
                "weight leading dims {:?} and metadata leading dims {:?} differ",
                &weight.shape[..rank - 1],
                &scales.shape[..rank - 1]
            ),
        });
    }

    let packed_cols = weight.shape[rank - 1];
    let groups = scales.shape[rank - 1];
    let out_features = weight.shape[rank - 2];
    let leading = weight.shape[..rank - 2].to_vec();

    let in_features = mul(module, groups, u64::from(spec.group_size.get()))?;
    let unpacked = mul(module, packed_cols, u64::from(spec.bits.codes_per_word()))?;
    if unpacked != in_features {
        // `bits = 32 * packed_cols / in_features` when that division is exact.
        let numerator = mul(module, packed_cols, 32)?;
        let implied_bits = if in_features != 0 && numerator % in_features == 0 {
            u32::try_from(numerator / in_features).ok()
        } else {
            None
        };
        return Err(AffineError::InconsistentOverride {
            module: module.to_string(),
            implied_bits,
            detail: format!(
                "{packed_cols} packed columns at {} bits unpack to {unpacked}, \
                 but {groups} groups of {} are {in_features}",
                spec.bits.get(),
                spec.group_size.get()
            ),
        });
    }

    Ok(AffineTriple {
        module: module.to_string(),
        weight: weight.clone(),
        scales: scales.clone(),
        biases: biases.clone(),
        scale_dtype,
        spec,
        out_features,
        in_features,
        leading,
    })
}

impl AffineTriple {
    /// Packed `u32` words in one `[out_features, in_features]` plane.
    pub fn packed_words_per_plane(&self) -> Result<u64> {
        let packed_cols = self.weight.shape[self.weight.shape.len() - 1];
        mul(&self.module, self.out_features, packed_cols)
    }

    /// Metadata elements in one plane.
    pub fn groups_per_row(&self) -> u64 {
        self.scales.shape[self.scales.shape.len() - 1]
    }

    /// The dtype the scales and biases are stored in.
    pub fn scale_dtype(&self) -> ScaleDtype {
        self.scale_dtype
    }

    fn flat_leading_index(&self, index_path: &[u64]) -> Result<u64> {
        if index_path.len() != self.leading.len() {
            return Err(AffineError::IndexOutOfBounds {
                module: self.module.clone(),
                detail: format!(
                    "{} leading indices supplied, the tensor has {}",
                    index_path.len(),
                    self.leading.len()
                ),
            });
        }
        let mut flat: u64 = 0;
        for (index, extent) in index_path.iter().zip(&self.leading) {
            if index >= extent {
                return Err(AffineError::IndexOutOfBounds {
                    module: self.module.clone(),
                    detail: format!("index {index} is outside a dimension of extent {extent}"),
                });
            }
            flat = mul(&self.module, flat, *extent)?;
            flat = flat
                .checked_add(*index)
                .ok_or_else(|| AffineError::Overflow {
                    module: self.module.clone(),
                    detail: "leading index overflows u64".to_string(),
                })?;
        }
        Ok(flat)
    }

    fn slice(&self, tensor: &TensorMeta, begin: u64, len: u64) -> Result<ByteSlice> {
        let end = begin
            .checked_add(len)
            .ok_or_else(|| AffineError::Overflow {
                module: self.module.clone(),
                detail: "slice end overflows u64".to_string(),
            })?;
        if end > tensor.byte_len {
            return Err(AffineError::IndexOutOfBounds {
                module: self.module.clone(),
                detail: format!(
                    "slice [{begin}, {end}) exceeds the {} bytes of {}",
                    tensor.byte_len, tensor.name
                ),
            });
        }
        let absolute =
            tensor
                .data_begin
                .checked_add(begin)
                .ok_or_else(|| AffineError::Overflow {
                    module: self.module.clone(),
                    detail: "absolute slice offset overflows u64".to_string(),
                })?;
        Ok(ByteSlice {
            shard: tensor.shard,
            begin: absolute,
            len,
        })
    }

    /// The three byte ranges of one `[out_features, in_features]` plane --
    /// one expert of a stacked `[E, out, in]` tensor, for instance.
    ///
    /// Pure arithmetic: nothing is read, and every step is checked.
    pub fn expert_slice(&self, index_path: &[u64]) -> Result<TripleSlice> {
        let flat = self.flat_leading_index(index_path)?;
        let words = self.packed_words_per_plane()?;
        let weight_bytes = mul(&self.module, words, 4)?;
        let weight_begin = mul(&self.module, flat, weight_bytes)?;

        let element = self.scale_dtype().size_bytes() as u64;
        let metadata_elements = mul(&self.module, self.out_features, self.groups_per_row())?;
        let metadata_bytes = mul(&self.module, metadata_elements, element)?;
        let metadata_begin = mul(&self.module, flat, metadata_bytes)?;

        Ok(TripleSlice {
            weight: self.slice(&self.weight, weight_begin, weight_bytes)?,
            scales: self.slice(&self.scales, metadata_begin, metadata_bytes)?,
            biases: self.slice(&self.biases, metadata_begin, metadata_bytes)?,
        })
    }

    /// The three byte ranges of one row of one plane.
    pub fn row_slice(&self, index_path: &[u64], row: u64) -> Result<TripleSlice> {
        if row >= self.out_features {
            return Err(AffineError::IndexOutOfBounds {
                module: self.module.clone(),
                detail: format!("row {row} is outside {} output features", self.out_features),
            });
        }
        let plane = self.expert_slice(index_path)?;
        let packed_cols = self.weight.shape[self.weight.shape.len() - 1];
        let row_weight_bytes = mul(&self.module, packed_cols, 4)?;
        let element = self.scale_dtype().size_bytes() as u64;
        let row_metadata_bytes = mul(&self.module, self.groups_per_row(), element)?;

        let weight_begin = plane
            .weight
            .begin
            .checked_add(mul(&self.module, row, row_weight_bytes)?)
            .ok_or_else(|| AffineError::Overflow {
                module: self.module.clone(),
                detail: "row offset overflows u64".to_string(),
            })?;
        let metadata_begin = plane
            .scales
            .begin
            .checked_add(mul(&self.module, row, row_metadata_bytes)?)
            .ok_or_else(|| AffineError::Overflow {
                module: self.module.clone(),
                detail: "row metadata offset overflows u64".to_string(),
            })?;
        let bias_begin = plane
            .biases
            .begin
            .checked_add(mul(&self.module, row, row_metadata_bytes)?)
            .ok_or_else(|| AffineError::Overflow {
                module: self.module.clone(),
                detail: "row bias offset overflows u64".to_string(),
            })?;

        Ok(TripleSlice {
            weight: ByteSlice {
                shard: plane.weight.shard,
                begin: weight_begin,
                len: row_weight_bytes,
            },
            scales: ByteSlice {
                shard: plane.scales.shard,
                begin: metadata_begin,
                len: row_metadata_bytes,
            },
            biases: ByteSlice {
                shard: plane.biases.shard,
                begin: bias_begin,
                len: row_metadata_bytes,
            },
        })
    }
}

/// Classify every module path in a catalog.
///
/// This is a whole-catalog pass, so it also closes the configuration against
/// the catalog: an override naming a path that resolves to no quantized module
/// is [`AffineError::UnresolvedOverride`]. Per-module classification cannot
/// see that, because it only ever visits paths the catalog already has --
/// which is precisely how an override for a module that does not exist went
/// unnoticed. A rule nothing matches is a statement about a checkpoint that is
/// not the one in hand, and silently ignoring it is how a width ends up
/// applied to nothing.
pub fn classify_all(
    catalog: &Catalog,
    config: Option<&QuantizationConfig>,
) -> Vec<(String, Result<ModuleKind>)> {
    let paths = module_paths(catalog);
    let mut out: Vec<(String, Result<ModuleKind>)> = paths
        .iter()
        .map(|module| (module.clone(), classify_module(catalog, config, module)))
        .collect();
    if let Some(config) = config {
        let quantized: BTreeSet<String> = out
            .iter()
            .filter(|(_, kind)| matches!(kind, Ok(ModuleKind::Quantized(_))))
            .map(|(module, _)| module.clone())
            .collect();
        for module in config.overrides().keys() {
            if !quantized.contains(module) {
                out.push((
                    module.clone(),
                    Err(AffineError::UnresolvedOverride {
                        module: module.clone(),
                    }),
                ));
            }
        }
    }
    out
}

/// Whole-catalog validation: every module classifies and every override
/// resolves, or the first refusal is returned with the path it is about.
pub fn validate_catalog(
    catalog: &Catalog,
    config: Option<&QuantizationConfig>,
) -> Result<Vec<(String, ModuleKind)>> {
    let mut out = Vec::new();
    for (module, kind) in classify_all(catalog, config) {
        out.push((module, kind?));
    }
    Ok(out)
}

/// A convenience for tests and censuses: the resolved spec of a module, as
/// `(bits, group_size, mode)`.
pub fn resolved_spec(kind: &ModuleKind) -> Option<(u32, u32, &'static str)> {
    kind.spec()
        .map(|spec| (spec.bits.get(), spec.group_size.get(), spec.mode.as_str()))
}

/// Re-exported so a caller can build a spec without naming the spec module.
pub fn spec(bits: u32, group_size: u32) -> Result<QuantSpec> {
    Ok(QuantSpec::new(
        Bits::from_u32(bits)?,
        GroupSize::from_u32(group_size)?,
        Mode::Affine,
    ))
}
