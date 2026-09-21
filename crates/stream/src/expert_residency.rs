use crate::SlotId;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ExpertKind {
    Routed,
    Shared,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ExpertKey {
    pub layer: u32,
    pub expert: u32,
    pub kind: ExpertKind,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ExpertResidencyTier {
    CompressedResident,
    DecodedHot,
    NativeReadyHot,
    Transient,
}

impl ExpertResidencyTier {
    const fn counts_as_hot(self) -> bool {
        matches!(self, Self::DecodedHot | Self::NativeReadyHot)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ExpertLifecycle {
    Available,
    Leased,
    Pinned,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ExpertAdmissionPolicy {
    pub max_resident_bytes: u64,
    pub max_hot_entries_per_layer: u32,
    pub allow_native_ready: bool,
    pub protect_shared: bool,
}

impl ExpertAdmissionPolicy {
    pub const fn new(
        max_resident_bytes: u64,
        max_hot_entries_per_layer: u32,
        allow_native_ready: bool,
        protect_shared: bool,
    ) -> Option<Self> {
        if max_resident_bytes == 0 || max_hot_entries_per_layer == 0 {
            return None;
        }
        Some(Self {
            max_resident_bytes,
            max_hot_entries_per_layer,
            allow_native_ready,
            protect_shared,
        })
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ExpertAdmissionRequest {
    pub key: ExpertKey,
    pub tier: ExpertResidencyTier,
    pub bytes: u64,
    pub slot_id: SlotId,
    pub protected: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ExpertResident {
    pub key: ExpertKey,
    pub tier: ExpertResidencyTier,
    pub bytes: u64,
    pub slot_id: SlotId,
    pub protected: bool,
    pub lifecycle: ExpertLifecycle,
    pub occupancy_generation: u64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ExpertAdmissionError {
    InvalidPolicy,
    InvalidSize,
    AlreadyResident,
    NativeReadyDisabled,
    SharedMustBeProtected,
    HotEntryLimit,
    ExceedsBudget,
    Missing,
    NotEvictable(ExpertLifecycle),
    Protected,
    InvalidLifecycle {
        from: ExpertLifecycle,
        to: ExpertLifecycle,
    },
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ExpertLookup {
    Resident(ExpertResident),
    Missing,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ExpertFallback {
    Native(ExpertResident),
    Reference,
}

#[derive(Debug, Clone)]
pub struct ExpertResidencyTable {
    policy: ExpertAdmissionPolicy,
    entries: Vec<ExpertResident>,
    resident_bytes: u64,
    next_occupancy_generation: u64,
}

impl ExpertResidencyTable {
    pub fn new(policy: ExpertAdmissionPolicy) -> Self {
        Self {
            policy,
            entries: Vec::new(),
            resident_bytes: 0,
            next_occupancy_generation: 1,
        }
    }

    pub const fn policy(&self) -> ExpertAdmissionPolicy {
        self.policy
    }

    pub const fn resident_bytes(&self) -> u64 {
        self.resident_bytes
    }

    pub fn len(&self) -> usize {
        self.entries.len()
    }

    pub fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }

    pub fn lookup(&self, key: ExpertKey) -> ExpertLookup {
        self.entries
            .iter()
            .find(|entry| entry.key == key)
            .copied()
            .map_or(ExpertLookup::Missing, ExpertLookup::Resident)
    }

    pub fn fallback(&self, key: ExpertKey) -> ExpertFallback {
        match self.lookup(key) {
            ExpertLookup::Resident(entry) => ExpertFallback::Native(entry),
            ExpertLookup::Missing => ExpertFallback::Reference,
        }
    }

    pub fn hot_entries_for_layer(&self, layer: u32) -> u32 {
        self.entries
            .iter()
            .filter(|entry| entry.key.layer == layer && entry.tier.counts_as_hot())
            .count() as u32
    }

    pub fn admit(
        &mut self,
        request: ExpertAdmissionRequest,
    ) -> Result<ExpertResident, ExpertAdmissionError> {
        if request.bytes == 0 {
            return Err(ExpertAdmissionError::InvalidSize);
        }
        if self.entries.iter().any(|entry| entry.key == request.key) {
            return Err(ExpertAdmissionError::AlreadyResident);
        }
        if request.tier == ExpertResidencyTier::NativeReadyHot && !self.policy.allow_native_ready {
            return Err(ExpertAdmissionError::NativeReadyDisabled);
        }
        if self.policy.protect_shared
            && request.key.kind == ExpertKind::Shared
            && !request.protected
        {
            return Err(ExpertAdmissionError::SharedMustBeProtected);
        }
        if request.tier.counts_as_hot()
            && self.hot_entries_for_layer(request.key.layer)
                >= self.policy.max_hot_entries_per_layer
        {
            return Err(ExpertAdmissionError::HotEntryLimit);
        }
        let total = self
            .resident_bytes
            .checked_add(request.bytes)
            .ok_or(ExpertAdmissionError::ExceedsBudget)?;
        if total > self.policy.max_resident_bytes {
            return Err(ExpertAdmissionError::ExceedsBudget);
        }
        let occupancy_generation = self.next_occupancy_generation;
        self.next_occupancy_generation = self
            .next_occupancy_generation
            .checked_add(1)
            .ok_or(ExpertAdmissionError::ExceedsBudget)?;
        let entry = ExpertResident {
            key: request.key,
            tier: request.tier,
            bytes: request.bytes,
            slot_id: request.slot_id,
            protected: request.protected,
            lifecycle: ExpertLifecycle::Available,
            occupancy_generation,
        };
        self.entries.push(entry);
        self.resident_bytes = total;
        Ok(entry)
    }

    pub fn transition(
        &mut self,
        key: ExpertKey,
        to: ExpertLifecycle,
    ) -> Result<ExpertResident, ExpertAdmissionError> {
        let entry = self
            .entries
            .iter_mut()
            .find(|entry| entry.key == key)
            .ok_or(ExpertAdmissionError::Missing)?;
        let valid = matches!(
            (entry.lifecycle, to),
            (ExpertLifecycle::Available, ExpertLifecycle::Leased)
                | (ExpertLifecycle::Leased, ExpertLifecycle::Pinned)
                | (ExpertLifecycle::Pinned, ExpertLifecycle::Leased)
                | (ExpertLifecycle::Leased, ExpertLifecycle::Available)
        );
        if !valid {
            return Err(ExpertAdmissionError::InvalidLifecycle {
                from: entry.lifecycle,
                to,
            });
        }
        entry.lifecycle = to;
        Ok(*entry)
    }

    pub fn evict(&mut self, key: ExpertKey) -> Result<ExpertResident, ExpertAdmissionError> {
        let index = self
            .entries
            .iter()
            .position(|entry| entry.key == key)
            .ok_or(ExpertAdmissionError::Missing)?;
        let entry = self.entries[index];
        if entry.protected {
            return Err(ExpertAdmissionError::Protected);
        }
        if entry.lifecycle != ExpertLifecycle::Available {
            return Err(ExpertAdmissionError::NotEvictable(entry.lifecycle));
        }
        self.resident_bytes = self
            .resident_bytes
            .checked_sub(entry.bytes)
            .ok_or(ExpertAdmissionError::ExceedsBudget)?;
        self.entries.remove(index);
        Ok(entry)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const ROUTED: ExpertKey = ExpertKey {
        layer: 3,
        expert: 15,
        kind: ExpertKind::Routed,
    };

    const SHARED: ExpertKey = ExpertKey {
        layer: 3,
        expert: 0,
        kind: ExpertKind::Shared,
    };

    fn policy() -> ExpertAdmissionPolicy {
        ExpertAdmissionPolicy::new(100, 2, true, true).unwrap()
    }

    fn request(key: ExpertKey, tier: ExpertResidencyTier, bytes: u64) -> ExpertAdmissionRequest {
        ExpertAdmissionRequest {
            key,
            tier,
            bytes,
            slot_id: SlotId(bytes),
            protected: false,
        }
    }

    #[test]
    fn supports_compressed_decoded_native_ready_and_transient_tiers() {
        let mut table = ExpertResidencyTable::new(policy());
        for (key, tier) in [
            (ROUTED, ExpertResidencyTier::CompressedResident),
            (
                ExpertKey {
                    expert: 16,
                    ..ROUTED
                },
                ExpertResidencyTier::DecodedHot,
            ),
            (
                ExpertKey {
                    expert: 17,
                    ..ROUTED
                },
                ExpertResidencyTier::NativeReadyHot,
            ),
            (
                ExpertKey {
                    expert: 18,
                    ..ROUTED
                },
                ExpertResidencyTier::Transient,
            ),
        ] {
            table.admit(request(key, tier, 10)).unwrap();
        }
        assert_eq!(table.resident_bytes(), 40);
        assert_eq!(table.hot_entries_for_layer(3), 2);
    }

    #[test]
    fn shared_entries_require_protection_and_cannot_be_evicted() {
        let mut table = ExpertResidencyTable::new(policy());
        assert_eq!(
            table.admit(request(SHARED, ExpertResidencyTier::DecodedHot, 10)),
            Err(ExpertAdmissionError::SharedMustBeProtected)
        );
        let mut shared = request(SHARED, ExpertResidencyTier::NativeReadyHot, 10);
        shared.protected = true;
        table.admit(shared).unwrap();
        assert_eq!(table.evict(SHARED), Err(ExpertAdmissionError::Protected));
    }

    #[test]
    fn admission_is_bounded_and_does_not_implicitly_evict() {
        let mut table = ExpertResidencyTable::new(policy());
        table
            .admit(request(ROUTED, ExpertResidencyTier::DecodedHot, 60))
            .unwrap();
        table
            .admit(request(
                ExpertKey {
                    expert: 16,
                    ..ROUTED
                },
                ExpertResidencyTier::DecodedHot,
                40,
            ))
            .unwrap();
        assert_eq!(
            table.admit(request(
                ExpertKey {
                    expert: 17,
                    ..ROUTED
                },
                ExpertResidencyTier::CompressedResident,
                1,
            ),),
            Err(ExpertAdmissionError::ExceedsBudget)
        );
        assert_eq!(table.len(), 2);
    }

    #[test]
    fn release_then_explicit_evict_enables_reference_fallback() {
        let mut table = ExpertResidencyTable::new(policy());
        table
            .admit(request(ROUTED, ExpertResidencyTier::DecodedHot, 10))
            .unwrap();
        table.transition(ROUTED, ExpertLifecycle::Leased).unwrap();
        assert_eq!(
            table.evict(ROUTED),
            Err(ExpertAdmissionError::NotEvictable(ExpertLifecycle::Leased))
        );
        table
            .transition(ROUTED, ExpertLifecycle::Available)
            .unwrap();
        table.evict(ROUTED).unwrap();
        assert_eq!(table.fallback(ROUTED), ExpertFallback::Reference);
    }

    #[test]
    fn native_ready_can_be_disabled_without_affecting_other_tiers() {
        let disabled = ExpertAdmissionPolicy::new(100, 2, false, false).unwrap();
        let mut table = ExpertResidencyTable::new(disabled);
        assert_eq!(
            table.admit(request(ROUTED, ExpertResidencyTier::NativeReadyHot, 1)),
            Err(ExpertAdmissionError::NativeReadyDisabled)
        );
        table
            .admit(request(ROUTED, ExpertResidencyTier::CompressedResident, 1))
            .unwrap();
    }
}
