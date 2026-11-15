//! CNF-07: the files the harness writes for a scenario before its server starts.
//!
//! These tests start no process and open no socket. They read the CNF-02 sample
//! scenario that transcribes the donor's `fake_config` and check the generated tokenizer
//! directory and run config against it; the shape is the donor's, from project-maya
//! serve/test_stop.py:44-68 at 7e68a30f.

use std::fs;
use std::path::{Path, PathBuf};

use console_conformance::process::{
    ProcessError, ScenarioFiles, Workdir, CONFIG_FILE_NAME, TOKENIZER_DIR_NAME,
};
use console_conformance::scenario::{Scenario, Substitutions};
use serde_json::Value;

fn sample(name: &str) -> Scenario {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests/data/scenarios")
        .join(format!("{name}.json"));
    match Scenario::from_path(&path) {
        Ok(s) => s,
        Err(e) => panic!("{}: {e}", path.display()),
    }
}

fn expanded(s: &Scenario, dir: &Workdir) -> Scenario {
    let tmp = dir.root().to_str().expect("UTF-8 temp path").to_string();
    let subs = Substitutions::new().with_tmp(&tmp).expect("tmp token");
    s.expand(&subs).expect("expansion")
}

fn read_json(p: &Path) -> Value {
    serde_json::from_str(&fs::read_to_string(p).unwrap()).unwrap()
}

#[test]
fn a_line_scenario_gets_the_donor_fake_config_shape() {
    let dir = Workdir::create(None).unwrap();
    let scenario = expanded(&sample("stop-on-sigterm"), &dir);
    let exe = Path::new("/opt/fakes/fake-multi-engine");
    let files = ScenarioFiles::write(&scenario, &dir.data(), Some(exe)).unwrap();

    let tok = files.tokenizer_dir.clone().unwrap();
    assert_eq!(tok, dir.data().join(TOKENIZER_DIR_NAME));
    let vocab = read_json(&tok.join("vocab.json"));
    let vocab = vocab.as_object().unwrap();
    assert_eq!(vocab.len(), 258);
    assert_eq!(vocab["<|im_end|>"], 256);
    assert_eq!(vocab["</think>"], 257);
    assert_eq!(fs::read_to_string(tok.join("merges.txt")).unwrap(), "a b");

    let config_path = files.config_path.clone().unwrap();
    assert_eq!(config_path, dir.data().join(CONFIG_FILE_NAME));
    let config = read_json(&config_path);
    assert_eq!(config["exe"], "/opt/fakes/fake-multi-engine");
    assert_eq!(config["args"], serde_json::json!(["1"]));
    assert_eq!(config["tokenizer"], tok.to_str().unwrap());
    assert_eq!(config["model_name"], "fake");
    let log = format!("{}/engine.log", dir.root().display());
    assert_eq!(config["log"], log.as_str());
    assert_eq!(
        files.config_args(),
        vec![
            std::ffi::OsString::from("--config"),
            config_path.into_os_string()
        ]
    );
}

#[test]
fn a_line_scenario_needs_the_fake_engine_executable() {
    let dir = Workdir::create(None).unwrap();
    let scenario = expanded(&sample("stop-on-sigterm"), &dir);
    let err = ScenarioFiles::write(&scenario, &dir.data(), None).unwrap_err();
    assert!(matches!(err, ProcessError::BadScenario { .. }), "{err}");
}

#[test]
fn an_unexpanded_token_in_the_config_is_refused() {
    let dir = Workdir::create(None).unwrap();
    let scenario = sample("stop-on-sigterm");
    let err = ScenarioFiles::write(&scenario, &dir.data(), Some(Path::new("/x"))).unwrap_err();
    assert!(err.to_string().contains("{{tmp}}"), "{err}");
}

fn mock_scenario(server: &str) -> Scenario {
    let text = format!(
        r#"{{
  "id": "harness-files",
  "engine": {{"kind": "mock", "tokenizer": {{"kind": "byte"}}, "script": ["Hi"]}},
  "template": "plain",
  "server": {server},
  "steps": [{{"request": {{"method": "GET", "path": "/health"}}}}],
  "observe": {{"http": true}}
}}"#
    );
    match Scenario::from_json_str(&text) {
        Ok(s) => s,
        Err(e) => panic!("{e}\n{text}"),
    }
}

#[test]
fn a_mock_scenario_writes_a_config_only_when_it_has_one() {
    let dir = Workdir::create(None).unwrap();
    let files = ScenarioFiles::write(&mock_scenario("{}"), &dir.data(), None).unwrap();
    assert_eq!(files, ScenarioFiles::default());
    assert!(files.config_args().is_empty());

    let dir = Workdir::create(None).unwrap();
    let s = mock_scenario(
        r#"{"config": {"model_name": "m", "env": {"FAKE_ENGINE_IDS": "1,2"}},
            "data_dir": {"notes/a.txt": "text", "b.json": {"k": [1]}}}"#,
    );
    let files = ScenarioFiles::write(&s, &dir.data(), None).unwrap();
    assert_eq!(files.tokenizer_dir, None);
    let config = read_json(files.config_path.as_ref().unwrap());
    assert_eq!(config["env"]["FAKE_ENGINE_IDS"], "1,2");
    assert_eq!(
        files.data_files,
        vec![dir.data().join("notes/a.txt"), dir.data().join("b.json")]
    );
    assert_eq!(
        fs::read_to_string(dir.data().join("notes/a.txt")).unwrap(),
        "text"
    );
    assert_eq!(
        read_json(&dir.data().join("b.json")),
        serde_json::json!({"k": [1]})
    );
}

#[test]
fn a_reserved_name_in_the_config_env_block_is_refused() {
    // the CNF-02 review point: server.config.env reaches the engine child through the
    // server, so it is held to the harness's reserved-environment rule
    for name in [
        "LD_PRELOAD",
        "DYLD_INSERT_LIBRARIES",
        "HOME",
        "PATH",
        "FAKE_ENGINE_GATE",
        "XDG_DATA_HOME",
        "PYTHONPATH",
    ] {
        let dir = Workdir::create(None).unwrap();
        let s = mock_scenario(&format!(r#"{{"config": {{"env": {{"{name}": "x"}}}}}}"#));
        let err = ScenarioFiles::write(&s, &dir.data(), None).unwrap_err();
        assert!(
            matches!(&err, ProcessError::BadEnv { origin, name: n, .. } if origin == "server.config.env" && n == name),
            "{name}: {err}"
        );
        assert!(!dir.data().join(CONFIG_FILE_NAME).exists());
    }
}

#[test]
fn a_data_file_may_not_take_a_harness_path() {
    for path in [CONFIG_FILE_NAME, "tokenizer/vocab.json"] {
        let dir = Workdir::create(None).unwrap();
        let s = mock_scenario(&format!(r#"{{"data_dir": {{"{path}": "x"}}}}"#));
        let err = ScenarioFiles::write(&s, &dir.data(), None).unwrap_err();
        assert!(
            matches!(err, ProcessError::BadScenario { .. }),
            "{path}: {err}"
        );
    }
}

fn line_scenario(engine_env: &str, server: &str) -> Scenario {
    let text = format!(
        r#"{{
  "id": "harness-line-files",
  "engine": {{"kind": "line", "fake": "glm", "tokenizer": {{"kind": "bpe-bytes", "added": {{"<|im_end|>": 256}}}}, "env": {engine_env}}},
  "template": "plain",
  "server": {server},
  "steps": [{{"signal": "SIGTERM"}}],
  "observe": {{"exit": true}}
}}"#
    );
    match Scenario::from_json_str(&text) {
        Ok(s) => s,
        Err(e) => panic!("{e}\n{text}"),
    }
}

#[test]
fn the_engine_env_merges_after_the_config_env() {
    let dir = Workdir::create(None).unwrap();
    let s = line_scenario(
        r#"{"FAKE_ENGINE_IDS": "5,6"}"#,
        r#"{"config": {"env": {"MAYA_GPU_RELEASE_S": "0"}}}"#,
    );
    let files = ScenarioFiles::write(&s, &dir.data(), Some(Path::new("/f"))).unwrap();
    let config = read_json(files.config_path.as_ref().unwrap());
    let env = config["env"].as_object().unwrap();
    let names: Vec<&String> = env.keys().collect();
    assert_eq!(names, ["MAYA_GPU_RELEASE_S", "FAKE_ENGINE_IDS"]);
    assert_eq!(config["args"], serde_json::json!([]));

    let dir = Workdir::create(None).unwrap();
    let both = line_scenario(
        r#"{"FAKE_ENGINE_IDS": "5"}"#,
        r#"{"config": {"env": {"FAKE_ENGINE_IDS": "6"}}}"#,
    );
    let err = ScenarioFiles::write(&both, &dir.data(), Some(Path::new("/f"))).unwrap_err();
    assert!(err.to_string().contains("FAKE_ENGINE_IDS"), "{err}");
}
