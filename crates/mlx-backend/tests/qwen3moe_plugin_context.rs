use backend::ArchitecturePlugin;
use mlx_backend::{
    Qwen3MoeArtifactBinding, Qwen3MoeExecutionContext, Qwen3MoeFullGraphDescriptor,
    Qwen3MoeGraphDescriptor, Qwen3MoeGraphNodeDescriptor, Qwen3MoeGraphOperation,
    Qwen3MoeLayerGraphDescriptor, Qwen3MoeMetadata, Qwen3MoePlugin, Qwen3MoeTensorBinding,
    Qwen3MoeTensorDescriptor, Qwen3MoeTensorRole, QWEN3MOE_FILENAME, QWEN3MOE_FILE_BYTES,
    QWEN3MOE_FULL_GRAPH_CONTRACT_ID, QWEN3MOE_REPOSITORY_ID, QWEN3MOE_REVISION, QWEN3MOE_SHA256,
};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;

fn admitted_descriptor_fixture() -> Qwen3MoeFullGraphDescriptor {
    let token_embedding = tensor_binding(
        Qwen3MoeTensorRole::TokenEmbedding,
        None,
        "fixture.token_embedding",
    );
    let final_norm = tensor_binding(Qwen3MoeTensorRole::OutputNorm, None, "fixture.final_norm");
    let output_projection = tensor_binding(
        Qwen3MoeTensorRole::OutputWeight,
        None,
        "fixture.output_projection",
    );
    let ffn_norm = tensor_binding(
        Qwen3MoeTensorRole::FfnNorm,
        Some(17),
        "fixture.layer17.ffn_norm",
    );
    let router = tensor_binding(
        Qwen3MoeTensorRole::RouterWeight,
        Some(17),
        "fixture.layer17.router",
    );

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
        vec![
            tensor_descriptor(&token_embedding),
            tensor_descriptor(&final_norm),
            tensor_descriptor(&output_projection),
            tensor_descriptor(&ffn_norm),
            tensor_descriptor(&router),
        ],
        Qwen3MoeGraphDescriptor {
            token_embedding,
            layers: vec![Qwen3MoeLayerGraphDescriptor {
                layer_index: 17,
                nodes: vec![
                    Qwen3MoeGraphNodeDescriptor {
                        operation: Qwen3MoeGraphOperation::FfnInputRmsNorm,
                        tensor: Some(ffn_norm),
                    },
                    Qwen3MoeGraphNodeDescriptor {
                        operation: Qwen3MoeGraphOperation::RouterProjection,
                        tensor: Some(router),
                    },
                ],
            }],
            final_norm,
            output_projection,
        },
    )
}

fn tensor_binding(
    role: Qwen3MoeTensorRole,
    layer_index: Option<u32>,
    tensor_name: &str,
) -> Qwen3MoeTensorBinding {
    Qwen3MoeTensorBinding {
        role,
        layer_index,
        tensor_name: tensor_name.to_owned(),
    }
}

fn tensor_descriptor(binding: &Qwen3MoeTensorBinding) -> Qwen3MoeTensorDescriptor {
    Qwen3MoeTensorDescriptor {
        role: binding.role,
        layer_index: binding.layer_index,
        name: binding.tensor_name.clone(),
        gguf_shape: vec![1],
        reader_shape: vec![1],
        execution_shape: vec![1],
        gguf_type: "F32".to_owned(),
        quantization: "none_f32".to_owned(),
        orientation: "fixture".to_owned(),
        logical_elements: 1,
        encoded_bytes: 4,
        absolute_data_offset: 5_969_408,
    }
}

struct InMemoryAdmittedCatalog {
    descriptor: Qwen3MoeFullGraphDescriptor,
    payload_reads: Arc<AtomicUsize>,
}

impl InMemoryAdmittedCatalog {
    fn new() -> Self {
        Self {
            descriptor: admitted_descriptor_fixture(),
            payload_reads: Arc::new(AtomicUsize::new(0)),
        }
    }

    fn descriptor(&self) -> Qwen3MoeFullGraphDescriptor {
        self.descriptor.clone()
    }

    fn payload_reads(&self) -> usize {
        self.payload_reads.load(Ordering::Acquire)
    }
}

#[test]
fn qwen3moe_plugin_uses_the_typed_architecture_identity() {
    let plugin = Qwen3MoePlugin::default();

    assert_eq!(plugin.architecture_id(), "qwen3moe");
}

#[test]
fn execution_context_reuses_admitted_graph_and_catalog_bindings() {
    let fixture = InMemoryAdmittedCatalog::new();
    let expected_descriptor = fixture.descriptor.clone();
    let context = Qwen3MoePlugin::new()
        .execution_context(fixture.descriptor())
        .expect("the already-admitted descriptor is accepted");

    assert_eq!(context.descriptor(), &expected_descriptor);
    assert_eq!(context.graph(), &expected_descriptor.graph);
    assert_eq!(context.tensors(), expected_descriptor.tensors.as_slice());
    assert_eq!(
        context.graph().layers[0].nodes[0]
            .tensor
            .as_ref()
            .expect("FFN binding")
            .tensor_name,
        "fixture.layer17.ffn_norm"
    );
    assert_eq!(
        context
            .tensor(Qwen3MoeTensorRole::RouterWeight, Some(17))
            .expect("typed router binding")
            .name,
        "fixture.layer17.router"
    );
}

#[test]
fn context_construction_performs_no_payload_read() {
    let fixture = InMemoryAdmittedCatalog::new();
    let context = Qwen3MoeExecutionContext::try_new(fixture.descriptor())
        .expect("the in-memory descriptor is accepted without a source");

    assert_eq!(fixture.payload_reads(), 0);
    assert_eq!(context.descriptor().artifact.filename, QWEN3MOE_FILENAME);
}

#[test]
fn context_rejects_a_descriptor_from_another_graph_contract() {
    let mut descriptor = admitted_descriptor_fixture();
    descriptor.contract_id = "other-graph-contract-v1".to_owned();

    let error = Qwen3MoeExecutionContext::try_new(descriptor)
        .expect_err("a context must not accept a descriptor from another contract");

    assert_eq!(error.code(), "qwen3moe_graph_contract_mismatch");
}
