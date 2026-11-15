//! Stand-in handlers for the transport and router tests, and the server around them.
//!
//! - [`TransportProbe`] is a raw transport [`Handler`] with test routes (echo a body, hold
//!   a request until released or until the client goes, stream keep-alives, panic on
//!   purpose) that reports what it saw; [`ProbeServer`] serves it and receives the
//!   reports. The API-02 tests use it.
//! - [`RouteProbe`] is a [`RouteHandler`] that answers with the slot it was called for, the
//!   matched path and the parsed body; [`probed`] registers it on every slot of a router.
//!   The API-03 tests use it, and any later test that needs the guards without a real
//!   handler.
//!
//! These handlers panic on purpose on their `/panic*` routes: the transport's panic
//! handling is under test there. They serve tests only and are never part of the server.

use std::net::SocketAddr;
use std::sync::{Arc, Mutex};
use std::time::Duration;

use console_core::engine::ControlHandle;
use console_http::error::ApiError;
use console_http::guard::GuardConfig;
use console_http::router::{Route, RouteHandler, RouteRequest, Router};
use console_http::transport::{
    BodyError, Exchange, Handler, HandlerFuture, RequestHead, TransportConfig,
};
use console_pyjson::dumps::dumps_str;
use serde_json::Value;
use tokio::sync::{mpsc, oneshot};
use tokio::task::JoinSet;

use super::TestServer;
use crate::raw::DEADLINE;

/// What the [`TransportProbe`] reports about a request.
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
    /// The head of the request and the client's address.
    Head(RequestHead, SocketAddr),
}

/// A transport handler that serves the test routes:
///
/// - `POST /echo` (and any other POST path not listed): reads the body; a refusal is
///   answered with its error, a read that ends without data answers nothing, a body is
///   answered `200 {"received": <length>}`.
/// - `GET /head`: reports the head, answers `200` text `ok`.
/// - `GET /panic`: panics inside the future; `GET /panic-sync` panics in the call to
///   `handle`, before the future exists; any request to `/panic-hook` panics in
///   `end_headers`.
/// - `POST /sse`: reports `TCP_NODELAY` around `sse_start`, writes two frames.
/// - `POST /hold`: reads the body, watches the client and waits, writing nothing, until the
///   client goes or the test releases it, then answers `200 {"held": true}`.
/// - `POST /hold-stream`: as `/hold`, after an SSE head; released, it writes one frame.
/// - `POST /ping`: SSE head, then `: keep-alive` frames every 0.1 s until released (then a
///   data frame and `[DONE]`) or until the client goes.
/// - anything else: 404.
pub struct TransportProbe {
    seen: mpsc::UnboundedSender<Seen>,
    release: Arc<Mutex<Option<oneshot::Receiver<()>>>>,
    end_headers: Vec<(String, String)>,
}

impl TransportProbe {
    fn take_release(&self) -> Option<oneshot::Receiver<()>> {
        self.release.lock().ok().and_then(|mut slot| slot.take())
    }
}

impl Handler for TransportProbe {
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
                    self.hold(exchange, route == "/hold").await;
                }
                ("POST", "/ping") => self.ping(exchange).await,
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

impl TransportProbe {
    async fn hold(&self, mut exchange: Exchange, plain: bool) {
        let _ = exchange.read_body().await;
        if !plain && exchange.responder().sse_start().await.is_err() {
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
                if plain {
                    let _ = exchange.responder().json(200, "{\"held\": true}").await;
                } else {
                    let _ = exchange.responder().write_body(b"data: hello\n\n").await;
                }
            }
        }
    }

    async fn ping(&self, mut exchange: Exchange) {
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
                    if exchange.responder().write_body(frame).await.is_err() {
                        // The write found the client gone before the watch's next check
                        // (it checks every 0.5 s, the keep-alives come every 0.1 s); the
                        // watch still sees the end at that check, and that is reported.
                        if tokio::time::timeout(DEADLINE, watch.gone()).await.is_ok() {
                            let _ = self.seen.send(Seen::Cancelled);
                        }
                        return;
                    }
                    if done {
                        return;
                    }
                }
            }
        }
    }
}

/// A [`TestServer`] around a [`TransportProbe`], with the probe's reports.
pub struct ProbeServer {
    /// The bound address.
    pub addr: SocketAddr,
    /// The listen backlog in force.
    pub backlog: u32,
    /// The probe's reports, in order.
    pub seen: mpsc::UnboundedReceiver<Seen>,
    release: Arc<Mutex<Option<oneshot::Receiver<()>>>>,
    server: TestServer,
}

impl std::fmt::Debug for ProbeServer {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("ProbeServer")
            .field("addr", &self.addr)
            .field("backlog", &self.backlog)
            .finish_non_exhaustive()
    }
}

impl ProbeServer {
    /// A probe server with the donor's transport defaults.
    pub async fn start() -> Self {
        Self::with(TransportConfig::default(), Vec::new()).await
    }

    /// A probe server with these transport settings and end-headers headers. Panics when
    /// the listener cannot be bound.
    pub async fn with(config: TransportConfig, end_headers: Vec<(String, String)>) -> Self {
        let (tx, rx) = mpsc::unbounded_channel();
        let release = Arc::new(Mutex::new(None));
        let handler = Arc::new(TransportProbe {
            seen: tx,
            release: Arc::clone(&release),
            end_headers,
        });
        let server = TestServer::with_handler(handler, config).await;
        Self {
            addr: server.addr,
            backlog: server.backlog,
            seen: rx,
            release,
            server,
        }
    }

    /// Arms the release of the next `/hold`, `/hold-stream` or `/ping` request.
    pub fn arm_release(&self) -> oneshot::Sender<()> {
        let (tx, rx) = oneshot::channel();
        if let Ok(mut slot) = self.release.lock() {
            *slot = Some(rx);
        }
        tx
    }

    /// The next report of the probe, within [`DEADLINE`]; panics when none comes.
    pub async fn next_seen(&mut self) -> Seen {
        match tokio::time::timeout(DEADLINE, self.seen.recv()).await {
            Ok(Some(seen)) => seen,
            Ok(None) => panic!("the probe is gone"),
            Err(_) => panic!("no report from the probe"),
        }
    }

    /// The server underneath.
    pub fn server(&self) -> &TestServer {
        &self.server
    }

    /// Stops accepting and returns the connections still in flight.
    pub async fn stop(self) -> JoinSet<()> {
        self.server.stop().await
    }
}

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

/// A stand-in for a later package's route handler: answers `200 {"route": "<slot>",
/// "path": <path>, "body": <the parsed body or null>}`. On the slots whose donor handler
/// asks for the key itself (`/models/sse`, `/v1/responses/*`), it asks first, as those
/// handlers do.
#[derive(Debug, Clone, Copy, Default)]
pub struct RouteProbe;

impl RouteHandler for RouteProbe {
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

/// A router with the guards of `config` and the [`RouteProbe`] on every slot.
pub fn probed(config: GuardConfig) -> Router {
    let probe: Arc<dyn RouteHandler> = Arc::new(RouteProbe);
    let mut router = Router::new(config);
    for route in ALL_ROUTES {
        router.register(route, Arc::clone(&probe));
    }
    router
}
