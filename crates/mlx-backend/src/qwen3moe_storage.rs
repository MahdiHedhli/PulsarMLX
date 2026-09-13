//! Bounded, source-free Qwen3MoE storage and exact f32 decode seam.
//!
//! The public API consumes an already-admitted Qwen3MoE graph descriptor and
//! backend-neutral catalog/store contracts. It performs one whole-slab read of
//! a tiny, exact Q8_0 lane; it does not open paths, access model payloads, or
//! provide a fallback decoder.

use backend::{
    CancellationToken, CheckpointIdentity, ContractError, ErrorCategory, RuntimeTensor,
    TensorCatalog, TensorRange, TensorStore,
};
use sha2::{Digest, Sha256};
use std::mem::{align_of, size_of};

use crate::qwen3moe::{
    Qwen3MoeFullGraphDescriptor, Qwen3MoeTensorDescriptor, Qwen3MoeTensorRole, QWEN3MOE_FILENAME,
    QWEN3MOE_FILE_BYTES, QWEN3MOE_FULL_GRAPH_CONTRACT_ID, QWEN3MOE_REPOSITORY_ID,
    QWEN3MOE_REVISION, QWEN3MOE_SHA256,
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

/// Immutable storage/decode request derived from one retained admitted tensor.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Qwen3MoeStorageRequest {
    checkpoint: CheckpointIdentity,
    tensor: Qwen3MoeTensorDescriptor,
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
    pub fn try_new(
        descriptor: &Qwen3MoeFullGraphDescriptor,
        role: Qwen3MoeTensorRole,
        layer_index: Option<u32>,
        decoder_contract: Qwen3MoeDecoderContract,
        correlation_id: impl Into<String>,
        cancellation: CancellationToken,
    ) -> Result<Self, ContractError> {
        if descriptor.contract_id != QWEN3MOE_FULL_GRAPH_CONTRACT_ID {
            return Err(storage_error(
                ErrorCategory::InvalidModel,
                "qwen3moe_graph_contract_mismatch",
                "storage requires the admitted Qwen3MoE full-graph contract",
            ));
        }
        if descriptor.artifact.repository_id != QWEN3MOE_REPOSITORY_ID
            || descriptor.artifact.revision != QWEN3MOE_REVISION
            || descriptor.artifact.filename != QWEN3MOE_FILENAME
            || descriptor.artifact.size_bytes != QWEN3MOE_FILE_BYTES
            || descriptor.artifact.sha256 != QWEN3MOE_SHA256
        {
            return Err(storage_error(
                ErrorCategory::InvalidModel,
                "qwen3moe_artifact_identity_mismatch",
                "storage requires the exact admitted Qwen3MoE artifact identity",
            ));
        }
        let tensor = descriptor
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
        let checkpoint = CheckpointIdentity::try_new(
            descriptor.artifact.sha256.clone(),
            descriptor.artifact.revision.clone(),
        )?;
        let correlation_id = correlation_id.into();
        validate_correlation_id(&correlation_id)?;

        Ok(Self {
            checkpoint,
            tensor,
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

    pub const fn decoder_contract(&self) -> Qwen3MoeDecoderContract {
        self.decoder_contract
    }

    pub fn correlation_id(&self) -> &str {
        &self.correlation_id
    }

    pub fn cancellation(&self) -> &CancellationToken {
        &self.cancellation
    }
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
pub fn decode_qwen3moe_tensor<C: TensorCatalog, S: TensorStore>(
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
    request.cancellation.check()?;

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
            "only the exact Q8_0 synthetic decoder lane is admitted",
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
    if logical_elements > MAX_SYNTHETIC_DECODE_ELEMENTS {
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

fn storage_error(
    category: ErrorCategory,
    code: &'static str,
    message: &'static str,
) -> ContractError {
    ContractError::new(category, code, message)
}

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
        Qwen3MoeFullGraphDescriptor {
            contract_id: QWEN3MOE_FULL_GRAPH_CONTRACT_ID.to_owned(),
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
            tensors: vec![tensor],
            graph: Qwen3MoeGraphDescriptor {
                token_embedding: binding.clone(),
                layers: Vec::new(),
                final_norm: binding.clone(),
                output_projection: binding,
            },
        }
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
        Qwen3MoeStorageRequest::try_new(
            descriptor,
            Qwen3MoeTensorRole::ExpertGateWeight,
            Some(0),
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
        assert_eq!(result.decoder_version(), QWEN3MOE_Q8_0_DECODER_VERSION);
        assert_eq!(
            result.content_hash().algorithm(),
            QWEN3MOE_F32_HASH_ALGORITHM
        );
        assert_eq!((result.data().as_ptr() as usize) % result.alignment(), 0);
        assert_eq!(result.content_sha256().len(), 64);
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
    }
}
