//! Provenance: translated from project-maya serve/test_server.py::StallWatchdog::test_the_config_env_reaches_the_server, serve/test_server.py::CorsOptIn::test_the_config_value, serve/test_server.py::ModelManagement::test_on_unless_the_config_turns_it_off, serve/test_server.py::RequestBodies::test_the_listen_backlog, serve/test_models.py::Page::test_secrets_in_the_environment_stay_on_this_pc, serve/test_models.py::Page::test_another_models_settings_leave_which_one_starts_next and serve/test_models.py::Settings::test_glm_written_back_with_the_rest_kept at 7e68a30f (MIT); license text in console/LICENSES/project-maya-MIT.txt.
//!
//! The donor's `MAYA_*` variables are re-expressed under their `PULSAR_CONSOLE_*` names
//! (decision B2, deviation BRAND-1), its `maya-` file names under `pulsar-`, and its
//! fixture's quant label and engine path by neutral ones. Where a
//! donor method also drives an HTTP route or the Models page's settings mapping, which later
//! packages build, only its run-config part is re-expressed here and the method stays
//! pending in the parity ledger; each such test says which part it covers.

use std::collections::BTreeMap;
use std::fs;
use std::path::PathBuf;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::time::{Duration, SystemTime};

use console_core::config::{
    commit, file_times, kept_secret, names, parse_cors_origins, read_document, set_file_times,
    shown_env, write_document, ConfigError, EnvSettings, FileTimes, RunConfig, MASK,
};
use console_pyjson::loads::loads;
use serde_json::{Map, Value};

struct TempDir(PathBuf);

impl TempDir {
    fn new() -> TempDir {
        static NEXT: AtomicUsize = AtomicUsize::new(0);
        let tag = console_pyjson::ids::hex12().unwrap_or_else(|_| String::from("x"));
        let dir = std::env::temp_dir().join(format!(
            "api15-donor-{}-{}-{tag}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir_all(&dir).expect("temporary directory");
        TempDir(dir)
    }
}

impl Drop for TempDir {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

fn value(text: &str) -> Value {
    loads(text).expect("test JSON")
}

fn object(text: &str) -> RunConfig {
    match value(text) {
        Value::Object(m) => RunConfig::from(m),
        other => panic!("not an object: {other}"),
    }
}

/// The donor's `glm_cfg` fixture (serve/test_models.py:29-41), with the pack path given.
fn glm_cfg(pack: &str, models_dir: &str) -> RunConfig {
    let mut cfg = object(
        "{\"exe\": \"/b/engine\", \"args\": [\"--glm-pack\", \"PACK\", \"--max-context\", \"131072\", \
         \"--expert-cache\", \"auto\", \"--prefill\", \"auto\", \"--kv-streaming\", \"on\"], \
         \"model_name\": \"glm-5.3-flash\", \"gpu\": [0, 1], \"port\": 8080, \
         \"vision\": {\"mmproj\": \"/v/mmproj.gguf\"}, \"env\": {\"MAYA_GLM_RAM_HEADROOM_GB\": \"4\"}, \
         \"sampling\": {\"temperature\": 1.0}, \"installer\": {\"models_dir\": \"DIR\", \
         \"quant\": \"Q-M\", \"draft\": \"mtp\", \"written\": \"2026-10-20 09:00\"}}",
    );
    if let Some(Value::Array(args)) = cfg.as_map_mut().get_mut("args") {
        args[1] = Value::String(pack.to_string());
    }
    if let Some(Value::Object(inst)) = cfg.as_map_mut().get_mut("installer") {
        inst.insert(
            String::from("models_dir"),
            Value::String(models_dir.to_string()),
        );
    }
    cfg
}

// Donor: serve/test_server.py::StallWatchdog::test_the_config_env_reaches_the_server
#[test]
fn stall_watchdog_the_config_env_reaches_the_server() {
    // The donor applies the config's env to os.environ and reads module globals; here the
    // settings are resolved from an empty injected environment and the config.
    let cfg = object(
        "{\"env\": {\"PULSAR_CONSOLE_ENGINE_STALL_S\": \"0\", \"PULSAR_CONSOLE_HTTP_BACKLOG\": \"64\"}}",
    );
    let s = EnvSettings::resolve(&BTreeMap::<String, String>::new(), &cfg).expect("resolve");
    assert_eq!((s.engine_stall_s, s.http_backlog), (0.0, 64));
    // The donor's finally block: with no config env the defaults are back.
    let s = EnvSettings::resolve(&BTreeMap::<String, String>::new(), &RunConfig::new())
        .expect("resolve");
    assert_eq!((s.engine_stall_s, s.http_backlog), (90.0, 256));
}

// Donor: serve/test_server.py::CorsOptIn::test_the_config_value
#[test]
fn cors_opt_in_the_config_value() {
    assert_eq!(
        parse_cors_origins(None).expect("none"),
        Vec::<String>::new()
    );
    assert_eq!(
        parse_cors_origins(Some(&value("null"))).expect("null"),
        Vec::<String>::new()
    );
    assert_eq!(
        parse_cors_origins(Some(&value("[]"))).expect("[]"),
        Vec::<String>::new()
    );
    assert_eq!(
        parse_cors_origins(Some(&value("[\" http://a:1/ \", \"*\"]"))).expect("list"),
        vec![String::from("http://a:1"), String::from("*")]
    );
    for bad in ["\"http://a:1\"", "[1]", "[\"\"]", "{\"a\": 1}"] {
        assert!(
            matches!(
                parse_cors_origins(Some(&value(bad))),
                Err(ConfigError::Invalid(_))
            ),
            "{bad}"
        );
    }
}

// Donor: serve/test_server.py::ModelManagement::test_on_unless_the_config_turns_it_off
#[test]
fn model_management_on_unless_the_config_turns_it_off() {
    // Setting part only. The routes' 404 while it is off (the first three assertions of the
    // donor method) belong to the route package; the ledger row stays pending.
    let no_env: Option<&str> = None;
    assert!(object("{}").model_management(no_env));
    assert!(object("{\"model_management\": true}").model_management(no_env));
    assert!(!object("{\"model_management\": false}").model_management(no_env));
    assert!(!object("{\"model_management\": true}").model_management(Some("0")));
    assert!(object("{}").model_management(Some("on")));
    // The name the environment value is read from.
    let s = EnvSettings::from_env(&[(names::MODEL_MANAGEMENT, "0")]);
    assert_eq!(s.model_management.as_deref(), Some("0"));
    let legacy = EnvSettings::from_env(&[("MAYA_MODEL_MANAGEMENT", "0")]);
    assert_eq!(legacy.model_management, None);
}

// Donor: serve/test_server.py::RequestBodies::test_the_listen_backlog
#[test]
fn request_bodies_the_listen_backlog_setting() {
    // Setting part only: the default backlog the listener is given. The listener itself is
    // API-02's; the ledger row stays pending until the two are joined.
    let s = EnvSettings::from_env(&BTreeMap::<String, String>::new());
    assert!(s.http_backlog >= 256);
}

// Donor: serve/test_models.py::Page::test_secrets_in_the_environment_stay_on_this_pc
#[test]
fn page_secrets_in_the_environment_stay_on_this_pc() {
    // Run-config part: the masked copy the page gets, the mask sent back keeping the stored
    // value, and a new value replacing it, through the store. The GET and POST routes are
    // OPS-05's and OPS-07's; the ledger row stays pending.
    let dir = TempDir::new();
    let path = dir.0.join("pulsar-glm-m.json");
    let mut cfg = glm_cfg("/p/pack", "/p");
    cfg.set(
        "env",
        value("{\"HF_TOKEN\": \"hf_secret\", \"MAYA_GLM_RAM_HEADROOM_GB\": \"4\"}"),
    );
    write_document(&path, &cfg).expect("write");

    let stored = read_document(&path);
    let shown = shown_env(stored.env_block().expect("env"));
    let shown_text = console_pyjson::dumps::to_wire(&Value::Object(shown.clone())).expect("dumps");
    assert!(!shown_text.contains("hf_secret"));
    assert_eq!(
        shown.get("HF_TOKEN"),
        Some(&Value::String(String::from(MASK)))
    );

    // A save that sends the page's masked env back keeps the secret.
    let mut kept = Map::new();
    for (k, v) in &shown {
        kept.insert(
            k.clone(),
            kept_secret(stored.env_block().expect("env"), k, v),
        );
    }
    let mut new = stored.clone();
    new.set("env", Value::Object(kept));
    commit(&path, &stored, new, |_| Value::Null).expect("save");
    let reread = read_document(&path);
    assert_eq!(
        reread.get("env").and_then(|e| e.get("HF_TOKEN")),
        Some(&Value::String(String::from("hf_secret")))
    );
    assert!(!console_pyjson::dumps::to_wire(&Value::Object(shown_env(
        reread.env_block().expect("env")
    )))
    .expect("dumps")
    .contains("hf_secret"));

    // A new value replaces it.
    let sent = Value::String(String::from("hf_new"));
    let mut env = Map::new();
    env.insert(
        String::from("HF_TOKEN"),
        kept_secret(reread.env_block().expect("env"), "HF_TOKEN", &sent),
    );
    let mut new = reread.clone();
    new.set("env", Value::Object(env));
    commit(&path, &reread, new, |_| Value::Null).expect("save");
    assert_eq!(
        read_document(&path).get("env"),
        Some(&value("{\"HF_TOKEN\": \"hf_new\"}"))
    );
}

// Donor: serve/test_models.py::Page::test_another_models_settings_leave_which_one_starts_next
#[test]
fn page_another_models_settings_leave_which_one_starts_next() {
    // Run-config part: a save of another model's config keeps its modification time (still
    // the one used longest ago). The route and the "tp" setting mapping are OPS-05's; the
    // ledger row stays pending.
    let dir = TempDir::new();
    let other = dir.0.join("pulsar-gguf-q8.json");
    let old_doc = object(
        "{\"exe\": \"/b/engine-ds4\", \"args\": [\"--pack\", \"/p\", \"--max-context\", \"65536\", \"--tp\", \"2\"], \
         \"model_name\": \"deepseek-v4.1-flash\", \"gpu\": [0, 1]}",
    );
    write_document(&other, &old_doc).expect("write");
    let old = SystemTime::now() - Duration::from_secs(1000);
    set_file_times(
        &other,
        FileTimes {
            accessed: old,
            modified: old,
        },
    )
    .expect("utime");
    let mut new = old_doc.clone();
    new.set(
        "args",
        value("[\"--pack\", \"/p\", \"--max-context\", \"65536\", \"--tp\", \"1\"]"),
    );
    let out = commit(&other, &old_doc, new, |_| Value::Null).expect("save");
    assert!(out.changed);
    let args = read_document(&other).get("args").cloned().expect("args");
    assert_eq!(args.get(5), Some(&Value::String(String::from("1"))));
    let modified = file_times(&other).expect("times").modified;
    let delta = modified
        .duration_since(old)
        .unwrap_or_else(|e| e.duration());
    assert!(delta <= Duration::from_secs(1));
}

// Donor: serve/test_models.py::Settings::test_glm_written_back_with_the_rest_kept
#[test]
fn settings_glm_written_back_with_the_rest_kept() {
    // Preservation part: the keys the settings do not touch (sampling, port, model name,
    // installer, unknown keys) are kept, in order, when the config is written back. The
    // argument and GPU mapping (`apply`) is OPS-05's; the ledger row stays pending.
    let dir = TempDir::new();
    let path = dir.0.join("pulsar-glm-m.json");
    let cfg = glm_cfg("/p/GLM-5.3-Flash/Q-M/pack", "/p");
    write_document(&path, &cfg).expect("write");
    let read = read_document(&path);
    let mut new = read.clone();
    new.set(
        "args",
        value("[\"--glm-pack\", \"/p/GLM-5.3-Flash/Q-M/pack\", \"--max-context\", \"65536\"]"),
    );
    new.set("gpu", value("[1]"));
    new.set("env", value("{\"A\": \"1\"}"));
    new.as_map_mut().shift_remove("vision");
    commit(&path, &read, new, |_| Value::Null).expect("save");
    let back = read_document(&path);
    assert_eq!(
        (
            back.get("gpu"),
            back.get("env"),
            back.get("sampling"),
            back.get("port")
        ),
        (
            Some(&value("[1]")),
            Some(&value("{\"A\": \"1\"}")),
            Some(&value("{\"temperature\": 1.0}")),
            Some(&Value::from(8080))
        )
    );
    assert!(back.get("vision").is_none());
    let keys: Vec<&str> = back.as_map().keys().map(String::as_str).collect();
    assert_eq!(
        keys,
        [
            "exe",
            "args",
            "model_name",
            "gpu",
            "port",
            "env",
            "sampling",
            "installer"
        ]
    );
    assert!(fs::read_to_string(&path)
        .expect("read")
        .contains("\"temperature\": 1.0"));
}
