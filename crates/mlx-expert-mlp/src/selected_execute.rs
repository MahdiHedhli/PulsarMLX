//! Selected full-shape execution core. No checkpoint loading or dense weights.
//! Entry point integration requires the separately verified review capability.
use crate::{bridge, ffi, native, selected_resources};
use mlx_expert_mlp::selected_adapter::{selected_preflight, SelectedAdapter};
use mlx_native_affine::{
    dtype::Dtype,
    fixture::{sha256_hex, HostTensor},
    refusal::DeviceFacts,
};
use serde_json::{json, Value};

extern "C" {
    fn pulsar_selected_cpu_guard(fpcr: *mut u64) -> i32;
    fn pulsar_selected_activation(
        g: *const f32,
        u: *const f32,
        m: i32,
        h: i32,
        out: *mut f32,
        gc: *mut u32,
        uc: *mut u32,
        stats: *mut u64,
        mode: i32,
    ) -> i32;
}
fn cpu() -> Result<u64, String> {
    let mut fpcr = 0;
    if unsafe { pulsar_selected_cpu_guard(&mut fpcr) } != 0 {
        return Err("SELECTED-R-CPU".into());
    }
    Ok(fpcr)
}
fn bits(t: &HostTensor) -> Value {
    json!({"shape":t.shape,"dtype":t.dtype.name(),"sha256":sha256_hex(&t.bytes),
      "f32_bits":t.bytes.chunks_exact(4).map(|b|u32::from_le_bytes(b.try_into().unwrap())).collect::<Vec<_>>()})
}
fn host(copy: native::HostCopy, n: usize) -> Result<HostTensor, String> {
    if copy.dtype != Dtype::F32
        || copy.shape != [1, n]
        || copy.bytes.len() != n * 4
        || copy
            .bytes
            .chunks_exact(4)
            .any(|b| !f32::from_le_bytes(b.try_into().unwrap()).is_finite())
    {
        return Err("SELECTED-R-RESULT".into());
    }
    Ok(HostTensor {
        name: "selected-result".into(),
        dtype: Dtype::F32,
        shape: copy.shape,
        bytes: copy.bytes,
    })
}
fn projection(
    ctx: &native::NativeContext,
    adapter: &SelectedAdapter,
    role: usize,
    x: &HostTensor,
    report: &mut Value,
) -> Result<HostTensor, String> {
    let parts = adapter.stage(role)?;
    let resource_before = selected_resources::sample()?;
    let before = ffi::call_counts();
    let bound = selected_preflight(role, x, &parts)?;
    if ffi::call_counts() != before {
        return Err("SELECTED-R-PREFLIGHT-CALLS".into());
    }
    let guard = cpu()?;
    let (geometry, copy, stats) =
        bridge::quantized_matmul(ctx, x, &parts[0], &parts[1], &parts[2], 4, 64)
            .map_err(|(e, _)| format!("{e:?}"))?;
    if cpu()? != guard
        || stats.numerical_before_decision != 0
        || stats.imports_before_decision != 0
        || geometry.m_eff != 1
        || geometry.n * geometry.k != 8388608
    {
        return Err("SELECTED-R-STAGE-AUDIT".into());
    }
    let out = host(copy, if role == 2 { 4096 } else { 2048 })?;
    report[["gate", "up", "down"][role]] = json!({"output":bits(&out),"bound_exponent":bound,
       "input_sha256":sha256_hex(&x.bytes),"packed_sha256":sha256_hex(&parts[0].bytes),
       "calls_before":before,"calls_after":ffi::call_counts(),"preflight_calls":0,
       "active_before":stats.active_before,"peak_after":stats.peak_after,"cpu_fpcr":guard,
       "resources_before":resource_before,"resources_after":selected_resources::sample()?});
    Ok(out)
}

/// The private selected entrypoint validates exact review and original-byte
/// admission before calling this core.
pub(crate) fn run(adapter: SelectedAdapter, report: &mut Value) -> Result<(), String> {
    // Preflight both original-input projections before creating native arrays.
    for role in 0..2 {
        selected_preflight(role, adapter.input(), &adapter.stage(role)?)?;
    }
    ffi::verify_abi()?;
    native::ensure_error_handler();
    native::set_default_device_gpu().map_err(|e| e.to_string())?;
    let gpu = native::NativeContext::new(native::DeviceKind::Gpu).map_err(|e| e.to_string())?;
    if gpu.device_facts().map_err(|e| e.to_string())? != DeviceFacts::GPU {
        return Err("R-DEVICE".into());
    }
    selected_resources::initialize()?;
    report["resources_initial"] = selected_resources::sample()?;
    let g = projection(&gpu, &adapter, 0, adapter.input(), report)?;
    let u = projection(&gpu, &adapter, 1, adapter.input(), report)?;
    let values = |t: &HostTensor| {
        t.bytes
            .chunks_exact(4)
            .map(|b| f32::from_le_bytes(b.try_into().unwrap()))
            .collect::<Vec<_>>()
    };
    let gv = values(&g);
    let uv = values(&u);
    if gv.iter().chain(uv.iter()).any(|v| v.abs() > 16.) {
        return Err("SELECTED-R-ACTIVATION".into());
    }
    let mut h = vec![0f32; 2048];
    let mut gc = vec![0u32; 2048];
    let mut uc = vec![0u32; 2048];
    let mut stats = [0u64; 8];
    let rc = unsafe {
        pulsar_selected_activation(
            gv.as_ptr(),
            uv.as_ptr(),
            1,
            2048,
            h.as_mut_ptr(),
            gc.as_mut_ptr(),
            uc.as_mut_ptr(),
            stats.as_mut_ptr(),
            0,
        )
    };
    report["activation"] =
        json!({"status":rc,"stats":stats,"gate_clamp_bits":gc,"up_clamp_bits":uc,"elements":2048});
    if rc != 0
        || stats[0] != 2
        || stats[2] != 9
        || stats[3] != 4
        || stats[4] != 13
        || stats[5] != 1
        || stats[6] != 9
        || stats[7] != 0
    {
        return Err("SELECTED-R-ACTIVATION-OWNERSHIP".into());
    }
    let hidden = host(
        native::HostCopy {
            dtype: Dtype::F32,
            shape: vec![1, 2048],
            bytes: h.iter().flat_map(|v| v.to_le_bytes()).collect(),
        },
        2048,
    )?;
    report["activation"]["output"] = bits(&hidden);
    report["activation"]["resources"] = selected_resources::sample()?;
    let before = ffi::call_counts();
    let decision = selected_preflight(2, &hidden, &adapter.stage(2)?);
    report["down_admission"] = json!({"decision":if decision.is_ok(){"admitted"}else{"refused"},"before":before,"after":ffi::call_counts(),"input_sha256":sha256_hex(&hidden.bytes)});
    decision?;
    projection(&gpu, &adapter, 2, &hidden, report)?;
    gpu.synchronize().map_err(|e| e.to_string())?;
    drop(gpu);
    native::drain_residual_error("selected full expert teardown");
    let (live, freed) = native::handle_census();
    report["cleanup"] = json!({"live":live,"freed":freed,"double_frees":native::double_free_attempts(),"handler_messages":native::handler_messages(),"cleanup_errors":native::cleanup_errors().len()});
    if live != 0
        || native::double_free_attempts() != 0
        || native::handler_messages() != 0
        || !native::cleanup_errors().is_empty()
    {
        return Err("SELECTED-R-CLEANUP".into());
    }
    Ok(())
}

/// Safe synthetic-only mutations; caller binds IDs to the frozen population and
/// rejects this entry for real mode. Controls are never counted as positives.
pub(crate) fn control(
    adapter: SelectedAdapter,
    id: &str,
    report: &mut Value,
) -> Result<(), String> {
    ffi::verify_abi()?;
    native::ensure_error_handler();
    native::set_default_device_gpu().map_err(|e| e.to_string())?;
    selected_resources::initialize()?;
    report["control_id"] = json!(id);
    if id == "omit-gate-bias" || id == "omit-up-bias" {
        let role = usize::from(id == "omit-up-bias");
        let mut parts = adapter.stage(role)?;
        parts[2].bytes.fill(0);
        selected_preflight(role, adapter.input(), &parts)?;
        let gpu = native::NativeContext::new(native::DeviceKind::Gpu).map_err(|e| e.to_string())?;
        let before = ffi::call_counts();
        let guard = cpu()?;
        let (_, copy, stats) = bridge::quantized_matmul(
            &gpu,
            adapter.input(),
            &parts[0],
            &parts[1],
            &parts[2],
            4,
            64,
        )
        .map_err(|(e, _)| format!("{e:?}"))?;
        if cpu()? != guard
            || stats.numerical_before_decision != 0
            || stats.imports_before_decision != 0
        {
            return Err("control guard failure".into());
        }
        let out = host(copy, 2048)?;
        report["projection_control"] = json!({"role":role,"output":bits(&out),"before":before,"after":ffi::call_counts(),"resources":selected_resources::sample()?});
        drop(gpu);
        return Ok(());
    }
    let (g, u, mode, swap) = match id {
        "lower-gate-clamp" => (-15f32, 1f32, 1, false),
        "missing-upper-gate-clamp" => (12., 2., 2, false),
        "missing-up-upper-clamp" => (2., 12., 3, false),
        "missing-up-lower-clamp" => (2., -12., 4, false),
        "gate-up-swap" => (1., 2., 0, true),
        _ => return Err("unsupported native selected control".into()),
    };
    let mut runs = Vec::new();
    for mutant in [false, true] {
        let (ga, ua) = if mutant && swap { (u, g) } else { (g, u) };
        let gv = vec![ga; 2048];
        let uv = vec![ua; 2048];
        let mut h = vec![0f32; 2048];
        let mut gc = vec![0u32; 2048];
        let mut uc = vec![0u32; 2048];
        let mut stats = [0u64; 8];
        let rc = unsafe {
            pulsar_selected_activation(
                gv.as_ptr(),
                uv.as_ptr(),
                1,
                2048,
                h.as_mut_ptr(),
                gc.as_mut_ptr(),
                uc.as_mut_ptr(),
                stats.as_mut_ptr(),
                if mutant { mode } else { 0 },
            )
        };
        let out = host(
            native::HostCopy {
                dtype: Dtype::F32,
                shape: vec![1, 2048],
                bytes: h.iter().flat_map(|v| v.to_le_bytes()).collect(),
            },
            2048,
        )?;
        runs.push(json!({"mutant":mutant,"status":rc,"stats":stats,"gate_clamp_bits":gc,"up_clamp_bits":uc,"output":bits(&out),"resources":selected_resources::sample()?}));
        if rc != 0 || stats[0] != 2 || stats[2..] != [9, 4, 13, 1, 9, 0] {
            report["activation_control"] = json!(runs);
            return Err("control activation ownership".into());
        }
    }
    report["activation_control"] = json!(runs);
    Ok(())
}
