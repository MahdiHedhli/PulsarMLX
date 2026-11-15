//! Owned by API-01. Python string helpers: code-point slicing, `isspace`, `strip` and
//! `split`.
//!
//! Python indexes a `str` by code point; Rust indexes a `str` by byte. The helpers here take
//! and return code-point indexes where Python would, and convert between the two.
//!
//! The character classes are Python 3's, not Rust's:
//!
//! - [`is_space`] is `str.isspace` for one character: Unicode bidirectional class WS, B or S,
//!   or category Zs. It differs from `char::is_whitespace` by including U+001C to U+001F.
//!   `str.strip()`, `str.split()` with no argument and `str.isspace()` use this set.
//! - [`is_digit`] is `str.isdigit` for one character (Numeric_Type Digit or Decimal), which
//!   includes superscripts and circled digits but not fractions.
//!
//! The digit and title-case tables were recorded from CPython 3.14.7 (Unicode 16.0.0) with
//! `python3 -I -c '...'` and the standard library only. Rust's own case mappings follow the
//! toolchain's Unicode version (17.0 for 1.97.1); [`capitalize`] keeps the case pairs that
//! Unicode 17 added unchanged, as Python 3.14 does, so its output matches CPython 3.14.
//!
//! Behavior reference: the `str` methods of CPython 3.14 (`Objects/unicodeobject.c`,
//! `Objects/stringlib/split.h`), as used throughout project-maya serve/frontend.py at
//! 7e68a30f.

use std::fmt;

/// An error a Python `str` method would raise as `ValueError`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PyStrError {
    /// `str.split("")`: Python raises `ValueError: empty separator`.
    EmptySeparator,
}

impl fmt::Display for PyStrError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            PyStrError::EmptySeparator => f.write_str("empty separator"),
        }
    }
}

impl std::error::Error for PyStrError {}

/// Python's whitespace test for one character (`Py_UNICODE_ISSPACE`).
pub fn is_space(c: char) -> bool {
    matches!(
        c,
        '\u{9}'..='\u{d}'
            | '\u{1c}'..='\u{20}'
            | '\u{85}'
            | '\u{a0}'
            | '\u{1680}'
            | '\u{2000}'..='\u{200a}'
            | '\u{2028}'
            | '\u{2029}'
            | '\u{202f}'
            | '\u{205f}'
            | '\u{3000}'
    )
}

/// Python `str.isspace()`: true when the string is not empty and every character is
/// whitespace in Python's sense.
pub fn isspace(s: &str) -> bool {
    !s.is_empty() && s.chars().all(is_space)
}

/// Code-point ranges for which CPython 3.14.7 `str.isdigit()` is true (Unicode 16.0.0).
const DIGIT_RANGES: &[(u32, u32)] = &[
    (0x30, 0x39),
    (0xb2, 0xb3),
    (0xb9, 0xb9),
    (0x660, 0x669),
    (0x6f0, 0x6f9),
    (0x7c0, 0x7c9),
    (0x966, 0x96f),
    (0x9e6, 0x9ef),
    (0xa66, 0xa6f),
    (0xae6, 0xaef),
    (0xb66, 0xb6f),
    (0xbe6, 0xbef),
    (0xc66, 0xc6f),
    (0xce6, 0xcef),
    (0xd66, 0xd6f),
    (0xde6, 0xdef),
    (0xe50, 0xe59),
    (0xed0, 0xed9),
    (0xf20, 0xf29),
    (0x1040, 0x1049),
    (0x1090, 0x1099),
    (0x1369, 0x1371),
    (0x17e0, 0x17e9),
    (0x1810, 0x1819),
    (0x1946, 0x194f),
    (0x19d0, 0x19da),
    (0x1a80, 0x1a89),
    (0x1a90, 0x1a99),
    (0x1b50, 0x1b59),
    (0x1bb0, 0x1bb9),
    (0x1c40, 0x1c49),
    (0x1c50, 0x1c59),
    (0x2070, 0x2070),
    (0x2074, 0x2079),
    (0x2080, 0x2089),
    (0x2460, 0x2468),
    (0x2474, 0x247c),
    (0x2488, 0x2490),
    (0x24ea, 0x24ea),
    (0x24f5, 0x24fd),
    (0x24ff, 0x24ff),
    (0x2776, 0x277e),
    (0x2780, 0x2788),
    (0x278a, 0x2792),
    (0xa620, 0xa629),
    (0xa8d0, 0xa8d9),
    (0xa900, 0xa909),
    (0xa9d0, 0xa9d9),
    (0xa9f0, 0xa9f9),
    (0xaa50, 0xaa59),
    (0xabf0, 0xabf9),
    (0xff10, 0xff19),
    (0x104a0, 0x104a9),
    (0x10a40, 0x10a43),
    (0x10d30, 0x10d39),
    (0x10d40, 0x10d49),
    (0x10e60, 0x10e68),
    (0x11052, 0x1105a),
    (0x11066, 0x1106f),
    (0x110f0, 0x110f9),
    (0x11136, 0x1113f),
    (0x111d0, 0x111d9),
    (0x112f0, 0x112f9),
    (0x11450, 0x11459),
    (0x114d0, 0x114d9),
    (0x11650, 0x11659),
    (0x116c0, 0x116c9),
    (0x116d0, 0x116e3),
    (0x11730, 0x11739),
    (0x118e0, 0x118e9),
    (0x11950, 0x11959),
    (0x11bf0, 0x11bf9),
    (0x11c50, 0x11c59),
    (0x11d50, 0x11d59),
    (0x11da0, 0x11da9),
    (0x11f50, 0x11f59),
    (0x16130, 0x16139),
    (0x16a60, 0x16a69),
    (0x16ac0, 0x16ac9),
    (0x16b50, 0x16b59),
    (0x16d70, 0x16d79),
    (0x1ccf0, 0x1ccf9),
    (0x1d7ce, 0x1d7ff),
    (0x1e140, 0x1e149),
    (0x1e2f0, 0x1e2f9),
    (0x1e4f0, 0x1e4f9),
    (0x1e5f1, 0x1e5fa),
    (0x1e950, 0x1e959),
    (0x1f100, 0x1f10a),
    (0x1fbf0, 0x1fbf9),
];

/// Python's digit test for one character (`str.isdigit` on a one-character string).
pub fn is_digit(c: char) -> bool {
    let cp = c as u32;
    DIGIT_RANGES
        .binary_search_by(|&(lo, hi)| {
            if hi < cp {
                std::cmp::Ordering::Less
            } else if lo > cp {
                std::cmp::Ordering::Greater
            } else {
                std::cmp::Ordering::Equal
            }
        })
        .is_ok()
}

/// Python `str.isdigit()`: true when the string is not empty and every character is a digit.
pub fn isdigit(s: &str) -> bool {
    !s.is_empty() && s.chars().all(is_digit)
}

fn strip_set(chars: Option<&str>) -> impl Fn(char) -> bool + '_ {
    move |c| match chars {
        None => is_space(c),
        Some(set) => set.contains(c),
    }
}

/// Python `str.strip()` (with `None`) or `str.strip(chars)`.
pub fn strip<'a>(s: &'a str, chars: Option<&str>) -> &'a str {
    let test = strip_set(chars);
    s.trim_start_matches(&test).trim_end_matches(&test)
}

/// Python `str.lstrip()` (with `None`) or `str.lstrip(chars)`.
pub fn lstrip<'a>(s: &'a str, chars: Option<&str>) -> &'a str {
    s.trim_start_matches(strip_set(chars))
}

/// Python `str.rstrip()` (with `None`) or `str.rstrip(chars)`.
pub fn rstrip<'a>(s: &'a str, chars: Option<&str>) -> &'a str {
    s.trim_end_matches(strip_set(chars))
}

/// Python `str.split()` / `str.split(None, maxsplit)`: runs of Python whitespace separate
/// fields, leading and trailing whitespace give no empty field, and once `maxsplit` splits are
/// made the rest of the string, with its leading whitespace removed, is the last field.
/// `None` stands for Python's `maxsplit=-1`.
pub fn split_whitespace(s: &str, maxsplit: Option<usize>) -> Vec<&str> {
    let mut out = Vec::new();
    let mut remaining = maxsplit.unwrap_or(usize::MAX);
    let mut rest = s;
    while remaining > 0 {
        rest = rest.trim_start_matches(is_space);
        if rest.is_empty() {
            return out;
        }
        let end = rest.find(is_space).unwrap_or(rest.len());
        let (field, tail) = rest.split_at_checked(end).unwrap_or((rest, ""));
        out.push(field);
        rest = tail;
        remaining -= 1;
    }
    let tail = rest.trim_start_matches(is_space);
    if !tail.is_empty() {
        out.push(tail);
    }
    out
}

/// Python `str.split(sep)` / `str.split(sep, maxsplit)` with an explicit separator. `None`
/// stands for Python's `maxsplit=-1`. An empty separator is Python's `ValueError`.
pub fn split<'a>(
    s: &'a str,
    sep: &str,
    maxsplit: Option<usize>,
) -> Result<Vec<&'a str>, PyStrError> {
    if sep.is_empty() {
        return Err(PyStrError::EmptySeparator);
    }
    let mut out = Vec::new();
    let mut remaining = maxsplit.unwrap_or(usize::MAX);
    let mut rest = s;
    while remaining > 0 {
        match rest.find(sep) {
            Some(pos) => {
                out.push(rest.get(..pos).unwrap_or(""));
                rest = rest.get(pos + sep.len()..).unwrap_or("");
                remaining -= 1;
            }
            None => break,
        }
    }
    out.push(rest);
    Ok(out)
}

/// Python `len(s)`: the number of code points.
pub fn char_len(s: &str) -> usize {
    s.chars().count()
}

/// The byte offset of code point `index` in `s`; `index == char_len(s)` gives `s.len()`.
/// `None` when the index is past the end.
pub fn char_to_byte(s: &str, index: usize) -> Option<usize> {
    if index == 0 {
        return Some(0);
    }
    let mut count = 0usize;
    for (byte, _) in s.char_indices() {
        if count == index {
            return Some(byte);
        }
        count += 1;
    }
    if count == index {
        Some(s.len())
    } else {
        None
    }
}

/// The code-point index of byte offset `byte` in `s`. `None` when the offset is past the end
/// or not on a character boundary.
pub fn byte_to_char(s: &str, byte: usize) -> Option<usize> {
    if !s.is_char_boundary(byte) {
        return None;
    }
    s.get(..byte).map(|head| head.chars().count())
}

/// Python's index normalization for a slice bound of a sequence of `len` items: a negative
/// bound counts from the end, and the result is clamped to `0..=len`.
fn clamp_bound(bound: isize, len: usize) -> usize {
    if bound < 0 {
        len.saturating_sub(bound.unsigned_abs())
    } else {
        bound.unsigned_abs().min(len)
    }
}

/// Python `s[start:stop]` with step 1, by code point. `None` bounds are Python's omitted
/// bounds; negative bounds count from the end; out-of-range bounds are clamped; an empty
/// range gives `""`.
///
/// ```
/// use console_pyjson::pystr::slice;
/// assert_eq!(slice("héllo", Some(1), Some(-1)), "éll");
/// assert_eq!(slice("héllo", Some(-2), None), "lo");
/// assert_eq!(slice("héllo", Some(4), Some(2)), "");
/// ```
pub fn slice(s: &str, start: Option<isize>, stop: Option<isize>) -> &str {
    let len = char_len(s);
    let begin = start.map_or(0, |b| clamp_bound(b, len));
    let end = stop.map_or(len, |b| clamp_bound(b, len));
    if begin >= end {
        return "";
    }
    let from = char_to_byte(s, begin).unwrap_or(s.len());
    let to = char_to_byte(s, end).unwrap_or(s.len());
    s.get(from..to).unwrap_or("")
}

/// Code points whose Python 3.14 title case is not their upper case, with that title case
/// (recorded from CPython 3.14.7, Unicode 16.0.0).
const TITLE_EXCEPTIONS: &[(u32, &str)] = &[
    (0xdf, "\u{53}\u{73}"),
    (0x1c4, "\u{1c5}"),
    (0x1c5, "\u{1c5}"),
    (0x1c6, "\u{1c5}"),
    (0x1c7, "\u{1c8}"),
    (0x1c8, "\u{1c8}"),
    (0x1c9, "\u{1c8}"),
    (0x1ca, "\u{1cb}"),
    (0x1cb, "\u{1cb}"),
    (0x1cc, "\u{1cb}"),
    (0x1f1, "\u{1f2}"),
    (0x1f2, "\u{1f2}"),
    (0x1f3, "\u{1f2}"),
    (0x587, "\u{535}\u{582}"),
    (0x1f80, "\u{1f88}"),
    (0x1f81, "\u{1f89}"),
    (0x1f82, "\u{1f8a}"),
    (0x1f83, "\u{1f8b}"),
    (0x1f84, "\u{1f8c}"),
    (0x1f85, "\u{1f8d}"),
    (0x1f86, "\u{1f8e}"),
    (0x1f87, "\u{1f8f}"),
    (0x1f88, "\u{1f88}"),
    (0x1f89, "\u{1f89}"),
    (0x1f8a, "\u{1f8a}"),
    (0x1f8b, "\u{1f8b}"),
    (0x1f8c, "\u{1f8c}"),
    (0x1f8d, "\u{1f8d}"),
    (0x1f8e, "\u{1f8e}"),
    (0x1f8f, "\u{1f8f}"),
    (0x1f90, "\u{1f98}"),
    (0x1f91, "\u{1f99}"),
    (0x1f92, "\u{1f9a}"),
    (0x1f93, "\u{1f9b}"),
    (0x1f94, "\u{1f9c}"),
    (0x1f95, "\u{1f9d}"),
    (0x1f96, "\u{1f9e}"),
    (0x1f97, "\u{1f9f}"),
    (0x1f98, "\u{1f98}"),
    (0x1f99, "\u{1f99}"),
    (0x1f9a, "\u{1f9a}"),
    (0x1f9b, "\u{1f9b}"),
    (0x1f9c, "\u{1f9c}"),
    (0x1f9d, "\u{1f9d}"),
    (0x1f9e, "\u{1f9e}"),
    (0x1f9f, "\u{1f9f}"),
    (0x1fa0, "\u{1fa8}"),
    (0x1fa1, "\u{1fa9}"),
    (0x1fa2, "\u{1faa}"),
    (0x1fa3, "\u{1fab}"),
    (0x1fa4, "\u{1fac}"),
    (0x1fa5, "\u{1fad}"),
    (0x1fa6, "\u{1fae}"),
    (0x1fa7, "\u{1faf}"),
    (0x1fa8, "\u{1fa8}"),
    (0x1fa9, "\u{1fa9}"),
    (0x1faa, "\u{1faa}"),
    (0x1fab, "\u{1fab}"),
    (0x1fac, "\u{1fac}"),
    (0x1fad, "\u{1fad}"),
    (0x1fae, "\u{1fae}"),
    (0x1faf, "\u{1faf}"),
    (0x1fb2, "\u{1fba}\u{345}"),
    (0x1fb3, "\u{1fbc}"),
    (0x1fb4, "\u{386}\u{345}"),
    (0x1fb7, "\u{391}\u{342}\u{345}"),
    (0x1fbc, "\u{1fbc}"),
    (0x1fc2, "\u{1fca}\u{345}"),
    (0x1fc3, "\u{1fcc}"),
    (0x1fc4, "\u{389}\u{345}"),
    (0x1fc7, "\u{397}\u{342}\u{345}"),
    (0x1fcc, "\u{1fcc}"),
    (0x1ff2, "\u{1ffa}\u{345}"),
    (0x1ff3, "\u{1ffc}"),
    (0x1ff4, "\u{38f}\u{345}"),
    (0x1ff7, "\u{3a9}\u{342}\u{345}"),
    (0x1ffc, "\u{1ffc}"),
    (0xfb00, "\u{46}\u{66}"),
    (0xfb01, "\u{46}\u{69}"),
    (0xfb02, "\u{46}\u{6c}"),
    (0xfb03, "\u{46}\u{66}\u{69}"),
    (0xfb04, "\u{46}\u{66}\u{6c}"),
    (0xfb05, "\u{53}\u{74}"),
    (0xfb06, "\u{53}\u{74}"),
    (0xfb13, "\u{544}\u{576}"),
    (0xfb14, "\u{544}\u{565}"),
    (0xfb15, "\u{544}\u{56b}"),
    (0xfb16, "\u{54e}\u{576}"),
    (0xfb17, "\u{544}\u{56d}"),
];

/// Georgian Mkhedruli letters, whose title case is themselves in Python 3.14 although their
/// upper case is Mtavruli.
fn is_georgian_mkhedruli(cp: u32) -> bool {
    matches!(cp, 0x10d0..=0x10fa | 0x10fd..=0x10ff)
}

/// Case pairs that Unicode 17 added and Python 3.14 (Unicode 16) does not map.
fn is_unicode17_case_pair(cp: u32) -> bool {
    matches!(
        cp,
        0xa7ce | 0xa7cf | 0xa7d2..=0xa7d5 | 0x16ea0..=0x16eb8 | 0x16ebb..=0x16ed3
    )
}

fn push_title(out: &mut String, c: char) {
    let cp = c as u32;
    if is_unicode17_case_pair(cp) || is_georgian_mkhedruli(cp) {
        out.push(c);
        return;
    }
    if let Ok(i) = TITLE_EXCEPTIONS.binary_search_by_key(&cp, |&(k, _)| k) {
        if let Some((_, title)) = TITLE_EXCEPTIONS.get(i) {
            out.push_str(title);
            return;
        }
    }
    out.extend(c.to_uppercase());
}

/// Python `str.capitalize()` (3.8 and later): the first character in title case and the rest
/// in lower case, with the final-sigma rule applied in the context of the whole string.
pub fn capitalize(s: &str) -> String {
    let mut chars = s.chars();
    let Some(first) = chars.next() else {
        return String::new();
    };
    let mut out = String::with_capacity(s.len());
    push_title(&mut out, first);
    // Lower-case the whole string so that the final-sigma rule sees the first character, then
    // drop what the first character became.
    let skip = first.to_lowercase().count();
    let lowered = s.to_lowercase();
    let mut original = s.chars().skip(1);
    let mut lowered_chars = lowered.chars().skip(skip).peekable();
    // Walk the original characters so that Unicode 17 case pairs stay unchanged.
    for c in original.by_ref() {
        let n = c.to_lowercase().count();
        if is_unicode17_case_pair(c as u32) {
            for _ in 0..n {
                lowered_chars.next();
            }
            out.push(c);
        } else {
            for _ in 0..n {
                if let Some(l) = lowered_chars.next() {
                    out.push(l);
                }
            }
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    // Expected values recorded from CPython 3.14.7 with `python3 -I -c '...'`.
    #[test]
    fn whitespace_set_is_pythons() {
        let spaces = [
            '\t', '\n', '\u{b}', '\u{c}', '\r', '\u{1c}', '\u{1d}', '\u{1e}', '\u{1f}', ' ',
            '\u{85}', '\u{a0}', '\u{1680}', '\u{2000}', '\u{200a}', '\u{2028}', '\u{2029}',
            '\u{202f}', '\u{205f}', '\u{3000}',
        ];
        for c in spaces {
            assert!(is_space(c), "{:x} is Python whitespace", c as u32);
        }
        for c in ['\u{200b}', '\u{feff}', 'a', '\u{0}', '\u{180e}'] {
            assert!(!is_space(c), "{:x} is not Python whitespace", c as u32);
        }
        assert!(!isspace(""));
        assert!(isspace(" \u{1f}\u{85}"));
    }

    #[test]
    fn strip_and_split_follow_python() {
        assert_eq!(strip("\u{1c} a b \u{3000}", None), "a b");
        assert_eq!(lstrip("  a ", None), "a ");
        assert_eq!(rstrip("  a ", None), "  a");
        assert_eq!(strip("xxaxbxx", Some("x")), "axb");
        assert_eq!(strip("abc", Some("")), "abc");
        assert_eq!(split_whitespace("  a  b c  ", None), vec!["a", "b", "c"]);
        assert_eq!(split_whitespace("  a b  c  ", Some(1)), vec!["a", "b  c  "]);
        assert_eq!(split_whitespace("  a b ", Some(0)), vec!["a b "]);
        assert_eq!(split_whitespace("   ", Some(0)), Vec::<&str>::new());
        assert_eq!(split_whitespace("", None), Vec::<&str>::new());
        assert_eq!(split("a,,b", ",", None), Ok(vec!["a", "", "b"]));
        assert_eq!(split("a,b,c", ",", Some(1)), Ok(vec!["a", "b,c"]));
        assert_eq!(split("", ",", None), Ok(vec![""]));
        assert_eq!(split("abc", "", None), Err(PyStrError::EmptySeparator));
        assert_eq!(PyStrError::EmptySeparator.to_string(), "empty separator");
    }

    #[test]
    fn digits_follow_python() {
        assert!(isdigit("0123456789"));
        assert!(isdigit("\u{b2}\u{2460}\u{ff11}\u{1d7ce}"));
        assert!(!isdigit("\u{bd}"));
        assert!(!isdigit(""));
        assert!(!isdigit("-1"));
        assert!(!isdigit("\u{2469}"));
    }

    #[test]
    fn code_point_indexes() {
        let s = "a\u{e9}\u{1f600}b";
        assert_eq!(char_len(s), 4);
        assert_eq!(char_to_byte(s, 0), Some(0));
        assert_eq!(char_to_byte(s, 2), Some(3));
        assert_eq!(char_to_byte(s, 3), Some(7));
        assert_eq!(char_to_byte(s, 4), Some(8));
        assert_eq!(char_to_byte(s, 5), None);
        assert_eq!(byte_to_char(s, 7), Some(3));
        assert_eq!(byte_to_char(s, 4), None);
        assert_eq!(byte_to_char(s, 99), None);
        assert_eq!(slice(s, Some(1), Some(3)), "\u{e9}\u{1f600}");
        assert_eq!(slice(s, Some(-1), None), "b");
        assert_eq!(slice(s, Some(-99), Some(99)), s);
        assert_eq!(slice(s, None, Some(-3)), "a");
        assert_eq!(slice(s, Some(3), Some(1)), "");
    }

    #[test]
    fn capitalize_follows_python_314() {
        let table: &[(&str, &str)] = &[
            ("hello WORLD", "Hello world"),
            ("", ""),
            ("\u{df}x", "Ssx"),
            ("\u{1c6}A", "\u{1c5}a"),
            ("\u{10d0}\u{10d1}", "\u{10d0}\u{10d1}"),
            ("\u{391}\u{3a3}", "\u{391}\u{3c2}"),
            ("\u{3a3}\u{391}", "\u{3a3}\u{3b1}"),
            ("\u{fb01}x", "Fix"),
            ("1ABC", "1abc"),
            ("\u{130}X", "\u{130}x"),
            ("a\u{a7ce}", "A\u{a7ce}"),
        ];
        for (input, expected) in table {
            assert_eq!(capitalize(input), *expected, "capitalize({input:?})");
        }
    }
}
