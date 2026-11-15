//! `decode(encode(s)) == s` over the donor's boundary corpus (multi-byte UTF-8, emoji,
//! combining marks, whitespace runs, C0 controls) for every pre-tokenizer family, on
//! synthetic vocabularies trained in code; and bounded time on 5,000-character inputs.
//!
//! Behavior reference: project-maya tools/strata_tokenizer.py:9-14 and 433-446 at 7e68a30f.

#[path = "prm04_common.rs"]
mod common;

use std::time::{Duration, Instant};

use common::{alphabet_tokens, train};
use console_tokenizer::bpe::Tokenizer;
use console_tokenizer::pack_dir::from_dir;
use console_tokenizer::pretok::KNOWN_SCHEMES;
use unicode_normalization::UnicodeNormalization;

/// The donor's `--check` corpus, verbatim.
fn boundary_corpus() -> Vec<String> {
    let mut corpus: Vec<String> = [
        "",
        "Hello, world!",
        "  leading and trailing  ",
        "a\n\n\nb",
        "def f(x):\n\treturn x  # comment\n",
        "\u{4f60}\u{597d}\u{ff0c}\u{4e16}\u{754c}",
        "\u{0645}\u{0631}\u{062d}\u{0628}\u{0627}",
        "\u{1f600}\u{1f680}\u{1f1fa}\u{1f1f8}",
        "e\u{0301}\u{0301} combining",
        "\u{0}\u{1}\u{7f} control",
        "\u{a0}non-breaking\u{a0}space",
        "1234567890",
        "MixedCASE_and-dashes",
        "\r\n\r\n",
        "\u{2028}\u{2029}",
    ]
    .map(String::from)
    .to_vec();
    corpus.push("x".repeat(5000));
    corpus
}

/// More boundaries: every C0 control, the U+001C..U+001F separators, CJK with kana for the
/// deepseek3 stage, contractions in both cases, and long digit runs.
fn extra_corpus() -> Vec<String> {
    let c0: String = (0u8..0x20).map(char::from).collect();
    [
        c0.as_str(),
        "a\u{1c}b\u{1d} \u{1e}\n\u{1f}",
        "\u{65e5}\u{672c}\u{8a9e}\u{306e}\u{30c6}\u{30ad}\u{30b9}\u{30c8}123x",
        "IT'S it's We'VE they'll I'D",
        "98765432109876543210",
        "!!//\n\n..\r\n",
        "tab\t\t\tend\u{3000}\u{3000}",
        "\u{1F469}\u{200D}\u{1F4BB} \u{1F44D}\u{1F3FD}",
        "\u{fffd}\u{feff}\u{10ffff}",
    ]
    .map(String::from)
    .to_vec()
}

fn trained_for(pre: &str) -> Tokenizer {
    let corpus = boundary_corpus();
    let refs: Vec<&str> = corpus.iter().map(String::as_str).collect();
    let trained = train(pre, &refs, 200);
    Tokenizer::new(trained.tokens, &trained.merges, None, pre, None).expect("trained tokenizer")
}

#[test]
fn round_trip_every_family_on_the_boundary_corpus() {
    for pre in KNOWN_SCHEMES {
        let tk = trained_for(pre);
        assert!(tk.n_merges() > 20, "{pre}: the trainer found merges");
        for s in boundary_corpus().iter().chain(extra_corpus().iter()) {
            let ids = tk.encode(s, false, &[]).expect("encodes");
            let back = tk.decode(&ids).expect("decodes");
            // minimax normalizes each plain segment to NFC first, so its round trip is to the
            // NFC form (the donor's behavior; "e\u{301}" comes back as "\u{e9}").
            let want: String = if pre == "minimax" {
                s.nfc().collect()
            } else {
                s.clone()
            };
            assert_eq!(
                back,
                want,
                "{pre}: round trip failed for {:?}",
                s.get(..40.min(s.len()))
            );
            let pieces = tk.pretokenize(&want).expect("splits");
            assert_eq!(pieces.concat(), want, "{pre}: lossy split");
        }
    }
}

#[test]
fn minimax_round_trip_is_to_nfc() {
    let tk = trained_for("minimax");
    let ids = tk
        .encode("e\u{301}\u{301} combining", false, &[])
        .expect("encodes");
    assert_eq!(tk.decode(&ids).expect("decodes"), "\u{e9}\u{301} combining");
    let qwen = trained_for("qwen35");
    let ids = qwen
        .encode("e\u{301}\u{301} combining", false, &[])
        .expect("encodes");
    assert_eq!(
        qwen.decode(&ids).expect("decodes"),
        "e\u{301}\u{301} combining"
    );
}

#[test]
fn byte_alphabet_alone_round_trips_with_one_id_per_byte() {
    for pre in ["qwen35", "deepseek3"] {
        let tk =
            Tokenizer::new(alphabet_tokens(), &[] as &[&str], None, pre, None).expect("alphabet");
        for s in boundary_corpus() {
            let ids = tk.encode(&s, true, &[]).expect("encodes");
            assert_eq!(ids.len(), s.len(), "{pre}: one id per byte");
            assert_eq!(tk.decode(&ids).expect("decodes"), s);
        }
    }
}

/// Inputs of 5,000 characters built to make a backtracking matcher work hard.
fn long_inputs() -> Vec<String> {
    vec![
        " ".repeat(5000),
        "\n".repeat(5000),
        " \n".repeat(2500),
        "\r\n".repeat(2500),
        format!("{}x", "\t".repeat(4999)),
        format!("a{}b", " ".repeat(4998)),
        "!".repeat(5000),
        "\u{3000}".repeat(5000),
        format!("{}\n", " ".repeat(4999)),
        "1".repeat(5000),
        "'s".repeat(2500),
        "\u{301}".repeat(5000),
    ]
}

#[test]
fn long_whitespace_runs_take_bounded_time() {
    // The bound is generous (an unoptimized build on a loaded machine); quadratic
    // backtracking on these inputs would take far longer.
    let bound = Duration::from_secs(20);
    let started = Instant::now();
    for pre in KNOWN_SCHEMES {
        let tk =
            Tokenizer::new(alphabet_tokens(), &[] as &[&str], None, pre, None).expect("alphabet");
        for s in long_inputs() {
            let ids = tk.encode(&s, false, &[]).expect("encodes");
            let want: String = if pre == "minimax" {
                s.nfc().collect()
            } else {
                s.clone()
            };
            assert_eq!(tk.decode(&ids).expect("decodes"), want, "{pre}");
        }
    }
    let spent = started.elapsed();
    assert!(spent < bound, "pre-tokenizing took {spent:?}");
}

#[test]
fn long_segments_are_cached_without_changing_ids() {
    let tk = trained_for("qwen35");
    let long = "Hello, world! ".repeat(300);
    let a = tk.encode(&long, false, &[]).expect("encodes");
    let b = tk.encode(&long, false, &[]).expect("encodes");
    assert_eq!(a, b);
    let shorter = tk
        .encode(&long[..long.len() - 1], false, &[])
        .expect("encodes");
    assert_ne!(a, shorter);
    assert_eq!(tk.decode(&a).expect("decodes"), long);
}

#[test]
fn concurrent_encodes_agree() {
    let tk = std::sync::Arc::new(trained_for("glm5"));
    let corpus = boundary_corpus();
    let expected: Vec<Vec<u32>> = corpus
        .iter()
        .map(|s| tk.encode(s, false, &[]).expect("encodes"))
        .collect();
    let handles: Vec<_> = (0..4)
        .map(|_| {
            let tk = std::sync::Arc::clone(&tk);
            let corpus = corpus.clone();
            std::thread::spawn(move || {
                corpus
                    .iter()
                    .map(|s| tk.encode(s, false, &[]).expect("encodes"))
                    .collect::<Vec<_>>()
            })
        })
        .collect();
    for h in handles {
        assert_eq!(h.join().expect("thread"), expected);
    }
}

/// Optional parity check on a real pack's tokenizer directory, named by
/// `PULSAR_CONSOLE_PACK_TOKENIZER`. Ignored by default: without a pack the round trip on real
/// vocabularies is unverified.
#[test]
#[ignore = "needs PULSAR_CONSOLE_PACK_TOKENIZER (a real pack's tokenizer directory); unverified without it"]
fn real_pack_round_trip() {
    let dir = std::env::var_os("PULSAR_CONSOLE_PACK_TOKENIZER")
        .expect("PULSAR_CONSOLE_PACK_TOKENIZER names a tokenizer directory");
    let tk = from_dir(std::path::Path::new(&dir)).expect("loads the pack");
    for s in boundary_corpus().iter().chain(extra_corpus().iter()) {
        let ids = tk.encode(s, false, &[]).expect("encodes");
        let want: String = if tk.pre().nfc() {
            s.nfc().collect()
        } else {
            s.clone()
        };
        assert_eq!(tk.decode(&ids).expect("decodes"), want);
    }
}

#[test]
fn two_million_character_whitespace_runs_encode_and_round_trip() {
    // A backtracking `\s+(?!\S)` overflows its stack near a million characters; the donor's
    // `regex` module splits these. Spaces followed by a letter, then trailing tabs.
    let text = format!("a{}b{}", " ".repeat(2_000_000), "\t".repeat(2_000_000));
    for pre in KNOWN_SCHEMES {
        let tk =
            Tokenizer::new(alphabet_tokens(), &[] as &[&str], None, pre, None).expect("alphabet");
        let pieces = tk.pretokenize(&text).expect("splits");
        assert_eq!(pieces.len(), 4, "{pre}");
        assert_eq!(pieces[1].len(), 1_999_999, "{pre}");
        assert_eq!(pieces[2], " b", "{pre}");
        assert_eq!(pieces[3].len(), 2_000_000, "{pre}");
        let ids = tk.encode(&text, false, &[]).expect("encodes");
        assert_eq!(ids.len(), text.len(), "{pre}");
        assert_eq!(tk.decode(&ids).expect("decodes"), text, "{pre}");
    }
}
