//! Common synchronous sequence for copied native projections and host boundary tests.
use crate::resident_fixture::*;
use backend::CancellationToken;
use mlx_expert_ranges::residency::{Demand, TupleHashes};
use mlx_native_affine::{
    dtype::Dtype,
    family,
    fixture::{sha256_hex, HostTensor},
    refusal::{check_qmm, DeviceFacts},
};
use serde_json::{json, Value};
use std::panic::{catch_unwind, AssertUnwindSafe};

pub const HOST_EXTRA: u64 = 1 << 20;
pub const NATIVE: u64 = 32 << 20;
pub const ROW_LIMIT: usize = 32768;
pub const MAX_ROWS: usize = 9;
pub const REPORT_LIMIT: usize = 512 << 10;
#[derive(Debug)]
pub struct Fault {
    pub reason: String,
    pub uncertain: bool,
    pub cleanup: Option<String>,
}
impl Fault {
    pub fn clean(s: impl ToString) -> Self {
        Self {
            reason: s.to_string(),
            uncertain: false,
            cleanup: None,
        }
    }
    pub fn uncertain(s: impl ToString) -> Self {
        Self {
            reason: s.to_string(),
            uncertain: true,
            cleanup: None,
        }
    }
}
pub type StageResult<T> = std::result::Result<T, Fault>;
pub struct Projection {
    pub output: HostTensor,
    pub imports: u64,
    pub calls: u64,
    pub before_import: u64,
    pub before_call: u64,
    pub cpu_checks: u64,
    pub gpu: bool,
    pub memory: [usize; 3],
}
pub struct Activation {
    pub hidden: HostTensor,
    pub clamps: [[u32; 64]; 2],
    pub stats: [u64; 8],
    pub memory: [usize; 3],
}
pub struct Retirement {
    pub live: u64,
    pub freed: u64,
    pub double_free: u64,
    pub errors: usize,
    pub messages: u64,
    pub results: [u64; 3],
}
impl Retirement {
    pub fn check(&self) -> StageResult<()> {
        if self.live != 0
            || self.double_free != 0
            || self.errors != 0
            || self.messages != 0
            || self.results[0] != self.results[1] + self.results[2]
        {
            Err(Fault::uncertain("native retirement census"))
        } else {
            Ok(())
        }
    }
    fn record(&self) -> Value {
        json!({"live":self.live,"freed":self.freed,"double_free":self.double_free,"errors":self.errors,"messages":self.messages,"results":self.results})
    }
}
/// One occurrence owns all work between begin and retire. Native implementation is thread-affine.
pub trait Driver {
    fn begin(&mut self) -> StageResult<DeviceFacts>;
    fn projection(
        &mut self,
        role: usize,
        input: &HostTensor,
        parts: &[HostTensor; 3],
        bits: u32,
    ) -> StageResult<Projection>;
    fn activation(&mut self, gate: &HostTensor, up: &HostTensor) -> StageResult<Activation>;
    fn retire(&mut self) -> StageResult<Retirement>;
    fn finish(&mut self) -> StageResult<()>;
}
fn check_cancel(t: &CancellationToken) -> StageResult<()> {
    t.check().map_err(Fault::clean)
}
fn words(t: &HostTensor) -> Vec<u32> {
    t.bytes
        .chunks_exact(4)
        .map(|v| u32::from_le_bytes(v.try_into().unwrap()))
        .collect()
}
fn output(t: &HostTensor) -> Value {
    json!({"dtype":"F32","shape":t.shape,"bytes":t.bytes.len(),"sha256":sha256_hex(&t.bytes),"f32_bits":words(t)})
}
fn check_output(t: &HostTensor, n: usize) -> StageResult<()> {
    ensure(
        t.shape == [1, n]
            && t.dtype == Dtype::F32
            && t.bytes.len() == 4 * n
            && t.bytes.capacity() <= 4096
            && t.name.capacity() <= 128
            && t.shape.capacity() <= 8
            && t.bytes
                .chunks_exact(4)
                .all(|b| f32::from_le_bytes(b.try_into().unwrap()).is_finite()),
        "invalid stage readback",
    )
    .map_err(Fault::uncertain)
}
fn memory(m: [usize; 3]) -> StageResult<()> {
    ensure(
        m.iter().all(|n| (*n as u64) <= NATIVE),
        "native allocator envelope",
    )
    .map_err(Fault::uncertain)
}
pub fn native_bound(geo: Geometry) -> Result<Value> {
    let mut stages = vec![];
    let mut peak = 0usize;
    for i in 0..3 {
        let [n, k] = if i == 2 { [128, 64] } else { [64, 128] };
        let packed = n * k * geo.bits[i] as usize / 8;
        let raw = 4 * n * (k / 64);
        let wide = 2 * raw;
        let sum = packed + raw + wide + 4 * k + 4 * n;
        peak = peak.max(sum);
        stages.push(json!({"packed":packed,"metadata_raw":raw,"metadata_f32":wide,"input":4*k,"output":4*n,"bytes":sum}));
    }
    let activation = 7 * 64 * 4 + 8;
    let headroom = 4usize << 20;
    let bound = peak
        .max(activation)
        .checked_add(headroom)
        .ok_or("native bound")?;
    ensure(bound <= NATIVE as usize, "native live estimate")?;
    Ok(
        json!({"qmm":stages,"activation":activation,"temporary_headroom":headroom,"bound":bound,"envelope":NATIVE,"cache_limit":0}),
    )
}
fn qmm(
    d: &mut impl Driver,
    i: usize,
    x: &HostTensor,
    p: &Planes,
    geo: Geometry,
    row: &mut Value,
) -> StageResult<HostTensor> {
    let q = d.projection(i, x, &p[i], geo.bits[i])?;
    let n = if i == 2 { 128 } else { 64 };
    let k = if i == 2 { 64 } else { 128 };
    check_output(&q.output, n)?;
    memory(q.memory)?;
    ensure(
        q.gpu
            && q.before_import == 0
            && q.before_call == 0
            && q.cpu_checks == 2
            && q.imports == 4
            && q.calls > 0,
        "QMM guard/import evidence",
    )
    .map_err(Fault::uncertain)?;
    row[["gate", "up", "down"][i]] = json!({"bits":geo.bits[i],"group_size":64,"packed_weight_sha256":sha256_hex(&p[i][0].bytes),"output":output(&q.output),"bound_gamma_n":family::bound_exponent(1,n,k,64,geo.bits[i]),"device_facts_gpu":q.gpu,"cpu_guard_checks":q.cpu_checks,"imports_before_decision":q.before_import,"numerical_before_decision":q.before_call,"imports":q.imports,"numerical":q.calls,"active_cache_peak":q.memory});
    Ok(q.output)
}
fn admit(facts: &DeviceFacts, x: &HostTensor, p: &[HostTensor; 3], bits: u32) -> StageResult<()> {
    check_qmm(facts, true, x, &p[0], &p[1], &p[2], bits, 64)
        .map(|_| ())
        .map_err(Fault::clean)
}
fn evaluate(
    d: &mut impl Driver,
    x: &HostTensor,
    p: &Planes,
    geo: Geometry,
    cancel: &CancellationToken,
    row: &mut Value,
) -> StageResult<HostTensor> {
    check_cancel(cancel)?;
    let facts = d.begin()?;
    if facts != DeviceFacts::GPU {
        return Err(Fault::clean("GPU device/stream required"));
    }
    admit(&facts, x, &p[0], geo.bits[0])?;
    admit(&facts, x, &p[1], geo.bits[1])?;
    let gate = qmm(d, 0, x, p, geo, row)?;
    check_cancel(cancel)?;
    let up = qmm(d, 1, x, p, geo, row)?;
    check_cancel(cancel)?;
    for t in [&gate, &up] {
        ensure(
            t.bytes
                .chunks_exact(4)
                .all(|b| f32::from_le_bytes(b.try_into().unwrap()).abs() <= 16.),
            "MLP-R-ACTIVATION",
        )
        .map_err(Fault::clean)?;
    }
    let a = d.activation(&gate, &up)?;
    check_output(&a.hidden, 64)?;
    memory(a.memory)?;
    ensure(
        a.stats[0] == 2 && a.stats[2..] == [9, 4, 13, 1, 9, 0],
        "activation retirement/materialization",
    )
    .map_err(Fault::uncertain)?;
    row["activation"] = json!({"status":0,"stats":a.stats,"materializations":a.stats[5],"gate_clamp_bits":a.clamps[0].as_slice(),"up_clamp_bits":a.clamps[1].as_slice(),"output":output(&a.hidden),"active_cache_peak":a.memory});
    check_cancel(cancel)?;
    let down = admit(&facts, &a.hidden, &p[2], geo.bits[2]);
    row["down_admission"] = json!({"actual_input_sha256":sha256_hex(&a.hidden.bytes),"decision":if down.is_ok(){"admitted"}else{"refused"},"imports_before_decision":0,"numerical_before_decision":0});
    down?;
    let out = qmm(d, 2, &a.hidden, p, geo, row)?;
    check_cancel(cancel)?;
    Ok(out)
}

pub(crate) fn occurrence(
    d: &mut impl Driver,
    geo: Geometry,
    parts: Slices<'_>,
    hashes: &TupleHashes,
    demand: Demand,
    x: &HostTensor,
    cancel: &CancellationToken,
    row: &mut Value,
) -> StageResult<HostTensor> {
    check_cancel(cancel)?;
    let (p, capacity) = stage_parts(parts, geo, hashes).map_err(Fault::clean)?;
    ensure(capacity <= 65536, "staging capacity").map_err(Fault::clean)?;
    let before = hashes.map(|r| r.map(|h| hex(&h)));
    row["binding"] = json!(hex(&demand.binding));
    row["component_sha256_before"] = json!(before);
    row["staging_capacity"] = json!(capacity);
    let result = catch_unwind(AssertUnwindSafe(|| evaluate(d, x, &p, geo, cancel, row)))
        .unwrap_or_else(|_| Err(Fault::uncertain("native callback unwind")));
    let cleanup = catch_unwind(AssertUnwindSafe(|| d.retire()))
        .unwrap_or_else(|_| Err(Fault::uncertain("retirement unwind")))
        .and_then(|q| {
            row["cleanup"] = q.record();
            q.check()?;
            if result.is_ok() && (q.freed == 0 || q.results[0] == 0 || q.results[2] != 0) {
                return Err(Fault::uncertain("missing successful native retirement"));
            }
            Ok(())
        });
    if let Err(e) = cleanup {
        let mut f = result
            .err()
            .unwrap_or_else(|| Fault::uncertain("retirement failed"));
        f.uncertain = true;
        f.cleanup = Some(e.reason);
        return Err(f);
    }
    let out = result?;
    verify_parts(parts, geo, hashes).map_err(Fault::uncertain)?;
    verify_parts(
        p.each_ref()
            .map(|r| r.each_ref().map(|v| v.bytes.as_slice())),
        geo,
        hashes,
    )
    .map_err(Fault::uncertain)?;
    row["component_sha256_after"] = json!(before);
    row["copies"] = json!({"staging_components":9,"staging_bytes":parts.iter().flatten().map(|p|p.len()).sum::<usize>(),"qmm_data_imports":12,"qmm_metadata_widenings":6,"projection_readbacks":3,"activation_input_imports":2,"scalar_imports":2,"activation_readbacks":3,"down_host_reimport":1});
    Ok(out)
}
