//! Python's numeric coercion rules over JSON values: the `int` / `float` / `bool`
//! distinction, `float(str)`, `int(str)`, `int(float)`, `float(int)` and the two `re`
//! patterns the request checks use.
//!
//! A JSON number arrives as Python-normalized text (`console-pyjson`, with
//! `arbitrary_precision`), so an integer of any size is kept: [`PyInt`] holds it as decimal
//! digits, as Python holds an `int`. Character classes are Python 3.14's (Unicode 16.0.0):
//! whitespace is `str.isspace` ([`console_pyjson::pystr::is_space`]) for `str.strip()` and
//! the `re` class `\s`, but `float()` and `int()` do not strip the ASCII separators
//! U+001C..U+001F; a decimal digit is any character of category Nd, which `float()`,
//! `int()` and the `re` class `\d` all accept.
//!
//! Behavior reference: project-maya serve/server.py:506-521, 652-698, 6810-6854 and
//! 6899-6960 at 7e68a30f, which rely on CPython's `float()`, `int()` and `re` semantics.

use std::cmp::Ordering;
use std::fmt;

use console_pyjson::dumps::{classify_number, PyNumber};
use console_pyjson::loads::INT_MAX_STR_DIGITS;
use console_pyjson::pystr::is_space;
use serde_json::{Map, Number, Value};

use super::error::RequestError;
use super::pyrepr::repr_str;

/// The first code point of each run of ten Unicode decimal digits (category Nd, zero to
/// nine), recorded from CPython 3.14.7 (Unicode 16.0.0) with `python3 -I -c` and the
/// standard library only (`unicodedata.category(c) == 'Nd' and unicodedata.decimal(c) ==
/// 0`). Every Nd character lies in one such run.
#[rustfmt::skip]
const DECIMAL_ZEROS: &[u32] = &[
    0x30, 0x660, 0x6f0, 0x7c0, 0x966, 0x9e6, 0xa66, 0xae6, 0xb66, 0xbe6, 0xc66, 0xce6,
    0xd66, 0xde6, 0xe50, 0xed0, 0xf20, 0x1040, 0x1090, 0x17e0, 0x1810, 0x1946, 0x19d0,
    0x1a80, 0x1a90, 0x1b50, 0x1bb0, 0x1c40, 0x1c50, 0xa620, 0xa8d0, 0xa900, 0xa9d0, 0xa9f0,
    0xaa50, 0xabf0, 0xff10, 0x104a0, 0x10d30, 0x10d40, 0x11066, 0x110f0, 0x11136, 0x111d0,
    0x112f0, 0x11450, 0x114d0, 0x11650, 0x116c0, 0x116d0, 0x116da, 0x11730, 0x118e0,
    0x11950, 0x11bf0, 0x11c50, 0x11d50, 0x11da0, 0x11f50, 0x16130, 0x16a60, 0x16ac0,
    0x16b50, 0x16d70, 0x1ccf0, 0x1d7ce, 0x1d7d8, 0x1d7e2, 0x1d7ec, 0x1d7f6, 0x1e140,
    0x1e2f0, 0x1e4f0, 0x1e5f1, 0x1e950, 0x1fbf0,
];

/// The value of a Unicode decimal digit (category Nd), or `None` for any other character.
pub fn decimal_value(c: char) -> Option<u8> {
    let cp = c as u32;
    let idx = DECIMAL_ZEROS.partition_point(|&z| z <= cp);
    let zero = *DECIMAL_ZEROS.get(idx.checked_sub(1)?)?;
    let d = cp - zero;
    if d <= 9 {
        u8::try_from(d).ok()
    } else {
        None
    }
}

/// A Python `int` of any size: a sign and normalized decimal digits (no leading zeros;
/// zero is `0` and never negative).
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct PyInt {
    neg: bool,
    mag: String,
}

impl PyInt {
    /// Zero.
    pub fn zero() -> Self {
        PyInt {
            neg: false,
            mag: String::from("0"),
        }
    }

    /// From a machine integer.
    pub fn from_i64(v: i64) -> Self {
        PyInt {
            neg: v < 0,
            mag: v.unsigned_abs().to_string(),
        }
    }

    /// From decimal text: an optional `-` and ASCII digits (leading zeros allowed). `None`
    /// for any other text.
    pub fn from_decimal(text: &str) -> Option<Self> {
        let (neg, digits) = match text.strip_prefix('-') {
            Some(d) => (true, d),
            None => (false, text),
        };
        if digits.is_empty() || !digits.bytes().all(|b| b.is_ascii_digit()) {
            return None;
        }
        let trimmed = digits.trim_start_matches('0');
        let mag = if trimmed.is_empty() { "0" } else { trimmed };
        Some(PyInt {
            neg: neg && mag != "0",
            mag: mag.to_string(),
        })
    }

    /// True for zero.
    pub fn is_zero(&self) -> bool {
        self.mag == "0"
    }

    /// True below zero.
    pub fn is_negative(&self) -> bool {
        self.neg
    }

    /// The decimal digits of the magnitude.
    pub fn magnitude(&self) -> &str {
        &self.mag
    }

    /// The value as an `i64`, or `None` when it does not fit.
    pub fn to_i64(&self) -> Option<i64> {
        let m: u64 = self.mag.parse().ok()?;
        if self.neg {
            0i64.checked_sub_unsigned(m)
        } else {
            i64::try_from(m).ok()
        }
    }

    /// The value as a `u64`, or `None` when it is negative or does not fit.
    pub fn to_u64(&self) -> Option<u64> {
        if self.neg {
            None
        } else {
            self.mag.parse().ok()
        }
    }

    /// Compares with a machine integer, as Python compares two `int`s.
    pub fn cmp_i64(&self, other: i64) -> Ordering {
        self.cmp(&PyInt::from_i64(other))
    }

    /// Python `float(int)`: correctly rounded, or `OverflowError` "int too large to convert
    /// to float" when the value rounds beyond the largest finite double.
    pub fn to_f64(&self) -> Result<f64, RequestError> {
        let m: f64 = self.mag.parse().unwrap_or(f64::INFINITY);
        if m.is_infinite() {
            return Err(RequestError::Overflow(String::from(
                "int too large to convert to float",
            )));
        }
        Ok(if self.neg { -m } else { m })
    }

    /// The value as a JSON number holding a Python `int`.
    pub fn to_value(&self) -> Value {
        Value::Number(Number::from_string_unchecked(self.to_string()))
    }
}

impl Ord for PyInt {
    fn cmp(&self, other: &Self) -> Ordering {
        let by_mag = self
            .mag
            .len()
            .cmp(&other.mag.len())
            .then_with(|| self.mag.cmp(&other.mag));
        match (self.neg, other.neg) {
            (false, false) => by_mag,
            (true, true) => by_mag.reverse(),
            (true, false) => Ordering::Less,
            (false, true) => Ordering::Greater,
        }
    }
}

impl PartialOrd for PyInt {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

impl fmt::Display for PyInt {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        if self.neg {
            f.write_str("-")?;
        }
        f.write_str(&self.mag)
    }
}

/// A JSON value read with Python's types: `None`, `bool`, `int`, `float`, `str`, `list`
/// and `dict`.
#[derive(Debug, Clone, PartialEq)]
pub enum PyKind<'a> {
    /// `null`.
    None,
    /// `true` / `false`.
    Bool(bool),
    /// A number without fraction or exponent.
    Int(PyInt),
    /// A number with a fraction or an exponent, or a non-finite one.
    Float(f64),
    /// A string.
    Str(&'a str),
    /// An array.
    List(&'a [Value]),
    /// An object.
    Dict(&'a Map<String, Value>),
}

impl PyKind<'_> {
    /// Python's type name (`type(x).__name__`).
    pub fn type_name(&self) -> &'static str {
        match self {
            PyKind::None => "NoneType",
            PyKind::Bool(_) => "bool",
            PyKind::Int(_) => "int",
            PyKind::Float(_) => "float",
            PyKind::Str(_) => "str",
            PyKind::List(_) => "list",
            PyKind::Dict(_) => "dict",
        }
    }

    /// `isinstance(x, (int, float)) and not isinstance(x, bool)` as a float: `None` for
    /// anything else, an `OverflowError` for an `int` too large for a float.
    pub fn number_f64(&self) -> Option<Result<f64, RequestError>> {
        match self {
            PyKind::Int(i) => Some(i.to_f64()),
            PyKind::Float(f) => Some(Ok(*f)),
            _ => None,
        }
    }

    /// `float(x)` for `isinstance(x, (int, float))`, where a `bool` counts as an `int`:
    /// `None` for anything else.
    pub fn int_or_float_f64(&self) -> Option<Result<f64, RequestError>> {
        match self {
            PyKind::Bool(b) => Some(Ok(if *b { 1.0 } else { 0.0 })),
            other => other.number_f64(),
        }
    }
}

/// Reads a JSON value with Python's types.
///
/// A number text that `console-pyjson` cannot classify (which no parsed body produces) is
/// read as the float `serde_json` gives it, or NaN.
pub fn kind(v: &Value) -> PyKind<'_> {
    match v {
        Value::Null => PyKind::None,
        Value::Bool(b) => PyKind::Bool(*b),
        Value::Number(n) => match classify_number(n) {
            Ok(PyNumber::Int(digits)) => match PyInt::from_decimal(&digits) {
                Some(i) => PyKind::Int(i),
                None => PyKind::Float(n.as_f64().unwrap_or(f64::NAN)),
            },
            Ok(PyNumber::Float(f)) => PyKind::Float(f),
            Err(_) => PyKind::Float(n.as_f64().unwrap_or(f64::NAN)),
        },
        Value::String(s) => PyKind::Str(s),
        Value::Array(a) => PyKind::List(a),
        Value::Object(o) => PyKind::Dict(o),
    }
}

/// The characters `float(str)` and `int(str)` strip around a number. CPython first turns
/// only non-ASCII whitespace into a space and leaves every ASCII character as it is, then
/// strips with `Py_ISSPACE` (space, `\t`, `\n`, `\v`, `\f`, `\r`). The ASCII separators
/// U+001C..U+001F, which `str.isspace()` accepts, are therefore not stripped and make the
/// text invalid.
fn is_number_space(c: char) -> bool {
    if c.is_ascii() {
        matches!(c, ' ' | '\t' | '\n' | '\u{b}' | '\u{c}' | '\r')
    } else {
        is_space(c)
    }
}

/// Strips the whitespace CPython strips ([`is_number_space`]) and maps every Unicode
/// decimal digit to its ASCII digit, as CPython does before parsing a number from a `str`.
/// `None` when another non-ASCII character remains.
fn ascii_number_text(s: &str) -> Option<String> {
    let t = s.trim_matches(is_number_space);
    let mut out = String::with_capacity(t.len());
    for c in t.chars() {
        if c.is_ascii() {
            out.push(c);
        } else {
            let d = decimal_value(c)?;
            out.push(char::from(b'0' + d));
        }
    }
    Some(out)
}

/// A run of ASCII digits with single underscores between digits (PEP 515), as `float()`
/// and `int()` accept it. Returns the digits without underscores.
fn digit_part(s: &str) -> Option<String> {
    if s.is_empty() || s.starts_with('_') || s.ends_with('_') || s.contains("__") {
        return None;
    }
    if !s.bytes().all(|b| b.is_ascii_digit() || b == b'_') {
        return None;
    }
    Some(s.replace('_', ""))
}

/// Python `float(s)` for a `str`: surrounding whitespace, a sign, `inf`, `infinity` and
/// `nan` in any case, Unicode decimal digits and single underscores between digits are
/// accepted. `None` where Python raises `ValueError`.
pub fn py_float_str(s: &str) -> Option<f64> {
    let t = ascii_number_text(s)?;
    let (neg, body) = match t.as_bytes().first() {
        Some(b'-') => (true, t.get(1..)?),
        Some(b'+') => (false, t.get(1..)?),
        _ => (false, t.as_str()),
    };
    let lower = body.to_ascii_lowercase();
    let special = match lower.as_str() {
        "inf" | "infinity" => Some(f64::INFINITY),
        "nan" => Some(f64::NAN),
        _ => None,
    };
    if let Some(v) = special {
        return Some(if neg { -v } else { v });
    }
    let (mantissa, exponent) = match body.find(['e', 'E']) {
        Some(i) => (body.get(..i)?, Some(body.get(i + 1..)?)),
        None => (body, None),
    };
    let (int_part, frac_part) = match mantissa.find('.') {
        Some(i) => (mantissa.get(..i)?, Some(mantissa.get(i + 1..)?)),
        None => (mantissa, None),
    };
    let int_digits = if int_part.is_empty() {
        String::new()
    } else {
        digit_part(int_part)?
    };
    let frac_digits = match frac_part {
        Some(f) if !f.is_empty() => digit_part(f)?,
        _ => String::new(),
    };
    if int_digits.is_empty() && frac_digits.is_empty() {
        return None;
    }
    let mut text = String::new();
    if neg {
        text.push('-');
    }
    text.push_str(if int_digits.is_empty() {
        "0"
    } else {
        &int_digits
    });
    if !frac_digits.is_empty() {
        text.push('.');
        text.push_str(&frac_digits);
    }
    if let Some(e) = exponent {
        let (esign, edigits) = match e.as_bytes().first() {
            Some(b'-') => ("-", e.get(1..)?),
            Some(b'+') => ("", e.get(1..)?),
            _ => ("", e),
        };
        let edigits = digit_part(edigits)?;
        text.push('e');
        text.push_str(esign);
        text.push_str(&edigits);
    }
    text.parse::<f64>().ok()
}

/// The message of Python's `int()` for a literal it cannot read: the `repr` of the text,
/// cut to 200 characters as CPython's `%.200R` does.
fn invalid_int_literal(s: &str) -> RequestError {
    let shown: String = repr_str(s).chars().take(200).collect();
    RequestError::invalid(format!("invalid literal for int() with base 10: {shown}"))
}

/// Python `int(s)` for a `str` in base 10: surrounding whitespace, a sign, Unicode
/// decimal digits and single underscores between digits. A literal with more than 4300
/// digits raises Python's limit message.
pub fn py_int_str(s: &str) -> Result<PyInt, RequestError> {
    let Some(t) = ascii_number_text(s) else {
        return Err(invalid_int_literal(s));
    };
    let (neg, body) = match t.as_bytes().first() {
        Some(b'-') => (true, t.get(1..).unwrap_or("")),
        Some(b'+') => (false, t.get(1..).unwrap_or("")),
        _ => (false, t.as_str()),
    };
    let Some(digits) = digit_part(body) else {
        return Err(invalid_int_literal(s));
    };
    if digits.len() > INT_MAX_STR_DIGITS {
        return Err(RequestError::invalid(format!(
            "Exceeds the limit ({INT_MAX_STR_DIGITS} digits) for integer string conversion: \
             value has {} digits; use sys.set_int_max_str_digits() to increase the limit",
            digits.len()
        )));
    }
    let text = if neg { format!("-{digits}") } else { digits };
    PyInt::from_decimal(&text).ok_or_else(|| invalid_int_literal(s))
}

/// Python `int(x)` for a float: truncation toward zero, exact for every finite double.
/// NaN raises `ValueError` and an infinity `OverflowError`, with Python's messages.
pub fn py_int_of_float(x: f64) -> Result<PyInt, RequestError> {
    if x.is_nan() {
        return Err(RequestError::invalid("cannot convert float NaN to integer"));
    }
    if x.is_infinite() {
        return Err(RequestError::Overflow(String::from(
            "cannot convert float infinity to integer",
        )));
    }
    let t = x.trunc();
    let neg = t < 0.0;
    let a = t.abs();
    let mag = if a < 9_007_199_254_740_992.0 {
        // Below 2^53 every integral double converts exactly.
        format!("{a:.0}")
    } else {
        let bits = a.to_bits();
        let exp_bits = i64::try_from((bits >> 52) & 0x7ff).unwrap_or(0);
        let mantissa = (bits & ((1u64 << 52) - 1)) | (1u64 << 52);
        let shift = exp_bits - 1075;
        exact_decimal(mantissa, u32::try_from(shift.max(0)).unwrap_or(0))
    };
    let text = if neg { format!("-{mag}") } else { mag };
    PyInt::from_decimal(&text).ok_or_else(|| RequestError::invalid("cannot convert float"))
}

/// `mantissa * 2^shift` in decimal (`shift` is at most 971 for a double).
fn exact_decimal(mantissa: u64, shift: u32) -> String {
    const BASE: u64 = 1_000_000_000;
    let mut limbs: Vec<u64> = Vec::new();
    let mut m = mantissa;
    while m > 0 {
        limbs.push(m % BASE);
        m /= BASE;
    }
    for _ in 0..shift {
        let mut carry = 0u64;
        for limb in limbs.iter_mut() {
            let v = *limb * 2 + carry;
            *limb = v % BASE;
            carry = v / BASE;
        }
        if carry > 0 {
            limbs.push(carry);
        }
    }
    let mut out = String::new();
    for (i, limb) in limbs.iter().rev().enumerate() {
        if i == 0 {
            out.push_str(&limb.to_string());
        } else {
            out.push_str(&format!("{limb:09}"));
        }
    }
    if out.is_empty() {
        out.push('0');
    }
    out
}

/// Python `int(x)` for a JSON value: a `bool` is 0 or 1, an `int` itself, a `float`
/// truncated, a `str` read in base 10; a `list`, `dict` or `None` raises `TypeError`.
pub fn py_int(v: &Value) -> Result<PyInt, RequestError> {
    match kind(v) {
        PyKind::Bool(b) => Ok(PyInt::from_i64(i64::from(b))),
        PyKind::Int(i) => Ok(i),
        PyKind::Float(f) => py_int_of_float(f),
        PyKind::Str(s) => py_int_str(s),
        other => Err(RequestError::type_error(format!(
            "int() argument must be a string, a bytes-like object or a real number, not '{}'",
            other.type_name()
        ))),
    }
}

/// `re.fullmatch(r"\s*[+-]?\d+\s*", s)` with Python's Unicode `\s` and `\d`.
pub fn matches_signed_digits(s: &str) -> bool {
    let t = s.trim_matches(is_space);
    let body = t.strip_prefix(['+', '-']).unwrap_or(t);
    !body.is_empty() && body.chars().all(|c| decimal_value(c).is_some())
}

/// `re.fullmatch(r"\s*\d+\s*", s)` with Python's Unicode `\s` and `\d`.
pub fn matches_digits(s: &str) -> bool {
    let t = s.trim_matches(is_space);
    !t.is_empty() && t.chars().all(|c| decimal_value(c).is_some())
}

/// A JSON number holding a Python `float`, written as Python's `json.dumps` would.
pub fn float_json(x: f64) -> Value {
    console_pyjson::dumps::float_value(x)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn decimal_digits_follow_category_nd() {
        assert_eq!(decimal_value('7'), Some(7));
        assert_eq!(decimal_value('\u{663}'), Some(3));
        assert_eq!(decimal_value('\u{ff15}'), Some(5));
        assert_eq!(decimal_value('\u{1d7ff}'), Some(9));
        assert_eq!(decimal_value('\u{b2}'), None); // superscript two: a digit, not decimal
        assert_eq!(decimal_value('a'), None);
        assert_eq!(decimal_value('/'), None);
    }

    // Expected values recorded from CPython 3.14.7 with `python3 -I -c 'float(s)'`.
    #[test]
    fn float_of_str_matches_python() {
        let ok: &[(&str, f64)] = &[
            ("1_0.5", 10.5),
            ("1e1_0", 1e10),
            (".5", 0.5),
            ("5.", 5.0),
            ("+inf", f64::INFINITY),
            ("-Infinity", f64::NEG_INFINITY),
            (" \u{3000} \u{663}.5 ", 3.5),
            ("1.5e+3", 1500.0),
            ("\u{663}_\u{664}", 34.0),
            (" 12 ", 12.0),
            ("1e400", f64::INFINITY),
            ("-0", -0.0),
            ("1e-400", 0.0),
        ];
        for (s, want) in ok {
            assert_eq!(py_float_str(s), Some(*want), "{s:?}");
        }
        assert!(py_float_str("nAn").is_some_and(f64::is_nan));
        for bad in [
            "1__0", "_1", "1_", "1_.5", "1e", "e5", "0x10", "1 2", "\u{b2}", "", " ", ".", "warm",
            "+-1", "1e+", "in f", "1._5",
        ] {
            assert_eq!(py_float_str(bad), None, "{bad:?}");
        }
        // The ASCII separators U+001C..U+001F are `str.isspace()` but not stripped by
        // `float()`; non-ASCII whitespace (U+0085, U+00A0, U+3000) is.
        for bad in [
            "5\u{1c}",
            "\u{1f}5",
            "\u{1d}5\u{1e}",
            "5\u{1c}\u{3000}",
            "5\u{3000}\u{1c}",
        ] {
            assert_eq!(py_float_str(bad), None, "{bad:?}");
        }
        for s in ["5\u{85}", "5\u{a0}", "\u{3000}5", "\t5\u{b}\u{c}\r\n"] {
            assert_eq!(py_float_str(s), Some(5.0), "{s:?}");
        }
    }

    // Expected values and messages recorded from CPython 3.14.7 (`int(s)`).
    #[test]
    fn int_of_str_matches_python() {
        for (s, want) in [
            (" 07 ", "7"),
            ("+5", "5"),
            ("-0", "0"),
            ("1_000", "1000"),
            ("\u{663}", "3"),
        ] {
            assert_eq!(
                py_int_str(s).map(|i| i.to_string()),
                Ok(want.to_string()),
                "{s:?}"
            );
        }
        assert_eq!(
            py_int_str("1__0"),
            Err(RequestError::invalid(
                "invalid literal for int() with base 10: '1__0'"
            ))
        );
        assert_eq!(
            py_int_str("5\u{1c}"),
            Err(RequestError::invalid(
                "invalid literal for int() with base 10: '5\\x1c'"
            ))
        );
        assert_eq!(
            py_int_str("\u{1f}5"),
            Err(RequestError::invalid(
                "invalid literal for int() with base 10: '\\x1f5'"
            ))
        );
        assert_eq!(py_int_str("5\u{85}").map(|i| i.to_string()), Ok("5".into()));
        assert_eq!(
            py_int_str(""),
            Err(RequestError::invalid(
                "invalid literal for int() with base 10: ''"
            ))
        );
        let long = "x".repeat(5000);
        let msg = py_int_str(&long).unwrap_err().message().to_string();
        assert_eq!(msg.chars().count(), 240);
        let limit = format!("{}_1", "1".repeat(4300));
        assert_eq!(
            py_int_str(&limit).unwrap_err().message(),
            "Exceeds the limit (4300 digits) for integer string conversion: value has 4301 \
             digits; use sys.set_int_max_str_digits() to increase the limit"
        );
        assert!(py_int_str(&"1".repeat(4300)).is_ok());
        assert!(py_int_str(&format!("-{}", "1".repeat(4300))).is_ok());
        // An invalid literal is reported as such before the digit limit.
        let both = format!("{}x", "1".repeat(4301));
        assert!(py_int_str(&both)
            .unwrap_err()
            .message()
            .starts_with("invalid literal"));
    }

    #[test]
    fn int_of_float_is_exact_and_raises_like_python() {
        assert_eq!(
            py_int_of_float(40.9).map(|i| i.to_string()),
            Ok("40".into())
        );
        assert_eq!(
            py_int_of_float(-2.5).map(|i| i.to_string()),
            Ok("-2".into())
        );
        assert_eq!(py_int_of_float(-0.5).map(|i| i.to_string()), Ok("0".into()));
        assert_eq!(
            py_int_of_float(1e30).map(|i| i.to_string()),
            Ok("1000000000000000019884624838656".into())
        );
        assert_eq!(
            py_int_of_float(f64::MAX).map(|i| i.magnitude().len()),
            Ok(309)
        );
        assert_eq!(
            py_int_of_float(f64::NAN),
            Err(RequestError::invalid("cannot convert float NaN to integer"))
        );
        assert_eq!(
            py_int_of_float(f64::NEG_INFINITY),
            Err(RequestError::Overflow(
                "cannot convert float infinity to integer".into()
            ))
        );
    }

    #[test]
    fn py_int_of_values() {
        assert_eq!(py_int(&Value::Bool(true)), Ok(PyInt::from_i64(1)));
        assert_eq!(
            py_int(&serde_json::json!([1])),
            Err(RequestError::type_error(
                "int() argument must be a string, a bytes-like object or a real number, not 'list'"
            ))
        );
        assert_eq!(
            py_int(&serde_json::json!({})).unwrap_err().message(),
            "int() argument must be a string, a bytes-like object or a real number, not 'dict'"
        );
        assert_eq!(
            py_int(&Value::String("abc".into())).unwrap_err().message(),
            "invalid literal for int() with base 10: 'abc'"
        );
    }

    #[test]
    fn big_ints_compare_and_convert() {
        let big = PyInt::from_decimal(&format!("1{}", "0".repeat(400))).unwrap();
        assert_eq!(big.cmp_i64(i64::MAX), Ordering::Greater);
        assert_eq!(big.to_i64(), None);
        assert_eq!(
            big.to_f64(),
            Err(RequestError::Overflow(
                "int too large to convert to float".into()
            ))
        );
        let neg = PyInt::from_decimal("-0005").unwrap();
        assert_eq!(neg.to_string(), "-5");
        assert_eq!(neg.cmp_i64(-1), Ordering::Less);
        assert_eq!(neg.cmp_i64(-5), Ordering::Equal);
        assert_eq!(PyInt::from_decimal("-0").unwrap(), PyInt::zero());
        assert_eq!(PyInt::from_i64(i64::MIN).to_i64(), Some(i64::MIN));
        assert_eq!(PyInt::from_decimal("12a"), None);
        assert_eq!(PyInt::from_i64(-3).to_u64(), None);
        assert_eq!(PyInt::from_i64(3).to_value().to_string(), "3");
    }

    #[test]
    fn digit_patterns_follow_python_re() {
        assert!(matches_signed_digits(" +12 "));
        assert!(matches_signed_digits("\u{663}"));
        assert!(!matches_signed_digits("1.0"));
        assert!(!matches_signed_digits("+"));
        assert!(!matches_signed_digits("1_0"));
        assert!(matches_digits(" 5\u{1c}"));
        assert!(!matches_digits("-5"));
        assert!(!matches_digits(""));
    }

    #[test]
    fn kinds_follow_python_types() {
        let v: Value =
            console_pyjson::loads::loads(r#"[null, true, 3, 3.0, "s", [], {}]"#).unwrap();
        let names: Vec<_> = v
            .as_array()
            .unwrap()
            .iter()
            .map(|x| kind(x).type_name())
            .collect();
        assert_eq!(
            names,
            ["NoneType", "bool", "int", "float", "str", "list", "dict"]
        );
        assert_eq!(kind(&Value::Bool(true)).number_f64(), None);
        assert_eq!(kind(&Value::Bool(true)).int_or_float_f64(), Some(Ok(1.0)));
    }
}
