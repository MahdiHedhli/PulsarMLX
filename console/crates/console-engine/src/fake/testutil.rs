//! Sinks and helpers for this module's unit tests.

use console_core::engine::{
    generate_ledgered, ControlHandle, DeliveryRefused, EngineEvent, EngineFailure, EngineInstance,
    EventSink, GenerationRequest, LedgerCounts, RequestId, Terminal, TokenLogprob,
};

/// Collects every event; optionally cancels `handle` once `cancel_after` tokens arrived,
/// or answers `ConsumerGone` from the `gone_at`-th token on.
#[derive(Default)]
pub(crate) struct Collect {
    pub(crate) events: Vec<EngineEvent>,
    pub(crate) cancel_after: Option<(usize, ControlHandle)>,
    pub(crate) gone_at: Option<usize>,
    pub(crate) pause_after: Option<(usize, ControlHandle)>,
}

impl Collect {
    pub(crate) fn tokens(&self) -> Vec<u32> {
        self.events
            .iter()
            .filter_map(|e| match e {
                EngineEvent::Token(t) => Some(t.id),
                _ => None,
            })
            .collect()
    }

    pub(crate) fn logprobs(&self) -> Vec<Option<TokenLogprob>> {
        self.events
            .iter()
            .filter_map(|e| match e {
                EngineEvent::Token(t) => Some(t.logprob.clone()),
                _ => None,
            })
            .collect()
    }

    fn token_count(&self) -> usize {
        self.events
            .iter()
            .filter(|e| matches!(e, EngineEvent::Token(_)))
            .count()
    }
}

impl EventSink for Collect {
    fn deliver(&mut self, event: EngineEvent) -> Result<(), DeliveryRefused> {
        if matches!(event, EngineEvent::Token(_)) {
            if let Some(at) = self.gone_at {
                if self.token_count() >= at {
                    return Err(DeliveryRefused::ConsumerGone);
                }
            }
        }
        self.events.push(event);
        let n = self.token_count();
        if let Some((k, h)) = &self.cancel_after {
            if n >= *k {
                h.cancel();
            }
        }
        if let Some((k, h)) = &self.pause_after {
            if n >= *k {
                h.pause(false);
            }
        }
        Ok(())
    }
}

pub(crate) fn req(prompt: Vec<u32>, max_new: u32) -> GenerationRequest {
    GenerationRequest::new(RequestId(1), prompt, max_new)
}

/// One generation through the ledger with a fresh control state.
pub(crate) fn run(
    e: &mut dyn EngineInstance,
    r: &GenerationRequest,
) -> (Collect, Result<(Terminal, LedgerCounts), EngineFailure>) {
    let h = ControlHandle::new();
    let mut sink = Collect::default();
    let out = generate_ledgered(e, r, &h.probe(), &mut sink);
    (sink, out)
}
