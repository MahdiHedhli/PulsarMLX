//! The request checks that run before anything is sent to an engine: the sampling fields,
//! the loop guard, `logit_bias`, `ablate`, `ignore_eos` and `logprobs`; and the readers of
//! a request's stop strings and answer budget.
//!
//! The checks work on the request's order-preserving JSON map and rewrite a field in place
//! where the donor does (a number sent as a string becomes the number; `logit_bias` becomes
//! the checked map), so the rest of the pipeline sees what the donor's sees.
//!
//! Behavior reference: project-maya serve/server.py:497-529 (`logprobs_of`,
//! `logprobs_asked`), 624-632 (`client_stop_strings`), 635-718 (`PENALTY_WINDOW_MAX`,
//! `SAMPLING_TYPES`, `check_request_sampling`, `logit_bias_of`), 2489-2530
//! (`Service.check_request`), 6571 and 6679 (the answer budget) at 7e68a30f.

use std::cmp::Ordering;
use std::collections::HashMap;

use console_pyjson::loads::truthy;
use serde_json::{Map, Value};

use super::error::RequestError;
use super::pynum::{
    float_json, kind, matches_digits, matches_signed_digits, py_float_str, py_int, py_int_of_float,
    py_int_str, PyInt, PyKind,
};
use crate::engine::EngineCaps;

/// The most alternatives a token's log-probabilities carry (`top_logprobs` 0..20).
///
/// Behavior reference: project-maya serve/server.py:502 at 7e68a30f.
pub const TOP_LOGPROBS_MAX: u8 = 20;

/// The most stop strings a request's `stop` / `stop_sequences` keep.
///
/// Behavior reference: project-maya serve/server.py:632 at 7e68a30f.
pub const STOP_STRINGS_MAX: usize = 16;

/// The largest token id `logit_bias` accepts (`2**31 - 1`).
///
/// Behavior reference: project-maya serve/server.py:706 at 7e68a30f.
pub const LOGIT_BIAS_MAX_ID: i64 = (1 << 31) - 1;

/// A request's sampling fields and whether each is an integer field, in the donor's order.
///
/// Behavior reference: project-maya serve/server.py:640-642 at 7e68a30f.
pub const SAMPLING_TYPES: [(&str, bool); 9] = [
    ("temperature", false),
    ("top_p", false),
    ("min_p", false),
    ("presence_penalty", false),
    ("frequency_penalty", false),
    ("repetition_penalty", false),
    ("top_k", true),
    ("penalty_last_n", true),
    ("seed", true),
];

/// The tail the donor's refusals add where an older engine lacks a feature. The donor
/// points to its own setup script; the product wording names PulsarMLX Console instead
/// (deviation BRAND-1; contracts/naming.md section 3.8, package API-04).
const UPDATE_HINT: &str = "update PulsarMLX Console";

fn is_null(v: Option<&Value>) -> bool {
    matches!(v, None | Some(Value::Null))
}

/// Reads a request's sampling fields the way the run config's are read, or refuses with a
/// message naming the field. A number sent as a string is read with Python's `float()`
/// (surrounding whitespace allowed) and stored as an `int` when it is an optional sign and
/// digits, or for an integer field with an integral value. llama.cpp's `repeat_penalty` and
/// `repeat_last_n` are copied to `repetition_penalty` and `penalty_last_n` when those are
/// absent or null; the window is named in messages by the key the request used. The loop
/// guard accepts a bool, the words true/false/on/off/1/0 or the integers 0 and 1, and is
/// stored as a bool.
///
/// Behavior reference: project-maya serve/server.py:645-691 at 7e68a30f.
pub fn check_request_sampling(req: &mut Map<String, Value>) -> Result<(), RequestError> {
    if !is_null(req.get("repeat_penalty")) && is_null(req.get("repetition_penalty")) {
        let v = req.get("repeat_penalty").cloned().unwrap_or(Value::Null);
        req.insert(String::from("repetition_penalty"), v);
    }
    let mut window_key = "penalty_last_n";
    if is_null(req.get("penalty_last_n")) && !is_null(req.get("repeat_last_n")) {
        let v = req.get("repeat_last_n").cloned().unwrap_or(Value::Null);
        req.insert(String::from("penalty_last_n"), v);
        window_key = "repeat_last_n";
    }
    for (key, integer) in SAMPLING_TYPES {
        let Some(value) = req.get(key) else { continue };
        if value.is_null() {
            continue;
        }
        let shown = if key == "penalty_last_n" {
            window_key
        } else {
            key
        };
        let what = || {
            RequestError::invalid(format!(
                "{shown}: {}",
                if integer { "an integer" } else { "a number" }
            ))
        };
        let mut current = kind(value);
        if let PyKind::Str(text) = current {
            if !text
                .trim_matches(console_pyjson::pystr::is_space)
                .is_empty()
            {
                let num = py_float_str(text).ok_or_else(what)?;
                if !num.is_finite() {
                    return Err(what());
                }
                let converted = if integer {
                    if num != num.trunc() {
                        return Err(what());
                    }
                    PyKind::Int(py_int_of_float(num)?)
                } else if matches_signed_digits(text) {
                    PyKind::Int(py_int_str(text)?)
                } else {
                    PyKind::Float(num)
                };
                let stored = match &converted {
                    PyKind::Int(i) => i.to_value(),
                    PyKind::Float(f) => float_json(*f),
                    _ => Value::Null,
                };
                req.insert(key.to_string(), stored);
                current = converted;
            }
        }
        let ok = match current {
            PyKind::Int(_) => true,
            PyKind::Float(_) => !integer,
            _ => false,
        };
        if !ok {
            return Err(what());
        }
    }
    if let Some(PyKind::Int(n)) = req.get("penalty_last_n").map(kind) {
        if n.cmp_i64(-1) == Ordering::Less {
            return Err(RequestError::invalid(format!(
                "{window_key}: -1 (the whole context), 0 (no penalties) or a positive number of \
                 tokens"
            )));
        }
    }
    if let Some(guard) = req.get("loop_guard") {
        let read = match kind(guard) {
            PyKind::None | PyKind::Bool(_) => None,
            PyKind::Str(s) => {
                let word = console_pyjson::pystr::strip(s, None).to_lowercase();
                match word.as_str() {
                    "true" | "on" | "1" => Some(true),
                    "false" | "off" | "0" => Some(false),
                    _ => return Err(RequestError::invalid("loop_guard: true or false")),
                }
            }
            PyKind::Int(i) if i.is_zero() => Some(false),
            PyKind::Int(i) if i.cmp_i64(1) == Ordering::Equal => Some(true),
            _ => return Err(RequestError::invalid("loop_guard: true or false")),
        };
        if let Some(b) = read {
            req.insert(String::from("loop_guard"), Value::Bool(b));
        }
    }
    Ok(())
}

/// A checked `logit_bias`: `(token id, bias)` pairs in the order the donor's dict keeps them
/// (first appearance of each id; a repeated id, such as `"7"` and `"07"`, keeps its first
/// position and takes the later bias).
#[derive(Debug, Clone, PartialEq, Default)]
pub struct LogitBias(Vec<(u32, f64)>);

impl LogitBias {
    /// No biases.
    pub fn new() -> Self {
        Self::default()
    }

    /// Sets a bias as a Python dict assignment does: in place for a known id, appended
    /// otherwise.
    fn set(&mut self, index: &mut HashMap<u32, usize>, id: u32, bias: f64) {
        match index.get(&id) {
            Some(&at) => {
                if let Some(slot) = self.0.get_mut(at) {
                    slot.1 = bias;
                }
            }
            None => {
                index.insert(id, self.0.len());
                self.0.push((id, bias));
            }
        }
    }

    /// The pairs in the donor's dict order.
    pub fn entries(&self) -> &[(u32, f64)] {
        &self.0
    }

    /// The pairs sorted by id, as the engine line writes them and as
    /// [`crate::engine::Sampling::logit_bias`] holds them.
    pub fn sorted(&self) -> Vec<(u32, f64)> {
        let mut v = self.0.clone();
        v.sort_by_key(|&(id, _)| id);
        v
    }

    /// True when there is no bias.
    pub fn is_empty(&self) -> bool {
        self.0.is_empty()
    }

    /// The map as the donor stores it back into the request (`{id: float(bias)}`), with the
    /// ids as JSON object keys.
    pub fn to_value(&self) -> Value {
        let mut m = Map::new();
        for (id, bias) in &self.0 {
            m.insert(id.to_string(), float_json(*bias));
        }
        Value::Object(m)
    }

    fn index(&self) -> HashMap<u32, usize> {
        self.0
            .iter()
            .enumerate()
            .map(|(i, (id, _))| (*id, i))
            .collect()
    }
}

/// OpenAI's `logit_bias` (`{"<token id>": bias}`, bias -100..100) checked, or a refusal
/// naming the field. A bias of -100 bans the token. `vocab_size` of `None` or `Some(0)`
/// skips the vocabulary checks, as the donor's `len(tokens) or None` does.
///
/// Behavior reference: project-maya serve/server.py:694-718 at 7e68a30f.
pub fn logit_bias_of(value: &Value, vocab_size: Option<u64>) -> Result<LogitBias, RequestError> {
    let vocab = vocab_size.filter(|&v| v > 0);
    let map = match kind(value) {
        PyKind::None => return Ok(LogitBias::new()),
        PyKind::Dict(m) => m,
        _ => {
            return Err(RequestError::invalid(
                "logit_bias: an object of {\"<token id>\": bias}",
            ))
        }
    };
    let mut out = LogitBias::new();
    let mut index = HashMap::new();
    let biases_msg = "logit_bias: biases are numbers from -100 to 100";
    for (token, bias) in map {
        if token.is_empty() || !token.bytes().all(|b| b.is_ascii_digit()) {
            return Err(RequestError::invalid(
                "logit_bias: token ids are non-negative integers",
            ));
        }
        let tid = py_int_str(token)?;
        let outside = tid.cmp_i64(LOGIT_BIAS_MAX_ID) == Ordering::Greater
            || vocab.is_some_and(|v| tid.to_u64().is_none_or(|t| t >= v));
        if outside {
            return Err(RequestError::invalid(format!(
                "logit_bias: token {tid} is outside the model's vocabulary"
            )));
        }
        let id = tid
            .to_u64()
            .and_then(|t| u32::try_from(t).ok())
            .ok_or_else(|| RequestError::invalid(biases_msg))?;
        let b = match kind(bias) {
            PyKind::Str(s) => py_float_str(s).ok_or_else(|| RequestError::invalid(biases_msg))?,
            PyKind::Int(i) => {
                if i.cmp_i64(-100) == Ordering::Less || i.cmp_i64(100) == Ordering::Greater {
                    return Err(RequestError::invalid(biases_msg));
                }
                i.to_f64()?
            }
            PyKind::Float(f) => f,
            _ => return Err(RequestError::invalid(biases_msg)),
        };
        if !(-100.0..=100.0).contains(&b) {
            return Err(RequestError::invalid(biases_msg));
        }
        out.set(&mut index, id, b);
    }
    if let Some(v) = vocab {
        let banned = out.0.iter().filter(|(_, b)| *b <= -100.0).count();
        if u64::try_from(banned).unwrap_or(u64::MAX) >= v {
            return Err(RequestError::invalid(
                "logit_bias: it cannot ban the whole vocabulary",
            ));
        }
    }
    Ok(out)
}

/// The engine's `logprobs=<n>` for a request (n alternatives a token, 0..20), `None` when
/// it does not ask. `"logprobs": true` asks; `top_logprobs` (an integer, or digits in a
/// string) says how many alternatives, 0 when absent; `top_logprobs` without `logprobs`
/// true, or a value of the wrong type, is refused naming the field.
///
/// Behavior reference: project-maya serve/server.py:506-521 at 7e68a30f.
pub fn logprobs_of(req: &Map<String, Value>) -> Result<Option<u8>, RequestError> {
    let lp = req.get("logprobs").map(kind).unwrap_or(PyKind::None);
    let asked = match lp {
        PyKind::None => false,
        PyKind::Bool(b) => b,
        _ => return Err(RequestError::invalid("logprobs: true or false")),
    };
    let mut top = req.get("top_logprobs").map(kind).unwrap_or(PyKind::None);
    if let PyKind::Str(s) = top {
        if matches_digits(s) {
            top = PyKind::Int(py_int_str(s)?);
        }
    }
    let n = match top {
        PyKind::None => None,
        PyKind::Int(i) => {
            let n = i
                .to_u64()
                .filter(|&n| n <= u64::from(TOP_LOGPROBS_MAX))
                .and_then(|n| u8::try_from(n).ok())
                .ok_or_else(|| {
                    RequestError::invalid(format!(
                        "top_logprobs: an integer from 0 to {TOP_LOGPROBS_MAX}"
                    ))
                })?;
            if !asked {
                return Err(RequestError::invalid(
                    "top_logprobs: it needs \"logprobs\": true",
                ));
            }
            Some(n)
        }
        _ => {
            return Err(RequestError::invalid(format!(
                "top_logprobs: an integer from 0 to {TOP_LOGPROBS_MAX}"
            )))
        }
    };
    Ok(if asked { Some(n.unwrap_or(0)) } else { None })
}

/// [`logprobs_of`] for a request already checked: `None` for one it would refuse.
///
/// Behavior reference: project-maya serve/server.py:524-529 at 7e68a30f.
pub fn logprobs_asked(req: &Map<String, Value>) -> Option<u8> {
    logprobs_of(req).ok().flatten()
}

/// A request's own stop strings: OpenAI's `stop` (a string or a list) or, when `stop` is
/// absent or null, Anthropic's `stop_sequences`; the first 16 non-empty strings of a list.
///
/// Behavior reference: project-maya serve/server.py:624-632 at 7e68a30f.
pub fn client_stop_strings(req: &Map<String, Value>) -> Vec<String> {
    let mut s = req.get("stop");
    if is_null(s) {
        s = req.get("stop_sequences");
    }
    match s {
        Some(Value::String(one)) => {
            if one.is_empty() {
                Vec::new()
            } else {
                vec![one.clone()]
            }
        }
        Some(Value::Array(items)) => items
            .iter()
            .filter_map(|x| match x {
                Value::String(t) if !t.is_empty() => Some(t.clone()),
                _ => None,
            })
            .take(STOP_STRINGS_MAX)
            .collect(),
        _ => Vec::new(),
    }
}

/// `a or b or ... or 0` with Python truthiness.
fn first_truthy<'a>(req: &'a Map<String, Value>, keys: &[&str]) -> Option<&'a Value> {
    keys.iter().filter_map(|k| req.get(*k)).find(|v| truthy(v))
}

/// An OpenAI request's answer budget, `int(max_completion_tokens or max_tokens or 0)`.
/// Zero or below means the rest of the context. A value `int()` cannot read is refused as
/// the donor refuses it (`ValueError`, `TypeError` or `OverflowError`).
///
/// Behavior reference: project-maya serve/server.py:6571 at 7e68a30f.
pub fn openai_max_tokens(req: &Map<String, Value>) -> Result<PyInt, RequestError> {
    match first_truthy(req, &["max_completion_tokens", "max_tokens"]) {
        Some(v) => py_int(v),
        None => Ok(PyInt::zero()),
    }
}

/// An Anthropic request's answer budget, `int(max_tokens or 0)`. Zero or below means the
/// rest of the context.
///
/// Behavior reference: project-maya serve/server.py:6679 at 7e68a30f.
pub fn anthropic_max_tokens(req: &Map<String, Value>) -> Result<PyInt, RequestError> {
    match first_truthy(req, &["max_tokens"]) {
        Some(v) => py_int(v),
        None => Ok(PyInt::zero()),
    }
}

/// What the request checks need to know about the engine and the tokenizer.
#[derive(Debug, Clone, Default)]
pub struct CheckContext {
    /// The engine's capability flags (`INFO logit_bias=1`, `INFO logprobs=<n>`, `INFO
    /// ablate=1`).
    pub caps: EngineCaps,
    /// The tokenizer's vocabulary size (`len(tok.tokens)`); `None` or `Some(0)` skips the
    /// vocabulary checks of `logit_bias`.
    pub vocab_size: Option<u64>,
    /// The token ids that end an answer (the stop ids and the end-of-sequence ids), which
    /// `ignore_eos` bans. Any order; duplicates are ignored.
    pub end_ids: Vec<u32>,
}

/// What [`check_request`] read, in typed form, beside the fields it rewrote in the map.
#[derive(Debug, Clone, PartialEq, Default)]
pub struct CheckedRequest {
    /// The checked biases, with `ignore_eos`'s bans merged in; `None` when the request has
    /// no `logit_bias` key and no `ignore_eos`, in which case the map was left alone.
    pub logit_bias: Option<LogitBias>,
    /// `ablate: true`, accepted only for an engine that advertises it (deviation POL-1).
    pub ablate: bool,
    /// `ignore_eos: true`.
    pub ignore_eos: bool,
    /// The log-probabilities asked for (`logprobs_of`).
    pub logprobs: Option<u8>,
    /// The request's own loop-guard choice, when it made one.
    pub loop_guard: Option<bool>,
}

/// A request's sampling fields, `logit_bias`, `ablate`, `ignore_eos` and `logprobs`,
/// checked before anything is sent, and kept in the form the engine line takes. A feature
/// the engine does not apply is refused, not ignored: a non-empty `logit_bias` or
/// `ignore_eos` needs `INFO logit_bias=1`, `logprobs` needs `INFO logprobs=<n>` with n at
/// least the alternatives asked for. `ablate: true` is refused unless the engine advertises
/// `INFO ablate=1`, which no engine of this increment does (deviation POL-1.1).
///
/// Behavior reference: project-maya serve/server.py:2489-2530 at 7e68a30f.
pub fn check_request(
    req: &mut Map<String, Value>,
    ctx: &CheckContext,
) -> Result<CheckedRequest, RequestError> {
    check_request_sampling(req)?;
    let mut bias = logit_bias_of(
        req.get("logit_bias").unwrap_or(&Value::Null),
        ctx.vocab_size,
    )?;
    if !bias.is_empty() && !ctx.caps.logit_bias {
        return Err(RequestError::invalid(format!(
            "logit_bias: this engine does not apply token biases - {UPDATE_HINT}"
        )));
    }
    // Deviation POL-1: `ablate` is recognized and refused unless the engine advertises
    // it; the Models-page switch the donor's message points to is not ported (POL-1.2).
    let ablate = match req.get("ablate").map(kind).unwrap_or(PyKind::None) {
        PyKind::None => false,
        PyKind::Bool(b) => b,
        _ => return Err(RequestError::invalid("ablate: true or false")),
    };
    if ablate && !ctx.caps.ablate {
        return Err(RequestError::invalid(
            "ablate: this model has no refusal direction loaded",
        ));
    }
    let ignore = match req.get("ignore_eos").map(kind).unwrap_or(PyKind::None) {
        PyKind::None => false,
        PyKind::Bool(b) => b,
        _ => return Err(RequestError::invalid("ignore_eos: true or false")),
    };
    if ignore {
        let limit = match openai_max_tokens(req) {
            Ok(n) => n,
            Err(RequestError::Overflow(m)) => return Err(RequestError::Overflow(m)),
            Err(_) => PyInt::zero(),
        };
        if limit.cmp_i64(0) != Ordering::Greater {
            return Err(RequestError::invalid(
                "ignore_eos: needs max_tokens (the answer would run until the context is full)",
            ));
        }
        if !ctx.caps.logit_bias {
            return Err(RequestError::invalid(format!(
                "ignore_eos: this engine does not apply token biases - {UPDATE_HINT}"
            )));
        }
        let mut ends = ctx.end_ids.clone();
        ends.sort_unstable();
        ends.dedup();
        let mut index = bias.index();
        for t in ends {
            bias.set(&mut index, t, -100.0);
        }
    }
    let has_key = req.contains_key("logit_bias");
    if has_key || ignore {
        req.insert(String::from("logit_bias"), bias.to_value());
    }
    let n = logprobs_of(req)?;
    if matches!(req.get("top_logprobs"), Some(Value::String(_))) {
        let stored = n.map_or(Value::Null, Value::from);
        req.insert(String::from("top_logprobs"), stored);
    }
    if let Some(n) = n {
        if ctx.caps.logprobs_max.is_none_or(|top| top < n) {
            return Err(RequestError::invalid(format!(
                "logprobs: this model's engine does not report token log-probabilities (the \
                 DeepSeek engine does - {UPDATE_HINT} if it is that one)"
            )));
        }
    }
    let loop_guard = match req.get("loop_guard") {
        Some(Value::Bool(b)) => Some(*b),
        _ => None,
    };
    Ok(CheckedRequest {
        logit_bias: (has_key || ignore).then_some(bias),
        ablate,
        ignore_eos: ignore,
        logprobs: n,
        loop_guard,
    })
}
