//! The client watcher: notices that the client of a request closed or reset its connection
//! while the server has nothing to write yet (a request waiting in the queue, a
//! non-streamed answer being generated).
//!
//! # Polling
//!
//! The watcher owns the reading side of the connection and polls it as the donor's
//! `watch_client` does: it waits [`WATCH_INTERVAL`] (0.5 s) first, then checks, then waits
//! again, until the [`ClientWatch`] is dropped or a check reaches a verdict. A check never
//! waits for the socket. When the socket has something to read, the watcher peeks one byte
//! without consuming it:
//!
//! - end of file (the client closed the connection, or only its sending side) means the
//!   client is gone;
//! - a reset or an abort (Python's `ConnectionError`) means the client is gone as well;
//! - a byte the client sent (its data, never read by the handler) is not an end, and the
//!   watcher waits for the next check;
//! - any other socket error ends the watch without a verdict.
//!
//! When the client is gone, the request's [`ControlHandle`] is cancelled, which the engine
//! reads through its `ControlProbe`, and [`ClientWatch::gone`] resolves for async waiters.
//! A watch whose control was cancelled by someone else ends without a verdict: the donor's
//! `cancel.wait(every)` returns at once, and this watcher notices at its next check, which
//! changes nothing on the wire because neither gives a verdict.
//!
//! # Why the donor's timing
//!
//! The first check comes one interval after the watch starts, never at once, and the timing
//! shows on the wire. An HTTP/1.0 client may send its request and then shut down its
//! sending side (`nc -N`, a raw socket); the connection then reads as end of file from the
//! start. In the donor, an answer that is ready before the first check reaches such a
//! client in full, and a longer one is cancelled at the next check. A watcher that reacted
//! to the end of file at once would cancel every half-closed request before its engine
//! wrote a token, and the client would get an empty answer where the donor sends the whole
//! one. A client that closes while its request waits is still noticed within one interval
//! plus the time of one check.
//!
//! Behavior reference: project-maya serve/server.py:5019-5044 (`watch_client`) at 7e68a30f.

use std::io;
use std::task::{Context, Poll, Waker};
use std::time::Duration;

use console_core::engine::ControlHandle;
use tokio::io::{BufReader, ReadBuf};
use tokio::net::tcp::OwnedReadHalf;
use tokio::sync::watch;
use tokio::task::JoinHandle;

use super::io::is_connection_error;

/// The wait before the first check of a watch and between two checks (the donor's
/// `every = 0.5`).
///
/// Behavior reference: project-maya serve/server.py:5019 and 5034 at 7e68a30f.
pub const WATCH_INTERVAL: Duration = Duration::from_millis(500);

/// A running client watch. Dropping it stops the watch.
#[derive(Debug)]
pub struct ClientWatch {
    gone: watch::Receiver<bool>,
    task: JoinHandle<()>,
}

/// What one check of the socket found.
#[derive(Debug, PartialEq, Eq)]
enum Check {
    /// Nothing to read, or data the client sent: look again at the next check.
    Stay,
    /// End of file, a reset or an abort: the client is gone.
    Gone,
    /// Another socket error: the watch ends without a verdict.
    End,
}

/// Maps the outcome of one non-waiting peek to a verdict. `None` is a socket with nothing
/// to read (the donor's `select` with a zero timeout returned no readable socket).
///
/// Behavior reference: project-maya serve/server.py:5034-5042 at 7e68a30f.
fn verdict(peeked: Option<io::Result<usize>>) -> Check {
    match peeked {
        None | Some(Ok(1..)) => Check::Stay,
        Some(Ok(0)) => Check::Gone,
        Some(Err(e)) if is_connection_error(&e) => Check::Gone,
        // Closed by this server, or another error: the request is done.
        Some(Err(_)) => Check::End,
    }
}

/// One check: peeks one byte when the socket has something to read, without waiting.
///
/// The peek is polled once, with a waker that does nothing: a socket that is not readable
/// at this moment answers `Pending`, which is the donor's empty `select` result, and no
/// wake-up is left behind for the watch task.
fn check(reader: &mut BufReader<OwnedReadHalf>) -> Check {
    let mut byte = [0u8; 1];
    let mut cx = Context::from_waker(Waker::noop());
    let mut buf = ReadBuf::new(&mut byte);
    let peeked = match reader.get_mut().poll_peek(&mut cx, &mut buf) {
        Poll::Ready(r) => Some(r),
        Poll::Pending => None,
    };
    verdict(peeked)
}

/// The watch loop: wait one interval, then check, until a verdict or a cancel by another
/// party. True when the client was seen to go.
///
/// Behavior reference: project-maya serve/server.py:5033-5043 at 7e68a30f.
async fn poll_loop(mut reader: BufReader<OwnedReadHalf>, control: &ControlHandle) -> bool {
    let probe = control.probe();
    loop {
        // `while not cancel.wait(every)`: the wait comes before every check.
        tokio::time::sleep(WATCH_INTERVAL).await;
        if probe.is_cancelled() {
            return false;
        }
        match check(&mut reader) {
            Check::Stay => {}
            Check::Gone => return true,
            Check::End => return false,
        }
    }
}

impl ClientWatch {
    /// Starts watching the connection's reading side. The first check comes one
    /// [`WATCH_INTERVAL`] after this call. When the client goes, `control` is cancelled.
    ///
    /// Behavior reference: project-maya serve/server.py:5019-5044 at 7e68a30f.
    pub(crate) fn spawn(reader: BufReader<OwnedReadHalf>, control: ControlHandle) -> Self {
        let (tx, rx) = watch::channel(false);
        let task = tokio::spawn(async move {
            let gone = poll_loop(reader, &control).await;
            if gone {
                control.cancel();
                let _ = tx.send(true);
            }
        });
        Self { gone: rx, task }
    }

    /// True once the client was seen to go.
    pub fn is_gone(&self) -> bool {
        *self.gone.borrow()
    }

    /// Resolves when the client is seen to go; never resolves if the watch ended without a
    /// verdict.
    pub async fn gone(&mut self) {
        if self.gone.wait_for(|gone| *gone).await.is_err() {
            std::future::pending::<()>().await;
        }
    }
}

impl Drop for ClientWatch {
    fn drop(&mut self) {
        self.task.abort();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    use std::time::Instant;

    use tokio::io::AsyncWriteExt;
    use tokio::net::{TcpListener, TcpStream};

    #[test]
    fn a_peek_maps_to_the_donors_verdicts() {
        assert_eq!(verdict(None), Check::Stay);
        assert_eq!(verdict(Some(Ok(1))), Check::Stay);
        assert_eq!(verdict(Some(Ok(0))), Check::Gone);
        for kind in [
            io::ErrorKind::ConnectionReset,
            io::ErrorKind::ConnectionAborted,
            io::ErrorKind::BrokenPipe,
            io::ErrorKind::ConnectionRefused,
        ] {
            assert_eq!(verdict(Some(Err(io::Error::from(kind)))), Check::Gone);
        }
        for kind in [io::ErrorKind::NotConnected, io::ErrorKind::Other] {
            assert_eq!(verdict(Some(Err(io::Error::from(kind)))), Check::End);
        }
    }

    async fn pair() -> (
        TcpStream,
        BufReader<OwnedReadHalf>,
        tokio::net::tcp::OwnedWriteHalf,
    ) {
        let listener = TcpListener::bind("127.0.0.1:0").await;
        let Ok(listener) = listener else {
            panic!("bind");
        };
        let Ok(addr) = listener.local_addr() else {
            panic!("local address");
        };
        let (client, accepted) = tokio::join!(TcpStream::connect(addr), listener.accept());
        let (Ok(client), Ok((server, _))) = (client, accepted) else {
            panic!("connect");
        };
        let (read, write) = server.into_split();
        (client, BufReader::new(read), write)
    }

    // serve/server.py:5034: the first check comes one interval after the start, also for a
    // connection that reads as end of file from the start.
    #[tokio::test]
    async fn a_half_closed_client_is_seen_at_the_first_check_not_before() {
        let (mut client, reader, _write) = pair().await;
        assert!(client.shutdown().await.is_ok());
        let control = ControlHandle::new();
        let probe = control.probe();
        let start = Instant::now();
        let mut watch = ClientWatch::spawn(reader, control);
        assert!(!watch.is_gone());
        let seen = tokio::time::timeout(Duration::from_secs(10), watch.gone()).await;
        assert!(seen.is_ok(), "the half-close was not seen");
        let waited = start.elapsed();
        // Never before the first check; well before the second on an idle or loaded machine.
        assert!(waited >= WATCH_INTERVAL, "{waited:?}");
        assert!(waited < Duration::from_millis(1250), "{waited:?}");
        assert!(probe.is_cancelled());
        assert!(watch.is_gone());
    }

    // serve/server.py:5033: a cancel set by another party ends the watch without a verdict.
    // The donor's `cancel.wait(every)` returns at once; this watcher notices at its next
    // check, which gives no verdict either, even on a closed connection.
    #[tokio::test]
    async fn a_cancel_from_elsewhere_ends_the_watch_without_a_verdict() {
        let (client, reader, _write) = pair().await;
        drop(client);
        let control = ControlHandle::new();
        let probe = control.probe();
        control.cancel();
        let start = Instant::now();
        let watch = ClientWatch::spawn(reader, control);
        let mut rx = watch.gone.clone();
        // The watch task ends at its first check, and its sender with it.
        let ended = tokio::time::timeout(Duration::from_secs(10), rx.changed()).await;
        assert!(matches!(ended, Ok(Err(_))), "{ended:?}");
        let waited = start.elapsed();
        // No later than the first check, with the same margin as above for a loaded machine.
        assert!(waited < Duration::from_millis(1250), "{waited:?}");
        assert!(!watch.is_gone());
        assert!(probe.is_cancelled());
    }
}
