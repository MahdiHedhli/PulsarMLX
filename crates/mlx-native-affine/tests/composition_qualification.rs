//! F020 Slice 2C -- synthetic expert-plane composition qualification (parent
//! side; slice2c-plan.md section 4) and its required controls.
//!
//! `test = false` in Cargo.toml: the Slice 2B step's `cargo test -p
//! mlx-native-affine` never runs this target; the Slice 2C step runs it with
//! `--test composition_qualification`.
//!
//! `composition_qualification_of_the_frozen_population` is the gate:
//!
//! 1. validate the frozen population (composition contract, plan, generator,
//!    generator test, manifest, listing, every checkpoint and standalone file,
//!    the six Slice 2B identities, generator `--check`, the generator's test);
//! 2. run `qualify --mode compose` ONCE with the fixed Slice 2B child
//!    environment under the frozen 1800 s watchdog (SIGKILL, reap, TIMEOUT, no
//!    retry) and accept its report with `harness::accept_compose_report`;
//! 3. re-decide every selection check from the reported evidence (the child's
//!    verdicts are never trusted; equal outputs never substitute for input
//!    evidence), the refusal and mutation counter rules, and N-COMP-ARRAYS;
//! 4. compute C: the Rust binary64 R1 (`mlx_affine::reference_qmm`) and, via
//!    `acceptance/composition_gates_v1.py`, the exact Python R1 on every
//!    standalone file of the 14 executed cases;
//! 5. decide G-QMM-RUST and G-QMM-EXACT on A and on B separately,
//!    G-R1-SELF-QMM on C, N-QMM-SHAPE-DTYPE, N-COMP-AB (exact byte equality of
//!    A's and B's output files), N-COMP-ABA and N-COMP-ARRAYS;
//! 6. validate again, check child independence (static source scan and `nm`
//!    with both controls), and write `summary.json`.
//!
//! Environment as the Slice 2B parent: `MLX_C_PREFIX`,
//! `PULSAR_F020_COMPOSITION_OUT` (default `target/f020-slice2c`),
//! `PULSAR_F020_HOST_LABEL`, `PULSAR_F020_PYTHON`. Without the native build the
//! native tests fail under `PULSAR_REQUIRE_NATIVE_MLX=1` and report NOT RUN
//! otherwise.

use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};
use std::time::Duration;

use mlx_affine::module::{classify_module, AffineTriple, ModuleKind};
use mlx_affine::reference_qmm::{qmm_reference, QmmMetadata};
use mlx_affine::spec::{Bits, GroupSize, Mode, QuantSpec};
use mlx_native_affine::compose::{
    compose, select_plane, stage, Backing, CompositionRefusalId, Source, COMPONENTS,
    IDENTITY_FIELDS,
};
use mlx_native_affine::dtype::Dtype;
use mlx_native_affine::fixture::{load_case, repo_root, sha256_hex, CaseSpec};
use mlx_native_affine::frozen_compose::{self as fc, validate_population};
use mlx_native_affine::gates::g_qmm_rust;
use mlx_native_affine::harness::{
    accept_compose_report, child_env, frozen_timeout, run_child, ChildOutcome, ChildRun,
    ReportError,
};
use serde_json::{json, Map, Value};

// ------------------------------------------------------------ plumbing --

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
    let p = std::env::var("PULSAR_F020_COMPOSITION_OUT")
        .map(PathBuf::from)
        .unwrap_or_else(|_| repo_root().join("target/f020-slice2c"));
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

fn crate_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
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

fn compose_run(out: &Path, label: &str, extra: &[&str], timeout: Duration) -> (ChildRun, PathBuf) {
    let root = repo_root();
    let tmp = fresh(&out.join(format!("{label}-tmp")));
    let child_out = out.join(label);
    let _ = std::fs::remove_dir_all(&child_out);
    let mut args: Vec<String> = vec![
        "--repo".into(),
        root.to_string_lossy().into(),
        "--out".into(),
        child_out.to_string_lossy().into(),
        "--mode".into(),
        fc::CHILD_MODE.into(),
    ];
    args.extend(extra.iter().map(|s| s.to_string()));
    let run = run_child(
        &child(),
        &args,
        &child_env(&native_prefix(), &tmp),
        timeout,
        out,
        label,
    );
    (run, child_out)
}

fn manifest_ids() -> BTreeSet<String> {
    let raw = std::fs::read(repo_root().join(fc::MANIFEST_PATH)).unwrap();
    mlx_native_affine::fixture::parse_manifest(&raw)
        .unwrap()
        .ids()
        .into_iter()
        .collect()
}

// ---------------------------------------------------- R1 (Rust, on C) --

struct RustR1 {
    y: Vec<f64>,
    phi: Vec<f64>,
}

fn rust_r1(dir: &Path, spec: &CaseSpec) -> RustR1 {
    let c = load_case(dir, spec).unwrap();
    let t = |n: &str| c.tensor(n).unwrap();
    let (s, b) = (t("scales"), t("biases"));
    assert_eq!(
        s.dtype,
        Dtype::BF16,
        "{}: Slice 2C metadata is BF16",
        spec.id
    );
    let (sh, bh) = (s.halves_u16(), b.halves_u16());
    let m = QmmMetadata::Bf16 {
        scales: &sh,
        biases: &bh,
    };
    let p = |k: &str| spec.param_u64(k).unwrap() as usize;
    let r = qmm_reference(
        &t("x").words_u32(),
        &t("w").words_u32(),
        m,
        p("M_eff"),
        p("N"),
        p("K"),
        p("bits") as u32,
        p("group_size"),
    )
    .unwrap();
    RustR1 { y: r.y, phi: r.phi }
}

fn hexes(v: &[f64]) -> Vec<String> {
    v.iter().map(|x| format!("{:016x}", x.to_bits())).collect()
}

fn u32s(b: &[u8]) -> Vec<u32> {
    b.chunks_exact(4)
        .map(|c| u32::from_le_bytes(c.try_into().unwrap()))
        .collect()
}

fn side_output(out_dir: &Path, side: &Value) -> Option<Vec<u8>> {
    let o = &side["output"];
    let data = std::fs::read(out_dir.join(o["file"].as_str()?)).ok()?;
    (sha256_hex(&data) == o["sha256"].as_str()?).then_some(data)
}

fn g_rust_side(y3: &[u8], r: &RustR1, k: usize, n_gamma: usize) -> (bool, usize, f64) {
    let y: Vec<f32> = u32s(y3).into_iter().map(f32::from_bits).collect();
    if y.len() != r.y.len() {
        return (false, usize::MAX, f64::INFINITY);
    }
    let mut failed = 0usize;
    let mut worst = 0f64;
    for ((&v, &y1), &ph) in y.iter().zip(&r.y).zip(&r.phi) {
        let (pass, d, b) = g_qmm_rust(v, y1, ph, k, n_gamma);
        if !pass {
            failed += 1;
        }
        worst = worst.max(if b > 0.0 {
            d / b
        } else if d == 0.0 {
            0.0
        } else {
            f64::INFINITY
        });
    }
    (failed == 0, failed, worst)
}

// ------------------------------------------- selection re-decisions --

/// The parent's own comparison of a reported selection record with an
/// oracle: identity field by field, ranges and sha256 component by component.
/// Written independently of `compose::selection_mismatches`.
fn parent_mismatches(
    record: &Value,
    identity: &Value,
    ranges: &Value,
    sha: &Value,
) -> BTreeSet<String> {
    let mut out = BTreeSet::new();
    let id = record.get("identity");
    for f in IDENTITY_FIELDS {
        let got = id.and_then(|i| i.get(f));
        let want = identity.get(f);
        if got.is_none() || want.is_none() || got != want {
            out.insert(format!("S-IDENTITY:{f}"));
        }
    }
    for c in COMPONENTS {
        let got = record.get("ranges").and_then(|r| r.get(c));
        let want = ranges.get(c);
        let ok = matches!((got, want), (Some(g), Some(w))
            if g.get("shard").is_some() && g.get("shard") == w.get("shard")
            && g.get("begin").and_then(Value::as_u64).is_some() && g.get("begin") == w.get("begin")
            && g.get("len").and_then(Value::as_u64).is_some() && g.get("len") == w.get("len"));
        if !ok {
            out.insert(format!("S-RANGES:{c}"));
        }
        let got = record
            .get("sha256")
            .and_then(|s| s.get(c))
            .and_then(Value::as_str);
        let want = sha.get(c).and_then(Value::as_str);
        if got.is_none() || got != want {
            out.insert(format!("S-BYTES:{c}"));
        }
    }
    out
}

fn has_prefix(set: &BTreeSet<String>, p: &str) -> bool {
    set.iter().any(|s| s.starts_with(p))
}

/// S-STAGED-EQUAL from the per-side records only (S-NO-OUTPUT-SUBSTITUTION):
/// A == B == expected.staged_inputs for x, w, scales, biases, each with
/// dtype, shape, nbytes and sha256 present. Missing evidence fails.
fn staged_equal(rec: &Value, expected: &Value) -> bool {
    let (a, b) = (&rec["staged_inputs"]["A"], &rec["staged_inputs"]["B"]);
    ["x", "w", "scales", "biases"].iter().all(|role| {
        let (ra, rb, re) = (&a[role], &b[role], &expected[role]);
        ["dtype", "shape", "nbytes", "sha256"]
            .iter()
            .all(|k| !ra[k].is_null() && ra[k] == rb[k] && ra[k] == re[k])
    })
}

/// An object whose key set equals `want`'s exactly and whose every value
/// equals `want`'s (no missing, no extra key).
fn exact_map(got: &Value, want: &Map<String, Value>) -> bool {
    got.as_object().is_some_and(|g| {
        g.len() == want.len()
            && g.keys().eq(want.keys())
            && want.iter().all(|(k, v)| g.get(k) == Some(v))
    })
}

/// A phase's backing records: one record per expected shard, EXACTLY -- the
/// reported shard names are unique and their set equals the expected set
/// (no duplicate, no missing, no extra shard) -- and every record is the
/// whole file (not a window) with the file's length and expected hash at
/// load and as held now. Missing evidence fails (S-NO-OUTPUT-SUBSTITUTION).
fn backing_exact(
    phase: &Value,
    shard_map: &Map<String, Value>,
    file_lens: &BTreeMap<String, u64>,
) -> bool {
    let Some(list) = phase.get("backing").and_then(Value::as_array) else {
        return false;
    };
    let mut seen: BTreeSet<&str> = BTreeSet::new();
    for b in list {
        let Some(name) = b.get("shard").and_then(Value::as_str) else {
            return false;
        };
        if !seen.insert(name) {
            return false; // duplicate record
        }
        let Some(want) = shard_map.get(name) else {
            return false; // extra shard
        };
        let entry_ok = b.get("sha256") == Some(want)
            && b.get("file_sha256_at_load") == Some(want)
            && b.get("len").and_then(Value::as_u64).is_some()
            && b.get("len").and_then(Value::as_u64) == file_lens.get(name).copied()
            && b.get("file_len").and_then(Value::as_u64) == file_lens.get(name).copied()
            && b.get("window") == Some(&Value::Bool(false));
        if !entry_ok {
            return false;
        }
    }
    // Exhaustive: every expected shard has exactly one record.
    seen.len() == shard_map.len()
        && seen
            .iter()
            .copied()
            .eq(shard_map.keys().map(String::as_str))
}

/// S-SOURCE-UNCHANGED from the phase-labelled records only: for EACH phase,
/// the reported shard-file set equals the expected set exactly with the
/// expected hashes; the backing records after selection and after execution
/// are unique and exhaustive (see [`backing_exact`]); the standalone file
/// before and after equals the expected one exactly.
fn source_unchanged(rec: &Value, expected: &Value, file_lens: &BTreeMap<String, u64>) -> bool {
    let ph = &rec["source_hashes"];
    let Some(shard_map) = expected["shards"].as_object() else {
        return false;
    };
    let Some(standalone) = expected["standalone"].as_object() else {
        return false;
    };
    if shard_map.is_empty()
        || standalone.len() != 1
        || expected["phases"] != json!(fc::SOURCE_PHASES)
        || file_lens.len() < shard_map.len()
    {
        return false;
    }
    exact_map(&ph["before_load"]["shards"], shard_map)
        && exact_map(&ph["before_load"]["standalone"], standalone)
        && exact_map(&ph["after_host_selection"]["shards"], shard_map)
        && backing_exact(&ph["after_host_selection"], shard_map, file_lens)
        && exact_map(&ph["after_native_execution"]["shards"], shard_map)
        && backing_exact(&ph["after_native_execution"], shard_map, file_lens)
        && exact_map(&ph["after_native_execution"]["standalone"], standalone)
}

/// Controls for S-SOURCE-UNCHANGED (implementation review r1, finding 1):
/// every defect below, applied to an otherwise valid record, must be
/// REJECTED. Returns (label, rejected) for each; the valid record itself
/// must be accepted, reported as ("valid record accepted", accepted).
fn source_evidence_controls(
    rec: &Value,
    expected: &Value,
    file_lens: &BTreeMap<String, u64>,
) -> Vec<(String, bool)> {
    let mut out = vec![(
        "valid record accepted".to_string(),
        source_unchanged(rec, expected, file_lens),
    )];
    let mut add = |label: String, mutate: &dyn Fn(&mut Value)| {
        let mut r = rec.clone();
        mutate(&mut r);
        out.push((label, !source_unchanged(&r, expected, file_lens)));
    };
    for phase in ["after_host_selection", "after_native_execution"] {
        let n = rec["source_hashes"][phase]["backing"]
            .as_array()
            .map_or(0, Vec::len);
        if n >= 2 {
            add(
                format!("{phase}: duplicate backing record replacing another shard"),
                &|r| {
                    let list = r["source_hashes"][phase]["backing"].as_array_mut().unwrap();
                    let first = list[0].clone();
                    for slot in list.iter_mut().skip(1) {
                        *slot = first.clone();
                    }
                },
            );
            add(
                format!("{phase}: one duplicated backing record added"),
                &|r| {
                    let list = r["source_hashes"][phase]["backing"].as_array_mut().unwrap();
                    let first = list[0].clone();
                    list.push(first);
                },
            );
        }
        add(format!("{phase}: missing backing record"), &|r| {
            r["source_hashes"][phase]["backing"]
                .as_array_mut()
                .unwrap()
                .pop();
        });
        add(
            format!("{phase}: extra backing record for another shard"),
            &|r| {
                let list = r["source_hashes"][phase]["backing"].as_array_mut().unwrap();
                let mut extra = list[0].clone();
                extra["shard"] = json!("model-extra.safetensors");
                list.push(extra);
            },
        );
        add(format!("{phase}: backing evidence absent"), &|r| {
            r["source_hashes"][phase]
                .as_object_mut()
                .unwrap()
                .remove("backing");
        });
        add(format!("{phase}: windowed backing"), &|r| {
            r["source_hashes"][phase]["backing"][0]["window"] = json!(true);
        });
    }
    for phase in fc::SOURCE_PHASES {
        add(format!("{phase}: missing shard-file hash"), &|r| {
            let m = r["source_hashes"][phase]["shards"].as_object_mut().unwrap();
            let k = m.keys().next().unwrap().clone();
            m.remove(&k);
        });
        add(format!("{phase}: extra shard-file hash"), &|r| {
            r["source_hashes"][phase]["shards"]["model-extra.safetensors"] = json!("0".repeat(64));
        });
        add(format!("{phase}: phase evidence absent"), &|r| {
            r["source_hashes"].as_object_mut().unwrap().remove(phase);
        });
    }
    for phase in ["before_load", "after_native_execution"] {
        add(format!("{phase}: extra standalone entry"), &|r| {
            r["source_hashes"][phase]["standalone"]["standalone/extra.bin"] = json!("0".repeat(64));
        });
    }
    out
}

fn counters_match(got: &Value, want: &Value) -> bool {
    let Some(w) = want.as_object() else {
        return false;
    };
    !w.is_empty() && w.iter().all(|(k, v)| got.get(k) == Some(v))
}

// ---------------------------------------------- child independence --

/// Names no child code path may contain (plan section 2.1 level 1).
const FORBIDDEN_CHILD_NAMES: [&str; 9] = [
    "reference_qmm",
    "reference::",
    "mlx_affine::reference",
    "decode::",
    "mlx_affine::decode",
    "dequantize_rows",
    "unpack_codes",
    "qmm_reference",
    "dq_reference",
];

/// Scan one source text: forbidden names, glob imports from `mlx_affine`,
/// and any `mlx_affine::` path whose first segment is not module/spec/error.
fn scan_child_source(label: &str, text: &str) -> Vec<String> {
    let mut hits = Vec::new();
    for (i, line) in text.lines().enumerate() {
        for name in FORBIDDEN_CHILD_NAMES {
            if line.contains(name) {
                hits.push(format!("{label}:{}: names {name}", i + 1));
            }
        }
    }
    // `use mlx_affine...;` statements, possibly spanning lines.
    let mut rest = text;
    while let Some(at) = rest.find("use mlx_affine") {
        let tail = &rest[at..];
        let end = tail.find(';').unwrap_or(tail.len());
        let stmt = &tail[..end];
        if stmt.contains('*') {
            hits.push(format!(
                "{label}: glob import `{}`",
                stmt.replace('\n', " ")
            ));
        }
        rest = &tail[end.min(tail.len())..];
        if rest.is_empty() {
            break;
        }
        rest = &rest[1.min(rest.len())..];
    }
    let mut rest = text;
    while let Some(at) = rest.find("mlx_affine::") {
        let seg: String = rest[at + "mlx_affine::".len()..]
            .chars()
            .take_while(|c| c.is_ascii_alphanumeric() || *c == '_' || *c == '{')
            .collect();
        if !(seg == "module" || seg == "spec" || seg == "error") {
            hits.push(format!("{label}: names mlx_affine::{seg}"));
        }
        rest = &rest[at + 1..];
    }
    hits
}

fn child_source_files() -> Vec<PathBuf> {
    let mut files = vec![
        crate_dir().join("src/compose.rs"),
        crate_dir().join("src/frozen_compose.rs"),
    ];
    let bin = crate_dir().join("src/bin/qualify");
    let mut stack = vec![bin];
    while let Some(d) = stack.pop() {
        for e in std::fs::read_dir(&d).unwrap() {
            let p = e.unwrap().path();
            if p.is_dir() {
                stack.push(p);
            } else {
                files.push(p);
            }
        }
    }
    files.sort();
    files
}

fn static_independence() -> Value {
    let mut hits = Vec::new();
    let files = child_source_files();
    for f in &files {
        let text = std::fs::read_to_string(f).unwrap();
        hits.extend(scan_child_source(&f.to_string_lossy(), &text));
    }
    // Non-vacuous control: the scanner flags every forbidden form.
    let control = "use mlx_affine::*;\nuse mlx_affine::{module::*};\nlet y = mlx_affine::reference_qmm::qmm_reference;\nmlx_affine::decode::unpack_codes();\nuse mlx_affine::ScaleDtype;\n";
    let control_hits = scan_child_source("control", control);
    let control_ok = control_hits.len() >= 8
        && FORBIDDEN_CHILD_NAMES
            .iter()
            .filter(|n| control.contains(*n))
            .all(|n| control_hits.iter().any(|h| h.contains(n)))
        && control_hits.iter().any(|h| h.contains("glob import"))
        && control_hits
            .iter()
            .any(|h| h.contains("mlx_affine::ScaleDtype"));
    let rels: Vec<String> = files
        .iter()
        .map(|f| {
            f.strip_prefix(crate_dir())
                .unwrap_or(f)
                .to_string_lossy()
                .into_owned()
        })
        .collect();
    json!({"files": rels, "hits": hits, "control_detected": control_ok, "control_hits": control_hits.len(),
           "pass": hits.is_empty() && control_ok && rels.len() >= 9})
}

fn nm_symbols(path: &Path) -> Result<String, String> {
    let out = std::process::Command::new("nm")
        .arg("-a")
        .arg(path)
        .output()
        .map_err(|e| format!("nm spawn: {e}"))?;
    if !out.status.success() {
        return Err(format!(
            "nm failed: {}",
            String::from_utf8_lossy(&out.stderr)
        ));
    }
    Ok(String::from_utf8_lossy(&out.stdout).into_owned())
}

const NM_FORBIDDEN: [&str; 3] = [
    "10mlx_affine13reference_qmm",
    "10mlx_affine9reference",
    "10mlx_affine6decode",
];

fn nm_independence() -> Value {
    let version = std::process::Command::new("nm")
        .arg("--version")
        .output()
        .map(|o| {
            String::from_utf8_lossy(&o.stdout)
                .lines()
                .take(2)
                .collect::<Vec<_>>()
                .join(" | ")
        })
        .unwrap_or_else(|e| format!("unavailable: {e}"));
    let count = |table: &str, pat: &str| table.lines().filter(|l| l.contains(pat)).count();
    let r = (|| -> Result<Value, String> {
        let child_table = nm_symbols(&child())?;
        let own = std::env::current_exe().map_err(|e| e.to_string())?;
        let own_table = nm_symbols(&own)?;
        let forbidden: Map<String, Value> = NM_FORBIDDEN
            .iter()
            .map(|p| (p.to_string(), json!(count(&child_table, p))))
            .collect();
        let positive = count(&child_table, "10mlx_affine6module");
        let negative = count(&own_table, "10mlx_affine13reference_qmm");
        let child_sha = sha256_hex(&std::fs::read(child()).map_err(|e| e.to_string())?);
        let pass = forbidden.values().all(|v| v == 0) && positive >= 1 && negative >= 1;
        Ok(json!({
            "nm_version": version,
            "child_executable_sha256": child_sha,
            "child_symbol_lines": child_table.lines().count(),
            "child_forbidden_hits": forbidden,
            "positive_control_10mlx_affine6module": positive,
            "negative_control_parent_10mlx_affine13reference_qmm": negative,
            "pass": pass,
        }))
    })();
    r.unwrap_or_else(|e| json!({"pass": false, "error": e, "nm_version": version}))
}

/// Coexistence (C7): the only mlx_set_error_handler call site is the child's
/// Once; no crate linked into the child names it.
fn handler_coexistence() -> Value {
    let mut sites = Vec::new();
    for f in child_source_files() {
        let text = std::fs::read_to_string(&f).unwrap();
        for (i, l) in text.lines().enumerate() {
            let t = l.trim();
            if t.starts_with("//") || t.starts_with("pub fn mlx_set_error_handler") {
                continue;
            }
            if t.contains("mlx_set_error_handler(") {
                sites.push(format!(
                    "{}:{}",
                    f.file_name().unwrap().to_string_lossy(),
                    i + 1
                ));
            }
        }
    }
    let mut linked_hits = Vec::new();
    for krate in ["mlx-affine", "safetensors-catalog", "backend"] {
        let src = crate_dir().join("..").join(krate).join("src");
        let mut stack = vec![src];
        while let Some(d) = stack.pop() {
            for e in std::fs::read_dir(&d).unwrap() {
                let p = e.unwrap().path();
                if p.is_dir() {
                    stack.push(p);
                } else if std::fs::read_to_string(&p)
                    .unwrap_or_default()
                    .contains("mlx_set_error_handler")
                {
                    linked_hits.push(p.to_string_lossy().into_owned());
                }
            }
        }
    }
    json!({"call_sites": sites, "linked_crate_hits": linked_hits,
           "pass": sites.len() == 1 && sites[0].starts_with("native.rs") && linked_hits.is_empty()})
}

// ---------------------------------------------------------------- gate --

#[test]
fn composition_qualification_of_the_frozen_population() {
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
    let arch_host = std::env::consts::ARCH;

    // 1. Frozen population before the run.
    let (manifest, doc, pre) = validate_population(&root, Some(&py_s))
        .expect("frozen population validates before the run");
    let docs = fc::case_documents(&doc);
    let tmp = fresh(&out.join("tmp"));
    let gen_test = run_child(
        &py,
        &[
            "-B".into(),
            root.join(fc::GENERATOR_TEST_PATH).to_string_lossy().into(),
        ],
        &[
            ("PATH".to_string(), "/usr/bin:/bin".to_string()),
            ("HOME".to_string(), tmp.to_string_lossy().into_owned()),
        ],
        frozen_timeout(),
        &out,
        "generator-test",
    );

    // 2. The compose child, once, under the frozen watchdog.
    let (run, child_out) = compose_run(&out, "child", &[], frozen_timeout());
    let report_path = child_out.join("report.json");
    let want_ids: BTreeSet<String> = manifest.ids().into_iter().collect();
    let report = match accept_compose_report(&run, &report_path, &want_ids) {
        Ok(r) => r,
        Err(e) => {
            let summary = json!({"schema": fc::PARENT_SUMMARY_SCHEMA, "result": "FAIL", "host_label": host,
                                 "candidate_commit": candidate, "child_outcome": run.outcome.describe(),
                                 "report_error": e.to_string()});
            std::fs::write(
                out.join("summary.json"),
                serde_json::to_vec_pretty(&summary).unwrap(),
            )
            .unwrap();
            panic!(
                "compose child report not accepted: {e} ({})",
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
    if gen_test.outcome != ChildOutcome::Exited(0) {
        fail(format!("generator test: {}", gen_test.outcome.describe()));
    }

    // Child-level evidence: E1-E4, E6 inherited, handler, handles.
    let prov = &report["provenance"];
    if prov["mlx_version"] != fc_mlx_version() {
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
    if report["per_side_numerical_calls_pinned_from_source"] != fc::PER_SIDE_NUMERICAL_CALLS {
        fail("child's pinned per-side numerical-call count differs".into());
    }

    // 4. C: the Rust binary64 R1 on every standalone file that lists it; then
    // the exact Python R1 and the exact gates on A and B.
    let fixture_dir = fc::fixture_dir(&root);
    let mut r1: BTreeMap<String, RustR1> = BTreeMap::new();
    let mut rust_doc = Map::new();
    for spec in manifest
        .cases
        .iter()
        .filter(|c| c.has_reference("rust_binary64_r1"))
    {
        let r = rust_r1(&fixture_dir, spec);
        rust_doc.insert(
            spec.id.clone(),
            json!({"op": spec.op, "y": hexes(&r.y), "phi": hexes(&r.phi)}),
        );
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
    let gates_path = out.join("composition-gates.json");
    let py_env = vec![
        ("PATH".to_string(), "/usr/bin:/bin".to_string()),
        ("HOME".to_string(), tmp.to_string_lossy().into_owned()),
    ];
    let g_run = run_child(
        &py,
        &[
            "-I".into(),
            "-B".into(),
            crate_dir()
                .join("acceptance/composition_gates_v1.py")
                .to_string_lossy()
                .into(),
            "--manifest".into(),
            root.join(fc::MANIFEST_PATH).to_string_lossy().into(),
            "--fixture-dir".into(),
            fixture_dir.to_string_lossy().into(),
            "--rust-r1".into(),
            rust_path.to_string_lossy().into(),
            "--report".into(),
            report_path.to_string_lossy().into(),
            "--report-dir".into(),
            child_out.to_string_lossy().into(),
            "--out".into(),
            gates_path.to_string_lossy().into(),
        ],
        &py_env,
        frozen_timeout(),
        &out,
        "composition-gates",
    );
    if g_run.outcome != ChildOutcome::Exited(0) {
        fail(format!(
            "composition gates run: {}",
            g_run.outcome.describe()
        ));
    }
    let exact: Value = std::fs::read(&gates_path)
        .ok()
        .and_then(|b| serde_json::from_slice(&b).ok())
        .unwrap_or(Value::Null);

    // 3 + 5. Per-case decisions, by family.
    let mut counts: BTreeMap<String, (usize, usize)> = BTreeMap::new();
    let mut tally = |gate: &str, pass: bool| {
        let e = counts.entry(gate.to_string()).or_default();
        e.0 += 1;
        e.1 += pass as usize;
    };
    let mut per_case = Vec::new();
    let mut refusals = Vec::new();
    let mut mutations = Vec::new();
    let mut ab = Vec::new();
    let mut copy = Vec::new();
    let mut worst: BTreeMap<String, (usize, f64, f64)> = BTreeMap::new();
    let mut outputs_a: BTreeMap<String, Vec<u8>> = BTreeMap::new();
    let mut source_control_failures: Vec<String> = Vec::new();
    let mut source_controls_run = 0usize;
    let mut source_control_cases = 0usize;
    for spec in &manifest.cases {
        let rec = &records[&spec.id];
        let d = &docs[&spec.id];
        let expected = &d["expected"];
        let oracle = &d["oracle"];
        let mut gates = Map::new();
        let mut case_pass = true;
        let mut gate = |g: &str, pass: bool, detail: Value, gates: &mut Map<String, Value>| {
            tally(g, pass);
            gates.insert(g.into(), json!({"pass": pass, "detail": detail}));
            pass
        };
        let ck = d["composition"]["checkpoint"]
            .as_str()
            .unwrap_or_default()
            .trim_start_matches("checkpoints/")
            .to_string();
        let file_lens: BTreeMap<String, u64> = doc["checkpoints"][&ck]["files"]
            .as_object()
            .map(|m| {
                m.iter()
                    .filter_map(|(k, v)| v["bytes"].as_u64().map(|b| (k.clone(), b)))
                    .collect()
            })
            .unwrap_or_default();
        match spec.family.as_str() {
            "FX-COMP-ACCEPT" | "FX-COMP-SEQUENCE" | "FX-COMP-INHERITED-REFUSE" => {
                let inherited = spec.family == "FX-COMP-INHERITED-REFUSE";
                let checks: BTreeSet<&str> = expected["checks"]
                    .as_array()
                    .map(|a| a.iter().filter_map(Value::as_str).collect())
                    .unwrap_or_default();
                // Selection, from the SelectionRecord against the oracle.
                let mm = parent_mismatches(
                    &rec["selection"],
                    &oracle["identity"],
                    &oracle["ranges"],
                    &oracle["sha256"],
                );
                let sel = json!({"mismatches": mm});
                for (g, p) in [
                    ("S-IDENTITY", "S-IDENTITY:"),
                    ("S-RANGES", "S-RANGES:"),
                    ("S-BYTES", "S-BYTES:"),
                ] {
                    if checks.contains(g) {
                        case_pass &= gate(
                            g,
                            !has_prefix(&mm, p) && rec["selection"].is_object(),
                            sel.clone(),
                            &mut gates,
                        );
                    }
                }
                // Inputs: decided from input evidence only.
                if checks.contains("S-STAGED-EQUAL") {
                    let p = staged_equal(rec, &expected["staged_inputs"]);
                    case_pass &= gate(
                        "S-STAGED-EQUAL",
                        p,
                        rec["staged_inputs"].clone(),
                        &mut gates,
                    );
                }
                if checks.contains("S-SOURCE-UNCHANGED") {
                    let p = source_unchanged(rec, &expected["source_hashes"], &file_lens);
                    // The predicate's own controls on this real record: every
                    // incomplete, duplicated or extra evidence form is rejected.
                    let ctl = source_evidence_controls(rec, &expected["source_hashes"], &file_lens);
                    let not_rejected: Vec<&String> =
                        ctl.iter().filter(|(_, ok)| !ok).map(|(l, _)| l).collect();
                    if !not_rejected.is_empty() {
                        source_control_failures.push(format!("{}: {not_rejected:?}", spec.id));
                    }
                    source_controls_run += ctl.len();
                    source_control_cases += 1;
                    case_pass &= gate(
                        "S-SOURCE-UNCHANGED",
                        p,
                        json!({"controls_rejected": ctl.len() - not_rejected.len(), "controls": ctl.len()}),
                        &mut gates,
                    );
                }
                // E1 on both sides (the bridge asserted the device facts).
                let e1 = ["A", "B"]
                    .iter()
                    .all(|s| rec[s]["stats"]["device_facts_gpu"] == true);
                case_pass &= gate("E1-DEVICE", e1, json!(null), &mut gates);
                if inherited {
                    let want = expected["refusal_id"].as_str();
                    let want_b = expected["b_refusal_id"].as_str();
                    let zero_before = |s: &str| {
                        rec[s]["stats"]["numerical_calls_before_decision"] == 0
                            && rec[s]["stats"]["imports_before_decision"] == 0
                            && counters_match(
                                &rec[s]["counters"],
                                &json!({"imports": 0, "numerical_calls": 0, "result_handles_created": 0, "array_free_calls": 0}),
                            )
                    };
                    let p = rec["outcome"] == "refused"
                        && rec["A"]["refusal_id"].as_str() == want
                        && rec["B"]["refusal_id"].as_str() == want_b
                        && want == want_b
                        && zero_before("A")
                        && zero_before("B")
                        && expected["native_numerical_before_decision"] == 0
                        && expected["native_imports_before_decision"] == 0;
                    refusals.push(json!({"id": spec.id, "stage": "bridge", "expected": want, "got_A": rec["A"]["refusal_id"],
                                         "got_B": rec["B"]["refusal_id"], "stats_A": rec["A"]["stats"], "stats_B": rec["B"]["stats"], "pass": p}));
                    case_pass &= gate(
                        "INHERITED-REFUSAL",
                        p,
                        json!({"A": rec["A"]["refusal_id"], "B": rec["B"]["refusal_id"]}),
                        &mut gates,
                    );
                } else {
                    let executed = rec["outcome"] == "executed"
                        && rec["A"]["outcome"] == "executed"
                        && rec["B"]["outcome"] == "executed";
                    if !executed {
                        case_pass = false;
                        gates.insert("EXECUTION".into(), json!({"pass": false, "outcome": rec["outcome"], "error": rec["error"]}));
                    } else {
                        // N-COMP-ARRAYS: measured per-side intervals, aggregate = sum,
                        // pinned numerical calls, bridge-visible handles.
                        let census = &expected["array_census"];
                        let per = &census["measured_counter_deltas"]["per_side"];
                        let agg_want = &census["measured_counter_deltas"]["whole_case_aggregate"];
                        let (ca, cb, cg) = (
                            &rec["A"]["counters"],
                            &rec["B"]["counters"],
                            &rec["counters"]["whole_case_aggregate"],
                        );
                        let pinned: Map<String, Value> = fc::PER_SIDE_COUNTERS
                            .iter()
                            .map(|(k, v)| (k.to_string(), json!(v)))
                            .collect();
                        let sum_ok = fc::PER_SIDE_COUNTERS.iter().all(|(k, _)| {
                            cg[*k].as_u64().is_some()
                                && cg[*k].as_u64()
                                    == ca[*k].as_u64().zip(cb[*k].as_u64()).map(|(x, y)| x + y)
                        }) && cg["numerical_calls"].as_u64()
                            == Some(2 * fc::PER_SIDE_NUMERICAL_CALLS);
                        let handles = census["bridge_visible_handles"]
                            .as_array()
                            .cloned()
                            .unwrap_or_default();
                        let imports_ok = ["x", "w", "scales", "biases"].iter().all(|role| {
                            let h = handles.iter().find(|h| h["role"] == *role);
                            h.is_some_and(|h| {
                                h["op"] == "import"
                                    && ["A", "B"].iter().all(|s| {
                                        rec["staged_inputs"][s][role]["dtype"] == h["dtype"]
                                            && rec["staged_inputs"][s][role]["shape"] == h["shape"]
                                    })
                            })
                        });
                        let out_h = handles.iter().find(|h| h["role"] == "out");
                        let out_ok = out_h.is_some_and(|h| {
                            ["A", "B"].iter().all(|s| {
                                rec[s]["output"]["dtype"] == h["dtype"]
                                    && rec[s]["output"]["shape"] == h["shape"]
                            })
                        });
                        let logical = &oracle["identity"]["logical_shape"];
                        let casts: Vec<&Value> =
                            handles.iter().filter(|h| h["op"] == "astype").collect();
                        let no_weight_float = casts.len() == 2
                            && casts.iter().all(|h| {
                                h["shape"] != *logical
                                    && h["dtype"] == "F32"
                                    && h["shape"] == oracle["identity"]["metadata_shape"]
                            })
                            && ["A", "B"]
                                .iter()
                                .all(|s| rec[s]["output"]["shape"] != *logical)
                            && handles.len() == 7;
                        let arrays_ok = counters_match(ca, &per["A"])
                            && counters_match(cb, &per["B"])
                            && counters_match(ca, &Value::Object(pinned.clone()))
                            && counters_match(cb, &Value::Object(pinned))
                            && ca["numerical_calls"] == fc::PER_SIDE_NUMERICAL_CALLS
                            && cb["numerical_calls"] == fc::PER_SIDE_NUMERICAL_CALLS
                            && counters_match(cg, agg_want)
                            && sum_ok
                            && imports_ok
                            && out_ok
                            && no_weight_float;
                        case_pass &= gate(
                            "N-COMP-ARRAYS",
                            arrays_ok,
                            json!({"A": ca, "B": cb, "aggregate": cg, "imports_ok": imports_ok, "out_ok": out_ok, "no_float_weight": no_weight_float}),
                            &mut gates,
                        );
                        let plane_bytes_equal = ["w", "scales", "biases"]
                            .iter()
                            .zip(COMPONENTS)
                            .all(|(r, c)| {
                                rec["staged_inputs"]["A"][r]["nbytes"]
                                    == rec["selection"]["ranges"][c]["len"]
                            });
                        copy.push(json!({"id": spec.id, "staging_bytes": rec["copy_accounting"]["measured"]["staging"],
                                         "plane_bytes_equal": plane_bytes_equal,
                                         "counters_A": ca, "counters_B": cb, "aggregate": cg,
                                         "source_derived_workspace": census["source_derived_workspace"]}));
                        // N-QMM-SHAPE-DTYPE on A and B.
                        for s in ["A", "B"] {
                            let st = rec[s]["structural"]
                                .as_object()
                                .is_some_and(|m| !m.is_empty() && m.values().all(|v| v == true));
                            case_pass &= gate(
                                &format!("N-QMM-SHAPE-DTYPE({s})"),
                                st,
                                rec[s]["structural"].clone(),
                                &mut gates,
                            );
                        }
                        // N-COMP-AB: the output FILES, byte for byte.
                        let (oa, ob) = (
                            side_output(&child_out, &rec["A"]),
                            side_output(&child_out, &rec["B"]),
                        );
                        let ab_equal =
                            matches!((&oa, &ob), (Some(a), Some(b)) if a == b && !a.is_empty());
                        let first_diff = match (&oa, &ob) {
                            (Some(a), Some(b)) => a.iter().zip(b).position(|(x, y)| x != y),
                            _ => None,
                        };
                        ab.push(json!({"id": spec.id, "equal": ab_equal, "A_sha256": rec["A"]["output"]["sha256"],
                                       "B_sha256": rec["B"]["output"]["sha256"], "first_differing_byte": first_diff,
                                       "staged_equal": staged_equal(rec, &expected["staged_inputs"])}));
                        case_pass &= gate(
                            "N-COMP-AB",
                            ab_equal,
                            json!({"first_differing_byte": first_diff}),
                            &mut gates,
                        );
                        if let Some(a) = &oa {
                            outputs_a.insert(spec.id.clone(), a.clone());
                        }
                        // G-QMM-RUST on A and B against C.
                        let k = spec.param_u64("K").unwrap() as usize;
                        let n_gamma = spec.manifest_gamma_n().unwrap() as usize;
                        if rec["A"]["kernel"]["bound_gamma_n"].as_u64() != Some(n_gamma as u64) {
                            fail(format!(
                                "{}: family.rs exponent differs from manifest",
                                spec.id
                            ));
                        }
                        let fam = rec["A"]["kernel"]["derived_family"]
                            .as_str()
                            .unwrap_or("?")
                            .to_string();
                        let r = &r1[&spec.id];
                        for (s, o) in [("A", &oa), ("B", &ob)] {
                            let (p, failed, wr) = match o {
                                Some(bytes) => g_rust_side(bytes, r, k, n_gamma),
                                None => (false, usize::MAX, f64::INFINITY),
                            };
                            case_pass &= gate(
                                &format!("G-QMM-RUST({s})"),
                                p,
                                json!({"gamma_n": n_gamma, "failed_elements": failed, "worst_ratio_d_hi_over_B_lo": wr}),
                                &mut gates,
                            );
                            let e = worst.entry(format!("{fam}/{s}")).or_default();
                            e.0 += 1;
                            e.1 = e.1.max(wr);
                        }
                        // G-QMM-EXACT on A and B; G-R1-SELF-QMM on C.
                        let d = &exact["cases"][&spec.id];
                        for s in ["A", "B"] {
                            let g = &d[s]["G-QMM-EXACT"];
                            let p = g["pass"] == true;
                            case_pass &=
                                gate(&format!("G-QMM-EXACT({s})"), p, g.clone(), &mut gates);
                            let e = worst.entry(format!("{fam}/{s}")).or_default();
                            e.2 = e.2.max(g["worst_ratio"].as_f64().unwrap_or(f64::INFINITY));
                        }
                        let g = &d["C"]["G-R1-SELF-QMM"];
                        case_pass &=
                            gate("G-R1-SELF-QMM(C)", g["pass"] == true, g.clone(), &mut gates);
                        gates.insert("kernel (recorded)".into(), json!({"A": rec["A"]["kernel"], "B_family": rec["B"]["kernel"]["derived_family"],
                            "manifest_families_0_31_2": expected["families_0_31_2"]}));
                    }
                }
            }
            "FX-COMP-REFUSE" => {
                let want = expected["refusal_id"].as_str();
                let zero = json!({"numerical": 0, "imports": 0});
                let p = rec["outcome"] == "refused"
                    && rec["refusal"]["id"].as_str() == want
                    && rec["counters"]["whole_case"] == zero
                    && rec["counters"]["at_decision"] == zero
                    && expected["native_calls_in_case"] == zero
                    && rec.get("A").is_none()
                    && rec.get("B").is_none();
                refusals.push(json!({"id": spec.id, "stage": "composition", "expected": want, "got": rec["refusal"]["id"],
                                     "slice1_variant": rec["refusal"]["slice1_variant"], "counters": rec["counters"], "pass": p}));
                case_pass &= gate("C-R-REFUSAL", p, rec["refusal"].clone(), &mut gates);
            }
            "FX-COMP-MUTATION" => {
                let want: BTreeSet<String> = expected["detected_by"]
                    .as_array()
                    .map(|a| {
                        a.iter()
                            .filter_map(|v| v.as_str().map(String::from))
                            .collect()
                    })
                    .unwrap_or_default();
                let zero = json!({"numerical": 0, "imports": 0});
                let m = &d["composition"]["mutation"];
                let kind = m["kind"].as_str().unwrap_or_default();
                let reported: BTreeSet<String> = rec["detected_checks"]
                    .as_array()
                    .map(|a| {
                        a.iter()
                            .filter_map(|v| v.as_str().map(String::from))
                            .collect()
                    })
                    .unwrap_or_default();
                let (p, detail) = if kind == "override_ignored_at_resolution" {
                    let s1 = &m["slice1_refusal"];
                    let p = rec["outcome"] == "detected"
                        && rec["refusal"]["id"] == "C-R-RESOLVE"
                        && rec["refusal"]["slice1_variant"] == s1["variant"]
                        && rec["refusal"]["implied_bits"] == s1["implied_bits"]
                        && reported == want;
                    (p, json!({"refusal": rec["refusal"]}))
                } else {
                    // Re-decide detection from the mutated record, and that the
                    // mutation took effect exactly as the manifest specifies.
                    let mutated = &rec["mutation"]["mutated_record"];
                    let parent_set = parent_mismatches(
                        mutated,
                        &oracle["baseline_identity"],
                        &oracle["baseline_ranges"],
                        &oracle["baseline_sha256"],
                    );
                    let baseline_clean = parent_mismatches(
                        &rec["selection"],
                        &oracle["baseline_identity"],
                        &oracle["baseline_ranges"],
                        &oracle["baseline_sha256"],
                    )
                    .is_empty();
                    let applied = match (m.get("ranges"), m.get("identity")) {
                        (Some(r), None) => {
                            mutated["ranges"] == *r
                                && mutated["sha256"] == m["sha256"]
                                && mutated["identity"] == oracle["baseline_identity"]
                        }
                        (None, Some(i)) => {
                            mutated["identity"] == *i
                                && mutated["ranges"] == oracle["baseline_ranges"]
                                && mutated["sha256"] == oracle["baseline_sha256"]
                        }
                        _ => false,
                    };
                    let p = rec["outcome"] == "detected"
                        && parent_set == want
                        && reported == want
                        && applied
                        && baseline_clean;
                    (
                        p,
                        json!({"parent_detection_set": parent_set, "applied_exactly": applied, "unmutated_plane_matches_baseline": baseline_clean}),
                    )
                };
                let p = p
                    && rec["counters"]["whole_case"] == zero
                    && expected["native_calls_in_case"] == zero
                    && rec.get("A").is_none();
                mutations.push(json!({"id": spec.id, "kind": kind, "expected_detected_by": want, "reported": reported, "detail": detail,
                                      "counters": rec["counters"], "pass": p}));
                case_pass &= gate("MUTATION-DETECTED", p, detail, &mut gates);
            }
            other => {
                case_pass = false;
                gates.insert("FAMILY".into(), json!({"pass": false, "family": other}));
            }
        }
        if !case_pass {
            fail(format!(
                "case {} failed: {}",
                spec.id,
                Value::Object(gates.clone())
            ));
        }
        per_case.push(json!({"id": spec.id, "family": spec.family, "entry": d["composition"]["entry"], "outcome": rec["outcome"],
                             "gates": gates, "pass": case_pass}));
    }
    // N-COMP-ABA: seq-aba-2's A output equals seq-aba-0's A output, with
    // seq-aba-1 run between them (manifest order, one child).
    let order: Vec<&str> = manifest.cases.iter().map(|c| c.id.as_str()).collect();
    let pos = |id: &str| order.iter().position(|x| *x == id);
    let consecutive = matches!((pos("seq-aba-0"), pos("seq-aba-1"), pos("seq-aba-2")), (Some(a), Some(b), Some(c)) if b == a + 1 && c == b + 1);
    let aba = consecutive
        && matches!((outputs_a.get("seq-aba-0"), outputs_a.get("seq-aba-2")), (Some(x), Some(y)) if x == y && !x.is_empty())
        && records["seq-aba-1"]["outcome"] == "executed"
        && records["seq-aba-1"]["selection"]["identity"]["bits"]
            != records["seq-aba-0"]["selection"]["identity"]["bits"];
    tally("N-COMP-ABA", aba);
    if !aba {
        fail("N-COMP-ABA: seq-aba-2 A output differs from seq-aba-0 A output (or order/outcome wrong)".into());
    }

    // S-SOURCE-UNCHANGED evidence controls (implementation review r1 finding 1).
    if source_control_cases != 17 || !source_control_failures.is_empty() {
        fail(format!(
            "S-SOURCE-UNCHANGED evidence controls: {source_control_cases} cases, not rejected: {source_control_failures:?}"
        ));
    }
    // E6 in the compose child (contract C8; implementation review r1 finding
    // 2): the CPU-context negative control on a composed, staged plane is
    // refused R-DEVICE before any MLX-C numerical call or import. A control
    // like E4, not a manifest case: exactly one, and it must pass.
    let e6 = &report["e6_cpu_negative_control"];
    let e6_case = e6["case_id"].as_str().unwrap_or_default().to_string();
    let e6_oracle = docs
        .get(&e6_case)
        .map(|d| d["oracle"].clone())
        .unwrap_or(Value::Null);
    let e6_selection_ok = e6["selection"].is_object()
        && parent_mismatches(
            &e6["selection"],
            &e6_oracle["identity"],
            &e6_oracle["ranges"],
            &e6_oracle["sha256"],
        )
        .is_empty();
    let e6_pass = e6.is_object()
        && e6["context"] == "cpu"
        && docs
            .get(&e6_case)
            .is_some_and(|d| d["family"] == "FX-COMP-ACCEPT")
        && e6_selection_ok
        && e6["outcome"] == "refused"
        && e6["refusal_id"] == "R-DEVICE"
        && e6["stats"]["device_facts_gpu"] == false
        && e6["stats"]["numerical_calls_before_decision"] == 0
        && e6["stats"]["imports_before_decision"] == 0
        && counters_match(
            &e6["counters"],
            &json!({"imports": 0, "numerical_calls": 0, "result_handles_created": 0, "result_handles_adopted": 0, "result_handles_freed_on_error_path": 0, "array_free_calls": 0}),
        )
        && e6["cpu_context_live_arrays_after"] == 0;
    let controls = json!({
        "E6-CPU-REFUSED": {"cases": 1, "passed": e6_pass as usize, "record": e6, "selection_matches_oracle": e6_selection_ok},
        "S-SOURCE-UNCHANGED-evidence-controls": {"cases": source_control_cases, "controls_run": source_controls_run,
                                                  "not_rejected": source_control_failures},
    });
    if !e6_pass {
        fail(format!("E6-CPU-REFUSED in the compose child: {e6}"));
    }

    // Exact case-id accounting and every expected gate count, exactly.
    let by_family: BTreeMap<String, usize> =
        manifest.cases.iter().fold(BTreeMap::new(), |mut m, c| {
            *m.entry(c.family.clone()).or_default() += 1;
            m
        });
    if by_family.get("FX-COMP-ACCEPT") != Some(&11)
        || by_family.get("FX-COMP-SEQUENCE") != Some(&3)
        || by_family.get("FX-COMP-REFUSE") != Some(&9)
        || by_family.get("FX-COMP-INHERITED-REFUSE") != Some(&3)
        || by_family.get("FX-COMP-MUTATION") != Some(&6)
        || records.len() != fc::CASE_COUNT
    {
        fail(format!(
            "case accounting {by_family:?}, {} records",
            records.len()
        ));
    }
    let expect = [
        ("S-IDENTITY", 17),
        ("S-RANGES", 17),
        ("S-BYTES", 17),
        ("S-STAGED-EQUAL", 17),
        ("S-SOURCE-UNCHANGED", 17),
        ("E1-DEVICE", 17),
        ("N-COMP-ARRAYS", 14),
        ("N-QMM-SHAPE-DTYPE(A)", 14),
        ("N-QMM-SHAPE-DTYPE(B)", 14),
        ("N-COMP-AB", 14),
        ("G-QMM-RUST(A)", 14),
        ("G-QMM-RUST(B)", 14),
        ("G-QMM-EXACT(A)", 14),
        ("G-QMM-EXACT(B)", 14),
        ("G-R1-SELF-QMM(C)", 14),
        ("N-COMP-ABA", 1),
        ("C-R-REFUSAL", 9),
        ("INHERITED-REFUSAL", 3),
        ("MUTATION-DETECTED", 6),
    ];
    for (g, n) in expect {
        let got = counts.get(g).copied().unwrap_or((0, 0));
        if got != (n, n) {
            fail(format!("{g}: {}/{} passed, expected {n}/{n}", got.1, got.0));
        }
    }
    let unexpected_gates: Vec<&String> = counts
        .keys()
        .filter(|g| !expect.iter().any(|(e, _)| e == g))
        .collect();
    if !unexpected_gates.is_empty() {
        fail(format!("unexpected gates {unexpected_gates:?}"));
    }

    // 6. Independence (C7) and the population after the run.
    let static_ind = static_independence();
    let nm_ind = nm_independence();
    let handler = handler_coexistence();
    for (label, v) in [
        ("static source independence", &static_ind),
        ("nm symbol independence", &nm_ind),
        ("handler coexistence", &handler),
    ] {
        if v["pass"] != true {
            fail(format!("{label}: {v}"));
        }
    }
    let post = validate_population(&root, Some(&py_s));
    if post.is_err() {
        fail(format!(
            "population after the run: {:?}",
            post.as_ref().err()
        ));
    }

    let result = if failures.is_empty() { "PASS" } else { "FAIL" };
    let outcomes: BTreeMap<String, usize> = records.values().fold(BTreeMap::new(), |mut m, r| {
        *m.entry(r["outcome"].as_str().unwrap_or("?").to_string())
            .or_default() += 1;
        m
    });
    let summary = json!({
        "schema": fc::PARENT_SUMMARY_SCHEMA,
        "result": result,
        "host_label": host,
        "host_architecture": arch_host,
        "candidate_commit": candidate,
        "worktree_dirty": dirty,
        "frozen": {"contract_sha256": pre.contract_sha256, "plan_sha256": pre.plan_sha256,
                   "generator_sha256": pre.generator_sha256, "generator_test_sha256": pre.generator_test_sha256,
                   "manifest_sha256": pre.manifest_sha256, "files_listing_sha256": pre.files_listing_sha256,
                   "listed_file_count": pre.listed_file_count, "case_count": pre.case_count,
                   "checkpoint_files_checked": pre.checkpoint_files_checked, "standalone_files_checked": pre.standalone_files_checked,
                   "generator_check_before": pre.generator_check, "generator_test": gen_test.outcome.describe(),
                   "population_valid_after": post.is_ok(),
                   "slice2b": {"contract_sha256": pre.slice2b.contract_sha256, "plan_sha256": pre.slice2b.plan_sha256,
                               "source_pins_sha256": pre.slice2b.source_pins_sha256, "generator_sha256": pre.slice2b.generator_sha256,
                               "manifest_sha256": pre.slice2b.manifest_sha256, "cases_listing_sha256": pre.slice2b.cases_listing_sha256}},
        "child": {"outcome": run.outcome.describe(), "elapsed_ms": run.elapsed_ms, "timeout_seconds": mlx_native_affine::frozen::CHILD_TIMEOUT_SECONDS,
                  "report_sha256": report_sha, "abi_values": report["abi_values"], "error_handler": report["error_handler"],
                  "handles": report["handles"], "cleanup": report["cleanup"], "call_counts": report["call_counts"],
                  "canary_start": report["canary_start"], "canary_end": report["canary_end"]},
        "provenance": prov,
        "case_accounting": {"case_ids": records.len(), "by_family": by_family, "by_outcome": outcomes},
        "gate_counts": counts.iter().map(|(g, (n, p))| (g.clone(), json!({"cases": n, "passed": p}))).collect::<Map<_, _>>(),
        "worst_ratio_by_family_and_side": worst.iter().map(|(f, (n, r, e))| (f.clone(), json!({"cases": n, "rust_d_hi_over_B_lo": r, "exact_distance_over_bound": e}))).collect::<Map<_, _>>(),
        "a_vs_b": ab,
        "refusals": refusals,
        "mutations": mutations,
        "copy_accounting": copy,
        "independence": {"static_source": static_ind, "nm": nm_ind, "handler": handler},
        "controls": controls,
        "composition_gates_summary": exact["summary"],
        "cases": per_case,
        "failures": failures,
        "artifacts": {"child_report": "child/report.json", "rust_r1": "r1-rust.json", "composition_gates": "composition-gates.json"},
    });
    std::fs::write(
        out.join("summary.json"),
        serde_json::to_vec_pretty(&summary).unwrap(),
    )
    .unwrap();
    println!(
        "F020 Slice 2C composition qualification: {result} (summary {})",
        out.join("summary.json").display()
    );
    println!("{}", serde_json::to_string(&json!({"result": result, "gate_counts": summary["gate_counts"], "architecture": prov["architecture"]})).unwrap());
    assert!(
        failures.is_empty(),
        "composition qualification FAILED:\n{}",
        failures.join("\n")
    );
}

fn fc_mlx_version() -> &'static str {
    mlx_native_affine::frozen::MLX_VERSION
}

// ------------------------------------------------ required controls --

/// C7 (a): no child code path names R1 or the production decoder, no glob
/// import from `mlx_affine`, only `mlx_affine::{module, spec, error}`; the
/// scanner detects a planted control.
#[test]
fn child_independence_static_source() {
    let v = static_independence();
    println!("{}", serde_json::to_string_pretty(&v).unwrap());
    assert_eq!(v["pass"], true, "{v}");
}

/// C7 (b): `nm -a` of the built `qualify` executable has no R1/decoder
/// symbol, has the positive control, and the same scan of this parent
/// executable (which calls `reference_qmm`) finds the negative control.
#[test]
fn child_independence_nm_symbols() {
    if !native_built() {
        return;
    }
    let v = nm_independence();
    println!("{}", serde_json::to_string_pretty(&v).unwrap());
    // The negative control's premise: this test executable links R1 because
    // the qualification test above calls `qmm_reference` on C.
    assert_eq!(v["pass"], true, "{v}");
}

/// C7: one mlx_set_error_handler call site (the child's Once), none in any
/// newly linked crate; the library crate stays `#![forbid(unsafe_code)]` and
/// names no MLX-C symbol.
#[test]
fn handler_coexistence_and_mlx_free_library() {
    let v = handler_coexistence();
    assert_eq!(v["pass"], true, "{v}");
    let lib = std::fs::read_to_string(crate_dir().join("src/lib.rs")).unwrap();
    assert!(lib.contains("#![forbid(unsafe_code)]"));
    for f in ["src/compose.rs", "src/frozen_compose.rs"] {
        let text: String = std::fs::read_to_string(crate_dir().join(f))
            .unwrap()
            .lines()
            .filter(|l| !l.trim_start().starts_with("//"))
            .collect::<Vec<_>>()
            .join("\n");
        for bad in [
            "mlx_array",
            "mlx_quantized_matmul",
            "extern \"C\"",
            "unsafe",
            "transmute",
            "align_to",
            "from_raw_parts",
            "as *const",
        ] {
            assert!(!text.contains(bad), "{f} contains {bad}");
        }
    }
}

/// I-PLANE-SINGLE-INDEX, required sealed-plane interface test (plan section
/// 2.2): (1) an API audit of `compose.rs`; (2) every public entry driven with
/// every mixing the fixtures allow; (3) no `compile_fail` doctest exists.
#[test]
fn sealed_plane_interface() {
    let src = std::fs::read_to_string(crate_dir().join("src/compose.rs")).unwrap();
    // (1) API audit.
    let start = src
        .find("pub struct SelectedPlane<'b> {")
        .expect("SelectedPlane");
    let body = &src[start..start + src[start..].find("\n}").unwrap()];
    for line in body.lines().skip(1) {
        let t = line.trim();
        assert!(!t.starts_with("pub"), "public field in SelectedPlane: {t}");
    }
    let attrs: Vec<&str> = src[..start]
        .lines()
        .rev()
        .take_while(|l| l.trim_start().starts_with("///") || l.trim_start().starts_with("#["))
        .collect();
    assert!(
        attrs.iter().all(|l| !l.contains("derive")),
        "SelectedPlane derives something: {attrs:?}"
    );
    for bad in [
        "impl Clone for SelectedPlane",
        "impl Default for SelectedPlane",
        "impl<'b> Clone for SelectedPlane",
        "impl<'b> Default for SelectedPlane",
    ] {
        assert!(!src.contains(bad), "{bad}");
    }
    assert_eq!(
        src.matches("SelectedPlane {\n        identity").count(),
        1,
        "exactly one construction site"
    );
    // Every public function signature.
    let mut returning = Vec::new();
    let mut rest = src.as_str();
    while let Some(at) = rest.find("pub fn ") {
        let tail = &rest[at..];
        let sig = &tail[..tail.find('{').unwrap()];
        let name: String = sig["pub fn ".len()..]
            .chars()
            .take_while(|c| c.is_alphanumeric() || *c == '_')
            .collect();
        let (params, ret) = match sig.find("->") {
            Some(i) => (&sig[..i], &sig[i..]),
            None => (sig, ""),
        };
        if ret.contains("SelectedPlane") {
            returning.push((name.clone(), params.to_string()));
        }
        for component in ["ByteSlice", "TripleSlice", "&[u8]", "PlaneRange"] {
            if params.contains(component) {
                assert!(
                    !ret.contains("SelectedPlane") && !params.contains("&mut SelectedPlane"),
                    "{name} takes {component} and returns or modifies a plane"
                );
            }
        }
        assert!(
            !params.contains("&mut SelectedPlane"),
            "{name} modifies a plane"
        );
        rest = &tail["pub fn ".len()..];
    }
    let names: BTreeSet<&str> = returning.iter().map(|(n, _)| n.as_str()).collect();
    assert_eq!(
        names,
        BTreeSet::from(["compose", "select_plane"]),
        "{returning:?}"
    );
    for (name, params) in &returning {
        assert_eq!(
            params.matches("&[u64]").count(),
            1,
            "{name}: exactly one index path"
        );
        match name.as_str() {
            "select_plane" => assert_eq!(params.matches("&AffineTriple").count(), 1, "one triple"),
            "compose" => assert_eq!(params.matches("module: &str").count(), 1, "one module path"),
            _ => unreachable!(),
        }
    }
    // No &mut self in any impl of SelectedPlane.
    let mut rest = src.as_str();
    while let Some(at) = rest
        .find("impl SelectedPlane")
        .or_else(|| rest.find("impl<'b> SelectedPlane"))
    {
        let tail = &rest[at..];
        let end = tail.find("\n}\n").unwrap();
        assert!(
            !tail[..end].contains("&mut self"),
            "&mut self on SelectedPlane"
        );
        rest = &tail[end..];
    }
    // (3) no compile_fail doctest anywhere in the crate's sources.
    for f in child_source_files().iter().chain(
        [
            crate_dir().join("src/lib.rs"),
            crate_dir().join("src/harness.rs"),
        ]
        .iter(),
    ) {
        assert!(
            !std::fs::read_to_string(f).unwrap().contains("compile_fail"),
            "{}",
            f.display()
        );
    }

    // (2) Every public entry, run with every mixing the fixtures allow.
    let root = repo_root();
    let fx = fc::fixture_dir(&root);
    let raw = std::fs::read(root.join(fc::MANIFEST_PATH)).unwrap();
    let doc = fc::manifest_document(&raw).unwrap();
    let cfg = |ck: &str| {
        std::fs::read_to_string(fx.join(format!("checkpoints/{ck}/config.json"))).unwrap()
    };
    let none = BTreeMap::new();
    let a = Source::open(
        &fx.join("checkpoints/ck-a-single"),
        &cfg("ck-a-single"),
        &none,
    )
    .unwrap();
    let sibling = Backing::open(&fx.join("checkpoints/ck-a-sibling"), &none).unwrap();
    let cat = a.checkpoint().catalog();
    let m = |n: &str| cat.get(n).unwrap().clone();
    let spec = |b: u32, g: u32| {
        QuantSpec::new(
            Bits::from_u32(b).unwrap(),
            GroupSize::from_u32(g).unwrap(),
            Mode::Affine,
        )
    };
    // weight and companions from two modules through AffineTriple::new.
    let mixed = AffineTriple::new(
        "block.0.stack_a",
        m("block.0.stack_a.weight"),
        m("block.0.stack_b.scales"),
        m("block.0.stack_b.biases"),
        spec(4, 64),
    )
    .unwrap();
    let r = select_plane(a.checkpoint(), a.backing(), a.config(), &mixed, &[1])
        .err()
        .unwrap();
    assert_eq!(r.id, CompositionRefusalId::ModuleBinding, "{r}");
    let mixed2 = AffineTriple::new(
        "block.0.stack_b",
        m("block.0.stack_a.weight"),
        m("block.0.stack_b.scales"),
        m("block.0.stack_b.biases"),
        spec(4, 64),
    )
    .unwrap();
    let r = select_plane(a.checkpoint(), a.backing(), a.config(), &mixed2, &[1])
        .err()
        .unwrap();
    assert_eq!(r.id, CompositionRefusalId::ModuleBinding, "{r}");
    // The module's own descriptors with a shape-consistent other recipe.
    let recipe = AffineTriple::new(
        "block.0.stack_a",
        m("block.0.stack_a.weight"),
        m("block.0.stack_a.scales"),
        m("block.0.stack_a.biases"),
        spec(8, 32),
    )
    .unwrap();
    let r = select_plane(a.checkpoint(), a.backing(), a.config(), &recipe, &[1])
        .err()
        .unwrap();
    assert_eq!(r.id, CompositionRefusalId::RecipeBinding, "{r}");
    // A triple from one source with a backing from another.
    let own = match classify_module(cat, Some(a.config()), "block.0.stack_a").unwrap() {
        ModuleKind::Quantized(t) => *t,
        _ => panic!("quantized"),
    };
    let r = select_plane(a.checkpoint(), &sibling, a.config(), &own, &[1])
        .err()
        .unwrap();
    assert_eq!(r.id, CompositionRefusalId::SourceBinding, "{r}");
    // Accepted through E-SELECT with the authority's own triple.
    let p = select_plane(a.checkpoint(), a.backing(), a.config(), &own, &[1]).unwrap();
    assert_eq!(p.identity().index_path, vec![1]);
    // Every accepted case through E-COMPOSE: the three ranges are the
    // oracle's ranges of the ONE requested index, and every component's bytes
    // are that expert's and no other expert's (manifest expert_sha256).
    let mut sources: BTreeMap<String, Source> = BTreeMap::new();
    let mut checked = 0;
    for c in doc["cases"].as_array().unwrap() {
        if c["expected"]["outcome"] != "accept" {
            continue;
        }
        let comp = &c["composition"];
        let ckrel = comp["checkpoint"].as_str().unwrap();
        let ck = ckrel.trim_start_matches("checkpoints/");
        let src = sources.entry(ck.to_string()).or_insert_with(|| {
            Source::open(
                &fx.join(ckrel),
                &std::fs::read_to_string(fx.join(comp["config"].as_str().unwrap())).unwrap(),
                &none,
            )
            .unwrap()
        });
        let module = comp["module"].as_str().unwrap();
        let idx: Vec<u64> = comp["index_path"]
            .as_array()
            .unwrap()
            .iter()
            .map(|v| v.as_u64().unwrap())
            .collect();
        let plane = compose(src, module, &idx).unwrap();
        let rec = plane.record().to_json();
        assert_eq!(rec["ranges"], c["oracle"]["ranges"], "{}", c["id"]);
        assert_eq!(rec["identity"], c["oracle"]["identity"], "{}", c["id"]);
        let experts = doc["checkpoints"][ck]["modules"][module]["expert_sha256"]
            .as_array()
            .unwrap();
        for comp_name in COMPONENTS {
            let got = &rec["sha256"][comp_name];
            for (e, ex) in experts.iter().enumerate() {
                assert_eq!(
                    got == &ex[comp_name],
                    e as u64 == idx[0],
                    "{} {comp_name} expert {e}",
                    c["id"]
                );
            }
        }
        // Staging copies exactly the plane's bytes, never widened.
        let [w, s, b] = stage(&plane).unwrap();
        assert_eq!(
            (w.dtype, s.dtype, b.dtype),
            (Dtype::U32, Dtype::BF16, Dtype::BF16)
        );
        let lens: Vec<u64> = COMPONENTS
            .iter()
            .map(|k| rec["ranges"][k]["len"].as_u64().unwrap())
            .collect();
        assert_eq!(
            vec![
                w.bytes.len() as u64,
                s.bytes.len() as u64,
                b.bytes.len() as u64
            ],
            lens
        );
        checked += 1;
    }
    assert_eq!(checked, 14);
}

/// S-SOURCE-UNCHANGED evidence controls (implementation review r1 finding
/// 1) on synthetic records built from the manifest's own expectations: the
/// exact record is accepted; a duplicate backing record replacing another
/// shard, a missing or extra shard, absent evidence and a window are all
/// rejected, in both the after-selection and after-execution phases.
#[test]
fn source_unchanged_evidence_controls() {
    let raw = std::fs::read(repo_root().join(fc::MANIFEST_PATH)).unwrap();
    let doc = fc::manifest_document(&raw).unwrap();
    let docs = fc::case_documents(&doc);
    let mut checked = 0;
    for id in [
        "acc-b-stack_d-e0-m32",
        "acc-a-stack_a-e0-m1",
        "inh-meta-range-e1",
    ] {
        let d = &docs[id];
        let exp = &d["expected"]["source_hashes"];
        let ck = d["composition"]["checkpoint"]
            .as_str()
            .unwrap()
            .trim_start_matches("checkpoints/");
        let lens: BTreeMap<String, u64> = doc["checkpoints"][ck]["files"]
            .as_object()
            .unwrap()
            .iter()
            .map(|(k, v)| (k.clone(), v["bytes"].as_u64().unwrap()))
            .collect();
        let backing: Vec<Value> = exp["shards"]
            .as_object()
            .unwrap()
            .iter()
            .map(|(n, h)| json!({"shard": n, "sha256": h, "file_sha256_at_load": h, "len": lens[n], "file_len": lens[n], "window": false}))
            .collect();
        let rec = json!({"source_hashes": {
            "before_load": {"shards": exp["shards"], "standalone": exp["standalone"]},
            "after_host_selection": {"shards": exp["shards"], "backing": backing},
            "after_native_execution": {"shards": exp["shards"], "backing": backing, "standalone": exp["standalone"]},
        }});
        let ctl = source_evidence_controls(&rec, exp, &lens);
        let multi = exp["shards"].as_object().unwrap().len() >= 2;
        for (label, ok) in &ctl {
            assert!(ok, "{id}: {label}");
        }
        let duplicate_controls = ctl.iter().filter(|(l, _)| l.contains("duplicate")).count();
        assert_eq!(duplicate_controls, if multi { 4 } else { 0 }, "{id}");
        println!(
            "{id}: {} controls, all rejected (valid record accepted)",
            ctl.len() - 1
        );
        checked += 1;
    }
    assert_eq!(checked, 3);
}

/// Harness extraction regression (plan section 2.3) and composition report
/// validation: every acceptance rule of `accept_compose_report` rejects its
/// defect with the intended error, and a clean skeleton is accepted.
#[test]
fn compose_report_acceptance_rules() {
    let ids = manifest_ids();
    assert_eq!(ids.len(), fc::CASE_COUNT);
    let dir = fresh(&out_root().join("report-rules"));
    let ok_run = ChildRun {
        outcome: ChildOutcome::Exited(0),
        elapsed_ms: 1,
        stdout_path: dir.join("o"),
        stderr_path: dir.join("e"),
    };
    let skeleton = || {
        json!({
            "schema": fc::CHILD_REPORT_SCHEMA,
            "contract_sha256": fc::CONTRACT_SHA256,
            "manifest_sha256": fc::MANIFEST_SHA256,
            "generator_sha256": fc::GENERATOR_SHA256,
            "slice2b_contract_sha256": fc::SLICE2B_CONTRACT_SHA256,
            "completed": true,
            "test_fault": null,
            "cleanup": {"errors": [], "result_handles": {"balanced": true}},
            "handles": {"live_array_handles_after_context_drop": 0, "live_arrays_in_context_at_drop": 0, "double_free_attempts": 0},
            "cases": ids.iter().map(|i| json!({"id": i})).collect::<Vec<_>>(),
        })
    };
    let check = |name: &str, v: &Value, run: &ChildRun| {
        let p = dir.join(format!("{name}.json"));
        std::fs::write(&p, serde_json::to_vec(v).unwrap()).unwrap();
        accept_compose_report(run, &p, &ids)
    };
    assert!(check("ok", &skeleton(), &ok_run).is_ok());
    let failed_run = ChildRun {
        outcome: ChildOutcome::Timeout {
            elapsed_ms: 5,
            reaped_signal: Some(9),
        },
        ..ok_run.clone()
    };
    assert!(
        matches!(check("timeout", &skeleton(), &failed_run), Err(ReportError::ChildFailed(m)) if m.starts_with("TIMEOUT"))
    );
    assert!(matches!(
        accept_compose_report(&ok_run, &dir.join("absent.json"), &ids),
        Err(ReportError::Missing(_))
    ));
    std::fs::write(dir.join("garbage.json"), b"{ not json").unwrap();
    assert!(matches!(
        accept_compose_report(&ok_run, &dir.join("garbage.json"), &ids),
        Err(ReportError::Unparsable(_))
    ));
    let mut v = skeleton();
    v["schema"] = json!(mlx_native_affine::frozen::CHILD_REPORT_SCHEMA);
    assert!(
        matches!(check("schema", &v, &ok_run), Err(ReportError::Schema(_))),
        "a Slice 2B report is not a Slice 2C report"
    );
    for key in [
        "contract_sha256",
        "manifest_sha256",
        "generator_sha256",
        "slice2b_contract_sha256",
    ] {
        let mut v = skeleton();
        v[key] = json!("0".repeat(64));
        assert!(
            matches!(check(key, &v, &ok_run), Err(ReportError::HashEcho(_))),
            "{key}"
        );
    }
    let mut v = skeleton();
    v["completed"] = json!(false);
    assert!(matches!(
        check("incomplete", &v, &ok_run),
        Err(ReportError::Incomplete(_))
    ));
    let mut v = skeleton();
    v["cleanup"]["errors"] = json!([{"call": "mlx_array_free"}]);
    assert!(matches!(
        check("cleanup", &v, &ok_run),
        Err(ReportError::Cleanup(_))
    ));
    let mut v = skeleton();
    v["handles"]["live_arrays_in_context_at_drop"] = json!(1);
    assert!(matches!(
        check("handles", &v, &ok_run),
        Err(ReportError::HandleCensus(_))
    ));
    let mut v = skeleton();
    v["test_fault"] = json!("abort");
    assert!(matches!(
        check("fault", &v, &ok_run),
        Err(ReportError::TestFault(_))
    ));
    let mut v = skeleton();
    v["cases"].as_array_mut().unwrap().pop();
    assert!(
        matches!(check("missing", &v, &ok_run), Err(ReportError::CaseSet { missing, .. }) if missing.len() == 1)
    );
    let mut v = skeleton();
    v["cases"]
        .as_array_mut()
        .unwrap()
        .push(json!({"id": "acc-a-stack_a-e0-m1"}));
    assert!(
        matches!(check("dup", &v, &ok_run), Err(ReportError::CaseSet { duplicated, .. }) if duplicated.len() == 1)
    );
    let mut v = skeleton();
    v["cases"]
        .as_array_mut()
        .unwrap()
        .push(json!({"id": "not-a-case"}));
    assert!(
        matches!(check("unexpected", &v, &ok_run), Err(ReportError::CaseSet { unexpected, .. }) if unexpected.len() == 1)
    );
}

/// Manifest/generator validation controls: the frozen population validates,
/// and a tampered copy (a changed standalone byte, a changed checkpoint byte,
/// an extra file, a changed manifest byte) is refused.
#[test]
fn composition_population_validation_controls() {
    let src = repo_root();
    validate_population(&src, None).expect("the committed population validates");
    let base = fresh(&out_root().join("tampered-population"));
    let copy_tree = |from: &Path, to: &Path| {
        let mut stack = vec![PathBuf::new()];
        while let Some(rel) = stack.pop() {
            std::fs::create_dir_all(to.join(&rel)).unwrap();
            for e in std::fs::read_dir(from.join(&rel)).unwrap() {
                let e = e.unwrap();
                let r = rel.join(e.file_name());
                if e.file_type().unwrap().is_dir() {
                    stack.push(r);
                } else {
                    std::fs::copy(from.join(&r), to.join(&r)).unwrap();
                }
            }
        }
    };
    let make = |label: &str| -> PathBuf {
        let root = fresh(&base.join(label));
        for rel in [
            mlx_native_affine::frozen::CONTRACT_PATH,
            mlx_native_affine::frozen::PLAN_PATH,
            mlx_native_affine::frozen::SOURCE_PINS_PATH,
            mlx_native_affine::frozen::GENERATOR_PATH,
            fc::CONTRACT_PATH,
            fc::PLAN_PATH,
            fc::GENERATOR_PATH,
            fc::GENERATOR_TEST_PATH,
        ] {
            let to = root.join(rel);
            std::fs::create_dir_all(to.parent().unwrap()).unwrap();
            std::fs::copy(src.join(rel), &to).unwrap();
        }
        copy_tree(
            &src.join(mlx_native_affine::frozen::FIXTURE_DIR),
            &root.join(mlx_native_affine::frozen::FIXTURE_DIR),
        );
        copy_tree(&src.join(fc::FIXTURE_DIR), &root.join(fc::FIXTURE_DIR));
        root
    };
    let clean = make("clean");
    validate_population(&clean, None).expect("an exact copy validates");
    let flip = |p: &Path| {
        let mut b = std::fs::read(p).unwrap();
        let i = b.len() / 2;
        b[i] ^= 1;
        std::fs::write(p, b).unwrap();
    };
    let r = make("standalone");
    flip(
        &r.join(fc::FIXTURE_DIR)
            .join("standalone/acc-a-stack_a-e0-m1.bin"),
    );
    assert!(
        validate_population(&r, None).is_err(),
        "changed standalone byte"
    );
    let r = make("checkpoint");
    flip(
        &r.join(fc::FIXTURE_DIR)
            .join("checkpoints/ck-b-sharded/model-00002-of-00003.safetensors"),
    );
    assert!(
        validate_population(&r, None).is_err(),
        "changed checkpoint byte"
    );
    let r = make("extra");
    std::fs::write(r.join(fc::FIXTURE_DIR).join("standalone/extra.bin"), b"x").unwrap();
    assert!(validate_population(&r, None).is_err(), "extra file");
    let r = make("extra-top");
    std::fs::write(r.join(fc::FIXTURE_DIR).join("notes.txt"), b"x").unwrap();
    assert!(
        validate_population(&r, None).is_err(),
        "extra top-level entry"
    );
    let r = make("manifest");
    let mp = r.join(fc::MANIFEST_PATH);
    let mut b = std::fs::read(&mp).unwrap();
    let n = b.len() - 2;
    b[n] = b' ';
    std::fs::write(&mp, b).unwrap();
    assert!(
        validate_population(&r, None).is_err(),
        "changed manifest byte"
    );
    let r = make("slice2b");
    flip(
        &r.join(mlx_native_affine::frozen::FIXTURE_DIR)
            .join("cases/dq-codes-b8-g64-bf16.bin"),
    );
    assert!(
        validate_population(&r, None).is_err(),
        "changed Slice 2B case byte"
    );
}

/// Composition-mode failure paths (inherited watchdog/no-retry/cleanup
/// rules): the parent reports each as a failure with the intended error.
#[test]
fn composition_child_failure_paths_are_failures() {
    if !native_built() {
        return;
    }
    let ids = manifest_ids();
    let out = fresh(&out_root().join("faults"));
    let (run, dir) = compose_run(
        &out,
        "abort",
        &["--test-fault", "abort"],
        Duration::from_secs(120),
    );
    assert_eq!(run.outcome, ChildOutcome::Signaled(6), "abort");
    assert!(matches!(
        accept_compose_report(&run, &dir.join("report.json"), &ids),
        Err(ReportError::ChildFailed(_))
    ));
    let (run, dir) = compose_run(
        &out,
        "hang",
        &["--test-fault", "hang"],
        Duration::from_secs(5),
    );
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
    assert!(
        matches!(accept_compose_report(&run, &dir.join("report.json"), &ids), Err(ReportError::ChildFailed(ref m)) if m.starts_with("TIMEOUT"))
    );
    let (run, dir) = compose_run(
        &out,
        "no-report",
        &["--test-fault", "no-report"],
        Duration::from_secs(120),
    );
    assert_eq!(run.outcome, ChildOutcome::Exited(0));
    assert!(matches!(
        accept_compose_report(&run, &dir.join("report.json"), &ids),
        Err(ReportError::Missing(_))
    ));
    for (kind, call) in [
        ("cleanup-free", "mlx_array_free (NativeArray drop)"),
        ("cleanup-sync", "mlx_synchronize (context teardown)"),
    ] {
        let (run, dir) = compose_run(&out, kind, &["--test-fault", kind], frozen_timeout());
        assert_eq!(run.outcome, ChildOutcome::Exited(0), "{kind}");
        match accept_compose_report(&run, &dir.join("report.json"), &ids) {
            Err(ReportError::Cleanup(errors)) => assert!(
                errors
                    .iter()
                    .any(|e| e.contains(call) && e.contains("injected cleanup failure")),
                "{kind}: {errors:?}"
            ),
            other => panic!("{kind}: expected a cleanup failure, got {other:?}"),
        }
    }
}
