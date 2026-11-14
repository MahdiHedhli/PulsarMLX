use mlx_expert_ranges::{
    read_into::{aligned_transport::*, ExpertRole, PlaneDestination},
    BoundedSource, ExpertRequest,
};
use serde_json::{json, Value};
use std::{
    fs,
    io::Write,
    path::{Path, PathBuf},
};

fn destination<'a>(parts: &'a mut [Vec<u8>; 3], expected: &[String; 3]) -> PlaneDestination<'a> {
    let [w, s, b] = parts;
    PlaneDestination::new(w, s, b, expected.clone())
}

#[test]
fn all_original_roles_match_exact_reader_in_both_buffered_modes() {
    let dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../fixtures/resident-expert-mlp");
    let manifest: Value =
        serde_json::from_slice(&fs::read(dir.join("manifest.json")).unwrap()).unwrap();
    let mut log = std::env::var_os("WINDOW_CAPTURE_DIR")
        .map(|root| fs::File::create(PathBuf::from(root).join("real.jsonl")).unwrap());
    let mut count = 0;
    for profile in ["default", "mixed"] {
        let recipe = &manifest["recipes"][profile];
        let root = dir.join(recipe["name"].as_str().unwrap());
        let source = BoundedSource::open(&root).unwrap();
        for expert in 0..3 {
            let planes = &recipe["planes"][expert];
            let plan = source
                .plan(ExpertRequest {
                    expert: expert as u64,
                    experts: 3,
                    d: 128,
                    h: 64,
                    group_size: 64,
                    modules: std::array::from_fn(|i| planes[i]["module"].as_str().unwrap().into()),
                    bits: std::array::from_fn(|i| planes[i]["bits"].as_u64().unwrap() as u32),
                })
                .unwrap();
            for role in [ExpertRole::Gate, ExpertRole::Up, ExpertRole::Down] {
                let plane = &planes[role.index()];
                let original: [String; 3] =
                    std::array::from_fn(|i| plane["sha256"][i].as_str().unwrap().into());
                let mut reference: [Vec<u8>; 3] = std::array::from_fn(|i| {
                    vec![0; plane["ranges"][i]["len"].as_u64().unwrap() as usize]
                });
                let old = plan
                    .read_plane_into(role, destination(&mut reference, &original))
                    .unwrap()
                    .into_receipt();
                for a in [4096, 16384] {
                    let window = WindowPlan::new(&plan, role, a).unwrap();
                    let budget = window.minimum_reservation();
                    let mut scratch = Scratch::new(&window, budget).unwrap();
                    for mode in [Mode::BufferedExact, Mode::BufferedAlignedWindow] {
                        let mut out = reference.each_ref().map(|r| vec![0xcd; r.len()]);
                        let before = (
                            source.payload_read_calls(),
                            source.requested_payload_bytes(),
                        );
                        let (verified, r) = window
                            .read(mode, &mut scratch, destination(&mut out, &original), budget)
                            .unwrap()
                            .into_parts();
                        let inherited = verified.into_receipt();
                        assert_eq!(
                            serde_json::to_value(&old).unwrap(),
                            serde_json::to_value(&inherited).unwrap()
                        );
                        assert_eq!(out, reference);
                        assert_eq!(inherited.actual_sha256, original);
                        assert!(r.published);
                        assert_eq!(r.logical_attempts, source.payload_read_calls() - before.0);
                        assert_eq!(
                            r.logical_requested,
                            source.requested_payload_bytes() - before.1
                        );
                        assert_eq!(r.attempted, 3);
                        assert_eq!(r.requested, r.completed);
                        assert_eq!(r.logical_delivered, r.logical_requested);
                        assert_eq!(r.ledger.additional_reservation, budget);
                        for (i, w) in r.transfers.iter().enumerate() {
                            assert_eq!(w.logical_begin, old.plane.ranges[i].begin);
                            assert_eq!(w.logical_bytes, old.plane.ranges[i].len);
                            assert_eq!(r.effects[i].returned_bytes, Some(w.bytes));
                            assert_eq!(
                                r.effects[i].copied,
                                if w.kind == Kind::Window {
                                    w.logical_bytes
                                } else {
                                    0
                                }
                            );
                        }
                        if let Some(f) = &mut log {
                            writeln!(f, "{}", json!([profile, expert, old, r])).unwrap();
                        }
                        count += 1;
                    }
                }
            }
        }
    }
    assert_eq!(count, 72);
}
