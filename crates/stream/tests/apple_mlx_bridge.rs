#![cfg(all(target_os = "macos", pulsar_native_mlx))]

use stream::{MlxContext, MlxDevice, MlxStreamMode};

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
}

#[test]
fn gpu_managed_import_lifecycle_matrix_is_balanced() {
    run_managed_matrix(MlxStreamMode::BorrowedDefault, 30);
    run_managed_matrix(MlxStreamMode::Owned, 100);
}

#[test]
fn cpu_managed_import_lifecycle_is_balanced() {
    let context = MlxContext::new(MlxDevice::Cpu, MlxStreamMode::BorrowedDefault)
        .expect("CPU MLX context");
    for _ in 0..30 {
        let mut owner = vec![1.0_f32, 2.0, 3.0, 4.0];
        let input = context.import_f32(&mut owner).expect("managed import");
        input.evaluate_sync().expect("CPU evaluation/sync");
        assert_eq!(input.destroy().expect("CPU teardown"), 1);
    }
}

#[test]
fn empty_import_fails_closed_without_an_owner() {
    let context = MlxContext::new(MlxDevice::Gpu, MlxStreamMode::Owned)
        .expect("GPU MLX context");
    let mut owner = Vec::new();
    assert!(context.import_f32(&mut owner).is_err());
}

#[cfg(not(pulsar_native_mlx))]
#[test]
fn native_mlx_adapter_is_explicitly_skipped_when_unavailable() {
    eprintln!("native MLX C headers/libraries unavailable; adapter tests skipped");
}
