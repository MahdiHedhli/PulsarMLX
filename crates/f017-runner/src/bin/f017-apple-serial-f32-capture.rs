//! Future Apple production serial-f32 capture entry point.
//!
//! The retained-only phase compiles and tests this binary but never invokes
//! `--execute`. Execution requires a wrapper-owned durable attempt record at a
//! fixed contract path; this binary has no checkpoint or shard interface.

use f017_runner::apple_serial_f32::{
    run_apple_serial_f32, AppleGraphError, AppleLayerInputs, AppleLayerMatrices, CaptureSink,
    DenseMatrix, ExpertMatrices, ProjectionBackend,
};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fs::{self, OpenOptions};
use std::io::{Read, Write};
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
use std::path::{Path, PathBuf};

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct TensorSpec {
    path: PathBuf,
    sha256: String,
    encoding: String,
    shape: Vec<usize>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct RuntimeSpec {
    device: String,
    mlx_version: String,
    mlx_c_version: String,
    libmlx_sha256: String,
    libmlxc_sha256: String,
    backend: String,
    thread_limits: BTreeMap<String, String>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Package {
    schema: String,
    schema_version: String,
    graph_version: String,
    execution_code_head: String,
    fixed_attempt_root: PathBuf,
    fixed_capture_root: PathBuf,
    tensors: BTreeMap<String, TensorSpec>,
    position: usize,
    rope_base: f32,
    attention_scale: f32,
    expert_weight_scale: f32,
    heads: usize,
    qk_nope: usize,
    qk_rope: usize,
    kv_lora: usize,
    value_dim: usize,
    routed_expert_ids: Vec<usize>,
    runtime: RuntimeSpec,
    checkpoint_paths: Vec<String>,
}

#[derive(Debug, Serialize)]
struct CaptureRow {
    ordinal: usize,
    stage_id: String,
    shape: Vec<usize>,
    dtype: &'static str,
    byte_length: usize,
    sha256: String,
    path: String,
    direct_production_copy: bool,
}

fn sha_bytes(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn fsync_directory(path: &Path) -> Result<(), String> {
    fs::File::open(path)
        .and_then(|file| file.sync_all())
        .map_err(|e| format!("DIRECTORY_FSYNC: {e}"))
}

fn publish_bytes(path: &Path, bytes: &[u8]) -> Result<String, String> {
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o400)
        .open(path)
        .map_err(|e| format!("PUBLICATION_CREATE: {e}"))?;
    file.write_all(bytes)
        .and_then(|_| file.sync_all())
        .map_err(|e| format!("PUBLICATION_WRITE: {e}"))?;
    fsync_directory(path.parent().ok_or("PUBLICATION_PARENT")?)?;
    let expected = sha_bytes(bytes);
    let readback = open_once(path, &expected)?;
    if readback != bytes {
        return Err("PUBLICATION_READBACK".into());
    }
    Ok(expected)
}

fn load_unique_json(path: &Path) -> Result<Package, String> {
    let bytes = fs::read(path).map_err(|e| format!("PACKAGE_READ: {e}"))?;
    f017_runner::json::parse_json_no_duplicates(&bytes)
}

fn open_once(path: &Path, expected: &str) -> Result<Vec<u8>, String> {
    let before = fs::symlink_metadata(path).map_err(|e| format!("INPUT_STAT: {e}"))?;
    if !before.file_type().is_file() || before.file_type().is_symlink() || before.nlink() != 1 {
        return Err("INPUT_FILE_POLICY".into());
    }
    if before.mode() & 0o222 != 0 {
        return Err("INPUT_READ_ONLY".into());
    }
    let mut file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW)
        .open(path)
        .map_err(|e| format!("INPUT_OPEN: {e}"))?;
    let opened = file.metadata().map_err(|e| format!("INPUT_FSTAT: {e}"))?;
    if before.dev() != opened.dev() || before.ino() != opened.ino() {
        return Err("INPUT_DESCRIPTOR_SUBSTITUTION".into());
    }
    let mut bytes = Vec::new();
    file.read_to_end(&mut bytes)
        .map_err(|e| format!("INPUT_READ: {e}"))?;
    if sha_bytes(&bytes) != expected {
        return Err("INPUT_SHA".into());
    }
    let after = file.metadata().map_err(|e| format!("INPUT_AFTER: {e}"))?;
    if opened.dev() != after.dev() || opened.ino() != after.ino() || opened.len() != after.len() {
        return Err("INPUT_AFTER_IDENTITY".into());
    }
    Ok(bytes)
}

fn f32le(bytes: &[u8], count: usize) -> Result<Vec<f32>, String> {
    if bytes.len() != count.checked_mul(4).ok_or("F32_SIZE")? {
        return Err("F32_SIZE".into());
    }
    let output = bytes
        .chunks_exact(4)
        .map(|v| f32::from_le_bytes(v.try_into().unwrap()))
        .collect::<Vec<_>>();
    if output.iter().any(|v| !v.is_finite()) {
        return Err("F32_NONFINITE".into());
    }
    Ok(output)
}

fn decode(spec: &TensorSpec) -> Result<Vec<f32>, String> {
    let bytes = open_once(&spec.path, &spec.sha256)?;
    let count = spec
        .shape
        .iter()
        .try_fold(1_usize, |a, &b| a.checked_mul(b))
        .ok_or("SHAPE_OVERFLOW")?;
    let columns = *spec.shape.last().ok_or("SHAPE_EMPTY")?;
    let rows = if spec.shape.len() == 1 {
        1
    } else {
        spec.shape[..spec.shape.len() - 1]
            .iter()
            .try_fold(1_usize, |a, &b| a.checked_mul(b))
            .ok_or("SHAPE_OVERFLOW")?
    };
    let mut output = vec![0.0_f32; count];
    match spec.encoding.as_str() {
        "F32_LE" => return f32le(&bytes, count),
        "Q4_K" => {
            let row_bytes = columns / 256 * 144;
            if columns % 256 != 0 || bytes.len() != rows * row_bytes {
                return Err("Q4_K_LAYOUT".into());
            }
            for row in 0..rows {
                let decoded = quant::cpu_dot::dequant_q4_k(
                    &bytes[row * row_bytes..(row + 1) * row_bytes],
                    columns,
                );
                if decoded.len() != columns {
                    return Err("Q4_K_DECODE".into());
                }
                output[row * columns..(row + 1) * columns].copy_from_slice(&decoded);
            }
        }
        "Q5_K" => {
            let row_bytes = columns / 256 * 176;
            if columns % 256 != 0 || bytes.len() != rows * row_bytes {
                return Err("Q5_K_LAYOUT".into());
            }
            for row in 0..rows {
                let decoded = quant::cpu_dot::dequant_q5_k(
                    &bytes[row * row_bytes..(row + 1) * row_bytes],
                    columns,
                );
                if decoded.len() != columns {
                    return Err("Q5_K_DECODE".into());
                }
                output[row * columns..(row + 1) * columns].copy_from_slice(&decoded);
            }
        }
        "Q6_K" => quant::decode_q6_k_matrix(&bytes, rows, columns, &mut output)
            .map_err(|e| format!("Q6_K_DECODE: {e:?}"))?,
        "Q8_0" => quant::decode_q8_0_matrix(&bytes, rows, columns, &mut output)
            .map_err(|e| format!("Q8_0_DECODE: {e:?}"))?,
        "IQ2_XXS" => quant::decode_iq2_xxs_matrix(&bytes, rows, columns, &mut output)
            .map_err(|e| format!("IQ2_XXS_DECODE: {e:?}"))?,
        "IQ3_XXS" => quant::decode_iq3_xxs_matrix(&bytes, rows, columns, &mut output)
            .map_err(|e| format!("IQ3_XXS_DECODE: {e:?}"))?,
        _ => return Err("ENCODING".into()),
    }
    if output.iter().any(|v| !v.is_finite()) {
        return Err("DECODE_NONFINITE".into());
    }
    Ok(output)
}

fn tensor<'a>(package: &'a Package, role: &str) -> Result<&'a TensorSpec, String> {
    package
        .tensors
        .get(role)
        .ok_or_else(|| format!("MISSING_TENSOR: {role}"))
}

fn matrix(package: &Package, role: &str) -> Result<DenseMatrix, String> {
    let spec = tensor(package, role)?;
    if spec.shape.len() < 2 {
        return Err(format!("MATRIX_SHAPE: {role}"));
    }
    let columns = *spec.shape.last().unwrap();
    let rows = spec.shape[..spec.shape.len() - 1].iter().product();
    Ok(DenseMatrix {
        rows,
        columns,
        values: decode(spec)?,
    })
}

fn vector(package: &Package, role: &str) -> Result<Vec<f32>, String> {
    let spec = tensor(package, role)?;
    if spec.shape.len() != 1 {
        return Err(format!("VECTOR_SHAPE: {role}"));
    }
    decode(spec)
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
struct MlxBackend {
    context: stream::MlxContext,
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
impl MlxBackend {
    fn new() -> Result<Self, String> {
        Ok(Self {
            context: stream::MlxContext::new(stream::MlxDevice::Gpu, stream::MlxStreamMode::Owned)?,
        })
    }
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
impl ProjectionBackend for MlxBackend {
    fn matvec(
        &mut self,
        role: &'static str,
        matrix: &DenseMatrix,
        vector: &[f32],
    ) -> Result<Vec<f32>, AppleGraphError> {
        if vector.len() != matrix.columns {
            return Err(AppleGraphError::InvalidShape(role));
        }
        let mut matrix_owner = matrix.values.clone();
        let mut vector_owner = vector.to_vec();
        let matrix_array = self
            .context
            .import_f32_shaped(&mut matrix_owner, &[matrix.rows, matrix.columns])
            .map_err(|_| AppleGraphError::Backend(role))?;
        let vector_array = self
            .context
            .import_f32(&mut vector_owner)
            .map_err(|_| AppleGraphError::Backend(role))?;
        let computed = matrix_array
            .matvec(&vector_array)
            .map_err(|_| AppleGraphError::Backend(role))?;
        computed
            .evaluate_sync()
            .map_err(|_| AppleGraphError::Backend(role))?;
        let mut output = vec![0.0_f32; matrix.rows];
        computed
            .copy_f32(&mut output)
            .map_err(|_| AppleGraphError::Backend(role))?;
        Ok(output)
    }
}

struct DirectoryCapture {
    root: PathBuf,
    rows: Vec<CaptureRow>,
}

impl CaptureSink for DirectoryCapture {
    fn capture(
        &mut self,
        stage_id: &'static str,
        shape: &[usize],
        values: &[f32],
    ) -> Result<(), AppleGraphError> {
        let bytes = values
            .iter()
            .flat_map(|v| v.to_le_bytes())
            .collect::<Vec<_>>();
        let name = format!("{:02}-{stage_id}.f32le", self.rows.len());
        let path = self.root.join(&name);
        let published_sha =
            publish_bytes(&path, &bytes).map_err(|_| AppleGraphError::Capture(stage_id))?;
        self.rows.push(CaptureRow {
            ordinal: self.rows.len(),
            stage_id: stage_id.into(),
            shape: shape.to_vec(),
            dtype: "little-endian-f32",
            byte_length: bytes.len(),
            sha256: published_sha,
            path: name,
            direct_production_copy: true,
        });
        Ok(())
    }

    fn capture_u16(
        &mut self,
        stage_id: &'static str,
        shape: &[usize],
        values: &[u16],
    ) -> Result<(), AppleGraphError> {
        let bytes = values
            .iter()
            .flat_map(|v| v.to_le_bytes())
            .collect::<Vec<_>>();
        let name = format!("{:02}-{stage_id}.u16le", self.rows.len());
        let path = self.root.join(&name);
        let published_sha =
            publish_bytes(&path, &bytes).map_err(|_| AppleGraphError::Capture(stage_id))?;
        self.rows.push(CaptureRow {
            ordinal: self.rows.len(),
            stage_id: stage_id.into(),
            shape: shape.to_vec(),
            dtype: "little-endian-u16",
            byte_length: bytes.len(),
            sha256: published_sha,
            path: name,
            direct_production_copy: true,
        });
        Ok(())
    }
}

fn validate_package(package: &Package) -> Result<(), String> {
    if package.schema != "pulsarmlx.f017.apple-production-serial-f32-package"
        || package.schema_version != "1.0.0"
        || package.graph_version != f017_runner::apple_serial_f32::APPLE_SERIAL_F32_GRAPH_VERSION
        || package.checkpoint_paths.len() != 0
        || package.routed_expert_ids != [250, 10, 237, 62, 73, 177, 218, 28]
        || package.runtime.device != "APPLE_METAL_GPU"
        || package.runtime.backend != "MLX_C_MATVEC_PLUS_RUST_SERIAL_F32"
        || package.runtime.mlx_version != "0.32.1"
        || package.runtime.mlx_c_version != "0.6.0_4"
        || package.runtime.libmlx_sha256
            != "c30b1529178de28d23817e6e73ea5133cf63af060379c41a27aa7420aa616b3d"
        || package.runtime.libmlxc_sha256
            != "9882fe1f7ec1fcdb10cebde60e88b41826ab4dfed8ae624b99be419d6fa89561"
        || package.runtime.thread_limits.values().any(|v| v != "1")
        || package.execution_code_head.len() != 40
        || !package.fixed_attempt_root.is_absolute()
        || !package.fixed_capture_root.is_absolute()
        || package.position != 0
        || package.attention_scale.to_bits() != 0.0625_f32.to_bits()
        || package.expert_weight_scale.to_bits() != 2.5_f32.to_bits()
        || package.heads != 64
        || package.qk_nope != 192
        || package.qk_rope != 64
        || package.kv_lora != 512
        || package.value_dim != 256
    {
        return Err("PACKAGE_POLICY".into());
    }
    let required = [
        "s0",
        "attention_norm_scale",
        "q_rank_norm_scale",
        "kv_norm_scale",
        "ffn_norm_scale",
        "correction_bias",
        "q_a",
        "q_b",
        "kv_a",
        "k_b",
        "v_b",
        "attention_output",
        "router",
        "shared.gate",
        "shared.up",
        "shared.down",
    ];
    if required.iter().any(|r| !package.tensors.contains_key(*r)) {
        return Err("PACKAGE_TENSOR_CENSUS".into());
    }
    for slot in 0..8 {
        for suffix in ["gate", "up", "down"] {
            if !package
                .tensors
                .contains_key(&format!("routed.{slot}.{suffix}"))
            {
                return Err("PACKAGE_ROUTED_CENSUS".into());
            }
        }
    }
    let mut expected = BTreeMap::from([
        ("s0".to_owned(), ("F32_LE", vec![6144])),
        ("attention_norm_scale".to_owned(), ("F32_LE", vec![6144])),
        ("q_rank_norm_scale".to_owned(), ("F32_LE", vec![2048])),
        ("kv_norm_scale".to_owned(), ("F32_LE", vec![512])),
        ("ffn_norm_scale".to_owned(), ("F32_LE", vec![6144])),
        ("correction_bias".to_owned(), ("F32_LE", vec![256])),
        ("q_a".to_owned(), ("Q5_K", vec![2048, 6144])),
        ("q_b".to_owned(), ("Q8_0", vec![64, 256, 2048])),
        ("kv_a".to_owned(), ("Q8_0", vec![576, 6144])),
        ("k_b".to_owned(), ("Q8_0", vec![64, 512, 192])),
        ("v_b".to_owned(), ("Q8_0", vec![64, 256, 512])),
        ("attention_output".to_owned(), ("Q5_K", vec![6144, 16384])),
        ("router".to_owned(), ("F32_LE", vec![256, 6144])),
        ("shared.gate".to_owned(), ("Q5_K", vec![2048, 6144])),
        ("shared.up".to_owned(), ("Q5_K", vec![2048, 6144])),
        ("shared.down".to_owned(), ("Q6_K", vec![6144, 2048])),
    ]);
    for slot in 0..8 {
        expected.insert(format!("routed.{slot}.gate"), ("IQ2_XXS", vec![2048, 6144]));
        expected.insert(format!("routed.{slot}.up"), ("IQ2_XXS", vec![2048, 6144]));
        expected.insert(format!("routed.{slot}.down"), ("IQ3_XXS", vec![6144, 2048]));
    }
    if package.tensors.len() != expected.len() {
        return Err("PACKAGE_EXTRA_OR_MISSING_TENSOR".into());
    }
    for (role, (encoding, shape)) in expected {
        let spec = package
            .tensors
            .get(&role)
            .ok_or_else(|| format!("PACKAGE_TENSOR:{role}"))?;
        if spec.encoding != encoding || spec.shape != shape || !spec.path.is_absolute() {
            return Err(format!("PACKAGE_TENSOR_AUTHORITY:{role}"));
        }
    }
    Ok(())
}

fn main() -> Result<(), String> {
    let arguments = std::env::args().collect::<Vec<_>>();
    let package_at = arguments
        .iter()
        .position(|v| v == "--package")
        .and_then(|i| arguments.get(i + 1))
        .ok_or("USAGE: --package PATH (--preflight-only|--execute)")?;
    let package = load_unique_json(Path::new(package_at))?;
    validate_package(&package)?;
    if arguments.iter().any(|v| v == "--preflight-only") {
        println!("PRODUCTION_BINDINGS_SCHEMA_RESOLVED_NO_INPUT_READ_NO_ARITHMETIC");
        return Ok(());
    }
    if !arguments.iter().any(|v| v == "--execute") {
        return Err("MODE".into());
    }
    let owner_path = package.fixed_attempt_root.join("owner.json");
    let owner_sha = std::env::var("PULSARMLX_F017_OWNED_ATTEMPT_SHA256")
        .map_err(|_| "WRAPPER_OWNERSHIP_REQUIRED")?;
    let _owner = open_once(&owner_path, &owner_sha)?;
    if package.fixed_capture_root.exists() {
        return Err("CAPTURE_ROOT_EXISTS".into());
    }

    let routed = package
        .routed_expert_ids
        .iter()
        .enumerate()
        .map(|(slot, &id)| {
            Ok(ExpertMatrices {
                expert_id: id,
                gate: matrix(&package, &format!("routed.{slot}.gate"))?,
                up: matrix(&package, &format!("routed.{slot}.up"))?,
                down: matrix(&package, &format!("routed.{slot}.down"))?,
            })
        })
        .collect::<Result<Vec<_>, String>>()?;
    let matrices = AppleLayerMatrices {
        q_a: matrix(&package, "q_a")?,
        q_b: matrix(&package, "q_b")?,
        kv_a: matrix(&package, "kv_a")?,
        k_b: matrix(&package, "k_b")?,
        v_b: matrix(&package, "v_b")?,
        attention_output: matrix(&package, "attention_output")?,
        router: matrix(&package, "router")?,
        routed,
        shared: ExpertMatrices {
            expert_id: usize::MAX,
            gate: matrix(&package, "shared.gate")?,
            up: matrix(&package, "shared.up")?,
            down: matrix(&package, "shared.down")?,
        },
    };
    let inputs = AppleLayerInputs {
        s0: vector(&package, "s0")?,
        attention_norm_scale: vector(&package, "attention_norm_scale")?,
        q_rank_norm_scale: vector(&package, "q_rank_norm_scale")?,
        kv_norm_scale: vector(&package, "kv_norm_scale")?,
        ffn_norm_scale: vector(&package, "ffn_norm_scale")?,
        correction_bias: vector(&package, "correction_bias")?,
        position: package.position,
        rope_base: package.rope_base,
        attention_scale: package.attention_scale,
        expert_weight_scale: package.expert_weight_scale,
        heads: package.heads,
        qk_nope: package.qk_nope,
        qk_rope: package.qk_rope,
        kv_lora: package.kv_lora,
        value_dim: package.value_dim,
    };
    if package.fixed_capture_root.exists() {
        return Err("CAPTURE_ROOT_CHANGED_DURING_PREFLIGHT".into());
    }
    fs::create_dir(&package.fixed_capture_root).map_err(|e| format!("CAPTURE_ROOT: {e}"))?;
    fsync_directory(
        package
            .fixed_capture_root
            .parent()
            .ok_or("CAPTURE_ROOT_PARENT")?,
    )?;
    let mut capture = DirectoryCapture {
        root: package.fixed_capture_root.clone(),
        rows: Vec::new(),
    };
    #[cfg(all(target_os = "macos", pulsar_native_mlx))]
    {
        let mut backend = MlxBackend::new()?;
        let result = run_apple_serial_f32(&mut backend, &mut capture, &matrices, &inputs)
            .map_err(|e| e.to_string())?;
        let manifest_bytes = serde_json::to_vec_pretty(&serde_json::json!({"schema":"pulsarmlx.f017.apple-production-serial-f32-capture-manifest","schema_version":"1.0.0","stages":capture.rows,"s2_sha256":sha_bytes(&result.s2.iter().flat_map(|v|v.to_le_bytes()).collect::<Vec<_>>())})).unwrap();
        let path = package.fixed_capture_root.join("capture-manifest.json");
        publish_bytes(&path, &manifest_bytes)?;
        return Ok(());
    }
    #[cfg(not(all(target_os = "macos", pulsar_native_mlx)))]
    Err("PINNED_NATIVE_MLX_REQUIRED".into())
}
