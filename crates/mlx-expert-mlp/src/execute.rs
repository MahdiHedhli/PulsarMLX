use crate::{bridge, ffi, native, provenance};
use mlx_expert_mlp::expert_tuple::{ExpertTuple, ROLES};
use mlx_native_affine::{
    compose::{compose, stage, Source},
    dtype::Dtype,
    family,
    fixture::{sha256_hex, HostTensor},
    refusal::{check_qmm, DeviceFacts},
};
use serde_json::{json, Value};
use std::os::unix::fs::{MetadataExt, PermissionsExt};
use std::{
    collections::BTreeMap,
    path::{Path, PathBuf},
    process::Command,
};

extern "C" {
    fn pulsar_mlp_cpu_guard(fpcr: *mut u64) -> i32;
    fn pulsar_mlp_activation(
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

fn read_json(p: &Path) -> Result<Value, String> {
    serde_json::from_slice(&std::fs::read(p).map_err(|e| e.to_string())?).map_err(|e| e.to_string())
}
fn hash_file(p: &Path) -> Result<String, String> {
    Ok(sha256_hex(&std::fs::read(p).map_err(|e| e.to_string())?))
}
fn git(repo: &Path, args: &[&str]) -> Result<String, String> {
    let p = Command::new("git")
        .args(args)
        .current_dir(repo)
        .output()
        .map_err(|e| e.to_string())?;
    if !p.status.success() {
        return Err("git verification failed".into());
    }
    Ok(String::from_utf8(p.stdout)
        .map_err(|e| e.to_string())?
        .trim()
        .into())
}
fn confined(root: &Path, rel: &str) -> Result<PathBuf, String> {
    if rel.is_empty()
        || Path::new(rel).is_absolute()
        || Path::new(rel)
            .components()
            .any(|c| !matches!(c, std::path::Component::Normal(_)))
    {
        return Err("fixture path not relative and confined".into());
    }
    let p = root.join(rel).canonicalize().map_err(|e| e.to_string())?;
    if !p.starts_with(root) {
        return Err("fixture path escapes root".into());
    }
    Ok(p)
}
fn snapshots() -> Value {
    let (n, i) = ffi::call_counts();
    json!({"numerical":n,"imports":i})
}
fn output(copy: &native::HostCopy) -> Value {
    json!({"dtype":copy.dtype.name(),"shape":copy.shape,"bytes":copy.bytes.len(),"sha256":sha256_hex(&copy.bytes),"f32_bits":copy.bytes.chunks_exact(4).map(|b|u32::from_le_bytes(b.try_into().unwrap())).collect::<Vec<_>>()})
}
fn host(copy: &native::HostCopy, name: &str) -> Result<HostTensor, String> {
    if copy.dtype != Dtype::F32
        || copy.shape.len() != 2
        || copy.bytes.len() != copy.shape.iter().product::<usize>() * 4
    {
        return Err("malformed intermediate".into());
    }
    if copy
        .bytes
        .chunks_exact(4)
        .any(|b| !f32::from_le_bytes(b.try_into().unwrap()).is_finite())
    {
        return Err("nonfinite intermediate".into());
    }
    Ok(HostTensor {
        name: name.into(),
        dtype: Dtype::F32,
        shape: copy.shape.clone(),
        bytes: copy.bytes.clone(),
    })
}
fn stage_qmm(
    gpu: &native::NativeContext,
    x: &HostTensor,
    parts: &[HostTensor; 3],
    bits: u32,
    name: &str,
    report: &mut Value,
) -> Result<native::HostCopy, String> {
    let before = snapshots();
    let mut fpcr = 0;
    if unsafe { pulsar_mlp_cpu_guard(&mut fpcr) } != 0 {
        return Err("MLP-R-CPU".into());
    }
    let r = bridge::quantized_matmul(gpu, x, &parts[0], &parts[1], &parts[2], bits, 64);
    let after = snapshots();
    if unsafe { pulsar_mlp_cpu_guard(&mut fpcr) } != 0 {
        return Err("MLP-R-CPU".into());
    }
    match r {
        Ok((g, copy, s)) => {
            let exponent = family::bound_exponent(g.m_eff, g.n, g.k, 64, bits);
            report[name] = json!({"outcome":"executed","output":output(&copy),"bound_gamma_n":exponent,
                "before":before,"after":after,"numerical_before_decision":s.numerical_before_decision,
                "imports_before_decision":s.imports_before_decision,"cpu_guard_checks":2,"cpu_fpcr":fpcr,
                "packed_weight_sha256":sha256_hex(&parts[0].bytes),"bits":bits,"group_size":64,
                "active_before":s.active_before,"peak_after":s.peak_after,"device_facts_gpu":s.device_facts==Some(DeviceFacts::GPU)});
            if s.numerical_before_decision != 0
                || s.imports_before_decision != 0
                || copy.shape != [g.m_eff, g.n]
                || copy.dtype != Dtype::F32
            {
                return Err("stage structural/guard evidence".into());
            }
            host(&copy, name)?;
            Ok(copy)
        }
        Err((e, s)) => {
            report[name] = json!({"outcome":"refused-or-error","detail":format!("{e:?}"),"before":before,"after":after,"numerical_before_decision":s.numerical_before_decision,"imports_before_decision":s.imports_before_decision});
            Err(format!("{e:?}"))
        }
    }
}

fn run(
    repo: &Path,
    root: &Path,
    case: &Value,
    mutation: &str,
    report: &mut Value,
) -> Result<(), String> {
    let manifest = read_json(&root.join("manifest.json"))?;
    let cp = &manifest["checkpoints"][case["checkpoint"].as_str().ok_or("checkpoint")?];
    let ck = confined(root, cp["path"].as_str().ok_or("checkpoint path")?)?;
    let mut config = std::fs::read_to_string(ck.join("config.json")).map_err(|e| e.to_string())?;
    if mutation == "ignore-bit-override" {
        let mut v: Value = serde_json::from_str(&config).map_err(|e| e.to_string())?;
        for role in [ROLES[0], ROLES[2]] {
            v["quantization"]
                .as_object_mut()
                .ok_or("quantization")?
                .remove(role);
        }
        config = serde_json::to_string(&v).map_err(|e| e.to_string())?;
    }
    let source = Source::open(&ck, &config, &BTreeMap::new()).map_err(|e| e.to_string())?;
    let e = case["expert"].as_u64().ok_or("expert")?;
    let d = case["D"].as_u64().ok_or("D")?;
    let h = case["H"].as_u64().ok_or("H")?;
    let m = case["M"].as_u64().ok_or("M")?;
    if ![1, 32].contains(&m) {
        return Err("MLP-R-TUPLE: M".into());
    }
    let mixed = case["profile"] == "mixed";
    let probe = case["probe"].as_str().unwrap_or("");
    report["phase"] = json!("tuple");
    report["at_start"] = snapshots();
    let tuple = if probe == "cross-expert"
        || mutation == "down-expert-swap"
        || mutation == "gate-down-role-swap"
    {
        let gate = compose(&source, ROLES[0], &[e]).map_err(|e| e.to_string())?;
        let up = compose(&source, ROLES[1], &[e]).map_err(|e| e.to_string())?;
        let down_expert = if mutation == "gate-down-role-swap" {
            e
        } else {
            (e + 1) % 3
        };
        let down = compose(&source, ROLES[2], &[down_expert]).map_err(|e| e.to_string())?;
        let mut p = [gate, up, down];
        if mutation == "gate-down-role-swap" {
            p.swap(0, 2);
        }
        ExpertTuple::bind(&source, p, e, d, h, mixed)?
    } else {
        ExpertTuple::select(&source, e, d, h, mixed)?
    };
    report["selections"] = json!(tuple
        .planes()
        .iter()
        .map(|p| p.record().to_json())
        .collect::<Vec<_>>());
    let before = source.backing().buffer_records();
    report["source_before"] = json!(before);
    let parts = tuple
        .planes()
        .iter()
        .map(stage)
        .collect::<Result<Vec<_>, _>>()?;
    let x = HostTensor {
        name: "x".into(),
        dtype: Dtype::F32,
        shape: vec![m as usize, d as usize],
        bytes: std::fs::read(confined(root, case["input"].as_str().ok_or("input")?)?)
            .map_err(|e| e.to_string())?,
    };
    if x.bytes.len() != m as usize * d as usize * 4 {
        return Err("input byte count".into());
    }
    report["input_sha256"] = json!(sha256_hex(&x.bytes));
    report["phase"] = json!("preflight");
    for i in 0..2 {
        check_qmm(
            &DeviceFacts::GPU,
            true,
            &x,
            &parts[i][0],
            &parts[i][1],
            &parts[i][2],
            tuple.planes()[i].identity().bits,
            64,
        )
        .map_err(|e| e.to_string())?;
    }
    ffi::verify_abi()?;
    native::ensure_error_handler();
    native::set_default_device_gpu().map_err(|e| e.to_string())?;
    let gpu = native::NativeContext::new(native::DeviceKind::Gpu).map_err(|e| e.to_string())?;
    if gpu.device_facts().map_err(|e| e.to_string())? != DeviceFacts::GPU {
        return Err("R-DEVICE".into());
    }
    report["provenance"] =
        provenance::collect(&std::env::var("MLX_C_PREFIX").map_err(|e| e.to_string())?)?;
    let pin = [
        (
            "libmlx",
            "c11a4d814042213b866ce66032107921857e4bbc8bfe0dd8150573a1ff9a8053",
        ),
        (
            "libmlxc",
            "e523f544758f042f78aeacdbe646af9d966432605ad4cfe760609b4044c2ce27",
        ),
        (
            "metallib",
            "5518fd265f31a8973732996d5eecc612301c94c1852156fb9ff30f6b708be365",
        ),
    ];
    for (name, want) in pin {
        if report["provenance"][name]["sha256"] != want {
            return Err("native pin mismatch before numerical execution".into());
        }
    }
    report["phase"] = json!("gate-up");
    let gi = if mutation == "gate-up-argument-swap" {
        1
    } else {
        0
    };
    let ui = 1 - gi;
    let gate = stage_qmm(
        &gpu,
        &x,
        &parts[gi],
        tuple.planes()[gi].identity().bits,
        "gate",
        report,
    )?;
    let up = stage_qmm(
        &gpu,
        &x,
        &parts[ui],
        tuple.planes()[ui].identity().bits,
        "up",
        report,
    )?;
    let g = host(&gate, "gate")?;
    let u = host(&up, "up")?;
    report["phase"] = json!("activation");
    for t in [&g, &u] {
        if t.shape != [m as usize, h as usize]
            || t.bytes
                .chunks_exact(4)
                .any(|b| f32::from_le_bytes(b.try_into().unwrap()).abs() > 16.)
        {
            return Err("MLP-R-ACTIVATION".into());
        }
    }
    let gv = g
        .bytes
        .chunks_exact(4)
        .map(|b| f32::from_le_bytes(b.try_into().unwrap()))
        .collect::<Vec<_>>();
    let uv = u
        .bytes
        .chunks_exact(4)
        .map(|b| f32::from_le_bytes(b.try_into().unwrap()))
        .collect::<Vec<_>>();
    let mut values = vec![0.; gv.len()];
    let mut gc = vec![0; gv.len()];
    let mut uc = vec![0; gv.len()];
    let mut stats = [0u64; 8];
    let mode = match mutation {
        "missing-upper-gate-clamp" => 2,
        "missing-up-upper-clamp" => 3,
        "missing-up-lower-clamp" => 4,
        _ => 0,
    };
    let rc = unsafe {
        pulsar_mlp_activation(
            gv.as_ptr(),
            uv.as_ptr(),
            m as i32,
            h as i32,
            values.as_mut_ptr(),
            gc.as_mut_ptr(),
            uc.as_mut_ptr(),
            stats.as_mut_ptr(),
            mode,
        )
    };
    let copy = native::HostCopy {
        dtype: Dtype::F32,
        shape: vec![m as usize, h as usize],
        bytes: values.iter().flat_map(|v| v.to_le_bytes()).collect(),
    };
    report["activation"] = json!({"status":rc,"stats":stats,"output":output(&copy),"gate_clamp_bits":gc,"up_clamp_bits":uc,"materializations":stats[5],"host_output_copies":3});
    if rc != 0 || stats[0] != 2 || stats[5] != 1 || stats[2] != stats[6] || stats[7] != 0 {
        return Err("activation execution/ownership failure".into());
    }
    let mut hidden = host(&copy, "h")?;
    if probe == "down-floor-guard" {
        hidden.bytes[0..4].copy_from_slice(&(2f32.powi(-33)).to_le_bytes());
        report["guard_control_injected_input_sha256"] = json!(sha256_hex(&hidden.bytes));
    }
    report["phase"] = json!("down-guard");
    let before_down = snapshots();
    let decision = check_qmm(
        &gpu.device_facts().map_err(|e| e.to_string())?,
        true,
        &hidden,
        &parts[2][0],
        &parts[2][1],
        &parts[2][2],
        tuple.planes()[2].identity().bits,
        64,
    );
    report["down_admission"] = json!({"before":before_down,"after":snapshots(),"decision":decision.as_ref().map(|_|"admitted").unwrap_or("refused"),"actual_input_sha256":sha256_hex(&hidden.bytes)});
    decision.map_err(|e| e.to_string())?;
    report["phase"] = json!("down");
    stage_qmm(
        &gpu,
        &hidden,
        &parts[2],
        tuple.planes()[2].identity().bits,
        "down",
        report,
    )?;
    report["source_after"] = json!(source.backing().buffer_records());
    if report["source_before"] != report["source_after"] {
        return Err("source backing changed".into());
    }
    report["copy_accounting"] = json!({"packed_plane_host_staging":9,"qmm_host_readbacks":3,"activation_input_copies":2,"activation_scalar_imports":2,"activation_stage_readbacks":3,"down_host_reimport":1,"zero_copy_claim":false});
    report["phase"] = json!("complete");
    let _ = repo;
    Ok(())
}

pub fn main() -> Result<(), String> {
    let mut opts = BTreeMap::new();
    let mut args = std::env::args().skip(1);
    while let Some(k) = args.next() {
        if !["--repo", "--out", "--admission", "--case", "--mutation"].contains(&k.as_str()) {
            return Err("unknown argument".into());
        }
        let v = args.next().ok_or("missing argument value")?;
        if opts.insert(k, v).is_some() {
            return Err("duplicate argument".into());
        }
    }
    let repo = PathBuf::from(opts.get("--repo").ok_or("--repo")?)
        .canonicalize()
        .map_err(|e| e.to_string())?;
    let out = PathBuf::from(opts.get("--out").ok_or("--out")?);
    std::fs::create_dir_all(&out).map_err(|e| e.to_string())?;
    let cap_path = PathBuf::from(
        opts.get("--admission")
            .ok_or("review-bound --admission required; no default execution")?,
    );
    let cm = std::fs::symlink_metadata(&cap_path).map_err(|e| e.to_string())?;
    if !cm.is_file()
        || cm.uid() != unsafe { libc::geteuid() }
        || cm.permissions().mode() & 0o077 != 0
    {
        return Err("private regular admission capability required".into());
    }
    let cap = read_json(&cap_path)?;
    if cap["status"] != "ADMITTED"
        || cap["review_sha256"].as_str().unwrap_or("").len() != 64
        || cap["commit"] != git(&repo, &["rev-parse", "HEAD"])?
        || cap["tree"] != git(&repo, &["rev-parse", "HEAD^{tree}"])?
        || !git(&repo, &["status", "--porcelain"])?.is_empty()
    {
        return Err("exact clean reviewed source required".into());
    }
    if cap["binary_sha256"] != hash_file(&std::env::current_exe().map_err(|e| e.to_string())?)? {
        return Err("candidate executable hash mismatch".into());
    }
    for (name, want) in cap["source_files"].as_object().ok_or("source bindings")? {
        if hash_file(&confined(&repo, name)?)? != want.as_str().ok_or("source hash")? {
            return Err("source binding mismatch".into());
        }
    }
    if std::env::var("MLX_ENABLE_TF32").as_deref() != Ok("0") {
        return Err("R-NAX".into());
    }
    for k in [
        "MLX_METAL_GPU_ARCH",
        "MLX_MAX_OPS_PER_BUFFER",
        "MLX_MAX_MB_PER_BUFFER",
        "DYLD_INSERT_LIBRARIES",
    ] {
        if std::env::var_os(k).is_some() {
            return Err("R-NAX environment override".into());
        }
    }
    let root = repo
        .join("fixtures/expert-mlp-composition")
        .canonicalize()
        .map_err(|e| e.to_string())?;
    let manifest = read_json(&root.join("manifest.json"))?;
    if cap["manifest_sha256"] != hash_file(&root.join("manifest.json"))? {
        return Err("manifest binding mismatch".into());
    }
    for (name, meta) in manifest["files"].as_object().ok_or("fixture files")? {
        if hash_file(&confined(&root, name)?)? != meta["sha256"].as_str().ok_or("fixture hash")? {
            return Err("fixture binding mismatch".into());
        }
    }
    let ident = opts.get("--case").ok_or("--case")?;
    if ident == "clamp-stage-probe" {
        ffi::verify_abi()?;
        native::ensure_error_handler();
        native::set_default_device_gpu().map_err(|e| e.to_string())?;
        let pins = provenance::collect(&std::env::var("MLX_C_PREFIX").map_err(|e| e.to_string())?)?;
        for (name, want) in [
            (
                "libmlx",
                "c11a4d814042213b866ce66032107921857e4bbc8bfe0dd8150573a1ff9a8053",
            ),
            (
                "libmlxc",
                "e523f544758f042f78aeacdbe646af9d966432605ad4cfe760609b4044c2ce27",
            ),
            (
                "metallib",
                "5518fd265f31a8973732996d5eecc612301c94c1852156fb9ff30f6b708be365",
            ),
        ] {
            if pins[name]["sha256"] != want {
                return Err("clamp probe native pin mismatch".into());
            }
        }
        let mut runs = Vec::new();
        for mode in [0, 1] {
            let mut value = [0f32];
            let mut gc = [0u32];
            let mut uc = [0u32];
            let mut stats = [0u64; 8];
            let rc = unsafe {
                pulsar_mlp_activation(
                    [-15f32].as_ptr(),
                    [1f32].as_ptr(),
                    1,
                    1,
                    value.as_mut_ptr(),
                    gc.as_mut_ptr(),
                    uc.as_mut_ptr(),
                    stats.as_mut_ptr(),
                    mode,
                )
            };
            runs.push(json!({"mode":mode,"status":rc,"h_bits":value[0].to_bits(),"gate_clamp_bits":gc,"up_clamp_bits":uc,"stats":stats}));
            if rc != 0 {
                return Err("clamp probe failed".into());
            }
        }
        native::drain_residual_error("clamp probe teardown");
        if native::handler_messages() != 0 || !native::cleanup_errors().is_empty() {
            return Err("clamp probe handler failed".into());
        }
        std::fs::write(out.join("report.json"),serde_json::to_vec_pretty(&json!({"schema":"pulsarmlx.f020.expert-mlp-clamp-probe/1","kind":"activation-stage-only","commit":cap["commit"],"tree":cap["tree"],"runs":runs})).map_err(|e|e.to_string())?).map_err(|e|e.to_string())?;
        return Ok(());
    }
    let case = manifest["cases"]
        .as_array()
        .ok_or("cases")?
        .iter()
        .find(|c| c["id"] == *ident)
        .ok_or("unknown case")?;
    let mutation = opts.get("--mutation").map(String::as_str).unwrap_or("");
    if ![
        "",
        "gate-up-argument-swap",
        "gate-down-role-swap",
        "down-expert-swap",
        "ignore-bit-override",
        "missing-upper-gate-clamp",
        "missing-up-upper-clamp",
        "missing-up-lower-clamp",
    ]
    .contains(&mutation)
    {
        return Err("unsupported native mutation; host-only controls must remain host-only".into());
    }
    let mut report = json!({"schema":"pulsarmlx.f020.expert-mlp-child/1","id":ident,"mutation":mutation,"commit":cap["commit"],"tree":cap["tree"],"manifest_sha256":cap["manifest_sha256"],"outcome":"error"});
    let r = run(&repo, &root, case, mutation, &mut report);
    native::drain_residual_error("expert MLP teardown");
    let (live, freed) = native::handle_census();
    report["cleanup"] = json!({"live":live,"freed":freed,"double_frees":native::double_free_attempts(),"handler_installs":native::handler_installs(),"handler_messages":native::handler_messages(),"errors":native::cleanup_errors().iter().map(|e|json!({"call":e.call,"status":e.status,"message":e.message})).collect::<Vec<_>>()});
    report["final_counters"] = snapshots();
    match r {
        Ok(()) => report["outcome"] = json!("executed"),
        Err(e) => {
            report["outcome"] = json!("refused-or-error");
            report["detail"] = json!(e);
        }
    }
    std::fs::write(
        out.join("report.json"),
        serde_json::to_vec_pretty(&report).map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())?;
    if live != 0
        || native::double_free_attempts() != 0
        || native::handler_messages() != 0
        || !native::cleanup_errors().is_empty()
    {
        return Err("native cleanup/handler failed; report preserved".into());
    }
    Ok(())
}
