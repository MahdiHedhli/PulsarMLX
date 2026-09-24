//! The Slice 2B R1 self-checks over the frozen fixture population.
//!
//! This is an R1-vs-R1 check (contract B5), not a candidate observation: the
//! Rust binary64 R1 (`reference_qmm`) is run on every frozen case that carries
//! `rust_binary64_r1` (298), its values are written as binary64 bit patterns,
//! and the exact Python R1 (`scripts/research/mlx_affine_qmm_reference_v1.py`)
//! decides N-R1-SELF (G-R1-SELF-QMM, 237 cases) and N-R1-SELF-DQ (G-R1-SELF-DQ,
//! 59 cases) by exact rational comparison, as the contract requires. Nothing
//! here touches MLX, the native candidate or the production R3 path.
//!
//! The interpreter is `python3` unless `PULSAR_R1_PYTHON` names another; an
//! unavailable interpreter is a failure, not a skip. Setting
//! `PULSAR_R1_RUST_OUT=<path>` also writes the Rust R1 values there.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::process::Command;

use mlx_affine::reference_qmm::{dq_reference, qmm_reference, QmmMetadata};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};

const MANIFEST_SHA256: &str = "472b5b64aaddfe7ecbfd05930ba2f4d261023a9a829f957b5b23b110fcf37d04";
const RUST_SCHEMA: &str = "pulsarmlx.f020.r1-rust-binary64/1.0.0";

fn repository() -> PathBuf {
    [env!("CARGO_MANIFEST_DIR"), "..", ".."].iter().collect()
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

fn bits_hex(values: &[f64]) -> Vec<String> {
    values
        .iter()
        .map(|v| format!("{:016x}", v.to_bits()))
        .collect()
}

struct Tensor {
    dtype: String,
    shape: Vec<usize>,
    bytes: Vec<u8>,
}

impl Tensor {
    fn words(&self) -> Vec<u32> {
        assert!(self.dtype == "U32" || self.dtype == "F32");
        self.bytes
            .chunks_exact(4)
            .map(|c| u32::from_le_bytes([c[0], c[1], c[2], c[3]]))
            .collect()
    }

    fn halves(&self) -> Vec<u16> {
        assert!(self.dtype == "F16" || self.dtype == "BF16");
        self.bytes
            .chunks_exact(2)
            .map(|c| u16::from_le_bytes([c[0], c[1]]))
            .collect()
    }
}

fn tensors(case: &Value, cases_dir: &Path) -> BTreeMap<String, Tensor> {
    let file = cases_dir.join(case["file"].as_str().unwrap());
    let blob = std::fs::read(&file).unwrap();
    assert_eq!(
        hex(&Sha256::digest(&blob)),
        case["file_sha256"].as_str().unwrap(),
        "{}",
        case["id"]
    );
    let mut out = BTreeMap::new();
    for spec in case["tensors"].as_array().unwrap() {
        let offset = spec["offset"].as_u64().unwrap() as usize;
        let nbytes = spec["nbytes"].as_u64().unwrap() as usize;
        let bytes = blob[offset..offset + nbytes].to_vec();
        assert_eq!(
            hex(&Sha256::digest(&bytes)),
            spec["sha256"].as_str().unwrap()
        );
        out.insert(
            spec["name"].as_str().unwrap().to_string(),
            Tensor {
                dtype: spec["dtype"].as_str().unwrap().to_string(),
                shape: spec["shape"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .map(|d| d.as_u64().unwrap() as usize)
                    .collect(),
                bytes,
            },
        );
    }
    out
}

/// The Rust R1 of one frozen case, as the dump record the exact R1 reads.
fn rust_r1(case: &Value, cases_dir: &Path) -> Value {
    let t = tensors(case, cases_dir);
    let params = &case["params"];
    let bits = params["bits"].as_u64().unwrap() as u32;
    let group = params["group_size"].as_u64().unwrap() as usize;
    let k = params["K"].as_u64().unwrap() as usize;
    let w = t["w"].words();
    let rows = t["w"].shape[0];
    let (scale_halves, bias_halves, scale_words, bias_words);
    let meta = match t["scales"].dtype.as_str() {
        "F16" | "BF16" => {
            assert_eq!(t["biases"].dtype, t["scales"].dtype);
            scale_halves = t["scales"].halves();
            bias_halves = t["biases"].halves();
            if t["scales"].dtype == "F16" {
                QmmMetadata::F16 {
                    scales: &scale_halves,
                    biases: &bias_halves,
                }
            } else {
                QmmMetadata::Bf16 {
                    scales: &scale_halves,
                    biases: &bias_halves,
                }
            }
        }
        "F32" => {
            assert_eq!(t["biases"].dtype, "F32");
            scale_words = t["scales"].words();
            bias_words = t["biases"].words();
            QmmMetadata::F32 {
                scales: &scale_words,
                biases: &bias_words,
            }
        }
        other => panic!("unexpected metadata dtype {other}"),
    };
    match case["op"].as_str().unwrap() {
        "quantized_matmul" => {
            let x = &t["x"];
            assert_eq!(x.dtype, "F32");
            assert_eq!(*x.shape.last().unwrap(), k);
            let m: usize = x.shape[..x.shape.len() - 1].iter().product();
            assert_eq!(m as u64, params["M_eff"].as_u64().unwrap());
            assert_eq!(rows as u64, params["N"].as_u64().unwrap());
            let r = qmm_reference(&x.words(), &w, meta, m, rows, k, bits, group).unwrap();
            assert!(r.y.iter().all(|v| v.is_finite()));
            assert!(r.phi.iter().all(|v| v.is_finite() && *v >= 0.0));
            json!({"op": "quantized_matmul", "m_eff": m, "n": rows, "k": k,
                   "y": bits_hex(&r.y), "phi": bits_hex(&r.phi)})
        }
        "dequantize" => {
            assert_eq!(rows as u64, params["rows"].as_u64().unwrap());
            let r = dq_reference(&w, meta, rows, k, bits, group).unwrap();
            assert!(r.w.iter().chain(r.p.iter()).all(|v| v.is_finite()));
            json!({"op": "dequantize", "rows": rows, "k": k,
                   "w": bits_hex(&r.w), "p": bits_hex(&r.p)})
        }
        other => panic!("no R1 for op {other}"),
    }
}

fn references(case: &Value) -> Vec<&str> {
    case["references"]
        .as_array()
        .unwrap()
        .iter()
        .map(|r| r.as_str().unwrap())
        .collect()
}

#[test]
fn r1_self_checks_hold_on_the_frozen_population() {
    let root = repository();
    let cases_dir = root.join("fixtures/native-primitives");
    let manifest_path = cases_dir.join("manifest.json");
    let raw = std::fs::read(&manifest_path).unwrap();
    assert_eq!(hex(&Sha256::digest(&raw)), MANIFEST_SHA256);
    let manifest: Value = serde_json::from_slice(&raw).unwrap();
    let cases = manifest["cases"].as_array().unwrap();
    assert_eq!(cases.len(), 363);

    let rust: Vec<&Value> = cases
        .iter()
        .filter(|c| references(c).contains(&"rust_binary64_r1"))
        .collect();
    let exact = cases
        .iter()
        .filter(|c| references(c).contains(&"python_exact_r1"))
        .count();
    let dual_qmm = rust
        .iter()
        .filter(|c| references(c).contains(&"python_exact_r1") && c["op"] == "quantized_matmul")
        .count();
    let dual_dq = rust
        .iter()
        .filter(|c| references(c).contains(&"python_exact_r1") && c["op"] == "dequantize")
        .count();
    assert_eq!((rust.len(), exact, dual_qmm, dual_dq), (298, 296, 237, 59));

    let mut dump = serde_json::Map::new();
    for case in &rust {
        let id = case["id"].as_str().unwrap().to_string();
        dump.insert(id, rust_r1(case, &cases_dir));
    }
    assert_eq!(dump.len(), 298);
    let document = json!({"schema": RUST_SCHEMA, "manifest_sha256": MANIFEST_SHA256,
                          "cases": Value::Object(dump)});
    let text = serde_json::to_string(&document).unwrap();

    let scratch = PathBuf::from(env!("CARGO_TARGET_TMPDIR")).join("reference_qmm_frozen");
    std::fs::create_dir_all(&scratch).unwrap();
    let rust_path = scratch.join("r1-rust.json");
    let exact_path = scratch.join("r1-exact.json");
    std::fs::write(&rust_path, &text).unwrap();
    if let Ok(extra) = std::env::var("PULSAR_R1_RUST_OUT") {
        std::fs::write(extra, &text).unwrap();
    }

    let python = std::env::var("PULSAR_R1_PYTHON").unwrap_or_else(|_| "python3".to_string());
    let output = Command::new(&python)
        .arg(root.join("scripts/research/mlx_affine_qmm_reference_v1.py"))
        .arg("--manifest")
        .arg(&manifest_path)
        .arg("--cases-dir")
        .arg(&cases_dir)
        .arg("--all")
        .arg("--out")
        .arg(&exact_path)
        .arg("--rust-r1")
        .arg(&rust_path)
        .output()
        .unwrap_or_else(|error| panic!("{python} could not be started: {error}"));
    let stdout = String::from_utf8_lossy(&output.stdout);
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert_eq!(
        output.status.code(),
        Some(0),
        "exact R1 self-check failed\nstdout: {stdout}\nstderr: {stderr}"
    );

    let report: Value = serde_json::from_slice(&std::fs::read(&exact_path).unwrap()).unwrap();
    assert_eq!(report["manifest_sha256"], MANIFEST_SHA256);
    assert_eq!(report["case_count"], 296);
    let check = &report["r1_self_check"];
    assert_eq!(check["result"], "PASS", "{check}");
    assert_eq!(check["dual_reference_cases"], 296);
    assert_eq!(check["missing_cases"], json!([]));
    for (name, count) in [
        ("N-R1-SELF", 237),
        ("N-R1-SELF-DQ", 59),
        ("phi_hat_reference_error", 237),
        ("p_hat_exact", 59),
    ] {
        assert_eq!(check[name]["cases"], count, "{name}");
        assert_eq!(check[name]["passed_cases"], count, "{name}");
        assert_eq!(check[name]["failed_elements"], 0, "{name}");
        assert_eq!(check[name]["failed_cases"], json!([]), "{name}");
    }
    println!("{stdout}");
}
