//! The core of the scripted engine (the donor's `MockEngine.generate`), with the hooks
//! its doubles use to change one step of it, as the donor's subclasses wrap the
//! generator.

use std::sync::{Arc, Mutex};

use console_core::engine::{
    ControlProbe, EmbeddingsRef, EngineCounts, EngineDescriptor, EngineFailure, EngineKind,
    EngineStartConfig, EngineStop, EngineTimings, EventSink, GenerationRequest, InfoMap, InfoValue,
    Provenance, Terminal, TokenLogprob,
};

use super::clock::FakeClock;
use super::config::{py_sleep, FakeConfig, FakeConfigError, FakeScript};
use super::deliver::{admitted, certain_logprob, offer, prompt_tokens, token, Offer};
use super::{lock, TOP_LOGPROBS_MAX};

/// The sleep, in seconds, before the scripted engine writes `token` on its `run`-th
/// generation at `tok_s` tokens a second: the donor's deterministic jitter,
/// `(0.8 + 0.4 * ((t * 7919 + runs * 104729) % 101) / 100) / tok_s`, in the same order of
/// floating-point operations. `run` counts from 1.
///
/// Behavior reference: project-maya serve/server.py:232-233 at 7e68a30f.
pub fn jitter_sleep_s(token: u32, run: u64, tok_s: f64) -> f64 {
    let k = (u128::from(token) * 7919 + u128::from(run) * 104_729) % 101;
    // k < 101, so the conversion is exact.
    let k = f64::from(u8::try_from(k).unwrap_or(u8::MAX));
    (0.8 + 0.4 * k / 100.0) / tok_s
}

/// State shared by every instance one factory starts, and read by its probe: the script
/// rotation and run count survive a restart, as they live on the donor's engine object.
#[derive(Debug, Default)]
pub(crate) struct MockShared {
    pub(crate) turns: usize,
    pub(crate) runs: u64,
    pub(crate) starts: u64,
    pub(crate) generations: u64,
    pub(crate) context: Option<u32>,
    pub(crate) max_context_override: Option<u32>,
    pub(crate) last_prompt: Option<Arc<[u32]>>,
    pub(crate) last_request: Option<GenerationRequest>,
}

/// The settings and shared state of one scripted engine.
#[derive(Debug, Clone)]
pub(crate) struct MockParts {
    pub(crate) cfg: Arc<FakeConfig>,
    pub(crate) shared: Arc<Mutex<MockShared>>,
}

/// The descriptor of the scripted engine: synthetic provenance (LD28), the given context,
/// and the donor's `info`, `{"logit_bias": 1, "logprobs": 20}`. It samples nothing, so a
/// bias is as good as applied, and its tokens are certain. A context reload is supported
/// (by a restart with the new context, FIX-1.1).
///
/// Behavior reference: project-maya serve/server.py:214-216 at 7e68a30f.
pub(crate) fn mock_descriptor(max_context: u32) -> EngineDescriptor {
    let mut d = EngineDescriptor::new(EngineKind::Scripted, Provenance::Synthetic);
    d.max_context = max_context;
    let mut info = InfoMap::new();
    // Two short entries in an empty map: within every limit.
    let _ = info.try_insert("logit_bias", InfoValue::Int(1));
    let _ = info.try_insert("logprobs", InfoValue::Int(i64::from(TOP_LOGPROBS_MAX)));
    d.caps.apply_info(&info);
    d.info = info;
    d.caps.lifecycle.set_context = true;
    d
}

impl MockParts {
    pub(crate) fn new(script: FakeScript) -> Result<Self, FakeConfigError> {
        Ok(Self {
            cfg: Arc::new(script.into_config()?),
            shared: Arc::new(Mutex::new(MockShared::default())),
        })
    }

    /// The clock.
    pub(crate) fn clock(&self) -> &dyn FakeClock {
        self.cfg.clock.as_ref()
    }

    /// Starts one instance. A start with a context that differs from the context the
    /// factory reports now, after an earlier start, is a context reload: it takes the
    /// reload delay and then reports the new context, as the donor's `_restart_with` does
    /// for the mock engine. Any other start is a restart (after a death or an idle unload,
    /// the donor's `restart()`): it does not sleep, and a start without a context keeps the
    /// last context a start was given (a restart keeps the reloaded context). A reload
    /// whose delay cannot be slept (a bad [`RELOAD_DELAY_ENV`](super::RELOAD_DELAY_ENV)
    /// value, read now as the donor reads it at each reload) fails that start, with the
    /// error's text, and changes nothing. Returns the core and whether this was the first
    /// start.
    ///
    /// Behavior reference: project-maya serve/server.py:2654, 2765-2772 at 7e68a30f.
    pub(crate) fn start(
        &self,
        start: &EngineStartConfig,
    ) -> Result<(MockCore, bool), EngineFailure> {
        let reload = {
            let s = lock(&self.shared);
            let now = s.context.unwrap_or(self.cfg.max_context);
            s.starts > 0 && start.context.is_some_and(|c| c != now)
        };
        if reload {
            let d = self
                .cfg
                .reload_delay
                .resolve()
                .map_err(|e| EngineFailure::reported(&e.to_string()))?;
            self.clock().sleep(d);
        }
        let (ctx, first) = {
            let mut s = lock(&self.shared);
            let first = s.starts == 0;
            s.starts = s.starts.saturating_add(1);
            if start.context.is_some() {
                s.context = start.context;
            }
            (s.context.unwrap_or(self.cfg.max_context), first)
        };
        let core = MockCore {
            parts: self.clone(),
            base_context: ctx,
            desc: mock_descriptor(ctx),
        };
        Ok((core, first))
    }
}

/// The scripted engine's own figures, published just before its last token when it is
/// paced by `tok_s` (the donor's `last`).
#[derive(Debug, Clone, Copy, PartialEq)]
pub(crate) struct MockFigures {
    pub(crate) generated: u32,
    pub(crate) decode_ms: f64,
    pub(crate) prompt_ms: f64,
}

/// Whether a generation goes on after a hook.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum Flow {
    Go,
    Cancelled,
}

/// The default terminal of the scripted engine: no figures unless paced by `tok_s`, and
/// then `generated`, `prompt_ms`, `decode_ms` and `reused` 0 as the donor's `last` holds
/// them. The donor's `last` has no `prompt_tokens`; the prompt length is put there (the
/// field is informational, contract section 14, Q4).
pub(crate) fn mock_terminal(
    stop: EngineStop,
    figures: Option<MockFigures>,
    prompt_tokens: u32,
) -> Terminal {
    match figures {
        None => Terminal::bare(stop),
        Some(f) => Terminal {
            stop,
            counts: Some(EngineCounts {
                generated: f.generated,
                prompt_tokens,
                reused_tokens: Some(0),
                drafts: None,
                hits_lookups: None,
            }),
            timings: Some(EngineTimings {
                prompt_ms: f.prompt_ms,
                decode_ms: f.decode_ms,
            }),
        },
    }
}

/// The places where a double changes the scripted engine's generation. Every method has
/// the scripted engine's own behavior as its default.
pub(crate) trait MockHooks {
    /// At the start of a generation the engine accepted, before anything is delivered.
    fn on_generate(&mut self, _req: &GenerationRequest) {}

    /// After `Admitted`, before the first step (the donor's `yield None` heartbeats and
    /// `progress` before the mock's generator).
    fn before_steps(
        &mut self,
        _prompt_tokens: u32,
        _sink: &mut dyn EventSink,
        _control: &ControlProbe,
    ) -> Result<Flow, EngineFailure> {
        Ok(Flow::Go)
    }

    /// After the step's cancel check and pacing, before its token is delivered (where the
    /// donor's subclasses raise inside their loop over the mock's tokens).
    fn at_step(&mut self, _index: u32, _id: u32) -> Result<(), EngineFailure> {
        Ok(())
    }

    /// The logprob of a token when the request asks for `top` alternatives.
    fn logprob(&mut self, _index: u32, id: u32, top: u8) -> TokenLogprob {
        certain_logprob(id, top)
    }

    /// Just before a token is offered (a count that includes the token at which the
    /// consumer leaves, as the donor's `n += 1` before `yield` does).
    fn on_offered(&mut self, _index: u32) {}

    /// The terminal of a generation that did not fail.
    fn terminal(
        &mut self,
        stop: EngineStop,
        figures: Option<MockFigures>,
        prompt_tokens: u32,
    ) -> Terminal {
        mock_terminal(stop, figures, prompt_tokens)
    }
}

/// The scripted engine's hooks: all defaults.
pub(crate) struct NoHooks;

impl MockHooks for NoHooks {}

/// One started scripted engine.
#[derive(Debug)]
pub(crate) struct MockCore {
    pub(crate) parts: MockParts,
    base_context: u32,
    pub(crate) desc: EngineDescriptor,
}

impl MockCore {
    /// Applies a context set through the probe (the donor's tests assign
    /// `engine.max_context`); called from every `&mut self` method of the instance.
    pub(crate) fn refresh(&mut self) {
        let over = lock(&self.parts.shared).max_context_override;
        self.desc.max_context = over.unwrap_or(self.base_context);
    }

    /// Records the request as the donor's `last_prompt` and `last_embeddings` (and the
    /// whole request, for the recording doubles).
    pub(crate) fn record(&self, req: &GenerationRequest) {
        let mut s = lock(&self.parts.shared);
        s.generations = s.generations.saturating_add(1);
        s.last_prompt = Some(Arc::clone(&req.prompt));
        s.last_request = Some(req.clone());
    }

    /// The donor's `MockEngine.generate` behind the seam: records the request, takes the
    /// next script (the last one repeats), cuts it to `max_new`, delivers `Admitted`, then
    /// for each token checks cancel, sleeps `delay` and the `tok_s` jitter, publishes its
    /// figures just before the last token when paced, and delivers the token, with the
    /// logprob `(0.0, [(id, 0.0)])` (or `(0.0, [])` for no alternatives) when asked.
    /// A cancel stops it at once with `Cancelled`; a cut script ends with `Length`, a whole
    /// one with `Stop`. Pause and wrap requests are not read: the donor's mock engine has
    /// neither.
    ///
    /// Behavior reference: project-maya serve/server.py:218-240 at 7e68a30f.
    pub(crate) fn run(
        &mut self,
        req: &GenerationRequest,
        control: &ControlProbe,
        sink: &mut dyn EventSink,
        hooks: &mut dyn MockHooks,
    ) -> Result<Terminal, EngineFailure> {
        self.refresh();
        if self.desc.is_starting() {
            return Err(EngineFailure::not_ready());
        }
        let n_prompt = prompt_tokens(&req.prompt)?;
        self.record(req);
        hooks.on_generate(req);
        let cfg = Arc::clone(&self.parts.cfg);
        let (script, run) = {
            let mut s = lock(&self.parts.shared);
            let idx = if cfg.scripts.len() > 1 {
                let i = s.turns.min(cfg.scripts.len() - 1);
                s.turns = s.turns.saturating_add(1);
                i
            } else {
                0
            };
            s.runs = s.runs.saturating_add(1);
            (cfg.scripts.get(idx).cloned(), s.runs)
        };
        let script = script.unwrap_or_else(|| Arc::from(Vec::new()));
        let clock = cfg.clock.as_ref();
        let t0 = clock.now();
        let cut = script
            .len()
            .min(usize::try_from(req.max_new).unwrap_or(usize::MAX));
        let steps = script.get(..cut).unwrap_or(&[]);
        let length = script.len() > cut;
        let mut figures = None;

        if offer(sink, control, admitted(n_prompt)) == Offer::Gone {
            return Ok(hooks.terminal(EngineStop::Cancelled, figures, n_prompt));
        }
        if hooks.before_steps(n_prompt, sink, control)? == Flow::Cancelled {
            return Ok(hooks.terminal(EngineStop::Cancelled, figures, n_prompt));
        }
        for (i, &t) in steps.iter().enumerate() {
            // i < max_new, a u32.
            let index = u32::try_from(i).unwrap_or(u32::MAX);
            if control.is_cancelled() {
                return Ok(hooks.terminal(EngineStop::Cancelled, figures, n_prompt));
            }
            if !cfg.delay.is_zero() {
                clock.sleep(cfg.delay);
            }
            if let Some(tok_s) = cfg.tok_s {
                // A sleep `time.sleep` refuses fails the generation here, as the donor's
                // generator raises at its first paced token; never an unbounded sleep.
                let s = jitter_sleep_s(t, run, tok_s);
                clock.sleep(py_sleep(s).map_err(EngineFailure::reported)?);
                if i + 1 == steps.len() {
                    // Its DONE, before the last token: the server stops there.
                    figures = Some(MockFigures {
                        generated: index.saturating_add(1),
                        decode_ms: clock.now().saturating_sub(t0).as_secs_f64() * 1000.0,
                        prompt_ms: f64::from(n_prompt) * 0.5,
                    });
                }
            }
            hooks.at_step(index, t)?;
            let logprob = req.logprobs.map(|top| hooks.logprob(index, t, top));
            hooks.on_offered(index);
            if offer(sink, control, token(n_prompt, index, t, logprob)) == Offer::Gone {
                return Ok(hooks.terminal(EngineStop::Cancelled, figures, n_prompt));
            }
        }
        let stop = if length {
            EngineStop::Length
        } else {
            EngineStop::Stop { token: None }
        };
        Ok(hooks.terminal(stop, figures, n_prompt))
    }
}

/// The last request's picture data, for the probe.
pub(crate) fn last_embeddings(s: &MockShared) -> Option<EmbeddingsRef> {
    s.last_request.as_ref().and_then(|r| r.embeddings.clone())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fake_jitter_matches_the_donor_formula() {
        // Python: (0.8 + 0.4 * ((72 * 7919 + 1 * 104729) % 101) / 100) / 10
        // (72 * 7919 + 104729) % 101 == 674897 % 101 == 15.
        assert_eq!((72u64 * 7919 + 104_729) % 101, 15);
        assert_eq!(
            jitter_sleep_s(72, 1, 10.0),
            (0.8 + 0.4 * 15.0 / 100.0) / 10.0
        );
        // The spread stays within 0.8 to 1.2 of the nominal step (1.2 itself comes out
        // as 1.2000000000000002, as it does in Python).
        for t in [0u32, 1, 255, 65_535, u32::MAX] {
            for run in [1u64, 2, 1000, u64::MAX] {
                let s = jitter_sleep_s(t, run, 1.0);
                assert!((0.8..=1.2 + 1e-12).contains(&s), "{t} {run} {s}");
            }
        }
        // Large ids and run counts do not overflow: the donor's integers are unbounded.
        let k = (u128::from(u32::MAX) * 7919 + u128::from(u64::MAX) * 104_729) % 101;
        let want = (0.8 + 0.4 * (k as f64) / 100.0) / 4.0;
        assert_eq!(jitter_sleep_s(u32::MAX, u64::MAX, 4.0), want);
    }

    #[test]
    fn fake_descriptor_is_synthetic_with_the_donor_info() {
        let d = mock_descriptor(4096);
        assert_eq!(d.provenance, Provenance::Synthetic);
        assert_eq!(d.kind, EngineKind::Scripted);
        assert_eq!(d.max_context, 4096);
        assert!(d.caps.logit_bias);
        assert_eq!(d.caps.logprobs_max, Some(20));
        assert!(!d.caps.stop && !d.caps.pause && d.caps.multi.is_none());
        let info: Vec<_> = d
            .info
            .iter()
            .map(|(k, v)| (k.to_owned(), v.clone()))
            .collect();
        assert_eq!(
            info,
            vec![
                ("logit_bias".to_owned(), InfoValue::Int(1)),
                ("logprobs".to_owned(), InfoValue::Int(20)),
            ]
        );
        assert!(console_core::engine::require_synthetic(&d).is_ok());
    }
}
