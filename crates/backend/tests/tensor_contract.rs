use backend::{
    BroadcastRule, ComparisonMode, ComparisonPolicy, DType, NonFinitePolicy, QuantizationId,
    SynchronizationRule, TensorContract, TensorDescriptor, TensorLayout,
};

const ORACLE_ID: &str = "scalar:fixture-v1";

fn exact_policy(max_compared_count: u64) -> ComparisonPolicy {
    ComparisonPolicy::exact(ORACLE_ID, NonFinitePolicy::Reject, max_compared_count)
        .expect("the fixture comparison policy must be valid")
}

fn dense_descriptor() -> TensorDescriptor {
    TensorDescriptor {
        operation_id: "nonsymmetric-matmul".to_owned(),
        logical_shape: vec![2, 3],
        storage_shape: vec![3, 2],
        layout: TensorLayout::GgufFastestFirst,
        input_dtype: DType::F32,
        accumulation_dtype: DType::F32,
        output_dtype: DType::F32,
        encoded_byte_count: Some(24),
        quantization: None,
        broadcast_rule: BroadcastRule::None,
        synchronization: SynchronizationRule::EvaluatedAndDeviceSynchronized,
        comparison_policy: exact_policy(6),
    }
}

fn q8_zero_descriptor(element_count: u64, encoded_byte_count: u64) -> TensorDescriptor {
    TensorDescriptor {
        operation_id: "q8-zero-row".to_owned(),
        logical_shape: vec![1, element_count],
        storage_shape: vec![element_count, 1],
        layout: TensorLayout::GgufFastestFirst,
        input_dtype: DType::I8,
        accumulation_dtype: DType::F32,
        output_dtype: DType::F32,
        encoded_byte_count: Some(encoded_byte_count),
        quantization: Some(QuantizationId::Q8Zero),
        broadcast_rule: BroadcastRule::None,
        synchronization: SynchronizationRule::EvaluatedAndDeviceSynchronized,
        comparison_policy: exact_policy(element_count),
    }
}

#[test]
fn accepts_checked_nonzero_shapes_and_preserves_explicit_orientation() {
    let contract = TensorContract::try_new(dense_descriptor()).expect("valid tensor contract");

    assert_eq!(contract.operation_id(), "nonsymmetric-matmul");
    assert_eq!(contract.logical_shape(), &[2, 3]);
    assert_eq!(contract.storage_shape(), &[3, 2]);
    assert_ne!(contract.logical_shape(), contract.storage_shape());
    assert_eq!(contract.element_count(), 6);
    assert_eq!(contract.layout(), &TensorLayout::GgufFastestFirst);
    assert_eq!(contract.input_dtype(), &DType::F32);
    assert_eq!(contract.accumulation_dtype(), &DType::F32);
    assert_eq!(contract.output_dtype(), &DType::F32);
    assert_eq!(contract.encoded_byte_count(), Some(24));
    assert_eq!(contract.quantization(), None);
    assert_eq!(contract.broadcast_rule(), &BroadcastRule::None);
    assert_eq!(
        contract.synchronization(),
        &SynchronizationRule::EvaluatedAndDeviceSynchronized
    );
    assert_eq!(contract.comparison_policy().oracle_id(), ORACLE_ID);
}

#[test]
fn rejects_empty_zero_mismatched_and_overflowing_shapes() {
    let mut descriptor = dense_descriptor();
    descriptor.logical_shape.clear();
    assert!(TensorContract::try_new(descriptor).is_err());

    let mut descriptor = dense_descriptor();
    descriptor.storage_shape.clear();
    assert!(TensorContract::try_new(descriptor).is_err());

    let mut descriptor = dense_descriptor();
    descriptor.logical_shape = vec![2, 0, 3];
    descriptor.storage_shape = vec![3, 2, 0];
    assert!(TensorContract::try_new(descriptor).is_err());

    let mut descriptor = dense_descriptor();
    descriptor.logical_shape = vec![2, 3];
    descriptor.storage_shape = vec![2, 4];
    assert!(TensorContract::try_new(descriptor).is_err());

    let mut descriptor = dense_descriptor();
    descriptor.logical_shape = vec![u64::MAX, 2];
    descriptor.storage_shape = vec![2, u64::MAX];
    descriptor.encoded_byte_count = None;
    assert!(TensorContract::try_new(descriptor).is_err());
}

#[test]
fn rejects_empty_operation_ids() {
    let mut descriptor = dense_descriptor();
    descriptor.operation_id.clear();

    assert!(TensorContract::try_new(descriptor).is_err());
}

#[test]
fn enforces_exact_dense_encoded_byte_counts_with_checked_arithmetic() {
    let exact = TensorContract::try_new(dense_descriptor()).expect("24 bytes is 6 f32 values");
    assert_eq!(exact.encoded_byte_count(), Some(24));

    for wrong_count in [0, 23, 25] {
        let mut descriptor = dense_descriptor();
        descriptor.encoded_byte_count = Some(wrong_count);
        assert!(TensorContract::try_new(descriptor).is_err());
    }

    let mut descriptor = dense_descriptor();
    descriptor.logical_shape = vec![u64::MAX / 4 + 1];
    descriptor.storage_shape = descriptor.logical_shape.clone();
    descriptor.encoded_byte_count = Some(u64::MAX);
    assert!(TensorContract::try_new(descriptor).is_err());
}

#[test]
fn admits_only_exact_complete_q8_zero_blocks() {
    let contract = TensorContract::try_new(q8_zero_descriptor(32, 34))
        .expect("one complete Q8_0 block is exactly 34 bytes");
    assert_eq!(contract.element_count(), 32);
    assert_eq!(contract.encoded_byte_count(), Some(34));
    assert_eq!(contract.quantization(), Some(&QuantizationId::Q8Zero));

    let contract = TensorContract::try_new(q8_zero_descriptor(64, 68))
        .expect("two complete Q8_0 blocks are exactly 68 bytes");
    assert_eq!(contract.element_count(), 64);
    assert_eq!(contract.encoded_byte_count(), Some(68));

    for wrong_count in [0, 33, 35] {
        assert!(TensorContract::try_new(q8_zero_descriptor(32, wrong_count)).is_err());
    }

    assert!(TensorContract::try_new(q8_zero_descriptor(31, 34)).is_err());

    let overflowing_elements = u64::MAX - 31;
    assert_eq!(overflowing_elements % 32, 0);
    assert!(TensorContract::try_new(q8_zero_descriptor(overflowing_elements, u64::MAX,)).is_err());
}

#[test]
fn quantized_inputs_require_an_exact_encoded_byte_count() {
    let mut descriptor = q8_zero_descriptor(32, 34);
    descriptor.encoded_byte_count = None;

    assert!(TensorContract::try_new(descriptor).is_err());
}

#[test]
fn rejects_unsupported_layout_dtype_and_quantization_ids() {
    let mut descriptor = dense_descriptor();
    descriptor.layout = TensorLayout::Unsupported("implicit-column-major".to_owned());
    assert!(TensorContract::try_new(descriptor).is_err());

    let unsupported_dtype = DType::Unsupported("float128".to_owned());

    let mut descriptor = dense_descriptor();
    descriptor.input_dtype = unsupported_dtype.clone();
    assert!(TensorContract::try_new(descriptor).is_err());

    let mut descriptor = dense_descriptor();
    descriptor.accumulation_dtype = unsupported_dtype.clone();
    assert!(TensorContract::try_new(descriptor).is_err());

    let mut descriptor = dense_descriptor();
    descriptor.output_dtype = unsupported_dtype;
    assert!(TensorContract::try_new(descriptor).is_err());

    let mut descriptor = q8_zero_descriptor(32, 34);
    descriptor.quantization = Some(QuantizationId::Unsupported("IQ9_X".to_owned()));
    assert!(TensorContract::try_new(descriptor).is_err());
}

#[test]
fn requires_observable_evaluation_and_synchronization_metadata() {
    let valid = TensorContract::try_new(dense_descriptor()).expect("valid tensor contract");
    assert_eq!(
        valid.synchronization(),
        &SynchronizationRule::EvaluatedAndDeviceSynchronized
    );

    let mut descriptor = dense_descriptor();
    descriptor.synchronization = SynchronizationRule::QueuedOnly;
    assert!(TensorContract::try_new(descriptor).is_err());

    let mut descriptor = dense_descriptor();
    descriptor.synchronization = SynchronizationRule::EvaluatedOnly;
    assert!(TensorContract::try_new(descriptor).is_err());
}

#[test]
fn comparison_policies_are_predeclared_finite_and_bounded() {
    let policy = ComparisonPolicy::abs_rel(ORACLE_ID, 1.0e-5, 1.0e-4, NonFinitePolicy::Reject, 16)
        .expect("valid bounded absolute/relative comparison policy");

    assert_eq!(policy.oracle_id(), ORACLE_ID);
    assert_eq!(policy.mode(), ComparisonMode::AbsoluteAndRelative);
    assert_eq!(policy.absolute_tolerance(), Some(1.0e-5));
    assert_eq!(policy.relative_tolerance(), Some(1.0e-4));
    assert_eq!(policy.non_finite_policy(), NonFinitePolicy::Reject);
    assert_eq!(policy.max_compared_count(), 16);

    assert!(ComparisonPolicy::exact("", NonFinitePolicy::Reject, 1).is_err());
    assert!(ComparisonPolicy::exact(ORACLE_ID, NonFinitePolicy::Reject, 0).is_err());

    for invalid_tolerance in [-1.0, f64::NAN, f64::INFINITY] {
        assert!(ComparisonPolicy::abs_rel(
            ORACLE_ID,
            invalid_tolerance,
            0.0,
            NonFinitePolicy::Reject,
            1,
        )
        .is_err());
        assert!(ComparisonPolicy::abs_rel(
            ORACLE_ID,
            0.0,
            invalid_tolerance,
            NonFinitePolicy::Reject,
            1,
        )
        .is_err());
    }
}

#[test]
fn comparison_rejects_cardinality_and_policy_bound_violations() {
    let policy = exact_policy(2);

    assert!(policy.compare(&[1.0], &[1.0, 2.0]).is_err());
    assert!(policy.compare(&[1.0, 2.0, 3.0], &[1.0, 2.0, 3.0]).is_err());

    let result = policy
        .compare(&[1.0, 2.0], &[1.0, 2.0])
        .expect("equal bounded values compare successfully");
    assert_eq!(result.compared_count(), 2);
    assert!(result.passed());
    assert!(result.first_mismatch().is_none());
}

#[test]
fn comparison_rejects_non_finite_expected_and_actual_values() {
    let policy = exact_policy(1);

    for non_finite in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
        assert!(policy.compare(&[non_finite], &[0.0]).is_err());
        assert!(policy.compare(&[0.0], &[non_finite]).is_err());
    }
}

#[test]
fn comparison_reports_cardinality_max_errors_and_only_the_first_mismatch() {
    let policy = ComparisonPolicy::abs_rel(ORACLE_ID, 0.01, 0.01, NonFinitePolicy::Reject, 8)
        .expect("valid comparison policy");

    let result = policy
        .compare(&[1.0, 2.0, 4.0], &[1.005, 2.2, 4.02])
        .expect("finite values with matching cardinality produce a result");

    assert_eq!(result.compared_count(), 3);
    assert!(!result.passed());
    assert!((result.max_absolute_error().expect("absolute error") - 0.2).abs() < 1.0e-12);
    assert!((result.max_relative_error().expect("relative error") - 0.1).abs() < 1.0e-12);

    let mismatch = result
        .first_mismatch()
        .expect("one bounded mismatch detail");
    assert_eq!(mismatch.index(), 1);
    assert_eq!(mismatch.expected(), 2.0);
    assert_eq!(mismatch.actual(), 2.2);
    assert!((mismatch.absolute_error() - 0.2).abs() < 1.0e-12);
    assert!((mismatch.relative_error() - 0.1).abs() < 1.0e-12);
}

#[test]
fn absolute_or_relative_tolerance_can_independently_admit_a_value() {
    let policy = ComparisonPolicy::abs_rel(ORACLE_ID, 0.001, 0.02, NonFinitePolicy::Reject, 2)
        .expect("valid comparison policy");

    let result = policy
        .compare(&[100.0, 0.0], &[101.0, 0.0005])
        .expect("finite values with matching cardinality produce a result");

    assert!(result.passed());
    assert_eq!(result.compared_count(), 2);
    assert!(result.first_mismatch().is_none());
}
