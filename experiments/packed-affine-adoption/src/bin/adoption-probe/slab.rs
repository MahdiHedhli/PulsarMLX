use sha2::{Digest, Sha256};
use std::{
    alloc::{alloc_zeroed, dealloc, Layout},
    ffi::c_void,
    marker::PhantomData,
    ptr::NonNull,
    rc::Rc,
    sync::{
        atomic::{AtomicU64, Ordering},
        Arc,
    },
};

#[derive(Default)]
pub struct Callback {
    pub completed: AtomicU64,
}
pub unsafe extern "C" fn callback(p: *const c_void) {
    // SAFETY: exactly one raw Arc reference was transferred for this constructor.
    // It independently retains the token until callback exit. No payload access,
    // allocation, locks, MLX, pool calls or unwinding occurs in this callback.
    let token = unsafe { Arc::from_raw(p.cast::<Callback>()) };
    token.completed.fetch_add(1, Ordering::Release);
}
pub struct Slab {
    ptr: NonNull<u8>,
    layout: Layout,
    retired: bool,
    _owner: PhantomData<Rc<()>>,
}
impl Slab {
    pub fn new(bytes: usize, page: usize) -> Result<Self, String> {
        let layout = Layout::from_size_align(bytes, page).map_err(|e| e.to_string())?;
        // SAFETY: checked layout; allocation address is stable for its lifetime.
        let ptr = NonNull::new(unsafe { alloc_zeroed(layout) }).ok_or("allocation refused")?;
        Ok(Self {
            ptr,
            layout,
            retired: false,
            _owner: PhantomData,
        })
    }
    pub fn pointer(&self) -> *mut u8 {
        self.ptr.as_ptr()
    }
    pub fn bytes(&self) -> usize {
        self.layout.size()
    }
    /// Caller proves whole-buffer quiescence and releases the borrow before any
    /// native call. Only the selected weight range is exposed, never the slab.
    pub unsafe fn destination(&mut self, offset: usize, len: usize) -> Result<&mut [u8], String> {
        if offset.checked_add(len).is_none_or(|e| e > self.bytes()) {
            return Err("slot bounds".into());
        }
        Ok(unsafe { std::slice::from_raw_parts_mut(self.pointer().add(offset), len) })
    }
    pub unsafe fn diagnostic_hash(&self) -> String {
        // SAFETY: caller establishes no fills/evaluations; allocation initialized.
        format!(
            "{:x}",
            Sha256::digest(unsafe { std::slice::from_raw_parts(self.pointer(), self.bytes()) })
        )
    }
    pub fn acknowledge_retirement(&mut self) {
        self.retired = true;
    }
}
impl Drop for Slab {
    fn drop(&mut self) {
        // Failure is quarantine, not guessed ownership. Native children terminate
        // after such a failure; no repeated replacement allocations are permitted.
        if self.retired {
            unsafe { dealloc(self.pointer(), self.layout) }
        }
    }
}
