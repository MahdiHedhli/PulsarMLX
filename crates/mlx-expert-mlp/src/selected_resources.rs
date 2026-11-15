//! Measured acceptance gates; MLX's memory guideline is not a hard cap.
use crate::native;
use serde_json::{json, Value};
extern "C" {
    fn mlx_set_cache_limit(previous: *mut usize, limit: usize) -> i32;
    fn mlx_get_cache_memory(value: *mut usize) -> i32;
}
pub const NATIVE_LIMIT: usize = 64 * 1024 * 1024;
pub const RSS_LIMIT: u64 = 1024 * 1024 * 1024;

pub fn peak_rss() -> Result<u64, String> {
    let mut usage = std::mem::MaybeUninit::<libc::rusage>::uninit();
    if unsafe { libc::getrusage(libc::RUSAGE_SELF, usage.as_mut_ptr()) } != 0 {
        return Err("SELECTED-R-RESOURCE: getrusage".into());
    }
    let usage = unsafe { usage.assume_init() };
    u64::try_from(usage.ru_maxrss).map_err(|_| "SELECTED-R-RESOURCE: negative peak RSS".into())
}
pub fn initialize() -> Result<(), String> {
    let mut previous = 0;
    if unsafe { mlx_set_cache_limit(&mut previous, 0) } != 0 {
        return Err("SELECTED-R-RESOURCE: cache limit".into());
    }
    Ok(())
}
pub fn sample() -> Result<Value, String> {
    let active = native::active_memory().map_err(|e| e.to_string())?;
    let peak = native::peak_memory().map_err(|e| e.to_string())?;
    let rss = peak_rss()?;
    let mut cache = 0;
    if unsafe { mlx_get_cache_memory(&mut cache) } != 0 {
        return Err("SELECTED-R-RESOURCE: cache counter".into());
    }
    let value = json!({"active_bytes":active,"allocator_peak_bytes":peak,"cache_bytes":cache,
      "process_peak_rss_bytes":rss,"native_acceptance_cap_bytes":NATIVE_LIMIT,
      "process_peak_rss_acceptance_cap_bytes":RSS_LIMIT,"instantaneous_os_limit_claim":false});
    if active > NATIVE_LIMIT || peak > NATIVE_LIMIT || rss > RSS_LIMIT {
        return Err(format!(
            "SELECTED-R-RESOURCE: measured cap exceeded {value}"
        ));
    }
    Ok(value)
}
