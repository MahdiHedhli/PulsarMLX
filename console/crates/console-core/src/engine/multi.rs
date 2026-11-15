//! The submit-and-pump form of the token level, for engines with several places
//! (`READY ... multi=<n>`; contract section 4.1, question Q1).
//!
//! The instance stays owned by one driver thread. The driver submits generations up to
//! the engine's places and pumps the engine; events arrive tagged with the request id,
//! and each generation ends with exactly one [`Finished`]. The blocking
//! [`EngineInstance::generate`](super::EngineInstance::generate) form is the
//! single-conversation case; [`generate_one`] runs it over this form.

use std::time::Duration;

use super::control::ControlProbe;
use super::descriptor::EngineDescriptor;
use super::error::EngineFailure;
use super::event::{DeliveryRefused, EngineEvent, EventSink, TaggedSink};
use super::ledger::{ledgered_deliver, ledgered_finish, EventLedger, LedgerCounts};
use super::request::{GenerationRequest, RequestId};
use super::terminal::Terminal;

/// The end of one submitted generation.
#[derive(Debug, Clone, PartialEq)]
pub struct Finished {
    /// The generation.
    pub rid: RequestId,
    /// Its terminal record or its failure.
    pub outcome: Result<Terminal, EngineFailure>,
}

/// The submit-and-pump form. Called on the driver thread only.
///
/// Rules (contract section 4.1):
///
/// 1. `submit` starts one generation. The server submits at most `caps.places()` at
///    once and never reuses a request id; an engine refuses a submission beyond its
///    places, or with an id already running, with a failure and starts nothing.
/// 2. `pump` waits at most `wait` for engine output, delivers what arrived to the sink
///    tagged with its request id, and returns every generation that ended during the
///    call. Per request id the order of section 7 holds: `Admitted` first, tokens in index
///    order, then exactly one `Finished`, and no event for that id after it.
/// 3. Each submission carries its own [`ControlProbe`], read between steps; a cancel is
///    sent for that request id only (deviation FIX-1.3).
/// 4. `Backpressure` for one id holds that id's events and is offered again; other ids go
///    on. `ConsumerGone` for one id stops that id, which then finishes `Cancelled`; tokens
///    already in flight for it may still be delivered and are recorded, not forwarded. A
///    generation cancelled before its `Admitted` was delivered also finishes `Cancelled`.
/// 5. An `Err` from `pump` is engine-wide (for example the engine died): every running
///    generation ends with that failure, and the instance is poisoned.
pub trait MultiEngine {
    /// Starts one generation.
    fn submit(
        &mut self,
        req: &GenerationRequest,
        control: ControlProbe,
    ) -> Result<(), EngineFailure>;

    /// Advances the running generations; see rule 2.
    fn pump(
        &mut self,
        sink: &mut dyn TaggedSink,
        wait: Duration,
    ) -> Result<Vec<Finished>, EngineFailure>;

    /// Generations submitted and not yet finished.
    fn running(&self) -> usize;
}

/// One [`EventLedger`] per running generation, for a driver of a [`MultiEngine`].
#[derive(Debug, Clone)]
pub struct LedgerSet {
    entries: Vec<(RequestId, EventLedger)>,
    capacity: usize,
}

impl LedgerSet {
    /// A set for an engine with `places` places (at least 1).
    pub fn new(places: u32) -> Self {
        let capacity = usize::try_from(places.max(1)).unwrap_or(usize::MAX);
        Self {
            entries: Vec::new(),
            capacity,
        }
    }

    /// Opens the ledger of a generation about to be submitted. Refused: an id already
    /// open (`Protocol`), and more open generations than places (`Unsupported`).
    pub fn open(
        &mut self,
        req: &GenerationRequest,
        desc: &EngineDescriptor,
    ) -> Result<(), EngineFailure> {
        if self.contains(req.rid) {
            return Err(EngineFailure::protocol(&format!(
                "request id {} is already running",
                req.rid
            )));
        }
        if self.entries.len() >= self.capacity {
            return Err(EngineFailure::unsupported(
                "a generation beyond the engine's places",
            ));
        }
        self.entries.push((req.rid, EventLedger::new(req, desc)));
        Ok(())
    }

    /// True when `rid` is open.
    pub fn contains(&self, rid: RequestId) -> bool {
        self.entries.iter().any(|(r, _)| *r == rid)
    }

    /// The ledger of `rid`.
    pub fn ledger(&self, rid: RequestId) -> Option<&EventLedger> {
        self.entries.iter().find(|(r, _)| *r == rid).map(|(_, l)| l)
    }

    /// Open generations.
    pub fn len(&self) -> usize {
        self.entries.len()
    }

    /// True when no generation is open.
    pub fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }

    /// A tagged sink that applies each generation's ledger before forwarding to
    /// `downstream`. An event for an id that is not open is dropped, as the donor drops
    /// lines of a request already gone.
    ///
    /// Behavior reference: project-maya serve/server.py:1052 at 7e68a30f.
    pub fn sink<'a>(&'a mut self, downstream: &'a mut dyn TaggedSink) -> LedgeredTaggedSink<'a> {
        LedgeredTaggedSink {
            set: self,
            downstream,
        }
    }

    /// Closes the generation `finished` names and returns its result through its ledger.
    /// An id that is not open is a `Protocol` failure.
    pub fn finish(
        &mut self,
        finished: Finished,
    ) -> Result<(Terminal, LedgerCounts), EngineFailure> {
        let Some(at) = self.entries.iter().position(|(r, _)| *r == finished.rid) else {
            return Err(EngineFailure::protocol(&format!(
                "request id {} finished but is not running",
                finished.rid
            )));
        };
        let (_, mut ledger) = self.entries.swap_remove(at);
        ledgered_finish(&mut ledger, finished.outcome)
    }

    /// Ends every open generation with `failure` (an engine-wide failure from `pump`),
    /// each with its own accepted token count, and empties the set.
    pub fn fail_all(&mut self, failure: &EngineFailure) -> Vec<(RequestId, EngineFailure)> {
        self.entries
            .drain(..)
            .map(|(rid, ledger)| (rid, failure.clone().with_after_tokens(ledger.accepted())))
            .collect()
    }
}

/// The sink of [`LedgerSet::sink`].
pub struct LedgeredTaggedSink<'a> {
    set: &'a mut LedgerSet,
    downstream: &'a mut dyn TaggedSink,
}

impl TaggedSink for LedgeredTaggedSink<'_> {
    fn deliver(&mut self, rid: RequestId, event: EngineEvent) -> Result<(), DeliveryRefused> {
        let Some((_, ledger)) = self.set.entries.iter_mut().find(|(r, _)| *r == rid) else {
            return Ok(());
        };
        let downstream = &mut *self.downstream;
        ledgered_deliver(ledger, event, |e| downstream.deliver(rid, e))
    }
}

struct OneRid<'a> {
    rid: RequestId,
    sink: &'a mut dyn EventSink,
}

impl TaggedSink for OneRid<'_> {
    fn deliver(&mut self, rid: RequestId, event: EngineEvent) -> Result<(), DeliveryRefused> {
        if rid == self.rid {
            self.sink.deliver(event)
        } else {
            Ok(())
        }
    }
}

/// The blocking single-conversation form over the submit-and-pump form: submits `req`
/// on an idle engine and pumps until it finishes, forwarding its events to `sink`. A
/// multi-conversation engine can implement
/// [`EngineInstance::generate`](super::EngineInstance::generate) with it. Refused with
/// `Unsupported` when another generation is running; a `Protocol` failure when the engine
/// stops running the generation without returning its `Finished`.
pub fn generate_one(
    engine: &mut dyn MultiEngine,
    req: &GenerationRequest,
    control: &ControlProbe,
    sink: &mut dyn EventSink,
    wait: Duration,
) -> Result<Terminal, EngineFailure> {
    if engine.running() != 0 {
        return Err(EngineFailure::unsupported(
            "a blocking generation while other generations run",
        ));
    }
    engine.submit(req, control.clone())?;
    let mut one = OneRid { rid: req.rid, sink };
    loop {
        if let Some(finished) = engine.pump(&mut one, wait)?.into_iter().next() {
            if finished.rid == req.rid {
                return finished.outcome;
            }
            return Err(EngineFailure::protocol(&format!(
                "request id {} finished but was never submitted",
                finished.rid
            )));
        }
        // Rule 2 promises exactly one Finished: an engine that dropped the generation
        // without one would otherwise keep this loop pumping forever.
        if engine.running() == 0 {
            return Err(EngineFailure::protocol(&format!(
                "request id {} ended without a Finished",
                req.rid
            )));
        }
    }
}
