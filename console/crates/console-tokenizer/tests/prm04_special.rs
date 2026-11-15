//! Special literals: type 4 (USER_DEFINED) is matched always, type 3 (CONTROL) only with
//! `parse_special`; longest literal first; a literal match that starts inside a plain span,
//! including one straddling the span's end, is encoded as text; `token_bytes` of a literal is
//! its UTF-8 text, also outside the byte alphabet.
//!
//! Behavior reference: project-maya tools/strata_tokenizer.py:171-198, 317-372 at 7e68a30f.

#[path = "prm04_common.rs"]
mod common;

use common::alphabet_tokens;
use console_tokenizer::bpe::{Tokenize, Tokenizer};

struct Fixture {
    tk: Tokenizer,
    im_end: u32,
    im: u32,
    think: u32,
    ds_user: u32,
    plain_token: u32,
}

/// The byte alphabet, then `<|im_end|>` (3), `<|im` (3), `<think>` (4), the DeepSeek-style
/// `<｜User｜>` (4, outside the byte alphabet) and an ordinary type-1 token `ab`.
fn fixture() -> Fixture {
    let mut tokens = alphabet_tokens();
    let base = tokens.len() as u32;
    tokens.extend(
        [
            "<|im_end|>",
            "<|im",
            "<think>",
            "<\u{ff5c}User\u{ff5c}>",
            "ab",
        ]
        .map(String::from),
    );
    let mut types = vec![1i64; base as usize];
    types.extend([3, 3, 4, 4, 1]);
    let tk = Tokenizer::new(tokens, &["a b"], Some(types), "qwen35", None).expect("builds");
    Fixture {
        tk,
        im_end: base,
        im: base + 1,
        think: base + 2,
        ds_user: base + 3,
        plain_token: base + 4,
    }
}

#[test]
fn special_tokens_are_types_3_and_4_in_id_order() {
    let f = fixture();
    let table: Vec<(&str, u32)> = f.tk.special_tokens().iter().collect();
    assert_eq!(
        table,
        [
            ("<|im_end|>", f.im_end),
            ("<|im", f.im),
            ("<think>", f.think),
            ("<\u{ff5c}User\u{ff5c}>", f.ds_user),
        ]
    );
    assert!(!f.tk.special_tokens().contains("ab"));
    assert_eq!(f.tk.id_of("ab"), Some(f.plain_token));
}

#[test]
fn type_4_always_type_3_only_with_parse_special() {
    let f = fixture();
    let text = "x<think>y<|im_end|>";
    let without = f.tk.encode(text, false, &[]).expect("encodes");
    assert!(without.contains(&f.think));
    assert!(!without.contains(&f.im_end));
    assert!(!without.contains(&f.im));
    let with = f.tk.encode(text, true, &[]).expect("encodes");
    assert!(with.contains(&f.think));
    assert_eq!(with.last(), Some(&f.im_end));
    assert_eq!(f.tk.decode(&without).expect("decodes"), text);
    assert_eq!(f.tk.decode(&with).expect("decodes"), text);
}

#[test]
fn longest_literal_wins_and_near_misses_cost_ordinary_tokens() {
    let f = fixture();
    let ids =
        f.tk.encode("<|im_end|><|im_star", true, &[])
            .expect("encodes");
    assert_eq!(ids.first(), Some(&f.im_end));
    // The near miss `<|im_star` matches the shorter literal `<|im`, then `_star` is text.
    assert_eq!(ids.get(1), Some(&f.im));
    assert_eq!(ids.len(), 2 + "_star".len());
}

#[test]
fn literal_straddling_a_span_end_is_text() {
    let f = fixture();
    let text = "ab<think>";
    // The span (1, 4) ends inside `<think>` (2..9); the literal starts inside it, so it is
    // encoded as text with the characters around it.
    let ids = f.tk.encode(text, false, &[(1, 4)]).expect("encodes");
    assert!(!ids.contains(&f.think));
    assert_eq!(f.tk.decode(&ids).expect("decodes"), text);
    // A span that ends where the literal starts does not cover it.
    let ids = f.tk.encode(text, false, &[(0, 2)]).expect("encodes");
    assert_eq!(ids, [f.plain_token, f.think]);
    // A span that starts after the literal's start does not cover it either.
    let ids = f.tk.encode(text, false, &[(3, 9)]).expect("encodes");
    assert_eq!(ids, [f.plain_token, f.think]);
}

#[test]
fn overlapping_and_nested_spans() {
    let f = fixture();
    let text = "<think>a<think>b<think>";
    // The literals start at 0, 8 and 16, all inside (0, 20), so all three are text.
    let ids =
        f.tk.encode(text, false, &[(0, 20), (2, 3)])
            .expect("encodes");
    assert!(!ids.contains(&f.think));
    // A later, wider span extends the reach of an earlier one (the maximum end counts).
    let ids =
        f.tk.encode(text, false, &[(0, 1), (0, 9)])
            .expect("encodes");
    assert_eq!(ids.iter().filter(|&&t| t == f.think).count(), 1);
    assert_eq!(ids.last(), Some(&f.think));
}

#[test]
fn spans_are_byte_offsets() {
    let f = fixture();
    // "é" is two bytes: `<think>` starts at byte 2, code point 1.
    let text = "\u{e9}<think>";
    let ids = f.tk.encode(text, false, &[(2, 3)]).expect("encodes");
    assert!(!ids.contains(&f.think));
    let ids = f.tk.encode(text, false, &[(1, 2)]).expect("encodes");
    assert_eq!(ids.last(), Some(&f.think));
}

#[test]
fn literal_bytes_are_their_text() {
    let f = fixture();
    assert_eq!(
        f.tk.token_bytes(f.ds_user).expect("bytes"),
        "<\u{ff5c}User\u{ff5c}>".as_bytes()
    );
    let ids =
        f.tk.encode("hi <\u{ff5c}User\u{ff5c}>", false, &[])
            .expect("encodes");
    assert_eq!(ids.last(), Some(&f.ds_user));
    assert_eq!(
        f.tk.decode(&ids).expect("decodes"),
        "hi <\u{ff5c}User\u{ff5c}>"
    );
}

#[test]
fn no_token_types_means_no_literals() {
    let mut tokens = alphabet_tokens();
    tokens.push("<think>".into());
    let tk = Tokenizer::new(tokens, &[] as &[&str], None, "qwen35", None).expect("builds");
    assert!(tk.special_tokens().is_empty());
    let ids = tk.encode("<think>", true, &[]).expect("encodes");
    assert_eq!(ids.len(), 7);
    // Without types, token_bytes maps through the byte alphabet; `<think>` is all ASCII.
    let think = tk.id_of("<think>").expect("in vocab");
    assert_eq!(tk.token_bytes(think).expect("bytes"), b"<think>");
}

#[test]
fn empty_token_types_list_is_falsy() {
    let mut tokens = alphabet_tokens();
    tokens.push("<\u{ff5c}x".into());
    let tk = Tokenizer::new(tokens, &[] as &[&str], Some(vec![]), "qwen35", None).expect("builds");
    assert!(tk.special_tokens().is_empty());
    let err = tk.token_bytes(256).expect_err("outside the alphabet");
    assert_eq!(err.python_type(), "KeyError");
}

/// The serving layer's prompt memo (serve/server.py:2167-2187, PRM-08) runs its own copy of
/// the literal loop over `_special_re` and `_encode_segment`; the same loop over the trait's
/// `special_matcher` and `encode_segment` gives the ids of `encode(text, true, plain)`, also
/// where a plain span covers a type-4 literal.
#[test]
fn manual_literal_loop_over_the_trait_matches_encode() {
    let f = fixture();
    let view: &dyn Tokenize = &f.tk;
    let text = "ab<think>x<|im_end|>ab<think><|imz<\u{ff5c}User\u{ff5c}>";
    let think_at = text.find("<think>").expect("present");
    let plain = [(think_at, think_at + 1)];
    let matcher = view.special_matcher().expect("has literals");
    let mut out = Vec::new();
    let mut pos = 0usize;
    let mut plain_end = 0usize;
    let mut upcoming = plain.iter().peekable();
    for (start, end) in matcher.find_all(text) {
        while let Some(&&(a, b)) = upcoming.peek() {
            if a > start {
                break;
            }
            plain_end = plain_end.max(b);
            upcoming.next();
        }
        if start < plain_end {
            continue;
        }
        if start > pos {
            out.extend(
                view.encode_segment(&text[pos..start])
                    .expect("has a segment encoder")
                    .expect("encodes"),
            );
        }
        out.push(
            view.special_tokens()
                .get(&text[start..end])
                .expect("literal"),
        );
        pos = end;
    }
    if pos < text.len() {
        out.extend(
            view.encode_segment(&text[pos..])
                .expect("has a segment encoder")
                .expect("encodes"),
        );
    }
    let want = f.tk.encode(text, true, &plain).expect("encodes");
    assert_eq!(out, want);
    assert_eq!(want.iter().filter(|&&i| i == f.think).count(), 1);
    assert!(want.contains(&f.im_end));
    assert!(want.contains(&f.ds_user));
    // `<|imz` holds the shorter type-3 literal `<|im`.
    assert!(want.contains(&f.im));
    // A segment never matches a literal, even a type-4 one.
    let seg = view
        .encode_segment("<think>")
        .expect("has a segment encoder")
        .expect("encodes");
    assert!(!seg.contains(&f.think));
}
