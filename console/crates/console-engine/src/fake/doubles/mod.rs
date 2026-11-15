//! Provenance: translated from project-maya serve/test_server.py, serve/test_fair.py, serve/test_logprobs.py and serve/test_ds4_restore_points.py at 7e68a30f (MIT); license text in console/LICENSES/project-maya-MIT.txt.
//!
//! The scriptable test engines of the donor's tests, behind the seam. Each type is the
//! Rust counterpart of one donor test double and names its upstream class. They are
//! factories (`EngineFactory`, `Send + Sync`, cheap to clone): clones share their
//! counters, so a test keeps one clone to observe and to steer the engine and hands
//! another to the server. Every one of them is synthetic and passes `require_synthetic`,
//! except [`NotSyntheticEngine`], which is built to be refused.
//!
//! Only built with the `test-support` feature (or for this crate's own tests). No
//! configuration key, command-line flag or environment variable selects any of them.
//!
//! Where a donor double yields `None` (a heartbeat while the engine is quiet), nothing is
//! delivered: heartbeats are not engine events (contract section 7); the server makes its
//! own. Where a donor double keeps figures in its `last` attribute across calls, the
//! figures here belong to the call that produced them (contract section 9).

use std::time::Instant;

use console_core::engine::{
    ControlProbe, EngineDescriptor, EngineFailure, EngineInstance, EventSink, GenerationRequest,
    Health, ShutdownOutcome, Terminal,
};

use super::mock::{MockCore, MockHooks};

mod budget;
mod failing;
mod fair;
mod figures;
mod lifecycle;
mod not_synthetic;
mod recording;

pub use budget::BudgetEngine;
pub use failing::{
    BrokenEngine, DyingEngine, ErrEngine, HalfDeadEngine, NonFiniteEngine, NON_FINITE_MESSAGE,
};
pub use fair::{PausingEngine, ResumingEngine, PAUSE_LATE_TOKENS, RESUMING_DEFAULT_DELAY};
pub use figures::{ClockedEngine, LpEngine, PacedEngine, CLOCKED_REUSED};
pub use lifecycle::{HeldEngine, LifecycleEngine, HELD_POLL};
pub use not_synthetic::NotSyntheticEngine;
pub use recording::{Recording, RecordingEngine, RecordingPrompt, Sampled};

/// The instance-level behavior of a double built on the scripted engine.
pub(crate) trait DoubleHooks: MockHooks {
    /// The donor's `alive()`, `exit_code()` and `death_note()`.
    fn health(&mut self) -> Health {
        Health::Alive
    }

    /// The donor's `close()`.
    fn shutdown(&mut self) -> ShutdownOutcome {
        ShutdownOutcome::Graceful
    }
}

/// A scripted engine whose generation one double changes through its hooks.
pub(crate) struct Hooked<H> {
    pub(crate) core: MockCore,
    pub(crate) hooks: H,
}

impl<H: DoubleHooks> EngineInstance for Hooked<H> {
    fn descriptor(&self) -> &EngineDescriptor {
        &self.core.desc
    }

    fn generate(
        &mut self,
        req: &GenerationRequest,
        control: &ControlProbe,
        sink: &mut dyn EventSink,
    ) -> Result<Terminal, EngineFailure> {
        self.core.run(req, control, sink, &mut self.hooks)
    }

    fn health(&mut self) -> Health {
        self.core.refresh();
        self.hooks.health()
    }

    fn sample(&mut self) -> Option<console_core::engine::EngineSample> {
        self.core.refresh();
        None
    }

    fn shutdown(mut self: Box<Self>, _deadline: Instant) -> ShutdownOutcome {
        self.hooks.shutdown()
    }
}
