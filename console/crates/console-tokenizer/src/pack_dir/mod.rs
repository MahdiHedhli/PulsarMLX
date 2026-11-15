//! Owned by PRM-04. Loading a tokenizer from a directory or from GGUF metadata keys.
//!
//! A pack's `tokenizer/` directory holds `vocab.json` (token to id), `merges.txt` (one merge
//! per line, split on `\n` only, so a trailing newline is an empty merge the constructor
//! refuses), and optionally `token_type.json` (the GGUF token types) and `tokenizer.json`
//! (with `pre`, defaulting to `qwen35`, and `special_ids`). Text files are read as UTF-8
//! with Python's universal newlines (`\r\n` and `\r` become `\n`) and parsed with
//! `console-pyjson`, which follows `json.loads`.
//!
//! [`from_gguf_metadata`] builds the same tokenizer from the `tokenizer.ggml.*` keys of a GGUF
//! file's metadata, given as JSON values; the special ids are the `*_token_id` keys.
//!
//! [`load_server_tokenizer`] is the server's choice at start-up: the directory's tokenizer
//! when it has a `vocab.json`, the byte tokenizer otherwise.
//!
//! Inputs the donor would accept and only fail on later, or not at all, are refused here
//! with a message of this crate's own: a `vocab.json` that leaves exactly one id without a
//! token, a truthy `special_ids` that is not an object, a truthy `token_type.json` that is not
//! a list, GGUF `tokenizer.ggml.tokens`, `tokenizer.ggml.merges` or truthy
//! `tokenizer.ggml.token_type` values that are not arrays (the donor `list()`s a string into
//! its characters), and GGUF token or merge arrays holding values that are not strings. In
//! [`from_dir`] these refusals come after the donor's own pre-tokenizer and duplicate checks.
//! A file larger than [`MAX_PACK_FILE_BYTES`] is refused before it is read. These
//! departures, the size limits and the byte-offset plain spans are proposal P-24 in the
//! deviation register of feature 022 and await the owner's decision.
//!
//! Behavior reference: project-maya tools/strata_tokenizer.py:200-232 and
//! serve/server.py:7178-7184 at 7e68a30f.

use std::fs::File;
use std::io::Read;
use std::path::Path;

use console_pyjson::dumps::{classify_number, int_value, PyNumber};
use console_pyjson::loads::{loads, UnicodeDecodeError};
use serde_json::{Map, Value};

use crate::bpe::TOKEN_TYPE_USER_DEFINED;
use crate::bpe::{py_repr, Tokenize, Tokenizer, TokenizerError, TOKEN_TYPE_CONTROL};
use crate::byte_tok::ByteTokenizer;
use crate::pretok::{unknown_scheme, PreScheme};
use crate::special::{LiteralMatcher, SpecialTokens};

/// The largest tokenizer file read, in bytes. A real model's files are tens of megabytes.
pub const MAX_PACK_FILE_BYTES: u64 = 512 * 1024 * 1024;

/// The token type stored for a `token_type.json` value that is not an integer: it equals
/// neither 3 nor 4, as such a value never equals them in Python.
pub const TOKEN_TYPE_NOT_INTEGER: i64 = i64::MIN;

fn io_error(path: &Path, e: &std::io::Error) -> TokenizerError {
    use std::io::ErrorKind;
    let class = match e.kind() {
        ErrorKind::NotFound => "FileNotFoundError",
        ErrorKind::PermissionDenied => "PermissionError",
        ErrorKind::IsADirectory => "IsADirectoryError",
        _ => "OSError",
    };
    let text = e.to_string();
    let description = match text.rfind(" (os error ") {
        Some(at) => text.get(..at).unwrap_or(&text).to_owned(),
        None => text.clone(),
    };
    let shown = py_repr(&path.to_string_lossy());
    let message = match e.raw_os_error() {
        Some(code) => format!("[Errno {code}] {description}: {shown}"),
        None => format!("{description}: {shown}"),
    };
    TokenizerError::Io { class, message }
}

fn utf8_error(raw: &[u8], e: std::str::Utf8Error) -> TokenizerError {
    let start = e.valid_up_to();
    let first = raw.get(start).copied().unwrap_or(0);
    let (end, reason) = match e.error_len() {
        None => (raw.len(), "unexpected end of data"),
        Some(n) => {
            let bad_start = matches!(first, 0x80..=0xC1 | 0xF5..=0xFF);
            if bad_start {
                (start + 1, "invalid start byte")
            } else {
                (start + n, "invalid continuation byte")
            }
        }
    };
    TokenizerError::Unicode(
        UnicodeDecodeError {
            encoding: "utf-8",
            first_byte: first,
            start,
            end,
            reason,
        }
        .to_string(),
    )
}

/// `Path.read_text(encoding="utf-8")`: strict UTF-8 and universal newlines.
fn read_text(path: &Path) -> Result<String, TokenizerError> {
    let mut file = File::open(path).map_err(|e| io_error(path, &e))?;
    let size = file.metadata().map_err(|e| io_error(path, &e))?.len();
    if size > MAX_PACK_FILE_BYTES {
        return Err(TokenizerError::TooLarge {
            file: path
                .file_name()
                .map(|n| n.to_string_lossy().into_owned())
                .unwrap_or_default(),
            size,
        });
    }
    let mut raw = Vec::new();
    file.by_ref()
        .take(MAX_PACK_FILE_BYTES + 1)
        .read_to_end(&mut raw)
        .map_err(|e| io_error(path, &e))?;
    if raw.len() as u64 > MAX_PACK_FILE_BYTES {
        return Err(TokenizerError::TooLarge {
            file: path
                .file_name()
                .map(|n| n.to_string_lossy().into_owned())
                .unwrap_or_default(),
            size: raw.len() as u64,
        });
    }
    let text = match String::from_utf8(raw) {
        Ok(t) => t,
        Err(e) => return Err(utf8_error(e.as_bytes(), e.utf8_error())),
    };
    if text.contains('\r') {
        Ok(text.replace("\r\n", "\n").replace('\r', "\n"))
    } else {
        Ok(text)
    }
}

fn read_json(path: &Path) -> Result<Value, TokenizerError> {
    loads(&read_text(path)?).map_err(TokenizerError::Json)
}

/// Python's type name of a JSON value.
fn py_type(v: &Value) -> &'static str {
    match v {
        Value::Null => "NoneType",
        Value::Bool(_) => "bool",
        Value::Number(n) => match classify_number(n) {
            Ok(PyNumber::Float(_)) => "float",
            _ => "int",
        },
        Value::String(_) => "str",
        Value::Array(_) => "list",
        Value::Object(_) => "dict",
    }
}

/// Python's `repr()` of a JSON value.
fn py_value_repr(v: &Value) -> String {
    match v {
        Value::Null => "None".to_owned(),
        Value::Bool(true) => "True".to_owned(),
        Value::Bool(false) => "False".to_owned(),
        Value::Number(n) => match classify_number(n) {
            Ok(PyNumber::Int(d)) => d,
            Ok(PyNumber::Float(f)) => console_pyjson::float_repr::repr_f64(f),
            Err(_) => n.to_string(),
        },
        Value::String(s) => py_repr(s),
        Value::Array(a) => format!(
            "[{}]",
            a.iter().map(py_value_repr).collect::<Vec<_>>().join(", ")
        ),
        Value::Object(o) => format!(
            "{{{}}}",
            o.iter()
                .map(|(k, v)| format!("{}: {}", py_repr(k), py_value_repr(v)))
                .collect::<Vec<_>>()
                .join(", ")
        ),
    }
}

/// Python truthiness of a JSON value.
fn truthy(v: &Value) -> bool {
    console_pyjson::loads::truthy(v)
}

/// The pre-tokenizer name, or the donor's refusal for a value that is not a known name.
fn pre_name(v: Option<&Value>) -> Result<&str, TokenizerError> {
    match v {
        None => Ok("qwen35"),
        Some(Value::String(s)) => Ok(s.as_str()),
        Some(other) => Err(unknown_scheme(&py_value_repr(other))),
    }
}

/// A token type as `ty in (3, 4)` sees it: an integer (a `bool` is 0 or 1, a float equal to an
/// integer counts as that integer), anything else [`TOKEN_TYPE_NOT_INTEGER`].
fn token_type_of(v: &Value) -> i64 {
    match v {
        Value::Bool(b) => i64::from(*b),
        Value::Number(n) => match classify_number(n) {
            Ok(PyNumber::Int(d)) => d.parse().unwrap_or(TOKEN_TYPE_NOT_INTEGER),
            Ok(PyNumber::Float(f)) if f == TOKEN_TYPE_CONTROL as f64 => TOKEN_TYPE_CONTROL,
            Ok(PyNumber::Float(f)) if f == TOKEN_TYPE_USER_DEFINED as f64 => {
                TOKEN_TYPE_USER_DEFINED
            }
            _ => TOKEN_TYPE_NOT_INTEGER,
        },
        _ => TOKEN_TYPE_NOT_INTEGER,
    }
}

/// `token_types` as the constructor receives it: `None` for a falsy value, the converted list
/// otherwise.
fn token_types_from(v: Option<&Value>, what: &str) -> Result<Option<Vec<i64>>, TokenizerError> {
    match v {
        None => Ok(None),
        Some(v) if !truthy(v) => Ok(None),
        Some(Value::Array(items)) => Ok(Some(items.iter().map(token_type_of).collect())),
        Some(other) => Err(TokenizerError::Type(format!(
            "{what} is a {}, not a list of token types",
            py_type(other)
        ))),
    }
}

/// A Python list index from a JSON value (`list[i] = s`), or the error Python raises.
fn list_index(v: &Value, len: usize) -> Result<usize, TokenizerError> {
    let i: i128 = match v {
        Value::Bool(b) => i128::from(*b),
        Value::Number(n) => match classify_number(n) {
            Ok(PyNumber::Int(d)) => match d.parse::<i128>() {
                Ok(i) => i,
                Err(_) => {
                    return Err(TokenizerError::Index(
                        "cannot fit 'int' into an index-sized integer".to_owned(),
                    ))
                }
            },
            _ => {
                return Err(TokenizerError::Type(format!(
                    "list indices must be integers or slices, not {}",
                    py_type(v)
                )))
            }
        },
        other => {
            return Err(TokenizerError::Type(format!(
                "list indices must be integers or slices, not {}",
                py_type(other)
            )))
        }
    };
    let n = len as i128;
    let at = if i < 0 { i + n } else { i };
    if (0..n).contains(&at) {
        Ok(at as usize)
    } else {
        Err(TokenizerError::Index(
            "list assignment index out of range".to_owned(),
        ))
    }
}

/// The slots of the donor's `tokens = [None] * len(vocab); for s, i in vocab.items():
/// tokens[i] = s`, with the errors Python raises on the way.
fn vocab_slots(vocab: &Value) -> Result<Vec<Option<String>>, TokenizerError> {
    let len = match vocab {
        Value::Object(o) => o.len(),
        Value::Array(a) => a.len(),
        Value::String(s) => s.chars().count(),
        other => {
            return Err(TokenizerError::Type(format!(
                "object of type '{}' has no len()",
                py_type(other)
            )))
        }
    };
    let Value::Object(entries) = vocab else {
        return Err(TokenizerError::Attribute(format!(
            "'{}' object has no attribute 'items'",
            py_type(vocab)
        )));
    };
    let mut slots: Vec<Option<String>> = vec![None; len];
    for (s, i) in entries {
        let at = list_index(i, len)?;
        if let Some(slot) = slots.get_mut(at) {
            *slot = Some(s.clone());
        }
    }
    Ok(slots)
}

/// The token list from the slots. Two or more empty slots are the donor constructor's
/// duplicate refusal (the empty slots are equal `None` tokens there); exactly one is refused
/// with this crate's own message.
fn tokens_from_slots(slots: Vec<Option<String>>) -> Result<Vec<String>, TokenizerError> {
    let len = slots.len();
    let holes: Vec<usize> = (0..len)
        .filter(|&i| slots.get(i).is_some_and(Option::is_none))
        .collect();
    match holes.as_slice() {
        [] => Ok(slots.into_iter().flatten().collect()),
        [one] => Err(TokenizerError::Value(format!(
            "vocabulary leaves id {one} without a token"
        ))),
        _ => {
            let filled = slots.iter().flatten().count();
            Err(TokenizerError::Value(format!(
                "vocabulary has duplicate tokens: {len} entries, {} unique",
                filled + 1
            )))
        }
    }
}

/// Loads the tokenizer in a pack's `tokenizer/` directory.
///
/// Behavior reference: project-maya tools/strata_tokenizer.py:201-214 at 7e68a30f.
pub fn from_dir(path: &Path) -> Result<Tokenizer, TokenizerError> {
    let vocab = read_json(&path.join("vocab.json"))?;
    // The token list is built before anything else is read.
    let slots = vocab_slots(&vocab)?;
    let meta_path = path.join("tokenizer.json");
    let meta = if meta_path.exists() {
        read_json(&meta_path)?
    } else {
        Value::Object(Map::new())
    };
    let types_path = path.join("token_type.json");
    let types = if types_path.exists() {
        Some(read_json(&types_path)?)
    } else {
        None
    };
    let merges_text = read_text(&path.join("merges.txt"))?;
    let Value::Object(meta) = &meta else {
        return Err(TokenizerError::Attribute(format!(
            "'{}' object has no attribute 'get'",
            py_type(&meta)
        )));
    };
    let pre = pre_name(meta.get("pre"))?;
    // The donor constructor checks the pre-tokenizer name first, then the vocabulary; the
    // refusals of this crate's own below come after both.
    PreScheme::parse(pre)?;
    let tokens = tokens_from_slots(slots)?;
    let special_ids = match meta.get("special_ids") {
        Some(v) if truthy(v) => match v {
            Value::Object(o) => Some(o.clone()),
            other => {
                return Err(TokenizerError::Type(format!(
                    "special_ids in tokenizer.json is a {}, not an object",
                    py_type(other)
                )))
            }
        },
        _ => None,
    };
    let token_types = token_types_from(types.as_ref(), "token_type.json")?;
    let merges: Vec<&str> = merges_text.split('\n').collect();
    Tokenizer::new(tokens, &merges, token_types, pre, special_ids)
}

/// Python's `int(v)` for a GGUF metadata value given as JSON.
fn py_int(v: &Value) -> Result<Value, TokenizerError> {
    match v {
        Value::Bool(b) => Ok(Value::from(u8::from(*b))),
        Value::Number(n) => match classify_number(n) {
            Ok(PyNumber::Int(d)) => int_value(&d)
                .ok_or_else(|| TokenizerError::Value("integer is too large to convert".to_owned())),
            Ok(PyNumber::Float(f)) if f.is_nan() => Err(TokenizerError::Value(
                "cannot convert float NaN to integer".to_owned(),
            )),
            Ok(PyNumber::Float(f)) if f.is_infinite() => Err(TokenizerError::Value(
                "cannot convert float infinity to integer".to_owned(),
            )),
            Ok(PyNumber::Float(f)) => {
                let t = f.trunc();
                let text = format!("{t:.0}");
                int_value(&text).ok_or_else(|| {
                    TokenizerError::Value("integer is too large to convert".to_owned())
                })
            }
            Err(_) => Err(TokenizerError::Value(format!(
                "invalid literal for int() with base 10: {}",
                py_repr(n.as_str())
            ))),
        },
        Value::String(s) => {
            let t = s.trim();
            let (sign, digits) = match t.strip_prefix('-') {
                Some(d) => ("-", d),
                None => ("", t.strip_prefix('+').unwrap_or(t)),
            };
            let clean = digits.replace('_', "");
            let shaped = !digits.is_empty()
                && !digits.starts_with('_')
                && !digits.ends_with('_')
                && !digits.contains("__")
                && clean.bytes().all(|c| c.is_ascii_digit());
            match int_value(&format!("{sign}{clean}")) {
                Some(v) if shaped => Ok(v),
                _ => Err(TokenizerError::Value(format!(
                    "invalid literal for int() with base 10: {}",
                    py_repr(s)
                ))),
            }
        }
        other => Err(TokenizerError::Type(format!(
            "int() argument must be a string, a bytes-like object or a real number, not '{}'",
            py_type(other)
        ))),
    }
}

fn string_list(v: &Value, key: &str) -> Result<Vec<String>, TokenizerError> {
    let Value::Array(items) = v else {
        return Err(TokenizerError::Type(format!(
            "{key} is a {}, not a list of strings",
            py_type(v)
        )));
    };
    items
        .iter()
        .map(|item| match item {
            Value::String(s) => Ok(s.clone()),
            other => Err(TokenizerError::Type(format!(
                "{key} holds a {}, not a string",
                py_type(other)
            ))),
        })
        .collect()
}

/// Builds the tokenizer from GGUF metadata keys: `tokenizer.ggml.tokens` and
/// `tokenizer.ggml.merges` are required, `tokenizer.ggml.model` must be `gpt2`, and every
/// `tokenizer.ggml.*_token_id` key becomes a special id under its full key name.
///
/// Behavior reference: project-maya tools/strata_tokenizer.py:216-232 at 7e68a30f.
pub fn from_gguf_metadata(md: &Map<String, Value>) -> Result<Tokenizer, TokenizerError> {
    const TOKENS_KEY: &str = "tokenizer.ggml.tokens";
    const MERGES_KEY: &str = "tokenizer.ggml.merges";
    let missing: Vec<&str> = [TOKENS_KEY, MERGES_KEY]
        .into_iter()
        .filter(|k| !md.contains_key(*k))
        .collect();
    if !missing.is_empty() {
        return Err(TokenizerError::Value(format!(
            "GGUF is missing {}; it does not carry a tokenizer",
            missing.join(", ")
        )));
    }
    match md.get("tokenizer.ggml.model") {
        Some(Value::String(m)) if m == "gpt2" => {}
        other => {
            let shown = other.map_or_else(|| "None".to_owned(), py_value_repr);
            return Err(TokenizerError::Value(format!(
                "expected a byte-level BPE tokenizer (model 'gpt2'), got {shown}"
            )));
        }
    }
    let mut special = Map::new();
    for (k, v) in md {
        if k.starts_with("tokenizer.ggml.") && k.ends_with("_token_id") {
            special.insert(k.clone(), py_int(v)?);
        }
    }
    let tokens = string_list(md.get(TOKENS_KEY).unwrap_or(&Value::Null), TOKENS_KEY)?;
    let merges = string_list(md.get(MERGES_KEY).unwrap_or(&Value::Null), MERGES_KEY)?;
    let token_types = token_types_from(
        md.get("tokenizer.ggml.token_type"),
        "tokenizer.ggml.token_type",
    )?;
    let pre = pre_name(md.get("tokenizer.ggml.pre"))?;
    Tokenizer::new(tokens, &merges, token_types, pre, Some(special))
}

/// The server's tokenizer: a byte-level BPE one or the byte tokenizer.
#[derive(Debug)]
pub enum AnyTokenizer {
    /// The stand-in byte tokenizer (no `vocab.json` at the configured path).
    Byte(ByteTokenizer),
    /// A pack's byte-level BPE tokenizer.
    Bpe(Box<Tokenizer>),
}

/// The tokenizer the server starts with: the one in `path` when `path/vocab.json` exists,
/// the byte tokenizer otherwise.
///
/// Behavior reference: project-maya serve/server.py:7178-7184 at 7e68a30f.
pub fn load_server_tokenizer(path: &Path) -> Result<AnyTokenizer, TokenizerError> {
    if path.join("vocab.json").exists() {
        return from_dir(path).map(|t| AnyTokenizer::Bpe(Box::new(t)));
    }
    Ok(AnyTokenizer::Byte(ByteTokenizer::new()))
}

impl Tokenize for AnyTokenizer {
    fn encode(
        &self,
        text: &str,
        parse_special: bool,
        plain: &[(usize, usize)],
    ) -> Result<Vec<u32>, TokenizerError> {
        match self {
            Self::Byte(t) => Tokenize::encode(t, text, parse_special, plain),
            Self::Bpe(t) => Tokenize::encode(t.as_ref(), text, parse_special, plain),
        }
    }
    fn decode(&self, ids: &[u32]) -> Result<String, TokenizerError> {
        match self {
            Self::Byte(t) => Tokenize::decode(t, ids),
            Self::Bpe(t) => Tokenize::decode(t.as_ref(), ids),
        }
    }
    fn token_bytes(&self, id: u32) -> Option<Result<Vec<u8>, TokenizerError>> {
        match self {
            Self::Byte(t) => Tokenize::token_bytes(t, id),
            Self::Bpe(t) => Tokenize::token_bytes(t.as_ref(), id),
        }
    }
    fn has_token_bytes(&self) -> bool {
        match self {
            Self::Byte(t) => t.has_token_bytes(),
            Self::Bpe(t) => t.has_token_bytes(),
        }
    }
    fn special_tokens(&self) -> &SpecialTokens {
        match self {
            Self::Byte(t) => t.special_tokens(),
            Self::Bpe(t) => t.special_tokens(),
        }
    }
    fn special_ids(&self) -> &Map<String, Value> {
        match self {
            Self::Byte(t) => t.special_ids(),
            Self::Bpe(t) => t.special_ids(),
        }
    }
    fn tokens(&self) -> Option<&[String]> {
        match self {
            Self::Byte(t) => Tokenize::tokens(t),
            Self::Bpe(t) => Tokenize::tokens(t.as_ref()),
        }
    }
    fn n_tokens(&self) -> usize {
        match self {
            Self::Byte(t) => t.n_tokens(),
            Self::Bpe(t) => t.as_ref().n_tokens(),
        }
    }
    fn token_types(&self) -> Option<&[i64]> {
        match self {
            Self::Byte(t) => Tokenize::token_types(t),
            Self::Bpe(t) => Tokenize::token_types(t.as_ref()),
        }
    }
    fn special_matcher(&self) -> Option<&LiteralMatcher> {
        match self {
            Self::Byte(t) => Tokenize::special_matcher(t),
            Self::Bpe(t) => Tokenize::special_matcher(t.as_ref()),
        }
    }
    fn encode_segment(&self, text: &str) -> Option<Result<Vec<u32>, TokenizerError>> {
        match self {
            Self::Byte(t) => Tokenize::encode_segment(t, text),
            Self::Bpe(t) => Tokenize::encode_segment(t.as_ref(), text),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn md(pairs: &[(&str, Value)]) -> Map<String, Value> {
        pairs
            .iter()
            .map(|(k, v)| ((*k).to_owned(), v.clone()))
            .collect()
    }

    fn alphabet_values() -> Value {
        Value::Array(
            crate::byte_map::alphabet()
                .into_iter()
                .map(|c| Value::String(c.to_string()))
                .collect(),
        )
    }

    #[test]
    fn gguf_missing_keys() {
        let err = from_gguf_metadata(&Map::new()).expect_err("missing");
        assert_eq!(
            err.to_string(),
            "GGUF is missing tokenizer.ggml.tokens, tokenizer.ggml.merges; it does not carry a tokenizer"
        );
    }

    #[test]
    fn gguf_model_must_be_gpt2() {
        let base = [
            ("tokenizer.ggml.tokens", alphabet_values()),
            ("tokenizer.ggml.merges", Value::Array(vec![])),
        ];
        let err = from_gguf_metadata(&md(&base)).expect_err("no model");
        assert_eq!(
            err.to_string(),
            "expected a byte-level BPE tokenizer (model 'gpt2'), got None"
        );
        let mut with = base.to_vec();
        with.push(("tokenizer.ggml.model", Value::from("llama")));
        let err = from_gguf_metadata(&md(&with)).expect_err("llama");
        assert_eq!(
            err.to_string(),
            "expected a byte-level BPE tokenizer (model 'gpt2'), got 'llama'"
        );
    }

    #[test]
    fn gguf_special_ids_and_pre() {
        let pairs = [
            ("tokenizer.ggml.model", Value::from("gpt2")),
            ("tokenizer.ggml.eos_token_id", Value::from(3)),
            ("tokenizer.ggml.tokens", alphabet_values()),
            ("tokenizer.ggml.merges", Value::Array(vec![])),
            ("tokenizer.ggml.bos_token_id", Value::from("7")),
            ("tokenizer.ggml.pre", Value::from("glm5")),
            ("general.eos_token_id", Value::from(9)),
        ];
        let tk = from_gguf_metadata(&md(&pairs)).expect("builds");
        assert_eq!(tk.pre(), PreScheme::Glm5);
        let ids = console_pyjson::dumps::to_wire(&Value::Object(tk.special_ids().clone()))
            .expect("dumps");
        assert_eq!(
            ids,
            "{\"tokenizer.ggml.eos_token_id\": 3, \"tokenizer.ggml.bos_token_id\": 7}"
        );
        assert!(tk.token_types().is_none());
    }

    #[test]
    fn gguf_bad_pre_is_the_donor_refusal() {
        let pairs = [
            ("tokenizer.ggml.model", Value::from("gpt2")),
            ("tokenizer.ggml.tokens", alphabet_values()),
            ("tokenizer.ggml.merges", Value::Array(vec![])),
            ("tokenizer.ggml.pre", Value::from(5)),
        ];
        let err = from_gguf_metadata(&md(&pairs)).expect_err("pre");
        assert_eq!(
            err.to_string(),
            "the 5 pre-tokenizer is not transcribed; known: qwen35, glm4, glm5, deepseek3, minimax"
        );
    }

    #[test]
    fn py_int_follows_python() {
        assert_eq!(py_int(&Value::from(true)).expect("bool"), Value::from(1));
        assert_eq!(
            py_int(&console_pyjson::dumps::float_value(3.9)).expect("float"),
            Value::from(3)
        );
        assert_eq!(
            py_int(&Value::from(" -1_0 ")).expect("str"),
            Value::from(-10)
        );
        assert_eq!(
            py_int(&Value::from("x")).expect_err("bad").to_string(),
            "invalid literal for int() with base 10: 'x'"
        );
        assert_eq!(
            py_int(&Value::Null).expect_err("none").to_string(),
            "int() argument must be a string, a bytes-like object or a real number, not 'NoneType'"
        );
    }

    #[test]
    fn list_index_wraps_and_refuses_like_python() {
        assert_eq!(list_index(&Value::from(-1), 3).expect("wraps"), 2);
        assert_eq!(list_index(&Value::from(false), 3).expect("bool"), 0);
        assert_eq!(
            list_index(&Value::from(3), 3)
                .expect_err("range")
                .to_string(),
            "list assignment index out of range"
        );
        assert_eq!(
            list_index(&console_pyjson::dumps::float_value(1.0), 3)
                .expect_err("float")
                .to_string(),
            "list indices must be integers or slices, not float"
        );
    }

    #[test]
    fn token_types_conversion() {
        let v: Value = serde_json::from_str("[1, 3, 4.0, true, \"4\", null]").expect("json");
        let got = token_types_from(Some(&v), "t")
            .expect("list")
            .expect("some");
        assert_eq!(
            got,
            [1, 3, 4, 1, TOKEN_TYPE_NOT_INTEGER, TOKEN_TYPE_NOT_INTEGER]
        );
        assert_eq!(
            token_types_from(Some(&Value::from(0)), "t").expect("falsy"),
            None
        );
        assert!(token_types_from(Some(&Value::from(7)), "t").is_err());
    }

    #[test]
    fn gguf_tokens_or_merges_that_are_not_arrays_are_refused() {
        // The donor list()s a string into its characters; this crate refuses it.
        let pairs = [
            ("tokenizer.ggml.model", Value::from("gpt2")),
            ("tokenizer.ggml.tokens", Value::from("abc")),
            ("tokenizer.ggml.merges", Value::Array(vec![])),
        ];
        let err = from_gguf_metadata(&md(&pairs)).expect_err("tokens");
        assert_eq!(err.python_type(), "TypeError");
        assert_eq!(
            err.to_string(),
            "tokenizer.ggml.tokens is a str, not a list of strings"
        );
        let pairs = [
            ("tokenizer.ggml.model", Value::from("gpt2")),
            ("tokenizer.ggml.tokens", alphabet_values()),
            ("tokenizer.ggml.merges", Value::from("a b")),
        ];
        let err = from_gguf_metadata(&md(&pairs)).expect_err("merges");
        assert_eq!(
            err.to_string(),
            "tokenizer.ggml.merges is a str, not a list of strings"
        );
    }

    #[test]
    fn gguf_truthy_token_type_that_is_not_an_array_is_refused() {
        let pairs = [
            ("tokenizer.ggml.model", Value::from("gpt2")),
            ("tokenizer.ggml.tokens", alphabet_values()),
            ("tokenizer.ggml.merges", Value::Array(vec![])),
            ("tokenizer.ggml.token_type", Value::from("13")),
        ];
        let err = from_gguf_metadata(&md(&pairs)).expect_err("types");
        assert_eq!(err.python_type(), "TypeError");
        assert_eq!(
            err.to_string(),
            "tokenizer.ggml.token_type is a str, not a list of token types"
        );
        // A falsy value is no types at all, as `list(... or []) or None` gives.
        let pairs = [
            ("tokenizer.ggml.model", Value::from("gpt2")),
            ("tokenizer.ggml.tokens", alphabet_values()),
            ("tokenizer.ggml.merges", Value::Array(vec![])),
            ("tokenizer.ggml.token_type", Value::from("")),
        ];
        assert!(from_gguf_metadata(&md(&pairs))
            .expect("builds")
            .token_types()
            .is_none());
    }

    #[test]
    fn value_repr() {
        let v: Value = serde_json::from_str("{\"a\": [null, true, 1.5, \"x\"]}").expect("json");
        assert_eq!(py_value_repr(&v), "{'a': [None, True, 1.5, 'x']}");
    }

    #[test]
    fn missing_file_message() {
        let err = read_text(Path::new("no-such-dir-prm04/vocab.json")).expect_err("missing");
        assert_eq!(err.python_type(), "FileNotFoundError");
        assert_eq!(
            err.to_string(),
            "[Errno 2] No such file or directory: 'no-such-dir-prm04/vocab.json'"
        );
    }

    #[test]
    fn utf8_error_messages_follow_python() {
        fn err_of(raw: &[u8]) -> std::str::Utf8Error {
            std::str::from_utf8(raw).expect_err("invalid")
        }
        let e = err_of(b"ab\xff");
        assert_eq!(
            utf8_error(b"ab\xff", e).to_string(),
            "'utf-8' codec can't decode byte 0xff in position 2: invalid start byte"
        );
        let e = err_of(b"\xe4\xbd");
        assert_eq!(
            utf8_error(b"\xe4\xbd", e).to_string(),
            "'utf-8' codec can't decode bytes in position 0-1: unexpected end of data"
        );
        let e = err_of(b"\xe4A");
        assert_eq!(
            utf8_error(b"\xe4A", e).to_string(),
            "'utf-8' codec can't decode byte 0xe4 in position 0: invalid continuation byte"
        );
    }
}
