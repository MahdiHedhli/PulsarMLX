//! Synthetic custody tests only. Distinct range patterns are not numerical positives.
use mlx_expert_mlp::selected_snapshot::{Binding, SelectedSnapshot, PAYLOAD_BYTES};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::fs::{File, Permissions};
use std::io::{Read, Seek, SeekFrom, Write};
use std::os::unix::fs::PermissionsExt;
use std::path::PathBuf;
use std::sync::atomic::{AtomicUsize, Ordering};
static NEXT: AtomicUsize = AtomicUsize::new(0);
fn hash(b: &[u8]) -> String {
    format!("{:x}", Sha256::digest(b))
}
fn document() -> Value {
    let prefix = "language_model.model.layers.3.mlp.switch_mlp";
    let modules = ["gate_proj", "up_proj", "down_proj"].map(|r| format!("{prefix}.{r}"));
    let lengths = [4_194_304usize, 262_144, 262_144];
    let hashes: Vec<_> = (0..9)
        .map(|i| hash(&vec![(i + 1) as u8; lengths[i % 3]]))
        .collect();
    let planes:Vec<_>=modules.iter().enumerate().map(|(i,m)|{
        let ranges:Vec<_>=["weight","scales","biases"].iter().enumerate().map(|(j,s)|
            json!({"tensor":format!("{m}.{s}"),"shard":"synthetic.safetensors","begin":0,"len":lengths[j]})).collect();
        json!({"role":(["gate","up","down"][i]),"module":m,"expert":0,"bits":4,"group_size":64,
          "resolved_from":"default","metadata_dtype":"BF16","logical_shape":if i==2 {[4096,2048]} else {[2048,4096]},"ranges":ranges})
    }).collect();
    json!({"schema":"pulsarmlx.selected-expert-snapshot/1",
      "scope":"selected packed content only; no numerical qualification",
      "payload_lengths":lengths.repeat(3),"owned":{
        "schema":"pulsarmlx.bounded-expert-owned/1","owned_bytes":PAYLOAD_BYTES,
        "packed_weights_unchanged":true,"native_calls":0,"whole_shard_reads":0,"whole_shard_hashes":0,
        "scope":"host owned range bytes only; no numerical or full-checkpoint qualification",
        "selected_range_sha256":hashes,"plan":{
          "schema":"pulsarmlx.bounded-expert-plan/1","checkpoint":"synthetic-test",
          "metadata_snapshot_sha256":"a".repeat(64),"metadata_bytes_read":790848,
          "request":{"modules":modules,"expert":0,"experts":288,"d":4096,"h":2048,"bits":[4,4,4],"group_size":64},
          "planes":planes,"selected_bytes":PAYLOAD_BYTES,
          "identity_scope":"metadata snapshot and selected ranges only; no whole-checkpoint payload identity"}}})
}
fn snapshot(doc: &Value, raw_header: Option<Vec<u8>>) -> (PathBuf, Binding) {
    let raw = raw_header.unwrap_or_else(|| serde_json::to_vec(doc).unwrap());
    let path = std::env::temp_dir().join(format!(
        "f020-selected-host-{}-{}.snapshot",
        std::process::id(),
        NEXT.fetch_add(1, Ordering::SeqCst)
    ));
    let mut f = File::create_new(&path).unwrap();
    let prefix = [b"PLSEX001".as_slice(), &(raw.len() as u64).to_le_bytes()].concat();
    f.write_all(&prefix).unwrap();
    f.write_all(&raw).unwrap();
    let size = (16 + raw.len() + PAYLOAD_BYTES) as u64;

    let mut hash = Sha256::new();
    hash.update(&prefix);
    hash.update(&raw);
    for i in 0..9 {
        let block = vec![(i + 1) as u8; [4194304, 262144, 262144][i % 3]];
        hash.update(&block);
        f.write_all(&block).unwrap();
    }
    f.set_permissions(Permissions::from_mode(0o400)).unwrap();
    let binding = Binding {
        snapshot_sha256: format!("{:x}", hash.finalize()),
        snapshot_bytes: size,
        metadata_sha256: "a".repeat(64),
        checkpoint: "synthetic-test".into(),
        ranges_sha256: std::array::from_fn(|i| {
            doc["owned"]["selected_range_sha256"][i]
                .as_str()
                .unwrap()
                .into()
        }),
    };
    (path, binding)
}
#[test]
fn accepts_full_storage_geometry_without_numerical_claim() {
    let (p, b) = snapshot(&document(), None);
    let s = SelectedSnapshot::read(&p, &b).unwrap();
    assert_eq!(s.component(0, 0).unwrap().len(), 4_194_304);
    assert_eq!(s.component(2, 2).unwrap().len(), 262_144);
    assert!(s.component(3, 0).is_none());
    assert!(s.component(0, 3).is_none());
}
#[test]
fn semantic_manifest_controls_refuse_before_payload() {
    let changes = [
        ("/owned/plan/request/expert", json!(1)),
        ("/owned/plan/request/d", json!(2048)),
        ("/owned/plan/planes/0/bits", json!(8)),
        ("/owned/plan/planes/1/role", json!("gate")),
        (
            "/owned/plan/planes/2/module",
            json!("language_model.model.layers.4.mlp.switch_mlp.down_proj"),
        ),
        (
            "/owned/plan/metadata_snapshot_sha256",
            json!("b".repeat(64)),
        ),
        ("/owned/plan/planes/0/ranges/0/len", json!(1)),
        ("/owned/plan/planes/0/ranges/0/shard", json!("../escape")),
        ("/owned/native_calls", json!(1)),
        ("/payload_lengths/0", json!(1)),
        ("/scope", json!("numerically qualified")),
    ];
    for (pointer, value) in changes {
        let mut doc = document();
        *doc.pointer_mut(pointer).unwrap() = value;
        let (p, b) = snapshot(&doc, None);
        assert!(SelectedSnapshot::read(&p, &b).is_err(), "{pointer}");
    }
}
#[test]
fn unknown_and_duplicate_keys_refused() {
    let mut doc = document();
    doc["owned"]["unexpected"] = json!(true);
    let (p, b) = snapshot(&doc, None);
    assert!(SelectedSnapshot::read(&p, &b).is_err());
    let doc = document();
    let raw = serde_json::to_string(&doc).unwrap();
    let duplicated = format!("{{\"schema\":\"duplicate\",{}", &raw[1..]);
    let (p, b) = snapshot(&doc, Some(duplicated.into_bytes()));
    assert!(SelectedSnapshot::read(&p, &b).is_err());
}
#[test]
fn all_nine_hash_bindings_required() {
    let (p, mut b) = snapshot(&document(), None);
    for i in 0..9 {
        let old = b.ranges_sha256[i].clone();
        b.ranges_sha256[i] = "f".repeat(64);
        assert!(SelectedSnapshot::read(&p, &b).is_err());
        b.ranges_sha256[i] = old;
    }
    b.snapshot_sha256 = "f".repeat(64);
    assert!(SelectedSnapshot::read(&p, &b).is_err());
}
#[test]
fn symlink_writable_and_size_bindings_refused() {
    let (p, mut b) = snapshot(&document(), None);
    let link = p.with_extension("link");
    std::os::unix::fs::symlink(&p, &link).unwrap();
    assert!(SelectedSnapshot::read(&link, &b).is_err());
    b.snapshot_bytes += 1;
    assert!(SelectedSnapshot::read(&p, &b).is_err());
    b.snapshot_bytes -= 1;
    std::fs::set_permissions(&p, Permissions::from_mode(0o600)).unwrap();
    assert!(SelectedSnapshot::read(&p, &b).is_err());
}

#[test]
fn selected_preflight_keeps_domains_and_exact_family() {
    use mlx_expert_mlp::selected_adapter::selected_preflight;
    use mlx_native_affine::{dtype::Dtype, fixture::HostTensor};
    for role in 0..3 {
        let (n, k) = if role == 2 {
            (4096, 2048)
        } else {
            (2048, 4096)
        };
        let mut parts = std::array::from_fn(|c| HostTensor {
            name: format!("test-{c}"),
            dtype: if c == 0 { Dtype::U32 } else { Dtype::BF16 },
            shape: vec![n, if c == 0 { k / 8 } else { k / 64 }],
            bytes: vec![0; if c == 0 { n * k / 2 } else { n * k / 32 }],
        });
        let mut x = HostTensor {
            name: "synthetic-input".into(),
            dtype: Dtype::F32,
            shape: vec![1, k],
            bytes: (0..k).flat_map(|_| 1f32.to_le_bytes()).collect(),
        };
        assert_eq!(
            selected_preflight(role, &x, &parts).unwrap(),
            if role == 2 { 145 } else { 273 }
        );
        x.bytes[..4].copy_from_slice(&2f32.powi(-33).to_le_bytes());
        assert!(selected_preflight(role, &x, &parts)
            .unwrap_err()
            .contains("R-DOMAIN-X-RANGE"));
        x.bytes[..4].copy_from_slice(&1f32.to_le_bytes());
        let bf = (2f32.powi(-33).to_bits() >> 16) as u16;
        parts[1].bytes[..2].copy_from_slice(&bf.to_le_bytes());
        assert!(selected_preflight(role, &x, &parts)
            .unwrap_err()
            .contains("R-DOMAIN-META-RANGE"));
        x.shape[0] = 2;
        assert!(selected_preflight(role, &x, &parts)
            .unwrap_err()
            .contains("SELECTED-R-GEOMETRY"));
    }
}

#[test]
fn each_payload_digest_and_equal_length_role_swap_are_detected() {
    let (p, b) = snapshot(&document(), None);
    let mut f = File::open(&p).unwrap();
    let mut prefix = [0u8; 16];
    f.read_exact(&mut prefix).unwrap();
    let start = 16 + u64::from_le_bytes(prefix[8..].try_into().unwrap());
    let lengths = [4194304u64, 262144, 262144];
    let patch = |offset: u64, bytes: &[u8]| {
        std::fs::set_permissions(&p, Permissions::from_mode(0o600)).unwrap();
        let mut f = std::fs::OpenOptions::new().write(true).open(&p).unwrap();
        f.seek(SeekFrom::Start(offset)).unwrap();
        f.write_all(bytes).unwrap();
        f.set_permissions(Permissions::from_mode(0o400)).unwrap();
    };
    let mut offset = start;
    for i in 0..9 {
        patch(offset, &[255]);
        assert_eq!(
            SelectedSnapshot::read(&p, &b).err().unwrap(),
            "SELECTED-R-CUSTODY: original range digest"
        );
        patch(offset, &[(i + 1) as u8]);
        offset += lengths[i % 3];
    }
    let up = start + lengths.iter().sum::<u64>();
    patch(start, &vec![4; 4194304]);
    patch(up, &vec![1; 4194304]);
    assert_eq!(
        SelectedSnapshot::read(&p, &b).err().unwrap(),
        "SELECTED-R-CUSTODY: original range digest"
    );
}

#[test]
fn missing_capture_scope_refused() {
    let mut doc = document();
    doc.as_object_mut().unwrap().remove("scope");
    let (p, b) = snapshot(&doc, None);
    assert!(SelectedSnapshot::read(&p, &b).is_err());
}
