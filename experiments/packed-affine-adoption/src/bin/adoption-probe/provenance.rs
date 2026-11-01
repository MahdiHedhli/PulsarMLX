//! Observe loaded images, not merely filenames in the selected installation.
use mlx_native_affine::fixture::sha256_hex;
use serde_json::{json, Value};
use std::{
    collections::BTreeMap,
    ffi::{c_char, CStr},
    fs,
    path::{Path, PathBuf},
};
extern "C" {
    fn _dyld_image_count() -> u32;
    fn _dyld_get_image_name(index: u32) -> *const c_char;
}
pub fn collect(config: &Value) -> Result<Value, String> {
    let prefix =
        PathBuf::from(std::env::var_os("PULSAR_F020_NATIVE_PREFIX").ok_or("native prefix")?)
            .canonicalize()
            .map_err(|e| e.to_string())?;
    if std::env::var("MLX_ENABLE_TF32").as_deref() != Ok("0")
        || [
            "MLX_METAL_GPU_ARCH",
            "MLX_MAX_OPS_PER_BUFFER",
            "MLX_MAX_MB_PER_BUFFER",
        ]
        .iter()
        .any(|n| std::env::var_os(n).is_some())
    {
        return Err("nonfrozen native environment".into());
    }
    let mut images = BTreeMap::new();
    // SAFETY: dyld names are stable NUL-terminated image names.
    for i in 0..unsafe { _dyld_image_count() } {
        let ptr = unsafe { _dyld_get_image_name(i) };
        if ptr.is_null() {
            continue;
        }
        let path = PathBuf::from(
            unsafe { CStr::from_ptr(ptr) }
                .to_string_lossy()
                .into_owned(),
        );
        let name = path
            .file_name()
            .ok_or("loaded image name")?
            .to_string_lossy()
            .into_owned();
        if !name.to_lowercase().contains("mlx") {
            continue;
        }
        if !["libmlx.dylib", "libmlxc.dylib"].contains(&name.as_str()) {
            return Err("unexpected MLX image".into());
        }
        let real = path.canonicalize().map_err(|e| e.to_string())?;
        if !real.starts_with(prefix.join("lib"))
            || images
                .insert(
                    name.clone(),
                    sha256_hex(&fs::read(real).map_err(|e| e.to_string())?),
                )
                .is_some()
        {
            return Err("loaded library outside prefix or duplicate".into());
        }
    }
    if images.len() != 2 {
        return Err("missing loaded MLX library".into());
    }
    let metal = prefix
        .join("lib/mlx.metallib")
        .canonicalize()
        .map_err(|e| e.to_string())?;
    if !metal.starts_with(prefix.join("lib")) {
        return Err("metallib outside prefix".into());
    }
    images.insert(
        "mlx.metallib".into(),
        sha256_hex(&fs::read(metal).map_err(|e| e.to_string())?),
    );
    if serde_json::to_value(&images).unwrap() != config["native_libraries"] {
        return Err("actual loaded native identities differ from freeze".into());
    }
    let binary = sha256_hex(
        &fs::read(std::env::current_exe().map_err(|e| e.to_string())?)
            .map_err(|e| e.to_string())?,
    );
    if config["binary_sha256"] != binary {
        return Err("child executable differs from frozen binary".into());
    }
    let dyld = std::env::var("DYLD_LIBRARY_PATH").map_err(|_| "library search path")?;
    if Path::new(&dyld).canonicalize().map_err(|e| e.to_string())? != prefix.join("lib") {
        return Err("library search prefix".into());
    }
    Ok(
        json!({"native_libraries":images,"binary_sha256":binary,"source_commit":config["source_commit"],"source_tree":config["source_tree"],"loaded_images_verified":true,"TF32":false,"native_prefix":"<NATIVE_PREFIX>"}),
    )
}
