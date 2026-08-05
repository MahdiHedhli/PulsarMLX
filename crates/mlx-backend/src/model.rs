//! Admission contract for the first bounded external Qwen model slice.
//!
//! This module validates caller-observed artifact metadata. It deliberately
//! performs no file access, model acquisition, parsing, or execution.

use backend::{ContractError, ErrorCategory};

const REPOSITORY_ID: &str = "Qwen/Qwen3-30B-A3B-GGUF";
const REVISION: &str = "e4d4bafdfb96a411a163846265362aceb0b9c63a";
const FILENAME: &str = "Qwen3-30B-A3B-Q8_0.gguf";
const LICENSE_SPDX: &str = "Apache-2.0";
const SHA256: &str = "4ad960d180b16f56024f5b704697e5dd5b0837167c2e515ef0569abfc599743c";
const FILE_BYTES: u64 = 32_483_931_648;

const ARCHITECTURE: &str = "qwen3moe";
const STRING_VALUE_TYPE: &str = "STRING";
const UINT32_VALUE_TYPE: &str = "UINT32";
const EMBEDDING_LENGTH: u64 = 2_048;
const EXPERT_FEED_FORWARD_LENGTH: u64 = 768;
const EXPERT_COUNT: u64 = 128;

const TENSOR_ROLE: &str = "layer_0_routed_expert_gate_projection";
const TENSOR_NAME: &str = "blk.0.ffn_gate_exps.weight";
const TENSOR_QUANTIZATION: &str = "Q8_0";
const TENSOR_DIMENSIONS: [u64; 3] = [2_048, 768, 128];
const TENSOR_ENCODED_SHAPE: [u64; 3] = [128, 768, 2_176];
const TENSOR_ELEMENTS: u64 = 201_326_592;
const TENSOR_BYTES: u64 = 213_909_504;
const TENSOR_DATA_OFFSET: u64 = 901_175_808;

const ENCODED_SLICE_BYTES: u64 = 34_816;
const DECODED_SLICE_BYTES: u64 = 131_072;
const ACTIVATION_BYTES: u64 = 8_192;
const OUTPUT_BYTES: u64 = 64;

const REQUIRED_DISK_BYTES: u64 = 134_761_081_856;
const REQUIRED_HOST_BYTES: u64 = 42_949_672_960;
const SYSTEM_HEADROOM_BYTES: u64 = 34_359_738_368;
const COMPONENT_ENVELOPE_BYTES: u64 = 7_583_301_632;

const OWNED_COMPRESSED_BYTES_MAX: u64 = 268_435_456;
const DECODED_ARRAY_BYTES_MAX: u64 = 1_073_741_824;
const TEMPORARY_PEAK_BYTES_MAX: u64 = 2_147_483_648;
const MLX_ACTIVE_BYTES_MAX: u64 = 3_221_225_472;
const MLX_CACHE_BYTES_MAX: u64 = 1_342_177_280;
const MLX_PEAK_BYTES_MAX: u64 = 4_294_967_296;
const PROCESS_PHYSICAL_FOOTPRINT_BYTES_MAX: u64 = 8_589_934_592;

/// Immutable source and locally observed identity for the admitted artifact.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ModelIdentityDescriptor {
    pub repository_id: String,
    pub revision: String,
    pub filename: String,
    pub license_spdx: String,
    pub expected_size_bytes: u64,
    pub actual_size_bytes: u64,
    pub expected_sha256: String,
    pub actual_sha256: String,
    pub stored_outside_repository: bool,
}

/// Typed GGUF metadata required by the bounded Qwen slice.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ModelMetadataDescriptor {
    pub architecture: String,
    pub architecture_value_type: String,
    pub embedding_length: u64,
    pub embedding_length_value_type: String,
    pub expert_feed_forward_length: u64,
    pub expert_feed_forward_length_value_type: String,
    pub expert_count: u64,
    pub expert_count_value_type: String,
    pub little_endian: bool,
}

/// One observed tensor-inventory entry.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ModelTensorDescriptor {
    pub role: String,
    pub name: String,
    pub occurrences: u64,
    pub quantization: String,
    pub gguf_dimensions_fastest_axis_first: Vec<u64>,
    pub reader_encoded_shape: Vec<u64>,
    pub logical_elements: u64,
    pub encoded_bytes: u64,
    pub absolute_data_offset: u64,
}

/// Host observations and immutable caps for the one admitted operation.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ModelMemoryBudget {
    pub available_disk_bytes: u64,
    pub required_disk_bytes: u64,
    pub host_unified_memory_bytes: u64,
    pub required_host_bytes: u64,
    pub owned_compressed_bytes_cap: u64,
    pub decoded_array_bytes_cap: u64,
    pub temporary_peak_bytes_cap: u64,
    pub mlx_active_bytes_cap: u64,
    pub mlx_cache_bytes_cap: u64,
    pub mlx_peak_bytes_cap: u64,
    pub process_physical_footprint_bytes_cap: u64,
    pub mandatory_system_headroom_bytes: u64,
}

/// Execution boundary requested after identity and inventory admission.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ModelExecutionDepth {
    Layer0Expert0GateRows0To16Matvec,
    MetadataOnly,
    FullLayer,
    Logits,
    Generation,
}

/// Complete caller-observed admission input.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ModelAdmissionDescriptor {
    pub identity: ModelIdentityDescriptor,
    pub metadata: ModelMetadataDescriptor,
    pub tensors: Vec<ModelTensorDescriptor>,
    pub memory_budget: ModelMemoryBudget,
    pub execution_depth: ModelExecutionDepth,
    pub automatic_download_requested: bool,
}

/// Proof that the descriptor matched the one frozen, bounded model operation.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct AdmittedModelSlice {
    _private: (),
}

impl AdmittedModelSlice {
    pub fn repository_id(&self) -> &'static str {
        REPOSITORY_ID
    }

    pub fn revision(&self) -> &'static str {
        REVISION
    }

    pub fn filename(&self) -> &'static str {
        FILENAME
    }

    pub fn sha256(&self) -> &'static str {
        SHA256
    }

    pub fn size_bytes(&self) -> u64 {
        FILE_BYTES
    }

    pub fn architecture(&self) -> &'static str {
        ARCHITECTURE
    }

    pub fn tensor_name(&self) -> &'static str {
        TENSOR_NAME
    }

    pub fn tensor_quantization(&self) -> &'static str {
        TENSOR_QUANTIZATION
    }

    pub fn tensor_dimensions(&self) -> &'static [u64] {
        &TENSOR_DIMENSIONS
    }

    pub fn tensor_data_offset(&self) -> u64 {
        TENSOR_DATA_OFFSET
    }

    pub fn encoded_slice_bytes(&self) -> u64 {
        ENCODED_SLICE_BYTES
    }

    pub fn decoded_slice_bytes(&self) -> u64 {
        DECODED_SLICE_BYTES
    }

    pub fn activation_bytes(&self) -> u64 {
        ACTIVATION_BYTES
    }

    pub fn output_bytes(&self) -> u64 {
        OUTPUT_BYTES
    }

    pub fn execution_depth(&self) -> ModelExecutionDepth {
        ModelExecutionDepth::Layer0Expert0GateRows0To16Matvec
    }
}

/// Admit only the immutable Qwen Q8_0 expert-gate prefix frozen by US4.
pub fn admit_qwen3_q8_0_slice(
    descriptor: &ModelAdmissionDescriptor,
) -> Result<AdmittedModelSlice, ContractError> {
    if descriptor.automatic_download_requested {
        return Err(invalid_model(
            "automatic_download_forbidden",
            "model admission never performs or authorizes automatic acquisition",
        ));
    }

    validate_identity(&descriptor.identity)?;
    validate_metadata(&descriptor.metadata)?;
    validate_tensor_inventory(&descriptor.tensors)?;
    validate_memory_budget(&descriptor.memory_budget)?;

    if descriptor.execution_depth != ModelExecutionDepth::Layer0Expert0GateRows0To16Matvec {
        return Err(invalid_model(
            "unsupported_execution_depth",
            "only the bounded layer-0 expert-0 gate-projection prefix is admitted",
        ));
    }

    Ok(AdmittedModelSlice { _private: () })
}

fn validate_identity(identity: &ModelIdentityDescriptor) -> Result<(), ContractError> {
    if identity.repository_id != REPOSITORY_ID
        || identity.revision != REVISION
        || identity.filename != FILENAME
        || identity.expected_size_bytes != FILE_BYTES
        || identity.expected_sha256 != SHA256
    {
        return Err(invalid_model(
            "model_identity_mismatch",
            "model source identity does not match the immutable admitted artifact",
        ));
    }
    if identity.license_spdx != LICENSE_SPDX {
        return Err(invalid_model(
            "model_license_mismatch",
            "model license does not match the frozen Apache-2.0 admission record",
        ));
    }
    if identity.actual_size_bytes != FILE_BYTES {
        return Err(invalid_model(
            "model_size_mismatch",
            "observed model byte size does not match the immutable artifact",
        ));
    }
    if identity.actual_sha256 != SHA256 {
        return Err(invalid_model(
            "model_checksum_mismatch",
            "observed model checksum does not match the immutable artifact",
        ));
    }
    if !identity.stored_outside_repository {
        return Err(invalid_model(
            "model_path_not_external",
            "model weights must remain outside the source repository",
        ));
    }
    Ok(())
}

fn validate_metadata(metadata: &ModelMetadataDescriptor) -> Result<(), ContractError> {
    if metadata.architecture_value_type != STRING_VALUE_TYPE
        || metadata.embedding_length_value_type != UINT32_VALUE_TYPE
        || metadata.expert_feed_forward_length_value_type != UINT32_VALUE_TYPE
        || metadata.expert_count_value_type != UINT32_VALUE_TYPE
    {
        return Err(invalid_model(
            "model_metadata_type_mismatch",
            "required GGUF metadata types do not match the frozen typed inventory",
        ));
    }
    if metadata.architecture != ARCHITECTURE
        || metadata.embedding_length != EMBEDDING_LENGTH
        || metadata.expert_feed_forward_length != EXPERT_FEED_FORWARD_LENGTH
        || metadata.expert_count != EXPERT_COUNT
    {
        return Err(invalid_model(
            "model_metadata_mismatch",
            "required GGUF metadata values do not match the frozen inventory",
        ));
    }
    if !metadata.little_endian {
        return Err(invalid_model(
            "model_endianness_mismatch",
            "the admitted GGUF artifact must use little-endian encoding",
        ));
    }
    Ok(())
}

fn validate_tensor_inventory(tensors: &[ModelTensorDescriptor]) -> Result<(), ContractError> {
    let matching_role: Vec<&ModelTensorDescriptor> = tensors
        .iter()
        .filter(|tensor| tensor.role == TENSOR_ROLE)
        .collect();

    if matching_role.is_empty()
        || (matching_role.len() == 1
            && (matching_role[0].name != TENSOR_NAME || matching_role[0].occurrences == 0))
    {
        return Err(invalid_model(
            "missing_tensor_role",
            "the exact layer-0 routed-expert gate tensor role is missing",
        ));
    }
    if matching_role.len() != 1 || matching_role[0].occurrences != 1 {
        return Err(invalid_model(
            "duplicate_tensor_role",
            "the admitted tensor role must occur exactly once",
        ));
    }

    let tensor = matching_role[0];
    if tensor.quantization != TENSOR_QUANTIZATION {
        return Err(invalid_model(
            "unsupported_tensor_quantization",
            "the admitted tensor role requires exact Q8_0 encoding",
        ));
    }
    if tensor.gguf_dimensions_fastest_axis_first != TENSOR_DIMENSIONS
        || tensor.reader_encoded_shape != TENSOR_ENCODED_SHAPE
    {
        return Err(invalid_model(
            "tensor_shape_mismatch",
            "tensor dimensions or reader orientation do not match the admitted layout",
        ));
    }
    if tensor.logical_elements != TENSOR_ELEMENTS || tensor.encoded_bytes != TENSOR_BYTES {
        return Err(invalid_model(
            "tensor_size_mismatch",
            "tensor logical or encoded size does not match the admitted inventory",
        ));
    }

    let end = tensor
        .absolute_data_offset
        .checked_add(tensor.encoded_bytes)
        .ok_or_else(|| {
            invalid_model(
                "invalid_tensor_range",
                "tensor byte range overflows the admitted artifact",
            )
        })?;
    if tensor.absolute_data_offset != TENSOR_DATA_OFFSET || end > FILE_BYTES {
        return Err(invalid_model(
            "invalid_tensor_range",
            "tensor byte range does not match the admitted in-file location",
        ));
    }
    Ok(())
}

fn validate_memory_budget(budget: &ModelMemoryBudget) -> Result<(), ContractError> {
    let disk_is_bounded = budget.required_disk_bytes >= REQUIRED_DISK_BYTES
        && budget.available_disk_bytes >= budget.required_disk_bytes;
    let host_is_bounded = budget.required_host_bytes >= REQUIRED_HOST_BYTES
        && budget.host_unified_memory_bytes >= budget.required_host_bytes;
    let headroom_is_bounded = budget.mandatory_system_headroom_bytes >= SYSTEM_HEADROOM_BYTES;
    let declared_host_envelope = COMPONENT_ENVELOPE_BYTES
        .max(budget.process_physical_footprint_bytes_cap)
        .checked_add(budget.mandatory_system_headroom_bytes)
        .is_some_and(|required| budget.required_host_bytes >= required);

    let compressed_is_bounded = within_cap(
        budget.owned_compressed_bytes_cap,
        ENCODED_SLICE_BYTES,
        OWNED_COMPRESSED_BYTES_MAX,
    );
    let decoded_is_bounded = within_cap(
        budget.decoded_array_bytes_cap,
        DECODED_SLICE_BYTES,
        DECODED_ARRAY_BYTES_MAX,
    );
    let temporary_is_bounded = within_cap(
        budget.temporary_peak_bytes_cap,
        DECODED_SLICE_BYTES,
        TEMPORARY_PEAK_BYTES_MAX,
    );
    let mlx_active_is_bounded = within_cap(
        budget.mlx_active_bytes_cap,
        DECODED_SLICE_BYTES,
        MLX_ACTIVE_BYTES_MAX,
    );
    let mlx_cache_is_bounded = within_cap(
        budget.mlx_cache_bytes_cap,
        ENCODED_SLICE_BYTES,
        MLX_CACHE_BYTES_MAX,
    );
    let mlx_peak_is_bounded = within_cap(
        budget.mlx_peak_bytes_cap,
        DECODED_SLICE_BYTES,
        MLX_PEAK_BYTES_MAX,
    );
    let footprint_is_bounded = within_cap(
        budget.process_physical_footprint_bytes_cap,
        DECODED_SLICE_BYTES,
        PROCESS_PHYSICAL_FOOTPRINT_BYTES_MAX,
    );

    if !(disk_is_bounded
        && host_is_bounded
        && headroom_is_bounded
        && declared_host_envelope
        && compressed_is_bounded
        && decoded_is_bounded
        && temporary_is_bounded
        && mlx_active_is_bounded
        && mlx_cache_is_bounded
        && mlx_peak_is_bounded
        && footprint_is_bounded)
    {
        return Err(ContractError::new(
            ErrorCategory::ResourceLimit,
            "model_budget_exceeded",
            "one or more frozen disk, host, allocation, allocator, footprint, or headroom bounds are not satisfied",
        ));
    }

    Ok(())
}

fn within_cap(value: u64, required: u64, maximum: u64) -> bool {
    (required..=maximum).contains(&value)
}

fn invalid_model(code: &'static str, message: &'static str) -> ContractError {
    ContractError::new(ErrorCategory::InvalidModel, code, message)
}
