//! Follow-up to work package API-02: the client watcher polls as the donor's `watch_client`
//! does (project-maya serve/server.py:5019-5044 at 7e68a30f). The first check comes one
//! watch interval (0.5 s) after the watch starts, and one check follows every interval.
//!
//! All tests run on real loopback sockets and the real clock, because the interval itself
//! is under test. They wait on reported events with a deadline instead of sleeping; the one
//! fixed wait is the 1.1 s window of the unread-data test, the shortest that spans two
//! checks. Every test closes its sockets, releases the requests it held and stops its
//! server, joining the connections still in flight.
//!
//! Timing bounds, with their margins: a half-closed request is cancelled no earlier than
//! 0.5 s after its watch started (a check never runs before the first interval has passed,
//! so this lower bound has no margin to give) and before 1.25 s (the check at 0.5 s sees
//! the end; 1.25 s leaves 0.75 s for a loaded machine, and still fails a watcher that
//! skipped two checks). A client that closes while its request waits is noticed within
//! 1 s of the close, the bound of API-02's "Done when".

#[path = "api08_kit.rs"]
mod kit;

use std::sync::Arc;
use std::time::{Duration, Instant};

use console_core::engine::ControlHandle;
use console_engine::fake::DEFAULT_MAX_CONTEXT;
use console_http::transport::{Exchange, Handler, HandlerFuture, TransportConfig, WATCH_INTERVAL};
use console_testkit::engines::{script, shared};
use console_testkit::raw::{
    connect, parse_response, read_to_eof, read_to_eof_allowing_reset, write, RawRequest,
};
use console_testkit::server::TestServer;
use tokio::io::AsyncWriteExt;
use tokio::net::TcpStream;
use tokio::sync::{mpsc, watch};

use kit::{builder, chat, normalized, Finished, DEADLINE};

// ------------------------------------------------------------------ the watch handler

/// What the [`Watching`] handler reports, with the request's path.
#[derive(Debug)]
enum Seen {
    /// The body was read and the watch started.
    Holding(String),
    /// The watch saw the client go: how long after the watch started, and whether the
    /// request's control was cancelled.
    Gone(String, Duration, bool),
    /// The request was released and answered.
    Answered(String),
}

/// A transport handler for every `POST`: reads the body, starts the client watch, and
/// waits, writing nothing, until the client goes (reported, nothing answered) or the test
/// releases every held request (answered `200 {"held": true}`), within [`DEADLINE`].
struct Watching {
    seen: mpsc::UnboundedSender<Seen>,
    release: watch::Receiver<bool>,
}

impl Handler for Watching {
    fn handle(&self, mut exchange: Exchange) -> HandlerFuture<'_> {
        Box::pin(async move {
            let path = exchange.head().route_path().to_owned();
            let _ = exchange.read_body().await;
            let control = ControlHandle::new();
            let probe = control.probe();
            let start = Instant::now();
            let Some(mut client) = exchange.watch_client(control) else {
                return;
            };
            let _ = self.seen.send(Seen::Holding(path.clone()));
            let mut release = self.release.clone();
            let outcome = tokio::time::timeout(DEADLINE, async {
                tokio::select! {
                    () = client.gone() => Some(start.elapsed()),
                    _ = release.wait_for(|r| *r) => None,
                }
            })
            .await;
            match outcome {
                Ok(Some(after)) => {
                    let _ = self
                        .seen
                        .send(Seen::Gone(path, after, probe.is_cancelled()));
                }
                Ok(None) => {
                    let _ = exchange.responder().json(200, "{\"held\": true}").await;
                    let _ = self.seen.send(Seen::Answered(path));
                }
                Err(_) => {}
            }
        })
    }
}

/// A server around [`Watching`], its reports and its release switch.
struct Held {
    server: TestServer,
    seen: mpsc::UnboundedReceiver<Seen>,
    release: watch::Sender<bool>,
}

impl Held {
    async fn start() -> Self {
        let (tx, seen) = mpsc::unbounded_channel();
        let (release, rx) = watch::channel(false);
        let handler = Watching {
            seen: tx,
            release: rx,
        };
        let server = TestServer::with_handler(Arc::new(handler), TransportConfig::default()).await;
        Self {
            server,
            seen,
            release,
        }
    }

    fn request(&self, path: &str) -> Vec<u8> {
        RawRequest::post(path)
            .header("Host", &self.server.host())
            .json("{}")
            .to_bytes()
    }

    /// A connection that has sent its request to `path`.
    async fn send(&self, path: &str) -> TcpStream {
        let mut s = connect(self.server.addr).await;
        write(&mut s, &self.request(path)).await;
        s
    }

    async fn next(&mut self) -> Seen {
        match tokio::time::timeout(DEADLINE, self.seen.recv()).await {
            Ok(Some(seen)) => seen,
            other => panic!("no report from the handler: {other:?}"),
        }
    }

    async fn holding(&mut self, path: &str) {
        match self.next().await {
            Seen::Holding(p) if p == path => {}
            other => panic!("{path} should be held, got {other:?}"),
        }
    }

    /// Releases every held request, stops the server and joins what is in flight.
    async fn stop(self) {
        let _ = self.release.send(true);
        let mut in_flight = self.server.stop().await;
        let joined = tokio::time::timeout(DEADLINE, async {
            while let Some(r) = in_flight.join_next().await {
                assert!(r.is_ok(), "a connection task failed: {r:?}");
            }
        })
        .await;
        assert!(joined.is_ok(), "connections still in flight after the stop");
    }
}

// --------------------------------------------- 1. a half-close before a quick answer

/// The chat request of these tests, as raw bytes for `server`.
fn chat_request(server: &TestServer, body: &str) -> Vec<u8> {
    RawRequest::post("/v1/chat/completions")
        .header("Host", &server.host())
        .json(body)
        .to_bytes()
}

/// Sends `request`, optionally shutting the sending side at once, and reads to the end.
async fn exchange_with(addr: std::net::SocketAddr, request: &[u8], half_close: bool) -> Vec<u8> {
    let mut s = connect(addr).await;
    write(&mut s, request).await;
    if half_close {
        assert!(s.shutdown().await.is_ok(), "shutdown of the sending side");
    }
    let raw = read_to_eof(&mut s).await;
    drop(s);
    raw
}

// Donor lines: serve/server.py:5033-5036 (`while not cancel.wait(every)` before each
// `select`). A client that sends its request and then shuts its sending side (an HTTP/1.0
// client such as `nc -N`) reads as end of file from the start, but the first check comes
// one interval later: an answer ready before it reaches the client in full, byte for byte
// the answer of the same request without the half-close, collected or streamed.
#[tokio::test]
async fn a_half_closed_request_gets_the_whole_answer_ready_within_the_first_interval() {
    let finished = Finished::default();
    let engine = match script("Hi!", DEFAULT_MAX_CONTEXT).build() {
        Ok(f) => shared(f),
        Err(e) => panic!("{e}"),
    };
    let server = match builder(engine)
        .observer(Arc::new(finished.clone()))
        .start()
        .await
    {
        Ok(s) => s,
        Err(e) => panic!("the test server did not start: {e}"),
    };
    let mut turns = 0;
    for body in [chat(""), chat("\"stream\": true")] {
        let request = chat_request(&server, &body);
        let plain = parse_response(&exchange_with(server.addr, &request, false).await);
        let half = parse_response(&exchange_with(server.addr, &request, true).await);
        turns += 2;
        assert_eq!(plain.status, 200, "{}", plain.text());
        assert_eq!(normalized(&half), normalized(&plain), "{body}");
        let records = finished.wait(turns).await;
        for r in records.iter().skip(turns - 2) {
            assert_eq!(r.finish, "stop", "{body}: {r:?}");
            assert!(!r.cancelled, "{body}: {r:?}");
            // Three letters and the end-of-turn token.
            assert_eq!(r.output_tokens, 4, "{body}: {r:?}");
        }
    }
    // The collected answer, in full: not the empty one with `content: null`.
    let request = chat_request(&server, &chat(""));
    let half = parse_response(&exchange_with(server.addr, &request, true).await);
    let json = half.json();
    assert_eq!(json["choices"][0]["message"]["content"], "Hi!");
    assert_eq!(json["choices"][0]["finish_reason"], "stop");
    assert_eq!(json["usage"]["completion_tokens"], 4);
    let records = finished.wait(turns + 1).await;
    assert!(records.iter().all(|r| r.finish == "stop"), "{records:?}");
    let mut in_flight = server.stop().await;
    let joined = tokio::time::timeout(DEADLINE, async {
        while in_flight.join_next().await.is_some() {}
    })
    .await;
    assert!(joined.is_ok());
}

// ------------------------------------------ 2. a half-close before a long answer

// Donor lines: serve/server.py:5033-5038 (wait 0.5 s, then `select` with a zero timeout and
// `recv(1, MSG_PEEK) == b""` sets the cancel). A half-closed request whose handler takes
// longer than one interval is cancelled at the first check, never before it: no earlier
// than 0.5 s and before 1.25 s after its watch started (bounds in the module comment).
#[tokio::test]
async fn a_half_closed_request_that_takes_longer_is_cancelled_at_the_first_check() {
    let mut held = Held::start().await;
    let mut s = held.send("/long").await;
    assert!(s.shutdown().await.is_ok(), "shutdown of the sending side");
    held.holding("/long").await;
    match held.next().await {
        Seen::Gone(path, after, cancelled) => {
            assert_eq!(path, "/long");
            assert!(cancelled, "the watch cancels the control");
            assert!(
                after >= WATCH_INTERVAL,
                "cancelled before the first check: {after:?}"
            );
            assert!(
                after < Duration::from_millis(1250),
                "not cancelled at the first check: {after:?}"
            );
        }
        other => panic!("the half-closed request should be cancelled, got {other:?}"),
    }
    // A cancelled request answers nothing; the connection closes.
    let raw = read_to_eof(&mut s).await;
    assert!(raw.is_empty(), "{:?}", String::from_utf8_lossy(&raw));
    drop(s);
    held.stop().await;
}

// ------------------------------------------ 3. a client that closes while it waits

// Donor lines: serve/server.py:5033-5041 (an end of file, or a `ConnectionError` from a
// reset, at a check sets the cancel). A client that closes its socket, or resets it, while
// its request waits is still noticed within 1 s of the close, the bound of API-02.
#[tokio::test]
async fn a_client_that_closes_while_it_waits_is_noticed_within_a_second() {
    let mut held = Held::start().await;
    for (path, reset) in [("/closed", false), ("/reset", true)] {
        let s = held.send(path).await;
        held.holding(path).await;
        if reset {
            assert!(s.set_zero_linger().is_ok());
        }
        let closed = Instant::now();
        drop(s);
        match held.next().await {
            Seen::Gone(p, _, cancelled) => {
                assert_eq!(p, path);
                assert!(cancelled, "{path}: the watch cancels the control");
                let waited = closed.elapsed();
                assert!(
                    waited < Duration::from_secs(1),
                    "{path}: noticed {waited:?} after the close"
                );
            }
            other => panic!("{path}: the closed client should be noticed, got {other:?}"),
        }
    }
    held.stop().await;
}

// --------------------------------------------- 4. data from the client is not an end

// Donor lines: serve/server.py:5035-5036 (`recv(1, MSG_PEEK)` returns the client's byte,
// which is not `b""`, and the loop goes on). Bytes the client sends after its request are
// not an end, at two checks in a row, also when a half-close follows them (the unread
// bytes come first); released, both requests are answered as before.
#[tokio::test]
async fn bytes_after_the_request_are_not_an_end() {
    let mut held = Held::start().await;
    let mut data = held.send("/data").await;
    held.holding("/data").await;
    let mut data_then_half = held.send("/data-half").await;
    held.holding("/data-half").await;
    // Sent after the watch started, so they wait in the socket where the watcher peeks.
    write(&mut data, b"more bytes the handler never reads").await;
    write(&mut data_then_half, b"more bytes").await;
    assert!(data_then_half.shutdown().await.is_ok());
    // The checks at 0.5 s and 1 s of both watches fall inside this window.
    let verdict = tokio::time::timeout(Duration::from_millis(1100), held.seen.recv()).await;
    assert!(verdict.is_err(), "unread data is not an end: {verdict:?}");
    let _ = held.release.send(true);
    let mut answered = Vec::new();
    for _ in 0..2 {
        match held.next().await {
            Seen::Answered(path) => answered.push(path),
            other => panic!("a released request should be answered, got {other:?}"),
        }
    }
    answered.sort();
    assert_eq!(answered, ["/data", "/data-half"]);
    // The server closes a connection whose bytes it never read, which the kernel turns into
    // a reset after the answer; the answer itself arrives first.
    for s in [&mut data, &mut data_then_half] {
        let r = parse_response(&read_to_eof_allowing_reset(s).await);
        assert_eq!(r.status, 200);
        assert_eq!(r.text(), "{\"held\": true}");
    }
    drop(data);
    drop(data_then_half);
    held.stop().await;
}
