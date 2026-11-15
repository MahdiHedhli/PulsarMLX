//! Python-compatible JSON and string output for PulsarMLX Console.
//!
//! Work package API-01 provides the one writer that every wire body and every
//! persisted file of PulsarMLX Console goes through: JSON serialized byte for
//! byte as Python's `json.dumps` writes it (separators, key order,
//! `ensure_ascii` escaping, float formatting and non-finite numbers). It also
//! provides a reader that follows `json.loads`, Python's float `repr`, the
//! Python-compatible string helpers the prompt pipeline needs, and ids drawn
//! from operating-system randomness. Byte equality matters because rendered
//! prompt bytes decide token ids, and because the adapted dashboard and
//! existing clients read these bodies.
//!
//! The crate is checked against tables recorded from CPython and is qualified
//! on synthetic inputs only. Two refusals of the reader differ from
//! `json.loads` and await the owner's decision: proposals P-19 and P-20 in the
//! deviation register of feature 022.
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
    /// The package identity is the one the workspace and the parity documents
    /// name.
    #[test]
    fn skeleton_crate_has_the_expected_package_name() {
        assert_eq!(env!("CARGO_PKG_NAME"), "console-pyjson");
    }
}
