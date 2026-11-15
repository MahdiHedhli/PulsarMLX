//! Errors of the scenario format and its companion contract files.
//!
//! Every error names the place it was found as a JSON pointer (RFC 6901) into the
//! document, so a reviewer can go straight to the offending value. The empty pointer is
//! the document itself.

use std::fmt;

/// One problem found while reading a scenario, a rename map or a volatile-field list.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ScenarioError {
    /// JSON pointer to the value at fault; empty for the whole document.
    pub pointer: String,
    /// What is wrong there.
    pub kind: ErrorKind,
}

/// What is wrong at [`ScenarioError::pointer`].
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ErrorKind {
    /// The text is not JSON. Line and column are 1-based, as `serde_json` reports them.
    Syntax {
        /// Line of the first character the reader could not accept.
        line: usize,
        /// Column of that character.
        column: usize,
        /// The reader's own description.
        message: String,
    },
    /// The document is larger than the limit for its kind, in bytes.
    TooLarge {
        /// The limit in bytes.
        limit: usize,
    },
    /// An object holds the same key twice. The pointer names the object.
    DuplicateKey {
        /// The repeated key.
        key: String,
    },
    /// An object holds a key the format does not define. The pointer names the object.
    UnknownField {
        /// The key that is not allowed.
        field: String,
    },
    /// An object lacks a key the format requires. The pointer names the object.
    MissingField {
        /// The key that is required.
        field: &'static str,
    },
    /// A value has the wrong JSON type.
    WrongType {
        /// What the format wants there.
        expected: &'static str,
        /// What the document has there.
        found: &'static str,
    },
    /// An integer lies outside its allowed range (inclusive bounds).
    OutOfRange {
        /// Smallest allowed value.
        min: u64,
        /// Largest allowed value.
        max: u64,
    },
    /// A string is longer than its limit, counted in Unicode scalar values.
    TooLong {
        /// The limit in characters.
        limit: usize,
    },
    /// An array or object holds more entries than its limit.
    TooMany {
        /// The limit in entries.
        limit: usize,
    },
    /// An array that must hold at least one entry is empty.
    Empty,
    /// A value has the right type but is not acceptable, for the reason given.
    InvalidValue {
        /// Why the value is refused.
        reason: String,
    },
    /// Two keys that exclude each other are both present. The pointer names the object.
    Exclusive {
        /// The first key, in the format's order.
        first: &'static str,
        /// The second key.
        second: &'static str,
    },
    /// A string holds a substitution token the format does not define.
    UnknownToken {
        /// The token as written, with its braces.
        token: String,
    },
    /// A substitution token has no value in the run-time context.
    UnboundToken {
        /// The token as written, with its braces.
        token: String,
    },
    /// The file name does not match the scenario's `id`.
    IdMismatch {
        /// The file stem found.
        file_stem: String,
    },
    /// The file could not be read.
    Io {
        /// The operating system's description.
        message: String,
    },
}

impl ScenarioError {
    /// An error at `pointer`.
    pub fn new(pointer: impl Into<String>, kind: ErrorKind) -> Self {
        Self {
            pointer: pointer.into(),
            kind,
        }
    }

    /// An [`ErrorKind::InvalidValue`] error at `pointer`.
    pub fn invalid(pointer: impl Into<String>, reason: impl Into<String>) -> Self {
        Self::new(
            pointer,
            ErrorKind::InvalidValue {
                reason: reason.into(),
            },
        )
    }
}

impl fmt::Display for ScenarioError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let at = if self.pointer.is_empty() {
            "(document)"
        } else {
            self.pointer.as_str()
        };
        write!(f, "{at}: ")?;
        match &self.kind {
            ErrorKind::Syntax {
                line,
                column,
                message,
            } => write!(f, "not JSON at line {line} column {column}: {message}"),
            ErrorKind::TooLarge { limit } => write!(f, "larger than {limit} bytes"),
            ErrorKind::DuplicateKey { key } => write!(f, "duplicate key {key:?}"),
            ErrorKind::UnknownField { field } => write!(f, "unknown field {field:?}"),
            ErrorKind::MissingField { field } => write!(f, "missing field {field:?}"),
            ErrorKind::WrongType { expected, found } => {
                write!(f, "expected {expected}, found {found}")
            }
            ErrorKind::OutOfRange { min, max } => {
                write!(f, "out of range: allowed {min} to {max}")
            }
            ErrorKind::TooLong { limit } => write!(f, "longer than {limit} characters"),
            ErrorKind::TooMany { limit } => write!(f, "more than {limit} entries"),
            ErrorKind::Empty => write!(f, "must not be empty"),
            ErrorKind::InvalidValue { reason } => write!(f, "{reason}"),
            ErrorKind::Exclusive { first, second } => {
                write!(f, "{first:?} and {second:?} exclude each other")
            }
            ErrorKind::UnknownToken { token } => write!(f, "unknown substitution token {token}"),
            ErrorKind::UnboundToken { token } => {
                write!(f, "substitution token {token} has no value here")
            }
            ErrorKind::IdMismatch { file_stem } => {
                write!(f, "id does not match the file name {file_stem:?}")
            }
            ErrorKind::Io { message } => write!(f, "cannot read: {message}"),
        }
    }
}

impl std::error::Error for ScenarioError {}

/// Result type of this module.
pub type Result<T> = std::result::Result<T, ScenarioError>;
