//! Owned by CNF-03. The observation recorder: framing, SSE and NDJSON parsing, and the
//! observation document.
//!
//! An [`Exchange`] is what one request got back, recorded by
//! [`crate::client`]: the bytes sent, every interim and final response head with its
//! headers in order, the framing of the body (and, for a chunked body, every chunk size
//! and trailer), the de-framed body, the body parsed by its media type (JSON, an event
//! stream as [`SseStream`], NDJSON as [`NdjsonStream`], or opaque bytes), how the read
//! ended, the disconnect the client made, and every byte received.
//!
//! Nothing is normalized here: the comparator of CNF-04 decides what is volatile
//! (`contracts/parity-ledger.md` section 1.1, where header names, header order and stream
//! framing are observable). [`Exchange::to_json`] writes the whole record;
//! [`Exchange::logical_json`] writes the part that does not depend on how the body was
//! framed, which is what the self-tests of CNF-03 compare across Content-Length, chunked
//! and close-delimited answers.
//!
//! An [`Observation`] is the document of one scenario run, with the five parts the
//! conformance design names: `http`, `engine_tape`, `files`, `log` and `exit`. The client
//! fills `http`; the other parts are recorded by the packages that run the server and the
//! engine, through the constructors here.
//!
//! Behavior reference: project-maya serve/server.py:5404-5406 (HTTP/1.0, a stream ends by
//! closing the connection) and 5456-5463 (a JSON answer with Content-Length) at 7e68a30f.

pub mod ndjson;
pub mod sse;

use std::io::Read;
use std::path::Path;

use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};

use crate::client::{Disconnect, DisconnectMode, Trigger};

pub use ndjson::{NdjsonLine, NdjsonParser, NdjsonStream};
pub use sse::{SseComment, SseEvent, SseParser, SseStream};

/// Header names whose presence and value follow from the framing of the body. They are
/// left out of [`Exchange::logical_json`] and kept everywhere else.
pub const FRAMING_HEADERS: &[&str] = &["content-length", "transfer-encoding"];

/// The largest file [`FileRecord::read`] reads.
pub const MAX_FILE_BYTES: usize = 16 * 1024 * 1024;

/// One response header, as received. The value is decoded as ISO-8859-1, so every byte
/// maps to one character and nothing is lost (as Python's `http.client` decodes it).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Header {
    /// The name, as sent (case kept).
    pub name: String,
    /// The value, as sent, without the surrounding white space the parser drops.
    pub value: String,
}

/// A response head: the status line and the headers in order.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ResponseHead {
    /// The version token of the status line, `HTTP/1.0` or `HTTP/1.1`.
    pub version: String,
    /// The status code.
    pub code: u16,
    /// The reason phrase, decoded as ISO-8859-1.
    pub reason: String,
    /// Every header, in the order received, duplicates kept.
    pub headers: Vec<Header>,
    /// The exact bytes of the head, through the blank line that ends it.
    pub raw: Vec<u8>,
}

impl ResponseHead {
    /// The value of the first header named `name` (compared without case).
    pub fn header(&self, name: &str) -> Option<&str> {
        self.headers
            .iter()
            .find(|h| h.name.eq_ignore_ascii_case(name))
            .map(|h| h.value.as_str())
    }

    /// The values of every header named `name`, in order.
    pub fn headers_named<'a>(&'a self, name: &'a str) -> impl Iterator<Item = &'a str> + 'a {
        self.headers
            .iter()
            .filter(move |h| h.name.eq_ignore_ascii_case(name))
            .map(|h| h.value.as_str())
    }

    /// The media type of the first `Content-Type` header, lower case, without
    /// parameters.
    pub fn media_type(&self) -> Option<String> {
        let value = self.header("content-type")?;
        let media = value.split(';').next().unwrap_or("").trim();
        Some(media.to_ascii_lowercase())
    }

    fn to_json(&self, logical: bool) -> Value {
        let headers: Vec<Value> = self
            .headers
            .iter()
            .filter(|h| {
                !logical
                    || !FRAMING_HEADERS
                        .iter()
                        .any(|f| h.name.eq_ignore_ascii_case(f))
            })
            .map(|h| json!([h.name, h.value]))
            .collect();
        let mut map = Map::new();
        map.insert("version".into(), json!(self.version));
        map.insert("code".into(), json!(self.code));
        map.insert("reason".into(), json!(self.reason));
        map.insert("headers".into(), Value::Array(headers));
        if !logical {
            map.insert("raw".into(), bytes_json(&self.raw));
        }
        Value::Object(map)
    }
}

/// One chunk of a chunked body.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ChunkRecord {
    /// The chunk size.
    pub size: u64,
    /// The chunk extension after `;`, verbatim (empty when there is none).
    pub ext: String,
}

/// How the body was delimited.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Framing {
    /// No body by rule: a HEAD request, or status 1xx, 204 or 304.
    NoBody,
    /// `Content-Length` gave the length.
    ContentLength(u64),
    /// `Transfer-Encoding: chunked`. The chunks read, the terminating zero chunk
    /// included when it was read, and the trailer fields.
    Chunked {
        /// Every chunk, in order.
        chunks: Vec<ChunkRecord>,
        /// Trailer fields after the zero chunk.
        trailers: Vec<Header>,
    },
    /// The body ran to the end of the connection.
    CloseDelimited,
    /// The answer had no head: it did not start with `HTTP/` and could not be parsed as
    /// a status line, so every byte received is the body (Python's `http.server` answers
    /// an HTTP/0.9 request line this way). [`Exchange::end`] is then
    /// [`End::Malformed`].
    Headless,
}

impl Framing {
    fn to_json(&self) -> Value {
        match self {
            Framing::NoBody => json!({"kind": "none"}),
            Framing::ContentLength(n) => json!({"kind": "content-length", "length": n}),
            Framing::Chunked { chunks, trailers } => json!({
                "kind": "chunked",
                "chunks": chunks
                    .iter()
                    .map(|c| json!({"size": c.size, "ext": c.ext}))
                    .collect::<Vec<_>>(),
                "trailers": trailers
                    .iter()
                    .map(|h| json!([h.name, h.value]))
                    .collect::<Vec<_>>(),
            }),
            Framing::CloseDelimited => json!({"kind": "close-delimited"}),
            Framing::Headless => json!({"kind": "headless"}),
        }
    }
}

/// The body parsed by its media type.
#[derive(Debug, Clone, PartialEq)]
pub enum Content {
    /// `application/json` that parses.
    Json(Value),
    /// `application/json` that does not parse (the body is kept in [`Exchange::body`]).
    InvalidJson(String),
    /// `text/event-stream`.
    Sse(SseStream),
    /// `application/x-ndjson`.
    Ndjson(NdjsonStream),
    /// Any other media type, or none: only the bytes in [`Exchange::body`].
    Opaque,
}

/// How reading the response ended.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum End {
    /// The body ended as its framing says (for a close-delimited body, at end of file).
    Complete,
    /// The connection ended before the head or the body was complete.
    Truncated,
    /// The client disconnected (a [`DisconnectMode::Close`] disconnect fired).
    Disconnected,
    /// No byte arrived within the read timeout, or the deadline passed.
    Timeout,
    /// A read failed; the value is the error kind (for example `ConnectionReset`).
    Io(String),
    /// The head or the chunked framing could not be parsed; the value says what. The
    /// rest of the connection was still read (to end of file or the deadline) and kept
    /// in [`Exchange::wire`], and in [`Exchange::body`] for a [`Framing::Headless`]
    /// answer.
    Malformed(String),
    /// A read limit was reached; the value names it.
    LimitExceeded(String),
}

impl End {
    fn to_json(&self) -> Value {
        match self {
            End::Complete => json!({"kind": "complete"}),
            End::Truncated => json!({"kind": "truncated"}),
            End::Disconnected => json!({"kind": "disconnected"}),
            End::Timeout => json!({"kind": "timeout"}),
            End::Io(kind) => json!({"kind": "io", "error": kind}),
            End::Malformed(what) => json!({"kind": "malformed", "error": what}),
            End::LimitExceeded(what) => json!({"kind": "limit", "error": what}),
        }
    }
}

/// The disconnect asked for, and where it fired.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DisconnectRecord {
    /// What was asked for.
    pub asked: Disconnect,
    /// Whether the trigger fired before the response ended.
    pub fired: bool,
    /// Bytes received when it fired (or in all, when it did not).
    pub wire_bytes: u64,
    /// De-framed body bytes recorded when it fired.
    pub body_bytes: u64,
    /// Stream events (SSE events or NDJSON lines) recorded when it fired.
    pub events: u64,
}

impl DisconnectRecord {
    fn to_json(&self, logical: bool) -> Value {
        let (trigger, n) = match self.asked.trigger {
            Trigger::AfterRequest => ("after-request", None),
            Trigger::AfterEvents(n) => ("after-events", Some(n)),
            Trigger::AfterBytes(n) => ("after-bytes", Some(n)),
        };
        let mode = match self.asked.mode {
            DisconnectMode::Close => "close",
            DisconnectMode::HalfClose => "half-close",
        };
        let mut map = Map::new();
        map.insert("trigger".into(), json!(trigger));
        if let Some(n) = n {
            map.insert("n".into(), json!(n));
        }
        map.insert("mode".into(), json!(mode));
        map.insert("fired".into(), json!(self.fired));
        if !logical {
            map.insert("wire_bytes".into(), json!(self.wire_bytes));
        }
        map.insert("body_bytes".into(), json!(self.body_bytes));
        map.insert("events".into(), json!(self.events));
        Value::Object(map)
    }
}

/// Everything one request got back.
#[derive(Debug, Clone, PartialEq)]
pub struct Exchange {
    /// The request bytes the client tried to send, exactly as built. When
    /// [`Exchange::write_error`] is set, only the first [`Exchange::request_sent`] of
    /// them reached the socket.
    pub request: Vec<u8>,
    /// How many bytes of [`Exchange::request`] were written to the socket.
    pub request_sent: u64,
    /// The error kind when writing the request failed part way, `TimedOut` when the
    /// deadline cut it short (the response is still read: a server may answer before it
    /// reads the whole request).
    pub write_error: Option<String>,
    /// Interim (1xx) heads before the final one.
    pub interim: Vec<ResponseHead>,
    /// The final head, when a complete one was read.
    pub head: Option<ResponseHead>,
    /// How the body was delimited, when a head was read.
    pub framing: Option<Framing>,
    /// The de-framed body bytes recorded (up to the disconnect, when one fired).
    pub body: Vec<u8>,
    /// The body parsed by its media type.
    pub content: Content,
    /// How reading ended.
    pub end: End,
    /// After a complete body: whether the server closed the connection within the close
    /// wait (`Some(false)` when it kept it open). `None` when not checked.
    pub server_closed: Option<bool>,
    /// The disconnect asked for, and where it fired.
    pub disconnect: Option<DisconnectRecord>,
    /// Every byte received, in order. After a disconnect it may hold bytes past the
    /// disconnect point that arrived in the same read; [`Exchange::body`] and the parsed
    /// content never do.
    pub wire: Vec<u8>,
}

impl Exchange {
    /// The final status code, when a head was read.
    pub fn status(&self) -> Option<u16> {
        self.head.as_ref().map(|h| h.code)
    }

    /// The value of the first header named `name` in the final head.
    pub fn header(&self, name: &str) -> Option<&str> {
        self.head.as_ref().and_then(|h| h.header(name))
    }

    /// The parsed JSON body, when the body was JSON.
    pub fn json(&self) -> Option<&Value> {
        match &self.content {
            Content::Json(v) => Some(v),
            _ => None,
        }
    }

    /// The SSE events, when the body was an event stream; empty otherwise.
    pub fn events(&self) -> &[SseEvent] {
        match &self.content {
            Content::Sse(s) => &s.events,
            _ => &[],
        }
    }

    /// The NDJSON lines, when the body was NDJSON; empty otherwise.
    pub fn lines(&self) -> &[NdjsonLine] {
        match &self.content {
            Content::Ndjson(s) => &s.lines,
            _ => &[],
        }
    }

    /// The whole record as JSON, keys in a fixed order.
    pub fn to_json(&self) -> Value {
        self.build_json(false)
    }

    /// The record without what depends on the framing: no `framing`, no
    /// `server_closed`, no `wire`, no raw head bytes, no [`FRAMING_HEADERS`], and no wire
    /// byte count in the disconnect. The same logical response gives the same value
    /// whether it was sent with Content-Length, chunked or close-delimited.
    pub fn logical_json(&self) -> Value {
        self.build_json(true)
    }

    fn build_json(&self, logical: bool) -> Value {
        let mut map = Map::new();
        map.insert("request".into(), bytes_json(&self.request));
        map.insert("request_sent".into(), json!(self.request_sent));
        map.insert(
            "write_error".into(),
            self.write_error.as_ref().map_or(Value::Null, |e| json!(e)),
        );
        map.insert(
            "interim".into(),
            Value::Array(self.interim.iter().map(|h| h.to_json(logical)).collect()),
        );
        map.insert(
            "head".into(),
            self.head
                .as_ref()
                .map_or(Value::Null, |h| h.to_json(logical)),
        );
        if !logical {
            map.insert(
                "framing".into(),
                self.framing.as_ref().map_or(Value::Null, Framing::to_json),
            );
        }
        map.insert("body".into(), bytes_json(&self.body));
        map.insert("content".into(), content_json(&self.content));
        map.insert("end".into(), self.end.to_json());
        if !logical {
            map.insert(
                "server_closed".into(),
                self.server_closed.map_or(Value::Null, Value::Bool),
            );
        }
        map.insert(
            "disconnect".into(),
            self.disconnect
                .as_ref()
                .map_or(Value::Null, |d| d.to_json(logical)),
        );
        if !logical {
            map.insert("wire".into(), bytes_json(&self.wire));
        }
        Value::Object(map)
    }
}

fn content_json(content: &Content) -> Value {
    match content {
        Content::Json(v) => json!({"kind": "json", "value": v}),
        Content::InvalidJson(e) => json!({"kind": "json-invalid", "error": e}),
        Content::Sse(s) => {
            let events: Vec<Value> = s
                .events
                .iter()
                .map(|e| {
                    let mut m = Map::new();
                    m.insert("event".into(), opt_str(&e.event));
                    m.insert("data".into(), opt_str(&e.data));
                    if let Some(v) = e.data_json() {
                        m.insert("json".into(), v);
                    }
                    m.insert("id".into(), opt_str(&e.id));
                    m.insert("retry".into(), opt_str(&e.retry));
                    m.insert(
                        "fields".into(),
                        Value::Array(e.fields.iter().map(|(n, v)| json!([n, v])).collect()),
                    );
                    m.insert("raw".into(), bytes_json(&e.raw));
                    Value::Object(m)
                })
                .collect();
            let comments: Vec<Value> = s
                .comments
                .iter()
                .map(|c| json!({"before_event": c.before_event, "text": c.text}))
                .collect();
            json!({
                "kind": "sse",
                "events": events,
                "comments": comments,
                "unterminated": s.unterminated.as_deref().map_or(Value::Null, bytes_json),
                "bom": s.bom,
                "invalid_utf8": s.invalid_utf8,
            })
        }
        Content::Ndjson(s) => {
            let lines: Vec<Value> = s
                .lines
                .iter()
                .map(|l| {
                    let mut m = Map::new();
                    m.insert("text".into(), json!(l.text));
                    m.insert("json".into(), l.json.clone().unwrap_or(Value::Null));
                    m.insert("is_json".into(), json!(l.json.is_some()));
                    Value::Object(m)
                })
                .collect();
            json!({
                "kind": "ndjson",
                "lines": lines,
                "unterminated": s.unterminated.as_deref().map_or(Value::Null, bytes_json),
                "invalid_utf8": s.invalid_utf8,
            })
        }
        Content::Opaque => json!({"kind": "opaque"}),
    }
}

fn opt_str(v: &Option<String>) -> Value {
    v.as_ref().map_or(Value::Null, |s| json!(s))
}

/// Bytes as JSON: `{"length", "sha256", "text"}` when they are UTF-8, otherwise
/// `{"length", "sha256", "base64"}`.
pub fn bytes_json(bytes: &[u8]) -> Value {
    let mut map = Map::new();
    map.insert("length".into(), json!(bytes.len()));
    map.insert("sha256".into(), json!(sha256_hex(bytes)));
    match std::str::from_utf8(bytes) {
        Ok(text) => map.insert("text".into(), json!(text)),
        Err(_) => map.insert("base64".into(), json!(base64(bytes))),
    };
    Value::Object(map)
}

/// The SHA-256 of `bytes` in lower-case hex.
pub fn sha256_hex(bytes: &[u8]) -> String {
    let digest = Sha256::digest(bytes);
    let mut out = String::with_capacity(64);
    for b in digest {
        out.push(hex_digit(b >> 4));
        out.push(hex_digit(b & 0xf));
    }
    out
}

fn hex_digit(n: u8) -> char {
    char::from(if n < 10 { b'0' + n } else { b'a' + n - 10 })
}

/// Standard base64 with padding (RFC 4648 section 4).
pub fn base64(bytes: &[u8]) -> String {
    const ALPHABET: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let sym = |i: u32| char::from(ALPHABET[(i & 63) as usize]);
    let mut out = String::with_capacity(bytes.len().div_ceil(3) * 4);
    for chunk in bytes.chunks(3) {
        let b0 = chunk.first().copied().map_or(0, u32::from);
        let b1 = chunk.get(1).copied().map_or(0, u32::from);
        let b2 = chunk.get(2).copied().map_or(0, u32::from);
        let n = (b0 << 16) | (b1 << 8) | b2;
        out.push(sym(n >> 18));
        out.push(sym(n >> 12));
        out.push(if chunk.len() > 1 { sym(n >> 6) } else { '=' });
        out.push(if chunk.len() > 2 { sym(n) } else { '=' });
    }
    out
}

/// Decodes ISO-8859-1: every byte is the character with that code point.
pub fn latin1(bytes: &[u8]) -> String {
    bytes.iter().map(|&b| char::from(b)).collect()
}

/// A file written by the server, as recorded.
#[derive(Debug, Clone, PartialEq)]
pub struct FileRecord {
    /// The path relative to the data directory, with `/` separators.
    pub path: String,
    /// The exact bytes.
    pub bytes: Vec<u8>,
    /// The bytes parsed as JSON, when they parse.
    pub json: Option<Value>,
}

impl FileRecord {
    /// A record of `bytes` at `path`.
    pub fn from_bytes(path: &str, bytes: Vec<u8>) -> Self {
        let json = serde_json::from_slice(&bytes).ok();
        Self {
            path: path.to_string(),
            bytes,
            json,
        }
    }

    /// Reads `root/rel`, up to [`MAX_FILE_BYTES`]. `rel` must be relative and must not
    /// leave `root`: no part of it may be a symbolic link, and it must name a regular
    /// file (a named pipe or a device is refused without being opened for reading).
    pub fn read(root: &Path, rel: &str) -> std::io::Result<Self> {
        let bad = rel.is_empty()
            || rel.starts_with('/')
            || rel
                .split('/')
                .any(|s| s.is_empty() || s == "." || s == "..");
        if bad {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidInput,
                "not a relative path inside the data directory",
            ));
        }
        let file = open_inside(root, Path::new(rel))?;
        let mut bytes = Vec::new();
        let cap = u64::try_from(MAX_FILE_BYTES).unwrap_or(u64::MAX) + 1;
        file.take(cap).read_to_end(&mut bytes)?;
        if bytes.len() > MAX_FILE_BYTES {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                "file larger than the observation limit",
            ));
        }
        Ok(Self::from_bytes(rel, bytes))
    }

    fn to_json(&self) -> Value {
        let mut map = Map::new();
        map.insert("path".into(), json!(self.path));
        map.insert("bytes".into(), bytes_json(&self.bytes));
        map.insert("json".into(), self.json.clone().unwrap_or(Value::Null));
        map.insert("is_json".into(), json!(self.json.is_some()));
        Value::Object(map)
    }
}

/// Opens the regular file `root/rel` for reading without following a symbolic link in
/// `rel`. Every part of `rel` must be a plain name; each directory on the way is checked
/// with `symlink_metadata`, and the file itself is opened with `O_NOFOLLOW` and
/// `O_NONBLOCK` (so a named pipe does not block) and refused unless it is a regular file.
pub(crate) fn open_inside(root: &Path, rel: &Path) -> std::io::Result<std::fs::File> {
    use std::io::{Error, ErrorKind};
    use std::path::Component;
    let refuse = |why: &str| Error::new(ErrorKind::InvalidInput, why.to_string());
    let parts: Vec<_> = rel.components().collect();
    if parts.is_empty() || !parts.iter().all(|c| matches!(c, Component::Normal(_))) {
        return Err(refuse("not a plain relative path"));
    }
    let mut path = root.to_path_buf();
    for part in &parts {
        path.push(part);
        if std::fs::symlink_metadata(&path)?.file_type().is_symlink() {
            return Err(refuse("a part of the path is a symbolic link"));
        }
    }
    let mut options = std::fs::OpenOptions::new();
    options.read(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK);
    }
    let file = options.open(&path)?;
    if !file.metadata()?.is_file() {
        return Err(refuse("not a regular file"));
    }
    Ok(file)
}

/// How the server process ended.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ExitRecord {
    /// The exit code, when it exited.
    pub code: Option<i32>,
    /// The signal number, when a signal ended it.
    pub signal: Option<i32>,
}

impl ExitRecord {
    /// The record of a process status.
    pub fn from_status(status: std::process::ExitStatus) -> Self {
        #[cfg(unix)]
        let signal = {
            use std::os::unix::process::ExitStatusExt;
            status.signal()
        };
        #[cfg(not(unix))]
        let signal = None;
        Self {
            code: status.code(),
            signal,
        }
    }

    fn to_json(self) -> Value {
        json!({"code": self.code, "signal": self.signal})
    }
}

/// The observation document of one scenario run.
#[derive(Debug, Clone, PartialEq, Default)]
pub struct Observation {
    /// One exchange per request, in step order.
    pub http: Vec<Exchange>,
    /// The engine tape, as the engine side recorded it.
    pub engine_tape: Option<Value>,
    /// The observed files. The document writes them in path order (byte order of
    /// [`FileRecord::path`]), whatever order they were added in.
    pub files: Vec<FileRecord>,
    /// The contracted log lines.
    pub log: Vec<String>,
    /// How the server ended, when observed.
    pub exit: Option<ExitRecord>,
}

impl Observation {
    /// The document as JSON, with the keys `http`, `engine_tape`, `files`, `log` and
    /// `exit` in that order.
    pub fn to_json(&self) -> Value {
        self.build_json(false)
    }

    /// As [`Observation::to_json`], with each exchange written by
    /// [`Exchange::logical_json`].
    pub fn logical_json(&self) -> Value {
        self.build_json(true)
    }

    fn build_json(&self, logical: bool) -> Value {
        let mut map = Map::new();
        map.insert(
            "http".into(),
            Value::Array(
                self.http
                    .iter()
                    .map(|e| {
                        if logical {
                            e.logical_json()
                        } else {
                            e.to_json()
                        }
                    })
                    .collect(),
            ),
        );
        map.insert(
            "engine_tape".into(),
            self.engine_tape.clone().unwrap_or(Value::Null),
        );
        let mut files: Vec<&FileRecord> = self.files.iter().collect();
        files.sort_by(|a, b| a.path.cmp(&b.path));
        map.insert(
            "files".into(),
            Value::Array(files.into_iter().map(FileRecord::to_json).collect()),
        );
        map.insert(
            "log".into(),
            Value::Array(self.log.iter().map(|l| json!(l)).collect()),
        );
        map.insert(
            "exit".into(),
            self.exit.map_or(Value::Null, ExitRecord::to_json),
        );
        Value::Object(map)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn base64_matches_rfc_4648_vectors() {
        let cases: [(&[u8], &str); 7] = [
            (b"", ""),
            (b"f", "Zg=="),
            (b"fo", "Zm8="),
            (b"foo", "Zm9v"),
            (b"foob", "Zm9vYg=="),
            (b"fooba", "Zm9vYmE="),
            (b"foobar", "Zm9vYmFy"),
        ];
        for (input, want) in cases {
            assert_eq!(base64(input), want);
        }
    }

    #[test]
    fn sha256_hex_of_empty_input() {
        assert_eq!(
            sha256_hex(b""),
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        );
    }

    #[test]
    fn bytes_json_uses_text_or_base64() {
        assert_eq!(bytes_json(b"hi")["text"], json!("hi"));
        assert_eq!(bytes_json(b"\xff")["base64"], json!("/w=="));
        assert_eq!(bytes_json(b"\xff")["length"], json!(1));
    }

    #[test]
    fn latin1_keeps_every_byte() {
        assert_eq!(latin1(b"a\xe9\xff"), "a\u{e9}\u{ff}");
    }

    #[test]
    fn media_type_is_lower_case_without_parameters() {
        let head = ResponseHead {
            version: "HTTP/1.0".into(),
            code: 200,
            reason: "OK".into(),
            headers: vec![Header {
                name: "Content-Type".into(),
                value: "Text/Event-Stream; charset=utf-8".into(),
            }],
            raw: Vec::new(),
        };
        assert_eq!(head.media_type().as_deref(), Some("text/event-stream"));
        assert_eq!(
            head.header("CONTENT-TYPE"),
            Some("Text/Event-Stream; charset=utf-8")
        );
    }

    #[test]
    fn file_records_refuse_paths_outside_the_root() {
        let root = Path::new(".");
        for rel in ["", "/etc/x", "../x", "a/../b", "a//b", "./a"] {
            assert!(FileRecord::read(root, rel).is_err(), "{rel}");
        }
        let rec = FileRecord::from_bytes("s.json", b"{\"a\": 1}".to_vec());
        assert_eq!(rec.json, Some(json!({"a": 1})));
        assert_eq!(FileRecord::from_bytes("t", b"x y".to_vec()).json, None);
    }

    /// A fresh directory under the system temporary directory.
    fn scratch(name: &str) -> std::path::PathBuf {
        let dir = std::env::temp_dir().join(format!(
            "cnf03-{name}-{}-{:?}",
            std::process::id(),
            std::thread::current().id()
        ));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap_or_else(|e| panic!("mkdir: {e}"));
        dir
    }

    #[cfg(unix)]
    #[test]
    fn file_records_refuse_symlinks_and_non_regular_files() {
        let dir = scratch("files");
        let root = dir.join("data");
        let outside = dir.join("outside.txt");
        std::fs::create_dir_all(root.join("sub")).unwrap_or_else(|e| panic!("mkdir: {e}"));
        std::fs::write(&outside, b"private").unwrap_or_else(|e| panic!("write: {e}"));
        std::fs::write(root.join("sub/ok.json"), b"{\"a\": 1}")
            .unwrap_or_else(|e| panic!("write: {e}"));
        std::os::unix::fs::symlink(&outside, root.join("link"))
            .unwrap_or_else(|e| panic!("symlink: {e}"));
        std::os::unix::fs::symlink(&dir, root.join("dirlink"))
            .unwrap_or_else(|e| panic!("symlink: {e}"));
        let ok = FileRecord::read(&root, "sub/ok.json");
        assert_eq!(ok.ok().and_then(|r| r.json), Some(json!({"a": 1})));
        assert!(FileRecord::read(&root, "link").is_err());
        assert!(FileRecord::read(&root, "dirlink/outside.txt").is_err());
        assert!(FileRecord::read(&root, "sub").is_err());
        // A named pipe with no writer: refused at once instead of blocking.
        let fifo = root.join("pipe");
        let made = std::process::Command::new("mkfifo")
            .arg(&fifo)
            .status()
            .is_ok_and(|s| s.success());
        if made {
            let started = std::time::Instant::now();
            assert!(FileRecord::read(&root, "pipe").is_err());
            assert!(started.elapsed() < std::time::Duration::from_secs(5));
        }
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn observation_files_are_written_in_path_order() {
        let obs = Observation {
            files: vec![
                FileRecord::from_bytes("sessions/b.json", b"{}".to_vec()),
                FileRecord::from_bytes("a.json", b"{}".to_vec()),
                FileRecord::from_bytes("sessions/a.json", b"{}".to_vec()),
            ],
            ..Observation::default()
        };
        for v in [obs.to_json(), obs.logical_json()] {
            let paths: Vec<&str> = v["files"]
                .as_array()
                .map(|a| a.iter().filter_map(|f| f["path"].as_str()).collect())
                .unwrap_or_default();
            assert_eq!(paths, ["a.json", "sessions/a.json", "sessions/b.json"]);
        }
    }

    #[test]
    fn observation_keys_are_in_the_documented_order() {
        let obs = Observation {
            log: vec!["[console] ready".into()],
            exit: Some(ExitRecord {
                code: Some(0),
                signal: None,
            }),
            ..Observation::default()
        };
        let v = obs.to_json();
        let keys: Vec<&String> = v
            .as_object()
            .map(|m| m.keys().collect())
            .unwrap_or_default();
        assert_eq!(keys, ["http", "engine_tape", "files", "log", "exit"]);
        assert_eq!(v["exit"], json!({"code": 0, "signal": null}));
    }
}
