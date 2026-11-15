//! Provenance: translated from project-maya serve/test_server.py::NonFiniteRetry, serve/test_server.py::TimingsDrafts::test_draft_fields and serve/test_server.py::TestCarryEmbeddings::test_the_job_thread_sees_the_request_threads_image_file at 7e68a30f (MIT); license text in console/LICENSES/project-maya-MIT.txt.
//!
//! ENG-10: the donor test methods the turn driver re-expresses whole. The donor drives
//! `Service.run` with its test engines and reads the events, the done record and the
//! error; here the turn driver runs ENG-02's counterparts of those engines on its driver
//! thread, and the consumer does the stop detection the donor's `run` does (the byte
//! tokenizer's `<|im_end|>` ends the answer).

#[path = "eng10_helpers.rs"]
mod helpers;

use std::path::PathBuf;
use std::sync::Arc;

use console_core::engine::{EmbeddingsKind, EmbeddingsRef, FailureKind};
use console_core::turn::{request_timings, SegmentFigures, TurnEnd};
use console_engine::fake::doubles::{BrokenEngine, NonFiniteEngine};
use console_engine::fake::{FakeFactory, FakeScript};

use helpers::{answer, driver, enc, read_turn, request, CTX, END};

const SCRIPT: &str = "all good, and then some";

/// The donor's `NonFiniteRetry.answer`: (text, finish, error, engine calls).
async fn non_finite(fail: Vec<Option<u32>>) -> (String, &'static str, Option<String>, u64) {
    let eng = NonFiniteEngine::new(FakeScript::new(answer(SCRIPT)).max_context(CTX), fail)
        .unwrap_or_else(|e| panic!("{e}"));
    let (d, _, _) = driver(Arc::new(eng.clone())).await;
    let read = read_turn(d.turn(request(&enc("hi"), 200)), &[END]).await;
    let err = read.outcome.error().map(|e| e.message());
    (read.text(), read.outcome.finish, err, eng.calls())
}

// Donor: serve/test_server.py::NonFiniteRetry::test_retried_before_the_answer
#[tokio::test(start_paused = true)]
async fn non_finite_retry_retried_before_the_answer() {
    assert_eq!(
        non_finite(vec![Some(0)]).await,
        (SCRIPT.to_owned(), "stop", None, 2)
    );
}

// Donor: serve/test_server.py::NonFiniteRetry::test_answer_under_way_ends_as_length
#[tokio::test(start_paused = true)]
async fn non_finite_retry_answer_under_way_ends_as_length() {
    assert_eq!(
        non_finite(vec![Some(8)]).await,
        ("all good".to_owned(), "length", None, 1)
    );
}

// Donor: serve/test_server.py::NonFiniteRetry::test_twice_is_an_error
#[tokio::test(start_paused = true)]
async fn non_finite_retry_twice_is_an_error() {
    let (out, finish, err, calls) = non_finite(vec![Some(0), Some(0)]).await;
    let err = err.unwrap_or_default();
    assert!(err.contains("non-finite"), "{err}");
    assert_eq!(calls, 2);
    assert_eq!((out.as_str(), finish), ("", "error"));
}

// Donor: serve/test_server.py::NonFiniteRetry::test_other_errors_are_not_retried
#[tokio::test(start_paused = true)]
async fn non_finite_retry_other_errors_are_not_retried() {
    let eng = BrokenEngine::new(FakeScript::new(enc("x")).max_context(CTX))
        .unwrap_or_else(|e| panic!("{e}"));
    let (d, _, _) = driver(Arc::new(eng.clone())).await;
    let read = read_turn(d.turn(request(&enc("hi"), 20)), &[END]).await;
    let err = read.outcome.error().map(|e| e.message());
    assert_eq!(err.as_deref(), Some("verify: layer 31 never rang"));
    assert!(matches!(read.outcome.end, TurnEnd::Failed(_)));
    // The donor's `assertRaises(ValueError)`: the engine's own ERR, not a death or a
    // protocol failure.
    assert_eq!(
        read.outcome
            .error()
            .and_then(|e| e.engine_failure())
            .map(|f| f.kind),
        Some(FailureKind::Reported)
    );
    assert_eq!(read.outcome.finish, "error");
    assert_eq!(eng.calls(), 1);
}

// Donor: serve/test_server.py::TimingsDrafts::test_draft_fields
#[test]
fn timings_drafts_draft_fields() {
    let base = SegmentFigures {
        prompt_ms: Some(100.0),
        decode_ms: Some(200.0),
        generated: Some(20),
        reused: Some(4),
        ..SegmentFigures::default()
    };
    let with = SegmentFigures {
        drafts_offered: Some(15),
        drafts_accepted: Some(11),
        ..base
    };
    let t = request_timings(24, 20, &with).unwrap_or_else(|| panic!("timings"));
    assert_eq!(t.drafts, Some((15, 11)));
    assert_eq!((t.prompt_n, t.cache_n), (20, 4));
    let t = request_timings(24, 20, &base).unwrap_or_else(|| panic!("timings"));
    assert_eq!(t.drafts, None);
    assert_eq!(request_timings(24, 20, &SegmentFigures::default()), None);
}

// Donor: serve/test_server.py::TestCarryEmbeddings::test_the_job_thread_sees_the_request_threads_image_file
#[tokio::test(start_paused = true)]
async fn carry_embeddings_the_job_thread_sees_the_request_threads_image_file() {
    // The donor's thread-local is replaced by the request itself: the picture data set
    // while the prompt is prepared travels in the turn's request, so the engine call sees
    // it whichever task or thread reads the answer (a strata_resume job).
    let factory = FakeFactory::new(FakeScript::new(answer("chunk")).max_context(CTX))
        .unwrap_or_else(|e| panic!("{e}"));
    let probe = factory.probe();
    let (d, _, _) = driver(Arc::new(factory)).await;
    let mut req = request(&enc("hi"), 20);
    let file = EmbeddingsRef {
        path: PathBuf::from("req-1.sve"),
        kind: EmbeddingsKind::Embeddings,
    };
    req.generation.embeddings = Some(file.clone());
    let stream = d.turn(req);
    let job = tokio::spawn(async move { read_turn(stream, &[END]).await });
    let read = job.await.unwrap_or_else(|e| panic!("{e}"));
    assert_eq!(read.text(), "chunk");
    assert_eq!(probe.last_embeddings(), Some(file));
}
