//! HTTP test kit for PulsarMLX Console. Test only: it is never linked into the product
//! binary.
//!
//! Work package API-19 owns every module below and writes inside them without editing this
//! file; its own integration tests go in `tests/api19_*.rs`. The kit holds a raw socket
//! client, an SSE reader, an in-process test server over the transport, the router and the
//! scripted engine, engine helpers, a process helper and a ledger helper. The process helper
//! is proven against shell scripts only until the server binary and the fake engine binaries
//! exist. PRM-02 extends the kit in M2.

pub mod engines;
pub mod ledger;
pub mod process;
pub mod raw;
pub mod server;
pub mod sse;
