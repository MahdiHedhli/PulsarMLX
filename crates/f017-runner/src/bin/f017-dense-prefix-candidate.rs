//! Narrow native candidate for the F017 layer-3-entry dense-prefix boundary.
//!
//! The command surface intentionally has no full-model, layer-3, router,
//! expert, logits, sampling, or generation mode.

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

const ATTEMPT: &str = "DPREFIX-REAL-1";
const PROMPT_PACKAGE: &str = "c05ba1cba69535cd17daf9f4326e5e1db25ffafe504c53712aa548f251741dff";
const INVENTORY: &str = "c9c1540ea1cc9e69344ed9f3dcc4eb8ba1e5c15e3d55c1bccdec00eeb1db36aa";

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct IdentityBinding {
    attempt_id: String,
    binary_sha256: String,
    source_manifest_sha256: String,
    execution_config_sha256: String,
    authorization_binding_sha256: String,
    inventory_sha256: String,
    prompt_package_sha256: String,
    ledger_before: u64,
}

#[derive(Debug, Serialize)]
struct SelfVerification {
    result: &'static str,
    attempt_id: &'static str,
    binary_sha256: String,
    source_manifest_sha256: String,
    execution_config_sha256: String,
    authorization_binding_sha256: String,
    inventory_sha256: &'static str,
    prompt_package_sha256: &'static str,
    ledger_before: u64,
    checkpoint_reads: u64,
}

#[derive(Clone)]
struct Dimensions {
    hidden: usize,
    q_lora: usize,
    heads: usize,
    qk_nope: usize,
    qk_rope: usize,
    kv_lora: usize,
    value: usize,
    ffn: usize,
}

#[derive(Default, Serialize)]
struct DispatchEvidence {
    native_matvecs: u64,
    cpu_rms_norm: u64,
    cpu_attention: u64,
    cpu_activation: u64,
    synchronizations: u64,
    readbacks: u64,
    fallback: u64,
    backend_errors: u64,
}

#[derive(Serialize)]
struct SyntheticEvidence {
    schema: &'static str,
    result: &'static str,
    actual_binary_path: bool,
    real_checkpoint_access: u64,
    ledger: u64,
    repeats: usize,
    deterministic: bool,
    hidden_width: usize,
    stage_hashes: Vec<BTreeMap<String, String>>,
    dispatch: DispatchEvidence,
    quantization_family_decoded_sha256: BTreeMap<String, String>,
    lifecycle_reconciled: bool,
    retained_state: RetainedState,
}

fn exercise_decoder_families() -> Result<BTreeMap<String, String>, String> {
    let source = (0..256)
        .map(|index| ((index * 29 % 251) as f32 - 125.0) / 64.0)
        .collect::<Vec<_>>();
    let mut result = BTreeMap::from([("F32".to_owned(), hash_f32(&source))]);
    let mut q8 = Vec::new();
    quant::quantize_row_q8_0(&source, &mut q8);
    let mut q8_values = vec![0.0_f32; 256];
    quant::decode_q8_0_matrix(&q8, 1, 256, &mut q8_values)
        .map_err(|error| format!("synthetic Q8_0: {error}"))?;
    result.insert("Q8_0".to_owned(), hash_f32(&q8_values));
    let mut q4 = Vec::new();
    quant::quantize_row_q4_k(&source, &mut q4);
    let q4_values = quant::cpu_dot::dequant_q4_k(&q4, 256);
    result.insert("Q4_K".to_owned(), hash_f32(&q4_values));
    let mut q5 = Vec::new();
    quant::quantize_row_q5_k(&source, &mut q5);
    let q5_values = quant::cpu_dot::dequant_q5_k(&q5, 256);
    result.insert("Q5_K".to_owned(), hash_f32(&q5_values));
    let mut q6 = Vec::new();
    quant::quantize_row_q6_k(&source, &mut q6);
    let mut q6_values = vec![0.0_f32; 256];
    quant::decode_q6_k_matrix(&q6, 1, 256, &mut q6_values)
        .map_err(|error| format!("synthetic Q6_K: {error}"))?;
    result.insert("Q6_K".to_owned(), hash_f32(&q6_values));
    if result.len() != 5
        || [&q4_values, &q5_values, &q6_values, &q8_values]
            .iter()
            .any(|values| values.len() != 256 || values.iter().any(|value| !value.is_finite()))
    {
        return Err("synthetic decoder-family coverage".to_owned());
    }
    Ok(result)
}

#[derive(Serialize)]
struct RetainedState {
    dtype: &'static str,
    shape: [usize; 1],
    count: usize,
    sha256: String,
    canonical_bytes: usize,
    immutable: bool,
    read_only: bool,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct MaterialPackage {
    schema: String,
    attempt_id: String,
    identity_binding: String,
    prompt_package_sha256: String,
    inventory_sha256: String,
    tensor_count: usize,
    tensors: Vec<MaterialTensor>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct MaterialTensor {
    ordinal: usize,
    name: String,
    quantization: String,
    gguf_shape: Vec<usize>,
    packed_path: String,
    packed_sha256: String,
}

struct DecodedTensor {
    dimensions: Vec<usize>,
    values: Vec<f32>,
}

impl DecodedTensor {
    fn columns(&self) -> usize {
        self.dimensions[0]
    }

    fn rows(&self) -> usize {
        self.dimensions[1..].iter().product()
    }
}

#[derive(Serialize)]
struct RealCandidateEvidence {
    schema: &'static str,
    attempt_id: &'static str,
    result: &'static str,
    real_checkpoint_reads_by_candidate: u64,
    material_tensor_count: usize,
    input_packed_hashes: BTreeMap<String, String>,
    input_decoded_hashes: BTreeMap<String, String>,
    identity_confirmations: BTreeMap<String, bool>,
    repeats: usize,
    deterministic: bool,
    stage_hashes: Vec<BTreeMap<String, String>>,
    dispatch: DispatchEvidence,
    retained_state: RetainedState,
}

fn sha_bytes(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn sha_file(path: &Path) -> Result<String, String> {
    fs::read(path)
        .map(|bytes| sha_bytes(&bytes))
        .map_err(|error| error.to_string())
}

fn canonical_f32(values: &[f32]) -> Vec<u8> {
    values
        .iter()
        .flat_map(|value| value.to_le_bytes())
        .collect()
}

fn hash_f32(values: &[f32]) -> String {
    sha_bytes(&canonical_f32(values))
}

fn self_verify(binding_path: &Path) -> Result<SelfVerification, String> {
    let binding: IdentityBinding = serde_json::from_slice(
        &fs::read(binding_path).map_err(|error| format!("candidate identity read: {error}"))?,
    )
    .map_err(|error| format!("candidate identity parse: {error}"))?;
    if binding.attempt_id != ATTEMPT
        || binding.inventory_sha256 != INVENTORY
        || binding.prompt_package_sha256 != PROMPT_PACKAGE
        || binding.ledger_before != 59
    {
        return Err("CANDIDATE_IDENTITY: frozen identity mismatch".to_owned());
    }
    let executable = std::env::current_exe().map_err(|error| error.to_string())?;
    let actual = sha_file(&executable)?;
    if actual != binding.binary_sha256 {
        return Err("CANDIDATE_IDENTITY: binary SHA-256 mismatch".to_owned());
    }
    for value in [
        &binding.source_manifest_sha256,
        &binding.execution_config_sha256,
        &binding.authorization_binding_sha256,
    ] {
        if value.len() != 64 || !value.bytes().all(|byte| byte.is_ascii_hexdigit()) {
            return Err("CANDIDATE_IDENTITY: malformed bound SHA-256".to_owned());
        }
    }
    Ok(SelfVerification {
        result: "CANDIDATE_IDENTITY_VERIFIED",
        attempt_id: ATTEMPT,
        binary_sha256: actual,
        source_manifest_sha256: binding.source_manifest_sha256,
        execution_config_sha256: binding.execution_config_sha256,
        authorization_binding_sha256: binding.authorization_binding_sha256,
        inventory_sha256: INVENTORY,
        prompt_package_sha256: PROMPT_PACKAGE,
        ledger_before: 59,
        checkpoint_reads: 0,
    })
}

fn rms_norm(values: &[f32], scale: &[f32], epsilon: f32) -> Result<Vec<f32>, String> {
    if values.is_empty() || values.len() != scale.len() {
        return Err("candidate RMSNorm shape".to_owned());
    }
    let total = values
        .iter()
        .fold(0.0_f32, |acc, value| acc + value * value);
    let inverse = 1.0_f32 / (total / values.len() as f32 + epsilon).sqrt();
    Ok(values
        .iter()
        .zip(scale)
        .map(|(value, weight)| value * inverse * weight)
        .collect())
}

fn swiglu(gate: &[f32], up: &[f32]) -> Result<Vec<f32>, String> {
    if gate.len() != up.len() {
        return Err("candidate SwiGLU shape".to_owned());
    }
    Ok(gate
        .iter()
        .zip(up)
        .map(|(&gate, &up)| (gate / (1.0 + (-gate).exp())) * up)
        .collect())
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
fn native_matvec(
    matrix: &mut [f32],
    rows: usize,
    columns: usize,
    vector: &[f32],
    dispatch: &mut DispatchEvidence,
) -> Result<Vec<f32>, String> {
    use stream::{MlxContext, MlxDevice, MlxStreamMode};
    if matrix.len() != rows * columns || vector.len() != columns {
        return Err("native candidate matvec shape".to_owned());
    }
    let mut vector_owner = vector.to_vec();
    let context = MlxContext::new(MlxDevice::Gpu, MlxStreamMode::BorrowedDefault)?;
    let matrix_array = context.import_f32_shaped(matrix, &[rows, columns])?;
    let vector_array = context.import_f32_shaped(&mut vector_owner, &[columns])?;
    let output = matrix_array.matvec(&vector_array)?;
    output.evaluate_sync()?;
    let mut result = vec![0.0_f32; rows];
    output.copy_f32(&mut result)?;
    dispatch.native_matvecs += 1;
    dispatch.synchronizations += 1;
    dispatch.readbacks += 1;
    let callbacks = output.destroy()? + vector_array.destroy()? + matrix_array.destroy()?;
    let snapshot = context.ownership_snapshot()?;
    if callbacks != 2
        || snapshot.managed_created != snapshot.managed_destroyed
        || snapshot.derived_created != snapshot.derived_destroyed
        || snapshot.derived_live != 0
    {
        return Err("candidate MLX lifecycle mismatch".to_owned());
    }
    Ok(result)
}

#[cfg(not(all(target_os = "macos", pulsar_native_mlx)))]
fn native_matvec(
    _matrix: &mut [f32],
    _rows: usize,
    _columns: usize,
    _vector: &[f32],
    _dispatch: &mut DispatchEvidence,
) -> Result<Vec<f32>, String> {
    Err("NATIVE_RUNTIME: binary lacks pinned native MLX".to_owned())
}

fn deterministic_matrix(rows: usize, columns: usize, salt: usize) -> Vec<f32> {
    (0..rows * columns)
        .map(|index| (((index * 17 + salt * 31) % 257) as f32 - 128.0) / 4096.0)
        .collect()
}

fn run_layer(
    residual: &[f32],
    dimensions: &Dimensions,
    layer: usize,
    dispatch: &mut DispatchEvidence,
) -> Result<(Vec<f32>, BTreeMap<String, String>), String> {
    let d = dimensions;
    let ones = vec![1.0_f32; d.hidden];
    let x_norm = rms_norm(residual, &ones, 1e-5)?;
    dispatch.cpu_rms_norm += 1;
    let mut q_a = deterministic_matrix(d.q_lora, d.hidden, 100 + layer);
    let q_rank = native_matvec(&mut q_a, d.q_lora, d.hidden, &x_norm, dispatch)?;
    let q_rank_norm = rms_norm(&q_rank, &vec![1.0; d.q_lora], 1e-5)?;
    dispatch.cpu_rms_norm += 1;
    let q_width = d.heads * (d.qk_nope + d.qk_rope);
    let mut q_b = deterministic_matrix(q_width, d.q_lora, 200 + layer);
    let q = native_matvec(&mut q_b, q_width, d.q_lora, &q_rank_norm, dispatch)?;
    let mut kv_a = deterministic_matrix(d.kv_lora + d.qk_rope, d.hidden, 300 + layer);
    let kv = native_matvec(
        &mut kv_a,
        d.kv_lora + d.qk_rope,
        d.hidden,
        &x_norm,
        dispatch,
    )?;
    let kv_norm = rms_norm(&kv[..d.kv_lora], &vec![1.0; d.kv_lora], 1e-5)?;
    dispatch.cpu_rms_norm += 1;
    let mut values = Vec::with_capacity(d.heads * d.value);
    let mut key_hash_material = Vec::new();
    for head in 0..d.heads {
        let mut key = deterministic_matrix(d.qk_nope, d.kv_lora, 400 + layer * 97 + head);
        key_hash_material.extend(native_matvec(
            &mut key, d.qk_nope, d.kv_lora, &kv_norm, dispatch,
        )?);
        let mut value = deterministic_matrix(d.value, d.kv_lora, 500 + layer * 97 + head);
        values.extend(native_matvec(
            &mut value, d.value, d.kv_lora, &kv_norm, dispatch,
        )?);
    }
    // Position zero has one visible key; softmax([score]) is exactly [1].
    dispatch.cpu_attention += 1;
    let mut output_projection = deterministic_matrix(d.hidden, d.heads * d.value, 600 + layer);
    let attention = native_matvec(
        &mut output_projection,
        d.hidden,
        d.heads * d.value,
        &values,
        dispatch,
    )?;
    let attention_residual = residual
        .iter()
        .zip(&attention)
        .map(|(a, b)| a + b)
        .collect::<Vec<_>>();
    let ffn_input = rms_norm(&attention_residual, &ones, 1e-5)?;
    dispatch.cpu_rms_norm += 1;
    let mut gate_matrix = deterministic_matrix(d.ffn, d.hidden, 700 + layer);
    let gate = native_matvec(&mut gate_matrix, d.ffn, d.hidden, &ffn_input, dispatch)?;
    let mut up_matrix = deterministic_matrix(d.ffn, d.hidden, 800 + layer);
    let up = native_matvec(&mut up_matrix, d.ffn, d.hidden, &ffn_input, dispatch)?;
    let activated = swiglu(&gate, &up)?;
    dispatch.cpu_activation += 1;
    let mut down_matrix = deterministic_matrix(d.hidden, d.ffn, 900 + layer);
    let down = native_matvec(&mut down_matrix, d.hidden, d.ffn, &activated, dispatch)?;
    let output = attention_residual
        .iter()
        .zip(&down)
        .map(|(a, b)| a + b)
        .collect::<Vec<_>>();
    let stages = BTreeMap::from([
        (format!("layer_{layer}_q"), hash_f32(&q)),
        (format!("layer_{layer}_keys"), hash_f32(&key_hash_material)),
        (format!("layer_{layer}_attention"), hash_f32(&attention)),
        (
            format!("layer_{layer}_attention_residual"),
            hash_f32(&attention_residual),
        ),
        (format!("layer_{layer}_ffn"), hash_f32(&down)),
        (format!("layer_{layer}_output"), hash_f32(&output)),
    ]);
    Ok((output, stages))
}

fn synthetic_rehearsal(output: &Path) -> Result<(), String> {
    let dimensions = Dimensions {
        hidden: 64,
        q_lora: 32,
        heads: 4,
        qk_nope: 8,
        qk_rope: 8,
        kv_lora: 16,
        value: 16,
        ffn: 96,
    };
    let embedding = (0..dimensions.hidden)
        .map(|index| (index as f32 - 31.5) / 128.0)
        .collect::<Vec<_>>();
    let mut repeat_hashes = Vec::new();
    let mut dispatch = DispatchEvidence::default();
    let mut final_state = Vec::new();
    for _ in 0..10 {
        let mut stages = BTreeMap::from([("embedding".to_owned(), hash_f32(&embedding))]);
        let mut hidden = embedding.clone();
        for layer in 0..3 {
            let (next, layer_stages) = run_layer(&hidden, &dimensions, layer, &mut dispatch)?;
            stages.extend(layer_stages);
            hidden = next;
        }
        stages.insert("layer_3_entry".to_owned(), hash_f32(&hidden));
        final_state = hidden;
        repeat_hashes.push(stages);
    }
    let deterministic = repeat_hashes.windows(2).all(|pair| pair[0] == pair[1]);
    if !deterministic {
        return Err("REPEAT_DETERMINISM".to_owned());
    }
    // The native rehearsal keeps projection matrices bounded while exercising
    // the production-width retention path required downstream.  Values are a
    // deterministic expansion of the actual synthetic layer-3 result; real
    // evidence never uses this rehearsal artifact as numerical truth.
    let retained_values = (0..6144)
        .map(|index| final_state[index % final_state.len()])
        .collect::<Vec<_>>();
    let retained_bytes = canonical_f32(&retained_values);
    let retained_path = output.with_extension("layer3-entry.f32le");
    fs::write(&retained_path, &retained_bytes).map_err(|error| error.to_string())?;
    let mut permissions = fs::metadata(&retained_path)
        .map_err(|error| error.to_string())?
        .permissions();
    permissions.set_readonly(true);
    fs::set_permissions(&retained_path, permissions).map_err(|error| error.to_string())?;
    let evidence = SyntheticEvidence {
        schema: "pulsarmlx.f017.dprefix-candidate-synthetic-rehearsal",
        result: "SYNTHETIC_ACTUAL_BINARY_10_REPEAT_PASS",
        actual_binary_path: true,
        real_checkpoint_access: 0,
        ledger: 59,
        repeats: 10,
        deterministic,
        hidden_width: dimensions.hidden,
        stage_hashes: repeat_hashes,
        dispatch,
        quantization_family_decoded_sha256: exercise_decoder_families()?,
        lifecycle_reconciled: true,
        retained_state: RetainedState {
            dtype: "little_endian_f32",
            shape: [6144],
            count: 6144,
            sha256: sha_bytes(&retained_bytes),
            canonical_bytes: retained_bytes.len(),
            immutable: true,
            read_only: true,
        },
    };
    fs::write(
        output,
        serde_json::to_vec_pretty(&evidence).map_err(|error| error.to_string())?,
    )
    .map_err(|error| error.to_string())
}

fn decode_material(tensor: &MaterialTensor, package_root: &Path) -> Result<DecodedTensor, String> {
    if tensor.gguf_shape.is_empty() || tensor.gguf_shape.iter().any(|&value| value == 0) {
        return Err(format!(
            "DECODER_IDENTITY: invalid shape for {}",
            tensor.name
        ));
    }
    let relative = Path::new(&tensor.packed_path);
    if relative.is_absolute()
        || relative
            .components()
            .any(|component| matches!(component, std::path::Component::ParentDir))
    {
        return Err(format!("PACKED_PAYLOAD: unsafe path for {}", tensor.name));
    }
    let packed = fs::read(package_root.join(relative))
        .map_err(|error| format!("PACKED_PAYLOAD {}: {error}", tensor.name))?;
    if sha_bytes(&packed) != tensor.packed_sha256 {
        return Err(format!("PACKED_PAYLOAD: hash mismatch for {}", tensor.name));
    }
    let count = tensor
        .gguf_shape
        .iter()
        .try_fold(1_usize, |acc, &value| acc.checked_mul(value))
        .ok_or_else(|| format!("DECODER_IDENTITY: shape overflow for {}", tensor.name))?;
    let columns = tensor.gguf_shape[0];
    let rows = count / columns;
    let values = match tensor.quantization.as_str() {
        "F32" => {
            if packed.len() != count * 4 {
                return Err(format!("DECODER_IDENTITY: F32 length for {}", tensor.name));
            }
            packed
                .chunks_exact(4)
                .map(|bytes| f32::from_le_bytes(bytes.try_into().unwrap()))
                .collect()
        }
        "Q8_0" => {
            let mut values = vec![0.0_f32; count];
            quant::decode_q8_0_matrix(&packed, rows, columns, &mut values)
                .map_err(|error| format!("DECODER_IDENTITY {}: {error}", tensor.name))?;
            values
        }
        "Q4_K" => {
            let values = quant::cpu_dot::dequant_q4_k(&packed, count);
            if values.len() != count {
                return Err(format!("DECODER_IDENTITY: Q4_K length for {}", tensor.name));
            }
            values
        }
        "Q5_K" => {
            let values = quant::cpu_dot::dequant_q5_k(&packed, count);
            if values.len() != count {
                return Err(format!("DECODER_IDENTITY: Q5_K length for {}", tensor.name));
            }
            values
        }
        "Q6_K" => {
            let mut values = vec![0.0_f32; count];
            quant::decode_q6_k_matrix(&packed, rows, columns, &mut values)
                .map_err(|error| format!("DECODER_IDENTITY {}: {error}", tensor.name))?;
            values
        }
        other => return Err(format!("DECODER_IDENTITY: unsupported {other}")),
    };
    if values.iter().any(|value| !value.is_finite()) {
        return Err(format!("DECODER_IDENTITY: non-finite {}", tensor.name));
    }
    Ok(DecodedTensor {
        dimensions: tensor.gguf_shape.clone(),
        values,
    })
}

fn take_matvec(
    tensors: &mut BTreeMap<String, DecodedTensor>,
    name: &str,
    vector: &[f32],
    dispatch: &mut DispatchEvidence,
) -> Result<Vec<f32>, String> {
    let tensor = tensors
        .get_mut(name)
        .ok_or_else(|| format!("candidate tensor absent: {name}"))?;
    let rows = tensor.rows();
    let columns = tensor.columns();
    native_matvec(&mut tensor.values, rows, columns, vector, dispatch)
}

fn take_head_matvec(
    tensors: &mut BTreeMap<String, DecodedTensor>,
    name: &str,
    head: usize,
    vector: &[f32],
    dispatch: &mut DispatchEvidence,
) -> Result<Vec<f32>, String> {
    let tensor = tensors
        .get_mut(name)
        .ok_or_else(|| format!("candidate tensor absent: {name}"))?;
    if tensor.dimensions.len() != 3 || head >= tensor.dimensions[2] {
        return Err(format!("candidate head tensor shape: {name}"));
    }
    let columns = tensor.dimensions[0];
    let rows = tensor.dimensions[1];
    let head_elements = columns * rows;
    native_matvec(
        &mut tensor.values[head * head_elements..(head + 1) * head_elements],
        rows,
        columns,
        vector,
        dispatch,
    )
}

fn vector(
    tensors: &BTreeMap<String, DecodedTensor>,
    name: &str,
    expected: usize,
) -> Result<Vec<f32>, String> {
    let values = &tensors
        .get(name)
        .ok_or_else(|| format!("candidate vector absent: {name}"))?
        .values;
    if values.len() != expected {
        return Err(format!("candidate vector shape: {name}"));
    }
    Ok(values.clone())
}

fn run_real_layer(
    tensors: &mut BTreeMap<String, DecodedTensor>,
    residual: &[f32],
    layer: usize,
    dispatch: &mut DispatchEvidence,
) -> Result<(Vec<f32>, BTreeMap<String, String>), String> {
    const HIDDEN: usize = 6144;
    const Q_LORA: usize = 2048;
    const HEADS: usize = 64;
    const QK_NOPE: usize = 192;
    const QK_ROPE: usize = 64;
    const KV_LORA: usize = 512;
    const VALUE: usize = 256;
    const FFN: usize = 12288;
    let prefix = format!("blk.{layer}");
    let x_norm = rms_norm(
        residual,
        &vector(tensors, &format!("{prefix}.attn_norm.weight"), HIDDEN)?,
        1e-5,
    )?;
    dispatch.cpu_rms_norm += 1;
    let q_rank = take_matvec(
        tensors,
        &format!("{prefix}.attn_q_a.weight"),
        &x_norm,
        dispatch,
    )?;
    if q_rank.len() != Q_LORA {
        return Err("candidate q_lora width".to_owned());
    }
    let q_rank_norm = rms_norm(
        &q_rank,
        &vector(tensors, &format!("{prefix}.attn_q_a_norm.weight"), Q_LORA)?,
        1e-5,
    )?;
    dispatch.cpu_rms_norm += 1;
    let q = take_matvec(
        tensors,
        &format!("{prefix}.attn_q_b.weight"),
        &q_rank_norm,
        dispatch,
    )?;
    if q.len() != HEADS * (QK_NOPE + QK_ROPE) {
        return Err("candidate query width".to_owned());
    }
    // Position zero RoPE is the identity.  The q/k surfaces remain executed
    // and retained even though one-visible-token softmax is exactly one.
    let kv = take_matvec(
        tensors,
        &format!("{prefix}.attn_kv_a_mqa.weight"),
        &x_norm,
        dispatch,
    )?;
    if kv.len() != KV_LORA + QK_ROPE {
        return Err("candidate kv width".to_owned());
    }
    let kv_norm = rms_norm(
        &kv[..KV_LORA],
        &vector(tensors, &format!("{prefix}.attn_kv_a_norm.weight"), KV_LORA)?,
        1e-5,
    )?;
    dispatch.cpu_rms_norm += 1;
    let mut keys = Vec::with_capacity(HEADS * QK_NOPE);
    let mut values = Vec::with_capacity(HEADS * VALUE);
    for head in 0..HEADS {
        keys.extend(take_head_matvec(
            tensors,
            &format!("{prefix}.attn_k_b.weight"),
            head,
            &kv_norm,
            dispatch,
        )?);
        values.extend(take_head_matvec(
            tensors,
            &format!("{prefix}.attn_v_b.weight"),
            head,
            &kv_norm,
            dispatch,
        )?);
    }
    dispatch.cpu_attention += 1;
    let attention = take_matvec(
        tensors,
        &format!("{prefix}.attn_output.weight"),
        &values,
        dispatch,
    )?;
    let attention_residual = residual
        .iter()
        .zip(&attention)
        .map(|(a, b)| a + b)
        .collect::<Vec<_>>();
    let ffn_input = rms_norm(
        &attention_residual,
        &vector(tensors, &format!("{prefix}.ffn_norm.weight"), HIDDEN)?,
        1e-5,
    )?;
    dispatch.cpu_rms_norm += 1;
    let gate = take_matvec(
        tensors,
        &format!("{prefix}.ffn_gate.weight"),
        &ffn_input,
        dispatch,
    )?;
    let up = take_matvec(
        tensors,
        &format!("{prefix}.ffn_up.weight"),
        &ffn_input,
        dispatch,
    )?;
    if gate.len() != FFN || up.len() != FFN {
        return Err("candidate FFN width".to_owned());
    }
    let activated = swiglu(&gate, &up)?;
    dispatch.cpu_activation += 1;
    let down = take_matvec(
        tensors,
        &format!("{prefix}.ffn_down.weight"),
        &activated,
        dispatch,
    )?;
    let output = attention_residual
        .iter()
        .zip(&down)
        .map(|(a, b)| a + b)
        .collect::<Vec<_>>();
    Ok((
        output.clone(),
        BTreeMap::from([
            (format!("layer_{layer}_q"), hash_f32(&q)),
            (format!("layer_{layer}_keys"), hash_f32(&keys)),
            (format!("layer_{layer}_attention"), hash_f32(&attention)),
            (
                format!("layer_{layer}_attention_residual"),
                hash_f32(&attention_residual),
            ),
            (format!("layer_{layer}_ffn"), hash_f32(&down)),
            (format!("layer_{layer}_output"), hash_f32(&output)),
        ]),
    ))
}

fn execute_material_package(manifest_path: &Path, output: &Path) -> Result<(), String> {
    let package: MaterialPackage =
        serde_json::from_slice(&fs::read(manifest_path).map_err(|error| error.to_string())?)
            .map_err(|error| format!("material manifest parse: {error}"))?;
    if package.schema != "pulsarmlx.f017.dprefix-material-package"
        || package.attempt_id != ATTEMPT
        || package.prompt_package_sha256 != PROMPT_PACKAGE
        || package.inventory_sha256 != INVENTORY
        || package.tensor_count != 40
        || package.tensors.len() != 40
    {
        return Err("IDENTITY_BINDING: material package".to_owned());
    }
    let identity_relative = Path::new(&package.identity_binding);
    if identity_relative.is_absolute()
        || identity_relative
            .components()
            .any(|component| matches!(component, std::path::Component::ParentDir))
    {
        return Err("IDENTITY_BINDING: unsafe identity path".to_owned());
    }
    let binding_path = manifest_path
        .parent()
        .unwrap_or(Path::new("."))
        .join(identity_relative);
    self_verify(&binding_path)?;
    let mut ordinals = package
        .tensors
        .iter()
        .map(|tensor| tensor.ordinal)
        .collect::<Vec<_>>();
    ordinals.sort_unstable();
    if ordinals != (0..40).collect::<Vec<_>>() {
        return Err("ACCESS_BUDGET: material ordinals".to_owned());
    }
    let package_root = manifest_path.parent().unwrap_or(Path::new("."));
    let mut tensors = BTreeMap::new();
    let mut packed_hashes = BTreeMap::new();
    let mut decoded_hashes = BTreeMap::new();
    for descriptor in &package.tensors {
        if tensors.contains_key(&descriptor.name) {
            return Err("ACCESS_BUDGET: duplicate tensor".to_owned());
        }
        packed_hashes.insert(descriptor.name.clone(), descriptor.packed_sha256.clone());
        let decoded = decode_material(descriptor, package_root)?;
        decoded_hashes.insert(descriptor.name.clone(), hash_f32(&decoded.values));
        tensors.insert(descriptor.name.clone(), decoded);
    }
    let identity_confirmations = BTreeMap::from([
        (
            "Q4_K".to_owned(),
            packed_hashes.get("token_embd.weight")
                == Some(
                    &"3e4c34141f918333883442b8ff44c78c9927295ae16378047a8a36edeb7ed5ef".to_owned(),
                )
                && decoded_hashes.get("token_embd.weight")
                    == Some(
                        &"e2cff562131674156704ca21b2b6e850337c2e5d8948b4dcc9f14676ecf8f2c1"
                            .to_owned(),
                    ),
        ),
        (
            "Q6_K".to_owned(),
            packed_hashes.get("blk.0.ffn_down.weight")
                == Some(
                    &"845b4fd6b5d290506e576ca5099336bae7d28f3ebfcec964ed2136c3ea4a8ede".to_owned(),
                )
                && decoded_hashes.get("blk.0.ffn_down.weight")
                    == Some(
                        &"ff26151a7997379c1713b90852fdbfd8301b36d5d89a1c3bb623b9b8f273483a"
                            .to_owned(),
                    ),
        ),
    ]);
    if !identity_confirmations["Q4_K"] {
        return Err("Q4_IDENTITY_CONFIRMATION".to_owned());
    }
    if !identity_confirmations["Q6_K"] {
        return Err("Q6_IDENTITY_CONFIRMATION".to_owned());
    }
    let embedding_tensor = tensors
        .get("token_embd.weight")
        .ok_or("candidate embedding absent")?;
    if embedding_tensor.dimensions != [6144, 154880] {
        return Err("candidate embedding shape".to_owned());
    }
    let embedding = embedding_tensor.values[9703 * 6144..9704 * 6144].to_vec();
    let mut dispatch = DispatchEvidence::default();
    let mut stage_hashes = Vec::new();
    let mut final_state = Vec::new();
    for _ in 0..10 {
        let mut stages = BTreeMap::from([("embedding".to_owned(), hash_f32(&embedding))]);
        let mut hidden = embedding.clone();
        for layer in 0..3 {
            let (next, layer_stages) = run_real_layer(&mut tensors, &hidden, layer, &mut dispatch)?;
            stages.extend(layer_stages);
            hidden = next;
        }
        stages.insert("layer_3_entry".to_owned(), hash_f32(&hidden));
        final_state = hidden;
        stage_hashes.push(stages);
    }
    let deterministic = stage_hashes.windows(2).all(|pair| pair[0] == pair[1]);
    if !deterministic {
        return Err("REPEAT_DETERMINISM".to_owned());
    }
    let retained = canonical_f32(&final_state);
    let retained_path = output.with_extension("layer3-entry.f32le");
    fs::write(&retained_path, &retained).map_err(|error| format!("RETENTION_FAILURE: {error}"))?;
    let mut permissions = fs::metadata(&retained_path)
        .map_err(|error| error.to_string())?
        .permissions();
    permissions.set_readonly(true);
    fs::set_permissions(&retained_path, permissions).map_err(|error| error.to_string())?;
    let evidence = RealCandidateEvidence {
        schema: "pulsarmlx.f017.dprefix-native-candidate-result",
        attempt_id: ATTEMPT,
        result: "CANDIDATE_COMPLETE_PENDING_ORACLE_COMPARISON",
        real_checkpoint_reads_by_candidate: 0,
        material_tensor_count: 40,
        input_packed_hashes: packed_hashes,
        input_decoded_hashes: decoded_hashes,
        identity_confirmations,
        repeats: 10,
        deterministic,
        stage_hashes,
        dispatch,
        retained_state: RetainedState {
            dtype: "little_endian_f32",
            shape: [6144],
            count: 6144,
            sha256: sha_bytes(&retained),
            canonical_bytes: retained.len(),
            immutable: true,
            read_only: true,
        },
    };
    fs::write(
        output,
        serde_json::to_vec_pretty(&evidence).map_err(|error| error.to_string())?,
    )
    .map_err(|error| error.to_string())
}

fn usage() -> &'static str {
    "usage: f017-dense-prefix-candidate --self-verify <identity.json> | --synthetic-rehearsal <evidence.json> | --execute-material-package <manifest.json> <evidence.json>"
}

fn run() -> Result<(), String> {
    let arguments = std::env::args_os().skip(1).collect::<Vec<_>>();
    if arguments.len() == 3 && arguments[0] == "--execute-material-package" {
        return execute_material_package(Path::new(&arguments[1]), Path::new(&arguments[2]));
    }
    if arguments.len() != 2 {
        return Err(usage().to_owned());
    }
    let mode = arguments[0].to_string_lossy();
    let path = PathBuf::from(&arguments[1]);
    match mode.as_ref() {
        "--self-verify" => {
            let result = self_verify(&path)?;
            println!(
                "{}",
                serde_json::to_string_pretty(&result).map_err(|error| error.to_string())?
            );
            Ok(())
        }
        "--synthetic-rehearsal" => synthetic_rehearsal(&path),
        _ => Err(format!("scope refusal: {}; {mode}", usage())),
    }
}

fn main() {
    if let Err(error) = run() {
        eprintln!("{error}");
        std::process::exit(2);
    }
}
