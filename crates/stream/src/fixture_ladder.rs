use crate::{
    ArtifactRecord, BoundaryEvidence, ParityBoundary, ParityLadder, ParityLadderError,
    PortableFixtureManifest, PortableFixtureValidationError, ValidationMode,
};

#[derive(Debug)]
pub enum FixtureLadderError {
    Manifest(PortableFixtureValidationError),
    Ladder(ParityLadderError),
}

#[derive(Debug, Clone, Copy)]
pub struct FixtureLadder<'a> {
    fixture: &'a PortableFixtureManifest,
    ladder: ParityLadder,
}

impl<'a> FixtureLadder<'a> {
    pub fn new(
        fixture: &'a PortableFixtureManifest,
        mode: ValidationMode,
    ) -> Result<Self, FixtureLadderError> {
        fixture
            .validate_identity()
            .map_err(FixtureLadderError::Manifest)?;
        Ok(Self {
            fixture,
            ladder: ParityLadder::new(mode),
        })
    }

    pub const fn mode(self) -> ValidationMode {
        self.ladder.mode()
    }

    pub const fn next_boundary(self) -> Option<ParityBoundary> {
        self.ladder.next_boundary()
    }

    pub const fn passed_count(self) -> usize {
        self.ladder.passed_count()
    }

    pub const fn is_complete(self) -> bool {
        self.ladder.is_complete()
    }

    pub const fn is_stopped(self) -> bool {
        self.ladder.is_stopped()
    }

    pub fn evidence(&self, boundary: ParityBoundary) -> Option<BoundaryEvidence> {
        self.ladder.evidence(boundary)
    }

    pub fn artifact_for(&self, boundary: ParityBoundary) -> &ArtifactRecord {
        match boundary {
            ParityBoundary::ByteRange
            | ParityBoundary::QuantBlock
            | ParityBoundary::CompleteMatrix
            | ParityBoundary::MatrixReference => &self.fixture.payload,
            ParityBoundary::Router => &self.fixture.required_boundaries.router_logits,
            ParityBoundary::Projection => &self.fixture.required_boundaries.attention_or_mla_output,
            ParityBoundary::CompleteExpert => {
                &self.fixture.required_boundaries.selected_expert_output
            }
            ParityBoundary::Top8Shared => &self.fixture.required_boundaries.moe_aggregate,
            ParityBoundary::MlaDense => &self.fixture.required_boundaries.attention_or_mla_output,
            ParityBoundary::CompleteLayer => &self.fixture.required_boundaries.residual_output,
            ParityBoundary::FinalLogits => &self.fixture.required_boundaries.topk_logits,
        }
    }

    pub fn advance(
        &mut self,
        boundary: ParityBoundary,
        evidence: BoundaryEvidence,
    ) -> Result<(), FixtureLadderError> {
        let artifact = self.artifact_for(boundary);
        if artifact.byte_length == 0 || artifact.content_sha256.len() != 64 {
            return Err(FixtureLadderError::Manifest(
                PortableFixtureValidationError::MissingField(format!(
                    "boundary artifact for {boundary:?}"
                )),
            ));
        }
        self.ladder
            .advance(boundary, evidence)
            .map_err(FixtureLadderError::Ladder)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{RuntimeTelemetry, ValidationClassification};
    use std::fs;
    use std::path::Path;

    fn synthetic_fixture() -> PortableFixtureManifest {
        let path = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../specs/017-rust-native-inference-runtime/fixtures/portable-fixture-synthetic-v1.json");
        PortableFixtureManifest::from_json(&fs::read_to_string(path).unwrap()).unwrap()
    }

    fn evidence() -> BoundaryEvidence {
        let telemetry = RuntimeTelemetry::new();
        BoundaryEvidence::from_telemetry(
            ValidationClassification::GoldenIdentical,
            true,
            &telemetry,
        )
        .unwrap()
    }

    #[test]
    fn synthetic_manifest_drives_all_ordered_structural_boundaries() {
        let fixture = synthetic_fixture();
        let mut ladder = FixtureLadder::new(&fixture, ValidationMode::GoldenStrict).unwrap();
        for boundary in ParityBoundary::ORDERED {
            assert!(ladder.artifact_for(boundary).byte_length > 0);
            ladder.advance(boundary, evidence()).unwrap();
        }
        assert!(ladder.is_complete());
        assert_eq!(ladder.passed_count(), ParityBoundary::ORDERED.len());
    }

    #[test]
    fn structural_ladder_preserves_strict_stop_semantics() {
        let fixture = synthetic_fixture();
        let mut ladder = FixtureLadder::new(&fixture, ValidationMode::GoldenStrict).unwrap();
        let divergent = BoundaryEvidence {
            classification: ValidationClassification::NumericallyQualifiedGreedyDivergent,
            ..evidence()
        };
        assert!(matches!(
            ladder.advance(ParityBoundary::ByteRange, divergent),
            Err(FixtureLadderError::Ladder(
                ParityLadderError::ClassificationRejected { .. }
            ))
        ));
        assert!(ladder.is_stopped());
    }

    #[test]
    fn fixture_ladder_rejects_invalid_manifest_before_progress() {
        let mut fixture = synthetic_fixture();
        fixture.payload.byte_length = 0;
        assert!(matches!(
            FixtureLadder::new(&fixture, ValidationMode::GoldenStrict),
            Err(FixtureLadderError::Manifest(_))
        ));
    }
}
