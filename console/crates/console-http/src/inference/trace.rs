//! The turn trace (`PULSAR_CONSOLE_TURN_TRACE`, the donor's `MAYA_TURN_TRACE`): monotonic
//! clock marks of one request, printed as one line when its first token arrives.
//!
//! The line is the donor's, with the `[console]` prefix (B2):
//! `[console] trace n=<prompt tokens> <name>=<ms>... t0=<ms>`, where each mark is written
//! as milliseconds after `t0` with one decimal, in time order, and `t0` is the `http` mark
//! (or the earliest one). The donor keeps one process-wide mark table and prints the
//! absolute `CLOCK_MONOTONIC` milliseconds as `t0`, to line up with its engine's own trace
//! line; this trace belongs to its request, and `t0` counts milliseconds from the first
//! trace this process made, since the standard library exposes no absolute monotonic
//! reading. The engine-side marks of the donor (`gen_start`, `gen_written`,
//! `gen_flushed`) belong to the line-protocol client of M3, and the line is printed only
//! once `gen_start` exists, as the donor's (so M1 prints none); the prompt marks
//! (`render_start`, `marked`, `rendered`, `encoded`) to the prompt packages of M2, which
//! add them through [`TurnTrace::mark`].
//!
//! Behavior reference: project-maya serve/server.py:2093-2110, 6161-6162, 6242-6244,
//! 6581-6583 and 1416-1417 at 7e68a30f.

use std::sync::OnceLock;
use std::time::Instant;

use crate::error::LOG_PREFIX;

/// The most marks one request keeps; later new names are ignored.
pub const TRACE_MARKS_MAX: usize = 32;

/// The instant the process's first trace was made: the zero of `t0`.
fn anchor() -> Instant {
    static ANCHOR: OnceLock<Instant> = OnceLock::new();
    *ANCHOR.get_or_init(Instant::now)
}

/// The clock marks of one request.
#[derive(Debug, Clone)]
pub struct TurnTrace {
    on: bool,
    marks: Vec<(&'static str, Instant)>,
    printed: bool,
}

impl TurnTrace {
    /// A trace that records marks when `on`, and does nothing otherwise.
    pub fn new(on: bool) -> Self {
        if on {
            let _ = anchor();
        }
        Self {
            on,
            marks: Vec::new(),
            printed: false,
        }
    }

    /// Whether marks are recorded.
    pub fn is_on(&self) -> bool {
        self.on
    }

    /// Records `name` now (the donor's `turn_mark`); a mark of the same name is replaced.
    pub fn mark(&mut self, name: &'static str) {
        self.mark_at(name, Instant::now());
    }

    /// Records `name` at `at`.
    pub fn mark_at(&mut self, name: &'static str, at: Instant) {
        if !self.on {
            return;
        }
        if let Some(slot) = self.marks.iter_mut().find(|(n, _)| *n == name) {
            slot.1 = at;
        } else if self.marks.len() < TRACE_MARKS_MAX {
            self.marks.push((name, at));
        }
    }

    /// The marks recorded, in the order they were first made.
    pub fn marks(&self) -> &[(&'static str, Instant)] {
        &self.marks
    }

    /// The trace line for a prompt of `n` tokens (the donor's `turn_print`), or `None` when
    /// the trace is off or holds no mark.
    pub fn line(&self, n: Option<usize>) -> Option<String> {
        if !self.on || self.marks.is_empty() {
            return None;
        }
        let ms = |at: Instant| at.saturating_duration_since(anchor()).as_secs_f64() * 1000.0;
        let t0 = match self.marks.iter().find(|(name, _)| *name == "http") {
            Some((_, at)) => ms(*at),
            None => self
                .marks
                .iter()
                .map(|(_, at)| ms(*at))
                .fold(f64::INFINITY, f64::min),
        };
        let mut sorted: Vec<(&str, f64)> = self.marks.iter().map(|(k, at)| (*k, ms(*at))).collect();
        // A stable sort by time, as Python's `sorted` over the table's insertion order.
        sorted.sort_by(|a, b| a.1.total_cmp(&b.1));
        let parts: Vec<String> = sorted
            .iter()
            .map(|(k, v)| format!("{k}={:.1}", v - t0))
            .collect();
        let n = n.map_or_else(|| String::from("None"), |n| n.to_string());
        Some(format!(
            "{LOG_PREFIX} trace n={n} {} t0={t0:.1}",
            parts.join(" ")
        ))
    }

    /// The first token arrived: marks `first_t` and returns the line, once per request, and
    /// only once the engine-side `gen_start` mark exists (the donor prints under `"gen_start"
    /// in TURN and "first_t" not in TURN`; its in-process engines never mark `gen_start`, so
    /// in M1, before the line-protocol client of M3 adds that mark, no line is printed).
    pub fn first_token(&mut self, n: usize) -> Option<String> {
        if !self.on || self.printed || !self.marks.iter().any(|(k, _)| *k == "gen_start") {
            return None;
        }
        self.printed = true;
        self.mark("first_t");
        self.line(Some(n))
    }
}

#[cfg(test)]
mod tests {
    use std::time::Duration;

    use super::*;

    #[test]
    fn an_off_trace_records_nothing() {
        let mut t = TurnTrace::new(false);
        t.mark("http");
        assert!(t.marks().is_empty());
        assert_eq!(t.line(Some(3)), None);
        assert_eq!(t.first_token(3), None);
    }

    #[test]
    fn the_line_is_in_time_order_relative_to_http() {
        let base = Instant::now() + Duration::from_millis(5);
        let mut t = TurnTrace::new(true);
        t.mark_at("json", base + Duration::from_micros(2_260));
        t.mark_at("http", base);
        t.mark_at("prepared", base + Duration::from_micros(10_040));
        t.mark_at("body", base + Duration::from_micros(1_000));
        let line = t.line(Some(42)).unwrap_or_default();
        let (head, t0) = line.rsplit_once(" t0=").unwrap_or_default();
        assert_eq!(
            head,
            "[console] trace n=42 http=0.0 body=1.0 json=2.3 prepared=10.0"
        );
        let t0: f64 = t0.parse().unwrap_or(-1.0);
        assert!(t0 >= 5.0, "{t0}");
        // The same name again replaces its mark.
        t.mark_at("body", base + Duration::from_micros(3_000));
        assert!(t
            .line(None)
            .unwrap_or_default()
            .starts_with("[console] trace n=None http=0.0 json=2.3 body=3.0 "));
    }

    #[test]
    fn without_http_the_earliest_mark_is_t0_and_the_first_token_prints_once() {
        let base = Instant::now();
        let mut t = TurnTrace::new(true);
        t.mark_at("json", base);
        // Without the engine-side `gen_start` mark, no line (and no `first_t`).
        assert_eq!(t.first_token(7), None);
        assert_eq!(t.marks().len(), 1);
        t.mark_at("gen_start", base);
        let first = t.first_token(7).unwrap_or_default();
        assert!(
            first.starts_with("[console] trace n=7 json=0.0 gen_start=0.0 first_t="),
            "{first}"
        );
        assert_eq!(t.first_token(7), None);
        for i in 0..100 {
            let name: &'static str = if i % 2 == 0 { "a" } else { "b" };
            t.mark(name);
        }
        assert_eq!(t.marks().len(), 5);
    }
}
