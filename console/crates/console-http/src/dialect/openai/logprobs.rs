//! OpenAI's logprobs entry of one token, from the engine's logprob row.
//!
//! Behavior reference: project-maya serve/server.py:503 and 571-596 at 7e68a30f.

use console_core::engine::TokenLogprob;
use console_pyjson::dumps::float_value;
use console_tokenizer::bpe::Tokenize;
use console_tokenizer::detok::decode_utf8_replace;
use serde_json::{Map, Value};

/// OpenAI's logprob for a token the model gives no chance: `-inf` is no JSON number, so a
/// non-finite logprob is written as this floor.
///
/// Behavior reference: project-maya serve/server.py:503 at 7e68a30f.
pub const LOGPROB_FLOOR: f64 = -9999.0;

/// One token's bytes (an entry's `bytes`): the tokenizer's own `token_bytes`, else the
/// UTF-8 of its decode; empty for an id the tokenizer refuses.
///
/// Behavior reference: project-maya serve/server.py:571-578 at 7e68a30f.
pub fn token_piece(tok: &dyn Tokenize, id: u32) -> Vec<u8> {
    if tok.has_token_bytes() {
        return match tok.token_bytes(id) {
            Some(Ok(bytes)) => bytes,
            _ => Vec::new(),
        };
    }
    tok.decode(&[id])
        .map(String::into_bytes)
        .unwrap_or_default()
}

/// `{token, logprob, bytes}` of one id: the bytes as numbers, the token as their UTF-8
/// decode with replacement characters, the logprob as given, or [`LOGPROB_FLOOR`] when it
/// is not finite.
fn piece(tok: &dyn Tokenize, id: u32, logprob: f64) -> Map<String, Value> {
    let bytes = token_piece(tok, id);
    let value = if logprob.is_finite() {
        logprob
    } else {
        LOGPROB_FLOOR
    };
    let mut m = Map::new();
    m.insert("token".into(), Value::String(decode_utf8_replace(&bytes)));
    m.insert("logprob".into(), float_value(value));
    m.insert(
        "bytes".into(),
        Value::Array(bytes.into_iter().map(Value::from).collect()),
    );
    m
}

/// OpenAI's logprobs entry for token `id` with the engine's row `lp`: `{token, logprob,
/// bytes, top_logprobs}`, with at most `n_top` alternatives in the row's order. A token
/// split inside a UTF-8 character has the replacement character in `token` and its own
/// bytes in `bytes`, as OpenAI's do.
///
/// Behavior reference: project-maya serve/server.py:581-596 at 7e68a30f.
pub fn logprob_entry(tok: &dyn Tokenize, id: u32, lp: &TokenLogprob, n_top: u8) -> Value {
    let mut entry = piece(tok, id, lp.logprob);
    let top: Vec<Value> = lp
        .top
        .iter()
        .take(usize::from(n_top))
        .map(|(i, v)| Value::Object(piece(tok, *i, *v)))
        .collect();
    entry.insert("top_logprobs".into(), Value::Array(top));
    Value::Object(entry)
}

#[cfg(test)]
mod tests {
    use super::*;
    use console_pyjson::dumps::to_wire;
    use console_tokenizer::byte_tok::ByteTokenizer;

    fn wire(v: &Value) -> String {
        to_wire(v).unwrap_or_default()
    }

    #[test]
    fn an_entry_has_the_donor_shape() {
        let tok = ByteTokenizer::new();
        let lp = TokenLogprob {
            logprob: -0.1,
            top: vec![(72, -0.1), (73, -1.1), (74, -2.1)],
        };
        assert_eq!(
            wire(&logprob_entry(&tok, 72, &lp, 2)),
            r#"{"token": "H", "logprob": -0.1, "bytes": [72], "top_logprobs": [{"token": "H", "logprob": -0.1, "bytes": [72]}, {"token": "I", "logprob": -1.1, "bytes": [73]}]}"#
        );
    }

    #[test]
    fn a_split_character_no_chance_and_unknown_ids() {
        let tok = ByteTokenizer::new();
        // A lone lead byte decodes to U+FFFD, whose UTF-8 is what `bytes` carries (the
        // byte tokenizer has no `token_bytes`: the donor encodes its decode).
        let lp = TokenLogprob {
            logprob: f64::NEG_INFINITY,
            top: vec![],
        };
        assert_eq!(
            wire(&logprob_entry(&tok, 0xe4, &lp, 0)),
            "{\"token\": \"\u{fffd}\", \"logprob\": -9999.0, \"bytes\": [239, 191, 189], \"top_logprobs\": []}"
        );
        // A special decodes to its literal; an id past the vocabulary has no bytes.
        assert_eq!(token_piece(&tok, 257), b"<|im_end|>".to_vec());
        assert!(token_piece(&tok, 900).is_empty());
        let nan = TokenLogprob {
            logprob: f64::NAN,
            top: vec![(900, 0.0)],
        };
        assert_eq!(
            wire(&logprob_entry(&tok, 900, &nan, 5)),
            r#"{"token": "", "logprob": -9999.0, "bytes": [], "top_logprobs": [{"token": "", "logprob": 0.0, "bytes": []}]}"#
        );
    }
}
