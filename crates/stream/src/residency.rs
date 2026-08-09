use crate::trunk_inventory::TrunkInventorySummary;
use crate::SlotId;

pub const GIB: u64 = 1024 * 1024 * 1024;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ResidencyOptionId {
    ACompressedAllTrunk,
    BDecodedAllTrunk,
    CDecodedAttentionMlaOnly,
    DDecodedOutputHeadOnly,
    EDecodedHotSubset,
    FCompressedAllPlusDecodedHot,
}

impl ResidencyOptionId {
    pub const ALL: [Self; 6] = [
        Self::ACompressedAllTrunk,
        Self::BDecodedAllTrunk,
        Self::CDecodedAttentionMlaOnly,
        Self::DDecodedOutputHeadOnly,
        Self::EDecodedHotSubset,
        Self::FCompressedAllPlusDecodedHot,
    ];

    pub const fn name(self) -> &'static str {
        match self {
            Self::ACompressedAllTrunk => "compressed_all_trunk_residency",
            Self::BDecodedAllTrunk => "decoded_f32_all_trunk_residency",
            Self::CDecodedAttentionMlaOnly => "decoded_attention_mla_only_residency",
            Self::DDecodedOutputHeadOnly => "decoded_output_head_only_residency",
            Self::EDecodedHotSubset => {
                "decoded_hot_subset_candidate_output_head_plus_router_norms"
            }
            Self::FCompressedAllPlusDecodedHot => "compressed_all_trunk_plus_decoded_hot_subset",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ResidencyDisposition {
    NominalOnlyRequiresMeasurement,
    UnsafeExceedsReserve,
    SafeLogicalFixtureCandidate,
}

#[derive(Debug, Clone, Copy)]
pub struct ResidencyCandidate {
    pub id: ResidencyOptionId,
    pub logical_bytes: u64,
    pub projected_headroom_gib: f64,
    pub margin_after_reserve_gib: f64,
    pub disposition: ResidencyDisposition,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct HostMemoryBudget {
    pub total_bytes: u64,
    pub safety_reserve_bytes: u64,
    pub required_margin_bytes: u64,
}

impl HostMemoryBudget {
    pub const fn m2_max() -> Self {
        Self {
            total_bytes: 64 * GIB,
            safety_reserve_bytes: 24 * GIB,
            required_margin_bytes: 4 * GIB,
        }
    }

    const fn admissible_bytes(self) -> u64 {
        self.total_bytes - self.safety_reserve_bytes - self.required_margin_bytes
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AdmissionDecision {
    Admit,
    Reject(AdmissionRejection),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AdmissionRejection {
    UnsafeDisposition,
    ExceedsBudget,
}

impl ResidencyCandidate {
    pub fn admit_on(self, budget: HostMemoryBudget) -> AdmissionDecision {
        if self.disposition != ResidencyDisposition::SafeLogicalFixtureCandidate {
            return AdmissionDecision::Reject(AdmissionRejection::UnsafeDisposition);
        }
        if self.logical_bytes > budget.admissible_bytes() {
            return AdmissionDecision::Reject(AdmissionRejection::ExceedsBudget);
        }
        AdmissionDecision::Admit
    }
}

pub fn authoritative_candidates(
    inventory: &TrunkInventorySummary,
) -> Result<[ResidencyCandidate; 6], String> {
    inventory.validate_authoritative()?;
    let compressed = inventory.total_compressed_bytes;
    let decoded = inventory.total_decoded_f32_bytes;
    let attention = inventory
        .group("attention_mla")
        .ok_or("missing attention_mla inventory group")?
        .decoded_f32_bytes;
    let output_head = inventory
        .group("output_head")
        .ok_or("missing output_head inventory group")?
        .decoded_f32_bytes;
    let router_norms = inventory
        .group("router_norms")
        .ok_or("missing router_norms inventory group")?
        .decoded_f32_bytes;
    let hot_subset = output_head
        .checked_add(router_norms)
        .ok_or("decoded hot subset byte overflow")?;
    let hybrid = compressed
        .checked_add(hot_subset)
        .ok_or("hybrid residency byte overflow")?;

    Ok([
        ResidencyCandidate {
            id: ResidencyOptionId::ACompressedAllTrunk,
            logical_bytes: compressed,
            projected_headroom_gib: 25.852,
            margin_after_reserve_gib: 1.852,
            disposition: ResidencyDisposition::NominalOnlyRequiresMeasurement,
        },
        ResidencyCandidate {
            id: ResidencyOptionId::BDecodedAllTrunk,
            logical_bytes: decoded,
            projected_headroom_gib: -23.274,
            margin_after_reserve_gib: -47.274,
            disposition: ResidencyDisposition::UnsafeExceedsReserve,
        },
        ResidencyCandidate {
            id: ResidencyOptionId::CDecodedAttentionMlaOnly,
            logical_bytes: attention,
            projected_headroom_gib: -12.922,
            margin_after_reserve_gib: -36.922,
            disposition: ResidencyDisposition::UnsafeExceedsReserve,
        },
        ResidencyCandidate {
            id: ResidencyOptionId::DDecodedOutputHeadOnly,
            logical_bytes: output_head,
            projected_headroom_gib: 34.856,
            margin_after_reserve_gib: 10.856,
            disposition: ResidencyDisposition::SafeLogicalFixtureCandidate,
        },
        ResidencyCandidate {
            id: ResidencyOptionId::EDecodedHotSubset,
            logical_bytes: hot_subset,
            projected_headroom_gib: 34.407,
            margin_after_reserve_gib: 10.407,
            disposition: ResidencyDisposition::SafeLogicalFixtureCandidate,
        },
        ResidencyCandidate {
            id: ResidencyOptionId::FCompressedAllPlusDecodedHot,
            logical_bytes: hybrid,
            projected_headroom_gib: 21.858,
            margin_after_reserve_gib: -2.142,
            disposition: ResidencyDisposition::UnsafeExceedsReserve,
        },
    ])
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ResidencyClass {
    CompressedResident,
    DecodedResident,
    Transient,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SlotLifecycle {
    Created,
    Leased,
    Pinned,
    Released,
    Reused,
    Disposed,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ResidencySlot {
    pub slot_id: SlotId,
    pub class: ResidencyClass,
    pub lifecycle: SlotLifecycle,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ResidencyTransitionError {
    InvalidTransition { from: SlotLifecycle, to: SlotLifecycle },
}

impl ResidencySlot {
    pub const fn new(slot_id: SlotId, class: ResidencyClass) -> Self {
        Self {
            slot_id,
            class,
            lifecycle: SlotLifecycle::Created,
        }
    }

    pub fn transition(&mut self, to: SlotLifecycle) -> Result<(), ResidencyTransitionError> {
        let valid = matches!(
            (self.lifecycle, to),
            (SlotLifecycle::Created, SlotLifecycle::Leased)
                | (SlotLifecycle::Leased, SlotLifecycle::Pinned)
                | (SlotLifecycle::Pinned, SlotLifecycle::Released)
                | (SlotLifecycle::Released, SlotLifecycle::Reused)
                | (SlotLifecycle::Released, SlotLifecycle::Disposed)
                | (SlotLifecycle::Reused, SlotLifecycle::Leased)
        );
        if !valid {
            return Err(ResidencyTransitionError::InvalidTransition {
                from: self.lifecycle,
                to,
            });
        }
        self.lifecycle = to;
        Ok(())
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ResidentOrMissing<T> {
    Resident(T),
    Missing,
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::trunk_inventory::TrunkInventorySummary;
    use std::fs;
    use std::path::Path;

    fn inventory() -> TrunkInventorySummary {
        let data = fs::read_to_string(
            Path::new(env!("CARGO_MANIFEST_DIR"))
                .join("../../docs/research/glm52/raw/f016-gguf-trunk-inventory-0001.json"),
        )
        .expect("read authoritative trunk inventory");
        TrunkInventorySummary::from_json(&data).expect("inventory parses")
    }

    #[test]
    fn all_authoritative_residency_options_have_names_and_budgets() {
        let candidates = authoritative_candidates(&inventory()).expect("candidates derive");
        for (candidate, expected) in candidates.iter().zip(ResidencyOptionId::ALL) {
            assert_eq!(candidate.id, expected);
            assert!(!candidate.id.name().is_empty());
            assert!(candidate.logical_bytes > 0);
        }
        assert_eq!(candidates[0].logical_bytes, 13_474_784_256);
        assert_eq!(candidates[1].logical_bytes, 66_223_309_824);
        assert_eq!(candidates[4].logical_bytes, 4_288_466_944);
    }

    #[test]
    fn m2_max_rejects_decoded_all_and_unsafe_hybrid() {
        let candidates = authoritative_candidates(&inventory()).expect("candidates derive");
        let budget = HostMemoryBudget::m2_max();
        assert_eq!(
            candidates[1].admit_on(budget),
            AdmissionDecision::Reject(AdmissionRejection::UnsafeDisposition)
        );
        assert_eq!(
            candidates[5].admit_on(budget),
            AdmissionDecision::Reject(AdmissionRejection::UnsafeDisposition)
        );
        assert_eq!(candidates[3].admit_on(budget), AdmissionDecision::Admit);
        assert_eq!(candidates[4].admit_on(budget), AdmissionDecision::Admit);
    }

    #[test]
    fn residency_lifecycle_reuses_only_released_slots() {
        let mut slot = ResidencySlot::new(SlotId(7), ResidencyClass::CompressedResident);
        slot.transition(SlotLifecycle::Leased).unwrap();
        slot.transition(SlotLifecycle::Pinned).unwrap();
        slot.transition(SlotLifecycle::Released).unwrap();
        slot.transition(SlotLifecycle::Reused).unwrap();
        slot.transition(SlotLifecycle::Leased).unwrap();
        assert_eq!(slot.lifecycle, SlotLifecycle::Leased);
        assert!(slot.transition(SlotLifecycle::Disposed).is_err());
    }
}
