//! Owned by API-07. The dialect-agnostic inference request lifecycle driver: one request on
//! a chat route, from the route handler to the last byte.
//!
//! # One request
//!
//! [`Inference::register`] puts an [`InferenceRoute`] on a chat route of the router
//! (`/v1/chat/completions`, `/v1/responses`, `/v1/messages`). The router has already run
//! its guards and read the body as a JSON object. Then, in the donor's order:
//!
//! 1. **Overloaded gate.** While the updater is busy or a context reload waits or runs,
//!    503 `overloaded_error` with `Retry-After: 30` ([`InferenceHooks::overloaded_message`]).
//! 2. **Boundary strip.** Every top-level key beginning with `_` is removed (deviation
//!    SEC-6.1, `console_core::request::strip_internal_keys`).
//! 3. **Attachments.** The attachment planner's `expand_request` ([`Attachments`], RSP-16;
//!    inert in M1).
//! 4. **Dialect.** [`Dialect::prepare`] checks the request, prepares the prompt and builds
//!    the [`TurnRequest`](console_core::turn::TurnRequest); any error is answered with its
//!    status ([`InferenceError`]).
//! 5. **Debug line** (`PULSAR_CONSOLE_DEBUG`, [`DebugRequest`]).
//! 6. **Turn.** The client watcher starts (unless the dialect says not to) and the turn
//!    runs on the [`TurnDriver`]. A collected answer drains the turn's items into the
//!    dialect before any header is written, so failures become real statuses. A stream
//!    writes the SSE head, then each frame on its own; a keep-alive without progress is
//!    `: keep-alive`. When the client is seen to go, the turn is cancelled. When a write
//!    fails, the turn is cancelled and its stream dropped, which stops the engine once
//!    (STOP) and drains it while the turn still holds its FIFO place; the place is given
//!    back only after the engine call has returned (`console_core::turn`, rule 2).
//!    A failure is first offered to the dialect ([`DialectTurn::failed`], for the
//!    Responses dialect's own failed answer); otherwise it is answered by its class: before
//!    the head with its status, after it as the dialect's error event or the mid-answer
//!    log line ([`InferenceError::before_start`], [`InferenceError::after_start`]).
//!
//! The turn trace (`PULSAR_CONSOLE_TURN_TRACE`, [`TurnTrace`]) marks `json` when the
//! handler receives the parsed body; the dialect marks `prepare_start` and `prepared`.
//! The line is printed at the first token of a turn that is not cancelled, and only once
//! the engine-side `gen_start` mark exists, as the donor's (M3's line-protocol client adds
//! that mark, so M1 prints no trace line).
//!
//! The traceback line of a malformed request and the line of an exception the donor's
//! handler does not catch go to the error log (standard error by default, as the donor's
//! `traceback.print_exc` and `handle_error`); the debug and trace lines go to the log
//! (standard output).
//!
//! # Seams
//!
//! ENG-12's reload state ([`ReloadState`]), OPS-22's updater ([`UpdaterState`]), RSP-16's
//! attachment planner ([`Attachments`]), PRM-11's prompt step ([`Dialect::prepare`] and the
//! P-8 mapping point [`PromptFailure`]) and PRM-12's output pipeline
//! ([`DialectTurn::token`]) each have their M1 behavior as the default. The request
//! context carries no embeddings handle (the donor's `carry_embeddings`): that seam is
//! deferred to the vision packages.
//!
//! The driver admits no engine itself: every engine reaches it through the
//! [`TurnDriver`], whose admission step applies the synthetic-only guard. Nothing here is
//! qualified beyond synthetic backends.
//!
//! Behavior reference: project-maya serve/server.py:6160-6166, 6241-6297, 5019-5044,
//! 6566-6624, 6680-6710, 4796-4808, 2093-2110 and 3680-3694 at 7e68a30f.

mod debug;
mod dialect;
mod drive;
mod error;
mod hooks;
mod trace;

use std::sync::Arc;

use console_core::config::EnvSettings;
use console_core::fifo::FifoLog;
use console_core::turn::TurnDriver;

use crate::router::{BodyMode, Route, RouteHandler, RouteRequest, Router, ROUTES};
use crate::transport::HandlerFuture;

pub use debug::{DebugRequest, DEBUG_PREVIEW_CHARS};
pub use dialect::{Dialect, DialectTurn, Failure, PrepareCall, PrepareFuture, PreparedTurn, Step};
pub use drive::KEEP_ALIVE;
pub use error::{
    AfterStart, BeforeStart, FaultClass, InferenceError, PromptFailure, PromptFailureKind,
    StreamFault,
};
pub use hooks::{
    AttachCall, AttachDialect, Attachments, InferenceHooks, NeverReloading, NoAttachments,
    NoUpdater, ReloadState, UpdaterState, OVERLOADED_UPDATING,
};
pub use trace::{TurnTrace, TRACE_MARKS_MAX};

/// The driver's settings from the environment.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct InferenceSettings {
    /// `PULSAR_CONSOLE_DEBUG`: write the debug line of each request.
    pub debug: bool,
    /// `PULSAR_CONSOLE_TURN_TRACE`: record each request's clock marks.
    pub turn_trace: bool,
}

impl InferenceSettings {
    /// The settings `env` gives.
    pub fn from_env(env: &EnvSettings) -> Self {
        Self {
            debug: env.debug,
            turn_trace: env.turn_trace,
        }
    }
}

/// The server's inference state, shared by the chat routes.
pub struct Inference {
    driver: TurnDriver,
    hooks: InferenceHooks,
    settings: InferenceSettings,
    log: FifoLog,
    error_log: FifoLog,
}

impl std::fmt::Debug for Inference {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("Inference")
            .field("driver", &self.driver)
            .field("hooks", &self.hooks)
            .field("settings", &self.settings)
            .finish_non_exhaustive()
    }
}

impl Inference {
    /// The state over `driver`, with the M1 hooks, the settings off, the log on standard
    /// output and the error log on standard error.
    pub fn new(driver: TurnDriver) -> Self {
        Self {
            driver,
            hooks: InferenceHooks::default(),
            settings: InferenceSettings::default(),
            log: FifoLog::stdout(),
            error_log: FifoLog::new(|line| eprintln!("{line}")),
        }
    }

    /// With these hooks.
    pub fn with_hooks(mut self, hooks: InferenceHooks) -> Self {
        self.hooks = hooks;
        self
    }

    /// With these settings.
    pub fn with_settings(mut self, settings: InferenceSettings) -> Self {
        self.settings = settings;
        self
    }

    /// With this log for the debug and trace lines.
    pub fn with_log(mut self, log: FifoLog) -> Self {
        self.log = log;
        self
    }

    /// With this log for the traceback and uncaught-exception lines.
    pub fn with_error_log(mut self, log: FifoLog) -> Self {
        self.error_log = log;
        self
    }

    /// The turn driver.
    pub fn driver(&self) -> &TurnDriver {
        &self.driver
    }

    /// The hooks.
    pub fn hooks(&self) -> &InferenceHooks {
        &self.hooks
    }

    /// The settings.
    pub fn settings(&self) -> InferenceSettings {
        self.settings
    }

    /// The log.
    pub fn log(&self) -> &FifoLog {
        &self.log
    }

    /// The error log.
    pub fn error_log(&self) -> &FifoLog {
        &self.error_log
    }

    /// The route handler of `dialect` over this state.
    pub fn route(self: &Arc<Self>, dialect: Arc<dyn Dialect>) -> Arc<dyn RouteHandler> {
        Arc::new(InferenceRoute {
            inference: Arc::clone(self),
            dialect,
        })
    }

    /// Registers `dialect` on `route`, returning the handler it replaces. Only a route
    /// whose body the router reads as a JSON object ([`BodyMode::Json`]: the chat routes
    /// [`Route::ChatCompletions`], [`Route::Responses`] and [`Route::Messages`]) can carry
    /// the driver, which reads no body of its own.
    ///
    /// # Panics
    ///
    /// When `route` is not a [`BodyMode::Json`] route (a wiring error at startup).
    pub fn register(
        self: &Arc<Self>,
        router: &mut Router,
        route: Route,
        dialect: Arc<dyn Dialect>,
    ) -> Option<Arc<dyn RouteHandler>> {
        assert!(
            is_json_route(route),
            "the inference driver needs a route with a JSON body, not {route:?}"
        );
        router.register(route, self.route(dialect))
    }
}

/// Whether the router reads `route`'s body as a JSON object.
fn is_json_route(route: Route) -> bool {
    ROUTES
        .iter()
        .any(|spec| spec.route == route && spec.body == BodyMode::Json)
}

/// The route handler of one chat route: the lifecycle driver over one dialect.
pub struct InferenceRoute {
    inference: Arc<Inference>,
    dialect: Arc<dyn Dialect>,
}

impl std::fmt::Debug for InferenceRoute {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("InferenceRoute")
            .field("dialect", &self.dialect.attach_dialect())
            .finish_non_exhaustive()
    }
}

impl RouteHandler for InferenceRoute {
    fn serve(&self, request: RouteRequest) -> HandlerFuture<'_> {
        Box::pin(drive::serve(
            Arc::clone(&self.inference),
            Arc::clone(&self.dialect),
            request,
        ))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_json_body_routes_can_carry_the_driver() {
        for route in [Route::ChatCompletions, Route::Responses, Route::Messages] {
            assert!(is_json_route(route), "{route:?}");
        }
        let without_json: Vec<Route> = ROUTES
            .iter()
            .filter(|spec| spec.body != BodyMode::Json)
            .map(|spec| spec.route)
            .filter(|route| !is_json_route(*route))
            .collect();
        assert!(!without_json.is_empty());
    }
}
