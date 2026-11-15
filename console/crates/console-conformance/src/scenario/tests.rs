//! Unit tests of the scenario loader: every field, its default, and every error it can
//! raise, each checked with the JSON pointer it must name.

use serde_json::{json, Value};

use super::*;

/// A valid scenario using every field of the format.
fn full() -> Value {
    json!({
        "id": "full-01",
        "description": "every field",
        "donor": ["serve/test_server.py::MaxTokens::test_explicit_budget_is_honoured", "serve/test_x.py::fn_name"],
        "notes": "a note",
        "engine": {
            "kind": "mock",
            "tokenizer": {"kind": "byte", "extra_specials": ["<think>", "</think>"]},
            "script": ["</think>\n\nhello", {"repeat": "ab", "times": 3}],
            "max_context": 4096,
            "info": {"logprobs": 20},
            "delay_ms": 2,
            "tok_s": 50.5
        },
        "template": "vendor:serve/chat_template.jinja",
        "server": {
            "flags": ["--fit-max-tokens", "--idle-unload", "5"],
            "env": {"PULSAR_CONSOLE_MOCK_RELOAD_S": "0.3"},
            "config": {"model_name": "m", "cors_origins": ["http://{{loopback}}:8090"]},
            "data_dir": {"notes/a.txt": "text", "pulsar-x.json": {"k": 1}, "list.json": [1]}
        },
        "steps": [
            {"request": {
                "method": "POST",
                "path": "/v1/chat/completions?x=1",
                "headers": [["Content-Type", "application/json"], ["X-A", "1"], ["X-A", "2"]],
                "body": {"model": "m", "stream": true},
                "http_version": "1.0"
            }, "disconnect_after_events": 3, "concurrent_group": "g1"},
            {"request": {"method": "GET", "path": "/health", "body_text": ""}, "concurrent_group": "g1",
             "wait_for_engine_step": 2, "release_engine_step": 2},
            {"request": {"method": "POST", "path": "/v1/messages", "body_file": "bodies/m.json"},
             "disconnect_after_bytes": 100},
            {"request": {"raw": "GET / HTTP/1.0\r\n\r\n"}},
            {"release_engine_step": 0},
            {"signal": "SIGTERM"}
        ],
        "observe": {"http": true, "engine_tape": true, "files": ["**/*.json", "a?.txt"], "log": ["stopping"], "exit": true}
    })
}

/// A valid scenario with only the required fields.
fn minimal() -> Value {
    json!({
        "id": "min",
        "engine": {"kind": "mock", "tokenizer": {"kind": "byte"}, "script": ["ok"]},
        "template": "chatml-synthetic",
        "steps": [{"request": {"method": "GET", "path": "/health"}}],
        "observe": {"http": true}
    })
}

fn load(v: &Value) -> Result<Scenario> {
    Scenario::from_json_str(&v.to_string())
}

/// `v` with the member at `pointer` set to `value` (the parent must exist).
fn set(mut v: Value, pointer: &str, value: Value) -> Value {
    let (parent, key) = pointer.rsplit_once('/').unwrap();
    let target = v.pointer_mut(parent).unwrap();
    match target {
        Value::Object(map) => {
            map.insert(key.replace("~1", "/").replace("~0", "~"), value);
        }
        Value::Array(items) => {
            let i: usize = key.parse().unwrap();
            items[i] = value;
        }
        _ => panic!("no container at {parent}"),
    }
    v
}

fn remove(mut v: Value, pointer: &str) -> Value {
    let (parent, key) = pointer.rsplit_once('/').unwrap();
    v.pointer_mut(parent)
        .unwrap()
        .as_object_mut()
        .unwrap()
        .shift_remove(key);
    v
}

#[track_caller]
fn fails(v: Value, pointer: &str) -> ErrorKind {
    match load(&v) {
        Ok(_) => panic!("loaded, expected an error at {pointer}"),
        Err(e) => {
            assert_eq!(e.pointer, pointer, "{e}");
            e.kind
        }
    }
}

#[track_caller]
fn invalid(v: Value, pointer: &str) {
    let kind = fails(v, pointer);
    assert!(matches!(kind, ErrorKind::InvalidValue { .. }), "{kind:?}");
}

// ------------------------------------------------------------------ whole documents

#[test]
fn full_scenario_loads_with_every_field() {
    let s = load(&full()).unwrap();
    assert_eq!(s.id, "full-01");
    assert_eq!(s.description.as_deref(), Some("every field"));
    assert_eq!(s.donor.len(), 2);
    assert_eq!(s.notes.as_deref(), Some("a note"));
    let EngineSpec::Mock(m) = &s.engine else {
        panic!("mock expected")
    };
    assert_eq!(
        m.script,
        vec!["</think>\n\nhello".to_string(), "ababab".to_string()]
    );
    assert_eq!(m.max_context, 4096);
    assert_eq!(m.info["logprobs"], 20);
    assert_eq!(m.delay_ms, 2);
    assert_eq!(m.tok_s, Some(50.5));
    assert_eq!(
        m.tokenizer.specials()[6..],
        [("<think>".to_string(), 262), ("</think>".to_string(), 263)]
    );
    assert_eq!(
        s.template,
        TemplateRef::Vendor("serve/chat_template.jinja".into())
    );
    assert_eq!(s.server.flags, ["--fit-max-tokens", "--idle-unload", "5"]);
    assert_eq!(
        s.server.env,
        [(
            "PULSAR_CONSOLE_MOCK_RELOAD_S".to_string(),
            "0.3".to_string()
        )]
    );
    assert_eq!(s.server.config["model_name"], "m");
    assert_eq!(s.server.data_dir.len(), 3);
    assert_eq!(
        s.server.data_dir[0],
        ("notes/a.txt".into(), DataFile::Text("text".into()))
    );
    assert_eq!(s.server.data_dir[1].1, DataFile::Json(json!({"k": 1})));
    assert_eq!(s.steps.len(), 6);
    let Some(Request::Structured(r)) = &s.steps[0].request else {
        panic!("structured request expected")
    };
    assert_eq!(r.method, "POST");
    assert_eq!(r.path, "/v1/chat/completions?x=1");
    assert_eq!(
        r.headers.len(),
        3,
        "duplicate header names are kept in order"
    );
    assert_eq!(r.headers[2], ("X-A".into(), "2".into()));
    assert_eq!(r.body, Body::Json(json!({"model": "m", "stream": true})));
    assert_eq!(r.http_version, HttpVersion::V1_0);
    assert_eq!(s.steps[0].disconnect, Some(Disconnect::AfterEvents(3)));
    assert_eq!(s.steps[0].concurrent_group.as_deref(), Some("g1"));
    assert_eq!(s.steps[0].wait_for_engine_step, None);
    assert_eq!(s.steps[1].wait_for_engine_step, Some(2));
    assert_eq!(s.steps[1].release_engine_step, Some(2));
    let Some(Request::Structured(r1)) = &s.steps[1].request else {
        panic!()
    };
    assert_eq!(r1.body, Body::Text(String::new()));
    assert_eq!(r1.http_version, HttpVersion::V1_1);
    let Some(Request::Structured(r2)) = &s.steps[2].request else {
        panic!()
    };
    assert_eq!(r2.body, Body::File("bodies/m.json".into()));
    assert_eq!(s.steps[2].disconnect, Some(Disconnect::AfterBytes(100)));
    assert_eq!(
        s.steps[3].request,
        Some(Request::Raw("GET / HTTP/1.0\r\n\r\n".into()))
    );
    assert_eq!(s.steps[4].release_engine_step, Some(0));
    assert_eq!(s.steps[5].signal, Some(Signal::Term));
    assert_eq!(s.steps[5].signal.map(Signal::name), Some("SIGTERM"));
    assert_eq!(
        s.observe,
        Observe {
            http: true,
            engine_tape: true,
            files: vec!["**/*.json".into(), "a?.txt".into()],
            log: vec!["stopping".into()],
            exit: true
        }
    );
}

#[test]
fn minimal_scenario_takes_the_defaults() {
    let s = load(&minimal()).unwrap();
    assert!(s.description.is_none() && s.notes.is_none() && s.donor.is_empty());
    let EngineSpec::Mock(m) = &s.engine else {
        panic!()
    };
    assert_eq!(m.max_context, MOCK_DEFAULT_MAX_CONTEXT);
    assert_eq!((m.delay_ms, m.tok_s), (0, None));
    assert!(m.info.is_empty());
    assert_eq!(
        m.tokenizer,
        TokenizerSpec::Byte {
            extra_specials: vec![]
        }
    );
    assert_eq!(s.template, TemplateRef::Project("chatml-synthetic".into()));
    assert_eq!(s.server, ServerSpec::default());
    let Some(Request::Structured(r)) = &s.steps[0].request else {
        panic!()
    };
    assert_eq!(
        (r.body.clone(), r.http_version),
        (Body::None, HttpVersion::V1_1)
    );
    assert!(r.headers.is_empty());
    assert_eq!(s.observe.files.len() + s.observe.log.len(), 0);
}

#[test]
fn line_engine_loads() {
    let v = set(
        minimal(),
        "/engine",
        json!({"kind": "line", "fake": "multi",
               "tokenizer": {"kind": "bpe-bytes", "added": {"<|im_end|>": 256, "</think>": 257}},
               "args": ["1"], "env": {"FAKE_MULTI_INTERLEAVE": "4", "MAYA_GLM_SLOT_KEEP": "1"}}),
    );
    let s = load(&v).unwrap();
    let EngineSpec::Line(l) = &s.engine else {
        panic!()
    };
    assert_eq!(l.fake, LineFake::Multi);
    assert_eq!(l.args, ["1"]);
    assert_eq!(l.env[1], ("MAYA_GLM_SLOT_KEEP".into(), "1".into()));
    assert_eq!(
        l.tokenizer,
        TokenizerSpec::BpeBytes {
            added: vec![("<|im_end|>".into(), 256), ("</think>".into(), 257)]
        }
    );
    let v = set(
        minimal(),
        "/engine",
        json!({"kind": "line", "fake": "glm", "tokenizer": {"kind": "bpe-bytes"}}),
    );
    let EngineSpec::Line(l) = load(&v).unwrap().engine else {
        panic!()
    };
    assert_eq!((l.fake, l.args.len(), l.env.len()), (LineFake::Glm, 0, 0));
}

// ------------------------------------------------------------------ document-level errors

#[test]
fn not_json_and_trailing_text() {
    let err = Scenario::from_json_str("{\"id\": }").unwrap_err();
    assert!(
        matches!(err.kind, ErrorKind::Syntax { line: 1, .. }),
        "{err}"
    );
    let err = Scenario::from_json_str("[]").unwrap_err();
    assert_eq!(
        err.kind,
        ErrorKind::WrongType {
            expected: "object",
            found: "array"
        }
    );
}

#[test]
fn duplicate_key_is_refused() {
    let text = minimal()
        .to_string()
        .replacen("\"id\":\"min\"", "\"id\":\"min\",\"id\":\"min\"", 1);
    let err = Scenario::from_json_str(&text).unwrap_err();
    assert_eq!(err.kind, ErrorKind::DuplicateKey { key: "id".into() });
}

#[test]
fn oversize_scenario_is_refused() {
    let big = " ".repeat(limits::MAX_SCENARIO_BYTES + 1);
    let err = Scenario::from_json_str(&big).unwrap_err();
    assert_eq!(
        err.kind,
        ErrorKind::TooLarge {
            limit: limits::MAX_SCENARIO_BYTES
        }
    );
}

#[test]
fn unknown_and_missing_top_level_fields() {
    assert_eq!(
        fails(set(minimal(), "/extra", json!(1)), ""),
        ErrorKind::UnknownField {
            field: "extra".into()
        }
    );
    for field in ["id", "engine", "template", "steps", "observe"] {
        let kind = fails(remove(minimal(), &format!("/{field}")), "");
        assert!(
            matches!(kind, ErrorKind::MissingField { field: f } if f == field),
            "{field}"
        );
    }
}

// ------------------------------------------------------------------ id, description, donor, notes

#[test]
fn id_rules() {
    for bad in ["", "Upper", "-x", "x-", "a_b", "a b", "a.b"] {
        let kind = fails(set(minimal(), "/id", json!(bad)), "/id");
        assert!(
            matches!(kind, ErrorKind::InvalidValue { .. } | ErrorKind::Empty),
            "{bad}: {kind:?}"
        );
    }
    assert_eq!(
        fails(set(minimal(), "/id", json!("a".repeat(65))), "/id"),
        ErrorKind::TooLong { limit: 64 }
    );
    assert!(matches!(
        fails(set(minimal(), "/id", json!(3)), "/id"),
        ErrorKind::WrongType { .. }
    ));
    assert!(load(&set(minimal(), "/id", json!("0-a-9"))).is_ok());
}

#[test]
fn description_and_notes() {
    assert_eq!(
        fails(set(minimal(), "/description", json!("")), "/description"),
        ErrorKind::Empty
    );
    assert_eq!(
        fails(
            set(minimal(), "/description", json!("x".repeat(1001))),
            "/description"
        ),
        ErrorKind::TooLong { limit: 1000 }
    );
    assert!(matches!(
        fails(set(minimal(), "/notes", json!(null)), "/notes"),
        ErrorKind::WrongType { .. }
    ));
    assert_eq!(
        fails(set(minimal(), "/notes", json!("x".repeat(4001))), "/notes"),
        ErrorKind::TooLong { limit: 4000 }
    );
}

#[test]
fn donor_rules() {
    assert_eq!(
        fails(set(minimal(), "/donor", json!([])), "/donor"),
        ErrorKind::Empty
    );
    for bad in [
        "serve/test_x.py",
        "serve/x.py::A::b",
        "tools/test_x.py::A::b",
        "serve/test_x.py::A::b::c",
        "serve/test_X.py::A::b",
        "serve/test_x.py::1A::b",
    ] {
        invalid(set(minimal(), "/donor", json!([bad])), "/donor/0");
    }
    invalid(
        set(
            minimal(),
            "/donor",
            json!(["serve/test_x.py::A::b", "serve/test_x.py::A::b"]),
        ),
        "/donor/1",
    );
    assert_eq!(
        fails(
            set(minimal(), "/donor", json!(vec!["serve/test_x.py::f"; 17])),
            "/donor"
        ),
        ErrorKind::TooMany { limit: 16 }
    );
}

// ------------------------------------------------------------------ engine

#[test]
fn engine_kind_and_members() {
    invalid(
        set(minimal(), "/engine/kind", json!("real")),
        "/engine/kind",
    );
    assert!(matches!(
        fails(remove(minimal(), "/engine/kind"), "/engine"),
        ErrorKind::MissingField { field: "kind" }
    ));
    assert_eq!(
        fails(set(minimal(), "/engine/fake", json!("glm")), "/engine"),
        ErrorKind::UnknownField {
            field: "fake".into()
        }
    );
    for field in ["tokenizer", "script"] {
        let kind = fails(remove(minimal(), &format!("/engine/{field}")), "/engine");
        assert!(matches!(kind, ErrorKind::MissingField { .. }), "{field}");
    }
    assert!(matches!(
        fails(set(minimal(), "/engine", json!("mock")), "/engine"),
        ErrorKind::WrongType { .. }
    ));
}

#[test]
fn script_rules() {
    assert_eq!(
        fails(
            set(minimal(), "/engine/script", json!([])),
            "/engine/script"
        ),
        ErrorKind::Empty
    );
    assert_eq!(
        fails(
            set(minimal(), "/engine/script", json!(vec!["x"; 65])),
            "/engine/script"
        ),
        ErrorKind::TooMany { limit: 64 }
    );
    assert!(
        load(&set(minimal(), "/engine/script", json!([""]))).is_ok(),
        "an empty script is the donor's empty answer"
    );
    assert!(matches!(
        fails(
            set(minimal(), "/engine/script", json!([1])),
            "/engine/script/0"
        ),
        ErrorKind::WrongType { .. }
    ));
    assert_eq!(
        fails(
            set(minimal(), "/engine/script", json!([{"repeat": "a"}])),
            "/engine/script/0"
        ),
        ErrorKind::MissingField { field: "times" }
    );
    assert_eq!(
        fails(
            set(
                minimal(),
                "/engine/script",
                json!([{"repeat": "a", "times": 2, "x": 1}])
            ),
            "/engine/script/0"
        ),
        ErrorKind::UnknownField { field: "x".into() }
    );
    assert_eq!(
        fails(
            set(
                minimal(),
                "/engine/script",
                json!([{"repeat": "", "times": 2}])
            ),
            "/engine/script/0/repeat"
        ),
        ErrorKind::Empty
    );
    assert!(matches!(
        fails(
            set(
                minimal(),
                "/engine/script",
                json!([{"repeat": "a", "times": 0}])
            ),
            "/engine/script/0/times"
        ),
        ErrorKind::OutOfRange { .. }
    ));
    invalid(
        set(
            minimal(),
            "/engine/script",
            json!([{"repeat": "ab", "times": limits::MAX_SCRIPT_BYTES}]),
        ),
        "/engine/script/0",
    );
    invalid(
        set(
            minimal(),
            "/engine/script",
            json!([{"repeat": "a", "times": limits::MAX_SCRIPT_BYTES}, "b"]),
        ),
        "/engine/script/1",
    );
    let s = load(&set(
        minimal(),
        "/engine/script",
        json!([{"repeat": "a", "times": 2000}, "Ready"]),
    ))
    .unwrap();
    let EngineSpec::Mock(m) = s.engine else {
        panic!()
    };
    assert_eq!((m.script[0].len(), m.script[1].as_str()), (2000, "Ready"));
}

#[test]
fn mock_numbers() {
    for (field, bad) in [
        ("max_context", json!(0)),
        ("max_context", json!(limits::MAX_CONTEXT + 1)),
        ("delay_ms", json!(60001)),
    ] {
        assert!(matches!(
            fails(
                set(minimal(), &format!("/engine/{field}"), bad),
                &format!("/engine/{field}")
            ),
            ErrorKind::OutOfRange { .. }
        ));
    }
    assert!(matches!(
        fails(
            set(minimal(), "/engine/max_context", json!(1.5)),
            "/engine/max_context"
        ),
        ErrorKind::WrongType { .. }
    ));
    for bad in [json!(0), json!(-1), json!(2_000_000.0)] {
        invalid(set(minimal(), "/engine/tok_s", bad), "/engine/tok_s");
    }
    assert!(matches!(
        fails(set(minimal(), "/engine/tok_s", json!("5")), "/engine/tok_s"),
        ErrorKind::WrongType { .. }
    ));
    assert!(matches!(
        fails(set(minimal(), "/engine/info", json!([])), "/engine/info"),
        ErrorKind::WrongType {
            expected: "object",
            ..
        }
    ));
}

#[test]
fn byte_tokenizer_rules() {
    invalid(
        set(minimal(), "/engine/tokenizer/kind", json!("sentencepiece")),
        "/engine/tokenizer/kind",
    );
    assert_eq!(
        fails(
            set(minimal(), "/engine/tokenizer/added", json!({})),
            "/engine/tokenizer"
        ),
        ErrorKind::UnknownField {
            field: "added".into()
        }
    );
    invalid(
        set(
            minimal(),
            "/engine/tokenizer/extra_specials",
            json!(["<|im_end|>"]),
        ),
        "/engine/tokenizer/extra_specials/0",
    );
    invalid(
        set(
            minimal(),
            "/engine/tokenizer/extra_specials",
            json!(["<a>", "<a>"]),
        ),
        "/engine/tokenizer/extra_specials/1",
    );
    assert_eq!(
        fails(
            set(minimal(), "/engine/tokenizer/extra_specials", json!([""])),
            "/engine/tokenizer/extra_specials/0"
        ),
        ErrorKind::Empty
    );
    assert_eq!(
        fails(
            set(
                minimal(),
                "/engine/tokenizer/extra_specials",
                json!(["x".repeat(65)])
            ),
            "/engine/tokenizer/extra_specials/0"
        ),
        ErrorKind::TooLong { limit: 64 }
    );
}

#[test]
fn bpe_tokenizer_rules() {
    let with = |added: Value| {
        set(
            minimal(),
            "/engine/tokenizer",
            json!({"kind": "bpe-bytes", "added": added}),
        )
    };
    assert!(load(&with(json!({"<x>": 256}))).is_ok());
    assert!(matches!(
        fails(with(json!({"<x>": 255})), "/engine/tokenizer/added/<x>"),
        ErrorKind::OutOfRange { min: 256, .. }
    ));
    invalid(
        with(json!({"<x>": 300, "<y>": 300})),
        "/engine/tokenizer/added/<y>",
    );
    invalid(with(json!({"!": 300})), "/engine/tokenizer/added/!");
    invalid(with(json!({"": 300})), "/engine/tokenizer/added/");
    assert!(matches!(
        fails(with(json!(["<x>"])), "/engine/tokenizer/added"),
        ErrorKind::WrongType { .. }
    ));
    assert_eq!(
        fails(
            set(
                minimal(),
                "/engine/tokenizer",
                json!({"kind": "bpe-bytes", "extra_specials": []})
            ),
            "/engine/tokenizer"
        ),
        ErrorKind::UnknownField {
            field: "extra_specials".into()
        }
    );
}

#[test]
fn line_engine_rules() {
    let line = || json!({"kind": "line", "fake": "glm", "tokenizer": {"kind": "bpe-bytes"}});
    invalid(
        set(
            set(minimal(), "/engine", line()),
            "/engine/fake",
            json!("ds4"),
        ),
        "/engine/fake",
    );
    invalid(
        set(
            set(minimal(), "/engine", line()),
            "/engine/tokenizer",
            json!({"kind": "byte"}),
        ),
        "/engine/tokenizer",
    );
    assert_eq!(
        fails(
            set(
                set(minimal(), "/engine", line()),
                "/engine/script",
                json!(["x"])
            ),
            "/engine"
        ),
        ErrorKind::UnknownField {
            field: "script".into()
        }
    );
    for field in ["fake", "tokenizer"] {
        let kind = fails(
            remove(
                set(minimal(), "/engine", line()),
                &format!("/engine/{field}"),
            ),
            "/engine",
        );
        assert!(matches!(kind, ErrorKind::MissingField { .. }), "{field}");
    }
    for bad in [
        "lower",
        "1ABC",
        "A-B",
        "",
        "LD_PRELOAD",
        "DYLD_INSERT_LIBRARIES",
        "HOME",
        "XDG_DATA_HOME",
        "FAKE_ENGINE_GATE",
    ] {
        invalid(
            set(
                set(minimal(), "/engine", line()),
                "/engine/env",
                json!({bad: "1"}),
            ),
            &format!("/engine/env/{bad}"),
        );
    }
    assert!(matches!(
        fails(
            set(
                set(minimal(), "/engine", line()),
                "/engine/env",
                json!({"A": 1})
            ),
            "/engine/env/A"
        ),
        ErrorKind::WrongType { .. }
    ));
    invalid(
        set(
            set(minimal(), "/engine", line()),
            "/engine/args",
            json!(["a\u{0}b"]),
        ),
        "/engine/args/0",
    );
    assert_eq!(
        fails(
            set(
                set(minimal(), "/engine", line()),
                "/engine/args",
                json!(vec!["a"; 65])
            ),
            "/engine/args"
        ),
        ErrorKind::TooMany { limit: 64 }
    );
}

// ------------------------------------------------------------------ template

#[test]
fn template_rules() {
    for ok in [
        "chatml-synthetic",
        "glm.synthetic_2",
        "vendor:serve/chat_template.jinja",
        "vendor:data/glm-dsa/templates/glm-5.3.official.jinja",
    ] {
        assert!(
            load(&set(minimal(), "/template", json!(ok))).is_ok(),
            "{ok}"
        );
    }
    for bad in [
        "Chat",
        "chat/ml",
        "chat..ml",
        "chatml.jinja",
        "vendor:",
        "vendor:serve/chat_template.txt",
        "vendor:/abs.jinja",
        "vendor:serve/../x.jinja",
        "vendor:serve//x.jinja",
        "other:x",
    ] {
        invalid(set(minimal(), "/template", json!(bad)), "/template");
    }
    assert_eq!(
        fails(set(minimal(), "/template", json!("")), "/template"),
        ErrorKind::Empty
    );
}

// ------------------------------------------------------------------ server

#[test]
fn server_rules() {
    assert_eq!(
        fails(set(minimal(), "/server", json!({"cwd": "/"})), "/server"),
        ErrorKind::UnknownField {
            field: "cwd".into()
        }
    );
    for flag in [
        "--port",
        "--port=0",
        "--config",
        "--engine",
        "--script",
        "--tokenizer=x",
    ] {
        invalid(
            set(minimal(), "/server", json!({"flags": ["--open", flag]})),
            "/server/flags/1",
        );
    }
    // argparse abbreviations of the harness flags (allow_abbrev=True in the donor)
    for flag in [
        "--eng",
        "--eng=maya",
        "--scr",
        "--conf=x",
        "--tok",
        "--po=1",
        "--p",
        "--por",
    ] {
        invalid(
            set(minimal(), "/server", json!({"flags": ["--open", flag]})),
            "/server/flags/1",
        );
    }
    invalid(
        set(minimal(), "/server", json!({"flags": ["--por", "80"]})),
        "/server/flags/0",
    );
    // names that only start like a harness flag are not abbreviations of it
    assert!(load(&set(
        minimal(),
        "/server",
        json!({"flags": ["--", "--ports", "--engines=x", "--open"]})
    ))
    .is_ok());
    // the bind address may only be the loopback token
    for flags in [
        json!(["--host", "{{loopback}}"]),
        json!(["--host={{loopback}}"]),
        json!(["--ho", "{{loopback}}", "--open"]),
    ] {
        assert!(
            load(&set(minimal(), "/server", json!({ "flags": flags }))).is_ok(),
            "{flags}"
        );
    }
    for (flags, at) in [
        (json!(["--host", "0.0.0.0"]), "/server/flags/0"),
        (json!(["--open", "--host=0.0.0.0"]), "/server/flags/1"),
        (json!(["--hos", "::"]), "/server/flags/0"),
        (json!(["--host"]), "/server/flags/0"),
        (json!(["--host", "{{loopback}}x"]), "/server/flags/0"),
    ] {
        invalid(set(minimal(), "/server", json!({ "flags": flags })), at);
    }
    let bind_key = HOST_CONFIG_KEY;
    invalid(
        set(
            minimal(),
            "/server",
            json!({"config": {bind_key: "0.0.0.0"}}),
        ),
        "/server/config/host",
    );
    invalid(
        set(minimal(), "/server", json!({"config": {bind_key: 1}})),
        "/server/config/host",
    );
    assert!(load(&set(
        minimal(),
        "/server",
        json!({"config": {bind_key: "{{loopback}}"}})
    ))
    .is_ok());
    // reserved environment names, in server.env
    for name in [
        "PATH",
        "HOME",
        "TZ",
        "LC_ALL",
        "LANG",
        "TMPDIR",
        "PULSAR_CONSOLE_VENDOR_DIR",
        "FAKE_ENGINE_GATE",
        "XDG_CONFIG_HOME",
        "LD_PRELOAD",
        "DYLD_INSERT_LIBRARIES",
        "PYTHONPATH",
    ] {
        invalid(
            set(minimal(), "/server", json!({"env": {"A": "1", name: "x"}})),
            &format!("/server/env/{name}"),
        );
    }
    assert!(load(&set(
        minimal(),
        "/server",
        json!({"env": {"PATHS": "1", "MY_HOME": "1", "LDX": "1"}})
    ))
    .is_ok());
    invalid(
        set(minimal(), "/server", json!({"env": {"bad-name": "1"}})),
        "/server/env/bad-name",
    );
    assert!(matches!(
        fails(
            set(minimal(), "/server", json!({"config": []})),
            "/server/config"
        ),
        ErrorKind::WrongType { .. }
    ));
    // a mock engine's run config may carry exe and args, as the donor's dashboard test does
    assert!(load(&set(
        minimal(),
        "/server",
        json!({"config": {"exe": "strata", "args": []}})
    ))
    .is_ok());
    let line = set(
        minimal(),
        "/engine",
        json!({"kind": "line", "fake": "multi", "tokenizer": {"kind": "bpe-bytes"}}),
    );
    for key in ["exe", "args", "tokenizer"] {
        invalid(
            set(line.clone(), "/server", json!({"config": {key: "x"}})),
            &format!("/server/config/{key}"),
        );
    }
}

#[test]
fn data_dir_rules() {
    for bad in ["/abs", "../x", "a/../b", "a//b", ".", "a b", "a\\b"] {
        invalid(
            set(minimal(), "/server", json!({"data_dir": {bad: "x"}})),
            &format!(
                "/server/data_dir/{}",
                bad.replace('~', "~0").replace('/', "~1")
            ),
        );
    }
    for bad in [json!(1), json!(true), json!(null)] {
        assert!(matches!(
            fails(
                set(minimal(), "/server", json!({"data_dir": {"a": bad}})),
                "/server/data_dir/a"
            ),
            ErrorKind::WrongType { .. }
        ));
    }
    let many: serde_json::Map<String, Value> =
        (0..33).map(|i| (format!("f{i}"), json!("x"))).collect();
    assert_eq!(
        fails(
            set(minimal(), "/server", json!({"data_dir": many})),
            "/server/data_dir"
        ),
        ErrorKind::TooMany { limit: 32 }
    );
}

// ------------------------------------------------------------------ steps

#[test]
fn step_rules() {
    assert_eq!(
        fails(set(minimal(), "/steps", json!([])), "/steps"),
        ErrorKind::Empty
    );
    assert_eq!(
        fails(
            set(
                minimal(),
                "/steps",
                json!(vec![json!({"signal": "SIGHUP"}); 257])
            ),
            "/steps"
        ),
        ErrorKind::TooMany { limit: 256 }
    );
    invalid(set(minimal(), "/steps", json!([{}])), "/steps/0");
    assert_eq!(
        fails(set(minimal(), "/steps", json!([{"pause": 1}])), "/steps/0"),
        ErrorKind::UnknownField {
            field: "pause".into()
        }
    );
    invalid(
        set(
            minimal(),
            "/steps",
            json!([{"disconnect_after_events": 2, "release_engine_step": 1}]),
        ),
        "/steps/0",
    );
    invalid(
        set(
            minimal(),
            "/steps",
            json!([{"concurrent_group": "g", "signal": "SIGHUP"}]),
        ),
        "/steps/0",
    );
    // a gate-only step may belong to a group
    for gate in ["wait_for_engine_step", "release_engine_step"] {
        assert!(load(&set(
            minimal(),
            "/steps",
            json!([{"concurrent_group": "g", gate: 1}])
        ))
        .is_ok());
    }
    let req = json!({"method": "GET", "path": "/"});
    assert_eq!(
        fails(
            set(
                minimal(),
                "/steps",
                json!([{"request": req, "disconnect_after_events": 1, "disconnect_after_bytes": 1}])
            ),
            "/steps/0"
        ),
        ErrorKind::Exclusive {
            first: "disconnect_after_events",
            second: "disconnect_after_bytes"
        }
    );
    assert_eq!(
        fails(
            set(
                minimal(),
                "/steps",
                json!([{"request": req, "signal": "SIGTERM"}])
            ),
            "/steps/0"
        ),
        ErrorKind::Exclusive {
            first: "request",
            second: "signal"
        }
    );
    for (field, bad) in [
        ("disconnect_after_events", json!(0)),
        ("disconnect_after_bytes", json!(0)),
        ("wait_for_engine_step", json!(limits::MAX_ENGINE_STEP + 1)),
        ("release_engine_step", json!(-1)),
    ] {
        assert!(matches!(
            fails(
                set(minimal(), "/steps", json!([{"request": req, field: bad}])),
                &format!("/steps/0/{field}")
            ),
            ErrorKind::OutOfRange { .. }
        ));
    }
    invalid(
        set(minimal(), "/steps", json!([{"signal": "SIGKILL"}])),
        "/steps/0/signal",
    );
    for ok in ["SIGTERM", "SIGHUP", "SIGINT"] {
        assert!(load(&set(minimal(), "/steps", json!([{"signal": ok}]))).is_ok());
    }
    invalid(
        set(
            minimal(),
            "/steps",
            json!([{"request": req, "concurrent_group": "G!"}]),
        ),
        "/steps/0/concurrent_group",
    );
}

#[test]
fn hold_send_release_in_one_group_loads() {
    // A is held before engine step 0; B is started once A is held; then step 0 is
    // released, all inside group q, and the group is joined at the status request.
    let chat = json!({"method": "POST", "path": "/v1/chat/completions",
                      "body": {"model": "m", "messages": [{"role": "user", "content": "hi"}]}});
    let steps = json!([
        {"request": chat, "concurrent_group": "q"},
        {"wait_for_engine_step": 0, "request": chat, "concurrent_group": "q"},
        {"release_engine_step": 0, "concurrent_group": "q"},
        {"request": {"method": "GET", "path": "/v1/status"}}
    ]);
    let s = load(&set(minimal(), "/steps", steps)).unwrap();
    assert_eq!(s.steps.len(), 4);
    assert!(s.steps[..3]
        .iter()
        .all(|st| st.concurrent_group.as_deref() == Some("q")));
    assert_eq!(s.steps[1].wait_for_engine_step, Some(0));
    assert!(s.steps[1].request.is_some());
    assert_eq!(s.steps[2].request, None);
    assert_eq!(s.steps[2].release_engine_step, Some(0));
    assert_eq!(s.steps[3].concurrent_group, None);
}

#[test]
fn every_required_member_of_the_table_is_enforced() {
    let line = set(
        minimal(),
        "/engine",
        json!({"kind": "line", "fake": "multi",
               "tokenizer": {"kind": "bpe-bytes", "added": {"<|im_end|>": 256}},
               "args": ["1"], "env": {"FAKE_MULTI_INTERLEAVE": "4"}}),
    );
    // each object of the table, with a valid instance that holds every member it may
    let cases = [
        (schema::SCENARIO, full(), ""),
        (schema::ENGINE_MOCK, full(), "/engine"),
        (schema::ENGINE_LINE, line.clone(), "/engine"),
        (schema::TOKENIZER_BYTE, full(), "/engine/tokenizer"),
        (schema::TOKENIZER_BPE_BYTES, line, "/engine/tokenizer"),
        (schema::SCRIPT_REPEAT, full(), "/engine/script/1"),
        (schema::SERVER, full(), "/server"),
        (schema::STEP, full(), "/steps/1"),
        (schema::REQUEST, full(), "/steps/0/request"),
        (schema::REQUEST_RAW, full(), "/steps/3/request"),
        (schema::OBSERVE, full(), "/observe"),
    ];
    assert_eq!(cases.len(), schema::SCHEMA_OBJECTS.len());
    for (object, base, at) in cases {
        assert!(load(&base).is_ok(), "{}", object.name);
        let present = base.pointer(at).and_then(Value::as_object).unwrap();
        for member in object.properties {
            if !present.contains_key(*member) {
                // mutually exclusive alternatives (body, body_text, body_file;
                // disconnect_after_events or _bytes; request or signal) are covered by
                // the other fixtures' steps
                continue;
            }
            let without = remove(base.clone(), &format!("{at}/{member}"));
            let result = load(&without);
            if object.required.contains(member) {
                let err = result.expect_err(&format!("{} without {member}", object.name));
                assert_eq!(err.pointer, at, "{} without {member}: {err}", object.name);
                if object.name == "request_raw" {
                    // raw is what makes a request raw: without it, the request is read as
                    // a structured one, which misses its own required members
                    assert!(matches!(err.kind, ErrorKind::MissingField { .. }), "{err}");
                } else {
                    assert_eq!(
                        err.kind,
                        ErrorKind::MissingField { field: member },
                        "{} without {member}",
                        object.name
                    );
                }
            } else {
                assert!(
                    result.is_ok(),
                    "{} without the optional {member}: {:?}",
                    object.name,
                    result.err()
                );
            }
        }
    }
}

#[test]
fn concurrent_groups_are_contiguous() {
    let req = json!({"method": "GET", "path": "/"});
    let ok = json!([
        {"request": req, "concurrent_group": "a"}, {"request": req, "concurrent_group": "a"},
        {"request": req}, {"request": req, "concurrent_group": "b"}
    ]);
    assert!(load(&set(minimal(), "/steps", ok)).is_ok());
    let split = json!([
        {"request": req, "concurrent_group": "a"}, {"request": req},
        {"request": req, "concurrent_group": "a"}
    ]);
    invalid(set(minimal(), "/steps", split), "/steps/2/concurrent_group");
    let interleaved = json!([
        {"request": req, "concurrent_group": "a"}, {"request": req, "concurrent_group": "b"},
        {"request": req, "concurrent_group": "a"}
    ]);
    invalid(
        set(minimal(), "/steps", interleaved),
        "/steps/2/concurrent_group",
    );
}

#[test]
fn request_rules() {
    let with = |r: Value| set(minimal(), "/steps", json!([{"request": r}]));
    for field in ["method", "path"] {
        let mut r = json!({"method": "GET", "path": "/"});
        r.as_object_mut().unwrap().shift_remove(field);
        assert!(matches!(
            fails(with(r), "/steps/0/request"),
            ErrorKind::MissingField { .. }
        ));
    }
    for bad in ["get", "GET1", "G-T"] {
        invalid(
            with(json!({"method": bad, "path": "/"})),
            "/steps/0/request/method",
        );
    }
    assert!(load(&with(json!({"method": "OPTIONS", "path": "*"}))).is_ok());
    for bad in ["health", "/a b", "/a\tb", "/a\u{7f}"] {
        invalid(
            with(json!({"method": "GET", "path": bad})),
            "/steps/0/request/path",
        );
    }
    assert_eq!(
        fails(
            with(json!({"method": "GET", "path": "/", "url": "x"})),
            "/steps/0/request"
        ),
        ErrorKind::UnknownField {
            field: "url".into()
        }
    );
    for (a, b) in [
        ("body", "body_text"),
        ("body", "body_file"),
        ("body_text", "body_file"),
    ] {
        let mut r = json!({"method": "POST", "path": "/"});
        r[a] = json!("x");
        r[b] = json!("x");
        assert_eq!(
            fails(with(r), "/steps/0/request"),
            ErrorKind::Exclusive {
                first: a,
                second: b
            }
        );
    }
    invalid(
        with(json!({"method": "POST", "path": "/", "body_file": "../x.json"})),
        "/steps/0/request/body_file",
    );
    invalid(
        with(json!({"method": "GET", "path": "/", "http_version": "2"})),
        "/steps/0/request/http_version",
    );
    assert!(matches!(
        fails(
            with(json!({"method": "GET", "path": "/", "http_version": 1.1})),
            "/steps/0/request/http_version"
        ),
        ErrorKind::WrongType { .. }
    ));
    assert!(
        load(&with(json!({"method": "POST", "path": "/", "body": null}))).is_ok(),
        "a JSON null body is sent as null"
    );
}

#[test]
fn header_rules() {
    let with = |h: Value| {
        set(
            minimal(),
            "/steps",
            json!([{"request": {"method": "GET", "path": "/", "headers": h}}]),
        )
    };
    invalid(with(json!([["A"]])), "/steps/0/request/headers/0");
    assert_eq!(
        fails(with(json!([["A", "1", "2"]])), "/steps/0/request/headers/0"),
        ErrorKind::TooMany { limit: 2 }
    );
    assert!(matches!(
        fails(with(json!({"A": "1"})), "/steps/0/request/headers"),
        ErrorKind::WrongType { .. }
    ));
    invalid(
        with(json!([["Bad Name", "1"]])),
        "/steps/0/request/headers/0/0",
    );
    invalid(with(json!([["A:", "1"]])), "/steps/0/request/headers/0/0");
    for bad in ["a\r\nB: c", "a\nb", "a\u{0}"] {
        invalid(with(json!([["A", bad]])), "/steps/0/request/headers/0/1");
    }
    assert!(
        load(&with(json!([["A", ""]]))).is_ok(),
        "an empty header value is allowed"
    );
    assert_eq!(
        fails(
            with(json!(vec![json!(["A", "1"]); 65])),
            "/steps/0/request/headers"
        ),
        ErrorKind::TooMany { limit: 64 }
    );
}

#[test]
fn raw_request_rules() {
    let with = |r: Value| set(minimal(), "/steps", json!([{"request": r}]));
    assert_eq!(
        fails(
            with(json!({"raw": "GET / HTTP/1.0\r\n\r\n", "method": "GET"})),
            "/steps/0/request"
        ),
        ErrorKind::UnknownField {
            field: "method".into()
        }
    );
    assert_eq!(
        fails(with(json!({"raw": ""})), "/steps/0/request/raw"),
        ErrorKind::Empty
    );
}

// ------------------------------------------------------------------ observe

#[test]
fn observe_rules() {
    invalid(set(minimal(), "/observe", json!({})), "/observe");
    invalid(
        set(minimal(), "/observe", json!({"http": false, "exit": false})),
        "/observe",
    );
    assert_eq!(
        fails(
            set(minimal(), "/observe", json!({"stdout": true})),
            "/observe"
        ),
        ErrorKind::UnknownField {
            field: "stdout".into()
        }
    );
    assert!(matches!(
        fails(
            set(minimal(), "/observe", json!({"http": "yes"})),
            "/observe/http"
        ),
        ErrorKind::WrongType {
            expected: "boolean",
            ..
        }
    ));
    assert_eq!(
        fails(
            set(minimal(), "/observe", json!({"files": []})),
            "/observe/files"
        ),
        ErrorKind::Empty
    );
    for bad in ["/abs/*", "../x", "a/***", "a//b"] {
        invalid(
            set(minimal(), "/observe", json!({"files": [bad]})),
            "/observe/files/0",
        );
    }
    invalid(
        set(minimal(), "/observe", json!({"log": ["Bad Id"]})),
        "/observe/log/0",
    );
    for (field, value) in [
        ("engine_tape", json!(true)),
        ("exit", json!(true)),
        ("log", json!(["a"])),
        ("files", json!(["*.json"])),
    ] {
        assert!(
            load(&set(minimal(), "/observe", json!({field: value}))).is_ok(),
            "{field}"
        );
    }
}

// ------------------------------------------------------------------ tokens

#[test]
fn unknown_token_anywhere_is_refused_at_its_string() {
    assert_eq!(
        fails(
            set(minimal(), "/engine/info", json!({"a": ["{{loopbak}}"]})),
            "/engine/info/a/0"
        ),
        ErrorKind::UnknownToken {
            token: "{{loopbak}}".into()
        }
    );
    let v = set(
        minimal(),
        "/steps",
        json!([{"request": {"method": "GET", "path": "/", "headers": [["Host", "{{hostname}}"]]}}]),
    );
    assert!(matches!(
        fails(v, "/steps/0/request/headers/0/1"),
        ErrorKind::UnknownToken { .. }
    ));
}

#[test]
fn expand_fills_every_token_and_checks_again() {
    let v = set(
        minimal(),
        "/steps",
        json!([{"request": {"method": "GET", "path": "/v1/models",
            "headers": [["Host", "{{loopback}}:{{port}}"], ["Authorization", "Bearer {{key_short}}"]]}}]),
    );
    let v = set(
        v,
        "/server",
        json!({"config": {"log": "{{tmp}}/engine.log"}}),
    );
    let s = load(&v).unwrap();
    let subs = Substitutions::new()
        .with_loopback("127.0.0.1")
        .unwrap()
        .with_port(41000)
        .with_tmp("/tmp/cnf")
        .unwrap()
        .with_key_short("k1")
        .unwrap();
    let e = s.expand(&subs).unwrap();
    let Some(Request::Structured(r)) = &e.steps[0].request else {
        panic!()
    };
    assert_eq!(r.headers[0].1, "127.0.0.1:41000");
    assert_eq!(r.headers[1].1, "Bearer k1");
    assert_eq!(e.server.config["log"], "/tmp/cnf/engine.log");
    // the original keeps its tokens
    assert_eq!(s.source()["server"]["config"]["log"], "{{tmp}}/engine.log");

    let partial = Substitutions::new().with_loopback("127.0.0.1").unwrap();
    let err = s.expand(&partial).unwrap_err();
    assert_eq!(err.pointer, "/steps/0/request/headers/0/1");
    assert_eq!(
        err.kind,
        ErrorKind::UnboundToken {
            token: "{{port}}".into()
        }
    );
}

#[test]
fn expansion_that_breaks_the_format_is_caught() {
    // a {{tmp}} value with a space makes the request path invalid after expansion
    let v = set(
        minimal(),
        "/steps",
        json!([{"request": {"method": "GET", "path": "/files{{tmp}}"}}]),
    );
    let s = load(&v).unwrap();
    let subs = Substitutions::new().with_tmp("/a b").unwrap();
    let err = s.expand(&subs).unwrap_err();
    assert_eq!(err.pointer, "/steps/0/request/path");
}

// ------------------------------------------------------------------ files

#[test]
fn from_path_checks_the_file_stem_and_the_size() {
    let dir = std::env::temp_dir().join(format!("cnf02-scenario-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    let good = dir.join("min.json");
    std::fs::write(&good, minimal().to_string()).unwrap();
    assert_eq!(Scenario::from_path(&good).unwrap().id, "min");
    let other = dir.join("other.json");
    std::fs::write(&other, minimal().to_string()).unwrap();
    let err = Scenario::from_path(&other).unwrap_err();
    assert_eq!(
        err.kind,
        ErrorKind::IdMismatch {
            file_stem: "other".into()
        }
    );
    let big = dir.join("big.json");
    std::fs::write(&big, " ".repeat(limits::MAX_SCENARIO_BYTES + 10)).unwrap();
    assert_eq!(
        Scenario::from_path(&big).unwrap_err().kind,
        ErrorKind::TooLarge {
            limit: limits::MAX_SCENARIO_BYTES
        }
    );
    let missing = Scenario::from_path(&dir.join("absent.json")).unwrap_err();
    assert!(matches!(missing.kind, ErrorKind::Io { .. }));
    let bad_utf8 = dir.join("bin.json");
    std::fs::write(&bad_utf8, [0xffu8, 0xfe]).unwrap();
    assert!(matches!(
        Scenario::from_path(&bad_utf8).unwrap_err().kind,
        ErrorKind::Io { .. }
    ));
    std::fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn errors_display_their_pointer() {
    let err = load(&set(minimal(), "/engine/max_context", json!(0))).unwrap_err();
    assert_eq!(
        err.to_string(),
        "/engine/max_context: out of range: allowed 1 to 16777216"
    );
    let err = load(&remove(minimal(), "/id")).unwrap_err();
    assert_eq!(err.to_string(), "(document): missing field \"id\"");
}
