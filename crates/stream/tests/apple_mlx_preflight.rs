#![cfg(all(target_os = "macos", pulsar_native_mlx))]

use stream::{run_native_mlx_preflight, NativeMlxPreflightMode};

#[test]
fn production_preflight_reconciles_in_fresh_test_process() {
    let report = run_native_mlx_preflight(NativeMlxPreflightMode::OwnedDevice)
        .expect("production native MLX preflight");
    assert!(report.native_executed);
    assert!(report.pointer_identity);
    assert!(report.explicit_synchronize);
    assert!(report.second_context_rejected);
    assert!(report.singleton_reacquired);
    assert!(report.reconciled());
}
