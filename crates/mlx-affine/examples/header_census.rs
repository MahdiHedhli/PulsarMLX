//! A header-only census of a checkpoint that stays where it is.
//!
//! `Checkpoint::from_headers` builds the catalog from header bytes alone, so a
//! compatibility observation over a real checkpoint needs its headers and
//! nothing else: **no payload byte is read, and the checkpoint does not move.**
//! Reads are refused in that mode, which is what makes the claim checkable
//! rather than promised.
//!
//! This is an observation tool, not a gate. It runs by hand, against a
//! directory of extracted metadata that is never committed, and what it
//! produces is labelled a compatibility observation and not a qualification:
//! header compatibility is not Q0 payload identity and not numerical
//! qualification.
//!
//! Input directory layout, as `scripts/research/extract_safetensors_headers_v1.py`
//! writes it:
//!
//! ```text
//! <dir>/shards.json                  {"shards": [{ file, file_len, header_file, header_len, header_sha256 }]}
//! <dir>/headers/<shard>.header       the 8-byte prefix and the header JSON, verbatim
//! <dir>/config.json                  the checkpoint's configuration
//! <dir>/model.safetensors.index.json the shard index
//! ```
//!
//! ```text
//! cargo run -p mlx-affine --example header_census -- <dir> <output.json> [rules.json]
//! ```
//!
//! The census logic is `support/header_census_core.rs`, which has no file
//! access of its own; the only reader is `support/header_census_source.rs`,
//! which admits the four input kinds above by name and refuses a shard.
//! Categorization is caller-supplied: with no rules file the census still runs
//! and reports no groups. A name means nothing to this crate unless a caller
//! says what it means, and model-specific rules live outside `crates/`.

#[path = "support/header_census_core.rs"]
mod header_census_core;
#[path = "support/header_census_source.rs"]
mod header_census_source;

use std::path::PathBuf;

use header_census_core::{parse_rules, run};
use header_census_source::DirectorySource;
use serde_json::Value;

const USAGE: &str = "usage: header_census <dir> <output.json> [rules.json]";

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut arguments = std::env::args().skip(1);
    let directory = PathBuf::from(arguments.next().ok_or(USAGE)?);
    let output = PathBuf::from(arguments.next().ok_or(USAGE)?);
    let rules = match arguments.next() {
        None => Vec::new(),
        Some(path) => {
            let document: Value = serde_json::from_str(&std::fs::read_to_string(&path)?)?;
            parse_rules(&document)?
        }
    };
    if arguments.next().is_some() {
        return Err(USAGE.into());
    }

    let census = run(&DirectorySource::new(&directory), &rules)?;
    std::fs::write(
        &output,
        serde_json::to_string_pretty(&census.report)? + "\n",
    )?;
    let result = census.report["result"].as_str().unwrap_or("?");
    println!("header_census: {result}; wrote {}", output.display());
    Ok(())
}
