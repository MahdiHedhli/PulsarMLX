//! The `file-name` and `log-text` patterns of `contracts/volatile-fields.json`.
//!
//! A pattern is literal text with holes. Each hole has a fixed character class, so a
//! pattern never matches more than the volatile value it names:
//!
//! | Hole | Matches |
//! | --- | --- |
//! | `<host>` | one or more characters other than white space and `/` |
//! | `<port>` | one to five decimal digits |
//! | `<pid>` | one to ten decimal digits |
//! | `<hex>` | one or more lower-case hex digits |
//! | `<hexN>` | exactly N lower-case hex digits, for example `<hex12>` |
//! | `<rand>` | exactly eight characters of `a-z`, `0-9` and `_` (Python `tempfile` names) |
//! | `<num>` | one to 32 decimal digits and dots: a figure as Python's `{x:.0f}` or `{x:.1f}` writes it (log-text only; the value is then checked as a non-negative number) |
//!
//! Any other hole is refused when the normalizer is built, so a list entry the normalizer
//! cannot apply is an error rather than a silent no-op.

/// The longest text a pattern is matched against; longer text never matches and is
/// compared exactly.
pub const MAX_PATTERN_TEXT: usize = 4096;

/// A hole's character class.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum Hole {
    Host,
    Port,
    Pid,
    Hex(Option<usize>),
    Rand,
    Num,
}

/// One piece of a pattern.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum Piece {
    Literal(String),
    Hole(Hole),
}

/// A compiled pattern.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct Pattern {
    pub(crate) pieces: Vec<Piece>,
}

/// Where a hole matched.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct Capture {
    pub(crate) hole: Hole,
    /// Index of the hole's piece in [`Pattern::pieces`].
    pub(crate) piece: usize,
    pub(crate) start: usize,
    pub(crate) end: usize,
}

impl Pattern {
    /// Compiles `text`; `Err` names the first unknown or malformed hole.
    pub(crate) fn compile(text: &str) -> Result<Self, String> {
        let mut pieces = Vec::new();
        let mut rest = text;
        while let Some(open) = rest.find('<') {
            if open > 0 {
                pieces.push(Piece::Literal(
                    rest.get(..open).unwrap_or_default().to_string(),
                ));
            }
            let after = rest.get(open + 1..).unwrap_or_default();
            let close = after
                .find('>')
                .ok_or_else(|| format!("an unclosed hole in {text:?}"))?;
            let name = after.get(..close).unwrap_or_default();
            let hole = match name {
                "host" => Hole::Host,
                "port" => Hole::Port,
                "pid" => Hole::Pid,
                "rand" => Hole::Rand,
                "num" => Hole::Num,
                "hex" => Hole::Hex(None),
                _ => match name
                    .strip_prefix("hex")
                    .and_then(|n| n.parse::<usize>().ok())
                {
                    Some(n) if (1..=64).contains(&n) => Hole::Hex(Some(n)),
                    _ => return Err(format!("unknown hole <{name}> in {text:?}")),
                },
            };
            if matches!(pieces.last(), Some(Piece::Hole(_))) {
                return Err(format!(
                    "two holes without literal text between them in {text:?}"
                ));
            }
            pieces.push(Piece::Hole(hole));
            rest = after.get(close + 1..).unwrap_or_default();
        }
        if !rest.is_empty() {
            pieces.push(Piece::Literal(rest.to_string()));
        }
        if !matches!(pieces.first(), Some(Piece::Literal(_))) {
            return Err(format!("a pattern starts with literal text: {text:?}"));
        }
        Ok(Self { pieces })
    }

    /// The literal text before the first hole.
    pub(crate) fn lead(&self) -> &str {
        match self.pieces.first() {
            Some(Piece::Literal(s)) => s,
            _ => "",
        }
    }

    /// Matches the whole of `text`.
    pub(crate) fn match_whole(&self, text: &str) -> Option<Vec<Capture>> {
        if text.len() > MAX_PATTERN_TEXT {
            return None;
        }
        let mut caps = Vec::new();
        let end = self.match_at(text.as_bytes(), 0, 0, &mut caps)?;
        (end == text.len()).then_some(caps)
    }

    /// Every non-overlapping match inside `text`, left to right, each as its byte range
    /// and captures.
    pub(crate) fn find_all(&self, text: &str) -> Vec<((usize, usize), Vec<Capture>)> {
        let mut found = Vec::new();
        if text.len() > MAX_PATTERN_TEXT || self.lead().is_empty() {
            return found;
        }
        let b = text.as_bytes();
        let mut from = 0;
        while let Some(off) = text.get(from..).and_then(|t| t.find(self.lead())) {
            let start = from + off;
            let mut caps = Vec::new();
            match self.match_at(b, 0, start, &mut caps) {
                Some(end) if end > start => {
                    found.push(((start, end), caps));
                    from = end;
                }
                _ => from = start + 1,
            }
            while from < text.len() && !text.is_char_boundary(from) {
                from += 1;
            }
        }
        found
    }

    /// Matches pieces from `piece` on at byte `at`; greedy holes back off one byte at a
    /// time. Returns the end of the match.
    fn match_at(
        &self,
        b: &[u8],
        piece: usize,
        at: usize,
        caps: &mut Vec<Capture>,
    ) -> Option<usize> {
        let Some(p) = self.pieces.get(piece) else {
            return Some(at);
        };
        match p {
            Piece::Literal(lit) => {
                let end = at.checked_add(lit.len())?;
                if b.get(at..end)? == lit.as_bytes() {
                    self.match_at(b, piece + 1, end, caps)
                } else {
                    None
                }
            }
            Piece::Hole(hole) => {
                let (min, max) = hole.lengths();
                let mut run = 0;
                while run < max && b.get(at + run).is_some_and(|&c| hole.allows(c)) {
                    run += 1;
                }
                let mut len = run;
                while len >= min {
                    let mark = caps.len();
                    caps.push(Capture {
                        hole: *hole,
                        piece,
                        start: at,
                        end: at + len,
                    });
                    if let Some(end) = self.match_at(b, piece + 1, at + len, caps) {
                        return Some(end);
                    }
                    caps.truncate(mark);
                    if len == 0 {
                        break;
                    }
                    len -= 1;
                }
                None
            }
        }
    }
}

impl Hole {
    fn lengths(self) -> (usize, usize) {
        match self {
            Hole::Host | Hole::Hex(None) => (1, MAX_PATTERN_TEXT),
            Hole::Port => (1, 5),
            Hole::Pid => (1, 10),
            Hole::Hex(Some(n)) => (n, n),
            Hole::Rand => (8, 8),
            Hole::Num => (1, 32),
        }
    }

    fn allows(self, c: u8) -> bool {
        match self {
            Hole::Host => !c.is_ascii_whitespace() && c != b'/' && c != 0,
            Hole::Port | Hole::Pid => c.is_ascii_digit(),
            Hole::Hex(_) => c.is_ascii_digit() || (b'a'..=b'f').contains(&c),
            Hole::Rand => c.is_ascii_lowercase() || c.is_ascii_digit() || c == b'_',
            Hole::Num => c.is_ascii_digit() || c == b'.',
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn pat(s: &str) -> Pattern {
        Pattern::compile(s).unwrap_or_else(|e| panic!("{e}"))
    }

    #[test]
    fn holes_are_closed_classes() {
        for bad in [
            "a<name>",
            "a<hex0>",
            "a<hex65>",
            "<pid>.json",
            "a<pid><hex>",
            "a<pid",
        ] {
            assert!(Pattern::compile(bad).is_err(), "{bad}");
        }
        let p = pat("req-<hex12>.dsi");
        assert!(p.match_whole("req-0123456789ab.dsi").is_some());
        assert!(p.match_whole("req-0123456789AB.dsi").is_none());
        assert!(p.match_whole("req-0123456789abc.dsi").is_none());
        assert!(pat("kept-<pid>.json").match_whole("kept-.json").is_none());
    }

    #[test]
    fn find_all_backs_off_greedy_holes() {
        let p = pat("ready: http://<host>:<port>/v1");
        let line = "ready: http://[::1]:43210/v1  (OpenAI: ...)";
        let found = p.find_all(line);
        assert_eq!(found.len(), 1);
        let caps = &found[0].1;
        assert_eq!(line.get(caps[0].start..caps[0].end), Some("[::1]"));
        assert_eq!(line.get(caps[1].start..caps[1].end), Some("43210"));
        assert!(p.find_all("ready: http://h:123456/v1").is_empty());
        let r = pat("maya-vision-<rand>");
        assert_eq!(
            r.find_all("/t/maya-vision-ab_12cd3 and /t/maya-vision-x")
                .len(),
            1
        );
        let n = pat("tokens in <num> s (<num> tok/s)");
        let line = "[maya] done: 12 tokens in 3 s (4.5 tok/s) (stop, cancel=False)";
        let found = n.find_all(line);
        assert_eq!(found.len(), 1);
        let caps = &found[0].1;
        assert_eq!(line.get(caps[0].start..caps[0].end), Some("3"));
        assert_eq!(line.get(caps[1].start..caps[1].end), Some("4.5"));
        assert!(n.find_all("12 tokens in x s (4.5 tok/s)").is_empty());
    }
}
