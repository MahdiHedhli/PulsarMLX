//! The request head: the request line and the headers, read as CPython 3.14's
//! `BaseHTTPRequestHandler.parse_request` and `http.client.parse_headers` read them.
//!
//! The parsing is Python's, not a strict HTTP/1.1 grammar, because what the donor accepts
//! and refuses is part of the behavior:
//!
//! - The request line is at most 65536 bytes with its line ending (414 beyond), decoded as
//!   Latin-1, stripped of trailing `\r` and `\n` and split on Python whitespace. An empty
//!   line closes the connection without an answer. Three words give a version, which must
//!   be `HTTP/<digits>.<digits>` with at most ten digits each (400 "Bad request version"),
//!   below 2.0 (505); two words are an HTTP/0.9 `GET` (400 for another method), other counts
//!   are 400 "Bad request syntax". A path that starts with `//` is reduced to one `/`.
//! - Header lines are read up to the blank line, each at most 65536 bytes (431 "Line too
//!   long") and at most 100 lines counting the blank one (431 "Too many headers"). They are
//!   then parsed as the `email` package does: lines split at `\r\n`, `\r` or `\n`; the first
//!   line that is neither `Name:` (name characters `!` to `~` except `:`), a continuation
//!   (leading space or tab) nor `From ` ends the headers, and the rest is ignored; a value
//!   keeps its continuation lines and loses leading whitespace and trailing line breaks.
//!   Header lookup is case-insensitive and returns the first match.
//!
//! Behavior reference: project-maya serve/server.py:5403-5410 at 7e68a30f, and CPython 3.14
//! `Lib/http/server.py` (`handle_one_request`, `parse_request`), `Lib/http/client.py`
//! (`_read_headers`, `_MAXLINE`, `_MAXHEADERS`), `Lib/email/feedparser.py` (`headerRE`,
//! `_parse_headers`) and `Lib/email/_policybase.py` (`Compat32.header_source_parse`).

use std::time::Duration;

use console_pyjson::pystr;
use tokio::io::AsyncBufRead;

use super::io::{read_line, ReadFail};
use super::wire::{from_latin1, py_repr, ErrorPage};

/// The longest request line or header line, in bytes with its line ending.
pub const MAX_LINE: usize = 65536;

/// The most header lines, counting the blank line that ends them.
pub const MAX_HEADERS: usize = 100;

/// The request headers, in arrival order, as Latin-1 text.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct Headers {
    entries: Vec<(String, String)>,
}

impl Headers {
    /// Headers from `(name, value)` pairs, in order.
    pub fn from_pairs(entries: Vec<(String, String)>) -> Self {
        Self { entries }
    }

    /// The value of the first header named `name`, compared case-insensitively (Python's
    /// `Message.get`).
    pub fn get(&self, name: &str) -> Option<&str> {
        self.entries
            .iter()
            .find(|(k, _)| k.eq_ignore_ascii_case(name))
            .map(|(_, v)| v.as_str())
    }

    /// Every value of the headers named `name`, in order (Python's `Message.get_all`).
    pub fn get_all<'a>(&'a self, name: &'a str) -> impl Iterator<Item = &'a str> + 'a {
        self.entries
            .iter()
            .filter(move |(k, _)| k.eq_ignore_ascii_case(name))
            .map(|(_, v)| v.as_str())
    }

    /// All headers in order.
    pub fn iter(&self) -> impl Iterator<Item = (&str, &str)> {
        self.entries.iter().map(|(k, v)| (k.as_str(), v.as_str()))
    }

    /// The number of headers.
    pub fn len(&self) -> usize {
        self.entries.len()
    }

    /// True when there are none.
    pub fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }
}

/// A parsed request head.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RequestHead {
    method: String,
    path: String,
    version: String,
    headers: Headers,
}

impl RequestHead {
    /// A head from its parts (for tests and fixture servers).
    pub fn new(method: &str, path: &str, version: &str, headers: Headers) -> Self {
        Self {
            method: method.to_owned(),
            path: path.to_owned(),
            version: version.to_owned(),
            headers,
        }
    }

    /// The method, exactly as sent (case-sensitive: `get` is not `GET`).
    pub fn method(&self) -> &str {
        &self.method
    }

    /// The raw request target, query string included (Python's `self.path`, after the
    /// `//` reduction).
    pub fn path(&self) -> &str {
        &self.path
    }

    /// The path the router matches: the query string dropped and trailing slashes removed
    /// (`self.path.split("?")[0].rstrip("/")`), so `/` becomes the empty string.
    ///
    /// Behavior reference: project-maya serve/server.py:6165 at 7e68a30f.
    pub fn route_path(&self) -> &str {
        let before_query = self.path.split('?').next().unwrap_or("");
        before_query.trim_end_matches('/')
    }

    /// The text after the first `?`, without it, or `""`.
    pub fn query(&self) -> &str {
        self.path.split_once('?').map_or("", |(_, q)| q)
    }

    /// The version as sent (`HTTP/1.1`, `HTTP/1.0`), or `HTTP/0.9` for a two-word request
    /// line.
    pub fn version(&self) -> &str {
        &self.version
    }

    /// True when the answer is written as HTTP/0.9: the version text is exactly `HTTP/0.9`,
    /// so Python writes neither the status line nor headers, only the body.
    pub fn is_http09(&self) -> bool {
        self.version == "HTTP/0.9"
    }

    /// The headers (empty for an HTTP/0.9 request).
    pub fn headers(&self) -> &Headers {
        &self.headers
    }
}

/// What reading a request head ended with.
#[derive(Debug)]
pub(crate) enum HeadOutcome {
    /// A request to hand to the method check and the handler.
    Request(RequestHead),
    /// Nothing to answer: close the connection (empty request line, or end of file).
    Close,
    /// An error page to send, then close. `method` is Python's `self.command` at that point
    /// (a `HEAD` page has no body); `http09` suppresses the status line and headers.
    /// `target` is Python's `self.path` and `request_version` when they are already set (the
    /// 431 pages only), so that the end-headers hook can run as the donor's does.
    Refuse {
        page: ErrorPage,
        method: Option<String>,
        target: Option<(String, String)>,
        http09: bool,
    },
}

/// The request line, parsed.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum RequestLine {
    /// A usable request line.
    Line {
        method: String,
        path: String,
        version: String,
        two_words: bool,
    },
    /// No words: close without an answer.
    Empty,
    /// An error page. CPython sets `self.request_version = ''` right before each 400 of the
    /// request line, and sets it to the (accepted, below-2.0-checked) version before the 505,
    /// so every one of these pages is written with its status line and headers; only a
    /// request version of exactly `HTTP/0.9` suppresses them.
    Refuse(ErrorPage),
}

/// Parses one raw request line (with its line ending, at most [`MAX_LINE`] bytes).
pub(crate) fn parse_request_line(raw: &[u8]) -> RequestLine {
    let decoded = from_latin1(raw);
    let line = decoded.trim_end_matches(['\r', '\n']);
    let words = pystr::split_whitespace(line, None);
    if words.is_empty() {
        return RequestLine::Empty;
    }
    let mut version = String::from("HTTP/0.9");
    if words.len() >= 3 {
        let last = words.last().copied().unwrap_or("");
        let Some(numbers) = parse_version(last) else {
            return RequestLine::Refuse(ErrorPage::with_message(
                400,
                format!("Bad request version ({})", py_repr(last)),
            ));
        };
        if numbers.0 >= 2 {
            let base = last.split_once('/').map_or("", |(_, b)| b);
            return RequestLine::Refuse(ErrorPage::with_message(
                505,
                format!("Invalid HTTP version ({base})"),
            ));
        }
        version = last.to_owned();
    }
    if !(2..=3).contains(&words.len()) {
        return RequestLine::Refuse(ErrorPage::with_message(
            400,
            format!("Bad request syntax ({})", py_repr(line)),
        ));
    }
    let (method, raw_path) = match (words.first(), words.get(1)) {
        (Some(m), Some(p)) => (*m, *p),
        _ => return RequestLine::Empty,
    };
    let two_words = words.len() == 2;
    if two_words && method != "GET" {
        return RequestLine::Refuse(ErrorPage::with_message(
            400,
            format!("Bad HTTP/0.9 request type ({})", py_repr(method)),
        ));
    }
    // gh-87389: a path that starts with "//" is reduced to a single "/".
    let path = if raw_path.starts_with("//") {
        format!("/{}", raw_path.trim_start_matches('/'))
    } else {
        raw_path.to_owned()
    };
    RequestLine::Line {
        method: method.to_owned(),
        path,
        version,
        two_words,
    }
}

/// `HTTP/<major>.<minor>` as Python checks it: the prefix, exactly one dot, each part
/// non-empty Python digits of at most ten characters that `int()` accepts (ASCII digits).
/// Leading zeros are ignored.
fn parse_version(word: &str) -> Option<(u64, u64)> {
    let base = word.strip_prefix("HTTP/")?;
    let (major, minor) = base.split_once('.')?;
    if minor.contains('.') {
        return None;
    }
    let number = |part: &str| -> Option<u64> {
        if !pystr::isdigit(part) || part.chars().count() > 10 {
            return None;
        }
        // isdigit() admits superscripts, which int() then refuses: only ASCII remains.
        if !part.bytes().all(|b| b.is_ascii_digit()) {
            return None;
        }
        part.parse::<u64>().ok()
    };
    Some((number(major)?, number(minor)?))
}

/// The header lines read so far ended badly.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum HeaderLimit {
    /// A line longer than [`MAX_LINE`].
    LineTooLong,
    /// More than [`MAX_HEADERS`] lines.
    TooMany,
}

impl HeaderLimit {
    /// Python's 431 page for this limit.
    pub(crate) fn page(self) -> ErrorPage {
        match self {
            HeaderLimit::LineTooLong => ErrorPage {
                code: 431,
                message: Some(String::from("Line too long")),
                explain: Some(format!(
                    "got more than {MAX_LINE} bytes when reading header line"
                )),
            },
            HeaderLimit::TooMany => ErrorPage {
                code: 431,
                message: Some(String::from("Too many headers")),
                explain: Some(format!("got more than {MAX_HEADERS} headers")),
            },
        }
    }
}

/// Parses the raw header lines (each with its line ending, the blank line included) into
/// headers, as `email.parser.Parser().parsestr(b''.join(lines).decode('iso-8859-1'))`.
pub(crate) fn parse_header_lines(lines: &[Vec<u8>]) -> Headers {
    let text = from_latin1(&lines.concat());
    let mut header_lines: Vec<&str> = Vec::new();
    for line in split_email_lines(&text) {
        if !matches_header_re(line) {
            break;
        }
        header_lines.push(line);
    }
    let mut entries: Vec<(String, String)> = Vec::new();
    let mut current: Option<Vec<&str>> = None;
    let flush = |current: &mut Option<Vec<&str>>, entries: &mut Vec<(String, String)>| {
        if let Some(source) = current.take() {
            entries.push(header_source_parse(&source));
        }
    };
    for line in header_lines {
        if line.starts_with([' ', '\t']) {
            // A continuation of the header before it; a first line that is a continuation
            // is dropped (a parser defect).
            if let Some(source) = current.as_mut() {
                source.push(line);
            }
            continue;
        }
        flush(&mut current, &mut entries);
        if line.starts_with("From ") {
            // An envelope line: never a header, wherever it is.
            continue;
        }
        match line.find(':') {
            // ":value" has no name: dropped.
            Some(0) | None => continue,
            Some(_) => current = Some(vec![line]),
        }
    }
    flush(&mut current, &mut entries);
    Headers::from_pairs(entries)
}

/// Splits text into lines at `\r\n`, `\r` or `\n`, keeping each line's ending.
fn split_email_lines(text: &str) -> Vec<&str> {
    let bytes = text.as_bytes();
    let mut lines = Vec::new();
    let mut start = 0usize;
    let mut i = 0usize;
    while i < bytes.len() {
        let end = match bytes.get(i) {
            Some(b'\n') => Some(i + 1),
            Some(b'\r') if bytes.get(i + 1) == Some(&b'\n') => Some(i + 2),
            Some(b'\r') => Some(i + 1),
            _ => None,
        };
        match end {
            Some(end) => {
                lines.push(text.get(start..end).unwrap_or(""));
                start = end;
                i = end;
            }
            None => i += 1,
        }
    }
    if start < bytes.len() {
        lines.push(text.get(start..).unwrap_or(""));
    }
    lines
}

/// `email.feedparser.headerRE`: `^(From |[\041-\071\073-\176]*:|[\t ])`.
fn matches_header_re(line: &str) -> bool {
    if line.starts_with("From ") || line.starts_with([' ', '\t']) {
        return true;
    }
    for c in line.chars() {
        match c {
            ':' => return true,
            '\u{21}'..='\u{39}' | '\u{3b}'..='\u{7e}' => {}
            _ => return false,
        }
    }
    false
}

/// `Compat32.header_source_parse`: the name up to the first `:`, and the rest of the first
/// line joined with the continuation lines, leading spaces, tabs, `\r` and `\n` removed and
/// trailing `\r` and `\n` removed.
fn header_source_parse(source: &[&str]) -> (String, String) {
    let first = source.first().copied().unwrap_or("");
    let (name, rest) = first.split_once(':').unwrap_or((first, ""));
    let mut value = String::from(rest);
    for line in source.iter().skip(1) {
        value.push_str(line);
    }
    let value = value
        .trim_start_matches([' ', '\t', '\r', '\n'])
        .trim_end_matches(['\r', '\n']);
    (name.to_owned(), value.to_owned())
}

/// Reads and parses a request head from the connection.
pub(crate) async fn read_head<R: AsyncBufRead + Unpin>(
    reader: &mut R,
    limit: Duration,
) -> Result<HeadOutcome, ReadFail> {
    let raw = read_line(reader, MAX_LINE + 1, limit).await?;
    if raw.len() > MAX_LINE {
        return Ok(HeadOutcome::Refuse {
            page: ErrorPage::new(414),
            method: None,
            target: None,
            http09: false,
        });
    }
    if raw.is_empty() {
        return Ok(HeadOutcome::Close);
    }
    let (method, path, version, two_words) = match parse_request_line(&raw) {
        RequestLine::Empty => return Ok(HeadOutcome::Close),
        RequestLine::Refuse(page) => {
            return Ok(HeadOutcome::Refuse {
                page,
                method: None,
                target: None,
                http09: false,
            })
        }
        RequestLine::Line {
            method,
            path,
            version,
            two_words,
        } => (method, path, version, two_words),
    };
    if two_words {
        // HTTP/0.9: no headers are read at all (CPython 3.14 parse_request: "For HTTP/0.9,
        // headers are not expected at all", `self.headers = {}` and return).
        return Ok(HeadOutcome::Request(RequestHead {
            method,
            path,
            version,
            headers: Headers::default(),
        }));
    }
    let mut lines: Vec<Vec<u8>> = Vec::new();
    loop {
        let line = read_line(reader, MAX_LINE + 1, limit).await?;
        let limit_hit = if line.len() > MAX_LINE {
            Some(HeaderLimit::LineTooLong)
        } else {
            None
        };
        let end = matches!(line.as_slice(), b"\r\n" | b"\n" | b"");
        lines.push(line);
        let limit_hit = limit_hit.or(if lines.len() > MAX_HEADERS {
            Some(HeaderLimit::TooMany)
        } else {
            None
        });
        if let Some(hit) = limit_hit {
            let http09 = version == "HTTP/0.9";
            return Ok(HeadOutcome::Refuse {
                page: hit.page(),
                method: Some(method),
                target: Some((path, version)),
                http09,
            });
        }
        if end {
            break;
        }
    }
    Ok(HeadOutcome::Request(RequestHead {
        method,
        path,
        version,
        headers: parse_header_lines(&lines),
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn line(method: &str, path: &str, version: &str, two: bool) -> RequestLine {
        RequestLine::Line {
            method: method.into(),
            path: path.into(),
            version: version.into(),
            two_words: two,
        }
    }

    fn refused(code: u16, message: &str) -> RequestLine {
        RequestLine::Refuse(ErrorPage::with_message(code, message))
    }

    // Expected outcomes follow CPython 3.14 BaseHTTPRequestHandler.parse_request.
    #[test]
    fn request_lines_follow_python() {
        let p = |s: &[u8]| parse_request_line(s);
        assert_eq!(
            p(b"GET /x HTTP/1.1\r\n"),
            line("GET", "/x", "HTTP/1.1", false)
        );
        assert_eq!(
            p(b"POST /a?b=1 HTTP/1.0\n"),
            line("POST", "/a?b=1", "HTTP/1.0", false)
        );
        assert_eq!(
            p(b"GET  /x\tHTTP/01.001\r\n"),
            line("GET", "/x", "HTTP/01.001", false)
        );
        assert_eq!(p(b"GET /x\r\n"), line("GET", "/x", "HTTP/0.9", true));
        assert_eq!(
            p(b"GET //evil.example/a HTTP/1.1\r\n"),
            line("GET", "/evil.example/a", "HTTP/1.1", false)
        );
        assert_eq!(
            p(b"PUT / HTTP/1.1\r\n"),
            line("PUT", "/", "HTTP/1.1", false)
        );
        assert_eq!(p(b"\r\n"), RequestLine::Empty);
        assert_eq!(p(b"  \t \r\n"), RequestLine::Empty);
        assert_eq!(
            p(b"POST /x\r\n"),
            refused(400, "Bad HTTP/0.9 request type ('POST')")
        );
        assert_eq!(p(b"GET\r\n"), refused(400, "Bad request syntax ('GET')"));
        assert_eq!(
            p(b"GET / x HTTP/1.1\r\n"),
            refused(400, "Bad request syntax ('GET / x HTTP/1.1')")
        );
        assert_eq!(
            p(b"GET / FTP/1.1\r\n"),
            refused(400, "Bad request version ('FTP/1.1')")
        );
        assert_eq!(
            p(b"GET / HTTP/1\r\n"),
            refused(400, "Bad request version ('HTTP/1')")
        );
        assert_eq!(
            p(b"GET / HTTP/1.1.1\r\n"),
            refused(400, "Bad request version ('HTTP/1.1.1')")
        );
        assert_eq!(
            p(b"GET / HTTP/1.x\r\n"),
            refused(400, "Bad request version ('HTTP/1.x')")
        );
        assert_eq!(
            p(b"GET / HTTP/12345678901.1\r\n"),
            refused(400, "Bad request version ('HTTP/12345678901.1')")
        );
        assert_eq!(
            p(b"GET / HTTP/\xb9.1\r\n"),
            refused(400, "Bad request version ('HTTP/\u{b9}.1')")
        );
        assert_eq!(
            p(b"GET / HTTP/2.0\r\n"),
            refused(505, "Invalid HTTP version (2.0)")
        );
        assert_eq!(
            p(b"GET / x HTTP/3.0\r\n"),
            refused(505, "Invalid HTTP version (3.0)")
        );
        assert_eq!(
            p(b"GET / x HTTP/x\r\n"),
            refused(400, "Bad request version ('HTTP/x')")
        );
        // Python splits on its own whitespace, which includes \x1c and \x85 in Latin-1.
        assert_eq!(
            p(b"GET\x1c/\x85HTTP/1.0\r\n"),
            line("GET", "/", "HTTP/1.0", false)
        );
    }

    fn headers(raw: &[u8]) -> Vec<(String, String)> {
        let lines: Vec<Vec<u8>> = raw
            .split_inclusive(|&b| b == b'\n')
            .map(<[u8]>::to_vec)
            .collect();
        parse_header_lines(&lines)
            .iter()
            .map(|(k, v)| (k.to_owned(), v.to_owned()))
            .collect()
    }

    fn pairs(list: &[(&str, &str)]) -> Vec<(String, String)> {
        list.iter()
            .map(|(k, v)| ((*k).to_owned(), (*v).to_owned()))
            .collect()
    }

    // Expected values follow CPython 3.14 http.client.parse_headers on the same bytes.
    #[test]
    fn headers_follow_the_email_parser() {
        assert_eq!(
            headers(b"Host: a\r\nContent-Length:  5 \r\n\r\n"),
            pairs(&[("Host", "a"), ("Content-Length", "5 ")])
        );
        assert_eq!(
            headers(b"X: a\r\n b\r\n\tc\r\nY:\r\n\r\n"),
            pairs(&[("X", "a\r\n b\r\n\tc"), ("Y", "")])
        );
        // A line that is not a header ends the headers; the rest is ignored.
        assert_eq!(
            headers(b"A: 1\r\nBad Line\r\nB: 2\r\n\r\n"),
            pairs(&[("A", "1")])
        );
        assert_eq!(headers(b"A : 1\r\nB: 2\r\n\r\n"), pairs(&[]));
        // A lone \r splits lines too.
        assert_eq!(
            headers(b"A: 1\rB: 2\r\n\r\n"),
            pairs(&[("A", "1"), ("B", "2")])
        );
        assert_eq!(headers(b"A: 1\r\rB: 2\r\n\r\n"), pairs(&[("A", "1")]));
        // Dropped: a leading continuation, a nameless header, envelope lines.
        assert_eq!(
            headers(b" lead\r\n: x\r\n more\r\nFrom someone\r\nA: 1\r\n\r\n"),
            pairs(&[("A", "1")])
        );
        assert_eq!(
            headers(b"Odd(name)\"x: v\r\nA: 1\r\n\r\n"),
            pairs(&[("Odd(name)\"x", "v"), ("A", "1")])
        );
        assert_eq!(headers(b"X: \xe9\r\n\r\n"), pairs(&[("X", "\u{e9}")]));
        assert_eq!(headers(b"A: 1\n\n"), pairs(&[("A", "1")]));
    }

    #[test]
    fn lookup_is_case_insensitive_and_first_wins() {
        let h = Headers::from_pairs(pairs(&[("content-length", "1"), ("Content-Length", "2")]));
        assert_eq!(h.get("CONTENT-LENGTH"), Some("1"));
        assert_eq!(
            h.get_all("Content-length").collect::<Vec<_>>(),
            vec!["1", "2"]
        );
        assert_eq!(h.get("Host"), None);
        assert_eq!(h.len(), 2);
        assert!(!h.is_empty());
    }

    #[test]
    fn route_path_drops_query_and_trailing_slashes() {
        let head = |p: &str| RequestHead::new("GET", p, "HTTP/1.1", Headers::default());
        assert_eq!(head("/").route_path(), "");
        assert_eq!(head("/v1/messages?beta=true").route_path(), "/v1/messages");
        assert_eq!(head("/v1/models//?x").route_path(), "/v1/models");
        assert_eq!(head("/a?b?c").query(), "b?c");
        assert_eq!(head("/a").query(), "");
        assert!(!head("/").is_http09());
        assert!(RequestHead::new("GET", "/", "HTTP/0.9", Headers::default()).is_http09());
    }

    #[tokio::test]
    async fn head_limits_follow_python() {
        let t = Duration::from_secs(5);
        let long_line = vec![b'a'; MAX_LINE + 1];
        let mut r: &[u8] = &long_line;
        assert!(matches!(
            read_head(&mut r, t).await,
            Ok(HeadOutcome::Refuse { page, .. }) if page == ErrorPage::new(414)
        ));
        // Exactly 65536 bytes with the line ending is accepted.
        let mut ok = b"GET /".to_vec();
        ok.resize(MAX_LINE - b" HTTP/1.0\r\n".len(), b'a');
        ok.extend_from_slice(b" HTTP/1.0\r\n\r\n");
        let mut r: &[u8] = &ok;
        assert!(matches!(
            read_head(&mut r, t).await,
            Ok(HeadOutcome::Request(_))
        ));
        // 99 header lines and the blank one fit; 100 header lines do not.
        let many = |n: usize| {
            let mut v = b"GET / HTTP/1.1\r\n".to_vec();
            for i in 0..n {
                v.extend_from_slice(format!("X-{i}: v\r\n").as_bytes());
            }
            v.extend_from_slice(b"\r\n");
            v
        };
        let bytes = many(99);
        let mut r: &[u8] = &bytes;
        assert!(
            matches!(read_head(&mut r, t).await, Ok(HeadOutcome::Request(h)) if h.headers().len() == 99)
        );
        let bytes = many(100);
        let mut r: &[u8] = &bytes;
        assert!(matches!(
            read_head(&mut r, t).await,
            Ok(HeadOutcome::Refuse { page, method: Some(m), target: Some((p, v)), http09: false })
                if page == HeaderLimit::TooMany.page() && m == "GET" && p == "/" && v == "HTTP/1.1"
        ));
        let mut long_header = b"HEAD / HTTP/0.9\r\nX: ".to_vec();
        long_header.resize(long_header.len() + MAX_LINE, b'v');
        let mut r: &[u8] = &long_header;
        assert!(matches!(
            read_head(&mut r, t).await,
            Ok(HeadOutcome::Refuse { page, http09: true, .. }) if page == HeaderLimit::LineTooLong.page()
        ));
        let mut r: &[u8] = b"";
        assert!(matches!(read_head(&mut r, t).await, Ok(HeadOutcome::Close)));
        // End of file ends the headers too.
        let mut r: &[u8] = b"GET /x HTTP/1.1\r\nA: 1\r\n";
        assert!(
            matches!(read_head(&mut r, t).await, Ok(HeadOutcome::Request(h)) if h.headers().get("a") == Some("1"))
        );
    }
}
