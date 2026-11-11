mod support;
use mlx_expert_ranges::{BoundedSource, ExpertRole, PlaneDestination};
use sha2::{Digest, Sha256};

#[test]
fn all_roles_experts_recipes_match_independent_allocating_loader() {
    for mixed in [false, true] {
        let f = support::fixture(128, 64, 3, mixed, 0, true);
        let source = BoundedSource::open(&f.root).unwrap();
        for expert in 0..3 {
            let mut request = f.request.clone();
            request.expert = expert;
            let plan = source.plan(request).unwrap();
            let control = plan.load().unwrap();
            for role in [ExpertRole::Gate, ExpertRole::Up, ExpertRole::Down] {
                let expected = std::array::from_fn(|c| {
                    format!(
                        "{:x}",
                        Sha256::digest(control.bytes(role.index(), c).unwrap())
                    )
                });
                let mut parts: [Vec<u8>; 3] = std::array::from_fn(|c| {
                    vec![0xa5; control.bytes(role.index(), c).unwrap().len()]
                });
                let [w, s, b] = &mut parts;
                let before = (
                    source.requested_payload_bytes(),
                    source.payload_read_calls(),
                );
                let receipt = plan
                    .read_plane_into(role, PlaneDestination::new(w, s, b, expected.clone()))
                    .unwrap()
                    .into_receipt();
                assert_eq!(receipt.actual_sha256, expected);
                assert_eq!(receipt.role, role);
                assert_eq!(receipt.plane.expert, expert);
                assert_eq!(
                    receipt.metadata_snapshot_sha256,
                    plan.record().metadata_snapshot_sha256
                );
                assert_eq!(source.payload_read_calls() - before.1, 3);
                assert_eq!(
                    source.requested_payload_bytes() - before.0,
                    receipt.requested_bytes
                );
                for c in 0..3 {
                    assert_eq!(parts[c], control.bytes(role.index(), c).unwrap());
                }
            }
        }
    }
}

#[test]
fn every_bad_destination_length_refuses_before_any_write_or_read() {
    let f = support::fixture(128, 64, 3, false, 0, true);
    let source = BoundedSource::open(&f.root).unwrap();
    let plan = source.plan(f.request.clone()).unwrap();
    for c in 0..3 {
        for delta in [-1i64, 1] {
            let mut parts: [Vec<u8>; 3] = std::array::from_fn(|i| {
                vec![
                    0xa5;
                    (plan.record().planes[0].ranges[i].len as i64 + if i == c { delta } else { 0 })
                        as usize
                ]
            });
            let [w, s, b] = &mut parts;
            assert!(
                matches!(plan.read_plane_into(ExpertRole::Gate,PlaneDestination::new(w,s,b,std::array::from_fn(|_| "0".repeat(64)))),Err(e) if e.phase=="DESTINATION")
            );
            assert!(parts.iter().flatten().all(|b| *b == 0xa5));
        }
    }
    assert_eq!(source.payload_read_calls(), 0);
}

#[test]
fn changed_descriptor_and_wrong_content_never_publish_a_filled_capability() {
    use std::os::unix::fs::FileExt;
    let f = support::fixture(128, 64, 3, false, 0, true);
    let source = BoundedSource::open(&f.root).unwrap();
    let plan = source.plan(f.request.clone()).unwrap();
    let mut parts: [Vec<u8>; 3] =
        std::array::from_fn(|i| vec![0xa5; plan.record().planes[0].ranges[i].len as usize]);
    let [w, s, b] = &mut parts;
    assert!(
        matches!(plan.read_plane_into(ExpertRole::Gate,PlaneDestination::new(w,s,b,std::array::from_fn(|_| "0".repeat(64)))),Err(e) if e.phase=="CONTENT")
    );
    assert_eq!(source.payload_read_calls(), 1);
    assert!(parts[1].iter().all(|b| *b == 0xa5));
    std::fs::OpenOptions::new()
        .write(true)
        .open(f.root.join("model.safetensors"))
        .unwrap()
        .write_all_at(&[0], plan.record().planes[0].ranges[0].begin)
        .unwrap();
    let [w, s, b] = &mut parts;
    assert!(
        matches!(plan.read_plane_into(ExpertRole::Gate,PlaneDestination::new(w,s,b,std::array::from_fn(|_| "0".repeat(64)))),Err(e) if e.phase=="MUTATION")
    );
    assert_eq!(source.payload_read_calls(), 1);
}
