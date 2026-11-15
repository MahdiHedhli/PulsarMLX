//! The SSE frame parser and stream reader. Every frame keeps its raw bytes, terminator
//! included, so a test can compare a stream byte for byte with a golden as well as read
//! its fields.
//!
//! The donor's streams use three frame shapes, each ended by a blank line:
//!
//! - `data: <json>\n\n` (the OpenAI chunks and the closing `data: [DONE]\n\n`);
//! - `event: <name>\ndata: <json>\n\n` (the Anthropic events and `event: error`);
//! - `: keep-alive\n\n`, an SSE comment that clients ignore (queue and engine heartbeats).
//!
//! The parser accepts any mix of these, and the general SSE line rules besides: a frame
//! ends at `\n\n` or `\r\n\r\n`; within it a line `field: value` (one space after the
//! colon dropped, as the SSE specification says), `field:value` or `field` alone; several
//! `data` lines join with `\n`; a line that starts with `:` is a comment. Bytes after the
//! last terminator are left over as an incomplete frame, never guessed at. The collectors
//! [`data_json`] and [`chat_text`] read the donor's way instead: line by line over the
//! whole text, only `data: ` lines (with the space), and they fail the test where the
//! donor's `json.loads` or indexing would raise.
//!
//! [`SseReader`] reads such a stream from a socket: it writes the request, reads the head,
//! then hands out frames one at a time with a deadline, so a test can assert on frames as
//! they arrive (keep-alives while queued, the first token, the end).
//!
//! Behavior reference: project-maya serve/server.py:5846-5859, 6519-6526, 6609-6639 and
//! 6694-6710 at 7e68a30f (the frames the donor writes), and serve/test_logprobs.py:182-185
//! and serve/test_server.py:2470-2471 at 7e68a30f (how its tests read them).

use std::net::SocketAddr;
use std::time::Duration;

use serde_json::Value;
use tokio::io::AsyncReadExt;
use tokio::net::TcpStream;

use crate::raw::{self, RawResponse, DEADLINE, MAX_RESPONSE_BYTES};

/// The data of the frame that ends an OpenAI stream.
pub const DONE: &str = "[DONE]";

/// The comment text of the donor's keep-alive frames.
pub const KEEP_ALIVE: &str = "keep-alive";

/// The most frames one parse returns; beyond it the rest is left unparsed (a stream that
/// large is a broken test, not a real answer).
pub const MAX_FRAMES: usize = 1 << 20;

/// One frame of an event stream.
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct SseFrame {
    /// The frame's bytes as they arrived, its terminating blank line included.
    pub raw: Vec<u8>,
    /// The `event` field, if the frame has one (the last one wins, as in the SSE
    /// specification).
    pub event: Option<String>,
    /// The `data` lines joined with `\n`, if the frame has any.
    pub data: Option<String>,
    /// The `id` field, if any.
    pub id: Option<String>,
    /// The text of each comment line, after the `:` and one optional space.
    pub comments: Vec<String>,
}

impl SseFrame {
    /// Whether the frame is a comment and nothing else.
    pub fn is_comment(&self) -> bool {
        self.data.is_none() && self.event.is_none() && self.id.is_none()
    }

    /// Whether the frame is the donor's keep-alive comment (`: keep-alive`).
    pub fn is_keep_alive(&self) -> bool {
        self.is_comment() && self.comments.iter().any(|c| c == KEEP_ALIVE)
    }

    /// Whether the frame is `data: [DONE]`.
    pub fn is_done(&self) -> bool {
        self.data.as_deref() == Some(DONE)
    }

    /// The data parsed as JSON, when the frame has data that is JSON (`[DONE]` is not).
    pub fn json(&self) -> Option<Value> {
        self.data
            .as_deref()
            .and_then(|d| serde_json::from_str(d).ok())
    }
}

/// What a parse of stream bytes found.
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct SseParse {
    /// The complete frames, in order.
    pub frames: Vec<SseFrame>,
    /// The bytes after the last complete frame.
    pub rest: Vec<u8>,
}

/// Where the next frame ends in `bytes`: the end of its terminator (`\n\n` or
/// `\r\n\r\n`, whichever ends first).
fn frame_end(bytes: &[u8]) -> Option<usize> {
    frame_end_from(bytes, 0)
}

/// [`frame_end`], with the bytes before `from` already known to hold no terminator that
/// ends before `from` (so a reader that waits for more bytes does not scan its buffer
/// again). One pass: at each `\n`, a following `\n` ends a frame two bytes on, a
/// following `\r\n` after a `\r` ends one three bytes on; the first match ends first.
fn frame_end_from(bytes: &[u8], from: usize) -> Option<usize> {
    let start = from.saturating_sub(3).min(bytes.len());
    let tail = bytes.get(start..)?;
    for (offset, &b) in tail.iter().enumerate() {
        if b != b'\n' {
            continue;
        }
        let k = start + offset;
        match bytes.get(k + 1) {
            Some(b'\n') => return Some(k + 2),
            Some(b'\r')
                if k >= 1
                    && bytes.get(k - 1) == Some(&b'\r')
                    && bytes.get(k + 2) == Some(&b'\n') =>
            {
                return Some(k + 3)
            }
            _ => {}
        }
    }
    None
}

/// Parses one complete frame (its raw bytes, terminator included).
pub fn parse_frame(raw: &[u8]) -> SseFrame {
    let text = String::from_utf8_lossy(raw);
    let mut frame = SseFrame {
        raw: raw.to_vec(),
        ..SseFrame::default()
    };
    let mut data: Vec<String> = Vec::new();
    for line in text.split('\n') {
        let line = line.strip_suffix('\r').unwrap_or(line);
        if line.is_empty() {
            continue;
        }
        if let Some(comment) = line.strip_prefix(':') {
            frame
                .comments
                .push(comment.strip_prefix(' ').unwrap_or(comment).to_owned());
            continue;
        }
        let (field, value) = match line.split_once(':') {
            Some((f, v)) => (f, v.strip_prefix(' ').unwrap_or(v)),
            None => (line, ""),
        };
        match field {
            "data" => data.push(value.to_owned()),
            "event" => frame.event = Some(value.to_owned()),
            "id" => frame.id = Some(value.to_owned()),
            _ => {}
        }
    }
    if !data.is_empty() {
        frame.data = Some(data.join("\n"));
    }
    frame
}

/// Splits stream bytes into complete frames and the bytes left over.
pub fn parse_frames(bytes: &[u8]) -> SseParse {
    let mut frames = Vec::new();
    let mut at = 0usize;
    while frames.len() < MAX_FRAMES {
        let Some(rest) = bytes.get(at..) else { break };
        let Some(end) = frame_end(rest) else { break };
        frames.push(parse_frame(rest.get(..end).unwrap_or_default()));
        at += end;
    }
    SseParse {
        frames,
        rest: bytes.get(at..).unwrap_or_default().to_vec(),
    }
}

/// The frames of a whole streamed answer: the body of `response` parsed.
pub fn frames_of(response: &RawResponse) -> Vec<SseFrame> {
    parse_frames(&response.body).frames
}

/// The lines of `text` as Python's `str.splitlines()` splits them (at `\n`, `\r`,
/// `\r\n`, `\x0b`, `\x0c`, `\x1c`, `\x1d`, `\x1e`, `\x85`, U+2028 and U+2029), without
/// their ends.
pub fn splitlines(text: &str) -> Vec<&str> {
    let mut lines = Vec::new();
    let mut start = 0usize;
    let mut chars = text.char_indices().peekable();
    while let Some((i, c)) = chars.next() {
        let is_break = matches!(
            c,
            '\n' | '\r'
                | '\x0b'
                | '\x0c'
                | '\x1c'
                | '\x1d'
                | '\x1e'
                | '\u{85}'
                | '\u{2028}'
                | '\u{2029}'
        );
        if !is_break {
            continue;
        }
        lines.push(text.get(start..i).unwrap_or_default());
        let mut next = i + c.len_utf8();
        if c == '\r' {
            if let Some(&(j, '\n')) = chars.peek() {
                chars.next();
                next = j + 1;
            }
        }
        start = next;
    }
    if start < text.len() {
        lines.push(text.get(start..).unwrap_or_default());
    }
    lines
}

/// The text of the frames, joined, as the donor's `r.read().decode()`. Panics (failing the
/// test, as `decode` raising fails the donor's) when the bytes are not UTF-8.
fn stream_text(frames: &[SseFrame]) -> String {
    let bytes: Vec<u8> = frames.iter().flat_map(|f| f.raw.iter().copied()).collect();
    match String::from_utf8(bytes) {
        Ok(text) => text,
        Err(e) => panic!("a stream that is not UTF-8: {e}"),
    }
}

/// The JSON of every `data: ` line except `data: [DONE]`, as the donor's `Http.post`
/// collects a stream: `[json.loads(line[6:]) for line in text.splitlines() if
/// line.startswith("data: ") and line != "data: [DONE]"]`. Line by line, as the donor reads
/// it (not frame by frame), and strict as it is: a `data: ` line that is not JSON panics,
/// naming the line, as `json.loads` raising fails the donor's test. A `data:` line with no
/// space is not collected, as the donor's `startswith("data: ")` does not collect it.
///
/// Behavior reference: project-maya serve/test_logprobs.py:182-185 at 7e68a30f.
pub fn data_json(frames: &[SseFrame]) -> Vec<Value> {
    let text = stream_text(frames);
    splitlines(&text)
        .into_iter()
        .filter(|line| line.starts_with("data: ") && *line != "data: [DONE]")
        .map(|line| {
            let data = line.get(6..).unwrap_or_default();
            match serde_json::from_str(data) {
                Ok(v) => v,
                Err(e) => panic!("a data line that is not JSON ({e}): {line:?}"),
            }
        })
        .collect()
}

/// The text of an OpenAI chat stream as the donor's `QueuedKeepAlives` reads it:
/// `"".join(json.loads(line[6:])["choices"][0]["delta"].get("content") or "" for line in
/// text.splitlines() if line.startswith("data: {"))`. Strict as the donor is: a
/// `data: {` line that is not JSON, or a chunk with no `choices[0].delta`, or a content
/// that is neither empty nor a string, panics, naming the line.
///
/// Behavior reference: project-maya serve/test_server.py:2470-2471 at 7e68a30f.
pub fn chat_text(frames: &[SseFrame]) -> String {
    let text = stream_text(frames);
    let mut out = String::new();
    for line in splitlines(&text) {
        if !line.starts_with("data: {") {
            continue;
        }
        let chunk: Value = match serde_json::from_str(line.get(6..).unwrap_or_default()) {
            Ok(v) => v,
            Err(e) => panic!("a data line that is not JSON ({e}): {line:?}"),
        };
        let Some(delta) = chunk
            .get("choices")
            .and_then(|c| c.get(0))
            .and_then(|c| c.get("delta"))
        else {
            panic!("a chunk with no choices[0].delta: {line:?}");
        };
        // `.get("content") or ""`: a missing or falsy content adds nothing.
        match delta.get("content") {
            None => {}
            Some(Value::String(piece)) => out.push_str(piece),
            Some(v) if is_falsy(v) => {}
            Some(other) => panic!("a delta content that is not a string ({other}): {line:?}"),
        }
    }
    out
}

/// The event names of a stream's frames, in order (`None` for frames without one).
pub fn event_names(frames: &[SseFrame]) -> Vec<Option<String>> {
    frames.iter().map(|f| f.event.clone()).collect()
}

/// Whether Python's truth test finds `v` false (`None`, `False`, zero, or an empty string,
/// list or object).
fn is_falsy(v: &Value) -> bool {
    match v {
        Value::Null => true,
        Value::Bool(b) => !b,
        Value::Number(n) => n.as_f64() == Some(0.0),
        Value::String(t) => t.is_empty(),
        Value::Array(a) => a.is_empty(),
        Value::Object(o) => o.is_empty(),
    }
}

/// Reads an event stream from one connection, frame by frame.
#[derive(Debug)]
pub struct SseReader {
    stream: TcpStream,
    head: RawResponse,
    /// The bytes read and not yet handed out start at `pos`; the buffer is compacted when
    /// `pos` passes half of it, so handing out a frame does not copy the rest each time.
    buf: Vec<u8>,
    pos: usize,
    /// How far past `pos` the buffer is known to hold no terminator.
    scanned: usize,
    raw: Vec<u8>,
    ended: bool,
}

/// Why [`SseReader::next_frame`] returned no frame.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SseEnd {
    /// The server closed the connection; any bytes after the last frame are kept.
    Closed {
        /// The bytes of an incomplete last frame.
        rest: Vec<u8>,
    },
    /// No complete frame within the time given.
    TimedOut,
    /// The stream grew past [`MAX_RESPONSE_BYTES`].
    TooLarge,
}

impl SseReader {
    /// Connects to `addr`, writes `request`, and reads the head (up to the blank line)
    /// within [`DEADLINE`]. Bytes that arrived after the head are kept for the first
    /// frames. Panics when no head arrives (the connection closed first, or the deadline
    /// passed); the head of a refused request is still returned, with its body in the
    /// buffer.
    pub async fn open(addr: SocketAddr, request: &[u8]) -> Self {
        let mut stream = raw::connect(addr).await;
        raw::write(&mut stream, request).await;
        let got = raw::read_until(&mut stream, |b| raw::contains(b, b"\r\n\r\n")).await;
        let Some(split) = raw::find(&got, b"\r\n\r\n") else {
            panic!(
                "the connection closed before a head: {:?}",
                String::from_utf8_lossy(&got)
            );
        };
        let head = raw::parse_response(got.get(..split + 4).unwrap_or_default());
        let buf = got.get(split + 4..).unwrap_or_default().to_vec();
        Self {
            stream,
            head,
            raw: got,
            buf,
            pos: 0,
            scanned: 0,
            ended: false,
        }
    }

    /// The head of the answer (its body is empty: the frames follow).
    pub fn head(&self) -> &RawResponse {
        &self.head
    }

    /// Every byte read so far, head included.
    pub fn raw(&self) -> &[u8] {
        &self.raw
    }

    /// The next frame, waiting at most `within`.
    pub async fn next_frame_within(&mut self, within: Duration) -> Result<SseFrame, SseEnd> {
        let deadline = tokio::time::Instant::now() + within;
        let mut chunk = vec![0u8; 65536];
        loop {
            let pending = self.buf.get(self.pos..).unwrap_or_default();
            if let Some(end) = frame_end_from(pending, self.scanned) {
                let frame = parse_frame(pending.get(..end).unwrap_or_default());
                self.pos += end;
                self.scanned = 0;
                if self.pos > self.buf.len() / 2 {
                    self.buf.drain(..self.pos);
                    self.pos = 0;
                }
                return Ok(frame);
            }
            self.scanned = pending.len();
            if self.ended {
                return Err(SseEnd::Closed {
                    rest: pending.to_vec(),
                });
            }
            if self.raw.len() > MAX_RESPONSE_BYTES {
                return Err(SseEnd::TooLarge);
            }
            let now = tokio::time::Instant::now();
            if now >= deadline {
                return Err(SseEnd::TimedOut);
            }
            match tokio::time::timeout(deadline - now, self.stream.read(&mut chunk)).await {
                Err(_) => return Err(SseEnd::TimedOut),
                Ok(Ok(0)) | Ok(Err(_)) => self.ended = true,
                Ok(Ok(n)) => {
                    let got = chunk.get(..n).unwrap_or_default();
                    self.buf.extend_from_slice(got);
                    self.raw.extend_from_slice(got);
                }
            }
        }
    }

    /// The next frame within [`DEADLINE`].
    pub async fn next_frame(&mut self) -> Result<SseFrame, SseEnd> {
        self.next_frame_within(DEADLINE).await
    }

    /// Frames up to and including the first one for which `stop` holds, within
    /// [`DEADLINE`] in all. Panics when the stream ends or the deadline passes first.
    pub async fn frames_until(&mut self, stop: impl Fn(&SseFrame) -> bool) -> Vec<SseFrame> {
        let deadline = tokio::time::Instant::now() + DEADLINE;
        let mut frames = Vec::new();
        loop {
            let left = deadline.saturating_duration_since(tokio::time::Instant::now());
            match self.next_frame_within(left).await {
                Ok(frame) => {
                    let done = stop(&frame);
                    frames.push(frame);
                    if done {
                        return frames;
                    }
                }
                Err(end) => panic!(
                    "the stream ended ({end:?}) before the frame waited for; frames so far: {frames:?}"
                ),
            }
        }
    }

    /// Frames up to and including `data: [DONE]`.
    pub async fn frames_until_done(&mut self) -> Vec<SseFrame> {
        self.frames_until(SseFrame::is_done).await
    }

    /// Every frame until the server closes the connection, within [`DEADLINE`]; panics on
    /// the deadline. Returns the frames and the bytes of an incomplete last frame.
    pub async fn frames_to_end(&mut self) -> SseParse {
        let deadline = tokio::time::Instant::now() + DEADLINE;
        let mut frames = Vec::new();
        loop {
            let left = deadline.saturating_duration_since(tokio::time::Instant::now());
            match self.next_frame_within(left).await {
                Ok(frame) => frames.push(frame),
                Err(SseEnd::Closed { rest }) => return SseParse { frames, rest },
                Err(end) => panic!("the stream did not end ({end:?}); frames so far: {frames:?}"),
            }
        }
    }

    /// Frames that arrive within `period`; the end of the period is not a failure, nor is
    /// the end of the stream. The donor's `read_for` over a stream, frame by frame.
    pub async fn frames_for(&mut self, period: Duration) -> Vec<SseFrame> {
        let deadline = tokio::time::Instant::now() + period;
        let mut frames = Vec::new();
        loop {
            let left = deadline.saturating_duration_since(tokio::time::Instant::now());
            match self.next_frame_within(left).await {
                Ok(frame) => frames.push(frame),
                Err(_) => return frames,
            }
        }
    }

    /// Closes the connection from the client side (a client that goes away).
    pub fn close(self) {
        drop(self.stream);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_three_donor_frame_shapes() {
        let bytes = b"data: {\"a\": 1}\n\n: keep-alive\n\nevent: message_start\ndata: {\"type\": \"message_start\"}\n\ndata: [DONE]\n\n";
        let p = parse_frames(bytes);
        assert!(p.rest.is_empty());
        assert_eq!(p.frames.len(), 4);
        assert_eq!(p.frames[0].raw, b"data: {\"a\": 1}\n\n");
        assert_eq!(p.frames[0].json(), Some(serde_json::json!({"a": 1})));
        assert!(p.frames[1].is_keep_alive() && p.frames[1].is_comment());
        assert_eq!(p.frames[1].raw, b": keep-alive\n\n");
        assert_eq!(p.frames[2].event.as_deref(), Some("message_start"));
        assert_eq!(p.frames[2].json().unwrap()["type"], "message_start");
        assert!(p.frames[3].is_done());
        assert_eq!(p.frames[3].json(), None);
        let joined: Vec<u8> = p.frames.iter().flat_map(|f| f.raw.clone()).collect();
        assert_eq!(joined, bytes, "the raw bytes of the frames are the stream");
        assert_eq!(data_json(&p.frames).len(), 2);
        assert_eq!(
            event_names(&p.frames),
            vec![None, None, Some("message_start".to_owned()), None]
        );
    }

    #[test]
    fn general_line_rules() {
        let f = parse_frame(b"data:one\r\ndata: two\r\nid: 7\r\nretry: 5\r\nfield\r\n:c\r\n\r\n");
        assert_eq!(f.data.as_deref(), Some("one\ntwo"));
        assert_eq!(f.id.as_deref(), Some("7"));
        assert_eq!(f.comments, vec!["c".to_owned()]);
        assert!(!f.is_comment());
        let only_data_field = parse_frame(b"data\n\n");
        assert_eq!(only_data_field.data.as_deref(), Some(""));
        let two_spaces = parse_frame(b"data:  x\n\n");
        assert_eq!(two_spaces.data.as_deref(), Some(" x"));
    }

    #[test]
    fn an_incomplete_frame_is_left_over() {
        let p = parse_frames(b"data: 1\n\ndata: 2\n");
        assert_eq!(p.frames.len(), 1);
        assert_eq!(p.rest, b"data: 2\n");
        let p = parse_frames(b"");
        assert!(p.frames.is_empty() && p.rest.is_empty());
        // A CRLF terminator that comes first ends the frame there.
        let p = parse_frames(b"data: a\r\n\r\ndata: b\n\n");
        assert_eq!(p.frames.len(), 2);
        assert_eq!(p.frames[0].raw, b"data: a\r\n\r\n");
    }

    #[test]
    fn chat_text_joins_the_deltas() {
        let p = parse_frames(
            b"data: {\"choices\": [{\"delta\": {\"role\": \"assistant\"}}]}\n\n\
data: {\"choices\": [{\"delta\": {\"content\": \"hel\"}}]}\n\n\
data: {\"choices\": [{\"delta\": {\"content\": \"lo\"}}]}\n\n\
data: {\"choices\": [{\"delta\": {\"content\": null}}]}\n\ndata: [DONE]\n\n",
        );
        assert_eq!(chat_text(&p.frames), "hello");
    }

    #[test]
    fn data_json_reads_line_by_line_as_the_donor() {
        // Two data lines in one frame are two values, as the donor's splitlines gives them;
        // a `data:` line with no space is not collected.
        let p = parse_frames(
            b"data: 1\ndata: {\"a\": 2}\n\ndata:3\n\n: keep-alive\n\ndata: [DONE]\n\n",
        );
        assert_eq!(
            data_json(&p.frames),
            vec![serde_json::json!(1), serde_json::json!({"a": 2})]
        );
        assert_eq!(splitlines("a\r\nb\rc\u{2028}d\n"), vec!["a", "b", "c", "d"]);
        assert_eq!(splitlines("x\n\ny"), vec!["x", "", "y"]);
        assert!(splitlines("").is_empty());
    }

    #[test]
    #[should_panic(expected = "a data line that is not JSON")]
    fn data_json_fails_on_a_data_line_that_is_not_json() {
        let p = parse_frames(b"data: {\"a\": 1}\n\ndata: {\"trunc\n\ndata: [DONE]\n\n");
        let _ = data_json(&p.frames);
    }

    #[test]
    #[should_panic(expected = "a chunk with no choices[0].delta")]
    fn chat_text_fails_on_a_chunk_without_a_delta() {
        let p = parse_frames(b"data: {\"choices\": [{\"delta\": {\"content\": \"a\"}}]}\n\ndata: {\"error\": {}}\n\n");
        let _ = chat_text(&p.frames);
    }

    #[test]
    fn the_frame_end_is_found_in_one_pass() {
        assert_eq!(frame_end(b"data: a\n\n"), Some(9));
        assert_eq!(frame_end(b"data: a\r\n\r\nmore\n\n"), Some(11));
        assert_eq!(
            frame_end(b"a\n\r\n"),
            None,
            "a CRLF terminator needs its first CR"
        );
        assert_eq!(
            frame_end(b"a\r\n\n"),
            Some(4),
            "an LF pair after a CR ends a frame"
        );
        assert_eq!(frame_end(b"data: a\r\n"), None);
        // Resuming past bytes already scanned finds a terminator split across reads.
        let bytes = b"data: abc\r\n\r\n";
        assert_eq!(frame_end_from(bytes, 10), Some(13));
        assert_eq!(frame_end_from(bytes, bytes.len()), Some(13));
        // A large stream of small frames parses in time linear in its size.
        let many = b"data: {}\n\n".repeat(200_000);
        let started = std::time::Instant::now();
        let p = parse_frames(&many);
        assert_eq!(p.frames.len(), 200_000);
        assert!(started.elapsed() < std::time::Duration::from_secs(20));
    }
}
