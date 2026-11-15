//! Provenance: translated from project-maya serve/test_server.py::MaxTokens, serve/test_server.py::FitMaxTokens, serve/test_server.py::EngineDeath, serve/test_server.py::UsageAndStatus, serve/test_server.py::PromptProgressStream and serve/test_server.py::NoRoomOrNoToken (their driver halves) at 7e68a30f (MIT); license text in console/LICENSES/project-maya-MIT.txt.
//!
//! ENG-10: the turn driver on tokio's paused clock with ENG-02's synthetic engines.
//!
//! Driver halves of the donor's MaxTokens, FitMaxTokens, EngineDeath, PromptProgressStream,
//! UsageAndStatus and NoRoomOrNoToken tests (their HTTP halves, the status codes and the
//! bodies of both dialects, belong to API-07 and API-08, which own those ledger rows),
//! and the driver's own rules: a dropped consumer still gives STOP, the drain and the
//! release of the place in that order; keep-alives; cancel; a stopping server; an id
//! outside the vocabulary; continuations; and the observer's hooks.
//!
//! Behavior reference: project-maya serve/server.py:1150-1170, 1451-1500, 2632-2661,
//! 3680-3694, 4097-4126, 4256-4271, 4340-4378, 4433-4465, 4491-4496, 4507-4518, 4657-4793
//! at 7e68a30f.

#[path = "eng10_helpers.rs"]
mod helpers;

use std::sync::atomic::{AtomicU32, Ordering};
use std::sync::{Arc, Mutex, PoisonError};
use std::time::Duration;

use console_core::engine::{
    CommittedToken, ControlProbe, DeliveryRefused, EngineDescriptor, EngineEvent, EngineFactory,
    EngineFailure, EngineInstance, EngineKind, EngineStartConfig, EngineStop, EventSink,
    FailureKind, GenerationRequest, Health, PromptProgress, Provenance, ShutdownOutcome, Terminal,
};
use console_core::fifo::{EngineFifo, Units};
use console_core::request::pynum::PyInt;
use console_core::request::CTX_SLACK;
use console_core::turn::{
    CallSummary, CallerFinish, Continuation, ContinuationPolicy, PingProgress, TurnEnd, TurnError,
    TurnItem, TurnSettings, ENGINE_PANICKED, STOPPING_MESSAGE,
};
use console_engine::fake::doubles::{
    ClockedEngine, DyingEngine, HeldEngine, NonFiniteEngine, PacedEngine, CLOCKED_REUSED,
    NON_FINITE_MESSAGE,
};
use console_engine::fake::{FakeFactory, FakeScript};
use tokio::time::Instant;

use helpers::{
    answer, driver, driver_with, enc, quiet_settings, read_turn, request, until, Seen, CTX, END,
    VOCAB,
};

/// The donor's 2,000-letter answer: longer than the old 1,024 fallback, and no loop.
fn long_answer() -> Vec<u32> {
    let mut x: u64 = 2000;
    let text: String = (0..2000)
        .map(|_| {
            x = x
                .wrapping_mul(6_364_136_223_846_793_005)
                .wrapping_add(1_442_695_040_888_963_407);
            let k = u8::try_from((x >> 33) % 26).unwrap_or(0);
            char::from(b'a' + k)
        })
        .collect();
    let mut ids = enc("</think>\n\n");
    ids.extend(answer(&text));
    ids
}

fn fake(script: Vec<u32>) -> FakeFactory {
    FakeFactory::new(FakeScript::new(script).max_context(CTX)).unwrap_or_else(|e| panic!("{e}"))
}

fn n(v: i64) -> PyInt {
    PyInt::from_i64(v)
}

// ----------------------------------------------------------------- the context rule

#[tokio::test(start_paused = true)]
async fn unset_budget_is_the_rest_of_the_context() {
    let factory = fake(long_answer());
    let probe = factory.probe();
    let (d, _, _) = driver(Arc::new(factory)).await;
    let prompt = enc("<|im_start|>user\nhi<|im_end|>\n<|im_start|>assistant\n");
    for budget in [None, Some(n(0)), Some(n(-1))] {
        let max_new = d
            .context_budget(prompt.len(), budget.as_ref())
            .unwrap_or_else(|e| panic!("{e}"));
        let read = read_turn(d.turn(request(&prompt, max_new)), &[END]).await;
        let pt = i64::try_from(prompt.len()).unwrap_or(0);
        let seen = probe.last_request().map(|r| i64::from(r.max_new));
        assert_eq!(seen, Some(i64::from(CTX) - CTX_SLACK - pt));
        assert!(read.outcome.completion_tokens > 1024);
        assert_eq!(read.outcome.prompt_tokens, u32::try_from(pt).unwrap_or(0));
    }
}

#[tokio::test(start_paused = true)]
async fn explicit_budget_is_honoured() {
    let factory = fake(long_answer());
    let probe = factory.probe();
    let (d, _, _) = driver(Arc::new(factory)).await;
    let prompt = enc("hi");
    for want in [50, 1500] {
        let max_new = d
            .context_budget(prompt.len(), Some(&n(want)))
            .unwrap_or_else(|e| panic!("{e}"));
        let read = read_turn(d.turn(request(&prompt, max_new)), &[END]).await;
        assert_eq!(
            probe.last_request().map(|r| i64::from(r.max_new)),
            Some(want)
        );
        assert_eq!(i64::from(read.outcome.completion_tokens), want);
        assert_eq!(read.outcome.end, TurnEnd::Ended(EngineStop::Length));
        assert_eq!(read.outcome.finish, "length");
    }
}

#[tokio::test(start_paused = true)]
async fn budgets_over_the_context_are_refused_and_no_room_is_refused() {
    let (d, _, _) = driver(Arc::new(fake(long_answer()))).await;
    let ctx = i64::from(CTX);
    let err = d.context_budget(2, Some(&n(ctx))).unwrap_err();
    assert_eq!(err.code(), Some("context_length_exceeded"));
    let msg = err.message();
    assert!(msg.contains("exceeds the context"), "{msg}");
    assert!(msg.contains(&format!("maximum context length is {CTX} tokens")));
    assert!(msg.contains(&format!("max tokens ({CTX})")));
    // A few tokens left: the budget is exactly those; none left: refused.
    let room5 = usize::try_from(ctx - CTX_SLACK - 5).unwrap_or(0);
    assert_eq!(d.context_budget(room5, Some(&n(-1))), Ok(5));
    let full = usize::try_from(ctx - CTX_SLACK).unwrap_or(0);
    let err = d.context_budget(full, None).unwrap_err();
    assert!(err.message().contains("no room to answer"));
    assert_eq!(err.code(), Some("context_length_exceeded"));
}

#[tokio::test(start_paused = true)]
async fn fit_max_tokens_clamps_an_overshoot() {
    let factory = fake(long_answer());
    let probe = factory.probe();
    let settings = TurnSettings {
        fit_max_tokens: true,
        ..quiet_settings()
    };
    let (d, _, _) = driver_with(Arc::new(factory), settings).await;
    let prompt = enc("hi");
    let max_new = d
        .context_budget(prompt.len(), Some(&n(i64::from(CTX))))
        .unwrap_or_else(|e| panic!("{e}"));
    let _ = read_turn(d.turn(request(&prompt, max_new)), &[END]).await;
    let want = i64::from(CTX) - CTX_SLACK - 2;
    assert_eq!(
        probe.last_request().map(|r| i64::from(r.max_new)),
        Some(want)
    );
    assert_eq!(d.context_budget(2, Some(&n(50))), Ok(50));
    let full = usize::try_from(i64::from(CTX) - CTX_SLACK).unwrap_or(0);
    let err = d.context_budget(full, Some(&n(100))).unwrap_err();
    assert!(err.message().contains("no room to answer"));
}

#[tokio::test(start_paused = true)]
async fn an_engine_that_is_not_ready_is_starting() {
    let factory = fake(answer("ok"));
    let probe = factory.probe();
    let (d, rec, _) = driver(Arc::new(factory)).await;
    probe.set_max_context(Some(0));
    let read = read_turn(d.turn(request(&enc("hi"), 5)), &[END]).await;
    assert_eq!(read.outcome.end, TurnEnd::Failed(TurnError::Starting));
    assert_eq!(probe.generations(), 0, "nothing was sent to the engine");
    assert_eq!(d.max_context(), 0);
    assert_eq!(d.context_budget(2, None), Err(TurnError::Starting));
    assert_eq!(rec.records()[0].finish, "error");
}

// ------------------------------------------------------------------ engine death

#[tokio::test(start_paused = true)]
async fn a_dead_engine_is_an_error_and_the_next_turn_restarts_it() {
    let engine = DyingEngine::new(FakeScript::new(long_answer()).max_context(CTX))
        .unwrap_or_else(|e| panic!("{e}"));
    let (d, rec, cap) = driver(Arc::new(engine.clone())).await;
    let read = read_turn(d.turn(request(&enc("hi"), 50)), &[END]).await;
    assert_eq!(read.tokens.len(), 5);
    let err = read.outcome.error().unwrap_or_else(|| panic!("no error"));
    let f = err
        .engine_failure()
        .unwrap_or_else(|| panic!("not an engine failure"));
    assert_eq!(f.kind, FailureKind::Died);
    assert!(f.message.as_str().contains("stopped unexpectedly"));
    assert_eq!(read.outcome.finish, "error");
    assert_eq!(rec.records()[0].finish, "error");
    assert!(cap.lines().contains(
        &"[console] the engine stopped unexpectedly (exit code -9).  The next request starts \
          the engine again."
            .to_owned()
    ));
    let read = read_turn(d.turn(request(&enc("hi"), 50)), &[END]).await;
    assert_eq!(engine.restarts(), 1);
    assert_eq!(read.outcome.completion_tokens, 50);
    let lines = cap.lines();
    assert!(lines.contains(
        &"[console] the engine had stopped (exit code -9); starting it again (a minute or two) ..."
            .to_owned()
    ));
    assert!(lines.contains(&"[console] the engine is running again".to_owned()));
}

// --------------------------------------------------------- figures and progress

#[tokio::test(start_paused = true)]
async fn usage_and_timings_come_from_the_engine_clock() {
    let engine = ClockedEngine::new(FakeScript::new(answer("</think>\n\nok")).max_context(CTX))
        .unwrap_or_else(|e| panic!("{e}"));
    let (d, rec, _) = driver(Arc::new(engine)).await;
    let prompt = enc("<|im_start|>user\nhi<|im_end|>\n");
    let read = read_turn(d.turn(request(&prompt, 20)), &[END]).await;
    let o = &read.outcome;
    let t = o.timings.unwrap_or_else(|| panic!("no timings"));
    assert_eq!(o.cached_tokens(), CLOCKED_REUSED);
    assert_eq!(t.cache_n, CLOCKED_REUSED);
    assert_eq!(t.prompt_n + t.cache_n, o.prompt_tokens);
    assert_eq!(t.predicted_n, o.completion_tokens);
    let want = f64::from(t.prompt_n) / 0.040;
    assert!((t.prompt_per_second.unwrap_or(0.0) - want).abs() <= 0.1);
    assert_eq!(t.predicted_per_second, Some(50.0)); // 20 ms a token
    let figures = o.figures.unwrap_or_else(|| panic!("no figures"));
    assert_eq!((figures.hits, figures.lookups), (Some(9), Some(10)));
    let r = &rec.records()[0];
    assert_eq!(
        (r.finish, r.output_tokens, r.timings),
        ("stop", o.completion_tokens, o.timings)
    );
}

#[tokio::test(start_paused = true)]
async fn an_engine_without_a_clock_has_no_timings_and_nothing_cached() {
    let (d, _, cap) = driver(Arc::new(fake(answer("</think>\n\nok")))).await;
    let read = read_turn(d.turn(request(&enc("hi"), 5)), &[END]).await;
    assert_eq!(read.outcome.timings, None);
    assert_eq!(read.outcome.figures, None);
    assert_eq!(read.outcome.cached_tokens(), 0);
    assert_eq!(read.outcome.completion_tokens, 5);
    // The done line, on the paused clock: no time passed, so no rate.
    assert!(cap.lines().contains(
        &"[console] done: 5 tokens in 0 s (0.0 tok/s) (length, cancel=False)".to_owned()
    ));
}

#[tokio::test(start_paused = true)]
async fn prompt_progress_becomes_pings_with_its_payload() {
    let engine = PacedEngine::new(FakeScript::new(answer("hello")).max_context(CTX))
        .unwrap_or_else(|e| panic!("{e}"));
    let (d, _, _) = driver(Arc::new(engine)).await;
    let read = read_turn(d.turn(request(&enc("hi"), 20)), &[END]).await;
    assert_eq!(
        read.pings,
        vec![
            Some(PingProgress {
                total: 8192,
                cache: 2048,
                processed: 4096,
                time_ms: 251
            }),
            Some(PingProgress {
                total: 8192,
                cache: 2048,
                processed: 8192,
                time_ms: 500
            }),
        ]
    );
    assert_eq!(read.text(), "hello");
    // The scripted engine reports no progress: no payload at all.
    let (d, _, _) = driver(Arc::new(fake(answer("hello")))).await;
    assert!(read_turn(d.turn(request(&enc("hi"), 20)), &[END])
        .await
        .pings
        .is_empty());
}

#[tokio::test(start_paused = true)]
async fn a_progress_time_round_refuses_ends_the_turn_as_the_donor_does() {
    // (ms, the class Python's `round` raises, the finish, the donor's `except ValueError`
    // line written)
    for (ms, class, finish, logged) in [
        (f64::NAN, "ValueError", "error", true),
        (f64::INFINITY, "OverflowError", "length", false),
    ] {
        let progress = PromptProgress {
            read: 1,
            total: 2,
            reused: 0,
            ms,
            tok_s: None,
        };
        let engine = PacedEngine::with_progress(
            FakeScript::new(answer("ok")).max_context(CTX),
            vec![progress],
        )
        .unwrap_or_else(|e| panic!("{e}"));
        let (d, _, cap) = driver(Arc::new(engine)).await;
        let read = read_turn(d.turn(request(&enc("hi"), 20)), &[END]).await;
        let err = read
            .outcome
            .error()
            .unwrap_or_else(|| panic!("no error at {ms}"));
        assert!(matches!(err, TurnError::Request(e) if e.python_type() == class));
        assert_eq!(read.outcome.finish, finish);
        let line = format!("[console] the engine reported an error: {}", err.message());
        assert_eq!(cap.lines().contains(&line), logged, "{:?}", cap.lines());
        assert_eq!(d.fifo().used(), 0);
    }
}

#[tokio::test(start_paused = true)]
async fn a_quiet_engine_gets_heartbeat_pings() {
    let engine = HeldEngine::new(FakeScript::new(answer("late")).max_context(CTX))
        .unwrap_or_else(|e| panic!("{e}"));
    let settings = TurnSettings {
        heartbeat: Some(Duration::from_secs(10)),
        queue_ping: None,
        ..TurnSettings::default()
    };
    let (d, _, _) = driver_with(Arc::new(engine.clone()), settings).await;
    let t0 = Instant::now();
    let mut stream = d.turn(request(&enc("hi"), 20));
    match stream.next().await {
        Some(TurnItem::Ping(None)) => {}
        other => panic!("expected a keep-alive, got {other:?}"),
    }
    assert!(t0.elapsed() >= Duration::from_secs(10));
    // The keep-alive came from the call's wait, so the call was sent: the engine holds it.
    assert!(engine.wait_held(Duration::from_secs(30)));
    engine.release();
    let mut text = Vec::new();
    loop {
        match stream.next().await {
            Some(TurnItem::Token(t)) if t.id == END => stream.finish(CallerFinish::Stop),
            Some(TurnItem::Token(t)) => text.push(t.id),
            Some(TurnItem::Ping(_)) => {}
            Some(TurnItem::Done(o)) => {
                assert_eq!(o.finish, "stop");
                break;
            }
            None => panic!("no Done"),
        }
    }
    assert_eq!(helpers::dec(&text), "late");
}

// ------------------------------------------------- the consumer, cancel, stopping

/// A recording engine: it writes tokens until it reads the cancel, and records, with the
/// FIFO's places in use, when it saw the cancel (STOP) and when its call returned (the
/// drain). The observer records when the turn gave its place back.
#[derive(Clone, Default)]
struct Recording {
    /// The driver's FIFO and the observer's list, linked once the driver runs.
    link: Arc<Mutex<Option<(EngineFifo, Seen)>>>,
}

impl Recording {
    fn record(&self, what: &str) {
        let link = self.link.lock().unwrap_or_else(PoisonError::into_inner);
        if let Some((fifo, seen)) = link.as_ref() {
            seen.push(format!("{what} used={}", fifo.used()));
        }
    }
}

struct RecordingInstance {
    desc: EngineDescriptor,
    rec: Recording,
}

impl EngineFactory for Recording {
    fn kind(&self) -> EngineKind {
        EngineKind::Scripted
    }

    fn start(&self, _cfg: &EngineStartConfig) -> Result<Box<dyn EngineInstance>, EngineFailure> {
        let mut desc = EngineDescriptor::new(EngineKind::Scripted, Provenance::Synthetic);
        desc.max_context = 1 << 20;
        Ok(Box::new(RecordingInstance {
            desc,
            rec: self.clone(),
        }))
    }
}

impl EngineInstance for RecordingInstance {
    fn descriptor(&self) -> &EngineDescriptor {
        &self.desc
    }

    fn generate(
        &mut self,
        req: &GenerationRequest,
        control: &ControlProbe,
        sink: &mut dyn EventSink,
    ) -> Result<Terminal, EngineFailure> {
        let prompt_tokens = u32::try_from(req.prompt.len()).unwrap_or(u32::MAX);
        let _ = sink.deliver(EngineEvent::Admitted {
            prompt_tokens,
            reused_tokens: None,
        });
        for index in 0..req.max_new {
            if control.is_cancelled() {
                // The in-process engine's STOP: it reads the cancel between steps.
                self.rec.record("stop");
                // The drain: the call returns now, and the driver thread replies after it.
                self.rec.record("drain");
                return Ok(Terminal::bare(EngineStop::Cancelled));
            }
            let t = CommittedToken {
                index,
                position: u64::from(prompt_tokens) + u64::from(index),
                id: 97 + index % 26,
                logprob: None,
            };
            match sink.deliver(EngineEvent::Token(t)) {
                Ok(()) | Err(DeliveryRefused::ConsumerGone) => {}
                Err(DeliveryRefused::Backpressure) => {}
            }
        }
        self.rec.record("drain");
        Ok(Terminal::bare(EngineStop::Length))
    }

    fn shutdown(self: Box<Self>, _deadline: std::time::Instant) -> ShutdownOutcome {
        ShutdownOutcome::Graceful
    }
}

#[tokio::test(start_paused = true)]
async fn a_dropped_consumer_still_gives_stop_then_drain_then_release() {
    let rec = Recording::default();
    let settings = TurnSettings {
        channel_capacity: 1,
        ..quiet_settings()
    };
    let (d, observer, _) = driver_with(Arc::new(rec.clone()), settings).await;
    // The engine's records go to the observer's list, where "release" goes.
    let order = observer.seen.clone();
    *rec.link.lock().unwrap_or_else(PoisonError::into_inner) =
        Some((d.fifo().clone(), order.clone()));
    let mut stream = d.turn(request(&enc("hi"), 1_000_000));
    for _ in 0..3 {
        match stream.next().await {
            Some(TurnItem::Token(_)) => {}
            other => panic!("expected a token, got {other:?}"),
        }
    }
    assert_eq!(d.fifo().used(), 1);
    let released = observer.released.notified();
    drop(stream);
    released.await;
    let seen: Vec<String> = order
        .list()
        .into_iter()
        .filter(|s| s.starts_with("stop") || s.starts_with("drain") || s == "release")
        .collect();
    assert_eq!(seen, ["stop used=1", "drain used=1", "release"]);
    assert_eq!(d.fifo().used(), 0);
    until(|| observer.records().len() == 1).await;
    let r = &observer.records()[0];
    assert_eq!(
        (r.finish, r.output_tokens, r.cancelled),
        ("disconnect", 3, true)
    );
    // The engine serves the next turn.
    let mut next = d.turn(request(&enc("hi"), 4));
    let mut got = 0;
    while let Some(item) = next.next().await {
        if let TurnItem::Token(_) = item {
            got += 1;
        }
    }
    assert_eq!(got, 4);
}

#[tokio::test(start_paused = true)]
async fn finishing_early_stops_the_engine_and_counts_what_was_taken() {
    let factory = fake(long_answer());
    let (d, rec, _) = driver(Arc::new(factory)).await;
    let mut stream = d.turn(request(&enc("hi"), 1000));
    let mut taken = 0;
    loop {
        match stream.next().await {
            Some(TurnItem::Token(_)) => {
                taken += 1;
                if taken == 7 {
                    stream.finish(CallerFinish::Stop);
                }
            }
            Some(TurnItem::Done(o)) => {
                assert_eq!(o.completion_tokens, 7);
                assert_eq!(o.finish, "stop");
                assert!(!o.cancelled);
                break;
            }
            Some(TurnItem::Ping(_)) => {}
            None => panic!("no Done"),
        }
    }
    assert_eq!(taken, 7);
    assert_eq!(rec.records()[0].output_tokens, 7);
    assert_eq!(d.fifo().used(), 0);
}

#[tokio::test(start_paused = true)]
async fn a_cancel_while_queued_leaves_the_line_and_never_reaches_the_engine() {
    let factory = fake(answer("ok"));
    let probe = factory.probe();
    let settings = TurnSettings {
        queue_ping: Some(Duration::from_millis(100)),
        ..quiet_settings()
    };
    let (d, rec, _) = driver_with(Arc::new(factory), settings).await;
    let held = d.fifo().acquire(Units::All).await;
    let mut stream = d.turn(request(&enc("hi"), 5));
    for _ in 0..2 {
        assert_eq!(stream.next().await, Some(TurnItem::Ping(None)));
    }
    stream.cancel();
    match stream.next().await {
        Some(TurnItem::Done(o)) => {
            assert_eq!(o.end, TurnEnd::CancelledBeforeEngine);
            assert_eq!((o.finish, o.completion_tokens), ("cancel", 0));
        }
        other => panic!("expected Done, got {other:?}"),
    }
    assert_eq!(d.fifo().waiting(), 0);
    drop(held);
    assert_eq!(probe.generations(), 0);
    assert!(
        rec.records().is_empty(),
        "a turn that never ran has no history row"
    );
    assert_eq!(rec.seen.list(), ["queued", "dequeued"]);
}

#[tokio::test(start_paused = true)]
async fn a_stopping_server_refuses_the_turn() {
    let factory = fake(answer("ok"));
    let probe = factory.probe();
    let (d, rec, _) = driver(Arc::new(factory)).await;
    d.set_stopping(true);
    let read = read_turn(d.turn(request(&enc("hi"), 5)), &[END]).await;
    let err = read.outcome.error().unwrap_or_else(|| panic!("no error"));
    assert_eq!(err.message(), STOPPING_MESSAGE);
    assert!(matches!(err, TurnError::Request(e) if e.python_type() == "ValueError"));
    assert_eq!(probe.generations(), 0);
    assert!(rec.records().is_empty());
    d.set_stopping(false);
    assert_eq!(
        read_turn(d.turn(request(&enc("hi"), 5)), &[END])
            .await
            .text(),
        "ok"
    );
}

#[tokio::test(start_paused = true)]
async fn an_id_outside_the_vocabulary_ends_the_turn_as_the_tokenizer_does() {
    let factory = fake(vec![104, 300, 105, END]);
    let (d, rec, _) = driver(Arc::new(factory)).await;
    let mut req = request(&enc("hi"), 20);
    req.vocab_size = Some(VOCAB);
    let read = read_turn(d.turn(req), &[END]).await;
    assert_eq!(read.text(), "h");
    let err = read.outcome.error().unwrap_or_else(|| panic!("no error"));
    assert_eq!(
        err.message(),
        "token id 300 is outside the vocabulary (262)"
    );
    assert!(matches!(err, TurnError::Request(e) if e.python_type() == "IndexError"));
    // The donor's `run` does not catch the IndexError: its finish stays `length`.
    assert_eq!(read.outcome.finish, "length");
    assert_eq!(rec.records()[0].finish, "length");
    // The donor counts the refused token (`n += 1` before its tokenizer raises).
    assert_eq!(read.outcome.completion_tokens, 2);
    assert_eq!(rec.records()[0].output_tokens, 2);
    assert_eq!(d.fifo().used(), 0);
}

#[tokio::test(start_paused = true)]
async fn an_id_outside_the_vocabulary_after_the_stop_is_never_reached() {
    let factory = fake(vec![104, END, 300]);
    let (d, rec, _) = driver(Arc::new(factory)).await;
    let mut req = request(&enc("hi"), 20);
    req.vocab_size = Some(VOCAB);
    let released = rec.released.notified();
    let stream = d.turn(req);
    // The turn's task runs to its end, past the stop id, before the consumer reads.
    released.await;
    let read = read_turn(stream, &[END]).await;
    // The donor stops decoding at the stop id: it never reaches the id outside the
    // vocabulary, and its drain swallows what follows.
    assert_eq!(read.text(), "h");
    assert_eq!(read.outcome.error(), None);
    assert_eq!(read.outcome.finish, "stop");
    assert_eq!(read.outcome.completion_tokens, 2);
    until(|| rec.records().len() == 1).await;
    assert_eq!(
        (rec.records()[0].finish, rec.records()[0].output_tokens),
        ("stop", 2)
    );
}

#[tokio::test(start_paused = true)]
async fn a_death_after_the_stop_is_part_of_the_drain() {
    // The engine dies at its sixth token (index 5); the answer ends at index 2.
    let mut script = answer("hi");
    script.extend(enc("after the end"));
    let engine = DyingEngine::new(FakeScript::new(script).max_context(CTX))
        .unwrap_or_else(|e| panic!("{e}"));
    let (d, rec, _) = driver(Arc::new(engine.clone())).await;
    let released = rec.released.notified();
    let stream = d.turn(request(&enc("hi"), 50));
    released.await;
    assert!(engine.is_dead(), "the engine ran ahead to its death");
    let read = read_turn(stream, &[END]).await;
    assert_eq!(read.text(), "hi");
    assert_eq!(read.outcome.error(), None);
    assert_eq!(read.outcome.finish, "stop");
    // The death is still known to the driver thread: the next turn starts the engine again.
    let read = read_turn(d.turn(request(&enc("hi"), 50)), &[END]).await;
    assert_eq!(engine.restarts(), 1);
    assert_eq!(read.outcome.finish, "stop");
}

#[tokio::test(start_paused = true)]
async fn the_observer_sees_the_turn_in_order() {
    let (d, rec, _) = driver(Arc::new(fake(answer("ab")))).await;
    let _ = read_turn(d.turn(request(&enc("hi"), 9)), &[END]).await;
    assert_eq!(
        rec.seen.list(),
        [
            "queued",
            "dequeued",
            "active reading the prompt 2 9",
            "release",
            "inactive",
            "finished stop"
        ]
    );
}

/// A continuation policy that calls the engine once more, on the prompt and what it wrote.
struct OnceMore(bool);

impl ContinuationPolicy for OnceMore {
    fn after_call(&mut self, call: &CallSummary<'_>) -> Continuation {
        if self.0 {
            return Continuation::Finish;
        }
        self.0 = true;
        let mut prompt = call.prompt.to_vec();
        prompt.extend_from_slice(call.produced);
        let left = call
            .max_new
            .saturating_sub(u32::try_from(call.produced.len()).unwrap_or(0));
        Continuation::Again {
            prompt: prompt.into(),
            max_new: left,
        }
    }
}

#[tokio::test(start_paused = true)]
async fn a_continuation_calls_again_and_merges_the_figures() {
    let engine = ClockedEngine::new(FakeScript::new(enc("abc")).max_context(CTX))
        .unwrap_or_else(|e| panic!("{e}"));
    let probe = engine.probe();
    let (d, _, _) = driver(Arc::new(engine)).await;
    let prompt = enc("0123456789");
    let mut req = request(&prompt, 10);
    req.continuation = Box::new(OnceMore(false));
    let read = read_turn(d.turn(req), &[]).await;
    assert_eq!(read.text(), "abcabc");
    assert_eq!(probe.generations(), 2);
    let second = probe.last_request().unwrap_or_else(|| panic!("no request"));
    assert_eq!(second.prompt.len(), 13);
    assert_eq!(second.max_new, 7);
    let f = read.outcome.figures.unwrap_or_else(|| panic!("no figures"));
    // prompt_tokens and reused from the first call; generated and the clock summed.
    assert_eq!(
        (f.prompt_tokens, f.reused, f.generated),
        (Some(10), Some(5), Some(6))
    );
    assert_eq!((f.prompt_ms, f.decode_ms), (Some(80.0), Some(120.0)));
    assert_eq!((f.hits, f.lookups), (Some(18), Some(20)));
}

/// A continuation policy that starts one more call after the first, as a fair slice
/// (`Again`) or as a new segment (`NextSegment`), on a prompt of its own.
struct SecondCall {
    segment: bool,
    prompt: Vec<u32>,
    max_new: u32,
    asked: bool,
}

impl SecondCall {
    fn new(segment: bool, prompt: &[u32], max_new: u32) -> Self {
        Self {
            segment,
            prompt: prompt.to_vec(),
            max_new,
            asked: false,
        }
    }
}

impl ContinuationPolicy for SecondCall {
    fn after_call(&mut self, _call: &CallSummary<'_>) -> Continuation {
        if self.asked {
            return Continuation::Finish;
        }
        self.asked = true;
        let (prompt, max_new) = (self.prompt.clone().into(), self.max_new);
        if self.segment {
            Continuation::NextSegment { prompt, max_new }
        } else {
            Continuation::Again { prompt, max_new }
        }
    }
}

#[tokio::test(start_paused = true)]
async fn a_non_finite_failure_at_a_new_segment_runs_that_segment_again() {
    // The second engine call fails before its first token; the first call sent tokens.
    let eng = NonFiniteEngine::new(
        FakeScript::new(enc("abc")).max_context(CTX),
        vec![None, Some(0)],
    )
    .unwrap_or_else(|e| panic!("{e}"));
    let probe = eng.probe();
    let (d, _, cap) = driver(Arc::new(eng.clone())).await;
    let segment = enc("segment two");
    let mut req = request(&enc("hi"), 20);
    req.continuation = Box::new(SecondCall::new(true, &segment, 7));
    let read = read_turn(d.turn(req), &[]).await;
    // The donor runs `attempts` afresh for the segment: its retry runs the segment's own
    // prompt and budget again, not the request's.
    assert_eq!(eng.calls(), 3);
    let last = probe.last_request().unwrap_or_else(|| panic!("no request"));
    assert_eq!((last.prompt.to_vec(), last.max_new), (segment, 7));
    assert_eq!(read.text(), "abcabc");
    assert_eq!(read.outcome.error(), None);
    assert!(cap
        .lines()
        .iter()
        .any(|l| l.contains("running the request again from token 0")));
}

#[tokio::test(start_paused = true)]
async fn a_non_finite_failure_in_a_later_slice_ends_the_answer() {
    // A fair slice shares its attempt: tokens were sent, so the answer ends there.
    let eng = NonFiniteEngine::new(
        FakeScript::new(enc("abc")).max_context(CTX),
        vec![None, Some(0)],
    )
    .unwrap_or_else(|e| panic!("{e}"));
    let (d, _, _) = driver(Arc::new(eng.clone())).await;
    let mut req = request(&enc("hi"), 20);
    req.continuation = Box::new(SecondCall::new(false, &enc("hiabc"), 17));
    let read = read_turn(d.turn(req), &[]).await;
    assert_eq!(eng.calls(), 2);
    assert_eq!(read.text(), "abc");
    assert_eq!(read.outcome.end, TurnEnd::NonFiniteCut);
    assert_eq!(read.outcome.finish, "length");
}

#[tokio::test(start_paused = true)]
async fn a_new_segment_reports_its_own_figures() {
    let engine = ClockedEngine::new(FakeScript::new(enc("abc")).max_context(CTX))
        .unwrap_or_else(|e| panic!("{e}"));
    let (d, _, _) = driver(Arc::new(engine)).await;
    let prompt = enc("0123456789");
    let mut segment = prompt.clone();
    segment.extend(enc("abc"));
    let mut req = request(&prompt, 10);
    req.continuation = Box::new(SecondCall::new(true, &segment, 7));
    let read = read_turn(d.turn(req), &[]).await;
    assert_eq!(read.text(), "abcabc");
    let f = read.outcome.figures.unwrap_or_else(|| panic!("no figures"));
    // Only the last segment's call, read back to the request's own prompt (its 13-token
    // prompt held 5 cached tokens, 3 of them its own kept tokens).
    assert_eq!(
        (f.prompt_tokens, f.reused, f.generated),
        (Some(10), Some(2), Some(3))
    );
    assert_eq!((f.prompt_ms, f.decode_ms), (Some(40.0), Some(60.0)));
    assert_eq!((f.hits, f.lookups), (Some(9), Some(10)));
}

/// An engine that answers with an error when its call returns after the cancel (an `ERR`
/// read during the drain).
struct ErrOnDrain {
    inner: Box<dyn EngineInstance>,
    message: &'static str,
}

impl EngineInstance for ErrOnDrain {
    fn descriptor(&self) -> &EngineDescriptor {
        self.inner.descriptor()
    }

    fn generate(
        &mut self,
        req: &GenerationRequest,
        control: &ControlProbe,
        sink: &mut dyn EventSink,
    ) -> Result<Terminal, EngineFailure> {
        let r = self.inner.generate(req, control, sink);
        if control.is_cancelled() {
            return Err(EngineFailure::reported(self.message));
        }
        r
    }

    fn health(&mut self) -> Health {
        self.inner.health()
    }

    fn shutdown(self: Box<Self>, deadline: std::time::Instant) -> ShutdownOutcome {
        self.inner.shutdown(deadline)
    }
}

struct ErrOnDrainFactory(FakeFactory, &'static str);

impl EngineFactory for ErrOnDrainFactory {
    fn kind(&self) -> EngineKind {
        self.0.kind()
    }

    fn start(&self, cfg: &EngineStartConfig) -> Result<Box<dyn EngineInstance>, EngineFailure> {
        Ok(Box::new(ErrOnDrain {
            inner: self.0.start(cfg)?,
            message: self.1,
        }))
    }
}

#[derive(Clone, Copy, Debug)]
enum Stopper {
    Finish,
    Cancel,
    Drop,
}

/// Reads three tokens of a long answer, stops as `how` says, and returns the finish.
async fn err_on_drain(message: &'static str, how: Stopper) -> &'static str {
    let long: Vec<u32> = std::iter::repeat_n(u32::from(b'a'), 2000)
        .chain([END])
        .collect();
    let factory =
        FakeFactory::new(FakeScript::new(long).max_context(CTX)).unwrap_or_else(|e| panic!("{e}"));
    let settings = TurnSettings {
        channel_capacity: 1,
        ..quiet_settings()
    };
    let (d, rec, cap) = driver_with(Arc::new(ErrOnDrainFactory(factory, message)), settings).await;
    let mut s = d.turn(request(&enc("hi"), 3000));
    let mut n = 0;
    let finish = loop {
        match s.next().await {
            Some(TurnItem::Token(_)) => {
                n += 1;
                if n == 3 {
                    match how {
                        Stopper::Finish => s.finish(CallerFinish::Stop),
                        Stopper::Cancel => s.cancel(),
                        Stopper::Drop => {
                            let released = rec.released.notified();
                            drop(s);
                            released.await;
                            until(|| rec.records().len() == 1).await;
                            break rec.records()[0].finish;
                        }
                    }
                }
            }
            Some(TurnItem::Done(o)) => {
                assert_eq!(o.error(), None, "{how:?}");
                break o.finish;
            }
            Some(TurnItem::Ping(_)) => {}
            None => panic!("no Done"),
        }
    };
    assert!(
        !cap.lines().iter().any(|l| l.contains("reported an error")),
        "{:?}",
        cap.lines()
    );
    assert_eq!(d.fifo().used(), 0);
    finish
}

#[tokio::test(start_paused = true)]
async fn an_err_during_the_drain_keeps_the_answer_as_it_ended() {
    for message in ["verify: layer 31 never rang", NON_FINITE_MESSAGE] {
        assert_eq!(err_on_drain(message, Stopper::Finish).await, "stop");
        assert_eq!(err_on_drain(message, Stopper::Cancel).await, "cancel");
        assert_eq!(err_on_drain(message, Stopper::Drop).await, "disconnect");
    }
}

/// A factory whose first instance panics in `generate`; later instances are the scripted
/// engine's own.
struct PanicFirst {
    inner: FakeFactory,
    starts: AtomicU32,
}

struct Panicking(Box<dyn EngineInstance>);

impl EngineInstance for Panicking {
    fn descriptor(&self) -> &EngineDescriptor {
        self.0.descriptor()
    }

    fn generate(
        &mut self,
        _req: &GenerationRequest,
        _control: &ControlProbe,
        _sink: &mut dyn EventSink,
    ) -> Result<Terminal, EngineFailure> {
        panic!("a synthetic engine bug");
    }

    fn shutdown(self: Box<Self>, deadline: std::time::Instant) -> ShutdownOutcome {
        self.0.shutdown(deadline)
    }
}

impl EngineFactory for PanicFirst {
    fn kind(&self) -> EngineKind {
        self.inner.kind()
    }

    fn start(&self, cfg: &EngineStartConfig) -> Result<Box<dyn EngineInstance>, EngineFailure> {
        let inner = self.inner.start(cfg)?;
        if self.starts.fetch_add(1, Ordering::SeqCst) == 0 {
            return Ok(Box::new(Panicking(inner)));
        }
        Ok(inner)
    }
}

#[tokio::test(start_paused = true)]
async fn a_panic_in_the_engine_is_a_death_and_the_next_turn_restarts_it() {
    let factory = Arc::new(PanicFirst {
        inner: fake(answer("ok")),
        starts: AtomicU32::new(0),
    });
    let (d, _, cap) = driver(factory.clone()).await;
    let read = read_turn(d.turn(request(&enc("hi"), 5)), &[END]).await;
    let f = read
        .outcome
        .error()
        .and_then(TurnError::engine_failure)
        .unwrap_or_else(|| panic!("no engine failure: {:?}", read.outcome));
    assert_eq!(
        (f.kind, f.message.as_str()),
        (FailureKind::Died, ENGINE_PANICKED)
    );
    assert!(f.poisoned);
    assert_eq!(read.outcome.finish, "error");
    assert_eq!(d.fifo().used(), 0);
    // The driver thread lives on: the next turn starts the engine again, through the
    // admission step, and is served.
    let read = read_turn(d.turn(request(&enc("hi"), 5)), &[END]).await;
    assert_eq!(read.text(), "ok");
    assert_eq!(factory.starts.load(Ordering::SeqCst), 2);
    assert_eq!(d.fifo().used(), 0);
    assert!(cap
        .lines()
        .iter()
        .any(|l| l.starts_with("[console] the engine panicked")));
}

/// A factory whose second and later instances report two places.
struct TwoPlacesLater {
    inner: FakeFactory,
    starts: AtomicU32,
}

struct WithPlaces {
    inner: Box<dyn EngineInstance>,
    desc: EngineDescriptor,
}

impl EngineInstance for WithPlaces {
    fn descriptor(&self) -> &EngineDescriptor {
        &self.desc
    }

    fn generate(
        &mut self,
        req: &GenerationRequest,
        control: &ControlProbe,
        sink: &mut dyn EventSink,
    ) -> Result<Terminal, EngineFailure> {
        self.inner.generate(req, control, sink)
    }

    fn shutdown(self: Box<Self>, deadline: std::time::Instant) -> ShutdownOutcome {
        self.inner.shutdown(deadline)
    }
}

impl EngineFactory for TwoPlacesLater {
    fn kind(&self) -> EngineKind {
        self.inner.kind()
    }

    fn start(&self, cfg: &EngineStartConfig) -> Result<Box<dyn EngineInstance>, EngineFailure> {
        let inner = self.inner.start(cfg)?;
        if self.starts.fetch_add(1, Ordering::SeqCst) == 0 {
            return Ok(inner);
        }
        let mut desc = inner.descriptor().clone();
        desc.caps.multi = Some(2);
        Ok(Box::new(WithPlaces { inner, desc }))
    }
}

#[tokio::test(start_paused = true)]
async fn a_switch_to_more_places_resizes_the_fifo_only_at_the_next_turn() {
    let factory = Arc::new(TwoPlacesLater {
        inner: fake(long_answer()),
        starts: AtomicU32::new(0),
    });
    let settings = TurnSettings {
        channel_capacity: 1,
        ..quiet_settings()
    };
    let (d, _, _) = driver_with(factory.clone(), settings).await;
    assert_eq!(d.fifo().capacity(), 1);
    let held = d.fifo().acquire(Units::All).await;
    let switcher = d.clone();
    let to: Arc<dyn EngineFactory> = factory.clone();
    let switch =
        tokio::spawn(async move { switcher.switch_engine(to, EngineStartConfig::new()).await });
    until(|| d.fifo().waiting() == 1).await;
    // A turn queued behind the switch.
    let mut stream = d.turn(request(&enc("hi"), 1000));
    until(|| d.fifo().waiting() == 2).await;
    drop(held);
    switch
        .await
        .unwrap_or_else(|e| panic!("{e}"))
        .unwrap_or_else(|e| panic!("{e}"));
    match stream.next().await {
        Some(TurnItem::Token(_)) => {}
        other => panic!("expected a token, got {other:?}"),
    }
    // The turn's start on the engine resized the FIFO, while the turn held one place: the
    // count is the places really held.
    assert_eq!((d.fifo().capacity(), d.fifo().used()), (2, 1));
    stream.finish(CallerFinish::Stop);
    let read = read_turn(stream, &[]).await;
    assert_eq!(read.outcome.finish, "stop");
    assert_eq!(d.fifo().used(), 0);
}

#[tokio::test(start_paused = true)]
async fn a_turn_after_the_driver_thread_ended_still_reports_its_release() {
    let (d, rec, _) = driver(Arc::new(fake(answer("ok")))).await;
    d.close().await;
    let read = read_turn(d.turn(request(&enc("hi"), 5)), &[END]).await;
    let f = read
        .outcome
        .error()
        .and_then(TurnError::engine_failure)
        .map(|f| f.kind);
    assert_eq!(f, Some(FailureKind::Died));
    assert_eq!(d.fifo().used(), 0);
    assert_eq!(rec.seen.list(), ["queued", "dequeued", "release"]);
}

#[tokio::test(start_paused = true)]
async fn queued_turns_go_in_order_and_ping_while_they_wait() {
    let settings = TurnSettings {
        queue_ping: Some(Duration::from_millis(100)),
        ..quiet_settings()
    };
    let (d, _, _) = driver_with(Arc::new(fake(answer("x"))), settings).await;
    let held = d.fifo().acquire(Units::All).await;
    let mut first = d.turn(request(&enc("a"), 5));
    let mut second = d.turn(request(&enc("b"), 5));
    assert_eq!(first.next().await, Some(TurnItem::Ping(None)));
    assert_eq!(second.next().await, Some(TurnItem::Ping(None)));
    assert_eq!(d.fifo().waiting(), 2);
    drop(held);
    let a = read_turn(first, &[END]).await;
    let b = read_turn(second, &[END]).await;
    assert_eq!((a.text(), b.text()), ("x".to_owned(), "x".to_owned()));
    assert_eq!(d.fifo().used(), 0);
}
