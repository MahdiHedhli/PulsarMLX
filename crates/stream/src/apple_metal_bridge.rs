use std::ffi::CStr;
use std::marker::PhantomData;
use std::os::raw::c_char;
use std::ptr;
use std::time::Instant;

use crate::{
    iq2_xxs_grid_bytes, iq2_xxs_sign_bytes, Iq2XxsGemvSpec, StableSlab, IQ2_XXS_GRID_BYTES,
    IQ2_XXS_SIGN_BYTES,
};

#[repr(C)]
struct RawMetalContext {
    _private: [u8; 0],
}

#[repr(C)]
struct RawMetalRegistration {
    _private: [u8; 0],
}

#[repr(C)]
#[derive(Debug, Clone, Copy, Default)]
struct RawIq2XxsGemvTelemetry {
    dispatch_seconds: f64,
    kernel_seconds: f64,
    synchronization_seconds: f64,
    total_seconds: f64,
}

unsafe extern "C" {
    fn pulsar_metal_context_create(
        out_context: *mut *mut RawMetalContext,
        error_buffer: *mut c_char,
        error_capacity: usize,
    ) -> i32;
    fn pulsar_metal_context_destroy(context: *mut RawMetalContext);
    fn pulsar_metal_context_configure_iq2_xxs(
        context: *mut RawMetalContext,
        grid: *const u8,
        grid_length: usize,
        signs: *const u8,
        signs_length: usize,
        error_buffer: *mut c_char,
        error_capacity: usize,
    ) -> i32;
    fn pulsar_metal_context_compilation_seconds(context: *mut RawMetalContext) -> f64;
    fn pulsar_metal_context_device_name(
        context: *mut RawMetalContext,
        output: *mut c_char,
        output_capacity: usize,
    ) -> i32;
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
    fn pulsar_metal_iq2_xxs_gemv(
        context: *mut RawMetalContext,
        registration: *mut RawMetalRegistration,
        rows: u32,
        columns: u32,
        packed_row_bytes: u32,
        activation: *const f32,
        activation_len: usize,
        output: *mut f32,
        output_len: usize,
        out_telemetry: *mut RawIq2XxsGemvTelemetry,
        error_buffer: *mut c_char,
        error_capacity: usize,
    ) -> i32;
    fn pulsar_metal_registration_address(registration: *mut RawMetalRegistration) -> usize;
}

const ERROR_CAPACITY: usize = 512;

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

#[derive(Debug, Clone, PartialEq)]
pub struct Iq2XxsGemvResult {
    pub output: Vec<f32>,
    pub telemetry: Iq2XxsGemvTelemetry,
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
    length: usize,
    registration_seconds: f64,
    _lifetime: PhantomData<(&'a MetalBridge, &'a StableSlab)>,
}

impl MetalRegistration<'_> {
    pub fn registration_seconds(&self) -> f64 {
        self.registration_seconds
    }
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
        let grid = iq2_xxs_grid_bytes();
        let signs = iq2_xxs_sign_bytes();
        debug_assert_eq!(grid.len(), IQ2_XXS_GRID_BYTES);
        debug_assert_eq!(signs.len(), IQ2_XXS_SIGN_BYTES);
        let status = unsafe {
            pulsar_metal_context_configure_iq2_xxs(
                raw,
                grid.as_ptr(),
                grid.len(),
                signs.as_ptr(),
                signs.len(),
                error.as_mut_ptr(),
                ERROR_CAPACITY,
            )
        };
        if status != 0 {
            unsafe { pulsar_metal_context_destroy(raw) };
            return Err(bridge_error(status, &error));
        }
        Ok(Self { raw })
    }

    pub fn device_name(&self) -> Result<String, String> {
        let mut output = [0_i8; ERROR_CAPACITY];
        let status = unsafe {
            pulsar_metal_context_device_name(self.raw, output.as_mut_ptr(), output.len())
        };
        if status != 0 {
            return Err("Metal device name unavailable".into());
        }
        Ok(unsafe { CStr::from_ptr(output.as_ptr()) }
            .to_string_lossy()
            .into_owned())
    }

    pub fn compilation_seconds(&self) -> f64 {
        unsafe { pulsar_metal_context_compilation_seconds(self.raw) }
    }

    pub fn register<'a>(&'a self, slab: &'a StableSlab) -> Result<MetalRegistration<'a>, String> {
        let mut raw = ptr::null_mut();
        let mut error = [0_i8; ERROR_CAPACITY];
        let started = Instant::now();
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
        let registration_seconds = started.elapsed().as_secs_f64();
        if status != 0 || raw.is_null() {
            return Err(bridge_error(status, &error));
        }
        Ok(MetalRegistration {
            raw,
            length: slab.len(),
            registration_seconds,
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

    pub fn iq2_xxs_gemv(
        &self,
        registration: &MetalRegistration<'_>,
        spec: Iq2XxsGemvSpec,
        activation: &[f32],
    ) -> Result<Iq2XxsGemvResult, String> {
        if registration.length != spec.packed_matrix_bytes() {
            return Err("Metal registration length does not match IQ2_XXS request".into());
        }
        if activation.len() != spec.columns() || !activation.iter().all(|value| value.is_finite()) {
            return Err("IQ2_XXS activation must have exact finite values".into());
        }
        let rows =
            u32::try_from(spec.rows()).map_err(|_| "IQ2_XXS rows exceed Metal ABI".to_owned())?;
        let columns = u32::try_from(spec.columns())
            .map_err(|_| "IQ2_XXS columns exceed Metal ABI".to_owned())?;
        let packed_row_bytes = u32::try_from(spec.packed_row_bytes())
            .map_err(|_| "IQ2_XXS row bytes exceed Metal ABI".to_owned())?;
        let mut output = vec![0.0_f32; spec.rows()];
        let mut raw_telemetry = RawIq2XxsGemvTelemetry::default();
        let mut error = [0_i8; ERROR_CAPACITY];
        let status = unsafe {
            pulsar_metal_iq2_xxs_gemv(
                self.raw,
                registration.raw,
                rows,
                columns,
                packed_row_bytes,
                activation.as_ptr(),
                activation.len(),
                output.as_mut_ptr(),
                output.len(),
                &mut raw_telemetry,
                error.as_mut_ptr(),
                ERROR_CAPACITY,
            )
        };
        if status != 0 {
            return Err(bridge_error(status, &error));
        }
        if !output.iter().all(|value| value.is_finite()) {
            return Err("Metal IQ2_XXS output contains non-finite values".into());
        }
        Ok(Iq2XxsGemvResult {
            output,
            telemetry: Iq2XxsGemvTelemetry {
                registration_seconds: registration.registration_seconds,
                compilation_seconds: self.compilation_seconds(),
                dispatch_seconds: raw_telemetry.dispatch_seconds,
                kernel_seconds: (raw_telemetry.kernel_seconds >= 0.0)
                    .then_some(raw_telemetry.kernel_seconds),
                synchronization_seconds: raw_telemetry.synchronization_seconds,
                total_seconds: raw_telemetry.total_seconds,
                cpu_fallback_count: 0,
                complete_f32_weight_materialized_bytes: 0,
            },
        })
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
