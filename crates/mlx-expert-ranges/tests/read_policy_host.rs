//! The production policy path on both immutable synthetic recipes.
#[cfg(target_os = "macos")]
#[test]
fn fixed_policies_match_all_frozen_components_at_runtime_page_size() {
    use mlx_expert_ranges::{
        read_into::{
            aligned_transport::{read_policy::*, Scratch, WindowPlan},
            ExpertRole, PlaneDestination,
        },
        BoundedSource, ExpertRequest,
    };
    use serde_json::{json, Value};
    use std::{
        fs,
        io::Write,
        path::{Path, PathBuf},
    };
    let dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../fixtures/resident-expert-mlp");
    let manifest: Value =
        serde_json::from_slice(&fs::read(dir.join("manifest.json")).unwrap()).unwrap();
    let page = safetensors_catalog::admission::read_policy::page_size().unwrap();
    fn destination<'a>(
        parts: &'a mut [Vec<u8>; 3],
        expected: &[String; 3],
    ) -> PlaneDestination<'a> {
        let [w, s, b] = parts;
        PlaneDestination::new(w, s, b, expected.clone())
    }
    let mut log = std::env::var_os("WINDOW_CAPTURE_DIR")
        .map(|root| fs::File::create(PathBuf::from(root).join("policy-real.jsonl")).unwrap());
    let mut cases = 0;
    for profile in ["default", "mixed"] {
        let recipe = &manifest["recipes"][profile];
        let src = BoundedSource::open(&dir.join(recipe["name"].as_str().unwrap())).unwrap();
        for expert in 0..3 {
            let planes = &recipe["planes"][expert];
            let plan = src
                .plan(ExpertRequest {
                    expert: expert as u64,
                    experts: 3,
                    d: 128,
                    h: 64,
                    group_size: 64,
                    bits: std::array::from_fn(|i| planes[i]["bits"].as_u64().unwrap() as u32),
                    modules: std::array::from_fn(|i| planes[i]["module"].as_str().unwrap().into()),
                })
                .unwrap();
            for role in [ExpertRole::Gate, ExpertRole::Up, ExpertRole::Down] {
                let p = &planes[role.index()];
                let hashes: [String; 3] =
                    std::array::from_fn(|i| p["sha256"][i].as_str().unwrap().into());
                let mut reference: [Vec<u8>; 3] = std::array::from_fn(|i| {
                    vec![0; p["ranges"][i]["len"].as_u64().unwrap() as usize]
                });
                let old = plan
                    .read_plane_into(role, destination(&mut reference, &hashes))
                    .unwrap()
                    .into_receipt();
                let wp = WindowPlan::new(&plan, role, page).unwrap();
                let budget = PreparedPolicy::minimum_budget(&wp);
                let mut scratch = Scratch::new(&wp, budget).unwrap();
                for policy in [Policy::BufferedRequested, Policy::NoCacheRequested] {
                    let p = PreparedPolicy::prepare(&wp, policy, budget).unwrap();
                    let mut parts = reference.each_ref().map(|v| vec![0xcc; v.len()]);
                    let before = (src.payload_read_calls(), src.requested_payload_bytes());
                    let (filled, r) = p
                        .read(&mut scratch, destination(&mut parts, &hashes), budget)
                        .unwrap()
                        .into_parts();
                    let inherited = filled.into_receipt();
                    assert_eq!(json!(inherited), json!(old));
                    assert_eq!(parts, reference);
                    assert_eq!(src.payload_read_calls() - before.0, 3);
                    assert_eq!(
                        src.requested_payload_bytes() - before.1,
                        old.requested_bytes
                    );
                    let length = r.encoded_bytes();
                    assert!(length <= POLICY_RECORD_LIMIT);
                    assert_eq!(length, serde_json::to_vec(&r).unwrap().len());
                    let retired = p.retire();
                    assert_eq!(retired.live, 0);
                    assert_eq!(retired.released, r.setup.live);
                    assert_eq!(r.combined_reservation, budget);
                    for step in r.setup.slots.iter().flatten() {
                        let call = step.setter.unwrap();
                        assert_eq!(call.returned, 0);
                        assert_eq!(call.argument, policy.argument());
                        assert_eq!(step.matched, Some(true));
                    }
                    if let Some(f) = &mut log {
                        writeln!(f, "{}", json!([profile, expert, old, r, length, retired]))
                            .unwrap();
                    }
                    cases += 1;
                }
            }
        }
    }
    assert_eq!(cases, 36);
}
