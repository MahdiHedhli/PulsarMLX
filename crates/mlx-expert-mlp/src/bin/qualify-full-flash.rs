//! Cold one-token qualification. Production entry is usable only by the live supervised child.
#[cfg(all(pulsar_native_mlx, not(test)))]
#[path = "../full_flash/child.rs"]
mod child;
#[cfg(pulsar_native_mlx)]
#[path = "../../../mlx-native-affine/src/bin/qualify/ffi.rs"]
mod ffi;
#[path = "../full_flash/graph.rs"]
mod graph;
#[cfg(pulsar_native_mlx)]
#[path = "../../../mlx-native-affine/src/bin/qualify/native.rs"]
mod native;
#[cfg(pulsar_native_mlx)]
#[path = "../full_flash/provider.rs"]
mod provider;
fn main() {
    #[cfg(all(pulsar_native_mlx, not(test)))]
    if let Err(e) = child::run() {
        eprintln!("cold forward refused: {e}");
        std::process::exit(1)
    }
    #[cfg(not(pulsar_native_mlx))]
    {
        eprintln!("pinned native MLX is required");
        std::process::exit(1)
    }
}
