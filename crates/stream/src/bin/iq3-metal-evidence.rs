#[cfg(not(target_os = "macos"))]
fn main() {
    eprintln!("iq3-metal-evidence requires macOS and Apple Metal");
    std::process::exit(2);
}

#[cfg(target_os = "macos")]
fn main() {
    if let Err(error) = run() {
        eprintln!("iq3-metal-evidence: {error}");
        std::process::exit(1);
    }
}

#[cfg(target_os = "macos")]
fn run() -> Result<(), String> {
    use serde_json::{json, Value};
    use sha2::{Digest, Sha256};
    use std::cmp::Ordering;
    use std::path::PathBuf;
    use std::process::Command;
    use stream::{
        iq3_xxs_gemv_reference, iq3_xxs_lookup_sha256, synthetic_iq3_xxs_matrix, Iq3XxsGemvSpec,
        MetalBridge, StableSlabAllocator, StableSlabConfig, ZeroingPolicy,
    };

    const ROWS: usize = 64;
    const COLUMNS: usize = 2048;
    const WARMUPS: usize = 5;
    const MEASURED: usize = 100;
    const ABSOLUTE_TOLERANCE: f32 = 0.00025;
    const RELATIVE_TOLERANCE: f32 = 0.00025;
    const COSINE_MINIMUM: f64 = 0.999_999_5;
    const NORM_RATIO_MINIMUM: f64 = 0.999_75;
    const NORM_RATIO_MAXIMUM: f64 = 1.000_25;

    let mut args = std::env::args().skip(1);
    let flag = args.next().ok_or("usage: iq3-metal-evidence --out PATH")?;
    let output_path = args.next().ok_or("usage: iq3-metal-evidence --out PATH")?;
    if flag != "--out" || args.next().is_some() {
        return Err("usage: iq3-metal-evidence --out PATH".into());
    }
    let output_path = PathBuf::from(output_path);
    let status = Command::new("git")
        .args(["status", "--porcelain"])
        .output()
        .map_err(|error| format!("git status failed: {error}"))?;
    if !status.status.success() || !status.stdout.is_empty() {
        return Err("source worktree must be clean before evidence collection".into());
    }
    let commit = Command::new("git")
        .args(["rev-parse", "HEAD"])
        .output()
        .map_err(|error| format!("git rev-parse failed: {error}"))?;
    if !commit.status.success() {
        return Err("source commit could not be resolved".into());
    }
    let commit = String::from_utf8(commit.stdout)
        .map_err(|_| "source commit is not UTF-8")?
        .trim()
        .to_owned();

    let packed = synthetic_iq3_xxs_matrix(ROWS, COLUMNS)?;
    let activation = (0..COLUMNS)
        .map(|index| ((index % 127) as f32 - 63.0) / 127.0)
        .collect::<Vec<_>>();
    let spec = Iq3XxsGemvSpec::new(ROWS, COLUMNS, packed.len(), activation.len())?;
    let reference = iq3_xxs_gemv_reference(&packed, spec, &activation)?;
    let allocator = StableSlabAllocator::new(StableSlabConfig::new(
        packed.len(),
        4096,
        1,
        ZeroingPolicy::ZeroInitialize,
    ))
    .map_err(|error| error.to_string())?;
    let mut slab = allocator.acquire().map_err(|error| error.to_string())?;
    slab.as_mut_slice().copy_from_slice(&packed);
    let bridge = MetalBridge::new()?;
    let device_name = bridge.device_name()?;
    let registration = bridge.register(&slab)?;
    for _ in 0..WARMUPS {
        bridge.iq3_xxs_gemv(&registration, spec, &activation)?;
    }

    let mut total_samples = Vec::with_capacity(MEASURED);
    let mut dispatch_samples = Vec::with_capacity(MEASURED);
    let mut synchronization_samples = Vec::with_capacity(MEASURED);
    let mut kernel_samples = Vec::with_capacity(MEASURED);
    let mut first_output = None;
    let mut repeat_hashes = Vec::with_capacity(MEASURED);
    for _ in 0..MEASURED {
        let result = bridge.iq3_xxs_gemv(&registration, spec, &activation)?;
        let output_bytes = result
            .output
            .iter()
            .flat_map(|value| value.to_bits().to_le_bytes())
            .collect::<Vec<_>>();
        repeat_hashes.push(format!("{:x}", Sha256::digest(&output_bytes)));
        first_output.get_or_insert_with(|| result.output.clone());
        total_samples.push(result.telemetry.total_seconds);
        dispatch_samples.push(result.telemetry.dispatch_seconds);
        synchronization_samples.push(result.telemetry.synchronization_seconds);
        if let Some(seconds) = result.telemetry.kernel_seconds {
            kernel_samples.push(seconds);
        }
    }
    let candidate = first_output.ok_or("no measured candidate output")?;
    if repeat_hashes.iter().any(|hash| hash != &repeat_hashes[0]) {
        return Err("direct IQ3_XXS output was nondeterministic".into());
    }

    let errors = reference
        .iter()
        .zip(&candidate)
        .map(|(expected, actual)| (expected - actual).abs())
        .collect::<Vec<_>>();
    let bit_mismatch_indices = reference
        .iter()
        .zip(&candidate)
        .enumerate()
        .filter_map(|(index, (expected, actual))| {
            (expected.to_bits() != actual.to_bits()).then_some(index)
        })
        .collect::<Vec<_>>();
    let signed_zero_mismatch_count = reference
        .iter()
        .zip(&candidate)
        .filter(|(expected, actual)| {
            **expected == 0.0 && **actual == 0.0 && expected.to_bits() != actual.to_bits()
        })
        .count();
    let mismatch_count = reference
        .iter()
        .zip(&errors)
        .filter(|(expected, error)| {
            **error > ABSOLUTE_TOLERANCE + RELATIVE_TOLERANCE * expected.abs()
        })
        .count();
    if mismatch_count != 0 || signed_zero_mismatch_count != 0 {
        return Err(format!(
            "direct IQ3_XXS qualification failed: mismatches={mismatch_count} signed_zero={signed_zero_mismatch_count}"
        ));
    }

    let reference_norm = reference
        .iter()
        .map(|value| f64::from(*value) * f64::from(*value))
        .sum::<f64>()
        .sqrt();
    let candidate_norm = candidate
        .iter()
        .map(|value| f64::from(*value) * f64::from(*value))
        .sum::<f64>()
        .sqrt();
    let dot = reference
        .iter()
        .zip(&candidate)
        .map(|(expected, actual)| f64::from(*expected) * f64::from(*actual))
        .sum::<f64>();
    let cosine_similarity = dot / (reference_norm * candidate_norm);
    let norm_ratio = candidate_norm / reference_norm;
    if cosine_similarity < COSINE_MINIMUM
        || !(NORM_RATIO_MINIMUM..=NORM_RATIO_MAXIMUM).contains(&norm_ratio)
    {
        return Err(format!(
            "direct IQ3_XXS geometry failed: cosine={cosine_similarity} norm_ratio={norm_ratio}"
        ));
    }
    let exact_bits = bit_mismatch_indices.is_empty();
    let classification = if exact_bits {
        "golden_identical"
    } else {
        "numerically_qualified_greedy_identical"
    };
    let maximum_meaningful_relative_error = reference
        .iter()
        .zip(&errors)
        .filter_map(|(expected, error)| {
            (expected.abs() > ABSOLUTE_TOLERANCE).then_some(error / expected.abs())
        })
        .fold(0.0_f32, f32::max);
    let summarize = |values: &[f64]| -> Value {
        let mut ordered = values.to_vec();
        ordered.sort_by(|left, right| left.partial_cmp(right).unwrap_or(Ordering::Equal));
        let mean = values.iter().sum::<f64>() / values.len() as f64;
        let sample_standard_deviation = if values.len() > 1 {
            (values
                .iter()
                .map(|value| (value - mean).powi(2))
                .sum::<f64>()
                / (values.len() - 1) as f64)
                .sqrt()
        } else {
            0.0
        };
        let percentile = |fraction: f64| {
            let index = ((ordered.len() - 1) as f64 * fraction).round() as usize;
            ordered[index]
        };
        json!({
            "sample_count": values.len(),
            "measured_samples_seconds": values,
            "minimum_seconds": ordered[0],
            "maximum_seconds": ordered[ordered.len() - 1],
            "mean_seconds": mean,
            "median_seconds": (ordered[(ordered.len() - 1) / 2] + ordered[ordered.len() / 2]) / 2.0,
            "sample_standard_deviation_seconds": sample_standard_deviation,
            "p5_seconds": percentile(0.05),
            "p25_seconds": percentile(0.25),
            "p75_seconds": percentile(0.75),
            "p95_seconds": percentile(0.95),
            "coefficient_of_variation": if mean == 0.0 { 0.0 } else { sample_standard_deviation / mean },
        })
    };
    let total_summary = summarize(&total_samples);
    let (grid_sha, signs_sha) = iq3_xxs_lookup_sha256();
    let compiler = bridge.compiler_settings();
    let record = json!({
        "schema": "pulsarmlx.research.f018-direct-iq3-xxs",
        "schema_version": "1.0.0",
        "actual_status": "passed",
        "classification": classification,
        "source": {"commit": commit, "dirty": false},
        "environment": {
            "machine_class": "apple_silicon_m1_ultra",
            "architecture": std::env::consts::ARCH,
            "metal_device": device_name,
        },
        "binding": {
            "fixture": "deterministic_synthetic_iq3_xxs_v1",
            "rows": ROWS,
            "columns": COLUMNS,
            "packed_bytes": packed.len(),
            "activation_sha256": format!("{:x}", Sha256::digest(activation.iter().flat_map(|value| value.to_bits().to_le_bytes()).collect::<Vec<_>>())),
            "reference_output_sha256": format!("{:x}", Sha256::digest(reference.iter().flat_map(|value| value.to_bits().to_le_bytes()).collect::<Vec<_>>())),
        },
        "kernel": {
            "quantization": "IQ3_XXS",
            "packed_block_bytes": 98,
            "values_per_block": 256,
            "accumulation": "f32_sequential_per_output_row",
            "dispatch_geometry": "one_logical_thread_per_output_row",
            "grid_table_sha256": grid_sha,
            "sign_table_sha256": signs_sha,
            "cpu_fallback_count": 0,
            "complete_f32_weight_materialized_bytes": 0,
            "compiler": {
                "fast_math_enabled": compiler.fast_math_enabled,
                "language_version": compiler.language_version,
                "math_mode": "safe",
                "math_floating_point_functions": "precise",
                "pipeline_identity": "iq3_xxs_sequential_scaffold_v1",
            },
        },
        "correctness": {
            "contract_version": "f018-iq3-down-v1",
            "exact_f32_bits": exact_bits,
            "greedy_applicable": false,
            "deterministic_repetitions": MEASURED,
            "unique_output_hashes": 1,
            "candidate_output_sha256": repeat_hashes[0],
            "f32_bit_mismatch_count": bit_mismatch_indices.len(),
            "first_f32_bit_mismatch_index": bit_mismatch_indices.first(),
            "signed_zero_mismatch_count": signed_zero_mismatch_count,
            "elementwise_mismatch_count": mismatch_count,
            "maximum_absolute_error": errors.iter().copied().fold(0.0_f32, f32::max),
            "mean_absolute_error": errors.iter().sum::<f32>() / errors.len() as f32,
            "rmse": (errors.iter().map(|error| error * error).sum::<f32>() / errors.len() as f32).sqrt(),
            "maximum_meaningful_relative_error": maximum_meaningful_relative_error,
            "cosine_similarity": cosine_similarity,
            "norm_ratio": norm_ratio,
            "absolute_tolerance": ABSOLUTE_TOLERANCE,
            "relative_tolerance": RELATIVE_TOLERANCE,
            "cosine_minimum": COSINE_MINIMUM,
            "norm_ratio_minimum": NORM_RATIO_MINIMUM,
            "norm_ratio_maximum": NORM_RATIO_MAXIMUM,
        },
        "setup": {
            "compilation_seconds": bridge.compilation_seconds(),
            "pipeline_creation_seconds": bridge.pipeline_creation_seconds(),
            "registration_seconds": registration.registration_seconds(),
            "logical_packed_bytes": packed.len(),
            "allocator_telemetry": {
                "allocated_bytes": allocator.telemetry().allocated_bytes,
                "peak_logical_residency": allocator.telemetry().peak_logical_residency,
            },
        },
        "timing": {
            "warmup_count": WARMUPS,
            "sample_count": total_samples.len(),
            "measured_samples_seconds": total_samples,
            "minimum_seconds": total_summary["minimum_seconds"],
            "maximum_seconds": total_summary["maximum_seconds"],
            "mean_seconds": total_summary["mean_seconds"],
            "median_seconds": total_summary["median_seconds"],
            "dispatch": summarize(&dispatch_samples),
            "synchronization": summarize(&synchronization_samples),
            "kernel": if kernel_samples.is_empty() { Value::Null } else { summarize(&kernel_samples) },
            "storage_read_seconds": 0.0,
            "buffer_import_seconds": registration.registration_seconds(),
            "shader_compile_first_use_seconds": bridge.compilation_seconds(),
            "pipeline_creation_seconds": bridge.pipeline_creation_seconds(),
        },
        "resource": {"level": "normal"},
        "claim_boundary": "Synthetic packed IQ3_XXS matrix GEMV on one M1 Ultra; not a real checkpoint matrix, expert, layer, token, Rust runtime, or production result.",
        "unsupported_interpretations": [
            "real checkpoint performance",
            "complete expert or model inference",
            "general token throughput",
            "all-format direct Metal support"
        ],
    });
    let parent = output_path.parent().ok_or("output path has no parent")?;
    std::fs::create_dir_all(parent).map_err(|error| format!("create output parent: {error}"))?;
    std::fs::write(
        &output_path,
        serde_json::to_string_pretty(&record).map_err(|error| error.to_string())? + "\n",
    )
    .map_err(|error| format!("write evidence: {error}"))?;
    println!("wrote {}", output_path.display());
    Ok(())
}
