//! The class checks of `contracts/volatile-fields.json`. A value is replaced by its class
//! placeholder only when its check passes; a value that fails stays as sent and is
//! compared exactly, so a wrong type, a negative figure, a time stamp outside the run
//! window or a malformed id is still a difference.

/// The time a side ran in, as seconds since the epoch.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct RunWindow {
    /// When the side started (before the server was started).
    pub start: f64,
    /// When the side ended (after the last observation was taken).
    pub end: f64,
}

impl RunWindow {
    /// Whether `t` lies in the window, widened to whole seconds (a server that writes
    /// `int(time.time())` rounds down) and with `extra` seconds added to the end.
    pub(crate) fn contains(&self, t: f64, extra: f64) -> bool {
        t.is_finite() && t >= self.start.floor() && t <= (self.end + extra).ceil()
    }
}

/// How a number token is written: the placeholder keeps this, so an integer that turns
/// into a fraction (or back) is still a difference.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum Shape {
    /// Digits only.
    Integer,
    /// With a fraction and no exponent.
    Fraction,
    /// With an exponent (Python's `repr` of a float below 1e-4 or from 1e16 on).
    Exponent,
}

impl Shape {
    pub(crate) fn suffix(self) -> &'static str {
        match self {
            Shape::Integer => "",
            Shape::Fraction => ":f",
            Shape::Exponent => ":e",
        }
    }
}

/// A non-negative JSON number token (RFC 8259 grammar, no minus sign): its shape and
/// value. Python writes its figures this way (`repr` of an `int` or a `float`).
pub(crate) fn non_negative_number(lexeme: &str) -> Option<(Shape, f64)> {
    let b = lexeme.as_bytes();
    let mut i = 0;
    let digits = |i: &mut usize| {
        let s = *i;
        while b.get(*i).is_some_and(u8::is_ascii_digit) {
            *i += 1;
        }
        *i - s
    };
    match b.first()? {
        b'0' => i = 1,
        b'1'..=b'9' => {
            digits(&mut i);
        }
        _ => return None,
    }
    let mut shape = Shape::Integer;
    if b.get(i) == Some(&b'.') {
        i += 1;
        if digits(&mut i) == 0 {
            return None;
        }
        shape = Shape::Fraction;
    }
    if matches!(b.get(i), Some(b'e' | b'E')) {
        i += 1;
        if matches!(b.get(i), Some(b'+' | b'-')) {
            i += 1;
        }
        if digits(&mut i) == 0 {
            return None;
        }
        shape = Shape::Exponent;
    }
    if i != b.len() {
        return None;
    }
    let v: f64 = lexeme.parse().ok()?;
    v.is_finite().then_some((shape, v))
}

/// Seconds since the epoch written as digits, with an optional fraction and no
/// exponent (`int(time.time())` or `time.time()`).
pub(crate) fn epoch(lexeme: &str) -> Option<(Shape, f64)> {
    if lexeme.bytes().any(|c| c == b'e' || c == b'E') {
        return None;
    }
    non_negative_number(lexeme)
}

/// A time stamp as project-maya writes it: `datetime.isoformat()` in UTC with `+00:00`
/// replaced by `Z`, so `YYYY-MM-DDTHH:MM:SS` then either nothing or six fraction digits,
/// then `Z`. Returns seconds since the epoch.
///
/// Behavior reference: project-maya serve/model_api.py:57-58 at 7e68a30f.
pub(crate) fn iso_utc(s: &str) -> Option<f64> {
    let b = s.as_bytes();
    let num = |from: usize, len: usize| -> Option<i64> {
        let part = b.get(from..from + len)?;
        if !part.iter().all(u8::is_ascii_digit) {
            return None;
        }
        std::str::from_utf8(part).ok()?.parse().ok()
    };
    let sep = |at: usize, c: u8| b.get(at) == Some(&c);
    if !(sep(4, b'-') && sep(7, b'-') && sep(10, b'T') && sep(13, b':') && sep(16, b':')) {
        return None;
    }
    let (year, month, day) = (num(0, 4)?, num(5, 2)?, num(8, 2)?);
    let (hour, minute, second) = (num(11, 2)?, num(14, 2)?, num(17, 2)?);
    let fraction = match b.len() {
        20 if sep(19, b'Z') => 0.0,
        27 if sep(19, b'.') && sep(26, b'Z') => num(20, 6)? as f64 / 1e6,
        _ => return None,
    };
    let leap = (year % 4 == 0 && year % 100 != 0) || year % 400 == 0;
    let month_days = [
        31,
        if leap { 29 } else { 28 },
        31,
        30,
        31,
        30,
        31,
        31,
        30,
        31,
        30,
        31,
    ];
    let max_day = *month_days.get(usize::try_from(month).ok()?.checked_sub(1)?)?;
    if year < 1 || day < 1 || day > max_day || hour > 23 || minute > 59 || second > 59 {
        return None;
    }
    let days = days_from_civil(year, month, day);
    Some((days * 86_400 + hour * 3_600 + minute * 60 + second) as f64 + fraction)
}

/// Days from 1970-01-01 to the given proleptic Gregorian date (H. Hinnant's algorithm).
fn days_from_civil(y: i64, m: i64, d: i64) -> i64 {
    let y = if m <= 2 { y - 1 } else { y };
    let era = if y >= 0 { y } else { y - 399 } / 400;
    let yoe = y - era * 400;
    let mp = (m + 9) % 12;
    let doy = (153 * mp + 2) / 5 + d - 1;
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    era * 146_097 + doe - 719_468
}

/// An HTTP date in the IMF-fixdate form of RFC 9110 section 5.6.7, as Python writes the
/// `Date` header (`BaseHTTPRequestHandler.date_time_string`, which calls
/// `email.utils.formatdate(timestamp, usegmt=True)`): `Www, DD Mon YYYY HH:MM:SS GMT`
/// with English day and month names, a two-digit day and a weekday that matches the
/// date. Returns seconds since the epoch.
///
/// Behavior reference: project-maya serve/server.py:5459 at 7e68a30f (`send_response`,
/// which writes the header), CPython 3.14 `http.server` and `email.utils`.
pub(crate) fn imf_fixdate(s: &str) -> Option<f64> {
    const DAYS: [&str; 7] = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
    const MONTHS: [&str; 12] = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ];
    if s.len() != 29 || !s.is_ascii() {
        return None;
    }
    let part = |from: usize, to: usize| s.get(from..to).unwrap_or_default();
    let weekday = DAYS.iter().position(|d| part(0, 3) == *d)?;
    let month = MONTHS.iter().position(|m| part(8, 11) == *m)? + 1;
    let fixed = [(3, ", "), (7, " "), (11, " "), (16, " "), (25, " GMT")];
    if !fixed
        .iter()
        .all(|(at, lit)| part(*at, at + lit.len()) == *lit)
    {
        return None;
    }
    let iso = format!(
        "{}-{month:02}-{}T{}Z",
        part(12, 16),
        part(5, 7),
        part(17, 25)
    );
    let t = iso_utc(&iso)?;
    let days = (t / 86_400.0).floor() as i64;
    // 1970-01-01 was a Thursday, index 3 from Monday
    (usize::try_from((days + 3).rem_euclid(7)).ok() == Some(weekday)).then_some(t)
}

/// `prefix` followed by exactly `hex_digits` lower-case hex digits, and nothing else.
pub(crate) fn is_id(value: &str, prefix: &str, hex_digits: u64) -> bool {
    value.strip_prefix(prefix).is_some_and(|rest| {
        u64::try_from(rest.len()).is_ok_and(|n| n == hex_digits) && is_lower_hex(rest)
    })
}

pub(crate) fn is_lower_hex(s: &str) -> bool {
    !s.is_empty()
        && s.bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
}

/// A positive decimal integer without a leading zero that fits an `i32` (a process id).
pub(crate) fn pid(s: &str) -> bool {
    !s.starts_with('0')
        && !s.is_empty()
        && s.bytes().all(|c| c.is_ascii_digit())
        && s.parse::<i32>().is_ok_and(|n| n > 0)
}

/// A decimal port from 1 to 65535 without a leading zero, equal to `listening`.
pub(crate) fn port(s: &str, listening: Option<u16>) -> bool {
    !s.starts_with('0')
        && s.bytes().all(|c| c.is_ascii_digit())
        && s.parse::<u16>().ok().filter(|p| *p != 0) == listening.filter(|p| *p != 0)
        && listening.is_some()
}

/// Whether `path` is one of `dirs` or lies under one; returns the length of the matched
/// directory prefix.
pub(crate) fn under_tmp(path: &str, dirs: &[String]) -> Option<usize> {
    dirs.iter()
        .filter(|d| !d.is_empty())
        .filter(|d| {
            let d = d.trim_end_matches('/');
            !d.is_empty()
                && path
                    .strip_prefix(d)
                    .is_some_and(|rest| rest.is_empty() || rest.starts_with('/'))
        })
        .map(|d| d.trim_end_matches('/').len())
        .max()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn numbers_keep_their_shape() {
        assert_eq!(non_negative_number("12"), Some((Shape::Integer, 12.0)));
        assert_eq!(non_negative_number("0.5"), Some((Shape::Fraction, 0.5)));
        assert_eq!(non_negative_number("1e-05"), Some((Shape::Exponent, 1e-5)));
        assert_eq!(
            non_negative_number("1.5e+16"),
            Some((Shape::Exponent, 1.5e16))
        );
        for bad in ["-1", "01", "1.", "", "inf", "nan", "+1", "1e", " 1"] {
            assert_eq!(non_negative_number(bad), None, "{bad}");
        }
        assert_eq!(epoch("1e9"), None);
        assert_eq!(
            epoch("1731600000.25"),
            Some((Shape::Fraction, 1_731_600_000.25))
        );
    }

    #[test]
    fn iso_stamps_follow_python() {
        assert_eq!(iso_utc("1970-01-01T00:00:00Z"), Some(0.0));
        assert_eq!(
            iso_utc("2024-02-29T12:00:00.500000Z"),
            Some(1_709_208_000.5)
        );
        for bad in [
            "2023-02-29T00:00:00Z",
            "2024-01-01T00:00:00+00:00",
            "2024-01-01T00:00:00.5Z",
            "2024-01-01 00:00:00Z",
            "2024-13-01T00:00:00Z",
            "2024-01-01T24:00:00Z",
            "0000-01-01T00:00:00Z",
        ] {
            assert_eq!(iso_utc(bad), None, "{bad}");
        }
        // the donor's constant for "no idle unload" parses, and lies outside any run
        let never = iso_utc("0001-01-01T00:00:00Z").unwrap_or(0.0);
        assert!(!RunWindow {
            start: 1.0e9,
            end: 2.0e9
        }
        .contains(never, 0.0));
    }

    #[test]
    fn http_dates_follow_python() {
        assert_eq!(
            imf_fixdate("Thu, 14 Nov 2024 16:00:00 GMT"),
            Some(1_731_600_000.0)
        );
        assert_eq!(imf_fixdate("Thu, 01 Jan 1970 00:00:00 GMT"), Some(0.0));
        for bad in [
            "Fri, 14 Nov 2024 16:00:00 GMT",
            "Thu, 14 Nov 2024 16:00:00 UTC",
            "Thu, 4 Nov 2024 16:00:00 GMT",
            "Thu, 14 nov 2024 16:00:00 GMT",
            "Thursday, 14 Nov 2024 16:00:00 GMT",
            "Thu, 14 Nov 2024 16:00:00 GMT ",
            "Thu, 31 Nov 2024 16:00:00 GMT",
            "Thu, 14-Nov-2024 16:00:00 GMT",
            "2024-11-14T16:00:00Z",
            "yesterday",
            "",
        ] {
            assert_eq!(imf_fixdate(bad), None, "{bad}");
        }
    }

    #[test]
    fn ids_ports_pids_and_paths() {
        assert!(is_id("chatcmpl-0123456789abcdef01234567", "chatcmpl-", 24));
        assert!(!is_id("chatcmpl-0123456789ABCDEF01234567", "chatcmpl-", 24));
        assert!(!is_id("chatcmpl-0123456789abcdef0123456", "chatcmpl-", 24));
        assert!(!is_id("call_loop_guard", "call_", 24));
        assert!(port("8080", Some(8080)));
        assert!(!port("8081", Some(8080)));
        assert!(!port("08080", Some(8080)));
        assert!(!port("8080", None));
        assert!(pid("4242") && !pid("0") && !pid("042") && !pid("99999999999"));
        let dirs = vec!["/t/run".to_string()];
        assert_eq!(under_tmp("/t/run/a.json", &dirs), Some(6));
        assert_eq!(under_tmp("/t/run", &dirs), Some(6));
        assert_eq!(under_tmp("/t/runner/a.json", &dirs), None);
    }
}
