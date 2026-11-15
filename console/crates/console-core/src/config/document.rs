//! The run-config document: an order-preserving JSON object with typed accessors for the
//! keys the server reads at start-up.
//!
//! Unknown keys are kept, in their order, through every read and rewrite; accessors read the
//! keys the donor reads with the donor's coercions, defaults and messages.
//!
//! Behavior reference: project-maya serve/server.py:599-621 (`model_management_setting`,
//! `loop_guard_setting`), 5393-5400 (`parse_cors_origins`), 7139-7166 and 7313-7333 (API key,
//! host, server log, `fit_max_tokens`, `idle_unload_s`, CORS), serve/models.py:52-53 and
//! 662-666 (secret masking), 470-481 (a mask sent back keeps the value), 825-840 (what
//! counts as an engine change) at 7e68a30f.

use std::fmt;
use std::path::PathBuf;

use console_pyjson::dumps::DumpsError;
use console_pyjson::loads::{truthy, LoadsError, UnicodeDecodeError};
use console_pyjson::pystr;
use serde_json::{Map, Value};

use super::py;

/// What the Models page shows instead of a secret's value.
///
/// Behavior reference: project-maya serve/models.py:53 at 7e68a30f.
pub const MASK: &str = "***";

/// The host the server listens on when neither the command line nor the run config names
/// one.
pub const DEFAULT_HOST: &str = "127.0.0.1";

/// The run-config keys whose change means the engine must start again (the engine's command
/// or environment).
///
/// Behavior reference: project-maya serve/models.py:829 at 7e68a30f.
pub const ENGINE_KEYS: [&str; 5] = ["args", "env", "gpu", "vision", "vision_off"];

/// The message of a `cors_origins` value that is not a list of non-blank strings.
pub const CORS_ORIGINS_MESSAGE: &str =
    "\"cors_origins\" must be a list of origins like \"http://127.0.0.1:8090\" (or [\"*\"])";

/// The message of an `allowed_hosts` value that is not a list of non-blank strings
/// (deviation SEC-1.1; the key has no donor counterpart, so the wording is the console's).
pub const ALLOWED_HOSTS_MESSAGE: &str =
    "\"allowed_hosts\" must be a list of host names like \"pulsar.local\"";

/// Why a run config could not be read, written or used.
#[derive(Debug)]
pub enum ConfigError {
    /// Reading, writing, renaming or changing the times of a file failed.
    Io {
        /// The file.
        path: PathBuf,
        /// The operating system's error.
        source: std::io::Error,
    },
    /// The file is larger than [`super::MAX_CONFIG_BYTES`].
    TooLarge {
        /// The file.
        path: PathBuf,
    },
    /// The file is not UTF-8 (Python's `UnicodeDecodeError` from the `utf-8-sig` codec).
    Unicode {
        /// The file.
        path: PathBuf,
        /// Python's error.
        error: UnicodeDecodeError,
    },
    /// The file is not JSON (Python's `json.JSONDecodeError` and relatives).
    Json {
        /// The file.
        path: PathBuf,
        /// Python's error.
        error: LoadsError,
    },
    /// The file holds JSON that is not an object.
    NotAnObject {
        /// The file.
        path: PathBuf,
    },
    /// The document could not be serialized (Python's `ValueError` from `json.dumps`).
    Encode {
        /// The file being written.
        path: PathBuf,
        /// Python's error.
        error: DumpsError,
    },
    /// A key holds a value the server cannot start with. The text is the message alone;
    /// start-up prints it after `config: `, as the donor does for `cors_origins`.
    Invalid(String),
}

impl fmt::Display for ConfigError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ConfigError::Io { path, source } => write!(f, "{}: {source}", path.display()),
            ConfigError::TooLarge { path } => write!(
                f,
                "{}: larger than {} bytes",
                path.display(),
                super::MAX_CONFIG_BYTES
            ),
            ConfigError::Unicode { path, error } => write!(f, "{}: {error}", path.display()),
            ConfigError::Json { path, error } => write!(f, "{}: {error}", path.display()),
            ConfigError::NotAnObject { path } => {
                write!(f, "{}: a run config must be a JSON object", path.display())
            }
            ConfigError::Encode { path, error } => write!(f, "{}: {error}", path.display()),
            ConfigError::Invalid(message) => f.write_str(message),
        }
    }
}

impl std::error::Error for ConfigError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            ConfigError::Io { source, .. } => Some(source),
            ConfigError::Json { error, .. } => Some(error),
            ConfigError::Encode { error, .. } => Some(error),
            _ => None,
        }
    }
}

/// A run config: a JSON object whose keys keep their order. Equality is Python's `dict`
/// equality (key order ignored, `1 == 1.0 == True`).
///
/// `Debug` shows a non-empty top-level `api_key` as [`MASK`] and the `env` block as
/// [`shown_env`] gives it, so formatting a run config does not print its secrets.
#[derive(Clone, Default)]
pub struct RunConfig {
    map: Map<String, Value>,
}

impl PartialEq for RunConfig {
    fn eq(&self, other: &Self) -> bool {
        py::py_eq(&self.to_value(), &other.to_value())
    }
}

impl fmt::Debug for RunConfig {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let mut shown = self.map.clone();
        if let Some(key) = shown.get_mut("api_key") {
            *key = masked_value(key);
        }
        if let Some(env) = shown.get_mut("env") {
            if let Value::Object(block) = env {
                *env = Value::Object(shown_env(Some(block)));
            } else if truthy(env) {
                *env = Value::String(String::from(MASK));
            }
        }
        f.debug_struct("RunConfig").field("map", &shown).finish()
    }
}

/// A secret value as `Debug` shows it: an empty string or `null` as it is, anything else
/// [`MASK`].
pub(crate) fn masked_value(v: &Value) -> Value {
    match v {
        Value::Null => Value::Null,
        Value::String(s) if s.is_empty() => Value::String(String::new()),
        _ => Value::String(String::from(MASK)),
    }
}

impl From<Map<String, Value>> for RunConfig {
    fn from(map: Map<String, Value>) -> Self {
        RunConfig { map }
    }
}

impl RunConfig {
    /// An empty run config (`{}`), what an unreadable file reads as.
    pub fn new() -> Self {
        Self::default()
    }

    /// The document as an object value, keys in order.
    pub fn to_value(&self) -> Value {
        Value::Object(self.map.clone())
    }

    /// The keys and values, in order.
    pub fn as_map(&self) -> &Map<String, Value> {
        &self.map
    }

    /// The keys and values for editing; a new key goes last, a replaced key keeps its place.
    pub fn as_map_mut(&mut self) -> &mut Map<String, Value> {
        &mut self.map
    }

    /// The keys and values, by value.
    pub fn into_map(self) -> Map<String, Value> {
        self.map
    }

    /// Whether the document has no key.
    pub fn is_empty(&self) -> bool {
        self.map.is_empty()
    }

    /// The value of a key (Python's `cfg.get(key)`; a JSON `null` is `Some(Value::Null)`).
    pub fn get(&self, key: &str) -> Option<&Value> {
        self.map.get(key)
    }

    /// Sets a key, keeping its place when it exists (Python's `cfg[key] = value`).
    pub fn set(&mut self, key: &str, value: Value) {
        self.map.insert(key.to_string(), value);
    }

    /// The value of a key, with JSON `null` read as absent (Python's `cfg.get(key)` tested
    /// with `is None`).
    fn present(&self, key: &str) -> Option<&Value> {
        self.map.get(key).filter(|v| !v.is_null())
    }

    /// The `env` block: `None` when it is absent or false in Python's sense (`null`, `{}`,
    /// `""`, `0`, `false`, `[]`), the object otherwise.
    ///
    /// # Errors
    ///
    /// [`ConfigError::Invalid`] for a true value that is not an object, which the donor
    /// cannot read (`(cfg.get("env") or {}).get(k)` raises an `AttributeError`). The server
    /// stops in both; the console's message differs from the donor's traceback, which is
    /// part of proposal P-23 in the deviation register, awaiting the owner's decision.
    ///
    /// Behavior reference: project-maya serve/server.py:6747-6750 at 7e68a30f.
    pub fn env_block(&self) -> Result<Option<&Map<String, Value>>, ConfigError> {
        match self.map.get("env") {
            None => Ok(None),
            Some(v) if !truthy(v) => Ok(None),
            Some(Value::Object(m)) => Ok(Some(m)),
            Some(_) => Err(ConfigError::Invalid(String::from(
                "\"env\" must be an object of NAME: value pairs",
            ))),
        }
    }

    /// The `env` block as the engine child gets it: every entry once, its name verbatim and
    /// its value as Python's `str()` writes it, in document order. Names are opaque engine
    /// data and are neither renamed nor refused for their prefix (contracts/naming.md rule 3);
    /// the donor's export of each entry under both a `MAYA_` and a `STRATA_` name is not
    /// reproduced (lead decision of 2026-11-14, naming N3).
    ///
    /// # Errors
    ///
    /// As [`RunConfig::env_block`].
    ///
    /// Behavior reference: project-maya tools/maya_names.py:52-58 (`export_env`) at
    /// 7e68a30f.
    pub fn engine_env(&self) -> Result<Vec<(String, String)>, ConfigError> {
        Ok(self
            .env_block()?
            .map(|m| {
                m.iter()
                    .map(|(k, v)| (k.clone(), py::str_value(v)))
                    .collect()
            })
            .unwrap_or_default())
    }

    /// The host to listen on: the command line's when given and not empty, else the config's
    /// `host` when true in Python's sense, else [`DEFAULT_HOST`].
    ///
    /// # Errors
    ///
    /// [`ConfigError::Invalid`] for a config `host` that is true but not a string, which the
    /// donor's socket call refuses with a `TypeError`. The server stops in both; the message
    /// differs, which is part of proposal P-23 in the deviation register, awaiting the owner's decision.
    ///
    /// Behavior reference: project-maya serve/server.py:7166 at 7e68a30f.
    pub fn host(&self, cli: Option<&str>) -> Result<String, ConfigError> {
        if let Some(h) = cli.filter(|h| !h.is_empty()) {
            return Ok(h.to_string());
        }
        match self.map.get("host") {
            Some(v) if truthy(v) => match v {
                Value::String(s) => Ok(s.clone()),
                _ => Err(ConfigError::Invalid(String::from(
                    "\"host\" must be a host name or address",
                ))),
            },
            _ => Ok(String::from(DEFAULT_HOST)),
        }
    }

    /// The API key setting: the command line's key when given and not empty, else the
    /// environment's ([`super::EnvSettings::api_key`]) when not empty, else the config's
    /// `api_key` as it is (a string, or a list for keys that contain a comma), else `""`.
    /// Splitting it into keys is the HTTP guard's (API-03).
    ///
    /// Behavior reference: project-maya serve/server.py:7139-7141 and 7327 at 7e68a30f.
    pub fn api_key(&self, cli: Option<&str>, env_api_key: &str) -> Value {
        let first = cli.unwrap_or(env_api_key);
        if !first.is_empty() {
            return Value::String(first.to_string());
        }
        self.map
            .get("api_key")
            .cloned()
            .unwrap_or_else(|| Value::String(String::new()))
    }

    /// The browser origins allowed to call `/v1/*`: none when `cors_origins` is absent,
    /// `null`, `""` or `[]`; otherwise each origin with surrounding whitespace and trailing
    /// `/` removed.
    ///
    /// # Errors
    ///
    /// [`ConfigError::Invalid`] with [`CORS_ORIGINS_MESSAGE`] for anything but a list of
    /// non-blank strings; start-up stops with `config: ` and that message.
    ///
    /// Behavior reference: project-maya serve/server.py:5393-5400 and 7328-7331 at 7e68a30f.
    pub fn cors_origins(&self) -> Result<Vec<String>, ConfigError> {
        parse_cors_origins(self.map.get("cors_origins"))
    }

    /// The optional `allowed_hosts` key (deviation SEC-1.1, decided by the owner on
    /// 2026-11-14): `None` when absent or `null`, the default, so only loopback names pass on
    /// a loopback bind and `Host` is unrestricted on another bind. A list of non-blank strings
    /// is returned in order, each name with surrounding whitespace removed; an empty list is `Some(vec![])`, which on a
    /// non-loopback bind lets only the loopback names pass. How names are matched (case, port,
    /// IPv6 forms) is the guard's (API-03).
    ///
    /// # Errors
    ///
    /// [`ConfigError::Invalid`] with [`ALLOWED_HOSTS_MESSAGE`] for anything else.
    pub fn allowed_hosts(&self) -> Result<Option<Vec<String>>, ConfigError> {
        match self.present("allowed_hosts") {
            None => Ok(None),
            Some(Value::Array(items)) => {
                let mut out = Vec::with_capacity(items.len());
                for item in items {
                    match item {
                        Value::String(s) if !pystr::strip(s, None).is_empty() => {
                            out.push(pystr::strip(s, None).to_string())
                        }
                        _ => return Err(ConfigError::Invalid(ALLOWED_HOSTS_MESSAGE.to_string())),
                    }
                }
                Ok(Some(out))
            }
            Some(_) => Err(ConfigError::Invalid(ALLOWED_HOSTS_MESSAGE.to_string())),
        }
    }

    /// llama.cpp's model management routes: on unless the environment says otherwise or the
    /// config has `"model_management"` false. A set, non-blank environment value wins: on
    /// for `1`, `on`, `true` or `yes` (any case, trimmed), off for anything else. Without
    /// one, the config's value by Python truthiness, and on when absent or `null`.
    ///
    /// Behavior reference: project-maya serve/server.py:599-609 at 7e68a30f.
    pub fn model_management(&self, env_value: Option<&str>) -> bool {
        const ON: [&str; 4] = ["1", "on", "true", "yes"];
        if let Some(v) = env_value {
            let v = pystr::strip(v, None);
            if !v.is_empty() {
                return ON.contains(&v.to_lowercase().as_str());
            }
        }
        match self.present("model_management") {
            Some(v) => truthy(v),
            None => true,
        }
    }

    /// The loop guard: on unless the environment says `0`, `off`, `false`, `no` or `none`
    /// (any case, trimmed) or the config turns it off. A set, non-blank environment value
    /// wins. The config's value: a string is off for the same words; otherwise off only for
    /// `false` and for numbers equal to zero; absent or `null` is on.
    ///
    /// Behavior reference: project-maya serve/server.py:612-621 at 7e68a30f.
    pub fn loop_guard(&self, env_value: Option<&str>) -> bool {
        const OFF: [&str; 5] = ["0", "off", "false", "no", "none"];
        let off = |s: &str| OFF.contains(&pystr::strip(s, None).to_lowercase().as_str());
        if let Some(v) = env_value {
            if !pystr::strip(v, None).is_empty() {
                return !off(v);
            }
        }
        match self.present("loop_guard") {
            None => true,
            Some(Value::String(s)) => !off(s),
            Some(Value::Bool(false)) => false,
            Some(v) => !py::equals_zero(v),
        }
    }

    /// Whether `max_tokens` is clamped to the room left instead of refused: the command-line
    /// flag, or `"fit_max_tokens": true` exactly.
    ///
    /// Behavior reference: project-maya serve/server.py:7294 at 7e68a30f.
    pub fn fit_max_tokens(&self, cli: bool) -> bool {
        cli || matches!(self.map.get("fit_max_tokens"), Some(Value::Bool(true)))
    }

    /// Seconds without a request before the model unloads (0: never): the command line's when
    /// given, else `float()` of the config's `idle_unload_s` (false values read as 0), never
    /// below 0.
    ///
    /// # Errors
    ///
    /// [`ConfigError::Invalid`] with Python's `float()` message for a value it cannot read.
    ///
    /// Behavior reference: project-maya serve/server.py:7313 at 7e68a30f.
    pub fn idle_unload_s(&self, cli: Option<f64>) -> Result<f64, ConfigError> {
        let seconds = match cli {
            Some(s) => s,
            None => match self.map.get("idle_unload_s") {
                Some(v) if truthy(v) => py_float_of(v)?,
                _ => 0.0,
            },
        };
        Ok(py::py_max(0.0, seconds))
    }

    /// Where the server's own lines are copied: the environment's value when set, else
    /// Python's `str()` of the config's `log` (false values read as `""`); empty, `0`, `off`,
    /// `no`, `false` or `none` (any case, trimmed) keep them on the terminal only.
    ///
    /// Behavior reference: project-maya serve/server.py:7157-7163 at 7e68a30f.
    pub fn server_log(&self, env_value: Option<&str>) -> ServerLog {
        const OFF: [&str; 6] = ["", "0", "off", "no", "false", "none"];
        let target = match env_value {
            Some(v) => v.to_string(),
            None => match self.map.get("log") {
                Some(v) if truthy(v) => py::str_value(v),
                _ => String::new(),
            },
        };
        if OFF.contains(&pystr::strip(&target, None).to_lowercase().as_str()) {
            ServerLog::Terminal
        } else {
            ServerLog::File(target)
        }
    }
}

/// Where the server's own log lines go.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ServerLog {
    /// The terminal only.
    Terminal,
    /// The terminal and this file, as named.
    File(String),
}

/// Python's `float(value)` for a decoded JSON value: numbers and booleans as numbers, strings
/// through `float()`, anything else a `TypeError`.
fn py_float_of(v: &Value) -> Result<f64, ConfigError> {
    match v {
        Value::Bool(b) => Ok(if *b { 1.0 } else { 0.0 }),
        Value::Number(n) => py::number_as_f64(n)
            .ok_or_else(|| ConfigError::Invalid(format!("could not read the number {n}"))),
        Value::String(s) => py::py_float(s).ok_or_else(|| ConfigError::Invalid(py::float_error(s))),
        Value::Null => Err(ConfigError::Invalid(String::from(
            "float() argument must be a string or a real number, not 'NoneType'",
        ))),
        Value::Array(_) => Err(ConfigError::Invalid(String::from(
            "float() argument must be a string or a real number, not 'list'",
        ))),
        Value::Object(_) => Err(ConfigError::Invalid(String::from(
            "float() argument must be a string or a real number, not 'dict'",
        ))),
    }
}

/// The donor's `parse_cors_origins` on a raw value (`None` is an absent key).
///
/// # Errors
///
/// [`ConfigError::Invalid`] with [`CORS_ORIGINS_MESSAGE`].
///
/// Behavior reference: project-maya serve/server.py:5393-5400 at 7e68a30f.
pub fn parse_cors_origins(value: Option<&Value>) -> Result<Vec<String>, ConfigError> {
    let items = match value {
        None | Some(Value::Null) => return Ok(Vec::new()),
        Some(Value::String(s)) if s.is_empty() => return Ok(Vec::new()),
        Some(Value::Array(items)) => items,
        Some(_) => return Err(ConfigError::Invalid(CORS_ORIGINS_MESSAGE.to_string())),
    };
    let mut out = Vec::with_capacity(items.len());
    for item in items {
        match item {
            Value::String(s) if !pystr::strip(s, None).is_empty() => {
                out.push(pystr::rstrip(pystr::strip(s, None), Some("/")).to_string());
            }
            _ => return Err(ConfigError::Invalid(CORS_ORIGINS_MESSAGE.to_string())),
        }
    }
    Ok(out)
}

/// A run config's environment as the Models page gets it: every value as Python's `str()`
/// writes it, with [`MASK`] in place of a non-empty value whose name contains `key`,
/// `token`, `secret` or `password` (any case). Keys keep their order. A missing or false
/// `env` gives an empty object.
///
/// Behavior reference: project-maya serve/models.py:662-666 at 7e68a30f.
pub fn shown_env(env: Option<&Map<String, Value>>) -> Map<String, Value> {
    let mut out = Map::new();
    for (k, v) in env.into_iter().flatten() {
        let text = py::str_value(v);
        let shown = if py::is_secret_name(k) && !text.is_empty() {
            String::from(MASK)
        } else {
            text
        };
        out.insert(k.clone(), Value::String(shown));
    }
    out
}

/// The value to store for an environment entry sent back from the Models page: the stored
/// value when the page sent [`MASK`] for a secret name the config already has, else what
/// was sent.
///
/// Behavior reference: project-maya serve/models.py:480-481 at 7e68a30f.
pub fn kept_secret(stored: Option<&Map<String, Value>>, name: &str, sent: &Value) -> Value {
    if py::str_value(sent) == MASK && py::is_secret_name(name) {
        if let Some(old) = stored.and_then(|m| m.get(name)) {
            return old.clone();
        }
    }
    sent.clone()
}

/// Whether `new` changes the engine's command or environment compared with `old` (any of
/// [`ENGINE_KEYS`] differs by Python equality, an absent key being `None`).
///
/// Behavior reference: project-maya serve/models.py:829-830 at 7e68a30f.
pub fn engine_changed(old: &RunConfig, new: &RunConfig) -> bool {
    ENGINE_KEYS.iter().any(|k| match (old.get(k), new.get(k)) {
        (None, None) => false,
        (Some(a), Some(b)) => !py::py_eq(a, b),
        (Some(a), None) | (None, Some(a)) => !a.is_null(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use console_pyjson::loads::loads;

    fn cfg(text: &str) -> RunConfig {
        match loads(text) {
            Ok(Value::Object(m)) => RunConfig::from(m),
            _ => RunConfig::new(),
        }
    }

    #[test]
    fn host_falls_back_in_order() {
        let c = cfg("{\"port\": 1}");
        assert_eq!(c.host(None).ok().as_deref(), Some(DEFAULT_HOST));
        assert_eq!(c.host(Some("")).ok().as_deref(), Some(DEFAULT_HOST));
        assert_eq!(c.host(Some("0.0.0.0")).ok().as_deref(), Some("0.0.0.0"));
        let mut c = RunConfig::new();
        c.set("host", Value::String(String::from("::1")));
        assert_eq!(c.host(None).ok().as_deref(), Some("::1"));
        assert_eq!(c.host(Some("10.0.0.2")).ok().as_deref(), Some("10.0.0.2"));
        c.set("host", Value::String(String::new()));
        assert_eq!(c.host(None).ok().as_deref(), Some(DEFAULT_HOST));
        c.set("host", Value::from(5));
        assert!(matches!(c.host(None), Err(ConfigError::Invalid(_))));
    }

    #[test]
    fn api_key_command_line_then_environment_then_config() {
        let mut c = RunConfig::new();
        assert_eq!(c.api_key(None, ""), Value::String(String::new()));
        c.set("api_key", Value::String(String::from("cfgk")));
        assert_eq!(c.api_key(None, ""), Value::String(String::from("cfgk")));
        assert_eq!(c.api_key(None, "envk"), Value::String(String::from("envk")));
        assert_eq!(
            c.api_key(Some("clik"), "envk"),
            Value::String(String::from("clik"))
        );
        // An explicit empty --api-key falls through to the config, as `a.api_key or ...`.
        assert_eq!(
            c.api_key(Some(""), "envk"),
            Value::String(String::from("cfgk"))
        );
        let listed = cfg("{\"api_key\": [\"a,b\"]}");
        assert_eq!(
            listed.api_key(None, ""),
            loads("[\"a,b\"]").unwrap_or(Value::Null)
        );
    }

    #[test]
    fn allowed_hosts_absent_by_default() {
        assert_eq!(RunConfig::new().allowed_hosts().ok(), Some(None));
        assert_eq!(
            cfg("{\"allowed_hosts\": null}").allowed_hosts().ok(),
            Some(None)
        );
        assert_eq!(
            cfg("{\"allowed_hosts\": []}").allowed_hosts().ok(),
            Some(Some(Vec::new()))
        );
        assert_eq!(
            cfg("{\"allowed_hosts\": [\"pulsar.local\", \"Box.LAN:8095\"]}")
                .allowed_hosts()
                .ok(),
            Some(Some(vec![
                String::from("pulsar.local"),
                String::from("Box.LAN:8095")
            ]))
        );
        assert_eq!(
            cfg("{\"allowed_hosts\": [\" box.lan \", \"\\tpulsar.local\\n\"]}")
                .allowed_hosts()
                .ok(),
            Some(Some(vec![
                String::from("box.lan"),
                String::from("pulsar.local")
            ]))
        );
        for bad in [
            "{\"allowed_hosts\": \"pulsar.local\"}",
            "{\"allowed_hosts\": [\"\"]}",
            "{\"allowed_hosts\": [\"  \"]}",
            "{\"allowed_hosts\": [1]}",
            "{\"allowed_hosts\": {\"a\": 1}}",
            "{\"allowed_hosts\": false}",
        ] {
            match cfg(bad).allowed_hosts() {
                Err(ConfigError::Invalid(m)) => assert_eq!(m, ALLOWED_HOSTS_MESSAGE, "{bad}"),
                other => panic!("{bad}: {other:?}"),
            }
        }
    }

    #[test]
    fn loop_guard_environment_then_config() {
        let none = RunConfig::new();
        assert!(none.loop_guard(None));
        assert!(none.loop_guard(Some("  ")));
        for off in ["0", "off", " FALSE ", "No", "none"] {
            assert!(!none.loop_guard(Some(off)), "{off}");
        }
        assert!(none.loop_guard(Some("1")));
        assert!(none.loop_guard(Some("maybe")));
        assert!(!cfg("{\"loop_guard\": false}").loop_guard(None));
        assert!(!cfg("{\"loop_guard\": 0}").loop_guard(None));
        assert!(!cfg("{\"loop_guard\": 0.0}").loop_guard(None));
        assert!(!cfg("{\"loop_guard\": \" Off \"}").loop_guard(None));
        assert!(cfg("{\"loop_guard\": \"\"}").loop_guard(None));
        assert!(cfg("{\"loop_guard\": null}").loop_guard(None));
        assert!(cfg("{\"loop_guard\": true}").loop_guard(None));
        assert!(cfg("{\"loop_guard\": []}").loop_guard(None));
        assert!(cfg("{\"loop_guard\": false}").loop_guard(Some("on")));
    }

    #[test]
    fn idle_unload_and_fit_max_tokens() {
        assert_eq!(RunConfig::new().idle_unload_s(None).ok(), Some(0.0));
        assert_eq!(
            cfg("{\"idle_unload_s\": 30}").idle_unload_s(None).ok(),
            Some(30.0)
        );
        assert_eq!(
            cfg("{\"idle_unload_s\": \" 2.5 \"}")
                .idle_unload_s(None)
                .ok(),
            Some(2.5)
        );
        assert_eq!(
            cfg("{\"idle_unload_s\": -4}").idle_unload_s(None).ok(),
            Some(0.0)
        );
        assert_eq!(
            cfg("{\"idle_unload_s\": 30}").idle_unload_s(Some(5.0)).ok(),
            Some(5.0)
        );
        assert_eq!(
            cfg("{\"idle_unload_s\": null}").idle_unload_s(None).ok(),
            Some(0.0)
        );
        match cfg("{\"idle_unload_s\": \"soon\"}").idle_unload_s(None) {
            Err(ConfigError::Invalid(m)) => {
                assert_eq!(m, "could not convert string to float: 'soon'")
            }
            other => panic!("{other:?}"),
        }
        assert!(cfg("{\"idle_unload_s\": [1]}").idle_unload_s(None).is_err());
        assert!(!RunConfig::new().fit_max_tokens(false));
        assert!(RunConfig::new().fit_max_tokens(true));
        assert!(cfg("{\"fit_max_tokens\": true}").fit_max_tokens(false));
        assert!(!cfg("{\"fit_max_tokens\": 1}").fit_max_tokens(false));
        assert!(!cfg("{\"fit_max_tokens\": \"true\"}").fit_max_tokens(false));
    }

    #[test]
    fn server_log_environment_then_config() {
        let none = RunConfig::new();
        assert_eq!(none.server_log(None), ServerLog::Terminal);
        let logged = cfg("{\"log\": \"run.txt\"}");
        assert_eq!(
            logged.server_log(None),
            ServerLog::File(String::from("run.txt"))
        );
        assert_eq!(logged.server_log(Some("0")), ServerLog::Terminal);
        assert_eq!(logged.server_log(Some(" OFF ")), ServerLog::Terminal);
        assert_eq!(logged.server_log(Some("")), ServerLog::Terminal);
        assert_eq!(
            none.server_log(Some("other.txt")),
            ServerLog::File(String::from("other.txt"))
        );
        assert_eq!(
            cfg("{\"log\": 7}").server_log(None),
            ServerLog::File(String::from("7"))
        );
        assert_eq!(
            cfg("{\"log\": false}").server_log(None),
            ServerLog::Terminal
        );
    }

    #[test]
    fn env_block_and_engine_env() {
        assert!(matches!(RunConfig::new().env_block(), Ok(None)));
        assert!(matches!(cfg("{\"env\": \"\"}").env_block(), Ok(None)));
        assert!(matches!(cfg("{\"env\": []}").env_block(), Ok(None)));
        assert!(cfg("{\"env\": [1]}").env_block().is_err());
        assert!(cfg("{\"env\": \"A=1\"}").env_block().is_err());
        let c = cfg("{\"env\": {\"MAYA_GLM_SLOT_KEEP\": 1, \"STRATA_X\": \"y\", \"B\": 1.0, \"C\": true, \"D\": null}}");
        assert_eq!(
            c.engine_env().ok(),
            Some(vec![
                (String::from("MAYA_GLM_SLOT_KEEP"), String::from("1")),
                (String::from("STRATA_X"), String::from("y")),
                (String::from("B"), String::from("1.0")),
                (String::from("C"), String::from("True")),
                (String::from("D"), String::from("None")),
            ])
        );
    }

    #[test]
    fn debug_masks_the_api_key_and_env_secrets() {
        let c = cfg(
            "{\"api_key\": \"cfgsecret1\", \"env\": {\"HF_TOKEN\": \"hfsecret2\", \"N\": 4}, \"port\": 9}",
        );
        let shown = format!("{c:?}");
        assert!(!shown.contains("cfgsecret1"), "{shown}");
        assert!(!shown.contains("hfsecret2"), "{shown}");
        assert!(shown.contains("***") && shown.contains("port"), "{shown}");
        let listed = cfg("{\"api_key\": [\"k1sec,k2sec\"], \"env\": \"RAWsecret\"}");
        let shown = format!("{listed:?}");
        assert!(
            !shown.contains("k1sec") && !shown.contains("RAWsecret"),
            "{shown}"
        );
        assert!(format!("{:?}", cfg("{\"api_key\": \"\"}")).contains("\"\""));
    }

    #[test]
    fn engine_change_is_by_python_equality() {
        let a = cfg("{\"args\": [\"--x\"], \"gpu\": 1, \"port\": 1}");
        let b = cfg("{\"args\": [\"--x\"], \"gpu\": 1.0, \"port\": 2}");
        assert!(!engine_changed(&a, &b));
        let c = cfg("{\"args\": [\"--y\"], \"gpu\": 1}");
        assert!(engine_changed(&a, &c));
        let d = cfg("{\"args\": [\"--x\"], \"gpu\": 1, \"vision_off\": null}");
        assert!(!engine_changed(&a, &d));
        let e = cfg("{\"args\": [\"--x\"], \"gpu\": 1, \"env\": {}}");
        assert!(engine_changed(&a, &e));
    }

    #[test]
    fn masks_and_kept_secrets() {
        let c =
            cfg("{\"env\": {\"HF_TOKEN\": \"hf_s\", \"A_KEY\": \"\", \"N\": 4, \"PASSWORD\": 0}}");
        let shown = shown_env(c.env_block().ok().flatten());
        assert_eq!(
            Value::Object(shown),
            loads("{\"HF_TOKEN\": \"***\", \"A_KEY\": \"\", \"N\": \"4\", \"PASSWORD\": \"***\"}")
                .unwrap_or(Value::Null)
        );
        let stored = c.env_block().ok().flatten();
        let mask = Value::String(String::from(MASK));
        assert_eq!(
            kept_secret(stored, "HF_TOKEN", &mask),
            Value::String(String::from("hf_s"))
        );
        assert_eq!(kept_secret(stored, "N", &mask), mask);
        assert_eq!(kept_secret(stored, "NEW_TOKEN", &mask), mask);
        assert_eq!(
            kept_secret(stored, "HF_TOKEN", &Value::String(String::from("hf_n"))),
            Value::String(String::from("hf_n"))
        );
    }
}
