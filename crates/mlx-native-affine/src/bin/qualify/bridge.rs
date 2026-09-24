//! The bridge operations: refusals first (in the frozen order, on host data,
//! before any MLX-C numerical call or import), then import, the bridge's own
//! metadata cast, the MLX-C operation on the explicit GPU stream, and the
//! Evaluated readback.
//!
//! The public quantized matmul has no transpose parameter; transpose=false is
//! reachable only through `quantized_matmul_transpose_test_only`, which exists
//! so that R-TRANSPOSE can be exercised and always refuses.
//!
//! The imported U32 weight is passed to `mlx_quantized_matmul` unchanged;
//! only scales and biases are widened (OP-CAST). The weight is never
//! dequantized on the quantized-matmul path.

use mlx_native_affine::dtype::Dtype;
use mlx_native_affine::fixture::HostTensor;
use mlx_native_affine::refusal::{
    check_dq, check_qmm, DeviceFacts, DqGeometry, QmmGeometry, RefusalId,
};

use crate::ffi;
use crate::native::{self, HostCopy, NativeContext, NativeError};

#[derive(Debug)]
pub enum BridgeError {
    Refused(RefusalId),
    Native(NativeError),
}

impl From<NativeError> for BridgeError {
    fn from(e: NativeError) -> Self {
        BridgeError::Native(e)
    }
}

/// Counters observed around one operation.
#[derive(Clone, Debug, Default)]
pub struct OpStats {
    /// MLX-C numerical calls issued before the refusal decision.
    pub numerical_before_decision: u64,
    /// MLX-C imports issued before the refusal decision.
    pub imports_before_decision: u64,
    pub device_facts: Option<DeviceFacts>,
    pub active_before: Option<usize>,
    pub peak_after: Option<usize>,
    pub output_nbytes: Option<usize>,
}

fn facts(ctx: &NativeContext) -> Result<DeviceFacts, BridgeError> {
    Ok(ctx.device_facts()?)
}

/// E1 for non-refusal operations (imports and casts): the same device facts
/// must hold; a violation is a native error, not a numerical result.
fn assert_gpu(ctx: &NativeContext, stats: &mut OpStats) -> Result<(), BridgeError> {
    let f = facts(ctx)?;
    stats.device_facts = Some(f);
    if f != DeviceFacts::GPU {
        return Err(BridgeError::Refused(RefusalId::Device));
    }
    Ok(())
}

/// OP-IMPORT-U32 / OP-IMPORT-META: copy in, evaluate, read back.
pub fn import_readback(
    ctx: &NativeContext,
    t: &HostTensor,
) -> Result<(HostCopy, OpStats), BridgeError> {
    let mut stats = OpStats::default();
    assert_gpu(ctx, &mut stats)?;
    let a = ctx.import(t.dtype, &t.shape, &t.bytes)?;
    let e = a.evaluate()?;
    let copy = e.host_copy()?;
    stats.output_nbytes = Some(copy.bytes.len());
    Ok((copy, stats))
}

/// OP-CAST: the bridge's own widening of F16/BF16 metadata to float32 on the
/// explicit GPU stream (mlx_astype), evaluated and read back.
pub fn cast_readback(
    ctx: &NativeContext,
    t: &HostTensor,
) -> Result<(HostCopy, OpStats), BridgeError> {
    let mut stats = OpStats::default();
    assert_gpu(ctx, &mut stats)?;
    if !matches!(t.dtype, Dtype::F16 | Dtype::BF16) {
        return Err(BridgeError::Native(NativeError::Unexpected(format!(
            "cast of {}",
            t.dtype.name()
        ))));
    }
    let a = ctx.import(t.dtype, &t.shape, &t.bytes)?;
    let c = ctx.astype_f32(&a)?;
    let e = c.evaluate()?;
    let copy = e.host_copy()?;
    stats.output_nbytes = Some(copy.bytes.len());
    Ok((copy, stats))
}

fn memory_before(stats: &mut OpStats) -> Result<(), BridgeError> {
    native::reset_peak_memory()?;
    stats.active_before = Some(native::active_memory()?);
    Ok(())
}

/// OP-DQ.
pub fn dequantize(
    ctx: &NativeContext,
    w: &HostTensor,
    s: &HostTensor,
    b: &HostTensor,
    bits: u32,
    group_size: u32,
) -> Result<(DqGeometry, HostCopy, OpStats), (BridgeError, OpStats)> {
    let mut stats = OpStats::default();
    let before = ffi::call_counts();
    let decision = facts(ctx).and_then(|f| {
        stats.device_facts = Some(f);
        check_dq(&f, w, s, b, bits, group_size).map_err(BridgeError::Refused)
    });
    let after = ffi::call_counts();
    stats.numerical_before_decision = after.0 - before.0;
    stats.imports_before_decision = after.1 - before.1;
    let geom = match decision {
        Ok(g) => g,
        Err(e) => return Err((e, stats)),
    };
    let run = (|| -> Result<HostCopy, BridgeError> {
        let wa = ctx.import(w.dtype, &w.shape, &w.bytes)?;
        let sa = ctx.import(s.dtype, &s.shape, &s.bytes)?;
        let ba = ctx.import(b.dtype, &b.shape, &b.bytes)?;
        memory_before(&mut stats)?;
        let out = ctx.dequantize(&wa, &sa, &ba, group_size, bits)?;
        let e = out.evaluate()?;
        stats.peak_after = Some(native::peak_memory()?);
        stats.output_nbytes = Some(e.nbytes());
        Ok(e.host_copy()?)
    })();
    match run {
        Ok(copy) => Ok((geom, copy, stats)),
        Err(e) => Err((e, stats)),
    }
}

/// OP-QMM, public entry: transpose is always true.
pub fn quantized_matmul(
    ctx: &NativeContext,
    x: &HostTensor,
    w: &HostTensor,
    s: &HostTensor,
    b: &HostTensor,
    bits: u32,
    group_size: u32,
) -> Result<(QmmGeometry, HostCopy, OpStats), (BridgeError, OpStats)> {
    qmm_inner(ctx, true, x, w, s, b, bits, group_size)
}

/// Test-only entry point: the only way to request transpose=false, which is
/// refused (R-TRANSPOSE) before any MLX-C numerical call.
#[allow(clippy::too_many_arguments)]
pub fn quantized_matmul_transpose_test_only(
    ctx: &NativeContext,
    transpose: bool,
    x: &HostTensor,
    w: &HostTensor,
    s: &HostTensor,
    b: &HostTensor,
    bits: u32,
    group_size: u32,
) -> Result<(QmmGeometry, HostCopy, OpStats), (BridgeError, OpStats)> {
    qmm_inner(ctx, transpose, x, w, s, b, bits, group_size)
}

#[allow(clippy::too_many_arguments)]
fn qmm_inner(
    ctx: &NativeContext,
    transpose: bool,
    x: &HostTensor,
    w: &HostTensor,
    s: &HostTensor,
    b: &HostTensor,
    bits: u32,
    group_size: u32,
) -> Result<(QmmGeometry, HostCopy, OpStats), (BridgeError, OpStats)> {
    let mut stats = OpStats::default();
    let before = ffi::call_counts();
    let decision = facts(ctx).and_then(|f| {
        stats.device_facts = Some(f);
        check_qmm(&f, transpose, x, w, s, b, bits, group_size).map_err(BridgeError::Refused)
    });
    let after = ffi::call_counts();
    stats.numerical_before_decision = after.0 - before.0;
    stats.imports_before_decision = after.1 - before.1;
    let geom = match decision {
        Ok(g) => g,
        Err(e) => return Err((e, stats)),
    };
    // Admitted: transpose is true here (R-TRANSPOSE refused otherwise).
    debug_assert!(transpose);
    let run = (|| -> Result<HostCopy, BridgeError> {
        let xa = ctx.import(x.dtype, &x.shape, &x.bytes)?;
        // The packed U32 weight, unchanged.
        let wa = ctx.import(w.dtype, &w.shape, &w.bytes)?;
        let sa = ctx.import(s.dtype, &s.shape, &s.bytes)?;
        let ba = ctx.import(b.dtype, &b.shape, &b.bytes)?;
        memory_before(&mut stats)?;
        let out = if s.dtype == Dtype::F32 {
            // F32 metadata: no cast is issued (OP-CAST).
            ctx.quantized_matmul(&xa, &wa, &sa, &ba, true, group_size, bits)?
        } else {
            let s32 = ctx.astype_f32(&sa)?;
            let b32 = ctx.astype_f32(&ba)?;
            ctx.quantized_matmul(&xa, &wa, &s32, &b32, true, group_size, bits)?
        };
        let e = out.evaluate()?;
        stats.peak_after = Some(native::peak_memory()?);
        stats.output_nbytes = Some(e.nbytes());
        Ok(e.host_copy()?)
    })();
    match run {
        Ok(copy) => Ok((geom, copy, stats)),
        Err(e) => Err((e, stats)),
    }
}
