//! Provenance: translated from project-maya serve/test_server.py::RecordingEngine, serve/test_server.py::RecordingPrompt, serve/test_server.py::ThinkingBudget (Sampled) and serve/test_ds4_restore_points.py::Recording at 7e68a30f (MIT); license text in console/LICENSES/project-maya-MIT.txt.
//!
//! The donor's recording subclasses of `MockEngine` each keep one part of the latest
//! request. The scripted engine keeps the whole request already, so each of them is the
//! scripted engine itself, read through [`FakeProbe`](crate::fake::FakeProbe).

use crate::fake::FakeFactory;

/// Rust counterpart of the donor's `RecordingEngine` (serve/test_server.py:32): the
/// scripted engine that keeps the latest `max_new`. Read it as
/// `probe.last_request().map(|r| r.max_new)`.
pub type RecordingEngine = FakeFactory;

/// Rust counterpart of the donor's `RecordingPrompt` (serve/test_server.py:906): the
/// scripted engine that keeps the latest prompt ids. Read them with
/// [`FakeProbe::last_prompt`](crate::fake::FakeProbe::last_prompt).
pub type RecordingPrompt = FakeFactory;

/// Rust counterpart of the donor's `Recording` (serve/test_ds4_restore_points.py:48): the
/// scripted engine that keeps the latest sampling, restore points included. Read it as
/// `probe.last_request().map(|r| (r.sampling, r.restore))`.
pub type Recording = FakeFactory;

/// Rust counterpart of the donor's `Sampled` (serve/test_server.py:68, a
/// `RecordingEngine` that keeps the latest sampling and thinking keys). Read them as
/// `probe.last_request().map(|r| (r.sampling, r.thinking))`.
pub type Sampled = FakeFactory;

#[cfg(test)]
mod tests {
    use std::sync::Arc;

    use console_core::engine::{
        generate_ledgered, ControlHandle, EngineDescriptor, EngineEvent, EngineInstance,
        EngineStartConfig, EventSink, GenerationRequest, RequestId, RestoreHints, ThinkingHints,
    };

    use super::*;
    use crate::fake::FakeScript;

    struct Null;
    impl EventSink for Null {
        fn deliver(
            &mut self,
            _e: EngineEvent,
        ) -> Result<(), console_core::engine::DeliveryRefused> {
            Ok(())
        }
    }

    fn assert_descriptor(d: &EngineDescriptor) {
        assert!(console_core::engine::require_synthetic(d).is_ok());
    }

    #[test]
    fn fake_recording_doubles_keep_the_whole_request() {
        let f: RecordingEngine = FakeScript::new(vec![1, 2, 3]).build().expect("valid");
        let probe = f.probe();
        let mut e = f.start_engine(&EngineStartConfig::new()).expect("starts");
        assert_descriptor(e.descriptor());
        let mut req = GenerationRequest::new(RequestId(1), vec![9, 8, 7], 2);
        req.sampling.temperature = Some(0.7);
        req.thinking = Some(ThinkingHints {
            budget: 64,
            end_id: 5,
            soft: None,
        });
        req.restore = Some(RestoreHints {
            marks: vec![2],
            tail: Some(3),
            shared: None,
        });
        let h = ControlHandle::new();
        generate_ledgered(&mut e, &req, &h.probe(), &mut Null).expect("runs");
        let last = probe.last_request().expect("recorded");
        assert_eq!(last.max_new, 2, "RecordingEngine.last_max_new");
        assert_eq!(
            probe.last_prompt(),
            Some(vec![9, 8, 7]),
            "RecordingPrompt.last_ids"
        );
        assert_eq!(
            last.sampling.temperature,
            Some(0.7),
            "Recording.last_sampling"
        );
        assert_eq!(
            last.thinking.map(|t| t.budget),
            Some(64),
            "Sampled.last_sampling"
        );
        assert_eq!(last.restore.map(|r| r.marks), Some(vec![2]));
        assert_eq!(probe.last_embeddings(), None);
        assert!(
            Arc::ptr_eq(&last.prompt, &req.prompt),
            "the prompt is shared, not copied"
        );
    }
}
