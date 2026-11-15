//! Provenance: translated from project-maya serve/test_server.py::GoneClients::test_a_queued_request_leaves_when_its_client_goes, serve/test_server.py::QueuedKeepAlives::test_keep_alives_while_queued and serve/test_server.py::ModelManagement::test_a_request_while_the_engine_starts_gets_a_retryable_503 at 7e68a30f (MIT); license text in console/LICENSES/project-maya-MIT.txt.
//!
//! API-07: the lifecycle of one request on a real loopback socket, with the driver on the
//! chat-completions route, a probe dialect and ENG-02's synthetic engines.
//!
//! The gone-client, keep-alive and write-failure tests are timing-sensitive; they wait on
//! recorded events with a deadline instead of sleeping.
//!
//! Behavior reference: project-maya serve/server.py:5019-5044, 6241-6297, 6584-6624,
//! 3680-3681, 4364-4365, 4796-4808 and 2093-2110 at 7e68a30f.

#[path = "api07_kit.rs"]
mod kit;

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Condvar, Mutex, PoisonError};
use std::time::Duration;

use console_core::engine::{
    CommittedToken, ControlProbe, DeliveryRefused, EngineDescriptor, EngineEvent, EngineFactory,
    EngineFailure, EngineInstance, EngineKind, EngineStartConfig, EngineStop, EventSink,
    GenerationRequest, Provenance, ShutdownOutcome, Terminal,
};
use console_core::fifo::EngineFifo;
use console_core::request::{text_file_limit, CTX_SLACK};
use console_core::turn::{TurnDriver, TurnSettings, STOPPING_MESSAGE};
use console_engine::fake::doubles::HeldEngine;
use console_engine::fake::{FakeFactory, FakeScript};
use console_http::inference::{
    AttachCall, AttachDialect, Attachments, InferenceError, InferenceHooks, InferenceSettings,
    ReloadState, UpdaterState, OVERLOADED_UPDATING,
};
use serde_json::{Map, Value};

use kit::{
    answer, chat, count, parse_response, read_to_eof, read_until, Harness, Record, Setup, CTX,
};

fn fake(script: Vec<u32>) -> FakeFactory {
    FakeFactory::new(FakeScript::new(script).max_context(CTX)).unwrap_or_else(|e| panic!("{e}"))
}

fn held() -> HeldEngine {
    HeldEngine::new(FakeScript::new(answer("</think>\n\nhello")).max_context(CTX))
        .unwrap_or_else(|e| panic!("{e}"))
}

async fn wait_held(engine: &HeldEngine) {
    let e = engine.clone();
    let held = tokio::task::spawn_blocking(move || e.wait_held(kit::DEADLINE))
        .await
        .unwrap_or(false);
    assert!(held, "the first request should hold the engine");
}

// ------------------------------------------------------------------- gone clients (#314)

// Donor: serve/test_server.py::GoneClients::test_a_queued_request_leaves_when_its_client_goes
#[tokio::test]
async fn a_queued_request_leaves_when_its_client_goes() {
    let engine = held();
    let h = Harness::start(Setup::new(Arc::new(engine.clone()))).await;
    let mut first = h.send(&chat("hi", 8, false, "")).await;
    wait_held(&engine).await;
    for stream in [false, true] {
        let waiting = h.send(&chat("hi", 8, stream, "")).await;
        h.record
            .wait("the second request should wait in the queue", |r| {
                r.queued() == 1
            })
            .await;
        drop(waiting);
        h.record
            .wait(
                &format!("stream={stream}: still queued after its client left"),
                |r| r.queued() == 0,
            )
            .await;
    }
    engine.release();
    // The request that kept its client answers as before.
    let got = parse_response(&read_to_eof(&mut first).await);
    assert_eq!(got.status, 200, "{:?}", got.text());
    assert!(got.raw.starts_with(b"HTTP/1.0 200 OK\r\n"));
    // Neither gone request reached the engine.
    assert_eq!(engine.calls(), 1);
    assert_eq!(h.record.records().len(), 1);
    assert_eq!(h.driver.fifo().used(), 0);
    h.stop().await;
}

// ------------------------------------------------------------- queue keep-alives (#483)

/// The probe-dialect half of the donor's QueuedKeepAlives test: the row stays pending
/// until both chat dialects exist (API-08, API-09).
#[tokio::test]
async fn keep_alives_while_queued() {
    let engine = held();
    let mut setup = Setup::new(Arc::new(engine.clone()));
    setup.turn.queue_ping = Some(Duration::from_millis(20));
    let h = Harness::start(setup).await;
    let mut first = h.send(&chat("hi", 8, false, "")).await;
    wait_held(&engine).await;
    let mut s = h.send(&chat("hi", 8, true, "")).await;
    h.record.wait("queued", |r| r.queued() == 1).await;
    let waited = read_until(&mut s, |got| count(got, b": keep-alive\n\n") >= 3).await;
    assert!(count(&waited, b": keep-alive\n\n") >= 3, "{waited:?}");
    let text = String::from_utf8_lossy(&waited);
    assert!(text.starts_with("HTTP/1.0 200 OK\r\n"), "{text}");
    assert!(text.contains("Content-Type: text/event-stream\r\nCache-Control: no-cache\r\n\r\n"));
    assert!(
        !text.contains("\"text\""),
        "still queued: nothing answered yet"
    );
    drop(s);
    h.record
        .wait("gone while queued: left the line", |r| r.queued() == 0)
        .await;
    // The answer after a wait is unchanged.
    let mut s = h.send(&chat("hi", 64, true, "")).await;
    h.record.wait("queued", |r| r.queued() == 1).await;
    let first_part = read_until(&mut s, |got| count(got, b": keep-alive\n\n") >= 1).await;
    engine.release();
    let mut rest = first_part;
    rest.extend(read_to_eof(&mut s).await);
    let got = parse_response(&rest);
    assert!(got.streamed_text().contains("hello"), "{:?}", got.text());
    assert!(got.text().ends_with("data: [DONE]\n\n"), "{:?}", got.text());
    let first = parse_response(&read_to_eof(&mut first).await);
    assert_eq!(first.status, 200);
    assert_eq!(engine.calls(), 2);
    h.stop().await;
}

// ------------------------------------------------- write failures and the fake transcript

/// An engine that writes tokens until it reads the cancel (or nobody reads), and records
/// each call, its STOP and its drain with the FIFO's places in use.
#[derive(Clone, Default)]
struct Transcript {
    link: Arc<Mutex<Option<(EngineFifo, Record)>>>,
}

impl Transcript {
    fn link(&self, fifo: EngineFifo, record: Record) {
        *self.link.lock().unwrap_or_else(PoisonError::into_inner) = Some((fifo, record));
    }

    fn note(&self, what: &str) {
        let link = self.link.lock().unwrap_or_else(PoisonError::into_inner);
        if let Some((fifo, record)) = link.as_ref() {
            record.push(format!("{what} used={}", fifo.used()));
        }
    }
}

struct TranscriptEngine {
    desc: EngineDescriptor,
    t: Transcript,
}

impl EngineFactory for Transcript {
    fn kind(&self) -> EngineKind {
        EngineKind::Scripted
    }

    fn start(&self, _cfg: &EngineStartConfig) -> Result<Box<dyn EngineInstance>, EngineFailure> {
        let mut desc = EngineDescriptor::new(EngineKind::Scripted, Provenance::Synthetic);
        // Room for a long answer: the client goes away long before its end.
        desc.max_context = 1 << 21;
        Ok(Box::new(TranscriptEngine {
            desc,
            t: self.clone(),
        }))
    }
}

impl EngineInstance for TranscriptEngine {
    fn descriptor(&self) -> &EngineDescriptor {
        &self.desc
    }

    fn generate(
        &mut self,
        req: &GenerationRequest,
        control: &ControlProbe,
        sink: &mut dyn EventSink,
    ) -> Result<Terminal, EngineFailure> {
        self.t.note("generate");
        let prompt_tokens = u32::try_from(req.prompt.len()).unwrap_or(u32::MAX);
        let _ = sink.deliver(EngineEvent::Admitted {
            prompt_tokens,
            reused_tokens: None,
        });
        for index in 0..req.max_new {
            if control.is_cancelled() {
                // The in-process engine's STOP: it reads the cancel between steps.
                self.t.note("stop");
                self.t.note("drain");
                return Ok(Terminal::bare(EngineStop::Cancelled));
            }
            let token = CommittedToken {
                index,
                position: u64::from(prompt_tokens) + u64::from(index),
                id: 97 + index % 26,
                logprob: None,
            };
            loop {
                match sink.deliver(EngineEvent::Token(token.clone())) {
                    Ok(()) => break,
                    Err(DeliveryRefused::Backpressure) => std::thread::yield_now(),
                    Err(DeliveryRefused::ConsumerGone) => {
                        self.t.note("stop");
                        self.t.note("drain");
                        return Ok(Terminal::bare(EngineStop::Cancelled));
                    }
                }
            }
        }
        self.t.note("drain");
        Ok(Terminal::bare(EngineStop::Length))
    }

    fn shutdown(self: Box<Self>, _deadline: std::time::Instant) -> ShutdownOutcome {
        ShutdownOutcome::Graceful
    }
}

/// The transcript's engine events and the place's release, in order.
fn engine_events(record: &Record) -> Vec<String> {
    record
        .events()
        .into_iter()
        .filter(|e| {
            e.starts_with("generate")
                || e.starts_with("stop")
                || e.starts_with("drain")
                || e == "release"
        })
        .collect()
}

async fn transcript_harness() -> (Harness, Transcript) {
    let t = Transcript::default();
    let h = Harness::start(Setup::new(Arc::new(t.clone()))).await;
    t.link(h.driver.fifo().clone(), h.record.clone());
    (h, t)
}

/// A stream whose client goes away mid-answer: the next write fails, and the engine is
/// stopped exactly once, then drained, and only then is the FIFO place given back. The
/// client watcher is off here (as for a web-app answer), so the write failure alone stops
/// the engine.
#[tokio::test]
async fn a_write_failure_stops_the_engine_once_then_drains_then_releases() {
    let (h, _t) = transcript_harness().await;
    let mut s = h
        .send(&chat("hi", 1_000_000, true, ", \"probe_watch\": false"))
        .await;
    let got = read_until(&mut s, |got| count(got, b"data: {\"text\"") >= 3).await;
    assert!(count(&got, b"data: {\"text\"") >= 3);
    drop(s);
    h.record
        .wait("the place is given back", |r| {
            r.events().iter().any(|e| e == "release")
        })
        .await;
    assert_eq!(
        engine_events(&h.record),
        ["generate used=1", "stop used=1", "drain used=1", "release"]
    );
    h.record
        .wait("the turn is booked", |r| r.records().len() == 1)
        .await;
    assert_eq!(h.record.records()[0].finish, "disconnect");
    assert_eq!(h.driver.fifo().used(), 0);
    // The engine serves the next request.
    let next = h.call(&chat("hi", 3, false, "")).await;
    assert_eq!(next.status, 200, "{:?}", next.text());
    assert_eq!(next.json()["text"], "abc");
    h.stop().await;
}

/// The same with the client watcher on: whichever notices first, the engine is stopped
/// once.
#[tokio::test]
async fn a_gone_stream_client_stops_the_engine_once_with_the_watcher_on() {
    let (h, _t) = transcript_harness().await;
    let mut s = h.send(&chat("hi", 1_000_000, true, "")).await;
    let _ = read_until(&mut s, |got| count(got, b"data: {\"text\"") >= 3).await;
    drop(s);
    h.record
        .wait("the place is given back", |r| {
            r.events().iter().any(|e| e == "release")
        })
        .await;
    assert_eq!(
        engine_events(&h.record),
        ["generate used=1", "stop used=1", "drain used=1", "release"]
    );
    h.stop().await;
}

/// A collected answer whose client leaves while the engine runs: the watcher cancels the
/// turn (finish `cancel`), the engine is stopped once and drained before the place goes
/// back.
#[tokio::test]
async fn a_client_that_leaves_a_collected_answer_stops_the_engine_once() {
    let (h, _t) = transcript_harness().await;
    let s = h.send(&chat("hi", 1_000_000, false, "")).await;
    h.record
        .wait("the engine runs", |r| {
            r.events().iter().any(|e| e.starts_with("generate"))
        })
        .await;
    drop(s);
    h.record
        .wait("the turn is booked", |r| r.records().len() == 1)
        .await;
    assert_eq!(
        engine_events(&h.record),
        ["generate used=1", "stop used=1", "drain used=1", "release"]
    );
    assert_eq!(h.record.records()[0].finish, "cancel");
    h.stop().await;
}

// ------------------------------------------------------- the model is starting (#677)

/// A factory whose starts after the first wait until the test opens its gate: while one
/// waits, the engine reports no context (a start in progress, no `READY` yet).
#[derive(Clone)]
struct Gated {
    inner: FakeFactory,
    record: Record,
    gate: Arc<(Mutex<(u32, bool)>, Condvar)>,
}

impl Gated {
    fn open(&self) {
        let (lock, cv) = &*self.gate;
        lock.lock().unwrap_or_else(PoisonError::into_inner).1 = true;
        cv.notify_all();
    }
}

impl EngineFactory for Gated {
    fn kind(&self) -> EngineKind {
        EngineKind::Scripted
    }

    fn start(&self, cfg: &EngineStartConfig) -> Result<Box<dyn EngineInstance>, EngineFailure> {
        let (lock, cv) = &*self.gate;
        let mut g = lock.lock().unwrap_or_else(PoisonError::into_inner);
        g.0 += 1;
        if g.0 > 1 {
            self.record.push("starting");
            let (_g, _) = cv
                .wait_timeout_while(g, kit::DEADLINE, |s| !s.1)
                .unwrap_or_else(PoisonError::into_inner);
        } else {
            drop(g);
        }
        self.inner.start(cfg)
    }
}

// Donor: serve/test_server.py::ModelManagement::test_a_request_while_the_engine_starts_gets_a_retryable_503
#[tokio::test]
async fn a_request_while_the_engine_starts_gets_a_retryable_503() {
    let record = Record::default();
    let gated = Gated {
        inner: fake(answer("</think>\n\nok")),
        record: record.clone(),
        gate: Arc::new((Mutex::new((0, false)), Condvar::new())),
    };
    let h = Harness::start(Setup::new(Arc::new(gated.clone()))).await;
    let body = chat("hi", 8, false, "");
    let driver: TurnDriver = h.driver.clone();
    let restart = tokio::spawn(async move { driver.restart().await });
    record
        .wait("a start is in progress", |r| {
            r.events().iter().any(|e| e == "starting")
        })
        .await;
    assert_eq!(h.driver.max_context(), 0);
    let got = h.call(&body).await;
    assert_eq!(got.status, 503);
    assert_eq!(
        got.text(),
        r#"{"error": {"type": "invalid_request_error", "message": "the model is starting; try again in a moment"}}"#
    );
    assert!(got.json()["error"]["message"]
        .as_str()
        .unwrap_or_default()
        .contains("starting"));
    gated.open();
    let restarted = restart.await.unwrap_or_else(|e| panic!("join: {e}"));
    assert_eq!(restarted, Ok(()));
    assert_eq!(h.driver.max_context(), CTX);
    let got = h.call(&body).await;
    assert_eq!(got.status, 200, "{:?}", got.text());
    h.stop().await;
}

/// The engine reports no context only when the turn reaches it: the collected answer is
/// still the 503, since nothing was sent.
#[tokio::test]
async fn an_engine_found_starting_at_its_turn_is_a_503_before_the_first_byte() {
    let factory = fake(answer("ok"));
    let probe = factory.probe();
    let h = Harness::start(Setup::new(Arc::new(factory))).await;
    probe.set_max_context(Some(0));
    let got = h.call(&chat("hi", 8, false, "")).await;
    assert_eq!(got.status, 503);
    assert_eq!(
        got.text(),
        r#"{"error": {"type": "invalid_request_error", "message": "the model is starting; try again in a moment"}}"#
    );
    assert_eq!(probe.generations(), 0);
    h.stop().await;
}

// ------------------------------------------------------------- the overloaded gate

#[derive(Default)]
struct Switch(AtomicBool);

impl ReloadState for Switch {
    fn reloading(&self) -> bool {
        self.0.load(Ordering::SeqCst)
    }
}

impl UpdaterState for Switch {
    fn busy(&self) -> bool {
        self.0.load(Ordering::SeqCst)
    }
}

/// The 503 while a context reload waits or runs, or the updater is busy: before the
/// dialect sees the request, with `Retry-After: 30` between the type and the length, and a
/// body written with `ensure_ascii=True`. The updater's message wins.
#[tokio::test]
async fn chat_routes_answer_503_while_reloading_or_updating() {
    let reload = Arc::new(Switch::default());
    let updater = Arc::new(Switch::default());
    let mut setup = Setup::new(Arc::new(fake(answer("hello"))));
    setup.hooks = InferenceHooks {
        reload: reload.clone(),
        updater: updater.clone(),
        ..InferenceHooks::default()
    };
    let h = Harness::start(setup).await;
    let body = chat("hi", 8, false, "");
    reload.0.store(true, Ordering::SeqCst);
    let got = h.call(&body).await;
    assert_eq!(got.status, 503);
    assert_eq!(
        got.header_names(),
        [
            "Server",
            "Date",
            "Content-Type",
            "Retry-After",
            "Content-Length"
        ]
    );
    assert_eq!(got.header("Retry-After"), Some("30"));
    assert_eq!(
        got.text(),
        r#"{"error": {"type": "overloaded_error", "message": "the model is reloading with a new context size; try again in a minute"}}"#
    );
    updater.0.store(true, Ordering::SeqCst);
    let got = h.call(&body).await;
    assert_eq!(got.status, 503);
    assert_eq!(
        got.text(),
        format!(
            r#"{{"error": {{"type": "overloaded_error", "message": "{OVERLOADED_UPDATING}"}}}}"#
        )
    );
    assert_eq!(h.probe.prepares.load(Ordering::SeqCst), 0);
    reload.0.store(false, Ordering::SeqCst);
    updater.0.store(false, Ordering::SeqCst);
    let got = h.call(&body).await;
    assert_eq!(got.status, 200, "{:?}", got.text());
    assert_eq!(got.json()["text"], "hello");
    h.stop().await;
}

// ------------------------------------------------------- the boundary and the seams

/// Deviation SEC-6.1: every top-level key beginning with `_` is gone before the dialect
/// reads the request; nested keys stay.
#[tokio::test]
async fn internal_keys_are_stripped_before_the_dialect() {
    let h = Harness::start(Setup::new(Arc::new(fake(answer("ok"))))).await;
    let got = h
        .call(&chat(
            "hi",
            8,
            false,
            ", \"_prefill\": \"x\", \"_think_budget\": 5, \"tools\": [{\"_restore\": 1}]",
        ))
        .await;
    assert_eq!(got.status, 200, "{:?}", got.text());
    let seen = h.probe.last_seen().unwrap_or_default();
    let keys: Vec<&str> = seen.keys().map(String::as_str).collect();
    assert_eq!(keys, ["model", "max_tokens", "stream", "messages", "tools"]);
    assert_eq!(seen["tools"][0]["_restore"], 1);
    h.stop().await;
}

/// The attachment planner's seam: called after the gate and the strip, before the
/// dialect, with the donor's arguments; an error is answered as its class.
#[derive(Default)]
struct Expander {
    calls: Mutex<Vec<AttachCall>>,
}

impl Attachments for Expander {
    fn text_only(&self) -> Option<String> {
        Some("text only".into())
    }

    fn expand_request(
        &self,
        req: &mut Map<String, Value>,
        call: &AttachCall,
    ) -> Result<(), InferenceError> {
        self.calls
            .lock()
            .unwrap_or_else(PoisonError::into_inner)
            .push(call.clone());
        if req.contains_key("broken_file") {
            return Err(InferenceError::value("the file is not text"));
        }
        if let Some(Value::Object(m)) = req.get_mut("messages").and_then(|m| m.get_mut(0)) {
            m.insert("content".into(), Value::String("expanded".into()));
        }
        Ok(())
    }
}

#[tokio::test]
async fn the_attachment_planner_runs_before_the_dialect() {
    let expander = Arc::new(Expander::default());
    let mut setup = Setup::new(Arc::new(fake(answer("ok"))));
    setup.hooks.attachments = expander.clone();
    let h = Harness::start(setup).await;
    let got = h.call(&chat("hi", 8, false, "")).await;
    assert_eq!(got.status, 200, "{:?}", got.text());
    assert_eq!(
        h.probe.last_seen().unwrap_or_default()["messages"][0]["content"],
        "expanded"
    );
    let calls = expander
        .calls
        .lock()
        .unwrap_or_else(PoisonError::into_inner)
        .clone();
    assert_eq!(
        calls,
        [AttachCall {
            dialect: AttachDialect::OpenAi,
            want_images: false,
            text_limit: text_file_limit(i64::from(CTX)),
            text_only: Some("text only".into()),
        }]
    );
    let got = h.call(&chat("hi", 8, false, ", \"broken_file\": 1")).await;
    assert_eq!(got.status, 400);
    assert_eq!(
        got.text(),
        r#"{"error": {"type": "invalid_request_error", "message": "the file is not text"}}"#
    );
    assert_eq!(h.probe.prepares.load(Ordering::SeqCst), 1);
    h.stop().await;
}

// ------------------------------------------------------------- debug line and trace

/// The debug line shows the resolved budget (the probe-dialect half of the donor's
/// MaxTokens debug test; the row needs both chat dialects).
#[tokio::test]
async fn the_debug_line_shows_the_resolved_budget() {
    let mut setup = Setup::new(Arc::new(fake(answer("ok"))));
    setup.settings = InferenceSettings {
        debug: true,
        turn_trace: false,
    };
    let h = Harness::start(setup).await;
    let got = h.call(&chat("hi", -1, false, "")).await;
    assert_eq!(got.status, 200, "{:?}", got.text());
    let pt: u32 = 2;
    let want = format!(
        "[console] req probe: msgs=1 tools=0 max_tokens_raw=-1/None max_new={} thinking=True \
         stream=False prompt_tokens={pt} last='user':'hi'",
        i64::from(CTX) - CTX_SLACK - i64::from(pt)
    );
    let lines = h.log.lines();
    assert!(lines.contains(&want), "{lines:?}");
    assert!(want.contains(&format!("max_new={} ", i64::from(CTX) - CTX_SLACK - 2)));
    h.stop().await;
}

/// Without the setting there is no debug line.
#[tokio::test]
async fn no_debug_line_by_default() {
    let h = Harness::start(Setup::new(Arc::new(fake(answer("ok"))))).await;
    let _ = h.call(&chat("hi", -1, false, "")).await;
    assert!(!h.log.lines().iter().any(|l| l.contains(" req probe: ")));
    assert!(!h.log.lines().iter().any(|l| l.contains(" trace n=")));
    h.stop().await;
}

/// The turn trace prints one line at the first token, with the handler's marks in order,
/// once the engine-side `gen_start` mark exists (the probe stands in for M3's client).
/// Without that mark no line is printed, as the donor's in-process engines print none.
#[tokio::test]
async fn the_turn_trace_prints_its_marks_at_the_first_token() {
    let mut setup = Setup::new(Arc::new(fake(answer("ok"))));
    setup.settings = InferenceSettings {
        debug: false,
        turn_trace: true,
    };
    let h = Harness::start(setup).await;
    let got = h.call(&chat("hi", 8, true, "")).await;
    assert_eq!(got.status, 200);
    let got = h.call(&chat("hi", 8, false, "")).await;
    assert_eq!(got.status, 200);
    assert!(!h.log.lines().iter().any(|l| l.contains(" trace n=")));
    let got = h
        .call(&chat("hi", 8, true, ", \"probe_gen_start\": true"))
        .await;
    assert_eq!(got.status, 200);
    let lines: Vec<String> = h
        .log
        .lines()
        .into_iter()
        .filter(|l| l.contains(" trace n="))
        .collect();
    assert_eq!(lines.len(), 1, "{lines:?}");
    let line = &lines[0];
    assert!(
        line.starts_with("[console] trace n=2 http=0.0 body="),
        "{line}"
    );
    let names: Vec<&str> = line
        .split(' ')
        .filter_map(|p| p.split_once('=').map(|(k, _)| k))
        .collect();
    assert_eq!(
        names,
        [
            "n",
            "http",
            "body",
            "json",
            "prepare_start",
            "prepared",
            "gen_start",
            "first_t",
            "t0"
        ]
    );
    h.stop().await;
}

// ------------------------------------------------------------- a stopping server

/// A request that reaches its turn while the server is stopping: the donor's `ValueError`,
/// 400 `invalid_request_error` for a collected answer, the dialect's error event in a
/// stream.
#[tokio::test]
async fn a_stopping_server_refuses_the_turn() {
    let h = Harness::start(Setup::new(Arc::new(fake(answer("ok"))))).await;
    h.driver.set_stopping(true);
    let got = h.call(&chat("hi", 8, false, "")).await;
    assert_eq!(got.status, 400);
    assert_eq!(
        got.text(),
        format!(
            r#"{{"error": {{"type": "invalid_request_error", "message": "{STOPPING_MESSAGE}"}}}}"#
        )
    );
    let got = h.call(&chat("hi", 8, true, "")).await;
    assert_eq!(got.status, 200);
    assert_eq!(
        got.text(),
        format!(
            "data: {{\"error\": {{\"type\": \"server_error\", \"message\": \"{STOPPING_MESSAGE}\"}}}}\n\ndata: [DONE]\n\n"
        )
    );
    h.driver.set_stopping(false);
    let got = h.call(&chat("hi", 8, false, "")).await;
    assert_eq!(got.status, 200);
    h.stop().await;
}

/// A streamed answer that goes to its end: the SSE head, one frame per token, the end.
#[tokio::test]
async fn a_streamed_answer_is_framed_and_ended() {
    let h = Harness::start(Setup::new(Arc::new(fake(answer("hey"))))).await;
    let got = h.call(&chat("hi", 8, true, "")).await;
    assert_eq!(got.status, 200);
    assert_eq!(
        got.header_names(),
        ["Server", "Date", "Content-Type", "Cache-Control"]
    );
    assert_eq!(
        got.text(),
        "data: {\"text\": \"h\"}\n\ndata: {\"text\": \"e\"}\n\ndata: {\"text\": \"y\"}\n\n\
         data: {\"finish\": \"stop\", \"completion_tokens\": 4}\n\ndata: [DONE]\n\n"
    );
    let got = h.call(&chat("hi", 8, false, "")).await;
    assert_eq!(got.status, 200);
    assert_eq!(got.header("Content-Type"), Some("application/json"));
    assert_eq!(
        got.text(),
        r#"{"text": "hey", "finish": "stop", "completion_tokens": 4}"#
    );
    h.stop().await;
}

/// Prompt progress and heartbeats on a stream: a keep-alive without progress is the SSE
/// comment.
#[tokio::test]
async fn a_quiet_engine_gets_keep_alive_comments() {
    let engine = held();
    let mut setup = Setup::new(Arc::new(engine.clone()));
    setup.turn = TurnSettings {
        heartbeat: Some(Duration::from_millis(20)),
        queue_ping: None,
        ..TurnSettings::default()
    };
    let h = Harness::start(setup).await;
    let mut s = h.send(&chat("hi", 64, true, "")).await;
    let waited = read_until(&mut s, |got| count(got, b": keep-alive\n\n") >= 2).await;
    assert!(count(&waited, b": keep-alive\n\n") >= 2);
    engine.release();
    let mut all = waited;
    all.extend(read_to_eof(&mut s).await);
    let got = parse_response(&all);
    assert_eq!(got.streamed_text(), "</think>\n\nhello");
    h.stop().await;
}
