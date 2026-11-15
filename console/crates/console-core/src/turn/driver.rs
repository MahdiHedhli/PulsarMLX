//! The turn driver: one request's turn on the engine, as an explicit state machine.
//!
//! The donor's `Service.run` nests generators (`_queue_wait`, `_turn`, `attempts`,
//! `segments`, `_sliced` and the engine's `generate`), each with a `finally`. Here one
//! spawned task walks these states:
//!
//! 1. **Queued**: in the FIFO, a keep-alive every queue-ping interval; a cancel leaves the
//!    line ([`QueueStep::Cancelled`]).
//! 2. **Admitting**: the turn holds its place. A cancel set by now ends it with nothing
//!    asked of the engine; a server that is stopping refuses it; otherwise the driver
//!    thread runs the donor's `ensure_engine` (a restart through the synthetic-only guard
//!    when the engine is not running) and the mixed-GPU layout.
//! 3. **Calling**: one engine call on the driver thread, its events forwarded to the
//!    consumer, a keep-alive when the engine is quiet for the heartbeat interval. A cancel
//!    (the consumer's, or the server's when the answer is finished) reaches the engine
//!    through its control probe; the call still runs to its end (the drain) and the place
//!    stays held. The result decides the next state: another call of the same attempt (a
//!    fair slice, [`Continuation::Again`]), the first call of a new segment
//!    ([`Continuation::NextSegment`], with an attempt of its own), a second attempt of the
//!    segment (the non-finite retry), or the end. A failure the call returns once the
//!    cancel is set is part of the drain, as the donor's drain swallows an `ERR` or an end
//!    read after STOP.
//! 4. **Ended**: the place is given back, only now that the last engine call has
//!    returned (contract section 4, rule 4), and the outcome is sent.
//!
//! Behavior reference: project-maya serve/server.py:2632-2661, 4097-4126, 4256-4271,
//! 4273-4307, 4340-4378, 4433-4454, 4491-4496, 4657-4793 at 7e68a30f.

use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{mpsc as std_mpsc, Arc, Mutex, PoisonError};
use std::time::Duration;

use tokio::sync::{mpsc, oneshot};
use tokio::time::Instant;

use crate::engine::{
    AloneReason, ControlHandle, EngineDescriptor, EngineEvent, EngineFactory, EngineFailure,
    EngineStartConfig, EngineStop, FailureKind, GenerationRequest, PromptProgress, RequestId,
};
use crate::fifo::{EngineFifo, FifoLog, PlaceGuard, QueueStep, Units, QUEUE_PING};
use crate::request::pynum::PyInt;

use super::context::{call_budget, context_rule};
use super::error::{is_non_finite, TurnError};
use super::figures::{request_figures, SegmentFigures};
use super::hooks::{
    CallSummary, Continuation, ContinuationPolicy, NoContinuation, NoObserver, TurnObserver,
    TurnStart, PHASE_READING_THE_PROMPT,
};
use super::host::{CallDone, GenerateJob, Host, Job, Lifecycle, Snapshot};
use super::log::{log_safe, LOG_PREFIX};
use super::stream::{Item, PingProgress, RawDone, StreamShared, TurnEnd, TurnStream};

/// How long an engine may stay quiet before the turn sends a keep-alive of its own (the
/// donor's 10-second wait for an engine line).
///
/// Behavior reference: project-maya serve/server.py:1387-1403 at 7e68a30f.
pub const HEARTBEAT: Duration = Duration::from_secs(10);

/// The most token ids a turn keeps of what one attempt produced, for its continuation
/// policy (4 Mi ids: beyond any context the engines report).
const PRODUCED_MAX: usize = 1 << 22;

/// The default bound of each turn channel (engine to turn, turn to consumer).
pub const TURN_CHANNEL_CAPACITY: usize = 64;

/// Settings of the turn driver.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TurnSettings {
    /// `--fit-max-tokens`: clamp an answer budget that overshoots the context instead of
    /// refusing it.
    pub fit_max_tokens: bool,
    /// The keep-alive interval while the engine is quiet; `None`: never.
    pub heartbeat: Option<Duration>,
    /// The keep-alive interval while queued (normally
    /// [`queue_ping_interval`](crate::fifo::queue_ping_interval)); `None`: never.
    pub queue_ping: Option<Duration>,
    /// The bound of each turn channel; at least 1.
    pub channel_capacity: usize,
}

impl Default for TurnSettings {
    fn default() -> Self {
        Self {
            fit_max_tokens: false,
            heartbeat: Some(HEARTBEAT),
            queue_ping: Some(QUEUE_PING),
            channel_capacity: TURN_CHANNEL_CAPACITY,
        }
    }
}

/// One request for a turn on the engine.
pub struct TurnRequest {
    /// The engine call: the whole prompt, the answer budget after the context rule
    /// ([`TurnDriver::context_budget`]), sampling, stop ids, logprobs, hints and picture
    /// data. The embeddings reference travels here, so a turn consumed on another task or
    /// thread keeps its picture data (it replaces the donor's thread-local
    /// `carry_embeddings`). The request id is assigned by the driver for each call.
    pub generation: GenerationRequest,
    /// The places the turn takes: [`Units::ONE`] for a request.
    pub units: Units,
    /// Why the request runs on one GPU alone on a mixed-GPU engine, if it does.
    pub alone: Option<AloneReason>,
    /// The tokenizer's vocabulary size: an engine token at or beyond it ends the turn as
    /// the donor's tokenizer does (an `IndexError`), with the engine stopped and drained.
    pub vocab_size: Option<u32>,
    /// Server-side continuations (ENG-11); [`NoContinuation`] by default.
    pub continuation: Box<dyn ContinuationPolicy>,
}

impl TurnRequest {
    /// A request for one place, with no continuations.
    pub fn new(generation: GenerationRequest) -> Self {
        Self {
            generation,
            units: Units::ONE,
            alone: None,
            vocab_size: None,
            continuation: Box::new(NoContinuation),
        }
    }
}

impl std::fmt::Debug for TurnRequest {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("TurnRequest")
            .field("generation", &self.generation)
            .field("units", &self.units)
            .field("alone", &self.alone)
            .field("vocab_size", &self.vocab_size)
            .finish_non_exhaustive()
    }
}

struct DriverShared {
    jobs: Mutex<std_mpsc::Sender<Job>>,
    fifo: EngineFifo,
    snapshot: Arc<Snapshot>,
    settings: TurnSettings,
    observer: Arc<dyn TurnObserver>,
    log: FifoLog,
    stopping: AtomicBool,
    next_rid: AtomicU64,
}

impl DriverShared {
    /// Sends a job to the driver thread; false when the thread has ended (the job, and a
    /// place it carries, is then dropped, which gives the place back).
    fn send(&self, job: Job) -> bool {
        self.jobs
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .send(job)
            .is_ok()
    }

    fn rid(&self) -> RequestId {
        RequestId(self.next_rid.fetch_add(1, Ordering::Relaxed))
    }
}

fn driver_gone() -> EngineFailure {
    EngineFailure::died("the engine's driver thread has ended")
}

/// The server's handle on the engine: the driver thread that owns the engine instance, the
/// FIFO in front of it, and the turns. Cloning gives another handle to the same driver.
/// The driver thread ends, shutting the engine down, when every handle is gone or after
/// [`TurnDriver::close`].
#[derive(Clone)]
pub struct TurnDriver {
    shared: Arc<DriverShared>,
}

impl std::fmt::Debug for TurnDriver {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("TurnDriver")
            .field("fifo", &self.shared.fifo)
            .field("max_context", &self.shared.snapshot.max_context())
            .finish_non_exhaustive()
    }
}

impl TurnDriver {
    /// Starts the driver thread and the engine on it (the first start). The engine is
    /// admitted only if [`require_synthetic`](crate::engine::require_synthetic) accepts
    /// its descriptor; a refused engine is shut down and the start fails with
    /// [`ProvenanceRefused::to_failure`](crate::engine::ProvenanceRefused::to_failure),
    /// whose message is the refusal line `pulsar-console` prints before it exits. The FIFO
    /// follows the engine's places.
    pub async fn start(
        factory: Arc<dyn EngineFactory>,
        fifo: EngineFifo,
        settings: TurnSettings,
        observer: Arc<dyn TurnObserver>,
        log: FifoLog,
    ) -> Result<TurnDriver, EngineFailure> {
        let snapshot = Arc::new(Snapshot::default());
        let (tx, rx) = std_mpsc::channel();
        let (host_fifo, host_snapshot, host_log) =
            (fifo.clone(), Arc::clone(&snapshot), log.clone());
        std::thread::Builder::new()
            .name("console-engine-driver".to_owned())
            // The host, and with it the engine instance, is created on the driver thread
            // and never leaves it.
            .spawn(move || Host::new(factory, host_fifo, host_snapshot, host_log).run(rx))
            .map_err(|e| {
                EngineFailure::died(&format!("the engine's driver thread did not start: {e}"))
            })?;
        let driver = TurnDriver {
            shared: Arc::new(DriverShared {
                jobs: Mutex::new(tx),
                fifo,
                snapshot,
                settings,
                observer,
                log,
                stopping: AtomicBool::new(false),
                next_rid: AtomicU64::new(1),
            }),
        };
        driver.lifecycle(Lifecycle::First, None).await?;
        Ok(driver)
    }

    /// [`TurnDriver::start`] with the default settings, no observer and the standard
    /// output log.
    pub async fn start_default(
        factory: Arc<dyn EngineFactory>,
        fifo: EngineFifo,
    ) -> Result<TurnDriver, EngineFailure> {
        Self::start(
            factory,
            fifo,
            TurnSettings::default(),
            Arc::new(NoObserver),
            FifoLog::stdout(),
        )
        .await
    }

    async fn lifecycle(
        &self,
        op: Lifecycle,
        place: Option<PlaceGuard>,
    ) -> Result<(), EngineFailure> {
        let (reply, rx) = oneshot::channel();
        if !self.shared.send(Job::Lifecycle { op, place, reply }) {
            return Err(driver_gone());
        }
        match rx.await {
            Ok((place, result)) => {
                drop(place);
                result
            }
            Err(_) => Err(driver_gone()),
        }
    }

    async fn exclusive(&self, op: Lifecycle) -> Result<(), TurnError> {
        let place = self.shared.fifo.acquire(Units::All).await;
        self.lifecycle(op, Some(place))
            .await
            .map_err(TurnError::Engine)
    }

    /// Restarts the engine, holding every place: a shutdown, then a start through the
    /// admission step (the synthetic-only guard). A refused engine is closed and the
    /// restart fails with the guard's refusal; the next turn tries the start again.
    pub async fn restart(&self) -> Result<(), TurnError> {
        self.exclusive(Lifecycle::Restart).await
    }

    /// Reloads the engine with another context, holding every place: a graceful shutdown
    /// (FIX-1.1), then a start with `context` through the admission step.
    pub async fn reload_context(&self, context: u32) -> Result<(), TurnError> {
        self.exclusive(Lifecycle::Reload(context)).await
    }

    /// Switches to another engine (the entry point of a model switch), holding every
    /// place: the current engine is shut down, then `factory` starts with `cfg` through
    /// the admission step. A refused engine is closed and nothing is served from it.
    pub async fn switch_engine(
        &self,
        factory: Arc<dyn EngineFactory>,
        cfg: EngineStartConfig,
    ) -> Result<(), TurnError> {
        self.exclusive(Lifecycle::Switch(factory, cfg)).await
    }

    /// Ends the engine between requests (an idle unload), holding every place; the next
    /// turn starts it again through the admission step.
    pub async fn unload(&self) -> Result<(), TurnError> {
        self.exclusive(Lifecycle::Unload).await
    }

    /// Shuts the engine down and ends the driver thread, without waiting for a place.
    pub async fn close(&self) {
        let _ = self.lifecycle(Lifecycle::Close, None).await;
    }

    /// Marks the server as stopping: a turn that reaches its turn from now on fails with
    /// the donor's "the server is stopping" error, and no continuation starts.
    pub fn set_stopping(&self, stopping: bool) {
        self.shared.stopping.store(stopping, Ordering::Release);
    }

    /// True while the server is stopping.
    pub fn is_stopping(&self) -> bool {
        self.shared.stopping.load(Ordering::Acquire)
    }

    /// The context the engine reports now: 0 before the first start has answered, while a
    /// start runs, or when the engine reports none (not ready). An idle unload, and a start
    /// that fails or is refused, keep the last context, as the donor does (#351), so the
    /// next request reaches the turn that starts the engine again.
    pub fn max_context(&self) -> u32 {
        self.shared.snapshot.max_context()
    }

    /// The running engine's descriptor, as of the driver's last job.
    pub fn descriptor(&self) -> Option<EngineDescriptor> {
        self.shared.snapshot.descriptor()
    }

    /// The FIFO in front of the engine.
    pub fn fifo(&self) -> &EngineFifo {
        &self.shared.fifo
    }

    /// The context rule ([`context_rule`]) against the engine's context now and the
    /// driver's `fit_max_tokens` setting.
    pub fn context_budget(
        &self,
        prompt_tokens: usize,
        max_new: Option<&PyInt>,
    ) -> Result<u32, TurnError> {
        context_rule(
            i64::from(self.max_context()),
            prompt_tokens,
            max_new,
            self.shared.settings.fit_max_tokens,
        )
    }

    /// Starts a turn in its own task, which owns the FIFO place and the engine calls. The
    /// returned stream yields its items; dropping it only sets the cancel, so the engine is
    /// still stopped and drained before the place is given back. Must be called inside a
    /// tokio runtime.
    pub fn turn(&self, req: TurnRequest) -> TurnStream {
        let cap = self.shared.settings.channel_capacity.max(1);
        let (tx, rx) = mpsc::channel(cap);
        let control = ControlHandle::new();
        let stream_shared = Arc::new(StreamShared::new(
            Arc::clone(&self.shared.observer),
            self.shared.log.clone(),
        ));
        let task = TurnTask {
            driver: Arc::clone(&self.shared),
            control: control.clone(),
            tx,
            stream: Arc::clone(&stream_shared),
            gone: false,
            last_progress: None,
            error: None,
            extra_tokens: 0,
            sent: 0,
            first_at: None,
            started: Instant::now(),
            produced: Vec::new(),
        };
        tokio::spawn(task.run(req));
        TurnStream::new(rx, control, stream_shared)
    }
}

/// One attempt's engine calls within one segment (the donor's `attempts`, run afresh for
/// each segment, at most twice).
///
/// Behavior reference: project-maya serve/server.py:4433-4465 at 7e68a30f.
struct Attempt {
    /// The second attempt of the segment (the non-finite retry).
    again: bool,
    /// The segment's first prompt and budget: what a non-finite retry runs again.
    first_prompt: Arc<[u32]>,
    first_max_new: u32,
    /// How many tokens the turn had produced when the segment began.
    produced_at: usize,
    /// The next call's prompt and budget (a fair slice changes them).
    prompt: Arc<[u32]>,
    max_new: u32,
    /// The figures of this attempt's calls, merged as the donor merges the slices of one
    /// `_sliced` call.
    segments: Vec<SegmentFigures>,
    /// Tokens this attempt sent.
    got: u32,
}

impl Attempt {
    fn new(prompt: Arc<[u32]>, max_new: u32, produced_at: usize, again: bool) -> Self {
        Self {
            again,
            first_prompt: Arc::clone(&prompt),
            first_max_new: max_new,
            produced_at,
            prompt,
            max_new,
            segments: Vec::new(),
            got: 0,
        }
    }
}

/// The states of a turn.
enum State {
    Queued,
    Admitting(PlaceGuard),
    Calling(PlaceGuard, Attempt),
    Ended(Option<PlaceGuard>, TurnEnd, Option<SegmentFigures>),
}

struct TurnTask {
    driver: Arc<DriverShared>,
    control: ControlHandle,
    tx: mpsc::Sender<Item>,
    stream: Arc<StreamShared>,
    /// The consumer's channel is closed: items are dropped, the engine is stopped.
    gone: bool,
    /// The latest prompt progress of the current engine call.
    last_progress: Option<PromptProgress>,
    /// An error the turn raised itself while forwarding (an id outside the vocabulary, a
    /// progress time `round` refuses); the engine is stopped and drained first.
    error: Option<TurnError>,
    /// Tokens the request took that were not handed out: the id outside the vocabulary,
    /// which the donor counts (`n += 1`) before its tokenizer raises.
    extra_tokens: u32,
    /// Tokens forwarded to the consumer.
    sent: u32,
    first_at: Option<Instant>,
    started: Instant,
    /// The current attempt's tokens.
    produced: Vec<u32>,
}

impl TurnTask {
    fn log(&self, line: &str) {
        self.driver.log.line(line);
    }

    async fn send(&mut self, item: Item) {
        if self.gone {
            return;
        }
        if self.tx.send(item).await.is_err() {
            self.gone = true;
            self.control.cancel();
        }
    }

    async fn ping(&mut self) {
        match self.last_progress.as_ref().map(PingProgress::from_progress) {
            None => self.send(Item::Ping(None)).await,
            Some(Ok(p)) => self.send(Item::Ping(Some(p))).await,
            Some(Err(e)) => self.raise(TurnError::Request(e)),
        }
    }

    /// Records an error of the turn's own and stops the engine; the call drains first.
    fn raise(&mut self, e: TurnError) {
        if self.error.is_none() {
            self.error = Some(e);
        }
        self.control.cancel();
    }

    async fn run(mut self, mut req: TurnRequest) {
        let prompt_tokens = u32::try_from(req.generation.prompt.len()).unwrap_or(u32::MAX);
        let mut counted = false;
        // The turn held a place at some point: its release is reported even when the
        // driver side gave it back (a driver thread that has ended).
        let mut held = false;
        let mut state = State::Queued;
        loop {
            state = match state {
                State::Queued => {
                    let next = self.queued(req.units).await;
                    held = matches!(next, State::Admitting(_));
                    next
                }
                State::Admitting(place) => {
                    let next = self
                        .admitting(
                            place,
                            req.alone,
                            &req.generation.prompt,
                            req.generation.max_new,
                        )
                        .await;
                    if matches!(next, State::Calling(..)) {
                        counted = true;
                        self.driver.observer.active(&TurnStart {
                            phase: PHASE_READING_THE_PROMPT,
                            prompt_tokens,
                            max_tokens: req.generation.max_new,
                        });
                        self.started = Instant::now();
                    }
                    next
                }
                State::Calling(place, attempt) => self.calling(place, attempt, &mut req).await,
                State::Ended(place, end, figures) => {
                    // The place goes back only now: the last engine call has returned.
                    drop(place);
                    if held {
                        self.driver.observer.place_released();
                    }
                    if counted {
                        self.driver.observer.inactive();
                    }
                    let raw = RawDone {
                        end,
                        prompt_tokens,
                        figures,
                        extra_tokens: self.extra_tokens,
                        counted,
                        started: self.started,
                        first_at: self.first_at,
                    };
                    self.finish(raw).await;
                    return;
                }
            };
        }
    }

    async fn finish(&mut self, raw: RawDone) {
        if self.gone {
            let _ = self.stream.conclude(raw);
            return;
        }
        if let Err(mpsc::error::SendError(Item::Done(raw))) = self.tx.send(Item::Done(raw)).await {
            // The stream was dropped: the end is booked here, with what it handed out.
            let _ = self.stream.conclude(raw);
        }
    }

    /// The wait for a place, with keep-alives.
    ///
    /// Behavior reference: project-maya serve/server.py:3839-3860, 4340-4364 at 7e68a30f.
    async fn queued(&mut self, units: Units) -> State {
        let fifo = self.driver.fifo.clone();
        self.driver.observer.queued();
        let mut wait =
            fifo.queue_wait(units, self.control.probe(), self.driver.settings.queue_ping);
        loop {
            match wait.next().await {
                QueueStep::Ping => self.send(Item::Ping(None)).await,
                QueueStep::Turn(place) => {
                    self.driver.observer.dequeued();
                    return State::Admitting(place);
                }
                QueueStep::Cancelled | QueueStep::Ended => {
                    self.driver.observer.dequeued();
                    return State::Ended(None, TurnEnd::CancelledBeforeEngine, None);
                }
            }
        }
    }

    /// The turn taken: the cancel, the stopping server, then the engine prepared on the
    /// driver thread.
    ///
    /// Behavior reference: project-maya serve/server.py:4361-4370, 2632-2661 at 7e68a30f.
    async fn admitting(
        &mut self,
        place: PlaceGuard,
        alone: Option<AloneReason>,
        prompt: &Arc<[u32]>,
        max_new: u32,
    ) -> State {
        if self.control.probe().is_cancelled() {
            return State::Ended(Some(place), TurnEnd::CancelledBeforeEngine, None);
        }
        if self.driver.stopping.load(Ordering::Acquire) {
            let end = TurnEnd::Failed(TurnError::stopping());
            return State::Ended(Some(place), end, None);
        }
        let (reply, rx) = oneshot::channel();
        let job = Job::Prepare {
            place,
            alone,
            reply,
        };
        if !self.driver.send(job) {
            let end = TurnEnd::Failed(TurnError::Engine(driver_gone()));
            return State::Ended(None, end, None);
        }
        match rx.await {
            Ok((place, Ok(_max_context))) => {
                State::Calling(place, Attempt::new(Arc::clone(prompt), max_new, 0, false))
            }
            Ok((place, Err(f))) => State::Ended(
                Some(place),
                TurnEnd::Failed(TurnError::from_engine(f)),
                None,
            ),
            Err(_) => State::Ended(
                None,
                TurnEnd::Failed(TurnError::Engine(driver_gone())),
                None,
            ),
        }
    }

    /// The donor's "the engine reported an error" line, written only for what its `except
    /// ValueError` catches: an engine's `ERR` (`Reported`), a token-id error of the engine
    /// (`InvalidToken`, other than an id outside the vocabulary, which is an `IndexError`),
    /// and the `ValueError` Python's `round` raises on a NaN progress time. An `IndexError`,
    /// an `OverflowError` and the other failures pass that handler without a line.
    ///
    /// Behavior reference: project-maya serve/server.py:4682-4691 at 7e68a30f.
    fn log_reported(&self, e: &TurnError) {
        let caught = match e {
            TurnError::Request(r) => r.python_type() == "ValueError",
            TurnError::Engine(f) => {
                matches!(f.kind, FailureKind::Reported | FailureKind::InvalidToken)
            }
            TurnError::ContextOverflow { .. } | TurnError::Starting => false,
        };
        if caught {
            self.log(&format!(
                "{LOG_PREFIX} the engine reported an error: {}",
                log_safe(&e.message())
            ));
        }
    }

    /// One engine call and what follows it.
    ///
    /// Behavior reference: project-maya serve/server.py:1451-1500, 4433-4465, 4646-4691 at
    /// 7e68a30f.
    async fn calling(
        &mut self,
        place: PlaceGuard,
        mut attempt: Attempt,
        req: &mut TurnRequest,
    ) -> State {
        let max_context = self.driver.snapshot.max_context();
        let mut generation = req.generation.clone();
        generation.rid = self.driver.rid();
        generation.prompt = Arc::clone(&attempt.prompt);
        generation.max_new = call_budget(max_context, attempt.prompt.len(), attempt.max_new);
        let got_before = self.sent;
        let done = self.call(place, generation, req.vocab_size).await;
        attempt.got = attempt.got.saturating_add(self.sent - got_before);
        let CallDone {
            place,
            result,
            death_note,
            log_path,
        } = match done {
            Ok(done) => done,
            Err(f) => {
                let end = TurnEnd::Failed(self.error.take().unwrap_or(TurnError::Engine(f)));
                return State::Ended(None, end, None);
            }
        };
        match result {
            Ok((terminal, _counts)) => {
                if let Some(e) = self.error.take() {
                    self.log_reported(&e);
                    return State::Ended(Some(place), TurnEnd::Failed(e), None);
                }
                if let Some(s) = SegmentFigures::from_terminal(&terminal) {
                    attempt.segments.push(s);
                }
                let stop = terminal.stop;
                let decision = if self.control.probe().is_cancelled()
                    || self.driver.stopping.load(Ordering::Acquire)
                {
                    Continuation::Finish
                } else {
                    req.continuation.after_call(&CallSummary {
                        prompt: &req.generation.prompt,
                        produced: &self.produced,
                        stop,
                        max_new: req.generation.max_new,
                    })
                };
                match decision {
                    Continuation::Again { prompt, max_new } => {
                        attempt.prompt = prompt;
                        attempt.max_new = max_new;
                        State::Calling(place, attempt)
                    }
                    Continuation::NextSegment { prompt, max_new } => {
                        // A new segment: a fresh attempt (its own retry and count), and
                        // its figures replace the earlier segment's.
                        let produced_at = self.produced.len();
                        State::Calling(place, Attempt::new(prompt, max_new, produced_at, false))
                    }
                    Continuation::Finish => {
                        let n_prompt =
                            u32::try_from(req.generation.prompt.len()).unwrap_or(u32::MAX);
                        match request_figures(&attempt.segments, n_prompt) {
                            Ok(figures) => State::Ended(Some(place), TurnEnd::Ended(stop), figures),
                            Err(f) => State::Ended(
                                Some(place),
                                TurnEnd::Failed(TurnError::Engine(f)),
                                None,
                            ),
                        }
                    }
                }
            }
            Err(f) => {
                if let Some(e) = self.error.take() {
                    self.log_reported(&e);
                    return State::Ended(Some(place), TurnEnd::Failed(e), None);
                }
                if self.control.probe().is_cancelled() {
                    // The cancel was set before the call returned (the server's finish,
                    // the client's cancel or a dropped stream): the failure is part of the
                    // drain, which the donor's drain swallows (an ERR or the engine's end
                    // read after STOP). A poisoned failure is still recorded on the driver
                    // thread, so the next turn starts the engine again.
                    let n_prompt = u32::try_from(req.generation.prompt.len()).unwrap_or(u32::MAX);
                    let figures = request_figures(&attempt.segments, n_prompt).ok().flatten();
                    return State::Ended(
                        Some(place),
                        TurnEnd::Ended(EngineStop::Cancelled),
                        figures,
                    );
                }
                if is_non_finite(&f) && !attempt.again && attempt.got == 0 {
                    self.log(&format!(
                        "{LOG_PREFIX} the engine's numbers went non-finite before the answer \
                         started ({}): running the request again from token 0",
                        log_safe(f.message.as_str())
                    ));
                    // The segment runs again from its own first prompt and budget.
                    self.produced.truncate(attempt.produced_at);
                    let again = Attempt::new(
                        attempt.first_prompt,
                        attempt.first_max_new,
                        attempt.produced_at,
                        true,
                    );
                    return State::Calling(place, again);
                }
                if is_non_finite(&f) && self.sent > 0 {
                    self.log(&format!(
                        "{LOG_PREFIX} the engine's numbers went non-finite after {} tokens ({}): \
                         the answer ends there",
                        self.sent,
                        log_safe(f.message.as_str())
                    ));
                    return State::Ended(Some(place), TurnEnd::NonFiniteCut, None);
                }
                if f.kind == FailureKind::Died {
                    let note = death_note.unwrap_or_default();
                    let its_log = log_path
                        .filter(|p| !p.is_empty())
                        .map_or_else(String::new, |p| format!(" Its log: {}", log_safe(&p)));
                    self.log(&format!(
                        "{LOG_PREFIX} {}. {note} The next request starts the engine again.{its_log}",
                        log_safe(f.message.as_str())
                    ));
                    return State::Ended(
                        Some(place),
                        TurnEnd::Failed(TurnError::from_engine(f)),
                        None,
                    );
                }
                let e = TurnError::from_engine(f);
                self.log_reported(&e);
                State::Ended(Some(place), TurnEnd::Failed(e), None)
            }
        }
    }

    /// Sends one engine call to the driver thread and forwards its events until the call
    /// has returned. Returns the call's result with its place, or, when the driver thread
    /// is gone, the failure to report (the place is then already given back).
    async fn call(
        &mut self,
        place: PlaceGuard,
        generation: GenerationRequest,
        vocab_size: Option<u32>,
    ) -> Result<CallDone, EngineFailure> {
        let cap = self.driver.settings.channel_capacity.max(1);
        let (events, mut ev_rx) = mpsc::channel(cap);
        let (reply, reply_rx) = oneshot::channel();
        let job = Job::Generate(Box::new(GenerateJob {
            place,
            req: generation,
            control: self.control.probe(),
            events,
            reply,
        }));
        if !self.driver.send(job) {
            return Err(driver_gone());
        }
        self.last_progress = None;
        let heartbeat = self.driver.settings.heartbeat;
        loop {
            let next = match heartbeat {
                Some(every) => match tokio::time::timeout(every, ev_rx.recv()).await {
                    Ok(ev) => ev,
                    Err(_) => {
                        self.ping().await;
                        continue;
                    }
                },
                None => ev_rx.recv().await,
            };
            match next {
                Some(ev) => self.on_event(ev, vocab_size).await,
                None => break,
            }
        }
        reply_rx.await.map_err(|_| driver_gone())
    }

    async fn on_event(&mut self, ev: EngineEvent, vocab_size: Option<u32>) {
        match ev {
            EngineEvent::Admitted { .. } => {}
            EngineEvent::PromptProgress(p) => {
                self.last_progress = Some(p);
                self.ping().await;
            }
            EngineEvent::Token(t) => {
                if self.error.is_some() {
                    return;
                }
                if let Some(v) = vocab_size {
                    if t.id >= v {
                        // The donor counts the token (`n += 1`) before its tokenizer
                        // raises; it is not handed out.
                        self.sent = self.sent.saturating_add(1);
                        self.extra_tokens = 1;
                        self.driver.observer.generated(self.sent);
                        self.raise(TurnError::out_of_vocabulary(t.id, v));
                        return;
                    }
                }
                self.sent = self.sent.saturating_add(1);
                if self.first_at.is_none() {
                    self.first_at = Some(Instant::now());
                }
                if self.produced.len() < PRODUCED_MAX {
                    self.produced.push(t.id);
                }
                self.driver.observer.generated(self.sent);
                self.send(Item::Token(t)).await;
            }
            EngineEvent::Sample(s) => self.driver.observer.sample(&s),
            EngineEvent::Note(n) => {
                self.log(&format!("{LOG_PREFIX} {}", log_safe(n.as_str().trim())));
            }
        }
    }
}
