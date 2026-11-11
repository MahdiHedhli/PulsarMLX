use mlx_expert_mlp::expert_tuple::{ExpertTuple, ROLES};
use mlx_native_affine::compose::{compose, Source};
use std::{collections::BTreeMap, path::PathBuf};

fn source(profile: &str) -> Source {
    let p = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../fixtures/expert-mlp-composition/checkpoints")
        .join(format!("d64-h64-{profile}"));
    Source::open(
        &p,
        &std::fs::read_to_string(p.join("config.json")).unwrap(),
        &BTreeMap::new(),
    )
    .unwrap()
}

#[test]
fn default_and_overridden_expert_tuples_bind_real_catalog_selection() {
    for mixed in [false, true] {
        let s = source(if mixed { "mixed" } else { "default" });
        for e in 0..3 {
            let t = ExpertTuple::select(&s, e, 64, 64, mixed).unwrap();
            let ids = t
                .planes()
                .iter()
                .map(|p| p.identity().index_path.clone())
                .collect::<Vec<_>>();
            assert_eq!(ids, vec![vec![e], vec![e], vec![e]]);
        }
    }
}

#[test]
fn individually_valid_selected_planes_do_not_authorize_cross_expert_or_role_tuple() {
    let s = source("default");
    let gate = compose(&s, ROLES[0], &[0]).unwrap();
    let up = compose(&s, ROLES[1], &[0]).unwrap();
    let down = compose(&s, ROLES[2], &[1]).unwrap();
    match ExpertTuple::bind(&s, [gate, up, down], 0, 64, 64, false) {
        Ok(_) => panic!("cross expert admitted"),
        Err(e) => assert!(e.contains("MLP-R-TUPLE: index_path")),
    }
    let gate = compose(&s, ROLES[0], &[0]).unwrap();
    let up = compose(&s, ROLES[1], &[0]).unwrap();
    let down = compose(&s, ROLES[2], &[0]).unwrap();
    match ExpertTuple::bind(&s, [down, up, gate], 0, 64, 64, false) {
        Ok(_) => panic!("cross role admitted"),
        Err(e) => assert!(e.contains("MLP-R-TUPLE: module")),
    }
}

#[test]
fn catalog_recipe_and_geometry_cannot_be_overridden_by_caller() {
    let s = source("mixed");
    assert!(ExpertTuple::select(&s, 0, 64, 64, false).is_err());
    assert!(ExpertTuple::select(&s, 0, 128, 64, true).is_err());
    assert!(ExpertTuple::select(&s, 3, 64, 64, true).is_err());
}

#[test]
fn same_shape_from_another_checkpoint_cannot_be_bound_to_source() {
    let a = source("default");
    let b = source("mixed");
    let gate = compose(&a, ROLES[0], &[0]).unwrap();
    let up = compose(&a, ROLES[1], &[0]).unwrap();
    let down = compose(&b, ROLES[2], &[0]).unwrap();
    assert!(ExpertTuple::bind(&a, [gate, up, down], 0, 64, 64, false).is_err());
}

#[test]
fn dropping_explicit_override_refuses_tuple_before_any_native_bridge() {
    let p = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../fixtures/expert-mlp-composition/checkpoints/d64-h64-mixed");
    let mut config: serde_json::Value =
        serde_json::from_str(&std::fs::read_to_string(p.join("config.json")).unwrap()).unwrap();
    for role in [ROLES[0], ROLES[2]] {
        config["quantization"].as_object_mut().unwrap().remove(role);
    }
    let s = Source::open(&p, &config.to_string(), &BTreeMap::new()).unwrap();
    match ExpertTuple::select(&s, 0, 64, 64, true) {
        Ok(_) => panic!("ignored override was admitted"),
        Err(e) => assert!(e.contains("MLP-R-TUPLE")),
    }
}
