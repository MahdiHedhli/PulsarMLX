//! Provenance: translated from project-maya serve/test_server.py (`CTX`, `RecordingEngine`, `ClockedEngine`, the `GoneClients` `HeldEngine` set-up) and serve/test_logprobs.py (`LpEngine`, the `Http` set-up) at 7e68a30f (MIT); license text in console/LICENSES/project-maya-MIT.txt.
//!
//! The test engines of the HTTP tests, over the ENG-02 scripted engine.
//!
//! The doubles themselves (Recording, Held, Clocked, Lp, Dying and the others) are ENG-02's
//! `console_engine::fake::doubles`; this module does not copy them. It gives the HTTP tests
//! the donor's set-up in one call: the script text encoded with the byte tokenizer
//! (special literals parsed, the end-of-turn id appended, as the donor's `MockEngine`
//! does), the donor's context of 4096 tokens, and the double built from it. Each
//! constructor returns the factory; clones share their counters, so a test keeps one clone
//! to steer and observe the engine and gives another to the
//! [`TestServer`](crate::server::TestServer).
//!
//! Every engine here is synthetic and passes `require_synthetic`. The one double built to
//! be refused, `NotSyntheticEngine`, is re-exported for the refusal tests only; nothing in
//! the kit selects it unless a test names it.
//!
//! Behavior reference: project-maya serve/server.py:199-213 (`MockEngine.__init__`) and
//! serve/test_server.py:26-35, 2367-2373 at 7e68a30f.

use std::sync::Arc;

use console_core::engine::EngineFactory;
use console_tokenizer::byte_tok::{ByteTokenizer, EOS_ID};

pub use console_engine::fake::doubles::{
    BrokenEngine, BudgetEngine, ClockedEngine, DyingEngine, ErrEngine, HalfDeadEngine, HeldEngine,
    LifecycleEngine, LpEngine, NonFiniteEngine, NotSyntheticEngine, PacedEngine, PausingEngine,
    Recording, RecordingEngine, RecordingPrompt, ResumingEngine, Sampled, CLOCKED_REUSED,
    HELD_POLL,
};
pub use console_engine::fake::{
    FakeClock, FakeConfigError, FakeFactory, FakeProbe, FakeScript, ManualClock, SystemClock,
    DEFAULT_MODEL_NAME,
};

/// The donor's test context, `CTX = 4096`.
///
/// Behavior reference: project-maya serve/test_server.py:27 at 7e68a30f.
pub const CTX: u32 = 4096;

/// The answer most donor HTTP tests script: `"</think>\n\nhello"` (with the byte
/// tokenizer, `</think>` is plain bytes).
///
/// Behavior reference: project-maya serve/test_server.py:1676, 2045, 2367 at 7e68a30f.
pub const HELLO: &str = "</think>\n\nhello";

/// The answer of the donor's `Http` logprobs tests: `"abc</think>Hello"`.
///
/// Behavior reference: project-maya serve/test_logprobs.py:165 at 7e68a30f.
pub const LP_ANSWER: &str = "abc</think>Hello";

/// The ids the donor's `MockEngine` replays for `text`: the text encoded with special
/// literals parsed, then the end-of-turn literal `<|im_end|>` encoded the same way.
///
/// Behavior reference: project-maya serve/server.py:209-211 at 7e68a30f.
pub fn script_ids(tok: &ByteTokenizer, text: &str) -> Vec<u32> {
    let mut ids = tok.encode(text, true, &[]);
    ids.push(EOS_ID);
    ids
}

/// One script for `text` with the byte tokenizer, reporting a context of `max_context`.
pub fn script(text: &str, max_context: u32) -> FakeScript {
    FakeScript::new(script_ids(&ByteTokenizer::new(), text)).max_context(max_context)
}

/// Several scripts (each request takes the next, the last one repeats), as the donor's
/// `MockEngine(tok, [a, b, ...])`.
pub fn rotating(texts: &[&str], max_context: u32) -> FakeScript {
    let tok = ByteTokenizer::new();
    FakeScript::rotating(texts.iter().map(|t| script_ids(&tok, t)).collect())
        .max_context(max_context)
}

/// The donor's `RecordingEngine(tok, text, max_context=CTX)`: the scripted engine, which
/// keeps the latest request (read it through [`FakeFactory::probe`]).
pub fn recording(text: &str) -> Result<RecordingEngine, FakeConfigError> {
    script(text, CTX).build()
}

/// The `GoneClients` engine: `HeldEngine(tok, text, max_context=CTX)`, whose first
/// generation waits until released.
pub fn held(text: &str) -> Result<HeldEngine, FakeConfigError> {
    HeldEngine::new(script(text, CTX))
}

/// `ClockedEngine(tok, text, max_context=CTX)`: engine figures as the line-protocol
/// engine's `DONE` line gives them.
pub fn clocked(text: &str) -> Result<ClockedEngine, FakeConfigError> {
    ClockedEngine::new(script(text, CTX))
}

/// `LpEngine(tok, text, max_context=CTX)`: made-up logprobs for every token.
pub fn lp(text: &str) -> Result<LpEngine, FakeConfigError> {
    LpEngine::new(script(text, CTX))
}

/// `DyingEngine(tok, text, max_context=CTX)`: dies after five tokens of its first answer.
pub fn dying(text: &str) -> Result<DyingEngine, FakeConfigError> {
    DyingEngine::new(script(text, CTX))
}

/// `ErrEngine`: answers each generation with an `ERR` line.
pub fn err(text: &str) -> Result<ErrEngine, FakeConfigError> {
    ErrEngine::new(script(text, CTX))
}

/// A factory as the server takes it.
pub fn shared<F: EngineFactory + 'static>(factory: F) -> Arc<dyn EngineFactory> {
    Arc::new(factory)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn scripts_end_with_the_end_of_turn_id() {
        let tok = ByteTokenizer::new();
        assert_eq!(script_ids(&tok, "hi"), vec![104, 105, EOS_ID]);
        // `</think>` is plain bytes for the byte tokenizer; `<|im_end|>` is a special.
        let ids = script_ids(&tok, HELLO);
        assert_eq!(ids.len(), HELLO.len() + 1);
        assert_eq!(script_ids(&tok, "<|im_end|>"), vec![EOS_ID, EOS_ID]);
        assert_eq!(CTX, 4096);
    }

    #[test]
    fn every_constructor_builds_a_synthetic_engine() {
        use console_core::engine::{require_synthetic, EngineStartConfig};
        let factories: Vec<Arc<dyn EngineFactory>> = vec![
            shared(recording(HELLO).expect("valid script")),
            shared(held(HELLO).expect("valid script")),
            shared(clocked(HELLO).expect("valid script")),
            shared(lp(LP_ANSWER).expect("valid script")),
            shared(dying(HELLO).expect("valid script")),
            shared(err(HELLO).expect("valid script")),
            shared(rotating(&["a", "b"], CTX).build().expect("valid script")),
        ];
        for f in factories {
            let engine = f.start(&EngineStartConfig::new()).expect("starts");
            assert!(require_synthetic(engine.descriptor()).is_ok());
            assert_eq!(engine.descriptor().max_context, CTX);
        }
    }
}
