//! Shared helpers of the API-03 router tests: a server around a [`Router`], a raw socket
//! client, and a probe handler that stands in for the route handlers of later packages.
//! Included by the `api03_*.rs` test files with `#[path]`; as a test target of its own it
//! holds no test.
//!
//! The raw client follows the archived PulsarMLX serving crate's `raw_exchange` and
//! `parse_response` helpers (tag `archive/2026-09-21/feat/openai-serving`,
//! `crates/serve-synthetic/tests/raw_http.rs`), PulsarMLX's own code. Work package API-19
//! replaces it with the shared test kit.
#![allow(dead_code)]

use std::net::{IpAddr, Ipv4Addr, SocketAddr};
use std::sync::Arc;
use std::time::Duration;

use console_http::guard::GuardConfig;
use console_http::router::{Route, RouteHandler, RouteRequest, Router};
use console_http::transport::{bind, HandlerFuture, TransportConfig};
use console_pyjson::dumps::dumps_str;
use serde_json::Value;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::TcpStream;
use tokio::sync::oneshot;
use tokio::task::JoinSet;

/// A generous bound for one exchange.
pub const DEADLINE: Duration = Duration::from_secs(10);

/// The loopback address.
pub const LOOPBACK: IpAddr = IpAddr::V4(Ipv4Addr::LOCALHOST);

/// Every slot a later package fills, so that a test can register the probe on all of them.
pub const ALL_ROUTES: [Route; 46] = [
    Route::ModelsSse,
    Route::OllamaGet,
    Route::ResponseResource,
    Route::Fonts,
    Route::WebRedirect,
    Route::WebAsset,
    Route::Metrics,
    Route::MetricsPrometheus,
    Route::SettingsGet,
    Route::Mcp,
    Route::Index,
    Route::Health,
    Route::ContextGet,
    Route::ThinkingBudgetGet,
    Route::PortGet,
    Route::TurboGet,
    Route::ModelsInfo,
    Route::Savings,
    Route::UpdateGet,
    Route::Report,
    Route::Status,
    Route::Models,
    Route::Props,
    Route::Slots,
    Route::V1Status,
    Route::StrataStream,
    Route::LlamacppModels,
    Route::ResponseCancel,
    Route::OllamaPost,
    Route::SettingsPost,
    Route::Attach,
    Route::StrataCancel,
    Route::ContextPost,
    Route::PortPost,
    Route::ThinkingBudgetPost,
    Route::UpdatePost,
    Route::TurboPost,
    Route::ModelsAdmin,
    Route::SavingsReset,
    Route::SavingsPrices,
    Route::Tokens,
    Route::Tokenize,
    Route::Detokenize,
    Route::ChatCompletions,
    Route::Responses,
    Route::Messages,
];

/// A stand-in for a later package's handler: answers `200 {"route": "<slot>", "path":
/// <path>, "body": <the parsed body or null>}`. On the slots whose donor handler asks for
/// the key itself (`/models/sse`, `/v1/responses/*`), it asks first, as those handlers do.
pub struct Probe;

impl RouteHandler for Probe {
    fn serve(&self, mut request: RouteRequest) -> HandlerFuture<'_> {
        Box::pin(async move {
            if matches!(request.route, Route::ModelsSse | Route::ResponseResource) {
                if let Err(refusal) = request.guard.check_key(request.exchange.head()) {
                    let _ = refusal.answer(request.exchange.responder()).await;
                    return;
                }
            }
            let body = match &request.body {
                Some(map) => Value::Object(map.clone()).to_string(),
                None => String::from("null"),
            };
            let text = format!(
                "{{\"route\": \"{:?}\", \"path\": {}, \"body\": {body}}}",
                request.route,
                dumps_str(&request.path, false)
            );
            let _ = request.exchange.responder().json(200, &text).await;
        })
    }
}

/// A router with the probe on every slot.
pub fn probed(config: GuardConfig) -> Router {
    let probe: Arc<dyn RouteHandler> = Arc::new(Probe);
    let mut router = Router::new(config);
    for route in ALL_ROUTES {
        router.register(route, Arc::clone(&probe));
    }
    router
}

/// A running server.
pub struct Server {
    pub addr: SocketAddr,
    pub router: Arc<Router>,
    stop: Option<oneshot::Sender<()>>,
    task: tokio::task::JoinHandle<JoinSet<()>>,
}

impl Server {
    /// Serves `router` on a loopback port chosen by the system.
    pub async fn start(router: Router) -> Self {
        let listener = match bind(SocketAddr::new(LOOPBACK, 0), TransportConfig::default()) {
            Ok(listener) => listener,
            Err(e) => panic!("bind: {e}"),
        };
        let addr = listener
            .local_addr()
            .unwrap_or_else(|e| panic!("addr: {e}"));
        let router = Arc::new(router);
        let handler: Arc<dyn console_http::transport::Handler> = router.clone();
        let (stop, stopped) = oneshot::channel::<()>();
        let task = tokio::spawn(listener.serve(handler, async move {
            let _ = stopped.await;
        }));
        Self {
            addr,
            router,
            stop: Some(stop),
            task,
        }
    }

    /// `host:port` of the server, as a client puts it in `Host`.
    pub fn host(&self) -> String {
        format!("127.0.0.1:{}", self.addr.port())
    }

    /// Sends one request: `method path`, a `Host` of [`Server::host`] unless `headers`
    /// has one, the headers, and the body with its `Content-Length`.
    pub async fn call(
        &self,
        method: &str,
        path: &str,
        headers: &[(&str, &str)],
        body: Option<&[u8]>,
    ) -> RawResponse {
        let mut text = format!("{method} {path} HTTP/1.1\r\n");
        if !headers.iter().any(|(k, _)| k.eq_ignore_ascii_case("host")) {
            text.push_str(&format!("Host: {}\r\n", self.host()));
        }
        for (k, v) in headers {
            text.push_str(&format!("{k}: {v}\r\n"));
        }
        if let Some(body) = body {
            text.push_str(&format!("Content-Length: {}\r\n", body.len()));
        }
        text.push_str("\r\n");
        let mut bytes = text.into_bytes();
        if let Some(body) = body {
            bytes.extend_from_slice(body);
        }
        exchange(self.addr, &bytes).await
    }

    /// A JSON POST (`Content-Type: application/json`) of `body`.
    pub async fn post_json(&self, path: &str, headers: &[(&str, &str)], body: &str) -> RawResponse {
        let mut all = vec![("Content-Type", "application/json")];
        all.extend_from_slice(headers);
        self.call("POST", path, &all, Some(body.as_bytes())).await
    }

    /// Stops accepting.
    pub async fn stop(mut self) {
        if let Some(stop) = self.stop.take() {
            let _ = stop.send(());
        }
        let _ = self.task.await;
    }
}

/// A raw response.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RawResponse {
    pub raw: Vec<u8>,
    pub status: u16,
    /// The header lines after the status line.
    pub headers: Vec<(String, String)>,
    pub body: Vec<u8>,
}

impl RawResponse {
    /// The first header named `name` (any case).
    pub fn header(&self, name: &str) -> Option<&str> {
        self.headers
            .iter()
            .find(|(k, _)| k.eq_ignore_ascii_case(name))
            .map(|(_, v)| v.as_str())
    }

    /// The body as text.
    pub fn text(&self) -> String {
        String::from_utf8_lossy(&self.body).into_owned()
    }

    /// The body as JSON (`null` when it is not JSON).
    pub fn json(&self) -> Value {
        serde_json::from_slice(&self.body).unwrap_or(Value::Null)
    }

    /// The probe's slot name, when the probe answered.
    pub fn routed(&self) -> Option<String> {
        self.json()
            .get("route")
            .and_then(Value::as_str)
            .map(str::to_owned)
    }
}

/// Connects, writes `request`, reads to end of file within [`DEADLINE`].
pub async fn exchange(addr: SocketAddr, request: &[u8]) -> RawResponse {
    let mut stream = match TcpStream::connect(addr).await {
        Ok(stream) => stream,
        Err(e) => panic!("connect: {e}"),
    };
    if let Err(e) = stream.write_all(request).await {
        panic!("write: {e}");
    }
    let mut raw = Vec::new();
    match tokio::time::timeout(DEADLINE, stream.read_to_end(&mut raw)).await {
        // A reset after the answer still leaves what arrived.
        Ok(_) => parse_response(&raw),
        Err(_) => panic!(
            "no end of file within the deadline; got {:?}",
            String::from_utf8_lossy(&raw)
        ),
    }
}

/// Splits a raw response into its status, headers and body. An empty response has status 0.
pub fn parse_response(raw: &[u8]) -> RawResponse {
    let split = raw.windows(4).position(|w| w == b"\r\n\r\n");
    let (head, body) = match split {
        Some(at) => (&raw[..at], raw[at + 4..].to_vec()),
        None => (raw, Vec::new()),
    };
    let head = String::from_utf8_lossy(head);
    let mut lines = head.split("\r\n");
    let status = lines
        .next()
        .and_then(|l| l.split(' ').nth(1))
        .and_then(|s| s.parse().ok())
        .unwrap_or(0);
    let headers = lines
        .filter_map(|l| l.split_once(": "))
        .map(|(k, v)| (k.to_owned(), v.to_owned()))
        .collect();
    RawResponse {
        raw: raw.to_vec(),
        status,
        headers,
        body,
    }
}
