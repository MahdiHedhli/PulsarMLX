#![cfg(all(target_os = "macos", pulsar_native_mlx))]

use std::sync::{Mutex, MutexGuard, OnceLock};

use stream::{
    MlxContext, MlxDevice, MlxNativeFreeCounters, MlxStreamMode, MlxStreamOrigin,
    P1AccountingSnapshot,
};

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

fn assert_native_deltas_balanced(before: MlxNativeFreeCounters, after: MlxNativeFreeCounters) {
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
    assert_eq!(after.live_handles, before.live_handles);
    assert_eq!(after.origin_mismatches, before.origin_mismatches);
}

#[test]
fn gpu_managed_import_lifecycle_matrix_is_balanced() {
    let _guard = test_lock();
    run_managed_matrix(MlxStreamMode::BorrowedDefault, 30);
    run_managed_matrix(MlxStreamMode::Owned, 100);
}

#[test]
fn unified_p1_snapshot_is_live_complete_and_reconciles_after_teardown() {
    let _guard = test_lock();
    let before = P1AccountingSnapshot::capture().expect("pre snapshot");
    {
        let context =
            MlxContext::new(MlxDevice::Gpu, MlxStreamMode::Owned).expect("owned GPU MLX context");
        let active = P1AccountingSnapshot::capture().expect("active snapshot");
        assert_eq!(active.context_active, 1);
        assert_eq!(active.registrations - before.registrations, 1);
        let mut owner = vec![1.0_f32, -1.0, 0.0, -0.0];
        let input = context.import_f32(&mut owner).expect("managed input");
        let derived = input.add_self().expect("derived input");
        assert_eq!(input.destroy().expect("source-first destroy"), 0);
        assert_eq!(derived.destroy().expect("derived destroy"), 0);
        context.synchronize().expect("quiescence sync");
    }
    let after = P1AccountingSnapshot::capture().expect("post snapshot");
    assert_eq!(after.context_active, 0);
    assert_eq!(after.registrations - before.registrations, 1);
    assert_eq!(after.teardowns - before.teardowns, 1);
    assert_eq!(after.managed_created - before.managed_created, 1);
    assert_eq!(after.managed_destroyed - before.managed_destroyed, 1);
    assert_eq!(after.derived_created - before.derived_created, 1);
    assert_eq!(after.derived_destroyed - before.derived_destroyed, 1);
    assert_eq!(after.callback_count - before.callback_count, 1);
    assert_eq!(after.in_flight_work, 0);
    assert_eq!(after.stale_native_ready_generations, 0);
    assert_eq!(
        after.native_live_stream_handles,
        before.native_live_stream_handles
    );
    assert_eq!(
        after.owned_stream_freed - before.owned_stream_freed,
        after.native_owned_stream_freed - before.native_owned_stream_freed
    );
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
    let derived = input.add_self().expect("derived array");
    let before = context.ownership_snapshot().expect("pre-destroy snapshot");
    assert_eq!(before.callback_count, 0);
    assert_eq!(input.destroy().expect("source-first teardown"), 0);
    let retained = context
        .ownership_snapshot()
        .expect("retained-owner snapshot");
    assert_eq!(retained.callback_count, 0);
    assert_eq!(retained.managed_destroyed, 1);
    assert_eq!(retained.derived_created, 1);
    assert_eq!(retained.derived_destroyed, 0);
    assert_eq!(derived.destroy().expect("derived teardown"), 0);
    let accounting = context.ownership_snapshot().expect("ownership snapshot");
    assert_eq!(accounting.callback_count, 1);
    assert_eq!(accounting.managed_created, 1);
    assert_eq!(accounting.managed_destroyed, 1);
    assert_eq!(accounting.derived_created, 1);
    assert_eq!(accounting.derived_destroyed, 1);
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
    let native_before = MlxContext::debug_native_free_counters().expect("native counters");

    for _ in 0..1000 {
        let context = MlxContext::new(MlxDevice::Cpu, MlxStreamMode::BorrowedDefault)
            .expect("default CPU MLX context");
        assert_eq!(context.stream_mode(), MlxStreamMode::BorrowedDefault);
        drop(context);
    }
    let after_cpu = MlxContext::debug_stream_counters().expect("stream counters");
    let native_after_cpu = MlxContext::debug_native_free_counters().expect("native counters");
    assert_stream_deltas_balanced(before, after_cpu);
    assert_native_deltas_balanced(native_before, native_after_cpu);
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
    let native_after_gpu = MlxContext::debug_native_free_counters().expect("native counters");
    assert_stream_deltas_balanced(after_cpu, after_gpu);
    assert_native_deltas_balanced(native_after_cpu, native_after_gpu);
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
    let native_after = MlxContext::debug_native_free_counters().expect("native counters");
    assert_stream_deltas_balanced(after_gpu, after);
    assert_native_deltas_balanced(native_after_gpu, native_after);
    assert_eq!(
        after.default_cpu_created - after_gpu.default_cpu_created,
        1000
    );
    assert_eq!(after.owned_created - after_gpu.owned_created, 1000);
}

#[test]
fn stream_authority_separates_origin_from_native_handle_ownership() {
    let _guard = test_lock();
    for (device, mode, expected_origin) in [
        (
            MlxDevice::Cpu,
            MlxStreamMode::BorrowedDefault,
            MlxStreamOrigin::DefaultCpu,
        ),
        (
            MlxDevice::Gpu,
            MlxStreamMode::BorrowedDefault,
            MlxStreamOrigin::DefaultGpu,
        ),
        (
            MlxDevice::Gpu,
            MlxStreamMode::Owned,
            MlxStreamOrigin::OwnedDevice,
        ),
    ] {
        let context = MlxContext::new(device, mode).expect("MLX context");
        let authority = context.stream_authority().expect("stream authority");
        assert_eq!(authority.origin, expected_origin);
        assert!(
            authority.handle_owned,
            "all _new-returned handles require free"
        );
        drop(context);
    }
}

#[test]
fn missing_native_free_is_visible_even_when_logical_free_is_recorded() {
    let _guard = test_lock();
    let logical_before = MlxContext::debug_stream_counters().unwrap();
    let native_before = MlxContext::debug_native_free_counters().unwrap();
    let context = MlxContext::new(MlxDevice::Gpu, MlxStreamMode::Owned).unwrap();
    MlxContext::debug_set_next_release_fault(1);
    drop(context);
    let logical_after = MlxContext::debug_stream_counters().unwrap();
    let native_after = MlxContext::debug_native_free_counters().unwrap();
    assert_eq!(logical_after.owned_freed - logical_before.owned_freed, 1);
    assert_eq!(native_after.owned_freed - native_before.owned_freed, 0);
    assert_eq!(native_after.live_handles - native_before.live_handles, 1);
    MlxContext::debug_cleanup_release_fault().unwrap();
}

#[test]
fn missing_logical_free_is_visible_even_when_native_free_occurs() {
    let _guard = test_lock();
    let logical_before = MlxContext::debug_stream_counters().unwrap();
    let native_before = MlxContext::debug_native_free_counters().unwrap();
    let context = MlxContext::new(MlxDevice::Gpu, MlxStreamMode::Owned).unwrap();
    MlxContext::debug_set_next_release_fault(2);
    drop(context);
    let logical_after = MlxContext::debug_stream_counters().unwrap();
    let native_after = MlxContext::debug_native_free_counters().unwrap();
    assert_eq!(logical_after.owned_freed - logical_before.owned_freed, 0);
    assert_eq!(native_after.owned_freed - native_before.owned_freed, 1);
    MlxContext::debug_cleanup_release_fault().unwrap();
}

#[test]
fn duplicate_native_free_request_is_detected_without_double_free() {
    let _guard = test_lock();
    let before = MlxContext::debug_native_free_counters().unwrap();
    let context = MlxContext::new(MlxDevice::Gpu, MlxStreamMode::Owned).unwrap();
    MlxContext::debug_set_next_release_fault(3);
    drop(context);
    let after = MlxContext::debug_native_free_counters().unwrap();
    assert_eq!(
        after.duplicate_free_attempts - before.duplicate_free_attempts,
        1
    );
    assert_eq!(after.live_handles, before.live_handles);
}

#[test]
fn partial_stream_construction_failures_release_handles_and_singleton() {
    let _guard = test_lock();
    let before = MlxContext::debug_stream_counters().expect("stream counters");
    let native_before = MlxContext::debug_native_free_counters().expect("native counters");
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
    let native_after = MlxContext::debug_native_free_counters().expect("native counters");
    assert_stream_deltas_balanced(before, after);
    assert_native_deltas_balanced(native_before, native_after);
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

#[cfg(not(pulsar_native_mlx))]
#[test]
fn native_mlx_adapter_is_explicitly_skipped_when_unavailable() {
    eprintln!("native MLX C headers/libraries unavailable; adapter tests skipped");
}
