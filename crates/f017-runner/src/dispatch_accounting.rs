//! Route-independent conceptual/native dispatch reconciliation for later M1-F evidence.

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
}

#[derive(Debug, Default, Clone, PartialEq, Eq)]
pub struct DispatchAccounting {
    native: BTreeMap<DispatchRole, u64>,
    conceptual: BTreeMap<DispatchRole, u64>,
    scaffold: u64,
    explicit_reference: u64,
    fallback: u64,
    backend_errors: u64,
}

impl DispatchAccounting {
    pub fn record_native(&mut self, role: DispatchRole) {
        *self.native.entry(role).or_default() += 1;
        *self.conceptual.entry(role).or_default() += 1;
    }

    pub fn native_for(&self, role: DispatchRole) -> u64 {
        self.native.get(&role).copied().unwrap_or_default()
    }

    pub fn native_total(&self) -> u64 {
        self.native.values().sum()
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

    pub fn reconcile_native(&self, expected: &BTreeMap<DispatchRole, u64>) -> bool {
        &self.native == expected
    }
}

#[cfg(test)]
mod tests {
    use super::{DispatchAccounting, DispatchRole};
    use std::collections::BTreeMap;

    #[test]
    fn generic_layer_roles_reconcile_without_freezing_a_route() {
        let mut accounting = DispatchAccounting::default();
        // q_a, q_b, kv_a, k_b, and v_b; output is classified separately.
        for _ in 0..5 {
            accounting.record_native(DispatchRole::AttentionProjection);
        }
        accounting.record_native(DispatchRole::AttentionOutput);
        accounting.record_native(DispatchRole::Router);
        for _ in 0..8 {
            accounting.record_native(DispatchRole::RoutedExpertGate);
            accounting.record_native(DispatchRole::RoutedExpertUp);
            accounting.record_native(DispatchRole::RoutedExpertDown);
        }
        accounting.record_native(DispatchRole::SharedExpertGate);
        accounting.record_native(DispatchRole::SharedExpertUp);
        accounting.record_native(DispatchRole::SharedExpertDown);

        let expected = BTreeMap::from([
            (DispatchRole::AttentionProjection, 5),
            (DispatchRole::AttentionOutput, 1),
            (DispatchRole::Router, 1),
            (DispatchRole::RoutedExpertGate, 8),
            (DispatchRole::RoutedExpertUp, 8),
            (DispatchRole::RoutedExpertDown, 8),
            (DispatchRole::SharedExpertGate, 1),
            (DispatchRole::SharedExpertUp, 1),
            (DispatchRole::SharedExpertDown, 1),
        ]);
        assert!(accounting.reconcile_native(&expected));
        assert_eq!(accounting.native_total(), 34);
        assert!(accounting.production_clean());
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
