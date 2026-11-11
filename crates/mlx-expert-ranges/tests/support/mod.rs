#![allow(dead_code, unused_imports)]
use mlx_expert_ranges::{
    BoundedSource, ExpertRequest, MAX_JSON_BYTES, MAX_ONE_HEADER_BYTES, MAX_SELECTED_BYTES,
};
use serde_json::{json, Value};
use std::fs::{self, File, OpenOptions};
use std::os::unix::fs::{symlink, FileExt, MetadataExt};
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};

static NEXT: AtomicU64 = AtomicU64::new(0);
pub struct Fixture {
    pub root: PathBuf,
    pub request: ExpertRequest,
}
impl Drop for Fixture {
    fn drop(&mut self) {
        fs::remove_dir_all(&self.root).expect("remove only owned temporary test fixture");
    }
}
pub fn fixture(d: u64, h: u64, e: u64, mixed: bool, gap: u64, write_payload: bool) -> Fixture {
    let parent = std::env::var_os("PULSARMLX_RANGE_TEST_ROOT")
        .map(PathBuf::from)
        .unwrap_or_else(std::env::temp_dir);
    let root = parent.join(format!(
        "pulsar-range-{}-{}",
        std::process::id(),
        NEXT.fetch_add(1, Ordering::Relaxed)
    ));
    fs::create_dir_all(&root).unwrap();
    let modules = ["fixture.gate", "fixture.up", "fixture.down"].map(String::from);
    let bits = if mixed { [8, 4, 8] } else { [4, 4, 4] };
    let request = ExpertRequest {
        modules: modules.clone(),
        expert: 0,
        experts: e,
        d,
        h,
        bits,
        group_size: 64,
    };
    let mut tensors = serde_json::Map::new();
    let mut weights = serde_json::Map::new();
    let mut offset = 0;
    if gap > 0 {
        tensors.insert(
            "decoy".into(),
            json!({"dtype":"U8","shape":[gap/1024,1024],"data_offsets":[0,gap]}),
        );
        weights.insert("decoy".into(), json!("model.safetensors"));
        offset = gap;
    }
    let mut payloads = Vec::new();
    for role in 0..3 {
        let [n, k] = if role == 2 { [d, h] } else { [h, d] };
        for component in 0..3 {
            let name = format!(
                "{}.{}",
                modules[role],
                ["weight", "scales", "biases"][component]
            );
            let cols = if component == 0 {
                k * bits[role] as u64 / 32
            } else {
                k / 64
            };
            let size = if component == 0 { 4 } else { 2 };
            let plane_len = n * cols * size;
            tensors.insert(name.clone(),json!({"dtype":if component==0{"U32"}else{"BF16"},"shape":[e,n,cols],"data_offsets":[offset,offset+e*plane_len]}));
            weights.insert(name, json!("model.safetensors"));
            if write_payload {
                for expert in 0..e {
                    payloads.push((
                        offset + expert * plane_len,
                        plane_len,
                        marker(role, expert, component),
                    ));
                }
            }
            offset += e * plane_len;
        }
    }
    let header = serde_json::to_vec(&Value::Object(tensors)).unwrap();
    let base = 8 + header.len() as u64;
    let file = File::create(root.join("model.safetensors")).unwrap();
    file.set_len(base + offset).unwrap();
    file.write_all_at(&(header.len() as u64).to_le_bytes(), 0)
        .unwrap();
    file.write_all_at(&header, 8).unwrap();
    for (begin, len, value) in payloads {
        file.write_all_at(&vec![value; len as usize], base + begin)
            .unwrap();
    }
    fs::write(
        root.join("model.safetensors.index.json"),
        serde_json::to_vec(&json!({"metadata":{"total_size":offset},"weight_map":weights}))
            .unwrap(),
    )
    .unwrap();
    let mut quant = json!({"bits":4,"group_size":64});
    if mixed {
        for role in [0, 2] {
            quant[&modules[role]] = json!({"bits":8,"group_size":64});
        }
    }
    fs::write(
        root.join("config.json"),
        serde_json::to_vec(&json!({"quantization":quant})).unwrap(),
    )
    .unwrap();
    Fixture { root, request }
}
fn marker(role: usize, expert: u64, component: usize) -> u8 {
    (1 + role * 40 + expert as usize * 7 + component) as u8
}
fn expect_phase<T>(result: Result<T, mlx_expert_ranges::Refusal>, phase: &str) {
    match result {
        Err(e) => assert_eq!(e.phase, phase, "{e}"),
        Ok(_) => panic!("expected {phase} refusal"),
    }
}
