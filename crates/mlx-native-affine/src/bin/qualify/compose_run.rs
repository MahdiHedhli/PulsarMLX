//! `--mode compose`: the F020 Slice 2C composition child (slice2c-plan.md
//! section 3).
//!
//! Start sequence exactly as the Slice 2B child: the R-NAX environment
//! assertion (in `main`, before any MLX-C call), ABI verification, the single
//! error handler, the default device set to GPU, provenance (E3) and the E4
//! canary (the unchanged Slice 2B canary on the Slice 2B population); E6 (the
//! CPU-context negative control) runs on a composed plane after the cases. Then the
//! frozen Slice 2C files are read against `frozen_compose`, one
//! `NativeContext` is opened, every manifest case runs in manifest order (the
//! three `seq-aba-*` cases are consecutive in the manifest), the canary runs
//! again, the context is torn down and the report is written atomically.
//!
//! Per case the child composes (E-COMPOSE, E-SELECT or E-RANGE, as the
//! manifest's `composition.entry` says), records any composition refusal with
//! its counter deltas, runs the selection checks against the manifest's oracle
//! before any native call, stages side A from the plane and side B from the
//! standalone file, records the staged-input evidence of both sides, then runs
//! A and B through the EXISTING `bridge::quantized_matmul` with a separate
//! counter interval around each call. It records outputs, counters and the
//! phase-labelled source/backing hashes. It decides nothing that needs R1 and
//! never decides N-COMP-AB: the parent re-decides every check from these
//! records.
//!
//! No FFI, bridge, QMM or handler code lives here: this module only calls
//! `bridge`, `native`, `ffi::call_counts`, `provenance` and `run`'s canary and
//! report helpers, all unchanged.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

use mlx_affine::module::AffineTriple;
use mlx_affine::spec::{Bits, GroupSize, Mode, QuantSpec};
use mlx_native_affine::compose::{
    compose as compose_plane, resolve_range, select_plane, selection_mismatches, stage, Backing,
    CompositionRefusal, SelectedPlane, SelectionRecord, Source, COMPONENTS,
};
use mlx_native_affine::family::{self, parse_architecture, Architecture};
use mlx_native_affine::fixture::{load_case, parse_manifest, sha256_hex, CaseSpec, HostTensor};
use mlx_native_affine::frozen;
use mlx_native_affine::frozen_compose;
use serde_json::{json, Map, Value};

use crate::bridge::{self, BridgeError};
use crate::ffi;
use crate::native::{self, DeviceKind, NativeContext};
use crate::provenance;
use crate::run::{canary, cleanup_json, read_frozen, redact, stats_json, write_atomic, Ctx};
use crate::Args;

struct ComposeCtx {
    fixture_dir: PathBuf,
    out_dir: PathBuf,
    arch: Architecture,
}

/// All counters the bridge-visible accounting reads, at one instant.
#[derive(Clone, Copy)]
struct Snapshot {
    numerical: u64,
    imports: u64,
    created: u64,
    adopted: u64,
    error_freed: u64,
    frees: u64,
}

fn snapshot() -> Snapshot {
    let (numerical, imports) = ffi::call_counts();
    let (created, adopted, error_freed) = native::result_census();
    Snapshot {
        numerical,
        imports,
        created,
        adopted,
        error_freed,
        frees: native::array_free_calls(),
    }
}

fn delta(a: Snapshot, b: Snapshot) -> Value {
    json!({
        "imports": b.imports - a.imports,
        "result_handles_created": b.created - a.created,
        "result_handles_adopted": b.adopted - a.adopted,
        "result_handles_freed_on_error_path": b.error_freed - a.error_freed,
        "array_free_calls": b.frees - a.frees,
        "numerical_calls": b.numerical - a.numerical,
    })
}

fn calls(a: Snapshot, b: Snapshot) -> Value {
    json!({"numerical": b.numerical - a.numerical, "imports": b.imports - a.imports})
}

fn staged_record(t: &HostTensor) -> Value {
    json!({
        "dtype": t.dtype.name(),
        "shape": t.shape,
        "nbytes": t.bytes.len(),
        "sha256": sha256_hex(&t.bytes),
    })
}

fn staged_records(x: &HostTensor, w: &HostTensor, s: &HostTensor, b: &HostTensor) -> Value {
    json!({
        "x": staged_record(x),
        "w": staged_record(w),
        "scales": staged_record(s),
        "biases": staged_record(b),
    })
}

/// sha256 of every `*.safetensors` file in a checkpoint directory, read
/// straight from disk (not through the backing), by file name.
fn shard_file_hashes(dir: &Path) -> Result<Map<String, Value>, String> {
    let mut names = Vec::new();
    for e in std::fs::read_dir(dir).map_err(|e| format!("{}: {e}", dir.display()))? {
        let e = e.map_err(|e| e.to_string())?;
        let name = e.file_name().to_string_lossy().into_owned();
        if name.ends_with(".safetensors") {
            names.push(name);
        }
    }
    names.sort();
    let mut out = Map::new();
    for n in names {
        let data = std::fs::read(dir.join(&n)).map_err(|e| format!("{n}: {e}"))?;
        out.insert(n, Value::String(sha256_hex(&data)));
    }
    Ok(out)
}

fn file_hash(dir: &Path, rel: &str) -> Result<Value, String> {
    let data = std::fs::read(dir.join(rel)).map_err(|e| format!("{rel}: {e}"))?;
    Ok(json!({ rel: sha256_hex(&data) }))
}

fn str_of<'a>(v: &'a Value, what: &str) -> Result<&'a str, String> {
    v.as_str()
        .ok_or_else(|| format!("manifest: {what} is not a string"))
}

fn index_path(v: &Value) -> Result<Vec<u64>, String> {
    v.as_array()
        .ok_or("manifest: index_path")?
        .iter()
        .map(|i| i.as_u64().ok_or_else(|| format!("manifest: index {i}")))
        .collect()
}

fn windows(v: &Value) -> Result<BTreeMap<String, u64>, String> {
    let mut out = BTreeMap::new();
    if let Some(m) = v.as_object() {
        for (k, w) in m {
            out.insert(
                k.clone(),
                w.as_u64().ok_or_else(|| format!("manifest: window {k}"))?,
            );
        }
    }
    Ok(out)
}

fn read_text(dir: &Path, rel: &str) -> Result<String, String> {
    std::fs::read_to_string(dir.join(rel)).map_err(|e| format!("{rel}: {e}"))
}

fn refusal_json(r: &CompositionRefusal) -> Value {
    let mut v = r.to_json();
    v["detail"] = Value::String(redact(&r.detail));
    v
}

/// The test-only mutator (plan section 3 step 3; planner resolution 5): it
/// operates on a SELECTION RECORD, never on a plane. It replaces the ranges
/// and/or identity exactly as `composition.mutation` specifies, reads the
/// bytes at the mutated ranges from the backing and hashes them.
fn apply_mutation(
    record: &SelectionRecord,
    mutation: &Value,
    backing: &Backing,
) -> Result<(Value, Value), String> {
    let mut mutated = record.to_json();
    let mut applied = Map::new();
    if let Some(ranges) = mutation.get("ranges").and_then(Value::as_object) {
        for c in COMPONENTS {
            let r = ranges.get(c).ok_or_else(|| format!("mutation range {c}"))?;
            let shard = str_of(&r["shard"], "mutation shard")?;
            let begin = r["begin"].as_u64().ok_or("mutation begin")?;
            let len = r["len"].as_u64().ok_or("mutation len")?;
            let bytes = resolve_range(backing, shard, begin, len)
                .map_err(|e| format!("mutated range {c}: {e}"))?;
            mutated["ranges"][c] = json!({"shard": shard, "begin": begin, "len": len});
            mutated["sha256"][c] = Value::String(sha256_hex(bytes));
        }
        applied.insert(
            "ranges_equal_manifest".into(),
            json!(mutated["ranges"] == mutation["ranges"]),
        );
        applied.insert(
            "sha256_equal_manifest".into(),
            json!(mutated["sha256"] == mutation["sha256"]),
        );
    }
    if let Some(identity) = mutation.get("identity") {
        mutated["identity"] = identity.clone();
        applied.insert(
            "identity_equal_manifest".into(),
            json!(&mutated["identity"] == identity),
        );
    }
    if applied.is_empty() {
        return Err(format!("mutation {mutation} replaces nothing"));
    }
    Ok((mutated, Value::Object(applied)))
}

fn output_json(
    cx: &ComposeCtx,
    id: &str,
    side: &str,
    copy: &native::HostCopy,
) -> Result<Value, String> {
    let rel = format!("outputs/{id}.{side}.bin");
    std::fs::write(cx.out_dir.join(&rel), &copy.bytes).map_err(|e| format!("{rel}: {e}"))?;
    Ok(json!({
        "file": rel,
        "sha256": sha256_hex(&copy.bytes),
        "dtype": copy.dtype.name(),
        "shape": copy.shape,
        "nbytes": copy.bytes.len(),
    }))
}

/// One side (A or B) through the EXISTING bridge entry, inside its own
/// counter interval: opened immediately before and closed immediately after
/// `bridge::quantized_matmul` (which evaluates, reads back and drops every
/// handle before it returns).
#[allow(clippy::too_many_arguments)]
fn run_side(
    cx: &ComposeCtx,
    gpu: &NativeContext,
    id: &str,
    side: &str,
    x: &HostTensor,
    w: &HostTensor,
    s: &HostTensor,
    b: &HostTensor,
    bits: u32,
    group: u32,
) -> Result<Value, String> {
    let before = snapshot();
    let r = bridge::quantized_matmul(gpu, x, w, s, b, bits, group);
    let after = snapshot();
    let interval = delta(before, after);
    Ok(match r {
        Ok((g, copy, stats)) => {
            let derived =
                family::derive(g.m_eff, g.n, g.k, g.group_size as usize, g.bits, &cx.arch);
            let cands = family::candidates(g.m_eff, g.n, g.k, g.group_size as usize, g.bits);
            let bound_n = family::bound_exponent(g.m_eff, g.n, g.k, g.group_size as usize, g.bits);
            let mut want_shape = x.shape[..x.shape.len() - 1].to_vec();
            want_shape.push(g.n);
            json!({
                "side": side, "outcome": "executed",
                "bits": bits, "group_size": group,
                "geometry": {"x_shape": x.shape, "M_eff": g.m_eff, "N": g.n, "K": g.k, "bits": g.bits,
                             "group_size": g.group_size, "metadata_dtype": g.meta.name(), "x_dtype": "F32", "transpose": true},
                "kernel": {
                    "architecture": cx.arch.name,
                    "batch_limit_L": derived.batch_limit,
                    "split_k": derived.split_k,
                    "derived_family": derived.family.as_str(),
                    "derived_family_gamma_n": derived.family_gamma_n,
                    "candidate_families": cands.iter().map(|c| json!({"family": c.family.as_str(), "split_k": c.split_k, "gamma_n": c.gamma_n})).collect::<Vec<_>>(),
                    "bound_gamma_n": bound_n,
                    "architecture_dependent_band": (6..=31).contains(&g.m_eff),
                },
                "metadata_cast": "bridge mlx_astype to float32 on the GPU stream",
                "structural": {"dtype_equal": copy.dtype == mlx_native_affine::dtype::Dtype::F32, "shape_equal": copy.shape == want_shape},
                "output": output_json(cx, id, side, &copy)?,
                "stats": stats_json(&stats),
                "counters": interval,
            })
        }
        Err((BridgeError::Refused(rid), stats)) => json!({
            "side": side, "outcome": "refused", "refusal_id": rid.as_str(),
            "bits": bits, "group_size": group,
            "stats": stats_json(&stats), "counters": interval,
        }),
        Err((BridgeError::Native(n), stats)) => json!({
            "side": side, "outcome": "error", "error": redact(&n.to_string()),
            "stats": stats_json(&stats), "counters": interval,
        }),
    })
}

fn run_case(cx: &ComposeCtx, gpu: &NativeContext, spec: &CaseSpec, doc: &Value) -> Value {
    match run_case_inner(cx, gpu, spec, doc) {
        Ok(v) => v,
        Err(e) => {
            json!({"id": spec.id, "manifest_family": spec.family, "outcome": "error", "error": redact(&e)})
        }
    }
}

fn run_case_inner(
    cx: &ComposeCtx,
    gpu: &NativeContext,
    spec: &CaseSpec,
    doc: &Value,
) -> Result<Value, String> {
    let c0 = snapshot();
    let comp = &doc["composition"];
    let entry = str_of(&comp["entry"], "composition.entry")?;
    let ck_rel = str_of(&comp["checkpoint"], "composition.checkpoint")?;
    let ck_dir = cx.fixture_dir.join(ck_rel);
    let backing_rel = str_of(
        &comp["backing"]["checkpoint"],
        "composition.backing.checkpoint",
    )?;
    let backing_dir = cx.fixture_dir.join(backing_rel);
    let wins = windows(&comp["backing"]["windows"])?;
    let module = str_of(&comp["module"], "composition.module")?;
    let idx = index_path(&comp["index_path"])?;
    let mutation = comp.get("mutation");
    let mutation_kind = mutation.and_then(|m| m["kind"].as_str());
    let config_rel = match mutation.and_then(|m| m["config"].as_str()) {
        // override_ignored_at_resolution: E-COMPOSE with the mutated config.
        Some(c) => c,
        None => str_of(&comp["config"], "composition.config")?,
    };
    let config_text = read_text(&cx.fixture_dir, config_rel)?;

    let mut rec = Map::new();
    rec.insert("id".into(), json!(spec.id));
    rec.insert("manifest_family".into(), json!(spec.family));
    rec.insert("entry".into(), json!(entry));
    rec.insert("module".into(), json!(module));
    rec.insert("index_path".into(), json!(idx));
    rec.insert("config".into(), json!(config_rel));

    // Phase before_load: shard files before Checkpoint::open and the backing
    // load; the standalone file before B's load.
    let mut before_load = Map::new();
    before_load.insert("shards".into(), Value::Object(shard_file_hashes(&ck_dir)?));
    if backing_rel != ck_rel {
        before_load.insert(
            "backing_checkpoint_shards".into(),
            Value::Object(shard_file_hashes(&backing_dir)?),
        );
    }
    if let Some(file) = &spec.file {
        before_load.insert("standalone".into(), file_hash(&cx.fixture_dir, file)?);
    }

    // Compose. Every composition refusal is decided here, on host data.
    let source_holder;
    let backing_holder;
    let selected: Result<(SelectedPlane<'_>, &Backing), CompositionRefusal> = match entry {
        "E-RANGE" => {
            let source = Source::open(&ck_dir, &config_text, &wins);
            let probe = &comp["range_probe"];
            let r = source.and_then(|src| {
                let shard = probe["shard"].as_str().unwrap_or_default();
                let begin = probe["begin"].as_u64().unwrap_or_default();
                let len = probe["len"].as_u64().unwrap_or_default();
                resolve_range(src.backing(), shard, begin, len).map(|b| b.len())
            });
            let at_decision = snapshot();
            rec.insert("range_probe".into(), probe.clone());
            return Ok(match r {
                Err(refusal) => {
                    rec.insert("outcome".into(), json!("refused"));
                    rec.insert("refusal".into(), refusal_json(&refusal));
                    rec.insert("counters".into(), json!({"at_decision": calls(c0, at_decision), "whole_case": calls(c0, snapshot())}));
                    Value::Object(rec)
                }
                Ok(n) => {
                    rec.insert("outcome".into(), json!("range_admitted"));
                    rec.insert("admitted_bytes".into(), json!(n));
                    rec.insert("counters".into(), json!({"at_decision": calls(c0, at_decision), "whole_case": calls(c0, snapshot())}));
                    Value::Object(rec)
                }
            });
        }
        "E-SELECT" => {
            source_holder = Source::open(&ck_dir, &config_text, &BTreeMap::new());
            match &source_holder {
                Err(r) => Err(r.clone()),
                Ok(src) => {
                    backing_holder = if backing_rel == ck_rel && wins.is_empty() {
                        None
                    } else {
                        Some(Backing::open(&backing_dir, &wins))
                    };
                    let backing: Result<&Backing, CompositionRefusal> = match &backing_holder {
                        None => Ok(src.backing()),
                        Some(Ok(b)) => Ok(b),
                        Some(Err(r)) => Err(r.clone()),
                    };
                    let tc = &comp["triple_components"];
                    let ts = &comp["triple_spec"];
                    let catalog = src.checkpoint().catalog();
                    let meta = |role: &str| -> Result<_, String> {
                        let name = str_of(&tc[role], "triple component")?;
                        catalog
                            .get(name)
                            .cloned()
                            .ok_or_else(|| format!("no catalog entry {name}"))
                    };
                    let bits = ts["bits"].as_u64().ok_or("triple_spec.bits")?;
                    let group = ts["group_size"].as_u64().ok_or("triple_spec.group_size")?;
                    let qspec = QuantSpec::new(
                        Bits::from_u32(u32::try_from(bits).map_err(|e| e.to_string())?)
                            .map_err(|e| e.to_string())?,
                        GroupSize::from_u32(u32::try_from(group).map_err(|e| e.to_string())?)
                            .map_err(|e| e.to_string())?,
                        Mode::parse(str_of(&ts["mode"], "triple_spec.mode")?)
                            .map_err(|e| e.to_string())?,
                    );
                    // The candidate, built through the PUBLIC Slice 1
                    // constructor from the manifest's components and recipe.
                    let candidate = AffineTriple::new(
                        module,
                        meta("weight")?,
                        meta("scales")?,
                        meta("biases")?,
                        qspec,
                    )
                    .map_err(|e| format!("AffineTriple::new refused the candidate: {e}"))?;
                    rec.insert("candidate".into(), json!({"components": tc, "spec": ts}));
                    backing.and_then(|b| {
                        select_plane(src.checkpoint(), b, src.config(), &candidate, &idx)
                            .map(|p| (p, b))
                    })
                }
            }
        }
        "E-COMPOSE" => {
            source_holder = Source::open(&ck_dir, &config_text, &wins);
            match &source_holder {
                Ok(src) => compose_plane(src, module, &idx).map(|p| (p, src.backing())),
                Err(r) => Err(r.clone()),
            }
        }
        other => return Err(format!("unknown composition entry {other}")),
    };
    let at_decision = snapshot();

    let (plane, backing) = match selected {
        Err(refusal) => {
            if mutation_kind == Some("override_ignored_at_resolution") {
                rec.insert("outcome".into(), json!("detected"));
                rec.insert("detected_checks".into(), json!([refusal.id.as_str()]));
            } else {
                rec.insert("outcome".into(), json!("refused"));
            }
            rec.insert("refusal".into(), refusal_json(&refusal));
            rec.insert(
                "counters".into(),
                json!({"at_decision": calls(c0, at_decision), "whole_case": calls(c0, snapshot())}),
            );
            return Ok(Value::Object(rec));
        }
        Ok(p) => p,
    };
    let record = plane.record();
    let record_json = record.to_json();
    rec.insert("selection".into(), record_json.clone());
    rec.insert(
        "borrows".into(),
        json!(COMPONENTS
            .iter()
            .enumerate()
            .map(|(i, c)| json!({"component": c, "shard": record.ranges[i].shard, "begin": record.ranges[i].begin, "len": record.ranges[i].len, "accounting": "measured: borrowed sub-slice of the immutable backing, not a copy"}))
            .collect::<Vec<_>>()),
    );

    // Mutation controls: selection-record level only; no native call follows.
    if let Some(m) = mutation {
        let oracle = &doc["oracle"];
        let baseline = selection_mismatches(
            &record_json,
            &oracle["baseline_identity"],
            &oracle["baseline_ranges"],
            &oracle["baseline_sha256"],
        );
        let (mutated, applied) = apply_mutation(&record, m, backing)?;
        let detected = selection_mismatches(
            &mutated,
            &oracle["baseline_identity"],
            &oracle["baseline_ranges"],
            &oracle["baseline_sha256"],
        );
        rec.insert("baseline_mismatches".into(), json!(baseline));
        rec.insert(
            "mutation".into(),
            json!({"kind": mutation_kind, "mutated_record": mutated, "applied": applied}),
        );
        rec.insert(
            "outcome".into(),
            json!(if detected.is_empty() {
                "undetected"
            } else {
                "detected"
            }),
        );
        rec.insert("detected_checks".into(), json!(detected));
        rec.insert(
            "counters".into(),
            json!({"at_decision": calls(c0, at_decision), "whole_case": calls(c0, snapshot())}),
        );
        return Ok(Value::Object(rec));
    }

    // Selection checks against the oracle, before any native call. A wrong
    // plane is never executed.
    let oracle = &doc["oracle"];
    let mismatches = selection_mismatches(
        &record_json,
        &oracle["identity"],
        &oracle["ranges"],
        &oracle["sha256"],
    );
    rec.insert("child_selection_mismatches".into(), json!(mismatches));
    if !mismatches.is_empty() {
        rec.insert("outcome".into(), json!("selection_mismatch"));
        rec.insert(
            "counters".into(),
            json!({"whole_case": calls(c0, snapshot())}),
        );
        return Ok(Value::Object(rec));
    }

    // Stage A from the plane; load B (and A's x) from the standalone file.
    let [wa, sa, ba] = stage(&plane)?;
    let standalone = load_case(&cx.fixture_dir, spec).map_err(|e| e.to_string())?;
    let t = |n: &str| {
        standalone
            .tensor(n)
            .ok_or_else(|| format!("{}: no standalone tensor {n}", spec.id))
    };
    let (xb, wb, sb, bb) = (t("x")?, t("w")?, t("scales")?, t("biases")?);
    let xa = xb.clone();
    let staged_a = staged_records(&xa, &wa, &sa, &ba);
    let staged_b = staged_records(xb, wb, sb, bb);
    let staged_equal_local = staged_a == staged_b && staged_a == doc["expected"]["staged_inputs"];
    rec.insert(
        "staged_inputs".into(),
        json!({"A": staged_a, "B": staged_b, "accounting": "measured: the exact host bytes handed to mlx_array_new_data (the staged HostTensor bytes as imported)"}),
    );
    rec.insert("child_staged_equal".into(), json!(staged_equal_local));

    // Phase after_host_selection: after selection and staging, before any
    // native call.
    let after_selection = json!({
        "shards": shard_file_hashes(&ck_dir)?,
        "backing": backing.buffer_records(),
    });
    let mut phases = Map::new();
    phases.insert("before_load".into(), Value::Object(before_load));
    phases.insert("after_host_selection".into(), after_selection);

    let native_before_decision = calls(c0, snapshot());
    rec.insert("counters_before_native".into(), native_before_decision);
    if !staged_equal_local {
        rec.insert("outcome".into(), json!("staged_mismatch"));
        rec.insert("source_hashes".into(), Value::Object(phases));
        rec.insert(
            "counters".into(),
            json!({"whole_case": calls(c0, snapshot())}),
        );
        return Ok(Value::Object(rec));
    }

    // A then B, each in its own counter interval; bits and group from the
    // plane identity for A and from the manifest params for B.
    let id = plane.identity();
    let agg0 = snapshot();
    let a = run_side(
        cx,
        gpu,
        &spec.id,
        "A",
        &xa,
        &wa,
        &sa,
        &ba,
        id.bits,
        id.group_size,
    )?;
    let b_bits = spec.param_u64("bits").ok_or("params.bits")? as u32;
    let b_group = spec.param_u64("group_size").ok_or("params.group_size")? as u32;
    let b = run_side(cx, gpu, &spec.id, "B", xb, wb, sb, bb, b_bits, b_group)?;
    let agg1 = snapshot();

    // Phase after_native_execution.
    phases.insert(
        "after_native_execution".into(),
        json!({
            "shards": shard_file_hashes(&ck_dir)?,
            "backing": backing.buffer_records(),
            "standalone": file_hash(&cx.fixture_dir, spec.file.as_deref().unwrap_or_default())?,
        }),
    );
    let outcome = match (a["outcome"].as_str(), b["outcome"].as_str()) {
        (Some("executed"), Some("executed")) => "executed",
        (Some("refused"), Some("refused")) => "refused",
        _ => "error",
    };
    rec.insert("outcome".into(), json!(outcome));
    rec.insert("A".into(), a);
    rec.insert("B".into(), b);
    rec.insert("source_hashes".into(), Value::Object(phases));
    rec.insert(
        "counters".into(),
        json!({"whole_case_aggregate": delta(agg0, agg1), "whole_case": delta(c0, snapshot())}),
    );
    let staging: Vec<Value> = [("w", &wa), ("scales", &sa), ("biases", &ba)]
        .iter()
        .map(|(r, t)| {
            json!({"role": r, "dtype": t.dtype.name(), "shape": t.shape, "bytes": t.bytes.len(),
                   "sha256": sha256_hex(&t.bytes), "source": "copy of the plane's borrowed bytes"})
        })
        .collect();
    let census = &doc["expected"]["array_census"];
    let derived_casts: Vec<Value> = census["bridge_visible_handles"]
        .as_array()
        .map(|a| a.iter().filter(|h| h["op"] == "astype").cloned().collect())
        .unwrap_or_default();
    rec.insert(
        "copy_accounting".into(),
        json!({
            "measured": {
                "staging": staging,
                "x_staging": {"role": "x", "dtype": xa.dtype.name(), "shape": xa.shape, "bytes": xa.bytes.len(),
                              "sha256": sha256_hex(&xa.bytes), "source": "standalone x (x_from)"},
                "counters": "per-side intervals in A.counters and B.counters; whole_case_aggregate in counters",
            },
            "source_derived": {
                "casts": derived_casts,
                "workspace": census["source_derived_workspace"],
                "label": "source-derived from the bridge code and pinned MLX source, copied from the manifest; not measured",
            },
        }),
    );
    Ok(Value::Object(rec))
}

/// E6 in the compose child (contract C8; slice2c-plan.md section 3 keeps the
/// Slice 2B start sequence and evidence): the CPU-context negative control.
/// The first FX-COMP-ACCEPT case is composed and staged exactly as side A,
/// then handed to the EXISTING bridge on a CPU-device `NativeContext`, which
/// must refuse it with R-DEVICE before any MLX-C numerical call or import. It
/// is a control like the E4 canary, not a manifest case: the frozen 32-case
/// population is unchanged. The child records; the parent decides.
fn e6_cpu_control(cx: &ComposeCtx, specs: &[CaseSpec], docs: &BTreeMap<String, Value>) -> Value {
    let r = (|| -> Result<Value, String> {
        let spec = specs
            .iter()
            .find(|c| c.family == "FX-COMP-ACCEPT")
            .ok_or("no FX-COMP-ACCEPT case")?;
        let doc = docs.get(&spec.id).ok_or("no manifest document")?;
        let comp = &doc["composition"];
        let ck_dir = cx
            .fixture_dir
            .join(str_of(&comp["checkpoint"], "composition.checkpoint")?);
        let config_text = read_text(
            &cx.fixture_dir,
            str_of(&comp["config"], "composition.config")?,
        )?;
        let module = str_of(&comp["module"], "composition.module")?;
        let idx = index_path(&comp["index_path"])?;
        let source = Source::open(
            &ck_dir,
            &config_text,
            &windows(&comp["backing"]["windows"])?,
        )
        .map_err(|e| e.to_string())?;
        let plane = compose_plane(&source, module, &idx).map_err(|e| e.to_string())?;
        let selection = plane.record().to_json();
        let [w, s, b] = stage(&plane)?;
        let standalone = load_case(&cx.fixture_dir, spec).map_err(|e| e.to_string())?;
        let x = standalone.tensor("x").ok_or("no standalone x")?;
        let id = plane.identity();
        let cpu = NativeContext::new(DeviceKind::Cpu).map_err(|e| e.to_string())?;
        let before = snapshot();
        let r = bridge::quantized_matmul(&cpu, x, &w, &s, &b, id.bits, id.group_size);
        let after = snapshot();
        let mut rec = json!({
            "case_id": spec.id, "context": "cpu", "selection": selection,
            "staged": staged_records(x, &w, &s, &b),
            "counters": delta(before, after),
        });
        match r {
            Err((BridgeError::Refused(rid), stats)) => {
                rec["outcome"] = json!("refused");
                rec["refusal_id"] = json!(rid.as_str());
                rec["stats"] = stats_json(&stats);
            }
            Err((BridgeError::Native(n), stats)) => {
                rec["outcome"] = json!("error");
                rec["error"] = json!(redact(&n.to_string()));
                rec["stats"] = stats_json(&stats);
            }
            Ok((_, _, stats)) => {
                rec["outcome"] = json!("executed");
                rec["stats"] = stats_json(&stats);
            }
        }
        rec["cpu_context_live_arrays_after"] = json!(cpu.live_arrays());
        drop(cpu);
        Ok(rec)
    })();
    r.unwrap_or_else(|e| json!({"context": "cpu", "outcome": "error", "error": redact(&e)}))
}

pub fn compose(args: &Args) -> Result<(), String> {
    let abi = ffi::verify_abi()?;
    native::ensure_error_handler();
    native::set_default_device_gpu().map_err(|e| e.to_string())?;
    let prefix = std::env::var("PULSAR_F020_NATIVE_PREFIX")
        .map_err(|_| "PULSAR_F020_NATIVE_PREFIX unset".to_string())?;
    let prov = provenance::collect(&prefix)?;
    let arch_name = prov["architecture"]
        .as_str()
        .unwrap_or_default()
        .to_string();

    // The Slice 2B files the unchanged E4 canary needs.
    read_frozen(&args.repo, frozen::CONTRACT_PATH, frozen::CONTRACT_SHA256)?;
    let s2b_raw = read_frozen(&args.repo, frozen::MANIFEST_PATH, frozen::MANIFEST_SHA256)?;
    let s2b_manifest = parse_manifest(&s2b_raw).map_err(|e| e.to_string())?;
    // The frozen Slice 2C files.
    read_frozen(
        &args.repo,
        frozen_compose::CONTRACT_PATH,
        frozen_compose::CONTRACT_SHA256,
    )?;
    read_frozen(
        &args.repo,
        frozen_compose::GENERATOR_PATH,
        frozen_compose::GENERATOR_SHA256,
    )?;
    let raw = read_frozen(
        &args.repo,
        frozen_compose::MANIFEST_PATH,
        frozen_compose::MANIFEST_SHA256,
    )?;
    let manifest = parse_manifest(&raw).map_err(|e| e.to_string())?;
    let doc = frozen_compose::manifest_document(&raw).map_err(|e| e.to_string())?;
    let docs = frozen_compose::case_documents(&doc);
    std::fs::create_dir_all(args.out.join("outputs")).map_err(|e| e.to_string())?;

    let canary_cx = Ctx {
        out_dir: args.out.clone(),
        fixture_dir: args.repo.join(frozen::FIXTURE_DIR),
        manifest: &s2b_manifest,
        arch: parse_architecture(&arch_name),
    };
    let cx = ComposeCtx {
        fixture_dir: args.repo.join(frozen_compose::FIXTURE_DIR),
        out_dir: args.out.clone(),
        arch: parse_architecture(&arch_name),
    };
    let gpu = NativeContext::new(DeviceKind::Gpu).map_err(|e| e.to_string())?;
    let canary_start = canary(&canary_cx, &gpu, "start");
    let mut cases = Vec::with_capacity(manifest.cases.len());
    for spec in &manifest.cases {
        let case_doc = docs
            .get(&spec.id)
            .ok_or_else(|| format!("{}: no manifest document", spec.id))?;
        cases.push(run_case(&cx, &gpu, spec, case_doc));
    }
    let e6 = e6_cpu_control(&cx, &manifest.cases, &docs);
    let canary_end = canary(&canary_cx, &gpu, "end");
    let live_in_context = gpu.live_arrays();
    if args.test_fault.as_deref() == Some("cleanup-sync") {
        native::inject_teardown_sync_failure();
    }
    drop(gpu);
    native::drain_residual_error("residual error slot after teardown");
    let (live, freed) = native::handle_census();

    let report = json!({
        "schema": frozen_compose::CHILD_REPORT_SCHEMA,
        "mode": frozen_compose::CHILD_MODE,
        "contract_sha256": frozen_compose::CONTRACT_SHA256,
        "manifest_sha256": frozen_compose::MANIFEST_SHA256,
        "generator_sha256": frozen_compose::GENERATOR_SHA256,
        "slice2b_contract_sha256": frozen_compose::SLICE2B_CONTRACT_SHA256,
        "canary_manifest_sha256": frozen::MANIFEST_SHA256,
        "per_side_numerical_calls_pinned_from_source": frozen_compose::PER_SIDE_NUMERICAL_CALLS,
        "abi_values": abi,
        "error_handler": {"installs": native::handler_installs(), "messages_received": native::handler_messages()},
        "provenance": prov,
        "canary_start": canary_start,
        "canary_end": canary_end,
        "e6_cpu_negative_control": e6,
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
