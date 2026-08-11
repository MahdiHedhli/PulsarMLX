#![cfg(all(target_os = "macos", pulsar_native_mlx))]

use std::sync::{Mutex, MutexGuard, OnceLock};

use stream::{MlxContext, MlxDevice, MlxStreamMode};

fn test_lock() -> MutexGuard<'static, ()> {
    static LOCK: OnceLock<Mutex<()>> = OnceLock::new();
    LOCK.get_or_init(|| Mutex::new(()))
        .lock()
        .expect("MLX test lock")
}

fn run_managed_matrix(mode: MlxStreamMode, repeats: usize) {
    let context = MlxContext::new(MlxDevice::Gpu, mode).expect("GPU MLX context");
    assert_eq!(context.stream_mode(), mode);
    for iteration in 0..repeats {
        let mut owner = vec![iteration as f32 + 1.0, 2.0, 3.0, 4.0];
        let owner_pointer = owner.as_ptr() as usize;
        let input = context.import_f32(&mut owner).expect("managed import");
        input.evaluate_sync().expect("explicit evaluation/sync");
        let pointer = input.data_pointer().expect("evaluated data pointer");
        assert_eq!(pointer, owner_pointer);
        let result = input.add_self().expect("GPU operation");
        result.evaluate_sync().expect("operation evaluation/sync");
        assert_eq!(result.destroy().expect("result teardown"), 0);
        assert_eq!(input.destroy().expect("input teardown"), 1);
        owner[0] = 0.0;
        assert_eq!(owner[0], 0.0);
    }
    let accounting = context.ownership_snapshot().expect("ownership snapshot");
    assert_eq!(accounting.callback_count, repeats as u64);
    assert_eq!(accounting.managed_created, repeats as u64);
    assert_eq!(accounting.managed_destroyed, repeats as u64);
    assert_eq!(accounting.derived_created, repeats as u64);
    assert_eq!(accounting.derived_destroyed, repeats as u64);
    assert_eq!(accounting.derived_live, 0);
}

fn assert_stream_deltas_balanced(
    before: stream::MlxDebugStreamCounters,
    after: stream::MlxDebugStreamCounters,
) {
    assert_eq!(
        after.default_cpu_created - before.default_cpu_created,
        after.default_cpu_freed - before.default_cpu_freed
    );
    assert_eq!(
        after.default_gpu_created - before.default_gpu_created,
        after.default_gpu_freed - before.default_gpu_freed
    );
    assert_eq!(
        after.owned_created - before.owned_created,
        after.owned_freed - before.owned_freed
    );
}

#[test]
fn gpu_managed_import_lifecycle_matrix_is_balanced() {
    let _guard = test_lock();
    run_managed_matrix(MlxStreamMode::BorrowedDefault, 30);
    run_managed_matrix(MlxStreamMode::Owned, 100);
}

#[test]
fn cpu_managed_import_lifecycle_is_balanced() {
    let _guard = test_lock();
    let context =
        MlxContext::new(MlxDevice::Cpu, MlxStreamMode::BorrowedDefault).expect("CPU MLX context");
    for _ in 0..30 {
        let mut owner = vec![1.0_f32, 2.0, 3.0, 4.0];
        let input = context.import_f32(&mut owner).expect("managed import");
        input.evaluate_sync().expect("CPU evaluation/sync");
        assert_eq!(input.destroy().expect("CPU teardown"), 1);
    }
    let accounting = context.ownership_snapshot().expect("ownership snapshot");
    assert_eq!(accounting.callback_count, 30);
    assert_eq!(accounting.managed_created, 30);
    assert_eq!(accounting.managed_destroyed, 30);
    assert_eq!(accounting.derived_created, 0);
}

#[test]
fn source_first_derived_teardown_keeps_owner_state_alive() {
    let _guard = test_lock();
    let context = MlxContext::new(MlxDevice::Gpu, MlxStreamMode::Owned).expect("GPU MLX context");
    let mut owner = vec![1.0_f32, 2.0, 3.0, 4.0];
    let input = context.import_f32(&mut owner).expect("managed import");
    let first = input.add_self().expect("first derived array");
    let second = input.add_self().expect("second derived array");
    first
        .evaluate_sync()
        .expect("first derived evaluation/sync");
    second
        .evaluate_sync()
        .expect("second derived evaluation/sync");
    assert_eq!(input.destroy().expect("source-first teardown"), 1);
    assert_eq!(first.destroy().expect("first derived teardown"), 0);
    assert_eq!(second.destroy().expect("second derived teardown"), 0);
    context
        .synchronize()
        .expect("post-teardown synchronization");
    let accounting = context.ownership_snapshot().expect("ownership snapshot");
    assert_eq!(accounting.callback_count, 1);
    assert_eq!(accounting.managed_created, 1);
    assert_eq!(accounting.managed_destroyed, 1);
    assert_eq!(accounting.derived_created, 2);
    assert_eq!(accounting.derived_destroyed, 2);
    assert_eq!(accounting.derived_live, 0);
}

#[test]
fn derived_first_teardown_reconciles_accounting() {
    let _guard = test_lock();
    let context = MlxContext::new(MlxDevice::Gpu, MlxStreamMode::Owned).expect("GPU MLX context");
    let mut owner = vec![1.0_f32, 2.0, 3.0, 4.0];
    let input = context.import_f32(&mut owner).expect("managed import");
    let derived = input.add_self().expect("derived array");
    assert_eq!(derived.destroy().expect("derived-first teardown"), 0);
    assert_eq!(input.destroy().expect("source teardown"), 1);
    let accounting = context.ownership_snapshot().expect("ownership snapshot");
    assert_eq!(accounting.callback_count, 1);
    assert_eq!(accounting.derived_created, accounting.derived_destroyed);
}

#[test]
fn default_and_owned_stream_creation_balance_over_1000_contexts_each() {
    let _guard = test_lock();
    let before = MlxContext::debug_stream_counters().expect("stream counters");

    for _ in 0..1000 {
        let context = MlxContext::new(MlxDevice::Cpu, MlxStreamMode::BorrowedDefault)
            .expect("default CPU MLX context");
        assert_eq!(context.stream_mode(), MlxStreamMode::BorrowedDefault);
        drop(context);
    }
    let after_cpu = MlxContext::debug_stream_counters().expect("stream counters");
    assert_stream_deltas_balanced(before, after_cpu);
    assert_eq!(
        after_cpu.default_cpu_created - before.default_cpu_created,
        2000
    );

    for _ in 0..1000 {
        let context = MlxContext::new(MlxDevice::Gpu, MlxStreamMode::BorrowedDefault)
            .expect("default GPU MLX context");
        assert_eq!(context.stream_mode(), MlxStreamMode::BorrowedDefault);
        drop(context);
    }
    let after_gpu = MlxContext::debug_stream_counters().expect("stream counters");
    assert_stream_deltas_balanced(after_cpu, after_gpu);
    assert_eq!(
        after_gpu.default_cpu_created - after_cpu.default_cpu_created,
        1000
    );
    assert_eq!(
        after_gpu.default_gpu_created - after_cpu.default_gpu_created,
        1000
    );

    for _ in 0..1000 {
        let context =
            MlxContext::new(MlxDevice::Gpu, MlxStreamMode::Owned).expect("owned GPU MLX context");
        assert_eq!(context.stream_mode(), MlxStreamMode::Owned);
        drop(context);
    }
    let after = MlxContext::debug_stream_counters().expect("stream counters");
    assert_stream_deltas_balanced(after_gpu, after);
    assert_eq!(
        after.default_cpu_created - after_gpu.default_cpu_created,
        1000
    );
    assert_eq!(after.owned_created - after_gpu.owned_created, 1000);
}

#[test]
fn partial_stream_construction_failures_release_handles_and_singleton() {
    let _guard = test_lock();
    let before = MlxContext::debug_stream_counters().expect("stream counters");
    for (device, mode) in [
        (MlxDevice::Cpu, MlxStreamMode::BorrowedDefault),
        (MlxDevice::Gpu, MlxStreamMode::BorrowedDefault),
        (MlxDevice::Gpu, MlxStreamMode::Owned),
    ] {
        MlxContext::debug_fail_next_after_stream_create();
        let error = match MlxContext::new(device, mode) {
            Ok(_) => panic!("injected construction failure unexpectedly succeeded"),
            Err(error) => error,
        };
        assert!(error.contains("injected failure after MLX stream creation"));
        let recreated = MlxContext::new(device, mode).expect("singleton released after failure");
        drop(recreated);
    }
    let after = MlxContext::debug_stream_counters().expect("stream counters");
    assert_stream_deltas_balanced(before, after);
}

#[test]
fn process_singleton_rejects_second_context_and_recovers() {
    let _guard = test_lock();
    let first =
        MlxContext::new(MlxDevice::Cpu, MlxStreamMode::BorrowedDefault).expect("first context");
    assert!(MlxContext::new(MlxDevice::Cpu, MlxStreamMode::BorrowedDefault).is_err());
    drop(first);
    assert!(MlxContext::new(MlxDevice::Cpu, MlxStreamMode::BorrowedDefault).is_ok());
}

#[test]
fn shape_count_guard_rejects_zero_and_int_overflow() {
    assert!(MlxContext::validate_f32_count(0).is_err());
    assert!(MlxContext::validate_f32_count(i32::MAX as usize).is_ok());
    assert!(MlxContext::validate_f32_count(i32::MAX as usize + 1).is_err());
}

#[test]
fn empty_import_fails_closed_without_an_owner() {
    let _guard = test_lock();
    let before = MlxContext::debug_stream_counters().expect("stream counters");
    let context = MlxContext::new(MlxDevice::Gpu, MlxStreamMode::Owned).expect("GPU MLX context");
    let mut owner = Vec::new();
    assert!(context.import_f32(&mut owner).is_err());
    drop(context);
    let after = MlxContext::debug_stream_counters().expect("stream counters");
    assert_stream_deltas_balanced(before, after);
}

#[test]
fn shaped_matvec_uses_production_adapter_and_reconciles() {
    let _guard = test_lock();
    let context = MlxContext::new(MlxDevice::Gpu, MlxStreamMode::Owned).expect("GPU MLX context");
    let mut matrix_owner = vec![1.0_f32, 2.0, 3.0, 4.0, -1.0, 0.5];
    let mut vector_owner = vec![2.0_f32, -1.0, 0.25];
    let matrix = context
        .import_f32_shaped(&mut matrix_owner, &[2, 3])
        .expect("shaped matrix import");
    let vector = context
        .import_f32_shaped(&mut vector_owner, &[3])
        .expect("shaped vector import");
    let result = matrix.matvec(&vector).expect("typed matvec");
    result.evaluate_sync().expect("matvec evaluation/sync");
    let mut output = [0.0_f32; 2];
    result.copy_f32(&mut output).expect("bounded result copy");
    assert_eq!(
        output.map(f32::to_bits),
        [0.75_f32.to_bits(), 9.125_f32.to_bits()]
    );
    assert_eq!(result.destroy().expect("result teardown"), 0);
    assert_eq!(vector.destroy().expect("vector teardown"), 1);
    assert_eq!(matrix.destroy().expect("matrix teardown"), 1);

    let accounting = context.ownership_snapshot().expect("ownership snapshot");
    assert_eq!(accounting.callback_count, 2);
    assert_eq!(accounting.managed_created, 2);
    assert_eq!(accounting.managed_destroyed, 2);
    assert_eq!(accounting.derived_created, 1);
    assert_eq!(accounting.derived_destroyed, 1);
    assert_eq!(accounting.derived_live, 0);
}

#[test]
fn shaped_import_and_matvec_reject_malformed_dimensions() {
    let _guard = test_lock();
    let context = MlxContext::new(MlxDevice::Gpu, MlxStreamMode::Owned).expect("GPU MLX context");
    let mut malformed = vec![0.0_f32; 4];
    assert!(context.import_f32_shaped(&mut malformed, &[]).is_err());
    assert!(context.import_f32_shaped(&mut malformed, &[0, 4]).is_err());
    assert!(context.import_f32_shaped(&mut malformed, &[2, 3]).is_err());
    assert!(context
        .import_f32_shaped(&mut malformed, &[1, 1, 4])
        .is_err());

    let mut matrix_owner = vec![1.0_f32; 4];
    let mut vector_owner = vec![1.0_f32; 3];
    let matrix = context
        .import_f32_shaped(&mut matrix_owner, &[2, 2])
        .expect("matrix import");
    let vector = context
        .import_f32_shaped(&mut vector_owner, &[3])
        .expect("vector import");
    assert!(matrix.matvec(&vector).is_err());
}

#[cfg(not(pulsar_native_mlx))]
#[test]
fn native_mlx_adapter_is_explicitly_skipped_when_unavailable() {
    eprintln!("native MLX C headers/libraries unavailable; adapter tests skipped");
}
