//! Bit width, group size, mode -- and the configuration that resolves them
//! per module.
//!
//! The admitted set is narrower than MLX's. MLX accepts bits 2,3,4,5,6,8 and
//! group sizes 32,64,128; this crate accepts **bits 4 and 8** and group sizes
//! 32, 64 and 128, in `affine` mode only. The reason is not taste: at 4 and 8
//! bits a code never straddles a 32-bit word, while at 3, 5 and 6 MLX uses a
//! different bit-serial layout across the word. Admitting a width whose layout
//! this crate does not implement would mis-decode silently, so it is refused
//! instead.

use std::collections::BTreeMap;

use serde_json::{Map, Value};

use crate::error::{AffineError, Result};

/// The admitted packed bit widths.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum Bits {
    Four,
    Eight,
}

impl Bits {
    pub fn from_u32(value: u32) -> Result<Self> {
        match value {
            4 => Ok(Self::Four),
            8 => Ok(Self::Eight),
            other => Err(AffineError::UnsupportedQuantization {
                detail: format!("bits {other} is outside the admitted set {{4, 8}}"),
            }),
        }
    }

    pub fn get(self) -> u32 {
        match self {
            Self::Four => 4,
            Self::Eight => 8,
        }
    }

    /// Codes per packed `u32` word. Exact, because 32 is a multiple of both.
    pub fn codes_per_word(self) -> u32 {
        32 / self.get()
    }

    /// The largest code this width can hold.
    pub fn max_code(self) -> u32 {
        (1u32 << self.get()) - 1
    }
}

/// The admitted group sizes.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum GroupSize {
    ThirtyTwo,
    SixtyFour,
    OneTwentyEight,
}

impl GroupSize {
    pub fn from_u32(value: u32) -> Result<Self> {
        match value {
            32 => Ok(Self::ThirtyTwo),
            64 => Ok(Self::SixtyFour),
            128 => Ok(Self::OneTwentyEight),
            other => Err(AffineError::UnsupportedQuantization {
                detail: format!("group_size {other} is outside the admitted set {{32, 64, 128}}"),
            }),
        }
    }

    pub fn get(self) -> u32 {
        match self {
            Self::ThirtyTwo => 32,
            Self::SixtyFour => 64,
            Self::OneTwentyEight => 128,
        }
    }
}

/// The admitted quantization mode. MLX's `mode` is a free string and newer
/// modes exist; only `affine` is implemented here, and any other value is a
/// refusal rather than an assumption.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Default)]
pub enum Mode {
    #[default]
    Affine,
}

impl Mode {
    pub fn parse(value: &str) -> Result<Self> {
        if value == "affine" {
            Ok(Self::Affine)
        } else {
            Err(AffineError::UnsupportedQuantization {
                detail: format!("mode {value:?} is not affine"),
            })
        }
    }

    pub fn as_str(self) -> &'static str {
        "affine"
    }
}

/// One fully resolved quantization specification.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct QuantSpec {
    pub bits: Bits,
    pub group_size: GroupSize,
    pub mode: Mode,
}

impl QuantSpec {
    pub fn new(bits: Bits, group_size: GroupSize, mode: Mode) -> Self {
        Self {
            bits,
            group_size,
            mode,
        }
    }

    /// `group_size` codes packed at `bits` each occupy this many `u32` words.
    /// Exact for every admitted combination.
    pub fn words_per_group(self) -> u32 {
        self.group_size.get() / self.bits.codes_per_word()
    }
}

/// The checkpoint's quantization configuration: one default plus the explicit
/// per-module overrides.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct QuantizationConfig {
    default: QuantSpec,
    overrides: BTreeMap<String, QuantSpec>,
}

const BITS_KEY: &str = "bits";
const GROUP_KEY: &str = "group_size";
const MODE_KEY: &str = "mode";

fn integer(object: &Map<String, Value>, key: &str) -> Option<std::result::Result<u32, String>> {
    let value = object.get(key)?;
    Some(match value {
        Value::Number(number) => match number.as_u64() {
            Some(raw) => u32::try_from(raw).map_err(|_| format!("{key} {raw} is out of range")),
            None => Err(format!("{key} {number} is not a non-negative integer")),
        },
        other => Err(format!("{key} {other} is not a non-negative integer")),
    })
}

fn spec_from_object(object: &Map<String, Value>, inherited_mode: Mode) -> Result<QuantSpec> {
    let bits = match integer(object, BITS_KEY) {
        None => {
            return Err(AffineError::MissingDefaultSpec {
                detail: "no bits".to_string(),
            });
        }
        Some(Err(detail)) => return Err(AffineError::UnsupportedQuantization { detail }),
        Some(Ok(value)) => Bits::from_u32(value)?,
    };
    let group_size = match integer(object, GROUP_KEY) {
        None => {
            return Err(AffineError::MissingDefaultSpec {
                detail: "no group_size".to_string(),
            });
        }
        Some(Err(detail)) => return Err(AffineError::UnsupportedQuantization { detail }),
        Some(Ok(value)) => GroupSize::from_u32(value)?,
    };
    let mode = match object.get(MODE_KEY) {
        None => inherited_mode,
        Some(Value::String(text)) => Mode::parse(text)?,
        Some(other) => {
            return Err(AffineError::UnsupportedQuantization {
                detail: format!("mode {other} is not a string"),
            })
        }
    };
    Ok(QuantSpec {
        bits,
        group_size,
        mode,
    })
}

impl QuantizationConfig {
    /// Build a configuration directly, for tests and for callers that already
    /// hold a resolved default.
    pub fn new(default: QuantSpec) -> Self {
        Self {
            default,
            overrides: BTreeMap::new(),
        }
    }

    pub fn with_override(mut self, module: &str, spec: QuantSpec) -> Self {
        self.overrides.insert(module.to_string(), spec);
        self
    }

    pub fn default_spec(&self) -> QuantSpec {
        self.default
    }

    pub fn overrides(&self) -> &BTreeMap<String, QuantSpec> {
        &self.overrides
    }

    pub fn explicit(&self, module: &str) -> Option<QuantSpec> {
        self.overrides.get(module).copied()
    }

    /// Read the `quantization` object out of a `config.json`.
    ///
    /// `quantization_config`, when present, must be identical to it; the two
    /// are written as one dict upstream, so a difference is a corrupted or a
    /// hand-edited configuration and is refused.
    ///
    /// The top-level `bits` and `group_size` are the default. Every other key
    /// is a module path whose value must be an object carrying its own `bits`
    /// and `group_size`. The upstream Python loader also writes `False` for
    /// "do not quantize this module"; this crate does **not** admit that
    /// spelling. Absence of a module from the dict already means "no explicit
    /// override", and the presence of `<module>.scales` already decides
    /// whether the default applies, so `False` is redundant with a rule that
    /// is checked against the shards themselves. Admitting it would add a
    /// second, weaker source of truth.
    pub fn from_config_json(json: &str) -> Result<Self> {
        // Duplicate members at any depth are refused before the text becomes a
        // map: `{"bits":3,"bits":4}` has two readings, and the second being
        // valid is not a reason to accept it. The scanner lives in
        // `safetensors-catalog` so both crates refuse the same documents.
        safetensors_catalog::reject_duplicate_keys_str(json, "config.json").map_err(|error| {
            match error {
                safetensors_catalog::CatalogError::DuplicateKey { path } => {
                    AffineError::DuplicateConfigKey { path }
                }
                other => AffineError::InvalidConfigJson {
                    detail: other.to_string(),
                },
            }
        })?;
        let value: Value =
            serde_json::from_str(json).map_err(|error| AffineError::InvalidConfigJson {
                detail: error.to_string(),
            })?;
        let root = value
            .as_object()
            .ok_or_else(|| AffineError::InvalidConfigJson {
                detail: "configuration is not an object".to_string(),
            })?;

        let primary = root.get("quantization");
        let secondary = root.get("quantization_config");
        let chosen = match (primary, secondary) {
            (None, None) => return Err(AffineError::NoQuantizationConfig),
            (Some(first), Some(second)) => {
                if first != second {
                    return Err(AffineError::InconsistentConfig);
                }
                first
            }
            (Some(only), None) | (None, Some(only)) => only,
        };
        let object = chosen
            .as_object()
            .ok_or_else(|| AffineError::InvalidConfigJson {
                detail: "quantization is not an object".to_string(),
            })?;

        let mode = match object.get(MODE_KEY) {
            None => Mode::Affine,
            Some(Value::String(text)) => Mode::parse(text)?,
            Some(other) => {
                return Err(AffineError::UnsupportedQuantization {
                    detail: format!("mode {other} is not a string"),
                })
            }
        };
        let default = spec_from_object(object, mode)?;

        let mut overrides = BTreeMap::new();
        for (key, entry) in object {
            if key == BITS_KEY || key == GROUP_KEY || key == MODE_KEY {
                continue;
            }
            let nested =
                entry
                    .as_object()
                    .ok_or_else(|| AffineError::UnsupportedOverrideValue {
                        module: key.clone(),
                        detail: format!(
                            "value {entry} is not an object carrying bits and group_size"
                        ),
                    })?;
            let spec = match spec_from_object(nested, mode) {
                Ok(spec) => spec,
                Err(AffineError::MissingDefaultSpec { detail }) => {
                    return Err(AffineError::UnsupportedOverrideValue {
                        module: key.clone(),
                        detail,
                    })
                }
                Err(other) => return Err(other),
            };
            overrides.insert(key.clone(), spec);
        }

        Ok(Self { default, overrides })
    }
}
