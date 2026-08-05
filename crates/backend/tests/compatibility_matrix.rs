use backend::{
    ActualStatus, CompatibilityCellDescriptor, CompatibilityEvidenceLevel, CompatibilityMatrix,
    CompatibilityMatrixDescriptor, CompatibilityStatus, GitDirtyState, MemoryGaugeDescriptor,
    ValidationCase, ValidationDescriptor,
};

const CLEAN_COMMIT: &str = "0123456789abcdef0123456789abcdef01234567";

const ALL_LEVELS: [CompatibilityEvidenceLevel; 6] = [
    CompatibilityEvidenceLevel::ScalarFixture,
    CompatibilityEvidenceLevel::EvaluatedMlxTensorFixture,
    CompatibilityEvidenceLevel::SyntheticRoutedMoe,
    CompatibilityEvidenceLevel::BoundedRealModelSlice,
    CompatibilityEvidenceLevel::GiantModelExecution,
    CompatibilityEvidenceLevel::ProductionServing,
];

fn verified_case(
    case_id: &str,
    claim_scope: &str,
    evidence_level: CompatibilityEvidenceLevel,
) -> ValidationCase {
    ValidationCase::try_new(ValidationDescriptor {
        case_id: case_id.to_owned(),
        claim_scope: claim_scope.to_owned(),
        evidence_level: Some(evidence_level),
        commit: CLEAN_COMMIT.to_owned(),
        git_dirty_state: GitDirtyState::Clean,
        command: "cargo test -p backend --test compatibility_matrix".to_owned(),
        oracle_id: Some("independent:test-oracle-v1".to_owned()),
        actual_status: ActualStatus::Passed,
        actual_values_or_bounded_summary: Some("one exact-level result matched".to_owned()),
        memory_gauges: Some(MemoryGaugeDescriptor::default()),
        warnings: Vec::new(),
        exclusions: vec!["all-other-evidence-levels".to_owned()],
        artifact_paths: vec!["docs/validation/example.json".to_owned()],
    })
    .expect("the executed case is complete")
    .verify()
    .expect("passing executed evidence can be verified")
}

fn unsupported_cell(level: CompatibilityEvidenceLevel) -> CompatibilityCellDescriptor {
    CompatibilityCellDescriptor {
        level,
        status: CompatibilityStatus::Unsupported,
        evidence_case_ids: Vec::new(),
        explanation: Some(format!("{level:?} was not executed for this exact entry")),
    }
}

fn cells_with_one_verified(
    verified_level: CompatibilityEvidenceLevel,
    case_id: &str,
) -> Vec<CompatibilityCellDescriptor> {
    ALL_LEVELS
        .into_iter()
        .map(|level| {
            if level == verified_level {
                CompatibilityCellDescriptor {
                    level,
                    status: CompatibilityStatus::Verified,
                    evidence_case_ids: vec![case_id.to_owned()],
                    explanation: Some("verified only at this exact evidence level".to_owned()),
                }
            } else {
                unsupported_cell(level)
            }
        })
        .collect()
}

fn matrix_with_one_verified(level: CompatibilityEvidenceLevel) -> CompatibilityMatrix {
    let case_id = format!("{}-v1", level_slug(level));
    let evidence = verified_case(&case_id, &format!("{level:?} exact-scope proof"), level);
    CompatibilityMatrix::try_new(
        CompatibilityMatrixDescriptor {
            architecture: "qwen3moe".to_owned(),
            quantization: "Q8_0".to_owned(),
            cells: cells_with_one_verified(level, &case_id),
        },
        &[&evidence],
    )
    .expect("one exact verified cell plus five explicit boundaries is valid")
}

fn level_slug(level: CompatibilityEvidenceLevel) -> &'static str {
    match level {
        CompatibilityEvidenceLevel::ScalarFixture => "scalar",
        CompatibilityEvidenceLevel::EvaluatedMlxTensorFixture => "mlx-tensor",
        CompatibilityEvidenceLevel::SyntheticRoutedMoe => "synthetic-moe",
        CompatibilityEvidenceLevel::BoundedRealModelSlice => "bounded-real",
        CompatibilityEvidenceLevel::GiantModelExecution => "giant-model",
        CompatibilityEvidenceLevel::ProductionServing => "production-serving",
    }
}

fn assert_only_level_is_verified(
    matrix: &CompatibilityMatrix,
    verified_level: CompatibilityEvidenceLevel,
) {
    for level in ALL_LEVELS {
        assert_eq!(
            matrix.status(level),
            if level == verified_level {
                CompatibilityStatus::Verified
            } else {
                CompatibilityStatus::Unsupported
            },
            "evidence at {verified_level:?} must not imply {level:?}"
        );
        assert_eq!(matrix.is_verified(level), level == verified_level);
    }
}

#[test]
fn scalar_fixture_evidence_does_not_imply_mlx_synthetic_or_model_execution() {
    let matrix = matrix_with_one_verified(CompatibilityEvidenceLevel::ScalarFixture);
    assert_only_level_is_verified(&matrix, CompatibilityEvidenceLevel::ScalarFixture);
}

#[test]
fn evaluated_mlx_tensor_evidence_does_not_imply_routing_or_model_execution() {
    let matrix = matrix_with_one_verified(CompatibilityEvidenceLevel::EvaluatedMlxTensorFixture);
    assert_only_level_is_verified(
        &matrix,
        CompatibilityEvidenceLevel::EvaluatedMlxTensorFixture,
    );
}

#[test]
fn synthetic_moe_evidence_does_not_imply_any_real_model_depth() {
    let matrix = matrix_with_one_verified(CompatibilityEvidenceLevel::SyntheticRoutedMoe);
    assert_only_level_is_verified(&matrix, CompatibilityEvidenceLevel::SyntheticRoutedMoe);
}

#[test]
fn bounded_real_model_evidence_does_not_imply_giant_execution_or_serving() {
    let matrix = matrix_with_one_verified(CompatibilityEvidenceLevel::BoundedRealModelSlice);
    assert_only_level_is_verified(&matrix, CompatibilityEvidenceLevel::BoundedRealModelSlice);
}

#[test]
fn giant_model_evidence_does_not_imply_bounded_slice_or_production_serving() {
    let matrix = matrix_with_one_verified(CompatibilityEvidenceLevel::GiantModelExecution);
    assert_only_level_is_verified(&matrix, CompatibilityEvidenceLevel::GiantModelExecution);
}

#[test]
fn production_serving_evidence_does_not_backfill_any_other_evidence_level() {
    let matrix = matrix_with_one_verified(CompatibilityEvidenceLevel::ProductionServing);
    assert_only_level_is_verified(&matrix, CompatibilityEvidenceLevel::ProductionServing);
}

#[test]
fn matrix_requires_one_explicit_cell_for_every_evidence_level() {
    let evidence = verified_case(
        "synthetic-only-v1",
        "synthetic routed-MoE exact proof",
        CompatibilityEvidenceLevel::SyntheticRoutedMoe,
    );
    let mut cells = cells_with_one_verified(
        CompatibilityEvidenceLevel::SyntheticRoutedMoe,
        evidence.case_id(),
    );
    cells.retain(|cell| cell.level != CompatibilityEvidenceLevel::ProductionServing);

    let missing = CompatibilityMatrixDescriptor {
        architecture: "synthetic-routed-moe-v1".to_owned(),
        quantization: "f32".to_owned(),
        cells,
    };
    assert!(CompatibilityMatrix::try_new(missing, &[&evidence]).is_err());

    let mut duplicate_cells = cells_with_one_verified(
        CompatibilityEvidenceLevel::SyntheticRoutedMoe,
        evidence.case_id(),
    );
    duplicate_cells.push(unsupported_cell(
        CompatibilityEvidenceLevel::SyntheticRoutedMoe,
    ));
    let duplicate = CompatibilityMatrixDescriptor {
        architecture: "synthetic-routed-moe-v1".to_owned(),
        quantization: "f32".to_owned(),
        cells: duplicate_cells,
    };
    assert!(CompatibilityMatrix::try_new(duplicate, &[&evidence]).is_err());
}

#[test]
fn verified_cells_require_an_exact_supplied_verified_case() {
    let executed = ValidationCase::try_new(ValidationDescriptor {
        case_id: "executed-not-verified-v1".to_owned(),
        claim_scope: "bounded real-model slice".to_owned(),
        evidence_level: Some(CompatibilityEvidenceLevel::BoundedRealModelSlice),
        commit: CLEAN_COMMIT.to_owned(),
        git_dirty_state: GitDirtyState::Clean,
        command: "cargo test -p backend --test compatibility_matrix".to_owned(),
        oracle_id: Some("independent:test-oracle-v1".to_owned()),
        actual_status: ActualStatus::Passed,
        actual_values_or_bounded_summary: Some("one exact-level result matched".to_owned()),
        memory_gauges: Some(MemoryGaugeDescriptor::default()),
        warnings: Vec::new(),
        exclusions: Vec::new(),
        artifact_paths: vec!["docs/validation/example.json".to_owned()],
    })
    .expect("executed passing evidence is valid before verification");
    let descriptor = CompatibilityMatrixDescriptor {
        architecture: "qwen3moe".to_owned(),
        quantization: "Q8_0".to_owned(),
        cells: cells_with_one_verified(
            CompatibilityEvidenceLevel::BoundedRealModelSlice,
            executed.case_id(),
        ),
    };

    assert!(CompatibilityMatrix::try_new(descriptor.clone(), &[]).is_err());
    assert!(CompatibilityMatrix::try_new(descriptor, &[&executed]).is_err());
}

#[test]
fn verified_cells_reject_evidence_from_a_different_claim_level() {
    let scalar = verified_case(
        "scalar-only-v1",
        "scalar Q8_0 fixture",
        CompatibilityEvidenceLevel::ScalarFixture,
    );
    let descriptor = CompatibilityMatrixDescriptor {
        architecture: "qwen3moe".to_owned(),
        quantization: "Q8_0".to_owned(),
        cells: cells_with_one_verified(
            CompatibilityEvidenceLevel::GiantModelExecution,
            scalar.case_id(),
        ),
    };

    assert!(CompatibilityMatrix::try_new(descriptor, &[&scalar]).is_err());
}

#[test]
fn every_nonverified_cell_requires_a_bounded_explanation() {
    for status in [
        CompatibilityStatus::Planned,
        CompatibilityStatus::Unsupported,
        CompatibilityStatus::Blocked,
    ] {
        let evidence = verified_case(
            "scalar-boundary-v1",
            "scalar fixture exact proof",
            CompatibilityEvidenceLevel::ScalarFixture,
        );
        let mut cells = cells_with_one_verified(
            CompatibilityEvidenceLevel::ScalarFixture,
            evidence.case_id(),
        );
        let production = cells
            .iter_mut()
            .find(|cell| cell.level == CompatibilityEvidenceLevel::ProductionServing)
            .expect("the complete matrix contains production serving");
        production.status = status;
        production.explanation = None;

        let descriptor = CompatibilityMatrixDescriptor {
            architecture: "qwen3moe".to_owned(),
            quantization: "Q8_0".to_owned(),
            cells,
        };
        assert!(CompatibilityMatrix::try_new(descriptor, &[&evidence]).is_err());
    }
}
