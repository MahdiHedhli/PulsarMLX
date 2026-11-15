//! Conformance harness for PulsarMLX Console. Test only: it is never linked into the
//! product binary, and it depends on no other console crate, so it observes the server
//! only from outside.
//!
//! This crate is a skeleton created for CNF-01, which owns the `cnf` binary in
//! `src/bin/cnf.rs`. Each module below has one owning work package, which writes inside
//! the module without editing this file. Integration tests go in `tests/<package>_*.rs`,
//! for example `tests/cnf03_client.rs`. Nothing is implemented yet, so nothing here may be
//! described as working.

pub mod client;
pub mod compare;
pub mod normalize;
pub mod observe;
pub mod process;
pub mod scenario;
