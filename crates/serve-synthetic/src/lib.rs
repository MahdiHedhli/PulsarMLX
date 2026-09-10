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

pub const MODEL_ID: &str = "pulsarmlx-synthetic-v1";
pub const MAX_HEADER_BYTES: usize = 8 * 1024;
pub const MAX_BODY_BYTES: usize = 16 * 1024;
pub const MAX_MESSAGES: usize = 16;
pub const MAX_MESSAGE_BYTES: usize = 2 * 1024;
pub const MAX_OUTPUT_TOKENS: u16 = 16;
pub const MAX_CONNECTIONS: usize = 32;
pub const MAX_GENERATIONS: usize = 1;
pub const HEADER_DEADLINE: Duration = Duration::from_secs(5);
pub const CONNECTION_DEADLINE: Duration = Duration::from_secs(15);
pub const GENERATION_DEADLINE: Duration = Duration::from_secs(2);
pub const STREAM_SEND_DEADLINE: Duration = Duration::from_millis(500);

pub type BoxBody = http_body_util::combinators::BoxBody<Bytes, Infallible>;

#[derive(Clone)]
pub struct AppState {
    token: Arc<[u8]>,
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
    connections_spawned: AtomicUsize,
    connections_reaped: AtomicUsize,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct MetricsSnapshot {
    pub backend_started: usize,
    pub backend_active: usize,
    pub backend_finished: usize,
    /// Connection tasks handed to the accept loop's `JoinSet`.
    pub connections_spawned: usize,
    /// Connection tasks joined and removed from that set. F1 requires this to
    /// track `connections_spawned` during normal operation, not only at
    /// shutdown.
    pub connections_reaped: usize,
}

impl AppState {
    pub fn new(token: String) -> Result<Self, &'static str> {
        let token = token.into_bytes();
        if token.len() < 16 || token.len() > 256 || token.iter().any(u8::is_ascii_whitespace) {
            return Err("synthetic token must be 16..=256 non-whitespace bytes");
        }
        let (shutdown, _) = watch::channel(false);
        Ok(Self {
            token: token.into(),
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
                let (stream, peer) = accepted?;
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
    if !valid_host(request.headers().get(HOST), expected_port) {
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
                "data":[{"id":MODEL_ID,"object":"model","created":1789000000_u64,"owned_by":"pulsarmlx-synthetic","capabilities":["chat.completions","streaming","synthetic-only"]}]
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
        Err(response) => return response,
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
    if let Err((code, message)) = parsed.validate() {
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
    let mode = BackendMode::from_request(&parsed);
    if parsed.stream {
        stream_chat(state, permit, parsed, completion_id, mode)
    } else {
        nonstream_chat(state, permit, parsed, completion_id, mode).await
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

async fn read_body(mut body: Incoming) -> Result<Vec<u8>, Response<BoxBody>> {
    let mut bytes = Vec::new();
    while let Some(frame) = body.frame().await {
        let frame = frame.map_err(|_| {
            api_error(
                StatusCode::BAD_REQUEST,
                "invalid_body",
                "request body could not be read",
            )
        })?;
        if let Some(data) = frame.data_ref() {
            if bytes.len().saturating_add(data.len()) > MAX_BODY_BYTES {
                return Err(api_error(
                    StatusCode::PAYLOAD_TOO_LARGE,
                    "body_too_large",
                    "request body exceeds the limit",
                ));
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

impl ChatRequest {
    fn validate(&self) -> Result<(), (&'static str, &'static str)> {
        if self.model != MODEL_ID {
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
        let _ = self
            .messages
            .iter()
            .any(|m| matches!(m.role, Role::System | Role::User | Role::Assistant));
        Ok(())
    }
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum BackendMode {
    Success,
    Empty,
    DisconnectProbe,
    FailBefore,
    FailAfter,
    Slow,
}

impl BackendMode {
    fn from_request(request: &ChatRequest) -> Self {
        match request.messages.last().map(|m| m.content.as_str()) {
            Some("__synthetic_empty__") => Self::Empty,
            Some("__synthetic_disconnect__") => Self::DisconnectProbe,
            Some("__synthetic_fail_before__") => Self::FailBefore,
            Some("__synthetic_fail_after__") => Self::FailAfter,
            Some("__synthetic_slow__") => Self::Slow,
            _ => Self::Success,
        }
    }
}

/// How a streaming generation finished. `Completed` covers every path the
/// generation body already terminated itself, including its own `event: error`
/// and the abort taken when the consumer stopped reading.
#[derive(Clone, Copy, PartialEq, Eq)]
enum StreamOutcome {
    Completed,
    GenerationTimeout,
    ServerShutdown,
}

impl StreamOutcome {
    fn error_terminal(self) -> Option<(&'static str, &'static str)> {
        match self {
            Self::Completed => None,
            Self::GenerationTimeout => Some((
                "generation_timeout",
                "synthetic generation exceeded its deadline",
            )),
            Self::ServerShutdown => Some(("server_shutdown", "server is shutting down")),
        }
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
    permit: OwnedSemaphorePermit,
    request: ChatRequest,
    id: String,
    mode: BackendMode,
) -> Response<BoxBody> {
    let _guard = GenerationGuard::new(state, permit);
    if mode == BackendMode::FailBefore || mode == BackendMode::FailAfter {
        return api_error(
            StatusCode::INTERNAL_SERVER_ERROR,
            "backend_failure",
            "synthetic backend failed",
        );
    }
    let work = async {
        if mode == BackendMode::Slow {
            tokio::time::sleep(GENERATION_DEADLINE + Duration::from_millis(250)).await;
        }
        let (content, finish_reason, output_tokens) =
            render_output(mode, request.max_tokens.unwrap_or(MAX_OUTPUT_TOKENS));
        json_response(
            StatusCode::OK,
            json!({
                "id":id,"object":"chat.completion","created":1789000000_u64,"model":MODEL_ID,
                "choices":[{"index":0,"message":{"role":"assistant","content":content},"finish_reason":finish_reason}],
                "usage":{"prompt_tokens":request.messages.len(),"completion_tokens":output_tokens,"total_tokens":request.messages.len()+output_tokens}
            }),
        )
    };
    match tokio::time::timeout(GENERATION_DEADLINE, work).await {
        Ok(response) => response,
        Err(_) => api_error(
            StatusCode::GATEWAY_TIMEOUT,
            "generation_timeout",
            "synthetic generation exceeded its deadline",
        ),
    }
}

fn stream_chat(
    state: AppState,
    permit: OwnedSemaphorePermit,
    request: ChatRequest,
    id: String,
    mode: BackendMode,
) -> Response<BoxBody> {
    if mode == BackendMode::FailBefore {
        drop(GenerationGuard::new(state, permit));
        return api_error(
            StatusCode::INTERNAL_SERVER_ERROR,
            "backend_failure",
            "synthetic backend failed",
        );
    }
    let (sender, receiver) = mpsc::channel::<Result<Frame<Bytes>, Infallible>>(1);
    let mut shutdown = state.shutdown.subscribe();
    tokio::spawn(async move {
        let _guard = GenerationGuard::new(state, permit);
        let generation = async {
            if mode == BackendMode::Slow {
                tokio::time::sleep(GENERATION_DEADLINE + Duration::from_millis(250)).await;
            }
            let role = json!({"id":id,"object":"chat.completion.chunk","created":1789000000_u64,"model":MODEL_ID,"choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}]});
            if !send_sse(&sender, &role).await {
                return;
            }
            if mode == BackendMode::DisconnectProbe {
                tokio::time::sleep(Duration::from_millis(250)).await;
            }
            if mode == BackendMode::FailAfter {
                let error = json!({"error":{"code":"backend_failure","message":"synthetic backend failed","type":"server_error"}});
                let _ = send_event(&sender, "error", &error).await;
                return;
            }
            let (content, finish_reason, _) =
                render_output(mode, request.max_tokens.unwrap_or(MAX_OUTPUT_TOKENS));
            for chunk in utf8_chunks(&content) {
                let item = json!({"id":id,"object":"chat.completion.chunk","created":1789000000_u64,"model":MODEL_ID,"choices":[{"index":0,"delta":{"content":chunk},"finish_reason":null}]});
                if !send_sse(&sender, &item).await {
                    return;
                }
            }
            let terminal = json!({"id":id,"object":"chat.completion.chunk","created":1789000000_u64,"model":MODEL_ID,"choices":[{"index":0,"delta":{},"finish_reason":finish_reason}]});
            if !send_sse(&sender, &terminal).await {
                return;
            }
            let _ = send_raw(&sender, Bytes::from_static(b"data: [DONE]\n\n")).await;
        };
        // F2: an SSE body that has already sent headers must never be closed
        // silently. Classify how the generation ended and, when the stream can
        // still accept bytes, emit a bounded `event: error` terminal. A stream
        // that ended because the consumer stalled or vanished is left alone:
        // delivery is no longer possible there.
        let outcome = tokio::select! {
            result = tokio::time::timeout(GENERATION_DEADLINE, generation) => match result {
                Ok(()) => StreamOutcome::Completed,
                Err(_) => StreamOutcome::GenerationTimeout,
            },
            _ = shutdown.changed() => StreamOutcome::ServerShutdown,
        };
        if let Some((code, message)) = outcome.error_terminal() {
            let error = json!({"error":{"code":code,"message":message,"type":"server_error"}});
            let _ = send_event(&sender, "error", &error).await;
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

fn render_output(mode: BackendMode, max_tokens: u16) -> (String, &'static str, usize) {
    if mode == BackendMode::Empty {
        return (String::new(), "stop", 0);
    }
    let tokens = ["SYNTHETIC_OK:", " café", " 🚀"];
    let take = usize::from(max_tokens).min(tokens.len());
    let finish = if take < tokens.len() {
        "length"
    } else {
        "stop"
    };
    (tokens[..take].concat(), finish, take)
}

fn utf8_chunks(content: &str) -> Vec<&str> {
    if content.is_empty() {
        return Vec::new();
    }
    let mut cuts = vec![0];
    for (index, _) in content.char_indices().skip(1) {
        if cuts.len() < 3 {
            cuts.push(index);
        }
    }
    cuts.push(content.len());
    cuts.windows(2).map(|w| &content[w[0]..w[1]]).collect()
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

fn header_bytes(headers: &hyper::HeaderMap) -> usize {
    headers.iter().fold(0usize, |total, (name, value)| {
        total
            .saturating_add(name.as_str().len())
            .saturating_add(value.as_bytes().len())
    })
}

fn valid_host(value: Option<&hyper::header::HeaderValue>, expected_port: u16) -> bool {
    let Some(host) = value.and_then(|v| v.to_str().ok()) else {
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

fn api_error(status: StatusCode, code: &'static str, message: &'static str) -> Response<BoxBody> {
    json_response(
        status,
        json!({"error":{"code":code,"message":message,"type":"invalid_request_error"}}),
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
