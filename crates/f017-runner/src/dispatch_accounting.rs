//! Route-independent conceptual/native dispatch reconciliation for later M1-F evidence.
//!
//! Conceptual model operations and native backend launches are deliberately
//! separate: production may fuse or batch routed expert work, so a conceptual
//! `gate/up/down × N` inventory must never be mistaken for a native launch
//! count. The exact M1-F total is derived from emitted launch events only after
//! the selected route and production path are frozen.

use std::collections::BTreeMap;

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum DispatchRole {
    AttentionProjection,
    AttentionOutput,
    Router,
    RoutedExpertGate,
    RoutedExpertUp,
    RoutedExpertDown,
    SharedExpertGate,
    SharedExpertUp,
    SharedExpertDown,
    Normalization,
    NonMlx,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DispatchScaling {
    ConstantPerRepeat,
    PerSelectedExpert,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct NativeDispatchEvent {
    dispatches_per_unit: u64,
    scaling: DispatchScaling,
}

#[derive(Debug, Default, Clone, PartialEq, Eq)]
pub struct DispatchAccounting {
    conceptual: BTreeMap<DispatchRole, u64>,
    native_events: BTreeMap<String, NativeDispatchEvent>,
    scaffold: u64,
    explicit_reference: u64,
    fallback: u64,
    backend_errors: u64,
}

impl DispatchAccounting {
    pub fn record_conceptual(&mut self, role: DispatchRole, multiplicity: u64) {
        assert!(multiplicity > 0, "conceptual multiplicity must be positive");
        *self.conceptual.entry(role).or_default() += multiplicity;
    }

    pub fn conceptual_for(&self, role: DispatchRole) -> u64 {
        self.conceptual.get(&role).copied().unwrap_or_default()
    }

    pub fn conceptual_total(&self) -> u64 {
        self.conceptual.values().sum()
    }

    pub fn record_native_event(
        &mut self,
        event: impl Into<String>,
        dispatches_per_unit: u64,
        scaling: DispatchScaling,
    ) -> Result<(), &'static str> {
        let event = event.into();
        if event.is_empty() || dispatches_per_unit == 0 {
            return Err("native event identity and count must be nonzero");
        }
        if self
            .native_events
            .insert(
                event,
                NativeDispatchEvent {
                    dispatches_per_unit,
                    scaling,
                },
            )
            .is_some()
        {
            return Err("duplicate native dispatch event");
        }
        Ok(())
    }

    pub fn expected_native_total(&self, selected_expert_count: u64) -> Result<u64, &'static str> {
        if selected_expert_count == 0 || self.native_events.is_empty() {
            return Err("selected expert count and native event plan must be nonzero");
        }
        self.native_events.values().try_fold(0_u64, |total, event| {
            let multiplier = match event.scaling {
                DispatchScaling::ConstantPerRepeat => 1,
                DispatchScaling::PerSelectedExpert => selected_expert_count,
            };
            let contribution = event
                .dispatches_per_unit
                .checked_mul(multiplier)
                .ok_or("native dispatch multiplication overflow")?;
            total
                .checked_add(contribution)
                .ok_or("native dispatch total overflow")
        })
    }

    pub fn validate_conceptual_surface(&self, selected_expert_count: u64) -> bool {
        if selected_expert_count == 0 {
            return false;
        }
        let required = [
            DispatchRole::AttentionProjection,
            DispatchRole::AttentionOutput,
            DispatchRole::Router,
            DispatchRole::RoutedExpertGate,
            DispatchRole::RoutedExpertUp,
            DispatchRole::RoutedExpertDown,
            DispatchRole::SharedExpertGate,
            DispatchRole::SharedExpertUp,
            DispatchRole::SharedExpertDown,
            DispatchRole::Normalization,
            DispatchRole::NonMlx,
        ];
        required.into_iter().all(|role| self.conceptual_for(role) > 0)
            && [
                DispatchRole::RoutedExpertGate,
                DispatchRole::RoutedExpertUp,
                DispatchRole::RoutedExpertDown,
            ]
            .into_iter()
            .all(|role| self.conceptual_for(role) == selected_expert_count)
            && [
                DispatchRole::AttentionOutput,
                DispatchRole::Router,
                DispatchRole::SharedExpertGate,
                DispatchRole::SharedExpertUp,
                DispatchRole::SharedExpertDown,
            ]
            .into_iter()
            .all(|role| self.conceptual_for(role) == 1)
    }

    pub fn record_scaffold(&mut self) {
        self.scaffold += 1;
    }

    pub fn record_explicit_reference(&mut self) {
        self.explicit_reference += 1;
    }

    pub fn record_fallback(&mut self) {
        self.fallback += 1;
    }

    pub fn record_backend_error(&mut self) {
        self.backend_errors += 1;
    }

    pub fn production_clean(&self) -> bool {
        self.scaffold == 0
            && self.explicit_reference == 0
            && self.fallback == 0
            && self.backend_errors == 0
    }
}

#[cfg(test)]
mod tests {
    use super::{DispatchAccounting, DispatchRole, DispatchScaling};

    fn conceptual_layer(accounting: &mut DispatchAccounting, selected: u64) {
        accounting.record_conceptual(DispatchRole::AttentionProjection, 5);
        accounting.record_conceptual(DispatchRole::AttentionOutput, 1);
        accounting.record_conceptual(DispatchRole::Router, 1);
        accounting.record_conceptual(DispatchRole::RoutedExpertGate, selected);
        accounting.record_conceptual(DispatchRole::RoutedExpertUp, selected);
        accounting.record_conceptual(DispatchRole::RoutedExpertDown, selected);
        accounting.record_conceptual(DispatchRole::SharedExpertGate, 1);
        accounting.record_conceptual(DispatchRole::SharedExpertUp, 1);
        accounting.record_conceptual(DispatchRole::SharedExpertDown, 1);
        accounting.record_conceptual(DispatchRole::Normalization, 2);
        accounting.record_conceptual(DispatchRole::NonMlx, 1);
    }

    #[test]
    fn conceptual_and_native_surfaces_are_independent_and_fusion_safe() {
        let mut accounting = DispatchAccounting::default();
        conceptual_layer(&mut accounting, 8);
        accounting
            .record_native_event("attention_pipeline", 6, DispatchScaling::ConstantPerRepeat)
            .unwrap();
        accounting
            .record_native_event("router_projection", 1, DispatchScaling::ConstantPerRepeat)
            .unwrap();
        accounting
            .record_native_event("routed_gate_up_fused", 1, DispatchScaling::ConstantPerRepeat)
            .unwrap();
        accounting
            .record_native_event("routed_down_fused", 1, DispatchScaling::ConstantPerRepeat)
            .unwrap();
        accounting
            .record_native_event("shared_triplet", 3, DispatchScaling::ConstantPerRepeat)
            .unwrap();

        assert!(accounting.validate_conceptual_surface(8));
        assert_eq!(accounting.conceptual_for(DispatchRole::RoutedExpertGate), 8);
        assert_eq!(accounting.conceptual_total(), 37);
        assert_eq!(accounting.expected_native_total(8).unwrap(), 12);
        assert!(accounting.production_clean());
    }

    #[test]
    fn per_expert_native_scaling_is_derived_not_hard_coded() {
        let mut accounting = DispatchAccounting::default();
        conceptual_layer(&mut accounting, 8);
        accounting
            .record_native_event("constant", 7, DispatchScaling::ConstantPerRepeat)
            .unwrap();
        accounting
            .record_native_event("per_expert", 2, DispatchScaling::PerSelectedExpert)
            .unwrap();
        assert_eq!(accounting.expected_native_total(8).unwrap(), 23);
        assert_eq!(accounting.expected_native_total(3).unwrap(), 13);
    }

    #[test]
    fn duplicate_events_incomplete_surfaces_and_overflow_fail_closed() {
        let mut accounting = DispatchAccounting::default();
        assert!(!accounting.validate_conceptual_surface(8));
        accounting
            .record_native_event("event", 1, DispatchScaling::ConstantPerRepeat)
            .unwrap();
        assert!(accounting
            .record_native_event("event", 1, DispatchScaling::ConstantPerRepeat)
            .is_err());
        let mut overflow = DispatchAccounting::default();
        overflow
            .record_native_event("overflow", u64::MAX, DispatchScaling::PerSelectedExpert)
            .unwrap();
        assert!(overflow.expected_native_total(8).is_err());
    }

    #[test]
    fn reference_fallback_and_errors_are_not_production_clean() {
        let mut accounting = DispatchAccounting::default();
        accounting.record_scaffold();
        accounting.record_explicit_reference();
        accounting.record_fallback();
        accounting.record_backend_error();
        assert!(!accounting.production_clean());
    }
}
