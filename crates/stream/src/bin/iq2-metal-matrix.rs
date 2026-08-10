#[cfg(not(target_os = "macos"))]
fn main() {
    eprintln!("iq2-metal-matrix requires macOS and Apple Metal");
    std::process::exit(2);
}

#[cfg(target_os = "macos")]
fn main() {
    if let Err(error) = run() {
        eprintln!("iq2-metal-matrix: {error}");
        std::process::exit(1);
    }
}

#[cfg(target_os = "macos")]
fn run() -> Result<(), String> {
    use serde_json::json;
    use sha2::{Digest, Sha256};
    use std::cmp::Ordering;
    use std::collections::BTreeMap;
    use std::fs;
    use std::path::PathBuf;
    use std::process::Command;
    use std::time::Instant;
    use stream::{
        Iq2XxsGemvSpec, MetalBridge, StableSlabAllocator, StableSlabConfig, ZeroingPolicy,
    };

    const WARMUPS: usize = 3;
    const MEASURED: usize = 30;

    let mut values = BTreeMap::new();
    let mut args = std::env::args().skip(1);
    while let Some(flag) = args.next() {
        if !matches!(
            flag.as_str(),
            "--packed" | "--activation" | "--rows" | "--columns" | "--out"
        ) {
            return Err(format!("unsupported argument: {flag}"));
        }
        let value = args
            .next()
            .ok_or_else(|| format!("missing value for {flag}"))?;
        if values.insert(flag.clone(), value).is_some() {
            return Err(format!("duplicate argument: {flag}"));
        }
    }
    let required = |flag: &str| {
        values
            .get(flag)
            .cloned()
            .ok_or_else(|| format!("missing required argument: {flag}"))
    };
    let packed_path = PathBuf::from(required("--packed")?);
    let activation_path = PathBuf::from(required("--activation")?);
    let output_path = PathBuf::from(required("--out")?);
    let rows = required("--rows")?
        .parse::<usize>()
        .map_err(|_| "--rows must be a positive integer".to_owned())?;
    let columns = required("--columns")?
        .parse::<usize>()
        .map_err(|_| "--columns must be a positive integer".to_owned())?;
    if output_path.exists() {
        return Err("output path already exists".into());
    }

    let status = Command::new("git")
        .args(["status", "--porcelain"])
        .output()
        .map_err(|error| format!("git status failed: {error}"))?;
    if !status.status.success() || !status.stdout.is_empty() {
        return Err("source worktree must be clean before real matrix measurement".into());
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

    let packed_read_start = Instant::now();
    let packed = fs::read(&packed_path).map_err(|error| format!("packed read failed: {error}"))?;
    let packed_read_seconds = packed_read_start.elapsed().as_secs_f64();
    let activation_read_start = Instant::now();
    let activation_bytes =
        fs::read(&activation_path).map_err(|error| format!("activation read failed: {error}"))?;
    let activation_read_seconds = activation_read_start.elapsed().as_secs_f64();
    if activation_bytes.len() != columns.checked_mul(4).ok_or("activation size overflow")? {
        return Err("activation byte length does not match columns".into());
    }
    let activation = activation_bytes
        .chunks_exact(4)
        .map(|bytes| f32::from_le_bytes(bytes.try_into().expect("four-byte chunk")))
        .collect::<Vec<_>>();
    if !activation.iter().all(|value| value.is_finite()) {
        return Err("activation contains non-finite f32 values".into());
    }
    let spec = Iq2XxsGemvSpec::new(rows, columns, packed.len(), activation.len())?;
    let allocator = StableSlabAllocator::new(StableSlabConfig::new(
        packed.len(),
        4096,
        1,
        ZeroingPolicy::ZeroInitialize,
    ))
    .map_err(|error| error.to_string())?;
    let mut slab = allocator.acquire().map_err(|error| error.to_string())?;
    let slab_copy_start = Instant::now();
    slab.as_mut_slice().copy_from_slice(&packed);
    let slab_copy_seconds = slab_copy_start.elapsed().as_secs_f64();
    let bridge = MetalBridge::new()?;
    let device_name = bridge.device_name()?;
    let compiler = bridge.compiler_settings();
    let registration = bridge.register(&slab)?;
    let process_first = bridge.iq2_xxs_gemv(&registration, spec, &activation)?;
    for _ in 0..WARMUPS {
        bridge.iq2_xxs_gemv(&registration, spec, &activation)?;
    }

    let mut totals = Vec::with_capacity(MEASURED);
    let mut dispatch = Vec::with_capacity(MEASURED);
    let mut synchronization = Vec::with_capacity(MEASURED);
    let mut kernel = Vec::with_capacity(MEASURED);
    let mut hashes = Vec::with_capacity(MEASURED);
    let mut output_bits = None;
    for _ in 0..MEASURED {
        let result = bridge.iq2_xxs_gemv(&registration, spec, &activation)?;
        let bytes = result
            .output
            .iter()
            .flat_map(|value| value.to_bits().to_le_bytes())
            .collect::<Vec<_>>();
        hashes.push(format!("{:x}", Sha256::digest(&bytes)));
        if output_bits.is_none() {
            output_bits = Some(
                result
                    .output
                    .iter()
                    .map(|value| value.to_bits())
                    .collect::<Vec<_>>(),
            );
        }
        totals.push(result.telemetry.total_seconds);
        dispatch.push(result.telemetry.dispatch_seconds);
        synchronization.push(result.telemetry.synchronization_seconds);
        if let Some(seconds) = result.telemetry.kernel_seconds {
            kernel.push(seconds);
        }
    }
    if hashes.iter().any(|hash| hash != &hashes[0]) {
        return Err("direct IQ2_XXS output was nondeterministic".into());
    }

    let summarize = |samples: &[f64]| {
        let mut ordered = samples.to_vec();
        ordered.sort_by(|left, right| left.partial_cmp(right).unwrap_or(Ordering::Equal));
        let mean = samples.iter().sum::<f64>() / samples.len() as f64;
        let sample_standard_deviation = if samples.len() > 1 {
            (samples
                .iter()
                .map(|value| (value - mean).powi(2))
                .sum::<f64>()
                / (samples.len() - 1) as f64)
                .sqrt()
        } else {
            0.0
        };
        let percentile =
            |fraction: f64| ordered[((ordered.len() - 1) as f64 * fraction).round() as usize];
        json!({
            "sample_count": samples.len(),
            "measured_samples_seconds": samples,
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
    let record = json!({
        "schema": "pulsarmlx.internal.f018-iq2-metal-runner",
        "schema_version": "1.0.0",
        "source": {"commit": commit, "dirty": false},
        "device": device_name,
        "binding": {
            "rows": rows,
            "columns": columns,
            "packed_bytes": packed.len(),
            "packed_sha256": format!("{:x}", Sha256::digest(&packed)),
            "activation_bytes": activation_bytes.len(),
            "activation_sha256": format!("{:x}", Sha256::digest(&activation_bytes)),
        },
        "setup": {
            "packed_read_count": 1,
            "packed_read_seconds": packed_read_seconds,
            "activation_read_count": 1,
            "activation_read_seconds": activation_read_seconds,
            "slab_copy_seconds": slab_copy_seconds,
            "registration_seconds": registration.registration_seconds(),
            "compilation_seconds": bridge.compilation_seconds(),
            "pipeline_creation_seconds": bridge.pipeline_creation_seconds(),
            "compiler": {
                "fast_math_enabled": compiler.fast_math_enabled,
                "language_version": compiler.language_version,
                "math_mode": "safe",
                "math_floating_point_functions": "precise",
                "pipeline_identity": "iq2_xxs_sequential_scaffold_v1",
            },
            "slab_logical_bytes": slab.len(),
            "slab_allocated_bytes": allocator.telemetry().allocated_bytes,
        },
        "protocol": {"warmups": WARMUPS, "measured": MEASURED},
        "process_first": {
            "dispatch_seconds": process_first.telemetry.dispatch_seconds,
            "kernel_seconds": process_first.telemetry.kernel_seconds,
            "synchronization_seconds": process_first.telemetry.synchronization_seconds,
            "total_seconds": process_first.telemetry.total_seconds,
        },
        "timing": {
            "total": summarize(&totals),
            "dispatch": summarize(&dispatch),
            "synchronization": summarize(&synchronization),
            "kernel": if kernel.len() == MEASURED { summarize(&kernel) } else { serde_json::Value::Null },
        },
        "output_f32_bits": output_bits.ok_or("no output samples")?,
        "output_sha256": hashes[0],
        "unique_output_hashes": 1,
        "cpu_fallback_count": 0,
        "complete_f32_weight_materialized_bytes": 0,
    });
    fs::write(
        &output_path,
        serde_json::to_vec_pretty(&record).map_err(|error| error.to_string())?,
    )
    .map_err(|error| format!("output write failed: {error}"))?;
    Ok(())
}
