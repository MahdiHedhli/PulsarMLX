//! Successful-demand metadata model for synthetic two-slot cache comparisons.
mod input;
pub use input::{Source, Trace};
use serde::Serialize;
use sha2::{Digest, Sha256};
use std::{collections::VecDeque, io::Write, mem::size_of, str::FromStr};

pub type Result<T> = std::result::Result<T, String>;
pub const LIMIT: usize = 8 << 20;
pub const MAX_CALLS: usize = 4096;
pub const MAX_OCCURRENCES: usize = 65536;
const FIFO: usize = 64;
fn checked(a: u64, b: u64) -> Result<u64> {
    a.checked_add(b)
        .ok_or_else(|| "logical counter overflow".into())
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
pub enum Policy {
    AdmitAll,
    TwoHit,
}
impl FromStr for Policy {
    type Err = String;
    fn from_str(s: &str) -> Result<Self> {
        match s {
            "AdmitAll" => Ok(Self::AdmitAll),
            "TwoHit" => Ok(Self::TwoHit),
            _ => Err("unknown policy".into()),
        }
    }
}
#[derive(Debug, Serialize, PartialEq, Eq)]
pub struct Ledger {
    pub modeled_persistent_payload_bound: u64,
    pub modeled_transient_payload_bound: u64,
    pub catalog_bytes: u64,
    pub parsed_input_bytes: u64,
    pub history_capacity_bytes: u64,
    pub state_and_tickets_bytes: u64,
    pub event_capacity_bytes: u64,
    pub scratch_capacity_bytes: u64,
    pub report_capacity_bytes: u64,
    pub logical_total: u64,
}
impl Ledger {
    fn for_trace(t: &Trace) -> Result<Self> {
        let payload = t.tuple.checked_mul(2).ok_or("payload overflow")?;
        let catalog = std::mem::size_of_val(t.bindings.as_ref()) as u64;
        let parsed = t.input_bytes();
        let hist = (FIFO * size_of::<u16>()) as u64;
        let control = (size_of::<State>() + 2 * size_of::<Ticket>() + size_of::<Ledger>()) as u64;
        let events = (t.count * size_of::<Event>()) as u64;
        // Includes the transactional state copy, serialization framing, compact final state
        // and fixed hash-formatting buffers. Report encoding is charged separately.
        let scratch = 16384;
        let report = LIMIT as u64;
        let total = [
            payload, payload, catalog, parsed, hist, control, events, scratch, report,
        ]
        .into_iter()
        .try_fold(0, checked)?;
        Ok(Self {
            modeled_persistent_payload_bound: payload,
            modeled_transient_payload_bound: payload,
            catalog_bytes: catalog,
            parsed_input_bytes: parsed,
            history_capacity_bytes: hist,
            state_and_tickets_bytes: control,
            event_capacity_bytes: events,
            scratch_capacity_bytes: scratch,
            report_capacity_bytes: report,
            logical_total: total,
        })
    }
}
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
pub enum Category {
    R,
    M,
    #[serde(rename = "U_R")]
    RetainedReuse,
    #[serde(rename = "U_T")]
    TransientReuse,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
pub enum Kind {
    Persistent,
    Transient,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
pub struct Event {
    pub call: u16,
    pub wave: u64,
    pub expert: u16,
    pub category: Category,
    pub kind: Kind,
    pub slot: u8,
    pub generation: u64,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
pub struct Slot {
    pub expert: u16,
    pub generation: u64,
    pub recency: u64,
}
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize)]
pub struct Counts {
    pub occurrences: u64,
    pub waves: u64,
    pub r: u64,
    pub m: u64,
    pub u_r: u64,
    pub u_t: u64,
    pub admitted_fills: u64,
    pub bypasses: u64,
    pub persistent_evictions: u64,
    pub history_insertions: u64,
    pub history_evictions: u64,
    pub peak_persistent: u64,
    pub peak_transient: u64,
    pub peak_history: u64,
}
#[derive(Clone, Debug, Default, PartialEq, Eq, Serialize)]
pub struct State {
    pub slots: [Option<Slot>; 2],
    pub history: VecDeque<u16>,
    pub counts: Counts,
}
#[derive(Clone, Copy)]
struct Ticket {
    kind: Kind,
    slot: u8,
    generation: u64,
    hit: bool,
    seen: bool,
}
impl State {
    fn wave(
        &mut self,
        policy: Policy,
        call: u16,
        word: &[u16],
        ids: &[u16],
        events: &mut Vec<Event>,
    ) -> Result<()> {
        let epoch = checked(self.counts.waves, 1)?;
        let prior = ids.iter().map(|id| {
            self.slots
                .iter()
                .position(|s| s.is_some_and(|s| s.expert == *id))
        });
        let mut tickets = [Ticket {
            kind: Kind::Transient,
            slot: 0,
            generation: epoch,
            hit: false,
            seen: false,
        }; 2];
        let mut protected = [false; 2];
        for (i, s) in prior.enumerate() {
            if let Some(slot) = s {
                protected[slot] = true;
                tickets[i] = Ticket {
                    kind: Kind::Persistent,
                    slot: slot as u8,
                    generation: self.slots[slot].unwrap().generation,
                    hit: true,
                    seen: false,
                };
            }
        }
        let mut transient = 0;
        for (i, &id) in ids.iter().enumerate() {
            if tickets[i].hit {
                continue;
            }
            self.counts.m = checked(self.counts.m, 1)?;
            if policy == Policy::AdmitAll || self.history.contains(&id) {
                let slot = (0..2)
                    .filter(|&s| !protected[s])
                    .min_by_key(|&s| (self.slots[s].map(|v| v.recency), s))
                    .ok_or("no unprotected slot")?;
                let generation = checked(self.slots[slot].map_or(0, |v| v.generation), 1)?;
                if self.slots[slot].is_some() {
                    self.counts.persistent_evictions =
                        checked(self.counts.persistent_evictions, 1)?;
                }
                self.slots[slot] = Some(Slot {
                    expert: id,
                    generation,
                    recency: 0,
                });
                protected[slot] = true;
                tickets[i].kind = Kind::Persistent;
                tickets[i].slot = slot as u8;
                tickets[i].generation = generation;
                self.counts.admitted_fills = checked(self.counts.admitted_fills, 1)?;
            } else {
                tickets[i].slot = transient;
                transient += 1;
                self.counts.bypasses = checked(self.counts.bypasses, 1)?;
            }
        }
        self.counts.peak_transient = self.counts.peak_transient.max(u64::from(transient));
        self.counts.peak_persistent = self
            .counts
            .peak_persistent
            .max(self.slots.iter().flatten().count() as u64);
        for &id in word {
            let t = &mut tickets[usize::from(id != ids[0])];
            self.counts.occurrences = checked(self.counts.occurrences, 1)?;
            let category = if t.hit {
                self.counts.r = checked(self.counts.r, 1)?;
                Category::R
            } else if !t.seen {
                Category::M
            } else if t.kind == Kind::Transient {
                self.counts.u_t = checked(self.counts.u_t, 1)?;
                Category::TransientReuse
            } else {
                self.counts.u_r = checked(self.counts.u_r, 1)?;
                Category::RetainedReuse
            };
            if t.kind == Kind::Persistent {
                self.slots[t.slot as usize].as_mut().unwrap().recency = self.counts.occurrences;
            }
            t.seen = true;
            events.push(Event {
                call,
                wave: epoch,
                expert: id,
                category,
                kind: t.kind,
                slot: t.slot,
                generation: t.generation,
            });
        }
        if policy == Policy::TwoHit {
            self.history.retain(|id| {
                !ids.iter()
                    .zip(tickets)
                    .any(|(k, t)| k == id && t.kind == Kind::Persistent)
            });
            for (&id, t) in ids.iter().zip(tickets) {
                if t.kind == Kind::Transient {
                    if self.history.len() == FIFO {
                        self.history.pop_front();
                        self.counts.history_evictions = checked(self.counts.history_evictions, 1)?;
                    }
                    self.history.push_back(id);
                    self.counts.history_insertions = checked(self.counts.history_insertions, 1)?;
                }
            }
            self.counts.peak_history = self.counts.peak_history.max(self.history.len() as u64);
        }
        self.counts.waves = epoch;
        Ok(())
    }
    fn apply_call(
        &mut self,
        policy: Policy,
        index: u16,
        mut call: &[u16],
        events: &mut Vec<Event>,
    ) -> Result<()> {
        // No caller-visible mutation until every wave in this call has succeeded.
        let mut next = self.clone();
        next.history.reserve_exact(FIFO - next.history.len());
        let marker = events.len();
        while !call.is_empty() {
            let first = call[0];
            let mut ids = [first; 2];
            let mut n = 1;
            let mut end = 0;
            for &id in call {
                if !ids[..n].contains(&id) {
                    if n == 2 {
                        break;
                    }
                    ids[n] = id;
                    n += 1;
                }
                end += 1;
            }
            if let Err(e) = next.wave(policy, index, &call[..end], &ids[..n], events) {
                events.truncate(marker);
                return Err(e);
            }
            call = &call[end..];
        }
        *self = next;
        Ok(())
    }
}
#[derive(Debug, Serialize)]
pub struct Metrics {
    pub materializations: u64,
    pub demanded_bytes: u64,
    pub component_read_calls: u64,
    pub issued_bytes: u64,
    pub persistent_hit_bytes: u64,
    pub retained_reuse_bytes: u64,
    pub transient_reuse_bytes: u64,
    pub read_avoidance_hits: u64,
    pub read_avoidance_bytes: u64,
    pub persistent_hit_ratio: [u64; 2],
    pub read_avoidance_ratio: [u64; 2],
    pub final_persistent: u64,
    pub final_transient: u64,
    pub final_history: u64,
}
impl Metrics {
    fn new(s: &State, size: u64) -> Result<Self> {
        let c = s.counts;
        let hits = checked(c.r, checked(c.u_r, c.u_t)?)?;
        if checked(hits, c.m)? != c.occurrences || checked(c.bypasses, c.admitted_fills)? != c.m {
            return Err("disjoint count invariant".into());
        }
        let bytes = |n: u64| n.checked_mul(size).ok_or("logical byte count overflow");
        Ok(Self {
            materializations: c.m,
            demanded_bytes: bytes(c.occurrences)?,
            component_read_calls: c.m.checked_mul(9).ok_or("read count overflow")?,
            issued_bytes: bytes(c.m)?,
            persistent_hit_bytes: bytes(c.r)?,
            retained_reuse_bytes: bytes(c.u_r)?,
            transient_reuse_bytes: bytes(c.u_t)?,
            read_avoidance_hits: hits,
            read_avoidance_bytes: bytes(hits)?,
            persistent_hit_ratio: [c.r, c.occurrences],
            read_avoidance_ratio: [hits, c.occurrences],
            final_persistent: s.slots.iter().flatten().count() as u64,
            final_transient: 0,
            final_history: s.history.len() as u64,
        })
    }
}
fn digest_prefix(tag: &[u8], t: &Trace, p: Policy) -> Sha256 {
    let mut h = Sha256::new();
    h.update(tag);
    h.update(t.input);
    h.update(t.domain);
    h.update([if p == Policy::AdmitAll { 0 } else { 1 }]);
    h
}
#[derive(Debug, Serialize)]
pub struct Report<'a> {
    pub schema: &'static str,
    pub provenance_kind: &'static str,
    pub policy: Policy,
    pub source: &'a Source,
    pub input_sha256: String,
    pub domain_sha256: String,
    /// Catalog index is the expert ID. Each event's full identity is this bound domain plus its index and binding.
    #[serde(serialize_with = "binding_list")]
    pub catalog: &'a [[u8; 32]],
    pub ledger: Ledger,
    pub events: Vec<Event>,
    pub state: State,
    pub metrics: Metrics,
    pub event_sha256: String,
    pub state_sha256: String,
}
fn binding_list<S: serde::Serializer>(
    catalog: &[[u8; 32]],
    serializer: S,
) -> std::result::Result<S::Ok, S::Error> {
    use serde::ser::SerializeSeq;
    let mut seq = serializer.serialize_seq(Some(catalog.len()))?;
    for hash in catalog {
        seq.serialize_element(&input::hex(hash))?;
    }
    seq.end()
}
pub fn screen(trace: &Trace, policy: Policy, available: u64) -> Result<Report<'_>> {
    let ledger = trace.ledger()?;
    if available < ledger.logical_total {
        return Err("insufficient comparison budget".into());
    }
    let mut state = State {
        history: VecDeque::with_capacity(FIFO),
        ..Default::default()
    };
    let mut events = Vec::new();
    events
        .try_reserve_exact(trace.count)
        .map_err(|e| e.to_string())?;
    if events.capacity() != trace.count {
        return Err("event storage capacity".into());
    }
    for (i, call) in trace.calls().enumerate() {
        state.apply_call(policy, i as u16, call, &mut events)?;
    }
    let metrics = Metrics::new(&state, trace.tuple)?;
    let mut h = digest_prefix(b"admission-screen.events/1\0", trace, policy);
    for e in &events {
        h.update(e.call.to_le_bytes());
        h.update(e.wave.to_le_bytes());
        h.update(e.expert.to_le_bytes());
        let category = match e.category {
            Category::R => 0,
            Category::M => 1,
            Category::RetainedReuse => 2,
            Category::TransientReuse => 3,
        };
        h.update([category, u8::from(e.kind == Kind::Transient), e.slot]);
        h.update(e.generation.to_le_bytes());
    }
    let event_sha256 = format!("{:x}", h.finalize());
    let mut h = digest_prefix(b"admission-screen.state/1\0", trace, policy);
    h.update(serde_json::to_vec(&state).map_err(|e| e.to_string())?);
    Ok(Report {
        schema: "pulsarmlx.admission-screen.report/1",
        provenance_kind: "synthetic",
        policy,
        source: &trace.source,
        input_sha256: input::hex(&trace.input),
        domain_sha256: input::hex(&trace.domain),
        catalog: &trace.bindings,
        ledger,
        events,
        state,
        metrics,
        event_sha256,
        state_sha256: format!("{:x}", h.finalize()),
    })
}
struct Bounded(Vec<u8>, usize);
impl Write for Bounded {
    fn write(&mut self, buf: &[u8]) -> std::io::Result<usize> {
        if buf.len() > self.1 - self.0.len() {
            return Err(std::io::Error::other("report size limit"));
        }
        self.0.extend_from_slice(buf);
        Ok(buf.len())
    }
    fn flush(&mut self) -> std::io::Result<()> {
        Ok(())
    }
}
impl Report<'_> {
    /// Encode into a bounded payload before publishing any bytes to a caller.
    pub fn encode(&self, limit: usize) -> Result<Vec<u8>> {
        let max = limit.min(LIMIT);
        let mut out = Vec::new();
        out.try_reserve_exact(max).map_err(|e| e.to_string())?;
        if out.capacity() != max {
            return Err("report capacity".into());
        }
        let mut dst = Bounded(out, max);
        serde_json::to_writer(&mut dst, self).map_err(|e| e.to_string())?;
        dst.write_all(b"\n").map_err(|e| e.to_string())?;
        Ok(dst.0)
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn admission_screen_counter_and_generation_overflow_are_atomic() {
        for fault in 0..3 {
            let mut s = State::default();
            match fault {
                0 => s.counts.occurrences = u64::MAX - 1,
                1 => {
                    s.slots = [Some(Slot {
                        expert: 1,
                        generation: u64::MAX,
                        recency: 0,
                    }); 2]
                }
                _ => s.counts.waves = u64::MAX,
            };
            let was = s.clone();
            let mut events = vec![];
            assert!(s
                .apply_call(Policy::AdmitAll, 0, &[0, 0], &mut events)
                .is_err());
            assert_eq!(s, was);
            assert!(events.is_empty());
        }
        let mut s = State::default();
        s.counts.occurrences = u64::MAX;
        s.counts.r = u64::MAX;
        assert!(Metrics::new(&s, 2).is_err());
    }
    #[test]
    fn admission_screen_equal_recency_uses_lower_slot() {
        let mut s = State {
            slots: [
                Some(Slot {
                    expert: 1,
                    generation: 3,
                    recency: 5,
                }),
                Some(Slot {
                    expert: 2,
                    generation: 4,
                    recency: 5,
                }),
            ],
            ..Default::default()
        };
        let mut events = vec![];
        s.apply_call(Policy::AdmitAll, 0, &[0], &mut events)
            .unwrap();
        assert_eq!((events[0].slot, events[0].generation), (0, 4));
    }
}
