//! Owned by API-01. Python `json.dumps` output, byte for byte, for every wire body and
//! persisted file.
//!
//! [`dumps`] reproduces CPython's `json.dumps(obj, ensure_ascii=..., indent=...,
//! separators=..., sort_keys=..., allow_nan=...)` for a [`serde_json::Value`]:
//!
//! - Separators default to `", "` and `": "`, or `","` and `": "` when `indent` is set.
//! - Keys keep insertion order (the workspace enables `preserve_order`) unless `sort_keys`,
//!   which orders them by code point.
//! - `ensure_ascii=True` escapes every character outside printable ASCII (including DEL) as
//!   `\uXXXX` in lower-case hex, astral characters as a surrogate pair; with
//!   `ensure_ascii=False` only `"`, `\` and the C0 controls are escaped. The short escapes are
//!   `\" \\ \n \r \t \b \f`. There is no HTML escaping.
//! - Floats are written as Python `repr` ([`crate::float_repr`]), integers exactly, and the
//!   non-finite floats as `NaN`, `Infinity` and `-Infinity` (or a `ValueError` with
//!   `allow_nan=False`).
//! - With `indent`, each item goes on its own line indented by the indent string times the
//!   level; empty containers stay `[]` and `{}`.
//!
//! The donor uses four modes, each with a preset: [`DumpsOptions::wire`] for HTTP bodies
//! (`ensure_ascii=False`), [`DumpsOptions::python_default`] for bodies written with a bare
//! `json.dumps(obj)`, [`DumpsOptions::file`] for persisted files (`indent=1`) and
//! [`DumpsOptions::canonical`] for the Responses store encoding.
//!
//! Behavior reference: project-maya serve/server.py:5457-5463 (`_json`), 2577, 2818, 2863,
//! 2918 (`indent=1` rewrites), 6260 (bare `json.dumps`), serve/models.py:662-700 (run-config
//! write), serve/response_store.py:10-11 (`encoded`), serve/loop_guard.py:314-326
//! (`sort_keys`), serve/response_schema.py:14-21 and serve/frontend.py:45 (`tojson`) at
//! 7e68a30f.

use std::fmt;

use serde_json::{Number, Value};

use crate::float_repr::{json_float, repr_f64};
use crate::loads::{INT_MAX_STR_DIGITS, MAX_DEPTH};

/// The `indent` argument of `json.dumps`: an integer is that many spaces (a negative Python
/// integer is the same as zero), a string is used as given.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Indent {
    /// `indent=n`.
    Spaces(usize),
    /// `indent="..."`.
    Text(String),
}

impl Indent {
    fn unit(&self) -> String {
        match self {
            Indent::Spaces(n) => " ".repeat(*n),
            Indent::Text(t) => t.clone(),
        }
    }
}

/// The keyword arguments of Python's `json.dumps` that the donor uses. `Default` is Python's
/// default: `ensure_ascii=True`, `indent=None`, `separators=None`, `sort_keys=False`,
/// `allow_nan=True`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DumpsOptions {
    /// `ensure_ascii`.
    pub ensure_ascii: bool,
    /// `indent`; `None` is the compact single-line form.
    pub indent: Option<Indent>,
    /// `separators=(item_separator, key_separator)`; `None` picks Python's default for the
    /// `indent` setting.
    pub separators: Option<(String, String)>,
    /// `sort_keys`.
    pub sort_keys: bool,
    /// `allow_nan`.
    pub allow_nan: bool,
}

impl Default for DumpsOptions {
    fn default() -> Self {
        DumpsOptions {
            ensure_ascii: true,
            indent: None,
            separators: None,
            sort_keys: false,
            allow_nan: true,
        }
    }
}

impl DumpsOptions {
    /// `json.dumps(obj)`.
    pub fn python_default() -> Self {
        Self::default()
    }

    /// `json.dumps(obj, ensure_ascii=False)`: every JSON body the HTTP layer writes (`_json`).
    pub fn wire() -> Self {
        DumpsOptions {
            ensure_ascii: false,
            ..Self::default()
        }
    }

    /// `json.dumps(obj, indent=1)`: every persisted file (run configs, shared settings).
    pub fn file() -> Self {
        DumpsOptions {
            indent: Some(Indent::Spaces(1)),
            ..Self::default()
        }
    }

    /// `json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    /// allow_nan=False)`: the Responses store encoding.
    pub fn canonical() -> Self {
        DumpsOptions {
            ensure_ascii: false,
            indent: None,
            separators: Some((String::from(","), String::from(":"))),
            sort_keys: true,
            allow_nan: false,
        }
    }

    /// Sets `ensure_ascii`.
    pub fn ensure_ascii(mut self, on: bool) -> Self {
        self.ensure_ascii = on;
        self
    }

    /// Sets `indent`.
    pub fn indent(mut self, indent: Option<Indent>) -> Self {
        self.indent = indent;
        self
    }

    /// Sets `separators`.
    pub fn separators(mut self, item: &str, key: &str) -> Self {
        self.separators = Some((item.to_string(), key.to_string()));
        self
    }

    /// Sets `sort_keys`.
    pub fn sort_keys(mut self, on: bool) -> Self {
        self.sort_keys = on;
        self
    }

    /// Sets `allow_nan`.
    pub fn allow_nan(mut self, on: bool) -> Self {
        self.allow_nan = on;
        self
    }
}

/// Why a value could not be written. Each case is a Python `ValueError` (or `RecursionError`)
/// with Python's message as `Display`.
#[derive(Debug, Clone, PartialEq)]
pub enum DumpsError {
    /// A non-finite float with `allow_nan=False`; holds the float.
    OutOfRangeFloat(f64),
    /// An integer of more than [`INT_MAX_STR_DIGITS`] digits.
    IntTooLong,
    /// A `serde_json::Number` whose text is neither a Python int nor a float. It cannot come
    /// from [`crate::loads`] or from `serde_json`'s own constructors.
    InvalidNumber(String),
    /// Nesting deeper than [`MAX_DEPTH`].
    TooDeep,
}

impl DumpsError {
    /// The Python exception class: `ValueError` or `RecursionError`.
    pub fn python_type(&self) -> &'static str {
        match self {
            DumpsError::TooDeep => "RecursionError",
            _ => "ValueError",
        }
    }
}

impl fmt::Display for DumpsError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            DumpsError::OutOfRangeFloat(x) => write!(
                f,
                "Out of range float values are not JSON compliant: {}",
                repr_f64(*x)
            ),
            DumpsError::IntTooLong => write!(
                f,
                "Exceeds the limit ({INT_MAX_STR_DIGITS} digits) for integer string conversion; \
                 use sys.set_int_max_str_digits() to increase the limit"
            ),
            DumpsError::InvalidNumber(text) => write!(f, "not a Python number: {text:?}"),
            DumpsError::TooDeep => {
                f.write_str("maximum recursion depth exceeded while encoding a JSON object")
            }
        }
    }
}

impl std::error::Error for DumpsError {}

/// A JSON number read with Python's `int` / `float` distinction.
#[derive(Debug, Clone, PartialEq)]
pub enum PyNumber {
    /// A Python `int`, as normalized decimal digits (`-0` is `0`, no leading zeros).
    Int(String),
    /// A Python `float`.
    Float(f64),
}

/// Reads a number the way Python's `json.loads` would have typed it: text with a fraction or
/// an exponent is a `float`, `NaN`, `Infinity` and `-Infinity` are the non-finite floats, and
/// anything else is an `int`.
///
/// This normalizes the number text that `arbitrary_precision` keeps, whatever produced it
/// (this crate's parser, `serde_json`'s parser, or `serde_json`'s `From<f64>`, which writes
/// `1e16` for `1e16`).
pub fn classify_number(n: &Number) -> Result<PyNumber, DumpsError> {
    let text = n.as_str();
    match text {
        "NaN" => return Ok(PyNumber::Float(f64::NAN)),
        "Infinity" => return Ok(PyNumber::Float(f64::INFINITY)),
        "-Infinity" => return Ok(PyNumber::Float(f64::NEG_INFINITY)),
        _ => {}
    }
    let (neg, digits) = match text.strip_prefix('-') {
        Some(d) => (true, d),
        None => (false, text),
    };
    if !digits.is_empty() && digits.bytes().all(|c| c.is_ascii_digit()) {
        let trimmed = digits.trim_start_matches('0');
        let magnitude = if trimmed.is_empty() { "0" } else { trimmed };
        return Ok(PyNumber::Int(if neg && magnitude != "0" {
            format!("-{magnitude}")
        } else {
            magnitude.to_string()
        }));
    }
    let json_float_shape = !digits.is_empty()
        && digits.bytes().next().is_some_and(|c| c.is_ascii_digit())
        && digits
            .bytes()
            .all(|c| c.is_ascii_digit() || matches!(c, b'.' | b'e' | b'E' | b'+' | b'-'));
    if json_float_shape {
        if let Ok(f) = text.parse::<f64>() {
            return Ok(PyNumber::Float(f));
        }
    }
    Err(DumpsError::InvalidNumber(text.to_string()))
}

/// A `serde_json::Value` holding a Python float, with its number text in Python's form
/// (`repr` for a finite value; `NaN`, `Infinity` or `-Infinity` otherwise). Unlike
/// `serde_json::Value::from(f64)` this keeps the non-finite values instead of mapping them to
/// `null`.
///
/// It stores the text with `serde_json`'s hidden `Number::from_string_unchecked`, as
/// [`crate::loads`] does; see the note there on the exact version pin.
pub fn float_value(x: f64) -> Value {
    Value::Number(Number::from_string_unchecked(json_float(x)))
}

/// A `serde_json::Value` holding a Python int given as decimal text (an optional `-` and at
/// least one ASCII digit). `None` for any other text or for more than
/// [`INT_MAX_STR_DIGITS`] digits.
pub fn int_value(text: &str) -> Option<Value> {
    let digits = text.strip_prefix('-').unwrap_or(text);
    if digits.is_empty()
        || digits.len() > INT_MAX_STR_DIGITS
        || !digits.bytes().all(|c| c.is_ascii_digit())
    {
        return None;
    }
    match classify_number(&Number::from_string_unchecked(text.to_string())) {
        Ok(PyNumber::Int(n)) => Some(Value::Number(Number::from_string_unchecked(n))),
        _ => None,
    }
}

/// Python's JSON string literal for `s`, quotes included: `json.dumps(s,
/// ensure_ascii=ensure_ascii)` for a `str`.
pub fn dumps_str(s: &str, ensure_ascii: bool) -> String {
    let mut out = String::with_capacity(s.len() + 2);
    write_str(&mut out, s, ensure_ascii);
    out
}

fn push_u_escape(out: &mut String, unit: u32) {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    out.push_str("\\u");
    for shift in [12u32, 8, 4, 0] {
        let nibble = ((unit >> shift) & 0xf) as usize;
        out.push(char::from(HEX.get(nibble).copied().unwrap_or(b'0')));
    }
}

fn write_str(out: &mut String, s: &str, ensure_ascii: bool) {
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
            c if (c as u32) < 0x20 => push_u_escape(out, c as u32),
            c if ensure_ascii && (c as u32) >= 0x7f => {
                let cp = c as u32;
                if cp >= 0x10000 {
                    let v = cp - 0x10000;
                    push_u_escape(out, 0xd800 | (v >> 10));
                    push_u_escape(out, 0xdc00 | (v & 0x3ff));
                } else {
                    push_u_escape(out, cp);
                }
            }
            c => out.push(c),
        }
    }
    out.push('"');
}

struct Writer<'a> {
    opts: &'a DumpsOptions,
    item_sep: &'a str,
    key_sep: &'a str,
    indent_unit: Option<String>,
    out: String,
}

impl Writer<'_> {
    fn newline(&mut self, level: usize) {
        if let Some(unit) = &self.indent_unit {
            self.out.push('\n');
            for _ in 0..level {
                self.out.push_str(unit);
            }
        }
    }

    fn number(&mut self, n: &Number) -> Result<(), DumpsError> {
        match classify_number(n)? {
            PyNumber::Int(digits) => {
                let count = digits.strip_prefix('-').unwrap_or(&digits).len();
                if count > INT_MAX_STR_DIGITS {
                    return Err(DumpsError::IntTooLong);
                }
                self.out.push_str(&digits);
            }
            PyNumber::Float(x) => {
                if !x.is_finite() && !self.opts.allow_nan {
                    return Err(DumpsError::OutOfRangeFloat(x));
                }
                self.out.push_str(&json_float(x));
            }
        }
        Ok(())
    }

    /// Writes one scalar, or opens a container and returns its frame.
    fn open<'v>(&mut self, v: &'v Value, depth: usize) -> Result<Option<Frame<'v>>, DumpsError> {
        match v {
            Value::Null => self.out.push_str("null"),
            Value::Bool(true) => self.out.push_str("true"),
            Value::Bool(false) => self.out.push_str("false"),
            Value::Number(n) => self.number(n)?,
            Value::String(s) => write_str(&mut self.out, s, self.opts.ensure_ascii),
            Value::Array(items) => {
                if depth >= MAX_DEPTH {
                    return Err(DumpsError::TooDeep);
                }
                if items.is_empty() {
                    self.out.push_str("[]");
                } else {
                    self.out.push('[');
                    return Ok(Some(Frame::Array(items.iter(), true)));
                }
            }
            Value::Object(map) => {
                if depth >= MAX_DEPTH {
                    return Err(DumpsError::TooDeep);
                }
                if map.is_empty() {
                    self.out.push_str("{}");
                } else {
                    let mut entries: Vec<(&'v String, &'v Value)> = map.iter().collect();
                    if self.opts.sort_keys {
                        entries.sort_by(|a, b| a.0.cmp(b.0));
                    }
                    self.out.push('{');
                    return Ok(Some(Frame::Object(entries.into_iter(), true)));
                }
            }
        }
        Ok(None)
    }

    /// Writes `v` with an explicit stack of open containers (Python's encoder recurses; the
    /// output is the same, and the depth costs heap, not stack).
    fn value(&mut self, v: &Value) -> Result<(), DumpsError> {
        let mut stack: Vec<Frame<'_>> = Vec::new();
        let mut current = v;
        loop {
            if let Some(frame) = self.open(current, stack.len())? {
                stack.push(frame);
            }
            // Find the next value to write, closing finished containers.
            loop {
                let level = stack.len();
                let Some(frame) = stack.last_mut() else {
                    return Ok(());
                };
                let next = match frame {
                    Frame::Array(items, first) => items.next().map(|item| (None, item, first)),
                    Frame::Object(entries, first) => {
                        entries.next().map(|(key, item)| (Some(key), item, first))
                    }
                };
                match next {
                    Some((key, item, first)) => {
                        if !*first {
                            self.out.push_str(self.item_sep);
                        }
                        *first = false;
                        self.newline(level);
                        if let Some(key) = key {
                            write_str(&mut self.out, key, self.opts.ensure_ascii);
                            self.out.push_str(self.key_sep);
                        }
                        current = item;
                        break;
                    }
                    None => {
                        let closer = match stack.pop() {
                            Some(Frame::Object(..)) => '}',
                            _ => ']',
                        };
                        self.newline(stack.len());
                        self.out.push(closer);
                    }
                }
            }
        }
    }
}

/// An open container of the writer and whether its first member is still to come.
enum Frame<'v> {
    Array(std::slice::Iter<'v, Value>, bool),
    Object(std::vec::IntoIter<(&'v String, &'v Value)>, bool),
}

/// Python `json.dumps(value, **opts)`.
///
/// ```
/// use console_pyjson::dumps::{dumps, DumpsOptions};
/// let v = console_pyjson::loads::loads(r#"{"a": [1, 2.50, "é"], "b": {}}"#).unwrap();
/// assert_eq!(dumps(&v, &DumpsOptions::wire()).unwrap(), r#"{"a": [1, 2.5, "é"], "b": {}}"#);
/// assert_eq!(
///     dumps(&v, &DumpsOptions::file()).unwrap(),
///     "{\n \"a\": [\n  1,\n  2.5,\n  \"\\u00e9\"\n ],\n \"b\": {}\n}"
/// );
/// ```
pub fn dumps(value: &Value, opts: &DumpsOptions) -> Result<String, DumpsError> {
    let (item_sep, key_sep) = match (&opts.separators, &opts.indent) {
        (Some((item, key)), _) => (item.as_str(), key.as_str()),
        (None, Some(_)) => (",", ": "),
        (None, None) => (", ", ": "),
    };
    let mut writer = Writer {
        opts,
        item_sep,
        key_sep,
        indent_unit: opts.indent.as_ref().map(Indent::unit),
        out: String::new(),
    };
    writer.value(value)?;
    Ok(writer.out)
}

/// `json.dumps(value, ensure_ascii=False)`: the body of every JSON response.
pub fn to_wire(value: &Value) -> Result<String, DumpsError> {
    dumps(value, &DumpsOptions::wire())
}

/// `json.dumps(value, indent=1)`: the text of every persisted JSON file.
pub fn to_file(value: &Value) -> Result<String, DumpsError> {
    dumps(value, &DumpsOptions::file())
}

/// `json.dumps(value)`: Python's defaults (`ensure_ascii=True`, `", "` and `": "`).
pub fn to_python_default(value: &Value) -> Result<String, DumpsError> {
    dumps(value, &DumpsOptions::python_default())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn classify_normalizes_number_text() {
        let cases: &[(&str, PyNumber)] = &[
            ("0", PyNumber::Int("0".into())),
            ("-0", PyNumber::Int("0".into())),
            ("007", PyNumber::Int("7".into())),
            ("-12", PyNumber::Int("-12".into())),
            ("1e16", PyNumber::Float(1e16)),
            ("2.0", PyNumber::Float(2.0)),
            ("1E+2", PyNumber::Float(100.0)),
        ];
        for (text, expected) in cases {
            let n = Number::from_string_unchecked((*text).to_string());
            assert_eq!(classify_number(&n).ok().as_ref(), Some(expected), "{text}");
        }
        for bad in ["", "-", "abc", "inf", "nan", "+1", ".5", "0x10"] {
            let n = Number::from_string_unchecked(bad.to_string());
            assert!(
                classify_number(&n).is_err(),
                "{bad:?} is not a Python number"
            );
        }
    }

    #[test]
    fn int_value_checks_its_text() {
        assert_eq!(int_value("-0").map(|v| v.to_string()), Some("0".into()));
        assert_eq!(int_value("123").map(|v| v.to_string()), Some("123".into()));
        assert!(int_value("1.5").is_none());
        assert!(int_value("").is_none());
        assert!(int_value(&"9".repeat(INT_MAX_STR_DIGITS + 1)).is_none());
    }

    #[test]
    fn invalid_number_text_is_an_error() {
        let v = Value::Number(Number::from_string_unchecked("bogus".into()));
        let err = dumps(&v, &DumpsOptions::wire()).err();
        assert_eq!(err, Some(DumpsError::InvalidNumber("bogus".into())));
    }

    #[test]
    fn writer_depth_is_bounded() {
        let mut v = Value::Array(Vec::new());
        for _ in 1..MAX_DEPTH {
            v = Value::Array(vec![v]);
        }
        assert!(dumps(&v, &DumpsOptions::wire()).is_ok());
        for _ in 0..1 {
            v = Value::Array(vec![v]);
        }
        let err = dumps(&v, &DumpsOptions::wire()).err();
        assert_eq!(err, Some(DumpsError::TooDeep));
        assert_eq!(DumpsError::TooDeep.python_type(), "RecursionError");
        // Dropping a deep value recursively is safe at this depth.
        drop(v);
    }
}
