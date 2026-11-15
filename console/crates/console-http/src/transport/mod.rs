//! Owned by API-02. The HTTP/1.0 transport on `tokio`: one request per connection, bodies,
//! responses and the client watcher.
//!
//! # Shape
//!
//! [`bind`] (or [`bind_host`]) opens a [`Listener`]; [`Listener::serve`] accepts
//! connections and gives each request to a [`Handler`] as an [`Exchange`]. The exchange
//! carries the parsed [`RequestHead`], reads the body on demand
//! ([`Exchange::read_body`]), writes the answer through its [`Responder`], and can hand its
//! reading side to a [`ClientWatch`] ([`Exchange::watch_client`]). When the handler's future
//! ends, the connection closes.
//!
//! The router of API-03 implements [`Handler`]: it matches [`RequestHead::route_path`],
//! applies its guards, adds its CORS headers through [`Handler::end_headers`] and refuses a
//! `Host` the allowlist does not serve through [`Handler::early_refusal`]. The
//! inference driver of API-07 reads the body, starts a [`ClientWatch`] with the request's
//! [`ControlHandle`](console_core::engine::ControlHandle), and writes through
//! [`Responder::json`], [`Responder::sse_start`] and the [`FrameSink`].
//!
//! # Parity
//!
//! The request head is read with Python's own rules (CPython 3.14 `http.server`,
//! `http.client.parse_headers` and the `email` parser), and the transport's error answers
//! are Python's HTML error pages, because what the donor accepts and refuses and the bytes
//! it sends are part of the behavior. The parser is hand-written for that reason: a strict
//! HTTP/1.1 parser such as `httparse` refuses header lines that Python accepts or skips.
//! Two answers differ from the donor by approved deviations: the `Server` header value is
//! `pulsar-console/<version>` (P-1), and a request with both `Content-Length` and a chunked
//! `Transfer-Encoding` is refused with 400 before the handler is called (P-2). The 413
//! message names `PULSAR_CONSOLE_MAX_BODY_MIB` (BRAND-1).
//!
//! Nothing here is qualified beyond synthetic backends; the transport serves whatever the
//! handler answers and admits no engine itself.
//!
//! Behavior reference: project-maya serve/server.py:5346-5372, 5403-5463, 5019-5044,
//! 6463-6474, 6715-6734, 6797-6803 and 7166-7171 at 7e68a30f.

mod body;
mod config;
mod head;
mod io;
mod response;
mod server;
mod watch;
mod wire;

use std::future::Future;
use std::net::SocketAddr;
use std::pin::Pin;

use console_core::engine::ControlHandle;
use tokio::io::BufReader;
use tokio::net::tcp::OwnedReadHalf;

use crate::error::ApiError;

pub use body::{
    has_conflicting_framing, is_chunked, too_large, BodyError, CONFLICTING_FRAMING,
    INVALID_CONTENT_LENGTH, MALFORMED_CHUNKED,
};
pub use config::{
    parse_backlog, parse_max_body_bytes, parse_request_timeout, TransportConfig, DEFAULT_BACKLOG,
    DEFAULT_MAX_BODY_MIB, DEFAULT_REQUEST_TIMEOUT_S, ENV_HTTP_BACKLOG, ENV_MAX_BODY_MIB,
    ENV_REQUEST_TIMEOUT_S, MIN_BACKLOG,
};
pub use head::{Headers, RequestHead, MAX_HEADERS, MAX_LINE};
pub use response::{ClientGone, FrameSink, Responder};
pub use server::{bind, bind_host, probe_port, Listener, SERVED_METHODS};
pub use watch::{ClientWatch, WATCH_INTERVAL};
pub use wire::{
    error_page_body, html_escape, http_date, py_repr, reason_phrase, ErrorPage, ERROR_CONTENT_TYPE,
    PROTOCOL, SERVER_HEADER,
};

/// The future a [`Handler`] returns.
pub type HandlerFuture<'a> = Pin<Box<dyn Future<Output = ()> + Send + 'a>>;

/// What the transport calls for each request. Object safe, so a router can be shared as
/// `Arc<dyn Handler>`.
pub trait Handler: Send + Sync + 'static {
    /// Serves one request. The connection closes when the future ends; an answer the
    /// handler never wrote is no answer, as in the donor.
    fn handle(&self, exchange: Exchange) -> HandlerFuture<'_>;

    /// Headers added at the end of every head written for this request, right before the
    /// blank line (the donor's `end_headers` override, where its CORS headers are added),
    /// including the transport's own 501 page and its 400 for conflicting framing (P-2).
    /// Called once, before [`handle`](Self::handle). It is also called for a 431 page, with
    /// the method, path and version and empty headers, because Python has set `self.command`
    /// and `self.path` but not `self.headers` when it sends that page; it is not called for
    /// the 400, 414 and 505 pages of the request line. The default adds none.
    fn end_headers(&self, head: &RequestHead) -> Vec<(String, String)> {
        let _ = head;
        Vec::new()
    }

    /// The early refusal of a request head, checked before the transport answers anything
    /// of its own for a parsed request. The transport calls it once per request, right
    /// after [`end_headers`](Self::end_headers) and before its 501 page for a method it
    /// does not serve and its 400 for conflicting framing (approved deviation P-2); an
    /// error is written as the answer (with the headers of `end_headers`) and the handler
    /// is not called. It exists so that the `Host` allowlist of deviation SEC-1.1 holds
    /// on those transport pages too. It is not a second dispatch path: it sees only the
    /// head and must not read the body or run route checks.
    ///
    /// It is not called for the 431 header-limit pages, which have no usable headers, nor
    /// for the 400, 414 and 505 pages of the request line. The default refuses nothing.
    fn early_refusal(&self, head: &RequestHead) -> Option<ApiError> {
        let _ = head;
        None
    }
}

/// One request and its connection.
#[derive(Debug)]
pub struct Exchange {
    head: RequestHead,
    reader: Option<BufReader<OwnedReadHalf>>,
    body_taken: bool,
    responder: Responder,
    config: TransportConfig,
    peer: SocketAddr,
    local: SocketAddr,
}

impl Exchange {
    pub(crate) fn new(
        head: RequestHead,
        reader: BufReader<OwnedReadHalf>,
        responder: Responder,
        config: TransportConfig,
        peer: SocketAddr,
        local: SocketAddr,
    ) -> Self {
        Self {
            head,
            reader: Some(reader),
            body_taken: false,
            responder,
            config,
            peer,
            local,
        }
    }

    /// The request head.
    pub fn head(&self) -> &RequestHead {
        &self.head
    }

    /// The client's address.
    pub fn peer_addr(&self) -> SocketAddr {
        self.peer
    }

    /// The address the request arrived on.
    pub fn local_addr(&self) -> SocketAddr {
        self.local
    }

    /// The transport settings.
    pub fn config(&self) -> TransportConfig {
        self.config
    }

    /// The writer of the answer.
    pub fn responder(&mut self) -> &mut Responder {
        &mut self.responder
    }

    /// The head and the writer together.
    pub fn parts(&mut self) -> (&RequestHead, &mut Responder) {
        (&self.head, &mut self.responder)
    }

    /// Reads the request body by the donor's `_body` rules (`Content-Length`, or a chunked
    /// body; the limit; approved deviation P-2). The body can be read once; afterwards, or
    /// after [`watch_client`](Self::watch_client), this returns [`BodyError::Unavailable`].
    /// A refused body leaves the connection unread; it closes after the answer.
    ///
    /// Behavior reference: project-maya serve/server.py:5416-5455 at 7e68a30f.
    pub async fn read_body(&mut self) -> Result<Vec<u8>, BodyError> {
        if self.body_taken {
            return Err(BodyError::Unavailable);
        }
        let Some(reader) = self.reader.as_mut() else {
            return Err(BodyError::Unavailable);
        };
        self.body_taken = true;
        // The reading side stays for the client watcher, which needs it.
        body::read_body(
            reader,
            self.head.headers(),
            self.config.max_body_bytes,
            self.config.request_timeout,
        )
        .await
    }

    /// Starts the client watcher on this connection: when the client closes or resets it,
    /// `control` is cancelled and the watch reports it. Read the body first; the reading
    /// side moves to the watcher. `None` when it was already given away. The watch stops
    /// when the returned value is dropped.
    pub fn watch_client(&mut self, control: ControlHandle) -> Option<ClientWatch> {
        self.reader
            .take()
            .map(|reader| ClientWatch::spawn(reader, control))
    }
}
