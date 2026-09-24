//! Hand-written FFI for the MLX-C surface of plan §6.2 (MLX-C 0726ca92 plus
//! the four hash-verified patches). Layouts and enumerator values are pinned
//! by `src/abi_check.c` at build time and compared at run time with
//! [`verify_abi`] before the first MLX-C call.
//!
//! Every call that goes through [`numerical`] or [`import`] is counted, so the
//! child can prove that a refused request reached no MLX-C numerical call and
//! no import (acceptance B6).

#![allow(non_camel_case_types)]

use std::cell::Cell;
use std::os::raw::{c_char, c_int, c_void};

#[repr(C)]
#[derive(Clone, Copy)]
pub struct mlx_array {
    pub ctx: *mut c_void,
}
#[repr(C)]
#[derive(Clone, Copy)]
pub struct mlx_device {
    pub ctx: *mut c_void,
}
#[repr(C)]
#[derive(Clone, Copy)]
pub struct mlx_stream {
    pub ctx: *mut c_void,
}
#[repr(C)]
#[derive(Clone, Copy)]
pub struct mlx_string {
    pub ctx: *mut c_void,
}
#[repr(C)]
#[derive(Clone, Copy)]
pub struct mlx_device_info {
    pub ctx: *mut c_void,
}
#[repr(C)]
#[derive(Clone, Copy)]
pub struct mlx_optional_int {
    pub value: c_int,
    pub has_value: bool,
}
#[repr(C)]
#[derive(Clone, Copy)]
pub struct mlx_optional_dtype {
    pub value: mlx_dtype,
    pub has_value: bool,
}

pub type mlx_dtype = c_int;
pub type mlx_device_type = c_int;
pub const MLX_CPU: mlx_device_type = 0;
pub const MLX_GPU: mlx_device_type = 1;
pub const MLX_UINT16: mlx_dtype = 2;
pub const MLX_UINT32: mlx_dtype = 3;
pub const MLX_FLOAT16: mlx_dtype = 9;
pub const MLX_FLOAT32: mlx_dtype = 10;
pub const MLX_BFLOAT16: mlx_dtype = 12;

pub type mlx_error_handler_func = unsafe extern "C" fn(msg: *const c_char, data: *mut c_void);

extern "C" {
    pub fn pulsar_f020_abi_values(out: *mut i64, capacity: c_int) -> c_int;

    pub fn mlx_set_error_handler(
        handler: Option<mlx_error_handler_func>,
        data: *mut c_void,
        dtor: Option<unsafe extern "C" fn(*mut c_void)>,
    );

    pub fn mlx_version(res: *mut mlx_string) -> c_int;
    pub fn mlx_string_new() -> mlx_string;
    pub fn mlx_string_data(s: mlx_string) -> *const c_char;
    pub fn mlx_string_free(s: mlx_string) -> c_int;

    pub fn mlx_device_new_type(t: mlx_device_type, index: c_int) -> mlx_device;
    pub fn mlx_device_free(dev: mlx_device) -> c_int;
    pub fn mlx_device_get_type(t: *mut mlx_device_type, dev: mlx_device) -> c_int;
    pub fn mlx_get_default_device(dev: *mut mlx_device) -> c_int;
    pub fn mlx_set_default_device(dev: mlx_device) -> c_int;

    pub fn mlx_device_info_new() -> mlx_device_info;
    pub fn mlx_device_info_get(info: *mut mlx_device_info, dev: mlx_device) -> c_int;
    pub fn mlx_device_info_free(info: mlx_device_info) -> c_int;
    pub fn mlx_device_info_has_key(
        exists: *mut bool,
        info: mlx_device_info,
        key: *const c_char,
    ) -> c_int;
    pub fn mlx_device_info_is_string(
        is_string: *mut bool,
        info: mlx_device_info,
        key: *const c_char,
    ) -> c_int;
    pub fn mlx_device_info_get_string(
        value: *mut *const c_char,
        info: mlx_device_info,
        key: *const c_char,
    ) -> c_int;
    pub fn mlx_device_info_get_size(
        value: *mut usize,
        info: mlx_device_info,
        key: *const c_char,
    ) -> c_int;

    pub fn mlx_metal_is_available(res: *mut bool) -> c_int;

    pub fn mlx_stream_new_device(dev: mlx_device) -> mlx_stream;
    pub fn mlx_stream_free(s: mlx_stream) -> c_int;
    pub fn mlx_stream_get_device(dev: *mut mlx_device, s: mlx_stream) -> c_int;
    pub fn mlx_synchronize(s: mlx_stream) -> c_int;

    pub fn mlx_array_new() -> mlx_array;
    pub fn mlx_array_new_data(
        data: *const c_void,
        shape: *const c_int,
        dim: c_int,
        dtype: mlx_dtype,
    ) -> mlx_array;
    pub fn mlx_array_free(arr: mlx_array) -> c_int;
    pub fn mlx_array_eval(arr: mlx_array) -> c_int;
    pub fn mlx_array_dtype(arr: mlx_array) -> mlx_dtype;
    pub fn mlx_array_ndim(arr: mlx_array) -> usize;
    pub fn mlx_array_size(arr: mlx_array) -> usize;
    pub fn mlx_array_nbytes(arr: mlx_array) -> usize;
    pub fn mlx_array_shape(arr: mlx_array) -> *const c_int;
    pub fn mlx_array_data_uint32(arr: mlx_array) -> *const u32;
    pub fn mlx_array_data_float32(arr: mlx_array) -> *const f32;
    // float16_t / bfloat16_t are 2-byte types; read as their bit patterns.
    pub fn mlx_array_data_float16(arr: mlx_array) -> *const u16;
    pub fn mlx_array_data_bfloat16(arr: mlx_array) -> *const u16;

    pub fn mlx_astype(res: *mut mlx_array, a: mlx_array, dtype: mlx_dtype, s: mlx_stream) -> c_int;
    pub fn mlx_dequantize(
        res: *mut mlx_array,
        w: mlx_array,
        scales: mlx_array,
        biases: mlx_array,
        group_size: mlx_optional_int,
        bits: mlx_optional_int,
        mode: *const c_char,
        global_scale: mlx_array,
        dtype: mlx_optional_dtype,
        s: mlx_stream,
    ) -> c_int;
    pub fn mlx_quantized_matmul(
        res: *mut mlx_array,
        x: mlx_array,
        w: mlx_array,
        scales: mlx_array,
        biases: mlx_array,
        transpose: bool,
        group_size: mlx_optional_int,
        bits: mlx_optional_int,
        mode: *const c_char,
        s: mlx_stream,
    ) -> c_int;

    pub fn mlx_get_peak_memory(res: *mut usize) -> c_int;
    pub fn mlx_get_active_memory(res: *mut usize) -> c_int;
    pub fn mlx_reset_peak_memory() -> c_int;
}

/// Rust's view of the values `pulsar_f020_abi_values` reports, in its order.
pub fn expected_abi() -> Vec<i64> {
    use std::mem::{offset_of, size_of};
    vec![
        size_of::<mlx_array>() as i64,
        size_of::<mlx_device>() as i64,
        size_of::<mlx_stream>() as i64,
        size_of::<mlx_string>() as i64,
        size_of::<mlx_device_info>() as i64,
        size_of::<mlx_dtype>() as i64,
        size_of::<mlx_device_type>() as i64,
        MLX_CPU as i64,
        MLX_GPU as i64,
        MLX_UINT16 as i64,
        MLX_UINT32 as i64,
        MLX_FLOAT16 as i64,
        MLX_FLOAT32 as i64,
        MLX_BFLOAT16 as i64,
        size_of::<mlx_optional_int>() as i64,
        offset_of!(mlx_optional_int, has_value) as i64,
        size_of::<mlx_optional_dtype>() as i64,
        offset_of!(mlx_optional_dtype, has_value) as i64,
    ]
}

/// Compare the C-side layout report with the Rust declarations. Calls no
/// MLX-C function.
pub fn verify_abi() -> Result<Vec<i64>, String> {
    let mut buf = [0i64; 64];
    // SAFETY: the C function writes at most `capacity` values into `buf`.
    let n = unsafe { pulsar_f020_abi_values(buf.as_mut_ptr(), buf.len() as c_int) };
    if n <= 0 {
        return Err(format!("abi_check returned {n}"));
    }
    let got = buf[..n as usize].to_vec();
    let want = expected_abi();
    if got != want {
        return Err(format!("ABI mismatch: C {got:?} vs Rust {want:?}"));
    }
    Ok(got)
}

thread_local! {
    static NUMERICAL_CALLS: Cell<u64> = const { Cell::new(0) };
    static IMPORT_CALLS: Cell<u64> = const { Cell::new(0) };
}

/// Count one MLX-C numerical call (astype, dequantize, quantized_matmul,
/// eval, synchronize) and run it.
pub fn numerical<T>(f: impl FnOnce() -> T) -> T {
    NUMERICAL_CALLS.with(|c| c.set(c.get() + 1));
    f()
}

/// Count one MLX-C import (array construction from host data) and run it.
pub fn import<T>(f: impl FnOnce() -> T) -> T {
    IMPORT_CALLS.with(|c| c.set(c.get() + 1));
    f()
}

/// (numerical calls, imports) issued so far on this thread.
pub fn call_counts() -> (u64, u64) {
    (
        NUMERICAL_CALLS.with(Cell::get),
        IMPORT_CALLS.with(Cell::get),
    )
}
