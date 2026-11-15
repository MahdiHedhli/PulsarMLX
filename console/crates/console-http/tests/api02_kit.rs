//! Shared helpers of the API-02 transport tests: a test server, a raw socket client and a
//! test handler. Included by `api02_transport.rs` and `api02_donor.rs` with `#[path]`; as a
//! test target of its own it holds no test.
//!
//! The raw client follows the archived PulsarMLX serving crate's `raw_exchange` and
//! `parse_response` helpers (tag `archive/2026-09-21/feat/openai-serving`,
//! `crates/serve-synthetic/tests/raw_http.rs`), PulsarMLX's own code. Work package API-19
//! replaces it with the shared test kit.
#![allow(dead_code)]

use std::net::SocketAddr;
use std::sync::{Arc, Mutex};
use std::time::Duration;

use console_core::engine::ControlHandle;
use console_http::error::ApiError;
use console_http::transport::{
    bind, BodyError, Exchange, Handler, HandlerFuture, RequestHead, TransportConfig,
};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::TcpStream;
use tokio::sync::{mpsc, oneshot};
use tokio::task::JoinSet;

/// A generous bound for one exchange; tests that depend on timing say so themselves.
pub const DEADLINE: Duration = Duration::from_secs(10);

/// What the test handler reports about a request.
#[derive(Debug)]
pub enum Seen {
    /// The body as read, or the refusal.
    Body(Result<Vec<u8>, BodyError>),
    /// `TCP_NODELAY` before and after `sse_start`.
    NoDelay(bool, bool),
    /// A `/hold` or `/ping` request is waiting, its client watched.
    Holding,
    /// The client watch saw the client go (the request's control was cancelled).
    Cancelled,
    /// The head of the request.
    Head(RequestHead, SocketAddr),
}

/// A handler that serves the test routes:
///
/// - `POST /echo` (and any other POST path not listed): reads the body; a refusal is
///   answered with its error, a read that ends without data answers nothing, a body is
///   answered `200 {"received": <length>}`.
/// - `GET /head`: reports the head, answers `200` text.
/// - `GET /panic`: panics inside the future; `GET /panic-sync` panics in the call to
///   `handle`, before the future exists; any request to `/panic-hook` panics in
///   `end_headers`.
/// - `POST /sse`: reports `TCP_NODELAY` around `sse_start`, writes two frames.
/// - `POST /hold`: reads the body, watches the client and waits, writing nothing, until the
///   client goes or the test releases it, then answers `200`.
/// - `POST /hold-stream`: as `/hold`, after an SSE head.
/// - `POST /ping`: SSE head, then `: keep-alive` frames every 0.1 s until released (then a
///   data frame and `[DONE]`) or until the client goes.
pub struct TestHandler {
    pub seen: mpsc::UnboundedSender<Seen>,
    pub release: Arc<Mutex<Option<oneshot::Receiver<()>>>>,
    pub end_headers: Vec<(String, String)>,
}

impl TestHandler {
    fn take_release(&self) -> Option<oneshot::Receiver<()>> {
        self.release.lock().ok().and_then(|mut slot| slot.take())
    }
}

impl Handler for TestHandler {
    fn end_headers(&self, head: &RequestHead) -> Vec<(String, String)> {
        assert!(head.path() != "/panic-hook", "the end-headers hook panics");
        self.end_headers.clone()
    }

    fn handle(&self, mut exchange: Exchange) -> HandlerFuture<'_> {
        assert!(
            exchange.head().path() != "/panic-sync",
            "the handler panics before its future exists"
        );
        Box::pin(async move {
            let head = exchange.head().clone();
            let route = head.route_path().to_owned();
            match (head.method(), route.as_str()) {
                ("GET", "/head") => {
                    let _ = self
                        .seen
                        .send(Seen::Head(head.clone(), exchange.peer_addr()));
                    let _ = exchange.responder().text(200, "text/plain", b"ok").await;
                }
                ("GET", "/panic") => panic!("the test handler panics"),
                ("POST", "/sse") => {
                    let before = exchange.responder().nodelay().unwrap_or(true);
                    let after = match exchange.responder().sse_start().await {
                        Ok(mut sink) => {
                            let _ = sink.send(b"data: one\n\n").await;
                            let _ = sink.send(b"data: [DONE]\n\n").await;
                            exchange.responder().nodelay().unwrap_or(false)
                        }
                        Err(_) => false,
                    };
                    let _ = self.seen.send(Seen::NoDelay(before, after));
                }
                ("POST", "/hold") | ("POST", "/hold-stream") => {
                    let _ = exchange.read_body().await;
                    if route == "/hold-stream" && exchange.responder().sse_start().await.is_err() {
                        return;
                    }
                    let control = ControlHandle::new();
                    let probe = control.probe();
                    let Some(mut watch) = exchange.watch_client(control) else {
                        return;
                    };
                    let release = self.take_release();
                    let _ = self.seen.send(Seen::Holding);
                    tokio::select! {
                        () = watch.gone() => {
                            assert!(probe.is_cancelled(), "the watch cancels the control");
                            let _ = self.seen.send(Seen::Cancelled);
                        }
                        _ = async move {
                            match release {
                                Some(rx) => { let _ = rx.await; }
                                None => std::future::pending::<()>().await,
                            }
                        } => {
                            if route == "/hold" {
                                let _ = exchange.responder().json(200, "{\"held\": true}").await;
                            } else {
                                let _ = exchange.responder().write_body(b"data: hello\n\n").await;
                            }
                        }
                    }
                }
                ("POST", "/ping") => {
                    let _ = exchange.read_body().await;
                    if exchange.responder().sse_start().await.is_err() {
                        return;
                    }
                    let control = ControlHandle::new();
                    let Some(mut watch) = exchange.watch_client(control) else {
                        return;
                    };
                    let mut release = self.take_release();
                    let _ = self.seen.send(Seen::Holding);
                    loop {
                        tokio::select! {
                            () = watch.gone() => {
                                let _ = self.seen.send(Seen::Cancelled);
                                return;
                            }
                            () = tokio::time::sleep(Duration::from_millis(100)) => {
                                let done = match release.as_mut() {
                                    Some(rx) => rx.try_recv().is_ok(),
                                    None => false,
                                };
                                let frame: &[u8] = if done {
                                    b"data: hello\n\ndata: [DONE]\n\n"
                                } else {
                                    b": keep-alive\n\n"
                                };
                                if exchange.responder().write_body(frame).await.is_err() || done {
                                    return;
                                }
                            }
                        }
                    }
                }
                ("POST", _) => {
                    let body = exchange.read_body().await;
                    match &body {
                        Ok(bytes) => {
                            let text = format!("{{\"received\": {}}}", bytes.len());
                            let _ = exchange.responder().json(200, &text).await;
                        }
                        Err(BodyError::Refused(e)) => {
                            let _ = exchange.responder().error(e).await;
                        }
                        Err(_) => {}
                    }
                    let _ = self.seen.send(Seen::Body(body));
                }
                _ => {
                    let _ = exchange.responder().error(&ApiError::NotFound).await;
                }
            }
        })
    }
}

/// A running test server.
pub struct TestServer {
    pub addr: SocketAddr,
    pub backlog: u32,
    pub seen: mpsc::UnboundedReceiver<Seen>,
    pub release: Arc<Mutex<Option<oneshot::Receiver<()>>>>,
    stop: Option<oneshot::Sender<()>>,
    task: tokio::task::JoinHandle<JoinSet<()>>,
}

impl TestServer {
    /// A server with the donor's defaults.
    pub async fn start() -> Self {
        Self::with(TransportConfig::default(), Vec::new()).await
    }

    /// A server with these settings and end-headers headers.
    pub async fn with(config: TransportConfig, end_headers: Vec<(String, String)>) -> Self {
        let listener = match bind(SocketAddr::from(([127, 0, 0, 1], 0)), config) {
            Ok(listener) => listener,
            Err(e) => panic!("bind: {e}"),
        };
        let addr = listener
            .local_addr()
            .unwrap_or_else(|e| panic!("addr: {e}"));
        let backlog = listener.backlog();
        let (tx, rx) = mpsc::unbounded_channel();
        let release = Arc::new(Mutex::new(None));
        let handler = Arc::new(TestHandler {
            seen: tx,
            release: Arc::clone(&release),
            end_headers,
        });
        let (stop, stopped) = oneshot::channel::<()>();
        let task = tokio::spawn(listener.serve(handler, async move {
            let _ = stopped.await;
        }));
        Self {
            addr,
            backlog,
            seen: rx,
            release,
            stop: Some(stop),
            task,
        }
    }

    /// Arms the release of the next `/hold` or `/ping` request.
    pub fn arm_release(&self) -> oneshot::Sender<()> {
        let (tx, rx) = oneshot::channel();
        if let Ok(mut slot) = self.release.lock() {
            *slot = Some(rx);
        }
        tx
    }

    /// The next report of the handler.
    pub async fn next_seen(&mut self) -> Seen {
        match tokio::time::timeout(DEADLINE, self.seen.recv()).await {
            Ok(Some(seen)) => seen,
            Ok(None) => panic!("the handler is gone"),
            Err(_) => panic!("no report from the handler"),
        }
    }

    /// Stops accepting and returns the connections still in flight.
    pub async fn stop(mut self) -> JoinSet<()> {
        if let Some(stop) = self.stop.take() {
            let _ = stop.send(());
        }
        match self.task.await {
            Ok(set) => set,
            Err(e) => panic!("serve task: {e}"),
        }
    }
}

/// A raw response.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RawResponse {
    pub raw: Vec<u8>,
    pub status: u16,
    /// Header lines after the status line, `Date` value replaced by `<date>`.
    pub head: String,
    pub body: Vec<u8>,
}

impl RawResponse {
    pub fn text(&self) -> String {
        String::from_utf8_lossy(&self.body).into_owned()
    }
}

/// Connects, writes `request`, reads to end of file within [`DEADLINE`].
pub async fn exchange(addr: SocketAddr, request: &[u8]) -> RawResponse {
    let mut stream = connect(addr).await;
    write(&mut stream, request).await;
    parse_response(&read_to_eof(&mut stream).await)
}

/// As [`exchange`], with the client's write side shut after the request.
pub async fn exchange_with_eof(addr: SocketAddr, request: &[u8]) -> RawResponse {
    let mut stream = connect(addr).await;
    write(&mut stream, request).await;
    let _ = stream.shutdown().await;
    parse_response(&read_to_eof(&mut stream).await)
}

pub async fn connect(addr: SocketAddr) -> TcpStream {
    match TcpStream::connect(addr).await {
        Ok(stream) => stream,
        Err(e) => panic!("connect: {e}"),
    }
}

pub async fn write(stream: &mut TcpStream, bytes: &[u8]) {
    if let Err(e) = stream.write_all(bytes).await {
        panic!("write: {e}");
    }
}

pub async fn read_to_eof(stream: &mut TcpStream) -> Vec<u8> {
    let mut raw = Vec::new();
    match tokio::time::timeout(DEADLINE, stream.read_to_end(&mut raw)).await {
        Ok(Ok(_)) => raw,
        // A reset after the answer still leaves what arrived.
        Ok(Err(_)) => raw,
        Err(_) => panic!(
            "no end of file within the deadline; got {:?}",
            String::from_utf8_lossy(&raw)
        ),
    }
}

/// Splits a raw response: status code, the header lines with the `Date` value masked, and
/// the body. An empty response has status 0.
pub fn parse_response(raw: &[u8]) -> RawResponse {
    let split = raw.windows(4).position(|w| w == b"\r\n\r\n");
    let Some(split) = split else {
        return RawResponse {
            raw: raw.to_vec(),
            status: 0,
            head: String::new(),
            body: raw.to_vec(),
        };
    };
    let head_bytes = raw.get(..split).unwrap_or_default();
    let head: String = head_bytes.iter().map(|&b| char::from(b)).collect();
    let status = head
        .split(' ')
        .nth(1)
        .and_then(|s| s.parse().ok())
        .unwrap_or(0);
    let masked: Vec<String> = head
        .split("\r\n")
        .map(|line| {
            if line.starts_with("Date: ") {
                String::from("Date: <date>")
            } else {
                line.to_owned()
            }
        })
        .collect();
    RawResponse {
        raw: raw.to_vec(),
        status,
        head: masked.join("\r\n"),
        body: raw.get(split + 4..).unwrap_or_default().to_vec(),
    }
}

/// The donor's raw POST to `/v1/chat/completions` with extra header lines.
pub fn donor_post(headers: &str, body: &[u8]) -> Vec<u8> {
    let mut bytes = format!(
        "POST /v1/chat/completions HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\n{headers}\r\n"
    )
    .into_bytes();
    bytes.extend_from_slice(body);
    bytes
}

/// The `Server` line every answer carries (approved deviation P-1).
pub fn server_line() -> String {
    format!("Server: pulsar-console/{}", env!("CARGO_PKG_VERSION"))
}

/// The JSON error body of the donor's `BadBody`.
pub fn invalid_request(message: &str) -> String {
    format!("{{\"error\": {{\"type\": \"invalid_request_error\", \"message\": \"{message}\"}}}}")
}
