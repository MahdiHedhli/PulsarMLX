//! Error constructors of `console_http::error` (work package API-01): every constructor's
//! status, headers and body.
//!
//! Expected bodies were recorded from CPython 3.14.7 `json.dumps` (run as `python3 -I -c
//! '...'` with the standard library only) applied to the dictionaries the donor builds; no
//! donor file was run.
//!
//! Behavior reference: project-maya serve/server.py:412-428, 5375-5381, 5457-5463,
//! 5805-5819, 6141-6158, 6255-6266 and 6283-6297 at 7e68a30f.

use console_http::error::{
    fail, AnswerState, ApiError, ErrorKind, ErrorResponse, FailAction, MalformedCategory,
    OVERLOADED_RELOADING,
};
use console_pyjson::dumps::to_wire;
use console_pyjson::loads::{loads, loads_bytes};

fn json_headers(body: &str) -> Vec<(&'static str, String)> {
    vec![
        ("Content-Type", String::from("application/json")),
        ("Content-Length", body.len().to_string()),
    ]
}

fn check(error: &ApiError, status: u16, body: &str) {
    let response = error.to_response();
    assert_eq!(response.status, status, "status of {error:?}");
    assert_eq!(response.body, body, "body of {error:?}");
    if error.retry_after().is_none() {
        assert_eq!(
            response.headers(),
            json_headers(body),
            "headers of {error:?}"
        );
    }
    // The hand-assembled body is what the Python-compatible writer gives for the same value
    // (the overloaded body aside, which is written with ensure_ascii=True).
    if !matches!(error, ApiError::Overloaded { .. }) {
        let value = loads(&response.body).unwrap_or_else(|e| panic!("body is not JSON: {e}"));
        assert_eq!(to_wire(&value).ok().as_deref(), Some(body));
    }
}

#[test]
fn bad_body_keeps_its_status() {
    check(
        &ApiError::bad_body(400, "invalid Content-Length"),
        400,
        r#"{"error": {"type": "invalid_request_error", "message": "invalid Content-Length"}}"#,
    );
    check(
        &ApiError::bad_body(413, "too big"),
        413,
        r#"{"error": {"type": "invalid_request_error", "message": "too big"}}"#,
    );
    check(
        &ApiError::model_starting(),
        503,
        r#"{"error": {"type": "invalid_request_error", "message": "the model is starting; try again in a moment"}}"#,
    );
}

#[test]
fn validation_has_no_code_and_context_overflow_has_one() {
    check(
        &ApiError::validation("the request body must be a JSON object"),
        400,
        r#"{"error": {"type": "invalid_request_error", "message": "the request body must be a JSON object"}}"#,
    );
    let overflow = ApiError::context_no_room(4096, 4090);
    assert_eq!(overflow.code(), Some("context_length_exceeded"));
    check(
        &overflow,
        400,
        r#"{"error": {"type": "invalid_request_error", "message": "maximum context length is 4096 tokens; prompt (4090 tokens) leaves no room to answer in the context; requests are never truncated", "code": "context_length_exceeded"}}"#,
    );
    assert_eq!(
        ApiError::context_exceeded(4096, 100, 4000).message(),
        "maximum context length is 4096 tokens; prompt (100 tokens) + max tokens (4000) \
         exceeds the context; requests are never truncated"
    );
    assert_eq!(ApiError::validation("x").code(), None);
}

#[test]
fn server_errors() {
    check(
        &ApiError::job(429, "background queue is at capacity"),
        429,
        r#"{"error": {"type": "server_error", "message": "background queue is at capacity"}}"#,
    );
    check(
        &ApiError::store_busy("Responses snapshot assembly is at capacity; retry later"),
        503,
        r#"{"error": {"type": "server_error", "message": "Responses snapshot assembly is at capacity; retry later"}}"#,
    );
    check(
        &ApiError::engine_died("the engine stopped unexpectedly (exit code -9)"),
        503,
        r#"{"error": {"type": "server_error", "message": "the engine stopped unexpectedly (exit code -9); the next request restarts it"}}"#,
    );
}

/// Approved deviation P-3: the `malformed request (` prefix and a Python-like category are
/// kept; the detail text is this server's own.
#[test]
fn malformed_request_keeps_prefix_and_category_p3() {
    let cases = [
        (MalformedCategory::KeyError, "KeyError"),
        (MalformedCategory::TypeError, "TypeError"),
        (MalformedCategory::AttributeError, "AttributeError"),
        (MalformedCategory::IndexError, "IndexError"),
    ];
    for (category, name) in cases {
        let error = ApiError::malformed(category, "messages[0].content must be a string");
        assert_eq!(error.status(), 400);
        assert_eq!(error.kind(), Some(ErrorKind::InvalidRequest));
        let message = error.message();
        assert!(message.starts_with("malformed request ("), "{message}");
        assert_eq!(
            message,
            format!("malformed request ({name}: messages[0].content must be a string)")
        );
        check(
            &error,
            400,
            &format!(
                "{{\"error\": {{\"type\": \"invalid_request_error\", \"message\": \
                 \"malformed request ({name}: messages[0].content must be a string)\"}}}}"
            ),
        );
    }
}

#[test]
fn not_found_auth_permission_and_plain() {
    check(
        &ApiError::NotFound,
        404,
        r#"{"error": {"message": "not found"}}"#,
    );
    check(
        &ApiError::Auth,
        401,
        r#"{"error": {"type": "authentication_error", "message": "missing or wrong API key"}}"#,
    );
    check(
        &ApiError::permission("requests from other web pages are refused"),
        403,
        r#"{"error": {"type": "permission_error", "message": "requests from other web pages are refused"}}"#,
    );
    check(
        &ApiError::plain(503, "loading model x: caf\u{e9}"),
        503,
        "{\"error\": \"loading model x: caf\u{e9}\"}",
    );
    assert_eq!(ApiError::plain(409, "x").kind(), None);
}

#[test]
fn overloaded_carries_retry_after_and_ascii_body() {
    let error = ApiError::overloaded(OVERLOADED_RELOADING);
    let response = error.to_response();
    assert_eq!(response.status, 503);
    assert_eq!(
        response.body,
        r#"{"error": {"type": "overloaded_error", "message": "the model is reloading with a new context size; try again in a minute"}}"#
    );
    assert_eq!(
        response.headers(),
        vec![
            ("Content-Type", String::from("application/json")),
            ("Retry-After", String::from("30")),
            ("Content-Length", response.body.len().to_string()),
        ]
    );
    // json.dumps without ensure_ascii=False escapes non-ASCII text.
    assert_eq!(
        ApiError::overloaded("caf\u{e9} \"busy\"").body(),
        r#"{"error": {"type": "overloaded_error", "message": "caf\u00e9 \"busy\""}}"#
    );
}

#[test]
fn wire_bodies_keep_non_ascii_raw_and_escape_controls() {
    check(
        &ApiError::validation("caf\u{e9} \"q\" \\\\ \n\u{2028}"),
        400,
        "{\"error\": {\"type\": \"invalid_request_error\", \"message\": \"caf\u{e9} \\\"q\\\" \\\\\\\\ \\n\u{2028}\"}}",
    );
    // Content-Length counts bytes, not characters.
    let response = ApiError::validation("\u{e9}").to_response();
    assert_eq!(
        response.headers().last().map(|h| h.1.clone()),
        Some(response.body.len().to_string())
    );
}

#[test]
fn a_body_that_does_not_parse_is_a_400_with_pythons_message() {
    let error = match loads_bytes(b"{\"a\": }") {
        Err(e) => ApiError::from(e),
        Ok(v) => panic!("parsed: {v}"),
    };
    check(
        &error,
        400,
        r#"{"error": {"type": "invalid_request_error", "message": "Expecting value: line 1 column 7 (char 6)"}}"#,
    );
    let error = match loads_bytes(b"\xff") {
        Err(e) => ApiError::from(e),
        Ok(v) => panic!("parsed: {v}"),
    };
    assert_eq!(
        error.message(),
        "'utf-8' codec can't decode byte 0xff in position 0: invalid start byte"
    );
}

#[test]
fn fail_answers_before_the_start_and_only_logs_after_it() {
    let mut state = AnswerState::new();
    assert!(!state.is_started());
    let error = ApiError::engine_died("the engine stopped unexpectedly (exit code 1)");
    match fail(&state, &error) {
        FailAction::Respond(ErrorResponse { status, body, .. }) => {
            assert_eq!(status, 503);
            assert_eq!(body, error.body());
        }
        other => panic!("expected an answer, got {other:?}"),
    }
    state.mark_started();
    assert_eq!(
        fail(&state, &error),
        FailAction::LogAndClose(String::from(
            "[console] request failed mid-answer: the engine stopped unexpectedly (exit code 1); \
             the next request restarts it"
        ))
    );
    // A context overflow after the start logs its message without the code.
    assert_eq!(
        fail(&state, &ApiError::context_no_room(10, 9)),
        FailAction::LogAndClose(String::from(
            "[console] request failed mid-answer: maximum context length is 10 tokens; prompt \
             (9 tokens) leaves no room to answer in the context; requests are never truncated"
        ))
    );
}

#[test]
fn mid_answer_log_line_stays_one_line() {
    let mut state = AnswerState::new();
    state.mark_started();
    let forged = "x\n[console] engine ready\r\t\u{0}\u{7f}\u{85}\u{2028}\u{2029}\u{1b}[0m end";
    let line = match fail(&state, &ApiError::validation(forged)) {
        FailAction::LogAndClose(line) => line,
        other => panic!("expected a log line, got {other:?}"),
    };
    assert_eq!(
        line,
        "[console] request failed mid-answer: x\\n[console] engine ready\\r\\t\\u{0}\\u{7f}\\u{85}\\u{2028}\\u{2029}\\u{1b}[0m end"
    );
    assert!(!line
        .chars()
        .any(|c| c.is_control() || c == '\u{2028}' || c == '\u{2029}'));
    // The answer body before the start is unchanged: the controls are JSON-escaped there.
    let mut fresh = AnswerState::new();
    assert!(!fresh.is_started());
    match fail(&fresh, &ApiError::validation("a\nb")) {
        FailAction::Respond(ErrorResponse { body, .. }) => assert!(body.contains("a\\nb")),
        other => panic!("expected an answer, got {other:?}"),
    }
    fresh.mark_started();
    // Ordinary text, a backslash included, is logged as it is.
    assert_eq!(
        fail(&fresh, &ApiError::validation("C:\\dir é")),
        FailAction::LogAndClose(String::from(
            "[console] request failed mid-answer: C:\\dir é"
        ))
    );
}

#[test]
fn display_is_the_message() {
    assert_eq!(ApiError::Auth.to_string(), "missing or wrong API key");
    assert_eq!(ApiError::NotFound.to_string(), "not found");
}
