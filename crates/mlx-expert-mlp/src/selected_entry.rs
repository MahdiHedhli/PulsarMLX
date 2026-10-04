//! Review-bound selected entrypoint. All authority checks precede snapshot reads.
use crate::{native, provenance, selected_execute};
use mlx_expert_mlp::{
    selected_adapter::SelectedAdapter,
    selected_authority::{review_descriptor, strict},
    selected_snapshot::{Binding, SelectedSnapshot},
};
use mlx_native_affine::fixture::sha256_hex;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
use std::{
    fs::OpenOptions,
    io::{Read, Write},
    path::{Path, PathBuf},
    process::Command,
};

fn need(ok: bool, why: &str) -> Result<(), String> {
    if ok {
        Ok(())
    } else {
        Err(format!("SELECTED-R-AUTHORITY: {why}"))
    }
}
fn text<'a>(v: &'a Value, key: &str) -> Result<&'a str, String> {
    v[key].as_str().ok_or_else(|| format!("missing {key}"))
}
fn read(path: &Path, limit: u64, private: bool) -> Result<Vec<u8>, String> {
    let mut f = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW)
        .open(path)
        .map_err(|e| e.to_string())?;
    let a = f.metadata().map_err(|e| e.to_string())?;
    need(
        a.is_file() && a.len() <= limit,
        "bounded regular authority file",
    )?;
    if private {
        need(
            a.uid() == unsafe { libc::geteuid() } && a.mode() & 0o077 == 0,
            "private authority file",
        )?;
    }
    let mut raw = Vec::with_capacity(a.len() as usize);
    std::io::Read::by_ref(&mut f)
        .take(limit + 1)
        .read_to_end(&mut raw)
        .map_err(|e| e.to_string())?;
    let b = f.metadata().map_err(|e| e.to_string())?;
    need(
        raw.len() as u64 == a.len()
            && (
                a.dev(),
                a.ino(),
                a.len(),
                a.mtime(),
                a.mtime_nsec(),
                a.ctime(),
                a.ctime_nsec(),
            ) == (
                b.dev(),
                b.ino(),
                b.len(),
                b.mtime(),
                b.mtime_nsec(),
                b.ctime(),
                b.ctime_nsec(),
            ),
        "authority file changed",
    )?;
    Ok(raw)
}
fn hash_file(path: &Path, limit: u64) -> Result<String, String> {
    let mut f = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW)
        .open(path)
        .map_err(|e| e.to_string())?;
    let a = f.metadata().map_err(|e| e.to_string())?;
    need(a.is_file() && a.len() <= limit, "bounded hash file")?;
    let mut h = Sha256::new();
    let mut buf = [0u8; 262144];
    let mut count = 0;
    loop {
        let n = f.read(&mut buf).map_err(|e| e.to_string())?;
        if n == 0 {
            break;
        }
        count += n as u64;
        need(count <= limit, "hash growth")?;
        h.update(&buf[..n]);
    }
    let b = f.metadata().map_err(|e| e.to_string())?;
    need(
        count == a.len()
            && (
                a.dev(),
                a.ino(),
                a.len(),
                a.mtime(),
                a.mtime_nsec(),
                a.ctime(),
                a.ctime_nsec(),
            ) == (
                b.dev(),
                b.ino(),
                b.len(),
                b.mtime(),
                b.mtime_nsec(),
                b.ctime(),
                b.ctime_nsec(),
            ),
        "hash file changed",
    )?;
    Ok(format!("{:x}", h.finalize()))
}
fn git(repo: &Path, args: &[&str]) -> Result<String, String> {
    let out = Command::new("git")
        .current_dir(repo)
        .args(args)
        .output()
        .map_err(|e| e.to_string())?;
    need(out.status.success(), "git check")?;
    Ok(String::from_utf8(out.stdout)
        .map_err(|e| e.to_string())?
        .trim()
        .into())
}
fn confined(repo: &Path, name: &str) -> Result<PathBuf, String> {
    let p = Path::new(name);
    need(
        !p.is_absolute()
            && !name.is_empty()
            && p.components()
                .all(|c| matches!(c, std::path::Component::Normal(_))),
        "source relative path",
    )?;
    let path = repo.join(p).canonicalize().map_err(|e| e.to_string())?;
    need(path.starts_with(repo), "source path escape")?;
    Ok(path)
}
fn bound_receipt(cap: &Value, key: &str) -> Result<Value, String> {
    let r = &cap[key];
    let raw = read(Path::new(text(r, "path")?), 16 * 1024 * 1024, true)?;
    need(sha256_hex(&raw) == text(r, "sha256")?, "receipt hash")?;
    strict(&raw)
}

fn begin_real_native(
    cap: &Value,
    descriptor: &Value,
    binding: &Value,
    admission: &Value,
) -> Result<(), String> {
    use mlx_expert_mlp::selected_ledger as ledger;
    // Account home is independent of HOME and the capability's output/repo.
    let home = unsafe {
        let account = libc::getpwuid(libc::geteuid());
        need(!account.is_null(), "OS account home")?;
        let dir = (*account).pw_dir;
        need(!dir.is_null(), "OS account home path")?;
        std::ffi::CStr::from_ptr(dir)
            .to_str()
            .map_err(|e| e.to_string())?
            .to_owned()
    };
    let root = PathBuf::from(home).join(ledger::RELATIVE_ROOT);
    let dir = root.join(ledger::key(descriptor, binding)?);
    for path in [&root, &dir] {
        let m = path.symlink_metadata().map_err(|e| e.to_string())?;
        need(
            m.is_dir() && m.uid() == unsafe { libc::geteuid() } && m.mode() & 0o077 == 0,
            "private fixed ledger directory",
        )?;
    }
    let raw = read(&dir.join("ledger.json"), 1024 * 1024, true)?;
    let record = strict(&raw)?;
    ledger::validate(&record, cap, descriptor, binding)?;
    need(
        admission["real_attempt_sha256"] == record["capability_sha256"],
        "real admission ledger identity",
    )?;
    let start = strict(&read(&dir.join("reference-start.json"), 1024 * 1024, true)?)?;
    need(
        start["schema"] == "pulsarmlx.selected-real-start/2"
            && start["phase"] == "reference"
            && start["ledger_sha256"] == sha256_hex(&raw)
            && start["capability_sha256"] == record["capability_sha256"],
        "original R1 attempt ledger",
    )?;
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(dir.join("native-start.json"))
        .map_err(|e| e.to_string())?;
    let start = json!({"schema":"pulsarmlx.selected-real-start/2","phase":"native","ledger_sha256":sha256_hex(&raw),"capability_sha256":record["capability_sha256"]});
    file.write_all(&serde_json::to_vec(&start).map_err(|e| e.to_string())?)
        .map_err(|e| e.to_string())?;
    file.sync_all().map_err(|e| e.to_string())?;
    Ok(())
}

pub fn main() -> Result<(), String> {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    need(
        args.len() == 2 && args[0] == "--selected",
        "usage --selected PRIVATE_CAPABILITY.json",
    )?;
    let cap = strict(&read(Path::new(&args[1]), 1024 * 1024, true)?)?;
    need(
        cap["schema"] == "pulsarmlx.selected-capability/2",
        "capability schema",
    )?;
    let repo = PathBuf::from(text(&cap, "repo")?)
        .canonicalize()
        .map_err(|e| e.to_string())?;
    let capsule = read(
        Path::new(text(&cap, "capsule_path")?),
        16 * 1024 * 1024,
        true,
    )?;
    let review = read(
        Path::new(text(&cap, "review_path")?),
        16 * 1024 * 1024,
        true,
    )?;
    let descriptor = review_descriptor(
        &capsule,
        &review,
        text(&cap, "capsule_sha256")?,
        text(&cap, "review_sha256")?,
    )?;
    drop(capsule);
    drop(review);
    need(
        git(&repo, &["rev-parse", "HEAD"])? == text(&descriptor, "commit")?
            && git(&repo, &["rev-parse", "HEAD^{tree}"])? == text(&descriptor, "tree")?
            && git(&repo, &["status", "--porcelain"])?.is_empty(),
        "exact clean source",
    )?;
    for (name, want) in descriptor["source_sha256"]
        .as_object()
        .ok_or("source map")?
    {
        need(
            sha256_hex(&read(&confined(&repo, name)?, 16 * 1024 * 1024, false)?)
                == want.as_str().ok_or("source hash")?,
            "current source digest",
        )?;
        need(
            git(&repo, &["ls-files", "--error-unmatch", "--", name])? == *name,
            "committed source",
        )?;
    }
    let executable = std::env::current_exe().map_err(|e| e.to_string())?;
    need(
        hash_file(&executable, 256 * 1024 * 1024)? == text(&descriptor, "executable_sha256")?,
        "executable identity",
    )?;
    let contract_raw = read(
        &confined(&repo, text(&descriptor, "contract_path")?)?,
        1024 * 1024,
        false,
    )?;
    need(
        sha256_hex(&contract_raw) == text(&descriptor, "contract_sha256")?,
        "contract identity",
    )?;
    let contract = strict(&contract_raw)?;
    let manifest_raw = read(
        Path::new(text(&cap, "population_path")?),
        4 * 1024 * 1024,
        false,
    )?;
    need(
        sha256_hex(&manifest_raw) == text(&descriptor, "population_sha256")?,
        "population identity",
    )?;
    let manifest = strict(&manifest_raw)?;
    let x = read(Path::new(text(&cap, "input_path")?), 16384, false)?;
    need(
        x.len() == 16384
            && sha256_hex(&x) == text(&descriptor, "input_sha256")?
            && contract["input"]["sha256"] == sha256_hex(&x),
        "original input identity",
    )?;
    let kind = text(&cap, "kind")?;
    need(kind == "synthetic" || kind == "real", "execution scope")?;
    let control_id = cap.get("control_id").and_then(Value::as_str).unwrap_or("");
    if !control_id.is_empty() {
        need(
            kind == "synthetic"
                && manifest["mutations"]
                    .as_array()
                    .ok_or("mutations")?
                    .iter()
                    .any(|m| m["id"] == control_id),
            "frozen synthetic control only",
        )?;
    }
    let binding_value = if kind == "synthetic" {
        manifest["cases"]
            .as_array()
            .ok_or("cases")?
            .iter()
            .find(|c| c["id"] == cap["case_id"])
            .ok_or("frozen positive case")?["binding"]
            .clone()
    } else {
        // Raw private checkpoint name is not exported. Its content is also
        // cryptographically covered by the fixed original snapshot hash.
        let binding = &cap["real_binding"];
        need(
            binding["snapshot_sha256"] == contract["snapshot_sha256"]
                && binding["snapshot_bytes"] == contract["snapshot_bytes"]
                && binding["metadata_sha256"] == contract["metadata_sha256"]
                && binding["ranges_sha256"] == contract["ranges_sha256"],
            "original capture binding",
        )?;
        let qualified = bound_receipt(&cap, "synthetic_qualification")?;
        need(
            qualified["schema"] == "pulsarmlx.selected-synthetic-qualification/2"
                && qualified["status"] == "PASS"
                && qualified["commit"] == descriptor["commit"]
                && qualified["tree"] == descriptor["tree"]
                && qualified["executable_sha256"] == descriptor["executable_sha256"]
                && qualified["population_sha256"] == descriptor["population_sha256"]
                && qualified["review_sha256"] == cap["review_sha256"]
                && qualified["positive_count"] == 2
                && qualified["refusal_count"] == 26
                && qualified["mutation_count"] == 13
                && qualified["mutation_survivors"] == 0
                && qualified["primitive_regressions"] == 363
                && qualified["plane_regressions"] == 32,
            "full synthetic qualification required",
        )?;
        let ids: Vec<_> = ["cases", "refusals", "mutations"]
            .iter()
            .flat_map(|key| {
                manifest[*key]
                    .as_array()
                    .into_iter()
                    .flatten()
                    .map(|v| v["id"].clone())
            })
            .collect();
        need(
            qualified["passed_ids"] == Value::Array(ids),
            "exact synthetic population IDs",
        )?;
        binding.clone()
    };
    let admission = bound_receipt(&cap, "pre_admission")?;
    need(
        admission["schema"] == "pulsarmlx.selected-r1-admission/2"
            && admission["status"] == "ADMITTED"
            && admission["commit"] == descriptor["commit"]
            && admission["tree"] == descriptor["tree"]
            && admission["executable_sha256"] == descriptor["executable_sha256"]
            && admission["review_sha256"] == cap["review_sha256"]
            && admission["contract_sha256"] == descriptor["contract_sha256"]
            && admission["population_sha256"] == descriptor["population_sha256"]
            && admission["input_sha256"] == descriptor["input_sha256"]
            && admission["snapshot_sha256"] == binding_value["snapshot_sha256"]
            && admission["resources"]["status"] == "PASS",
        "original-byte pre-admission required",
    )?;
    let hashes = binding_value["ranges_sha256"]
        .as_array()
        .ok_or("range hashes")?
        .iter()
        .map(|v| v.as_str().map(str::to_owned).ok_or("range hash"))
        .collect::<Result<Vec<_>, _>>()?;
    let binding = Binding {
        snapshot_sha256: text(&binding_value, "snapshot_sha256")?.into(),
        snapshot_bytes: binding_value["snapshot_bytes"].as_u64().ok_or("size")?,
        metadata_sha256: text(&binding_value, "metadata_sha256")?.into(),
        checkpoint: text(&binding_value, "checkpoint")?.into(),
        ranges_sha256: hashes.try_into().map_err(|_| "nine hashes")?,
    };
    need(
        std::env::var("MLX_ENABLE_TF32").as_deref() == Ok("0"),
        "R-NAX",
    )?;
    for key in [
        "MLX_METAL_GPU_ARCH",
        "MLX_MAX_OPS_PER_BUFFER",
        "MLX_MAX_MB_PER_BUFFER",
        "DYLD_INSERT_LIBRARIES",
    ] {
        need(
            std::env::var_os(key).is_none(),
            "native environment override",
        )?;
    }
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
        need(pins[name]["sha256"] == want, "native pins before execution")?;
    }
    let out = PathBuf::from(text(&cap, "out")?)
        .canonicalize()
        .map_err(|e| e.to_string())?;
    let m = out.metadata().map_err(|e| e.to_string())?;
    need(
        m.is_dir()
            && m.uid() == unsafe { libc::geteuid() }
            && m.mode() & 0o077 == 0
            && !out.starts_with(&repo),
        "private output directory outside Git",
    )?;
    if kind == "real" {
        begin_real_native(&cap, &descriptor, &binding_value, &admission)?;
    }
    let mut result_file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(out.join("native-result.json"))
        .map_err(|e| e.to_string())?;
    // Snapshot bytes are first accessed after all exact review/admission checks.
    let mut report = json!({"schema":"pulsarmlx.selected-native-result/2","kind":kind,"case_id":cap["case_id"],"commit":descriptor["commit"],"tree":descriptor["tree"],"snapshot_sha256":binding.snapshot_sha256,"input_sha256":descriptor["input_sha256"],"review_sha256":cap["review_sha256"],"provenance":pins});
    let run = (|| {
        let snapshot = SelectedSnapshot::read(Path::new(text(&cap, "snapshot_path")?), &binding)?;
        let adapter = SelectedAdapter::bind(snapshot, x)?;
        if control_id.is_empty() {
            selected_execute::run(adapter, &mut report)
        } else {
            selected_execute::control(adapter, control_id, &mut report)
        }
    })();
    native::drain_residual_error("selected entry final cleanup");
    let (live, freed) = native::handle_census();
    report["final_cleanup"] = json!({"live":live,"freed":freed,"double_frees":native::double_free_attempts(),"handler_messages":native::handler_messages(),"errors":native::cleanup_errors().iter().map(|e|json!({"call":e.call,"status":e.status,"message":e.message})).collect::<Vec<_>>()});
    report["outcome"] = json!(if run.is_ok() {
        "executed"
    } else {
        "refused-or-error"
    });
    if let Err(ref e) = run {
        report["detail"] = json!(e);
    }
    result_file
        .write_all(&serde_json::to_vec_pretty(&report).map_err(|e| e.to_string())?)
        .map_err(|e| e.to_string())?;
    result_file.sync_all().map_err(|e| e.to_string())?;
    run?;
    need(
        live == 0
            && native::double_free_attempts() == 0
            && native::handler_messages() == 0
            && native::cleanup_errors().is_empty(),
        "cleanup failure",
    )?;
    Ok(())
}
