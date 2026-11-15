//! The error a request check raises, typed by the Python exception class the donor raises.
//!
//! The donor's checks raise `ValueError` with a message (answered 400
//! `invalid_request_error`), reach a `TypeError` on a field of the wrong shape (answered 400
//! `malformed request (...)`), and in two places reach an `OverflowError` that no handler
//! catches. `console-core` does not depend on `console-http`; API-07 maps each variant to
//! its error body.
//!
//! Behavior reference: project-maya serve/server.py:6287-6297 at 7e68a30f (the exception
//! mapping of `do_POST`).

use std::fmt;

/// A refused request, by the Python exception class the donor raises for it.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RequestError {
    /// The donor's `ValueError`: a 400 `invalid_request_error` whose message is this text,
    /// exactly as the donor writes it.
    Invalid(String),
    /// The donor's `TypeError` on a field of the wrong shape: a 400 `malformed request
    /// (TypeError: ...)`. The detail is Python's message; deviation P-3 lets the HTTP layer
    /// use its own detail text.
    Malformed {
        /// The Python exception class, `"TypeError"`.
        category: &'static str,
        /// Python's message for it.
        detail: String,
    },
    /// The donor's `OverflowError` (`int(float('inf'))`, `float(10**400)`), which no
    /// handler of the donor catches: the donor drops the connection without an answer. The
    /// mapping is API-07's (reported as an open question of API-04).
    Overflow(String),
}

impl RequestError {
    /// A `ValueError` with this message.
    pub fn invalid(message: impl Into<String>) -> Self {
        RequestError::Invalid(message.into())
    }

    /// A `TypeError` with Python's message.
    pub fn type_error(detail: impl Into<String>) -> Self {
        RequestError::Malformed {
            category: "TypeError",
            detail: detail.into(),
        }
    }

    /// The message text: the `ValueError` message, Python's `TypeError` message or the
    /// `OverflowError` message.
    pub fn message(&self) -> &str {
        match self {
            RequestError::Invalid(m) | RequestError::Overflow(m) => m,
            RequestError::Malformed { detail, .. } => detail,
        }
    }

    /// The Python exception class the donor raises: `ValueError`, `TypeError` or
    /// `OverflowError`.
    pub fn python_type(&self) -> &'static str {
        match self {
            RequestError::Invalid(_) => "ValueError",
            RequestError::Malformed { category, .. } => category,
            RequestError::Overflow(_) => "OverflowError",
        }
    }
}

impl fmt::Display for RequestError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.message())
    }
}

impl std::error::Error for RequestError {}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn each_variant_names_its_python_class_and_message() {
        let v = RequestError::invalid("temperature: a number");
        assert_eq!(
            (v.python_type(), v.message()),
            ("ValueError", "temperature: a number")
        );
        assert_eq!(v.to_string(), "temperature: a number");
        let t = RequestError::type_error("int() argument must be a string");
        assert_eq!(t.python_type(), "TypeError");
        assert_eq!(t.message(), "int() argument must be a string");
        let o = RequestError::Overflow("cannot convert float infinity to integer".into());
        assert_eq!(o.python_type(), "OverflowError");
    }
}
