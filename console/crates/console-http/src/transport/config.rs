//! The transport's three settings: the conversion of the resolved values into a
//! [`TransportConfig`], and the raw-text path that reads them with the donor's rules.
//!
//! The settings have one source of truth. The rule that turns a variable's text into a
//! value (Python's `int()` and `float()` syntax, the defaults, the minimum and the
//! fallbacks) lives in console-core, on [`EnvSettings`] (`http_backlog_from`,
//! `max_body_mib_from`, `request_timeout_s_from`); the conversion of those values into the
//! listener's settings (the clamp to the platform's `int`, the shift to bytes, a
//! `Duration` that cannot panic) lives here, in [`TransportConfig::from_values`]. The
//! server builds its settings with [`TransportConfig::from_settings`] from the resolved
//! [`EnvSettings`] (the run config's `env` block laid over the environment); the raw-text
//! path ([`TransportConfig::from_raw`] and the three `parse_` functions) delegates to the
//! same two halves, so the two paths cannot drift apart.
//!
//! Behavior reference: project-maya serve/server.py:5346-5372 at 7e68a30f.

use std::time::Duration;

use console_core::config::EnvSettings;
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
    /// The settings from the resolved values of the three variables, as the donor converts
    /// them: the backlog is at least 5 and at most `i32::MAX` (CPython's `listen()` would
    /// raise `OverflowError` beyond the platform's `int`); a body limit of 0 or less is
    /// 256 MiB, and a limit beyond `u64` bytes saturates; a timeout of 0 or less, or `nan`,
    /// is 300 s, and an infinite one, or one too large for a `Duration`, is
    /// `Duration::MAX` (no practical limit).
    ///
    /// Behavior reference: project-maya serve/server.py:5347-5372 at 7e68a30f.
    pub fn from_values(http_backlog: i64, max_body_mib: i64, request_timeout_s: f64) -> Self {
        Self {
            backlog: backlog_value(http_backlog),
            max_body_bytes: body_bytes_value(max_body_mib),
            request_timeout: timeout_value(request_timeout_s),
        }
    }

    /// The settings from the server's resolved environment settings: their
    /// `http_backlog`, `max_body_mib` and `request_timeout_s` ([`Self::from_values`]).
    /// This is how the server and the test kit build the listener's settings.
    pub fn from_settings(env: &EnvSettings) -> Self {
        Self::from_values(env.http_backlog, env.max_body_mib, env.request_timeout_s)
    }

    /// The settings from the raw text of the three variables (`None` when unset): the rules
    /// of [`EnvSettings`], then [`Self::from_values`].
    pub fn from_raw(
        backlog: Option<&str>,
        max_body_mib: Option<&str>,
        request_timeout_s: Option<&str>,
    ) -> Self {
        Self::from_values(
            EnvSettings::http_backlog_from(backlog),
            EnvSettings::max_body_mib_from(max_body_mib),
            EnvSettings::request_timeout_s_from(request_timeout_s),
        )
    }

    /// The body limit in whole MiB, as the 413 message prints it (`limit >> 20`).
    pub fn max_body_mib(&self) -> u64 {
        self.max_body_bytes >> 20
    }
}

/// The listen backlog from the raw text: `max(5, int(value or 256))`, and 256 when the
/// value is not an integer. An unset or empty value gives 256; `"0"` and negative values
/// give 5. A value beyond `i32::MAX` is clamped there (CPython's `listen()` would raise
/// `OverflowError`). Delegates to [`EnvSettings::http_backlog_from`].
///
/// Behavior reference: project-maya serve/server.py:5347-5351 at 7e68a30f.
pub fn parse_backlog(raw: Option<&str>) -> u32 {
    backlog_value(EnvSettings::http_backlog_from(raw))
}

/// The body limit in bytes from the raw text: `int(value)` MiB when that is a positive
/// integer, otherwise 256 MiB; shifted left by 20. A limit beyond `u64` saturates.
/// Delegates to [`EnvSettings::max_body_mib_from`].
///
/// Behavior reference: project-maya serve/server.py:5365-5372 at 7e68a30f.
pub fn parse_max_body_bytes(raw: Option<&str>) -> u64 {
    body_bytes_value(EnvSettings::max_body_mib_from(raw))
}

/// The per-operation timeout from the raw text: `float(value)` seconds when that is
/// greater than zero, otherwise 300 s. Zero, negative, NaN and unparsable values give
/// 300 s. Infinity, or a value too large for a `Duration`, gives `Duration::MAX` (no
/// practical limit). Delegates to [`EnvSettings::request_timeout_s_from`].
///
/// Behavior reference: project-maya serve/server.py:5354-5362 at 7e68a30f.
pub fn parse_request_timeout(raw: Option<&str>) -> Duration {
    timeout_value(EnvSettings::request_timeout_s_from(raw))
}

/// `max(5, n)`, clamped to `i32::MAX`.
fn backlog_value(n: i64) -> u32 {
    let clamped = n.clamp(i64::from(MIN_BACKLOG), i64::from(i32::MAX));
    u32::try_from(clamped).unwrap_or(DEFAULT_BACKLOG)
}

/// `(mib if mib > 0 else 256) << 20`, saturating at `u64::MAX`.
fn body_bytes_value(mib: i64) -> u64 {
    let mib = u64::try_from(mib)
        .ok()
        .filter(|m| *m > 0)
        .unwrap_or(DEFAULT_MAX_BODY_MIB);
    if mib > (u64::MAX >> 20) {
        u64::MAX
    } else {
        mib << 20
    }
}

/// `s if s > 0 else 300.0` as a `Duration`, without panicking on `inf` or a huge value.
fn timeout_value(seconds: f64) -> Duration {
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
    fn typed_values_keep_the_donors_bounds() {
        let backlog = |n| TransportConfig::from_values(n, 1, 1.0).backlog;
        assert_eq!(backlog(i64::MIN), 5);
        assert_eq!(backlog(0), 5);
        assert_eq!(backlog(5), 5);
        assert_eq!(backlog(64), 64);
        assert_eq!(backlog(i64::from(i32::MAX)), i32::MAX as u32);
        assert_eq!(backlog(i64::MAX), i32::MAX as u32);
        let body = |m| TransportConfig::from_values(256, m, 1.0).max_body_bytes;
        assert_eq!(body(i64::MIN), 256 << 20);
        assert_eq!(body(-1), 256 << 20);
        assert_eq!(body(0), 256 << 20);
        assert_eq!(body(1), 1 << 20);
        assert_eq!(body((1 << 44) - 1), ((1u64 << 44) - 1) << 20);
        assert_eq!(body(1 << 44), u64::MAX);
        assert_eq!(body(i64::MAX), u64::MAX);
        let timeout = |s| TransportConfig::from_values(256, 1, s).request_timeout;
        let default = Duration::from_secs(300);
        assert_eq!(timeout(0.0), default);
        assert_eq!(timeout(-0.0), default);
        assert_eq!(timeout(-1.0), default);
        assert_eq!(timeout(f64::NAN), default);
        assert_eq!(timeout(f64::NEG_INFINITY), default);
        assert_eq!(timeout(0.5), Duration::from_millis(500));
        assert_eq!(timeout(f64::INFINITY), Duration::MAX);
        assert_eq!(timeout(1e300), Duration::MAX);
    }

    /// The raw-text path and the resolved-settings path give the same settings on every
    /// edge case the two listed before they were merged (the second path is the one the
    /// server uses: `EnvSettings::from_env`, then `from_settings`).
    #[test]
    fn the_raw_text_and_the_resolved_settings_agree() {
        use std::collections::BTreeMap;
        let long = "9".repeat(4300);
        let too_long = "9".repeat(4301);
        let ints = [
            "",
            "abc",
            "1.5",
            "0",
            "3",
            "-40",
            "-0",
            " 1_024 ",
            "+64",
            "1__0",
            "_10",
            "10_",
            "x",
            "2.5",
            "1",
            "\t512\n",
            "99999999999999999999",
            "17592186044416",
            "007",
            "\u{a0}12\u{85}",
            "\u{b2}",
            "0x10",
            &long,
            &too_long,
        ];
        let floats = [
            "", "0", "-1", "nan", "-nan", "soon", "1_.5", "2", " 0.5 ", "1_0", "1e1", "inf",
            "-inf", "Infinity", "1e300", "1e-12",
        ];
        let check = |b: Option<&str>, m: Option<&str>, t: Option<&str>| {
            let mut env = BTreeMap::new();
            for (name, value) in [
                (ENV_HTTP_BACKLOG, b),
                (ENV_MAX_BODY_MIB, m),
                (ENV_REQUEST_TIMEOUT_S, t),
            ] {
                if let Some(v) = value {
                    env.insert(name.to_owned(), v.to_owned());
                }
            }
            let resolved = TransportConfig::from_settings(&EnvSettings::from_env(&env));
            assert_eq!(
                TransportConfig::from_raw(b, m, t),
                resolved,
                "{b:?} {m:?} {t:?}"
            );
            assert_eq!(parse_backlog(b), resolved.backlog, "{b:?}");
            assert_eq!(parse_max_body_bytes(m), resolved.max_body_bytes, "{m:?}");
            assert_eq!(parse_request_timeout(t), resolved.request_timeout, "{t:?}");
        };
        check(None, None, None);
        for i in ints {
            check(Some(i), Some(i), None);
        }
        for f in floats {
            check(None, None, Some(f));
        }
        assert_eq!(parse_backlog(Some(&too_long)), 256);
        assert_eq!(parse_max_body_bytes(Some(&too_long)), 256 << 20);
        assert_eq!(parse_backlog(Some(&long)), i32::MAX as u32);
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
