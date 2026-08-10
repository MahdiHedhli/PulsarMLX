use std::ffi::CStr;
use std::marker::PhantomData;
use std::os::raw::c_char;
use std::ptr;

use crate::StableSlab;

#[repr(C)]
struct RawMetalContext {
    _private: [u8; 0],
}

#[repr(C)]
struct RawMetalRegistration {
    _private: [u8; 0],
}

unsafe extern "C" {
    fn pulsar_metal_context_create(
        out_context: *mut *mut RawMetalContext,
        error_buffer: *mut c_char,
        error_capacity: usize,
    ) -> i32;
    fn pulsar_metal_context_destroy(context: *mut RawMetalContext);
    fn pulsar_metal_register_no_copy(
        context: *mut RawMetalContext,
        address: *const u8,
        length: usize,
        out_registration: *mut *mut RawMetalRegistration,
        error_buffer: *mut c_char,
        error_capacity: usize,
    ) -> i32;
    fn pulsar_metal_registration_destroy(registration: *mut RawMetalRegistration);
    fn pulsar_metal_checksum(
        context: *mut RawMetalContext,
        registration: *mut RawMetalRegistration,
        out_checksum: *mut u32,
        error_buffer: *mut c_char,
        error_capacity: usize,
    ) -> i32;
    fn pulsar_metal_registration_address(registration: *mut RawMetalRegistration) -> usize;
}

const ERROR_CAPACITY: usize = 512;

const IQ2_XXS_BLOCK_WEIGHTS: usize = 256;
const IQ2_XXS_BLOCK_BYTES: usize = 66;

/// Validated packed-IQ2_XXS matrix-vector request.
///
/// Construction performs every shape and byte-range check required before a
/// future Metal dispatch. The direct path never allocates a complete decoded
/// f32 weight matrix, so that accounting is fixed at zero.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Iq2XxsGemvSpec {
    rows: usize,
    columns: usize,
    packed_row_bytes: usize,
    packed_matrix_bytes: usize,
}

impl Iq2XxsGemvSpec {
    pub fn new(
        rows: usize,
        columns: usize,
        packed_len: usize,
        activation_len: usize,
    ) -> Result<Self, String> {
        if rows == 0 || columns == 0 {
            return Err("IQ2_XXS rows and columns must be positive".into());
        }
        if columns % IQ2_XXS_BLOCK_WEIGHTS != 0 {
            return Err("IQ2_XXS columns must be divisible by 256".into());
        }
        if activation_len != columns {
            return Err(format!(
                "IQ2_XXS activation length mismatch: {activation_len} != {columns}"
            ));
        }
        let packed_row_bytes = (columns / IQ2_XXS_BLOCK_WEIGHTS)
            .checked_mul(IQ2_XXS_BLOCK_BYTES)
            .ok_or_else(|| "IQ2_XXS packed row size overflow".to_owned())?;
        let packed_matrix_bytes = rows
            .checked_mul(packed_row_bytes)
            .ok_or_else(|| "IQ2_XXS packed matrix size overflow".to_owned())?;
        if packed_len != packed_matrix_bytes {
            return Err(format!(
                "IQ2_XXS packed length mismatch: {packed_len} != {packed_matrix_bytes}"
            ));
        }
        Ok(Self {
            rows,
            columns,
            packed_row_bytes,
            packed_matrix_bytes,
        })
    }

    pub fn rows(self) -> usize {
        self.rows
    }

    pub fn columns(self) -> usize {
        self.columns
    }

    pub fn packed_row_bytes(self) -> usize {
        self.packed_row_bytes
    }

    pub fn packed_matrix_bytes(self) -> usize {
        self.packed_matrix_bytes
    }

    pub fn complete_f32_weight_materialized_bytes(self) -> usize {
        0
    }
}

#[derive(Debug, Clone, Copy, Default, PartialEq)]
pub struct Iq2XxsGemvTelemetry {
    pub registration_seconds: f64,
    pub compilation_seconds: f64,
    pub dispatch_seconds: f64,
    pub kernel_seconds: Option<f64>,
    pub synchronization_seconds: f64,
    pub total_seconds: f64,
    pub cpu_fallback_count: u64,
    pub complete_f32_weight_materialized_bytes: u64,
}

fn bridge_error(status: i32, buffer: &[i8; ERROR_CAPACITY]) -> String {
    let message = unsafe { CStr::from_ptr(buffer.as_ptr()) };
    format!(
        "Metal bridge status {status}: {}",
        message.to_string_lossy()
    )
}

pub struct MetalBridge {
    raw: *mut RawMetalContext,
}

pub struct MetalRegistration<'a> {
    raw: *mut RawMetalRegistration,
    _lifetime: PhantomData<(&'a MetalBridge, &'a StableSlab)>,
}

impl MetalBridge {
    pub fn new() -> Result<Self, String> {
        let mut raw = ptr::null_mut();
        let mut error = [0_i8; ERROR_CAPACITY];
        let status =
            unsafe { pulsar_metal_context_create(&mut raw, error.as_mut_ptr(), ERROR_CAPACITY) };
        if status != 0 || raw.is_null() {
            return Err(bridge_error(status, &error));
        }
        Ok(Self { raw })
    }

    pub fn register<'a>(&'a self, slab: &'a StableSlab) -> Result<MetalRegistration<'a>, String> {
        let mut raw = ptr::null_mut();
        let mut error = [0_i8; ERROR_CAPACITY];
        let status = unsafe {
            pulsar_metal_register_no_copy(
                self.raw,
                slab.as_ptr(),
                slab.len(),
                &mut raw,
                error.as_mut_ptr(),
                ERROR_CAPACITY,
            )
        };
        if status != 0 || raw.is_null() {
            return Err(bridge_error(status, &error));
        }
        Ok(MetalRegistration {
            raw,
            _lifetime: PhantomData,
        })
    }

    pub fn checksum(&self, registration: &MetalRegistration<'_>) -> Result<u32, String> {
        let mut checksum = 0_u32;
        let mut error = [0_i8; ERROR_CAPACITY];
        let status = unsafe {
            pulsar_metal_checksum(
                self.raw,
                registration.raw,
                &mut checksum,
                error.as_mut_ptr(),
                ERROR_CAPACITY,
            )
        };
        if status != 0 {
            return Err(bridge_error(status, &error));
        }
        Ok(checksum)
    }

    pub fn registered_address(registration: &MetalRegistration<'_>) -> usize {
        unsafe { pulsar_metal_registration_address(registration.raw) }
    }
}

impl Drop for MetalBridge {
    fn drop(&mut self) {
        if !self.raw.is_null() {
            unsafe { pulsar_metal_context_destroy(self.raw) };
        }
    }
}

impl Drop for MetalRegistration<'_> {
    fn drop(&mut self) {
        if !self.raw.is_null() {
            unsafe { pulsar_metal_registration_destroy(self.raw) };
        }
    }
}
