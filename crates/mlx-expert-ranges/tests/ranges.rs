use mlx_expert_ranges::{
    BoundedSource, ExpertRequest, MAX_JSON_BYTES, MAX_ONE_HEADER_BYTES, MAX_SELECTED_BYTES,
};
use serde_json::{json, Value};
use std::fs::{self, File, OpenOptions};
use std::os::unix::fs::{symlink, FileExt, MetadataExt};
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};

static NEXT: AtomicU64 = AtomicU64::new(0);
struct Fixture {
    root: PathBuf,
    request: ExpertRequest,
}
impl Drop for Fixture {
    fn drop(&mut self) {
        fs::remove_dir_all(&self.root).expect("remove only owned temporary test fixture");
    }
}
fn fixture(d: u64, h: u64, e: u64, mixed: bool, gap: u64, write_payload: bool) -> Fixture {
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
fn fidelity(source: &BoundedSource, request: ExpertRequest) {
    let expert = request.expert;
    let plan = source.plan(request).unwrap();
    let want = plan.record().selected_bytes;
    let before = source.requested_payload_bytes();
    let calls = source.payload_read_calls();
    let owned = plan.load().unwrap();
    assert_eq!(source.requested_payload_bytes() - before, want);
    assert_eq!(source.payload_read_calls() - calls, 9);
    for role in 0..3 {
        for component in 0..3 {
            let bytes = owned.bytes(role, component).unwrap();
            assert!(bytes.iter().all(|b| *b == marker(role, expert, component)));
        }
    }
    assert_eq!(owned.receipt()["owned_bytes"], want);
    assert!(owned.bytes(3, 0).is_none());
    assert!(owned.bytes(0, 3).is_none());
}

#[test]
fn every_expert_and_component_stays_packed() {
    let f = fixture(64, 128, 3, false, 0, true);
    let source = BoundedSource::open(&f.root).unwrap();
    assert_eq!(source.requested_payload_bytes(), 0);
    for expert in 0..3 {
        let mut req = f.request.clone();
        req.expert = expert;
        fidelity(&source, req);
    }
}
#[test]
fn mixed_overrides_are_bound_per_role() {
    let f = fixture(128, 64, 3, true, 0, true);
    let source = BoundedSource::open(&f.root).unwrap();
    let p = source.plan(f.request.clone()).unwrap();
    assert_eq!(
        p.record()
            .planes
            .iter()
            .map(|p| p.resolved_from.as_str())
            .collect::<Vec<_>>(),
        ["override", "default", "override"]
    );
    fidelity(&source, f.request.clone());
    let mut wrong = f.request.clone();
    wrong.bits = [4, 4, 4];
    expect_phase(source.plan(wrong), "RECIPE");
}
#[test]
fn owned_bytes_survive_source_drop_and_owner_move() {
    let f = fixture(64, 64, 3, false, 0, true);
    let owned = {
        let s = BoundedSource::open(&f.root).unwrap();
        s.plan(f.request.clone()).unwrap().load().unwrap()
    };
    let address = owned.bytes(0, 0).unwrap().as_ptr();
    let mut owners = Vec::new();
    owners.push(owned);
    for _ in 0..8 {
        owners.reserve(owners.capacity() + 1);
    }
    assert_eq!(address, owners[0].bytes(0, 0).unwrap().as_ptr());
    assert!(owners[0]
        .bytes(2, 2)
        .unwrap()
        .iter()
        .all(|b| *b == marker(2, 0, 2)));
}
#[test]
fn invalid_binding_refuses_before_payload() {
    let f = fixture(64, 128, 3, false, 0, true);
    let s = BoundedSource::open(&f.root).unwrap();
    let mut q = f.request.clone();
    q.expert = 3;
    expect_phase(s.plan(q), "INDEX");
    let mut q = f.request.clone();
    q.d = 128;
    expect_phase(s.plan(q), "GEOMETRY");
    let mut q = f.request.clone();
    q.modules[1] = q.modules[0].clone();
    expect_phase(s.plan(q), "MODULE");
    let mut q = f.request.clone();
    q.group_size = 32;
    expect_phase(s.plan(q), "RECIPE");
    assert_eq!(s.requested_payload_bytes(), 0);
    assert_eq!(s.payload_read_calls(), 0);
}
#[test]
fn selected_budget_refuses_without_reading_large_sparse_planes() {
    let f = fixture(8192, 8192, 1, false, 0, false);
    let s = BoundedSource::open(&f.root).unwrap();
    expect_phase(s.plan(f.request.clone()), "BUDGET");
    assert_eq!(s.requested_payload_bytes(), 0);
    assert_eq!(s.payload_read_calls(), 0);
    assert!(
        MAX_SELECTED_BYTES
            < fs::metadata(f.root.join("model.safetensors"))
                .unwrap()
                .len()
    );
}
#[test]
fn same_size_payload_mutation_refuses_before_first_read() {
    let f = fixture(64, 64, 3, false, 0, true);
    let s = BoundedSource::open(&f.root).unwrap();
    let p = s.plan(f.request.clone()).unwrap();
    let at = p.record().planes[0].ranges[0].begin;
    let file = OpenOptions::new()
        .write(true)
        .open(f.root.join("model.safetensors"))
        .unwrap();
    std::thread::sleep(std::time::Duration::from_millis(2));
    file.write_all_at(&[200], at).unwrap();
    expect_phase(p.load(), "MUTATION");
    assert_eq!(s.payload_read_calls(), 0);
}
#[test]
fn truncated_descriptor_refuses_before_first_read() {
    let f = fixture(64, 64, 3, false, 0, true);
    let s = BoundedSource::open(&f.root).unwrap();
    let p = s.plan(f.request.clone()).unwrap();
    OpenOptions::new()
        .write(true)
        .open(f.root.join("model.safetensors"))
        .unwrap()
        .set_len(8)
        .unwrap();
    expect_phase(p.load(), "MUTATION");
    assert_eq!(s.requested_payload_bytes(), 0);
}
#[test]
fn changed_config_refuses_before_first_read() {
    let f = fixture(64, 64, 3, false, 0, true);
    let s = BoundedSource::open(&f.root).unwrap();
    let p = s.plan(f.request.clone()).unwrap();
    std::thread::sleep(std::time::Duration::from_millis(2));
    OpenOptions::new()
        .write(true)
        .open(f.root.join("config.json"))
        .unwrap()
        .write_all_at(b" ", 0)
        .unwrap();
    expect_phase(p.load(), "MUTATION");
    assert_eq!(s.requested_payload_bytes(), 0);
}
#[test]
fn symlink_shard_and_config_are_refused() {
    for name in ["model.safetensors", "config.json"] {
        let f = fixture(64, 64, 3, false, 0, true);
        let old = f.root.join("original");
        fs::rename(f.root.join(name), &old).unwrap();
        symlink(&old, f.root.join(name)).unwrap();
        expect_phase(BoundedSource::open(&f.root), "PATH");
    }
}
#[test]
fn index_path_escape_and_duplicate_config_are_refused() {
    let f = fixture(64, 64, 3, false, 0, true);
    let path = f.root.join("model.safetensors.index.json");
    let mut index: Value = serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
    index["weight_map"]["fixture.gate.weight"] = json!("../escape.safetensors");
    fs::write(&path, serde_json::to_vec(&index).unwrap()).unwrap();
    expect_phase(BoundedSource::open(&f.root), "INDEX");
    let f = fixture(64, 64, 3, false, 0, true);
    fs::write(
        f.root.join("config.json"),
        br#"{"quantization":{"bits":4,"bits":8,"group_size":64}}"#,
    )
    .unwrap();
    expect_phase(BoundedSource::open(&f.root), "CONFIG");
}
#[test]
fn metadata_limits_refuse_before_large_allocation() {
    let f = fixture(64, 64, 3, false, 0, true);
    OpenOptions::new()
        .write(true)
        .open(f.root.join("config.json"))
        .unwrap()
        .set_len(MAX_JSON_BYTES + 1)
        .unwrap();
    expect_phase(BoundedSource::open(&f.root), "LIMIT");
    let f = fixture(64, 64, 3, false, 0, true);
    OpenOptions::new()
        .write(true)
        .open(f.root.join("model.safetensors"))
        .unwrap()
        .write_all_at(&(MAX_ONE_HEADER_BYTES + 1).to_le_bytes(), 0)
        .unwrap();
    expect_phase(BoundedSource::open(&f.root), "LIMIT");
}
#[test]
fn huge_sparse_decoy_is_never_loaded_or_hashed() {
    let gap = 8 * 1024 * 1024 * 1024u64;
    let f = fixture(64, 64, 3, false, gap, true);
    let m = fs::metadata(f.root.join("model.safetensors")).unwrap();
    assert!(m.len() > gap);
    assert!(m.blocks() * 512 < 1024 * 1024);
    let s = BoundedSource::open(&f.root).unwrap();
    let p = s.plan(f.request.clone()).unwrap();
    assert!(p.record().planes[0].ranges[0].begin > gap);
    assert_eq!(s.requested_payload_bytes(), 0);
    fidelity(&s, f.request.clone());
    assert!(s.requested_payload_bytes() < MAX_SELECTED_BYTES);
    println!(
        "sparse_case logical_file_bytes={} physical_bytes={} requested_payload_bytes={} read_calls={}",
        m.len(),
        m.blocks() * 512,
        s.requested_payload_bytes(),
        s.payload_read_calls()
    );
}
#[test]
fn descriptor_stays_bound_after_shard_name_replacement() {
    let f = fixture(64, 64, 3, false, 0, true);
    let s = BoundedSource::open(&f.root).unwrap();
    let p = s.plan(f.request.clone()).unwrap();
    // The admitted object remains authoritative after a rename; opening the new
    // pathname would read these wrong bytes. Owned descriptor access must not.
    fs::rename(
        f.root.join("model.safetensors"),
        f.root.join("old.safetensors"),
    )
    .unwrap();
    fs::write(f.root.join("model.safetensors"), b"not the admitted shard").unwrap();
    // Rename can change ctime; the stamp guard may conservatively refuse the
    // old object, but it must never read or accept the replacement.
    match p.load() {
        Ok(o) => assert!(o.bytes(0, 0).unwrap().iter().all(|b| *b == marker(0, 0, 0))),
        Err(e) => assert_eq!(e.phase, "MUTATION"),
    }
}
#[test]
fn stored_wrong_weight_dtype_is_not_reinterpreted() {
    let f = fixture(64, 64, 3, false, 0, true);
    let file = OpenOptions::new()
        .read(true)
        .write(true)
        .open(f.root.join("model.safetensors"))
        .unwrap();
    let mut prefix = [0; 8];
    file.read_exact_at(&mut prefix, 0).unwrap();
    let mut bytes = vec![0; u64::from_le_bytes(prefix) as usize];
    file.read_exact_at(&mut bytes, 8).unwrap();
    let header = String::from_utf8(bytes)
        .unwrap()
        .replace("\"U32\"", "\"F32\"");
    file.write_all_at(header.as_bytes(), 8).unwrap();
    let s = BoundedSource::open(&f.root).unwrap();
    expect_phase(s.plan(f.request.clone()), "RESOLVE");
    assert_eq!(s.requested_payload_bytes(), 0);
}
#[test]
fn malformed_and_overflowing_headers_fail_catalog_admission() {
    for header in [br#"{"bad":0}"#.as_slice(),br#"{"fixture.gate.weight":{"dtype":"U32","shape":[18446744073709551615,2],"data_offsets":[0,8]}}"#.as_slice()] {
        let f=fixture(64,64,3,false,0,true);let file=OpenOptions::new().write(true).truncate(true).open(f.root.join("model.safetensors")).unwrap();
        file.set_len(8+header.len() as u64+8).unwrap();file.write_all_at(&(header.len() as u64).to_le_bytes(),0).unwrap();file.write_all_at(header,8).unwrap();
        expect_phase(BoundedSource::open(&f.root),"CATALOG");
    }
}
#[test]
fn nonregular_index_refuses_at_descriptor_admission() {
    let f = fixture(64, 64, 3, false, 0, true);
    let path = f.root.join("model.safetensors.index.json");
    fs::remove_file(&path).unwrap();
    fs::create_dir(path).unwrap();
    expect_phase(BoundedSource::open(&f.root), "PATH");
}
#[test]
fn shard_count_and_aggregate_header_limits_are_checked() {
    for count in [33, 9] {
        let f = fixture(64, 64, 3, false, 0, true);
        let mut map = serde_json::Map::new();
        for n in 0..count {
            let name = format!("model-{n:02}.safetensors");
            map.insert(format!("tensor{n}"), json!(name));
            if count == 9 {
                let header_len = MAX_ONE_HEADER_BYTES - 8;
                let file = File::create(f.root.join(&name)).unwrap();
                file.set_len(8 + header_len).unwrap();
                file.write_all_at(&header_len.to_le_bytes(), 0).unwrap();
                file.write_all_at(&vec![b' '; header_len as usize], 8)
                    .unwrap();
            }
        }
        fs::write(
            f.root.join("model.safetensors.index.json"),
            serde_json::to_vec(&json!({"weight_map":map})).unwrap(),
        )
        .unwrap();
        expect_phase(BoundedSource::open(&f.root), "LIMIT");
    }
}
