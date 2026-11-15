//! Owned by PRM-04. The incremental UTF-8 detokenizer.
//!
//! A generated token can end in the middle of a multi-byte character. [`Detokenizer`] feeds
//! each token's raw bytes through an incremental UTF-8 decoder that emits the complete
//! characters and holds an incomplete one until its remaining bytes arrive, replacing invalid
//! bytes with U+FFFD exactly where Python's `codecs` UTF-8 decoder with `errors="replace"`
//! does (one U+FFFD per maximal invalid subpart). In this mode each token costs constant
//! time.
//!
//! A tokenizer without `token_bytes` (the byte tokenizer of the tests and of the synthetic
//! engines) keeps the donor's older algorithm: re-decode every id so far, emit nothing while
//! the text ends in U+FFFD, and emit the new code points otherwise. That mode costs O(n) per
//! token, O(n^2) over a generation of n tokens, as in the donor; the trait gives no byte view
//! of a token there, so it cannot be made incremental without one.
//!
//! Behavior reference: project-maya serve/server.py:2294-2313 at 7e68a30f.

use crate::bpe::{Tokenize, TokenizerError};

/// Decodes `bytes` as UTF-8, replacing each maximal invalid subpart (and an incomplete
/// sequence at the end) with one U+FFFD, as Python's `bytes.decode("utf-8", "replace")`.
pub fn decode_utf8_replace(bytes: &[u8]) -> String {
    String::from_utf8_lossy(bytes).into_owned()
}

/// Python's `codecs.getincrementaldecoder("utf-8")(errors="replace")`, used without a final
/// call: an incomplete character at the end of the input is held for the next call.
#[derive(Debug, Clone, Default)]
pub struct Utf8IncrementalDecoder {
    /// The bytes of an incomplete but so far valid character (at most three).
    pending: Vec<u8>,
}

impl Utf8IncrementalDecoder {
    /// A decoder with nothing held.
    pub fn new() -> Self {
        Self::default()
    }

    /// Decodes `input` after any held bytes and returns the complete text.
    pub fn decode(&mut self, input: &[u8]) -> String {
        let mut buf = std::mem::take(&mut self.pending);
        buf.extend_from_slice(input);
        let mut out = String::with_capacity(buf.len());
        let mut rest: &[u8] = &buf;
        loop {
            match std::str::from_utf8(rest) {
                Ok(text) => {
                    out.push_str(text);
                    break;
                }
                Err(e) => {
                    let (valid, after) = rest.split_at(e.valid_up_to());
                    // The prefix is valid UTF-8 by construction.
                    out.push_str(&String::from_utf8_lossy(valid));
                    match e.error_len() {
                        Some(n) => {
                            out.push('\u{FFFD}');
                            rest = after.get(n..).unwrap_or_default();
                        }
                        None => {
                            self.pending = after.to_vec();
                            break;
                        }
                    }
                }
            }
        }
        out
    }

    /// The bytes held for an incomplete character.
    pub fn pending(&self) -> &[u8] {
        &self.pending
    }
}

#[derive(Debug, Clone)]
enum Mode {
    Incremental(Utf8IncrementalDecoder),
    Redecode { ids: Vec<u32>, sent: usize },
}

/// Turns generated ids into text deltas, one id at a time.
#[derive(Debug, Clone)]
pub struct Detokenizer<T: Tokenize> {
    tok: T,
    mode: Mode,
}

impl<T: Tokenize> Detokenizer<T> {
    /// A detokenizer over `tok`: incremental when the tokenizer has `token_bytes`, the
    /// re-decode otherwise. `tok` may be a reference or an `Arc`.
    pub fn new(tok: T) -> Self {
        let mode = if tok.has_token_bytes() {
            Mode::Incremental(Utf8IncrementalDecoder::new())
        } else {
            Mode::Redecode {
                ids: Vec::new(),
                sent: 0,
            }
        };
        Self { tok, mode }
    }

    /// Whether the incremental decoder is in use (the donor's `self.inc is not None`).
    pub fn is_incremental(&self) -> bool {
        matches!(self.mode, Mode::Incremental(_))
    }

    /// The text that id `id` completes. An error from the tokenizer (an id outside the
    /// vocabulary) leaves the incremental decoder unchanged; in the re-decode mode the id
    /// stays recorded, as in the donor.
    pub fn push(&mut self, id: u32) -> Result<String, TokenizerError> {
        match &mut self.mode {
            Mode::Incremental(dec) => {
                let raw = match self.tok.token_bytes(id) {
                    Some(r) => r?,
                    None => Vec::new(),
                };
                Ok(dec.decode(&raw))
            }
            Mode::Redecode { ids, sent } => {
                ids.push(id);
                let text = self.tok.decode(ids)?;
                if text.ends_with('\u{FFFD}') {
                    return Ok(String::new());
                }
                let delta: String = text.chars().skip(*sent).collect();
                *sent = text.chars().count();
                Ok(delta)
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn feed(chunks: &[&[u8]]) -> Vec<String> {
        let mut d = Utf8IncrementalDecoder::new();
        chunks.iter().map(|c| d.decode(c)).collect()
    }

    #[test]
    fn holds_a_split_character() {
        // U+1F600 is F0 9F 98 80.
        assert_eq!(
            feed(&[b"a\xf0", b"\x9f", b"\x98", b"\x80b"]),
            ["a", "", "", "\u{1F600}b"]
        );
    }

    #[test]
    fn invalid_bytes_become_one_replacement_per_maximal_subpart() {
        // Python: b"\xf0\x9f\x41".decode("utf-8", "replace") == "�A"
        assert_eq!(feed(&[b"\xf0\x9f", b"A"]), ["", "\u{FFFD}A"]);
        // Python: b"\xed\xa0\x80" (a surrogate) gives three U+FFFD.
        assert_eq!(feed(&[b"\xed\xa0\x80"]), ["\u{FFFD}\u{FFFD}\u{FFFD}"]);
        // A lone continuation byte, and a byte that never starts a character.
        assert_eq!(
            feed(&[b"\x80", b"\xff", b"\xc3"]),
            ["\u{FFFD}", "\u{FFFD}", ""]
        );
        // E0 needs A0..BF next: E0 80 is two errors.
        assert_eq!(feed(&[b"\xe0", b"\x80"]), ["", "\u{FFFD}\u{FFFD}"]);
    }

    #[test]
    fn whole_decode_matches_python_replace() {
        assert_eq!(decode_utf8_replace(b"\xf0\x9f\x98"), "\u{FFFD}");
        assert_eq!(decode_utf8_replace(b"a\xc3\xa9\xc3"), "a\u{e9}\u{FFFD}");
        assert_eq!(
            decode_utf8_replace(b"\xf4\x90\x80\x80"),
            "\u{FFFD}".repeat(4)
        );
    }

    #[test]
    fn pending_is_visible() {
        let mut d = Utf8IncrementalDecoder::new();
        assert_eq!(d.decode(b"\xe4\xbd"), "");
        assert_eq!(d.pending(), b"\xe4\xbd");
        assert_eq!(d.decode(b"\xa0"), "\u{4F60}");
        assert!(d.pending().is_empty());
    }
}
