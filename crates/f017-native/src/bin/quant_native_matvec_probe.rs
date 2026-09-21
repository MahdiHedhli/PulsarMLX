//! Checkpoint-incapable packed-decoder plus native-MLX matvec probe.

use f017_native::loader::decode_packed_matrix_for_qualification;
use f017_native::model::{Matrix, MatvecBackend, NativeMlxBackend};
use serde::{Deserialize, Serialize};
use std::io::{Read, Write};
use stream::{MlxContext, MlxDevice, MlxStreamMode};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Request {
    format: String,
    type_id: u32,
    rows: usize,
    columns: usize,
    encoded_hex: String,
    activation_f32_bits: Vec<u32>,
}

#[derive(Serialize)]
struct Response {
    format: String,
    type_id: u32,
    rows: usize,
    columns: usize,
    decoded_f32_bits: Vec<u32>,
    output_f32_bits: Vec<u32>,
    backend: &'static str,
    original_checkpoint_reads: u32,
}

fn decode_hex(value: &str) -> Result<Vec<u8>, String> {
    if value.len() % 2 != 0 {
        return Err("odd hex length".into());
    }
    value
        .as_bytes()
        .chunks_exact(2)
        .map(|pair| {
            let text = std::str::from_utf8(pair).map_err(|error| error.to_string())?;
            u8::from_str_radix(text, 16).map_err(|error| error.to_string())
        })
        .collect()
}

fn run() -> Result<(), String> {
    let mut bytes = Vec::new();
    std::io::stdin()
        .read_to_end(&mut bytes)
        .map_err(|error| error.to_string())?;
    let request: Request = f017_native::json::parse_json_no_duplicates(&bytes)?;
    if request.rows == 0
        || request.columns == 0
        || request.activation_f32_bits.len() != request.columns
    {
        return Err("qualification shape".into());
    }
    let encoded = decode_hex(&request.encoded_hex)?;
    let decoded = decode_packed_matrix_for_qualification(
        &request.format,
        request.type_id,
        &encoded,
        request.rows,
        request.columns,
    )?;
    let activation = request
        .activation_f32_bits
        .iter()
        .map(|bits| f32::from_bits(*bits))
        .collect::<Vec<_>>();
    let matrix = Matrix {
        rows: request.rows,
        columns: request.columns,
        values: decoded.clone(),
    };
    let context = MlxContext::new(MlxDevice::Gpu, MlxStreamMode::Owned)?;
    let output = NativeMlxBackend { context: &context }.matvec(
        "synthetic_packed_qualification",
        &matrix,
        &activation,
    )?;
    context.synchronize()?;
    let response = Response {
        format: request.format,
        type_id: request.type_id,
        rows: request.rows,
        columns: request.columns,
        decoded_f32_bits: decoded.iter().map(|value| value.to_bits()).collect(),
        output_f32_bits: output.iter().map(|value| value.to_bits()).collect(),
        backend: "NATIVE_MLX_DECODED_F32_MATVEC",
        original_checkpoint_reads: 0,
    };
    let mut rendered = serde_json::to_vec(&response).map_err(|error| error.to_string())?;
    rendered.push(b'\n');
    std::io::stdout()
        .write_all(&rendered)
        .map_err(|error| error.to_string())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("{error}");
        std::process::exit(2);
    }
}
