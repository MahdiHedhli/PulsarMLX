//! The independence of R1 from R3, checked statically against the source.
//!
//! The claim this file defends is narrow and mechanical: the binary64
//! reference must not be the production decoder in disguise, nor share a
//! helper with it, so that agreement between them is evidence rather than
//! tautology.

use std::path::PathBuf;

fn source(relative: &str) -> String {
    let path: PathBuf = [env!("CARGO_MANIFEST_DIR"), relative].iter().collect();
    std::fs::read_to_string(&path).unwrap_or_else(|error| panic!("{}: {error}", path.display()))
}

/// Source lines with `//` comments and doc comments removed, so that the
/// scanners below do not trip over prose that merely names the other module.
fn code_lines(text: &str) -> Vec<String> {
    text.lines()
        .map(|line| {
            let trimmed = line.trim_start();
            if trimmed.starts_with("//") {
                String::new()
            } else {
                match line.find("//") {
                    Some(at) => line[..at].to_string(),
                    None => line.to_string(),
                }
            }
        })
        .collect()
}

#[test]
fn the_reference_imports_nothing_at_all() {
    let text = source("src/reference.rs");
    for (number, line) in code_lines(&text).iter().enumerate() {
        let trimmed = line.trim_start();
        assert!(
            !trimmed.starts_with("use ") && !trimmed.starts_with("pub use "),
            "src/reference.rs:{}: the reference must have no use statements, found {trimmed:?}",
            number + 1
        );
    }
}

#[test]
fn the_reference_names_nothing_from_this_crate() {
    let text = source("src/reference.rs");
    let code = code_lines(&text).join("\n");
    for forbidden in ["crate::", "super::", "mlx_affine::", "safetensors_catalog"] {
        assert!(
            !code.contains(forbidden),
            "src/reference.rs must not name {forbidden:?}"
        );
    }
}

#[test]
fn the_reference_never_mentions_the_production_decoder() {
    let text = source("src/reference.rs");
    let code = code_lines(&text).join("\n");
    assert!(
        !code.contains("decode"),
        "src/reference.rs must not refer to the decode module in code"
    );
    assert!(
        !code.contains("QuantSpec") && !code.contains("ScaleDtype") && !code.contains("Bits"),
        "src/reference.rs must not use the production types"
    );
}

#[test]
fn the_production_decoder_never_calls_the_reference() {
    let text = source("src/decode.rs");
    let code = code_lines(&text).join("\n");
    assert!(
        !code.contains("reference"),
        "src/decode.rs must not refer to the reference module in code"
    );
}

#[test]
fn the_two_implementations_are_separate_files_of_real_size() {
    // A degenerate reference -- one that delegated, or that was a stub --
    // would satisfy the scanners above while proving nothing.
    let reference = source("src/reference.rs");
    let decode = source("src/decode.rs");
    assert!(
        reference.len() > 3000,
        "the reference is suspiciously short"
    );
    assert!(decode.len() > 3000, "the decoder is suspiciously short");
    assert!(reference.contains("fn extract_code"));
    assert!(decode.contains("fn unpack_codes"));
    // They do not even share a function name.
    let reference_fns: Vec<&str> = reference
        .lines()
        .filter_map(|line| line.trim_start().strip_prefix("pub fn "))
        .filter_map(|rest| rest.split('(').next())
        .collect();
    let decode_fns: Vec<&str> = decode
        .lines()
        .filter_map(|line| line.trim_start().strip_prefix("pub fn "))
        .filter_map(|rest| rest.split('(').next())
        .collect();
    for name in &reference_fns {
        assert!(
            !decode_fns.contains(name),
            "{name} is defined in both the reference and the decoder"
        );
    }
    assert!(reference_fns.len() >= 6, "{reference_fns:?}");
    assert!(decode_fns.len() >= 3, "{decode_fns:?}");
}

#[test]
fn the_python_reference_declares_its_authoring_order_and_stays_stdlib() {
    let path: PathBuf = [
        env!("CARGO_MANIFEST_DIR"),
        "../../scripts/research/mlx_affine_reference_v1.py",
    ]
    .iter()
    .collect();
    let text = std::fs::read_to_string(&path).unwrap();
    assert!(text.contains("was written **first**"));
    for forbidden in [
        "import mlx",
        "from mlx",
        "import numpy",
        "subprocess",
        "ctypes",
    ] {
        assert!(
            !text.contains(forbidden),
            "the Python R1 must not use {forbidden}"
        );
    }
}
