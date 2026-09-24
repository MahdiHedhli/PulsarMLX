//! Host-only checks of the Slice 2B implementation (no MLX): the refusal
//! order against every frozen probe, the kernel-family transcription against
//! the manifest, the parent's report acceptance rules, the tamper detection of
//! the frozen population, and static source properties the contract requires.

use std::collections::BTreeSet;
use std::path::{Path, PathBuf};

use mlx_native_affine::dtype::Dtype;
use mlx_native_affine::family;
use mlx_native_affine::fixture::{
    load_case, parse_manifest, repo_root, validate_population, HostTensor,
};
use mlx_native_affine::frozen;
use mlx_native_affine::harness::{accept_report, ChildOutcome, ChildRun, ReportError};
use mlx_native_affine::refusal::{check_dq, check_qmm, DeviceFacts};
use serde_json::{json, Value};

fn manifest() -> mlx_native_affine::fixture::Manifest {
    let raw = std::fs::read(repo_root().join(frozen::MANIFEST_PATH)).unwrap();
    parse_manifest(&raw).unwrap()
}

fn t<'a>(c: &'a mlx_native_affine::fixture::LoadedCase, n: &str) -> &'a HostTensor {
    c.tensor(n).unwrap()
}

/// B6 (host part): every FX-REFUSE probe is refused with exactly its expected
/// id, and every accepted case passes every guard with the manifest geometry.
#[test]
fn refusal_order_matches_every_frozen_case() {
    let m = manifest();
    let dir = repo_root().join(frozen::FIXTURE_DIR);
    let (mut refused, mut accepted) = (0, 0);
    for spec in &m.cases {
        if spec.op != "quantized_matmul" && spec.op != "dequantize" {
            continue;
        }
        let c = load_case(&dir, spec).unwrap();
        let dev = if spec.param_str("context") == Some("cpu") {
            DeviceFacts {
                context_device_gpu: false,
                stream_device_gpu: false,
                ..DeviceFacts::GPU
            }
        } else {
            DeviceFacts::GPU
        };
        let bits = spec.param_u64("bits").unwrap() as u32;
        let gs = spec.param_u64("group_size").unwrap() as u32;
        let got = if spec.op == "quantized_matmul" {
            let transpose = spec.param_bool("transpose").unwrap_or(true);
            check_qmm(
                &dev,
                transpose,
                t(&c, "x"),
                t(&c, "w"),
                t(&c, "scales"),
                t(&c, "biases"),
                bits,
                gs,
            )
            .map(|g| {
                assert_eq!(
                    g.m_eff as u64,
                    spec.param_u64("M_eff").unwrap(),
                    "{}",
                    spec.id
                );
                assert_eq!(g.n as u64, spec.param_u64("N").unwrap(), "{}", spec.id);
                assert_eq!(g.k as u64, spec.param_u64("K").unwrap(), "{}", spec.id);
            })
        } else {
            check_dq(&dev, t(&c, "w"), t(&c, "scales"), t(&c, "biases"), bits, gs).map(|g| {
                assert_eq!(
                    g.rows as u64,
                    spec.param_u64("rows").unwrap(),
                    "{}",
                    spec.id
                );
                assert_eq!(g.k as u64, spec.param_u64("K").unwrap(), "{}", spec.id);
            })
        };
        if spec.is_refusal() {
            assert_eq!(
                got.err().map(|r| r.as_str()),
                spec.expected_refusal(),
                "{}",
                spec.id
            );
            refused += 1;
        } else {
            assert!(got.is_ok(), "{} refused {:?}", spec.id, got.err());
            accepted += 1;
        }
    }
    assert_eq!(refused, 37);
    assert_eq!(accepted, 239 + 77);
}

/// Every data-reachable refusal id is probed.
#[test]
fn every_data_reachable_refusal_id_is_probed() {
    let m = manifest();
    let probed: BTreeSet<&str> = m
        .cases
        .iter()
        .filter_map(|c| c.expected_refusal())
        .collect();
    let all: BTreeSet<&str> = frozen::REFUSAL_ORDER.iter().copied().collect();
    assert_eq!(probed, all);
}

/// family.rs reproduces the manifest's candidate families and exponents.
#[test]
fn family_transcription_matches_the_manifest() {
    let m = manifest();
    let mut n = 0;
    for spec in m
        .cases
        .iter()
        .filter(|c| c.op == "quantized_matmul" && !c.is_refusal())
    {
        let p = |k: &str| spec.param_u64(k).unwrap() as usize;
        let cands = family::candidates(
            p("M_eff"),
            p("N"),
            p("K"),
            p("group_size"),
            p("bits") as u32,
        );
        let want = spec.expected["families_0_31_2"].as_array().unwrap();
        assert_eq!(cands.len(), want.len(), "{}", spec.id);
        for (c, w) in cands.iter().zip(want) {
            assert_eq!(
                c.family.as_str(),
                w["family"].as_str().unwrap(),
                "{}",
                spec.id
            );
            assert_eq!(
                c.gamma_n as u64,
                w["gamma_n"].as_u64().unwrap(),
                "{}",
                spec.id
            );
            assert_eq!(
                c.split_k.map(|s| s as u64),
                w.get("split_k").and_then(Value::as_u64),
                "{}",
                spec.id
            );
        }
        assert_eq!(
            family::bound_exponent(
                p("M_eff"),
                p("N"),
                p("K"),
                p("group_size"),
                p("bits") as u32
            ) as u64,
            spec.manifest_gamma_n().unwrap()
        );
        // On every architecture class the derived family is one of the candidates.
        for arch in [
            "applegpu_g13s",
            "applegpu_g14s",
            "applegpu_g14d",
            "applegpu_g15s",
            "applegpu_g16d",
            "applegpu_g17p",
        ] {
            let a = family::parse_architecture(arch);
            let d = family::derive(
                p("M_eff"),
                p("N"),
                p("K"),
                p("group_size"),
                p("bits") as u32,
                &a,
            );
            assert!(
                cands.iter().any(|c| c.family == d.family),
                "{} {arch}",
                spec.id
            );
        }
        n += 1;
    }
    assert_eq!(n, 239);
}

fn ok_run() -> ChildRun {
    ChildRun {
        outcome: ChildOutcome::Exited(0),
        elapsed_ms: 1,
        stdout_path: PathBuf::new(),
        stderr_path: PathBuf::new(),
    }
}

fn write_report(dir: &Path, name: &str, v: &Value) -> PathBuf {
    std::fs::create_dir_all(dir).unwrap();
    let p = dir.join(name);
    std::fs::write(&p, serde_json::to_vec(v).unwrap()).unwrap();
    p
}

fn skeleton(ids: &[String]) -> Value {
    json!({
        "schema": frozen::CHILD_REPORT_SCHEMA,
        "contract_sha256": frozen::CONTRACT_SHA256,
        "manifest_sha256": frozen::MANIFEST_SHA256,
        "generator_sha256": frozen::GENERATOR_SHA256,
        "completed": true,
        "cases": ids.iter().map(|i| json!({"id": i})).collect::<Vec<_>>(),
    })
}

/// Parent failure conditions on the report (contract
/// frozen_population.parent_validation (3), (4)).
#[test]
fn report_acceptance_rules() {
    let m = manifest();
    let ids = m.ids();
    let dir = std::env::temp_dir().join(format!("f020-report-rules-{}", std::process::id()));
    let good = write_report(&dir, "good.json", &skeleton(&ids));
    assert!(accept_report(&ok_run(), &good, &m).is_ok());

    let mut missing = ids.clone();
    missing.pop();
    let p = write_report(&dir, "missing.json", &skeleton(&missing));
    assert!(matches!(
        accept_report(&ok_run(), &p, &m),
        Err(ReportError::CaseSet { .. })
    ));

    let mut dup = ids.clone();
    dup.push(ids[0].clone());
    let p = write_report(&dir, "dup.json", &skeleton(&dup));
    assert!(
        matches!(accept_report(&ok_run(), &p, &m), Err(ReportError::CaseSet { ref duplicated, .. }) if duplicated.len() == 1)
    );

    let mut extra = ids.clone();
    extra.push("not-a-case".into());
    let p = write_report(&dir, "extra.json", &skeleton(&extra));
    assert!(matches!(
        accept_report(&ok_run(), &p, &m),
        Err(ReportError::CaseSet { .. })
    ));

    let mut bad = skeleton(&ids);
    bad["manifest_sha256"] = json!("00");
    let p = write_report(&dir, "hash.json", &bad);
    assert!(matches!(
        accept_report(&ok_run(), &p, &m),
        Err(ReportError::HashEcho(_))
    ));

    let mut inc = skeleton(&ids);
    inc["completed"] = json!(false);
    let p = write_report(&dir, "inc.json", &inc);
    assert!(matches!(
        accept_report(&ok_run(), &p, &m),
        Err(ReportError::Incomplete(_))
    ));

    let p = dir.join("garbage.json");
    std::fs::write(&p, b"{ nope").unwrap();
    assert!(matches!(
        accept_report(&ok_run(), &p, &m),
        Err(ReportError::Unparsable(_))
    ));
    assert!(matches!(
        accept_report(&ok_run(), &dir.join("absent.json"), &m),
        Err(ReportError::Missing(_))
    ));

    for outcome in [
        ChildOutcome::Exited(3),
        ChildOutcome::Signaled(6),
        ChildOutcome::Timeout {
            elapsed_ms: 5,
            reaped_signal: Some(9),
        },
    ] {
        let run = ChildRun {
            outcome,
            ..ok_run()
        };
        assert!(matches!(
            accept_report(&run, &good, &m),
            Err(ReportError::ChildFailed(_))
        ));
    }
    let _ = std::fs::remove_dir_all(&dir);
}

fn copy_population(dst: &Path) {
    let src = repo_root();
    for rel in [
        frozen::CONTRACT_PATH,
        frozen::PLAN_PATH,
        frozen::SOURCE_PINS_PATH,
        frozen::GENERATOR_PATH,
        frozen::MANIFEST_PATH,
    ] {
        let to = dst.join(rel);
        std::fs::create_dir_all(to.parent().unwrap()).unwrap();
        std::fs::copy(src.join(rel), &to).unwrap();
    }
    let cases = dst.join(frozen::FIXTURE_DIR).join("cases");
    std::fs::create_dir_all(&cases).unwrap();
    for e in std::fs::read_dir(src.join(frozen::FIXTURE_DIR).join("cases")).unwrap() {
        let e = e.unwrap();
        std::fs::copy(e.path(), cases.join(e.file_name())).unwrap();
    }
}

/// B10 + tampered-population fault: any byte change in the manifest or in a
/// case file, or an extra file, fails validation before a child is run.
#[test]
fn tampered_population_is_refused() {
    let root = std::env::temp_dir().join(format!("f020-tamper-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&root);
    copy_population(&root);
    let (_, check) = validate_population(&root, None).expect("pristine copy validates");
    assert_eq!(check.case_count, frozen::CASE_COUNT);
    assert_eq!(check.case_file_count, frozen::CASE_FILE_COUNT);
    assert_eq!(check.cases_listing_sha256, frozen::CASES_LISTING_SHA256);

    let manifest = root.join(frozen::MANIFEST_PATH);
    let original = std::fs::read(&manifest).unwrap();
    let mut tampered = original.clone();
    let i = tampered.iter().position(|&b| b == b'7').unwrap();
    tampered[i] = b'8';
    std::fs::write(&manifest, &tampered).unwrap();
    assert!(validate_population(&root, None).is_err());
    std::fs::write(&manifest, &original).unwrap();

    let case = root
        .join(frozen::FIXTURE_DIR)
        .join("cases/qmm-b4-g64-bf16-quad64.bin");
    let original = std::fs::read(&case).unwrap();
    let mut tampered = original.clone();
    tampered[0] ^= 1;
    std::fs::write(&case, &tampered).unwrap();
    assert!(validate_population(&root, None).is_err());
    std::fs::write(&case, &original).unwrap();

    let extra = root.join(frozen::FIXTURE_DIR).join("cases/extra.bin");
    std::fs::write(&extra, b"x").unwrap();
    assert!(validate_population(&root, None).is_err());
    std::fs::remove_file(&extra).unwrap();

    std::fs::remove_file(
        root.join(frozen::FIXTURE_DIR)
            .join("cases/dq-b4-g32-f16-r1-k32.bin"),
    )
    .unwrap();
    assert!(validate_population(&root, None).is_err());
    let _ = std::fs::remove_dir_all(&root);
}

fn crate_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
}

fn rust_sources(dir: &Path, out: &mut Vec<PathBuf>) {
    for e in std::fs::read_dir(dir).unwrap() {
        let p = e.unwrap().path();
        if p.is_dir() {
            rust_sources(&p, out);
        } else if p
            .extension()
            .is_some_and(|x| x == "rs" || x == "c" || x == "mm" || x == "cpp")
        {
            out.push(p);
        }
    }
}

/// Coexistence policy: exactly one mlx_set_error_handler call site in this
/// crate (inside the Once), no workspace crate is linked into the child, and
/// no other workspace crate calls mlx_set_error_handler.
#[test]
fn single_error_handler_call_site_and_no_other_workspace_crate_in_the_child() {
    let mut files = Vec::new();
    rust_sources(&crate_dir().join("src"), &mut files);
    let mut calls = Vec::new();
    for f in &files {
        let text = std::fs::read_to_string(f).unwrap();
        for (i, line) in text.lines().enumerate() {
            let l = line.trim();
            if l.starts_with("//") || l.starts_with("pub fn mlx_set_error_handler") {
                continue;
            }
            if l.contains("mlx_set_error_handler(") {
                calls.push(format!(
                    "{}:{}",
                    f.file_name().unwrap().to_string_lossy(),
                    i + 1
                ));
            }
        }
    }
    assert_eq!(calls.len(), 1, "{calls:?}");
    let native = std::fs::read_to_string(crate_dir().join("src/bin/qualify/native.rs")).unwrap();
    let once = native.find("HANDLER_ONCE.call_once").unwrap();
    let call = native.find("ffi::mlx_set_error_handler(").unwrap();
    assert!(
        call > once && call - once < 400,
        "the call sits inside the Once"
    );

    // The child's dependency closure: [dependencies] has no path (workspace) crate.
    let cargo = std::fs::read_to_string(crate_dir().join("Cargo.toml")).unwrap();
    let deps = cargo
        .split("[dependencies]")
        .nth(1)
        .unwrap()
        .split("\n[")
        .next()
        .unwrap();
    assert!(
        !deps.contains("path"),
        "a workspace crate would be linked into the child: {deps}"
    );
    assert!(deps.contains("serde_json") && deps.contains("sha2") && deps.contains("libc"));

    // No other workspace crate calls it (crates/stream included).
    let mut others = Vec::new();
    for e in std::fs::read_dir(crate_dir().parent().unwrap()).unwrap() {
        let p = e.unwrap().path();
        if p == crate_dir() || !p.join("src").is_dir() {
            continue;
        }
        let mut fs = Vec::new();
        rust_sources(&p.join("src"), &mut fs);
        for f in fs {
            if std::fs::read_to_string(&f)
                .unwrap_or_default()
                .contains("mlx_set_error_handler")
            {
                others.push(f);
            }
        }
    }
    assert!(others.is_empty(), "{others:?}");
}

/// The public quantized matmul has no transpose parameter; transpose=false is
/// only reachable through the test-only entry point.
#[test]
fn public_quantized_matmul_has_no_transpose_parameter() {
    let bridge = std::fs::read_to_string(crate_dir().join("src/bin/qualify/bridge.rs")).unwrap();
    let start = bridge.find("pub fn quantized_matmul(").unwrap();
    let sig = &bridge[start..start + bridge[start..].find(") ->").unwrap()];
    assert!(!sig.contains("transpose"), "{sig}");
    assert_eq!(
        bridge
            .matches("quantized_matmul_transpose_test_only(")
            .count(),
        1
    );
    // The packed weight is never dequantized on the quantized-matmul path.
    let qmm = &bridge[bridge.find("fn qmm_inner(").unwrap()..];
    assert!(
        !qmm.contains("dequantize"),
        "quantized matmul must not dequantize the weight"
    );
    // The library never links or names MLX-C.
    let mut lib = Vec::new();
    rust_sources(&crate_dir().join("src"), &mut lib);
    for f in lib
        .iter()
        .filter(|f| !f.to_string_lossy().contains("/bin/") && f.extension().unwrap() == "rs")
    {
        let text = std::fs::read_to_string(f).unwrap();
        assert!(!text.contains("extern \"C\""), "{}", f.display());
    }
}

/// The frozen constants in the library equal the contract's.
#[test]
fn frozen_constants_equal_the_contract() {
    let root = repo_root();
    let c: Value =
        serde_json::from_slice(&std::fs::read(root.join(frozen::CONTRACT_PATH)).unwrap()).unwrap();
    assert_eq!(c["schema"], frozen::CONTRACT_SCHEMA);
    let order: Vec<&str> = c["refusals"]["order"]
        .as_array()
        .unwrap()
        .iter()
        .map(|r| r["id"].as_str().unwrap())
        .collect();
    assert_eq!(order, frozen::REFUSAL_ORDER);
    let wd = c["error_handling"]["child_process"]["watchdog"]
        .as_str()
        .unwrap();
    assert!(wd.contains("CHILD_TIMEOUT_SECONDS = 1800"));
    assert_eq!(frozen::CHILD_TIMEOUT_SECONDS, 1800);
    let _ = Dtype::U32;
}
