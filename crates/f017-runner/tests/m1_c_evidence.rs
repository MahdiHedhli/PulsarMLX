use f017_runner::json::{parse_json_no_duplicates, sha256_bytes};
use serde_json::Value;

const EXPECTED_EVIDENCE_SHA256: &str =
    "343548afefd4edbe844f0645c63cf0b9cb53edfcdbfc3b3d8e4b15f7c6c3041e";
const EXPECTED_RUNTIME_SHA: &str = "b29202171a279cd3bb2ac2cf4dc6b3be7486019e";
const EXPECTED_PAYLOAD_SHA256: &str =
    "5ed2cdb29cd2c920a2b2b0d3fc5a0f0912593924ce7e2fd7ff8ca994803b8e77";

fn u64_at(value: &Value, pointer: &str) -> u64 {
    value
        .pointer(pointer)
        .and_then(Value::as_u64)
        .unwrap_or_else(|| panic!("missing unsigned integer at {pointer}"))
}

#[test]
fn banked_m1_c_evidence_passes_the_frozen_single_tensor_and_zero_compute_gate() {
    let bytes = include_bytes!(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../docs/architecture/reviews/evidence/f017-m1-c-real-tensor-v1.json"
    ));
    assert_eq!(sha256_bytes(bytes), EXPECTED_EVIDENCE_SHA256);
    let evidence: Value = parse_json_no_duplicates(bytes).expect("duplicate-safe M1-C JSON");

    assert_eq!(evidence["result"], "M1-C ACCEPTED");
    assert_eq!(evidence["attempt"], 1);
    assert_eq!(evidence["runtime_source_sha"], EXPECTED_RUNTIME_SHA);
    assert_eq!(
        evidence["admission"]["environment_kind"],
        "production_reviewed"
    );
    assert_eq!(evidence["admission"]["telemetry_source"], "measured_host");
    assert_eq!(evidence["tensor"]["name"], "output_norm.weight");
    assert_eq!(evidence["tensor"]["gguf_type"], "F32");
    assert_eq!(
        evidence["tensor"]["payload_sha256"],
        EXPECTED_PAYLOAD_SHA256
    );
    assert_eq!(u64_at(&evidence, "/tensor/byte_length"), 24_576);
    assert_eq!(u64_at(&evidence, "/f32_validation/element_count"), 6_144);
    assert_eq!(u64_at(&evidence, "/isolation/shard_open_count"), 1);
    assert_eq!(u64_at(&evidence, "/isolation/positional_read_count"), 1);
    assert_eq!(u64_at(&evidence, "/isolation/tensor_payload_count"), 1);
    for pointer in [
        "/isolation/tensor_execution_count",
        "/isolation/quant_decode_count",
        "/isolation/mlx_compute_count",
        "/isolation/model_compute_dispatch_count",
        "/isolation/projection_count",
        "/isolation/expert_execution_count",
        "/isolation/layer_execution_count",
        "/isolation/logits_execution_count",
    ] {
        assert_eq!(
            u64_at(&evidence, pointer),
            0,
            "nonzero isolation field {pointer}"
        );
    }
    assert_eq!(
        evidence["f32_validation"]["independent_python_ieee754_reparse_identical"],
        true
    );
    assert_eq!(
        evidence["f32_validation"]["rust_quant_row_to_f32_bits_identical"],
        true
    );
    assert_eq!(evidence["validation"]["local_manifest_validated"], true);
    assert_eq!(
        evidence["validation"]["pass_persisted_after_final_fixture_validation"],
        true
    );
    assert_eq!(evidence["privacy"]["payload_committed"], false);
    assert_eq!(
        evidence["privacy"]["absolute_paths_in_public_evidence"],
        false
    );
}
