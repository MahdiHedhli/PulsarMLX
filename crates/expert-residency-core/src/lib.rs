#![forbid(unsafe_code)]

pub mod expert_residency;

/// Stable identity for a reusable slot.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct SlotId(pub u64);
