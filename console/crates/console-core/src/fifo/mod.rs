//! Owned by ENG-09. `EngineFifo`: places in arrival order, exclusive holders, yields, queue
//! keep-alives and the queue watchdog.
//!
//! The FIFO decides which request has the engine. A request takes one place
//! ([`Units::ONE`]); exclusive work (an image encode, a context reload, an unload, a restart
//! for a model switch, shutdown) takes them all ([`Units::All`]). Places go in arrival
//! order, and a waiter for every place holds back the waiters behind it.
//!
//! How the turn driver uses it, for one request:
//!
//! 1. `let mut wait = fifo.queue_wait(Units::ONE, control.probe(), queue_ping_interval());`
//! 2. Loop on `wait.next().await`: write a keep-alive on [`QueueStep::Ping`]; stop on
//!    [`QueueStep::Cancelled`]; on [`QueueStep::Turn`] keep the [`PlaceGuard`]. Dropping the
//!    wait (the client went away) gives up the place in line. After `Turn`, check the
//!    cancel again: `Turn` can arrive with the cancel already set, and then the turn driver
//!    drops the guard and answers with a cancelled finish and zero completion tokens without
//!    calling the engine, as the donor's `_turn` does (serve/server.py:4361-4363).
//! 3. Hold the guard until the engine call has really returned on the driver thread
//!    (contracts/backend-seam.md section 4, rule 4): move it into the driver job and drop
//!    it there, or keep it until the driver's reply arrives. Dropping it gives the place
//!    back synchronously, so no error path, cancel or panic can leak a place.
//!
//! Fair slices (ENG-11) use [`PlaceGuard::claim_yield`], [`PlaceGuard::unclaim_yield`] and
//! [`PlaceGuard::yield_place`]; a claim made through the guard ends when the guard is
//! dropped, so a cancelled turn never leaks one. [`EngineFifo::claim_yield`] and
//! [`EngineFifo::unclaim_yield`] are the donor's untied forms.
//!
//! Known donor hazard (kept, see [`PlaceGuard`]): an exclusive holder whose capacity grew
//! while it held gives back the new capacity, which can free places other requests hold. The watchdog is [`EngineFifo::spawn_queue_watch`].
//!
//! Tests run on tokio's paused clock: every instant here is a `tokio::time::Instant`. Under
//! a paused clock, call the FIFO from inside the runtime only, since a thread outside it
//! reads the real clock; in production both clocks agree.
//! Nothing here is qualified beyond synthetic backends.
//!
//! Behavior reference: project-maya serve/server.py:172-187, 243-401, 3239-3270, 3813-3860
//! and 4346-4378 at 7e68a30f.

mod lock;
mod log;
mod queue;
mod watch;

pub use lock::{EngineFifo, Place, PlaceGuard, TurnWait, Units};
pub use log::{FifoLog, LogCapture, LOG_CAPTURE_MAX_LINES};
pub use queue::{
    queue_ping_interval, queue_ping_interval_from, QueueStep, QueueWait, QUEUE_LOG, QUEUE_PING,
    QUEUE_PING_ENV, QUEUE_PING_MIN, QUEUE_POLL,
};
pub use watch::{
    queue_watch_line, QueueWatch, QueueWatchState, WatchStatus, QUEUE_TICK, QUEUE_WARN,
    QUEUE_WEDGED,
};
