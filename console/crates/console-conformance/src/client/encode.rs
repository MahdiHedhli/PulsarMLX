//! Request bodies written as Python's `json.dumps(value)` writes them with its defaults:
//! separators `", "` and `": "`, `ensure_ascii` (every character outside space to `~`
//! escaped as `\uXXXX`, lower-case hex, a surrogate pair above U+FFFF), integers as
//! written, and floats in Python's `repr` form (`100.0`, `1e-05`, `1e+16`).
//!
//! The donor's tests build their request bodies this way, so a scenario request sends the
//! same bytes the donor test sent.
//!
//! Behavior reference: project-maya serve/test_server.py:1446-1449 and 2386-2390 at
//! 7e68a30f (`json.dumps(body).encode()`).

use std::fmt::Write as _;

use serde_json::{Number, Value};

/// The deepest nesting written. Deeper values are refused.
pub const MAX_DEPTH: usize = 512;

/// Writes `value` as Python's `json.dumps(value)` does. Fails only past [`MAX_DEPTH`].
pub fn py_json_dumps(value: &Value) -> Result<String, String> {
    let mut out = String::new();
    write_value(&mut out, value, 0)?;
    Ok(out)
}

fn write_value(out: &mut String, value: &Value, depth: usize) -> Result<(), String> {
    if depth > MAX_DEPTH {
        return Err(format!("the body nests deeper than {MAX_DEPTH} levels"));
    }
    match value {
        Value::Null => out.push_str("null"),
        Value::Bool(true) => out.push_str("true"),
        Value::Bool(false) => out.push_str("false"),
        Value::Number(n) => out.push_str(&py_number(n)),
        Value::String(s) => write_string(out, s),
        Value::Array(items) => {
            out.push('[');
            for (i, item) in items.iter().enumerate() {
                if i > 0 {
                    out.push_str(", ");
                }
                write_value(out, item, depth + 1)?;
            }
            out.push(']');
        }
        Value::Object(map) => {
            out.push('{');
            for (i, (k, v)) in map.iter().enumerate() {
                if i > 0 {
                    out.push_str(", ");
                }
                write_string(out, k);
                out.push_str(": ");
                write_value(out, v, depth + 1)?;
            }
            out.push('}');
        }
    }
    Ok(())
}

fn write_string(out: &mut String, s: &str) {
    out.push('"');
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            '\u{8}' => out.push_str("\\b"),
            '\u{c}' => out.push_str("\\f"),
            ' '..='~' => out.push(c),
            _ => {
                let mut units = [0u16; 2];
                for unit in c.encode_utf16(&mut units) {
                    let _ = write!(out, "\\u{unit:04x}");
                }
            }
        }
    }
    out.push('"');
}

/// A JSON number as Python writes it after `json.loads`: an integer keeps its digits
/// (`-0` becomes `0`); a number with a fraction or an exponent becomes a float in
/// `repr` form.
pub fn py_number(n: &Number) -> String {
    let text = n.to_string();
    if !text.contains(['.', 'e', 'E']) {
        return if text == "-0" { "0".to_string() } else { text };
    }
    match text.parse::<f64>() {
        Ok(f) => py_float_repr(f),
        Err(_) => text,
    }
}

/// Python's `repr(float)`: the shortest digits that read back to the same value, in
/// fixed notation when the decimal exponent is from -4 to 15 and in scientific notation
/// (`1e-05`, `1.5e+16`) otherwise. Infinities and NaN are written as `json.dumps`
/// writes them.
pub fn py_float_repr(f: f64) -> String {
    if f.is_nan() {
        return "NaN".to_string();
    }
    if f.is_infinite() {
        return if f > 0.0 { "Infinity" } else { "-Infinity" }.to_string();
    }
    // `{:e}` gives the shortest round-trip digits, as `d.ddde<exp>`.
    let sci = format!("{:e}", f.abs());
    let (mantissa, exp) = sci.split_once('e').unwrap_or((sci.as_str(), "0"));
    let exp: i32 = exp.parse().unwrap_or(0);
    let digits: String = mantissa.chars().filter(char::is_ascii_digit).collect();
    let sign = if f.is_sign_negative() { "-" } else { "" };
    if !(-4..16).contains(&exp) {
        let (first, rest) = digits.split_at(1.min(digits.len()));
        let frac = if rest.is_empty() {
            String::new()
        } else {
            format!(".{rest}")
        };
        let esign = if exp < 0 { '-' } else { '+' };
        return format!("{sign}{first}{frac}e{esign}{:02}", exp.unsigned_abs());
    }
    if exp >= 0 {
        let int_len = usize::try_from(exp).unwrap_or(0) + 1;
        let mut int_part = digits.clone();
        let mut frac_part = String::new();
        if digits.len() > int_len {
            frac_part = digits[int_len..].to_string();
            int_part.truncate(int_len);
        } else {
            while int_part.len() < int_len {
                int_part.push('0');
            }
        }
        if frac_part.is_empty() {
            frac_part.push('0');
        }
        format!("{sign}{int_part}.{frac_part}")
    } else {
        let zeros = "0".repeat(usize::try_from(-exp - 1).unwrap_or(0));
        format!("{sign}0.{zeros}{digits}")
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn num(text: &str) -> String {
        let v: Value = serde_json::from_str(text).unwrap_or(Value::Null);
        match v {
            Value::Number(n) => py_number(&n),
            _ => String::from("not a number"),
        }
    }

    #[test]
    fn floats_follow_python_repr() {
        let cases = [
            ("0.1", "0.1"),
            ("1.5", "1.5"),
            ("1.50", "1.5"),
            ("100.0", "100.0"),
            ("1E2", "100.0"),
            ("1e15", "1000000000000000.0"),
            ("1e16", "1e+16"),
            ("1.5e16", "1.5e+16"),
            ("0.0001", "0.0001"),
            ("0.00001", "1e-05"),
            ("1.23e-7", "1.23e-07"),
            ("123456789012345678.0", "1.2345678901234568e+17"),
            ("2.5e+20", "2.5e+20"),
            ("0.30000000000000004", "0.30000000000000004"),
            ("0.0", "0.0"),
            ("-0.0", "-0.0"),
            ("-2.5", "-2.5"),
            ("1e400", "Infinity"),
            ("-1e400", "-Infinity"),
            ("1e-400", "0.0"),
            ("12345.678", "12345.678"),
            ("1e300", "1e+300"),
        ];
        for (input, want) in cases {
            assert_eq!(num(input), want, "{input}");
        }
    }

    #[test]
    fn integers_keep_their_digits() {
        assert_eq!(num("0"), "0");
        assert_eq!(num("-0"), "0");
        assert_eq!(num("-17"), "-17");
        assert_eq!(
            num("123456789012345678901234567890"),
            "123456789012345678901234567890"
        );
    }

    #[test]
    fn strings_are_escaped_as_ensure_ascii() {
        let v = json!("\u{e9}\u{2028}\u{1f600}\u{7f}\u{1}\"\\/\n\r\t\u{8}\u{c} ~");
        assert_eq!(
            py_json_dumps(&v).ok().as_deref(),
            Some("\"\\u00e9\\u2028\\ud83d\\ude00\\u007f\\u0001\\\"\\\\/\\n\\r\\t\\b\\f ~\"")
        );
    }

    #[test]
    fn containers_use_python_separators_and_key_order() {
        let v: Value = serde_json::from_str(
            r#"{"model": "m", "max_tokens": 8, "stream": true, "messages": [{"role": "user", "content": "hi"}], "e": [], "o": {}, "n": null, "f": false}"#,
        )
        .unwrap_or(Value::Null);
        assert_eq!(
            py_json_dumps(&v).ok().as_deref(),
            Some(
                "{\"model\": \"m\", \"max_tokens\": 8, \"stream\": true, \"messages\": [{\"role\": \"user\", \"content\": \"hi\"}], \"e\": [], \"o\": {}, \"n\": null, \"f\": false}"
            )
        );
    }

    #[test]
    fn nesting_past_the_limit_is_refused() {
        let mut v = json!(1);
        for _ in 0..=MAX_DEPTH {
            v = json!([v]);
        }
        assert!(py_json_dumps(&v).is_err());
    }
}
