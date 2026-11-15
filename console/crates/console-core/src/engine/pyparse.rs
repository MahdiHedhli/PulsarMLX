//! Python-compatible number parsing for engine figures (`int()` and `float()` on one
//! whitespace-free field).

/// Removes single underscores that stand between two ASCII digits, as Python's numeric
/// literals allow; `None` for any other underscore or for non-ASCII text.
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

/// Python's `float()` on a string: surrounding whitespace ignored, an optional sign, a
/// decimal or exponent form with single underscores between digits, or `inf`,
/// `infinity` and `nan` in any case. Non-ASCII digits, which Python also reads, give
/// `None`.
pub(crate) fn py_float(s: &str) -> Option<f64> {
    strip_digit_underscores(s.trim())?.parse::<f64>().ok()
}

/// Python's `int()` on a string, limited to `i64`: surrounding whitespace ignored, an
/// optional sign, ASCII digits with single underscores between them.
pub(crate) fn py_int(s: &str) -> Option<i64> {
    let cleaned = strip_digit_underscores(s.trim())?;
    let digits = cleaned
        .strip_prefix('-')
        .or_else(|| cleaned.strip_prefix('+'))
        .unwrap_or(&cleaned);
    if digits.is_empty() || !digits.bytes().all(|b| b.is_ascii_digit()) {
        return None;
    }
    cleaned.parse::<i64>().ok()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn py_float_matches_python_on_the_usual_forms() {
        assert_eq!(py_float("1"), Some(1.0));
        assert_eq!(py_float("-2.5"), Some(-2.5));
        assert_eq!(py_float("+.5"), Some(0.5));
        assert_eq!(py_float("1."), Some(1.0));
        assert_eq!(py_float("1e3"), Some(1000.0));
        assert_eq!(py_float("1E+3"), Some(1000.0));
        assert_eq!(py_float("1_000"), Some(1000.0));
        assert_eq!(py_float("1_0.2_5"), Some(10.25));
        assert_eq!(py_float(" 7 "), Some(7.0));
        assert_eq!(py_float("inf"), Some(f64::INFINITY));
        assert_eq!(py_float("-Infinity"), Some(f64::NEG_INFINITY));
        assert_eq!(py_float("INF"), Some(f64::INFINITY));
        assert!(py_float("NaN").is_some_and(f64::is_nan));
        for bad in [
            "", ".", "e5", "1e", "_1", "1_", "1__0", "1_.5", "0x10", "abc", "gpu0", "1,5",
            "\u{663}",
        ] {
            assert_eq!(py_float(bad), None, "{bad:?}");
        }
    }

    #[test]
    fn py_int_matches_python_on_the_usual_forms() {
        assert_eq!(py_int("0"), Some(0));
        assert_eq!(py_int("-3"), Some(-3));
        assert_eq!(py_int("+3"), Some(3));
        assert_eq!(py_int("007"), Some(7));
        assert_eq!(py_int("1_000"), Some(1000));
        assert_eq!(py_int(" 4 "), Some(4));
        for bad in [
            "", "-", "1.0", "1e3", "_1", "1_", "--1", "+-1", "0x1", "\u{663}",
        ] {
            assert_eq!(py_int(bad), None, "{bad:?}");
        }
        assert_eq!(py_int("99999999999999999999"), None);
    }
}
