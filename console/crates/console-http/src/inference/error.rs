//! The errors of one inference request, classified as the donor's `do_POST` classifies
//! them, and what each class answers before and after the first byte of the answer.
//!
//! The donor's handler catches, in this order: `BadBody` (its own status,
//! `invalid_request_error`), `JobError` and `StoreBusy` (their status, `server_error`),
//! `ValueError` (400 `error_body`, with the code of a `ContextOverflow`), `EngineDied` (503
//! `server_error`, "`<message>`; the next request restarts it"), and `KeyError`, `TypeError`,
//! `AttributeError` and `IndexError` (a traceback in the log, then 400 `malformed request
//! (<Class>: <detail>)`, approved deviation P-3). Each is answered through `_fail`: while
//! nothing was sent, as JSON; once the answer has begun, only the line `request failed
//! mid-answer: <message>` and a closed connection. Inside a stream's write loop the donor
//! catches `ValueError` and `EngineDied` first and writes them into the stream as the
//! dialect's error event, followed by the stream's end. Any other exception (an
//! `OverflowError`, a plain `RuntimeError`) is not caught by the handler: `socketserver`'s
//! `handle_error` prints the traceback and the connection closes with no answer.
//!
//! [`InferenceError`] carries the class; [`InferenceError::before_start`] and
//! [`InferenceError::after_start`] say what it answers. Two classes have no donor
//! counterpart and follow `contracts/backend-seam.md` section 10: an engine protocol
//! violation (500 before the first byte, a stream error after) and an engine that failed
//! to start or was refused by the synthetic-only guard (503 before, a stream error after).
//!
//! Behavior reference: project-maya serve/server.py:412-428, 6152-6158, 6283-6297,
//! 6607-6624, 6692-6710 and 6732-6734 at 7e68a30f.

use std::fmt;

use console_core::engine::{EngineFailure, FailureKind};
use console_core::request::RequestError;
use console_core::turn::TurnError;

use crate::error::{ApiError, MalformedCategory};
use crate::guard::Refusal;

/// What failed in the prompt step, for the mapping of approved deviation P-8. The prompt
/// packages of M2 build these from their own error types: PRM-03 from a template's
/// `raise_exception`, PRM-07 from a failed assertion of the DeepSeek encoder.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PromptFailureKind {
    /// A chat template called `raise_exception` (PRM-03's template error).
    TemplateRaise,
    /// The DeepSeek encoder's input check failed (PRM-07's encode error).
    EncoderAssertion,
}

/// A refusal of the prompt step that answers 400 `invalid_request_error` with its message
/// (approved deviation P-8, owner decision of 2026-11-14, settling OPEN-07). The donor ends
/// both cases in an unclean server error.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PromptFailure {
    /// Which refusal.
    pub kind: PromptFailureKind,
    /// The text the answer carries.
    pub message: String,
}

impl PromptFailure {
    /// A template's `raise_exception` with its message.
    pub fn template_raise(message: impl Into<String>) -> Self {
        Self {
            kind: PromptFailureKind::TemplateRaise,
            message: message.into(),
        }
    }

    /// A failed assertion of the DeepSeek encoder, with its message.
    pub fn encoder_assertion(message: impl Into<String>) -> Self {
        Self {
            kind: PromptFailureKind::EncoderAssertion,
            message: message.into(),
        }
    }
}

/// The class of an error written into a stream that has begun.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FaultClass {
    /// The donor's `ValueError` (an engine `ERR`, a context overflow, a stopping server).
    Value,
    /// The donor's `EngineDied`.
    EngineDied,
    /// A server-side failure with no donor class: an engine protocol violation or an
    /// engine that could not start (contract section 10).
    Server,
}

/// An error a dialect writes into its stream as an error event (the donor's stream loop:
/// OpenAI writes `{"error": {"type": "server_error", ...}}` and `data: [DONE]`, Anthropic an
/// `event: error` with `api_error`).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct StreamFault {
    /// The class.
    pub class: FaultClass,
    /// The message as the event carries it; for [`FaultClass::EngineDied`] it already ends
    /// with "; the next request restarts it".
    pub message: String,
}

/// What an error answers while nothing has been sent.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum BeforeStart {
    /// This status and JSON body (headers as `Responder::error` writes them).
    Answer {
        /// HTTP status.
        status: u16,
        /// The body.
        body: String,
    },
    /// Nothing: the connection closes without an answer (an exception the donor's handler
    /// does not catch).
    NoAnswer,
}

/// What an error does once the answer has begun.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum AfterStart {
    /// Inside the stream's write loop: the dialect writes this fault as its error event,
    /// then the stream ends.
    StreamError(StreamFault),
    /// The donor's `_fail` after the answer began: the line `[console] request failed
    /// mid-answer: <message>` on standard error, and the connection closes.
    LogAndClose(String),
    /// The connection closes with nothing more written (an uncaught exception).
    Close,
}

/// Why one inference request failed.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum InferenceError {
    /// An answer of the error model raised as the donor's `BadBody`, `JobError`,
    /// `StoreBusy`, or a malformed request (approved deviation P-3), answered through
    /// `_fail`: its own answer before the first byte, the mid-answer log line after it.
    /// A `Validation`, `ContextOverflow` or `EngineDied` error converted with
    /// [`From<ApiError>`] lands in its own class instead.
    Fail(ApiError),
    /// A guard's refusal written by the dialect's preparation (the donor's `_own_page`,
    /// which answers and returns). Only possible before the first byte.
    Refused(Refusal),
    /// The donor's `ValueError`: 400 `invalid_request_error` before the first byte (with
    /// `"code": "context_length_exceeded"` for a context overflow), the dialect's stream
    /// error after it.
    Value {
        /// Python's `str(e)`.
        message: String,
        /// A `ContextOverflow`, whose body carries its code.
        context_overflow: bool,
    },
    /// The donor's `EngineDied`: 503 `server_error`, "`<message>`; the next request restarts
    /// it", or the dialect's stream error after the first byte.
    EngineDied {
        /// The engine's message, without the suffix.
        message: String,
    },
    /// A server-side failure with no donor class (contract section 10): `server_error`
    /// with this status before the first byte, the dialect's stream error after it.
    Server {
        /// 500 for an engine protocol violation, 503 for an engine that could not start.
        status: u16,
        /// The message.
        message: String,
    },
    /// An exception the donor's handler does not catch (`OverflowError`, a plain
    /// `RuntimeError`): a log line and no answer; after the first byte the stream is cut.
    Uncaught {
        /// The Python exception class.
        class: &'static str,
        /// Its message.
        message: String,
    },
}

/// The message suffix of an engine death.
const RESTARTS: &str = "; the next request restarts it";

impl InferenceError {
    /// A `ValueError` with this message: 400 `invalid_request_error`.
    pub fn value(message: impl Into<String>) -> Self {
        InferenceError::Value {
            message: message.into(),
            context_overflow: false,
        }
    }

    /// A context overflow: 400 with `"code": "context_length_exceeded"`.
    pub fn context_overflow(message: impl Into<String>) -> Self {
        InferenceError::Value {
            message: message.into(),
            context_overflow: true,
        }
    }

    /// A malformed request (approved deviation P-3).
    pub fn malformed(category: MalformedCategory, detail: impl Into<String>) -> Self {
        InferenceError::Fail(ApiError::malformed(category, detail))
    }

    /// An exception the donor does not catch.
    pub fn uncaught(class: &'static str, message: impl Into<String>) -> Self {
        InferenceError::Uncaught {
            class,
            message: message.into(),
        }
    }

    /// The error-model answer this error writes before the first byte, if it is one
    /// (`None` for a refusal and for an uncaught exception).
    pub fn api_error(&self) -> Option<ApiError> {
        match self {
            InferenceError::Fail(e) => Some(e.clone()),
            InferenceError::Refused(_) | InferenceError::Uncaught { .. } => None,
            InferenceError::Value {
                message,
                context_overflow: true,
            } => Some(ApiError::context_overflow(message.clone())),
            InferenceError::Value { message, .. } => Some(ApiError::validation(message.clone())),
            InferenceError::EngineDied { message } => Some(ApiError::engine_died(message.clone())),
            // The body of a `server_error` with a status is the same as the donor's
            // `JobError(status, message)`.
            InferenceError::Server { status, message } => {
                Some(ApiError::job(*status, message.clone()))
            }
        }
    }

    /// What this error answers while nothing has been sent.
    pub fn before_start(&self) -> BeforeStart {
        match self {
            InferenceError::Refused(r) => BeforeStart::Answer {
                status: r.status(),
                body: r.body(),
            },
            other => match other.api_error() {
                Some(e) => BeforeStart::Answer {
                    status: e.status(),
                    body: e.body(),
                },
                None => BeforeStart::NoAnswer,
            },
        }
    }

    /// The fault a dialect writes into a stream that has begun, for the classes the
    /// donor's stream loop catches.
    pub fn stream_fault(&self) -> Option<StreamFault> {
        match self {
            InferenceError::Value { message, .. } => Some(StreamFault {
                class: FaultClass::Value,
                message: message.clone(),
            }),
            InferenceError::EngineDied { message } => Some(StreamFault {
                class: FaultClass::EngineDied,
                message: format!("{message}{RESTARTS}"),
            }),
            InferenceError::Server { message, .. } => Some(StreamFault {
                class: FaultClass::Server,
                message: message.clone(),
            }),
            _ => None,
        }
    }

    /// What this error does once a stream has begun: the policy of the donor's OpenAI and
    /// Anthropic stream loops. The Responses dialect answers its failures itself through
    /// [`DialectTurn::failed`](super::DialectTurn::failed).
    pub fn after_start(&self) -> AfterStart {
        if let Some(fault) = self.stream_fault() {
            return AfterStart::StreamError(fault);
        }
        match self {
            InferenceError::Fail(e) => AfterStart::LogAndClose(e.message()),
            _ => AfterStart::Close,
        }
    }

    /// The message, as the donor's `str(e)` (and for a malformed request the whole
    /// `malformed request (...)` text).
    pub fn message(&self) -> String {
        match self {
            InferenceError::Fail(e) => e.message(),
            InferenceError::Refused(r) => match r {
                Refusal::Api(e) => e.message(),
                Refusal::Message { message, .. } => message.clone(),
            },
            InferenceError::Value { message, .. }
            | InferenceError::Server { message, .. }
            | InferenceError::Uncaught { message, .. } => message.clone(),
            InferenceError::EngineDied { message } => format!("{message}{RESTARTS}"),
        }
    }

    /// The Python class of a malformed request or an uncaught exception, which the donor
    /// logs with a traceback; `None` for the other classes.
    pub fn traceback_class(&self) -> Option<&'static str> {
        match self {
            InferenceError::Fail(ApiError::Malformed { category, .. }) => Some(category.as_str()),
            InferenceError::Uncaught { class, .. } => Some(class),
            _ => None,
        }
    }
}

impl fmt::Display for InferenceError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.message())
    }
}

impl std::error::Error for InferenceError {}

impl From<ApiError> for InferenceError {
    /// The class of an error-model answer: a `Validation` or `ContextOverflow` is a
    /// `ValueError`, an `EngineDied` is an engine death, anything else is answered through
    /// `_fail`.
    fn from(e: ApiError) -> Self {
        match e {
            ApiError::Validation { message } => InferenceError::value(message),
            ApiError::ContextOverflow { message } => InferenceError::context_overflow(message),
            ApiError::EngineDied { message } => InferenceError::EngineDied { message },
            other => InferenceError::Fail(other),
        }
    }
}

impl From<Refusal> for InferenceError {
    fn from(r: Refusal) -> Self {
        InferenceError::Refused(r)
    }
}

impl From<PromptFailure> for InferenceError {
    /// Approved deviation P-8: a template's `raise_exception` and a failed assertion of the
    /// DeepSeek encoder answer 400 `invalid_request_error` with their message.
    fn from(p: PromptFailure) -> Self {
        InferenceError::value(p.message)
    }
}

/// The P-3 category of a Python exception class the donor answers as a malformed request.
fn malformed_category(class: &str) -> Option<MalformedCategory> {
    match class {
        "KeyError" => Some(MalformedCategory::KeyError),
        "TypeError" => Some(MalformedCategory::TypeError),
        "AttributeError" => Some(MalformedCategory::AttributeError),
        "IndexError" => Some(MalformedCategory::IndexError),
        _ => None,
    }
}

impl From<RequestError> for InferenceError {
    /// A request check's error by its Python class: `ValueError` is 400 with its message;
    /// `TypeError` (and the other classes the handler catches) is a malformed request; an
    /// `OverflowError` is not caught by the donor's handler, so it is answered with
    /// nothing (see the module documentation).
    fn from(e: RequestError) -> Self {
        match e {
            RequestError::Invalid(message) => InferenceError::value(message),
            RequestError::Malformed { category, detail } => match malformed_category(category) {
                Some(c) => InferenceError::malformed(c, detail),
                None => InferenceError::uncaught(category, detail),
            },
            RequestError::Overflow(message) => InferenceError::uncaught("OverflowError", message),
        }
    }
}

impl From<EngineFailure> for InferenceError {
    /// An engine failure, by contract section 10's server mapping: `Died` is an engine
    /// death; `Reported`, `NeverAnswered`, a negative token id and `Unsupported` are the
    /// donor's `ValueError`s; an id outside the vocabulary is the tokenizer's `IndexError`
    /// (section 12.1, rule 10); `NotReady` is the 503 "the model is starting"; `Protocol`
    /// is 500 and `StartFailed` 503 `server_error`, both stream errors after the first
    /// byte.
    fn from(f: EngineFailure) -> Self {
        let message = f.message.as_str().to_owned();
        match f.kind {
            FailureKind::Died => InferenceError::EngineDied { message },
            FailureKind::Reported | FailureKind::NeverAnswered | FailureKind::Unsupported => {
                InferenceError::value(message)
            }
            FailureKind::InvalidToken => match f.out_of_vocabulary_parts() {
                Some((id, vocab)) => TurnError::out_of_vocabulary(id, vocab).into(),
                None => InferenceError::value(message),
            },
            FailureKind::NotReady => InferenceError::Fail(ApiError::model_starting()),
            FailureKind::Protocol => InferenceError::Server {
                status: 500,
                message,
            },
            FailureKind::StartFailed => InferenceError::Server {
                status: 503,
                message,
            },
        }
    }
}

impl From<TurnError> for InferenceError {
    /// A turn's error: a context overflow is a `ValueError` with its code; `Starting` is
    /// the donor's `BadBody(503, "the model is starting; try again in a moment")`; a
    /// request error and an engine failure by their own mappings. The server's stopping
    /// refusal is the donor's `ValueError` (serve/server.py:4364-4365), so it answers 400
    /// `invalid_request_error`.
    fn from(e: TurnError) -> Self {
        match e {
            TurnError::ContextOverflow { message } => InferenceError::context_overflow(message),
            TurnError::Starting => InferenceError::Fail(ApiError::model_starting()),
            TurnError::Request(r) => r.into(),
            TurnError::Engine(f) => f.into(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    use console_core::turn::{STARTING_MESSAGE, STOPPING_MESSAGE};

    fn answer(status: u16, body: &str) -> BeforeStart {
        BeforeStart::Answer {
            status,
            body: body.to_owned(),
        }
    }

    fn fault(class: FaultClass, message: &str) -> AfterStart {
        AfterStart::StreamError(StreamFault {
            class,
            message: message.to_owned(),
        })
    }

    /// Every error class, with the status and body it answers before the first byte and
    /// what it does after it.
    #[test]
    fn every_error_class_maps_to_its_status_and_body() {
        let overflow = "maximum context length is 4096 tokens; prompt (5000 tokens) leaves \
                        no room to answer in the context; requests are never truncated";
        let cases: Vec<(&str, InferenceError, BeforeStart, AfterStart)> = vec![
            (
                "BadBody",
                ApiError::bad_body(413, "too large").into(),
                answer(413, r#"{"error": {"type": "invalid_request_error", "message": "too large"}}"#),
                AfterStart::LogAndClose("too large".into()),
            ),
            (
                "model starting (TurnError::Starting)",
                TurnError::Starting.into(),
                answer(
                    503,
                    r#"{"error": {"type": "invalid_request_error", "message": "the model is starting; try again in a moment"}}"#,
                ),
                AfterStart::LogAndClose(STARTING_MESSAGE.into()),
            ),
            (
                "model starting (EngineFailure::not_ready)",
                EngineFailure::not_ready().into(),
                answer(
                    503,
                    r#"{"error": {"type": "invalid_request_error", "message": "the model is starting; try again in a moment"}}"#,
                ),
                AfterStart::LogAndClose(STARTING_MESSAGE.into()),
            ),
            (
                "JobError",
                ApiError::job(409, "busy job").into(),
                answer(409, r#"{"error": {"type": "server_error", "message": "busy job"}}"#),
                AfterStart::LogAndClose("busy job".into()),
            ),
            (
                "StoreBusy",
                ApiError::store_busy("store busy").into(),
                answer(503, r#"{"error": {"type": "server_error", "message": "store busy"}}"#),
                AfterStart::LogAndClose("store busy".into()),
            ),
            (
                "ValueError (validation)",
                RequestError::invalid("temperature: a number").into(),
                answer(
                    400,
                    r#"{"error": {"type": "invalid_request_error", "message": "temperature: a number"}}"#,
                ),
                fault(FaultClass::Value, "temperature: a number"),
            ),
            (
                "ValueError (the server is stopping)",
                TurnError::stopping().into(),
                answer(
                    400,
                    &format!(
                        r#"{{"error": {{"type": "invalid_request_error", "message": "{STOPPING_MESSAGE}"}}}}"#
                    ),
                ),
                fault(FaultClass::Value, STOPPING_MESSAGE),
            ),
            (
                "ContextOverflow",
                TurnError::ContextOverflow {
                    message: overflow.into(),
                }
                .into(),
                answer(
                    400,
                    &format!(
                        r#"{{"error": {{"type": "invalid_request_error", "message": "{overflow}", "code": "context_length_exceeded"}}}}"#
                    ),
                ),
                fault(FaultClass::Value, overflow),
            ),
            (
                "engine ERR",
                EngineFailure::reported("verify: layer 31 never rang").into(),
                answer(
                    400,
                    r#"{"error": {"type": "invalid_request_error", "message": "verify: layer 31 never rang"}}"#,
                ),
                fault(FaultClass::Value, "verify: layer 31 never rang"),
            ),
            (
                "engine never answered",
                EngineFailure::never_answered(30.0).into(),
                answer(
                    400,
                    r#"{"error": {"type": "invalid_request_error", "message": "the engine never answered this request (30 s without a line of its own); it was stopped"}}"#,
                ),
                fault(
                    FaultClass::Value,
                    "the engine never answered this request (30 s without a line of its own); it was stopped",
                ),
            ),
            (
                "negative token id",
                EngineFailure::negative_token(-1).into(),
                answer(
                    400,
                    r#"{"error": {"type": "invalid_request_error", "message": "the engine could not pick a token (it wrote the id -1: its sampling failed - the engine's log says why)"}}"#,
                ),
                fault(
                    FaultClass::Value,
                    "the engine could not pick a token (it wrote the id -1: its sampling failed - the engine's log says why)",
                ),
            ),
            (
                "unsupported",
                EngineFailure::unsupported("pictures").into(),
                answer(
                    400,
                    r#"{"error": {"type": "invalid_request_error", "message": "unsupported: pictures"}}"#,
                ),
                fault(FaultClass::Value, "unsupported: pictures"),
            ),
            (
                "EngineDied",
                EngineFailure::stopped_unexpectedly(Some(-9)).into(),
                answer(
                    503,
                    r#"{"error": {"type": "server_error", "message": "the engine stopped unexpectedly (exit code -9); the next request restarts it"}}"#,
                ),
                fault(
                    FaultClass::EngineDied,
                    "the engine stopped unexpectedly (exit code -9); the next request restarts it",
                ),
            ),
            (
                "engine protocol violation (contract section 10)",
                EngineFailure::protocol("token after the end").into(),
                answer(
                    500,
                    r#"{"error": {"type": "server_error", "message": "engine protocol violation: token after the end"}}"#,
                ),
                fault(
                    FaultClass::Server,
                    "engine protocol violation: token after the end",
                ),
            ),
            (
                "engine start failed (contract section 10)",
                EngineFailure::exited_before_ready(None).into(),
                answer(
                    503,
                    r#"{"error": {"type": "server_error", "message": "the engine exited before it was ready"}}"#,
                ),
                fault(FaultClass::Server, "the engine exited before it was ready"),
            ),
            (
                "IndexError: an id outside the vocabulary (turn)",
                TurnError::out_of_vocabulary(300, 262).into(),
                answer(
                    400,
                    r#"{"error": {"type": "invalid_request_error", "message": "malformed request (IndexError: token id 300 is outside the vocabulary (262))"}}"#,
                ),
                AfterStart::LogAndClose(
                    "malformed request (IndexError: token id 300 is outside the vocabulary (262))"
                        .into(),
                ),
            ),
            (
                "IndexError: an id outside the vocabulary (engine ledger)",
                EngineFailure::out_of_vocabulary(9, 8).into(),
                answer(
                    400,
                    r#"{"error": {"type": "invalid_request_error", "message": "malformed request (IndexError: token id 9 is outside the vocabulary (8))"}}"#,
                ),
                AfterStart::LogAndClose(
                    "malformed request (IndexError: token id 9 is outside the vocabulary (8))"
                        .into(),
                ),
            ),
            (
                "TypeError (P-3)",
                RequestError::type_error("max_tokens: an integer").into(),
                answer(
                    400,
                    r#"{"error": {"type": "invalid_request_error", "message": "malformed request (TypeError: max_tokens: an integer)"}}"#,
                ),
                AfterStart::LogAndClose("malformed request (TypeError: max_tokens: an integer)".into()),
            ),
            (
                "KeyError (P-3)",
                InferenceError::malformed(MalformedCategory::KeyError, "'messages'"),
                answer(
                    400,
                    r#"{"error": {"type": "invalid_request_error", "message": "malformed request (KeyError: 'messages')"}}"#,
                ),
                AfterStart::LogAndClose("malformed request (KeyError: 'messages')".into()),
            ),
            (
                "AttributeError (P-3)",
                InferenceError::malformed(
                    MalformedCategory::AttributeError,
                    "'str' object has no attribute 'get'",
                ),
                answer(
                    400,
                    r#"{"error": {"type": "invalid_request_error", "message": "malformed request (AttributeError: 'str' object has no attribute 'get')"}}"#,
                ),
                AfterStart::LogAndClose(
                    "malformed request (AttributeError: 'str' object has no attribute 'get')"
                        .into(),
                ),
            ),
            (
                "template raise_exception (P-8)",
                PromptFailure::template_raise("tools are not supported").into(),
                answer(
                    400,
                    r#"{"error": {"type": "invalid_request_error", "message": "tools are not supported"}}"#,
                ),
                fault(FaultClass::Value, "tools are not supported"),
            ),
            (
                "DeepSeek encoder assertion (P-8)",
                PromptFailure::encoder_assertion("a tool message without a call").into(),
                answer(
                    400,
                    r#"{"error": {"type": "invalid_request_error", "message": "a tool message without a call"}}"#,
                ),
                fault(FaultClass::Value, "a tool message without a call"),
            ),
            (
                "own-page refusal",
                Refusal::message(403, "MCP tools can be used only from PulsarMLX Console's own page")
                    .into(),
                answer(
                    403,
                    r#"{"error": {"message": "MCP tools can be used only from PulsarMLX Console's own page"}}"#,
                ),
                AfterStart::Close,
            ),
            (
                "permission",
                ApiError::permission("no").into(),
                answer(403, r#"{"error": {"type": "permission_error", "message": "no"}}"#),
                AfterStart::LogAndClose("no".into()),
            ),
            (
                "OverflowError (uncaught by the donor)",
                RequestError::Overflow("cannot convert float infinity to integer".into()).into(),
                BeforeStart::NoAnswer,
                AfterStart::Close,
            ),
            (
                "OverflowError from a prompt-progress time (uncaught by the donor)",
                TurnError::Request(RequestError::Overflow(
                    "cannot convert float infinity to integer".into(),
                ))
                .into(),
                BeforeStart::NoAnswer,
                AfterStart::Close,
            ),
            (
                "an exception class the handler does not name",
                RequestError::Malformed {
                    category: "RecursionError",
                    detail: "too deep".into(),
                }
                .into(),
                BeforeStart::NoAnswer,
                AfterStart::Close,
            ),
        ];
        for (name, error, before, after) in cases {
            assert_eq!(
                error.before_start(),
                before,
                "{name}: before the first byte"
            );
            assert_eq!(error.after_start(), after, "{name}: after the first byte");
        }
    }

    #[test]
    fn api_errors_take_their_python_class() {
        assert_eq!(
            InferenceError::from(ApiError::validation("x")),
            InferenceError::value("x")
        );
        assert_eq!(
            InferenceError::from(ApiError::context_overflow("x")),
            InferenceError::context_overflow("x")
        );
        assert_eq!(
            InferenceError::from(ApiError::engine_died("gone")),
            InferenceError::EngineDied {
                message: "gone".into()
            }
        );
        assert_eq!(
            InferenceError::from(ApiError::NotFound),
            InferenceError::Fail(ApiError::NotFound)
        );
    }

    #[test]
    fn tracebacks_are_logged_for_malformed_and_uncaught_errors() {
        let oov: InferenceError = TurnError::out_of_vocabulary(300, 262).into();
        assert_eq!(oov.traceback_class(), Some("IndexError"));
        assert_eq!(
            InferenceError::uncaught("OverflowError", "x").traceback_class(),
            Some("OverflowError")
        );
        assert_eq!(InferenceError::value("x").traceback_class(), None);
        assert_eq!(
            InferenceError::EngineDied {
                message: "gone".into()
            }
            .to_string(),
            "gone; the next request restarts it"
        );
    }
}
