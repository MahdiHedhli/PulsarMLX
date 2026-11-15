//! The response reader: a state machine fed with the bytes of one connection.
//!
//! It finds the head (with `httparse`), records interim 1xx heads, decides the framing
//! from the final head, de-frames the body (Content-Length, chunked or to the end of the
//! connection), feeds the body to the parser its media type selects, and stops exactly at
//! a disconnect trigger. Every size it holds is bounded by [`ReadLimits`].
//!
//! A head that cannot be parsed, or chunked framing that breaks, does not stop the read:
//! the failure is kept ([`Reader::failure`]) and the rest of the connection is drained, so
//! that every byte the server sent reaches the record whatever the read sizes were. An
//! answer that does not start with `HTTP/` is an answer without a head (what Python's
//! `http.server` sends to an HTTP/0.9 request line such as `GET /health`, with no status
//! line and no headers): all of its bytes are kept as a body with [`Framing::Headless`].
//!
//! The head is parsed only when the bytes just received may end it (a blank line), while
//! it is still short (so that an answer without a head is seen at once), when it reaches
//! the size limit, and at end of file, so a head sent a byte at a time costs linear time.

use crate::observe::{
    latin1, ChunkRecord, Content, End, Framing, Header, NdjsonParser, ResponseHead, SseParser,
};

use super::ReadLimits;

/// The most header slots given to the head parser, whatever [`ReadLimits::max_headers`]
/// says.
const MAX_HEADER_SLOTS: usize = 4096;

/// A head buffer shorter than this is parsed after every read, so that bytes which cannot
/// start a status line are seen at once.
const EARLY_PARSE: usize = 64;

/// What feeding bytes led to.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum Fed {
    /// All bytes were taken; more are wanted.
    More,
    /// The response is complete (as its framing says).
    Complete,
    /// The event trigger was reached; the count of input bytes consumed is given.
    Triggered(usize),
    /// The response cannot be read further.
    Failed(End),
}

enum Parser {
    None,
    Sse(SseParser),
    Ndjson(NdjsonParser),
}

enum BodyKind {
    Json,
    Other,
}

enum Phase {
    Head,
    Body(Decoder),
    Done,
    /// After a malformed head or chunked framing: bytes are read to the end of the
    /// connection, and kept as the body when the answer has no head.
    Drain {
        headless: bool,
    },
}

enum Decoder {
    Length { remaining: u64 },
    Chunked(ChunkState),
    Close,
}

enum ChunkState {
    Size { line: Vec<u8> },
    Data { remaining: u64 },
    DataEnd { seen_cr: bool },
    Trailer { line: Vec<u8> },
}

/// The reader of one response.
pub(crate) struct Reader {
    limits: ReadLimits,
    head_request: bool,
    phase: Phase,
    head_buf: Vec<u8>,
    pub(crate) interim: Vec<ResponseHead>,
    pub(crate) head: Option<ResponseHead>,
    pub(crate) framing: Option<Framing>,
    pub(crate) body: Vec<u8>,
    parser: Parser,
    kind: BodyKind,
    /// The event count at which feeding stops; `None` for no event trigger.
    stop_at: Option<usize>,
    /// The malformation found, when the reader is draining.
    failure: Option<End>,
}

impl Reader {
    pub(crate) fn new(limits: ReadLimits, head_request: bool, stop_at: Option<usize>) -> Self {
        Self {
            limits,
            head_request,
            phase: Phase::Head,
            head_buf: Vec::new(),
            interim: Vec::new(),
            head: None,
            framing: None,
            body: Vec::new(),
            parser: Parser::None,
            kind: BodyKind::Other,
            stop_at,
            failure: None,
        }
    }

    /// The malformed head or framing found, if any; the read went on past it.
    pub(crate) fn failure(&self) -> Option<&End> {
        self.failure.as_ref()
    }

    /// Keeps a malformation and drains the rest. When no final head was read and the
    /// bytes so far do not start with `HTTP/`, the answer has no head: the head buffer
    /// becomes the start of the body.
    fn start_drain(&mut self, failure: End) {
        let headless = self.head.is_none() && !self.head_buf.starts_with(b"HTTP/");
        if headless {
            self.framing = Some(Framing::Headless);
            self.body = std::mem::take(&mut self.head_buf);
        }
        self.head_buf.clear();
        self.failure = Some(failure);
        self.phase = Phase::Drain { headless };
    }

    /// Whether a stream parser selected by the media type is running.
    fn streaming(&self) -> bool {
        !matches!(self.parser, Parser::None)
    }

    /// Drops the event trigger (after a half-close fired), so feeding goes on to the end.
    pub(crate) fn clear_trigger(&mut self) {
        self.stop_at = None;
    }

    /// Whether the final head has been read.
    pub(crate) fn has_head(&self) -> bool {
        self.head.is_some()
    }

    /// Stream events recorded so far.
    pub(crate) fn events(&self) -> usize {
        match &self.parser {
            Parser::None => 0,
            Parser::Sse(p) => p.event_count(),
            Parser::Ndjson(p) => p.line_count(),
        }
    }

    /// Feeds received bytes.
    pub(crate) fn feed(&mut self, input: &[u8]) -> Fed {
        let mut pos = 0;
        loop {
            match &mut self.phase {
                Phase::Done => return Fed::Complete,
                Phase::Drain { headless } => {
                    if *headless {
                        let rest = input.get(pos..).unwrap_or_default();
                        let room = self.limits.max_body_bytes.saturating_sub(self.body.len());
                        self.body
                            .extend_from_slice(rest.get(..room).unwrap_or(rest));
                        if rest.len() > room {
                            return Fed::Failed(End::LimitExceeded("body size".into()));
                        }
                    }
                    return Fed::More;
                }
                Phase::Head => {
                    let room = self
                        .limits
                        .max_head_bytes
                        .saturating_sub(self.head_buf.len());
                    let take = (input.len() - pos).min(room.max(1));
                    let start = self.head_buf.len();
                    self.head_buf.extend_from_slice(&input[pos..pos + take]);
                    let window = self
                        .head_buf
                        .get(start.saturating_sub(3)..)
                        .unwrap_or_default();
                    let may_end = start < EARLY_PARSE
                        || self.head_buf.len() >= self.limits.max_head_bytes
                        || find(window, b"\n\n")
                        || find(window, b"\n\r\n");
                    let parsed = if may_end { self.parse_head() } else { Ok(None) };
                    match parsed {
                        Ok(Some(len)) => {
                            // Bytes of this input past the head go on to the body (or to the
                            // next head after an interim response).
                            let used = len.saturating_sub(start);
                            pos += used;
                            self.head_buf.clear();
                            if let Phase::Done = self.phase {
                                return Fed::Complete;
                            }
                            if self.stop_at == Some(0)
                                && matches!(self.phase, Phase::Body(_))
                                && self.streaming()
                            {
                                return Fed::Triggered(pos);
                            }
                            continue;
                        }
                        Ok(None) => {
                            pos += take;
                            if self.head_buf.len() >= self.limits.max_head_bytes {
                                return Fed::Failed(End::LimitExceeded("head size".into()));
                            }
                            if pos >= input.len() {
                                return Fed::More;
                            }
                        }
                        Err(end @ End::Malformed(_)) => {
                            pos += take;
                            self.start_drain(end);
                        }
                        Err(end) => return Fed::Failed(end),
                    }
                }
                Phase::Body(_) => {
                    if pos >= input.len() {
                        return Fed::More;
                    }
                    return match self.feed_body(&input[pos..]) {
                        Fed::Triggered(n) => Fed::Triggered(pos + n),
                        Fed::Failed(end @ End::Malformed(_)) => {
                            // The rest of this read is already in the wire record.
                            self.start_drain(end);
                            Fed::More
                        }
                        other => other,
                    };
                }
            }
        }
    }

    /// Tries to parse the head buffer. `Ok(Some(len))` when a head of `len` bytes was
    /// read (interim or final).
    fn parse_head(&mut self) -> Result<Option<usize>, End> {
        let slots = self.limits.max_headers.min(MAX_HEADER_SLOTS);
        let mut headers = vec![httparse::EMPTY_HEADER; slots];
        let mut resp = httparse::Response::new(&mut headers);
        let len = match resp.parse(&self.head_buf) {
            Ok(httparse::Status::Complete(len)) => len,
            Ok(httparse::Status::Partial) => return Ok(None),
            Err(httparse::Error::TooManyHeaders) => {
                return Err(End::LimitExceeded("header count".into()))
            }
            Err(e) => return Err(End::Malformed(format!("response head: {e}"))),
        };
        let code = resp.code.unwrap_or(0);
        let version = format!("HTTP/1.{}", resp.version.unwrap_or(0));
        let raw = self
            .head_buf
            .get(..len)
            .map(<[u8]>::to_vec)
            .unwrap_or_default();
        let headers: Vec<Header> = resp
            .headers
            .iter()
            .map(|h| Header {
                name: h.name.to_string(),
                value: latin1(h.value),
            })
            .collect();
        let head = ResponseHead {
            version,
            code,
            reason: reason_phrase(&raw),
            headers,
            raw,
        };
        if (100..200).contains(&code) && code != 101 {
            if self.interim.len() >= self.limits.max_interim {
                return Err(End::LimitExceeded("interim responses".into()));
            }
            self.interim.push(head);
            return Ok(Some(len));
        }
        self.start_body(head)?;
        Ok(Some(len))
    }

    fn start_body(&mut self, head: ResponseHead) -> Result<(), End> {
        let media = head.media_type();
        let (framing, decoder) = framing_of(&head, self.head_request)?;
        match media.as_deref() {
            Some("text/event-stream") => self.parser = Parser::Sse(SseParser::new()),
            Some("application/x-ndjson") => self.parser = Parser::Ndjson(NdjsonParser::new()),
            Some("application/json") => self.kind = BodyKind::Json,
            _ => {}
        }
        self.framing = Some(framing);
        self.head = Some(head);
        self.phase = match decoder {
            Some(d) => Phase::Body(d),
            None => Phase::Done,
        };
        Ok(())
    }

    fn feed_body(&mut self, input: &[u8]) -> Fed {
        let mut pos = 0;
        while pos < input.len() {
            let rest = &input[pos..];
            let step = match &mut self.phase {
                Phase::Done | Phase::Head | Phase::Drain { .. } => return Fed::Complete,
                Phase::Body(Decoder::Close) => Step::Data {
                    skip: 0,
                    len: rest.len(),
                },
                Phase::Body(Decoder::Length { remaining }) => Step::Data {
                    skip: 0,
                    len: usize::try_from(*remaining)
                        .unwrap_or(usize::MAX)
                        .min(rest.len()),
                },
                Phase::Body(Decoder::Chunked(state)) => {
                    match chunk_step(state, rest, &self.limits, &mut self.framing) {
                        Ok(step) => step,
                        Err(end) => return Fed::Failed(end),
                    }
                }
            };
            match step {
                Step::Need => return Fed::More,
                Step::Done => {
                    self.phase = Phase::Done;
                    return Fed::Complete;
                }
                Step::Data { skip, len } => {
                    let slice = rest.get(skip..skip + len).unwrap_or_default();
                    let (taken, triggered) = self.on_body(slice);
                    let taken_u64 = u64::try_from(taken).unwrap_or(u64::MAX);
                    match &mut self.phase {
                        Phase::Body(Decoder::Length { remaining }) => {
                            *remaining = remaining.saturating_sub(taken_u64);
                            if *remaining == 0 {
                                self.phase = Phase::Done;
                            }
                        }
                        Phase::Body(Decoder::Chunked(state)) => {
                            if let ChunkState::Data { remaining } = state {
                                *remaining = remaining.saturating_sub(taken_u64);
                                if *remaining == 0 {
                                    *state = ChunkState::DataEnd { seen_cr: false };
                                }
                            }
                        }
                        _ => {}
                    }
                    pos += skip + taken;
                    if self.body.len() > self.limits.max_body_bytes {
                        return Fed::Failed(End::LimitExceeded("body size".into()));
                    }
                    if self.events() > self.limits.max_events {
                        return Fed::Failed(End::LimitExceeded("event count".into()));
                    }
                    if self.lines() > self.limits.max_lines {
                        return Fed::Failed(End::LimitExceeded("line count".into()));
                    }
                    if triggered {
                        return Fed::Triggered(pos);
                    }
                    if matches!(self.phase, Phase::Done) {
                        return Fed::Complete;
                    }
                }
            }
        }
        Fed::More
    }

    /// Records body bytes and feeds them to the stream parser. Returns the bytes taken
    /// and whether the event trigger was reached.
    fn on_body(&mut self, slice: &[u8]) -> (usize, bool) {
        let (taken, hit) = match &mut self.parser {
            Parser::None => (slice.len(), false),
            Parser::Sse(p) => p.feed(slice, self.stop_at),
            Parser::Ndjson(p) => p.feed(slice, self.stop_at),
        };
        let taken = taken.min(slice.len());
        self.body.extend_from_slice(&slice[..taken]);
        (taken, hit && self.stop_at.is_some())
    }

    /// Whether the body is complete by its framing.
    pub(crate) fn complete(&self) -> bool {
        matches!(self.phase, Phase::Done)
    }

    /// Whether the body runs to the end of the connection.
    pub(crate) fn close_delimited(&self) -> bool {
        matches!(self.phase, Phase::Body(Decoder::Close))
    }

    /// Non-blank SSE lines (comments and field lines) read so far.
    fn lines(&self) -> usize {
        match &self.parser {
            Parser::Sse(p) => p.line_count(),
            Parser::None | Parser::Ndjson(_) => 0,
        }
    }

    /// Marks a close-delimited body complete at end of file. A partial head is parsed
    /// once more, so that bytes which cannot be a head (an answer without one) are kept.
    pub(crate) fn eof(&mut self) {
        if self.close_delimited() {
            self.phase = Phase::Done;
        }
        if matches!(self.phase, Phase::Head) && !self.head_buf.is_empty() {
            if let Err(end @ End::Malformed(_)) = self.parse_head() {
                self.start_drain(end);
            }
        }
    }

    /// Ends reading and returns the parsed content.
    pub(crate) fn content(&mut self) -> Content {
        match std::mem::replace(&mut self.parser, Parser::None) {
            Parser::Sse(p) => Content::Sse(p.finish()),
            Parser::Ndjson(p) => Content::Ndjson(p.finish()),
            Parser::None => match self.kind {
                BodyKind::Json => match serde_json::from_slice(&self.body) {
                    Ok(v) => Content::Json(v),
                    Err(e) => Content::InvalidJson(e.to_string()),
                },
                BodyKind::Other => Content::Opaque,
            },
        }
    }
}

/// Whether `needle` occurs in `hay`.
fn find(hay: &[u8], needle: &[u8]) -> bool {
    hay.windows(needle.len()).any(|w| w == needle)
}

/// The reason phrase: the status line after the second space, decoded as ISO-8859-1.
fn reason_phrase(raw: &[u8]) -> String {
    let line_end = raw.iter().position(|&b| b == b'\n').unwrap_or(raw.len());
    let line = raw.get(..line_end).unwrap_or_default();
    let line = line.strip_suffix(b"\r").unwrap_or(line);
    let mut parts = line.splitn(3, |&b| b == b' ');
    let _version = parts.next();
    let _code = parts.next();
    latin1(parts.next().unwrap_or_default())
}

/// The framing of a response, as a client must decide it (RFC 9112 section 6.3).
fn framing_of(head: &ResponseHead, head_request: bool) -> Result<(Framing, Option<Decoder>), End> {
    if head_request || head.code == 204 || head.code == 304 || (100..200).contains(&head.code) {
        return Ok((Framing::NoBody, None));
    }
    let codings: Vec<String> = head
        .headers_named("transfer-encoding")
        .flat_map(|v| v.split(','))
        .map(|c| c.trim().to_ascii_lowercase())
        .filter(|c| !c.is_empty())
        .collect();
    if let Some(last) = codings.last() {
        if last == "chunked" {
            return Ok((
                Framing::Chunked {
                    chunks: Vec::new(),
                    trailers: Vec::new(),
                },
                Some(Decoder::Chunked(ChunkState::Size { line: Vec::new() })),
            ));
        }
        return Ok((Framing::CloseDelimited, Some(Decoder::Close)));
    }
    let mut length: Option<u64> = None;
    for value in head.headers_named("content-length") {
        for part in value.split(',') {
            let part = part.trim();
            let parsed = if !part.is_empty() && part.bytes().all(|b| b.is_ascii_digit()) {
                part.parse::<u64>().ok()
            } else {
                None
            };
            let Some(n) = parsed else {
                return Err(End::Malformed(format!("Content-Length {value:?}")));
            };
            if length.is_some_and(|l| l != n) {
                return Err(End::Malformed("Content-Length values differ".into()));
            }
            length = Some(n);
        }
    }
    match length {
        Some(0) => Ok((Framing::ContentLength(0), None)),
        Some(n) => Ok((
            Framing::ContentLength(n),
            Some(Decoder::Length { remaining: n }),
        )),
        None => Ok((Framing::CloseDelimited, Some(Decoder::Close))),
    }
}

/// What the chunked decoder found in the input it was given.
enum Step {
    /// Every byte was a control byte; more input is needed.
    Need,
    /// Data bytes: `len` of them after `skip` control bytes.
    Data { skip: usize, len: usize },
    /// The chunked body ended (the blank line after the trailers was read).
    Done,
}

/// One step of the chunked decoder over `input`: control bytes are consumed until data
/// bytes are available, the body ends, or the input runs out.
fn chunk_step(
    state: &mut ChunkState,
    input: &[u8],
    limits: &ReadLimits,
    framing: &mut Option<Framing>,
) -> Result<Step, End> {
    let mut i = 0;
    while let Some(&b) = input.get(i) {
        if let ChunkState::Data { remaining } = state {
            let len = usize::try_from(*remaining)
                .unwrap_or(usize::MAX)
                .min(input.len() - i);
            return Ok(Step::Data { skip: i, len });
        }
        i += 1;
        match state {
            ChunkState::Data { .. } => {}
            ChunkState::Size { line } => {
                if b != b'\n' {
                    if line.len() >= limits.max_chunk_line {
                        return Err(End::LimitExceeded("chunk size line".into()));
                    }
                    line.push(b);
                    continue;
                }
                let text = latin1(line.strip_suffix(b"\r").unwrap_or(line));
                let (size_text, ext) = match text.split_once(';') {
                    Some((s, e)) => (s, e.to_string()),
                    None => (text.as_str(), String::new()),
                };
                let size_text = size_text.trim_matches([' ', '\t']);
                let valid = !size_text.is_empty()
                    && size_text.len() <= 16
                    && size_text.bytes().all(|c| c.is_ascii_hexdigit());
                let size = if valid {
                    u64::from_str_radix(size_text, 16).ok()
                } else {
                    None
                };
                let Some(size) = size else {
                    return Err(End::Malformed(format!("chunk size line {text:?}")));
                };
                if let Some(Framing::Chunked { chunks, .. }) = framing {
                    if chunks.len() >= limits.max_chunks {
                        return Err(End::LimitExceeded("chunk count".into()));
                    }
                    chunks.push(ChunkRecord { size, ext });
                }
                *state = if size == 0 {
                    ChunkState::Trailer { line: Vec::new() }
                } else {
                    ChunkState::Data { remaining: size }
                };
            }
            ChunkState::DataEnd { seen_cr } => match (b, *seen_cr) {
                (b'\r', false) => *seen_cr = true,
                (b'\n', _) => *state = ChunkState::Size { line: Vec::new() },
                _ => return Err(End::Malformed("no line end after chunk data".into())),
            },
            ChunkState::Trailer { line } => {
                if b != b'\n' {
                    if line.len() >= limits.max_chunk_line {
                        return Err(End::LimitExceeded("trailer line".into()));
                    }
                    line.push(b);
                    continue;
                }
                let text = line.strip_suffix(b"\r").unwrap_or(line);
                if text.is_empty() {
                    return Ok(Step::Done);
                }
                let text = latin1(text);
                if let Some(Framing::Chunked { trailers, .. }) = framing {
                    if trailers.len() >= limits.max_trailers {
                        return Err(End::LimitExceeded("trailer count".into()));
                    }
                    let (name, value) = text.split_once(':').unwrap_or((text.as_str(), ""));
                    trailers.push(Header {
                        name: name.trim().to_string(),
                        value: value.trim().to_string(),
                    });
                }
                line.clear();
            }
        }
    }
    Ok(Step::Need)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Feeds `wire` in pieces of `step` bytes, then end of file.
    fn run(wire: &[u8], step: usize, stop_at: Option<usize>) -> (Reader, Fed, Content) {
        let mut r = Reader::new(ReadLimits::default(), false, stop_at);
        let mut fed = Fed::More;
        for piece in wire.chunks(step.max(1)) {
            fed = r.feed(piece);
            if fed != Fed::More {
                break;
            }
        }
        if fed == Fed::More {
            r.eof();
        }
        let content = r.content();
        (r, fed, content)
    }

    const SSE: &[u8] = b"data: {\"a\": \"\xc3\xa9\"}\n\n: keep-alive\n\ndata: [DONE]\n\n";

    fn chunked(body: &[u8], size: usize) -> Vec<u8> {
        let mut out = Vec::new();
        for c in body.chunks(size) {
            out.extend_from_slice(format!("{:x}\r\n", c.len()).as_bytes());
            out.extend_from_slice(c);
            out.extend_from_slice(b"\r\n");
        }
        out.extend_from_slice(b"0\r\n\r\n");
        out
    }

    #[test]
    fn the_three_framings_give_the_same_body_and_events() {
        let head = b"HTTP/1.0 200 OK\r\nContent-Type: text/event-stream\r\n";
        let mut cl = head.to_vec();
        cl.extend_from_slice(format!("Content-Length: {}\r\n\r\n", SSE.len()).as_bytes());
        cl.extend_from_slice(SSE);
        let mut ch = head.to_vec();
        ch.extend_from_slice(b"Transfer-Encoding: chunked\r\n\r\n");
        ch.extend_from_slice(&chunked(SSE, 3));
        let mut close = head.to_vec();
        close.extend_from_slice(b"\r\n");
        close.extend_from_slice(SSE);
        for step in [1, 2, 7, 4096] {
            let results: Vec<_> = [&cl, &ch, &close]
                .iter()
                .map(|w| run(w, step, None))
                .collect();
            for (r, fed, content) in &results {
                assert!(r.complete(), "step {step}");
                assert_ne!(*fed, Fed::Failed(End::Truncated));
                assert_eq!(r.body, SSE);
                assert!(matches!(content, Content::Sse(s) if s.events.len() == 2));
            }
            assert_eq!(results[0].2, results[1].2);
            assert_eq!(results[1].2, results[2].2);
        }
        let (r, _, _) = run(&ch, 5, None);
        match &r.framing {
            Some(Framing::Chunked { chunks, trailers }) => {
                assert_eq!(chunks.len(), SSE.len().div_ceil(3) + 1);
                assert_eq!(chunks.last().map(|c| c.size), Some(0));
                assert!(trailers.is_empty());
            }
            other => panic!("framing {other:?}"),
        }
    }

    #[test]
    fn chunk_extensions_and_trailers_are_recorded() {
        let wire = b"HTTP/1.1 200 OK\r\nTransfer-Encoding: gzip, chunked\r\n\r\n\
3;name=v\r\nabc\r\n0\r\nX-T: 1\r\n\r\n";
        let (r, fed, _) = run(wire, 1, None);
        assert_eq!(fed, Fed::Complete);
        assert_eq!(r.body, b"abc");
        assert_eq!(
            r.framing,
            Some(Framing::Chunked {
                chunks: vec![
                    ChunkRecord {
                        size: 3,
                        ext: "name=v".into()
                    },
                    ChunkRecord {
                        size: 0,
                        ext: String::new()
                    }
                ],
                trailers: vec![Header {
                    name: "X-T".into(),
                    value: "1".into()
                }],
            })
        );
    }

    #[test]
    fn malformed_chunks_and_lengths_are_reported_and_drained() {
        let cases: [(&[u8], usize); 5] = [
            (
                b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\nzz\r\nmore",
                4,
            ),
            (
                b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n1\r\nab",
                4,
            ),
            (b"HTTP/1.0 200 OK\r\nContent-Length: -5\r\n\r\nxyz", 4),
            (
                b"HTTP/1.0 200 OK\r\nContent-Length: 2\r\nContent-Length: 3\r\n\r\n",
                64,
            ),
            (b"HTTP/1.0 200 OK\r\nX-Bad: a\x01b\r\n\r\nbody", 1),
        ];
        for (wire, step) in cases {
            for step in [step, 1, 4096] {
                // The read is not stopped: every piece is taken, and nothing is a body.
                let (r, fed, _) = run(wire, step, None);
                assert_eq!(fed, Fed::More, "{wire:?}");
                assert!(matches!(r.failure(), Some(End::Malformed(_))), "{wire:?}");
                assert_ne!(r.framing, Some(Framing::Headless), "{wire:?}");
                assert!(r.body.len() <= 1, "{wire:?}");
            }
        }
        // The same Content-Length twice is one length.
        let (r, fed, _) = run(
            b"HTTP/1.0 200 OK\r\nContent-Length: 2, 2\r\n\r\nok",
            64,
            None,
        );
        assert_eq!((fed, r.body.as_slice()), (Fed::Complete, &b"ok"[..]));
    }

    #[test]
    fn a_short_content_length_body_is_not_complete() {
        let (r, fed, _) = run(
            b"HTTP/1.0 200 OK\r\nContent-Length: 10\r\n\r\nabc",
            64,
            None,
        );
        assert_eq!(fed, Fed::More);
        assert!(!r.complete());
    }

    #[test]
    fn interim_heads_are_recorded_and_no_body_statuses_end_at_the_head() {
        let wire = b"HTTP/1.1 100 Continue\r\n\r\nHTTP/1.1 204 No Content\r\nX: y\r\n\r\n";
        let (r, fed, _) = run(wire, 3, None);
        assert_eq!(fed, Fed::Complete);
        assert_eq!(r.interim.len(), 1);
        assert_eq!(r.interim[0].code, 100);
        assert_eq!(r.head.as_ref().map(|h| h.code), Some(204));
        assert_eq!(r.framing, Some(Framing::NoBody));
        let mut head_req = Reader::new(ReadLimits::default(), true, None);
        assert_eq!(
            head_req.feed(b"HTTP/1.0 200 OK\r\nContent-Length: 5\r\n\r\n"),
            Fed::Complete
        );
    }

    #[test]
    fn the_status_line_and_headers_are_kept_as_sent() {
        let wire = b"HTTP/1.0 418 I'm a teapot \xe9\r\nX-A: 1\r\nx-a:  2 \r\nServer: s\r\n\r\n";
        let (r, _, _) = run(wire, 1, None);
        let head = r.head.unwrap_or_else(|| panic!("no head"));
        assert_eq!(head.version, "HTTP/1.0");
        assert_eq!(head.code, 418);
        assert_eq!(head.reason, "I'm a teapot \u{e9}");
        let names: Vec<_> = head
            .headers
            .iter()
            .map(|h| (h.name.as_str(), h.value.as_str()))
            .collect();
        assert_eq!(names, [("X-A", "1"), ("x-a", "2"), ("Server", "s")]);
        assert_eq!(head.raw, wire);
    }

    #[test]
    fn limits_stop_the_read() {
        let limits = ReadLimits {
            max_head_bytes: 32,
            ..ReadLimits::default()
        };
        let mut r = Reader::new(limits, false, None);
        let fed = r.feed(b"HTTP/1.0 200 OK\r\nX-Long: aaaaaaaaaaaaaaaaaaaaaaaaaaaaa\r\n\r\n");
        assert_eq!(fed, Fed::Failed(End::LimitExceeded("head size".into())));
        let limits = ReadLimits {
            max_body_bytes: 4,
            ..ReadLimits::default()
        };
        let mut r = Reader::new(limits, false, None);
        let fed = r.feed(b"HTTP/1.0 200 OK\r\n\r\n0123456789");
        assert_eq!(fed, Fed::Failed(End::LimitExceeded("body size".into())));
        let limits = ReadLimits {
            max_headers: 2,
            ..ReadLimits::default()
        };
        let mut r = Reader::new(limits, false, None);
        let fed = r.feed(b"HTTP/1.0 200 OK\r\nA: 1\r\nB: 2\r\nC: 3\r\n\r\n");
        assert_eq!(fed, Fed::Failed(End::LimitExceeded("header count".into())));
    }

    #[test]
    fn an_event_trigger_stops_exactly_inside_a_chunk() {
        let head = b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nTransfer-Encoding: chunked\r\n\r\n";
        let body = b"data: 1\n\ndata: 2\n\ndata: 3\n\n";
        let mut wire = head.to_vec();
        wire.extend_from_slice(&chunked(body, 64));
        let mut r = Reader::new(ReadLimits::default(), false, Some(2));
        let fed = r.feed(&wire);
        let Fed::Triggered(used) = fed else {
            panic!("fed {fed:?}");
        };
        assert_eq!(r.body, b"data: 1\n\ndata: 2\n\n");
        assert_eq!(used, head.len() + 4 + r.body.len());
        // After the trigger is cleared, the rest of the read completes the body.
        r.clear_trigger();
        assert_eq!(r.feed(&wire[used..]), Fed::Complete);
        assert_eq!(r.body, body);
    }

    #[test]
    fn zero_events_fires_at_the_head() {
        let wire = b"HTTP/1.0 200 OK\r\nContent-Type: application/x-ndjson\r\n\r\n{}\n";
        let mut r = Reader::new(ReadLimits::default(), false, Some(0));
        assert_eq!(r.feed(wire), Fed::Triggered(wire.len() - 3));
        assert!(r.body.is_empty());
    }

    #[test]
    fn zero_events_never_fires_for_another_media_type() {
        let wire = b"HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n\r\n{\"a\": 1}";
        let (r, fed, content) = run(wire, 4096, Some(0));
        assert_eq!(fed, Fed::More);
        assert!(r.complete());
        assert_eq!(content, Content::Json(serde_json::json!({"a": 1})));
        let wire = b"HTTP/1.0 200 OK\r\nContent-Length: 2\r\n\r\nok";
        let (r, fed, _) = run(wire, 4096, Some(0));
        assert_eq!((fed, r.body.as_slice()), (Fed::Complete, &b"ok"[..]));
    }

    #[test]
    fn an_answer_without_a_head_is_kept_whole_whatever_the_read_sizes() {
        let wire = b"{\"ok\": true}\n\nand more after a blank line";
        let mut seen = Vec::new();
        for step in [1, 2, 3, 7, 4096] {
            let (r, fed, content) = run(wire, step, None);
            assert_eq!(fed, Fed::More, "step {step}");
            assert_eq!(r.body, wire, "step {step}");
            assert_eq!(r.framing, Some(Framing::Headless));
            assert_eq!(r.head, None);
            assert_eq!(content, Content::Opaque);
            seen.push(format!("{:?}", r.failure()));
        }
        assert!(seen
            .iter()
            .all(|f| f == &seen[0] && f.contains("Malformed")));
        // Bytes that could still start a status line are parsed once more at the end.
        let (r, _, _) = run(b"HTX", 1, None);
        assert_eq!(r.body, b"HTX");
        assert_eq!(r.framing, Some(Framing::Headless));
        let (r, _, _) = run(b"HTT", 1, None);
        assert_eq!((r.failure(), r.framing.as_ref()), (None, None));
        // A body longer than the head limit without a blank line is kept too.
        let long = vec![b'x'; 70 * 1024];
        let (r, _, _) = run(&long, 1000, None);
        assert_eq!(r.body, long);
    }

    #[test]
    fn sse_comment_lines_are_bounded() {
        let limits = ReadLimits {
            max_lines: 100,
            ..ReadLimits::default()
        };
        let mut wire = b"HTTP/1.0 200 OK\r\nContent-Type: text/event-stream\r\n\r\n".to_vec();
        wire.extend(std::iter::repeat_n(&b":\n"[..], 200).flatten());
        let mut r = Reader::new(limits, false, None);
        assert_eq!(
            r.feed(&wire),
            Fed::Failed(End::LimitExceeded("line count".into()))
        );
        let mut wire = b"HTTP/1.0 200 OK\r\nContent-Type: text/event-stream\r\n\r\n".to_vec();
        wire.extend(std::iter::repeat_n(&b"a\n"[..], 200).flatten());
        let mut r = Reader::new(limits, false, None);
        assert_eq!(
            r.feed(&wire),
            Fed::Failed(End::LimitExceeded("line count".into()))
        );
    }

    #[test]
    fn a_huge_header_count_limit_is_clamped() {
        let limits = ReadLimits {
            max_headers: usize::MAX,
            ..ReadLimits::default()
        };
        let mut r = Reader::new(limits, false, None);
        assert_eq!(
            r.feed(b"HTTP/1.0 200 OK\r\nContent-Length: 0\r\n\r\n"),
            Fed::Complete
        );
    }

    #[test]
    fn a_head_sent_a_byte_at_a_time_is_parsed_once_it_ends() {
        let mut wire = b"HTTP/1.0 200 OK\r\n".to_vec();
        for k in 0..100 {
            wire.extend_from_slice(format!("X-H{k}: {}\r\n", "v".repeat(300)).as_bytes());
        }
        wire.extend_from_slice(b"Content-Length: 2\r\n\r\nok");
        let (r, fed, _) = run(&wire, 1, None);
        assert_eq!(fed, Fed::Complete);
        assert_eq!(r.head.as_ref().map(|h| h.headers.len()), Some(101));
        assert_eq!(r.body, b"ok");
    }

    #[test]
    fn json_bodies_parse_with_key_order_and_number_text_kept() {
        let wire =
            b"HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n\r\n{\"z\": 1.50, \"a\": [1e2]}";
        let (_, _, content) = run(wire, 5, None);
        let Content::Json(v) = content else {
            panic!("content {content:?}");
        };
        let keys: Vec<&String> = v
            .as_object()
            .map(|m| m.keys().collect())
            .unwrap_or_default();
        assert_eq!(keys, ["z", "a"]);
        assert_eq!(v["z"].to_string(), "1.50");
        let wire = b"HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n\r\n{\"x\": NaN}";
        let (_, _, content) = run(wire, 5, None);
        assert!(matches!(content, Content::InvalidJson(_)));
    }
}
