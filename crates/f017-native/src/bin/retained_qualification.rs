//! Future Apple production serial-f32 capture entry point.
//!
//! The retained-only phase compiles and tests this binary but never invokes
//! `--execute`. Execution requires a wrapper-owned durable attempt record at a
//! fixed contract path; this binary has no checkpoint or shard interface.

use stream::f017_apple_serial_f32::{
    run_apple_serial_f32, AppleGraphError, AppleLayerInputs, AppleLayerMatrices, CaptureSink,
    DenseMatrix, ExpertMatrices, ProjectionBackend,
};
use f017_native::retained::{
    load_grant, load_package, GrantedInputs, RetainedPackage as Package, TensorSpec,
};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fs::{self, OpenOptions};
use std::io::{Read, Write};
use std::os::unix::fs::{MetadataExt, OpenOptionsExt, PermissionsExt};
use std::path::{Path, PathBuf};

#[derive(Debug, Serialize, Deserialize)]
struct CaptureRow {
    ordinal: usize,
    stage_id: String,
    shape: Vec<usize>,
    dtype: String,
    byte_length: usize,
    sha256: String,
    path: String,
    direct_production_copy: bool,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct CaptureManifest {
    schema: String,
    schema_version: String,
    stages: Vec<CaptureRow>,
    s2_sha256: String,
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct QualificationOwner {
    schema: String,
    event_id: String,
    owner_pid: u32,
    ownership_nonce: String,
    state: String,
    same_process_runs: u32,
    fresh_process_runs: u32,
    retry: bool,
    resume: bool,
}

fn sha_bytes(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn sha_file(path: &Path) -> Result<String, String> {
    let bytes = fs::read(path).map_err(|e| format!("RUNTIME_FILE_READ:{e}"))?;
    Ok(sha_bytes(&bytes))
}

fn runtime_preflight(package: &Package) -> Result<(), String> {
    const PREFIX: &str = "/Users/mhedhli/.local/pulsarmlx/mlx-native-0.31.2-mlxc-0.6.0-a4b08e1";
    let prefix = Path::new(PREFIX);
    let libmlx = prefix.join("lib/libmlx.dylib");
    let libmlxc = prefix.join("lib/libmlxc.dylib");
    for path in [&libmlx, &libmlxc] {
        let metadata = fs::symlink_metadata(path).map_err(|e| format!("RUNTIME_STAT:{e}"))?;
        if !metadata.file_type().is_file() || metadata.file_type().is_symlink() {
            return Err("RUNTIME_LIBRARY_POLICY".into());
        }
    }
    let brand = std::process::Command::new("/usr/sbin/sysctl")
        .args(["-n", "machdep.cpu.brand_string"])
        .output()
        .map_err(|e| format!("MACHINE_BRAND:{e}"))?;
    let brand = String::from_utf8(brand.stdout).map_err(|_| "MACHINE_BRAND_UTF8")?;
    let required_dyld = prefix.join("lib").display().to_string();
    if !brand.ends_with('\n')
        || brand.trim_end_matches(['\r', '\n']) != "Apple M1 Ultra"
        || std::env::consts::ARCH != "aarch64"
        || std::env::var("PULSAR_REQUIRE_NATIVE_MLX").as_deref() != Ok("1")
        || std::env::var("MLX_PREFIX").as_deref() != Ok(PREFIX)
        || std::env::var("MLX_C_PREFIX").as_deref() != Ok(PREFIX)
        || std::env::var("DYLD_LIBRARY_PATH").as_deref() != Ok(required_dyld.as_str())
        || sha_file(&libmlx)? != package.runtime.libmlx_sha256
        || sha_file(&libmlxc)? != package.runtime.libmlxc_sha256
        || package.runtime.mlx_version != "0.31.2"
        || package.runtime.mlx_c_version != "0.6.0"
        || package.runtime.thread_limits.iter().any(|(name, expected)| {
            expected != "1" || std::env::var(name).as_deref() != Ok("1")
        })
    {
        return Err("PINNED_RUNTIME_OR_MACHINE_IDENTITY".into());
    }
    Ok(())
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

fn decode(role: &str, spec: &TensorSpec, granted: &mut GrantedInputs) -> Result<Vec<f32>, String> {
    let bytes = granted.read(role)?;
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

fn matrix(package: &Package, granted: &mut GrantedInputs, role: &str) -> Result<DenseMatrix, String> {
    let spec = tensor(package, role)?;
    if spec.shape.len() < 2 {
        return Err(format!("MATRIX_SHAPE: {role}"));
    }
    let columns = *spec.shape.last().unwrap();
    let rows = spec.shape[..spec.shape.len() - 1].iter().product();
    Ok(DenseMatrix {
        rows,
        columns,
        values: decode(role, spec, granted)?,
    })
}

fn vector(package: &Package, granted: &mut GrantedInputs, role: &str) -> Result<Vec<f32>, String> {
    let spec = tensor(package, role)?;
    if spec.shape.len() != 1 {
        return Err(format!("VECTOR_SHAPE: {role}"));
    }
    decode(role, spec, granted)
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
            dtype: "little-endian-f32".into(),
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
            dtype: "little-endian-u16".into(),
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
        || package.graph_version != stream::f017_apple_serial_f32::APPLE_SERIAL_F32_GRAPH_VERSION
        || package.checkpoint_paths.len() != 0
        || package.routed_expert_ids != [250, 10, 237, 62, 73, 177, 218, 28]
        || package.runtime.device != "APPLE_METAL_GPU"
        || package.runtime.backend != "MLX_C_MATVEC_PLUS_RUST_SERIAL_F32"
        || package.runtime.mlx_version != "0.31.2"
        || package.runtime.mlx_c_version != "0.6.0"
        || package.runtime.libmlx_sha256
            != "6622caeb3e65a8310cf2290751ffbecf32135187aa75ef05f398916ac37bd9ed"
        || package.runtime.libmlxc_sha256
            != "a060915d4b9accbf58e84d174029d5c51805891834494d50cf87a0d573222e62"
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
        || package.rope_base.to_bits() != 1_000_000.0_f32.to_bits()
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

fn execute_one(arguments: &[String], capture_root: PathBuf) -> Result<(), String> {
    let package_at = arguments
        .iter()
        .position(|v| v == "--package")
        .and_then(|i| arguments.get(i + 1))
        .ok_or("USAGE: --package PATH --grant PATH (--preflight-only|--execute)")?;
    let grant_at = arguments
        .iter()
        .position(|v| v == "--grant")
        .and_then(|i| arguments.get(i + 1))
        .ok_or("USAGE: --package PATH --grant PATH (--preflight-only|--execute)")?;
    let package = load_package(Path::new(package_at))?;
    let grant = load_grant(Path::new(grant_at))?;
    validate_package(&package)?;
    let mut granted = GrantedInputs::validate(grant, &package)?;
    if arguments.iter().any(|v| v == "--preflight-only") {
        println!("NATIVE_RETAINED_GRANT_AND_PACKAGE_SCHEMA_RESOLVED_NO_RETAINED_READ_NO_ARITHMETIC");
        return Ok(());
    }
    if !arguments.iter().any(|v| v == "--execute") {
        return Err("MODE".into());
    }
    if capture_root.parent() != Some(granted.grant().allowed_output_root.as_path()) {
        return Err("OUTPUT_NOT_GRANT_DERIVED".into());
    }
    if capture_root.exists() {
        return Err("CAPTURE_ROOT_EXISTS".into());
    }
    let mut routed = Vec::with_capacity(8);
    for (slot, &id) in package.routed_expert_ids.iter().enumerate() {
        routed.push(ExpertMatrices {
            expert_id: id,
            gate: matrix(&package, &mut granted, &format!("routed.{slot}.gate"))?,
            up: matrix(&package, &mut granted, &format!("routed.{slot}.up"))?,
            down: matrix(&package, &mut granted, &format!("routed.{slot}.down"))?,
        });
    }
    let matrices = AppleLayerMatrices {
        q_a: matrix(&package, &mut granted, "q_a")?,
        q_b: matrix(&package, &mut granted, "q_b")?,
        kv_a: matrix(&package, &mut granted, "kv_a")?,
        k_b: matrix(&package, &mut granted, "k_b")?,
        v_b: matrix(&package, &mut granted, "v_b")?,
        attention_output: matrix(&package, &mut granted, "attention_output")?,
        router: matrix(&package, &mut granted, "router")?,
        routed,
        shared: ExpertMatrices {
            expert_id: usize::MAX,
            gate: matrix(&package, &mut granted, "shared.gate")?,
            up: matrix(&package, &mut granted, "shared.up")?,
            down: matrix(&package, &mut granted, "shared.down")?,
        },
    };
    let inputs = AppleLayerInputs {
        s0: vector(&package, &mut granted, "s0")?,
        attention_norm_scale: vector(&package, &mut granted, "attention_norm_scale")?,
        q_rank_norm_scale: vector(&package, &mut granted, "q_rank_norm_scale")?,
        kv_norm_scale: vector(&package, &mut granted, "kv_norm_scale")?,
        ffn_norm_scale: vector(&package, &mut granted, "ffn_norm_scale")?,
        correction_bias: vector(&package, &mut granted, "correction_bias")?,
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
    if capture_root.exists() {
        return Err("CAPTURE_ROOT_CHANGED_DURING_PREFLIGHT".into());
    }
    if !granted.complete_census() {
        return Err("RETAINED_READ_RECEIPT_CENSUS".into());
    }
    fs::create_dir(&capture_root).map_err(|e| format!("CAPTURE_ROOT: {e}"))?;
    fsync_directory(
        capture_root.parent().ok_or("CAPTURE_ROOT_PARENT")?,
    )?;
    let receipts = serde_json::to_vec_pretty(&serde_json::json!({
        "schema":"pulsarmlx.f017.native-retained-read-receipt-census/1.0.0",
        "grant_id":granted.grant().grant_id,
        "consumer_id":granted.grant().consumer_id,
        "expected_count":40,
        "actual_count":granted.receipts().len(),
        "original_checkpoint_reads":0,
        "original_checkpoint_shard_opens":0,
        "reads":granted.receipts(),
    })).map_err(|e| format!("RECEIPT_JSON:{e}"))?;
    publish_bytes(&capture_root.join("retained-read-receipts.json"), &receipts)?;
    let mut capture = DirectoryCapture {
        root: capture_root.clone(),
        rows: Vec::new(),
    };
    #[cfg(all(target_os = "macos", pulsar_native_mlx))]
    {
        let mut backend = MlxBackend::new()?;
        let result = run_apple_serial_f32(&mut backend, &mut capture, &matrices, &inputs)
            .map_err(|e| e.to_string())?;
        let manifest_bytes = serde_json::to_vec_pretty(&serde_json::json!({"schema":"pulsarmlx.f017.apple-production-serial-f32-capture-manifest","schema_version":"1.0.0","stages":capture.rows,"s2_sha256":sha_bytes(&result.s2.iter().flat_map(|v|v.to_le_bytes()).collect::<Vec<_>>())})).unwrap();
        let path = capture_root.join("capture-manifest.json");
        publish_bytes(&path, &manifest_bytes)?;
        return Ok(());
    }
    #[cfg(not(all(target_os = "macos", pulsar_native_mlx)))]
    Err("PINNED_NATIVE_MLX_REQUIRED".into())
}

fn argument_value<'a>(arguments: &'a [String], name: &str) -> Result<&'a str, String> {
    arguments
        .iter()
        .position(|value| value == name)
        .and_then(|index| arguments.get(index + 1))
        .map(String::as_str)
        .ok_or_else(|| format!("MISSING_ARGUMENT:{name}"))
}

fn qualification_owner(
    event_id: &str,
    owner_pid: u32,
    ownership_nonce: String,
    state: &str,
) -> QualificationOwner {
    QualificationOwner {
        schema: "pulsarmlx.f017.native-retained-qualification-owner/1.0.0".into(),
        event_id: event_id.into(),
        owner_pid,
        ownership_nonce,
        state: state.into(),
        same_process_runs: 10,
        fresh_process_runs: 10,
        retry: false,
        resume: false,
    }
}

fn verify_worker_owner(arguments: &[String]) -> Result<(Package, PathBuf), String> {
    let package = load_package(Path::new(argument_value(arguments, "--package")?))?;
    let grant = load_grant(Path::new(argument_value(arguments, "--grant")?))?;
    let run: usize = argument_value(arguments, "--run")?
        .parse()
        .map_err(|_| "WORKER_RUN")?;
    if run >= 10 {
        return Err("WORKER_RUN_RANGE".into());
    }
    let owner_path = package.fixed_attempt_root.join("owner.json");
    let expected_sha = std::env::var("PULSARMLX_F017_QUALIFICATION_OWNER_SHA256")
        .map_err(|_| "WORKER_OWNER_SHA")?;
    let bytes = open_once(&owner_path, &expected_sha)?;
    let owner: QualificationOwner = f017_native::json::parse_json_no_duplicates(&bytes)?;
    let expected_pid = std::env::var("PULSARMLX_F017_QUALIFICATION_OWNER_PID")
        .map_err(|_| "WORKER_OWNER_PID")?
        .parse::<u32>()
        .map_err(|_| "WORKER_OWNER_PID")?;
    let expected_nonce = std::env::var("PULSARMLX_F017_QUALIFICATION_OWNER_NONCE")
        .map_err(|_| "WORKER_OWNER_NONCE")?;
    if owner.owner_pid != expected_pid
        || owner.ownership_nonce != expected_nonce
        || owner.state != "CONSUMING"
        || owner.retry
        || owner.resume
        || unsafe { libc::kill(expected_pid as i32, 0) } != 0
    {
        return Err("WORKER_OWNER_MISMATCH".into());
    }
    Ok((package, grant.allowed_output_root.join(format!("fresh-{run:02}"))))
}

fn capture_manifest(path: &Path) -> Result<CaptureManifest, String> {
    f017_native::json::parse_json_no_duplicates(
        &fs::read(path).map_err(|error| format!("CAPTURE_MANIFEST_READ:{error}"))?,
    )
}

fn bank_batch_result(output_root: &Path, owner: &QualificationOwner) -> Result<String, String> {
    let mut manifests = Vec::with_capacity(20);
    for family in ["same", "fresh"] {
        for run in 0..10 {
            let root = output_root.join(format!("{family}-{run:02}"));
            let manifest = capture_manifest(&root.join("capture-manifest.json"))?;
            if manifest.schema != "pulsarmlx.f017.apple-production-serial-f32-capture-manifest"
                || manifest.schema_version != "1.0.0"
                || manifest.stages.len() != 34
            {
                return Err("CAPTURE_MANIFEST_CENSUS".into());
            }
            let reads: serde_json::Value = f017_native::json::parse_json_no_duplicates(
                &fs::read(root.join("retained-read-receipts.json"))
                    .map_err(|error| format!("READ_RECEIPTS:{error}"))?,
            )?;
            if reads.get("actual_count").and_then(|value| value.as_u64()) != Some(40) {
                return Err("PER_RUN_READ_RECEIPT_CENSUS".into());
            }
            manifests.push((family, run, manifest));
        }
    }
    let baseline = &manifests[0].2;
    for (_, _, manifest) in manifests.iter().skip(1) {
        if manifest.s2_sha256 != baseline.s2_sha256 {
            return Err("D3_5_S2_REPEAT_DIVERGENCE".into());
        }
        for (expected, actual) in baseline.stages.iter().zip(&manifest.stages) {
            if expected.ordinal != actual.ordinal
                || expected.stage_id != actual.stage_id
                || expected.shape != actual.shape
                || expected.dtype != actual.dtype
                || expected.byte_length != actual.byte_length
                || expected.sha256 != actual.sha256
            {
                return Err(format!("D3_5_EARLIEST_DIVERGENCE:{}", expected.stage_id));
            }
        }
    }
    let result = serde_json::json!({
        "schema":"pulsarmlx.f017.native-retained-qualification-repeat-result/1.0.0",
        "event_id":owner.event_id,
        "owner_pid":owner.owner_pid,
        "ownership_nonce":owner.ownership_nonce,
        "same_process_runs":10,
        "fresh_process_runs":10,
        "total_runs":20,
        "stages_per_run":34,
        "retained_reads_per_run":40,
        "retained_read_receipts":800,
        "all_stage_bytes_exact":true,
        "earliest_divergence":null,
        "s2_sha256":baseline.s2_sha256,
        "original_checkpoint_reads":0,
        "original_checkpoint_shard_opens":0,
        "historical_payload_ledger_delta":0,
    });
    let bytes = serde_json::to_vec_pretty(&result).map_err(|e| format!("BATCH_JSON:{e}"))?;
    publish_bytes(&output_root.join("repeat-result.json"), &bytes)
}

fn terminalize_batch(
    attempt_root: &Path,
    output_root: &Path,
    owner: &QualificationOwner,
    state: &str,
    repeat_result_sha256: Option<&str>,
) -> Result<(), String> {
    let owner_bytes = open_once(&attempt_root.join("owner.json"), &sha_bytes(
        &fs::read(attempt_root.join("owner.json")).map_err(|e| format!("OWNER_READ:{e}"))?,
    ))?;
    let observed: QualificationOwner = f017_native::json::parse_json_no_duplicates(&owner_bytes)?;
    if observed.owner_pid != owner.owner_pid
        || observed.ownership_nonce != owner.ownership_nonce
        || observed.event_id != owner.event_id
    {
        return Err("TERMINAL_NOT_OWNER".into());
    }
    let mut receipt_count = 0_u32;
    if output_root.is_dir() {
        for entry in fs::read_dir(output_root).map_err(|e| format!("OUTPUT_CENSUS:{e}"))? {
            let entry = entry.map_err(|e| format!("OUTPUT_CENSUS_ENTRY:{e}"))?;
            let receipt_path = entry.path().join("retained-read-receipts.json");
            if receipt_path.is_file() {
                let receipt: serde_json::Value = f017_native::json::parse_json_no_duplicates(
                    &fs::read(&receipt_path).map_err(|e| format!("TERMINAL_RECEIPT_READ:{e}"))?,
                )?;
                receipt_count = receipt_count
                    .checked_add(receipt.get("actual_count").and_then(|v| v.as_u64()).ok_or("TERMINAL_RECEIPT_COUNT")? as u32)
                    .ok_or("TERMINAL_RECEIPT_OVERFLOW")?;
            }
        }
    }
    if repeat_result_sha256.is_some() && receipt_count != 800 {
        return Err("SUCCESS_TERMINAL_RECEIPT_CENSUS".into());
    }
    let terminal = serde_json::json!({
        "schema":"pulsarmlx.f017.native-retained-qualification-terminal/1.0.0",
        "event_id":owner.event_id,
        "owner_pid":owner.owner_pid,
        "ownership_nonce":owner.ownership_nonce,
        "state":state,
        "repeat_result_sha256":repeat_result_sha256,
        "authoritative_retained_read_receipt_count":receipt_count,
        "expected_success_receipt_count":800,
        "retry_permitted":false,
        "resume_permitted":false,
    });
    let bytes = serde_json::to_vec_pretty(&terminal).map_err(|e| format!("TERMINAL_JSON:{e}"))?;
    publish_bytes(&attempt_root.join("terminal.json"), &bytes)?;
    Ok(())
}

fn execute_batch(arguments: &[String]) -> Result<(), String> {
    let package = load_package(Path::new(argument_value(arguments, "--package")?))?;
    let grant = load_grant(Path::new(argument_value(arguments, "--grant")?))?;
    runtime_preflight(&package)?;
    if package.fixed_attempt_root.exists() || grant.allowed_output_root.exists() {
        return Err("QUALIFICATION_EVENT_ALREADY_CONSUMED_OR_PARTIAL".into());
    }
    fs::create_dir(&package.fixed_attempt_root).map_err(|e| format!("ATTEMPT_ROOT:{e}"))?;
    fs::set_permissions(&package.fixed_attempt_root, fs::Permissions::from_mode(0o700))
        .map_err(|e| format!("ATTEMPT_MODE:{e}"))?;
    fsync_directory(package.fixed_attempt_root.parent().ok_or("ATTEMPT_PARENT")?)?;
    let owner_pid = std::process::id();
    let nonce = format!("{}-{owner_pid}-{}", grant.grant_id, std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map_err(|_| "CLOCK")?.as_nanos());
    let owner = qualification_owner(&grant.grant_id, owner_pid, nonce.clone(), "CONSUMING");
    let owner_bytes = serde_json::to_vec_pretty(&owner).map_err(|e| format!("OWNER_JSON:{e}"))?;
    let owner_sha = publish_bytes(&package.fixed_attempt_root.join("owner.json"), &owner_bytes)?;
    publish_bytes(&package.fixed_attempt_root.join("durable-attempt-start.json"), &owner_bytes)?;
    fs::create_dir(&grant.allowed_output_root).map_err(|e| format!("OUTPUT_ROOT:{e}"))?;
    fsync_directory(grant.allowed_output_root.parent().ok_or("OUTPUT_PARENT")?)?;

    let mut worker_arguments = arguments.to_vec();
    worker_arguments.push("--execute".into());
    let outcome = (|| {
        for run in 0..10 {
            execute_one(&worker_arguments, grant.allowed_output_root.join(format!("same-{run:02}")))?;
        }
        let executable = std::env::current_exe().map_err(|e| format!("CURRENT_EXE:{e}"))?;
        for run in 0..10 {
            let status = std::process::Command::new(&executable)
                .arg("--package").arg(argument_value(arguments, "--package")?)
                .arg("--grant").arg(argument_value(arguments, "--grant")?)
                .arg("--fresh-worker").arg("--run").arg(run.to_string())
                .env("PULSARMLX_F017_QUALIFICATION_OWNER_SHA256", &owner_sha)
                .env("PULSARMLX_F017_QUALIFICATION_OWNER_PID", owner_pid.to_string())
                .env("PULSARMLX_F017_QUALIFICATION_OWNER_NONCE", &nonce)
                .status().map_err(|e| format!("FRESH_PROCESS:{e}"))?;
            if !status.success() { return Err(format!("FRESH_PROCESS_EXIT:{run}:{status}")); }
        }
        bank_batch_result(&grant.allowed_output_root, &owner)
    })();
    match outcome {
        Ok(result_sha) => terminalize_batch(&package.fixed_attempt_root, &grant.allowed_output_root, &owner, "COMPLETE", Some(&result_sha)),
        Err(error) => {
            let terminal = terminalize_batch(&package.fixed_attempt_root, &grant.allowed_output_root, &owner, "TERMINAL_FAILURE", None);
            terminal.and(Err(error))
        }
    }
}

fn main() -> Result<(), String> {
    let arguments = std::env::args().collect::<Vec<_>>();
    if arguments.iter().any(|value| value == "--preflight-only") {
        return execute_one(&arguments, PathBuf::from("/preflight-not-used"));
    }
    if arguments.iter().any(|value| value == "--fresh-worker") {
        let (_, output) = verify_worker_owner(&arguments)?;
        let mut worker_arguments = arguments.clone();
        worker_arguments.push("--execute".into());
        return execute_one(&worker_arguments, output);
    }
    if arguments.iter().any(|value| value == "--execute-batch") {
        return execute_batch(&arguments);
    }
    Err("MODE_REQUIRES_PREFLIGHT_OR_WRAPPER_OWNED_BATCH".into())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_root(label: &str) -> PathBuf {
        std::env::temp_dir().join(format!(
            "pulsarmlx-f017-{label}-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ))
    }

    fn seed_run(root: &Path, family: &str, run: usize) {
        let run_root = root.join(format!("{family}-{run:02}"));
        fs::create_dir(&run_root).unwrap();
        let stages = (0..34).map(|ordinal| CaptureRow {
            ordinal,
            stage_id: format!("stage-{ordinal:02}"),
            shape: vec![1],
            dtype: "little-endian-f32".into(),
            byte_length: 4,
            sha256: format!("{ordinal:064x}"),
            path: format!("{ordinal:02}.f32le"),
            direct_production_copy: true,
        }).collect::<Vec<_>>();
        fs::write(run_root.join("capture-manifest.json"), serde_json::to_vec(&serde_json::json!({
            "schema":"pulsarmlx.f017.apple-production-serial-f32-capture-manifest",
            "schema_version":"1.0.0","stages":stages,"s2_sha256":"f".repeat(64)
        })).unwrap()).unwrap();
        fs::write(run_root.join("retained-read-receipts.json"), br#"{"actual_count":40}"#).unwrap();
    }

    #[test]
    fn repeat_batch_requires_10_same_and_10_fresh_with_exact_stage_bytes() {
        let root = test_root("repeat-batch");
        fs::create_dir(&root).unwrap();
        for family in ["same", "fresh"] {
            for run in 0..10 { seed_run(&root, family, run); }
        }
        let owner = qualification_owner("event", 1, "nonce".into(), "CONSUMING");
        assert!(bank_batch_result(&root, &owner).is_ok());
        fs::set_permissions(root.join("repeat-result.json"), fs::Permissions::from_mode(0o600)).unwrap();
        fs::remove_file(root.join("repeat-result.json")).unwrap();
        let changed = root.join("fresh-09/capture-manifest.json");
        let mut manifest: serde_json::Value = serde_json::from_slice(&fs::read(&changed).unwrap()).unwrap();
        manifest["stages"][7]["sha256"] = serde_json::Value::String("e".repeat(64));
        fs::write(&changed, serde_json::to_vec(&manifest).unwrap()).unwrap();
        assert_eq!(bank_batch_result(&root, &owner).unwrap_err(), "D3_5_EARLIEST_DIVERGENCE:stage-07");
        fs::remove_dir_all(&root).unwrap();
    }
}
