//! Native execution is opt-in and belongs only to the two named host routes.
#![cfg(feature = "native-adoption")]
use mlx_native_affine::{
    fixture::sha256_hex,
    harness::{child_env, run_child, ChildOutcome},
};
use serde_json::{json, Value};
use std::{
    fs,
    io::Write,
    path::{Path, PathBuf},
    time::Duration,
};
#[path = "support/continuation.rs"]
mod continuation;
#[path = "support/performance.rs"]
mod performance;

fn continuation_call(campaign: &Path, freeze: &Value, command: &str, extra: &[&str]) -> Value {
    let helper = Path::new(env!("CARGO_MANIFEST_DIR")).join("tools/m1a_continuation.py");
    let python = Path::new(freeze["python"].as_str().expect("bound interpreter"));
    assert_eq!(
        packed_affine_adoption::file_sha256(python).unwrap(),
        freeze["python_sha256"]
    );
    let relative = "experiments/packed-affine-adoption/tools/m1a_continuation.py";
    let row = freeze["source_inventory"]["files"]
        .as_array()
        .unwrap()
        .iter()
        .find(|row| row["path"] == relative)
        .expect("bound helper source");
    assert_eq!(
        packed_affine_adoption::file_sha256(&helper).unwrap(),
        row["sha256"]
    );
    let result = std::process::Command::new(python)
        .arg("-B")
        .arg(helper)
        .arg(command)
        .arg(campaign)
        .args(extra)
        .output()
        .expect("host admission helper");
    assert!(
        result.status.success(),
        "continuation admission refused: {}",
        String::from_utf8_lossy(&result.stderr)
    );
    serde_json::from_slice(&result.stdout).expect("continuation admission result")
}

fn create(path: &Path, value: &Value) {
    let mut f = fs::OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(path)
        .expect("preserve existing attempts");
    writeln!(f, "{}", serde_json::to_string_pretty(value).unwrap()).unwrap();
    f.sync_all().unwrap();
}
fn read(path: &Path) -> Value {
    serde_json::from_slice(&fs::read(path).unwrap()).unwrap()
}
fn child(root: &Path, prefix: &Path, label: &str, mut config: Value, seconds: u64) -> Value {
    let freeze = read(&root.parent().unwrap().join("freeze.json"));
    if freeze["schema"] == continuation::SCHEMA {
        continuation_call(
            root.parent().unwrap(),
            &freeze,
            "before-child",
            &["--label", label],
        );
    }
    for key in [
        "native_libraries",
        "binary_sha256",
        "source_commit",
        "source_tree",
    ] {
        config[key] = freeze[key].clone();
    }
    for key in ["host", "generator_hashes", "dependency_manifest_sha256"] {
        config[key] = freeze[key].clone();
    }
    let input = root.join(format!("{label}.config.json"));
    create(&input, &config);
    let out = root.join(label);
    let run = run_child(
        Path::new(env!("CARGO_BIN_EXE_adoption-probe")),
        &[input.to_string_lossy().into(), out.to_string_lossy().into()],
        &child_env(prefix, root),
        Duration::from_secs(seconds),
        root,
        label,
    );
    create(
        &root.join(format!("{label}.outcome.json")),
        &json!({"outcome":run.outcome.describe(),"elapsed_ms":run.elapsed_ms,"binary_sha256":packed_affine_adoption::file_sha256(env!("CARGO_BIN_EXE_adoption-probe")).unwrap(),"config_sha256":sha256_hex(&fs::read(input).unwrap())}),
    );
    if config["mode"] == "raw-length" {
        let events = fs::read_to_string(out.join("events.jsonl")).unwrap_or_default();
        assert!(
            events
                .lines()
                .filter_map(|s| serde_json::from_str::<Value>(s).ok())
                .any(|v| v["phase"] == "before-call"),
            "raw probe did not reach its attempted call"
        );
        match run.outcome {
            ChildOutcome::Timeout {
                reaped_signal: Some(9),
                ..
            } => return json!({"raw_probe":"timeout-reaped"}),
            ChildOutcome::Signaled(s) => return json!({"raw_probe":"signal","signal":s}),
            ChildOutcome::Exited(0) => return read(&out.join("run.json")),
            other => panic!("raw probe harness failure: {other:?}"),
        }
    }
    assert_eq!(
        run.outcome,
        ChildOutcome::Exited(0),
        "preserve failure; no retry"
    );
    let report = read(&out.join("run.json"));
    assert_eq!(
        report["config_sha256"],
        sha256_hex(&fs::read(root.join(format!("{label}.config.json"))).unwrap())
    );
    assert_eq!(report["provenance"]["loaded_images_verified"], true);
    for key in [
        "native_libraries",
        "binary_sha256",
        "source_commit",
        "source_tree",
    ] {
        assert_eq!(report["provenance"][key], freeze[key]);
    }
    assert_eq!(report["lifetime"]["live"], 0);
    assert_eq!(report["lifetime"]["created"], report["lifetime"]["freed"]);
    assert_eq!(report["lifetime"]["early_free_count"], 0);
    for key in ["parent_counts", "view_counts", "output_counts"] {
        assert_eq!(report["lifetime"][key][0], report["lifetime"][key][1]);
    }
    assert_eq!(
        report["lifetime"]["completed_callbacks"],
        u64::from(config["arm"] == "adopted")
    );
    if config["mode"] != "inherited" {
        assert_eq!(
            report["identity"]["contract_sha256"],
            packed_affine_adoption::CONTRACT
        );
        assert_eq!(
            report["identity"]["fixture_manifest_sha256"],
            config["fixture_manifest_sha256"]
        );
        assert_eq!(report["lifetime"]["quarantine"], false);
    }
    report
}
#[test]
fn required_native_m1a() {
    let role = std::env::var("PULSAR_ADOPTION_HOST_ROLE").expect("native host role required");
    match role.as_str() {
        "native-ci" => assert_eq!(std::env::var("GITHUB_ACTIONS").as_deref(), Ok("true")),
        "m1-ultra-studio" => {
            let output = std::process::Command::new("/usr/sbin/sysctl")
                .args(["-n", "machdep.cpu.brand_string"])
                .output()
                .unwrap();
            assert!(
                output.status.success()
                    && String::from_utf8_lossy(&output.stdout).trim() == "Apple M1 Ultra"
            );
        }
        _ => panic!("unapproved execution host"),
    }
    let campaign = PathBuf::from(
        std::env::var_os("PULSAR_ADOPTION_CAMPAIGN").expect("existing frozen campaign required"),
    );
    let freeze = read(&campaign.join("freeze.json"));
    let phase = std::env::var("PULSAR_ADOPTION_PHASE").ok();
    let continuation_raw = continuation::raw_allowed(&freeze, phase.as_deref())
        .expect("freeze policy refused before launch");
    if continuation_raw.is_some() {
        let parent = std::env::current_exe().expect("actual parent path");
        continuation_call(
            &campaign,
            &freeze,
            "admit",
            &[
                "--parent",
                parent.to_str().unwrap(),
                "--binary",
                env!("CARGO_BIN_EXE_adoption-probe"),
            ],
        );
    }
    assert_eq!(freeze["contract_sha256"], packed_affine_adoption::CONTRACT);
    assert_eq!(freeze["host_role"], role);
    let root = campaign.join("m1a");
    let prefix = PathBuf::from(std::env::var_os("MLX_C_PREFIX").unwrap());
    if continuation_raw.is_some() {
        assert_eq!(
            prefix.canonicalize().unwrap(),
            PathBuf::from(freeze["native_prefix"].as_str().unwrap())
        );
    }
    assert_eq!(
        prefix,
        PathBuf::from(std::env::var_os("MLX_PREFIX").unwrap()),
        "one pinned prefix required"
    );
    assert_eq!(
        freeze["native_libraries"]
            .as_object()
            .unwrap()
            .keys()
            .map(String::as_str)
            .collect::<Vec<_>>(),
        ["libmlx.dylib", "libmlxc.dylib", "mlx.metallib"]
    );
    for (name, record) in freeze["native_libraries"]
        .as_object()
        .expect("frozen native library hashes")
    {
        assert_eq!(
            packed_affine_adoption::file_sha256(prefix.join("lib").join(name)).unwrap(),
            record.as_str().unwrap()
        );
    }
    assert_eq!(
        freeze["mlx_commit"],
        "68cf2fddd8de5edd8ab3d926391772b2e2cedad8"
    );
    assert_eq!(
        freeze["mlx_c_commit"],
        "0726ca922fc902c4c61ef9c27d94132be418e945"
    );
    assert_eq!(
        freeze["binary_sha256"],
        packed_affine_adoption::file_sha256(env!("CARGO_BIN_EXE_adoption-probe")).unwrap()
    );
    if std::env::var("PULSAR_ADOPTION_PHASE").as_deref() == Ok("m1b") {
        performance::run(&campaign, &prefix, &freeze);
        return;
    }
    fs::create_dir(&root).expect("existing campaign must be reconciled, never rerun");
    // Pure injected controls are labelled independently of native fallback.
    assert!(packed_affine_adoption::registration(4096, 3, usize::MAX).is_err());
    assert!(packed_affine_adoption::adopted(true, true, true).is_err());
    create(
        &root.join("injected-controls.json"),
        &json!({"C-GEOMETRY":{"reached":true,"native_calls":0},"C-CALLBACK":{"reached":true,"injected":true,"native_fallback_claim":false}}),
    );
    // Intent is create-only, before dispatch. An unknown result is spent until
    // reconciled. This campaign root is carried forward across host handoffs.
    if continuation_raw != Some(false) {
        create(
            &campaign.join("raw-probe.intent.json"),
            &json!({"binary_sha256":freeze["binary_sha256"],"host_role":role,"attempt":1}),
        );
        let raw = child(
            &root,
            &prefix,
            "raw-probe",
            json!({"mode":"raw-length"}),
            60,
        );
        create(&root.join("raw-probe-summary.json"), &raw);
    }
    let fixtures = PathBuf::from(freeze["fixture_root"].as_str().unwrap());
    let manifest = packed_affine_adoption::cases::manifest(
        &fixtures,
        freeze["fixture_manifest_sha256"].as_str().unwrap(),
    )
    .unwrap();
    let portable = read(Path::new(freeze["portable_report"].as_str().unwrap()));
    assert_eq!(
        sha256_hex(&fs::read(freeze["portable_report"].as_str().unwrap()).unwrap()),
        freeze["portable_report_sha256"]
    );
    let identities: serde_json::Map<String, Value> = portable["cases"]
        .as_array()
        .unwrap()
        .iter()
        .map(|v| {
            (
                v["id"].as_str().unwrap().into(),
                v["receipt"]["metadata_snapshot_sha256"].clone(),
            )
        })
        .collect();
    let mut groups = manifest["small_sequences"].as_array().unwrap().clone();
    for c in manifest["cases"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|c| c["population_id"] == "representative-read-into-v1")
    {
        groups.push(json!([c["id"]]));
    }
    let mut rows = Vec::new();
    for (i, sequence) in groups.into_iter().enumerate() {
        let mut arms = Vec::new();
        for arm in ["copied", "adopted"] {
            let label = format!("group-{i}-{arm}");
            let config = json!({"mode":"diagnostic","arm":arm,"sequence":sequence,"fixture_root":fixtures,"fixture_manifest_sha256":freeze["fixture_manifest_sha256"],"metadata_identities":identities});
            arms.push(child(&root, &prefix, &label, config, 300));
            rows.push(json!({"label":label,"report":format!("{label}/run.json")}));
        }
        assert_eq!(
            arms[0]["outputs"].as_array().unwrap().len(),
            arms[1]["outputs"].as_array().unwrap().len()
        );
        for (a, b) in arms[0]["outputs"]
            .as_array()
            .unwrap()
            .iter()
            .zip(arms[1]["outputs"].as_array().unwrap())
        {
            assert_eq!(a["sha256"], b["sha256"], "copied/adopted output identity");
        }
    }
    let inherited = PathBuf::from(freeze["inherited_root"].as_str().unwrap());
    let m = read(&inherited.join("manifest.json"));
    let positives: Vec<_> = m["cases"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|c| c["expected"]["outcome"] == "accept")
        .collect();
    assert_eq!(positives.len(), 14);
    for (i, c) in positives.into_iter().enumerate() {
        let mut arms = Vec::new();
        for arm in ["copied", "adopted"] {
            let label = format!("inherited-{i}-{arm}");
            arms.push(child(
                &root,
                &prefix,
                &label,
                json!({"mode":"inherited","arm":arm,"case_id":c["id"],"inherited_root":inherited}),
                300,
            ));
            rows.push(json!({"label":label,"report":format!("{label}/run.json")}));
        }
        assert_eq!(arms[0]["output"]["sha256"], arms[1]["output"]["sha256"]);
    }
    // This is a mechanism receipt only. The independent reference wrapper and
    // original Slice 2C gates must accept every saved output before M1b release.
    let mut mechanism = json!({"contract_sha256":packed_affine_adoption::CONTRACT,"host_role":role,"fixture_manifest_sha256":freeze["fixture_manifest_sha256"],"source_commit":freeze["source_commit"],"source_tree":freeze["source_tree"],"binary_sha256":freeze["binary_sha256"],"reports":rows,"mechanism":"PASS","correctness":"PENDING_REFERENCE_GATES","M1b_released":false});
    if continuation_raw.is_some() {
        mechanism["continuation"] = continuation_call(&campaign, &freeze, "seal", &[]);
    }
    create(&root.join("mechanism.json"), &mechanism);
}
