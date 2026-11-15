//! Bounded text carried across the seam: engine notes and failure messages.

use std::fmt;

/// The most bytes a [`BoundedText`] note may carry (contract section 7: "at most 512 bytes").
pub const NOTE_MAX_BYTES: usize = 512;

/// The most bytes an [`EngineFailure`](super::EngineFailure) message may carry.
pub const MESSAGE_MAX_BYTES: usize = 4096;

/// Text cut to a byte limit at a character boundary, so that nothing an engine writes can
/// grow a record without bound.
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct BoundedText {
    text: String,
    truncated: bool,
}

impl BoundedText {
    /// Keeps at most `max_bytes` bytes of `text`, cut at the last character boundary that
    /// fits.
    pub fn new(text: &str, max_bytes: usize) -> Self {
        if text.len() <= max_bytes {
            return Self {
                text: text.to_owned(),
                truncated: false,
            };
        }
        let mut end = max_bytes;
        while end > 0 && !text.is_char_boundary(end) {
            end -= 1;
        }
        Self {
            text: text.get(..end).unwrap_or_default().to_owned(),
            truncated: true,
        }
    }

    /// A note line (at most [`NOTE_MAX_BYTES`]).
    pub fn note(text: &str) -> Self {
        Self::new(text, NOTE_MAX_BYTES)
    }

    /// A failure message (at most [`MESSAGE_MAX_BYTES`]).
    pub fn message(text: &str) -> Self {
        Self::new(text, MESSAGE_MAX_BYTES)
    }

    /// The kept text.
    pub fn as_str(&self) -> &str {
        &self.text
    }

    /// True when the original text was longer than the limit.
    pub fn was_truncated(&self) -> bool {
        self.truncated
    }
}

impl fmt::Display for BoundedText {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.text)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn short_text_is_kept_whole() {
        let t = BoundedText::note("hello");
        assert_eq!(t.as_str(), "hello");
        assert!(!t.was_truncated());
    }

    #[test]
    fn long_text_is_cut_at_a_char_boundary() {
        // "é" is two bytes; a limit of 3 falls inside the second one.
        let t = BoundedText::new("éé", 3);
        assert_eq!(t.as_str(), "é");
        assert!(t.was_truncated());
        let note = BoundedText::note(&"x".repeat(NOTE_MAX_BYTES + 10));
        assert_eq!(note.as_str().len(), NOTE_MAX_BYTES);
    }
}
