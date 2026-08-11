use engine::f017_parity::{
    run_complete_layer_fixture, run_expert_fixture, run_final_output_fixture,
    run_mla_dense_fixture, run_projection_fixture, run_router_fixture, run_top8_shared_fixture,
    CompleteLayerFixture, ExpertFixture, FinalOutputFixture, MlaDenseFixture, ProjectionDispatch,
    ProjectionFixture, RouterFixture, Top8SharedFixture,
};
use quant::decode_q8_0_matrix;
use serde_json::Value;
use sha2::{Digest, Sha256};
use stream::ValidationClassification;

const ORACLE_BYTES: &[u8] = include_bytes!(
    "../../../specs/017-rust-native-inference-runtime/fixtures/f017-independent-oracle-v1.json"
);
const ORACLE_SHA256: &str = "16ca1e412dbf98d59e19b685b86549567de043ea7e728b254a952540aa783960";
const GENERATOR_SHA: &str = "a9779097de029f26be1cb9fde3543cc517ff153e";

fn oracle() -> Value {
    serde_json::from_slice(ORACLE_BYTES).expect("independent oracle JSON must parse")
}

fn hex_bytes(value: &str) -> Vec<u8> {
    assert_eq!(value.len() % 2, 0, "hex input must contain complete bytes");
    value
        .as_bytes()
        .chunks_exact(2)
        .map(|pair| {
            let text = std::str::from_utf8(pair).expect("hex must be ASCII");
            u8::from_str_radix(text, 16).expect("hex must contain valid digits")
        })
        .collect()
}

fn sha256_f32(values: &[f32]) -> String {
    let mut digest = Sha256::new();
    for value in values {
        digest.update(value.to_le_bytes());
    }
    format!("{:x}", digest.finalize())
}

#[test]
fn independent_oracle_metadata_and_artifact_hash_are_frozen() {
    let document = oracle();
    assert_eq!(format!("{:x}", Sha256::digest(ORACLE_BYTES)), ORACLE_SHA256);
    assert_eq!(document["schema"], "glm52-f017-independent-oracle-v1");
    assert_eq!(document["generator"]["source_commit"], GENERATOR_SHA);
    assert_eq!(document["generator"]["python_version"], "3.13.13");
    assert_eq!(document["generator"]["numpy_version"], "2.4.5");
    assert_eq!(document["independence"]["classification"], "INDEPENDENT");
    assert_eq!(document["independence"]["uses_rust_candidate"], false);
    assert_eq!(
        document["independence"]["uses_rust_reference_functions"],
        false
    );
    assert_eq!(document["independence"]["uses_rust_ffi"], false);
    assert_eq!(document["independence"]["uses_mlx"], false);

    let boundaries = document["boundaries"]
        .as_object()
        .expect("boundaries must be an object");
    assert_eq!(boundaries.len(), 7);
    for name in [
        "projection",
        "router",
        "complete_expert",
        "top8_shared",
        "mla_dense",
        "complete_layer",
        "final_norm_logits_topk",
    ] {
        assert_eq!(boundaries[name]["classification"], "INDEPENDENT");
        assert!(boundaries[name]["fixture_version"]
            .as_str()
            .expect("fixture version must be a string")
            .ends_with("-v2"));
    }
}

#[test]
fn q8_edge_distributions_match_independent_exact_f32_bits() {
    let document = oracle();
    let cases = document["edge_distributions"]["q8_0"]
        .as_array()
        .expect("Q8 edge cases must be an array");
    assert_eq!(cases.len(), 5);
    for case in cases {
        let packed = hex_bytes(
            case["packed_hex"]
                .as_str()
                .expect("packed hex must be present"),
        );
        let mut actual = vec![0.0_f32; 32];
        decode_q8_0_matrix(&packed, 1, 32, &mut actual).expect("edge Q8 block must decode");
        let expected = case["decoded"]
            .as_array()
            .expect("decoded values must be present")
            .iter()
            .map(|value| value.as_f64().expect("decoded value must be numeric") as f32)
            .collect::<Vec<_>>();
        assert!(actual
            .iter()
            .zip(expected.iter())
            .all(|(left, right)| left.to_bits() == right.to_bits()));
        assert_eq!(
            sha256_f32(&actual),
            case["decoded_sha256"]
                .as_str()
                .expect("decoded hash must be present")
        );
    }
}

#[test]
fn ordered_candidate_ladder_matches_independent_oracle() {
    let document = oracle();
    let boundaries = &document["boundaries"];

    let projection = run_projection_fixture(
        &ProjectionFixture::synthetic_q8_0(),
        ProjectionDispatch::ExplicitReference,
    )
    .expect("projection must pass");
    assert_eq!(
        projection.classification,
        ValidationClassification::GoldenIdentical
    );
    assert_eq!(
        projection.reference_output_sha256,
        boundaries["projection"]["expected"]["output_sha256"]
            .as_str()
            .unwrap()
    );

    let router = run_router_fixture(
        &RouterFixture::synthetic(),
        ProjectionDispatch::ExplicitReference,
    )
    .expect("router must pass");
    assert_eq!(
        router.classification,
        ValidationClassification::NumericallyQualifiedGreedyIdentical
    );
    assert_eq!(
        router.output_sha256,
        boundaries["router"]["expected"]["output_sha256"]
            .as_str()
            .unwrap()
    );

    let expert = run_expert_fixture(
        &ExpertFixture::synthetic(),
        ProjectionDispatch::ExplicitReference,
    )
    .expect("complete expert must pass");
    assert_eq!(
        expert.classification,
        ValidationClassification::GoldenIdentical
    );
    assert_eq!(
        expert.output_sha256,
        boundaries["complete_expert"]["expected"]["output_sha256"]
            .as_str()
            .unwrap()
    );

    let top8 = run_top8_shared_fixture(
        &Top8SharedFixture::synthetic(),
        ProjectionDispatch::ExplicitReference,
    )
    .expect("top-8 plus shared must pass");
    assert_eq!(
        top8.output_sha256,
        boundaries["top8_shared"]["expected"]["output_sha256"]
            .as_str()
            .unwrap()
    );

    let mla = run_mla_dense_fixture(
        &MlaDenseFixture::synthetic(),
        ProjectionDispatch::ExplicitReference,
    )
    .expect("MLA/dense must pass");
    assert_eq!(
        mla.output_sha256,
        boundaries["mla_dense"]["expected"]["output_sha256"]
            .as_str()
            .unwrap()
    );

    let layer = run_complete_layer_fixture(
        &CompleteLayerFixture::synthetic(),
        ProjectionDispatch::ExplicitReference,
    )
    .expect("complete layer must pass");
    assert_eq!(
        layer.classification,
        ValidationClassification::GoldenIdentical
    );
    assert_eq!(
        layer.output_sha256,
        boundaries["complete_layer"]["expected"]["output_sha256"]
            .as_str()
            .unwrap()
    );

    let final_output = run_final_output_fixture(
        &FinalOutputFixture::synthetic(),
        ProjectionDispatch::ExplicitReference,
    )
    .expect("final norm/logits/top-k must pass");
    assert_eq!(
        final_output.classification,
        ValidationClassification::NumericallyQualifiedGreedyIdentical
    );
    assert_eq!(final_output.argmax, 0);
    assert_eq!(
        final_output.logits_sha256,
        boundaries["final_norm_logits_topk"]["expected"]["logits_sha256"]
            .as_str()
            .unwrap()
    );
}
