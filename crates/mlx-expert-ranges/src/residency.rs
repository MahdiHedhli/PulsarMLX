//! Two-slot serial storage for complete routed tuples. See the crate README.
use crate::{
    refusal, BoundedSource, ExpertPlan, ExpertRequest, ExpertRole, PlaneDestination, PlaneRecord,
    Refusal, Result, MAX_SELECTED_BYTES,
};
use expert_residency_core::{expert_residency::*, SlotId};
use sha2::{Digest, Sha256};
use std::{
    mem::size_of,
    panic::{catch_unwind, resume_unwind, AssertUnwindSafe},
};

pub const CONTROL_BYTES: u64 = 1 << 20;
pub const WORKSPACE_BYTES: u64 = 64 << 10;
pub const METADATA_LIMIT: u64 = 24 << 20;
pub const MAX_OCCURRENCES: usize = 64;
pub type Hash256 = [u8; 32];
pub type TupleHashes = [[Hash256; 3]; 3];

/// Per-checkpoint content authority supplied by the caller before any fill.
pub struct ContentAuthority<'a> {
    pub checkpoint: &'a str,
    pub metadata: &'a str,
    pub content: Hash256,
    pub hashes: &'a [TupleHashes],
}

/// Decode an externally supplied canonical SHA-256 before admitting its bytes.
pub fn parse_hash(s: &str) -> Result<Hash256> {
    if s.len() != 64
        || !s
            .bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
    {
        return Err(refusal("CONTENT", "expected a lowercase SHA-256"));
    }
    let mut out = [0; 32];
    for (i, v) in out.iter_mut().enumerate() {
        *v = u8::from_str_radix(&s[2 * i..2 * i + 2], 16).map_err(|e| refusal("CONTENT", e))?;
    }
    Ok(out)
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Demand {
    pub key: ExpertKey,
    pub binding: Hash256,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Ledger {
    pub tuple_bytes: u64,
    pub metadata_bytes: u64,
    pub control_bound: u64,
    pub working_bytes: u64,
}

#[derive(Default, Debug, Clone, Copy, PartialEq, Eq)]
pub struct CacheStats {
    pub fills: u64,
    pub hits: u64,
    pub evictions: u64,
    pub consumed: u64,
}

/// The callback can only borrow these initialized slices for one occurrence.
pub struct TupleView<'a> {
    pub demand: Demand,
    pub slot: SlotId,
    pub generation: u64,
    pub components: [[&'a [u8]; 3]; 3],
    pub hashes: &'a TupleHashes,
}

#[derive(Debug)]
pub struct CacheFailure {
    pub primary: Refusal,
    pub cleanup: Option<Refusal>,
}
impl From<Refusal> for CacheFailure {
    fn from(primary: Refusal) -> Self {
        Self {
            primary,
            cleanup: None,
        }
    }
}
impl std::fmt::Display for CacheFailure {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.primary)?;
        if let Some(e) = &self.cleanup {
            write!(f, ", cleanup: {e}")?
        }
        Ok(())
    }
}
impl std::error::Error for CacheFailure {}

struct Binding {
    digest: Hash256,
    hashes: TupleHashes,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct Ticket {
    owner: u64,
    lease_epoch: u64,
    demand: Demand,
    slot: usize,
    generation: u64,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum State {
    Free,
    Filling(Ticket),
    Ready(Ticket),
    Leased(Ticket),
    Quarantined,
}
struct Slot {
    parts: [[Vec<u8>; 3]; 3],
    state: State,
    generation: u64,
    recency: u64,
}

fn overflow() -> Refusal {
    refusal("OVERFLOW", "residency ledger or counter")
}
fn add(a: u64, b: u64) -> Result<u64> {
    a.checked_add(b).ok_or_else(overflow)
}
fn mul(a: u64, b: u64) -> Result<u64> {
    a.checked_mul(b).ok_or_else(overflow)
}
fn bounded(n: u64, limit: u64, why: &'static str) -> Result<()> {
    if n > limit {
        Err(refusal("BUDGET", why))
    } else {
        Ok(())
    }
}
fn standing_charge(tuple_bytes: u64, metadata_bytes: u64, available: u64) -> Result<u64> {
    bounded(metadata_bytes, METADATA_LIMIT, "source metadata")?;
    let total = add(
        add(mul(2, tuple_bytes)?, metadata_bytes)?,
        CONTROL_BYTES + WORKSPACE_BYTES,
    )?;
    bounded(total, available, "standing cache envelope")?;
    Ok(total)
}
fn table_error(e: ExpertAdmissionError) -> Refusal {
    refusal("RESIDENCY", format!("{e:?}"))
}

impl Slot {
    fn allocate(lengths: [[usize; 3]; 3]) -> Result<Self> {
        let mut parts = std::array::from_fn(|_| std::array::from_fn(|_| Vec::new()));
        for (role, lens) in parts.iter_mut().zip(lengths) {
            for (part, len) in role.iter_mut().zip(lens) {
                part.try_reserve_exact(len)
                    .map_err(|e| refusal("ALLOCATION", e))?;
                if part.capacity() != len {
                    return Err(refusal(
                        "BUDGET",
                        "component allocation exceeds admitted length",
                    ));
                }
                part.resize(len, 0);
            }
        }
        Ok(Self {
            parts,
            state: State::Free,
            generation: 0,
            recency: 0,
        })
    }
}

fn binding_digest(
    layer: u32,
    content: Hash256,
    plan: &ExpertPlan<'_>,
    hashes: &TupleHashes,
) -> Result<Hash256> {
    let mut digest = Sha256::new();
    digest.update(b"pulsarmlx.copied-residency/1");
    digest.update(layer.to_be_bytes());
    digest.update(content);
    for role in hashes {
        for hash in role {
            digest.update(hash);
        }
    }
    serde_json::to_writer(&mut digest, plan.record()).map_err(|e| refusal("PLAN", e))?;
    Ok(digest.finalize().into())
}

/// One source, one immutable class and externally admitted hash tuple per expert.
pub struct CopiedResidency {
    owner: u64,
    lease_epoch: u64,
    source: BoundedSource,
    class: ExpertRequest,
    layer: u32,
    content: Hash256,
    bindings: Vec<Binding>,
    slots: [Slot; 2],
    table: ExpertResidencyTable,
    ledger: Ledger,
    stats: CacheStats,
    poisoned: bool,
}

impl CopiedResidency {
    /// `class.expert` selects the representative geometry, while `hashes[i]`
    /// authorizes expert i. Source parsing precedes this allocation admission.
    pub fn new(
        source: BoundedSource,
        layer: u32,
        class: &ExpertRequest,
        authority: ContentAuthority<'_>,
        available: u64,
        workspace_required: u64,
    ) -> Result<Self> {
        let ContentAuthority {
            checkpoint,
            metadata,
            content,
            hashes,
        } = authority;
        if source.checkpoint.root_name() != checkpoint {
            return Err(refusal("SOURCE", "checkpoint name mismatch"));
        }
        if source.metadata_snapshot() != metadata {
            return Err(refusal("SOURCE", "metadata snapshot mismatch"));
        }
        let metadata_bytes = source.logical_metadata_bytes()?;
        bounded(metadata_bytes, METADATA_LIMIT, "source metadata")?;
        Self::check_workspace(workspace_required)?;
        if hashes.is_empty()
            || hashes.len() as u64 != class.experts
            || class.experts > u32::MAX as u64
        {
            return Err(refusal(
                "CONTENT",
                "one immutable binding per routed expert required",
            ));
        }
        // At most one plan, one plane receipt and one affine classification are
        // live at once. Allow 96 name buffers (including formatting spare), plus
        // 64 KiB for fixed records, two table entries, hashes and wave bookkeeping.
        let max_name = class
            .modules
            .iter()
            .map(String::len)
            .chain(source.checkpoint.shards().iter().map(|s| s.file_name.len()))
            .chain([source.checkpoint.root_name().len()])
            .max()
            .unwrap_or(0) as u64;
        let fixed = add(64 << 10, mul(96, add(max_name, 32)?)?)?;
        let control =
            |capacity: usize| add(fixed, mul(capacity as u64, size_of::<Binding>() as u64)?);
        bounded(
            control(hashes.len())?,
            CONTROL_BYTES,
            "binding and plan control payload",
        )?;
        // The affine planner owns temporary TensorMeta clones. Reject unsupported
        // ranks while shapes are still borrowed from the charged source catalog.
        for module in &class.modules {
            for suffix in ["weight", "scales", "biases"] {
                let name = format!("{module}.{suffix}");
                if source
                    .checkpoint
                    .catalog()
                    .get(&name)
                    .is_some_and(|t| t.shape.len() != 3)
                {
                    return Err(refusal(
                        "GEOMETRY",
                        "complete expert components require rank three",
                    ));
                }
            }
        }
        let representative = source.plan(class.clone())?;
        let tuple_bytes = representative.record().selected_bytes;
        if tuple_bytes == 0 || tuple_bytes > MAX_SELECTED_BYTES {
            return Err(refusal("BUDGET", "complete tuple size"));
        }
        let working_bytes = standing_charge(tuple_bytes, metadata_bytes, available)?;
        let mut lengths = [[0; 3]; 3];
        for (lens, plane) in lengths.iter_mut().zip(&representative.record().planes) {
            for (len, r) in lens.iter_mut().zip(&plane.ranges) {
                *len = usize::try_from(r.len).map_err(|_| overflow())?;
            }
        }
        drop(representative);
        let mut bindings = Vec::new();
        bindings
            .try_reserve_exact(hashes.len())
            .map_err(|e| refusal("ALLOCATION", e))?;
        let control_bound = control(bindings.capacity())?;
        bounded(control_bound, CONTROL_BYTES, "binding capacity")?;
        for (i, hashes) in hashes.iter().enumerate() {
            let plan = source.plan(ExpertRequest {
                expert: i as u64,
                ..class.clone()
            })?;
            for (lens, plane) in lengths.iter().zip(&plan.record().planes) {
                if !lens
                    .iter()
                    .zip(&plane.ranges)
                    .all(|(len, r)| *len as u64 == r.len)
                {
                    return Err(refusal("CLASS", "inconsistent tuple lengths"));
                }
            }
            plan.validate_source()?;
            bindings.push(Binding {
                digest: binding_digest(layer, content, &plan, hashes)?,
                hashes: *hashes,
            });
        }
        use std::sync::atomic::{AtomicU64, Ordering};
        static NEXT_OWNER: AtomicU64 = AtomicU64::new(1);
        let owner = NEXT_OWNER
            .fetch_update(Ordering::Relaxed, Ordering::Relaxed, |n| n.checked_add(1))
            .map_err(|_| overflow())?;
        let slots = [Slot::allocate(lengths)?, Slot::allocate(lengths)?];
        let policy = ExpertAdmissionPolicy::new(2 * tuple_bytes, 1, false, false)
            .ok_or_else(|| refusal("RESIDENCY", "invalid policy"))?;
        Ok(Self {
            source,
            owner,
            lease_epoch: 0,
            class: class.clone(),
            layer,
            content,
            bindings,
            slots,
            table: ExpertResidencyTable::new(policy),
            ledger: Ledger {
                tuple_bytes,
                metadata_bytes,
                control_bound,
                working_bytes,
            },
            stats: CacheStats::default(),
            poisoned: false,
        })
    }

    pub fn check_workspace(bytes: u64) -> Result<()> {
        bounded(bytes, WORKSPACE_BYTES, "executor workspace")
    }
    pub fn ledger(&self) -> Ledger {
        self.ledger
    }
    pub fn working_bytes(&self) -> u64 {
        self.ledger.working_bytes
    }
    pub fn resident_bytes(&self) -> u64 {
        self.table.resident_bytes()
    }
    pub fn stats(&self) -> CacheStats {
        self.stats
    }
    pub fn read_calls(&self) -> u64 {
        self.source.payload_read_calls()
    }
    pub fn requested_bytes(&self) -> u64 {
        self.source.requested_payload_bytes()
    }
    pub fn is_quarantined(&self) -> bool {
        self.poisoned
    }
    pub fn demand(&self, expert: u32) -> Result<Demand> {
        let binding = self
            .bindings
            .get(expert as usize)
            .ok_or_else(|| refusal("INDEX", "expert outside class"))?;
        Ok(Demand {
            key: ExpertKey {
                layer: self.layer,
                expert,
                kind: ExpertKind::Routed,
            },
            binding: binding.digest,
        })
    }
    fn validate_demand(&self, demand: &[Demand]) -> Result<()> {
        if self.poisoned {
            return Err(refusal("QUARANTINE", "cache unavailable"));
        }
        if demand.is_empty() || demand.len() > MAX_OCCURRENCES {
            return Err(refusal("DEMAND", "requires 1..=64 occurrences"));
        }
        for item in demand {
            if self.demand(item.key.expert)? != *item {
                return Err(refusal("CONTENT", "key or plan/content binding differs"));
            }
        }
        let n = demand.len() as u64;
        add(self.lease_epoch, n)?;
        for count in [
            self.stats.fills,
            self.stats.hits,
            self.stats.evictions,
            self.stats.consumed,
        ] {
            add(count, n)?;
        }
        add(self.read_calls(), mul(n, 9)?)?;
        add(self.requested_bytes(), mul(n, self.ledger.tuple_bytes)?)?;
        Ok(())
    }
    /// Mark uncertain completion/ownership. The pool stays charged until drop.
    pub fn quarantine(&mut self) {
        self.poisoned = true;
        for slot in &mut self.slots {
            slot.state = State::Quarantined;
        }
    }
    pub fn finish(&mut self) -> Result<()> {
        if self.poisoned
            || self
                .slots
                .iter()
                .any(|s| !matches!(s.state, State::Free | State::Ready(_)))
        {
            self.quarantine();
            return Err(refusal("QUARANTINE", "unresolved step or slot ownership"));
        }
        Ok(())
    }

    /// Consume each occurrence while its wave is protected. Callback borrows cannot escape.
    pub fn consume(
        &mut self,
        demand: &[Demand],
        mut cancelled: impl FnMut() -> bool,
        mut consumer: impl FnMut(TupleView<'_>) -> Result<()>,
    ) -> std::result::Result<(), CacheFailure> {
        self.validate_demand(demand)?;
        // If user code unwinds, no lease from this cache can be used again.
        match catch_unwind(AssertUnwindSafe(|| {
            self.run(demand, &mut cancelled, &mut consumer)
        })) {
            Ok(result) => result,
            Err(panic) => {
                self.quarantine();
                resume_unwind(panic)
            }
        }
    }
    fn run(
        &mut self,
        mut demand: &[Demand],
        cancelled: &mut impl FnMut() -> bool,
        consumer: &mut impl FnMut(TupleView<'_>) -> Result<()>,
    ) -> std::result::Result<(), CacheFailure> {
        while !demand.is_empty() {
            check_cancel(cancelled)?;
            let first = demand[0];
            let second = demand.iter().copied().find(|&d| d != first);
            let len = demand
                .iter()
                .position(|d| *d != first && Some(*d) != second)
                .unwrap_or(demand.len());
            let (wave, rest) = demand.split_at(len);
            let mut leases = [None, None];
            let primary = self.wave(
                wave,
                [Some(first), second],
                &mut leases,
                cancelled,
                consumer,
            );
            self.end_wave(primary, leases)?;
            demand = rest;
        }
        Ok(())
    }

    fn end_wave(
        &mut self,
        primary: Result<()>,
        leases: [Option<Ticket>; 2],
    ) -> std::result::Result<(), CacheFailure> {
        let mut cleanup = None;
        for ticket in leases.into_iter().flatten() {
            if let Err(e) = self.release(ticket) {
                cleanup = Some(e);
                self.quarantine();
                break;
            }
        }
        match (primary, cleanup) {
            (Err(primary), cleanup) => return Err(CacheFailure { primary, cleanup }),
            (Ok(()), Some(e)) => return Err(e.into()),
            (Ok(()), None) => {}
        }
        Ok(())
    }
    fn plan_for<'s>(
        source: &'s BoundedSource,
        class: &ExpertRequest,
        d: Demand,
        content: Hash256,
        hashes: &TupleHashes,
    ) -> Result<ExpertPlan<'s>> {
        let plan = source.plan(ExpertRequest {
            expert: u64::from(d.key.expert),
            ..class.clone()
        })?;
        if binding_digest(d.key.layer, content, &plan, hashes)? != d.binding {
            return Err(refusal("CONTENT", "sealed plan changed"));
        }
        Ok(plan)
    }
    fn wave(
        &mut self,
        wave: &[Demand],
        keys: [Option<Demand>; 2],
        leases: &mut [Option<Ticket>; 2],
        cancelled: &mut impl FnMut() -> bool,
        consumer: &mut impl FnMut(TupleView<'_>) -> Result<()>,
    ) -> Result<()> {
        let mut fresh = [false; 2];
        // Protect *all* hits, even those following a miss in occurrence order.
        for (i, d) in keys.iter().enumerate() {
            if let Some(d) = d {
                if let Some(ticket) = self.slots.iter().find_map(|s| match s.state {
                    State::Ready(t) if t.demand == *d => Some(t),
                    _ => None,
                }) {
                    self.validate(*d)?;
                    leases[i] = Some(self.acquire(ticket)?);
                }
            }
        }
        for (i, d) in keys.iter().enumerate() {
            if let Some(d) = d {
                if leases[i].is_none() {
                    let ticket = self.fill(*d, cancelled)?;
                    leases[i] = Some(self.acquire(ticket)?);
                    fresh[i] = true;
                }
            }
        }
        for d in wave {
            check_cancel(cancelled)?;
            self.validate(*d)?;
            let i = usize::from(keys[0] != Some(*d));
            let ticket = leases[i].ok_or_else(|| refusal("LEASE", "missing wave capability"))?;
            let slot = &self.slots[ticket.slot];
            if slot.state != State::Leased(ticket) || ticket.demand != *d {
                return Err(refusal("LEASE", "invalid view"));
            }
            consumer(TupleView {
                demand: *d,
                slot: SlotId(ticket.slot as u64),
                generation: ticket.generation,
                components: slot
                    .parts
                    .each_ref()
                    .map(|row| row.each_ref().map(Vec::as_slice)),
                hashes: &self.bindings[d.key.expert as usize].hashes,
            })?;
            self.stats.consumed += 1;
            self.slots[ticket.slot].recency = self.stats.consumed;
            if !fresh[i] {
                self.stats.hits += 1;
            }
            fresh[i] = false;
        }
        Ok(())
    }
    fn validate(&self, d: Demand) -> Result<()> {
        Self::plan_for(
            &self.source,
            &self.class,
            d,
            self.content,
            &self.bindings[d.key.expert as usize].hashes,
        )?
        .validate_source()
    }
    fn acquire(&mut self, t: Ticket) -> Result<Ticket> {
        if self.slots[t.slot].state != State::Ready(t) {
            return Err(refusal("LEASE", "acquire stale or busy slot"));
        }
        let epoch = add(self.lease_epoch, 1)?;
        self.table
            .transition(t.demand.key, ExpertLifecycle::Leased)
            .map_err(table_error)?;
        self.lease_epoch = epoch;
        let t = Ticket {
            lease_epoch: epoch,
            ..t
        };
        self.slots[t.slot].state = State::Leased(t);
        Ok(t)
    }
    fn release(&mut self, t: Ticket) -> Result<()> {
        if self.slots[t.slot].state != State::Leased(t) {
            return Err(refusal("LEASE", "stale or duplicate release"));
        }
        self.table
            .transition(t.demand.key, ExpertLifecycle::Available)
            .map_err(table_error)?;
        self.slots[t.slot].state = State::Ready(t);
        Ok(())
    }
    fn victim(&self) -> Result<usize> {
        self.slots
            .iter()
            .position(|s| s.state == State::Free)
            .or_else(|| {
                self.slots
                    .iter()
                    .enumerate()
                    .filter(|(_, s)| matches!(s.state, State::Ready(_)))
                    .min_by_key(|(i, s)| (s.recency, *i))
                    .map(|(i, _)| i)
            })
            .ok_or_else(|| refusal("LEASE", "no reusable slot"))
    }
    fn fill(&mut self, d: Demand, cancelled: &mut impl FnMut() -> bool) -> Result<Ticket> {
        check_cancel(cancelled)?;
        let index = self.victim()?;
        let hashes = &self.bindings[d.key.expert as usize].hashes;
        let plan = Self::plan_for(&self.source, &self.class, d, self.content, hashes)?;
        plan.validate_source()?;
        let slot = &mut self.slots[index];
        let ticket = Ticket {
            owner: self.owner,
            lease_epoch: 0,
            demand: d,
            slot: index,
            generation: add(slot.generation, 1)?,
        };
        if let State::Ready(old) = slot.state {
            self.table.evict(old.demand.key).map_err(table_error)?;
            self.stats.evictions += 1;
        }
        slot.state = State::Filling(ticket);
        slot.generation = ticket.generation;
        if let Err(e) = fill_parts(&plan, hashes, slot, cancelled) {
            slot.state = State::Free;
            return Err(e);
        }
        self.publish(ticket)?;
        self.stats.fills += 1;
        Ok(ticket)
    }
    fn publish(&mut self, t: Ticket) -> Result<()> {
        if self.slots[t.slot].state != State::Filling(t) {
            return Err(refusal("LEASE", "stale or duplicate publication"));
        }
        let req = ExpertAdmissionRequest {
            key: t.demand.key,
            tier: ExpertResidencyTier::CompressedResident,
            bytes: self.ledger.tuple_bytes,
            slot_id: SlotId(t.slot as u64),
            protected: false,
        };
        if let Err(error) = self.table.admit(req) {
            self.slots[t.slot].state = State::Free;
            return Err(table_error(error));
        }
        self.slots[t.slot].state = State::Ready(t);
        Ok(())
    }
}

fn check_cancel(cancelled: &mut impl FnMut() -> bool) -> Result<()> {
    if cancelled() {
        Err(refusal("CANCELLED", "ordered demand interrupted"))
    } else {
        Ok(())
    }
}
fn same_plane(a: &PlaneRecord, b: &PlaneRecord) -> bool {
    a.role == b.role
        && a.module == b.module
        && a.expert == b.expert
        && a.bits == b.bits
        && a.group_size == b.group_size
        && a.resolved_from == b.resolved_from
        && a.metadata_dtype == b.metadata_dtype
        && a.logical_shape == b.logical_shape
        && a.ranges.iter().zip(&b.ranges).all(|(a, b)| {
            a.tensor == b.tensor && a.shard == b.shard && a.begin == b.begin && a.len == b.len
        })
}
fn fill_parts(
    plan: &ExpertPlan<'_>,
    hashes: &TupleHashes,
    slot: &mut Slot,
    cancelled: &mut impl FnMut() -> bool,
) -> Result<()> {
    for role in [ExpertRole::Gate, ExpertRole::Up, ExpertRole::Down] {
        check_cancel(cancelled)?;
        let index = role.index();
        let expected = hashes[index].map(|hash| safetensors_catalog::hex(&hash));
        let [weights, scales, biases] = &mut slot.parts[index];
        let dest = PlaneDestination::new(weights, scales, biases, expected.clone());
        let receipt = plan.read_plane_into(role, dest)?.into_receipt();
        let plane = &plan.record().planes[index];
        if receipt.role != role
            || receipt.checkpoint != plan.record().checkpoint
            || receipt.metadata_snapshot_sha256 != plan.record().metadata_snapshot_sha256
            || receipt.actual_sha256 != expected
            || !same_plane(&receipt.plane, plane)
            || receipt.range_attempts != 3
            || receipt.requested_bytes != plane.ranges.iter().map(|r| r.len).sum::<u64>()
        {
            return Err(refusal(
                "CONTENT",
                "verified role receipt differs from admitted tuple",
            ));
        }
    }
    check_cancel(cancelled)?;
    plan.validate_source()
}

#[cfg(test)]
mod tests;
