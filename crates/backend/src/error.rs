//! Bounded, backend-neutral contract errors.

use std::fmt;

/// Maximum number of Unicode scalar values retained in a public diagnostic.
pub const MAX_ERROR_MESSAGE_CHARS: usize = 512;

/// Stable semantic categories shared by contract callers.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ErrorCategory {
    InvalidSelection,
    InvalidCapability,
    InvalidStateTransition,
    InvalidTensor,
    ArithmeticOverflow,
    InvalidComparison,
    InvalidEvidence,
    InvalidQuantization,
    InvalidModel,
    InvalidBenchmark,
    ResourceLimit,
}

/// A bounded diagnostic that never carries backend implementation objects.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ContractError {
    category: ErrorCategory,
    code: &'static str,
    message: String,
}

impl ContractError {
    pub fn new(category: ErrorCategory, code: &'static str, message: impl AsRef<str>) -> Self {
        let code = if valid_code(code) {
            code
        } else {
            "invalid_error_code"
        };
        Self {
            category,
            code,
            message: sanitize_message(message.as_ref()),
        }
    }

    pub fn category(&self) -> ErrorCategory {
        self.category
    }

    pub fn code(&self) -> &'static str {
        self.code
    }

    pub fn message(&self) -> &str {
        &self.message
    }
}

impl fmt::Display for ContractError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{}: {}", self.code, self.message)
    }
}

impl std::error::Error for ContractError {}

fn valid_code(code: &str) -> bool {
    !code.is_empty()
        && code.len() <= 64
        && code
            .bytes()
            .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || byte == b'_')
}

fn sanitize_message(message: &str) -> String {
    let mut sanitized = String::new();
    for (index, token) in message.split_whitespace().enumerate() {
        if index > 0 {
            sanitized.push(' ');
        }
        if looks_like_private_path(token) {
            sanitized.push_str("<redacted-path>");
        } else {
            sanitized.push_str(token);
        }
    }

    if sanitized.is_empty() {
        sanitized.push_str("contract validation failed");
    }

    let mut bounded: String = sanitized.chars().take(MAX_ERROR_MESSAGE_CHARS).collect();
    if sanitized.chars().count() > MAX_ERROR_MESSAGE_CHARS {
        bounded.pop();
        bounded.push('…');
    }
    bounded
}

fn looks_like_private_path(token: &str) -> bool {
    token.starts_with('/')
        || token.starts_with("~/")
        || token.contains("/Users/")
        || token.contains("/home/")
        || token.contains("\\Users\\")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn diagnostics_are_bounded_and_redact_private_paths() {
        let long = format!("failed at /Users/private/model.gguf {}", "x".repeat(700));
        let error = ContractError::new(ErrorCategory::InvalidEvidence, "invalid_evidence", long);

        assert!(!error.message().contains("/Users/private"));
        assert!(error.message().chars().count() <= MAX_ERROR_MESSAGE_CHARS);
    }

    #[test]
    fn invalid_codes_are_replaced_with_a_stable_value() {
        let error = ContractError::new(ErrorCategory::InvalidEvidence, "Bad Code", "failure");
        assert_eq!(error.code(), "invalid_error_code");
    }
}
