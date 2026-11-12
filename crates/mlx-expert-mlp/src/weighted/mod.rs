//! Bounded, fixed-route composition over the existing synchronous occurrence pipeline.
mod book;
mod sum;
use crate::{
    resident_fixture::*,
    resident_pipeline::{native_bound, occurrence, Driver, Fault, NATIVE, ROW_LIMIT},
};
use backend::{step::*, *};
pub use book::{Identity, RouteBook, Term, ARITHMETIC, FIXED, MAX_PLANS, MAX_TERMS};
use mlx_expert_ranges::{
    residency::{CopiedResidency, Demand, TupleHashes},
    BoundedSource,
};
use mlx_native_affine::{
    dtype::Dtype,
    fixture::{sha256_hex, HostTensor},
};
use serde_json::{json, Value};
use std::{
    cell::Cell,
    io::Cursor,
    panic::{catch_unwind, AssertUnwindSafe},
    path::{Path, PathBuf},
};
pub use sum::WeightedSum;

pub const HOST_BYTES: u64 = 1_114_112;
type BackendResult<T> = std::result::Result<T, ContractError>;
fn bounded(s: &str) -> &str {
    let mut n = s.len().min(256);
    while !s.is_char_boundary(n) {
        n -= 1;
    }
    &s[..n]
}
fn err(code: &'static str, detail: impl AsRef<str>) -> ContractError {
    ContractError::new(
        ErrorCategory::InvalidStateTransition,
        code,
        bounded(detail.as_ref()),
    )
}

/// Reads only the admitted M=1 activation through the original checked fixture reader.
pub struct InputStore {
    path: PathBuf,
    tensor: RuntimeTensor,
    reads: Cell<u64>,
}
impl InputStore {
    pub fn reads(&self) -> u64 {
        self.reads.get()
    }
}
impl TensorCatalog for InputStore {
    fn tensor(&self, name: &str) -> BackendResult<Option<RuntimeTensor>> {
        Ok((name == self.tensor.name).then(|| self.tensor.clone()))
    }
}
impl HostTensorStore for InputStore {
    fn validate_range(&self, t: &RuntimeTensor) -> BackendResult<()> {
        if t != &self.tensor {
            return Err(err("input", "activation descriptor"));
        }
        Ok(())
    }
}
impl TensorStore for InputStore {
    fn read_range(
        &self,
        t: &RuntimeTensor,
        out: &mut [u8],
        cancel: &CancellationToken,
    ) -> BackendResult<usize> {
        self.validate_range(t)?;
        cancel.check()?;
        let reads = self
            .reads
            .get()
            .checked_add(1)
            .ok_or_else(|| err("input", "read counter overflow"))?;
        let b = checked_file(&self.path, 512).map_err(|e| err("input", e))?;
        if b.len() != 512 || out.len() != 512 || sha256_hex(&b) != INPUT_SHA {
            return Err(err("input", "activation binding"));
        }
        out.copy_from_slice(&b);
        self.reads.set(reads);
        Ok(b.len())
    }
}
struct Pending {
    id: String,
    position: u64,
    input: HostTensor,
    keys: Vec<Demand>,
}

/// Retains one bounded slot for each scheduled occurrence, including failed waves.
struct Record {
    position: u64,
    expert: u32,
    weight: u32,
    data: Vec<u8>,
}
impl Record {
    fn reserve(position: u64, (expert, weight): Term) -> Result<Self> {
        let mut data = Vec::new();
        data.try_reserve_exact(ROW_LIMIT)
            .map_err(|e| e.to_string())?;
        ensure(data.capacity() == ROW_LIMIT, "row capacity")?;
        data.extend_from_slice(br#"{"status":"not_reached"}"#);
        Ok(Self {
            position,
            expert,
            weight,
            data,
        })
    }
    fn save(&mut self, row: &Value) -> Result<()> {
        self.data.resize(ROW_LIMIT, 0);
        let mut dst = Cursor::new(self.data.as_mut_slice());
        if serde_json::to_writer(&mut dst, row).is_err() {
            self.data.clear();
            self.data
                .extend_from_slice(br#"{"status":"record_overflow"}"#);
            return Err("occurrence record exceeds capacity".into());
        }
        let used = dst.position() as usize;
        self.data.truncate(used);
        Ok(())
    }
}
pub struct WeightedExecutor<D: Driver> {
    book: RouteBook,
    population: Population,
    geo: Geometry,
    cache: CopiedResidency,
    control: Option<BoundedSource>,
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
impl<D: Driver> WeightedExecutor<D> {
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
    pub fn snapshot(&self) -> Value {
        let s = self.cache.stats();
        json!({"cache_reads":self.cache.read_calls(),"control_reads":self.control.as_ref().map_or(0,BoundedSource::payload_read_calls),
        "fills":s.fills,"hits":s.hits,"evictions":s.evictions,"consumed":s.consumed,"occupied":self.cache.resident_bytes(),
        "quarantined":self.cache.is_quarantined(),"records":self.records.len(),"dispatches":self.dispatches,"weighted":self.weighted,
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
        if self.records.len() + terms.len() > MAX_TERMS {
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
        let result = if let Some(source) = &self.control {
            (|| -> Result<()> {
                for d in &p.keys {
                    t.check().map_err(|e| e.to_string())?;
                    let e = d.key.expert;
                    let plan = source.plan(pop.request(e)).map_err(|e| e.to_string())?;
                    pop.verify_plan(&plan, e)?;
                    let owned = plan.load().map_err(|e| e.to_string())?;
                    let parts = std::array::from_fn(|i| {
                        std::array::from_fn(|j| owned.bytes(i, j).expect("admitted tuple"))
                    });
                    verify_parts(parts, self.geo, &pop.hashes[e as usize])?;
                    consume(*d, None, parts, &pop.hashes[e as usize])?;
                    plan.validate_source().map_err(|e| e.to_string())?;
                }
                Ok(())
            })()
        } else {
            self.cache
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
                })
        };
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
impl<D: Driver> LayerExecutor for WeightedExecutor<D> {
    fn execute_layer(
        &mut self,
        r: LayerRequest,
        t: &CancellationToken,
    ) -> BackendResult<RuntimeBuffer> {
        catch_unwind(AssertUnwindSafe(|| self.compute(r, t))).unwrap_or_else(|_| {
            self.cache.quarantine();
            self.cleanup = Some("callback unwound".into());
            Err(err("unwind", "unknown completion"))
        })
    }
}
impl<D: Driver> HostLayerExecutor for WeightedExecutor<D> {
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
        if self.cache.is_quarantined()
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
        if self.records.len() + terms.len() > MAX_TERMS {
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
    arm: Arm,
    driver: D,
    capacity: Option<u64>,
) -> Result<(StepCoordinator<WeightedExecutor<D>>, InputStore)> {
    let population = Population::load(profile)?;
    book.check(&population)?;
    let (cache, control) = population.open(repo, arm)?;
    let geo = Geometry::from_cache(&cache, &population)?;
    let store = InputStore {
        path: population.input(repo, 0),
        tensor: book.request(0)?.inputs.remove(0),
        reads: Cell::new(0),
    };
    let control_meta = control
        .as_ref()
        .map(BoundedSource::logical_metadata_bytes)
        .transpose()
        .map_err(|e| e.to_string())?
        .unwrap_or(0);
    let l = cache.ledger();
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
        (
            "allocating_tuple",
            if control.is_some() { l.tuple_bytes } else { 0 },
        ),
        ("allocating_metadata", control_meta),
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
    let total = l
        .working_bytes
        .checked_add(HOST_BYTES + NATIVE)
        .ok_or("working charge overflow")?;
    let ledger = json!({"W_cache":l.working_bytes,"M":l.metadata_bytes,"S":l.tuple_bytes,"H_weighted":HOST_BYTES,"N_native":NATIVE,
        "prospective_native":native_bound(geo)?,"W_total":total,"host_bound":host_bound,"parts":parts,
        "saved_payload_ceiling":MAX_TERMS*ROW_LIMIT});
    let cp = book.checkpoint().clone();
    let exec = WeightedExecutor {
        book,
        population,
        geo,
        cache,
        control,
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
