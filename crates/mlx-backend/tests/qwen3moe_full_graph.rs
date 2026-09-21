use mlx_backend::{
    Qwen3MoeGraphOperation, QWEN3MOE_EXPERT_COUNT, QWEN3MOE_FULL_GRAPH_CONTRACT_ID,
    QWEN3MOE_HIDDEN_WIDTH, QWEN3MOE_LAYER_COUNT, QWEN3MOE_TENSOR_COUNT, QWEN3MOE_TOP_K,
};
use serde::Deserialize;

const FULL_GRAPH_FIXTURE: &str = include_str!("../../../fixtures/mlx/qwen3moe-full-graph-v1.json");

#[derive(Debug, Deserialize)]
struct FullGraphFixture {
    schema: String,
    evidence_level: String,
    model_free: bool,
    proves_real_checkpoint_admission: bool,
    architecture: String,
    tensor_catalog: TensorCatalogFixture,
    graph: GraphFixture,
}

#[derive(Debug, Deserialize)]
struct TensorCatalogFixture {
    entry_count: usize,
    global_entry_count: usize,
    entries_per_layer: usize,
    layer_count: usize,
    uses_checkpoint_payload_bytes: bool,
}

#[derive(Debug, Deserialize)]
struct GraphFixture {
    layer_count: usize,
    operations_per_layer: Vec<String>,
    global_operations: Vec<String>,
    attention: AttentionFixture,
    routing: RoutingFixture,
}

#[derive(Debug, Deserialize)]
struct AttentionFixture {
    head_count: u64,
    kv_head_count: u64,
    head_dimension: u64,
    rope: String,
}

#[derive(Debug, Deserialize)]
struct RoutingFixture {
    expert_count: u64,
    top_k: u64,
    normalization: String,
}

#[test]
fn model_free_full_graph_fixture_matches_typed_contract() {
    let fixture: FullGraphFixture =
        serde_json::from_str(FULL_GRAPH_FIXTURE).expect("parse full graph fixture");
    assert_eq!(fixture.schema, "pulsarmlx.fixture.qwen3moe-full-graph-v1");
    assert_eq!(
        fixture.evidence_level,
        "synthetic_full_graph_semantics_only"
    );
    assert!(fixture.model_free);
    assert!(!fixture.proves_real_checkpoint_admission);
    assert_eq!(fixture.architecture, "qwen3moe");

    assert_eq!(fixture.tensor_catalog.entry_count, QWEN3MOE_TENSOR_COUNT);
    assert_eq!(fixture.tensor_catalog.global_entry_count, 3);
    assert_eq!(fixture.tensor_catalog.entries_per_layer, 12);
    assert_eq!(
        fixture.tensor_catalog.layer_count,
        QWEN3MOE_LAYER_COUNT as usize
    );
    assert!(!fixture.tensor_catalog.uses_checkpoint_payload_bytes);

    assert_eq!(fixture.graph.layer_count, QWEN3MOE_LAYER_COUNT as usize);
    let expected_layer_operations = vec![
        Qwen3MoeGraphOperation::AttentionInputRmsNorm.as_str(),
        Qwen3MoeGraphOperation::QueryProjection.as_str(),
        Qwen3MoeGraphOperation::QueryRmsNorm.as_str(),
        Qwen3MoeGraphOperation::KeyProjection.as_str(),
        Qwen3MoeGraphOperation::KeyRmsNorm.as_str(),
        Qwen3MoeGraphOperation::ValueProjection.as_str(),
        Qwen3MoeGraphOperation::NeoxRotaryEmbedding.as_str(),
        Qwen3MoeGraphOperation::GroupedQueryAttention.as_str(),
        Qwen3MoeGraphOperation::AttentionOutputProjection.as_str(),
        Qwen3MoeGraphOperation::AttentionResidualAdd.as_str(),
        Qwen3MoeGraphOperation::FfnInputRmsNorm.as_str(),
        Qwen3MoeGraphOperation::RouterProjection.as_str(),
        Qwen3MoeGraphOperation::RouterTopK.as_str(),
        Qwen3MoeGraphOperation::ExpertGateProjection.as_str(),
        Qwen3MoeGraphOperation::ExpertUpProjection.as_str(),
        Qwen3MoeGraphOperation::SwiGluActivation.as_str(),
        Qwen3MoeGraphOperation::ExpertDownProjection.as_str(),
        Qwen3MoeGraphOperation::RoutedExpertWeightedAggregate.as_str(),
        Qwen3MoeGraphOperation::FfnResidualAdd.as_str(),
    ];
    assert_eq!(
        fixture.graph.operations_per_layer,
        expected_layer_operations
    );
    assert_eq!(fixture.graph.global_operations.len(), 3);
    assert_eq!(
        fixture.graph.operations_per_layer[0],
        Qwen3MoeGraphOperation::AttentionInputRmsNorm.as_str()
    );
    assert_eq!(
        fixture.graph.operations_per_layer[12],
        Qwen3MoeGraphOperation::RouterTopK.as_str()
    );
    assert_eq!(
        fixture.graph.global_operations,
        vec![
            Qwen3MoeGraphOperation::TokenEmbedding.as_str(),
            Qwen3MoeGraphOperation::FinalRmsNorm.as_str(),
            Qwen3MoeGraphOperation::OutputProjection.as_str(),
        ]
    );
    assert_eq!(fixture.graph.attention.head_count, 32);
    assert_eq!(fixture.graph.attention.kv_head_count, 4);
    assert_eq!(fixture.graph.attention.head_dimension, 128);
    assert_eq!(fixture.graph.attention.rope, "neox");
    assert_eq!(fixture.graph.routing.expert_count, QWEN3MOE_EXPERT_COUNT);
    assert_eq!(fixture.graph.routing.top_k, QWEN3MOE_TOP_K);
    assert_eq!(
        fixture.graph.routing.normalization,
        "full_128_way_softmax_then_selected_probability_renormalization"
    );
    assert_eq!(QWEN3MOE_HIDDEN_WIDTH, 2_048);
    assert_eq!(
        QWEN3MOE_FULL_GRAPH_CONTRACT_ID,
        "qwen3moe-full-graph-admission-v1"
    );
}
