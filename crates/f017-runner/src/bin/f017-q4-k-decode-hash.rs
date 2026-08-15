//! Evidence-only streaming wrapper around the reviewed Rust Q4_K decoder.
//!
//! This binary never opens a checkpoint. It accepts only the private immutable
//! packed copy created by the one-read Q4K-REAL-1 executor.

use f017_runner::final_output_qualification::{
    decode_q4_k_matrix, Q4_K_BYTES_PER_BLOCK, Q4_K_ELEMENTS_PER_BLOCK,
};
use serde_json::json;
use sha2::{Digest, Sha256};
use std::fs::{File, OpenOptions};
use std::io::{Read, Write};
use std::path::PathBuf;

const CHUNK_BLOCKS: usize = 4096;

fn take_arg(args: &mut impl Iterator<Item = String>, expected: &str) -> Result<String, String> {
    let name = args.next().ok_or_else(|| format!("missing {expected}"))?;
    if name != expected {
        return Err(format!("expected {expected}, got {name}"));
    }
    args.next().ok_or_else(|| format!("missing value for {expected}"))
}

fn run() -> Result<(), String> {
    let mut args = std::env::args().skip(1);
    let input = PathBuf::from(take_arg(&mut args, "--input")?);
    let output = PathBuf::from(take_arg(&mut args, "--output")?);
    let summary = PathBuf::from(take_arg(&mut args, "--summary")?);
    if args.next().is_some() {
        return Err("unexpected argument".into());
    }

    let length = input.metadata().map_err(|error| error.to_string())?.len() as usize;
    if length == 0 || length % Q4_K_BYTES_PER_BLOCK != 0 {
        return Err("private packed input length is not Q4_K block aligned".into());
    }
    let mut reader = File::open(&input).map_err(|error| error.to_string())?;
    let mut writer = OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(&output)
        .map_err(|error| error.to_string())?;
    let mut hasher = Sha256::new();
    let mut packed = vec![0_u8; CHUNK_BLOCKS * Q4_K_BYTES_PER_BLOCK];
    let mut elements = 0_u64;
    let mut signed_zero_count = 0_u64;
    let mut minimum = f32::INFINITY;
    let mut maximum = f32::NEG_INFINITY;
    let mut first_bits = None;
    let mut last_bits = None;

    loop {
        let mut filled = 0;
        while filled < packed.len() {
            let count = reader
                .read(&mut packed[filled..])
                .map_err(|error| error.to_string())?;
            if count == 0 {
                break;
            }
            filled += count;
        }
        if filled == 0 {
            break;
        }
        if filled % Q4_K_BYTES_PER_BLOCK != 0 {
            return Err("private packed input ended mid-block".into());
        }
        let blocks = filled / Q4_K_BYTES_PER_BLOCK;
        let decoded = decode_q4_k_matrix(
            &packed[..filled],
            blocks,
            Q4_K_ELEMENTS_PER_BLOCK,
        )
        .map_err(|error| error.to_string())?;
        let mut canonical = Vec::with_capacity(decoded.len() * 4);
        for value in decoded {
            if !value.is_finite() {
                return Err("Rust Q4_K decoder emitted non-finite output".into());
            }
            let bits = value.to_bits();
            first_bits.get_or_insert(bits);
            last_bits = Some(bits);
            signed_zero_count += u64::from(bits == 0x8000_0000);
            minimum = minimum.min(value);
            maximum = maximum.max(value);
            canonical.extend_from_slice(&bits.to_le_bytes());
            elements += 1;
        }
        hasher.update(&canonical);
        writer.write_all(&canonical).map_err(|error| error.to_string())?;
        if filled < packed.len() {
            break;
        }
    }
    writer.sync_all().map_err(|error| error.to_string())?;
    let record = json!({
        "decoded_sha256": format!("{:x}", hasher.finalize()),
        "element_count": elements,
        "non_finite_count": 0,
        "signed_zero_count": signed_zero_count,
        "minimum": minimum,
        "maximum": maximum,
        "first_f32_bits": format!("{:08x}", first_bits.ok_or("empty decoded output")?),
        "last_f32_bits": format!("{:08x}", last_bits.ok_or("empty decoded output")?),
    });
    let bytes = serde_json::to_vec(&record).map_err(|error| error.to_string())?;
    let mut summary_file = OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(summary)
        .map_err(|error| error.to_string())?;
    summary_file.write_all(&bytes).map_err(|error| error.to_string())?;
    summary_file.write_all(b"\n").map_err(|error| error.to_string())?;
    summary_file.sync_all().map_err(|error| error.to_string())?;
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("{error}");
        std::process::exit(1);
    }
}
