//! Byte-level pieces of a response head: the status line, the `Server` and `Date` headers,
//! and Python's default HTML error page.
//!
//! Reason phrases, the error page and the `Date` format are those of CPython 3.14's
//! `http.server` (`BaseHTTPRequestHandler.responses`, `DEFAULT_ERROR_MESSAGE`,
//! `email.utils.formatdate(usegmt=True)`), which the donor inherits.
//!
//! Behavior reference: project-maya serve/server.py:5403-5415 at 7e68a30f, and CPython 3.14
//! `Lib/http/server.py` (`send_error`, `send_response`, `send_header`).

use std::time::{SystemTime, UNIX_EPOCH};

/// The value of the `Server` header: `pulsar-console/<crate version>`.
///
/// Approved deviation P-1 (owner decision of 2026-11-14): the donor sends Python's
/// `BaseHTTP/0.6 Python/3.x`; the header's name and its position (right after the status
/// line, before `Date`) are the donor's.
pub const SERVER_HEADER: &str = concat!("pulsar-console/", env!("CARGO_PKG_VERSION"));

/// The protocol token of every status line (`protocol_version = "HTTP/1.0"`).
pub const PROTOCOL: &str = "HTTP/1.0";

/// The `Content-Type` of Python's HTML error page.
pub const ERROR_CONTENT_TYPE: &str = "text/html;charset=utf-8";

/// CPython 3.14 `http.server.BaseHTTPRequestHandler.responses`: code, short phrase, long
/// explanation.
const RESPONSES: &[(u16, &str, &str)] = &[
    (100, "Continue", "Request received, please continue"),
    (
        101,
        "Switching Protocols",
        "Switching to new protocol; obey Upgrade header",
    ),
    (102, "Processing", "Server is processing the request"),
    (
        103,
        "Early Hints",
        "Headers sent to prepare for the response",
    ),
    (200, "OK", "Request fulfilled, document follows"),
    (201, "Created", "Document created, URL follows"),
    (
        202,
        "Accepted",
        "Request accepted, processing continues off-line",
    ),
    (
        203,
        "Non-Authoritative Information",
        "Request fulfilled from cache",
    ),
    (204, "No Content", "Request fulfilled, nothing follows"),
    (205, "Reset Content", "Clear input form for further input"),
    (206, "Partial Content", "Partial content follows"),
    (
        207,
        "Multi-Status",
        "Response contains multiple statuses in the body",
    ),
    (
        208,
        "Already Reported",
        "Operation has already been reported",
    ),
    (
        226,
        "IM Used",
        "Request completed using instance manipulations",
    ),
    (
        300,
        "Multiple Choices",
        "Object has several resources -- see URI list",
    ),
    (
        301,
        "Moved Permanently",
        "Object moved permanently -- see URI list",
    ),
    (302, "Found", "Object moved temporarily -- see URI list"),
    (303, "See Other", "Object moved -- see Method and URL list"),
    (
        304,
        "Not Modified",
        "Document has not changed since given time",
    ),
    (
        305,
        "Use Proxy",
        "You must use proxy specified in Location to access this resource",
    ),
    (
        307,
        "Temporary Redirect",
        "Object moved temporarily -- see URI list",
    ),
    (
        308,
        "Permanent Redirect",
        "Object moved permanently -- see URI list",
    ),
    (
        400,
        "Bad Request",
        "Bad request syntax or unsupported method",
    ),
    (
        401,
        "Unauthorized",
        "No permission -- see authorization schemes",
    ),
    (
        402,
        "Payment Required",
        "No payment -- see charging schemes",
    ),
    (
        403,
        "Forbidden",
        "Request forbidden -- authorization will not help",
    ),
    (404, "Not Found", "Nothing matches the given URI"),
    (
        405,
        "Method Not Allowed",
        "Specified method is invalid for this resource",
    ),
    (
        406,
        "Not Acceptable",
        "URI not available in preferred format",
    ),
    (
        407,
        "Proxy Authentication Required",
        "You must authenticate with this proxy before proceeding",
    ),
    (408, "Request Timeout", "Request timed out; try again later"),
    (409, "Conflict", "Request conflict"),
    (
        410,
        "Gone",
        "URI no longer exists and has been permanently removed",
    ),
    (411, "Length Required", "Client must specify Content-Length"),
    (
        412,
        "Precondition Failed",
        "Precondition in headers is false",
    ),
    (413, "Content Too Large", "Content is too large"),
    (414, "URI Too Long", "URI is too long"),
    (
        415,
        "Unsupported Media Type",
        "Entity body in unsupported format",
    ),
    (416, "Range Not Satisfiable", "Cannot satisfy request range"),
    (
        417,
        "Expectation Failed",
        "Expect condition could not be satisfied",
    ),
    (
        418,
        "I'm a Teapot",
        "Server refuses to brew coffee because it is a teapot",
    ),
    (
        421,
        "Misdirected Request",
        "Server is not able to produce a response",
    ),
    (
        422,
        "Unprocessable Content",
        "Server is not able to process the contained instructions",
    ),
    (423, "Locked", "Resource of a method is locked"),
    (
        424,
        "Failed Dependency",
        "Dependent action of the request failed",
    ),
    (
        425,
        "Too Early",
        "Server refuses to process a request that might be replayed",
    ),
    (
        426,
        "Upgrade Required",
        "Server refuses to perform the request using the current protocol",
    ),
    (
        428,
        "Precondition Required",
        "The origin server requires the request to be conditional",
    ),
    (
        429,
        "Too Many Requests",
        "The user has sent too many requests in a given amount of time (\"rate limiting\")",
    ),
    (
        431,
        "Request Header Fields Too Large",
        "The server is unwilling to process the request because its header fields are too large",
    ),
    (
        451,
        "Unavailable For Legal Reasons",
        "The server is denying access to the resource as a consequence of a legal demand",
    ),
    (500, "Internal Server Error", "Server got itself in trouble"),
    (
        501,
        "Not Implemented",
        "Server does not support this operation",
    ),
    (
        502,
        "Bad Gateway",
        "Invalid responses from another server/proxy",
    ),
    (
        503,
        "Service Unavailable",
        "The server cannot process the request due to a high load",
    ),
    (
        504,
        "Gateway Timeout",
        "The gateway server did not receive a timely response",
    ),
    (505, "HTTP Version Not Supported", "Cannot fulfill request"),
    (
        506,
        "Variant Also Negotiates",
        "Server has an internal configuration error",
    ),
    (
        507,
        "Insufficient Storage",
        "Server is not able to store the representation",
    ),
    (
        508,
        "Loop Detected",
        "Server encountered an infinite loop while processing a request",
    ),
    (
        510,
        "Not Extended",
        "Request does not meet the resource access policy",
    ),
    (
        511,
        "Network Authentication Required",
        "The client needs to authenticate to gain network access",
    ),
];

/// The short reason phrase of `code`, or `""` for a code Python does not know (the status
/// line then ends with a space, as Python writes it).
pub fn reason_phrase(code: u16) -> &'static str {
    lookup(code).map_or("", |(short, _)| short)
}

fn lookup(code: u16) -> Option<(&'static str, &'static str)> {
    RESPONSES
        .binary_search_by_key(&code, |&(c, _, _)| c)
        .ok()
        .and_then(|i| RESPONSES.get(i))
        .map(|&(_, short, long)| (short, long))
}

/// Text encoded as Latin-1, as Python's `str.encode('latin-1')` does for a status line or a
/// header. `None` when a character is beyond U+00FF (Python raises `UnicodeEncodeError`).
pub(crate) fn latin1(text: &str) -> Option<Vec<u8>> {
    text.chars()
        .map(|c| u8::try_from(u32::from(c)).ok())
        .collect()
}

/// Bytes decoded as Latin-1 (`bytes.decode('iso-8859-1')`): every byte becomes the
/// character with the same code point.
pub(crate) fn from_latin1(bytes: &[u8]) -> String {
    bytes.iter().map(|&b| char::from(b)).collect()
}

/// The current time as Python's `email.utils.formatdate(time.time(), usegmt=True)`, for
/// example `Sat, 14 Nov 2026 09:05:03 GMT`.
pub fn http_date_now() -> String {
    let seconds = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_or(0, |d| i64::try_from(d.as_secs()).unwrap_or(i64::MAX));
    http_date(seconds)
}

/// `seconds` since the Unix epoch formatted as `email.utils.formatdate(usegmt=True)`.
pub fn http_date(seconds: i64) -> String {
    const DAYS: [&str; 7] = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
    const MONTHS: [&str; 12] = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ];
    let days = seconds.div_euclid(86_400);
    let secs_of_day = seconds.rem_euclid(86_400);
    let (year, month, day) = civil_from_days(days);
    // 1970-01-01 was a Thursday (index 3 with Monday at 0).
    let weekday = DAYS
        .get(usize::try_from((days + 3).rem_euclid(7)).unwrap_or(0))
        .copied()
        .unwrap_or("Mon");
    let month_name = MONTHS
        .get(usize::try_from(month - 1).unwrap_or(0))
        .copied()
        .unwrap_or("Jan");
    format!(
        "{weekday}, {day:02} {month_name} {year:04} {:02}:{:02}:{:02} GMT",
        secs_of_day / 3600,
        (secs_of_day % 3600) / 60,
        secs_of_day % 60
    )
}

/// The proleptic Gregorian date of a day count since 1970-01-01 (H. Hinnant's algorithm).
fn civil_from_days(days: i64) -> (i64, i64, i64) {
    let z = days + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z.rem_euclid(146_097);
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let day = doy - (153 * mp + 2) / 5 + 1;
    let month = if mp < 10 { mp + 3 } else { mp - 9 };
    let year = yoe + era * 400 + i64::from(month <= 2);
    (year, month, day)
}

/// Python `repr()` of a string: single quotes unless the text holds `'` and no `"`; `\\`,
/// the quote, `\t`, `\n` and `\r` escaped; other non-printable characters as `\xhh`,
/// `\uhhhh` or `\Uhhhhhhhh`. Printability is exact for U+0000 to U+00FF (all the transport
/// passes, since request text is decoded as Latin-1); above that, controls and separators
/// other than the space are escaped.
pub fn py_repr(text: &str) -> String {
    let quote = if text.contains('\'') && !text.contains('"') {
        '"'
    } else {
        '\''
    };
    let mut out = String::with_capacity(text.len() + 2);
    out.push(quote);
    for c in text.chars() {
        match c {
            '\\' => out.push_str("\\\\"),
            '\t' => out.push_str("\\t"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            c if c == quote => {
                out.push('\\');
                out.push(c);
            }
            c if is_printable(c) => out.push(c),
            c => {
                let cp = u32::from(c);
                if cp < 0x100 {
                    out.push_str(&format!("\\x{cp:02x}"));
                } else if cp < 0x10000 {
                    out.push_str(&format!("\\u{cp:04x}"));
                } else {
                    out.push_str(&format!("\\U{cp:08x}"));
                }
            }
        }
    }
    out.push(quote);
    out
}

/// Python `str.isprintable()` for one character, exact for U+0000 to U+00FF.
fn is_printable(c: char) -> bool {
    match u32::from(c) {
        0x20..=0x7e => true,
        0x00..=0x1f | 0x7f..=0xa0 | 0xad => false,
        0xa1..=0xff => true,
        _ => !(c.is_control() || c.is_whitespace()),
    }
}

/// Python `html.escape(text, quote=False)`: `&`, `<` and `>` become entities.
pub fn html_escape(text: &str) -> String {
    let mut out = String::with_capacity(text.len());
    for c in text.chars() {
        match c {
            '&' => out.push_str("&amp;"),
            '<' => out.push_str("&lt;"),
            '>' => out.push_str("&gt;"),
            c => out.push(c),
        }
    }
    out
}

/// Python's default error page (`DEFAULT_ERROR_MESSAGE` of CPython 3.14) for `code`, with
/// `message` and `explain` HTML-escaped, encoded as UTF-8.
pub fn error_page_body(code: u16, message: &str, explain: &str) -> Vec<u8> {
    format!(
        "<!DOCTYPE HTML>\n\
<html lang=\"en\">\n    \
<head>\n        \
<meta charset=\"utf-8\">\n        \
<style type=\"text/css\">\n            \
:root {{\n                \
color-scheme: light dark;\n            \
}}\n        \
</style>\n        \
<title>Error response</title>\n    \
</head>\n    \
<body>\n        \
<h1>Error response</h1>\n        \
<p>Error code: {code}</p>\n        \
<p>Message: {}.</p>\n        \
<p>Error code explanation: {code} - {}.</p>\n    \
</body>\n\
</html>\n",
        html_escape(message),
        html_escape(explain)
    )
    .into_bytes()
}

/// One error page the transport sends itself, as Python's `send_error(code, message,
/// explain)`: the status line carries `message` as its reason, then `Server`, `Date`,
/// `Connection: close`, `Content-Type` and `Content-Length`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ErrorPage {
    /// HTTP status.
    pub code: u16,
    /// The reason in the status line and the page's "Message" (Python's `message`, or the
    /// short phrase when `None`).
    pub message: Option<String>,
    /// The page's explanation (Python's `explain`, or the long phrase when `None`).
    pub explain: Option<String>,
}

impl ErrorPage {
    /// A page with Python's default message and explanation for `code`.
    pub fn new(code: u16) -> Self {
        Self {
            code,
            message: None,
            explain: None,
        }
    }

    /// A page with its own message.
    pub fn with_message(code: u16, message: impl Into<String>) -> Self {
        Self {
            code,
            message: Some(message.into()),
            explain: None,
        }
    }

    /// The reason phrase of the status line.
    pub fn reason(&self) -> String {
        match &self.message {
            Some(message) => message.clone(),
            None => lookup(self.code)
                .map_or("???", |(short, _)| short)
                .to_owned(),
        }
    }

    /// The HTML body, or `None` for codes Python sends without one (below 200, 204, 205,
    /// 304).
    pub fn body(&self) -> Option<Vec<u8>> {
        if self.code < 200 || matches!(self.code, 204 | 205 | 304) {
            return None;
        }
        let explain = match &self.explain {
            Some(explain) => explain.clone(),
            None => lookup(self.code).map_or("???", |(_, long)| long).to_owned(),
        };
        Some(error_page_body(self.code, &self.reason(), &explain))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn server_header_is_the_product_version() {
        // Approved deviation P-1.
        assert_eq!(
            SERVER_HEADER,
            format!("pulsar-console/{}", env!("CARGO_PKG_VERSION"))
        );
    }

    #[test]
    fn reason_phrases_are_pythons() {
        assert_eq!(reason_phrase(200), "OK");
        assert_eq!(reason_phrase(413), "Content Too Large");
        assert_eq!(reason_phrase(414), "URI Too Long");
        assert_eq!(reason_phrase(503), "Service Unavailable");
        assert_eq!(reason_phrase(299), "");
        assert!(RESPONSES
            .windows(2)
            .all(|w| matches!(w, [a, b] if a.0 < b.0)));
    }

    #[test]
    fn dates_are_formatdate_gmt() {
        // email.utils.formatdate(t, usegmt=True) for these timestamps (CPython 3.14).
        assert_eq!(http_date(0), "Thu, 01 Jan 1970 00:00:00 GMT");
        assert_eq!(http_date(951_782_400), "Tue, 29 Feb 2000 00:00:00 GMT");
        assert_eq!(http_date(1_794_387_903), "Wed, 11 Nov 2026 09:05:03 GMT");
        assert_eq!(http_date(4_102_444_799), "Thu, 31 Dec 2099 23:59:59 GMT");
        assert_eq!(http_date_now().len(), 29);
    }

    #[test]
    fn repr_matches_python() {
        // repr() of these strings in CPython 3.14.
        assert_eq!(py_repr("PUT"), "'PUT'");
        assert_eq!(py_repr("it's"), "\"it's\"");
        assert_eq!(py_repr("a'b\"c"), "'a\\'b\"c'");
        assert_eq!(py_repr("a\\b\t\u{1}\u{7f}"), "'a\\\\b\\t\\x01\\x7f'");
        assert_eq!(
            py_repr("\u{a0}\u{ad}\u{e9}\u{ff}"),
            "'\\xa0\\xad\u{e9}\u{ff}'"
        );
        assert_eq!(py_repr("\u{85}x"), "'\\x85x'");
        assert_eq!(py_repr(""), "''");
    }

    #[test]
    fn error_page_is_pythons() {
        let page = ErrorPage::with_message(501, "Unsupported method ('<P>')");
        let body = page.body().unwrap_or_default();
        let text = String::from_utf8(body).unwrap_or_default();
        assert!(text.starts_with("<!DOCTYPE HTML>\n<html lang=\"en\">\n    <head>\n"));
        assert!(text.contains(
            "        <p>Message: Unsupported method ('&lt;P&gt;').</p>\n        \
             <p>Error code explanation: 501 - Server does not support this operation.</p>\n"
        ));
        assert!(text.ends_with("    </body>\n</html>\n"));
        assert_eq!(ErrorPage::new(414).reason(), "URI Too Long");
        assert_eq!(ErrorPage::new(299).reason(), "???");
        assert_eq!(ErrorPage::new(204).body(), None);
    }

    #[test]
    fn latin1_round_trip() {
        assert_eq!(latin1("a\u{e9}"), Some(vec![b'a', 0xe9]));
        assert_eq!(latin1("\u{100}"), None);
        assert_eq!(from_latin1(&[b'a', 0xe9, 0x85]), "a\u{e9}\u{85}");
    }
}
