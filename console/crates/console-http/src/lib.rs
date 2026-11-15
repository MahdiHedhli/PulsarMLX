//! HTTP side of PulsarMLX Console: the HTTP/1.0 transport, the route table and guards, the
//! inference request lifecycle and the client dialects.
//!
//! This crate is a skeleton. Each module has one owning work package, which writes inside
//! the module without editing this file. Integration tests go in `tests/<package>_*.rs`,
//! for example `tests/api02_transport.rs`. Nothing is implemented yet, so nothing here may
//! be described as working.

pub mod dialect;
pub mod error;
pub mod guard;
pub mod inference;
pub mod router;
pub mod transport;
