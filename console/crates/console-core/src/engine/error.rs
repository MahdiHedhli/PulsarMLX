//! Engine failures (contract section 10).

use std::fmt;

use super::text::BoundedText;

/// The class of an [`EngineFailure`].
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum FailureKind {
    /// The process ended, the pipe closed, or the runtime panicked.
    Died,
    /// The engine's `ERR` text.
    Reported,
    /// `max_context == 0`.
    NotReady,
    /// A multi-mode request heard nothing for the quiet limit.
    NeverAnswered,
    /// A negative or out-of-vocabulary id.
    InvalidToken,
    /// The request needs a capability the descriptor lacks.
    Unsupported,
    /// A ledger violation.
    Protocol,
    /// The engine exited before `READY`, or was refused at admission.
    StartFailed,
}

impl FailureKind {
    /// A short lower-case name for logs.
    pub fn as_str(self) -> &'static str {
        match self {
            FailureKind::Died => "died",
            FailureKind::Reported => "reported",
            FailureKind::NotReady => "not_ready",
            FailureKind::NeverAnswered => "never_answered",
            FailureKind::InvalidToken => "invalid_token",
            FailureKind::Unsupported => "unsupported",
            FailureKind::Protocol => "protocol",
            FailureKind::StartFailed => "start_failed",
        }
    }
}

impl fmt::Display for FailureKind {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

/// One failure of an engine call or start. The message carries the donor's text where
/// the donor has one; none of those texts carries a product name (BRAND-1).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EngineFailure {
    /// The class.
    pub kind: FailureKind,
    /// The message, bounded.
    pub message: BoundedText,
    /// The instance must not be used again.
    pub poisoned: bool,
    /// Tokens the ledger accepted before the failure.
    pub after_tokens: u32,
}

impl EngineFailure {
    fn new(kind: FailureKind, message: &str, poisoned: bool) -> Self {
        Self {
            kind,
            message: BoundedText::message(message),
            poisoned,
            after_tokens: 0,
        }
    }

    /// The engine died with a stated reason (for example a stall watchdog's). Poisoned.
    pub fn died(reason: &str) -> Self {
        Self::new(FailureKind::Died, reason, true)
    }

    /// The engine ended unexpectedly: "the engine stopped unexpectedly (exit code N)".
    /// An unknown code prints as `None`, as the donor's f-string does. Poisoned.
    ///
    /// Behavior reference: project-maya serve/server.py:1380, 1406 at 7e68a30f.
    pub fn stopped_unexpectedly(exit_code: Option<i32>) -> Self {
        let code = match exit_code {
            Some(c) => c.to_string(),
            None => "None".to_owned(),
        };
        Self::died(&format!(
            "the engine stopped unexpectedly (exit code {code})"
        ))
    }

    /// The engine's `ERR` text, as the line adapter extracted it. Not poisoned.
    ///
    /// Behavior reference: project-maya serve/server.py:1448-1452 at 7e68a30f.
    pub fn reported(text: &str) -> Self {
        Self::new(FailureKind::Reported, text, false)
    }

    /// The engine is not ready: "the model is starting; try again in a moment".
    ///
    /// Behavior reference: project-maya serve/server.py:3680-3681 at 7e68a30f.
    pub fn not_ready() -> Self {
        Self::new(
            FailureKind::NotReady,
            "the model is starting; try again in a moment",
            false,
        )
    }

    /// A multi-mode request heard nothing of its own for `quiet_s` seconds. The seconds
    /// are printed with no decimals, rounding half to even as Python's `:.0f` does on the
    /// exact binary value. Not poisoned: the request was stopped, the engine runs on.
    ///
    /// Behavior reference: project-maya serve/server.py:1609-1610 at 7e68a30f.
    pub fn never_answered(quiet_s: f64) -> Self {
        Self::new(
            FailureKind::NeverAnswered,
            &format!(
                "the engine never answered this request ({quiet_s:.0} s without a line of its \
                 own); it was stopped"
            ),
            false,
        )
    }

    /// A negative token id: the engine's sampling failed. Not poisoned.
    ///
    /// Behavior reference: project-maya serve/server.py:560-568 at 7e68a30f.
    pub fn negative_token(id: i64) -> Self {
        Self::new(
            FailureKind::InvalidToken,
            &format!(
                "the engine could not pick a token (it wrote the id {id}: its sampling failed - \
                 the engine's log says why)"
            ),
            false,
        )
    }

    /// A token id at or beyond the vocabulary. The donor has no check of its own at this
    /// level: its tokenizer raises an `IndexError` when the id is decoded, and the turn
    /// driver maps this failure to that error (`console_core::turn`). Not poisoned.
    pub fn out_of_vocabulary(id: u32, vocab_size: u32) -> Self {
        Self::new(
            FailureKind::InvalidToken,
            &format!(
                "the engine wrote the token id {id}, outside its vocabulary of {vocab_size} ids"
            ),
            false,
        )
    }

    /// The token id and the vocabulary size of an [`EngineFailure::out_of_vocabulary`]
    /// failure, and `None` for any other failure. They are read back from the message,
    /// which this file alone writes, and are accepted only when they rebuild it.
    pub fn out_of_vocabulary_parts(&self) -> Option<(u32, u32)> {
        if self.kind != FailureKind::InvalidToken {
            return None;
        }
        let text = self.message.as_str();
        let rest = text.strip_prefix("the engine wrote the token id ")?;
        let (id, rest) = rest.split_once(", outside its vocabulary of ")?;
        let vocab = rest.strip_suffix(" ids")?;
        let id: u32 = id.parse().ok()?;
        let vocab: u32 = vocab.parse().ok()?;
        (Self::out_of_vocabulary(id, vocab).message.as_str() == text).then_some((id, vocab))
    }

    /// The request needs something the engine does not offer. Not poisoned.
    pub fn unsupported(what: &str) -> Self {
        Self::new(
            FailureKind::Unsupported,
            &format!("unsupported: {what}"),
            false,
        )
    }

    /// A violation of the seam's ordering or counting rules. Poisoned.
    pub fn protocol(detail: &str) -> Self {
        Self::new(
            FailureKind::Protocol,
            &format!("engine protocol violation: {detail}"),
            true,
        )
    }

    /// The engine exited before it was ready, naming its log when there is one.
    /// Poisoned.
    ///
    /// Behavior reference: project-maya serve/server.py:941-947 at 7e68a30f.
    pub fn exited_before_ready(log: Option<&str>) -> Self {
        let mut text = String::from("the engine exited before it was ready");
        if let Some(log) = log.filter(|l| !l.is_empty()) {
            text.push_str(&format!(" (see {log})"));
        }
        Self::new(FailureKind::StartFailed, &text, true)
    }

    /// The same failure with `after_tokens` set.
    pub fn with_after_tokens(mut self, after_tokens: u32) -> Self {
        self.after_tokens = after_tokens;
        self
    }
}

impl fmt::Display for EngineFailure {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.message.as_str())
    }
}

impl std::error::Error for EngineFailure {}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn out_of_vocabulary_parts_round_trip() {
        let f = EngineFailure::out_of_vocabulary(300, 262);
        assert_eq!(f.out_of_vocabulary_parts(), Some((300, 262)));
        assert_eq!(
            EngineFailure::unsupported("x").out_of_vocabulary_parts(),
            None
        );
        assert_eq!(EngineFailure::not_ready().out_of_vocabulary_parts(), None);
    }

    #[test]
    fn donor_texts_are_reproduced() {
        assert_eq!(
            EngineFailure::stopped_unexpectedly(Some(137)).to_string(),
            "the engine stopped unexpectedly (exit code 137)"
        );
        assert_eq!(
            EngineFailure::stopped_unexpectedly(None).to_string(),
            "the engine stopped unexpectedly (exit code None)"
        );
        assert_eq!(
            EngineFailure::not_ready().to_string(),
            "the model is starting; try again in a moment"
        );
        assert_eq!(
            EngineFailure::negative_token(-1).to_string(),
            "the engine could not pick a token (it wrote the id -1: its sampling failed - the \
             engine's log says why)"
        );
        assert_eq!(
            EngineFailure::never_answered(30.4).to_string(),
            "the engine never answered this request (30 s without a line of its own); it was \
             stopped"
        );
        assert_eq!(
            EngineFailure::exited_before_ready(Some("engine.txt")).to_string(),
            "the engine exited before it was ready (see engine.txt)"
        );
        assert_eq!(
            EngineFailure::exited_before_ready(None).to_string(),
            "the engine exited before it was ready"
        );
    }

    #[test]
    fn never_answered_rounds_half_to_even() {
        // Python: f"{2.5:.0f}" == "2", f"{3.5:.0f}" == "4", f"{0.5:.0f}" == "0".
        for (v, want) in [(2.5, "(2 s"), (3.5, "(4 s"), (0.5, "(0 s"), (59.9, "(60 s")] {
            let text = EngineFailure::never_answered(v).to_string();
            assert!(text.contains(want), "{v}: {text}");
        }
    }

    #[test]
    fn kinds_and_poisoning() {
        assert!(EngineFailure::died("x").poisoned);
        assert!(EngineFailure::protocol("x").poisoned);
        assert!(EngineFailure::exited_before_ready(None).poisoned);
        assert!(!EngineFailure::reported("x").poisoned);
        assert!(!EngineFailure::negative_token(-1).poisoned);
        assert!(!EngineFailure::not_ready().poisoned);
        assert!(!EngineFailure::unsupported("command").poisoned);
        assert_eq!(
            EngineFailure::out_of_vocabulary(9, 8).kind,
            FailureKind::InvalidToken
        );
        assert_eq!(
            EngineFailure::reported("x")
                .with_after_tokens(3)
                .after_tokens,
            3
        );
        let long = "e".repeat(10_000);
        assert!(EngineFailure::reported(&long).message.was_truncated());
    }
}
