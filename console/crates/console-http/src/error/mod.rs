//! Owned by API-01. The error taxonomy and the status and body each error produces.
//!
//! The donor answers errors in three body conventions, each written with Python's
//! `json.dumps`:
//!
//! 1. `{"error": {"type": <kind>, "message": <text>}}`, with `"code"` added after `"message"`
//!    only for a context overflow (`error_body`, `_fail`);
//! 2. `{"error": {"message": "not found"}}` for an unknown route;
//! 3. `{"error": <text>}` for the model-management answers.
//!
//! Every body goes through `_json` (`ensure_ascii=False`) except the overloaded answer, which
//! the donor writes with a bare `json.dumps` (`ensure_ascii=True`) and sends with
//! `Retry-After: 30` between `Content-Type` and `Content-Length`.
//!
//! Once the status line of an answer has been written (a stream has begun), an error can no
//! longer be answered: the donor only logs `request failed mid-answer: <message>` and closes
//! the connection ([`fail`]).
//!
//! The malformed-request answer follows approved deviation P-3: it keeps the
//! `malformed request (` prefix and a Python-like category (`KeyError`, `TypeError`,
//! `AttributeError`, `IndexError`), and the detail text after the category is this server's
//! own, since the Python exception `repr` has no Rust counterpart.
//!
//! Behavior reference: project-maya serve/server.py:412-428 (`EngineDied`,
//! `ContextOverflow`, `error_body`), 5375-5381 (`BadBody`), 5457-5463 (`_json`), 6152-6158
//! (`_fail`), 6283-6297 (the exception mapping of `do_POST`), 6255-6266 (overloaded),
//! 5805-5819 (authentication), 6141-6150 (permission), 3680-3693 (context overflow
//! messages), 163-171 (`CTX_SLACK`, `text_file_limit`); serve/response_jobs.py:10-13
//! (`JobError`) and serve/response_store.py:14-15 (`StoreBusy`) at 7e68a30f.

use std::fmt;

use console_core::turn::log_safe;
use console_pyjson::dumps::dumps_str;
use console_pyjson::loads::LoadsError;

/// The context margin and the text-file limits are defined once, in `console_core::request`
/// (API-04), and re-exported here for the routes that answer with them.
pub use console_core::request::{text_file_limit, CTX_SLACK, TEXT_FILE_MAX, TEXT_FILE_MIN};

/// The message of the overloaded answer while the model reloads with a new context size.
///
/// Behavior reference: project-maya serve/server.py:6258-6259 at 7e68a30f.
pub const OVERLOADED_RELOADING: &str =
    "the model is reloading with a new context size; try again in a minute";

/// The `type` of an error body.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ErrorKind {
    /// `invalid_request_error`.
    InvalidRequest,
    /// `server_error`.
    Server,
    /// `overloaded_error`.
    Overloaded,
    /// `authentication_error`.
    Authentication,
    /// `permission_error`.
    Permission,
}

impl ErrorKind {
    /// The wire string.
    pub fn as_str(self) -> &'static str {
        match self {
            ErrorKind::InvalidRequest => "invalid_request_error",
            ErrorKind::Server => "server_error",
            ErrorKind::Overloaded => "overloaded_error",
            ErrorKind::Authentication => "authentication_error",
            ErrorKind::Permission => "permission_error",
        }
    }
}

/// The Python-like category of a malformed request (approved deviation P-3): the exception
/// classes the donor maps to `malformed request (...)`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MalformedCategory {
    /// A required field is missing (Python `KeyError`).
    KeyError,
    /// A field has the wrong type (Python `TypeError`).
    TypeError,
    /// A value lacks an expected member (Python `AttributeError`).
    AttributeError,
    /// An index is out of range (Python `IndexError`).
    IndexError,
}

impl MalformedCategory {
    /// The category name as written in the message.
    pub fn as_str(self) -> &'static str {
        match self {
            MalformedCategory::KeyError => "KeyError",
            MalformedCategory::TypeError => "TypeError",
            MalformedCategory::AttributeError => "AttributeError",
            MalformedCategory::IndexError => "IndexError",
        }
    }
}

/// Every error a request can end with, and the answer each one gives.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ApiError {
    /// The donor's `BadBody(status, message)`: a body that cannot be read, or a request the
    /// server cannot take now. `invalid_request_error` with the given status.
    BadBody {
        /// HTTP status.
        status: u16,
        /// Message text.
        message: String,
    },
    /// A `ValueError` raised while handling a request: 400 `invalid_request_error` (the
    /// donor's `error_body`, without a code). A JSON body that does not parse lands here.
    Validation {
        /// Message text (Python's `str(e)`).
        message: String,
    },
    /// The donor's `ContextOverflow`: 400 `invalid_request_error` with
    /// `"code": "context_length_exceeded"` after the message.
    ContextOverflow {
        /// Message text.
        message: String,
    },
    /// The donor's `JobError(status, message)` of the background Responses jobs:
    /// `server_error` with the given status.
    Job {
        /// HTTP status.
        status: u16,
        /// Message text.
        message: String,
    },
    /// The donor's `StoreBusy`: 503 `server_error`.
    StoreBusy {
        /// Message text.
        message: String,
    },
    /// The donor's `EngineDied`: 503 `server_error`, the message followed by
    /// `; the next request restarts it`.
    EngineDied {
        /// The engine's own message, without the suffix.
        message: String,
    },
    /// A field of the wrong shape: 400 `invalid_request_error` with
    /// `malformed request (<Category>: <detail>)` (approved deviation P-3).
    Malformed {
        /// The Python-like category.
        category: MalformedCategory,
        /// This server's detail text.
        detail: String,
    },
    /// An unknown route: 404 `{"error": {"message": "not found"}}`.
    NotFound,
    /// A chat route while the model reloads or the server updates: 503 `overloaded_error`,
    /// `Retry-After: 30`, body written with `ensure_ascii=True`.
    Overloaded {
        /// Message text.
        message: String,
    },
    /// A missing or wrong API key: 401 `authentication_error`,
    /// `missing or wrong API key`.
    Auth,
    /// A refused request: 403 `permission_error`.
    Permission {
        /// Message text.
        message: String,
    },
    /// The third convention, `{"error": <message>}`, with the given status (the
    /// model-management answers).
    Plain {
        /// HTTP status.
        status: u16,
        /// Message text.
        message: String,
    },
}

impl ApiError {
    /// `BadBody(status, message)`.
    pub fn bad_body(status: u16, message: impl Into<String>) -> Self {
        ApiError::BadBody {
            status,
            message: message.into(),
        }
    }

    /// A `ValueError` answered with 400.
    pub fn validation(message: impl Into<String>) -> Self {
        ApiError::Validation {
            message: message.into(),
        }
    }

    /// `ContextOverflow(message)`.
    pub fn context_overflow(message: impl Into<String>) -> Self {
        ApiError::ContextOverflow {
            message: message.into(),
        }
    }

    /// The context overflow when the prompt alone leaves no room to answer.
    ///
    /// Behavior reference: project-maya serve/server.py:3684-3687 at 7e68a30f.
    pub fn context_no_room(max_context: i64, prompt_tokens: usize) -> Self {
        Self::context_overflow(format!(
            "maximum context length is {max_context} tokens; prompt ({prompt_tokens} tokens) \
             leaves no room to answer in the context; requests are never truncated"
        ))
    }

    /// The context overflow when prompt plus the requested answer exceeds the context.
    ///
    /// Behavior reference: project-maya serve/server.py:3689-3693 at 7e68a30f.
    pub fn context_exceeded(max_context: i64, prompt_tokens: usize, max_new: i64) -> Self {
        Self::context_overflow(format!(
            "maximum context length is {max_context} tokens; prompt ({prompt_tokens} tokens) \
             + max tokens ({max_new}) exceeds the context; requests are never truncated"
        ))
    }

    /// The 503 the donor gives while the engine has not reported its context yet.
    ///
    /// Behavior reference: project-maya serve/server.py:3680-3681 at 7e68a30f.
    pub fn model_starting() -> Self {
        Self::bad_body(503, "the model is starting; try again in a moment")
    }

    /// `JobError(status, message)`.
    pub fn job(status: u16, message: impl Into<String>) -> Self {
        ApiError::Job {
            status,
            message: message.into(),
        }
    }

    /// `StoreBusy(message)`.
    pub fn store_busy(message: impl Into<String>) -> Self {
        ApiError::StoreBusy {
            message: message.into(),
        }
    }

    /// `EngineDied(message)`.
    pub fn engine_died(message: impl Into<String>) -> Self {
        ApiError::EngineDied {
            message: message.into(),
        }
    }

    /// A malformed request (approved deviation P-3).
    pub fn malformed(category: MalformedCategory, detail: impl Into<String>) -> Self {
        ApiError::Malformed {
            category,
            detail: detail.into(),
        }
    }

    /// An overloaded answer.
    pub fn overloaded(message: impl Into<String>) -> Self {
        ApiError::Overloaded {
            message: message.into(),
        }
    }

    /// A permission refusal.
    pub fn permission(message: impl Into<String>) -> Self {
        ApiError::Permission {
            message: message.into(),
        }
    }

    /// `{"error": message}` with `status`.
    pub fn plain(status: u16, message: impl Into<String>) -> Self {
        ApiError::Plain {
            status,
            message: message.into(),
        }
    }

    /// The HTTP status.
    pub fn status(&self) -> u16 {
        match self {
            ApiError::BadBody { status, .. }
            | ApiError::Job { status, .. }
            | ApiError::Plain { status, .. } => *status,
            ApiError::Validation { .. }
            | ApiError::ContextOverflow { .. }
            | ApiError::Malformed { .. } => 400,
            ApiError::StoreBusy { .. }
            | ApiError::EngineDied { .. }
            | ApiError::Overloaded { .. } => 503,
            ApiError::NotFound => 404,
            ApiError::Auth => 401,
            ApiError::Permission { .. } => 403,
        }
    }

    /// The body's `type`, or `None` for the conventions that have none.
    pub fn kind(&self) -> Option<ErrorKind> {
        match self {
            ApiError::BadBody { .. }
            | ApiError::Validation { .. }
            | ApiError::ContextOverflow { .. }
            | ApiError::Malformed { .. } => Some(ErrorKind::InvalidRequest),
            ApiError::Job { .. } | ApiError::StoreBusy { .. } | ApiError::EngineDied { .. } => {
                Some(ErrorKind::Server)
            }
            ApiError::Overloaded { .. } => Some(ErrorKind::Overloaded),
            ApiError::Auth => Some(ErrorKind::Authentication),
            ApiError::Permission { .. } => Some(ErrorKind::Permission),
            ApiError::NotFound | ApiError::Plain { .. } => None,
        }
    }

    /// The `code` of the body (only a context overflow has one).
    pub fn code(&self) -> Option<&'static str> {
        match self {
            ApiError::ContextOverflow { .. } => Some("context_length_exceeded"),
            _ => None,
        }
    }

    /// The message as the body carries it, and as the mid-answer log line prints it.
    pub fn message(&self) -> String {
        match self {
            ApiError::BadBody { message, .. }
            | ApiError::Validation { message }
            | ApiError::ContextOverflow { message }
            | ApiError::Job { message, .. }
            | ApiError::StoreBusy { message }
            | ApiError::Overloaded { message }
            | ApiError::Permission { message }
            | ApiError::Plain { message, .. } => message.clone(),
            ApiError::EngineDied { message } => format!("{message}; the next request restarts it"),
            ApiError::Malformed { category, detail } => {
                format!("malformed request ({}: {detail})", category.as_str())
            }
            ApiError::NotFound => String::from("not found"),
            ApiError::Auth => String::from("missing or wrong API key"),
        }
    }

    /// The `Retry-After` value in seconds, when the answer carries one.
    pub fn retry_after(&self) -> Option<u32> {
        match self {
            ApiError::Overloaded { .. } => Some(30),
            _ => None,
        }
    }

    /// The JSON body, byte for byte as the donor's `json.dumps` writes it.
    pub fn body(&self) -> String {
        // The overloaded body is the only one written with ensure_ascii=True.
        let ascii = matches!(self, ApiError::Overloaded { .. });
        let message = dumps_str(&self.message(), ascii);
        match (self, self.kind()) {
            (ApiError::Plain { .. }, _) => format!("{{\"error\": {message}}}"),
            (_, None) => format!("{{\"error\": {{\"message\": {message}}}}}"),
            (_, Some(kind)) => {
                let code = match self.code() {
                    Some(code) => format!(", \"code\": {}", dumps_str(code, ascii)),
                    None => String::new(),
                };
                format!(
                    "{{\"error\": {{\"type\": \"{}\", \"message\": {message}{code}}}}}",
                    kind.as_str()
                )
            }
        }
    }

    /// The complete answer: status, headers and body.
    pub fn to_response(&self) -> ErrorResponse {
        ErrorResponse {
            status: self.status(),
            retry_after: self.retry_after(),
            body: self.body(),
        }
    }
}

impl fmt::Display for ApiError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.message())
    }
}

impl std::error::Error for ApiError {}

impl From<LoadsError> for ApiError {
    /// A request body that does not parse. The donor's `json.loads` raises a `ValueError`
    /// (`JSONDecodeError`, `UnicodeDecodeError`, or the integer-digit limit), answered 400
    /// with `str(e)`. The nesting limit of `console_pyjson` (a `RecursionError` in CPython
    /// only when its stack runs out) is answered the same way. That 400 (proposal P-20), like
    /// the refusal of an unpaired surrogate (proposal P-19), awaits the owner's decision in
    /// the deviation register.
    fn from(e: LoadsError) -> Self {
        ApiError::validation(e.to_string())
    }
}

/// An error answer ready for the transport: the status, the headers in the donor's order and
/// the body. The transport adds the status line and its own `Server` and `Date` headers
/// before these, as `send_response` does.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ErrorResponse {
    /// HTTP status.
    pub status: u16,
    /// `Retry-After` in seconds, when present.
    pub retry_after: Option<u32>,
    /// The JSON body.
    pub body: String,
}

impl ErrorResponse {
    /// The headers in the donor's order: `Content-Type: application/json`, then
    /// `Retry-After` when present, then `Content-Length` (the body's length in bytes).
    pub fn headers(&self) -> Vec<(&'static str, String)> {
        let mut headers = vec![("Content-Type", String::from("application/json"))];
        if let Some(seconds) = self.retry_after {
            headers.push(("Retry-After", seconds.to_string()));
        }
        headers.push(("Content-Length", self.body.len().to_string()));
        headers
    }
}

/// Whether the answer to a request has begun. It becomes true when the status line is
/// written; after that an error can only be logged.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct AnswerState {
    started: bool,
}

impl AnswerState {
    /// A request whose answer has not begun.
    pub fn new() -> Self {
        Self::default()
    }

    /// Records that the status line has been written.
    pub fn mark_started(&mut self) {
        self.started = true;
    }

    /// Whether the status line has been written.
    pub fn is_started(&self) -> bool {
        self.started
    }
}

/// What to do with an error.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum FailAction {
    /// Nothing was sent yet: send this answer.
    Respond(ErrorResponse),
    /// The answer has begun: write this line to standard error and close the connection.
    LogAndClose(String),
}

/// The log prefix of server lines (decision B2).
pub const LOG_PREFIX: &str = "[console]";

/// The donor's `_fail`: an error answer while nothing was sent, otherwise only the log line
/// `[console] request failed mid-answer: <message>` and a closed connection.
///
/// The message is passed through [`log_safe`] so that engine or client text cannot add a
/// second, forged line to the server log; the HTTP body is unchanged. Log text is not a wire
/// parity surface.
///
/// Behavior reference: project-maya serve/server.py:6152-6158 at 7e68a30f.
pub fn fail(state: &AnswerState, error: &ApiError) -> FailAction {
    if state.is_started() {
        FailAction::LogAndClose(format!(
            "{LOG_PREFIX} request failed mid-answer: {}",
            log_safe(&error.message())
        ))
    } else {
        FailAction::Respond(error.to_response())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn text_file_limit_clamps() {
        assert_eq!(text_file_limit(0), 524_288);
        assert_eq!(text_file_limit(-5), 524_288);
        assert_eq!(text_file_limit(131_072), 524_288);
        assert_eq!(text_file_limit(131_073), 524_292);
        assert_eq!(text_file_limit(4_194_304), 16_777_216);
        assert_eq!(text_file_limit(i64::MAX), 16_777_216);
        assert_eq!(CTX_SLACK, 8);
    }

    #[test]
    fn kinds_have_their_wire_names() {
        assert_eq!(ErrorKind::InvalidRequest.as_str(), "invalid_request_error");
        assert_eq!(ErrorKind::Server.as_str(), "server_error");
        assert_eq!(ErrorKind::Overloaded.as_str(), "overloaded_error");
        assert_eq!(ErrorKind::Authentication.as_str(), "authentication_error");
        assert_eq!(ErrorKind::Permission.as_str(), "permission_error");
    }
}
