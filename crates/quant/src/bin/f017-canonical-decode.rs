//! Byte-only bridge for the accepted F017 IQ2_XXS/IQ3_XXS Rust decoders.
//!
//! Packed bytes arrive on stdin and canonical little-endian f32 bytes leave on
//! stdout.  The binary has no filesystem or checkpoint path capability.

use std::env;
use std::io::{self, Read, Write};

use quant::{decode_iq2_xxs_matrix, decode_iq3_xxs_matrix};

fn parse_usize(value: Option<String>, name: &str) -> Result<usize, String> {
    value
        .ok_or_else(|| format!("missing {name}"))?
        .parse::<usize>()
        .map_err(|_| format!("invalid {name}"))
}

fn run() -> Result<(), String> {
    let mut args = env::args().skip(1);
    let quant_type = args.next().ok_or_else(|| "missing quant type".to_string())?;
    let rows = parse_usize(args.next(), "rows")?;
    let columns = parse_usize(args.next(), "columns")?;
    if args.next().is_some() {
        return Err("unexpected argument".to_string());
    }
    let mut packed = Vec::new();
    io::stdin()
        .read_to_end(&mut packed)
        .map_err(|error| format!("stdin read failed: {error}"))?;
    let count = rows
        .checked_mul(columns)
        .ok_or_else(|| "decoded count overflow".to_string())?;
    let mut decoded = vec![0.0_f32; count];
    match quant_type.as_str() {
        "IQ2_XXS" => decode_iq2_xxs_matrix(&packed, rows, columns, &mut decoded)
            .map_err(|error| format!("IQ2_XXS decode failed: {error:?}"))?,
        "IQ3_XXS" => decode_iq3_xxs_matrix(&packed, rows, columns, &mut decoded)
            .map_err(|error| format!("IQ3_XXS decode failed: {error:?}"))?,
        _ => return Err("unsupported quant type".to_string()),
    }
    let stdout = io::stdout();
    let mut locked = stdout.lock();
    for value in decoded {
        locked
            .write_all(&value.to_le_bytes())
            .map_err(|error| format!("stdout write failed: {error}"))?;
    }
    locked.flush().map_err(|error| format!("stdout flush failed: {error}"))
}

fn main() {
    if let Err(error) = run() {
        eprintln!("{error}");
        std::process::exit(2);
    }
}
