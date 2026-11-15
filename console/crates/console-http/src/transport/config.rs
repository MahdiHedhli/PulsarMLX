//! The transport's three settings and the donor's rules for reading them from text.
//!
//! The settings arrive as a plain [`TransportConfig`]; reading the environment is work
//! package API-08's job. The parse functions take the raw text of a variable (`None` when it
//! is unset) and apply the donor's rules, including Python's `int()` and `float()` syntax
//! (surrounding whitespace, a sign, `_` between digits).
//!
//! Behavior reference: project-maya serve/server.py:5346-5372 at 7e68a30f.

use std::time::Duration;

use console_pyjson::pystr;

/// Environment variable naming the listen backlog (contracts/naming.md, donor
/// `MAYA_HTTP_BACKLOG`).
pub const ENV_HTTP_BACKLOG: &str = "PULSAR_CONSOLE_HTTP_BACKLOG";

/// Environment variable naming the request body limit in MiB (contracts/naming.md, donor
/// `MAYA_MAX_BODY_MIB`). The 413 answer names it.
pub const ENV_MAX_BODY_MIB: &str = "PULSAR_CONSOLE_MAX_BODY_MIB";

/// Environment variable naming the per-operation socket timeout in seconds
/// (contracts/naming.md, donor `MAYA_REQUEST_TIMEOUT_S`).
pub const ENV_REQUEST_TIMEOUT_S: &str = "PULSAR_CONSOLE_REQUEST_TIMEOUT_S";

/// The donor's default listen backlog.
pub const DEFAULT_BACKLOG: u32 = 256;

/// The smallest listen backlog the donor uses.
pub const MIN_BACKLOG: u32 = 5;

/// The donor's default body limit, in MiB.
pub const DEFAULT_MAX_BODY_MIB: u64 = 256;

/// The donor's default per-operation timeout, in seconds.
pub const DEFAULT_REQUEST_TIMEOUT_S: u64 = 300;

/// Python's limit on the number of decimal digits `int()` converts (CPython 3.11 and later:
/// `sys.int_info.default_max_str_digits`). A longer string is a `ValueError`.
const PY_MAX_STR_DIGITS: usize = 4300;

/// The settings of the transport.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct TransportConfig {
    /// The listen backlog (`request_queue_size`).
    pub backlog: u32,
    /// The largest request body, in bytes; a larger one is answered 413.
    pub max_body_bytes: u64,
    /// How long one socket read or write may wait. There is no overall request deadline.
    pub request_timeout: Duration,
}

impl Default for TransportConfig {
    /// The donor's defaults: backlog 256, 256 MiB, 300 s.
    fn default() -> Self {
        Self {
            backlog: DEFAULT_BACKLOG,
            max_body_bytes: DEFAULT_MAX_BODY_MIB << 20,
            request_timeout: Duration::from_secs(DEFAULT_REQUEST_TIMEOUT_S),
        }
    }
}

impl TransportConfig {
    /// The settings from the raw text of the three variables (`None` when unset), by the
    /// donor's rules ([`parse_backlog`], [`parse_max_body_bytes`],
    /// [`parse_request_timeout`]).
    pub fn from_raw(
        backlog: Option<&str>,
        max_body_mib: Option<&str>,
        request_timeout_s: Option<&str>,
    ) -> Self {
        Self {
            backlog: parse_backlog(backlog),
            max_body_bytes: parse_max_body_bytes(max_body_mib),
            request_timeout: parse_request_timeout(request_timeout_s),
        }
    }

    /// The body limit in whole MiB, as the 413 message prints it (`limit >> 20`).
    pub fn max_body_mib(&self) -> u64 {
        self.max_body_bytes >> 20
    }
}

/// The listen backlog: `max(5, int(value or 256))`, and 256 when the value is not an
/// integer. An unset or empty value gives 256; `"0"` and negative values give 5. A value
/// beyond `i32::MAX` is clamped there (CPython's `listen()` would raise `OverflowError`).
///
/// Behavior reference: project-maya serve/server.py:5347-5351 at 7e68a30f.
pub fn parse_backlog(raw: Option<&str>) -> u32 {
    let text = match raw {
        None | Some("") => return DEFAULT_BACKLOG,
        Some(text) => text,
    };
    let Some(value) = py_int(text) else {
        return DEFAULT_BACKLOG;
    };
    if value.negative {
        return MIN_BACKLOG;
    }
    let clamped = value.magnitude.min(i32::MAX as u64);
    u32::try_from(clamped)
        .unwrap_or(i32::MAX as u32)
        .max(MIN_BACKLOG)
}

/// The body limit in bytes: `int(value)` MiB when that is a positive integer, otherwise 256
/// MiB; shifted left by 20. A limit beyond `u64` saturates.
///
/// Behavior reference: project-maya serve/server.py:5365-5372 at 7e68a30f.
pub fn parse_max_body_bytes(raw: Option<&str>) -> u64 {
    let mib = match raw.and_then(py_int) {
        Some(v) if !v.negative && v.magnitude > 0 => v.magnitude,
        _ => DEFAULT_MAX_BODY_MIB,
    };
    if mib > (u64::MAX >> 20) {
        u64::MAX
    } else {
        mib << 20
    }
}

/// The per-operation timeout: `float(value)` seconds when that is greater than zero,
/// otherwise 300 s. Zero, negative, NaN and unparsable values give 300 s. Infinity, or a
/// value too large for a `Duration`, gives `Duration::MAX` (no practical limit).
///
/// Behavior reference: project-maya serve/server.py:5354-5362 at 7e68a30f.
pub fn parse_request_timeout(raw: Option<&str>) -> Duration {
    let seconds = raw.and_then(py_float).unwrap_or(0.0);
    if seconds > 0.0 {
        Duration::try_from_secs_f64(seconds).unwrap_or(Duration::MAX)
    } else {
        Duration::from_secs(DEFAULT_REQUEST_TIMEOUT_S)
    }
}

/// An integer read by Python's `int()`: its sign and its magnitude, which saturates at
/// `u64::MAX`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct PyInt {
    /// True for a `-` sign with a non-zero magnitude.
    pub(crate) negative: bool,
    /// The absolute value, saturating.
    pub(crate) magnitude: u64,
}

/// Python `int(text)` with base 10: surrounding Python whitespace, an optional sign, ASCII
/// digits with single `_` between digits, at most 4300 digits. `None` where Python raises
/// `ValueError`. Python also accepts non-ASCII decimal digits; text that reaches this
/// function from an HTTP header is Latin-1, where there are none, and environment values
/// with them are refused here (reported as an open question of API-02).
pub(crate) fn py_int(text: &str) -> Option<PyInt> {
    let s = pystr::strip(text, None);
    let (negative, digits) = split_sign(s);
    let digit_count = check_digits(digits, |c| c.is_ascii_digit())?;
    if digit_count > PY_MAX_STR_DIGITS {
        return None;
    }
    let mut magnitude: u64 = 0;
    for c in digits.chars() {
        if let Some(d) = c.to_digit(10) {
            magnitude = magnitude.saturating_mul(10).saturating_add(u64::from(d));
        }
    }
    Some(PyInt {
        negative: negative && magnitude > 0,
        magnitude,
    })
}

/// Python `float(text)`: surrounding whitespace, `_` only between digits, then the decimal,
/// `inf`, `infinity` and `nan` forms. `None` where Python raises `ValueError`.
fn py_float(text: &str) -> Option<f64> {
    let s = pystr::strip(text, None);
    if s.is_empty() {
        return None;
    }
    let chars: Vec<char> = s.chars().collect();
    let mut cleaned = String::with_capacity(s.len());
    for (i, &c) in chars.iter().enumerate() {
        if c == '_' {
            let before = i.checked_sub(1).and_then(|j| chars.get(j));
            let after = chars.get(i + 1);
            let digit = |x: Option<&char>| x.is_some_and(|c| c.is_ascii_digit());
            if !(digit(before) && digit(after)) {
                return None;
            }
            continue;
        }
        if !c.is_ascii() {
            return None;
        }
        cleaned.push(c);
    }
    cleaned.parse::<f64>().ok()
}

/// Splits an optional leading `+` or `-`.
fn split_sign(s: &str) -> (bool, &str) {
    if let Some(rest) = s.strip_prefix('-') {
        (true, rest)
    } else if let Some(rest) = s.strip_prefix('+') {
        (false, rest)
    } else {
        (false, s)
    }
}

/// Checks Python's digit-and-underscore grammar (a digit first and last, no `__`) and
/// returns the number of digits.
fn check_digits(digits: &str, is_digit: impl Fn(char) -> bool) -> Option<usize> {
    let mut count = 0usize;
    let mut previous_underscore = true;
    for c in digits.chars() {
        if c == '_' {
            if previous_underscore {
                return None;
            }
            previous_underscore = true;
        } else if is_digit(c) {
            count += 1;
            previous_underscore = false;
        } else {
            return None;
        }
    }
    if count == 0 || previous_underscore {
        return None;
    }
    Some(count)
}

/// A chunk size read as the donor does: `int(line.split(b";", 1)[0].strip(), 16)`. Returns
/// the sign and the magnitude (saturating), or `None` where Python raises `ValueError`.
///
/// Python's `int(bytes, 16)` takes ASCII whitespace around the number, a sign, an optional
/// `0x` or `0X` prefix (after which one `_` may come first), and hexadecimal digits with
/// single `_` between them.
pub(crate) fn py_hex_chunk_size(line: &[u8]) -> Option<PyInt> {
    let head = match line.iter().position(|&b| b == b';') {
        Some(at) => line.get(..at).unwrap_or(line),
        None => line,
    };
    let trimmed = trim_ascii_space(head);
    let text = std::str::from_utf8(trimmed).ok()?;
    if !text.is_ascii() {
        return None;
    }
    let (negative, rest) = split_sign(text);
    let (prefixed, digits) = match rest.strip_prefix("0x").or_else(|| rest.strip_prefix("0X")) {
        Some(after) => (true, after),
        None => (false, rest),
    };
    // After a base prefix, Python allows one leading underscore ("0x_1a").
    let digits = if prefixed {
        digits.strip_prefix('_').unwrap_or(digits)
    } else {
        digits
    };
    check_digits(digits, |c| c.is_ascii_hexdigit())?;
    let mut magnitude: u64 = 0;
    for c in digits.chars() {
        if let Some(d) = c.to_digit(16) {
            magnitude = magnitude.saturating_mul(16).saturating_add(u64::from(d));
        }
    }
    Some(PyInt {
        negative: negative && magnitude > 0,
        magnitude,
    })
}

/// Python `bytes.strip()`: removes ASCII whitespace (space, `\t`, `\n`, `\r`, `\x0b`,
/// `\x0c`) from both ends.
pub(crate) fn trim_ascii_space(bytes: &[u8]) -> &[u8] {
    let is_space = |b: &u8| matches!(b, b' ' | b'\t' | b'\n' | b'\r' | 0x0b | 0x0c);
    let start = bytes
        .iter()
        .position(|b| !is_space(b))
        .unwrap_or(bytes.len());
    let end = bytes
        .iter()
        .rposition(|b| !is_space(b))
        .map_or(start, |p| p + 1);
    bytes.get(start..end).unwrap_or(&[])
}

#[cfg(test)]
mod tests {
    // Provenance: translated from project-maya serve/test_server.py::RequestBodies::test_the_listen_backlog at 7e68a30f (MIT); license text in console/LICENSES/project-maya-MIT.txt.

    use super::*;

    // Expected values follow CPython 3.14 `int()`, `float()` and `max()` on the same text.
    #[test]
    fn backlog_follows_the_donor() {
        assert_eq!(parse_backlog(None), 256);
        assert_eq!(parse_backlog(Some("")), 256);
        assert_eq!(parse_backlog(Some("abc")), 256);
        assert_eq!(parse_backlog(Some("1.5")), 256);
        assert_eq!(parse_backlog(Some("0")), 5);
        assert_eq!(parse_backlog(Some("3")), 5);
        assert_eq!(parse_backlog(Some("-40")), 5);
        assert_eq!(parse_backlog(Some(" 1_024 ")), 1024);
        assert_eq!(parse_backlog(Some("+64")), 64);
        assert_eq!(parse_backlog(Some("99999999999999999999")), i32::MAX as u32);
        assert_eq!(parse_backlog(Some("1__0")), 256);
        assert_eq!(parse_backlog(Some("_10")), 256);
        assert_eq!(parse_backlog(Some("10_")), 256);
    }

    #[test]
    fn body_limit_follows_the_donor() {
        assert_eq!(parse_max_body_bytes(None), 256 << 20);
        assert_eq!(parse_max_body_bytes(Some("0")), 256 << 20);
        assert_eq!(parse_max_body_bytes(Some("-3")), 256 << 20);
        assert_eq!(parse_max_body_bytes(Some("x")), 256 << 20);
        assert_eq!(parse_max_body_bytes(Some("2.5")), 256 << 20);
        assert_eq!(parse_max_body_bytes(Some("1")), 1 << 20);
        assert_eq!(parse_max_body_bytes(Some("\t512\n")), 512 << 20);
        assert_eq!(parse_max_body_bytes(Some("99999999999999999999")), u64::MAX);
        let config = TransportConfig::from_raw(None, Some("3"), None);
        assert_eq!(config.max_body_mib(), 3);
    }

    #[test]
    fn timeout_follows_the_donor() {
        let default = Duration::from_secs(300);
        assert_eq!(parse_request_timeout(None), default);
        assert_eq!(parse_request_timeout(Some("")), default);
        assert_eq!(parse_request_timeout(Some("0")), default);
        assert_eq!(parse_request_timeout(Some("-1")), default);
        assert_eq!(parse_request_timeout(Some("nan")), default);
        assert_eq!(parse_request_timeout(Some("soon")), default);
        assert_eq!(parse_request_timeout(Some("1_.5")), default);
        assert_eq!(parse_request_timeout(Some("2")), Duration::from_secs(2));
        assert_eq!(
            parse_request_timeout(Some(" 0.5 ")),
            Duration::from_millis(500)
        );
        assert_eq!(parse_request_timeout(Some("1_0")), Duration::from_secs(10));
        assert_eq!(parse_request_timeout(Some("1e1")), Duration::from_secs(10));
        assert_eq!(parse_request_timeout(Some("inf")), Duration::MAX);
        assert_eq!(parse_request_timeout(Some("1e300")), Duration::MAX);
    }

    #[test]
    fn defaults_are_the_donors() {
        let config = TransportConfig::default();
        assert_eq!(config.backlog, 256);
        assert_eq!(config.max_body_bytes, 268_435_456);
        assert_eq!(config.request_timeout, Duration::from_secs(300));
        assert_eq!(TransportConfig::from_raw(None, None, None), config);
    }

    #[test]
    fn python_int_grammar() {
        let int = |s: &str| py_int(s).map(|v| (v.negative, v.magnitude));
        assert_eq!(int("5"), Some((false, 5)));
        assert_eq!(int(" -5 "), Some((true, 5)));
        assert_eq!(int("-0"), Some((false, 0)));
        assert_eq!(int("007"), Some((false, 7)));
        assert_eq!(int("\u{a0}12\u{85}"), Some((false, 12)));
        assert_eq!(int(""), None);
        assert_eq!(int("+"), None);
        assert_eq!(int("1 2"), None);
        assert_eq!(int("0x10"), None);
        assert_eq!(int("\u{b2}"), None);
        assert_eq!(int(&"9".repeat(4300)), Some((false, u64::MAX)));
        assert_eq!(int(&"9".repeat(4301)), None);
    }

    #[test]
    fn python_hex_chunk_sizes() {
        let hex = |s: &[u8]| py_hex_chunk_size(s).map(|v| (v.negative, v.magnitude));
        assert_eq!(hex(b"1a\r\n"), Some((false, 26)));
        assert_eq!(hex(b"1A;ext=1\r\n"), Some((false, 26)));
        assert_eq!(hex(b" 0x1a \r\n"), Some((false, 26)));
        assert_eq!(hex(b"0X_1a\r\n"), Some((false, 26)));
        assert_eq!(hex(b"1_0\n"), Some((false, 16)));
        assert_eq!(hex(b"-1\r\n"), Some((true, 1)));
        assert_eq!(hex(b"-0\r\n"), Some((false, 0)));
        assert_eq!(hex(b"0\r\n"), Some((false, 0)));
        assert_eq!(hex(b"zz\r\n"), None);
        assert_eq!(hex(b"\r\n"), None);
        assert_eq!(hex(b"_1\r\n"), None);
        assert_eq!(hex(b"0x\r\n"), None);
        assert_eq!(hex(b"1__0\r\n"), None);
        assert_eq!(hex(b"ffffffffffffffffffff\r\n"), Some((false, u64::MAX)));
        assert_eq!(trim_ascii_space(b" \t\x0bab \r\n"), b"ab");
        assert_eq!(trim_ascii_space(b"  "), b"");
    }
}
