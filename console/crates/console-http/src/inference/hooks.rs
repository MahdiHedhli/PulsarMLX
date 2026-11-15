//! The seams of the lifecycle driver to later milestones, each a small trait with the M1
//! behavior as its default (R13):
//!
//! - [`ReloadState`]: a context reload is waiting or running (ENG-12, M3). Default
//!   [`NeverReloading`].
//! - [`UpdaterState`]: the updater is busy (OPS-22, M7). Default [`NoUpdater`]; under
//!   deviation SEC-5 the update contract only notifies, so a busy updater is not expected
//!   in this increment, but the gate is kept.
//! - [`Attachments`]: the attachment planner's `expand_request` (RSP-16, M6). Default
//!   [`NoAttachments`], which leaves the request as it is.
//!
//! The prompt packages of M2 meet the driver elsewhere: PRM-11 through
//! [`Dialect::prepare`](super::Dialect::prepare) and the P-8 mapping point
//! [`PromptFailure`](super::PromptFailure), PRM-12 through
//! [`DialectTurn::token`](super::DialectTurn::token).
//!
//! Behavior reference: project-maya serve/server.py:6255-6274 at 7e68a30f.

use std::sync::Arc;

use serde_json::{Map, Value};

use super::error::InferenceError;
use crate::error::OVERLOADED_RELOADING;

/// The message of the overloaded answer while the updater is busy. The donor's text names
/// the donor product; the product wording replaces it (BRAND-1, contracts/naming.md section
/// 3.8: rename decided, value proposed by API-07).
///
/// Behavior reference: project-maya serve/server.py:6258 at 7e68a30f.
pub const OVERLOADED_UPDATING: &str =
    "PulsarMLX Console is updating and starts again in a few minutes";

/// Whether a context reload is waiting or running (the donor's `svc.reloading()`).
/// Implemented by the engine host of ENG-12.
pub trait ReloadState: Send + Sync + 'static {
    /// True while a context reload waits for its turn or runs.
    fn reloading(&self) -> bool;
}

/// The M1 reload state: no reload ever runs.
#[derive(Debug, Clone, Copy, Default)]
pub struct NeverReloading;

impl ReloadState for NeverReloading {
    fn reloading(&self) -> bool {
        false
    }
}

/// Whether the updater is busy (the donor's `svc.updater.busy()`). Implemented by OPS-22.
pub trait UpdaterState: Send + Sync + 'static {
    /// True while an update runs.
    fn busy(&self) -> bool;
}

/// The M1 updater: never busy.
#[derive(Debug, Clone, Copy, Default)]
pub struct NoUpdater;

impl UpdaterState for NoUpdater {
    fn busy(&self) -> bool {
        false
    }
}

/// The dialect a request's file parts are read in (the donor's `"openai"`, `"responses"`
/// and `"anthropic"`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AttachDialect {
    /// OpenAI Chat Completions (`file` parts).
    OpenAi,
    /// The Responses API (`input_file` parts).
    Responses,
    /// Anthropic messages (`document` blocks).
    Anthropic,
}

impl AttachDialect {
    /// The donor's name for it.
    pub fn as_str(self) -> &'static str {
        match self {
            AttachDialect::OpenAi => "openai",
            AttachDialect::Responses => "responses",
            AttachDialect::Anthropic => "anthropic",
        }
    }
}

/// The arguments of one `expand_request` call, as the donor passes them.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AttachCall {
    /// The request's dialect.
    pub dialect: AttachDialect,
    /// A vision encoder is loaded (`svc.vision is not None`).
    pub want_images: bool,
    /// The largest text file, from the engine's context
    /// ([`text_file_limit`](console_core::request::text_file_limit)).
    pub text_limit: i64,
    /// The model's words for a text-only model (`svc.text_only()`), passed only when set.
    pub text_only: Option<String>,
}

/// The attachment planner: turns a request's file parts into text, or a scanned PDF's
/// pages into pictures, before the dialect reads its messages. Implemented by RSP-16.
pub trait Attachments: Send + Sync + 'static {
    /// Whether a vision encoder is loaded (the donor's `svc.vision is not None`).
    fn want_images(&self) -> bool {
        false
    }

    /// The model's words for a text-only model, if it is one (the donor's
    /// `svc.text_only()`).
    fn text_only(&self) -> Option<String> {
        None
    }

    /// Expands the request's file parts in place. An error is answered as its class.
    fn expand_request(
        &self,
        req: &mut Map<String, Value>,
        call: &AttachCall,
    ) -> Result<(), InferenceError>;
}

/// The M1 attachment planner: leaves every request as it is.
#[derive(Debug, Clone, Copy, Default)]
pub struct NoAttachments;

impl Attachments for NoAttachments {
    fn expand_request(
        &self,
        _req: &mut Map<String, Value>,
        _call: &AttachCall,
    ) -> Result<(), InferenceError> {
        Ok(())
    }
}

/// The driver's seams, each with its M1 default.
#[derive(Clone)]
pub struct InferenceHooks {
    /// ENG-12's reload state.
    pub reload: Arc<dyn ReloadState>,
    /// OPS-22's updater.
    pub updater: Arc<dyn UpdaterState>,
    /// RSP-16's attachment planner.
    pub attachments: Arc<dyn Attachments>,
}

impl Default for InferenceHooks {
    fn default() -> Self {
        Self {
            reload: Arc::new(NeverReloading),
            updater: Arc::new(NoUpdater),
            attachments: Arc::new(NoAttachments),
        }
    }
}

impl std::fmt::Debug for InferenceHooks {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("InferenceHooks")
            .field("reloading", &self.reload.reloading())
            .field("updater_busy", &self.updater.busy())
            .finish_non_exhaustive()
    }
}

impl InferenceHooks {
    /// The overloaded message for a chat route now, if one applies: the updater first,
    /// then a context reload, in the donor's order.
    ///
    /// Behavior reference: project-maya serve/server.py:6255-6259 at 7e68a30f.
    pub fn overloaded_message(&self) -> Option<&'static str> {
        let busy = self.updater.busy();
        if busy || self.reload.reloading() {
            Some(if busy {
                OVERLOADED_UPDATING
            } else {
                OVERLOADED_RELOADING
            })
        } else {
            None
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    struct Flag(bool);

    impl ReloadState for Flag {
        fn reloading(&self) -> bool {
            self.0
        }
    }

    impl UpdaterState for Flag {
        fn busy(&self) -> bool {
            self.0
        }
    }

    fn hooks(reloading: bool, busy: bool) -> InferenceHooks {
        InferenceHooks {
            reload: Arc::new(Flag(reloading)),
            updater: Arc::new(Flag(busy)),
            ..InferenceHooks::default()
        }
    }

    #[test]
    fn the_updater_wins_over_a_reload() {
        assert_eq!(hooks(false, false).overloaded_message(), None);
        assert_eq!(
            hooks(true, false).overloaded_message(),
            Some("the model is reloading with a new context size; try again in a minute")
        );
        assert_eq!(
            hooks(false, true).overloaded_message(),
            Some(OVERLOADED_UPDATING)
        );
        assert_eq!(
            hooks(true, true).overloaded_message(),
            Some(OVERLOADED_UPDATING)
        );
        assert_eq!(InferenceHooks::default().overloaded_message(), None);
    }

    #[test]
    fn the_updating_message_names_the_product_only() {
        assert!(OVERLOADED_UPDATING.starts_with("PulsarMLX Console "));
        assert!(!OVERLOADED_UPDATING.to_ascii_lowercase().contains("maya"));
        assert_eq!(AttachDialect::OpenAi.as_str(), "openai");
        assert_eq!(AttachDialect::Responses.as_str(), "responses");
        assert_eq!(AttachDialect::Anthropic.as_str(), "anthropic");
    }
}
