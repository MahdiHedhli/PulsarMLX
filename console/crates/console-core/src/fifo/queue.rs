//! A request's wait for its first turn: keep-alive pings while queued, a prompt exit when
//! its cancel is set, and the line for a long wait.
//!
//! Behavior reference: project-maya serve/server.py:3842-3860 (`_queue_wait`), 3813-3840
//! (`_turn`), 4351-4364 (the long-wait line) and 396-401 (`queue_ping_seconds`) at
//! 7e68a30f.

use std::time::Duration;

use tokio::time::Instant;

use super::lock::{deadline_after, EngineFifo, EntryWait, Place, PlaceGuard, Units};
use crate::engine::ControlProbe;

/// The keep-alive interval when the variable is unset, empty or unreadable.
///
/// Behavior reference: project-maya serve/server.py:178-180 at 7e68a30f (`QUEUE_PING_S`).
pub const QUEUE_PING: Duration = Duration::from_secs(2);

/// The shortest keep-alive interval the variable can set.
pub const QUEUE_PING_MIN: Duration = Duration::from_millis(10);

/// A request that waited at least this long gets a line when its turn comes.
///
/// Behavior reference: project-maya serve/server.py:175-177 at 7e68a30f (`QUEUE_LOG_S`).
pub const QUEUE_LOG: Duration = Duration::from_secs(5);

/// How often a queued request looks at its cancel and at the line between wake-ups.
///
/// Behavior reference: project-maya serve/server.py:3828, 3854 at 7e68a30f
/// (`wait_turn(place, timeout=0.05)`).
pub const QUEUE_POLL: Duration = Duration::from_millis(50);

/// The environment variable that sets the keep-alive interval, in seconds (naming.md,
/// renamed from the donor's `MAYA_QUEUE_PING_S` under B2).
pub const QUEUE_PING_ENV: &str = "PULSAR_CONSOLE_QUEUE_PING_S";

/// The keep-alive interval for a variable's value, as the donor reads it:
/// `max(0.01, float(value or 2.0))`, and 2 s when the value is not a number. `None` means
/// never (an infinite or unrepresentably long interval).
///
/// Behavior reference: project-maya serve/server.py:396-401 at 7e68a30f.
pub fn queue_ping_interval_from(value: Option<&str>) -> Option<Duration> {
    let secs = match value {
        None | Some("") => return Some(QUEUE_PING),
        Some(v) => match py_float(v) {
            Some(x) => x,
            None => return Some(QUEUE_PING),
        },
    };
    // Python's max(0.01, x) keeps 0.01 for a NaN, which compares false.
    let secs = if secs > QUEUE_PING_MIN.as_secs_f64() {
        secs
    } else {
        return Some(QUEUE_PING_MIN);
    };
    Duration::try_from_secs_f64(secs).ok()
}

/// The keep-alive interval read from [`QUEUE_PING_ENV`] now.
///
/// Behavior reference: project-maya serve/server.py:396-401 at 7e68a30f.
pub fn queue_ping_interval() -> Option<Duration> {
    let value = std::env::var(QUEUE_PING_ENV).ok();
    queue_ping_interval_from(value.as_deref())
}

/// Python's `float()` on a string: surrounding whitespace ignored, an optional sign,
/// decimal or exponent form with single underscores between digits, or `inf`,
/// `infinity` and `nan` in any case.
fn py_float(s: &str) -> Option<f64> {
    let t = s.trim();
    if !t.is_ascii() {
        return None;
    }
    let b = t.as_bytes();
    let mut cleaned = String::with_capacity(t.len());
    for (i, &c) in b.iter().enumerate() {
        if c == b'_' {
            let before = i.checked_sub(1).and_then(|j| b.get(j));
            match (before, b.get(i + 1)) {
                (Some(x), Some(y)) if x.is_ascii_digit() && y.is_ascii_digit() => continue,
                _ => return None,
            }
        }
        cleaned.push(char::from(c));
    }
    cleaned.parse::<f64>().ok()
}

/// One step of a queued request's wait.
#[derive(Debug)]
pub enum QueueStep {
    /// Still queued; time for a keep-alive (HTTP writes it as `: keep-alive`).
    Ping,
    /// The turn: the place is held until the guard is dropped.
    ///
    /// It can arrive with the cancel already set (the cancel is looked at once per
    /// [`QUEUE_POLL`], and the grant may come first). The turn driver checks the cancel
    /// after `Turn` and, when it is set, answers with a cancelled finish and zero completion
    /// tokens and drops the guard without calling the engine, as the donor's `_turn` does
    /// (serve/server.py:4361-4363 at 7e68a30f).
    Turn(PlaceGuard),
    /// The cancel was set while queued: the place in line was given up and nothing is
    /// held. The turn driver answers with a cancelled finish.
    Cancelled,
    /// The wait had already ended (a call after `Turn`, `Cancelled` or `Ended`).
    Ended,
}

/// A request's wait in the FIFO for its first turn, stepped with [`QueueWait::next`].
///
/// Dropping it (the client went away between pings) gives the place in line up; it holds
/// nothing until it returns [`QueueStep::Turn`]. When the turn comes, or the cancel ends
/// the wait, a request that waited at least [`QUEUE_LOG`] logs
/// `[console] this request waited <s> s for the engine (<n> request(s) behind it)`,
/// measured from the creation of the wait. The line is written on a cancel too, as the
/// donor's `_turn` body logs before it looks at the cancel; on a cancel the count includes
/// the request itself, as the donor's `_turn` has put it back in line by then (on a turn it
/// does not, since the request has left the line).
///
/// Behavior reference: project-maya serve/server.py:3842-3860, 4351-4364 at 7e68a30f.
#[derive(Debug)]
pub struct QueueWait {
    fifo: EngineFifo,
    ticket: Option<Place>,
    cancel: ControlProbe,
    ping: Option<Duration>,
    asked: Instant,
    last_ping: Instant,
}

impl EngineFifo {
    /// Joins the line for `units` and returns the wait, stepped with [`QueueWait::next`].
    /// `ping` is the keep-alive interval (`None`: never), normally
    /// [`queue_ping_interval`].
    ///
    /// Behavior reference: project-maya serve/server.py:3842-3860 at 7e68a30f.
    pub fn queue_wait(
        &self,
        units: Units,
        cancel: ControlProbe,
        ping: Option<Duration>,
    ) -> QueueWait {
        let asked = Instant::now();
        QueueWait {
            fifo: self.clone(),
            ticket: Some(self.enqueue(units)),
            cancel,
            ping,
            asked,
            last_ping: asked,
        }
    }
}

impl QueueWait {
    /// When the request joined the line.
    pub fn asked_at(&self) -> Instant {
        self.asked
    }

    /// The next step: a ping, the turn, or the cancel.
    ///
    /// Cancel-safe: dropping the future keeps the wait as it was (still in line, holding
    /// nothing), and a granted place is never lost between the grant and the return.
    pub async fn next(&mut self) -> QueueStep {
        loop {
            let Some(id) = self.ticket.as_ref().map(Place::id) else {
                return QueueStep::Ended;
            };
            if self.cancel.is_cancelled() {
                // Logged while the place is still in line, so the count includes this
                // request, as the donor's re-enqueued place in `_turn` is counted.
                self.log_long_wait();
                // Dropping the place in line leaves the line.
                self.ticket = None;
                return QueueStep::Cancelled;
            }
            let deadline = deadline_after(Instant::now(), QUEUE_POLL);
            match self.fifo.inner.wait_entry(id, Some(deadline)).await {
                EntryWait::Granted(k) => {
                    let guard = match self.ticket.take() {
                        Some(t) => t.into_guard(k),
                        None => return QueueStep::Ended,
                    };
                    self.log_long_wait();
                    return QueueStep::Turn(guard);
                }
                EntryWait::Gone => {
                    if let Some(t) = self.ticket.take() {
                        t.forget();
                    }
                    return QueueStep::Ended;
                }
                EntryWait::TimedOut => {}
            }
            if let Some(every) = self.ping {
                let now = Instant::now();
                if now.saturating_duration_since(self.last_ping) >= every {
                    self.last_ping = now;
                    return QueueStep::Ping;
                }
            }
        }
    }

    fn log_long_wait(&self) {
        let waited = Instant::now().saturating_duration_since(self.asked);
        if waited < QUEUE_LOG {
            return;
        }
        let fifo = &self.fifo;
        fifo.log().line(&format!(
            "[console] this request waited {} s for the engine ({} request(s) behind it)",
            secs0(waited),
            fifo.waiting()
        ));
    }
}

/// Seconds as Python's `f"{x:.0f}"` writes them: rounded half to even on the exact value.
pub(super) fn secs0(d: Duration) -> String {
    format!("{:.0}", d.as_secs_f64())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ping_interval_reads_like_the_donor() {
        let ms = Duration::from_millis;
        assert_eq!(queue_ping_interval_from(None), Some(QUEUE_PING));
        assert_eq!(queue_ping_interval_from(Some("")), Some(QUEUE_PING));
        assert_eq!(queue_ping_interval_from(Some("  ")), Some(QUEUE_PING));
        assert_eq!(queue_ping_interval_from(Some("soon")), Some(QUEUE_PING));
        assert_eq!(queue_ping_interval_from(Some("0.1")), Some(ms(100)));
        assert_eq!(
            queue_ping_interval_from(Some(" 1_0 ")),
            Some(Duration::from_secs(10))
        );
        assert_eq!(queue_ping_interval_from(Some("1__0")), Some(QUEUE_PING));
        assert_eq!(queue_ping_interval_from(Some("0")), Some(QUEUE_PING_MIN));
        assert_eq!(queue_ping_interval_from(Some("-3")), Some(QUEUE_PING_MIN));
        assert_eq!(queue_ping_interval_from(Some("nan")), Some(QUEUE_PING_MIN));
        assert_eq!(queue_ping_interval_from(Some("1e-9")), Some(QUEUE_PING_MIN));
        assert_eq!(queue_ping_interval_from(Some("2.5E0")), Some(ms(2500)));
        assert_eq!(queue_ping_interval_from(Some("inf")), None);
        assert_eq!(queue_ping_interval_from(Some("Infinity")), None);
        assert_eq!(queue_ping_interval_from(Some("1e300")), None);
    }

    #[test]
    fn whole_seconds_round_half_to_even_as_python_does() {
        let s = |x: f64| secs0(Duration::from_secs_f64(x));
        assert_eq!(s(0.5), "0");
        assert_eq!(s(1.5), "2");
        assert_eq!(s(2.5), "2");
        assert_eq!(s(5.0), "5");
        assert_eq!(s(119.6), "120");
    }
}
