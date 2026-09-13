//! Typed, fail-closed Qwen3MoE metadata and tensor-role admission.
//!
//! This module consumes a parsed GGUF header/tensor catalog only. It never
//! opens a path, downloads a model, reads tensor payload bytes, or executes a
//! model. The caller that supplies a catalog must bind it to the separately
//! verified whole-file artifact identity.

use backend::{ContractError, ErrorCategory};
use gguf::{Gguf, TensorInfo, TensorType, Value};
use std::collections::{BTreeMap, BTreeSet};

pub const QWEN3MOE_ADAPTER_CONTRACT_ID: &str = "qwen3moe-adapter-admission-v1";
pub const QWEN3MOE_REPOSITORY_ID: &str = "Qwen/Qwen3-30B-A3B-GGUF";
pub const QWEN3MOE_REVISION: &str = "e4d4bafdfb96a411a163846265362aceb0b9c63a";
pub const QWEN3MOE_FILENAME: &str = "Qwen3-30B-A3B-Q8_0.gguf";
pub const QWEN3MOE_FILE_BYTES: u64 = 32_483_931_648;
pub const QWEN3MOE_SHA256: &str =
    "4ad960d180b16f56024f5b704697e5dd5b0837167c2e515ef0569abfc599743c";
pub const QWEN3MOE_LAYER_COUNT: u32 = 48;
pub const QWEN3MOE_HIDDEN_WIDTH: u64 = 2_048;
pub const QWEN3MOE_EXPERT_COUNT: u64 = 128;
pub const QWEN3MOE_TOP_K: u64 = 8;
pub const QWEN3MOE_EXPERT_FFN_WIDTH: u64 = 768;
pub const QWEN3MOE_TENSOR_COUNT: usize = 579;
const QWEN3MOE_GGUF_VERSION: u32 = 3;
const QWEN3MOE_DATA_OFFSET: u64 = 5_969_408;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Qwen3MoeArtifactBinding {
    pub repository_id: String,
    pub revision: String,
    pub filename: String,
    pub size_bytes: u64,
    pub sha256: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Qwen3MoeMetadata {
    pub architecture: String,
    pub hidden_width: u64,
    pub layer_count: u64,
    pub expert_count: u64,
    pub top_k: u64,
    pub expert_ffn_width: u64,
    pub attention_head_count: u64,
    pub attention_head_count_kv: u64,
    pub key_length: u64,
    pub value_length: u64,
    pub feed_forward_width: u64,
    pub context_length: u64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum Qwen3MoeTensorRole {
    OutputWeight,
    OutputNorm,
    TokenEmbedding,
    AttentionKeyWeight,
    AttentionKeyNorm,
    AttentionNorm,
    AttentionOutputWeight,
    AttentionQueryWeight,
    AttentionQueryNorm,
    AttentionValueWeight,
    ExpertDownWeight,
    ExpertGateWeight,
    RouterWeight,
    FfnNorm,
    ExpertUpWeight,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Qwen3MoeTensorDescriptor {
    pub role: Qwen3MoeTensorRole,
    pub layer_index: Option<u32>,
    pub name: String,
    /// GGUF dimensions, fastest axis first.
    pub gguf_shape: Vec<u64>,
    /// Reader shape: reversed logical axes, with Q8_0 row bytes as the final axis.
    pub reader_shape: Vec<u64>,
    /// Execution shape after restoring logical axes to model order.
    pub execution_shape: Vec<u64>,
    pub gguf_type: String,
    pub quantization: String,
    pub orientation: String,
    pub logical_elements: u64,
    pub encoded_bytes: u64,
    pub absolute_data_offset: u64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Qwen3MoeAdmissionInput {
    pub artifact: Qwen3MoeArtifactBinding,
    pub metadata: Qwen3MoeMetadata,
    pub tensors: Vec<Qwen3MoeTensorDescriptor>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Qwen3MoeAdapterDescriptor {
    pub contract_id: String,
    pub artifact: Qwen3MoeArtifactBinding,
    pub metadata: Qwen3MoeMetadata,
    /// Complete 579-entry tensor catalog in GGUF file order.
    pub tensors: Vec<Qwen3MoeTensorDescriptor>,
}

impl Qwen3MoeAdapterDescriptor {
    pub fn tensor(&self, name: &str) -> Option<&Qwen3MoeTensorDescriptor> {
        self.tensors.iter().find(|tensor| tensor.name == name)
    }

    pub fn layer0_tensor(&self, role: Qwen3MoeTensorRole) -> Option<&Qwen3MoeTensorDescriptor> {
        self.tensors
            .iter()
            .find(|tensor| tensor.layer_index == Some(0) && tensor.role == role)
    }
}

/// Admit one exact, typed Qwen3MoE catalog. No path or payload bytes are
/// accepted by this API; artifact identity is supplied separately by the
/// read-only verifier that produced the catalog.
pub fn admit_qwen3moe_adapter(
    input: Qwen3MoeAdmissionInput,
) -> Result<Qwen3MoeAdapterDescriptor, ContractError> {
    validate_artifact(&input.artifact)?;
    validate_metadata(&input.metadata)?;

    let expected = expected_tensor_specs();
    let expected_by_name: BTreeMap<&str, &TensorSpec> = expected
        .iter()
        .map(|spec| (spec.name.as_str(), spec))
        .collect();
    let mut seen = BTreeSet::new();
    for tensor in &input.tensors {
        if !seen.insert(tensor.name.as_str()) {
            return Err(adapter_error(
                "duplicate_tensor_role",
                "the Qwen3MoE tensor catalog contains a duplicate tensor name",
            ));
        }
        let Some(spec) = expected_by_name.get(tensor.name.as_str()) else {
            return Err(adapter_error(
                "unexpected_tensor_role",
                "the Qwen3MoE tensor catalog contains an unreviewed tensor alias",
            ));
        };
        validate_tensor(tensor, spec)?;
    }
    if seen.len() != expected_by_name.len() {
        return Err(adapter_error(
            "missing_tensor_role",
            "the Qwen3MoE tensor catalog is missing a required tensor role",
        ));
    }

    Ok(Qwen3MoeAdapterDescriptor {
        contract_id: QWEN3MOE_ADAPTER_CONTRACT_ID.to_owned(),
        artifact: input.artifact,
        metadata: input.metadata,
        tensors: input.tensors,
    })
}

pub(crate) fn admission_input_from_gguf(
    gguf: &Gguf,
    artifact: Qwen3MoeArtifactBinding,
) -> Result<Qwen3MoeAdmissionInput, ContractError> {
    if gguf.version != QWEN3MOE_GGUF_VERSION
        || gguf.data_offset != QWEN3MOE_DATA_OFFSET
        || gguf.tensors.len() != QWEN3MOE_TENSOR_COUNT
    {
        return Err(adapter_error(
            "model_metadata_mismatch",
            "the GGUF version, data offset, or tensor count differs from the pinned map",
        ));
    }
    let metadata = metadata_from_gguf(gguf)?;
    let tensors = gguf
        .tensors
        .iter()
        .map(|tensor| tensor_from_gguf(tensor, gguf.data_offset))
        .collect::<Result<Vec<_>, _>>()?;
    Ok(Qwen3MoeAdmissionInput {
        artifact,
        metadata,
        tensors,
    })
}

fn validate_artifact(artifact: &Qwen3MoeArtifactBinding) -> Result<(), ContractError> {
    if artifact.repository_id != QWEN3MOE_REPOSITORY_ID
        || artifact.revision != QWEN3MOE_REVISION
        || artifact.filename != QWEN3MOE_FILENAME
        || artifact.size_bytes != QWEN3MOE_FILE_BYTES
    {
        return Err(adapter_error(
            "model_artifact_mismatch",
            "the Qwen3MoE source revision, filename, or byte size is not admitted",
        ));
    }
    if artifact.sha256 != QWEN3MOE_SHA256 {
        return Err(adapter_error(
            "model_checksum_mismatch",
            "the Qwen3MoE whole-file SHA-256 is not admitted",
        ));
    }
    Ok(())
}

fn validate_metadata(metadata: &Qwen3MoeMetadata) -> Result<(), ContractError> {
    if metadata.architecture != "qwen3moe" {
        return Err(adapter_error(
            "model_architecture_mismatch",
            "only the exact qwen3moe architecture is admitted; aliases are rejected",
        ));
    }
    let expected = [
        (metadata.hidden_width, QWEN3MOE_HIDDEN_WIDTH),
        (metadata.layer_count, QWEN3MOE_LAYER_COUNT as u64),
        (metadata.expert_count, QWEN3MOE_EXPERT_COUNT),
        (metadata.top_k, QWEN3MOE_TOP_K),
        (metadata.expert_ffn_width, QWEN3MOE_EXPERT_FFN_WIDTH),
        (metadata.attention_head_count, 32),
        (metadata.attention_head_count_kv, 4),
        (metadata.key_length, 128),
        (metadata.value_length, 128),
        (metadata.feed_forward_width, 6_144),
        (metadata.context_length, 40_960),
    ];
    if expected.iter().any(|(actual, wanted)| actual != wanted) {
        return Err(adapter_error(
            "model_metadata_mismatch",
            "required qwen3moe dimensions differ from the pinned GGUF metadata",
        ));
    }
    Ok(())
}

#[derive(Debug, Clone)]
struct TensorSpec {
    role: Qwen3MoeTensorRole,
    layer_index: Option<u32>,
    name: String,
    gguf_shape: Vec<u64>,
    reader_shape: Vec<u64>,
    execution_shape: Vec<u64>,
    gguf_type: &'static str,
    quantization: &'static str,
    orientation: &'static str,
    logical_elements: u64,
    encoded_bytes: u64,
}

fn expected_tensor_specs() -> Vec<TensorSpec> {
    let mut specs = vec![
        spec(None, Qwen3MoeTensorRole::OutputWeight, "output.weight"),
        spec(None, Qwen3MoeTensorRole::OutputNorm, "output_norm.weight"),
        spec(
            None,
            Qwen3MoeTensorRole::TokenEmbedding,
            "token_embd.weight",
        ),
    ];
    for layer in 0..QWEN3MOE_LAYER_COUNT {
        for (role, suffix) in [
            (Qwen3MoeTensorRole::AttentionKeyWeight, "attn_k.weight"),
            (Qwen3MoeTensorRole::AttentionKeyNorm, "attn_k_norm.weight"),
            (Qwen3MoeTensorRole::AttentionNorm, "attn_norm.weight"),
            (
                Qwen3MoeTensorRole::AttentionOutputWeight,
                "attn_output.weight",
            ),
            (Qwen3MoeTensorRole::AttentionQueryWeight, "attn_q.weight"),
            (Qwen3MoeTensorRole::AttentionQueryNorm, "attn_q_norm.weight"),
            (Qwen3MoeTensorRole::AttentionValueWeight, "attn_v.weight"),
            (Qwen3MoeTensorRole::ExpertDownWeight, "ffn_down_exps.weight"),
            (Qwen3MoeTensorRole::ExpertGateWeight, "ffn_gate_exps.weight"),
            (Qwen3MoeTensorRole::RouterWeight, "ffn_gate_inp.weight"),
            (Qwen3MoeTensorRole::FfnNorm, "ffn_norm.weight"),
            (Qwen3MoeTensorRole::ExpertUpWeight, "ffn_up_exps.weight"),
        ] {
            specs.push(spec(Some(layer), role, suffix));
        }
    }
    specs
}

fn spec(layer_index: Option<u32>, role: Qwen3MoeTensorRole, suffix: &str) -> TensorSpec {
    let name = match layer_index {
        Some(layer) => format!("blk.{layer}.{suffix}"),
        None => suffix.to_owned(),
    };
    let (gguf_shape, gguf_type, quantization, orientation) = role_layout(role);
    let execution_shape = gguf_shape.iter().rev().copied().collect::<Vec<_>>();
    let reader_shape = reader_shape(&gguf_shape, quantization);
    let logical_elements = gguf_shape.iter().product();
    let encoded_bytes = encoded_bytes(&gguf_shape, quantization);
    TensorSpec {
        role,
        layer_index,
        name,
        gguf_shape,
        reader_shape,
        execution_shape,
        gguf_type,
        quantization,
        orientation,
        logical_elements,
        encoded_bytes,
    }
}

fn role_layout(role: Qwen3MoeTensorRole) -> (Vec<u64>, &'static str, &'static str, &'static str) {
    match role {
        Qwen3MoeTensorRole::OutputWeight | Qwen3MoeTensorRole::TokenEmbedding => (
            vec![2_048, 151_936],
            "Q8_0",
            "Q8_0",
            "vocab_rows_hidden_columns",
        ),
        Qwen3MoeTensorRole::OutputNorm
        | Qwen3MoeTensorRole::AttentionNorm
        | Qwen3MoeTensorRole::FfnNorm => (vec![2_048], "F32", "none_f32", "hidden_vector"),
        Qwen3MoeTensorRole::AttentionKeyNorm | Qwen3MoeTensorRole::AttentionQueryNorm => {
            (vec![128], "F32", "none_f32", "head_vector")
        }
        Qwen3MoeTensorRole::AttentionKeyWeight | Qwen3MoeTensorRole::AttentionValueWeight => (
            vec![2_048, 512],
            "Q8_0",
            "Q8_0",
            "projection_rows_hidden_columns",
        ),
        Qwen3MoeTensorRole::AttentionOutputWeight => (
            vec![4_096, 2_048],
            "Q8_0",
            "Q8_0",
            "projection_rows_attention_columns",
        ),
        Qwen3MoeTensorRole::AttentionQueryWeight => (
            vec![2_048, 4_096],
            "Q8_0",
            "Q8_0",
            "projection_rows_hidden_columns",
        ),
        Qwen3MoeTensorRole::ExpertDownWeight => (
            vec![768, 2_048, 128],
            "Q8_0",
            "Q8_0",
            "expert_major_output_rows_hidden_input_columns",
        ),
        Qwen3MoeTensorRole::ExpertGateWeight | Qwen3MoeTensorRole::ExpertUpWeight => (
            vec![2_048, 768, 128],
            "Q8_0",
            "Q8_0",
            "expert_major_intermediate_rows_hidden_input_columns",
        ),
        Qwen3MoeTensorRole::RouterWeight => (
            vec![2_048, 128],
            "F32",
            "none_f32",
            "expert_major_rows_input_columns",
        ),
    }
}

fn reader_shape(gguf_shape: &[u64], quantization: &str) -> Vec<u64> {
    if quantization == "Q8_0" {
        let mut shape = gguf_shape[1..].iter().rev().copied().collect::<Vec<_>>();
        shape.push(
            TensorType::Q8_0
                .row_bytes(gguf_shape[0])
                .expect("Q8_0 row layout"),
        );
        shape
    } else {
        gguf_shape.iter().rev().copied().collect()
    }
}

fn encoded_bytes(gguf_shape: &[u64], quantization: &str) -> u64 {
    if quantization == "Q8_0" {
        TensorType::Q8_0
            .row_bytes(gguf_shape[0])
            .expect("Q8_0 row layout")
            * gguf_shape[1..].iter().product::<u64>()
    } else {
        gguf_shape.iter().product::<u64>() * 4
    }
}

fn validate_tensor(
    tensor: &Qwen3MoeTensorDescriptor,
    spec: &TensorSpec,
) -> Result<(), ContractError> {
    if tensor.role != spec.role || tensor.layer_index != spec.layer_index {
        return Err(adapter_error(
            "tensor_role_mismatch",
            "a Qwen3MoE tensor name is bound to the wrong semantic role",
        ));
    }
    if tensor.gguf_shape != spec.gguf_shape
        || tensor.reader_shape != spec.reader_shape
        || tensor.execution_shape != spec.execution_shape
    {
        return Err(adapter_error(
            "tensor_shape_mismatch",
            "a Qwen3MoE tensor shape or orientation differs from the pinned map",
        ));
    }
    if tensor.gguf_type != spec.gguf_type || tensor.quantization != spec.quantization {
        return Err(adapter_error(
            "unsupported_tensor_quantization",
            "a Qwen3MoE tensor uses an unadmitted storage type",
        ));
    }
    if tensor.orientation != spec.orientation {
        return Err(adapter_error(
            "invalid_tensor_orientation",
            "a Qwen3MoE tensor orientation differs from the pinned map",
        ));
    }
    if tensor.logical_elements != spec.logical_elements
        || tensor.encoded_bytes != spec.encoded_bytes
    {
        return Err(adapter_error(
            "tensor_size_mismatch",
            "a Qwen3MoE tensor logical or encoded size differs from the pinned map",
        ));
    }
    let end = tensor
        .absolute_data_offset
        .checked_add(tensor.encoded_bytes)
        .ok_or_else(|| {
            adapter_error("invalid_tensor_range", "a Qwen3MoE tensor range overflows")
        })?;
    if tensor.absolute_data_offset >= QWEN3MOE_FILE_BYTES || end > QWEN3MOE_FILE_BYTES {
        return Err(adapter_error(
            "invalid_tensor_range",
            "a Qwen3MoE tensor range is outside the pinned artifact",
        ));
    }
    Ok(())
}

fn metadata_from_gguf(gguf: &Gguf) -> Result<Qwen3MoeMetadata, ContractError> {
    let architecture = match gguf.metadata.get("general.architecture") {
        Some(Value::String(value)) => value.clone(),
        _ => {
            return Err(adapter_error(
                "model_metadata_type_mismatch",
                "GGUF architecture metadata is missing or not STRING",
            ));
        }
    };
    Ok(Qwen3MoeMetadata {
        architecture,
        hidden_width: exact_u32(gguf, "qwen3moe.embedding_length")?,
        layer_count: exact_u32(gguf, "qwen3moe.block_count")?,
        expert_count: exact_u32(gguf, "qwen3moe.expert_count")?,
        top_k: exact_u32(gguf, "qwen3moe.expert_used_count")?,
        expert_ffn_width: exact_u32(gguf, "qwen3moe.expert_feed_forward_length")?,
        attention_head_count: exact_u32(gguf, "qwen3moe.attention.head_count")?,
        attention_head_count_kv: exact_u32(gguf, "qwen3moe.attention.head_count_kv")?,
        key_length: exact_u32(gguf, "qwen3moe.attention.key_length")?,
        value_length: exact_u32(gguf, "qwen3moe.attention.value_length")?,
        feed_forward_width: exact_u32(gguf, "qwen3moe.feed_forward_length")?,
        context_length: exact_u32(gguf, "qwen3moe.context_length")?,
    })
}

fn exact_u32(gguf: &Gguf, key: &str) -> Result<u64, ContractError> {
    match gguf.metadata.get(key) {
        Some(Value::U32(value)) => Ok(u64::from(*value)),
        _ => Err(adapter_error(
            "model_metadata_type_mismatch",
            "a required Qwen3MoE GGUF metadata value is missing or not UINT32",
        )),
    }
}

fn tensor_from_gguf(
    tensor: &TensorInfo,
    data_offset: u64,
) -> Result<Qwen3MoeTensorDescriptor, ContractError> {
    let (layer_index, role) = role_for_name(&tensor.name).ok_or_else(|| {
        adapter_error(
            "unexpected_tensor_role",
            "the Qwen3MoE GGUF tensor catalog contains an unreviewed tensor alias",
        )
    })?;
    let spec = spec(layer_index, role, suffix_for_role(role));
    let quantization = match tensor.ty {
        TensorType::F32 => "none_f32",
        TensorType::Q8_0 => "Q8_0",
        _ => {
            return Err(adapter_error(
                "unsupported_tensor_quantization",
                "the Qwen3MoE GGUF tensor type is not admitted",
            ));
        }
    };
    if tensor.dims != spec.gguf_shape {
        return Err(adapter_error(
            "tensor_shape_mismatch",
            "the Qwen3MoE GGUF tensor dimensions differ from the pinned map",
        ));
    }
    let encoded_bytes = tensor.byte_size().ok_or_else(|| {
        adapter_error(
            "unsupported_tensor_quantization",
            "the Qwen3MoE GGUF tensor byte layout is not supported",
        )
    })?;
    let logical_elements = tensor.n_elements();
    let absolute_data_offset = data_offset.checked_add(tensor.offset).ok_or_else(|| {
        adapter_error("invalid_tensor_range", "a Qwen3MoE tensor offset overflows")
    })?;
    Ok(Qwen3MoeTensorDescriptor {
        role,
        layer_index,
        name: tensor.name.clone(),
        gguf_shape: tensor.dims.clone(),
        reader_shape: reader_shape(&tensor.dims, quantization),
        execution_shape: tensor.dims.iter().rev().copied().collect(),
        gguf_type: match tensor.ty {
            TensorType::F32 => "F32".to_owned(),
            TensorType::Q8_0 => "Q8_0".to_owned(),
            _ => unreachable!(),
        },
        quantization: quantization.to_owned(),
        orientation: spec.orientation.to_owned(),
        logical_elements,
        encoded_bytes,
        absolute_data_offset,
    })
}

fn role_for_name(name: &str) -> Option<(Option<u32>, Qwen3MoeTensorRole)> {
    let global = match name {
        "output.weight" => Some(Qwen3MoeTensorRole::OutputWeight),
        "output_norm.weight" => Some(Qwen3MoeTensorRole::OutputNorm),
        "token_embd.weight" => Some(Qwen3MoeTensorRole::TokenEmbedding),
        _ => None,
    };
    if let Some(role) = global {
        return Some((None, role));
    }
    let rest = name.strip_prefix("blk.")?;
    let (layer, suffix) = rest.split_once('.')?;
    let layer = layer.parse::<u32>().ok()?;
    if layer >= QWEN3MOE_LAYER_COUNT {
        return None;
    }
    let role = match suffix {
        "attn_k.weight" => Qwen3MoeTensorRole::AttentionKeyWeight,
        "attn_k_norm.weight" => Qwen3MoeTensorRole::AttentionKeyNorm,
        "attn_norm.weight" => Qwen3MoeTensorRole::AttentionNorm,
        "attn_output.weight" => Qwen3MoeTensorRole::AttentionOutputWeight,
        "attn_q.weight" => Qwen3MoeTensorRole::AttentionQueryWeight,
        "attn_q_norm.weight" => Qwen3MoeTensorRole::AttentionQueryNorm,
        "attn_v.weight" => Qwen3MoeTensorRole::AttentionValueWeight,
        "ffn_down_exps.weight" => Qwen3MoeTensorRole::ExpertDownWeight,
        "ffn_gate_exps.weight" => Qwen3MoeTensorRole::ExpertGateWeight,
        "ffn_gate_inp.weight" => Qwen3MoeTensorRole::RouterWeight,
        "ffn_norm.weight" => Qwen3MoeTensorRole::FfnNorm,
        "ffn_up_exps.weight" => Qwen3MoeTensorRole::ExpertUpWeight,
        _ => return None,
    };
    Some((Some(layer), role))
}

fn suffix_for_role(role: Qwen3MoeTensorRole) -> &'static str {
    match role {
        Qwen3MoeTensorRole::OutputWeight => "output.weight",
        Qwen3MoeTensorRole::OutputNorm => "output_norm.weight",
        Qwen3MoeTensorRole::TokenEmbedding => "token_embd.weight",
        Qwen3MoeTensorRole::AttentionKeyWeight => "attn_k.weight",
        Qwen3MoeTensorRole::AttentionKeyNorm => "attn_k_norm.weight",
        Qwen3MoeTensorRole::AttentionNorm => "attn_norm.weight",
        Qwen3MoeTensorRole::AttentionOutputWeight => "attn_output.weight",
        Qwen3MoeTensorRole::AttentionQueryWeight => "attn_q.weight",
        Qwen3MoeTensorRole::AttentionQueryNorm => "attn_q_norm.weight",
        Qwen3MoeTensorRole::AttentionValueWeight => "attn_v.weight",
        Qwen3MoeTensorRole::ExpertDownWeight => "ffn_down_exps.weight",
        Qwen3MoeTensorRole::ExpertGateWeight => "ffn_gate_exps.weight",
        Qwen3MoeTensorRole::RouterWeight => "ffn_gate_inp.weight",
        Qwen3MoeTensorRole::FfnNorm => "ffn_norm.weight",
        Qwen3MoeTensorRole::ExpertUpWeight => "ffn_up_exps.weight",
    }
}

fn adapter_error(code: &'static str, message: &'static str) -> ContractError {
    ContractError::new(ErrorCategory::InvalidModel, code, message)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Read;

    fn input_with_tensors(tensors: Vec<Qwen3MoeTensorDescriptor>) -> Qwen3MoeAdmissionInput {
        Qwen3MoeAdmissionInput {
            artifact: Qwen3MoeArtifactBinding {
                repository_id: QWEN3MOE_REPOSITORY_ID.to_owned(),
                revision: QWEN3MOE_REVISION.to_owned(),
                filename: QWEN3MOE_FILENAME.to_owned(),
                size_bytes: QWEN3MOE_FILE_BYTES,
                sha256: QWEN3MOE_SHA256.to_owned(),
            },
            metadata: Qwen3MoeMetadata {
                architecture: "qwen3moe".to_owned(),
                hidden_width: 2_048,
                layer_count: 48,
                expert_count: 128,
                top_k: 8,
                expert_ffn_width: 768,
                attention_head_count: 32,
                attention_head_count_kv: 4,
                key_length: 128,
                value_length: 128,
                feed_forward_width: 6_144,
                context_length: 40_960,
            },
            tensors,
        }
    }

    fn descriptor_from_spec(
        spec: TensorSpec,
        absolute_data_offset: u64,
    ) -> Qwen3MoeTensorDescriptor {
        Qwen3MoeTensorDescriptor {
            role: spec.role,
            layer_index: spec.layer_index,
            name: spec.name,
            gguf_shape: spec.gguf_shape,
            reader_shape: spec.reader_shape,
            execution_shape: spec.execution_shape,
            gguf_type: spec.gguf_type.to_owned(),
            quantization: spec.quantization.to_owned(),
            orientation: spec.orientation.to_owned(),
            logical_elements: spec.logical_elements,
            encoded_bytes: spec.encoded_bytes,
            absolute_data_offset,
        }
    }

    fn complete_input() -> Qwen3MoeAdmissionInput {
        input_with_tensors(
            expected_tensor_specs()
                .into_iter()
                .map(|spec| descriptor_from_spec(spec, 1))
                .collect(),
        )
    }

    #[test]
    fn expected_map_has_complete_layer_and_global_cardinality() {
        let specs = expected_tensor_specs();
        assert_eq!(specs.len(), QWEN3MOE_TENSOR_COUNT);
        assert_eq!(
            specs
                .iter()
                .filter(|spec| spec.layer_index == Some(0))
                .count(),
            12
        );
        assert_eq!(
            specs
                .iter()
                .filter(|spec| spec.layer_index.is_none())
                .count(),
            3
        );
    }

    #[test]
    fn complete_typed_map_admits_and_exposes_layer0_semantics() {
        let adapter = admit_qwen3moe_adapter(complete_input()).expect("complete map is admitted");
        assert_eq!(adapter.contract_id, QWEN3MOE_ADAPTER_CONTRACT_ID);
        assert_eq!(adapter.tensors.len(), QWEN3MOE_TENSOR_COUNT);
        let router = adapter
            .layer0_tensor(Qwen3MoeTensorRole::RouterWeight)
            .expect("layer-0 router");
        assert_eq!(router.gguf_shape, [2_048, 128]);
        assert_eq!(router.reader_shape, [128, 2_048]);
        assert_eq!(router.execution_shape, [128, 2_048]);
        assert_eq!(router.quantization, "none_f32");
        let gate = adapter
            .layer0_tensor(Qwen3MoeTensorRole::ExpertGateWeight)
            .expect("layer-0 expert gate");
        assert_eq!(gate.gguf_shape, [2_048, 768, 128]);
        assert_eq!(gate.reader_shape, [128, 768, 2_176]);
        assert_eq!(gate.execution_shape, [128, 768, 2_048]);
        assert_eq!(gate.quantization, "Q8_0");
    }

    #[test]
    fn missing_duplicate_alias_shape_orientation_and_type_are_rejected() {
        let mut missing = complete_input();
        missing.tensors.pop();
        assert_eq!(
            admit_qwen3moe_adapter(missing)
                .expect_err("missing role must fail")
                .code(),
            "missing_tensor_role"
        );

        let mut duplicate = complete_input();
        duplicate.tensors.push(duplicate.tensors[0].clone());
        assert_eq!(
            admit_qwen3moe_adapter(duplicate)
                .expect_err("duplicate role must fail")
                .code(),
            "duplicate_tensor_role"
        );

        for (mutation, expected_code) in [
            ("alias", "unexpected_tensor_role"),
            ("shape", "tensor_shape_mismatch"),
            ("orientation", "invalid_tensor_orientation"),
            ("type", "unsupported_tensor_quantization"),
        ] {
            let mut input = complete_input();
            let tensor = input
                .tensors
                .iter_mut()
                .find(|tensor| tensor.name == "blk.0.ffn_gate_inp.weight")
                .expect("router tensor in complete map");
            match mutation {
                "alias" => tensor.name = "blk.0.ffn_gate_inp.bias".to_owned(),
                "shape" => tensor.gguf_shape[0] = 1,
                "orientation" => tensor.orientation = "input_rows_expert_columns".to_owned(),
                "type" => {
                    tensor.gguf_type = "Q4_K".to_owned();
                    tensor.quantization = "Q4_K".to_owned();
                }
                _ => unreachable!(),
            }
            assert_eq!(
                admit_qwen3moe_adapter(input)
                    .expect_err("mutated tensor must fail closed")
                    .code(),
                expected_code
            );
        }
    }

    #[test]
    fn artifact_and_metadata_identity_mismatches_are_rejected() {
        let mut artifact = complete_input();
        artifact.artifact.sha256 = "0".repeat(64);
        assert_eq!(
            admit_qwen3moe_adapter(artifact)
                .expect_err("wrong whole-file hash must fail")
                .code(),
            "model_checksum_mismatch"
        );

        let mut metadata = complete_input();
        metadata.metadata.layer_count = 47;
        assert_eq!(
            admit_qwen3moe_adapter(metadata)
                .expect_err("wrong layer count must fail")
                .code(),
            "model_metadata_mismatch"
        );
    }

    #[test]
    #[ignore = "requires the approved external GGUF via PULSARMLX_QWEN_GGUF"]
    fn pinned_header_catalog_admits_without_reading_tensor_payloads() {
        let path = std::env::var_os("PULSARMLX_QWEN_GGUF")
            .expect("PULSARMLX_QWEN_GGUF must identify the approved file");
        let file = std::fs::File::open(path).expect("open approved GGUF read-only");
        let mut header = Vec::new();
        file.take(64 * 1024 * 1024)
            .read_to_end(&mut header)
            .expect("read bounded GGUF header");
        let gguf = Gguf::parse(&header).expect("parse approved GGUF header");
        let input = admission_input_from_gguf(
            &gguf,
            Qwen3MoeArtifactBinding {
                repository_id: QWEN3MOE_REPOSITORY_ID.to_owned(),
                revision: QWEN3MOE_REVISION.to_owned(),
                filename: QWEN3MOE_FILENAME.to_owned(),
                size_bytes: QWEN3MOE_FILE_BYTES,
                sha256: QWEN3MOE_SHA256.to_owned(),
            },
        )
        .expect("the approved GGUF catalog is typed");
        let adapter = admit_qwen3moe_adapter(input).expect("the approved catalog is admitted");
        assert_eq!(adapter.tensors.len(), QWEN3MOE_TENSOR_COUNT);
        assert_eq!(adapter.metadata.architecture, "qwen3moe");
        assert_eq!(
            adapter
                .tensor("blk.0.ffn_gate_inp.weight")
                .expect("router tensor")
                .absolute_data_offset,
            1_115_085_312
        );
        assert_eq!(
            adapter
                .tensor("blk.0.ffn_gate_exps.weight")
                .expect("expert gate tensor")
                .absolute_data_offset,
            901_175_808
        );
    }
}
