fn main() {
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() != Ok("macos") {
        return;
    }

    println!("cargo:rerun-if-changed=src/apple_metal_bridge.mm");
    cc::Build::new()
        .cpp(true)
        .file("src/apple_metal_bridge.mm")
        .flag("-std=c++17")
        .flag("-fobjc-arc")
        .compile("pulsar_metal_bridge");
    println!("cargo:rustc-link-lib=framework=Foundation");
    println!("cargo:rustc-link-lib=framework=Metal");
}
