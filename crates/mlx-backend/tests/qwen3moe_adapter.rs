use mlx_backend::{
    admit_qwen3moe_adapter, Qwen3MoeAdmissionInput, Qwen3MoeArtifactBinding, Qwen3MoeMetadata,
    QWEN3MOE_ADAPTER_CONTRACT_ID, QWEN3MOE_FILENAME, QWEN3MOE_FILE_BYTES, QWEN3MOE_REPOSITORY_ID,
    QWEN3MOE_REVISION, QWEN3MOE_SHA256, QWEN3MOE_TENSOR_COUNT,
};
use serde::Deserialize;

const ADAPTER_FIXTURE: &str = include_str!("../../../fixtures/mlx/qwen3moe-adapter-v1.json");

fn pinned_artifact() -> Qwen3MoeArtifactBinding {
    Qwen3MoeArtifactBinding {
        repository_id: QWEN3MOE_REPOSITORY_ID.to_owned(),
        revision: QWEN3MOE_REVISION.to_owned(),
        filename: QWEN3MOE_FILENAME.to_owned(),
        size_bytes: QWEN3MOE_FILE_BYTES,
        sha256: QWEN3MOE_SHA256.to_owned(),
    }
}

fn pinned_metadata() -> Qwen3MoeMetadata {
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
    }
}

#[test]
fn qwen35_architecture_alias_is_rejected_before_tensor_admission() {
    let mut metadata = pinned_metadata();
    metadata.architecture = "qwen35".to_owned();
    let error = admit_qwen3moe_adapter(Qwen3MoeAdmissionInput {
        artifact: pinned_artifact(),
        metadata,
        tensors: Vec::new(),
    })
    .expect_err("a qwen35 alias must not enter the qwen3moe adapter");
    assert_eq!(error.code(), "model_architecture_mismatch");
}

#[derive(Debug, Deserialize)]
struct AdapterFixture {
    schema: String,
    evidence_level: String,
    model_free: bool,
    proves_real_checkpoint_admission: bool,
    routing: RoutingFixture,
    shape_semantics: ShapeFixture,
}

#[derive(Debug, Deserialize)]
struct RoutingFixture {
    token_count: u64,
    expert_count: u64,
    top_k: u64,
    low_score: f64,
    high_score: f64,
    low_expert_count: usize,
    high_expert_count: usize,
    expected_selected_expert_ids: Vec<u64>,
    expected_normalized_weights: Vec<f64>,
}

#[derive(Debug, Deserialize)]
struct ShapeFixture {
    router_gguf_shape: Vec<u64>,
    router_reader_shape: Vec<u64>,
    expert_gate_gguf_shape: Vec<u64>,
    expert_gate_reader_shape: Vec<u64>,
    expert_gate_execution_shape: Vec<u64>,
    quantization: String,
}

#[test]
fn synthetic_adapter_fixture_reuses_pure_routing_and_shape_contracts() {
    let fixture: AdapterFixture =
        serde_json::from_str(ADAPTER_FIXTURE).expect("parse adapter fixture");
    assert_eq!(fixture.schema, "pulsarmlx.fixture.qwen3moe-adapter-v1");
    assert_eq!(fixture.evidence_level, "synthetic_adapter_semantics_only");
    assert!(fixture.model_free);
    assert!(!fixture.proves_real_checkpoint_admission);
    assert_eq!(
        QWEN3MOE_ADAPTER_CONTRACT_ID,
        "qwen3moe-adapter-admission-v1"
    );
    assert_eq!(QWEN3MOE_TENSOR_COUNT, 579);

    let mut scores = vec![fixture.routing.low_score; fixture.routing.low_expert_count];
    scores.extend(std::iter::repeat_n(
        fixture.routing.high_score,
        fixture.routing.high_expert_count,
    ));
    let plan = backend::RoutingPlan::try_softmax(
        &scores,
        fixture.routing.token_count,
        fixture.routing.expert_count,
        fixture.routing.top_k,
    )
    .expect("synthetic route shape is admitted by the existing pure router");
    assert_eq!(
        plan.selected_expert_ids(),
        fixture.routing.expected_selected_expert_ids
    );
    for (actual, expected) in plan
        .normalized_weights()
        .iter()
        .zip(fixture.routing.expected_normalized_weights)
    {
        assert!((actual - expected).abs() < 1.0e-12);
    }

    assert_eq!(fixture.shape_semantics.router_gguf_shape, vec![2_048, 128]);
    assert_eq!(
        fixture.shape_semantics.router_reader_shape,
        vec![128, 2_048]
    );
    assert_eq!(
        fixture.shape_semantics.expert_gate_gguf_shape,
        vec![2_048, 768, 128]
    );
    assert_eq!(
        fixture.shape_semantics.expert_gate_reader_shape,
        vec![128, 768, 2_176]
    );
    assert_eq!(
        fixture.shape_semantics.expert_gate_execution_shape,
        vec![128, 768, 2_048]
    );
    assert_eq!(fixture.shape_semantics.quantization, "Q8_0");
}
