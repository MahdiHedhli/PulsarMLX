use std::ffi::c_void;
extern "C" {
    pub fn pa_page() -> usize;
    pub fn pa_max_buffer() -> usize;
    pub fn pa_open() -> *mut c_void;
    pub fn pa_stream(ctx: *mut c_void) -> i32;
    pub fn pa_sync(ctx: *mut c_void) -> i32;
    pub fn pa_register(
        ctx: *mut c_void,
        bytes: *mut u8,
        length: usize,
        token: *const c_void,
        callback: unsafe extern "C" fn(*const c_void),
        raw: bool,
    ) -> i32;
    pub fn pa_drop_slot(ctx: *mut c_void, slot: usize) -> i32;
    pub fn pa_prepare(
        ctx: *mut c_void,
        slot: usize,
        w: *const u8,
        s: *const u8,
        b: *const u8,
        offset: usize,
        n: i32,
        k: i32,
        bits: i32,
        adopted: bool,
        diagnostic: bool,
        metadata: i32,
    ) -> i32;
    pub fn pa_input(ctx: *mut c_void, slot: usize, x: *const u8, m: i32, k: i32) -> i32;
    pub fn pa_project(
        ctx: *mut c_void,
        slot: usize,
        m: i32,
        n: i32,
        k: i32,
        bits: i32,
        output: *mut f32,
    ) -> i32;
    pub fn pa_copy_control(ctx: *mut c_void, source: *const u8, bytes: usize) -> i32;
    pub fn pa_memory(ctx: *mut c_void, out: *mut usize) -> i32;
    pub fn pa_reset_peak() -> i32;
    pub fn pa_retire(ctx: *mut c_void, counts: *mut usize) -> i32;
    pub fn pa_close(ctx: *mut c_void) -> i32;
}
