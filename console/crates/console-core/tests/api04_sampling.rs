//! Sampling normalization of work package API-04: the semantic rules of the engine line's
//! sampling keys, the shared defaults, the run-config `sampling` block and the precedence
//! between them.
//!
//! Provenance: translated from project-maya serve/test_server.py::SamplingKeys at 7e68a30f (MIT); license text in console/LICENSES/project-maya-MIT.txt.
//! Provenance: translated from project-maya serve/test_server.py::SharedSettings at 7e68a30f (MIT); license text in console/LICENSES/project-maya-MIT.txt.
//!
//! The donor asserts the sampling keys on the engine line that its `sampling_keys` writes.
//! The line's encoder is ENG-03's (milestone M3); here the same expectations are asserted
//! on the ordered keys of [`ResolvedSampling`], written with the line's spacing and
//! Python's float `repr` by the `line` helper below. The joint test through the encoder,
//! and the HTTP halves of the SharedSettings methods (API-13, API-08), come with those
//! packages.

use console_core::request::{
    clean_shared_defaults, effort_level, effort_name, with_shared, Dialect, RequestError,
    SharedDefaults, EFFORT_WORDS,
};
use console_core::sampling::{
    effective_sampling, run_sampling_defaults, sampling_defaults_from_config, DefaultsOrigin,
    ResolvedSampling, PENALTY_WINDOW_MAX,
};
use serde_json::{Map, Value};

fn obj(src: &str) -> Map<String, Value> {
    match console_pyjson::loads::loads(src) {
        Ok(Value::Object(m)) => m,
        other => panic!("test input {src:?} is not an object: {other:?}"),
    }
}

fn val(src: &str) -> Value {
    match console_pyjson::loads::loads(src) {
        Ok(v) => v,
        Err(e) => panic!("test input {src:?} does not parse: {e}"),
    }
}

/// The sampling keys of a sampling map, as the engine line spaces them.
fn line(src: &str) -> String {
    line_of(&obj(src))
}

fn line_of(m: &Map<String, Value>) -> String {
    let resolved = match ResolvedSampling::resolve(m) {
        Ok(r) => r,
        Err(e) => panic!("{m:?} does not resolve: {e}"),
    };
    resolved
        .keys()
        .into_iter()
        .map(|(k, v)| format!(" {k}={v}"))
        .collect()
}

fn keys(src: &str) -> Vec<String> {
    line(src).split_whitespace().map(String::from).collect()
}

fn shared(src: &str) -> SharedDefaults {
    match SharedDefaults::from_value(&val(src)) {
        Ok(s) => s,
        Err(e) => panic!("{src} refused: {e}"),
    }
}

fn invalid(m: &str) -> RequestError {
    RequestError::Invalid(m.to_string())
}

// Donor: serve/test_server.py::SamplingKeys::test_top_k
#[test]
fn top_k() {
    assert!(keys(r#"{"temperature": 0.7, "top_k": 10}"#).contains(&"top_k=10".into()));
    assert!(keys(r#"{"temperature": 0.7, "top_k": 64}"#).contains(&"top_k=64".into()));
    assert!(keys(r#"{"temperature": 0.7, "top_k": 0}"#).contains(&"top_k=64".into()));
    assert!(keys(r#"{"temperature": 0.7, "top_k": 100}"#).contains(&"top_k=64".into()));
    for bad in ["-1", "true", "2.5", "\"20\""] {
        let k = keys(&format!("{{\"temperature\": 0.7, \"top_k\": {bad}}}"));
        assert!(!k.iter().any(|x| x.starts_with("top_k=")), "{bad}: {k:?}");
    }
}

// Donor: serve/test_server.py::SamplingKeys::test_penalty_window
#[test]
fn penalty_window() {
    assert!(keys(r#"{"presence_penalty": 1.5}"#).contains(&"penalty_last_n=64".into()));
    assert!(
        keys(r#"{"repetition_penalty": 1.1, "penalty_last_n": 4096}"#)
            .contains(&"penalty_last_n=4096".into())
    );
    assert!(!keys(r#"{"temperature": 0.7}"#)
        .iter()
        .any(|k| k.starts_with("penalty")));
}

// Donor: serve/test_server.py::SamplingKeys::test_penalty_window_llama_cpp
#[test]
fn penalty_window_llama_cpp() {
    let k = keys(r#"{"temperature": 0.7, "repetition_penalty": 1.3, "penalty_last_n": 0}"#);
    assert!(!k.iter().any(|x| x.starts_with("penalty")));
    assert_eq!(
        line(r#"{"temperature": 0, "repetition_penalty": 1.3, "penalty_last_n": 0}"#),
        " temperature=0"
    );
    assert!(
        keys(r#"{"temperature": 0, "repetition_penalty": 1.3, "penalty_last_n": -1}"#)
            .contains(&format!("penalty_last_n={PENALTY_WINDOW_MAX}"))
    );
    assert!(keys(r#"{"temperature": 0, "repetition_penalty": 1.3}"#)
        .contains(&"penalty_last_n=64".into()));
}

// Donor: serve/test_server.py::SamplingKeys::test_penalties_greedy
#[test]
fn penalties_greedy() {
    let k = keys(
        r#"{"temperature": 0, "repetition_penalty": 1.3, "penalty_last_n": 128, "frequency_penalty": 0.5}"#,
    );
    assert_eq!(k[0], "temperature=0");
    for want in [
        "penalty_repeat=1.3",
        "penalty_freq=0.5",
        "penalty_last_n=128",
    ] {
        assert!(k.contains(&want.to_string()), "{want}: {k:?}");
    }
    assert!(keys(r#"{"temperature": 0, "presence_penalty": 0.4}"#)
        .contains(&"penalty_last_n=64".into()));
    // Neutral penalties, or none: the greedy line is the one it always was.
    let plain = line(r#"{"temperature": 0, "top_p": 0.9}"#);
    assert_eq!(plain, " temperature=0");
    for neutral in [
        r#""repetition_penalty": 1.0"#,
        r#""frequency_penalty": 0, "presence_penalty": 0.0"#,
        r#""penalty_last_n": 64"#,
    ] {
        let src = format!("{{\"temperature\": 0, \"top_p\": 0.9, {neutral}}}");
        assert_eq!(line(&src), plain, "{neutral}");
    }
    // A sampled request's line.
    assert_eq!(
        line(r#"{"temperature": 0.7, "repetition_penalty": 1.1, "seed": 5}"#),
        " temperature=0.7 penalty_repeat=1.1 penalty_last_n=64 seed=5"
    );
}

#[test]
fn semantic_rules_of_each_sampler_key() {
    // top_p only below 1; min_p only in (0, 1]; seed only above 0; ints as floats.
    assert_eq!(
        line(r#"{"temperature": 1, "top_p": 1, "min_p": 1, "seed": 0}"#),
        " temperature=1.0 min_p=1.0"
    );
    assert_eq!(
        line(r#"{"temperature": 2, "top_p": 0.95, "top_k": 1, "min_p": 0, "seed": -3}"#),
        " temperature=2.0 top_p=0.95 top_k=1"
    );
    // Greedy suppresses the sampler keys but keeps the penalties, in the line's order.
    assert_eq!(
        line(
            r#"{"seed": 9, "temperature": -1, "top_k": 5, "min_p": 0.1, "presence_penalty": 0.2,
                "frequency_penalty": 0.3, "repetition_penalty": 1.2}"#
        ),
        " temperature=0 penalty_repeat=1.2 penalty_freq=0.3 penalty_present=0.2 penalty_last_n=64"
    );
    // No temperature at all: not greedy, and the other keys go.
    assert_eq!(
        line(r#"{"top_k": 70, "seed": 12345678901234567890123}"#),
        " top_k=64 seed=12345678901234567890123"
    );
    // A bool is an int in Python: `seed=True` for true (True > 0), nothing for false;
    // a bool top_k is left out, a bool temperature or min_p is read as 1.0.
    assert_eq!(
        line(r#"{"temperature": true, "top_k": true, "min_p": true, "seed": true}"#),
        " temperature=1.0 min_p=1.0 seed=True"
    );
    assert_eq!(
        line(r#"{"temperature": 0.5, "seed": false}"#),
        " temperature=0.5"
    );
    let r = ResolvedSampling::resolve(&obj(r#"{"temperature": 0.0, "top_p": 0.5}"#)).unwrap();
    assert!(r.greedy);
    assert_eq!((r.temperature, r.top_p), (None, None));
    // An integer too large for a float raises Python's OverflowError.
    let huge = format!("{{\"temperature\": 1{}}}", "0".repeat(400));
    assert_eq!(
        ResolvedSampling::resolve(&obj(&huge)),
        Err(RequestError::Overflow(
            "int too large to convert to float".into()
        ))
    );
}

// Donor: serve/test_server.py::SharedSettings::test_other_apps_get_the_chat_settings
// (the core half: the settings checked, applied to a client that sets nothing, its own
// values winning, and the thinking level filled per dialect)
#[test]
fn other_apps_get_the_chat_settings() {
    let d = r#"{"temperature": 0.3, "top_p": 0.9, "top_k": 10, "min_p": 0.05, "seed": 7, "max_tokens": 77,
                "reasoning_effort": "low", "experimental_speed_projection": false}"#;
    let s = shared(d);
    assert!(!s.is_empty());
    let sent = val(d);
    let plain = obj(r#"{"model": "m", "messages": [{"role": "user", "content": "hi"}]}"#);
    let (req, _) = with_shared(&plain, Dialect::OpenAi, &s, false);
    let got = effective_sampling(&Map::new(), &s, &req);
    for k in [
        "temperature",
        "top_p",
        "top_k",
        "min_p",
        "seed",
        "experimental_speed_projection",
    ] {
        assert_eq!(got[k], sent[k], "{k}");
    }
    assert_eq!(req["max_tokens"], val("77"));
    let own = obj(r#"{"model": "m", "messages": [], "temperature": 0.9, "max_tokens": 5}"#);
    let (req, _) = with_shared(&own, Dialect::OpenAi, &s, false);
    let got = effective_sampling(&Map::new(), &s, &req);
    assert_eq!(got["temperature"].to_string(), "0.9");
    assert_eq!(req["max_tokens"], val("5"));
    let (r, _) = with_shared(&obj(r#"{"messages": []}"#), Dialect::OpenAi, &s, false);
    assert_eq!(r["reasoning_effort"], val("\"low\""));
    let (r, _) = with_shared(
        &obj(r#"{"reasoning_effort": "high"}"#),
        Dialect::OpenAi,
        &s,
        false,
    );
    assert_eq!(r["reasoning_effort"], val("\"high\""));
    let (r, _) = with_shared(&obj("{}"), Dialect::Anthropic, &s, false);
    assert_eq!(r["output_config"], val(r#"{"effort": "low"}"#));
}

// Donor: serve/test_server.py::SharedSettings::test_top_k_and_min_p_off_win_over_the_run_config
// (the core half: the request's 0s win over the run config's, and the line has no min_p
// and top-k's widest list; the shared settings take top_k 0)
#[test]
fn top_k_and_min_p_off_win_over_the_run_config() {
    let config = obj(r#"{"temperature": 1.0, "top_p": 0.95, "top_k": 40, "min_p": 0.02}"#);
    let req = obj(r#"{"temperature": 1.0, "top_p": 0.95, "top_k": 0, "min_p": 0}"#);
    let got = effective_sampling(&config, &SharedDefaults::new(), &req);
    assert_eq!(
        (got["top_k"].to_string(), got["min_p"].to_string()),
        ("0".into(), "0".into())
    );
    let l = line_of(&got);
    assert!(!l.contains("min_p="), "{l}");
    assert!(l.contains("top_k=64"), "{l}");
    let s = shared(r#"{"temperature": 1.0, "top_p": 0.9, "top_k": 0, "min_p": 0}"#);
    assert_eq!(s.as_map()["top_k"].to_string(), "0");
}

// Donor: serve/test_server.py::SharedSettings::test_penalties_only_when_set
// (the core half)
#[test]
fn penalties_only_when_set() {
    let none = effective_sampling(
        &Map::new(),
        &SharedDefaults::new(),
        &obj(r#"{"temperature": 1.0}"#),
    );
    assert!(!line_of(&none).contains("penalty"));
    let own = obj(
        r#"{"temperature": 1.0, "repetition_penalty": 1.2, "frequency_penalty": 0.3, "presence_penalty": 0.4}"#,
    );
    let l = line_of(&effective_sampling(
        &Map::new(),
        &SharedDefaults::new(),
        &own,
    ));
    for k in [
        "penalty_repeat=1.2",
        "penalty_freq=0.3",
        "penalty_present=0.4",
        "penalty_last_n=64",
    ] {
        assert!(l.contains(k), "{k}: {l}");
    }
    let s = shared(r#"{"temperature": 1.0, "repetition_penalty": 1.1, "presence_penalty": 0.5}"#);
    assert_eq!(s.as_map()["repetition_penalty"].to_string(), "1.1");
    assert_eq!(s.as_map()["presence_penalty"].to_string(), "0.5");
    let l = line_of(&effective_sampling(&Map::new(), &s, &obj("{}")));
    assert!(l.contains("penalty_repeat=1.1"), "{l}");
    assert_eq!(
        SharedDefaults::from_value(&val(r#"{"repetition_penalty": 0}"#)),
        Err(invalid("repetition_penalty: above 0, at most 10 (1 = off)"))
    );
}

// Donor: serve/test_server.py::SharedSettings::test_off_again
// (the core half)
#[test]
fn off_again() {
    let s = shared(r#"{"temperature": 0.3}"#);
    assert!(effective_sampling(&Map::new(), &s, &obj("{}")).contains_key("temperature"));
    let off = shared("null");
    assert!(off.is_empty());
    let got = effective_sampling(&Map::new(), &off, &obj(r#"{"messages": []}"#));
    assert!(!got.contains_key("temperature"));
}

/// Every message of the donor's `clean_shared_defaults`, with an input that triggers it.
#[test]
fn every_shared_defaults_message_with_its_input() {
    let cases: &[(&str, String)] = &[
        ("[1]", "defaults must be an object".into()),
        ("\"x\"", "defaults must be an object".into()),
        (
            r#"{"reasoning_effort": "extreme"}"#,
            format!("reasoning_effort: {EFFORT_WORDS}"),
        ),
        (
            r#"{"reasoning_effort": true}"#,
            format!("reasoning_effort: {EFFORT_WORDS}"),
        ),
        (
            r#"{"reasoning_effort": 3}"#,
            format!("reasoning_effort: {EFFORT_WORDS}"),
        ),
        (r#"{"temperature": 9}"#, "temperature: 0..2".into()),
        (r#"{"temperature": "1"}"#, "temperature: 0..2".into()),
        (r#"{"temperature": true}"#, "temperature: 0..2".into()),
        (r#"{"temperature": NaN}"#, "temperature: 0..2".into()),
        (r#"{"top_p": 0}"#, "top_p: 0 < top_p <= 1".into()),
        (r#"{"min_p": 1}"#, "min_p: 0 <= min_p < 1".into()),
        (r#"{"top_k": 65}"#, "top_k: an integer 0..64".into()),
        (r#"{"top_k": 2.5}"#, "top_k: an integer 0..64".into()),
        (
            r#"{"top_k": NaN}"#,
            "cannot convert float NaN to integer".into(),
        ),
        (r#"{"seed": 0}"#, "seed: a positive integer".into()),
        (
            r#"{"max_tokens": 1.5}"#,
            "max_tokens: a positive integer".into(),
        ),
        (
            r#"{"repetition_penalty": 10.5}"#,
            "repetition_penalty: above 0, at most 10 (1 = off)".into(),
        ),
        (
            r#"{"frequency_penalty": -2.5}"#,
            "frequency_penalty: -2..2 (0 = off)".into(),
        ),
        (
            r#"{"presence_penalty": "0"}"#,
            "presence_penalty: -2..2 (0 = off)".into(),
        ),
        (
            r#"{"experimental_speed_projection": 1}"#,
            "experimental_speed_projection: true or false".into(),
        ),
        (
            r#"{"penalty_last_n": 64}"#,
            "unknown setting 'penalty_last_n'".into(),
        ),
        (r#"{"it's": 1}"#, "unknown setting \"it's\"".into()),
    ];
    for (src, msg) in cases {
        assert_eq!(clean_shared_defaults(&val(src)), Err(invalid(msg)), "{src}");
    }
    assert_eq!(
        clean_shared_defaults(&val(r#"{"seed": -Infinity}"#)),
        Err(RequestError::Overflow(
            "cannot convert float infinity to integer".into()
        ))
    );
}

#[test]
fn shared_defaults_keep_their_order_and_python_types() {
    let s = shared(
        r#"{"seed": 7.0, "temperature": 1, "max_tokens": 10000000000000000000000, "top_k": 0,
            "reasoning_effort": " Maximum ", "frequency_penalty": -2, "top_p": null, "min_p": "",
            "experimental_speed_projection": true}"#,
    );
    let text: Vec<String> = s.as_map().iter().map(|(k, v)| format!("{k}={v}")).collect();
    assert_eq!(
        text,
        [
            "seed=7",
            "temperature=1.0",
            "max_tokens=10000000000000000000000",
            "top_k=0",
            "reasoning_effort=\"max\"",
            "frequency_penalty=-2.0",
            "experimental_speed_projection=true",
        ]
    );
    assert_eq!(shared("{}").to_value(), val("{}"));
    // False is the level "none"; MiniMax's own words are kept by name.
    assert_eq!(
        shared(r#"{"reasoning_effort": false}"#).as_map()["reasoning_effort"],
        val("\"none\"")
    );
    assert_eq!(
        shared(r#"{"reasoning_effort": "MEDIUM"}"#).as_map()["reasoning_effort"],
        val("\"medium\"")
    );
    for (word, level, name) in [
        ("off", "none", "none"),
        ("medium", "high", "medium"),
        ("xhigh", "max", "xhigh"),
        ("default", "auto", "auto"),
        ("minimal", "none", "none"),
    ] {
        let v = Value::String(word.into());
        assert_eq!(
            (effort_level(&v), effort_name(&v)),
            (Some(level), Some(name)),
            "{word}"
        );
    }
    assert_eq!(effort_level(&Value::String(String::new())), None);
}

#[test]
fn with_shared_fills_only_what_the_request_leaves_out() {
    let s = shared(r#"{"reasoning_effort": "none", "max_tokens": 50}"#);
    // Anthropic: level none is thinking disabled; a request with its own thinking keeps it.
    let (r, flags) = with_shared(&obj(r#"{"max_tokens": 0}"#), Dialect::Anthropic, &s, true);
    assert_eq!(r["thinking"], val(r#"{"type": "disabled"}"#));
    assert_eq!(r["max_tokens"], val("50"));
    assert!(flags.level_shared);
    let (r, flags) = with_shared(
        &obj(r#"{"output_config": {"effort": "high"}}"#),
        Dialect::Anthropic,
        &s,
        true,
    );
    assert!(!r.contains_key("thinking"));
    assert!(!flags.level_shared);
    // OpenAI: chat_template_kwargs naming either key keeps the request's own level.
    for own in [
        r#"{"chat_template_kwargs": {"enable_thinking": false}}"#,
        r#"{"chat_template_kwargs": {"reasoning_effort": null}}"#,
        r#"{"reasoning": {"effort": "low"}}"#,
    ] {
        let (r, flags) = with_shared(&obj(own), Dialect::OpenAi, &s, true);
        assert!(!r.contains_key("reasoning_effort"), "{own}");
        assert!(!flags.level_shared, "{own}");
    }
    let (r, flags) = with_shared(
        &obj(r#"{"chat_template_kwargs": [1]}"#),
        Dialect::OpenAi,
        &s,
        false,
    );
    assert_eq!(r["reasoning_effort"], val("\"none\""));
    assert!(!flags.level_shared); // not a GLM-DSA template
                                  // No shared settings: the request as it is.
    let req = obj(r#"{"a": 1}"#);
    assert_eq!(
        with_shared(&req, Dialect::OpenAi, &SharedDefaults::new(), true).0,
        req
    );
}

/// Request, then shared settings, then the run config's block (or the model's own defaults
/// when the config has none), then nothing.
#[test]
fn precedence_matrix() {
    let requests = [
        ("own", Some(r#"{"temperature": 0.9}"#)),
        ("null", Some(r#"{"temperature": null}"#)),
        ("absent", Some("{}")),
        ("zero", Some(r#"{"temperature": 0}"#)),
    ];
    let shareds = [("shared", Some(r#"{"temperature": 0.5}"#)), ("none", None)];
    let configs = [
        ("config", r#"{"sampling": {"temperature": 0.3}}"#),
        ("config-without", r#"{"sampling": {"top_k": 5}}"#),
        ("model", "{}"),
    ];
    let models = [
        ("model-defaults", Some(r#"{"temperature": 0.1}"#)),
        ("no-model", None),
    ];
    let mut rows = 0;
    for (rname, rsrc) in requests {
        for (sname, ssrc) in shareds {
            for (cname, csrc) in configs {
                for (mname, msrc) in models {
                    let model = msrc.map(obj);
                    let run = run_sampling_defaults(&obj(csrc), model.as_ref()).unwrap();
                    let s = ssrc.map(shared).unwrap_or_default();
                    let req = obj(rsrc.unwrap_or("{}"));
                    let got = effective_sampling(&run.values, &s, &req);
                    let want = match rname {
                        "own" => Some("0.9"),
                        "zero" => Some("0"),
                        _ if sname == "shared" => Some("0.5"),
                        _ if cname == "config" => Some("0.3"),
                        _ if cname == "model" && mname == "model-defaults" => Some("0.1"),
                        _ if rname == "null"
                            && cname == "model"
                            && mname == "no-model"
                            && sname == "none" =>
                        {
                            Some("null")
                        }
                        _ => None,
                    };
                    let shown = got.get("temperature").map(|v| v.to_string());
                    assert_eq!(
                        shown.as_deref(),
                        want,
                        "request {rname}, {sname}, {cname}, {mname}: {got:?}"
                    );
                    let origin = if cname == "model" {
                        DefaultsOrigin::Model
                    } else {
                        DefaultsOrigin::Config
                    };
                    assert_eq!(run.origin, origin);
                    rows += 1;
                }
            }
        }
    }
    assert_eq!(rows, 48);
    // An explicit 0 over every default stays greedy.
    let run = run_sampling_defaults(&obj(r#"{"sampling": {"temperature": 0.3}}"#), None).unwrap();
    let got = effective_sampling(
        &run.values,
        &shared(r#"{"temperature": 0.5}"#),
        &obj(r#"{"temperature": 0}"#),
    );
    assert_eq!(line_of(&got), " temperature=0");
    // Key order is Python's {**config, **shared, **request}.
    let got = effective_sampling(
        &obj(r#"{"top_k": 5, "temperature": 0.3}"#),
        &shared(r#"{"seed": 4, "temperature": 0.5}"#),
        &obj(r#"{"messages": [], "top_k": 9, "seed": null}"#),
    );
    let text: Vec<String> = got.iter().map(|(k, v)| format!("{k}={v}")).collect();
    assert_eq!(
        text,
        ["top_k=9", "temperature=0.5", "seed=4", "messages=[]"]
    );
}

#[test]
fn run_config_sampling_block() {
    let cfg = obj(
        r#"{"sampling": {"temperature": 1, "top_k": 40.0, "penalty_last_n": -1, "seed": 3,
            "min_p": 1, "repetition_penalty": 1.1, "frequency_penalty": 0, "presence_penalty": 0.5,
            "top_p": 0.95, "experimental_speed_projection": false, "ablate": true, "x": null,
            "mirostat": [2]}}"#,
    );
    let got = sampling_defaults_from_config(&cfg).unwrap();
    let text: Vec<String> = got.values.iter().map(|(k, v)| format!("{k}={v}")).collect();
    assert_eq!(
        text,
        [
            "temperature=1.0",
            "top_k=40",
            "penalty_last_n=-1",
            "seed=3",
            "min_p=1.0",
            "repetition_penalty=1.1",
            "frequency_penalty=0.0",
            "presence_penalty=0.5",
            "top_p=0.95",
            "experimental_speed_projection=false",
        ]
    );
    // Deviation POL-1.2: the donor's ablation default is an unknown key here.
    assert_eq!(
        got.notes,
        [
            "[console] config sampling.ablate=True: unknown key, ignored",
            "[console] config sampling.mirostat=[2]: unknown key, ignored",
        ]
    );
    let run = run_sampling_defaults(&cfg, None).unwrap();
    assert_eq!(
        run.announcement().unwrap(),
        "[console] sampling defaults from the config: temperature=1.0, top_k=40, \
         penalty_last_n=-1, seed=3, min_p=1.0, repetition_penalty=1.1, frequency_penalty=0.0, \
         presence_penalty=0.5, top_p=0.95, experimental_speed_projection=False"
    );
    // A falsy block is no block; a config without the key takes the model's defaults.
    for empty in [
        r#"{"sampling": null}"#,
        r#"{"sampling": []}"#,
        r#"{"sampling": 0}"#,
    ] {
        let r = run_sampling_defaults(&obj(empty), Some(&obj(r#"{"top_k": 20}"#))).unwrap();
        assert!(r.values.is_empty(), "{empty}");
        assert_eq!(r.announcement(), None);
    }
    let r = run_sampling_defaults(&obj("{}"), Some(&obj(r#"{"top_k": 20}"#))).unwrap();
    assert_eq!(
        r.announcement().unwrap(),
        "[console] sampling defaults from the model: top_k=20"
    );
}

/// Every start-up refusal of the donor's `sampling_defaults_from_config`, with its input.
#[test]
fn every_run_config_sampling_message_with_its_input() {
    let cases: &[(&str, &str)] = &[
        (r#"{"temperature": -0.5}"#, "[console] config sampling.temperature=-0.5: expected a number >= 0 (0 = greedy)"),
        (r#"{"temperature": "hot"}"#, "[console] config sampling.temperature='hot': expected a number >= 0 (0 = greedy)"),
        (r#"{"top_p": 1.5}"#, "[console] config sampling.top_p=1.5: expected 0 < top_p <= 1"),
        (r#"{"top_p": NaN}"#, "[console] config sampling.top_p=nan: expected 0 < top_p <= 1"),
        (r#"{"min_p": -0.1}"#, "[console] config sampling.min_p=-0.1: expected 0 <= min_p <= 1"),
        (r#"{"top_k": 0}"#, "[console] config sampling.top_k=0: the sampled path takes an integer 1..64"),
        (r#"{"top_k": 2.5}"#, "[console] config sampling.top_k=2.5: the sampled path takes an integer 1..64"),
        (r#"{"top_k": true}"#, "[console] config sampling.top_k=True: the sampled path takes an integer 1..64"),
        (r#"{"presence_penalty": -1}"#, "[console] config sampling.presence_penalty=-1: expected a number >= 0"),
        (r#"{"frequency_penalty": {"a": 1}}"#, "[console] config sampling.frequency_penalty={'a': 1}: expected a number >= 0"),
        (r#"{"repetition_penalty": 0}"#, "[console] config sampling.repetition_penalty=0: expected a number > 0 (1 = off)"),
        (
            r#"{"penalty_last_n": -2}"#,
            "[console] config sampling.penalty_last_n=-2: expected an integer >= -1 (0 = no penalties, -1 = the whole context)",
        ),
        (r#"{"seed": 0}"#, "[console] config sampling.seed=0: expected a positive integer"),
        (
            r#"{"experimental_speed_projection": "on"}"#,
            "[console] config sampling.experimental_speed_projection='on': expected true or false (the default for requests that leave it out, when the engine has the vector)",
        ),
        (r#"{"top_k": NaN}"#, "ValueError: cannot convert float NaN to integer"),
        (r#"{"seed": Infinity}"#, "OverflowError: cannot convert float infinity to integer"),
    ];
    for (block, msg) in cases {
        let cfg = obj(&format!("{{\"sampling\": {block}}}"));
        let err = sampling_defaults_from_config(&cfg).unwrap_err();
        assert_eq!(err.message(), *msg, "{block}");
        assert!(err.notes().is_empty(), "{block}");
    }
    // The donor prints each unknown-key note as it reaches the key, so the notes before a
    // refused key are already out: the error carries them, in order; later keys are never
    // reached.
    let err = sampling_defaults_from_config(&obj(
        r#"{"sampling": {"mirostat": 2, "temperature": 0.5, "typical_p": "x", "top_k": 0, "tfs": 1}}"#,
    ))
    .unwrap_err();
    assert_eq!(
        err.notes(),
        [
            "[console] config sampling.mirostat=2: unknown key, ignored",
            "[console] config sampling.typical_p='x': unknown key, ignored",
        ]
    );
    assert_eq!(
        err.message(),
        "[console] config sampling.top_k=0: the sampled path takes an integer 1..64"
    );
    let err = run_sampling_defaults(
        &obj(r#"{"sampling": {"mirostat": 2, "seed": Infinity}}"#),
        None,
    )
    .unwrap_err();
    assert_eq!(
        err.notes(),
        ["[console] config sampling.mirostat=2: unknown key, ignored"]
    );
    assert_eq!(
        err.message(),
        "OverflowError: cannot convert float infinity to integer"
    );
    let huge = format!(
        "{{\"sampling\": {{\"temperature\": 1{}}}}}",
        "0".repeat(400)
    );
    assert_eq!(
        sampling_defaults_from_config(&obj(&huge))
            .unwrap_err()
            .message(),
        "OverflowError: int too large to convert to float"
    );
    assert_eq!(
        sampling_defaults_from_config(&obj(r#"{"sampling": "greedy"}"#))
            .unwrap_err()
            .message(),
        "AttributeError: 'str' object has no attribute 'items'"
    );
    // NaN is not below 0, so the donor keeps it as the temperature.
    let got = sampling_defaults_from_config(&obj(r#"{"sampling": {"temperature": NaN}}"#)).unwrap();
    assert_eq!(got.values["temperature"].to_string(), "NaN");
}

// Deviation SEC-6.1: the merge that feeds the engine drops a client's underscore keys
// even when the boundary strip was missed, with defaults and without.
#[test]
fn effective_sampling_never_carries_underscore_keys() {
    let req = obj(
        r#"{"_prefill": "forged", "_think_budget": 1, "_restore": [1], "_responses": true,
            "temperature": 0.4, "messages": []}"#,
    );
    let without = effective_sampling(&Map::new(), &SharedDefaults::new(), &req);
    assert!(without.keys().all(|k| !k.starts_with('_')), "{without:?}");
    assert_eq!(
        without.keys().map(String::as_str).collect::<Vec<_>>(),
        ["temperature", "messages"]
    );
    let with = effective_sampling(&obj(r#"{"top_k": 5}"#), &shared(r#"{"seed": 4}"#), &req);
    assert!(with.keys().all(|k| !k.starts_with('_')), "{with:?}");
    assert_eq!(
        with.keys().map(String::as_str).collect::<Vec<_>>(),
        ["top_k", "seed", "temperature", "messages"]
    );
}
