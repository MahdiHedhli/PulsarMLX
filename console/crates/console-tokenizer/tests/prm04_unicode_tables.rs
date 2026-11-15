//! Pinned differences between Python's `regex` module (and `unicodedata`) and the Rust crates
//! the pre-tokenizers run on. The lead accepted residual Unicode-table differences on
//! 2026-11-14 when a test names and pins each one (lead decision LD24); these are those tests.
//!
//! Behavior reference: project-maya tools/strata_tokenizer.py:56-111 at 7e68a30f.

use console_tokenizer::pretok::{PreScheme, PreTokenizer};

fn split(scheme: PreScheme, text: &str) -> Vec<String> {
    PreTokenizer::new(scheme)
        .expect("compiles")
        .findall(text)
        .expect("splits")
        .into_iter()
        .map(String::from)
        .collect()
}

/// `\s` is Unicode `White_Space`, so the information separators U+001C..U+001F are not
/// whitespace for the pre-tokenizers; Python's `str.isspace` (and the `re` module's `\s`) say
/// they are. The `regex` module's `\s` for a `str` pattern is believed to be `White_Space` as
/// here; if it is not, "!\x1c" would split as ["!", "\x1c"] in the donor.
#[test]
fn whitespace_class_excludes_u001c_to_u001f() {
    for c in ['\u{1c}', '\u{1d}', '\u{1e}', '\u{1f}'] {
        let text = format!("!{c}");
        assert_eq!(
            split(PreScheme::Qwen35, &text),
            std::slice::from_ref(&text),
            "qwen35 {c:?}"
        );
        assert_eq!(
            split(PreScheme::Glm5, &text),
            std::slice::from_ref(&text),
            "glm5 {c:?}"
        );
        assert_eq!(
            split(PreScheme::Minimax, &text),
            std::slice::from_ref(&text),
            "minimax {c:?}"
        );
        // Python's str.isspace, as console-pyjson reproduces it, does include them.
        assert!(console_pyjson::pystr::is_space(c));
    }
    // The White_Space characters themselves are whitespace here.
    assert_eq!(split(PreScheme::Qwen35, "!\u{85}"), ["!", "\u{85}"]);
}

/// The general categories (`\p{L}`, `\p{N}`, `\p{M}`, `\p{P}`, `\p{S}`) come from Unicode
/// 16.0.0, the tables of `regex-syntax` 0.8.11. A letter assigned in Unicode 16 (Todhri
/// U+105C0) is a letter; one assigned in Unicode 17 (Sidetic U+10940) is unassigned here, so
/// it does not join the preceding letter, where a `regex` module with Unicode 17 tables would
/// give one piece.
#[test]
fn letter_classes_use_unicode_16_tables() {
    assert_eq!(split(PreScheme::Qwen35, "a\u{105C0}"), ["a\u{105C0}"]);
    assert_eq!(split(PreScheme::Qwen35, "a\u{10940}"), ["a", "\u{10940}"]);
    assert_eq!(split(PreScheme::Glm4, "a\u{10940}"), ["a", "\u{10940}"]);
}

/// NFC for `minimax` comes from `unicode-normalization` 0.1.26, which carries Unicode 18.0.0
/// tables; CPython 3.14's `unicodedata` carries 16.0.0 (the donor's CI runs Python 3.12, with
/// 15.0.0). Normalization is stable for characters assigned in both versions, so only
/// characters assigned after 16.0 can normalize differently.
#[test]
fn nfc_tables_are_unicode_18() {
    assert_eq!(unicode_normalization::UNICODE_VERSION, (18, 0, 0));
}

/// The case-insensitive contraction group of `minimax` uses simple case folding, so the long
/// s (U+017F) matches `s`. The `regex` module is believed to fold U+017F the same way; this
/// pins the Rust behavior.
#[test]
fn case_insensitive_contraction_folds_long_s() {
    assert_eq!(split(PreScheme::Minimax, "it'\u{17F}"), ["it'\u{17F}"]);
    assert_eq!(split(PreScheme::Minimax, "IT'S"), ["IT'S"]);
}
