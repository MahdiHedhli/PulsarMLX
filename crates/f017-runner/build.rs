use std::process::Command;

fn main() {
    println!("cargo:rerun-if-changed=../../.git/HEAD");
    let sha = Command::new("git")
        .args(["rev-parse", "HEAD"])
        .output()
        .ok()
        .filter(|output| output.status.success())
        .and_then(|output| String::from_utf8(output.stdout).ok())
        .map(|value| value.trim().to_owned())
        .filter(|value| value.len() == 40 && value.bytes().all(|byte| byte.is_ascii_hexdigit()))
        .unwrap_or_else(|| "0000000000000000000000000000000000000000".to_owned());
    println!("cargo:rustc-env=PULSARMLX_SOURCE_SHA={sha}");
    let root = std::env::var("CARGO_MANIFEST_DIR")
        .map(|value| format!("{value}/../.."))
        .unwrap_or_default();
    println!("cargo:rustc-env=PULSARMLX_SOURCE_ROOT={root}");
}
