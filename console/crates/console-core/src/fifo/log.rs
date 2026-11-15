//! Where the FIFO's server-window lines go: standard output by default, a capture in tests.
//!
//! Every line already carries the `[console] ` prefix (naming rule 7, B2). The sink is a
//! seam: the server's logging package can wrap it without this module knowing how lines
//! are stored or shown.

use std::fmt;
use std::sync::{Arc, Mutex, PoisonError};

/// Upper bound on the lines a [`LogCapture`] keeps; older lines are dropped first.
pub const LOG_CAPTURE_MAX_LINES: usize = 4096;

/// A destination for the FIFO's log lines. Cheap to clone; `Send + Sync`.
#[derive(Clone)]
pub struct FifoLog(Arc<dyn Fn(&str) + Send + Sync>);

impl FifoLog {
    /// Lines written to standard output, one per call, as the donor's `print(..., flush=True)`.
    ///
    /// Behavior reference: project-maya serve/server.py:268, 371-372 at 7e68a30f.
    pub fn stdout() -> Self {
        Self(Arc::new(|line: &str| {
            use std::io::Write;
            let mut out = std::io::stdout().lock();
            // A log line that cannot be written is dropped: a diagnostic never fails the FIFO.
            let _ = writeln!(out, "{line}");
            let _ = out.flush();
        }))
    }

    /// Lines handed to `f`.
    pub fn new(f: impl Fn(&str) + Send + Sync + 'static) -> Self {
        Self(Arc::new(f))
    }

    /// A sink that keeps its lines, and the handle that reads them back.
    pub fn capture() -> (Self, LogCapture) {
        let cap = LogCapture::default();
        let keep = cap.clone();
        (Self::new(move |line| keep.push(line)), cap)
    }

    /// Writes one line.
    pub fn line(&self, line: &str) {
        (self.0)(line);
    }
}

impl Default for FifoLog {
    fn default() -> Self {
        Self::stdout()
    }
}

impl fmt::Debug for FifoLog {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str("FifoLog(..)")
    }
}

/// The lines a captured [`FifoLog`] received, oldest first, at most
/// [`LOG_CAPTURE_MAX_LINES`].
#[derive(Clone, Debug, Default)]
pub struct LogCapture(Arc<Mutex<Vec<String>>>);

impl LogCapture {
    fn push(&self, line: &str) {
        let mut lines = self.0.lock().unwrap_or_else(PoisonError::into_inner);
        if lines.len() >= LOG_CAPTURE_MAX_LINES {
            lines.remove(0);
        }
        lines.push(line.to_owned());
    }

    /// A copy of the lines received so far.
    pub fn lines(&self) -> Vec<String> {
        self.0
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .clone()
    }

    /// Takes the lines received so far, leaving the capture empty.
    pub fn take(&self) -> Vec<String> {
        std::mem::take(&mut *self.0.lock().unwrap_or_else(PoisonError::into_inner))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn capture_keeps_lines_in_order_and_bounded() {
        let (log, cap) = FifoLog::capture();
        log.line("a");
        log.line("b");
        assert_eq!(cap.lines(), vec!["a".to_owned(), "b".to_owned()]);
        assert_eq!(cap.take().len(), 2);
        assert!(cap.lines().is_empty());
        for i in 0..LOG_CAPTURE_MAX_LINES + 3 {
            log.line(&i.to_string());
        }
        let lines = cap.lines();
        assert_eq!(lines.len(), LOG_CAPTURE_MAX_LINES);
        assert_eq!(lines.first().map(String::as_str), Some("3"));
    }
}
