//! Portable admission/lease/report logic. This library never calls MLX.
#![forbid(unsafe_code)]
pub mod cases;
pub mod lease;
pub mod policy;
pub mod selected_preflight;
pub const CONTRACT: &str = "943e0a9e2358985038f2fba31831fa302d3aeae3dd8f50e85970a4760931a49b";
pub const LIVE_LIMIT: usize = 32 * 1024 * 1024;
pub const RESERVATION: usize = 96 * 1024 * 1024;

pub fn registration(
    plane_bytes: usize,
    page: usize,
    max_buffer: usize,
) -> Result<usize, &'static str> {
    if plane_bytes == 0 || plane_bytes % 4 != 0 || !page.is_power_of_two() || page < 4 {
        return Err("geometry");
    }
    let capacity = plane_bytes.checked_mul(2).ok_or("overflow")?;
    let rounded = capacity.checked_add(page - 1).ok_or("overflow")? & !(page - 1);
    if rounded > max_buffer || rounded > LIVE_LIMIT || rounded / 4 > i32::MAX as usize {
        return Err("capacity");
    }
    Ok(rounded)
}

pub fn adopted(
    pointer_equal: bool,
    early_callback: bool,
    native_success: bool,
) -> Result<(), &'static str> {
    if !native_success {
        Err("native-error")
    } else if early_callback {
        Err("early-callback")
    } else if !pointer_equal {
        Err("copied-fallback")
    } else {
        Ok(())
    }
}

pub fn require_retired(
    retired: u64,
    callbacks: u64,
    live: u64,
    early_free: u64,
    quarantine: bool,
) -> Result<(), &'static str> {
    if retired != callbacks || live != 0 || early_free != 0 || quarantine {
        Err("ownership-unresolved")
    } else {
        Ok(())
    }
}
