//! Tests of the test kit's raw client and SSE reader over real loopback sockets (work
//! package API-19), against the kit's transport probe: the donor's `read_for` with and
//! without a marker, frames read one at a time as they are written, a client that goes,
//! and the parse of an answer that has no head.
//!
//! These are tests of the kit itself, not re-expressions of donor methods.

use std::time::Duration;

use console_testkit::raw::{self, connect, json_post, read_for, write, RawRequest};
use console_testkit::server::probe::{ProbeServer, Seen};
use console_testkit::sse::{SseEnd, SseReader};

const MSG: &[u8] = br#"{"model": "m"}"#;

#[tokio::test]
async fn read_for_returns_what_came_when_the_period_ends() {
    let mut server = ProbeServer::start().await;
    let release = server.arm_release();
    let mut s = connect(server.addr).await;
    write(&mut s, &json_post("/hold", MSG)).await;
    assert!(matches!(server.next_seen().await, Seen::Holding));
    // Nothing is written while the request is held: the period ends, which is no failure.
    let got = read_for(&mut s, Duration::from_millis(300), None).await;
    assert!(got.is_empty(), "{:?}", String::from_utf8_lossy(&got));
    let _ = release.send(());
    let got = read_for(&mut s, Duration::from_secs(10), Some(b"held")).await;
    assert!(raw::contains(&got, b"{\"held\": true}"), "{got:?}");
    assert!(raw::contains(&got, b"HTTP/1.0 200 OK\r\n"));
}

#[tokio::test]
async fn read_for_stops_at_its_marker() {
    let mut server = ProbeServer::start().await;
    let mut s = connect(server.addr).await;
    write(&mut s, &json_post("/ping", MSG)).await;
    assert!(matches!(server.next_seen().await, Seen::Holding));
    let got = read_for(&mut s, Duration::from_secs(10), Some(b": keep-alive")).await;
    assert_eq!(
        raw::count(&got, b": keep-alive"),
        1,
        "stopped at the first: {:?}",
        String::from_utf8_lossy(&got)
    );
    drop(s);
    assert!(matches!(server.next_seen().await, Seen::Cancelled));
}

#[tokio::test]
async fn frames_arrive_one_at_a_time() {
    let mut server = ProbeServer::start().await;
    let release = server.arm_release();
    let mut reader = SseReader::open(server.addr, &json_post("/ping", MSG)).await;
    assert!(matches!(server.next_seen().await, Seen::Holding));
    assert_eq!(reader.head().status, 200);
    assert_eq!(
        reader.head().header("Content-Type"),
        Some("text/event-stream")
    );
    assert!(reader.head().body.is_empty(), "the frames follow the head");
    for _ in 0..3 {
        let frame = reader.next_frame().await.expect("a keep-alive");
        assert!(frame.is_keep_alive(), "{frame:?}");
        assert_eq!(frame.raw, b": keep-alive\n\n");
    }
    let _ = release.send(());
    let rest = reader.frames_until_done().await;
    let last_two: Vec<&[u8]> = rest
        .iter()
        .rev()
        .take(2)
        .map(|f| f.raw.as_slice())
        .collect();
    assert_eq!(last_two, vec![&b"data: [DONE]\n\n"[..], b"data: hello\n\n"]);
    assert!(rest.iter().take(rest.len() - 2).all(|f| f.is_keep_alive()));
    assert_eq!(
        reader.next_frame().await,
        Err(SseEnd::Closed { rest: Vec::new() })
    );
    assert!(raw::contains(reader.raw(), b"\r\n\r\n: keep-alive\n\n"));
}

#[tokio::test]
async fn a_reader_that_closes_is_a_client_that_goes() {
    let mut server = ProbeServer::start().await;
    let mut reader = SseReader::open(server.addr, &json_post("/ping", MSG)).await;
    assert!(matches!(server.next_seen().await, Seen::Holding));
    let some = reader.frames_for(Duration::from_millis(350)).await;
    assert!(some.iter().all(|f| f.is_keep_alive()));
    reader.close();
    assert!(matches!(server.next_seen().await, Seen::Cancelled));
}

#[tokio::test]
async fn a_short_wait_for_a_frame_times_out() {
    let mut server = ProbeServer::start().await;
    let mut reader = SseReader::open(server.addr, &json_post("/hold-stream", MSG)).await;
    assert!(matches!(server.next_seen().await, Seen::Holding));
    assert_eq!(
        reader.next_frame_within(Duration::from_millis(100)).await,
        Err(SseEnd::TimedOut)
    );
}

#[tokio::test]
async fn an_answer_without_a_head_is_all_body() {
    let server = ProbeServer::start().await;
    // HTTP/0.9: Python answers with the body only.
    let r09 = raw::exchange(server.addr, b"GET /head\r\n").await;
    assert_eq!(r09.status, 0);
    assert_eq!(r09.body, b"ok");
    assert_eq!(r09.raw, b"ok");
    assert!(r09.head.is_empty() && r09.headers.is_empty());
    // The same route over HTTP/1.0, written with the request builder.
    let r = RawRequest::get("/head")
        .version("HTTP/1.0")
        .send(server.addr)
        .await;
    assert_eq!(r.status, 200);
    assert_eq!(r.status_line(), Some("HTTP/1.0 200 OK"));
    assert_eq!(r.body, b"ok");
}

/// A listener that answers its one connection with `bytes`, then resets it (a zero linger
/// time makes the close send RST instead of FIN).
async fn resetting_peer(bytes: &'static [u8]) -> std::net::SocketAddr {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0")
        .await
        .expect("bind");
    let addr = listener.local_addr().expect("addr");
    tokio::spawn(async move {
        use tokio::io::{AsyncReadExt, AsyncWriteExt};
        let Ok((mut s, _)) = listener.accept().await else {
            return;
        };
        let mut buf = [0u8; 64];
        let _ = s.read(&mut buf).await;
        let _ = s.write_all(bytes).await;
        tokio::time::sleep(Duration::from_millis(100)).await;
        let _ = s.set_zero_linger();
        drop(s);
    });
    addr
}

#[tokio::test]
async fn a_reset_fails_the_read_as_it_fails_the_donors_recv() {
    let addr = resetting_peer(b"HTTP/1.0 200 OK\r\n").await;
    let read = tokio::spawn(async move {
        let mut s = connect(addr).await;
        write(&mut s, b"GET / HTTP/1.0\r\n\r\n").await;
        raw::read_to_eof(&mut s).await
    })
    .await;
    let err = read.expect_err("a reset is not an end of file");
    assert!(err.is_panic(), "{err:?}");
}

#[tokio::test]
async fn a_test_that_expects_a_reset_opts_in() {
    let addr = resetting_peer(b"HTTP/1.0 200 OK\r\n").await;
    let mut s = connect(addr).await;
    write(&mut s, b"GET / HTTP/1.0\r\n\r\n").await;
    let got = raw::read_to_eof_allowing_reset(&mut s).await;
    assert!(
        got.is_empty() || got.starts_with(b"HTTP/1.0"),
        "{:?}",
        String::from_utf8_lossy(&got)
    );
}
