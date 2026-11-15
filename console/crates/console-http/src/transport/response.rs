//! Response writers.
//!
//! Every answer starts as Python's `send_response` writes it: `HTTP/1.0 <code> <reason>`,
//! then `Server: pulsar-console/<version>` (approved deviation P-1) and `Date`, then the
//! handler's headers, then the headers of [`Handler::end_headers`](super::Handler) (the
//! donor's `end_headers` override), then the blank line. There is never a `Content-Length`
//! the handler did not give, never a chunked response encoding and never a keep-alive: a
//! body without `Content-Length` ends when the connection closes. For an HTTP/0.9 request
//! only the body is written, as Python does.
//!
//! Every write waits at most the per-operation timeout. A write that fails or times out is
//! reported as [`ClientGone`] and ends the answer: every later write returns
//! [`ClientGone::Closed`], so nothing can follow a partly sent frame. The handler then
//! returns without answering, as the donor's handler leaves on the exception.
//!
//! Behavior reference: project-maya serve/server.py:5403-5415 (`protocol_version`,
//! `send_response`), 5457-5463 (`_json`), 5628-5633 (`_ndjson_start`), 5964-5970 (the
//! redirect), 6152-6158 (`_fail`) and 6463-6474 (`_sse`) at 7e68a30f.

use std::fmt;
use std::io;
use std::time::Duration;

use tokio::io::AsyncWriteExt;
use tokio::net::tcp::OwnedWriteHalf;

use super::wire::{latin1, reason_phrase, ErrorPage, ERROR_CONTENT_TYPE, PROTOCOL, SERVER_HEADER};
use crate::error::{fail, AnswerState, ApiError, FailAction, LOG_PREFIX};

/// A write that did not reach the client.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ClientGone {
    /// The connection failed (closed or reset by the client, broken pipe).
    Disconnected,
    /// One write or read waited longer than the per-operation timeout.
    TimedOut,
    /// This server ended the answer: an error after the answer had begun (the donor's
    /// `_fail`), or a header that Latin-1 cannot carry.
    Closed,
}

impl fmt::Display for ClientGone {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(match self {
            ClientGone::Disconnected => "the client went away",
            ClientGone::TimedOut => "a socket operation timed out",
            ClientGone::Closed => "the answer was ended by the server",
        })
    }
}

impl std::error::Error for ClientGone {}

/// The writing side of one connection.
#[derive(Debug)]
pub struct Responder {
    writer: OwnedWriteHalf,
    timeout: Duration,
    http09: bool,
    extra_headers: Vec<(String, String)>,
    state: AnswerState,
    closed: bool,
}

impl Responder {
    /// A writer over `writer`. `http09` writes bodies only; `extra_headers` go last in every
    /// head (the router's CORS headers, for example).
    pub(crate) fn new(
        writer: OwnedWriteHalf,
        timeout: Duration,
        http09: bool,
        extra_headers: Vec<(String, String)>,
    ) -> Self {
        Self {
            writer,
            timeout,
            http09,
            extra_headers,
            state: AnswerState::new(),
            closed: false,
        }
    }

    /// True once a status line has been written (the donor's `answer_started`).
    pub fn is_started(&self) -> bool {
        self.state.is_started()
    }

    /// Whether `TCP_NODELAY` is set on the connection.
    pub fn nodelay(&self) -> io::Result<bool> {
        self.writer.as_ref().nodelay()
    }

    /// Writes the status line, `Server`, `Date`, `headers`, the end-headers hook's headers
    /// and the blank line. The answer has begun afterwards, even when the write fails.
    pub async fn start(&mut self, code: u16, headers: &[(&str, &str)]) -> Result<(), ClientGone> {
        let head = self.head(code, reason_phrase(code), headers)?;
        self.write_all(&head).await
    }

    /// [`start`](Self::start) and `body` in one write.
    pub async fn send(
        &mut self,
        code: u16,
        headers: &[(&str, &str)],
        body: &[u8],
    ) -> Result<(), ClientGone> {
        let mut bytes = self.head(code, reason_phrase(code), headers)?;
        bytes.extend_from_slice(body);
        self.write_all(&bytes).await
    }

    /// The donor's `_json`: `Content-Type: application/json` and `Content-Length`, then
    /// `body`, which the caller wrote with `console_pyjson`.
    pub async fn json(&mut self, code: u16, body: &str) -> Result<(), ClientGone> {
        let length = body.len().to_string();
        self.send(
            code,
            &[
                ("Content-Type", "application/json"),
                ("Content-Length", &length),
            ],
            body.as_bytes(),
        )
        .await
    }

    /// A body with its `Content-Type` and `Content-Length`.
    pub async fn text(
        &mut self,
        code: u16,
        content_type: &str,
        body: &[u8],
    ) -> Result<(), ClientGone> {
        let length = body.len().to_string();
        self.send(
            code,
            &[("Content-Type", content_type), ("Content-Length", &length)],
            body,
        )
        .await
    }

    /// `302` with `Location` and `Content-Length: 0`.
    pub async fn redirect(&mut self, location: &str) -> Result<(), ClientGone> {
        self.send(302, &[("Location", location), ("Content-Length", "0")], b"")
            .await
    }

    /// The donor's `_fail` for `error`: the error's JSON answer while nothing was sent;
    /// once the answer has begun, only the line `[console] request failed mid-answer:
    /// <message>` on standard error, and the answer is ended (later writes return
    /// [`ClientGone::Closed`]).
    pub async fn error(&mut self, error: &ApiError) -> Result<(), ClientGone> {
        match fail(&self.state, error) {
            FailAction::Respond(response) => {
                let headers = response.headers();
                let pairs: Vec<(&str, &str)> =
                    headers.iter().map(|(k, v)| (*k, v.as_str())).collect();
                self.send(response.status, &pairs, response.body.as_bytes())
                    .await
            }
            FailAction::LogAndClose(line) => {
                eprintln!("{line}");
                self.closed = true;
                Ok(())
            }
        }
    }

    /// The donor's `_sse`: sets `TCP_NODELAY` (small frames are flushed as they come; a
    /// failure to set it is ignored), then `200` with `Content-Type: text/event-stream` and
    /// `Cache-Control: no-cache` and no `Content-Length`. Frames follow through the sink.
    pub async fn sse_start(&mut self) -> Result<FrameSink<'_>, ClientGone> {
        // As the donor: an OSError from setsockopt is ignored.
        let _ = self.writer.as_ref().set_nodelay(true);
        self.start(
            200,
            &[
                ("Content-Type", "text/event-stream"),
                ("Cache-Control", "no-cache"),
            ],
        )
        .await?;
        Ok(FrameSink { responder: self })
    }

    /// The donor's `_ndjson_start`: `200` with `Content-Type: application/x-ndjson` and
    /// `Cache-Control: no-cache`; lines follow through the sink.
    pub async fn ndjson_start(&mut self) -> Result<FrameSink<'_>, ClientGone> {
        self.start(
            200,
            &[
                ("Content-Type", "application/x-ndjson"),
                ("Cache-Control", "no-cache"),
            ],
        )
        .await?;
        Ok(FrameSink { responder: self })
    }

    /// A sink for body bytes after a head written with [`start`](Self::start).
    pub fn frames(&mut self) -> FrameSink<'_> {
        FrameSink { responder: self }
    }

    /// Writes body bytes as they are, within the timeout.
    pub async fn write_body(&mut self, bytes: &[u8]) -> Result<(), ClientGone> {
        self.write_all(bytes).await
    }

    /// Python's `send_error(code, message, explain)`: the page's reason in the status line,
    /// `Server`, `Date`, `Connection: close`, the HTML type and length, the hook headers,
    /// and the page (no body for a `HEAD` request).
    pub(crate) async fn error_page(
        &mut self,
        page: &ErrorPage,
        method: Option<&str>,
    ) -> Result<(), ClientGone> {
        let body = page.body();
        let length = body.as_ref().map(|b| b.len().to_string());
        let mut headers: Vec<(&str, &str)> = vec![("Connection", "close")];
        if let Some(length) = length.as_deref() {
            headers.push(("Content-Type", ERROR_CONTENT_TYPE));
            headers.push(("Content-Length", length));
        }
        let mut bytes = self.head(page.code, &page.reason(), &headers)?;
        if method != Some("HEAD") {
            if let Some(body) = body {
                bytes.extend_from_slice(&body);
            }
        }
        self.write_all(&bytes).await
    }

    /// The bytes of a head, or nothing for HTTP/0.9. Marks the answer begun.
    fn head(
        &mut self,
        code: u16,
        reason: &str,
        headers: &[(&str, &str)],
    ) -> Result<Vec<u8>, ClientGone> {
        self.state.mark_started();
        if self.closed {
            return Err(ClientGone::Closed);
        }
        if self.http09 {
            return Ok(Vec::new());
        }
        let mut text = format!(
            "{PROTOCOL} {code} {reason}\r\nServer: {SERVER_HEADER}\r\nDate: {}\r\n",
            super::wire::http_date_now()
        );
        for (name, value) in headers {
            text.push_str(&format!("{name}: {value}\r\n"));
        }
        for (name, value) in &self.extra_headers {
            text.push_str(&format!("{name}: {value}\r\n"));
        }
        text.push_str("\r\n");
        match latin1(&text) {
            Some(bytes) => Ok(bytes),
            None => {
                // Python's send_header raises UnicodeEncodeError before anything is sent;
                // the connection then closes with no answer.
                eprintln!(
                    "{LOG_PREFIX} a response header is not Latin-1; the connection is closed"
                );
                self.closed = true;
                Err(ClientGone::Closed)
            }
        }
    }

    async fn write_all(&mut self, bytes: &[u8]) -> Result<(), ClientGone> {
        if self.closed {
            return Err(ClientGone::Closed);
        }
        match tokio::time::timeout(self.timeout, self.writer.write_all(bytes)).await {
            Ok(Ok(())) => Ok(()),
            Err(_) => {
                self.closed = true;
                Err(ClientGone::TimedOut)
            }
            Ok(Err(_)) => {
                self.closed = true;
                Err(ClientGone::Disconnected)
            }
        }
    }
}

/// The raw frame sink of a stream: each frame is written and sent as it comes. A failed
/// write is [`ClientGone`].
#[derive(Debug)]
pub struct FrameSink<'a> {
    responder: &'a mut Responder,
}

impl FrameSink<'_> {
    /// Writes one frame (for SSE, the whole `data: ...\n\n` or `: keep-alive\n\n` bytes).
    pub async fn send(&mut self, frame: &[u8]) -> Result<(), ClientGone> {
        self.responder.write_all(frame).await
    }
}

#[cfg(test)]
mod tests {
    // Provenance: translated from project-maya serve/test_server.py::NoDelayStreaming::test_sse_sets_tcp_nodelay at 7e68a30f (MIT); license text in console/LICENSES/project-maya-MIT.txt.

    use super::*;
    use tokio::io::AsyncReadExt;
    use tokio::net::{TcpListener, TcpStream};

    async fn pair() -> (Responder, TcpStream) {
        let listener = TcpListener::bind("127.0.0.1:0").await.expect("bind");
        let addr = listener.local_addr().expect("addr");
        let client = TcpStream::connect(addr).await.expect("connect");
        let (conn, _) = listener.accept().await.expect("accept");
        let (_read, write) = conn.into_split();
        (
            Responder::new(write, Duration::from_secs(5), false, Vec::new()),
            client,
        )
    }

    async fn received(responder: Responder, mut client: TcpStream) -> String {
        drop(responder);
        let mut raw = Vec::new();
        let _ = client.read_to_end(&mut raw).await;
        String::from_utf8_lossy(&raw).into_owned()
    }

    fn without_date(text: &str) -> String {
        text.lines()
            .filter(|l| !l.starts_with("Date: "))
            .collect::<Vec<_>>()
            .join("\n")
    }

    // Donor: serve/test_server.py::NoDelayStreaming::test_sse_sets_tcp_nodelay
    #[tokio::test]
    async fn sse_sets_tcp_nodelay() {
        let (mut responder, client) = pair().await;
        assert!(
            !responder.nodelay().expect("getsockopt"),
            "accepted sockets start without TCP_NODELAY"
        );
        let started = responder.sse_start().await.is_ok();
        assert!(started);
        assert!(
            responder.nodelay().expect("getsockopt"),
            "_sse sets TCP_NODELAY"
        );
        let text = received(responder, client).await;
        assert_eq!(
            without_date(&text),
            format!(
                "HTTP/1.0 200 OK\nServer: pulsar-console/{}\nContent-Type: text/event-stream\n\
                 Cache-Control: no-cache\n",
                env!("CARGO_PKG_VERSION")
            )
        );
    }

    #[tokio::test]
    async fn json_and_extra_headers_keep_the_donors_order() {
        let (write, client) = pair().await;
        let mut responder = Responder {
            extra_headers: vec![("Vary".into(), "Origin".into())],
            ..write
        };
        assert!(responder.json(201, "{\"a\": 1}").await.is_ok());
        assert!(responder.is_started());
        let text = received(responder, client).await;
        let lines: Vec<&str> = text.split("\r\n").collect();
        assert_eq!(lines.first(), Some(&"HTTP/1.0 201 Created"));
        assert_eq!(
            lines.get(1).copied(),
            Some(SERVER_HEADER)
                .map(|s| format!("Server: {s}"))
                .as_deref()
        );
        assert!(lines
            .get(2)
            .is_some_and(|l| l.starts_with("Date: ") && l.ends_with(" GMT")));
        assert_eq!(
            &lines[3..],
            [
                "Content-Type: application/json",
                "Content-Length: 8",
                "Vary: Origin",
                "",
                "{\"a\": 1}"
            ]
        );
    }

    #[tokio::test]
    async fn an_error_after_the_answer_began_only_closes() {
        let (mut responder, client) = pair().await;
        assert!(responder.ndjson_start().await.is_ok());
        assert_eq!(responder.error(&ApiError::validation("late")).await, Ok(()));
        assert_eq!(responder.write_body(b"more").await, Err(ClientGone::Closed));
        let text = received(responder, client).await;
        assert!(
            text.contains("Content-Type: application/x-ndjson\r\nCache-Control: no-cache\r\n\r\n")
        );
        assert!(
            text.ends_with("\r\n\r\n"),
            "nothing after the head: {text:?}"
        );
    }

    #[tokio::test]
    async fn a_failed_write_ends_the_answer() {
        let (mut responder, client) = pair().await;
        assert!(client.set_zero_linger().is_ok());
        drop(client);
        // The reset arrives after a write or two; the first failure is Disconnected.
        let mut failure = None;
        for _ in 0..200 {
            if let Err(e) = responder.write_body(&[b'x'; 4096]).await {
                failure = Some(e);
                break;
            }
            tokio::time::sleep(Duration::from_millis(5)).await;
        }
        assert_eq!(failure, Some(ClientGone::Disconnected));
        assert_eq!(responder.write_body(b"next").await, Err(ClientGone::Closed));
        assert_eq!(responder.frames().send(b"x").await, Err(ClientGone::Closed));
    }

    #[tokio::test]
    async fn a_timed_out_write_ends_the_answer() {
        let (write, client) = pair().await;
        let mut responder = Responder {
            timeout: Duration::from_millis(200),
            ..write
        };
        // The client never reads: the socket buffers fill and a write times out.
        let chunk = vec![b'x'; 1 << 20];
        let mut failure = None;
        for _ in 0..256 {
            if let Err(e) = responder.write_body(&chunk).await {
                failure = Some(e);
                break;
            }
        }
        assert_eq!(failure, Some(ClientGone::TimedOut));
        assert_eq!(responder.write_body(b"next").await, Err(ClientGone::Closed));
        drop(client);
    }

    #[tokio::test]
    async fn a_header_beyond_latin1_closes_without_an_answer() {
        let (mut responder, client) = pair().await;
        assert_eq!(
            responder.send(200, &[("X", "\u{2603}")], b"x").await,
            Err(ClientGone::Closed)
        );
        assert_eq!(received(responder, client).await, "");
    }

    #[tokio::test]
    async fn http09_writes_the_body_only() {
        let (write, client) = pair().await;
        let mut responder = Responder {
            http09: true,
            ..write
        };
        assert!(responder.redirect("./").await.is_ok());
        assert!(responder.text(200, "text/plain", b"plain").await.is_ok());
        assert_eq!(received(responder, client).await, "plain");
    }
}
