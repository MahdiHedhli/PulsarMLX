use std::{env, path::PathBuf};
fn main() {
    for k in ["MLX_PREFIX", "MLX_C_PREFIX", "PULSAR_REQUIRE_NATIVE_MLX"] {
        println!("cargo:rerun-if-env-changed={k}");
    }
    println!("cargo:rerun-if-changed=native/adoption_bridge.mm");
    println!("cargo:rerun-if-changed=native/adoption_bridge_core.h");
    if env::var_os("CARGO_FEATURE_NATIVE_ADOPTION").is_none() {
        return;
    }
    assert_eq!(
        env::var("CARGO_CFG_TARGET_OS").as_deref(),
        Ok("macos"),
        "native adoption requires macOS"
    );
    let mlx = PathBuf::from(env::var_os("MLX_PREFIX").expect("pinned MLX_PREFIX required"));
    let mlxc = PathBuf::from(env::var_os("MLX_C_PREFIX").expect("pinned MLX_C_PREFIX required"));
    for p in [
        mlx.join("lib/libmlx.dylib"),
        mlxc.join("lib/libmlxc.dylib"),
        mlxc.join("include/mlx/c/mlx.h"),
    ] {
        assert!(p.is_file(), "missing pinned native input: {}", p.display());
    }
    cc::Build::new()
        .cpp(true)
        .file("native/adoption_bridge.mm")
        .include(mlxc.join("include"))
        .flag("-std=c++17")
        .flag("-fobjc-arc")
        .flag("-Wall")
        .flag("-Wextra")
        .flag("-Werror")
        .cargo_metadata(false)
        .compile("adoption_bridge");
    let out = PathBuf::from(env::var_os("OUT_DIR").unwrap());
    println!(
        "cargo:rustc-link-arg-bin=adoption-probe={}",
        out.join("libadoption_bridge.a").display()
    );
    for p in [&mlx, &mlxc] {
        println!(
            "cargo:rustc-link-arg-bin=adoption-probe=-L{}",
            p.join("lib").display()
        );
        println!(
            "cargo:rustc-link-arg-bin=adoption-probe=-Wl,-rpath,{}",
            p.join("lib").display()
        );
    }
    for arg in [
        "-lmlx",
        "-lmlxc",
        "-lc++",
        "-framework",
        "Foundation",
        "-framework",
        "Metal",
    ] {
        println!("cargo:rustc-link-arg-bin=adoption-probe={arg}");
    }
}
