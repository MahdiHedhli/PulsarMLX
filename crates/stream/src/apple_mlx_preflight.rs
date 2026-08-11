#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum NativeMlxPreflightMode {
    DefaultGpu,
    OwnedDevice,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct NativeMlxPreflightReport {
    pub native_executed: bool,
    pub mode: NativeMlxPreflightMode,
    pub context_initially_active: bool,
    pub context_active_during: bool,
    pub context_active_after: bool,
    pub second_context_rejected: bool,
    pub singleton_reacquired: bool,
    pub pointer_identity: bool,
    pub explicit_synchronize: bool,
    pub callback_count: u64,
    pub managed_created: u64,
    pub managed_destroyed: u64,
    pub derived_created: u64,
    pub derived_destroyed: u64,
    pub derived_live: u64,
    pub default_cpu_created_before: u64,
    pub default_cpu_freed_before: u64,
    pub default_gpu_created_before: u64,
    pub default_gpu_freed_before: u64,
    pub owned_created_before: u64,
    pub owned_freed_before: u64,
    pub default_cpu_created_after: u64,
    pub default_cpu_freed_after: u64,
    pub default_gpu_created_after: u64,
    pub default_gpu_freed_after: u64,
    pub owned_created_after: u64,
    pub owned_freed_after: u64,
}

impl NativeMlxPreflightReport {
    pub fn reconciled(self) -> bool {
        self.native_executed
            && !self.context_initially_active
            && self.context_active_during
            && !self.context_active_after
            && self.second_context_rejected
            && self.singleton_reacquired
            && self.pointer_identity
            && self.explicit_synchronize
            && self.callback_count == self.managed_created
            && self.managed_created == self.managed_destroyed
            && self.derived_created == self.derived_destroyed
            && self.derived_live == 0
            && self.default_cpu_created_after - self.default_cpu_created_before
                == self.default_cpu_freed_after - self.default_cpu_freed_before
            && self.default_gpu_created_after - self.default_gpu_created_before
                == self.default_gpu_freed_after - self.default_gpu_freed_before
            && self.owned_created_after - self.owned_created_before
                == self.owned_freed_after - self.owned_freed_before
    }
}

#[cfg(all(target_os = "macos", pulsar_native_mlx))]
pub fn run_native_mlx_preflight(
    mode: NativeMlxPreflightMode,
) -> Result<NativeMlxPreflightReport, String> {
    use crate::{MlxContext, MlxDevice, MlxStreamMode};

    let before = MlxContext::debug_stream_counters()?;
    let context_initially_active = MlxContext::debug_context_active();
    if context_initially_active {
        return Err("MLX context singleton was already claimed before preflight".to_owned());
    }
    let stream_mode = match mode {
        NativeMlxPreflightMode::DefaultGpu => MlxStreamMode::BorrowedDefault,
        NativeMlxPreflightMode::OwnedDevice => MlxStreamMode::Owned,
    };
    let context = MlxContext::new(MlxDevice::Gpu, stream_mode)?;
    let context_active_during = MlxContext::debug_context_active();
    let second_context_rejected = MlxContext::new(MlxDevice::Gpu, stream_mode).is_err();

    let mut owner = vec![1.0_f32, -2.0, 3.0, -4.0];
    let owner_pointer = owner.as_ptr() as usize;
    let input = context.import_f32(&mut owner)?;
    input.evaluate_sync()?;
    let pointer_identity = input.data_pointer()? == owner_pointer;
    let derived = input.add_self()?;
    derived.evaluate_sync()?;
    let explicit_synchronize = context.synchronize().is_ok();
    if !explicit_synchronize {
        return Err("explicit MLX synchronization failed".to_owned());
    }
    let input_callbacks = input.destroy()?;
    derived.destroy()?;
    context.synchronize()?;
    let ownership = context.ownership_snapshot()?;
    if input_callbacks != 1 {
        return Err(format!(
            "managed owner callback count {input_callbacks} differs from one"
        ));
    }
    drop(context);
    let context_active_after_first = MlxContext::debug_context_active();
    let recreated = MlxContext::new(MlxDevice::Gpu, stream_mode)?;
    let singleton_reacquired = MlxContext::debug_context_active();
    drop(recreated);
    let context_active_after = MlxContext::debug_context_active();
    if context_active_after_first || context_active_after {
        return Err("MLX context singleton remained claimed after teardown".to_owned());
    }
    let after = MlxContext::debug_stream_counters()?;
    let report = NativeMlxPreflightReport {
        native_executed: true,
        mode,
        context_initially_active,
        context_active_during,
        context_active_after,
        second_context_rejected,
        singleton_reacquired,
        pointer_identity,
        explicit_synchronize,
        callback_count: ownership.callback_count,
        managed_created: ownership.managed_created,
        managed_destroyed: ownership.managed_destroyed,
        derived_created: ownership.derived_created,
        derived_destroyed: ownership.derived_destroyed,
        derived_live: ownership.derived_live,
        default_cpu_created_before: before.default_cpu_created,
        default_cpu_freed_before: before.default_cpu_freed,
        default_gpu_created_before: before.default_gpu_created,
        default_gpu_freed_before: before.default_gpu_freed,
        owned_created_before: before.owned_created,
        owned_freed_before: before.owned_freed,
        default_cpu_created_after: after.default_cpu_created,
        default_cpu_freed_after: after.default_cpu_freed,
        default_gpu_created_after: after.default_gpu_created,
        default_gpu_freed_after: after.default_gpu_freed,
        owned_created_after: after.owned_created,
        owned_freed_after: after.owned_freed,
    };
    if !report.reconciled() {
        return Err(format!(
            "MLX adapter preflight did not reconcile: {report:?}"
        ));
    }
    Ok(report)
}

#[cfg(not(all(target_os = "macos", pulsar_native_mlx)))]
pub fn run_native_mlx_preflight(
    _mode: NativeMlxPreflightMode,
) -> Result<NativeMlxPreflightReport, String> {
    Err("native MLX adapter was not compiled; preflight cannot skip".to_owned())
}
