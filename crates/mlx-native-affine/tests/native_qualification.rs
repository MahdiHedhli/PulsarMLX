//! The Slice 2B native qualification (parent side) and the child-process
//! failure-path tests.
//!
//! `native_qualification_of_the_frozen_population` is the gate:
//!
//! 1. validate the frozen population (contract, plan, pins, generator,
//!    manifest, every case file, the listing hash, generator `--check`);
//! 2. run the `qualify` child once, with the fixed environment, under the
//!    frozen 1800 s watchdog (SIGKILL + reap + TIMEOUT, no retry);
//! 3. accept its report only under the parent failure conditions;
//! 4. compute the Rust binary64 R1 (`mlx_affine::reference_qmm`) and the exact
//!    Python R1 (`scripts/research/mlx_affine_qmm_reference_v1.py`);
//! 5. decide every gate with the contract's frozen algorithm: G-IMPORT,
//!    G-CAST, G-DQ-CODES, G-DQ-RUST, G-QMM-RUST and N-QMM-ZERO here, and
//!    G-QMM-EXACT, G-DQ-EXACT, G-R1-SELF-QMM, G-R1-SELF-DQ with Fraction in
//!    `acceptance/exact_gates_v1.py`; a case carrying both references passes
//!    only if both decisions pass;
//! 6. validate the population again and write the summary.
//!
//! Environment: `MLX_C_PREFIX` names the pinned native prefix (the same the
//! build used). `PULSAR_F020_QUALIFICATION_OUT` chooses the output directory
//! (default `target/f020-slice2b`), `PULSAR_F020_HOST_LABEL` labels the host,
//! `PULSAR_F020_PYTHON` names the interpreter (default `python3` on PATH).
//! Without the native build these tests fail when
//! `PULSAR_REQUIRE_NATIVE_MLX=1` and are reported as not run otherwise.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::time::Duration;

use mlx_affine::reference_qmm::{dq_reference, qmm_reference, QmmMetadata};
use mlx_native_affine::dtype::{Dtype, FloatFormat};
use mlx_native_affine::fixture::{
    load_case, repo_root, sha256_hex, validate_population, CaseSpec, HostTensor, Manifest,
};
use mlx_native_affine::frozen;
use mlx_native_affine::gates::{
    g_cast, g_dq_codes, g_dq_rust, g_qmm_rust, is_zero_row, qmm_zero_violations,
};
use mlx_native_affine::harness::{
    accept_report, child_env, frozen_timeout, run_child, ChildOutcome, ReportError,
};
use mlx_native_affine::refusal::code_at;
use serde_json::{json, Value};

fn native_built() -> bool {
    if cfg!(pulsar_native_mlx) {
        return true;
    }
    if std::env::var("PULSAR_REQUIRE_NATIVE_MLX").as_deref() == Ok("1") {
        panic!("PULSAR_REQUIRE_NATIVE_MLX=1 but the qualify child was built without the pinned native prefix: a skipped suite is a failure");
    }
    eprintln!("NOT RUN: the qualify child was built without the pinned native MLX prefix");
    false
}

fn native_prefix() -> PathBuf {
    let p = std::env::var("MLX_C_PREFIX").expect("MLX_C_PREFIX names the pinned native prefix");
    PathBuf::from(p)
        .canonicalize()
        .expect("native prefix exists")
}

fn out_root() -> PathBuf {
    let p = std::env::var("PULSAR_F020_QUALIFICATION_OUT")
        .map(PathBuf::from)
        .unwrap_or_else(|_| repo_root().join("target/f020-slice2b"));
    std::fs::create_dir_all(&p).unwrap();
    p.canonicalize().unwrap()
}

fn fresh(dir: &Path) -> PathBuf {
    let _ = std::fs::remove_dir_all(dir);
    std::fs::create_dir_all(dir).unwrap();
    dir.to_path_buf()
}

fn python() -> PathBuf {
    let name = std::env::var("PULSAR_F020_PYTHON").unwrap_or_else(|_| "python3".into());
    let p = PathBuf::from(&name);
    if p.is_absolute() {
        return p;
    }
    for dir in std::env::split_paths(&std::env::var_os("PATH").unwrap_or_default()) {
        let c = dir.join(&name);
        if c.is_file() {
            return c;
        }
    }
    panic!("interpreter {name} not found on PATH (a missing interpreter is a failure)");
}

fn child() -> PathBuf {
    PathBuf::from(env!("CARGO_BIN_EXE_qualify"))
}

fn git(args: &[&str]) -> String {
    std::process::Command::new("git")
        .args(args)
        .current_dir(repo_root())
        .output()
        .ok()
        .filter(|o| o.status.success())
        .map(|o| String::from_utf8_lossy(&o.stdout).trim().to_string())
        .unwrap_or_default()
}

// ------------------------------------------------------------ R1 (Rust) --

fn words(t: &HostTensor) -> Vec<u32> {
    t.words_u32()
}

fn meta<'a>(
    dtype: Dtype,
    sh: &'a [u16],
    bh: &'a [u16],
    sw: &'a [u32],
    bw: &'a [u32],
) -> QmmMetadata<'a> {
    match dtype {
        Dtype::F16 => QmmMetadata::F16 {
            scales: sh,
            biases: bh,
        },
        Dtype::BF16 => QmmMetadata::Bf16 {
            scales: sh,
            biases: bh,
        },
        Dtype::F32 => QmmMetadata::F32 {
            scales: sw,
            biases: bw,
        },
        Dtype::U32 => panic!("U32 metadata"),
    }
}

struct RustR1 {
    /// OP-QMM: (y1, phi_hat); OP-DQ: (w_hat, p_hat).
    first: Vec<f64>,
    second: Vec<f64>,
}

fn rust_r1(dir: &Path, spec: &CaseSpec) -> RustR1 {
    let c = load_case(dir, spec).unwrap();
    let t = |n: &str| c.tensor(n).unwrap();
    let (s, b) = (t("scales"), t("biases"));
    let (sh, bh) = if s.dtype == Dtype::F32 {
        (vec![], vec![])
    } else {
        (s.halves_u16(), b.halves_u16())
    };
    let (sw, bw) = if s.dtype == Dtype::F32 {
        (s.words_u32(), b.words_u32())
    } else {
        (vec![], vec![])
    };
    let m = meta(s.dtype, &sh, &bh, &sw, &bw);
    let p = |k: &str| spec.param_u64(k).unwrap() as usize;
    if spec.op == "quantized_matmul" {
        let r = qmm_reference(
            &words(t("x")),
            &words(t("w")),
            m,
            p("M_eff"),
            p("N"),
            p("K"),
            p("bits") as u32,
            p("group_size"),
        )
        .unwrap();
        RustR1 {
            first: r.y,
            second: r.phi,
        }
    } else {
        let r = dq_reference(
            &words(t("w")),
            m,
            p("rows"),
            p("K"),
            p("bits") as u32,
            p("group_size"),
        )
        .unwrap();
        RustR1 {
            first: r.w,
            second: r.p,
        }
    }
}

fn hexes(v: &[f64]) -> Vec<String> {
    v.iter().map(|x| format!("{:016x}", x.to_bits())).collect()
}

// ------------------------------------------------------------ decisions --

fn output_bytes(out_dir: &Path, rec: &Value) -> Vec<u8> {
    let o = &rec["output"];
    let data = std::fs::read(out_dir.join(o["file"].as_str().unwrap())).unwrap();
    assert_eq!(
        sha256_hex(&data),
        o["sha256"].as_str().unwrap(),
        "{}",
        rec["id"]
    );
    data
}

fn u32s(b: &[u8]) -> Vec<u32> {
    b.chunks_exact(4)
        .map(|c| u32::from_le_bytes(c.try_into().unwrap()))
        .collect()
}
fn u16s(b: &[u8]) -> Vec<u32> {
    b.chunks_exact(2)
        .map(|c| u16::from_le_bytes(c.try_into().unwrap()) as u32)
        .collect()
}

#[derive(Default)]
struct Worst {
    rust: f64,
    exact: f64,
    cases: usize,
}

fn structural_ok(rec: &Value) -> bool {
    rec["structural"]
        .as_object()
        .is_some_and(|m| !m.is_empty() && m.values().all(|v| v.as_bool() == Some(true)))
}

#[test]
fn native_qualification_of_the_frozen_population() {
    if !native_built() {
        return;
    }
    let root = repo_root();
    let out = fresh(&out_root().join("qualification"));
    let py = python();
    let py_s = py.to_string_lossy().into_owned();
    let host = std::env::var("PULSAR_F020_HOST_LABEL").unwrap_or_else(|_| "unlabelled".into());
    let candidate = git(&["rev-parse", "HEAD"]);
    let dirty = !git(&["status", "--porcelain", "--untracked-files=no"]).is_empty();

    // 1. Frozen population before the run (B10).
    let (manifest, pre) = validate_population(&root, Some(&py_s))
        .expect("frozen population validates before the run");

    // 2. The child, once, under the frozen watchdog.
    let prefix = native_prefix();
    let tmp = fresh(&out.join("tmp"));
    let child_out = fresh(&out.join("child"));
    let run = run_child(
        &child(),
        &[
            "--repo".into(),
            root.to_string_lossy().into(),
            "--out".into(),
            child_out.to_string_lossy().into(),
        ],
        &child_env(&prefix, &tmp),
        frozen_timeout(),
        &out,
        "child",
    );
    let report_path = child_out.join("report.json");
    let report = match accept_report(&run, &report_path, &manifest) {
        Ok(r) => r,
        Err(e) => {
            let summary = json!({"schema": frozen::PARENT_SUMMARY_SCHEMA, "result": "FAIL", "host_label": host,
                                 "candidate_commit": candidate, "child_outcome": run.outcome.describe(), "report_error": e.to_string()});
            std::fs::write(
                out.join("summary.json"),
                serde_json::to_vec_pretty(&summary).unwrap(),
            )
            .unwrap();
            panic!(
                "child report not accepted: {e} ({})",
                run.outcome.describe()
            );
        }
    };
    let report_sha = sha256_hex(&std::fs::read(&report_path).unwrap());
    let records: BTreeMap<String, Value> = report["cases"]
        .as_array()
        .unwrap()
        .iter()
        .map(|r| (r["id"].as_str().unwrap().to_string(), r.clone()))
        .collect();

    let mut failures: Vec<String> = Vec::new();
    let mut fail = |msg: String| failures.push(msg);

    // Child-level evidence: E1-E4, E6 and the handler.
    let prov = &report["provenance"];
    if prov["mlx_version"] != frozen::MLX_VERSION {
        fail(format!("mlx_version {}", prov["mlx_version"]));
    }
    if prov["environment"]["MLX_ENABLE_TF32"] != "0"
        || prov["environment"]["DYLD_LIBRARY_PATH"] != "<native-prefix>/lib"
    {
        fail("child environment".into());
    }
    for key in ["libmlx", "libmlxc", "metallib"] {
        if !prov[key]["relative_path"]
            .as_str()
            .is_some_and(|p| p.starts_with("lib/"))
        {
            fail(format!("{key} not inside the native prefix"));
        }
    }
    for c in ["canary_start", "canary_end"] {
        if report[c]["pass"] != true {
            fail(format!("E4 {c} failed: {}", report[c]));
        }
    }
    if report["error_handler"]["installs"] != 1 {
        fail("error handler installed other than once".into());
    }
    let h = &report["handles"];
    if h["live_array_handles_after_context_drop"] != 0
        || h["double_free_attempts"] != 0
        || h["live_arrays_in_context_at_drop"] != 0
    {
        fail(format!("handle census {h}"));
    }

    // 3. R1 (Rust binary64) on every case that carries it; then the exact
    // Python R1 (with its own self-check) and the exact gates.
    let fixture_dir = root.join(frozen::FIXTURE_DIR);
    let mut r1: BTreeMap<String, RustR1> = BTreeMap::new();
    let mut rust_doc = serde_json::Map::new();
    for spec in manifest
        .cases
        .iter()
        .filter(|c| c.has_reference("rust_binary64_r1"))
    {
        let r = rust_r1(&fixture_dir, spec);
        let entry = if spec.op == "quantized_matmul" {
            json!({"op": spec.op, "y": hexes(&r.first), "phi": hexes(&r.second)})
        } else {
            json!({"op": spec.op, "w": hexes(&r.first), "p": hexes(&r.second)})
        };
        rust_doc.insert(spec.id.clone(), entry);
        r1.insert(spec.id.clone(), r);
    }
    let rust_path = out.join("r1-rust.json");
    std::fs::write(
        &rust_path,
        serde_json::to_vec(
            &json!({"schema": "pulsarmlx.f020.r1-rust-binary64/1.0.0", "cases": rust_doc}),
        )
        .unwrap(),
    )
    .unwrap();
    let r1_exact = out.join("r1-exact.json");
    let py_env = vec![
        ("PATH".to_string(), "/usr/bin:/bin".to_string()),
        ("HOME".to_string(), tmp.to_string_lossy().into_owned()),
    ];
    let r1_run = run_child(
        &py,
        &[
            "-I".into(),
            "-B".into(),
            root.join("scripts/research/mlx_affine_qmm_reference_v1.py")
                .to_string_lossy()
                .into(),
            "--manifest".into(),
            root.join(frozen::MANIFEST_PATH).to_string_lossy().into(),
            "--cases-dir".into(),
            fixture_dir.to_string_lossy().into(),
            "--all".into(),
            "--out".into(),
            r1_exact.to_string_lossy().into(),
            "--rust-r1".into(),
            rust_path.to_string_lossy().into(),
        ],
        &py_env,
        frozen_timeout(),
        &out,
        "r1-exact",
    );
    if r1_run.outcome != ChildOutcome::Exited(0) {
        fail(format!(
            "exact R1 / N-R1-SELF(-DQ) run: {}",
            r1_run.outcome.describe()
        ));
    }
    let r1_doc: Value =
        serde_json::from_slice(&std::fs::read(&r1_exact).expect("exact R1 output")).unwrap();
    let r1_self = r1_doc["r1_self_check"].clone();
    if r1_self["result"] != "PASS" {
        fail(format!(
            "R1 self-check (reference owner's decision) {}",
            r1_self["result"]
        ));
    }
    let gates_path = out.join("exact-gates.json");
    let g_run = run_child(
        &py,
        &[
            "-I".into(),
            "-B".into(),
            root.join("crates/mlx-native-affine/acceptance/exact_gates_v1.py")
                .to_string_lossy()
                .into(),
            "--manifest".into(),
            root.join(frozen::MANIFEST_PATH).to_string_lossy().into(),
            "--r1-exact".into(),
            r1_exact.to_string_lossy().into(),
            "--rust-r1".into(),
            rust_path.to_string_lossy().into(),
            "--r3-report".into(),
            report_path.to_string_lossy().into(),
            "--r3-dir".into(),
            child_out.to_string_lossy().into(),
            "--out".into(),
            gates_path.to_string_lossy().into(),
        ],
        &py_env,
        frozen_timeout(),
        &out,
        "exact-gates",
    );
    if g_run.outcome != ChildOutcome::Exited(0) {
        fail(format!("exact gates run: {}", g_run.outcome.describe()));
    }
    let exact: Value =
        serde_json::from_slice(&std::fs::read(&gates_path).expect("exact gates output")).unwrap();

    // 4. Per-case decisions.
    let mut per_case = Vec::new();
    let mut worst: BTreeMap<String, Worst> = BTreeMap::new();
    let mut counts: BTreeMap<String, (usize, usize)> = BTreeMap::new();
    let mut tally = |gate: &str, pass: bool| {
        let e = counts.entry(gate.to_string()).or_default();
        e.0 += 1;
        e.1 += pass as usize;
    };
    let mut refusals = Vec::new();
    let mut cast_outcomes = serde_json::Map::new();
    for spec in &manifest.cases {
        let rec = &records[&spec.id];
        let mut gates = serde_json::Map::new();
        let mut case_pass = true;
        let executed = rec["outcome"] == "executed";
        if spec.is_refusal() {
            let calls = &rec["stats"];
            let pass = rec["outcome"] == "refused"
                && rec["refusal_id"].as_str() == spec.expected_refusal()
                && calls["numerical_calls_before_decision"] == 0
                && calls["imports_before_decision"] == 0;
            tally("B6-REFUSAL", pass);
            refusals.push(json!({"id": spec.id, "expected": spec.expected_refusal(), "got": rec["refusal_id"],
                                 "numerical_calls_before_decision": calls["numerical_calls_before_decision"],
                                 "imports_before_decision": calls["imports_before_decision"], "pass": pass}));
            gates.insert("B6-REFUSAL".into(), json!(pass));
            case_pass &= pass;
        } else if !executed {
            case_pass = false;
            gates.insert(
                "EXECUTION".into(),
                json!({"pass": false, "outcome": rec["outcome"], "error": rec["error"]}),
            );
        } else {
            let st = structural_ok(rec);
            gates.insert("SHAPE-DTYPE".into(), json!(st));
            tally("SHAPE-DTYPE", st);
            case_pass &= st;
            let data = output_bytes(&child_out, rec);
            let c = load_case(&fixture_dir, spec).unwrap();
            match spec.op.as_str() {
                "import_u32" | "import_meta" => {
                    let name = if spec.op == "import_u32" {
                        "w"
                    } else {
                        "values"
                    };
                    let pass = data == c.tensor(name).unwrap().bytes;
                    tally("G-IMPORT", pass);
                    gates.insert("G-IMPORT".into(), json!(pass));
                    case_pass &= pass;
                }
                "astype_f32" => {
                    let input = manifest
                        .case(spec.param_str("input_case").unwrap())
                        .unwrap();
                    let ic = load_case(&fixture_dir, input).unwrap();
                    let t = ic.tensor("values").unwrap();
                    let f = t.dtype.float().unwrap();
                    let o = g_cast(f, &t.halves_u16(), &u32s(&data));
                    let pass = o.gated_mismatches == 0 && o.gated_patterns > 0;
                    tally("G-CAST", pass);
                    let rec_o = json!({"gated_patterns": o.gated_patterns, "gated_mismatches": o.gated_mismatches,
                        "recorded_only": {"subnormal": o.recorded_subnormal, "subnormal_bit_equal": o.recorded_subnormal_bit_equal,
                                          "subnormal_flushed_to_signed_zero": o.recorded_subnormal_flushed_to_signed_zero,
                                          "infinite": o.recorded_infinite, "infinite_bit_equal": o.recorded_infinite_bit_equal,
                                          "nan": o.recorded_nan, "nan_bit_equal": o.recorded_nan_bit_equal, "nan_is_nan": o.recorded_nan_is_nan}});
                    cast_outcomes.insert(spec.id.clone(), rec_o.clone());
                    gates.insert("G-CAST".into(), json!({"pass": pass, "detail": rec_o}));
                    case_pass &= pass;
                }
                "dequantize" => {
                    let s = c.tensor("scales").unwrap();
                    let f = s.dtype.float().unwrap();
                    let out_bits = if f == FloatFormat::F32 {
                        u32s(&data)
                    } else {
                        u16s(&data)
                    };
                    if spec.has_reference("codes_exact") {
                        let w = c.tensor("w").unwrap();
                        let (rows, k, bits) = (
                            spec.param_u64("rows").unwrap() as usize,
                            spec.param_u64("K").unwrap() as usize,
                            spec.param_u64("bits").unwrap() as u32,
                        );
                        let words = w.words_u32();
                        let codes: Vec<u32> = (0..rows)
                            .flat_map(|r| (0..k).map(move |j| (r, j)))
                            .map(|(r, j)| code_at(&words, w.shape[1], bits, r, j))
                            .collect();
                        let pass =
                            out_bits.len() == codes.len() && g_dq_codes(f, &codes, &out_bits) == 0;
                        tally("G-DQ-CODES", pass);
                        gates.insert("G-DQ-CODES".into(), json!(pass));
                        case_pass &= pass;
                    }
                    if let Some(r) = r1.get(&spec.id) {
                        let mut ok = out_bits.len() == r.first.len();
                        let mut wr = 0f64;
                        let mut failed = 0usize;
                        if ok {
                            for ((&o, &w_hat), &p_hat) in
                                out_bits.iter().zip(&r.first).zip(&r.second)
                            {
                                let (pass, d, b) = g_dq_rust(f, o, p_hat, w_hat);
                                if !pass {
                                    failed += 1;
                                }
                                wr = wr.max(if b > 0.0 {
                                    d / b
                                } else if d == 0.0 {
                                    0.0
                                } else {
                                    f64::INFINITY
                                });
                            }
                            ok = failed == 0;
                        }
                        tally("G-DQ-RUST", ok);
                        gates.insert("G-DQ-RUST".into(), json!({"pass": ok, "failed_elements": failed, "worst_ratio_d_hi_over_B_lo": wr}));
                        case_pass &= ok;
                        let e = worst.entry(format!("dequantize/{}", f.name())).or_default();
                        e.rust = e.rust.max(wr);
                        e.cases += 1;
                    }
                    if spec.has_reference("python_exact_r1") {
                        let d = &exact["cases"][&spec.id];
                        for g in ["G-DQ-EXACT", "G-R1-SELF-DQ"] {
                            let pass = d[g]["pass"] == true;
                            tally(g, pass);
                            gates.insert(g.into(), d[g].clone());
                            case_pass &= pass;
                        }
                        gates.insert("H-DQ-SET (recorded)".into(), d["H-DQ-SET"].clone());
                        let e = worst.entry(format!("dequantize/{}", f.name())).or_default();
                        e.exact = e.exact.max(
                            d["G-DQ-EXACT"]["worst_ratio"]
                                .as_f64()
                                .unwrap_or(f64::INFINITY),
                        );
                    }
                }
                "quantized_matmul" => {
                    let y3: Vec<f32> = u32s(&data).into_iter().map(f32::from_bits).collect();
                    let k = spec.param_u64("K").unwrap() as usize;
                    let n_gamma = spec.manifest_gamma_n().unwrap() as usize;
                    let fam = rec["kernel"]["derived_family"]
                        .as_str()
                        .unwrap_or("?")
                        .to_string();
                    if rec["kernel"]["bound_gamma_n"].as_u64() != Some(n_gamma as u64) {
                        fail(format!(
                            "{}: family.rs exponent differs from manifest",
                            spec.id
                        ));
                    }
                    let r = &r1[&spec.id];
                    let mut failed = 0usize;
                    let mut wr = 0f64;
                    let ok_len = y3.len() == r.first.len();
                    if ok_len {
                        for ((&y, &y1), &ph) in y3.iter().zip(&r.first).zip(&r.second) {
                            let (pass, d, b) = g_qmm_rust(y, y1, ph, k, n_gamma);
                            if !pass {
                                failed += 1;
                            }
                            wr = wr.max(if b > 0.0 {
                                d / b
                            } else if d == 0.0 {
                                0.0
                            } else {
                                f64::INFINITY
                            });
                        }
                    }
                    let ok = ok_len && failed == 0;
                    tally("G-QMM-RUST", ok);
                    gates.insert("G-QMM-RUST".into(), json!({"pass": ok, "gamma_n": n_gamma, "failed_elements": failed, "worst_ratio_d_hi_over_B_lo": wr}));
                    case_pass &= ok;
                    let e = worst.entry(format!("quantized_matmul/{fam}")).or_default();
                    e.rust = e.rust.max(wr);
                    e.cases += 1;
                    if spec.has_reference("python_exact_r1") {
                        let d = &exact["cases"][&spec.id];
                        for g in ["G-QMM-EXACT", "G-R1-SELF-QMM"] {
                            let pass = d[g]["pass"] == true;
                            tally(g, pass);
                            gates.insert(g.into(), d[g].clone());
                            case_pass &= pass;
                        }
                        e.exact = e.exact.max(
                            d["G-QMM-EXACT"]["worst_ratio"]
                                .as_f64()
                                .unwrap_or(f64::INFINITY),
                        );
                    }
                    // N-QMM-ZERO: gated where the case marks it, recorded elsewhere.
                    let marked = spec.expected["checks"].as_array().is_some_and(|a| {
                        a.iter()
                            .any(|c| c.as_str().is_some_and(|s| s.starts_with("N-QMM-ZERO")))
                    });
                    let x = c.tensor("x").unwrap().words_u32();
                    let nn = spec.param_u64("N").unwrap() as usize;
                    let m = spec.param_u64("M_eff").unwrap() as usize;
                    let mut zero_rows = 0;
                    let mut zero_viol = 0;
                    for row in 0..m {
                        if is_zero_row(&x[row * k..(row + 1) * k]) {
                            zero_rows += 1;
                            zero_viol += qmm_zero_violations(&y3[row * nn..(row + 1) * nn]);
                        }
                    }
                    if marked {
                        let pass = zero_rows >= 1 && zero_viol == 0;
                        tally("N-QMM-ZERO", pass);
                        gates.insert(
                            "N-QMM-ZERO".into(),
                            json!({"pass": pass, "zero_rows": zero_rows}),
                        );
                        case_pass &= pass;
                    } else if zero_rows > 0 {
                        gates.insert(
                            "N-QMM-ZERO (recorded)".into(),
                            json!({"zero_rows": zero_rows, "violations": zero_viol}),
                        );
                    }
                }
                other => panic!("unknown op {other}"),
            }
        }
        if !case_pass {
            fail(format!(
                "case {} failed: {}",
                spec.id,
                Value::Object(gates.clone())
            ));
        }
        per_case.push(json!({
            "id": spec.id, "op": spec.op, "family": spec.family, "references": spec.references,
            "production_relevant": spec.params.get("production_relevant").cloned().unwrap_or(json!(false)),
            "outcome": rec["outcome"], "kernel": rec.get("kernel").cloned().unwrap_or(Value::Null),
            "gates": gates, "pass": case_pass,
        }));
    }
    // Every expected gate count, exactly (case accounting).
    let expect = [
        ("B6-REFUSAL", 37),
        ("G-IMPORT", 8),
        ("G-CAST", 2),
        ("G-DQ-CODES", 18),
        ("G-DQ-RUST", 59),
        ("G-DQ-EXACT", 59),
        ("G-R1-SELF-DQ", 59),
        ("G-QMM-RUST", 239),
        ("G-QMM-EXACT", 237),
        ("G-R1-SELF-QMM", 237),
        ("N-QMM-ZERO", 1),
        ("SHAPE-DTYPE", 326),
    ];
    for (g, n) in expect {
        let got = counts.get(g).copied().unwrap_or((0, 0));
        if got != (n, n) {
            fail(format!("{g}: {}/{} passed, expected {n}/{n}", got.1, got.0));
        }
    }

    // 5. Frozen population after the run (B10).
    let post = validate_population(&root, Some(&py_s));
    if post.is_err() {
        fail(format!(
            "population after the run: {:?}",
            post.as_ref().err()
        ));
    }

    let result = if failures.is_empty() { "PASS" } else { "FAIL" };
    let summary = json!({
        "schema": frozen::PARENT_SUMMARY_SCHEMA,
        "result": result,
        "host_label": host,
        "candidate_commit": candidate,
        "worktree_dirty": dirty,
        "frozen": {"contract_sha256": pre.contract_sha256, "plan_sha256": pre.plan_sha256, "source_pins_sha256": pre.source_pins_sha256,
                   "generator_sha256": pre.generator_sha256, "manifest_sha256": pre.manifest_sha256,
                   "cases_listing_sha256": pre.cases_listing_sha256, "case_count": pre.case_count, "case_file_count": pre.case_file_count,
                   "generator_check_before": pre.generator_check, "population_valid_after": post.is_ok()},
        "child": {"outcome": run.outcome.describe(), "elapsed_ms": run.elapsed_ms, "timeout_seconds": frozen::CHILD_TIMEOUT_SECONDS,
                  "report_sha256": report_sha, "abi_values": report["abi_values"], "error_handler": report["error_handler"],
                  "handles": report["handles"], "call_counts": report["call_counts"],
                  "canary_start": report["canary_start"], "canary_end": report["canary_end"]},
        "provenance": prov,
        "gate_counts": counts.iter().map(|(g, (n, p))| (g.clone(), json!({"cases": n, "passed": p}))).collect::<serde_json::Map<_, _>>(),
        "worst_ratio_by_family": worst.iter().map(|(f, w)| (f.clone(), json!({"cases": w.cases, "rust_d_hi_over_B_lo": w.rust, "exact_distance_over_bound": w.exact}))).collect::<serde_json::Map<_, _>>(),
        "r1_self_check_reference_owner": r1_self,
        "exact_gates_summary": exact["summary"],
        "cast_recorded": cast_outcomes,
        "refusals": refusals,
        "cases": per_case,
        "failures": failures,
        "artifacts": {"child_report": "child/report.json", "exact_r1": "r1-exact.json", "rust_r1": "r1-rust.json", "exact_gates": "exact-gates.json"},
    });
    std::fs::write(
        out.join("summary.json"),
        serde_json::to_vec_pretty(&summary).unwrap(),
    )
    .unwrap();
    println!(
        "F020 Slice 2B qualification: {result} (summary {})",
        out.join("summary.json").display()
    );
    println!("{}", serde_json::to_string(&json!({"result": result, "gate_counts": summary["gate_counts"], "worst_ratio_by_family": summary["worst_ratio_by_family"], "architecture": prov["architecture"]})).unwrap());
    assert!(
        failures.is_empty(),
        "qualification FAILED:\n{}",
        failures.join("\n")
    );
}

// ------------------------------------------------ child failure paths --

fn fault_run(
    kind: &str,
    timeout: Duration,
) -> (
    mlx_native_affine::harness::ChildRun,
    Result<Value, ReportError>,
) {
    let root = repo_root();
    let out = fresh(&out_root().join(format!("faults/{kind}")));
    let tmp = fresh(&out.join("tmp"));
    let child_out = out.join("child");
    let run = run_child(
        &child(),
        &[
            "--repo".into(),
            root.to_string_lossy().into(),
            "--out".into(),
            child_out.to_string_lossy().into(),
            "--test-fault".into(),
            kind.into(),
        ],
        &child_env(&native_prefix(), &tmp),
        timeout,
        &out,
        "child",
    );
    let manifest = manifest_only();
    let accepted = accept_report(&run, &child_out.join("report.json"), &manifest);
    (run, accepted)
}

fn manifest_only() -> Manifest {
    mlx_native_affine::fixture::parse_manifest(
        &std::fs::read(repo_root().join(frozen::MANIFEST_PATH)).unwrap(),
    )
    .unwrap()
}

/// B9: a test-only child abort and hang are reported by the parent as
/// failures with signal/exit status and TIMEOUT; a nonzero exit, a missing
/// report and an unparsable report are failures too. No retry happens.
#[test]
fn child_failure_paths_are_reported_as_failures() {
    if !native_built() {
        return;
    }
    let (run, acc) = fault_run("abort", Duration::from_secs(120));
    assert_eq!(run.outcome, ChildOutcome::Signaled(libc_sigabrt()), "abort");
    assert!(matches!(acc, Err(ReportError::ChildFailed(_))));

    // The frozen watchdog is 1800 s; the mechanism is exercised with a short
    // limit so the test finishes (SIGKILL, reap, TIMEOUT, no retry).
    let (run, acc) = fault_run("hang", Duration::from_secs(5));
    assert!(
        matches!(
            run.outcome,
            ChildOutcome::Timeout {
                reaped_signal: Some(9),
                ..
            }
        ),
        "{:?}",
        run.outcome
    );
    assert!(matches!(acc, Err(ReportError::ChildFailed(ref m)) if m.starts_with("TIMEOUT")));

    let (run, acc) = fault_run("exit", Duration::from_secs(120));
    assert_eq!(run.outcome, ChildOutcome::Exited(7));
    assert!(matches!(acc, Err(ReportError::ChildFailed(_))));

    let (run, acc) = fault_run("no-report", Duration::from_secs(120));
    assert_eq!(run.outcome, ChildOutcome::Exited(0));
    assert!(matches!(acc, Err(ReportError::Missing(_))));

    let (run, acc) = fault_run("garbage-report", Duration::from_secs(120));
    assert_eq!(run.outcome, ChildOutcome::Exited(0));
    assert!(matches!(acc, Err(ReportError::Unparsable(_))));
}

fn libc_sigabrt() -> i32 {
    6
}

/// R-NAX (parent-level test): the child refuses its start environment with
/// the dedicated status before any MLX-C call and writes no report.
#[test]
fn child_refuses_a_nax_enabling_environment() {
    let root = repo_root();
    let out = fresh(&out_root().join("r-nax"));
    let tmp = fresh(&out.join("tmp"));
    let prefix = std::env::var("MLX_C_PREFIX")
        .map(PathBuf::from)
        .unwrap_or_else(|_| tmp.clone());
    let base = child_env(&prefix, &tmp);
    let variants: Vec<(&str, Vec<(String, String)>)> = vec![
        (
            "tf32-unset",
            base.iter()
                .filter(|(k, _)| k != "MLX_ENABLE_TF32")
                .cloned()
                .collect(),
        ),
        (
            "tf32-one",
            base.iter()
                .map(|(k, v)| {
                    if k == "MLX_ENABLE_TF32" {
                        (k.clone(), "1".into())
                    } else {
                        (k.clone(), v.clone())
                    }
                })
                .collect(),
        ),
        (
            "gpu-arch",
            [
                base.clone(),
                vec![("MLX_METAL_GPU_ARCH".into(), "applegpu_g17s".into())],
            ]
            .concat(),
        ),
        (
            "max-ops",
            [
                base.clone(),
                vec![("MLX_MAX_OPS_PER_BUFFER".into(), "1".into())],
            ]
            .concat(),
        ),
        (
            "max-mb",
            [
                base.clone(),
                vec![("MLX_MAX_MB_PER_BUFFER".into(), "1".into())],
            ]
            .concat(),
        ),
    ];
    for (label, env) in variants {
        let child_out = out.join(label);
        let run = run_child(
            &child(),
            &[
                "--repo".into(),
                root.to_string_lossy().into(),
                "--out".into(),
                child_out.to_string_lossy().into(),
            ],
            &env,
            Duration::from_secs(120),
            &out,
            label,
        );
        assert_eq!(
            run.outcome,
            ChildOutcome::Exited(frozen::R_NAX_EXIT_STATUS),
            "{label}"
        );
        assert!(!child_out.join("report.json").exists(), "{label}");
        let err = std::fs::read_to_string(&run.stderr_path).unwrap();
        assert!(err.starts_with("R-NAX"), "{label}: {err}");
    }
}

/// B8/B9 in the child: ownership permutations, error-path frees, an injected
/// MLX-C error that becomes a Rust error after which the child continues, a
/// refusal with zero MLX-C calls, and a single handler install.
#[test]
fn child_selftest_ownership_and_injected_error() {
    if !native_built() {
        return;
    }
    let root = repo_root();
    let out = fresh(&out_root().join("selftest"));
    let tmp = fresh(&out.join("tmp"));
    let run = run_child(
        &child(),
        &[
            "--repo".into(),
            root.to_string_lossy().into(),
            "--out".into(),
            out.join("child").to_string_lossy().into(),
            "--mode".into(),
            "selftest".into(),
        ],
        &child_env(&native_prefix(), &tmp),
        frozen_timeout(),
        &out,
        "child",
    );
    assert_eq!(
        run.outcome,
        ChildOutcome::Exited(0),
        "{}",
        std::fs::read_to_string(&run.stderr_path).unwrap_or_default()
    );
    let st: Value =
        serde_json::from_slice(&std::fs::read(out.join("child/selftest.json")).unwrap()).unwrap();
    println!("{}", serde_json::to_string_pretty(&st).unwrap());
    assert_eq!(st["pass"], true, "{st}");
    assert!(st["checks"].as_object().unwrap().len() >= 8);
}

/// A tampered population never reaches the qualification: the child itself
/// refuses a manifest whose hash differs from the frozen one (setup failure,
/// no report), independently of the parent's own validation.
#[test]
fn child_refuses_a_tampered_manifest() {
    if !native_built() {
        return;
    }
    let src = repo_root();
    let root = fresh(&out_root().join("tampered-repo"));
    for rel in [
        frozen::CONTRACT_PATH,
        frozen::GENERATOR_PATH,
        frozen::MANIFEST_PATH,
    ] {
        let to = root.join(rel);
        std::fs::create_dir_all(to.parent().unwrap()).unwrap();
        std::fs::copy(src.join(rel), &to).unwrap();
    }
    let m = root.join(frozen::MANIFEST_PATH);
    let mut bytes = std::fs::read(&m).unwrap();
    let last = bytes.len() - 2;
    bytes[last] = b' ';
    std::fs::write(&m, bytes).unwrap();
    assert!(validate_population(&root, None).is_err());
    let out = fresh(&out_root().join("faults/tampered"));
    let tmp = fresh(&out.join("tmp"));
    let run = run_child(
        &child(),
        &[
            "--repo".into(),
            root.to_string_lossy().into(),
            "--out".into(),
            out.join("child").to_string_lossy().into(),
        ],
        &child_env(&native_prefix(), &tmp),
        Duration::from_secs(300),
        &out,
        "child",
    );
    assert_eq!(
        run.outcome,
        ChildOutcome::Exited(frozen::SETUP_FAILURE_EXIT_STATUS)
    );
    assert!(!out.join("child/report.json").exists());
    let err = std::fs::read_to_string(&run.stderr_path).unwrap();
    assert!(err.contains("manifest.json: sha256"), "{err}");
}
