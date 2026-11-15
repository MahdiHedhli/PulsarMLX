//! Owned by ENG-10. The engine turn driver: place, engine start, engine calls, drain,
//! context rule, error classification, non-finite retry and figures.
//!
//! [`TurnDriver`] owns the engine's driver thread (contract section 4): the engine instance
//! is started on it, lives on it and is called only there, one call at a time, while async
//! request tasks reach it through a job channel. Each [`TurnDriver::turn`] runs in its own
//! task, which takes a FIFO place, makes sure the engine runs, calls it, and gives the
//! place back only after the engine call has really returned; the consumer reads the
//! turn's [`TurnItem`]s from a [`TurnStream`]. Dropping the stream sets the turn's cancel
//! and nothing else, so STOP, the drain and the release of the place still happen, in that
//! order.
//!
//! Every path that admits an engine (first start, restart, model switch, context reload,
//! and the start after an idle unload or a death) runs the admission step of the driver
//! thread, which calls [`require_synthetic`](crate::engine::require_synthetic) before the
//! engine serves a request. A refused engine is shut down and the operation fails with
//! [`ProvenanceRefused::to_failure`](crate::engine::ProvenanceRefused::to_failure); nothing
//! is served from it. No setting, flag or feature skips the call. Nothing here is qualified
//! beyond synthetic backends.
//!
//! The driver works on token ids and on the seam's events: stop detection, parsing and
//! detokenization belong to its caller, which also decides the finish
//! ([`TurnStream::finish`]). Errors are [`TurnError`]s, built from the seam's
//! [`EngineFailure`](crate::engine::EngineFailure) and the request module's
//! [`RequestError`](crate::request::RequestError); `console-http` maps them to bodies.
//!
//! Behavior reference: project-maya serve/server.py:163, 431-432, 2639-2661, 3680-3694,
//! 4097-4126, 4256-4271, 4273-4307, 4340-4378, 4433-4454, 4491-4496, 4657-4793, 5011-5016
//! at 7e68a30f.

mod context;
mod driver;
mod error;
mod figures;
mod hooks;
mod host;
mod log;
mod stream;

pub use context::{call_budget, context_rule};
pub use driver::{TurnDriver, TurnRequest, TurnSettings, HEARTBEAT, TURN_CHANNEL_CAPACITY};
pub use error::{is_non_finite, TurnError, NONFINITE, STARTING_MESSAGE, STOPPING_MESSAGE};
pub use figures::{
    merge_segments, own_prompt_figures, request_figures, request_timings, RequestTimings,
    SegmentFigures,
};
pub use hooks::{
    CallSummary, Continuation, ContinuationPolicy, NoContinuation, NoObserver, TurnObserver,
    TurnRecord, TurnStart, PHASE_READING_THE_PROMPT,
};
pub use host::{ENGINE_CLOSE_WAIT, ENGINE_PANICKED};
pub use log::log_safe;
pub use stream::{CallerFinish, PingProgress, TurnEnd, TurnItem, TurnOutcome, TurnStream};
