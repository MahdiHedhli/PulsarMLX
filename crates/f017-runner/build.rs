use std::process::Command;

fn main() {
    println!("cargo:rustc-check-cfg=cfg(pulsar_native_mlx)");
    println!("cargo:rerun-if-env-changed=PULSAR_REQUIRE_NATIVE_MLX");
    println!("cargo:rerun-if-env-changed=MLX_C_PREFIX");
    println!("cargo:rerun-if-env-changed=MLX_PREFIX");
    configure_native_mlx_cfg();
    for name in ["HEAD", "index"] {
        if let Some(path) = git_output(&["rev-parse", "--git-path", name]) {
            println!("cargo:rerun-if-changed={path}");
        }
    }
    let sha = git_output(&["rev-parse", "HEAD"])
        .filter(|value| value.len() == 40 && value.bytes().all(|byte| byte.is_ascii_hexdigit()))
        .unwrap_or_else(|| "0000000000000000000000000000000000000000".to_owned());
    println!("cargo:rustc-env=PULSARMLX_SOURCE_SHA={sha}");
    let root = std::env::var("CARGO_MANIFEST_DIR")
        .map(|value| format!("{value}/../.."))
        .unwrap_or_default();
    println!("cargo:rustc-env=PULSARMLX_SOURCE_ROOT={root}");
}

fn configure_native_mlx_cfg() {
    let required = std::env::var("PULSAR_REQUIRE_NATIVE_MLX").as_deref() == Ok("1");
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() != Ok("macos") {
        if required {
            panic!("PULSAR_REQUIRE_NATIVE_MLX=1 requires a macOS target");
        }
        return;
    }
    let mlx_c_prefix = std::env::var("MLX_C_PREFIX")
        .map(std::path::PathBuf::from)
        .unwrap_or_else(|_| std::path::PathBuf::from("/opt/homebrew/opt/mlx-c"));
    let mlx_prefix = std::env::var("MLX_PREFIX")
        .map(std::path::PathBuf::from)
        .unwrap_or_else(|_| std::path::PathBuf::from("/opt/homebrew/opt/mlx"));
    let available = mlx_c_prefix.join("include/mlx/c/mlx.h").is_file()
        && mlx_c_prefix.join("lib/libmlxc.dylib").is_file()
        && mlx_prefix.join("lib/libmlx.dylib").is_file();
    if available {
        println!("cargo:rustc-cfg=pulsar_native_mlx");
    } else if required {
        panic!("PULSAR_REQUIRE_NATIVE_MLX=1 but pinned native MLX artifacts are unavailable");
    }
}

fn git_output(arguments: &[&str]) -> Option<String> {
    Command::new("git")
        .args(arguments)
        .output()
        .ok()
        .filter(|output| output.status.success())
        .and_then(|output| String::from_utf8(output.stdout).ok())
        .map(|value| value.trim().to_owned())
        .filter(|value| !value.is_empty())
}
