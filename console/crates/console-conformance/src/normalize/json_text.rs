//! A strict JSON scanner that keeps the byte span of every string and number token.
//!
//! The normalizer edits JSON text in place: it replaces the exact bytes of a volatile
//! token and leaves every other byte (white space, separators, key order, escapes) as
//! the server sent it, then parses the edited text again with `serde_json`. That keeps
//! the text form and the parsed form of a body consistent by construction, and it never
//! hides a formatting difference.
//!
//! The grammar is RFC 8259, as `serde_json` reads it: no `NaN`, no comments, no trailing
//! commas, no lone surrogates. A document this scanner refuses is left unnormalized and
//! is compared byte for byte.

/// The deepest nesting the scanner follows; a deeper document is left unnormalized.
pub const MAX_DEPTH: usize = 256;

/// One scanned value.
#[derive(Debug, Clone, PartialEq)]
pub(crate) enum Node {
    /// `null`, `true` or `false`.
    Literal,
    /// A number token; `span` is its exact bytes.
    Number { span: (usize, usize) },
    /// A string token. `span` covers the quotes; `plain` is true when the bytes between
    /// the quotes hold no backslash, so they equal the decoded value.
    String {
        value: String,
        span: (usize, usize),
        plain: bool,
    },
    /// An array, elements in order.
    Array(Vec<Node>),
    /// An object, members in document order (duplicates kept).
    Object(Vec<(String, Node)>),
}

/// Scans `text` as one JSON document. `None` when it is not strict JSON or nests deeper
/// than [`MAX_DEPTH`].
pub(crate) fn scan(text: &str) -> Option<Node> {
    let mut s = Scanner {
        b: text.as_bytes(),
        i: 0,
    };
    s.ws();
    let node = s.value(0)?;
    s.ws();
    (s.i == s.b.len()).then_some(node)
}

struct Scanner<'a> {
    b: &'a [u8],
    i: usize,
}

impl Scanner<'_> {
    fn peek(&self) -> Option<u8> {
        self.b.get(self.i).copied()
    }

    fn ws(&mut self) {
        while matches!(self.peek(), Some(b' ' | b'\t' | b'\n' | b'\r')) {
            self.i += 1;
        }
    }

    fn eat(&mut self, lit: &[u8]) -> Option<()> {
        let end = self.i.checked_add(lit.len())?;
        (self.b.get(self.i..end)? == lit).then(|| self.i = end)
    }

    fn value(&mut self, depth: usize) -> Option<Node> {
        match self.peek()? {
            b'{' => self.object(depth + 1),
            b'[' => self.array(depth + 1),
            b'"' => self.string(),
            b't' => self.eat(b"true").map(|()| Node::Literal),
            b'f' => self.eat(b"false").map(|()| Node::Literal),
            b'n' => self.eat(b"null").map(|()| Node::Literal),
            b'-' | b'0'..=b'9' => self.number(),
            _ => None,
        }
    }

    fn object(&mut self, depth: usize) -> Option<Node> {
        if depth > MAX_DEPTH {
            return None;
        }
        self.i += 1;
        let mut members = Vec::new();
        self.ws();
        if self.peek()? == b'}' {
            self.i += 1;
            return Some(Node::Object(members));
        }
        loop {
            self.ws();
            let Node::String { value: key, .. } = self.string()? else {
                return None;
            };
            self.ws();
            self.eat(b":")?;
            self.ws();
            let v = self.value(depth)?;
            members.push((key, v));
            self.ws();
            match self.peek()? {
                b',' => self.i += 1,
                b'}' => {
                    self.i += 1;
                    return Some(Node::Object(members));
                }
                _ => return None,
            }
        }
    }

    fn array(&mut self, depth: usize) -> Option<Node> {
        if depth > MAX_DEPTH {
            return None;
        }
        self.i += 1;
        let mut items = Vec::new();
        self.ws();
        if self.peek()? == b']' {
            self.i += 1;
            return Some(Node::Array(items));
        }
        loop {
            self.ws();
            items.push(self.value(depth)?);
            self.ws();
            match self.peek()? {
                b',' => self.i += 1,
                b']' => {
                    self.i += 1;
                    return Some(Node::Array(items));
                }
                _ => return None,
            }
        }
    }

    fn digits(&mut self) -> usize {
        let start = self.i;
        while matches!(self.peek(), Some(b'0'..=b'9')) {
            self.i += 1;
        }
        self.i - start
    }

    fn number(&mut self) -> Option<Node> {
        let start = self.i;
        if self.peek() == Some(b'-') {
            self.i += 1;
        }
        match self.peek()? {
            b'0' => self.i += 1,
            b'1'..=b'9' => {
                self.digits();
            }
            _ => return None,
        }
        if self.peek() == Some(b'.') {
            self.i += 1;
            if self.digits() == 0 {
                return None;
            }
        }
        if matches!(self.peek(), Some(b'e' | b'E')) {
            self.i += 1;
            if matches!(self.peek(), Some(b'+' | b'-')) {
                self.i += 1;
            }
            if self.digits() == 0 {
                return None;
            }
        }
        Some(Node::Number {
            span: (start, self.i),
        })
    }

    fn hex4(&mut self) -> Option<u32> {
        let end = self.i.checked_add(4)?;
        let digits = std::str::from_utf8(self.b.get(self.i..end)?).ok()?;
        if !digits.bytes().all(|c| c.is_ascii_hexdigit()) {
            return None;
        }
        self.i = end;
        u32::from_str_radix(digits, 16).ok()
    }

    fn string(&mut self) -> Option<Node> {
        let start = self.i;
        if self.peek()? != b'"' {
            return None;
        }
        self.i += 1;
        let mut value = String::new();
        let mut plain = true;
        loop {
            let run_start = self.i;
            while let Some(c) = self.peek() {
                if c == b'"' || c == b'\\' || c < 0x20 {
                    break;
                }
                self.i += 1;
            }
            value.push_str(std::str::from_utf8(self.b.get(run_start..self.i)?).ok()?);
            match self.peek()? {
                b'"' => {
                    self.i += 1;
                    return Some(Node::String {
                        value,
                        span: (start, self.i),
                        plain,
                    });
                }
                b'\\' => {
                    plain = false;
                    self.i += 1;
                    let c = self.peek()?;
                    self.i += 1;
                    match c {
                        b'"' => value.push('"'),
                        b'\\' => value.push('\\'),
                        b'/' => value.push('/'),
                        b'b' => value.push('\u{8}'),
                        b'f' => value.push('\u{c}'),
                        b'n' => value.push('\n'),
                        b'r' => value.push('\r'),
                        b't' => value.push('\t'),
                        b'u' => {
                            let hi = self.hex4()?;
                            let code = if (0xD800..0xDC00).contains(&hi) {
                                self.eat(b"\\u")?;
                                let lo = self.hex4()?;
                                if !(0xDC00..0xE000).contains(&lo) {
                                    return None;
                                }
                                0x10000 + ((hi - 0xD800) << 10) + (lo - 0xDC00)
                            } else if (0xDC00..0xE000).contains(&hi) {
                                return None;
                            } else {
                                hi
                            };
                            value.push(char::from_u32(code)?);
                        }
                        _ => return None,
                    }
                }
                _ => return None,
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn spans(n: &Node, text: &str, out: &mut Vec<String>) {
        match n {
            Node::Number { span } | Node::String { span, .. } => {
                out.push(text.get(span.0..span.1).unwrap_or("?").to_string());
            }
            Node::Array(items) => items.iter().for_each(|i| spans(i, text, out)),
            Node::Object(m) => m.iter().for_each(|(_, v)| spans(v, text, out)),
            Node::Literal => {}
        }
    }

    #[test]
    fn spans_cover_the_exact_tokens() {
        let text = r#" {"a": [1, -2.5e3, "x\u00e9"], "b": {"c": "plain"}, "d": null} "#;
        let node = scan(text);
        let mut out = Vec::new();
        if let Some(n) = &node {
            spans(n, text, &mut out);
        }
        assert_eq!(out, ["1", "-2.5e3", r#""x\u00e9""#, r#""plain""#]);
        match node {
            Some(Node::Object(m)) => {
                assert_eq!(m.len(), 3);
                assert!(matches!(&m[0].1, Node::Array(a) if matches!(&a[2],
                    Node::String { value, plain: false, .. } if value == "x\u{e9}")));
            }
            other => panic!("{other:?}"),
        }
    }

    #[test]
    fn strict_grammar() {
        for bad in [
            "",
            "01",
            "1.",
            ".5",
            "-",
            "1e",
            "[1,]",
            "{\"a\":1,}",
            "NaN",
            "\"\\x\"",
            "\"a\nb\"",
            "\"\\ud800\"",
            "\"\\udc00\"",
            "{1: 2}",
            "[1] [2]",
            "tru",
        ] {
            assert!(scan(bad).is_none(), "{bad:?}");
        }
        for good in [
            "0",
            "-0.0",
            "1E+2",
            "\"\\ud83d\\ude00\"",
            "[]",
            "{}",
            " true ",
        ] {
            assert!(scan(good).is_some(), "{good:?}");
        }
    }

    #[test]
    fn depth_is_bounded() {
        let ok = format!("{}{}", "[".repeat(MAX_DEPTH), "]".repeat(MAX_DEPTH));
        assert!(scan(&ok).is_some());
        let deep = format!("{}{}", "[".repeat(MAX_DEPTH + 1), "]".repeat(MAX_DEPTH + 1));
        assert!(scan(&deep).is_none());
    }
}
