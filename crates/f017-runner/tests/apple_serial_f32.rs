use f017_runner::apple_serial_f32::*;
use std::collections::BTreeMap;

struct ScalarBackend;

impl ProjectionBackend for ScalarBackend {
    fn matvec(
        &mut self,
        role: &'static str,
        matrix: &DenseMatrix,
        vector: &[f32],
    ) -> Result<Vec<f32>, AppleGraphError> {
        if vector.len() != matrix.columns {
            return Err(AppleGraphError::InvalidShape(role));
        }
        let mut output = vec![0.0_f32; matrix.rows];
        for row in 0..matrix.rows {
            let mut sum = 0.0_f32;
            for column in 0..matrix.columns {
                sum = f32::from_bits(
                    (sum + f32::from_bits(
                        (matrix.values[row * matrix.columns + column] * vector[column]).to_bits(),
                    ))
                    .to_bits(),
                );
            }
            output[row] = sum;
        }
        Ok(output)
    }
}

#[derive(Default)]
struct Capture {
    rows: BTreeMap<String, (Vec<usize>, Vec<f32>)>,
}

impl CaptureSink for Capture {
    fn capture(
        &mut self,
        stage_id: &'static str,
        shape: &[usize],
        values: &[f32],
    ) -> Result<(), AppleGraphError> {
        if self
            .rows
            .insert(stage_id.into(), (shape.to_vec(), values.to_vec()))
            .is_some()
        {
            return Err(AppleGraphError::Capture(stage_id));
        }
        Ok(())
    }

    fn capture_u16(
        &mut self,
        stage_id: &'static str,
        shape: &[usize],
        values: &[u16],
    ) -> Result<(), AppleGraphError> {
        let converted = values.iter().map(|&v| v as f32).collect();
        if self
            .rows
            .insert(stage_id.into(), (shape.to_vec(), converted))
            .is_some()
        {
            return Err(AppleGraphError::Capture(stage_id));
        }
        Ok(())
    }
}

fn matrix(rows: usize, columns: usize, diagonal: f32) -> DenseMatrix {
    let mut values = vec![0.0; rows * columns];
    for i in 0..rows.min(columns) {
        values[i * columns + i] = diagonal;
    }
    DenseMatrix {
        rows,
        columns,
        values,
    }
}

fn expert(id: usize, width: usize) -> ExpertMatrices {
    ExpertMatrices {
        expert_id: id,
        gate: matrix(width, width, 0.5),
        up: matrix(width, width, 0.25),
        down: matrix(width, width, 0.75),
    }
}

fn fixture() -> (AppleLayerMatrices, AppleLayerInputs) {
    let width = 4;
    let matrices = AppleLayerMatrices {
        q_a: matrix(4, width, 0.5),
        q_b: matrix(8, 4, 0.25),
        kv_a: matrix(4, width, 0.2),
        k_b: matrix(4, 2, 0.3),
        v_b: matrix(4, 2, 0.4),
        attention_output: matrix(width, 4, 0.5),
        router: matrix(8, width, 0.0),
        routed: (0..8).map(|id| expert(id, width)).collect(),
        shared: expert(usize::MAX, width),
    };
    let inputs = AppleLayerInputs {
        s0: vec![0.25, -0.5, 0.75, 1.0],
        attention_norm_scale: vec![1.0; width],
        q_rank_norm_scale: vec![1.0; 4],
        kv_norm_scale: vec![1.0; 2],
        ffn_norm_scale: vec![1.0; width],
        correction_bias: (0..8).map(|i| 8.0 - i as f32).collect(),
        position: 0,
        rope_base: 1_000_000.0,
        attention_scale: 0.0625,
        expert_weight_scale: 2.5,
        heads: 2,
        qk_nope: 2,
        qk_rope: 2,
        kv_lora: 2,
        value_dim: 2,
    };
    (matrices, inputs)
}

#[test]
fn synthetic_full_graph_captures_every_stage_once() {
    let (matrices, inputs) = fixture();
    let mut backend = ScalarBackend;
    let mut capture = Capture::default();
    let output = run_apple_serial_f32(&mut backend, &mut capture, &matrices, &inputs).unwrap();
    assert_eq!(capture.rows.len(), STAGE_IDS.len());
    assert!(STAGE_IDS.iter().all(|id| capture.rows.contains_key(*id)));
    assert_eq!(output.selected_ids, (0..8).collect::<Vec<_>>());
    assert_eq!(output.s2.len(), 4);
    assert!(output.s2.iter().all(|v| v.is_finite()));
}

#[test]
fn exact_router_tie_break_is_lower_expert_id() {
    let (matrices, mut inputs) = fixture();
    inputs.correction_bias.fill(0.0);
    let mut backend = ScalarBackend;
    let mut capture = Capture::default();
    let output = run_apple_serial_f32(&mut backend, &mut capture, &matrices, &inputs).unwrap();
    assert_eq!(output.selected_ids, (0..8).collect::<Vec<_>>());
}

#[test]
fn wrong_rms_epsilon_is_rejected() {
    assert_eq!(
        rms_norm_serial_f32(&[1.0], &[1.0], 1.0e-6),
        Err(AppleGraphError::InvalidShape("rms_norm"))
    );
}

#[test]
fn serial_softmax_is_finite_and_normalized() {
    let values = softmax_serial_f32(&[-100.0, 0.0, 100.0]).unwrap();
    assert!(values.iter().all(|v| v.is_finite()));
    let mut sum = 0.0_f32;
    for value in values {
        sum = f32::from_bits((sum + value).to_bits());
    }
    assert_eq!(sum.to_bits(), 1.0_f32.to_bits());
}

#[test]
fn selected_expert_binding_fails_closed() {
    let (mut matrices, inputs) = fixture();
    matrices.routed.swap(0, 1);
    let mut backend = ScalarBackend;
    let mut capture = Capture::default();
    assert_eq!(
        run_apple_serial_f32(&mut backend, &mut capture, &matrices, &inputs),
        Err(AppleGraphError::InvalidShape("selected expert bindings"))
    );
}
