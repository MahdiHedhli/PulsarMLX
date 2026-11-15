//! One child of the prospectively granted Studio016 campaign.
#[cfg(pulsar_native_mlx)]
#[path = "../../../mlx-native-affine/src/bin/qualify/bridge.rs"]
mod bridge;
#[cfg(pulsar_native_mlx)]
#[path = "../../../mlx-native-affine/src/bin/qualify/ffi.rs"]
mod ffi;
#[cfg(pulsar_native_mlx)]
#[path = "../../../mlx-native-affine/src/bin/qualify/native.rs"]
mod native;
#[cfg(pulsar_native_mlx)]
#[path = "../real_execute.rs"]
mod real_execute;
#[cfg(pulsar_native_mlx)]
#[path = "../real_stage.rs"]
mod real_stage;
#[cfg(pulsar_native_mlx)]
#[path = "../selected_resources.rs"]
mod selected_resources;
#[cfg(pulsar_native_mlx)]
fn child(report: &mut serde_json::Value) -> Result<(), String> {
    use mlx_expert_ranges::{
        read_into::aligned_transport::{
            read_policy::{Policy, PreparedPolicy},
            Scratch, WindowPlan,
        },
        BoundedSource, ExpertRequest, ExpertRole, PlaneDestination,
    };
    use mlx_native_affine::{
        dtype::Dtype,
        fixture::{sha256_hex, HostTensor},
    };
    use serde_json::{json, Value};
    use std::{env, fs, path::PathBuf, process::Command};
    let args: Vec<_> = env::args_os().skip(1).collect();
    if args.len() != 1 {
        return Err("one private campaign directory required".into());
    }
    let dir = PathBuf::from(&args[0]);
    let verifier = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../scripts/research/studio016_campaign.py")
        .canonicalize()
        .map_err(|e| e.to_string())?;
    let vb = fs::read(&verifier).map_err(|e| e.to_string())?;
    if vb != include_bytes!("../../../../scripts/research/studio016_campaign.py") {
        return Err("verifier drift".into());
    }
    let exe = env::current_exe().map_err(|e| e.to_string())?;
    let v = Command::new("/opt/homebrew/bin/python3")
        .env_remove("DYLD_LIBRARY_PATH")
        .args(["-I", "-B"])
        .arg(verifier)
        .arg("verify-child")
        .arg(&dir)
        .arg(&exe)
        .output()
        .map_err(|e| e.to_string())?;
    if !v.status.success() || v.stdout.len() > 8192 {
        return Err(format!(
            "external grant or child custody refused: {}",
            String::from_utf8_lossy(&v.stderr)
        ));
    }
    let info: Value = serde_json::from_slice(&v.stdout).map_err(|e| e.to_string())?;
    let lib = PathBuf::from(info["prefix"].as_str().ok_or("prefix")?).join("lib");
    let mut seen = std::collections::BTreeSet::new();
    let count = unsafe { libc::_dyld_image_count() };
    if count > 4096 {
        return Err("image census".into());
    }
    for ix in 0..count {
        let ptr = unsafe { libc::_dyld_get_image_name(ix) };
        if ptr.is_null() {
            return Err("image name".into());
        }
        let name = unsafe { std::ffi::CStr::from_ptr(ptr) }
            .to_str()
            .map_err(|_| "image path encoding")?;
        let image = std::path::Path::new(name);
        let leaf = image.file_name().and_then(|x| x.to_str()).unwrap_or("");
        if (leaf.to_ascii_lowercase().contains("mlx") || leaf == "libjaccl.dylib")
            && leaf.ends_with(".dylib")
        {
            if !matches!(leaf, "libmlx.dylib" | "libmlxc.dylib" | "libjaccl.dylib")
                || image.canonicalize().map_err(|e| e.to_string())?
                    != lib.join(leaf).canonicalize().map_err(|e| e.to_string())?
                || image.metadata().map_err(|e| e.to_string())?.len() > 32 << 20
                || sha256_hex(&fs::read(image).map_err(|e| e.to_string())?) != info["libs"][leaf]
                || !seen.insert(leaf.to_owned())
            {
                return Err("unbound loaded MLX image".into());
            }
        }
    }
    if seen.len() != 3 {
        return Err("missing original image".into());
    }
    report["loaded_libraries"] = json!(seen);
    report["identity"] = info["identity"].clone();
    let binding: Value = serde_json::from_str(include_str!("../real_binding.json")).unwrap();
    let root = PathBuf::from(info["root"].as_str().ok_or("root")?);
    if root.canonicalize().map_err(|e| e.to_string())? != root {
        return Err("checkpoint redirect".into());
    }
    let inputs = fs::read(dir.join("input.f32le")).map_err(|e| e.to_string())?;
    if inputs.len() != 16384 || sha256_hex(&inputs) != binding["input_sha256"] {
        return Err("input".into());
    }
    let source = BoundedSource::open(&root).map_err(|e| e.to_string())?;
    let plan = source
        .plan(ExpertRequest {
            expert: 0,
            experts: 288,
            d: 4096,
            h: 2048,
            bits: [4; 3],
            group_size: 64,
            modules: ["gate", "up", "down"]
                .map(|r| format!("language_model.model.layers.3.mlp.switch_mlp.{r}_proj")),
        })
        .map_err(|e| e.to_string())?;
    let p = plan.record();
    if p.metadata_snapshot_sha256 != binding["metadata_snapshot_sha256"]
        || p.selected_bytes != 14155776
    {
        return Err("original checkpoint manifest".into());
    }
    let mut parts = Vec::new();
    let mut transport = 0u64;
    let mut receipt_bytes = 0usize;
    report["staging"] = json!([]);
    for role in [ExpertRole::Gate, ExpertRole::Up, ExpertRole::Down] {
        let i = role.index();
        let plane = &p.planes[i];
        let mut expected: [String; 3] = Default::default();
        for (j, r) in plane.ranges.iter().enumerate() {
            let a = &binding["ranges"][3 * i + j];
            if r.tensor != a["tensor"]
                || r.shard != a["shard"]
                || r.begin != a["begin"]
                || r.len != a["len"]
            {
                return Err("range mismatch".into());
            }
            expected[j] = a["sha256"].as_str().ok_or("digest")?.into();
        }
        let wp = WindowPlan::new(&plan, role, 16384).map_err(|e| e.to_string())?;
        let budget = PreparedPolicy::minimum_budget(&wp);
        if budget > 33_734_653 {
            return Err("policy budget".into());
        }
        let mut scratch = Scratch::new(&wp, budget).map_err(|e| e.to_string())?;
        let policy =
            PreparedPolicy::prepare(&wp, Policy::BufferedRequested, budget).map_err(|e| {
                report["failed_setup"] = json!(e.setup);
                e.cause.to_string()
            })?;
        let observed = policy.observation();
        if observed
            .original_stamps
            .iter()
            .any(|stamp| json!(stamp) != info["stamp"])
        {
            report["refused_retirement"] = json!(policy.retire());
            return Err("original descriptor stamp mismatch".into());
        }
        let mut data = plane.ranges.each_ref().map(|r| vec![0; r.len as usize]);
        let [w, s, b] = &mut data;
        let (filled, receipt) = match policy.read(
            &mut scratch,
            PlaneDestination::new(w, s, b, expected),
            budget,
        ) {
            Ok(v) => v.into_parts(),
            Err(e) => {
                report["failed_read"] = json!(e.receipt);
                report["refused_retirement"] = json!(policy.retire());
                return Err(e.cause.to_string());
            }
        };
        let logical = filled.into_receipt();
        let retired = policy.retire();
        transport += receipt.components.iter().map(|v| v.bytes).sum::<u64>();
        let row = json!({"reader":receipt,"logical":logical,"retired":retired});
        receipt_bytes += serde_json::to_vec(&row).map_err(|e| e.to_string())?.len() + 1;
        if !receipt.published
            || retired.live != 0
            || retired.released != receipt.setup.live
            || transport > 33_734_653
            || receipt_bytes + 2 > 2_073_600
        {
            return Err("reader or ledger".into());
        }
        report["staging"].as_array_mut().unwrap().push(row);
        let (n, k) = if i == 2 { (4096, 2048) } else { (2048, 4096) };
        let mut it = data.into_iter().enumerate();
        parts.push(std::array::from_fn(|_| {
            let (j, bytes) = it.next().unwrap();
            HostTensor {
                name: plane.ranges[j].tensor.clone(),
                dtype: if j == 0 { Dtype::U32 } else { Dtype::BF16 },
                shape: vec![n, if j == 0 { k / 8 } else { k / 64 }],
                bytes,
            }
        }));
    }
    if source.payload_read_calls() != 9 || source.requested_payload_bytes() != 14155776 {
        return Err("read counters".into());
    }
    report["source"] = json!({"metadata_sha256":p.metadata_snapshot_sha256,"logical_bytes":p.selected_bytes,"requested_window_bytes":transport,"logical_calls":9,"receipt_bytes":receipt_bytes+2});
    drop(plan);
    drop(source);
    let adapter = real_stage::SelectedAdapter {
        parts,
        input: HostTensor {
            name: "frozen expert input".into(),
            dtype: Dtype::F32,
            shape: vec![1, 4096],
            bytes: inputs,
        },
    };
    let result = real_execute::run(adapter, report);
    let (live, freed) = native::handle_census();
    report["final_native"] = json!({"calls":ffi::call_counts(),"live":live,"freed":freed,
        "double_frees":native::double_free_attempts(),"handler_messages":native::handler_messages(),
        "cleanup_errors":native::cleanup_errors().len()});
    result
}
fn main() {
    #[cfg(pulsar_native_mlx)]
    {
        let mut report = serde_json::json!({});
        let result = child(&mut report);
        report["outcome"] = serde_json::json!(if result.is_ok() {
            "executed"
        } else {
            "refused"
        });
        if let Err(ref e) = result {
            report["error"] = serde_json::json!(e);
        }
        println!("{}", report);
        if result.is_err() {
            std::process::exit(1)
        }
    }
    #[cfg(not(pulsar_native_mlx))]
    {
        eprintln!("pinned native build required");
        std::process::exit(69)
    }
}
