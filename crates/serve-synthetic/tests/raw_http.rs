use pulsar_serve_synthetic::{bind_loopback, serve, AppState, MAX_BODY_BYTES};
use serde_json::Value;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::TcpStream;
use tokio::sync::oneshot;

static TOKEN_ID: AtomicU64 = AtomicU64::new(1);

struct TestServer {
    address: std::net::SocketAddr,
    token: String,
    state: AppState,
    shutdown: Option<oneshot::Sender<()>>,
    task: tokio::task::JoinHandle<std::io::Result<()>>,
}

impl TestServer {
    async fn start() -> Self {
        let token = format!(
            "synthetic-test-{}-{}",
            std::process::id(),
            TOKEN_ID.fetch_add(1, Ordering::SeqCst)
        );
        let state = AppState::new(token.clone()).expect("test token");
        let listener = bind_loopback(0).await.expect("bind");
        let address = listener.local_addr().expect("address");
        let (shutdown, receiver) = oneshot::channel();
        let app = state.clone();
        let task = tokio::spawn(serve(listener, app, async {
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

    async fn stop(mut self) {
        let _ = self.shutdown.take().expect("shutdown sender").send(());
        self.task.await.expect("join").expect("serve result");
    }

    async fn request(
        &self,
        method: &str,
        path: &str,
        body: Option<&str>,
        auth: bool,
    ) -> RawResponse {
        let mut headers = format!(
            "{method} {path} HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nConnection: close\r\n",
            self.address.port()
        );
        if auth {
            headers.push_str(&format!("Authorization: Bearer {}\r\n", self.token));
        }
        if let Some(body) = body {
            headers.push_str(&format!(
                "Content-Type: application/json\r\nContent-Length: {}\r\n",
                body.len()
            ));
        }
        headers.push_str("\r\n");
        if let Some(body) = body {
            headers.push_str(body);
        }
        raw_exchange(self.address, headers.as_bytes()).await
    }
}

struct RawResponse {
    status: u16,
    headers: String,
    body: Vec<u8>,
}

impl RawResponse {
    fn json(&self) -> Value {
        serde_json::from_slice(&self.body).expect("JSON response")
    }
    fn text(&self) -> String {
        String::from_utf8(self.body.clone()).expect("UTF-8 response")
    }
}

async fn raw_exchange(address: std::net::SocketAddr, request: &[u8]) -> RawResponse {
    let mut stream = TcpStream::connect(address).await.expect("connect");
    stream.write_all(request).await.expect("write request");
    let mut raw = Vec::new();
    tokio::time::timeout(Duration::from_secs(5), stream.read_to_end(&mut raw))
        .await
        .expect("read deadline")
        .expect("read response");
    parse_response(&raw)
}

async fn raw_exchange_with_eof(address: std::net::SocketAddr, request: &[u8]) -> RawResponse {
    let mut stream = TcpStream::connect(address).await.expect("connect");
    stream.write_all(request).await.expect("write request");
    stream.shutdown().await.expect("half close request");
    let mut raw = Vec::new();
    tokio::time::timeout(Duration::from_secs(5), stream.read_to_end(&mut raw))
        .await
        .expect("read deadline")
        .expect("read response");
    parse_response(&raw)
}

async fn custom_request(server: &TestServer, headers_and_body: String) -> RawResponse {
    raw_exchange(server.address, headers_and_body.as_bytes()).await
}

fn parse_response(raw: &[u8]) -> RawResponse {
    let split = raw
        .windows(4)
        .position(|w| w == b"\r\n\r\n")
        .expect("header terminator");
    let headers = String::from_utf8(raw[..split].to_vec()).expect("header UTF-8");
    let status = headers
        .lines()
        .next()
        .expect("status line")
        .split_whitespace()
        .nth(1)
        .expect("status")
        .parse()
        .expect("numeric status");
    let payload = &raw[split + 4..];
    let body = if headers
        .to_ascii_lowercase()
        .contains("transfer-encoding: chunked")
    {
        decode_chunked(payload)
    } else {
        payload.to_vec()
    };
    RawResponse {
        status,
        headers,
        body,
    }
}

fn decode_chunked(mut input: &[u8]) -> Vec<u8> {
    let mut output = Vec::new();
    loop {
        let end = input
            .windows(2)
            .position(|w| w == b"\r\n")
            .expect("chunk size");
        let size =
            usize::from_str_radix(std::str::from_utf8(&input[..end]).expect("size UTF-8"), 16)
                .expect("hex size");
        input = &input[end + 2..];
        if size == 0 {
            break;
        }
        output.extend_from_slice(&input[..size]);
        input = &input[size + 2..];
    }
    output
}

fn chat_body(content: &str, stream: bool) -> String {
    serde_json::json!({"model":"pulsarmlx-synthetic-v1","messages":[{"role":"user","content":content}],"stream":stream}).to_string()
}

#[tokio::test]
async fn health_and_models_enforce_the_boundary() {
    let server = TestServer::start().await;
    let health = server.request("GET", "/health", None, false).await;
    assert_eq!(health.status, 200);
    assert_eq!(
        health.json(),
        serde_json::json!({"status":"ok","synthetic":true})
    );
    let missing = server.request("GET", "/v1/models", None, false).await;
    assert_eq!(missing.status, 401);
    assert_eq!(missing.json()["error"]["code"], "invalid_api_key");
    let models = server.request("GET", "/v1/models", None, true).await;
    assert_eq!(models.status, 200);
    assert_eq!(models.json()["data"][0]["id"], "pulsarmlx-synthetic-v1");
    assert_eq!(
        models.json()["data"][0]["capabilities"],
        serde_json::json!(["chat.completions", "streaming", "synthetic-only"])
    );
    assert!(models
        .headers
        .to_ascii_lowercase()
        .contains("cache-control: no-store"));
    server.stop().await;
}

#[tokio::test]
async fn nonstream_and_stream_reassemble_to_predeclared_utf8() {
    let server = TestServer::start().await;
    let body = chat_body("hello", false);
    let json_response = server
        .request("POST", "/v1/chat/completions", Some(&body), true)
        .await;
    assert_eq!(json_response.status, 200);
    let json = json_response.json();
    assert_eq!(
        json["choices"][0]["message"]["content"],
        "SYNTHETIC_OK: café 🚀"
    );
    assert_eq!(json["usage"]["completion_tokens"], 3);

    let body = chat_body("hello", true);
    let stream = server
        .request("POST", "/v1/chat/completions", Some(&body), true)
        .await;
    assert_eq!(stream.status, 200);
    let text = stream.text();
    assert!(text.ends_with("data: [DONE]\n\n"));
    let mut content = String::new();
    let mut ids = Vec::new();
    let mut created = Vec::new();
    let mut finish = None;
    for line in text
        .lines()
        .filter_map(|line| line.strip_prefix("data: "))
        .filter(|line| *line != "[DONE]")
    {
        let chunk: Value = serde_json::from_str(line).expect("chunk JSON");
        ids.push(chunk["id"].clone());
        created.push(chunk["created"].clone());
        if let Some(value) = chunk["choices"][0]["delta"]["content"].as_str() {
            content.push_str(value);
        }
        if !chunk["choices"][0]["finish_reason"].is_null() {
            finish = chunk["choices"][0]["finish_reason"]
                .as_str()
                .map(str::to_owned);
        }
    }
    assert_eq!(content, "SYNTHETIC_OK: café 🚀");
    assert_eq!(finish.as_deref(), Some("stop"));
    assert!(ids.windows(2).all(|pair| pair[0] == pair[1]));
    assert!(created.windows(2).all(|pair| pair[0] == pair[1]));
    server.stop().await;
}

#[tokio::test]
async fn invalid_and_oversized_requests_never_start_backend() {
    let server = TestServer::start().await;
    let invalid_model =
        serde_json::json!({"model":"real-model","messages":[{"role":"user","content":"x"}]})
            .to_string();
    assert_eq!(
        server
            .request("POST", "/v1/chat/completions", Some(&invalid_model), true)
            .await
            .status,
        400
    );
    let unsupported = serde_json::json!({"model":"pulsarmlx-synthetic-v1","messages":[{"role":"user","content":"x"}],"tools":[]}).to_string();
    assert_eq!(
        server
            .request("POST", "/v1/chat/completions", Some(&unsupported), true)
            .await
            .json()["error"]["code"],
        "unsupported_parameter"
    );
    let too_large = "x".repeat(MAX_BODY_BYTES + 1);
    assert_eq!(
        server
            .request("POST", "/v1/chat/completions", Some(&too_large), true)
            .await
            .status,
        413
    );
    let too_many_messages = serde_json::json!({
        "model":"pulsarmlx-synthetic-v1",
        "messages":(0..17).map(|_| serde_json::json!({"role":"user","content":"x"})).collect::<Vec<_>>()
    })
    .to_string();
    assert_eq!(
        server
            .request(
                "POST",
                "/v1/chat/completions",
                Some(&too_many_messages),
                true
            )
            .await
            .json()["error"]["code"],
        "invalid_messages"
    );
    let oversized_message = chat_body(&"x".repeat(2 * 1024 + 1), false);
    assert_eq!(
        server
            .request(
                "POST",
                "/v1/chat/completions",
                Some(&oversized_message),
                true
            )
            .await
            .json()["error"]["code"],
        "message_too_large"
    );
    assert_eq!(server.state.metrics().backend_started, 0);
    server.stop().await;
}

#[tokio::test]
async fn backend_modes_and_capacity_release_ownership() {
    let server = TestServer::start().await;
    let empty = chat_body("__synthetic_empty__", false);
    let empty_response = server
        .request("POST", "/v1/chat/completions", Some(&empty), true)
        .await
        .json();
    assert_eq!(empty_response["choices"][0]["message"]["content"], "");
    assert_eq!(empty_response["usage"]["completion_tokens"], 0);

    let failure = chat_body("__synthetic_fail_before__", false);
    assert_eq!(
        server
            .request("POST", "/v1/chat/completions", Some(&failure), true)
            .await
            .status,
        500
    );

    let slow = chat_body("__synthetic_slow__", false);
    let address = server.address;
    let token = server.token.clone();
    let slow_task = tokio::spawn(async move {
        let mut request = format!("POST /v1/chat/completions HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nAuthorization: Bearer {}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n", address.port(), token, slow.len());
        request.push_str(&slow);
        raw_exchange(address, request.as_bytes()).await
    });
    tokio::time::timeout(Duration::from_secs(1), async {
        while server.state.metrics().backend_active == 0 {
            tokio::task::yield_now().await;
        }
    })
    .await
    .expect("backend started");
    let busy = chat_body("hello", false);
    assert_eq!(
        server
            .request("POST", "/v1/chat/completions", Some(&busy), true)
            .await
            .status,
        429
    );
    assert_eq!(slow_task.await.expect("slow join").status, 504);
    assert_eq!(server.state.metrics().backend_active, 0);
    assert_eq!(
        server.state.metrics().backend_started,
        server.state.metrics().backend_finished
    );
    server.stop().await;
}

#[tokio::test]
async fn stream_failure_has_no_success_terminal() {
    let server = TestServer::start().await;
    let body = chat_body("__synthetic_fail_after__", true);
    let response = server
        .request("POST", "/v1/chat/completions", Some(&body), true)
        .await;
    assert_eq!(response.status, 200);
    let text = response.text();
    assert!(text.contains("event: error"));
    assert!(!text.contains("data: [DONE]"));
    assert!(!text.contains("finish_reason\":\"stop"));
    assert_eq!(server.state.metrics().backend_active, 0);

    let before = chat_body("__synthetic_fail_before__", true);
    let response = server
        .request("POST", "/v1/chat/completions", Some(&before), true)
        .await;
    assert_eq!(response.status, 500);
    assert_eq!(response.json()["error"]["code"], "backend_failure");

    let slow = chat_body("__synthetic_slow__", true);
    let response = server
        .request("POST", "/v1/chat/completions", Some(&slow), true)
        .await;
    assert_eq!(response.status, 200);
    let text = response.text();
    assert!(!text.contains("data: [DONE]"));
    assert!(!text.contains("finish_reason\":\"stop"));
    assert_eq!(server.state.metrics().backend_active, 0);
    server.stop().await;
}

#[tokio::test]
async fn host_origin_auth_and_header_limits_are_enforced() {
    let server = TestServer::start().await;
    let wrong_host = custom_request(
        &server,
        "GET /health HTTP/1.1\r\nHost: attacker.invalid\r\nConnection: close\r\n\r\n".into(),
    )
    .await;
    assert_eq!(wrong_host.status, 403);
    assert_eq!(wrong_host.json()["error"]["code"], "invalid_host");

    let cross_origin = custom_request(
        &server,
        format!(
            "GET /v1/models HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nOrigin: https://attacker.invalid\r\nAuthorization: Bearer {}\r\nConnection: close\r\n\r\n",
            server.address.port(),
            server.token
        ),
    )
    .await;
    assert_eq!(cross_origin.status, 403);
    assert_eq!(cross_origin.json()["error"]["code"], "invalid_origin");

    let wrong_auth = custom_request(
        &server,
        format!(
            "GET /v1/models HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nAuthorization: Bearer definitely-wrong-token\r\nConnection: close\r\n\r\n",
            server.address.port()
        ),
    )
    .await;
    assert_eq!(wrong_auth.status, 401);

    let long_header = "a".repeat(8 * 1024);
    let oversized_headers = custom_request(
        &server,
        format!(
            "GET /health HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nX-Padding: {long_header}\r\nConnection: close\r\n\r\n",
            server.address.port()
        ),
    )
    .await;
    assert_eq!(oversized_headers.status, 431);
    assert_eq!(server.state.metrics().backend_started, 0);
    server.stop().await;
}

#[tokio::test]
async fn parser_rejects_conflicting_framing_and_routes_are_explicit() {
    let server = TestServer::start().await;
    let conflicting = custom_request(
        &server,
        format!(
            "POST /v1/chat/completions HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nAuthorization: Bearer {}\r\nContent-Type: application/json\r\nContent-Length: 1\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{{}}",
            server.address.port(),
            server.token
        ),
    )
    .await;
    assert_eq!(conflicting.status, 400);

    let truncated = format!(
        "POST /v1/chat/completions HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nAuthorization: Bearer {}\r\nContent-Type: application/json\r\nContent-Length: 20\r\nConnection: close\r\n\r\n{{}}",
        server.address.port(),
        server.token
    );
    let truncated = raw_exchange_with_eof(server.address, truncated.as_bytes()).await;
    assert_eq!(truncated.status, 400);
    assert_eq!(truncated.json()["error"]["code"], "invalid_body");

    let unknown = server.request("GET", "/v1/unknown", None, true).await;
    assert_eq!(unknown.status, 404);
    assert_eq!(unknown.json()["error"]["code"], "not_found");
    let wrong_method = server.request("POST", "/v1/models", None, true).await;
    assert_eq!(wrong_method.status, 405);
    assert_eq!(wrong_method.json()["error"]["code"], "method_not_allowed");
    assert_eq!(server.state.metrics().backend_started, 0);
    server.stop().await;
}

#[tokio::test]
async fn output_limit_and_unsupported_sampling_are_explicit() {
    let server = TestServer::start().await;
    let limited = serde_json::json!({
        "model":"pulsarmlx-synthetic-v1",
        "messages":[{"role":"user","content":"hello"}],
        "max_tokens":1
    })
    .to_string();
    let response = server
        .request("POST", "/v1/chat/completions", Some(&limited), true)
        .await
        .json();
    assert_eq!(
        response["choices"][0]["message"]["content"],
        "SYNTHETIC_OK:"
    );
    assert_eq!(response["choices"][0]["finish_reason"], "length");
    assert_eq!(response["usage"]["completion_tokens"], 1);

    let sampling = serde_json::json!({
        "model":"pulsarmlx-synthetic-v1",
        "messages":[{"role":"user","content":"hello"}],
        "temperature":0.5
    })
    .to_string();
    let rejected = server
        .request("POST", "/v1/chat/completions", Some(&sampling), true)
        .await;
    assert_eq!(rejected.status, 400);
    assert_eq!(rejected.json()["error"]["code"], "unsupported_parameter");
    assert_eq!(server.state.metrics().backend_started, 1);
    server.stop().await;
}

#[tokio::test]
async fn disconnect_releases_stream_ownership() {
    let server = TestServer::start().await;
    let body = chat_body("__synthetic_disconnect__", true);
    let mut stream = TcpStream::connect(server.address).await.expect("connect");
    let request = format!(
        "POST /v1/chat/completions HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nAuthorization: Bearer {}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
        server.address.port(),
        server.token,
        body.len(),
        body
    );
    stream.write_all(request.as_bytes()).await.expect("write");
    let mut headers = Vec::new();
    tokio::time::timeout(Duration::from_secs(1), async {
        let mut byte = [0_u8; 1];
        while !headers.ends_with(b"\r\n\r\n") {
            stream
                .read_exact(&mut byte)
                .await
                .expect("read header byte");
            headers.push(byte[0]);
        }
    })
    .await
    .expect("response headers");
    let mut first_body = [0_u8; 128];
    let body_bytes = tokio::time::timeout(Duration::from_secs(1), stream.read(&mut first_body))
        .await
        .expect("first stream chunk deadline")
        .expect("first stream chunk");
    assert!(body_bytes > 0);
    assert_eq!(server.state.metrics().backend_active, 1);
    drop(stream);
    tokio::time::timeout(Duration::from_secs(1), async {
        while server.state.metrics().backend_active != 0 {
            tokio::task::yield_now().await;
        }
    })
    .await
    .expect("ownership released");
    assert_eq!(
        server.state.metrics().backend_started,
        server.state.metrics().backend_finished
    );
    server.stop().await;
}

#[tokio::test]
async fn shutdown_cancels_active_stream_and_releases_ownership() {
    let server = TestServer::start().await;
    let state = server.state.clone();
    let body = chat_body("__synthetic_disconnect__", true);
    let mut stream = TcpStream::connect(server.address).await.expect("connect");
    let request = format!(
        "POST /v1/chat/completions HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nAuthorization: Bearer {}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
        server.address.port(),
        server.token,
        body.len(),
        body
    );
    stream.write_all(request.as_bytes()).await.expect("write");
    tokio::time::timeout(Duration::from_secs(1), async {
        while state.metrics().backend_active == 0 {
            tokio::task::yield_now().await;
        }
    })
    .await
    .expect("backend active");
    server.stop().await;
    tokio::time::timeout(Duration::from_secs(1), async {
        while state.metrics().backend_active != 0 {
            tokio::task::yield_now().await;
        }
    })
    .await
    .expect("shutdown released ownership");
    assert_eq!(
        state.metrics().backend_started,
        state.metrics().backend_finished
    );
    drop(stream);
}

/// F1: completed connection tasks must be reaped while the accept loop is
/// still running. Before the fix `connections_reaped` stayed at zero until
/// shutdown, so every accepted connection retained a JoinHandle for the whole
/// process lifetime.
#[tokio::test]
async fn repeated_connections_are_reaped_during_normal_operation() {
    let server = TestServer::start().await;
    const ROUNDS: usize = 40;
    for _ in 0..ROUNDS {
        assert_eq!(
            server.request("GET", "/health", None, false).await.status,
            200
        );
    }
    // Reaping is observed by the accept loop, so allow it to run without
    // requiring a fixed scheduling order.
    tokio::time::timeout(Duration::from_secs(5), async {
        while server.state.metrics().connections_reaped < ROUNDS {
            tokio::task::yield_now().await;
        }
    })
    .await
    .expect("connection tasks reaped before shutdown");

    let live = server.state.metrics();
    assert_eq!(live.connections_spawned, ROUNDS);
    assert_eq!(live.connections_reaped, ROUNDS);

    // Reaping must not break shutdown or leave the accounting inconsistent.
    server.stop().await;
}

/// F1: shutdown still drains connections that are in flight when it fires, and
/// the spawned/reaped accounting balances afterwards.
#[tokio::test]
async fn shutdown_still_drains_in_flight_connections() {
    let server = TestServer::start().await;
    let state = server.state.clone();
    let body = chat_body("__synthetic_disconnect__", true);
    let mut stream = TcpStream::connect(server.address).await.expect("connect");
    let request = format!(
        "POST /v1/chat/completions HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nAuthorization: Bearer {}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
        server.address.port(),
        server.token,
        body.len(),
        body
    );
    stream.write_all(request.as_bytes()).await.expect("write");
    tokio::time::timeout(Duration::from_secs(1), async {
        while state.metrics().backend_active == 0 {
            tokio::task::yield_now().await;
        }
    })
    .await
    .expect("backend active");

    server.stop().await;

    let after = state.metrics();
    assert_eq!(after.connections_spawned, after.connections_reaped);
    assert!(after.connections_spawned >= 1);
    drop(stream);
}

/// F2: a generation that exceeds its deadline after headers are sent must be
/// reported, not silently truncated. Before the fix the body simply ended with
/// no terminal event at all.
#[tokio::test]
async fn stream_generation_timeout_emits_bounded_error_event() {
    let server = TestServer::start().await;
    let body = chat_body("__synthetic_slow__", true);
    let response = server
        .request("POST", "/v1/chat/completions", Some(&body), true)
        .await;
    assert_eq!(response.status, 200);
    let text = response.text();

    assert!(
        text.contains("event: error"),
        "timeout must carry an error event, got: {text:?}"
    );
    assert!(
        text.contains("generation_timeout"),
        "error event must name the timeout, got: {text:?}"
    );
    // An unsuccessful stream must never look successful.
    assert!(!text.contains("data: [DONE]"), "got: {text:?}");
    assert!(!text.contains("finish_reason\":\"stop"), "got: {text:?}");

    // Cancellation released the generation permit and the accounting balances.
    let metrics = server.state.metrics();
    assert_eq!(metrics.backend_active, 0);
    assert_eq!(metrics.backend_started, metrics.backend_finished);

    // The single generation slot is genuinely reusable afterwards.
    let follow_up = server
        .request(
            "POST",
            "/v1/chat/completions",
            Some(&chat_body("hello", false)),
            true,
        )
        .await;
    assert_eq!(follow_up.status, 200);
    assert_eq!(follow_up.json()["choices"][0]["finish_reason"], "stop");
    server.stop().await;
}

/// Send a chunked request body, tolerating the server closing the connection
/// as soon as it rejects the payload.
async fn chunked_exchange(
    address: std::net::SocketAddr,
    head: &str,
    chunks: &[Vec<u8>],
) -> RawResponse {
    let mut stream = TcpStream::connect(address).await.expect("connect");
    if stream.write_all(head.as_bytes()).await.is_ok() {
        'outer: for chunk in chunks {
            for part in [
                format!("{:x}\r\n", chunk.len()).into_bytes(),
                chunk.clone(),
                b"\r\n".to_vec(),
            ] {
                // A rejected body closes the connection early; that is the
                // behaviour under test, not a harness failure.
                if stream.write_all(&part).await.is_err() {
                    break 'outer;
                }
            }
        }
        let _ = stream.write_all(b"0\r\n\r\n").await;
    }
    let mut raw = Vec::new();
    tokio::time::timeout(Duration::from_secs(5), stream.read_to_end(&mut raw))
        .await
        .expect("read deadline")
        .expect("read response");
    parse_response(&raw)
}

/// F3: the accumulated-frame cap in `read_body` is a separate defence from the
/// declared `Content-Length` cap. This request declares no length at all, so
/// only the frame accumulation check can reject it.
#[tokio::test]
async fn chunked_body_exceeding_accumulated_limit_is_rejected() {
    let server = TestServer::start().await;
    let head = format!(
        "POST /v1/chat/completions HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nAuthorization: Bearer {}\r\nContent-Type: application/json\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\n",
        server.address.port(),
        server.token
    );
    // Four 8 KiB frames, each individually under the cap, together over it.
    let chunks: Vec<Vec<u8>> = (0..4).map(|_| vec![b'x'; 8 * 1024]).collect();
    let total: usize = chunks.iter().map(Vec::len).sum();
    assert!(total > MAX_BODY_BYTES);
    assert!(chunks.iter().all(|c| c.len() <= MAX_BODY_BYTES));

    let response = chunked_exchange(server.address, &head, &chunks).await;
    assert_eq!(response.status, 413, "body: {:?}", response.text());
    assert_eq!(response.json()["error"]["code"], "body_too_large");
    assert_eq!(server.state.metrics().backend_started, 0);

    // A chunked body under the cap still succeeds, so the guard is not simply
    // rejecting all chunked framing.
    let ok_body = chat_body("hello", false).into_bytes();
    let ok = chunked_exchange(server.address, &head, &[ok_body]).await;
    assert_eq!(ok.status, 200, "body: {:?}", ok.text());
    assert_eq!(ok.json()["choices"][0]["finish_reason"], "stop");
    server.stop().await;
}

/// F3: malformed JSON and an unsupported media type are distinct rejections
/// and neither reaches the synthetic backend.
#[tokio::test]
async fn malformed_json_and_unsupported_content_type_are_rejected() {
    let server = TestServer::start().await;

    for invalid in [
        "{\"model\":",
        "not json at all",
        "{\"model\":\"pulsarmlx-synthetic-v1\",}",
        "",
    ] {
        let response = server
            .request("POST", "/v1/chat/completions", Some(invalid), true)
            .await;
        assert_eq!(response.status, 400, "input {invalid:?}");
        assert_eq!(
            response.json()["error"]["code"],
            "invalid_json",
            "input {invalid:?}"
        );
    }

    // Well-formed JSON carrying the wrong media type is refused before parsing.
    let body = chat_body("hello", false);
    for content_type in ["text/plain", "application/x-www-form-urlencoded", "*/*"] {
        let response = custom_request(
            &server,
            format!(
                "POST /v1/chat/completions HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nAuthorization: Bearer {}\r\nContent-Type: {}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
                server.address.port(),
                server.token,
                content_type,
                body.len(),
                body
            ),
        )
        .await;
        assert_eq!(response.status, 415, "content-type {content_type}");
        assert_eq!(
            response.json()["error"]["code"],
            "invalid_content_type",
            "content-type {content_type}"
        );
    }

    // A charset parameter on the supported type is still accepted.
    let ok = custom_request(
        &server,
        format!(
            "POST /v1/chat/completions HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nAuthorization: Bearer {}\r\nContent-Type: application/json; charset=utf-8\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
            server.address.port(),
            server.token,
            body.len(),
            body
        ),
    )
    .await;
    assert_eq!(ok.status, 200);
    assert_eq!(server.state.metrics().backend_started, 1);
    server.stop().await;
}

/// F3: a malformed declared length is rejected before any application code
/// runs. hyper's parser refuses these during header parsing and answers with a
/// bare 400 carrying no JSON body, so the crate's own `invalid_content_length`
/// branch is currently unreachable; it is retained as defence in depth. This
/// test records the behaviour that is actually observable.
#[tokio::test]
async fn invalid_declared_length_is_rejected_by_the_parser() {
    let server = TestServer::start().await;
    for value in ["abc", "99999999999999999999999999", "-1", "+5", "1 2"] {
        let response = custom_request(
            &server,
            format!(
                "POST /v1/chat/completions HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nAuthorization: Bearer {}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
                server.address.port(),
                server.token,
                value
            ),
        )
        .await;
        assert_eq!(response.status, 400, "Content-Length: {value}");
        assert!(
            response.body.is_empty(),
            "parser rejection carries no application body, got {:?}",
            response.text()
        );
    }

    // A declared length over the cap is the crate's own rejection and does
    // carry the application error shape.
    let oversized = custom_request(
        &server,
        format!(
            "POST /v1/chat/completions HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nAuthorization: Bearer {}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
            server.address.port(),
            server.token,
            MAX_BODY_BYTES + 1
        ),
    )
    .await;
    assert_eq!(oversized.status, 413);
    assert_eq!(oversized.json()["error"]["code"], "body_too_large");
    assert_eq!(server.state.metrics().backend_started, 0);
    server.stop().await;
}

/// F3: token limits outside the supported range are refused before a
/// generation permit is taken.
#[tokio::test]
async fn token_limits_outside_supported_range_are_rejected() {
    let server = TestServer::start().await;
    for max_tokens in ["0", "17", "65535"] {
        let body = format!(
            "{{\"model\":\"pulsarmlx-synthetic-v1\",\"messages\":[{{\"role\":\"user\",\"content\":\"hello\"}}],\"max_tokens\":{max_tokens}}}"
        );
        let response = server
            .request("POST", "/v1/chat/completions", Some(&body), true)
            .await;
        assert_eq!(response.status, 400, "max_tokens={max_tokens}");
        assert_eq!(
            response.json()["error"]["code"],
            "invalid_max_tokens",
            "max_tokens={max_tokens}"
        );
    }

    // Out-of-type values are refused as malformed input rather than accepted.
    for max_tokens in ["-1", "65536", "1.5"] {
        let body = format!(
            "{{\"model\":\"pulsarmlx-synthetic-v1\",\"messages\":[{{\"role\":\"user\",\"content\":\"hello\"}}],\"max_tokens\":{max_tokens}}}"
        );
        let response = server
            .request("POST", "/v1/chat/completions", Some(&body), true)
            .await;
        assert_eq!(response.status, 400, "max_tokens={max_tokens}");
        assert_eq!(
            response.json()["error"]["code"],
            "invalid_json",
            "max_tokens={max_tokens}"
        );
    }

    // The upper bound itself remains accepted.
    let body = format!(
        "{{\"model\":\"pulsarmlx-synthetic-v1\",\"messages\":[{{\"role\":\"user\",\"content\":\"hello\"}}],\"max_tokens\":{}}}",
        16
    );
    let ok = server
        .request("POST", "/v1/chat/completions", Some(&body), true)
        .await;
    assert_eq!(ok.status, 200);
    assert_eq!(server.state.metrics().backend_started, 1);
    server.stop().await;
}
