//! The shared defaults: the Chat settings that every client gets for what it leaves out
//! ("Use for other apps too", `POST /settings`), checked, and filled into a request.
//!
//! Storing them (the shared-settings file) and the `/settings` route belong to the run
//! config store and the admin routes; this module holds the rules.
//!
//! Behavior reference: project-maya serve/server.py:2571-2609 (`set_shared`,
//! `with_shared`), 6806-6854 (`SHARED_KEYS`, `clean_shared_defaults`) and
//! serve/frontend.py:188-219 (`EFFORT`, `EFFORT_NAMES`, `EFFORT_WORDS`, `effort_level`,
//! `effort_name`) at 7e68a30f.

use std::cmp::Ordering;

use console_pyjson::loads::truthy;
use serde_json::{Map, Value};

use super::error::RequestError;
use super::pynum::{float_json, kind, py_int_of_float, PyInt, PyKind};
use super::pyrepr::repr_str;

/// The settings the dashboard shares with other clients, in the donor's order.
///
/// Behavior reference: project-maya serve/server.py:6806-6807 at 7e68a30f.
pub const SHARED_KEYS: [&str; 10] = [
    "reasoning_effort",
    "temperature",
    "top_p",
    "top_k",
    "seed",
    "max_tokens",
    "experimental_speed_projection",
    "repetition_penalty",
    "frequency_penalty",
    "presence_penalty",
];

/// The thinking-level words a client may use, as the refusal lists them.
///
/// Behavior reference: project-maya serve/frontend.py:200 at 7e68a30f.
pub const EFFORT_WORDS: &str = "none, auto, low, medium, high, xhigh or max";

/// Spellings of a thinking level and the level each means (`None` is "no thinking").
const EFFORT: [(&str, Option<&str>); 13] = [
    ("none", None),
    ("off", None),
    ("minimal", None),
    ("disabled", None),
    ("false", None),
    ("low", Some("low")),
    ("medium", Some("high")),
    ("high", Some("high")),
    ("xhigh", Some("max")),
    ("max", Some("max")),
    ("maximum", Some("max")),
    ("auto", Some("auto")),
    ("default", Some("auto")),
];

/// The level names a five-level template takes by the client's own word.
const EFFORT_NAMES: [&str; 5] = ["low", "medium", "high", "xhigh", "max"];

/// The spelling of a level a client sent, stripped and lower-cased, or `None` for a
/// value that is not a string (`False` is handled by the callers).
fn effort_key(value: &Value) -> Option<String> {
    match value {
        Value::String(s) => Some(console_pyjson::pystr::strip(s, None).to_lowercase()),
        _ => None,
    }
}

/// A client's spelling of a thinking level, as the level's name (`none`, `low`, `high`,
/// `max` or `auto`); `None` when none is given or it is unknown.
///
/// Behavior reference: project-maya serve/frontend.py:203-211 at 7e68a30f.
pub fn effort_level(value: &Value) -> Option<&'static str> {
    match value {
        Value::Null => None,
        Value::String(s) if s.is_empty() => None,
        Value::Bool(false) => Some("none"),
        other => {
            let key = effort_key(other)?;
            EFFORT
                .iter()
                .find(|(k, _)| *k == key)
                .map(|(_, level)| level.unwrap_or("none"))
        }
    }
}

/// A client's spelling of a thinking level, as a five-level template names it (`none`,
/// `auto`, `low`, `medium`, `high`, `xhigh` or `max`); `None` when none is given or it is
/// unknown.
///
/// Behavior reference: project-maya serve/frontend.py:214-219 at 7e68a30f.
pub fn effort_name(value: &Value) -> Option<&'static str> {
    let level = effort_level(value)?;
    if level == "none" {
        return Some(level);
    }
    let key = effort_key(value)?;
    Some(
        EFFORT_NAMES
            .iter()
            .find(|n| **n == key)
            .copied()
            .unwrap_or(level),
    )
}

/// The shared defaults, checked: only known keys, each within its range, in the order the
/// dashboard sent them. Empty means clients use their own settings.
#[derive(Debug, Clone, PartialEq, Default)]
pub struct SharedDefaults(Map<String, Value>);

impl SharedDefaults {
    /// No shared defaults.
    pub fn new() -> Self {
        Self::default()
    }

    /// Checks the `defaults` the dashboard sent ([`clean_shared_defaults`]).
    pub fn from_value(defaults: &Value) -> Result<Self, RequestError> {
        clean_shared_defaults(defaults).map(SharedDefaults)
    }

    /// The checked settings.
    pub fn as_map(&self) -> &Map<String, Value> {
        &self.0
    }

    /// True when clients use their own settings.
    pub fn is_empty(&self) -> bool {
        self.0.is_empty()
    }

    /// The settings as a JSON object.
    pub fn to_value(&self) -> Value {
        Value::Object(self.0.clone())
    }
}

fn number_f64(value: &Value) -> Option<Result<f64, RequestError>> {
    kind(value).number_f64()
}

/// `not number or value != int(value) or not lo <= value [<= hi]`, then `int(value)`:
/// `Ok(None)` when the check fails, the integer when it passes. `int(nan)` raises
/// `ValueError` and `int(inf)` `OverflowError`, as in the donor.
fn checked_int(value: &Value, lo: i64, hi: Option<i64>) -> Result<Option<PyInt>, RequestError> {
    let n = match kind(value) {
        PyKind::Int(i) => i,
        PyKind::Float(f) => {
            let i = py_int_of_float(f)?;
            if f != f.trunc() {
                return Ok(None);
            }
            i
        }
        _ => return Ok(None),
    };
    let in_range =
        n.cmp_i64(lo) != Ordering::Less && hi.is_none_or(|h| n.cmp_i64(h) != Ordering::Greater);
    Ok(in_range.then_some(n))
}

/// The Chat settings other clients get (`POST /settings`), checked: only known keys, each
/// within range, or a refusal naming the bad one. `null` and empty-string values are
/// dropped. Ranges: `reasoning_effort` a level word, `temperature` 0..2, `top_p` (0, 1],
/// `min_p` [0, 1), `top_k` an integer 0..64, `seed` and `max_tokens` positive integers,
/// `repetition_penalty` (0, 10], `frequency_penalty` and `presence_penalty` -2..2,
/// `experimental_speed_projection` a bool. Sampling numbers are stored as floats.
///
/// Behavior reference: project-maya serve/server.py:6810-6854 at 7e68a30f.
pub fn clean_shared_defaults(d: &Value) -> Result<Map<String, Value>, RequestError> {
    let map = match d {
        Value::Null => return Ok(Map::new()),
        Value::Object(m) => m,
        _ => return Err(RequestError::invalid("defaults must be an object")),
    };
    let mut out = Map::new();
    for (key, value) in map {
        if value.is_null() || matches!(value, Value::String(s) if s.is_empty()) {
            continue;
        }
        let in_range = |lo_ok: fn(f64) -> bool| -> Result<Option<f64>, RequestError> {
            match number_f64(value) {
                Some(Ok(f)) => Ok(lo_ok(f).then_some(f)),
                Some(Err(_)) => Ok(None),
                None => Ok(None),
            }
        };
        let stored = match key.as_str() {
            "reasoning_effort" => {
                if effort_level(value).is_none() {
                    return Err(RequestError::invalid(format!(
                        "reasoning_effort: {EFFORT_WORDS}"
                    )));
                }
                Value::String(effort_name(value).unwrap_or("none").to_string())
            }
            "temperature" => match in_range(|v| (0.0..=2.0).contains(&v))? {
                Some(f) => float_json(f),
                None => return Err(RequestError::invalid("temperature: 0..2")),
            },
            "top_p" => match in_range(|v| 0.0 < v && v <= 1.0)? {
                Some(f) => float_json(f),
                None => return Err(RequestError::invalid("top_p: 0 < top_p <= 1")),
            },
            "min_p" => match in_range(|v| (0.0..1.0).contains(&v))? {
                Some(f) => float_json(f),
                None => return Err(RequestError::invalid("min_p: 0 <= min_p < 1")),
            },
            "top_k" => match checked_int(value, 0, Some(64))? {
                Some(i) => i.to_value(),
                None => return Err(RequestError::invalid("top_k: an integer 0..64")),
            },
            "seed" | "max_tokens" => match checked_int(value, 1, None)? {
                Some(i) => i.to_value(),
                None => return Err(RequestError::invalid(format!("{key}: a positive integer"))),
            },
            "repetition_penalty" => match in_range(|v| 0.0 < v && v <= 10.0)? {
                Some(f) => float_json(f),
                None => {
                    return Err(RequestError::invalid(
                        "repetition_penalty: above 0, at most 10 (1 = off)",
                    ))
                }
            },
            "frequency_penalty" | "presence_penalty" => {
                match in_range(|v| (-2.0..=2.0).contains(&v))? {
                    Some(f) => float_json(f),
                    None => return Err(RequestError::invalid(format!("{key}: -2..2 (0 = off)"))),
                }
            }
            "experimental_speed_projection" => match value {
                Value::Bool(b) => Value::Bool(*b),
                _ => {
                    return Err(RequestError::invalid(
                        "experimental_speed_projection: true or false",
                    ))
                }
            },
            _ => {
                return Err(RequestError::invalid(format!(
                    "unknown setting {}",
                    repr_str(key)
                )))
            }
        };
        out.insert(key.clone(), stored);
    }
    Ok(out)
}

/// The API a request came in on, for [`with_shared`].
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Dialect {
    /// OpenAI chat completions, the Responses API and the model-API routes.
    OpenAi,
    /// Anthropic messages.
    Anthropic,
}

/// Internal markers that travel with a request in typed form, never in the client's map
/// (deviation SEC-6.2).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub struct InternalFlags {
    /// The thinking level was filled from the shared defaults, not asked for by the
    /// request itself (the donor's `_level_shared`, set only for a GLM-DSA template).
    pub level_shared: bool,
}

/// The request with the shared thinking level and answer budget filled in where it has
/// none of its own. `max_tokens` is filled when the request has neither max field. For
/// OpenAI, `reasoning_effort` is filled when the request has no `reasoning_effort`, no
/// `reasoning` and no `chat_template_kwargs.enable_thinking` or `.reasoning_effort`; for
/// Anthropic, `thinking: {"type": "disabled"}` (level `none`) or `output_config: {"effort":
/// <level>}` when the request has neither `thinking` nor `output_config`. When a level was
/// filled and the template is GLM-DSA (`glm_dsa`), [`InternalFlags::level_shared`] is set.
///
/// Behavior reference: project-maya serve/server.py:2584-2609 at 7e68a30f.
pub fn with_shared(
    req: &Map<String, Value>,
    dialect: Dialect,
    shared: &SharedDefaults,
    glm_dsa: bool,
) -> (Map<String, Value>, InternalFlags) {
    let s = shared.as_map();
    let mut flags = InternalFlags::default();
    if s.is_empty() {
        return (req.clone(), flags);
    }
    let mut out = req.clone();
    let has = |m: &Map<String, Value>, k: &str| m.get(k).is_some_and(truthy);
    if let Some(max) = s.get("max_tokens") {
        if !has(&out, "max_tokens") && !has(&out, "max_completion_tokens") {
            out.insert(String::from("max_tokens"), max.clone());
        }
    }
    let mut filled = false;
    if let Some(effort) = s.get("reasoning_effort").filter(|e| truthy(e)) {
        match dialect {
            Dialect::OpenAi => {
                let ctk_has = |k: &str| match out.get("chat_template_kwargs") {
                    Some(Value::Object(m)) => m.contains_key(k),
                    _ => false,
                };
                let own = has(&out, "reasoning_effort")
                    || has(&out, "reasoning")
                    || ctk_has("enable_thinking")
                    || ctk_has("reasoning_effort");
                if !own {
                    out.insert(String::from("reasoning_effort"), effort.clone());
                    filled = true;
                }
            }
            Dialect::Anthropic => {
                if !has(&out, "thinking") && !has(&out, "output_config") {
                    if effort.as_str() == Some("none") {
                        let mut t = Map::new();
                        t.insert(String::from("type"), Value::String("disabled".into()));
                        out.insert(String::from("thinking"), Value::Object(t));
                    } else {
                        let mut c = Map::new();
                        c.insert(String::from("effort"), effort.clone());
                        out.insert(String::from("output_config"), Value::Object(c));
                    }
                    filled = true;
                }
            }
        }
    }
    flags.level_shared = filled && glm_dsa;
    (out, flags)
}
