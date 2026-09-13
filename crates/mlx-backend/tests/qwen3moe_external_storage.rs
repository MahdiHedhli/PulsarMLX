use backend::{CancellationToken, ContractError, RuntimeTensor, TensorCatalog, TensorStore};
use mlx_backend::{
    decode_qwen3moe_tensor, read_admitted_tensor, ExternalModelInspection, Qwen3MoeDecoderContract,
    Qwen3MoeDestinationPolicy, Qwen3MoeExternalStorage, Qwen3MoeFullGraphDescriptor,
    Qwen3MoeGraphDescriptor, Qwen3MoeStorageRequest, Qwen3MoeTensorBinding,
    Qwen3MoeTensorDescriptor, Qwen3MoeTensorRole, QWEN3MOE_ADAPTER_CONTRACT_ID, QWEN3MOE_FILENAME,
    QWEN3MOE_FILE_BYTES, QWEN3MOE_FULL_GRAPH_CONTRACT_ID, QWEN3MOE_Q8_0_BLOCK_BYTES,
    QWEN3MOE_Q8_0_BLOCK_ELEMENTS, QWEN3MOE_REPOSITORY_ID, QWEN3MOE_REVISION, QWEN3MOE_SHA256,
};
use std::fs::{self, File, OpenOptions};
use std::io::{Seek, SeekFrom, Write};
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};

const DATA_OFFSET: u64 = 4_096;
static FIXTURE_NONCE: AtomicU64 = AtomicU64::new(0);

struct EphemeralFile {
    path: PathBuf,
    file: File,
}

impl Drop for EphemeralFile {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.path);
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
        reader_shape: vec![encoded_bytes],
        execution_shape: shape.clone(),
        gguf_shape: shape.clone(),
        gguf_type: "Q8_0".to_owned(),
        quantization: "Q8_0".to_owned(),
        orientation: "synthetic".to_owned(),
        logical_elements: shape.iter().product(),
        encoded_bytes,
        absolute_data_offset: DATA_OFFSET,
    };
    Qwen3MoeFullGraphDescriptor::new_synthetic_for_test(
        QWEN3MOE_FULL_GRAPH_CONTRACT_ID.to_owned(),
        mlx_backend::Qwen3MoeArtifactBinding {
            repository_id: QWEN3MOE_REPOSITORY_ID.to_owned(),
            revision: QWEN3MOE_REVISION.to_owned(),
            filename: QWEN3MOE_FILENAME.to_owned(),
            size_bytes: QWEN3MOE_FILE_BYTES,
            sha256: QWEN3MOE_SHA256.to_owned(),
        },
        mlx_backend::Qwen3MoeMetadata {
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

fn ephemeral_file(encoded: &[u8]) -> EphemeralFile {
    let nonce = FIXTURE_NONCE.fetch_add(1, Ordering::Relaxed);
    let path = std::env::temp_dir().join(format!(
        "pulsarmlx-qwen3moe-external-{pid}-{nonce}.gguf",
        pid = std::process::id()
    ));
    let mut file = OpenOptions::new()
        .create_new(true)
        .read(true)
        .write(true)
        .open(&path)
        .expect("create ephemeral tensor file");
    file.seek(SeekFrom::Start(DATA_OFFSET))
        .expect("position ephemeral tensor file");
    file.write_all(encoded)
        .expect("write ephemeral tensor bytes");
    file.sync_all().expect("sync ephemeral tensor bytes");
    file.seek(SeekFrom::Start(0))
        .expect("rewind ephemeral tensor file");
    let read_only = File::open(&path).expect("open ephemeral tensor file read-only");
    drop(file);
    EphemeralFile {
        path,
        file: read_only,
    }
}

fn storage_and_request(
    file: &EphemeralFile,
    descriptor: &Qwen3MoeFullGraphDescriptor,
) -> (Qwen3MoeExternalStorage, Qwen3MoeStorageRequest) {
    let inspection = ExternalModelInspection::new_synthetic_for_test(
        file.file.try_clone().expect("clone test file"),
        file.path.clone(),
        descriptor.clone(),
    )
    .expect("bind synthetic inspection");
    let storage =
        Qwen3MoeExternalStorage::try_from_inspection(&inspection).expect("bind external storage");
    let request = Qwen3MoeStorageRequest::try_new_synthetic_for_test(
        descriptor,
        Qwen3MoeTensorRole::ExpertGateWeight,
        Some(0),
        Qwen3MoeDestinationPolicy::RustOwned,
        Qwen3MoeDecoderContract::q8_0(),
        "external-qwen3moe-test",
        CancellationToken::new(),
    )
    .expect("create synthetic storage request");
    (storage, request)
}

struct OverlongStore;

impl TensorStore for OverlongStore {
    fn read_range(
        &self,
        _tensor: &RuntimeTensor,
        destination: &mut [u8],
        _cancellation: &CancellationToken,
    ) -> Result<usize, ContractError> {
        destination.fill(0);
        Ok(destination.len() + 1)
    }
}

struct StaticCatalog(RuntimeTensor);

impl TensorCatalog for StaticCatalog {
    fn tensor(&self, name: &str) -> Result<Option<RuntimeTensor>, ContractError> {
        Ok((name == self.0.name).then(|| self.0.clone()))
    }
}

#[test]
fn valid_ephemeral_q8_0_range_decodes_without_fixture_fallback() {
    let encoded = q8_block(0x3c00, &[1; 32]);
    let file = ephemeral_file(&encoded);
    let descriptor = descriptor(vec![32], encoded.len() as u64);
    let (storage, request) = storage_and_request(&file, &descriptor);

    let result = read_admitted_tensor(&storage, &request).expect("decode admitted tensor");

    assert_eq!(result.data(), &[1.0; 32]);
    assert_eq!(result.shape(), [32]);
    assert_eq!(result.byte_length(), 32 * std::mem::size_of::<f32>() as u64);
    assert!(
        !result.data().is_empty(),
        "no fixture-logit fallback is allowed"
    );
}

#[test]
fn wrong_identity_role_name_shape_and_quantization_fail_closed() {
    let encoded = q8_block(0x3c00, &[1; 32]);
    let file = ephemeral_file(&encoded);
    let canonical = descriptor(vec![32], encoded.len() as u64);
    let (storage, request) = storage_and_request(&file, &canonical);

    let mut wrong_identity = canonical.clone();
    wrong_identity.artifact.revision = "wrong-revision".to_owned();
    let wrong_identity_request = Qwen3MoeStorageRequest::try_new_synthetic_for_test(
        &wrong_identity,
        Qwen3MoeTensorRole::ExpertGateWeight,
        Some(0),
        Qwen3MoeDestinationPolicy::RustOwned,
        Qwen3MoeDecoderContract::q8_0(),
        "external-qwen3moe-test",
        CancellationToken::new(),
    )
    .expect("build wrong identity request");
    assert_eq!(
        read_admitted_tensor(&storage, &wrong_identity_request)
            .expect_err("wrong checkpoint identity must fail")
            .code(),
        "qwen3moe_checkpoint_identity_mismatch"
    );

    let mut wrong_role = canonical.clone();
    wrong_role.tensors[0].role = Qwen3MoeTensorRole::RouterWeight;
    assert!(Qwen3MoeStorageRequest::try_new_synthetic_for_test(
        &wrong_role,
        Qwen3MoeTensorRole::ExpertGateWeight,
        Some(0),
        Qwen3MoeDestinationPolicy::RustOwned,
        Qwen3MoeDecoderContract::q8_0(),
        "external-qwen3moe-test",
        CancellationToken::new(),
    )
    .is_err());

    let mut wrong_name = canonical.clone();
    wrong_name.tensors[0].name = "unadmitted.tensor".to_owned();
    let wrong_name_request = Qwen3MoeStorageRequest::try_new_synthetic_for_test(
        &wrong_name,
        Qwen3MoeTensorRole::ExpertGateWeight,
        Some(0),
        Qwen3MoeDestinationPolicy::RustOwned,
        Qwen3MoeDecoderContract::q8_0(),
        "external-qwen3moe-test",
        CancellationToken::new(),
    )
    .expect("build wrong name request");
    assert_eq!(
        read_admitted_tensor(&storage, &wrong_name_request)
            .expect_err("wrong tensor name must fail")
            .code(),
        "qwen3moe_tensor_not_admitted"
    );

    let mut wrong_shape = canonical.clone();
    wrong_shape.tensors[0].gguf_shape = vec![64];
    let wrong_shape_request = Qwen3MoeStorageRequest::try_new_synthetic_for_test(
        &wrong_shape,
        Qwen3MoeTensorRole::ExpertGateWeight,
        Some(0),
        Qwen3MoeDestinationPolicy::RustOwned,
        Qwen3MoeDecoderContract::q8_0(),
        "external-qwen3moe-test",
        CancellationToken::new(),
    )
    .expect("build wrong shape request");
    assert!(read_admitted_tensor(&storage, &wrong_shape_request).is_err());

    let mut wrong_quantization = canonical.clone();
    wrong_quantization.tensors[0].quantization = "Q4_K".to_owned();
    let wrong_quantization_request = Qwen3MoeStorageRequest::try_new_synthetic_for_test(
        &wrong_quantization,
        Qwen3MoeTensorRole::ExpertGateWeight,
        Some(0),
        Qwen3MoeDestinationPolicy::RustOwned,
        Qwen3MoeDecoderContract::q8_0(),
        "external-qwen3moe-test",
        CancellationToken::new(),
    )
    .expect("build wrong quantization request");
    assert!(read_admitted_tensor(&storage, &wrong_quantization_request).is_err());

    let _ = request;
    assert_eq!(
        QWEN3MOE_ADAPTER_CONTRACT_ID,
        "qwen3moe-adapter-admission-v1"
    );
}

#[test]
fn range_bounds_short_reads_cancellation_and_mutation_never_publish_partial_output() {
    let encoded = q8_block(0x3c00, &[1; 32]);
    let file = ephemeral_file(&encoded);
    let canonical = descriptor(vec![32], encoded.len() as u64);
    let (storage, request) = storage_and_request(&file, &canonical);

    let cancelled = CancellationToken::new();
    cancelled.cancel();
    let cancelled_request = Qwen3MoeStorageRequest::try_new_synthetic_for_test(
        &canonical,
        Qwen3MoeTensorRole::ExpertGateWeight,
        Some(0),
        Qwen3MoeDestinationPolicy::RustOwned,
        Qwen3MoeDecoderContract::q8_0(),
        "external-qwen3moe-test",
        cancelled,
    )
    .expect("build cancelled request");
    assert_eq!(
        read_admitted_tensor(&storage, &cancelled_request)
            .expect_err("cancel before I/O")
            .code(),
        "cancelled"
    );

    let mut out_of_range = canonical.clone();
    out_of_range.tensors[0].absolute_data_offset = u64::MAX;
    let out_of_range_request = Qwen3MoeStorageRequest::try_new_synthetic_for_test(
        &out_of_range,
        Qwen3MoeTensorRole::ExpertGateWeight,
        Some(0),
        Qwen3MoeDestinationPolicy::RustOwned,
        Qwen3MoeDecoderContract::q8_0(),
        "external-qwen3moe-test",
        CancellationToken::new(),
    )
    .expect("build out-of-range request");
    assert!(read_admitted_tensor(&storage, &out_of_range_request).is_err());

    let replacement = file.path.with_extension("replacement.gguf");
    fs::rename(&file.path, &replacement).expect("displace original path");
    let replacement_file = OpenOptions::new()
        .create_new(true)
        .read(true)
        .write(true)
        .open(&file.path)
        .expect("create same-path replacement");
    replacement_file
        .set_len(DATA_OFFSET + encoded.len() as u64)
        .expect("size same-path replacement");
    drop(replacement_file);
    assert_eq!(
        read_admitted_tensor(&storage, &request)
            .expect_err("path replacement must fail")
            .code(),
        "model_path_identity_changed"
    );
    fs::remove_file(&file.path).expect("remove replacement");
    fs::rename(replacement, &file.path).expect("restore original path");
}

#[test]
fn caller_owned_destination_is_rejected_before_any_file_read() {
    let encoded = q8_block(0x3c00, &[1; 32]);
    let file = ephemeral_file(&encoded);
    let descriptor = descriptor(vec![32], encoded.len() as u64);
    let inspection = ExternalModelInspection::new_synthetic_for_test(
        file.file.try_clone().expect("clone test file"),
        file.path.clone(),
        descriptor.clone(),
    )
    .expect("bind synthetic inspection");
    let storage =
        Qwen3MoeExternalStorage::try_from_inspection(&inspection).expect("bind external storage");
    let request = Qwen3MoeStorageRequest::try_new_synthetic_for_test(
        &descriptor,
        Qwen3MoeTensorRole::ExpertGateWeight,
        Some(0),
        Qwen3MoeDestinationPolicy::CallerOwned,
        Qwen3MoeDecoderContract::q8_0(),
        "external-qwen3moe-test",
        CancellationToken::new(),
    );
    assert!(request.is_err());
    let _ = storage;
}

#[test]
fn overlong_and_short_file_slabs_are_rejected_without_partial_output() {
    let encoded = q8_block(0x3c00, &[1; 32]);
    let short_file = ephemeral_file(&encoded[..encoded.len() - 1]);
    let short_descriptor = descriptor(vec![32], encoded.len() as u64);
    let short_inspection = ExternalModelInspection::new_synthetic_for_test(
        short_file.file.try_clone().expect("clone short file"),
        short_file.path.clone(),
        short_descriptor.clone(),
    )
    .expect("bind short synthetic inspection");
    let short_storage = Qwen3MoeExternalStorage::try_from_inspection(&short_inspection)
        .expect("bind short storage");
    let short_request = Qwen3MoeStorageRequest::try_new_synthetic_for_test(
        &short_descriptor,
        Qwen3MoeTensorRole::ExpertGateWeight,
        Some(0),
        Qwen3MoeDestinationPolicy::RustOwned,
        Qwen3MoeDecoderContract::q8_0(),
        "external-qwen3moe-test",
        CancellationToken::new(),
    )
    .expect("build short request");
    assert!(read_admitted_tensor(&short_storage, &short_request).is_err());

    let overlong_file = ephemeral_file(&encoded);
    let overlong_descriptor = descriptor(vec![32], encoded.len() as u64);
    let overlong_inspection = ExternalModelInspection::new_synthetic_for_test(
        overlong_file.file.try_clone().expect("clone overlong file"),
        overlong_file.path.clone(),
        overlong_descriptor.clone(),
    )
    .expect("bind overlong synthetic inspection");
    let overlong_storage = Qwen3MoeExternalStorage::try_from_inspection(&overlong_inspection)
        .expect("bind overlong storage");
    let overlong_request = Qwen3MoeStorageRequest::try_new_synthetic_for_test(
        &overlong_descriptor,
        Qwen3MoeTensorRole::ExpertGateWeight,
        Some(0),
        Qwen3MoeDestinationPolicy::RustOwned,
        Qwen3MoeDecoderContract::q8_0(),
        "external-qwen3moe-test",
        CancellationToken::new(),
    );
    let overlong_request = overlong_request.expect("build overlong request");
    let catalog_tensor = overlong_storage
        .tensor(&overlong_request.tensor().name)
        .expect("resolve overlong test tensor")
        .expect("overlong test tensor is admitted");
    assert_eq!(
        decode_qwen3moe_tensor(
            &overlong_request,
            &StaticCatalog(catalog_tensor),
            &OverlongStore,
        )
        .expect_err("overlong Q8_0 metadata must fail")
        .code(),
        "qwen3moe_overlong_read"
    );
    assert_eq!(QWEN3MOE_Q8_0_BLOCK_BYTES, 34);
}
