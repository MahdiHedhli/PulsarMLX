use std::ffi::CStr;
use std::marker::PhantomData;
use std::os::raw::c_char;
use std::ptr;

#[repr(C)]
struct RawMlxContext {
    _private: [u8; 0],
}

#[repr(C)]
struct RawMlxArray {
    _private: [u8; 0],
}

unsafe extern "C" {
    fn pulsar_mlx_context_create(
        device_type: i32,
        stream_mode: i32,
        out_context: *mut *mut RawMlxContext,
        error_buffer: *mut c_char,
        error_capacity: usize,
    ) -> i32;
    fn pulsar_mlx_context_destroy(context: *mut RawMlxContext);
    fn pulsar_mlx_context_synchronize(
        context: *mut RawMlxContext,
        error_buffer: *mut c_char,
        error_capacity: usize,
    ) -> i32;
    fn pulsar_mlx_context_ownership_snapshot(
        context: *mut RawMlxContext,
        callback_count: *mut u64,
        managed_created: *mut u64,
        managed_destroyed: *mut u64,
        derived_created: *mut u64,
        derived_destroyed: *mut u64,
        derived_live: *mut u64,
        error_buffer: *mut c_char,
        error_capacity: usize,
    ) -> i32;
    fn pulsar_mlx_debug_stream_counters(
        default_cpu_created: *mut u64,
        default_cpu_freed: *mut u64,
        default_gpu_created: *mut u64,
        default_gpu_freed: *mut u64,
        owned_created: *mut u64,
        owned_freed: *mut u64,
        error_buffer: *mut c_char,
        error_capacity: usize,
    ) -> i32;
    fn pulsar_mlx_debug_fail_next_after_stream_create();
    fn pulsar_mlx_validate_f32_count(
        count: usize,
        error_buffer: *mut c_char,
        error_capacity: usize,
    ) -> i32;
    fn pulsar_mlx_import_f32(
        context: *mut RawMlxContext,
        data: *mut f32,
        count: usize,
        out_array: *mut *mut RawMlxArray,
        error_buffer: *mut c_char,
        error_capacity: usize,
    ) -> i32;
    fn pulsar_mlx_array_eval_sync(
        context: *mut RawMlxContext,
        array: *mut RawMlxArray,
        error_buffer: *mut c_char,
        error_capacity: usize,
    ) -> i32;
    fn pulsar_mlx_array_add_self(
        context: *mut RawMlxContext,
        array: *mut RawMlxArray,
        out_array: *mut *mut RawMlxArray,
        error_buffer: *mut c_char,
        error_capacity: usize,
    ) -> i32;
    fn pulsar_mlx_array_data_pointer(
        array: *mut RawMlxArray,
        out_pointer: *mut usize,
        error_buffer: *mut c_char,
        error_capacity: usize,
    ) -> i32;
    fn pulsar_mlx_array_destroy(
        array: *mut RawMlxArray,
        callback_count: *mut u64,
        error_buffer: *mut c_char,
        error_capacity: usize,
    ) -> i32;
}

const ERROR_CAPACITY: usize = 512;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum MlxDevice {
    Cpu,
    Gpu,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum MlxStreamMode {
    BorrowedDefault,
    Owned,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct MlxOwnershipSnapshot {
    pub callback_count: u64,
    pub managed_created: u64,
    pub managed_destroyed: u64,
    pub derived_created: u64,
    pub derived_destroyed: u64,
    pub derived_live: u64,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct MlxDebugStreamCounters {
    pub default_cpu_created: u64,
    pub default_cpu_freed: u64,
    pub default_gpu_created: u64,
    pub default_gpu_freed: u64,
    pub owned_created: u64,
    pub owned_freed: u64,
}

fn bridge_error(status: i32, buffer: &[i8; ERROR_CAPACITY]) -> String {
    let message = unsafe { CStr::from_ptr(buffer.as_ptr()) };
    format!("MLX bridge status {status}: {}", message.to_string_lossy())
}

pub struct MlxContext {
    raw: *mut RawMlxContext,
    stream_mode: MlxStreamMode,
}

pub struct MlxArray<'a> {
    raw: *mut RawMlxArray,
    context: &'a MlxContext,
    _owner: PhantomData<&'a [f32]>,
}

pub struct MlxComputedArray<'a> {
    raw: *mut RawMlxArray,
    context: &'a MlxContext,
    _owner: PhantomData<&'a [f32]>,
}

impl MlxContext {
    pub fn new(device: MlxDevice, stream_mode: MlxStreamMode) -> Result<Self, String> {
        let mut raw = ptr::null_mut();
        let mut error = [0_i8; ERROR_CAPACITY];
        let status = unsafe {
            pulsar_mlx_context_create(
                match device {
                    MlxDevice::Cpu => 0,
                    MlxDevice::Gpu => 1,
                },
                match stream_mode {
                    MlxStreamMode::BorrowedDefault => 0,
                    MlxStreamMode::Owned => 1,
                },
                &mut raw,
                error.as_mut_ptr(),
                ERROR_CAPACITY,
            )
        };
        if status != 0 || raw.is_null() {
            return Err(bridge_error(status, &error));
        }
        Ok(Self { raw, stream_mode })
    }

    pub fn stream_mode(&self) -> MlxStreamMode {
        self.stream_mode
    }

    pub fn synchronize(&self) -> Result<(), String> {
        let mut error = [0_i8; ERROR_CAPACITY];
        let status = unsafe {
            pulsar_mlx_context_synchronize(self.raw, error.as_mut_ptr(), ERROR_CAPACITY)
        };
        if status != 0 {
            return Err(bridge_error(status, &error));
        }
        Ok(())
    }

    pub fn ownership_snapshot(&self) -> Result<MlxOwnershipSnapshot, String> {
        let mut callback_count = 0;
        let mut managed_created = 0;
        let mut managed_destroyed = 0;
        let mut derived_created = 0;
        let mut derived_destroyed = 0;
        let mut derived_live = 0;
        let mut error = [0_i8; ERROR_CAPACITY];
        let status = unsafe {
            pulsar_mlx_context_ownership_snapshot(
                self.raw,
                &mut callback_count,
                &mut managed_created,
                &mut managed_destroyed,
                &mut derived_created,
                &mut derived_destroyed,
                &mut derived_live,
                error.as_mut_ptr(),
                ERROR_CAPACITY,
            )
        };
        if status != 0 {
            return Err(bridge_error(status, &error));
        }
        Ok(MlxOwnershipSnapshot {
            callback_count,
            managed_created,
            managed_destroyed,
            derived_created,
            derived_destroyed,
            derived_live,
        })
    }

    pub fn debug_stream_counters() -> Result<MlxDebugStreamCounters, String> {
        let mut default_cpu_created = 0;
        let mut default_cpu_freed = 0;
        let mut default_gpu_created = 0;
        let mut default_gpu_freed = 0;
        let mut owned_created = 0;
        let mut owned_freed = 0;
        let mut error = [0_i8; ERROR_CAPACITY];
        let status = unsafe {
            pulsar_mlx_debug_stream_counters(
                &mut default_cpu_created,
                &mut default_cpu_freed,
                &mut default_gpu_created,
                &mut default_gpu_freed,
                &mut owned_created,
                &mut owned_freed,
                error.as_mut_ptr(),
                ERROR_CAPACITY,
            )
        };
        if status != 0 {
            return Err(bridge_error(status, &error));
        }
        Ok(MlxDebugStreamCounters {
            default_cpu_created,
            default_cpu_freed,
            default_gpu_created,
            default_gpu_freed,
            owned_created,
            owned_freed,
        })
    }

    #[doc(hidden)]
    pub fn debug_fail_next_after_stream_create() {
        unsafe { pulsar_mlx_debug_fail_next_after_stream_create() };
    }

    pub fn validate_f32_count(count: usize) -> Result<(), String> {
        let mut error = [0_i8; ERROR_CAPACITY];
        let status = unsafe {
            pulsar_mlx_validate_f32_count(count, error.as_mut_ptr(), ERROR_CAPACITY)
        };
        if status != 0 {
            return Err(bridge_error(status, &error));
        }
        Ok(())
    }

    pub fn import_f32<'a>(&'a self, owner: &'a mut [f32]) -> Result<MlxArray<'a>, String> {
        if owner.is_empty() {
            return Err("MLX f32 import requires a non-empty owner".to_owned());
        }
        let mut raw = ptr::null_mut();
        let mut error = [0_i8; ERROR_CAPACITY];
        let status = unsafe {
            pulsar_mlx_import_f32(
                self.raw,
                owner.as_mut_ptr(),
                owner.len(),
                &mut raw,
                error.as_mut_ptr(),
                ERROR_CAPACITY,
            )
        };
        if status != 0 || raw.is_null() {
            return Err(bridge_error(status, &error));
        }
        Ok(MlxArray {
            raw,
            context: self,
            _owner: PhantomData,
        })
    }
}

impl<'a> MlxArray<'a> {
    pub fn evaluate_sync(&self) -> Result<(), String> {
        let mut error = [0_i8; ERROR_CAPACITY];
        let status = unsafe {
            pulsar_mlx_array_eval_sync(
                self.context.raw,
                self.raw,
                error.as_mut_ptr(),
                ERROR_CAPACITY,
            )
        };
        if status != 0 {
            return Err(bridge_error(status, &error));
        }
        Ok(())
    }

    pub fn add_self(&self) -> Result<MlxComputedArray<'a>, String> {
        let mut raw = ptr::null_mut();
        let mut error = [0_i8; ERROR_CAPACITY];
        let status = unsafe {
            pulsar_mlx_array_add_self(
                self.context.raw,
                self.raw,
                &mut raw,
                error.as_mut_ptr(),
                ERROR_CAPACITY,
            )
        };
        if status != 0 || raw.is_null() {
            return Err(bridge_error(status, &error));
        }
        Ok(MlxComputedArray {
            raw,
            context: self.context,
            _owner: PhantomData,
        })
    }

    pub fn data_pointer(&self) -> Result<usize, String> {
        let mut pointer = 0;
        let mut error = [0_i8; ERROR_CAPACITY];
        let status = unsafe {
            pulsar_mlx_array_data_pointer(
                self.raw,
                &mut pointer,
                error.as_mut_ptr(),
                ERROR_CAPACITY,
            )
        };
        if status != 0 {
            return Err(bridge_error(status, &error));
        }
        Ok(pointer)
    }

    pub fn destroy(mut self) -> Result<u64, String> {
        self.destroy_inner()
    }

    fn destroy_inner(&mut self) -> Result<u64, String> {
        if self.raw.is_null() {
            return Ok(0);
        }
        let mut callbacks = 0;
        let mut error = [0_i8; ERROR_CAPACITY];
        let status = unsafe {
            pulsar_mlx_array_destroy(
                self.raw,
                &mut callbacks,
                error.as_mut_ptr(),
                ERROR_CAPACITY,
            )
        };
        self.raw = ptr::null_mut();
        if status != 0 {
            return Err(bridge_error(status, &error));
        }
        Ok(callbacks)
    }
}

impl Drop for MlxArray<'_> {
    fn drop(&mut self) {
        let _ = self.destroy_inner();
    }
}

impl<'a> MlxComputedArray<'a> {
    pub fn evaluate_sync(&self) -> Result<(), String> {
        let mut error = [0_i8; ERROR_CAPACITY];
        let status = unsafe {
            pulsar_mlx_array_eval_sync(
                self.context.raw,
                self.raw,
                error.as_mut_ptr(),
                ERROR_CAPACITY,
            )
        };
        if status != 0 {
            return Err(bridge_error(status, &error));
        }
        Ok(())
    }

    pub fn destroy(mut self) -> Result<u64, String> {
        self.destroy_inner()
    }

    fn destroy_inner(&mut self) -> Result<u64, String> {
        if self.raw.is_null() {
            return Ok(0);
        }
        let mut callbacks = 0;
        let mut error = [0_i8; ERROR_CAPACITY];
        let status = unsafe {
            pulsar_mlx_array_destroy(
                self.raw,
                &mut callbacks,
                error.as_mut_ptr(),
                ERROR_CAPACITY,
            )
        };
        self.raw = ptr::null_mut();
        if status != 0 {
            return Err(bridge_error(status, &error));
        }
        Ok(callbacks)
    }
}

impl Drop for MlxComputedArray<'_> {
    fn drop(&mut self) {
        let _ = self.destroy_inner();
    }
}

impl Drop for MlxContext {
    fn drop(&mut self) {
        if !self.raw.is_null() {
            unsafe { pulsar_mlx_context_destroy(self.raw) };
            self.raw = ptr::null_mut();
        }
    }
}
