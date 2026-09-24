//! Build script for the F020 Slice 2B native primitives.
//!
//! Modelled on `crates/f017-native/build.rs`, with two deliberate
//! differences:
//!
//! * there is no Homebrew fallback. The only admitted native library is the
//!   pinned MLX / MLX-C prefix built by `scripts/ci/install_native_mlx.sh`,
//!   named explicitly through `MLX_C_PREFIX` and `MLX_PREFIX`;
//! * MLX is linked into the `qualify` binary only. The library and every test
//!   binary of this package stay free of MLX, so the parent harness never
//!   loads the library it qualifies.
//!
//! `src/abi_check.c` is compiled against the pinned headers; its
//! `_Static_assert`s pin the C-side layout and enumerator values that the
//! hand-written Rust FFI assumes, and its exported function reports the same
//! values at run time so the child can compare them before its first MLX-C
//! call.

use std::path::PathBuf;
use std::process::Command;

fn main() {
    println!("cargo:rustc-check-cfg=cfg(pulsar_native_mlx)");
    println!("cargo:rerun-if-env-changed=PULSAR_REQUIRE_NATIVE_MLX");
    println!("cargo:rerun-if-env-changed=MLX_C_PREFIX");
    println!("cargo:rerun-if-env-changed=MLX_PREFIX");
    println!("cargo:rerun-if-changed=src/abi_check.c");

    let rustc = std::env::var("RUSTC").unwrap_or_else(|_| "rustc".into());
    let rustc_version = Command::new(&rustc)
        .arg("-V")
        .output()
        .ok()
        .and_then(|o| String::from_utf8(o.stdout).ok())
        .map(|s| s.trim().to_string())
        .unwrap_or_else(|| "unknown".into());
    println!("cargo:rustc-env=F020_RUSTC_VERSION={rustc_version}");
    let profile = std::env::var("PROFILE").unwrap_or_else(|_| "unknown".into());
    println!("cargo:rustc-env=F020_BUILD_PROFILE={profile}");

    let require = std::env::var("PULSAR_REQUIRE_NATIVE_MLX").as_deref() == Ok("1");
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() != Ok("macos") {
        if require {
            panic!("PULSAR_REQUIRE_NATIVE_MLX=1 requires a macOS target");
        }
        return;
    }

    let prefixes = (std::env::var("MLX_C_PREFIX"), std::env::var("MLX_PREFIX"));
    let (mlx_c, mlx) = match prefixes {
        (Ok(c), Ok(m)) => (PathBuf::from(c), PathBuf::from(m)),
        _ => {
            let detail = "MLX_C_PREFIX and MLX_PREFIX must both name the pinned native prefix";
            if require {
                panic!("PULSAR_REQUIRE_NATIVE_MLX=1 but {detail}");
            }
            println!("cargo:warning={detail}; the qualify binary is built without MLX and refuses to run");
            return;
        }
    };
    let header = mlx_c.join("include/mlx/c/mlx.h");
    let libmlxc = mlx_c.join("lib/libmlxc.dylib");
    let libmlx = mlx.join("lib/libmlx.dylib");
    if !(header.is_file() && libmlxc.is_file() && libmlx.is_file()) {
        let detail = format!(
            "pinned native MLX unavailable: header={}, mlxc={}, mlx={}",
            header.display(),
            libmlxc.display(),
            libmlx.display()
        );
        if require {
            panic!("PULSAR_REQUIRE_NATIVE_MLX=1 but {detail}");
        }
        println!(
            "cargo:warning={detail}; the qualify binary is built without MLX and refuses to run"
        );
        return;
    }

    cc::Build::new()
        .file("src/abi_check.c")
        .include(mlx_c.join("include"))
        .flag("-std=c11")
        .flag("-Wall")
        .flag("-Werror")
        .cargo_metadata(false)
        .compile("f020_abi_check");
    let out = PathBuf::from(std::env::var("OUT_DIR").expect("OUT_DIR"));

    println!("cargo:rustc-cfg=pulsar_native_mlx");
    let bin = "qualify";
    println!(
        "cargo:rustc-link-arg-bin={bin}={}",
        out.join("libf020_abi_check.a").display()
    );
    println!(
        "cargo:rustc-link-arg-bin={bin}=-L{}",
        mlx_c.join("lib").display()
    );
    println!(
        "cargo:rustc-link-arg-bin={bin}=-L{}",
        mlx.join("lib").display()
    );
    println!("cargo:rustc-link-arg-bin={bin}=-lmlxc");
    println!("cargo:rustc-link-arg-bin={bin}=-lmlx");
    println!(
        "cargo:rustc-link-arg-bin={bin}=-Wl,-rpath,{}",
        mlx_c.join("lib").display()
    );
    if mlx != mlx_c {
        println!(
            "cargo:rustc-link-arg-bin={bin}=-Wl,-rpath,{}",
            mlx.join("lib").display()
        );
    }
}
