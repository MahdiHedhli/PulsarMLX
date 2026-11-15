//! The queue watchdog: a queue that has stopped moving says so, with what holds the engine.
//!
//! Behavior reference: project-maya serve/server.py:182-187 (`QUEUE_TICK_S`,
//! `QUEUE_WEDGED_S`, `QUEUE_WARN_S`) and 3239-3270 (`start_queue_watch`) at 7e68a30f.

use std::time::Duration;

use tokio::task::JoinHandle;
use tokio::time::Instant;

use super::lock::EngineFifo;
use super::queue::secs0;

/// How often the watchdog looks.
pub const QUEUE_TICK: Duration = Duration::from_secs(15);

/// The age of the first waiter at which the queue counts as stopped.
pub const QUEUE_WEDGED: Duration = Duration::from_secs(120);

/// How often the warning repeats while the queue stays stopped.
pub const QUEUE_WARN: Duration = Duration::from_secs(60);

/// What the server is doing, for the watchdog's line; read only when a warning is due.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct WatchStatus {
    /// A request is running on the engine.
    pub busy: bool,
    /// The running request's phase; empty or `None` reads as `working`.
    pub phase: Option<String>,
    /// Tokens generated so far by the running request; `None` is written `None`, as the
    /// donor's `s.get('generated')` would print it.
    pub generated: Option<i64>,
    /// Requests counted active.
    pub active: u64,
}

/// The watchdog's decision state between ticks.
#[derive(Debug, Default, Clone)]
pub struct QueueWatchState {
    warned: Option<Instant>,
}

impl QueueWatchState {
    /// One tick's decision: true when a warning is due now (and then counted from `now`).
    /// A warning is due when someone waits, the first in line has waited at least
    /// [`QUEUE_WEDGED`], and no warning was given in the last [`QUEUE_WARN`].
    ///
    /// Behavior reference: project-maya serve/server.py:3249-3256 at 7e68a30f.
    pub fn due(&mut self, now: Instant, oldest: Duration, waiting: usize) -> bool {
        if waiting == 0 || oldest < QUEUE_WEDGED {
            return false;
        }
        if let Some(w) = self.warned {
            if now.saturating_duration_since(w) < QUEUE_WARN {
                return false;
            }
        }
        self.warned = Some(now);
        true
    }
}

/// The watchdog's warning line.
///
/// Behavior reference: project-maya serve/server.py:3257-3266 at 7e68a30f; the log
/// prefix and the variable names are renamed under B2 (naming.md).
pub fn queue_watch_line(
    waiting: usize,
    oldest: Duration,
    held_by: &str,
    status: &WatchStatus,
) -> String {
    let doing = if status.busy {
        let phase = match status.phase.as_deref() {
            Some(p) if !p.is_empty() => p,
            _ => "working",
        };
        let generated = status
            .generated
            .map_or_else(|| "None".to_owned(), |g| g.to_string());
        format!("a request is running ({phase}, {generated} tokens so far)")
    } else {
        "nothing is running".to_owned()
    };
    format!(
        "[console] WARNING: {waiting} request(s) have waited for the engine for up to {} s \
         and {doing}; {held_by}, {} request(s) counted active. A request that holds the \
         engine and waits on it for ever stops every request behind it - \
         PULSAR_CONSOLE_REQUEST_QUIET_S / PULSAR_CONSOLE_DRAIN_S bound those waits, so this \
         line is what a wedged FIFO would look like. Queue state: GET /status, /metrics \
         (queued, active).",
        secs0(oldest),
        status.active
    )
}

/// The running watchdog; dropping it stops the task.
#[derive(Debug)]
pub struct QueueWatch {
    task: JoinHandle<()>,
}

impl Drop for QueueWatch {
    fn drop(&mut self) {
        self.task.abort();
    }
}

impl EngineFifo {
    /// Starts the queue watchdog on the current tokio runtime: every [`QUEUE_TICK`] it
    /// looks at the line and, when a warning is due ([`QueueWatchState::due`]), writes
    /// [`queue_watch_line`] to the FIFO's log with `status()` read at that moment. One
    /// watchdog per FIFO is the caller's to ensure (the donor's service starts it once).
    ///
    /// Behavior reference: project-maya serve/server.py:3239-3270 at 7e68a30f.
    pub fn spawn_queue_watch<F>(&self, status: F) -> QueueWatch
    where
        F: Fn() -> WatchStatus + Send + 'static,
    {
        let fifo = self.clone();
        let task = tokio::spawn(async move {
            let mut state = QueueWatchState::default();
            loop {
                tokio::time::sleep(QUEUE_TICK).await;
                let oldest = fifo.oldest_wait();
                let waiting = fifo.waiting();
                if !state.due(Instant::now(), oldest, waiting) {
                    continue;
                }
                let line = queue_watch_line(waiting, oldest, &fifo.held_by(), &status());
                fifo.log().line(&line);
            }
        });
        QueueWatch { task }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_line_names_what_runs() {
        let busy = WatchStatus {
            busy: true,
            phase: Some(String::new()),
            generated: None,
            active: 2,
        };
        let line = queue_watch_line(
            3,
            Duration::from_millis(130_500),
            "1 of 1 place(s) in use",
            &busy,
        );
        assert!(line.starts_with(
            "[console] WARNING: 3 request(s) have waited for the engine for up to 130 s and a \
             request is running (working, None tokens so far); 1 of 1 place(s) in use, 2 \
             request(s) counted active. "
        ));
        let phased = WatchStatus {
            busy: true,
            phase: Some("writing".to_owned()),
            generated: Some(41),
            active: 1,
        };
        assert!(queue_watch_line(1, QUEUE_WEDGED, "x", &phased)
            .contains("a request is running (writing, 41 tokens so far); x, 1 request(s)"));
    }

    #[test]
    fn due_only_when_wedged_and_not_recently_warned() {
        let t0 = Instant::now();
        let mut s = QueueWatchState::default();
        assert!(!s.due(t0, QUEUE_WEDGED, 0));
        assert!(!s.due(t0, QUEUE_WEDGED - Duration::from_millis(1), 1));
        assert!(s.due(t0, QUEUE_WEDGED, 1));
        assert!(!s.due(t0 + QUEUE_WARN - Duration::from_millis(1), QUEUE_WEDGED, 1));
        assert!(s.due(t0 + QUEUE_WARN, QUEUE_WEDGED, 1));
    }
}
