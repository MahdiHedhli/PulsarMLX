//! Owned by ENG-02. The in-process scripted engine (the donor's `MockEngine`) and, behind
//! the `test-support` feature, the scriptable test engines (`doubles`) the donor's tests
//! define.
//!
//! The scripted engine implements the backend seam of `console_core::engine`: a
//! [`FakeFactory`] (`EngineFactory`) starts [`FakeEngine`] instances (`EngineInstance`)
//! on the driver thread; a generation runs through the ledger with
//! `generate_ledgered`; cancel reaches it through the `ControlProbe`. It replays scripts
//! that are already encoded, one token per step: each request takes the next script and
//! the last one repeats, the output is cut to `max_new`, cancel is checked before each
//! token, and pacing and figures are optional. The seam is synchronous: this module needs
//! no async runtime.
//!
//! Every engine here is synthetic: no model is behind it. Each reports
//! `Provenance::Synthetic` and passes `require_synthetic`, except the one double built to
//! be refused (`doubles::NotSyntheticEngine`), which exists only with the `test-support`
//! feature and which nothing in a configuration, a flag or an environment variable can
//! select. Nothing here is qualified beyond synthetic backends.

use std::sync::{Mutex, MutexGuard, PoisonError};

mod clock;
mod config;
mod deliver;
mod factory;
mod mock;

#[cfg(test)]
mod testutil;

#[cfg(any(test, feature = "test-support"))]
pub mod doubles;

pub use clock::{FakeClock, ManualClock, SystemClock, MANUAL_CLOCK_MAX_RECORDED};
pub use config::{
    reload_delay_from, tok_s_from, FakeConfigError, FakeScript, DEFAULT_MAX_CONTEXT,
    DEFAULT_RELOAD_DELAY, MAX_SCRIPTS, MAX_SCRIPT_TOKENS, RELOAD_DELAY_ENV, TOK_S_ENV,
};
pub use factory::{FakeEngine, FakeFactory, FakeProbe};
pub use mock::jitter_sleep_s;

/// The scripted engine's default model name, exactly `pulsar-console-synthetic`: the
/// donor's default names a real model, which would overclaim on a synthetic engine
/// (deviation PLAN-2, decided by the owner on 2026-11-14, settling OPEN-03). The server
/// reports it when the run config names no model; API-08 asserts it.
///
/// Behavior reference: project-maya serve/server.py:2383, 7292 at 7e68a30f.
pub const DEFAULT_MODEL_NAME: &str = "pulsar-console-synthetic";

/// The scripted engine's answer when the command line gives no script. The wiring encodes
/// it with the tokenizer and appends the end-of-turn id.
///
/// Behavior reference: project-maya serve/server.py:7287-7289 at 7e68a30f.
pub const DEFAULT_SCRIPT_TEXT: &str = "Thinking about it.</think>\n\nHello from the mock engine.";

/// The most alternatives a token's logprob row carries, as the scripted engine advertises
/// it (`INFO logprobs=20`).
///
/// Behavior reference: project-maya serve/server.py:502 at 7e68a30f.
pub const TOP_LOGPROBS_MAX: u8 = 20;

/// Locks a mutex, taking the data of a poisoned one: the state here is counters and
/// records, which stay meaningful after a panic elsewhere.
pub(crate) fn lock<T>(m: &Mutex<T>) -> MutexGuard<'_, T> {
    m.lock().unwrap_or_else(PoisonError::into_inner)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fake_default_model_name_is_the_decided_one() {
        // Deviation PLAN-2 (owner decision of 2026-11-14, OPEN-03).
        assert_eq!(DEFAULT_MODEL_NAME, "pulsar-console-synthetic");
        assert!(DEFAULT_MODEL_NAME.contains("synthetic"));
    }

    #[test]
    fn fake_default_script_is_the_donor_greeting() {
        assert_eq!(
            DEFAULT_SCRIPT_TEXT,
            "Thinking about it.</think>\n\nHello from the mock engine."
        );
    }
}
