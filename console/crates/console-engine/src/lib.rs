//! Engine implementations behind the PulsarMLX Console backend seam.
//!
//! This crate is a skeleton. In this increment every engine is synthetic: no real model
//! is served and no donor engine binary is launched. Work package ENG-02 owns the `fake`
//! module and writes inside it without editing this file; its integration tests go in
//! `tests/eng02_*.rs`. Later engine packages add their own modules here. Nothing is
//! implemented yet, so nothing here may be described as working.

pub mod fake;
