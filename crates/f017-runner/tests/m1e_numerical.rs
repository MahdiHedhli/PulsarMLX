use f017_runner::qualification::{
    exact_matvec_f32, exact_swiglu_f32, qualify_m1e_expert_tier_b, M1E_TIER_B_CONTRACT_VERSION,
};

fn fixture() -> (
    Vec<f32>,
    Vec<f32>,
    Vec<f32>,
    Vec<f32>,
    Vec<f32>,
    Vec<f32>,
    Vec<f32>,
    Vec<f32>,
) {
    let input = vec![1.0, -1.0, 0.5, -0.5];
    let gate = vec![1.0, 1.0, -1.0, -1.0, 0.25, -0.25, 4.0, -4.0];
    let up = vec![-1.0, 1.0, 1.0, -1.0, 2.0, -2.0, 0.5, -0.5];
    let down = vec![1.0, -1.0, -1.0, 1.0, 0.5, 0.5, -0.5, -0.5];
    let mut g = vec![0.0; 2];
    let mut u = vec![0.0; 2];
    let mut h = vec![0.0; 2];
    let mut o = vec![0.0; 4];
    exact_matvec_f32(&gate, 2, 4, &input, &mut g).unwrap();
    exact_matvec_f32(&up, 2, 4, &input, &mut u).unwrap();
    exact_swiglu_f32(&g, &u, &mut h).unwrap();
    exact_matvec_f32(&down, 4, 2, &h, &mut o).unwrap();
    (input, gate, up, down, g, u, h, o)
}

#[test]
fn frozen_expert_composition_accepts_exact_candidate_without_fitting() {
    let (input, gate, up, down, g, u, h, o) = fixture();
    let q = qualify_m1e_expert_tier_b(&gate, &up, &down, &input, &g, &g, &u, &u, &h, &h, &o, &o)
        .unwrap();
    assert_eq!(q.contract_version, M1E_TIER_B_CONTRACT_VERSION);
    assert!(q.passes);
    assert!(q.final_absolute_bounds.iter().all(|v| *v >= 0.0));
}

#[test]
fn non_finite_and_large_final_divergence_fail_closed() {
    let (input, gate, up, down, g, u, h, o) = fixture();
    let mut bad = o.clone();
    bad[0] = f32::NAN;
    assert!(
        !qualify_m1e_expert_tier_b(&gate, &up, &down, &input, &g, &g, &u, &u, &h, &h, &o, &bad)
            .unwrap()
            .passes
    );
    let mut bad = o.clone();
    bad[0] += 1.0;
    assert!(
        !qualify_m1e_expert_tier_b(&gate, &up, &down, &input, &g, &g, &u, &u, &h, &h, &o, &bad)
            .unwrap()
            .passes
    );
}

#[test]
fn zero_up_lane_keeps_the_frozen_silu_error_term() {
    let input = vec![1.0_f32];
    let gate_matrix = vec![2.0_f32];
    let up_matrix = vec![0.0_f32];
    let down_matrix = vec![1.0_f32];
    let gate = vec![2.0_f32];
    let up = vec![0.0_f32];
    let hidden = vec![0.0_f32];
    let output = vec![0.0_f32];
    let qualification = qualify_m1e_expert_tier_b(
        &gate_matrix,
        &up_matrix,
        &down_matrix,
        &input,
        &gate,
        &gate,
        &up,
        &up,
        &hidden,
        &hidden,
        &output,
        &output,
    )
    .unwrap();
    assert!(qualification.hidden_absolute_bounds[0] > 0.0);
    assert!(qualification.passes);
}
