use std::process::Command;

fn main() {
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
