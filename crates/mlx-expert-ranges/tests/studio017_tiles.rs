#![cfg(feature = "studio017")]
mod support;
use mlx_expert_ranges::{flash_tiles::FlashRows, BoundedSource};
use serde_json::{json, Value};
use std::{
    fs,
    os::unix::fs::{FileExt, MetadataExt},
};
#[test]
fn binds_descriptor_and_plane_before_copy_and_refuses_mutated_source() {
    let f = support::fixture(64, 128, 3, false, 0, true);
    let root = f.root.canonicalize().unwrap();
    let shard = root.join("model.safetensors");
    let old = fs::read(&shard).unwrap();
    let n = u64::from_le_bytes(old[..8].try_into().unwrap()) as usize;
    let hdr = std::str::from_utf8(&old[8..8 + n])
        .unwrap()
        .replace("fixture.", "language_model.fixture.");
    let mut data = (hdr.len() as u64).to_le_bytes().to_vec();
    data.extend(hdr.as_bytes());
    data.extend(&old[8 + n..]);
    fs::write(&shard, data).unwrap();
    for n in ["config.json", "model.safetensors.index.json"] {
        let p = root.join(n);
        let t = fs::read_to_string(&p)
            .unwrap()
            .replace("fixture.", "language_model.fixture.");
        fs::write(p, t).unwrap()
    }
    let src = BoundedSource::open(&root).unwrap();
    let mut witness = json!({});
    for name in [
        "config.json",
        "model.safetensors.index.json",
        "model.safetensors",
    ] {
        let m = root.join(name).metadata().unwrap();
        witness[name] = json!([
            m.dev(),
            m.ino(),
            m.len(),
            m.mtime() * 1_000_000_000 + m.mtime_nsec(),
            m.ctime() * 1_000_000_000 + m.ctime_nsec()
        ]);
    }
    assert!(FlashRows::new(&root, "wrong", &witness).is_err());
    let mut bad = witness.clone();
    bad["model.safetensors"][1] = Value::from(0);
    assert!(FlashRows::new(&root, src.metadata_snapshot(), &bad).is_err());
    let reader = FlashRows::new(&root, src.metadata_snapshot(), &witness).unwrap();
    assert!(reader.matrix("vision_model.fixture.gate", Some(2)).is_err());
    assert!(reader
        .matrix("language_model.fixture.gate", Some(3))
        .is_err());
    let m = reader
        .matrix("language_model.fixture.gate", Some(2))
        .unwrap();
    assert!(reader.tile(&m, 0, 65).is_err() && reader.tile(&m, 127, 2).is_err());
    assert_eq!(reader.finish().unwrap(), (0, 0));
    let parts = reader.tile(&m, 17, 3).unwrap();
    for (i, b) in parts.iter().enumerate() {
        assert!(b.iter().all(|&v| v == 15 + i as u8))
    }
    let fd = fs::OpenOptions::new().write(true).open(&shard).unwrap();
    fd.set_len(fd.metadata().unwrap().len() - 1).unwrap();
    fd.write_at(&[0], 8).unwrap();
    assert!(reader.tile(&m, 20, 3).is_err());
    assert!(reader.finish().is_err());
}
