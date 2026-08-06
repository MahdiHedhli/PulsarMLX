use mlx_backend::protocol::{
    parse_response_line, ProtocolLimits, WorkerErrorKind, MAX_RESPONSE_BYTES,
};
use mlx_backend::router::{validate_major_router_timing_series, RouterTimingSeries};
use serde_json::{json, Value};

const SINGLE_BENCHMARK_ID: &str = "f002-major-single-row-minimal-v1";
const TWO_ROW_BENCHMARK_ID: &str = "f002-major-two-row-minimal-v1";
const SINGLE_CASE_ID: &str = "qwen3moe-layer0-router-token0-row0-v1";
const TWO_ROW_CASE_ID: &str = "qwen3moe-layer0-router-token0-token1-batch-v1";
const GENERATED_SINGLE_CASE_ID: &str = "generated-qwen3moe-router-single-row-v1";
const OUTPUT_SHA256: &str = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";

#[allow(clippy::too_many_arguments)]
fn timing_observation(
    kind: &str,
    run_index: usize,
    process_replication_id: &str,
    process_state: &str,
    condition: &str,
    instrumentation_mode: &str,
    external_costly: bool,
    output_sha256: &str,
) -> Value {
    let stages = if instrumentation_mode == "stage_instrumented" {
        json!({
            "setup_admission": {
                "status": "unavailable",
                "reason": "not_separately_observed_in_model_free_fixture"
            },
            "file_io": {
                "status": "unavailable",
                "reason": "not_separately_observed_in_model_free_fixture"
            },
            "storage_validation_f32_decode": {
                "status": "unavailable",
                "reason": "not_separately_observed_in_model_free_fixture"
            },
            "dequantization": {
                "status": "not_applicable",
                "reason": "f32_router_requires_no_dequantization"
            },
            "host_to_device": {
                "status": "unavailable",
                "reason": "not_separately_observed_in_model_free_fixture"
            },
            "graph_construction": {
                "status": "unavailable",
                "reason": "not_separately_observed_in_model_free_fixture"
            },
            "compilation": {
                "status": "unavailable",
                "reason": "not_separately_observed_in_model_free_fixture"
            },
            "router_projection": {
                "status": "observed",
                "duration_ns": 500_u64 + u64::try_from(run_index).unwrap()
            },
            "top_k": {
                "status": "unavailable",
                "reason": "not_separately_observed_in_model_free_fixture"
            },
            "normalization": {
                "status": "unavailable",
                "reason": "not_separately_observed_in_model_free_fixture"
            },
            "total_evaluated_router": {
                "status": "observed",
                "duration_ns": 1_000_u64 + u64::try_from(run_index).unwrap()
            },
            "synchronized_readback": {
                "status": "unavailable",
                "reason": "not_separately_observed_in_model_free_fixture"
            },
            "end_to_end_router_command": {
                "status": "unavailable",
                "reason": "not_separately_observed_in_model_free_fixture"
            }
        })
    } else if external_costly {
        json!({
            "file_io": {
                "status": "observed",
                "duration_ns": 250_u64 + u64::try_from(run_index).unwrap()
            },
            "storage_validation_f32_decode": {
                "status": "observed",
                "duration_ns": 300_u64 + u64::try_from(run_index).unwrap()
            },
            "dequantization": {
                "status": "not_applicable",
                "reason": "f32_router_requires_no_dequantization"
            },
            "host_to_device": {
                "status": "unavailable",
                "reason": "not_separately_observed_in_model_free_fixture"
            },
            "total_evaluated_router": {
                "status": "observed",
                "duration_ns": 1_000_u64 + u64::try_from(run_index).unwrap()
            },
            "end_to_end_router_command": {
                "status": "observed",
                "duration_ns": 1_500_u64 + u64::try_from(run_index).unwrap()
            }
        })
    } else {
        json!({
            "dequantization": {
                "status": "not_applicable",
                "reason": "f32_router_requires_no_dequantization"
            },
            "total_evaluated_router": {
                "status": "observed",
                "duration_ns": 1_000_u64 + u64::try_from(run_index).unwrap()
            }
        })
    };

    json!({
        "observation_id": format!("{process_replication_id}-{kind}-{run_index:02}"),
        "run_index": run_index,
        "observation_kind": kind,
        "process_replication_id": process_replication_id,
        "process_state": process_state,
        "condition": condition,
        "instrumentation_mode": instrumentation_mode,
        "monotonic_clock": "perf_counter_ns",
        "stages": stages,
        "status": "passed",
        "requested_device": "gpu",
        "selected_device": "gpu",
        "fallback_used": false,
        "evaluated": true,
        "synchronized": true,
        "output_sha256": output_sha256,
        "correctness_passed": true
    })
}

#[allow(clippy::too_many_arguments)]
fn timing_series(
    benchmark_id: &str,
    case_id: &str,
    row_count: usize,
    series_kind: &str,
    instrumentation_mode: &str,
    replication_role: &str,
    process_replication_id: &str,
    process_state: &str,
    condition: &str,
    warmup_count: usize,
    measurement_count: usize,
) -> Value {
    let mut observations = Vec::with_capacity(warmup_count + measurement_count);
    let external_costly = matches!(series_kind, "costly_real" | "first_process_costly");
    observations.extend((0..warmup_count).map(|index| {
        timing_observation(
            "warmup",
            index,
            process_replication_id,
            process_state,
            condition,
            instrumentation_mode,
            external_costly,
            OUTPUT_SHA256,
        )
    }));
    observations.extend((0..measurement_count).map(|index| {
        timing_observation(
            "measurement",
            index,
            process_replication_id,
            process_state,
            condition,
            instrumentation_mode,
            external_costly,
            OUTPUT_SHA256,
        )
    }));

    json!({
        "benchmark_id": benchmark_id,
        "case_id": case_id,
        "row_count": row_count,
        "series_kind": series_kind,
        "replication_role": replication_role,
        "process_replication_id": process_replication_id,
        "process_state": process_state,
        "condition": condition,
        "instrumentation_mode": instrumentation_mode,
        "warmup_count": warmup_count,
        "measurement_count": measurement_count,
        "raw_timing_observations": observations
    })
}

fn primary_major(benchmark_id: &str, case_id: &str, row_count: usize) -> Value {
    timing_series(
        benchmark_id,
        case_id,
        row_count,
        "major_minimally_instrumented",
        "minimally_instrumented",
        "primary",
        &format!("primary-{row_count}-row"),
        "reused_process",
        "warm",
        5,
        30,
    )
}

fn clean_replica(benchmark_id: &str, case_id: &str, row_count: usize) -> Value {
    timing_series(
        benchmark_id,
        case_id,
        row_count,
        "major_minimally_instrumented",
        "minimally_instrumented",
        "clean_process_replication",
        &format!("clean-{row_count}-row"),
        "fresh_process",
        "warm",
        5,
        30,
    )
}

fn parse_series(value: Value) -> RouterTimingSeries {
    RouterTimingSeries::try_from_value(value).expect("valid frozen timing series")
}

fn assert_costly_external_stages(series: &Value) {
    for observation in series["raw_timing_observations"]
        .as_array()
        .expect("costly timing observations")
    {
        let stages = observation["stages"]
            .as_object()
            .expect("costly timing stages");
        assert_eq!(stages.len(), 6);
        for stage in [
            "file_io",
            "storage_validation_f32_decode",
            "total_evaluated_router",
            "end_to_end_router_command",
        ] {
            assert_eq!(stages[stage]["status"], "observed");
            assert!(stages[stage]["duration_ns"].as_u64().unwrap_or(0) > 0);
        }
        assert_eq!(stages["dequantization"]["status"], "not_applicable");
        assert_eq!(
            stages["dequantization"]["reason"],
            "f32_router_requires_no_dequantization"
        );
        assert_eq!(stages["host_to_device"]["status"], "unavailable");
        let host_to_device_reason = stages["host_to_device"]["reason"]
            .as_str()
            .expect("bounded host-to-device reason");
        assert!(!host_to_device_reason.is_empty() && host_to_device_reason.len() <= 512);
    }
}

fn complete_major_series() -> Vec<RouterTimingSeries> {
    vec![
        parse_series(primary_major(SINGLE_BENCHMARK_ID, SINGLE_CASE_ID, 1)),
        parse_series(primary_major(TWO_ROW_BENCHMARK_ID, TWO_ROW_CASE_ID, 2)),
        parse_series(clean_replica(SINGLE_BENCHMARK_ID, SINGLE_CASE_ID, 1)),
        parse_series(clean_replica(TWO_ROW_BENCHMARK_ID, TWO_ROW_CASE_ID, 2)),
    ]
}

#[test]
fn fixed_sample_policies_reject_count_overrides() {
    let major = primary_major(SINGLE_BENCHMARK_ID, SINGLE_CASE_ID, 1);
    parse_series(major.clone());

    for (label, field, value) in [
        ("too few major warmups", "warmup_count", 4),
        ("too many major warmups", "warmup_count", 6),
        ("too few major measurements", "measurement_count", 29),
        ("too many major measurements", "measurement_count", 31),
    ] {
        let mut changed = major.clone();
        changed[field] = json!(value);
        assert!(
            RouterTimingSeries::try_from_value(changed).is_err(),
            "{label} must not weaken or override the frozen 5+30 policy"
        );
    }

    let costly = timing_series(
        "f002-costly-read-single-row-v1",
        SINGLE_CASE_ID,
        1,
        "costly_real",
        "minimally_instrumented",
        "primary",
        "costly-process",
        "reused_process",
        "warm",
        5,
        10,
    );
    assert_costly_external_stages(&costly);
    parse_series(costly.clone());
    let mut costly_with_microbenchmark_count = costly;
    costly_with_microbenchmark_count["measurement_count"] = json!(30);
    assert!(RouterTimingSeries::try_from_value(costly_with_microbenchmark_count).is_err());

    let first_process_values = (0..10)
        .map(|replication_index| {
            timing_series(
                "f002-first-read-single-row-v1",
                SINGLE_CASE_ID,
                1,
                "first_process_costly",
                "minimally_instrumented",
                "primary",
                &format!("first-read-process-{replication_index:02}"),
                "fresh_process",
                "first_read_new_process_os_cache_uncontrolled",
                0,
                1,
            )
        })
        .collect::<Vec<_>>();
    for series in &first_process_values {
        assert_costly_external_stages(series);
    }
    let first_process_cohort = first_process_values
        .iter()
        .cloned()
        .map(parse_series)
        .collect::<Vec<_>>();
    assert_eq!(first_process_cohort.len(), 10);
    assert_eq!(
        first_process_cohort
            .iter()
            .map(RouterTimingSeries::process_replication_id)
            .collect::<std::collections::BTreeSet<_>>()
            .len(),
        10,
        "each 0+1 first-process series must identify a distinct fresh process"
    );
    assert_eq!(
        first_process_cohort
            .iter()
            .flat_map(|series| series.raw_timing_observations())
            .map(|observation| observation.observation_id())
            .collect::<std::collections::BTreeSet<_>>()
            .len(),
        10,
        "the truthful ten-process cohort must retain ten distinct measurements"
    );
    assert!(first_process_cohort.iter().all(|series| {
        series.warmup_count() == 0
            && series.measurement_count() == 1
            && series.raw_timing_observations().len() == 1
    }));

    let first_process = first_process_values[0].clone();
    let mut first_process_without_read = first_process.clone();
    for observation in first_process_without_read["raw_timing_observations"]
        .as_array_mut()
        .expect("first-process observations")
    {
        observation["stages"]
            .as_object_mut()
            .expect("timing stages")
            .remove("file_io");
    }
    assert!(RouterTimingSeries::try_from_value(first_process_without_read).is_err());
    let mut invented_warmup = first_process;
    invented_warmup["warmup_count"] = json!(1);
    assert!(RouterTimingSeries::try_from_value(invented_warmup).is_err());

    let mut warm_major_with_first_read = major;
    for observation in warm_major_with_first_read["raw_timing_observations"]
        .as_array_mut()
        .expect("major observations")
    {
        observation["stages"]["file_io"] = json!({
            "status": "observed",
            "duration_ns": 250
        });
    }
    assert!(RouterTimingSeries::try_from_value(warm_major_with_first_read).is_err());

    let generated = timing_series(
        "f002-generated-router-single-row-minimal-v1",
        GENERATED_SINGLE_CASE_ID,
        1,
        "inexpensive_synthetic",
        "minimally_instrumented",
        "primary",
        "generated-process",
        "reused_process",
        "warm",
        5,
        30,
    );
    let generated_series = parse_series(generated.clone());
    assert!(generated_series.has_complete_success_samples());

    let mut generated_with_retained_failure = generated;
    let mut failed_attempt = timing_observation(
        "measurement",
        30,
        "generated-process",
        "reused_process",
        "warm",
        "minimally_instrumented",
        false,
        OUTPUT_SHA256,
    );
    failed_attempt["status"] = json!("aborted");
    failed_attempt["selected_device"] = json!("not_available");
    failed_attempt["evaluated"] = json!(false);
    failed_attempt["synchronized"] = json!(false);
    failed_attempt["output_sha256"] = Value::Null;
    failed_attempt["correctness_passed"] = Value::Null;
    failed_attempt["stages"] = json!({
        "dequantization": {
            "status": "not_applicable",
            "reason": "f32_router_requires_no_dequantization"
        }
    });
    failed_attempt["failure"] = json!({
        "code": "resource_limit",
        "message": "bounded resource admission stopped the attempt",
        "stage": "resource_admission"
    });
    generated_with_retained_failure["raw_timing_observations"]
        .as_array_mut()
        .expect("observation array")
        .push(failed_attempt);
    let retained = parse_series(generated_with_retained_failure);
    assert_eq!(retained.raw_timing_observations().len(), 36);
    assert_eq!(retained.successful_warmup_count(), 5);
    assert_eq!(retained.successful_measurement_count(), 30);
    assert_eq!(
        parse_series(retained.try_to_value().expect("bounded serialization")),
        retained,
        "validated timing evidence must round-trip without a parallel raw JSON tree"
    );
}

#[test]
fn exact_major_benchmarks_require_a_complete_clean_process_replication_each() {
    let complete = complete_major_series();
    validate_major_router_timing_series(&complete)
        .expect("the exact single-row and two-row primary/clean series are complete");

    for missing_index in 0..complete.len() {
        let remaining = complete
            .iter()
            .enumerate()
            .filter(|(index, _)| *index != missing_index)
            .map(|(_, series)| series.clone())
            .collect::<Vec<_>>();
        assert!(
            validate_major_router_timing_series(&remaining).is_err(),
            "neither major nor either clean-process replication may be omitted"
        );
    }

    let diagnostic = timing_series(
        "f002-stage-single-row-v1",
        SINGLE_CASE_ID,
        1,
        "stage_diagnostic",
        "stage_instrumented",
        "primary",
        "diagnostic-process",
        "reused_process",
        "warm",
        5,
        10,
    );
    assert_eq!(
        diagnostic["raw_timing_observations"][0]["stages"]
            .as_object()
            .expect("stage diagnostic boundaries")
            .len(),
        13,
        "stage diagnostics must retain every required observed-or-unavailable boundary"
    );
    parse_series(diagnostic.clone());

    let mut wrong_series_mode = diagnostic.clone();
    wrong_series_mode["instrumentation_mode"] = json!("minimally_instrumented");
    assert!(
        RouterTimingSeries::try_from_value(wrong_series_mode).is_err(),
        "a stage diagnostic cannot claim minimally instrumented series timing"
    );

    let mut wrong_observation_mode = diagnostic.clone();
    wrong_observation_mode["raw_timing_observations"][0]["instrumentation_mode"] =
        json!("minimally_instrumented");
    assert!(
        RouterTimingSeries::try_from_value(wrong_observation_mode).is_err(),
        "a stage diagnostic cannot contain minimally instrumented observations"
    );

    let mut missing_two_row_replica = complete[..3].to_vec();
    missing_two_row_replica.push(parse_series(diagnostic));
    assert!(
        validate_major_router_timing_series(&missing_two_row_replica).is_err(),
        "a stage diagnostic cannot become a third major or replace a clean replica"
    );

    let mut failed_primary = primary_major(SINGLE_BENCHMARK_ID, SINGLE_CASE_ID, 1);
    failed_primary["raw_timing_observations"][6]["status"] = json!("failed");
    failed_primary["raw_timing_observations"][6]["correctness_passed"] = json!(false);
    failed_primary["raw_timing_observations"][6]["failure"] = json!({
        "code": "comparison_failed",
        "message": "bounded correctness failure",
        "stage": "correctness_gate"
    });
    let mut unsuccessful_major = complete_major_series();
    unsuccessful_major[0] = parse_series(failed_primary);
    assert!(
        validate_major_router_timing_series(&unsuccessful_major).is_err(),
        "retained failed attempts must prevent a major timing series from passing"
    );

    let mut shared_single = primary_major(SINGLE_BENCHMARK_ID, SINGLE_CASE_ID, 1);
    let mut shared_two = primary_major(TWO_ROW_BENCHMARK_ID, TWO_ROW_CASE_ID, 2);
    for value in [&mut shared_single, &mut shared_two] {
        value["process_replication_id"] = json!("shared-primary-process");
        for observation in value["raw_timing_observations"]
            .as_array_mut()
            .expect("observation array")
        {
            observation["process_replication_id"] = json!("shared-primary-process");
        }
    }
    let shared_primary_process = vec![
        parse_series(shared_single),
        parse_series(shared_two),
        parse_series(clean_replica(SINGLE_BENCHMARK_ID, SINGLE_CASE_ID, 1)),
        parse_series(clean_replica(TWO_ROW_BENCHMARK_ID, TWO_ROW_CASE_ID, 2)),
    ];
    validate_major_router_timing_series(&shared_primary_process)
        .expect("both primary cases may share one persistent worker");

    let duplicate_observation_id = primary_major(SINGLE_BENCHMARK_ID, SINGLE_CASE_ID, 1)
        ["raw_timing_observations"][0]["observation_id"]
        .clone();
    let mut duplicate_clean = clean_replica(SINGLE_BENCHMARK_ID, SINGLE_CASE_ID, 1);
    duplicate_clean["raw_timing_observations"][0]["observation_id"] = duplicate_observation_id;
    let duplicate_across_series = vec![
        parse_series(primary_major(SINGLE_BENCHMARK_ID, SINGLE_CASE_ID, 1)),
        parse_series(primary_major(TWO_ROW_BENCHMARK_ID, TWO_ROW_CASE_ID, 2)),
        parse_series(duplicate_clean),
        parse_series(clean_replica(TWO_ROW_BENCHMARK_ID, TWO_ROW_CASE_ID, 2)),
    ];
    assert!(
        validate_major_router_timing_series(&duplicate_across_series).is_err(),
        "observation IDs must be unique across the complete experiment"
    );
}

#[test]
fn timing_schema_labels_order_and_failures_are_closed() {
    let valid = primary_major(SINGLE_BENCHMARK_ID, SINGLE_CASE_ID, 1);
    let mut mutations: Vec<(&str, Value)> = Vec::new();

    let mut missing_series_field = valid.clone();
    missing_series_field
        .as_object_mut()
        .expect("series object")
        .remove("condition");
    mutations.push(("missing series field", missing_series_field));

    let mut unknown_series_field = valid.clone();
    unknown_series_field["unreviewed"] = json!(true);
    mutations.push(("unknown series field", unknown_series_field));

    let mut missing_observation_field = valid.clone();
    missing_observation_field["raw_timing_observations"][0]
        .as_object_mut()
        .expect("observation object")
        .remove("output_sha256");
    mutations.push(("missing observation field", missing_observation_field));

    let mut unknown_observation_field = valid.clone();
    unknown_observation_field["raw_timing_observations"][0]["unreviewed"] = json!(true);
    mutations.push(("unknown observation field", unknown_observation_field));

    let mut unknown_stage_field = valid.clone();
    unknown_stage_field["raw_timing_observations"][0]["stages"]["total_evaluated_router"]
        ["unreviewed"] = json!(true);
    mutations.push(("unknown stage field", unknown_stage_field));

    let mut null_required = valid.clone();
    null_required["raw_timing_observations"][0]["process_state"] = Value::Null;
    mutations.push(("null required field", null_required));

    let mut null_optional_union = valid.clone();
    null_optional_union["raw_timing_observations"][0]["failure"] = Value::Null;
    mutations.push(("explicit null failure", null_optional_union));

    let mut mismatched_process = valid.clone();
    mismatched_process["raw_timing_observations"][0]["process_replication_id"] =
        json!("different-process");
    mutations.push(("observation process mismatch", mismatched_process));

    let mut wrong_index = valid.clone();
    wrong_index["raw_timing_observations"][1]["run_index"] = json!(9);
    mutations.push(("noncontiguous index", wrong_index));

    let mut duplicate_id = valid.clone();
    duplicate_id["raw_timing_observations"][1]["observation_id"] =
        duplicate_id["raw_timing_observations"][0]["observation_id"].clone();
    mutations.push(("duplicate observation ID", duplicate_id));

    let mut wrong_order = valid.clone();
    wrong_order["raw_timing_observations"]
        .as_array_mut()
        .expect("observation array")
        .swap(4, 5);
    mutations.push(("warmup after measurement", wrong_order));

    let mut short_series = valid.clone();
    short_series["raw_timing_observations"]
        .as_array_mut()
        .expect("observation array")
        .pop();
    mutations.push(("missing successful measurement", short_series));

    let mut unbarriered_failure = valid.clone();
    unbarriered_failure["raw_timing_observations"][0]["status"] = json!("failed");
    unbarriered_failure["raw_timing_observations"][0]["evaluated"] = json!(false);
    unbarriered_failure["raw_timing_observations"][0]["synchronized"] = json!(false);
    unbarriered_failure["raw_timing_observations"][0]["output_sha256"] = Value::Null;
    unbarriered_failure["raw_timing_observations"][0]["correctness_passed"] = Value::Null;
    unbarriered_failure["raw_timing_observations"][0]["failure"] = json!({
        "code": "evaluation_failed",
        "message": "the evaluated boundary failed",
        "stage": "router_execution"
    });
    mutations.push((
        "observed evaluated stage without barriers",
        unbarriered_failure,
    ));

    let mut unknown_failure_code = valid.clone();
    unknown_failure_code["raw_timing_observations"][0]["status"] = json!("failed");
    unknown_failure_code["raw_timing_observations"][0]["correctness_passed"] = json!(false);
    unknown_failure_code["raw_timing_observations"][0]["failure"] = json!({
        "code": "invented_failure",
        "message": "bounded failure",
        "stage": "correctness_gate"
    });
    mutations.push(("unknown failure code", unknown_failure_code));

    let mut unknown_failure_stage = valid.clone();
    unknown_failure_stage["raw_timing_observations"][0]["status"] = json!("failed");
    unknown_failure_stage["raw_timing_observations"][0]["correctness_passed"] = json!(false);
    unknown_failure_stage["raw_timing_observations"][0]["failure"] = json!({
        "code": "comparison_failed",
        "message": "bounded failure",
        "stage": "invented_stage"
    });
    mutations.push(("unknown failure stage", unknown_failure_stage));

    let mut unsanitized_failure = valid.clone();
    unsanitized_failure["raw_timing_observations"][0]["status"] = json!("failed");
    unsanitized_failure["raw_timing_observations"][0]["correctness_passed"] = json!(false);
    let sensitive_marker = ["HF_", "TOKEN", "=private"].concat();
    unsanitized_failure["raw_timing_observations"][0]["failure"] = json!({
        "code": "comparison_failed",
        "message": format!("bounded failure {sensitive_marker}"),
        "stage": "correctness_gate"
    });
    mutations.push(("unsanitized failure message", unsanitized_failure));

    let mut observed_failed_stage = valid.clone();
    observed_failed_stage["raw_timing_observations"][0]["status"] = json!("failed");
    observed_failed_stage["raw_timing_observations"][0]["correctness_passed"] = json!(false);
    observed_failed_stage["raw_timing_observations"][0]["failure"] = json!({
        "code": "evaluation_failed",
        "message": "bounded failure",
        "stage": "total_evaluated_router"
    });
    mutations.push(("observed failed stage", observed_failed_stage));

    for (label, changed) in mutations {
        assert!(
            RouterTimingSeries::try_from_value(changed).is_err(),
            "{label} must fail closed"
        );
    }
}

#[test]
fn labels_evaluated_envelope_and_output_hashes_fail_closed() {
    let valid = primary_major(SINGLE_BENCHMARK_ID, SINGLE_CASE_ID, 1);
    parse_series(valid.clone());

    type TimingMutation = (&'static str, Box<dyn Fn(&mut Value)>);
    let mutations: [TimingMutation; 11] = [
        (
            "unregistered process state",
            Box::new(|value| {
                value["process_state"] = json!("newish_process");
            }),
        ),
        (
            "invented cold label",
            Box::new(|value| {
                value["condition"] = json!("cold_filesystem");
            }),
        ),
        (
            "wrong instrumentation",
            Box::new(|value| {
                value["instrumentation_mode"] = json!("stage_instrumented");
            }),
        ),
        (
            "missing output hash",
            Box::new(|value| {
                value["raw_timing_observations"][0]["output_sha256"] = Value::Null;
            }),
        ),
        (
            "malformed output hash",
            Box::new(|value| {
                value["raw_timing_observations"][0]["output_sha256"] = json!("abcd");
            }),
        ),
        (
            "changed output hash",
            Box::new(|value| {
                value["raw_timing_observations"][6]["output_sha256"] = json!("c".repeat(64));
            }),
        ),
        (
            "missing correctness result",
            Box::new(|value| {
                value["raw_timing_observations"][0]["correctness_passed"] = Value::Null;
            }),
        ),
        (
            "failed correctness result",
            Box::new(|value| {
                value["raw_timing_observations"][0]["correctness_passed"] = json!(false);
            }),
        ),
        (
            "fallback",
            Box::new(|value| {
                value["raw_timing_observations"][0]["fallback_used"] = json!(true);
            }),
        ),
        (
            "unevaluated",
            Box::new(|value| {
                value["raw_timing_observations"][0]["evaluated"] = json!(false);
            }),
        ),
        (
            "unsynchronized",
            Box::new(|value| {
                value["raw_timing_observations"][0]["synchronized"] = json!(false);
            }),
        ),
    ];

    for (label, mutate) in mutations {
        let mut changed = valid.clone();
        mutate(&mut changed);
        assert!(
            RouterTimingSeries::try_from_value(changed).is_err(),
            "{label} must fail before evidence admission"
        );
    }

    for (label, stage_mutation) in [
        (
            "zero duration",
            json!({"status": "observed", "duration_ns": 0}),
        ),
        (
            "scheduling-only duration",
            json!({"status": "observed", "duration_ns": 1, "synchronized": false}),
        ),
        ("missing total", Value::Null),
    ] {
        let mut changed = valid.clone();
        if stage_mutation.is_null() {
            changed["raw_timing_observations"][0]["stages"]
                .as_object_mut()
                .expect("stages object")
                .remove("total_evaluated_router");
        } else {
            changed["raw_timing_observations"][0]["stages"]["total_evaluated_router"] =
                stage_mutation;
        }
        assert!(
            RouterTimingSeries::try_from_value(changed).is_err(),
            "{label} must not become execution timing"
        );
    }
}

#[test]
fn timing_response_is_bounded_by_the_existing_protocol_cap() {
    let mut oversized_series = timing_series(
        "f002-generated-router-single-row-minimal-v1",
        GENERATED_SINGLE_CASE_ID,
        1,
        "inexpensive_synthetic",
        "minimally_instrumented",
        "primary",
        "oversized-process",
        "reused_process",
        "warm",
        5,
        30,
    );
    let bounded_reason = "x".repeat(512);
    for run_index in 30..1_019 {
        let mut failed = timing_observation(
            "measurement",
            run_index,
            "oversized-process",
            "reused_process",
            "warm",
            "minimally_instrumented",
            false,
            OUTPUT_SHA256,
        );
        failed["status"] = json!("aborted");
        failed["selected_device"] = json!("not_available");
        failed["evaluated"] = json!(false);
        failed["synchronized"] = json!(false);
        failed["output_sha256"] = Value::Null;
        failed["correctness_passed"] = Value::Null;
        failed["stages"] = json!({
            "dequantization": {
                "status": "not_applicable",
                "reason": "f32_router_requires_no_dequantization"
            },
            "setup_admission": {"status": "unavailable", "reason": bounded_reason},
            "file_io": {"status": "unavailable", "reason": bounded_reason},
            "storage_validation_f32_decode": {"status": "unavailable", "reason": bounded_reason},
            "host_to_device": {"status": "unavailable", "reason": bounded_reason},
            "graph_construction": {"status": "unavailable", "reason": bounded_reason},
            "compilation": {"status": "unavailable", "reason": bounded_reason},
            "router_projection": {"status": "unavailable", "reason": bounded_reason},
            "top_k": {"status": "unavailable", "reason": bounded_reason},
            "normalization": {"status": "unavailable", "reason": bounded_reason},
            "total_evaluated_router": {"status": "unavailable", "reason": bounded_reason},
            "synchronized_readback": {"status": "unavailable", "reason": bounded_reason},
            "end_to_end_router_command": {"status": "unavailable", "reason": bounded_reason}
        });
        failed["failure"] = json!({
            "code": "resource_limit",
            "message": bounded_reason,
            "stage": "resource_admission"
        });
        oversized_series["raw_timing_observations"]
            .as_array_mut()
            .expect("observation array")
            .push(failed);
    }
    assert!(
        serde_json::to_vec(&oversized_series)
            .expect("oversized series encodes")
            .len()
            > MAX_RESPONSE_BYTES
    );
    assert!(
        RouterTimingSeries::try_from_value(oversized_series).is_err(),
        "admission and bounded serialization must enforce the same byte ceiling"
    );

    let result = json!({
        "timing_series": [
            primary_major(SINGLE_BENCHMARK_ID, SINGLE_CASE_ID, 1),
            primary_major(TWO_ROW_BENCHMARK_ID, TWO_ROW_CASE_ID, 2),
            clean_replica(SINGLE_BENCHMARK_ID, SINGLE_CASE_ID, 1),
            clean_replica(TWO_ROW_BENCHMARK_ID, TWO_ROW_CASE_ID, 2)
        ]
    });
    let mut bounded = serde_json::to_vec(&json!({
        "protocol": 1,
        "request_id": 7,
        "ok": true,
        "result": result
    }))
    .expect("bounded timing response serializes");
    bounded.push(b'\n');
    assert!(bounded.len() <= MAX_RESPONSE_BYTES);
    let parsed = parse_response_line(&bounded, 7, &ProtocolLimits::default())
        .expect("bounded timing response stays inside protocol v1")
        .into_result()
        .expect("bounded timing response is successful");
    let parsed_series = parsed["timing_series"]
        .as_array()
        .expect("timing series array")
        .iter()
        .cloned()
        .map(parse_series)
        .collect::<Vec<_>>();
    validate_major_router_timing_series(&parsed_series)
        .expect("framed timing response retains the complete major contract");

    let mut oversized = vec![b' '; MAX_RESPONSE_BYTES + 1];
    oversized.push(b'\n');
    assert_eq!(
        parse_response_line(&oversized, 7, &ProtocolLimits::default())
            .expect_err("timing evidence must not bypass the response cap")
            .kind(),
        WorkerErrorKind::MessageTooLarge
    );
}
