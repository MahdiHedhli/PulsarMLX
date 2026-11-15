//! Owned by ENG-01. The backend seam of `contracts/backend-seam.md` (draft 0.2): engine
//! factory and instance, events, the event ledger, capabilities, facts, failures and the
//! synthetic-only guard.
//!
//! The token level is synchronous. An engine instance is created on, and owned by, one
//! driver thread and need not be `Send`; requests to cancel, pause or wrap reach it
//! through a [`ControlProbe`]. The request id is assigned by the server. Engines with
//! several places use the submit-and-pump form of [`MultiEngine`]; the blocking
//! [`EngineInstance::generate`] is the single-conversation case.
//!
//! Every engine behind this seam in this increment is synthetic, and
//! [`require_synthetic`] refuses any other. Nothing here is qualified beyond synthetic
//! backends.

mod control;
mod descriptor;
mod error;
mod event;
mod guard;
mod instance;
mod ledger;
mod multi;
mod pyparse;
mod request;
mod terminal;
mod text;

pub use control::{ControlHandle, ControlProbe, PauseRequest};
pub use descriptor::{
    DeclaredProvenance, EngineCaps, EngineDescriptor, EngineFacts, EngineKind, InfoMap,
    InfoRejected, InfoValue, LifecycleCaps, Provenance, SeamVersion, VisionCap,
    DECLARED_PROVENANCE_MAX_CHARS, INFO_MAX_ENTRIES, INFO_MAX_TEXT_BYTES, SEAM_VERSION,
};
pub use error::{EngineFailure, FailureKind};
pub use event::{
    CommittedToken, DeliveryRefused, EngineEvent, EngineSample, EventSink, PromptProgress,
    StatValue, TaggedSink, TokenLogprob, SAMPLE_MAX_ENTRIES, SAMPLE_MAX_TEXT_BYTES,
};
pub use guard::{require_synthetic, ProvenanceRefused, ALLOWING_NON_SYNTHETIC_ENGINES_PATH};
pub use instance::{
    generate_ledgered, AloneReason, ControlCommand, EngineFactory, EngineInstance,
    EngineStartConfig, Health, ShutdownOutcome,
};
pub use ledger::{Checked, EventLedger, LedgerCounts, LedgeredSink, Verdict};
pub use multi::{generate_one, Finished, LedgerSet, LedgeredTaggedSink, MultiEngine};
pub use pyparse::{py_float, py_int};
pub use request::{
    EmbeddingsKind, EmbeddingsRef, GenerationRequest, Penalties, RequestId, RestoreHints, Sampling,
    SoftClose, ThinkingHints, TuneKnobs, TuneValue, TUNE_MAX_KNOBS,
};
pub use terminal::{
    DoneFigures, EngineCounts, EngineStop, EngineTimings, Terminal, DONE_FINISH_MAX_BYTES,
};
pub use text::{BoundedText, MESSAGE_MAX_BYTES, NOTE_MAX_BYTES};
