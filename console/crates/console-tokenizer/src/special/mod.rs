//! Owned by PRM-04. Special literals (token types 3 and 4) and plain-span matching.
//!
//! A special literal is matched in the raw text, before the byte mapping, and emitted as its
//! single id; the text between two literals is encoded as ordinary text. GGUF token type 4
//! (USER_DEFINED, such as `<think>`) is matched always; type 3 (CONTROL, such as
//! `<|im_end|>`) only when the caller asks for special parsing. Literals are tried longest
//! first (by code points, ties in vocabulary order), and the leftmost match wins.
//!
//! A plain span is a `(start, end)` range of the text that is ordinary text even where it
//! spells a literal, such as a `</think>` quoted inside a message. A literal match that
//! starts inside a plain span is not emitted; it is encoded with the text around it. Spans
//! are byte offsets into the text here, where the donor uses code-point indexes; the caller
//! computes them on the same Rust string, so the same spans select the same matches.
//!
//! Behavior reference: project-maya tools/strata_tokenizer.py:171-198 and 317-359 at 7e68a30f.

use std::collections::HashMap;

use crate::bpe::TokenizerError;

/// The compiled alternation may grow large for a vocabulary with many literals; this is the
/// size budget handed to the `regex` crate (its default is 10 MiB).
const LITERAL_REGEX_SIZE_LIMIT: usize = 256 * 1024 * 1024;

/// The special literals of a tokenizer and their ids, in insertion order, as the donor's
/// `special_tokens` dictionary.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct SpecialTokens {
    entries: Vec<(String, u32)>,
    index: HashMap<String, usize>,
}

impl SpecialTokens {
    /// An empty table.
    pub fn new() -> Self {
        Self::default()
    }

    /// Inserts a literal. As in a Python `dict`, a literal already present keeps its position
    /// and takes the new id.
    pub fn insert(&mut self, literal: &str, id: u32) {
        if let Some(&at) = self.index.get(literal) {
            if let Some(entry) = self.entries.get_mut(at) {
                entry.1 = id;
            }
            return;
        }
        self.index.insert(literal.to_owned(), self.entries.len());
        self.entries.push((literal.to_owned(), id));
    }

    /// The id of `literal`, if it is a special literal.
    pub fn get(&self, literal: &str) -> Option<u32> {
        let at = *self.index.get(literal)?;
        self.entries.get(at).map(|e| e.1)
    }

    /// Whether `literal` is a special literal.
    pub fn contains(&self, literal: &str) -> bool {
        self.index.contains_key(literal)
    }

    /// The number of literals.
    pub fn len(&self) -> usize {
        self.entries.len()
    }

    /// Whether there are no literals.
    pub fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }

    /// The literals and their ids in insertion order.
    pub fn iter(&self) -> impl Iterator<Item = (&str, u32)> {
        self.entries.iter().map(|(s, i)| (s.as_str(), *i))
    }
}

/// A leftmost, longest-literal-first matcher over a set of literals (the donor's `_alt`).
#[derive(Debug, Clone)]
pub struct LiteralMatcher {
    /// The non-empty literals, longest first, as one alternation.
    any: Option<regex::Regex>,
    /// The same alternation anchored at the start, used only when `has_empty` is set.
    anchored: Option<regex::Regex>,
    /// Whether the empty string is one of the literals (it then matches wherever no other
    /// literal does, as in Python's `finditer`).
    has_empty: bool,
}

impl LiteralMatcher {
    /// Builds the matcher for `literals`, or `None` when there are none (the donor's `None`
    /// pattern, which makes the whole text one segment).
    pub fn new<'a, I>(literals: I) -> Result<Option<Self>, TokenizerError>
    where
        I: IntoIterator<Item = &'a str>,
    {
        let mut sorted: Vec<&str> = literals.into_iter().collect();
        if sorted.is_empty() {
            return Ok(None);
        }
        // A stable sort by code-point length, longest first: equal lengths keep their order.
        sorted.sort_by_key(|s| std::cmp::Reverse(s.chars().count()));
        let has_empty = sorted.iter().any(|s| s.is_empty());
        let alternation: Vec<String> = sorted
            .iter()
            .filter(|s| !s.is_empty())
            .map(|s| regex::escape(s))
            .collect();
        if alternation.is_empty() {
            return Ok(Some(Self {
                any: None,
                anchored: None,
                has_empty,
            }));
        }
        let joined = alternation.join("|");
        let build = |pattern: &str| {
            regex::RegexBuilder::new(pattern)
                .size_limit(LITERAL_REGEX_SIZE_LIMIT)
                .build()
                .map_err(|e| TokenizerError::Regex(e.to_string()))
        };
        let any = build(&joined)?;
        let anchored = if has_empty {
            Some(build(&format!(r"\A(?:{joined})"))?)
        } else {
            None
        };
        Ok(Some(Self {
            any: Some(any),
            anchored,
            has_empty,
        }))
    }

    /// The matches in `text` as byte ranges, in the order and with the empty-match rules of
    /// Python's `finditer`.
    pub fn find_all(&self, text: &str) -> Vec<(usize, usize)> {
        if !self.has_empty {
            return match &self.any {
                Some(re) => re.find_iter(text).map(|m| (m.start(), m.end())).collect(),
                None => Vec::new(),
            };
        }
        // With the empty literal, every character boundary not inside a non-empty match
        // yields a match: the non-empty literal starting there if any, else the empty one.
        let mut out = Vec::new();
        let mut pos = 0usize;
        loop {
            let hit = self
                .anchored
                .as_ref()
                .and_then(|re| text.get(pos..).and_then(|rest| re.find(rest)));
            match hit {
                Some(m) if m.end() > 0 => {
                    out.push((pos, pos + m.end()));
                    pos += m.end();
                    continue;
                }
                _ => out.push((pos, pos)),
            }
            match text.get(pos..).and_then(|rest| rest.chars().next()) {
                Some(c) => pos += c.len_utf8(),
                None => break,
            }
        }
        out
    }
}

/// Encodes `text`, emitting each literal match as its id and encoding the rest with
/// `segment`; a match that starts inside one of the `plain` spans is left to the text around
/// it. Without a matcher, the whole text is one segment.
///
/// Behavior reference: project-maya tools/strata_tokenizer.py:317-349 at 7e68a30f.
pub fn encode_matching<F>(
    text: &str,
    matcher: Option<&LiteralMatcher>,
    plain: &[(usize, usize)],
    specials: &SpecialTokens,
    mut segment: F,
) -> Result<Vec<u32>, TokenizerError>
where
    F: FnMut(&str) -> Result<Vec<u32>, TokenizerError>,
{
    let Some(matcher) = matcher else {
        return segment(text);
    };
    let mut spans = plain.to_vec();
    spans.sort_unstable();
    let mut upcoming = spans.into_iter().peekable();
    let mut plain_end = 0usize;
    let mut out = Vec::new();
    let mut pos = 0usize;
    for (start, end) in matcher.find_all(text) {
        // Matches come in text order, so each span is consumed once.
        while let Some(&(span_start, span_end)) = upcoming.peek() {
            if span_start > start {
                break;
            }
            plain_end = plain_end.max(span_end);
            upcoming.next();
        }
        if start < plain_end {
            continue;
        }
        if start > pos {
            out.extend(segment(text.get(pos..start).unwrap_or_default())?);
        }
        let literal = text.get(start..end).unwrap_or_default();
        let id = specials
            .get(literal)
            .ok_or_else(|| TokenizerError::Key(literal.to_owned()))?;
        out.push(id);
        pos = end;
    }
    if pos < text.len() {
        out.extend(segment(text.get(pos..).unwrap_or_default())?);
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn matcher(lits: &[&str]) -> LiteralMatcher {
        LiteralMatcher::new(lits.iter().copied())
            .expect("builds")
            .expect("not empty")
    }

    #[test]
    fn longest_literal_first() {
        let m = matcher(&["<|im", "<|im_end|>", "<"]);
        assert_eq!(
            m.find_all("a<|im_end|>b<|imx<"),
            [(1, 11), (12, 16), (17, 18)]
        );
    }

    #[test]
    fn metacharacters_are_literal() {
        let m = matcher(&["[(x)]", "a.b"]);
        assert_eq!(m.find_all("axb a.b [(x)]"), [(4, 7), (8, 13)]);
    }

    #[test]
    fn no_literals_is_none() {
        assert!(LiteralMatcher::new(std::iter::empty())
            .expect("ok")
            .is_none());
    }

    #[test]
    fn empty_literal_follows_finditer() {
        // Python: [(m.start(), m.end()) for m in regex.finditer("ab|", "xaby")]
        // is [(0, 0), (1, 3), (3, 3), (4, 4)].
        let m = matcher(&["", "ab"]);
        assert_eq!(m.find_all("xaby"), [(0, 0), (1, 3), (3, 3), (4, 4)]);
        let only_empty = matcher(&[""]);
        assert_eq!(only_empty.find_all("\u{e9}a"), [(0, 0), (2, 2), (3, 3)]);
    }

    #[test]
    fn insertion_order_and_update() {
        let mut t = SpecialTokens::new();
        t.insert("b", 2);
        t.insert("a", 1);
        t.insert("b", 5);
        assert_eq!(t.iter().collect::<Vec<_>>(), [("b", 5), ("a", 1)]);
        assert_eq!(t.get("b"), Some(5));
        assert!(t.contains("a"));
        assert_eq!(t.len(), 2);
        assert!(!t.is_empty());
    }

    #[test]
    fn spans_skip_matches_that_start_inside_them() {
        let mut specials = SpecialTokens::new();
        specials.insert("<x>", 100);
        let m = matcher(&["<x>"]);
        let seg = |s: &str| Ok(s.bytes().map(u32::from).collect());
        let all = encode_matching("<x>a<x>", Some(&m), &[], &specials, seg).expect("ok");
        assert_eq!(all, [100, 97, 100]);
        let some = encode_matching("<x>a<x>", Some(&m), &[(4, 5)], &specials, seg).expect("ok");
        assert_eq!(some, [100, 97, 60, 120, 62]);
        // A literal that starts inside a span and ends after it is still text.
        let straddle = encode_matching("a<x>", Some(&m), &[(0, 2)], &specials, seg).expect("ok");
        assert_eq!(straddle, [97, 60, 120, 62]);
        let after = encode_matching("a<x>", Some(&m), &[(0, 1)], &specials, seg).expect("ok");
        assert_eq!(after, [97, 100]);
    }
}
