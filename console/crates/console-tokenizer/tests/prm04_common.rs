//! Shared helpers for the PRM-04 integration tests: synthetic vocabularies built in code
//! (binding decision B13), a tiny deterministic BPE trainer, a deterministic random number
//! generator and scratch directories. No real model's tokenizer is used.
//!
//! Each `prm04_*.rs` test file includes this file with `#[path]`; compiled on its own it has
//! no tests.

#![allow(dead_code)]

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

use console_tokenizer::bpe::Tokenizer;
use console_tokenizer::byte_map;

/// The 256 byte-alphabet characters in the donor's order, as tokens.
pub fn alphabet_tokens() -> Vec<String> {
    byte_map::alphabet().into_iter().map(String::from).collect()
}

/// The donor's `tiny_vocab()`: the byte alphabet plus five whole-word tokens, no merges.
pub fn tiny_vocab() -> Vec<String> {
    let mut tokens = alphabet_tokens();
    tokens.extend(["hello", "world", "hello world", "12345", " Head"].map(String::from));
    tokens
}

/// A vocabulary and merge list trained on `corpus` for the pre-tokenizer `pre`.
pub struct Trained {
    /// The byte alphabet, then one token per merge, then `extra` (the special literals).
    pub tokens: Vec<String>,
    /// The merges in rank order.
    pub merges: Vec<String>,
}

/// Trains up to `n_merges` merges over the byte-mapped pre-tokenizer pieces of `corpus`: the
/// most frequent adjacent pair first, ties broken by the smaller pair, pairs seen fewer than
/// twice never merged. Deterministic.
pub fn train(pre: &str, corpus: &[&str], n_merges: usize) -> Trained {
    let base =
        Tokenizer::new(alphabet_tokens(), &[] as &[&str], None, pre, None).expect("base tokenizer");
    let mut words: BTreeMap<Vec<String>, usize> = BTreeMap::new();
    for text in corpus {
        for piece in base.pretokenize(text).expect("pre-tokenizes") {
            let word: Vec<String> = byte_map::map_bytes(piece.as_bytes())
                .chars()
                .map(String::from)
                .collect();
            *words.entry(word).or_default() += 1;
        }
    }
    let mut tokens = alphabet_tokens();
    let mut merges = Vec::new();
    for _ in 0..n_merges {
        let mut pairs: BTreeMap<(String, String), usize> = BTreeMap::new();
        for (word, count) in &words {
            for pair in word.windows(2) {
                *pairs.entry((pair[0].clone(), pair[1].clone())).or_default() += count;
            }
        }
        let Some(((a, b), count)) = pairs
            .into_iter()
            .max_by(|x, y| x.1.cmp(&y.1).then_with(|| y.0.cmp(&x.0)))
        else {
            break;
        };
        if count < 2 {
            break;
        }
        let joined = format!("{a}{b}");
        if !tokens.contains(&joined) {
            tokens.push(joined.clone());
        }
        merges.push(format!("{a} {b}"));
        words = words
            .into_iter()
            .fold(BTreeMap::new(), |mut acc, (word, count)| {
                let mut merged = Vec::with_capacity(word.len());
                let mut i = 0;
                while i < word.len() {
                    if i + 1 < word.len() && word[i] == a && word[i + 1] == b {
                        merged.push(joined.clone());
                        i += 2;
                    } else {
                        merged.push(word[i].clone());
                        i += 1;
                    }
                }
                *acc.entry(merged).or_default() += count;
                acc
            });
    }
    Trained { tokens, merges }
}

/// A small deterministic generator (SplitMix64), standing in for Python's `random.Random`.
pub struct Rng(u64);

impl Rng {
    /// A generator from a seed.
    pub fn new(seed: u64) -> Self {
        Self(seed)
    }

    /// The next 64 random bits.
    pub fn next_u64(&mut self) -> u64 {
        self.0 = self.0.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.0;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }

    /// A value in `0..n` (`n > 0`).
    pub fn below(&mut self, n: usize) -> usize {
        (self.next_u64() % n as u64) as usize
    }
}

static NEXT_DIR: AtomicU64 = AtomicU64::new(0);

/// A fresh, empty scratch directory under the system temporary directory, removed on drop.
pub struct ScratchDir(PathBuf);

impl ScratchDir {
    /// Creates the directory.
    pub fn new(tag: &str) -> Self {
        let n = NEXT_DIR.fetch_add(1, Ordering::Relaxed);
        let nanos = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.subsec_nanos())
            .unwrap_or(0);
        let dir =
            std::env::temp_dir().join(format!("prm04-{tag}-{}-{n}-{nanos}", std::process::id()));
        std::fs::create_dir_all(&dir).expect("scratch dir");
        Self(dir)
    }

    /// The directory's path.
    pub fn path(&self) -> &Path {
        &self.0
    }
}

impl Drop for ScratchDir {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}
