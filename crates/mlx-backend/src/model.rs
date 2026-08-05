//! Admission contract for the first bounded external Qwen model slice.
//!
//! This module validates caller-observed descriptors and can inspect one
//! explicit external artifact read-only. It never acquires or executes a model.

use backend::{ContractError, ErrorCategory};
use gguf::{Gguf, TensorType, Value};
use sha2::{Digest, Sha256};
use std::fs::File;
use std::io::{Read, Seek, SeekFrom};
use std::path::Path;

pub const QWEN_REPOSITORY_ID: &str = "Qwen/Qwen3-30B-A3B-GGUF";
pub const QWEN_REVISION: &str = "e4d4bafdfb96a411a163846265362aceb0b9c63a";
pub const QWEN_FILENAME: &str = "Qwen3-30B-A3B-Q8_0.gguf";
pub const QWEN_LICENSE_SPDX: &str = "Apache-2.0";
pub const QWEN_SHA256: &str = "4ad960d180b16f56024f5b704697e5dd5b0837167c2e515ef0569abfc599743c";
pub const QWEN_FILE_BYTES: u64 = 32_483_931_648;

const REPOSITORY_ID: &str = QWEN_REPOSITORY_ID;
const REVISION: &str = QWEN_REVISION;
const FILENAME: &str = QWEN_FILENAME;
const LICENSE_SPDX: &str = QWEN_LICENSE_SPDX;
const SHA256: &str = QWEN_SHA256;
const FILE_BYTES: u64 = QWEN_FILE_BYTES;

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
pub const QWEN_TENSOR_DATA_OFFSET: u64 = 901_175_808;
const TENSOR_DATA_OFFSET: u64 = QWEN_TENSOR_DATA_OFFSET;

pub const QWEN_ENCODED_SLICE_BYTES: u64 = 34_816;
const ENCODED_SLICE_BYTES: u64 = QWEN_ENCODED_SLICE_BYTES;
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
const HEADER_READ_START: usize = 8 * 1024 * 1024;
const HEADER_READ_MAX: usize = 64 * 1024 * 1024;
const HASH_BUFFER_BYTES: usize = 8 * 1024 * 1024;
const EXPECTED_GGUF_VERSION: u32 = 3;
const EXPECTED_DATA_OFFSET: u64 = 5_969_408;
const EXPECTED_TENSOR_COUNT: usize = 579;
const EXPECTED_F32_TENSOR_COUNT: usize = 241;
const EXPECTED_Q8_0_TENSOR_COUNT: usize = 338;

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

/// Read-only inspection of the immutable external artifact.
///
/// Only the already-opened file is retained. Its private external path is not
/// exposed to the worker protocol or evidence layer.
pub struct ExternalModelInspection {
    file: File,
    admission_descriptor: ModelAdmissionDescriptor,
    admitted: AdmittedModelSlice,
    gguf_version: u32,
    data_offset: u64,
    tensor_count: usize,
    f32_tensor_count: usize,
    q8_0_tensor_count: usize,
    encoded_slice_sha256: String,
}

impl ExternalModelInspection {
    pub fn try_clone_file(&self) -> Result<File, ContractError> {
        self.file.try_clone().map_err(|_| {
            invalid_model(
                "model_read_failed",
                "the admitted external model handle could not be cloned",
            )
        })
    }

    pub fn admission_descriptor(&self) -> &ModelAdmissionDescriptor {
        &self.admission_descriptor
    }

    pub fn admitted(&self) -> AdmittedModelSlice {
        self.admitted
    }

    pub fn gguf_version(&self) -> u32 {
        self.gguf_version
    }

    pub fn data_offset(&self) -> u64 {
        self.data_offset
    }

    pub fn tensor_count(&self) -> usize {
        self.tensor_count
    }

    pub fn f32_tensor_count(&self) -> usize {
        self.f32_tensor_count
    }

    pub fn q8_0_tensor_count(&self) -> usize {
        self.q8_0_tensor_count
    }

    pub fn encoded_slice_sha256(&self) -> &str {
        &self.encoded_slice_sha256
    }

    /// Recheck the exact open artifact after execution without reopening its
    /// private path. This detects mutation while preserving the same inode.
    pub fn verify_unchanged(&self) -> Result<(), ContractError> {
        let metadata = self.file.metadata().map_err(|_| {
            invalid_model(
                "model_unavailable",
                "the admitted external model metadata could not be rechecked",
            )
        })?;
        if !metadata.is_file() || metadata.len() != FILE_BYTES {
            return Err(invalid_model(
                "model_size_mismatch",
                "the admitted external model size changed during validation",
            ));
        }
        let mut file = self.try_clone_file()?;
        if sha256_reader(&mut file)? != SHA256
            || sha256_exact_range(&self.file, TENSOR_DATA_OFFSET, ENCODED_SLICE_BYTES as usize)?
                != self.encoded_slice_sha256
        {
            return Err(invalid_model(
                "model_checksum_mismatch",
                "the admitted external model changed during validation",
            ));
        }
        Ok(())
    }
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

/// Construct the exact frozen budget with fresh disk and host observations.
pub fn frozen_qwen_model_memory_budget(
    available_disk_bytes: u64,
    host_unified_memory_bytes: u64,
) -> ModelMemoryBudget {
    ModelMemoryBudget {
        available_disk_bytes,
        required_disk_bytes: REQUIRED_DISK_BYTES,
        host_unified_memory_bytes,
        required_host_bytes: REQUIRED_HOST_BYTES,
        owned_compressed_bytes_cap: OWNED_COMPRESSED_BYTES_MAX,
        decoded_array_bytes_cap: DECODED_ARRAY_BYTES_MAX,
        temporary_peak_bytes_cap: TEMPORARY_PEAK_BYTES_MAX,
        mlx_active_bytes_cap: MLX_ACTIVE_BYTES_MAX,
        mlx_cache_bytes_cap: MLX_CACHE_BYTES_MAX,
        mlx_peak_bytes_cap: MLX_PEAK_BYTES_MAX,
        process_physical_footprint_bytes_cap: PROCESS_PHYSICAL_FOOTPRINT_BYTES_MAX,
        mandatory_system_headroom_bytes: SYSTEM_HEADROOM_BYTES,
    }
}

/// Hash, parse, inventory, and admit the exact external Qwen artifact.
///
/// The file is opened read-only, never downloaded, mapped, or executed. The
/// complete SHA-256 and the exact consumed slice SHA-256 are both calculated
/// from the same open file description.
pub fn inspect_external_qwen_model(
    requested_path: &Path,
    repository_root: &Path,
    memory_budget: ModelMemoryBudget,
) -> Result<ExternalModelInspection, ContractError> {
    if !requested_path.is_absolute() {
        return Err(invalid_model(
            "model_path_not_absolute",
            "the external model path must be absolute",
        ));
    }
    let canonical_path = requested_path.canonicalize().map_err(|_| {
        invalid_model(
            "model_unavailable",
            "the external model file is unavailable",
        )
    })?;
    let canonical_root = repository_root.canonicalize().map_err(|_| {
        invalid_model(
            "repository_unavailable",
            "the source repository root is unavailable",
        )
    })?;
    if canonical_path.starts_with(&canonical_root) {
        return Err(invalid_model(
            "model_path_not_external",
            "model weights must remain outside the source repository",
        ));
    }
    if canonical_path.file_name().and_then(|name| name.to_str()) != Some(FILENAME) {
        return Err(invalid_model(
            "model_identity_mismatch",
            "the external model filename does not match the immutable artifact",
        ));
    }

    let mut file = File::open(&canonical_path).map_err(|_| {
        invalid_model(
            "model_unavailable",
            "the external model file could not be opened read-only",
        )
    })?;
    let metadata = file.metadata().map_err(|_| {
        invalid_model(
            "model_unavailable",
            "the external model metadata could not be read",
        )
    })?;
    if !metadata.is_file() || metadata.len() != FILE_BYTES {
        return Err(invalid_model(
            "model_size_mismatch",
            "the external model byte size does not match the immutable artifact",
        ));
    }

    let actual_sha256 = sha256_reader(&mut file)?;
    if actual_sha256 != SHA256 {
        return Err(invalid_model(
            "model_checksum_mismatch",
            "the external model checksum does not match the immutable artifact",
        ));
    }

    let gguf = parse_bounded_header(&file)?;
    let (metadata_descriptor, tensor_descriptor, f32_count, q8_0_count) =
        inspect_gguf_inventory(&gguf, metadata.len())?;
    let encoded_slice_sha256 = sha256_exact_range(
        &file,
        TENSOR_DATA_OFFSET,
        usize::try_from(ENCODED_SLICE_BYTES).map_err(|_| {
            invalid_model(
                "invalid_tensor_range",
                "the encoded model slice size is not representable",
            )
        })?,
    )?;

    let admission_descriptor = ModelAdmissionDescriptor {
        identity: ModelIdentityDescriptor {
            repository_id: REPOSITORY_ID.to_owned(),
            revision: REVISION.to_owned(),
            filename: FILENAME.to_owned(),
            license_spdx: LICENSE_SPDX.to_owned(),
            expected_size_bytes: FILE_BYTES,
            actual_size_bytes: metadata.len(),
            expected_sha256: SHA256.to_owned(),
            actual_sha256,
            stored_outside_repository: true,
        },
        metadata: metadata_descriptor,
        tensors: vec![tensor_descriptor],
        memory_budget,
        execution_depth: ModelExecutionDepth::Layer0Expert0GateRows0To16Matvec,
        automatic_download_requested: false,
    };
    let admitted = admit_qwen3_q8_0_slice(&admission_descriptor)?;

    Ok(ExternalModelInspection {
        file,
        admission_descriptor,
        admitted,
        gguf_version: gguf.version,
        data_offset: gguf.data_offset,
        tensor_count: gguf.tensors.len(),
        f32_tensor_count: f32_count,
        q8_0_tensor_count: q8_0_count,
        encoded_slice_sha256,
    })
}

fn sha256_reader(file: &mut File) -> Result<String, ContractError> {
    file.seek(SeekFrom::Start(0)).map_err(|_| {
        invalid_model(
            "model_read_failed",
            "the external model could not be positioned for hashing",
        )
    })?;
    let mut digest = Sha256::new();
    let mut buffer = vec![0_u8; HASH_BUFFER_BYTES];
    loop {
        let count = file.read(&mut buffer).map_err(|_| {
            invalid_model(
                "model_read_failed",
                "the external model could not be read completely for hashing",
            )
        })?;
        if count == 0 {
            break;
        }
        digest.update(&buffer[..count]);
    }
    Ok(format!("{:x}", digest.finalize()))
}

fn parse_bounded_header(file: &File) -> Result<Gguf, ContractError> {
    let mut read_size = HEADER_READ_START;
    loop {
        let mut reader = file.try_clone().map_err(|_| {
            invalid_model(
                "model_read_failed",
                "the external model handle could not be cloned for header inspection",
            )
        })?;
        reader.seek(SeekFrom::Start(0)).map_err(|_| {
            invalid_model(
                "model_read_failed",
                "the external model could not be positioned for header inspection",
            )
        })?;
        let mut header = Vec::with_capacity(read_size);
        reader
            .take(read_size as u64)
            .read_to_end(&mut header)
            .map_err(|_| {
                invalid_model(
                    "model_read_failed",
                    "the external model header could not be read completely",
                )
            })?;
        match Gguf::parse(&header) {
            Ok(gguf) => return Ok(gguf),
            Err(gguf::Error::Truncated { .. })
                if header.len() == read_size && read_size < HEADER_READ_MAX =>
            {
                read_size = (read_size * 2).min(HEADER_READ_MAX);
            }
            Err(_) => {
                return Err(invalid_model(
                    "model_metadata_mismatch",
                    "the external model GGUF header is invalid or exceeds its byte bound",
                ));
            }
        }
    }
}

fn inspect_gguf_inventory(
    gguf: &Gguf,
    file_bytes: u64,
) -> Result<(ModelMetadataDescriptor, ModelTensorDescriptor, usize, usize), ContractError> {
    if gguf.version != EXPECTED_GGUF_VERSION
        || gguf.data_offset != EXPECTED_DATA_OFFSET
        || gguf.tensors.len() != EXPECTED_TENSOR_COUNT
    {
        return Err(invalid_model(
            "model_metadata_mismatch",
            "the GGUF version, data offset, or tensor count differs from the frozen inventory",
        ));
    }
    let architecture = match gguf.metadata.get("general.architecture") {
        Some(Value::String(value)) if value == ARCHITECTURE => value.clone(),
        Some(Value::String(_)) => {
            return Err(invalid_model(
                "model_metadata_mismatch",
                "the GGUF architecture value differs from the admitted model",
            ));
        }
        _ => {
            return Err(invalid_model(
                "model_metadata_type_mismatch",
                "the GGUF architecture metadata is missing or not STRING",
            ));
        }
    };
    let embedding_length = exact_u32_metadata(gguf, "qwen3moe.embedding_length", EMBEDDING_LENGTH)?;
    let expert_feed_forward_length = exact_u32_metadata(
        gguf,
        "qwen3moe.expert_feed_forward_length",
        EXPERT_FEED_FORWARD_LENGTH,
    )?;
    let expert_count = exact_u32_metadata(gguf, "qwen3moe.expert_count", EXPERT_COUNT)?;

    let f32_count = gguf
        .tensors
        .iter()
        .filter(|tensor| tensor.ty == TensorType::F32)
        .count();
    let q8_0_count = gguf
        .tensors
        .iter()
        .filter(|tensor| tensor.ty == TensorType::Q8_0)
        .count();
    if f32_count != EXPECTED_F32_TENSOR_COUNT || q8_0_count != EXPECTED_Q8_0_TENSOR_COUNT {
        return Err(invalid_model(
            "model_metadata_mismatch",
            "the GGUF tensor-type inventory differs from the immutable artifact",
        ));
    }

    let matching = gguf
        .tensors
        .iter()
        .filter(|tensor| tensor.name == TENSOR_NAME)
        .collect::<Vec<_>>();
    if matching.is_empty() {
        return Err(invalid_model(
            "missing_tensor_role",
            "the required Qwen expert-gate tensor is missing",
        ));
    }
    if matching.len() != 1 {
        return Err(invalid_model(
            "duplicate_tensor_role",
            "the required Qwen expert-gate tensor is not unique",
        ));
    }
    let tensor = matching[0];
    if tensor.ty != TensorType::Q8_0 || tensor.dims != TENSOR_DIMENSIONS {
        return Err(invalid_model(
            "model_tensor_mismatch",
            "the required tensor type or shape differs from the frozen inventory",
        ));
    }
    let logical_elements = tensor
        .dims
        .iter()
        .try_fold(1_u64, |product, dimension| product.checked_mul(*dimension))
        .ok_or_else(|| {
            invalid_model(
                "model_tensor_mismatch",
                "the required tensor element count overflows",
            )
        })?;
    let encoded_row_bytes = tensor.ty.row_bytes(tensor.dims[0]).ok_or_else(|| {
        invalid_model(
            "unsupported_tensor_quantization",
            "the required tensor row layout is not supported",
        )
    })?;
    let encoded_rows = tensor.dims[1].checked_mul(tensor.dims[2]).ok_or_else(|| {
        invalid_model(
            "model_tensor_mismatch",
            "the required tensor row count overflows",
        )
    })?;
    let encoded_bytes = encoded_row_bytes.checked_mul(encoded_rows).ok_or_else(|| {
        invalid_model(
            "model_tensor_mismatch",
            "the required tensor encoded byte count overflows",
        )
    })?;
    let absolute_data_offset = gguf.data_offset.checked_add(tensor.offset).ok_or_else(|| {
        invalid_model(
            "invalid_tensor_range",
            "the required tensor offset overflows the model file",
        )
    })?;
    let end = absolute_data_offset
        .checked_add(encoded_bytes)
        .ok_or_else(|| {
            invalid_model(
                "invalid_tensor_range",
                "the required tensor range overflows the model file",
            )
        })?;
    if logical_elements != TENSOR_ELEMENTS
        || encoded_bytes != TENSOR_BYTES
        || absolute_data_offset != TENSOR_DATA_OFFSET
        || end > file_bytes
    {
        return Err(invalid_model(
            "model_tensor_mismatch",
            "the required tensor type, shape, size, or range differs from the frozen inventory",
        ));
    }
    Ok((
        ModelMetadataDescriptor {
            architecture,
            architecture_value_type: STRING_VALUE_TYPE.to_owned(),
            embedding_length,
            embedding_length_value_type: UINT32_VALUE_TYPE.to_owned(),
            expert_feed_forward_length,
            expert_feed_forward_length_value_type: UINT32_VALUE_TYPE.to_owned(),
            expert_count,
            expert_count_value_type: UINT32_VALUE_TYPE.to_owned(),
            little_endian: true,
        },
        ModelTensorDescriptor {
            role: TENSOR_ROLE.to_owned(),
            name: TENSOR_NAME.to_owned(),
            occurrences: 1,
            quantization: TENSOR_QUANTIZATION.to_owned(),
            gguf_dimensions_fastest_axis_first: tensor.dims.clone(),
            reader_encoded_shape: vec![tensor.dims[2], tensor.dims[1], encoded_row_bytes],
            logical_elements,
            encoded_bytes,
            absolute_data_offset,
        },
        f32_count,
        q8_0_count,
    ))
}

fn exact_u32_metadata(gguf: &Gguf, key: &str, expected: u64) -> Result<u64, ContractError> {
    match gguf.metadata.get(key) {
        Some(Value::U32(value)) if u64::from(*value) == expected => Ok(u64::from(*value)),
        Some(Value::U32(_)) => Err(invalid_model(
            "model_metadata_mismatch",
            "a required GGUF UINT32 metadata value differs from the frozen inventory",
        )),
        _ => Err(invalid_model(
            "model_metadata_type_mismatch",
            "required GGUF metadata is missing or not UINT32",
        )),
    }
}

fn sha256_exact_range(
    file: &File,
    offset: u64,
    byte_count: usize,
) -> Result<String, ContractError> {
    let mut reader = file.try_clone().map_err(|_| {
        invalid_model(
            "model_read_failed",
            "the external model handle could not be cloned for the bounded slice",
        )
    })?;
    reader.seek(SeekFrom::Start(offset)).map_err(|_| {
        invalid_model(
            "model_read_failed",
            "the external model could not be positioned at the bounded slice",
        )
    })?;
    let mut bytes = vec![0_u8; byte_count];
    reader.read_exact(&mut bytes).map_err(|_| {
        invalid_model(
            "model_read_failed",
            "the external model did not provide the complete bounded slice",
        )
    })?;
    Ok(format!("{:x}", Sha256::digest(bytes)))
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
