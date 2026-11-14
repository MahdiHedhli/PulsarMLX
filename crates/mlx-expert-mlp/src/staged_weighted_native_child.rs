use crate::{
    ffi, native,
    resident_native::Copied,
    resident_verifier,
    weighted_native_guard::{Guard, Guarded},
};
use backend::{step::HostLayerExecutor, CancellationToken, ContractError, ErrorCategory};
use mlx_expert_mlp::{
    resident_fixture::{self as fixture},
    resident_pipeline::{Fault, StageResult},
    weighted,
};
use mlx_native_affine::{fixture::sha256_hex, frozen};
use serde_json::{json, Value};
use std::{
    cell::RefCell,
    ffi::CStr,
    fs,
    io::{Read, Write},
    path::{Path, PathBuf},
    process::Stdio,
    rc::Rc,
    sync::Arc,
};

extern "C" {
    fn pulsar_mlp_cpu_guard(fpcr: *mut u64) -> i32;
    fn mlx_set_cache_limit(old: *mut usize, limit: usize) -> i32;
    fn mlx_get_cache_memory(size: *mut usize) -> i32;
    fn mlx_clear_cache() -> i32;
}
fn probe() -> StageResult<u64> {
    let mut word = 0;
    if unsafe { pulsar_mlp_cpu_guard(&mut word) } != 0 {
        return Err(Fault::uncertain(format!(
            "arithmetic guard refused FPCR {word}"
        )));
    }
    Ok(word)
}
fn verify(ok: bool, message: &str) -> Result<(), String> {
    fixture::ensure(ok, message)
}
fn write(out: &Path, name: &str, bytes: &[u8], limit: usize) -> Result<(), String> {
    verify(bytes.len() <= limit, "output size")?;
    let mut file = fs::File::create_new(out.join(name)).map_err(|e| e.to_string())?;
    file.write_all(bytes)
        .and_then(|_| file.sync_all())
        .map_err(|e| e.to_string())
}
// Observe the actual image addresses in this process. The isolated verifier streams
// file hashes for these exact canonical paths; the child never buffers an entire dylib.
fn images() -> Result<Value, String> {
    let count = unsafe { libc::_dyld_image_count() };
    verify(count <= 4096, "image census")?;
    let mut paths = std::collections::BTreeMap::new();
    for i in 0..count {
        let ptr = unsafe { libc::_dyld_get_image_name(i) };
        verify(!ptr.is_null(), "image name")?;
        let value = unsafe { CStr::from_ptr(ptr) }
            .to_str()
            .map_err(|_| "image path")?;
        let path = Path::new(value);
        let name = path.file_name().and_then(|s| s.to_str()).unwrap_or("");
        if name.to_ascii_lowercase().contains("mlx") {
            verify(
                matches!(name, "libmlx.dylib" | "libmlxc.dylib")
                    && value.len() <= 1024
                    && !paths.contains_key(name),
                "unexpected MLX image",
            )?;
            paths.insert(
                name.to_owned(),
                path.canonicalize().map_err(|e| e.to_string())?,
            );
        }
    }
    let mut info: libc::Dl_info = unsafe { std::mem::zeroed() };
    verify(
        unsafe { libc::dladdr(ffi::mlx_version as *const libc::c_void, &mut info) } != 0
            && !info.dli_fname.is_null(),
        "mlx_version address",
    )?;
    let symbol = Path::new(
        unsafe { CStr::from_ptr(info.dli_fname) }
            .to_str()
            .map_err(|_| "symbol image path")?,
    )
    .canonicalize()
    .map_err(|e| e.to_string())?;
    verify(
        paths.len() == 2 && paths.get("libmlxc.dylib") == Some(&symbol),
        "symbol and loaded image differ",
    )?;
    Ok(json!({"loaded":paths,"mlx_version_symbol":symbol}))
}

#[path = "staged_weighted_native_pins.rs"]
mod pins;
fn admit(path: &Path) -> Result<Value, String> {
    let modules = pins::MODULES;
    let measured = images()?;
    let evidence = json!({"images":measured,"binary":std::env::current_exe().map_err(|e|e.to_string())?,
        "parent":unsafe{libc::getppid()},"reference":pins::REFERENCE,
        "seal":pins::SEAL,"abi":resident_verifier::layout_stamp(),"rustc":env!("F020_RUSTC_VERSION"),"profile":env!("F020_BUILD_PROFILE"),
        "mlx_commit":frozen::MLX_COMMIT,"mlx_c_commit":frozen::MLX_C_COMMIT,
        "prefix":std::env::var("MLX_C_PREFIX").map_err(|_|"native prefix")?});
    let prefix = PathBuf::from(evidence["prefix"].as_str().ok_or("prefix")?);
    verify(
        std::env::var_os("DYLD_LIBRARY_PATH").as_deref() == Some(prefix.join("lib").as_os_str())
            && std::env::var("MLX_ENABLE_TF32").as_deref() == Ok("0"),
        "native loader or TF32",
    )?;
    for (key, _) in std::env::vars_os() {
        let k = key.to_string_lossy();
        if k.starts_with("DYLD_") || k.starts_with("LD_") || k.starts_with("MLX_") {
            verify(
                matches!(
                    k.as_ref(),
                    "DYLD_LIBRARY_PATH" | "MLX_C_PREFIX" | "MLX_ENABLE_TF32"
                ),
                "native environment override",
            )?;
        }
    }
    let bootstrap = include_str!("../../../scripts/research/f020_staged_weighted_bootstrap.py");
    let mut cmd = resident_verifier::verifier_command(
        bootstrap,
        &serde_json::to_string(&modules).map_err(|e| e.to_string())?,
        path,
    )?;
    let mut child = cmd
        .arg(evidence.to_string())
        .stdout(Stdio::piped())
        .spawn()
        .map_err(|e| e.to_string())?;
    let mut answer = Vec::with_capacity(8193);
    let read = child
        .stdout
        .take()
        .ok_or("verifier pipe")?
        .take(8193)
        .read_to_end(&mut answer);
    if read.is_err() || answer.len() > 8192 {
        let _ = child.kill();
    }
    let status = child.wait().map_err(|e| e.to_string())?;
    verify(
        read.is_ok() && status.success() && answer.len() <= 8192,
        "child admission",
    )?;
    let cap: Value = serde_json::from_slice(&answer).map_err(|e| e.to_string())?;
    let directory = path.parent().ok_or("intent directory")?;
    let saved = fixture::checked_file(&directory.join("startup.json"), 8192)?;
    let receipt: Value = serde_json::from_slice(&saved).map_err(|e| e.to_string())?;
    let intent_hash = sha256_hex(&fixture::checked_file(path, 65536)?);
    verify(
        receipt == cap
            && cap.as_object().is_some_and(|v| v.len() == 9)
            && cap["intent_sha256"] == intent_hash
            && cap["reference"] == evidence["reference"]
            && cap["images"] == measured
            && images()? == measured,
        "original startup receipt or loaded images changed",
    )?;
    let profile = fixture::text(&cap["profile"])?;
    let mode = fixture::text(&cap["arm"])?;
    let order = [
        ("default", "Serial"),
        ("default", "Overlap"),
        ("mixed", "Serial"),
        ("mixed", "Overlap"),
    ];
    let index = order
        .iter()
        .position(|v| *v == (profile, mode))
        .ok_or("startup arm")?;
    verify(
        directory.file_name().and_then(|n| n.to_str())
            == Some(&format!("{index}-{profile}-{mode}")),
        "startup arm directory",
    )?;
    for (field, len) in [
        ("source", 40),
        ("tree", 40),
        ("binary_sha256", 64),
        ("build_sha256", 64),
    ] {
        let v = fixture::text(&cap[field])?;
        verify(
            v.len() == len
                && v.bytes()
                    .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)),
            "startup identity",
        )?;
    }
    Ok(cap)
}
pub fn run() -> Result<(), String> {
    let mut args = std::env::args_os().skip(1);
    verify(
        args.next().as_deref() == Some(std::ffi::OsStr::new("--intent")),
        "supervised weighted intent required",
    )?;
    let path = PathBuf::from(args.next().ok_or("intent")?);
    verify(
        args.next().is_none()
            && path.file_name().and_then(|s| s.to_str()) == Some("staged-intent.json")
            && path.canonicalize().map_err(|e| e.to_string())? == path,
        "canonical intent",
    )?;
    let cap = admit(&path)?;
    let out = path.parent().ok_or("intent directory")?.join("out");
    fs::create_dir(&out).map_err(|e| e.to_string())?;
    let mut phases = vec!["verified_child"];
    let result = run_arm(&cap, &out, &mut phases);
    if let Err(e) = &result {
        // Absence of an occurrence/receipt is not a zero-effect observation.
        write(&out,"failure.json",&serde_json::to_vec(&json!({"status":"failed","completed_phases":phases,"ffi_counts":ffi::call_counts(),"reason":e.chars().take(512).collect::<String>(),"unobserved_effects":"unknown"})).map_err(|e|e.to_string())?,8192)?;
    }
    result
}
fn run_arm(cap: &Value, out: &Path, phases: &mut Vec<&'static str>) -> Result<(), String> {
    let profile = fixture::text(&cap["profile"])?;
    let arm = fixture::text(&cap["arm"])?;
    let mode = match arm {
        "Serial" => weighted::staged::Mode::Serial,
        "Overlap" => weighted::staged::Mode::Overlap,
        _ => return Err("staged mode".into()),
    };
    let repo = std::env::current_dir().map_err(|e| e.to_string())?;
    let state = Rc::new(RefCell::new(Guard::new(probe).map_err(|e| e.reason)?));
    phases.push("initial_guard");
    ffi::verify_abi()?;
    phases.push("abi");
    native::ensure_error_handler();
    phases.push("error_handler");
    native::set_default_device_gpu().map_err(|e| e.to_string())?;
    phases.push("default_gpu");
    let version = native::mlx_version().map_err(|e| e.to_string())?;
    verify(version == frozen::MLX_VERSION, "native version")?;
    let (mut old, mut initial) = (0, 0);
    verify(
        unsafe { mlx_set_cache_limit(&mut old, 0) } == 0
            && unsafe { mlx_clear_cache() } == 0
            && unsafe { mlx_get_cache_memory(&mut initial) } == 0
            && initial == 0,
        "cache initialization",
    )?;
    phases.push("verified_version_and_empty_cache");
    let driver = Guarded {
        copied: Copied::new(),
        state: state.clone(),
    };
    let (mut host, store) = weighted::staged::setup(
        &repo,
        profile,
        weighted::RouteBook::fixed(profile)?,
        mode,
        driver,
        None,
    )?;
    phases.push("weighted_setup");
    let t = CancellationToken::new();
    let mut steps = Vec::with_capacity(5);
    let mut replay = Value::Null;
    let counts = || {
        let (n, i) = ffi::call_counts();
        [n, i]
    };
    let initial_counts = counts();
    let sequence = (|| -> Result<(), String> {
        for pos in 0..5 {
            let request = host.backend().book().request(pos)?;
            let result = host
                .execute(&request, &store, &store, &t, |_| {
                    if pos == 0 {
                        Err(ContractError::new(
                            ErrorCategory::InvalidStateTransition,
                            "delivery",
                            "lost fixture delivery",
                        ))
                    } else {
                        Ok(())
                    }
                })
                .map_err(|e| e.to_string())?;
            let after_commit = state.borrow_mut().check("committed");
            let snap = host.backend().snapshot();
            let observed = counts();
            let checks = state.borrow().words.len();
            verify(
                !result.replayed
                    && result.delivery_error.is_some() == (pos == 0)
                    && result.committed.token == 0
                    && result.committed.bytes.len() == 512
                    && result.committed.position == pos + 1,
                "weighted commit",
            )?;
            write(
                out,
                &format!("weighted-{pos}.f32"),
                &result.committed.bytes,
                512,
            )?;
            steps.push(json!({"position":pos,"request":request.id,"token":0,"input_reads":store.reads(),"counts":observed,
                "snapshot":snap,"peak":host.peak_reservation_bytes(),"active":host.active_reservation_bytes(),"sha256":sha256_hex(&result.committed.bytes)}));
            after_commit.map_err(|e| e.reason)?;
            if pos == 0 {
                let again = host
                    .execute(&request, &store, &store, &t, |_| Ok(()))
                    .map_err(|e| e.to_string())?;
                verify(
                    again.replayed
                        && Arc::ptr_eq(&result.committed, &again.committed)
                        && observed == counts()
                        && checks == state.borrow().words.len()
                        && snap == host.backend().snapshot()
                        && store.reads() == 1
                        && host.state().position() == 1,
                    "replay performed work",
                )?;
                replay = json!({"same_commit":true,"lost_delivery":true,"position":1,"input_reads":1,"counts":observed,"snapshot":snap,"guard_count":checks});
            }
        }
        Ok(())
    })();
    let mut size = steps.len() * 512;
    let mut rows = 0;
    for (i, (_, _, bytes)) in host.backend().records().enumerate() {
        verify(i < 12, "occurrence limit")?;
        write(out, &format!("occ-{i:02}.json"), bytes, 32768)?;
        size += bytes.len();
        rows += 1;
    }
    for (i, bytes) in host.backend().transport_records().enumerate() {
        verify(i < 5, "transport count")?;
        write(
            out,
            &format!("transport-{i}.json"),
            bytes,
            weighted::staged::TRANSPORT_ROW,
        )?;
        size += bytes.len();
    }
    let report = json!({"schema":"staged-weighted-native-arm-v1","admission":cap,"profile":profile,"arm":arm,"book":host.backend().book().digest(),
        "allocator":{"previous_limit":old,"initial_cache":initial,"cache_limit":0,"initial_clear":0},"version":version,"initial_counts":initial_counts,
        "steps":steps,"replay":replay,"row_count":rows,"final":host.backend().snapshot(),"ledger":host.backend().ledger(),"standing":host.backend().working_bytes(),
        "guards":state.borrow().words,"failure":sequence.as_ref().err(),"payload_before_report":size,
        "harness":{"limit":2<<20,"admission_and_paths":128<<10,"step_snapshots_and_guards":128<<10,"report_tree_and_encoding":768<<10,
            "verifier_and_provenance":384<<10,"caller_output_clones":0,"combined_bound":host.peak_reservation_bytes()+(2<<20)}});
    let mut data = vec![0; 128 << 10];
    let mut target = std::io::Cursor::new(data.as_mut_slice());
    serde_json::to_writer(&mut target, &report).map_err(|_| "bounded report encoding")?;
    let used = target.position() as usize;
    verify(size + used <= 2 << 20, "arm payload")?;
    write(out, "report.json", &data[..used], 128 << 10)?;
    sequence
}
