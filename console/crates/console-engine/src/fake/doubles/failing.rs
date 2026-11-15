//! Provenance: translated from project-maya serve/test_server.py::DyingEngine, serve/test_server.py::NonFiniteEngine, serve/test_server.py::NonFiniteRetry::test_other_errors_are_not_retried (Broken), serve/test_server.py::EngineDeath::test_engine_err_mid_stream (ErrEngine) and serve/test_server.py::LiveRate::test_a_request_without_a_done_keeps_no_engine_counters (HalfDead) at 7e68a30f (MIT); license text in console/LICENSES/project-maya-MIT.txt.
//!
//! Doubles whose generation fails: the engine dies, reports an error, or raises at once.

use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Instant;

use console_core::engine::{
    ControlProbe, EngineDescriptor, EngineFactory, EngineFailure, EngineInstance, EngineKind,
    EngineStartConfig, EngineStop, EventSink, GenerationRequest, Health, ShutdownOutcome, Terminal,
};

use super::{DoubleHooks, Hooked};
use crate::fake::config::{FakeConfigError, FakeScript};
use crate::fake::deliver::{admitted, offer, prompt_tokens, Offer};
use crate::fake::lock;
use crate::fake::mock::{MockCore, MockHooks, MockParts};
use crate::fake::FakeProbe;

/// The donor's `NonFiniteEngine` error text, the engine's `ERR` when a route met a NaN.
///
/// Behavior reference: project-maya serve/test_server.py:947 at 7e68a30f.
pub const NON_FINITE_MESSAGE: &str =
    "glm router: layer 7 decode invalid expert ID or non-finite score";

/// The exit code the donor's dying doubles report.
const KILLED_EXIT_CODE: i32 = -9;

// ------------------------------------------------------------------------------ Dying

#[derive(Debug)]
struct DyingState {
    dead: bool,
    restarts: u32,
    die_after: Option<u32>,
}

/// Rust counterpart of the donor's `DyingEngine` (serve/test_server.py:912-931): the
/// scripted engine that dies after `die_after` tokens (5 by default) of its first answer,
/// with "the engine stopped unexpectedly (exit code -9)", reports itself ended, and comes
/// back when restarted: every start after the first is a restart, which clears the death
/// and the planned failure and is counted.
#[derive(Debug, Clone)]
pub struct DyingEngine {
    parts: MockParts,
    state: Arc<Mutex<DyingState>>,
}

impl DyingEngine {
    /// Dies after 5 tokens, as the donor's double does.
    pub fn new(script: FakeScript) -> Result<Self, FakeConfigError> {
        Ok(Self {
            parts: MockParts::new(script)?,
            state: Arc::new(Mutex::new(DyingState {
                dead: false,
                restarts: 0,
                die_after: Some(5),
            })),
        })
    }

    /// Dies after `k` tokens instead; `None` never dies.
    pub fn die_after(self, k: Option<u32>) -> Self {
        lock(&self.state).die_after = k;
        self
    }

    /// The donor's `restarts`.
    pub fn restarts(&self) -> u32 {
        lock(&self.state).restarts
    }

    /// The donor's `dead`.
    pub fn is_dead(&self) -> bool {
        lock(&self.state).dead
    }

    /// What the scripted engine recorded.
    pub fn probe(&self) -> FakeProbe {
        FakeProbe::from_shared(Arc::clone(&self.parts.shared))
    }
}

struct DyingHooks {
    state: Arc<Mutex<DyingState>>,
}

impl MockHooks for DyingHooks {
    fn at_step(&mut self, index: u32, _id: u32) -> Result<(), EngineFailure> {
        let mut s = lock(&self.state);
        if s.die_after == Some(index) {
            s.dead = true;
            return Err(EngineFailure::stopped_unexpectedly(Some(KILLED_EXIT_CODE)));
        }
        Ok(())
    }
}

impl DoubleHooks for DyingHooks {
    fn health(&mut self) -> Health {
        if lock(&self.state).dead {
            Health::Ended {
                exit_code: Some(KILLED_EXIT_CODE),
                note: None,
            }
        } else {
            Health::Alive
        }
    }

    fn shutdown(&mut self) -> ShutdownOutcome {
        if lock(&self.state).dead {
            ShutdownOutcome::AlreadyEnded
        } else {
            ShutdownOutcome::Graceful
        }
    }
}

impl EngineFactory for DyingEngine {
    fn kind(&self) -> EngineKind {
        EngineKind::Scripted
    }

    fn start(&self, cfg: &EngineStartConfig) -> Result<Box<dyn EngineInstance>, EngineFailure> {
        let (mut core, first) = self.parts.start(cfg)?;
        if !first {
            let mut s = lock(&self.state);
            s.dead = false;
            s.die_after = None;
            s.restarts = s.restarts.saturating_add(1);
        }
        core.desc.caps.lifecycle.restart = true;
        Ok(Box::new(Hooked {
            core,
            hooks: DyingHooks {
                state: Arc::clone(&self.state),
            },
        }))
    }
}

// -------------------------------------------------------------------------- NonFinite

/// Rust counterpart of the donor's `NonFiniteEngine` (serve/test_server.py:934-948): the
/// scripted engine whose `n`-th generation reports [`NON_FINITE_MESSAGE`] after
/// `fail[n]` tokens (`None`, or no entry: no failure). The failure is the engine's own
/// error report (`Reported`), not a death.
#[derive(Debug, Clone)]
pub struct NonFiniteEngine {
    parts: MockParts,
    fail: Arc<[Option<u32>]>,
    calls: Arc<AtomicU64>,
}

impl NonFiniteEngine {
    /// `fail` lists, per generation, after how many tokens it fails.
    pub fn new(script: FakeScript, fail: Vec<Option<u32>>) -> Result<Self, FakeConfigError> {
        Ok(Self {
            parts: MockParts::new(script)?,
            fail: Arc::from(fail),
            calls: Arc::new(AtomicU64::new(0)),
        })
    }

    /// The donor's `calls`: generations started.
    pub fn calls(&self) -> u64 {
        self.calls.load(Ordering::SeqCst)
    }

    /// What the scripted engine recorded.
    pub fn probe(&self) -> FakeProbe {
        FakeProbe::from_shared(Arc::clone(&self.parts.shared))
    }
}

struct NonFiniteHooks {
    fail: Arc<[Option<u32>]>,
    calls: Arc<AtomicU64>,
    at: Option<u32>,
}

impl MockHooks for NonFiniteHooks {
    fn on_generate(&mut self, _req: &GenerationRequest) {
        let n = self.calls.fetch_add(1, Ordering::SeqCst);
        self.at = usize::try_from(n)
            .ok()
            .and_then(|n| self.fail.get(n).copied().flatten());
    }

    fn at_step(&mut self, index: u32, _id: u32) -> Result<(), EngineFailure> {
        if self.at == Some(index) {
            return Err(EngineFailure::reported(NON_FINITE_MESSAGE));
        }
        Ok(())
    }
}

impl DoubleHooks for NonFiniteHooks {}

impl EngineFactory for NonFiniteEngine {
    fn kind(&self) -> EngineKind {
        EngineKind::Scripted
    }

    fn start(&self, cfg: &EngineStartConfig) -> Result<Box<dyn EngineInstance>, EngineFailure> {
        let (core, _) = self.parts.start(cfg)?;
        Ok(Box::new(Hooked {
            core,
            hooks: NonFiniteHooks {
                fail: Arc::clone(&self.fail),
                calls: Arc::clone(&self.calls),
                at: None,
            },
        }))
    }
}

// --------------------------------------------------------------------------- HalfDead

/// Rust counterpart of the donor's `HalfDead` (serve/test_server.py:1387-1395): the
/// scripted engine that dies at its fourth token (index 3) of every answer with "the
/// engine stopped unexpectedly (exit code -9)". The donor's double also carries a
/// previous request's `last` figures, to show they are not taken for this request's; here
/// figures belong to their call, so there are none to carry.
#[derive(Debug, Clone)]
pub struct HalfDeadEngine {
    parts: MockParts,
    die_at: u32,
}

impl HalfDeadEngine {
    /// Dies at index 3, as the donor's double does.
    pub fn new(script: FakeScript) -> Result<Self, FakeConfigError> {
        Ok(Self {
            parts: MockParts::new(script)?,
            die_at: 3,
        })
    }

    /// What the scripted engine recorded.
    pub fn probe(&self) -> FakeProbe {
        FakeProbe::from_shared(Arc::clone(&self.parts.shared))
    }
}

struct HalfDeadHooks {
    die_at: u32,
}

impl MockHooks for HalfDeadHooks {
    fn at_step(&mut self, index: u32, _id: u32) -> Result<(), EngineFailure> {
        if index == self.die_at {
            return Err(EngineFailure::stopped_unexpectedly(Some(KILLED_EXIT_CODE)));
        }
        Ok(())
    }
}

impl DoubleHooks for HalfDeadHooks {}

impl EngineFactory for HalfDeadEngine {
    fn kind(&self) -> EngineKind {
        EngineKind::Scripted
    }

    fn start(&self, cfg: &EngineStartConfig) -> Result<Box<dyn EngineInstance>, EngineFailure> {
        let (core, _) = self.parts.start(cfg)?;
        Ok(Box::new(Hooked {
            core,
            hooks: HalfDeadHooks {
                die_at: self.die_at,
            },
        }))
    }
}

// ------------------------------------------------------------------- Err and Broken

/// A scripted engine whose every generation raises `message`, after `Admitted` or before.
struct Raising {
    core: MockCore,
    calls: Arc<AtomicU64>,
    message: Arc<str>,
    admit: bool,
}

impl EngineInstance for Raising {
    fn descriptor(&self) -> &EngineDescriptor {
        &self.core.desc
    }

    fn generate(
        &mut self,
        req: &GenerationRequest,
        control: &ControlProbe,
        sink: &mut dyn EventSink,
    ) -> Result<Terminal, EngineFailure> {
        self.core.refresh();
        if self.core.desc.is_starting() {
            return Err(EngineFailure::not_ready());
        }
        let n_prompt = prompt_tokens(&req.prompt)?;
        self.calls.fetch_add(1, Ordering::SeqCst);
        if self.admit && offer(sink, control, admitted(n_prompt)) == Offer::Gone {
            return Ok(Terminal::bare(EngineStop::Cancelled));
        }
        Err(EngineFailure::reported(&self.message))
    }

    fn health(&mut self) -> Health {
        self.core.refresh();
        Health::Alive
    }

    fn shutdown(self: Box<Self>, _deadline: Instant) -> ShutdownOutcome {
        ShutdownOutcome::Graceful
    }
}

/// Rust counterpart of the donor's `ErrEngine` (serve/test_server.py:1099-1102): every
/// generation is admitted (the donor's double yields a heartbeat first, so the stream has
/// started) and then reports "verify: layer 31 never rang (an illegal memory access was
/// encountered)", with no token.
#[derive(Debug, Clone)]
pub struct ErrEngine {
    parts: MockParts,
    calls: Arc<AtomicU64>,
    message: Arc<str>,
}

impl ErrEngine {
    /// The donor's message.
    pub fn new(script: FakeScript) -> Result<Self, FakeConfigError> {
        Ok(Self {
            parts: MockParts::new(script)?,
            calls: Arc::new(AtomicU64::new(0)),
            message: Arc::from(
                "verify: layer 31 never rang (an illegal memory access was encountered)",
            ),
        })
    }

    /// Another error text.
    pub fn with_message(mut self, message: &str) -> Self {
        self.message = Arc::from(message);
        self
    }

    /// Generations started.
    pub fn calls(&self) -> u64 {
        self.calls.load(Ordering::SeqCst)
    }
}

impl EngineFactory for ErrEngine {
    fn kind(&self) -> EngineKind {
        EngineKind::Scripted
    }

    fn start(&self, cfg: &EngineStartConfig) -> Result<Box<dyn EngineInstance>, EngineFailure> {
        Ok(Box::new(Raising {
            core: self.parts.start(cfg)?.0,
            calls: Arc::clone(&self.calls),
            message: Arc::clone(&self.message),
            admit: true,
        }))
    }
}

/// Rust counterpart of the donor's `Broken` (serve/test_server.py:984-990): every
/// generation reports "verify: layer 31 never rang" at once, before anything is
/// delivered, and is counted.
#[derive(Debug, Clone)]
pub struct BrokenEngine {
    parts: MockParts,
    calls: Arc<AtomicU64>,
}

impl BrokenEngine {
    /// The donor's double.
    pub fn new(script: FakeScript) -> Result<Self, FakeConfigError> {
        Ok(Self {
            parts: MockParts::new(script)?,
            calls: Arc::new(AtomicU64::new(0)),
        })
    }

    /// The donor's `Broken.calls`.
    pub fn calls(&self) -> u64 {
        self.calls.load(Ordering::SeqCst)
    }
}

impl EngineFactory for BrokenEngine {
    fn kind(&self) -> EngineKind {
        EngineKind::Scripted
    }

    fn start(&self, cfg: &EngineStartConfig) -> Result<Box<dyn EngineInstance>, EngineFailure> {
        Ok(Box::new(Raising {
            core: self.parts.start(cfg)?.0,
            calls: Arc::clone(&self.calls),
            message: Arc::from("verify: layer 31 never rang"),
            admit: false,
        }))
    }
}

#[cfg(test)]
mod tests {
    use console_core::engine::{EngineEvent, FailureKind};

    use super::*;
    use crate::fake::testutil::{req, run};

    fn script(n: u32) -> FakeScript {
        FakeScript::new((100..100 + n).collect())
    }

    #[test]
    fn fake_dying_dies_once_and_comes_back_after_a_restart() {
        let f = DyingEngine::new(script(20)).expect("valid");
        let mut e = f.start(&EngineStartConfig::new()).expect("starts");
        assert!(e.descriptor().caps.lifecycle.restart);
        assert_eq!(e.health(), Health::Alive);
        let (sink, out) = run(e.as_mut(), &req(vec![1, 2], 50));
        let err = out.unwrap_err();
        assert_eq!(err.kind, FailureKind::Died);
        assert!(err.poisoned);
        assert_eq!(
            err.to_string(),
            "the engine stopped unexpectedly (exit code -9)"
        );
        assert_eq!(err.after_tokens, 5);
        assert_eq!(sink.tokens(), vec![100, 101, 102, 103, 104]);
        assert!(f.is_dead());
        assert_eq!(
            e.health(),
            Health::Ended {
                exit_code: Some(-9),
                note: None
            }
        );
        assert_eq!(e.shutdown(Instant::now()), ShutdownOutcome::AlreadyEnded);
        let mut again = f.start(&EngineStartConfig::new()).expect("restarts");
        assert_eq!(f.restarts(), 1);
        assert!(!f.is_dead());
        let (sink, out) = run(again.as_mut(), &req(vec![1, 2], 50));
        let (_, counts) = out.expect("answers in full after the restart");
        assert_eq!(counts.completion_tokens, 20);
        assert_eq!(sink.tokens().len(), 20);
    }

    #[test]
    fn fake_non_finite_fails_per_call_as_listed() {
        let f = NonFiniteEngine::new(script(10), vec![Some(0), None, Some(4)]).expect("valid");
        let mut e = f.start(&EngineStartConfig::new()).expect("starts");
        let (sink, out) = run(e.as_mut(), &req(vec![1], 200));
        let err = out.unwrap_err();
        assert_eq!(err.kind, FailureKind::Reported);
        assert!(!err.poisoned);
        assert!(err.to_string().contains("non-finite"));
        assert_eq!(err.to_string(), NON_FINITE_MESSAGE);
        assert!(sink.tokens().is_empty(), "before the first token");
        let (sink, out) = run(e.as_mut(), &req(vec![1], 200));
        assert!(out.is_ok());
        assert_eq!(sink.tokens().len(), 10);
        let (sink, out) = run(e.as_mut(), &req(vec![1], 200));
        assert_eq!(out.unwrap_err().after_tokens, 4);
        assert_eq!(sink.tokens().len(), 4);
        // No entry: no failure.
        let (_, out) = run(e.as_mut(), &req(vec![1], 200));
        assert!(out.is_ok());
        assert_eq!(f.calls(), 4);
    }

    #[test]
    fn fake_half_dead_dies_at_its_fourth_token_with_no_figures() {
        let f = HalfDeadEngine::new(script(40).tok_s(None)).expect("valid");
        let mut e = f.start(&EngineStartConfig::new()).expect("starts");
        let (sink, out) = run(e.as_mut(), &req(vec![1], 40));
        let err = out.unwrap_err();
        assert_eq!(err.kind, FailureKind::Died);
        assert_eq!(err.after_tokens, 3);
        assert_eq!(sink.tokens().len(), 3);
    }

    #[test]
    fn fake_err_engine_reports_after_admission_and_broken_before() {
        let f = ErrEngine::new(script(5)).expect("valid");
        let mut e = f.start(&EngineStartConfig::new()).expect("starts");
        let (sink, out) = run(e.as_mut(), &req(vec![1, 2, 3], 20));
        let err = out.unwrap_err();
        assert_eq!(err.kind, FailureKind::Reported);
        assert!(err.to_string().contains("illegal memory access"));
        assert_eq!(
            sink.events,
            vec![EngineEvent::Admitted {
                prompt_tokens: 3,
                reused_tokens: None
            }]
        );
        assert_eq!(f.calls(), 1);

        let b = BrokenEngine::new(script(1)).expect("valid");
        let mut e = b.start(&EngineStartConfig::new()).expect("starts");
        let (sink, out) = run(e.as_mut(), &req(vec![1], 20));
        assert_eq!(out.unwrap_err().to_string(), "verify: layer 31 never rang");
        assert!(sink.events.is_empty());
        assert_eq!(b.calls(), 1);
    }
}
