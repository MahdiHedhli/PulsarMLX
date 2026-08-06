use mlx_backend::router::{
    RouterOracle, RouterOracleFormat, RouterTensorDescriptor, ROUTER_MODEL_BYTES,
    ROUTER_MODEL_SHA256, ROUTER_ORACLE_OUTPUT_BUNDLE_SHA256, ROUTER_REAL_INPUT_SHA256,
    ROUTER_REAL_SINGLE_ROW_CASE_ID, ROUTER_REAL_TWO_ROW_CASE_ID, ROUTER_TENSOR_ABSOLUTE_OFFSET,
    ROUTER_TENSOR_BYTES, ROUTER_TENSOR_ELEMENTS, ROUTER_TENSOR_NAME, ROUTER_TENSOR_SHA256,
};
use serde_json::{json, Value};
use std::fs;
use std::path::PathBuf;

fn repository_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..")
}

fn public_oracle_value() -> Value {
    let bytes = fs::read(
        repository_root()
            .join("fixtures/research/router-v1/real/f002-router-oracle-freeze-0001.json"),
    )
    .expect("committed public oracle is readable");
    serde_json::from_slice(&bytes).expect("committed public oracle is JSON")
}

fn external_oracle_value() -> Value {
    let public = public_oracle_value();
    json!({
        "schema": "pulsarmlx.research.router-oracle",
        "schema_version": "1.0.0",
        "oracle_id": "qwen3moe-layer0-router-cpu-oracle-v1",
        "status": "passed",
        "source": public["source"].clone(),
        "generator": public["generator"].clone(),
        "model": {
            "filename": public["model"]["filename"].clone(),
            "size_bytes": public["model"]["size_bytes"].clone(),
            "sha256": public["model"]["sha256"].clone(),
            "runtime_identity": {
                "device": 1,
                "inode": 2,
                "size_bytes": public["model"]["size_bytes"].clone(),
                "sha256": public["model"]["sha256"].clone(),
            },
            "consumer_proofs": [],
        },
        "tensor": {
            "name": public["tensor"]["name"].clone(),
            "gguf_type": public["tensor"]["gguf_type"].clone(),
            "gguf_dimensions_fastest_axis_first": public["tensor"]["gguf_dimensions"].clone(),
            "reader_shape": public["tensor"]["reader_shape"].clone(),
            "logical_element_count": public["tensor"]["logical_element_count"].clone(),
            "encoded_byte_length": public["tensor"]["encoded_length_bytes"].clone(),
            "encoded_sha256": public["tensor"]["encoded_sha256"].clone(),
            "orientation": public["tensor"]["orientation"].clone(),
        },
        "capture": public["capture"].clone(),
        "capture_provenance": public["capture_provenance"].clone(),
        "input": public["input"].clone(),
        "result": public["result"].clone(),
        "comparison_policy": public["comparison_policy"].clone(),
        "unsupported_interpretations": public["unsupported_interpretations"].clone(),
    })
}

fn frozen_descriptor() -> RouterTensorDescriptor {
    RouterTensorDescriptor {
        name: ROUTER_TENSOR_NAME.to_owned(),
        semantic_role: "layer_0_router_projection".to_owned(),
        occurrence_count: 1,
        gguf_dimensions_fastest_axis_first: vec![2_048, 128],
        reader_shape: vec![128, 2_048],
        execution_shape: vec![128, 2_048],
        gguf_type: "F32".to_owned(),
        quantization: "none_f32".to_owned(),
        logical_elements: ROUTER_TENSOR_ELEMENTS,
        absolute_data_offset: ROUTER_TENSOR_ABSOLUTE_OFFSET,
        encoded_length: ROUTER_TENSOR_BYTES,
        encoded_sha256: ROUTER_TENSOR_SHA256.to_owned(),
        byte_order: "little".to_owned(),
        orientation: "expert_major_rows_input_columns".to_owned(),
        expert_count: 128,
        top_k: 8,
        weight_scale: 1.0,
        bias_present: false,
        correction_bias_present: false,
    }
}

#[test]
fn committed_public_oracle_closes_every_execution_identity() {
    let oracle = RouterOracle::try_from_value(public_oracle_value())
        .expect("committed public oracle satisfies the Rust gate");
    assert_eq!(oracle.format(), RouterOracleFormat::PublicProjection);
    assert_eq!(oracle.hidden_states().len(), 2 * 2_048);
    assert_eq!(
        mlx_backend::router::canonical_f32le_sha256(oracle.hidden_states()).unwrap(),
        ROUTER_REAL_INPUT_SHA256,
    );

    let single = oracle.reference(ROUTER_REAL_SINGLE_ROW_CASE_ID).unwrap();
    let batch = oracle.reference(ROUTER_REAL_TWO_ROW_CASE_ID).unwrap();
    assert_eq!(single.row_count(), 1);
    assert_eq!(batch.row_count(), 2);
    assert_eq!(single.selected_expert_ids()[0], [114, 45, 99, 46, 98, 74, 102, 65]);
    assert_eq!(batch.selected_expert_ids()[1], [73, 95, 114, 99, 102, 46, 108, 106]);
    assert!(oracle.reference("unregistered-router-case").is_none());
    oracle
        .validate_artifact_binding(&frozen_descriptor(), ROUTER_MODEL_BYTES, ROUTER_MODEL_SHA256)
        .expect("model and tensor are immutable-bound");
    assert_eq!(
        ROUTER_ORACLE_OUTPUT_BUNDLE_SHA256,
        "eba36f9149b61f0d408de3ec5ad6ba73d1ff45b98867a4da56cfc586109ee93f"
    );
}

#[test]
fn external_oracle_envelope_normalizes_to_the_same_frozen_outputs() {
    let public = RouterOracle::try_from_value(public_oracle_value()).unwrap();
    let external = RouterOracle::try_from_value(external_oracle_value())
        .expect("external candidate envelope satisfies the same closed binding");
    assert_eq!(external.format(), RouterOracleFormat::ExternalCandidate);
    assert_eq!(external.hidden_states(), public.hidden_states());
    assert_eq!(
        external.reference(ROUTER_REAL_TWO_ROW_CASE_ID),
        public.reference(ROUTER_REAL_TWO_ROW_CASE_ID),
    );
}

#[test]
fn malformed_oracle_ids_ties_tolerances_and_hashes_fail_closed() {
    type Mutation = (&'static str, Box<dyn Fn(&mut Value)>);
    let mutations: Vec<Mutation> = vec![
        ("unknown root field", Box::new(|value| value["extra"] = json!(true))),
        (
            "case order",
            Box::new(|value| value["input"]["case_ids"][0] = json!("wrong-case")),
        ),
        (
            "cutoff tie",
            Box::new(|value| value["result"]["cutoff_ties"][0] = json!(true)),
        ),
        (
            "logit tolerance",
            Box::new(|value| {
                value["comparison_policy"]["logits"]["absolute_tolerance"] = json!(0.001)
            }),
        ),
        (
            "selected ID",
            Box::new(|value| value["result"]["selected_expert_ids"][0][0] = json!(0)),
        ),
        (
            "input hash",
            Box::new(|value| {
                value["input"]["canonical_f32le_sha256"] = json!("0".repeat(64))
            }),
        ),
        (
            "output hash",
            Box::new(|value| {
                value["result"]["hashes"]["output_bundle_sha256"] = json!("0".repeat(64))
            }),
        ),
    ];
    for (label, mutation) in mutations {
        let mut value = public_oracle_value();
        mutation(&mut value);
        let error = RouterOracle::try_from_value(value)
            .expect_err("mutated oracle must not reach execution");
        assert_eq!(error.code(), "invalid_evidence", "{label}");
    }
}

#[test]
fn artifact_binding_rejects_offset_hash_and_bias_drift() {
    let oracle = RouterOracle::try_from_value(public_oracle_value()).unwrap();
    let mutations: [fn(&mut RouterTensorDescriptor); 3] = [
        |descriptor| descriptor.absolute_data_offset += 4,
        |descriptor| descriptor.encoded_sha256 = "0".repeat(64),
        |descriptor| descriptor.bias_present = true,
    ];
    for mutation in mutations {
        let mut descriptor = frozen_descriptor();
        mutation(&mut descriptor);
        assert_eq!(
            oracle
                .validate_artifact_binding(&descriptor, ROUTER_MODEL_BYTES, ROUTER_MODEL_SHA256)
                .expect_err("tensor drift must fail")
                .code(),
            "model_tensor_mismatch",
        );
    }
    assert!(oracle
        .validate_artifact_binding(
            &frozen_descriptor(),
            ROUTER_MODEL_BYTES,
            &"0".repeat(64),
        )
        .is_err());
}
