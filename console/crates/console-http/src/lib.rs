//! HTTP side of PulsarMLX Console: the HTTP/1.0 transport, the route table and guards, the
//! inference request lifecycle and the client dialects.
//!
//! Each module has one owning work package, which writes inside the module without editing
//! this file. Integration tests go in `tests/<package>_*.rs`, for example
//! `tests/api02_transport.rs`. A module that still holds only its header comment is not
//! implemented; `tasks.md` of feature 022 records which packages are done. Nothing here may
//! be described as more than qualified on synthetic backends.

pub mod dialect;
pub mod error;
pub mod guard;
pub mod inference;
pub mod router;
pub mod transport;
