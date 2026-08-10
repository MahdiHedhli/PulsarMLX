#![cfg(target_os = "macos")]

use stream::{
    iq3_xxs_gemv_reference, iq3_xxs_lookup_sha256, synthetic_iq3_xxs_matrix, Iq3XxsGemvSpec,
    MetalBridge, StableSlabAllocator, StableSlabConfig, ZeroingPolicy,
};

#[test]
fn valid_packed_iq3_xxs_request_has_exact_byte_accounting() {
    let spec = Iq3XxsGemvSpec::new(2, 256, 196, 256).expect("valid request");
    assert_eq!(spec.rows(), 2);
    assert_eq!(spec.columns(), 256);
    assert_eq!(spec.packed_row_bytes(), 98);
    assert_eq!(spec.packed_matrix_bytes(), 196);
    assert_eq!(spec.complete_f32_weight_materialized_bytes(), 0);
}

#[test]
fn malformed_iq3_shape_and_lengths_fail_before_dispatch() {
    for result in [
        Iq3XxsGemvSpec::new(0, 256, 0, 256),
        Iq3XxsGemvSpec::new(1, 0, 0, 0),
        Iq3XxsGemvSpec::new(1, 255, 98, 255),
        Iq3XxsGemvSpec::new(1, 256, 97, 256),
        Iq3XxsGemvSpec::new(1, 256, 99, 256),
        Iq3XxsGemvSpec::new(1, 256, 98, 255),
        Iq3XxsGemvSpec::new(usize::MAX, 256, 98, 256),
    ] {
        assert!(result.is_err());
    }
}

#[test]
fn representative_down_shape_accounts_without_f32_weights() {
    let rows = 6144;
    let columns = 2048;
    let packed = rows * (columns / 256) * 98;
    let spec =
        Iq3XxsGemvSpec::new(rows, columns, packed, columns).expect("representative GLM down shape");
    assert_eq!(spec.packed_row_bytes(), 784);
    assert_eq!(spec.packed_matrix_bytes(), 4_816_896);
    assert_eq!(spec.complete_f32_weight_materialized_bytes(), 0);
}

#[test]
fn iq3_lookup_tables_have_stable_distinct_hashes() {
    let (grid, signs) = iq3_xxs_lookup_sha256();
    assert_eq!(grid.len(), 64);
    assert_eq!(signs.len(), 64);
    assert_ne!(grid, signs);
    assert!(grid.chars().all(|value| value.is_ascii_hexdigit()));
    assert!(signs.chars().all(|value| value.is_ascii_hexdigit()));
}

#[test]
fn native_iq3_xxs_scaffold_qualifies_and_repeats() {
    let rows = 8;
    let columns = 512;
    let packed = synthetic_iq3_xxs_matrix(rows, columns).expect("synthetic packed matrix");
    let activation = (0..columns)
        .map(|index| ((index % 37) as f32 - 18.0) * 0.01)
        .collect::<Vec<_>>();
    let spec = Iq3XxsGemvSpec::new(rows, columns, packed.len(), activation.len())
        .expect("valid synthetic request");
    let reference = iq3_xxs_gemv_reference(&packed, spec, &activation).expect("CPU reference");

    let allocator = StableSlabAllocator::new(StableSlabConfig::new(
        packed.len(),
        4096,
        1,
        ZeroingPolicy::ZeroInitialize,
    ))
    .expect("bounded page-aligned allocator");
    let mut slab = allocator.acquire().expect("stable packed slab");
    slab.as_mut_slice().copy_from_slice(&packed);
    let bridge = MetalBridge::new().expect("strict Metal context");
    let compiler = bridge.compiler_settings();
    assert!(!compiler.fast_math_enabled);
    assert_eq!(compiler.language_version, "3.2");
    let registration = bridge.register(&slab).expect("no-copy registration");
    let first = bridge
        .iq3_xxs_gemv(&registration, spec, &activation)
        .expect("first direct IQ3 GEMV");
    let first_bits = first
        .output
        .iter()
        .map(|value| value.to_bits())
        .collect::<Vec<_>>();
    for (expected, actual) in reference.iter().zip(&first.output) {
        let error = (expected - actual).abs();
        assert!(
            error <= 0.00025 + 0.00025 * expected.abs(),
            "reference={expected} actual={actual} error={error}"
        );
    }
    assert_eq!(first.telemetry.cpu_fallback_count, 0);
    assert_eq!(first.telemetry.complete_f32_weight_materialized_bytes, 0);
    assert_eq!(registration.in_flight_count(), 0);

    for _ in 0..100 {
        let repeated = bridge
            .iq3_xxs_gemv(&registration, spec, &activation)
            .expect("deterministic IQ3 repeat");
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
        assert_eq!(registration.in_flight_count(), 0);
    }
}

#[test]
fn iq3_rejects_bad_activation_before_dispatch() {
    let packed = synthetic_iq3_xxs_matrix(1, 256).expect("synthetic matrix");
    let spec = Iq3XxsGemvSpec::new(1, 256, packed.len(), 256).expect("valid spec");
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
        .iq3_xxs_gemv(&registration, spec, &vec![0.0; 255])
        .is_err());
    let mut nonfinite = vec![0.0; 256];
    nonfinite[17] = f32::INFINITY;
    assert!(bridge
        .iq3_xxs_gemv(&registration, spec, &nonfinite)
        .is_err());
    assert_eq!(registration.in_flight_count(), 0);
}

#[test]
fn iq3_rejects_registration_mismatch_and_cross_context() {
    let packed = synthetic_iq3_xxs_matrix(1, 512).expect("two-block matrix");
    let smaller = Iq3XxsGemvSpec::new(1, 256, 98, 256).expect("smaller spec");
    let full = Iq3XxsGemvSpec::new(1, 512, packed.len(), 512).expect("full spec");
    let allocator = StableSlabAllocator::new(StableSlabConfig::new(
        packed.len(),
        4096,
        1,
        ZeroingPolicy::ZeroInitialize,
    ))
    .expect("allocator");
    let mut slab = allocator.acquire().expect("slab");
    slab.as_mut_slice().copy_from_slice(&packed);
    let owner = MetalBridge::new().expect("owner");
    let other = MetalBridge::new().expect("other");
    let registration = owner.register(&slab).expect("registration");
    let length_error = owner
        .iq3_xxs_gemv(&registration, smaller, &vec![0.0; 256])
        .expect_err("length mismatch");
    assert!(length_error.contains("registration length"));
    let context_error = other
        .iq3_xxs_gemv(&registration, full, &vec![0.0; 512])
        .expect_err("cross-context dispatch");
    assert!(context_error.contains("belongs to another context"));
    assert_eq!(registration.in_flight_count(), 0);
}

#[test]
fn repeated_iq3_context_registration_and_teardown_is_stable() {
    let packed = synthetic_iq3_xxs_matrix(2, 256).expect("synthetic matrix");
    let spec = Iq3XxsGemvSpec::new(2, 256, packed.len(), 256).expect("valid spec");
    for _ in 0..32 {
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
        let result = bridge
            .iq3_xxs_gemv(&registration, spec, &vec![0.125; 256])
            .expect("direct IQ3 GEMV");
        assert_eq!(result.telemetry.cpu_fallback_count, 0);
        assert_eq!(result.telemetry.complete_f32_weight_materialized_bytes, 0);
        assert_eq!(registration.in_flight_count(), 0);
    }
}
