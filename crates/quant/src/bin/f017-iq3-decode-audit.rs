use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::PathBuf;

use quant::decode_iq3_xxs_matrix;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = std::env::args_os();
    let _program = args.next();
    let input = PathBuf::from(args.next().ok_or("missing packed input")?);
    let output = PathBuf::from(args.next().ok_or("missing decoded output")?);
    let rows: usize = args
        .next()
        .ok_or("missing rows")?
        .to_string_lossy()
        .parse()?;
    let columns: usize = args
        .next()
        .ok_or("missing columns")?
        .to_string_lossy()
        .parse()?;
    if args.next().is_some() {
        return Err("unexpected argument".into());
    }

    let packed = fs::read(&input)?;
    let output_len = rows.checked_mul(columns).ok_or("output length overflow")?;
    let mut decoded = vec![0.0_f32; output_len];
    decode_iq3_xxs_matrix(&packed, rows, columns, &mut decoded)
        .map_err(|error| format!("IQ3_XXS decode failed: {error:?}"))?;

    let mut bytes = Vec::with_capacity(output_len * 4);
    for value in &decoded {
        bytes.extend_from_slice(&value.to_le_bytes());
    }
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&output)?;
    file.write_all(&bytes)?;
    file.sync_all()?;
    println!(
        "decoded_elements={} decoded_bytes={} rows={} columns={}",
        decoded.len(),
        bytes.len(),
        rows,
        columns
    );
    Ok(())
}
