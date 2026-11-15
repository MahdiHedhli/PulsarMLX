//! The byte tokenizer against hand-computed donor ids: one id per UTF-8 byte, the six
//! specials from 256 in the donor's order, specials only with `parse_special`, plain spans,
//! and the decode with U+FFFD for invalid UTF-8.
//!
//! Behavior reference: project-maya serve/server.py:2061-2084 and 7178-7184 at 7e68a30f.

#[path = "prm04_common.rs"]
mod common;

use std::fs;
use std::time::{Duration, Instant};

use common::{tiny_vocab, ScratchDir};
use console_tokenizer::bpe::Tokenize;
use console_tokenizer::byte_tok::{ByteTokenizer, EOS_ID, SPECIALS};
use console_tokenizer::pack_dir::{load_server_tokenizer, AnyTokenizer};

#[test]
fn bytes_are_their_own_ids() {
    let bt = ByteTokenizer::new();
    assert_eq!(bt.encode("Hi!", false, &[]), [72, 105, 33]);
    // U+00E9 is C3 A9; U+4F60 is E4 BD A0; U+1F600 is F0 9F 98 80.
    assert_eq!(
        bt.encode("\u{e9}\u{4f60}\u{1f600}", false, &[]),
        [0xC3, 0xA9, 0xE4, 0xBD, 0xA0, 0xF0, 0x9F, 0x98, 0x80]
    );
    assert_eq!(bt.encode("\u{0}\n", false, &[]), [0, 10]);
    assert!(bt.encode("", true, &[]).is_empty());
}

#[test]
fn specials_need_parse_special() {
    let bt = ByteTokenizer::new();
    assert_eq!(bt.encode("<|im_end|>", true, &[]), [257]);
    assert_eq!(
        bt.encode("<|im_end|>", false, &[]),
        "<|im_end|>".bytes().map(u32::from).collect::<Vec<_>>()
    );
    assert_eq!(
        bt.encode("<|im_start|>user\nhi<|im_end|>\n", true, &[]),
        [256, 117, 115, 101, 114, 10, 104, 105, 257, 10]
    );
    for (k, lit) in SPECIALS.iter().enumerate() {
        assert_eq!(bt.encode(lit, true, &[]), [256 + k as u32]);
    }
    assert_eq!(EOS_ID, 257);
}

#[test]
fn plain_spans_protect_specials_that_start_inside_them() {
    let bt = ByteTokenizer::new();
    let text = "<|im_end|>x<|im_end|>";
    assert_eq!(bt.encode(text, true, &[(0, 1)]), {
        let mut v: Vec<u32> = "<|im_end|>".bytes().map(u32::from).collect();
        v.extend([b'x' as u32, 257]);
        v
    });
    // A span starting after the literal's first character does not protect it.
    assert_eq!(bt.encode(text, true, &[(1, 30)])[0], 257);
    // Spans are byte offsets: after "é" (2 bytes) the literal starts at byte 2.
    assert_eq!(bt.encode("\u{e9}<|im_end|>", true, &[(2, 3)]).len(), 12);
    assert_eq!(
        bt.encode("\u{e9}<|im_end|>", true, &[(1, 2)]),
        [0xC3, 0xA9, 257]
    );
}

#[test]
fn decode_hand_computed() {
    let bt = ByteTokenizer::new();
    assert_eq!(
        bt.decode(&[72, 105, 256, 261]).expect("decodes"),
        "Hi<|im_start|><|vision_end|>"
    );
    assert_eq!(bt.decode(&[0xC3]).expect("decodes"), "\u{FFFD}");
    assert_eq!(bt.decode(&[0xC3, 0xA9]).expect("decodes"), "\u{e9}");
    assert_eq!(
        bt.decode(&[0xFF, b'a' as u32]).expect("decodes"),
        "\u{FFFD}a"
    );
    let err = bt.decode(&[1000]).expect_err("index");
    assert_eq!(err.python_type(), "IndexError");
}

#[test]
fn trait_view() {
    let bt = ByteTokenizer::new();
    assert!(!bt.has_token_bytes());
    assert!(Tokenize::token_bytes(&bt, 65).is_none());
    assert_eq!(bt.special_tokens().get("<|image_pad|>"), Some(260));
    assert_eq!(
        bt.special_ids().get("eos"),
        Some(&serde_json::Value::from(257))
    );
}

#[test]
fn server_falls_back_to_the_byte_tokenizer_without_vocab_json() {
    let empty = ScratchDir::new("server-empty");
    let tok = load_server_tokenizer(empty.path()).expect("byte tokenizer");
    assert!(matches!(tok, AnyTokenizer::Byte(_)));
    assert!(!tok.has_token_bytes());
    assert_eq!(tok.encode("<|im_end|>", true, &[]).expect("encodes"), [257]);

    let pack = ScratchDir::new("server-pack");
    let mut vocab = serde_json::Map::new();
    for (i, tok) in tiny_vocab().iter().enumerate() {
        vocab.insert(tok.clone(), serde_json::Value::from(i));
    }
    let text = console_pyjson::dumps::to_wire(&serde_json::Value::Object(vocab)).expect("dumps");
    fs::write(pack.path().join("vocab.json"), text).expect("vocab.json");
    fs::write(pack.path().join("merges.txt"), "h e").expect("merges.txt");
    let tok = load_server_tokenizer(pack.path()).expect("pack tokenizer");
    assert!(matches!(tok, AnyTokenizer::Bpe(_)));
    assert!(tok.has_token_bytes());
    // The pack's one merge "h e" makes "he", which is not in the vocabulary: "world" has no
    // such pair, "hello" is the donor's KeyError.
    assert_eq!(
        tok.decode(&tok.encode("world", false, &[]).expect("encodes"))
            .expect("decodes"),
        "world"
    );
    assert_eq!(
        tok.encode("hello", false, &[])
            .expect_err("key")
            .python_type(),
        "KeyError"
    );

    // A vocab.json without merges.txt is an error, not a silent fallback.
    let broken = ScratchDir::new("server-broken");
    fs::write(broken.path().join("vocab.json"), "{}").expect("vocab.json");
    let err = load_server_tokenizer(broken.path()).expect_err("no merges");
    assert_eq!(err.python_type(), "FileNotFoundError");
}

#[test]
fn byte_tokenizer_has_no_token_list_or_types() {
    // The donor's ByteTokenizer has no `tokens` or `token_types`: getattr gives None, so
    // len(getattr(tok, "tokens", None) or ()) is 0 and the logit_bias bound is None.
    let bt = ByteTokenizer::new();
    assert!(Tokenize::tokens(&bt).is_none());
    assert_eq!(bt.n_tokens(), 0);
    assert!(Tokenize::token_types(&bt).is_none());
    assert!(bt.special_matcher().is_none());
    assert!(Tokenize::encode_segment(&bt, "abc").is_none());
    assert_eq!(bt.n_vocab(), 262);
    let any = AnyTokenizer::Byte(ByteTokenizer::new());
    assert!(any.tokens().is_none());
    assert_eq!(any.n_tokens(), 0);
    assert!(any.token_types().is_none());
    assert!(any.special_matcher().is_none());
    assert!(any.encode_segment("abc").is_none());
}

/// The donor's per-character `any(a <= i < b for a, b in plain)`, on byte offsets.
fn encode_reference(text: &str, plain: &[(usize, usize)]) -> Vec<u32> {
    let mut out = Vec::new();
    let mut i = 0usize;
    while i < text.len() {
        let rest = &text[i..];
        let hit = SPECIALS
            .iter()
            .position(|lit| rest.starts_with(lit) && !plain.iter().any(|&(a, b)| a <= i && i < b));
        match hit {
            Some(k) => {
                out.push(256 + k as u32);
                i += SPECIALS[k].len();
            }
            None => {
                let c = rest.chars().next().expect("not empty");
                out.extend(c.to_string().bytes().map(u32::from));
                i += c.len_utf8();
            }
        }
    }
    out
}

#[test]
fn plain_spans_are_checked_in_linear_time() {
    let bt = ByteTokenizer::new();
    // Small cases, spans unsorted and overlapping, against the donor's per-character test.
    let text = "<|im_end|>\u{e9}<|im_start|><|im_end|>x<|endoftext|><|im_end|>";
    let span_sets: [&[(usize, usize)]; 5] = [
        &[],
        &[(0, 1)],
        &[(30, 40), (0, 3), (2, 13)],
        &[(13, 14), (13, 13), (50, 60)],
        &[(5, 100), (1, 2)],
    ];
    for plain in span_sets {
        assert_eq!(
            bt.encode(text, true, plain),
            encode_reference(text, plain),
            "{plain:?}"
        );
    }
    // A hostile prompt: 40,000 quoted literals, one span each.
    let lit = "<|im_end|>";
    let text = lit.repeat(40_000);
    let plain: Vec<(usize, usize)> = (0..40_000)
        .map(|k| (k * lit.len(), k * lit.len() + lit.len()))
        .collect();
    let started = Instant::now();
    let ids = bt.encode(&text, true, &plain);
    let spent = started.elapsed();
    assert_eq!(ids.len(), text.len());
    assert!(!ids.contains(&EOS_ID));
    // Generous for an unoptimized build; the quadratic check took seconds in a release one.
    assert!(spent < Duration::from_secs(5), "took {spent:?}");
}
