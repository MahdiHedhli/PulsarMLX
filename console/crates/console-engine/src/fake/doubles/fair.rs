//! Provenance: translated from project-maya serve/test_fair.py::ResumingEngine and serve/test_fair.py::PausingEngine at 7e68a30f (MIT); license text in console/LICENSES/project-maya-MIT.txt.
//!
//! The doubles of the fair-slice tests: an engine that continues an answer from wherever
//! the prompt says it got to, as the real engine does with its conversation slots, and
//! its variant that honors a pause a few tokens late. With more than one place they offer
//! the submit-and-pump form (contract section 4.1), as the donor's runs them from several
//! threads at once.

use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use console_core::engine::{
    ControlProbe, DeliveryRefused, EngineCounts, EngineDescriptor, EngineEvent, EngineFactory,
    EngineFailure, EngineInstance, EngineKind, EngineStartConfig, EngineStop, EngineTimings,
    EventSink, Finished, GenerationRequest, Health, InfoMap, MultiEngine, RequestId,
    ShutdownOutcome, TaggedSink, Terminal,
};

use crate::fake::clock::FakeClock;
use crate::fake::config::{FakeConfigError, FakeScript, MAX_SCRIPTS, MAX_SCRIPT_TOKENS};
use crate::fake::deliver::{admitted, prompt_tokens, token, BACKPRESSURE_PAUSE};
use crate::fake::lock;
use crate::fake::mock::{MockCore, MockParts};

/// The donor's `ResumingEngine` sleep before each token: 2 ms.
pub const RESUMING_DEFAULT_DELAY: Duration = Duration::from_millis(2);

/// The tokens a [`PausingEngine`] still writes once it sees a pause, the one in flight
/// included (the donor's `PausingEngine.LATE`).
pub const PAUSE_LATE_TOKENS: u32 = 3;

/// The most distinct conversations (first prompts) a resuming engine remembers.
const MAX_BASES: usize = 4096;

/// The most calls a resuming engine records; later ones are not recorded.
const MAX_CALLS: usize = 65_536;

#[derive(Debug)]
struct ResumeState {
    answers: Vec<(Vec<u32>, Vec<u32>)>,
    end: Vec<u32>,
    bases: Vec<Arc<[u32]>>,
    calls: Vec<(Vec<u32>, u32)>,
    pauses: u64,
}

/// True when `key` occurs in `base` as a contiguous run (the donor's `k in text` on the
/// decoded first prompt); an empty key occurs everywhere.
fn contains(base: &[u32], key: &[u32]) -> bool {
    key.is_empty() || base.windows(key.len()).any(|w| w == key)
}

/// Rust counterpart of the donor's `ResumingEngine` (serve/test_fair.py:24-49): each
/// conversation's answer is the answer whose key its first prompt contains (keys and
/// answers already encoded; the key is matched as a contiguous run of ids, where the
/// donor matches text in the decoded prompt), followed by the end-of-turn ids; a later
/// prompt that extends a first prompt (the prompt plus what was already written) gets the
/// rest of the same answer, cut to `max_new`. It checks cancel and sleeps `delay` (2 ms by
/// default) before each token, and records every call's prompt and `max_new` and every
/// first prompt (the donor's `calls` and `bases`). A prompt that no key matches is a
/// failure (the donor's generator raises). With [`places`](Self::places) above 1 it
/// offers the submit-and-pump form.
#[derive(Debug, Clone)]
pub struct ResumingEngine {
    parts: MockParts,
    state: Arc<Mutex<ResumeState>>,
    delay: Duration,
    places: u32,
    pausing: bool,
}

/// Rust counterpart of the donor's `PausingEngine` (serve/test_fair.py:52-74): a
/// [`ResumingEngine`] that advertises pause and, once it sees a pause request, still
/// writes [`PAUSE_LATE_TOKENS`] tokens (the ones already on their way) and then ends as
/// `Paused`. Its figures are the donor's `last`, `generated` 0 and both times 0, on every
/// end but a consumer that left; the donor sets no `prompt_tokens`, so it is 0 here. The
/// donor's `pauses` counts `pause()` calls; here it counts generations that saw a pause
/// request, since the request reaches the engine through its control probe. Like the
/// donor's double, it reports no `info`.
#[derive(Debug, Clone)]
pub struct PausingEngine(ResumingEngine);

impl PausingEngine {
    /// `answers` as `(key, answer)` pairs in order (the first match wins) and the
    /// end-of-turn ids, with the scripted engine's default settings; it pauses.
    pub fn new(answers: Vec<(Vec<u32>, Vec<u32>)>, end: Vec<u32>) -> Result<Self, FakeConfigError> {
        Ok(Self(ResumingEngine::new(answers, end)?.with_pause()))
    }

    /// As [`new`](Self::new), with the context and clock of `settings` (its scripts are
    /// not used).
    pub fn with_settings(
        answers: Vec<(Vec<u32>, Vec<u32>)>,
        end: Vec<u32>,
        settings: FakeScript,
    ) -> Result<Self, FakeConfigError> {
        Ok(Self(
            ResumingEngine::with_settings(answers, end, settings)?.with_pause(),
        ))
    }

    /// The sleep before each token (the donor's `delay_s`).
    pub fn delay(self, d: Duration) -> Self {
        Self(self.0.delay(d))
    }

    /// Runs `n` generations at once through the submit-and-pump form (`multi=<n>`); 1 is
    /// a single-conversation engine.
    pub fn places(self, n: u32) -> Self {
        Self(self.0.places(n))
    }

    /// Sets the answer of `key`, in place when the key is present, else last.
    pub fn set_answer(&self, key: Vec<u32>, answer: Vec<u32>) {
        self.0.set_answer(key, answer);
    }

    /// Every call's prompt and `max_new`, in order (the donor's `calls`).
    pub fn calls(&self) -> Vec<(Vec<u32>, u32)> {
        self.0.calls()
    }

    /// The first prompt of each conversation, in order (the donor's `bases`).
    pub fn bases(&self) -> Vec<Vec<u32>> {
        self.0.bases()
    }

    /// Generations that saw a pause request (the donor's `pauses`; see the type).
    pub fn pauses(&self) -> u64 {
        lock(&self.0.state).pauses
    }
}

impl EngineFactory for PausingEngine {
    fn kind(&self) -> EngineKind {
        self.0.kind()
    }

    fn start(&self, cfg: &EngineStartConfig) -> Result<Box<dyn EngineInstance>, EngineFailure> {
        self.0.start(cfg)
    }
}

impl ResumingEngine {
    /// `answers` as `(key, answer)` pairs in order (the first match wins) and the
    /// end-of-turn ids, with the scripted engine's default settings.
    pub fn new(answers: Vec<(Vec<u32>, Vec<u32>)>, end: Vec<u32>) -> Result<Self, FakeConfigError> {
        Self::with_settings(answers, end, FakeScript::new(Vec::new()))
    }

    /// As [`new`](Self::new), with the context and clock of `settings` (its scripts are
    /// not used).
    pub fn with_settings(
        answers: Vec<(Vec<u32>, Vec<u32>)>,
        end: Vec<u32>,
        settings: FakeScript,
    ) -> Result<Self, FakeConfigError> {
        if answers.len() > MAX_SCRIPTS {
            return Err(FakeConfigError::TooManyScripts {
                count: answers.len(),
            });
        }
        for (index, (key, answer)) in answers.iter().enumerate() {
            let len = key.len().max(answer.len().saturating_add(end.len()));
            if len > MAX_SCRIPT_TOKENS {
                return Err(FakeConfigError::ScriptTooLong { index, len });
            }
        }
        Ok(Self {
            parts: MockParts::new(settings)?,
            state: Arc::new(Mutex::new(ResumeState {
                answers,
                end,
                bases: Vec::new(),
                calls: Vec::new(),
                pauses: 0,
            })),
            delay: RESUMING_DEFAULT_DELAY,
            places: 1,
            pausing: false,
        })
    }

    /// The [`PausingEngine`] of these answers (the same as [`PausingEngine::new`]).
    pub fn pausing(
        answers: Vec<(Vec<u32>, Vec<u32>)>,
        end: Vec<u32>,
    ) -> Result<PausingEngine, FakeConfigError> {
        PausingEngine::new(answers, end)
    }

    /// Advertises pause and honors it [`PAUSE_LATE_TOKENS`] late: only a
    /// [`PausingEngine`] does.
    fn with_pause(mut self) -> Self {
        self.pausing = true;
        self
    }

    /// The sleep before each token (the donor's `delay_s`).
    pub fn delay(mut self, d: Duration) -> Self {
        self.delay = d;
        self
    }

    /// Runs `n` generations at once through the submit-and-pump form (`multi=<n>`); 1 is
    /// a single-conversation engine.
    pub fn places(mut self, n: u32) -> Self {
        self.places = n.max(1);
        self
    }

    /// Sets the answer of `key`, in place when the key is present, else last (the donor's
    /// tests assign `engine.answers[key]`).
    pub fn set_answer(&self, key: Vec<u32>, answer: Vec<u32>) {
        let mut s = lock(&self.state);
        if let Some(slot) = s.answers.iter_mut().find(|(k, _)| *k == key) {
            slot.1 = answer;
        } else if s.answers.len() < MAX_SCRIPTS {
            s.answers.push((key, answer));
        }
    }

    /// Every call's prompt and `max_new`, in order (the donor's `calls`).
    pub fn calls(&self) -> Vec<(Vec<u32>, u32)> {
        lock(&self.state).calls.clone()
    }

    /// The first prompt of each conversation, in order (the donor's `bases`).
    pub fn bases(&self) -> Vec<Vec<u32>> {
        lock(&self.state).bases.iter().map(|b| b.to_vec()).collect()
    }

    /// Plans one generation of `req`.
    fn plan(&self, req: &GenerationRequest, control: ControlProbe) -> Result<Gen, EngineFailure> {
        let n_prompt = prompt_tokens(&req.prompt)?;
        let mut s = lock(&self.state);
        if s.calls.len() < MAX_CALLS {
            s.calls.push((req.prompt.to_vec(), req.max_new));
        }
        let base = match s.bases.iter().find(|b| req.prompt.starts_with(b)) {
            Some(b) => Arc::clone(b),
            None => {
                if s.bases.len() >= MAX_BASES {
                    return Err(EngineFailure::unsupported(
                        "more conversations than the resuming engine remembers",
                    ));
                }
                let b: Arc<[u32]> = Arc::clone(&req.prompt);
                s.bases.push(Arc::clone(&b));
                b
            }
        };
        let Some((_, answer)) = s.answers.iter().find(|(k, _)| contains(&base, k)) else {
            return Err(EngineFailure::reported(
                "no scripted answer matches the conversation's first prompt",
            ));
        };
        let script: Vec<u32> = answer.iter().chain(s.end.iter()).copied().collect();
        drop(s);
        let start = req.prompt.len().saturating_sub(base.len());
        let rest = script.get(start..).unwrap_or(&[]);
        let max_new = usize::try_from(req.max_new).unwrap_or(usize::MAX);
        let steps = rest.get(..rest.len().min(max_new)).unwrap_or(&[]).to_vec();
        Ok(Gen {
            rid: req.rid,
            n_prompt,
            length: rest.len() > max_new,
            steps,
            next: 0,
            control,
            admitted: false,
            pending: None,
            late: None,
            saw_pause: false,
            pausing: self.pausing,
        })
    }
}

/// One planned generation, advanced one step at a time.
struct Gen {
    rid: RequestId,
    n_prompt: u32,
    steps: Vec<u32>,
    length: bool,
    next: usize,
    control: ControlProbe,
    admitted: bool,
    pending: Option<EngineEvent>,
    late: Option<u32>,
    saw_pause: bool,
    pausing: bool,
}

enum StepOut {
    Continue,
    Held,
    Done(Terminal),
}

impl Gen {
    /// The terminal for `stop`: bare for the resuming engine; for the pausing engine, the
    /// donor's `last` unless the consumer left (its generator was closed at a `yield`).
    fn terminal(&self, stop: EngineStop, consumer_left: bool) -> Terminal {
        if !self.pausing || consumer_left {
            return Terminal::bare(stop);
        }
        Terminal {
            stop,
            counts: Some(EngineCounts {
                generated: 0,
                prompt_tokens: 0,
                reused_tokens: None,
                drafts: None,
                hits_lookups: None,
            }),
            timings: Some(EngineTimings {
                prompt_ms: 0.0,
                decode_ms: 0.0,
            }),
        }
    }

    fn send(
        &mut self,
        event: EngineEvent,
        deliver: &mut dyn FnMut(EngineEvent) -> Result<(), DeliveryRefused>,
    ) -> StepOut {
        let is_token = matches!(event, EngineEvent::Token(_));
        match deliver(event.clone()) {
            Ok(()) => {
                if is_token {
                    self.next += 1;
                } else {
                    self.admitted = true;
                }
                StepOut::Continue
            }
            Err(DeliveryRefused::ConsumerGone) => {
                StepOut::Done(self.terminal(EngineStop::Cancelled, true))
            }
            Err(DeliveryRefused::Backpressure) => {
                if self.control.is_cancelled() {
                    return StepOut::Done(self.terminal(EngineStop::Cancelled, true));
                }
                self.pending = Some(event);
                StepOut::Held
            }
        }
    }

    /// One step: `Admitted`, or one token (a pending one first), or the end. `sleep` is
    /// false in the pump form, where the pump sleeps once for every running generation.
    fn step(
        &mut self,
        deliver: &mut dyn FnMut(EngineEvent) -> Result<(), DeliveryRefused>,
        clock: &dyn FakeClock,
        delay: Duration,
        sleep: bool,
        state: &Mutex<ResumeState>,
    ) -> StepOut {
        if let Some(ev) = self.pending.take() {
            return self.send(ev, deliver);
        }
        if !self.admitted {
            return self.send(admitted(self.n_prompt), deliver);
        }
        let Some(&id) = self.steps.get(self.next) else {
            let stop = if self.length {
                EngineStop::Length
            } else {
                EngineStop::Stop { token: None }
            };
            return StepOut::Done(self.terminal(stop, false));
        };
        if self.control.is_cancelled() {
            return StepOut::Done(self.terminal(EngineStop::Cancelled, false));
        }
        if sleep && !delay.is_zero() {
            clock.sleep(delay);
        }
        if self.pausing && self.control.pause_requested().is_some() {
            if !self.saw_pause {
                self.saw_pause = true;
                let mut s = lock(state);
                s.pauses = s.pauses.saturating_add(1);
            }
            let late = self.late.map_or(PAUSE_LATE_TOKENS, |l| l.saturating_sub(1));
            self.late = Some(late);
            if late == 0 {
                return StepOut::Done(self.terminal(EngineStop::Paused, false));
            }
        }
        let index = u32::try_from(self.next).unwrap_or(u32::MAX);
        self.send(token(self.n_prompt, index, id, None), deliver)
    }
}

impl EngineFactory for ResumingEngine {
    fn kind(&self) -> EngineKind {
        EngineKind::Scripted
    }

    fn start(&self, cfg: &EngineStartConfig) -> Result<Box<dyn EngineInstance>, EngineFailure> {
        let (mut core, _) = self.parts.start(cfg)?;
        // The donor's doubles are plain classes, not mock engines: no `info`, so neither
        // a logit bias nor logprobs is offered (the donor's server refuses both with them).
        core.desc.info = InfoMap::new();
        core.desc.caps.logit_bias = false;
        core.desc.caps.logprobs_max = None;
        core.desc.caps.pause = self.pausing;
        if self.places > 1 {
            core.desc.caps.multi = Some(self.places);
        }
        Ok(Box::new(ResumeInstance {
            core,
            engine: self.clone(),
            gens: Vec::new(),
            due: None,
        }))
    }
}

struct ResumeInstance {
    core: MockCore,
    engine: ResumingEngine,
    gens: Vec<Gen>,
    /// In the pump form, the clock time at which the next step is due (the delay after
    /// the last step); `None` until a pump finds generations running.
    due: Option<Duration>,
}

impl ResumeInstance {
    fn ready(&mut self) -> Result<(), EngineFailure> {
        self.core.refresh();
        if self.core.desc.is_starting() {
            return Err(EngineFailure::not_ready());
        }
        Ok(())
    }
}

impl EngineInstance for ResumeInstance {
    fn descriptor(&self) -> &EngineDescriptor {
        &self.core.desc
    }

    fn generate(
        &mut self,
        req: &GenerationRequest,
        control: &ControlProbe,
        sink: &mut dyn EventSink,
    ) -> Result<Terminal, EngineFailure> {
        self.ready()?;
        if !self.gens.is_empty() {
            return Err(EngineFailure::unsupported(
                "a blocking generation while other generations run",
            ));
        }
        let mut g = self.engine.plan(req, control.clone())?;
        let clock = Arc::clone(&self.core.parts.cfg.clock);
        let mut deliver = |e: EngineEvent| sink.deliver(e);
        loop {
            match g.step(
                &mut deliver,
                clock.as_ref(),
                self.engine.delay,
                true,
                &self.engine.state,
            ) {
                StepOut::Continue => {}
                StepOut::Held => std::thread::sleep(BACKPRESSURE_PAUSE),
                StepOut::Done(t) => return Ok(t),
            }
        }
    }

    fn multi(&mut self) -> Option<&mut dyn MultiEngine> {
        if self.engine.places > 1 {
            Some(self)
        } else {
            None
        }
    }

    fn health(&mut self) -> Health {
        self.core.refresh();
        Health::Alive
    }

    fn shutdown(self: Box<Self>, _deadline: Instant) -> ShutdownOutcome {
        ShutdownOutcome::Graceful
    }
}

impl MultiEngine for ResumeInstance {
    fn submit(
        &mut self,
        req: &GenerationRequest,
        control: ControlProbe,
    ) -> Result<(), EngineFailure> {
        self.ready()?;
        if self.gens.iter().any(|g| g.rid == req.rid) {
            return Err(EngineFailure::protocol(&format!(
                "request id {} is already running",
                req.rid
            )));
        }
        if self.gens.len() >= usize::try_from(self.engine.places).unwrap_or(usize::MAX) {
            return Err(EngineFailure::unsupported(
                "a generation beyond the engine's places",
            ));
        }
        let g = self.engine.plan(req, control)?;
        self.gens.push(g);
        Ok(())
    }

    /// Advances every running generation by one step once the delay has passed since
    /// the last step (since the first pump, for the first step), sleeping for it once
    /// for all of them. Waits at most `wait` (rule 2): when the step is not due within
    /// it, sleeps `wait` and returns with nothing advanced; a later pump goes on from
    /// there.
    fn pump(
        &mut self,
        sink: &mut dyn TaggedSink,
        wait: Duration,
    ) -> Result<Vec<Finished>, EngineFailure> {
        if self.gens.is_empty() {
            self.due = None;
            return Ok(Vec::new());
        }
        let clock = Arc::clone(&self.core.parts.cfg.clock);
        let delay = self.engine.delay;
        if !delay.is_zero() {
            let now = clock.now();
            let due = *self.due.get_or_insert_with(|| now.saturating_add(delay));
            if now < due {
                let nap = due.saturating_sub(now).min(wait);
                if !nap.is_zero() {
                    clock.sleep(nap);
                }
                if clock.now() < due {
                    return Ok(Vec::new());
                }
            }
            self.due = Some(clock.now().saturating_add(delay));
        }
        let mut finished = Vec::new();
        let mut i = 0;
        while let Some(g) = self.gens.get_mut(i) {
            let rid = g.rid;
            let mut deliver = |e: EngineEvent| sink.deliver(rid, e);
            match g.step(
                &mut deliver,
                clock.as_ref(),
                self.engine.delay,
                false,
                &self.engine.state,
            ) {
                StepOut::Continue | StepOut::Held => i += 1,
                StepOut::Done(t) => {
                    self.gens.remove(i);
                    finished.push(Finished {
                        rid,
                        outcome: Ok(t),
                    });
                }
            }
        }
        Ok(finished)
    }

    fn running(&self) -> usize {
        self.gens.len()
    }
}

#[cfg(test)]
mod tests {
    use console_core::engine::{ControlHandle, FailureKind};

    use super::*;
    use crate::fake::testutil::{req, run, Collect};

    const END: u32 = 999;

    fn answers() -> Vec<(Vec<u32>, Vec<u32>)> {
        vec![(vec![7, 7], (100..130).collect()), (vec![8], vec![1, 2, 3])]
    }

    #[test]
    fn fake_resuming_continues_where_the_prompt_got_to() {
        let f = ResumingEngine::new(answers(), vec![END])
            .expect("valid")
            .delay(Duration::ZERO);
        let mut e = f.start(&EngineStartConfig::new()).expect("starts");
        assert!(e.multi().is_none());
        let first = vec![5, 7, 7, 5];
        let (sink, out) = run(e.as_mut(), &req(first.clone(), 10));
        assert_eq!(sink.tokens(), (100..110).collect::<Vec<_>>());
        assert_eq!(out.expect("runs").0.stop, EngineStop::Length);
        // The prompt plus what was written: the rest of the same answer.
        let mut again = first.clone();
        again.extend(100..110);
        let (sink, out) = run(e.as_mut(), &req(again.clone(), 100));
        let want: Vec<u32> = (110..130).chain([END]).collect();
        assert_eq!(sink.tokens(), want);
        assert_eq!(out.expect("runs").0.stop, EngineStop::Stop { token: None });
        assert_eq!(f.bases(), vec![first.clone()]);
        assert_eq!(f.calls(), vec![(first, 10), (again, 100)]);
        // Another conversation.
        let (sink, _) = run(e.as_mut(), &req(vec![8, 0], 100));
        assert_eq!(sink.tokens(), vec![1, 2, 3, END]);
        assert_eq!(f.bases().len(), 2);
        // No key matches.
        let (_, out) = run(e.as_mut(), &req(vec![4], 100));
        assert_eq!(out.unwrap_err().kind, FailureKind::Reported);
        // An answer changed in place.
        f.set_answer(vec![8], vec![4]);
        let (sink, _) = run(e.as_mut(), &req(vec![8, 0], 100));
        assert_eq!(sink.tokens(), vec![4, END]);
    }

    #[test]
    fn fake_resuming_checks_cancel_and_sleeps_before_each_token() {
        let clock = crate::fake::ManualClock::new();
        let f = ResumingEngine::with_settings(
            answers(),
            vec![END],
            FakeScript::new(Vec::new()).clock(Arc::new(clock.clone())),
        )
        .expect("valid");
        let mut e = f.start(&EngineStartConfig::new()).expect("starts");
        let h = ControlHandle::new();
        let mut sink = Collect {
            cancel_after: Some((4, h.clone())),
            ..Collect::default()
        };
        let (t, _) = console_core::engine::generate_ledgered(
            e.as_mut(),
            &req(vec![7, 7], 100),
            &h.probe(),
            &mut sink,
        )
        .expect("runs");
        assert_eq!(t, Terminal::bare(EngineStop::Cancelled));
        assert_eq!(sink.tokens().len(), 4);
        assert_eq!(clock.sleeps(), vec![RESUMING_DEFAULT_DELAY; 4]);
    }

    #[test]
    fn fake_pausing_lets_the_late_tokens_arrive_then_pauses() {
        let f = ResumingEngine::pausing(answers(), vec![END])
            .expect("valid")
            .delay(Duration::ZERO);
        let mut e = f.start(&EngineStartConfig::new()).expect("starts");
        assert!(e.descriptor().caps.pause);
        let h = ControlHandle::new();
        let mut sink = Collect {
            pause_after: Some((5, h.clone())),
            ..Collect::default()
        };
        let (t, _) = console_core::engine::generate_ledgered(
            e.as_mut(),
            &req(vec![7, 7], 100),
            &h.probe(),
            &mut sink,
        )
        .expect("runs");
        assert_eq!(t.stop, EngineStop::Paused);
        assert_eq!(sink.tokens().len(), 5 + PAUSE_LATE_TOKENS as usize);
        assert_eq!(t.counts.map(|c| c.generated), Some(0));
        assert_eq!(f.pauses(), 1);
        // The continuation reads the rest.
        let mut again = vec![7, 7];
        again.extend(sink.tokens());
        let (sink2, out) = run(e.as_mut(), &req(again, 100));
        let t = out.expect("runs").0;
        assert_eq!(t.stop, EngineStop::Stop { token: None });
        assert_eq!(t.counts.map(|c| c.prompt_tokens), Some(0));
        assert_eq!(sink.tokens().len() + sink2.tokens().len(), 31);
        // A pause near the end: the answer ends first, as "stop".
        let h = ControlHandle::new();
        let mut sink = Collect {
            pause_after: Some((2, h.clone())),
            ..Collect::default()
        };
        let (t, _) = console_core::engine::generate_ledgered(
            e.as_mut(),
            &req(vec![8], 100),
            &h.probe(),
            &mut sink,
        )
        .expect("runs");
        assert_eq!(t.stop, EngineStop::Stop { token: None });
        assert_eq!(sink.tokens(), vec![1, 2, 3, END]);
        // A consumer that leaves: no figures.
        let mut gone = Collect {
            gone_at: Some(1),
            ..Collect::default()
        };
        let h = ControlHandle::new();
        let (t, _) = console_core::engine::generate_ledgered(
            e.as_mut(),
            &req(vec![8, 1], 100),
            &h.probe(),
            &mut gone,
        )
        .expect("runs");
        assert_eq!(t, Terminal::bare(EngineStop::Cancelled));
    }

    #[test]
    fn fake_pausing_engine_new_pauses() {
        // The type named after the donor's class pauses through its own constructor.
        let f = PausingEngine::new(answers(), vec![END])
            .expect("valid")
            .delay(Duration::ZERO);
        let mut e = f.start(&EngineStartConfig::new()).expect("starts");
        assert!(e.descriptor().caps.pause);
        let h = ControlHandle::new();
        let mut sink = Collect {
            pause_after: Some((1, h.clone())),
            ..Collect::default()
        };
        let (t, _) = console_core::engine::generate_ledgered(
            e.as_mut(),
            &req(vec![7, 7], 100),
            &h.probe(),
            &mut sink,
        )
        .expect("runs");
        assert_eq!(t.stop, EngineStop::Paused);
        assert_eq!(sink.tokens().len(), 1 + PAUSE_LATE_TOKENS as usize);
        assert_eq!(f.pauses(), 1);
        assert_eq!(f.calls().len(), 1);
        assert_eq!(f.bases(), vec![vec![7, 7]]);
        // The resuming engine does not pause.
        let r = ResumingEngine::new(answers(), vec![END]).expect("valid");
        let e = r.start(&EngineStartConfig::new()).expect("starts");
        assert!(!e.descriptor().caps.pause);
    }

    #[test]
    fn fake_fair_doubles_report_no_info() {
        // The donor's ResumingEngine and PausingEngine have no `info`: no logit bias, no
        // logprobs on offer.
        let resuming = ResumingEngine::new(answers(), vec![END]).expect("valid");
        let pausing = PausingEngine::new(answers(), vec![END]).expect("valid");
        let factories: [&dyn EngineFactory; 2] = [&resuming, &pausing];
        for f in factories {
            let e = f.start(&EngineStartConfig::new()).expect("starts");
            let d = e.descriptor();
            assert!(d.info.iter().next().is_none());
            assert!(!d.caps.logit_bias);
            assert_eq!(d.caps.logprobs_max, None);
            assert_eq!(d.max_context, 32_768);
            assert!(console_core::engine::require_synthetic(d).is_ok());
        }
    }

    #[test]
    fn fake_resuming_pump_waits_at_most_wait() {
        #[derive(Default)]
        struct Tagged(Vec<(RequestId, EngineEvent)>);
        impl TaggedSink for Tagged {
            fn deliver(
                &mut self,
                rid: RequestId,
                event: EngineEvent,
            ) -> Result<(), DeliveryRefused> {
                self.0.push((rid, event));
                Ok(())
            }
        }

        let clock = crate::fake::ManualClock::new();
        let f = ResumingEngine::with_settings(
            answers(),
            vec![END],
            FakeScript::new(Vec::new()).clock(Arc::new(clock.clone())),
        )
        .expect("valid")
        .delay(Duration::from_millis(10))
        .places(2);
        let mut e = f.start(&EngineStartConfig::new()).expect("starts");
        let m = e.multi().expect("two places");
        let a = GenerationRequest::new(RequestId(1), vec![8], 50);
        m.submit(&a, ControlHandle::new().probe()).expect("submits");
        let mut out = Tagged::default();
        // A zero wait: no sleep at all, and nothing advanced while the step is not due.
        for _ in 0..3 {
            assert!(m.pump(&mut out, Duration::ZERO).expect("pumps").is_empty());
        }
        assert!(clock.sleeps().is_empty());
        assert!(out.0.is_empty());
        // Shorter waits add up to the delay; the step comes when it is due.
        m.pump(&mut out, Duration::from_millis(4)).expect("pumps");
        m.pump(&mut out, Duration::from_millis(4)).expect("pumps");
        assert!(out.0.is_empty());
        m.pump(&mut out, Duration::from_millis(4)).expect("pumps");
        assert_eq!(
            clock.sleeps(),
            vec![
                Duration::from_millis(4),
                Duration::from_millis(4),
                Duration::from_millis(2)
            ]
        );
        assert_eq!(out.0.len(), 1, "Admitted");
        // Time that passed elsewhere counts: no sleep is needed once the step is due.
        clock.clear_sleeps();
        clock.advance(Duration::from_millis(10));
        m.pump(&mut out, Duration::ZERO).expect("pumps");
        assert_eq!(out.0.len(), 2, "the first token");
        assert!(clock.sleeps().is_empty());
        // A long wait sleeps only the delay, never more than `wait`.
        m.pump(&mut out, Duration::from_secs(5)).expect("pumps");
        assert_eq!(clock.sleeps(), vec![Duration::from_millis(10)]);
        assert_eq!(out.0.len(), 3);
    }

    #[test]
    fn fake_resuming_runs_several_places_through_submit_and_pump() {
        use console_core::engine::LedgerSet;

        #[derive(Default)]
        struct Tagged(Vec<(RequestId, EngineEvent)>);
        impl TaggedSink for Tagged {
            fn deliver(
                &mut self,
                rid: RequestId,
                event: EngineEvent,
            ) -> Result<(), DeliveryRefused> {
                self.0.push((rid, event));
                Ok(())
            }
        }

        let f = ResumingEngine::new(answers(), vec![END])
            .expect("valid")
            .delay(Duration::ZERO)
            .places(2);
        let mut e = f.start(&EngineStartConfig::new()).expect("starts");
        assert_eq!(e.descriptor().caps.multi, Some(2));
        let desc = e.descriptor().clone();
        let a = GenerationRequest::new(RequestId(1), vec![7, 7], 5);
        let b = GenerationRequest::new(RequestId(2), vec![8], 50);
        let c = GenerationRequest::new(RequestId(3), vec![8, 8], 50);
        let (ha, hb) = (ControlHandle::new(), ControlHandle::new());
        let mut ledgers = LedgerSet::new(2);
        let m = e.multi().expect("two places");
        ledgers.open(&a, &desc).expect("opens");
        m.submit(&a, ha.probe()).expect("submits");
        ledgers.open(&b, &desc).expect("opens");
        m.submit(&b, hb.probe()).expect("submits");
        assert_eq!(m.running(), 2);
        let refused = m.submit(&c, ControlHandle::new().probe()).unwrap_err();
        assert_eq!(refused.kind, FailureKind::Unsupported);
        let dup = m.submit(&a, ha.probe()).unwrap_err();
        assert_eq!(dup.kind, FailureKind::Protocol);
        let mut out = Tagged::default();
        let mut done = Vec::new();
        for _ in 0..100 {
            let finished = m
                .pump(&mut ledgers.sink(&mut out), Duration::from_millis(1))
                .expect("pumps");
            for fin in finished {
                done.push((fin.rid, ledgers.finish(fin).expect("ledger agrees")));
            }
            if m.running() == 0 {
                break;
            }
        }
        assert_eq!(done.len(), 2);
        let ids = |rid| -> Vec<u32> {
            out.0
                .iter()
                .filter_map(|(r, e)| match e {
                    EngineEvent::Token(t) if *r == rid => Some(t.id),
                    _ => None,
                })
                .collect()
        };
        assert_eq!(ids(RequestId(1)), vec![100, 101, 102, 103, 104]);
        assert_eq!(ids(RequestId(2)), vec![1, 2, 3, END]);
        let stop_of = |rid| {
            done.iter()
                .find(|(r, _)| *r == rid)
                .map(|(_, (t, _))| t.stop)
        };
        assert_eq!(stop_of(RequestId(1)), Some(EngineStop::Length));
        assert_eq!(
            stop_of(RequestId(2)),
            Some(EngineStop::Stop { token: None })
        );
        // The tokens interleave: both ran at once.
        let first_b = out
            .0
            .iter()
            .position(|(r, e)| *r == RequestId(2) && matches!(e, EngineEvent::Token(_)));
        let last_a = out
            .0
            .iter()
            .rposition(|(r, e)| *r == RequestId(1) && matches!(e, EngineEvent::Token(_)));
        assert!(first_b < last_a);
        // A cancel for one request id only.
        let m = e.multi().expect("two places");
        let hc = ControlHandle::new();
        m.submit(&c, hc.probe()).expect("submits");
        hc.cancel();
        let fin = m
            .pump(&mut Tagged::default(), Duration::ZERO)
            .expect("pumps");
        assert!(fin.is_empty(), "Admitted first");
        let fin = m
            .pump(&mut Tagged::default(), Duration::ZERO)
            .expect("pumps");
        assert_eq!(fin.len(), 1);
        assert_eq!(fin[0].outcome, Ok(Terminal::bare(EngineStop::Cancelled)));
    }
}
