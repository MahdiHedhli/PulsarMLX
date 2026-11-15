//! What can end a turn with an error, classified as the donor classifies it.
//!
//! The donor raises Python exceptions out of `Service.prepare` and `Service.run`, and its
//! HTTP handler maps each class to a status and body. `console-core` does not depend on
//! `console-http`: [`TurnError`] carries the class and the donor's text, and API-07 maps it
//! (contract section 10, the "Server mapping" column).
//!
//! Behavior reference: project-maya serve/server.py:412-432, 560-568, 6283-6297 at
//! 7e68a30f, and project-maya tools/strata_tokenizer.py:361-366 at 7e68a30f.

use std::fmt;

use crate::engine::{EngineFailure, FailureKind};
use crate::request::RequestError;

/// The text in an engine's error that marks numbers gone non-finite (a NaN or an infinity
/// in a route): the engine has dropped that conversation's state.
///
/// Behavior reference: project-maya serve/server.py:431-432 at 7e68a30f.
pub const NONFINITE: &str = "non-finite";

/// The donor's text when a request reaches its turn while the server is stopping.
///
/// Behavior reference: project-maya serve/server.py:4364-4365 at 7e68a30f.
pub const STOPPING_MESSAGE: &str =
    "the server is stopping: send the request again once the model is back";

/// The donor's text while the engine has not reported its context yet.
///
/// Behavior reference: project-maya serve/server.py:3680-3681 at 7e68a30f.
pub const STARTING_MESSAGE: &str = "the model is starting; try again in a moment";

/// Why a turn failed.
#[derive(Debug, Clone, PartialEq)]
pub enum TurnError {
    /// The donor's `ContextOverflow` (a `ValueError` with the code
    /// `context_length_exceeded`): 400 `invalid_request_error`, with the code.
    ContextOverflow {
        /// The donor's text, "maximum context length is N tokens; ...".
        message: String,
    },
    /// The engine has not reported its context yet (the donor's `BadBody(503, ...)`):
    /// 503 `invalid_request_error`, [`STARTING_MESSAGE`].
    Starting,
    /// A request-level Python exception of the donor, typed by its class: the server is
    /// stopping (`ValueError`, [`STOPPING_MESSAGE`]); a token id outside the tokenizer's
    /// vocabulary (`IndexError`, which the donor answers 400 `malformed request
    /// (IndexError: ...)` before the first byte and only logs after it); a prompt-progress
    /// time that Python's `round` refuses (`ValueError` for a NaN, `OverflowError` for an
    /// infinity).
    Request(RequestError),
    /// An engine failure: `Died` (503 `server_error`, "<message>; the next request
    /// restarts it"), `Reported` (the engine's `ERR`: 400 before the first byte, a stream
    /// error after), `InvalidToken`, `Protocol`, `StartFailed` (a start that failed or an
    /// engine the synthetic-only guard refused, with the guard's line), and the others of
    /// contract section 10.
    Engine(EngineFailure),
}

impl TurnError {
    /// The error body's `code`, for the one error that has one.
    pub fn code(&self) -> Option<&'static str> {
        match self {
            TurnError::ContextOverflow { .. } => Some("context_length_exceeded"),
            _ => None,
        }
    }

    /// The message, as the donor's `str(e)` gives it.
    pub fn message(&self) -> String {
        match self {
            TurnError::ContextOverflow { message } => message.clone(),
            TurnError::Starting => STARTING_MESSAGE.to_owned(),
            TurnError::Request(e) => e.message().to_owned(),
            TurnError::Engine(f) => f.message.as_str().to_owned(),
        }
    }

    /// The engine failure, when this is one.
    pub fn engine_failure(&self) -> Option<&EngineFailure> {
        match self {
            TurnError::Engine(f) => Some(f),
            _ => None,
        }
    }

    /// The server is stopping.
    pub fn stopping() -> Self {
        TurnError::Request(RequestError::invalid(STOPPING_MESSAGE))
    }

    /// A token id at or beyond the tokenizer's vocabulary of `vocab` ids: the donor's
    /// `IndexError("token id N is outside the vocabulary (V)")`, raised when the server
    /// decodes the token (#805).
    ///
    /// Behavior reference: project-maya tools/strata_tokenizer.py:361-366 and
    /// serve/server.py:6293-6297 at 7e68a30f.
    pub fn out_of_vocabulary(id: u32, vocab: u32) -> Self {
        TurnError::Request(RequestError::Malformed {
            category: "IndexError",
            detail: format!("token id {id} is outside the vocabulary ({vocab})"),
        })
    }

    /// An engine failure as the turn reports it: `NotReady` is [`TurnError::Starting`],
    /// and the ledger's out-of-vocabulary failure (an id beyond the engine's own
    /// vocabulary) is the donor's `IndexError` of [`TurnError::out_of_vocabulary`]. Any
    /// other failure is kept as it is.
    pub fn from_engine(f: EngineFailure) -> Self {
        match f.kind {
            FailureKind::NotReady => TurnError::Starting,
            FailureKind::InvalidToken => match out_of_vocabulary_parts(&f) {
                Some((id, vocab)) => TurnError::out_of_vocabulary(id, vocab),
                None => TurnError::Engine(f),
            },
            _ => TurnError::Engine(f),
        }
    }
}

impl fmt::Display for TurnError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.message())
    }
}

impl std::error::Error for TurnError {}

/// True for an engine error the donor retries once before the first token: a `ValueError`
/// (the engine's `ERR`, or a token-id error) whose text contains [`NONFINITE`].
///
/// Behavior reference: project-maya serve/server.py:4433-4454 at 7e68a30f.
pub fn is_non_finite(f: &EngineFailure) -> bool {
    matches!(f.kind, FailureKind::Reported | FailureKind::InvalidToken)
        && f.message.as_str().contains(NONFINITE)
}

/// The id and vocabulary size of the ledger's out-of-vocabulary failure
/// ([`EngineFailure::out_of_vocabulary`]); `None` for any other failure.
fn out_of_vocabulary_parts(f: &EngineFailure) -> Option<(u32, u32)> {
    f.out_of_vocabulary_parts()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn classes_and_texts() {
        let s = TurnError::stopping();
        assert_eq!(s.message(), STOPPING_MESSAGE);
        assert!(matches!(&s, TurnError::Request(e) if e.python_type() == "ValueError"));
        let o = TurnError::out_of_vocabulary(300, 262);
        assert_eq!(o.message(), "token id 300 is outside the vocabulary (262)");
        assert!(matches!(&o, TurnError::Request(e) if e.python_type() == "IndexError"));
        assert_eq!(o.code(), None);
        assert_eq!(TurnError::Starting.to_string(), STARTING_MESSAGE);
    }

    #[test]
    fn engine_failures_map() {
        assert_eq!(
            TurnError::from_engine(EngineFailure::not_ready()),
            TurnError::Starting
        );
        assert_eq!(
            TurnError::from_engine(EngineFailure::out_of_vocabulary(9, 8)),
            TurnError::out_of_vocabulary(9, 8)
        );
        let neg = EngineFailure::negative_token(-1);
        assert_eq!(TurnError::from_engine(neg.clone()), TurnError::Engine(neg));
        let died = EngineFailure::stopped_unexpectedly(Some(-9));
        assert_eq!(
            TurnError::from_engine(died.clone()).engine_failure(),
            Some(&died)
        );
    }

    #[test]
    fn non_finite_is_read_from_the_text() {
        assert!(is_non_finite(&EngineFailure::reported(
            "glm router: layer 7 decode invalid expert ID or non-finite score"
        )));
        assert!(!is_non_finite(&EngineFailure::reported(
            "verify: layer 31 never rang"
        )));
        assert!(!is_non_finite(&EngineFailure::died("non-finite")));
    }
}
