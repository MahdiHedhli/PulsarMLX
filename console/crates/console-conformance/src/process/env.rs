//! The environment of a process the harness starts.
//!
//! The environment is cleared, then filled from an allowlist:
//!
//! - `PATH`: the harness's own, or `/usr/bin:/bin` when it has none;
//! - `TZ=UTC`, `LC_ALL=C.UTF-8` and `LANG=C.UTF-8`;
//! - `HOME`, `XDG_CONFIG_HOME`, `XDG_DATA_HOME`, `XDG_CACHE_HOME`, `XDG_STATE_HOME`,
//!   `XDG_RUNTIME_DIR` and `TMPDIR`, all inside the run's [`Workdir`](super::Workdir);
//! - `PULSAR_CONSOLE_VENDOR_DIR` and `FAKE_ENGINE_GATE` when the caller gives them;
//! - then the scenario's own variables, which may not use a reserved name
//!   ([`crate::scenario::is_reserved_env`]).
//!
//! Nothing else is inherited: no `PULSAR_CONSOLE_*`, `MAYA_*` or `STRATA_*` setting, no
//! proxy variable, no loader variable.
//!
//! The same refusal covers the `env` block of a run config the harness writes
//! ([`check_config_env`]): the server passes that block to its engine child (naming.md
//! rule 3), so a reserved name there would undo the allowlist for the engine.

use std::ffi::OsString;
use std::path::Path;

use super::ProcessError;
use crate::scenario::{is_reserved_env, limits, VENDOR_DIR_ENV};

/// The variable naming the engine step-gate FIFO (tasks/conformance.md, "Scripted
/// behaviour expressed once"); a fake-engine control variable, kept under the donor
/// fakes' naming (R5).
pub const ENGINE_GATE_ENV: &str = "FAKE_ENGINE_GATE";

/// `PATH` when the harness itself has none.
pub const FALLBACK_PATH: &str = "/usr/bin:/bin";

/// Whether `name` is a well-formed environment name for a scenario: `[A-Z_][A-Z0-9_]*`,
/// at most [`limits::MAX_ENV_NAME_CHARS`] characters (the scenario loader's rule).
pub fn is_env_name(name: &str) -> bool {
    !name.is_empty()
        && name.len() <= limits::MAX_ENV_NAME_CHARS
        && name
            .bytes()
            .next()
            .is_some_and(|b| b.is_ascii_uppercase() || b == b'_')
        && name
            .bytes()
            .all(|b| b.is_ascii_uppercase() || b.is_ascii_digit() || b == b'_')
}

/// Checks one caller-supplied entry: a well-formed, unreserved name, a value without NUL
/// and within [`limits::MAX_ENV_VALUE_CHARS`].
pub fn check_entry(origin: &str, name: &str, value: &str) -> Result<(), ProcessError> {
    let refuse = |reason: &str| ProcessError::BadEnv {
        origin: origin.to_string(),
        name: name.to_string(),
        reason: reason.to_string(),
    };
    if !is_env_name(name) {
        return Err(refuse("an environment name must match [A-Z_][A-Z0-9_]*"));
    }
    if is_reserved_env(name) {
        return Err(refuse(
            "set by the harness: PATH, HOME, TZ, LC_ALL, LANG, TMPDIR, PULSAR_CONSOLE_VENDOR_DIR, FAKE_ENGINE_GATE and names starting with XDG_, LD_, DYLD_ or PYTHON are reserved",
        ));
    }
    if value.contains('\0') {
        return Err(refuse("the value must not contain NUL"));
    }
    if value.chars().count() > limits::MAX_ENV_VALUE_CHARS {
        return Err(refuse("the value is too long"));
    }
    Ok(())
}

/// Checks the `env` member of a run config the harness is about to write. A missing
/// member is fine. A present one must be an object whose names pass [`check_entry`] and
/// whose values are strings, numbers or booleans (the donor writes each with `str()`).
pub fn check_config_env(
    config: &serde_json::Map<String, serde_json::Value>,
) -> Result<(), ProcessError> {
    let origin = "server.config.env";
    let Some(env) = config.get("env") else {
        return Ok(());
    };
    let Some(map) = env.as_object() else {
        return Err(ProcessError::BadScenario {
            reason: format!("{origin} must be an object"),
        });
    };
    if map.len() > limits::MAX_ENV {
        return Err(ProcessError::BadScenario {
            reason: format!("{origin} has more than {} entries", limits::MAX_ENV),
        });
    }
    for (name, value) in map {
        let text = match value {
            serde_json::Value::String(s) => s.clone(),
            serde_json::Value::Number(n) => n.to_string(),
            serde_json::Value::Bool(b) => b.to_string(),
            _ => {
                return Err(ProcessError::BadEnv {
                    origin: origin.to_string(),
                    name: name.clone(),
                    reason: "the value must be a string, a number or a boolean".to_string(),
                })
            }
        };
        check_entry(origin, name, &text)?;
    }
    Ok(())
}

/// The directories the allowlist points into.
#[derive(Debug, Clone, Copy)]
pub struct EnvDirs<'a> {
    /// `HOME`.
    pub home: &'a Path,
    /// `TMPDIR`.
    pub tmp: &'a Path,
    /// `XDG_RUNTIME_DIR`.
    pub runtime: &'a Path,
}

/// Builds the full environment: the allowlist, then `extra` in order. `extra` is checked
/// with [`check_entry`]; a name given twice is refused.
pub fn build(
    dirs: EnvDirs<'_>,
    vendor_dir: Option<&Path>,
    engine_gate: Option<&Path>,
    extra: &[(String, String)],
) -> Result<Vec<(OsString, OsString)>, ProcessError> {
    let path = std::env::var_os("PATH")
        .filter(|p| !p.is_empty())
        .unwrap_or_else(|| OsString::from(FALLBACK_PATH));
    let home = dirs.home;
    let mut out: Vec<(OsString, OsString)> = vec![
        ("PATH".into(), path),
        ("TZ".into(), "UTC".into()),
        ("LC_ALL".into(), "C.UTF-8".into()),
        ("LANG".into(), "C.UTF-8".into()),
        ("HOME".into(), home.into()),
        ("XDG_CONFIG_HOME".into(), home.join(".config").into()),
        ("XDG_DATA_HOME".into(), home.join(".local/share").into()),
        ("XDG_CACHE_HOME".into(), home.join(".cache").into()),
        ("XDG_STATE_HOME".into(), home.join(".local/state").into()),
        ("XDG_RUNTIME_DIR".into(), dirs.runtime.into()),
        ("TMPDIR".into(), dirs.tmp.into()),
    ];
    if let Some(v) = vendor_dir {
        out.push((VENDOR_DIR_ENV.into(), v.into()));
    }
    if let Some(g) = engine_gate {
        out.push((ENGINE_GATE_ENV.into(), g.into()));
    }
    if extra.len() > limits::MAX_ENV {
        return Err(ProcessError::BadScenario {
            reason: format!("more than {} environment entries", limits::MAX_ENV),
        });
    }
    for (i, (name, value)) in extra.iter().enumerate() {
        check_entry("server.env", name, value)?;
        if extra.iter().take(i).any(|(n, _)| n == name) {
            return Err(ProcessError::BadEnv {
                origin: "server.env".to_string(),
                name: name.clone(),
                reason: "given twice".to_string(),
            });
        }
        out.push((name.into(), value.into()));
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn dirs() -> (std::path::PathBuf, std::path::PathBuf, std::path::PathBuf) {
        ("/w/home".into(), "/w/tmp".into(), "/w/run".into())
    }

    fn get<'a>(env: &'a [(OsString, OsString)], name: &str) -> Option<&'a OsString> {
        env.iter().find(|(n, _)| n == name).map(|(_, v)| v)
    }

    #[test]
    fn the_allowlist_and_nothing_else() {
        let (h, t, r) = dirs();
        let d = EnvDirs {
            home: &h,
            tmp: &t,
            runtime: &r,
        };
        let env = build(
            d,
            None,
            None,
            &[("PULSAR_CONSOLE_DEBUG".into(), "1".into())],
        )
        .unwrap();
        let names: Vec<String> = env
            .iter()
            .map(|(n, _)| n.to_string_lossy().into_owned())
            .collect();
        assert_eq!(
            names,
            [
                "PATH",
                "TZ",
                "LC_ALL",
                "LANG",
                "HOME",
                "XDG_CONFIG_HOME",
                "XDG_DATA_HOME",
                "XDG_CACHE_HOME",
                "XDG_STATE_HOME",
                "XDG_RUNTIME_DIR",
                "TMPDIR",
                "PULSAR_CONSOLE_DEBUG"
            ]
        );
        assert_eq!(get(&env, "TZ").unwrap(), "UTC");
        assert_eq!(get(&env, "LC_ALL").unwrap(), "C.UTF-8");
        assert_eq!(get(&env, "HOME").unwrap(), "/w/home");
        assert_eq!(get(&env, "XDG_CACHE_HOME").unwrap(), "/w/home/.cache");
        assert_eq!(get(&env, "TMPDIR").unwrap(), "/w/tmp");
    }

    #[test]
    fn vendor_dir_and_gate_only_when_given() {
        let (h, t, r) = dirs();
        let d = EnvDirs {
            home: &h,
            tmp: &t,
            runtime: &r,
        };
        let env = build(d, Some(Path::new("/v")), Some(Path::new("/w/gate")), &[]).unwrap();
        assert_eq!(get(&env, VENDOR_DIR_ENV).unwrap(), "/v");
        assert_eq!(get(&env, ENGINE_GATE_ENV).unwrap(), "/w/gate");
    }

    #[test]
    fn reserved_malformed_and_repeated_names_are_refused() {
        let (h, t, r) = dirs();
        let d = EnvDirs {
            home: &h,
            tmp: &t,
            runtime: &r,
        };
        for name in [
            "PATH",
            "HOME",
            "LD_PRELOAD",
            "DYLD_INSERT_LIBRARIES",
            "XDG_CONFIG_HOME",
            "PYTHONPATH",
            "FAKE_ENGINE_GATE",
            "lower",
            "1X",
            "",
        ] {
            let err = build(d, None, None, &[(name.to_string(), "x".to_string())]).unwrap_err();
            assert!(matches!(err, ProcessError::BadEnv { .. }), "{name}: {err}");
        }
        let err = build(d, None, None, &[("A".into(), "x\0y".into())]).unwrap_err();
        assert!(err.to_string().contains("NUL"), "{err}");
        let twice = [
            ("A".to_string(), "1".to_string()),
            ("A".to_string(), "2".to_string()),
        ];
        assert!(build(d, None, None, &twice)
            .unwrap_err()
            .to_string()
            .contains("twice"));
    }

    #[test]
    fn a_config_env_block_is_held_to_the_same_rule() {
        // the CNF-02 review point: server.config.env reaches the engine child
        let ok = json!({"env": {"FAKE_ENGINE_IDS": "1,2", "MAYA_GPU_RELEASE_S": 0, "X": true}});
        assert!(check_config_env(ok.as_object().unwrap()).is_ok());
        assert!(check_config_env(json!({}).as_object().unwrap()).is_ok());
        for bad in [
            json!({"env": {"LD_PRELOAD": "/x.so"}}),
            json!({"env": {"HOME": "/elsewhere"}}),
            json!({"env": {"FAKE_ENGINE_GATE": "/g"}}),
            json!({"env": {"PULSAR_CONSOLE_VENDOR_DIR": "/v"}}),
        ] {
            let err = check_config_env(bad.as_object().unwrap()).unwrap_err();
            assert!(
                matches!(&err, ProcessError::BadEnv { origin, .. } if origin == "server.config.env"),
                "{err}"
            );
        }
        let err = check_config_env(json!({"env": ["A"]}).as_object().unwrap()).unwrap_err();
        assert!(matches!(err, ProcessError::BadScenario { .. }));
        let err =
            check_config_env(json!({"env": {"A": {"b": 1}}}).as_object().unwrap()).unwrap_err();
        assert!(matches!(err, ProcessError::BadEnv { .. }));
    }
}
