//! The output stage of one answer: committed tokens in, [`AnswerEvent`]s out.
//!
//! [`AnswerStage`] is the seam the output pipeline of M2 implements (PRM-12 with the
//! parsers of PRM-06, PRM-09 and PRM-16: reasoning, tool calls, markers inside code, the
//! loop guard and the thinking budget). [`PlainOutput`] is the M1 stage, the plain-content
//! subset of the donor's token loop in `Service.run`: detokenization, the end-of-turn ids,
//! the stop texts and the client's own stop strings, and the logprobs entries that ride
//! with the text. Every piece of text is answer content: there is no reasoning parser in
//! M1, so a script that writes `</think>` writes it as content.
//!
//! Behavior reference: project-maya serve/server.py:2442-2477, 4310-4340 and 4519-4660 at
//! 7e68a30f.

use std::sync::Arc;

use console_core::engine::CommittedToken;
use console_core::turn::CallerFinish;
use console_tokenizer::bpe::Tokenize;
use console_tokenizer::detok::Detokenizer;
use serde_json::Value;

use super::events::AnswerEvent;
use super::logprobs::logprob_entry;
use crate::error::MalformedCategory;
use crate::inference::InferenceError;

/// What one token gave: the events to send, and whether the answer ends here.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct StageStep {
    /// The events, in order.
    pub events: Vec<AnswerEvent>,
    /// The answer is finished here (an end-of-turn id, a stop text, a stop string).
    pub finish: Option<CallerFinish>,
}

/// The output stage of one answer. The dialect calls [`token`](Self::token) for each
/// committed token until a step finishes the answer or the turn ends, then
/// [`finish`](Self::finish) once when the turn ended without failure.
pub trait AnswerStage: Send + 'static {
    /// One committed token.
    fn token(&mut self, token: &CommittedToken) -> Result<StageStep, InferenceError>;

    /// The turn ended: the events of the text still held (a possible start of a stop
    /// text that never completed).
    fn finish(&mut self) -> Result<Vec<AnswerEvent>, InferenceError>;
}

/// What the output stage of one request needs to know.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct OutputSpec {
    /// The template opened a reasoning block (always false in M1).
    pub thinking: bool,
    /// The logprobs asked for: `Some(n)` with `n` alternatives a token.
    pub logprobs: Option<u8>,
    /// The client's own stop strings (`stop`), at most 16.
    pub client_stops: Vec<String>,
}

/// Starts the output stage of each request. M2's output pipeline replaces
/// [`PlainOutput`] here.
pub trait OutputPipeline: Send + Sync + 'static {
    /// The stage of one answer.
    fn stage(&self, spec: &OutputSpec) -> Box<dyn AnswerStage>;

    /// The token ids that end an answer wherever they come (the end-of-turn markers), for
    /// the engine's stop hint.
    fn stop_ids(&self) -> Vec<u32>;

    /// The ids `ignore_eos` bans: the stop ids and the end-of-sequence ids.
    ///
    /// Behavior reference: project-maya serve/server.py:2519 at 7e68a30f.
    fn end_ids(&self) -> Vec<u32>;
}

/// The tokenizer's end-of-turn markers, as the donor's `Service` computes them: the stop
/// ids are the markers that are one special token each; the stop texts are the markers
/// whose spelled-out form also ends the text; the end-of-sequence ids are the tokenizer's
/// named `eos`, else every stop id.
///
/// Behavior reference: project-maya serve/server.py:2442-2477 at 7e68a30f.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct StopMarkers {
    /// Ids that end the answer, sorted.
    pub stop_ids: Vec<u32>,
    /// Texts that end the answer, in the donor's order.
    pub stop_texts: Vec<String>,
    /// The ids the engine itself ends at, sorted.
    pub eos_ids: Vec<u32>,
}

/// The markers whose single special token ends an answer.
///
/// Behavior reference: project-maya serve/server.py:2447-2452 at 7e68a30f.
const STOP_ID_MARKERS: [&str; 8] = [
    "<|im_end|>",
    "<|endoftext|>",
    "<|user|>",
    "<|observation|>",
    "<\u{ff5c}end\u{2581}of\u{2581}sentence\u{ff5c}>",
    "<\u{ff5c}User\u{ff5c}>",
    "[e~[",
    "]~b]",
];

/// The markers whose spelled-out text also ends an answer.
///
/// Behavior reference: project-maya serve/server.py:2458-2460 at 7e68a30f.
const STOP_TEXT_MARKERS: [&str; 7] = [
    "<|user|>",
    "<|observation|>",
    "<|endoftext|>",
    "<\u{ff5c}end\u{2581}of\u{2581}sentence\u{ff5c}>",
    "<\u{ff5c}User\u{ff5c}>",
    "[e~[",
    "]~b]",
];

impl StopMarkers {
    /// The markers of `tok`.
    pub fn of(tok: &dyn Tokenize) -> Self {
        let single = |s: &str| -> Option<u32> {
            match tok.encode(s, true, &[]) {
                Ok(ids) if ids.len() == 1 => ids.first().copied(),
                _ => None,
            }
        };
        let mut stop_ids: Vec<u32> = STOP_ID_MARKERS.iter().filter_map(|s| single(s)).collect();
        stop_ids.sort_unstable();
        stop_ids.dedup();
        let stop_texts = STOP_TEXT_MARKERS
            .iter()
            .filter(|s| single(s).is_some())
            .map(|s| (*s).to_owned())
            .collect();
        let eos_ids = match tok.special_ids().get("eos").and_then(Value::as_u64) {
            Some(eos) => u32::try_from(eos).map(|e| vec![e]).unwrap_or_default(),
            None => stop_ids.clone(),
        };
        Self {
            stop_ids,
            stop_texts,
            eos_ids,
        }
    }
}

/// The M1 output pipeline over a tokenizer.
#[derive(Clone)]
pub struct PlainOutput {
    tok: Arc<dyn Tokenize + Send + Sync>,
    markers: StopMarkers,
}

impl std::fmt::Debug for PlainOutput {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("PlainOutput")
            .field("markers", &self.markers)
            .finish_non_exhaustive()
    }
}

impl PlainOutput {
    /// The plain pipeline over `tok`, with its end-of-turn markers.
    pub fn new(tok: Arc<dyn Tokenize + Send + Sync>) -> Self {
        let markers = StopMarkers::of(tok.as_ref());
        Self { tok, markers }
    }

    /// The markers in force.
    pub fn markers(&self) -> &StopMarkers {
        &self.markers
    }
}

impl OutputPipeline for PlainOutput {
    fn stage(&self, spec: &OutputSpec) -> Box<dyn AnswerStage> {
        let mut stops = self.markers.stop_texts.clone();
        stops.extend(spec.client_stops.iter().cloned());
        Box::new(PlainStage {
            tok: Arc::clone(&self.tok),
            detok: Detokenizer::new(Arc::clone(&self.tok)),
            stop_ids: self.markers.stop_ids.clone(),
            stops,
            n_top: spec.logprobs,
            held: String::new(),
            lp_wait: Vec::new(),
        })
    }

    fn stop_ids(&self) -> Vec<u32> {
        self.markers.stop_ids.clone()
    }

    fn end_ids(&self) -> Vec<u32> {
        let mut ids = self.markers.stop_ids.clone();
        ids.extend(self.markers.eos_ids.iter().copied());
        ids.sort_unstable();
        ids.dedup();
        ids
    }
}

/// The plain stage of one answer.
struct PlainStage {
    tok: Arc<dyn Tokenize + Send + Sync>,
    detok: Detokenizer<Arc<dyn Tokenize + Send + Sync>>,
    stop_ids: Vec<u32>,
    /// The stop texts, then the client's stop strings.
    stops: Vec<String>,
    n_top: Option<u8>,
    /// Text that may be the start of a stop text.
    held: String,
    /// Logprobs entries waiting for the next text.
    lp_wait: Vec<Value>,
}

impl PlainStage {
    /// The content event of `text` with the waiting entries (the donor's `with_lp` around
    /// `parser.feed`); none for empty text, which leaves the entries waiting.
    fn content(&mut self, text: String) -> Vec<AnswerEvent> {
        if text.is_empty() {
            return Vec::new();
        }
        let logprobs = std::mem::take(&mut self.lp_wait);
        vec![AnswerEvent::Content { text, logprobs }]
    }

    /// The held text, sent as it is: the run ended on what only looked like a stop
    /// text's start.
    fn flush_held(&mut self) -> Vec<AnswerEvent> {
        let held = std::mem::take(&mut self.held);
        self.content(held)
    }
}

/// The byte length of the longest tail of `held` that is a proper prefix of one of
/// `stops`: the text kept back because it could still grow into a stop text.
///
/// Only prefixes no longer than `held` can match, so the work per token is bounded by
/// `held`, not by the length of the client's stop strings.
fn kept_back(held: &str, stops: &[String]) -> usize {
    stops
        .iter()
        .flat_map(|s| {
            s.char_indices()
                .skip(1)
                .map(|(j, _)| j)
                .take_while(|&j| j <= held.len())
                .filter(|&j| s.get(..j).is_some_and(|p| held.ends_with(p)))
        })
        .max()
        .unwrap_or(0)
}

impl AnswerStage for PlainStage {
    fn token(&mut self, token: &CommittedToken) -> Result<StageStep, InferenceError> {
        let t = token.id;
        let text = self
            .detok
            .push(t)
            .map_err(|e| InferenceError::malformed(MalformedCategory::IndexError, e.to_string()))?;
        if self.stop_ids.contains(&t) {
            // The end of the turn: its own entry is never one. What only looked like a
            // stop text's start goes out as it is.
            return Ok(StageStep {
                events: self.flush_held(),
                finish: Some(CallerFinish::Stop),
            });
        }
        if let (Some(n_top), Some(lp)) = (self.n_top, &token.logprob) {
            self.lp_wait
                .push(logprob_entry(self.tok.as_ref(), t, lp, n_top));
        }
        let mut stopped = false;
        let out = if self.stops.is_empty() {
            text
        } else {
            self.held.push_str(&text);
            let hit = self
                .stops
                .iter()
                .filter(|s| s.len() <= self.held.len())
                .filter_map(|s| self.held.find(s.as_str()).map(|i| (i, s.as_str())))
                .min();
            match hit {
                Some((cut, _)) => {
                    let before = self.held.get(..cut).unwrap_or("").to_owned();
                    self.held.clear();
                    stopped = true;
                    if before.is_empty() {
                        // The stop text's own tokens: no text of the answer.
                        self.lp_wait.clear();
                    }
                    before
                }
                None => {
                    let k = kept_back(&self.held, &self.stops);
                    let split = self.held.len() - k;
                    let tail = self.held.split_off(split);
                    std::mem::replace(&mut self.held, tail)
                }
            }
        };
        let events = self.content(out);
        Ok(StageStep {
            events,
            finish: stopped.then_some(CallerFinish::Stop),
        })
    }

    fn finish(&mut self) -> Result<Vec<AnswerEvent>, InferenceError> {
        Ok(self.flush_held())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use console_core::engine::TokenLogprob;
    use console_tokenizer::byte_tok::ByteTokenizer;

    fn tok() -> Arc<dyn Tokenize + Send + Sync> {
        Arc::new(ByteTokenizer::new())
    }

    fn committed(index: u32, id: u32, lp: Option<f64>) -> CommittedToken {
        CommittedToken {
            index,
            position: u64::from(index),
            id,
            logprob: lp.map(|v| TokenLogprob {
                logprob: v,
                top: vec![(id, v)],
            }),
        }
    }

    /// Runs `ids` through a stage; returns the texts with their entry counts, and the
    /// finish with the index of the token that gave it.
    fn run(spec: &OutputSpec, ids: &[u32]) -> (Vec<(String, usize)>, Option<usize>) {
        let mut stage = PlainOutput::new(tok()).stage(spec);
        let mut out = Vec::new();
        let take = |evs: Vec<AnswerEvent>, out: &mut Vec<(String, usize)>| {
            for e in evs {
                if let AnswerEvent::Content { text, logprobs } = e {
                    out.push((text, logprobs.len()));
                }
            }
        };
        for (i, &id) in ids.iter().enumerate() {
            let lp = spec.logprobs.map(|_| -0.5);
            let step = stage
                .token(&committed(u32::try_from(i).unwrap_or(0), id, lp))
                .unwrap_or_default();
            take(step.events, &mut out);
            if step.finish.is_some() {
                return (out, Some(i));
            }
        }
        take(stage.finish().unwrap_or_default(), &mut out);
        (out, None)
    }

    fn ids(text: &str) -> Vec<u32> {
        text.bytes().map(u32::from).collect()
    }

    #[test]
    fn the_byte_tokenizer_markers() {
        let m = StopMarkers::of(&ByteTokenizer::new());
        assert_eq!(m.stop_ids, vec![257, 258]);
        assert_eq!(m.stop_texts, vec!["<|endoftext|>".to_owned()]);
        assert_eq!(m.eos_ids, vec![257]);
    }

    #[test]
    fn text_goes_out_as_it_comes_and_the_end_of_turn_stops_it() {
        let mut script = ids("hi");
        script.push(257);
        script.extend(ids("never"));
        let (out, finish) = run(&OutputSpec::default(), &script);
        assert_eq!(out, vec![("h".to_owned(), 0), ("i".to_owned(), 0)]);
        assert_eq!(finish, Some(2));
    }

    #[test]
    fn a_split_character_waits_and_its_entries_wait_with_it() {
        let spec = OutputSpec {
            logprobs: Some(1),
            ..OutputSpec::default()
        };
        let (out, finish) = run(&spec, &ids("a\u{e9}"));
        // "é" is two bytes: the first gives no text, so its entry rides with the second.
        assert_eq!(out, vec![("a".to_owned(), 1), ("\u{e9}".to_owned(), 2)]);
        assert_eq!(finish, None);
    }

    #[test]
    fn a_stop_text_ends_the_answer_before_it() {
        let spec = OutputSpec {
            client_stops: vec!["END".into()],
            logprobs: Some(0),
            ..OutputSpec::default()
        };
        let (out, finish) = run(&spec, &ids("abENDzz"));
        // "E" and "EN" are held back; at "END" the text before it goes out alone.
        assert_eq!(out, vec![("a".to_owned(), 1), ("b".to_owned(), 1)]);
        assert_eq!(finish, Some(4));
        // A stop text with nothing before it: its tokens' entries are dropped.
        let (out, finish) = run(&spec, &ids("END"));
        assert!(out.is_empty());
        assert_eq!(finish, Some(2));
        // The spelled-out end-of-text marker is a stop text of the byte tokenizer.
        let (out, finish) = run(&OutputSpec::default(), &ids("ok<|endoftext|>more"));
        assert_eq!(out, vec![("o".to_owned(), 0), ("k".to_owned(), 0)]);
        assert_eq!(finish, Some(14));
    }

    #[test]
    fn held_text_goes_out_at_the_end_or_at_the_end_of_turn() {
        let spec = OutputSpec {
            client_stops: vec!["STOP".into()],
            ..OutputSpec::default()
        };
        let (out, finish) = run(&spec, &ids("xST"));
        assert_eq!(out, vec![("x".to_owned(), 0), ("ST".to_owned(), 0)]);
        assert_eq!(finish, None);
        let mut script = ids("xS");
        script.push(257);
        let (out, finish) = run(&spec, &script);
        assert_eq!(out, vec![("x".to_owned(), 0), ("S".to_owned(), 0)]);
        assert_eq!(finish, Some(2));
        // The held text stops being held once it can no longer grow into a stop text.
        let (out, _) = run(&spec, &ids("STx"));
        assert_eq!(out, vec![("STx".to_owned(), 0)]);
    }

    #[test]
    fn the_earliest_stop_wins_and_the_tail_is_kept_back() {
        let spec = OutputSpec {
            client_stops: vec!["bc".into(), "b".into(), "cd".into()],
            ..OutputSpec::default()
        };
        let (out, finish) = run(&spec, &ids("abcd"));
        assert_eq!(out, vec![("a".to_owned(), 0)]);
        assert_eq!(finish, Some(1));
        assert_eq!(kept_back("xyEN", &["END".to_owned()]), 2);
        assert_eq!(kept_back("xy", &["END".to_owned()]), 0);
    }

    #[test]
    fn long_stop_strings_cost_the_held_text_not_their_length() {
        // 16 stop strings of 1 MiB each: the scan per token is bounded by the held text.
        let long = |c: char| -> String {
            let mut s = "ab".to_owned();
            s.extend(std::iter::repeat_n(c, 1 << 20));
            s
        };
        let client_stops: Vec<String> = "cdefghijklmnopqr".chars().map(long).collect();
        let spec = OutputSpec {
            client_stops,
            ..OutputSpec::default()
        };
        let script = "Thinking about it. Hello from the mock engine, with an ab in it.";
        let started = std::time::Instant::now();
        let (out, finish) = run(&spec, &ids(script));
        assert!(
            started.elapsed() < std::time::Duration::from_secs(1),
            "{:?}",
            started.elapsed()
        );
        let text: String = out.into_iter().map(|(t, _)| t).collect();
        assert_eq!(text, script);
        assert_eq!(finish, None);
        // The prefix of a long stop string is still kept back.
        assert_eq!(kept_back("xab", &[long('c')]), 2);
    }
}
