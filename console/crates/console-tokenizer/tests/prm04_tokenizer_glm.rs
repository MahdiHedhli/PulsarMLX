// Provenance: translated from project-maya tools/test_tokenizer_glm.py at 7e68a30f (MIT); license text in console/LICENSES/project-maya-MIT.txt.
//! The glm4/glm5 pre-tokenizer, `ignore_merges`, `from_dir`, plain spans and the scheme guard,
//! checked on synthetic vocabularies built in code (the byte alphabet plus a handful of
//! constructed tokens). No model is used.

#[path = "prm04_common.rs"]
mod common;

use std::fs;

use common::{alphabet_tokens, tiny_vocab, ScratchDir};
use console_tokenizer::bpe::Tokenizer;
use console_tokenizer::pack_dir::from_dir;
use console_tokenizer::pretok::{PreScheme, PreTokenizer, GLM_PATTERN, QWEN35_PATTERN};

fn glm5() -> Tokenizer {
    Tokenizer::new(tiny_vocab(), &[] as &[&str], None, "glm5", None).expect("glm5 tokenizer")
}

fn owned(pieces: Vec<&str>) -> Vec<String> {
    pieces.into_iter().map(String::from).collect()
}

// Donor: tools/test_tokenizer_glm.py::GlmPatternTest::test_regex_is_the_chatglm4_transcription
#[test]
fn glm_pattern_regex_is_the_chatglm4_transcription() {
    // The two load-bearing differences from qwen35, as substrings.
    assert!(GLM_PATTERN.contains(r"\p{N}{1,3}"));
    assert!(!GLM_PATTERN.contains(r"\p{M}"));
    assert!(QWEN35_PATTERN.contains(r"\p{N}"));
    assert!(QWEN35_PATTERN.contains(r"\p{M}"));
    // The shared spine is the same shape.
    assert!(GLM_PATTERN.contains(r"(?:'[sS]|'[tT]|'[rR][eE]|'[vV][eE]|'[mM]|'[lL][lL]|'[dD])"));
    // Stronger than the donor: the whole transcription, character for character.
    assert_eq!(
        GLM_PATTERN,
        concat!(
            r"(?:'[sS]|'[tT]|'[rR][eE]|'[vV][eE]|'[mM]|'[lL][lL]|'[dD])",
            r"|[^\r\n\p{L}\p{N}]?\p{L}+|\p{N}{1,3}| ?[^\s\p{L}\p{N}]+[\r\n]*",
            r"|\s*[\r\n]+|\s+(?!\S)|\s+"
        )
    );
}

// Donor: tools/test_tokenizer_glm.py::GlmPatternTest::test_pieces_are_lossless
#[test]
fn glm_pattern_pieces_are_lossless() {
    let tk = glm5();
    let corpus = [
        "hello world",
        "plain text 12345 and 9876543210",
        "UTF-8: h\u{e9}llo w\u{f6}rld, combining a\u{301} and e\u{301}",
        "emoji \u{1F44D}\u{1F3FD} and CJK \u{4F60}\u{597D}\u{4E16}\u{754C}",
        "tabs\tand\nnewlines\r\n  spaces   ",
        "contractions: don't I'll we've I'm",
        "punctuation!!! ...\u{FF1F}\u{3002}\u{FF0C}\u{3001}",
    ];
    for text in corpus {
        let pieces = tk.pretokenize(text).expect("splits");
        assert_eq!(
            pieces.concat(),
            text,
            "the GLM split dropped or reordered a character"
        );
        assert!(pieces.iter().all(|p| !p.is_empty()));
    }
}

// Donor: tools/test_tokenizer_glm.py::GlmPatternTest::test_digit_grouping_3_plus_1
#[test]
fn glm_pattern_digit_grouping_3_plus_1() {
    let tk = glm5();
    assert_eq!(
        tk.pretokenize("9876543210").expect("splits"),
        ["987", "654", "321", "0"]
    );
    let qwen = PreTokenizer::new(PreScheme::Qwen35).expect("qwen35");
    assert_eq!(
        owned(qwen.findall("9876543210").expect("splits")),
        "9876543210".chars().map(String::from).collect::<Vec<_>>()
    );
}

// Donor: tools/test_tokenizer_glm.py::GlmPatternTest::test_ignore_merges_emits_whole_vocab_hits
#[test]
fn glm_pattern_ignore_merges_emits_whole_vocab_hits() {
    let tk = glm5();
    let ids = tk.encode("hello", false, &[]).expect("encodes");
    assert_eq!(ids.len(), 1);
    assert_eq!(tk.tokens()[ids[0] as usize], "hello");
    assert!(tk.ignore_merges());
}

// Donor: tools/test_tokenizer_glm.py::GlmPatternTest::test_ignore_merges_falls_back_to_bpe_off_vocab
#[test]
fn glm_pattern_ignore_merges_falls_back_to_bpe_off_vocab() {
    let tk = glm5();
    let ids = tk.encode("helio", false, &[]).expect("encodes");
    assert!(!ids.is_empty());
    let raw: Vec<u8> = ids
        .iter()
        .flat_map(|&i| tk.token_bytes(i).expect("bytes"))
        .collect();
    assert_eq!(String::from_utf8(raw).expect("utf-8"), "helio");
    // With no merges, BPE bottoms out at one byte token per character.
    assert_eq!(ids.len(), 5);
}

// Donor: tools/test_tokenizer_glm.py::GlmPatternTest::test_qwen_path_has_no_ignore_merges
#[test]
fn glm_pattern_qwen_path_has_no_ignore_merges() {
    let tk = Tokenizer::new(tiny_vocab(), &[] as &[&str], None, "qwen35", None).expect("qwen35");
    let ids = tk.encode("hello", false, &[]).expect("encodes");
    assert_ne!(ids.len(), 1);
    assert_eq!(ids.len(), 5);
    assert!(!tk.ignore_merges());
}

/// The donor's `FromDir.write`: a pack directory with the tiny vocabulary, one merge, all
/// token types 1, and `tokenizer.json` when `meta` is given.
fn write_pack(meta: Option<&str>) -> ScratchDir {
    let dir = ScratchDir::new("fromdir");
    let tokens = tiny_vocab();
    let mut vocab = serde_json::Map::new();
    for (i, tok) in tokens.iter().enumerate() {
        vocab.insert(tok.clone(), serde_json::Value::from(i));
    }
    let vocab_json =
        console_pyjson::dumps::to_python_default(&serde_json::Value::Object(vocab)).expect("dumps");
    fs::write(dir.path().join("vocab.json"), vocab_json).expect("vocab.json");
    fs::write(dir.path().join("merges.txt"), "h e").expect("merges.txt");
    let types = format!("[{}]", vec!["1"; tokens.len()].join(", "));
    fs::write(dir.path().join("token_type.json"), types).expect("token_type.json");
    if let Some(meta) = meta {
        fs::write(dir.path().join("tokenizer.json"), meta).expect("tokenizer.json");
    }
    dir
}

// Donor: tools/test_tokenizer_glm.py::FromDir::test_glm_pack_groups_digits
#[test]
fn from_dir_glm_pack_groups_digits() {
    let dir = write_pack(Some(
        "{\"pre\": \"glm4\", \"special_ids\": {\"tokenizer.ggml.eos_token_id\": 3}}",
    ));
    let tk = from_dir(dir.path()).expect("loads");
    assert_eq!(tk.pre(), PreScheme::Glm4);
    let ids = console_pyjson::dumps::to_wire(&serde_json::Value::Object(
        console_tokenizer::bpe::Tokenize::special_ids(&tk).clone(),
    ))
    .expect("dumps");
    assert_eq!(ids, "{\"tokenizer.ggml.eos_token_id\": 3}");
    assert_eq!(
        tk.pretokenize("504 9876").expect("splits"),
        ["504", " ", "987", "6"]
    );
    assert_eq!(tk.n_vocab(), tiny_vocab().len());
    assert_eq!(tk.n_merges(), 1);
}

// Donor: tools/test_tokenizer_glm.py::FromDir::test_without_tokenizer_json_stays_qwen35
#[test]
fn from_dir_without_tokenizer_json_stays_qwen35() {
    let dir = write_pack(None);
    let tk = from_dir(dir.path()).expect("loads");
    assert_eq!(tk.pre(), PreScheme::Qwen35);
    assert!(console_tokenizer::bpe::Tokenize::special_ids(&tk).is_empty());
}

// Donor: tools/test_tokenizer_glm.py::PlainSpans::test_spans
#[test]
fn plain_spans_spans() {
    let mut tokens = alphabet_tokens();
    tokens.extend(["<think>", "<|user|>"].map(String::from));
    let mut types = vec![1i64; tokens.len() - 2];
    types.extend([4, 3]);
    let think = (tokens.len() - 2) as u32;
    let user = (tokens.len() - 1) as u32;
    let tk = Tokenizer::new(tokens, &[] as &[&str], Some(types), "glm5", None).expect("builds");

    let text = "<|user|>a<think>b<|user|>c<think>";
    let all = tk.encode(text, true, &[]).expect("encodes");
    assert_eq!(all.iter().filter(|&&t| t == user).count(), 2);
    // The middle <think> (9..16) and <|user|> (17..25) are plain text.
    let got = tk
        .encode(text, true, &[(9, 16), (17, 25)])
        .expect("encodes");
    let literals: Vec<u32> = got
        .iter()
        .copied()
        .filter(|t| *t == think || *t == user)
        .collect();
    assert_eq!(literals, [user, think]);
    assert_eq!(got.first(), Some(&user));
    assert_eq!(got.last(), Some(&think));
    let middle: Vec<u8> = got[1..got.len() - 1]
        .iter()
        .flat_map(|&t| tk.token_bytes(t).expect("bytes"))
        .collect();
    assert_eq!(middle, b"a<think>b<|user|>c");
    // Unsorted spans, and no spans at all, as before.
    assert_eq!(
        tk.encode(text, true, &[(17, 25), (9, 16)])
            .expect("encodes"),
        got
    );
    assert_eq!(tk.encode(text, true, &[]).expect("encodes"), all);
}

// Donor: tools/test_tokenizer_glm.py::PreSchemeGuard::test_unknown_scheme_refused
#[test]
fn pre_scheme_guard_unknown_scheme_refused() {
    let err = Tokenizer::new(alphabet_tokens(), &[] as &[&str], None, "llama3", None)
        .expect_err("refused");
    assert_eq!(err.python_type(), "ValueError");
    assert_eq!(
        err.to_string(),
        "the 'llama3' pre-tokenizer is not transcribed; known: qwen35, glm4, glm5, deepseek3, minimax"
    );
}

// Donor: tools/test_tokenizer_glm.py::PreSchemeGuard::test_glm_schemes_accepted
#[test]
fn pre_scheme_guard_glm_schemes_accepted() {
    for pre in ["glm4", "glm5"] {
        let tk =
            Tokenizer::new(alphabet_tokens(), &[] as &[&str], None, pre, None).expect("accepted");
        assert_eq!(tk.pre().name(), pre);
    }
}
