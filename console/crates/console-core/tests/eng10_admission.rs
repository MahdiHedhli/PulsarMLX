//! ENG-10: the synthetic-only guard on every path of the turn driver that admits an engine
//! (contract section 5.1; owner decision of 2026-11-14 on OPEN-29, lead decision LD28).
//!
//! Each path is pinned with ENG-02's `NotSyntheticEngine`: its first `n` starts are the
//! synthetic scripted engine and every later start reports a provenance that is not
//! synthetic. On a refusal the engine is shut down, the operation fails with the failure
//! `ProvenanceRefused::to_failure` gives (the refusal line), and nothing is served from
//! that engine: its `generate` is never called. These tests must not be deleted or
//! weakened to make a real engine start (section 5.1, rule 5).

#[path = "eng10_helpers.rs"]
mod helpers;

use std::sync::atomic::{AtomicU32, Ordering};
use std::sync::Arc;
use std::time::Duration;

use console_core::engine::{
    require_synthetic, ControlProbe, EngineDescriptor, EngineFactory, EngineFailure,
    EngineInstance, EngineKind, EngineStartConfig, EventSink, FailureKind, GenerationRequest,
    Health, Provenance, ProvenanceRefused, ShutdownOutcome, Terminal,
    ALLOWING_NON_SYNTHETIC_ENGINES_PATH,
};
use console_core::fifo::{EngineFifo, FifoLog};
use console_core::request::pynum::PyInt;
use console_core::turn::{NoObserver, TurnDriver, TurnEnd, TurnError};
use console_engine::fake::doubles::NotSyntheticEngine;
use console_engine::fake::{FakeFactory, FakeScript};

use helpers::{answer, driver, enc, quiet_settings, read_turn, request, CTX, END};

const DECLARED: &str = "real-model-v1";

fn refusal_line(declared: Option<&str>) -> String {
    ProvenanceRefused {
        kind: EngineKind::Scripted,
        reported: Provenance::not_synthetic(declared),
    }
    .to_string()
}

fn script() -> FakeScript {
    FakeScript::new(answer("served"))
        .max_context(CTX)
        .reload_delay(Duration::ZERO)
}

/// An engine whose first start is synthetic and every later start is refused.
fn one_synthetic_start() -> NotSyntheticEngine {
    NotSyntheticEngine::after_synthetic_starts(script(), 1, DECLARED)
        .unwrap_or_else(|e| panic!("{e}"))
}

fn assert_refused(err: &TurnError) {
    let f = err
        .engine_failure()
        .unwrap_or_else(|| panic!("not an engine failure: {err:?}"));
    assert_eq!(f.kind, FailureKind::StartFailed);
    assert!(f.poisoned);
    assert_eq!(f.message.as_str(), refusal_line(Some(DECLARED)));
    assert!(f
        .message
        .as_str()
        .contains(ALLOWING_NON_SYNTHETIC_ENGINES_PATH));
}

/// The server's flow for a request: the context rule first, then the turn. The context
/// rule must let the request through, so that its turn reaches the start (and the guard).
fn budget(d: &TurnDriver) -> u32 {
    let prompt = enc("hi");
    d.context_budget(prompt.len(), Some(&PyInt::from_i64(20)))
        .unwrap_or_else(|e| panic!("the context rule refused the request: {e}"))
}

/// A turn on a driver whose engine is refused: it passes the context rule, fails with the
/// refusal, and nothing is served.
async fn assert_turn_refused(d: &TurnDriver) {
    let max_new = budget(d);
    let read = read_turn(d.turn(request(&enc("hi"), max_new)), &[END]).await;
    assert!(read.tokens.is_empty());
    match &read.outcome.end {
        TurnEnd::Failed(e) => assert_refused(e),
        other => panic!("expected the refusal, got {other:?}"),
    }
    assert_eq!(read.outcome.finish, "error");
}

/// The first turn, served by the synthetic first start.
async fn assert_served(d: &TurnDriver) {
    let max_new = budget(d);
    let read = read_turn(d.turn(request(&enc("hi"), max_new)), &[END]).await;
    assert_eq!(read.text(), "served");
    assert_eq!(read.outcome.finish, "stop");
}

#[tokio::test(start_paused = true)]
async fn the_first_start_refuses_an_engine_that_is_not_synthetic() {
    for (engine, declared) in [
        (NotSyntheticEngine::declaring(DECLARED), Some(DECLARED)),
        (NotSyntheticEngine::undeclared(), None),
    ] {
        let (log, cap) = FifoLog::capture();
        let started = TurnDriver::start(
            Arc::new(engine.clone()),
            EngineFifo::with_log(1, log.clone()),
            quiet_settings(),
            Arc::new(NoObserver),
            log,
        )
        .await;
        let err = match started {
            Ok(_) => panic!("a refused engine started"),
            Err(e) => e,
        };
        assert_eq!(err.kind, FailureKind::StartFailed);
        assert!(err.poisoned);
        assert_eq!(err.message.as_str(), refusal_line(declared));
        assert_eq!(engine.starts(), 1);
        assert_eq!(engine.shutdowns(), 1, "the refused engine is closed");
        assert_eq!(engine.generate_calls(), 0, "nothing is served");
        // At process start the caller prints the line (API-08); the driver does not.
        assert!(cap.lines().is_empty(), "{:?}", cap.lines());
    }
}

#[tokio::test(start_paused = true)]
async fn a_restart_refuses_an_engine_that_is_not_synthetic() {
    let engine = one_synthetic_start();
    let (d, _, cap) = driver(Arc::new(engine.clone())).await;
    assert_served(&d).await;
    let err = d
        .restart()
        .await
        .err()
        .unwrap_or_else(|| panic!("restart admitted"));
    assert_refused(&err);
    assert_eq!((engine.starts(), engine.synthetic_starts()), (2, 1));
    assert_eq!(engine.shutdowns(), 1);
    assert!(cap.lines().contains(&refusal_line(Some(DECLARED))));
    // The refused start keeps the context from before it (the donor's #351), so the next
    // request passes the context rule and its turn starts the engine again, through the
    // guard: refused again.
    assert_eq!(d.max_context(), CTX);
    assert_eq!(d.descriptor(), None);
    assert_turn_refused(&d).await;
    assert_eq!((engine.starts(), engine.shutdowns()), (3, 2));
    assert_eq!(engine.generate_calls(), 0);
    assert_eq!(d.fifo().used(), 0);
    assert_eq!(d.max_context(), CTX);
}

#[tokio::test(start_paused = true)]
async fn a_context_reload_refuses_an_engine_that_is_not_synthetic() {
    let engine = one_synthetic_start();
    let (d, _, cap) = driver(Arc::new(engine.clone())).await;
    assert_served(&d).await;
    let err = d
        .reload_context(2048)
        .await
        .err()
        .unwrap_or_else(|| panic!("reload admitted"));
    assert_refused(&err);
    assert_eq!(engine.shutdowns(), 1);
    assert!(cap.lines().contains(&refusal_line(Some(DECLARED))));
    assert_turn_refused(&d).await;
    assert_eq!(engine.generate_calls(), 0);
}

#[tokio::test(start_paused = true)]
async fn a_model_switch_refuses_an_engine_that_is_not_synthetic() {
    let engine = one_synthetic_start();
    let (d, _, cap) = driver(Arc::new(engine.clone())).await;
    assert_served(&d).await;
    // The model switch's entry point, to the same factory (its second start is refused).
    let err = d
        .switch_engine(Arc::new(engine.clone()), EngineStartConfig::new())
        .await
        .err()
        .unwrap_or_else(|| panic!("switch admitted"));
    assert_refused(&err);
    assert_eq!(engine.shutdowns(), 1);
    assert!(cap.lines().contains(&refusal_line(Some(DECLARED))));
    assert_turn_refused(&d).await;
    assert_eq!(engine.generate_calls(), 0);

    // A switch to another engine whose starts are all refused.
    let other = NotSyntheticEngine::after_synthetic_starts(script(), 0, DECLARED)
        .unwrap_or_else(|e| panic!("{e}"));
    let fresh = FakeFactory::new(script()).unwrap_or_else(|e| panic!("{e}"));
    let (d, _, _) = driver(Arc::new(fresh)).await;
    assert_served(&d).await;
    let err = d
        .switch_engine(Arc::new(other.clone()), EngineStartConfig::new())
        .await
        .err()
        .unwrap_or_else(|| panic!("switch admitted"));
    assert_refused(&err);
    assert_turn_refused(&d).await;
    assert_eq!(
        (other.starts(), other.shutdowns(), other.generate_calls()),
        (2, 2, 0)
    );
}

#[tokio::test(start_paused = true)]
async fn the_start_after_an_idle_unload_refuses_an_engine_that_is_not_synthetic() {
    let engine = one_synthetic_start();
    let (d, _, cap) = driver(Arc::new(engine.clone())).await;
    assert_served(&d).await;
    d.unload().await.unwrap_or_else(|e| panic!("unload: {e}"));
    // The unload leaves the context: the next request passes the context rule and its turn
    // starts the engine again.
    assert_eq!(d.max_context(), CTX);
    assert_turn_refused(&d).await;
    let lines = cap.lines();
    assert!(lines.contains(
        &"[console] loading the model again after an idle unload (a minute or so) ...".to_owned()
    ));
    assert!(lines.contains(&refusal_line(Some(DECLARED))));
    assert!(!lines.iter().any(|l| l.contains("running again")));
    assert_eq!((engine.shutdowns(), engine.generate_calls()), (1, 0));
}

/// The first instance of a [`NotSyntheticEngine`] (the synthetic one) dies at its first
/// call, reporting itself ended; every later instance is the engine's own.
#[derive(Clone)]
struct DiesFirst {
    inner: NotSyntheticEngine,
    starts: Arc<AtomicU32>,
}

struct DeadOnCall {
    inner: Box<dyn EngineInstance>,
    dead: bool,
}

impl EngineFactory for DiesFirst {
    fn kind(&self) -> EngineKind {
        self.inner.kind()
    }

    fn start(&self, cfg: &EngineStartConfig) -> Result<Box<dyn EngineInstance>, EngineFailure> {
        let inner = self.inner.start(cfg)?;
        if self.starts.fetch_add(1, Ordering::SeqCst) > 0 {
            return Ok(inner);
        }
        Ok(Box::new(DeadOnCall { inner, dead: false }))
    }
}

impl EngineInstance for DeadOnCall {
    fn descriptor(&self) -> &EngineDescriptor {
        self.inner.descriptor()
    }

    fn generate(
        &mut self,
        _req: &GenerationRequest,
        _control: &ControlProbe,
        _sink: &mut dyn EventSink,
    ) -> Result<Terminal, EngineFailure> {
        self.dead = true;
        Err(EngineFailure::stopped_unexpectedly(Some(-9)))
    }

    fn health(&mut self) -> Health {
        if self.dead {
            Health::Ended {
                exit_code: Some(-9),
                note: None,
            }
        } else {
            Health::Alive
        }
    }

    fn shutdown(self: Box<Self>, deadline: std::time::Instant) -> ShutdownOutcome {
        self.inner.shutdown(deadline)
    }
}

#[tokio::test(start_paused = true)]
async fn the_start_after_a_death_refuses_an_engine_that_is_not_synthetic() {
    let engine = one_synthetic_start();
    let factory = DiesFirst {
        inner: engine.clone(),
        starts: Arc::new(AtomicU32::new(0)),
    };
    let (d, _, cap) = driver(Arc::new(factory)).await;
    // The first turn: the synthetic engine dies in the call.
    let max_new = budget(&d);
    let read = read_turn(d.turn(request(&enc("hi"), max_new)), &[END]).await;
    let died = read
        .outcome
        .error()
        .and_then(TurnError::engine_failure)
        .map(|f| f.kind);
    assert_eq!(died, Some(FailureKind::Died));
    // The next turn starts the engine again after the death, through the guard: refused.
    assert_turn_refused(&d).await;
    let lines = cap.lines();
    assert!(lines.contains(
        &"[console] the engine had stopped (exit code -9); starting it again (a minute or two) ..."
            .to_owned()
    ));
    assert!(lines.contains(&refusal_line(Some(DECLARED))));
    assert!(!lines.iter().any(|l| l.contains("running again")));
    assert_eq!((engine.starts(), engine.synthetic_starts()), (2, 1));
    assert_eq!(
        engine.generate_calls(),
        0,
        "the refused engine served nothing"
    );
    assert_eq!(d.fifo().used(), 0);
}

/// A factory whose `n`-th start fails before the engine is ready.
struct FailNth {
    inner: FakeFactory,
    n: u32,
    count: AtomicU32,
}

impl EngineFactory for FailNth {
    fn kind(&self) -> EngineKind {
        self.inner.kind()
    }

    fn start(&self, cfg: &EngineStartConfig) -> Result<Box<dyn EngineInstance>, EngineFailure> {
        if self.count.fetch_add(1, Ordering::SeqCst) + 1 == self.n {
            return Err(EngineFailure::exited_before_ready(None));
        }
        self.inner.start(cfg)
    }
}

#[tokio::test(start_paused = true)]
async fn a_failed_restart_keeps_the_context_and_the_next_turn_starts_again() {
    let factory = FailNth {
        inner: FakeFactory::new(script()).unwrap_or_else(|e| panic!("{e}")),
        n: 2,
        count: AtomicU32::new(0),
    };
    let (d, _, _) = driver(Arc::new(factory)).await;
    assert!(d.restart().await.is_err());
    // The donor's #351: the context stays what it was, so the request is not refused as
    // starting, and its turn starts the engine again.
    assert_eq!(d.max_context(), CTX);
    assert_ne!(d.context_budget(2, None), Err(TurnError::Starting));
    assert_served(&d).await;
}

#[tokio::test(start_paused = true)]
async fn synthetic_engines_pass_every_admission_path() {
    let factory = FakeFactory::new(script()).unwrap_or_else(|e| panic!("{e}"));
    let probe = factory.probe();
    let (d, _, _) = driver(Arc::new(factory.clone())).await;
    assert_served(&d).await;
    d.restart().await.unwrap_or_else(|e| panic!("{e}"));
    assert_served(&d).await;
    d.reload_context(2048)
        .await
        .unwrap_or_else(|e| panic!("{e}"));
    assert_eq!(d.max_context(), 2048);
    assert_served(&d).await;
    d.switch_engine(Arc::new(factory), EngineStartConfig::new())
        .await
        .unwrap_or_else(|e| panic!("{e}"));
    assert_served(&d).await;
    let before = d.max_context();
    d.unload().await.unwrap_or_else(|e| panic!("{e}"));
    assert_eq!(d.max_context(), before);
    assert_served(&d).await;
    assert_eq!(probe.starts(), 5);
    let desc: EngineDescriptor = d.descriptor().unwrap_or_else(|| panic!("descriptor"));
    assert!(require_synthetic(&desc).is_ok());
}

/// A source-level pin: the driver thread starts an engine in exactly one place, the
/// admission step, and that step calls the guard unconditionally before it keeps the
/// instance; no environment read, conditional compilation or feature switch is in the
/// file.
#[test]
fn every_start_goes_through_the_guard() {
    let src = include_str!("../src/turn/host.rs");
    assert_eq!(src.matches(".start(&").count(), 1, "one engine start");
    assert_eq!(
        src.matches("require_synthetic(").count(),
        1,
        "one call of the guard"
    );
    let admit = src
        .find("fn admit(")
        .unwrap_or_else(|| panic!("no admission step"));
    let body = &src[admit..];
    let start = body.find(".start(&").unwrap_or(usize::MAX);
    let guard = body.find("require_synthetic(").unwrap_or(usize::MAX);
    let keep = body.find("self.instance = Some(").unwrap_or(usize::MAX);
    assert!(
        start < guard && guard < keep,
        "start, then the guard, then keep"
    );
    for banned in ["std::env", "env::var", "#[cfg(", "cfg!(", "feature ="] {
        assert!(!src.contains(banned), "{banned} in the admission file");
    }
    // Every other file of the turn driver leaves engine starts to the host.
    for (name, other) in [
        ("driver.rs", include_str!("../src/turn/driver.rs")),
        ("stream.rs", include_str!("../src/turn/stream.rs")),
        ("hooks.rs", include_str!("../src/turn/hooks.rs")),
    ] {
        assert!(!other.contains(".start(&"), "{name} starts an engine");
    }
}
