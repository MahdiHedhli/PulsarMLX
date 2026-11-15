//! Request checks of work package API-04: the sampling fields, the loop guard,
//! `logit_bias`, `ablate`, `ignore_eos`, `logprobs`, stop strings, the answer budget and the
//! underscore stripping of deviation SEC-6.
//!
//! Provenance: translated from project-maya serve/test_server.py::RequestChecks at 7e68a30f (MIT); license text in console/LICENSES/project-maya-MIT.txt.
//! Provenance: translated from project-maya serve/test_logprobs.py::Fields at 7e68a30f (MIT); license text in console/LICENSES/project-maya-MIT.txt.
//!
//! The donor's `Service` with its `MockEngine` and `ByteTokenizer` is stood in for by a
//! [`CheckContext`]: the mock engine advertises `INFO logit_bias=1` and `INFO logprobs=20`,
//! the byte tokenizer has no `tokens` list (no vocabulary size), and its stop and end ids
//! are 257 (`<|im_end|>`) and 258 (`<|endoftext|>`). Every other expected value is the
//! donor's. Messages that the donor ends with its setup script use the product wording
//! (BRAND-1, contracts/naming.md section 3.8).

use console_core::engine::EngineCaps;
use console_core::request::{
    anthropic_max_tokens, check_request, check_request_sampling, client_stop_strings,
    logit_bias_of, logprobs_asked, logprobs_of, openai_max_tokens, strip_internal_keys,
    CheckContext, RequestError,
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

/// The donor's `Service(MockEngine(ByteTokenizer()))`, as far as the checks see it.
fn mock_service() -> CheckContext {
    CheckContext {
        caps: EngineCaps {
            logit_bias: true,
            logprobs_max: Some(20),
            ..EngineCaps::default()
        },
        vocab_size: None,
        end_ids: vec![258, 257],
    }
}

/// An engine from before `logit_bias`: `svc.engine.info = {}`.
fn bare_engine() -> CheckContext {
    CheckContext {
        caps: EngineCaps::default(),
        ..mock_service()
    }
}

fn invalid(m: &str) -> RequestError {
    RequestError::Invalid(m.to_string())
}

fn sampling_error(src: &str) -> RequestError {
    let mut m = obj(src);
    match check_request_sampling(&mut m) {
        Err(e) => e,
        Ok(()) => panic!("{src} was accepted: {m:?}"),
    }
}

// Donor: serve/test_server.py::RequestChecks::test_numeric_strings
#[test]
fn numeric_strings() {
    let mut req = obj(
        r#"{"temperature": "0.7", "top_k": "40", "seed": " 12 ", "top_p": "1", "min_p": null}"#,
    );
    check_request_sampling(&mut req).unwrap();
    // The stored text is the Python type: 0.7 a float, 40, 12 and 1 ints.
    assert_eq!(req["temperature"].to_string(), "0.7");
    assert_eq!(req["top_k"].to_string(), "40");
    assert_eq!(req["seed"].to_string(), "12");
    assert_eq!(req["top_p"].to_string(), "1");
    assert_eq!(req["min_p"], Value::Null);
    let mut req = obj(r#"{"top_k": "40.0"}"#);
    check_request_sampling(&mut req).unwrap();
    assert_eq!(req["top_k"].to_string(), "40");
}

// Donor: serve/test_server.py::RequestChecks::test_wrong_types_name_the_field
#[test]
fn wrong_types_name_the_field() {
    for (bad, msg) in [
        (r#"{"temperature": "warm"}"#, "temperature: a number"),
        (r#"{"top_k": 40.5}"#, "top_k: an integer"),
        (r#"{"top_k": "40.5"}"#, "top_k: an integer"),
        (r#"{"seed": true}"#, "seed: an integer"),
        (r#"{"top_p": "nan"}"#, "top_p: a number"),
        (r#"{"min_p": [0.1]}"#, "min_p: a number"),
    ] {
        assert_eq!(sampling_error(bad), invalid(msg), "{bad}");
    }
}

// Donor: serve/test_server.py::RequestChecks::test_llama_cpp_names
#[test]
fn llama_cpp_names() {
    let mut req = obj(r#"{"repeat_penalty": 1.1, "repeat_last_n": 128}"#);
    check_request_sampling(&mut req).unwrap();
    assert_eq!(req["repetition_penalty"].to_string(), "1.1");
    assert_eq!(req["penalty_last_n"].to_string(), "128");
    // The copies are appended, as a Python dict assignment appends a new key.
    let keys: Vec<_> = req.keys().map(String::as_str).collect();
    assert_eq!(
        keys,
        [
            "repeat_penalty",
            "repeat_last_n",
            "repetition_penalty",
            "penalty_last_n"
        ]
    );
    let mut req = obj(r#"{"repeat_penalty": 1.1, "repetition_penalty": 1.3, "repeat_last_n": -1}"#);
    check_request_sampling(&mut req).unwrap();
    assert_eq!(req["repetition_penalty"].to_string(), "1.3");
    assert_eq!(req["penalty_last_n"].to_string(), "-1"); // the whole context
    let mut req = obj(r#"{"repeat_last_n": "0", "penalty_last_n": 32}"#);
    check_request_sampling(&mut req).unwrap();
    assert_eq!(req["penalty_last_n"].to_string(), "32"); // penalty_last_n wins
    let mut req = obj(r#"{"repeat_last_n": "0"}"#);
    check_request_sampling(&mut req).unwrap();
    assert_eq!(req["penalty_last_n"].to_string(), "0"); // no penalties
    let window = "-1 (the whole context), 0 (no penalties) or a positive number of tokens";
    for (bad, msg) in [
        (
            r#"{"repeat_last_n": -2}"#,
            format!("repeat_last_n: {window}"),
        ),
        (
            r#"{"penalty_last_n": -5}"#,
            format!("penalty_last_n: {window}"),
        ),
        (
            r#"{"repeat_last_n": 1.5}"#,
            String::from("repeat_last_n: an integer"),
        ),
    ] {
        assert_eq!(sampling_error(bad), invalid(&msg), "{bad}");
    }
}

// Donor: serve/test_server.py::RequestChecks::test_logit_bias
#[test]
fn logit_bias() {
    let got = logit_bias_of(&val(r#"{"12": -100, "7": 2}"#), None).unwrap();
    assert_eq!(got.entries(), &[(12, -100.0), (7, 2.0)]);
    assert!(logit_bias_of(&Value::Null, None).unwrap().is_empty());
    for (bad, msg) in [
        (
            "[[1, 2]]",
            "logit_bias: an object of {\"<token id>\": bias}",
        ),
        (
            r#"{"x": 1}"#,
            "logit_bias: token ids are non-negative integers",
        ),
        (
            r#"{"-1": 1}"#,
            "logit_bias: token ids are non-negative integers",
        ),
        (
            r#"{"5": 101}"#,
            "logit_bias: biases are numbers from -100 to 100",
        ),
        (
            r#"{"5": true}"#,
            "logit_bias: biases are numbers from -100 to 100",
        ),
        (
            r#"{"5": "a"}"#,
            "logit_bias: biases are numbers from -100 to 100",
        ),
        (
            r#"{"300": 1}"#,
            "logit_bias: token 300 is outside the model's vocabulary",
        ),
    ] {
        assert_eq!(
            logit_bias_of(&val(bad), Some(256)),
            Err(invalid(msg)),
            "{bad}"
        );
    }
    let all = val(r#"{"0": -100, "1": -100, "2": -100, "3": -100}"#);
    assert_eq!(
        logit_bias_of(&all, Some(4)),
        Err(invalid("logit_bias: it cannot ban the whole vocabulary"))
    );
}

// Donor: serve/test_server.py::RequestChecks::test_engine_must_apply_it
#[test]
fn engine_must_apply_it() {
    let mut req = obj(r#"{"logit_bias": {"65": "-100"}}"#);
    let checked = check_request(&mut req, &mock_service()).unwrap();
    assert_eq!(req["logit_bias"], val(r#"{"65": -100.0}"#));
    assert_eq!(checked.logit_bias.unwrap().entries(), &[(65, -100.0)]);
    // An engine from before logit_bias: refused, not ignored.
    let mut req = obj(r#"{"logit_bias": {"65": 1}}"#);
    assert_eq!(
        check_request(&mut req, &bare_engine()),
        Err(invalid(
            "logit_bias: this engine does not apply token biases - update PulsarMLX Console"
        ))
    );
    // None asked for: fine anywhere.
    let mut req = obj(r#"{"logit_bias": {}}"#);
    check_request(&mut req, &bare_engine()).unwrap();
    assert_eq!(req["logit_bias"], val("{}"));
}

// Donor: serve/test_server.py::RequestChecks::test_ablate
// Deviation POL-1: `ablate` is recognized and refused unless the engine advertises it. The
// donor's `ablate_state` and its `ablate=1` engine key are not ported (POL-1.2, POL-1.3),
// so those assertions of the donor method are replaced by the typed flag.
#[test]
fn ablate_is_recognized_and_refused_unless_advertised() {
    let svc = mock_service();
    let mut off = obj(r#"{"ablate": false}"#);
    assert!(!check_request(&mut off, &svc).unwrap().ablate); // off: fine anywhere
    let mut on = obj(r#"{"ablate": true}"#);
    assert_eq!(
        check_request(&mut on, &svc),
        Err(invalid(
            "ablate: this model has no refusal direction loaded"
        ))
    );
    let mut word = obj(r#"{"ablate": "yes"}"#);
    assert_eq!(
        check_request(&mut word, &svc),
        Err(invalid("ablate: true or false"))
    );
    let advertised = CheckContext {
        caps: EngineCaps {
            ablate: true,
            ..svc.caps
        },
        ..svc.clone()
    };
    let mut on = obj(r#"{"ablate": true}"#);
    assert!(check_request(&mut on, &advertised).unwrap().ablate);
    // No engine of this increment advertises it: the default capability set refuses.
    assert!(!EngineCaps::default().ablate);
}

// Donor: serve/test_server.py::RequestChecks::test_ignore_eos
// (The donor's last assertion on the engine line's `logit_bias=` text belongs to the
// engine encoder of ENG-03; the sorted pairs it encodes are asserted here.)
#[test]
fn ignore_eos() {
    let svc = mock_service();
    let mut req =
        obj(r#"{"ignore_eos": true, "max_tokens": 64, "logit_bias": {"65": 2, "257": 5}}"#);
    let checked = check_request(&mut req, &svc).unwrap();
    assert_eq!(
        req["logit_bias"],
        val(r#"{"65": 2.0, "257": -100.0, "258": -100.0}"#)
    );
    assert!(checked.ignore_eos);
    let mut req = obj(r#"{"ignore_eos": true, "max_completion_tokens": "32"}"#);
    let checked = check_request(&mut req, &svc).unwrap();
    assert_eq!(req["logit_bias"], val(r#"{"257": -100.0, "258": -100.0}"#));
    let sorted = checked.logit_bias.unwrap().sorted();
    assert_eq!(sorted, vec![(257, -100.0), (258, -100.0)]);
    let mut req = obj(r#"{"ignore_eos": false, "max_tokens": 8}"#);
    let checked = check_request(&mut req, &svc).unwrap();
    assert!(!req.contains_key("logit_bias"));
    assert_eq!(checked.logit_bias, None);
    let needs = "ignore_eos: needs max_tokens (the answer would run until the context is full)";
    for (bad, msg) in [
        (r#"{"ignore_eos": true}"#, needs),
        (r#"{"ignore_eos": true, "max_tokens": 0}"#, needs),
        (
            r#"{"ignore_eos": "yes", "max_tokens": 8}"#,
            "ignore_eos: true or false",
        ),
    ] {
        let mut m = obj(bad);
        assert_eq!(check_request(&mut m, &svc), Err(invalid(msg)), "{bad}");
    }
    // An engine that applies no biases: refused, not ignored.
    let mut req = obj(r#"{"ignore_eos": true, "max_tokens": 8}"#);
    assert_eq!(
        check_request(&mut req, &bare_engine()),
        Err(invalid(
            "ignore_eos: this engine does not apply token biases - update PulsarMLX Console"
        ))
    );
}

// Donor: serve/test_logprobs.py::Fields::test_asking
#[test]
fn logprobs_asking() {
    assert_eq!(logprobs_of(&obj("{}")), Ok(None));
    assert_eq!(logprobs_of(&obj(r#"{"logprobs": false}"#)), Ok(None));
    assert_eq!(logprobs_of(&obj(r#"{"logprobs": true}"#)), Ok(Some(0)));
    assert_eq!(
        logprobs_of(&obj(r#"{"logprobs": true, "top_logprobs": 20}"#)),
        Ok(Some(20))
    );
    assert_eq!(
        logprobs_of(&obj(r#"{"logprobs": true, "top_logprobs": "5"}"#)),
        Ok(Some(5))
    );
    assert_eq!(
        logprobs_of(&obj(r#"{"logprobs": true, "top_logprobs": null}"#)),
        Ok(Some(0))
    );
}

// Donor: serve/test_logprobs.py::Fields::test_refused
#[test]
fn logprobs_refused() {
    let range = "top_logprobs: an integer from 0 to 20";
    for (bad, msg) in [
        (r#"{"logprobs": 1}"#, "logprobs: true or false"),
        (r#"{"logprobs": "yes"}"#, "logprobs: true or false"),
        (
            r#"{"top_logprobs": 3}"#,
            "top_logprobs: it needs \"logprobs\": true",
        ),
        (
            r#"{"logprobs": false, "top_logprobs": 3}"#,
            "top_logprobs: it needs \"logprobs\": true",
        ),
        (r#"{"logprobs": true, "top_logprobs": 21}"#, range),
        (r#"{"logprobs": true, "top_logprobs": -1}"#, range),
        (r#"{"logprobs": true, "top_logprobs": true}"#, range),
        (r#"{"logprobs": true, "top_logprobs": 2.5}"#, range),
    ] {
        assert_eq!(logprobs_of(&obj(bad)), Err(invalid(msg)), "{bad}");
        assert_eq!(logprobs_asked(&obj(bad)), None, "{bad}");
    }
}

/// Every message of the donor's `check_request_sampling`, `logit_bias_of`,
/// `logprobs_of` and `Service.check_request`, with an input that triggers it.
#[test]
fn every_check_request_message_with_its_input() {
    let window = "-1 (the whole context), 0 (no penalties) or a positive number of tokens";
    let svc = mock_service();
    let no_logprobs = CheckContext {
        caps: EngineCaps {
            logprobs_max: None,
            ..svc.caps
        },
        ..svc.clone()
    };
    let three = CheckContext {
        caps: EngineCaps {
            logprobs_max: Some(3),
            ..svc.caps
        },
        ..svc.clone()
    };
    let vocab = CheckContext {
        vocab_size: Some(2),
        ..svc.clone()
    };
    let bare = bare_engine();
    let lp_msg = "logprobs: this model's engine does not report token log-probabilities (the \
                  DeepSeek engine does - update PulsarMLX Console if it is that one)";
    let cases: Vec<(&str, &CheckContext, String)> = vec![
        (
            r#"{"temperature": "hot"}"#,
            &svc,
            "temperature: a number".into(),
        ),
        (r#"{"top_p": false}"#, &svc, "top_p: a number".into()),
        (r#"{"min_p": "inf"}"#, &svc, "min_p: a number".into()),
        (
            r#"{"presence_penalty": "  "}"#,
            &svc,
            "presence_penalty: a number".into(),
        ),
        (
            r#"{"frequency_penalty": {}}"#,
            &svc,
            "frequency_penalty: a number".into(),
        ),
        (
            r#"{"repetition_penalty": "1,1"}"#,
            &svc,
            "repetition_penalty: a number".into(),
        ),
        (r#"{"top_k": "4e-1"}"#, &svc, "top_k: an integer".into()),
        (
            r#"{"penalty_last_n": 64.0}"#,
            &svc,
            "penalty_last_n: an integer".into(),
        ),
        (
            r#"{"repeat_last_n": "x"}"#,
            &svc,
            "repeat_last_n: an integer".into(),
        ),
        (r#"{"seed": "-Infinity"}"#, &svc, "seed: an integer".into()),
        (
            r#"{"penalty_last_n": "-3"}"#,
            &svc,
            format!("penalty_last_n: {window}"),
        ),
        (
            r#"{"repeat_last_n": -7}"#,
            &svc,
            format!("repeat_last_n: {window}"),
        ),
        (
            r#"{"loop_guard": "maybe"}"#,
            &svc,
            "loop_guard: true or false".into(),
        ),
        (
            r#"{"loop_guard": 2}"#,
            &svc,
            "loop_guard: true or false".into(),
        ),
        (
            r#"{"loop_guard": 1.0}"#,
            &svc,
            "loop_guard: true or false".into(),
        ),
        (
            r#"{"logit_bias": "65:-100"}"#,
            &svc,
            "logit_bias: an object of {\"<token id>\": bias}".into(),
        ),
        (
            r#"{"logit_bias": {"6 5": 1}}"#,
            &svc,
            "logit_bias: token ids are non-negative integers".into(),
        ),
        (
            r#"{"logit_bias": {"2147483648": 1}}"#,
            &svc,
            "logit_bias: token 2147483648 is outside the model's vocabulary".into(),
        ),
        (
            r#"{"logit_bias": {"0002": 1}}"#,
            &vocab,
            "logit_bias: token 2 is outside the model's vocabulary".into(),
        ),
        (
            r#"{"logit_bias": {"1": -100.5}}"#,
            &svc,
            "logit_bias: biases are numbers from -100 to 100".into(),
        ),
        (
            r#"{"logit_bias": {"1": NaN}}"#,
            &svc,
            "logit_bias: biases are numbers from -100 to 100".into(),
        ),
        (
            r#"{"logit_bias": {"1": null}}"#,
            &svc,
            "logit_bias: biases are numbers from -100 to 100".into(),
        ),
        (
            r#"{"logit_bias": {"0": -100, "1": "-100"}}"#,
            &vocab,
            "logit_bias: it cannot ban the whole vocabulary".into(),
        ),
        (
            r#"{"logit_bias": {"1": 1}}"#,
            &bare,
            "logit_bias: this engine does not apply token biases - update PulsarMLX Console".into(),
        ),
        (r#"{"ablate": 1}"#, &svc, "ablate: true or false".into()),
        (
            r#"{"ablate": true}"#,
            &svc,
            "ablate: this model has no refusal direction loaded".into(),
        ),
        (
            r#"{"ignore_eos": 1, "max_tokens": 8}"#,
            &svc,
            "ignore_eos: true or false".into(),
        ),
        (
            r#"{"ignore_eos": true, "max_tokens": "lots"}"#,
            &svc,
            "ignore_eos: needs max_tokens (the answer would run until the context is full)".into(),
        ),
        (
            r#"{"ignore_eos": true, "max_tokens": -1}"#,
            &svc,
            "ignore_eos: needs max_tokens (the answer would run until the context is full)".into(),
        ),
        (
            r#"{"ignore_eos": true, "max_tokens": 8}"#,
            &bare,
            "ignore_eos: this engine does not apply token biases - update PulsarMLX Console".into(),
        ),
        (
            r#"{"logprobs": "true"}"#,
            &svc,
            "logprobs: true or false".into(),
        ),
        (
            r#"{"logprobs": true, "top_logprobs": "-1"}"#,
            &svc,
            "top_logprobs: an integer from 0 to 20".into(),
        ),
        (
            r#"{"top_logprobs": 0}"#,
            &svc,
            "top_logprobs: it needs \"logprobs\": true".into(),
        ),
        (r#"{"logprobs": true}"#, &no_logprobs, lp_msg.into()),
        (
            r#"{"logprobs": true, "top_logprobs": 4}"#,
            &three,
            lp_msg.into(),
        ),
    ];
    for (src, ctx, msg) in cases {
        let mut m = obj(src);
        assert_eq!(check_request(&mut m, ctx), Err(invalid(&msg)), "{src}");
    }
    // At the engine's own maximum it passes, and a string top_logprobs is stored as an int.
    let mut m = obj(r#"{"logprobs": true, "top_logprobs": " 3 "}"#);
    assert_eq!(check_request(&mut m, &three).unwrap().logprobs, Some(3));
    assert_eq!(m["top_logprobs"].to_string(), "3");
}

#[test]
fn python_numeric_coercions() {
    // A non-integer field keeps the int type for a signed digit string, else a float.
    let mut m = obj(
        r#"{"temperature": " +1 ", "top_p": "1e0", "min_p": "٣", "presence_penalty": "1_0.5"}"#,
    );
    check_request_sampling(&mut m).unwrap();
    assert_eq!(m["temperature"].to_string(), "1");
    assert_eq!(m["top_p"].to_string(), "1.0");
    assert_eq!(m["min_p"].to_string(), "3");
    assert_eq!(m["presence_penalty"].to_string(), "10.5");
    // An integer field takes an integral float text, and a huge integer stays exact.
    let mut m = obj(r#"{"seed": "1e30", "top_k": 123456789012345678901234567890}"#);
    check_request_sampling(&mut m).unwrap();
    assert_eq!(m["seed"].to_string(), "1000000000000000019884624838656");
    assert_eq!(m["top_k"].to_string(), "123456789012345678901234567890");
    // A JSON float is accepted for a number field whatever its size (the donor checks
    // only strings for NaN and the infinities).
    let mut m = obj(r#"{"temperature": Infinity, "top_p": 2}"#);
    check_request_sampling(&mut m).unwrap();
    // A digit string padded past Python's 4300-digit limit raises Python's message.
    let padded = format!("{{\"temperature\": \"{}1\"}}", "0".repeat(4300));
    let err = sampling_error(&padded);
    assert!(
        err.message().starts_with("Exceeds the limit (4300 digits)"),
        "{err}"
    );
    // Loop guard words and integers become bools; null and bools are left alone.
    for (src, want) in [
        (r#"{"loop_guard": " ON "}"#, Some(true)),
        (r#"{"loop_guard": "Off"}"#, Some(false)),
        (r#"{"loop_guard": "1"}"#, Some(true)),
        (r#"{"loop_guard": 0}"#, Some(false)),
        (r#"{"loop_guard": true}"#, Some(true)),
        (r#"{"loop_guard": null}"#, None),
    ] {
        let mut m = obj(src);
        let got = check_request(&mut m, &mock_service()).unwrap().loop_guard;
        assert_eq!(got, want, "{src}");
    }
}

/// CPython's `float()` and `int()` strip only space, `\t`, `\n`, `\v`, `\f`, `\r` and
/// non-ASCII whitespace; the ASCII separators U+001C..U+001F, which `str.strip()` and the
/// `re` class `\s` accept, make the number text invalid.
#[test]
fn ascii_separators_are_not_number_whitespace() {
    for (bad, msg) in [
        (r#"{"temperature": "5\u001c"}"#, "temperature: a number"),
        (r#"{"temperature": "0.7\u001c"}"#, "temperature: a number"),
        (r#"{"top_p": "\u001f0.5"}"#, "top_p: a number"),
        (r#"{"top_k": "40\u001c"}"#, "top_k: an integer"),
    ] {
        assert_eq!(sampling_error(bad), invalid(msg), "{bad}");
    }
    // Non-ASCII whitespace is still stripped.
    let mut m = obj(r#"{"temperature": "0.5\u0085", "top_k": "　40"}"#);
    check_request_sampling(&mut m).unwrap();
    assert_eq!(m["temperature"].to_string(), "0.5");
    assert_eq!(m["top_k"].to_string(), "40");
    // `\s*\d+\s*` matches, then `int()` raises its own message.
    assert_eq!(
        logprobs_of(&obj(r#"{"logprobs": true, "top_logprobs": "5\u001c"}"#)),
        Err(invalid("invalid literal for int() with base 10: '5\\x1c'"))
    );
    assert_eq!(
        logit_bias_of(&val(r#"{"1": "2\u001c"}"#), None),
        Err(invalid("logit_bias: biases are numbers from -100 to 100"))
    );
    assert_eq!(
        openai_max_tokens(&obj(r#"{"max_tokens": "8\u001c"}"#)),
        Err(invalid("invalid literal for int() with base 10: '8\\x1c'"))
    );
    assert_eq!(
        anthropic_max_tokens(&obj(r#"{"max_tokens": "\u001e8"}"#)),
        Err(invalid("invalid literal for int() with base 10: '\\x1e8'"))
    );
    // `ignore_eos` catches the int() error: no budget, so refused.
    let mut m = obj(r#"{"ignore_eos": true, "max_tokens": "8\u001c"}"#);
    assert_eq!(
        check_request(&mut m, &mock_service()),
        Err(invalid(
            "ignore_eos: needs max_tokens (the answer would run until the context is full)"
        ))
    );
}

#[test]
fn logit_bias_quirks() {
    // A repeated id keeps its first position and takes the later bias.
    let b = logit_bias_of(&val(r#"{"7": 1, "3": 2, "07": -5.5}"#), None).unwrap();
    assert_eq!(b.entries(), &[(7, -5.5), (3, 2.0)]);
    assert_eq!(b.sorted(), vec![(3, 2.0), (7, -5.5)]);
    // Numeric strings use Python's float(); a huge id names its digits.
    let b = logit_bias_of(&val(r#"{"1": " -1e2 ", "2": "1_0"}"#), None).unwrap();
    assert_eq!(b.entries(), &[(1, -100.0), (2, 10.0)]);
    let big = format!("{{\"{}\": 1}}", "9".repeat(40));
    assert_eq!(
        logit_bias_of(&val(&big), None),
        Err(invalid(&format!(
            "logit_bias: token {} is outside the model's vocabulary",
            "9".repeat(40)
        )))
    );
    // Unicode digits are not ASCII token ids.
    assert_eq!(
        logit_bias_of(&val(r#"{"٣": 1}"#), None),
        Err(invalid("logit_bias: token ids are non-negative integers"))
    );
    // A vocabulary size of 0 skips the vocabulary checks, as `len(tokens) or None` does.
    assert!(logit_bias_of(&val(r#"{"300": -100}"#), Some(0)).is_ok());
}

#[test]
fn stop_strings() {
    assert_eq!(client_stop_strings(&obj(r#"{"stop": "END"}"#)), ["END"]);
    assert_eq!(
        client_stop_strings(&obj(r#"{"stop": ""}"#)),
        Vec::<String>::new()
    );
    assert_eq!(
        client_stop_strings(&obj(
            r#"{"stop": ["a", "", 3, null, "b"], "stop_sequences": ["z"]}"#
        )),
        ["a", "b"]
    );
    assert_eq!(
        client_stop_strings(&obj(r#"{"stop": null, "stop_sequences": ["z"]}"#)),
        ["z"]
    );
    assert_eq!(
        client_stop_strings(&obj(r#"{"stop": 5, "stop_sequences": ["z"]}"#)),
        Vec::<String>::new()
    );
    let many: Vec<String> = (0..20).map(|i| format!("\"s{i}\"")).collect();
    let got = client_stop_strings(&obj(&format!("{{\"stop\": [{}]}}", many.join(", "))));
    assert_eq!(got.len(), 16);
    assert_eq!(got[15], "s15");
}

#[test]
fn answer_budget() {
    let n = |src: &str| openai_max_tokens(&obj(src)).map(|i| i.to_string());
    assert_eq!(n("{}"), Ok("0".into()));
    assert_eq!(
        n(r#"{"max_tokens": 5, "max_completion_tokens": 9}"#),
        Ok("9".into())
    );
    assert_eq!(
        n(r#"{"max_tokens": 5, "max_completion_tokens": 0}"#),
        Ok("5".into())
    );
    assert_eq!(n(r#"{"max_tokens": " 1_000 "}"#), Ok("1000".into()));
    assert_eq!(n(r#"{"max_tokens": 2.9}"#), Ok("2".into()));
    assert_eq!(n(r#"{"max_tokens": true}"#), Ok("1".into()));
    assert_eq!(n(r#"{"max_tokens": -1}"#), Ok("-1".into()));
    assert_eq!(
        n(r#"{"max_tokens": "2.5"}"#),
        Err(invalid("invalid literal for int() with base 10: '2.5'"))
    );
    assert_eq!(
        openai_max_tokens(&obj(r#"{"max_tokens": [8]}"#)),
        Err(RequestError::type_error(
            "int() argument must be a string, a bytes-like object or a real number, not 'list'"
        ))
    );
    assert_eq!(
        openai_max_tokens(&obj(r#"{"max_tokens": NaN}"#)),
        Err(invalid("cannot convert float NaN to integer"))
    );
    assert_eq!(
        openai_max_tokens(&obj(r#"{"max_tokens": -Infinity}"#)),
        Err(RequestError::Overflow(
            "cannot convert float infinity to integer".into()
        ))
    );
    let a = |src: &str| anthropic_max_tokens(&obj(src)).map(|i| i.to_string());
    assert_eq!(
        a(r#"{"max_tokens": 7, "max_completion_tokens": 9}"#),
        Ok("7".into())
    );
    assert_eq!(a(r#"{"max_tokens": ""}"#), Ok("0".into()));
}

#[test]
fn ignore_eos_with_an_infinite_budget_is_python_s_overflow() {
    // The donor catches TypeError and ValueError around the budget, not OverflowError.
    let mut m = obj(r#"{"ignore_eos": true, "max_tokens": Infinity}"#);
    assert_eq!(
        check_request(&mut m, &mock_service()),
        Err(RequestError::Overflow(
            "cannot convert float infinity to integer".into()
        ))
    );
    // A list budget is a TypeError the donor catches: no budget, so refused.
    let mut m = obj(r#"{"ignore_eos": true, "max_tokens": [1]}"#);
    assert_eq!(
        check_request(&mut m, &mock_service()),
        Err(invalid(
            "ignore_eos: needs max_tokens (the answer would run until the context is full)"
        ))
    );
}

// Deviation SEC-6.1: a client's underscore keys never reach the checks.
#[test]
fn underscore_keys_never_reach_the_checks() {
    let mut req = obj(
        r#"{"_prefill": "forged", "_think_budget": 1, "_level_shared": true,
            "_restore": [1, 2], "logit_bias": {"65": 1}, "_logit_bias": 5}"#,
    );
    assert_eq!(strip_internal_keys(&mut req), 5);
    let checked = check_request(&mut req, &mock_service()).unwrap();
    assert_eq!(checked.logit_bias.unwrap().entries(), &[(65, 1.0)]);
    assert!(req.keys().all(|k| !k.starts_with('_')));
}
