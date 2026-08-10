#![cfg(target_os = "macos")]

use stream::{
    iq2_xxs_gemv_reference, iq2_xxs_lookup_sha256, synthetic_iq2_xxs_matrix, Iq2XxsGemvSpec,
    MetalBridge, StableSlabAllocator, StableSlabConfig, ZeroingPolicy,
};

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

#[test]
fn lookup_tables_have_stable_nonempty_hashes() {
    let (grid, signs) = iq2_xxs_lookup_sha256();
    assert_eq!(grid.len(), 64);
    assert_eq!(signs.len(), 64);
    assert_ne!(grid, signs);
    assert!(grid.chars().all(|value| value.is_ascii_hexdigit()));
    assert!(signs.chars().all(|value| value.is_ascii_hexdigit()));
}

#[test]
fn native_iq2_xxs_direct_gemv_matches_reference_and_repeats() {
    let rows = 8;
    let columns = 512;
    let packed = synthetic_iq2_xxs_matrix(rows, columns).expect("synthetic packed matrix");
    let activation = (0..columns)
        .map(|index| ((index % 31) as f32 - 15.0) * 0.01)
        .collect::<Vec<_>>();
    let spec = Iq2XxsGemvSpec::new(rows, columns, packed.len(), activation.len())
        .expect("valid synthetic request");
    let reference = iq2_xxs_gemv_reference(&packed, spec, &activation).expect("CPU reference");

    let allocator = StableSlabAllocator::new(StableSlabConfig::new(
        packed.len(),
        4096,
        1,
        ZeroingPolicy::ZeroInitialize,
    ))
    .expect("bounded page-aligned allocator");
    let mut slab = allocator.acquire().expect("stable packed slab");
    slab.as_mut_slice().copy_from_slice(&packed);
    let bridge = MetalBridge::new().expect("Metal IQ2_XXS pipeline");
    assert!(!bridge.device_name().expect("Metal device name").is_empty());
    assert!(bridge.compilation_seconds() >= 0.0);
    let registration = bridge.register(&slab).expect("no-copy packed registration");
    let first = bridge
        .iq2_xxs_gemv(&registration, spec, &activation)
        .expect("first direct GEMV");
    let first_bits = first
        .output
        .iter()
        .map(|value| value.to_bits())
        .collect::<Vec<_>>();
    for (expected, actual) in reference.iter().zip(&first.output) {
        let error = (expected - actual).abs();
        assert!(
            error <= 0.0005 + 0.0005 * expected.abs(),
            "reference={expected} actual={actual} error={error}"
        );
    }
    assert_eq!(first.telemetry.cpu_fallback_count, 0);
    assert_eq!(first.telemetry.complete_f32_weight_materialized_bytes, 0);
    assert!(first.telemetry.total_seconds >= 0.0);

    for _ in 0..100 {
        let repeated = bridge
            .iq2_xxs_gemv(&registration, spec, &activation)
            .expect("deterministic direct GEMV repeat");
        assert_eq!(
            repeated
                .output
                .iter()
                .map(|value| value.to_bits())
                .collect::<Vec<_>>(),
            first_bits
        );
        assert_eq!(repeated.telemetry.cpu_fallback_count, 0);
        assert_eq!(repeated.telemetry.complete_f32_weight_materialized_bytes, 0);
    }
}

#[test]
fn direct_gemv_rejects_bad_activation_before_dispatch() {
    let rows = 1;
    let columns = 256;
    let packed = synthetic_iq2_xxs_matrix(rows, columns).expect("synthetic packed matrix");
    let spec = Iq2XxsGemvSpec::new(rows, columns, packed.len(), columns).expect("valid spec");
    let allocator = StableSlabAllocator::new(StableSlabConfig::new(
        packed.len(),
        4096,
        1,
        ZeroingPolicy::ZeroInitialize,
    ))
    .expect("allocator");
    let mut slab = allocator.acquire().expect("slab");
    slab.as_mut_slice().copy_from_slice(&packed);
    let bridge = MetalBridge::new().expect("Metal context");
    let registration = bridge.register(&slab).expect("registration");
    assert!(bridge
        .iq2_xxs_gemv(&registration, spec, &vec![0.0; columns - 1])
        .is_err());
    let mut nonfinite = vec![0.0; columns];
    nonfinite[17] = f32::NAN;
    assert!(bridge
        .iq2_xxs_gemv(&registration, spec, &nonfinite)
        .is_err());
}
