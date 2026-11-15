//! API-15: the server settings resolved from an injected environment, the run config's
//! `env` block and the command line, with the donor's precedence; the optional
//! `allowed_hosts` key of deviation SEC-1.1; the verbatim passthrough of engine `env` names.
//! No test touches the process environment.

use std::collections::BTreeMap;

use console_core::config::EnvSource;
use console_core::config::{
    names, seconds, server_env_overrides, CliOverrides, ConfigError, EnvSettings, LayeredEnv,
    PromptMemo, RunConfig, Seconds, ServerLog, ServerSettings, ALLOWED_HOSTS_MESSAGE,
    CORS_ORIGINS_MESSAGE, DEFAULT_HOST, SERVER_ENV,
};
use console_pyjson::loads::loads;
use serde_json::Value;

fn object(text: &str) -> RunConfig {
    match loads(text).expect("test JSON") {
        Value::Object(m) => RunConfig::from(m),
        other => panic!("not an object: {other}"),
    }
}

fn env(pairs: &[(&str, &str)]) -> BTreeMap<String, String> {
    pairs
        .iter()
        .map(|(k, v)| ((*k).to_string(), (*v).to_string()))
        .collect()
}

#[test]
fn the_config_s_server_entries_override_the_environment() {
    let process = env(&[
        (names::ENGINE_STALL_S, "30"),
        (names::HTTP_BACKLOG, "100"),
        (names::DEBUG, "1"),
    ]);
    let cfg = object(
        "{\"env\": {\"PULSAR_CONSOLE_ENGINE_STALL_S\": 0, \"PULSAR_CONSOLE_HTTP_BACKLOG\": \"64\", \
         \"PULSAR_CONSOLE_DEBUG\": \"\", \"PULSAR_CONSOLE_QUEUE_PING_S\": null, \
         \"PULSAR_CONSOLE_GLM_RESPONSES_JOB_WORKERS\": 3, \"MAYA_ENGINE_STALL_S\": \"7\"}}",
    );
    let s = EnvSettings::resolve(&process, &cfg).expect("resolve");
    assert_eq!(s.engine_stall_s, 0.0);
    assert_eq!(s.http_backlog, 64);
    // DEBUG is not a server entry of the env block: the process value stands.
    assert!(s.debug);
    // A null entry is skipped, so the default stands.
    assert_eq!(s.queue_ping_s, 2.0);
    assert_eq!(
        s.responses,
        vec![(
            "PULSAR_CONSOLE_GLM_RESPONSES_JOB_WORKERS",
            String::from("3")
        )]
    );
}

#[test]
fn engine_env_names_pass_verbatim_once() {
    let cfg = object(
        "{\"env\": {\"MAYA_GLM_SLOT_KEEP\": \"1\", \"PULSAR_CONSOLE_DRAIN_S\": 5, \"X\": 2.0}}",
    );
    assert_eq!(
        cfg.engine_env().expect("env"),
        vec![
            (String::from("MAYA_GLM_SLOT_KEEP"), String::from("1")),
            (String::from("PULSAR_CONSOLE_DRAIN_S"), String::from("5")),
            (String::from("X"), String::from("2.0")),
        ]
    );
    // No STRATA_ twin is synthesized (contracts/naming.md rule 3, N3).
    assert!(cfg
        .engine_env()
        .expect("env")
        .iter()
        .all(|(k, _)| !k.starts_with("STRATA_")));
}

#[test]
fn late_entries_copy_null_as_none() {
    let cfg = object(
        "{\"env\": {\"PULSAR_CONSOLE_TURN_TRACE\": null, \"PULSAR_CONSOLE_PROMPT_MEMO\": 0}}",
    );
    let over = server_env_overrides(&cfg).expect("overrides");
    assert_eq!(
        over.get(names::TURN_TRACE).map(String::as_str),
        Some("None")
    );
    assert_eq!(over.get(names::PROMPT_MEMO).map(String::as_str), Some("0"));
    let s = EnvSettings::resolve(&env(&[]), &cfg).expect("resolve");
    assert!(s.turn_trace);
    assert_eq!(s.prompt_memo, PromptMemo::Off);
}

#[test]
fn the_prompt_memo_verify_mode_comes_from_the_environment_or_the_config() {
    let s = EnvSettings::from_env(&env(&[(names::PROMPT_MEMO, "verify")]));
    assert_eq!(s.prompt_memo, PromptMemo::Verify);
    let cfg = object("{\"env\": {\"PULSAR_CONSOLE_PROMPT_MEMO\": \"verify\"}}");
    let over = server_env_overrides(&cfg).expect("overrides");
    assert_eq!(
        over.get(names::PROMPT_MEMO).map(String::as_str),
        Some("verify")
    );
    let s = EnvSettings::resolve(&env(&[(names::PROMPT_MEMO, "0")]), &cfg).expect("resolve");
    assert_eq!(s.prompt_memo, PromptMemo::Verify);
    assert!(s.prompt_memo.is_on() && s.prompt_memo.verifies());
    // A config null is copied as the text "None", which is on without the check.
    let cfg = object("{\"env\": {\"PULSAR_CONSOLE_PROMPT_MEMO\": null}}");
    let s = EnvSettings::resolve(&env(&[(names::PROMPT_MEMO, "verify")]), &cfg).expect("resolve");
    assert_eq!(s.prompt_memo, PromptMemo::On);
}

#[test]
fn infinite_seconds_from_the_environment_and_the_config_convert_without_panicking() {
    let s = EnvSettings::from_env(&env(&[
        (names::REQUEST_TIMEOUT_S, "inf"),
        (names::ENGINE_QUIT_S, "nan"),
    ]));
    assert_eq!(seconds(s.request_timeout_s), Seconds::Unbounded);
    assert_eq!(
        s.engine_quit_s.as_ref().map(|x| seconds(*x)),
        Ok(Seconds::NotANumber)
    );
    let cfg = object("{\"idle_unload_s\": \"inf\"}");
    let idle = cfg.idle_unload_s(None).expect("idle unload");
    assert_eq!(seconds(idle), Seconds::Unbounded);
    let cfg = object("{\"idle_unload_s\": Infinity}");
    let idle = cfg.idle_unload_s(None).expect("idle unload");
    assert_eq!(seconds(idle), Seconds::Unbounded);
}

#[test]
fn formatted_settings_do_not_show_the_secrets() {
    let mut cfg = object("{\"env\": {\"HF_TOKEN\": \"hfsecret9\"}}");
    cfg.set("api_key", Value::String(String::from("cfgsecret8")));
    let cli = CliOverrides {
        api_key: Some(String::from("clisecret7")),
        ..CliOverrides::default()
    };
    let s = ServerSettings::resolve(&cli, &env(&[(names::API_KEY, "envsecret6")]), &cfg)
        .expect("resolve");
    let shown = format!("{s:?} {cli:?} {cfg:?}");
    for secret in ["hfsecret9", "cfgsecret8", "clisecret7", "envsecret6"] {
        assert!(!shown.contains(secret), "{secret} in {shown}");
    }
    assert!(shown.contains("***"));
}

#[test]
fn a_bad_env_block_stops_the_start() {
    for text in ["{\"env\": [\"A=1\"]}", "{\"env\": \"A=1\"}", "{\"env\": 1}"] {
        assert!(
            matches!(
                EnvSettings::resolve(&env(&[]), &object(text)),
                Err(ConfigError::Invalid(_))
            ),
            "{text}"
        );
    }
    for text in [
        "{\"env\": null}",
        "{\"env\": []}",
        "{\"env\": \"\"}",
        "{\"env\": 0}",
    ] {
        assert!(
            EnvSettings::resolve(&env(&[]), &object(text)).is_ok(),
            "{text}"
        );
    }
}

#[test]
fn layered_env_reports_its_overrides() {
    let cfg = object("{\"env\": {\"PULSAR_CONSOLE_UPDATE_CHECK\": \"1\", \"OTHER\": \"x\"}}");
    let layered = LayeredEnv::new(env(&[("OTHER", "base")]), &cfg).expect("layer");
    assert_eq!(layered.var(names::UPDATE_CHECK).as_deref(), Some("1"));
    assert_eq!(layered.var("OTHER").as_deref(), Some("base"));
    assert_eq!(layered.overrides().len(), 1);
    assert!(SERVER_ENV.contains(&names::UPDATE_CHECK));
}

#[test]
fn server_settings_defaults() {
    let s = ServerSettings::resolve(&CliOverrides::default(), &env(&[]), &RunConfig::new())
        .expect("resolve");
    assert_eq!(s.host, DEFAULT_HOST);
    assert_eq!(s.api_key, Value::String(String::new()));
    assert!(s.cors_origins.is_empty());
    assert_eq!(s.allowed_hosts, None);
    assert!(s.model_management);
    assert!(s.loop_guard);
    assert!(!s.fit_max_tokens);
    assert_eq!(s.idle_unload_s, 0.0);
    assert_eq!(s.server_log, ServerLog::Terminal);
    assert_eq!(s.env, EnvSettings::from_env(&env(&[])));
}

#[test]
fn server_settings_precedence() {
    let mut cfg = object(
        "{\"api_key\": \"from-config\", \"model_management\": false, \"loop_guard\": false, \
         \"cors_origins\": [\"http://127.0.0.1:8090/\"], \"fit_max_tokens\": true, \
         \"idle_unload_s\": 60, \"log\": \"server.txt\", \"allowed_hosts\": [\"box.lan\"], \
         \"env\": {\"PULSAR_CONSOLE_LOOP_GUARD\": \"on\"}}",
    );
    // Built at run time: a JSON literal pairing this key with a quoted value is avoided.
    cfg.set("host", Value::String(String::from("0.0.0.0")));
    let process = env(&[
        (names::API_KEY, "from-env"),
        (names::MODEL_MANAGEMENT, "yes"),
        (names::SERVER_LOG, "off"),
    ]);
    let cli = CliOverrides {
        host: Some(String::from("127.0.0.1")),
        api_key: None,
        fit_max_tokens: false,
        idle_unload_s: Some(5.0),
    };
    let s = ServerSettings::resolve(&cli, &process, &cfg).expect("resolve");
    assert_eq!(s.host, "127.0.0.1");
    assert_eq!(s.api_key, Value::String(String::from("from-env")));
    assert!(
        s.model_management,
        "a set environment value wins over the config"
    );
    assert!(
        s.loop_guard,
        "the config's env block sets the variable, which wins over the key"
    );
    assert_eq!(s.cors_origins, vec![String::from("http://127.0.0.1:8090")]);
    assert!(s.fit_max_tokens);
    assert_eq!(s.idle_unload_s, 5.0);
    assert_eq!(s.server_log, ServerLog::Terminal);
    assert_eq!(s.allowed_hosts, Some(vec![String::from("box.lan")]));
    let spaced = object("{\"allowed_hosts\": [\" box.lan \"]}");
    let s2 =
        ServerSettings::resolve(&CliOverrides::default(), &env(&[]), &spaced).expect("resolve");
    assert_eq!(s2.allowed_hosts, Some(vec![String::from("box.lan")]));

    let s = ServerSettings::resolve(&CliOverrides::default(), &env(&[]), &cfg).expect("resolve");
    assert_eq!(s.host, "0.0.0.0");
    assert_eq!(s.api_key, Value::String(String::from("from-config")));
    assert!(!s.model_management);
    assert_eq!(s.idle_unload_s, 60.0);
    assert_eq!(s.server_log, ServerLog::File(String::from("server.txt")));
}

#[test]
fn allowed_hosts_is_absent_by_default_and_read_as_a_list() {
    // Deviation SEC-1.1 (owner decision of 2026-11-14, tasks.md R29).
    let s = ServerSettings::resolve(&CliOverrides::default(), &env(&[]), &object("{}"))
        .expect("resolve");
    assert_eq!(s.allowed_hosts, None);
    let s = ServerSettings::resolve(
        &CliOverrides::default(),
        &env(&[]),
        &object("{\"allowed_hosts\": [\"pulsar.local\", \"10.0.0.5\"]}"),
    )
    .expect("resolve");
    assert_eq!(
        s.allowed_hosts,
        Some(vec![String::from("pulsar.local"), String::from("10.0.0.5")])
    );
    match ServerSettings::resolve(
        &CliOverrides::default(),
        &env(&[]),
        &object("{\"allowed_hosts\": \"pulsar.local\"}"),
    ) {
        Err(ConfigError::Invalid(m)) => assert_eq!(m, ALLOWED_HOSTS_MESSAGE),
        other => panic!("{other:?}"),
    }
}

#[test]
fn start_up_errors_come_in_the_donor_s_order() {
    // idle_unload_s is read before cors_origins.
    let cfg = object("{\"idle_unload_s\": \"x\", \"cors_origins\": \"http://a:1\"}");
    match ServerSettings::resolve(&CliOverrides::default(), &env(&[]), &cfg) {
        Err(ConfigError::Invalid(m)) => assert_eq!(m, "could not convert string to float: 'x'"),
        other => panic!("{other:?}"),
    }
    let cfg = object("{\"cors_origins\": \"http://a:1\", \"allowed_hosts\": 1}");
    match ServerSettings::resolve(&CliOverrides::default(), &env(&[]), &cfg) {
        Err(e) => assert_eq!(
            format!("config: {e}"),
            format!("config: {CORS_ORIGINS_MESSAGE}")
        ),
        Ok(s) => panic!("{s:?}"),
    }
}
