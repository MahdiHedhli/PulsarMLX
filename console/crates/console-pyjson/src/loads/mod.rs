//! Owned by API-01. Parsing with Python `json.loads` semantics, including `raw_decode`.
//!
//! The parser is a port of CPython 3.14's C scanner (`Modules/_json.c`) and of
//! `json.loads` / `json.detect_encoding` (`Lib/json/__init__.py`, `Lib/json/decoder.py`). It
//! accepts what CPython accepts and fails with CPython's message and position for every
//! input CPython rejects. Two inputs CPython accepts are refused here, each with its own
//! [`LoadsError`] case: a string holding an unpaired UTF-16 surrogate, which a Rust `String`
//! cannot hold ([`LoadsError::LoneSurrogate`]), and nesting deeper than [`MAX_DEPTH`]
//! ([`LoadsError::TooDeep`]). The two refusals are proposals P-19 and P-20 in the deviation
//! register of feature 022 and await the owner's decision. As in CPython:
//!
//! - `NaN`, `Infinity` and `-Infinity` are accepted.
//! - Integers of any size up to Python's 4300-digit conversion limit are kept exactly; a float
//!   is read as an IEEE double (`1e400` is infinity, `0.10000000000000001` is `0.1`).
//! - A duplicate key keeps its first position and takes the last value, as a Python `dict`.
//! - Whitespace is only space, tab, line feed and carriage return; anything else after the
//!   document is `Extra data`.
//! - Error positions are code-point indexes (`char N`) with Python's line and column.
//!
//! Numbers are stored in [`serde_json::Value`] in Python's normalized form, so that the
//! number text is what Python would print: an integer as its decimal digits (`-0` becomes
//! `0`), a float as its `repr` (`1e+16`, `2.0`, `1e-07`), and the non-finite floats as `NaN`,
//! `Infinity` and `-Infinity` (see [`crate::dumps::float_value`]).
//!
//! Behavior reference: project-maya serve/server.py:6243 (`json.loads(raw_ or b"{}")` for a
//! request body), serve/server.py:4909-4930 (`json_from_text` and `raw_decode`) and the
//! `json.loads` sites of serve/frontend.py at 7e68a30f.

use std::cell::Cell;
use std::fmt;

use serde_json::{Map, Value};

/// The deepest nesting of arrays and objects the parser and the writer accept.
///
/// CPython has no fixed limit (it fails when its C stack runs out, at a depth that depends on
/// the platform). An explicit limit keeps the stack and the recursive drop of a
/// [`serde_json::Value`] bounded; a deeper document fails with [`LoadsError::TooDeep`].
///
/// Proposal P-20 in the deviation register, awaiting the owner's decision.
pub const MAX_DEPTH: usize = 1000;

/// Python's default limit on the decimal digits of an integer converted from or to text
/// (`sys.get_int_max_str_digits()`).
pub const INT_MAX_STR_DIGITS: usize = 4300;

/// A `json.JSONDecodeError`: the message, and the code-point position with its line and
/// column. Its `Display` is Python's `str(error)`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct JsonDecodeError {
    /// The message without the position, such as `Expecting value`.
    pub msg: &'static str,
    /// Code-point index into the document.
    pub pos: usize,
    /// One-based line number.
    pub lineno: usize,
    /// One-based column number, in code points.
    pub colno: usize,
}

impl fmt::Display for JsonDecodeError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "{}: line {} column {} (char {})",
            self.msg, self.lineno, self.colno, self.pos
        )
    }
}

/// A `UnicodeDecodeError` raised while decoding a request body's bytes. Its `Display` is
/// Python's `str(error)`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct UnicodeDecodeError {
    /// The codec name Python reports, such as `utf-8` or `utf-16-le`.
    pub encoding: &'static str,
    /// The first byte of the bad sequence.
    pub first_byte: u8,
    /// Byte position of the bad sequence (start, inclusive).
    pub start: usize,
    /// Byte position of the bad sequence (end, exclusive).
    pub end: usize,
    /// Python's reason text, such as `invalid start byte`.
    pub reason: &'static str,
}

impl fmt::Display for UnicodeDecodeError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        if self.end.saturating_sub(self.start) <= 1 {
            write!(
                f,
                "'{}' codec can't decode byte 0x{:02x} in position {}: {}",
                self.encoding, self.first_byte, self.start, self.reason
            )
        } else {
            write!(
                f,
                "'{}' codec can't decode bytes in position {}-{}: {}",
                self.encoding,
                self.start,
                self.end - 1,
                self.reason
            )
        }
    }
}

/// Why a document could not be parsed.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum LoadsError {
    /// Python's `json.JSONDecodeError` (a `ValueError`), with Python's message and position.
    Decode(JsonDecodeError),
    /// Python's `UnicodeDecodeError` (a `ValueError`) for a body that is not valid text in the
    /// encoding `json.detect_encoding` chose.
    Unicode(UnicodeDecodeError),
    /// Python's `ValueError` for an integer literal of more than [`INT_MAX_STR_DIGITS`]
    /// digits; `digits` excludes the sign.
    IntTooLong {
        /// The number of digits of the literal.
        digits: usize,
    },
    /// A string holds an unpaired UTF-16 surrogate (a `\uD800` escape with no low half, or a
    /// surrogate encoded in the body bytes). CPython accepts it and builds a `str` that Rust
    /// cannot hold; this parser refuses the document instead, but only once the rest of the
    /// document has parsed, so that any error CPython would raise is still raised first.
    /// There is no Python message for this case; the text is this crate's own, in Python's
    /// position format, at the first such surrogate.
    ///
    /// Proposal P-19 in the deviation register, awaiting the owner's decision.
    LoneSurrogate(JsonDecodeError),
    /// Nesting deeper than [`MAX_DEPTH`]. CPython raises `RecursionError` only when its stack
    /// runs out; the message follows CPython's wording.
    ///
    /// Proposal P-20 in the deviation register, awaiting the owner's decision.
    TooDeep {
        /// `true` for an object, `false` for an array.
        object: bool,
    },
}

impl LoadsError {
    /// The Python exception class this error corresponds to: `JSONDecodeError`,
    /// `UnicodeDecodeError`, `ValueError` or `RecursionError`.
    pub fn python_type(&self) -> &'static str {
        match self {
            LoadsError::Decode(_) | LoadsError::LoneSurrogate(_) => "JSONDecodeError",
            LoadsError::Unicode(_) => "UnicodeDecodeError",
            LoadsError::IntTooLong { .. } => "ValueError",
            LoadsError::TooDeep { .. } => "RecursionError",
        }
    }

    /// Whether Python would raise a subclass of `ValueError` (every case but
    /// [`LoadsError::TooDeep`]).
    pub fn is_value_error(&self) -> bool {
        !matches!(self, LoadsError::TooDeep { .. })
    }
}

impl fmt::Display for LoadsError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            LoadsError::Decode(e) => e.fmt(f),
            LoadsError::Unicode(e) => e.fmt(f),
            LoadsError::IntTooLong { digits } => write!(
                f,
                "Exceeds the limit ({INT_MAX_STR_DIGITS} digits) for integer string conversion: \
                 value has {digits} digits; use sys.set_int_max_str_digits() to increase the limit"
            ),
            LoadsError::LoneSurrogate(e) => e.fmt(f),
            LoadsError::TooDeep { object } => write!(
                f,
                "maximum recursion depth exceeded while decoding a JSON {} from a unicode string",
                if *object { "object" } else { "array" }
            ),
        }
    }
}

impl std::error::Error for LoadsError {}

/// Python `json.loads(s)` for a `str`.
///
/// A leading U+FEFF is refused as Python refuses it (`Unexpected UTF-8 BOM`).
pub fn loads(s: &str) -> Result<Value, LoadsError> {
    if s.starts_with('\u{feff}') {
        return Err(LoadsError::Decode(decode_error_at(
            s.as_bytes(),
            "Unexpected UTF-8 BOM (decode using utf-8-sig)",
            0,
        )));
    }
    Parser::new(s, &[]).decode()
}

/// Python `json.loads(b)` for `bytes`: the encoding is chosen by `json.detect_encoding`
/// (UTF-32 or UTF-16 by byte-order mark or by zero-byte pattern, UTF-8 with or without a
/// byte-order mark otherwise) and the text is decoded with the `surrogatepass` handler.
pub fn loads_bytes(b: &[u8]) -> Result<Value, LoadsError> {
    let (text, surrogates) = decode_body(b).map_err(LoadsError::Unicode)?;
    Parser::new(&text, &surrogates).decode()
}

/// Python `json.JSONDecoder().raw_decode(s, idx)`: one JSON value starting exactly at
/// code-point index `idx` (no whitespace is skipped), and the code-point index just after it.
/// Text after the value is ignored.
pub fn raw_decode(s: &str, idx: usize) -> Result<(Value, usize), LoadsError> {
    let Some(byte) = crate::pystr::char_to_byte(s, idx) else {
        // Past the end: Python's scanner raises StopIteration(idx), reported as
        // "Expecting value" at that index.
        let b = s.as_bytes();
        let newlines = b.iter().filter(|&&c| c == b'\n').count();
        let last_nl = s.rfind('\n').map(|p| count_chars(b.get(..p).unwrap_or(b)));
        return Err(LoadsError::Decode(JsonDecodeError {
            msg: "Expecting value",
            pos: idx,
            lineno: newlines + 1,
            colno: match last_nl {
                Some(nl) => idx - nl,
                None => idx + 1,
            },
        }));
    };
    let (value, end) = raw_decode_bytes(s, byte)?;
    let b = s.as_bytes();
    Ok((value, count_chars(b.get(..end).unwrap_or(b))))
}

/// [`raw_decode`] with byte offsets: the value starting at byte offset `start` (which must be
/// a character boundary) and the byte offset just after it. Error positions are still
/// reported as Python code-point indexes.
pub fn raw_decode_bytes(s: &str, start: usize) -> Result<(Value, usize), LoadsError> {
    let parser = Parser::new(s, &[]);
    let parsed = parser.scan_once(start)?;
    parser.finish(parsed)
}

/// Python truthiness of a decoded value: `None`, `False`, `0`, `0.0`, `""`, `[]` and `{}` are
/// false; everything else (including `NaN`) is true.
pub fn truthy(v: &Value) -> bool {
    match v {
        Value::Null => false,
        Value::Bool(b) => *b,
        Value::Number(n) => match crate::dumps::classify_number(n) {
            Ok(crate::dumps::PyNumber::Int(digits)) => digits != "0",
            Ok(crate::dumps::PyNumber::Float(f)) => f != 0.0,
            Err(_) => true,
        },
        Value::String(s) => !s.is_empty(),
        Value::Array(a) => !a.is_empty(),
        Value::Object(o) => !o.is_empty(),
    }
}

// ---------------------------------------------------------------------------------------
// Byte decoding (json.detect_encoding and the surrogatepass codecs)

/// Code points of the input that are UTF-16 surrogates are written as U+FFFD into the decoded
/// text; their byte offsets in that text are returned beside it, so that the parser treats
/// them as Python treats a lone surrogate (accepted only inside a string, where this port
/// refuses it with [`LoadsError::LoneSurrogate`]).
type Decoded = (String, Vec<usize>);

fn decode_body(b: &[u8]) -> Result<Decoded, UnicodeDecodeError> {
    const BOM8: &[u8] = &[0xef, 0xbb, 0xbf];
    if b.starts_with(&[0x00, 0x00, 0xfe, 0xff]) {
        return decode_utf32(b, 4, true);
    }
    if b.starts_with(&[0xff, 0xfe, 0x00, 0x00]) {
        return decode_utf32(b, 4, false);
    }
    if b.starts_with(&[0xfe, 0xff]) {
        return decode_utf16(b, 2, true);
    }
    if b.starts_with(&[0xff, 0xfe]) {
        return decode_utf16(b, 2, false);
    }
    if let Some(rest) = b.strip_prefix(BOM8) {
        return decode_utf8(rest);
    }
    match b {
        [0, b1, _, _, ..] => {
            if *b1 != 0 {
                decode_utf16(b, 0, true)
            } else {
                decode_utf32(b, 0, true)
            }
        }
        [_, 0, b2, b3, ..] => {
            if *b2 != 0 || *b3 != 0 {
                decode_utf16(b, 0, false)
            } else {
                decode_utf32(b, 0, false)
            }
        }
        [0, _] => decode_utf16(b, 0, true),
        [_, 0] => decode_utf16(b, 0, false),
        _ => decode_utf8(b),
    }
}

fn push_surrogate(out: &mut String, marks: &mut Vec<usize>) {
    marks.push(out.len());
    out.push('\u{fffd}');
}

/// UTF-8 with the `surrogatepass` handler. Positions in errors are relative to `b` (for
/// `utf-8-sig` Python reports them after the byte-order mark).
fn decode_utf8(b: &[u8]) -> Result<Decoded, UnicodeDecodeError> {
    let mut out = String::with_capacity(b.len());
    let mut marks = Vec::new();
    let mut pos = 0usize;
    while pos < b.len() {
        let Some(rest) = b.get(pos..) else {
            break;
        };
        match std::str::from_utf8(rest) {
            Ok(text) => {
                out.push_str(text);
                break;
            }
            Err(e) => {
                let good = e.valid_up_to();
                if let Ok(text) = std::str::from_utf8(rest.get(..good).unwrap_or_default()) {
                    out.push_str(text);
                }
                let bad = pos + good;
                let tail = b.get(bad..).unwrap_or_default();
                // surrogatepass: ED A0..BF 80..BF is a surrogate code point.
                if let [0xed, b1, b2, ..] = tail {
                    if (0xa0..=0xbf).contains(b1) && (0x80..=0xbf).contains(b2) {
                        push_surrogate(&mut out, &mut marks);
                        pos = bad + 3;
                        continue;
                    }
                }
                let first = tail.first().copied().unwrap_or(0);
                return Err(match e.error_len() {
                    None => UnicodeDecodeError {
                        encoding: "utf-8",
                        first_byte: first,
                        start: bad,
                        end: b.len(),
                        reason: "unexpected end of data",
                    },
                    Some(1) if matches!(first, 0x80..=0xc1 | 0xf5..=0xff) => UnicodeDecodeError {
                        encoding: "utf-8",
                        first_byte: first,
                        start: bad,
                        end: bad + 1,
                        reason: "invalid start byte",
                    },
                    Some(n) => UnicodeDecodeError {
                        encoding: "utf-8",
                        first_byte: first,
                        start: bad,
                        end: bad + n,
                        reason: "invalid continuation byte",
                    },
                });
            }
        }
    }
    Ok((out, marks))
}

fn decode_utf16(b: &[u8], start: usize, big_endian: bool) -> Result<Decoded, UnicodeDecodeError> {
    let name = if big_endian { "utf-16-be" } else { "utf-16-le" };
    let unit_at = |i: usize| -> Option<u32> {
        match (b.get(i), b.get(i + 1)) {
            (Some(&x), Some(&y)) => Some(if big_endian {
                u32::from(x) << 8 | u32::from(y)
            } else {
                u32::from(y) << 8 | u32::from(x)
            }),
            _ => None,
        }
    };
    let mut out = String::with_capacity(b.len() / 2);
    let mut marks = Vec::new();
    let mut i = start;
    while i < b.len() {
        let Some(u) = unit_at(i) else {
            return Err(UnicodeDecodeError {
                encoding: name,
                first_byte: b.get(i).copied().unwrap_or(0),
                start: i,
                end: b.len(),
                reason: "truncated data",
            });
        };
        if (0xd800..=0xdbff).contains(&u) {
            if let Some(low) = unit_at(i + 2).filter(|l| (0xdc00..=0xdfff).contains(l)) {
                let cp = 0x10000 + ((u - 0xd800) << 10) + (low - 0xdc00);
                if let Some(c) = char::from_u32(cp) {
                    out.push(c);
                }
                i += 4;
                continue;
            }
            push_surrogate(&mut out, &mut marks);
        } else if (0xdc00..=0xdfff).contains(&u) {
            push_surrogate(&mut out, &mut marks);
        } else if let Some(c) = char::from_u32(u) {
            out.push(c);
        }
        i += 2;
    }
    Ok((out, marks))
}

fn decode_utf32(b: &[u8], start: usize, big_endian: bool) -> Result<Decoded, UnicodeDecodeError> {
    let name = if big_endian { "utf-32-be" } else { "utf-32-le" };
    let mut out = String::with_capacity(b.len() / 4);
    let mut marks = Vec::new();
    let mut i = start;
    while i < b.len() {
        let Some([w0, w1, w2, w3]) = b.get(i..i + 4).and_then(|s| <[u8; 4]>::try_from(s).ok())
        else {
            return Err(UnicodeDecodeError {
                encoding: name,
                first_byte: b.get(i).copied().unwrap_or(0),
                start: i,
                end: b.len(),
                reason: "truncated data",
            });
        };
        let cp = if big_endian {
            u32::from_be_bytes([w0, w1, w2, w3])
        } else {
            u32::from_le_bytes([w0, w1, w2, w3])
        };
        if (0xd800..=0xdfff).contains(&cp) {
            push_surrogate(&mut out, &mut marks);
        } else if let Some(c) = char::from_u32(cp) {
            out.push(c);
        } else {
            return Err(UnicodeDecodeError {
                encoding: name,
                first_byte: w0,
                start: i,
                end: i + 4,
                reason: "code point not in range(0x110000)",
            });
        }
        i += 4;
    }
    Ok((out, marks))
}

// ---------------------------------------------------------------------------------------
// The scanner

/// Number of code points in a UTF-8 byte prefix (bytes that are not continuation bytes).
fn count_chars(b: &[u8]) -> usize {
    b.iter().filter(|&&c| (c & 0xc0) != 0x80).count()
}

/// A `JSONDecodeError` at byte offset `byte`, with Python's code-point position, line and
/// column (`lineno = doc.count('\n', 0, pos) + 1`, `colno = pos - doc.rfind('\n', 0, pos)`).
fn decode_error_at(b: &[u8], msg: &'static str, byte: usize) -> JsonDecodeError {
    let head = b.get(..byte).unwrap_or(b);
    let pos = count_chars(head);
    let lineno = head.iter().filter(|&&c| c == b'\n').count() + 1;
    let colno = match head.iter().rposition(|&c| c == b'\n') {
        Some(nl) => pos - count_chars(head.get(..nl).unwrap_or_default()),
        None => pos + 1,
    };
    JsonDecodeError {
        msg,
        pos,
        lineno,
        colno,
    }
}

fn is_ws(c: u8) -> bool {
    matches!(c, b' ' | b'\t' | b'\n' | b'\r')
}

/// Wraps Python's normalized number text in a `serde_json::Number`.
///
/// `Number::from_string_unchecked` is marked hidden ("not public API") in `serde_json`; it is
/// the only constructor that stores arbitrary number text, which `NaN` and `Infinity` need
/// under `arbitrary_precision`. The exact `=1.0.151` pin in console/Cargo.toml keeps it; a
/// version change must re-check it (the golden tests fail if it changes behavior).
fn number_value(text: String) -> Value {
    Value::Number(serde_json::Number::from_string_unchecked(text))
}

/// An open container of the iterative scanner: an array with its items so far, or an object
/// with its members so far and the key whose value is being parsed.
enum Frame {
    Array(Vec<Value>),
    Object(Map<String, Value>, String),
}

struct Parser<'a> {
    s: &'a str,
    b: &'a [u8],
    /// Byte offsets of U+FFFD characters that stand for lone surrogates of the body bytes.
    surrogates: &'a [usize],
    /// The first lone surrogate met inside a string. CPython accepts it and goes on, so a
    /// later syntax error still wins; it is reported only when the rest of the document
    /// parses.
    first_surrogate: Cell<Option<usize>>,
}

impl<'a> Parser<'a> {
    fn new(s: &'a str, surrogates: &'a [usize]) -> Self {
        Parser {
            s,
            b: s.as_bytes(),
            surrogates,
            first_surrogate: Cell::new(None),
        }
    }

    fn err(&self, msg: &'static str, byte: usize) -> LoadsError {
        LoadsError::Decode(decode_error_at(self.b, msg, byte))
    }

    /// Notes a lone surrogate at byte offset `byte` (the first one is kept).
    fn note_surrogate(&self, byte: usize) {
        if self.first_surrogate.get().is_none() {
            self.first_surrogate.set(Some(byte));
        }
    }

    /// The deferred lone-surrogate refusal, once the document has parsed.
    fn finish<T>(&self, parsed: T) -> Result<T, LoadsError> {
        match self.first_surrogate.get() {
            None => Ok(parsed),
            Some(byte) => Err(LoadsError::LoneSurrogate(decode_error_at(
                self.b,
                "Unpaired surrogate in string (not representable)",
                byte,
            ))),
        }
    }

    fn skip_ws(&self, mut idx: usize) -> usize {
        while self.b.get(idx).copied().is_some_and(is_ws) {
            idx += 1;
        }
        idx
    }

    fn at(&self, idx: usize) -> Option<u8> {
        self.b.get(idx).copied()
    }

    /// `json.loads` after decoding: skip whitespace, one value, skip whitespace, nothing else.
    fn decode(&self) -> Result<Value, LoadsError> {
        let idx = self.skip_ws(0);
        let (value, end) = self.scan_once(idx)?;
        let end = self.skip_ws(end);
        if end != self.b.len() {
            return Err(self.err("Extra data", end));
        }
        self.finish(value)
    }

    fn literal(&self, idx: usize, word: &[u8]) -> bool {
        self.b.get(idx..idx + word.len()) == Some(word)
    }

    /// `scan_once_unicode`: one value at `idx`.
    ///
    /// CPython's scanner recurses into arrays and objects; this port keeps an explicit stack
    /// of open containers instead, so that the nesting depth costs heap, not stack. The
    /// checks and their order (and so every error message and position) are those of
    /// `_parse_array_unicode` and `_parse_object_unicode`.
    fn scan_once(&self, start: usize) -> Result<(Value, usize), LoadsError> {
        let mut stack: Vec<Frame> = Vec::new();
        let mut idx = start;
        'value: loop {
            // Parse the value at `idx`: a scalar completes at once; a non-empty container is
            // opened and its first member is parsed next.
            let (mut value, mut next) = match self.at(idx) {
                Some(b'{') => {
                    if stack.len() + 1 > MAX_DEPTH {
                        return Err(LoadsError::TooDeep { object: true });
                    }
                    let first = self.skip_ws(idx + 1);
                    if self.at(first) == Some(b'}') {
                        (Value::Object(Map::new()), first + 1)
                    } else {
                        let (key, after) = self.object_key(first)?;
                        stack.push(Frame::Object(Map::new(), key));
                        idx = after;
                        continue 'value;
                    }
                }
                Some(b'[') => {
                    if stack.len() + 1 > MAX_DEPTH {
                        return Err(LoadsError::TooDeep { object: false });
                    }
                    let first = self.skip_ws(idx + 1);
                    if self.at(first) == Some(b']') {
                        (Value::Array(Vec::new()), first + 1)
                    } else {
                        stack.push(Frame::Array(Vec::new()));
                        idx = first;
                        continue 'value;
                    }
                }
                _ => self.scan_scalar(idx)?,
            };
            // Attach the completed value to the innermost open container, closing containers
            // as their end is reached.
            loop {
                let Some(frame) = stack.last_mut() else {
                    return Ok((value, next));
                };
                let at = self.skip_ws(next);
                let (closer, trailing) = match frame {
                    Frame::Array(items) => {
                        items.push(value);
                        (b']', "Illegal trailing comma before end of array")
                    }
                    Frame::Object(map, key) => {
                        map.insert(std::mem::take(key), value);
                        (b'}', "Illegal trailing comma before end of object")
                    }
                };
                if self.at(at) == Some(closer) {
                    value = match stack.pop() {
                        Some(Frame::Array(items)) => Value::Array(items),
                        Some(Frame::Object(map, _)) => Value::Object(map),
                        None => Value::Null,
                    };
                    next = at + 1;
                    continue;
                }
                if self.at(at) != Some(b',') {
                    return Err(self.err("Expecting ',' delimiter", at));
                }
                let member = self.skip_ws(at + 1);
                if self.at(member) == Some(closer) {
                    return Err(self.err(trailing, at));
                }
                if let Some(Frame::Object(_, key)) = stack.last_mut() {
                    let (k, after) = self.object_key(member)?;
                    *key = k;
                    idx = after;
                } else {
                    idx = member;
                }
                continue 'value;
            }
        }
    }

    /// The key of an object member at `idx` and its `:` delimiter; returns the key and the
    /// byte where the member's value starts.
    fn object_key(&self, idx: usize) -> Result<(String, usize), LoadsError> {
        if self.at(idx) != Some(b'"') {
            return Err(self.err("Expecting property name enclosed in double quotes", idx));
        }
        let (key, next) = self.scanstring(idx + 1)?;
        let colon = self.skip_ws(next);
        if self.at(colon) != Some(b':') {
            return Err(self.err("Expecting ':' delimiter", colon));
        }
        Ok((key, self.skip_ws(colon + 1)))
    }

    /// A string, a named constant or a number at `idx` (the non-container cases of
    /// `scan_once_unicode`).
    fn scan_scalar(&self, idx: usize) -> Result<(Value, usize), LoadsError> {
        let Some(c) = self.at(idx) else {
            return Err(self.err("Expecting value", idx));
        };
        match c {
            b'"' => {
                let (s, end) = self.scanstring(idx + 1)?;
                return Ok((Value::String(s), end));
            }
            b'n' if self.literal(idx, b"null") => return Ok((Value::Null, idx + 4)),
            b't' if self.literal(idx, b"true") => return Ok((Value::Bool(true), idx + 4)),
            b'f' if self.literal(idx, b"false") => return Ok((Value::Bool(false), idx + 5)),
            b'N' if self.literal(idx, b"NaN") => {
                return Ok((number_value(String::from("NaN")), idx + 3));
            }
            b'I' if self.literal(idx, b"Infinity") => {
                return Ok((number_value(String::from("Infinity")), idx + 8));
            }
            b'-' if self.literal(idx, b"-Infinity") => {
                return Ok((number_value(String::from("-Infinity")), idx + 9));
            }
            _ => {}
        }
        self.match_number(idx)
    }

    /// `_match_number_unicode`.
    fn match_number(&self, start: usize) -> Result<(Value, usize), LoadsError> {
        let b = self.b;
        let digit = |i: usize| b.get(i).is_some_and(u8::is_ascii_digit);
        let mut idx = start;
        if self.at(idx) == Some(b'-') {
            idx += 1;
            if idx >= b.len() {
                return Err(self.err("Expecting value", start));
            }
        }
        match self.at(idx) {
            Some(b'1'..=b'9') => {
                idx += 1;
                while digit(idx) {
                    idx += 1;
                }
            }
            Some(b'0') => idx += 1,
            _ => return Err(self.err("Expecting value", start)),
        }
        let mut is_float = false;
        if self.at(idx) == Some(b'.') && digit(idx + 1) {
            is_float = true;
            idx += 2;
            while digit(idx) {
                idx += 1;
            }
        }
        if matches!(self.at(idx), Some(b'e' | b'E')) && idx + 1 < b.len() {
            let e_start = idx;
            idx += 1;
            if matches!(self.at(idx), Some(b'-' | b'+')) && idx + 1 < b.len() {
                idx += 1;
            }
            while digit(idx) {
                idx += 1;
            }
            if digit(idx - 1) {
                is_float = true;
            } else {
                idx = e_start;
            }
        }
        let text = self.s.get(start..idx).unwrap_or("0");
        if is_float {
            let f: f64 = text.parse().unwrap_or(f64::NAN);
            Ok((crate::dumps::float_value(f), idx))
        } else {
            let (neg, digits) = match text.strip_prefix('-') {
                Some(d) => (true, d),
                None => (false, text),
            };
            if digits.len() > INT_MAX_STR_DIGITS {
                return Err(LoadsError::IntTooLong {
                    digits: digits.len(),
                });
            }
            let normalized = if digits == "0" || !neg {
                digits.to_string()
            } else {
                format!("-{digits}")
            };
            Ok((number_value(normalized), idx))
        }
    }

    /// `scanstring_unicode` (strict): `end` is the byte just after the opening quote.
    fn scanstring(&self, end: usize) -> Result<(String, usize), LoadsError> {
        let b = self.b;
        let len = b.len();
        let begin = end.saturating_sub(1);
        let mut out = String::new();
        let mut pos = end;
        loop {
            let mut next = pos;
            let mut found = None;
            while let Some(&c) = b.get(next) {
                if c == b'"' || c == b'\\' {
                    found = Some(c);
                    break;
                }
                if c <= 0x1f {
                    return Err(self.err("Invalid control character at", next));
                }
                next += 1;
            }
            let Some(c) = found else {
                return Err(self.err("Unterminated string starting at", begin));
            };
            self.check_surrogates(pos, next);
            out.push_str(self.s.get(pos..next).unwrap_or(""));
            next += 1;
            if c == b'"' {
                return Ok((out, next));
            }
            let Some(esc) = self.at(next) else {
                return Err(self.err("Unterminated string starting at", begin));
            };
            if esc != b'u' {
                pos = next + 1;
                let ch = match esc {
                    b'"' => '"',
                    b'\\' => '\\',
                    b'/' => '/',
                    b'b' => '\u{8}',
                    b'f' => '\u{c}',
                    b'n' => '\n',
                    b'r' => '\r',
                    b't' => '\t',
                    _ => return Err(self.err("Invalid \\escape", pos - 2)),
                };
                out.push(ch);
            } else {
                let backslash = next - 1;
                next += 1;
                let end4 = next + 4;
                if end4 > len {
                    return Err(self.err("Invalid \\uXXXX escape", next - 1));
                }
                let Some(mut cp) = hex4(b.get(next..end4)) else {
                    return Err(self.err("Invalid \\uXXXX escape", end4 - 5));
                };
                pos = end4;
                if (0xd800..=0xdbff).contains(&cp)
                    && end4 + 6 <= len
                    && b.get(end4) == Some(&b'\\')
                    && b.get(end4 + 1) == Some(&b'u')
                {
                    let e2 = end4 + 6;
                    let Some(low) = hex4(b.get(end4 + 2..e2)) else {
                        return Err(self.err("Invalid \\uXXXX escape", e2 - 5));
                    };
                    if (0xdc00..=0xdfff).contains(&low) {
                        cp = 0x10000 + ((cp - 0xd800) << 10) + (low - 0xdc00);
                        pos = e2;
                    }
                }
                match char::from_u32(cp) {
                    Some(ch) => out.push(ch),
                    None => {
                        self.note_surrogate(backslash);
                        out.push('\u{fffd}');
                    }
                }
            }
        }
    }

    fn check_surrogates(&self, from: usize, to: usize) {
        if self.surrogates.is_empty() {
            return;
        }
        let first = self.surrogates.partition_point(|&m| m < from);
        if let Some(&m) = self.surrogates.get(first) {
            if m < to {
                self.note_surrogate(m);
            }
        }
    }
}

fn hex4(digits: Option<&[u8]>) -> Option<u32> {
    let digits = digits?;
    let mut v = 0u32;
    for &d in digits {
        v = (v << 4) | char::from(d).to_digit(16)?;
    }
    Some(v)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn msg(input: &str) -> String {
        match loads(input) {
            Ok(v) => format!("OK {v}"),
            Err(e) => format!("{}: {}", e.python_type(), e),
        }
    }

    #[test]
    fn error_positions_count_code_points() {
        assert_eq!(
            msg("[\"\u{e9}\u{1f600}\", x]"),
            "JSONDecodeError: Expecting value: line 1 column 8 (char 7)"
        );
        assert_eq!(
            msg("\n\n  x"),
            "JSONDecodeError: Expecting value: line 3 column 3 (char 4)"
        );
    }

    #[test]
    fn depth_limit_is_explicit() {
        // Pins proposal P-20 of the deviation register (awaiting the owner's decision).
        let ok = format!("{}{}", "[".repeat(MAX_DEPTH), "]".repeat(MAX_DEPTH));
        assert!(loads(&ok).is_ok());
        let deep = format!("{}{}", "[".repeat(MAX_DEPTH + 1), "]".repeat(MAX_DEPTH + 1));
        let err = loads(&deep).err();
        assert_eq!(err, Some(LoadsError::TooDeep { object: false }));
        assert_eq!(
            err.map(|e| e.to_string()).unwrap_or_default(),
            "maximum recursion depth exceeded while decoding a JSON array from a unicode string"
        );
        let deep_obj = format!(
            "{}1{}",
            "{\"a\":".repeat(MAX_DEPTH + 1),
            "}".repeat(MAX_DEPTH + 1)
        );
        assert_eq!(
            loads(&deep_obj).err(),
            Some(LoadsError::TooDeep { object: true })
        );
    }

    #[test]
    fn truthiness_is_pythons() {
        for (text, expected) in [
            ("null", false),
            ("false", false),
            ("0", false),
            ("-0", false),
            ("0.0", false),
            ("-0.0", false),
            ("\"\"", false),
            ("[]", false),
            ("{}", false),
            ("NaN", true),
            ("1", true),
            ("0.5", true),
            ("\"0\"", true),
            ("[0]", true),
            ("{\"a\":0}", true),
            ("true", true),
        ] {
            let v = loads(text).unwrap_or(Value::Null);
            assert_eq!(truthy(&v), expected, "truthiness of {text}");
        }
    }
}
