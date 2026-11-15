//! CNF-03: the raw HTTP client and the observation recorder, tested against a server
//! each test starts itself on a loopback socket (`std::net`, port 0).
//!
//! The server writes a scripted answer with a chosen framing: Content-Length, chunked
//! (with several chunk splits, some inside a UTF-8 sequence or a CRLF), or close-delimited.
//! The same logical answer must give the same logical observation under all three. The
//! disconnect tests have the server wait for the client to go away, so a client that read
//! one event too many (or waited for one) fails by deadlock rather than by timing. No test
//! sleeps; the timeouts below only bound a failing test.
//!
//! No donor test method is re-expressed here: CNF-03 owns none (its parity tests are
//! these self-tests). The answers mimic what project-maya writes (serve/server.py
//! 5456-5463, 5618-5634, 5765-5774 and 6600-6640 at 7e68a30f).

use std::io::{ErrorKind, Read, Write};
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::path::PathBuf;
use std::thread::{self, JoinHandle};
use std::time::Duration;

use console_conformance::client::{
    Client, ClientConfig, Disconnect, DisconnectMode, RawRequest, RequestBuilder, Trigger,
};
use console_conformance::observe::{Content, End, Exchange, Framing, Observation};
use console_conformance::scenario::{HttpVersion, Scenario};
use serde_json::{json, Value};

const BOUND: Duration = Duration::from_secs(10);

/// Starts a server for one connection. `handle` gets the connection and the request
/// bytes it read (head, and a Content-Length body).
fn serve_once<R, F>(handle: F) -> (SocketAddr, JoinHandle<R>)
where
    R: Send + 'static,
    F: FnOnce(TcpStream, Vec<u8>) -> R + Send + 'static,
{
    let listener = TcpListener::bind("127.0.0.1:0").unwrap_or_else(|e| panic!("bind: {e}"));
    let addr = listener
        .local_addr()
        .unwrap_or_else(|e| panic!("local_addr: {e}"));
    let join = thread::spawn(move || {
        let (mut conn, _) = listener.accept().unwrap_or_else(|e| panic!("accept: {e}"));
        let _ = conn.set_read_timeout(Some(BOUND));
        let _ = conn.set_nodelay(true);
        let request = read_request(&mut conn);
        handle(conn, request)
    });
    (addr, join)
}

/// Reads a request head and, when it names one, a Content-Length body.
fn read_request(conn: &mut TcpStream) -> Vec<u8> {
    let mut got = Vec::new();
    let mut buf = [0u8; 4096];
    loop {
        if let Some(end) = find(&got, b"\r\n\r\n") {
            let head = String::from_utf8_lossy(&got[..end]).to_ascii_lowercase();
            let length = head
                .lines()
                .find_map(|l| l.strip_prefix("content-length:"))
                .and_then(|v| v.trim().parse::<usize>().ok())
                .unwrap_or(0);
            if got.len() >= end + 4 + length {
                return got;
            }
        }
        match conn.read(&mut buf) {
            Ok(0) | Err(_) => return got,
            Ok(n) => got.extend_from_slice(&buf[..n]),
        }
    }
}

fn find(hay: &[u8], needle: &[u8]) -> Option<usize> {
    hay.windows(needle.len()).position(|w| w == needle)
}

/// Waits until the client closes or resets the connection. True when it did within the
/// bound.
fn wait_for_close(conn: &mut TcpStream) -> bool {
    let _ = conn.set_read_timeout(Some(BOUND));
    let mut buf = [0u8; 1024];
    loop {
        match conn.read(&mut buf) {
            Ok(0) => return true,
            Ok(_) => continue,
            Err(e) if e.kind() == ErrorKind::Interrupted => continue,
            Err(e) if matches!(e.kind(), ErrorKind::WouldBlock | ErrorKind::TimedOut) => {
                return false
            }
            Err(_) => return true,
        }
    }
}

fn write(conn: &mut TcpStream, bytes: &[u8]) {
    let _ = conn.write_all(bytes);
    let _ = conn.flush();
}

fn client(addr: SocketAddr) -> Client {
    Client::with_config(
        addr,
        ClientConfig {
            read_timeout: BOUND,
            deadline: Duration::from_secs(30),
            close_wait: BOUND,
            ..ClientConfig::default()
        },
    )
}

fn get(c: &Client, target: &str) -> RawRequest {
    c.request("GET", target)
        .build()
        .unwrap_or_else(|e| panic!("build: {e}"))
}

/// A response as the application means it, before framing.
#[derive(Clone)]
struct Logical {
    status_line: &'static str,
    headers: Vec<(&'static str, &'static str)>,
    body: Vec<u8>,
}

#[derive(Clone, Copy, Debug)]
enum Frame {
    Length,
    /// Chunks of this many bytes.
    Chunked(usize),
    Close,
}

/// Writes `l` with framing `f`, in pieces of `piece` bytes, then closes.
fn emit(conn: &mut TcpStream, l: &Logical, f: Frame, piece: usize) {
    let mut head = format!("{}\r\n", l.status_line);
    for (n, v) in &l.headers {
        head.push_str(&format!("{n}: {v}\r\n"));
    }
    match f {
        Frame::Length => head.push_str(&format!("Content-Length: {}\r\n", l.body.len())),
        Frame::Chunked(_) => head.push_str("Transfer-Encoding: chunked\r\n"),
        Frame::Close => {}
    }
    head.push_str("\r\n");
    let mut wire = head.into_bytes();
    match f {
        Frame::Chunked(size) => {
            for c in l.body.chunks(size.max(1)) {
                wire.extend_from_slice(format!("{:x}\r\n", c.len()).as_bytes());
                wire.extend_from_slice(c);
                wire.extend_from_slice(b"\r\n");
            }
            wire.extend_from_slice(b"0\r\n\r\n");
        }
        Frame::Length | Frame::Close => wire.extend_from_slice(&l.body),
    }
    for p in wire.chunks(piece.max(1)) {
        write(conn, p);
    }
}

fn observe(l: &Logical, f: Frame, piece: usize) -> Exchange {
    let answer = l.clone();
    let (addr, join) = serve_once(move |mut conn, _| emit(&mut conn, &answer, f, piece));
    let c = client(addr);
    let ex = c
        .exchange(&get(&c, "/stream"), None)
        .unwrap_or_else(|e| panic!("exchange: {e}"));
    let _ = join.join();
    ex
}

/// The request line and headers differ only by port between runs; replace the request
/// part so logical observations of different servers can be compared.
fn logical(ex: &Exchange) -> Value {
    let mut v = ex.logical_json();
    if let Some(m) = v.as_object_mut() {
        m.insert("request".into(), json!("<request>"));
        m.insert("request_sent".into(), json!("<request_sent>"));
    }
    v
}

fn donor_sse() -> Vec<u8> {
    let mut b = Vec::new();
    b.extend_from_slice(b": keep-alive\n\n");
    b.extend_from_slice(
        "data: {\"id\": \"chatcmpl-1\", \"choices\": [{\"delta\": {\"content\": \"h\u{e9}llo \u{1f600}\"}}]}\n\n"
            .as_bytes(),
    );
    b.extend_from_slice(b"event: response.output_text.delta\ndata: {\"delta\": \"x\"}\n\n");
    b.extend_from_slice(b"data: [DONE]\n\n");
    b
}

fn logical_answers() -> Vec<(&'static str, Logical)> {
    vec![
        (
            "json",
            Logical {
                status_line: "HTTP/1.0 200 OK",
                headers: vec![("Server", "test"), ("Content-Type", "application/json")],
                body: "{\"object\": \"chat.completion\", \"text\": \"caf\u{e9} \u{1f600}\"}"
                    .as_bytes()
                    .to_vec(),
            },
        ),
        (
            "sse-donor",
            Logical {
                status_line: "HTTP/1.0 200 OK",
                headers: vec![
                    ("Server", "test"),
                    ("Content-Type", "text/event-stream"),
                    ("Cache-Control", "no-cache"),
                ],
                body: donor_sse(),
            },
        ),
        (
            "sse-edges",
            Logical {
                status_line: "HTTP/1.0 200 OK",
                headers: vec![("Content-Type", "text/event-stream; charset=utf-8")],
                body: b"event: a\r\ndata: one\r\ndata: two\r\n\r\ndata:x\rid: 3\r\r: c\ndata: last"
                    .to_vec(),
            },
        ),
        (
            "ndjson",
            Logical {
                status_line: "HTTP/1.0 200 OK",
                headers: vec![
                    ("Content-Type", "application/x-ndjson"),
                    ("Cache-Control", "no-cache"),
                ],
                body: "{\"message\": {\"content\": \"\u{e9}\"}, \"done\": false}\n{\"done\": true}\n{\"tail\""
                    .as_bytes()
                    .to_vec(),
            },
        ),
        (
            "opaque",
            Logical {
                status_line: "HTTP/1.0 404 Not Found",
                headers: vec![("Content-Type", "application/octet-stream")],
                body: vec![0, 159, 146, 150, 255, 13, 10, 13, 10],
            },
        ),
        (
            "empty",
            Logical {
                status_line: "HTTP/1.0 200 OK",
                headers: vec![("Content-Type", "application/json")],
                body: Vec::new(),
            },
        ),
    ]
}

#[test]
fn the_three_framings_give_identical_logical_observations() {
    for (name, answer) in logical_answers() {
        let reference = observe(&answer, Frame::Length, usize::MAX);
        assert_eq!(reference.end, End::Complete, "{name}");
        assert_eq!(reference.server_closed, Some(true), "{name}");
        assert_eq!(reference.body, answer.body, "{name}");
        let want = logical(&reference);
        let variants = [
            (Frame::Length, 1),
            (Frame::Length, 5),
            (Frame::Chunked(1), usize::MAX),
            (Frame::Chunked(3), 2),
            (Frame::Chunked(7), 7),
            (Frame::Chunked(4096), 1),
            (Frame::Close, usize::MAX),
            (Frame::Close, 3),
        ];
        for (frame, piece) in variants {
            let ex = observe(&answer, frame, piece);
            assert_eq!(ex.end, End::Complete, "{name} {frame:?}");
            assert_eq!(ex.server_closed, Some(true), "{name} {frame:?}");
            assert_eq!(logical(&ex), want, "{name} {frame:?} piece {piece}");
            assert_eq!(ex.content, reference.content, "{name} {frame:?}");
            let framing_ok = match (frame, &ex.framing) {
                (Frame::Length, Some(Framing::ContentLength(n))) => *n == answer.body.len() as u64,
                (Frame::Chunked(size), Some(Framing::Chunked { chunks, .. })) => {
                    chunks.len() == answer.body.len().div_ceil(size) + 1
                }
                (Frame::Close, Some(Framing::CloseDelimited)) => true,
                _ => false,
            };
            assert!(framing_ok, "{name} {frame:?}: {:?}", ex.framing);
            // The full records do differ by framing, so the framing is observable.
            if !matches!(frame, Frame::Length) {
                assert_ne!(ex.to_json()["framing"], reference.to_json()["framing"]);
            }
        }
    }
}

#[test]
fn parsed_content_matches_what_was_sent() {
    let answers = logical_answers();
    let by_name = |n: &str| {
        answers
            .iter()
            .find(|(k, _)| *k == n)
            .map(|(_, l)| l.clone())
            .unwrap_or_else(|| panic!("no answer {n}"))
    };
    let ex = observe(&by_name("sse-donor"), Frame::Chunked(3), 1);
    let events = ex.events();
    assert_eq!(events.len(), 3);
    assert_eq!(
        events[0].data_json(),
        Some(
            json!({"id": "chatcmpl-1", "choices": [{"delta": {"content": "h\u{e9}llo \u{1f600}"}}]})
        )
    );
    assert_eq!(
        events[1].event.as_deref(),
        Some("response.output_text.delta")
    );
    assert_eq!(events[2].data.as_deref(), Some("[DONE]"));
    let Content::Sse(stream) = &ex.content else {
        panic!("content {:?}", ex.content);
    };
    assert_eq!(stream.comments.len(), 1);
    assert_eq!(stream.comments[0].before_event, 0);
    assert_eq!(stream.comments[0].text, " keep-alive");
    assert_eq!(stream.unterminated, None);

    let ex = observe(&by_name("sse-edges"), Frame::Close, 1);
    let Content::Sse(stream) = &ex.content else {
        panic!("content {:?}", ex.content);
    };
    assert_eq!(stream.events.len(), 2);
    assert_eq!(stream.events[0].data.as_deref(), Some("one\ntwo"));
    assert_eq!(stream.events[1].data.as_deref(), Some("x"));
    assert_eq!(stream.events[1].id.as_deref(), Some("3"));
    assert_eq!(stream.comments[0].before_event, 2);
    // Everything after the last blank line, the comment included.
    assert_eq!(
        stream.unterminated.as_deref(),
        Some(&b": c\ndata: last"[..])
    );

    let ex = observe(&by_name("ndjson"), Frame::Chunked(2), 3);
    assert_eq!(ex.lines().len(), 2);
    assert_eq!(ex.lines()[1].json, Some(json!({"done": true})));
    let Content::Ndjson(stream) = &ex.content else {
        panic!("content {:?}", ex.content);
    };
    assert_eq!(stream.unterminated.as_deref(), Some(&b"{\"tail\""[..]));

    let ex = observe(&by_name("json"), Frame::Close, 2);
    assert_eq!(
        ex.json(),
        Some(&json!({"object": "chat.completion", "text": "caf\u{e9} \u{1f600}"}))
    );
    let ex = observe(&by_name("opaque"), Frame::Length, 4);
    assert_eq!(ex.content, Content::Opaque);
    assert_eq!(ex.status(), Some(404));
    assert!(ex.to_json()["body"]["base64"].is_string());
}

#[test]
fn headers_keep_names_order_and_duplicates() {
    let answer = Logical {
        status_line: "HTTP/1.0 200 OK",
        headers: vec![
            ("Server", "test"),
            ("Date", "now"),
            ("content-type", "application/json"),
            ("Set-Cookie", "a=1"),
            ("set-cookie", "b=2"),
        ],
        body: b"{}".to_vec(),
    };
    let ex = observe(&answer, Frame::Length, usize::MAX);
    let head = ex.head.clone().unwrap_or_else(|| panic!("no head"));
    let got: Vec<(String, String)> = head
        .headers
        .iter()
        .map(|h| (h.name.clone(), h.value.clone()))
        .collect();
    let want: Vec<(String, String)> = [
        ("Server", "test"),
        ("Date", "now"),
        ("content-type", "application/json"),
        ("Set-Cookie", "a=1"),
        ("set-cookie", "b=2"),
        ("Content-Length", "2"),
    ]
    .iter()
    .map(|(n, v)| (n.to_string(), v.to_string()))
    .collect();
    assert_eq!(got, want);
    assert_eq!(head.version, "HTTP/1.0");
    assert_eq!(head.reason, "OK");
    let logical_headers = &ex.logical_json()["head"]["headers"];
    assert_eq!(logical_headers.as_array().map(Vec::len), Some(5));
}

#[test]
fn http_1_0_requests_are_sent_exactly_and_answered() {
    let (addr, join) = serve_once(|mut conn, request| {
        write(
            &mut conn,
            b"HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n\r\n{\"ok\": true}",
        );
        request
    });
    let c = client(addr);
    let req = c
        .request("GET", "/health")
        .version(HttpVersion::V1_0)
        .build()
        .unwrap_or_else(|e| panic!("build: {e}"));
    let ex = c
        .exchange(&req, None)
        .unwrap_or_else(|e| panic!("exchange: {e}"));
    let received = join.join().unwrap_or_default();
    let want = format!("GET /health HTTP/1.0\r\nHost: {addr}\r\n\r\n");
    assert_eq!(received, want.as_bytes());
    assert_eq!(ex.request, want.as_bytes());
    assert_eq!(ex.end, End::Complete);
    assert_eq!(ex.framing, Some(Framing::CloseDelimited));
    assert_eq!(ex.json(), Some(&json!({"ok": true})));
    assert_eq!(
        ex.head.as_ref().map(|h| h.version.as_str()),
        Some("HTTP/1.0")
    );
}

#[test]
fn a_post_body_is_written_as_python_json_dumps() {
    let (addr, join) = serve_once(|mut conn, request| {
        write(&mut conn, b"HTTP/1.0 200 OK\r\n\r\n");
        request
    });
    let c = client(addr);
    let req = c
        .request("POST", "/v1/chat/completions")
        .header("Content-Type", "application/json")
        .json(&json!({"model": "m", "max_tokens": 8, "temperature": 1e-5, "messages": [{"role": "user", "content": "h\u{e9}"}]}))
        .and_then(RequestBuilder::build)
        .unwrap_or_else(|e| panic!("build: {e}"));
    let _ = c.exchange(&req, None);
    let received = join.join().unwrap_or_default();
    let body = "{\"model\": \"m\", \"max_tokens\": 8, \"temperature\": 1e-05, \"messages\": [{\"role\": \"user\", \"content\": \"h\\u00e9\"}]}";
    let want = format!(
        "POST /v1/chat/completions HTTP/1.1\r\nHost: {addr}\r\nContent-Type: application/json\r\nContent-Length: {}\r\n\r\n{body}",
        body.len()
    );
    assert_eq!(String::from_utf8_lossy(&received), want);
}

#[test]
fn a_raw_request_is_sent_byte_for_byte() {
    let raw: &[u8] =
        b"POST /v1/chat/completions HTTP/1.1\r\nContent-Length: abc\r\nX-Odd:\x01\xff\r\n\r\n";
    let (addr, join) = serve_once(|mut conn, request| {
        write(&mut conn, b"HTTP/1.0 400 Bad Request\r\nContent-Type: application/json\r\nContent-Length: 2\r\n\r\n{}");
        request
    });
    let c = client(addr);
    let req = RawRequest::raw(raw).unwrap_or_else(|e| panic!("raw: {e}"));
    let ex = c
        .exchange(&req, None)
        .unwrap_or_else(|e| panic!("exchange: {e}"));
    assert_eq!(join.join().unwrap_or_default(), raw);
    assert_eq!(ex.status(), Some(400));
    assert_eq!(ex.request, raw);
}

/// Writes `count` events (each in two writes, the split inside the event), then waits
/// for the client to go away. Returns whether it did before the server had to write
/// anything more.
fn paced_events(conn: &mut TcpStream, count: usize, ndjson: bool) -> bool {
    let ctype = if ndjson {
        "application/x-ndjson"
    } else {
        "text/event-stream"
    };
    write(
        conn,
        format!("HTTP/1.0 200 OK\r\nContent-Type: {ctype}\r\nCache-Control: no-cache\r\n\r\n")
            .as_bytes(),
    );
    for k in 0..count {
        let event = if ndjson {
            format!("{{\"k\": {k}}}\n")
        } else {
            format!("event: e{k}\ndata: {{\"k\": {k}}}\n\n")
        };
        let (a, b) = event.as_bytes().split_at(event.len() - 1);
        write(conn, a);
        write(conn, b);
    }
    wait_for_close(conn)
}

#[test]
fn disconnect_after_events_is_exact_to_the_event() {
    for ndjson in [false, true] {
        for n in [1u64, 3] {
            let (addr, join) =
                serve_once(move |mut conn, _| paced_events(&mut conn, n as usize, ndjson));
            let c = client(addr);
            let ex = c
                .exchange(&get(&c, "/s"), Some(Disconnect::after_events(n)))
                .unwrap_or_else(|e| panic!("exchange: {e}"));
            let saw_close = join.join().unwrap_or(false);
            assert!(
                saw_close,
                "the server never saw the client go (ndjson {ndjson}, n {n})"
            );
            assert_eq!(ex.end, End::Disconnected);
            let count = if ndjson {
                ex.lines().len()
            } else {
                ex.events().len()
            };
            assert_eq!(count as u64, n);
            let record = ex.disconnect.clone().unwrap_or_else(|| panic!("no record"));
            assert!(record.fired);
            assert_eq!(record.events, n);
            assert_eq!(record.body_bytes, ex.body.len() as u64);
            assert_eq!(record.wire_bytes, ex.wire.len() as u64);
        }
    }
}

#[test]
fn an_event_disconnect_ignores_bytes_already_received_past_it() {
    for frame in [Frame::Close, Frame::Length, Frame::Chunked(5)] {
        let mut body = Vec::new();
        for k in 0..10 {
            body.extend_from_slice(format!("data: {{\"k\": {k}}}\n\n").as_bytes());
        }
        let answer = Logical {
            status_line: "HTTP/1.0 200 OK",
            headers: vec![("Content-Type", "text/event-stream")],
            body,
        };
        let sent = answer.clone();
        let (addr, join) = serve_once(move |mut conn, _| {
            // The whole stream in one write: the client receives far past the trigger.
            emit_open(&mut conn, &sent, frame);
            wait_for_close(&mut conn)
        });
        let c = client(addr);
        let ex = c
            .exchange(&get(&c, "/s"), Some(Disconnect::after_events(3)))
            .unwrap_or_else(|e| panic!("exchange: {e}"));
        assert!(join.join().unwrap_or(false), "{frame:?}");
        assert_eq!(ex.end, End::Disconnected, "{frame:?}");
        assert_eq!(ex.events().len(), 3, "{frame:?}");
        assert_eq!(
            ex.body, b"data: {\"k\": 0}\n\ndata: {\"k\": 1}\n\ndata: {\"k\": 2}\n\n",
            "{frame:?}"
        );
        let Content::Sse(s) = &ex.content else {
            panic!("content {:?}", ex.content);
        };
        assert_eq!(s.unterminated, None);
    }
}

/// As [`emit`] in one write, without closing afterwards.
fn emit_open(conn: &mut TcpStream, l: &Logical, f: Frame) {
    let mut head = format!("{}\r\n", l.status_line);
    for (n, v) in &l.headers {
        head.push_str(&format!("{n}: {v}\r\n"));
    }
    let mut body = Vec::new();
    match f {
        Frame::Length => {
            head.push_str(&format!("Content-Length: {}\r\n", l.body.len()));
            body.extend_from_slice(&l.body);
        }
        Frame::Chunked(size) => {
            head.push_str("Transfer-Encoding: chunked\r\n");
            for c in l.body.chunks(size.max(1)) {
                body.extend_from_slice(format!("{:x}\r\n", c.len()).as_bytes());
                body.extend_from_slice(c);
                body.extend_from_slice(b"\r\n");
            }
            body.extend_from_slice(b"0\r\n\r\n");
        }
        Frame::Close => body.extend_from_slice(&l.body),
    }
    head.push_str("\r\n");
    let mut wire = head.into_bytes();
    wire.extend_from_slice(&body);
    write(conn, &wire);
}

#[test]
fn disconnect_after_bytes_receives_exactly_that_many() {
    let answer = Logical {
        status_line: "HTTP/1.0 200 OK",
        headers: vec![("Content-Type", "text/event-stream")],
        body: b"data: 1\n\ndata: 2\n\ndata: 3\n\n".to_vec(),
    };
    for n in [1u64, 10, 40, 47, 60] {
        let sent = answer.clone();
        let (addr, join) = serve_once(move |mut conn, _| {
            emit_open(&mut conn, &sent, Frame::Close);
            wait_for_close(&mut conn)
        });
        let c = client(addr);
        let ex = c
            .exchange(&get(&c, "/s"), Some(Disconnect::after_bytes(n)))
            .unwrap_or_else(|e| panic!("exchange: {e}"));
        assert!(join.join().unwrap_or(false), "n {n}");
        assert_eq!(ex.wire.len() as u64, n);
        assert_eq!(ex.end, End::Disconnected);
        let record = ex.disconnect.clone().unwrap_or_else(|| panic!("no record"));
        assert_eq!(record.wire_bytes, n);
        assert!(record.fired);
    }
}

#[test]
fn a_half_close_lets_the_server_see_end_of_file_and_the_rest_is_read() {
    let (addr, join) = serve_once(|mut conn, _| {
        write(
            &mut conn,
            b"HTTP/1.0 200 OK\r\nContent-Type: text/event-stream\r\n\r\ndata: 1\n\ndata: 2\n\n",
        );
        // The client's half-close reads as end of file while the connection stays open.
        let mut buf = [0u8; 16];
        let eof = matches!(conn.read(&mut buf), Ok(0));
        write(&mut conn, b"data: {\"saw_eof\": true}\n\n");
        eof
    });
    let c = client(addr);
    let ex = c
        .exchange(
            &get(&c, "/s"),
            Some(Disconnect::after_events(2).half_close()),
        )
        .unwrap_or_else(|e| panic!("exchange: {e}"));
    assert!(join.join().unwrap_or(false));
    assert_eq!(ex.end, End::Complete);
    assert_eq!(ex.events().len(), 3);
    assert_eq!(ex.events()[2].data_json(), Some(json!({"saw_eof": true})));
    let record = ex.disconnect.clone().unwrap_or_else(|| panic!("no record"));
    assert_eq!(record.asked.mode, DisconnectMode::HalfClose);
    assert_eq!(record.events, 2);
    assert!(record.fired);
}

#[test]
fn disconnect_right_after_the_request() {
    let (addr, join) = serve_once(|mut conn, request| (wait_for_close(&mut conn), request));
    let c = client(addr);
    let ex = c
        .exchange(&get(&c, "/s"), Some(Disconnect::after_request()))
        .unwrap_or_else(|e| panic!("exchange: {e}"));
    let (closed, request) = join.join().unwrap_or((false, Vec::new()));
    assert!(closed);
    assert_eq!(request, ex.request);
    assert_eq!(ex.end, End::Disconnected);
    assert_eq!(ex.head, None);
    assert!(ex.wire.is_empty());

    // Half-closed: the server reads end of file, then answers.
    let (addr, join) = serve_once(|mut conn, _| {
        let mut buf = [0u8; 16];
        let eof = matches!(conn.read(&mut buf), Ok(0));
        write(&mut conn, b"HTTP/1.0 499 Gone\r\nContent-Length: 0\r\n\r\n");
        eof
    });
    let c = client(addr);
    let ex = c
        .exchange(
            &get(&c, "/s"),
            Some(Disconnect::after_request().half_close()),
        )
        .unwrap_or_else(|e| panic!("exchange: {e}"));
    assert!(join.join().unwrap_or(false));
    assert_eq!(ex.status(), Some(499));
    assert_eq!(ex.end, End::Complete);
    assert_eq!(
        ex.disconnect.map(|d| (d.asked.trigger, d.fired)),
        Some((Trigger::AfterRequest, true))
    );
}

#[test]
fn a_trigger_that_never_fires_is_recorded_as_such() {
    let answer = Logical {
        status_line: "HTTP/1.0 200 OK",
        headers: vec![("Content-Type", "text/event-stream")],
        body: b"data: 1\n\n".to_vec(),
    };
    let (addr, join) = serve_once(move |mut conn, _| emit(&mut conn, &answer, Frame::Close, 4));
    let c = client(addr);
    let ex = c
        .exchange(&get(&c, "/s"), Some(Disconnect::after_events(5)))
        .unwrap_or_else(|e| panic!("exchange: {e}"));
    let _ = join.join();
    assert_eq!(ex.end, End::Complete);
    let record = ex.disconnect.unwrap_or_else(|| panic!("no record"));
    assert!(!record.fired);
    assert_eq!(record.events, 1);
}

#[test]
fn a_body_cut_short_is_truncated() {
    let (addr, join) = serve_once(|mut conn, _| {
        write(
            &mut conn,
            b"HTTP/1.0 200 OK\r\nContent-Length: 10\r\n\r\nabc",
        );
    });
    let c = client(addr);
    let ex = c
        .exchange(&get(&c, "/"), None)
        .unwrap_or_else(|e| panic!("exchange: {e}"));
    let _ = join.join();
    assert_eq!(ex.end, End::Truncated);
    assert_eq!(ex.body, b"abc");

    let (addr, join) = serve_once(|mut conn, _| write(&mut conn, b"HTTP/1.0 200 O"));
    let c = client(addr);
    let ex = c
        .exchange(&get(&c, "/"), None)
        .unwrap_or_else(|e| panic!("exchange: {e}"));
    let _ = join.join();
    assert_eq!(ex.end, End::Truncated);
    assert_eq!(ex.head, None);
    assert_eq!(ex.wire, b"HTTP/1.0 200 O");
}

#[test]
fn a_silent_server_times_out_and_an_open_connection_is_reported() {
    let (addr, join) = serve_once(|mut conn, _| {
        write(
            &mut conn,
            b"HTTP/1.0 200 OK\r\nContent-Length: 10\r\n\r\nabc",
        );
        wait_for_close(&mut conn)
    });
    let c = Client::with_config(
        addr,
        ClientConfig {
            read_timeout: Duration::from_millis(200),
            ..ClientConfig::default()
        },
    );
    let ex = c
        .exchange(&get(&c, "/"), None)
        .unwrap_or_else(|e| panic!("exchange: {e}"));
    assert_eq!(ex.end, End::Timeout);
    assert!(join.join().unwrap_or(false));

    // A complete Content-Length body on a connection the server keeps open.
    let (addr, join) = serve_once(|mut conn, _| {
        write(&mut conn, b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok");
        wait_for_close(&mut conn)
    });
    let c = Client::with_config(
        addr,
        ClientConfig {
            close_wait: Duration::from_millis(200),
            ..ClientConfig::default()
        },
    );
    let ex = c
        .exchange(&get(&c, "/"), None)
        .unwrap_or_else(|e| panic!("exchange: {e}"));
    assert!(join.join().unwrap_or(false));
    assert_eq!(ex.end, End::Complete);
    assert_eq!(ex.server_closed, Some(false));
}

#[test]
fn an_interim_head_is_recorded_before_the_answer() {
    let (addr, join) = serve_once(|mut conn, _| {
        write(&mut conn, b"HTTP/1.1 100 Continue\r\n\r\n");
        write(&mut conn, b"HTTP/1.0 200 OK\r\nContent-Length: 2\r\n\r\nok");
    });
    let c = client(addr);
    let ex = c
        .exchange(&get(&c, "/"), None)
        .unwrap_or_else(|e| panic!("exchange: {e}"));
    let _ = join.join();
    assert_eq!(ex.interim.len(), 1);
    assert_eq!(ex.interim[0].code, 100);
    assert_eq!(ex.status(), Some(200));
    assert_eq!(ex.body, b"ok");
}

fn scenario_path(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests/data/scenarios")
        .join(name)
}

#[test]
fn a_scenario_step_drives_the_request_and_its_disconnect() {
    let path = scenario_path("responses-stream-disconnect.json");
    let scenario = Scenario::from_path(&path).unwrap_or_else(|e| panic!("scenario: {e}"));
    let base = path.parent().map(PathBuf::from);

    // Step 0: a stored Responses stream dropped at its fifth event.
    let (addr, join) = serve_once(|mut conn, request| {
        let mut body = String::new();
        for name in [
            "response.created",
            "response.in_progress",
            "response.output_item.added",
            "response.content_part.added",
            "response.output_text.delta",
            "response.output_text.delta",
            "response.output_text.delta",
        ] {
            body.push_str(&format!(
                "event: {name}\ndata: {{\"type\": \"{name}\"}}\n\n"
            ));
        }
        write(
            &mut conn,
            format!("HTTP/1.0 200 OK\r\nContent-Type: text/event-stream\r\nCache-Control: no-cache\r\n\r\n{body}")
                .as_bytes(),
        );
        (wait_for_close(&mut conn), request)
    });
    let c = client(addr);
    let ex = c
        .run_step(&scenario.steps[0], base.as_deref())
        .unwrap_or_else(|e| panic!("step: {e}"))
        .unwrap_or_else(|| panic!("no request in step 0"));
    let (closed, request) = join.join().unwrap_or((false, Vec::new()));
    assert!(closed);
    let body = "{\"input\": \"hi\", \"stream\": true, \"store\": true, \"reasoning\": {\"effort\": \"none\"}}";
    let want = format!(
        "POST /v1/responses HTTP/1.1\r\nHost: {addr}\r\nContent-Type: application/json\r\nContent-Length: {}\r\n\r\n{body}",
        body.len()
    );
    assert_eq!(String::from_utf8_lossy(&request), want);
    assert_eq!(ex.end, End::Disconnected);
    assert_eq!(ex.events().len(), 5);
    assert_eq!(
        ex.events()[4].event.as_deref(),
        Some("response.output_text.delta")
    );

    // Step 1: the next request is read whole.
    let (addr, join) = serve_once(|mut conn, _| {
        write(
            &mut conn,
            b"HTTP/1.0 200 OK\r\nContent-Type: application/json\r\nContent-Length: 23\r\n\r\n{\"status\": \"completed\"}",
        );
    });
    let c = client(addr);
    let ex = c
        .run_step(&scenario.steps[1], base.as_deref())
        .unwrap_or_else(|e| panic!("step: {e}"))
        .unwrap_or_else(|| panic!("no request in step 1"));
    let _ = join.join();
    assert_eq!(ex.disconnect, None);
    assert_eq!(ex.json(), Some(&json!({"status": "completed"})));
}

#[test]
fn the_observation_document_has_five_parts_in_order() {
    let answer = Logical {
        status_line: "HTTP/1.0 200 OK",
        headers: vec![("Content-Type", "application/x-ndjson")],
        body: b"{\"a\": 1}\n".to_vec(),
    };
    let chunked = observe(&answer, Frame::Chunked(2), usize::MAX);
    let closed = observe(&answer, Frame::Close, usize::MAX);
    let doc = |ex: Exchange| Observation {
        http: vec![ex],
        engine_tape: Some(json!([{"prompt": [1, 2], "max_new": 8}])),
        ..Observation::default()
    };
    let a = doc(chunked);
    let b = doc(closed);
    let full = a.to_json();
    let keys: Vec<&String> = full
        .as_object()
        .map(|m| m.keys().collect())
        .unwrap_or_default();
    assert_eq!(keys, ["http", "engine_tape", "files", "log", "exit"]);
    let ex_keys: Vec<&String> = full["http"][0]
        .as_object()
        .map(|m| m.keys().collect())
        .unwrap_or_default();
    assert_eq!(
        ex_keys,
        [
            "request",
            "request_sent",
            "write_error",
            "interim",
            "head",
            "framing",
            "body",
            "content",
            "end",
            "server_closed",
            "disconnect",
            "wire"
        ]
    );
    assert_eq!(
        full["http"][0]["content"]["lines"][0]["json"],
        json!({"a": 1})
    );
    // The two documents differ in full (framing) and agree logically, apart from the
    // request, which names each server's port.
    assert_ne!(a.to_json(), b.to_json());
    let strip = |mut v: Value| {
        v["http"][0]["request"] = json!("<request>");
        v["http"][0]["request_sent"] = json!("<request_sent>");
        v
    };
    assert_eq!(strip(a.logical_json()), strip(b.logical_json()));
}

#[test]
fn an_answer_without_a_head_is_recorded_whole_whatever_the_pieces() {
    // What Python's http.server sends to an HTTP/0.9 request line: the body alone, then
    // the close. Every byte must be recorded whatever the server's write sizes.
    let answer: &[u8] = b"{\"ok\": true}";
    let mut seen = Vec::new();
    for piece in [1usize, 3, usize::MAX] {
        let (addr, join) = serve_once(move |mut conn, _| {
            for p in answer.chunks(piece) {
                write(&mut conn, p);
            }
        });
        let c = client(addr);
        let req =
            RawRequest::raw(&b"GET /health\r\n\r\n"[..]).unwrap_or_else(|e| panic!("raw: {e}"));
        let ex = c
            .exchange(&req, None)
            .unwrap_or_else(|e| panic!("exchange: {e}"));
        let _ = join.join();
        assert_eq!(ex.wire, answer, "piece {piece}");
        assert_eq!(ex.body, answer, "piece {piece}");
        assert_eq!(ex.head, None);
        assert_eq!(ex.framing, Some(Framing::Headless));
        assert!(matches!(ex.end, End::Malformed(_)), "end {:?}", ex.end);
        assert_eq!(ex.server_closed, Some(true));
        assert_eq!(ex.request_sent, ex.request.len() as u64);
        seen.push(ex.to_json());
    }
    assert!(seen.iter().all(|v| v == &seen[0]));
}

#[test]
fn a_malformed_head_is_read_to_the_end_of_the_connection() {
    let answer: &[u8] = b"HTTP/1.0 200 OK\r\nX-Bad: a\x01b\r\n\r\nthe rest of the answer";
    let mut seen = Vec::new();
    for piece in [1usize, 5, usize::MAX] {
        let (addr, join) = serve_once(move |mut conn, _| {
            for p in answer.chunks(piece) {
                write(&mut conn, p);
            }
        });
        let c = client(addr);
        let ex = c
            .exchange(&get(&c, "/"), None)
            .unwrap_or_else(|e| panic!("exchange: {e}"));
        let _ = join.join();
        assert_eq!(ex.wire, answer, "piece {piece}");
        assert!(ex.body.is_empty());
        assert!(matches!(ex.end, End::Malformed(_)), "end {:?}", ex.end);
        assert_eq!(ex.server_closed, Some(true));
        seen.push(logical(&ex));
    }
    assert!(seen.iter().all(|v| v == &seen[0]));
}
