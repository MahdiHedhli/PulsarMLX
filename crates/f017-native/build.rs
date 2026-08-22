fn main() {
    println!("cargo:rustc-check-cfg=cfg(pulsar_native_mlx)");
    println!("cargo:rerun-if-env-changed=PULSAR_REQUIRE_NATIVE_MLX");
    println!("cargo:rerun-if-env-changed=MLX_C_PREFIX");
    println!("cargo:rerun-if-env-changed=MLX_PREFIX");
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() != Ok("macos") {
        return;
    }
    let mlx_c = std::env::var("MLX_C_PREFIX")
        .map(std::path::PathBuf::from)
        .unwrap_or_else(|_| "/opt/homebrew/opt/mlx-c".into());
    let mlx = std::env::var("MLX_PREFIX")
        .map(std::path::PathBuf::from)
        .unwrap_or_else(|_| "/opt/homebrew/opt/mlx".into());
    let available = mlx_c.join("include/mlx/c/mlx.h").is_file()
        && mlx_c.join("lib/libmlxc.dylib").is_file()
        && mlx.join("lib/libmlx.dylib").is_file();
    if available {
        println!("cargo:rustc-cfg=pulsar_native_mlx");
    } else if std::env::var("PULSAR_REQUIRE_NATIVE_MLX").as_deref() == Ok("1") {
        panic!("PULSAR_REQUIRE_NATIVE_MLX=1 but pinned native MLX is unavailable");
    }
}
