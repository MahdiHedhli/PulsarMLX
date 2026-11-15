//! HTTP test kit for PulsarMLX Console. Test only: it is never linked into the product
//! binary.
//!
//! This crate is a skeleton. Work package API-19 owns every module below and writes
//! inside them without editing this file; its own integration tests go in
//! `tests/api19_*.rs`. PRM-02 extends the kit in M2. Nothing is implemented yet, so
//! nothing here may be described as working.

pub mod engines;
pub mod ledger;
pub mod process;
pub mod raw;
pub mod server;
pub mod sse;
