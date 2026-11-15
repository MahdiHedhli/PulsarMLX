//! Owned by API-04. Sampling normalization, shared defaults and their precedence.
//!
//! - [`sampling_defaults_from_config`] checks the run config's `sampling` block at start-up;
//!   [`run_sampling_defaults`] picks it, or the model's own defaults when the config has no
//!   block.
//! - [`effective_sampling`] applies the precedence: a request's own non-null value, then
//!   the shared defaults, then the run-config (or model) defaults, then nothing.
//! - [`ResolvedSampling`] applies the engine's semantic rules (greedy, the top-k widest
//!   list, the penalty window) and lists the sampling keys in the engine line's order. The
//!   line's text and its other keys (thinking, tune, projection, bias, restore, logprobs)
//!   belong to the engine encoder of ENG-03.
//!
//! Qualified on synthetic backends only.

use std::cmp::Ordering;
use std::fmt;

use serde_json::{Map, Value};

use crate::request::pynum::{float_json, kind, py_int_of_float, PyInt, PyKind};
use crate::request::pyrepr::repr_value;
use crate::request::{RequestError, SharedDefaults};

/// The most tokens the engines count for the penalties: a window of -1 ("the whole
/// context") means this many.
///
/// Behavior reference: project-maya serve/server.py:635-637 at 7e68a30f.
pub const PENALTY_WINDOW_MAX: u32 = 4096;

/// The penalty window when a request names none: the last 64 tokens.
///
/// Behavior reference: project-maya serve/server.py:1311-1319 at 7e68a30f.
pub const PENALTY_WINDOW_DEFAULT: u32 = 64;

/// The widest candidate list the engines' sampled path keeps: `top_k` 0 ("off") and any
/// value above it become this.
///
/// Behavior reference: project-maya serve/server.py:1274-1277 at 7e68a30f.
pub const TOP_K_WIDEST: u32 = 64;

/// A run config's `sampling` block refused at start-up. The message is the one line the
/// server prints on standard error before it exits with a non-zero status.
///
/// The donor prints each "unknown key, ignored" note on standard output as it reaches the
/// key, so the notes for unknown keys placed before the refused one are already out when
/// it exits. [`ConfigSamplingError::notes`] carries those notes: the caller prints them,
/// in order, before the refusal line.
///
/// Behavior reference: project-maya serve/server.py:6957 at 7e68a30f.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ConfigSamplingError {
    message: String,
    notes: Vec<String>,
}

impl ConfigSamplingError {
    fn new(message: String) -> Self {
        ConfigSamplingError {
            message,
            notes: Vec::new(),
        }
    }

    /// The line printed on standard error.
    pub fn message(&self) -> &str {
        &self.message
    }

    /// The "unknown key, ignored" notes for the keys before the refused one, printed
    /// before [`ConfigSamplingError::message`].
    pub fn notes(&self) -> &[String] {
        &self.notes
    }
}

impl fmt::Display for ConfigSamplingError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.message)
    }
}

impl std::error::Error for ConfigSamplingError {}

/// A checked run-config `sampling` block.
#[derive(Debug, Clone, PartialEq, Default)]
pub struct ConfigSampling {
    /// The defaults, in the config's order, numbers stored as the donor stores them.
    pub values: Map<String, Value>,
    /// One `[console] ...: unknown key, ignored` line for each key the server does not use.
    pub notes: Vec<String>,
}

/// `value` compared with a small integer as Python compares numbers; `None` for NaN, for
/// which every comparison is false.
fn cmp_num(k: &PyKind<'_>, x: i64) -> Option<Ordering> {
    match k {
        PyKind::Int(i) => Some(i.cmp_i64(x)),
        PyKind::Float(f) => {
            let xf = f64::from(i32::try_from(x).unwrap_or(0));
            f.partial_cmp(&xf)
        }
        _ => None,
    }
}

fn is_number(k: &PyKind<'_>) -> bool {
    matches!(k, PyKind::Int(_) | PyKind::Float(_))
}

/// A Python exception the donor does not catch at start-up, as the last line of its
/// traceback.
fn uncaught(e: RequestError) -> ConfigSamplingError {
    ConfigSamplingError::new(format!("{}: {}", e.python_type(), e.message()))
}

/// `float(value)` for a number, or the start-up failure Python raises.
fn to_float(k: &PyKind<'_>) -> Result<f64, ConfigSamplingError> {
    match k {
        PyKind::Int(i) => i.to_f64().map_err(uncaught),
        PyKind::Float(f) => Ok(*f),
        _ => Ok(f64::NAN),
    }
}

/// `value != int(value)`, raising as Python does for NaN and the infinities.
fn not_integral(k: &PyKind<'_>) -> Result<bool, ConfigSamplingError> {
    match k {
        PyKind::Int(_) => Ok(false),
        PyKind::Float(f) => {
            py_int_of_float(*f).map_err(uncaught)?;
            Ok(*f != f.trunc())
        }
        _ => Ok(true),
    }
}

fn to_int(k: &PyKind<'_>) -> Result<PyInt, ConfigSamplingError> {
    match k {
        PyKind::Int(i) => Ok(i.clone()),
        PyKind::Float(f) => py_int_of_float(*f).map_err(uncaught),
        _ => Ok(PyInt::zero()),
    }
}

/// The run config's optional `sampling` block: defaults for the sampling fields a request
/// leaves out. Supported: `temperature`, `top_p`, `top_k`, `min_p`, `presence_penalty`,
/// `repetition_penalty`, `frequency_penalty`, `penalty_last_n`, `seed` and
/// `experimental_speed_projection`. A bad value refuses to start the server with the
/// donor's message; an unknown key is named in a note and ignored. `null` values are
/// skipped. A `sampling` value that is falsy counts as no block.
///
/// Deviation POL-1.2: the donor's `ablate` key (the refusal-ablation default) is not
/// ported, so it is an unknown key here.
///
/// Behavior reference: project-maya serve/server.py:6899-6960 at 7e68a30f.
pub fn sampling_defaults_from_config(
    cfg: &Map<String, Value>,
) -> Result<ConfigSampling, ConfigSamplingError> {
    let mut out = ConfigSampling::default();
    let block = match cfg.get("sampling") {
        None => return Ok(out),
        Some(v) if !console_pyjson::loads::truthy(v) => return Ok(out),
        Some(Value::Object(m)) => m,
        Some(other) => {
            return Err(ConfigSamplingError::new(format!(
                "AttributeError: '{}' object has no attribute 'items'",
                kind(other).type_name()
            )))
        }
    };
    for (key, value) in block {
        if value.is_null() {
            continue;
        }
        match check_key(key, value) {
            Ok(Some(stored)) => {
                out.values.insert(key.clone(), stored);
            }
            Ok(None) => out.notes.push(format!(
                "[console] config sampling.{key}={}: unknown key, ignored",
                repr_value(value)
            )),
            Err(mut e) => {
                e.notes = out.notes;
                return Err(e);
            }
        }
    }
    Ok(out)
}

/// One key of the `sampling` block: the value as the donor stores it, `None` for a key the
/// server does not use, or the start-up refusal.
fn check_key(key: &str, value: &Value) -> Result<Option<Value>, ConfigSamplingError> {
    let k = kind(value);
    let number = is_number(&k);
    let refuse = |expected: &str| {
        ConfigSamplingError::new(format!(
            "[console] config sampling.{key}={}: {expected}",
            repr_value(value)
        ))
    };
    let stored = match key {
        "temperature" => {
            if !number || cmp_num(&k, 0) == Some(Ordering::Less) {
                return Err(refuse("expected a number >= 0 (0 = greedy)"));
            }
            float_json(to_float(&k)?)
        }
        "top_p" => {
            let ok = cmp_num(&k, 0) == Some(Ordering::Greater)
                && matches!(cmp_num(&k, 1), Some(Ordering::Less | Ordering::Equal));
            if !number || !ok {
                return Err(refuse("expected 0 < top_p <= 1"));
            }
            float_json(to_float(&k)?)
        }
        "min_p" => {
            let ok = matches!(cmp_num(&k, 0), Some(Ordering::Greater | Ordering::Equal))
                && matches!(cmp_num(&k, 1), Some(Ordering::Less | Ordering::Equal));
            if !number || !ok {
                return Err(refuse("expected 0 <= min_p <= 1"));
            }
            float_json(to_float(&k)?)
        }
        "top_k" => {
            if !number
                || not_integral(&k)?
                || cmp_num(&k, 1) == Some(Ordering::Less)
                || cmp_num(&k, 64) == Some(Ordering::Greater)
            {
                return Err(refuse("the sampled path takes an integer 1..64"));
            }
            to_int(&k)?.to_value()
        }
        "presence_penalty" | "frequency_penalty" => {
            if !number || cmp_num(&k, 0) == Some(Ordering::Less) {
                return Err(refuse("expected a number >= 0"));
            }
            float_json(to_float(&k)?)
        }
        "repetition_penalty" => {
            if !number || matches!(cmp_num(&k, 0), Some(Ordering::Less | Ordering::Equal)) {
                return Err(refuse("expected a number > 0 (1 = off)"));
            }
            float_json(to_float(&k)?)
        }
        "penalty_last_n" => {
            if !number || not_integral(&k)? || cmp_num(&k, -1) == Some(Ordering::Less) {
                return Err(refuse(
                    "expected an integer >= -1 (0 = no penalties, -1 = the whole context)",
                ));
            }
            to_int(&k)?.to_value()
        }
        "seed" => {
            if !number
                || not_integral(&k)?
                || matches!(cmp_num(&k, 0), Some(Ordering::Less | Ordering::Equal))
            {
                return Err(refuse("expected a positive integer"));
            }
            to_int(&k)?.to_value()
        }
        "experimental_speed_projection" => match value {
            Value::Bool(b) => Value::Bool(*b),
            _ => {
                return Err(refuse(
                    "expected true or false (the default for requests that leave it out, \
                     when the engine has the vector)",
                ))
            }
        },
        _ => return Ok(None),
    };
    Ok(Some(stored))
}

/// Where the run's sampling defaults come from.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DefaultsOrigin {
    /// The run config's `sampling` block.
    Config,
    /// The model's own defaults, for a config without a `sampling` key.
    Model,
}

/// The sampling defaults of a run: the config's block, or the model's own.
#[derive(Debug, Clone, PartialEq)]
pub struct RunSamplingDefaults {
    /// The defaults.
    pub values: Map<String, Value>,
    /// Where they come from.
    pub origin: DefaultsOrigin,
    /// Notes on ignored config keys.
    pub notes: Vec<String>,
}

impl RunSamplingDefaults {
    /// The start-up line naming the defaults (`[console] sampling defaults from the config:
    /// temperature=0.7, top_k=40`), or `None` when there are none.
    ///
    /// Behavior reference: project-maya serve/server.py:7213-7215 at 7e68a30f.
    pub fn announcement(&self) -> Option<String> {
        if self.values.is_empty() {
            return None;
        }
        let pretty: Vec<String> = self
            .values
            .iter()
            .map(|(k, v)| format!("{k}={}", crate::request::pyrepr::str_value(v)))
            .collect();
        let from = match self.origin {
            DefaultsOrigin::Config => "config",
            DefaultsOrigin::Model => "model",
        };
        Some(format!(
            "[console] sampling defaults from the {from}: {}",
            pretty.join(", ")
        ))
    }
}

/// The run's sampling defaults: the config's checked `sampling` block, or, when the config
/// has no `sampling` key at all, the model's own defaults (`model_defaults`, supplied by
/// the model catalog; the catalog ships empty in this increment).
///
/// Behavior reference: project-maya serve/server.py:7208-7210 at 7e68a30f. The donor's
/// ablation default (7211-7212) is not ported (deviation POL-1.2).
pub fn run_sampling_defaults(
    cfg: &Map<String, Value>,
    model_defaults: Option<&Map<String, Value>>,
) -> Result<RunSamplingDefaults, ConfigSamplingError> {
    let checked = sampling_defaults_from_config(cfg)?;
    if cfg.contains_key("sampling") {
        return Ok(RunSamplingDefaults {
            values: checked.values,
            origin: DefaultsOrigin::Config,
            notes: checked.notes,
        });
    }
    Ok(RunSamplingDefaults {
        values: model_defaults.cloned().unwrap_or_default(),
        origin: DefaultsOrigin::Model,
        notes: checked.notes,
    })
}

/// The sampling a request runs with: the run's defaults, then the shared defaults over
/// them, then every non-null field of the request over both. A request field set to
/// `null` falls back to the defaults; an explicit `temperature: 0` stays greedy. With no
/// defaults at all, the request is used as it is. Key order follows Python's `{**a, **b}`.
///
/// Deviation SEC-6.1: a request key that starts with an underscore never reaches the
/// result, on either path, even when the caller did not strip it at the API boundary
/// ([`crate::request::strip_internal_keys`]); internal flags travel in typed structures.
///
/// Behavior reference: project-maya serve/server.py:4275-4278 at 7e68a30f.
pub fn effective_sampling(
    run_defaults: &Map<String, Value>,
    shared: &SharedDefaults,
    request: &Map<String, Value>,
) -> Map<String, Value> {
    let mut defaults = run_defaults.clone();
    for (k, v) in shared.as_map() {
        defaults.insert(k.clone(), v.clone());
    }
    if defaults.is_empty() {
        return request
            .iter()
            .filter(|(k, _)| !k.starts_with('_'))
            .map(|(k, v)| (k.clone(), v.clone()))
            .collect();
    }
    for (k, v) in request {
        if !v.is_null() && !k.starts_with('_') {
            defaults.insert(k.clone(), v.clone());
        }
    }
    defaults
}

/// The value of one sampling key, written as the engine line writes it: an integer's
/// digits, a float's Python `repr`, or a `bool` as Python's `str` writes it.
#[derive(Debug, Clone, PartialEq)]
pub enum KeyValue {
    /// An integer.
    Int(PyInt),
    /// A float.
    Float(f64),
    /// A `bool`: the donor's `isinstance(seed, int)` admits it, so a seed of `true` is
    /// written `True`.
    Bool(bool),
}

impl fmt::Display for KeyValue {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            KeyValue::Int(i) => write!(f, "{i}"),
            KeyValue::Float(x) => f.write_str(&console_pyjson::float_repr::repr_f64(*x)),
            KeyValue::Bool(b) => f.write_str(if *b { "True" } else { "False" }),
        }
    }
}

/// The penalties that change something, with their window.
#[derive(Debug, Clone, PartialEq)]
pub struct ResolvedPenalties {
    /// `repetition_penalty`, when not 1.
    pub repeat: Option<f64>,
    /// `frequency_penalty`, when not 0.
    pub frequency: Option<f64>,
    /// `presence_penalty`, when not 0.
    pub presence: Option<f64>,
    /// The window: a positive `penalty_last_n` as given, [`PENALTY_WINDOW_MAX`] for -1,
    /// [`PENALTY_WINDOW_DEFAULT`] otherwise.
    pub last_n: PyInt,
}

/// A request's sampling after the engine's semantic rules: `temperature <= 0` is greedy
/// and drops every sampler key but the penalties; `top_p` is kept only below 1; `top_k`
/// 1..64 as given, 0 or above 64 as 64; `min_p` only in (0, 1]; `seed` only above 0 (a
/// `bool` counts as an `int`, so `true` is kept);
/// penalties only when non-neutral, never with a window of 0.
///
/// Behavior reference: project-maya serve/server.py:1217-1219 and 1263-1319 at 7e68a30f.
#[derive(Debug, Clone, PartialEq, Default)]
pub struct ResolvedSampling {
    /// `temperature <= 0`: the engine picks the best token (after the penalties).
    pub greedy: bool,
    /// A temperature above 0 (never set when greedy).
    pub temperature: Option<f64>,
    /// `top_p` below 1.
    pub top_p: Option<f64>,
    /// `top_k`, 1..64.
    pub top_k: Option<u32>,
    /// `min_p` in (0, 1].
    pub min_p: Option<f64>,
    /// A seed above 0: a [`KeyValue::Int`], or [`KeyValue::Bool`] `true`, which the donor's
    /// `isinstance(seed, int) and seed > 0` admits.
    pub seed: Option<KeyValue>,
    /// The penalties that change something.
    pub penalties: Option<ResolvedPenalties>,
}

fn field<'a>(s: &'a Map<String, Value>, key: &str) -> PyKind<'a> {
    s.get(key).map(kind).unwrap_or(PyKind::None)
}

fn penalties_of(s: &Map<String, Value>) -> Result<Option<ResolvedPenalties>, RequestError> {
    let pln = field(s, "penalty_last_n");
    if matches!(&pln, PyKind::Int(i) if i.is_zero()) {
        return Ok(None);
    }
    let read = |key: &str, neutral: f64| -> Result<Option<f64>, RequestError> {
        match field(s, key).int_or_float_f64() {
            Some(r) => {
                let v = r?;
                Ok((v != neutral).then_some(v))
            }
            None => Ok(None),
        }
    };
    let repeat = read("repetition_penalty", 1.0)?;
    let frequency = read("frequency_penalty", 0.0)?;
    let presence = read("presence_penalty", 0.0)?;
    if repeat.is_none() && frequency.is_none() && presence.is_none() {
        return Ok(None);
    }
    let last_n = match &pln {
        PyKind::Int(i) if i.cmp_i64(0) == Ordering::Greater => i.clone(),
        PyKind::Int(i) if i.cmp_i64(-1) == Ordering::Equal => {
            PyInt::from_i64(i64::from(PENALTY_WINDOW_MAX))
        }
        PyKind::Float(f) if *f == -1.0 => PyInt::from_i64(i64::from(PENALTY_WINDOW_MAX)),
        _ => PyInt::from_i64(i64::from(PENALTY_WINDOW_DEFAULT)),
    };
    Ok(Some(ResolvedPenalties {
        repeat,
        frequency,
        presence,
        last_n,
    }))
}

impl ResolvedSampling {
    /// Applies the semantic rules to an effective sampling map ([`effective_sampling`]).
    /// Fields of the wrong type are left out, as the engine line leaves them out. An
    /// integer too large for a float raises `OverflowError` where the donor's `float()`
    /// does.
    ///
    /// A seed of `true` is kept as `seed=True`, as the donor's line writes it (`bool` is an
    /// `int` in Python, and `True > 0`). The request, config and shared-default checks
    /// refuse a boolean seed, so only a model's own defaults can carry one.
    pub fn resolve(s: &Map<String, Value>) -> Result<Self, RequestError> {
        let penalties = penalties_of(s)?;
        let t = field(s, "temperature");
        if let Some(r) = t.number_f64() {
            if r? <= 0.0 {
                return Ok(ResolvedSampling {
                    greedy: true,
                    penalties,
                    ..Self::default()
                });
            }
        }
        let positive = |k: &PyKind<'_>| -> Result<Option<f64>, RequestError> {
            match k.int_or_float_f64() {
                Some(r) => r.map(Some),
                None => Ok(None),
            }
        };
        let temperature = positive(&t)?.filter(|&v| v > 0.0);
        let top_p = positive(&field(s, "top_p"))?.filter(|&v| v < 1.0);
        let top_k = match field(s, "top_k") {
            PyKind::Int(i) if i.cmp_i64(0) != Ordering::Less => Some(
                i.to_u64()
                    .and_then(|v| u32::try_from(v).ok())
                    .filter(|v| (1..=TOP_K_WIDEST).contains(v))
                    .unwrap_or(TOP_K_WIDEST),
            ),
            _ => None,
        };
        let min_p = positive(&field(s, "min_p"))?.filter(|&v| 0.0 < v && v <= 1.0);
        let seed = match field(s, "seed") {
            PyKind::Int(i) if i.cmp_i64(0) == Ordering::Greater => Some(KeyValue::Int(i)),
            PyKind::Bool(true) => Some(KeyValue::Bool(true)),
            _ => None,
        };
        Ok(ResolvedSampling {
            greedy: false,
            temperature,
            top_p,
            top_k,
            min_p,
            seed,
            penalties,
        })
    }

    /// The sampling keys in the engine line's order: `temperature=0` and the penalty keys
    /// when greedy; otherwise `temperature`, `top_p`, `top_k`, `min_p`, the penalty keys
    /// (`penalty_repeat`, `penalty_freq`, `penalty_present`, `penalty_last_n`) and `seed`.
    ///
    /// Behavior reference: project-maya serve/server.py:1262-1287 and 1290-1319 at
    /// 7e68a30f.
    pub fn keys(&self) -> Vec<(&'static str, KeyValue)> {
        let mut out = Vec::new();
        let penalty_keys = |out: &mut Vec<(&'static str, KeyValue)>| {
            if let Some(p) = &self.penalties {
                if let Some(v) = p.repeat {
                    out.push(("penalty_repeat", KeyValue::Float(v)));
                }
                if let Some(v) = p.frequency {
                    out.push(("penalty_freq", KeyValue::Float(v)));
                }
                if let Some(v) = p.presence {
                    out.push(("penalty_present", KeyValue::Float(v)));
                }
                out.push(("penalty_last_n", KeyValue::Int(p.last_n.clone())));
            }
        };
        if self.greedy {
            out.push(("temperature", KeyValue::Int(PyInt::zero())));
            penalty_keys(&mut out);
            return out;
        }
        if let Some(v) = self.temperature {
            out.push(("temperature", KeyValue::Float(v)));
        }
        if let Some(v) = self.top_p {
            out.push(("top_p", KeyValue::Float(v)));
        }
        if let Some(v) = self.top_k {
            out.push(("top_k", KeyValue::Int(PyInt::from_i64(i64::from(v)))));
        }
        if let Some(v) = self.min_p {
            out.push(("min_p", KeyValue::Float(v)));
        }
        penalty_keys(&mut out);
        if let Some(v) = &self.seed {
            out.push(("seed", v.clone()));
        }
        out
    }
}
