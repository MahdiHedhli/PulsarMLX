use backend::{
    ActualStatus, BenchmarkDescriptor, BenchmarkRecord, CompatibilityEvidenceLevel, ErrorCategory,
    EvidenceStatus, GitDirtyState, MemoryGaugeDescriptor, ValidationCase, ValidationDescriptor,
};

const CLEAN_COMMIT: &str = "0123456789abcdef0123456789abcdef01234567";

fn validation_descriptor(case_id: &str, actual_status: ActualStatus) -> ValidationDescriptor {
    ValidationDescriptor {
        case_id: case_id.to_owned(),
        claim_scope: "bounded correctness fixture".to_owned(),
        commit: CLEAN_COMMIT.to_owned(),
        git_dirty_state: GitDirtyState::Clean,
        evidence_level: None::<CompatibilityEvidenceLevel>,
        command: "cargo test -p backend --test validation_records".to_owned(),
        oracle_id: Some("scalar:validation-records-v1".to_owned()),
        actual_status,
        actual_values_or_bounded_summary: Some("one bounded result matched".to_owned()),
        memory_gauges: Some(MemoryGaugeDescriptor::default()),
        warnings: Vec::new(),
        exclusions: vec!["model inference".to_owned()],
        artifact_paths: vec!["docs/validation/example.json".to_owned()],
    }
}

fn passed_validation(case_id: &str) -> ValidationCase {
    ValidationCase::try_new(validation_descriptor(case_id, ActualStatus::Passed))
        .expect("a complete passing validation record is admissible")
}

fn verified_validation(case_id: &str) -> ValidationCase {
    passed_validation(case_id)
        .verify()
        .expect("executed passing evidence can be verified")
}

fn benchmark_descriptor(correctness_case_ids: Vec<String>) -> BenchmarkDescriptor {
    BenchmarkDescriptor {
        case_id: "bounded-benchmark-v1".to_owned(),
        commit: CLEAN_COMMIT.to_owned(),
        git_dirty_state: GitDirtyState::Clean,
        exact_command: "cargo run -p mlx-backend --bin pulsar-mlx -- benchmark".to_owned(),
        backend_id: "apple-mlx".to_owned(),
        device_id: "gpu".to_owned(),
        input_identity: "synthetic-routed-moe-v1".to_owned(),
        warmup_count: 2,
        samples_ns: vec![100, 105, 110],
        statistic: "median nanoseconds".to_owned(),
        correctness_case_ids,
    }
}

#[test]
fn validation_requires_an_actual_value_or_bounded_summary() {
    let complete = passed_validation("complete-result-v1");
    assert_eq!(complete.actual_status(), ActualStatus::Passed);
    assert_eq!(complete.evidence_status(), EvidenceStatus::ExecutedPassed);

    for actual in [None, Some(String::new()), Some("   ".to_owned())] {
        let mut descriptor = validation_descriptor("missing-result-v1", ActualStatus::Passed);
        descriptor.actual_values_or_bounded_summary = actual;

        let error = ValidationCase::try_new(descriptor)
            .expect_err("status alone must not substitute for an actual result");
        assert_eq!(error.category(), ErrorCategory::InvalidEvidence);
        assert_eq!(error.code(), "missing_actual_result");
    }

    let descriptor = validation_descriptor("not-run-v1", ActualStatus::NotRun);
    let error = ValidationCase::try_new(descriptor)
        .expect_err("a not-run case is not executed validation evidence");
    assert_eq!(error.category(), ErrorCategory::InvalidEvidence);
    assert_eq!(error.code(), "missing_actual_result");
}

#[test]
fn validation_rejects_dirty_or_unknown_source_identity() {
    for dirty_state in [GitDirtyState::Dirty, GitDirtyState::Unknown] {
        let mut descriptor = validation_descriptor("mutable-source-v1", ActualStatus::Passed);
        descriptor.git_dirty_state = dirty_state;

        let error = ValidationCase::try_new(descriptor)
            .expect_err("validation evidence requires a known-clean source tree");
        assert_eq!(error.category(), ErrorCategory::InvalidEvidence);
        assert_eq!(error.code(), "nonimmutable_validation");
    }

    for commit in [
        "unknown".to_owned(),
        "a".repeat(39),
        format!("{}g", "a".repeat(39)),
    ] {
        let mut descriptor = validation_descriptor("unknown-commit-v1", ActualStatus::Passed);
        descriptor.commit = commit;

        let error = ValidationCase::try_new(descriptor)
            .expect_err("an abbreviated, unknown, or nonhex commit is not immutable identity");
        assert_eq!(error.category(), ErrorCategory::InvalidEvidence);
        assert_eq!(error.code(), "invalid_commit_identity");
    }
}

#[test]
fn validation_requires_a_bounded_independent_oracle_identity() {
    for oracle_id in [None, Some(String::new()), Some("   ".to_owned())] {
        let mut descriptor = validation_descriptor("missing-oracle-v1", ActualStatus::Passed);
        descriptor.oracle_id = oracle_id;

        let error = ValidationCase::try_new(descriptor)
            .expect_err("correctness evidence without an oracle cannot be admitted");
        assert_eq!(error.category(), ErrorCategory::InvalidEvidence);
        assert_eq!(error.code(), "missing_validation_oracle");
    }
}

#[test]
fn validation_rejects_a_summed_overlapping_memory_gauge() {
    let mut descriptor = validation_descriptor("overlapping-memory-v1", ActualStatus::Passed);
    descriptor.memory_gauges = Some(MemoryGaugeDescriptor {
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
        reported_summed_total_bytes: Some(4_010),
    });

    let error = ValidationCase::try_new(descriptor)
        .expect_err("overlapping gauges cannot be published as an authoritative sum");
    assert_eq!(error.category(), ErrorCategory::InvalidEvidence);
    assert_eq!(error.code(), "overlapping_memory_total");
}

#[test]
fn only_an_executed_passing_record_can_transition_to_verified() {
    let passed = passed_validation("passed-state-v1");
    let verified = passed.verify().expect("passing evidence can be verified");
    assert_eq!(verified.evidence_status(), EvidenceStatus::Verified);
    assert_eq!(passed.evidence_status(), EvidenceStatus::ExecutedPassed);

    for actual_status in [ActualStatus::Failed, ActualStatus::Blocked] {
        let descriptor = validation_descriptor("nonpassing-state-v1", actual_status);
        let record = ValidationCase::try_new(descriptor)
            .expect("failed and blocked records remain durable evidence");
        let error = record
            .verify()
            .expect_err("nonpassing evidence must not become verified");
        assert_eq!(error.category(), ErrorCategory::InvalidStateTransition);
        assert_eq!(error.code(), "invalid_evidence_transition");
    }
}

#[test]
fn benchmark_requires_each_named_correctness_prerequisite_to_be_verified() {
    let correctness = verified_validation("correctness-passed-v1");
    let descriptor = benchmark_descriptor(vec![correctness.case_id().to_owned()]);
    BenchmarkRecord::try_new(descriptor, &[&correctness])
        .expect("verified passing correctness admits a bounded benchmark");

    let unverified = passed_validation("correctness-unverified-v1");
    let descriptor = benchmark_descriptor(vec![unverified.case_id().to_owned()]);
    let error = BenchmarkRecord::try_new(descriptor, &[&unverified])
        .expect_err("executed-but-unverified correctness is insufficient");
    assert_eq!(error.category(), ErrorCategory::InvalidBenchmark);
    assert_eq!(error.code(), "invalid_benchmark_correctness");

    let descriptor = benchmark_descriptor(Vec::new());
    let error = BenchmarkRecord::try_new(descriptor, &[])
        .expect_err("a benchmark requires a named correctness prerequisite");
    assert_eq!(error.category(), ErrorCategory::InvalidBenchmark);
    assert_eq!(error.code(), "invalid_benchmark_correctness");

    let descriptor = benchmark_descriptor(vec!["correctness-not-supplied-v1".to_owned()]);
    let error = BenchmarkRecord::try_new(descriptor, &[&correctness])
        .expect_err("every referenced correctness record must be supplied");
    assert_eq!(error.category(), ErrorCategory::InvalidBenchmark);
    assert_eq!(error.code(), "invalid_benchmark_correctness");
}

#[test]
fn benchmark_rejects_failed_or_blocked_correctness_records() {
    for actual_status in [ActualStatus::Failed, ActualStatus::Blocked] {
        let record = ValidationCase::try_new(validation_descriptor(
            "nonpassing-correctness-v1",
            actual_status,
        ))
        .expect("failed and blocked correctness outcomes remain durable");
        let descriptor = benchmark_descriptor(vec![record.case_id().to_owned()]);

        let error = BenchmarkRecord::try_new(descriptor, &[&record])
            .expect_err("a benchmark cannot use failed or blocked correctness evidence");
        assert_eq!(error.category(), ErrorCategory::InvalidBenchmark);
        assert_eq!(error.code(), "invalid_benchmark_correctness");
    }
}
