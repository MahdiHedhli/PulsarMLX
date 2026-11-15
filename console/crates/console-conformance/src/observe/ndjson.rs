//! An incremental `application/x-ndjson` parser that records every line.
//!
//! A line ends at LF. Each complete line is recorded with its exact bytes, its text and,
//! when it parses, its JSON value; an empty line is recorded too. Bytes after the last LF
//! when the body ends are kept as [`NdjsonStream::unterminated`]. Lines are split before
//! they are decoded, so a UTF-8 sequence cut between two reads is decoded whole.
//!
//! Behavior reference: project-maya serve/server.py:5618-5634 and 5717-5745 at 7e68a30f
//! (the donor writes `json.dumps(event) + "\n"` per line).

use serde_json::Value;

/// One complete line.
#[derive(Debug, Clone, PartialEq)]
pub struct NdjsonLine {
    /// The exact bytes of the line, without the LF that ends it.
    pub raw: Vec<u8>,
    /// The line decoded as UTF-8 (U+FFFD for an invalid sequence).
    pub text: String,
    /// The line parsed as JSON, when it parses.
    pub json: Option<Value>,
}

/// Everything read from one NDJSON body.
#[derive(Debug, Clone, PartialEq, Default)]
pub struct NdjsonStream {
    /// The complete lines, in order.
    pub lines: Vec<NdjsonLine>,
    /// Bytes after the last LF when the body ended, if any.
    pub unterminated: Option<Vec<u8>>,
    /// Some line was not valid UTF-8.
    pub invalid_utf8: bool,
}

/// The incremental parser.
#[derive(Debug, Default)]
pub struct NdjsonParser {
    stream: NdjsonStream,
    line: Vec<u8>,
}

impl NdjsonParser {
    /// A parser at the start of a body.
    pub fn new() -> Self {
        Self::default()
    }

    /// The complete lines recorded so far.
    pub fn line_count(&self) -> usize {
        self.stream.lines.len()
    }

    /// Feeds bytes. When `stop_at` is given and the line count reaches it, parsing stops
    /// right after the LF that completed that line. Returns the bytes consumed and whether
    /// the count reached `stop_at`.
    pub fn feed(&mut self, bytes: &[u8], stop_at: Option<usize>) -> (usize, bool) {
        if stop_at.is_some_and(|n| self.stream.lines.len() >= n) {
            return (0, true);
        }
        for (i, &b) in bytes.iter().enumerate() {
            if b != b'\n' {
                self.line.push(b);
                continue;
            }
            let raw = std::mem::take(&mut self.line);
            let json = serde_json::from_slice(&raw).ok();
            let text = match std::str::from_utf8(&raw) {
                Ok(t) => t.to_string(),
                Err(_) => {
                    self.stream.invalid_utf8 = true;
                    String::from_utf8_lossy(&raw).into_owned()
                }
            };
            self.stream.lines.push(NdjsonLine { raw, text, json });
            if stop_at.is_some_and(|n| self.stream.lines.len() >= n) {
                return (i + 1, true);
            }
        }
        (bytes.len(), false)
    }

    /// Ends the body.
    pub fn finish(mut self) -> NdjsonStream {
        if !self.line.is_empty() {
            self.stream.unterminated = Some(std::mem::take(&mut self.line));
        }
        self.stream
    }
}

/// Parses a whole body at once.
pub fn parse_all(bytes: &[u8]) -> NdjsonStream {
    let mut parser = NdjsonParser::new();
    parser.feed(bytes, None);
    parser.finish()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn lines_are_recorded_with_json_and_text() {
        let s = parse_all(b"{\"a\": 1}\n\nnot json\n{\"done\": true}");
        assert_eq!(s.lines.len(), 3);
        assert_eq!(s.lines[0].json, Some(serde_json::json!({"a": 1})));
        assert_eq!(s.lines[1].raw, b"");
        assert_eq!(s.lines[1].json, None);
        assert_eq!(s.lines[2].text, "not json");
        assert_eq!(s.unterminated.as_deref(), Some(&b"{\"done\": true}"[..]));
    }

    #[test]
    fn split_reads_give_the_same_stream() {
        let body = "{\"t\": \"\u{e9}\u{1f600}\"}\n{\"u\": 2}\n".as_bytes();
        let whole = parse_all(body);
        for cut in 0..body.len() {
            let mut p = NdjsonParser::new();
            p.feed(&body[..cut], None);
            p.feed(&body[cut..], None);
            assert_eq!(p.finish(), whole);
        }
    }

    #[test]
    fn stop_at_is_exact_to_the_line() {
        let body = b"{\"a\": 1}\n{\"a\": 2}\n{\"a\": 3}\n";
        let mut p = NdjsonParser::new();
        let (used, stop) = p.feed(body, Some(2));
        assert!(stop);
        assert_eq!(&body[..used], b"{\"a\": 1}\n{\"a\": 2}\n");
        assert_eq!(p.feed(&body[used..], Some(2)), (0, true));
    }

    #[test]
    fn invalid_utf8_is_flagged() {
        let s = parse_all(b"\xfe\n");
        assert!(s.invalid_utf8);
        assert_eq!(s.lines[0].text, "\u{fffd}");
    }
}
