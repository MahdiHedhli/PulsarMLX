//! Provenance: translated from project-maya serve/test_server.py::RequestBodies (`raw`), serve/test_server.py::GoneClients (`send`), serve/test_server.py::QueuedKeepAlives (`send_to`, `read_for`) and serve/test_server.py::WebApp (`get`) at 7e68a30f (MIT); license text in console/LICENSES/project-maya-MIT.txt.
//!
//! The raw HTTP client: arbitrary request bytes in, status, headers and body out.
//!
//! The donor's HTTP tests write requests by hand on a plain socket and read until the
//! server closes the connection (its HTTP/1.0 transport closes after every answer), then
//! split the bytes at the first blank line. This client does the same, with no HTTP
//! library in between, so a test sees exactly the bytes the server wrote: the status line,
//! header names, order and values, and the body. [`RawResponse::head`] keeps the whole
//! head with the `Date` value masked, for byte comparisons; [`RawResponse::headers`]
//! keeps the header lines as pairs, values unmasked.
//!
//! Every read has a deadline ([`DEADLINE`] unless the caller gives one) so a server that
//! never answers fails the test instead of hanging it. A connection reset fails the read,
//! as `recv` raising `ConnectionResetError` fails the donor's test; a test that expects a
//! reset says so with [`read_to_eof_allowing_reset`].
//!
//! The donor's `WebApp.get` goes through `urllib`, which follows redirects and adds its
//! own `Accept-Encoding`, `User-Agent` and `Connection` headers. The raw client adds no
//! header and follows nothing: a request is the bytes the test wrote, and a 3xx answer
//! comes back as it is. [`TestServer::get_following`](crate::server::TestServer::get_following)
//! follows a `Location` on the same server for the ports that need urllib's redirects. Only loopback addresses are used by
//! the kit's own tests; nothing here opens a connection the caller did not name.
//!
//! The parser follows the archived PulsarMLX serving crate's `parse_response` helper (tag
//! `archive/2026-09-21/feat/openai-serving`, `crates/serve-synthetic/tests/raw_http.rs`),
//! PulsarMLX's own code, which the API-02 and API-03 tests used before this kit.
//!
//! Behavior reference: project-maya serve/test_server.py:2055-2068, 2380-2387, 2423-2441
//! and 1683-1689 at 7e68a30f.

use std::net::SocketAddr;
use std::time::Duration;

use serde_json::Value;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::TcpStream;
use tokio::time::Instant;

/// A generous bound for one exchange; tests that depend on timing say so themselves.
pub const DEADLINE: Duration = Duration::from_secs(10);

/// The most bytes [`read_to_eof`] and its relatives keep from one connection (64 MiB). A
/// server that sends more fails the read instead of exhausting the test's memory.
pub const MAX_RESPONSE_BYTES: usize = 64 << 20;

/// The size of one socket read.
const READ_CHUNK: usize = 65536;

/// The `Host` value the donor's hand-written requests carry.
pub const DONOR_HOST: &str = "127.0.0.1";

/// The donor's path for its hand-written requests.
pub const CHAT_PATH: &str = "/v1/chat/completions";

/// A response as the raw client read it.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RawResponse {
    /// Every byte read, as read.
    pub raw: Vec<u8>,
    /// The status code from the status line; 0 when the bytes hold no complete head (an
    /// empty answer, or an HTTP/0.9 answer, which has no head).
    pub status: u16,
    /// The head up to the blank line, the status line included, with the value of every
    /// `Date` line replaced by `<date>`; empty when there is no complete head.
    pub head: String,
    /// The header lines after the status line, split at the first `": "`, values as sent;
    /// lines without `": "` are left out. Empty when there is no complete head.
    pub headers: Vec<(String, String)>,
    /// What follows the blank line; all of [`raw`](Self::raw) when there is no complete
    /// head.
    pub body: Vec<u8>,
}

impl RawResponse {
    /// The value of the first header named `name`, compared without case.
    pub fn header(&self, name: &str) -> Option<&str> {
        self.headers
            .iter()
            .find(|(k, _)| k.eq_ignore_ascii_case(name))
            .map(|(_, v)| v.as_str())
    }

    /// Every value of the headers named `name`, in order, compared without case.
    pub fn header_all<'a>(&'a self, name: &'a str) -> impl Iterator<Item = &'a str> + 'a {
        self.headers
            .iter()
            .filter(move |(k, _)| k.eq_ignore_ascii_case(name))
            .map(|(_, v)| v.as_str())
    }

    /// The header names in the order they were sent.
    pub fn header_names(&self) -> Vec<&str> {
        self.headers.iter().map(|(k, _)| k.as_str()).collect()
    }

    /// The status line, when there is a complete head.
    pub fn status_line(&self) -> Option<&str> {
        if self.head.is_empty() {
            return None;
        }
        self.head.split("\r\n").next()
    }

    /// The body as text, invalid UTF-8 replaced.
    pub fn text(&self) -> String {
        String::from_utf8_lossy(&self.body).into_owned()
    }

    /// The body as JSON, `null` when it is not JSON.
    pub fn json(&self) -> Value {
        serde_json::from_slice(&self.body).unwrap_or(Value::Null)
    }

    /// The body as JSON as the donor's `raw` helper reads it (`json.loads(rest or b"{}")`):
    /// an empty body is `{}`, and a body that is not JSON fails the test, as `json.loads`
    /// raising fails the donor's. Panics on a non-empty body that is not JSON.
    pub fn donor_json(&self) -> Value {
        if self.body.is_empty() {
            return Value::Object(serde_json::Map::new());
        }
        match serde_json::from_slice(&self.body) {
            Ok(v) => v,
            Err(e) => panic!(
                "a body that is not JSON ({e}): {:?}",
                String::from_utf8_lossy(&self.body)
            ),
        }
    }

    /// The `route` field of a [`RouteProbe`](crate::server::probe::RouteProbe) answer:
    /// which handler slot served the request, when the probe answered.
    pub fn routed(&self) -> Option<String> {
        self.json()
            .get("route")
            .and_then(Value::as_str)
            .map(str::to_owned)
    }
}

/// Splits raw response bytes at the first blank line (`\r\n\r\n`) into status, head,
/// headers and body. Bytes with no blank line give status 0, an empty head and headers,
/// and all of the bytes as the body, so an HTTP/0.9 answer is still readable.
pub fn parse_response(raw: &[u8]) -> RawResponse {
    let Some(split) = find(raw, b"\r\n\r\n") else {
        return RawResponse {
            raw: raw.to_vec(),
            status: 0,
            head: String::new(),
            headers: Vec::new(),
            body: raw.to_vec(),
        };
    };
    let head_bytes = raw.get(..split).unwrap_or_default();
    // Latin-1, as Python's `http.client` reads a head: every byte stays one character.
    let head: String = head_bytes.iter().map(|&b| char::from(b)).collect();
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
        headers,
        body: raw.get(split + 4..).unwrap_or_default().to_vec(),
    }
}

/// Connects to `addr`. Panics (failing the test) when the connection is refused.
pub async fn connect(addr: SocketAddr) -> TcpStream {
    match tokio::time::timeout(DEADLINE, TcpStream::connect(addr)).await {
        Ok(Ok(stream)) => stream,
        Ok(Err(e)) => panic!("connect to {addr}: {e}"),
        Err(_) => panic!("connect to {addr}: no connection within the deadline"),
    }
}

/// Writes all of `bytes`. Panics (failing the test) when the write fails.
pub async fn write(stream: &mut TcpStream, bytes: &[u8]) {
    match tokio::time::timeout(DEADLINE, stream.write_all(bytes)).await {
        Ok(Ok(())) => {}
        Ok(Err(e)) => panic!("write: {e}"),
        Err(_) => panic!("write: not written within the deadline"),
    }
}

/// Reads until the server closes the connection, within [`DEADLINE`], as the donor's loop
/// over `recv` does. Panics when the read fails (a reset among others: the donor's `recv`
/// raises then, and its test fails), when no end of file comes within the deadline, or
/// when more than [`MAX_RESPONSE_BYTES`] arrive.
///
/// Behavior reference: project-maya serve/test_server.py:2061-2066 at 7e68a30f.
pub async fn read_to_eof(stream: &mut TcpStream) -> Vec<u8> {
    read_to_eof_within(stream, DEADLINE).await
}

/// [`read_to_eof`] with another deadline.
pub async fn read_to_eof_within(stream: &mut TcpStream, deadline: Duration) -> Vec<u8> {
    read_to_end_of(stream, deadline, false).await
}

/// [`read_to_eof`] for a test that expects the server may reset the connection: a failed
/// read ends the read like an end of file and returns what arrived. Not the donor's
/// behavior; a test that uses it says why.
pub async fn read_to_eof_allowing_reset(stream: &mut TcpStream) -> Vec<u8> {
    read_to_end_of(stream, DEADLINE, true).await
}

async fn read_to_end_of(stream: &mut TcpStream, deadline: Duration, allow_reset: bool) -> Vec<u8> {
    let mut raw = Vec::new();
    let mut buf = vec![0u8; READ_CHUNK];
    let mut failed: Option<std::io::Error> = None;
    let read = tokio::time::timeout(deadline, async {
        loop {
            match stream.read(&mut buf).await {
                Ok(0) => break,
                Err(e) => {
                    if !allow_reset {
                        failed = Some(e);
                    }
                    break;
                }
                Ok(n) => {
                    raw.extend_from_slice(buf.get(..n).unwrap_or_default());
                    if raw.len() > MAX_RESPONSE_BYTES {
                        break;
                    }
                }
            }
        }
    })
    .await;
    assert!(
        raw.len() <= MAX_RESPONSE_BYTES,
        "more than {MAX_RESPONSE_BYTES} bytes in one answer"
    );
    if let Some(e) = failed {
        panic!(
            "the read failed ({e}) before an end of file; got {:?}",
            String::from_utf8_lossy(&raw)
        );
    }
    match read {
        Ok(()) => raw,
        Err(_) => panic!(
            "no end of file within {deadline:?}; got {:?}",
            String::from_utf8_lossy(&raw)
        ),
    }
}

/// Reads until `done` holds for what arrived, the connection ends, or [`DEADLINE`]
/// passes; panics on the deadline. Returns what arrived.
pub async fn read_until(stream: &mut TcpStream, done: impl Fn(&[u8]) -> bool) -> Vec<u8> {
    let mut got = Vec::new();
    let mut buf = vec![0u8; READ_CHUNK];
    let result = tokio::time::timeout(DEADLINE, async {
        while !done(&got) {
            match stream.read(&mut buf).await {
                Ok(0) | Err(_) => break,
                Ok(n) => {
                    got.extend_from_slice(buf.get(..n).unwrap_or_default());
                    if got.len() > MAX_RESPONSE_BYTES {
                        break;
                    }
                }
            }
        }
    })
    .await;
    assert!(
        result.is_ok(),
        "timed out with {:?}",
        String::from_utf8_lossy(&got)
    );
    assert!(
        got.len() <= MAX_RESPONSE_BYTES,
        "more than {MAX_RESPONSE_BYTES} bytes in one answer"
    );
    got
}

/// The donor's `read_for`: reads for at most `period`, stopping early when the connection
/// ends or, with `until`, as soon as those bytes have arrived. Unlike [`read_until`] the
/// end of the period is not a failure: it returns what arrived, which may be nothing.
///
/// Behavior reference: project-maya serve/test_server.py:2430-2441 at 7e68a30f.
pub async fn read_for(stream: &mut TcpStream, period: Duration, until: Option<&[u8]>) -> Vec<u8> {
    let mut got = Vec::new();
    let mut buf = vec![0u8; READ_CHUNK];
    let end = Instant::now() + period;
    loop {
        if let Some(marker) = until {
            if contains(&got, marker) {
                break;
            }
        }
        let now = Instant::now();
        if now >= end || got.len() > MAX_RESPONSE_BYTES {
            break;
        }
        match tokio::time::timeout(end - now, stream.read(&mut buf)).await {
            Ok(Ok(0)) | Ok(Err(_)) | Err(_) => break,
            Ok(Ok(n)) => got.extend_from_slice(buf.get(..n).unwrap_or_default()),
        }
    }
    got
}

/// Connects, writes `request`, reads to end of file within [`DEADLINE`], and parses.
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

/// A request written by hand: method, target, version, header lines in order, and body.
/// Nothing is added that the caller did not ask for, except by [`RawRequest::json`] and
/// [`RawRequest::body`] (the `Content-Length` line); so a test can send any head, valid
/// or not.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RawRequest {
    method: String,
    target: String,
    version: String,
    headers: Vec<(String, String)>,
    body: Vec<u8>,
}

impl RawRequest {
    /// `method target HTTP/1.1` with no header and no body.
    pub fn new(method: &str, target: &str) -> Self {
        Self {
            method: method.to_owned(),
            target: target.to_owned(),
            version: String::from("HTTP/1.1"),
            headers: Vec::new(),
            body: Vec::new(),
        }
    }

    /// A `GET`.
    pub fn get(target: &str) -> Self {
        Self::new("GET", target)
    }

    /// A `POST`.
    pub fn post(target: &str) -> Self {
        Self::new("POST", target)
    }

    /// Another version token (for example `HTTP/1.0`).
    pub fn version(mut self, version: &str) -> Self {
        self.version = version.to_owned();
        self
    }

    /// Appends a header line `name: value`.
    pub fn header(mut self, name: &str, value: &str) -> Self {
        self.headers.push((name.to_owned(), value.to_owned()));
        self
    }

    /// Whether a header named `name` (any case) is already set.
    pub fn has_header(&self, name: &str) -> bool {
        self.headers
            .iter()
            .any(|(k, _)| k.eq_ignore_ascii_case(name))
    }

    /// Sets the body and appends its `Content-Length` line.
    pub fn body(mut self, body: &[u8]) -> Self {
        self.headers
            .push((String::from("Content-Length"), body.len().to_string()));
        self.body = body.to_vec();
        self
    }

    /// Sets the body without any length line (for chunked or deliberately unframed bodies).
    pub fn raw_body(mut self, body: &[u8]) -> Self {
        self.body = body.to_vec();
        self
    }

    /// A JSON body: `Content-Type: application/json`, then [`body`](Self::body).
    pub fn json(self, body: &str) -> Self {
        self.header("Content-Type", "application/json")
            .body(body.as_bytes())
    }

    /// The bytes on the wire.
    pub fn to_bytes(&self) -> Vec<u8> {
        let mut text = format!("{} {} {}\r\n", self.method, self.target, self.version);
        for (k, v) in &self.headers {
            text.push_str(k);
            text.push_str(": ");
            text.push_str(v);
            text.push_str("\r\n");
        }
        text.push_str("\r\n");
        let mut bytes = text.into_bytes();
        bytes.extend_from_slice(&self.body);
        bytes
    }

    /// Sends the request to `addr` and reads the answer ([`exchange`]).
    pub async fn send(&self, addr: SocketAddr) -> RawResponse {
        exchange(addr, &self.to_bytes()).await
    }
}

/// A `POST` to `path` as the donor writes one by hand: `Host: 127.0.0.1`,
/// `Content-Type: application/json`, then the caller's header lines (each ending in
/// `\r\n`), the blank line and `body`, which is not framed unless `headers` frames it.
///
/// Behavior reference: project-maya serve/test_server.py:2057-2059 at 7e68a30f.
pub fn post_to(path: &str, headers: &str, body: &[u8]) -> Vec<u8> {
    let mut bytes = format!(
        "POST {path} HTTP/1.1\r\nHost: {DONOR_HOST}\r\nContent-Type: application/json\r\n{headers}\r\n"
    )
    .into_bytes();
    bytes.extend_from_slice(body);
    bytes
}

/// [`post_to`] for `/v1/chat/completions`: the donor's `RequestBodies.raw` request.
pub fn donor_post(headers: &str, body: &[u8]) -> Vec<u8> {
    post_to(CHAT_PATH, headers, body)
}

/// A framed JSON `POST` to `path`, as the donor's `GoneClients.send` and
/// `QueuedKeepAlives.send_to` write it.
///
/// Behavior reference: project-maya serve/test_server.py:2380-2387, 2423-2428 at 7e68a30f.
pub fn json_post(path: &str, body: &[u8]) -> Vec<u8> {
    post_to(path, &format!("Content-Length: {}\r\n", body.len()), body)
}

/// The `Server` line every answer of the transport carries (approved deviation P-1):
/// `pulsar-console/<version>`, built here from the product name and the workspace version
/// (every crate takes `version.workspace`), apart from the transport's own constant, so
/// a test that compares it with an answer pins the value instead of reading it back.
pub fn server_line() -> String {
    format!("Server: pulsar-console/{}", env!("CARGO_PKG_VERSION"))
}

/// The JSON error body of the donor's `BadBody` (`invalid_request_error`).
pub fn invalid_request(message: &str) -> String {
    format!("{{\"error\": {{\"type\": \"invalid_request_error\", \"message\": \"{message}\"}}}}")
}

/// The first position of `needle` in `haystack`.
pub fn find(haystack: &[u8], needle: &[u8]) -> Option<usize> {
    if needle.is_empty() {
        return Some(0);
    }
    haystack.windows(needle.len()).position(|w| w == needle)
}

/// How many times `needle` occurs in `haystack` (overlaps counted, as a window scan
/// counts them; the kit's markers cannot overlap themselves).
pub fn count(haystack: &[u8], needle: &[u8]) -> usize {
    if needle.is_empty() {
        return 0;
    }
    haystack
        .windows(needle.len())
        .filter(|w| *w == needle)
        .count()
}

/// Whether `needle` occurs in `haystack`.
pub fn contains(haystack: &[u8], needle: &[u8]) -> bool {
    find(haystack, needle).is_some()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_splits_head_and_body_and_masks_the_date() {
        let raw = b"HTTP/1.0 200 OK\r\nServer: x\r\nDate: Mon, 01 Jan 2026 00:00:00 GMT\r\nX-Two: a: b\r\nbare\r\n\r\n{\"a\": 1}";
        let r = parse_response(raw);
        assert_eq!(r.status, 200);
        assert_eq!(
            r.head,
            "HTTP/1.0 200 OK\r\nServer: x\r\nDate: <date>\r\nX-Two: a: b\r\nbare"
        );
        assert_eq!(
            r.headers,
            vec![
                ("Server".to_owned(), "x".to_owned()),
                (
                    "Date".to_owned(),
                    "Mon, 01 Jan 2026 00:00:00 GMT".to_owned()
                ),
                ("X-Two".to_owned(), "a: b".to_owned()),
            ]
        );
        assert_eq!(r.header("x-two"), Some("a: b"));
        assert_eq!(r.header_names(), vec!["Server", "Date", "X-Two"]);
        assert_eq!(r.status_line(), Some("HTTP/1.0 200 OK"));
        assert_eq!(r.body, b"{\"a\": 1}");
        assert_eq!(r.json()["a"], 1);
        assert_eq!(r.raw, raw);
    }

    #[test]
    fn parse_without_a_head_keeps_every_byte_as_the_body() {
        let r = parse_response(b"ok");
        assert_eq!(r.status, 0);
        assert!(r.head.is_empty() && r.headers.is_empty());
        assert_eq!(r.status_line(), None);
        assert_eq!(r.body, b"ok");
        let empty = parse_response(b"");
        assert_eq!(empty.status, 0);
        assert!(empty.raw.is_empty() && empty.body.is_empty());
        assert_eq!(empty.donor_json(), serde_json::json!({}));
    }

    #[test]
    fn parse_keeps_latin1_head_bytes_as_characters() {
        let r = parse_response(b"HTTP/1.0 200 OK\r\nX: \xe9\r\n\r\n");
        assert_eq!(r.header("X"), Some("\u{e9}"));
        let bad = parse_response(b"HTTP/1.0 abc\r\n\r\n");
        assert_eq!(bad.status, 0);
    }

    #[test]
    fn requests_are_written_as_given() {
        let r = RawRequest::post("/x")
            .header("Host", "h")
            .json("{}")
            .to_bytes();
        assert_eq!(
            r,
            b"POST /x HTTP/1.1\r\nHost: h\r\nContent-Type: application/json\r\nContent-Length: 2\r\n\r\n{}"
        );
        let r = RawRequest::get("/").version("HTTP/1.0").to_bytes();
        assert_eq!(r, b"GET / HTTP/1.0\r\n\r\n");
        assert!(RawRequest::get("/").header("HOST", "x").has_header("host"));
        assert_eq!(
            RawRequest::post("/c")
                .header("Transfer-Encoding", "chunked")
                .raw_body(b"0\r\n\r\n")
                .to_bytes(),
            b"POST /c HTTP/1.1\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n"
        );
    }

    #[test]
    fn donor_requests_have_the_donor_head() {
        assert_eq!(
            donor_post("Content-Length: 2\r\n", b"{}"),
            b"POST /v1/chat/completions HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\nContent-Length: 2\r\n\r\n{}"
        );
        assert_eq!(
            json_post("/v1/messages", b"{}"),
            post_to("/v1/messages", "Content-Length: 2\r\n", b"{}")
        );
        assert_eq!(
            invalid_request("m"),
            "{\"error\": {\"type\": \"invalid_request_error\", \"message\": \"m\"}}"
        );
        assert_eq!(
            server_line(),
            format!("Server: pulsar-console/{}", env!("CARGO_PKG_VERSION"))
        );
    }

    #[test]
    fn donor_json_reads_an_empty_body_as_an_object() {
        let r = parse_response(b"HTTP/1.0 200 OK\r\n\r\n{\"a\": 1}");
        assert_eq!(r.donor_json(), serde_json::json!({"a": 1}));
        let empty = parse_response(b"HTTP/1.0 200 OK\r\n\r\n");
        assert_eq!(empty.donor_json(), serde_json::json!({}));
    }

    #[test]
    #[should_panic(expected = "a body that is not JSON")]
    fn donor_json_fails_on_a_body_that_is_not_json() {
        let _ = parse_response(b"HTTP/1.0 200 OK\r\n\r\n<html>").donor_json();
    }

    #[test]
    fn byte_search_helpers() {
        assert_eq!(count(b": k\n\n: k\n\n", b": k"), 2);
        assert_eq!(count(b"abc", b""), 0);
        assert!(contains(b"xx hello", b"hello"));
        assert!(!contains(b"xx", b"hello"));
        assert_eq!(find(b"abc", b"c"), Some(2));
        assert_eq!(find(b"abc", b""), Some(0));
    }
}
