fn main() {
    println!("cargo:rustc-check-cfg=cfg(pulsar_native_mlx)");
    println!("cargo:rerun-if-env-changed=PULSAR_REQUIRE_NATIVE_MLX");
    let require_native_mlx = std::env::var("PULSAR_REQUIRE_NATIVE_MLX")
        .map(|value| value == "1")
        .unwrap_or(false);
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() != Ok("macos") {
        if require_native_mlx {
            panic!("PULSAR_REQUIRE_NATIVE_MLX=1 requires a macOS target");
        }
        return;
    }

    println!("cargo:rerun-if-changed=src/apple_metal_bridge.mm");
    println!("cargo:rerun-if-changed=src/apple_mlx_bridge.mm");
    println!("cargo:rerun-if-changed=src/apple_mlx_deallocation_observer.mm");
    println!("cargo:rerun-if-env-changed=MLX_C_PREFIX");
    println!("cargo:rerun-if-env-changed=MLX_PREFIX");
    cc::Build::new()
        .cpp(true)
        .file("src/apple_metal_bridge.mm")
        .flag("-std=c++17")
        .flag("-fobjc-arc")
        .compile("pulsar_metal_bridge");
    println!("cargo:rustc-link-lib=framework=Foundation");
    println!("cargo:rustc-link-lib=framework=Metal");

    let mlx_c_prefix = std::env::var("MLX_C_PREFIX")
        .map(std::path::PathBuf::from)
        .unwrap_or_else(|_| std::path::PathBuf::from("/opt/homebrew/opt/mlx-c"));
    let mlx_prefix = std::env::var("MLX_PREFIX")
        .map(std::path::PathBuf::from)
        .unwrap_or_else(|_| std::path::PathBuf::from("/opt/homebrew/opt/mlx"));
    let mlx_include = mlx_c_prefix.join("include");
    let mlx_c_lib = mlx_c_prefix.join("lib");
    let mlx_lib = mlx_prefix.join("lib");
    let mlx_header = mlx_include.join("mlx/c/mlx.h");
    let mlx_c_library = mlx_c_lib.join("libmlxc.dylib");
    let mlx_library = mlx_lib.join("libmlx.dylib");
    if mlx_header.is_file() && mlx_c_library.is_file() && mlx_library.is_file() {
        cc::Build::new()
            .cpp(true)
            .file("src/apple_mlx_bridge.mm")
            .file("src/apple_mlx_deallocation_observer.mm")
            .include(&mlx_include)
            .flag("-std=c++17")
            .flag("-fobjc-arc")
            .compile("pulsar_mlx_bridge");
        println!("cargo:rustc-cfg=pulsar_native_mlx");
        println!("cargo:rustc-link-search=native={}", mlx_c_lib.display());
        println!("cargo:rustc-link-search=native={}", mlx_lib.display());
        println!("cargo:rustc-link-lib=dylib=mlxc");
        println!("cargo:rustc-link-lib=dylib=mlx");
        println!("cargo:rustc-link-arg=-Wl,-rpath,{}", mlx_c_lib.display());
        println!("cargo:rustc-link-arg=-Wl,-rpath,{}", mlx_lib.display());
    } else {
        let detail = format!(
            "native MLX C API unavailable: header={}, mlxc={}, mlx={}",
            mlx_header.display(),
            mlx_c_library.display(),
            mlx_library.display()
        );
        if require_native_mlx {
            panic!("PULSAR_REQUIRE_NATIVE_MLX=1 but {detail}");
        }
        println!("cargo:warning={detail}; MLX adapter tests are skipped");
    }
}
