//! Owned by PRM-04. `ByteTokenizer`: one id per UTF-8 byte plus the donor's six specials.
//!
//! The stand-in tokenizer the server uses when no model tokenizer is configured, and the one
//! synthetic engines and tests run with: each UTF-8 byte is its own id (0 to 255), and the six
//! special literals take ids 256 to 261 in the donor's order. Specials are matched only with
//! special parsing, scanning the text left to right and trying the six literals in order at
//! each character; a literal that starts inside a plain span is ordinary text. It has no
//! `token_bytes`, so the detokenizer re-decodes with it.
//!
//! Plain spans are byte offsets here, where the donor uses code-point indexes (see
//! [`crate::special`]).
//!
//! Behavior reference: project-maya serve/server.py:2061-2084 at 7e68a30f.

use serde_json::{Map, Value};

use crate::bpe::{Tokenize, TokenizerError};
use crate::detok::decode_utf8_replace;
use crate::special::SpecialTokens;

/// The special literals, in id order from 256.
pub const SPECIALS: [&str; 6] = [
    "<|im_start|>",
    "<|im_end|>",
    "<|endoftext|>",
    "<|vision_start|>",
    "<|image_pad|>",
    "<|vision_end|>",
];

/// The id of the first special literal.
pub const FIRST_SPECIAL_ID: u32 = 256;

/// The id the byte tokenizer names `eos` (its `<|im_end|>`).
pub const EOS_ID: u32 = 257;

/// One id per UTF-8 byte, and [`SPECIALS`] from id 256.
#[derive(Debug, Clone)]
pub struct ByteTokenizer {
    specials: SpecialTokens,
    special_ids: Map<String, Value>,
}

impl Default for ByteTokenizer {
    fn default() -> Self {
        Self::new()
    }
}

impl ByteTokenizer {
    /// The byte tokenizer, with `special_ids` `{"eos": 257}`.
    pub fn new() -> Self {
        let mut specials = SpecialTokens::new();
        for (k, lit) in (0u32..).zip(SPECIALS) {
            specials.insert(lit, FIRST_SPECIAL_ID + k);
        }
        let mut special_ids = Map::new();
        special_ids.insert("eos".to_owned(), Value::from(EOS_ID));
        Self {
            specials,
            special_ids,
        }
    }

    /// The number of ids this tokenizer can encode to or decode (256 bytes and six specials),
    /// that is the id range only. It is not the donor's `len(getattr(tok, "tokens", None) or
    /// ())`, which is 0 for the byte tokenizer (it has no `tokens`); that value is
    /// [`Tokenize::n_tokens`].
    pub fn n_vocab(&self) -> usize {
        256 + SPECIALS.len()
    }

    /// Encodes `text`: with `parse_special`, a special literal starting at a character outside
    /// every `plain` byte range becomes its id; every other character becomes its UTF-8 bytes.
    pub fn encode(&self, text: &str, parse_special: bool, plain: &[(usize, usize)]) -> Vec<u32> {
        let mut out = Vec::with_capacity(text.len());
        // The donor tests `any(a <= i < b for a, b in plain)` at each character. Positions only
        // grow, so the spans are sorted once and consumed in start order, keeping the furthest
        // end of those started so far: `i < plain_end` is the same test in linear time.
        let mut spans = if parse_special {
            plain.to_vec()
        } else {
            Vec::new()
        };
        spans.sort_unstable();
        let mut upcoming = spans.into_iter().peekable();
        let mut plain_end = 0usize;
        let mut i = 0usize;
        while let Some(rest) = text.get(i..) {
            let Some(c) = rest.chars().next() else {
                break;
            };
            while let Some(&(a, b)) = upcoming.peek() {
                if a > i {
                    break;
                }
                plain_end = plain_end.max(b);
                upcoming.next();
            }
            let hit = if parse_special && i >= plain_end {
                (0u32..)
                    .zip(SPECIALS)
                    .find(|(_, lit)| rest.starts_with(lit))
            } else {
                None
            };
            match hit {
                Some((k, lit)) => {
                    out.push(FIRST_SPECIAL_ID + k);
                    i += lit.len();
                }
                None => {
                    let mut buf = [0u8; 4];
                    out.extend(c.encode_utf8(&mut buf).bytes().map(u32::from));
                    i += c.len_utf8();
                }
            }
        }
        out
    }

    /// Decodes ids: bytes below 256, specials as their text, invalid UTF-8 as U+FFFD. An id
    /// past the last special is the donor's `IndexError`.
    pub fn decode(&self, ids: &[u32]) -> Result<String, TokenizerError> {
        let mut raw = Vec::with_capacity(ids.len());
        for &id in ids {
            match u8::try_from(id) {
                Ok(b) => raw.push(b),
                Err(_) => {
                    let lit = usize::try_from(id - FIRST_SPECIAL_ID)
                        .ok()
                        .and_then(|k| SPECIALS.get(k))
                        .ok_or_else(|| {
                            TokenizerError::Index("list index out of range".to_owned())
                        })?;
                    raw.extend_from_slice(lit.as_bytes());
                }
            }
        }
        Ok(decode_utf8_replace(&raw))
    }
}

impl Tokenize for ByteTokenizer {
    fn encode(
        &self,
        text: &str,
        parse_special: bool,
        plain: &[(usize, usize)],
    ) -> Result<Vec<u32>, TokenizerError> {
        Ok(ByteTokenizer::encode(self, text, parse_special, plain))
    }
    fn decode(&self, ids: &[u32]) -> Result<String, TokenizerError> {
        ByteTokenizer::decode(self, ids)
    }
    fn token_bytes(&self, _id: u32) -> Option<Result<Vec<u8>, TokenizerError>> {
        None
    }
    fn has_token_bytes(&self) -> bool {
        false
    }
    fn special_tokens(&self) -> &SpecialTokens {
        &self.specials
    }
    fn special_ids(&self) -> &Map<String, Value> {
        &self.special_ids
    }
    // The donor's byte tokenizer has no `tokens`, `token_types`, `_special_re` or
    // `_encode_segment`: the trait's defaults (`None`, and 0 for `n_tokens`) are its view.
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn special_ids_and_table() {
        let bt = ByteTokenizer::new();
        let table: Vec<(&str, u32)> = bt.specials.iter().collect();
        assert_eq!(
            table,
            [
                ("<|im_start|>", 256),
                ("<|im_end|>", 257),
                ("<|endoftext|>", 258),
                ("<|vision_start|>", 259),
                ("<|image_pad|>", 260),
                ("<|vision_end|>", 261),
            ]
        );
        assert_eq!(
            console_pyjson::dumps::to_wire(&Value::Object(bt.special_ids.clone())).expect("dumps"),
            "{\"eos\": 257}"
        );
        assert_eq!(bt.n_vocab(), 262);
    }

    #[test]
    fn decode_past_the_specials_is_an_index_error() {
        let err = ByteTokenizer::new().decode(&[262]).expect_err("index");
        assert_eq!(err.python_type(), "IndexError");
        assert_eq!(err.to_string(), "list index out of range");
    }
}
