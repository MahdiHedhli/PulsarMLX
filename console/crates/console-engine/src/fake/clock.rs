//! The clock the scripted engine paces itself by.
//!
//! The donor's mock engine sleeps with `time.sleep` and measures its decode time with
//! `time.time()`. Here both go through a [`FakeClock`], so that a test can replace the wall
//! clock with a [`ManualClock`] whose sleeps only advance a counter: the token choice never
//! depends on the clock, and with a manual clock the figures do not either.

use std::fmt;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use super::lock;

/// A monotonic clock with a sleep. `Send + Sync`, so a factory can hold it and hand it to
/// every instance it starts.
pub trait FakeClock: Send + Sync + fmt::Debug {
    /// Time elapsed since an arbitrary fixed origin.
    fn now(&self) -> Duration;

    /// Waits for `d` (a [`ManualClock`] only advances its counter).
    fn sleep(&self, d: Duration);
}

/// The wall clock: [`Instant`] and [`std::thread::sleep`].
#[derive(Debug, Clone, Copy)]
pub struct SystemClock {
    origin: Instant,
}

impl SystemClock {
    /// A clock whose origin is now.
    pub fn new() -> Self {
        Self {
            origin: Instant::now(),
        }
    }
}

impl Default for SystemClock {
    fn default() -> Self {
        Self::new()
    }
}

impl FakeClock for SystemClock {
    fn now(&self) -> Duration {
        self.origin.elapsed()
    }

    fn sleep(&self, d: Duration) {
        if !d.is_zero() {
            std::thread::sleep(d);
        }
    }
}

/// The most sleeps a [`ManualClock`] records; later sleeps still advance it.
pub const MANUAL_CLOCK_MAX_RECORDED: usize = 65_536;

#[derive(Debug, Default)]
struct ManualState {
    now: Duration,
    sleeps: Vec<Duration>,
}

/// A clock for tests: `sleep` returns at once and advances `now` by the requested time,
/// and every sleep is recorded (up to [`MANUAL_CLOCK_MAX_RECORDED`]). Cloning shares the
/// clock.
#[derive(Debug, Clone, Default)]
pub struct ManualClock(Arc<Mutex<ManualState>>);

impl ManualClock {
    /// A clock at zero with no sleep recorded.
    pub fn new() -> Self {
        Self::default()
    }

    /// Moves the clock forward by `d` without recording a sleep.
    pub fn advance(&self, d: Duration) {
        let mut s = lock(&self.0);
        s.now = s.now.saturating_add(d);
    }

    /// The sleeps requested so far, in order.
    pub fn sleeps(&self) -> Vec<Duration> {
        lock(&self.0).sleeps.clone()
    }

    /// Forgets the recorded sleeps; the time stays where it is.
    pub fn clear_sleeps(&self) {
        lock(&self.0).sleeps.clear();
    }
}

impl FakeClock for ManualClock {
    fn now(&self) -> Duration {
        lock(&self.0).now
    }

    fn sleep(&self, d: Duration) {
        let mut s = lock(&self.0);
        s.now = s.now.saturating_add(d);
        if s.sleeps.len() < MANUAL_CLOCK_MAX_RECORDED {
            s.sleeps.push(d);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fake_manual_clock_advances_only_by_sleeps() {
        let c = ManualClock::new();
        assert_eq!(c.now(), Duration::ZERO);
        c.sleep(Duration::from_millis(3));
        c.advance(Duration::from_millis(2));
        let shared = c.clone();
        shared.sleep(Duration::from_millis(5));
        assert_eq!(c.now(), Duration::from_millis(10));
        assert_eq!(
            c.sleeps(),
            vec![Duration::from_millis(3), Duration::from_millis(5)]
        );
        c.clear_sleeps();
        assert!(c.sleeps().is_empty());
        assert_eq!(c.now(), Duration::from_millis(10));
    }

    #[test]
    fn fake_system_clock_is_monotonic() {
        let c = SystemClock::new();
        let a = c.now();
        c.sleep(Duration::ZERO);
        assert!(c.now() >= a);
    }
}
