use mlx_backend::protocol::{
    parse_response_line, ProtocolLimits, WorkerErrorKind, MAX_RESPONSE_BYTES,
};
use mlx_backend::router::{validate_major_router_timing_series, RouterTimingSeries};
use serde_json::{json, Value};

const SINGLE_BENCHMARK_ID: &str = "f002-major-single-row-minimal-v1";
const TWO_ROW_BENCHMARK_ID: &str = "f002-major-two-row-minimal-v1";
const SINGLE_CASE_ID: &str = "qwen3moe-layer0-router-token0-row0-v1";
const TWO_ROW_CASE_ID: &str = "qwen3moe-layer0-router-token0-token1-batch-v1";
const OUTPUT_SHA256: &str = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";

fn timing_observation(
    kind: &str,
    run_index: usize,
    process_replication_id: &str,
    process_state: &str,
    condition: &str,
    output_sha256: &str,
) -> Value {
    json!({
        "observation_id": format!("{process_replication_id}-{kind}-{run_index:02}"),
        "run_index": run_index,
        "observation_kind": kind,
        "process_replication_id": process_replication_id,
        "process_state": process_state,
        "condition": condition,
        "instrumentation_mode": "minimally_instrumented",
        "monotonic_clock": "perf_counter_ns",
        "stages": {
            "dequantization": {
                "status": "not_applicable",
                "reason": "f32_router_requires_no_dequantization"
            },
            "total_evaluated_router": {
                "status": "observed",
                "duration_ns": 1_000_u64 + u64::try_from(run_index).unwrap()
            }
        },
        "status": "passed",
        "requested_device": "gpu",
        "selected_device": "gpu",
        "fallback_used": false,
        "evaluated": true,
        "synchronized": true,
        "output_sha256": output_sha256
    })
}

#[allow(clippy::too_many_arguments)]
fn timing_series(
    benchmark_id: &str,
    case_id: &str,
    row_count: usize,
    series_kind: &str,
    replication_role: &str,
    process_replication_id: &str,
    process_state: &str,
    condition: &str,
    warmup_count: usize,
    measurement_count: usize,
) -> Value {
    let mut observations = Vec::with_capacity(warmup_count + measurement_count);
    observations.extend((0..warmup_count).map(|index| {
        timing_observation(
            "warmup",
            index,
            process_replication_id,
            process_state,
            condition,
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
        "instrumentation_mode": "minimally_instrumented",
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
        "primary",
        "costly-process",
        "reused_process",
        "warm",
        5,
        10,
    );
    parse_series(costly.clone());
    let mut costly_with_microbenchmark_count = costly;
    costly_with_microbenchmark_count["measurement_count"] = json!(30);
    assert!(RouterTimingSeries::try_from_value(costly_with_microbenchmark_count).is_err());

    let first_process = timing_series(
        "f002-first-read-single-row-v1",
        SINGLE_CASE_ID,
        1,
        "first_process_costly",
        "primary",
        "first-read-process",
        "fresh_process",
        "first_read_new_process_os_cache_uncontrolled",
        0,
        10,
    );
    parse_series(first_process.clone());
    let mut invented_warmup = first_process;
    invented_warmup["warmup_count"] = json!(1);
    assert!(RouterTimingSeries::try_from_value(invented_warmup).is_err());
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
        "primary",
        "diagnostic-process",
        "reused_process",
        "warm",
        5,
        10,
    );
    let mut missing_two_row_replica = complete[..3].to_vec();
    missing_two_row_replica.push(parse_series(diagnostic));
    assert!(
        validate_major_router_timing_series(&missing_two_row_replica).is_err(),
        "a stage diagnostic cannot become a third major or replace a clean replica"
    );
}

#[test]
fn labels_evaluated_envelope_and_output_hashes_fail_closed() {
    let valid = primary_major(SINGLE_BENCHMARK_ID, SINGLE_CASE_ID, 1);
    parse_series(valid.clone());

    let mutations: [(&str, Box<dyn Fn(&mut Value)>); 9] = [
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
    parse_response_line(&bounded, 7, &ProtocolLimits::default())
        .expect("bounded timing response stays inside protocol v1");

    let mut oversized = vec![b' '; MAX_RESPONSE_BYTES + 1];
    oversized.push(b'\n');
    assert_eq!(
        parse_response_line(&oversized, 7, &ProtocolLimits::default())
            .expect_err("timing evidence must not bypass the response cap")
            .kind(),
        WorkerErrorKind::MessageTooLarge
    );
}
