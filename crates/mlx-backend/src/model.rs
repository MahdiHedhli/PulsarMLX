//! Admission contract for the first bounded external Qwen model slice.
//!
//! This module validates caller-observed descriptors and can inspect one
//! explicit external artifact read-only. It never acquires or executes a model.

use crate::qwen3moe::{
    admission_input_from_gguf, admit_qwen3moe_adapter, construct_qwen3moe_full_graph,
    Qwen3MoeAdapterDescriptor, Qwen3MoeArtifactBinding, Qwen3MoeFullGraphDescriptor,
};
use crate::router::{
    admit_router_tensor, RouterTensorDescriptor, ROUTER_EXPERT_COUNT, ROUTER_HIDDEN_WIDTH,
    ROUTER_TENSOR_BYTES, ROUTER_TENSOR_ELEMENTS, ROUTER_TENSOR_NAME, ROUTER_TOP_K,
};
use backend::{CancellationToken, CheckpointIdentity, ContractError, ErrorCategory};
use gguf::{Gguf, TensorType, Value};
use sha2::{Digest, Sha256};
use std::fs::{self, File, Metadata, OpenOptions};
use std::io::{Read, Seek, SeekFrom};
#[cfg(unix)]
use std::os::unix::fs::{FileExt, MetadataExt, OpenOptionsExt};
#[cfg(windows)]
use std::os::windows::fs::FileExt;
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
pub const QWEN_DECODED_SLICE_BYTES: u64 = 131_072;
const ENCODED_SLICE_BYTES: u64 = QWEN_ENCODED_SLICE_BYTES;
const DECODED_SLICE_BYTES: u64 = QWEN_DECODED_SLICE_BYTES;
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
const ROUTER_EXPERT_USED_KEY: &str = "qwen3moe.expert_used_count";
const ROUTER_WEIGHT_SCALE_KEY: &str = "qwen3moe.expert_weights_scale";
const ROUTER_WEIGHT_NORM_KEY: &str = "qwen3moe.expert_weights_norm";
const FLOAT32_VALUE_TYPE: &str = "FLOAT32";
const BOOL_VALUE_TYPE: &str = "BOOL";
const ROUTER_SEMANTIC_ROLE: &str = "layer_0_router_projection";
const ROUTER_QUANTIZATION: &str = "none_f32";
const ROUTER_BYTE_ORDER: &str = "little";
const ROUTER_ORIENTATION: &str = "expert_major_rows_input_columns";
const ROUTER_BIAS_NAME: &str = "blk.0.ffn_gate_inp.bias";
const ROUTER_CORRECTION_BIAS_NAMES: [&str; 2] = ["blk.0.exp_probs_b", "blk.0.exp_probs_b.bias"];

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

/// Private provenance carried only by canonical model admission.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct CanonicalAdmissionToken {
    _private: (),
}

/// Proof that the descriptor matched the one frozen, bounded model operation.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct AdmittedModelSlice {
    canonical: Option<CanonicalAdmissionToken>,
}

impl AdmittedModelSlice {
    fn canonical() -> Self {
        Self {
            canonical: Some(CanonicalAdmissionToken { _private: () }),
        }
    }

    fn synthetic() -> Self {
        Self { canonical: None }
    }

    pub(crate) fn is_canonical(self) -> bool {
        self.canonical.is_some()
    }
}

/// Stable identity of the regular file behind an admitted checkpoint handle.
///
/// Device and inode values are deliberately private and this type implements
/// no serialization or debug formatting. Callers may use the comparison-only
/// accessor to bind a pre-open path observation to the retained descriptor,
/// but these host-specific values must never enter public evidence.
#[derive(Clone, Copy, PartialEq, Eq)]
pub struct ExternalFileIdentity {
    #[cfg(unix)]
    device: u64,
    #[cfg(unix)]
    inode: u64,
}

/// Read-only inspection of the immutable external artifact.
///
/// The already-opened file and its canonical path are retained privately so
/// pathname identity can be rechecked. Neither path nor host file identifiers
/// are exposed to the worker protocol or evidence layer.
pub struct ExternalModelInspection {
    file: File,
    canonical_path: std::path::PathBuf,
    opened_file_identity: ExternalFileIdentity,
    admission_descriptor: ModelAdmissionDescriptor,
    admitted: AdmittedModelSlice,
    gguf_version: u32,
    data_offset: u64,
    tensor_count: usize,
    f32_tensor_count: usize,
    q8_0_tensor_count: usize,
    encoded_slice_sha256: String,
    qwen3moe_adapter: Qwen3MoeAdapterDescriptor,
    qwen3moe_full_graph: Qwen3MoeFullGraphDescriptor,
}

/// Backend-private binding to one already-admitted external Qwen file.
///
/// This retains a clone of the inspection's open descriptor. The canonical
/// path is retained solely for identity checks; this type has no path-opening
/// capability.
pub(crate) struct ExternalQwen3MoeStorageBinding {
    pub(crate) file: File,
    pub(crate) canonical_path: std::path::PathBuf,
    pub(crate) opened_file_identity: ExternalFileIdentity,
    pub(crate) file_size: u64,
    pub(crate) admitted_slice_sha256: String,
    pub(crate) checkpoint: CheckpointIdentity,
    pub(crate) full_graph: Qwen3MoeFullGraphDescriptor,
}

/// Read-only, path-free observation of the exact layer-0 router tensor.
///
/// The containing [`ExternalModelInspection`] has already established the
/// complete immutable artifact identity. This value adds only bounded GGUF
/// router metadata and the hash of the exact F32 tensor range; it does not
/// decode the tensor or initialize MLX.
#[derive(Debug, Clone, PartialEq)]
pub struct ExternalRouterInspection {
    descriptor: RouterTensorDescriptor,
    relative_data_offset: u64,
    exclusive_end_offset: u64,
    expert_used_count: u64,
    expert_used_count_value_type: String,
    weight_scale_metadata_present: bool,
    weight_scale_value_type: Option<String>,
    weight_scale_metadata_value: Option<f32>,
    expert_weights_norm_metadata_present: bool,
    expert_weights_norm_value_type: Option<String>,
    expert_weights_norm: Option<bool>,
    expert_weights_norm_effective: bool,
    router_bias_occurrence_count: u64,
    correction_bias_occurrence_count: u64,
    unexpected_router_alias_occurrence_count: u64,
}

impl ExternalFileIdentity {
    pub(crate) fn from_metadata(metadata: &Metadata) -> Self {
        file_identity(metadata)
    }

    /// Return the comparison tuple on Unix hosts.
    ///
    /// This is an admission-only value. It is not stable across copied files
    /// or hosts and must not be serialized into public evidence.
    pub fn unix_device_and_inode(&self) -> Option<(u64, u64)> {
        #[cfg(unix)]
        {
            Some((self.device, self.inode))
        }
        #[cfg(not(unix))]
        {
            None
        }
    }
}

impl ExternalModelInspection {
    /// Identity of the exact regular file held open for this inspection.
    ///
    /// The returned value is comparison-only and intentionally carries no
    /// path or public-evidence representation.
    pub fn opened_file_identity(&self) -> ExternalFileIdentity {
        self.opened_file_identity
    }

    pub fn try_clone_file(&self) -> Result<File, ContractError> {
        self.file.try_clone().map_err(|_| {
            invalid_model(
                "model_read_failed",
                "the admitted external model handle could not be cloned",
            )
        })
    }

    /// Bind one clone of this inspection to a backend storage transaction.
    ///
    /// The binding copies the already-admitted full-graph descriptor and
    /// rechecks the retained path/inode/size plus the admitted slice hash
    /// before returning. No path is opened here outside the retained handle.
    pub(crate) fn bind_qwen3moe_storage(
        &self,
        cancellation: &CancellationToken,
    ) -> Result<ExternalQwen3MoeStorageBinding, ContractError> {
        cancellation.check()?;
        if !self.admitted.is_canonical() {
            return Err(invalid_model(
                "canonical_admission_required",
                "synthetic inspections cannot bind to production external storage",
            ));
        }
        self.verify_storage_identity(cancellation)?;
        cancellation.check()?;
        self.qwen3moe_full_graph.verify_admission_proof()?;
        cancellation.check()?;
        let metadata = self.file.metadata().map_err(|_| {
            invalid_model(
                "model_unavailable",
                "the admitted external model metadata could not be read",
            )
        })?;
        let artifact_size = self.qwen3moe_full_graph.artifact.size_bytes;
        if metadata.len() != artifact_size
            || metadata.len() != self.admission_descriptor.identity.expected_size_bytes
            || self.admission_descriptor.identity.actual_size_bytes != artifact_size
            || self.encoded_slice_sha256.is_empty()
        {
            return Err(invalid_model(
                "model_size_mismatch",
                "the admitted external model size does not match its immutable artifact",
            ));
        }
        cancellation.check()?;
        let slice_hash = sha256_exact_range(
            &self.file,
            TENSOR_DATA_OFFSET,
            usize::try_from(ENCODED_SLICE_BYTES).map_err(|_| {
                invalid_model(
                    "invalid_tensor_range",
                    "the admitted encoded slice size is not representable",
                )
            })?,
            cancellation,
        )?;
        if slice_hash != self.encoded_slice_sha256 {
            return Err(invalid_model(
                "model_checksum_mismatch",
                "the admitted external model slice changed before storage binding",
            ));
        }
        cancellation.check()?;
        let checkpoint = CheckpointIdentity::try_new(
            self.qwen3moe_full_graph.artifact.sha256.clone(),
            self.qwen3moe_full_graph.artifact.revision.clone(),
        )?;
        cancellation.check()?;
        let file = self.try_clone_file()?;
        cancellation.check()?;
        Ok(ExternalQwen3MoeStorageBinding {
            file,
            canonical_path: self.canonical_path.clone(),
            opened_file_identity: self.opened_file_identity,
            file_size: artifact_size,
            admitted_slice_sha256: self.encoded_slice_sha256.clone(),
            checkpoint,
            full_graph: self.qwen3moe_full_graph.clone(),
        })
    }

    fn verify_storage_identity(
        &self,
        cancellation: &CancellationToken,
    ) -> Result<(), ContractError> {
        cancellation.check()?;
        verify_path_matches_open_file(&self.canonical_path, &self.file, self.opened_file_identity)?;
        cancellation.check()?;
        let metadata = self.file.metadata().map_err(|_| {
            invalid_model(
                "model_unavailable",
                "the admitted external model metadata could not be read",
            )
        })?;
        if !metadata.is_file() {
            return Err(invalid_model(
                "model_path_identity_changed",
                "the admitted external model descriptor is no longer a regular file",
            ));
        }
        if metadata.len() != self.qwen3moe_full_graph.artifact.size_bytes
            || metadata.len() != self.admission_descriptor.identity.expected_size_bytes
        {
            return Err(invalid_model(
                "model_size_mismatch",
                "the admitted external model size changed from its immutable artifact",
            ));
        }
        cancellation.check()?;
        Ok(())
    }

    /// Construct an inspection around ephemeral bytes for model-free tests.
    ///
    /// This helper never hashes, downloads, or executes a model and is not a
    /// production admission path. It exists so integration tests can exercise
    /// the same retained-file identity and storage transaction boundaries.
    #[doc(hidden)]
    pub(crate) fn new_synthetic_for_test(
        file: File,
        path: impl Into<std::path::PathBuf>,
        qwen3moe_full_graph: Qwen3MoeFullGraphDescriptor,
    ) -> Result<Self, ContractError> {
        let canonical_path = path.into().canonicalize().map_err(|_| {
            invalid_model(
                "model_unavailable",
                "the synthetic external model file is unavailable",
            )
        })?;
        let metadata = file.metadata().map_err(|_| {
            invalid_model(
                "model_unavailable",
                "the synthetic external model metadata could not be read",
            )
        })?;
        let opened_file_identity = file_identity(&metadata);
        verify_path_matches_open_file(&canonical_path, &file, opened_file_identity)?;
        let artifact = &qwen3moe_full_graph.artifact;
        let admission_descriptor = ModelAdmissionDescriptor {
            identity: ModelIdentityDescriptor {
                repository_id: artifact.repository_id.clone(),
                revision: artifact.revision.clone(),
                filename: artifact.filename.clone(),
                license_spdx: QWEN_LICENSE_SPDX.to_owned(),
                expected_size_bytes: metadata.len(),
                actual_size_bytes: metadata.len(),
                expected_sha256: artifact.sha256.clone(),
                actual_sha256: artifact.sha256.clone(),
                stored_outside_repository: true,
            },
            metadata: ModelMetadataDescriptor {
                architecture: qwen3moe_full_graph.metadata.architecture.clone(),
                architecture_value_type: STRING_VALUE_TYPE.to_owned(),
                embedding_length: qwen3moe_full_graph.metadata.hidden_width,
                embedding_length_value_type: UINT32_VALUE_TYPE.to_owned(),
                expert_feed_forward_length: qwen3moe_full_graph.metadata.expert_ffn_width,
                expert_feed_forward_length_value_type: UINT32_VALUE_TYPE.to_owned(),
                expert_count: qwen3moe_full_graph.metadata.expert_count,
                expert_count_value_type: UINT32_VALUE_TYPE.to_owned(),
                little_endian: true,
            },
            tensors: Vec::new(),
            memory_budget: frozen_qwen_model_memory_budget(u64::MAX, u64::MAX),
            execution_depth: ModelExecutionDepth::Layer0Expert0GateRows0To16Matvec,
            automatic_download_requested: false,
        };
        let qwen3moe_adapter = Qwen3MoeAdapterDescriptor {
            contract_id: crate::qwen3moe::QWEN3MOE_ADAPTER_CONTRACT_ID.to_owned(),
            artifact: artifact.clone(),
            metadata: qwen3moe_full_graph.metadata.clone(),
            tensors: qwen3moe_full_graph.tensors.clone(),
        };
        let encoded_slice_sha256 = match qwen3moe_full_graph.tensors.iter().find(|tensor| {
            tensor.role == crate::qwen3moe::Qwen3MoeTensorRole::ExpertGateWeight
                && tensor.layer_index == Some(0)
        }) {
            Some(tensor)
                if tensor
                    .absolute_data_offset
                    .checked_add(tensor.encoded_bytes)
                    .is_some_and(|end| end <= metadata.len()) =>
            {
                sha256_exact_range(
                    &file,
                    tensor.absolute_data_offset,
                    usize::try_from(tensor.encoded_bytes).map_err(|_| {
                        invalid_model(
                            "invalid_tensor_range",
                            "the synthetic encoded slice size is not representable",
                        )
                    })?,
                    &CancellationToken::new(),
                )?
            }
            _ => String::new(),
        };
        Ok(Self {
            file,
            canonical_path,
            opened_file_identity,
            admission_descriptor,
            admitted: AdmittedModelSlice::synthetic(),
            gguf_version: 3,
            data_offset: crate::qwen3moe::QWEN3MOE_DATA_OFFSET,
            tensor_count: qwen3moe_full_graph.tensors.len(),
            f32_tensor_count: 0,
            q8_0_tensor_count: qwen3moe_full_graph.tensors.len(),
            encoded_slice_sha256,
            qwen3moe_adapter,
            qwen3moe_full_graph,
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

    /// The typed, complete Qwen3MoE metadata/tensor-role map admitted from
    /// the same already-verified GGUF header. No tensor payload is decoded.
    pub fn qwen3moe_adapter(&self) -> &Qwen3MoeAdapterDescriptor {
        &self.qwen3moe_adapter
    }

    /// The complete metadata-only Qwen3MoE transformer graph admitted from
    /// the same verified GGUF header. No tensor payload is decoded.
    pub fn qwen3moe_full_graph(&self) -> &Qwen3MoeFullGraphDescriptor {
        &self.qwen3moe_full_graph
    }

    /// Inspect and admit the complete F32 layer-0 router range from the same
    /// already-opened immutable file description.
    pub fn inspect_router_tensor(&self) -> Result<ExternalRouterInspection, ContractError> {
        let gguf = parse_bounded_header(&self.file)?;
        inspect_router_inventory(&gguf, &self.file)
    }

    /// Recheck the exact open artifact after execution without reopening its
    /// private path. This detects mutation while preserving the same inode.
    pub fn verify_unchanged(&self) -> Result<(), ContractError> {
        verify_path_matches_open_file(&self.canonical_path, &self.file, self.opened_file_identity)?;
        let metadata = self.file.metadata().map_err(|_| {
            invalid_model(
                "model_unavailable",
                "the admitted external model metadata could not be rechecked",
            )
        })?;
        if !metadata.is_file()
            || metadata.len() != self.admission_descriptor.identity.expected_size_bytes
        {
            return Err(invalid_model(
                "model_size_mismatch",
                "the admitted external model size changed during validation",
            ));
        }
        let tensor = self
            .qwen3moe_full_graph
            .tensors
            .iter()
            .find(|tensor| {
                tensor.role == crate::qwen3moe::Qwen3MoeTensorRole::ExpertGateWeight
                    && tensor.layer_index == Some(0)
            })
            .ok_or_else(|| {
                invalid_model(
                    "missing_tensor_role",
                    "the admitted Qwen expert-gate slice is missing",
                )
            })?;
        let slice_bytes = if self.admitted.is_canonical() {
            ENCODED_SLICE_BYTES
        } else {
            tensor.encoded_bytes
        };
        let slice_hash = sha256_exact_range(
            &self.file,
            tensor.absolute_data_offset,
            usize::try_from(slice_bytes).map_err(|_| {
                invalid_model(
                    "invalid_tensor_range",
                    "the admitted encoded slice size is not representable",
                )
            })?,
            &CancellationToken::new(),
        )?;
        if slice_hash != self.encoded_slice_sha256 {
            return Err(invalid_model(
                "model_checksum_mismatch",
                "the admitted external model changed during validation",
            ));
        }
        if self.admitted.is_canonical() {
            let mut file = self.try_clone_file()?;
            if sha256_reader(&mut file)? != SHA256 {
                return Err(invalid_model(
                    "model_checksum_mismatch",
                    "the admitted external model changed during validation",
                ));
            }
        }
        verify_path_matches_open_file(&self.canonical_path, &self.file, self.opened_file_identity)?;
        Ok(())
    }
}

impl ExternalRouterInspection {
    pub fn descriptor(&self) -> &RouterTensorDescriptor {
        &self.descriptor
    }

    pub fn relative_data_offset(&self) -> u64 {
        self.relative_data_offset
    }

    pub fn exclusive_end_offset(&self) -> u64 {
        self.exclusive_end_offset
    }

    pub fn expert_used_count(&self) -> u64 {
        self.expert_used_count
    }

    pub fn expert_used_count_value_type(&self) -> &str {
        &self.expert_used_count_value_type
    }

    pub fn weight_scale_metadata_present(&self) -> bool {
        self.weight_scale_metadata_present
    }

    pub fn weight_scale_value_type(&self) -> Option<&str> {
        self.weight_scale_value_type.as_deref()
    }

    pub fn weight_scale_metadata_value(&self) -> Option<f32> {
        self.weight_scale_metadata_value
    }

    pub fn expert_weights_norm_metadata_present(&self) -> bool {
        self.expert_weights_norm_metadata_present
    }

    pub fn expert_weights_norm_value_type(&self) -> Option<&str> {
        self.expert_weights_norm_value_type.as_deref()
    }

    pub fn expert_weights_norm(&self) -> Option<bool> {
        self.expert_weights_norm
    }

    pub fn expert_weights_norm_effective(&self) -> bool {
        self.expert_weights_norm_effective
    }

    pub fn router_bias_occurrence_count(&self) -> u64 {
        self.router_bias_occurrence_count
    }

    pub fn correction_bias_occurrence_count(&self) -> u64 {
        self.correction_bias_occurrence_count
    }

    pub fn unexpected_router_alias_occurrence_count(&self) -> u64 {
        self.unexpected_router_alias_occurrence_count
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

    Ok(AdmittedModelSlice::canonical())
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

fn file_identity(metadata: &Metadata) -> ExternalFileIdentity {
    #[cfg(unix)]
    {
        ExternalFileIdentity {
            device: metadata.dev(),
            inode: metadata.ino(),
        }
    }
    #[cfg(not(unix))]
    {
        let _ = metadata;
        ExternalFileIdentity {}
    }
}

fn verify_path_matches_open_file(
    canonical_path: &Path,
    file: &File,
    expected_identity: ExternalFileIdentity,
) -> Result<(), ContractError> {
    let cancellation = CancellationToken::new();
    verify_path_matches_open_file_cancellable(
        canonical_path,
        file,
        expected_identity,
        &cancellation,
    )
}

fn verify_path_matches_open_file_cancellable(
    canonical_path: &Path,
    file: &File,
    expected_identity: ExternalFileIdentity,
    cancellation: &CancellationToken,
) -> Result<(), ContractError> {
    cancellation.check()?;
    let path_metadata = fs::symlink_metadata(canonical_path).map_err(|_| {
        invalid_model(
            "model_path_identity_changed",
            "the admitted model pathname is no longer available",
        )
    })?;
    cancellation.check()?;
    let open_metadata = file.metadata().map_err(|_| {
        invalid_model(
            "model_unavailable",
            "the admitted external model descriptor metadata could not be read",
        )
    })?;
    cancellation.check()?;
    if path_metadata.file_type().is_symlink()
        || !path_metadata.is_file()
        || !open_metadata.is_file()
        || file_identity(&path_metadata) != expected_identity
        || file_identity(&open_metadata) != expected_identity
    {
        return Err(invalid_model(
            "model_path_identity_changed",
            "the admitted model pathname no longer resolves to the retained regular file",
        ));
    }
    cancellation.check()?;
    Ok(())
}

#[cfg(test)]
fn open_read_only_no_follow(
    canonical_path: &Path,
) -> Result<(File, Metadata, ExternalFileIdentity), ContractError> {
    let cancellation = CancellationToken::new();
    open_read_only_no_follow_cancellable(canonical_path, &cancellation)
}

fn open_read_only_no_follow_cancellable(
    canonical_path: &Path,
    cancellation: &CancellationToken,
) -> Result<(File, Metadata, ExternalFileIdentity), ContractError> {
    cancellation.check()?;
    let path_metadata = fs::symlink_metadata(canonical_path).map_err(|_| {
        invalid_model(
            "model_unavailable",
            "the external model file is unavailable",
        )
    })?;
    cancellation.check()?;
    if path_metadata.file_type().is_symlink() || !path_metadata.is_file() {
        return Err(invalid_model(
            "model_unavailable",
            "the external model path must name a regular non-symbolic-link target",
        ));
    }
    let path_identity = file_identity(&path_metadata);
    let mut options = OpenOptions::new();
    options.read(true);
    #[cfg(unix)]
    options.custom_flags(libc::O_NOFOLLOW);
    cancellation.check()?;
    let file = options.open(canonical_path).map_err(|_| {
        invalid_model(
            "model_unavailable",
            "the external model file could not be opened read-only without following a link",
        )
    })?;
    cancellation.check()?;
    let metadata = file.metadata().map_err(|_| {
        invalid_model(
            "model_unavailable",
            "the external model metadata could not be read",
        )
    })?;
    cancellation.check()?;
    let opened_file_identity = file_identity(&metadata);
    if !metadata.is_file() || opened_file_identity != path_identity {
        return Err(invalid_model(
            "model_path_identity_changed",
            "the external model pathname changed while its descriptor was opened",
        ));
    }
    verify_path_matches_open_file_cancellable(
        canonical_path,
        &file,
        opened_file_identity,
        cancellation,
    )?;
    Ok((file, metadata, opened_file_identity))
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
    let cancellation = CancellationToken::new();
    inspect_external_qwen_model_with_cancellation(
        requested_path,
        repository_root,
        memory_budget,
        &cancellation,
    )
}

/// Hash, parse, inventory, and admit the exact external Qwen artifact with a
/// caller-owned cancellation token covering every admission boundary.
pub fn inspect_external_qwen_model_with_cancellation(
    requested_path: &Path,
    repository_root: &Path,
    memory_budget: ModelMemoryBudget,
    cancellation: &CancellationToken,
) -> Result<ExternalModelInspection, ContractError> {
    cancellation.check()?;
    if !requested_path.is_absolute() {
        return Err(invalid_model(
            "model_path_not_absolute",
            "the external model path must be absolute",
        ));
    }
    cancellation.check()?;
    let canonical_path = requested_path.canonicalize().map_err(|_| {
        invalid_model(
            "model_unavailable",
            "the external model file is unavailable",
        )
    })?;
    cancellation.check()?;
    let canonical_root = repository_root.canonicalize().map_err(|_| {
        invalid_model(
            "repository_unavailable",
            "the source repository root is unavailable",
        )
    })?;
    cancellation.check()?;
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

    cancellation.check()?;
    let (mut file, metadata, opened_file_identity) =
        open_read_only_no_follow_cancellable(&canonical_path, cancellation)?;
    cancellation.check()?;
    if !metadata.is_file() || metadata.len() != FILE_BYTES {
        return Err(invalid_model(
            "model_size_mismatch",
            "the external model byte size does not match the immutable artifact",
        ));
    }

    cancellation.check()?;
    let actual_sha256 = sha256_reader_cancellable(&mut file, cancellation)?;
    cancellation.check()?;
    if actual_sha256 != SHA256 {
        return Err(invalid_model(
            "model_checksum_mismatch",
            "the external model checksum does not match the immutable artifact",
        ));
    }

    cancellation.check()?;
    let gguf = parse_bounded_header_cancellable(&file, cancellation)?;
    cancellation.check()?;
    let qwen3moe_adapter = admit_qwen3moe_adapter(admission_input_from_gguf(
        &gguf,
        Qwen3MoeArtifactBinding {
            repository_id: REPOSITORY_ID.to_owned(),
            revision: REVISION.to_owned(),
            filename: FILENAME.to_owned(),
            size_bytes: FILE_BYTES,
            sha256: SHA256.to_owned(),
        },
    )?)?;
    cancellation.check()?;
    let qwen3moe_full_graph = construct_qwen3moe_full_graph(qwen3moe_adapter.clone())?;
    cancellation.check()?;
    let (metadata_descriptor, tensor_descriptor, f32_count, q8_0_count) =
        inspect_gguf_inventory(&gguf, metadata.len())?;
    cancellation.check()?;
    let encoded_slice_sha256 = sha256_qwen_encoded_slice(&file, cancellation)?;
    cancellation.check()?;

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
    cancellation.check()?;
    let admitted = admit_qwen3_q8_0_slice(&admission_descriptor)?;
    cancellation.check()?;
    verify_path_matches_open_file_cancellable(
        &canonical_path,
        &file,
        opened_file_identity,
        cancellation,
    )?;
    cancellation.check()?;

    Ok(ExternalModelInspection {
        file,
        canonical_path,
        opened_file_identity,
        admission_descriptor,
        admitted,
        gguf_version: gguf.version,
        data_offset: gguf.data_offset,
        tensor_count: gguf.tensors.len(),
        f32_tensor_count: f32_count,
        q8_0_tensor_count: q8_0_count,
        encoded_slice_sha256,
        qwen3moe_adapter,
        qwen3moe_full_graph,
    })
}

fn sha256_reader(file: &mut File) -> Result<String, ContractError> {
    let cancellation = CancellationToken::new();
    sha256_reader_cancellable(file, &cancellation)
}

fn sha256_reader_cancellable(
    file: &mut File,
    cancellation: &CancellationToken,
) -> Result<String, ContractError> {
    cancellation.check()?;
    file.seek(SeekFrom::Start(0)).map_err(|_| {
        invalid_model(
            "model_read_failed",
            "the external model could not be positioned for hashing",
        )
    })?;
    cancellation.check()?;
    sha256_stream_with_buffer(file, cancellation, HASH_BUFFER_BYTES)
}

fn sha256_stream_with_buffer(
    reader: &mut impl Read,
    cancellation: &CancellationToken,
    buffer_size: usize,
) -> Result<String, ContractError> {
    if buffer_size == 0 {
        return Err(invalid_model(
            "model_read_failed",
            "the external model hash buffer size must be nonzero",
        ));
    }
    let mut digest = Sha256::new();
    let mut buffer = vec![0_u8; buffer_size];
    loop {
        cancellation.check()?;
        let count = reader.read(&mut buffer).map_err(|_| {
            invalid_model(
                "model_read_failed",
                "the external model could not be read completely for hashing",
            )
        })?;
        cancellation.check()?;
        if count == 0 {
            break;
        }
        digest.update(&buffer[..count]);
        cancellation.check()?;
    }
    Ok(format!("{:x}", digest.finalize()))
}

fn parse_bounded_header(file: &File) -> Result<Gguf, ContractError> {
    let cancellation = CancellationToken::new();
    parse_bounded_header_cancellable(file, &cancellation)
}

fn parse_bounded_header_cancellable(
    file: &File,
    cancellation: &CancellationToken,
) -> Result<Gguf, ContractError> {
    let mut read_size = HEADER_READ_START;
    loop {
        cancellation.check()?;
        let mut reader = file.try_clone().map_err(|_| {
            invalid_model(
                "model_read_failed",
                "the external model handle could not be cloned for header inspection",
            )
        })?;
        cancellation.check()?;
        reader.seek(SeekFrom::Start(0)).map_err(|_| {
            invalid_model(
                "model_read_failed",
                "the external model could not be positioned for header inspection",
            )
        })?;
        cancellation.check()?;
        let header = read_header_prefix_with_reader(
            &mut reader,
            read_size,
            HASH_BUFFER_BYTES,
            cancellation,
        )?;
        cancellation.check()?;
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

fn read_header_prefix_with_reader(
    reader: &mut impl Read,
    read_size: usize,
    chunk_size: usize,
    cancellation: &CancellationToken,
) -> Result<Vec<u8>, ContractError> {
    if chunk_size == 0 {
        return Err(invalid_model(
            "model_read_failed",
            "the external model header read chunk size must be nonzero",
        ));
    }
    let mut header = Vec::with_capacity(read_size);
    let mut chunk = vec![0_u8; chunk_size.min(read_size.max(1))];
    while header.len() < read_size {
        cancellation.check()?;
        let remaining = read_size - header.len();
        let limit = remaining.min(chunk.len());
        let count = reader.read(&mut chunk[..limit]).map_err(|_| {
            invalid_model(
                "model_read_failed",
                "the external model header could not be read completely",
            )
        })?;
        cancellation.check()?;
        if count == 0 {
            break;
        }
        header.extend_from_slice(&chunk[..count]);
        cancellation.check()?;
    }
    Ok(header)
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

/// Inspect the exact Feature 002 router inventory from an already admitted,
/// read-only model handle.
///
/// This function performs no router math and does not initialize MLX. It
/// validates typed routing metadata, proves that prohibited bias/correction
/// tensors are absent, hashes the complete router range, and passes the
/// resulting descriptor through the model-neutral router admission contract.
fn inspect_router_inventory(
    gguf: &Gguf,
    file: &File,
) -> Result<ExternalRouterInspection, ContractError> {
    let file_metadata = file.metadata().map_err(|_| {
        invalid_model(
            "model_unavailable",
            "the admitted external model metadata could not be read for router inspection",
        )
    })?;
    if !file_metadata.is_file() {
        return Err(invalid_model(
            "model_unavailable",
            "router inspection requires a regular read-only model file",
        ));
    }
    let file_bytes = file_metadata.len();

    let expert_used_count = exact_u32_metadata(
        gguf,
        ROUTER_EXPERT_USED_KEY,
        u64::try_from(ROUTER_TOP_K).expect("router top-k fits u64"),
    )?;
    let (
        weight_scale_metadata_present,
        weight_scale_value_type,
        weight_scale_metadata_value,
        effective_weight_scale,
    ) = match gguf.metadata.get(ROUTER_WEIGHT_SCALE_KEY) {
        None => (false, None, None, 1.0_f32),
        Some(Value::F32(value)) if value.to_bits() == 1.0_f32.to_bits() => (
            true,
            Some(FLOAT32_VALUE_TYPE.to_owned()),
            Some(*value),
            *value,
        ),
        Some(Value::F32(_)) => {
            return Err(invalid_model(
                "model_metadata_mismatch",
                "the router expert-weight scale differs from the frozen value 1.0",
            ));
        }
        Some(_) => {
            return Err(invalid_model(
                "model_metadata_type_mismatch",
                "the router expert-weight scale is not GGUF FLOAT32",
            ));
        }
    };
    let (
        expert_weights_norm_metadata_present,
        expert_weights_norm_value_type,
        expert_weights_norm,
        expert_weights_norm_effective,
    ) = match gguf.metadata.get(ROUTER_WEIGHT_NORM_KEY) {
        None => (false, None, None, true),
        Some(Value::Bool(true)) => (true, Some(BOOL_VALUE_TYPE.to_owned()), Some(true), true),
        Some(Value::Bool(false)) => {
            return Err(invalid_model(
                "model_metadata_mismatch",
                "the router expert-weight normalization metadata disables the frozen behavior",
            ));
        }
        Some(_) => {
            return Err(invalid_model(
                "model_metadata_type_mismatch",
                "the router expert-weight normalization metadata is not GGUF BOOL",
            ));
        }
    };

    let router_bias_occurrence_count = gguf
        .tensors
        .iter()
        .filter(|tensor| tensor.name == ROUTER_BIAS_NAME)
        .count() as u64;
    let correction_bias_occurrence_count = gguf
        .tensors
        .iter()
        .filter(|tensor| {
            ROUTER_CORRECTION_BIAS_NAMES
                .iter()
                .any(|name| tensor.name == *name)
        })
        .count() as u64;
    let unexpected_router_alias_occurrence_count = gguf
        .tensors
        .iter()
        .filter(|tensor| is_unexpected_layer_0_router_alias(&tensor.name))
        .count() as u64;
    if router_bias_occurrence_count != 0
        || correction_bias_occurrence_count != 0
        || unexpected_router_alias_occurrence_count != 0
    {
        return Err(invalid_model(
            "model_tensor_mismatch",
            "the frozen Qwen router contract does not admit a router bias, correction bias, or unreviewed layer-0 router alias",
        ));
    }

    let matching = gguf
        .tensors
        .iter()
        .filter(|tensor| tensor.name == ROUTER_TENSOR_NAME)
        .collect::<Vec<_>>();
    match matching.len() {
        0 => {
            return Err(invalid_model(
                "missing_tensor_role",
                "the exact layer-0 router tensor is missing",
            ));
        }
        1 => {}
        _ => {
            return Err(invalid_model(
                "duplicate_tensor_role",
                "the exact layer-0 router tensor is not unique",
            ));
        }
    }
    let tensor = matching[0];
    if tensor.ty != TensorType::F32 {
        return Err(invalid_model(
            "unsupported_tensor_quantization",
            "the Feature 002 router contract requires exact unquantized F32 storage",
        ));
    }
    let expected_dimensions = [ROUTER_HIDDEN_WIDTH as u64, ROUTER_EXPERT_COUNT as u64];
    if tensor.dims != expected_dimensions {
        return Err(invalid_model(
            "model_tensor_mismatch",
            "the layer-0 router GGUF dimensions differ from [2048,128]",
        ));
    }
    let logical_elements = tensor
        .dims
        .iter()
        .try_fold(1_u64, |product, dimension| product.checked_mul(*dimension))
        .ok_or_else(|| {
            invalid_model(
                "model_tensor_mismatch",
                "the layer-0 router element count overflows",
            )
        })?;
    let encoded_length = tensor.byte_size().ok_or_else(|| {
        invalid_model(
            "unsupported_tensor_quantization",
            "the layer-0 router tensor byte layout is unsupported",
        )
    })?;
    if logical_elements != ROUTER_TENSOR_ELEMENTS || encoded_length != ROUTER_TENSOR_BYTES {
        return Err(invalid_model(
            "model_tensor_mismatch",
            "the layer-0 router element or encoded byte count differs from the frozen contract",
        ));
    }
    let absolute_data_offset = gguf.data_offset.checked_add(tensor.offset).ok_or_else(|| {
        invalid_model(
            "invalid_tensor_range",
            "the layer-0 router absolute offset overflows",
        )
    })?;
    let exclusive_end_offset = absolute_data_offset
        .checked_add(encoded_length)
        .ok_or_else(|| {
            invalid_model(
                "invalid_tensor_range",
                "the layer-0 router range end overflows",
            )
        })?;
    if absolute_data_offset >= file_bytes || exclusive_end_offset > file_bytes {
        return Err(invalid_model(
            "invalid_tensor_range",
            "the complete layer-0 router range is outside the immutable artifact",
        ));
    }
    let encoded_sha256 = sha256_exact_range(
        file,
        absolute_data_offset,
        usize::try_from(encoded_length).map_err(|_| {
            invalid_model(
                "invalid_tensor_range",
                "the layer-0 router byte count is not representable",
            )
        })?,
        &CancellationToken::new(),
    )?;
    let descriptor = RouterTensorDescriptor {
        name: ROUTER_TENSOR_NAME.to_owned(),
        semantic_role: ROUTER_SEMANTIC_ROLE.to_owned(),
        occurrence_count: 1,
        gguf_dimensions_fastest_axis_first: tensor.dims.clone(),
        reader_shape: vec![ROUTER_EXPERT_COUNT as u64, ROUTER_HIDDEN_WIDTH as u64],
        execution_shape: vec![ROUTER_EXPERT_COUNT as u64, ROUTER_HIDDEN_WIDTH as u64],
        gguf_type: "F32".to_owned(),
        quantization: ROUTER_QUANTIZATION.to_owned(),
        logical_elements,
        absolute_data_offset,
        encoded_length,
        encoded_sha256,
        byte_order: ROUTER_BYTE_ORDER.to_owned(),
        orientation: ROUTER_ORIENTATION.to_owned(),
        expert_count: ROUTER_EXPERT_COUNT as u64,
        top_k: expert_used_count,
        weight_scale: effective_weight_scale,
        bias_present: false,
        correction_bias_present: false,
    };
    let admitted = admit_router_tensor(&descriptor, file_bytes)?;

    Ok(ExternalRouterInspection {
        descriptor,
        relative_data_offset: tensor.offset,
        exclusive_end_offset: admitted.exclusive_end_offset(),
        expert_used_count,
        expert_used_count_value_type: UINT32_VALUE_TYPE.to_owned(),
        weight_scale_metadata_present,
        weight_scale_value_type,
        weight_scale_metadata_value,
        expert_weights_norm_metadata_present,
        expert_weights_norm_value_type,
        expert_weights_norm,
        expert_weights_norm_effective,
        router_bias_occurrence_count,
        correction_bias_occurrence_count,
        unexpected_router_alias_occurrence_count,
    })
}

fn is_unexpected_layer_0_router_alias(name: &str) -> bool {
    if name == ROUTER_TENSOR_NAME
        || name == ROUTER_BIAS_NAME
        || ROUTER_CORRECTION_BIAS_NAMES.contains(&name)
    {
        return false;
    }
    let Some(layer_name) = name.strip_prefix("blk.0.") else {
        return false;
    };
    let normalized = layer_name.to_ascii_lowercase();
    normalized.starts_with("ffn_gate_inp")
        || normalized.starts_with("exp_probs")
        || normalized.contains("router")
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

fn sha256_qwen_encoded_slice(
    file: &File,
    cancellation: &CancellationToken,
) -> Result<String, ContractError> {
    sha256_qwen_encoded_slice_with_reader(cancellation, |destination, read_offset| {
        positional_read(file, destination, read_offset)
    })
}

fn sha256_qwen_encoded_slice_with_reader(
    cancellation: &CancellationToken,
    reader: impl FnMut(&mut [u8], u64) -> std::io::Result<usize>,
) -> Result<String, ContractError> {
    let slice_bytes = usize::try_from(ENCODED_SLICE_BYTES).map_err(|_| {
        invalid_model(
            "invalid_tensor_range",
            "the encoded model slice size is not representable",
        )
    })?;
    sha256_exact_range_with_reader(TENSOR_DATA_OFFSET, slice_bytes, cancellation, reader)
}

fn sha256_exact_range(
    file: &File,
    offset: u64,
    byte_count: usize,
    cancellation: &CancellationToken,
) -> Result<String, ContractError> {
    sha256_exact_range_with_reader(
        offset,
        byte_count,
        cancellation,
        |destination, read_offset| positional_read(file, destination, read_offset),
    )
}

fn sha256_exact_range_with_reader(
    offset: u64,
    byte_count: usize,
    cancellation: &CancellationToken,
    mut reader: impl FnMut(&mut [u8], u64) -> std::io::Result<usize>,
) -> Result<String, ContractError> {
    cancellation.check()?;
    let mut bytes = vec![0_u8; byte_count];
    let mut read = 0_usize;
    while read < bytes.len() {
        cancellation.check()?;
        let read_offset = offset
            .checked_add(u64::try_from(read).map_err(|_| {
                invalid_model(
                    "invalid_tensor_range",
                    "the bounded slice offset is not representable",
                )
            })?)
            .ok_or_else(|| {
                invalid_model("invalid_tensor_range", "the bounded slice offset overflows")
            })?;
        let count = reader(&mut bytes[read..], read_offset).map_err(|_| {
            invalid_model(
                "model_read_failed",
                "the external model bounded slice could not be read",
            )
        })?;
        if count == 0 || count > bytes.len() - read {
            return Err(invalid_model(
                "model_read_failed",
                "the external model did not provide the complete bounded slice",
            ));
        }
        read += count;
        cancellation.check()?;
    }
    Ok(format!("{:x}", Sha256::digest(bytes)))
}

fn positional_read(file: &File, destination: &mut [u8], offset: u64) -> std::io::Result<usize> {
    #[cfg(unix)]
    {
        file.read_at(destination, offset)
    }
    #[cfg(windows)]
    {
        file.seek_read(destination, offset)
    }
    #[cfg(not(any(unix, windows)))]
    {
        let _ = (file, destination, offset);
        Err(std::io::Error::new(
            std::io::ErrorKind::Unsupported,
            "positional file reads are unsupported on this platform",
        ))
    }
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

#[cfg(test)]
mod tests {
    use super::*;
    use gguf::{TensorInfo, GGUF_MAGIC};
    use std::fs::{self, OpenOptions};
    use std::sync::atomic::{AtomicU64, Ordering};

    static FIXTURE_NONCE: AtomicU64 = AtomicU64::new(0);
    const FIXTURE_DATA_OFFSET: u64 = 64;
    const FIXTURE_RELATIVE_OFFSET: u64 = 32;
    const FIXTURE_ABSOLUTE_OFFSET: u64 = FIXTURE_DATA_OFFSET + FIXTURE_RELATIVE_OFFSET;

    struct RouterFileFixture {
        path: std::path::PathBuf,
        file: File,
    }

    impl Drop for RouterFileFixture {
        fn drop(&mut self) {
            let _ = fs::remove_file(&self.path);
        }
    }

    fn empty_gguf() -> Gguf {
        let mut header = Vec::new();
        header.extend_from_slice(&GGUF_MAGIC.to_le_bytes());
        header.extend_from_slice(&3_u32.to_le_bytes());
        header.extend_from_slice(&0_u64.to_le_bytes());
        header.extend_from_slice(&0_u64.to_le_bytes());
        Gguf::parse(&header).expect("minimal GGUF header parses")
    }

    fn router_gguf() -> Gguf {
        let mut gguf = empty_gguf();
        gguf.data_offset = FIXTURE_DATA_OFFSET;
        gguf.metadata
            .insert(ROUTER_EXPERT_USED_KEY.to_owned(), Value::U32(8));
        gguf.tensors.push(TensorInfo {
            name: ROUTER_TENSOR_NAME.to_owned(),
            dims: vec![ROUTER_HIDDEN_WIDTH as u64, ROUTER_EXPERT_COUNT as u64],
            ty: TensorType::F32,
            offset: FIXTURE_RELATIVE_OFFSET,
        });
        gguf
    }

    fn router_file(file_bytes: u64) -> RouterFileFixture {
        let nonce = FIXTURE_NONCE.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "pulsarmlx-model-router-inventory-{}-{nonce}.gguf",
            std::process::id()
        ));
        let writable = OpenOptions::new()
            .create_new(true)
            .read(true)
            .write(true)
            .open(&path)
            .expect("create isolated sparse router fixture");
        writable
            .set_len(file_bytes)
            .expect("size isolated sparse router fixture");
        drop(writable);
        let file = File::open(&path).expect("reopen router fixture read-only");
        RouterFileFixture { path, file }
    }

    fn complete_router_file() -> RouterFileFixture {
        router_file(FIXTURE_ABSOLUTE_OFFSET + ROUTER_TENSOR_BYTES)
    }

    fn assert_router_error(gguf: &Gguf, expected_code: &str) {
        let fixture = complete_router_file();
        let error = inspect_router_inventory(gguf, &fixture.file)
            .expect_err("invalid router inventory must fail closed");
        assert_eq!(error.code(), expected_code);
    }

    #[test]
    fn exact_router_inventory_is_hash_bound_with_explicit_absent_defaults() {
        let fixture = complete_router_file();
        let observed = inspect_router_inventory(&router_gguf(), &fixture.file)
            .expect("exact complete router inventory is admitted");
        let descriptor = observed.descriptor();

        assert_eq!(descriptor.name, ROUTER_TENSOR_NAME);
        assert_eq!(descriptor.gguf_dimensions_fastest_axis_first, [2_048, 128]);
        assert_eq!(descriptor.reader_shape, [128, 2_048]);
        assert_eq!(descriptor.execution_shape, [128, 2_048]);
        assert_eq!(descriptor.gguf_type, "F32");
        assert_eq!(descriptor.quantization, "none_f32");
        assert_eq!(descriptor.logical_elements, ROUTER_TENSOR_ELEMENTS);
        assert_eq!(descriptor.absolute_data_offset, FIXTURE_ABSOLUTE_OFFSET);
        assert_eq!(descriptor.encoded_length, ROUTER_TENSOR_BYTES);
        assert_eq!(
            descriptor.encoded_sha256,
            format!(
                "{:x}",
                Sha256::digest(vec![0_u8; ROUTER_TENSOR_BYTES as usize])
            )
        );
        assert_eq!(observed.relative_data_offset(), FIXTURE_RELATIVE_OFFSET);
        assert_eq!(
            observed.exclusive_end_offset(),
            FIXTURE_ABSOLUTE_OFFSET + ROUTER_TENSOR_BYTES
        );
        assert_eq!(observed.expert_used_count(), 8);
        assert_eq!(observed.expert_used_count_value_type(), UINT32_VALUE_TYPE);
        assert!(!observed.weight_scale_metadata_present());
        assert_eq!(observed.weight_scale_value_type(), None);
        assert_eq!(observed.weight_scale_metadata_value(), None);
        assert_eq!(descriptor.weight_scale.to_bits(), 1.0_f32.to_bits());
        assert!(!observed.expert_weights_norm_metadata_present());
        assert_eq!(observed.expert_weights_norm_value_type(), None);
        assert_eq!(observed.expert_weights_norm(), None);
        assert!(observed.expert_weights_norm_effective());
        assert_eq!(observed.router_bias_occurrence_count(), 0);
        assert_eq!(observed.correction_bias_occurrence_count(), 0);
        assert_eq!(observed.unexpected_router_alias_occurrence_count(), 0);
    }

    #[test]
    fn present_scale_and_normalization_metadata_are_typed_and_retained() {
        let fixture = complete_router_file();
        let mut gguf = router_gguf();
        gguf.metadata
            .insert(ROUTER_WEIGHT_SCALE_KEY.to_owned(), Value::F32(1.0));
        gguf.metadata
            .insert(ROUTER_WEIGHT_NORM_KEY.to_owned(), Value::Bool(true));

        let observed = inspect_router_inventory(&gguf, &fixture.file)
            .expect("exact typed optional routing metadata is admitted");
        assert!(observed.weight_scale_metadata_present());
        assert_eq!(observed.weight_scale_value_type(), Some(FLOAT32_VALUE_TYPE));
        assert_eq!(observed.weight_scale_metadata_value(), Some(1.0));
        assert!(observed.expert_weights_norm_metadata_present());
        assert_eq!(
            observed.expert_weights_norm_value_type(),
            Some(BOOL_VALUE_TYPE)
        );
        assert_eq!(observed.expert_weights_norm(), Some(true));
        assert!(observed.expert_weights_norm_effective());
    }

    #[test]
    fn routing_metadata_type_and_value_mismatches_fail_closed() {
        let cases = [
            (
                ROUTER_EXPERT_USED_KEY,
                Value::U64(8),
                "model_metadata_type_mismatch",
            ),
            (
                ROUTER_EXPERT_USED_KEY,
                Value::U32(7),
                "model_metadata_mismatch",
            ),
            (
                ROUTER_WEIGHT_SCALE_KEY,
                Value::F64(1.0),
                "model_metadata_type_mismatch",
            ),
            (
                ROUTER_WEIGHT_SCALE_KEY,
                Value::F32(0.5),
                "model_metadata_mismatch",
            ),
            (
                ROUTER_WEIGHT_NORM_KEY,
                Value::U32(1),
                "model_metadata_type_mismatch",
            ),
            (
                ROUTER_WEIGHT_NORM_KEY,
                Value::Bool(false),
                "model_metadata_mismatch",
            ),
        ];
        for (key, value, expected_code) in cases {
            let mut gguf = router_gguf();
            gguf.metadata.insert(key.to_owned(), value);
            assert_router_error(&gguf, expected_code);
        }

        let mut missing_top_k = router_gguf();
        missing_top_k.metadata.remove(ROUTER_EXPERT_USED_KEY);
        assert_router_error(&missing_top_k, "model_metadata_type_mismatch");
    }

    #[test]
    fn missing_duplicate_wrong_type_and_wrong_shape_router_tensors_are_rejected() {
        let mut missing = router_gguf();
        missing.tensors.clear();
        assert_router_error(&missing, "missing_tensor_role");

        let mut duplicate = router_gguf();
        duplicate.tensors.push(duplicate.tensors[0].clone());
        assert_router_error(&duplicate, "duplicate_tensor_role");

        let mut wrong_type = router_gguf();
        wrong_type.tensors[0].ty = TensorType::Q8_0;
        assert_router_error(&wrong_type, "unsupported_tensor_quantization");

        let mut wrong_shape = router_gguf();
        wrong_shape.tensors[0].dims = vec![128, 2_048];
        assert_router_error(&wrong_shape, "model_tensor_mismatch");
    }

    #[test]
    fn router_and_correction_bias_tensors_are_rejected_before_range_read() {
        for forbidden_name in std::iter::once(ROUTER_BIAS_NAME)
            .chain(ROUTER_CORRECTION_BIAS_NAMES.iter().copied())
            .chain([
                "blk.0.ffn_gate_inp.unreviewed_correction",
                "blk.0.router_surprise.weight",
                "blk.0.exp_probs_future.bias",
            ])
        {
            let mut gguf = router_gguf();
            gguf.tensors.push(TensorInfo {
                name: forbidden_name.to_owned(),
                dims: vec![ROUTER_EXPERT_COUNT as u64],
                ty: TensorType::F32,
                offset: 0,
            });
            assert_router_error(&gguf, "model_tensor_mismatch");
        }

        let mut unrelated = router_gguf();
        unrelated.tensors.push(TensorInfo {
            name: "blk.1.router_surprise.weight".to_owned(),
            dims: vec![ROUTER_EXPERT_COUNT as u64],
            ty: TensorType::F32,
            offset: 0,
        });
        let fixture = complete_router_file();
        inspect_router_inventory(&unrelated, &fixture.file)
            .expect("a similarly named tensor outside layer 0 is outside this scan");
    }

    #[test]
    fn truncated_and_overflowing_router_ranges_are_rejected() {
        let truncated = router_file(FIXTURE_ABSOLUTE_OFFSET + ROUTER_TENSOR_BYTES - 1);
        let error = inspect_router_inventory(&router_gguf(), &truncated.file)
            .expect_err("a truncated complete router range must fail");
        assert_eq!(error.code(), "invalid_tensor_range");

        let fixture = complete_router_file();
        let mut overflowing = router_gguf();
        overflowing.data_offset = u64::MAX;
        overflowing.tensors[0].offset = 1;
        let error = inspect_router_inventory(&overflowing, &fixture.file)
            .expect_err("an overflowing absolute router offset must fail");
        assert_eq!(error.code(), "invalid_tensor_range");
    }

    #[cfg(unix)]
    #[test]
    fn read_only_open_exposes_comparison_identity_and_rejects_final_symlinks() {
        use std::os::unix::fs::{symlink, MetadataExt};
        use std::os::unix::io::AsRawFd;

        let fixture = router_file(4 * 1024 * 1024);
        let (file, metadata, identity) =
            open_read_only_no_follow(&fixture.path).expect("regular sparse file opens read-only");
        let descriptor_flags = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GETFL) };
        assert_ne!(descriptor_flags, -1);
        assert_eq!(descriptor_flags & libc::O_ACCMODE, libc::O_RDONLY);
        assert_eq!(
            identity.unix_device_and_inode(),
            Some((metadata.dev(), metadata.ino()))
        );
        verify_path_matches_open_file(&fixture.path, &file, identity)
            .expect("the unchanged path still names the retained descriptor");

        let alias = fixture.path.with_extension("alias.gguf");
        symlink(&fixture.path, &alias).expect("create final-component symbolic link");
        let error = match open_read_only_no_follow(&alias) {
            Ok(_) => panic!("a final-component symbolic link must fail closed"),
            Err(error) => error,
        };
        assert_eq!(error.code(), "model_unavailable");
        fs::remove_file(alias).expect("remove symbolic-link fixture");
    }

    #[cfg(unix)]
    #[test]
    fn retained_descriptor_rejects_same_size_path_replacement() {
        let fixture = router_file(4 * 1024 * 1024);
        let (file, _metadata, identity) =
            open_read_only_no_follow(&fixture.path).expect("regular sparse file opens read-only");
        let displaced = fixture.path.with_extension("displaced.gguf");
        fs::rename(&fixture.path, &displaced).expect("move the originally opened inode");
        let replacement = OpenOptions::new()
            .create_new(true)
            .read(true)
            .write(true)
            .open(&fixture.path)
            .expect("create a same-size replacement");
        replacement
            .set_len(4 * 1024 * 1024)
            .expect("size the replacement sparsely");
        drop(replacement);

        let error = verify_path_matches_open_file(&fixture.path, &file, identity)
            .expect_err("a same-size path replacement must not match the retained descriptor");
        assert_eq!(error.code(), "model_path_identity_changed");

        fs::remove_file(&fixture.path).expect("remove replacement path");
        fs::rename(&displaced, &fixture.path).expect("restore original fixture for cleanup");
    }

    #[test]
    fn cancellable_inspection_checks_token_before_path_access() {
        let nonce = FIXTURE_NONCE.fetch_add(1, Ordering::Relaxed);
        let missing = std::env::temp_dir()
            .join(format!(
                "pulsarmlx-missing-qwen-{pid}-{nonce}",
                pid = std::process::id()
            ))
            .join(FILENAME);
        let invalid_parent = std::env::temp_dir().join(format!(
            "pulsarmlx-invalid-qwen-{pid}-{nonce}",
            pid = std::process::id()
        ));
        fs::create_dir(&invalid_parent).expect("create invalid metadata parent");
        let invalid_directory = invalid_parent.join(FILENAME);
        fs::create_dir(&invalid_directory).expect("create directory where model file would be");
        let repository_root = std::env::current_dir().expect("current repository root");
        let budget = frozen_qwen_model_memory_budget(u64::MAX, u64::MAX);
        let cancellation = CancellationToken::new();
        cancellation.cancel();

        for requested_path in [&missing, &invalid_directory] {
            let error = match inspect_external_qwen_model_with_cancellation(
                requested_path,
                &repository_root,
                budget.clone(),
                &cancellation,
            ) {
                Ok(_) => panic!("pre-cancelled admission must fail before path I/O"),
                Err(error) => error,
            };
            assert_eq!(error.code(), "cancelled");
        }

        fs::remove_dir(&invalid_directory).expect("remove invalid directory");
        fs::remove_dir(&invalid_parent).expect("remove invalid parent");
    }

    struct CancelsAfterFirstRead<'a> {
        cancellation: &'a CancellationToken,
        reads: usize,
    }

    impl Read for CancelsAfterFirstRead<'_> {
        fn read(&mut self, destination: &mut [u8]) -> std::io::Result<usize> {
            if destination.is_empty() {
                return Ok(0);
            }
            self.reads += 1;
            destination[0] = 0x5a;
            self.cancellation.cancel();
            Ok(1)
        }
    }

    #[test]
    fn full_hash_reader_honors_mid_stream_cancellation() {
        let cancellation = CancellationToken::new();
        let mut reader = CancelsAfterFirstRead {
            cancellation: &cancellation,
            reads: 0,
        };

        let error = sha256_stream_with_buffer(&mut reader, &cancellation, 1)
            .expect_err("hashing must stop after caller cancellation");

        assert_eq!(error.code(), "cancelled");
        assert_eq!(reader.reads, 1);
    }

    #[test]
    fn bounded_header_reader_honors_mid_stream_cancellation() {
        let cancellation = CancellationToken::new();
        let mut reader = CancelsAfterFirstRead {
            cancellation: &cancellation,
            reads: 0,
        };

        let error = read_header_prefix_with_reader(&mut reader, 2, 1, &cancellation)
            .expect_err("header reading must stop after caller cancellation");

        assert_eq!(error.code(), "cancelled");
        assert_eq!(reader.reads, 1);
    }

    #[test]
    fn qwen_initial_slice_hash_uses_the_caller_cancellation_token() {
        let cancellation = CancellationToken::new();
        let mut reads = 0_usize;
        let mut offsets = Vec::new();
        let result = sha256_qwen_encoded_slice_with_reader(&cancellation, |destination, offset| {
            reads += 1;
            offsets.push(offset);
            destination[0] = 0;
            cancellation.cancel();
            Ok(1)
        });

        assert_eq!(
            result
                .expect_err("caller cancellation must stop the initial Qwen slice hash")
                .code(),
            "cancelled"
        );
        assert_eq!(reads, 1);
        assert_eq!(offsets, [TENSOR_DATA_OFFSET]);
    }

    #[test]
    fn range_hash_honors_cancellation_between_identity_reads() {
        let cancellation = CancellationToken::new();
        let mut reads = 0_usize;
        let mut offsets = Vec::new();
        let result = sha256_exact_range_with_reader(37, 2, &cancellation, |destination, offset| {
            reads += 1;
            offsets.push(offset);
            destination[0] = 0;
            cancellation.cancel();
            Ok(1)
        });

        assert_eq!(
            result
                .expect_err("cancellation must stop range hashing")
                .code(),
            "cancelled"
        );
        assert_eq!(reads, 1);
        assert_eq!(offsets, [37]);
    }
}
