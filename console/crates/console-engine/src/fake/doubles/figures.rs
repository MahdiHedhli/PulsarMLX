//! Provenance: translated from project-maya serve/test_server.py::ClockedEngine, serve/test_server.py::PromptProgressStream::test_asked_for_and_sent (Paced) and serve/test_logprobs.py::LpEngine at 7e68a30f (MIT); license text in console/LICENSES/project-maya-MIT.txt.
//!
//! Doubles that report more than the scripted engine: a clock and cache figures, prompt
//! progress, and made-up logprobs.

use std::sync::Arc;

use console_core::engine::{
    ControlProbe, EngineCounts, EngineEvent, EngineFactory, EngineFailure, EngineInstance,
    EngineKind, EngineStartConfig, EngineStop, EngineTimings, EventSink, PromptProgress, Terminal,
    TokenLogprob,
};

use super::{DoubleHooks, Hooked};
use crate::fake::config::{FakeConfigError, FakeScript};
use crate::fake::deliver::{offer, Offer};
use crate::fake::mock::{Flow, MockFigures, MockHooks, MockParts};
use crate::fake::FakeProbe;

// ---------------------------------------------------------------------------- Clocked

/// The prompt tokens the [`ClockedEngine`]'s conversation cache holds: the first 5 of
/// every prompt (the donor's `ClockedEngine.REUSED`).
pub const CLOCKED_REUSED: u32 = 5;

/// Rust counterpart of the donor's `ClockedEngine` (serve/test_server.py:1869-1882): the
/// scripted engine with the line-protocol engine's clock. Every generation that does not
/// fail, a cancelled one included (the donor sets `last` in a `finally`), ends with the
/// figures a `DONE` line would give: `generated` = the tokens offered (the one at which
/// the consumer left included), `prompt_tokens` = the prompt length, `prompt_ms` 40,
/// `decode_ms` 20 a token, `reused` = the smaller of [`CLOCKED_REUSED`] and the prompt
/// length, `hits` 9 and `lookups` 10, and no draft counts.
#[derive(Debug, Clone)]
pub struct ClockedEngine {
    parts: MockParts,
}

impl ClockedEngine {
    /// The donor's double.
    pub fn new(script: FakeScript) -> Result<Self, FakeConfigError> {
        Ok(Self {
            parts: MockParts::new(script)?,
        })
    }

    /// What the scripted engine recorded (the donor's tests read `last_prompt`).
    pub fn probe(&self) -> FakeProbe {
        FakeProbe::from_shared(Arc::clone(&self.parts.shared))
    }
}

struct ClockedHooks {
    n: u32,
}

impl MockHooks for ClockedHooks {
    fn on_generate(&mut self, _req: &console_core::engine::GenerationRequest) {
        self.n = 0;
    }

    fn on_offered(&mut self, _index: u32) {
        self.n = self.n.saturating_add(1);
    }

    fn terminal(
        &mut self,
        stop: EngineStop,
        _figures: Option<MockFigures>,
        prompt_tokens: u32,
    ) -> Terminal {
        Terminal {
            stop,
            counts: Some(EngineCounts {
                generated: self.n,
                prompt_tokens,
                reused_tokens: Some(CLOCKED_REUSED.min(prompt_tokens)),
                drafts: None,
                hits_lookups: Some((9, 10)),
            }),
            timings: Some(EngineTimings {
                prompt_ms: 40.0,
                decode_ms: 20.0 * f64::from(self.n),
            }),
        }
    }
}

impl DoubleHooks for ClockedHooks {}

impl EngineFactory for ClockedEngine {
    fn kind(&self) -> EngineKind {
        EngineKind::Scripted
    }

    fn start(&self, cfg: &EngineStartConfig) -> Result<Box<dyn EngineInstance>, EngineFailure> {
        let (core, _) = self.parts.start(cfg)?;
        Ok(Box::new(Hooked {
            core,
            hooks: ClockedHooks { n: 0 },
        }))
    }
}

// ------------------------------------------------------------------------------ Paced

/// Rust counterpart of the donor's `Paced` (serve/test_server.py:1150-1157): the scripted
/// engine that reports prompt progress before its answer. By default the donor's two
/// chunks, `(read, total, reuse, ms)` = (4096, 8192, 2048, 251.0) and then
/// (8192, 8192, 2048, 500.0), each delivered as a `PromptProgress` after `Admitted`.
#[derive(Debug, Clone)]
pub struct PacedEngine {
    parts: MockParts,
    progress: Arc<[PromptProgress]>,
}

impl PacedEngine {
    /// The donor's two progress chunks.
    pub fn new(script: FakeScript) -> Result<Self, FakeConfigError> {
        let chunk = |read, ms| PromptProgress {
            read,
            total: 8192,
            reused: 2048,
            ms,
            tok_s: None,
        };
        Self::with_progress(script, vec![chunk(4096, 251.0), chunk(8192, 500.0)])
    }

    /// Other progress events, delivered in order before the answer.
    pub fn with_progress(
        script: FakeScript,
        progress: Vec<PromptProgress>,
    ) -> Result<Self, FakeConfigError> {
        Ok(Self {
            parts: MockParts::new(script)?,
            progress: Arc::from(progress),
        })
    }

    /// What the scripted engine recorded.
    pub fn probe(&self) -> FakeProbe {
        FakeProbe::from_shared(Arc::clone(&self.parts.shared))
    }
}

struct PacedHooks {
    progress: Arc<[PromptProgress]>,
}

impl MockHooks for PacedHooks {
    fn before_steps(
        &mut self,
        _prompt_tokens: u32,
        sink: &mut dyn EventSink,
        control: &ControlProbe,
    ) -> Result<Flow, EngineFailure> {
        for p in self.progress.iter() {
            if offer(sink, control, EngineEvent::PromptProgress(*p)) == Offer::Gone {
                return Ok(Flow::Cancelled);
            }
        }
        Ok(Flow::Go)
    }
}

impl DoubleHooks for PacedHooks {}

impl EngineFactory for PacedEngine {
    fn kind(&self) -> EngineKind {
        EngineKind::Scripted
    }

    fn start(&self, cfg: &EngineStartConfig) -> Result<Box<dyn EngineInstance>, EngineFailure> {
        let (core, _) = self.parts.start(cfg)?;
        Ok(Box::new(Hooked {
            core,
            hooks: PacedHooks {
                progress: Arc::clone(&self.progress),
            },
        }))
    }
}

// --------------------------------------------------------------------------------- Lp

/// Rust counterpart of the donor's `LpEngine` (serve/test_logprobs.py:35-49): the
/// scripted engine with made-up logprobs. When the request asks for `n` alternatives,
/// token `i` of the answer has the logprob `v = -0.1 * (i + 1)` (or `own`, which can be
/// `-inf`: a token the model gave no chance), and its row is the token and then
/// `id + 1, id + 2, ...`, each 1 lower: `[(id + j, v - j) for j in 0..n]`.
#[derive(Debug, Clone)]
pub struct LpEngine {
    parts: MockParts,
    own: Option<f64>,
}

impl LpEngine {
    /// Logprobs `-0.1 * (i + 1)`.
    pub fn new(script: FakeScript) -> Result<Self, FakeConfigError> {
        Ok(Self {
            parts: MockParts::new(script)?,
            own: None,
        })
    }

    /// Every token's own logprob is `own` (the donor's `own=`).
    pub fn with_own(mut self, own: f64) -> Self {
        self.own = Some(own);
        self
    }

    /// What the scripted engine recorded (the donor's `sampling`).
    pub fn probe(&self) -> FakeProbe {
        FakeProbe::from_shared(Arc::clone(&self.parts.shared))
    }
}

struct LpHooks {
    own: Option<f64>,
}

impl MockHooks for LpHooks {
    fn logprob(&mut self, index: u32, id: u32, top: u8) -> TokenLogprob {
        let v = self.own.unwrap_or(-0.1 * (f64::from(index) + 1.0));
        TokenLogprob {
            logprob: v,
            top: (0..top)
                .map(|j| (id.saturating_add(u32::from(j)), v - f64::from(j)))
                .collect(),
        }
    }
}

impl DoubleHooks for LpHooks {}

impl EngineFactory for LpEngine {
    fn kind(&self) -> EngineKind {
        EngineKind::Scripted
    }

    fn start(&self, cfg: &EngineStartConfig) -> Result<Box<dyn EngineInstance>, EngineFailure> {
        let (core, _) = self.parts.start(cfg)?;
        Ok(Box::new(Hooked {
            core,
            hooks: LpHooks { own: self.own },
        }))
    }
}

#[cfg(test)]
mod tests {
    use console_core::engine::ControlHandle;

    use super::*;
    use crate::fake::testutil::{req, run, Collect};

    #[test]
    fn fake_clocked_reports_done_figures_even_when_cancelled() {
        let f = ClockedEngine::new(FakeScript::new(vec![10, 11, 12])).expect("valid");
        let mut e = f.start(&EngineStartConfig::new()).expect("starts");
        let (_, out) = run(e.as_mut(), &req(vec![1, 2, 3, 4, 5, 6, 7], 20));
        let (t, counts) = out.expect("runs");
        assert_eq!(t.stop, EngineStop::Stop { token: None });
        let c = t.counts.expect("figures");
        assert_eq!(
            (
                c.generated,
                c.prompt_tokens,
                c.reused_tokens,
                c.hits_lookups
            ),
            (3, 7, Some(5), Some((9, 10)))
        );
        assert_eq!(c.drafts, None);
        let tm = t.timings.expect("clock");
        assert_eq!((tm.prompt_ms, tm.decode_ms), (40.0, 60.0));
        assert_eq!(counts.reused_tokens, Some(CLOCKED_REUSED));
        // A prompt shorter than the cache: all of it reused.
        let (_, out) = run(e.as_mut(), &req(vec![1, 2], 20));
        assert_eq!(out.expect("runs").1.reused_tokens, Some(2));
        // Closed at the second token (a stop id): both offered tokens are counted.
        let h = ControlHandle::new();
        let mut sink = Collect {
            cancel_after: Some((2, h.clone())),
            ..Collect::default()
        };
        let (t, _) = console_core::engine::generate_ledgered(
            e.as_mut(),
            &req(vec![1; 9], 20),
            &h.probe(),
            &mut sink,
        )
        .expect("runs");
        assert_eq!(t.stop, EngineStop::Cancelled);
        assert_eq!(t.counts.map(|c| c.generated), Some(2));
        assert_eq!(t.timings.map(|t| t.decode_ms), Some(40.0));
        // The consumer leaves at the second token: it was offered, so it counts.
        let mut gone = Collect {
            gone_at: Some(1),
            ..Collect::default()
        };
        let h = ControlHandle::new();
        let (t, counts) = console_core::engine::generate_ledgered(
            e.as_mut(),
            &req(vec![1; 9], 20),
            &h.probe(),
            &mut gone,
        )
        .expect("runs");
        assert_eq!(t.stop, EngineStop::Cancelled);
        assert_eq!(t.counts.map(|c| c.generated), Some(2));
        assert_eq!(counts.completion_tokens, 1);
    }

    #[test]
    fn fake_paced_reports_progress_before_the_answer() {
        let f = PacedEngine::new(FakeScript::new(vec![10, 11])).expect("valid");
        let mut e = f.start(&EngineStartConfig::new()).expect("starts");
        let (sink, out) = run(e.as_mut(), &req(vec![1], 20));
        assert!(out.is_ok());
        let pp: Vec<(u32, u32, u32, f64)> = sink
            .events
            .iter()
            .filter_map(|e| match e {
                EngineEvent::PromptProgress(p) => Some((p.read, p.total, p.reused, p.ms)),
                _ => None,
            })
            .collect();
        assert_eq!(
            pp,
            vec![(4096, 8192, 2048, 251.0), (8192, 8192, 2048, 500.0)]
        );
        assert!(matches!(
            sink.events.first(),
            Some(EngineEvent::Admitted { .. })
        ));
        assert!(matches!(sink.events.get(3), Some(EngineEvent::Token(_))));
        assert_eq!(sink.tokens(), vec![10, 11]);
    }

    #[test]
    fn fake_lp_engine_makes_up_its_logprobs() {
        let f = LpEngine::new(FakeScript::new(vec![72, 105, 33])).expect("valid");
        let mut e = f.start(&EngineStartConfig::new()).expect("starts");
        let mut r = req(vec![1], 20);
        r.logprobs = Some(2);
        let (sink, out) = run(e.as_mut(), &r);
        assert!(out.is_ok());
        let lps = sink.logprobs();
        let first = lps[0].clone().expect("asked");
        assert_eq!(first.logprob, -0.1);
        assert_eq!(first.top, vec![(72, -0.1), (73, -0.1 - 1.0)]);
        let third = lps[2].clone().expect("asked");
        assert_eq!(third.logprob, -0.1 * 3.0);
        assert_eq!(third.top[1], (34, -0.1 * 3.0 - 1.0));
        // Not asked: plain tokens.
        let (sink, _) = run(e.as_mut(), &req(vec![1], 20));
        assert!(sink.logprobs().iter().all(Option::is_none));
        // own = -inf, no alternatives.
        let f = LpEngine::new(FakeScript::new(vec![9]))
            .expect("valid")
            .with_own(f64::NEG_INFINITY);
        let mut e = f.start(&EngineStartConfig::new()).expect("starts");
        let mut r = req(vec![1], 20);
        r.logprobs = Some(0);
        let (sink, _) = run(e.as_mut(), &r);
        let lp = sink.logprobs()[0].clone().expect("asked");
        assert_eq!(lp.logprob, f64::NEG_INFINITY);
        assert!(lp.top.is_empty());
    }
}
