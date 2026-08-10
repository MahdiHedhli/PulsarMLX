#[cfg(not(target_os = "macos"))]
fn main() {
    eprintln!("iq2-metal-worker requires macOS and Apple Metal");
    std::process::exit(2);
}

#[cfg(target_os = "macos")]
fn main() {
    if let Err(error) = run() {
        eprintln!("iq2-metal-worker: {error}");
        std::process::exit(1);
    }
}

#[cfg(target_os = "macos")]
fn run() -> Result<(), String> {
    use serde_json::{json, Value};
    use std::collections::HashMap;
    use std::io::{BufRead, BufReader, Write};
    use std::process::Command;
    use stream::{MetalBridge, StableSlab};

    const MAX_RESIDENT_MATRICES: usize = 2;
    let status = Command::new("git")
        .args(["status", "--porcelain"])
        .output()
        .map_err(|error| format!("git status failed: {error}"))?;
    if !status.status.success() || !status.stdout.is_empty() {
        return Err("source worktree must be clean before starting the Metal worker".into());
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
    let bridge = MetalBridge::new()?;
    let device = bridge.device_name()?;
    let compiler = bridge.compiler_settings();
    let mut stdout = std::io::stdout().lock();
    writeln!(
        stdout,
        "{}",
        json!({
            "status": "ready",
            "source_commit": commit,
            "device": device,
            "compilation_seconds": bridge.compilation_seconds(),
            "pipeline_creation_seconds": bridge.pipeline_creation_seconds(),
            "compiler": {
                "fast_math_enabled": compiler.fast_math_enabled,
                "language_version": compiler.language_version,
                "math_mode": "safe",
                "math_floating_point_functions": "precise",
                "pipeline_identity": "iq2_xxs_sequential_scaffold_v1",
                "lookup_address_space": "constant",
            },
            "max_resident_matrices": MAX_RESIDENT_MATRICES,
        })
    )
    .map_err(|error| error.to_string())?;
    stdout.flush().map_err(|error| error.to_string())?;

    let stdin = std::io::stdin();
    let mut reader = BufReader::new(stdin.lock());
    let mut line = String::new();
    let mut resident: HashMap<String, StableSlab> = HashMap::new();
    let mut evictions = 0_u64;
    loop {
        line.clear();
        if reader
            .read_line(&mut line)
            .map_err(|error| error.to_string())?
            == 0
        {
            break;
        }
        let request: Value = match serde_json::from_str(&line) {
            Ok(value) => value,
            Err(error) => {
                respond_error(&mut stdout, None, &format!("invalid JSON request: {error}"))?;
                continue;
            }
        };
        let request_id = request.get("request_id").and_then(Value::as_u64);
        match request.get("command").and_then(Value::as_str) {
            Some("shutdown") => {
                writeln!(
                    stdout,
                    "{}",
                    json!({"status": "shutdown", "request_id": request_id})
                )
                .map_err(|error| error.to_string())?;
                stdout.flush().map_err(|error| error.to_string())?;
                break;
            }
            Some("clear") => {
                resident.clear();
                writeln!(
                    stdout,
                    "{}",
                    json!({"status": "cleared", "request_id": request_id, "evictions": evictions})
                )
                .map_err(|error| error.to_string())?;
                stdout.flush().map_err(|error| error.to_string())?;
            }
            Some("gemv") => {
                let response = handle_gemv(
                    &bridge,
                    &request,
                    &mut resident,
                    &mut evictions,
                    MAX_RESIDENT_MATRICES,
                );
                match response {
                    Ok(value) => writeln!(stdout, "{value}").map_err(|error| error.to_string())?,
                    Err(error) => respond_error(&mut stdout, request_id, &error)?,
                }
                stdout.flush().map_err(|error| error.to_string())?;
            }
            _ => respond_error(&mut stdout, request_id, "unsupported worker command")?,
        }
    }
    Ok(())
}

#[cfg(target_os = "macos")]
fn respond_error(
    output: &mut impl std::io::Write,
    request_id: Option<u64>,
    error: &str,
) -> Result<(), String> {
    writeln!(
        output,
        "{}",
        serde_json::json!({"status": "error", "request_id": request_id, "error": error})
    )
    .map_err(|failure| failure.to_string())?;
    output.flush().map_err(|failure| failure.to_string())
}

#[cfg(target_os = "macos")]
fn handle_gemv(
    bridge: &stream::MetalBridge,
    request: &serde_json::Value,
    resident: &mut std::collections::HashMap<String, stream::StableSlab>,
    evictions: &mut u64,
    max_resident: usize,
) -> Result<serde_json::Value, String> {
    use serde_json::{json, Value};
    use sha2::{Digest, Sha256};
    use std::fs::File;
    use std::os::unix::fs::FileExt;
    use std::path::Path;
    use std::time::Instant;
    use stream::{Iq2XxsGemvSpec, StableSlabAllocator, StableSlabConfig, ZeroingPolicy};

    let request_id = request
        .get("request_id")
        .and_then(Value::as_u64)
        .ok_or("request_id must be an unsigned integer")?;
    let path = request
        .get("shard_path")
        .and_then(Value::as_str)
        .ok_or("shard_path must be a string")?;
    let offset = request
        .get("offset")
        .and_then(Value::as_u64)
        .ok_or("offset must be an unsigned integer")?;
    let rows = request
        .get("rows")
        .and_then(Value::as_u64)
        .and_then(|value| usize::try_from(value).ok())
        .ok_or("rows must fit usize")?;
    let columns = request
        .get("columns")
        .and_then(Value::as_u64)
        .and_then(|value| usize::try_from(value).ok())
        .ok_or("columns must fit usize")?;
    let activation_bits = request
        .get("activation_f32_bits")
        .and_then(Value::as_array)
        .ok_or("activation_f32_bits must be an array")?;
    let activation = activation_bits
        .iter()
        .map(|value| {
            value
                .as_u64()
                .and_then(|bits| u32::try_from(bits).ok())
                .map(f32::from_bits)
                .ok_or_else(|| "activation bit pattern must fit u32".to_owned())
        })
        .collect::<Result<Vec<_>, _>>()?;
    let packed_row_bytes = (columns / 256)
        .checked_mul(66)
        .ok_or("packed row size overflow")?;
    let packed_bytes = rows
        .checked_mul(packed_row_bytes)
        .ok_or("packed matrix size overflow")?;
    let spec = Iq2XxsGemvSpec::new(rows, columns, packed_bytes, activation.len())?;
    let key = format!("{path}\0{offset}\0{packed_bytes}");
    let cache_hit = resident.contains_key(&key);
    let mut storage_read_seconds = 0.0;
    if !cache_hit {
        if resident.len() >= max_resident {
            *evictions += resident.len() as u64;
            resident.clear();
        }
        let allocator = StableSlabAllocator::new(StableSlabConfig::new(
            packed_bytes,
            4096,
            1,
            ZeroingPolicy::ZeroInitialize,
        ))
        .map_err(|error| error.to_string())?;
        let mut slab = allocator.acquire().map_err(|error| error.to_string())?;
        let file = File::open(Path::new(path)).map_err(|error| format!("open failed: {error}"))?;
        let read_start = Instant::now();
        let mut actual = 0_usize;
        while actual < slab.len() {
            let count = file
                .read_at(&mut slab.as_mut_slice()[actual..], offset + actual as u64)
                .map_err(|error| format!("positional read failed: {error}"))?;
            if count == 0 {
                return Err(format!(
                    "short read: expected {}, received {actual}",
                    slab.len()
                ));
            }
            actual += count;
        }
        storage_read_seconds = read_start.elapsed().as_secs_f64();
        resident.insert(key.clone(), slab);
    }
    let slab = resident.get(&key).ok_or("resident slab disappeared")?;
    let registration = bridge.register(slab)?;
    let result = bridge.iq2_xxs_gemv(&registration, spec, &activation)?;
    let output_bytes = result
        .output
        .iter()
        .flat_map(|value| value.to_bits().to_le_bytes())
        .collect::<Vec<_>>();
    Ok(json!({
        "status": "ok",
        "request_id": request_id,
        "cache_hit": cache_hit,
        "resident_entries": resident.len(),
        "evictions": *evictions,
        "storage_read_count": if cache_hit { 0 } else { 1 },
        "storage_bytes_read": if cache_hit { 0 } else { packed_bytes },
        "storage_read_seconds": storage_read_seconds,
        "registration_seconds": registration.registration_seconds(),
        "dispatch_seconds": result.telemetry.dispatch_seconds,
        "kernel_seconds": result.telemetry.kernel_seconds,
        "synchronization_seconds": result.telemetry.synchronization_seconds,
        "total_seconds": result.telemetry.total_seconds,
        "output_f32_bits": result.output.iter().map(|value| value.to_bits()).collect::<Vec<_>>(),
        "output_sha256": format!("{:x}", Sha256::digest(&output_bytes)),
        "cpu_fallback_count": 0,
        "complete_f32_weight_materialized_bytes": 0,
    }))
}
