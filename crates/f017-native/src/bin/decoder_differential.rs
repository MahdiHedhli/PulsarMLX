//! Checkpoint-free decoder differential producer (glm52-weekend W3). Reads a
//! JSON case file, decodes every case through the secure loader's exact
//! qualification dispatch (`decode_packed_matrix_for_qualification`, the same
//! `decode` the real P1 path uses), and writes the decoded f32 values as
//! little-endian hex so an independent Python driver can compare them against
//! the corrected oracle's scalar decoders. No filesystem or checkpoint
//! capability beyond the two operand paths; no numerical reference here.

use f017_native::loader::decode_packed_matrix_for_qualification;
use serde::{Deserialize, Serialize};
use std::fs;

#[derive(Deserialize)]
struct Case {
    id: String,
    format: String,
    type_id: u32,
    rows: usize,
    columns: usize,
    bytes_hex: String,
}

#[derive(Deserialize)]
struct Cases {
    cases: Vec<Case>,
}

#[derive(Serialize)]
struct Decoded {
    id: String,
    format: String,
    rows: usize,
    columns: usize,
    result: String,
    values_f32le_hex: Option<String>,
    error: Option<String>,
}

fn unhex(s: &str) -> Result<Vec<u8>, String> {
    if s.len() % 2 != 0 {
        return Err("odd hex".into());
    }
    (0..s.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(&s[i..i + 2], 16).map_err(|e| e.to_string()))
        .collect()
}

fn main() -> Result<(), String> {
    let args: Vec<String> = std::env::args().collect();
    if args.len() != 3 {
        return Err("usage: f017-native-decoder-differential CASES_JSON OUT_JSON".into());
    }
    let cases: Cases =
        serde_json::from_slice(&fs::read(&args[1]).map_err(|e| e.to_string())?).map_err(|e| e.to_string())?;
    let mut out = Vec::with_capacity(cases.cases.len());
    for c in cases.cases {
        let bytes = unhex(&c.bytes_hex)?;
        let decoded = decode_packed_matrix_for_qualification(&c.format, c.type_id, &bytes, c.rows, c.columns);
        out.push(match decoded {
            Ok(values) => {
                let mut hex = String::with_capacity(values.len() * 8);
                for v in &values {
                    for b in v.to_le_bytes() {
                        hex.push_str(&format!("{b:02x}"));
                    }
                }
                Decoded { id: c.id, format: c.format, rows: c.rows, columns: c.columns, result: "OK".into(), values_f32le_hex: Some(hex), error: None }
            }
            Err(e) => Decoded { id: c.id, format: c.format, rows: c.rows, columns: c.columns, result: "ERROR".into(), values_f32le_hex: None, error: Some(e) },
        });
    }
    let body = serde_json::json!({"schema": "pulsarmlx.f017.decoder-differential-producer/1.0.0", "producer": "f017-native decode_packed_matrix_for_qualification", "decoded": out});
    fs::write(&args[2], serde_json::to_vec_pretty(&body).map_err(|e| e.to_string())?).map_err(|e| e.to_string())?;
    Ok(())
}
