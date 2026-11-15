//! Core of PulsarMLX Console: the request model, the backend seam, the engine FIFO, the
//! turn driver and the run-config store.
//!
//! This crate is a skeleton. It depends on no HTTP, prompt or template crate, so every
//! engine implementation and every route can build on it. Nothing is implemented yet, so
//! nothing here may be described as working.
//!
//! Each module has one owning work package, which writes inside the module without editing
//! this file. Integration tests go in `tests/<package>_*.rs`, for example
//! `tests/eng09_fifo.rs`.

pub mod config;
pub mod digest;
pub mod engine;
pub mod fifo;
pub mod request;
pub mod sampling;
pub mod turn;
