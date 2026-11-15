//! The synthetic-only guard (contract section 5.1; owner decision of 2026-11-14 on
//! OPEN-29, carried out by lead decision LD28).
//!
//! [`require_synthetic`] is the single function that decides whether an engine may be
//! admitted. It reads nothing but the descriptor: no environment variable, configuration
//! key, command-line flag or Cargo feature changes its answer. What must be done before
//! any other engine may be admitted is written in
//! `docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md`; the tests that pin this guard must
//! not be deleted or weakened to make a real engine start (section 5.1, rule 5).

use std::fmt;

use super::descriptor::{EngineDescriptor, EngineKind, Provenance};
use super::error::{EngineFailure, FailureKind};
use super::text::BoundedText;

/// The repository path every refusal names.
pub const ALLOWING_NON_SYNTHETIC_ENGINES_PATH: &str =
    "docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md";

/// An engine refused by [`require_synthetic`]. Its `Display` is the one refusal line of
/// section 5.1, rule 3, which names the engine kind, what the engine reported, and
/// [`ALLOWING_NON_SYNTHETIC_ENGINES_PATH`].
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProvenanceRefused {
    /// The engine kind, named in the refusal line.
    pub kind: EngineKind,
    /// What the engine reported, named in the refusal line.
    pub reported: Provenance,
}

impl ProvenanceRefused {
    /// The refusal as an engine failure for a restart, model switch or context reload:
    /// kind [`FailureKind::StartFailed`], poisoned, carrying the same line as the
    /// process-start refusal.
    pub fn to_failure(&self) -> EngineFailure {
        EngineFailure {
            kind: FailureKind::StartFailed,
            message: BoundedText::message(&self.to_string()),
            poisoned: true,
            after_tokens: 0,
        }
    }
}

impl fmt::Display for ProvenanceRefused {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "[console] refusing to start: engine {} reports provenance {}; this build serves \
             synthetic engines only. See {}",
            self.kind, self.reported, ALLOWING_NON_SYNTHETIC_ENGINES_PATH
        )
    }
}

impl std::error::Error for ProvenanceRefused {}

/// The single synthetic-only guard: `Ok(())` only for [`Provenance::Synthetic`], and a
/// [`ProvenanceRefused`] for every other value, including an engine that declared no
/// provenance. Every path that admits an engine (first start, restart, model switch,
/// context reload) calls it before the engine serves a request (ENG-10, API-08).
pub fn require_synthetic(d: &EngineDescriptor) -> Result<(), ProvenanceRefused> {
    match &d.provenance {
        Provenance::Synthetic => Ok(()),
        other => Err(ProvenanceRefused {
            kind: d.kind,
            reported: other.clone(),
        }),
    }
}
