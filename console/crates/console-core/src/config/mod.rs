//! Owned by API-15. The run-config document store (`RunConfigStore`) and the environment
//! settings (`EnvSettings`).
//!
//! - [`RunConfig`] is the run config as an order-preserving JSON object: unknown keys and
//!   key order survive every read and rewrite, and typed accessors read the keys the server
//!   uses at start-up (`host`, `api_key`, `cors_origins`, `model_management`, `loop_guard`,
//!   `fit_max_tokens`, `idle_unload_s`, `log`, `env`) with the donor's coercions, plus the
//!   console's own optional `allowed_hosts` (deviation SEC-1.1, decided by the owner on
//!   2026-11-14; API-03 enforces it).
//! - The store functions ([`load_document`], [`read_document`], [`write_document`],
//!   [`commit`], [`config_paths`]) and [`RunConfigStore`] read and write run configs through
//!   one writer, Python's `json.dumps(obj, indent=1)` from `console-pyjson`, written to
//!   `<name>.tmp` and renamed. Every persisted file is resolved relative to the directory of
//!   the run config passed with `--config` (lead decision LD26); the default directory when
//!   no config is given is open item OPEN-06 and is not chosen here.
//! - [`EnvSettings`] reads every server environment variable, named with the prefix
//!   `PULSAR_CONSOLE_` (contracts/naming.md section 3.1; legacy `MAYA_*` and `STRATA_*`
//!   names are not read), from an injected [`EnvSource`]. [`ServerSettings`] resolves the
//!   environment, the command line and the run config with the donor's precedence.
//!
//! Names in a run config's `env` block that go to the engine child pass verbatim, once
//! (contracts/naming.md rule 3). The engine ready-timeout of approved deviation P-6 is added
//! by ENG-06 in M3, not here. Nothing in this module admits or starts an engine; it is
//! qualified on synthetic backends only.

mod document;
mod env;
mod py;
mod store;

pub use document::{
    engine_changed, kept_secret, parse_cors_origins, shown_env, ConfigError, RunConfig, ServerLog,
    ALLOWED_HOSTS_MESSAGE, CORS_ORIGINS_MESSAGE, DEFAULT_HOST, ENGINE_KEYS, MASK,
};
pub use env::{
    seconds, server_env_overrides, CliOverrides, EnvSettings, EnvSource, InvalidSetting,
    LayeredEnv, ProcessEnv, PromptMemo, ResponsesLimit, SavingsPath, Seconds, ServerSettings,
    SettingName, ENV_PREFIX, RESPONSES_LIMITS, RESPONSES_PREFIX, SAVINGS_FILE, SERVER_ENV,
    SERVER_ENV_LATE, SERVER_SETTINGS,
};
pub use store::{
    checked_config_path, commit, config_dir, config_paths, document_text, file_times,
    is_config_file_name, load_document, no_config_message, prev_path, read_document,
    set_file_times, touch, write_document, write_keeping_times, write_note, write_prev,
    CommitOutcome, FileTimes, RunConfigStore, CONFIG_PREFIX, DELETE_FILE, MAX_CONFIG_BYTES,
    SHARED_SETTINGS_SUFFIX, SWITCH_FILE,
};

/// The environment variable names, one constant each (`names::HTTP_BACKLOG` is
/// `PULSAR_CONSOLE_HTTP_BACKLOG`).
pub mod names {
    pub use super::env::{
        API_KEY, DEBUG, DRAIN_S, DS4_KEEP_THINKING, DS4_RESTORE_POINTS, DS4_RESTORE_TAIL,
        ENGINE_QUIT_S, ENGINE_STALL_S, ENGINE_WRAP_S, FAIR_SLICE_S, GLM_THINK_RESERVE,
        HTTP_BACKLOG, LOOP_GUARD, LOOP_GUARD_COLLAPSE_MAX, MAX_BODY_MIB, MOCK_RELOAD_S, MOCK_TOK_S,
        MODEL_MANAGEMENT, PACK_TEMPLATE, PROMPT_MEMO, QUEUE_PING_S, REQUEST_QUIET_S,
        REQUEST_TIMEOUT_S, RESTART_ON_UPDATE, SAVINGS_PATH, SERVER_LOG, TURN_TRACE, UPDATE_CHECK,
        VIDEO_MAX_FRAMES,
    };
}
