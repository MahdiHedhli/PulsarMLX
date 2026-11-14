//! Fixed weighted execution on the bounded, joined raw-byte pipeline.
use super::*;
pub use mlx_expert_ranges::residency::overlap::Mode;
use mlx_expert_ranges::residency::overlap::StagedResidency;
pub const TRANSPORT: u64 = 1 << 20;
pub const TRANSPORT_ROW: usize = 128 << 10;

struct Journal {
    slots: [Vec<u8>; MAX_PLANS],
    used: usize,
}
impl Journal {
    fn new() -> Result<Self> {
        let mut slots = std::array::from_fn(|_| Vec::new());
        for slot in &mut slots {
            slot.try_reserve_exact(TRANSPORT_ROW)
                .map_err(|e| e.to_string())?;
            ensure(slot.capacity() == TRANSPORT_ROW, "transport capacity")?;
        }
        Ok(Self { slots, used: 0 })
    }

    fn capture(
        &mut self,
        cache: &StagedResidency,
        mode: Mode,
        position: u64,
        book: &str,
        request: &str,
    ) -> Result<()> {
        let slot = self
            .slots
            .get_mut(self.used)
            .ok_or("transport record limit")?;
        self.used += 1;
        let events = cache.events();
        // One fixed plan has at most three misses and four transitions per ticket.
        ensure(events.len() <= 12, "fixed ticket count")?;
        let row = json!({"schema":"staged-weighted-transport/1","mode":mode,"book":book,
            "request":request,"position":position,"activity":cache.activity(),"tickets":events,
            "residents":cache.cache().residents(),"reader_distinct":cache.reader_thread().is_some_and(|id| id != std::thread::current().id())});
        slot.resize(TRANSPORT_ROW, 0);
        let mut writer = Cursor::new(slot.as_mut_slice());
        if serde_json::to_writer(&mut writer, &row).is_err() {
            slot.clear();
            slot.extend_from_slice(br#"{"status":"transport record overflow"}"#);
            return Err("transport record overflow".into());
        }
        let used = writer.position() as usize;
        slot.truncate(used);
        Ok(())
    }
}
fn working_charge(pipeline: u64) -> Result<u64> {
    pipeline
        .checked_add(HOST_BYTES + TRANSPORT + NATIVE)
        .ok_or_else(|| "working charge overflow".into())
}
pub struct StagedWeightedExecutor<D: Driver> {
    book: RouteBook,
    population: Population,
    geo: Geometry,
    cache: StagedResidency,
    mode: Mode,
    transport: Journal,
    driver: D,
    total: u64,
    ledger: Value,
    records: Vec<Record>,
    pending: Option<Pending>,
    output: Option<LayerOutput>,
    cleanup: Option<String>,
    dispatches: u64,
    weighted: u64,
}
impl<D: Driver> StagedWeightedExecutor<D> {
    pub fn book(&self) -> &RouteBook {
        &self.book
    }
    pub fn ledger(&self) -> &Value {
        &self.ledger
    }
    /// Bounded caller-owned diagnostic export, outside semantic output.
    pub fn records(&self) -> impl Iterator<Item = (u64, Term, &[u8])> {
        self.records
            .iter()
            .map(|r| (r.position, (r.expert, r.weight), r.data.as_slice()))
    }
    pub fn transport_records(&self) -> impl Iterator<Item = &[u8]> {
        self.transport.slots[..self.transport.used]
            .iter()
            .map(Vec::as_slice)
    }
    pub fn snapshot(&self) -> Value {
        let cache = self.cache.cache();
        let s = cache.stats();
        json!({"cache_reads":cache.read_calls(),"transport_records":self.transport.used,"activity":self.cache.activity(),"mode":self.mode,
        "fills":s.fills,"hits":s.hits,"evictions":s.evictions,"consumed":s.consumed,"occupied":cache.resident_bytes(),
        "quarantined":self.cache.cache().is_quarantined(),"records":self.records.len(),"dispatches":self.dispatches,"weighted":self.weighted,
        "working_bytes":self.total,"pending":self.pending.is_some(),"output":self.output.is_some()})
    }
    fn compute(
        &mut self,
        req: LayerRequest,
        t: &CancellationToken,
    ) -> BackendResult<RuntimeBuffer> {
        let p = self
            .pending
            .as_ref()
            .ok_or_else(|| err("stage", "no staged request"))?;
        if self.output.is_some() || req.layer != LAYER || req.generation_position != p.position {
            return Err(err("stage", "layer or position"));
        }
        let terms = self.book.terms(p.position).map_err(|e| err("book", e))?;
        if self.records.len() + terms.len() > MAX_TERMS || self.transport.used >= MAX_PLANS {
            return Err(err("quota", "cumulative occurrence budget"));
        }
        let first = self.records.len();
        for &term in terms {
            self.records
                .push(Record::reserve(p.position, term).map_err(|e| err("row", e))?);
        }
        self.dispatches += 1;
        let pop = &self.population;
        let mut next = 0;
        let mut sum = Some(WeightedSum::default());
        let mut primary = None;
        let mut release_error = None;
        let mut consume = |d: Demand,
                           slot: Option<(u64, u64)>,
                           parts: Slices<'_>,
                           hashes: &TupleHashes|
         -> Result<()> {
            let &(expert, weight) = terms.get(next).ok_or("excess occurrence")?;
            ensure(
                p.keys[next] == d
                    && d.key.expert == expert
                    && d.key.layer == LAYER
                    && *hashes == pop.hashes[expert as usize],
                "ordered tuple binding",
            )?;
            let ordinal = first + next;
            next += 1;
            let record = &mut self.records[ordinal];
            record.data.clear();
            record
                .data
                .extend_from_slice(br#"{"status":"interrupted"}"#);
            let mut row = json!({"ordinal":ordinal,"position":p.position,"expert":expert,"weight_bits":weight,"slot_generation":slot,"recipe":pop.profile});
            let result = occurrence(
                &mut self.driver,
                self.geo,
                parts,
                hashes,
                d,
                &p.input,
                t,
                &mut row,
            )
            .and_then(|out| {
                sum = Some(
                    sum.take()
                        .ok_or_else(|| Fault::clean("missing sum"))?
                        .add(weight, &out)
                        .map_err(Fault::clean)?,
                );
                self.weighted += 1;
                Ok(())
            });
            match result {
                Ok(()) => {
                    row["status"] = json!("weighted_after_retirement");
                    record.save(&row)
                }
                Err(f) => {
                    row["status"] = json!("failed");
                    row["reason"] = json!(bounded(&f.reason));
                    row["uncertain"] = json!(f.uncertain);
                    row["cleanup_error"] = json!(f.cleanup.as_deref().map(bounded));
                    let reason = bounded(&f.reason).to_owned();
                    if f.uncertain {
                        self.cleanup = Some(
                            bounded(
                                f.cleanup
                                    .as_deref()
                                    .unwrap_or("uncertain occurrence retirement"),
                            )
                            .to_owned(),
                        );
                    }
                    primary = Some(reason.clone());
                    record.save(&row)?;
                    Err(reason)
                }
            }
        };
        let result = self
            .cache
            .consume(
                &p.keys,
                || t.check().is_err(),
                |v| {
                    consume(
                        v.demand,
                        Some((v.slot.0, v.generation)),
                        v.components,
                        v.hashes,
                    )
                    .map_err(|detail| mlx_expert_ranges::Refusal {
                        phase: "weighted occurrence",
                        detail,
                    })
                },
            )
            .map_err(|e| {
                release_error = e
                    .cleanup
                    .map(|error| bounded(&error.to_string()).to_owned());
                e.primary.to_string()
            });
        let capture = self.transport.capture(
            &self.cache,
            self.mode,
            p.position,
            self.book.digest(),
            &p.id,
        );
        if let Err(error) = capture {
            self.cache.quarantine();
            self.cleanup = Some(error);
        }

        if let Some(error) = release_error {
            self.cleanup = Some(match self.cleanup.take() {
                Some(previous) => format!("{previous}; cache release: {error}"),
                None => error,
            });
        }
        if self.cleanup.is_some() {
            self.cache.quarantine();
        }
        if let Some(reason) = primary {
            return Err(err("weighted_occurrence", reason));
        }
        result.map_err(|e| err("weighted_tuple", e))?;
        let a = self.cache.activity();
        if self.cleanup.is_some() || a.spawned != a.joined || !a.banks_home || a.outstanding {
            self.cache.quarantine();
            return Err(err("transport", "incomplete transport or capture"));
        }
        if next != terms.len() {
            return Err(err("weighted_tuple", "incomplete ordered demand"));
        }
        let buffer = RuntimeBuffer {
            slot_id: p.position,
            byte_length: 512,
        };
        self.output = Some(LayerOutput {
            step_id: p.id.clone(),
            request: req,
            buffer,
            token: 0,
            bytes: sum.ok_or_else(|| err("sum", "missing sum"))?.into_bytes(),
        });
        Ok(buffer)
    }
}
impl<D: Driver> LayerExecutor for StagedWeightedExecutor<D> {
    fn execute_layer(
        &mut self,
        r: LayerRequest,
        t: &CancellationToken,
    ) -> BackendResult<RuntimeBuffer> {
        catch_unwind(AssertUnwindSafe(|| self.compute(r, t))).unwrap_or_else(|_| {
            self.cache.quarantine();
            if let Some(pending) = &self.pending {
                let _ = self.transport.capture(
                    &self.cache,
                    self.mode,
                    pending.position,
                    self.book.digest(),
                    &pending.id,
                );
            }
            self.cleanup = Some("callback unwound".into());
            Err(err("unwind", "unknown completion"))
        })
    }
}
impl<D: Driver> HostLayerExecutor for StagedWeightedExecutor<D> {
    fn working_bytes(&self) -> u64 {
        self.total
    }
    fn stage(
        &mut self,
        r: &StepRequest,
        inputs: &[LoadedTensor],
        scratch: &mut [u8],
        t: &CancellationToken,
    ) -> BackendResult<()> {
        t.check()?;
        let expected = self
            .book
            .request(r.expected_position)
            .map_err(|e| err("stage", e))?;
        if self.cache.cache().is_quarantined()
            || self.pending.is_some()
            || *r != expected
            || !scratch.is_empty()
            || inputs.len() != 1
            || inputs[0].descriptor != expected.inputs[0]
            || inputs[0].bytes.len() != 512
            || sha256_hex(&inputs[0].bytes) != INPUT_SHA
        {
            return Err(err("stage", "exact weighted request and input required"));
        }
        let terms = self
            .book
            .terms(r.expected_position)
            .map_err(|e| err("book", e))?;
        if self.records.len() + terms.len() > MAX_TERMS || self.transport.used >= MAX_PLANS {
            return Err(err("quota", "cumulative occurrence budget"));
        }
        let keys = terms
            .iter()
            .map(|&(e, _)| self.cache.demand(e))
            .collect::<std::result::Result<Vec<_>, _>>()
            .map_err(|e| err("demand", e.to_string()))?;
        self.pending = Some(Pending {
            id: expected.id,
            position: r.expected_position,
            input: HostTensor {
                name: "x".into(),
                dtype: Dtype::F32,
                shape: vec![1, 128],
                bytes: inputs[0].bytes.clone(),
            },
            keys,
        });
        Ok(())
    }
    fn take_output(&mut self, b: RuntimeBuffer) -> BackendResult<LayerOutput> {
        self.output
            .take()
            .filter(|v| v.buffer == b)
            .ok_or_else(|| err("weighted_output", "buffer mismatch"))
    }
    fn finish(&mut self) -> BackendResult<()> {
        self.pending = None;
        self.output = None;
        let stopped = catch_unwind(AssertUnwindSafe(|| self.driver.finish()))
            .unwrap_or_else(|_| Err(Fault::uncertain("finish unwind")));
        if let Err(e) = stopped {
            self.cache.quarantine();
            let previous = self.cleanup.take();
            self.cleanup = Some(match previous {
                Some(p) => format!("{p}; finish {}", bounded(&e.reason)),
                None => bounded(&e.reason).into(),
            });
        }
        let released = self.cache.finish();
        if let Some(reason) = self.cleanup.take() {
            return Err(ContractError::new(
                ErrorCategory::InvalidStateTransition,
                "weighted_cleanup",
                reason,
            ));
        }
        released.map_err(|e| {
            self.cache.quarantine();
            err("cache_cleanup", e.to_string())
        })
    }
}
pub fn setup<D: Driver>(
    repo: &Path,
    profile: &str,
    book: RouteBook,
    mode: Mode,
    driver: D,
    capacity: Option<u64>,
) -> Result<(StepCoordinator<StagedWeightedExecutor<D>>, InputStore)> {
    let population = Population::load(profile)?;
    book.check(&population)?;
    ensure(
        book.digest() == RouteBook::fixed(profile)?.digest(),
        "fixed staged route book",
    )?;
    let (cache, control) = population.open(repo, Arm::Cached)?;
    ensure(control.is_none(), "copied cache required")?;
    let geo = Geometry::from_cache(&cache, &population)?;
    let store = InputStore {
        path: population.input(repo, 0),
        tensor: book.request(0)?.inputs.remove(0),
        reads: Cell::new(0),
    };
    let cache = StagedResidency::new(cache, mode, u64::MAX).map_err(|e| e.to_string())?;
    let l = cache.ledger();
    let transport = Journal::new()?;
    let retained = transport.slots.iter().map(Vec::capacity).sum::<usize>() + size_of::<Journal>();
    // Live tree: at most twelve events, each with a 32-byte binding expanded to JSON.
    // The writer encodes directly into a retained slot. Reserve separate scratch for
    // current tree, identity strings, container nodes and bounded failure details.
    let transport_parts = [
        ("retained", retained),
        ("live_tree", 256 << 10),
        ("bookkeeping", 64 << 10),
    ];
    let transport_bound = transport_parts
        .iter()
        .try_fold(0usize, |a, (_, v)| a.checked_add(*v))
        .ok_or("transport overflow")?;
    ensure(
        transport_bound <= TRANSPORT as usize,
        "transport capacity proof",
    )?;
    let book_bytes = book.capacity();
    ensure(book_bytes <= 65536, "book storage")?;
    let pop_bytes = size_of::<Population>()
        + population.name.capacity()
        + population.metadata.capacity()
        + population.shard_sha.capacity();
    let records = Vec::<Record>::with_capacity(MAX_TERMS);
    let record_bytes = records.capacity() * (size_of::<Record>() + ROW_LIMIT);
    // stage_parts checks all byte, name and shape capacities against 64 KiB.
    // The control arm holds its separately loaded tuple during occurrence.
    let parts = [
        ("route_book_and_encoding", book_bytes as u64),
        ("population", pop_bytes as u64),
        ("staging_tuple_with_descriptors", 65536),
        ("activation_path", store.path.capacity() as u64),
        ("input_reader_and_pending_copy", 1024),
        ("readback_and_activation", 3 * 4096 + 5 * 4096),
        ("accumulator", 512),
        (
            "pending_demand_descriptors_and_ledger",
            32768 + 3 * size_of::<Demand>() as u64,
        ),
        ("retained_records", record_bytes as u64),
        ("live_record_tree_and_serialization", 192 << 10),
    ];
    let host_bound = parts
        .iter()
        .try_fold(0u64, |a, (_, b)| a.checked_add(*b))
        .ok_or("host estimate overflow")?;
    ensure(
        records.capacity() == MAX_TERMS && host_bound <= HOST_BYTES,
        "weighted host capacity",
    )?;
    let total = working_charge(l.total)?;
    let ledger = json!({"W_cache":l.cache_bytes,"M":l.metadata_bytes,"S":l.tuple_bytes,"H_weighted":HOST_BYTES,"N_native":NATIVE,
        "pipeline":l,"W_pipeline":l.total,"H_transport":TRANSPORT,"transport_parts":transport_parts,
        "transport_bound":transport_bound,"transport_row_bytes":TRANSPORT_ROW,"transport_slots":MAX_PLANS,
        "prospective_native":native_bound(geo)?,"W_total":total,"host_bound":host_bound,"parts":parts,
        "saved_payload_ceiling":MAX_TERMS*ROW_LIMIT});
    let cp = book.checkpoint().clone();
    let exec = StagedWeightedExecutor {
        book,
        population,
        geo,
        cache,
        mode,
        transport,
        driver,
        total,
        ledger,
        records,
        pending: None,
        output: None,
        cleanup: None,
        dispatches: 0,
        weighted: 0,
    };
    let max = capacity.unwrap_or(total + 1556);
    let budget = MemoryBudget::try_new(max.checked_add(1024).ok_or("budget overflow")?, 1024, max)
        .map_err(|e| e.to_string())?;
    Ok((
        StepCoordinator::new(cp, budget, GenerationState::default(), exec)
            .map_err(|e| e.to_string())?,
        store,
    ))
}
