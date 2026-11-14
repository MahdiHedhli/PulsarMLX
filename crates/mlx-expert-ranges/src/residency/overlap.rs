//! Opt-in serial or one-wave-ahead transport over the actual two-slot cache.
use super::*;
use serde::Serialize;
use std::{
    sync::{
        atomic::{AtomicBool, Ordering},
        mpsc::{sync_channel, Receiver, SyncSender, TrySendError},
    },
    thread::{self, ThreadId},
};

const CONTROL: u64 = 2 << 20;
const STACK: usize = 2 << 20;
const EVENT_LIMIT: usize = 2048;
const REPORT_LIMIT: usize = 1 << 20;
type Parts = [[Vec<u8>; 3]; 3];
type Lengths = [[usize; 3]; 3];
type Banks = [Parts; 2];
type StageResult = std::result::Result<(), CacheFailure>;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
pub enum Mode {
    Serial,
    Overlap,
}
#[derive(Clone, Copy, Debug, Serialize)]
pub struct PipelineLedger {
    pub tuple_bytes: u64,
    pub metadata_bytes: u64,
    pub cache_bytes: u64,
    pub staging_bytes: u64,
    pub control_bytes: u64,
    pub stack_bytes: u64,
    pub total: u64,
    pub control_required: u64,
    pub names_and_plans: u64,
    pub events_bytes: u64,
    pub channels_and_fixed: u64,
    pub live_report_limit: usize,
    pub component_capacities: Lengths,
}
#[derive(Clone, Copy, Debug, Default, Serialize, PartialEq, Eq)]
pub struct Activity {
    pub spawned: u64,
    pub joined: u64,
    pub requests: u64,
    pub completions: u64,
    pub cancelled_jobs: u64,
    pub verified_roles: u64,
    pub verified_components: u64,
    pub verified_bytes: u64,
    pub copy_operations: u64,
    pub copied_bytes: u64,
    pub attempted_reads: u64,
    pub requested_bytes: u64,
    pub discarded_issued_bytes: u64,
    pub request_high_water: u8,
    pub completion_high_water: u8,
    pub outstanding: bool,
    pub banks_home: bool,
}
#[derive(Clone, Copy, Debug, Serialize)]
pub struct Event {
    pub phase: &'static str,
    pub invocation: u64,
    pub wave: u8,
    pub bank: u8,
    pub generation: u64,
    pub expert: u32,
    pub binding: Hash256,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct Stamp {
    owner: u64,
    invocation: u64,
    epoch: u64,
    wave: u8,
    bank: u8,
    generation: u64,
    demand: Demand,
    content: Hash256,
    lengths: Lengths,
    hashes: TupleHashes,
}
type Stamps = [Option<Stamp>; 2];
struct Job {
    tickets: Stamps,
    banks: Banks,
}
struct Completion {
    job: Job,
    error: Option<Refusal>,
    panicked: bool,
    cancelled: bool,
    verified_roles: u64,
    verified_bytes: u64,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Point {
    Before,
    Role(usize),
    Verified,
}
#[cfg(test)]
type Hook = Option<Arc<dyn Fn(u8, u8, Point) + Send + Sync>>;
#[cfg(not(test))]
type Hook = ();
fn observe(h: &Hook, wave: u8, bank: u8, p: Point) {
    #[cfg(test)]
    if let Some(f) = h {
        f(wave, bank, p);
    }
    #[cfg(not(test))]
    let _ = (h, wave, bank, p);
}
fn execute_job(
    source: &BoundedSource,
    class: &ExpertRequest,
    mut job: Job,
    cancelled: &impl Fn() -> bool,
    h: &Hook,
) -> Completion {
    let (mut roles, mut bytes) = (0, 0);
    let observed_cancel = std::cell::Cell::new(false);
    let poll = || {
        let value = cancelled();
        if value {
            observed_cancel.set(true);
        }
        value
    };
    let result = catch_unwind(AssertUnwindSafe(|| -> Result<()> {
        for stamp in job.tickets.into_iter().flatten() {
            check_cancel(&mut || poll())?;
            observe(h, stamp.wave, stamp.bank, Point::Before);
            let plan = CopiedResidency::plan_for(
                source,
                class,
                stamp.demand,
                stamp.content,
                &stamp.hashes,
            )?;
            plan.validate_source()?;
            fill_parts(
                &plan,
                &stamp.hashes,
                &mut job.banks[stamp.bank as usize],
                &mut || poll(),
                |role| {
                    roles += 1;
                    bytes += stamp.lengths[role.index()].iter().sum::<usize>() as u64;
                    observe(h, stamp.wave, stamp.bank, Point::Role(role.index()));
                },
            )?;
            observe(h, stamp.wave, stamp.bank, Point::Verified);
        }
        Ok(())
    }));
    let (error, panicked) = match result {
        Ok(r) => (r.err(), false),
        Err(_) => (
            Some(refusal("WORKER", "reader panicked; ownership quarantined")),
            true,
        ),
    };
    Completion {
        job,
        error,
        panicked,
        cancelled: observed_cancel.get(),
        verified_roles: roles,
        verified_bytes: bytes,
    }
}
fn same_source<T: Send + Sync>(source: &Arc<T>) -> Arc<T> {
    Arc::clone(source)
}
fn stage_error(detail: &str) -> Refusal {
    refusal("STAGING", detail)
}
fn total_charge(cache: u64, tuple: u64) -> Result<u64> {
    add(add(cache, mul(2, tuple)?)?, CONTROL + STACK as u64)
}

pub struct StagedResidency {
    cache: CopiedResidency,
    banks: Option<Banks>,
    mode: Mode,
    ledger: PipelineLedger,
    invocation: u64,
    epoch: u64,
    generations: [u64; 2],
    expected: Option<Stamps>,
    activity: Activity,
    events: Vec<Event>,
    reader: Option<ThreadId>,
    hook: Hook,
}
impl StagedResidency {
    /// Reject the complete standing charge before allocating either staging bank.
    pub fn new(cache: CopiedResidency, mode: Mode, available: u64) -> Result<Self> {
        if cache.is_quarantined() {
            return Err(refusal("QUARANTINE", "input cache unavailable"));
        }
        let l = cache.ledger();
        let total = total_charge(l.working_bytes, l.tuple_bytes)?;
        bounded(total, available, "standing staging envelope")?;
        let cap = cache.slots[0]
            .parts
            .each_ref()
            .map(|r| r.each_ref().map(Vec::capacity));
        let max_name = cache
            .class
            .modules
            .iter()
            .map(String::len)
            .chain(
                cache
                    .source
                    .checkpoint
                    .shards()
                    .iter()
                    .map(|s| s.file_name.len()),
            )
            .chain([cache.source.checkpoint.root_name().len()])
            .max()
            .unwrap_or(0) as u64;
        let names = add(64 << 10, mul(96, add(max_name, 32)?)?)?;
        // Covers channel nodes, cloned class and held Arc, stack-side job/ticket
        // copies, owner verification, bounded receipt/hash strings and diagnostics.
        let fixed = add(
            64 << 10,
            8 * (size_of::<Completion>() + size_of::<Stamps>()) as u64,
        )?;
        let event_bytes = mul(EVENT_LIMIT as u64, size_of::<Event>() as u64)?;
        let required = add(add(names, fixed)?, add(event_bytes, REPORT_LIMIT as u64)?)?;
        bounded(required, CONTROL, "staging control capacity")?;
        let mut events = Vec::new();
        events
            .try_reserve_exact(EVENT_LIMIT)
            .map_err(|e| refusal("ALLOCATION", e))?;
        if events.capacity() != EVENT_LIMIT {
            return Err(refusal("BUDGET", "bounded stage events"));
        }
        let banks = [Slot::allocate(cap)?.parts, Slot::allocate(cap)?.parts];
        let ledger = PipelineLedger {
            tuple_bytes: l.tuple_bytes,
            metadata_bytes: l.metadata_bytes,
            cache_bytes: l.working_bytes,
            staging_bytes: 2 * l.tuple_bytes,
            control_bytes: CONTROL,
            stack_bytes: STACK as u64,
            total,
            control_required: required,
            names_and_plans: names,
            channels_and_fixed: fixed,
            events_bytes: event_bytes,
            live_report_limit: REPORT_LIMIT,
            component_capacities: cap,
        };
        Ok(Self {
            cache,
            mode,
            banks: Some(banks),
            ledger,
            invocation: 0,
            epoch: 0,
            generations: [0; 2],
            expected: None,
            events,
            reader: None,
            hook: Default::default(),
            activity: Activity {
                banks_home: true,
                ..Default::default()
            },
        })
    }
    pub fn cache(&self) -> &CopiedResidency {
        &self.cache
    }
    pub fn demand(&self, e: u32) -> Result<Demand> {
        self.cache.demand(e)
    }
    pub fn working_bytes(&self) -> u64 {
        self.ledger.total
    }
    pub fn ledger(&self) -> PipelineLedger {
        self.ledger
    }
    pub fn activity(&self) -> Activity {
        self.activity
    }
    /// Bounded evidence for the most recently admitted invocation.
    pub fn events(&self) -> &[Event] {
        &self.events
    }
    pub fn reader_thread(&self) -> Option<ThreadId> {
        self.reader
    }
    pub fn quarantine(&mut self) {
        self.cache.quarantine()
    }
    pub fn finish(&mut self) -> Result<()> {
        if self.expected.is_some()
            || self.banks.is_none()
            || self.activity.joined != self.activity.spawned
        {
            self.quarantine();
            return Err(refusal("QUARANTINE", "unresolved reader or banks"));
        }
        self.cache.finish()
    }
    fn preflight(&self, demand: &[Demand]) -> Result<()> {
        self.cache.validate_demand(demand)?;
        if self.expected.is_some() || self.banks.is_none() {
            return Err(stage_error("outstanding staging ownership"));
        }
        let n = demand.len() as u64;
        add(self.invocation, 1)?;
        add(self.epoch, 2)?;
        for &g in &self.generations {
            add(g, n)?;
        }
        for slot in &self.cache.slots {
            add(slot.generation, n)?;
        }
        let a = self.activity;
        for v in [
            a.spawned,
            a.joined,
            a.requests,
            a.completions,
            a.cancelled_jobs,
        ] {
            add(v, n)?;
        }
        for v in [
            a.copy_operations,
            a.verified_components,
            a.attempted_reads,
            a.verified_roles,
        ] {
            add(v, mul(9, n)?)?;
        }
        for v in [
            a.copied_bytes,
            a.verified_bytes,
            a.requested_bytes,
            a.discarded_issued_bytes,
        ] {
            add(v, mul(self.ledger.tuple_bytes, n)?)?;
        }
        // Four ticket transitions per miss (submit, returned, validated, installed).
        bounded(
            mul(n, 4)?,
            self.events.capacity() as u64,
            "call event capacity",
        )
    }
    fn log(&mut self, phase: &'static str, s: Stamp) {
        self.events.push(Event {
            phase,
            invocation: s.invocation,
            wave: s.wave,
            bank: s.bank,
            generation: s.generation,
            expert: s.demand.key.expert,
            binding: s.demand.binding,
        });
    }
    /// Miss prediction only. No future victim, cache slot or lease is reserved.
    fn submit(&mut self, keys: [Option<Demand>; 2], wave: u8, tx: &SyncSender<Job>) -> Result<()> {
        if self.expected.is_some() {
            return Err(stage_error("one outstanding job maximum"));
        }
        let mut tickets = [None, None];
        let mut n = 0;
        for d in keys.into_iter().flatten() {
            if self
                .cache
                .slots
                .iter()
                .any(|s| matches!(s.state,State::Ready(t)|State::Leased(t) if t.demand==d))
            {
                continue;
            }
            let generation = add(self.generations[n], 1)?;
            tickets[n] = Some(Stamp {
                owner: self.cache.owner,
                invocation: self.invocation,
                epoch: self.epoch,
                wave,
                bank: n as u8,
                generation,
                demand: d,
                content: self.cache.content,
                lengths: self.ledger.component_capacities,
                hashes: self.cache.bindings[d.key.expert as usize].hashes,
            });
            n += 1;
        }
        if n == 0 {
            return Ok(());
        }
        let banks = self
            .banks
            .take()
            .ok_or_else(|| stage_error("missing banks"))?;
        match tx.try_send(Job { banks, tickets }) {
            Ok(()) => {
                self.expected = Some(tickets);
                self.activity.requests += 1;
                self.activity.request_high_water = 1;
                self.activity.outstanding = true;
                self.activity.banks_home = false;
                for s in tickets.into_iter().flatten() {
                    self.generations[s.bank as usize] = s.generation;
                    self.log("submit", s);
                }
                Ok(())
            }
            Err(e) => {
                let (job, why) = match e {
                    TrySendError::Full(j) => (j, "request queue full"),
                    TrySendError::Disconnected(j) => (j, "reader disconnected"),
                };
                self.banks = Some(job.banks);
                Err(stage_error(why))
            }
        }
    }
    fn receive(&mut self, rx: &Receiver<Completion>) -> Result<Stamps> {
        let Some(expected) = self.expected.take() else {
            self.quarantine();
            return Err(stage_error("unexpected or duplicate completion"));
        };
        let done = rx.recv().map_err(|_| {
            self.quarantine();
            stage_error("reader lost banks")
        })?;
        self.activity.completions += 1;
        self.activity.cancelled_jobs += u64::from(done.cancelled);
        self.activity.completion_high_water = 1;
        self.activity.outstanding = false;
        self.activity.verified_roles += done.verified_roles;
        self.activity.verified_components += 3 * done.verified_roles;
        self.activity.verified_bytes += done.verified_bytes;
        let actual = done.job.tickets;
        self.banks = Some(done.job.banks);
        self.activity.banks_home = true;
        for s in expected.into_iter().flatten() {
            self.log("returned", s);
        }
        if done.panicked || actual != expected {
            self.quarantine();
            return Err(if actual != expected {
                stage_error("completion identity mismatch")
            } else {
                done.error.unwrap_or_else(|| stage_error("worker panic"))
            });
        }
        if let Some(e) = done.error {
            return Err(if done.cancelled {
                refusal("CANCELLED", "reader observed cancellation")
            } else {
                e
            });
        }

        Ok(expected)
    }
    fn accept(
        &mut self,
        wave: u8,
        keys: [Option<Demand>; 2],
        leases: &mut [Option<Ticket>; 2],
        rx: &Receiver<Completion>,
        cancelled: &impl Fn() -> bool,
    ) -> Result<[bool; 2]> {
        let mut fresh = [false; 2];
        let mut needed = keys
            .iter()
            .enumerate()
            .filter_map(|(i, d)| d.filter(|_| leases[i].is_none()));
        if self.expected.is_none() {
            if needed.next().is_some() {
                self.quarantine();
                return Err(stage_error("missing current-wave job"));
            }
            return Ok(fresh);
        }
        let stamps = self.receive(rx)?;
        check_cancel(&mut || cancelled())?;
        // Check *every* tuple and current source before assigning the first victim.
        for (i, s) in stamps.into_iter().flatten().enumerate() {
            if needed.next() != Some(s.demand)
                || s.wave != wave
                || s.bank as usize != i
                || s.invocation != self.invocation
                || s.epoch != self.epoch
                || s.owner != self.cache.owner
                || s.generation != self.generations[i]
                || s.content != self.cache.content
                || s.lengths != self.ledger.component_capacities
                || s.hashes != self.cache.bindings[s.demand.key.expert as usize].hashes
            {
                self.quarantine();
                return Err(stage_error("stale or crossed stage ticket"));
            }
            let bank = &self.banks.as_ref().unwrap()[i];
            self.cache.validate(s.demand)?;
            for (role, row) in bank.iter().enumerate() {
                for (part, data) in row.iter().enumerate() {
                    if data.len() != s.lengths[role][part]
                        || <Hash256>::from(Sha256::digest(data)) != s.hashes[role][part]
                    {
                        return Err(refusal("CONTENT", "staged component verification"));
                    }
                }
            }
            self.log("validated", s);
        }
        if needed.next().is_some() {
            self.quarantine();
            return Err(stage_error("incomplete stage job"));
        }
        check_cancel(&mut || cancelled())?;
        // The validated, immutable banks are owner-exclusive throughout installation.
        for s in stamps.into_iter().flatten() {
            self.cache.validate(s.demand)?;
        }
        for s in stamps.into_iter().flatten() {
            let ticket = self.cache.begin_fill(s.demand)?;
            let bank = &self.banks.as_ref().unwrap()[s.bank as usize];
            for (dst, src) in self.cache.slots[ticket.slot]
                .parts
                .iter_mut()
                .flatten()
                .zip(bank.iter().flatten())
            {
                dst.copy_from_slice(src);
                self.activity.copy_operations += 1;
                self.activity.copied_bytes += src.len() as u64;
            }
            self.cache.commit_fill(ticket)?;
            let i = usize::from(keys[0] != Some(s.demand));
            leases[i] = Some(self.cache.acquire(ticket)?);
            fresh[i] = true;
            self.log("installed", s);
        }
        Ok(fresh)
    }
    fn run(
        &mut self,
        mut demand: &[Demand],
        tx: &SyncSender<Job>,
        rx: &Receiver<Completion>,
        cancelled: &impl Fn() -> bool,
        consumer: &mut impl FnMut(TupleView<'_>) -> Result<()>,
    ) -> StageResult {
        let mut ordinal = 0;
        while !demand.is_empty() {
            check_cancel(&mut || cancelled())?;
            let (wave, keys, rest) = split_wave(demand);
            let mut leases = [None, None];
            let future = if rest.is_empty() {
                None
            } else {
                Some(split_wave(rest).1)
            };
            let primary = (|| {
                self.cache.protect_hits(&keys, &mut leases)?;
                if ordinal == 0 {
                    check_cancel(&mut || cancelled())?;
                    self.submit(keys, ordinal, tx)?;
                }
                let fresh = self.accept(ordinal, keys, &mut leases, rx, cancelled)?;
                if self.mode == Mode::Overlap {
                    if let Some(k) = future {
                        check_cancel(&mut || cancelled())?;
                        self.submit(k, ordinal + 1, tx)?;
                    }
                }
                self.cache
                    .consume_wave(wave, &keys, &leases, fresh, &mut || cancelled(), consumer)
            })();
            self.cache.end_wave(primary, leases)?;
            if self.mode == Mode::Serial {
                if let Some(k) = future {
                    check_cancel(&mut || cancelled())?;
                    self.submit(k, ordinal + 1, tx)?;
                }
            }
            demand = rest;
            ordinal += 1;
        }
        Ok(())
    }
    /// A synchronous call from the owner. The cancellation predicate may run on
    /// either thread. The view and consumer never leave the caller's thread.
    pub fn consume(
        &mut self,
        demand: &[Demand],
        cancelled: impl Fn() -> bool + Sync,
        mut consumer: impl FnMut(TupleView<'_>) -> Result<()>,
    ) -> StageResult {
        self.preflight(demand)?;
        check_cancel(&mut || cancelled())?;
        let source = same_source(&self.cache.source);
        let class = self.cache.class.clone();
        #[allow(clippy::clone_on_copy)]
        let hook = self.hook.clone();
        let stop = AtomicBool::new(false);
        let (requests, jobs) = sync_channel::<Job>(1);
        let (returns, completed) = sync_channel::<Completion>(1);
        let before = (
            self.cache.read_calls(),
            self.cache.requested_bytes(),
            self.activity.copied_bytes,
        );
        self.invocation += 1;
        self.epoch += 1;
        self.events.clear();
        thread::scope(|scope| {
            let stop_ref = &stop;
            let external = &cancelled;
            let handle = thread::Builder::new()
                .name("copied-range-reader".into())
                .stack_size(STACK)
                .spawn_scoped(scope, move || {
                    while let Ok(job) = jobs.recv() {
                        let done = execute_job(
                            &source,
                            &class,
                            job,
                            &|| stop_ref.load(Ordering::Acquire) || external(),
                            &hook,
                        );
                        if returns.send(done).is_err() {
                            break;
                        }
                    }
                })
                .map_err(|e| refusal("WORKER", e))?;
            self.activity.spawned += 1;
            self.reader = Some(handle.thread().id());
            let outcome = catch_unwind(AssertUnwindSafe(|| {
                self.run(demand, &requests, &completed, &cancelled, &mut consumer)
            }));
            stop.store(true, Ordering::Release);
            self.epoch += 1;
            drop(requests);
            let cleanup = self
                .expected
                .is_some()
                .then(|| self.receive(&completed))
                .and_then(|v| v.err())
                .filter(|e| e.phase != "CANCELLED"); // Cancelling a drained speculative job is successful cleanup.
            drop(completed);
            let join = handle.join();
            self.activity.joined += 1;
            let mut cleanup = cleanup;
            if join.is_err() || self.banks.is_none() {
                self.quarantine();
                cleanup = Some(stage_error("reader or bank ownership unresolved"));
            }
            let reads = self.cache.read_calls() - before.0;
            let bytes = self.cache.requested_bytes() - before.1;
            self.activity.attempted_reads += reads;
            self.activity.requested_bytes += bytes;
            self.activity.discarded_issued_bytes += bytes - (self.activity.copied_bytes - before.2);
            match outcome {
                Err(panic) => {
                    self.quarantine();
                    resume_unwind(panic)
                }
                Ok(Err(mut failure)) => {
                    if failure.cleanup.is_none() {
                        failure.cleanup = cleanup
                    }
                    Err(failure)
                }
                Ok(Ok(())) => match cleanup {
                    Some(e) => Err(e.into()),
                    None => self.finish().map_err(Into::into),
                },
            }
        })
    }
}
#[cfg(test)]
mod tests;
