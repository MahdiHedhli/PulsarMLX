//! A JSON scanner that refuses duplicate object members at **any** depth,
//! before anything is converted into a map.
//!
//! Why this exists. `serde_json::Value` is a map: by the time a document has
//! become one, `{"dtype":"U8","dtype":"U16"}` has already collapsed to one
//! member and the ambiguity is gone. The outermost level can be recovered with
//! a custom visitor, but nested entries -- a tensor's own object, an
//! `__metadata__` value, a `weight_map` entry, a quantization override -- were
//! still going through `Value`. A document in which one of those keys appears
//! twice has two readings, and the parser silently picked the last. That is
//! the opposite of fail-closed: the input is ambiguous and must be refused,
//! whether or not the surviving occurrence happens to be valid.
//!
//! So every document this project parses is scanned first. The scanner walks
//! the text once, validates the syntax itself, and reports the path of the
//! first duplicated member it finds. Only then is the text handed to
//! `serde_json`.
//!
//! It is deliberately a separate, self-contained pass rather than a
//! deserializer: it has to see the raw member sequence, and keeping it apart
//! from the types means adding a new parsed structure cannot accidentally
//! bypass it.

use std::collections::BTreeSet;

use crate::error::{CatalogError, Result};

/// The largest nesting depth admitted. JSON has no limit; a recursive-descent
/// scanner has a stack, and a deeply nested document is otherwise a way to
/// overflow it. Real headers, indexes and configurations nest three or four
/// levels.
pub const MAX_DEPTH: usize = 64;

struct Scanner<'a> {
    bytes: &'a [u8],
    at: usize,
    label: &'a str,
}

fn invalid(label: &str, at: usize, detail: &str) -> CatalogError {
    CatalogError::InvalidJson {
        shard: label.to_string(),
        detail: format!("at byte {at}: {detail}"),
    }
}

impl<'a> Scanner<'a> {
    fn new(bytes: &'a [u8], label: &'a str) -> Self {
        Self {
            bytes,
            at: 0,
            label,
        }
    }

    fn error(&self, detail: &str) -> CatalogError {
        invalid(self.label, self.at, detail)
    }

    fn peek(&self) -> Option<u8> {
        self.bytes.get(self.at).copied()
    }

    fn bump(&mut self) -> Result<u8> {
        let byte = self
            .peek()
            .ok_or_else(|| self.error("unexpected end of document"))?;
        self.at += 1;
        Ok(byte)
    }

    fn skip_whitespace(&mut self) {
        while let Some(byte) = self.peek() {
            match byte {
                b' ' | b'\t' | b'\n' | b'\r' => self.at += 1,
                _ => break,
            }
        }
    }

    fn expect(&mut self, byte: u8) -> Result<()> {
        self.skip_whitespace();
        if self.peek() != Some(byte) {
            return Err(self.error(&format!("expected {:?}", byte as char)));
        }
        self.at += 1;
        Ok(())
    }

    /// A JSON string, returned with its escapes resolved enough to compare
    /// member names. Escapes are decoded because `"a"` and `"a"` name the
    /// same member and must collide.
    fn string(&mut self) -> Result<String> {
        self.expect(b'"')?;
        let mut out = String::new();
        loop {
            let byte = self.bump()?;
            match byte {
                b'"' => return Ok(out),
                b'\\' => {
                    let escape = self.bump()?;
                    match escape {
                        b'"' => out.push('"'),
                        b'\\' => out.push('\\'),
                        b'/' => out.push('/'),
                        b'b' => out.push('\u{8}'),
                        b'f' => out.push('\u{c}'),
                        b'n' => out.push('\n'),
                        b'r' => out.push('\r'),
                        b't' => out.push('\t'),
                        b'u' => out.push(self.unicode_escape()?),
                        other => {
                            return Err(self.error(&format!("invalid escape \\{}", other as char)))
                        }
                    }
                }
                0x00..=0x1F => return Err(self.error("unescaped control character in a string")),
                _ => {
                    // Collect the raw UTF-8 sequence this byte starts.
                    let start = self.at - 1;
                    let width = utf8_width(byte).ok_or_else(|| self.error("invalid UTF-8"))?;
                    if start + width > self.bytes.len() {
                        return Err(self.error("truncated UTF-8 sequence"));
                    }
                    self.at = start + width;
                    let text = std::str::from_utf8(&self.bytes[start..self.at])
                        .map_err(|_| self.error("invalid UTF-8"))?;
                    out.push_str(text);
                }
            }
        }
    }

    fn unicode_escape(&mut self) -> Result<char> {
        let first = self.hex4()?;
        // Surrogate pairs. A lone surrogate is not a scalar value; it is
        // refused rather than replaced, so that two spellings of one name
        // cannot differ only in how they failed to decode.
        if (0xD800..0xDC00).contains(&first) {
            if self.peek() != Some(b'\\') {
                return Err(self.error("lone high surrogate"));
            }
            self.at += 1;
            if self.bump()? != b'u' {
                return Err(self.error("lone high surrogate"));
            }
            let second = self.hex4()?;
            if !(0xDC00..0xE000).contains(&second) {
                return Err(self.error("invalid surrogate pair"));
            }
            let combined =
                0x1_0000 + ((u32::from(first) - 0xD800) << 10) + (u32::from(second) - 0xDC00);
            return char::from_u32(combined).ok_or_else(|| self.error("invalid surrogate pair"));
        }
        if (0xDC00..0xE000).contains(&first) {
            return Err(self.error("lone low surrogate"));
        }
        char::from_u32(u32::from(first)).ok_or_else(|| self.error("invalid \\u escape"))
    }

    fn hex4(&mut self) -> Result<u16> {
        let mut value: u16 = 0;
        for _ in 0..4 {
            let byte = self.bump()?;
            let digit = match byte {
                b'0'..=b'9' => u16::from(byte - b'0'),
                b'a'..=b'f' => u16::from(byte - b'a') + 10,
                b'A'..=b'F' => u16::from(byte - b'A') + 10,
                _ => return Err(self.error("invalid hexadecimal digit in a \\u escape")),
            };
            value = value * 16 + digit;
        }
        Ok(value)
    }

    fn value(&mut self, depth: usize, path: &str) -> Result<()> {
        if depth > MAX_DEPTH {
            return Err(self.error("document nests deeper than the admitted maximum"));
        }
        self.skip_whitespace();
        match self
            .peek()
            .ok_or_else(|| self.error("unexpected end of document"))?
        {
            b'{' => self.object(depth, path),
            b'[' => self.array(depth, path),
            b'"' => self.string().map(|_| ()),
            b't' => self.literal(b"true"),
            b'f' => self.literal(b"false"),
            b'n' => self.literal(b"null"),
            b'-' | b'0'..=b'9' => self.number(),
            other => Err(self.error(&format!("unexpected {:?}", other as char))),
        }
    }

    fn literal(&mut self, word: &[u8]) -> Result<()> {
        if self.bytes.len() < self.at + word.len()
            || &self.bytes[self.at..self.at + word.len()] != word
        {
            return Err(self.error("invalid literal"));
        }
        self.at += word.len();
        Ok(())
    }

    fn number(&mut self) -> Result<()> {
        let start = self.at;
        if self.peek() == Some(b'-') {
            self.at += 1;
        }
        let integer_start = self.at;
        while matches!(self.peek(), Some(b'0'..=b'9')) {
            self.at += 1;
        }
        if self.at == integer_start {
            return Err(self.error("a number needs at least one digit"));
        }
        if self.bytes[integer_start] == b'0' && self.at - integer_start > 1 {
            return Err(self.error("a number may not have a leading zero"));
        }
        if self.peek() == Some(b'.') {
            self.at += 1;
            let fraction_start = self.at;
            while matches!(self.peek(), Some(b'0'..=b'9')) {
                self.at += 1;
            }
            if self.at == fraction_start {
                return Err(self.error("a fraction needs at least one digit"));
            }
        }
        if matches!(self.peek(), Some(b'e') | Some(b'E')) {
            self.at += 1;
            if matches!(self.peek(), Some(b'+') | Some(b'-')) {
                self.at += 1;
            }
            let exponent_start = self.at;
            while matches!(self.peek(), Some(b'0'..=b'9')) {
                self.at += 1;
            }
            if self.at == exponent_start {
                return Err(self.error("an exponent needs at least one digit"));
            }
        }
        debug_assert!(self.at > start);
        Ok(())
    }

    fn array(&mut self, depth: usize, path: &str) -> Result<()> {
        self.expect(b'[')?;
        self.skip_whitespace();
        if self.peek() == Some(b']') {
            self.at += 1;
            return Ok(());
        }
        let mut index = 0usize;
        loop {
            let child = format!("{path}[{index}]");
            self.value(depth + 1, &child)?;
            self.skip_whitespace();
            match self.bump()? {
                b',' => index += 1,
                b']' => return Ok(()),
                other => {
                    return Err(
                        self.error(&format!("expected , or ] but found {:?}", other as char))
                    )
                }
            }
        }
    }

    fn object(&mut self, depth: usize, path: &str) -> Result<()> {
        self.expect(b'{')?;
        let mut seen: BTreeSet<String> = BTreeSet::new();
        self.skip_whitespace();
        if self.peek() == Some(b'}') {
            self.at += 1;
            return Ok(());
        }
        loop {
            self.skip_whitespace();
            let key = self.string()?;
            let child = if path.is_empty() {
                key.clone()
            } else {
                format!("{path}.{key}")
            };
            if !seen.insert(key.clone()) {
                return Err(CatalogError::DuplicateKey { path: child });
            }
            self.expect(b':')?;
            self.value(depth + 1, &child)?;
            self.skip_whitespace();
            match self.bump()? {
                b',' => continue,
                b'}' => return Ok(()),
                other => {
                    return Err(
                        self.error(&format!("expected , or }} but found {:?}", other as char))
                    )
                }
            }
        }
    }
}

fn utf8_width(byte: u8) -> Option<usize> {
    match byte {
        0x00..=0x7F => Some(1),
        0xC2..=0xDF => Some(2),
        0xE0..=0xEF => Some(3),
        0xF0..=0xF4 => Some(4),
        _ => None,
    }
}

/// Validate a JSON document's syntax and refuse duplicate object members at
/// any depth. `label` names the document in any refusal.
///
/// Run this **before** handing the text to a deserializer. The path in a
/// [`CatalogError::DuplicateKey`] is dotted from the document root, with array
/// elements written `[n]`.
pub fn reject_duplicate_keys(bytes: &[u8], label: &str) -> Result<()> {
    let mut scanner = Scanner::new(bytes, label);
    scanner.value(0, "")?;
    scanner.skip_whitespace();
    if scanner.at != bytes.len() {
        return Err(invalid(
            label,
            scanner.at,
            "trailing bytes after the document",
        ));
    }
    Ok(())
}

/// [`reject_duplicate_keys`] for text.
pub fn reject_duplicate_keys_str(text: &str, label: &str) -> Result<()> {
    reject_duplicate_keys(text.as_bytes(), label)
}

#[cfg(test)]
mod tests {
    use super::{reject_duplicate_keys_str, MAX_DEPTH};
    use crate::error::CatalogError;

    fn duplicate_path(text: &str) -> String {
        match reject_duplicate_keys_str(text, "doc") {
            Err(CatalogError::DuplicateKey { path }) => path,
            other => panic!("expected a duplicate-key refusal, got {other:?}"),
        }
    }

    #[test]
    fn a_duplicate_at_the_top_level_is_refused() {
        assert_eq!(duplicate_path(r#"{"a":1,"a":2}"#), "a");
    }

    #[test]
    fn a_duplicate_inside_a_nested_object_is_refused() {
        assert_eq!(
            duplicate_path(r#"{"t":{"dtype":"U8","dtype":"U16"}}"#),
            "t.dtype"
        );
    }

    #[test]
    fn a_duplicate_inside_an_array_element_is_refused() {
        assert_eq!(duplicate_path(r#"{"a":[{"b":1,"b":2}]}"#), "a[0].b");
    }

    #[test]
    fn escaped_and_plain_spellings_of_one_name_collide() {
        // "a" and "a" are the same member.
        assert_eq!(duplicate_path(r#"{"a":1,"a":2}"#), "a");
    }

    #[test]
    fn well_formed_documents_pass() {
        for text in [
            r#"{}"#,
            r#"[]"#,
            r#"{"a":1,"b":{"a":2}}"#,
            r#"{"a":[1,2,{"b":3}],"c":null}"#,
            r#"{"n":-1.5e-3,"t":true,"f":false}"#,
            r#"  {"a" : "x"}  "#,
            r#"{"unicode":"é😀"}"#,
        ] {
            reject_duplicate_keys_str(text, "doc").unwrap_or_else(|e| panic!("{text}: {e}"));
        }
    }

    #[test]
    fn malformed_documents_are_refused_as_invalid_json() {
        for text in [
            r#"{"a":}"#,
            r#"{"a" 1}"#,
            r#"{"a":1,}"#,
            r#"{"a":01}"#,
            r#"{"a":1} trailing"#,
            r#"{"a":"unterminated"#,
            r#"{"a":tru}"#,
            "{\"a\":\"\u{1}\"}",
        ] {
            assert!(
                matches!(
                    reject_duplicate_keys_str(text, "doc"),
                    Err(CatalogError::InvalidJson { .. })
                ),
                "{text} must be refused"
            );
        }
    }

    #[test]
    fn nesting_is_bounded() {
        let deep = format!(
            "{}1{}",
            "[".repeat(MAX_DEPTH + 4),
            "]".repeat(MAX_DEPTH + 4)
        );
        assert!(matches!(
            reject_duplicate_keys_str(&deep, "doc"),
            Err(CatalogError::InvalidJson { .. })
        ));
        let shallow = format!("{}1{}", "[".repeat(8), "]".repeat(8));
        reject_duplicate_keys_str(&shallow, "doc").unwrap();
    }
}
