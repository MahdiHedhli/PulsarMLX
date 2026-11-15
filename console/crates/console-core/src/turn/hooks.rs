//! The turn driver's two hooks: [`TurnObserver`] for the status and history the monitoring
//! owner keeps, and [`ContinuationPolicy`] for the server-side continuations of ENG-11.
//! Both have inert defaults, so the driver works without either.

use std::sync::Arc;

use crate::engine::{EngineSample, EngineStop};

use super::figures::{RequestTimings, SegmentFigures};

/// The phase a turn reports when it starts on the engine.
///
/// Behavior reference: project-maya serve/server.py:4371 at 7e68a30f.
pub const PHASE_READING_THE_PROMPT: &str = "reading the prompt";

/// What a turn reports when it starts on the engine (the donor's `status.update(busy=True,
/// phase=..., prompt_tokens=..., generated=0, max_tokens=...)`).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TurnStart {
    /// [`PHASE_READING_THE_PROMPT`]. Later phases (thinking, answering, a tool call) are
    /// set by the event layer; text that comes from the engine is made log-safe by whoever
    /// sets it (LD35).
    pub phase: &'static str,
    /// The prompt length.
    pub prompt_tokens: u32,
    /// The request's answer budget after the context rule.
    pub max_tokens: u32,
}

/// One finished turn that reached the engine, for the history and the totals (the donor
/// writes these rows only for a request that was counted active).
#[derive(Debug, Clone, PartialEq)]
pub struct TurnRecord {
    /// The donor's finish word: `stop`, `length`, `cancel`, `error` or `disconnect`.
    pub finish: &'static str,
    /// The prompt length.
    pub prompt_tokens: u32,
    /// The tokens the request took.
    pub output_tokens: u32,
    /// The cancel was set when the turn ended.
    pub cancelled: bool,
    /// This request's engine figures (`None`: no `DONE` arrived for it).
    pub figures: Option<SegmentFigures>,
    /// This request's timings (`None`: the engine keeps no clock).
    pub timings: Option<RequestTimings>,
}

/// Status hooks of a turn, implemented by the monitoring owner. Every method has an empty
/// default. Calls come from the turn's task and from the consumer's
/// [`TurnStream`](super::TurnStream), never from the engine's driver thread, and they must
/// not block.
///
/// Behavior reference: project-maya serve/server.py:4337-4378, 4721-4769 at 7e68a30f.
pub trait TurnObserver: Send + Sync + 'static {
    /// The turn joined the FIFO (`status["queued"] += 1`).
    fn queued(&self) {}
    /// The turn left the line, with its turn or without (`status["queued"] -= 1`).
    fn dequeued(&self) {}
    /// The turn starts on the engine (`busy`, phase, prompt tokens, `active += 1`).
    fn active(&self, _start: &TurnStart) {}
    /// Tokens generated so far by the running turn.
    fn generated(&self, _tokens: u32) {}
    /// A telemetry sample from the engine (`STAT`).
    fn sample(&self, _sample: &EngineSample) {}
    /// The turn's FIFO place was given back, after its last engine call returned.
    fn place_released(&self) {}
    /// The turn is no longer active (`active -= 1`).
    fn inactive(&self) {}
    /// The turn ended; called once for a turn that reached the engine.
    fn finished(&self, _record: &TurnRecord) {}
}

/// The observer that records nothing.
#[derive(Debug, Clone, Copy, Default)]
pub struct NoObserver;

impl TurnObserver for NoObserver {}

/// What one engine call of an attempt produced, for a [`ContinuationPolicy`].
#[derive(Debug, Clone, Copy)]
pub struct CallSummary<'a> {
    /// The request's own prompt.
    pub prompt: &'a [u32],
    /// Every token the engine produced for this request so far, over its calls and
    /// segments, in order (a segment's retried attempt drops what its failed attempt
    /// produced).
    pub produced: &'a [u32],
    /// How the call ended.
    pub stop: EngineStop,
    /// The request's answer budget.
    pub max_new: u32,
}

/// A [`ContinuationPolicy`]'s decision after an engine call.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Continuation {
    /// The answer is complete.
    Finish,
    /// Call the engine again within the same attempt (a fair slice, the soft close of a
    /// thinking budget), still holding the place, with this prompt (normally the request's
    /// prompt and what it produced) and at most this many new tokens. The call shares the
    /// attempt's non-finite retry and token count, and its figures merge with the
    /// attempt's earlier calls (the donor's slices of one `_sliced` call).
    Again {
        /// The next call's whole prompt.
        prompt: Arc<[u32]>,
        /// The next call's budget, before the context's room caps it.
        max_new: u32,
    },
    /// Start a new segment (the call after a blocked loop-guard call), still holding the
    /// place: a fresh attempt over this prompt and budget, as the donor runs
    /// `attempts(seg["prompt"], ...)` afresh for each segment. A non-finite failure before
    /// the segment's first token runs this prompt and budget again; the segment's figures
    /// replace the earlier segment's.
    NextSegment {
        /// The segment's whole prompt.
        prompt: Arc<[u32]>,
        /// The segment's budget, before the context's room caps it.
        max_new: u32,
    },
}

/// Server-side continuations within one request (fair slices, the soft close of a thinking
/// budget, the loop guard's continuations): ENG-11 implements them over this hook. The
/// driver asks after every engine call that ended without failure, unless the turn was
/// cancelled or the server is stopping. It merges the figures of the calls of one attempt
/// as [`merge_segments`](super::merge_segments) does, and keeps only the last segment's.
///
/// Behavior reference: project-maya serve/server.py:4256-4267, 4433-4465 at 7e68a30f.
pub trait ContinuationPolicy: Send + 'static {
    /// Whether to call the engine again.
    fn after_call(&mut self, call: &CallSummary<'_>) -> Continuation;
}

/// The policy of M1: one engine call per attempt.
#[derive(Debug, Clone, Copy, Default)]
pub struct NoContinuation;

impl ContinuationPolicy for NoContinuation {
    fn after_call(&mut self, _call: &CallSummary<'_>) -> Continuation {
        Continuation::Finish
    }
}
