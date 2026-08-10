#![cfg(target_os = "macos")]

use stream::Iq2XxsGemvSpec;

#[test]
fn valid_packed_iq2_xxs_request_has_exact_byte_accounting() {
    let spec = Iq2XxsGemvSpec::new(2, 256, 132, 256).expect("valid request");
    assert_eq!(spec.rows(), 2);
    assert_eq!(spec.columns(), 256);
    assert_eq!(spec.packed_row_bytes(), 66);
    assert_eq!(spec.packed_matrix_bytes(), 132);
    assert_eq!(spec.complete_f32_weight_materialized_bytes(), 0);
}

#[test]
fn malformed_shape_and_lengths_fail_before_dispatch() {
    for result in [
        Iq2XxsGemvSpec::new(0, 256, 0, 256),
        Iq2XxsGemvSpec::new(1, 0, 0, 0),
        Iq2XxsGemvSpec::new(1, 255, 66, 255),
        Iq2XxsGemvSpec::new(1, 256, 65, 256),
        Iq2XxsGemvSpec::new(1, 256, 66, 255),
        Iq2XxsGemvSpec::new(usize::MAX, 256, 66, 256),
    ] {
        assert!(result.is_err());
    }
}

#[test]
fn representative_gate_shape_accounts_without_allocating_f32_weights() {
    let rows = 2048;
    let columns = 6144;
    let packed = rows * (columns / 256) * 66;
    let spec =
        Iq2XxsGemvSpec::new(rows, columns, packed, columns).expect("representative GLM gate shape");
    assert_eq!(spec.packed_matrix_bytes(), 3_244_032);
    assert_eq!(spec.complete_f32_weight_materialized_bytes(), 0);
}
