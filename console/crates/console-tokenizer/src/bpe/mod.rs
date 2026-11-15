//! Owned by PRM-04. Rank-ordered byte-level BPE and its vocabulary checks.
//!
//! [`Tokenizer`] is the byte-level BPE tokenizer of a model pack: a vocabulary in the GPT-2
//! byte alphabet (see [`crate::byte_map`]), merge rules ranked by their position, optional
//! GGUF token types, one of the pre-tokenizers of [`crate::pretok`], and the special literals
//! of [`crate::special`]. Encoding splits off special literals, normalizes (for `minimax`),
//! pre-tokenizes, byte-maps each piece and merges it by lowest rank first. Decoding joins the
//! tokens' raw bytes and replaces invalid UTF-8 with U+FFFD.
//!
//! The constructor refuses, with the donor's messages, an unknown pre-tokenizer name, a
//! vocabulary with duplicate tokens, a merge that is not a pair and a merge naming a token
//! outside the vocabulary. Errors carry the Python exception class the donor raises, and
//! their `Display` is Python's `str()` of that exception.
//!
//! Two caches speed up repeated text without changing any id: a piece memo (pieces of at
//! most 256 bytes only, dropped whole past 300,000 pieces) and an LRU of segments of 2,048 code points or more (up to about
//! 1,000,000 cached ids). Both are behind a mutex, so a [`Tokenizer`] can be shared across
//! threads.
//!
//! Behavior reference: project-maya tools/strata_tokenizer.py:137-383 at 7e68a30f.

use std::cmp::Reverse;
use std::collections::{BTreeMap, BinaryHeap, HashMap};
use std::fmt;
use std::sync::{Arc, Mutex, MutexGuard, OnceLock};

use serde_json::{Map, Value};
use unicode_normalization::UnicodeNormalization;

use crate::byte_map;
use crate::pretok::{PreScheme, PreTokenizer};
use crate::special::{encode_matching, LiteralMatcher, SpecialTokens};

/// The piece memo is dropped whole when it holds more pieces than this at the start of an
/// encode call.
pub const PIECE_MEMO_LIMIT: usize = 300_000;
/// Only pieces of at most this many bytes are kept in the piece memo, so the memo holds at
/// most about `PIECE_MEMO_LIMIT * PIECE_MEMO_MAX_BYTES` bytes of keys. The donor keeps every
/// piece; the memo never changes an id, so this bound is not observable in the output.
pub const PIECE_MEMO_MAX_BYTES: usize = 256;
/// Segments shorter than this many code points are not kept in the segment LRU.
pub const SEGMENT_CACHE_MIN_CHARS: usize = 2048;
/// The segment LRU evicts its oldest entries while it holds more ids than this (and more
/// than one entry).
pub const SEGMENT_CACHE_MAX_IDS: usize = 1_000_000;

/// GGUF token type of a CONTROL literal, matched only with special parsing.
pub const TOKEN_TYPE_CONTROL: i64 = 3;
/// GGUF token type of a USER_DEFINED literal, matched always.
pub const TOKEN_TYPE_USER_DEFINED: i64 = 4;

/// An error the donor raises as a Python exception. `Display` is Python's `str(exc)`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum TokenizerError {
    /// `ValueError` with this message.
    Value(String),
    /// `KeyError` with this argument; `str(KeyError(arg))` is `repr(arg)`.
    Key(String),
    /// `IndexError` with this message.
    Index(String),
    /// `TypeError` with this message.
    Type(String),
    /// `AttributeError` with this message.
    Attribute(String),
    /// An `OSError` (such as `FileNotFoundError`) reading a pack file, with Python's message.
    Io {
        /// The Python class, such as `FileNotFoundError`.
        class: &'static str,
        /// `[Errno N] description: 'path'`.
        message: String,
    },
    /// `UnicodeDecodeError` reading a pack file as UTF-8, with Python's message.
    Unicode(String),
    /// `json.loads` failed on a pack file.
    Json(console_pyjson::loads::LoadsError),
    /// A regular expression could not be compiled within the `regex` crate's size budget
    /// (no Python counterpart: the donor's `regex` module has no size budget). Matching
    /// itself never fails.
    Regex(String),
    /// A pack file is larger than [`crate::pack_dir::MAX_PACK_FILE_BYTES`] (no Python
    /// counterpart).
    TooLarge {
        /// The file's name.
        file: String,
        /// Its size in bytes.
        size: u64,
    },
}

impl TokenizerError {
    /// The Python exception class the donor raises for this error.
    pub fn python_type(&self) -> &'static str {
        match self {
            Self::Value(_) => "ValueError",
            Self::Key(_) => "KeyError",
            Self::Index(_) => "IndexError",
            Self::Type(_) => "TypeError",
            Self::Attribute(_) => "AttributeError",
            Self::Io { class, .. } => class,
            Self::Unicode(_) => "UnicodeDecodeError",
            Self::Json(e) => e.python_type(),
            Self::Regex(_) | Self::TooLarge { .. } => "RuntimeError",
        }
    }
}

impl fmt::Display for TokenizerError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Value(m) | Self::Index(m) | Self::Type(m) | Self::Attribute(m) => f.write_str(m),
            Self::Key(arg) => f.write_str(&py_repr(arg)),
            Self::Io { message, .. } => f.write_str(message),
            Self::Unicode(m) => f.write_str(m),
            Self::Json(e) => e.fmt(f),
            Self::Regex(m) => write!(f, "regular expression limit reached: {m}"),
            Self::TooLarge { file, size } => write!(
                f,
                "{file} is {size} bytes, more than the {} bytes a tokenizer file may have",
                crate::pack_dir::MAX_PACK_FILE_BYTES
            ),
        }
    }
}

impl std::error::Error for TokenizerError {}

/// Python's `repr()` of a `str`: single quotes unless the text holds a single quote and no
/// double quote, backslash escapes for `\\`, `\t`, `\n`, `\r` and the quote, and `\xNN`,
/// `\uNNNN` or `\UNNNNNNNN` for characters `str.isprintable` rejects. Printability follows
/// Rust's Unicode 16.0.0 tables.
pub fn py_repr(s: &str) -> String {
    static NON_PRINTABLE: OnceLock<Option<regex::Regex>> = OnceLock::new();
    let class = NON_PRINTABLE
        .get_or_init(|| regex::Regex::new(r"\A[[\p{C}\p{Z}]--[ ]]\z").ok())
        .as_ref();
    let quote = if s.contains('\'') && !s.contains('"') {
        '"'
    } else {
        '\''
    };
    let mut out = String::with_capacity(s.len() + 2);
    out.push(quote);
    let mut buf = [0u8; 4];
    for c in s.chars() {
        match c {
            '\\' => out.push_str("\\\\"),
            '\t' => out.push_str("\\t"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            c if c == quote => {
                out.push('\\');
                out.push(c);
            }
            c => {
                let cp = u32::from(c);
                let printable = if cp < 0x80 {
                    (0x20..0x7F).contains(&cp)
                } else {
                    match class {
                        Some(re) => !re.is_match(c.encode_utf8(&mut buf)),
                        None => false,
                    }
                };
                if printable {
                    out.push(c);
                } else if cp < 0x100 {
                    out.push_str(&format!("\\x{cp:02x}"));
                } else if cp < 0x10000 {
                    out.push_str(&format!("\\u{cp:04x}"));
                } else {
                    out.push_str(&format!("\\U{cp:08x}"));
                }
            }
        }
    }
    out.push(quote);
    out
}

/// What the serving layer needs from a tokenizer: the donor's duck-typed interface shared by
/// [`Tokenizer`] and [`crate::byte_tok::ByteTokenizer`].
pub trait Tokenize {
    /// Encodes `text`. `parse_special` enables the type-3 CONTROL literals; type-4 literals
    /// are matched either way. `plain` lists byte ranges of `text` that are ordinary text even
    /// where they spell a literal.
    fn encode(
        &self,
        text: &str,
        parse_special: bool,
        plain: &[(usize, usize)],
    ) -> Result<Vec<u32>, TokenizerError>;

    /// Decodes ids to text, replacing invalid UTF-8 with U+FFFD.
    fn decode(&self, ids: &[u32]) -> Result<String, TokenizerError>;

    /// The raw bytes of one token, or `None` when the tokenizer has no `token_bytes` (the
    /// donor's `hasattr(tok, "token_bytes")` is false), which makes the detokenizer re-decode.
    fn token_bytes(&self, id: u32) -> Option<Result<Vec<u8>, TokenizerError>>;

    /// Whether [`Tokenize::token_bytes`] is available (returns `Some`).
    fn has_token_bytes(&self) -> bool;

    /// The special literals and their ids.
    fn special_tokens(&self) -> &SpecialTokens;

    /// The named special ids (such as `eos`), as the pack or the GGUF metadata gives them.
    fn special_ids(&self) -> &Map<String, Value>;

    /// The vocabulary, index = id, or `None` when the tokenizer has no `tokens` attribute in
    /// the donor (the byte tokenizer: `getattr(tok, "tokens", None)` is `None`).
    fn tokens(&self) -> Option<&[String]> {
        None
    }

    /// The donor's `len(getattr(tok, "tokens", None) or ())`, used for the think stop tables
    /// and the `logit_bias` bound (server.py:470 and 2494): the vocabulary size, 0 for the byte
    /// tokenizer. It is `tokens().map_or(0, <[_]>::len)`.
    fn n_tokens(&self) -> usize {
        self.tokens().map_or(0, <[_]>::len)
    }

    /// The GGUF token types, or `None` where the donor's `getattr(tok, "token_types", None)`
    /// is falsy (the byte tokenizer, or a pack without types).
    fn token_types(&self) -> Option<&[i64]> {
        None
    }

    /// The matcher of every special literal (the donor's `_special_re`), or `None` when the
    /// tokenizer has none (the donor's `None` pattern or no attribute at all).
    fn special_matcher(&self) -> Option<&LiteralMatcher> {
        None
    }

    /// Encodes the text between two special literals (the donor's `_encode_segment`, with
    /// the segment LRU), or `None` when the tokenizer has no segment encoder (the donor's
    /// `hasattr(tok, "_encode_segment")` is false, which turns the prompt memo off).
    fn encode_segment(&self, text: &str) -> Option<Result<Vec<u32>, TokenizerError>> {
        let _ = text;
        None
    }
}

impl<T: Tokenize + ?Sized> Tokenize for &T {
    fn encode(
        &self,
        text: &str,
        parse_special: bool,
        plain: &[(usize, usize)],
    ) -> Result<Vec<u32>, TokenizerError> {
        (**self).encode(text, parse_special, plain)
    }
    fn decode(&self, ids: &[u32]) -> Result<String, TokenizerError> {
        (**self).decode(ids)
    }
    fn token_bytes(&self, id: u32) -> Option<Result<Vec<u8>, TokenizerError>> {
        (**self).token_bytes(id)
    }
    fn has_token_bytes(&self) -> bool {
        (**self).has_token_bytes()
    }
    fn special_tokens(&self) -> &SpecialTokens {
        (**self).special_tokens()
    }
    fn special_ids(&self) -> &Map<String, Value> {
        (**self).special_ids()
    }
    fn tokens(&self) -> Option<&[String]> {
        (**self).tokens()
    }
    fn n_tokens(&self) -> usize {
        (**self).n_tokens()
    }
    fn token_types(&self) -> Option<&[i64]> {
        (**self).token_types()
    }
    fn special_matcher(&self) -> Option<&LiteralMatcher> {
        (**self).special_matcher()
    }
    fn encode_segment(&self, text: &str) -> Option<Result<Vec<u32>, TokenizerError>> {
        (**self).encode_segment(text)
    }
}

impl<T: Tokenize + ?Sized> Tokenize for Arc<T> {
    fn encode(
        &self,
        text: &str,
        parse_special: bool,
        plain: &[(usize, usize)],
    ) -> Result<Vec<u32>, TokenizerError> {
        (**self).encode(text, parse_special, plain)
    }
    fn decode(&self, ids: &[u32]) -> Result<String, TokenizerError> {
        (**self).decode(ids)
    }
    fn token_bytes(&self, id: u32) -> Option<Result<Vec<u8>, TokenizerError>> {
        (**self).token_bytes(id)
    }
    fn has_token_bytes(&self) -> bool {
        (**self).has_token_bytes()
    }
    fn special_tokens(&self) -> &SpecialTokens {
        (**self).special_tokens()
    }
    fn special_ids(&self) -> &Map<String, Value> {
        (**self).special_ids()
    }
    fn tokens(&self) -> Option<&[String]> {
        (**self).tokens()
    }
    fn n_tokens(&self) -> usize {
        (**self).n_tokens()
    }
    fn token_types(&self) -> Option<&[i64]> {
        (**self).token_types()
    }
    fn special_matcher(&self) -> Option<&LiteralMatcher> {
        (**self).special_matcher()
    }
    fn encode_segment(&self, text: &str) -> Option<Result<Vec<u32>, TokenizerError>> {
        (**self).encode_segment(text)
    }
}

#[derive(Debug, Default)]
struct PieceMemo {
    map: HashMap<String, Arc<[u32]>>,
}

#[derive(Debug, Default)]
struct SegmentCache {
    map: HashMap<Arc<str>, (Arc<[u32]>, u64)>,
    order: BTreeMap<u64, Arc<str>>,
    next_stamp: u64,
    ids: usize,
}

impl SegmentCache {
    fn get(&mut self, text: &str) -> Option<Arc<[u32]>> {
        let stamp = self.next_stamp;
        let (key, entry) = self.map.get_key_value(text)?;
        let key = Arc::clone(key);
        let ids = Arc::clone(&entry.0);
        let old = entry.1;
        self.order.remove(&old);
        self.order.insert(stamp, Arc::clone(&key));
        if let Some(e) = self.map.get_mut(&key) {
            e.1 = stamp;
        }
        self.next_stamp += 1;
        Some(ids)
    }

    fn insert(&mut self, text: &str, ids: Arc<[u32]>) {
        if self.map.contains_key(text) {
            return;
        }
        let key: Arc<str> = Arc::from(text);
        let stamp = self.next_stamp;
        self.next_stamp += 1;
        self.ids += ids.len();
        self.order.insert(stamp, Arc::clone(&key));
        self.map.insert(key, (ids, stamp));
        while self.ids > SEGMENT_CACHE_MAX_IDS && self.map.len() > 1 {
            let Some((_, oldest)) = self.order.pop_first() else {
                break;
            };
            if let Some((old, _)) = self.map.remove(&oldest) {
                self.ids -= old.len();
            }
        }
    }
}

fn lock<T>(m: &Mutex<T>) -> MutexGuard<'_, T> {
    m.lock().unwrap_or_else(|poisoned| poisoned.into_inner())
}

/// A byte-level BPE tokenizer.
#[derive(Debug)]
pub struct Tokenizer {
    tokens: Vec<String>,
    pre: PreScheme,
    token_types: Option<Vec<i64>>,
    special_ids: Map<String, Value>,
    ids: HashMap<String, u32>,
    ranks: HashMap<(u32, u32), u32>,
    pretok: PreTokenizer,
    specials: SpecialTokens,
    always: Option<LiteralMatcher>,
    all_literals: Option<LiteralMatcher>,
    memo: Mutex<PieceMemo>,
    segments: Mutex<SegmentCache>,
}

impl Tokenizer {
    /// Builds a tokenizer from its vocabulary (index = id), merge rules (`"left right"`, rank
    /// = position; a later duplicate takes the later rank), optional GGUF token types, the
    /// pre-tokenizer name and the named special ids.
    ///
    /// Behavior reference: project-maya tools/strata_tokenizer.py:138-198 at 7e68a30f.
    pub fn new<S: AsRef<str>>(
        tokens: Vec<String>,
        merges: &[S],
        token_types: Option<Vec<i64>>,
        pre: &str,
        special_ids: Option<Map<String, Value>>,
    ) -> Result<Self, TokenizerError> {
        let pre = PreScheme::parse(pre)?;
        if u32::try_from(tokens.len()).is_err() {
            return Err(TokenizerError::Value(format!(
                "vocabulary has {} entries, more than token ids can number",
                tokens.len()
            )));
        }
        let mut ids: HashMap<String, u32> = HashMap::with_capacity(tokens.len());
        for (i, tok) in tokens.iter().enumerate() {
            ids.insert(tok.clone(), i as u32);
        }
        if ids.len() != tokens.len() {
            return Err(TokenizerError::Value(format!(
                "vocabulary has duplicate tokens: {} entries, {} unique",
                tokens.len(),
                ids.len()
            )));
        }
        let mut ranks: HashMap<(u32, u32), u32> = HashMap::with_capacity(merges.len());
        for (i, m) in merges.iter().enumerate() {
            let m = m.as_ref();
            let parts: Vec<&str> = m.split(' ').collect();
            let [left, right] = parts.as_slice() else {
                return Err(TokenizerError::Value(format!(
                    "merge {i} is not a pair: {}",
                    py_repr(m)
                )));
            };
            let (Some(&a), Some(&b)) = (ids.get(*left), ids.get(*right)) else {
                return Err(TokenizerError::Value(format!(
                    "merge {i} names a token outside the vocabulary: {}",
                    py_repr(m)
                )));
            };
            let rank = u32::try_from(i).map_err(|_| {
                TokenizerError::Value(format!("merge {i} is past the last rank a merge can take"))
            })?;
            ranks.insert((a, b), rank);
        }
        let pretok = PreTokenizer::new(pre)?;
        let mut specials = SpecialTokens::new();
        let mut always_ids: Vec<u32> = Vec::new();
        if let Some(types) = token_types.as_deref() {
            for (i, &ty) in types.iter().enumerate() {
                if ty == TOKEN_TYPE_CONTROL || ty == TOKEN_TYPE_USER_DEFINED {
                    let lit = tokens
                        .get(i)
                        .ok_or_else(|| TokenizerError::Index("list index out of range".into()))?;
                    specials.insert(lit, i as u32);
                }
            }
            for (_, id) in specials.iter() {
                if types.get(id as usize) == Some(&TOKEN_TYPE_USER_DEFINED) {
                    always_ids.push(id);
                }
            }
        }
        let always = LiteralMatcher::new(
            always_ids
                .iter()
                .filter_map(|&id| tokens.get(id as usize).map(String::as_str)),
        )?;
        let all_literals = LiteralMatcher::new(specials.iter().map(|(s, _)| s))?;
        Ok(Self {
            tokens,
            pre,
            token_types,
            special_ids: special_ids.unwrap_or_default(),
            ids,
            ranks,
            pretok,
            specials,
            always,
            all_literals,
            memo: Mutex::new(PieceMemo::default()),
            segments: Mutex::new(SegmentCache::default()),
        })
    }

    /// The pre-tokenizer scheme.
    pub fn pre(&self) -> PreScheme {
        self.pre
    }

    /// Whether a piece that is a whole vocabulary entry is emitted without BPE (`glm4`,
    /// `glm5`).
    pub fn ignore_merges(&self) -> bool {
        self.pre.ignore_merges()
    }

    /// The vocabulary, index = id, in the byte alphabet (special literals as their text).
    pub fn tokens(&self) -> &[String] {
        &self.tokens
    }

    /// The vocabulary size.
    pub fn n_vocab(&self) -> usize {
        self.tokens.len()
    }

    /// The GGUF token types, if the pack has them.
    pub fn token_types(&self) -> Option<&[i64]> {
        self.token_types.as_deref()
    }

    /// The matcher of every special literal, types 3 and 4 (the donor's `_special_re`), or
    /// `None` when there are none.
    pub fn special_matcher(&self) -> Option<&LiteralMatcher> {
        self.all_literals.as_ref()
    }

    /// The number of distinct merge pairs (`len(self.ranks)`).
    pub fn n_merges(&self) -> usize {
        self.ranks.len()
    }

    /// The id of a vocabulary entry.
    pub fn id_of(&self, tok: &str) -> Option<u32> {
        self.ids.get(tok).copied()
    }

    /// Splits plain text with the pre-tokenizer, without normalization (the donor's
    /// `self._re.findall(text)`).
    pub fn pretokenize<'t>(&self, text: &'t str) -> Result<Vec<&'t str>, TokenizerError> {
        self.pretok.findall(text)
    }

    /// Merges a byte-mapped word by lowest rank first, repeatedly, and returns the parts (the
    /// donor's `_bpe`).
    ///
    /// Behavior reference: project-maya tools/strata_tokenizer.py:235-251 at 7e68a30f.
    pub fn bpe(&self, word: &str) -> Vec<String> {
        self.bpe_parts(word)
            .into_iter()
            .map(|(s, e, _)| word.get(s..e).unwrap_or_default().to_owned())
            .collect()
    }

    /// The rank of the pair of two parts, when both are vocabulary entries and a merge names
    /// them.
    fn pair_rank(&self, left: Option<u32>, right: Option<u32>) -> Option<u32> {
        self.ranks.get(&(left?, right?)).copied()
    }

    /// The parts of `word` after BPE as byte ranges, each with its id when it is in the
    /// vocabulary. A pair can only have a rank when both parts are vocabulary entries.
    ///
    /// The donor rescans every pair after each merge and merges the lowest rank, the leftmost
    /// pair among equal ranks. This keeps the pairs in a heap ordered by (rank, start offset)
    /// instead, which picks the same pair at every step (a pair's left part keeps its start
    /// offset, so start order is list order) in O(n log n); stale heap entries are skipped by
    /// re-checking adjacency and rank when they are popped.
    fn bpe_parts(&self, word: &str) -> Vec<(usize, usize, Option<u32>)> {
        const NONE: usize = usize::MAX;
        struct Part {
            start: usize,
            end: usize,
            id: Option<u32>,
            prev: usize,
            next: usize,
            alive: bool,
        }
        let lookup = |s: usize, e: usize| self.ids.get(word.get(s..e).unwrap_or_default()).copied();
        let mut parts: Vec<Part> = word
            .char_indices()
            .map(|(i, c)| (i, i + c.len_utf8()))
            .enumerate()
            .map(|(k, (s, e))| Part {
                start: s,
                end: e,
                id: lookup(s, e),
                prev: if k == 0 { NONE } else { k - 1 },
                next: k + 1,
                alive: true,
            })
            .collect();
        if let Some(last) = parts.last_mut() {
            last.next = NONE;
        }
        let mut heap: BinaryHeap<Reverse<(u32, usize, usize, usize)>> = BinaryHeap::new();
        for k in 1..parts.len() {
            let (Some(l), Some(r)) = (parts.get(k - 1), parts.get(k)) else {
                continue;
            };
            if let Some(rank) = self.pair_rank(l.id, r.id) {
                heap.push(Reverse((rank, l.start, k - 1, k)));
            }
        }
        while let Some(Reverse((rank, _, li, ri))) = heap.pop() {
            let (Some(l), Some(r)) = (parts.get(li), parts.get(ri)) else {
                continue;
            };
            if !l.alive || !r.alive || l.next != ri || self.pair_rank(l.id, r.id) != Some(rank) {
                continue;
            }
            let (start, end, after) = (l.start, r.end, r.next);
            let merged_id = lookup(start, end);
            if let Some(l) = parts.get_mut(li) {
                l.end = end;
                l.id = merged_id;
                l.next = after;
            }
            if let Some(r) = parts.get_mut(ri) {
                r.alive = false;
            }
            if let Some(a) = parts.get_mut(after) {
                a.prev = li;
            }
            let before = parts.get(li).map_or(NONE, |l| l.prev);
            if let Some(b) = parts.get(before) {
                if let Some(rank) = self.pair_rank(b.id, merged_id) {
                    heap.push(Reverse((rank, b.start, before, li)));
                }
            }
            if let Some(a) = parts.get(after) {
                if let Some(rank) = self.pair_rank(merged_id, a.id) {
                    heap.push(Reverse((rank, start, li, after)));
                }
            }
        }
        parts
            .into_iter()
            .filter(|p| p.alive)
            .map(|p| (p.start, p.end, p.id))
            .collect()
    }

    /// The donor's algorithm as written (rescan after every merge), kept to check
    /// [`Tokenizer::bpe_parts`] against.
    #[cfg(test)]
    fn bpe_parts_reference(&self, word: &str) -> Vec<(usize, usize, Option<u32>)> {
        let mut parts: Vec<(usize, usize, Option<u32>)> = word
            .char_indices()
            .map(|(i, c)| {
                let end = i + c.len_utf8();
                (
                    i,
                    end,
                    self.ids.get(word.get(i..end).unwrap_or_default()).copied(),
                )
            })
            .collect();
        while parts.len() > 1 {
            let mut best: Option<(usize, u32)> = None;
            for (i, pair) in parts.windows(2).enumerate() {
                if let Some(r) = self.pair_rank(pair[0].2, pair[1].2) {
                    if best.is_none_or(|(_, br)| r < br) {
                        best = Some((i, r));
                    }
                }
            }
            let Some((i, _)) = best else {
                break;
            };
            let (start, end) = (parts[i].0, parts[i + 1].1);
            let merged = (start, end, self.ids.get(&word[start..end]).copied());
            parts.splice(i..i + 2, [merged]);
        }
        parts
    }

    fn encode_plain(&self, text: &str) -> Result<Vec<u32>, TokenizerError> {
        {
            let mut memo = lock(&self.memo);
            if memo.map.len() > PIECE_MEMO_LIMIT {
                memo.map.clear();
            }
        }
        let normalized: String;
        let text = if self.pre.nfc() {
            normalized = text.nfc().collect();
            normalized.as_str()
        } else {
            text
        };
        let mut out = Vec::new();
        for piece in self.pretok.findall(text)? {
            if let Some(hit) = lock(&self.memo).map.get(piece) {
                out.extend_from_slice(hit);
                continue;
            }
            // The vocabulary is in the byte alphabet, so the ignore_merges whole-entry lookup
            // runs on the byte-mapped piece.
            let mapped = byte_map::map_bytes(piece.as_bytes());
            let ids: Arc<[u32]> = match self.ids.get(&mapped) {
                Some(&id) if self.pre.ignore_merges() => Arc::from([id].as_slice()),
                _ => {
                    let mut got = Vec::new();
                    for (s, e, id) in self.bpe_parts(&mapped) {
                        let Some(id) = id else {
                            return Err(TokenizerError::Key(format!(
                                "BPE produced a token outside the vocabulary: {}",
                                py_repr(mapped.get(s..e).unwrap_or_default())
                            )));
                        };
                        got.push(id);
                    }
                    Arc::from(got)
                }
            };
            out.extend_from_slice(&ids);
            if piece.len() <= PIECE_MEMO_MAX_BYTES {
                lock(&self.memo).map.insert(piece.to_owned(), ids);
            }
        }
        Ok(out)
    }

    /// Encodes the text between two special literals without matching any literal in it:
    /// normalization, pre-tokenization and BPE, with segments of [`SEGMENT_CACHE_MIN_CHARS`]
    /// code points or more kept in the segment LRU (the donor's `_encode_segment`). The
    /// serving layer's prompt memo runs its own copy of the literal loop over
    /// [`Tokenizer::special_matcher`] and this, and must give the ids of [`Tokenizer::encode`].
    ///
    /// Behavior reference: project-maya tools/strata_tokenizer.py:288-315 at 7e68a30f.
    pub fn encode_segment(&self, text: &str) -> Result<Vec<u32>, TokenizerError> {
        if text.chars().count() < SEGMENT_CACHE_MIN_CHARS {
            return self.encode_plain(text);
        }
        if let Some(hit) = lock(&self.segments).get(text) {
            return Ok(hit.to_vec());
        }
        let ids = self.encode_plain(text)?;
        lock(&self.segments).insert(text, Arc::from(ids.as_slice()));
        Ok(ids)
    }

    /// Encodes `text`: special literals as their ids (type 4 always, type 3 only with
    /// `parse_special`), except where a match starts inside one of the `plain` byte ranges,
    /// and everything else through normalization, pre-tokenization and BPE.
    ///
    /// Behavior reference: project-maya tools/strata_tokenizer.py:351-359 at 7e68a30f.
    pub fn encode(
        &self,
        text: &str,
        parse_special: bool,
        plain: &[(usize, usize)],
    ) -> Result<Vec<u32>, TokenizerError> {
        let matcher = if parse_special {
            self.all_literals.as_ref()
        } else {
            self.always.as_ref()
        };
        encode_matching(text, matcher, plain, &self.specials, |seg| {
            self.encode_segment(seg)
        })
    }

    /// The raw bytes of one token: a type-3 or type-4 token is its UTF-8 text, any other maps
    /// back through the byte alphabet.
    ///
    /// Behavior reference: project-maya tools/strata_tokenizer.py:361-380 at 7e68a30f.
    pub fn token_bytes(&self, id: u32) -> Result<Vec<u8>, TokenizerError> {
        let Some(tok) = self.tokens.get(id as usize) else {
            return Err(TokenizerError::Index(format!(
                "token id {id} is outside the vocabulary ({})",
                self.tokens.len()
            )));
        };
        if let Some(types) = self.token_types.as_deref().filter(|t| !t.is_empty()) {
            let ty = types
                .get(id as usize)
                .ok_or_else(|| TokenizerError::Index("list index out of range".into()))?;
            if *ty == TOKEN_TYPE_CONTROL || *ty == TOKEN_TYPE_USER_DEFINED {
                return Ok(tok.as_bytes().to_vec());
            }
        }
        byte_map::unmap(tok).map_err(|c| {
            TokenizerError::Key(format!(
                "token {id} contains a character outside the byte alphabet: {}",
                py_repr(c.encode_utf8(&mut [0u8; 4]))
            ))
        })
    }

    /// Decodes ids, replacing invalid UTF-8 with U+FFFD as Python's `errors="replace"` does.
    pub fn decode(&self, ids: &[u32]) -> Result<String, TokenizerError> {
        let mut raw = Vec::new();
        for &id in ids {
            raw.extend(self.token_bytes(id)?);
        }
        Ok(crate::detok::decode_utf8_replace(&raw))
    }
}

impl Tokenize for Tokenizer {
    fn encode(
        &self,
        text: &str,
        parse_special: bool,
        plain: &[(usize, usize)],
    ) -> Result<Vec<u32>, TokenizerError> {
        Tokenizer::encode(self, text, parse_special, plain)
    }
    fn decode(&self, ids: &[u32]) -> Result<String, TokenizerError> {
        Tokenizer::decode(self, ids)
    }
    fn token_bytes(&self, id: u32) -> Option<Result<Vec<u8>, TokenizerError>> {
        Some(Tokenizer::token_bytes(self, id))
    }
    fn has_token_bytes(&self) -> bool {
        true
    }
    fn special_tokens(&self) -> &SpecialTokens {
        &self.specials
    }
    fn special_ids(&self) -> &Map<String, Value> {
        &self.special_ids
    }
    fn tokens(&self) -> Option<&[String]> {
        Some(Tokenizer::tokens(self))
    }
    fn token_types(&self) -> Option<&[i64]> {
        Tokenizer::token_types(self)
    }
    fn special_matcher(&self) -> Option<&LiteralMatcher> {
        Tokenizer::special_matcher(self)
    }
    fn encode_segment(&self, text: &str) -> Option<Result<Vec<u32>, TokenizerError>> {
        Some(Tokenizer::encode_segment(self, text))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn alphabet() -> Vec<String> {
        byte_map::alphabet().into_iter().map(String::from).collect()
    }

    #[test]
    fn repr_matches_python() {
        assert_eq!(py_repr("ab"), "'ab'");
        assert_eq!(py_repr("a'b"), "\"a'b\"");
        assert_eq!(py_repr("a'\"b"), "'a\\'\"b'");
        assert_eq!(py_repr("\t\n\r\\"), "'\\t\\n\\r\\\\'");
        assert_eq!(py_repr("\u{0}\u{7f}"), "'\\x00\\x7f'");
        assert_eq!(py_repr("\u{a0}\u{e9}\u{2028}"), "'\\xa0\u{e9}\\u2028'");
        assert_eq!(py_repr("\u{10FFFF}\u{1F600}"), "'\\U0010ffff\u{1F600}'");
        assert_eq!(py_repr("\u{0120}"), "'\u{0120}'");
    }

    #[test]
    fn duplicate_tokens_refused() {
        let toks = vec!["a".to_owned(), "b".to_owned(), "a".to_owned()];
        let err = Tokenizer::new(toks, &[] as &[&str], None, "qwen35", None).expect_err("dup");
        assert_eq!(
            err.to_string(),
            "vocabulary has duplicate tokens: 3 entries, 2 unique"
        );
        assert_eq!(err.python_type(), "ValueError");
    }

    #[test]
    fn merge_checks_use_the_donor_messages() {
        let toks = vec!["a".to_owned(), "b".to_owned(), "ab".to_owned()];
        let err = Tokenizer::new(toks.clone(), &["a b", "ab"], None, "qwen35", None)
            .expect_err("not a pair");
        assert_eq!(err.to_string(), "merge 1 is not a pair: 'ab'");
        let err =
            Tokenizer::new(toks.clone(), &["a  b"], None, "qwen35", None).expect_err("three parts");
        assert_eq!(err.to_string(), "merge 0 is not a pair: 'a  b'");
        let err =
            Tokenizer::new(toks.clone(), &["a c"], None, "qwen35", None).expect_err("outside");
        assert_eq!(
            err.to_string(),
            "merge 0 names a token outside the vocabulary: 'a c'"
        );
        // A trailing newline in merges.txt gives an empty last merge, which is not a pair.
        let err = Tokenizer::new(toks, &["a b", ""], None, "qwen35", None).expect_err("empty");
        assert_eq!(err.to_string(), "merge 1 is not a pair: ''");
    }

    #[test]
    fn pre_is_checked_first() {
        let toks = vec!["a".to_owned(), "a".to_owned()];
        let err = Tokenizer::new(toks, &["x"], None, "gpt2", None).expect_err("pre");
        assert!(err.to_string().starts_with("the 'gpt2' pre-tokenizer"));
    }

    #[test]
    fn lowest_rank_merges_first_not_list_order() {
        // "abc": the merge b+c has rank 0 and a+b rank 1, so b+c happens first, and the
        // result is ["a", "bc"]; applying merges left to right would give ["ab", "c"].
        let mut toks = alphabet();
        toks.extend(["ab", "bc"].map(String::from));
        let tk = Tokenizer::new(toks, &["b c", "a b"], None, "qwen35", None).expect("builds");
        assert_eq!(tk.bpe("abc"), ["a", "bc"]);
        assert_eq!(tk.n_merges(), 2);
        // Equal ranks: the leftmost pair goes first.
        let mut toks = alphabet();
        toks.push("aa".into());
        let tk = Tokenizer::new(toks, &["a a"], None, "qwen35", None).expect("builds");
        assert_eq!(tk.bpe("aaa"), ["aa", "a"]);
    }

    #[test]
    fn later_duplicate_merge_takes_the_later_rank() {
        let mut toks = alphabet();
        toks.extend(["ab", "bc"].map(String::from));
        // a+b at ranks 0 and 2, b+c at rank 1: a+b ends with rank 2, so b+c wins.
        let tk =
            Tokenizer::new(toks, &["a b", "b c", "a b"], None, "qwen35", None).expect("builds");
        assert_eq!(tk.bpe("abc"), ["a", "bc"]);
        assert_eq!(tk.n_merges(), 2);
    }

    #[test]
    fn bpe_output_outside_vocab_is_a_key_error() {
        // "a b" is a valid merge whose result "ab" is not a vocabulary entry.
        let tk = Tokenizer::new(alphabet(), &["a b"], None, "qwen35", None).expect("builds");
        let err = tk.encode("ab", false, &[]).expect_err("key error");
        assert_eq!(err.python_type(), "KeyError");
        assert_eq!(
            err.to_string(),
            "\"BPE produced a token outside the vocabulary: 'ab'\""
        );
    }

    #[test]
    fn token_bytes_errors() {
        let mut toks = alphabet();
        toks.push("\u{4E00}".into());
        let tk = Tokenizer::new(toks, &[] as &[&str], None, "qwen35", None).expect("builds");
        let err = tk.token_bytes(999).expect_err("index");
        assert_eq!(
            err.to_string(),
            "token id 999 is outside the vocabulary (257)"
        );
        assert_eq!(err.python_type(), "IndexError");
        let err = tk.token_bytes(256).expect_err("alphabet");
        assert_eq!(
            err.to_string(),
            "\"token 256 contains a character outside the byte alphabet: '\u{4E00}'\""
        );
        // Types shorter than the vocabulary: an IndexError on a token past them.
        let mut toks = alphabet();
        toks.push("<s>".into());
        let tk =
            Tokenizer::new(toks, &[] as &[&str], Some(vec![1; 3]), "qwen35", None).expect("builds");
        assert_eq!(tk.token_bytes(1).expect("in range"), b"\"".to_vec());
        assert_eq!(
            tk.token_bytes(256).expect_err("short types").to_string(),
            "list index out of range"
        );
    }

    #[test]
    fn type_index_past_the_vocabulary_is_an_index_error() {
        let err = Tokenizer::new(
            alphabet(),
            &[] as &[&str],
            Some(vec![1; 300].into_iter().chain([3]).collect()),
            "qwen35",
            None,
        )
        .expect_err("index");
        assert_eq!(err.python_type(), "IndexError");
    }

    #[test]
    fn caches_do_not_change_ids() {
        let mut toks = alphabet();
        toks.extend(["ab", "abab"].map(String::from));
        let tk = Tokenizer::new(toks, &["a b", "ab ab"], None, "qwen35", None).expect("builds");
        let long = "abab ".repeat(600);
        let first = tk.encode(&long, false, &[]).expect("encodes");
        let second = tk.encode(&long, false, &[]).expect("encodes");
        assert_eq!(first, second);
        assert_eq!(lock(&tk.segments).map.len(), 1);
        assert_eq!(tk.decode(&first).expect("decodes"), long);
    }

    #[test]
    fn segment_cache_evicts_oldest_past_the_id_budget() {
        let mut cache = SegmentCache::default();
        let big: Arc<[u32]> = Arc::from(vec![0u32; 600_000]);
        cache.insert("one", Arc::clone(&big));
        cache.insert("two", Arc::clone(&big));
        assert!(cache.get("one").is_none());
        assert!(cache.get("two").is_some());
        assert_eq!(cache.ids, 600_000);
        // A single entry over the budget stays.
        let huge: Arc<[u32]> = Arc::from(vec![0u32; 1_500_000]);
        let mut cache = SegmentCache::default();
        cache.insert("x", huge);
        assert!(cache.get("x").is_some());
    }

    #[test]
    fn segment_cache_get_refreshes_recency() {
        let mut cache = SegmentCache::default();
        let part: Arc<[u32]> = Arc::from(vec![0u32; 400_000]);
        cache.insert("a", Arc::clone(&part));
        cache.insert("b", Arc::clone(&part));
        assert!(cache.get("a").is_some());
        cache.insert("c", Arc::clone(&part));
        assert!(cache.get("b").is_none(), "b was the least recently used");
        assert!(cache.get("a").is_some());
        assert!(cache.get("c").is_some());
    }

    #[test]
    fn heap_bpe_matches_the_donor_rescan() {
        // Random words over a small alphabet with overlapping merges, compared step for step
        // with the donor's algorithm.
        let mut toks = alphabet();
        let merges = [
            "a b", "b a", "a a", "ab a", "b ab", "aa b", "ba ba", "ab ab", "a ba", "c a", "ca b",
            "b c", "abab ab", "aa aa", "c c",
        ];
        for m in merges {
            let joined = m.replace(' ', "");
            if !toks.contains(&joined) {
                toks.push(joined);
            }
        }
        toks.retain(|t| t != "cc");
        let tk = Tokenizer::new(toks, &merges, None, "qwen35", None).expect("builds");
        let mut state: u64 = 12345;
        for len in 0..200usize {
            for _ in 0..20 {
                let word: String = (0..len % 40)
                    .map(|_| {
                        state = state
                            .wrapping_mul(6364136223846793005)
                            .wrapping_add(1442695040888963407);
                        ['a', 'b', 'c', '\u{e9}'][(state >> 60) as usize % 4]
                    })
                    .collect();
                assert_eq!(tk.bpe_parts(&word), tk.bpe_parts_reference(&word), "{word}");
            }
        }
    }

    #[test]
    fn piece_memo_keeps_only_short_pieces() {
        let tk = Tokenizer::new(alphabet(), &[] as &[&str], None, "qwen35", None).expect("builds");
        let letters = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'];
        let mut total_ids = 0usize;
        for k in 0..200usize {
            // A distinct run of 10,000 letters is one piece under qwen35.
            let tag: String = (0..4).map(|d| letters[(k >> (3 * d)) & 7]).collect();
            let word = format!("{tag}{}", "x".repeat(10_000));
            let ids = tk.encode(&word, false, &[]).expect("encodes");
            assert_eq!(tk.decode(&ids).expect("decodes"), word);
            total_ids += ids.len();
        }
        assert_eq!(total_ids, 200 * 10_004);
        let memo = lock(&tk.memo);
        assert!(memo.map.keys().all(|k| k.len() <= PIECE_MEMO_MAX_BYTES));
        assert!(memo.map.is_empty());
        drop(memo);
        // Short pieces are still remembered, and give the same ids from the memo.
        let first = tk.encode("hello world", false, &[]).expect("encodes");
        assert_eq!(lock(&tk.memo).map.len(), 2);
        assert_eq!(
            tk.encode("hello world", false, &[]).expect("encodes"),
            first
        );
    }

    #[test]
    fn trait_view_of_a_bpe_tokenizer() {
        let mut toks = alphabet();
        toks.push("<x>".into());
        let types: Vec<i64> = vec![1; 256].into_iter().chain([3]).collect();
        let tk = Tokenizer::new(toks, &[] as &[&str], Some(types), "qwen35", None).expect("builds");
        let view: &dyn Tokenize = &tk;
        assert_eq!(view.tokens().map(<[_]>::len), Some(257));
        assert_eq!(view.n_tokens(), 257);
        assert_eq!(view.token_types().map(<[_]>::len), Some(257));
        assert!(view.special_matcher().is_some());
        let seg = view
            .encode_segment("a<x>")
            .expect("has a segment encoder")
            .expect("ok");
        assert_eq!(seg.len(), 4, "the literal is not matched in a segment");
        assert!(!seg.contains(&256));
        assert_eq!(tk.decode(&seg).expect("decodes"), "a<x>");
    }

    #[test]
    fn tokenizer_is_send_and_sync() {
        fn check<T: Send + Sync>() {}
        check::<Tokenizer>();
    }
}
