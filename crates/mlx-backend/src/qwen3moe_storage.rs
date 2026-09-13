//! Bounded, source-free Qwen3MoE storage and exact f32 decode seam.
//!
//! The public API consumes an already-admitted Qwen3MoE graph descriptor and
//! backend-neutral catalog/store contracts. It validates the retained artifact
//! and performs one whole-slab read of a tiny, exact Q8_0 lane; it does not open
//! paths or provide a fallback decoder.

use backend::{
    CancellationToken, CheckpointIdentity, ContractError, ErrorCategory, RuntimeTensor,
    TensorCatalog, TensorRange, TensorStore,
};
use sha2::{Digest, Sha256};
use std::fs::File;
use std::io;
use std::mem::{align_of, size_of};
#[cfg(unix)]
use std::os::unix::fs::FileExt;
#[cfg(windows)]
use std::os::windows::fs::FileExt;

use crate::model::{
    ExternalFileIdentity, ExternalModelInspection, ExternalQwen3MoeStorageBinding,
    QWEN_DECODED_SLICE_BYTES, QWEN_ENCODED_SLICE_BYTES, QWEN_TENSOR_DATA_OFFSET,
};
use crate::qwen3moe::{
    admit_qwen3moe_full_graph, Qwen3MoeAdapterDescriptor, Qwen3MoeArtifactBinding,
    Qwen3MoeFullGraphAdmissionInput, Qwen3MoeFullGraphDescriptor, Qwen3MoeTensorDescriptor,
    Qwen3MoeTensorRole, QWEN3MOE_ADAPTER_CONTRACT_ID, QWEN3MOE_EXPERT_FFN_WIDTH,
    QWEN3MOE_FULL_GRAPH_CONTRACT_ID, QWEN3MOE_HIDDEN_WIDTH, QWEN3MOE_REVISION, QWEN3MOE_SHA256,
};

/// The only decoder contract admitted by this bounded synthetic lane.
pub const QWEN3MOE_Q8_0_DECODER_CONTRACT_ID: &str = "qwen3moe-q8_0-f32";
/// Version of the exact Q8_0-to-contiguous-f32 decoder contract.
pub const QWEN3MOE_Q8_0_DECODER_VERSION: &str = "v1";
/// Q8_0 block element count.
pub const QWEN3MOE_Q8_0_BLOCK_ELEMENTS: u64 = 32;
/// Q8_0 block byte count: one f16 scale and 32 signed values.
pub const QWEN3MOE_Q8_0_BLOCK_BYTES: u64 = 34;
/// Algorithm metadata for the canonical little-endian f32 content hash.
pub const QWEN3MOE_F32_HASH_ALGORITHM: &str = "sha256-f32-le";

const MAX_CORRELATION_ID_CHARS: usize = 256;
const MAX_SHAPE_RANK: usize = 8;
// This deliberately bounded lane is for deterministic synthetic fixtures only;
// real checkpoint qualification is outside this seam.
const MAX_SYNTHETIC_DECODE_ELEMENTS: u64 = 1_048_576;
const MAX_SYNTHETIC_ENCODED_BYTES: u64 = 1 << 20;
const DECODE_CHUNK_BLOCKS: usize = 8;

/// An explicit decoder contract/version selected before storage work begins.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Qwen3MoeDecoderContract {
    contract_id: &'static str,
    version: &'static str,
}

impl Qwen3MoeDecoderContract {
    /// Construct the sole supported exact synthetic decoder contract.
    pub const fn q8_0() -> Self {
        Self {
            contract_id: QWEN3MOE_Q8_0_DECODER_CONTRACT_ID,
            version: QWEN3MOE_Q8_0_DECODER_VERSION,
        }
    }

    /// Validate an explicitly named decoder contract without guessing.
    pub fn try_new(
        contract_id: impl Into<String>,
        version: impl Into<String>,
    ) -> Result<Self, ContractError> {
        if contract_id.into() != QWEN3MOE_Q8_0_DECODER_CONTRACT_ID
            || version.into() != QWEN3MOE_Q8_0_DECODER_VERSION
        {
            return Err(storage_error(
                ErrorCategory::InvalidQuantization,
                "unsupported_decoder_contract",
                "the requested Qwen3MoE decoder contract is not admitted",
            ));
        }
        Ok(Self::q8_0())
    }

    pub const fn contract_id(self) -> &'static str {
        self.contract_id
    }

    pub const fn version(self) -> &'static str {
        self.version
    }
}

/// Destination ownership selected before storage access.
///
/// This bounded lane admits only Rust-owned output. Caller-owned storage is
/// deliberately represented so it cannot be silently treated as Rust-owned
/// until its alignment, size, mutability, lifetime, and release/fence proof
/// are part of the contract.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Qwen3MoeDestinationPolicy {
    RustOwned,
    CallerOwned,
}

/// Immutable storage/decode request derived from one retained admitted tensor.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct Qwen3MoeStorageRequest {
    checkpoint: CheckpointIdentity,
    tensor: Qwen3MoeTensorDescriptor,
    source_tensor: Qwen3MoeTensorDescriptor,
    production_slice: bool,
    destination_policy: Qwen3MoeDestinationPolicy,
    decoder_contract: Qwen3MoeDecoderContract,
    correlation_id: String,
    cancellation: CancellationToken,
}

impl Qwen3MoeStorageRequest {
    /// Select a tensor by its typed role from an already-admitted full graph.
    ///
    /// The tensor name, shard identity, checkpoint identity, and range are all
    /// retained from the descriptor. Callers cannot provide a free-form tensor
    /// name or path to this constructor.
    fn try_new(
        descriptor: &Qwen3MoeFullGraphDescriptor,
        role: Qwen3MoeTensorRole,
        layer_index: Option<u32>,
        destination_policy: Qwen3MoeDestinationPolicy,
        decoder_contract: Qwen3MoeDecoderContract,
        correlation_id: impl Into<String>,
        cancellation: CancellationToken,
    ) -> Result<Self, ContractError> {
        validate_destination_policy(destination_policy)?;
        descriptor.verify_admission_proof()?;
        if descriptor.contract_id != QWEN3MOE_FULL_GRAPH_CONTRACT_ID {
            return Err(storage_error(
                ErrorCategory::InvalidModel,
                "qwen3moe_graph_contract_mismatch",
                "storage requires the admitted Qwen3MoE full-graph contract",
            ));
        }
        let admitted = admit_qwen3moe_full_graph(Qwen3MoeFullGraphAdmissionInput {
            adapter: Qwen3MoeAdapterDescriptor {
                contract_id: QWEN3MOE_ADAPTER_CONTRACT_ID.to_owned(),
                artifact: descriptor.artifact.clone(),
                metadata: descriptor.metadata.clone(),
                tensors: descriptor.tensors.clone(),
            },
            graph: descriptor.graph.clone(),
        })?;
        let tensor = admitted
            .tensors
            .iter()
            .find(|tensor| tensor.role == role && tensor.layer_index == layer_index)
            .cloned()
            .ok_or_else(|| {
                storage_error(
                    ErrorCategory::InvalidTensor,
                    "qwen3moe_tensor_not_admitted",
                    "the requested typed tensor is absent from the admitted catalog",
                )
            })?;
        Self::from_selected_tensor(
            &admitted.artifact,
            tensor.clone(),
            tensor,
            false,
            destination_policy,
            decoder_contract,
            correlation_id,
            cancellation,
        )
    }

    #[doc(hidden)]
    fn try_new_synthetic_for_test(
        descriptor: &Qwen3MoeFullGraphDescriptor,
        role: Qwen3MoeTensorRole,
        layer_index: Option<u32>,
        destination_policy: Qwen3MoeDestinationPolicy,
        decoder_contract: Qwen3MoeDecoderContract,
        correlation_id: impl Into<String>,
        cancellation: CancellationToken,
    ) -> Result<Self, ContractError> {
        validate_destination_policy(destination_policy)?;
        let tensor = descriptor
            .tensors
            .iter()
            .find(|tensor| tensor.role == role && tensor.layer_index == layer_index)
            .cloned()
            .ok_or_else(|| {
                storage_error(
                    ErrorCategory::InvalidTensor,
                    "qwen3moe_tensor_not_admitted",
                    "the requested typed tensor is absent from the synthetic fixture",
                )
            })?;
        Self::from_selected_tensor(
            &descriptor.artifact,
            tensor.clone(),
            tensor,
            false,
            destination_policy,
            decoder_contract,
            correlation_id,
            cancellation,
        )
    }

    fn from_selected_tensor(
        artifact: &Qwen3MoeArtifactBinding,
        tensor: Qwen3MoeTensorDescriptor,
        source_tensor: Qwen3MoeTensorDescriptor,
        production_slice: bool,
        destination_policy: Qwen3MoeDestinationPolicy,
        decoder_contract: Qwen3MoeDecoderContract,
        correlation_id: impl Into<String>,
        cancellation: CancellationToken,
    ) -> Result<Self, ContractError> {
        let checkpoint =
            CheckpointIdentity::try_new(artifact.sha256.clone(), artifact.revision.clone())?;
        let correlation_id = correlation_id.into();
        validate_correlation_id(&correlation_id)?;

        Ok(Self {
            checkpoint,
            tensor,
            source_tensor,
            production_slice,
            destination_policy,
            decoder_contract,
            correlation_id,
            cancellation,
        })
    }

    pub fn checkpoint(&self) -> &CheckpointIdentity {
        &self.checkpoint
    }

    pub fn tensor(&self) -> &Qwen3MoeTensorDescriptor {
        &self.tensor
    }

    pub const fn destination_policy(&self) -> Qwen3MoeDestinationPolicy {
        self.destination_policy
    }

    pub const fn decoder_contract(&self) -> Qwen3MoeDecoderContract {
        self.decoder_contract
    }

    pub fn correlation_id(&self) -> &str {
        &self.correlation_id
    }

    pub fn cancellation(&self) -> &CancellationToken {
        &self.cancellation
    }

    fn try_new_admitted_layer0_slice(
        descriptor: &Qwen3MoeFullGraphDescriptor,
        destination_policy: Qwen3MoeDestinationPolicy,
        decoder_contract: Qwen3MoeDecoderContract,
        correlation_id: impl Into<String>,
        cancellation: CancellationToken,
    ) -> Result<Self, ContractError> {
        validate_destination_policy(destination_policy)?;
        descriptor.verify_admission_proof()?;
        let source_tensor = descriptor
            .tensor("blk.0.ffn_gate_exps.weight")
            .cloned()
            .ok_or_else(|| {
                storage_error(
                    ErrorCategory::InvalidTensor,
                    "qwen3moe_tensor_not_admitted",
                    "the admitted layer-0 expert-gate tensor is absent",
                )
            })?;
        let tensor = admitted_layer0_slice(&source_tensor)?;
        Self::from_selected_tensor(
            &descriptor.artifact,
            tensor,
            source_tensor,
            true,
            destination_policy,
            decoder_contract,
            correlation_id,
            cancellation,
        )
    }
}

/// File-backed catalog/store bound to one admitted external Qwen artifact.
///
/// The adapter owns only a clone of the inspection's already-opened read-only
/// descriptor. It exposes no path, arbitrary tensor-name reader, or fixture
/// fallback; each operation rechecks pathname identity and file metadata.
struct Qwen3MoeExternalStorage {
    binding: ExternalQwen3MoeStorageBinding,
    cancellation: CancellationToken,
}

impl Qwen3MoeExternalStorage {
    /// Bind storage to one previously admitted inspection without reopening it.
    fn try_from_inspection(
        inspection: &ExternalModelInspection,
        cancellation: &CancellationToken,
    ) -> Result<Self, ContractError> {
        cancellation.check()?;
        let binding = inspection.bind_qwen3moe_storage(cancellation)?;
        cancellation.check()?;
        let artifact = &binding.full_graph.artifact;
        if binding.full_graph.contract_id != QWEN3MOE_FULL_GRAPH_CONTRACT_ID
            || artifact.repository_id != crate::qwen3moe::QWEN3MOE_REPOSITORY_ID
            || artifact.revision != QWEN3MOE_REVISION
            || artifact.filename != crate::qwen3moe::QWEN3MOE_FILENAME
            || artifact.size_bytes != crate::qwen3moe::QWEN3MOE_FILE_BYTES
            || artifact.sha256 != QWEN3MOE_SHA256
        {
            return Err(storage_error(
                ErrorCategory::InvalidModel,
                "qwen3moe_checkpoint_identity_mismatch",
                "the external storage binding is not tied to the admitted Qwen artifact",
            ));
        }
        cancellation.check()?;
        Ok(Self {
            binding,
            cancellation: cancellation.clone(),
        })
    }

    fn verify_identity(&self) -> Result<(), ContractError> {
        verify_binding_identity(&self.binding, &self.cancellation)
    }
}

/// Read and decode the exact admitted layer-0 expert-gate rows 0 through 16.
pub fn read_admitted_layer0_expert_gate_rows_0_to_16(
    inspection: &ExternalModelInspection,
    correlation_id: impl Into<String>,
    cancellation: CancellationToken,
) -> Result<Qwen3MoEDecodedTensor, ContractError> {
    cancellation.check()?;
    let storage = Qwen3MoeExternalStorage::try_from_inspection(inspection, &cancellation)?;
    let request = Qwen3MoeStorageRequest::try_new_admitted_layer0_slice(
        &storage.binding.full_graph,
        Qwen3MoeDestinationPolicy::RustOwned,
        Qwen3MoeDecoderContract::q8_0(),
        correlation_id,
        cancellation,
    )?;
    read_admitted_tensor_internal(&storage, &request)
}

fn read_admitted_tensor_internal(
    storage: &Qwen3MoeExternalStorage,
    request: &Qwen3MoeStorageRequest,
) -> Result<Qwen3MoEDecodedTensor, ContractError> {
    storage.verify_identity()?;
    storage.cancellation.check()?;
    if request.checkpoint() != &storage.binding.checkpoint {
        return Err(storage_error(
            ErrorCategory::InvalidModel,
            "qwen3moe_checkpoint_identity_mismatch",
            "the storage request is bound to a different checkpoint identity",
        ));
    }
    let requested = storage
        .binding
        .full_graph
        .tensor(&request.source_tensor.name)
        .ok_or_else(|| {
            storage_error(
                ErrorCategory::InvalidTensor,
                "qwen3moe_tensor_not_admitted",
                "the requested tensor name is absent from the bound graph",
            )
        })?;
    if requested != &request.source_tensor || admitted_layer0_slice(requested)? != request.tensor {
        return Err(storage_error(
            ErrorCategory::InvalidModel,
            "qwen3moe_admitted_tensor_identity_mismatch",
            "the storage request tensor differs from the bound graph entry",
        ));
    }
    storage.cancellation.check()?;
    let decoded = decode_qwen3moe_tensor(request, storage, storage)?;
    storage.verify_identity()?;
    Ok(decoded)
}

impl TensorCatalog for Qwen3MoeExternalStorage {
    fn tensor(&self, name: &str) -> Result<Option<RuntimeTensor>, ContractError> {
        self.verify_identity()?;
        self.cancellation.check()?;
        if name != "blk.0.ffn_gate_exps.weight" {
            return Ok(None);
        }
        let source = self.binding.full_graph.tensor(name).ok_or_else(|| {
            storage_error(
                ErrorCategory::InvalidTensor,
                "qwen3moe_catalog_entry_missing",
                "the admitted layer-0 expert-gate tensor is absent",
            )
        })?;
        let slice = admitted_layer0_slice(source)?;
        Ok(Some(runtime_tensor(&slice)?))
    }
}

impl TensorStore for Qwen3MoeExternalStorage {
    fn read_range(
        &self,
        tensor: &RuntimeTensor,
        destination: &mut [u8],
        cancellation: &CancellationToken,
    ) -> Result<usize, ContractError> {
        self.cancellation.check()?;
        cancellation.check()?;
        self.verify_identity()?;
        self.cancellation.check()?;
        let admitted_source = self
            .binding
            .full_graph
            .tensor("blk.0.ffn_gate_exps.weight")
            .ok_or_else(|| {
                storage_error(
                    ErrorCategory::InvalidTensor,
                    "qwen3moe_catalog_entry_missing",
                    "the requested tensor is absent from the bound graph",
                )
            })?;
        let admitted = admitted_layer0_slice(admitted_source)?;
        self.cancellation.check()?;
        let expected = runtime_tensor(&admitted)?;
        if *tensor != expected {
            return Err(storage_error(
                ErrorCategory::InvalidModel,
                "qwen3moe_catalog_identity_mismatch",
                "the requested runtime tensor differs from the bound graph entry",
            ));
        }
        let length = usize::try_from(expected.range.length).map_err(|_| {
            storage_error(
                ErrorCategory::ResourceLimit,
                "qwen3moe_encoded_allocation_too_large",
                "encoded slab exceeds the bounded allocation limit",
            )
        })?;
        if destination.len() != length {
            return Err(storage_error(
                ErrorCategory::InvalidTensor,
                "qwen3moe_destination_length_mismatch",
                "the destination does not cover the complete admitted tensor range",
            ));
        }
        let end = expected.range.end()?;
        if end > self.binding.file_size {
            return Err(storage_error(
                ErrorCategory::InvalidTensor,
                "qwen3moe_short_read",
                "the admitted tensor range exceeds the retained file",
            ));
        }
        let bytes_read = read_exact_positional(
            &self.binding.file,
            destination,
            expected.range.offset,
            &self.cancellation,
        )?;
        self.cancellation.check()?;
        self.verify_identity()?;
        Ok(bytes_read)
    }
}

fn runtime_tensor(tensor: &Qwen3MoeTensorDescriptor) -> Result<RuntimeTensor, ContractError> {
    let range = TensorRange {
        offset: tensor.absolute_data_offset,
        length: tensor.encoded_bytes,
    };
    range.end()?;
    Ok(RuntimeTensor {
        name: tensor.name.clone(),
        shard: crate::qwen3moe::QWEN3MOE_FILENAME.to_owned(),
        range,
        shape: tensor.reader_shape.clone(),
        quantization: tensor.quantization.clone(),
    })
}

fn admitted_layer0_slice(
    source: &Qwen3MoeTensorDescriptor,
) -> Result<Qwen3MoeTensorDescriptor, ContractError> {
    let row_bytes = *source.reader_shape.last().ok_or_else(|| {
        storage_error(
            ErrorCategory::InvalidTensor,
            "qwen3moe_slice_layout_mismatch",
            "the admitted expert-gate tensor has no Q8_0 row-byte axis",
        )
    })?;
    let full_rows = QWEN3MOE_EXPERT_FFN_WIDTH.checked_mul(128).ok_or_else(|| {
        storage_error(
            ErrorCategory::ArithmeticOverflow,
            "qwen3moe_slice_layout_overflow",
            "the admitted expert-gate row count overflowed",
        )
    })?;
    let slice_rows = QWEN_ENCODED_SLICE_BYTES
        .checked_div(row_bytes)
        .filter(|_| QWEN_ENCODED_SLICE_BYTES % row_bytes == 0)
        .ok_or_else(|| {
            storage_error(
                ErrorCategory::InvalidTensor,
                "qwen3moe_slice_layout_mismatch",
                "the admitted encoded slice does not contain whole Q8_0 rows",
            )
        })?;
    let full_encoded_bytes = row_bytes.checked_mul(full_rows).ok_or_else(|| {
        storage_error(
            ErrorCategory::ArithmeticOverflow,
            "qwen3moe_slice_layout_overflow",
            "the admitted expert-gate encoded size overflowed",
        )
    })?;
    let source_end = source
        .absolute_data_offset
        .checked_add(source.encoded_bytes)
        .ok_or_else(|| {
            storage_error(
                ErrorCategory::ArithmeticOverflow,
                "qwen3moe_slice_layout_overflow",
                "the admitted expert-gate range overflowed",
            )
        })?;
    let slice_end = QWEN_TENSOR_DATA_OFFSET
        .checked_add(QWEN_ENCODED_SLICE_BYTES)
        .ok_or_else(|| {
            storage_error(
                ErrorCategory::ArithmeticOverflow,
                "qwen3moe_slice_layout_overflow",
                "the admitted slice range overflowed",
            )
        })?;
    if source.role != Qwen3MoeTensorRole::ExpertGateWeight
        || source.layer_index != Some(0)
        || source.name != "blk.0.ffn_gate_exps.weight"
        || source.gguf_shape != [QWEN3MOE_HIDDEN_WIDTH, QWEN3MOE_EXPERT_FFN_WIDTH, 128]
        || source.reader_shape != [128, QWEN3MOE_EXPERT_FFN_WIDTH, row_bytes]
        || source.execution_shape != [128, QWEN3MOE_EXPERT_FFN_WIDTH, QWEN3MOE_HIDDEN_WIDTH]
        || source.gguf_type != "Q8_0"
        || source.quantization != "Q8_0"
        || source.absolute_data_offset != QWEN_TENSOR_DATA_OFFSET
        || source.encoded_bytes != full_encoded_bytes
        || slice_rows == 0
        || slice_rows > QWEN3MOE_EXPERT_FFN_WIDTH
        || slice_end > source_end
        || QWEN_DECODED_SLICE_BYTES
            != slice_rows
                .checked_mul(QWEN3MOE_HIDDEN_WIDTH)
                .and_then(|elements| elements.checked_mul(size_of::<f32>() as u64))
                .unwrap_or(u64::MAX)
    {
        return Err(storage_error(
            ErrorCategory::InvalidTensor,
            "qwen3moe_slice_not_admitted",
            "the requested range is not the admitted layer-0 expert-gate slice",
        ));
    }
    let logical_elements = slice_rows * QWEN3MOE_HIDDEN_WIDTH;
    Ok(Qwen3MoeTensorDescriptor {
        role: source.role,
        layer_index: source.layer_index,
        name: source.name.clone(),
        gguf_shape: vec![QWEN3MOE_HIDDEN_WIDTH, slice_rows],
        reader_shape: vec![slice_rows, row_bytes],
        execution_shape: vec![slice_rows, QWEN3MOE_HIDDEN_WIDTH],
        gguf_type: source.gguf_type.clone(),
        quantization: source.quantization.clone(),
        orientation: "expert_0_rows_0_to_16".to_owned(),
        logical_elements,
        encoded_bytes: QWEN_ENCODED_SLICE_BYTES,
        absolute_data_offset: QWEN_TENSOR_DATA_OFFSET,
    })
}

fn verify_binding_identity(
    binding: &ExternalQwen3MoeStorageBinding,
    cancellation: &CancellationToken,
) -> Result<(), ContractError> {
    cancellation.check()?;
    let path_metadata = std::fs::symlink_metadata(&binding.canonical_path).map_err(|_| {
        storage_error(
            ErrorCategory::InvalidModel,
            "model_path_identity_changed",
            "the admitted model pathname is no longer available",
        )
    })?;
    cancellation.check()?;
    let open_metadata = binding.file.metadata().map_err(|_| {
        storage_error(
            ErrorCategory::InvalidModel,
            "model_unavailable",
            "the admitted external model descriptor metadata could not be read",
        )
    })?;
    if path_metadata.file_type().is_symlink()
        || !path_metadata.is_file()
        || !open_metadata.is_file()
        || ExternalFileIdentity::from_metadata(&path_metadata) != binding.opened_file_identity
        || ExternalFileIdentity::from_metadata(&open_metadata) != binding.opened_file_identity
    {
        return Err(storage_error(
            ErrorCategory::InvalidModel,
            "model_path_identity_changed",
            "the admitted model pathname no longer resolves to the retained regular file",
        ));
    }
    cancellation.check()?;
    let artifact_size = binding.full_graph.artifact.size_bytes;
    if open_metadata.len() != binding.file_size || open_metadata.len() != artifact_size {
        return Err(storage_error(
            ErrorCategory::InvalidModel,
            "model_size_mismatch",
            "the retained external model size differs from its immutable artifact",
        ));
    }
    cancellation.check()?;
    let slice_hash = sha256_exact_range(
        &binding.file,
        QWEN_TENSOR_DATA_OFFSET,
        usize::try_from(QWEN_ENCODED_SLICE_BYTES).map_err(|_| {
            storage_error(
                ErrorCategory::ArithmeticOverflow,
                "qwen3moe_slice_hash_size_overflow",
                "the admitted slice hash size is not representable",
            )
        })?,
        cancellation,
    )?;
    cancellation.check()?;
    if slice_hash != binding.admitted_slice_sha256 {
        return Err(storage_error(
            ErrorCategory::InvalidModel,
            "model_checksum_mismatch",
            "the admitted external model slice content changed",
        ));
    }
    Ok(())
}

fn read_exact_positional(
    file: &File,
    destination: &mut [u8],
    offset: u64,
    cancellation: &CancellationToken,
) -> Result<usize, ContractError> {
    let mut total = 0_usize;
    while total < destination.len() {
        cancellation.check()?;
        let read_offset = offset
            .checked_add(u64::try_from(total).map_err(|_| {
                storage_error(
                    ErrorCategory::ArithmeticOverflow,
                    "qwen3moe_read_offset_overflow",
                    "the positional read offset is not representable",
                )
            })?)
            .ok_or_else(|| {
                storage_error(
                    ErrorCategory::ArithmeticOverflow,
                    "qwen3moe_read_offset_overflow",
                    "the positional read offset overflowed",
                )
            })?;
        let count = loop {
            match positional_read(file, &mut destination[total..], read_offset) {
                Ok(count) => break count,
                Err(error) if error.kind() == io::ErrorKind::Interrupted => continue,
                Err(_) => {
                    return Err(storage_error(
                        ErrorCategory::InvalidTensor,
                        "qwen3moe_read_failed",
                        "the admitted tensor range could not be read",
                    ));
                }
            }
        };
        let remaining = destination.len() - total;
        if count == 0 {
            return Err(storage_error(
                ErrorCategory::InvalidTensor,
                "qwen3moe_short_read",
                "the admitted tensor range ended before the requested byte count",
            ));
        }
        if count > remaining {
            return Err(storage_error(
                ErrorCategory::InvalidTensor,
                "qwen3moe_overlong_read",
                "the positional reader returned more bytes than requested",
            ));
        }
        total += count;
        cancellation.check()?;
    }
    Ok(total)
}

fn positional_read(file: &File, destination: &mut [u8], offset: u64) -> io::Result<usize> {
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
        Err(io::Error::new(
            io::ErrorKind::Unsupported,
            "positional file reads are unsupported on this platform",
        ))
    }
}

fn sha256_exact_range(
    file: &File,
    offset: u64,
    byte_count: usize,
    cancellation: &CancellationToken,
) -> Result<String, ContractError> {
    cancellation.check()?;
    let mut bytes = vec![0_u8; byte_count];
    read_exact_positional(file, &mut bytes, offset, cancellation)?;
    cancellation.check()?;
    Ok(format!("{:x}", Sha256::digest(bytes)))
}

/// Hash metadata for the initialized decoded f32 content.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Qwen3MoeContentHashMetadata {
    algorithm: &'static str,
    sha256: String,
}

impl Qwen3MoeContentHashMetadata {
    pub const fn algorithm(&self) -> &'static str {
        self.algorithm
    }

    pub fn sha256(&self) -> &str {
        &self.sha256
    }
}

/// Owned, contiguous, initialized f32 output from the exact decoder lane.
#[derive(Debug, Clone, PartialEq)]
pub struct Qwen3MoEDecodedTensor {
    data: Vec<f32>,
    shape: Vec<u64>,
    byte_length: u64,
    alignment: usize,
    destination_policy: Qwen3MoeDestinationPolicy,
    decoder_version: &'static str,
    content_hash: Qwen3MoeContentHashMetadata,
}

impl Qwen3MoEDecodedTensor {
    pub fn data(&self) -> &[f32] {
        &self.data
    }

    pub fn into_data(self) -> Vec<f32> {
        self.data
    }

    pub fn shape(&self) -> &[u64] {
        &self.shape
    }

    pub const fn byte_length(&self) -> u64 {
        self.byte_length
    }

    /// The alignment guaranteed by the owned `Vec<f32>` allocation.
    pub const fn alignment(&self) -> usize {
        self.alignment
    }

    pub const fn destination_policy(&self) -> Qwen3MoeDestinationPolicy {
        self.destination_policy
    }

    pub const fn decoder_version(&self) -> &'static str {
        self.decoder_version
    }

    pub fn content_hash(&self) -> &Qwen3MoeContentHashMetadata {
        &self.content_hash
    }

    pub fn content_sha256(&self) -> &str {
        self.content_hash.sha256()
    }
}

/// Read and decode one exact, whole Q8_0 slab from an admitted catalog/store.
///
/// The catalog is resolved by the retained admitted tensor name and then the
/// complete returned entry is compared before the store is called. The store
/// receives exactly one bounded destination covering the whole slab.
pub(crate) fn decode_qwen3moe_tensor<C: TensorCatalog, S: TensorStore>(
    request: &Qwen3MoeStorageRequest,
    catalog: &C,
    store: &S,
) -> Result<Qwen3MoEDecodedTensor, ContractError> {
    request.cancellation.check()?;
    let expected = validate_request_tensor(request)?;
    let catalog_tensor = catalog.tensor(&expected.name)?.ok_or_else(|| {
        storage_error(
            ErrorCategory::InvalidModel,
            "qwen3moe_catalog_entry_missing",
            "the admitted tensor is absent from the resolved catalog",
        )
    })?;
    if catalog_tensor != expected {
        return Err(storage_error(
            ErrorCategory::InvalidModel,
            "qwen3moe_catalog_identity_mismatch",
            "the resolved catalog entry differs from the admitted tensor identity",
        ));
    }

    let encoded_length = checked_usize(
        expected.range.length,
        ErrorCategory::ResourceLimit,
        "qwen3moe_encoded_allocation_too_large",
        "encoded slab exceeds the bounded allocation limit",
    )?;
    let mut encoded = vec![0_u8; encoded_length];
    let bytes_read = store.read_range(&catalog_tensor, &mut encoded, request.cancellation())?;
    request.cancellation.check()?;
    if bytes_read != encoded_length {
        let (code, message) = if bytes_read < encoded_length {
            (
                "qwen3moe_short_read",
                "the whole encoded tensor slab was not returned",
            )
        } else {
            (
                "qwen3moe_overlong_read",
                "the store returned more bytes than the admitted tensor slab",
            )
        };
        return Err(storage_error(ErrorCategory::InvalidTensor, code, message));
    }
    let data = decode_q8_0(&request.tensor, &encoded, request.cancellation())?;
    request.cancellation.check()?;
    let decoded_elements = u64::try_from(data.len()).map_err(|_| {
        storage_error(
            ErrorCategory::ArithmeticOverflow,
            "qwen3moe_decoded_element_count_overflow",
            "decoded element count cannot be represented as u64",
        )
    })?;
    let byte_length = checked_output_bytes(decoded_elements)?;
    let content_hash = Qwen3MoeContentHashMetadata {
        algorithm: QWEN3MOE_F32_HASH_ALGORITHM,
        sha256: hash_f32_le(&data),
    };
    request.cancellation.check()?;

    Ok(Qwen3MoEDecodedTensor {
        data,
        shape: request.tensor.execution_shape.clone(),
        byte_length,
        alignment: align_of::<f32>(),
        destination_policy: request.destination_policy,
        decoder_version: request.decoder_contract.version(),
        content_hash,
    })
}

fn validate_request_tensor(
    request: &Qwen3MoeStorageRequest,
) -> Result<RuntimeTensor, ContractError> {
    if request.decoder_contract != Qwen3MoeDecoderContract::q8_0() {
        return Err(storage_error(
            ErrorCategory::InvalidQuantization,
            "unsupported_decoder_contract",
            "the requested decoder contract is not admitted",
        ));
    }
    let tensor = &request.tensor;
    if tensor.gguf_type != "Q8_0" || tensor.quantization != "Q8_0" {
        return Err(storage_error(
            ErrorCategory::InvalidQuantization,
            "unsupported_qwen3moe_quantization",
            "only the exact admitted Q8_0 decoder lane is admitted",
        ));
    }
    if tensor.gguf_shape.is_empty() || tensor.gguf_shape.len() > MAX_SHAPE_RANK {
        return Err(storage_error(
            ErrorCategory::InvalidTensor,
            "invalid_qwen3moe_shape_rank",
            "tensor shape rank is outside the bounded decoder contract",
        ));
    }
    let logical_elements = checked_shape_product(&tensor.gguf_shape)?;
    if logical_elements != tensor.logical_elements {
        return Err(storage_error(
            ErrorCategory::InvalidTensor,
            "qwen3moe_logical_size_mismatch",
            "tensor logical element count differs from its checked shape",
        ));
    }
    if !request.production_slice && logical_elements > MAX_SYNTHETIC_DECODE_ELEMENTS {
        return Err(storage_error(
            ErrorCategory::ResourceLimit,
            "qwen3moe_decode_bound_exceeded",
            "tensor exceeds the bounded synthetic decode element limit",
        ));
    }
    let row_elements = tensor.gguf_shape[0];
    if row_elements == 0 || row_elements % QWEN3MOE_Q8_0_BLOCK_ELEMENTS != 0 {
        return Err(storage_error(
            ErrorCategory::InvalidQuantization,
            "qwen3moe_q8_0_block_shape_mismatch",
            "Q8_0 rows must contain a whole number of 32-value blocks",
        ));
    }
    let block_count = logical_elements
        .checked_div(QWEN3MOE_Q8_0_BLOCK_ELEMENTS)
        .ok_or_else(|| {
            storage_error(
                ErrorCategory::ArithmeticOverflow,
                "qwen3moe_block_count_overflow",
                "Q8_0 block count could not be computed",
            )
        })?;
    let expected_encoded_bytes = block_count
        .checked_mul(QWEN3MOE_Q8_0_BLOCK_BYTES)
        .ok_or_else(|| {
            storage_error(
                ErrorCategory::ArithmeticOverflow,
                "qwen3moe_encoded_size_overflow",
                "Q8_0 encoded byte count overflowed",
            )
        })?;
    if tensor.encoded_bytes != expected_encoded_bytes {
        return Err(storage_error(
            ErrorCategory::InvalidTensor,
            "qwen3moe_encoded_size_mismatch",
            "tensor encoded byte count does not match its Q8_0 shape",
        ));
    }
    if !request.production_slice && expected_encoded_bytes >= MAX_SYNTHETIC_ENCODED_BYTES {
        return Err(storage_error(
            ErrorCategory::ResourceLimit,
            "qwen3moe_synthetic_slab_bound_exceeded",
            "encoded slab exceeds the bounded synthetic storage limit",
        ));
    }
    let expected_reader_shape = q8_reader_shape(&tensor.gguf_shape)?;
    let expected_execution_shape = tensor.gguf_shape.iter().rev().copied().collect::<Vec<_>>();
    if tensor.reader_shape != expected_reader_shape
        || tensor.execution_shape != expected_execution_shape
    {
        return Err(storage_error(
            ErrorCategory::InvalidTensor,
            "qwen3moe_shape_layout_mismatch",
            "tensor reader or execution shape differs from its Q8_0 layout",
        ));
    }
    if request.production_slice && admitted_layer0_slice(&request.source_tensor)? != *tensor {
        return Err(storage_error(
            ErrorCategory::InvalidTensor,
            "qwen3moe_slice_not_admitted",
            "the production request is not the exact admitted layer-0 slice",
        ));
    }
    let range = TensorRange {
        offset: tensor.absolute_data_offset,
        length: tensor.encoded_bytes,
    };
    range.end()?;
    let output_bytes = checked_output_bytes(logical_elements)?;
    checked_usize(
        expected_encoded_bytes,
        ErrorCategory::ResourceLimit,
        "qwen3moe_encoded_allocation_too_large",
        "encoded slab exceeds the bounded allocation limit",
    )?;
    checked_usize(
        output_bytes,
        ErrorCategory::ResourceLimit,
        "qwen3moe_output_allocation_too_large",
        "decoded output exceeds the bounded allocation limit",
    )?;

    let admitted_checkpoint = CheckpointIdentity::try_new(QWEN3MOE_SHA256, QWEN3MOE_REVISION)?;
    if admitted_checkpoint != request.checkpoint {
        return Err(storage_error(
            ErrorCategory::InvalidModel,
            "qwen3moe_checkpoint_identity_mismatch",
            "checkpoint identity failed revalidation before storage",
        ));
    }

    Ok(RuntimeTensor {
        name: tensor.name.clone(),
        // The admitted Qwen descriptor supplies the symbolic shard identity;
        // no filesystem path enters this seam.
        shard: crate::qwen3moe::QWEN3MOE_FILENAME.to_owned(),
        range,
        shape: tensor.reader_shape.clone(),
        quantization: tensor.quantization.clone(),
    })
}

fn checked_shape_product(shape: &[u64]) -> Result<u64, ContractError> {
    shape.iter().try_fold(1_u64, |product, &dimension| {
        if dimension == 0 {
            return Err(storage_error(
                ErrorCategory::InvalidTensor,
                "qwen3moe_zero_shape_dimension",
                "tensor shape dimensions must be nonzero",
            ));
        }
        product.checked_mul(dimension).ok_or_else(|| {
            storage_error(
                ErrorCategory::ArithmeticOverflow,
                "qwen3moe_shape_product_overflow",
                "tensor shape product overflowed",
            )
        })
    })
}

fn q8_reader_shape(shape: &[u64]) -> Result<Vec<u64>, ContractError> {
    let row_blocks = shape[0]
        .checked_div(QWEN3MOE_Q8_0_BLOCK_ELEMENTS)
        .ok_or_else(|| {
            storage_error(
                ErrorCategory::ArithmeticOverflow,
                "qwen3moe_row_block_overflow",
                "Q8_0 row block count could not be computed",
            )
        })?;
    let row_bytes = row_blocks
        .checked_mul(QWEN3MOE_Q8_0_BLOCK_BYTES)
        .ok_or_else(|| {
            storage_error(
                ErrorCategory::ArithmeticOverflow,
                "qwen3moe_row_bytes_overflow",
                "Q8_0 row byte count overflowed",
            )
        })?;
    let mut reader_shape = shape[1..].iter().rev().copied().collect::<Vec<_>>();
    reader_shape.push(row_bytes);
    Ok(reader_shape)
}

fn checked_output_bytes(elements: u64) -> Result<u64, ContractError> {
    elements
        .checked_mul(size_of::<f32>() as u64)
        .ok_or_else(|| {
            storage_error(
                ErrorCategory::ArithmeticOverflow,
                "qwen3moe_output_size_overflow",
                "decoded f32 output byte count overflowed",
            )
        })
}

fn checked_usize(
    value: u64,
    category: ErrorCategory,
    code: &'static str,
    message: &'static str,
) -> Result<usize, ContractError> {
    usize::try_from(value).map_err(|_| storage_error(category, code, message))
}

fn decode_q8_0(
    tensor: &Qwen3MoeTensorDescriptor,
    encoded: &[u8],
    cancellation: &CancellationToken,
) -> Result<Vec<f32>, ContractError> {
    let output_elements = usize::try_from(tensor.logical_elements).map_err(|_| {
        storage_error(
            ErrorCategory::ResourceLimit,
            "qwen3moe_output_allocation_too_large",
            "decoded output exceeds the bounded allocation limit",
        )
    })?;
    let expected_bytes = output_elements
        .checked_div(QWEN3MOE_Q8_0_BLOCK_ELEMENTS as usize)
        .and_then(|blocks| blocks.checked_mul(QWEN3MOE_Q8_0_BLOCK_BYTES as usize))
        .ok_or_else(|| {
            storage_error(
                ErrorCategory::ArithmeticOverflow,
                "qwen3moe_decode_size_overflow",
                "decoded Q8_0 block arithmetic overflowed",
            )
        })?;
    if encoded.len() != expected_bytes {
        return Err(storage_error(
            ErrorCategory::InvalidTensor,
            "qwen3moe_encoded_length_mismatch",
            "encoded Q8_0 bytes do not cover the complete tensor slab",
        ));
    }

    let block_count = output_elements / QWEN3MOE_Q8_0_BLOCK_ELEMENTS as usize;
    let mut output = Vec::with_capacity(output_elements);
    for (block_index, block) in encoded
        .chunks_exact(QWEN3MOE_Q8_0_BLOCK_BYTES as usize)
        .enumerate()
    {
        if block_index % DECODE_CHUNK_BLOCKS == 0 {
            cancellation.check()?;
        }
        let scale_bits = u16::from_le_bytes([block[0], block[1]]);
        let scale = f16_to_f32(scale_bits)?;
        for byte in &block[2..] {
            let quantized = i8::from_le_bytes([*byte]);
            let value = scale * f32::from(quantized);
            if !value.is_finite() {
                return Err(storage_error(
                    ErrorCategory::InvalidQuantization,
                    "qwen3moe_non_finite_decoded_value",
                    "Q8_0 decoding produced a non-finite f32 value",
                ));
            }
            output.push(value);
        }
        if (block_index + 1) % DECODE_CHUNK_BLOCKS == 0 || block_index + 1 == block_count {
            cancellation.check()?;
        }
    }
    if output.len() != output_elements {
        return Err(storage_error(
            ErrorCategory::InvalidTensor,
            "qwen3moe_decoded_length_mismatch",
            "decoded Q8_0 element count differs from the admitted shape",
        ));
    }
    Ok(output)
}

fn f16_to_f32(bits: u16) -> Result<f32, ContractError> {
    let sign = (u32::from(bits & 0x8000)) << 16;
    let exponent = (bits >> 10) & 0x1f;
    let fraction = bits & 0x03ff;
    if exponent == 0x1f {
        return Err(storage_error(
            ErrorCategory::InvalidQuantization,
            "qwen3moe_non_finite_scale",
            "Q8_0 scale metadata must be finite",
        ));
    }
    let f32_bits = if exponent == 0 {
        if fraction == 0 {
            sign
        } else {
            let highest_bit = 15 - fraction.leading_zeros() as u32;
            let exponent = (127 - 24 + highest_bit) << 23;
            let mantissa = (u32::from(fraction) - (1 << highest_bit)) << (23 - highest_bit);
            sign | exponent | mantissa
        }
    } else {
        sign | ((u32::from(exponent) + 112) << 23) | (u32::from(fraction) << 13)
    };
    Ok(f32::from_bits(f32_bits))
}

fn hash_f32_le(values: &[f32]) -> String {
    let mut hasher = Sha256::new();
    for value in values {
        hasher.update(value.to_bits().to_le_bytes());
    }
    let digest = hasher.finalize();
    digest.iter().map(|byte| format!("{byte:02x}")).collect()
}

fn validate_correlation_id(value: &str) -> Result<(), ContractError> {
    if value.is_empty()
        || value.chars().count() > MAX_CORRELATION_ID_CHARS
        || !value.chars().all(|character| {
            character.is_ascii_alphanumeric() || matches!(character, '.' | '-' | '_' | '/')
        })
    {
        return Err(storage_error(
            ErrorCategory::InvalidModel,
            "invalid_qwen3moe_correlation_id",
            "correlation identifier is empty or malformed",
        ));
    }
    Ok(())
}

fn validate_destination_policy(policy: Qwen3MoeDestinationPolicy) -> Result<(), ContractError> {
    if policy != Qwen3MoeDestinationPolicy::RustOwned {
        return Err(storage_error(
            ErrorCategory::InvalidCapability,
            "unsupported_qwen3moe_destination_policy",
            "caller-owned Qwen3MoE destinations are not admitted by this lane",
        ));
    }
    Ok(())
}

fn storage_error(
    category: ErrorCategory,
    code: &'static str,
    message: &'static str,
) -> ContractError {
    ContractError::new(category, code, message)
}

#[cfg(test)]
#[path = "qwen3moe_storage_external_tests.rs"]
mod external_storage_tests;
#[cfg(test)]
mod tests {
    use super::*;
    use crate::qwen3moe::{
        Qwen3MoeArtifactBinding, Qwen3MoeGraphDescriptor, Qwen3MoeMetadata, Qwen3MoeTensorBinding,
        QWEN3MOE_FILENAME, QWEN3MOE_FILE_BYTES, QWEN3MOE_REPOSITORY_ID, QWEN3MOE_REVISION,
        QWEN3MOE_SHA256,
    };
    use std::sync::atomic::{AtomicUsize, Ordering};
    use std::sync::Arc;

    const OFFSET: u64 = 5_969_408;

    #[derive(Clone)]
    struct FixtureCatalog {
        tensor: RuntimeTensor,
        lookups: Arc<AtomicUsize>,
    }

    impl TensorCatalog for FixtureCatalog {
        fn tensor(&self, name: &str) -> Result<Option<RuntimeTensor>, ContractError> {
            self.lookups.fetch_add(1, Ordering::AcqRel);
            Ok((name == self.tensor.name).then(|| self.tensor.clone()))
        }
    }

    struct FixtureStore {
        encoded: Vec<u8>,
        reads: Arc<AtomicUsize>,
        cancel_after_read: Option<CancellationToken>,
        reported_length: Option<usize>,
    }

    impl TensorStore for FixtureStore {
        fn read_range(
            &self,
            _tensor: &RuntimeTensor,
            destination: &mut [u8],
            _cancellation: &CancellationToken,
        ) -> Result<usize, ContractError> {
            self.reads.fetch_add(1, Ordering::AcqRel);
            destination[..self.encoded.len()].copy_from_slice(&self.encoded);
            if let Some(token) = &self.cancel_after_read {
                token.cancel();
            }
            Ok(self.reported_length.unwrap_or(self.encoded.len()))
        }
    }

    fn descriptor(shape: Vec<u64>, encoded_bytes: u64) -> Qwen3MoeFullGraphDescriptor {
        let binding = Qwen3MoeTensorBinding {
            role: Qwen3MoeTensorRole::ExpertGateWeight,
            layer_index: Some(0),
            tensor_name: "synthetic.blk.0.ffn_gate_exps.weight".to_owned(),
        };
        let tensor = Qwen3MoeTensorDescriptor {
            role: binding.role,
            layer_index: binding.layer_index,
            name: binding.tensor_name.clone(),
            reader_shape: {
                let mut reader_shape = shape[1..].iter().rev().copied().collect::<Vec<_>>();
                reader_shape
                    .push((shape[0] / QWEN3MOE_Q8_0_BLOCK_ELEMENTS) * QWEN3MOE_Q8_0_BLOCK_BYTES);
                reader_shape
            },
            execution_shape: shape.iter().rev().copied().collect(),
            gguf_shape: shape.clone(),
            gguf_type: "Q8_0".to_owned(),
            quantization: "Q8_0".to_owned(),
            orientation: "synthetic".to_owned(),
            logical_elements: shape.iter().product(),
            encoded_bytes,
            absolute_data_offset: OFFSET,
        };
        Qwen3MoeFullGraphDescriptor::new_synthetic_for_test(
            QWEN3MOE_FULL_GRAPH_CONTRACT_ID.to_owned(),
            Qwen3MoeArtifactBinding {
                repository_id: QWEN3MOE_REPOSITORY_ID.to_owned(),
                revision: QWEN3MOE_REVISION.to_owned(),
                filename: QWEN3MOE_FILENAME.to_owned(),
                size_bytes: QWEN3MOE_FILE_BYTES,
                sha256: QWEN3MOE_SHA256.to_owned(),
            },
            Qwen3MoeMetadata {
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
            vec![tensor],
            Qwen3MoeGraphDescriptor {
                token_embedding: binding.clone(),
                layers: Vec::new(),
                final_norm: binding.clone(),
                output_projection: binding,
            },
        )
    }

    fn q8_block(scale: u16, values: &[i8]) -> Vec<u8> {
        assert_eq!(values.len(), QWEN3MOE_Q8_0_BLOCK_ELEMENTS as usize);
        let mut block = scale.to_le_bytes().to_vec();
        block.extend(values.iter().map(|value| value.to_le_bytes()[0]));
        block
    }

    fn request(
        descriptor: &Qwen3MoeFullGraphDescriptor,
        cancellation: CancellationToken,
    ) -> Qwen3MoeStorageRequest {
        Qwen3MoeStorageRequest::try_new_synthetic_for_test(
            descriptor,
            Qwen3MoeTensorRole::ExpertGateWeight,
            Some(0),
            Qwen3MoeDestinationPolicy::RustOwned,
            Qwen3MoeDecoderContract::q8_0(),
            "synthetic-q8-0",
            cancellation,
        )
        .unwrap()
    }

    fn catalog() -> FixtureCatalog {
        FixtureCatalog {
            tensor: RuntimeTensor {
                name: "synthetic.blk.0.ffn_gate_exps.weight".to_owned(),
                shard: QWEN3MOE_FILENAME.to_owned(),
                range: TensorRange {
                    offset: OFFSET,
                    length: 34,
                },
                shape: vec![34],
                quantization: "Q8_0".to_owned(),
            },
            lookups: Arc::new(AtomicUsize::new(0)),
        }
    }

    #[test]
    fn exact_q8_0_decode_preserves_values_and_signed_zero() {
        let descriptor = descriptor(vec![64], 68);
        let cancellation = CancellationToken::new();
        let request = request(&descriptor, cancellation.clone());
        let catalog = FixtureCatalog {
            tensor: RuntimeTensor {
                range: TensorRange {
                    offset: OFFSET,
                    length: 68,
                },
                shape: vec![68],
                ..catalog().tensor
            },
            ..catalog()
        };
        let mut encoded = q8_block(
            0x3c00,
            &[
                0, 1, -1, 127, -128, 2, -2, 3, -3, 4, -4, 5, -5, 6, -6, 7, -7, 8, -8, 9, -9, 10,
                -10, 11, -11, 12, -12, 13, -13, 14, -14, 15,
            ],
        );
        encoded.extend(q8_block(0x8000, &[0; 32]));
        let store = FixtureStore {
            encoded,
            reads: Arc::new(AtomicUsize::new(0)),
            cancel_after_read: None,
            reported_length: None,
        };

        let result = decode_qwen3moe_tensor(&request, &catalog, &store).unwrap();
        assert_eq!(result.data()[0].to_bits(), 0);
        assert_eq!(result.data()[1].to_bits(), 1.0_f32.to_bits());
        assert_eq!(result.data()[2].to_bits(), (-1.0_f32).to_bits());
        assert_eq!(result.data()[3].to_bits(), 127.0_f32.to_bits());
        assert_eq!(result.data()[4].to_bits(), (-128.0_f32).to_bits());
        assert_eq!(result.data()[32 + 0].to_bits(), 0x8000_0000);
        assert_eq!(result.data().len(), 64);
        assert_eq!(result.shape(), [64]);
        assert_eq!(result.byte_length(), 64 * 4);
        assert_eq!(result.alignment(), align_of::<f32>());
        assert_eq!(
            result.destination_policy(),
            Qwen3MoeDestinationPolicy::RustOwned
        );
        assert_eq!(result.decoder_version(), QWEN3MOE_Q8_0_DECODER_VERSION);
        assert_eq!(
            result.content_hash().algorithm(),
            QWEN3MOE_F32_HASH_ALGORITHM
        );
        assert_eq!((result.data().as_ptr() as usize) % result.alignment(), 0);
        assert_eq!(
            result.content_sha256(),
            "ec80aebc6d51aa564b3ddf7f37845105ad576b3cfa5e8eaca2fa286e10e6194d"
        );
        assert_eq!(store.reads.load(Ordering::Acquire), 1);
    }

    #[test]
    fn decoder_contract_is_explicit_and_unsupported_versions_fail_closed() {
        let contract = Qwen3MoeDecoderContract::try_new(
            QWEN3MOE_Q8_0_DECODER_CONTRACT_ID,
            QWEN3MOE_Q8_0_DECODER_VERSION,
        )
        .unwrap();
        assert_eq!(contract, Qwen3MoeDecoderContract::q8_0());
        assert_eq!(
            Qwen3MoeDecoderContract::try_new("qwen3moe-q8_0-f32", "v2")
                .unwrap_err()
                .code(),
            "unsupported_decoder_contract"
        );
    }

    #[test]
    fn catalog_entry_is_revalidated_before_the_store_read() {
        for (mutation, expected_code) in [
            (
                Box::new(|tensor: &mut RuntimeTensor| tensor.shard = "other-shard".to_owned())
                    as Box<dyn Fn(&mut RuntimeTensor)>,
                "qwen3moe_catalog_identity_mismatch",
            ),
            (
                Box::new(|tensor: &mut RuntimeTensor| tensor.range.length = 36)
                    as Box<dyn Fn(&mut RuntimeTensor)>,
                "qwen3moe_catalog_identity_mismatch",
            ),
            (
                Box::new(|tensor: &mut RuntimeTensor| tensor.shape = vec![1, 34])
                    as Box<dyn Fn(&mut RuntimeTensor)>,
                "qwen3moe_catalog_identity_mismatch",
            ),
            (
                Box::new(|tensor: &mut RuntimeTensor| tensor.quantization = "Q4_K".to_owned())
                    as Box<dyn Fn(&mut RuntimeTensor)>,
                "qwen3moe_catalog_identity_mismatch",
            ),
            (
                Box::new(|tensor: &mut RuntimeTensor| tensor.name = "other.tensor".to_owned())
                    as Box<dyn Fn(&mut RuntimeTensor)>,
                "qwen3moe_catalog_entry_missing",
            ),
        ] {
            let descriptor = descriptor(vec![32], 34);
            let cancellation = CancellationToken::new();
            let request = request(&descriptor, cancellation);
            let mut catalog = catalog();
            mutation(&mut catalog.tensor);
            let reads = Arc::new(AtomicUsize::new(0));
            let store = FixtureStore {
                encoded: q8_block(0x3c00, &[1; 32]),
                reads: reads.clone(),
                cancel_after_read: None,
                reported_length: None,
            };
            let error = decode_qwen3moe_tensor(&request, &catalog, &store).unwrap_err();
            assert_eq!(error.code(), expected_code);
            assert_eq!(reads.load(Ordering::Acquire), 0);
        }
    }

    #[test]
    fn short_overlong_and_malformed_slabs_fail_without_a_result() {
        let descriptor = descriptor(vec![32], 34);
        for (reported_length, bytes, expected_code) in [
            (Some(33), q8_block(0x3c00, &[1; 32]), "qwen3moe_short_read"),
            (
                Some(35),
                q8_block(0x3c00, &[1; 32]),
                "qwen3moe_overlong_read",
            ),
            (
                None,
                q8_block(0x7c00, &[1; 32]),
                "qwen3moe_non_finite_scale",
            ),
        ] {
            let cancellation = CancellationToken::new();
            let request = request(&descriptor, cancellation);
            let store = FixtureStore {
                encoded: bytes,
                reads: Arc::new(AtomicUsize::new(0)),
                cancel_after_read: None,
                reported_length,
            };
            assert_eq!(
                decode_qwen3moe_tensor(&request, &catalog(), &store)
                    .unwrap_err()
                    .code(),
                expected_code
            );
        }
    }

    #[test]
    fn unsupported_shape_quantization_and_arithmetic_fail_closed() {
        let mut unsupported = descriptor(vec![32], 34);
        unsupported.tensors[0].quantization = "Q4_K".to_owned();
        unsupported.tensors[0].gguf_type = "Q4_K".to_owned();
        let unsupported_request = request(&unsupported, CancellationToken::new());
        let store = FixtureStore {
            encoded: q8_block(0x3c00, &[1; 32]),
            reads: Arc::new(AtomicUsize::new(0)),
            cancel_after_read: None,
            reported_length: None,
        };
        assert_eq!(
            decode_qwen3moe_tensor(&unsupported_request, &catalog(), &store)
                .unwrap_err()
                .code(),
            "unsupported_qwen3moe_quantization"
        );

        let invalid_shape = descriptor(vec![31], 34);
        let invalid_shape_request = request(&invalid_shape, CancellationToken::new());
        assert_eq!(
            decode_qwen3moe_tensor(&invalid_shape_request, &catalog(), &store)
                .unwrap_err()
                .code(),
            "qwen3moe_q8_0_block_shape_mismatch"
        );

        let mut encoded_size = descriptor(vec![64], 34);
        encoded_size.tensors[0].reader_shape = vec![34];
        let encoded_size_request = request(&encoded_size, CancellationToken::new());
        assert_eq!(
            decode_qwen3moe_tensor(&encoded_size_request, &catalog(), &store)
                .unwrap_err()
                .code(),
            "qwen3moe_encoded_size_mismatch"
        );

        let mut shape_overflow = descriptor(vec![32], 34);
        shape_overflow.tensors[0].gguf_shape = vec![u64::MAX, 32];
        let shape_overflow_request = request(&shape_overflow, CancellationToken::new());
        assert_eq!(
            decode_qwen3moe_tensor(&shape_overflow_request, &catalog(), &store)
                .unwrap_err()
                .code(),
            "qwen3moe_shape_product_overflow"
        );

        let overflow = descriptor(vec![32], 34);
        let mut overflow_descriptor = overflow;
        overflow_descriptor.tensors[0].absolute_data_offset = u64::MAX;
        let overflow_request = request(&overflow_descriptor, CancellationToken::new());
        assert_eq!(
            decode_qwen3moe_tensor(&overflow_request, &catalog(), &store)
                .unwrap_err()
                .code(),
            "tensor_range_overflow"
        );
    }

    #[test]
    fn synthetic_encoded_slab_is_bounded_before_allocation_or_store_read() {
        let encoded_bytes = 31_000 * QWEN3MOE_Q8_0_BLOCK_BYTES;
        let descriptor = descriptor(vec![32 * 31_000], encoded_bytes);
        let request = request(&descriptor, CancellationToken::new());
        let mut catalog = catalog();
        catalog.tensor.range.length = encoded_bytes;
        catalog.tensor.shape = vec![encoded_bytes];
        let reads = Arc::new(AtomicUsize::new(0));
        let store = FixtureStore {
            encoded: Vec::new(),
            reads: reads.clone(),
            cancel_after_read: None,
            reported_length: None,
        };

        let error = decode_qwen3moe_tensor(&request, &catalog, &store).unwrap_err();

        assert_eq!(error.code(), "qwen3moe_synthetic_slab_bound_exceeded");
        assert_eq!(reads.load(Ordering::Acquire), 0);
    }

    #[test]
    fn cancellation_is_checked_before_and_after_read_and_no_partial_output_escapes() {
        let descriptor = descriptor(vec![32], 34);
        let before = CancellationToken::new();
        before.cancel();
        let reads = Arc::new(AtomicUsize::new(0));
        let store = FixtureStore {
            encoded: q8_block(0x3c00, &[1; 32]),
            reads: reads.clone(),
            cancel_after_read: None,
            reported_length: None,
        };
        assert_eq!(
            decode_qwen3moe_tensor(&request(&descriptor, before), &catalog(), &store)
                .unwrap_err()
                .code(),
            "cancelled"
        );
        assert_eq!(reads.load(Ordering::Acquire), 0);

        let after = CancellationToken::new();
        let store = FixtureStore {
            encoded: q8_block(0x3c00, &[1; 32]),
            reads: Arc::new(AtomicUsize::new(0)),
            cancel_after_read: Some(after.clone()),
            reported_length: None,
        };
        assert_eq!(
            decode_qwen3moe_tensor(&request(&descriptor, after), &catalog(), &store)
                .unwrap_err()
                .code(),
            "cancelled"
        );

        for reported_length in [Some(33), Some(35)] {
            let cancellation = CancellationToken::new();
            let reads = Arc::new(AtomicUsize::new(0));
            let store = FixtureStore {
                encoded: q8_block(0x3c00, &[1; 32]),
                reads: reads.clone(),
                cancel_after_read: Some(cancellation.clone()),
                reported_length,
            };
            let error =
                decode_qwen3moe_tensor(&request(&descriptor, cancellation), &catalog(), &store)
                    .unwrap_err();
            assert_eq!(error.code(), "cancelled");
            assert_eq!(reads.load(Ordering::Acquire), 1);
        }
    }

    #[test]
    fn request_is_bound_to_checkpoint_and_admitted_tensor_without_free_form_name() {
        let descriptor = descriptor(vec![32], 34);
        let request = request(&descriptor, CancellationToken::new());
        assert_eq!(request.checkpoint().checkpoint_set_sha256, QWEN3MOE_SHA256);
        assert_eq!(request.checkpoint().immutable_revision, QWEN3MOE_REVISION);
        assert_eq!(
            request.tensor().name,
            "synthetic.blk.0.ffn_gate_exps.weight"
        );
        assert_eq!(request.correlation_id(), "synthetic-q8-0");
        assert_eq!(
            request.destination_policy(),
            Qwen3MoeDestinationPolicy::RustOwned
        );
    }

    #[test]
    fn caller_owned_destination_is_rejected_before_descriptor_admission() {
        let descriptor = descriptor(vec![32], 34);
        let error = Qwen3MoeStorageRequest::try_new(
            &descriptor,
            Qwen3MoeTensorRole::ExpertGateWeight,
            Some(0),
            Qwen3MoeDestinationPolicy::CallerOwned,
            Qwen3MoeDecoderContract::q8_0(),
            "synthetic-q8-0",
            CancellationToken::new(),
        )
        .expect_err("caller-owned storage is not admitted in this lane");
        assert_eq!(error.code(), "unsupported_qwen3moe_destination_policy");

        let error = Qwen3MoeStorageRequest::try_new(
            &descriptor,
            Qwen3MoeTensorRole::ExpertGateWeight,
            Some(0),
            Qwen3MoeDestinationPolicy::RustOwned,
            Qwen3MoeDecoderContract::q8_0(),
            "synthetic-q8-0",
            CancellationToken::new(),
        )
        .expect_err("synthetic fixtures cannot cross the production admission boundary");
        assert_eq!(error.code(), "unexpected_tensor_role");
    }

    #[test]
    fn every_public_full_graph_identity_mutation_is_rejected_at_request_boundary() {
        let mutations: Vec<(&str, Box<dyn Fn(&mut Qwen3MoeFullGraphDescriptor)>)> = vec![
            (
                "contract",
                Box::new(|descriptor| descriptor.contract_id = "forged".to_owned()),
            ),
            (
                "artifact repository",
                Box::new(|descriptor| descriptor.artifact.repository_id = "forged/repo".to_owned()),
            ),
            (
                "artifact revision",
                Box::new(|descriptor| descriptor.artifact.revision = "forged-revision".to_owned()),
            ),
            (
                "artifact filename",
                Box::new(|descriptor| descriptor.artifact.filename = "forged.gguf".to_owned()),
            ),
            (
                "artifact size",
                Box::new(|descriptor| descriptor.artifact.size_bytes += 1),
            ),
            (
                "artifact checksum",
                Box::new(|descriptor| descriptor.artifact.sha256.replace_range(..1, "0")),
            ),
            (
                "metadata architecture",
                Box::new(|descriptor| descriptor.metadata.architecture = "forged".to_owned()),
            ),
            (
                "metadata hidden width",
                Box::new(|descriptor| descriptor.metadata.hidden_width += 1),
            ),
            (
                "metadata layer count",
                Box::new(|descriptor| descriptor.metadata.layer_count -= 1),
            ),
            (
                "metadata expert count",
                Box::new(|descriptor| descriptor.metadata.expert_count -= 1),
            ),
            (
                "metadata top k",
                Box::new(|descriptor| descriptor.metadata.top_k -= 1),
            ),
            (
                "metadata expert ffn width",
                Box::new(|descriptor| descriptor.metadata.expert_ffn_width += 1),
            ),
            (
                "metadata attention heads",
                Box::new(|descriptor| descriptor.metadata.attention_head_count += 1),
            ),
            (
                "metadata kv heads",
                Box::new(|descriptor| descriptor.metadata.attention_head_count_kv += 1),
            ),
            (
                "metadata key length",
                Box::new(|descriptor| descriptor.metadata.key_length += 1),
            ),
            (
                "metadata value length",
                Box::new(|descriptor| descriptor.metadata.value_length += 1),
            ),
            (
                "metadata feed forward width",
                Box::new(|descriptor| descriptor.metadata.feed_forward_width += 1),
            ),
            (
                "metadata context length",
                Box::new(|descriptor| descriptor.metadata.context_length += 1),
            ),
            (
                "tensor role",
                Box::new(|descriptor| {
                    descriptor.tensors[0].role = Qwen3MoeTensorRole::RouterWeight
                }),
            ),
            (
                "tensor layer",
                Box::new(|descriptor| descriptor.tensors[0].layer_index = Some(1)),
            ),
            (
                "tensor name",
                Box::new(|descriptor| descriptor.tensors[0].name = "forged.tensor".to_owned()),
            ),
            (
                "tensor gguf shape",
                Box::new(|descriptor| descriptor.tensors[0].gguf_shape[0] = 64),
            ),
            (
                "tensor reader shape",
                Box::new(|descriptor| descriptor.tensors[0].reader_shape[0] = 64),
            ),
            (
                "tensor execution shape",
                Box::new(|descriptor| descriptor.tensors[0].execution_shape[0] = 64),
            ),
            (
                "tensor gguf type",
                Box::new(|descriptor| descriptor.tensors[0].gguf_type = "Q4_K".to_owned()),
            ),
            (
                "tensor quantization",
                Box::new(|descriptor| descriptor.tensors[0].quantization = "Q4_K".to_owned()),
            ),
            (
                "tensor orientation",
                Box::new(|descriptor| descriptor.tensors[0].orientation = "forged".to_owned()),
            ),
            (
                "tensor logical elements",
                Box::new(|descriptor| descriptor.tensors[0].logical_elements += 1),
            ),
            (
                "tensor encoded bytes",
                Box::new(|descriptor| descriptor.tensors[0].encoded_bytes += 1),
            ),
            (
                "tensor data offset",
                Box::new(|descriptor| descriptor.tensors[0].absolute_data_offset += 1),
            ),
            (
                "graph token role",
                Box::new(|descriptor| {
                    descriptor.graph.token_embedding.role = Qwen3MoeTensorRole::RouterWeight
                }),
            ),
            (
                "graph token layer",
                Box::new(|descriptor| descriptor.graph.token_embedding.layer_index = None),
            ),
            (
                "graph token name",
                Box::new(|descriptor| {
                    descriptor.graph.token_embedding.tensor_name = "forged.tensor".to_owned()
                }),
            ),
            (
                "graph final norm role",
                Box::new(|descriptor| {
                    descriptor.graph.final_norm.role = Qwen3MoeTensorRole::RouterWeight
                }),
            ),
            (
                "graph final norm layer",
                Box::new(|descriptor| descriptor.graph.final_norm.layer_index = None),
            ),
            (
                "graph final norm name",
                Box::new(|descriptor| {
                    descriptor.graph.final_norm.tensor_name = "forged.tensor".to_owned()
                }),
            ),
            (
                "graph output role",
                Box::new(|descriptor| {
                    descriptor.graph.output_projection.role = Qwen3MoeTensorRole::RouterWeight
                }),
            ),
            (
                "graph output layer",
                Box::new(|descriptor| descriptor.graph.output_projection.layer_index = None),
            ),
            (
                "graph output name",
                Box::new(|descriptor| {
                    descriptor.graph.output_projection.tensor_name = "forged.tensor".to_owned()
                }),
            ),
            (
                "graph layers",
                Box::new(|descriptor| {
                    descriptor
                        .graph
                        .layers
                        .push(crate::qwen3moe::Qwen3MoeLayerGraphDescriptor {
                            layer_index: 0,
                            nodes: Vec::new(),
                        })
                }),
            ),
        ];

        for (label, mutation) in mutations {
            let mut descriptor = descriptor(vec![32], 34);
            mutation(&mut descriptor);
            let error = Qwen3MoeStorageRequest::try_new(
                &descriptor,
                Qwen3MoeTensorRole::ExpertGateWeight,
                Some(0),
                Qwen3MoeDestinationPolicy::RustOwned,
                Qwen3MoeDecoderContract::q8_0(),
                "synthetic-q8-0",
                CancellationToken::new(),
            )
            .unwrap_err();
            assert_eq!(
                error.code(),
                "full_graph_admission_proof_mismatch",
                "{label}"
            );
        }
    }
}
