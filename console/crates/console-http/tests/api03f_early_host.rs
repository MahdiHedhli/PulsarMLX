//! API-03F: the `Host` allowlist (deviation SEC-1.1) before the transport's own answers.
//!
//! The transport asks [`Handler::early_refusal`] as soon as it has a parsed request head,
//! before its 501 page for a method it does not serve and its 400 for conflicting framing
//! (approved deviation P-2). The router answers a refused `Host` there with the same 403
//! `permission_error` it answers on a route. A handler that does not implement the hook
//! behaves as before, and the hook runs once per request (never for a 431 page, which has
//! no usable headers).
//!
//! These tests are this server's own (SEC-1.1 has no donor counterpart); no donor test
//! method is re-expressed here. The raw socket client is local to this file.

use std::net::{IpAddr, Ipv4Addr, SocketAddr};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;
use std::time::Duration;

use console_http::error::ApiError;
use console_http::guard::{GuardConfig, HOST_REFUSED_MESSAGE};
use console_http::router::Router;
use console_http::transport::{
    bind, Exchange, Handler, HandlerFuture, RequestHead, TransportConfig, CONFLICTING_FRAMING,
    MAX_HEADERS,
};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::TcpStream;
use tokio::sync::oneshot;
use tokio::task::JoinSet;

const DEADLINE: Duration = Duration::from_secs(10);
const LOOPBACK: IpAddr = IpAddr::V4(Ipv4Addr::LOCALHOST);
const REFUSED: &str = "rebind.example:8095";

// ---------------------------------------------------------------------------------------
// A raw socket client and a server around any handler.

struct Answer {
    status: u16,
    headers: Vec<(String, String)>,
    body: String,
    raw: String,
}

impl Answer {
    fn header(&self, name: &str) -> Option<&str> {
        self.headers
            .iter()
            .find(|(k, _)| k.eq_ignore_ascii_case(name))
            .map(|(_, v)| v.as_str())
    }

    /// The whole answer with the `Date` line removed, to compare two answers.
    fn without_date(&self) -> String {
        self.raw
            .split("\r\n")
            .filter(|line| !line.starts_with("Date: "))
            .collect::<Vec<_>>()
            .join("\r\n")
    }
}

async fn exchange(addr: SocketAddr, request: &[u8]) -> Answer {
    let run = async {
        let mut stream = TcpStream::connect(addr).await.expect("connect");
        stream.write_all(request).await.expect("write");
        let mut out = Vec::new();
        // A reset after the answer is complete still leaves the answer read.
        let _ = stream.read_to_end(&mut out).await;
        out
    };
    let out = tokio::time::timeout(DEADLINE, run)
        .await
        .expect("the exchange timed out");
    let raw = String::from_utf8_lossy(&out).into_owned();
    let (head, body) = raw.split_once("\r\n\r\n").unwrap_or((raw.as_str(), ""));
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
    Answer {
        status,
        headers,
        body: body.to_owned(),
        raw: raw.clone(),
    }
}

struct Server {
    addr: SocketAddr,
    stop: Option<oneshot::Sender<()>>,
    task: tokio::task::JoinHandle<JoinSet<()>>,
}

impl Server {
    async fn start(handler: Arc<dyn Handler>) -> Self {
        let listener = bind(SocketAddr::new(LOOPBACK, 0), TransportConfig::default())
            .expect("bind a loopback port");
        let addr = listener.local_addr().expect("local address");
        let (stop, stopped) = oneshot::channel::<()>();
        let task = tokio::spawn(listener.serve(handler, async move {
            let _ = stopped.await;
        }));
        Self {
            addr,
            stop: Some(stop),
            task,
        }
    }

    fn own_host(&self) -> String {
        format!("127.0.0.1:{}", self.addr.port())
    }

    /// `method /v1/models` with `Host: host` and the extra header lines.
    async fn send(&self, method: &str, host: &str, extra: &str) -> Answer {
        let request = format!("{method} /v1/models HTTP/1.1\r\nHost: {host}\r\n{extra}\r\n");
        exchange(self.addr, request.as_bytes()).await
    }

    /// A POST that carries both framings (P-2).
    async fn conflicting(&self, host: &str) -> Answer {
        let request = format!(
            "POST /v1/chat/completions HTTP/1.1\r\nHost: {host}\r\n\
             Content-Type: application/json\r\nContent-Length: 2\r\n\
             Transfer-Encoding: chunked\r\n\r\n{{}}"
        );
        exchange(self.addr, request.as_bytes()).await
    }

    /// A GET with more than [`MAX_HEADERS`] header lines (431).
    async fn too_many_headers(&self, host: &str) -> Answer {
        let mut request = format!("GET /v1/models HTTP/1.1\r\nHost: {host}\r\n");
        for i in 0..=MAX_HEADERS {
            request.push_str(&format!("X-Pad-{i}: 1\r\n"));
        }
        request.push_str("\r\n");
        exchange(self.addr, request.as_bytes()).await
    }

    async fn stop(mut self) {
        if let Some(stop) = self.stop.take() {
            let _ = stop.send(());
        }
        let _ = self.task.await;
    }
}

fn host_refused_body() -> String {
    format!(
        "{{\"error\": {{\"type\": \"permission_error\", \"message\": \"{HOST_REFUSED_MESSAGE}\"}}}}"
    )
}

fn loopback_router() -> Arc<Router> {
    Arc::new(Router::new(GuardConfig::new(LOOPBACK)))
}

// ---------------------------------------------------------------------------------------
// Handlers of these tests.

/// A handler that keeps the trait's default hook and answers 200 itself.
#[derive(Default)]
struct Plain {
    handled: AtomicUsize,
}

impl Handler for Plain {
    fn handle(&self, mut exchange: Exchange) -> HandlerFuture<'_> {
        self.handled.fetch_add(1, Ordering::SeqCst);
        Box::pin(async move {
            let _ = exchange.responder().json(200, "{\"ok\": true}").await;
        })
    }
}

/// A handler that counts its hook calls and refuses the `Host` it is told to.
struct Counting {
    refuse_host: &'static str,
    early: AtomicUsize,
    handled: AtomicUsize,
}

impl Counting {
    fn new(refuse_host: &'static str) -> Self {
        Self {
            refuse_host,
            early: AtomicUsize::new(0),
            handled: AtomicUsize::new(0),
        }
    }

    fn counts(&self) -> (usize, usize) {
        (
            self.early.load(Ordering::SeqCst),
            self.handled.load(Ordering::SeqCst),
        )
    }
}

impl Handler for Counting {
    fn handle(&self, mut exchange: Exchange) -> HandlerFuture<'_> {
        self.handled.fetch_add(1, Ordering::SeqCst);
        Box::pin(async move {
            let _ = exchange.responder().json(200, "{\"ok\": true}").await;
        })
    }

    fn end_headers(&self, _head: &RequestHead) -> Vec<(String, String)> {
        vec![(String::from("X-End-Headers"), String::from("1"))]
    }

    fn early_refusal(&self, head: &RequestHead) -> Option<ApiError> {
        self.early.fetch_add(1, Ordering::SeqCst);
        (head.headers().get("Host") == Some(self.refuse_host))
            .then(|| ApiError::permission("refused early"))
    }
}

/// A handler whose hook panics.
struct Panicking;

impl Handler for Panicking {
    fn handle(&self, mut exchange: Exchange) -> HandlerFuture<'_> {
        Box::pin(async move {
            let _ = exchange.responder().json(200, "{\"ok\": true}").await;
        })
    }

    fn early_refusal(&self, head: &RequestHead) -> Option<ApiError> {
        if head.path().contains("boom") {
            panic!("the early refusal failed");
        }
        None
    }
}

// ---------------------------------------------------------------------------------------
// The router.

// Deviation SEC-1.1: a refused `Host` with a method the transport does not serve gets the
// router's 403, not the transport's 501.
#[tokio::test]
async fn a_refused_host_with_an_unserved_method_gets_403() {
    let server = Server::start(loopback_router()).await;
    for method in ["PUT", "PATCH", "TRACE", "BREW"] {
        let answer = server.send(method, REFUSED, "").await;
        assert_eq!(answer.status, 403, "{method}: {}", answer.raw);
        assert_eq!(answer.body, host_refused_body(), "{method}");
        assert_eq!(answer.header("Content-Type"), Some("application/json"));
    }
    server.stop().await;
}

// A refused `Host` with HEAD gets the same 403 head (status, Content-Type and the
// Content-Length of the JSON body) and no body: a response to HEAD carries no content
// (RFC 9110 section 9.3.2), as the transport's own pages leave it out for HEAD.
#[tokio::test]
async fn a_refused_host_with_head_gets_403_without_a_body() {
    let server = Server::start(loopback_router()).await;
    let answer = server.send("HEAD", REFUSED, "").await;
    assert_eq!(answer.status, 403, "{}", answer.raw);
    assert_eq!(answer.header("Content-Type"), Some("application/json"));
    let length = host_refused_body().len().to_string();
    assert_eq!(answer.header("Content-Length"), Some(length.as_str()));
    assert_eq!(answer.body, "", "{}", answer.raw);
    // Compared with the GET on a route, only the body is missing.
    let on_route = server.send("GET", REFUSED, "").await;
    let route_head = on_route
        .without_date()
        .split_once("\r\n\r\n")
        .map(|(h, _)| h.to_owned());
    let head_head = answer
        .without_date()
        .split_once("\r\n\r\n")
        .map(|(h, _)| h.to_owned());
    assert_eq!(head_head, route_head);
    // An allowed `Host` with HEAD still gets the transport's 501 page with no body.
    let allowed = server.send("HEAD", &server.own_host(), "").await;
    assert_eq!(allowed.status, 501, "{}", allowed.raw);
    assert_eq!(allowed.body, "", "{}", allowed.raw);
    server.stop().await;
}

// Deviation SEC-1.1 before approved deviation P-2: a refused `Host` with conflicting
// framing gets 403, not the P-2 400.
#[tokio::test]
async fn a_refused_host_with_conflicting_framing_gets_403() {
    let server = Server::start(loopback_router()).await;
    let answer = server.conflicting(REFUSED).await;
    assert_eq!(answer.status, 403, "{}", answer.raw);
    assert_eq!(answer.body, host_refused_body());
    server.stop().await;
}

// An allowed `Host` still gets the transport's 501 page and the P-2 400.
#[tokio::test]
async fn an_allowed_host_still_gets_501_and_the_p2_400() {
    let server = Server::start(loopback_router()).await;
    for host in [
        server.own_host(),
        String::from("localhost"),
        String::from("[::1]:1"),
    ] {
        let answer = server.send("PUT", &host, "").await;
        assert_eq!(answer.status, 501, "{host}: {}", answer.raw);
        assert!(
            answer.body.contains("Unsupported method ('PUT')"),
            "{host}: {}",
            answer.body
        );
        let answer = server.conflicting(&host).await;
        assert_eq!(answer.status, 400, "{host}: {}", answer.raw);
        assert!(answer.body.contains(CONFLICTING_FRAMING), "{}", answer.body);
    }
    server.stop().await;
}

// The early 403 is byte for byte the 403 the router answers on a route today (apart from
// `Date`), with no CORS header even when `cors_origins` grants every origin.
#[tokio::test]
async fn the_early_403_is_the_route_403_and_carries_no_cors_header() {
    let config = GuardConfig::new(LOOPBACK).with_cors_origins(vec![String::from("*")]);
    let server = Server::start(Arc::new(Router::new(config))).await;
    let on_route = server.send("GET", REFUSED, "").await;
    let early = server.send("PUT", REFUSED, "").await;
    let framing = server.conflicting(REFUSED).await;
    assert_eq!(on_route.status, 403, "{}", on_route.raw);
    assert_eq!(early.without_date(), on_route.without_date());
    assert_eq!(framing.body, on_route.body);
    for answer in [&on_route, &early, &framing] {
        assert_eq!(answer.header("Access-Control-Allow-Origin"), None);
        assert_eq!(answer.header("Vary"), None);
    }
    // An allowed `Host` on a `/v1/` path keeps its CORS header on the 501 page.
    let allowed = server.send("PUT", &server.own_host(), "").await;
    assert_eq!(allowed.status, 501);
    assert_eq!(allowed.header("Access-Control-Allow-Origin"), Some("*"));
    server.stop().await;
}

// The 431 pages have no usable headers: a refused `Host` there still gets the 431 page.
#[tokio::test]
async fn the_431_page_is_answered_without_the_host_check() {
    let server = Server::start(loopback_router()).await;
    let answer = server.too_many_headers(REFUSED).await;
    assert_eq!(answer.status, 431, "{}", answer.raw);
    server.stop().await;
}

// On a bind that is not loopback and with no `allowed_hosts`, every `Host` is served, so
// the transport's pages are unchanged.
#[tokio::test]
async fn an_unrestricted_bind_keeps_the_transport_pages() {
    let any = IpAddr::V4(Ipv4Addr::UNSPECIFIED);
    let server = Server::start(Arc::new(Router::new(GuardConfig::new(any)))).await;
    assert_eq!(server.send("PUT", REFUSED, "").await.status, 501);
    assert_eq!(server.conflicting(REFUSED).await.status, 400);
    server.stop().await;
}

// ---------------------------------------------------------------------------------------
// The hook in the transport.

// A handler that keeps the default hook behaves as before: 501, the P-2 400, 431, and its
// own answer for a served method, whatever the `Host`.
#[tokio::test]
async fn a_handler_without_the_hook_behaves_as_before() {
    let plain = Arc::new(Plain::default());
    let server = Server::start(plain.clone()).await;
    assert_eq!(server.send("PUT", REFUSED, "").await.status, 501);
    assert_eq!(server.conflicting(REFUSED).await.status, 400);
    assert_eq!(server.too_many_headers(REFUSED).await.status, 431);
    let served = server.send("GET", REFUSED, "").await;
    assert_eq!(served.status, 200, "{}", served.raw);
    assert_eq!(served.body, "{\"ok\": true}");
    assert_eq!(plain.handled.load(Ordering::SeqCst), 1);
    server.stop().await;
}

// The hook runs once per request with a parsed head, before the 501 and P-2 answers, and
// never for a 431 page.
#[tokio::test]
async fn the_hook_runs_once_per_request() {
    let counting = Arc::new(Counting::new(REFUSED));
    let server = Server::start(counting.clone()).await;
    let host = server.own_host();

    assert_eq!(server.send("GET", &host, "").await.status, 200);
    assert_eq!(counting.counts(), (1, 1));
    assert_eq!(server.send("PUT", &host, "").await.status, 501);
    assert_eq!(counting.counts(), (2, 1));
    assert_eq!(server.conflicting(&host).await.status, 400);
    assert_eq!(counting.counts(), (3, 1));
    assert_eq!(server.too_many_headers(&host).await.status, 431);
    assert_eq!(counting.counts(), (3, 1));
    server.stop().await;
}

// A refusal from the hook is the answer, with the handler's end headers, and the handler
// is not called.
#[tokio::test]
async fn a_refusal_from_the_hook_is_the_answer() {
    let counting = Arc::new(Counting::new(REFUSED));
    let server = Server::start(counting.clone()).await;
    for method in ["GET", "POST", "PUT"] {
        let answer = server.send(method, REFUSED, "").await;
        assert_eq!(answer.status, 403, "{method}: {}", answer.raw);
        assert_eq!(
            answer.body,
            "{\"error\": {\"type\": \"permission_error\", \"message\": \"refused early\"}}"
        );
        assert_eq!(answer.header("X-End-Headers"), Some("1"));
    }
    assert_eq!(server.conflicting(REFUSED).await.status, 403);
    assert_eq!(counting.counts(), (4, 0));
    server.stop().await;
}

// A panic in the hook closes only its connection; the server goes on.
#[tokio::test]
async fn a_panic_in_the_hook_closes_only_its_connection() {
    let server = Server::start(Arc::new(Panicking)).await;
    let request = format!("GET /boom HTTP/1.1\r\nHost: {}\r\n\r\n", server.own_host());
    let answer = exchange(server.addr, request.as_bytes()).await;
    assert_eq!(answer.raw, "");
    assert_eq!(server.send("GET", &server.own_host(), "").await.status, 200);
    server.stop().await;
}
