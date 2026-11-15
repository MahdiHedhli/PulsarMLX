//! The generation request (contract section 6). Every field is typed; no client JSON key,
//! and in particular no key beginning with `_`, reaches it (deviation SEC-6). The wire
//! encoding of these fields belongs to ENG-03 and the line-protocol contract of ENG-04.

use std::fmt;
use std::path::PathBuf;
use std::sync::Arc;

/// A request id, assigned by the server: unique and increasing across engine restarts.
/// Engines never assign it (tasks.md R27).
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct RequestId(pub u64);

impl fmt::Display for RequestId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.0)
    }
}

/// One generation call.
#[derive(Debug, Clone, PartialEq)]
pub struct GenerationRequest {
    /// Assigned by the server.
    pub rid: RequestId,
    /// Always the whole prompt, already tokenized.
    pub prompt: Arc<[u32]>,
    /// After the server's context rule.
    pub max_new: u32,
    /// Sampling parameters.
    pub sampling: Sampling,
    /// An early-stop hint; the server re-checks every stop id itself.
    pub stop_ids: Arc<[u32]>,
    /// Top alternatives per token, at most `caps.logprobs_max`; `Some(0)` asks for the
    /// token's own logprob with no alternatives.
    pub logprobs: Option<u8>,
    /// Thinking-budget keys an engine may enforce itself.
    pub thinking: Option<ThinkingHints>,
    /// Restore points for engines that use them.
    pub restore: Option<RestoreHints>,
    /// Validated per-request engine settings (`strata_tune`).
    pub tune: TuneKnobs,
    /// `cvec=0|1` for an engine started with a vector.
    pub projection: Option<bool>,
    /// Always false unless `caps.ablate` (POL-1).
    pub ablate: bool,
    /// Picture data for `GENI`, carried with the request.
    pub embeddings: Option<EmbeddingsRef>,
}

impl GenerationRequest {
    /// A request with default sampling and no hints.
    pub fn new(rid: RequestId, prompt: impl Into<Arc<[u32]>>, max_new: u32) -> Self {
        Self {
            rid,
            prompt: prompt.into(),
            max_new,
            sampling: Sampling::default(),
            stop_ids: Arc::from(Vec::new()),
            logprobs: None,
            thinking: None,
            restore: None,
            tune: TuneKnobs::default(),
            projection: None,
            ablate: false,
            embeddings: None,
        }
    }
}

/// Sampling parameters. `None` keeps the engine's default.
#[derive(Debug, Clone, PartialEq, Default)]
pub struct Sampling {
    /// `None` keeps the engine default (greedy).
    pub temperature: Option<f64>,
    /// Nucleus sampling.
    pub top_p: Option<f64>,
    /// Top-k sampling.
    pub top_k: Option<u32>,
    /// Min-p sampling.
    pub min_p: Option<f64>,
    /// A seed.
    pub seed: Option<u64>,
    /// Repetition penalties.
    pub penalties: Penalties,
    /// Sorted by id, one entry per id; empty means none. `f64`, as the donor keeps the
    /// client's Python float until it writes the `GEN` key (serve/server.py:1259-1260 at
    /// 7e68a30f).
    pub logit_bias: Arc<[(u32, f64)]>,
}

/// Repetition penalties, as llama.cpp names them.
#[derive(Debug, Clone, Copy, PartialEq, Default)]
pub struct Penalties {
    /// `repetition_penalty`.
    pub repeat: Option<f64>,
    /// `presence_penalty`.
    pub presence: Option<f64>,
    /// `frequency_penalty`.
    pub frequency: Option<f64>,
    /// `penalty_last_n`: none given means the last 64 tokens, 0 no penalties, -1 the whole
    /// context.
    pub last_n: Option<i64>,
}

/// Thinking-budget keys.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ThinkingHints {
    /// Tokens of reasoning allowed.
    pub budget: u32,
    /// The token that ends reasoning.
    pub end_id: u32,
    /// A soft close at a sentence's end.
    pub soft: Option<SoftClose>,
}

/// The soft close of a thinking budget: close at the first stop text after `at` tokens.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SoftClose {
    /// Tokens after which a stop text closes reasoning.
    pub at: u32,
    /// The stop texts, as the run config gives them.
    pub stops: String,
}

/// Restore points for the prompt (engines that use them).
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct RestoreHints {
    /// Mark positions.
    pub marks: Vec<u64>,
    /// The tail position.
    pub tail: Option<u64>,
    /// The shared position.
    pub shared: Option<u64>,
}

/// The value of one tune knob.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum TuneValue {
    /// An integer knob.
    Int(i64),
    /// A share or probability knob.
    Float(f64),
    /// A word from the knob's fixed word list.
    Word(&'static str),
}

/// The most knobs a [`TuneKnobs`] carries.
pub const TUNE_MAX_KNOBS: usize = 64;

/// Validated per-request engine settings, in the order they were set. Knob names and word
/// values are `&'static str`, meant to come from ENG-03's compile-time table. The type
/// makes accidental use of client text harder but does not prevent it (a caller can leak a
/// `String` into a `&'static str`); ENG-03's validation is what keeps client keys out
/// (deviation SEC-6, contract section 14, Q8).
#[derive(Debug, Clone, PartialEq, Default)]
pub struct TuneKnobs(Vec<(&'static str, TuneValue)>);

impl TuneKnobs {
    /// No knobs.
    pub fn new() -> Self {
        Self::default()
    }

    /// Sets a knob; a repeated name replaces the earlier value in place. Returns false,
    /// keeping the set unchanged, when it already holds [`TUNE_MAX_KNOBS`] names.
    pub fn set(&mut self, name: &'static str, value: TuneValue) -> bool {
        if let Some(slot) = self.0.iter_mut().find(|(n, _)| *n == name) {
            slot.1 = value;
            return true;
        }
        if self.0.len() >= TUNE_MAX_KNOBS {
            return false;
        }
        self.0.push((name, value));
        true
    }

    /// The knobs in the order they were set.
    pub fn iter(&self) -> impl Iterator<Item = (&'static str, TuneValue)> + '_ {
        self.0.iter().copied()
    }

    /// True when no knob is set.
    pub fn is_empty(&self) -> bool {
        self.0.is_empty()
    }
}

/// What the picture data of a `GENI` request is.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EmbeddingsKind {
    /// An embeddings file the engine reads.
    Embeddings,
    /// A pixels file the engine's own vision tower reads.
    Pixels,
}

/// Picture data carried with a request. The file's format and lifetime belong to the
/// vision packages (ENG-14, RSP-18, RSP-19).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EmbeddingsRef {
    /// The file.
    pub path: PathBuf,
    /// What it holds.
    pub kind: EmbeddingsKind,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn tune_knobs_keep_order_and_bound() {
        let mut t = TuneKnobs::new();
        assert!(t.is_empty());
        assert!(t.set("pcie_frac", TuneValue::Float(0.5)));
        assert!(t.set("cpu_threads", TuneValue::Int(4)));
        assert!(t.set("pcie_frac", TuneValue::Float(0.25)));
        let got: Vec<_> = t.iter().collect();
        assert_eq!(
            got,
            vec![
                ("pcie_frac", TuneValue::Float(0.25)),
                ("cpu_threads", TuneValue::Int(4))
            ]
        );
        let mut full = TuneKnobs::new();
        for i in 0..TUNE_MAX_KNOBS {
            let name: &'static str = Box::leak(format!("k{i}").into_boxed_str());
            assert!(full.set(name, TuneValue::Int(1)));
        }
        assert!(!full.set("one_more", TuneValue::Int(1)));
    }

    #[test]
    fn a_new_request_has_no_hints() {
        let r = GenerationRequest::new(RequestId(7), vec![1, 2, 3], 16);
        assert_eq!(r.rid, RequestId(7));
        assert_eq!(&*r.prompt, &[1, 2, 3]);
        assert!(r.sampling.logit_bias.is_empty());
        assert!(!r.ablate);
        assert_eq!(r.logprobs, None);
        assert_eq!(RequestId(42).to_string(), "42");
    }
}
