use pulsar_serve_synthetic::{
    bind_loopback, serve, ActualUsage, AppState, BackendCancellation, BackendDescriptor,
    BackendEvent, BackendEventSender, BackendFailure, BackendFinishReason, BackendFuture,
    BackendMessage, BackendRequest, BackendRole, BackendSession, CleanupOwner, CompletionBackend,
    ShutdownOutcome,
};
use serde_json::Value;
use std::future::{pending, Future};
use std::pin::Pin;
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};
use std::task::{Context, Poll};
use std::time::Duration;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::TcpStream;
use tokio::sync::oneshot;

const MODEL: &str = "injected-semantic-test-model";

#[derive(Clone)]
struct RecordingBackend {
    events: Vec<BackendEvent>,
    begin_count: Arc<AtomicUsize>,
    request: Arc<Mutex<Option<BackendRequest>>>,
    hang: bool,
    cancelled: Arc<AtomicBool>,
}

impl RecordingBackend {
    fn scripted(events: Vec<BackendEvent>) -> Self {
        Self {
            events,
            begin_count: Arc::new(AtomicUsize::new(0)),
            request: Arc::new(Mutex::new(None)),
            hang: false,
            cancelled: Arc::new(AtomicBool::new(false)),
        }
    }

    fn hanging() -> Self {
        Self {
            hang: true,
            ..Self::scripted(Vec::new())
        }
    }
}

impl CompletionBackend for RecordingBackend {
    fn descriptor(&self) -> BackendDescriptor {
        BackendDescriptor {
            model_id: MODEL,
            owned_by: "injected-test",
            capabilities: &["chat.completions", "streaming"],
        }
    }

    fn begin(
        &self,
        request: BackendRequest,
        mut cancellation: BackendCancellation,
        sender: BackendEventSender,
    ) -> Result<BackendSession, BackendFailure> {
        self.begin_count.fetch_add(1, Ordering::SeqCst);
        *self.request.lock().expect("request lock") = Some(request);
        let events = self.events.clone();
        let hang = self.hang;
        let cancelled = self.cancelled.clone();
        Ok(BackendSession::new(Box::pin(async move {
            if hang {
                cancellation.cancelled().await;
                cancelled.store(true, Ordering::SeqCst);
                return;
            }
            for event in events {
                tokio::select! {
                    _ = cancellation.cancelled() => {
                        cancelled.store(true, Ordering::SeqCst);
                        return;
                    }
                    result = sender.send(event) => if result.is_err() { return; }
                }
            }
        })))
    }
}

#[derive(Clone, Copy)]
enum LifecycleCompletion {
    ReturnImmediately,
    AwaitCancellation,
    AwaitCancellationThenPending,
}

#[derive(Default)]
struct LifecycleObservations {
    polls: AtomicUsize,
    drops: AtomicUsize,
    returned: AtomicBool,
    sender_dropped: AtomicBool,
    cancellation_wait_returned: AtomicBool,
    cancellation_value_true: AtomicBool,
}

struct ObservedFuture {
    inner: BackendFuture,
    observations: Arc<LifecycleObservations>,
}

impl Future for ObservedFuture {
    type Output = ();

    fn poll(self: Pin<&mut Self>, context: &mut Context<'_>) -> Poll<Self::Output> {
        let this = self.get_mut();
        this.observations.polls.fetch_add(1, Ordering::SeqCst);
        let result = this.inner.as_mut().poll(context);
        if result.is_ready() {
            this.observations.returned.store(true, Ordering::SeqCst);
        }
        result
    }
}

impl Drop for ObservedFuture {
    fn drop(&mut self) {
        self.observations.drops.fetch_add(1, Ordering::SeqCst);
    }
}

#[derive(Clone)]
struct LifecycleBackend {
    events: Vec<BackendEvent>,
    completion: LifecycleCompletion,
    hold_sender_until_test: bool,
    observations: Arc<LifecycleObservations>,
    held_sender: Arc<Mutex<Option<BackendEventSender>>>,
    begin_count: Arc<AtomicUsize>,
}

impl LifecycleBackend {
    fn new(
        events: Vec<BackendEvent>,
        completion: LifecycleCompletion,
        hold_sender_until_test: bool,
    ) -> Self {
        Self {
            events,
            completion,
            hold_sender_until_test,
            observations: Arc::new(LifecycleObservations::default()),
            held_sender: Arc::new(Mutex::new(None)),
            begin_count: Arc::new(AtomicUsize::new(0)),
        }
    }
}

impl CompletionBackend for LifecycleBackend {
    fn descriptor(&self) -> BackendDescriptor {
        BackendDescriptor {
            model_id: MODEL,
            owned_by: "injected-lifecycle-test",
            capabilities: &["chat.completions", "streaming"],
        }
    }

    fn begin(
        &self,
        _request: BackendRequest,
        mut cancellation: BackendCancellation,
        sender: BackendEventSender,
    ) -> Result<BackendSession, BackendFailure> {
        let call = self.begin_count.fetch_add(1, Ordering::SeqCst);
        if call > 0 {
            return Ok(BackendSession::new(Box::pin(async move {
                let _ = sender.send(BackendEvent::AssistantRole).await;
                let _ = sender
                    .send(BackendEvent::Finished {
                        reason: BackendFinishReason::Stop,
                        usage: ActualUsage {
                            prompt_tokens: 1,
                            completion_tokens: 1,
                        },
                    })
                    .await;
            })));
        }
        if self.hold_sender_until_test {
            *self.held_sender.lock().expect("held sender lock") = Some(sender.clone());
        }
        let events = self.events.clone();
        let completion = self.completion;
        let observations = self.observations.clone();
        let inner_observations = observations.clone();
        let inner: BackendFuture = Box::pin(async move {
            for event in events {
                if sender.send(event).await.is_err() {
                    return;
                }
            }
            drop(sender);
            inner_observations
                .sender_dropped
                .store(true, Ordering::SeqCst);
            match completion {
                LifecycleCompletion::ReturnImmediately => {}
                LifecycleCompletion::AwaitCancellation => {
                    cancellation.cancelled().await;
                    inner_observations
                        .cancellation_wait_returned
                        .store(true, Ordering::SeqCst);
                    inner_observations
                        .cancellation_value_true
                        .store(cancellation.is_cancelled(), Ordering::SeqCst);
                }
                LifecycleCompletion::AwaitCancellationThenPending => {
                    cancellation.cancelled().await;
                    inner_observations
                        .cancellation_wait_returned
                        .store(true, Ordering::SeqCst);
                    inner_observations
                        .cancellation_value_true
                        .store(cancellation.is_cancelled(), Ordering::SeqCst);
                    pending::<()>().await;
                }
            }
        });
        Ok(BackendSession::new(Box::pin(ObservedFuture {
            inner,
            observations,
        })))
    }
}

struct TestServer {
    owner: CleanupOwner,
    address: std::net::SocketAddr,
    token: String,
    state: AppState,
    shutdown: Option<oneshot::Sender<()>>,
    task: tokio::task::JoinHandle<std::io::Result<ShutdownOutcome>>,
}

impl TestServer {
    async fn start<B: CompletionBackend + 'static>(backend: B) -> Self {
        let token = "semantic-provider-test-token".to_owned();
        let owner = CleanupOwner::new();
        let state =
            AppState::with_backend(token.clone(), Arc::new(backend), &owner).expect("state");
        let listener = bind_loopback(0).await.expect("bind");
        let address = listener.local_addr().expect("address");
        let (shutdown, receiver) = oneshot::channel();
        let task = tokio::spawn(serve(listener, state.clone(), async {
            let _ = receiver.await;
        }));
        Self {
            owner,
            address,
            token,
            state,
            shutdown: Some(shutdown),
            task,
        }
    }

    async fn request(&self, body: &str, auth: bool) -> (u16, String) {
        request_at(self.address, &self.token, body, auth).await
    }

    fn spawn_request(&self, body: String) -> tokio::task::JoinHandle<(u16, String)> {
        let address = self.address;
        let token = self.token.clone();
        tokio::spawn(async move { request_at(address, &token, &body, true).await })
    }

    fn signal_shutdown(&mut self) {
        if let Some(shutdown) = self.shutdown.take() {
            let _ = shutdown.send(());
        }
    }

    async fn join(self) {
        let shutdown = self.task.await.expect("join").expect("serve");
        let drained = self.owner.drain(Duration::from_secs(2)).await;
        assert!(
            drained.is_complete(),
            "Q_CLEANUP_INCOMPLETE: shutdown={shutdown:?}; drained={drained:?}"
        );
        assert_eq!(drained.snapshot().stream_tasks_pending, 0);
        assert_eq!(drained.snapshot().connection_tasks_pending, 0);
    }

    async fn stop(mut self) {
        self.signal_shutdown();
        self.join().await;
    }
}

async fn request_at(
    address: std::net::SocketAddr,
    token: &str,
    body: &str,
    auth: bool,
) -> (u16, String) {
    let mut request = format!(
            "POST /v1/chat/completions HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n",
            address.port(),
            body.len()
        );
    if auth {
        request.push_str(&format!("Authorization: Bearer {token}\r\n"));
    }
    request.push_str("\r\n");
    request.push_str(body);
    exchange(address, &request).await
}

async fn exchange(address: std::net::SocketAddr, request: &str) -> (u16, String) {
    let mut stream = TcpStream::connect(address).await.expect("connect");
    stream.write_all(request.as_bytes()).await.expect("write");
    let mut raw = Vec::new();
    tokio::time::timeout(Duration::from_secs(5), stream.read_to_end(&mut raw))
        .await
        .expect("deadline")
        .expect("read");
    let split = raw
        .windows(4)
        .position(|part| part == b"\r\n\r\n")
        .expect("headers");
    let head = String::from_utf8_lossy(&raw[..split]);
    let status = head
        .split_whitespace()
        .nth(1)
        .expect("status")
        .parse()
        .expect("number");
    (
        status,
        String::from_utf8_lossy(&raw[split + 4..]).into_owned(),
    )
}

fn body(stream: bool) -> String {
    serde_json::json!({
        "model": MODEL,
        "messages": [
            {"role":"system","content":"policy"},
            {"role":"user","content":"inert-request-marker"}
        ],
        "stream": stream,
        "max_tokens": 7
    })
    .to_string()
}

fn success_events() -> Vec<BackendEvent> {
    vec![
        BackendEvent::AssistantRole,
        BackendEvent::TextDelta("provider café ".into()),
        BackendEvent::TextDelta("🚀".into()),
        BackendEvent::Finished {
            reason: BackendFinishReason::Length,
            usage: ActualUsage {
                prompt_tokens: 41,
                completion_tokens: 13,
            },
        },
    ]
}

fn lifecycle_events(with_terminal: bool) -> Vec<BackendEvent> {
    let mut events = vec![BackendEvent::AssistantRole];
    if with_terminal {
        events.push(BackendEvent::TextDelta("owned-cleanup".into()));
        events.push(BackendEvent::Finished {
            reason: BackendFinishReason::Stop,
            usage: ActualUsage {
                prompt_tokens: 3,
                completion_tokens: 2,
            },
        });
    }
    events
}

async fn wait_for_flag(flag: &AtomicBool, label: &'static str) {
    tokio::time::timeout(Duration::from_secs(1), async {
        while !flag.load(Ordering::SeqCst) {
            tokio::task::yield_now().await;
        }
    })
    .await
    .unwrap_or_else(|_| panic!("timed out waiting for {label}"));
}

async fn within_case<T>(future: impl Future<Output = T>) -> T {
    tokio::time::timeout(Duration::from_secs(3), future)
        .await
        .expect("new semantic case exceeded its 3-second deadline")
}

#[tokio::test]
async fn admission_projection_model_and_provider_usage_are_authoritative() {
    let backend = RecordingBackend::scripted(success_events());
    let server = TestServer::start(backend.clone()).await;
    assert_eq!(server.request(&body(false), false).await.0, 401);
    assert_eq!(backend.begin_count.load(Ordering::SeqCst), 0);

    let invalid = serde_json::json!({"model":MODEL,"messages":[{"role":"user","content":"x"}],"provider_path":"/forbidden"}).to_string();
    assert_eq!(server.request(&invalid, true).await.0, 400);
    assert_eq!(backend.begin_count.load(Ordering::SeqCst), 0);

    let (status, response) = server.request(&body(false), true).await;
    assert_eq!(status, 200);
    let response: Value = serde_json::from_str(&response).expect("json");
    assert_eq!(response["model"], MODEL);
    assert_eq!(
        response["choices"][0]["message"]["content"],
        "provider café 🚀"
    );
    assert_eq!(response["choices"][0]["finish_reason"], "length");
    assert_eq!(response["usage"]["prompt_tokens"], 41);
    assert_eq!(response["usage"]["completion_tokens"], 13);
    assert_eq!(response["usage"]["total_tokens"], 54);

    let projected = backend
        .request
        .lock()
        .expect("request lock")
        .clone()
        .expect("request");
    assert_eq!(projected.model_id, MODEL);
    assert_eq!(projected.max_output_tokens, 7);
    assert_eq!(
        projected.messages[0],
        BackendMessage {
            role: BackendRole::System,
            content: "policy".into()
        }
    );
    assert_eq!(projected.messages[1].role, BackendRole::User);
    server.stop().await;
}

#[tokio::test]
async fn semantic_stream_preserves_multibyte_events_and_model_identity() {
    let server = TestServer::start(RecordingBackend::scripted(success_events())).await;
    let (status, response) = server.request(&body(true), true).await;
    assert_eq!(status, 200);
    assert!(response.contains("provider café "));
    assert!(response.contains("🚀"));
    assert!(response.contains(MODEL));
    assert!(response.contains("finish_reason\":\"length"));
    assert!(response.contains("data: [DONE]\n\n"));
    assert!(!response.contains("\"usage\""));
    server.stop().await;
}

#[tokio::test]
async fn malformed_provider_terminals_never_become_nonstream_success() {
    let finish = BackendEvent::Finished {
        reason: BackendFinishReason::Stop,
        usage: ActualUsage {
            prompt_tokens: 1,
            completion_tokens: 1,
        },
    };
    let cases = vec![
        vec![BackendEvent::AssistantRole],
        vec![
            BackendEvent::TextDelta("wrong-order".into()),
            finish.clone(),
        ],
        vec![BackendEvent::AssistantRole, finish.clone(), finish.clone()],
        vec![
            BackendEvent::AssistantRole,
            BackendEvent::Failed(BackendFailure::Generation),
            finish.clone(),
        ],
        vec![
            BackendEvent::AssistantRole,
            finish,
            BackendEvent::TextDelta("after".into()),
        ],
    ];
    for events in cases {
        let server = TestServer::start(RecordingBackend::scripted(events)).await;
        let (status, response) = server.request(&body(false), true).await;
        assert_eq!(status, 500);
        let response: Value = serde_json::from_str(&response).expect("json");
        assert_eq!(response["error"]["code"], "backend_protocol_error");
        assert_eq!(server.state.metrics().backend_active, 0);
        assert_eq!(
            server.state.metrics().backend_started,
            server.state.metrics().backend_finished
        );
        assert_eq!(server.state.metrics().backend_protocol_failures, 1);
        server.stop().await;
    }
}

#[tokio::test]
async fn post_terminal_stream_output_is_discarded_and_classified_once() {
    let events = vec![
        BackendEvent::AssistantRole,
        BackendEvent::Finished {
            reason: BackendFinishReason::Stop,
            usage: ActualUsage {
                prompt_tokens: 2,
                completion_tokens: 1,
            },
        },
        BackendEvent::TextDelta("must-not-appear".into()),
    ];
    let server = TestServer::start(RecordingBackend::scripted(events)).await;
    let (status, response) = server.request(&body(true), true).await;
    assert_eq!(status, 200);
    assert_eq!(response.matches("data: [DONE]").count(), 1);
    assert!(!response.contains("must-not-appear"));
    assert_eq!(server.state.metrics().backend_protocol_failures, 1);
    server.stop().await;
}

#[tokio::test]
async fn timeout_cancels_owned_provider_before_releasing_permit() {
    let backend = RecordingBackend::hanging();
    let server = TestServer::start(backend.clone()).await;
    let (status, response) = server.request(&body(false), true).await;
    assert_eq!(status, 504);
    let response: Value = serde_json::from_str(&response).expect("json");
    assert_eq!(response["error"]["code"], "generation_timeout");
    assert!(backend.cancelled.load(Ordering::SeqCst));
    let metrics = server.state.metrics();
    assert_eq!(metrics.backend_active, 0);
    assert_eq!(metrics.backend_started, metrics.backend_finished);
    server.stop().await;
}

#[tokio::test]
async fn completed_future_is_observed_before_eof_without_cancellation() {
    for stream in [false, true] {
        within_case(async {
            let backend = LifecycleBackend::new(
                lifecycle_events(true),
                LifecycleCompletion::ReturnImmediately,
                true,
            );
            let server = TestServer::start(backend.clone()).await;
            let request = server.spawn_request(body(stream));
            wait_for_flag(&backend.observations.returned, "provider Ready observation").await;
            drop(
                backend
                    .held_sender
                    .lock()
                    .expect("held sender lock")
                    .take()
                    .expect("held event sender"),
            );
            let (status, response) = request.await.expect("request task");
            assert_eq!(status, 200, "RETURNED_BEFORE_EOF_NO_CANCEL: {response}");
            assert!(backend.observations.returned.load(Ordering::SeqCst));
            assert!(
                !backend
                    .observations
                    .cancellation_wait_returned
                    .load(Ordering::SeqCst),
                "RETURNED_BEFORE_EOF_NO_CANCEL"
            );
            assert!(
                !backend
                    .observations
                    .cancellation_value_true
                    .load(Ordering::SeqCst),
                "RETURNED_BEFORE_EOF_NO_CANCEL"
            );
            assert_eq!(server.state.metrics().backend_cleanup_bound_drops, 0);
            assert_eq!(server.state.metrics().backend_protocol_failures, 0);
            assert_eq!(backend.observations.drops.load(Ordering::SeqCst), 1);
            if stream {
                assert_eq!(response.matches("data: [DONE]").count(), 1);
            } else {
                let response: Value = serde_json::from_str(&response).expect("json");
                assert_eq!(
                    response["choices"][0]["message"]["content"],
                    "owned-cleanup"
                );
            }
            server.stop().await;
        })
        .await;
    }
}

#[tokio::test]
async fn eof_before_return_observes_true_cancellation_and_cooperative_completion() {
    for stream in [false, true] {
        within_case(async {
            let backend = LifecycleBackend::new(
                lifecycle_events(true),
                LifecycleCompletion::AwaitCancellation,
                false,
            );
            let server = TestServer::start(backend.clone()).await;
            let (status, response) = server.request(&body(stream), true).await;
            assert!(
                backend
                    .observations
                    .cancellation_wait_returned
                    .load(Ordering::SeqCst),
                "EOF_BEFORE_RETURN_CANCEL_TRUE"
            );
            assert!(
                backend
                    .observations
                    .cancellation_value_true
                    .load(Ordering::SeqCst),
                "OBSERVED_CANCELLATION_VALUE_TRUE"
            );
            assert_eq!(status, 200, "EOF_BEFORE_RETURN_CANCEL_TRUE: {response}");
            assert!(backend.observations.returned.load(Ordering::SeqCst));
            assert_eq!(server.state.metrics().backend_cleanup_bound_drops, 0);
            if stream {
                assert_eq!(response.matches("data: [DONE]").count(), 1);
                assert!(!response.contains("event: error"));
            }
            server.stop().await;
        })
        .await;
    }
}

#[tokio::test]
async fn missing_terminal_eof_is_protocol_failure_after_cooperative_cleanup() {
    for stream in [false, true] {
        within_case(async {
            let backend = LifecycleBackend::new(
                lifecycle_events(false),
                LifecycleCompletion::AwaitCancellation,
                false,
            );
            let server = TestServer::start(backend.clone()).await;
            let (status, response) = server.request(&body(stream), true).await;
            assert_eq!(status, if stream { 200 } else { 500 });
            assert!(response.contains("backend_protocol_error"), "{response}");
            assert!(
                backend
                    .observations
                    .cancellation_value_true
                    .load(Ordering::SeqCst),
                "OBSERVED_CANCELLATION_VALUE_TRUE"
            );
            assert!(backend.observations.returned.load(Ordering::SeqCst));
            let metrics = server.state.metrics();
            assert_eq!(
                metrics.backend_protocol_failures, 1,
                "MISSING_TERMINAL_IS_PROTOCOL"
            );
            assert_eq!(metrics.backend_cleanup_bound_drops, 0);
            if stream {
                assert_eq!(response.matches("event: error").count(), 1);
                assert!(!response.contains("data: [DONE]"));
            }
            server.stop().await;
        })
        .await;
    }
}

#[tokio::test]
async fn uncooperative_valid_eof_drops_future_before_release_and_preserves_wire_precedence() {
    for stream in [false, true] {
        within_case(async {
            let backend = LifecycleBackend::new(
                lifecycle_events(true),
                LifecycleCompletion::AwaitCancellationThenPending,
                false,
            );
            let server = TestServer::start(backend.clone()).await;
            let first = server.spawn_request(body(stream));
            wait_for_flag(
                &backend.observations.cancellation_value_true,
                "true cancellation before cleanup bound",
            )
            .await;
            let during = server.state.metrics();
            assert_eq!(during.backend_active, 1, "permit released before cleanup");
            assert_eq!(during.backend_finished, 0, "permit released before cleanup");
            assert_eq!(during.backend_cleanup_bound_drops, 0);
            assert_eq!(backend.observations.drops.load(Ordering::SeqCst), 0);
            assert_eq!(server.request(&body(false), true).await.0, 429);
            assert_eq!(backend.begin_count.load(Ordering::SeqCst), 1);

            let (status, response) = first.await.expect("first request task");
            if stream {
                assert_eq!(status, 200);
                assert_eq!(
                    response.matches("data: [DONE]").count(),
                    1,
                    "ONE_STREAM_TERMINAL_MAX"
                );
                assert!(!response.contains("event: error"));
            } else {
                assert_eq!(status, 504);
                let response: Value = serde_json::from_str(&response).expect("json");
                assert_eq!(response["error"]["code"], "generation_timeout");
            }
            assert_eq!(
                backend.observations.drops.load(Ordering::SeqCst),
                1,
                "FUTURE_DESTRUCTOR_BEFORE_RELEASE"
            );
            let metrics = server.state.metrics();
            assert_eq!(
                metrics.backend_cleanup_bound_drops, 1,
                "CLEANUP_DROP_METRIC_EXACT"
            );
            assert_eq!(metrics.backend_protocol_failures, 0);
            assert_eq!(metrics.backend_active, 0);
            assert_eq!(metrics.backend_started, metrics.backend_finished);
            let polls_after_release = backend.observations.polls.load(Ordering::SeqCst);
            tokio::time::sleep(Duration::from_millis(100)).await;
            assert_eq!(
                backend.observations.polls.load(Ordering::SeqCst),
                polls_after_release,
                "NO_POST_RELEASE_POLLS"
            );
            assert_eq!(
                server.state.metrics().backend_cleanup_bound_drops,
                1,
                "NO_SECOND_CLEANUP_AFTER_DROP"
            );

            let (status, _) = server.request(&body(false), true).await;
            assert_eq!(status, 200, "permit was not reusable after cleanup");
            assert_eq!(backend.begin_count.load(Ordering::SeqCst), 2);
            let metrics = server.state.metrics();
            assert_eq!(metrics.backend_started, 2);
            assert_eq!(metrics.backend_finished, 2, "COUNTERS_BALANCED");
            assert_eq!(metrics.backend_cleanup_bound_drops, 1);
            server.stop().await;
        })
        .await;
    }
}

#[tokio::test]
async fn uncooperative_missing_terminal_counts_protocol_and_cleanup_once() {
    for stream in [false, true] {
        within_case(async {
            let backend = LifecycleBackend::new(
                lifecycle_events(false),
                LifecycleCompletion::AwaitCancellationThenPending,
                false,
            );
            let server = TestServer::start(backend.clone()).await;
            let (status, response) = server.request(&body(stream), true).await;
            assert_eq!(status, if stream { 200 } else { 500 });
            assert!(response.contains("backend_protocol_error"), "{response}");
            assert_eq!(
                backend.observations.drops.load(Ordering::SeqCst),
                1,
                "FUTURE_DESTRUCTOR_BEFORE_RELEASE"
            );
            assert!(
                backend
                    .observations
                    .cancellation_value_true
                    .load(Ordering::SeqCst),
                "OBSERVED_CANCELLATION_VALUE_TRUE"
            );
            let metrics = server.state.metrics();
            assert_eq!(metrics.backend_protocol_failures, 1);
            assert_eq!(metrics.backend_cleanup_bound_drops, 1);
            assert_eq!(metrics.backend_started, metrics.backend_finished);
            if stream {
                assert_eq!(response.matches("event: error").count(), 1);
                assert!(!response.contains("data: [DONE]"));
            }
            server.stop().await;
        })
        .await;
    }
}

#[tokio::test]
async fn shutdown_signal_racing_closed_event_channel_keeps_eof_cleanup_owned() {
    for stream in [false, true] {
        within_case(async {
            let backend = LifecycleBackend::new(
                lifecycle_events(true),
                LifecycleCompletion::AwaitCancellation,
                false,
            );
            let mut server = TestServer::start(backend.clone()).await;
            let request = server.spawn_request(body(stream));
            wait_for_flag(&backend.observations.sender_dropped, "event sender drop").await;
            server.signal_shutdown();
            let (status, response) = request.await.expect("request task");
            assert_eq!(
                status, 200,
                "EOF wins the biased closed-channel race: {response}"
            );
            assert!(
                backend
                    .observations
                    .cancellation_value_true
                    .load(Ordering::SeqCst),
                "OBSERVED_CANCELLATION_VALUE_TRUE"
            );
            assert!(backend.observations.returned.load(Ordering::SeqCst));
            assert_eq!(server.state.metrics().backend_cleanup_bound_drops, 0);
            server.join().await;
        })
        .await;
    }
}

#[tokio::test]
async fn provider_usage_round_trips_exactly_through_largest_representable_total() {
    assert_eq!(usize::BITS, 64, "the recorded arm64 wire boundary is u64");
    let cases = [(0usize, 0usize), (41, 13), (usize::MAX - 1, 1)];
    for (prompt_tokens, completion_tokens) in cases {
        within_case(async {
            let events = vec![
                BackendEvent::AssistantRole,
                BackendEvent::Finished {
                    reason: BackendFinishReason::Stop,
                    usage: ActualUsage {
                        prompt_tokens,
                        completion_tokens,
                    },
                },
            ];
            let server = TestServer::start(RecordingBackend::scripted(events)).await;
            let (status, response) = server.request(&body(false), true).await;
            assert_eq!(status, 200, "USAGE_JSON_EXACT: {response}");
            let response: Value = serde_json::from_str(&response).expect("json");
            assert_eq!(
                response["usage"]["prompt_tokens"].as_u64(),
                Some(prompt_tokens as u64)
            );
            assert_eq!(
                response["usage"]["completion_tokens"].as_u64(),
                Some(completion_tokens as u64)
            );
            assert_eq!(
                response["usage"]["total_tokens"].as_u64(),
                Some(
                    prompt_tokens
                        .checked_add(completion_tokens)
                        .expect("representable") as u64
                ),
                "USAGE_JSON_EXACT"
            );
            server.stop().await;
        })
        .await;
    }
}

#[tokio::test]
async fn usage_overflow_is_safe_protocol_failure_in_both_response_modes() {
    assert_eq!(
        ActualUsage {
            prompt_tokens: usize::MAX,
            completion_tokens: 1,
        }
        .total_tokens(),
        None
    );
    for stream in [false, true] {
        within_case(async {
            let events = vec![
                BackendEvent::AssistantRole,
                BackendEvent::Finished {
                    reason: BackendFinishReason::Stop,
                    usage: ActualUsage {
                        prompt_tokens: usize::MAX,
                        completion_tokens: 1,
                    },
                },
            ];
            let server = TestServer::start(RecordingBackend::scripted(events)).await;
            let (status, response) = server.request(&body(stream), true).await;
            assert_eq!(status, if stream { 200 } else { 500 });
            assert!(
                response.contains("backend_protocol_error"),
                "USAGE_OVERFLOW_IS_PROTOCOL: {response}"
            );
            assert!(!response.contains("total_tokens"));
            if stream {
                assert_eq!(response.matches("event: error").count(), 1);
                assert!(!response.contains("data: [DONE]"));
            }
            let metrics = server.state.metrics();
            assert_eq!(metrics.backend_protocol_failures, 1);
            assert_eq!(metrics.backend_cleanup_bound_drops, 0);
            server.stop().await;
        })
        .await;
    }
}
