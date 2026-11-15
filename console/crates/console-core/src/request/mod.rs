//! Owned by API-04. Request validation over the order-preserving JSON map, with the donor's
//! messages, and the request-level defaults the server shares between packages.
//!
//! - [`strip_internal_keys`] removes every top-level client key that begins with `_` at the
//!   dialect boundary, before any processing (deviation SEC-6.1). Internal markers travel
//!   in typed form ([`InternalFlags`]; deviation SEC-6.2).
//! - [`check_request`] runs the donor's checks on the sampling fields, the loop guard,
//!   `logit_bias`, `ablate` (deviation POL-1), `ignore_eos` and `logprobs`, against the
//!   engine's capability flags, and rewrites the fields the donor rewrites.
//! - [`SharedDefaults`] and [`with_shared`] are the Chat settings shared with other clients.
//! - [`client_stop_strings`], [`openai_max_tokens`] and [`anthropic_max_tokens`] read a
//!   request's stop strings and answer budget.
//! - [`CTX_SLACK`], [`TEXT_FILE_MIN`], [`TEXT_FILE_MAX`] and [`text_file_limit`] are the
//!   server's shared limits.
//!
//! Python's numeric coercions (`bool` is an `int`, `float(" 5 ")`, integers of any size)
//! are reproduced in [`pynum`]; [`pyrepr`] writes Python's `repr` for the messages that
//! quote client text. Errors are [`RequestError`], typed by the Python exception class the
//! donor raises; `console-http` maps them to error bodies (API-07).
//!
//! Qualified on synthetic backends only.

mod checks;
mod error;
pub mod pynum;
pub mod pyrepr;
mod shared;

pub use checks::{
    anthropic_max_tokens, check_request, check_request_sampling, client_stop_strings,
    logit_bias_of, logprobs_asked, logprobs_of, openai_max_tokens, CheckContext, CheckedRequest,
    LogitBias, LOGIT_BIAS_MAX_ID, SAMPLING_TYPES, STOP_STRINGS_MAX, TOP_LOGPROBS_MAX,
};
pub use error::RequestError;
pub use shared::{
    clean_shared_defaults, effort_level, effort_name, with_shared, Dialect, InternalFlags,
    SharedDefaults, EFFORT_WORDS, SHARED_KEYS,
};

use serde_json::{Map, Value};

/// The margin the engine keeps between prompt plus answer and the context size: a request
/// is refused when `prompt + max_new + CTX_SLACK > context`.
///
/// Behavior reference: project-maya serve/server.py:163 at 7e68a30f.
pub const CTX_SLACK: i64 = 8;

/// The smallest text-file limit the chat page uses (512 KiB).
///
/// Behavior reference: project-maya serve/server.py:164 at 7e68a30f.
pub const TEXT_FILE_MIN: i64 = 512 * 1024;

/// The largest text-file limit the chat page uses (16 MiB).
///
/// Behavior reference: project-maya serve/server.py:164 at 7e68a30f.
pub const TEXT_FILE_MAX: i64 = 16 * 1024 * 1024;

/// The largest text file the chat page attaches for a context of `context` tokens: about
/// four bytes a token, at least [`TEXT_FILE_MIN`] and at most [`TEXT_FILE_MAX`]
/// (`max(TEXT_FILE_MIN, min(TEXT_FILE_MAX, int(context or 0) * 4))`).
///
/// Behavior reference: project-maya serve/server.py:167-171 at 7e68a30f.
pub fn text_file_limit(context: i64) -> i64 {
    TEXT_FILE_MIN.max(TEXT_FILE_MAX.min(context.saturating_mul(4)))
}

/// Removes every top-level key that begins with `_` from a client's request, and returns
/// how many were removed. Called at the dialect boundary before any other processing, so
/// that no client can set an internal marker such as `_prefill`, `_think_budget` or
/// `_restore`.
///
/// Deviation SEC-6.1: the donor removes only `_restore` and reads the other markers from
/// the same dictionary (project-maya serve/server.py:1218-1225 at 7e68a30f).
pub fn strip_internal_keys(req: &mut Map<String, Value>) -> usize {
    let before = req.len();
    req.retain(|k, _| !k.starts_with('_'));
    before - req.len()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn text_file_limit_clamps() {
        assert_eq!(text_file_limit(0), 524_288);
        assert_eq!(text_file_limit(-5), 524_288);
        assert_eq!(text_file_limit(200_000), 800_000);
        assert_eq!(text_file_limit(i64::MAX), 16 * 1024 * 1024);
        assert_eq!(CTX_SLACK, 8);
    }

    // Deviation SEC-6.1: every top-level client key beginning with `_` is removed.
    #[test]
    fn underscore_keys_are_stripped_at_the_boundary() {
        let v = console_pyjson::loads::loads(
            r#"{"_prefill": "x", "model": "m", "_think_budget": 5, "_": 1,
                "messages": [{"_restore": 1}], "temperature": 0.2, "_restore": [1]}"#,
        )
        .unwrap();
        let mut m = v.as_object().unwrap().clone();
        assert_eq!(strip_internal_keys(&mut m), 4);
        let keys: Vec<_> = m.keys().map(String::as_str).collect();
        assert_eq!(keys, ["model", "messages", "temperature"]);
        // Only the top level: nested content is the dialect's and stays as sent.
        assert_eq!(m["messages"][0]["_restore"], 1);
        assert_eq!(strip_internal_keys(&mut m), 0);
    }
}
