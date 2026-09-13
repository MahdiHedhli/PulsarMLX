use super::*;
use crate::model::ExternalModelInspection;
use crate::qwen3moe::{
    Qwen3MoeArtifactBinding, Qwen3MoeGraphDescriptor, Qwen3MoeMetadata, Qwen3MoeTensorBinding,
    Qwen3MoeTensorRole, QWEN3MOE_FILENAME, QWEN3MOE_FILE_BYTES, QWEN3MOE_FULL_GRAPH_CONTRACT_ID,
    QWEN3MOE_REPOSITORY_ID, QWEN3MOE_REVISION, QWEN3MOE_SHA256,
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

fn q8_block() -> Vec<u8> {
    let mut block = 0x3c00_u16.to_le_bytes().to_vec();
    block.extend([1_i8; 32].into_iter().map(|value| value.to_le_bytes()[0]));
    block
}

#[test]
fn synthetic_inspection_cannot_bind_to_production_storage() {
    let encoded = q8_block();
    let file = ephemeral_file(&encoded);
    let inspection = ExternalModelInspection::new_synthetic_for_test(
        file.file.try_clone().expect("clone test file"),
        file.path.clone(),
        descriptor(vec![32], encoded.len() as u64),
    )
    .expect("construct synthetic inspection");

    let error = match Qwen3MoeExternalStorage::try_from_inspection(&inspection) {
        Ok(_) => panic!("synthetic inspection must not cross production admission"),
        Err(error) => error,
    };
    assert_eq!(error.code(), "canonical_admission_required");
}

#[test]
fn same_inode_truncation_and_in_place_mutation_fail_identity_recheck() {
    let encoded = q8_block();
    let file = ephemeral_file(&encoded);
    let inspection = ExternalModelInspection::new_synthetic_for_test(
        file.file.try_clone().expect("clone test file"),
        file.path.clone(),
        descriptor(vec![32], encoded.len() as u64),
    )
    .expect("construct synthetic inspection");
    inspection
        .verify_unchanged()
        .expect("unchanged synthetic fixture identity");

    let writer = OpenOptions::new()
        .read(true)
        .write(true)
        .open(&file.path)
        .expect("open same inode for truncation");
    writer.set_len(DATA_OFFSET).expect("truncate same inode");
    assert_eq!(
        inspection
            .verify_unchanged()
            .expect_err("same-inode truncation must fail")
            .code(),
        "model_size_mismatch"
    );
    drop(writer);

    let file = ephemeral_file(&encoded);
    let inspection = ExternalModelInspection::new_synthetic_for_test(
        file.file.try_clone().expect("clone test file"),
        file.path.clone(),
        descriptor(vec![32], encoded.len() as u64),
    )
    .expect("construct second synthetic inspection");
    let mut writer = OpenOptions::new()
        .read(true)
        .write(true)
        .open(&file.path)
        .expect("open same inode for mutation");
    writer
        .seek(SeekFrom::Start(DATA_OFFSET))
        .expect("position same inode mutation");
    writer.write_all(&[2]).expect("mutate same inode");
    writer.sync_all().expect("sync same inode mutation");
    assert_eq!(
        inspection
            .verify_unchanged()
            .expect_err("in-place mutation must fail")
            .code(),
        "model_checksum_mismatch"
    );
}

#[test]
fn positional_completion_does_not_move_the_shared_cursor() {
    let encoded = q8_block();
    let file = ephemeral_file(&encoded);
    let mut destination = vec![0_u8; encoded.len()];
    let mut reader = file.file.try_clone().expect("clone positional reader");
    reader.seek(SeekFrom::Start(0)).expect("set initial cursor");
    let cancellation = CancellationToken::new();
    assert_eq!(
        read_exact_positional(&reader, &mut destination, DATA_OFFSET, &cancellation)
            .expect("complete positional read"),
        encoded.len()
    );
    assert_eq!(destination, encoded);
    assert_eq!(reader.stream_position().expect("read cursor"), 0);
}

#[test]
fn production_request_uses_the_admitted_rows_zero_through_sixteen_slice() {
    let source = Qwen3MoeTensorDescriptor {
        role: Qwen3MoeTensorRole::ExpertGateWeight,
        layer_index: Some(0),
        name: "blk.0.ffn_gate_exps.weight".to_owned(),
        gguf_shape: vec![2_048, 768, 128],
        reader_shape: vec![128, 768, 2_176],
        execution_shape: vec![128, 768, 2_048],
        gguf_type: "Q8_0".to_owned(),
        quantization: "Q8_0".to_owned(),
        orientation: "expert_major_intermediate_rows_hidden_input_columns".to_owned(),
        logical_elements: 201_326_592,
        encoded_bytes: 213_909_504,
        absolute_data_offset: QWEN_TENSOR_DATA_OFFSET,
    };
    let slice = admitted_layer0_slice(&source).expect("admitted slice layout");
    assert_eq!(slice.gguf_shape, [2_048, 16]);
    assert_eq!(slice.reader_shape, [16, 2_176]);
    assert_eq!(slice.execution_shape, [16, 2_048]);
    assert_eq!(slice.logical_elements, 32_768);
    assert_eq!(slice.encoded_bytes, QWEN_ENCODED_SLICE_BYTES);
    assert_eq!(QWEN_DECODED_SLICE_BYTES, 131_072);

    let request = Qwen3MoeStorageRequest {
        checkpoint: CheckpointIdentity::try_new(QWEN3MOE_SHA256, QWEN3MOE_REVISION)
            .expect("checkpoint identity"),
        tensor: slice,
        source_tensor: source,
        production_slice: true,
        destination_policy: Qwen3MoeDestinationPolicy::RustOwned,
        decoder_contract: Qwen3MoeDecoderContract::q8_0(),
        correlation_id: "production-slice-test".to_owned(),
        cancellation: CancellationToken::new(),
    };
    let runtime =
        validate_request_tensor(&request).expect("production slice is not synthetic-capped");
    assert_eq!(runtime.range.length, QWEN_ENCODED_SLICE_BYTES);
    assert_eq!(runtime.shape, [16, 2_176]);
}
