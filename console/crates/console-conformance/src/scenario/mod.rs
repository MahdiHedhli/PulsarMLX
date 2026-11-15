//! Owned by CNF-02. The scenario format, its schema check, the loader, substitution tokens
//! and the rename map.
//!
//! A scenario is one JSON file that says, once, how a conformance case is run against
//! either target: which synthetic engine sits behind the server (the in-process scripted
//! engine or a line-protocol fake), which chat template, how the server is started, the
//! steps the harness takes (requests, disconnects, engine gates, concurrent groups,
//! signals) and what it records. The format is documented by
//! `specs/022-console-serving-parity/contracts/conformance-scenario.schema.json` and
//! enforced in code here (binding decision B6: the schema check is written in-house; the
//! member table in [`schema`] is checked against the schema file by a test).
//!
//! Loading is strict. Every error carries a JSON pointer to the value at fault: a
//! repeated key, an unknown member, a missing member, a wrong type, a value out of range,
//! an oversize document or list, an undefined substitution token. Every size is bounded
//! (see [`limits`]).
//!
//! The companion contracts read here are the rename map ([`RenameMap`]), derived from
//! `contracts/naming.md` and applied by the comparator to the reference side, and the
//! volatile-field list ([`VolatileFields`]), the field-by-field form of the rule in
//! `contracts/parity-ledger.md` section 1.1.
//!
//! Nothing here runs a server or an engine. A scenario describes a case on synthetic
//! engines only; no scenario can name an engine that is not one of the synthetic ones.

mod error;
mod json;
mod model;
mod rename;
pub mod schema;
mod subst;
mod template;
mod tokenizer;
mod volatile;

#[cfg(test)]
mod tests;

use std::fs;
use std::io::Read;
use std::path::Path;

pub use error::{ErrorKind, Result, ScenarioError};
pub use model::{
    is_abbreviation_of, is_reserved_env, limits, Body, DataFile, Disconnect, EngineSpec,
    HttpVersion, LineEngineSpec, LineFake, MockEngineSpec, Observe, Request, Scenario, ServerSpec,
    Signal, Step, StructuredRequest, HARNESS_CONFIG_KEYS, HARNESS_FLAGS, HOST_CONFIG_KEY,
    HOST_FLAG, LOOPBACK_TOKEN, MOCK_DEFAULT_MAX_CONTEXT, RESERVED_ENV, RESERVED_ENV_PREFIXES,
};
pub use rename::{
    Exclusion, Match, NamingRef, RenameEntry, RenameMap, Status, MAX_PATTERN_TEXT_BYTES,
    MAX_RENAME_MAP_BYTES, SCOPES,
};
pub use subst::{Substitutions, KEY_SHORT_MAX_CHARS, TOKENS};
pub use template::{
    vendor_dir_from_env, TemplateError, TemplateRef, VendorResolution, VendorTemplate,
    MAX_TEMPLATE_BYTES, VENDOR_DIR_ENV,
};
pub use tokenizer::{
    byte_level_chars, TokenizerSpec, BPE_MERGES_TEXT, BYTE_EOS_ID, BYTE_SPECIALS, FIRST_SPECIAL_ID,
};
pub use volatile::{Location, VolatileClass, VolatileField, VolatileFields, MAX_VOLATILE_BYTES};

impl Scenario {
    /// Reads and checks a scenario from its JSON text. Substitution tokens stay as
    /// written; see [`Scenario::expand`].
    pub fn from_json_str(text: &str) -> Result<Self> {
        let value = json::parse_strict(text, limits::MAX_SCENARIO_BYTES)?;
        model::scenario_from_value(&value, model::LOOPBACK_TOKEN)
    }

    /// Reads and checks a scenario file, and requires its file stem to equal its `id`.
    /// The file is read up to [`limits::MAX_SCENARIO_BYTES`] plus one byte, so an
    /// oversize file is refused without being read whole.
    pub fn from_path(path: &Path) -> Result<Self> {
        let text = read_bounded(path, limits::MAX_SCENARIO_BYTES)?;
        let scenario = Self::from_json_str(&text)?;
        let stem = path
            .file_stem()
            .map(|s| s.to_string_lossy().into_owned())
            .unwrap_or_default();
        if stem != scenario.id {
            return Err(ScenarioError::new(
                "/id",
                ErrorKind::IdMismatch { file_stem: stem },
            ));
        }
        Ok(scenario)
    }

    /// A copy with every substitution token expanded from `subs`, checked against the
    /// format again. Fails with [`ErrorKind::UnboundToken`] at the first string that uses
    /// a token `subs` has no value for.
    pub fn expand(&self, subs: &Substitutions) -> Result<Self> {
        let expanded = subs.expand_value(&self.source, "")?;
        let bind = subs
            .value("loopback")
            .unwrap_or_else(|| model::LOOPBACK_TOKEN.to_string());
        model::scenario_from_value(&expanded, &bind)
    }

    /// The document as read (tokens unexpanded).
    pub fn source(&self) -> &serde_json::Value {
        &self.source
    }
}

/// Reads `path` as UTF-8 text of at most `limit` bytes.
pub(crate) fn read_bounded(path: &Path, limit: usize) -> Result<String> {
    let io = |e: std::io::Error| {
        ScenarioError::new(
            "",
            ErrorKind::Io {
                message: e.to_string(),
            },
        )
    };
    let file = fs::File::open(path).map_err(io)?;
    let mut buf = Vec::new();
    let cap = u64::try_from(limit).unwrap_or(u64::MAX).saturating_add(1);
    file.take(cap).read_to_end(&mut buf).map_err(io)?;
    if buf.len() > limit {
        return Err(ScenarioError::new("", ErrorKind::TooLarge { limit }));
    }
    String::from_utf8(buf).map_err(|e| {
        ScenarioError::new(
            "",
            ErrorKind::Io {
                message: format!("not UTF-8: {e}"),
            },
        )
    })
}

/// Reads and checks the rename map file at `path`.
pub fn load_rename_map(path: &Path) -> Result<RenameMap> {
    RenameMap::from_json_str(&read_bounded(path, MAX_RENAME_MAP_BYTES)?)
}

/// Reads and checks the volatile-field file at `path`.
pub fn load_volatile_fields(path: &Path) -> Result<VolatileFields> {
    VolatileFields::from_json_str(&read_bounded(path, MAX_VOLATILE_BYTES)?)
}
