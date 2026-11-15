//! The server's environment settings: one name table, one parser per variable with the
//! donor's default, minimum and parsing rule, and the run-config `env` entries the server
//! reads itself.
//!
//! Names use the prefix `PULSAR_CONSOLE_`; the donor's `MAYA_*` names and their `STRATA_*`
//! fallbacks are not read (decision B2, deviation BRAND-1, contracts/naming.md rules 2 and
//! 9). Everything here reads an injected [`EnvSource`]; only the binary passes the real
//! process environment ([`ProcessEnv`]).
//!
//! Behavior reference: project-maya serve/server.py:395-409 (queue ping, fair slice),
//! 599-621 (model management, loop guard), 725-791 (stall, quiet, drain, restore points),
//! 1703-1705 (engine quit), 1926 (video frames), 2089-2093 (prompt memo, turn trace),
//! 2771 and 7290 (mock engine), 4402 (think reserve), 4747 (debug), 5347-5372 (backlog,
//! request timeout, body limit), 6737-6755 (`SERVER_ENV`, `apply_server_env`), 6858-6867
//! (pack template), 7139 (API key), 7157-7163 (server log), 7174-7177 (prompt memo and turn
//! trace from the config), 7428 (engine wrap); serve/frontend.py:284-287 (keep thinking);
//! serve/loop_guard.py:563-596 (collapse limit); serve/savings.py:24-33 (savings path);
//! serve/update.py:74-75 (update check); serve/response_config.py:4-14 (Responses limits);
//! docs/SETTINGS.md:206-217; tools/maya_names.py:1-78 (the names it maps; its aliasing is not
//! ported) at 7e68a30f.

use std::collections::{BTreeMap, HashMap};
use std::fmt;
use std::path::{Path, PathBuf};
use std::time::Duration;

use console_pyjson::pystr;
use serde_json::Value;

use super::document::{masked_value, ConfigError, RunConfig, ServerLog};
use super::py;

/// The prefix of every environment variable PulsarMLX Console reads (decision B2).
pub const ENV_PREFIX: &str = "PULSAR_CONSOLE_";

/// One server setting: its PulsarMLX Console name and the donor name it replaces.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct SettingName {
    /// The environment variable PulsarMLX Console reads.
    pub name: &'static str,
    /// The donor's variable (contracts/naming.md section 3.1, first column). It is never read.
    pub donor: &'static str,
}

const fn setting(name: &'static str, donor: &'static str) -> SettingName {
    SettingName { name, donor }
}

/// `PULSAR_CONSOLE_API_KEY`: the API key(s) `/v1/*` requires.
pub const API_KEY: &str = "PULSAR_CONSOLE_API_KEY";
/// `PULSAR_CONSOLE_DEBUG`: diagnostic lines when not empty.
pub const DEBUG: &str = "PULSAR_CONSOLE_DEBUG";
/// `PULSAR_CONSOLE_DRAIN_S`: the longest a stopped request's lines are waited for.
pub const DRAIN_S: &str = "PULSAR_CONSOLE_DRAIN_S";
/// `PULSAR_CONSOLE_DS4_KEEP_THINKING`: earlier reasoning kept in DeepSeek prompts.
pub const DS4_KEEP_THINKING: &str = "PULSAR_CONSOLE_DS4_KEEP_THINKING";
/// `PULSAR_CONSOLE_DS4_RESTORE_POINTS`: DeepSeek restore points (0: none).
pub const DS4_RESTORE_POINTS: &str = "PULSAR_CONSOLE_DS4_RESTORE_POINTS";
/// `PULSAR_CONSOLE_DS4_RESTORE_TAIL`: how far before the prompt's end the tail point sits.
pub const DS4_RESTORE_TAIL: &str = "PULSAR_CONSOLE_DS4_RESTORE_TAIL";
/// `PULSAR_CONSOLE_ENGINE_QUIT_S`: how long the engine gets to end after a stop.
pub const ENGINE_QUIT_S: &str = "PULSAR_CONSOLE_ENGINE_QUIT_S";
/// `PULSAR_CONSOLE_ENGINE_STALL_S`: silence and idleness that count as a stuck engine.
pub const ENGINE_STALL_S: &str = "PULSAR_CONSOLE_ENGINE_STALL_S";
/// `PULSAR_CONSOLE_ENGINE_WRAP_S`: how long a request in progress may answer on a stop.
pub const ENGINE_WRAP_S: &str = "PULSAR_CONSOLE_ENGINE_WRAP_S";
/// `PULSAR_CONSOLE_FAIR_SLICE_S`: how long an answer keeps the engine while others wait.
pub const FAIR_SLICE_S: &str = "PULSAR_CONSOLE_FAIR_SLICE_S";
/// `PULSAR_CONSOLE_GLM_THINK_RESERVE`: the answer's token reserve under a tiny limit.
pub const GLM_THINK_RESERVE: &str = "PULSAR_CONSOLE_GLM_THINK_RESERVE";
/// `PULSAR_CONSOLE_HTTP_BACKLOG`: connections that may wait to be accepted.
pub const HTTP_BACKLOG: &str = "PULSAR_CONSOLE_HTTP_BACKLOG";
/// `PULSAR_CONSOLE_LOOP_GUARD`: the loop guard switch (environment over config).
pub const LOOP_GUARD: &str = "PULSAR_CONSOLE_LOOP_GUARD";
/// `PULSAR_CONSOLE_LOOP_GUARD_COLLAPSE_MAX`: the most conversation the guard may rewrite.
pub const LOOP_GUARD_COLLAPSE_MAX: &str = "PULSAR_CONSOLE_LOOP_GUARD_COLLAPSE_MAX";
/// `PULSAR_CONSOLE_MAX_BODY_MIB`: the largest request body, in MiB.
pub const MAX_BODY_MIB: &str = "PULSAR_CONSOLE_MAX_BODY_MIB";
/// `PULSAR_CONSOLE_MOCK_RELOAD_S`: the scripted engine's reload time.
pub const MOCK_RELOAD_S: &str = "PULSAR_CONSOLE_MOCK_RELOAD_S";
/// `PULSAR_CONSOLE_MOCK_TOK_S`: the scripted engine's tokens per second.
pub const MOCK_TOK_S: &str = "PULSAR_CONSOLE_MOCK_TOK_S";
/// `PULSAR_CONSOLE_MODEL_MANAGEMENT`: llama.cpp's model routes (environment over config).
pub const MODEL_MANAGEMENT: &str = "PULSAR_CONSOLE_MODEL_MANAGEMENT";
/// `PULSAR_CONSOLE_PACK_TEMPLATE`: `1` keeps a pack's own chat template.
pub const PACK_TEMPLATE: &str = "PULSAR_CONSOLE_PACK_TEMPLATE";
/// `PULSAR_CONSOLE_PROMPT_MEMO`: prompt preparation remembered by text (`0`: off).
pub const PROMPT_MEMO: &str = "PULSAR_CONSOLE_PROMPT_MEMO";
/// `PULSAR_CONSOLE_QUEUE_PING_S`: keep-alive interval of a request waiting for its turn.
pub const QUEUE_PING_S: &str = "PULSAR_CONSOLE_QUEUE_PING_S";
/// `PULSAR_CONSOLE_REQUEST_QUIET_S`: silence after which a request counts as lost.
pub const REQUEST_QUIET_S: &str = "PULSAR_CONSOLE_REQUEST_QUIET_S";
/// `PULSAR_CONSOLE_REQUEST_TIMEOUT_S`: seconds one socket read or write may wait.
pub const REQUEST_TIMEOUT_S: &str = "PULSAR_CONSOLE_REQUEST_TIMEOUT_S";
/// `PULSAR_CONSOLE_RESTART_ON_UPDATE`: a supervisor restarts the server when not empty.
pub const RESTART_ON_UPDATE: &str = "PULSAR_CONSOLE_RESTART_ON_UPDATE";
/// `PULSAR_CONSOLE_SAVINGS_PATH`: where the token-savings count is kept.
pub const SAVINGS_PATH: &str = "PULSAR_CONSOLE_SAVINGS_PATH";
/// `PULSAR_CONSOLE_SERVER_LOG`: where the server's own lines are copied.
pub const SERVER_LOG: &str = "PULSAR_CONSOLE_SERVER_LOG";
/// `PULSAR_CONSOLE_TURN_TRACE`: per-turn timing lines.
pub const TURN_TRACE: &str = "PULSAR_CONSOLE_TURN_TRACE";
/// `PULSAR_CONSOLE_UPDATE_CHECK`: the release check (opt-in, deviation SEC-5.3).
pub const UPDATE_CHECK: &str = "PULSAR_CONSOLE_UPDATE_CHECK";
/// `PULSAR_CONSOLE_VIDEO_MAX_FRAMES`: the most frames a video may give.
pub const VIDEO_MAX_FRAMES: &str = "PULSAR_CONSOLE_VIDEO_MAX_FRAMES";

/// Every server setting [`EnvSettings`] reads, with the donor name it replaces, in the order
/// of contracts/naming.md section 3.1. `MAYA_PULL_COMMAND` has no entry: it is removed
/// (deviation SEC-7.1). The Responses limits are in [`RESPONSES_LIMITS`].
pub const SERVER_SETTINGS: &[SettingName] = &[
    setting(API_KEY, "MAYA_API_KEY"),
    setting(DEBUG, "MAYA_DEBUG"),
    setting(DRAIN_S, "MAYA_DRAIN_S"),
    setting(DS4_KEEP_THINKING, "MAYA_DS4_KEEP_THINKING"),
    setting(DS4_RESTORE_POINTS, "MAYA_DS4_RESTORE_POINTS"),
    setting(DS4_RESTORE_TAIL, "MAYA_DS4_RESTORE_TAIL"),
    setting(ENGINE_QUIT_S, "MAYA_ENGINE_QUIT_S"),
    setting(ENGINE_STALL_S, "MAYA_ENGINE_STALL_S"),
    setting(ENGINE_WRAP_S, "MAYA_ENGINE_WRAP_S"),
    setting(FAIR_SLICE_S, "MAYA_FAIR_SLICE_S"),
    setting(GLM_THINK_RESERVE, "MAYA_GLM_THINK_RESERVE"),
    setting(HTTP_BACKLOG, "MAYA_HTTP_BACKLOG"),
    setting(LOOP_GUARD, "MAYA_LOOP_GUARD"),
    setting(LOOP_GUARD_COLLAPSE_MAX, "MAYA_LOOP_GUARD_COLLAPSE_MAX"),
    setting(MAX_BODY_MIB, "MAYA_MAX_BODY_MIB"),
    setting(MOCK_RELOAD_S, "MAYA_MOCK_RELOAD_S"),
    setting(MOCK_TOK_S, "MAYA_MOCK_TOK_S"),
    setting(MODEL_MANAGEMENT, "MAYA_MODEL_MANAGEMENT"),
    setting(PACK_TEMPLATE, "MAYA_PACK_TEMPLATE"),
    setting(PROMPT_MEMO, "MAYA_PROMPT_MEMO"),
    setting(QUEUE_PING_S, "MAYA_QUEUE_PING_S"),
    setting(REQUEST_QUIET_S, "MAYA_REQUEST_QUIET_S"),
    setting(REQUEST_TIMEOUT_S, "MAYA_REQUEST_TIMEOUT_S"),
    setting(RESTART_ON_UPDATE, "MAYA_RESTART_ON_UPDATE"),
    setting(SAVINGS_PATH, "MAYA_SAVINGS_PATH"),
    setting(SERVER_LOG, "MAYA_SERVER_LOG"),
    setting(TURN_TRACE, "MAYA_TURN_TRACE"),
    setting(UPDATE_CHECK, "MAYA_UPDATE_CHECK"),
    setting(VIDEO_MAX_FRAMES, "MAYA_VIDEO_MAX_FRAMES"),
];

/// The prefix of the Responses limits under rule 9 of contracts/naming.md
/// (`MAYA_GLM_RESPONSES_` renamed). Whether `GLM_` stays is open item N2 (OPEN-31), owned by
/// RSP-01.
pub const RESPONSES_PREFIX: &str = "PULSAR_CONSOLE_GLM_RESPONSES_";

/// One Responses limit: its environment name, the donor's name and the donor's default.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ResponsesLimit {
    /// The key after the prefix, such as `CACHE_ENTRIES`.
    pub key: &'static str,
    /// The environment variable PulsarMLX Console reads.
    pub name: &'static str,
    /// The donor's variable. It is never read.
    pub donor: &'static str,
    /// The donor's default.
    pub default: u64,
}

const fn limit(
    key: &'static str,
    name: &'static str,
    donor: &'static str,
    default: u64,
) -> ResponsesLimit {
    ResponsesLimit {
        key,
        name,
        donor,
        default,
    }
}

const MIB: u64 = 1024 * 1024;

/// The Responses store, job and event limits, in the donor's order, with its defaults. Their
/// validation (`limits_from_env`) belongs to the Responses packages (RSP-01); this table only
/// names them, reads their raw text and lists them among the `env` entries the server reads
/// itself.
///
/// Behavior reference: project-maya serve/response_config.py:4-14 at 7e68a30f.
pub const RESPONSES_LIMITS: &[ResponsesLimit] = &[
    limit(
        "CACHE_ENTRIES",
        "PULSAR_CONSOLE_GLM_RESPONSES_CACHE_ENTRIES",
        "MAYA_GLM_RESPONSES_CACHE_ENTRIES",
        128,
    ),
    limit(
        "CACHE_BYTES",
        "PULSAR_CONSOLE_GLM_RESPONSES_CACHE_BYTES",
        "MAYA_GLM_RESPONSES_CACHE_BYTES",
        64 * MIB,
    ),
    limit(
        "CACHE_TTL_S",
        "PULSAR_CONSOLE_GLM_RESPONSES_CACHE_TTL_S",
        "MAYA_GLM_RESPONSES_CACHE_TTL_S",
        3600,
    ),
    limit(
        "ENTRY_BYTES",
        "PULSAR_CONSOLE_GLM_RESPONSES_ENTRY_BYTES",
        "MAYA_GLM_RESPONSES_ENTRY_BYTES",
        64 * MIB,
    ),
    limit(
        "OWNER_ENTRIES",
        "PULSAR_CONSOLE_GLM_RESPONSES_OWNER_ENTRIES",
        "MAYA_GLM_RESPONSES_OWNER_ENTRIES",
        0,
    ),
    limit(
        "OWNER_BYTES",
        "PULSAR_CONSOLE_GLM_RESPONSES_OWNER_BYTES",
        "MAYA_GLM_RESPONSES_OWNER_BYTES",
        0,
    ),
    limit(
        "ASSEMBLY_BYTES",
        "PULSAR_CONSOLE_GLM_RESPONSES_ASSEMBLY_BYTES",
        "MAYA_GLM_RESPONSES_ASSEMBLY_BYTES",
        64 * MIB,
    ),
    limit(
        "JOB_WORKERS",
        "PULSAR_CONSOLE_GLM_RESPONSES_JOB_WORKERS",
        "MAYA_GLM_RESPONSES_JOB_WORKERS",
        2,
    ),
    limit(
        "JOB_ENTRIES",
        "PULSAR_CONSOLE_GLM_RESPONSES_JOB_ENTRIES",
        "MAYA_GLM_RESPONSES_JOB_ENTRIES",
        16,
    ),
    limit(
        "JOB_OWNER_ENTRIES",
        "PULSAR_CONSOLE_GLM_RESPONSES_JOB_OWNER_ENTRIES",
        "MAYA_GLM_RESPONSES_JOB_OWNER_ENTRIES",
        4,
    ),
    limit(
        "JOB_TIMEOUT_S",
        "PULSAR_CONSOLE_GLM_RESPONSES_JOB_TIMEOUT_S",
        "MAYA_GLM_RESPONSES_JOB_TIMEOUT_S",
        300,
    ),
    limit(
        "JOB_TTL_S",
        "PULSAR_CONSOLE_GLM_RESPONSES_JOB_TTL_S",
        "MAYA_GLM_RESPONSES_JOB_TTL_S",
        900,
    ),
    limit(
        "JOB_INPUT_BYTES",
        "PULSAR_CONSOLE_GLM_RESPONSES_JOB_INPUT_BYTES",
        "MAYA_GLM_RESPONSES_JOB_INPUT_BYTES",
        2 * MIB,
    ),
    limit(
        "EVENT_BYTES",
        "PULSAR_CONSOLE_GLM_RESPONSES_EVENT_BYTES",
        "MAYA_GLM_RESPONSES_EVENT_BYTES",
        2 * MIB,
    ),
    limit(
        "EVENT_COUNT",
        "PULSAR_CONSOLE_GLM_RESPONSES_EVENT_COUNT",
        "MAYA_GLM_RESPONSES_EVENT_COUNT",
        4096,
    ),
    limit(
        "STREAM_READERS",
        "PULSAR_CONSOLE_GLM_RESPONSES_STREAM_READERS",
        "MAYA_GLM_RESPONSES_STREAM_READERS",
        32,
    ),
    limit(
        "STREAM_OWNER_READERS",
        "PULSAR_CONSOLE_GLM_RESPONSES_STREAM_OWNER_READERS",
        "MAYA_GLM_RESPONSES_STREAM_OWNER_READERS",
        8,
    ),
    limit(
        "STREAM_TIMEOUT_S",
        "PULSAR_CONSOLE_GLM_RESPONSES_STREAM_TIMEOUT_S",
        "MAYA_GLM_RESPONSES_STREAM_TIMEOUT_S",
        5,
    ),
];

/// The settings a run config's `env` block sets for the server itself, before it starts:
/// the donor's `SERVER_ENV` list under the new names, the Responses limits included. They
/// override the process environment. Other `env` entries go to the engine child verbatim
/// ([`RunConfig::engine_env`]).
///
/// Behavior reference: project-maya serve/server.py:6737-6741 at 7e68a30f.
pub const SERVER_ENV: &[&str] = &[
    ENGINE_STALL_S,
    REQUEST_QUIET_S,
    DRAIN_S,
    HTTP_BACKLOG,
    MAX_BODY_MIB,
    FAIR_SLICE_S,
    DS4_KEEP_THINKING,
    SERVER_LOG,
    GLM_THINK_RESERVE,
    LOOP_GUARD,
    QUEUE_PING_S,
    UPDATE_CHECK,
    PACK_TEMPLATE,
    DS4_RESTORE_POINTS,
    DS4_RESTORE_TAIL,
];

/// The two settings the donor copies from the config's `env` block after start-up, where a
/// JSON `null` is copied as the text `None` (the donor writes `str(value)` without testing
/// for `None`).
///
/// Behavior reference: project-maya serve/server.py:7174-7177 at 7e68a30f.
pub const SERVER_ENV_LATE: &[&str] = &[PROMPT_MEMO, TURN_TRACE];

/// Where the server reads environment variables from.
pub trait EnvSource {
    /// The value of a variable, or `None` when it is not set.
    fn var(&self, name: &str) -> Option<String>;
}

impl EnvSource for BTreeMap<String, String> {
    fn var(&self, name: &str) -> Option<String> {
        self.get(name).cloned()
    }
}

impl EnvSource for HashMap<String, String> {
    fn var(&self, name: &str) -> Option<String> {
        self.get(name).cloned()
    }
}

impl<const N: usize> EnvSource for [(&str, &str); N] {
    fn var(&self, name: &str) -> Option<String> {
        self.iter()
            .rev()
            .find(|(k, _)| *k == name)
            .map(|(_, v)| (*v).to_string())
    }
}

impl<S: EnvSource + ?Sized> EnvSource for &S {
    fn var(&self, name: &str) -> Option<String> {
        (**self).var(name)
    }
}

/// The real process environment. Only the binary uses it; tests inject a map. A value that
/// is not valid Unicode is read with replacement characters.
#[derive(Debug, Clone, Copy, Default)]
pub struct ProcessEnv;

impl EnvSource for ProcessEnv {
    fn var(&self, name: &str) -> Option<String> {
        std::env::var_os(name).map(|v| v.to_string_lossy().into_owned())
    }
}

/// The process environment with a run config's server entries laid over it, as the donor's
/// `apply_server_env` leaves `os.environ`: an entry of [`SERVER_ENV`] or a Responses limit
/// that the config's `env` block sets to a value other than `null` wins, as Python's `str()`
/// of that value; an entry of [`SERVER_ENV_LATE`] the block has wins likewise, `null`
/// included. `Debug` shows the entries taken from the config, not the base environment.
#[derive(Clone)]
pub struct LayeredEnv<S> {
    base: S,
    overrides: BTreeMap<String, String>,
}

impl<S: EnvSource> LayeredEnv<S> {
    /// Lays the config's server entries over `base`.
    ///
    /// # Errors
    ///
    /// As [`RunConfig::env_block`].
    pub fn new(base: S, cfg: &RunConfig) -> Result<Self, ConfigError> {
        Ok(LayeredEnv {
            base,
            overrides: server_env_overrides(cfg)?,
        })
    }

    /// The entries taken from the config, by name.
    pub fn overrides(&self) -> &BTreeMap<String, String> {
        &self.overrides
    }
}

impl<S: EnvSource> EnvSource for LayeredEnv<S> {
    fn var(&self, name: &str) -> Option<String> {
        self.overrides
            .get(name)
            .cloned()
            .or_else(|| self.base.var(name))
    }
}

/// The config `env` entries the server reads itself, by name, as text.
///
/// # Errors
///
/// As [`RunConfig::env_block`].
///
/// Behavior reference: project-maya serve/server.py:6744-6750 and 7174-7176 at 7e68a30f.
pub fn server_env_overrides(cfg: &RunConfig) -> Result<BTreeMap<String, String>, ConfigError> {
    let mut out = BTreeMap::new();
    let Some(block) = cfg.env_block()? else {
        return Ok(out);
    };
    let early = SERVER_ENV
        .iter()
        .copied()
        .chain(RESPONSES_LIMITS.iter().map(|l| l.name));
    for name in early {
        match block.get(name) {
            None | Some(Value::Null) => {}
            Some(v) => {
                out.insert(name.to_string(), py::str_value(v));
            }
        }
    }
    for name in SERVER_ENV_LATE {
        if let Some(v) = block.get(*name) {
            out.insert((*name).to_string(), py::str_value(v));
        }
    }
    Ok(out)
}

/// A setting whose text the donor reads only when it is used, and whose bad value raises
/// there (an uncaught `ValueError`). The value is kept with the error so the package that
/// uses the setting can fail where the donor fails.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct InvalidSetting {
    /// The variable.
    pub name: &'static str,
    /// Python's `ValueError` message, such as `could not convert string to float: 'x'`.
    pub message: String,
}

impl fmt::Display for InvalidSetting {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}: {}", self.name, self.message)
    }
}

impl std::error::Error for InvalidSetting {}

/// Where the token-savings count is kept.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SavingsPath {
    /// Beside the run config, as `token-savings.json` (the variable unset or blank).
    BesideConfig,
    /// No file: the count lives until the server stops (`off`, `none` or `0`, any case).
    Off,
    /// This file, as given with surrounding whitespace removed.
    File(String),
}

/// The file name of the savings count beside the run config.
pub const SAVINGS_FILE: &str = "token-savings.json";

impl SavingsPath {
    /// The file the count is kept in, or `None` for [`SavingsPath::Off`]: the file named by
    /// the variable (a leading `~` or `~/` stands for `home` when given), or
    /// [`SAVINGS_FILE`] in the directory of the run config.
    ///
    /// The expansion is narrower than the donor's `Path.expanduser()`: `~name/...` (another
    /// user's home) is not expanded and stays a relative path, and without `home` nothing is
    /// expanded (the donor falls back to the password database). This difference is
    /// part of proposal P-23 in the deviation register, awaiting the owner's decision.
    ///
    /// Behavior reference: project-maya serve/savings.py:27-33 at 7e68a30f.
    pub fn resolve(&self, config: &Path, home: Option<&Path>) -> Option<PathBuf> {
        match self {
            SavingsPath::Off => None,
            SavingsPath::BesideConfig => Some(super::store::config_dir(config).join(SAVINGS_FILE)),
            SavingsPath::File(v) => {
                let expanded = match (home, v.as_str()) {
                    (Some(h), "~") => h.to_path_buf(),
                    (Some(h), s) if s.starts_with("~/") => h.join(s.get(2..).unwrap_or("")),
                    _ => PathBuf::from(v),
                };
                Some(expanded)
            }
        }
    }
}

/// The prompt memo setting (`PULSAR_CONSOLE_PROMPT_MEMO`), with the donor's three readings.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PromptMemo {
    /// Exactly `0`: prompt preparation is not remembered.
    Off,
    /// Any other value, unset and the late-copied text `None` included: remembered.
    On,
    /// Exactly `verify` (case-sensitive, untrimmed): remembered, and every remembered prompt
    /// is checked against a whole preparation; a difference is an error.
    Verify,
}

impl PromptMemo {
    /// Reads the variable's value (`None` when unset).
    ///
    /// Behavior reference: project-maya serve/server.py:2090 and 2556 at 7e68a30f.
    pub fn from_value(value: Option<&str>) -> Self {
        match value {
            Some("0") => PromptMemo::Off,
            Some("verify") => PromptMemo::Verify,
            _ => PromptMemo::On,
        }
    }

    /// Whether prompt preparation is remembered ([`PromptMemo::On`] or
    /// [`PromptMemo::Verify`]).
    pub fn is_on(self) -> bool {
        self != PromptMemo::Off
    }

    /// Whether every remembered prompt is checked against a whole preparation.
    pub fn verifies(self) -> bool {
        self == PromptMemo::Verify
    }
}

/// A duration setting in seconds, ready for a timer.
///
/// Seconds settings are kept as `f64` with the donor's parsing, so they may be `inf` (Python's
/// `float("inf")`, or `Infinity` in a run config) and, for the unclamped settings
/// (`engine_quit_s`, `engine_wrap_s`, `mock_reload_s`, `mock_tok_s`), `nan`. Convert them
/// with [`seconds`], never with `Duration::from_secs_f64`, which panics on both.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Seconds {
    /// A finite wait; a negative value is zero.
    For(Duration),
    /// No bound: `+inf`, or a finite value too large for a [`Duration`].
    Unbounded,
    /// `nan`: no usable time. The package that uses the setting decides how it fails.
    NotANumber,
}

/// Converts a seconds setting into a [`Seconds`] without panicking.
pub fn seconds(x: f64) -> Seconds {
    if x.is_nan() {
        Seconds::NotANumber
    } else if x <= 0.0 {
        Seconds::For(Duration::ZERO)
    } else {
        Duration::try_from_secs_f64(x).map_or(Seconds::Unbounded, Seconds::For)
    }
}

/// Every environment setting the server reads, parsed with the donor's rule.
///
/// Fields typed `Result<_, InvalidSetting>` are the settings whose bad value the donor does
/// not tolerate: it raises at the moment it uses them. The others fall back to their default
/// on a bad value, as the donor does. Settings whose value is combined with a run-config key
/// keep the raw text (`loop_guard`, `model_management`, `server_log`); resolve them with
/// [`RunConfig`] or [`ServerSettings`].
///
/// The seconds fields (`drain_s`, `engine_quit_s`, `engine_stall_s`, `engine_wrap_s`,
/// `fair_slice_s`, `mock_reload_s`, `queue_ping_s`, `request_quiet_s`, `request_timeout_s`)
/// may be infinite, and the unclamped ones may be `nan`, as the donor's `float()` reads
/// them: convert them with [`seconds`].
///
/// `Debug` shows `api_key` as [`super::MASK`] when it is not empty.
#[derive(Clone, PartialEq)]
pub struct EnvSettings {
    /// `PULSAR_CONSOLE_API_KEY`, `""` when unset.
    pub api_key: String,
    /// `PULSAR_CONSOLE_DEBUG`: set and not empty.
    pub debug: bool,
    /// `PULSAR_CONSOLE_DRAIN_S`: `max(1.0, float(v))`, default and fallback 60. May be non-finite
    /// ([`seconds`]).
    pub drain_s: f64,
    /// `PULSAR_CONSOLE_DS4_KEEP_THINKING`: anything but unset, `""` and `0`.
    pub ds4_keep_thinking: bool,
    /// `PULSAR_CONSOLE_DS4_RESTORE_POINTS`: `max(0, int(v))`, default and fallback 4; on
    /// when above 0.
    pub ds4_restore_points: i64,
    /// `PULSAR_CONSOLE_DS4_RESTORE_TAIL`: `max(0, int(v))`, default and fallback 512.
    pub ds4_restore_tail: i64,
    /// `PULSAR_CONSOLE_ENGINE_QUIT_S`: `float(v or 50)`, unclamped. May be non-finite
    /// ([`seconds`]).
    pub engine_quit_s: Result<f64, InvalidSetting>,
    /// `PULSAR_CONSOLE_ENGINE_STALL_S`: `max(0.0, float(v))`, default and fallback 90; 0 is
    /// off. May be non-finite
    /// ([`seconds`]).
    pub engine_stall_s: f64,
    /// `PULSAR_CONSOLE_ENGINE_WRAP_S`: `float(v or 0)`, default 40 when unset; 0 or less
    /// cuts at once. May be non-finite
    /// ([`seconds`]).
    pub engine_wrap_s: Result<f64, InvalidSetting>,
    /// `PULSAR_CONSOLE_FAIR_SLICE_S`: `max(0.0, float(v or 0))`, fallback 0 (off). May be non-finite
    /// ([`seconds`]).
    pub fair_slice_s: f64,
    /// `PULSAR_CONSOLE_GLM_THINK_RESERVE`: `max(0, int(v or 1024))`.
    pub glm_think_reserve: Result<i64, InvalidSetting>,
    /// `PULSAR_CONSOLE_HTTP_BACKLOG`: `max(5, int(v or 256))`, fallback 256.
    pub http_backlog: i64,
    /// `PULSAR_CONSOLE_LOOP_GUARD`, raw ([`RunConfig::loop_guard`]).
    pub loop_guard: Option<String>,
    /// `PULSAR_CONSOLE_LOOP_GUARD_COLLAPSE_MAX`: `int(v or 32000)`, fallback 32000; 0 is no
    /// limit.
    pub loop_guard_collapse_max: i64,
    /// `PULSAR_CONSOLE_MAX_BODY_MIB`: `int(v)`, fallback 0; 0 or less means 256.
    pub max_body_mib: i64,
    /// `PULSAR_CONSOLE_MOCK_RELOAD_S`: `float(v)`, default 2 when unset. May be non-finite
    /// ([`seconds`]).
    pub mock_reload_s: Result<f64, InvalidSetting>,
    /// `PULSAR_CONSOLE_MOCK_TOK_S`: `float(v or 0) or None`.
    pub mock_tok_s: Result<Option<f64>, InvalidSetting>,
    /// `PULSAR_CONSOLE_MODEL_MANAGEMENT`, raw ([`RunConfig::model_management`]).
    pub model_management: Option<String>,
    /// `PULSAR_CONSOLE_PACK_TEMPLATE`: exactly `1` keeps a pack's own template.
    pub pack_template: bool,
    /// `PULSAR_CONSOLE_PROMPT_MEMO`: off for exactly `0`, on and checked against the whole
    /// prompt for exactly `verify`, on otherwise (default on).
    pub prompt_memo: PromptMemo,
    /// `PULSAR_CONSOLE_QUEUE_PING_S`: `max(0.01, float(v or 2.0))`, fallback 2.0. May be non-finite
    /// ([`seconds`]).
    pub queue_ping_s: f64,
    /// `PULSAR_CONSOLE_REQUEST_QUIET_S`: `max(0.0, float(v))`, default and fallback 900. May be non-finite
    /// ([`seconds`]).
    pub request_quiet_s: f64,
    /// `PULSAR_CONSOLE_REQUEST_TIMEOUT_S`: `float(v)` when above 0, else 300. May be non-finite
    /// ([`seconds`]).
    pub request_timeout_s: f64,
    /// `PULSAR_CONSOLE_RESTART_ON_UPDATE`: set and not empty.
    pub restart_on_update: bool,
    /// `PULSAR_CONSOLE_SAVINGS_PATH`.
    pub savings_path: SavingsPath,
    /// `PULSAR_CONSOLE_SERVER_LOG`, raw ([`RunConfig::server_log`]).
    pub server_log: Option<String>,
    /// `PULSAR_CONSOLE_TURN_TRACE`: anything but unset, `""` and `0`.
    pub turn_trace: bool,
    /// `PULSAR_CONSOLE_UPDATE_CHECK`, raw. The release check is opt-in and off by default
    /// (deviation SEC-5.3); which values enable it is fixed by OPS-22, so the text is kept.
    pub update_check: Option<String>,
    /// `PULSAR_CONSOLE_VIDEO_MAX_FRAMES`: `max(1, int(v or 240))`.
    pub video_max_frames: Result<i64, InvalidSetting>,
    /// The Responses limits as set, by name, in [`RESPONSES_LIMITS`] order; unset entries are
    /// absent. Validation belongs to RSP-01.
    pub responses: Vec<(&'static str, String)>,
}

/// `os.environ.get(name, "") or default`: the value unless unset or empty.
fn or_default<'a>(raw: Option<&'a str>, default: &'a str) -> &'a str {
    match raw {
        Some(v) if !v.is_empty() => v,
        _ => default,
    }
}

fn strict_float(name: &'static str, text: &str) -> Result<f64, InvalidSetting> {
    py::py_float(text).ok_or_else(|| InvalidSetting {
        name,
        message: py::float_error(text),
    })
}

fn strict_int(name: &'static str, text: &str) -> Result<i64, InvalidSetting> {
    py::py_int(text).ok_or_else(|| InvalidSetting {
        name,
        message: py::int_error(text),
    })
}

impl EnvSettings {
    /// Reads every setting from `env`. Nothing here fails: a bad value either falls back to
    /// the donor's default or is kept as an [`InvalidSetting`] for the package that uses it.
    pub fn from_env(env: &impl EnvSource) -> Self {
        let get = |name: &str| env.var(name);
        // `float(os.environ.get(name, default))` with `except ValueError: default`.
        let float_or = |name: &str, default: f64| -> f64 {
            get(name).map_or(default, |t| py::py_float(&t).unwrap_or(default))
        };

        // Behavior reference: serve/server.py:756.
        let drain_s = py::py_max(1.0, float_or(DRAIN_S, 60.0));
        // Behavior reference: serve/server.py:728.
        let engine_stall_s = py::py_max(0.0, float_or(ENGINE_STALL_S, 90.0));
        // Behavior reference: serve/server.py:742.
        let request_quiet_s = py::py_max(0.0, float_or(REQUEST_QUIET_S, 900.0));
        // Behavior reference: serve/server.py:404-407.
        let fair_slice_s = {
            let raw = get(FAIR_SLICE_S);
            let text = or_default(raw.as_deref(), "0");
            py::py_max(0.0, py::py_float(text).unwrap_or(0.0))
        };
        // Behavior reference: serve/server.py:396-398.
        let queue_ping_s = {
            let raw = get(QUEUE_PING_S);
            match raw.as_deref() {
                Some(t) if !t.is_empty() => py::py_float(t).map_or(2.0, |x| py::py_max(0.01, x)),
                _ => 2.0,
            }
        };
        // Behavior reference: serve/server.py:5348-5351.
        let http_backlog = {
            let raw = get(HTTP_BACKLOG);
            match raw.as_deref() {
                Some(t) if !t.is_empty() => py::py_int(t).map_or(256, |n| n.max(5)),
                _ => 256,
            }
        };
        // Behavior reference: serve/server.py:5354-5362.
        let request_timeout_s = {
            let s = get(REQUEST_TIMEOUT_S)
                .map_or(Some(0.0), |t| py::py_float(&t))
                .unwrap_or(0.0);
            if s > 0.0 {
                s
            } else {
                300.0
            }
        };
        // Behavior reference: serve/server.py:5365-5371.
        let max_body_mib = {
            let mib = get(MAX_BODY_MIB)
                .map_or(Some(0), |t| py::py_int(&t))
                .unwrap_or(0);
            if mib > 0 {
                mib
            } else {
                256
            }
        };
        // Behavior reference: serve/server.py:783-791.
        let whole = |name: &str, default: i64| -> i64 {
            match get(name) {
                Some(t) => py::py_int(&t).map_or(default, |n| n.max(0)),
                None => default,
            }
        };
        let ds4_restore_points = whole(DS4_RESTORE_POINTS, 4);
        let ds4_restore_tail = whole(DS4_RESTORE_TAIL, 512);
        // Behavior reference: serve/server.py:1705.
        let engine_quit_s = {
            let raw = get(ENGINE_QUIT_S);
            strict_float(ENGINE_QUIT_S, or_default(raw.as_deref(), "50"))
        };
        // Behavior reference: serve/server.py:7428 (an empty value is 0, not 40).
        let engine_wrap_s = match get(ENGINE_WRAP_S) {
            None => Ok(40.0),
            Some(t) if t.is_empty() => Ok(0.0),
            Some(t) => strict_float(ENGINE_WRAP_S, &t),
        };
        // Behavior reference: serve/server.py:4402.
        let glm_think_reserve = {
            let raw = get(GLM_THINK_RESERVE);
            strict_int(GLM_THINK_RESERVE, or_default(raw.as_deref(), "1024")).map(|n| n.max(0))
        };
        // Behavior reference: serve/server.py:1926.
        let video_max_frames = {
            let raw = get(VIDEO_MAX_FRAMES);
            strict_int(VIDEO_MAX_FRAMES, or_default(raw.as_deref(), "240")).map(|n| n.max(1))
        };
        // Behavior reference: serve/server.py:2771.
        let mock_reload_s = match get(MOCK_RELOAD_S) {
            None => Ok(2.0),
            Some(t) => strict_float(MOCK_RELOAD_S, &t),
        };
        // Behavior reference: serve/server.py:7290.
        let mock_tok_s = {
            let raw = get(MOCK_TOK_S);
            strict_float(MOCK_TOK_S, or_default(raw.as_deref(), "0")).map(|x| {
                if x == 0.0 {
                    None
                } else {
                    Some(x)
                }
            })
        };
        // Behavior reference: serve/loop_guard.py:594-596.
        let loop_guard_collapse_max = {
            let raw = get(LOOP_GUARD_COLLAPSE_MAX);
            py::py_int(or_default(raw.as_deref(), "32000")).unwrap_or(32000)
        };
        // Behavior reference: serve/savings.py:30-33.
        let savings_path = {
            let raw = get(SAVINGS_PATH).unwrap_or_default();
            let v = pystr::strip(&raw, None);
            if ["off", "none", "0"].contains(&v.to_lowercase().as_str()) {
                SavingsPath::Off
            } else if v.is_empty() {
                SavingsPath::BesideConfig
            } else {
                SavingsPath::File(v.to_string())
            }
        };
        let not_empty = |name: &str| get(name).is_some_and(|v| !v.is_empty());
        let not_off = |name: &str| get(name).is_some_and(|v| !v.is_empty() && v != "0");
        let responses = RESPONSES_LIMITS
            .iter()
            .filter_map(|l| get(l.name).map(|v| (l.name, v)))
            .collect();

        EnvSettings {
            // Behavior reference: serve/server.py:7139.
            api_key: get(API_KEY).unwrap_or_default(),
            // Behavior reference: serve/server.py:4747, serve/mcp.py:127.
            debug: not_empty(DEBUG),
            drain_s,
            // Behavior reference: serve/frontend.py:287.
            ds4_keep_thinking: not_off(DS4_KEEP_THINKING),
            ds4_restore_points,
            ds4_restore_tail,
            engine_quit_s,
            engine_stall_s,
            engine_wrap_s,
            fair_slice_s,
            glm_think_reserve,
            http_backlog,
            loop_guard: get(LOOP_GUARD),
            loop_guard_collapse_max,
            max_body_mib,
            mock_reload_s,
            mock_tok_s,
            model_management: get(MODEL_MANAGEMENT),
            // Behavior reference: serve/server.py:6866.
            pack_template: get(PACK_TEMPLATE).as_deref() == Some("1"),
            prompt_memo: PromptMemo::from_value(get(PROMPT_MEMO).as_deref()),
            queue_ping_s,
            request_quiet_s,
            request_timeout_s,
            // Behavior reference: serve/server.py:2873.
            restart_on_update: not_empty(RESTART_ON_UPDATE),
            savings_path,
            server_log: get(SERVER_LOG),
            // Behavior reference: serve/server.py:2093.
            turn_trace: not_off(TURN_TRACE),
            update_check: get(UPDATE_CHECK),
            video_max_frames,
            responses,
        }
    }

    /// Reads every setting from the process environment `base` with the run config's
    /// server entries laid over it ([`LayeredEnv`]), as the donor reads them after
    /// `apply_server_env`.
    ///
    /// # Errors
    ///
    /// As [`RunConfig::env_block`].
    ///
    /// Behavior reference: project-maya serve/server.py:6744-6755 at 7e68a30f.
    pub fn resolve(base: &impl EnvSource, cfg: &RunConfig) -> Result<Self, ConfigError> {
        Ok(Self::from_env(&LayeredEnv::new(base, cfg)?))
    }

    /// The largest request body in bytes: [`EnvSettings::max_body_mib`] MiB, saturating.
    ///
    /// Behavior reference: project-maya serve/server.py:5365-5371 at 7e68a30f.
    pub fn body_limit_bytes(&self) -> u64 {
        u64::try_from(self.max_body_mib)
            .unwrap_or(256)
            .saturating_mul(1 << 20)
    }

    /// Whether DeepSeek restore points are on.
    pub fn ds4_restore_on(&self) -> bool {
        self.ds4_restore_points > 0
    }
}

/// The values the command line may give for settings that the run config also holds.
/// `Debug` shows `api_key` as [`super::MASK`] when it is not empty.
#[derive(Clone, Default, PartialEq)]
pub struct CliOverrides {
    /// `--host`.
    pub host: Option<String>,
    /// `--api-key`; when absent the environment's key stands in, as the donor's default.
    pub api_key: Option<String>,
    /// `--fit-max-tokens`.
    pub fit_max_tokens: bool,
    /// `--idle-unload`.
    pub idle_unload_s: Option<f64>,
}

/// The server's settings at start-up: the environment settings and the run-config keys
/// resolved with the donor's precedence. `Debug` shows the API key as [`super::MASK`] when
/// it is not empty.
#[derive(Clone, PartialEq)]
pub struct ServerSettings {
    /// The environment settings, with the config's server entries applied.
    pub env: EnvSettings,
    /// The host to listen on ([`RunConfig::host`]).
    pub host: String,
    /// The API key setting ([`RunConfig::api_key`]): a string, or the config's list.
    pub api_key: Value,
    /// Browser origins allowed to call `/v1/*` ([`RunConfig::cors_origins`]).
    pub cors_origins: Vec<String>,
    /// Further `Host` names (deviation SEC-1.1, [`RunConfig::allowed_hosts`]); `None` by
    /// default.
    pub allowed_hosts: Option<Vec<String>>,
    /// llama.cpp's model management routes ([`RunConfig::model_management`]).
    pub model_management: bool,
    /// The loop guard ([`RunConfig::loop_guard`]).
    pub loop_guard: bool,
    /// `max_tokens` clamped instead of refused ([`RunConfig::fit_max_tokens`]).
    pub fit_max_tokens: bool,
    /// Seconds idle before the model unloads ([`RunConfig::idle_unload_s`]).
    pub idle_unload_s: f64,
    /// Where the server's own lines go ([`RunConfig::server_log`]).
    pub server_log: ServerLog,
}

impl ServerSettings {
    /// Resolves every setting, in the donor's start-up order: the config's server entries
    /// over the environment, the server log, the host, the idle unload, the API key, the CORS
    /// origins, and then the console's `allowed_hosts`.
    ///
    /// # Errors
    ///
    /// The first [`ConfigError`] in that order; start-up prints `config: ` and its text and
    /// stops.
    ///
    /// Behavior reference: project-maya serve/server.py:7151-7333 at 7e68a30f.
    pub fn resolve(
        cli: &CliOverrides,
        base: &impl EnvSource,
        cfg: &RunConfig,
    ) -> Result<Self, ConfigError> {
        let env = EnvSettings::resolve(base, cfg)?;
        let server_log = cfg.server_log(env.server_log.as_deref());
        let host = cfg.host(cli.host.as_deref())?;
        let idle_unload_s = cfg.idle_unload_s(cli.idle_unload_s)?;
        let model_management = cfg.model_management(env.model_management.as_deref());
        let loop_guard = cfg.loop_guard(env.loop_guard.as_deref());
        let api_key = cfg.api_key(cli.api_key.as_deref(), &env.api_key);
        let cors_origins = cfg.cors_origins()?;
        let allowed_hosts = cfg.allowed_hosts()?;
        Ok(ServerSettings {
            fit_max_tokens: cfg.fit_max_tokens(cli.fit_max_tokens),
            env,
            host,
            api_key,
            cors_origins,
            allowed_hosts,
            model_management,
            loop_guard,
            idle_unload_s,
            server_log,
        })
    }
}

/// `"***"` for a non-empty secret text, the text otherwise.
fn masked_text(text: &str) -> &str {
    if text.is_empty() {
        text
    } else {
        super::MASK
    }
}

impl<S> fmt::Debug for LayeredEnv<S> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("LayeredEnv")
            .field("overrides", &self.overrides)
            .finish_non_exhaustive()
    }
}

impl fmt::Debug for EnvSettings {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("EnvSettings")
            .field("api_key", &masked_text(&self.api_key))
            .field("debug", &self.debug)
            .field("drain_s", &self.drain_s)
            .field("ds4_keep_thinking", &self.ds4_keep_thinking)
            .field("ds4_restore_points", &self.ds4_restore_points)
            .field("ds4_restore_tail", &self.ds4_restore_tail)
            .field("engine_quit_s", &self.engine_quit_s)
            .field("engine_stall_s", &self.engine_stall_s)
            .field("engine_wrap_s", &self.engine_wrap_s)
            .field("fair_slice_s", &self.fair_slice_s)
            .field("glm_think_reserve", &self.glm_think_reserve)
            .field("http_backlog", &self.http_backlog)
            .field("loop_guard", &self.loop_guard)
            .field("loop_guard_collapse_max", &self.loop_guard_collapse_max)
            .field("max_body_mib", &self.max_body_mib)
            .field("mock_reload_s", &self.mock_reload_s)
            .field("mock_tok_s", &self.mock_tok_s)
            .field("model_management", &self.model_management)
            .field("pack_template", &self.pack_template)
            .field("prompt_memo", &self.prompt_memo)
            .field("queue_ping_s", &self.queue_ping_s)
            .field("request_quiet_s", &self.request_quiet_s)
            .field("request_timeout_s", &self.request_timeout_s)
            .field("restart_on_update", &self.restart_on_update)
            .field("savings_path", &self.savings_path)
            .field("server_log", &self.server_log)
            .field("turn_trace", &self.turn_trace)
            .field("update_check", &self.update_check)
            .field("video_max_frames", &self.video_max_frames)
            .field("responses", &self.responses)
            .finish()
    }
}

impl fmt::Debug for CliOverrides {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("CliOverrides")
            .field("host", &self.host)
            .field("api_key", &self.api_key.as_deref().map(masked_text))
            .field("fit_max_tokens", &self.fit_max_tokens)
            .field("idle_unload_s", &self.idle_unload_s)
            .finish()
    }
}

impl fmt::Debug for ServerSettings {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("ServerSettings")
            .field("env", &self.env)
            .field("host", &self.host)
            .field("api_key", &masked_value(&self.api_key))
            .field("cors_origins", &self.cors_origins)
            .field("allowed_hosts", &self.allowed_hosts)
            .field("model_management", &self.model_management)
            .field("loop_guard", &self.loop_guard)
            .field("fit_max_tokens", &self.fit_max_tokens)
            .field("idle_unload_s", &self.idle_unload_s)
            .field("server_log", &self.server_log)
            .finish()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::RefCell;

    fn env(pairs: &[(&str, &str)]) -> BTreeMap<String, String> {
        pairs
            .iter()
            .map(|(k, v)| ((*k).to_string(), (*v).to_string()))
            .collect()
    }

    fn settings(pairs: &[(&str, &str)]) -> EnvSettings {
        EnvSettings::from_env(&env(pairs))
    }

    struct Recording {
        asked: RefCell<Vec<String>>,
    }

    impl EnvSource for Recording {
        fn var(&self, name: &str) -> Option<String> {
            self.asked.borrow_mut().push(name.to_string());
            None
        }
    }

    #[test]
    fn reads_exactly_the_names_in_the_table() {
        let rec = Recording {
            asked: RefCell::new(Vec::new()),
        };
        let _ = EnvSettings::from_env(&rec);
        let mut asked: Vec<String> = rec.asked.borrow().clone();
        asked.sort();
        asked.dedup();
        let mut expected: Vec<String> = SERVER_SETTINGS
            .iter()
            .map(|s| s.name.to_string())
            .chain(RESPONSES_LIMITS.iter().map(|l| l.name.to_string()))
            .collect();
        expected.sort();
        assert_eq!(asked, expected);
        assert!(asked.iter().all(|n| n.starts_with(ENV_PREFIX)));
    }

    #[test]
    fn table_is_the_mechanical_rename() {
        for s in SERVER_SETTINGS {
            let suffix = s.donor.strip_prefix("MAYA_").unwrap_or("?");
            assert_eq!(s.name, format!("{ENV_PREFIX}{suffix}"), "{}", s.donor);
        }
        for l in RESPONSES_LIMITS {
            assert_eq!(l.name, format!("{RESPONSES_PREFIX}{}", l.key));
            assert_eq!(l.donor, format!("MAYA_GLM_RESPONSES_{}", l.key));
        }
        assert!(SERVER_ENV
            .iter()
            .chain(SERVER_ENV_LATE)
            .all(|n| SERVER_SETTINGS.iter().any(|s| s.name == *n)));
    }

    #[test]
    fn defaults_when_nothing_is_set() {
        let s = settings(&[]);
        assert_eq!(s.api_key, "");
        assert!(!s.debug);
        assert_eq!(s.drain_s, 60.0);
        assert!(!s.ds4_keep_thinking);
        assert_eq!((s.ds4_restore_points, s.ds4_restore_tail), (4, 512));
        assert!(s.ds4_restore_on());
        assert_eq!(s.engine_quit_s, Ok(50.0));
        assert_eq!(s.engine_stall_s, 90.0);
        assert_eq!(s.engine_wrap_s, Ok(40.0));
        assert_eq!(s.fair_slice_s, 0.0);
        assert_eq!(s.glm_think_reserve, Ok(1024));
        assert_eq!(s.http_backlog, 256);
        assert_eq!(s.loop_guard, None);
        assert_eq!(s.loop_guard_collapse_max, 32000);
        assert_eq!(s.max_body_mib, 256);
        assert_eq!(s.body_limit_bytes(), 256 << 20);
        assert_eq!(s.mock_reload_s, Ok(2.0));
        assert_eq!(s.mock_tok_s, Ok(None));
        assert_eq!(s.model_management, None);
        assert!(!s.pack_template);
        assert_eq!(s.prompt_memo, PromptMemo::On);
        assert_eq!(s.queue_ping_s, 2.0);
        assert_eq!(s.request_quiet_s, 900.0);
        assert_eq!(s.request_timeout_s, 300.0);
        assert!(!s.restart_on_update);
        assert_eq!(s.savings_path, SavingsPath::BesideConfig);
        assert_eq!(s.server_log, None);
        assert!(!s.turn_trace);
        assert_eq!(s.update_check, None);
        assert_eq!(s.video_max_frames, Ok(240));
        assert!(s.responses.is_empty());
    }

    #[test]
    fn minimums_apply() {
        let s = settings(&[
            (DRAIN_S, "0.5"),
            (ENGINE_STALL_S, "-3"),
            (REQUEST_QUIET_S, "-1"),
            (FAIR_SLICE_S, "-2"),
            (QUEUE_PING_S, "0.001"),
            (HTTP_BACKLOG, "1"),
            (DS4_RESTORE_POINTS, "-1"),
            (DS4_RESTORE_TAIL, "-5"),
            (GLM_THINK_RESERVE, "-9"),
            (VIDEO_MAX_FRAMES, "0"),
            (MAX_BODY_MIB, "-4"),
            (REQUEST_TIMEOUT_S, "-1"),
        ]);
        assert_eq!(s.drain_s, 1.0);
        assert_eq!(s.engine_stall_s, 0.0);
        assert_eq!(s.request_quiet_s, 0.0);
        assert_eq!(s.fair_slice_s, 0.0);
        assert_eq!(s.queue_ping_s, 0.01);
        assert_eq!(s.http_backlog, 5);
        assert_eq!((s.ds4_restore_points, s.ds4_restore_tail), (0, 0));
        assert!(!s.ds4_restore_on());
        assert_eq!(s.glm_think_reserve, Ok(0));
        assert_eq!(s.video_max_frames, Ok(1));
        assert_eq!(s.max_body_mib, 256);
        assert_eq!(s.request_timeout_s, 300.0);
    }

    #[test]
    fn values_parse_with_python_rules() {
        let s = settings(&[
            (DRAIN_S, " 12.5 "),
            (ENGINE_STALL_S, "0"),
            (QUEUE_PING_S, "1_0"),
            (HTTP_BACKLOG, " 64 "),
            (MAX_BODY_MIB, "8"),
            (REQUEST_TIMEOUT_S, "inf"),
            (ENGINE_QUIT_S, "1e1"),
            (ENGINE_WRAP_S, "0"),
            (MOCK_TOK_S, "25"),
            (MOCK_RELOAD_S, "0.25"),
            (LOOP_GUARD_COLLAPSE_MAX, "0"),
        ]);
        assert_eq!(s.drain_s, 12.5);
        assert_eq!(s.engine_stall_s, 0.0);
        assert_eq!(s.queue_ping_s, 10.0);
        assert_eq!(s.http_backlog, 64);
        assert_eq!(s.body_limit_bytes(), 8 << 20);
        assert_eq!(s.request_timeout_s, f64::INFINITY);
        assert_eq!(s.engine_quit_s, Ok(10.0));
        assert_eq!(s.engine_wrap_s, Ok(0.0));
        assert_eq!(s.mock_tok_s, Ok(Some(25.0)));
        assert_eq!(s.mock_reload_s, Ok(0.25));
        assert_eq!(s.loop_guard_collapse_max, 0);
    }

    #[test]
    fn invalid_values_fall_back_where_the_donor_catches_them() {
        let bad = "x";
        let s = settings(&[
            (DRAIN_S, bad),
            (ENGINE_STALL_S, bad),
            (REQUEST_QUIET_S, bad),
            (FAIR_SLICE_S, bad),
            (QUEUE_PING_S, bad),
            (HTTP_BACKLOG, "2.5"),
            (DS4_RESTORE_POINTS, bad),
            (DS4_RESTORE_TAIL, "1.0"),
            (LOOP_GUARD_COLLAPSE_MAX, bad),
            (MAX_BODY_MIB, "1.5"),
            (REQUEST_TIMEOUT_S, bad),
        ]);
        assert_eq!(s.drain_s, 60.0);
        assert_eq!(s.engine_stall_s, 90.0);
        assert_eq!(s.request_quiet_s, 900.0);
        assert_eq!(s.fair_slice_s, 0.0);
        assert_eq!(s.queue_ping_s, 2.0);
        assert_eq!(s.http_backlog, 256);
        assert_eq!((s.ds4_restore_points, s.ds4_restore_tail), (4, 512));
        assert_eq!(s.loop_guard_collapse_max, 32000);
        assert_eq!(s.max_body_mib, 256);
        assert_eq!(s.request_timeout_s, 300.0);
    }

    #[test]
    fn empty_values_follow_each_rule() {
        let s = settings(&[
            (DRAIN_S, ""),
            (ENGINE_STALL_S, ""),
            (QUEUE_PING_S, ""),
            (HTTP_BACKLOG, ""),
            (ENGINE_QUIT_S, ""),
            (ENGINE_WRAP_S, ""),
            (GLM_THINK_RESERVE, ""),
            (VIDEO_MAX_FRAMES, ""),
            (MOCK_TOK_S, ""),
            (DS4_KEEP_THINKING, ""),
            (TURN_TRACE, "0"),
            (DEBUG, ""),
            (PROMPT_MEMO, ""),
            (SAVINGS_PATH, "  "),
        ]);
        assert_eq!(s.drain_s, 60.0);
        assert_eq!(s.engine_stall_s, 90.0);
        assert_eq!(s.queue_ping_s, 2.0);
        assert_eq!(s.http_backlog, 256);
        assert_eq!(s.engine_quit_s, Ok(50.0));
        assert_eq!(s.engine_wrap_s, Ok(0.0));
        assert_eq!(s.glm_think_reserve, Ok(1024));
        assert_eq!(s.video_max_frames, Ok(240));
        assert_eq!(s.mock_tok_s, Ok(None));
        assert!(!s.ds4_keep_thinking);
        assert!(!s.turn_trace);
        assert!(!s.debug);
        assert_eq!(s.prompt_memo, PromptMemo::On);
        assert_eq!(s.savings_path, SavingsPath::BesideConfig);
        // An empty mock reload time is not tolerated: float("") raises.
        let r = settings(&[(MOCK_RELOAD_S, "")]);
        assert_eq!(
            r.mock_reload_s,
            Err(InvalidSetting {
                name: MOCK_RELOAD_S,
                message: String::from("could not convert string to float: ''"),
            })
        );
    }

    #[test]
    fn untolerated_values_keep_python_s_message() {
        let s = settings(&[
            (ENGINE_QUIT_S, "soon"),
            (ENGINE_WRAP_S, "x"),
            (GLM_THINK_RESERVE, "1.5"),
            (VIDEO_MAX_FRAMES, "many"),
            (MOCK_TOK_S, "fast"),
        ]);
        assert_eq!(
            s.engine_quit_s.as_ref().map_err(|e| e.message.as_str()),
            Err("could not convert string to float: 'soon'")
        );
        assert!(s.engine_wrap_s.is_err());
        assert_eq!(
            s.glm_think_reserve.as_ref().map_err(|e| e.to_string()),
            Err(String::from(
                "PULSAR_CONSOLE_GLM_THINK_RESERVE: invalid literal for int() with base 10: '1.5'"
            ))
        );
        assert!(s.video_max_frames.is_err());
        assert!(s.mock_tok_s.is_err());
    }

    #[test]
    fn switches() {
        let s = settings(&[
            (DEBUG, "1"),
            (DS4_KEEP_THINKING, "yes"),
            (TURN_TRACE, "1"),
            (RESTART_ON_UPDATE, "0"),
            (PACK_TEMPLATE, "1"),
            (PROMPT_MEMO, "0"),
            (UPDATE_CHECK, "1"),
        ]);
        assert!(s.debug && s.ds4_keep_thinking && s.turn_trace && s.pack_template);
        // Any non-empty value restarts, "0" included (Python's bool("0") is True).
        assert!(s.restart_on_update);
        assert_eq!(s.prompt_memo, PromptMemo::Off);
        assert!(!s.prompt_memo.is_on());
        assert_eq!(s.update_check.as_deref(), Some("1"));
        assert!(!settings(&[(PACK_TEMPLATE, " 1")]).pack_template);
        assert_eq!(settings(&[(PROMPT_MEMO, " 0")]).prompt_memo, PromptMemo::On);
    }

    #[test]
    fn prompt_memo_has_three_readings() {
        let verify = settings(&[(PROMPT_MEMO, "verify")]).prompt_memo;
        assert_eq!(verify, PromptMemo::Verify);
        assert!(verify.is_on() && verify.verifies());
        for on in ["1", " verify", "Verify", "verify ", "None", ""] {
            let m = settings(&[(PROMPT_MEMO, on)]).prompt_memo;
            assert_eq!(m, PromptMemo::On, "{on:?}");
            assert!(m.is_on() && !m.verifies(), "{on:?}");
        }
        assert_eq!(settings(&[]).prompt_memo, PromptMemo::On);
        assert!(!PromptMemo::Off.is_on() && !PromptMemo::Off.verifies());
    }

    #[test]
    fn seconds_never_panic() {
        assert_eq!(seconds(1.5), Seconds::For(Duration::from_millis(1500)));
        assert_eq!(seconds(0.0), Seconds::For(Duration::ZERO));
        assert_eq!(seconds(-3.0), Seconds::For(Duration::ZERO));
        assert_eq!(seconds(f64::NEG_INFINITY), Seconds::For(Duration::ZERO));
        assert_eq!(seconds(f64::INFINITY), Seconds::Unbounded);
        assert_eq!(seconds(1e300), Seconds::Unbounded);
        assert_eq!(seconds(f64::NAN), Seconds::NotANumber);
        let s = settings(&[
            (REQUEST_TIMEOUT_S, "inf"),
            (ENGINE_QUIT_S, "nan"),
            (ENGINE_WRAP_S, "-inf"),
            (DRAIN_S, "nan"),
        ]);
        assert_eq!(seconds(s.request_timeout_s), Seconds::Unbounded);
        assert_eq!(
            s.engine_quit_s.as_ref().map(|x| seconds(*x)),
            Ok(Seconds::NotANumber)
        );
        assert_eq!(
            s.engine_wrap_s.as_ref().map(|x| seconds(*x)),
            Ok(Seconds::For(Duration::ZERO))
        );
        // max(1.0, nan) is 1.0 in Python: the clamped settings are never nan.
        assert_eq!(seconds(s.drain_s), Seconds::For(Duration::from_secs(1)));
        // A NaN request timeout is not above 0, so it reads as 300.
        let nan_timeout = settings(&[(REQUEST_TIMEOUT_S, "nan")]);
        assert_eq!(
            seconds(nan_timeout.request_timeout_s),
            Seconds::For(Duration::from_secs(300))
        );
    }

    #[test]
    fn debug_masks_the_api_keys() {
        let s = settings(&[(API_KEY, "envsecret1")]);
        let shown = format!("{s:?}");
        assert!(
            !shown.contains("envsecret1") && shown.contains("***"),
            "{shown}"
        );
        assert!(format!("{:?}", settings(&[])).contains("api_key: \"\""));
        let cli = CliOverrides {
            api_key: Some(String::from("clisecret2")),
            ..CliOverrides::default()
        };
        let shown = format!("{cli:?}");
        assert!(!shown.contains("clisecret2"), "{shown}");
        let layered = LayeredEnv {
            base: env(&[(API_KEY, "basesecret3")]),
            overrides: BTreeMap::new(),
        };
        assert!(!format!("{layered:?}").contains("basesecret3"));
    }

    #[test]
    fn savings_path_forms() {
        assert_eq!(
            settings(&[(SAVINGS_PATH, " OFF ")]).savings_path,
            SavingsPath::Off
        );
        assert_eq!(
            settings(&[(SAVINGS_PATH, "none")]).savings_path,
            SavingsPath::Off
        );
        assert_eq!(
            settings(&[(SAVINGS_PATH, "0")]).savings_path,
            SavingsPath::Off
        );
        let file = settings(&[(SAVINGS_PATH, " ~/s.json ")]).savings_path;
        assert_eq!(file, SavingsPath::File(String::from("~/s.json")));
        let cfg_path = Path::new("dir").join("pulsar-a.json");
        assert_eq!(
            file.resolve(&cfg_path, Some(Path::new("home"))),
            Some(Path::new("home").join("s.json"))
        );
        assert_eq!(
            SavingsPath::BesideConfig.resolve(&cfg_path, None),
            Some(Path::new("dir").join(SAVINGS_FILE))
        );
        assert_eq!(
            SavingsPath::BesideConfig.resolve(Path::new("pulsar-a.json"), None),
            Some(Path::new(".").join(SAVINGS_FILE))
        );
        assert_eq!(SavingsPath::Off.resolve(&cfg_path, None), None);
        // Narrower than Python's expanduser (proposal P-23): `~name/` is not expanded,
        // and nothing is expanded without `home`.
        let other = SavingsPath::File(String::from("~bob/x.json"));
        assert_eq!(
            other.resolve(&cfg_path, Some(Path::new("home"))),
            Some(PathBuf::from("~bob/x.json"))
        );
        assert_eq!(
            SavingsPath::File(String::from("~/x.json")).resolve(&cfg_path, None),
            Some(PathBuf::from("~/x.json"))
        );
    }

    #[test]
    fn legacy_names_are_not_read() {
        // Decision B2 and deviation BRAND-1: MAYA_* and STRATA_* are not aliases.
        let s = settings(&[
            ("MAYA_HTTP_BACKLOG", "64"),
            ("STRATA_HTTP_BACKLOG", "64"),
            ("MAYA_API_KEY", "k"),
            ("MAYA_PULL_COMMAND", "[\"x\"]"),
        ]);
        assert_eq!(s, settings(&[]));
    }

    #[test]
    fn responses_limits_raw() {
        let s = settings(&[
            ("PULSAR_CONSOLE_GLM_RESPONSES_JOB_WORKERS", "4"),
            ("PULSAR_CONSOLE_GLM_RESPONSES_CACHE_ENTRIES", "x"),
        ]);
        assert_eq!(
            s.responses,
            vec![
                (
                    "PULSAR_CONSOLE_GLM_RESPONSES_CACHE_ENTRIES",
                    String::from("x")
                ),
                (
                    "PULSAR_CONSOLE_GLM_RESPONSES_JOB_WORKERS",
                    String::from("4")
                ),
            ]
        );
        assert_eq!(RESPONSES_LIMITS.len(), 18);
        assert_eq!(RESPONSES_LIMITS.iter().map(|l| l.default).sum::<u64>(), {
            128 + 64 * MIB
                + 3600
                + 64 * MIB
                + 64 * MIB
                + 2
                + 16
                + 4
                + 300
                + 900
                + 2 * MIB
                + 2 * MIB
                + 4096
                + 32
                + 8
                + 5
        });
    }
}
