//! The context rule: a request too long for the context is rejected, never truncated.
//!
//! Behavior reference: project-maya serve/server.py:163, 3680-3694 at 7e68a30f.

use crate::request::pynum::PyInt;
use crate::request::CTX_SLACK;

use super::error::TurnError;

/// The answer budget of a request, decided before any engine call.
///
/// - `max_context <= 0` (a start or reload that has not reported its context yet) is
///   [`TurnError::Starting`]: 503 "the model is starting; try again in a moment".
/// - `room = max_context - CTX_SLACK - prompt_tokens`.
/// - A `max_new` that is unset, 0 or negative means the room; so does any `max_new` with
///   `fit_max_tokens` when the room is below 1. A room below 1 is then
///   [`TurnError::ContextOverflow`] ("... leaves no room to answer in the context; ...").
/// - A `max_new` above the room is a [`TurnError::ContextOverflow`] ("... exceeds the
///   context; ..."), unless `fit_max_tokens` is on: then it is clamped to `max(1, room)`.
///
/// The overflow texts are the donor's, with OpenAI's wording "maximum context length is N
/// tokens", which OpenAI-compatible clients recognize as a context overflow.
///
/// Behavior reference: project-maya serve/server.py:3680-3694 at 7e68a30f.
pub fn context_rule(
    max_context: i64,
    prompt_tokens: usize,
    max_new: Option<&PyInt>,
    fit_max_tokens: bool,
) -> Result<u32, TurnError> {
    if max_context <= 0 {
        return Err(TurnError::Starting);
    }
    let prompt = i64::try_from(prompt_tokens).unwrap_or(i64::MAX);
    let room = max_context.saturating_sub(CTX_SLACK).saturating_sub(prompt);
    let unset = match max_new {
        None => true,
        Some(n) => n.is_zero() || n.is_negative(),
    };
    let budget = if unset || (fit_max_tokens && room < 1) {
        if room < 1 {
            return Err(TurnError::ContextOverflow {
                message: format!(
                    "maximum context length is {max_context} tokens; prompt ({prompt_tokens} \
                     tokens) leaves no room to answer in the context; requests are never \
                     truncated"
                ),
            });
        }
        room
    } else {
        // `unset` is false, so `max_new` is a positive integer here.
        let asked = max_new.cloned().unwrap_or_else(PyInt::zero);
        if asked > PyInt::from_i64(room) {
            if !fit_max_tokens {
                return Err(TurnError::ContextOverflow {
                    message: format!(
                        "maximum context length is {max_context} tokens; prompt \
                         ({prompt_tokens} tokens) + max tokens ({asked}) exceeds the context; \
                         requests are never truncated"
                    ),
                });
            }
            room.max(1)
        } else {
            // asked <= room <= max_context, so it fits.
            asked.to_i64().unwrap_or(room)
        }
    };
    Ok(u32::try_from(budget).unwrap_or(u32::MAX))
}

/// The `max_new` of one engine call: `max(1, min(left, room))`, where `room` is what the
/// context leaves after the call's prompt. The prompt of a later call can hold tokens the
/// request's `max_new` does not count, so the room caps it too.
///
/// Behavior reference: project-maya serve/server.py:4444-4451 at 7e68a30f.
pub fn call_budget(max_context: u32, prompt_tokens: usize, left: u32) -> u32 {
    let prompt = i64::try_from(prompt_tokens).unwrap_or(i64::MAX);
    let room = i64::from(max_context)
        .saturating_sub(CTX_SLACK)
        .saturating_sub(prompt);
    let n = room.min(i64::from(left)).max(1);
    u32::try_from(n).unwrap_or(1)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn n(v: i64) -> PyInt {
        PyInt::from_i64(v)
    }

    #[test]
    fn unset_or_non_positive_means_the_room() {
        for m in [None, Some(n(0)), Some(n(-1))] {
            assert_eq!(context_rule(4096, 20, m.as_ref(), false), Ok(4096 - 8 - 20));
        }
    }

    #[test]
    fn explicit_budget_is_kept_or_refused() {
        assert_eq!(context_rule(4096, 20, Some(&n(50)), false), Ok(50));
        let room = 4096 - 8 - 20;
        assert_eq!(context_rule(4096, 20, Some(&n(room)), false), Ok(4068));
        let err = context_rule(4096, 20, Some(&n(4096)), false).unwrap_err();
        assert_eq!(
            err.message(),
            "maximum context length is 4096 tokens; prompt (20 tokens) + max tokens (4096) \
             exceeds the context; requests are never truncated"
        );
        assert_eq!(err.code(), Some("context_length_exceeded"));
        // A budget beyond any machine integer is printed whole, as Python prints it.
        let huge = PyInt::from_decimal("123456789012345678901234567890").unwrap();
        assert!(context_rule(4096, 20, Some(&huge), false)
            .unwrap_err()
            .message()
            .contains("max tokens (123456789012345678901234567890)"));
    }

    #[test]
    fn no_room_is_refused_with_or_without_fit() {
        for fit in [false, true] {
            let err = context_rule(4096, 4088, None, fit).unwrap_err();
            assert_eq!(
                err.message(),
                "maximum context length is 4096 tokens; prompt (4088 tokens) leaves no room \
                 to answer in the context; requests are never truncated"
            );
            let err = context_rule(4096, 4088, Some(&n(100)), fit).unwrap_err();
            if fit {
                assert!(err.message().contains("leaves no room to answer"));
            } else {
                assert!(err.message().contains("exceeds the context"));
            }
        }
    }

    #[test]
    fn fit_clamps_an_overshoot_to_the_room() {
        assert_eq!(context_rule(4096, 20, Some(&n(4096)), true), Ok(4068));
        assert_eq!(context_rule(4096, 20, Some(&n(50)), true), Ok(50));
        assert_eq!(context_rule(4096, 4087, Some(&n(50)), true), Ok(1));
    }

    #[test]
    fn not_ready_is_starting() {
        assert_eq!(context_rule(0, 1, None, false), Err(TurnError::Starting));
        assert_eq!(context_rule(-3, 1, None, true), Err(TurnError::Starting));
        assert_eq!(
            TurnError::Starting.message(),
            "the model is starting; try again in a moment"
        );
    }

    #[test]
    fn call_budget_is_capped_by_the_room() {
        assert_eq!(call_budget(4096, 20, 50), 50);
        assert_eq!(call_budget(4096, 4080, 50), 8);
        assert_eq!(call_budget(4096, 5000, 50), 1);
        assert_eq!(call_budget(0, 0, 50), 1);
    }
}
