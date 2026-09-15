//! Caller-owned, acyclic supervision. Request capabilities never own this graph.
use crate::runtime_adapter::Worker;
use crate::{Metrics, MetricsSnapshot, MAX_GENERATIONS, SHUTDOWN_POLL};
use std::future::Future;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex, Weak};
use std::time::Duration;
use tokio::sync::{watch, OwnedSemaphorePermit, Semaphore};
use tokio::task::JoinSet;

pub struct CleanupOwner {
    core: Arc<Core>,
}

#[derive(Clone)]
pub struct DrainHandle {
    core: Weak<Core>,
    metrics: Arc<Metrics>,
}

impl std::fmt::Debug for DrainHandle {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("DrainHandle")
            .field("owner_alive", &(self.core.strong_count() != 0))
            .finish()
    }
}

#[derive(Debug)]
pub enum ShutdownOutcome {
    Complete(MetricsSnapshot),
    Incomplete(PendingCleanup),
}

#[derive(Debug)]
pub struct PendingCleanup {
    pub snapshot: MetricsSnapshot,
    pub drain: DrainHandle,
}

impl ShutdownOutcome {
    pub fn snapshot(&self) -> MetricsSnapshot {
        match self {
            Self::Complete(snapshot) => *snapshot,
            Self::Incomplete(pending) => pending.snapshot,
        }
    }
    pub fn is_complete(&self) -> bool {
        matches!(self, Self::Complete(_))
    }
}

struct Core {
    entries: Mutex<Vec<Entry>>,
    reaping: AtomicBool,
    server_running: AtomicBool,
    metrics: Arc<Metrics>,
    slots: Arc<Semaphore>,
    streams: Mutex<JoinSet<()>>,
    connections: Mutex<JoinSet<()>>,
}

struct Entry {
    ticket: Arc<Ticket>,
    _permit: OwnedSemaphorePermit,
    join_counted: bool,
}

pub(crate) struct Ticket {
    release: AtomicBool,
    worker: Mutex<Option<Arc<Worker>>>,
}

pub(crate) struct GenerationGuard {
    owner: DrainHandle,
    ticket: Arc<Ticket>,
}

impl Default for CleanupOwner {
    fn default() -> Self {
        Self::new()
    }
}

impl CleanupOwner {
    pub fn new() -> Self {
        Self {
            core: Arc::new(Core {
                entries: Mutex::new(Vec::new()),
                reaping: AtomicBool::new(false),
                server_running: AtomicBool::new(false),
                metrics: Arc::new(Metrics::default()),
                slots: Arc::new(Semaphore::new(MAX_GENERATIONS)),
                streams: Mutex::new(JoinSet::new()),
                connections: Mutex::new(JoinSet::new()),
            }),
        }
    }
    pub fn handle(&self) -> DrainHandle {
        DrainHandle {
            core: Arc::downgrade(&self.core),
            metrics: self.core.metrics.clone(),
        }
    }
    pub fn metrics(&self) -> MetricsSnapshot {
        self.handle().metrics()
    }
    pub fn reap(&self) {
        self.core.reap();
    }
    pub async fn drain(&self, timeout: Duration) -> ShutdownOutcome {
        self.handle().drain(timeout).await
    }
    pub fn cancel_tasks(&self) {
        self.core.cancel_tasks();
    }
    pub fn available_capacity(&self) -> usize {
        self.core.slots.available_permits()
    }
    pub(crate) fn slots(&self) -> Arc<Semaphore> {
        self.core.slots.clone()
    }
    pub(crate) fn metric_storage(&self) -> Arc<Metrics> {
        self.core.metrics.clone()
    }
}

impl DrainHandle {
    pub(crate) fn is_alive(&self) -> bool {
        self.core.strong_count() != 0
    }
    pub(crate) fn register(&self, permit: OwnedSemaphorePermit) -> Option<GenerationGuard> {
        let core = self.core.upgrade()?;
        let ticket = Arc::new(Ticket {
            release: AtomicBool::new(false),
            worker: Mutex::new(None),
        });
        core.metrics.backend_started.fetch_add(1, Ordering::SeqCst);
        core.metrics.backend_active.fetch_add(1, Ordering::SeqCst);
        core.entries
            .lock()
            .expect("generation registry")
            .push(Entry {
                ticket: ticket.clone(),
                _permit: permit,
                join_counted: false,
            });
        Some(GenerationGuard {
            owner: self.clone(),
            ticket,
        })
    }
    pub fn reap(&self) {
        if let Some(core) = self.core.upgrade() {
            core.reap();
        }
    }
    pub fn metrics(&self) -> MetricsSnapshot {
        let mut snapshot = self.metrics.snapshot();
        if let Some(core) = self.core.upgrade() {
            let entries = core.entries.lock().expect("generation registry");
            for entry in entries.iter() {
                if entry.ticket.release.load(Ordering::SeqCst) {
                    if let Some(worker) =
                        entry.ticket.worker.lock().expect("worker ticket").as_ref()
                    {
                        snapshot.runtime_cleanup_pending += 1;
                        if worker.producer_returned() && !worker.is_joined() {
                            snapshot.runtime_producers_returned_unjoined += 1;
                        }
                    }
                }
            }
            drop(entries);
            snapshot.cleanup_owner_alive = true;
            snapshot.cleanup_join_in_progress = core.reaping.load(Ordering::SeqCst);
            snapshot.server_running = core.server_running.load(Ordering::SeqCst);
            snapshot.stream_tasks_pending = core.streams.lock().expect("stream registry").len();
            snapshot.connection_tasks_pending =
                core.connections.lock().expect("connection registry").len();
        }
        snapshot
    }
    pub async fn drain(&self, timeout: Duration) -> ShutdownOutcome {
        let deadline = tokio::time::Instant::now() + timeout;
        loop {
            self.reap();
            let snapshot = self.metrics();
            if snapshot.cleanup_owner_alive
                && !snapshot.cleanup_join_in_progress
                && !snapshot.server_running
                && snapshot.backend_active == 0
                && snapshot.stream_tasks_pending == 0
                && snapshot.connection_tasks_pending == 0
            {
                return ShutdownOutcome::Complete(snapshot);
            }
            if tokio::time::Instant::now() >= deadline || !snapshot.cleanup_owner_alive {
                return ShutdownOutcome::Incomplete(PendingCleanup {
                    snapshot,
                    drain: self.clone(),
                });
            }
            tokio::time::sleep(SHUTDOWN_POLL).await;
        }
    }
    pub(crate) fn spawn_stream(&self, future: impl Future<Output = ()> + Send + 'static) -> bool {
        let Some(core) = self.core.upgrade() else {
            return false;
        };
        core.streams.lock().expect("stream registry").spawn(future);
        true
    }
    pub(crate) fn spawn_connection(&self, future: impl Future<Output = ()> + Send + 'static) {
        if let Some(core) = self.core.upgrade() {
            core.connections
                .lock()
                .expect("connection registry")
                .spawn(future);
        }
    }
    pub(crate) fn begin_server(&self, shutdown: watch::Sender<bool>) -> Option<ServerGuard> {
        let core = self.core.upgrade()?;
        core.server_running
            .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
            .ok()?;
        Some(ServerGuard {
            owner: self.clone(),
            shutdown,
        })
    }
}

pub(crate) struct ServerGuard {
    owner: DrainHandle,
    shutdown: watch::Sender<bool>,
}

impl Drop for ServerGuard {
    fn drop(&mut self) {
        self.shutdown.send_replace(true);
        if let Some(core) = self.owner.core.upgrade() {
            core.server_running.store(false, Ordering::SeqCst);
            core.cancel_tasks();
            core.reap();
        }
    }
}

impl GenerationGuard {
    #[cfg(test)]
    pub(crate) fn new(state: crate::AppState, permit: OwnedSemaphorePermit) -> Self {
        state
            .cleanup
            .register(permit)
            .expect("reachable cleanup owner")
    }
    pub(crate) fn attach_worker(&mut self, worker: Option<Arc<Worker>>) {
        if let Some(worker) = &worker {
            worker.register(self.owner.clone());
        }
        *self.ticket.worker.lock().expect("worker ticket") = worker;
    }
}

impl Drop for GenerationGuard {
    fn drop(&mut self) {
        self.ticket.release.store(true, Ordering::SeqCst);
        let worker = self.ticket.worker.lock().expect("worker ticket").clone();
        if let Some(worker) = worker {
            worker.request_cancel();
        }
        self.owner.reap();
    }
}

impl Core {
    fn cancel_tasks(&self) {
        let workers: Vec<_> = self
            .entries
            .lock()
            .expect("generation registry")
            .iter()
            .filter_map(|entry| entry.ticket.worker.lock().expect("worker ticket").clone())
            .collect();
        for worker in workers {
            worker.request_cancel();
        }
        self.connections
            .lock()
            .expect("connection registry")
            .abort_all();
        self.streams.lock().expect("stream registry").abort_all();
    }
    fn reap(&self) {
        if self
            .reaping
            .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
            .is_err()
        {
            return;
        }
        struct Reset<'a>(&'a AtomicBool);
        impl Drop for Reset<'_> {
            fn drop(&mut self) {
                self.0.store(false, Ordering::SeqCst);
            }
        }
        let _reset = Reset(&self.reaping);
        let entries = std::mem::take(&mut *self.entries.lock().expect("generation registry"));
        let mut retained = Vec::new();
        for mut entry in entries {
            let worker = entry.ticket.worker.lock().expect("worker ticket").clone();
            let released = entry.ticket.release.load(Ordering::SeqCst);
            let joined = match &worker {
                Some(worker) if worker.has_started() || released => worker.join_finished(),
                Some(_) => false,
                None => true,
            };
            if worker
                .as_ref()
                .is_some_and(|worker| worker.actually_joined())
                && !entry.join_counted
            {
                self.metrics
                    .runtime_workers_joined
                    .fetch_add(1, Ordering::SeqCst);
                entry.join_counted = true;
            }
            if released && joined {
                self.metrics.backend_active.fetch_sub(1, Ordering::SeqCst);
                self.metrics.backend_finished.fetch_add(1, Ordering::SeqCst);
                drop(entry); // No registry lock across user/session/permit destruction.
            } else {
                retained.push(entry);
            }
        }
        self.entries
            .lock()
            .expect("generation registry")
            .extend(retained);
        loop {
            let finished = self
                .connections
                .lock()
                .expect("connection registry")
                .try_join_next();
            let Some(result) = finished else {
                break;
            };
            self.metrics
                .connections_reaped
                .fetch_add(1, Ordering::SeqCst);
            drop(result);
        }
        loop {
            let finished = self
                .streams
                .lock()
                .expect("stream registry")
                .try_join_next();
            let Some(result) = finished else {
                break;
            };
            drop(result);
        }
    }
}

impl Drop for Core {
    fn drop(&mut self) {
        // Arbitrary final supervisor abandonment is outside qualified recovery.
        // Do not block, fabricate joins, detach a reaper, or return live capacity.
        let entries = std::mem::take(self.entries.get_mut().expect("generation registry"));
        let mut outstanding = 0;
        for entry in entries {
            let worker = entry.ticket.worker.lock().expect("worker ticket").clone();
            if let Some(worker) = &worker {
                worker.request_cancel();
            }
            let released = entry.ticket.release.load(Ordering::SeqCst);
            let joined = worker.as_ref().is_none_or(|worker| worker.is_joined());
            if released && joined {
                if worker
                    .as_ref()
                    .is_some_and(|worker| worker.actually_joined())
                    && !entry.join_counted
                {
                    self.metrics
                        .runtime_workers_joined
                        .fetch_add(1, Ordering::SeqCst);
                }
                self.metrics.backend_active.fetch_sub(1, Ordering::SeqCst);
                self.metrics.backend_finished.fetch_add(1, Ordering::SeqCst);
                drop(entry);
            } else {
                outstanding += 1;
                std::mem::forget(entry); // Deliberately retain the unjoined handle AND permit.
            }
        }
        let streams = self.streams.get_mut().expect("stream registry");
        let connections = self.connections.get_mut().expect("connection registry");
        streams.abort_all();
        connections.abort_all();
        let tasks = streams.len() + connections.len();
        if outstanding != 0 || tasks != 0 {
            eprintln!("pulsar-serve-synthetic: cleanup owner abandoned INCOMPLETE ({outstanding} retained leases, {tasks} unjoined tasks); process-supervised reclamation unqualified");
            std::mem::forget(std::mem::take(streams));
            std::mem::forget(std::mem::take(connections));
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::runtime_adapter::{
        CancelProbe, GeneratedToken, RuntimeBackend, RuntimeSession, RuntimeSessionFactory,
        RuntimeStop,
    };
    use crate::{
        AppState, BackendCancellation, BackendDescriptor, BackendFailure, BackendMessage,
        BackendRequest, CompletionBackend,
    };

    struct Probe {
        handle: DrainHandle,
        entered: AtomicBool,
        release: AtomicBool,
        destroyed: AtomicBool,
        reentrant_incomplete: AtomicBool,
        panic_drop: bool,
    }
    struct Session(Arc<Probe>);
    impl Drop for Session {
        fn drop(&mut self) {
            self.0.entered.store(true, Ordering::SeqCst);
            self.0.handle.reap();
            self.0.reentrant_incomplete.store(
                self.0.handle.metrics().backend_active == 1,
                Ordering::SeqCst,
            );
            while !self.0.release.load(Ordering::SeqCst) {
                std::thread::sleep(Duration::from_millis(1));
            }
            self.0.destroyed.store(true, Ordering::SeqCst);
            assert!(
                !self.0.panic_drop,
                "controlled CREATED session destructor unwind"
            );
        }
    }
    impl RuntimeSession for Session {
        fn render(&mut self, _: &[BackendMessage]) -> Result<Vec<u32>, BackendFailure> {
            Ok(vec![1])
        }
        fn generate(
            &mut self,
            _: &[u32],
            _: u16,
            _: &CancelProbe,
            _: &mut dyn FnMut(GeneratedToken) -> Result<(), BackendFailure>,
        ) -> Result<RuntimeStop, BackendFailure> {
            panic!("CREATED fixture must not launch")
        }
    }
    struct Factory(Arc<Probe>);
    impl RuntimeSessionFactory for Factory {
        fn create(&self) -> Result<Box<dyn RuntimeSession>, BackendFailure> {
            Ok(Box::new(Session(self.0.clone())))
        }
    }
    async fn created_destructor(panic_drop: bool) {
        let owner = Arc::new(CleanupOwner::new());
        let weak_core = Arc::downgrade(&owner.core);
        let probe = Arc::new(Probe {
            handle: owner.handle(),
            entered: AtomicBool::new(false),
            release: AtomicBool::new(false),
            destroyed: AtomicBool::new(false),
            reentrant_incomplete: AtomicBool::new(false),
            panic_drop,
        });
        let backend = RuntimeBackend::new(
            BackendDescriptor {
                model_id: "created",
                owned_by: "fixture",
                capabilities: &[],
            },
            Arc::new(Factory(probe.clone())),
        );
        let state = AppState::new("created-fixture-auth-12345".into(), &owner).unwrap();
        let (_, cancellation) = BackendCancellation::pair();
        let (events, _rx) = tokio::sync::mpsc::channel(4);
        let session = backend
            .begin(
                BackendRequest {
                    model_id: "created".into(),
                    messages: vec![],
                    max_output_tokens: 1,
                },
                cancellation,
                events,
            )
            .unwrap();
        let worker = session.worker.clone().unwrap();
        let mut guard = state
            .cleanup
            .register(owner.core.slots.clone().try_acquire_owned().unwrap())
            .unwrap();
        guard.attach_worker(Some(worker.clone()));
        drop(session.future);
        drop(state);
        drop(backend);
        let (stop, wait) = std::sync::mpsc::channel();
        let outer_probe = probe.clone();
        let outer = std::thread::spawn(move || {
            let _ = wait.recv_timeout(Duration::from_secs(3));
            outer_probe.release.store(true, Ordering::SeqCst);
        });
        let reaper = std::thread::spawn(move || drop(guard));
        let entered = tokio::time::timeout(Duration::from_secs(1), async {
            while !probe.entered.load(Ordering::SeqCst) {
                tokio::time::sleep(Duration::from_millis(2)).await;
            }
        })
        .await
        .is_ok();
        let pending = owner.drain(Duration::from_millis(20)).await;
        let held = owner.available_capacity() == 0;
        probe.release.store(true, Ordering::SeqCst);
        while !reaper.is_finished() {
            tokio::time::sleep(Duration::from_millis(2)).await;
        }
        reaper.join().unwrap();
        let completed = owner.drain(Duration::from_secs(1)).await;
        let again = owner.drain(Duration::from_millis(20)).await;
        let _ = stop.send(());
        while !outer.is_finished() {
            tokio::time::sleep(Duration::from_millis(2)).await;
        }
        outer.join().unwrap();
        let available = owner.available_capacity();
        drop(owner);
        assert!(
            entered
                && held
                && !pending.is_complete()
                && pending.snapshot().backend_active == 1
                && pending.snapshot().runtime_workers_joined == 0,
            "REENTRANT_DESTRUCTOR_IS_INCOMPLETE"
        );
        assert!(
            probe.reentrant_incomplete.load(Ordering::SeqCst),
            "NO_MUTEX_ACROSS_REENTRANT_USER_DROP"
        );
        assert!(probe.destroyed.load(Ordering::SeqCst) && worker.is_joined());
        assert!(worker.actually_joined());
        assert!(completed.is_complete() && again.is_complete());
        assert_eq!(again.snapshot().backend_finished, 1);
        assert_eq!(available, 1);
        assert!(
            weak_core.upgrade().is_none(),
            "ACYCLIC_OWNER_RECLAIMED_AFTER_DRAIN"
        );
    }
    #[tokio::test]
    async fn reentrant_created_drop_and_concurrent_drain() {
        created_destructor(false).await;
    }
    #[tokio::test]
    async fn created_destructor_unwind_releases_once() {
        created_destructor(true).await;
    }

    #[tokio::test]
    async fn unregistered_public_runtime_session_cannot_launch_worker() {
        let owner = CleanupOwner::new();
        let probe = Arc::new(Probe {
            handle: owner.handle(),
            entered: AtomicBool::new(false),
            release: AtomicBool::new(true),
            destroyed: AtomicBool::new(false),
            reentrant_incomplete: AtomicBool::new(false),
            panic_drop: false,
        });
        let backend = RuntimeBackend::new(
            BackendDescriptor {
                model_id: "unregistered",
                owned_by: "fixture",
                capabilities: &[],
            },
            Arc::new(Factory(probe.clone())),
        );
        let (_, cancellation) = BackendCancellation::pair();
        let (events, mut rx) = tokio::sync::mpsc::channel(4);
        let session = backend
            .begin(
                BackendRequest {
                    model_id: "unregistered".into(),
                    messages: vec![],
                    max_output_tokens: 1,
                },
                cancellation,
                events,
            )
            .unwrap();
        let worker = session.worker.clone().unwrap();
        session.future.await;
        drop(session.worker);
        assert!(
            !worker.has_started() && !worker.actually_joined(),
            "UNOWNED_RUNTIME_START_REFUSED"
        );
        assert!(rx.recv().await.is_none());
        drop(worker);
        drop(backend);
        assert!(probe.destroyed.load(Ordering::SeqCst));
        assert_eq!(owner.metrics().backend_started, 0);
        assert!(owner.drain(Duration::from_millis(20)).await.is_complete());
    }
}
