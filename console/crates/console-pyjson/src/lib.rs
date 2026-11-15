//! Python-compatible JSON and string output for PulsarMLX Console.
//!
//! This crate is a skeleton. Work package API-01 will fill it with the one
//! writer that every wire body and every persisted file of PulsarMLX Console
//! goes through: JSON serialized byte for byte as Python's `json.dumps` writes
//! it (separators, key order, `ensure_ascii` escaping, float formatting and
//! non-finite numbers), together with the Python-compatible string helpers the
//! prompt pipeline needs. Byte equality matters because rendered prompt bytes
//! decide token ids, and because the adapted dashboard and existing clients
//! read these bodies.
//!
//! Nothing is implemented yet, so nothing here may be described as working.
//!
//! Every module below belongs to API-01, which writes inside it without editing this file.
//! Its integration tests go in `tests/api01_*.rs`.

pub mod dumps;
pub mod float_repr;
pub mod ids;
pub mod loads;
pub mod pystr;

#[cfg(test)]
mod tests {
    /// Keeps `cargo test` meaningful for the skeleton: the crate compiles, its
    /// test harness runs, and the package identity is the one the workspace
    /// and the parity documents name.
    #[test]
    fn skeleton_crate_has_the_expected_package_name() {
        assert_eq!(env!("CARGO_PKG_NAME"), "console-pyjson");
    }
}
