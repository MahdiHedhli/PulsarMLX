use bytes::Bytes;
use http_body_util::{BodyExt, Full, StreamBody};
use hyper::body::{Frame, Incoming};
use hyper::header::{AUTHORIZATION, CONTENT_LENGTH, CONTENT_TYPE, HOST, ORIGIN};
use hyper::server::conn::http1;
use hyper::service::service_fn;
use hyper::{Method, Request, Response, StatusCode};
use hyper_util::rt::{TokioIo, TokioTimer};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::convert::Infallible;
use std::future::Future;
use std::io::Read;
use std::net::{IpAddr, Ipv4Addr, SocketAddr};
use std::path::Path;
use std::sync::atomic::{AtomicU64, AtomicUsize, Ordering};
use std::sync::Arc;
use std::time::Duration;
use tokio::net::TcpListener;
use tokio::sync::{mpsc, watch, OwnedSemaphorePermit, Semaphore};
use tokio::task::JoinSet;
use tokio_stream::wrappers::ReceiverStream;

mod backend;
pub use backend::{
    ActualUsage, BackendCancellation, BackendDescriptor, BackendEvent, BackendEventSender,
    BackendFailure, BackendFinishReason, BackendFuture, BackendMessage, BackendRequest,
    BackendRole, BackendSession, CompletionBackend, MAX_BACKEND_EVENTS, MAX_BACKEND_OUTPUT_BYTES,
};
use backend::{SyntheticBackend, BACKEND_EVENT_CAPACITY};

pub const MODEL_ID: &str = "pulsarmlx-synthetic-v1";
pub const MAX_HEADER_BYTES: usize = 8 * 1024;
pub const MAX_BODY_BYTES: usize = 16 * 1024;
pub const MAX_MESSAGES: usize = 16;
pub const MAX_MESSAGE_BYTES: usize = 2 * 1024;
pub const MAX_OUTPUT_TOKENS: u16 = 16;
pub const MAX_CONNECTIONS: usize = 32;
pub const MAX_GENERATIONS: usize = 1;
/// Consecutive `accept` failures tolerated before the listener is treated as
/// broken. Bounded so a permanently unusable listener still terminates rather
/// than spinning forever.
pub const MAX_CONSECUTIVE_ACCEPT_ERRORS: usize = 64;
/// Pause after a failed `accept`, so descriptor exhaustion backs off instead of
/// busy-looping while connections drain.
pub const ACCEPT_ERROR_BACKOFF: Duration = Duration::from_millis(10);
/// Bounded window after the shutdown signal in which active stream producers
/// may still flush their terminal `server_shutdown` event. Without it,
/// `abort_all` drops the response bodies first and the event is never
/// deliverable, which would make the documented shutdown contract false.
pub const SHUTDOWN_GRACE: Duration = Duration::from_millis(250);
/// Poll interval while waiting out `SHUTDOWN_GRACE`.
const SHUTDOWN_POLL: Duration = Duration::from_millis(2);
pub const HEADER_DEADLINE: Duration = Duration::from_secs(5);
pub const CONNECTION_DEADLINE: Duration = Duration::from_secs(15);
pub const GENERATION_DEADLINE: Duration = Duration::from_secs(2);
pub const STREAM_SEND_DEADLINE: Duration = Duration::from_millis(500);

pub type BoxBody = http_body_util::combinators::BoxBody<Bytes, Infallible>;

#[derive(Clone)]
pub struct AppState {
    token: Arc<[u8]>,
    backend: Arc<dyn CompletionBackend>,
    descriptor: BackendDescriptor,
    generation_slots: Arc<Semaphore>,
    next_id: Arc<AtomicU64>,
    metrics: Arc<Metrics>,
    shutdown: watch::Sender<bool>,
}

#[derive(Default)]
pub struct Metrics {
    backend_started: AtomicUsize,
    backend_active: AtomicUsize,
    backend_finished: AtomicUsize,
    backend_protocol_failures: AtomicUsize,
    connections_spawned: AtomicUsize,
    connections_reaped: AtomicUsize,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct MetricsSnapshot {
    pub backend_started: usize,
    pub backend_active: usize,
    pub backend_finished: usize,
    pub backend_protocol_failures: usize,
    /// Connection tasks handed to the accept loop's `JoinSet`.
    pub connections_spawned: usize,
    /// Connection tasks joined and removed from that set. F1 requires this to
    /// track `connections_spawned` during normal operation, not only at
    /// shutdown.
    pub connections_reaped: usize,
}

impl AppState {
    pub fn new(token: String) -> Result<Self, &'static str> {
        Self::with_backend(token, Arc::new(SyntheticBackend))
    }

    pub fn with_backend(
        token: String,
        backend: Arc<dyn CompletionBackend>,
    ) -> Result<Self, &'static str> {
        let token = token.into_bytes();
        if token.len() < 16 || token.len() > 256 || token.iter().any(u8::is_ascii_whitespace) {
            return Err("synthetic token must be 16..=256 non-whitespace bytes");
        }
        let (shutdown, _) = watch::channel(false);
        let descriptor = backend.descriptor();
        if descriptor.model_id.is_empty() {
            return Err("backend model identifier must not be empty");
        }
        Ok(Self {
            token: token.into(),
            backend,
            descriptor,
            generation_slots: Arc::new(Semaphore::new(MAX_GENERATIONS)),
            next_id: Arc::new(AtomicU64::new(1)),
            metrics: Arc::new(Metrics::default()),
            shutdown,
        })
    }

    pub fn metrics(&self) -> MetricsSnapshot {
        MetricsSnapshot {
            backend_started: self.metrics.backend_started.load(Ordering::SeqCst),
            backend_active: self.metrics.backend_active.load(Ordering::SeqCst),
            backend_finished: self.metrics.backend_finished.load(Ordering::SeqCst),
            backend_protocol_failures: self
                .metrics
                .backend_protocol_failures
                .load(Ordering::SeqCst),
            connections_spawned: self.metrics.connections_spawned.load(Ordering::SeqCst),
            connections_reaped: self.metrics.connections_reaped.load(Ordering::SeqCst),
        }
    }
}

pub fn read_token_file(path: &Path) -> Result<String, String> {
    let path_metadata =
        std::fs::symlink_metadata(path).map_err(|_| "cannot read token file metadata")?;
    if path_metadata.file_type().is_symlink() || !path_metadata.is_file() {
        return Err("token file must be a regular non-symlink file".into());
    }
    let mut file = std::fs::File::open(path).map_err(|_| "cannot open token file")?;
    let metadata = file
        .metadata()
        .map_err(|_| "cannot read opened token file metadata")?;
    if !metadata.is_file() {
        return Err("token file must be a regular non-symlink file".into());
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::{MetadataExt, PermissionsExt};
        if path_metadata.dev() != metadata.dev() || path_metadata.ino() != metadata.ino() {
            return Err("token file changed while opening".into());
        }
        if metadata.permissions().mode() & 0o777 != 0o600 {
            return Err("token file permissions must be 0600".into());
        }
    }
    if metadata.len() > 257 {
        return Err("token file is too large".into());
    }
    let mut token = String::new();
    file.read_to_string(&mut token)
        .map_err(|_| "cannot read token file")?;
    let token = token.strip_suffix('\n').unwrap_or(&token);
    AppState::new(token.to_owned()).map_err(str::to_owned)?;
    Ok(token.to_owned())
}

pub async fn bind_loopback(port: u16) -> std::io::Result<TcpListener> {
    TcpListener::bind(SocketAddr::new(IpAddr::V4(Ipv4Addr::LOCALHOST), port)).await
}

pub async fn serve<F>(listener: TcpListener, state: AppState, shutdown: F) -> std::io::Result<()>
where
    F: Future<Output = ()>,
{
    let expected_port = listener.local_addr()?.port();
    let connection_slots = Arc::new(Semaphore::new(MAX_CONNECTIONS));
    let mut tasks = JoinSet::new();
    let mut consecutive_accept_errors = 0usize;
    tokio::pin!(shutdown);

    loop {
        tokio::select! {
            _ = &mut shutdown => break,
            // F1: reap finished connection tasks during normal operation so
            // completed JoinHandles do not accumulate for the process lifetime.
            // The `!tasks.is_empty()` guard disables the branch when the set is
            // empty, which would otherwise return `None` immediately and spin.
            Some(_) = tasks.join_next(), if !tasks.is_empty() => {
                state.metrics.connections_reaped.fetch_add(1, Ordering::SeqCst);
            }
            accepted = listener.accept() => {
                // F8: a transient per-connection failure - a peer that vanished
                // between the SYN and the accept, or descriptor exhaustion under
                // load - previously propagated and terminated the whole
                // listener. Back off and continue instead, but give up once the
                // failures stop looking transient so a genuinely broken listener
                // is still reported.
                let (stream, peer) = match accepted {
                    Ok(accepted) => {
                        consecutive_accept_errors = 0;
                        accepted
                    }
                    Err(error) => {
                        consecutive_accept_errors += 1;
                        if !accept_error_is_recoverable(consecutive_accept_errors) {
                            return Err(error);
                        }
                        // Stay responsive to shutdown while backing off.
                        let mut shutting_down = false;
                        tokio::select! {
                            _ = tokio::time::sleep(ACCEPT_ERROR_BACKOFF) => {}
                            _ = &mut shutdown => shutting_down = true,
                        }
                        if shutting_down {
                            break;
                        }
                        continue;
                    }
                };
                if !peer.ip().is_loopback() { continue; }
                let Ok(connection_permit) = connection_slots.clone().try_acquire_owned() else {
                    continue;
                };
                let app = state.clone();
                state.metrics.connections_spawned.fetch_add(1, Ordering::SeqCst);
                tasks.spawn(async move {
                    let service = service_fn(move |request| handle(request, app.clone(), expected_port));
                    let mut builder = http1::Builder::new();
                    builder
                        .keep_alive(false)
                        .timer(TokioTimer::new())
                        .header_read_timeout(HEADER_DEADLINE)
                        .max_buf_size(32 * 1024);
                    let connection = builder.serve_connection(TokioIo::new(stream), service);
                    let _permit = connection_permit;
                    let _ = tokio::time::timeout(CONNECTION_DEADLINE, connection).await;
                });
            }
        }
    }
    state.shutdown.send_replace(true);
    // Wait only while generations are actually in flight, and never longer than
    // SHUTDOWN_GRACE, so a quiet server still shuts down immediately.
    let deadline = tokio::time::Instant::now() + SHUTDOWN_GRACE;
    while state.metrics.backend_active.load(Ordering::SeqCst) > 0
        && tokio::time::Instant::now() < deadline
    {
        tokio::time::sleep(SHUTDOWN_POLL).await;
    }
    tasks.abort_all();
    while tasks.join_next().await.is_some() {
        state
            .metrics
            .connections_reaped
            .fetch_add(1, Ordering::SeqCst);
    }
    Ok(())
}

async fn handle(
    request: Request<Incoming>,
    state: AppState,
    expected_port: u16,
) -> Result<Response<BoxBody>, Infallible> {
    let response = handle_inner(request, state, expected_port).await;
    Ok(response)
}

async fn handle_inner(
    request: Request<Incoming>,
    state: AppState,
    expected_port: u16,
) -> Response<BoxBody> {
    if header_bytes(request.headers()) > MAX_HEADER_BYTES {
        return api_error(
            StatusCode::REQUEST_HEADER_FIELDS_TOO_LARGE,
            "headers_too_large",
            "request headers exceed the limit",
        );
    }
    if !valid_host(request.headers(), expected_port) {
        return api_error(StatusCode::FORBIDDEN, "invalid_host", "Host is not allowed");
    }
    if !valid_origin(request.headers().get(ORIGIN), request.headers().get(HOST)) {
        return api_error(
            StatusCode::FORBIDDEN,
            "invalid_origin",
            "cross-origin request rejected",
        );
    }

    let path = request.uri().path().to_owned();
    let method = request.method().clone();
    if path == "/health" {
        return if method == Method::GET {
            json_response(StatusCode::OK, json!({"status":"ok","synthetic":true}))
        } else {
            api_error(
                StatusCode::METHOD_NOT_ALLOWED,
                "method_not_allowed",
                "method not allowed",
            )
        };
    }

    if !path.starts_with("/v1/") {
        return api_error(StatusCode::NOT_FOUND, "not_found", "route not found");
    }
    if !valid_auth(request.headers().get(AUTHORIZATION), &state.token) {
        return api_error(
            StatusCode::UNAUTHORIZED,
            "invalid_api_key",
            "missing or invalid bearer token",
        );
    }

    match (method, path.as_str()) {
        (Method::GET, "/v1/models") => json_response(
            StatusCode::OK,
            json!({
                "object":"list",
                "data":[{"id":state.descriptor.model_id,"object":"model","created":1789000000_u64,"owned_by":state.descriptor.owned_by,"capabilities":state.descriptor.capabilities}]
            }),
        ),
        (Method::POST, "/v1/chat/completions") => chat(request, state).await,
        (Method::GET | Method::POST, "/v1/models" | "/v1/chat/completions") => api_error(
            StatusCode::METHOD_NOT_ALLOWED,
            "method_not_allowed",
            "method not allowed",
        ),
        _ => api_error(StatusCode::NOT_FOUND, "not_found", "route not found"),
    }
}

async fn chat(request: Request<Incoming>, state: AppState) -> Response<BoxBody> {
    let is_json = request
        .headers()
        .get(CONTENT_TYPE)
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.split(';').next())
        .is_some_and(|v| v.trim().eq_ignore_ascii_case("application/json"));
    if !is_json {
        return api_error(
            StatusCode::UNSUPPORTED_MEDIA_TYPE,
            "invalid_content_type",
            "Content-Type must be application/json",
        );
    }
    if let Some(value) = request.headers().get(CONTENT_LENGTH) {
        let Ok(text) = value.to_str() else {
            return api_error(
                StatusCode::BAD_REQUEST,
                "invalid_content_length",
                "invalid Content-Length",
            );
        };
        let Ok(length) = text.parse::<usize>() else {
            return api_error(
                StatusCode::BAD_REQUEST,
                "invalid_content_length",
                "invalid Content-Length",
            );
        };
        if length > MAX_BODY_BYTES {
            return api_error(
                StatusCode::PAYLOAD_TOO_LARGE,
                "body_too_large",
                "request body exceeds the limit",
            );
        }
    }
    let body = match read_body(request.into_body()).await {
        Ok(body) => body,
        Err(response) => return *response,
    };
    let value: Value = match serde_json::from_slice(&body) {
        Ok(value) => value,
        Err(_) => {
            return api_error(
                StatusCode::BAD_REQUEST,
                "invalid_json",
                "request body is not valid supported JSON",
            )
        }
    };
    if has_unsupported_fields(&value) {
        return api_error(
            StatusCode::BAD_REQUEST,
            "unsupported_parameter",
            "request contains an unsupported field",
        );
    }
    let parsed: ChatRequest = match serde_json::from_value(value) {
        Ok(value) => value,
        Err(_) => {
            return api_error(
                StatusCode::BAD_REQUEST,
                "invalid_json",
                "request body is not valid supported JSON",
            )
        }
    };
    if let Err((code, message)) = parsed.validate(state.descriptor.model_id) {
        return api_error(StatusCode::BAD_REQUEST, code, message);
    }
    let permit = match state.generation_slots.clone().try_acquire_owned() {
        Ok(permit) => permit,
        Err(_) => {
            return api_error(
                StatusCode::TOO_MANY_REQUESTS,
                "server_busy",
                "synthetic generation capacity is busy",
            )
        }
    };
    let request_id = state.next_id.fetch_add(1, Ordering::SeqCst);
    let completion_id = format!("chatcmpl-synthetic-{request_id:08}");
    let descriptor = state.descriptor;
    let (cancel_sender, cancellation) = BackendCancellation::pair();
    let (event_sender, event_receiver) = mpsc::channel(BACKEND_EVENT_CAPACITY);
    let guard = GenerationGuard::new(state.clone(), permit);
    let session = match state.backend.begin(
        BackendRequest {
            model_id: parsed.model.clone(),
            messages: parsed
                .messages
                .iter()
                .map(|message| BackendMessage {
                    role: (&message.role).into(),
                    content: message.content.clone(),
                })
                .collect(),
            max_output_tokens: parsed.max_tokens.unwrap_or(MAX_OUTPUT_TOKENS),
        },
        cancellation,
        event_sender,
    ) {
        Ok(session) => session,
        Err(error) => {
            drop(guard);
            return backend_error_response(error);
        }
    };
    if parsed.stream {
        stream_chat(
            state,
            guard,
            completion_id,
            descriptor.model_id,
            session,
            event_receiver,
            cancel_sender,
        )
    } else {
        nonstream_chat(
            state,
            guard,
            completion_id,
            descriptor.model_id,
            session,
            event_receiver,
            cancel_sender,
        )
        .await
    }
}

fn has_unsupported_fields(value: &Value) -> bool {
    const REQUEST_FIELDS: &[&str] = &[
        "model",
        "messages",
        "stream",
        "max_tokens",
        "n",
        "temperature",
        "top_p",
    ];
    const MESSAGE_FIELDS: &[&str] = &["role", "content"];
    let Some(object) = value.as_object() else {
        return false;
    };
    if object
        .keys()
        .any(|key| !REQUEST_FIELDS.contains(&key.as_str()))
    {
        return true;
    }
    object
        .get("messages")
        .and_then(Value::as_array)
        .is_some_and(|messages| {
            messages.iter().any(|message| {
                message.as_object().is_some_and(|item| {
                    item.keys()
                        .any(|key| !MESSAGE_FIELDS.contains(&key.as_str()))
                })
            })
        })
}

/// The error variant is boxed so the common `Ok` path does not carry a whole
/// `Response`. Clippy's `result_large_err` reports the unboxed form on
/// toolchains from 1.98 onwards; it was invisible while no CI job ran Clippy
/// against this crate.
async fn read_body(mut body: Incoming) -> Result<Vec<u8>, Box<Response<BoxBody>>> {
    let mut bytes = Vec::new();
    while let Some(frame) = body.frame().await {
        let frame = frame.map_err(|_| {
            Box::new(api_error(
                StatusCode::BAD_REQUEST,
                "invalid_body",
                "request body could not be read",
            ))
        })?;
        if let Some(data) = frame.data_ref() {
            if bytes.len().saturating_add(data.len()) > MAX_BODY_BYTES {
                return Err(Box::new(api_error(
                    StatusCode::PAYLOAD_TOO_LARGE,
                    "body_too_large",
                    "request body exceeds the limit",
                )));
            }
            bytes.extend_from_slice(data);
        }
    }
    Ok(bytes)
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ChatRequest {
    model: String,
    messages: Vec<Message>,
    #[serde(default)]
    stream: bool,
    max_tokens: Option<u16>,
    n: Option<u8>,
    temperature: Option<f64>,
    top_p: Option<f64>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Message {
    /// Constrains the accepted roles at deserialization time: an unknown role
    /// makes the whole request fail to parse. The value is never read
    /// afterwards, which is what the removed `let _ = ...any(matches!(...))`
    /// expression in `validate` was concealing (F8).
    #[allow(dead_code)]
    role: Role,
    content: String,
}

#[derive(Deserialize)]
#[serde(rename_all = "lowercase")]
enum Role {
    System,
    User,
    Assistant,
}

impl From<&Role> for BackendRole {
    fn from(role: &Role) -> Self {
        match role {
            Role::System => Self::System,
            Role::User => Self::User,
            Role::Assistant => Self::Assistant,
        }
    }
}

impl ChatRequest {
    fn validate(&self, model_id: &str) -> Result<(), (&'static str, &'static str)> {
        if self.model != model_id {
            return Err(("model_not_found", "requested model is not available"));
        }
        if self.messages.is_empty() || self.messages.len() > MAX_MESSAGES {
            return Err((
                "invalid_messages",
                "message count is outside the supported range",
            ));
        }
        if self
            .messages
            .iter()
            .any(|m| m.content.len() > MAX_MESSAGE_BYTES)
        {
            return Err(("message_too_large", "a message exceeds the byte limit"));
        }
        if self.max_tokens.unwrap_or(MAX_OUTPUT_TOKENS) == 0
            || self.max_tokens.unwrap_or(MAX_OUTPUT_TOKENS) > MAX_OUTPUT_TOKENS
        {
            return Err((
                "invalid_max_tokens",
                "max_tokens is outside the supported range",
            ));
        }
        if self.n.unwrap_or(1) != 1 {
            return Err(("unsupported_parameter", "only n=1 is supported"));
        }
        if self.temperature.unwrap_or(1.0) != 1.0 || self.top_p.unwrap_or(1.0) != 1.0 {
            return Err(("unsupported_parameter", "sampling controls are unsupported"));
        }
        Ok(())
    }
}

struct GenerationGuard {
    state: AppState,
    _permit: OwnedSemaphorePermit,
}

impl GenerationGuard {
    fn new(state: AppState, permit: OwnedSemaphorePermit) -> Self {
        state.metrics.backend_started.fetch_add(1, Ordering::SeqCst);
        state.metrics.backend_active.fetch_add(1, Ordering::SeqCst);
        Self {
            state,
            _permit: permit,
        }
    }
}

impl Drop for GenerationGuard {
    fn drop(&mut self) {
        self.state
            .metrics
            .backend_active
            .fetch_sub(1, Ordering::SeqCst);
        self.state
            .metrics
            .backend_finished
            .fetch_add(1, Ordering::SeqCst);
    }
}

async fn nonstream_chat(
    state: AppState,
    _guard: GenerationGuard,
    id: String,
    model_id: &'static str,
    mut session: BackendSession,
    mut events: mpsc::Receiver<BackendEvent>,
    cancel: watch::Sender<bool>,
) -> Response<BoxBody> {
    let mut shutdown = state.shutdown.subscribe();
    let deadline = tokio::time::sleep(GENERATION_DEADLINE);
    tokio::pin!(deadline);
    let mut transcript = BackendTranscript::default();
    let mut future_done = false;
    loop {
        if future_done && events.is_empty() {
            break;
        }
        tokio::select! {
            biased;
            event = events.recv() => match event {
                Some(event) => if let Err(error) = transcript.accept(event) {
                    state.metrics.backend_protocol_failures.fetch_add(1, Ordering::SeqCst);
                    cancel_owned_backend(&cancel, &mut session.future, future_done).await;
                    return backend_error_response(error);
                },
                None => future_done = true,
            },
            _ = &mut session.future, if !future_done => future_done = true,
            _ = shutdown.changed() => {
                cancel_owned_backend(&cancel, &mut session.future, future_done).await;
                return api_error(StatusCode::SERVICE_UNAVAILABLE, "server_shutdown", "server is shutting down");
            }
            _ = &mut deadline => {
                cancel_owned_backend(&cancel, &mut session.future, future_done).await;
                return api_error(StatusCode::GATEWAY_TIMEOUT, "generation_timeout", "synthetic generation exceeded its deadline");
            }
        }
    }
    match transcript.finish() {
        Ok((content, reason, usage)) => json_response(
            StatusCode::OK,
            json!({
                "id":id,"object":"chat.completion","created":1789000000_u64,"model":model_id,
                "choices":[{"index":0,"message":{"role":"assistant","content":content},"finish_reason":reason.as_str()}],
                "usage":{"prompt_tokens":usage.prompt_tokens,"completion_tokens":usage.completion_tokens,"total_tokens":usage.total_tokens()}
            }),
        ),
        Err(error) => {
            if error == BackendFailure::Protocol {
                state
                    .metrics
                    .backend_protocol_failures
                    .fetch_add(1, Ordering::SeqCst);
            }
            backend_error_response(error)
        }
    }
}

fn stream_chat(
    state: AppState,
    guard: GenerationGuard,
    id: String,
    model_id: &'static str,
    mut session: BackendSession,
    mut events: mpsc::Receiver<BackendEvent>,
    cancel: watch::Sender<bool>,
) -> Response<BoxBody> {
    let (sender, receiver) = mpsc::channel::<Result<Frame<Bytes>, Infallible>>(1);
    let mut shutdown = state.shutdown.subscribe();
    tokio::spawn(async move {
        let _guard = guard;
        let deadline = tokio::time::sleep(GENERATION_DEADLINE);
        tokio::pin!(deadline);
        let mut transcript = BackendTranscript::default();
        let mut future_done = false;
        let mut wire_terminal = false;
        loop {
            if future_done && events.is_empty() {
                if !transcript.has_terminal() && !wire_terminal {
                    state
                        .metrics
                        .backend_protocol_failures
                        .fetch_add(1, Ordering::SeqCst);
                    let _ = send_backend_error(&sender, BackendFailure::Protocol).await;
                }
                break;
            }
            let event = tokio::select! {
                biased;
                event = events.recv() => event,
                _ = &mut session.future, if !future_done => {
                    future_done = true;
                    continue;
                }
                _ = shutdown.changed() => {
                    cancel_owned_backend(&cancel, &mut session.future, future_done).await;
                    if !wire_terminal {
                        let _ = send_backend_error_code(&sender, "server_shutdown", "server is shutting down").await;
                    }
                    break;
                }
                _ = &mut deadline => {
                    cancel_owned_backend(&cancel, &mut session.future, future_done).await;
                    if !wire_terminal {
                        let _ = send_backend_error_code(&sender, "generation_timeout", "synthetic generation exceeded its deadline").await;
                    }
                    break;
                }
            };
            let Some(event) = event else {
                future_done = true;
                continue;
            };
            let accepted = match transcript.accept(event) {
                Ok(accepted) => accepted,
                Err(error) => {
                    state
                        .metrics
                        .backend_protocol_failures
                        .fetch_add(1, Ordering::SeqCst);
                    cancel_owned_backend(&cancel, &mut session.future, future_done).await;
                    if !wire_terminal {
                        let _ = send_backend_error(&sender, error).await;
                    }
                    break;
                }
            };
            if wire_terminal {
                continue;
            }
            let delivered = match accepted {
                AcceptedEvent::Role => send_sse(&sender, &json!({"id":id,"object":"chat.completion.chunk","created":1789000000_u64,"model":model_id,"choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}]})).await,
                AcceptedEvent::Delta(content) => send_sse(&sender, &json!({"id":id,"object":"chat.completion.chunk","created":1789000000_u64,"model":model_id,"choices":[{"index":0,"delta":{"content":content},"finish_reason":null}]})).await,
                AcceptedEvent::Finished(reason) => {
                    let terminal = send_sse(&sender, &json!({"id":id,"object":"chat.completion.chunk","created":1789000000_u64,"model":model_id,"choices":[{"index":0,"delta":{},"finish_reason":reason.as_str()}]})).await;
                    if terminal {
                        wire_terminal = send_raw(&sender, Bytes::from_static(b"data: [DONE]\n\n")).await;
                    }
                    terminal && wire_terminal
                }
                AcceptedEvent::Failed(error) => {
                    wire_terminal = send_backend_error(&sender, error).await;
                    wire_terminal
                }
            };
            if !delivered {
                cancel_owned_backend(&cancel, &mut session.future, future_done).await;
                break;
            }
        }
        if !future_done {
            cancel_owned_backend(&cancel, &mut session.future, false).await;
        }
    });
    let stream = ReceiverStream::new(receiver);
    let body = StreamBody::new(stream).boxed();
    Response::builder()
        .status(StatusCode::OK)
        .header(CONTENT_TYPE, "text/event-stream")
        .header("cache-control", "no-cache")
        .body(body)
        .expect("valid response")
}

#[derive(Default)]
struct BackendTranscript {
    role_seen: bool,
    terminal: Option<Result<(BackendFinishReason, ActualUsage), BackendFailure>>,
    content: String,
    event_count: usize,
}

enum AcceptedEvent {
    Role,
    Delta(String),
    Finished(BackendFinishReason),
    Failed(BackendFailure),
}

impl BackendTranscript {
    fn accept(&mut self, event: BackendEvent) -> Result<AcceptedEvent, BackendFailure> {
        self.event_count = self.event_count.saturating_add(1);
        if self.event_count > MAX_BACKEND_EVENTS || self.terminal.is_some() {
            return Err(BackendFailure::Protocol);
        }
        match event {
            BackendEvent::AssistantRole if !self.role_seen => {
                self.role_seen = true;
                Ok(AcceptedEvent::Role)
            }
            BackendEvent::TextDelta(content) if self.role_seen => {
                if self.content.len().saturating_add(content.len()) > MAX_BACKEND_OUTPUT_BYTES {
                    return Err(BackendFailure::Protocol);
                }
                self.content.push_str(&content);
                Ok(AcceptedEvent::Delta(content))
            }
            BackendEvent::Finished { reason, usage } if self.role_seen => {
                self.terminal = Some(Ok((reason, usage)));
                Ok(AcceptedEvent::Finished(reason))
            }
            BackendEvent::Failed(error) if self.role_seen => {
                self.terminal = Some(Err(error));
                Ok(AcceptedEvent::Failed(error))
            }
            _ => Err(BackendFailure::Protocol),
        }
    }

    fn has_terminal(&self) -> bool {
        self.terminal.is_some()
    }

    fn finish(self) -> Result<(String, BackendFinishReason, ActualUsage), BackendFailure> {
        match self.terminal {
            Some(Ok((reason, usage))) if self.role_seen => Ok((self.content, reason, usage)),
            Some(Err(error)) => Err(error),
            _ => Err(BackendFailure::Protocol),
        }
    }
}

async fn cancel_owned_backend(
    cancel: &watch::Sender<bool>,
    future: &mut BackendFuture,
    future_done: bool,
) {
    cancel.send_replace(true);
    if !future_done {
        let _ = tokio::time::timeout(STREAM_SEND_DEADLINE, future).await;
    }
}

fn backend_error_response(error: BackendFailure) -> Response<BoxBody> {
    api_error(
        StatusCode::INTERNAL_SERVER_ERROR,
        error.code(),
        error.message(),
    )
}

async fn send_backend_error(
    sender: &mpsc::Sender<Result<Frame<Bytes>, Infallible>>,
    error: BackendFailure,
) -> bool {
    send_backend_error_code(sender, error.code(), error.message()).await
}

async fn send_backend_error_code(
    sender: &mpsc::Sender<Result<Frame<Bytes>, Infallible>>,
    code: &'static str,
    message: &'static str,
) -> bool {
    let error = json!({"error":{"code":code,"message":message,"type":"server_error"}});
    send_event(sender, "error", &error).await
}

async fn send_sse(sender: &mpsc::Sender<Result<Frame<Bytes>, Infallible>>, value: &Value) -> bool {
    send_raw(sender, Bytes::from(format!("data: {}\n\n", value))).await
}

async fn send_event(
    sender: &mpsc::Sender<Result<Frame<Bytes>, Infallible>>,
    event: &str,
    value: &Value,
) -> bool {
    send_raw(
        sender,
        Bytes::from(format!("event: {event}\ndata: {}\n\n", value)),
    )
    .await
}

async fn send_raw(sender: &mpsc::Sender<Result<Frame<Bytes>, Infallible>>, bytes: Bytes) -> bool {
    tokio::time::timeout(STREAM_SEND_DEADLINE, sender.send(Ok(Frame::data(bytes))))
        .await
        .is_ok_and(|r| r.is_ok())
}

/// Whether the accept loop should keep going after `consecutive` consecutive
/// failures. Kept separate from the loop so the give-up boundary is directly
/// testable; forcing a real `EMFILE` in a test is not portable.
fn accept_error_is_recoverable(consecutive: usize) -> bool {
    consecutive <= MAX_CONSECUTIVE_ACCEPT_ERRORS
}

fn header_bytes(headers: &hyper::HeaderMap) -> usize {
    headers.iter().fold(0usize, |total, (name, value)| {
        total
            .saturating_add(name.as_str().len())
            .saturating_add(value.as_bytes().len())
    })
}

/// F8: a second Host header was previously ignored because `get` returns only
/// the first value. Requiring exactly one value rejects the ambiguity instead
/// of choosing an interpretation for the peer.
fn valid_host(headers: &hyper::HeaderMap, expected_port: u16) -> bool {
    let mut values = headers.get_all(HOST).iter();
    let (Some(host), None) = (values.next(), values.next()) else {
        return false;
    };
    let Ok(host) = host.to_str() else {
        return false;
    };
    host == format!("127.0.0.1:{expected_port}") || host == format!("localhost:{expected_port}")
}

fn valid_origin(
    origin: Option<&hyper::header::HeaderValue>,
    host: Option<&hyper::header::HeaderValue>,
) -> bool {
    let Some(origin) = origin else {
        return true;
    };
    let (Some(origin), Some(host)) = (origin.to_str().ok(), host.and_then(|v| v.to_str().ok()))
    else {
        return false;
    };
    origin == format!("http://{host}")
}

fn valid_auth(value: Option<&hyper::header::HeaderValue>, token: &[u8]) -> bool {
    let Some(value) = value else {
        return false;
    };
    let bytes = value.as_bytes();
    let prefix = b"Bearer ";
    if !bytes.starts_with(prefix) {
        return false;
    }
    constant_time_eq(&bytes[prefix.len()..], token)
}

fn constant_time_eq(left: &[u8], right: &[u8]) -> bool {
    if left.len() != right.len() {
        return false;
    }
    left.iter()
        .zip(right)
        .fold(0u8, |diff, (a, b)| diff | (a ^ b))
        == 0
}

fn json_response(status: StatusCode, value: Value) -> Response<BoxBody> {
    let body = Full::new(Bytes::from(value.to_string())).boxed();
    Response::builder()
        .status(status)
        .header(CONTENT_TYPE, "application/json")
        .header("cache-control", "no-store")
        .body(body)
        .expect("valid response")
}

/// F5: OpenAI-style clients branch on `error.type`. Reporting every failure as
/// `invalid_request_error` told an SDK that a 401, a 429 and a 500 were all
/// caller mistakes, so retry and re-authentication logic could not work.
fn error_type(status: StatusCode) -> &'static str {
    match status {
        StatusCode::UNAUTHORIZED => "authentication_error",
        StatusCode::TOO_MANY_REQUESTS => "rate_limit_error",
        status if status.is_server_error() => "server_error",
        _ => "invalid_request_error",
    }
}

fn api_error(status: StatusCode, code: &'static str, message: &'static str) -> Response<BoxBody> {
    json_response(
        status,
        json!({"error":{"code":code,"message":message,"type":error_type(status)}}),
    )
}

#[derive(Serialize)]
pub struct Limits {
    pub max_header_bytes: usize,
    pub max_body_bytes: usize,
    pub max_messages: usize,
    pub max_message_bytes: usize,
    pub max_output_tokens: u16,
    pub max_connections: usize,
    pub max_generations: usize,
}

pub fn limits() -> Limits {
    Limits {
        max_header_bytes: MAX_HEADER_BYTES,
        max_body_bytes: MAX_BODY_BYTES,
        max_messages: MAX_MESSAGES,
        max_message_bytes: MAX_MESSAGE_BYTES,
        max_output_tokens: MAX_OUTPUT_TOKENS,
        max_connections: MAX_CONNECTIONS,
        max_generations: MAX_GENERATIONS,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    struct TestBackend;

    impl CompletionBackend for TestBackend {
        fn descriptor(&self) -> BackendDescriptor {
            BackendDescriptor {
                model_id: "test-constructor-model",
                owned_by: "test-owner",
                capabilities: &["chat.completions"],
            }
        }

        fn begin(
            &self,
            _request: BackendRequest,
            _cancellation: BackendCancellation,
            events: BackendEventSender,
        ) -> Result<BackendSession, BackendFailure> {
            Ok(BackendSession::new(Box::pin(async move {
                let _ = events.send(BackendEvent::AssistantRole).await;
                let _ = events
                    .send(BackendEvent::Finished {
                        reason: BackendFinishReason::Stop,
                        usage: ActualUsage {
                            prompt_tokens: 0,
                            completion_tokens: 0,
                        },
                    })
                    .await;
            })))
        }
    }

    #[test]
    fn backend_is_selected_only_at_state_construction() {
        let state =
            AppState::with_backend("synthetic-test-token-value".into(), Arc::new(TestBackend))
                .expect("valid token");
        assert_eq!(state.descriptor.model_id, "test-constructor-model");
        assert_eq!(state.descriptor.owned_by, "test-owner");
    }

    #[test]
    fn semantic_transcript_retains_provider_usage() {
        let mut transcript = BackendTranscript::default();
        transcript
            .accept(BackendEvent::AssistantRole)
            .expect("role");
        transcript
            .accept(BackendEvent::Finished {
                reason: BackendFinishReason::Stop,
                usage: ActualUsage {
                    prompt_tokens: 17,
                    completion_tokens: 9,
                },
            })
            .expect("finish");
        let (_, _, usage) = transcript.finish().expect("valid transcript");
        assert_eq!(usage.prompt_tokens, 17);
        assert_eq!(usage.completion_tokens, 9);
    }

    #[test]
    fn accept_errors_are_tolerated_then_surrendered() {
        assert!(accept_error_is_recoverable(1));
        assert!(accept_error_is_recoverable(MAX_CONSECUTIVE_ACCEPT_ERRORS));
        assert!(!accept_error_is_recoverable(
            MAX_CONSECUTIVE_ACCEPT_ERRORS + 1
        ));
    }

    #[test]
    fn error_types_map_from_status() {
        assert_eq!(error_type(StatusCode::UNAUTHORIZED), "authentication_error");
        assert_eq!(
            error_type(StatusCode::TOO_MANY_REQUESTS),
            "rate_limit_error"
        );
        assert_eq!(
            error_type(StatusCode::INTERNAL_SERVER_ERROR),
            "server_error"
        );
        assert_eq!(error_type(StatusCode::GATEWAY_TIMEOUT), "server_error");
        assert_eq!(error_type(StatusCode::BAD_REQUEST), "invalid_request_error");
        assert_eq!(error_type(StatusCode::NOT_FOUND), "invalid_request_error");
        assert_eq!(
            error_type(StatusCode::PAYLOAD_TOO_LARGE),
            "invalid_request_error"
        );
    }

    #[test]
    fn utf8_chunks_isolate_multibyte_characters() {
        assert!(backend::utf8_chunks("").is_empty());
        assert_eq!(backend::utf8_chunks("abc"), vec!["abc"]);
        assert_eq!(backend::utf8_chunks("café"), vec!["caf", "é"]);
        assert_eq!(backend::utf8_chunks("éé"), vec!["é", "é"]);
        assert_eq!(backend::utf8_chunks("🚀a"), vec!["🚀", "a"]);
        let content = "SYNTHETIC_OK: café 🚀";
        let chunks = backend::utf8_chunks(content);
        assert_eq!(chunks.concat(), content);
        assert!(chunks.contains(&"é"));
        assert!(chunks.contains(&"🚀"));
    }

    #[tokio::test]
    async fn stream_send_times_out_when_consumer_stalls() {
        let (sender, _receiver) = mpsc::channel(1);
        sender
            .send(Ok(Frame::data(Bytes::from_static(b"first"))))
            .await
            .expect("prefill channel");
        let started = tokio::time::Instant::now();
        assert!(!send_raw(&sender, Bytes::from_static(b"blocked")).await);
        assert!(started.elapsed() >= STREAM_SEND_DEADLINE);
        assert!(started.elapsed() < STREAM_SEND_DEADLINE + Duration::from_secs(1));
    }
}
