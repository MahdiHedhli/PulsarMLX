use backend::{
    ActualStatus, BenchmarkDescriptor, BenchmarkRecord, EvidenceStatus, GitDirtyState,
    MemoryGaugeDescriptor, MemoryGauges, ModelCompatibilityDescriptor, ModelCompatibilityRecord,
    ModelSupportStatus, QuantizationCompatibilityDescriptor, QuantizationCompatibilityRecord,
    QuantizationId, QuantizationStatus, ValidationCase, ValidationDescriptor,
};

fn scalar_verified_quantization() -> QuantizationCompatibilityRecord {
    QuantizationCompatibilityRecord::try_new(QuantizationCompatibilityDescriptor {
        quantization: QuantizationId::Q8Zero,
        tensor_roles: vec!["expert-weight".to_owned()],
        block_elements: 32,
        block_bytes: 34,
        row_divisibility: 32,
        malformed_case_ids: vec!["q8-malformed-v1".to_owned()],
        scalar_parity_case_ids: vec!["q8-scalar-v1".to_owned()],
        mlx_parity_case_ids: Vec::new(),
        status: QuantizationStatus::ScalarVerified,
    })
    .expect("complete scalar Q8_0 evidence is admissible")
}

fn passed_validation(case_id: &str) -> ValidationCase {
    ValidationCase::try_new(ValidationDescriptor {
        case_id: case_id.to_owned(),
        claim_scope: "bounded correctness fixture".to_owned(),
        commit: "0123456789abcdef0123456789abcdef01234567".to_owned(),
        git_dirty_state: GitDirtyState::Clean,
        evidence_level: None,
        command: "cargo test -p backend".to_owned(),
        oracle_id: Some("scalar:fixture-v1".to_owned()),
        actual_status: ActualStatus::Passed,
        actual_values_or_bounded_summary: Some("bounded fixture comparison passed".to_owned()),
        memory_gauges: None,
        warnings: Vec::new(),
        exclusions: vec!["real-model-inference".to_owned()],
        artifact_paths: vec!["docs/validation/example.json".to_owned()],
    })
    .expect("a complete executed validation record is valid")
}

#[test]
fn quantization_status_advances_only_with_required_evidence() {
    let scalar = scalar_verified_quantization();
    assert_eq!(scalar.status(), QuantizationStatus::ScalarVerified);
    assert_eq!(scalar.tensor_roles(), ["expert-weight"]);

    let mut missing_malformed = scalar.descriptor().clone();
    missing_malformed.malformed_case_ids.clear();
    assert!(QuantizationCompatibilityRecord::try_new(missing_malformed).is_err());

    let mut missing_scalar = scalar.descriptor().clone();
    missing_scalar.scalar_parity_case_ids.clear();
    assert!(QuantizationCompatibilityRecord::try_new(missing_scalar).is_err());

    let mut premature_mlx = scalar.descriptor().clone();
    premature_mlx.status = QuantizationStatus::MlxVerified;
    assert!(QuantizationCompatibilityRecord::try_new(premature_mlx).is_err());

    let mut mlx = scalar.descriptor().clone();
    mlx.status = QuantizationStatus::MlxVerified;
    mlx.mlx_parity_case_ids = vec!["q8-mlx-v1".to_owned()];
    assert!(QuantizationCompatibilityRecord::try_new(mlx).is_ok());
}

#[test]
fn quantization_layout_and_roles_are_explicit() {
    for mutate in [0_u8, 1, 2, 3] {
        let mut descriptor = scalar_verified_quantization().descriptor().clone();
        match mutate {
            0 => descriptor.tensor_roles.clear(),
            1 => descriptor.block_elements = 0,
            2 => descriptor.block_bytes = 0,
            3 => descriptor.row_divisibility = 0,
            _ => unreachable!(),
        }
        assert!(QuantizationCompatibilityRecord::try_new(descriptor).is_err());
    }
}

#[test]
fn memory_gauges_remain_independent_and_reject_an_overlapping_total() {
    let gauges = MemoryGauges::try_new(MemoryGaugeDescriptor {
        model_file_bytes: Some(1_000),
        mapped_virtual_bytes: Some(900),
        mapped_resident_bytes: Some(400),
        owned_compressed_bytes: Some(200),
        decoded_array_bytes: Some(300),
        temporary_current_bytes: Some(50),
        temporary_peak_bytes: Some(80),
        mlx_active_bytes: Some(330),
        mlx_cache_bytes: Some(40),
        mlx_peak_bytes: Some(410),
        process_footprint_bytes: Some(700),
        system_pressure: Some("normal".to_owned()),
        reported_summed_total_bytes: None,
    })
    .expect("independent gauges are valid");

    assert_eq!(gauges.model_file_bytes(), Some(1_000));
    assert_eq!(gauges.mapped_virtual_bytes(), Some(900));
    assert_eq!(gauges.mapped_resident_bytes(), Some(400));
    assert_eq!(gauges.mlx_peak_bytes(), Some(410));
    assert_eq!(gauges.process_footprint_bytes(), Some(700));
    assert_eq!(gauges.system_pressure(), Some("normal"));

    let mut overlapping = gauges.descriptor().clone();
    overlapping.reported_summed_total_bytes = Some(4_010);
    assert!(MemoryGauges::try_new(overlapping).is_err());
}

#[test]
fn memory_peak_gauges_cannot_be_below_current_gauges() {
    let descriptor = MemoryGaugeDescriptor {
        temporary_current_bytes: Some(100),
        temporary_peak_bytes: Some(99),
        ..MemoryGaugeDescriptor::default()
    };
    assert!(MemoryGauges::try_new(descriptor).is_err());

    let descriptor = MemoryGaugeDescriptor {
        mlx_active_bytes: Some(100),
        mlx_peak_bytes: Some(99),
        ..MemoryGaugeDescriptor::default()
    };
    assert!(MemoryGauges::try_new(descriptor).is_err());
}

#[test]
fn validation_case_requires_actual_results_and_clean_immutable_identity() {
    let case = passed_validation("foundation-evidence-v1");
    assert_eq!(case.actual_status(), ActualStatus::Passed);
    assert_eq!(case.evidence_status(), EvidenceStatus::ExecutedPassed);

    let mut missing_result = case.descriptor().clone();
    missing_result.actual_status = ActualStatus::NotRun;
    assert!(ValidationCase::try_new(missing_result).is_err());

    let mut unknown_commit = case.descriptor().clone();
    unknown_commit.commit = "unknown".to_owned();
    assert!(ValidationCase::try_new(unknown_commit).is_err());

    let mut dirty = case.descriptor().clone();
    dirty.git_dirty_state = GitDirtyState::Dirty;
    assert!(ValidationCase::try_new(dirty).is_err());

    let mut absent_oracle = case.descriptor().clone();
    absent_oracle.oracle_id = None;
    assert!(ValidationCase::try_new(absent_oracle).is_err());
}

#[test]
fn only_executed_passing_evidence_can_be_verified() {
    let passed = passed_validation("passed-v1");
    let verified = passed.verify().expect("passed evidence can be verified");
    assert_eq!(verified.evidence_status(), EvidenceStatus::Verified);
    assert_eq!(passed.evidence_status(), EvidenceStatus::ExecutedPassed);

    for status in [ActualStatus::Failed, ActualStatus::Blocked] {
        let mut descriptor = passed.descriptor().clone();
        descriptor.case_id = format!("{status:?}-v1");
        descriptor.actual_status = status;
        let case = ValidationCase::try_new(descriptor).expect("failed/blocked evidence is durable");
        assert!(case.verify().is_err());
    }
}

#[test]
fn verified_model_requires_identity_inventory_and_verified_evidence() {
    let evidence = passed_validation("model-slice-v1")
        .verify()
        .expect("fixture evidence verifies");
    let descriptor = ModelCompatibilityDescriptor {
        model_id: "Qwen/Qwen3-30B-A3B-GGUF".to_owned(),
        revision: "0123456789abcdef0123456789abcdef01234567".to_owned(),
        filename: "Qwen3-30B-A3B-Q8_0.gguf".to_owned(),
        sha256: Some("a".repeat(64)),
        size_bytes: Some(32_500_000_000),
        license: Some("Apache-2.0".to_owned()),
        architecture: "qwen3moe".to_owned(),
        tensor_roles: vec!["expert-weight:q8_0".to_owned()],
        execution_depth: "bounded-routed-layer".to_owned(),
        status: ModelSupportStatus::Verified,
        evidence_case_ids: vec![evidence.case_id().to_owned()],
    };

    let model = ModelCompatibilityRecord::try_new(descriptor.clone(), &[&evidence])
        .expect("verified model identity and evidence are complete");
    assert_eq!(model.status(), ModelSupportStatus::Verified);

    let mut no_checksum = descriptor.clone();
    no_checksum.sha256 = None;
    assert!(ModelCompatibilityRecord::try_new(no_checksum, &[&evidence]).is_err());

    let mut no_inventory = descriptor.clone();
    no_inventory.tensor_roles.clear();
    assert!(ModelCompatibilityRecord::try_new(no_inventory, &[&evidence]).is_err());

    let unverified = passed_validation("unverified-model-v1");
    assert!(ModelCompatibilityRecord::try_new(descriptor, &[&unverified]).is_err());
}

#[test]
fn benchmark_requires_verified_correctness_and_reproducible_samples() {
    let correctness = passed_validation("tensor-fixtures-v1")
        .verify()
        .expect("correctness verifies");
    let descriptor = BenchmarkDescriptor {
        case_id: "benchmark-v1".to_owned(),
        commit: "0123456789abcdef0123456789abcdef01234567".to_owned(),
        git_dirty_state: GitDirtyState::Clean,
        exact_command: "cargo run -p mlx-backend --bin pulsar-mlx -- benchmark".to_owned(),
        backend_id: "apple-mlx".to_owned(),
        device_id: "gpu".to_owned(),
        input_identity: "synthetic-routed-moe-v1".to_owned(),
        warmup_count: 2,
        samples_ns: vec![100, 110, 105],
        statistic: "median".to_owned(),
        correctness_case_ids: vec![correctness.case_id().to_owned()],
    };

    let benchmark = BenchmarkRecord::try_new(descriptor.clone(), &[&correctness])
        .expect("verified correctness admits a bounded benchmark");
    assert_eq!(benchmark.sample_count(), 3);

    let unverified = passed_validation("tensor-fixtures-unverified-v1");
    assert!(BenchmarkRecord::try_new(descriptor.clone(), &[&unverified]).is_err());

    let mut no_samples = descriptor.clone();
    no_samples.samples_ns.clear();
    assert!(BenchmarkRecord::try_new(no_samples, &[&correctness]).is_err());

    let mut dirty = descriptor;
    dirty.git_dirty_state = GitDirtyState::Dirty;
    assert!(BenchmarkRecord::try_new(dirty, &[&correctness]).is_err());
}
