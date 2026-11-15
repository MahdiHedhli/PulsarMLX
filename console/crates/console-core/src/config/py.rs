//! Python value semantics the run config needs: `int()` and `float()` on setting text,
//! `str()`, `repr()`, truthiness, `==` and `max()` on decoded JSON values, and the
//! case-insensitive secret-name test.
//!
//! Behavior reference: the CPython 3 built-ins `int`, `float`, `str`, `repr`, `max` and
//! `re.IGNORECASE`, as project-maya serve/server.py and serve/models.py use them at 7e68a30f.

use console_pyjson::dumps::{classify_number, PyNumber};
use console_pyjson::float_repr::repr_f64;
use console_pyjson::pystr;
use serde_json::Value;

/// Removes single underscores that stand between two ASCII digits, as Python's `int()` and
/// `float()` allow; `None` for any other underscore or for non-ASCII text.
fn strip_digit_underscores(s: &str) -> Option<String> {
    if !s.is_ascii() {
        return None;
    }
    let bytes = s.as_bytes();
    let mut cleaned = String::with_capacity(s.len());
    for (i, &b) in bytes.iter().enumerate() {
        if b == b'_' {
            let before = i.checked_sub(1).and_then(|j| bytes.get(j));
            let after = bytes.get(i + 1);
            match (before, after) {
                (Some(x), Some(y)) if x.is_ascii_digit() && y.is_ascii_digit() => continue,
                _ => return None,
            }
        }
        cleaned.push(char::from(b));
    }
    Some(cleaned)
}

/// Python's `float(s)` for a `str`: surrounding Python whitespace ignored, an optional sign,
/// a decimal or exponent form with single underscores between digits, or `inf`,
/// `infinity` and `nan` in any case. Non-ASCII digits, which Python also reads, give `None`.
pub(crate) fn py_float(s: &str) -> Option<f64> {
    let cleaned = strip_digit_underscores(pystr::strip(s, None))?;
    // Rust also reads "1e5", ".5", "1." and the non-finite words as Python does; it refuses
    // hexadecimal and the empty string, as Python does.
    cleaned.parse::<f64>().ok()
}

/// Python's `int(s)` for a `str`: surrounding Python whitespace ignored, an optional sign,
/// ASCII digits with single underscores between them. A value outside `i64` saturates (Python
/// integers are unbounded; no setting here can tell the difference). Non-ASCII digits give
/// `None`.
pub(crate) fn py_int(s: &str) -> Option<i64> {
    let cleaned = strip_digit_underscores(pystr::strip(s, None))?;
    let (negative, digits) = match cleaned.strip_prefix('-') {
        Some(d) => (true, d),
        None => (false, cleaned.strip_prefix('+').unwrap_or(&cleaned)),
    };
    if digits.is_empty() || !digits.bytes().all(|b| b.is_ascii_digit()) {
        return None;
    }
    match cleaned.parse::<i64>() {
        Ok(n) => Some(n),
        Err(_) if negative => Some(i64::MIN),
        Err(_) => Some(i64::MAX),
    }
}

/// Python's `max(a, b)` for floats: `b` only when `b > a`, so `max(0.0, nan)` is `0.0` and
/// `max(0.0, -0.0)` is `0.0`.
pub(crate) fn py_max(a: f64, b: f64) -> f64 {
    if b > a {
        b
    } else {
        a
    }
}

/// The message of Python's `ValueError` from `float(s)`.
pub(crate) fn float_error(s: &str) -> String {
    format!("could not convert string to float: {}", repr_str(s))
}

/// The message of Python's `ValueError` from `int(s)`.
pub(crate) fn int_error(s: &str) -> String {
    format!("invalid literal for int() with base 10: {}", repr_str(s))
}

/// Whether Python's `str.isprintable()` is false for one non-ASCII character, as far as it can
/// be told without the Unicode database: the C1 controls, the separators other than the space,
/// the format characters, the private-use planes and the non-characters. Unassigned code
/// points, which Python also escapes, are not recognized.
fn non_printable(c: char) -> bool {
    matches!(
        u32::from(c),
        0x80..=0xa0
            | 0xad
            | 0x600..=0x605
            | 0x61c
            | 0x6dd
            | 0x70f
            | 0x890..=0x891
            | 0x8e2
            | 0x1680
            | 0x180e
            | 0x2000..=0x200f
            | 0x2028..=0x202f
            | 0x205f..=0x2064
            | 0x2066..=0x206f
            | 0x3000
            | 0xe000..=0xf8ff
            | 0xfdd0..=0xfdef
            | 0xfeff
            | 0xfff9..=0xfffb
            | 0x110bd
            | 0x110cd
            | 0x13430..=0x1343f
            | 0x1bca0..=0x1bca3
            | 0x1d173..=0x1d17a
            | 0xe0001
            | 0xe0020..=0xe007f
            | 0xf0000..=0x10ffff
    ) || (u32::from(c) & 0xfffe) == 0xfffe
}

/// Python's `repr(s)` for a `str`: single quotes unless the text holds a single quote and no
/// double quote, backslash escapes for the quote, `\\`, `\t`, `\n` and `\r`, and `\x`, `\u` or
/// `\U` escapes for characters that are not printable.
pub(crate) fn repr_str(s: &str) -> String {
    let quote = if s.contains('\'') && !s.contains('"') {
        '"'
    } else {
        '\''
    };
    let mut out = String::with_capacity(s.len() + 2);
    out.push(quote);
    for c in s.chars() {
        match c {
            '\\' => out.push_str("\\\\"),
            '\t' => out.push_str("\\t"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            c if c == quote => {
                out.push('\\');
                out.push(c);
            }
            c if u32::from(c) < 0x20 || u32::from(c) == 0x7f => {
                out.push_str(&format!("\\x{:02x}", u32::from(c)));
            }
            c if u32::from(c) < 0x7f => out.push(c),
            c if non_printable(c) => {
                let n = u32::from(c);
                if n <= 0xff {
                    out.push_str(&format!("\\x{n:02x}"));
                } else if n <= 0xffff {
                    out.push_str(&format!("\\u{n:04x}"));
                } else {
                    out.push_str(&format!("\\U{n:08x}"));
                }
            }
            c => out.push(c),
        }
    }
    out.push(quote);
    out
}

/// The text of a JSON number as Python prints it: an `int`'s digits or a `float`'s `repr`.
fn number_text(n: &serde_json::Number) -> String {
    match classify_number(n) {
        Ok(PyNumber::Int(digits)) => digits,
        Ok(PyNumber::Float(x)) => repr_f64(x),
        Err(_) => n.to_string(),
    }
}

/// Python's `repr()` of a decoded JSON value: `None`, `True`, `False`, numbers, quoted
/// strings, `[a, b]` and `{'k': v}`. Nesting is bounded by the JSON reader's depth limit.
pub(crate) fn repr_value(v: &Value) -> String {
    match v {
        Value::String(s) => repr_str(s),
        Value::Array(items) => {
            let parts: Vec<String> = items.iter().map(repr_value).collect();
            format!("[{}]", parts.join(", "))
        }
        Value::Object(map) => {
            let parts: Vec<String> = map
                .iter()
                .map(|(k, v)| format!("{}: {}", repr_str(k), repr_value(v)))
                .collect();
            format!("{{{}}}", parts.join(", "))
        }
        other => str_value(other),
    }
}

/// Python's `str()` of a decoded JSON value: a string as it is, `None`, `True`, `False`,
/// numbers as Python prints them, and containers as their `repr`.
pub(crate) fn str_value(v: &Value) -> String {
    match v {
        Value::Null => String::from("None"),
        Value::Bool(true) => String::from("True"),
        Value::Bool(false) => String::from("False"),
        Value::Number(n) => number_text(n),
        Value::String(s) => s.clone(),
        Value::Array(_) | Value::Object(_) => repr_value(v),
    }
}

/// A JSON number as a Python `float` would hold it, or `None` for a value that is not a
/// number. `True` and `False` are not numbers here.
pub(crate) fn number_as_f64(n: &serde_json::Number) -> Option<f64> {
    match classify_number(n).ok()? {
        PyNumber::Int(digits) => digits.parse::<f64>().ok(),
        PyNumber::Float(x) => Some(x),
    }
}

/// Python's `==` between two decoded JSON values: `bool` is an `int` (`True == 1 == 1.0`),
/// an `int` equals a `float` of the same value, dictionaries compare without regard to key
/// order, and NaN equals nothing.
pub(crate) fn py_eq(a: &Value, b: &Value) -> bool {
    fn numeric(v: &Value) -> Option<NumKey> {
        match v {
            Value::Bool(b) => Some(NumKey::Int(if *b { "1" } else { "0" }.to_string())),
            Value::Number(n) => match classify_number(n).ok()? {
                PyNumber::Int(d) => Some(NumKey::Int(d)),
                PyNumber::Float(x) => Some(NumKey::Float(x)),
            },
            _ => None,
        }
    }
    match (a, b) {
        (Value::Null, Value::Null) => true,
        (Value::String(x), Value::String(y)) => x == y,
        (Value::Array(x), Value::Array(y)) => {
            x.len() == y.len() && x.iter().zip(y.iter()).all(|(p, q)| py_eq(p, q))
        }
        (Value::Object(x), Value::Object(y)) => {
            x.len() == y.len() && x.iter().all(|(k, v)| y.get(k).is_some_and(|w| py_eq(v, w)))
        }
        _ => match (numeric(a), numeric(b)) {
            (Some(p), Some(q)) => p.equals(&q),
            _ => false,
        },
    }
}

/// A Python number for equality: an exact `int` or a `float`.
enum NumKey {
    Int(String),
    Float(f64),
}

impl NumKey {
    fn equals(&self, other: &NumKey) -> bool {
        match (self, other) {
            (NumKey::Int(x), NumKey::Int(y)) => x == y,
            (NumKey::Float(x), NumKey::Float(y)) => x == y,
            (NumKey::Int(i), NumKey::Float(f)) | (NumKey::Float(f), NumKey::Int(i)) => {
                int_equals_float(i, *f)
            }
        }
    }
}

/// Python compares an `int` and a `float` exactly: `2**53 + 1 != 2.0**53`.
fn int_equals_float(digits: &str, f: f64) -> bool {
    if !f.is_finite() || f.fract() != 0.0 {
        return false;
    }
    match (digits.parse::<i128>(), f.abs() < 1.7e38) {
        // Every integral f64 below 2**127 is exactly an i128.
        (Ok(i), true) => i == f as i128,
        // Larger values: compare the integral float's exact decimal text.
        _ => format!("{f:.0}") == digits,
    }
}

/// Python's `x == 0` for a decoded JSON value (`False`, `0` and `0.0` are zero).
pub(crate) fn equals_zero(v: &Value) -> bool {
    py_eq(v, &Value::Bool(false))
}

/// Folds one character the way Python's `re.IGNORECASE` matches it against the lower-case
/// ASCII letters of the secret words: ASCII letters by case, the Kelvin sign as `k` and the
/// long s as `s`.
fn fold(c: char) -> char {
    match c {
        '\u{212a}' => 'k',
        '\u{17f}' => 's',
        c => c.to_ascii_lowercase(),
    }
}

/// Whether a variable name holds a secret: Python's
/// `re.compile(r"key|token|secret|password", re.I).search(name)`.
///
/// Behavior reference: project-maya serve/models.py:52 at 7e68a30f.
pub(crate) fn is_secret_name(name: &str) -> bool {
    const WORDS: [&str; 4] = ["key", "token", "secret", "password"];
    let folded: Vec<char> = name.chars().map(fold).collect();
    WORDS.iter().any(|word| {
        let w: Vec<char> = word.chars().collect();
        folded.windows(w.len()).any(|window| window == w.as_slice())
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use console_pyjson::loads::loads;

    fn v(text: &str) -> Value {
        loads(text).unwrap_or(Value::Null)
    }

    #[test]
    fn float_reads_python_forms() {
        assert_eq!(py_float(" 2.5 "), Some(2.5));
        assert_eq!(py_float("1_000"), Some(1000.0));
        assert_eq!(py_float("1e3"), Some(1000.0));
        assert_eq!(py_float("-0"), Some(-0.0));
        assert!(py_float("nan").is_some_and(f64::is_nan));
        assert_eq!(py_float("-Infinity"), Some(f64::NEG_INFINITY));
        assert_eq!(py_float(""), None);
        assert_eq!(py_float("1__0"), None);
        assert_eq!(py_float("_1"), None);
        assert_eq!(py_float("0x10"), None);
        assert_eq!(py_float("\u{1c}3\u{1f}"), Some(3.0));
    }

    #[test]
    fn int_reads_python_forms() {
        assert_eq!(py_int(" 64 "), Some(64));
        assert_eq!(py_int("+5"), Some(5));
        assert_eq!(py_int("-7"), Some(-7));
        assert_eq!(py_int("007"), Some(7));
        assert_eq!(py_int("1_0"), Some(10));
        assert_eq!(py_int("1.5"), None);
        assert_eq!(py_int(""), None);
        assert_eq!(py_int("-"), None);
        assert_eq!(py_int("99999999999999999999"), Some(i64::MAX));
        assert_eq!(py_int("-99999999999999999999"), Some(i64::MIN));
    }

    #[test]
    fn max_keeps_the_first_unless_the_second_is_greater() {
        assert_eq!(py_max(0.0, f64::NAN), 0.0);
        assert!(py_max(0.0, -0.0).is_sign_positive());
        assert_eq!(py_max(0.01, 0.001), 0.01);
        assert_eq!(py_max(0.0, f64::INFINITY), f64::INFINITY);
    }

    #[test]
    fn error_messages_are_python_s() {
        assert_eq!(float_error("x"), "could not convert string to float: 'x'");
        assert_eq!(float_error(""), "could not convert string to float: ''");
        assert_eq!(
            int_error("1.5"),
            "invalid literal for int() with base 10: '1.5'"
        );
    }

    #[test]
    fn repr_of_strings() {
        assert_eq!(repr_str("abc"), "'abc'");
        assert_eq!(repr_str("it's"), "\"it's\"");
        assert_eq!(repr_str("a'b\"c"), "'a\\'b\"c'");
        assert_eq!(repr_str("t\tn\nr\r\\"), "'t\\tn\\nr\\r\\\\'");
        assert_eq!(repr_str("\u{1}\u{7f}"), "'\\x01\\x7f'");
        assert_eq!(repr_str("é\u{a0}\u{2028}"), "'é\\xa0\\u2028'");
        assert_eq!(repr_str("\u{f0000}"), "'\\U000f0000'");
    }

    #[test]
    fn str_of_values() {
        assert_eq!(str_value(&v("null")), "None");
        assert_eq!(str_value(&v("true")), "True");
        assert_eq!(str_value(&v("0")), "0");
        assert_eq!(str_value(&v("1.50")), "1.5");
        assert_eq!(str_value(&v("1e5")), "100000.0");
        assert_eq!(str_value(&v("\"x y\"")), "x y");
        assert_eq!(
            str_value(&v("[1, \"a\", null, {\"k\": false}]")),
            "[1, 'a', None, {'k': False}]"
        );
    }

    #[test]
    fn equality_is_python_s() {
        assert!(py_eq(&v("1"), &v("1.0")));
        assert!(py_eq(&v("true"), &v("1")));
        assert!(py_eq(&v("false"), &v("0.0")));
        assert!(!py_eq(&v("\"1\""), &v("1")));
        assert!(py_eq(
            &v("{\"a\": 1, \"b\": 2}"),
            &v("{\"b\": 2, \"a\": 1.0}")
        ));
        assert!(!py_eq(&v("[1, 2]"), &v("[2, 1]")));
        assert!(!py_eq(&v("9007199254740993"), &v("9007199254740992.0")));
        assert!(py_eq(&v("9007199254740992"), &v("9007199254740992.0")));
        assert!(py_eq(&v("1e300"), &v("1e300")));
        assert!(equals_zero(&v("-0.0")));
        assert!(!equals_zero(&v("null")));
    }

    #[test]
    fn secret_names_match_case_insensitively() {
        for name in [
            "HF_TOKEN",
            "OPENAI_API_KEY",
            "my_Secret",
            "PASSWORD",
            "monkey",
        ] {
            assert!(is_secret_name(name), "{name}");
        }
        assert!(is_secret_name("\u{212a}EY"));
        assert!(is_secret_name("\u{17f}ecret"));
        for name in ["MAYA_GLM_RAM_HEADROOM_GB", "PATH", "kye", ""] {
            assert!(!is_secret_name(name), "{name}");
        }
    }
}
