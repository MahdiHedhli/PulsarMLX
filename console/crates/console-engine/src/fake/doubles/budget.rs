//! Provenance: translated from project-maya serve/test_server.py::BudgetEngine at 7e68a30f (MIT); license text in console/LICENSES/project-maya-MIT.txt.
//!
//! A double that honors the request's thinking budget itself, as the real engines do.

use std::sync::{Arc, Mutex};
use std::time::Instant;

use console_core::engine::{
    ControlProbe, EngineDescriptor, EngineFactory, EngineFailure, EngineInstance, EngineKind,
    EngineStartConfig, EngineStop, EventSink, GenerationRequest, Health, ShutdownOutcome, Terminal,
};

use crate::fake::config::{FakeConfigError, FakeScript};
use crate::fake::deliver::{admitted, offer, prompt_tokens, token, Offer};
use crate::fake::lock;
use crate::fake::mock::{MockCore, MockParts};

/// The most requests a [`BudgetEngine`] keeps; later ones are not recorded.
const BUDGET_MAX_CALLS: usize = 65_536;

/// The budget the donor uses when the request gives none (or 0): `1 << 30`.
const NO_BUDGET: u32 = 1 << 30;

#[derive(Debug)]
struct BudgetState {
    reasoning: Arc<[u32]>,
    answer: Arc<[u32]>,
    think_end: u32,
    calls: Vec<GenerationRequest>,
}

/// Rust counterpart of the donor's `BudgetEngine` (serve/test_server.py:2561-2585): it
/// thinks `reasoning` until the request's thinking budget, where it closes the thinking
/// itself with `think_end` (only when the budget cut the reasoning short), then writes
/// `answer` (whose last id is the end of turn); a prompt that ends with `think_end` (the
/// server closed the thinking) gets the answer only. The output is cut to `max_new`.
/// Cancel is checked before each token of the thinking path; the answer-only path, as in
/// the donor, does not check it (a consumer that leaves still stops it). Every request is
/// recorded (the donor's `calls`).
#[derive(Debug, Clone)]
pub struct BudgetEngine {
    parts: MockParts,
    state: Arc<Mutex<BudgetState>>,
}

impl BudgetEngine {
    /// `reasoning` and `answer` already encoded; `think_end` is the id that closes the
    /// thinking.
    pub fn new(
        reasoning: Vec<u32>,
        answer: Vec<u32>,
        think_end: u32,
    ) -> Result<Self, FakeConfigError> {
        let parts = MockParts::new(FakeScript::new(answer.clone()))?;
        // The answer is checked by the scripted engine's limits above; the reasoning too.
        FakeScript::new(reasoning.clone()).into_config()?;
        Ok(Self {
            parts,
            state: Arc::new(Mutex::new(BudgetState {
                reasoning: Arc::from(reasoning),
                answer: Arc::from(answer),
                think_end,
                calls: Vec::new(),
            })),
        })
    }

    /// The requests so far (the donor's `calls`, which keep each request's sampling).
    pub fn calls(&self) -> Vec<GenerationRequest> {
        lock(&self.state).calls.clone()
    }
}

struct BudgetInstance {
    core: MockCore,
    state: Arc<Mutex<BudgetState>>,
}

impl EngineInstance for BudgetInstance {
    fn descriptor(&self) -> &EngineDescriptor {
        &self.core.desc
    }

    fn generate(
        &mut self,
        req: &GenerationRequest,
        control: &ControlProbe,
        sink: &mut dyn EventSink,
    ) -> Result<Terminal, EngineFailure> {
        self.core.refresh();
        if self.core.desc.is_starting() {
            return Err(EngineFailure::not_ready());
        }
        let n_prompt = prompt_tokens(&req.prompt)?;
        let (reasoning, answer, end) = {
            let mut s = lock(&self.state);
            if s.calls.len() < BUDGET_MAX_CALLS {
                s.calls.push(req.clone());
            }
            (Arc::clone(&s.reasoning), Arc::clone(&s.answer), s.think_end)
        };
        let max_new = usize::try_from(req.max_new).unwrap_or(usize::MAX);
        let closed = req.prompt.last() == Some(&end);
        let out: Vec<u32> = if closed {
            answer.to_vec()
        } else {
            let budget = req
                .thinking
                .as_ref()
                .map(|h| h.budget)
                .filter(|b| *b != 0)
                .unwrap_or(NO_BUDGET);
            let budget = usize::try_from(budget).unwrap_or(usize::MAX);
            let mut out: Vec<u32> = reasoning.iter().take(budget).copied().collect();
            if budget < reasoning.len() {
                out.push(end);
            }
            out.extend_from_slice(&answer);
            out
        };
        let length = out.len() > max_new;
        if offer(sink, control, admitted(n_prompt)) == Offer::Gone {
            return Ok(Terminal::bare(EngineStop::Cancelled));
        }
        for (i, &t) in out.iter().take(max_new).enumerate() {
            let index = u32::try_from(i).unwrap_or(u32::MAX);
            if !closed && control.is_cancelled() {
                return Ok(Terminal::bare(EngineStop::Cancelled));
            }
            if offer(sink, control, token(n_prompt, index, t, None)) == Offer::Gone {
                return Ok(Terminal::bare(EngineStop::Cancelled));
            }
        }
        Ok(Terminal::bare(if length {
            EngineStop::Length
        } else {
            EngineStop::Stop { token: None }
        }))
    }

    fn health(&mut self) -> Health {
        self.core.refresh();
        Health::Alive
    }

    fn shutdown(self: Box<Self>, _deadline: Instant) -> ShutdownOutcome {
        ShutdownOutcome::Graceful
    }
}

impl EngineFactory for BudgetEngine {
    fn kind(&self) -> EngineKind {
        EngineKind::Scripted
    }

    fn start(&self, cfg: &EngineStartConfig) -> Result<Box<dyn EngineInstance>, EngineFailure> {
        Ok(Box::new(BudgetInstance {
            core: self.parts.start(cfg)?.0,
            state: Arc::clone(&self.state),
        }))
    }
}

#[cfg(test)]
mod tests {
    use console_core::engine::ThinkingHints;

    use super::*;
    use crate::fake::testutil::{req, run};

    const END: u32 = 300;

    fn engine() -> BudgetEngine {
        BudgetEngine::new((1..=10).collect(), vec![50, 51, 99], END).expect("valid")
    }

    fn budget(prompt: Vec<u32>, max_new: u32, b: u32) -> GenerationRequest {
        let mut r = req(prompt, max_new);
        r.thinking = Some(ThinkingHints {
            budget: b,
            end_id: END,
            soft: None,
        });
        r
    }

    #[test]
    fn fake_budget_closes_the_thinking_at_the_budget() {
        let f = engine();
        let mut e = f.start(&EngineStartConfig::new()).expect("starts");
        let (sink, out) = run(e.as_mut(), &budget(vec![7], 100, 4));
        assert_eq!(sink.tokens(), vec![1, 2, 3, 4, END, 50, 51, 99]);
        assert_eq!(out.expect("runs").0.stop, EngineStop::Stop { token: None });
        // No budget, or 0 (falsy in the donor): the whole reasoning, no close of its own.
        let (sink, _) = run(e.as_mut(), &req(vec![7], 100));
        assert_eq!(
            sink.tokens(),
            (1..=10).chain([50, 51, 99]).collect::<Vec<_>>()
        );
        let (sink, _) = run(e.as_mut(), &budget(vec![7], 100, 0));
        assert_eq!(sink.tokens().len(), 13);
        // A budget equal to the reasoning: no close token either.
        let (sink, _) = run(e.as_mut(), &budget(vec![7], 100, 10));
        assert!(!sink.tokens().contains(&END));
        // Cut to max_new.
        let (sink, out) = run(e.as_mut(), &budget(vec![7], 3, 4));
        assert_eq!(sink.tokens(), vec![1, 2, 3]);
        assert_eq!(out.expect("runs").0.stop, EngineStop::Length);
        assert_eq!(f.calls().len(), 5);
        assert_eq!(f.calls()[0].thinking.as_ref().map(|t| t.budget), Some(4));
    }

    #[test]
    fn fake_budget_answers_only_after_a_closed_thinking() {
        let f = engine();
        let mut e = f.start(&EngineStartConfig::new()).expect("starts");
        let (sink, _) = run(e.as_mut(), &budget(vec![7, END], 100, 4));
        assert_eq!(sink.tokens(), vec![50, 51, 99]);
        let (sink, out) = run(e.as_mut(), &req(vec![7, END], 2));
        assert_eq!(sink.tokens(), vec![50, 51]);
        assert_eq!(out.expect("runs").0.stop, EngineStop::Length);
    }
}
