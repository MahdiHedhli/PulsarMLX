//! The client watcher: notices that the client of a request closed or reset its connection
//! while the server has nothing to write yet (a request waiting in the queue, a
//! non-streamed answer being generated).
//!
//! The watcher owns the reading side of the connection and peeks one byte without consuming
//! it. End of file, or a reset (Python's `ConnectionError`), means the client is gone: the
//! request's [`ControlHandle`] is cancelled, which the engine reads through its
//! `ControlProbe`, and [`ClientWatch::gone`] resolves for async waiters. Data the client sent
//! is not an end; while such data waits unread, the watcher looks again every 0.5 s, as the
//! donor polls. Other socket errors end the watch without a verdict. The watch ends when the
//! [`ClientWatch`] is dropped, which a handler does when its request is done.
//!
//! The donor polls with `select` every 0.5 s; this watcher waits for the socket to become
//! readable instead, so a close is noticed at once rather than within 0.5 s. Nothing on the
//! wire differs.
//!
//! Behavior reference: project-maya serve/server.py:5019-5044 (`watch_client`) at 7e68a30f.

use std::time::Duration;

use console_core::engine::ControlHandle;
use tokio::io::BufReader;
use tokio::net::tcp::OwnedReadHalf;
use tokio::sync::watch;
use tokio::task::JoinHandle;

use super::io::is_connection_error;

/// How long the watcher waits before looking again while unread client data is present.
pub const WATCH_INTERVAL: Duration = Duration::from_millis(500);

/// A running client watch. Dropping it stops the watch.
#[derive(Debug)]
pub struct ClientWatch {
    gone: watch::Receiver<bool>,
    task: JoinHandle<()>,
}

impl ClientWatch {
    /// Starts watching the connection's reading side. When the client goes, `control` is
    /// cancelled.
    pub(crate) fn spawn(reader: BufReader<OwnedReadHalf>, control: ControlHandle) -> Self {
        let (tx, rx) = watch::channel(false);
        let task = tokio::spawn(async move {
            let mut reader = reader;
            let mut byte = [0u8; 1];
            loop {
                match reader.get_mut().peek(&mut byte).await {
                    Ok(0) => break,
                    Ok(_) => tokio::time::sleep(WATCH_INTERVAL).await,
                    Err(e) if is_connection_error(&e) => break,
                    // Closed by this server, or another error: the watch ends, no verdict.
                    Err(_) => return,
                }
            }
            control.cancel();
            let _ = tx.send(true);
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
