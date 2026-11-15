//! Cancel, pause and wrap requests (contract section 8). They reach a running generation
//! through a [`ControlProbe`] the engine reads between steps; no method of the engine
//! instance is called from another thread to deliver them.

use std::sync::atomic::{AtomicBool, AtomicU8, Ordering};
use std::sync::Arc;

const PAUSE_NONE: u8 = 0;
const PAUSE_PLAIN: u8 = 1;
const PAUSE_KEEP: u8 = 2;

#[derive(Debug, Default)]
struct ControlState {
    cancelled: AtomicBool,
    pause: AtomicU8,
    wrap: AtomicBool,
}

/// A pause request.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct PauseRequest {
    /// First set the prompt's state aside for the conversation's next turn.
    pub keep: bool,
}

/// The engine's read-only view of one generation's control state. `Send + Sync`;
/// atomics only.
#[derive(Debug, Clone)]
pub struct ControlProbe(Arc<ControlState>);

impl ControlProbe {
    /// True once cancel was requested.
    pub fn is_cancelled(&self) -> bool {
        self.0.cancelled.load(Ordering::Acquire)
    }

    /// The pause request, if any. A later `pause(true)` upgrades an earlier
    /// `pause(false)`; nothing downgrades it.
    pub fn pause_requested(&self) -> Option<PauseRequest> {
        match self.0.pause.load(Ordering::Acquire) {
            PAUSE_NONE => None,
            PAUSE_KEEP => Some(PauseRequest { keep: true }),
            _ => Some(PauseRequest { keep: false }),
        }
    }

    /// True once wrap was requested.
    pub fn wrap_requested(&self) -> bool {
        self.0.wrap.load(Ordering::Acquire)
    }
}

/// The server's side of one generation's control state. Requests are sticky: once set
/// they stay set for the generation.
#[derive(Debug, Clone, Default)]
pub struct ControlHandle(Arc<ControlState>);

impl ControlHandle {
    /// A fresh control state with nothing requested.
    pub fn new() -> Self {
        Self::default()
    }

    /// The probe the engine reads.
    pub fn probe(&self) -> ControlProbe {
        ControlProbe(Arc::clone(&self.0))
    }

    /// Client gone, shutdown, or the server decided the answer is finished.
    pub fn cancel(&self) {
        self.0.cancelled.store(true, Ordering::Release);
    }

    /// End at the next step and keep the engine's state (fair slices). Only for engines
    /// with `caps.pause`.
    pub fn pause(&self, keep: bool) {
        let want = if keep { PAUSE_KEEP } else { PAUSE_PLAIN };
        self.0.pause.fetch_max(want, Ordering::AcqRel);
    }

    /// The server is stopping: close reasoning at the next token and answer.
    pub fn wrap(&self) {
        self.0.wrap.store(true, Ordering::Release);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn requests_reach_the_probe() {
        let h = ControlHandle::new();
        let p = h.probe();
        assert!(!p.is_cancelled());
        assert_eq!(p.pause_requested(), None);
        assert!(!p.wrap_requested());
        h.wrap();
        assert!(p.wrap_requested());
        assert!(
            !p.is_cancelled(),
            "wrap does not end the generation by itself"
        );
        h.pause(false);
        assert_eq!(p.pause_requested(), Some(PauseRequest { keep: false }));
        h.pause(true);
        assert_eq!(p.pause_requested(), Some(PauseRequest { keep: true }));
        h.pause(false);
        assert_eq!(p.pause_requested(), Some(PauseRequest { keep: true }));
        h.clone().cancel();
        assert!(p.is_cancelled());
    }

    #[test]
    fn cancel_crosses_threads() {
        let h = ControlHandle::new();
        let p = h.probe();
        let t = std::thread::spawn(move || {
            while !p.is_cancelled() {
                std::thread::yield_now();
            }
            true
        });
        h.cancel();
        assert!(t.join().unwrap_or(false));
    }
}
