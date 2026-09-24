//! E3 provenance: which libraries this process actually loaded, their
//! hashes, the colocated metallib and its NAX-name scan, the device
//! architecture, and the relevant environment. Paths are recorded relative
//! to the native prefix, never as private absolute paths; a loaded MLX
//! library outside the prefix is a setup failure.

use std::ffi::{CStr, CString};
use std::os::raw::{c_char, c_void};
use std::path::{Path, PathBuf};

use mlx_native_affine::family::{nax_capable_hardware, parse_architecture};
use mlx_native_affine::fixture::sha256_hex;
use mlx_native_affine::frozen;
use serde_json::{json, Value};

use crate::ffi;
use crate::native;

extern "C" {
    fn _dyld_image_count() -> u32;
    fn _dyld_get_image_name(index: u32) -> *const c_char;
}

fn loaded_images() -> Vec<PathBuf> {
    // SAFETY: dyld's image list; names are NUL-terminated and static.
    let n = unsafe { _dyld_image_count() };
    (0..n)
        .filter_map(|i| {
            let p = unsafe { _dyld_get_image_name(i) };
            if p.is_null() {
                None
            } else {
                Some(PathBuf::from(
                    unsafe { CStr::from_ptr(p) }.to_string_lossy().into_owned(),
                ))
            }
        })
        .collect()
}

fn dladdr_path(symbol: *const c_void) -> Option<PathBuf> {
    let mut info: libc::Dl_info = unsafe { std::mem::zeroed() };
    // SAFETY: `symbol` is the address of a function in a loaded image.
    let ok = unsafe { libc::dladdr(symbol, &mut info) };
    if ok == 0 || info.dli_fname.is_null() {
        return None;
    }
    Some(PathBuf::from(
        unsafe { CStr::from_ptr(info.dli_fname) }
            .to_string_lossy()
            .into_owned(),
    ))
}

fn sysctl_string(name: &str) -> Option<String> {
    let c = CString::new(name).ok()?;
    let mut len: libc::size_t = 0;
    unsafe {
        if libc::sysctlbyname(
            c.as_ptr(),
            std::ptr::null_mut(),
            &mut len,
            std::ptr::null_mut(),
            0,
        ) != 0
        {
            return None;
        }
        let mut buf = vec![0u8; len];
        if libc::sysctlbyname(
            c.as_ptr(),
            buf.as_mut_ptr() as *mut c_void,
            &mut len,
            std::ptr::null_mut(),
            0,
        ) != 0
        {
            return None;
        }
        buf.truncate(len);
        while buf.last() == Some(&0) {
            buf.pop();
        }
        String::from_utf8(buf).ok()
    }
}

fn os_at_least(version: &str, major: u32, minor: u32) -> bool {
    let mut it = version.split('.').map(|p| p.parse::<u32>().unwrap_or(0));
    let a = it.next().unwrap_or(0);
    let b = it.next().unwrap_or(0);
    (a, b) >= (major, minor)
}

fn count(hay: &[u8], needle: &[u8]) -> usize {
    hay.windows(needle.len()).filter(|w| *w == needle).count()
}

fn relative(prefix: &Path, p: &Path) -> Result<String, String> {
    let real = p
        .canonicalize()
        .map_err(|e| format!("canonicalize {}: {e}", p.display()))?;
    real.strip_prefix(prefix)
        .map(|r| r.to_string_lossy().into_owned())
        .map_err(|_| {
            format!(
                "loaded library {} is outside the native prefix",
                real.file_name()
                    .map(|f| f.to_string_lossy().into_owned())
                    .unwrap_or_default()
            )
        })
}

/// Collect E3. `prefix` is the native prefix named by the parent.
pub fn collect(prefix_env: &str) -> Result<Value, String> {
    let prefix = Path::new(prefix_env)
        .canonicalize()
        .map_err(|e| format!("native prefix: {e}"))?;

    let mlxc =
        dladdr_path(ffi::mlx_version as *const c_void).ok_or("dladdr(mlx_version) failed")?;
    let mlxc_rel = relative(&prefix, &mlxc)?;
    let images = loaded_images();
    let named = |base: &str| -> Vec<&PathBuf> {
        images
            .iter()
            .filter(|p| {
                p.file_name()
                    .map(|f| f.to_string_lossy() == base)
                    .unwrap_or(false)
            })
            .collect()
    };
    let libmlx = named("libmlx.dylib");
    let libmlxc = named("libmlxc.dylib");
    if libmlx.len() != 1 || libmlxc.len() != 1 {
        return Err(format!(
            "expected exactly one libmlx and one libmlxc image, found {} and {}",
            libmlx.len(),
            libmlxc.len()
        ));
    }
    let mlx_rel = relative(&prefix, libmlx[0])?;
    if relative(&prefix, libmlxc[0])? != mlxc_rel {
        return Err("dyld libmlxc differs from dladdr(mlx_version)".into());
    }
    let mlx_real = libmlx[0].canonicalize().map_err(|e| e.to_string())?;
    let metallib = mlx_real
        .parent()
        .ok_or("libmlx parent")?
        .join("mlx.metallib");
    let metallib_rel = relative(&prefix, &metallib)?;
    let mlx_bytes = std::fs::read(&mlx_real).map_err(|e| e.to_string())?;
    let mlxc_bytes = std::fs::read(mlxc.canonicalize().map_err(|e| e.to_string())?)
        .map_err(|e| e.to_string())?;
    let metallib_bytes = std::fs::read(&metallib).map_err(|e| format!("metallib: {e}"))?;
    let libmlx_sha = sha256_hex(&mlx_bytes);
    let libmlxc_sha = sha256_hex(&mlxc_bytes);
    let metallib_sha = sha256_hex(&metallib_bytes);
    let nax_names = count(&metallib_bytes, b"_nax_");
    let identity = sha256_hex(
        format!(
            "{mlx_rel} {libmlx_sha}\n{mlxc_rel} {libmlxc_sha}\n{metallib_rel} {metallib_sha}\n"
        )
        .as_bytes(),
    );
    let other_mlx_images: Vec<String> = images
        .iter()
        .filter_map(|p| p.file_name().map(|f| f.to_string_lossy().into_owned()))
        .filter(|f| f.to_lowercase().contains("mlx") && f != "libmlx.dylib" && f != "libmlxc.dylib")
        .collect();

    let version = native::mlx_version().map_err(|e| e.to_string())?;
    let info = native::gpu_device_info().map_err(|e| e.to_string())?;
    let arch_name = info
        .iter()
        .find(|(k, _)| k == "architecture")
        .map(|(_, v)| v.clone())
        .ok_or("no architecture")?;
    let arch = parse_architecture(&arch_name);
    let os = sysctl_string("kern.osproductversion").unwrap_or_default();
    let nax_hw = nax_capable_hardware(&arch, os_at_least(&os, 26, 2));
    let device_info: serde_json::Map<String, Value> = info
        .into_iter()
        .map(|(k, v)| (k, Value::String(v)))
        .collect();
    let exe_sha = std::env::current_exe()
        .ok()
        .and_then(|p| std::fs::read(p).ok())
        .map(|b| sha256_hex(&b));
    let dyld = std::env::var("DYLD_LIBRARY_PATH").unwrap_or_default();
    let dyld_label = if Path::new(&dyld).canonicalize().ok() == Some(prefix.join("lib")) {
        "<native-prefix>/lib".to_string()
    } else {
        "OTHER".to_string()
    };

    Ok(json!({
        "mlx_version": version,
        "mlx_version_expected": frozen::MLX_VERSION,
        "mlx_commit_pinned": frozen::MLX_COMMIT,
        "mlx_c_commit_pinned": frozen::MLX_C_COMMIT,
        "native_prefix": {
            "label": "<native-prefix>",
            "identity_sha256": identity,
            "identity_method": "sha256 of '<relpath> <sha256>' lines for libmlx, libmlxc, mlx.metallib",
        },
        "libmlx": {"relative_path": mlx_rel, "sha256": libmlx_sha, "bytes": mlx_bytes.len(), "method": "dyld image list"},
        "libmlxc": {"relative_path": mlxc_rel, "sha256": libmlxc_sha, "bytes": mlxc_bytes.len(), "method": "dladdr(mlx_version)"},
        "metallib": {"relative_path": metallib_rel, "sha256": metallib_sha, "bytes": metallib_bytes.len(), "nax_name_occurrences": nax_names, "contains_nax_names": nax_names > 0},
        "other_mlx_named_images": other_mlx_images,
        "device_info": device_info,
        "architecture": arch.name,
        "architecture_generation": arch.generation,
        "architecture_size_class": arch.size_class.to_string(),
        "os_product_version": os,
        "nax_capable_hardware": nax_hw,
        "environment": {
            "MLX_ENABLE_TF32": std::env::var("MLX_ENABLE_TF32").ok(),
            "MLX_METAL_GPU_ARCH_set": std::env::var_os("MLX_METAL_GPU_ARCH").is_some(),
            "MLX_MAX_OPS_PER_BUFFER_set": std::env::var_os("MLX_MAX_OPS_PER_BUFFER").is_some(),
            "MLX_MAX_MB_PER_BUFFER_set": std::env::var_os("MLX_MAX_MB_PER_BUFFER").is_some(),
            "DYLD_LIBRARY_PATH": dyld_label,
        },
        "build": {
            "rustc": env!("F020_RUSTC_VERSION"),
            "profile": env!("F020_BUILD_PROFILE"),
            "crate_version": env!("CARGO_PKG_VERSION"),
            "qualify_executable_sha256": exe_sha,
        },
    }))
}
