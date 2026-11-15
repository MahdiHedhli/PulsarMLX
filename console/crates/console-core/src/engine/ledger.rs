//! The event ledger (contract section 7.1): one set of ordering and counting rules
//! applied to every engine, whatever its kind. Delivery is at least once and keyed by
//! position: an exact replay of the most recently accepted token is dropped, a gap or a
//! rewind is a `Protocol` failure.
//!
//! The ledger checks an event before it is forwarded and commits it only after the
//! downstream sink accepted it ([`EventLedger::check`], then [`EventLedger::commit`]), so
//! an event refused with `Backpressure` and offered again is forwarded again, not dropped
//! as a replay. A refusal with `ConsumerGone` is sticky: the refused event and every later
//! one are still checked and recorded, but no longer forwarded or counted as delivered,
//! so an engine that stops as told and returns `Cancelled` ends without a failure.

use super::descriptor::EngineDescriptor;
use super::error::EngineFailure;
use super::event::{CommittedToken, DeliveryRefused, EngineEvent, EventSink};
use super::request::GenerationRequest;
use super::terminal::{EngineCounts, EngineStop, EngineTimings, Terminal};

/// What the ledger decided about one event.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Verdict {
    /// New: forward it.
    Accepted,
    /// An exact repeat of the most recently accepted token: drop it.
    Replay,
}

#[derive(Debug, Clone, PartialEq)]
enum Effect {
    None,
    Admitted,
    Token(CommittedToken),
}

/// The result of [`EventLedger::check`]: the verdict, and what [`EventLedger::commit`]
/// will record. It is valid only until the next commit.
#[derive(Debug, Clone, PartialEq)]
#[must_use]
pub struct Checked {
    verdict: Verdict,
    stamp: u64,
    effect: Effect,
}

impl Checked {
    /// The verdict.
    pub fn verdict(&self) -> Verdict {
        self.verdict
    }

    /// The event to forward for `offered`, the event that was checked: a token as the
    /// ledger records it, with its alternatives cut to the request's `logprobs`; any other
    /// event unchanged.
    ///
    /// Behavior reference: project-maya serve/server.py:594 at 7e68a30f (`lp[1][:n_top]`).
    pub fn forwarded(&self, offered: EngineEvent) -> EngineEvent {
        match &self.effect {
            Effect::Token(t) => EngineEvent::Token(t.clone()),
            _ => offered,
        }
    }
}

/// The figures the server uses for usage, returned by [`EventLedger::close`].
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct LedgerCounts {
    /// The length of the prompt ids sent (the donor's `prompt_tokens`).
    pub prompt_tokens: u32,
    /// Every token the ledger accepted and the downstream sink took, a stop token included
    /// (contract section 14, Q4). Tokens recorded after the consumer left are not counted.
    pub completion_tokens: u32,
    /// From the terminal's counts only (the donor's `DONE` field 8); `None` when the
    /// terminal reports none. Reuse in `Admitted` or in progress events is not used here.
    ///
    /// Behavior reference: project-maya serve/server.py:1197, :4712, :5005 at 7e68a30f.
    pub reused_tokens: Option<u32>,
    /// How the engine says it ended.
    pub stop: EngineStop,
    /// The engine's own counts, passed through unchecked (Q4).
    pub engine: Option<EngineCounts>,
    /// The engine's clock.
    pub timings: Option<EngineTimings>,
}

/// The per-generation ledger.
#[derive(Debug, Clone)]
pub struct EventLedger {
    prompt_len: usize,
    max_new: u32,
    logprobs: Option<u8>,
    vocab_size: Option<u32>,
    admitted: bool,
    next: u32,
    delivered: u32,
    consumer_gone: bool,
    position0: Option<u64>,
    last: Option<CommittedToken>,
    failed: Option<EngineFailure>,
    closed: bool,
    stamp: u64,
}

/// Exact identity of two tokens, comparing logprobs bit for bit (so that a NaN replay is
/// still a replay).
fn same_token(a: &CommittedToken, b: &CommittedToken) -> bool {
    let lp_same = match (&a.logprob, &b.logprob) {
        (None, None) => true,
        (Some(x), Some(y)) => {
            x.logprob.to_bits() == y.logprob.to_bits()
                && x.top.len() == y.top.len()
                && x.top
                    .iter()
                    .zip(&y.top)
                    .all(|(p, q)| p.0 == q.0 && p.1.to_bits() == q.1.to_bits())
        }
        _ => false,
    };
    a.index == b.index && a.position == b.position && a.id == b.id && lp_same
}

impl EventLedger {
    /// A ledger for one generation of `req` on the engine `desc` describes.
    pub fn new(req: &GenerationRequest, desc: &EngineDescriptor) -> Self {
        Self {
            prompt_len: req.prompt.len(),
            max_new: req.max_new,
            logprobs: req.logprobs,
            vocab_size: desc.vocab_size,
            admitted: false,
            next: 0,
            delivered: 0,
            consumer_gone: false,
            position0: None,
            last: None,
            failed: None,
            closed: false,
            stamp: 0,
        }
    }

    /// Tokens accepted so far (the next expected index).
    pub fn accepted(&self) -> u32 {
        self.next
    }

    /// Tokens accepted while the consumer was still reading (the usage count).
    pub fn delivered(&self) -> u32 {
        self.delivered
    }

    /// Records that the downstream sink answered `ConsumerGone`. From then on events are
    /// still checked and committed, but not counted as delivered. Sticky.
    pub fn mark_consumer_gone(&mut self) {
        self.consumer_gone = true;
    }

    /// True after [`mark_consumer_gone`](Self::mark_consumer_gone).
    pub fn consumer_gone(&self) -> bool {
        self.consumer_gone
    }

    /// The failure that stopped this ledger, if any. Failures are sticky.
    pub fn failure(&self) -> Option<&EngineFailure> {
        self.failed.as_ref()
    }

    /// True after [`close`](Self::close) succeeded.
    pub fn is_closed(&self) -> bool {
        self.closed
    }

    fn fail(&mut self, failure: EngineFailure) -> EngineFailure {
        let failure = failure.with_after_tokens(self.next);
        self.failed = Some(failure.clone());
        failure
    }

    fn checked(&self, verdict: Verdict, effect: Effect) -> Checked {
        Checked {
            verdict,
            stamp: self.stamp,
            effect,
        }
    }

    /// Checks `event` against the rules of section 7.1 without recording it. A failure is
    /// recorded at once and returned by every later call.
    pub fn check(&mut self, event: &EngineEvent) -> Result<Checked, EngineFailure> {
        if let Some(f) = &self.failed {
            return Err(f.clone());
        }
        if self.closed {
            return Err(self.fail(EngineFailure::protocol("an event after the terminal")));
        }
        match event {
            EngineEvent::Admitted { prompt_tokens, .. } => {
                if self.admitted {
                    return Err(self.fail(EngineFailure::protocol("Admitted twice")));
                }
                if usize::try_from(*prompt_tokens).ok() != Some(self.prompt_len) {
                    let detail = format!(
                        "Admitted reports {prompt_tokens} prompt tokens for a prompt of {}",
                        self.prompt_len
                    );
                    return Err(self.fail(EngineFailure::protocol(&detail)));
                }
                Ok(self.checked(Verdict::Accepted, Effect::Admitted))
            }
            EngineEvent::PromptProgress(_) | EngineEvent::Sample(_) | EngineEvent::Note(_) => {
                Ok(self.checked(Verdict::Accepted, Effect::None))
            }
            EngineEvent::Token(t) => self.check_token(t),
        }
    }

    fn check_token(&mut self, offered: &CommittedToken) -> Result<Checked, EngineFailure> {
        // More alternatives than asked are cut to the asked number, as the donor renders
        // `lp[1][:n_top]`; the cut token is what is compared, recorded and forwarded.
        let cut;
        let t = match (self.logprobs, &offered.logprob) {
            (Some(n), Some(lp)) if lp.top.len() > usize::from(n) => {
                let mut c = offered.clone();
                if let Some(lp) = c.logprob.as_mut() {
                    lp.top.truncate(usize::from(n));
                }
                cut = c;
                &cut
            }
            _ => offered,
        };
        if self.last.as_ref().is_some_and(|last| same_token(last, t)) {
            return Ok(self.checked(Verdict::Replay, Effect::None));
        }
        if !self.admitted {
            return Err(self.fail(EngineFailure::protocol("a token before Admitted")));
        }
        if t.index < self.next {
            let detail = format!(
                "token index {} is behind the next index {} and is not a replay of the last \
                 token (a rewind, or a changed token at a committed position)",
                t.index, self.next
            );
            return Err(self.fail(EngineFailure::protocol(&detail)));
        }
        if t.index > self.next {
            let detail = format!(
                "token index {} skips ahead of the next index {} (a gap)",
                t.index, self.next
            );
            return Err(self.fail(EngineFailure::protocol(&detail)));
        }
        if t.index >= self.max_new {
            let detail = format!("token index {} reaches max_new {}", t.index, self.max_new);
            return Err(self.fail(EngineFailure::protocol(&detail)));
        }
        if let Some(p0) = self.position0 {
            match p0.checked_add(u64::from(t.index)) {
                Some(want) if want == t.position => {}
                Some(want) => {
                    let detail = format!(
                        "token index {} at position {}, expected position {want}",
                        t.index, t.position
                    );
                    return Err(self.fail(EngineFailure::protocol(&detail)));
                }
                None => {
                    return Err(self.fail(EngineFailure::protocol("token position overflows")));
                }
            }
        }
        if let Some(vocab) = self.vocab_size {
            if t.id >= vocab {
                return Err(self.fail(EngineFailure::out_of_vocabulary(t.id, vocab)));
            }
        }
        if self.logprobs.is_none() && t.logprob.is_some() {
            return Err(self.fail(EngineFailure::protocol(
                "a logprob on a token of a request that did not ask for logprobs",
            )));
        }
        Ok(self.checked(Verdict::Accepted, Effect::Token(t.clone())))
    }

    /// Records an event [`check`](Self::check) accepted, once the downstream sink took it
    /// (or, after [`mark_consumer_gone`](Self::mark_consumer_gone), without forwarding it).
    /// A `Checked` from before the latest commit is refused as a `Protocol` failure.
    pub fn commit(&mut self, checked: Checked) -> Result<(), EngineFailure> {
        if let Some(f) = &self.failed {
            return Err(f.clone());
        }
        if checked.stamp != self.stamp {
            return Err(self.fail(EngineFailure::protocol("a ledger commit of a stale check")));
        }
        match checked.effect {
            Effect::None => {}
            Effect::Admitted => self.admitted = true,
            Effect::Token(t) => {
                if self.position0.is_none() {
                    self.position0 = Some(t.position);
                }
                // `check` refused index >= max_new, so this cannot overflow.
                self.next = t.index.saturating_add(1);
                if !self.consumer_gone {
                    self.delivered = self.delivered.saturating_add(1);
                }
                self.last = Some(t);
            }
        }
        self.stamp = self.stamp.wrapping_add(1);
        Ok(())
    }

    /// [`check`](Self::check) and [`commit`](Self::commit) in one step, for a consumer
    /// that cannot refuse.
    pub fn observe(&mut self, event: &EngineEvent) -> Result<Verdict, EngineFailure> {
        let checked = self.check(event)?;
        let verdict = checked.verdict;
        self.commit(checked)?;
        Ok(verdict)
    }

    /// Checks the terminal record against what was accepted and returns the figures for
    /// usage. The engine's own `generated` and `prompt_tokens` are passed through and not
    /// compared (contract section 14, Q4). A `Cancelled` or `Paused` terminal before
    /// `Admitted` is accepted with no completion tokens: a generation cancelled before it
    /// started simply ends, as in the donor (serve/server.py:228-229, :1393-1394). Refused:
    /// a terminal after a failure, a second terminal, a `Stop` or `Length` terminal before
    /// `Admitted`, and a prompt longer than `u32` counts.
    pub fn close(&mut self, terminal: &Terminal) -> Result<LedgerCounts, EngineFailure> {
        if let Some(f) = &self.failed {
            return Err(f.clone());
        }
        if self.closed {
            return Err(self.fail(EngineFailure::protocol("a second terminal")));
        }
        let ends_early = matches!(terminal.stop, EngineStop::Cancelled | EngineStop::Paused);
        if !self.admitted && !ends_early {
            return Err(self.fail(EngineFailure::protocol(
                "a stop or length terminal before Admitted",
            )));
        }
        let Ok(prompt_tokens) = u32::try_from(self.prompt_len) else {
            return Err(self.fail(EngineFailure::protocol(
                "the prompt length overflows the usage count",
            )));
        };
        self.closed = true;
        Ok(LedgerCounts {
            prompt_tokens,
            completion_tokens: self.delivered,
            reused_tokens: terminal.counts.and_then(|c| c.reused_tokens),
            stop: terminal.stop,
            engine: terminal.counts,
            timings: terminal.timings,
        })
    }
}

/// Runs `event` through `ledger` and, when it is new, forwards it to `forward`, committing
/// it only once `forward` accepted it. A ledger failure is reported to the engine as
/// `ConsumerGone`, so it stops; the failure stays in the ledger. `Backpressure` from
/// `forward` commits nothing, so the event is offered again. `ConsumerGone` from `forward`
/// is sticky: the refused event is committed (the engine committed that step) and every
/// later event is checked and committed without being forwarded, and answered
/// `ConsumerGone`; a gap, rewind or other fault is still caught.
pub(crate) fn ledgered_deliver(
    ledger: &mut EventLedger,
    event: EngineEvent,
    forward: impl FnOnce(EngineEvent) -> Result<(), DeliveryRefused>,
) -> Result<(), DeliveryRefused> {
    let gone = DeliveryRefused::ConsumerGone;
    let checked = ledger.check(&event).map_err(|_| gone)?;
    if ledger.consumer_gone() {
        ledger.commit(checked).map_err(|_| gone)?;
        return Err(gone);
    }
    if checked.verdict() == Verdict::Accepted {
        match forward(checked.forwarded(event)) {
            Ok(()) => {}
            Err(DeliveryRefused::Backpressure) => return Err(DeliveryRefused::Backpressure),
            Err(DeliveryRefused::ConsumerGone) => {
                ledger.mark_consumer_gone();
                ledger.commit(checked).map_err(|_| gone)?;
                return Err(gone);
            }
        }
    }
    ledger.commit(checked).map_err(|_| gone)
}

/// The end of a generation seen through a ledger: a ledger failure wins over what the
/// engine returned; an engine failure gets the accepted token count; a terminal is closed.
pub(crate) fn ledgered_finish(
    ledger: &mut EventLedger,
    result: Result<Terminal, EngineFailure>,
) -> Result<(Terminal, LedgerCounts), EngineFailure> {
    if let Some(f) = ledger.failure() {
        return Err(f.clone());
    }
    match result {
        Err(e) => Err(e.with_after_tokens(ledger.accepted())),
        Ok(t) => ledger.close(&t).map(|c| (t, c)),
    }
}

/// An [`EventSink`] that applies an [`EventLedger`] before forwarding to `downstream`
/// (contract section 7.1: "the ledger runs inside the sink").
pub struct LedgeredSink<'a> {
    ledger: EventLedger,
    downstream: &'a mut dyn EventSink,
}

impl<'a> LedgeredSink<'a> {
    /// A sink for one generation of `req` on the engine `desc` describes.
    pub fn new(
        req: &GenerationRequest,
        desc: &EngineDescriptor,
        downstream: &'a mut dyn EventSink,
    ) -> Self {
        Self {
            ledger: EventLedger::new(req, desc),
            downstream,
        }
    }

    /// The ledger.
    pub fn ledger(&self) -> &EventLedger {
        &self.ledger
    }

    /// Ends the generation with what `generate` returned.
    pub fn finish(
        mut self,
        result: Result<Terminal, EngineFailure>,
    ) -> Result<(Terminal, LedgerCounts), EngineFailure> {
        ledgered_finish(&mut self.ledger, result)
    }
}

impl EventSink for LedgeredSink<'_> {
    fn deliver(&mut self, event: EngineEvent) -> Result<(), DeliveryRefused> {
        let downstream = &mut *self.downstream;
        ledgered_deliver(&mut self.ledger, event, |e| downstream.deliver(e))
    }
}
