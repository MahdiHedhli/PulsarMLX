use f017_runner::json::{sha256_bytes, sha256_file};
use f017_runner::local_boundary::LocalBoundaryFixtureManifest;
use gguf::TensorType;
use std::path::Path;

const RUNTIME_SOURCE_SHA: &str = "b29202171a279cd3bb2ac2cf4dc6b3be7486019e";
const CHECKPOINT_SET_SHA256: &str =
    "d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee";
const SHARD_SHA256: &str = "d94adaa58ddd5abbcf2514192958084416b1aa36bd4d21409028a164341bac36";
const DECODER_SHA256: &str = "b9d0c302ec9761432f55433d8b2b8208d4a366adc875370b7d7493d6cfc3b402";

#[test]
fn public_safe_f32_lane_preserves_ieee_bits() {
    let raw = [1.0f32.to_le_bytes(), (-0.0f32).to_le_bytes()].concat();
    let mut decoded = Vec::new();
    quant::row_to_f32(TensorType::F32, &raw, &mut decoded).expect("F32 lane");
    let rebuilt: Vec<u8> = decoded
        .iter()
        .flat_map(|value| value.to_le_bytes())
        .collect();
    assert_eq!(rebuilt, raw);
}

#[test]
#[ignore = "requires the separately authorized local-only M1-C fixture"]
fn authorized_local_m1_c_fixture_matches_rust_f32_lane_exactly() {
    let path = std::env::var("F017_M1_C_LOCAL_MANIFEST")
        .expect("F017_M1_C_LOCAL_MANIFEST must bind the authorized private fixture");
    let manifest = LocalBoundaryFixtureManifest::load(Path::new(&path)).expect("load manifest");
    manifest.validate_identity().expect("manifest identity");
    manifest.verify_local_fixture().expect("fixture identity");

    assert_eq!(manifest.source_sha, RUNTIME_SOURCE_SHA);
    assert_eq!(manifest.checkpoint_set_sha256, CHECKPOINT_SET_SHA256);
    assert_eq!(manifest.tensor.name, "output_norm.weight");
    assert_eq!(manifest.tensor.shard_sha256, SHARD_SHA256);
    assert_eq!(manifest.tensor.offset, 535_291_744);
    assert_eq!(manifest.tensor.length, 24_576);
    assert_eq!(manifest.tensor.quantization, "F32");
    assert_eq!(manifest.tensor.dimensions, vec![6_144]);
    assert_eq!(manifest.decoder_contract.sha256, DECODER_SHA256);

    let raw = std::fs::read(&manifest.fixture.path).expect("read local fixture");
    assert_eq!(sha256_bytes(&raw), manifest.fixture.sha256);
    assert_eq!(
        sha256_file(&manifest.fixture.path).expect("hash local fixture"),
        manifest.fixture.sha256
    );
    let mut decoded = Vec::new();
    quant::row_to_f32(TensorType::F32, &raw, &mut decoded).expect("decode exact F32 lane");
    assert_eq!(decoded.len(), 6_144);
    assert!(decoded.iter().all(|value| value.is_finite()));
    let rebuilt: Vec<u8> = decoded
        .iter()
        .flat_map(|value| value.to_le_bytes())
        .collect();
    assert_eq!(rebuilt, raw);
    assert_eq!(
        sha256_bytes(&rebuilt),
        manifest.reference.expected_output_sha256
    );
}
