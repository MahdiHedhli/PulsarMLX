//! Delivery helpers shared by the scripted engine and its doubles (contract section 7):
//! an event refused with `Backpressure` is offered again, never skipped; `ConsumerGone`
//! ends the generation as `Cancelled`.

use std::time::Duration;

use console_core::engine::{
    CommittedToken, ControlProbe, DeliveryRefused, EngineEvent, EngineFailure, EventSink,
    TokenLogprob,
};

/// How long the engine waits before it offers an event refused with `Backpressure` again.
pub(crate) const BACKPRESSURE_PAUSE: Duration = Duration::from_millis(1);

/// What became of an offered event.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum Offer {
    /// Accepted (or dropped as an exact replay).
    Taken,
    /// Nobody reads any more, or a cancel arrived while the sink held the event back: the
    /// generation ends as `Cancelled`.
    Gone,
}

/// Offers `event` until the sink accepts it. `Backpressure` waits
/// [`BACKPRESSURE_PAUSE`] and offers the same event again; a cancel seen meanwhile ends
/// the offer as [`Offer::Gone`].
pub(crate) fn offer(sink: &mut dyn EventSink, control: &ControlProbe, event: EngineEvent) -> Offer {
    loop {
        match sink.deliver(event.clone()) {
            Ok(()) => return Offer::Taken,
            Err(DeliveryRefused::ConsumerGone) => return Offer::Gone,
            Err(DeliveryRefused::Backpressure) => {
                if control.is_cancelled() {
                    return Offer::Gone;
                }
                std::thread::sleep(BACKPRESSURE_PAUSE);
            }
        }
    }
}

/// The prompt length as the `u32` the seam counts in; a longer prompt is refused before
/// anything is delivered.
pub(crate) fn prompt_tokens(prompt: &[u32]) -> Result<u32, EngineFailure> {
    u32::try_from(prompt.len())
        .map_err(|_| EngineFailure::unsupported("a prompt of more than 4294967295 tokens"))
}

/// `Admitted` for a prompt of `prompt_tokens` tokens, with no reuse known at admission.
pub(crate) fn admitted(prompt_tokens: u32) -> EngineEvent {
    EngineEvent::Admitted {
        prompt_tokens,
        reused_tokens: None,
    }
}

/// The token at `index` after a prompt of `prompt_tokens` tokens: its absolute position is
/// the prompt length plus the index.
pub(crate) fn token(
    prompt_tokens: u32,
    index: u32,
    id: u32,
    logprob: Option<TokenLogprob>,
) -> EngineEvent {
    EngineEvent::Token(CommittedToken {
        index,
        position: u64::from(prompt_tokens) + u64::from(index),
        id,
        logprob,
    })
}

/// The scripted engine's logprob: a scripted token is certain, logprob 0, the only entry
/// of its row, and the row is empty when no alternative is asked for.
///
/// Behavior reference: project-maya serve/server.py:214-216, 237-239 at 7e68a30f.
pub(crate) fn certain_logprob(id: u32, top: u8) -> TokenLogprob {
    TokenLogprob {
        logprob: 0.0,
        top: if top > 0 { vec![(id, 0.0)] } else { Vec::new() },
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use console_core::engine::ControlHandle;

    struct Refusing {
        backpressure: u32,
        gone: bool,
        seen: Vec<EngineEvent>,
    }

    impl EventSink for Refusing {
        fn deliver(&mut self, event: EngineEvent) -> Result<(), DeliveryRefused> {
            if self.gone {
                return Err(DeliveryRefused::ConsumerGone);
            }
            if self.backpressure > 0 {
                self.backpressure -= 1;
                return Err(DeliveryRefused::Backpressure);
            }
            self.seen.push(event);
            Ok(())
        }
    }

    #[test]
    fn fake_backpressure_offers_the_same_event_again() {
        let h = ControlHandle::new();
        let mut sink = Refusing {
            backpressure: 2,
            gone: false,
            seen: Vec::new(),
        };
        let ev = token(3, 0, 7, None);
        assert_eq!(offer(&mut sink, &h.probe(), ev.clone()), Offer::Taken);
        assert_eq!(sink.seen, vec![ev]);
    }

    #[test]
    fn fake_consumer_gone_or_cancel_under_backpressure_ends_the_offer() {
        let h = ControlHandle::new();
        let mut gone = Refusing {
            backpressure: 0,
            gone: true,
            seen: Vec::new(),
        };
        assert_eq!(offer(&mut gone, &h.probe(), admitted(1)), Offer::Gone);
        let mut held = Refusing {
            backpressure: u32::MAX,
            gone: false,
            seen: Vec::new(),
        };
        h.cancel();
        assert_eq!(offer(&mut held, &h.probe(), admitted(1)), Offer::Gone);
        assert!(held.seen.is_empty());
    }

    #[test]
    fn fake_token_positions_follow_the_prompt() {
        match token(5, 2, 9, None) {
            EngineEvent::Token(t) => {
                assert_eq!((t.index, t.position, t.id), (2, 7, 9));
            }
            other => panic!("not a token: {other:?}"),
        }
        assert_eq!(certain_logprob(9, 0).top, Vec::<(u32, f64)>::new());
        assert_eq!(certain_logprob(9, 3).top, vec![(9, 0.0)]);
    }
}
