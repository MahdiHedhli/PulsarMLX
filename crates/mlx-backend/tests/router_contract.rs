use mlx_backend::router::{
    admit_router_tensor, canonical_f32le_sha256, compare_router_outputs,
    validate_repeat_identities, RouterOutput, RouterTensorDescriptor, RouterTolerancePolicy,
};

const MODEL_FILE_BYTES: u64 = 32_483_931_648;
const ROUTER_TENSOR_BYTES: u64 = 1_048_576;
const ROUTER_OFFSET_FIXTURE: u64 = 8_388_608;

fn fixture_tensor_descriptor() -> RouterTensorDescriptor {
    RouterTensorDescriptor {
        name: "blk.0.ffn_gate_inp.weight".to_owned(),
        semantic_role: "layer_0_router_projection".to_owned(),
        occurrence_count: 1,
        gguf_dimensions_fastest_axis_first: vec![2_048, 128],
        reader_shape: vec![128, 2_048],
        execution_shape: vec![128, 2_048],
        gguf_type: "F32".to_owned(),
        quantization: "none_f32".to_owned(),
        logical_elements: 262_144,
        absolute_data_offset: ROUTER_OFFSET_FIXTURE,
        encoded_length: ROUTER_TENSOR_BYTES,
        encoded_sha256: "a".repeat(64),
        byte_order: "little".to_owned(),
        orientation: "expert_major_rows_input_columns".to_owned(),
        expert_count: 128,
        top_k: 8,
        weight_scale: 1.0,
        bias_present: false,
        correction_bias_present: false,
    }
}

fn full_softmax(logits: &[f32]) -> Vec<f32> {
    let maximum = logits
        .iter()
        .copied()
        .reduce(f32::max)
        .expect("fixture row is nonempty");
    let exponentials: Vec<f32> = logits
        .iter()
        .map(|value| (*value - maximum).exp())
        .collect();
    let denominator: f32 = exponentials.iter().copied().sum();
    exponentials
        .into_iter()
        .map(|value| value / denominator)
        .collect()
}

fn selected_row(probabilities: &[f32]) -> (Vec<u64>, Vec<f32>, Vec<f32>) {
    let mut ids: Vec<usize> = (0..probabilities.len()).collect();
    ids.sort_by(|left, right| {
        probabilities[*right]
            .total_cmp(&probabilities[*left])
            .then_with(|| left.cmp(right))
    });
    ids.truncate(8);

    let selected_probabilities: Vec<f32> = ids
        .iter()
        .map(|expert_id| probabilities[*expert_id])
        .collect();
    let selected_sum: f32 = selected_probabilities.iter().copied().sum();
    let normalized_weights = selected_probabilities
        .iter()
        .map(|probability| *probability / selected_sum)
        .collect();

    (
        ids.into_iter()
            .map(|expert_id| u64::try_from(expert_id).expect("fixture expert ID fits u64"))
            .collect(),
        selected_probabilities,
        normalized_weights,
    )
}

fn fixture_output_with_last_logit_delta(delta: f32) -> RouterOutput {
    let mut rows = vec![
        (0..128)
            .map(|expert_id| expert_id as f32 * 0.01)
            .collect::<Vec<_>>(),
        (0..128)
            .map(|expert_id| -(expert_id as f32) * 0.01)
            .collect::<Vec<_>>(),
    ];
    rows[1][127] += delta;

    let mut logits = Vec::with_capacity(256);
    let mut full_probabilities = Vec::with_capacity(256);
    let mut selected_expert_ids = Vec::with_capacity(2);
    let mut selected_probabilities = Vec::with_capacity(2);
    let mut normalized_weights = Vec::with_capacity(2);

    for row in rows {
        let probabilities = full_softmax(&row);
        let (ids, selected, normalized) = selected_row(&probabilities);
        logits.extend(row);
        full_probabilities.extend(probabilities);
        selected_expert_ids.push(ids);
        selected_probabilities.push(selected);
        normalized_weights.push(normalized);
    }

    RouterOutput::try_new(
        "synthetic-two-row-router-v1",
        2,
        logits,
        full_probabilities,
        selected_expert_ids,
        selected_probabilities,
        normalized_weights,
    )
    .expect("the complete synthetic router output is contract-valid")
}

fn fixture_output() -> RouterOutput {
    fixture_output_with_last_logit_delta(0.0)
}

#[test]
fn complete_output_rejects_probabilities_unrelated_to_logits() {
    let logits = (0..128)
        .map(|expert_id| expert_id as f32 * 0.01)
        .collect::<Vec<_>>();
    let probabilities = vec![1.0_f32 / 128.0; 128];
    let selected_ids = vec![(0..8).collect::<Vec<_>>()];
    let selected = vec![vec![1.0_f32 / 128.0; 8]];
    let normalized = vec![vec![1.0_f32 / 8.0; 8]];

    let error = RouterOutput::try_new(
        "synthetic-invalid-softmax-v1",
        1,
        logits,
        probabilities,
        selected_ids,
        selected,
        normalized,
    )
    .expect_err("self-consistent probabilities unrelated to logits must fail");
    assert_eq!(error.code(), "comparison_failed");
}

#[test]
fn exact_f32_router_tensor_contract_is_admitted_without_checkpoint_access() {
    // This is a structural fixture offset, not an observed checkpoint offset.
    // Real offsets and hashes remain prohibited until the notified model gate.
    let admitted = admit_router_tensor(&fixture_tensor_descriptor(), MODEL_FILE_BYTES)
        .expect("the exact complete F32 router descriptor is admitted");

    assert_eq!(admitted.name(), "blk.0.ffn_gate_inp.weight");
    assert_eq!(admitted.semantic_role(), "layer_0_router_projection");
    assert_eq!(admitted.gguf_dimensions(), &[2_048, 128]);
    assert_eq!(admitted.reader_shape(), &[128, 2_048]);
    assert_eq!(admitted.execution_shape(), &[128, 2_048]);
    assert_eq!(admitted.gguf_type(), "F32");
    assert_eq!(admitted.quantization(), "none_f32");
    assert_eq!(admitted.logical_elements(), 262_144);
    assert_eq!(admitted.encoded_length(), ROUTER_TENSOR_BYTES);
    assert_eq!(admitted.absolute_data_offset(), ROUTER_OFFSET_FIXTURE);
    assert_eq!(
        admitted.exclusive_end_offset(),
        ROUTER_OFFSET_FIXTURE + ROUTER_TENSOR_BYTES
    );
    assert_eq!(admitted.expert_count(), 128);
    assert_eq!(admitted.top_k(), 8);
    assert_eq!(admitted.weight_scale(), 1.0);
    assert!(!admitted.bias_present());
    assert!(!admitted.correction_bias_present());
}

#[test]
fn complete_outputs_preserve_all_128_values_and_ordered_top8_per_row() {
    let output = fixture_output();

    assert_eq!(output.case_id(), "synthetic-two-row-router-v1");
    assert_eq!(output.row_count(), 2);
    assert_eq!(output.logits_shape(), &[2, 128]);
    assert_eq!(output.full_probabilities_shape(), &[2, 128]);
    assert_eq!(output.logits().len(), 256);
    assert_eq!(output.full_probabilities().len(), 256);
    assert_eq!(output.selected_expert_ids().len(), 2);
    assert_eq!(output.selected_probabilities().len(), 2);
    assert_eq!(output.normalized_weights().len(), 2);

    assert_eq!(
        output.selected_expert_ids()[0],
        [127, 126, 125, 124, 123, 122, 121, 120]
    );
    assert_eq!(output.selected_expert_ids()[1], [0, 1, 2, 3, 4, 5, 6, 7]);

    for row_index in 0..2 {
        let probability_row = &output.full_probabilities()[row_index * 128..(row_index + 1) * 128];
        assert!((probability_row.iter().sum::<f32>() - 1.0).abs() <= 1.0e-6);
        assert_eq!(output.selected_expert_ids()[row_index].len(), 8);
        assert_eq!(output.selected_probabilities()[row_index].len(), 8);
        assert_eq!(output.normalized_weights()[row_index].len(), 8);

        for (selected_slot, expert_id) in output.selected_expert_ids()[row_index].iter().enumerate()
        {
            let expert_id = usize::try_from(*expert_id).expect("expert ID fits usize");
            assert_eq!(
                output.selected_probabilities()[row_index][selected_slot],
                probability_row[expert_id],
                "selected probabilities are the complete-softmax values before renormalization"
            );
        }

        assert!((output.normalized_weights()[row_index].iter().sum::<f32>() - 1.0).abs() <= 1.0e-6);
    }
}

#[test]
fn canonical_hashes_are_f32_little_endian_and_cover_each_complete_output() {
    let digest =
        canonical_f32le_sha256(&[0.0, 1.0, -2.5, -0.0]).expect("finite canonical F32 values hash");
    assert_eq!(
        digest,
        "39044cedea2113aea8f6396a56c4880474de6822b244c0bfe1a706d1228a7700"
    );

    let output = fixture_output();
    assert_eq!(
        output.logits_f32le_sha256(),
        canonical_f32le_sha256(output.logits()).expect("complete logits hash")
    );
    assert_eq!(
        output.full_probabilities_f32le_sha256(),
        canonical_f32le_sha256(output.full_probabilities()).expect("complete probabilities hash")
    );

    let selected: Vec<f32> = output
        .selected_probabilities()
        .iter()
        .flatten()
        .copied()
        .collect();
    let normalized: Vec<f32> = output
        .normalized_weights()
        .iter()
        .flatten()
        .copied()
        .collect();
    assert_eq!(
        output.selected_probabilities_f32le_sha256(),
        canonical_f32le_sha256(&selected).expect("complete selected-probability hash")
    );
    assert_eq!(
        output.normalized_weights_f32le_sha256(),
        canonical_f32le_sha256(&normalized).expect("complete normalized-weight hash")
    );
}

#[test]
fn full_output_comparisons_report_all_counts_and_bounded_error_metrics() {
    let reference = fixture_output();
    let exact = compare_router_outputs(
        &reference,
        &reference,
        &RouterTolerancePolicy::contract_v1(),
    )
    .expect("identical complete outputs compare");

    assert!(exact.passed());
    assert_eq!(exact.id_mismatch_count(), 0);
    assert_eq!(exact.order_mismatch_count(), 0);
    for comparison in [
        exact.logits(),
        exact.full_probabilities(),
        exact.selected_probabilities(),
        exact.normalized_weights(),
    ] {
        assert_eq!(comparison.mismatch_count(), 0);
        assert_eq!(comparison.maximum_absolute_error(), 0.0);
        assert_eq!(comparison.mean_absolute_error(), 0.0);
        assert_eq!(comparison.rmse(), 0.0);
        assert_eq!(comparison.maximum_relative_error(), Some(0.0));
        assert!(comparison.first_mismatch().is_none());
    }
    assert_eq!(exact.logits().compared_count(), 256);
    assert_eq!(exact.full_probabilities().compared_count(), 256);
    assert_eq!(exact.selected_probabilities().compared_count(), 16);
    assert_eq!(exact.normalized_weights().compared_count(), 16);

    let candidate = fixture_output_with_last_logit_delta(0.01);
    let mismatch = compare_router_outputs(
        &reference,
        &candidate,
        &RouterTolerancePolicy::contract_v1(),
    )
    .expect("complete mismatched outputs still produce comparison evidence");
    assert!(!mismatch.passed());
    assert_eq!(mismatch.logits().compared_count(), 256);
    assert_eq!(mismatch.logits().mismatch_count(), 1);
    assert!(mismatch.logits().maximum_absolute_error() > 0.009);
    assert!(mismatch.logits().mean_absolute_error() > 0.0);
    assert!(mismatch.logits().rmse() > 0.0);
    assert!(mismatch.logits().maximum_relative_error().is_some());

    let first = mismatch
        .logits()
        .first_mismatch()
        .expect("the first logit mismatch is retained");
    assert_eq!(first.row_index(), 1);
    assert_eq!(first.column_index(), 127);
    assert!(first.reference().is_finite());
    assert!(first.candidate().is_finite());
}

#[test]
fn ten_repetitions_require_identical_complete_hashes_and_route_order() {
    let output = fixture_output();
    let identity = output.repeat_identity();
    let ten_identical = vec![identity.clone(); 10];
    let summary = validate_repeat_identities(&ten_identical)
        .expect("ten bitwise-identical complete router outputs pass");

    assert_eq!(summary.repeat_count(), 10);
    assert_eq!(summary.unique_output_identity_count(), 1);
    assert!(summary.identical());

    let mut changed = ten_identical;
    changed[9] = fixture_output_with_last_logit_delta(0.01).repeat_identity();
    let error = validate_repeat_identities(&changed)
        .expect_err("one changed complete-output hash must fail repeat identity");
    assert_eq!(error.code(), "comparison_failed");
}
