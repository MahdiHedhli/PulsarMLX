//! New child; inherited bridge/ownership/provenance sources are used unchanged.
#[cfg(pulsar_native_mlx)]
#[path = "../../mlx-native-affine/src/bin/qualify/bridge.rs"]
mod bridge;
#[cfg(pulsar_native_mlx)]
mod execute;
#[cfg(pulsar_native_mlx)]
#[path = "../../mlx-native-affine/src/bin/qualify/ffi.rs"]
mod ffi;
#[cfg(pulsar_native_mlx)]
#[path = "../../mlx-native-affine/src/bin/qualify/native.rs"]
mod native;
#[cfg(pulsar_native_mlx)]
#[path = "../../mlx-native-affine/src/bin/qualify/provenance.rs"]
mod provenance;

#[cfg(pulsar_native_mlx)]
mod selected_entry;
#[cfg(pulsar_native_mlx)]
mod selected_execute;
#[cfg(pulsar_native_mlx)]
mod selected_resources;

fn main() {
    #[cfg(pulsar_native_mlx)]
    let result = if std::env::args().nth(1).as_deref() == Some("--selected") {
        selected_entry::main()
    } else {
        execute::main()
    };
    #[cfg(not(pulsar_native_mlx))]
    let result: Result<(), String> =
        Err("native Studio build required; no computation executed".into());
    if let Err(e) = result {
        eprintln!("{e}");
        std::process::exit(1);
    }
}
