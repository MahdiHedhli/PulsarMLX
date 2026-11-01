use super::{
    ffi,
    slab::{callback, Callback, Slab},
};
use packed_affine_adoption::{adopted, require_retired, LIVE_LIMIT};
use std::{
    ffi::c_void,
    marker::PhantomData,
    rc::Rc,
    sync::{atomic::Ordering, Arc},
    time::{Duration, Instant},
};
pub struct Native {
    pub ptr: *mut c_void,
    pub token: Arc<Callback>,
    registered: bool,
    _owner: PhantomData<Rc<()>>,
}
pub fn check(st: i32) -> Result<(), String> {
    if st == 0 {
        Ok(())
    } else {
        Err(format!(
            "native-status-{st}; ownership uncertain; terminate child"
        ))
    }
}
impl Native {
    pub fn open() -> Result<Self, String> {
        let ptr = unsafe { ffi::pa_open() };
        if ptr.is_null() {
            return Err("native initialization failed; terminate child".into());
        }
        Ok(Self {
            ptr,
            token: Arc::new(Callback::default()),
            registered: false,
            _owner: PhantomData,
        })
    }
    pub fn register(&mut self, slab: &Slab, raw: bool) -> Result<i32, String> {
        if self.registered {
            return Err("duplicate parent attempt".into());
        }
        self.registered = true;
        let token = Arc::into_raw(self.token.clone()).cast();
        // SAFETY: initialized stable allocation outlives all consumers, token has
        // independent ownership. No mutable payload borrow exists at this call.
        let st = unsafe {
            ffi::pa_register(self.ptr, slab.pointer(), slab.bytes(), token, callback, raw)
        };
        if !raw {
            adopted(
                st == 0,
                self.token.completed.load(Ordering::Acquire) != 0,
                st == 0 || st == 4,
            )
            .map_err(|reason| format!("{reason}; constructor status {st}"))?;
        }
        Ok(st)
    }
    pub fn memory(&self) -> Result<[usize; 3], String> {
        let mut m = [0; 3];
        check(unsafe { ffi::pa_memory(self.ptr, m.as_mut_ptr()) })?;
        if m[0] > LIVE_LIMIT || m[2] > LIVE_LIMIT {
            return Err("native active/interval peak exceeds 32 MiB".into());
        }
        Ok(m)
    }
    pub fn retire(self, slab: &mut Slab) -> Result<[usize; 9], String> {
        let mut counts = [0; 9];
        check(unsafe { ffi::pa_retire(self.ptr, counts.as_mut_ptr()) })?;
        let start = Instant::now();
        let expected = u64::from(self.registered);
        while self.token.completed.load(Ordering::Acquire) < expected
            && start.elapsed() < Duration::from_millis(5000)
        {
            std::thread::sleep(Duration::from_millis(1));
        }
        require_retired(
            expected,
            self.token.completed.load(Ordering::Acquire),
            counts[2] as u64,
            0,
            false,
        )
        .map_err(str::to_string)?;
        check(unsafe { ffi::pa_close(self.ptr) })?;
        slab.acknowledge_retirement();
        Ok(counts)
    }
}
