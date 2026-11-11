//! Copied-only diagnostic child. The default workspace build excludes this binary.
//! On macOS without prefixes the native implementation is type-checked but never called.
#[cfg(target_os = "macos")]
#[path = "../../../mlx-native-affine/src/bin/qualify/bridge.rs"]
mod bridge;
#[cfg(target_os = "macos")]
#[path = "../../../mlx-native-affine/src/bin/qualify/ffi.rs"]
mod ffi;
#[cfg(target_os = "macos")]
#[path = "../../../mlx-native-affine/src/bin/qualify/native.rs"]
mod native;
#[cfg(target_os = "macos")]
#[path = "../../../mlx-native-affine/src/bin/qualify/provenance.rs"]
mod provenance;
#[cfg(target_os = "macos")]
#[path = "../resident_native.rs"]
mod resident_native;

fn main() {
    #[cfg(all(target_os = "macos", pulsar_native_mlx))]
    if let Err(e) = resident_native::run() {
        eprintln!("{e}");
        std::process::exit(1);
    }
    #[cfg(not(all(target_os = "macos", pulsar_native_mlx)))]
    {
        eprintln!("explicit pinned native build required");
        std::process::exit(69);
    }
}
