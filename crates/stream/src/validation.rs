use crate::{RuntimeTelemetry, TelemetryError, TelemetrySnapshot};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ValidationMode {
    GoldenStrict,
    TeacherForcedValidation,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ValidationClassification {
    GoldenIdentical,
    NumericallyQualifiedGreedyIdentical,
    NumericallyQualifiedGreedyDivergent,
    NumericallyFailed,
}

impl ValidationClassification {
    fn accepted_by(self, mode: ValidationMode) -> bool {
        match mode {
            ValidationMode::GoldenStrict => self == Self::GoldenIdentical,
            ValidationMode::TeacherForcedValidation => matches!(
                self,
                Self::GoldenIdentical
                    | Self::NumericallyQualifiedGreedyIdentical
                    | Self::NumericallyQualifiedGreedyDivergent
            ),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ParityBoundary {
    ByteRange,
    QuantBlock,
    CompleteMatrix,
    MatrixReference,
    Router,
    Projection,
    CompleteExpert,
    Top8Shared,
    MlaDense,
    CompleteLayer,
    FinalLogits,
}

impl ParityBoundary {
    pub const ORDERED: [Self; 11] = [
        Self::ByteRange,
        Self::QuantBlock,
        Self::CompleteMatrix,
        Self::MatrixReference,
        Self::Router,
        Self::Projection,
        Self::CompleteExpert,
        Self::Top8Shared,
        Self::MlaDense,
        Self::CompleteLayer,
        Self::FinalLogits,
    ];
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct BoundaryEvidence {
    pub classification: ValidationClassification,
    pub memory_admitted: bool,
    pub telemetry: TelemetrySnapshot,
}

impl BoundaryEvidence {
    pub fn from_telemetry(
        classification: ValidationClassification,
        memory_admitted: bool,
        telemetry: &RuntimeTelemetry,
    ) -> Result<Self, TelemetryError> {
        Ok(Self {
            classification,
            memory_admitted,
            telemetry: telemetry.snapshot()?,
        })
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ParityLadderError {
    Stopped,
    OutOfOrder {
        expected: ParityBoundary,
        received: ParityBoundary,
    },
    MemoryRejected(ParityBoundary),
    ClassificationRejected {
        boundary: ParityBoundary,
        classification: ValidationClassification,
    },
}

#[derive(Debug, Clone, Copy)]
pub struct ParityLadder {
    mode: ValidationMode,
    next_index: usize,
    stopped: bool,
    evidence: [Option<BoundaryEvidence>; ParityBoundary::ORDERED.len()],
}

impl ParityLadder {
    pub fn new(mode: ValidationMode) -> Self {
        Self {
            mode,
            next_index: 0,
            stopped: false,
            evidence: [None; ParityBoundary::ORDERED.len()],
        }
    }

    pub const fn mode(self) -> ValidationMode {
        self.mode
    }

    pub const fn next_boundary(self) -> Option<ParityBoundary> {
        if self.stopped || self.next_index >= ParityBoundary::ORDERED.len() {
            None
        } else {
            Some(ParityBoundary::ORDERED[self.next_index])
        }
    }

    pub const fn is_complete(self) -> bool {
        !self.stopped && self.next_index == ParityBoundary::ORDERED.len()
    }

    pub const fn is_stopped(self) -> bool {
        self.stopped
    }

    pub const fn passed_count(self) -> usize {
        self.next_index
    }

    pub fn evidence(&self, boundary: ParityBoundary) -> Option<BoundaryEvidence> {
        let index = ParityBoundary::ORDERED
            .iter()
            .position(|item| *item == boundary)?;
        self.evidence[index]
    }

    pub fn advance(
        &mut self,
        boundary: ParityBoundary,
        evidence: BoundaryEvidence,
    ) -> Result<(), ParityLadderError> {
        if self.stopped || self.is_complete() {
            return Err(ParityLadderError::Stopped);
        }
        let expected = ParityBoundary::ORDERED[self.next_index];
        if boundary != expected {
            return Err(ParityLadderError::OutOfOrder {
                expected,
                received: boundary,
            });
        }
        if !evidence.memory_admitted {
            self.stopped = true;
            return Err(ParityLadderError::MemoryRejected(boundary));
        }
        if !evidence.classification.accepted_by(self.mode) {
            self.stopped = true;
            return Err(ParityLadderError::ClassificationRejected {
                boundary,
                classification: evidence.classification,
            });
        }
        self.evidence[self.next_index] = Some(evidence);
        self.next_index += 1;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::TelemetryBucket;
    use std::time::Duration;

    fn evidence(classification: ValidationClassification) -> BoundaryEvidence {
        let telemetry = RuntimeTelemetry::new();
        BoundaryEvidence::from_telemetry(classification, true, &telemetry).unwrap()
    }

    #[test]
    fn golden_strict_requires_golden_identical_and_stops() {
        let mut ladder = ParityLadder::new(ValidationMode::GoldenStrict);
        assert_eq!(ladder.next_boundary(), Some(ParityBoundary::ByteRange));
        assert_eq!(
            ladder.advance(
                ParityBoundary::ByteRange,
                evidence(ValidationClassification::NumericallyQualifiedGreedyDivergent)
            ),
            Err(ParityLadderError::ClassificationRejected {
                boundary: ParityBoundary::ByteRange,
                classification: ValidationClassification::NumericallyQualifiedGreedyDivergent,
            })
        );
        assert!(ladder.is_stopped());
        assert_eq!(ladder.next_boundary(), None);
    }

    #[test]
    fn teacher_forced_mode_can_continue_after_greedy_divergence() {
        let mut ladder = ParityLadder::new(ValidationMode::TeacherForcedValidation);
        ladder
            .advance(
                ParityBoundary::ByteRange,
                evidence(ValidationClassification::NumericallyQualifiedGreedyDivergent),
            )
            .unwrap();
        assert_eq!(ladder.passed_count(), 1);
        assert_eq!(
            ladder
                .evidence(ParityBoundary::ByteRange)
                .unwrap()
                .classification,
            ValidationClassification::NumericallyQualifiedGreedyDivergent
        );
    }

    #[test]
    fn ladder_enforces_order_and_memory_admission() {
        let mut ladder = ParityLadder::new(ValidationMode::GoldenStrict);
        assert_eq!(
            ladder.advance(
                ParityBoundary::Router,
                evidence(ValidationClassification::GoldenIdentical)
            ),
            Err(ParityLadderError::OutOfOrder {
                expected: ParityBoundary::ByteRange,
                received: ParityBoundary::Router,
            })
        );
        assert_eq!(
            ladder.advance(
                ParityBoundary::ByteRange,
                BoundaryEvidence {
                    classification: ValidationClassification::GoldenIdentical,
                    memory_admitted: false,
                    telemetry: TelemetrySnapshot::default(),
                }
            ),
            Err(ParityLadderError::MemoryRejected(ParityBoundary::ByteRange))
        );
        assert!(ladder.is_stopped());
    }

    #[test]
    fn ladder_can_reach_final_logits_only_in_order() {
        let mut ladder = ParityLadder::new(ValidationMode::GoldenStrict);
        let telemetry = {
            let mut value = RuntimeTelemetry::new();
            value
                .record_stage(TelemetryBucket::Compute, Duration::from_nanos(7), 1)
                .unwrap();
            value
        };
        for boundary in ParityBoundary::ORDERED {
            ladder
                .advance(
                    boundary,
                    BoundaryEvidence::from_telemetry(
                        ValidationClassification::GoldenIdentical,
                        true,
                        &telemetry,
                    )
                    .unwrap(),
                )
                .unwrap();
        }
        assert!(ladder.is_complete());
        assert_eq!(ladder.passed_count(), 11);
        assert_eq!(
            ladder.advance(
                ParityBoundary::FinalLogits,
                evidence(ValidationClassification::GoldenIdentical)
            ),
            Err(ParityLadderError::Stopped)
        );
    }

    #[test]
    fn poisoned_telemetry_cannot_create_boundary_evidence() {
        let mut telemetry = RuntimeTelemetry::new();
        telemetry
            .record_stage(
                TelemetryBucket::Compute,
                Duration::new(u64::MAX, 999_999_999),
                0,
            )
            .unwrap_err();
        assert_eq!(
            BoundaryEvidence::from_telemetry(
                ValidationClassification::GoldenIdentical,
                true,
                &telemetry,
            ),
            Err(TelemetryError::Poisoned)
        );
    }
}
