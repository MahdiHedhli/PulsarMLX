//! The listener and the per-connection loop.
//!
//! One accepted connection serves exactly one request and then closes (HTTP/1.0, decision
//! B1). The connection reads the request head and answers the errors of the head itself
//! (400, 414, 431, 505) with Python's HTML error page. For a parsed head it then asks the
//! handler's [`Handler::early_refusal`] (the router's `Host` allowlist, deviation SEC-1.1)
//! and writes a refusal as the answer; otherwise it answers a method the donor does not
//! serve with the 501 page, refuses a request that carries both framings with 400
//! (approved deviation P-2), and hands every other request (`GET`, `POST`, `DELETE`,
//! `OPTIONS`) to the [`Handler`]. The 431 pages are answered before the early refusal:
//! the header limit is hit before the headers are known, so there is no `Host` to check,
//! and they stay Python's pages as they are. There is no
//! access log; a client that hangs up is not logged. A panic in the handler (in
//! [`Handler::end_headers`], in the call to [`Handler::handle`] or in the future it
//! returns) closes only its connection, and the server goes on. The transport writes one
//! line, `[console] a request from <peer> failed: <message>`, after whatever the process
//! panic hook prints; with the standard hook that is the usual multi-line `thread ...
//! panicked at ...` report, which the binary may replace with its own hook. A panic in
//! [`Handler::early_refusal`] is handled the same way.
//!
//! The end-headers hook runs for the 501 page and for the 431 pages (where Python's
//! `self.command` and `self.path` are already set, with empty headers), as the donor's
//! `end_headers` override runs inside `send_error`. It does not run for the 400, 414 and
//! 505 pages of the request line, where Python's `self.path` is not set yet. With
//! `cors_origins` set, the donor's override raises there and the client gets no answer; this
//! transport answers the page. That difference is proposal P-22 in the deviation register of
//! feature 022 and awaits the owner's decision.
//!
//! Behavior reference: project-maya serve/server.py:6715-6734 (`Server`: address reuse, the
//! backlog, `handle_error`), 6797-6803 (`serve`) and 7166-7171 (the port probe) at 7e68a30f,
//! and CPython 3.14 `socketserver.TCPServer` (`allow_reuse_address`, `server_activate`,
//! `shutdown_request`).

use std::any::Any;
use std::future::Future;
use std::io;
use std::net::{Ipv4Addr, SocketAddr, SocketAddrV4, ToSocketAddrs};
use std::panic::{catch_unwind, AssertUnwindSafe};
use std::pin::Pin;
use std::sync::Arc;
use std::task::{Context, Poll};
use std::time::Duration;

use tokio::io::BufReader;
use tokio::net::{TcpListener, TcpSocket, TcpStream};
use tokio::task::JoinSet;

use super::body::{has_conflicting_framing, CONFLICTING_FRAMING};
use super::config::TransportConfig;
use super::head::{read_head, HeadOutcome, Headers, RequestHead};
use super::response::Responder;
use super::wire::{py_repr, ErrorPage};
use super::{Exchange, Handler};
use crate::error::{ApiError, LOG_PREFIX};

/// The methods the donor's handler defines (`do_GET`, `do_POST`, `do_DELETE`,
/// `do_OPTIONS`). Any other method is answered 501 by the transport.
pub const SERVED_METHODS: [&str; 4] = ["GET", "POST", "DELETE", "OPTIONS"];

/// Read buffer of one connection. A head line can be longer; it is collected in pieces.
const READ_BUFFER: usize = 16 * 1024;

/// A bound, listening socket.
#[derive(Debug)]
pub struct Listener {
    inner: TcpListener,
    config: TransportConfig,
}

/// Binds `addr` and listens with the configured backlog. `SO_REUSEADDR` is set except on
/// Windows, as the donor's `allow_reuse_address = os.name != "nt"`. Port 0 picks a free
/// port; [`Listener::local_addr`] reports it. Must be called inside a tokio runtime.
pub fn bind(addr: SocketAddr, config: TransportConfig) -> io::Result<Listener> {
    let socket = match addr {
        SocketAddr::V4(_) => TcpSocket::new_v4()?,
        SocketAddr::V6(_) => TcpSocket::new_v6()?,
    };
    if cfg!(not(windows)) {
        socket.set_reuseaddr(true)?;
    }
    socket.bind(addr)?;
    let inner = socket.listen(config.backlog)?;
    Ok(Listener { inner, config })
}

/// Binds `host:port` as the donor's `HTTPServer((host, port))` does: an IPv4 socket, the
/// empty host meaning every interface, a name resolved to its first IPv4 address. A host
/// with no IPv4 address (`::1`, for example) is an error, as it is for the donor.
pub fn bind_host(host: &str, port: u16, config: TransportConfig) -> io::Result<Listener> {
    bind(SocketAddr::V4(resolve_ipv4(host, port)?), config)
}

/// The donor's start-up probe: binds `host:port` and closes it at once, so that a port
/// already in use is reported before the model loads. Needs no runtime.
pub fn probe_port(host: &str, port: u16) -> io::Result<()> {
    let addr = resolve_ipv4(host, port)?;
    // std sets SO_REUSEADDR on Unix, as the donor's Server class does.
    let listener = std::net::TcpListener::bind(addr)?;
    drop(listener);
    Ok(())
}

fn resolve_ipv4(host: &str, port: u16) -> io::Result<SocketAddrV4> {
    if host.is_empty() {
        return Ok(SocketAddrV4::new(Ipv4Addr::UNSPECIFIED, port));
    }
    if let Ok(ip) = host.parse::<Ipv4Addr>() {
        return Ok(SocketAddrV4::new(ip, port));
    }
    (host, port)
        .to_socket_addrs()?
        .find_map(|a| match a {
            SocketAddr::V4(v4) => Some(v4),
            SocketAddr::V6(_) => None,
        })
        .ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::AddrNotAvailable,
                "the host has no IPv4 address",
            )
        })
}

impl Listener {
    /// The bound address (the chosen port when port 0 was asked for).
    pub fn local_addr(&self) -> io::Result<SocketAddr> {
        self.inner.local_addr()
    }

    /// The listen backlog the socket was opened with (the donor's `request_queue_size`).
    pub fn backlog(&self) -> u32 {
        self.config.backlog
    }

    /// The transport settings.
    pub fn config(&self) -> TransportConfig {
        self.config
    }

    /// Accepts connections until `shutdown` resolves, serving each on its own task. Then it
    /// stops accepting (the socket closes) and returns the connections still in flight, so
    /// that the caller decides how long to wait for them; dropping the set aborts them.
    pub async fn serve<S>(self, handler: Arc<dyn Handler>, shutdown: S) -> JoinSet<()>
    where
        S: Future<Output = ()>,
    {
        let mut connections = JoinSet::new();
        let mut shutdown = std::pin::pin!(shutdown);
        loop {
            tokio::select! {
                biased;
                () = &mut shutdown => break,
                accepted = self.inner.accept() => match accepted {
                    Ok((stream, peer)) => {
                        let handler = Arc::clone(&handler);
                        let config = self.config;
                        connections.spawn(serve_connection(stream, peer, handler, config));
                    }
                    // As socketserver: a failed accept (EMFILE, a reset in the queue) is
                    // skipped. A short pause keeps a persistent failure from spinning.
                    Err(_) => tokio::time::sleep(Duration::from_millis(10)).await,
                },
                Some(_) = connections.join_next(), if !connections.is_empty() => {}
            }
        }
        connections
    }
}

/// Serves the one request of a connection.
pub(crate) async fn serve_connection(
    stream: TcpStream,
    peer: SocketAddr,
    handler: Arc<dyn Handler>,
    config: TransportConfig,
) {
    let local = stream.local_addr().unwrap_or(peer);
    let (read, write) = stream.into_split();
    let mut reader = BufReader::with_capacity(READ_BUFFER, read);
    let timeout = config.request_timeout;
    // A timeout or a socket error while reading the head closes without an answer.
    let Ok(outcome) = read_head(&mut reader, timeout).await else {
        return;
    };
    let head = match outcome {
        HeadOutcome::Close => return,
        HeadOutcome::Refuse {
            page,
            method,
            target,
            http09,
        } => {
            let extra = match (method.as_deref(), target) {
                // The 431 pages: the donor's end_headers override sees `self.command` and
                // `self.path`, and no headers yet. With no headers there is no `Host`, so
                // the early refusal (SEC-1.1) is not asked and the page is answered as is.
                (Some(m), Some((path, version))) => {
                    let partial = RequestHead::new(m, &path, &version, Headers::default());
                    match guarded(peer, || handler.end_headers(&partial)) {
                        Some(extra) => extra,
                        None => return,
                    }
                }
                _ => Vec::new(),
            };
            let mut responder = Responder::new(write, timeout, http09, extra);
            let _ = responder.error_page(&page, method.as_deref()).await;
            return;
        }
        HeadOutcome::Request(head) => head,
    };
    let Some(extra) = guarded(peer, || handler.end_headers(&head)) else {
        return;
    };
    let mut responder = Responder::new(write, timeout, head.is_http09(), extra);
    // The handler's early refusal (the router's `Host` allowlist, deviation SEC-1.1) comes
    // before the transport's own answers for a parsed request, the 501 and the P-2 400.
    let Some(refusal) = guarded(peer, || handler.early_refusal(&head)) else {
        return;
    };
    if let Some(error) = refusal {
        if head.method() == "HEAD" {
            // A response to HEAD carries no content (RFC 9110 section 9.3.2), as Python's
            // send_error leaves the body out for HEAD: the same head (status,
            // Content-Type, the Content-Length of the JSON), without the body.
            let response = error.to_response();
            let headers = response.headers();
            let pairs: Vec<(&str, &str)> = headers.iter().map(|(k, v)| (*k, v.as_str())).collect();
            let _ = responder.start(response.status, &pairs).await;
        } else {
            let _ = responder.error(&error).await;
        }
        return;
    }
    if !SERVED_METHODS.contains(&head.method()) {
        let page = ErrorPage::with_message(
            501,
            format!("Unsupported method ({})", py_repr(head.method())),
        );
        let _ = responder.error_page(&page, Some(head.method())).await;
        return;
    }
    // Approved deviation P-2: ambiguous framing is refused on every route, before dispatch.
    if has_conflicting_framing(head.headers()) {
        let _ = responder
            .error(&ApiError::bad_body(400, CONFLICTING_FRAMING))
            .await;
        return;
    }
    let exchange = Exchange::new(head, reader, responder, config, peer, local);
    let Some(future) = guarded(peer, || handler.handle(exchange)) else {
        return;
    };
    if let Err(panic) = (CatchUnwind { inner: future }).await {
        log_panic(peer, panic.as_ref());
    }
}

/// Runs a synchronous handler call; a panic is logged with the transport's line and gives
/// `None`, so that the connection closes.
fn guarded<T>(peer: SocketAddr, call: impl FnOnce() -> T) -> Option<T> {
    match catch_unwind(AssertUnwindSafe(call)) {
        Ok(value) => Some(value),
        Err(panic) => {
            log_panic(peer, panic.as_ref());
            None
        }
    }
}

fn log_panic(peer: SocketAddr, panic: &(dyn Any + Send)) {
    eprintln!(
        "{LOG_PREFIX} a request from {peer} failed: {:?}",
        panic_message(panic)
    );
}

fn panic_message(panic: &(dyn Any + Send)) -> &str {
    if let Some(s) = panic.downcast_ref::<&'static str>() {
        s
    } else if let Some(s) = panic.downcast_ref::<String>() {
        s.as_str()
    } else {
        "a panic"
    }
}

/// Runs a future and turns a panic inside it into an error.
struct CatchUnwind<F> {
    inner: F,
}

impl<F> Future for CatchUnwind<Pin<Box<F>>>
where
    F: Future<Output = ()> + ?Sized,
{
    type Output = Result<(), Box<dyn Any + Send>>;

    fn poll(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<Self::Output> {
        let inner = &mut self.inner;
        match catch_unwind(AssertUnwindSafe(|| inner.as_mut().poll(cx))) {
            Ok(Poll::Pending) => Poll::Pending,
            Ok(Poll::Ready(())) => Poll::Ready(Ok(())),
            Err(panic) => Poll::Ready(Err(panic)),
        }
    }
}
