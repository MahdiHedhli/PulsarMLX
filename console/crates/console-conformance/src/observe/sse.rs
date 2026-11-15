//! An incremental `text/event-stream` parser that records everything it reads.
//!
//! The parser follows the line rules of the WHATWG event-stream format: a line ends at
//! CRLF, LF or a lone CR; a line that starts with `:` is a comment; a field name runs to
//! the first `:`, and one space after the colon is dropped; a line with no colon is a
//! field with an empty value; a blank line ends a block. One leading U+FEFF at the start
//! of the stream is dropped. Two choices differ from a browser, because a harness must
//! see what was sent rather than what a page would act on:
//!
//! - every block that holds at least one field is recorded as an event, even one with no
//!   `data` field (a browser drops it); a block of comments only is not an event, and its
//!   comments are kept in [`SseStream::comments`] with the number of events before them;
//! - bytes after the last blank line when the body ends are kept as
//!   [`SseStream::unterminated`] instead of being dropped.
//!
//! Bytes are split into lines before they are decoded, so a UTF-8 sequence cut between
//! two reads is decoded whole. A line that is not valid UTF-8 is decoded with U+FFFD and
//! [`SseStream::invalid_utf8`] is set; [`SseEvent::raw`] keeps the exact bytes.
//!
//! A blank line that ends in a lone CR is acted on when the next byte arrives (or at the
//! end of the body), so that in a CRLF stream the LF always belongs to the event it ends
//! and the bytes recorded for an event never depend on where a read was cut.
//!
//! Behavior reference: project-maya serve/server.py:5765-5859, 6463-6474, 6511-6530 and
//! 6600-6640 at 7e68a30f (the donor writes `event: <name>\n`, `data: <json>\n\n`,
//! `data: [DONE]\n\n` and `: keep-alive\n\n`, LF only).

use serde_json::Value;

/// One recorded event: a block of field lines ended by a blank line.
#[derive(Debug, Clone, PartialEq)]
pub struct SseEvent {
    /// Every field line of the block, in order, as `(name, value)`; comments excluded.
    pub fields: Vec<(String, String)>,
    /// The value of the last `event` field, if any.
    pub event: Option<String>,
    /// The values of every `data` field joined with `\n`; `None` when the block has no
    /// `data` field.
    pub data: Option<String>,
    /// The value of the last `id` field, if any.
    pub id: Option<String>,
    /// The value of the last `retry` field, if any.
    pub retry: Option<String>,
    /// The exact bytes of the block, comments and line ends included, through the blank
    /// line that ends it.
    pub raw: Vec<u8>,
}

impl SseEvent {
    /// The data parsed as JSON, or `None` when there is no data or it is not JSON (for
    /// example the literal `[DONE]`).
    pub fn data_json(&self) -> Option<Value> {
        let data = self.data.as_deref()?;
        serde_json::from_str(data).ok()
    }
}

/// A comment line (one that starts with `:`).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SseComment {
    /// How many events had been recorded when the comment was read.
    pub before_event: usize,
    /// The text after the colon, verbatim (the donor's keep-alive reads ` keep-alive`).
    pub text: String,
}

/// Everything read from one event stream.
#[derive(Debug, Clone, PartialEq, Default)]
pub struct SseStream {
    /// The events, in order.
    pub events: Vec<SseEvent>,
    /// The comments, in order.
    pub comments: Vec<SseComment>,
    /// Bytes after the last blank line when the body ended, if any.
    pub unterminated: Option<Vec<u8>>,
    /// A leading U+FEFF was dropped.
    pub bom: bool,
    /// Some line was not valid UTF-8.
    pub invalid_utf8: bool,
}

/// The incremental parser. Feed it body bytes with [`SseParser::feed`], then call
/// [`SseParser::finish`] at the end of the body.
#[derive(Debug, Default)]
pub struct SseParser {
    stream: SseStream,
    line: Vec<u8>,
    block_raw: Vec<u8>,
    fields: Vec<(String, String)>,
    pending_cr: bool,
    first_line_done: bool,
    lines: usize,
}

impl SseParser {
    /// A parser at the start of a stream.
    pub fn new() -> Self {
        Self::default()
    }

    /// The events recorded so far.
    pub fn event_count(&self) -> usize {
        self.stream.events.len()
    }

    /// The non-blank lines (comments and field lines) read so far, so that a reader can
    /// bound what a stream of comments, or of fields with no blank line, makes it hold.
    pub fn line_count(&self) -> usize {
        self.lines
    }

    /// Feeds bytes. When `stop_at` is given and the event count reaches it, parsing stops
    /// right after the byte that completed that event. Returns how many bytes of `bytes`
    /// were consumed and whether the count reached `stop_at`. Bytes not consumed have not
    /// been looked at, so they may be fed again.
    pub fn feed(&mut self, bytes: &[u8], stop_at: Option<usize>) -> (usize, bool) {
        if stop_at.is_some_and(|n| self.stream.events.len() >= n) {
            return (0, true);
        }
        for (i, &b) in bytes.iter().enumerate() {
            if self.pending_cr {
                self.pending_cr = false;
                if b == b'\n' {
                    self.block_raw.push(b);
                    if self.finish_line(stop_at) {
                        return (i + 1, true);
                    }
                    continue;
                }
                if self.finish_line(stop_at) {
                    return (i, true);
                }
            }
            self.block_raw.push(b);
            match b {
                b'\r' => self.pending_cr = true,
                b'\n' => {
                    if self.finish_line(stop_at) {
                        return (i + 1, true);
                    }
                }
                _ => self.line.push(b),
            }
        }
        (bytes.len(), false)
    }

    /// Ends the stream: acts on a pending lone CR and keeps whatever follows the last
    /// blank line as [`SseStream::unterminated`].
    pub fn finish(mut self) -> SseStream {
        if self.pending_cr {
            self.pending_cr = false;
            self.finish_line(None);
        }
        if !self.block_raw.is_empty() {
            self.stream.unterminated = Some(std::mem::take(&mut self.block_raw));
        }
        self.stream
    }

    /// Acts on the line just ended. Returns true when an event was recorded and the
    /// count reached `stop_at`.
    fn finish_line(&mut self, stop_at: Option<usize>) -> bool {
        let line = std::mem::take(&mut self.line);
        let first = !self.first_line_done;
        self.first_line_done = true;
        if line.is_empty() {
            if self.fields.is_empty() {
                // A stray blank line, or the end of a block of comments only.
                self.block_raw.clear();
                return false;
            }
            let fields = std::mem::take(&mut self.fields);
            let raw = std::mem::take(&mut self.block_raw);
            self.stream.events.push(build_event(fields, raw));
            return stop_at.is_some_and(|n| self.stream.events.len() >= n);
        }
        let mut text = match String::from_utf8(line) {
            Ok(text) => text,
            Err(e) => {
                self.stream.invalid_utf8 = true;
                String::from_utf8_lossy(e.as_bytes()).into_owned()
            }
        };
        if first {
            if let Some(rest) = text.strip_prefix('\u{feff}') {
                self.stream.bom = true;
                text = rest.to_string();
                if text.is_empty() {
                    return false;
                }
            }
        }
        self.lines += 1;
        if let Some(rest) = text.strip_prefix(':') {
            self.stream.comments.push(SseComment {
                before_event: self.stream.events.len(),
                text: rest.to_string(),
            });
            return false;
        }
        let (name, value) = match text.split_once(':') {
            Some((name, value)) => (
                name.to_string(),
                value.strip_prefix(' ').unwrap_or(value).to_string(),
            ),
            None => (text, String::new()),
        };
        self.fields.push((name, value));
        false
    }
}

fn build_event(fields: Vec<(String, String)>, raw: Vec<u8>) -> SseEvent {
    let mut event = None;
    let mut data: Option<String> = None;
    let mut id = None;
    let mut retry = None;
    for (name, value) in &fields {
        match name.as_str() {
            "event" => event = Some(value.clone()),
            "data" => match data.as_mut() {
                Some(d) => {
                    d.push('\n');
                    d.push_str(value);
                }
                None => data = Some(value.clone()),
            },
            "id" => id = Some(value.clone()),
            "retry" => retry = Some(value.clone()),
            _ => {}
        }
    }
    SseEvent {
        fields,
        event,
        data,
        id,
        retry,
        raw,
    }
}

/// Parses a whole body at once.
pub fn parse_all(bytes: &[u8]) -> SseStream {
    let mut parser = SseParser::new();
    parser.feed(bytes, None);
    parser.finish()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn bytewise(bytes: &[u8]) -> SseStream {
        let mut parser = SseParser::new();
        for b in bytes {
            let (used, stop) = parser.feed(std::slice::from_ref(b), None);
            assert_eq!((used, stop), (1, false));
        }
        parser.finish()
    }

    #[test]
    fn donor_shapes_parse_into_events_and_comments() {
        let body = b": keep-alive\n\nevent: response.created\ndata: {\"a\": 1}\n\n\
data: {\"b\": \"\xc3\xa9\"}\n\n: keep-alive\n\ndata: [DONE]\n\n";
        let s = parse_all(body);
        assert_eq!(s.events.len(), 3);
        assert_eq!(s.events[0].event.as_deref(), Some("response.created"));
        assert_eq!(s.events[0].data.as_deref(), Some("{\"a\": 1}"));
        assert_eq!(s.events[0].data_json(), Some(serde_json::json!({"a": 1})));
        assert_eq!(s.events[1].event, None);
        assert_eq!(s.events[1].data.as_deref(), Some("{\"b\": \"é\"}"));
        assert_eq!(s.events[2].data.as_deref(), Some("[DONE]"));
        assert_eq!(s.events[2].data_json(), None);
        assert_eq!(s.events[2].raw, b"data: [DONE]\n\n");
        assert_eq!(
            s.comments,
            vec![
                SseComment {
                    before_event: 0,
                    text: " keep-alive".into()
                },
                SseComment {
                    before_event: 2,
                    text: " keep-alive".into()
                },
            ]
        );
        assert_eq!(s.unterminated, None);
        assert_eq!(bytewise(body), s);
    }

    #[test]
    fn crlf_cr_and_lf_line_ends_give_the_same_fields() {
        let lf = parse_all(b"event: x\ndata: a\ndata: b\n\n");
        let crlf = parse_all(b"event: x\r\ndata: a\r\ndata: b\r\n\r\n");
        let cr = parse_all(b"event: x\rdata: a\rdata: b\r\r");
        for s in [&lf, &crlf, &cr] {
            assert_eq!(s.events.len(), 1);
            assert_eq!(s.events[0].event.as_deref(), Some("x"));
            assert_eq!(s.events[0].data.as_deref(), Some("a\nb"));
            assert_eq!(s.unterminated, None);
        }
        assert_eq!(
            crlf.events[0].raw,
            b"event: x\r\ndata: a\r\ndata: b\r\n\r\n"
        );
        assert_eq!(cr.events[0].raw, b"event: x\rdata: a\rdata: b\r\r");
        assert_eq!(bytewise(b"event: x\r\ndata: a\r\ndata: b\r\n\r\n"), crlf);
        assert_eq!(bytewise(b"event: x\rdata: a\rdata: b\r\r"), cr);
    }

    #[test]
    fn field_rules_follow_the_format() {
        let s = parse_all(b"data:x\ndata:  two\ndata\nfoo: bar\nid: 7\nretry: 10\n\n");
        let e = &s.events[0];
        assert_eq!(e.data.as_deref(), Some("x\n two\n"));
        assert_eq!(e.id.as_deref(), Some("7"));
        assert_eq!(e.retry.as_deref(), Some("10"));
        assert_eq!(
            e.fields,
            vec![
                ("data".into(), "x".into()),
                ("data".into(), " two".into()),
                ("data".into(), String::new()),
                ("foo".into(), "bar".into()),
                ("id".into(), "7".into()),
                ("retry".into(), "10".into()),
            ]
        );
    }

    #[test]
    fn a_block_without_data_is_still_recorded() {
        let s = parse_all(b"event: ping\n\n\n\n");
        assert_eq!(s.events.len(), 1);
        assert_eq!(s.events[0].data, None);
        assert_eq!(s.events[0].event.as_deref(), Some("ping"));
    }

    #[test]
    fn a_missing_final_blank_line_is_kept_as_unterminated() {
        let s = parse_all(b"data: 1\n\ndata: 2\n");
        assert_eq!(s.events.len(), 1);
        assert_eq!(s.unterminated.as_deref(), Some(&b"data: 2\n"[..]));
        let s = parse_all(b"data: 1\n\ndata: 2");
        assert_eq!(s.unterminated.as_deref(), Some(&b"data: 2"[..]));
        // A lone CR at the very end ends the line, but no blank line follows.
        let s = parse_all(b"data: 1\r\rdata: 2\r");
        assert_eq!(s.events.len(), 1);
        assert_eq!(s.unterminated.as_deref(), Some(&b"data: 2\r"[..]));
        // A blank line ended by a lone CR at the end of the body still ends the event.
        let s = parse_all(b"data: 1\r\r");
        assert_eq!(s.events.len(), 1);
        assert_eq!(s.unterminated, None);
    }

    #[test]
    fn utf8_split_across_reads_is_decoded_whole() {
        let body = "data: {\"t\": \"h\u{e9}llo \u{1f600}\"}\n\n".as_bytes();
        let whole = parse_all(body);
        assert!(!whole.invalid_utf8);
        for cut in 0..body.len() {
            let mut parser = SseParser::new();
            parser.feed(&body[..cut], None);
            parser.feed(&body[cut..], None);
            assert_eq!(parser.finish(), whole, "cut at {cut}");
        }
    }

    #[test]
    fn invalid_utf8_is_flagged_and_raw_is_kept() {
        let s = parse_all(b"data: \xff\n\n");
        assert!(s.invalid_utf8);
        assert_eq!(s.events[0].data.as_deref(), Some("\u{fffd}"));
        assert_eq!(s.events[0].raw, b"data: \xff\n\n");
    }

    #[test]
    fn a_leading_bom_is_dropped_once() {
        let s = parse_all(b"\xef\xbb\xbfdata: a\n\n\xef\xbb\xbfdata: b\n\n");
        assert!(s.bom);
        assert_eq!(s.events[0].fields[0].0, "data");
        assert_eq!(s.events[1].fields[0].0, "\u{feff}data");
    }

    #[test]
    fn comment_and_field_lines_are_counted() {
        let s = b": a\n\n: b\ndata: 1\nevent: x\n\nnot ended\n";
        let mut parser = SseParser::new();
        parser.feed(s, None);
        assert_eq!(parser.line_count(), 5);
        assert_eq!(parser.event_count(), 1);
    }

    #[test]
    fn stop_at_is_exact_to_the_event() {
        let body = b"data: 1\n\n: c\n\ndata: 2\n\ndata: 3\n\n";
        let mut parser = SseParser::new();
        let (used, stop) = parser.feed(body, Some(2));
        assert!(stop);
        assert_eq!(&body[..used], b"data: 1\n\n: c\n\ndata: 2\n\n");
        assert_eq!(parser.event_count(), 2);
        // Feeding again with the count already reached consumes nothing.
        assert_eq!(parser.feed(&body[used..], Some(2)), (0, true));
        // CRLF: the LF that ends the event belongs to it.
        let body = b"data: 1\r\n\r\ndata: 2\r\n\r\n";
        let mut parser = SseParser::new();
        let (used, stop) = parser.feed(body, Some(1));
        assert!(stop);
        assert_eq!(&body[..used], b"data: 1\r\n\r\n");
        // Lone CR: the event ends when the next byte arrives, which is not consumed.
        let body = b"data: 1\r\rdata: 2\r\r";
        let mut parser = SseParser::new();
        let (used, stop) = parser.feed(body, Some(1));
        assert!(stop);
        assert_eq!(&body[..used], b"data: 1\r\r");
    }
}
