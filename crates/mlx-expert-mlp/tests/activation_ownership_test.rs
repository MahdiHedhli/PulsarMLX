#[cfg(all(target_os = "macos", target_arch = "aarch64"))]
#[test]
fn activation_result_slots_and_error_cleanup_with_no_mlx_linkage() {
    use std::{path::PathBuf, process::Command};
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let stamp = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let out = std::env::temp_dir().join(format!(
        "pulsar-mlp-ownership-{}-{stamp}",
        std::process::id()
    ));
    std::fs::create_dir(&out).unwrap();
    let binary = out.join("ownership-stub");
    let compile = Command::new("clang++")
        .args([
            "-std=c++17",
            "-fno-fast-math",
            "-ffp-contract=off",
            "-Wall",
            "-Werror",
        ])
        .arg("-I")
        .arg(root.join("tests/native_stub"))
        .arg("-I")
        .arg(root.join("../../scripts/research"))
        .arg(root.join("src/activation.cpp"))
        .arg(root.join("tests/activation_ownership_stub.cpp"))
        .arg("-o")
        .arg(&binary)
        .output()
        .unwrap();
    assert!(
        compile.status.success(),
        "{}",
        String::from_utf8_lossy(&compile.stderr)
    );
    let result = Command::new(&binary).output().unwrap();
    assert!(
        result.status.success(),
        "stub failed: {} {}",
        String::from_utf8_lossy(&result.stdout),
        String::from_utf8_lossy(&result.stderr)
    );
    assert!(String::from_utf8_lossy(&result.stdout).contains("HOST_STUB_OWNERSHIP_PASS"));
    let linked = Command::new("otool")
        .arg("-L")
        .arg(&binary)
        .output()
        .unwrap();
    assert!(linked.status.success());
    assert!(!String::from_utf8_lossy(&linked.stdout).contains("libmlx"));
}
