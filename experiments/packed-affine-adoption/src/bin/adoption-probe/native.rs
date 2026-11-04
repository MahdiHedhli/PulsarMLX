use super::{
    ffi,
    slab::{callback, Callback, Slab},
};
use packed_affine_adoption::{adopted, require_retired, LIVE_LIMIT};
use std::{
    cell::{Cell, RefCell},
    ffi::c_void,
    marker::PhantomData,
    rc::Rc,
    sync::{atomic::Ordering, Arc},
    time::{Duration, Instant},
};
thread_local! {
    static DIAGNOSTIC_ENABLED: Cell<bool> = const { Cell::new(false) };
    static DIAGNOSTIC_TOKEN: RefCell<Option<(Arc<Callback>, bool)>> = const { RefCell::new(None) };
}
pub fn enable_diagnostic(fd: i32) -> Result<(), String> {
    check(unsafe { ffi::pa_diagnostic_enable(fd) })?;
    DIAGNOSTIC_ENABLED.with(|v| v.set(true));
    Ok(())
}
pub fn diagnostic_snapshot() -> serde_json::Value {
    let mut words = [0u64; 40];
    let mut error = [0u8; 256];
    let status = unsafe {
        ffi::pa_diagnostic_snapshot(
            words.as_mut_ptr(),
            words.len(),
            error.as_mut_ptr(),
            error.len(),
        )
    };
    let end = error.iter().position(|b| *b == 0).unwrap_or(error.len());
    let callback = DIAGNOSTIC_TOKEN.with(|v| v.borrow().as_ref().map(|(token, attempted)|
        serde_json::json!({"registration_attempted":attempted,"completed_callbacks":token.completed.load(Ordering::Acquire)})));
    serde_json::json!({"schema":"pulsarmlx.bridge-diagnostic-snapshot/1","snapshot_status":status,
        "enabled":words[0]!=0,"last_function":words[1],"last_substage":words[2],"last_phase":words[3],
        "mlx_status":if words[4]!=0 {Some(words[5] as i64)}else{None},
        "bridge_refusal":words[6],"failed_function":words[7],"failed_substage":words[8],
        "mlx_error_callbacks":words[9],"first_error_capture_state":words[10],"exception_category":words[11],
        "first_error_truncated":words[12]!=0,"first_error_text_lossy":String::from_utf8_lossy(&error[..end]),
        "first_error_bytes_hex":error[..end].iter().map(|b|format!("{b:02x}")).collect::<String>(),
        "qmm_graph_enter":words[13],"qmm_graph_return":words[14],"evaluation_attempts":words[15],"evaluation_completions":words[16],
        "synchronization_completions":words[17],"retirement_enter":words[18],"retirement_complete":words[19],"close_complete":words[20],
        "context_present":words[21]!=0,"evidence_write_failed":words[22]!=0,"trace_records":words[23],
        "accounting":if words[21]!=0 {Some(serde_json::json!({"created":words[24],"freed":words[25],"live":words[26],
            "parent_counts":[words[27],words[28]],"view_counts":[words[29],words[30]],"output_counts":[words[31],words[32]],
            "parent_present":words[33]!=0,"context_failed":words[34]!=0,"slot_handle_bits":[words[35],words[36]]}))}else{None},
        "callback":callback,"snapshot_native_calls":0,"cleanup_attempted_for_snapshot":false,
        "gpu_kernel_completion_inferred_from_qmm":false})
}
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
        let token = Arc::new(Callback::default());
        if DIAGNOSTIC_ENABLED.with(Cell::get) {
            DIAGNOSTIC_TOKEN.with(|v| *v.borrow_mut() = Some((token.clone(), false)));
        }
        Ok(Self {
            ptr,
            token,
            registered: false,
            _owner: PhantomData,
        })
    }
    pub fn register(&mut self, slab: &Slab, raw: bool) -> Result<i32, String> {
        if self.registered {
            return Err("duplicate parent attempt".into());
        }
        self.registered = true;
        DIAGNOSTIC_TOKEN.with(|v| {
            if let Some((_, attempted)) = v.borrow_mut().as_mut() {
                *attempted = true;
            }
        });
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
