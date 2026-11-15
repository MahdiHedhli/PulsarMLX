//! The engine's driver thread: the one thread that starts the engine instance, owns it and
//! calls it (contract section 4). Async request tasks reach it only through a job channel;
//! an engine call's events come back over a bounded channel, and its result with the FIFO
//! place the call held.
//!
//! Every path that admits an engine (first start, restart, model switch, context reload)
//! goes through [`Host::admit`], which calls
//! [`require_synthetic`](crate::engine::require_synthetic) before the instance can serve a
//! request (contract section 5.1; owner decision of 2026-11-14 on OPEN-29, lead decision
//! LD28). A refused instance is shut down at once and never stored, so nothing is served
//! from it. No setting, flag, environment variable or feature changes this.
//!
//! A panic in engine code is caught on the driver thread: the call fails as a death
//! ([`ENGINE_PANICKED`], poisoned), the instance is dropped without being called again, and
//! the next turn starts the engine again through the admission step (contract section 10,
//! `Died`; section 12.1, rule 6).
//!
//! Behavior reference: project-maya serve/server.py:1150-1170, 2632-2661 at 7e68a30f.

use std::panic::{catch_unwind, AssertUnwindSafe};
use std::sync::atomic::{AtomicU32, Ordering};
use std::sync::{mpsc as std_mpsc, Arc, Mutex, PoisonError};
use std::time::{Duration, Instant};

use tokio::sync::{mpsc, oneshot};

use crate::engine::{
    generate_ledgered, require_synthetic, AloneReason, ControlProbe, DeliveryRefused,
    EngineDescriptor, EngineEvent, EngineFactory, EngineFailure, EngineInstance, EngineStartConfig,
    EventSink, GenerationRequest, Health, LedgerCounts, Terminal,
};
use crate::fifo::{EngineFifo, FifoLog, PlaceGuard};

use super::log::{log_safe, LOG_PREFIX};

/// How long a graceful shutdown waits for the engine to end before it is killed (the
/// donor's `stop(timeout=60.0)`).
///
/// Behavior reference: project-maya serve/server.py:985-999 at 7e68a30f.
pub const ENGINE_CLOSE_WAIT: Duration = Duration::from_secs(60);

/// The death a panic in engine code is reported as.
pub const ENGINE_PANICKED: &str = "the engine panicked";

/// Runs one step of engine code, turning a panic into the death [`ENGINE_PANICKED`].
fn guarded<T>(step: impl FnOnce() -> T) -> Result<T, EngineFailure> {
    catch_unwind(AssertUnwindSafe(step)).map_err(|_| EngineFailure::died(ENGINE_PANICKED))
}

/// What the async side can read about the engine without a job: its descriptor and its
/// context, refreshed by the driver thread after every job.
///
/// The context outlives a shutdown, as the donor's `engine.max_context` does: an idle
/// unload leaves it, and a start that fails or is refused puts back the context from
/// before the start (the donor's #351), so the next request passes the context rule and
/// reaches the turn that starts the engine again. While a start runs it reads 0 (the
/// donor's `__init__`), which the context rule answers as starting.
#[derive(Debug, Default)]
pub(crate) struct Snapshot {
    max_context: AtomicU32,
    descriptor: Mutex<Option<EngineDescriptor>>,
}

impl Snapshot {
    pub(crate) fn max_context(&self) -> u32 {
        self.max_context.load(Ordering::Acquire)
    }

    pub(crate) fn descriptor(&self) -> Option<EngineDescriptor> {
        self.descriptor
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .clone()
    }

    /// The running engine's descriptor and its context.
    fn set_descriptor(&self, d: &EngineDescriptor) {
        self.set_context(d.max_context);
        *self
            .descriptor
            .lock()
            .unwrap_or_else(PoisonError::into_inner) = Some(d.clone());
    }

    /// No engine runs: the descriptor goes, the context stays.
    fn clear_descriptor(&self) {
        *self
            .descriptor
            .lock()
            .unwrap_or_else(PoisonError::into_inner) = None;
    }

    fn set_context(&self, n: u32) {
        self.max_context.store(n, Ordering::Release);
    }
}

/// A lifecycle operation of the driver thread. Every one that starts an engine admits it
/// through the synthetic-only guard.
pub(crate) enum Lifecycle {
    /// The first start.
    First,
    /// A shutdown and a start with the same settings.
    Restart,
    /// A shutdown and a start with a new context (graceful, FIX-1.1).
    Reload(u32),
    /// A shutdown and a start of another engine (the model switch).
    Switch(Arc<dyn EngineFactory>, EngineStartConfig),
    /// A shutdown with no start (an idle unload); the next turn starts the engine again.
    Unload,
    /// The end of the driver thread.
    Close,
}

/// The result of one engine call.
pub(crate) struct CallDone {
    /// The place the call held, given back only now that the call has returned.
    pub(crate) place: PlaceGuard,
    /// The terminal with the ledger's figures, or the failure.
    pub(crate) result: Result<(Terminal, LedgerCounts), EngineFailure>,
    /// The engine's death note, when it ended.
    pub(crate) death_note: Option<String>,
    /// The engine's log, when it names one.
    pub(crate) log_path: Option<String>,
}

/// One job for the driver thread.
pub(crate) enum Job {
    /// The donor's `ensure_engine` and `engine_for`: the engine running (started again
    /// after an idle unload or a death, through the guard), then the mixed-GPU layout.
    Prepare {
        place: PlaceGuard,
        alone: Option<AloneReason>,
        reply: oneshot::Sender<(PlaceGuard, Result<u32, EngineFailure>)>,
    },
    /// One engine call through the ledger.
    Generate(Box<GenerateJob>),
    /// A lifecycle operation, holding every place (or none, for the first start and the
    /// close).
    Lifecycle {
        op: Lifecycle,
        place: Option<PlaceGuard>,
        reply: oneshot::Sender<(Option<PlaceGuard>, Result<(), EngineFailure>)>,
    },
}

/// One engine call through the ledger, with the place it holds.
pub(crate) struct GenerateJob {
    pub(crate) place: PlaceGuard,
    pub(crate) req: GenerationRequest,
    pub(crate) control: ControlProbe,
    pub(crate) events: mpsc::Sender<EngineEvent>,
    pub(crate) reply: oneshot::Sender<CallDone>,
}

/// The sink of one engine call: each accepted event goes to the turn's task over a bounded
/// channel. A full channel holds the engine (backpressure by blocking, which is allowed on
/// the driver thread); a closed one answers `ConsumerGone`.
struct ChannelSink {
    tx: mpsc::Sender<EngineEvent>,
}

impl EventSink for ChannelSink {
    fn deliver(&mut self, event: EngineEvent) -> Result<(), DeliveryRefused> {
        self.tx
            .blocking_send(event)
            .map_err(|_| DeliveryRefused::ConsumerGone)
    }
}

/// The state the driver thread owns.
pub(crate) struct Host {
    factory: Arc<dyn EngineFactory>,
    cfg: EngineStartConfig,
    instance: Option<Box<dyn EngineInstance>>,
    /// The last call failed with a poisoned failure: the instance must not be used again.
    poisoned: bool,
    /// Ended by an idle unload, not by a death.
    unloaded: bool,
    fifo: EngineFifo,
    snapshot: Arc<Snapshot>,
    log: FifoLog,
}

fn close_deadline() -> Instant {
    let now = Instant::now();
    now.checked_add(ENGINE_CLOSE_WAIT).unwrap_or(now)
}

impl Host {
    pub(crate) fn new(
        factory: Arc<dyn EngineFactory>,
        fifo: EngineFifo,
        snapshot: Arc<Snapshot>,
        log: FifoLog,
    ) -> Self {
        Self {
            factory,
            cfg: EngineStartConfig::new(),
            instance: None,
            poisoned: false,
            unloaded: false,
            fifo,
            snapshot,
            log,
        }
    }

    /// The driver thread's loop: one job at a time, until every sender is gone or a
    /// [`Lifecycle::Close`] arrives; then the engine is shut down.
    pub(crate) fn run(mut self, jobs: std_mpsc::Receiver<Job>) {
        while let Ok(job) = jobs.recv() {
            match job {
                Job::Prepare {
                    place,
                    alone,
                    reply,
                } => {
                    let result = self.prepare(alone);
                    // A turn that has gone gives the place back here, the job being done.
                    let _ = reply.send((place, result));
                }
                Job::Generate(job) => {
                    let GenerateJob {
                        place,
                        req,
                        control,
                        events,
                        reply,
                    } = *job;
                    let done = self.generate(place, &req, &control, events);
                    // When the turn has gone, dropping `done` here gives its place back,
                    // after the engine call has returned (contract section 4, rule 4).
                    let _ = reply.send(done);
                }
                Job::Lifecycle { op, place, reply } => {
                    let close = matches!(op, Lifecycle::Close);
                    let result = self.lifecycle(op);
                    let _ = reply.send((place, result));
                    if close {
                        break;
                    }
                }
            }
        }
        self.shut_down();
    }

    /// Shuts the engine down. The context is left as it was (see [`Snapshot`]).
    fn shut_down(&mut self) {
        if let Some(old) = self.instance.take() {
            let _ = guarded(move || old.shutdown(close_deadline()));
        }
        self.poisoned = false;
        self.snapshot.clear_descriptor();
    }

    /// Engine code panicked: the instance is dropped without being called again (its drop
    /// guarded too), and the next turn starts the engine again through the admission step.
    fn lose_instance(&mut self) {
        if let Some(inst) = self.instance.take() {
            let _ = guarded(move || drop(inst));
        }
        self.poisoned = false;
        self.unloaded = false;
        self.snapshot.clear_descriptor();
        self.log.line(&format!(
            "{LOG_PREFIX} {ENGINE_PANICKED}: it is dropped, and the next request starts it again"
        ));
    }

    /// The FIFO follows the running engine's places (the donor's `ensure_engine`, where the
    /// turn holds one place; never inside an exclusive operation, which holds them all).
    fn follow_places(&self) {
        let Some(inst) = self.instance.as_ref() else {
            return;
        };
        let places = usize::try_from(inst.descriptor().caps.places()).unwrap_or(1);
        if places != self.fifo.capacity() {
            self.fifo.set_capacity(places);
        }
    }

    /// The admission step: start the engine and admit it only if the synthetic-only guard
    /// accepts its descriptor. A refused instance is shut down at once and never stored;
    /// the failure is the guard's ([`ProvenanceRefused::to_failure`]). While the start runs
    /// the context reads 0; a start that fails or is refused puts the context from before
    /// it back (the donor's #351). The FIFO's places are left to the caller.
    ///
    /// [`ProvenanceRefused::to_failure`]: crate::engine::ProvenanceRefused::to_failure
    ///
    /// Behavior reference: project-maya serve/server.py:1150-1170, 2654-2661 at 7e68a30f.
    fn admit(&mut self, log_refusal: bool) -> Result<(), EngineFailure> {
        let before = self.snapshot.max_context();
        self.snapshot.set_context(0);
        let started = guarded(|| self.factory.start(&self.cfg)).and_then(|started| started);
        let instance = match started {
            Ok(instance) => instance,
            Err(f) => {
                self.snapshot.set_context(before);
                return Err(f);
            }
        };
        if let Err(refused) = require_synthetic(instance.descriptor()) {
            let _ = guarded(move || instance.shutdown(close_deadline()));
            self.snapshot.set_context(before);
            if log_refusal {
                // The declared provenance is displayed escaped (DeclaredProvenance), so the
                // line is already log-safe.
                self.log.line(&refused.to_string());
            }
            return Err(refused.to_failure());
        }
        self.snapshot.set_descriptor(instance.descriptor());
        self.instance = Some(instance);
        self.poisoned = false;
        self.unloaded = false;
        Ok(())
    }

    fn lifecycle(&mut self, op: Lifecycle) -> Result<(), EngineFailure> {
        match op {
            Lifecycle::First => {
                // No place is held yet: the FIFO follows the engine's places at once.
                self.admit(false)?;
                self.follow_places();
                Ok(())
            }
            Lifecycle::Restart => {
                self.shut_down();
                self.admit(true)
            }
            Lifecycle::Reload(context) => {
                self.shut_down();
                self.cfg = self.cfg.clone().with_context(context);
                self.admit(true)
            }
            Lifecycle::Switch(factory, cfg) => {
                self.shut_down();
                self.factory = factory;
                self.cfg = cfg;
                self.admit(true)
            }
            Lifecycle::Unload => {
                self.shut_down();
                self.unloaded = true;
                Ok(())
            }
            Lifecycle::Close => {
                self.shut_down();
                Ok(())
            }
        }
    }

    /// The donor's `ensure_engine`: nothing to do while the engine runs; otherwise a line
    /// that says why it starts again (after an idle unload, or after it stopped), a restart
    /// through the admission step, and a line once it runs. Then the mixed-GPU layout for
    /// the request (`use_layout`, a no-op for an engine without one). The FIFO follows the
    /// engine's places here, where the turn holds one place, so a restart, reload or
    /// switch (which hold them all) never resizes it. Returns the context the engine
    /// reports.
    ///
    /// Behavior reference: project-maya serve/server.py:2632-2661 at 7e68a30f.
    fn prepare(&mut self, alone: Option<AloneReason>) -> Result<u32, EngineFailure> {
        let mut exit_code = None;
        let mut panicked = false;
        let alive = match self.instance.as_mut() {
            Some(inst) => match guarded(|| inst.health()) {
                Ok(Health::Alive) => !self.poisoned,
                Ok(Health::Ended { exit_code: c, .. }) => {
                    exit_code = c;
                    false
                }
                Err(_) => {
                    panicked = true;
                    false
                }
            },
            None => false,
        };
        if panicked {
            self.lose_instance();
        }
        if !alive {
            if self.unloaded {
                self.log.line(&format!(
                    "{LOG_PREFIX} loading the model again after an idle unload (a minute or so) ..."
                ));
            } else {
                let code = exit_code.map_or_else(|| "None".to_owned(), |c| c.to_string());
                self.log.line(&format!(
                    "{LOG_PREFIX} the engine had stopped (exit code {code}); starting it again \
                     (a minute or two) ..."
                ));
            }
            self.shut_down();
            self.admit(true)?;
            self.log
                .line(&format!("{LOG_PREFIX} the engine is running again"));
        }
        self.follow_places();
        let Some(inst) = self.instance.as_mut() else {
            return Err(EngineFailure::stopped_unexpectedly(None));
        };
        match guarded(|| inst.use_layout(alone)) {
            Ok(laid_out) => laid_out?,
            Err(f) => {
                self.lose_instance();
                return Err(f);
            }
        }
        self.snapshot.set_descriptor(inst.descriptor());
        Ok(inst.descriptor().max_context)
    }

    fn generate(
        &mut self,
        place: PlaceGuard,
        req: &GenerationRequest,
        control: &ControlProbe,
        events: mpsc::Sender<EngineEvent>,
    ) -> CallDone {
        let Some(inst) = self.instance.as_mut() else {
            return CallDone {
                place,
                result: Err(EngineFailure::stopped_unexpectedly(None)),
                death_note: None,
                log_path: None,
            };
        };
        let mut sink = ChannelSink { tx: events };
        let called = guarded(|| generate_ledgered(inst.as_mut(), req, control, &mut sink));
        // The sink's sender goes now, so the turn's task sees the end of the events before
        // it reads the result.
        drop(sink);
        let result = match called {
            Ok(result) => result,
            Err(f) => {
                // The place is still held here: it goes back with the reply, after the
                // call has unwound.
                self.lose_instance();
                return CallDone {
                    place,
                    result: Err(f),
                    death_note: None,
                    log_path: None,
                };
            }
        };
        let mut death_note = None;
        if let Err(f) = &result {
            if f.poisoned {
                self.poisoned = true;
                if let Ok(Health::Ended { note: Some(n), .. }) = guarded(|| inst.health()) {
                    death_note = Some(log_safe(n.as_str()));
                }
            }
        }
        let log_path = inst.descriptor().facts.log_path.clone();
        self.snapshot.set_descriptor(inst.descriptor());
        CallDone {
            place,
            result,
            death_note,
            log_path,
        }
    }
}
