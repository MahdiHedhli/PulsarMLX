//! Transport tests of work package API-02 beyond the donor's methods: Python's error pages
//! (400, 414, 431, 501, 505), HTTP/0.9, the absence of keep-alive and of chunked answers,
//! the `Server` header (approved deviation P-1), conflicting framing (approved deviation
//! P-2), chunked bodies, body limits, the per-operation timeout, the client watcher, panics
//! and the graceful stop.
//!
//! Expected error pages are the bytes CPython 3.14.7's `BaseHTTPRequestHandler` writes for
//! the same request (recorded with `python3 -I` and the standard library only, with the
//! version string and date replaced); no donor file was run. The tests marked as adapted
//! come from the archived PulsarMLX serving crate (tag
//! `archive/2026-09-21/feat/openai-serving`, `crates/serve-synthetic/tests/raw_http.rs`),
//! with the donor's rules where the two differ.
//!
//! Behavior reference: project-maya serve/server.py:5346-5372, 5403-5455, 5019-5044,
//! 6463-6474 and 6715-6734 at 7e68a30f.

#[path = "api02_kit.rs"]
mod kit;

use std::time::Duration;

use console_http::transport::{
    bind_host, probe_port, BodyError, ClientGone, TransportConfig, CONFLICTING_FRAMING,
};
use kit::*;
use tokio::io::AsyncWriteExt;
use tokio::time::Instant;

/// CPython 3.14's `DEFAULT_ERROR_MESSAGE` filled in, as `send_error` writes it.
fn python_page(code: u16, message: &str, explain: &str) -> String {
    format!(
        "<!DOCTYPE HTML>\n<html lang=\"en\">\n    <head>\n        <meta charset=\"utf-8\">\n        \
<style type=\"text/css\">\n            :root {{\n                color-scheme: light dark;\n            }}\n        \
</style>\n        <title>Error response</title>\n    </head>\n    <body>\n        <h1>Error response</h1>\n        \
<p>Error code: {code}</p>\n        <p>Message: {message}.</p>\n        \
<p>Error code explanation: {code} - {explain}.</p>\n    </body>\n</html>\n"
    )
}

/// The head `send_error` writes, `Date` masked.
fn python_error_head(code: u16, reason: &str, length: usize) -> String {
    format!(
        "HTTP/1.0 {code} {reason}\r\n{}\r\nDate: <date>\r\nConnection: close\r\n\
         Content-Type: text/html;charset=utf-8\r\nContent-Length: {length}",
        server_line()
    )
}

#[tokio::test]
async fn transport_errors_are_pythons_pages() {
    let server = TestServer::start().await;
    let long_uri = format!("GET /{} HTTP/1.1\r\n\r\n", "a".repeat(65536)).into_bytes();
    let long_header = format!("GET / HTTP/1.1\r\nX: {}\r\n\r\n", "v".repeat(65536)).into_bytes();
    let mut many = b"GET / HTTP/1.1\r\n".to_vec();
    for i in 0..100 {
        many.extend_from_slice(format!("X-{i}: v\r\n").as_bytes());
    }
    many.extend_from_slice(b"\r\n");
    let cases: Vec<(Vec<u8>, u16, &str, &str)> = vec![
        (
            b"PUT / HTTP/1.1\r\nHost: x\r\n\r\n".to_vec(),
            501,
            "Unsupported method ('PUT')",
            "Server does not support this operation",
        ),
        (
            b"get / HTTP/1.1\r\n\r\n".to_vec(),
            501,
            "Unsupported method ('get')",
            "Server does not support this operation",
        ),
        (
            b"PATCH /v1/x HTTP/1.0\r\n\r\n".to_vec(),
            501,
            "Unsupported method ('PATCH')",
            "Server does not support this operation",
        ),
        (
            b"P\xe9T / HTTP/1.1\r\n\r\n".to_vec(),
            501,
            "Unsupported method ('P\u{e9}T')",
            "Server does not support this operation",
        ),
        (long_uri, 414, "URI Too Long", "URI is too long"),
        (
            long_header,
            431,
            "Line too long",
            "got more than 65536 bytes when reading header line",
        ),
        (many, 431, "Too many headers", "got more than 100 headers"),
        (
            b"GET / HTTP/2.0\r\n\r\n".to_vec(),
            505,
            "Invalid HTTP version (2.0)",
            "Cannot fulfill request",
        ),
        (
            b"GET / x HTTP/1.1\r\n\r\n".to_vec(),
            400,
            "Bad request syntax ('GET / x HTTP/1.1')",
            "Bad request syntax or unsupported method",
        ),
        (
            b"GET / HTTP/1.x\r\n\r\n".to_vec(),
            400,
            "Bad request version ('HTTP/1.x')",
            "Bad request syntax or unsupported method",
        ),
        (
            b"POST /x\r\n".to_vec(),
            400,
            "Bad HTTP/0.9 request type ('POST')",
            "Bad request syntax or unsupported method",
        ),
    ];
    for (request, code, message, explain) in cases {
        let r = exchange(server.addr, &request).await;
        let page = python_page(code, message, explain);
        assert_eq!(
            r.head,
            python_error_head(code, message, page.len()),
            "{message}"
        );
        assert_eq!(r.text(), page, "{message}");
    }
}

#[tokio::test]
async fn a_head_request_gets_the_501_head_only() {
    let server = TestServer::start().await;
    let r = exchange(server.addr, b"HEAD / HTTP/1.1\r\n\r\n").await;
    let page = python_page(
        501,
        "Unsupported method ('HEAD')",
        "Server does not support this operation",
    );
    assert_eq!(
        r.head,
        python_error_head(501, "Unsupported method ('HEAD')", page.len())
    );
    assert!(r.body.is_empty());
}

#[tokio::test]
async fn the_end_headers_hook_reaches_the_501_page() {
    let server = TestServer::with(
        TransportConfig::default(),
        vec![("Access-Control-Allow-Origin".into(), "*".into())],
    )
    .await;
    let r = exchange(server.addr, b"PUT /v1/models HTTP/1.1\r\n\r\n").await;
    assert!(
        r.head
            .ends_with("Content-Length: 481\r\nAccess-Control-Allow-Origin: *"),
        "{}",
        r.head
    );
    // And every handler answer.
    let r = exchange(server.addr, b"GET /head HTTP/1.1\r\n\r\n").await;
    assert!(
        r.head
            .ends_with("Content-Length: 2\r\nAccess-Control-Allow-Origin: *"),
        "{}",
        r.head
    );
}

#[tokio::test]
async fn the_end_headers_hook_reaches_the_431_pages_only_of_the_head_errors() {
    // The donor's end_headers override runs inside send_error. For a 431 page Python has set
    // self.command and self.path, so a wildcard cors_origins adds its header; for the 400,
    // 414 and 505 pages of the request line self.path is not set and the hook is not run.
    let server = TestServer::with(
        TransportConfig::default(),
        vec![("Access-Control-Allow-Origin".into(), "*".into())],
    )
    .await;
    let mut many = b"GET /v1/models HTTP/1.1\r\n".to_vec();
    for i in 0..101 {
        many.extend_from_slice(format!("X-{i}: v\r\n").as_bytes());
    }
    many.extend_from_slice(b"\r\n");
    let long_header = format!(
        "GET /v1/models HTTP/1.1\r\nX: {}\r\n\r\n",
        "v".repeat(65536)
    )
    .into_bytes();
    for (request, message, explain) in [
        (many, "Too many headers", "got more than 100 headers"),
        (
            long_header,
            "Line too long",
            "got more than 65536 bytes when reading header line",
        ),
    ] {
        let r = exchange(server.addr, &request).await;
        let page = python_page(431, message, explain);
        assert_eq!(
            r.head,
            format!(
                "{}\r\nAccess-Control-Allow-Origin: *",
                python_error_head(431, message, page.len())
            ),
            "{message}"
        );
        assert_eq!(r.text(), page, "{message}");
    }
    for request in [
        format!("GET /{} HTTP/1.1\r\n\r\n", "a".repeat(65536)).into_bytes(),
        b"GET /v1/models HTTP/2.0\r\n\r\n".to_vec(),
        b"GET /v1/models HTTP/1.x\r\n\r\n".to_vec(),
        b"GET /v1/models x HTTP/1.1\r\n\r\n".to_vec(),
    ] {
        let r = exchange(server.addr, &request).await;
        assert!(r.status >= 400, "{}", r.head);
        assert!(!r.head.contains("Access-Control"), "{}", r.head);
    }
}

#[tokio::test]
async fn http09_answers_carry_the_body_only() {
    let server = TestServer::start().await;
    let r = exchange(server.addr, b"GET /head\r\n").await;
    assert_eq!(r.raw, b"ok");
    // A three-word request line whose version is exactly HTTP/0.9 is answered the same way.
    let r = exchange(server.addr, b"PUT / HTTP/0.9\r\n\r\n").await;
    assert_eq!(
        String::from_utf8_lossy(&r.raw),
        python_page(
            501,
            "Unsupported method ('PUT')",
            "Server does not support this operation"
        )
    );
}

#[tokio::test]
async fn an_empty_request_line_closes_without_an_answer() {
    let server = TestServer::start().await;
    assert!(exchange(server.addr, b"\r\n").await.raw.is_empty());
    assert!(exchange_with_eof(server.addr, b"").await.raw.is_empty());
}

#[tokio::test]
async fn one_request_per_connection_without_keep_alive_or_chunking() {
    let mut server = TestServer::start().await;
    let two = b"GET /head HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: keep-alive\r\n\r\n\
                GET /head HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n";
    let r = exchange(server.addr, two).await;
    // Approved deviation P-1: the Server header names the product version, in the donor's
    // position.
    assert_eq!(
        r.head,
        format!(
            "HTTP/1.0 200 OK\r\n{}\r\nDate: <date>\r\nContent-Type: text/plain\r\nContent-Length: 2",
            server_line()
        )
    );
    assert_eq!(
        r.body, b"ok",
        "exactly one answer, then the connection closed"
    );
    let lower = String::from_utf8_lossy(&r.raw).to_ascii_lowercase();
    assert!(!lower.contains("keep-alive") && !lower.contains("transfer-encoding"));
    assert!(matches!(server.next_seen().await, Seen::Head(..)));
    assert!(
        server.seen.try_recv().is_err(),
        "the second request was never read"
    );
    let date = String::from_utf8_lossy(&r.raw)
        .split("\r\n")
        .find_map(|l| l.strip_prefix("Date: ").map(str::to_owned))
        .unwrap_or_default();
    assert!(date.ends_with(" GMT") && date.len() == 29, "{date}");
}

#[tokio::test]
async fn the_request_head_reaches_the_handler_as_python_parses_it() {
    let mut server = TestServer::start().await;
    let request =
        b"GET //head/?a=1&force=1 HTTP/1.1\r\nHost: 127.0.0.1\r\nX-Folded: one\r\n two\r\n\
                    x-folded: second\r\nBad line\r\nAfter: lost\r\n\r\n";
    let r = exchange(server.addr, request).await;
    assert_eq!(r.status, 200);
    let Seen::Head(head, peer) = server.next_seen().await else {
        panic!("no head");
    };
    assert_eq!(head.method(), "GET");
    assert_eq!(head.path(), "/head/?a=1&force=1");
    assert_eq!(head.route_path(), "/head");
    assert_eq!(head.query(), "a=1&force=1");
    assert_eq!(head.version(), "HTTP/1.1");
    assert_eq!(head.headers().get("x-folded"), Some("one\r\n two"));
    assert_eq!(head.headers().get_all("X-Folded").count(), 2);
    assert_eq!(head.headers().get("After"), None);
    assert!(peer.ip().is_loopback());
}

#[tokio::test]
async fn both_content_length_and_chunked_are_refused() {
    // Approved deviation P-2 (owner decision of 2026-11-14): the donor would decode the
    // chunked body; the console answers 400 before reading anything, before the handler is
    // called.
    let mut server = TestServer::start().await;
    let r = exchange(
        server.addr,
        &donor_post(
            "Content-Length: 5\r\nTransfer-Encoding: chunked\r\n",
            b"5\r\nhello\r\n0\r\n\r\n",
        ),
    )
    .await;
    let body = invalid_request(CONFLICTING_FRAMING);
    assert_eq!(
        r.head,
        format!(
            "HTTP/1.0 400 Bad Request\r\n{}\r\nDate: <date>\r\nContent-Type: application/json\r\nContent-Length: {}",
            server_line(),
            body.len()
        )
    );
    assert_eq!(r.text(), body);
    // On a route that never reads a body, for any served method, with chunked in a second
    // Transfer-Encoding header, and with the end-headers hook's headers on the answer.
    let hooked = TestServer::with(
        TransportConfig::default(),
        vec![("Access-Control-Allow-Origin".into(), "*".into())],
    )
    .await;
    for request in [
        &b"GET /head HTTP/1.1\r\nContent-Length: 5\r\nTransfer-Encoding: chunked\r\n\r\n"[..],
        b"DELETE /head HTTP/1.1\r\nTransfer-Encoding: chunked\r\nContent-Length: 0\r\n\r\n",
        b"OPTIONS /v1/models HTTP/1.1\r\nTransfer-Encoding: chunked\r\nContent-Length: 0\r\n\r\n",
        b"POST /echo HTTP/1.1\r\nTransfer-Encoding: gzip\r\nTransfer-Encoding: chunked\r\n\
          Content-Length: 2\r\n\r\nab",
    ] {
        let r = exchange(hooked.addr, request).await;
        assert_eq!(r.status, 400, "{:?}", String::from_utf8_lossy(request));
        assert!(
            r.head.ends_with("\r\nAccess-Control-Allow-Origin: *"),
            "{}",
            r.head
        );
        assert_eq!(r.text(), body);
    }
    let mut hooked = hooked;
    assert!(
        hooked.seen.try_recv().is_err(),
        "the handler was never called"
    );
    assert!(
        server.seen.try_recv().is_err(),
        "the handler was never called"
    );
    // Chunked framing alone still decodes.
    let r = exchange(
        server.addr,
        &donor_post("Transfer-Encoding: chunked\r\n", b"5\r\nhello\r\n0\r\n\r\n"),
    )
    .await;
    assert_eq!(r.text(), "{\"received\": 5}");
}

#[tokio::test]
async fn chunked_bodies_with_extensions_and_trailers_decode() {
    let mut server = TestServer::start().await;
    let body = b"4;name=value\r\nWiki\r\n5\r\npedia\r\n0\r\nExpires: never\r\nX-Sum: 1\r\n\r\n";
    let r = exchange(
        server.addr,
        &donor_post("Transfer-Encoding: gzip, chunked\r\n", body),
    )
    .await;
    assert_eq!(r.text(), "{\"received\": 9}");
    assert!(matches!(server.next_seen().await, Seen::Body(Ok(b)) if b == b"Wikipedia"));
}

/// Adapted from the archived crate's `chunked_body_exceeding_accumulated_limit_is_rejected`:
/// chunks each under the limit, together over it, are refused with 413 by the running total.
#[tokio::test]
async fn chunked_bodies_over_the_limit_in_total_are_refused() {
    let config = TransportConfig {
        max_body_bytes: 1 << 20,
        ..TransportConfig::default()
    };
    let server = TestServer::with(config, Vec::new()).await;
    let mut stream = connect(server.addr).await;
    write(
        &mut stream,
        &donor_post("Transfer-Encoding: chunked\r\n", b""),
    )
    .await;
    let chunk = vec![b'x'; 300 * 1024];
    'send: for _ in 0..4 {
        for part in [
            format!("{:x}\r\n", chunk.len()).into_bytes(),
            chunk.clone(),
            b"\r\n".to_vec(),
        ] {
            // The server answers and closes as soon as the total passes the limit.
            if stream.write_all(&part).await.is_err() {
                break 'send;
            }
        }
    }
    let r = parse_response(&read_to_eof(&mut stream).await);
    assert_eq!(r.status, 413);
    assert_eq!(
        r.text(),
        invalid_request(
            "the request body is larger than 1 MiB (PULSAR_CONSOLE_MAX_BODY_MIB raises the limit)"
        )
    );
}

/// Adapted from the archived crate's `invalid_declared_length_is_rejected_by_the_parser`:
/// an oversized declared length is 413 even when the client sends no body and ends its side;
/// the other values follow the donor's `int()` rule (a huge integer is over the limit, `+5`
/// is five), not the archived crate's parser.
#[tokio::test]
async fn declared_lengths_follow_the_donor() {
    let mut server = TestServer::start().await;
    let over = (256u64 << 20) + 1;
    let r = exchange_with_eof(
        server.addr,
        &donor_post(&format!("Content-Length: {over}\r\n"), b""),
    )
    .await;
    assert_eq!(r.status, 413);
    let _ = server.next_seen().await;
    for (value, status) in [
        ("abc", 400),
        ("99999999999999999999999999", 413),
        ("-1", 400),
        ("1 2", 400),
    ] {
        let r = exchange_with_eof(
            server.addr,
            &donor_post(&format!("Content-Length: {value}\r\n"), b""),
        )
        .await;
        assert_eq!(r.status, status, "Content-Length: {value}");
        let _ = server.next_seen().await;
    }
    // "+5" is five bytes; the client ends after none, so the body is short (Python's read(n)).
    let r = exchange_with_eof(server.addr, &donor_post("Content-Length: +5\r\n", b"")).await;
    assert_eq!(r.text(), "{\"received\": 0}");
    assert!(matches!(server.next_seen().await, Seen::Body(Ok(b)) if b.is_empty()));
}

/// Adapted from the archived crate's `parser_rejects_conflicting_framing_and_routes_are_explicit`:
/// the donor reads the first `Content-Length` of two, and returns a body cut short by the
/// client as it arrived (the router then refuses it as JSON, in API-03).
#[tokio::test]
async fn repeated_lengths_and_short_bodies_follow_the_donor() {
    let mut server = TestServer::start().await;
    let r = exchange(
        server.addr,
        &donor_post("Content-Length: 1\r\nContent-Length: 2\r\n", b"{}"),
    )
    .await;
    assert_eq!(r.text(), "{\"received\": 1}");
    assert!(matches!(server.next_seen().await, Seen::Body(Ok(b)) if b == b"{"));
    let r = exchange_with_eof(server.addr, &donor_post("Content-Length: 20\r\n", b"{}")).await;
    assert_eq!(r.text(), "{\"received\": 2}");
    assert!(matches!(server.next_seen().await, Seen::Body(Ok(b)) if b == b"{}"));
}

async fn read_within(stream: &mut tokio::net::TcpStream, limit: Duration) -> Option<Vec<u8>> {
    use tokio::io::AsyncReadExt;
    let mut raw = Vec::new();
    match tokio::time::timeout(limit, stream.read_to_end(&mut raw)).await {
        Ok(_) => Some(raw),
        Err(_) => None,
    }
}

// The timeout tests run on the real clock with a timeout of one or two seconds: with the
// clock paused, tokio advances time before it notices socket readiness, so a paused clock
// cannot drive a test whose other side is a real socket. Each asserts a lower bound (the
// connection is not dropped early) and a generous upper bound.

#[tokio::test]
async fn a_stalled_head_is_dropped_after_the_timeout() {
    // Per socket operation, then the connection closes unanswered (the donor's default is
    // 300 s; the rule is the same for any value).
    let config = TransportConfig::from_raw(None, None, Some("1"));
    let server = TestServer::with(config, Vec::new()).await;
    let mut stream = connect(server.addr).await;
    write(&mut stream, b"POST /echo HTTP/1.1\r\nHost: 127.0.0.1\r\n").await;
    let start = Instant::now();
    let raw = read_within(&mut stream, Duration::from_secs(10)).await;
    assert_eq!(raw, Some(Vec::new()), "closed without an answer");
    let waited = start.elapsed();
    assert!(
        waited >= Duration::from_millis(990) && waited < Duration::from_secs(6),
        "{waited:?}"
    );
}

#[tokio::test]
async fn the_timeout_is_per_operation_not_per_request() {
    let config = TransportConfig::from_raw(None, None, Some("2"));
    assert_eq!(config.request_timeout, Duration::from_secs(2));
    let mut server = TestServer::with(config, Vec::new()).await;
    let mut stream = connect(server.addr).await;
    let start = Instant::now();
    let request = donor_post("Content-Length: 4\r\n", b"abcd");
    // A piece every 0.5 s: each wait is well under the 2 s timeout, the whole request is
    // not.
    for piece in request.chunks(16) {
        write(&mut stream, piece).await;
        tokio::time::sleep(Duration::from_millis(500)).await;
    }
    let raw = read_within(&mut stream, Duration::from_secs(10))
        .await
        .unwrap_or_default();
    assert!(start.elapsed() > Duration::from_secs(2));
    assert_eq!(parse_response(&raw).text(), "{\"received\": 4}");
    assert!(matches!(server.next_seen().await, Seen::Body(Ok(b)) if b == b"abcd"));
}

#[tokio::test]
async fn a_stalled_body_is_dropped_after_the_timeout() {
    let config = TransportConfig::from_raw(None, None, Some("1"));
    let mut server = TestServer::with(config, Vec::new()).await;
    let mut stream = connect(server.addr).await;
    write(&mut stream, &donor_post("Content-Length: 10\r\n", b"ab")).await;
    let start = Instant::now();
    let raw = read_within(&mut stream, Duration::from_secs(10)).await;
    assert_eq!(raw, Some(Vec::new()), "closed without an answer");
    let waited = start.elapsed();
    assert!(
        waited >= Duration::from_millis(990) && waited < Duration::from_secs(6),
        "{waited:?}"
    );
    assert!(matches!(
        server.next_seen().await,
        Seen::Body(Err(BodyError::Gone(ClientGone::TimedOut)))
    ));
}

#[tokio::test]
async fn data_from_the_client_is_not_an_end() {
    let mut server = TestServer::start().await;
    let release = server.arm_release();
    let mut stream = connect(server.addr).await;
    write(
        &mut stream,
        b"POST /hold HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: 2\r\n\r\n{}",
    )
    .await;
    assert!(matches!(server.next_seen().await, Seen::Holding));
    // Sent after the watch started, so the bytes wait in the socket (where the watcher
    // peeks), not in the connection's read buffer.
    write(&mut stream, b"more bytes the handler never reads").await;
    // More than two watch intervals on the real clock with unread data waiting: no verdict.
    let verdict = tokio::time::timeout(Duration::from_millis(1300), server.seen.recv()).await;
    assert!(verdict.is_err(), "unread data is not an end: {verdict:?}");
    let _ = release.send(());
    let raw = read_within(&mut stream, Duration::from_secs(60))
        .await
        .unwrap_or_default();
    assert_eq!(parse_response(&raw).text(), "{\"held\": true}");
}

#[tokio::test]
async fn a_reset_or_a_half_close_is_a_gone_client() {
    let mut server = TestServer::start().await;
    let hold = |path: &str| {
        let body = b"{}";
        let mut out = format!(
            "POST {path} HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: {}\r\n\r\n",
            body.len()
        )
        .into_bytes();
        out.extend_from_slice(body);
        out
    };
    let mut reset = connect(server.addr).await;
    write(&mut reset, &hold("/hold")).await;
    assert!(matches!(server.next_seen().await, Seen::Holding));
    assert!(reset.set_zero_linger().is_ok());
    drop(reset);
    assert!(matches!(server.next_seen().await, Seen::Cancelled));
    // A client that shuts its sending side reads as end of file, as in the donor.
    let mut half = connect(server.addr).await;
    write(&mut half, &hold("/hold")).await;
    assert!(matches!(server.next_seen().await, Seen::Holding));
    assert!(half.shutdown().await.is_ok());
    assert!(matches!(server.next_seen().await, Seen::Cancelled));
}

#[tokio::test]
async fn a_panicking_handler_closes_only_its_connection() {
    let server = TestServer::start().await;
    // In the future, in the call that builds it, and in the end-headers hook (also when
    // the hook runs for a 431 page).
    let mut many = b"GET /panic-hook HTTP/1.1\r\n".to_vec();
    for i in 0..101 {
        many.extend_from_slice(format!("X-{i}: v\r\n").as_bytes());
    }
    many.extend_from_slice(b"\r\n");
    for request in [
        b"GET /panic HTTP/1.1\r\n\r\n".to_vec(),
        b"GET /panic-sync HTTP/1.1\r\n\r\n".to_vec(),
        b"GET /panic-hook HTTP/1.1\r\n\r\n".to_vec(),
        many,
    ] {
        let r = exchange(server.addr, &request).await;
        assert!(r.raw.is_empty(), "{:?}", String::from_utf8_lossy(&r.raw));
        let r = exchange(server.addr, b"GET /head HTTP/1.1\r\n\r\n").await;
        assert_eq!(r.status, 200);
    }
}

#[tokio::test]
async fn a_graceful_stop_lets_requests_in_flight_finish() {
    let mut server = TestServer::start().await;
    let addr = server.addr;
    let release = server.arm_release();
    let mut held = connect(addr).await;
    write(
        &mut held,
        b"POST /hold HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: 0\r\n\r\n",
    )
    .await;
    assert!(matches!(server.next_seen().await, Seen::Holding));
    let mut in_flight = server.stop().await;
    assert_eq!(in_flight.len(), 1);
    assert!(
        tokio::net::TcpStream::connect(addr).await.is_err(),
        "no longer accepting"
    );
    let _ = release.send(());
    let r = parse_response(&read_to_eof(&mut held).await);
    assert_eq!(r.text(), "{\"held\": true}");
    let finished = tokio::time::timeout(DEADLINE, in_flight.join_next()).await;
    assert!(matches!(finished, Ok(Some(Ok(())))));
}

#[tokio::test]
async fn hosts_bind_as_the_donors_ipv4_server_does() {
    let config = TransportConfig::default();
    let listener = bind_host("localhost", 0, config);
    assert!(listener.as_ref().is_ok_and(|l| l
        .local_addr()
        .is_ok_and(|a| a.ip().is_loopback() && a.is_ipv4())));
    assert!(bind_host("::1", 0, config).is_err());
    let Ok(listener) = bind_host("127.0.0.1", 0, config) else {
        panic!("bind");
    };
    let port = listener.local_addr().map(|a| a.port()).unwrap_or(0);
    assert!(probe_port("127.0.0.1", port).is_err(), "the port is taken");
    drop(listener);
    assert!(
        probe_port("127.0.0.1", port).is_ok(),
        "the port is free again"
    );
}
