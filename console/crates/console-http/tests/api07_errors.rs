//! Provenance: translated from project-maya serve/test_server.py::EngineDeath::test_error_then_restart and serve/test_server.py::EngineDeath::test_engine_err_mid_stream (their HTTP framing halves) at 7e68a30f (MIT); license text in console/LICENSES/project-maya-MIT.txt.
//!
//! API-07: every error class on the wire, before the first byte of the answer and after
//! it, through the probe dialect and ENG-02's failing engines. The ledger rows of the
//! donor's EngineDeath tests stay pending for API-08: they also assert OpenAI's chunks and
//! the metrics row.
//!
//! Behavior reference: project-maya serve/server.py:6152-6158, 6283-6297, 6607-6624 and
//! 6732-6734 at 7e68a30f.

#[path = "api07_kit.rs"]
mod kit;

use std::sync::Arc;

use console_engine::fake::doubles::{DyingEngine, ErrEngine};
use console_engine::fake::{FakeFactory, FakeScript};

use kit::{answer, chat, enc, Harness, Setup, CTX, END};

fn fake(script: Vec<u32>) -> FakeFactory {
    FakeFactory::new(FakeScript::new(script).max_context(CTX)).unwrap_or_else(|e| panic!("{e}"))
}

fn fail(at: &str, class: &str, after: u32) -> String {
    format!(", \"probe_fail\": {{\"at\": \"{at}\", \"class\": \"{class}\", \"after\": {after}}}")
}

/// Before the first byte: each class answers its status and body; an exception the donor
/// does not catch closes the connection with nothing written.
#[tokio::test]
async fn every_error_class_answers_its_status_before_the_first_byte() {
    let h = Harness::start(Setup::new(Arc::new(fake(answer("hello"))))).await;
    let cases: [(&str, u16, &str); 18] = [
        (
            "bad_body",
            413,
            r#"{"error": {"type": "invalid_request_error", "message": "too large"}}"#,
        ),
        (
            "job",
            409,
            r#"{"error": {"type": "server_error", "message": "the job is busy"}}"#,
        ),
        (
            "store_busy",
            503,
            r#"{"error": {"type": "server_error", "message": "the store is busy"}}"#,
        ),
        (
            "value",
            400,
            r#"{"error": {"type": "invalid_request_error", "message": "temperature: a number"}}"#,
        ),
        (
            "overflow",
            400,
            r#"{"error": {"type": "invalid_request_error", "message": "maximum context length is 4096 tokens; prompt (5000 tokens) leaves no room to answer in the context; requests are never truncated", "code": "context_length_exceeded"}}"#,
        ),
        (
            "died",
            503,
            r#"{"error": {"type": "server_error", "message": "the engine stopped unexpectedly (exit code -9); the next request restarts it"}}"#,
        ),
        (
            "protocol",
            500,
            r#"{"error": {"type": "server_error", "message": "engine protocol violation: token after the end"}}"#,
        ),
        (
            "start_failed",
            503,
            r#"{"error": {"type": "server_error", "message": "the engine exited before it was ready"}}"#,
        ),
        (
            "key",
            400,
            r#"{"error": {"type": "invalid_request_error", "message": "malformed request (KeyError: 'messages')"}}"#,
        ),
        (
            "type",
            400,
            r#"{"error": {"type": "invalid_request_error", "message": "malformed request (TypeError: not a list)"}}"#,
        ),
        (
            "index",
            400,
            r#"{"error": {"type": "invalid_request_error", "message": "malformed request (IndexError: token id 300 is outside the vocabulary (262))"}}"#,
        ),
        (
            "attribute",
            400,
            r#"{"error": {"type": "invalid_request_error", "message": "malformed request (AttributeError: 'str' object has no attribute 'get')"}}"#,
        ),
        // Approved deviation P-8, with a stand-in for PRM-03's template error.
        (
            "template",
            400,
            r#"{"error": {"type": "invalid_request_error", "message": "tools are not supported here"}}"#,
        ),
        // Approved deviation P-8, with a stand-in for PRM-07's encoder error.
        (
            "encoder",
            400,
            r#"{"error": {"type": "invalid_request_error", "message": "a tool result without a call"}}"#,
        ),
        (
            "refused",
            403,
            r#"{"error": {"message": "MCP tools can be used only from the own page"}}"#,
        ),
        (
            "permission",
            403,
            r#"{"error": {"type": "permission_error", "message": "not here"}}"#,
        ),
        ("uncaught", 0, ""),
        // A failure in the collected body is still before the first byte.
        (
            "body:value",
            400,
            r#"{"error": {"type": "invalid_request_error", "message": "temperature: a number"}}"#,
        ),
    ];
    for (class, status, body) in cases {
        let (at, class) = class.split_once(':').unwrap_or(("prepare", class));
        let got = h.call(&chat("hi", 8, false, &fail(at, class, 0))).await;
        assert_eq!(got.status, status, "{class}: {:?}", got.text());
        assert_eq!(got.text(), body, "{class}");
        if status == 0 {
            assert!(got.raw.is_empty(), "{class}: nothing is written");
        } else {
            assert_eq!(
                got.header("Content-Type"),
                Some("application/json"),
                "{class}"
            );
            assert_eq!(
                got.header("Content-Length"),
                Some(body.len().to_string().as_str()),
                "{class}"
            );
        }
    }
    // A token-level failure of a collected answer is also answered with its status.
    let got = h
        .call(&chat("hi", 8, false, &fail("token", "died", 2)))
        .await;
    assert_eq!(got.status, 503);
    // The donor logs a traceback for a malformed request and an uncaught exception, on
    // standard error (the error log), never on the main log.
    assert!(!h
        .log
        .lines()
        .iter()
        .any(|l| l.contains("traceback") || l.contains("exception while serving")));
    let lines = h.errors.lines();
    assert!(lines
        .iter()
        .any(|l| l.starts_with("[console] traceback: IndexError in a request from 127.0.0.1:")));
    assert!(lines.iter().any(|l| l
        .starts_with("[console] exception while serving a request from 127.0.0.1:")
        && l.ends_with(": OverflowError: cannot convert float infinity to integer")));
    h.stop().await;
}

/// After the first byte: the classes the donor's stream loop catches become the dialect's
/// error event and the stream's end; the others are only logged (`_fail`) or end the
/// connection, and the stream is cut.
#[tokio::test]
async fn after_the_first_byte_errors_are_stream_events_or_a_cut() {
    let h = Harness::start(Setup::new(Arc::new(fake(answer("hello world"))))).await;
    let two = "data: {\"text\": \"h\"}\n\ndata: {\"text\": \"e\"}\n\n";
    let event = |m: &str| {
        format!(
            "{two}data: {{\"error\": {{\"type\": \"server_error\", \"message\": \"{m}\"}}}}\n\ndata: [DONE]\n\n"
        )
    };
    let cases: [(&str, String); 13] = [
        ("value", event("temperature: a number")),
        (
            "overflow",
            event(
                "maximum context length is 4096 tokens; prompt (5000 tokens) leaves no room to \
                 answer in the context; requests are never truncated",
            ),
        ),
        (
            "died",
            event("the engine stopped unexpectedly (exit code -9); the next request restarts it"),
        ),
        (
            "protocol",
            event("engine protocol violation: token after the end"),
        ),
        (
            "start_failed",
            event("the engine exited before it was ready"),
        ),
        ("template", event("tools are not supported here")),
        ("encoder", event("a tool result without a call")),
        // `_fail` after the answer began: the log line only, and the connection closes.
        ("bad_body", two.to_owned()),
        ("job", two.to_owned()),
        ("index", two.to_owned()),
        ("key", two.to_owned()),
        ("permission", two.to_owned()),
        // Uncaught: the connection closes.
        ("uncaught", two.to_owned()),
    ];
    for (class, want) in cases {
        let got = h
            .call(&chat("hi", 64, true, &fail("token", class, 2)))
            .await;
        assert_eq!(got.status, 200, "{class}");
        assert_eq!(got.text(), want, "{class}");
        assert!(!got.text().contains("HTTP/1"), "{class}");
    }
    // A failure of the stream's end frames.
    let got = h.call(&chat("hi", 64, true, &fail("end", "died", 0))).await;
    assert!(
        got.text().ends_with("restarts it\"}}\n\ndata: [DONE]\n\n"),
        "{:?}",
        got.text()
    );
    // The engine served every turn and each place came back.
    assert_eq!(h.driver.fifo().used(), 0);
    let got = h.call(&chat("hi", 64, false, "")).await;
    assert_eq!(got.json()["text"], "hello world");
    h.stop().await;
}

/// The HTTP framing half of the donor's EngineDeath test: a dead engine is an error event
/// in the open stream, then `data: [DONE]`; the turn's finish is `error`; the next request
/// restarts the engine and answers in full.
#[tokio::test]
async fn a_dead_engine_mid_stream_is_an_error_event_and_the_next_request_restarts_it() {
    let engine = DyingEngine::new(FakeScript::new(answer(&"x".repeat(100))).max_context(CTX))
        .unwrap_or_else(|e| panic!("{e}"));
    let h = Harness::start(Setup::new(Arc::new(engine.clone()))).await;
    let got = h.call(&chat("hi", 50, true, "")).await;
    assert_eq!(got.status, 200);
    let text = got.text();
    assert!(text.contains("\"error\""), "{text}");
    assert!(text.contains("stopped unexpectedly"), "{text}");
    assert!(text.contains("; the next request restarts it"), "{text}");
    assert!(text.trim_end().ends_with("data: [DONE]"), "{text}");
    assert_eq!(got.streamed_text(), "xxxxx");
    h.record
        .wait("the turn is booked", |r| r.records().len() == 1)
        .await;
    assert_eq!(h.record.records()[0].finish, "error");
    let got = h.call(&chat("hi", 50, false, "")).await;
    assert_eq!(got.status, 200, "{:?}", got.text());
    assert_eq!(engine.restarts(), 1);
    assert_eq!(got.json()["completion_tokens"], 50);
    h.stop().await;
}

/// The HTTP framing half of the donor's test_engine_err_mid_stream: the engine's `ERR`
/// after the stream started is an error event, never a status line inside the stream.
#[tokio::test]
async fn an_engine_err_after_the_stream_started_is_an_error_event() {
    let engine = ErrEngine::new(FakeScript::new(answer("x")).max_context(CTX))
        .unwrap_or_else(|e| panic!("{e}"));
    let h = Harness::start(Setup::new(Arc::new(engine))).await;
    let got = h.call(&chat("hi", 20, true, "")).await;
    assert_eq!(got.status, 200);
    let text = got.text();
    assert!(text.contains("illegal memory access"), "{text}");
    assert!(!text.contains("HTTP/1"), "{text}");
    assert_eq!(
        text,
        "data: {\"error\": {\"type\": \"server_error\", \"message\": \"verify: layer 31 never \
         rang (an illegal memory access was encountered)\"}}\n\ndata: [DONE]\n\n"
    );
    h.record
        .wait("the turn is booked", |r| r.records().len() == 1)
        .await;
    assert_eq!(h.record.records()[0].finish, "error");
    // Before the first byte the same error is a 400.
    let got = h.call(&chat("hi", 20, false, "")).await;
    assert_eq!(got.status, 400);
    assert_eq!(
        got.text(),
        r#"{"error": {"type": "invalid_request_error", "message": "verify: layer 31 never rang (an illegal memory access was encountered)"}}"#
    );
    h.stop().await;
}

/// A token id outside the vocabulary: the donor's tokenizer `IndexError`, answered 400
/// `malformed request (IndexError: ...)` before the first byte and only logged after it
/// (contract section 10 and section 12.1, rule 10).
#[tokio::test]
async fn an_id_outside_the_vocabulary_is_a_400_before_and_a_cut_after() {
    let mut script = enc("hi");
    script.push(300);
    script.push(END);
    let h = Harness::start(Setup::new(Arc::new(fake(script)))).await;
    let got = h.call(&chat("hi", 20, false, "")).await;
    assert_eq!(got.status, 400);
    assert_eq!(
        got.text(),
        r#"{"error": {"type": "invalid_request_error", "message": "malformed request (IndexError: token id 300 is outside the vocabulary (262))"}}"#
    );
    let got = h.call(&chat("hi", 20, true, "")).await;
    assert_eq!(got.status, 200);
    assert_eq!(
        got.text(),
        "data: {\"text\": \"h\"}\n\ndata: {\"text\": \"i\"}\n\n"
    );
    h.record
        .wait("both turns are booked", |r| r.records().len() == 2)
        .await;
    let records = h.record.records();
    assert_eq!(records[0].finish, "length");
    assert_eq!(records[0].output_tokens, 3);
    // After the first byte too, the turn's finish is `length` (contract section 10).
    assert_eq!(records[1].finish, "length");
    // Both requests logged the IndexError traceback (the streamed one also writes the
    // mid-answer line on standard error, through the transport's responder).
    let tracebacks = h
        .errors
        .lines()
        .into_iter()
        .filter(|l| l.starts_with("[console] traceback: IndexError in a request from 127.0.0.1:"))
        .count();
    assert_eq!(tracebacks, 2, "{:?}", h.errors.lines());
    assert_eq!(h.driver.fifo().used(), 0);
    h.stop().await;
}

/// A dialect that answers its failures itself (the Responses dialect, whose donor
/// `response_events` catches every exception): a turn error of a collected answer is the
/// dialect's 500 body; after the first byte, every class (an IndexError, an uncaught
/// exception, an engine death) is the dialect's frame; no traceback is logged, as the
/// donor's handler never sees the exception.
#[tokio::test]
async fn a_dialect_can_answer_its_own_failures() {
    let mut script = enc("hi");
    script.push(300);
    script.push(END);
    let h = Harness::start(Setup::new(Arc::new(fake(script)))).await;
    let own = ", \"probe_failed\": \"own\"";
    // A turn error before the first byte (the tokenizer's IndexError).
    let got = h.call(&chat("hi", 20, false, own)).await;
    assert_eq!(got.status, 500, "{:?}", got.text());
    assert_eq!(got.header("Content-Type"), Some("application/json"));
    assert_eq!(
        got.text(),
        r#"{"status": "failed", "error": {"code": "server_error", "message": "malformed request (IndexError: token id 300 is outside the vocabulary (262))"}}"#
    );
    // The same IndexError mid-stream is the dialect's frame, not a cut.
    let got = h.call(&chat("hi", 20, true, own)).await;
    assert_eq!(got.status, 200);
    assert_eq!(
        got.text(),
        "data: {\"text\": \"h\"}\n\ndata: {\"text\": \"i\"}\n\nevent: response.failed\ndata: \
         {\"status\": \"failed\", \"error\": {\"code\": \"server_error\", \"message\": \"malformed \
         request (IndexError: token id 300 is outside the vocabulary (262))\"}}\n\n"
    );
    assert_eq!(h.driver.fifo().used(), 0);
    h.stop().await;
    // Classes the driver would cut or turn into its own event, taken by the dialect, on an
    // engine that answers in full.
    let h = Harness::start(Setup::new(Arc::new(fake(answer("hello"))))).await;
    let two = "data: {\"text\": \"h\"}\n\ndata: {\"text\": \"e\"}\n\n";
    for (class, message) in [
        ("uncaught", "cannot convert float infinity to integer"),
        ("bad_body", "too large"),
        (
            "died",
            "the engine stopped unexpectedly (exit code -9); the next request restarts it",
        ),
    ] {
        let got = h
            .call(&chat(
                "hi",
                20,
                true,
                &format!("{own}{}", fail("token", class, 2)),
            ))
            .await;
        assert_eq!(
            got.text(),
            format!(
                "{two}event: response.failed\ndata: {{\"status\": \"failed\", \"error\": \
                 {{\"code\": \"server_error\", \"message\": \"{message}\"}}}}\n\n"
            ),
            "{class}"
        );
        // A collected answer: the dialect's 500 for the same class.
        let got = h
            .call(&chat(
                "hi",
                20,
                false,
                &format!("{own}{}", fail("token", class, 2)),
            ))
            .await;
        assert_eq!(got.status, 500, "{class}: {:?}", got.text());
    }
    // A failure of the collected body is offered to the dialect too.
    let got = h
        .call(&chat(
            "hi",
            20,
            false,
            &format!("{own}{}", fail("body", "value", 0)),
        ))
        .await;
    assert_eq!(got.status, 500);
    assert!(h.errors.lines().is_empty(), "{:?}", h.errors.lines());
    // A dialect that picks the mid-answer log line or a plain close for an error the
    // driver would write as an event: the stream is cut after what was sent.
    for policy in ["log", "close"] {
        let got = h
            .call(&chat(
                "hi",
                20,
                true,
                &format!(
                    ", \"probe_failed\": \"{policy}\"{}",
                    fail("token", "value", 2)
                ),
            ))
            .await;
        assert_eq!(got.text(), two, "{policy}");
    }
    // A variant that does not fit the moment falls back to the driver's mapping.
    let got = h
        .call(&chat(
            "hi",
            20,
            false,
            &format!(", \"probe_failed\": \"log\"{}", fail("token", "value", 1)),
        ))
        .await;
    assert_eq!(got.status, 400);
    assert_eq!(
        got.text(),
        r#"{"error": {"type": "invalid_request_error", "message": "temperature: a number"}}"#
    );
    assert_eq!(h.driver.fifo().used(), 0);
    h.stop().await;
}

/// An engine found not ready at its turn after the stream began: the donor's `BadBody`
/// can only be logged, and the stream is cut.
#[tokio::test]
async fn a_starting_engine_after_the_stream_began_is_a_cut() {
    let factory = fake(answer("ok"));
    let probe = factory.probe();
    let h = Harness::start(Setup::new(Arc::new(factory))).await;
    probe.set_max_context(Some(0));
    let got = h.call(&chat("hi", 8, true, "")).await;
    assert_eq!(got.status, 200);
    assert_eq!(got.text(), "");
    h.stop().await;
}
