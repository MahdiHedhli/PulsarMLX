// Provenance: translated from project-maya serve/test_detok.py at 7e68a30f (MIT); license text in console/LICENSES/project-maya-MIT.txt.
//! The streaming detokenizer: the incremental one emits exactly what the old re-decode did,
//! token by token, and its cost per token does not grow with the reply. The donor skips these
//! tests without a real pack; here they run on a synthetic byte-level BPE tokenizer trained in
//! code on the test texts, so multi-byte characters are split across tokens.

#[path = "prm04_common.rs"]
mod common;

use std::time::Instant;

use common::{train, Rng};
use console_tokenizer::bpe::{Tokenize, Tokenizer};
use console_tokenizer::byte_map;
use console_tokenizer::byte_tok::ByteTokenizer;
use console_tokenizer::detok::Detokenizer;

const SPLIT_TEXT: &str = "Gr\u{fc}\u{df}e aus Z\u{fc}rich! \u{4F60}\u{597D}\u{FF0C}\u{4E16}\u{754C}\u{3002}\u{65E5}\u{672C}\u{8A9E}\u{306E}\u{30C6}\u{30AD}\u{30B9}\u{30C8} \u{1F30A}\u{1F98A}\u{1F469}\u{200D}\u{1F4BB} and ASCII code: def f(x): return x**2\n";
const FOX: &str = "The quick brown fox jumps over the lazy dog. ";

/// A synthetic qwen35 tokenizer: two hand-made merges of rank 0 and 1 that join an ASCII
/// byte with the lead byte of a multi-byte character ("r" with the first byte of "\u{fc}",
/// and a space with the first byte of a four-byte emoji), so characters are split across
/// tokens as a real vocabulary splits them; then 400 merges trained on the two test texts;
/// then two special literals (type 4 and type 3).
fn synthetic() -> Tokenizer {
    let corpus = [SPLIT_TEXT, SPLIT_TEXT, FOX, FOX];
    let trained = train("qwen35", &corpus, 400);
    let lead_u = byte_map::byte_to_char(0xC3);
    let lead_emoji = byte_map::byte_to_char(0xF0);
    let space = byte_map::byte_to_char(b' ');
    let split_merges = [format!("r {lead_u}"), format!("{space} {lead_emoji}")];
    let mut merges: Vec<String> = split_merges.to_vec();
    merges.extend(trained.merges);
    let mut tokens = trained.tokens;
    for tok in [format!("r{lead_u}"), format!("{space}{lead_emoji}")] {
        if !tokens.contains(&tok) {
            tokens.push(tok);
        }
    }
    let n_plain = tokens.len();
    tokens.extend(["<think>", "<|im_end|>"].map(String::from));
    let mut types = vec![1i64; n_plain];
    types.extend([4, 3]);
    Tokenizer::new(tokens, &merges, Some(types), "qwen35", None).expect("synthetic")
}

/// The pre-0.1.22 algorithm: re-decode every generated id, hold a trailing U+FFFD.
struct OldDetokenizer<'a> {
    tok: &'a Tokenizer,
    ids: Vec<u32>,
    sent: usize,
}

impl<'a> OldDetokenizer<'a> {
    fn new(tok: &'a Tokenizer) -> Self {
        Self {
            tok,
            ids: Vec::new(),
            sent: 0,
        }
    }

    fn push(&mut self, t: u32) -> String {
        self.ids.push(t);
        let text = self.tok.decode(&self.ids).expect("decodes");
        if text.ends_with('\u{FFFD}') {
            return String::new();
        }
        let delta: String = text.chars().skip(self.sent).collect();
        self.sent = text.chars().count();
        delta
    }
}

/// The same text as the old re-decode, never behind it, and never ahead of what the ids so
/// far decode to.
fn same_stream(tok: &Tokenizer, ids: &[u32]) {
    let mut a = OldDetokenizer::new(tok);
    let mut b = Detokenizer::new(tok);
    assert!(b.is_incremental());
    let mut old = String::new();
    let mut new = String::new();
    for (i, &t) in ids.iter().enumerate() {
        old += &a.push(t);
        new += &b.push(t).expect("push");
        assert!(
            new.starts_with(&old),
            "token {i} ({t}): behind the old stream"
        );
        let so_far = tok.decode(&ids[..=i]).expect("decodes");
        assert!(
            so_far.starts_with(&new),
            "token {i} ({t}): ahead of the ids"
        );
    }
    if !tok.decode(ids).expect("decodes").ends_with('\u{FFFD}') {
        assert_eq!(old, new);
    }
}

// Donor: serve/test_detok.py::Detok::test_text_with_split_characters
#[test]
fn detok_text_with_split_characters() {
    let tok = synthetic();
    let text = SPLIT_TEXT.repeat(40);
    let ids = tok.encode(&text, false, &[]).expect("encodes");
    // The test only means something if some token ends inside a multi-byte character.
    let split = ids.iter().any(|&t| {
        let raw = tok.token_bytes(t).expect("bytes");
        std::str::from_utf8(&raw).is_err()
    });
    assert!(
        split,
        "no token splits a character; the test would be vacuous"
    );
    same_stream(&tok, &ids);
    // And the whole stream is the text.
    let mut d = Detokenizer::new(&tok);
    let streamed: String = ids.iter().map(|&t| d.push(t).expect("push")).collect();
    assert_eq!(streamed, text);
}

// Donor: serve/test_detok.py::Detok::test_random_ids_and_broken_bytes
#[test]
fn detok_random_ids_and_broken_bytes() {
    let tok = synthetic();
    let mut rng = Rng::new(5);
    let n = tok.n_vocab();
    let mut saw_replacement = false;
    for _ in 0..20 {
        // Random ids: split and invalid UTF-8 sequences everywhere (no U+FFFD token itself).
        let ids: Vec<u32> = (0..300)
            .map(|_| rng.below(n) as u32)
            .filter(|&t| {
                !tok.decode(&[t]).expect("decodes").contains('\u{FFFD}')
                    || tok.token_bytes(t).expect("bytes").len() < 3
            })
            .collect();
        saw_replacement |= tok.decode(&ids).expect("decodes").contains('\u{FFFD}');
        same_stream(&tok, &ids);
    }
    assert!(saw_replacement, "random ids never produced invalid UTF-8");
}

// Donor: serve/test_detok.py::Detok::test_constant_cost
#[test]
fn detok_constant_cost() {
    let tok = synthetic();
    let ids = tok.encode(&FOX.repeat(2000), false, &[]).expect("encodes");
    assert!(ids.len() >= 16_100, "only {} ids", ids.len());
    let ids = &ids[..16_384];
    let mut d = Detokenizer::new(&tok);
    for &t in &ids[..1024] {
        d.push(t).expect("push");
    }
    let t0 = Instant::now();
    for &t in &ids[1024..1124] {
        d.push(t).expect("push");
    }
    let early = t0.elapsed().as_secs_f64();
    for &t in &ids[1124..16_000] {
        d.push(t).expect("push");
    }
    let t0 = Instant::now();
    for &t in &ids[16_000..16_100] {
        d.push(t).expect("push");
    }
    let late = t0.elapsed().as_secs_f64();
    assert!(
        late / 100.0 < 0.0002,
        "a token after 16K tokens costs more than 0.2 ms"
    );
    assert!(late < early * 5.0 + 0.002);
}

#[test]
fn byte_tokenizer_keeps_the_redecode() {
    let bt = ByteTokenizer::new();
    let mut d = Detokenizer::new(&bt);
    assert!(!d.is_incremental());
    // U+00E9 is C3 A9: the first byte alone decodes to U+FFFD, so nothing is emitted.
    let pushed: Vec<String> = [b'a' as u32, 0xC3, 0xA9, 257, 0xE4]
        .iter()
        .map(|&t| d.push(t).expect("push"))
        .collect();
    assert_eq!(pushed, ["a", "", "\u{e9}", "<|im_end|>", ""]);
    // A held invalid byte followed by ASCII: the old algorithm emits U+FFFD and the letter.
    assert_eq!(d.push(b'x' as u32).expect("push"), "\u{FFFD}x");
    // An id past the specials is the donor's IndexError, and it stays recorded.
    let err = d.push(300).expect_err("index");
    assert_eq!(err.python_type(), "IndexError");
    assert!(d.push(b'y' as u32).is_err());
}

#[test]
fn incremental_errors_leave_the_decoder_unchanged() {
    let tok = synthetic();
    let mut d = Detokenizer::new(&tok);
    let snow = tok.encode("\u{2603}", false, &[]).expect("encodes");
    assert!(snow.len() > 1, "the snowman is split across byte tokens");
    let (first, rest) = snow.split_first().expect("ids");
    assert_eq!(d.push(*first).expect("push"), "");
    assert!(d.push(u32::MAX).is_err());
    let tail: String = rest.iter().map(|&t| d.push(t).expect("push")).collect();
    assert_eq!(tail, "\u{2603}");
}

#[test]
fn detokenizer_over_an_arc() {
    let tok = std::sync::Arc::new(synthetic());
    let ids = tok.encode("ok \u{1F30A}", false, &[]).expect("encodes");
    let mut d = Detokenizer::new(std::sync::Arc::clone(&tok));
    let out: String = ids.iter().map(|&t| d.push(t).expect("push")).collect();
    assert_eq!(out, "ok \u{1F30A}");
}
