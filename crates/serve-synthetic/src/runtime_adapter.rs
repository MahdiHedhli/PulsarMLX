//! Injected model-free synchronous sessions. No engine, tokenizer or model I/O.
//!
//! The caller retains CleanupOwner; AppState and semantic futures cannot own it.
use crate::{
    ActualUsage, BackendCancellation, BackendDescriptor, BackendEvent, BackendEventSender,
    BackendFailure, BackendFinishReason, BackendMessage, BackendRequest, BackendSession,
    CompletionBackend, MAX_BACKEND_OUTPUT_BYTES,
};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread::JoinHandle;
use std::time::Duration;
use tokio::sync::mpsc;

pub const MAX_RUNTIME_PROMPT_IDS: usize = 4096;

pub struct GeneratedToken {
    /// Zero-based callback ordinal, distinct from a repeatable vocabulary ID.
    pub sequence: usize,
    pub id: u32,
    pub bytes: Vec<u8>,
    /// A stopping ID is observed but excluded from completion usage/text.
    pub stopping: bool,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum RuntimeStop {
    Stop,
    Length,
    Cancelled,
}

pub struct CancelProbe(Arc<AtomicBool>);
impl CancelProbe {
    pub fn is_cancelled(&self) -> bool {
        self.0.load(Ordering::SeqCst)
    }
}

pub trait RuntimeSession: Send + 'static {
    /// Explicit fixture IDs, not character/message counts or a GLM template.
    fn render(&mut self, messages: &[BackendMessage]) -> Result<Vec<u32>, BackendFailure>;
    fn generate(
        &mut self,
        prompt: &[u32],
        maximum: u16,
        cancel: &CancelProbe,
        emit: &mut dyn FnMut(GeneratedToken) -> Result<(), BackendFailure>,
    ) -> Result<RuntimeStop, BackendFailure>;
}

pub trait RuntimeSessionFactory: Send + Sync + 'static {
    fn create(&self) -> Result<Box<dyn RuntimeSession>, BackendFailure>;
}

pub struct RuntimeBackend {
    descriptor: BackendDescriptor,
    factory: Arc<dyn RuntimeSessionFactory>,
}
impl RuntimeBackend {
    pub fn new(descriptor: BackendDescriptor, factory: Arc<dyn RuntimeSessionFactory>) -> Self {
        Self {
            descriptor,
            factory,
        }
    }
}

type Outcome = Result<RuntimeStop, BackendFailure>;
pub(crate) struct Worker {
    owner: Mutex<Option<crate::DrainHandle>>,
    started: AtomicBool,
    starting: AtomicBool,
    joining: AtomicBool,
    session: Arc<Mutex<Option<Box<dyn RuntimeSession>>>>,
    handle: Mutex<Option<JoinHandle<()>>>,
    outcome: Arc<Mutex<Option<Outcome>>>,
    cancel: Arc<AtomicBool>,
    joined: AtomicBool,
    actual_joined: AtomicBool,
    producer_returned: Arc<AtomicBool>,
}
impl Worker {
    fn new(session: Box<dyn RuntimeSession>) -> Self {
        Self {
            owner: Mutex::new(None),
            started: AtomicBool::new(false),
            starting: AtomicBool::new(false),
            joining: AtomicBool::new(false),
            session: Arc::new(Mutex::new(Some(session))),
            handle: Mutex::new(None),
            outcome: Arc::new(Mutex::new(None)),
            cancel: Arc::new(AtomicBool::new(false)),
            joined: AtomicBool::new(false),
            actual_joined: AtomicBool::new(false),
            producer_returned: Arc::new(AtomicBool::new(false)),
        }
    }
    pub(crate) fn request_cancel(&self) {
        self.cancel.store(true, Ordering::SeqCst);
    }
    pub(crate) fn register(&self, owner: crate::DrainHandle) {
        *self.owner.lock().expect("worker owner") = Some(owner);
    }
    pub(crate) fn request_reap(&self) {
        let owner = self.owner.lock().expect("worker owner").clone();
        if let Some(owner) = owner {
            owner.reap();
        }
    }
    pub(crate) fn has_started(&self) -> bool {
        self.started.load(Ordering::SeqCst)
    }
    pub(crate) fn is_joined(&self) -> bool {
        self.joined.load(Ordering::SeqCst)
    }
    pub(crate) fn join_finished(&self) -> bool {
        if self.joined.load(Ordering::SeqCst) {
            return true;
        }
        if self
            .joining
            .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
            .is_err()
        {
            return false;
        }
        struct Reset<'a>(&'a AtomicBool);
        impl Drop for Reset<'_> {
            fn drop(&mut self) {
                self.0.store(false, Ordering::SeqCst);
            }
        }
        let _reset = Reset(&self.joining);
        if self.starting.load(Ordering::SeqCst) {
            return false;
        }
        let mut handle = self.handle.lock().expect("worker handle mutex");
        if handle.is_none() {
            // CREATED cancellation may destroy user/native state. Run that
            // destructor on an owned thread too, never under a mutex or on the
            // async executor. A spawn refusal retains the session and capacity.
            drop(handle);
            if self.session.lock().expect("worker session mutex").is_none() {
                self.joined.store(true, Ordering::SeqCst);
                return true;
            }
            let slot = self.session.clone();
            let launched = std::thread::Builder::new()
                .name("synthetic-session-drop".into())
                .spawn(move || {
                    let session = slot.lock().expect("worker session mutex").take();
                    drop(session);
                });
            if let Ok(handle) = launched {
                self.started.store(true, Ordering::SeqCst);
                *self.handle.lock().expect("worker handle mutex") = Some(handle);
            }
            return false;
        }
        if !handle.as_ref().expect("worker handle").is_finished() {
            return false;
        }
        // Only an already exited thread may be joined on this async thread.
        let exited = handle.take().expect("worker handle");
        drop(handle);
        let result = exited.join();
        self.actual_joined.store(true, Ordering::SeqCst);
        if result.is_err() {
            *self.outcome.lock().expect("worker outcome mutex") =
                Some(Err(BackendFailure::Generation));
        }
        self.joined.store(true, Ordering::SeqCst);
        true
    }
    pub(crate) fn actually_joined(&self) -> bool {
        self.actual_joined.load(Ordering::SeqCst)
    }
    pub(crate) fn producer_returned(&self) -> bool {
        self.producer_returned.load(Ordering::SeqCst)
    }
    fn start(
        &self,
        prompt: Vec<u32>,
        maximum: u16,
        output: mpsc::Sender<GeneratedToken>,
    ) -> Result<(), BackendFailure> {
        let owner = self.owner.lock().expect("worker owner").clone();
        if !owner.as_ref().is_some_and(|owner| owner.is_alive())
            || self.joined.load(Ordering::SeqCst)
            || self
                .starting
                .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
                .is_err()
        {
            return Err(BackendFailure::Generation);
        }
        struct ResetStarting<'a>(&'a AtomicBool);
        impl Drop for ResetStarting<'_> {
            fn drop(&mut self) {
                self.0.store(false, Ordering::SeqCst);
            }
        }
        let _reset_starting = ResetStarting(&self.starting);
        if self.joining.load(Ordering::SeqCst) || self.joined.load(Ordering::SeqCst) {
            return Err(BackendFailure::Generation);
        }
        if self.started.swap(true, Ordering::SeqCst) {
            self.starting.store(false, Ordering::SeqCst);
            return Err(BackendFailure::Generation);
        }
        let session_slot = self.session.clone();
        let cancel = self.cancel.clone();
        let outcome = self.outcome.clone();
        let producer_returned = self.producer_returned.clone();
        let launched = std::thread::Builder::new()
            .name("synthetic-runtime".into())
            .spawn(move || {
                let Some(mut session) = session_slot.lock().expect("worker session mutex").take()
                else {
                    *outcome.lock().expect("worker outcome mutex") =
                        Some(Err(BackendFailure::Generation));
                    return;
                };
                let probe = CancelProbe(cancel);
                let mut emit = |mut token| loop {
                    if probe.is_cancelled() {
                        return Err(BackendFailure::Generation);
                    }
                    match output.try_send(token) {
                        Ok(()) => return Ok(()),
                        Err(mpsc::error::TrySendError::Closed(_)) => {
                            return Err(BackendFailure::Generation)
                        }
                        Err(mpsc::error::TrySendError::Full(returned)) => token = returned,
                    }
                    std::thread::sleep(Duration::from_millis(1));
                };
                let result = session.generate(&prompt, maximum, &probe, &mut emit);
                producer_returned.store(true, Ordering::SeqCst);
                drop(output); // Raw EOF can precede the session destructor/thread exit.
                drop(session);
                *outcome.lock().expect("worker outcome mutex") = Some(result);
            })
            .map_err(|_| BackendFailure::Generation);
        match launched {
            Ok(handle) => {
                *self.handle.lock().expect("worker handle mutex") = Some(handle);
                self.starting.store(false, Ordering::SeqCst);
                Ok(())
            }
            Err(error) => {
                self.starting.store(false, Ordering::SeqCst);
                Err(error)
            }
        }
    }
}

struct CancelOnDrop(Arc<Worker>);
impl Drop for CancelOnDrop {
    fn drop(&mut self) {
        self.0.request_cancel();
    }
}

async fn send(
    events: &BackendEventSender,
    event: BackendEvent,
    cancellation: &mut BackendCancellation,
) -> bool {
    tokio::select! {
        biased;
        _ = cancellation.cancelled() => false,
        result = events.send(event) => result.is_ok(),
    }
}

impl CompletionBackend for RuntimeBackend {
    fn descriptor(&self) -> BackendDescriptor {
        self.descriptor
    }
    fn begin(
        &self,
        request: BackendRequest,
        mut cancellation: BackendCancellation,
        events: BackendEventSender,
    ) -> Result<BackendSession, BackendFailure> {
        let mut session = self.factory.create()?;
        let prompt = session.render(&request.messages)?;
        if prompt.len() > MAX_RUNTIME_PROMPT_IDS {
            return Err(BackendFailure::Generation);
        }
        let prompt_count = prompt.len();
        let worker = Arc::new(Worker::new(session));
        let owned = worker.clone();
        let future = Box::pin(async move {
            let _cancel_on_drop = CancelOnDrop(owned.clone());
            let (tx, mut rx) = mpsc::channel(4);
            if owned.start(prompt, request.max_output_tokens, tx).is_err() {
                return;
            }
            if !send(&events, BackendEvent::AssistantRole, &mut cancellation).await {
                owned.request_cancel();
                return;
            }
            let mut observed = 0usize;
            let mut completion_count = 0usize;
            let mut pending = Vec::new();
            let mut text_bytes = 0usize;
            let mut stopping_seen = false;
            let mut failed = false;
            loop {
                let token = tokio::select! {
                    biased;
                    _ = cancellation.cancelled() => { owned.request_cancel(); break; },
                    token = rx.recv() => token,
                };
                let Some(token) = token else {
                    break;
                };
                if stopping_seen || token.sequence != observed {
                    failed = true;
                    break;
                }
                observed = match observed.checked_add(1) {
                    Some(n) => n,
                    None => {
                        failed = true;
                        break;
                    }
                };
                let _actual_id = token.id; // Sequence, not vocabulary identity, detects replay/drop.
                if token.stopping {
                    if !token.bytes.is_empty() {
                        failed = true;
                        break;
                    }
                    stopping_seen = true;
                    continue;
                }
                completion_count = match completion_count.checked_add(1) {
                    Some(n) => n,
                    None => {
                        failed = true;
                        break;
                    }
                };
                if completion_count > usize::from(request.max_output_tokens) {
                    failed = true;
                    break;
                }
                text_bytes = match text_bytes.checked_add(token.bytes.len()) {
                    Some(n) => n,
                    None => {
                        failed = true;
                        break;
                    }
                };
                if text_bytes > MAX_BACKEND_OUTPUT_BYTES {
                    failed = true;
                    break;
                }
                pending.extend(token.bytes);
                let valid = match std::str::from_utf8(&pending) {
                    Ok(_) => pending.len(),
                    Err(e) if e.error_len().is_none() => e.valid_up_to(),
                    Err(_) => {
                        failed = true;
                        break;
                    }
                };
                if valid > 0 {
                    let delta = String::from_utf8(pending.drain(..valid).collect())
                        .expect("validated UTF8");
                    if !send(&events, BackendEvent::TextDelta(delta), &mut cancellation).await {
                        owned.request_cancel();
                        break;
                    }
                }
            }
            drop(rx);
            if failed || cancellation.is_cancelled() {
                owned.request_cancel();
            }
            loop {
                owned.request_reap();
                if owned.is_joined() {
                    break;
                }
                if cancellation.is_cancelled() {
                    owned.request_cancel();
                }
                tokio::time::sleep(Duration::from_millis(2)).await;
            }
            if cancellation.is_cancelled() {
                return;
            }
            let outcome = owned.outcome.lock().expect("worker outcome mutex").take();
            let event = if failed || !pending.is_empty() {
                BackendEvent::Failed(BackendFailure::Protocol)
            } else {
                match outcome {
                    Some(Ok(RuntimeStop::Length))
                        if completion_count != usize::from(request.max_output_tokens)
                            || stopping_seen =>
                    {
                        BackendEvent::Failed(BackendFailure::Protocol)
                    }
                    Some(Ok(RuntimeStop::Stop | RuntimeStop::Length)) => {
                        let usage = ActualUsage {
                            prompt_tokens: prompt_count,
                            completion_tokens: completion_count,
                        };
                        if usage.total_tokens().is_none() {
                            BackendEvent::Failed(BackendFailure::Protocol)
                        } else {
                            BackendEvent::Finished {
                                reason: if matches!(outcome, Some(Ok(RuntimeStop::Stop))) {
                                    BackendFinishReason::Stop
                                } else {
                                    BackendFinishReason::Length
                                },
                                usage,
                            }
                        }
                    }
                    _ => BackendEvent::Failed(BackendFailure::Generation),
                }
            };
            let _ = send(&events, event, &mut cancellation).await;
        });
        Ok(BackendSession {
            future,
            worker: Some(worker),
        })
    }
}

#[cfg(test)]
mod ownership_tests {
    use super::*;
    use crate::{AppState, CleanupOwner, GenerationGuard};
    #[derive(Default)]
    struct Spy {
        entered: AtomicBool,
        release: AtomicBool,
        cancelled: AtomicBool,
        destroyed: AtomicBool,
    }
    struct Session {
        spy: Arc<Spy>,
        eof: bool,
        cooperative: bool,
    }
    impl RuntimeSession for Session {
        fn render(&mut self, _: &[BackendMessage]) -> Result<Vec<u32>, BackendFailure> {
            Ok(vec![4, 5])
        }
        fn generate(
            &mut self,
            _: &[u32],
            _: u16,
            probe: &CancelProbe,
            _: &mut dyn FnMut(GeneratedToken) -> Result<(), BackendFailure>,
        ) -> Outcome {
            self.spy.entered.store(true, Ordering::SeqCst);
            if !self.eof {
                while !self.spy.release.load(Ordering::SeqCst) {
                    if probe.is_cancelled() {
                        self.spy.cancelled.store(true, Ordering::SeqCst);
                        if self.cooperative {
                            break;
                        }
                    }
                    std::thread::sleep(Duration::from_millis(1));
                }
            }
            Ok(RuntimeStop::Stop)
        }
    }
    impl Drop for Session {
        fn drop(&mut self) {
            while self.eof && !self.spy.release.load(Ordering::SeqCst) {
                std::thread::sleep(Duration::from_millis(1));
            }
            self.spy.destroyed.store(true, Ordering::SeqCst);
        }
    }
    struct Factory {
        spy: Arc<Spy>,
        eof: bool,
        cooperative: bool,
    }
    impl RuntimeSessionFactory for Factory {
        fn create(&self) -> Result<Box<dyn RuntimeSession>, BackendFailure> {
            Ok(Box::new(Session {
                spy: self.spy.clone(),
                eof: self.eof,
                cooperative: self.cooperative,
            }))
        }
    }
    async fn scenario(eof: bool, cooperative: bool) {
        let spy = Arc::new(Spy::default());
        let owner = CleanupOwner::new();
        let state = AppState::new("unit-fixture-auth-123456789".into(), &owner).unwrap();
        let backend = RuntimeBackend::new(
            BackendDescriptor {
                model_id: "unit",
                owned_by: "unit",
                capabilities: &[],
            },
            Arc::new(Factory {
                spy: spy.clone(),
                eof,
                cooperative,
            }),
        );
        let (_cancel, cancellation) = BackendCancellation::pair();
        let (tx, _rx) = mpsc::channel(4);
        let session = backend
            .begin(
                BackendRequest {
                    model_id: "unit".into(),
                    messages: vec![],
                    max_output_tokens: 3,
                },
                cancellation,
                tx,
            )
            .unwrap();
        let worker = session.worker.clone().unwrap();
        let permit = state.generation_slots.clone().try_acquire_owned().unwrap();
        let mut guard = GenerationGuard::new(state.clone(), permit);
        guard.attach_worker(Some(worker.clone()));
        let task = tokio::spawn(async move {
            let _guard = guard;
            session.future.await;
        });
        tokio::time::timeout(Duration::from_secs(1), async {
            while !spy.entered.load(Ordering::SeqCst) || (eof && !worker.producer_returned()) {
                tokio::time::sleep(Duration::from_millis(2)).await;
            }
        })
        .await
        .unwrap();
        task.abort();
        let _ = task.await;
        // Record the oracle before the independent controller opens the barrier.
        let held = state.generation_slots.available_permits() == 0;
        let no_false_finish = state.metrics().backend_finished == 0;
        tokio::time::sleep(Duration::from_millis(30)).await;
        let cancellation_observed = spy.cancelled.load(Ordering::SeqCst);
        spy.release.store(true, Ordering::SeqCst);
        // Always await actual exit and join the retained real handle before
        // asserting the pre-release observation, even in a semantic mutant.
        tokio::time::timeout(Duration::from_secs(1), async {
            loop {
                let finished = worker
                    .handle
                    .lock()
                    .unwrap()
                    .as_ref()
                    .is_none_or(JoinHandle::is_finished);
                if finished {
                    break;
                }
                tokio::time::sleep(Duration::from_millis(2)).await;
            }
        })
        .await
        .unwrap();
        owner.reap();
        assert!(worker.is_joined());
        assert!(worker.actually_joined());
        state.reap_cleanup();
        assert!(spy.destroyed.load(Ordering::SeqCst));
        assert!(held && no_false_finish, "HELD_UNTIL_REAL_JOIN");
        assert_eq!(
            state.generation_slots.available_permits(),
            1,
            "NO_DOUBLE_CAPACITY_RELEASE"
        );
        assert_eq!(state.metrics().backend_finished, 1);
        if cooperative {
            assert!(cancellation_observed, "CANCEL_PROBE_OBSERVED");
        }
    }
    #[tokio::test]
    async fn eof_is_not_join() {
        scenario(true, false).await;
    }
    #[tokio::test]
    async fn async_drop_preserves_owned_join() {
        scenario(false, false).await;
    }
    #[tokio::test]
    async fn cancellation_probe_reaches_sync_session() {
        scenario(false, true).await;
    }

    #[tokio::test]
    async fn undrained_semantic_channel_backpressures_and_drop_joins() {
        use std::sync::atomic::AtomicUsize;
        struct Session {
            emitted: Arc<AtomicUsize>,
            destroyed: Arc<AtomicBool>,
        }
        impl Drop for Session {
            fn drop(&mut self) {
                self.destroyed.store(true, Ordering::SeqCst);
            }
        }
        impl RuntimeSession for Session {
            fn render(&mut self, _: &[BackendMessage]) -> Result<Vec<u32>, BackendFailure> {
                Ok(vec![1])
            }
            fn generate(
                &mut self,
                _: &[u32],
                maximum: u16,
                _: &CancelProbe,
                emit: &mut dyn FnMut(GeneratedToken) -> Result<(), BackendFailure>,
            ) -> Outcome {
                for n in 0..usize::from(maximum) {
                    self.emitted.fetch_add(1, Ordering::SeqCst);
                    emit(GeneratedToken {
                        sequence: n,
                        id: n as u32,
                        bytes: vec![b'x'],
                        stopping: false,
                    })?;
                }
                Ok(RuntimeStop::Length)
            }
        }
        struct Factory {
            emitted: Arc<AtomicUsize>,
            destroyed: Arc<AtomicBool>,
        }
        impl RuntimeSessionFactory for Factory {
            fn create(&self) -> Result<Box<dyn RuntimeSession>, BackendFailure> {
                Ok(Box::new(Session {
                    emitted: self.emitted.clone(),
                    destroyed: self.destroyed.clone(),
                }))
            }
        }
        let emitted = Arc::new(AtomicUsize::new(0));
        let destroyed = Arc::new(AtomicBool::new(false));
        let owner = CleanupOwner::new();
        let state = AppState::new("backpressure-fixture-auth-123456".into(), &owner).unwrap();
        let backend = RuntimeBackend::new(
            BackendDescriptor {
                model_id: "fixture",
                owned_by: "fixture",
                capabilities: &[],
            },
            Arc::new(Factory {
                emitted: emitted.clone(),
                destroyed: destroyed.clone(),
            }),
        );
        let (_cancel, cancellation) = BackendCancellation::pair();
        let (tx, _undrained) = mpsc::channel(1);
        let session = backend
            .begin(
                BackendRequest {
                    model_id: "fixture".into(),
                    messages: vec![],
                    max_output_tokens: 16,
                },
                cancellation,
                tx,
            )
            .unwrap();
        let worker = session.worker.clone().unwrap();
        let permit = state.generation_slots.clone().try_acquire_owned().unwrap();
        let mut guard = GenerationGuard::new(state.clone(), permit);
        guard.attach_worker(Some(worker.clone()));
        let task = tokio::spawn(async move {
            let _guard = guard;
            session.future.await;
        });
        tokio::time::timeout(Duration::from_secs(1), async {
            while emitted.load(Ordering::SeqCst) < 6 {
                tokio::time::sleep(Duration::from_millis(2)).await;
            }
        })
        .await
        .unwrap();
        let count = emitted.load(Ordering::SeqCst);
        let held = state.generation_slots.available_permits() == 0;
        task.abort();
        let _ = task.await;
        tokio::time::timeout(Duration::from_secs(1), async {
            while worker
                .handle
                .lock()
                .unwrap()
                .as_ref()
                .is_some_and(|handle| !handle.is_finished())
            {
                tokio::time::sleep(Duration::from_millis(2)).await;
            }
        })
        .await
        .unwrap();
        owner.reap();
        assert!(worker.is_joined());
        state.reap_cleanup();
        assert_eq!(count, 6, "BOUNDED_BACKPRESSURE");
        assert!(held && destroyed.load(Ordering::SeqCst));
        assert_eq!(state.metrics().runtime_workers_joined, 1);
        assert_eq!(state.generation_slots.available_permits(), 1);
    }
}
