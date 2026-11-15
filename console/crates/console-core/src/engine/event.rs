//! Engine events, the event sink and delivery (contract section 7).

use super::pyparse::py_float;
use super::request::RequestId;
use super::text::BoundedText;

/// One event an engine delivers during a generation.
#[derive(Debug, Clone, PartialEq)]
pub enum EngineEvent {
    /// First, exactly once: the prompt was taken.
    Admitted {
        /// Must equal the request's `prompt.len()`.
        prompt_tokens: u32,
        /// Prompt tokens reused from the engine's cache, when known at admission.
        reused_tokens: Option<u32>,
    },
    /// Prompt reading progress (the donor's `PP` line).
    PromptProgress(PromptProgress),
    /// One committed token.
    Token(CommittedToken),
    /// Telemetry (the donor's `STAT` line); any time.
    Sample(EngineSample),
    /// A note for the log, at most 512 bytes; never shown as output.
    Note(BoundedText),
}

/// Prompt reading progress.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct PromptProgress {
    /// Tokens read so far.
    pub read: u32,
    /// Tokens to read.
    pub total: u32,
    /// Tokens reused from the cache.
    pub reused: u32,
    /// Milliseconds so far.
    pub ms: f64,
    /// Reading speed, when the engine reports one.
    pub tok_s: Option<f64>,
}

/// One committed token.
#[derive(Debug, Clone, PartialEq)]
pub struct CommittedToken {
    /// 0-based ordinal among this call's generated tokens.
    pub index: u32,
    /// Absolute position in the engine's sequence.
    pub position: u64,
    /// The token id.
    pub id: u32,
    /// Present only when the request asked for logprobs.
    pub logprob: Option<TokenLogprob>,
}

/// A token's logprob and its row's most likely alternatives, most likely first. The values
/// are `f64`, as the donor keeps Python floats, so an engine's figure reaches the client
/// unchanged.
///
/// Behavior reference: project-maya serve/server.py:532-548 at 7e68a30f (`LpToken.lp`,
/// `parse_lp`).
#[derive(Debug, Clone, PartialEq)]
pub struct TokenLogprob {
    /// The token's own logprob.
    pub logprob: f64,
    /// `(id, logprob)` alternatives, most likely first.
    pub top: Vec<(u32, f64)>,
}

/// The most entries an [`EngineSample`] keeps.
pub const SAMPLE_MAX_ENTRIES: usize = 64;

/// The longest key or text value, in bytes, an [`EngineSample`] keeps.
pub const SAMPLE_MAX_TEXT_BYTES: usize = 256;

/// One value of a `STAT` entry.
#[derive(Debug, Clone, PartialEq)]
pub enum StatValue {
    /// A value Python's `float()` reads.
    Num(f64),
    /// Anything else, as written.
    Text(String),
}

/// A telemetry sample: the donor's untyped `STAT key=value` map, in arrival order
/// (contract section 14, Q7). The wall-clock time the donor adds is added by whoever
/// records the sample, not by the engine.
#[derive(Debug, Clone, PartialEq, Default)]
#[non_exhaustive]
pub struct EngineSample {
    /// The entries, in arrival order; a repeated key keeps its first position and takes
    /// the new value. Private, so that [`set`](Self::set) keeps the limits.
    stat: Vec<(String, StatValue)>,
}

impl EngineSample {
    /// An empty sample.
    pub fn new() -> Self {
        Self::default()
    }

    /// Reads the fields of one `STAT` line after its tag: each `key=value` split at the
    /// first `=`, the value a number where Python's `float()` reads one, else text.
    /// Entries beyond [`SAMPLE_MAX_ENTRIES`] distinct keys, and keys or text values longer
    /// than [`SAMPLE_MAX_TEXT_BYTES`], are dropped.
    ///
    /// Behavior reference: project-maya serve/server.py:1201-1215 at 7e68a30f.
    pub fn from_stat_fields<'a>(fields: impl IntoIterator<Item = &'a str>) -> Self {
        let mut sample = Self::default();
        for kv in fields {
            let (k, v) = kv.split_once('=').unwrap_or((kv, ""));
            let value = match py_float(v) {
                Some(x) => StatValue::Num(x),
                None => StatValue::Text(v.to_owned()),
            };
            sample.set(k, value);
        }
        sample
    }

    /// Sets one entry within the limits; returns false when it was dropped.
    pub fn set(&mut self, key: &str, value: StatValue) -> bool {
        let too_long = match &value {
            StatValue::Text(s) => s.len() > SAMPLE_MAX_TEXT_BYTES,
            StatValue::Num(_) => false,
        };
        if key.len() > SAMPLE_MAX_TEXT_BYTES || too_long {
            return false;
        }
        if let Some(slot) = self.stat.iter_mut().find(|(k, _)| k == key) {
            slot.1 = value;
            return true;
        }
        if self.stat.len() >= SAMPLE_MAX_ENTRIES {
            return false;
        }
        self.stat.push((key.to_owned(), value));
        true
    }

    /// The value of `key`.
    pub fn get(&self, key: &str) -> Option<&StatValue> {
        self.stat.iter().find(|(k, _)| k == key).map(|(_, v)| v)
    }

    /// The entries, in arrival order.
    pub fn iter(&self) -> impl Iterator<Item = (&str, &StatValue)> {
        self.stat.iter().map(|(k, v)| (k.as_str(), v))
    }

    /// The number of entries, at most [`SAMPLE_MAX_ENTRIES`].
    pub fn len(&self) -> usize {
        self.stat.len()
    }

    /// True when the sample has no entry.
    pub fn is_empty(&self) -> bool {
        self.stat.is_empty()
    }
}

/// Why a sink did not accept an event.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DeliveryRefused {
    /// Not accepted now; offer the same event again. Never skip it.
    Backpressure,
    /// Nobody is reading; stop at the next step and return `Cancelled`.
    ConsumerGone,
}

/// Where an engine delivers the events of one generation. Called on the driver thread.
pub trait EventSink {
    /// `Ok(())` means accepted, or an exact replay of the most recently accepted token,
    /// dropped.
    fn deliver(&mut self, event: EngineEvent) -> Result<(), DeliveryRefused>;
}

/// Where a multi-conversation engine delivers events, each tagged with its request id
/// (contract section 4.1).
pub trait TaggedSink {
    /// As [`EventSink::deliver`], for the generation `rid`.
    fn deliver(&mut self, rid: RequestId, event: EngineEvent) -> Result<(), DeliveryRefused>;
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn stat_fields_follow_the_donor_shape() {
        let s = EngineSample::from_stat_fields(["hit=0.75", "tier=ssd", "n=3", "flag", "hit=1"]);
        let entries: Vec<(&str, &StatValue)> = s.iter().collect();
        assert_eq!(
            entries,
            vec![
                ("hit", &StatValue::Num(1.0)),
                ("tier", &StatValue::Text("ssd".into())),
                ("n", &StatValue::Num(3.0)),
                ("flag", &StatValue::Text(String::new())),
            ]
        );
        assert_eq!(s.get("tier"), Some(&StatValue::Text("ssd".into())));
    }

    #[test]
    fn stat_sample_is_bounded() {
        let fields: Vec<String> = (0..SAMPLE_MAX_ENTRIES + 10)
            .map(|i| format!("k{i}=1"))
            .collect();
        let s = EngineSample::from_stat_fields(fields.iter().map(String::as_str));
        assert_eq!(s.len(), SAMPLE_MAX_ENTRIES);
        assert_eq!(s.iter().count(), SAMPLE_MAX_ENTRIES);
        let mut s = EngineSample::new();
        assert!(s.is_empty());
        assert!(!s.set("k", StatValue::Text("v".repeat(SAMPLE_MAX_TEXT_BYTES + 1))));
        assert!(!s.set(&"k".repeat(SAMPLE_MAX_TEXT_BYTES + 1), StatValue::Num(1.0)));
        assert!(s.set("k", StatValue::Num(1.0)));
        assert_eq!(s.len(), 1);
    }

    /// Reads an LP line's fields after its tag as the donor's `parse_lp` does
    /// (serve/server.py:539-548 at 7e68a30f), with this crate's Python `float()`.
    fn parse_lp(fields: &[&str]) -> Option<(u32, TokenLogprob)> {
        let id = fields.first()?.parse::<u32>().ok()?;
        let logprob = py_float(fields.get(1)?)?;
        let mut top = Vec::new();
        for f in fields.get(2..)? {
            let (i, v) = f.split_once(':').unwrap_or((f, ""));
            top.push((i.parse::<u32>().ok()?, py_float(v)?));
        }
        Some((id, TokenLogprob { logprob, top }))
    }

    #[test]
    fn logprobs_keep_the_engine_figure_as_a_python_float() {
        // The donor's parity test expects lp[1] == [(104, -0.1)] for this line
        // (serve/test_logprobs.py:104-111 at 7e68a30f); -0.1 is an f64 there.
        let (id, lp) = parse_lp(&["105", "-inf", "104:-0.1"]).expect("reads");
        assert_eq!(id, 105);
        assert_eq!(lp.logprob, f64::NEG_INFINITY);
        assert_eq!(lp.top, vec![(104, -0.1_f64)]);
        assert_eq!(lp.top[0].1.to_bits(), (-0.1_f64).to_bits());
        // A figure with more digits than an f32 holds comes through unchanged.
        let (_, lp) = parse_lp(&["7", "-0.123456789", "7:-0.123456789"]).expect("reads");
        assert_eq!(lp.logprob, -0.123_456_789_f64);
        assert_eq!(format!("{}", lp.top[0].1), "-0.123456789");
    }
}
