//! Ownership, error handling and evaluation over MLX-C (contract `ownership`,
//! `error_handling`, execution evidence E1/E2).
//!
//! * `NativeContext` owns one `mlx_device` and one `mlx_stream`; Drop
//!   synchronizes and frees both. `NativeArray<'ctx>` owns one `mlx_array`,
//!   borrows its context (L-OUTLIVE), frees its handle exactly once in Drop
//!   (L-ONCE), and has no Clone, no public raw accessor and no into_raw.
//!   Imports copy (L-NOALIAS). Nothing here is Send or Sync (L-THREAD).
//! * The MLX-C error handler is installed exactly once per process through a
//!   `std::sync::Once`, before the first context, with null data and a null
//!   dtor. It copies the message into a thread-local slot and returns.
//! * `Evaluated<'ctx>` is the only type that exposes element bytes, and the
//!   only way to obtain one is `NativeArray::evaluate`, which requires
//!   `mlx_array_eval == 0` and then `mlx_synchronize(stream) == 0` (E2).
//!   MLX-C itself does not prevent reading unevaluated data.

use std::cell::{Cell, RefCell};
use std::ffi::{CStr, CString};
use std::marker::PhantomData;
use std::os::raw::{c_char, c_int, c_void};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Once;

use mlx_native_affine::dtype::Dtype;
use mlx_native_affine::refusal::DeviceFacts;

use crate::ffi;

// ------------------------------------------------------------------ errors --

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum NativeError {
    /// An MLX-C call returned a nonzero status; message from the handler.
    Status {
        call: &'static str,
        status: i32,
        message: Option<String>,
    },
    /// A constructor returned an empty handle or left an error in the slot.
    EmptyHandle {
        call: &'static str,
        message: Option<String>,
    },
    /// An accessor left an error in the slot or returned null.
    Accessor {
        call: &'static str,
        message: Option<String>,
    },
    /// A readback found a dtype or shape the typestate did not expect.
    Unexpected(String),
}

impl std::fmt::Display for NativeError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{self:?}")
    }
}

thread_local! {
    static LAST_ERROR: RefCell<Option<String>> = const { RefCell::new(None) };
    static HANDLER_MESSAGES: Cell<u64> = const { Cell::new(0) };
}

/// The process-wide MLX-C error handler: copy the message into the
/// thread-local slot and return. Never exits, never unwinds.
unsafe extern "C" fn record_error(msg: *const c_char, _data: *mut c_void) {
    let text = if msg.is_null() {
        String::from("<null message>")
    } else {
        // SAFETY: MLX-C passes a NUL-terminated buffer valid for this call.
        unsafe { CStr::from_ptr(msg) }
            .to_string_lossy()
            .into_owned()
    };
    let _ = LAST_ERROR.try_with(|slot| {
        if let Ok(mut s) = slot.try_borrow_mut() {
            *s = Some(text);
        }
    });
    let _ = HANDLER_MESSAGES.try_with(|c| c.set(c.get() + 1));
}

static HANDLER_ONCE: Once = Once::new();
static HANDLER_INSTALLS: AtomicU64 = AtomicU64::new(0);

/// Install the handler (idempotent; the Once guarantees a single call).
pub fn ensure_error_handler() {
    HANDLER_ONCE.call_once(|| {
        // SAFETY: a valid `extern "C"` function, null data and a null dtor
        // (contract error_handling.handler).
        unsafe { ffi::mlx_set_error_handler(Some(record_error), std::ptr::null_mut(), None) };
        HANDLER_INSTALLS.fetch_add(1, Ordering::SeqCst);
    });
}

pub fn handler_installs() -> u64 {
    HANDLER_INSTALLS.load(Ordering::SeqCst)
}

pub fn handler_messages() -> u64 {
    HANDLER_MESSAGES.with(Cell::get)
}

fn take_error() -> Option<String> {
    LAST_ERROR.with(|s| s.borrow_mut().take())
}

fn status(call: &'static str, status: c_int) -> Result<(), NativeError> {
    // Always drain the slot so a stale message never reaches a later call.
    let message = take_error();
    if status == 0 && message.is_none() {
        Ok(())
    } else {
        Err(NativeError::Status {
            call,
            status,
            message,
        })
    }
}

fn after_accessor(call: &'static str) -> Result<(), NativeError> {
    match take_error() {
        None => Ok(()),
        Some(m) => Err(NativeError::Accessor {
            call,
            message: Some(m),
        }),
    }
}

// ---------------------------------------------------------- handle census --

static LIVE_HANDLES: AtomicU64 = AtomicU64::new(0);
static FREED_HANDLES: AtomicU64 = AtomicU64::new(0);
static DOUBLE_FREE_ATTEMPTS: AtomicU64 = AtomicU64::new(0);

/// (live array handles, arrays freed so far) across the process.
pub fn handle_census() -> (u64, u64) {
    (
        LIVE_HANDLES.load(Ordering::SeqCst),
        FREED_HANDLES.load(Ordering::SeqCst),
    )
}

pub fn double_free_attempts() -> u64 {
    DOUBLE_FREE_ATTEMPTS.load(Ordering::SeqCst)
}

// ------------------------------------------------------ cleanup accounting --
//
// Every MLX-C status returned during cleanup (frees, the context's final
// synchronize) is checked. A failure is never cleared: it is preserved here
// and written into the child report, and the parent fails qualification on
// any preserved cleanup error. A handle whose free failed stays counted as
// live; the freed counter moves only on a successful free.

/// One preserved cleanup failure.
#[derive(Clone, Debug)]
pub struct CleanupError {
    pub call: &'static str,
    pub status: i32,
    pub message: Option<String>,
}

thread_local! {
    static CLEANUP_ERRORS: RefCell<Vec<CleanupError>> = const { RefCell::new(Vec::new()) };
}

/// Test-only fault injection (reachable only through `--test-fault`): make
/// the n-th array free report failure (0 = never), or make the next context
/// teardown's synchronize report failure.
static INJECT_FREE_FAILURE_AT: AtomicU64 = AtomicU64::new(0);
static INJECT_TEARDOWN_SYNC_FAILURE: AtomicBool = AtomicBool::new(false);
static ARRAY_FREE_CALLS: AtomicU64 = AtomicU64::new(0);

pub fn inject_free_failure_at(n: u64) {
    INJECT_FREE_FAILURE_AT.store(n, Ordering::SeqCst);
}

pub fn inject_teardown_sync_failure() {
    INJECT_TEARDOWN_SYNC_FAILURE.store(true, Ordering::SeqCst);
}

fn record_cleanup(call: &'static str, status: i32, message: Option<String>) {
    CLEANUP_ERRORS.with(|v| {
        v.borrow_mut().push(CleanupError {
            call,
            status,
            message,
        })
    });
}

/// Check a cleanup call's status; a failure (nonzero status or a handler
/// message) is preserved, never discarded. Returns whether it succeeded.
fn cleanup_status(call: &'static str, st: c_int) -> bool {
    let message = take_error();
    if st == 0 && message.is_none() {
        true
    } else {
        record_cleanup(call, st, message);
        false
    }
}

/// Preserved cleanup failures so far (in order).
pub fn cleanup_errors() -> Vec<CleanupError> {
    CLEANUP_ERRORS.with(|v| v.borrow().clone())
}

/// Record any message still in the error slot as a cleanup failure (called
/// after teardown, before the report is written).
pub fn drain_residual_error(label: &'static str) {
    if let Some(m) = take_error() {
        record_cleanup(label, 0, Some(m));
    }
}

/// Every mlx_array_free goes through here.
fn free_array(raw: ffi::mlx_array, call: &'static str) -> bool {
    let n = ARRAY_FREE_CALLS.fetch_add(1, Ordering::SeqCst) + 1;
    if INJECT_FREE_FAILURE_AT.load(Ordering::SeqCst) == n {
        // Simulated failed free: the handle is left allocated, as a real
        // failure would leave it, and the failure is preserved.
        record_cleanup(
            call,
            1,
            Some("injected cleanup failure (test fault cleanup-free)".into()),
        );
        return false;
    }
    // SAFETY: callers pass a handle they own and free it exactly once.
    let st = unsafe { ffi::mlx_array_free(raw) };
    cleanup_status(call, st)
}

fn free_device(dev: ffi::mlx_device, call: &'static str) -> bool {
    // SAFETY: callers pass a device handle they own, freed once.
    cleanup_status(call, unsafe { ffi::mlx_device_free(dev) })
}

// Result-handle census (L-ERRFREE): every out-handle an operation creates
// with mlx_array_new is either adopted into a NativeArray or, on the error
// path, freed -- counted here independently of adoption.
static RESULT_HANDLES_CREATED: AtomicU64 = AtomicU64::new(0);
static RESULT_HANDLES_ADOPTED: AtomicU64 = AtomicU64::new(0);
static ERROR_RESULT_FREES: AtomicU64 = AtomicU64::new(0);

/// (result handles created, adopted, freed on an error path).
pub fn result_census() -> (u64, u64, u64) {
    (
        RESULT_HANDLES_CREATED.load(Ordering::SeqCst),
        RESULT_HANDLES_ADOPTED.load(Ordering::SeqCst),
        ERROR_RESULT_FREES.load(Ordering::SeqCst),
    )
}

pub fn array_free_calls() -> u64 {
    ARRAY_FREE_CALLS.load(Ordering::SeqCst)
}

fn new_result() -> ffi::mlx_array {
    RESULT_HANDLES_CREATED.fetch_add(1, Ordering::SeqCst);
    // SAFETY: returns an empty handle (no allocation, cannot fail).
    unsafe { ffi::mlx_array_new() }
}

// ------------------------------------------------------------------ device --

/// Which device a context owns.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DeviceKind {
    Gpu,
    /// Only for the E6 negative control: every bridge op refuses it.
    Cpu,
}

fn device_type_of(dev: ffi::mlx_device) -> Result<ffi::mlx_device_type, NativeError> {
    let mut t: ffi::mlx_device_type = -1;
    // SAFETY: `dev` is a non-empty handle owned by the caller.
    status("mlx_device_get_type", unsafe {
        ffi::mlx_device_get_type(&mut t, dev)
    })?;
    Ok(t)
}

/// Query the default device's type (the out-handle is freed here).
pub fn default_device_type() -> Result<ffi::mlx_device_type, NativeError> {
    let mut dev = ffi::mlx_device {
        ctx: std::ptr::null_mut(),
    };
    // SAFETY: MLX-C allocates into an empty out-handle; freed below.
    let s = unsafe { ffi::mlx_get_default_device(&mut dev) };
    let r = status("mlx_get_default_device", s).and_then(|_| device_type_of(dev));
    if !dev.ctx.is_null() {
        // Allocated by MLX-C above, freed once.
        free_device(dev, "mlx_device_free (default device query)");
    }
    r
}

/// Set the process default device to the GPU (plan §8.1 step 3).
pub fn set_default_device_gpu() -> Result<(), NativeError> {
    ensure_error_handler();
    // SAFETY: constructor without status; checked below.
    let dev = unsafe { ffi::mlx_device_new_type(ffi::MLX_GPU, 0) };
    let msg = take_error();
    if dev.ctx.is_null() || msg.is_some() {
        if !dev.ctx.is_null() {
            free_device(dev, "mlx_device_free (set default device, error path)");
        }
        return Err(NativeError::EmptyHandle {
            call: "mlx_device_new_type",
            message: msg,
        });
    }
    // SAFETY: `dev` is non-empty; freed once after use.
    let r = status("mlx_set_default_device", unsafe {
        ffi::mlx_set_default_device(dev)
    });
    free_device(dev, "mlx_device_free (set default device)");
    r
}

pub fn metal_available() -> Result<bool, NativeError> {
    let mut b = false;
    // SAFETY: plain out-parameter.
    status("mlx_metal_is_available", unsafe {
        ffi::mlx_metal_is_available(&mut b)
    })?;
    Ok(b)
}

/// One owned device + stream.
pub struct NativeContext {
    device: ffi::mlx_device,
    stream: ffi::mlx_stream,
    live_arrays: Cell<i64>,
    _not_send_sync: PhantomData<*const ()>,
}

impl NativeContext {
    pub fn new(kind: DeviceKind) -> Result<NativeContext, NativeError> {
        ensure_error_handler();
        let t = match kind {
            DeviceKind::Gpu => ffi::MLX_GPU,
            DeviceKind::Cpu => ffi::MLX_CPU,
        };
        // SAFETY: constructor without status; empty handle and slot checked.
        let device = unsafe { ffi::mlx_device_new_type(t, 0) };
        let msg = take_error();
        if device.ctx.is_null() || msg.is_some() {
            if !device.ctx.is_null() {
                free_device(device, "mlx_device_free (context construction, error path)");
            }
            return Err(NativeError::EmptyHandle {
                call: "mlx_device_new_type",
                message: msg,
            });
        }
        // SAFETY: `device` is non-empty.
        let stream = unsafe { ffi::mlx_stream_new_device(device) };
        let msg = take_error();
        if stream.ctx.is_null() || msg.is_some() {
            // L-ERRFREE: free what was created.
            if !stream.ctx.is_null() {
                cleanup_status(
                    "mlx_stream_free (context construction, error path)",
                    unsafe { ffi::mlx_stream_free(stream) },
                );
            }
            free_device(device, "mlx_device_free (context construction, error path)");
            return Err(NativeError::EmptyHandle {
                call: "mlx_stream_new_device",
                message: msg,
            });
        }
        Ok(NativeContext {
            device,
            stream,
            live_arrays: Cell::new(0),
            _not_send_sync: PhantomData,
        })
    }

    pub fn live_arrays(&self) -> i64 {
        self.live_arrays.get()
    }

    /// R-DEVICE inputs, queried fresh (E1: asserted before every op).
    pub fn device_facts(&self) -> Result<DeviceFacts, NativeError> {
        let context_type = device_type_of(self.device)?;
        let mut sdev = ffi::mlx_device {
            ctx: std::ptr::null_mut(),
        };
        // SAFETY: `self.stream` is owned and non-empty; the out-handle is freed.
        let s = unsafe { ffi::mlx_stream_get_device(&mut sdev, self.stream) };
        let stream_type = status("mlx_stream_get_device", s).and_then(|_| device_type_of(sdev));
        if !sdev.ctx.is_null() {
            free_device(sdev, "mlx_device_free (stream device query)");
        }
        let stream_type = stream_type?;
        Ok(DeviceFacts {
            context_device_gpu: context_type == ffi::MLX_GPU,
            metal_available: metal_available()?,
            stream_device_gpu: stream_type == ffi::MLX_GPU,
            default_device_gpu: default_device_type()? == ffi::MLX_GPU,
        })
    }

    pub fn synchronize(&self) -> Result<(), NativeError> {
        // SAFETY: owned, non-empty stream.
        ffi::numerical(|| {
            status("mlx_synchronize", unsafe {
                ffi::mlx_synchronize(self.stream)
            })
        })
    }

    fn adopt(&self, raw: ffi::mlx_array) -> NativeArray<'_> {
        self.live_arrays.set(self.live_arrays.get() + 1);
        LIVE_HANDLES.fetch_add(1, Ordering::SeqCst);
        NativeArray {
            raw,
            ctx: self,
            freed: Cell::new(false),
            _not_send_sync: PhantomData,
        }
    }

    /// Copying import (`mlx_array_new_data`) of host bytes as `dtype`.
    pub fn import(
        &self,
        dtype: Dtype,
        shape: &[usize],
        bytes: &[u8],
    ) -> Result<NativeArray<'_>, NativeError> {
        let count: usize = shape.iter().product();
        if count * dtype.size() != bytes.len() {
            return Err(NativeError::Unexpected(format!(
                "import: {} bytes for shape {shape:?}",
                bytes.len()
            )));
        }
        let dims: Vec<c_int> = shape.iter().map(|&d| d as c_int).collect();
        let t = mlx_dtype(dtype);
        // SAFETY: `bytes` is valid for the declared element count; MLX copies
        // it (array.h:588-629) so no alias outlives this call.
        let raw = ffi::import(|| unsafe {
            ffi::mlx_array_new_data(
                bytes.as_ptr() as *const c_void,
                dims.as_ptr(),
                dims.len() as c_int,
                t,
            )
        });
        let msg = take_error();
        if raw.ctx.is_null() || msg.is_some() {
            if !raw.ctx.is_null() {
                free_array(raw, "mlx_array_free (import, error path)");
            }
            return Err(NativeError::EmptyHandle {
                call: "mlx_array_new_data",
                message: msg,
            });
        }
        Ok(self.adopt(raw))
    }

    /// `mlx_astype(a, float32)` on this context's stream.
    pub fn astype_f32(&self, a: &NativeArray<'_>) -> Result<NativeArray<'_>, NativeError> {
        let mut res = new_result();
        // SAFETY: `a.raw` is owned by a live NativeArray; `res` is an empty
        // out-handle that is either adopted or freed.
        let s = ffi::numerical(|| unsafe {
            ffi::mlx_astype(&mut res, a.raw, ffi::MLX_FLOAT32, self.stream)
        });
        self.finish("mlx_astype", s, res)
    }

    /// `mlx_dequantize` (affine, no global scale, output dtype defaulted to
    /// the metadata dtype) on this context's stream.
    pub fn dequantize(
        &self,
        w: &NativeArray<'_>,
        s: &NativeArray<'_>,
        b: &NativeArray<'_>,
        group_size: u32,
        bits: u32,
    ) -> Result<NativeArray<'_>, NativeError> {
        let mode = CString::new("affine").unwrap();
        let mut res = new_result();
        let empty = ffi::mlx_array {
            ctx: std::ptr::null_mut(),
        };
        let st = ffi::numerical(|| unsafe {
            ffi::mlx_dequantize(
                &mut res,
                w.raw,
                s.raw,
                b.raw,
                ffi::mlx_optional_int {
                    value: group_size as c_int,
                    has_value: true,
                },
                ffi::mlx_optional_int {
                    value: bits as c_int,
                    has_value: true,
                },
                mode.as_ptr(),
                empty,
                ffi::mlx_optional_dtype {
                    value: 0,
                    has_value: false,
                },
                self.stream,
            )
        });
        self.finish("mlx_dequantize", st, res)
    }

    /// `mlx_quantized_matmul` on this context's stream. The bridge only ever
    /// passes `transpose = true` for admitted requests.
    #[allow(clippy::too_many_arguments)]
    pub fn quantized_matmul(
        &self,
        x: &NativeArray<'_>,
        w: &NativeArray<'_>,
        s: &NativeArray<'_>,
        b: &NativeArray<'_>,
        transpose: bool,
        group_size: u32,
        bits: u32,
    ) -> Result<NativeArray<'_>, NativeError> {
        let mode = CString::new("affine").unwrap();
        let mut res = new_result();
        let st = ffi::numerical(|| unsafe {
            ffi::mlx_quantized_matmul(
                &mut res,
                x.raw,
                w.raw,
                s.raw,
                b.raw,
                transpose,
                ffi::mlx_optional_int {
                    value: group_size as c_int,
                    has_value: true,
                },
                ffi::mlx_optional_int {
                    value: bits as c_int,
                    has_value: true,
                },
                mode.as_ptr(),
                self.stream,
            )
        });
        self.finish("mlx_quantized_matmul", st, res)
    }

    fn finish(
        &self,
        call: &'static str,
        st: c_int,
        res: ffi::mlx_array,
    ) -> Result<NativeArray<'_>, NativeError> {
        match status(call, st) {
            Ok(()) if !res.ctx.is_null() => {
                RESULT_HANDLES_ADOPTED.fetch_add(1, Ordering::SeqCst);
                Ok(self.adopt(res))
            }
            other => {
                // L-ERRFREE: the result handle is freed on every error path
                // (an empty-handle free is a no-op) and the free is counted
                // independently of adoption.
                if free_array(res, "mlx_array_free (operation result, error path)") {
                    ERROR_RESULT_FREES.fetch_add(1, Ordering::SeqCst);
                }
                Err(other.err().unwrap_or(NativeError::EmptyHandle {
                    call,
                    message: None,
                }))
            }
        }
    }
}

impl Drop for NativeContext {
    fn drop(&mut self) {
        // Arrays borrow the context, so none can be alive here unless a free
        // failed (L-OUTLIVE); either way it is preserved, not asserted away.
        let live = self.live_arrays.get();
        if live != 0 {
            record_cleanup(
                "NativeContext::drop (live arrays at context drop)",
                -1,
                Some(format!("{live} array handle(s) still live")),
            );
        }
        // SAFETY: owned, non-empty stream and device, each freed once.
        let st = ffi::numerical(|| unsafe { ffi::mlx_synchronize(self.stream) });
        if INJECT_TEARDOWN_SYNC_FAILURE.swap(false, Ordering::SeqCst) {
            let _ = cleanup_status("mlx_synchronize (context teardown)", st);
            record_cleanup(
                "mlx_synchronize (context teardown)",
                1,
                Some("injected cleanup failure (test fault cleanup-sync)".into()),
            );
        } else {
            cleanup_status("mlx_synchronize (context teardown)", st);
        }
        cleanup_status("mlx_stream_free (context teardown)", unsafe {
            ffi::mlx_stream_free(self.stream)
        });
        free_device(self.device, "mlx_device_free (context teardown)");
    }
}

fn mlx_dtype(d: Dtype) -> ffi::mlx_dtype {
    match d {
        Dtype::U32 => ffi::MLX_UINT32,
        Dtype::F16 => ffi::MLX_FLOAT16,
        Dtype::BF16 => ffi::MLX_BFLOAT16,
        Dtype::F32 => ffi::MLX_FLOAT32,
    }
}

fn from_mlx_dtype(t: ffi::mlx_dtype) -> Option<Dtype> {
    match t {
        ffi::MLX_UINT32 => Some(Dtype::U32),
        ffi::MLX_FLOAT16 => Some(Dtype::F16),
        ffi::MLX_BFLOAT16 => Some(Dtype::BF16),
        ffi::MLX_FLOAT32 => Some(Dtype::F32),
        _ => None,
    }
}

// ------------------------------------------------------------------- array --

/// One owned MLX array. No Clone, no public raw accessor, no into_raw.
pub struct NativeArray<'ctx> {
    raw: ffi::mlx_array,
    ctx: &'ctx NativeContext,
    freed: Cell<bool>,
    _not_send_sync: PhantomData<*const ()>,
}

impl<'ctx> NativeArray<'ctx> {
    /// E2: eval, then synchronize, then (only via the returned typestate)
    /// host copy.
    pub fn evaluate(self) -> Result<Evaluated<'ctx>, NativeError> {
        // SAFETY: owned, non-empty handle.
        ffi::numerical(|| status("mlx_array_eval", unsafe { ffi::mlx_array_eval(self.raw) }))?;
        self.ctx.synchronize()?;
        Ok(Evaluated { array: self })
    }

    fn free_once(&self) {
        if self.freed.replace(true) {
            DOUBLE_FREE_ATTEMPTS.fetch_add(1, Ordering::SeqCst);
            return;
        }
        // Freed at most once (guarded by `freed`). Only a successful free
        // moves the live and freed counters; a failure is preserved by
        // free_array and the handle stays counted as live.
        if free_array(self.raw, "mlx_array_free (NativeArray drop)") {
            self.ctx.live_arrays.set(self.ctx.live_arrays.get() - 1);
            LIVE_HANDLES.fetch_sub(1, Ordering::SeqCst);
            FREED_HANDLES.fetch_add(1, Ordering::SeqCst);
        }
    }
}

impl Drop for NativeArray<'_> {
    fn drop(&mut self) {
        self.free_once();
    }
}

/// An evaluated, synchronized array. The only source of element bytes.
pub struct Evaluated<'ctx> {
    array: NativeArray<'ctx>,
}

/// A host copy of an evaluated array.
#[derive(Clone, Debug)]
pub struct HostCopy {
    pub dtype: Dtype,
    pub shape: Vec<usize>,
    pub bytes: Vec<u8>,
}

impl Evaluated<'_> {
    pub fn host_copy(&self) -> Result<HostCopy, NativeError> {
        let raw = self.array.raw;
        // Accessors without status are called only on this proven non-empty,
        // evaluated handle; the error slot is checked after each.
        let t = unsafe { ffi::mlx_array_dtype(raw) };
        after_accessor("mlx_array_dtype")?;
        let dtype =
            from_mlx_dtype(t).ok_or_else(|| NativeError::Unexpected(format!("dtype {t}")))?;
        let ndim = unsafe { ffi::mlx_array_ndim(raw) };
        after_accessor("mlx_array_ndim")?;
        let size = unsafe { ffi::mlx_array_size(raw) };
        after_accessor("mlx_array_size")?;
        let shape = if ndim == 0 {
            Vec::new()
        } else {
            let p = unsafe { ffi::mlx_array_shape(raw) };
            after_accessor("mlx_array_shape")?;
            if p.is_null() {
                return Err(NativeError::Accessor {
                    call: "mlx_array_shape",
                    message: None,
                });
            }
            // SAFETY: MLX-C returns `ndim` ints valid while the array lives.
            unsafe { std::slice::from_raw_parts(p, ndim) }
                .iter()
                .map(|&d| d as usize)
                .collect::<Vec<_>>()
        };
        if shape.iter().product::<usize>() != size {
            return Err(NativeError::Unexpected(format!(
                "shape {shape:?} vs size {size}"
            )));
        }
        let nbytes = size * dtype.size();
        let ptr: *const u8 = unsafe {
            match dtype {
                Dtype::U32 => ffi::mlx_array_data_uint32(raw) as *const u8,
                Dtype::F32 => ffi::mlx_array_data_float32(raw) as *const u8,
                Dtype::F16 => ffi::mlx_array_data_float16(raw) as *const u8,
                Dtype::BF16 => ffi::mlx_array_data_bfloat16(raw) as *const u8,
            }
        };
        after_accessor("mlx_array_data_*")?;
        if ptr.is_null() && nbytes > 0 {
            return Err(NativeError::Accessor {
                call: "mlx_array_data_*",
                message: None,
            });
        }
        // SAFETY: the array is evaluated and synchronized; its row-contiguous
        // buffer holds `size` elements of `dtype` and outlives this copy.
        let bytes = if nbytes == 0 {
            Vec::new()
        } else {
            unsafe { std::slice::from_raw_parts(ptr, nbytes) }.to_vec()
        };
        Ok(HostCopy {
            dtype,
            shape,
            bytes,
        })
    }

    pub fn nbytes(&self) -> usize {
        unsafe { ffi::mlx_array_nbytes(self.array.raw) }
    }
}

// ---------------------------------------------------------------- misc info --

pub fn mlx_version() -> Result<String, NativeError> {
    let mut s = unsafe { ffi::mlx_string_new() };
    let st = unsafe { ffi::mlx_version(&mut s) };
    let r = status("mlx_version", st).and_then(|_| {
        let p = unsafe { ffi::mlx_string_data(s) };
        after_accessor("mlx_string_data")?;
        if p.is_null() {
            return Err(NativeError::Accessor {
                call: "mlx_string_data",
                message: None,
            });
        }
        Ok(unsafe { CStr::from_ptr(p) }.to_string_lossy().into_owned())
    });
    cleanup_status("mlx_string_free (version)", unsafe {
        ffi::mlx_string_free(s)
    });
    r
}

/// GPU device_info string and size entries (device_info.cpp:20-48).
pub fn gpu_device_info() -> Result<Vec<(String, String)>, NativeError> {
    let dev = unsafe { ffi::mlx_device_new_type(ffi::MLX_GPU, 0) };
    let msg = take_error();
    if dev.ctx.is_null() || msg.is_some() {
        if !dev.ctx.is_null() {
            free_device(dev, "mlx_device_free (device info, error path)");
        }
        return Err(NativeError::EmptyHandle {
            call: "mlx_device_new_type",
            message: msg,
        });
    }
    let mut info = unsafe { ffi::mlx_device_info_new() };
    if let Some(m) = take_error() {
        free_device(dev, "mlx_device_free (device info, error path)");
        return Err(NativeError::EmptyHandle {
            call: "mlx_device_info_new",
            message: Some(m),
        });
    }
    let result = (|| {
        status("mlx_device_info_get", unsafe {
            ffi::mlx_device_info_get(&mut info, dev)
        })?;
        let mut out = Vec::new();
        for key in [
            "architecture",
            "device_name",
            "max_buffer_length",
            "max_recommended_working_set_size",
            "memory_size",
            "resource_limit",
        ] {
            let k = CString::new(key).unwrap();
            let mut has = false;
            status("mlx_device_info_has_key", unsafe {
                ffi::mlx_device_info_has_key(&mut has, info, k.as_ptr())
            })?;
            if !has {
                continue;
            }
            let mut is_string = false;
            status("mlx_device_info_is_string", unsafe {
                ffi::mlx_device_info_is_string(&mut is_string, info, k.as_ptr())
            })?;
            if is_string {
                let mut v: *const c_char = std::ptr::null();
                status("mlx_device_info_get_string", unsafe {
                    ffi::mlx_device_info_get_string(&mut v, info, k.as_ptr())
                })?;
                if v.is_null() {
                    return Err(NativeError::Accessor {
                        call: "mlx_device_info_get_string",
                        message: None,
                    });
                }
                out.push((
                    key.to_string(),
                    unsafe { CStr::from_ptr(v) }.to_string_lossy().into_owned(),
                ));
            } else {
                let mut v: usize = 0;
                status("mlx_device_info_get_size", unsafe {
                    ffi::mlx_device_info_get_size(&mut v, info, k.as_ptr())
                })?;
                out.push((key.to_string(), v.to_string()));
            }
        }
        Ok(out)
    })();
    cleanup_status("mlx_device_info_free", unsafe {
        ffi::mlx_device_info_free(info)
    });
    free_device(dev, "mlx_device_free (device info)");
    result
}

pub fn peak_memory() -> Result<usize, NativeError> {
    let mut v = 0usize;
    status("mlx_get_peak_memory", unsafe {
        ffi::mlx_get_peak_memory(&mut v)
    })?;
    Ok(v)
}

pub fn active_memory() -> Result<usize, NativeError> {
    let mut v = 0usize;
    status("mlx_get_active_memory", unsafe {
        ffi::mlx_get_active_memory(&mut v)
    })?;
    Ok(v)
}

pub fn reset_peak_memory() -> Result<(), NativeError> {
    status("mlx_reset_peak_memory", unsafe {
        ffi::mlx_reset_peak_memory()
    })
}

// L-THREAD: compile-time proof that the owning types are neither Send nor
// Sync. Each block below is ambiguous (and fails to compile) if the type
// implements the auto trait.
#[allow(dead_code)]
mod not_send_sync {
    use super::{Evaluated, NativeArray, NativeContext};
    trait AmbiguousIfSend<A> {
        fn check() {}
    }
    impl<T: ?Sized> AmbiguousIfSend<()> for T {}
    impl<T: ?Sized + Send> AmbiguousIfSend<u8> for T {}
    trait AmbiguousIfSync<A> {
        fn check() {}
    }
    impl<T: ?Sized> AmbiguousIfSync<()> for T {}
    impl<T: ?Sized + Sync> AmbiguousIfSync<u8> for T {}
    const _: fn() = || {
        let _ = <NativeContext as AmbiguousIfSend<_>>::check;
        let _ = <NativeContext as AmbiguousIfSync<_>>::check;
        let _ = <NativeArray<'static> as AmbiguousIfSend<_>>::check;
        let _ = <NativeArray<'static> as AmbiguousIfSync<_>>::check;
        let _ = <Evaluated<'static> as AmbiguousIfSend<_>>::check;
        let _ = <Evaluated<'static> as AmbiguousIfSync<_>>::check;
    };
}
