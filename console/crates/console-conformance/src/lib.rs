//! Conformance harness for PulsarMLX Console. Test only: it is never linked into the
//! product binary, and it depends on no other console crate, so it observes the server
//! only from outside.
//!
//! CNF-01 owns the `cnf` binary in `src/bin/cnf.rs`. Each module below has one owning work
//! package, which writes inside the module without editing this file. Integration tests go
//! in `tests/<package>_*.rs`, for example `tests/cnf03_client.rs`. A module that still holds only its header comment is not
//! implemented; `tasks.md` of feature 022 records which packages are done. Nothing here may
//! be described as more than qualified on synthetic backends.

pub mod client;
pub mod compare;
pub mod normalize;
pub mod observe;
pub mod process;
pub mod scenario;
