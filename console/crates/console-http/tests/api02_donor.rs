//! Donor tests of work package API-02, re-expressed against the transport with the test
//! kit's transport probe (`console_testkit::server::probe`).
//!
//! Provenance: translated from project-maya serve/test_server.py::RequestBodies, serve/test_server.py::GoneClients::test_a_queued_request_leaves_when_its_client_goes and serve/test_server.py::QueuedKeepAlives::test_keep_alives_while_queued at 7e68a30f (MIT); license text in console/LICENSES/project-maya-MIT.txt.
//!
//! The donor's methods send raw bytes to `/v1/chat/completions` of a full server. Here the
//! router, the validation and the engine do not exist yet, so the kit's `TransportProbe`
//! stands behind the transport and the kit's raw client writes the donor's bytes. Methods whose assertions need those later packages are re-expressed only
//! in their transport part, and their ledger rows stay pending (each test says so).

use std::time::Instant;

use console_http::transport::{BodyError, TransportConfig};
use console_testkit::raw::*;
use console_testkit::server::probe::{ProbeServer, Seen};

const MSG: &[u8] = b"{\"model\": \"m\", \"messages\": [{\"role\": \"user\", \"content\": \"hi\"}]}";

// Donor: serve/test_server.py::RequestBodies::test_a_body_over_the_limit_is_refused_unread
#[tokio::test]
async fn a_body_over_the_limit_is_refused_unread() {
    let mut server = ProbeServer::start().await;
    // 300 MiB declared, no body byte ever sent: the answer still arrives.
    let r = exchange(
        server.addr,
        &donor_post(&format!("Content-Length: {}\r\n", 300u64 << 20), b""),
    )
    .await;
    assert_eq!(r.status, 413);
    assert!(r.text().contains("MiB"), "{}", r.text());
    let body = invalid_request(
        "the request body is larger than 256 MiB (PULSAR_CONSOLE_MAX_BODY_MIB raises the limit)",
    );
    assert_eq!(r.text(), body);
    assert_eq!(
        r.head,
        format!(
            "HTTP/1.0 413 Content Too Large\r\n{}\r\nDate: <date>\r\nContent-Type: application/json\r\nContent-Length: {}",
            server_line(),
            body.len()
        )
    );
    assert!(
        matches!(server.next_seen().await, Seen::Body(Err(BodyError::Refused(e))) if e.status() == 413)
    );
}

// Donor: serve/test_server.py::RequestBodies::test_a_bad_content_length
#[tokio::test]
async fn a_bad_content_length() {
    let server = ProbeServer::start().await;
    for value in ["abc", "-5"] {
        let r = exchange(
            server.addr,
            &donor_post(&format!("Content-Length: {value}\r\n"), b""),
        )
        .await;
        assert_eq!(r.status, 400, "Content-Length: {value}");
        assert_eq!(r.text(), invalid_request("invalid Content-Length"));
    }
}

/// Transport part of serve/test_server.py::RequestBodies::test_a_chunked_body: the chunked
/// body reaches the handler decoded, and a bad chunk size is 400. The donor's `200` with
/// the engine's "hello" needs the chat route (API-08); that ledger row stays pending.
#[tokio::test]
async fn a_chunked_body_is_decoded_for_the_handler() {
    let mut server = ProbeServer::start().await;
    let mut body = format!("{:x}\r\n", MSG.len()).into_bytes();
    body.extend_from_slice(MSG);
    body.extend_from_slice(b"\r\n0\r\n\r\n");
    let r = exchange(
        server.addr,
        &donor_post("Transfer-Encoding: chunked\r\n", &body),
    )
    .await;
    assert_eq!(r.status, 200, "{}", r.text());
    assert_eq!(r.text(), format!("{{\"received\": {}}}", MSG.len()));
    assert!(matches!(server.next_seen().await, Seen::Body(Ok(b)) if b == MSG));
    let r = exchange(
        server.addr,
        &donor_post("Transfer-Encoding: chunked\r\n", b"zz\r\nab\r\n0\r\n\r\n"),
    )
    .await;
    assert_eq!(r.status, 400);
    assert_eq!(r.text(), invalid_request("malformed chunked request body"));
}

/// Transport part of serve/test_server.py::RequestBodies::test_a_malformed_body_is_a_400:
/// both bodies reach the handler intact, and an error the handler raises is answered with
/// its status and the donor's error body. The 400s themselves come from the JSON-object
/// check of the router (API-03) and from request validation (API-04); that ledger row stays
/// pending.
#[tokio::test]
async fn a_malformed_body_reaches_the_handler_intact() {
    let mut server = ProbeServer::start().await;
    let r = exchange(server.addr, &donor_post("Content-Length: 2\r\n", b"[]")).await;
    assert_eq!(r.status, 200);
    assert!(matches!(server.next_seen().await, Seen::Body(Ok(b)) if b == b"[]"));
    let bad = b"{\"model\": \"m\", \"messages\": [{\"role\": \"user\", \"content\": {\"no\": \"list\"}}, 7]}";
    let r = exchange(
        server.addr,
        &donor_post(&format!("Content-Length: {}\r\n", bad.len()), bad),
    )
    .await;
    assert_eq!(r.status, 200);
    assert!(matches!(server.next_seen().await, Seen::Body(Ok(b)) if b == bad));
}

// Donor: serve/test_server.py::RequestBodies::test_the_listen_backlog
#[tokio::test]
async fn the_listen_backlog() {
    let server = ProbeServer::start().await;
    assert!(server.backlog >= 256, "backlog {}", server.backlog);
    assert_eq!(TransportConfig::from_raw(None, None, None).backlog, 256);
    // The server answers with that listener.
    let r = exchange(
        server.addr,
        b"GET /head HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n",
    )
    .await;
    assert_eq!(r.status, 200);
}

/// The full-server form of serve/test_server.py::NoDelayStreaming::test_sse_sets_tcp_nodelay
/// (the method's own re-expression is the unit test `sse_sets_tcp_nodelay` in
/// `transport::response`): a streamed answer's socket has `TCP_NODELAY`, and the stream is
/// delimited by closing the connection.
#[tokio::test]
async fn sse_answers_set_tcp_nodelay() {
    let mut server = ProbeServer::start().await;
    let r = exchange(server.addr, &post_to("/sse", "Content-Length: 0\r\n", b"")).await;
    assert_eq!(
        r.head,
        format!(
            "HTTP/1.0 200 OK\r\n{}\r\nDate: <date>\r\nContent-Type: text/event-stream\r\nCache-Control: no-cache",
            server_line()
        )
    );
    assert_eq!(r.text(), "data: one\n\ndata: [DONE]\n\n");
    assert!(matches!(
        server.next_seen().await,
        Seen::NoDelay(false, true)
    ));
}

/// Transport part of serve/test_server.py::GoneClients::test_a_queued_request_leaves_when_its_client_goes:
/// requests that wait writing nothing, plain or after an SSE head, are cancelled through
/// their control when their client closes, within one second, while the request that kept
/// its client is answered as before. The queue that the request leaves belongs to ENG-09
/// and API-07; that ledger row stays pending.
#[tokio::test]
async fn a_waiting_request_is_cancelled_when_its_client_goes() {
    let mut server = ProbeServer::start().await;
    let release = server.arm_release();
    let hold = |path: &str| json_post(path, MSG);
    let mut first = connect(server.addr).await;
    write(&mut first, &hold("/hold")).await;
    assert!(matches!(server.next_seen().await, Seen::Holding));
    for path in ["/hold", "/hold-stream"] {
        let mut waiting = connect(server.addr).await;
        write(&mut waiting, &hold(path)).await;
        assert!(
            matches!(server.next_seen().await, Seen::Holding),
            "{path} should wait"
        );
        let closed = Instant::now();
        drop(waiting);
        assert!(
            matches!(server.next_seen().await, Seen::Cancelled),
            "{path}: still waiting after its client left"
        );
        assert!(
            closed.elapsed().as_secs_f64() < 1.0,
            "{path}: cancelled after {:?}",
            closed.elapsed()
        );
    }
    let _ = release.send(());
    let r = parse_response(&read_to_eof(&mut first).await);
    assert!(String::from_utf8_lossy(&r.raw).contains("200 OK"));
    assert_eq!(r.text(), "{\"held\": true}");
}

/// Transport part of serve/test_server.py::QueuedKeepAlives::test_keep_alives_while_queued:
/// SSE keep-alive comments written while a request waits reach the raw client as they are
/// written; a client that leaves while waiting is seen to go; after a wait the answer
/// follows the keep-alives unchanged. The queue and its ping setting belong to ENG-09 and
/// API-07; that ledger row stays pending.
#[tokio::test]
async fn keep_alives_reach_a_waiting_client() {
    let mut server = ProbeServer::start().await;
    let ping = || json_post("/ping", MSG);
    for _ in 0..2 {
        let mut s = connect(server.addr).await;
        write(&mut s, &ping()).await;
        assert!(matches!(server.next_seen().await, Seen::Holding));
        let waited = read_until(&mut s, |got| count(got, b": keep-alive") >= 3).await;
        assert!(
            count(&waited, b": keep-alive") >= 3,
            "{:?}",
            String::from_utf8_lossy(&waited)
        );
        assert!(!contains(&waited, b"hello"));
        drop(s);
        assert!(matches!(server.next_seen().await, Seen::Cancelled));
    }
    let release = server.arm_release();
    let mut s = connect(server.addr).await;
    write(&mut s, &ping()).await;
    assert!(matches!(server.next_seen().await, Seen::Holding));
    let first = read_until(&mut s, |got| contains(got, b": keep-alive")).await;
    assert!(contains(&first, b": keep-alive"));
    let _ = release.send(());
    let mut rest = first;
    rest.extend(read_to_eof(&mut s).await);
    let text = String::from_utf8_lossy(&rest);
    assert!(text.contains("Content-Type: text/event-stream\r\nCache-Control: no-cache\r\n\r\n"));
    assert!(!text.contains("Content-Length"));
    assert!(
        text.ends_with("data: hello\n\ndata: [DONE]\n\n"),
        "{text:?}"
    );
}
