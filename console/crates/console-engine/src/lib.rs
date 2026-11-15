//! Engine implementations behind the PulsarMLX Console backend seam.
//!
//! In this increment every engine is synthetic: no real model is served and no donor
//! engine binary is launched. Work package ENG-02 owns the `fake` module (the scripted
//! engine and the test doubles) and writes inside it without editing this file; its
//! integration tests go in `tests/eng02_*.rs`. Later engine packages add their own modules
//! here. A module that still holds only its header comment is not
//! implemented; `tasks.md` of feature 022 records which packages are done. Nothing here may
//! be described as more than qualified on synthetic backends.

pub mod fake;
