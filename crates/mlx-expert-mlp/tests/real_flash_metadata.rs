//! Optional physical N3 metadata check: no payload reads and no native library calls.
use mlx_expert_ranges::{BoundedSource, ExpertRequest};
use serde_json::Value;
#[test]
fn sealed_original_geometry_or_host_fixture_only() {
    let Some(root) = std::env::var_os("STUDIO016_METADATA_ROOT") else {
        return;
    };
    let path = std::path::PathBuf::from(root);
    assert_eq!(path.canonicalize().unwrap(), path);
    let src = BoundedSource::open(&path).unwrap();
    let req = ExpertRequest {
        expert: 0,
        experts: 288,
        d: 4096,
        h: 2048,
        bits: [4; 3],
        group_size: 64,
        modules: ["gate", "up", "down"]
            .map(|r| format!("language_model.model.layers.3.mlp.switch_mlp.{r}_proj")),
    };
    let pin: Value = serde_json::from_str(include_str!("../src/real_binding.json")).unwrap();
    let plan = src.plan(req.clone()).unwrap();
    assert_eq!(plan.record().selected_bytes, 14_155_776);
    assert_eq!(
        plan.record().metadata_snapshot_sha256,
        pin["metadata_snapshot_sha256"]
    );
    for (i, r) in plan
        .record()
        .planes
        .iter()
        .flat_map(|p| &p.ranges)
        .enumerate()
    {
        let a = &pin["ranges"][i];
        assert_eq!(r.tensor, a["tensor"]);
        assert_eq!(r.shard, a["shard"]);
        assert_eq!(r.len, a["len"]);
        assert_eq!(r.begin, a["begin"]);
    }
    let mut bad = req.clone();
    bad.bits[1] = 8;
    assert!(src.plan(bad).is_err());
    let mut bad = req.clone();
    bad.modules[0].push_str(".wrong");
    assert!(src.plan(bad).is_err());
    let mut bad = req.clone();
    bad.expert = 288;
    assert!(src.plan(bad).is_err());
    let mut bad = req;
    bad.d = u64::MAX;
    assert!(src.plan(bad).is_err());
    assert_eq!(
        (src.payload_read_calls(), src.requested_payload_bytes()),
        (0, 0)
    );
}
