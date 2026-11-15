//! Reading a pack's `tokenizer/` directory, created by the tests: file formats, defaults,
//! universal newlines, the merges-file trailing-newline refusal, token types, and the
//! donor's errors for malformed files.
//!
//! Behavior reference: project-maya tools/strata_tokenizer.py:201-214 at 7e68a30f.

#[path = "prm04_common.rs"]
mod common;

use std::fs;
use std::path::Path;

use common::{alphabet_tokens, ScratchDir};
use console_tokenizer::bpe::Tokenize;
use console_tokenizer::pack_dir::from_dir;
use console_tokenizer::pretok::PreScheme;

fn vocab_json(tokens: &[String]) -> String {
    let mut vocab = serde_json::Map::new();
    for (i, tok) in tokens.iter().enumerate() {
        vocab.insert(tok.clone(), serde_json::Value::from(i));
    }
    console_pyjson::dumps::to_wire(&serde_json::Value::Object(vocab)).expect("dumps")
}

fn write(dir: &Path, name: &str, text: &str) {
    fs::write(dir.join(name), text).expect("writes");
}

fn pack(tokens: &[String], merges: &str) -> ScratchDir {
    let dir = ScratchDir::new("pack");
    write(dir.path(), "vocab.json", &vocab_json(tokens));
    write(dir.path(), "merges.txt", merges);
    dir
}

fn with_ab() -> Vec<String> {
    let mut tokens = alphabet_tokens();
    tokens.push("ab".into());
    tokens
}

#[test]
fn merges_and_crlf() {
    let dir = pack(&with_ab(), "a b");
    let tk = from_dir(dir.path()).expect("loads");
    assert_eq!(tk.encode("ab", false, &[]).expect("encodes"), [256]);
    // Universal newlines: "\r\n" and "\r" split merges like "\n".
    let mut tokens = with_ab();
    tokens.push("abab".into());
    tokens.push("cd".into());
    let dir = pack(&tokens, "a b\r\nab ab\rc d");
    let tk = from_dir(dir.path()).expect("loads");
    assert_eq!(tk.n_merges(), 3);
    assert_eq!(tk.encode("abab", false, &[]).expect("encodes"), [257]);
}

#[test]
fn trailing_newline_in_merges_is_refused() {
    let dir = pack(&with_ab(), "a b\n");
    let err = from_dir(dir.path()).expect_err("empty merge");
    assert_eq!(err.to_string(), "merge 1 is not a pair: ''");
}

#[test]
fn empty_merges_file_is_one_empty_merge() {
    let dir = pack(&alphabet_tokens(), "");
    let err = from_dir(dir.path()).expect_err("empty merge");
    assert_eq!(err.to_string(), "merge 0 is not a pair: ''");
}

#[test]
fn token_types_and_special_ids() {
    let mut tokens = alphabet_tokens();
    tokens.extend(["ab", "<|endoftext|>", "<tool_call>"].map(String::from));
    let dir = pack(&tokens, "a b");
    let mut types = vec!["1"; 257];
    types.extend(["3", "4"]);
    write(
        dir.path(),
        "token_type.json",
        &format!("[{}]", types.join(",")),
    );
    write(
        dir.path(),
        "tokenizer.json",
        "{\"pre\": \"deepseek3\", \"special_ids\": {\"eos\": 257, \"bos\": null}}",
    );
    let tk = from_dir(dir.path()).expect("loads");
    assert_eq!(tk.pre(), PreScheme::Deepseek3);
    assert_eq!(tk.token_types().map(<[i64]>::len), Some(259));
    assert_eq!(tk.special_tokens().get("<|endoftext|>"), Some(257));
    assert_eq!(tk.special_tokens().get("<tool_call>"), Some(258));
    let ids = console_pyjson::dumps::to_wire(&serde_json::Value::Object(tk.special_ids().clone()))
        .expect("dumps");
    assert_eq!(ids, "{\"eos\": 257, \"bos\": null}");
    assert_eq!(
        tk.encode("<tool_call>ab<|endoftext|>", false, &[])
            .expect("encodes"),
        {
            let mut v = vec![258, 256];
            v.extend("<|endoftext|>".bytes().map(|b| {
                tk.id_of(&console_tokenizer::byte_map::byte_to_char(b).to_string())
                    .expect("byte token")
            }));
            v
        }
    );
}

#[test]
fn falsy_special_ids_become_empty() {
    for meta in [
        "{\"special_ids\": null}",
        "{\"special_ids\": {}}",
        "{\"special_ids\": 0}",
        "{}",
    ] {
        let dir = pack(&alphabet_tokens(), "\u{120} \u{120}");
        write(dir.path(), "tokenizer.json", meta);
        // The merge "Ġ Ġ" names two byte tokens; "ĠĠ" is not in the vocabulary, so a double
        // space is a KeyError, but loading succeeds.
        let tk = from_dir(dir.path()).expect("loads");
        assert!(tk.special_ids().is_empty(), "{meta}");
        assert_eq!(tk.pre(), PreScheme::Qwen35);
    }
}

#[test]
fn unknown_pre_in_tokenizer_json() {
    let dir = pack(&alphabet_tokens(), "\u{120} \u{120}");
    write(dir.path(), "tokenizer.json", "{\"pre\": \"llama-bpe\"}");
    let err = from_dir(dir.path()).expect_err("refused");
    assert_eq!(
        err.to_string(),
        "the 'llama-bpe' pre-tokenizer is not transcribed; known: qwen35, glm4, glm5, deepseek3, minimax"
    );
    write(dir.path(), "tokenizer.json", "{\"pre\": null}");
    let err = from_dir(dir.path()).expect_err("refused");
    assert!(err.to_string().starts_with("the None pre-tokenizer"));
}

#[test]
fn vocab_ids_follow_python_list_assignment() {
    // Negative ids count from the end, as tokens[-1] = s does.
    let dir = ScratchDir::new("neg");
    let tokens = alphabet_tokens();
    let mut vocab = serde_json::Map::new();
    for (i, tok) in tokens.iter().enumerate() {
        let id = if i == 255 { -1 } else { i as i64 };
        vocab.insert(tok.clone(), serde_json::Value::from(id));
    }
    write(
        dir.path(),
        "vocab.json",
        &console_pyjson::dumps::to_wire(&serde_json::Value::Object(vocab)).expect("dumps"),
    );
    write(dir.path(), "merges.txt", "\u{120} \u{120}");
    let tk = from_dir(dir.path()).expect("loads");
    assert_eq!(tk.tokens(), tokens.as_slice());

    // An id past the end.
    write(dir.path(), "vocab.json", "{\"a\": 0, \"b\": 2}");
    let err = from_dir(dir.path()).expect_err("index");
    assert_eq!(err.to_string(), "list assignment index out of range");
    assert_eq!(err.python_type(), "IndexError");

    // Two ids for one slot leave two empty slots: the duplicate refusal.
    write(dir.path(), "vocab.json", "{\"a\": 0, \"b\": 0, \"c\": 0}");
    let err = from_dir(dir.path()).expect_err("dup");
    assert_eq!(
        err.to_string(),
        "vocabulary has duplicate tokens: 3 entries, 2 unique"
    );

    // A float id.
    write(dir.path(), "vocab.json", "{\"a\": 0.0}");
    let err = from_dir(dir.path()).expect_err("type");
    assert_eq!(
        err.to_string(),
        "list indices must be integers or slices, not float"
    );

    // A list is not a vocabulary.
    write(dir.path(), "vocab.json", "[\"a\"]");
    let err = from_dir(dir.path()).expect_err("attr");
    assert_eq!(err.to_string(), "'list' object has no attribute 'items'");
    assert_eq!(err.python_type(), "AttributeError");
}

#[test]
fn json_errors_are_json_loads_errors() {
    let dir = pack(&alphabet_tokens(), "\u{120} \u{120}");
    write(dir.path(), "tokenizer.json", "{\"pre\": ");
    let err = from_dir(dir.path()).expect_err("json");
    assert_eq!(err.python_type(), "JSONDecodeError");
    assert_eq!(err.to_string(), "Expecting value: line 1 column 9 (char 8)");
    // A UTF-8 byte-order mark is refused, as json.loads refuses it after a utf-8 read.
    write(dir.path(), "tokenizer.json", "\u{feff}{}");
    let err = from_dir(dir.path()).expect_err("bom");
    assert!(err.to_string().starts_with("Unexpected UTF-8 BOM"));
}

#[test]
fn invalid_utf8_is_a_unicode_decode_error() {
    let dir = pack(&alphabet_tokens(), "x");
    fs::write(dir.path().join("merges.txt"), b"\xff").expect("writes");
    let err = from_dir(dir.path()).expect_err("utf-8");
    assert_eq!(err.python_type(), "UnicodeDecodeError");
    assert_eq!(
        err.to_string(),
        "'utf-8' codec can't decode byte 0xff in position 0: invalid start byte"
    );
}

#[test]
fn missing_vocab_is_file_not_found() {
    let dir = ScratchDir::new("missing");
    let err = from_dir(dir.path()).expect_err("missing");
    assert_eq!(err.python_type(), "FileNotFoundError");
    assert!(err
        .to_string()
        .starts_with("[Errno 2] No such file or directory: '"));
    assert!(err.to_string().ends_with("vocab.json'"));
}

#[test]
fn unknown_pre_is_refused_before_the_crate_refusals() {
    // The donor constructor checks `pre` first, so its ValueError comes before this crate's
    // TypeError for a non-object `special_ids` or a non-list `token_type.json`.
    let dir = pack(&alphabet_tokens(), "\u{120} \u{120}");
    write(
        dir.path(),
        "tokenizer.json",
        "{\"pre\": \"gpt2\", \"special_ids\": [1]}",
    );
    write(dir.path(), "token_type.json", "7");
    let err = from_dir(dir.path()).expect_err("refused");
    assert_eq!(err.python_type(), "ValueError");
    assert!(err.to_string().starts_with("the 'gpt2' pre-tokenizer"));
    // With a known `pre`, the crate's own refusal shows.
    write(dir.path(), "tokenizer.json", "{\"special_ids\": [1]}");
    let err = from_dir(dir.path()).expect_err("refused");
    assert_eq!(err.python_type(), "TypeError");
    assert_eq!(
        err.to_string(),
        "special_ids in tokenizer.json is a list, not an object"
    );
}
