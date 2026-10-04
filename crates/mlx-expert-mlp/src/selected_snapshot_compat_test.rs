//! Exercise the accepted capture writer, not a replica of its header encoder.
//! Small synthetic geometry checks structural compatibility only, never admission.
use super::Header;
use mlx_expert_ranges::{snapshot::freeze_selected, BoundedSource, ExpertRequest};
use serde_json::json;
use std::io::Write;

#[test]
fn original_capture_writer_header_deserializes_strictly() {
    let root = std::env::temp_dir().join(format!(
        "f020-writer-compat-{}-{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    std::fs::create_dir(&root).unwrap();
    let modules = ["fixture.gate", "fixture.up", "fixture.down"].map(String::from);
    let request = ExpertRequest {
        modules: modules.clone(),
        expert: 0,
        experts: 3,
        d: 64,
        h: 128,
        bits: [4; 3],
        group_size: 64,
    };
    let mut tensors = serde_json::Map::new();
    let mut weights = serde_json::Map::new();
    let mut payload = Vec::new();
    for (role, module) in modules.iter().enumerate() {
        let (n, k) = if role == 2 { (64, 128) } else { (128, 64) };
        for (component, suffix) in ["weight", "scales", "biases"].iter().enumerate() {
            let cols = if component == 0 { k / 8 } else { k / 64 };
            let bytes = if component == 0 { 4 } else { 2 };
            let begin = payload.len();
            payload.resize(
                begin + 3 * n * cols * bytes,
                (role * 3 + component + 1) as u8,
            );
            let name = format!("{module}.{suffix}");
            tensors.insert(
                name.clone(),
                json!({"dtype":if component==0 {"U32"} else {"BF16"},
                "shape":[3,n,cols],"data_offsets":[begin,payload.len()]}),
            );
            weights.insert(name, json!("model.safetensors"));
        }
    }
    let header = serde_json::to_vec(&tensors).unwrap();
    let mut shard = std::fs::File::create_new(root.join("model.safetensors")).unwrap();
    shard
        .write_all(&(header.len() as u64).to_le_bytes())
        .unwrap();
    shard.write_all(&header).unwrap();
    shard.write_all(&payload).unwrap();
    std::fs::write(
        root.join("config.json"),
        br#"{"quantization":{"bits":4,"group_size":64}}"#,
    )
    .unwrap();
    std::fs::write(
        root.join("model.safetensors.index.json"),
        serde_json::to_vec(&json!({"metadata":{"total_size":payload.len()},"weight_map":weights}))
            .unwrap(),
    )
    .unwrap();
    let source = BoundedSource::open(&root).unwrap();
    let plan = source.plan(request).unwrap();
    let output = root.join("writer.snapshot");
    let receipt = freeze_selected(&plan, &plan.record().metadata_snapshot_sha256, &output).unwrap();
    assert_eq!(receipt.payload_read_calls, 9);
    let raw = std::fs::read(output).unwrap();
    assert_eq!(&raw[..8], b"PLSEX001");
    let length = u64::from_le_bytes(raw[8..16].try_into().unwrap()) as usize;
    let parsed: Header = serde_json::from_slice(&raw[16..16 + length]).unwrap();
    assert_eq!(parsed.schema, "pulsarmlx.selected-expert-snapshot/1");
    assert_eq!(
        parsed.scope,
        "selected packed content only; no numerical qualification"
    );
    assert_eq!(
        parsed.payload_lengths.iter().sum::<usize>(),
        raw.len() - 16 - length
    );
    assert_eq!(parsed.owned.plan.request.d, 64);
    // Retain this wholly synthetic fixture for inspection; no real content read.
}
