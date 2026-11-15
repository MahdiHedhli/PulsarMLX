//! Provenance: translated from project-maya serve/test_server.py::LifecycleEngine and serve/test_server.py::HeldEngine at 7e68a30f (MIT); license text in console/LICENSES/project-maya-MIT.txt.
//!
//! Doubles for the engine's lifecycle and for queue tests: an engine whose closes and
//! restarts are counted, and one that holds its first request until it is released.

use std::sync::{Arc, Condvar, Mutex};
use std::time::Duration;

use console_core::engine::{
    ControlProbe, EngineFactory, EngineFailure, EngineInstance, EngineKind, EngineStartConfig,
    EventSink, GenerationRequest, Health, ShutdownOutcome,
};

use super::{DoubleHooks, Hooked};
use crate::fake::config::{FakeConfigError, FakeScript};
use crate::fake::lock;
use crate::fake::mock::{Flow, MockHooks, MockParts};
use crate::fake::FakeProbe;

// -------------------------------------------------------------------------- Lifecycle

#[derive(Debug)]
struct LifeState {
    running: bool,
    closes: u32,
    restarts: u32,
}

/// Rust counterpart of the donor's `LifecycleEngine` (serve/test_server.py:2166-2182): the
/// scripted engine with the line-protocol engine's lifecycle, counted. Its health is
/// `Alive` while it runs; a shutdown (the donor's `close()`, a `QUIT`) counts a close and
/// stops it; every start after the first (the donor's `restart()`) counts a restart and
/// runs it again. It supports restart and idle unload.
#[derive(Debug, Clone)]
pub struct LifecycleEngine {
    parts: MockParts,
    state: Arc<Mutex<LifeState>>,
}

impl LifecycleEngine {
    /// The donor's double, running.
    pub fn new(script: FakeScript) -> Result<Self, FakeConfigError> {
        Ok(Self {
            parts: MockParts::new(script)?,
            state: Arc::new(Mutex::new(LifeState {
                running: true,
                closes: 0,
                restarts: 0,
            })),
        })
    }

    /// The donor's `running`.
    pub fn is_running(&self) -> bool {
        lock(&self.state).running
    }

    /// Sets `running`, as an engine that ended by itself.
    pub fn set_running(&self, running: bool) {
        lock(&self.state).running = running;
    }

    /// The donor's `closes`.
    pub fn closes(&self) -> u32 {
        lock(&self.state).closes
    }

    /// The donor's `restarts`.
    pub fn restarts(&self) -> u32 {
        lock(&self.state).restarts
    }

    /// What the scripted engine recorded; it also sets the context the engine reports
    /// (the donor's tests assign `max_context = 0` for a start in progress).
    pub fn probe(&self) -> FakeProbe {
        FakeProbe::from_shared(Arc::clone(&self.parts.shared))
    }
}

struct LifeHooks {
    state: Arc<Mutex<LifeState>>,
}

impl MockHooks for LifeHooks {}

impl DoubleHooks for LifeHooks {
    fn health(&mut self) -> Health {
        if lock(&self.state).running {
            Health::Alive
        } else {
            Health::Ended {
                exit_code: None,
                note: None,
            }
        }
    }

    fn shutdown(&mut self) -> ShutdownOutcome {
        let mut s = lock(&self.state);
        s.closes = s.closes.saturating_add(1);
        let was = s.running;
        s.running = false;
        if was {
            ShutdownOutcome::Graceful
        } else {
            ShutdownOutcome::AlreadyEnded
        }
    }
}

impl EngineFactory for LifecycleEngine {
    fn kind(&self) -> EngineKind {
        EngineKind::Scripted
    }

    fn start(&self, cfg: &EngineStartConfig) -> Result<Box<dyn EngineInstance>, EngineFailure> {
        let (mut core, first) = self.parts.start(cfg)?;
        {
            let mut s = lock(&self.state);
            if !first {
                s.restarts = s.restarts.saturating_add(1);
            }
            s.running = true;
        }
        core.desc.caps.lifecycle.restart = true;
        core.desc.caps.lifecycle.unload = true;
        Ok(Box::new(Hooked {
            core,
            hooks: LifeHooks {
                state: Arc::clone(&self.state),
            },
        }))
    }
}

// ------------------------------------------------------------------------------- Held

/// How often a held generation looks at its cancel request (the donor's 0.05 s heartbeat
/// sleep). A release wakes it at once.
pub const HELD_POLL: Duration = Duration::from_millis(50);

#[derive(Debug, Default)]
struct HeldFlags {
    held: bool,
    released: bool,
    calls: u64,
}

#[derive(Debug, Default)]
struct HeldState {
    flags: Mutex<HeldFlags>,
    changed: Condvar,
}

/// Rust counterpart of the donor's `HeldEngine` (serve/test_server.py:2348-2361): the
/// first generation of the engine (across restarts) is admitted and then holds the engine
/// until [`release`](Self::release) is called or the generation is cancelled; the others
/// answer at once. While it holds, nothing is delivered (the donor's heartbeats are the
/// server's own here, contract section 7). After it is released or cancelled it goes on
/// as the scripted engine, which stops at once when cancelled.
#[derive(Debug, Clone)]
pub struct HeldEngine {
    parts: MockParts,
    state: Arc<HeldState>,
}

impl HeldEngine {
    /// The donor's double.
    pub fn new(script: FakeScript) -> Result<Self, FakeConfigError> {
        Ok(Self {
            parts: MockParts::new(script)?,
            state: Arc::new(HeldState::default()),
        })
    }

    /// Lets the held generation go on (the donor's `release.set()`).
    pub fn release(&self) {
        lock(&self.state.flags).released = true;
        self.state.changed.notify_all();
    }

    /// True once the first generation holds the engine (the donor's `held`).
    pub fn is_held(&self) -> bool {
        lock(&self.state.flags).held
    }

    /// Waits up to `timeout` for the first generation to hold the engine; true when it
    /// does.
    pub fn wait_held(&self, timeout: Duration) -> bool {
        let guard = lock(&self.state.flags);
        let (guard, _) = self
            .state
            .changed
            .wait_timeout_while(guard, timeout, |f| !f.held)
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        guard.held
    }

    /// The donor's `calls`: generations started.
    pub fn calls(&self) -> u64 {
        lock(&self.state.flags).calls
    }

    /// What the scripted engine recorded.
    pub fn probe(&self) -> FakeProbe {
        FakeProbe::from_shared(Arc::clone(&self.parts.shared))
    }
}

struct HeldHooks {
    state: Arc<HeldState>,
    first: bool,
}

impl MockHooks for HeldHooks {
    fn on_generate(&mut self, _req: &GenerationRequest) {
        let mut f = lock(&self.state.flags);
        f.calls = f.calls.saturating_add(1);
        self.first = f.calls == 1;
    }

    fn before_steps(
        &mut self,
        _prompt_tokens: u32,
        _sink: &mut dyn EventSink,
        control: &ControlProbe,
    ) -> Result<Flow, EngineFailure> {
        if !self.first {
            return Ok(Flow::Go);
        }
        let mut f = lock(&self.state.flags);
        f.held = true;
        self.state.changed.notify_all();
        while !f.released && !control.is_cancelled() {
            f = self
                .state
                .changed
                .wait_timeout(f, HELD_POLL)
                .map(|(g, _)| g)
                .unwrap_or_else(|e| e.into_inner().0);
        }
        // Then on as the scripted engine, whose first step reads the cancel request.
        Ok(Flow::Go)
    }
}

impl DoubleHooks for HeldHooks {}

impl EngineFactory for HeldEngine {
    fn kind(&self) -> EngineKind {
        EngineKind::Scripted
    }

    fn start(&self, cfg: &EngineStartConfig) -> Result<Box<dyn EngineInstance>, EngineFailure> {
        let (core, _) = self.parts.start(cfg)?;
        Ok(Box::new(Hooked {
            core,
            hooks: HeldHooks {
                state: Arc::clone(&self.state),
                first: false,
            },
        }))
    }
}

#[cfg(test)]
mod tests {
    use std::time::Instant;

    use console_core::engine::{generate_ledgered, ControlHandle, EngineStop};

    use super::*;
    use crate::fake::testutil::{req, run, Collect};

    #[test]
    fn fake_lifecycle_counts_closes_and_restarts() {
        let f = LifecycleEngine::new(FakeScript::new(vec![1, 2])).expect("valid");
        let mut e = f.start(&EngineStartConfig::new()).expect("starts");
        assert!(e.descriptor().caps.lifecycle.unload);
        assert!(e.descriptor().caps.lifecycle.restart);
        assert_eq!(e.health(), Health::Alive);
        assert_eq!(e.shutdown(Instant::now()), ShutdownOutcome::Graceful);
        assert_eq!((f.closes(), f.restarts(), f.is_running()), (1, 0, false));
        let mut e = f.start(&EngineStartConfig::new()).expect("restarts");
        assert_eq!((f.closes(), f.restarts(), f.is_running()), (1, 1, true));
        assert!(run(e.as_mut(), &req(vec![5], 8)).1.is_ok());
        f.set_running(false);
        assert_eq!(
            e.health(),
            Health::Ended {
                exit_code: None,
                note: None
            }
        );
        assert_eq!(e.shutdown(Instant::now()), ShutdownOutcome::AlreadyEnded);
        assert_eq!(f.closes(), 2);
    }

    #[test]
    fn fake_lifecycle_start_in_progress_is_not_ready() {
        let f = LifecycleEngine::new(FakeScript::new(vec![1, 2])).expect("valid");
        let mut e = f.start(&EngineStartConfig::new()).expect("starts");
        f.probe().set_max_context(Some(0));
        assert_eq!(e.health(), Health::Alive);
        assert!(e.descriptor().is_starting());
        let (sink, out) = run(e.as_mut(), &req(vec![5], 8));
        assert_eq!(
            out.unwrap_err().to_string(),
            "the model is starting; try again in a moment"
        );
        assert!(sink.events.is_empty());
        f.probe().set_max_context(None);
        assert_eq!(e.health(), Health::Alive);
        assert_eq!(e.descriptor().max_context, 32_768);
        assert!(run(e.as_mut(), &req(vec![5], 8)).1.is_ok());
    }

    #[test]
    fn fake_held_holds_the_first_request_until_released() {
        let f = HeldEngine::new(FakeScript::new(vec![7, 8, 9])).expect("valid");
        let worker = {
            let f = f.clone();
            std::thread::spawn(move || {
                let mut e = f.start(&EngineStartConfig::new()).expect("starts");
                let first = run(e.as_mut(), &req(vec![1], 8));
                let second = run(e.as_mut(), &req(vec![1], 8));
                (first.0.tokens(), first.1.is_ok(), second.0.tokens())
            })
        };
        assert!(
            f.wait_held(Duration::from_secs(10)),
            "the first request holds"
        );
        assert!(f.is_held());
        assert_eq!(f.calls(), 1);
        f.release();
        let (first, ok, second) = worker.join().expect("joins");
        assert!(ok);
        assert_eq!(first, vec![7, 8, 9]);
        assert_eq!(second, vec![7, 8, 9]);
        assert_eq!(f.calls(), 2);
    }

    #[test]
    fn fake_held_request_leaves_when_cancelled() {
        let f = HeldEngine::new(FakeScript::new(vec![7, 8, 9])).expect("valid");
        let h = ControlHandle::new();
        let worker = {
            let f = f.clone();
            let probe = h.probe();
            std::thread::spawn(move || {
                let mut e = f.start(&EngineStartConfig::new()).expect("starts");
                let mut sink = Collect::default();
                let out = generate_ledgered(e.as_mut(), &req(vec![1], 8), &probe, &mut sink);
                (sink.tokens(), out.map(|(t, _)| t.stop))
            })
        };
        assert!(f.wait_held(Duration::from_secs(10)));
        h.cancel();
        let (tokens, stop) = worker.join().expect("joins");
        assert!(tokens.is_empty());
        assert_eq!(stop, Ok(EngineStop::Cancelled));
    }
}
