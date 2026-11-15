//! Owned by CNF-03. The raw HTTP client, with HTTP/1.0 and HTTP/1.1 request modes and
//! disconnect control.
//!
//! The client sends the bytes of a [`RawRequest`] exactly as built, over one plain
//! `std::net` TCP connection per request, and records everything that comes back as an
//! [`Exchange`]: interim and final heads with headers in order, the body de-framed from
//! Content-Length, chunked or close-delimited framing (the framing kept as metadata), the
//! body parsed by its media type, and every byte received. A malformed request is sent as
//! written ([`RawRequest::raw`]); a malformed or truncated answer is recorded, not
//! refused, so a robustness test can see what the server did.
//!
//! A [`Disconnect`] stops the read exactly at its trigger: after the request is sent,
//! after N stream events (SSE events or NDJSON lines), or after N bytes received. It
//! then either closes the socket or half-closes it (shuts down the client's sending
//! side) and reads on to the end. The donor treats both as the client going away: its
//! client watch reads end of file or a reset as gone. Bytes past an event trigger that
//! arrived in the same read stay in [`Exchange::wire`] and never reach the body or the
//! parsed events, so the observation of a disconnect does not depend on read timing.
//!
//! The client is usable alone ([`Client::exchange`]) or driven by a scenario step
//! ([`Client::run_step`], [`RawRequest::from_scenario`]). It has no async runtime and no
//! dependency on any console crate: it observes a server only from outside. Every size
//! it holds is bounded ([`ReadLimits`], [`MAX_REQUEST_BYTES`]), and every write and read
//! has a timeout and the deadline of the exchange ([`ClientConfig`]). A duration too large
//! for the clock (such as `Duration::MAX`) is held at [`MAX_WAIT`]; a zero duration is
//! held at one millisecond.
//!
//! Behavior reference: project-maya serve/server.py:5404-5406 (protocol_version
//! HTTP/1.0: a stream ends by closing the connection) and 5019-5044 (watch_client: end
//! of file or a reset from the client cancels the request) at 7e68a30f; the donor tests'
//! raw-socket helpers in serve/test_server.py:2055-2070 and 2384-2390 at 7e68a30f.

pub mod encode;
mod read;

use std::io::{ErrorKind, Read, Write};
use std::net::{Shutdown, SocketAddr, TcpStream};
use std::path::{Component, Path};
use std::time::{Duration, Instant};

use crate::observe::{DisconnectRecord, End, Exchange};
use crate::scenario::{self, Body, HttpVersion, Request, Step};

use read::{Fed, Reader};

pub use encode::py_json_dumps;

/// The largest request the client sends, in bytes.
pub const MAX_REQUEST_BYTES: usize = 64 * 1024 * 1024 + 64 * 1024;

/// The largest single read from the socket.
const READ_CHUNK: usize = 16 * 1024;

/// The longest any configured duration is taken to be (about thirty days). A larger value,
/// such as `Duration::MAX` to mean no deadline, is held at this one, so that adding it to
/// the clock cannot overflow and the socket accepts it as a timeout.
pub const MAX_WAIT: Duration = Duration::from_secs(30 * 24 * 3600);

/// The shortest timeout set on the socket (the socket refuses a zero timeout).
const MIN_WAIT: Duration = Duration::from_millis(1);

/// A configured duration, held between [`MIN_WAIT`] and [`MAX_WAIT`].
fn bounded(d: Duration) -> Duration {
    d.clamp(MIN_WAIT, MAX_WAIT)
}

/// The instant `d` after `start`, with `d` held at [`MAX_WAIT`]; never panics.
fn instant_after(start: Instant, d: Duration) -> Instant {
    start
        .checked_add(d.min(MAX_WAIT))
        .or_else(|| start.checked_add(Duration::from_secs(3600)))
        .unwrap_or(start)
}

/// What ends the read early.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Trigger {
    /// As soon as the request has been sent, before any byte is read.
    AfterRequest,
    /// Once this many stream events have been recorded: SSE events for
    /// `text/event-stream`, complete lines for `application/x-ndjson`. Zero fires as soon
    /// as the final head of such a stream is read. Never fires for another media type
    /// (zero included), nor for an answer without a body.
    AfterEvents(u64),
    /// Once this many bytes have been received, head included. The read is sized so that
    /// exactly this many are received.
    AfterBytes(u64),
}

/// What the client does when the trigger fires.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DisconnectMode {
    /// Close the socket and stop reading.
    Close,
    /// Shut down the sending side (the server reads end of file) and read on to the end.
    HalfClose,
}

/// A disconnect: when, and how.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Disconnect {
    /// When.
    pub trigger: Trigger,
    /// How.
    pub mode: DisconnectMode,
}

impl Disconnect {
    /// Close after `n` stream events.
    pub fn after_events(n: u64) -> Self {
        Self {
            trigger: Trigger::AfterEvents(n),
            mode: DisconnectMode::Close,
        }
    }

    /// Close after `n` bytes received.
    pub fn after_bytes(n: u64) -> Self {
        Self {
            trigger: Trigger::AfterBytes(n),
            mode: DisconnectMode::Close,
        }
    }

    /// Close as soon as the request is sent.
    pub fn after_request() -> Self {
        Self {
            trigger: Trigger::AfterRequest,
            mode: DisconnectMode::Close,
        }
    }

    /// The same trigger, half-closing instead of closing.
    pub fn half_close(self) -> Self {
        Self {
            mode: DisconnectMode::HalfClose,
            ..self
        }
    }
}

impl From<scenario::Disconnect> for Disconnect {
    fn from(d: scenario::Disconnect) -> Self {
        match d {
            scenario::Disconnect::AfterEvents(n) => Self::after_events(n),
            scenario::Disconnect::AfterBytes(n) => Self::after_bytes(n),
        }
    }
}

/// Bounds on what one response may make the client hold.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ReadLimits {
    /// The largest response head (and each interim head), in bytes.
    pub max_head_bytes: usize,
    /// The most headers in one head.
    pub max_headers: usize,
    /// The most interim (1xx) heads.
    pub max_interim: usize,
    /// The most bytes received in all.
    pub max_wire_bytes: usize,
    /// The largest de-framed body.
    pub max_body_bytes: usize,
    /// The most stream events recorded.
    pub max_events: usize,
    /// The most non-blank SSE lines (comments and field lines) read.
    pub max_lines: usize,
    /// The longest chunk-size or trailer line.
    pub max_chunk_line: usize,
    /// The most chunks.
    pub max_chunks: usize,
    /// The most trailer fields.
    pub max_trailers: usize,
}

impl Default for ReadLimits {
    fn default() -> Self {
        Self {
            max_head_bytes: 64 * 1024,
            max_headers: 128,
            max_interim: 8,
            max_wire_bytes: 72 * 1024 * 1024,
            max_body_bytes: 64 * 1024 * 1024,
            max_events: 1_000_000,
            max_lines: 2_000_000,
            max_chunk_line: 4096,
            max_chunks: 4_000_000,
            max_trailers: 64,
        }
    }
}

/// Timeouts and limits of a client.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ClientConfig {
    /// The connect timeout.
    pub connect_timeout: Duration,
    /// The longest wait for the next byte, and for one write of the request to progress.
    pub read_timeout: Duration,
    /// The longest whole exchange, from connect through the request write to the end of
    /// the read.
    pub deadline: Duration,
    /// After a body complete by Content-Length or chunked framing, how long to wait for
    /// the server to close the connection (recorded as [`Exchange::server_closed`]).
    /// Zero skips the check.
    pub close_wait: Duration,
    /// The read limits.
    pub limits: ReadLimits,
}

impl Default for ClientConfig {
    fn default() -> Self {
        Self {
            connect_timeout: Duration::from_secs(10),
            read_timeout: Duration::from_secs(30),
            deadline: Duration::from_secs(120),
            close_wait: Duration::from_secs(2),
            limits: ReadLimits::default(),
        }
    }
}

/// Why a request could not be sent.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ClientError {
    /// The request could not be built; the value says why.
    InvalidRequest(String),
    /// A body file could not be read.
    BodyFile(String),
    /// The connection could not be made; the value is the error kind.
    Connect(String),
}

impl std::fmt::Display for ClientError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ClientError::InvalidRequest(why) => write!(f, "invalid request: {why}"),
            ClientError::BodyFile(why) => write!(f, "body file: {why}"),
            ClientError::Connect(kind) => write!(f, "connect failed: {kind}"),
        }
    }
}

impl std::error::Error for ClientError {}

/// The bytes of one request, sent as they are.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RawRequest {
    bytes: Vec<u8>,
    head_method: bool,
}

impl RawRequest {
    /// A request written out whole, sent byte for byte. Nothing is checked or added, so a
    /// malformed request reaches the server as written. A request whose first word is
    /// `HEAD` is read as an answer without a body.
    pub fn raw(bytes: impl Into<Vec<u8>>) -> Result<Self, ClientError> {
        let bytes = bytes.into();
        if bytes.len() > MAX_REQUEST_BYTES {
            return Err(ClientError::InvalidRequest(
                "larger than the request limit".into(),
            ));
        }
        let head_method = bytes.starts_with(b"HEAD ");
        Ok(Self { bytes, head_method })
    }

    /// The bytes sent.
    pub fn bytes(&self) -> &[u8] {
        &self.bytes
    }

    /// A request built from a scenario request. `host` is the value of the `Host` header
    /// added when the request has none (see [`RequestBuilder`]); `base_dir` is the
    /// directory a `body_file` is read from. A raw scenario request is sent as written.
    pub fn from_scenario(
        req: &Request,
        host: &str,
        base_dir: Option<&Path>,
    ) -> Result<Self, ClientError> {
        let s = match req {
            Request::Raw(text) => return Self::raw(text.as_bytes()),
            Request::Structured(s) => s,
        };
        let mut b = RequestBuilder::new(&s.method, &s.path)
            .version(s.http_version)
            .host(host);
        for (name, value) in &s.headers {
            b = b.header(name, value);
        }
        b = match &s.body {
            Body::None => b,
            Body::Json(v) => b.json(v)?,
            Body::Text(t) => b.body(t.as_bytes()),
            Body::File(rel) => b.body(read_body_file(base_dir, rel)?),
        };
        b.build()
    }
}

/// Reads a scenario's body file, bounded, refusing a path that leaves `base_dir`, that
/// passes through a symbolic link, or that does not name a regular file.
fn read_body_file(base_dir: Option<&Path>, rel: &str) -> Result<Vec<u8>, ClientError> {
    let Some(base) = base_dir else {
        return Err(ClientError::BodyFile(
            "no scenario directory to read it from".into(),
        ));
    };
    let path = Path::new(rel);
    if !path.components().all(|c| matches!(c, Component::Normal(_))) {
        return Err(ClientError::BodyFile(format!(
            "{rel:?} is not a plain relative path"
        )));
    }
    let file = crate::observe::open_inside(base, path)
        .map_err(|e| ClientError::BodyFile(format!("{rel}: {:?}", e.kind())))?;
    let limit = MAX_REQUEST_BYTES;
    let mut bytes = Vec::new();
    file.take(u64::try_from(limit).unwrap_or(u64::MAX) + 1)
        .read_to_end(&mut bytes)
        .map_err(|e| ClientError::BodyFile(format!("{rel}: {:?}", e.kind())))?;
    if bytes.len() > limit {
        return Err(ClientError::BodyFile(format!(
            "{rel}: larger than the request limit"
        )));
    }
    Ok(bytes)
}

/// Builds a well-formed request: the request line, then a `Host` header when one is set
/// with [`RequestBuilder::host`] and the headers have none, then the headers in the
/// order given (duplicates kept), then `Content-Length` when there is a body and the
/// headers have neither `Content-Length` nor `Transfer-Encoding`, then the blank line and
/// the body. Nothing else is added: no `Connection`, no `User-Agent`, no
/// `Accept-Encoding`. A JSON body is written as Python's `json.dumps` writes it
/// ([`py_json_dumps`]), as the donor's tests send it.
#[derive(Debug, Clone)]
pub struct RequestBuilder {
    method: String,
    target: String,
    version: HttpVersion,
    host: Option<String>,
    headers: Vec<(String, String)>,
    body: Option<Vec<u8>>,
    content_length: bool,
}

impl RequestBuilder {
    /// A request with this method and target, HTTP/1.1, no headers and no body.
    pub fn new(method: &str, target: &str) -> Self {
        Self {
            method: method.to_string(),
            target: target.to_string(),
            version: HttpVersion::V1_1,
            host: None,
            headers: Vec::new(),
            body: None,
            content_length: true,
        }
    }

    /// The version of the request line.
    pub fn version(mut self, version: HttpVersion) -> Self {
        self.version = version;
        self
    }

    /// The `Host` value added when the headers have no `Host`.
    pub fn host(mut self, host: &str) -> Self {
        self.host = Some(host.to_string());
        self
    }

    /// Adds a header (kept in order, duplicates kept).
    pub fn header(mut self, name: &str, value: &str) -> Self {
        self.headers.push((name.to_string(), value.to_string()));
        self
    }

    /// The body bytes.
    pub fn body(mut self, bytes: impl Into<Vec<u8>>) -> Self {
        self.body = Some(bytes.into());
        self
    }

    /// A JSON body, written as Python's `json.dumps(value)`.
    pub fn json(self, value: &serde_json::Value) -> Result<Self, ClientError> {
        let text = py_json_dumps(value).map_err(ClientError::InvalidRequest)?;
        Ok(self.body(text.into_bytes()))
    }

    /// Do not add `Content-Length`.
    pub fn without_content_length(mut self) -> Self {
        self.content_length = false;
        self
    }

    /// The request bytes. Fails when the method, target or a header holds a byte that
    /// would end the line early (CR, LF or NUL), when a header name is empty or holds a
    /// space or colon, or when the request is larger than [`MAX_REQUEST_BYTES`]. Use
    /// [`RawRequest::raw`] for a request that must be malformed.
    pub fn build(self) -> Result<RawRequest, ClientError> {
        let bad = |s: &str| s.bytes().any(|b| matches!(b, b'\r' | b'\n' | 0));
        if self.method.is_empty() || self.method.bytes().any(|b| b <= b' ') {
            return Err(ClientError::InvalidRequest("method".into()));
        }
        if self.target.is_empty() || self.target.bytes().any(|b| b <= b' ') {
            return Err(ClientError::InvalidRequest("target".into()));
        }
        for (name, value) in &self.headers {
            if name.is_empty() || bad(name) || name.bytes().any(|b| b <= b' ' || b == b':') {
                return Err(ClientError::InvalidRequest(format!("header name {name:?}")));
            }
            if bad(value) {
                return Err(ClientError::InvalidRequest(format!(
                    "value of header {name}"
                )));
            }
        }
        if self.host.as_deref().is_some_and(bad) {
            return Err(ClientError::InvalidRequest("host".into()));
        }
        let has = |n: &str| self.headers.iter().any(|(k, _)| k.eq_ignore_ascii_case(n));
        let version = match self.version {
            HttpVersion::V1_0 => "HTTP/1.0",
            HttpVersion::V1_1 => "HTTP/1.1",
        };
        let mut out = format!("{} {} {}\r\n", self.method, self.target, version).into_bytes();
        if let Some(host) = &self.host {
            if !has("host") {
                out.extend_from_slice(format!("Host: {host}\r\n").as_bytes());
            }
        }
        for (name, value) in &self.headers {
            out.extend_from_slice(format!("{name}: {value}\r\n").as_bytes());
        }
        if let Some(body) = &self.body {
            if self.content_length && !has("content-length") && !has("transfer-encoding") {
                out.extend_from_slice(format!("Content-Length: {}\r\n", body.len()).as_bytes());
            }
        }
        out.extend_from_slice(b"\r\n");
        if let Some(body) = self.body {
            out.extend_from_slice(&body);
        }
        let head_method = self.method == "HEAD";
        let mut req = RawRequest::raw(out)?;
        req.head_method = head_method;
        Ok(req)
    }
}

/// A client for one server address.
#[derive(Debug, Clone)]
pub struct Client {
    addr: SocketAddr,
    config: ClientConfig,
}

impl Client {
    /// A client for `addr` with the default configuration.
    pub fn new(addr: SocketAddr) -> Self {
        Self::with_config(addr, ClientConfig::default())
    }

    /// A client for `addr` with `config`.
    pub fn with_config(addr: SocketAddr, config: ClientConfig) -> Self {
        Self { addr, config }
    }

    /// The server address.
    pub fn addr(&self) -> SocketAddr {
        self.addr
    }

    /// The configuration.
    pub fn config(&self) -> &ClientConfig {
        &self.config
    }

    /// The `Host` value for this address, as Python's `http.client` writes it:
    /// `127.0.0.1:8080`, or `[::1]:8080` for IPv6.
    pub fn host_header(&self) -> String {
        self.addr.to_string()
    }

    /// A [`RequestBuilder`] with this client's `Host` value.
    pub fn request(&self, method: &str, target: &str) -> RequestBuilder {
        RequestBuilder::new(method, target).host(&self.host_header())
    }

    /// Connects and sends the request; the response is read later with
    /// [`InFlight::read`]. A write that fails part way, or that the deadline cuts short
    /// (recorded as `TimedOut`), is recorded with the count of bytes sent, not returned:
    /// the server may have answered before reading the whole request.
    pub fn send(&self, req: &RawRequest) -> Result<InFlight, ClientError> {
        let started = Instant::now();
        let deadline = instant_after(started, self.config.deadline);
        let stream = TcpStream::connect_timeout(&self.addr, bounded(self.config.connect_timeout))
            .map_err(|e| ClientError::Connect(format!("{:?}", e.kind())))?;
        let _ = stream.set_nodelay(true);
        let bytes = req.bytes();
        let mut sent = 0usize;
        let write_error = loop {
            let Some(rest) = bytes.get(sent..).filter(|r| !r.is_empty()) else {
                break None;
            };
            let now = Instant::now();
            if now >= deadline {
                break Some(format!("{:?}", ErrorKind::TimedOut));
            }
            let wait = bounded(self.config.read_timeout.min(deadline - now));
            let _ = stream.set_write_timeout(Some(wait));
            match (&stream).write(rest) {
                Ok(0) => break Some(format!("{:?}", ErrorKind::WriteZero)),
                Ok(n) => sent += n,
                Err(e) if e.kind() == ErrorKind::Interrupted => {}
                Err(e)
                    if matches!(e.kind(), ErrorKind::WouldBlock | ErrorKind::TimedOut)
                        && Instant::now() >= deadline =>
                {
                    break Some(format!("{:?}", ErrorKind::TimedOut));
                }
                Err(e) => break Some(format!("{:?}", e.kind())),
            }
        };
        Ok(InFlight {
            stream,
            request: bytes.to_vec(),
            request_sent: sent as u64,
            head_method: req.head_method,
            write_error,
            config: self.config,
            started,
        })
    }

    /// Sends the request and reads the response, disconnecting as asked.
    pub fn exchange(
        &self,
        req: &RawRequest,
        disconnect: Option<Disconnect>,
    ) -> Result<Exchange, ClientError> {
        Ok(self.send(req)?.read(disconnect))
    }

    /// Runs the request of a scenario step, with the step's disconnect. Returns `None`
    /// for a step without a request (a gate or a signal, which the runner handles).
    /// `base_dir` is the scenario's directory, for a `body_file`.
    pub fn run_step(
        &self,
        step: &Step,
        base_dir: Option<&Path>,
    ) -> Result<Option<Exchange>, ClientError> {
        let Some(req) = &step.request else {
            return Ok(None);
        };
        let raw = RawRequest::from_scenario(req, &self.host_header(), base_dir)?;
        self.exchange(&raw, step.disconnect.map(Disconnect::from))
            .map(Some)
    }
}

/// A request sent, its response not yet read.
#[derive(Debug)]
pub struct InFlight {
    stream: TcpStream,
    request: Vec<u8>,
    request_sent: u64,
    head_method: bool,
    write_error: Option<String>,
    config: ClientConfig,
    started: Instant,
}

impl InFlight {
    /// The local address of the connection.
    pub fn local_addr(&self) -> Option<SocketAddr> {
        self.stream.local_addr().ok()
    }

    /// Reads the response, disconnecting as asked, and returns the record.
    pub fn read(self, disconnect: Option<Disconnect>) -> Exchange {
        let InFlight {
            stream,
            request,
            request_sent,
            head_method,
            write_error,
            config,
            started,
        } = self;
        let limits = config.limits;
        let stop_at = match disconnect.map(|d| d.trigger) {
            Some(Trigger::AfterEvents(n)) => Some(usize::try_from(n).unwrap_or(usize::MAX)),
            _ => None,
        };
        let mut byte_limit = match disconnect.map(|d| d.trigger) {
            Some(Trigger::AfterBytes(n)) => Some(n),
            _ => None,
        };
        let mut reader = Reader::new(limits, head_method, stop_at);
        let mut wire: Vec<u8> = Vec::new();
        let mut record = disconnect.map(|asked| DisconnectRecord {
            asked,
            fired: false,
            wire_bytes: 0,
            body_bytes: 0,
            events: 0,
        });
        let mut server_closed = None;
        let mut buf = vec![0u8; READ_CHUNK];
        let deadline = instant_after(started, config.deadline);
        let mut open = true;

        let fire = |record: &mut Option<DisconnectRecord>, reader: &Reader, wire: &[u8]| {
            if let Some(r) = record.as_mut() {
                r.fired = true;
                r.wire_bytes = wire.len() as u64;
                r.body_bytes = reader.body.len() as u64;
                r.events = reader.events() as u64;
            }
        };

        let mut end = 'read: {
            if let Some(d) = disconnect {
                if d.trigger == Trigger::AfterRequest || byte_limit == Some(0) {
                    fire(&mut record, &reader, &wire);
                    match d.mode {
                        DisconnectMode::Close => {
                            open = false;
                            break 'read End::Disconnected;
                        }
                        DisconnectMode::HalfClose => {
                            let _ = stream.shutdown(Shutdown::Write);
                            byte_limit = None;
                        }
                    }
                }
            }
            loop {
                let now = Instant::now();
                if now >= deadline {
                    break 'read End::Timeout;
                }
                let wait = bounded(config.read_timeout.min(deadline - now));
                let _ = stream.set_read_timeout(Some(wait));
                let mut want = buf.len();
                if let Some(n) = byte_limit {
                    let left = n.saturating_sub(wire.len() as u64);
                    want = want.min(usize::try_from(left).unwrap_or(usize::MAX));
                }
                let room = limits.max_wire_bytes.saturating_sub(wire.len());
                if room == 0 {
                    break 'read End::LimitExceeded("received bytes".into());
                }
                want = want.min(room);
                let got = match (&stream).read(&mut buf[..want]) {
                    Ok(0) => {
                        reader.eof();
                        if reader.complete() {
                            server_closed = Some(true);
                            break 'read End::Complete;
                        }
                        if reader.failure().is_some() {
                            // A malformed answer read to its end: the server closed.
                            server_closed = Some(true);
                        }
                        break 'read End::Truncated;
                    }
                    Ok(n) => n,
                    Err(e) if e.kind() == ErrorKind::Interrupted => continue,
                    Err(e) if matches!(e.kind(), ErrorKind::WouldBlock | ErrorKind::TimedOut) => {
                        break 'read End::Timeout;
                    }
                    Err(e) => break 'read End::Io(format!("{:?}", e.kind())),
                };
                let chunk = &buf[..got];
                wire.extend_from_slice(chunk);
                let mut fed = reader.feed(chunk);
                // A half-close event trigger: shut down, then feed the rest of the read.
                while let Fed::Triggered(used) = fed {
                    fire(&mut record, &reader, &wire);
                    let mode = disconnect.map_or(DisconnectMode::Close, |d| d.mode);
                    if mode == DisconnectMode::Close {
                        open = false;
                        break 'read End::Disconnected;
                    }
                    let _ = stream.shutdown(Shutdown::Write);
                    reader.clear_trigger();
                    let rest = chunk.get(used..).unwrap_or_default();
                    fed = if rest.is_empty() {
                        Fed::More
                    } else {
                        reader.feed(rest)
                    };
                }
                match fed {
                    Fed::Complete => break 'read End::Complete,
                    Fed::Failed(end) => break 'read end,
                    Fed::More | Fed::Triggered(_) => {}
                }
                if byte_limit.is_some_and(|n| wire.len() as u64 >= n) {
                    fire(&mut record, &reader, &wire);
                    match disconnect.map_or(DisconnectMode::Close, |d| d.mode) {
                        DisconnectMode::Close => {
                            open = false;
                            break 'read End::Disconnected;
                        }
                        DisconnectMode::HalfClose => {
                            let _ = stream.shutdown(Shutdown::Write);
                            byte_limit = None;
                        }
                    }
                }
            }
        };

        // A body complete by its framing: see whether the server closes the connection.
        if open && end == End::Complete && server_closed.is_none() && !config.close_wait.is_zero() {
            server_closed = Some(await_close(&stream, &mut wire, &config, deadline));
        }
        if !open {
            drop(stream);
        }
        if let Some(r) = record.as_mut() {
            if !r.fired {
                r.wire_bytes = wire.len() as u64;
                r.body_bytes = reader.body.len() as u64;
                r.events = reader.events() as u64;
            }
        }
        if end == End::Complete && !reader.has_head() {
            end = End::Truncated;
        }
        // A malformed head or chunked framing was read past to the end of the connection
        // (or the deadline): the malformation is what ended the answer, unless the client
        // disconnected or a limit stopped the read.
        if let Some(failure) = reader.failure() {
            if !matches!(end, End::Disconnected | End::LimitExceeded(_)) {
                end = failure.clone();
            }
        }
        let content = reader.content();
        Exchange {
            request,
            request_sent,
            write_error,
            interim: std::mem::take(&mut reader.interim),
            head: reader.head.take(),
            framing: reader.framing.take(),
            body: std::mem::take(&mut reader.body),
            content,
            end,
            server_closed,
            disconnect: record,
            wire,
        }
    }
}

/// Waits up to the close wait for end of file. Bytes that arrive meanwhile are kept in
/// `wire`. Returns whether the server closed (end of file or a reset).
fn await_close(
    stream: &TcpStream,
    wire: &mut Vec<u8>,
    config: &ClientConfig,
    deadline: Instant,
) -> bool {
    let until = instant_after(Instant::now(), config.close_wait);
    let mut buf = [0u8; 4096];
    loop {
        let now = Instant::now();
        let stop = until.min(deadline);
        if now >= stop {
            return false;
        }
        let _ = stream.set_read_timeout(Some(bounded(stop - now)));
        match (&*stream).read(&mut buf) {
            Ok(0) => return true,
            Ok(n) => {
                if wire.len() + n > config.limits.max_wire_bytes {
                    return false;
                }
                wire.extend_from_slice(&buf[..n]);
            }
            Err(e) if e.kind() == ErrorKind::Interrupted => {}
            Err(e) if matches!(e.kind(), ErrorKind::WouldBlock | ErrorKind::TimedOut) => {
                return false
            }
            Err(_) => return true,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn builder_adds_host_and_content_length_only() {
        let req = RequestBuilder::new("POST", "/v1/chat/completions")
            .host("127.0.0.1:9")
            .header("Content-Type", "application/json")
            .json(&json!({"model": "m", "stream": true}))
            .and_then(RequestBuilder::build)
            .map(|r| r.bytes().to_vec())
            .unwrap_or_default();
        assert_eq!(
            req,
            b"POST /v1/chat/completions HTTP/1.1\r\nHost: 127.0.0.1:9\r\n\
Content-Type: application/json\r\nContent-Length: 30\r\n\r\n{\"model\": \"m\", \"stream\": true}"
        );
    }

    #[test]
    fn builder_keeps_given_host_length_and_order() {
        let req = RequestBuilder::new("GET", "/health")
            .version(HttpVersion::V1_0)
            .host("ignored")
            .header("X-B", "2")
            .header("host", "example")
            .header("X-B", "3")
            .build()
            .map(|r| r.bytes().to_vec())
            .unwrap_or_default();
        assert_eq!(
            req,
            b"GET /health HTTP/1.0\r\nX-B: 2\r\nhost: example\r\nX-B: 3\r\n\r\n"
        );
        let req = RequestBuilder::new("POST", "/x")
            .header("Transfer-Encoding", "chunked")
            .body(&b"0\r\n\r\n"[..])
            .build()
            .map(|r| r.bytes().to_vec())
            .unwrap_or_default();
        assert_eq!(
            req,
            b"POST /x HTTP/1.1\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n"
        );
    }

    #[test]
    fn builder_refuses_line_breaking_input() {
        assert!(RequestBuilder::new("GET", "/a b").build().is_err());
        assert!(RequestBuilder::new("", "/").build().is_err());
        assert!(RequestBuilder::new("GET", "/")
            .header("X", "a\r\nY: b")
            .build()
            .is_err());
        assert!(RequestBuilder::new("GET", "/")
            .header("X Y", "a")
            .build()
            .is_err());
        assert!(RequestBuilder::new("GET", "/")
            .header("", "a")
            .build()
            .is_err());
    }

    #[test]
    fn raw_requests_are_kept_byte_for_byte() {
        let r = RawRequest::raw(&b"BLAH\r\n\r\n\x00\xff"[..]);
        assert_eq!(
            r.as_ref().map(|r| r.bytes()),
            Ok(&b"BLAH\r\n\r\n\x00\xff"[..])
        );
        assert!(RawRequest::raw(&b"HEAD / HTTP/1.0\r\n\r\n"[..]).is_ok_and(|r| r.head_method));
    }

    #[test]
    fn body_files_must_stay_inside_the_scenario_directory() {
        let base = Path::new(".");
        for rel in ["../x", "/etc/passwd", "a/../../b", "./a"] {
            assert!(read_body_file(Some(base), rel).is_err(), "{rel}");
        }
        assert!(read_body_file(None, "a").is_err());
    }

    #[test]
    fn durations_are_held_inside_what_the_clock_and_socket_accept() {
        assert_eq!(bounded(Duration::ZERO), MIN_WAIT);
        assert_eq!(bounded(Duration::MAX), MAX_WAIT);
        let now = Instant::now();
        assert!(instant_after(now, Duration::MAX) >= now + Duration::from_secs(3600));
        assert_eq!(
            instant_after(now, Duration::from_secs(5)),
            now + Duration::from_secs(5)
        );
        let listener = std::net::TcpListener::bind("127.0.0.1:0");
        let stream = listener
            .as_ref()
            .ok()
            .and_then(|l| l.local_addr().ok())
            .and_then(|a| TcpStream::connect(a).ok());
        let stream = stream.unwrap_or_else(|| panic!("loopback connect"));
        for d in [MIN_WAIT, MAX_WAIT] {
            assert!(stream.set_read_timeout(Some(d)).is_ok(), "{d:?}");
            assert!(stream.set_write_timeout(Some(d)).is_ok(), "{d:?}");
        }
    }

    /// A server for one connection that writes `answer` and closes.
    fn answer_once(answer: &'static [u8]) -> (SocketAddr, std::thread::JoinHandle<()>) {
        let listener =
            std::net::TcpListener::bind("127.0.0.1:0").unwrap_or_else(|e| panic!("bind: {e}"));
        let addr = listener
            .local_addr()
            .unwrap_or_else(|e| panic!("addr: {e}"));
        let join = std::thread::spawn(move || {
            if let Ok((mut conn, _)) = listener.accept() {
                let _ = conn.set_read_timeout(Some(Duration::from_secs(10)));
                let mut buf = [0u8; 1024];
                let _ = conn.read(&mut buf);
                let _ = conn.write_all(answer);
            }
        });
        (addr, join)
    }

    #[test]
    fn duration_max_means_no_deadline_and_does_not_panic() {
        let (addr, join) = answer_once(b"HTTP/1.0 200 OK\r\nContent-Length: 2\r\n\r\nok");
        let config = ClientConfig {
            connect_timeout: Duration::MAX,
            read_timeout: Duration::MAX,
            deadline: Duration::MAX,
            close_wait: Duration::MAX,
            ..ClientConfig::default()
        };
        let c = Client::with_config(addr, config);
        let req = c.request("GET", "/health").build();
        let ex = req.and_then(|r| c.exchange(&r, None));
        let _ = join.join();
        let ex = ex.unwrap_or_else(|e| panic!("exchange: {e}"));
        assert_eq!(ex.end, End::Complete);
        assert_eq!(ex.body, b"ok");
        assert_eq!(ex.server_closed, Some(true));
        assert_eq!(ex.request_sent, ex.request.len() as u64);
        assert_eq!(ex.write_error, None);
    }

    #[test]
    fn the_request_write_stops_at_the_deadline() {
        let listener =
            std::net::TcpListener::bind("127.0.0.1:0").unwrap_or_else(|e| panic!("bind: {e}"));
        let addr = listener
            .local_addr()
            .unwrap_or_else(|e| panic!("addr: {e}"));
        let (done_tx, done_rx) = std::sync::mpsc::channel::<()>();
        let join = std::thread::spawn(move || {
            // Accept, never read, and hold the connection until the client is done.
            let held = listener.accept();
            let _ = done_rx.recv_timeout(Duration::from_secs(30));
            drop(held);
        });
        let config = ClientConfig {
            read_timeout: Duration::from_secs(30),
            deadline: Duration::from_millis(300),
            ..ClientConfig::default()
        };
        let c = Client::with_config(addr, config);
        let req = c
            .request("POST", "/v1/chat/completions")
            .body(vec![b'x'; 48 * 1024 * 1024])
            .build()
            .unwrap_or_else(|e| panic!("build: {e}"));
        let started = Instant::now();
        let ex = c
            .exchange(&req, None)
            .unwrap_or_else(|e| panic!("exchange: {e}"));
        let elapsed = started.elapsed();
        let _ = done_tx.send(());
        let _ = join.join();
        assert!(elapsed < Duration::from_secs(10), "{elapsed:?}");
        assert_eq!(ex.write_error.as_deref(), Some("TimedOut"));
        assert!(ex.request_sent < ex.request.len() as u64);
        assert_eq!(ex.end, End::Timeout);
        assert_eq!(
            ex.to_json()["request_sent"],
            serde_json::json!(ex.request_sent)
        );
    }

    #[test]
    fn scenario_disconnects_map_to_close_triggers() {
        assert_eq!(
            Disconnect::from(scenario::Disconnect::AfterEvents(5)),
            Disconnect::after_events(5)
        );
        assert_eq!(
            Disconnect::from(scenario::Disconnect::AfterBytes(7)),
            Disconnect {
                trigger: Trigger::AfterBytes(7),
                mode: DisconnectMode::Close
            }
        );
    }
}
