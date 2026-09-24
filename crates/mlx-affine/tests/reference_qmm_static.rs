//! Static independence of the Slice 2B R1 (contract B5: "static independence of
//! the Rust R1 extension from decode.rs and MLX"), checked against the source
//! text rather than promised.

use std::path::PathBuf;

fn read(relative: &str) -> String {
    let path: PathBuf = [env!("CARGO_MANIFEST_DIR"), relative].iter().collect();
    std::fs::read_to_string(&path).unwrap_or_else(|error| panic!("{}: {error}", path.display()))
}

/// Lines with `//` comments (including doc comments) removed.
fn code_only(text: &str) -> String {
    text.lines()
        .map(|line| match line.find("//") {
            Some(at) => &line[..at],
            None => line,
        })
        .collect::<Vec<_>>()
        .join("\n")
}

#[test]
fn reference_qmm_has_no_use_statement() {
    let text = read("src/reference_qmm.rs");
    for (number, line) in text.lines().enumerate() {
        let trimmed = line.trim_start();
        for prefix in ["use ", "pub use ", "pub(crate) use ", "pub(super) use "] {
            assert!(
                !trimmed.starts_with(prefix),
                "src/reference_qmm.rs:{}: a use statement: {trimmed:?}",
                number + 1
            );
        }
    }
}

#[test]
fn reference_qmm_never_mentions_decode_anywhere() {
    // Stricter than code-only: not even a comment may name it.
    let text = read("src/reference_qmm.rs").to_lowercase();
    assert!(
        !text.contains("decode"),
        "src/reference_qmm.rs must not contain the word decode"
    );
}

#[test]
fn reference_qmm_names_nothing_outside_itself_and_std() {
    // The file's own error type is QmmReferenceError; any other *ReferenceError
    // would be the Slice 1 reference's.
    let code = code_only(&read("src/reference_qmm.rs")).replace("QmmReferenceError", "");
    for forbidden in [
        "crate::",
        "super::",
        "self::",
        "mlx_affine",
        "safetensors",
        "reference::",
        "spec::",
        "module::",
        "extern",
        "unsafe",
        "mlx_",
        "#[link",
        "include!",
        "Command",
        "QuantSpec",
        "ScaleDtype",
        "AffineError",
        "MetadataFormat",
        "ReferenceError",
    ] {
        assert!(
            !code.contains(forbidden),
            "src/reference_qmm.rs must not name {forbidden:?}"
        );
    }
}

#[test]
fn nothing_else_in_the_crate_calls_reference_qmm() {
    // R1 must not become part of the production path: only lib.rs declares it.
    for file in [
        "src/decode.rs",
        "src/error.rs",
        "src/module.rs",
        "src/reference.rs",
        "src/spec.rs",
    ] {
        let code = code_only(&read(file));
        assert!(
            !code.contains("reference_qmm"),
            "{file} must not refer to reference_qmm"
        );
    }
    let lib = code_only(&read("src/lib.rs"));
    let mentions: Vec<&str> = lib
        .lines()
        .filter(|line| line.contains("reference_qmm"))
        .collect();
    assert_eq!(mentions, vec!["pub mod reference_qmm;"]);
}

#[test]
fn reference_qmm_is_a_real_implementation() {
    let text = read("src/reference_qmm.rs");
    assert!(text.len() > 6000, "the reference is suspiciously short");
    for needle in [
        "pub fn qmm_reference(",
        "pub fn dq_reference(",
        "fn packed_code(",
        "sum += w_row[t] * x_row[t];",
        "envelope += a_row[t] * x_row[t].abs();",
        "w.push(s * q + b);",
        "a.push(s.abs() * q + b.abs());",
    ] {
        assert!(text.contains(needle), "missing {needle:?}");
    }
    // No fused multiply-add anywhere: the contract's operation order is fl(fl(a*b) + c).
    assert!(!code_only(&text).contains("mul_add"));
}

#[test]
fn the_python_exact_reference_stays_stdlib_and_independent() {
    let text = read("../../scripts/research/mlx_affine_qmm_reference_v1.py");
    let imports: Vec<&str> = text
        .lines()
        .filter(|line| line.starts_with("import ") || line.starts_with("from "))
        .collect();
    assert_eq!(
        imports,
        vec![
            "from __future__ import annotations",
            "import argparse",
            "import hashlib",
            "import json",
            "import operator",
            "import struct",
            "import sys",
            "from fractions import Fraction",
            "from pathlib import Path",
        ]
    );
    for forbidden in [
        "import mlx",
        "numpy",
        "subprocess",
        "ctypes",
        "importlib",
        "f020_native_primitives_fixtures_v1",
        "mlx_affine_reference_v1",
    ] {
        assert!(
            !text.contains(forbidden),
            "the exact Python R1 must not use {forbidden}"
        );
    }
}
