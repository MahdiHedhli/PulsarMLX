use pulsar_serve_synthetic::{
    bind_loopback, serve, ActualUsage, AppState, BackendCancellation, BackendDescriptor,
    BackendEvent, BackendEventSender, BackendFailure, BackendFinishReason, BackendMessage,
    BackendRequest, BackendRole, BackendSession, CompletionBackend,
};
use serde_json::Value;
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};
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

struct TestServer {
    address: std::net::SocketAddr,
    token: String,
    state: AppState,
    shutdown: Option<oneshot::Sender<()>>,
    task: tokio::task::JoinHandle<std::io::Result<()>>,
}

impl TestServer {
    async fn start(backend: RecordingBackend) -> Self {
        let token = "semantic-provider-test-token".to_owned();
        let state = AppState::with_backend(token.clone(), Arc::new(backend)).expect("state");
        let listener = bind_loopback(0).await.expect("bind");
        let address = listener.local_addr().expect("address");
        let (shutdown, receiver) = oneshot::channel();
        let task = tokio::spawn(serve(listener, state.clone(), async {
            let _ = receiver.await;
        }));
        Self {
            address,
            token,
            state,
            shutdown: Some(shutdown),
            task,
        }
    }

    async fn request(&self, body: &str, auth: bool) -> (u16, String) {
        let mut request = format!(
            "POST /v1/chat/completions HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n",
            self.address.port(),
            body.len()
        );
        if auth {
            request.push_str(&format!("Authorization: Bearer {}\r\n", self.token));
        }
        request.push_str("\r\n");
        request.push_str(body);
        exchange(self.address, &request).await
    }

    async fn stop(mut self) {
        let _ = self.shutdown.take().expect("shutdown").send(());
        self.task.await.expect("join").expect("serve");
    }
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
