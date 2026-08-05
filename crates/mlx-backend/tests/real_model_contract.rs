use std::path::PathBuf;
use std::time::{SystemTime, UNIX_EPOCH};

use backend::{ContractError, ErrorCategory};
use mlx_backend::{
    admit_qwen3_q8_0_slice, ModelAdmissionDescriptor, ModelExecutionDepth, ModelIdentityDescriptor,
    ModelMemoryBudget, ModelMetadataDescriptor, ModelTensorDescriptor,
};

const REPOSITORY_ID: &str = "Qwen/Qwen3-30B-A3B-GGUF";
const REVISION: &str = "e4d4bafdfb96a411a163846265362aceb0b9c63a";
const FILENAME: &str = "Qwen3-30B-A3B-Q8_0.gguf";
const SHA256: &str = "4ad960d180b16f56024f5b704697e5dd5b0837167c2e515ef0569abfc599743c";
const FILE_BYTES: u64 = 32_483_931_648;
const TENSOR_NAME: &str = "blk.0.ffn_gate_exps.weight";
const TENSOR_ELEMENTS: u64 = 201_326_592;
const TENSOR_BYTES: u64 = 213_909_504;
const TENSOR_DATA_OFFSET: u64 = 901_175_808;

fn admitted_descriptor() -> ModelAdmissionDescriptor {
    ModelAdmissionDescriptor {
        identity: ModelIdentityDescriptor {
            repository_id: REPOSITORY_ID.to_owned(),
            revision: REVISION.to_owned(),
            filename: FILENAME.to_owned(),
            license_spdx: "Apache-2.0".to_owned(),
            expected_size_bytes: FILE_BYTES,
            actual_size_bytes: FILE_BYTES,
            expected_sha256: SHA256.to_owned(),
            actual_sha256: SHA256.to_owned(),
            stored_outside_repository: true,
        },
        metadata: ModelMetadataDescriptor {
            architecture: "qwen3moe".to_owned(),
            architecture_value_type: "STRING".to_owned(),
            embedding_length: 2_048,
            embedding_length_value_type: "UINT32".to_owned(),
            expert_feed_forward_length: 768,
            expert_feed_forward_length_value_type: "UINT32".to_owned(),
            expert_count: 128,
            expert_count_value_type: "UINT32".to_owned(),
            little_endian: true,
        },
        tensors: vec![ModelTensorDescriptor {
            role: "layer_0_routed_expert_gate_projection".to_owned(),
            name: TENSOR_NAME.to_owned(),
            occurrences: 1,
            quantization: "Q8_0".to_owned(),
            gguf_dimensions_fastest_axis_first: vec![2_048, 768, 128],
            reader_encoded_shape: vec![128, 768, 2_176],
            logical_elements: TENSOR_ELEMENTS,
            encoded_bytes: TENSOR_BYTES,
            absolute_data_offset: TENSOR_DATA_OFFSET,
        }],
        memory_budget: ModelMemoryBudget {
            available_disk_bytes: 187_187_339_264,
            required_disk_bytes: 134_761_081_856,
            host_unified_memory_bytes: 137_438_953_472,
            required_host_bytes: 42_949_672_960,
            owned_compressed_bytes_cap: 268_435_456,
            decoded_array_bytes_cap: 1_073_741_824,
            temporary_peak_bytes_cap: 2_147_483_648,
            mlx_active_bytes_cap: 3_221_225_472,
            mlx_cache_bytes_cap: 1_342_177_280,
            mlx_peak_bytes_cap: 4_294_967_296,
            process_physical_footprint_bytes_cap: 8_589_934_592,
            mandatory_system_headroom_bytes: 34_359_738_368,
        },
        execution_depth: ModelExecutionDepth::Layer0Expert0GateRows0To16Matvec,
        automatic_download_requested: false,
    }
}

fn assert_rejected(descriptor: &ModelAdmissionDescriptor, expected_code: &str) {
    let error = admit_qwen3_q8_0_slice(descriptor)
        .expect_err("an invalid real-model contract must not be admitted");
    assert_eq!(error.code(), expected_code);
    assert!(error.message().chars().count() <= 512);
}

#[test]
fn exact_identity_metadata_role_budget_and_depth_are_admitted() {
    let admitted = admit_qwen3_q8_0_slice(&admitted_descriptor())
        .expect("the exact T055 observation must pass the bounded contract");

    assert_eq!(admitted.repository_id(), REPOSITORY_ID);
    assert_eq!(admitted.revision(), REVISION);
    assert_eq!(admitted.filename(), FILENAME);
    assert_eq!(admitted.sha256(), SHA256);
    assert_eq!(admitted.size_bytes(), FILE_BYTES);
    assert_eq!(admitted.architecture(), "qwen3moe");
    assert_eq!(admitted.tensor_name(), TENSOR_NAME);
    assert_eq!(admitted.tensor_quantization(), "Q8_0");
    assert_eq!(admitted.tensor_dimensions(), &[2_048, 768, 128]);
    assert_eq!(admitted.tensor_data_offset(), TENSOR_DATA_OFFSET);
    assert_eq!(admitted.encoded_slice_bytes(), 34_816);
    assert_eq!(admitted.decoded_slice_bytes(), 131_072);
    assert_eq!(admitted.activation_bytes(), 8_192);
    assert_eq!(admitted.output_bytes(), 64);
    assert_eq!(
        admitted.execution_depth(),
        ModelExecutionDepth::Layer0Expert0GateRows0To16Matvec
    );
}

#[test]
fn immutable_identity_and_license_mismatches_are_rejected() {
    let cases = [
        ("repository", "model_identity_mismatch"),
        ("revision", "model_identity_mismatch"),
        ("filename", "model_identity_mismatch"),
        ("license", "model_license_mismatch"),
        ("expected sha", "model_identity_mismatch"),
        ("actual sha", "model_checksum_mismatch"),
        ("size", "model_size_mismatch"),
        ("inside repository", "model_path_not_external"),
    ];

    for (case, expected_code) in cases {
        let mut descriptor = admitted_descriptor();
        match case {
            "repository" => descriptor.identity.repository_id = "other/repository".to_owned(),
            "revision" => descriptor.identity.revision = "main".to_owned(),
            "filename" => descriptor.identity.filename = "other.gguf".to_owned(),
            "license" => descriptor.identity.license_spdx = "unknown".to_owned(),
            "expected sha" => descriptor.identity.expected_sha256 = "0".repeat(64),
            "actual sha" => descriptor.identity.actual_sha256 = "1".repeat(64),
            "size" => descriptor.identity.actual_size_bytes -= 1,
            "inside repository" => descriptor.identity.stored_outside_repository = false,
            _ => unreachable!(),
        }
        assert_rejected(&descriptor, expected_code);
    }
}

#[test]
fn metadata_type_value_and_endianness_mismatches_are_rejected() {
    let cases = [
        ("architecture", "model_metadata_mismatch"),
        ("architecture type", "model_metadata_type_mismatch"),
        ("embedding", "model_metadata_mismatch"),
        ("embedding type", "model_metadata_type_mismatch"),
        ("expert width", "model_metadata_mismatch"),
        ("expert count", "model_metadata_mismatch"),
        ("endianness", "model_endianness_mismatch"),
    ];

    for (case, expected_code) in cases {
        let mut descriptor = admitted_descriptor();
        match case {
            "architecture" => descriptor.metadata.architecture = "qwen2moe".to_owned(),
            "architecture type" => descriptor.metadata.architecture_value_type = "ARRAY".to_owned(),
            "embedding" => descriptor.metadata.embedding_length = 4_096,
            "embedding type" => {
                descriptor.metadata.embedding_length_value_type = "UINT64".to_owned()
            }
            "expert width" => descriptor.metadata.expert_feed_forward_length = 1_536,
            "expert count" => descriptor.metadata.expert_count = 64,
            "endianness" => descriptor.metadata.little_endian = false,
            _ => unreachable!(),
        }
        assert_rejected(&descriptor, expected_code);
    }
}

#[test]
fn missing_duplicate_wrong_quantization_and_malformed_ranges_are_rejected() {
    let mut missing = admitted_descriptor();
    missing.tensors.clear();
    assert_rejected(&missing, "missing_tensor_role");

    let mut duplicate = admitted_descriptor();
    duplicate.tensors.push(duplicate.tensors[0].clone());
    assert_rejected(&duplicate, "duplicate_tensor_role");

    let cases = [
        ("name", "missing_tensor_role"),
        ("quantization", "unsupported_tensor_quantization"),
        ("dimensions", "tensor_shape_mismatch"),
        ("encoded shape", "tensor_shape_mismatch"),
        ("elements", "tensor_size_mismatch"),
        ("bytes", "tensor_size_mismatch"),
        ("range", "invalid_tensor_range"),
    ];
    for (case, expected_code) in cases {
        let mut descriptor = admitted_descriptor();
        let tensor = &mut descriptor.tensors[0];
        match case {
            "name" => tensor.name = "blk.0.ffn_up_exps.weight".to_owned(),
            "quantization" => tensor.quantization = "Q4_K_M".to_owned(),
            "dimensions" => tensor.gguf_dimensions_fastest_axis_first.swap(0, 2),
            "encoded shape" => tensor.reader_encoded_shape.swap(0, 2),
            "elements" => tensor.logical_elements -= 1,
            "bytes" => tensor.encoded_bytes -= 1,
            "range" => tensor.absolute_data_offset = FILE_BYTES - 1,
            _ => unreachable!(),
        }
        assert_rejected(&descriptor, expected_code);
    }
}

#[test]
fn every_budget_and_execution_depth_promotion_is_rejected() {
    let budget_cases = [
        ("disk", "model_budget_exceeded"),
        ("host", "model_budget_exceeded"),
        ("compressed", "model_budget_exceeded"),
        ("decoded", "model_budget_exceeded"),
        ("temporary", "model_budget_exceeded"),
        ("mlx active", "model_budget_exceeded"),
        ("mlx cache", "model_budget_exceeded"),
        ("mlx peak", "model_budget_exceeded"),
        ("footprint", "model_budget_exceeded"),
        ("headroom", "model_budget_exceeded"),
    ];
    for (case, expected_code) in budget_cases {
        let mut descriptor = admitted_descriptor();
        let budget = &mut descriptor.memory_budget;
        match case {
            "disk" => budget.available_disk_bytes = budget.required_disk_bytes - 1,
            "host" => budget.host_unified_memory_bytes = budget.required_host_bytes - 1,
            "compressed" => budget.owned_compressed_bytes_cap = 34_815,
            "decoded" => budget.decoded_array_bytes_cap = 131_071,
            "temporary" => budget.temporary_peak_bytes_cap = 131_071,
            "mlx active" => budget.mlx_active_bytes_cap = 131_071,
            "mlx cache" => budget.mlx_cache_bytes_cap = 34_815,
            "mlx peak" => budget.mlx_peak_bytes_cap = 131_071,
            "footprint" => budget.process_physical_footprint_bytes_cap = 131_071,
            "headroom" => budget.mandatory_system_headroom_bytes = 0,
            _ => unreachable!(),
        }
        assert_rejected(&descriptor, expected_code);
    }

    for depth in [
        ModelExecutionDepth::MetadataOnly,
        ModelExecutionDepth::FullLayer,
        ModelExecutionDepth::Logits,
        ModelExecutionDepth::Generation,
    ] {
        let mut descriptor = admitted_descriptor();
        descriptor.execution_depth = depth;
        assert_rejected(&descriptor, "unsupported_execution_depth");
    }
}

#[test]
fn automatic_download_is_rejected_without_creating_files_and_paths_are_redacted() {
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("clock must be after Unix epoch")
        .as_nanos();
    let absent = std::env::temp_dir().join(format!(
        "pulsarmlx-no-auto-download-{}-{nonce}.gguf",
        std::process::id()
    ));
    assert!(!absent.exists());

    let mut descriptor = admitted_descriptor();
    descriptor.automatic_download_requested = true;
    let error = admit_qwen3_q8_0_slice(&descriptor)
        .expect_err("automatic model acquisition must never be admitted");
    assert_eq!(error.code(), "automatic_download_forbidden");
    assert!(!absent.exists());

    let private_path = PathBuf::from("/Users/private/model.gguf");
    let diagnostic = format!("model is unavailable at {}", private_path.display());
    let sanitized =
        ContractError::new(ErrorCategory::InvalidModel, "model_unavailable", diagnostic);
    assert!(!sanitized.message().contains("/Users/private"));
    assert!(sanitized.message().contains("<redacted-path>"));
}
