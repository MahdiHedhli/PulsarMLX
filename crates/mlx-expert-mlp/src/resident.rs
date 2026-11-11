//! Fixed two-step diagnostic over the real coordinator and a synchronous copied driver.
use crate::{resident_fixture::*, resident_pipeline::*};
use backend::{step::*, *};
use mlx_expert_ranges::{
    residency::{CopiedResidency, Demand},
    BoundedSource,
};
use mlx_native_affine::{
    dtype::Dtype,
    fixture::{sha256_hex, HostTensor},
};
use serde_json::{json, Value};
use std::{
    cell::Cell,
    io::Write,
    panic::{catch_unwind, AssertUnwindSafe},
    path::{Path, PathBuf},
};

const FIRST: [u32; 6] = [0, 1, 0, 2, 1, 0];
const SECOND: [u32; 3] = [0, 1, 0];
fn err(code: &'static str, why: impl ToString) -> ContractError {
    ContractError::new(ErrorCategory::InvalidStateTransition, code, why.to_string())
}
fn descriptor() -> RuntimeTensor {
    RuntimeTensor {
        name: "fixture.activation".into(),
        shard: "fixture-input".into(),
        range: TensorRange {
            offset: 0,
            length: 512,
        },
        shape: vec![1, 128],
        quantization: "f32".into(),
    }
}
pub struct InputStore {
    file: PathBuf,
    reads: Cell<u64>,
}
impl InputStore {
    pub fn reads(&self) -> u64 {
        self.reads.get()
    }
}
impl TensorCatalog for InputStore {
    fn tensor(&self, name: &str) -> std::result::Result<Option<RuntimeTensor>, ContractError> {
        Ok((name == "fixture.activation").then(descriptor))
    }
}
impl HostTensorStore for InputStore {
    fn validate_range(&self, t: &RuntimeTensor) -> std::result::Result<(), ContractError> {
        if t == &descriptor() {
            Ok(())
        } else {
            Err(err("input", "fixed descriptor"))
        }
    }
}
impl TensorStore for InputStore {
    fn read_range(
        &self,
        t: &RuntimeTensor,
        out: &mut [u8],
        cancel: &CancellationToken,
    ) -> std::result::Result<usize, ContractError> {
        self.validate_range(t)?;
        cancel.check()?;
        let data = checked_file(&self.file, 512).map_err(|e| err("input", e))?;
        if data.len() != 512 || out.len() != 512 || sha256_hex(&data) != INPUT_SHA {
            return Err(err("input", "original M=1 input binding"));
        }
        out.copy_from_slice(&data);
        self.reads.set(self.reads.get() + 1);
        Ok(512)
    }
}
struct Pending {
    id: String,
    position: u64,
    input: HostTensor,
    keys: Vec<Demand>,
}
struct Buffer(Vec<u8>);
impl Write for Buffer {
    fn write(&mut self, b: &[u8]) -> std::io::Result<usize> {
        if b.len() > ROW_LIMIT - self.0.len() {
            return Err(std::io::Error::other("bounded occurrence record"));
        }
        self.0.extend_from_slice(b);
        Ok(b.len())
    }
    fn flush(&mut self) -> std::io::Result<()> {
        Ok(())
    }
}
pub struct ResidentExecutor<D: Driver> {
    cache: CopiedResidency,
    control: Option<BoundedSource>,
    population: Population,
    geo: Geometry,
    driver: D,
    ledger: Value,
    total: u64,
    pending: Option<Pending>,
    output: Option<LayerOutput>,
    pub records: Vec<Vec<u8>>,
    cleanup: Option<String>,
    dispatches: usize,
    calls: usize,
    imports: u64,
    projections: u64,
    activations: u64,
}
impl<D: Driver> ResidentExecutor<D> {
    pub fn new(repo: &Path, profile: &str, arm: Arm, driver: D) -> Result<Self> {
        let population = Population::load(profile)?;
        let (cache, control) = population.open(repo, arm)?;
        let geo = Geometry::from_cache(&cache, &population)?;
        let l = cache.ledger();
        let control_meta = control
            .as_ref()
            .map(BoundedSource::logical_metadata_bytes)
            .transpose()
            .map_err(|e| e.to_string())?
            .unwrap_or(0);
        let descriptor_bytes = 32u64 << 10;
        let transient = 192u64 << 10;
        // One live Value tree, its bounded serialization, and at most nine saved
        // serialized rows. Returned concatenation is charged as coordinator output.
        let host_parts = [
            l.tuple_bytes,
            if control.is_some() { l.tuple_bytes } else { 0 },
            control_meta,
            descriptor_bytes,
            512,
            3 * 512,
            2 * 256 + 3 * 256,
            MAX_ROWS as u64 * ROW_LIMIT as u64,
            transient,
        ];
        let host_bound = host_parts
            .iter()
            .try_fold(0u64, |a, b| a.checked_add(*b))
            .ok_or("host bound overflow")?;
        ensure(host_bound <= HOST_EXTRA, "host working capacity")?;
        let native = native_bound(geo)?;
        let total = l
            .working_bytes
            .checked_add(HOST_EXTRA + NATIVE)
            .ok_or("working charge overflow")?;
        let ledger = json!({"W_cache":l.working_bytes,"H_extra":HOST_EXTRA,"N_native":NATIVE,"W_total":total,"S":l.tuple_bytes,"M":l.metadata_bytes,"control_metadata":control_meta,"control_tuple":host_parts[1],"staging_tuple":l.tuple_bytes,"descriptor_key_and_shape_allowance":descriptor_bytes,"input_copy":512,"qmm_readbacks":1536,"activation_temporaries":1280,"saved_row_capacity":MAX_ROWS*ROW_LIMIT,"record_and_serialization_workspace":transient,"host_bound":host_bound,"native":native});
        Ok(Self {
            cache,
            control,
            population,
            geo,
            driver,
            ledger,
            total,
            pending: None,
            output: None,
            records: Vec::with_capacity(MAX_ROWS),
            cleanup: None,
            dispatches: 0,
            calls: 0,
            imports: 0,
            projections: 0,
            activations: 0,
        })
    }
    pub fn snapshot(&self) -> Value {
        let s = self.cache.stats();
        json!({"cache_reads":self.cache.read_calls(),"control_reads":self.control.as_ref().map_or(0,BoundedSource::payload_read_calls),"cache_fills":s.fills,"cache_hits":s.hits,"cache_evictions":s.evictions,"cache_consumed":s.consumed,"occupied":self.cache.resident_bytes(),"qmm_imports":self.imports,"projections":self.projections,"activations":self.activations,"dispatches":self.dispatches,"mlp_calls":self.calls,"records":self.records.len(),"quarantined":self.cache.is_quarantined(),"working_bytes":self.total})
    }
    pub fn ledger(&self) -> &Value {
        &self.ledger
    }
    fn compute(
        &mut self,
        req: LayerRequest,
        t: &CancellationToken,
    ) -> std::result::Result<RuntimeBuffer, ContractError> {
        let pending = self
            .pending
            .as_ref()
            .ok_or_else(|| err("stage", "no demand"))?;
        if req.layer != LAYER || req.generation_position != pending.position {
            return Err(err("stage", "layer/position"));
        }
        self.dispatches += 1;
        let pop = &self.population;
        let geo = self.geo;
        let driver = &mut self.driver;
        let records = &mut self.records;
        let calls = &mut self.calls;
        let mut out = Vec::new();
        let size = pending.keys.len() * 512;
        out.try_reserve_exact(size).map_err(|e| err("output", e))?;
        let (imports, projections, activations) = (
            &mut self.imports,
            &mut self.projections,
            &mut self.activations,
        );
        let mut failure = None;
        let mut consume = |d: Demand,
                           slot: Option<(u64, u64)>,
                           parts: Slices<'_>,
                           hashes: &mlx_expert_ranges::residency::TupleHashes|
         -> Result<()> {
            ensure(records.len() < MAX_ROWS, "nine occurrences maximum")?;
            let expert = d.key.expert as usize;
            ensure(
                expert < 3 && d.key.layer == LAYER && pop.hashes[expert] == *hashes,
                "fixed role/expert binding",
            )?;
            let mut row = json!({"ordinal":records.len(),"expert":expert,"step":pending.position,"slot_generation":slot,"recipe":pop.profile});
            let mut b = Buffer(Vec::new());
            b.0.try_reserve_exact(ROW_LIMIT)
                .map_err(|e| e.to_string())?;
            ensure(b.0.capacity() == ROW_LIMIT, "record capacity")?;
            *calls += 1;
            let result = occurrence(driver, geo, parts, hashes, d, &pending.input, t, &mut row);
            for role in ["gate", "up", "down"] {
                if let Some(n) = row[role]["imports"].as_u64() {
                    *imports += n;
                    *projections += 1;
                }
            }
            if row["activation"]["status"] == 0 {
                *activations += 1;
            }
            if let Err(e) = &result {
                row["error"] = json!(e.reason);
                row["uncertain"] = json!(e.uncertain);
                row["cleanup_error"] = json!(e.cleanup);
            }
            if let Err(e) = result {
                let reason = e.reason.clone();
                failure = Some(e);
                if serde_json::to_writer(&mut b, &row).is_ok() {
                    records.push(b.0);
                }
                return Err(reason);
            }
            serde_json::to_writer(&mut b, &row).map_err(|e| e.to_string())?;
            records.push(b.0);
            out.extend_from_slice(&result.unwrap().bytes);
            Ok(())
        };
        let result = if let Some(source) = &self.control {
            (|| {
                for d in &pending.keys {
                    t.check().map_err(|e| e.to_string())?;
                    let e = d.key.expert;
                    let plan = source.plan(pop.request(e)).map_err(|e| e.to_string())?;
                    pop.verify_plan(&plan, e)?;
                    let owned = plan.load().map_err(|e| e.to_string())?;
                    let parts = std::array::from_fn(|i| {
                        std::array::from_fn(|j| owned.bytes(i, j).expect("sealed complete tuple"))
                    });
                    verify_parts(parts, geo, &pop.hashes[e as usize])?;
                    consume(*d, None, parts, &pop.hashes[e as usize])?;
                    plan.validate_source().map_err(|e| e.to_string())?;
                }
                Ok(())
            })()
        } else {
            self.cache
                .consume(
                    &pending.keys,
                    || t.check().is_err(),
                    |v| {
                        consume(
                            v.demand,
                            Some((v.slot.0, v.generation)),
                            v.components,
                            v.hashes,
                        )
                        .map_err(|detail| mlx_expert_ranges::Refusal {
                            phase: "MLP",
                            detail,
                        })
                    },
                )
                .map_err(|e| e.to_string())
        };
        if let Some(f) = failure {
            if f.uncertain {
                self.cache.quarantine();
                self.cleanup = Some(
                    f.cleanup
                        .unwrap_or_else(|| "unverified native completion".into()),
                );
            }
            return Err(err("resident_mlp", f.reason));
        }
        result.map_err(|e| err("resident_tuple", e))?;
        let buffer = RuntimeBuffer {
            slot_id: pending.position,
            byte_length: size as u64,
        };
        self.output = Some(LayerOutput {
            step_id: pending.id.clone(),
            request: req,
            buffer,
            token: 0,
            bytes: out,
        });
        Ok(buffer)
    }
}
impl<D: Driver> LayerExecutor for ResidentExecutor<D> {
    fn execute_layer(
        &mut self,
        r: LayerRequest,
        t: &CancellationToken,
    ) -> std::result::Result<RuntimeBuffer, ContractError> {
        match catch_unwind(AssertUnwindSafe(|| self.compute(r, t))) {
            Ok(v) => v,
            Err(_) => {
                self.cache.quarantine();
                self.cleanup = Some("callback unwound".into());
                Err(err("resident_unwind", "unknown completion"))
            }
        }
    }
}
impl<D: Driver> HostLayerExecutor for ResidentExecutor<D> {
    fn working_bytes(&self) -> u64 {
        self.total
    }
    fn stage(
        &mut self,
        r: &StepRequest,
        inputs: &[LoadedTensor],
        _: &mut [u8],
        t: &CancellationToken,
    ) -> std::result::Result<(), ContractError> {
        t.check()?;
        let keys = match (r.expected_position, r.id.as_str()) {
            (0, "resident-step-0") => &FIRST[..],
            (1, "resident-step-1") => &SECOND[..],
            _ => return Err(err("stage", "unsupported step")),
        };
        if self.cache.is_quarantined()
            || r.layers != [LAYER]
            || r.output_bytes != keys.len() as u64 * 512
            || inputs.len() != 1
            || inputs[0].descriptor != descriptor()
            || inputs[0].bytes.len() != 512
            || sha256_hex(&inputs[0].bytes) != INPUT_SHA
        {
            return Err(err("stage", "admitted fixture input and output geometry"));
        }
        let keys = keys
            .iter()
            .map(|e| self.cache.demand(*e))
            .collect::<std::result::Result<Vec<_>, _>>()
            .map_err(|e| err("demand", e))?;
        self.pending = Some(Pending {
            id: r.id.clone(),
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
    fn take_output(&mut self, _: RuntimeBuffer) -> std::result::Result<LayerOutput, ContractError> {
        self.output
            .take()
            .ok_or_else(|| err("output", "missing result"))
    }
    fn finish(&mut self) -> std::result::Result<(), ContractError> {
        self.output = None;
        self.pending = None;
        let stopped = catch_unwind(AssertUnwindSafe(|| self.driver.finish()))
            .unwrap_or_else(|_| Err(Fault::uncertain("finish unwind")));
        if let Err(e) = stopped {
            self.cache.quarantine();
            let prev = self.cleanup.take().unwrap_or_default();
            self.cleanup = Some(format!("{prev} {}", e.reason));
        }
        if let Some(e) = self.cleanup.take() {
            return Err(err("resident_cleanup", e));
        }
        self.cache.finish().map_err(|e| err("resident_cleanup", e))
    }
}
pub fn request(cp: &CheckpointIdentity, pos: u64) -> StepRequest {
    StepRequest {
        id: format!("resident-step-{pos}"),
        checkpoint: cp.clone(),
        expected_position: pos,
        inputs: vec![descriptor()],
        layers: vec![LAYER],
        scratch_bytes: 0,
        output_bytes: if pos == 0 { 3072 } else { 1536 },
    }
}
pub fn setup<D: Driver>(
    repo: &Path,
    profile: &str,
    arm: Arm,
    driver: D,
    capacity: Option<u64>,
) -> Result<(
    StepCoordinator<ResidentExecutor<D>>,
    InputStore,
    CheckpointIdentity,
)> {
    let exec = ResidentExecutor::new(repo, profile, arm, driver)?;
    let cp = CheckpointIdentity::try_new(hex(&exec.population.content), "resident-mlp-v1")
        .map_err(|e| e.to_string())?;
    let store = InputStore {
        file: exec.population.input(repo, 0),
        reads: Cell::new(0),
    };
    let max = capacity.unwrap_or(exec.total + 512 + 1536 + 3072 + 8);
    let budget = MemoryBudget::try_new(max.checked_add(1024).ok_or("budget overflow")?, 1024, max)
        .map_err(|e| e.to_string())?;
    Ok((
        StepCoordinator::new(cp.clone(), budget, GenerationState::default(), exec)
            .map_err(|e| e.to_string())?,
        store,
        cp,
    ))
}
pub fn run_sequence<D: Driver>(
    host: &mut StepCoordinator<ResidentExecutor<D>>,
    store: &InputStore,
    cp: &CheckpointIdentity,
    arm: Arm,
) -> Result<Value> {
    let t = CancellationToken::new();
    let r = request(cp, 0);
    let before = host.backend().snapshot();
    let first = host
        .execute(&r, store, store, &t, |_| {
            Err(err("delivery", "fixed lost delivery"))
        })
        .map_err(|e| e.to_string())?;
    ensure(
        first.delivery_error.is_some() && !first.replayed && host.state().position() == 1,
        "first delivery",
    )?;
    let after = host.backend().snapshot();
    let reads = store.reads.get();
    let replay = host
        .execute(&r, store, store, &t, |_| Ok(()))
        .map_err(|e| e.to_string())?;
    ensure(
        replay.replayed
            && std::sync::Arc::ptr_eq(&first.committed, &replay.committed)
            && host.backend().snapshot() == after
            && store.reads.get() == reads,
        "replay changed state",
    )?;
    let replay_snapshot = host.backend().snapshot();
    let second = host
        .execute(&request(cp, 1), store, store, &t, |_| Ok(()))
        .map_err(|e| e.to_string())?;
    let end = host.backend().snapshot();
    let cached = arm == Arm::Cached;
    ensure(
        after["cache_reads"] == if cached { 36 } else { 0 }
            && after["control_reads"] == if cached { 0 } else { 54 }
            && end["cache_reads"] == if cached { 36 } else { 0 }
            && end["control_reads"] == if cached { 0 } else { 81 }
            && end["mlp_calls"] == 9
            && end["dispatches"] == 2
            && store.reads.get() == 2
            && host.state().position() == 2,
        "ordered campaign counts",
    )?;
    Ok(
        json!({"before":before,"first":after,"replay":replay_snapshot,"final":end,"activation_reads":[reads,reads,store.reads.get()],"delivery_failed":true,"replay_same_commit":true,"positions":[1,1,2],"output_sha256":[sha256_hex(&first.committed.bytes),sha256_hex(&second.committed.bytes)],"peak_reservation":host.peak_reservation_bytes(),"active_reservation":host.active_reservation_bytes()}),
    )
}
