use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum NumericalClassification {
    GoldenIdentical,
    NumericallyQualifiedGreedyNotApplicable,
    NumericallyQualifiedGreedyIdentical,
    NumericallyQualifiedGreedyDivergent,
    NumericallyFailed,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum GreedyApplicability {
    NotApplicable,
    Applicable,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct GreedyIdentityEvidence {
    pub top_k_ids_exact: bool,
    pub argmax_exact: bool,
}

pub fn validate_classification_applicability(
    classification: NumericalClassification,
    applicability: GreedyApplicability,
    identity: Option<&GreedyIdentityEvidence>,
) -> Result<(), &'static str> {
    match (classification, applicability, identity) {
        (
            NumericalClassification::NumericallyQualifiedGreedyNotApplicable,
            GreedyApplicability::NotApplicable,
            None,
        )
        | (NumericalClassification::GoldenIdentical, GreedyApplicability::NotApplicable, None)
        | (NumericalClassification::NumericallyFailed, _, _) => Ok(()),
        (
            NumericalClassification::NumericallyQualifiedGreedyIdentical,
            GreedyApplicability::Applicable,
            Some(identity),
        )
        | (
            NumericalClassification::GoldenIdentical,
            GreedyApplicability::Applicable,
            Some(identity),
        ) if identity.top_k_ids_exact && identity.argmax_exact => Ok(()),
        (
            NumericalClassification::NumericallyQualifiedGreedyDivergent,
            GreedyApplicability::Applicable,
            Some(identity),
        ) if !identity.top_k_ids_exact || !identity.argmax_exact => Ok(()),
        (
            NumericalClassification::NumericallyQualifiedGreedyIdentical,
            GreedyApplicability::NotApplicable,
            _,
        ) => Err("greedy-identical classification requires an applicable greedy decision"),
        (
            NumericalClassification::NumericallyQualifiedGreedyNotApplicable,
            GreedyApplicability::Applicable,
            _,
        ) => Err("greedy-not-applicable classification cannot describe an applicable decision"),
        (
            NumericalClassification::NumericallyQualifiedGreedyIdentical,
            GreedyApplicability::Applicable,
            _,
        )
        | (NumericalClassification::GoldenIdentical, GreedyApplicability::Applicable, _) => {
            Err("greedy-identical classification requires exact top-k and argmax evidence")
        }
        (
            NumericalClassification::NumericallyQualifiedGreedyDivergent,
            GreedyApplicability::NotApplicable,
            _,
        ) => Err("greedy divergence requires an applicable greedy decision"),
        (
            NumericalClassification::NumericallyQualifiedGreedyDivergent,
            GreedyApplicability::Applicable,
            _,
        ) => Err("greedy divergence requires changed top-k or argmax evidence"),
        (_, GreedyApplicability::NotApplicable, Some(_)) => {
            Err("greedy identity evidence is forbidden when greedy selection is not applicable")
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn exact_identity() -> GreedyIdentityEvidence {
        GreedyIdentityEvidence {
            top_k_ids_exact: true,
            argmax_exact: true,
        }
    }

    #[test]
    fn rejects_greedy_identical_when_not_applicable() {
        assert!(validate_classification_applicability(
            NumericalClassification::NumericallyQualifiedGreedyIdentical,
            GreedyApplicability::NotApplicable,
            None,
        )
        .is_err());
    }

    #[test]
    fn rejects_greedy_identical_without_identity_evidence() {
        assert!(validate_classification_applicability(
            NumericalClassification::NumericallyQualifiedGreedyIdentical,
            GreedyApplicability::Applicable,
            None,
        )
        .is_err());
    }

    #[test]
    fn accepts_qualified_non_greedy_boundary() {
        assert!(validate_classification_applicability(
            NumericalClassification::NumericallyQualifiedGreedyNotApplicable,
            GreedyApplicability::NotApplicable,
            None,
        )
        .is_ok());
    }

    #[test]
    fn accepts_applicable_exact_top_k_and_argmax() {
        assert!(validate_classification_applicability(
            NumericalClassification::NumericallyQualifiedGreedyIdentical,
            GreedyApplicability::Applicable,
            Some(&exact_identity()),
        )
        .is_ok());
    }

    #[test]
    fn changed_greedy_choice_cannot_be_not_applicable() {
        let changed = GreedyIdentityEvidence {
            top_k_ids_exact: false,
            argmax_exact: false,
        };
        assert!(validate_classification_applicability(
            NumericalClassification::NumericallyQualifiedGreedyNotApplicable,
            GreedyApplicability::Applicable,
            Some(&changed),
        )
        .is_err());
        assert!(validate_classification_applicability(
            NumericalClassification::NumericallyQualifiedGreedyDivergent,
            GreedyApplicability::Applicable,
            Some(&changed),
        )
        .is_ok());
    }
}
