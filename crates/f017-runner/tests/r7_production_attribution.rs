#![cfg(all(target_os = "macos", pulsar_native_mlx))]

use f017_runner::json::{parse_json_no_duplicates, sha256_bytes};
use f017_runner::qualification::{
    exact_matvec_f32, exact_swiglu_f32, measure_f32, NumericalMetrics, EXACT_SCAFFOLD_VERSION,
};
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::Path;
use std::time::Instant;
use stream::{MlxContext, MlxDevice, MlxStreamMode};

const REPEATS: usize = 10;

#[derive(Deserialize)]
struct Oracle {
    schema: String,
    boundaries: Boundaries,
}

#[derive(Deserialize)]
struct Boundaries {
    complete_expert: CompleteExpert,
}

#[derive(Deserialize)]
struct CompleteExpert {
    classification: String,
    fixture_version: String,
    dimensions: [usize; 2],
    dtype: String,
    quantization: String,
    inputs: ExpertInputs,
    expected: ExpertExpected,
    numerical_contract: NumericalContract,
}

#[derive(Deserialize)]
struct ExpertInputs {
    activation: Vec<f32>,
    activation_sha256: String,
    gate_packed_hex: String,
    gate_packed_sha256: String,
    up_packed_hex: String,
    up_packed_sha256: String,
    down_packed_hex: String,
    down_packed_sha256: String,
}

#[derive(Deserialize)]
struct ExpertExpected {
    gate_output_sha256: String,
    up_output_sha256: String,
    hidden_sha256: String,
    output: Vec<f32>,
    output_sha256: String,
}

#[derive(Deserialize)]
struct NumericalContract {
    kind: String,
    atol: f64,
    rtol: f64,
}

#[derive(Serialize)]
struct Attribution {
    schema: &'static str,
    schema_version: &'static str,
    fixture_version: String,
    fixture_sha256: String,
    scaffold_version: &'static str,
    production_backend: &'static str,
    deterministic_repeat_count: usize,
    deterministic: bool,
    gate: NumericalMetrics,
    up: NumericalMetrics,
    activated_hidden: NumericalMetrics,
    down_and_final_output: NumericalMetrics,
    production_hashes: ProductionHashes,
    reduction_models: Vec<ReductionModelResult>,
    timings: Timings,
    lifecycle: Lifecycle,
    checkpoint_accessed: bool,
}

#[derive(Serialize)]
struct ProductionHashes {
    gate_sha256: String,
    up_sha256: String,
    activated_hidden_sha256: String,
    output_sha256: String,
}

#[derive(Serialize)]
struct ReductionModelResult {
    name: &'static str,
    output_sha256: String,
    bit_mismatch_count_vs_production: usize,
    exact_production_match: bool,
}

#[derive(Default, Serialize)]
struct Timings {
    import_seconds: f64,
    compute_sync_seconds: f64,
    activation_seconds: f64,
    total_seconds: f64,
}

#[derive(Serialize)]
struct Lifecycle {
    managed_created: u64,
    managed_destroyed: u64,
    derived_created: u64,
    derived_destroyed: u64,
    derived_live: u64,
    callback_count: u64,
    owned_stream_created_delta: u64,
    owned_stream_freed_delta: u64,
    context_active_after: bool,
    reconciled: bool,
}

#[test]
fn original_r7_mismatch_is_attributed_without_a_tolerance() {
    let total_started = Instant::now();
    let fixture_path = Path::new(env!("CARGO_MANIFEST_DIR")).join(
        "../../specs/017-rust-native-inference-runtime/fixtures/f017-independent-oracle-v1.json",
    );
    let fixture_bytes = fs::read(&fixture_path).unwrap();
    let fixture_sha256 = sha256_bytes(&fixture_bytes);
    let oracle: Oracle = parse_json_no_duplicates(&fixture_bytes).unwrap();
    let expert = oracle.boundaries.complete_expert;
    validate_fixture(&oracle.schema, &expert);

    let matrices = [
        decode_matrix(
            &expert.inputs.gate_packed_hex,
            &expert.inputs.gate_packed_sha256,
        ),
        decode_matrix(
            &expert.inputs.up_packed_hex,
            &expert.inputs.up_packed_sha256,
        ),
        decode_matrix(
            &expert.inputs.down_packed_hex,
            &expert.inputs.down_packed_sha256,
        ),
    ];
    let (expected_gate, expected_up, expected_hidden, expected_output) =
        exact_expected(&matrices, &expert.inputs.activation);
    require_hash(
        &f32_bytes(&expected_gate),
        &expert.expected.gate_output_sha256,
    );
    require_hash(&f32_bytes(&expected_up), &expert.expected.up_output_sha256);
    require_hash(&f32_bytes(&expected_hidden), &expert.expected.hidden_sha256);
    require_hash(&f32_bytes(&expected_output), &expert.expected.output_sha256);
    assert_bits_equal(&expected_output, &expert.expected.output);

    let streams_before = MlxContext::debug_stream_counters().unwrap();
    assert!(!MlxContext::debug_context_active());
    let context = MlxContext::new(MlxDevice::Gpu, MlxStreamMode::Owned).unwrap();
    let mut timings = Timings::default();
    let mut first_outputs = None;
    for _ in 0..REPEATS {
        let gate = production_matvec(
            &context,
            matrices[0].clone(),
            expert.inputs.activation.clone(),
            &mut timings,
        );
        let up = production_matvec(
            &context,
            matrices[1].clone(),
            expert.inputs.activation.clone(),
            &mut timings,
        );
        let activation_started = Instant::now();
        let mut hidden = vec![0.0_f32; 32];
        exact_swiglu_f32(&gate, &up, &mut hidden).unwrap();
        timings.activation_seconds += activation_started.elapsed().as_secs_f64();
        let output = production_matvec(&context, matrices[2].clone(), hidden.clone(), &mut timings);
        let current = (gate, up, hidden, output);
        if let Some(first) = &first_outputs {
            assert_tuple_bits_equal(first, &current);
        } else {
            first_outputs = Some(current);
        }
    }
    let (gate, up, hidden, output) = first_outputs.unwrap();
    assert_eq!(output[0].to_bits(), 427_909.0_f32.to_bits());

    context.synchronize().unwrap();
    let ownership = context.ownership_snapshot().unwrap();
    drop(context);
    let streams_after = MlxContext::debug_stream_counters().unwrap();
    let context_active_after = MlxContext::debug_context_active();
    let lifecycle_reconciled = ownership.managed_created == ownership.managed_destroyed
        && ownership.derived_created == ownership.derived_destroyed
        && ownership.derived_live == 0
        && ownership.callback_count == ownership.managed_created
        && streams_after.owned_created - streams_before.owned_created
            == streams_after.owned_freed - streams_before.owned_freed
        && !context_active_after;
    assert!(lifecycle_reconciled);

    timings.total_seconds = total_started.elapsed().as_secs_f64();
    let attribution = Attribution {
        schema: "pulsarmlx.f017.r7-production-attribution",
        schema_version: "1.0.0",
        fixture_version: expert.fixture_version,
        fixture_sha256,
        scaffold_version: EXACT_SCAFFOLD_VERSION,
        production_backend: "mlx-c-matmul",
        deterministic_repeat_count: REPEATS,
        deterministic: true,
        gate: measure_f32(&expected_gate, &gate).unwrap(),
        up: measure_f32(&expected_up, &up).unwrap(),
        activated_hidden: measure_f32(&expected_hidden, &hidden).unwrap(),
        down_and_final_output: measure_f32(&expected_output, &output).unwrap(),
        production_hashes: ProductionHashes {
            gate_sha256: sha256_bytes(&f32_bytes(&gate)),
            up_sha256: sha256_bytes(&f32_bytes(&up)),
            activated_hidden_sha256: sha256_bytes(&f32_bytes(&hidden)),
            output_sha256: sha256_bytes(&f32_bytes(&output)),
        },
        reduction_models: reduction_models(&matrices[2], &expected_hidden, &output),
        timings,
        lifecycle: Lifecycle {
            managed_created: ownership.managed_created,
            managed_destroyed: ownership.managed_destroyed,
            derived_created: ownership.derived_created,
            derived_destroyed: ownership.derived_destroyed,
            derived_live: ownership.derived_live,
            callback_count: ownership.callback_count,
            owned_stream_created_delta: streams_after.owned_created - streams_before.owned_created,
            owned_stream_freed_delta: streams_after.owned_freed - streams_before.owned_freed,
            context_active_after,
            reconciled: lifecycle_reconciled,
        },
        checkpoint_accessed: false,
    };
    let json = serde_json::to_string(&attribution).unwrap();
    println!("F017_R7_ATTRIBUTION_JSON={json}");
}

fn reduction_models(
    matrix: &[f32],
    vector: &[f32],
    production: &[f32],
) -> Vec<ReductionModelResult> {
    [
        ("sequential_fma", matvec_sequential_fma(matrix, vector)),
        (
            "adjacent_pairwise_tree",
            matvec_adjacent_tree(matrix, vector),
        ),
        ("halving_pairwise_tree", matvec_halving_tree(matrix, vector)),
        ("four_sequential_chunks", matvec_chunked(matrix, vector, 4)),
        ("eight_sequential_chunks", matvec_chunked(matrix, vector, 8)),
    ]
    .into_iter()
    .map(|(name, candidate)| {
        let metrics = measure_f32(production, &candidate).unwrap();
        ReductionModelResult {
            name,
            output_sha256: sha256_bytes(&f32_bytes(&candidate)),
            bit_mismatch_count_vs_production: metrics.bit_mismatch_count,
            exact_production_match: metrics.bit_mismatch_count == 0,
        }
    })
    .collect()
}

fn matvec_sequential_fma(matrix: &[f32], vector: &[f32]) -> Vec<f32> {
    (0..32)
        .map(|row| {
            let mut total = 0.0_f32;
            for column in 0..32 {
                total = matrix[row * 32 + column].mul_add(vector[column], total);
            }
            total
        })
        .collect()
}

fn matvec_adjacent_tree(matrix: &[f32], vector: &[f32]) -> Vec<f32> {
    (0..32)
        .map(|row| {
            let mut values = (0..32)
                .map(|column| matrix[row * 32 + column] * vector[column])
                .collect::<Vec<_>>();
            while values.len() > 1 {
                values = values
                    .chunks_exact(2)
                    .map(|pair| pair[0] + pair[1])
                    .collect();
            }
            values[0]
        })
        .collect()
}

fn matvec_halving_tree(matrix: &[f32], vector: &[f32]) -> Vec<f32> {
    (0..32)
        .map(|row| {
            let mut values = (0..32)
                .map(|column| matrix[row * 32 + column] * vector[column])
                .collect::<Vec<_>>();
            let mut width = 32;
            while width > 1 {
                let half = width / 2;
                for index in 0..half {
                    values[index] += values[index + half];
                }
                width = half;
            }
            values[0]
        })
        .collect()
}

fn matvec_chunked(matrix: &[f32], vector: &[f32], chunks: usize) -> Vec<f32> {
    (0..32)
        .map(|row| {
            let width = 32 / chunks;
            let mut partials = vec![0.0_f32; chunks];
            for (chunk, partial) in partials.iter_mut().enumerate() {
                for column in chunk * width..(chunk + 1) * width {
                    *partial += matrix[row * 32 + column] * vector[column];
                }
            }
            partials.into_iter().fold(0.0_f32, |sum, value| sum + value)
        })
        .collect()
}

fn production_matvec(
    context: &MlxContext,
    mut matrix_owner: Vec<f32>,
    mut vector_owner: Vec<f32>,
    timings: &mut Timings,
) -> Vec<f32> {
    let import_started = Instant::now();
    let matrix = context
        .import_f32_shaped(&mut matrix_owner, &[32, 32])
        .unwrap();
    let vector = context.import_f32_shaped(&mut vector_owner, &[32]).unwrap();
    timings.import_seconds += import_started.elapsed().as_secs_f64();

    let compute_started = Instant::now();
    let result = matrix.matvec(&vector).unwrap();
    result.evaluate_sync().unwrap();
    let mut output = vec![0.0_f32; 32];
    result.copy_f32(&mut output).unwrap();
    timings.compute_sync_seconds += compute_started.elapsed().as_secs_f64();
    result.destroy().unwrap();
    vector.destroy().unwrap();
    matrix.destroy().unwrap();
    output
}

fn exact_expected(
    matrices: &[Vec<f32>; 3],
    activation: &[f32],
) -> (Vec<f32>, Vec<f32>, Vec<f32>, Vec<f32>) {
    let mut gate = vec![0.0_f32; 32];
    let mut up = vec![0.0_f32; 32];
    let mut hidden = vec![0.0_f32; 32];
    let mut output = vec![0.0_f32; 32];
    exact_matvec_f32(&matrices[0], 32, 32, activation, &mut gate).unwrap();
    exact_matvec_f32(&matrices[1], 32, 32, activation, &mut up).unwrap();
    exact_swiglu_f32(&gate, &up, &mut hidden).unwrap();
    exact_matvec_f32(&matrices[2], 32, 32, &hidden, &mut output).unwrap();
    (gate, up, hidden, output)
}

fn validate_fixture(schema: &str, expert: &CompleteExpert) {
    assert_eq!(schema, "glm52-f017-independent-oracle-v1");
    assert_eq!(expert.classification, "INDEPENDENT");
    assert_eq!(expert.fixture_version, "glm52-runtime-expert-q8-0-v2");
    assert_eq!(expert.dimensions, [32, 32]);
    assert_eq!(expert.dtype, "f32");
    assert_eq!(expert.quantization, "Q8_0");
    assert_eq!(expert.numerical_contract.kind, "exact_f32_bits");
    assert_eq!(expert.numerical_contract.atol, 0.0);
    assert_eq!(expert.numerical_contract.rtol, 0.0);
    require_hash(
        &f32_bytes(&expert.inputs.activation),
        &expert.inputs.activation_sha256,
    );
}

fn decode_matrix(encoded_hex: &str, expected_packed_hash: &str) -> Vec<f32> {
    let packed = decode_hex(encoded_hex);
    require_hash(&packed, expected_packed_hash);
    let mut decoded = vec![0.0_f32; 32 * 32];
    quant::decode_q8_0_matrix(&packed, 32, 32, &mut decoded).unwrap();
    decoded
}

fn decode_hex(encoded: &str) -> Vec<u8> {
    encoded
        .as_bytes()
        .chunks_exact(2)
        .map(|pair| u8::from_str_radix(std::str::from_utf8(pair).unwrap(), 16).unwrap())
        .collect()
}

fn f32_bytes(values: &[f32]) -> Vec<u8> {
    values
        .iter()
        .flat_map(|value| value.to_le_bytes())
        .collect()
}

fn require_hash(bytes: &[u8], expected: &str) {
    assert_eq!(sha256_bytes(bytes), expected);
}

fn assert_bits_equal(actual: &[f32], expected: &[f32]) {
    assert_eq!(
        actual
            .iter()
            .map(|value| value.to_bits())
            .collect::<Vec<_>>(),
        expected
            .iter()
            .map(|value| value.to_bits())
            .collect::<Vec<_>>()
    );
}

fn assert_tuple_bits_equal(
    left: &(Vec<f32>, Vec<f32>, Vec<f32>, Vec<f32>),
    right: &(Vec<f32>, Vec<f32>, Vec<f32>, Vec<f32>),
) {
    assert_bits_equal(&left.0, &right.0);
    assert_bits_equal(&left.1, &right.1);
    assert_bits_equal(&left.2, &right.2);
    assert_bits_equal(&left.3, &right.3);
}
