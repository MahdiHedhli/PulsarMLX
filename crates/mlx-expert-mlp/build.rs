use std::path::PathBuf;

fn main() {
    println!("cargo:rustc-check-cfg=cfg(pulsar_native_mlx)");
    println!("cargo:rerun-if-env-changed=MLX_C_PREFIX");
    println!("cargo:rerun-if-env-changed=MLX_PREFIX");
    println!("cargo:rerun-if-changed=src/activation.cpp");
    println!("cargo:rerun-if-changed=src/activation_selected.cpp");
    println!("cargo:rerun-if-changed=../mlx-native-affine/src/abi_check.c");
    println!("cargo:rerun-if-changed=../../scripts/research/f020_fused_swiglu_cpu_guard_v2_4.h");
    let rustc = std::process::Command::new("rustc")
        .arg("-V")
        .output()
        .expect("rustc");
    println!(
        "cargo:rustc-env=F020_RUSTC_VERSION={}",
        String::from_utf8_lossy(&rustc.stdout).trim()
    );
    println!(
        "cargo:rustc-env=F020_BUILD_PROFILE={}",
        std::env::var("PROFILE").unwrap()
    );
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() != Ok("macos") {
        return;
    }
    let (Ok(c), Ok(m)) = (std::env::var("MLX_C_PREFIX"), std::env::var("MLX_PREFIX")) else {
        return;
    };
    let c = PathBuf::from(c);
    let m = PathBuf::from(m);
    for p in [
        c.join("include/mlx/c/mlx.h"),
        c.join("lib/libmlxc.dylib"),
        m.join("lib/libmlx.dylib"),
    ] {
        assert!(
            p.is_file(),
            "missing explicitly supplied pinned native dependency"
        );
    }
    cc::Build::new()
        .file("../mlx-native-affine/src/abi_check.c")
        .include(c.join("include"))
        .flag("-std=c11")
        .flag("-Wall")
        .flag("-Werror")
        .cargo_metadata(false)
        .compile("expert_mlp_abi");
    cc::Build::new()
        .cpp(true)
        .file("src/activation.cpp")
        .file("src/activation_selected.cpp")
        .include(c.join("include"))
        .include("../../scripts/research")
        .flag("-std=c++17")
        .flag("-fno-fast-math")
        .flag("-ffp-contract=off")
        .flag("-Wall")
        .flag("-Werror")
        .cargo_metadata(false)
        .compile("expert_mlp_activation");
    let out = PathBuf::from(std::env::var("OUT_DIR").unwrap());
    let bin = "qualify-expert-mlp";
    for lib in ["expert_mlp_abi", "expert_mlp_activation"] {
        println!(
            "cargo:rustc-link-arg-bin={bin}={}",
            out.join(format!("lib{lib}.a")).display()
        );
    }
    for prefix in [&c, &m] {
        println!(
            "cargo:rustc-link-arg-bin={bin}=-L{}",
            prefix.join("lib").display()
        );
        println!(
            "cargo:rustc-link-arg-bin={bin}=-Wl,-rpath,{}",
            prefix.join("lib").display()
        );
    }
    for lib in ["mlxc", "mlx", "c++"] {
        println!("cargo:rustc-link-arg-bin={bin}=-l{lib}");
    }
    println!("cargo:rustc-cfg=pulsar_native_mlx");
}
