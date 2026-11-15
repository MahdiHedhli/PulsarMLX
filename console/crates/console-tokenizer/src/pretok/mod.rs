//! Owned by PRM-04. The pre-tokenizer patterns of the four supported families.
//!
//! A pre-tokenizer splits plain text into pieces before the byte mapping and BPE. The
//! patterns below are the donor's text verbatim; the donor transcribed them from llama.cpp's
//! `src/llama-vocab.cpp` (MIT License, copyright the ggml authors; license text in
//! `console/LICENSES/llama.cpp-MIT.txt`) and from the model families' `tokenizer.json`.
//!
//! - `qwen35`: letters are `[\p{L}\p{M}]`, digits one per piece.
//! - `glm4` and `glm5`: digits in runs of at most three, no `\p{M}` anywhere, and
//!   `ignore_merges` (see [`PreScheme::ignore_merges`]).
//! - `deepseek3`: three "Isolated" split stages applied in turn, where the text between two
//!   matches of a stage stays a piece of its own.
//! - `minimax`: GPT-4o's (o200k) pattern, applied after NFC normalization of each plain
//!   segment (the normalization is done by the caller, see `bpe`).
//!
//! Every pattern ends in the two whitespace branches `\s+(?!\S)|\s+`. Those two are applied
//! by hand (see [`PreTokenizer::findall`]); the rest of each pattern runs on the `regex`
//! crate, which needs no look-around for it and matches in linear time with no backtracking
//! stack. A backtracking engine overflows its stack on a whitespace run of about a million
//! characters, which the donor's `regex` module splits without error. The split equals the
//! whole pattern's (a unit test checks it against `fancy-regex` running the donor's text).
//! Matching uses Rust's Unicode tables. Where those tables differ from Python's `regex`
//! module, the difference is pinned by a named test in `tests/prm04_unicode_tables.rs` (lead
//! decision LD24):
//!
//! - `\s` is Unicode `White_Space`, which does not include U+001C to U+001F (Python's
//!   `str.isspace` does; the `regex` module's `\s` for a `str` pattern is believed to follow
//!   `White_Space`, as here).
//! - The general categories come from Unicode 16.0.0 (`regex-syntax` 0.8.11); the donor's
//!   `regex` module is unpinned and carries the tables of whatever version is installed.
//!
//! Behavior reference: project-maya tools/strata_tokenizer.py:46-134 and 140-148 at 7e68a30f.

use crate::bpe::{py_repr, TokenizerError};

/// The `qwen35` pattern (llama.cpp `LLAMA_VOCAB_PRE_TYPE_QWEN35`), as the donor writes it.
pub const QWEN35_PATTERN: &str = concat!(
    r"(?:'[sS]|'[tT]|'[rR][eE]|'[vV][eE]|'[mM]|'[lL][lL]|'[dD])",
    r"|[^\r\n\p{L}\p{N}]?[\p{L}\p{M}]+",
    r"|\p{N}",
    r"| ?[^\s\p{L}\p{M}\p{N}]+[\r\n]*",
    r"|\s*[\r\n]+",
    r"|\s+(?!\S)",
    r"|\s+",
);

/// The `glm4`/`glm5` pattern (llama.cpp `LLAMA_VOCAB_PRE_TYPE_CHATGLM4`), as the donor writes
/// it.
pub const GLM_PATTERN: &str = concat!(
    r"(?:'[sS]|'[tT]|'[rR][eE]|'[vV][eE]|'[mM]|'[lL][lL]|'[dD])",
    r"|[^\r\n\p{L}\p{N}]?\p{L}+",
    r"|\p{N}{1,3}",
    r"| ?[^\s\p{L}\p{N}]+[\r\n]*",
    r"|\s*[\r\n]+",
    r"|\s+(?!\S)",
    r"|\s+",
);

/// The three "Isolated" split stages of `deepseek3`, in order, as the donor writes them.
pub const DEEPSEEK3_PATTERNS: [&str; 3] = [
    r"\p{N}{1,3}",
    r"[\u4e00-\u9fa5\u3040-\u309f\u30a0-\u30ff]+",
    concat!(
        r##"[!\"#$%&'()*+,\-./:;<=>?@\[\\\]^_`{|}~][A-Za-z]+|[^\r\n\p{L}\p{P}\p{S}]?[\p{L}\p{M}]+"##,
        r"| ?[\p{P}\p{S}]+[\r\n]*|\s*[\r\n]+|\s+(?!\S)|\s+",
    ),
];

/// The `minimax` pattern (GPT-4o's o200k split), as the donor writes it.
pub const MINIMAX_PATTERN: &str = concat!(
    r"[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]*[\p{Ll}\p{Lm}\p{Lo}\p{M}]+(?i:'s|'t|'re|'ve|'m|'ll|'d)?",
    r"|[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]+[\p{Ll}\p{Lm}\p{Lo}\p{M}]*(?i:'s|'t|'re|'ve|'m|'ll|'d)?",
    r"|\p{N}{1,3}",
    r"| ?[^\s\p{L}\p{N}]+[\r\n/]*",
    r"|\s*[\r\n]+",
    r"|\s+(?!\S)",
    r"|\s+",
);

/// The pre-tokenizer names the donor accepts, in the order its refusal message lists them.
pub const KNOWN_SCHEMES: [&str; 5] = ["qwen35", "glm4", "glm5", "deepseek3", "minimax"];

/// The two whitespace branches every pattern ends with, applied by hand by
/// [`PreTokenizer::findall`].
pub const WHITESPACE_TAIL: &str = r"|\s+(?!\S)|\s+";

/// A supported pre-tokenizer scheme.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum PreScheme {
    /// `qwen35`, the default.
    Qwen35,
    /// `glm4`.
    Glm4,
    /// `glm5`.
    Glm5,
    /// `deepseek3`.
    Deepseek3,
    /// `minimax`.
    Minimax,
}

impl PreScheme {
    /// The scheme named `name`, or the donor's `ValueError` for any other name.
    pub fn parse(name: &str) -> Result<Self, TokenizerError> {
        match name {
            "qwen35" => Ok(Self::Qwen35),
            "glm4" => Ok(Self::Glm4),
            "glm5" => Ok(Self::Glm5),
            "deepseek3" => Ok(Self::Deepseek3),
            "minimax" => Ok(Self::Minimax),
            other => Err(unknown_scheme(&py_repr(other))),
        }
    }

    /// The scheme's name as a pack's `tokenizer.json` spells it.
    pub fn name(self) -> &'static str {
        match self {
            Self::Qwen35 => "qwen35",
            Self::Glm4 => "glm4",
            Self::Glm5 => "glm5",
            Self::Deepseek3 => "deepseek3",
            Self::Minimax => "minimax",
        }
    }

    /// `glm4` and `glm5` set llama.cpp's `ignore_merges`: a pre-token piece whose byte-mapped
    /// text is itself a vocabulary entry is emitted whole, without BPE.
    pub fn ignore_merges(self) -> bool {
        matches!(self, Self::Glm4 | Self::Glm5)
    }

    /// `minimax` normalizes each plain segment to NFC before splitting it.
    pub fn nfc(self) -> bool {
        matches!(self, Self::Minimax)
    }
}

/// The donor's refusal of a pre-tokenizer name, given the Python `repr` of the value.
pub fn unknown_scheme(repr: &str) -> TokenizerError {
    TokenizerError::Value(format!(
        "the {repr} pre-tokenizer is not transcribed; known: qwen35, glm4, glm5, deepseek3, minimax"
    ))
}

/// One compiled pattern: its branches before [`WHITESPACE_TAIL`], and whether the pattern
/// ends with that tail.
#[derive(Debug)]
struct Stage {
    body: regex::Regex,
    whitespace_tail: bool,
}

/// A compiled pre-tokenizer: one pattern, or the three isolated stages of `deepseek3`.
#[derive(Debug)]
pub struct PreTokenizer {
    stages: Vec<Stage>,
    isolated: bool,
    space_run: regex::Regex,
}

fn compile_regex(pattern: &str) -> Result<regex::Regex, TokenizerError> {
    regex::Regex::new(pattern).map_err(|e| TokenizerError::Regex(e.to_string()))
}

fn compile(pattern: &str) -> Result<Stage, TokenizerError> {
    match pattern.strip_suffix(WHITESPACE_TAIL) {
        Some(body) => Ok(Stage {
            body: compile_regex(body)?,
            whitespace_tail: true,
        }),
        None => Ok(Stage {
            body: compile_regex(pattern)?,
            whitespace_tail: false,
        }),
    }
}

/// The leftmost match of `re` at or after `pos`, reusing `cached` while it still is one: a
/// match found from an earlier position that starts at or after `pos` is also the leftmost
/// match from `pos`, since none of the patterns looks behind.
fn next_match(
    re: &regex::Regex,
    text: &str,
    pos: usize,
    cached: &mut Option<Option<(usize, usize)>>,
) -> Option<(usize, usize)> {
    match *cached {
        Some(Some((start, end))) if start >= pos => Some((start, end)),
        Some(None) => None,
        _ => {
            let found = re.find_at(text, pos).map(|m| (m.start(), m.end()));
            *cached = Some(found);
            found
        }
    }
}

impl PreTokenizer {
    /// Compiles the pattern of `scheme`.
    pub fn new(scheme: PreScheme) -> Result<Self, TokenizerError> {
        let (stages, isolated) = match scheme {
            PreScheme::Deepseek3 => (
                DEEPSEEK3_PATTERNS
                    .iter()
                    .map(|p| compile(p))
                    .collect::<Result<_, _>>()?,
                true,
            ),
            PreScheme::Minimax => (vec![compile(MINIMAX_PATTERN)?], false),
            PreScheme::Glm4 | PreScheme::Glm5 => (vec![compile(GLM_PATTERN)?], false),
            PreScheme::Qwen35 => (vec![compile(QWEN35_PATTERN)?], false),
        };
        Ok(Self {
            stages,
            isolated,
            space_run: compile_regex(r"\s+")?,
        })
    }

    /// The matches of one stage in `text` as byte ranges, as Python's `finditer` gives them.
    ///
    /// At each position the branches before the whitespace tail are tried first (the `regex`
    /// crate's leftmost-first match is the backtracking alternation's choice). Where none of
    /// them matches and a whitespace run of `L` characters starts, the tail decides:
    /// `\s+(?!\S)` takes the whole run when it reaches the end of the text and `L - 1`
    /// characters when a non-space follows and `L >= 2` (the last one is left to what
    /// follows); when `L == 1` it fails and `\s+` takes the one character.
    fn stage_matches(&self, stage: &Stage, text: &str) -> Vec<(usize, usize)> {
        let mut out = Vec::new();
        let mut pos = 0usize;
        let mut body_next: Option<Option<(usize, usize)>> = None;
        let mut space_next: Option<Option<(usize, usize)>> = None;
        while pos < text.len() {
            let body = next_match(&stage.body, text, pos, &mut body_next);
            let body_start = body.map_or(text.len(), |(s, _)| s);
            if stage.whitespace_tail {
                let run = next_match(&self.space_run, text, pos, &mut space_next)
                    .filter(|&(s, _)| s < body_start);
                if let Some((start, run_end)) = run {
                    let last = text
                        .get(start..run_end)
                        .and_then(|r| r.chars().next_back())
                        .map_or(0, char::len_utf8);
                    let end = if run_end == text.len() || run_end - last == start {
                        run_end
                    } else {
                        run_end - last
                    };
                    out.push((start, end));
                    pos = end;
                    continue;
                }
            }
            let Some((start, end)) = body else {
                break;
            };
            out.push((start, end));
            pos = if end > start {
                end
            } else {
                // No pattern here matches the empty string; this only guards the loop.
                end + text
                    .get(end..)
                    .and_then(|r| r.chars().next())
                    .map_or(1, char::len_utf8)
            };
        }
        out
    }

    /// Splits `text` into pieces, as the donor's `self._re.findall(text)` does. No
    /// normalization is applied here.
    pub fn findall<'t>(&self, text: &'t str) -> Result<Vec<&'t str>, TokenizerError> {
        if !self.isolated {
            let mut out = Vec::new();
            for stage in &self.stages {
                for (s, e) in self.stage_matches(stage, text) {
                    out.push(text.get(s..e).unwrap_or_default());
                }
            }
            return Ok(out);
        }
        let mut pieces: Vec<&'t str> = vec![text];
        for stage in &self.stages {
            let mut out = Vec::with_capacity(pieces.len());
            for piece in pieces {
                let mut pos = 0usize;
                for (s, e) in self.stage_matches(stage, piece) {
                    if s > pos {
                        out.push(piece.get(pos..s).unwrap_or_default());
                    }
                    if e > s {
                        out.push(piece.get(s..e).unwrap_or_default());
                    }
                    pos = e;
                }
                if pos < piece.len() {
                    out.push(piece.get(pos..).unwrap_or_default());
                }
            }
            pieces = out;
        }
        Ok(pieces)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn split(scheme: PreScheme, text: &str) -> Vec<String> {
        let pt = PreTokenizer::new(scheme).expect("compiles");
        pt.findall(text)
            .expect("splits")
            .into_iter()
            .map(String::from)
            .collect()
    }

    #[test]
    fn every_scheme_compiles() {
        for name in KNOWN_SCHEMES {
            let scheme = PreScheme::parse(name).expect("known");
            assert_eq!(scheme.name(), name);
            assert!(PreTokenizer::new(scheme).is_ok());
        }
    }

    #[test]
    fn unknown_scheme_message() {
        let err = PreScheme::parse("llama3").expect_err("refused");
        assert_eq!(
            err.to_string(),
            "the 'llama3' pre-tokenizer is not transcribed; known: qwen35, glm4, glm5, deepseek3, minimax"
        );
        assert_eq!(err.python_type(), "ValueError");
    }

    #[test]
    fn qwen35_hand_computed() {
        assert_eq!(split(PreScheme::Qwen35, "  b"), [" ", " b"]);
        assert_eq!(split(PreScheme::Qwen35, "a\u{301}!"), ["a\u{301}", "!"]);
        assert_eq!(
            split(PreScheme::Qwen35, "I'm 12"),
            ["I", "'m", " ", "1", "2"]
        );
        assert_eq!(
            split(PreScheme::Qwen35, "a\n\n  b"),
            ["a", "\n\n", " ", " b"]
        );
        assert_eq!(split(PreScheme::Qwen35, "x  "), ["x", "  "]);
    }

    #[test]
    fn glm_mark_joins_the_following_punctuation() {
        assert_eq!(split(PreScheme::Glm5, "a\u{301}!"), ["a", "\u{301}!"]);
        assert_eq!(split(PreScheme::Glm4, "1234"), ["123", "4"]);
    }

    #[test]
    fn deepseek3_isolated_stages_hand_computed() {
        assert_eq!(
            split(PreScheme::Deepseek3, "abc 1234 \u{4F60}\u{597D}x"),
            ["abc", " ", "123", "4", " ", "\u{4F60}\u{597D}", "x"]
        );
        assert_eq!(split(PreScheme::Deepseek3, "a.Bc"), ["a", ".Bc"]);
        assert_eq!(split(PreScheme::Deepseek3, ""), Vec::<String>::new());
    }

    #[test]
    fn minimax_hand_computed() {
        assert_eq!(
            split(PreScheme::Minimax, "Hello WORLD it's"),
            ["Hello", " WORLD", " it's"]
        );
        assert_eq!(split(PreScheme::Minimax, "IT'S"), ["IT'S"]);
        assert_eq!(split(PreScheme::Minimax, "x.\n\ny"), ["x", ".\n\n", "y"]);
        assert_eq!(split(PreScheme::Minimax, "12345"), ["123", "45"]);
    }

    #[test]
    fn scheme_flags() {
        assert!(PreScheme::Glm4.ignore_merges());
        assert!(PreScheme::Glm5.ignore_merges());
        assert!(!PreScheme::Qwen35.ignore_merges());
        assert!(!PreScheme::Deepseek3.ignore_merges());
        assert!(PreScheme::Minimax.nfc());
        assert!(!PreScheme::Qwen35.nfc());
    }

    #[test]
    fn deepseek3_cjk_stage_is_the_donor_text() {
        // tools/strata_tokenizer.py:94 writes the ranges as escapes.
        assert_eq!(
            DEEPSEEK3_PATTERNS[1],
            r"[\u4e00-\u9fa5\u3040-\u309f\u30a0-\u30ff]+"
        );
        assert_eq!(
            split(
                PreScheme::Deepseek3,
                "\u{4E00}\u{9FA5}\u{9FA6}\u{3040}\u{30FF}"
            ),
            ["\u{4E00}\u{9FA5}", "\u{9FA6}", "\u{3040}\u{30FF}"]
        );
    }

    /// The donor's whole pattern on a backtracking engine, the split this module must equal.
    fn reference_patterns(scheme: PreScheme) -> Vec<fancy_regex::Regex> {
        let build = |p: &str| fancy_regex::Regex::new(p).expect("compiles");
        match scheme {
            PreScheme::Qwen35 => vec![build(QWEN35_PATTERN)],
            PreScheme::Glm4 | PreScheme::Glm5 => vec![build(GLM_PATTERN)],
            PreScheme::Minimax => vec![build(MINIMAX_PATTERN)],
            PreScheme::Deepseek3 => DEEPSEEK3_PATTERNS.iter().map(|p| build(p)).collect(),
        }
    }

    fn reference_findall(
        scheme: PreScheme,
        stages: &[fancy_regex::Regex],
        text: &str,
    ) -> Vec<String> {
        let find = |re: &fancy_regex::Regex, t: &str| -> Vec<(usize, usize)> {
            re.find_iter(t)
                .map(|m| {
                    let m = m.expect("matches");
                    (m.start(), m.end())
                })
                .collect()
        };
        if scheme != PreScheme::Deepseek3 {
            return stages
                .iter()
                .flat_map(|re| find(re, text))
                .map(|(s, e)| text[s..e].to_owned())
                .collect();
        }
        let mut pieces: Vec<String> = vec![text.to_owned()];
        for re in stages {
            let mut out = Vec::new();
            for piece in pieces {
                let mut pos = 0;
                for (s, e) in find(re, &piece) {
                    if s > pos {
                        out.push(piece[pos..s].to_owned());
                    }
                    if e > s {
                        out.push(piece[s..e].to_owned());
                    }
                    pos = e;
                }
                if pos < piece.len() {
                    out.push(piece[pos..].to_owned());
                }
            }
            pieces = out;
        }
        pieces
    }

    #[test]
    fn hand_applied_whitespace_tail_equals_the_whole_pattern() {
        let alphabet = [
            " ",
            " ",
            " ",
            "\t",
            "\n",
            "\r",
            "\u{3000}",
            "\u{a0}",
            "\u{1c}",
            "a",
            "B",
            "s",
            "1",
            "!",
            "'",
            "/",
            ".",
            "\u{301}",
            "\u{4E00}",
            "\u{e9}",
            "\u{1F600}",
        ];
        let mut state: u64 = 0x9E37_79B9_7F4A_7C15;
        let mut next = || {
            state = state
                .wrapping_mul(6364136223846793005)
                .wrapping_add(1442695040888963407);
            (state >> 33) as usize
        };
        for name in KNOWN_SCHEMES {
            let scheme = PreScheme::parse(name).expect("known");
            let pt = PreTokenizer::new(scheme).expect("compiles");
            let stages = reference_patterns(scheme);
            for round in 0..1500usize {
                let len = round % 24;
                let text: String = (0..len)
                    .map(|_| alphabet[next() % alphabet.len()])
                    .collect();
                let got: Vec<String> = pt
                    .findall(&text)
                    .expect("splits")
                    .into_iter()
                    .map(String::from)
                    .collect();
                assert_eq!(
                    got,
                    reference_findall(scheme, &stages, &text),
                    "{name} {text:?}"
                );
            }
        }
    }

    #[test]
    fn whitespace_tail_hand_computed() {
        assert_eq!(split(PreScheme::Qwen35, "a   "), ["a", "   "]);
        assert_eq!(split(PreScheme::Qwen35, "a   !"), ["a", "  ", " !"]);
        assert_eq!(split(PreScheme::Qwen35, "a \t1"), ["a", " ", "\t", "1"]);
        assert_eq!(split(PreScheme::Qwen35, "1\t2"), ["1", "\t", "2"]);
        assert_eq!(
            split(PreScheme::Glm5, "\u{3000}\u{3000}x"),
            ["\u{3000}", "\u{3000}x"]
        );
    }

    #[test]
    fn whitespace_runs_of_two_million_characters_split() {
        for name in KNOWN_SCHEMES {
            let pt = PreTokenizer::new(PreScheme::parse(name).expect("known")).expect("compiles");
            for ws in [" ", "\t"] {
                let run = ws.repeat(2_000_000);
                let trailing = format!("hello{run}");
                assert_eq!(
                    pt.findall(&trailing).expect("splits"),
                    ["hello", run.as_str()],
                    "{name}"
                );
                let between = format!("hello{run}world");
                let got = pt.findall(&between).expect("splits");
                assert_eq!(got.len(), 3, "{name}");
                assert_eq!(got[2], format!("{ws}world"), "{name}");
                assert_eq!(got[1].len(), 1_999_999, "{name}");
                assert_eq!(got.concat(), between, "{name}");
            }
        }
    }
}
