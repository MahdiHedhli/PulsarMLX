//! Engine factory, instance and lifecycle (contract sections 4 and 11).

use std::time::{Duration, Instant};

use super::control::ControlProbe;
use super::descriptor::EngineDescriptor;
use super::error::EngineFailure;
use super::event::{EngineSample, EventSink};
use super::ledger::{LedgerCounts, LedgeredSink};
use super::multi::MultiEngine;
use super::request::GenerationRequest;
use super::terminal::Terminal;
use super::text::BoundedText;
use super::EngineKind;

/// Settings for one engine start. More settings are added by the packages that need them
/// (ENG-06, ENG-12, ENG-15), so it is built with [`EngineStartConfig::new`].
#[derive(Debug, Clone, PartialEq, Eq, Default)]
#[non_exhaustive]
pub struct EngineStartConfig {
    /// The context to start with; `None` keeps the engine's own choice. A context reload
    /// is a shutdown followed by a start with the new context (FIX-1.1).
    pub context: Option<u32>,
}

impl EngineStartConfig {
    /// The default start settings.
    pub fn new() -> Self {
        Self::default()
    }

    /// The same settings with `context`.
    pub fn with_context(mut self, context: u32) -> Self {
        self.context = Some(context);
        self
    }
}

/// Whether an engine instance still runs (the donor's `alive()`, `exit_code()` and
/// `death_note()`).
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Health {
    /// Running.
    Alive,
    /// Ended.
    Ended {
        /// The exit code, when known.
        exit_code: Option<i32>,
        /// Why it most likely ended.
        note: Option<BoundedText>,
    },
}

/// One control line between generations (the donor's `command(line, expect, timeout)`).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ControlCommand {
    /// The line to write, without its newline.
    pub line: String,
    /// The prefix of the answer line.
    pub expect: String,
    /// How long to wait for the answer.
    pub timeout: Duration,
}

/// Why a request runs on one GPU alone on a mixed-GPU engine.
///
/// Behavior reference: project-maya serve/server.py:2620-2630 at 7e68a30f.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AloneReason {
    /// The request has pictures.
    Pictures,
    /// The request asks for logprobs.
    Logprobs,
    /// The request uses refusal ablation (never true in this increment, POL-1).
    Ablation,
}

impl AloneReason {
    /// The donor's text for the reason.
    pub fn as_str(self) -> &'static str {
        match self {
            AloneReason::Pictures => "has pictures",
            AloneReason::Logprobs => "asks for log-probabilities",
            AloneReason::Ablation => "uses refusal ablation",
        }
    }
}

/// How a shutdown ended.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ShutdownOutcome {
    /// The engine ended by itself within the deadline.
    Graceful,
    /// The engine was killed at the deadline.
    Killed,
    /// The engine had already ended.
    AlreadyEnded,
}

/// Starts engine instances. `Send + Sync`, so the server can hold it anywhere; `start` is
/// called on the driver thread and the instance never leaves that thread.
pub trait EngineFactory: Send + Sync + 'static {
    /// The kind of engine this factory starts.
    fn kind(&self) -> EngineKind;

    /// Called on the driver thread. The returned instance never leaves it. The caller
    /// passes the descriptor to [`require_synthetic`](super::require_synthetic) before the
    /// instance serves a request.
    fn start(&self, cfg: &EngineStartConfig) -> Result<Box<dyn EngineInstance>, EngineFailure>;
}

/// A started engine. Deliberately neither `Send` nor `Sync`: it is created on, and owned
/// by, one driver thread, and every call happens there, one at a time.
pub trait EngineInstance {
    /// What the engine is and can do.
    fn descriptor(&self) -> &EngineDescriptor;

    /// Blocks until the generation ends. Delivers `Admitted`, then tokens in index order
    /// (an exact repeat of the last one is allowed), then returns exactly one terminal or
    /// one failure. Reads `control` between steps.
    fn generate(
        &mut self,
        req: &GenerationRequest,
        control: &ControlProbe,
        sink: &mut dyn EventSink,
    ) -> Result<Terminal, EngineFailure>;

    /// The submit-and-pump form, for an engine with more than one place (`multi=<n>`).
    /// `None` (the default) for a single-conversation engine.
    fn multi(&mut self) -> Option<&mut dyn MultiEngine> {
        None
    }

    /// Polled by the driver between generations.
    fn sample(&mut self) -> Option<EngineSample> {
        None
    }

    /// Whether the engine still runs.
    fn health(&mut self) -> Health {
        Health::Alive
    }

    /// A control line between generations (`VLEND` / `VRECLAIM`). Needs
    /// `caps.lifecycle.lend`.
    fn command(&mut self, _cmd: &ControlCommand) -> Result<String, EngineFailure> {
        Err(EngineFailure::unsupported("command"))
    }

    /// Mixed-GPU layout before a call. Default: nothing to do.
    fn use_layout(&mut self, _alone: Option<AloneReason>) -> Result<(), EngineFailure> {
        Ok(())
    }

    /// Graceful end: stop a running generation, quit, wait up to `deadline`, then kill.
    fn shutdown(self: Box<Self>, deadline: Instant) -> ShutdownOutcome;
}

/// One generation through the ledger: refuses at once with
/// [`EngineFailure::not_ready`] when `max_context` is 0 (nothing is sent to the engine),
/// else calls `generate` with a [`LedgeredSink`] in front of `downstream` and returns the
/// terminal with the ledger's figures. A ledger failure replaces whatever the engine
/// returned.
pub fn generate_ledgered(
    engine: &mut dyn EngineInstance,
    req: &GenerationRequest,
    control: &ControlProbe,
    downstream: &mut dyn EventSink,
) -> Result<(Terminal, LedgerCounts), EngineFailure> {
    if engine.descriptor().is_starting() {
        return Err(EngineFailure::not_ready());
    }
    let mut sink = LedgeredSink::new(req, engine.descriptor(), downstream);
    let result = engine.generate(req, control, &mut sink);
    sink.finish(result)
}
