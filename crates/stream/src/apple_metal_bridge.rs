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

fn bridge_error(status: i32, buffer: &[i8; ERROR_CAPACITY]) -> String {
    let message = unsafe { CStr::from_ptr(buffer.as_ptr()) };
    format!("Metal bridge status {status}: {}", message.to_string_lossy())
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
        let status = unsafe {
            pulsar_metal_context_create(&mut raw, error.as_mut_ptr(), ERROR_CAPACITY)
        };
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
