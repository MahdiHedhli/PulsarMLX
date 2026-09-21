//! Fail-closed lifecycle contract for the Apple native buffer bridge.
//!
//! This module models ownership and cancellation ordering without claiming that
//! it is an MLX import implementation. The Objective-C++ adapter must map its
//! native callbacks to these states before a production bridge is qualified.

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AppleBridgeState {
    Created,
    Registered,
    Submitted,
    Completed,
    Cancelled,
    Released,
    Destroyed,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AppleBridgeEvent {
    Register,
    Submit,
    Complete,
    CancelBeforeSubmit,
    CancelQueued,
    Release,
    Destroy,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AppleBridgeLifecycleError {
    InvalidTransition {
        state: AppleBridgeState,
        event: AppleBridgeEvent,
    },
    StaleGeneration {
        expected: u64,
        actual: u64,
    },
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct AppleBridgeGeneration {
    pub value: u64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct AppleBridgeLifecycle {
    state: AppleBridgeState,
    generation: AppleBridgeGeneration,
}

impl AppleBridgeLifecycle {
    pub const fn new(generation: AppleBridgeGeneration) -> Self {
        Self {
            state: AppleBridgeState::Created,
            generation,
        }
    }

    pub const fn state(self) -> AppleBridgeState {
        self.state
    }

    pub const fn generation(self) -> AppleBridgeGeneration {
        self.generation
    }

    pub fn apply(
        &mut self,
        event: AppleBridgeEvent,
        generation: AppleBridgeGeneration,
    ) -> Result<AppleBridgeState, AppleBridgeLifecycleError> {
        if generation != self.generation {
            return Err(AppleBridgeLifecycleError::StaleGeneration {
                expected: self.generation.value,
                actual: generation.value,
            });
        }
        let next = match (self.state, event) {
            (AppleBridgeState::Created, AppleBridgeEvent::Register) => AppleBridgeState::Registered,
            (AppleBridgeState::Registered, AppleBridgeEvent::Submit) => AppleBridgeState::Submitted,
            (AppleBridgeState::Registered, AppleBridgeEvent::CancelBeforeSubmit) => {
                AppleBridgeState::Cancelled
            }
            (AppleBridgeState::Submitted, AppleBridgeEvent::Complete) => {
                AppleBridgeState::Completed
            }
            (AppleBridgeState::Submitted, AppleBridgeEvent::CancelQueued) => {
                AppleBridgeState::Cancelled
            }
            (AppleBridgeState::Completed, AppleBridgeEvent::Release)
            | (AppleBridgeState::Cancelled, AppleBridgeEvent::Release) => {
                AppleBridgeState::Released
            }
            (AppleBridgeState::Released, AppleBridgeEvent::Destroy) => AppleBridgeState::Destroyed,
            _ => {
                return Err(AppleBridgeLifecycleError::InvalidTransition {
                    state: self.state,
                    event,
                })
            }
        };
        self.state = next;
        Ok(next)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const GENERATION: AppleBridgeGeneration = AppleBridgeGeneration { value: 11 };

    fn apply(lifecycle: &mut AppleBridgeLifecycle, event: AppleBridgeEvent) {
        lifecycle.apply(event, GENERATION).unwrap();
    }

    #[test]
    fn normal_completion_requires_release_before_destroy() {
        let mut lifecycle = AppleBridgeLifecycle::new(GENERATION);
        apply(&mut lifecycle, AppleBridgeEvent::Register);
        apply(&mut lifecycle, AppleBridgeEvent::Submit);
        apply(&mut lifecycle, AppleBridgeEvent::Complete);
        apply(&mut lifecycle, AppleBridgeEvent::Release);
        apply(&mut lifecycle, AppleBridgeEvent::Destroy);
        assert_eq!(lifecycle.state(), AppleBridgeState::Destroyed);
    }

    #[test]
    fn cancel_before_submit_is_terminal_and_releasable() {
        let mut lifecycle = AppleBridgeLifecycle::new(GENERATION);
        apply(&mut lifecycle, AppleBridgeEvent::Register);
        apply(&mut lifecycle, AppleBridgeEvent::CancelBeforeSubmit);
        apply(&mut lifecycle, AppleBridgeEvent::Release);
        apply(&mut lifecycle, AppleBridgeEvent::Destroy);
        assert_eq!(lifecycle.state(), AppleBridgeState::Destroyed);
    }

    #[test]
    fn queued_cancel_is_terminal_and_releasable() {
        let mut lifecycle = AppleBridgeLifecycle::new(GENERATION);
        apply(&mut lifecycle, AppleBridgeEvent::Register);
        apply(&mut lifecycle, AppleBridgeEvent::Submit);
        apply(&mut lifecycle, AppleBridgeEvent::CancelQueued);
        apply(&mut lifecycle, AppleBridgeEvent::Release);
        apply(&mut lifecycle, AppleBridgeEvent::Destroy);
        assert_eq!(lifecycle.state(), AppleBridgeState::Destroyed);
    }

    #[test]
    fn double_release_and_use_after_destroy_fail_closed() {
        let mut lifecycle = AppleBridgeLifecycle::new(GENERATION);
        apply(&mut lifecycle, AppleBridgeEvent::Register);
        apply(&mut lifecycle, AppleBridgeEvent::CancelBeforeSubmit);
        apply(&mut lifecycle, AppleBridgeEvent::Release);
        assert_eq!(
            lifecycle.apply(AppleBridgeEvent::Release, GENERATION),
            Err(AppleBridgeLifecycleError::InvalidTransition {
                state: AppleBridgeState::Released,
                event: AppleBridgeEvent::Release,
            })
        );
        apply(&mut lifecycle, AppleBridgeEvent::Destroy);
        assert!(lifecycle
            .apply(AppleBridgeEvent::Register, GENERATION)
            .is_err());
    }

    #[test]
    fn stale_generation_cannot_mutate_lifecycle() {
        let mut lifecycle = AppleBridgeLifecycle::new(GENERATION);
        let stale = AppleBridgeGeneration { value: 10 };
        assert_eq!(
            lifecycle.apply(AppleBridgeEvent::Register, stale),
            Err(AppleBridgeLifecycleError::StaleGeneration {
                expected: GENERATION.value,
                actual: stale.value,
            })
        );
        assert_eq!(lifecycle.state(), AppleBridgeState::Created);
    }

    #[test]
    fn repeated_instances_have_independent_generations() {
        let mut first = AppleBridgeLifecycle::new(AppleBridgeGeneration { value: 1 });
        let mut second = AppleBridgeLifecycle::new(AppleBridgeGeneration { value: 2 });
        first
            .apply(
                AppleBridgeEvent::Register,
                AppleBridgeGeneration { value: 1 },
            )
            .unwrap();
        assert_eq!(
            second.apply(
                AppleBridgeEvent::Register,
                AppleBridgeGeneration { value: 1 }
            ),
            Err(AppleBridgeLifecycleError::StaleGeneration {
                expected: 2,
                actual: 1,
            })
        );
        assert_eq!(first.state(), AppleBridgeState::Registered);
        assert_eq!(second.state(), AppleBridgeState::Created);
    }
}
