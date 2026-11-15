//! The scripted engine behind the seam: [`FakeFactory`] starts [`FakeEngine`] instances,
//! and [`FakeProbe`] shows what they recorded.

use std::sync::{Arc, Mutex};
use std::time::Instant;

use console_core::engine::{
    ControlProbe, EmbeddingsRef, EngineDescriptor, EngineFactory, EngineFailure, EngineInstance,
    EngineKind, EngineSample, EngineStartConfig, EventSink, GenerationRequest, Health,
    ShutdownOutcome, Terminal,
};

use super::config::{FakeConfigError, FakeScript};
use super::lock;
use super::mock::{last_embeddings, MockCore, MockParts, MockShared, NoHooks};

/// Starts scripted engines (the donor's `MockEngine`). `Send + Sync` and cheap to clone:
/// clones share the script rotation and the record, so a test keeps one clone (or a
/// [`FakeProbe`]) and hands another to the server.
///
/// Every instance reports [`Provenance::Synthetic`](console_core::engine::Provenance) and
/// passes [`require_synthetic`](console_core::engine::require_synthetic); the server's
/// default model name for it is [`DEFAULT_MODEL_NAME`](super::DEFAULT_MODEL_NAME)
/// (deviation PLAN-2).
///
/// Starts and context reloads: a context reload is a shutdown followed by a start with
/// the new context (FIX-1.1). A start whose context differs from the context the factory
/// reports now is a reload and sleeps the reload delay first, as the donor's
/// `_restart_with` does for the mock engine; a start with no context, or with the context
/// the factory already reports, is a restart and does not sleep, as the donor's
/// `restart()` does not. A reload whose delay [`RELOAD_DELAY_ENV`](super::RELOAD_DELAY_ENV)
/// makes unusable fails that start only.
///
/// Behavior reference: project-maya serve/server.py:198-240, 2654, 2765-2772 at 7e68a30f.
#[derive(Debug, Clone)]
pub struct FakeFactory {
    parts: MockParts,
}

impl FakeFactory {
    /// The factory of `script`, after its limits are checked.
    pub fn new(script: FakeScript) -> Result<Self, FakeConfigError> {
        Ok(Self {
            parts: MockParts::new(script)?,
        })
    }

    /// A view of what the engines of this factory recorded.
    pub fn probe(&self) -> FakeProbe {
        FakeProbe {
            shared: Arc::clone(&self.parts.shared),
        }
    }

    /// Starts an instance without boxing it, for tests that call it directly. Fails only
    /// for a context reload whose delay cannot be slept.
    pub fn start_engine(&self, cfg: &EngineStartConfig) -> Result<FakeEngine, EngineFailure> {
        Ok(FakeEngine {
            core: self.parts.start(cfg)?.0,
        })
    }
}

impl EngineFactory for FakeFactory {
    fn kind(&self) -> EngineKind {
        EngineKind::Scripted
    }

    fn start(&self, cfg: &EngineStartConfig) -> Result<Box<dyn EngineInstance>, EngineFailure> {
        Ok(Box::new(self.start_engine(cfg)?))
    }
}

/// One started scripted engine. Neither `Send` nor `Sync` is required of it; it lives on
/// the driver thread that started it.
#[derive(Debug)]
pub struct FakeEngine {
    core: MockCore,
}

impl EngineInstance for FakeEngine {
    fn descriptor(&self) -> &EngineDescriptor {
        &self.core.desc
    }

    fn generate(
        &mut self,
        req: &GenerationRequest,
        control: &ControlProbe,
        sink: &mut dyn EventSink,
    ) -> Result<Terminal, EngineFailure> {
        self.core.run(req, control, sink, &mut NoHooks)
    }

    fn sample(&mut self) -> Option<EngineSample> {
        self.core.refresh();
        None
    }

    fn health(&mut self) -> Health {
        self.core.refresh();
        Health::Alive
    }

    fn shutdown(self: Box<Self>, _deadline: Instant) -> ShutdownOutcome {
        ShutdownOutcome::Graceful
    }
}

/// What the instances of one scripted engine recorded, readable from any thread (the
/// donor's `last_prompt` and `last_embeddings`, and the requests its recording subclasses
/// keep). It also sets the context the instances report, as the donor's tests assign
/// `engine.max_context`.
#[derive(Debug, Clone)]
pub struct FakeProbe {
    shared: Arc<Mutex<MockShared>>,
}

impl FakeProbe {
    #[cfg(any(test, feature = "test-support"))]
    pub(crate) fn from_shared(shared: Arc<Mutex<MockShared>>) -> Self {
        Self { shared }
    }

    /// The prompt of the latest generation (the donor's `last_prompt`, `last_ids`).
    pub fn last_prompt(&self) -> Option<Vec<u32>> {
        lock(&self.shared).last_prompt.as_ref().map(|p| p.to_vec())
    }

    /// The latest request, whole: its `max_new` (the donor's `last_max_new`), its
    /// sampling (`last_sampling`), its logprobs and its hints.
    pub fn last_request(&self) -> Option<GenerationRequest> {
        lock(&self.shared).last_request.clone()
    }

    /// The latest request's picture data (the donor's `last_embeddings`).
    pub fn last_embeddings(&self) -> Option<EmbeddingsRef> {
        last_embeddings(&lock(&self.shared))
    }

    /// Generations started, across restarts.
    pub fn generations(&self) -> u64 {
        lock(&self.shared).generations
    }

    /// The donor's `_runs`: generations that took a script.
    pub fn runs(&self) -> u64 {
        lock(&self.shared).runs
    }

    /// The donor's `turns`: requests that advanced the script rotation.
    pub fn turns(&self) -> usize {
        lock(&self.shared).turns
    }

    /// Instances started.
    pub fn starts(&self) -> u64 {
        lock(&self.shared).starts
    }

    /// Makes every instance report `max_context` (0: a start in progress, so the server
    /// answers "the model is starting"); `None` returns to the started context. Applied at
    /// the instance's next `generate`, `health` or `sample`.
    pub fn set_max_context(&self, max_context: Option<u32>) {
        lock(&self.shared).max_context_override = max_context;
    }
}

#[cfg(test)]
mod tests {
    use std::time::Duration;

    use console_core::engine::{
        generate_ledgered, require_synthetic, ControlHandle, EmbeddingsKind, EngineEvent,
        EngineStop, FailureKind, Provenance, TokenLogprob,
    };

    use super::*;
    use crate::fake::testutil::{req, run, Collect};
    use crate::fake::{jitter_sleep_s, ManualClock, DEFAULT_RELOAD_DELAY};

    fn factory(scripts: Vec<Vec<u32>>) -> FakeFactory {
        FakeScript::rotating(scripts).build().expect("valid")
    }

    #[test]
    fn fake_engine_is_synthetic_and_passes_the_guard() {
        let f = factory(vec![vec![1]]);
        assert_eq!(f.kind(), EngineKind::Scripted);
        let e = f.start(&EngineStartConfig::new()).expect("starts");
        assert_eq!(e.descriptor().provenance, Provenance::Synthetic);
        assert!(require_synthetic(e.descriptor()).is_ok());
        assert_eq!(e.descriptor().max_context, 32_768);
        assert!(e.descriptor().caps.lifecycle.set_context);
    }

    #[test]
    fn fake_scripts_rotate_and_the_last_repeats() {
        let f = factory(vec![vec![1, 2], vec![3], vec![4, 5, 6]]);
        let probe = f.probe();
        let mut e = f.start_engine(&EngineStartConfig::new()).expect("starts");
        let mut got = Vec::new();
        for _ in 0..5 {
            let (sink, out) = run(&mut e, &req(vec![9], 100));
            let (t, counts) = out.expect("runs");
            assert_eq!(t, Terminal::bare(EngineStop::Stop { token: None }));
            assert_eq!(counts.completion_tokens as usize, sink.tokens().len());
            got.push(sink.tokens());
        }
        assert_eq!(
            got,
            vec![
                vec![1, 2],
                vec![3],
                vec![4, 5, 6],
                vec![4, 5, 6],
                vec![4, 5, 6]
            ]
        );
        assert_eq!(
            (probe.turns(), probe.runs(), probe.generations()),
            (5, 5, 5)
        );
        // One script: the rotation does not advance.
        let one = factory(vec![vec![7]]);
        let mut e = one.start_engine(&EngineStartConfig::new()).expect("starts");
        assert!(run(&mut e, &req(vec![9], 100)).1.is_ok());
        assert!(run(&mut e, &req(vec![9], 100)).1.is_ok());
        assert_eq!((one.probe().turns(), one.probe().runs()), (0, 2));
    }

    #[test]
    fn fake_rotation_survives_a_restart() {
        let f = factory(vec![vec![1], vec![2], vec![3]]);
        let mut e = f.start(&EngineStartConfig::new()).expect("starts");
        assert_eq!(run(e.as_mut(), &req(vec![9], 9)).0.tokens(), vec![1]);
        e.shutdown(Instant::now());
        let mut e = f.start(&EngineStartConfig::new()).expect("restarts");
        assert_eq!(run(e.as_mut(), &req(vec![9], 9)).0.tokens(), vec![2]);
        assert_eq!(f.probe().starts(), 2);
    }

    #[test]
    fn fake_output_is_cut_to_max_new() {
        let f = factory(vec![vec![1, 2, 3, 4, 5]]);
        let mut e = f.start_engine(&EngineStartConfig::new()).expect("starts");
        let (sink, out) = run(&mut e, &req(vec![9, 9], 3));
        assert_eq!(sink.tokens(), vec![1, 2, 3]);
        let (t, counts) = out.expect("runs");
        assert_eq!(t.stop, EngineStop::Length);
        assert_eq!((counts.prompt_tokens, counts.completion_tokens), (2, 3));
        assert_eq!(counts.reused_tokens, None, "no clock, nothing cached");
        // Exactly the script's length: a whole answer.
        let (_, out) = run(&mut e, &req(vec![9], 5));
        assert_eq!(out.expect("runs").0.stop, EngineStop::Stop { token: None });
        // max_new 0: admitted, no token.
        let (sink, out) = run(&mut e, &req(vec![9], 0));
        assert_eq!(sink.events.len(), 1);
        assert_eq!(out.expect("runs").0.stop, EngineStop::Length);
        // Positions follow the prompt.
        let (sink, _) = run(&mut e, &req(vec![9, 9, 9], 2));
        let pos: Vec<u64> = sink
            .events
            .iter()
            .filter_map(|e| match e {
                EngineEvent::Token(t) => Some(t.position),
                _ => None,
            })
            .collect();
        assert_eq!(pos, vec![3, 4]);
    }

    #[test]
    fn fake_cancel_is_checked_before_each_token_and_stops_at_once() {
        let f = factory(vec![(1..=10).collect()]);
        let mut e = f.start_engine(&EngineStartConfig::new()).expect("starts");
        let h = ControlHandle::new();
        let mut sink = Collect {
            cancel_after: Some((3, h.clone())),
            ..Collect::default()
        };
        let (t, counts) =
            generate_ledgered(&mut e, &req(vec![9], 100), &h.probe(), &mut sink).expect("runs");
        assert_eq!(t, Terminal::bare(EngineStop::Cancelled));
        assert_eq!(sink.tokens(), vec![1, 2, 3]);
        assert_eq!(counts.completion_tokens, 3);
        // Cancelled before it starts: admitted, then nothing.
        let h = ControlHandle::new();
        h.cancel();
        let mut sink = Collect::default();
        let (t, _) =
            generate_ledgered(&mut e, &req(vec![9], 100), &h.probe(), &mut sink).expect("runs");
        assert_eq!(t.stop, EngineStop::Cancelled);
        assert!(sink.tokens().is_empty());
        // A consumer that leaves stops it too.
        let mut gone = Collect {
            gone_at: Some(2),
            ..Collect::default()
        };
        let h = ControlHandle::new();
        let (t, counts) =
            generate_ledgered(&mut e, &req(vec![9], 100), &h.probe(), &mut gone).expect("runs");
        assert_eq!(t.stop, EngineStop::Cancelled);
        assert_eq!(counts.completion_tokens, 2);
        // Pause and wrap are not read by the scripted engine.
        let h = ControlHandle::new();
        h.pause(true);
        h.wrap();
        let (t, _) = generate_ledgered(
            &mut e,
            &req(vec![9], 100),
            &h.probe(),
            &mut Collect::default(),
        )
        .expect("runs");
        assert_eq!(t.stop, EngineStop::Stop { token: None });
    }

    #[test]
    fn fake_logprobs_have_the_scripted_shape() {
        let f = factory(vec![vec![72, 73]]);
        let mut e = f.start_engine(&EngineStartConfig::new()).expect("starts");
        let mut r = req(vec![9], 10);
        r.logprobs = Some(5);
        let (sink, out) = run(&mut e, &r);
        assert!(out.is_ok());
        assert_eq!(
            sink.logprobs(),
            vec![
                Some(TokenLogprob {
                    logprob: 0.0,
                    top: vec![(72, 0.0)]
                }),
                Some(TokenLogprob {
                    logprob: 0.0,
                    top: vec![(73, 0.0)]
                }),
            ]
        );
        r.logprobs = Some(0);
        let (sink, _) = run(&mut e, &r);
        assert_eq!(
            sink.logprobs()[0],
            Some(TokenLogprob {
                logprob: 0.0,
                top: Vec::new()
            })
        );
        let (sink, _) = run(&mut e, &req(vec![9], 10));
        assert_eq!(sink.logprobs(), vec![None, None]);
    }

    #[test]
    fn fake_tok_s_paces_with_the_jitter_and_reports_figures() {
        let clock = ManualClock::new();
        let script = vec![72, 101, 108];
        let f = FakeScript::new(script.clone())
            .tok_s(Some(10.0))
            .clock(Arc::new(clock.clone()))
            .build()
            .expect("valid");
        let mut e = f.start_engine(&EngineStartConfig::new()).expect("starts");
        let (_, out) = run(&mut e, &req(vec![1, 2, 3, 4], 100));
        let (t, counts) = out.expect("runs");
        let want: Vec<Duration> = script
            .iter()
            .map(|&id| Duration::try_from_secs_f64(jitter_sleep_s(id, 1, 10.0)).expect("finite"))
            .collect();
        assert_eq!(clock.sleeps(), want);
        let c = t.counts.expect("figures");
        assert_eq!(
            (c.generated, c.prompt_tokens, c.reused_tokens),
            (3, 4, Some(0))
        );
        let tm = t.timings.expect("clock");
        assert_eq!(tm.prompt_ms, 2.0);
        let total: Duration = want.iter().sum();
        assert_eq!(tm.decode_ms, total.as_secs_f64() * 1000.0);
        assert_eq!(counts.reused_tokens, Some(0));
        // The second run jitters differently (runs = 2).
        clock.clear_sleeps();
        assert!(run(&mut e, &req(vec![1], 100)).1.is_ok());
        let second: Vec<Duration> = script
            .iter()
            .map(|&id| Duration::try_from_secs_f64(jitter_sleep_s(id, 2, 10.0)).expect("finite"))
            .collect();
        assert_eq!(clock.sleeps(), second);
        // Cancelled before its last token: no figures for this call.
        let h = ControlHandle::new();
        let mut sink = Collect {
            cancel_after: Some((1, h.clone())),
            ..Collect::default()
        };
        let (t, _) =
            generate_ledgered(&mut e, &req(vec![1], 100), &h.probe(), &mut sink).expect("runs");
        assert_eq!(t, Terminal::bare(EngineStop::Cancelled));
        // Cut by max_new: the figures come before the last token sent.
        let (_, out) = run(&mut e, &req(vec![1], 2));
        assert_eq!(out.expect("runs").0.counts.map(|c| c.generated), Some(2));
    }

    #[test]
    fn fake_delay_sleeps_before_each_token() {
        let clock = ManualClock::new();
        let f = FakeScript::new(vec![1, 2])
            .delay(Duration::from_millis(7))
            .clock(Arc::new(clock.clone()))
            .build()
            .expect("valid");
        let mut e = f.start_engine(&EngineStartConfig::new()).expect("starts");
        let (_, out) = run(&mut e, &req(vec![1], 100));
        assert_eq!(out.expect("runs").0.counts, None, "no tok_s: no figures");
        assert_eq!(clock.sleeps(), vec![Duration::from_millis(7); 2]);
    }

    #[test]
    fn fake_reload_sleeps_then_reports_the_new_context() {
        let clock = ManualClock::new();
        let f = FakeScript::new(vec![1])
            .max_context(4096)
            .reload_delay(Duration::from_millis(1500))
            .clock(Arc::new(clock.clone()))
            .build()
            .expect("valid");
        let e = f.start_engine(&EngineStartConfig::new()).expect("starts");
        assert_eq!(e.descriptor().max_context, 4096);
        assert!(clock.sleeps().is_empty(), "the first start does not sleep");
        Box::new(e).shutdown(Instant::now());
        let e = f
            .start_engine(&EngineStartConfig::new().with_context(8192))
            .expect("starts");
        assert_eq!(e.descriptor().max_context, 8192);
        assert_eq!(clock.sleeps(), vec![Duration::from_millis(1500)]);
        // A later restart keeps the reloaded context and does not sleep.
        let e = f.start_engine(&EngineStartConfig::new()).expect("starts");
        assert_eq!(e.descriptor().max_context, 8192);
        assert_eq!(clock.sleeps().len(), 1);
        // The default reload delay is the donor's 2 seconds.
        let d = FakeScript::new(vec![1])
            .clock(Arc::new(clock.clone()))
            .build()
            .expect("valid");
        d.start_engine(&EngineStartConfig::new()).expect("starts");
        d.start_engine(&EngineStartConfig::new().with_context(100))
            .expect("starts");
        assert_eq!(clock.sleeps().last(), Some(&Duration::from_secs(2)));
    }

    #[test]
    fn fake_restart_with_the_same_context_does_not_sleep() {
        let clock = ManualClock::new();
        let f = FakeScript::new(vec![1])
            .max_context(4096)
            .clock(Arc::new(clock.clone()))
            .build()
            .expect("valid");
        f.start_engine(&EngineStartConfig::new().with_context(4096))
            .expect("starts");
        // A restart (after a death or an idle unload) that passes the context the factory
        // already reports, the configured one included: no reload, no sleep.
        f.start_engine(&EngineStartConfig::new().with_context(4096))
            .expect("restarts");
        f.start_engine(&EngineStartConfig::new()).expect("restarts");
        assert!(clock.sleeps().is_empty());
        // A new context is a reload; a restart that then passes it again is not.
        let e = f
            .start_engine(&EngineStartConfig::new().with_context(2048))
            .expect("reloads");
        assert_eq!(e.descriptor().max_context, 2048);
        assert_eq!(clock.sleeps(), vec![DEFAULT_RELOAD_DELAY]);
        let e = f
            .start_engine(&EngineStartConfig::new().with_context(2048))
            .expect("restarts");
        assert_eq!(e.descriptor().max_context, 2048);
        assert_eq!(clock.sleeps().len(), 1);
        assert_eq!(f.probe().starts(), 5);
    }

    #[test]
    fn fake_bad_reload_delay_fails_only_the_reload() {
        let clock = ManualClock::new();
        let env = |name: &str| (name == crate::fake::RELOAD_DELAY_ENV).then(String::new);
        let f = FakeScript::new(vec![1, 2])
            .max_context(4096)
            .clock(Arc::new(clock.clone()))
            .apply_env(env)
            .and_then(FakeScript::build)
            .expect("an unusable reload delay does not stop the build");
        let mut e = f.start_engine(&EngineStartConfig::new()).expect("starts");
        assert!(run(&mut e, &req(vec![9], 10)).1.is_ok(), "it serves");
        Box::new(e).shutdown(Instant::now());
        let err = f
            .start_engine(&EngineStartConfig::new().with_context(8192))
            .expect_err("the reload fails");
        assert_eq!(err.kind, FailureKind::Reported);
        assert_eq!(
            err.to_string(),
            "PULSAR_CONSOLE_MOCK_RELOAD_S: could not convert string to float: ''"
        );
        assert!(clock.sleeps().is_empty());
        // Nothing changed: a start with the old context is a restart and serves.
        let mut e = f
            .start(&EngineStartConfig::new().with_context(4096))
            .expect("restarts with the old context");
        assert_eq!(e.descriptor().max_context, 4096);
        assert!(run(e.as_mut(), &req(vec![9], 10)).1.is_ok());
        assert_eq!(f.probe().starts(), 2);
    }

    #[test]
    fn fake_tok_s_that_sleep_refuses_fails_at_the_first_paced_token() {
        for (tok_s, reason) in [
            (-3.0, "sleep length must be non-negative"),
            (f64::NAN, "Invalid value NaN (not a number)"),
            (1e-300, "timestamp too large to convert to C _PyTime_t"),
        ] {
            let clock = ManualClock::new();
            let f = FakeScript::new(vec![1, 2, 3])
                .tok_s(Some(tok_s))
                .clock(Arc::new(clock.clone()))
                .build()
                .expect("built, as the donor starts with it");
            let mut e = f.start_engine(&EngineStartConfig::new()).expect("starts");
            let (sink, out) = run(&mut e, &req(vec![9], 10));
            let err = out.expect_err("the generation fails");
            assert_eq!(err.kind, FailureKind::Reported, "{tok_s}");
            assert_eq!(err.to_string(), reason, "{tok_s}");
            assert!(sink.tokens().is_empty(), "{tok_s}");
            assert!(
                clock.sleeps().is_empty(),
                "never an unbounded sleep: {tok_s}"
            );
        }
        // An infinite speed sleeps for nothing, as `time.sleep(0.0)` does.
        let f = FakeScript::new(vec![1, 2])
            .tok_s(Some(f64::INFINITY))
            .clock(Arc::new(ManualClock::new()))
            .build()
            .expect("valid");
        let mut e = f.start_engine(&EngineStartConfig::new()).expect("starts");
        assert_eq!(run(&mut e, &req(vec![9], 10)).0.tokens(), vec![1, 2]);
    }

    #[test]
    fn fake_records_the_prompt_and_embeddings() {
        let f = factory(vec![vec![1]]);
        let probe = f.probe();
        assert_eq!(probe.last_prompt(), None);
        let mut e = f.start_engine(&EngineStartConfig::new()).expect("starts");
        let mut r = req(vec![4, 5, 6], 10);
        r.embeddings = Some(console_core::engine::EmbeddingsRef {
            path: "pic.emb".into(),
            kind: EmbeddingsKind::Embeddings,
        });
        assert!(run(&mut e, &r).1.is_ok());
        assert_eq!(probe.last_prompt(), Some(vec![4, 5, 6]));
        assert_eq!(
            probe.last_embeddings().map(|x| x.kind),
            Some(EmbeddingsKind::Embeddings)
        );
        assert_eq!(probe.last_request().map(|r| r.max_new), Some(10));
    }

    #[test]
    fn fake_not_ready_is_refused_before_anything_is_sent() {
        let f = FakeScript::new(vec![1])
            .max_context(0)
            .build()
            .expect("valid");
        let mut e = f.start_engine(&EngineStartConfig::new()).expect("starts");
        let (sink, out) = run(&mut e, &req(vec![1], 10));
        assert_eq!(out.unwrap_err().kind, FailureKind::NotReady);
        assert!(sink.events.is_empty());
        assert_eq!(f.probe().generations(), 0);
        // Even when called directly, not through the ledger.
        let h = ControlHandle::new();
        let err = e
            .generate(&req(vec![1], 10), &h.probe(), &mut Collect::default())
            .unwrap_err();
        assert_eq!(err.kind, FailureKind::NotReady);
    }
}
