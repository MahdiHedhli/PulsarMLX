//! Engine descriptor, provenance, capabilities, `INFO` facts and monitoring facts
//! (contract section 5).

use std::fmt;

/// The version of the seam contract an engine was built against.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct SeamVersion {
    /// Major version; 0 while the contract is a draft.
    pub major: u16,
    /// Minor version.
    pub minor: u16,
}

/// The seam version this crate implements: draft 0.2 of `contracts/backend-seam.md`.
/// It stays below 1.0 until the engine track's review is recorded (FR-039).
pub const SEAM_VERSION: SeamVersion = SeamVersion { major: 0, minor: 2 };

impl fmt::Display for SeamVersion {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}.{}", self.major, self.minor)
    }
}

/// The most characters of an engine's own provenance declaration that are kept.
pub const DECLARED_PROVENANCE_MAX_CHARS: usize = 64;

/// What an engine says it is. `Synthetic` is the only value the server accepts in this
/// increment; the single decision is [`require_synthetic`](super::require_synthetic)
/// (contract section 5.1, lead decision LD28).
#[non_exhaustive]
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Provenance {
    /// A synthetic engine: no real model behind it.
    Synthetic,
    /// Anything else: an engine that declared another provenance (`Some`), or declared
    /// none (`None`). Fail closed: an engine that cannot show it is synthetic is here.
    NotSynthetic {
        /// The engine's own declaration, bounded, when it made one.
        declared: Option<DeclaredProvenance>,
    },
}

impl Provenance {
    /// A provenance that is not synthetic, carrying the engine's declaration if it made
    /// one. Whatever the text says, the result is not synthetic: only an engine that
    /// constructs [`Provenance::Synthetic`] itself, or a line-protocol client that reads
    /// the declaration form settled under OPEN-58, reports synthetic provenance.
    pub fn not_synthetic(declared: Option<&str>) -> Self {
        Provenance::NotSynthetic {
            declared: declared.map(DeclaredProvenance::new),
        }
    }
}

impl fmt::Display for Provenance {
    /// `synthetic`, `not synthetic (declared "<text>")` or
    /// `not synthetic (no declaration)`. The declared text is escaped, so the result is
    /// always one line.
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Provenance::Synthetic => f.write_str("synthetic"),
            Provenance::NotSynthetic { declared: Some(d) } => {
                write!(f, "not synthetic (declared \"{d}\")")
            }
            Provenance::NotSynthetic { declared: None } => {
                f.write_str("not synthetic (no declaration)")
            }
        }
    }
}

/// An engine's own provenance text: at most [`DECLARED_PROVENANCE_MAX_CHARS`] characters,
/// displayed escaped (quotes, backslashes and control characters), so that it can be
/// named in a one-line refusal.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DeclaredProvenance {
    text: String,
    truncated: bool,
}

impl DeclaredProvenance {
    /// Keeps the first [`DECLARED_PROVENANCE_MAX_CHARS`] characters of `text`.
    pub fn new(text: &str) -> Self {
        let mut chars = text.chars();
        let kept: String = chars.by_ref().take(DECLARED_PROVENANCE_MAX_CHARS).collect();
        Self {
            text: kept,
            truncated: chars.next().is_some(),
        }
    }

    /// The kept text, unescaped.
    pub fn as_str(&self) -> &str {
        &self.text
    }
}

impl fmt::Display for DeclaredProvenance {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.text.escape_debug())?;
        if self.truncated {
            f.write_str("...")?;
        }
        Ok(())
    }
}

/// Which implementation stands behind the seam.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum EngineKind {
    /// The scripted in-process engine (ENG-02).
    Scripted,
    /// The line-protocol child engine (ENG-06, ENG-07).
    LineProtocol,
    /// The test adapter shaped like the engine track's coordinator (ENG-19).
    CoordinatorAdapter,
    /// The blocking runtime adapter (ENG-19).
    RuntimeAdapter,
}

impl EngineKind {
    /// The name used in logs and in the refusal line of section 5.1.
    pub fn as_str(self) -> &'static str {
        match self {
            EngineKind::Scripted => "scripted",
            EngineKind::LineProtocol => "line-protocol",
            EngineKind::CoordinatorAdapter => "coordinator-adapter",
            EngineKind::RuntimeAdapter => "runtime-adapter",
        }
    }
}

impl fmt::Display for EngineKind {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

/// Everything the server knows about a started engine (contract section 5).
#[derive(Debug, Clone, PartialEq)]
pub struct EngineDescriptor {
    /// The seam version the engine implements.
    pub seam: SeamVersion,
    /// The implementation.
    pub kind: EngineKind,
    /// What the engine reports it is; checked by [`require_synthetic`](super::require_synthetic).
    pub provenance: Provenance,
    /// `INFO engine=<v>`, else a build manifest.
    pub version: Option<String>,
    /// `READY <ctx>`; 0 means not ready.
    pub max_context: u32,
    /// When known, the ledger checks token ids against it.
    pub vocab_size: Option<u32>,
    /// Capability flags.
    pub caps: EngineCaps,
    /// Every `INFO key=value` fact, in arrival order.
    pub info: InfoMap,
    /// Monitoring-only facts.
    pub facts: EngineFacts,
}

impl EngineDescriptor {
    /// A descriptor at the current [`SEAM_VERSION`], not ready (`max_context` 0), with no
    /// capabilities, facts or `INFO` entries.
    pub fn new(kind: EngineKind, provenance: Provenance) -> Self {
        Self {
            seam: SEAM_VERSION,
            kind,
            provenance,
            version: None,
            max_context: 0,
            vocab_size: None,
            caps: EngineCaps::default(),
            info: InfoMap::default(),
            facts: EngineFacts::default(),
        }
    }

    /// True when `max_context` is 0: the server answers 503 "the model is starting"
    /// without calling the engine.
    ///
    /// Behavior reference: project-maya serve/server.py:3680-3681 at 7e68a30f.
    pub fn is_starting(&self) -> bool {
        self.max_context == 0
    }
}

/// Capability flags read from `READY` and `INFO` (contract section 5).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub struct EngineCaps {
    /// `READY ... stop`: honors a STOP mid-request.
    pub stop: bool,
    /// `READY ... pause`: a STOP that keeps the state.
    pub pause: bool,
    /// `READY ... multi=<n>`; `Some(1)` is not `None`.
    pub multi: Option<u32>,
    /// `INFO logit_bias=1`.
    pub logit_bias: bool,
    /// `INFO logprobs=<n>`.
    pub logprobs_max: Option<u8>,
    /// `INFO vision=ds4|mm3|off`, or absent.
    pub vision: VisionCap,
    /// `INFO ablate=1` (deviation POL-1: recognized, and refused unless advertised).
    pub ablate: bool,
    /// Lifecycle operations the engine supports.
    pub lifecycle: LifecycleCaps,
}

impl EngineCaps {
    /// The FIFO places the engine offers: `multi`, at least 1.
    ///
    /// Behavior reference: project-maya serve/server.py:2658 at 7e68a30f.
    pub fn places(&self) -> u32 {
        self.multi.unwrap_or(1).max(1)
    }

    /// Sets the `INFO`-derived flags as the donor reads them: `logit_bias` and `ablate`
    /// only for the integer 1; `logprobs_max` for a non-negative integer (capped at 255,
    /// which keeps the donor's `top >= n` test for every `n` the server accepts); `vision`
    /// for the exact strings `ds4`, `mm3` and `off`, and absent for anything else.
    ///
    /// Behavior reference: project-maya serve/server.py:2495, 2502, 2527, 7255-7271 at
    /// 7e68a30f.
    pub fn apply_info(&mut self, info: &InfoMap) {
        self.logit_bias = info.get("logit_bias") == Some(&InfoValue::Int(1));
        self.ablate = info.get("ablate") == Some(&InfoValue::Int(1));
        self.logprobs_max = match info.get("logprobs") {
            Some(InfoValue::Int(n)) if *n >= 0 => Some(u8::try_from(*n).unwrap_or(u8::MAX)),
            _ => None,
        };
        self.vision = match info.get("vision") {
            Some(InfoValue::Str(s)) if s == "ds4" => VisionCap::Ds4,
            Some(InfoValue::Str(s)) if s == "mm3" => VisionCap::Mm3,
            Some(InfoValue::Str(s)) if s == "off" => VisionCap::Off,
            _ => VisionCap::Absent,
        };
    }
}

/// The engine's own vision tower, as `INFO vision=` reports it.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum VisionCap {
    /// No `vision` fact, or a value the donor does not act on.
    #[default]
    Absent,
    /// `vision=off`: the tower did not load; pictures are refused.
    Off,
    /// `vision=ds4`.
    Ds4,
    /// `vision=mm3` (deviation LIC-2: this build cannot serve its pictures).
    Mm3,
}

/// Lifecycle operations an engine supports between generations.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub struct LifecycleCaps {
    /// Context reload by restart with a new context (FIX-1.1).
    pub set_context: bool,
    /// Restart after the engine ended.
    pub restart: bool,
    /// Unload between requests.
    pub unload: bool,
    /// `VLEND` / `VRECLAIM` control lines (PLAT-1).
    pub lend: bool,
}

/// The value of one `INFO key=value` fact.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum InfoValue {
    /// An optional minus sign followed by ASCII digits, within `i64`.
    Int(i64),
    /// Anything else, kept as written: `vram_gb=60.0` stays a string.
    Str(String),
}

impl InfoValue {
    /// Parses one value as the donor does: an optional minus followed by digits is an
    /// integer, anything else stays a string.
    ///
    /// Behavior reference: project-maya serve/server.py:927-930 at 7e68a30f. Where the
    /// donor's `v.lstrip("-").isdigit()` would accept more than one minus sign or a
    /// non-ASCII digit, and then fail in `int()` or read a non-ASCII digit, this keeps the
    /// value as a string; a value beyond `i64` also stays a string. These three cases are
    /// part of proposal P-21 in the deviation register, awaiting the owner's decision.
    pub fn parse(v: &str) -> Self {
        let digits = v.strip_prefix('-').unwrap_or(v);
        if !digits.is_empty() && digits.bytes().all(|b| b.is_ascii_digit()) {
            if let Ok(n) = v.parse::<i64>() {
                return InfoValue::Int(n);
            }
        }
        InfoValue::Str(v.to_owned())
    }
}

impl fmt::Display for InfoValue {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            InfoValue::Int(n) => write!(f, "{n}"),
            InfoValue::Str(s) => f.write_str(s),
        }
    }
}

/// The most distinct keys an [`InfoMap`] holds.
pub const INFO_MAX_ENTRIES: usize = 256;

/// The longest key or value, in bytes, an [`InfoMap`] keeps.
pub const INFO_MAX_TEXT_BYTES: usize = 1024;

/// Why an `INFO` fact was not kept.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum InfoRejected {
    /// The map already holds [`INFO_MAX_ENTRIES`] distinct keys.
    Full,
    /// The key or the value is longer than [`INFO_MAX_TEXT_BYTES`].
    TooLong,
}

/// Every `INFO key=value` fact in arrival order. A repeated key keeps its first position
/// and takes the new value, as a Python dict does.
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct InfoMap(Vec<(String, InfoValue)>);

impl InfoMap {
    /// An empty map.
    pub fn new() -> Self {
        Self::default()
    }

    /// Sets `key` to `value`: in place when the key is present, else at the end.
    pub fn try_insert(&mut self, key: &str, value: InfoValue) -> Result<(), InfoRejected> {
        let too_long = match &value {
            InfoValue::Str(s) => s.len() > INFO_MAX_TEXT_BYTES,
            InfoValue::Int(_) => false,
        };
        if key.len() > INFO_MAX_TEXT_BYTES || too_long {
            return Err(InfoRejected::TooLong);
        }
        if let Some(slot) = self.0.iter_mut().find(|(k, _)| k == key) {
            slot.1 = value;
            return Ok(());
        }
        if self.0.len() >= INFO_MAX_ENTRIES {
            return Err(InfoRejected::Full);
        }
        self.0.push((key.to_owned(), value));
        Ok(())
    }

    /// Reads the fields of one `INFO` line after its tag, each `key=value` split at the
    /// first `=` (a field without `=` has the empty string as its value), and returns how
    /// many fields were not kept because of the limits.
    ///
    /// Behavior reference: project-maya serve/server.py:927-930 at 7e68a30f.
    pub fn absorb_fields<'a>(&mut self, fields: impl IntoIterator<Item = &'a str>) -> usize {
        let mut dropped = 0;
        for kv in fields {
            let (k, v) = kv.split_once('=').unwrap_or((kv, ""));
            if self.try_insert(k, InfoValue::parse(v)).is_err() {
                dropped += 1;
            }
        }
        dropped
    }

    /// The value of `key`.
    pub fn get(&self, key: &str) -> Option<&InfoValue> {
        self.0.iter().find(|(k, _)| k == key).map(|(_, v)| v)
    }

    /// The facts in arrival order.
    pub fn iter(&self) -> impl Iterator<Item = (&str, &InfoValue)> {
        self.0.iter().map(|(k, v)| (k.as_str(), v))
    }

    /// The number of distinct keys.
    pub fn len(&self) -> usize {
        self.0.len()
    }

    /// True when no fact is held.
    pub fn is_empty(&self) -> bool {
        self.0.is_empty()
    }
}

/// Facts shown by monitoring only; nothing in serving depends on them.
#[derive(Debug, Clone, PartialEq, Default)]
pub struct EngineFacts {
    /// The model path the engine reports, if any.
    pub model_path: Option<String>,
    /// The engine's log file, if any.
    pub log_path: Option<String>,
    /// How long the start took, in seconds, rounded to a tenth as the donor does.
    pub load_s: Option<f64>,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn info_value_follows_the_donor_parse() {
        assert_eq!(InfoValue::parse("60.0"), InfoValue::Str("60.0".into()));
        assert_eq!(InfoValue::parse("1"), InfoValue::Int(1));
        assert_eq!(InfoValue::parse("-7"), InfoValue::Int(-7));
        assert_eq!(InfoValue::parse("007"), InfoValue::Int(7));
        assert_eq!(InfoValue::parse("-0"), InfoValue::Int(0));
        assert_eq!(InfoValue::parse(""), InfoValue::Str(String::new()));
        assert_eq!(InfoValue::parse("-"), InfoValue::Str("-".into()));
        assert_eq!(InfoValue::parse("+5"), InfoValue::Str("+5".into()));
        assert_eq!(InfoValue::parse("ds4"), InfoValue::Str("ds4".into()));
        assert_eq!(InfoValue::parse(" 5"), InfoValue::Str(" 5".into()));
    }

    #[test]
    fn info_value_quirks_stay_strings() {
        assert_eq!(InfoValue::parse("--5"), InfoValue::Str("--5".into()));
        assert_eq!(
            InfoValue::parse("\u{663}"),
            InfoValue::Str("\u{663}".into())
        );
        let huge = "99999999999999999999";
        assert_eq!(InfoValue::parse(huge), InfoValue::Str(huge.into()));
        assert_eq!(
            InfoValue::parse("-9223372036854775808"),
            InfoValue::Int(i64::MIN)
        );
    }

    #[test]
    fn places_is_multi_at_least_one() {
        let mut caps = EngineCaps::default();
        assert_eq!(caps.places(), 1);
        caps.multi = Some(1);
        assert_eq!(caps.places(), 1);
        assert_ne!(caps.multi, None, "multi=1 stays distinct from no multi");
        caps.multi = Some(0);
        assert_eq!(caps.places(), 1);
        caps.multi = Some(4);
        assert_eq!(caps.places(), 4);
    }

    #[test]
    fn info_map_keeps_first_position_on_repeat() {
        let mut m = InfoMap::new();
        assert_eq!(m.absorb_fields(["a=1", "vram_gb=60.0", "flag", "a=2"]), 0);
        let got: Vec<_> = m.iter().map(|(k, v)| (k.to_owned(), v.clone())).collect();
        assert_eq!(
            got,
            vec![
                ("a".to_owned(), InfoValue::Int(2)),
                ("vram_gb".to_owned(), InfoValue::Str("60.0".into())),
                ("flag".to_owned(), InfoValue::Str(String::new())),
            ]
        );
        // Split at the first `=` only, as `str.partition` does.
        m.absorb_fields(["k=a=b"]);
        assert_eq!(m.get("k"), Some(&InfoValue::Str("a=b".into())));
    }

    #[test]
    fn info_map_is_bounded() {
        let mut m = InfoMap::new();
        for i in 0..INFO_MAX_ENTRIES {
            assert!(m.try_insert(&format!("k{i}"), InfoValue::Int(1)).is_ok());
        }
        assert_eq!(
            m.try_insert("one_more", InfoValue::Int(1)),
            Err(InfoRejected::Full)
        );
        // An existing key can still change.
        assert!(m.try_insert("k0", InfoValue::Int(2)).is_ok());
        let long = "v".repeat(INFO_MAX_TEXT_BYTES + 1);
        assert_eq!(
            m.try_insert("k1", InfoValue::Str(long)),
            Err(InfoRejected::TooLong)
        );
        assert_eq!(m.len(), INFO_MAX_ENTRIES);
    }

    #[test]
    fn caps_from_info_follow_the_donor_truthiness() {
        let mut m = InfoMap::new();
        m.absorb_fields(["logit_bias=1", "logprobs=20", "vision=ds4", "ablate=2"]);
        let mut caps = EngineCaps::default();
        caps.apply_info(&m);
        assert!(caps.logit_bias);
        assert_eq!(caps.logprobs_max, Some(20));
        assert_eq!(caps.vision, VisionCap::Ds4);
        assert!(!caps.ablate, "only the integer 1 advertises ablation");

        let mut m = InfoMap::new();
        m.absorb_fields(["logit_bias=true", "logprobs=-1", "vision=1"]);
        caps.apply_info(&m);
        assert!(!caps.logit_bias);
        assert_eq!(caps.logprobs_max, None);
        assert_eq!(caps.vision, VisionCap::Absent);

        let mut m = InfoMap::new();
        m.absorb_fields(["logprobs=4000", "vision=mm3", "ablate=1"]);
        caps.apply_info(&m);
        assert_eq!(caps.logprobs_max, Some(u8::MAX));
        assert_eq!(caps.vision, VisionCap::Mm3);
        assert!(caps.ablate);
        m.absorb_fields(["vision=off"]);
        caps.apply_info(&m);
        assert_eq!(caps.vision, VisionCap::Off);
    }

    #[test]
    fn provenance_display_is_one_escaped_line() {
        assert_eq!(Provenance::Synthetic.to_string(), "synthetic");
        assert_eq!(
            Provenance::not_synthetic(None).to_string(),
            "not synthetic (no declaration)"
        );
        assert_eq!(
            Provenance::not_synthetic(Some("real\n\"x\"")).to_string(),
            "not synthetic (declared \"real\\n\\\"x\\\"\")"
        );
        let long = "a".repeat(DECLARED_PROVENANCE_MAX_CHARS + 5);
        let shown = Provenance::not_synthetic(Some(&long)).to_string();
        assert!(shown.ends_with("...\")"));
        assert!(!shown.contains(&long));
    }

    #[test]
    fn a_new_descriptor_is_starting_at_the_current_seam() {
        let d = EngineDescriptor::new(EngineKind::Scripted, Provenance::Synthetic);
        assert!(d.is_starting());
        assert_eq!(d.seam, SEAM_VERSION);
        assert_eq!(SEAM_VERSION.to_string(), "0.2");
    }
}
