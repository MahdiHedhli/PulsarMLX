//! The files a scenario needs before its server starts: the generated `bpe-bytes`
//! tokenizer directory, the run config, and the data-directory files.
//!
//! For a line engine the run config holds `exe` (the fake engine executable the caller
//! names), `args` and `tokenizer` from the engine spec, merged over the scenario's
//! `server.config`, and an `env` block that merges `server.config.env` with the engine's
//! `env`, in that order. A name set in both is refused, where the donor's
//! `dict(cfg["env"], **extra)` lets the engine value win (serve/test_glm_dsa_serve.py:226-228
//! at 7e68a30f): a scenario states each variable once. Every name of the
//! resulting `env` block is checked like the server's own environment
//! ([`super::env::check_config_env`]): the server hands that block to its engine child.
//!
//! Behavior reference: project-maya serve/test_stop.py:44-68 at 7e68a30f and
//! serve/test_glm_dsa_serve.py:224-236 at 7e68a30f.

use std::ffi::OsString;
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};

use serde_json::{Map, Value};

use super::env::check_config_env;
use super::ProcessError;
use crate::scenario::{DataFile, EngineSpec, Scenario, TokenizerSpec, TOKENS};

/// The name of the generated tokenizer directory inside the data directory.
pub const TOKENIZER_DIR_NAME: &str = "tokenizer";

/// The name of the generated run config inside the data directory (run-config files use
/// the prefix `pulsar-`, binding decision B2).
pub const CONFIG_FILE_NAME: &str = "pulsar-scenario.json";

/// What [`ScenarioFiles::write`] wrote.
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct ScenarioFiles {
    /// The generated tokenizer directory, for a `bpe-bytes` tokenizer.
    pub tokenizer_dir: Option<PathBuf>,
    /// The run config, for a line engine or a scenario with a `server.config`.
    pub config_path: Option<PathBuf>,
    /// The data-directory files, in the scenario's order.
    pub data_files: Vec<PathBuf>,
}

impl ScenarioFiles {
    /// Writes the files of `scenario` into `data_dir`, which must exist. `line_exe` is the
    /// fake engine executable for a line engine and is required for one. The scenario
    /// must already be expanded ([`Scenario::expand`]): a substitution token left in
    /// `server.config` is refused. No existing file is overwritten.
    pub fn write(
        scenario: &Scenario,
        data_dir: &Path,
        line_exe: Option<&Path>,
    ) -> Result<Self, ProcessError> {
        let mut out = ScenarioFiles::default();
        for (rel, _) in &scenario.server.data_dir {
            if rel == CONFIG_FILE_NAME
                || rel == TOKENIZER_DIR_NAME
                || rel.starts_with(&format!("{TOKENIZER_DIR_NAME}/"))
            {
                return Err(ProcessError::BadScenario {
                    reason: format!("server.data_dir/{rel} is a path the harness writes"),
                });
            }
        }

        let tokenizer = match &scenario.engine {
            EngineSpec::Mock(m) => &m.tokenizer,
            EngineSpec::Line(l) => &l.tokenizer,
        };
        out.tokenizer_dir = write_tokenizer(tokenizer, data_dir)?;

        let config = match &scenario.engine {
            EngineSpec::Line(line) => {
                let exe = line_exe.ok_or_else(|| ProcessError::BadScenario {
                    reason: "a line engine needs the fake engine executable".to_string(),
                })?;
                let tok = out
                    .tokenizer_dir
                    .as_ref()
                    .ok_or_else(|| ProcessError::BadScenario {
                        reason: "a line engine needs a bpe-bytes tokenizer".to_string(),
                    })?;
                let mut config = scenario.server.config.clone();
                config.insert("exe".into(), Value::String(path_text(exe)?));
                config.insert(
                    "args".into(),
                    Value::Array(line.args.iter().cloned().map(Value::String).collect()),
                );
                config.insert("tokenizer".into(), Value::String(path_text(tok)?));
                if !line.env.is_empty() {
                    let mut env = match config.get("env") {
                        None => Map::new(),
                        Some(Value::Object(m)) => m.clone(),
                        Some(_) => {
                            return Err(ProcessError::BadScenario {
                                reason: "server.config.env must be an object".to_string(),
                            })
                        }
                    };
                    for (name, value) in &line.env {
                        if env.contains_key(name) {
                            return Err(ProcessError::BadScenario {
                                reason: format!(
                                    "{name} is set both in server.config.env and in the line engine's env"
                                ),
                            });
                        }
                        env.insert(name.clone(), Value::String(value.clone()));
                    }
                    config.insert("env".into(), Value::Object(env));
                }
                Some(config)
            }
            EngineSpec::Mock(_) if !scenario.server.config.is_empty() => {
                Some(scenario.server.config.clone())
            }
            EngineSpec::Mock(_) => None,
        };
        if let Some(config) = config {
            check_config_env(&config)?;
            let text = Value::Object(config).to_string();
            for token in TOKENS {
                if text.contains(&format!("{{{{{token}}}}}")) {
                    return Err(ProcessError::BadScenario {
                        reason: format!(
                            "server.config still holds the token {{{{{token}}}}}: expand the scenario first"
                        ),
                    });
                }
            }
            let path = data_dir.join(CONFIG_FILE_NAME);
            create_new(&path, text.as_bytes())?;
            out.config_path = Some(path);
        }

        for (rel, file) in &scenario.server.data_dir {
            let path = data_dir.join(rel);
            if let Some(parent) = path.parent() {
                fs::create_dir_all(parent)
                    .map_err(|e| ProcessError::io(format!("create {}", parent.display()), e))?;
            }
            let bytes = match file {
                DataFile::Text(s) => s.clone().into_bytes(),
                DataFile::Json(v) => v.to_string().into_bytes(),
            };
            create_new(&path, &bytes)?;
            out.data_files.push(path);
        }
        Ok(out)
    }

    /// `--config <path>` when a run config was written; nothing otherwise. The engine
    /// flags themselves are set by the caller, from the command line of the binary under
    /// test (contracts/cli.md).
    pub fn config_args(&self) -> Vec<OsString> {
        match &self.config_path {
            Some(p) => vec!["--config".into(), p.clone().into_os_string()],
            None => Vec::new(),
        }
    }
}

fn write_tokenizer(spec: &TokenizerSpec, data_dir: &Path) -> Result<Option<PathBuf>, ProcessError> {
    let Some(files) = spec.generated_files() else {
        return Ok(None);
    };
    let dir = data_dir.join(TOKENIZER_DIR_NAME);
    fs::create_dir(&dir).map_err(|e| ProcessError::io(format!("create {}", dir.display()), e))?;
    for (name, content) in files {
        create_new(&dir.join(name), content.as_bytes())?;
    }
    Ok(Some(dir))
}

fn create_new(path: &Path, bytes: &[u8]) -> Result<(), ProcessError> {
    let mut f = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)
        .map_err(|e| ProcessError::io(format!("create {}", path.display()), e))?;
    f.write_all(bytes)
        .map_err(|e| ProcessError::io(format!("write {}", path.display()), e))
}

fn path_text(p: &Path) -> Result<String, ProcessError> {
    p.to_str()
        .map(str::to_string)
        .ok_or_else(|| ProcessError::BadScenario {
            reason: format!("{} is not UTF-8", p.display()),
        })
}
