//! Byte-level BPE tokenizer, byte tokenizer and incremental detokenizer for PulsarMLX
//! Console.
//!
//! Work package PRM-04 owns every module below and writes inside them without editing this
//! file; its integration tests go in `tests/prm04_*.rs`. The crate has no template
//! dependency, so the engine, media and HTTP crates can use it alone. It is tested with
//! synthetic vocabularies built in code and is qualified on synthetic inputs only; no real
//! model's tokenizer files are in the repository. Its departures from the donor in loading
//! and limits are proposal P-24 in the deviation register of feature 022.

pub mod bpe;
pub mod byte_map;
pub mod byte_tok;
pub mod detok;
pub mod pack_dir;
pub mod pretok;
pub mod special;
