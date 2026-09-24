//! The qualification child (plan §8.1): after the environment assertion
//! (done in main), install the error handler, set the default device to GPU,
//! record provenance, run the E4 canary, run every manifest case in manifest
//! order, run the E4 canary again, and write the report.
//!
//! The child records outputs and structural invariants; the bound gates that
//! need R1 are decided by the parent, which never trusts a verdict the child
//! could have computed with candidate code.

use std::path::{Path, PathBuf};

use mlx_native_affine::dtype::{Dtype, FloatFormat};
use mlx_native_affine::family::{self, parse_architecture, Architecture};
use mlx_native_affine::fixture::{
    load_case, parse_manifest, sha256_hex, CaseSpec, HostTensor, LoadedCase, Manifest,
};
use mlx_native_affine::frozen;
use mlx_native_affine::gates::g_dq_codes;
use mlx_native_affine::refusal::{code_at, RefusalId};
use serde_json::{json, Value};

use crate::bridge::{self, BridgeError, OpStats};
use crate::ffi;
use crate::native::{self, DeviceKind, HostCopy, NativeContext};
use crate::provenance;
use crate::Args;

fn write_atomic(path: &Path, bytes: &[u8]) -> Result<(), String> {
    let tmp = path.with_extension("tmp");
    std::fs::write(&tmp, bytes).map_err(|e| format!("write {}: {e}", tmp.display()))?;
    std::fs::rename(&tmp, path).map_err(|e| format!("rename {}: {e}", path.display()))
}

/// Remove absolute paths (MLX-C appends its build-time `__FILE__`) so no
/// private path reaches a report.
pub fn redact(text: &str) -> String {
    let mut out = String::with_capacity(text.len());
    let mut rest = text;
    while let Some(i) = rest.find(" at /") {
        out.push_str(&rest[..i]);
        out.push_str(" at <path>");
        let tail = &rest[i + 4..];
        let end = tail
            .find(['\n', ';', ',', '"', ')', '}'])
            .unwrap_or(tail.len());
        rest = &tail[end..];
    }
    out.push_str(rest);
    out
}

fn stats_json(s: &OpStats) -> Value {
    let e5 = match (s.active_before, s.peak_after, s.output_nbytes) {
        (Some(a), Some(p), Some(o)) => Some(p.saturating_sub(a) >= o),
        _ => None,
    };
    json!({
        "numerical_calls_before_decision": s.numerical_before_decision,
        "imports_before_decision": s.imports_before_decision,
        "device_facts_gpu": s.device_facts.map(|f| f == mlx_native_affine::refusal::DeviceFacts::GPU),
        "e5_peak_memory": {
            "active_before": s.active_before,
            "peak_after": s.peak_after,
            "output_nbytes": s.output_nbytes,
            "peak_delta_ge_output_nbytes": e5,
        },
    })
}

struct Ctx<'a> {
    out_dir: PathBuf,
    fixture_dir: PathBuf,
    manifest: &'a Manifest,
    arch: Architecture,
}

fn tensor<'a>(case: &'a LoadedCase, name: &str) -> Result<&'a HostTensor, String> {
    case.tensor(name)
        .ok_or_else(|| format!("{}: no tensor {name}", case.spec.id))
}

fn save_output(cx: &Ctx, id: &str, copy: &HostCopy) -> Result<Value, String> {
    let rel = format!("outputs/{id}.bin");
    std::fs::write(cx.out_dir.join(&rel), &copy.bytes).map_err(|e| format!("{rel}: {e}"))?;
    Ok(json!({
        "file": rel,
        "sha256": sha256_hex(&copy.bytes),
        "dtype": copy.dtype.name(),
        "shape": copy.shape,
        "nbytes": copy.bytes.len(),
    }))
}

fn error_record(spec: &CaseSpec, err: String) -> Value {
    json!({"id": spec.id, "op": spec.op, "manifest_family": spec.family, "outcome": "error", "error": redact(&err)})
}

fn bridge_outcome(spec: &CaseSpec, e: BridgeError, stats: &OpStats) -> Value {
    match e {
        BridgeError::Refused(id) => json!({
            "id": spec.id, "op": spec.op, "manifest_family": spec.family,
            "outcome": "refused", "refusal_id": id.as_str(),
            "expected_refusal_id": spec.expected_refusal(),
            "stats": stats_json(stats),
        }),
        BridgeError::Native(n) => json!({
            "id": spec.id, "op": spec.op, "manifest_family": spec.family,
            "outcome": "error", "error": redact(&n.to_string()), "stats": stats_json(stats),
        }),
    }
}

fn run_case(cx: &Ctx, gpu: &NativeContext, spec: &CaseSpec) -> Value {
    match run_case_inner(cx, gpu, spec) {
        Ok(v) => v,
        Err(e) => error_record(spec, e),
    }
}

fn run_case_inner(cx: &Ctx, gpu: &NativeContext, spec: &CaseSpec) -> Result<Value, String> {
    let loaded = load_case(&cx.fixture_dir, spec).map_err(|e| e.to_string())?;
    match spec.op.as_str() {
        "import_u32" | "import_meta" => {
            let name = if spec.op == "import_u32" {
                "w"
            } else {
                "values"
            };
            let t = tensor(&loaded, name)?;
            match bridge::import_readback(gpu, t) {
                Ok((copy, stats)) => Ok(json!({
                    "id": spec.id, "op": spec.op, "manifest_family": spec.family, "outcome": "executed",
                    "structural": {"dtype_equal": copy.dtype == t.dtype, "shape_equal": copy.shape == t.shape},
                    "output": save_output(cx, &spec.id, &copy)?,
                    "stats": stats_json(&stats),
                })),
                Err(e) => Ok(bridge_outcome(spec, e, &OpStats::default())),
            }
        }
        "astype_f32" => {
            let input_id = spec
                .param_str("input_case")
                .ok_or("astype: no input_case")?;
            let input_spec = cx
                .manifest
                .case(input_id)
                .ok_or("astype: unknown input_case")?;
            let input = load_case(&cx.fixture_dir, input_spec).map_err(|e| e.to_string())?;
            let t = tensor(&input, "values")?;
            match bridge::cast_readback(gpu, t) {
                Ok((copy, stats)) => Ok(json!({
                    "id": spec.id, "op": spec.op, "manifest_family": spec.family, "outcome": "executed",
                    "input_case": input_id,
                    "structural": {"dtype_equal": copy.dtype == Dtype::F32, "shape_equal": copy.shape == t.shape},
                    "output": save_output(cx, &spec.id, &copy)?,
                    "stats": stats_json(&stats),
                })),
                Err(e) => Ok(bridge_outcome(spec, e, &OpStats::default())),
            }
        }
        "dequantize" => {
            let bits = spec.param_u64("bits").ok_or("bits")? as u32;
            let gs = spec.param_u64("group_size").ok_or("group_size")? as u32;
            let (w, s, b) = (
                tensor(&loaded, "w")?,
                tensor(&loaded, "scales")?,
                tensor(&loaded, "biases")?,
            );
            match bridge::dequantize(gpu, w, s, b, bits, gs) {
                Ok((g, copy, stats)) => {
                    let want_dtype = s.dtype;
                    Ok(json!({
                        "id": spec.id, "op": spec.op, "manifest_family": spec.family, "outcome": "executed",
                        "geometry": {"rows": g.rows, "K": g.k, "bits": g.bits, "group_size": g.group_size, "metadata_dtype": g.meta.name()},
                        "structural": {"dtype_equal": copy.dtype == want_dtype, "shape_equal": copy.shape == vec![g.rows, g.k]},
                        "output": save_output(cx, &spec.id, &copy)?,
                        "stats": stats_json(&stats),
                    }))
                }
                Err((e, stats)) => Ok(bridge_outcome(spec, e, &stats)),
            }
        }
        "quantized_matmul" => {
            let bits = spec.param_u64("bits").ok_or("bits")? as u32;
            let gs = spec.param_u64("group_size").ok_or("group_size")? as u32;
            let transpose = spec.param_bool("transpose").unwrap_or(true);
            let (x, w, s, b) = (
                tensor(&loaded, "x")?,
                tensor(&loaded, "w")?,
                tensor(&loaded, "scales")?,
                tensor(&loaded, "biases")?,
            );
            let cpu_ctx;
            let ctx = if spec.param_str("context") == Some("cpu") {
                // E6: a CPU-device context must be refused (R-DEVICE).
                cpu_ctx = NativeContext::new(DeviceKind::Cpu).map_err(|e| e.to_string())?;
                &cpu_ctx
            } else {
                gpu
            };
            let r = if transpose {
                bridge::quantized_matmul(ctx, x, w, s, b, bits, gs)
            } else {
                bridge::quantized_matmul_transpose_test_only(ctx, false, x, w, s, b, bits, gs)
            };
            match r {
                Ok((g, copy, stats)) => {
                    let mut want_shape = x.shape[..x.shape.len() - 1].to_vec();
                    want_shape.push(g.n);
                    let derived =
                        family::derive(g.m_eff, g.n, g.k, g.group_size as usize, g.bits, &cx.arch);
                    let cands =
                        family::candidates(g.m_eff, g.n, g.k, g.group_size as usize, g.bits);
                    let bound_n =
                        family::bound_exponent(g.m_eff, g.n, g.k, g.group_size as usize, g.bits);
                    Ok(json!({
                        "id": spec.id, "op": spec.op, "manifest_family": spec.family, "outcome": "executed",
                        "geometry": {"x_shape": x.shape, "M_eff": g.m_eff, "N": g.n, "K": g.k, "bits": g.bits,
                                     "group_size": g.group_size, "metadata_dtype": g.meta.name(), "x_dtype": "F32",
                                     "transpose": true, "contiguity": "row-contiguous host copies imported by mlx_array_new_data"},
                        "kernel": {
                            "architecture": cx.arch.name,
                            "batch_limit_L": derived.batch_limit,
                            "split_k": derived.split_k,
                            "derived_family": derived.family.as_str(),
                            "derived_family_gamma_n": derived.family_gamma_n,
                            "candidate_families": cands.iter().map(|c| json!({"family": c.family.as_str(), "split_k": c.split_k, "gamma_n": c.gamma_n})).collect::<Vec<_>>(),
                            "bound_gamma_n": bound_n,
                            "manifest_gamma_n": spec.manifest_gamma_n(),
                            "architecture_dependent_band": (6..=31).contains(&g.m_eff),
                        },
                        "metadata_cast": if s.dtype == Dtype::F32 { "none (F32 metadata)" } else { "bridge mlx_astype to float32 on the GPU stream" },
                        "structural": {"dtype_equal": copy.dtype == Dtype::F32, "shape_equal": copy.shape == want_shape},
                        "output": save_output(cx, &spec.id, &copy)?,
                        "stats": stats_json(&stats),
                    }))
                }
                Err((e, stats)) => Ok(bridge_outcome(spec, e, &stats)),
            }
        }
        other => Err(format!("unknown op {other}")),
    }
}

/// E4: the N-DQ-CODES canary, decided in the child (it has no R1).
fn canary(cx: &Ctx, gpu: &NativeContext, label: &str) -> Value {
    let r = (|| -> Result<Value, String> {
        let spec = cx
            .manifest
            .case(frozen::CANARY_CASE_ID)
            .ok_or("canary case missing")?;
        let loaded = load_case(&cx.fixture_dir, spec).map_err(|e| e.to_string())?;
        let bits = spec.param_u64("bits").ok_or("bits")? as u32;
        let gs = spec.param_u64("group_size").ok_or("group_size")? as u32;
        let (w, s, b) = (
            tensor(&loaded, "w")?,
            tensor(&loaded, "scales")?,
            tensor(&loaded, "biases")?,
        );
        let (g, copy, _) =
            bridge::dequantize(gpu, w, s, b, bits, gs).map_err(|(e, _)| format!("{e:?}"))?;
        let f: FloatFormat = s.dtype.float().ok_or("meta")?;
        let words = w.words_u32();
        let mut codes = Vec::with_capacity(g.rows * g.k);
        for r in 0..g.rows {
            for j in 0..g.k {
                codes.push(code_at(&words, w.shape[1], bits, r, j));
            }
        }
        let out: Vec<u32> = copy
            .bytes
            .chunks_exact(2)
            .map(|c| u16::from_le_bytes([c[0], c[1]]) as u32)
            .collect();
        let mismatches = if out.len() == codes.len() {
            g_dq_codes(f, &codes, &out)
        } else {
            usize::MAX
        };
        Ok(json!({
            "label": label, "case_id": spec.id, "elements": codes.len(),
            "mismatches": mismatches, "output_sha256": sha256_hex(&copy.bytes),
            "pass": mismatches == 0 && copy.dtype == s.dtype,
        }))
    })();
    r.unwrap_or_else(|e| json!({"label": label, "pass": false, "error": redact(&e)}))
}

fn read_frozen(repo: &Path, rel: &str, want: &str) -> Result<Vec<u8>, String> {
    let raw = std::fs::read(repo.join(rel)).map_err(|e| format!("{rel}: {e}"))?;
    let got = sha256_hex(&raw);
    if got != want {
        return Err(format!("{rel}: sha256 {got} != frozen {want}"));
    }
    Ok(raw)
}

/// Preserved cleanup failures and the result-handle census, for the report.
/// Written only after every native handle has been torn down.
fn cleanup_json() -> Value {
    let (created, adopted, error_freed) = native::result_census();
    let errors: Vec<Value> = native::cleanup_errors()
        .iter()
        .map(|e| json!({"call": e.call, "status": e.status, "message": e.message.as_deref().map(redact)}))
        .collect();
    json!({
        "errors": errors,
        "array_free_calls": native::array_free_calls(),
        "result_handles": {"created": created, "adopted": adopted, "freed_on_error_path": error_freed,
                           "balanced": created == adopted + error_freed},
    })
}

pub fn qualify(args: &Args) -> Result<(), String> {
    let abi = ffi::verify_abi()?;
    native::ensure_error_handler();
    native::set_default_device_gpu().map_err(|e| e.to_string())?;
    let prefix = std::env::var("PULSAR_F020_NATIVE_PREFIX")
        .map_err(|_| "PULSAR_F020_NATIVE_PREFIX unset".to_string())?;
    let prov = provenance::collect(&prefix)?;
    let arch = parse_architecture(prov["architecture"].as_str().unwrap_or_default());

    read_frozen(&args.repo, frozen::CONTRACT_PATH, frozen::CONTRACT_SHA256)?;
    read_frozen(&args.repo, frozen::GENERATOR_PATH, frozen::GENERATOR_SHA256)?;
    let manifest_raw = read_frozen(&args.repo, frozen::MANIFEST_PATH, frozen::MANIFEST_SHA256)?;
    let manifest = parse_manifest(&manifest_raw).map_err(|e| e.to_string())?;
    std::fs::create_dir_all(args.out.join("outputs")).map_err(|e| e.to_string())?;

    let cx = Ctx {
        out_dir: args.out.clone(),
        fixture_dir: args.repo.join(frozen::FIXTURE_DIR),
        manifest: &manifest,
        arch,
    };
    let gpu = NativeContext::new(DeviceKind::Gpu).map_err(|e| e.to_string())?;
    let canary_start = canary(&cx, &gpu, "start");
    let mut cases = Vec::with_capacity(manifest.cases.len());
    for spec in &manifest.cases {
        cases.push(run_case(&cx, &gpu, spec));
    }
    let canary_end = canary(&cx, &gpu, "end");
    let live_in_context = gpu.live_arrays();
    if args.test_fault.as_deref() == Some("cleanup-sync") {
        native::inject_teardown_sync_failure();
    }
    drop(gpu);
    native::drain_residual_error("residual error slot after teardown");
    let (live, freed) = native::handle_census();

    let report = json!({
        "schema": frozen::CHILD_REPORT_SCHEMA,
        "contract_sha256": frozen::CONTRACT_SHA256,
        "manifest_sha256": frozen::MANIFEST_SHA256,
        "generator_sha256": frozen::GENERATOR_SHA256,
        "abi_values": abi,
        "error_handler": {"installs": native::handler_installs(), "messages_received": native::handler_messages()},
        "provenance": prov,
        "canary_start": canary_start,
        "canary_end": canary_end,
        "cases": cases,
        "handles": {"live_arrays_in_context_at_drop": live_in_context, "live_array_handles_after_context_drop": live,
                    "array_handles_freed": freed, "double_free_attempts": native::double_free_attempts()},
        "call_counts": {"numerical": ffi::call_counts().0, "imports": ffi::call_counts().1},
        "thread": "all MLX work on the main thread",
        "cleanup": cleanup_json(),
        "test_fault": args.test_fault,
        "completed": true,
    });
    let bytes = serde_json::to_vec_pretty(&report).map_err(|e| e.to_string())?;
    write_atomic(&args.out.join("report.json"), &bytes)
}

/// B8/B9 self-tests: ownership permutations, error-path frees, an injected
/// MLX-C error that becomes a Rust error after which the child continues, and
/// the single handler install.
pub fn selftest(args: &Args) -> Result<(), String> {
    ffi::verify_abi()?;
    native::ensure_error_handler();
    native::set_default_device_gpu().map_err(|e| e.to_string())?;
    let mut checks = serde_json::Map::new();
    let mut all = true;
    let mut record = |name: &str, pass: bool, detail: Value| {
        all &= pass;
        checks.insert(name.to_string(), json!({"pass": pass, "detail": detail}));
    };

    let bytes: Vec<u8> = (0u32..64).flat_map(|v| v.to_le_bytes()).collect();
    // L-ONCE / L-OUTLIVE: every drop-order permutation of three arrays frees
    // each handle exactly once and leaves the context with zero live arrays.
    {
        let ctx = NativeContext::new(DeviceKind::Gpu).map_err(|e| e.to_string())?;
        let perms: [[usize; 3]; 6] = [
            [0, 1, 2],
            [0, 2, 1],
            [1, 0, 2],
            [1, 2, 0],
            [2, 0, 1],
            [2, 1, 0],
        ];
        let mut ok = true;
        for p in perms {
            let (_, freed0) = native::handle_census();
            let mut arrs: Vec<Option<_>> = (0..3)
                .map(|_| ctx.import(Dtype::U32, &[8, 8], &bytes).ok())
                .collect();
            ok &= arrs.iter().all(Option::is_some) && ctx.live_arrays() == 3;
            for (step, &i) in p.iter().enumerate() {
                arrs[i] = None;
                ok &= ctx.live_arrays() == 2 - step as i64;
            }
            let (_, freed1) = native::handle_census();
            ok &= freed1 - freed0 == 3;
        }
        record(
            "L-ONCE drop-order permutations",
            ok && native::double_free_attempts() == 0,
            json!({"permutations": 6}),
        );
        record(
            "L-OUTLIVE zero live arrays before context drop",
            ctx.live_arrays() == 0,
            json!(ctx.live_arrays()),
        );
    }
    record(
        "zero live native array handles after context drop",
        native::handle_census().0 == 0,
        json!(native::handle_census()),
    );

    // B9 + L-ERRFREE: an injected MLX-C error (mismatched shapes passed
    // straight to mlx_quantized_matmul, bypassing the bridge refusals)
    // becomes a typed Rust error with the handler's message; the result
    // handle is freed; the child continues and a valid op then succeeds.
    {
        let ctx = NativeContext::new(DeviceKind::Gpu).map_err(|e| e.to_string())?;
        let x = ctx
            .import(Dtype::F32, &[1, 7], &[0u8; 28])
            .map_err(|e| e.to_string())?;
        let w = ctx
            .import(Dtype::U32, &[64, 8], &vec![0u8; 64 * 8 * 4])
            .map_err(|e| e.to_string())?;
        let s = ctx
            .import(Dtype::F32, &[64, 1], &vec![0u8; 256])
            .map_err(|e| e.to_string())?;
        let live_before = ctx.live_arrays();
        let msgs_before = native::handler_messages();
        let census_before = native::result_census();
        let frees_before = native::array_free_calls();
        let r = ctx.quantized_matmul(&x, &w, &s, &s, true, 64, 4);
        let census_after = native::result_census();
        let frees_after = native::array_free_calls();
        let (is_err, message) = match &r {
            Err(native::NativeError::Status { message, .. }) => (true, message.clone()),
            _ => (false, None),
        };
        drop(r);
        // Exactly one result handle created, none adopted, exactly one freed
        // on the error path (counted at the free itself, independently of
        // adoption), exactly one array free issued, and no live change.
        let freed_ok = census_after.0 - census_before.0 == 1
            && census_after.1 - census_before.1 == 0
            && census_after.2 - census_before.2 == 1
            && frees_after - frees_before == 1
            && ctx.live_arrays() == live_before;
        record(
            "B9 injected MLX-C error becomes a Rust error",
            is_err && message.is_some() && native::handler_messages() > msgs_before,
            json!({"message": message.as_deref().map(redact)}),
        );
        record(
            "L-ERRFREE result handle freed on the error path",
            freed_ok,
            json!({"result_handles_created": census_after.0 - census_before.0,
                   "adopted": census_after.1 - census_before.1,
                   "freed_on_error_path": census_after.2 - census_before.2,
                   "array_free_calls": frees_after - frees_before,
                   "live_arrays": ctx.live_arrays()}),
        );
        // Continue: a valid import + astype + evaluate on the same context.
        let h = ctx
            .import(Dtype::BF16, &[2], &[0x80, 0x3F, 0x00, 0x40])
            .map_err(|e| e.to_string())?;
        let c = ctx
            .astype_f32(&h)
            .and_then(|c| c.evaluate())
            .and_then(|e| e.host_copy());
        let cont = matches!(&c, Ok(copy) if copy.bytes == [0, 0, 0x80, 0x3F, 0, 0, 0, 0x40]);
        record(
            "B9 child continues after the injected error",
            cont,
            json!(match &c {
                Ok(copy) => sha256_hex(&copy.bytes),
                Err(e) => redact(&e.to_string()),
            }),
        );
    }
    // Refusal before any MLX-C call: a refused request issues no import and
    // no numerical call.
    {
        let ctx = NativeContext::new(DeviceKind::Gpu).map_err(|e| e.to_string())?;
        let x = HostTensor {
            name: "x".into(),
            dtype: Dtype::F16,
            shape: vec![1, 64],
            bytes: vec![0; 128],
        };
        let w = HostTensor {
            name: "w".into(),
            dtype: Dtype::U32,
            shape: vec![64, 8],
            bytes: vec![0; 64 * 8 * 4],
        };
        let s = HostTensor {
            name: "scales".into(),
            dtype: Dtype::BF16,
            shape: vec![64, 1],
            bytes: vec![0; 128],
        };
        let r = bridge::quantized_matmul(&ctx, &x, &w, &s, &s, 4, 64);
        let ok = matches!(&r, Err((BridgeError::Refused(RefusalId::XDtype), st)) if st.numerical_before_decision == 0 && st.imports_before_decision == 0);
        record(
            "B6 refusal precedes every MLX-C numerical call and import",
            ok && ctx.live_arrays() == 0,
            json!(null),
        );
    }
    record(
        "single error-handler install",
        native::handler_installs() == 1,
        json!(native::handler_installs()),
    );
    native::drain_residual_error("residual error slot after teardown");
    let (created, adopted, error_freed) = native::result_census();
    record(
        "L-ERRFREE result-handle census balanced (created = adopted + freed on error path)",
        created == adopted + error_freed && error_freed >= 1,
        json!({"created": created, "adopted": adopted, "freed_on_error_path": error_freed}),
    );
    let cleanup = cleanup_json();
    record(
        "no preserved cleanup errors",
        cleanup["errors"].as_array().is_some_and(Vec::is_empty),
        cleanup.clone(),
    );

    let report = json!({
        "schema": "pulsarmlx.f020.slice2b-child-selftest/1.0.0",
        "checks": checks,
        "pass": all,
        "completed": true,
    });
    let bytes = serde_json::to_vec_pretty(&report).map_err(|e| e.to_string())?;
    std::fs::create_dir_all(&args.out).map_err(|e| e.to_string())?;
    write_atomic(&args.out.join("selftest.json"), &bytes)
}
