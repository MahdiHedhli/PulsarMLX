//! Byte-level BPE tokenizer, byte tokenizer and incremental detokenizer for PulsarMLX
//! Console.
//!
//! This crate is a skeleton. Work package PRM-04 owns every module below and writes inside
//! them without editing this file; its integration tests go in `tests/prm04_*.rs`. The
//! crate has no template dependency, so the engine, media and HTTP crates can use it alone.
//! Nothing is implemented yet, so nothing here may be described as working.

pub mod bpe;
pub mod byte_map;
pub mod byte_tok;
pub mod detok;
pub mod pack_dir;
pub mod pretok;
pub mod special;
