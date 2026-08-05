use backend::ContractError;
use mlx_backend::router::{
    admit_router_tensor, canonical_f32le_sha256, compare_router_outputs, positional_read_exact,
    validate_repeat_identities, RouterCaseScope, RouterOutput, RouterTensorDescriptor,
    RouterTolerancePolicy,
};
#[cfg(unix)]
use mlx_backend::router::{with_admitted_router_tensor_f32, RouterResourceAdmission};
use serde::Deserialize;
#[cfg(unix)]
use sha2::{Digest, Sha256};
use std::cell::Cell;
#[cfg(unix)]
use std::fs::{self, File, OpenOptions};
#[cfg(unix)]
use std::io::Write;
#[cfg(unix)]
use std::path::{Path, PathBuf};
#[cfg(unix)]
use std::sync::atomic::{AtomicU64, Ordering};
#[cfg(unix)]
use std::time::{SystemTime, UNIX_EPOCH};

const MODEL_FILE_BYTES: u64 = 32_483_931_648;
const ROUTER_TENSOR_BYTES: u64 = 1_048_576;
const ROUTER_OFFSET_FIXTURE: u64 = 8_388_608;
const SYNTHETIC_TIE_FIXTURE: &str =
    include_str!("../../../fixtures/research/router-v1/synthetic-tie.json");

#[derive(Debug, Deserialize)]
struct SyntheticTieDocument {
    schema: String,
    provenance: SyntheticTieProvenance,
    cases: Vec<SyntheticTieCase>,
}

#[derive(Debug, Deserialize)]
struct SyntheticTieProvenance {
    evidence_level: String,
    model_free: bool,
    proves_real_checkpoint_routing: bool,
}

#[derive(Debug, Deserialize)]
struct SyntheticTieCase {
    case_id: String,
    kind: String,
    provenance: String,
    logits: Vec<Vec<f32>>,
    full_softmax_probabilities: Vec<Vec<f32>>,
    selected_expert_ids: Vec<Vec<u64>>,
    selected_probabilities: Vec<Vec<f32>>,
    normalized_weights: Vec<Vec<f32>>,
}

fn synthetic_tie_case(kind: &str) -> SyntheticTieCase {
    let document: SyntheticTieDocument =
        serde_json::from_str(SYNTHETIC_TIE_FIXTURE).expect("parse synthetic tie fixture");
    assert_eq!(document.schema, "pulsarmlx.fixture.router-synthetic-tie");
    assert_eq!(
        document.provenance.evidence_level,
        "synthetic_tie_fixture_only"
    );
    assert!(document.provenance.model_free);
    assert!(!document.provenance.proves_real_checkpoint_routing);
    document
        .cases
        .into_iter()
        .find(|case| case.kind == kind)
        .unwrap_or_else(|| panic!("synthetic tie fixture must contain {kind}"))
}

fn output_from_synthetic_tie_case(
    case: SyntheticTieCase,
    case_scope: RouterCaseScope,
) -> Result<RouterOutput, ContractError> {
    assert_eq!(case.provenance, "synthetic_generated_model_free");
    let row_count = case.logits.len();
    RouterOutput::try_new(
        case.case_id,
        case_scope,
        row_count,
        case.logits.into_iter().flatten().collect(),
        case.full_softmax_probabilities
            .into_iter()
            .flatten()
            .collect(),
        case.selected_expert_ids,
        case.selected_probabilities,
        case.normalized_weights,
    )
}

fn fixture_tensor_descriptor() -> RouterTensorDescriptor {
    RouterTensorDescriptor {
        name: "blk.0.ffn_gate_inp.weight".to_owned(),
        semantic_role: "layer_0_router_projection".to_owned(),
        occurrence_count: 1,
        gguf_dimensions_fastest_axis_first: vec![2_048, 128],
        reader_shape: vec![128, 2_048],
        execution_shape: vec![128, 2_048],
        gguf_type: "F32".to_owned(),
        quantization: "none_f32".to_owned(),
        logical_elements: 262_144,
        absolute_data_offset: ROUTER_OFFSET_FIXTURE,
        encoded_length: ROUTER_TENSOR_BYTES,
        encoded_sha256: "a".repeat(64),
        byte_order: "little".to_owned(),
        orientation: "expert_major_rows_input_columns".to_owned(),
        expert_count: 128,
        top_k: 8,
        weight_scale: 1.0,
        bias_present: false,
        correction_bias_present: false,
    }
}

fn bounded_error_code(error: ContractError) -> String {
    assert!(
        error.message().chars().count() <= 512,
        "router failures must remain bounded"
    );
    error.code().to_owned()
}

#[cfg(unix)]
fn encoded_sha256(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

#[cfg(unix)]
fn execution_descriptor_for_bytes(bytes: &[u8]) -> RouterTensorDescriptor {
    assert_eq!(bytes.len(), ROUTER_TENSOR_BYTES as usize);
    let mut descriptor = fixture_tensor_descriptor();
    descriptor.absolute_data_offset = 0;
    descriptor.encoded_sha256 = encoded_sha256(bytes);
    descriptor
}

#[cfg(unix)]
fn admitted_resources() -> RouterResourceAdmission {
    RouterResourceAdmission {
        disk_headroom_satisfied: true,
        unified_memory_headroom_satisfied: true,
        memory_pressure_normal: true,
    }
}

#[cfg(unix)]
fn production_preflight_with_bytes(
    label: &str,
    bytes: &[u8],
    descriptor: &RouterTensorDescriptor,
    resources: &RouterResourceAdmission,
    runner: impl FnOnce(&[f32]),
) -> Result<(), ContractError> {
    let directory = IsolatedDirectory::new(label);
    let path = directory.path().join("synthetic-router.bin");
    fs::write(&path, bytes).expect("write bounded synthetic router fixture");
    let file = File::open(&path).expect("open synthetic router fixture read-only");
    with_admitted_router_tensor_f32(
        &file,
        descriptor,
        bytes.len() as u64,
        resources,
        |_admitted, values| {
            runner(values);
            Ok(())
        },
    )
}

#[cfg(unix)]
struct IsolatedDirectory(PathBuf);

#[cfg(unix)]
impl IsolatedDirectory {
    fn new(label: &str) -> Self {
        static NEXT_ID: AtomicU64 = AtomicU64::new(0);

        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("test clock is after the Unix epoch")
            .as_nanos();
        let sequence = NEXT_ID.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "pulsarmlx-router-contract-{label}-{}-{nonce}-{sequence}",
            std::process::id()
        ));
        fs::create_dir(&path).expect("create isolated router-contract directory");
        Self(path)
    }

    fn path(&self) -> &Path {
        &self.0
    }
}

#[cfg(unix)]
impl Drop for IsolatedDirectory {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

fn full_softmax(logits: &[f32]) -> Vec<f32> {
    let maximum = logits
        .iter()
        .copied()
        .reduce(f32::max)
        .expect("fixture row is nonempty");
    let exponentials: Vec<f32> = logits
        .iter()
        .map(|value| (*value - maximum).exp())
        .collect();
    let denominator: f32 = exponentials.iter().copied().sum();
    exponentials
        .into_iter()
        .map(|value| value / denominator)
        .collect()
}

fn selected_row(probabilities: &[f32]) -> (Vec<u64>, Vec<f32>, Vec<f32>) {
    let mut ids: Vec<usize> = (0..probabilities.len()).collect();
    ids.sort_by(|left, right| {
        probabilities[*right]
            .partial_cmp(&probabilities[*left])
            .expect("fixture probabilities are finite")
            .then_with(|| left.cmp(right))
    });
    ids.truncate(8);

    let selected_probabilities: Vec<f32> = ids
        .iter()
        .map(|expert_id| probabilities[*expert_id])
        .collect();
    let selected_sum: f32 = selected_probabilities.iter().copied().sum();
    let normalized_weights = selected_probabilities
        .iter()
        .map(|probability| *probability / selected_sum)
        .collect();

    (
        ids.into_iter()
            .map(|expert_id| u64::try_from(expert_id).expect("fixture expert ID fits u64"))
            .collect(),
        selected_probabilities,
        normalized_weights,
    )
}

fn fixture_output_with_last_logit_delta(delta: f32) -> RouterOutput {
    let mut rows = vec![
        (0..128)
            .map(|expert_id| expert_id as f32 * 0.01)
            .collect::<Vec<_>>(),
        (0..128)
            .map(|expert_id| -(expert_id as f32) * 0.01)
            .collect::<Vec<_>>(),
    ];
    rows[1][127] += delta;

    let mut logits = Vec::with_capacity(256);
    let mut full_probabilities = Vec::with_capacity(256);
    let mut selected_expert_ids = Vec::with_capacity(2);
    let mut selected_probabilities = Vec::with_capacity(2);
    let mut normalized_weights = Vec::with_capacity(2);

    for row in rows {
        let probabilities = full_softmax(&row);
        let (ids, selected, normalized) = selected_row(&probabilities);
        logits.extend(row);
        full_probabilities.extend(probabilities);
        selected_expert_ids.push(ids);
        selected_probabilities.push(selected);
        normalized_weights.push(normalized);
    }

    RouterOutput::try_new(
        "synthetic-two-row-router-v1",
        RouterCaseScope::SyntheticFixture,
        2,
        logits,
        full_probabilities,
        selected_expert_ids,
        selected_probabilities,
        normalized_weights,
    )
    .expect("the complete synthetic router output is contract-valid")
}

fn fixture_output() -> RouterOutput {
    fixture_output_with_last_logit_delta(0.0)
}

#[test]
fn complete_output_rejects_probabilities_unrelated_to_logits() {
    let logits = (0..128)
        .map(|expert_id| expert_id as f32 * 0.01)
        .collect::<Vec<_>>();
    let probabilities = vec![1.0_f32 / 128.0; 128];
    let selected_ids = vec![(0..8).collect::<Vec<_>>()];
    let selected = vec![vec![1.0_f32 / 128.0; 8]];
    let normalized = vec![vec![1.0_f32 / 8.0; 8]];

    let error = RouterOutput::try_new(
        "synthetic-invalid-softmax-v1",
        RouterCaseScope::SyntheticFixture,
        1,
        logits,
        probabilities,
        selected_ids,
        selected,
        normalized,
    )
    .expect_err("self-consistent probabilities unrelated to logits must fail");
    assert_eq!(error.code(), "comparison_failed");
}

#[test]
fn exact_f32_router_tensor_contract_is_admitted_without_checkpoint_access() {
    // This is a structural fixture offset, not an observed checkpoint offset.
    // Real offsets and hashes remain prohibited until the notified model gate.
    let admitted = admit_router_tensor(&fixture_tensor_descriptor(), MODEL_FILE_BYTES)
        .expect("the exact complete F32 router descriptor is admitted");

    assert_eq!(admitted.name(), "blk.0.ffn_gate_inp.weight");
    assert_eq!(admitted.semantic_role(), "layer_0_router_projection");
    assert_eq!(admitted.gguf_dimensions(), &[2_048, 128]);
    assert_eq!(admitted.reader_shape(), &[128, 2_048]);
    assert_eq!(admitted.execution_shape(), &[128, 2_048]);
    assert_eq!(admitted.gguf_type(), "F32");
    assert_eq!(admitted.quantization(), "none_f32");
    assert_eq!(admitted.logical_elements(), 262_144);
    assert_eq!(admitted.encoded_length(), ROUTER_TENSOR_BYTES);
    assert_eq!(admitted.absolute_data_offset(), ROUTER_OFFSET_FIXTURE);
    assert_eq!(
        admitted.exclusive_end_offset(),
        ROUTER_OFFSET_FIXTURE + ROUTER_TENSOR_BYTES
    );
    assert_eq!(admitted.expert_count(), 128);
    assert_eq!(admitted.top_k(), 8);
    assert_eq!(admitted.weight_scale(), 1.0);
    assert!(!admitted.bias_present());
    assert!(!admitted.correction_bias_present());
}

#[test]
#[cfg(unix)]
fn missing_and_duplicate_router_occurrences_have_distinct_stable_codes_before_runner() {
    let bytes = vec![0_u8; ROUTER_TENSOR_BYTES as usize];
    let cases = [(0, "missing_tensor_role"), (2, "duplicate_tensor_role")];
    let mut observed = Vec::new();

    for (occurrence_count, expected_code) in cases {
        let mut descriptor = execution_descriptor_for_bytes(&bytes);
        descriptor.occurrence_count = occurrence_count;
        let runner_calls = Cell::new(0_u32);
        let error = production_preflight_with_bytes(
            "occurrence",
            &bytes,
            &descriptor,
            &admitted_resources(),
            |_| runner_calls.set(runner_calls.get() + 1),
        )
        .expect_err("a missing or duplicate router role must fail before execution");

        assert_eq!(
            runner_calls.get(),
            0,
            "occurrence count {occurrence_count} reached the router runner"
        );
        observed.push((expected_code, bounded_error_code(error)));
    }

    assert_eq!(
        observed,
        [
            ("missing_tensor_role", "missing_tensor_role".to_owned()),
            ("duplicate_tensor_role", "duplicate_tensor_role".to_owned()),
        ],
        "missing and duplicate tensor roles must remain distinguishable"
    );
}

#[test]
#[cfg(unix)]
fn tensor_name_and_semantic_role_aliases_are_missing_not_generic_mismatches() {
    let bytes = vec![0_u8; ROUTER_TENSOR_BYTES as usize];
    let mut name_alias = execution_descriptor_for_bytes(&bytes);
    name_alias.name = "blk.0.ffn_gate_exps.weight".to_owned();
    let mut role_alias = execution_descriptor_for_bytes(&bytes);
    role_alias.semantic_role = "layer_0_routed_expert_gate_projection".to_owned();

    let mut observed = Vec::new();
    for (label, descriptor) in [("tensor-name", name_alias), ("semantic-role", role_alias)] {
        let runner_calls = Cell::new(0_u32);
        let error = production_preflight_with_bytes(
            label,
            &bytes,
            &descriptor,
            &admitted_resources(),
            |_| runner_calls.set(runner_calls.get() + 1),
        )
        .expect_err("an aliased tensor identity must not be admitted");
        assert_eq!(runner_calls.get(), 0, "{label} alias reached the runner");
        observed.push((label, bounded_error_code(error)));
    }

    assert_eq!(
        observed,
        [
            ("tensor-name", "missing_tensor_role".to_owned()),
            ("semantic-role", "missing_tensor_role".to_owned()),
        ],
        "a different tensor or semantic role is not the required router role"
    );
}

#[test]
#[cfg(unix)]
fn truncated_overlong_and_out_of_file_ranges_fail_before_runner() {
    let bytes = vec![0_u8; ROUTER_TENSOR_BYTES as usize];
    let mut truncated = execution_descriptor_for_bytes(&bytes);
    truncated.encoded_length = ROUTER_TENSOR_BYTES - 4;
    let mut overlong = execution_descriptor_for_bytes(&bytes);
    overlong.encoded_length = ROUTER_TENSOR_BYTES + 4;
    let mut out_of_file = execution_descriptor_for_bytes(&bytes);
    out_of_file.absolute_data_offset = 1;
    let mut overflowing = execution_descriptor_for_bytes(&bytes);
    overflowing.absolute_data_offset = u64::MAX - ROUTER_TENSOR_BYTES + 1;

    let cases = [
        ("truncated", truncated, "model_tensor_mismatch"),
        ("overlong", overlong, "model_tensor_mismatch"),
        ("out-of-file", out_of_file, "invalid_tensor_range"),
        ("overflowing", overflowing, "invalid_tensor_range"),
    ];
    for (label, descriptor, expected_code) in cases {
        let runner_calls = Cell::new(0_u32);
        let error = production_preflight_with_bytes(
            label,
            &bytes,
            &descriptor,
            &admitted_resources(),
            |_| runner_calls.set(runner_calls.get() + 1),
        )
        .expect_err("a malformed range must fail before execution");
        assert_eq!(runner_calls.get(), 0, "{label} range reached the runner");
        assert_eq!(bounded_error_code(error), expected_code, "{label} range");
    }
}

#[test]
fn positional_reads_reject_short_overlong_and_overflowing_ranges_before_runner() {
    let mut first_read = true;
    let truncated = positional_read_exact(64, 4, |_position, destination| {
        if first_read {
            first_read = false;
            destination[..2].copy_from_slice(&[1, 2]);
            Ok(2)
        } else {
            Ok(0)
        }
    })
    .expect_err("a short positional read must fail closed");
    assert_eq!(bounded_error_code(truncated), "invalid_byte_count");

    let overlong = positional_read_exact(64, 4, |_position, destination| Ok(destination.len() + 1))
        .expect_err("an impossible overlong read result must fail closed");
    assert_eq!(bounded_error_code(overlong), "invalid_byte_count");

    let overflowing = positional_read_exact(u64::MAX, 1, |_position, _destination| {
        panic!("overflow must fail before the reader is called")
    })
    .expect_err("an overflowing positional range must fail closed");
    assert_eq!(bounded_error_code(overflowing), "invalid_tensor_range");

    let unbounded = positional_read_exact(
        0,
        ROUTER_TENSOR_BYTES as usize + 1,
        |_position, _destination| panic!("an unbounded read must fail before allocation or I/O"),
    )
    .expect_err("a read larger than the complete router range must fail closed");
    assert_eq!(bounded_error_code(unbounded), "invalid_byte_count");
}

#[test]
#[cfg(unix)]
fn wrong_f32_type_dimensions_and_orientation_have_exact_failure_codes() {
    let bytes = vec![0_u8; ROUTER_TENSOR_BYTES as usize];
    let mut wrong_type = execution_descriptor_for_bytes(&bytes);
    wrong_type.gguf_type = "Q8_0".to_owned();
    let mut wrong_quantization = execution_descriptor_for_bytes(&bytes);
    wrong_quantization.quantization = "Q8_0".to_owned();
    let mut wrong_gguf_dimensions = execution_descriptor_for_bytes(&bytes);
    wrong_gguf_dimensions.gguf_dimensions_fastest_axis_first = vec![128, 2_048];
    let mut wrong_reader_shape = execution_descriptor_for_bytes(&bytes);
    wrong_reader_shape.reader_shape = vec![2_048, 128];
    let mut wrong_execution_shape = execution_descriptor_for_bytes(&bytes);
    wrong_execution_shape.execution_shape = vec![2_048, 128];
    let mut wrong_orientation = execution_descriptor_for_bytes(&bytes);
    wrong_orientation.orientation = "input_major_rows_expert_columns".to_owned();

    let cases = [
        ("gguf-type", wrong_type, "unsupported_tensor_quantization"),
        (
            "quantization",
            wrong_quantization,
            "unsupported_tensor_quantization",
        ),
        (
            "gguf-dimensions",
            wrong_gguf_dimensions,
            "model_tensor_mismatch",
        ),
        ("reader-shape", wrong_reader_shape, "model_tensor_mismatch"),
        (
            "execution-shape",
            wrong_execution_shape,
            "model_tensor_mismatch",
        ),
        ("orientation", wrong_orientation, "invalid_layout"),
    ];

    for (label, descriptor, expected_code) in cases {
        let runner_calls = Cell::new(0_u32);
        let error = production_preflight_with_bytes(
            label,
            &bytes,
            &descriptor,
            &admitted_resources(),
            |_| runner_calls.set(runner_calls.get() + 1),
        )
        .expect_err("an incompatible F32 tensor contract must fail before execution");
        assert_eq!(runner_calls.get(), 0, "{label} reached the runner");
        assert_eq!(bounded_error_code(error), expected_code, "{label}");
    }
}

#[test]
#[cfg(unix)]
fn invalid_top_k_values_fail_before_runner() {
    let bytes = vec![0_u8; ROUTER_TENSOR_BYTES as usize];
    for top_k in [0, 7, 9, 128, 129] {
        let mut descriptor = execution_descriptor_for_bytes(&bytes);
        descriptor.top_k = top_k;
        let runner_calls = Cell::new(0_u32);
        let error = production_preflight_with_bytes(
            "top-k",
            &bytes,
            &descriptor,
            &admitted_resources(),
            |_| runner_calls.set(runner_calls.get() + 1),
        )
        .expect_err("only the exact top-8 contract may be admitted");
        assert_eq!(runner_calls.get(), 0, "top_k={top_k} reached the runner");
        assert_eq!(bounded_error_code(error), "model_tensor_mismatch");
    }
}

#[test]
fn non_finite_canonical_f32_data_is_rejected() {
    for value in [f32::NAN, f32::INFINITY, f32::NEG_INFINITY] {
        let error = canonical_f32le_sha256(&[0.0, value, 1.0])
            .expect_err("canonical router data must be finite");
        assert_eq!(bounded_error_code(error), "invalid_dtype");
    }
}

#[cfg(unix)]
#[test]
fn changed_range_identity_rejects_execution_after_exact_admission() {
    let directory = IsolatedDirectory::new("changed-identity");
    let path = directory.path().join("synthetic-router.bin");
    let bytes = vec![0_u8; ROUTER_TENSOR_BYTES as usize];
    fs::write(&path, &bytes).expect("write bounded synthetic router bytes");

    let mut descriptor = execution_descriptor_for_bytes(&bytes);
    descriptor.encoded_sha256 = "b".repeat(64);
    let file = File::open(&path).expect("open synthetic router fixture read-only");
    let runner_calls = Cell::new(0_u32);
    let error = with_admitted_router_tensor_f32(
        &file,
        &descriptor,
        ROUTER_TENSOR_BYTES,
        &admitted_resources(),
        |_admitted, _values| {
            runner_calls.set(runner_calls.get() + 1);
            Ok(())
        },
    )
    .expect_err("bytes that differ from the frozen range identity must fail");

    assert_eq!(runner_calls.get(), 0);
    assert_eq!(bounded_error_code(error), "model_checksum_mismatch");
}

#[cfg(unix)]
#[test]
fn changed_file_length_and_resource_failures_precede_production_runner() {
    let bytes = vec![0_u8; ROUTER_TENSOR_BYTES as usize];
    let descriptor = execution_descriptor_for_bytes(&bytes);
    let directory = IsolatedDirectory::new("file-length-and-resources");
    let path = directory.path().join("synthetic-router.bin");
    fs::write(&path, &bytes).expect("write bounded synthetic router fixture");
    let file = File::open(&path).expect("open synthetic router fixture read-only");

    let runner_calls = Cell::new(0_u32);
    let size_error = with_admitted_router_tensor_f32(
        &file,
        &descriptor,
        ROUTER_TENSOR_BYTES + 4,
        &admitted_resources(),
        |_admitted, _values| {
            runner_calls.set(runner_calls.get() + 1);
            Ok(())
        },
    )
    .expect_err("a changed artifact length must fail before execution");
    assert_eq!(runner_calls.get(), 0);
    assert_eq!(bounded_error_code(size_error), "model_size_mismatch");

    for (label, resources) in [
        (
            "disk",
            RouterResourceAdmission {
                disk_headroom_satisfied: false,
                ..admitted_resources()
            },
        ),
        (
            "unified-memory",
            RouterResourceAdmission {
                unified_memory_headroom_satisfied: false,
                ..admitted_resources()
            },
        ),
        (
            "memory-pressure",
            RouterResourceAdmission {
                memory_pressure_normal: false,
                ..admitted_resources()
            },
        ),
    ] {
        let error = with_admitted_router_tensor_f32(
            &file,
            &descriptor,
            ROUTER_TENSOR_BYTES,
            &resources,
            |_admitted, _values| {
                runner_calls.set(runner_calls.get() + 1);
                Ok(())
            },
        )
        .expect_err("a failed resource gate must precede execution");
        assert_eq!(runner_calls.get(), 0, "{label} gate reached the runner");
        assert_eq!(
            bounded_error_code(error),
            "model_budget_exceeded",
            "{label}"
        );
    }
}

#[cfg(unix)]
#[test]
fn matching_non_finite_f32_tensor_bytes_fail_before_runner() {
    let directory = IsolatedDirectory::new("non-finite");
    let path = directory.path().join("synthetic-router.bin");
    let mut bytes = vec![0_u8; ROUTER_TENSOR_BYTES as usize];
    bytes[..4].copy_from_slice(&f32::NAN.to_le_bytes());
    fs::write(&path, &bytes).expect("write bounded non-finite router fixture");
    let descriptor = execution_descriptor_for_bytes(&bytes);
    let file = File::open(&path).expect("open synthetic router fixture read-only");
    let runner_calls = Cell::new(0_u32);
    let error = with_admitted_router_tensor_f32(
        &file,
        &descriptor,
        ROUTER_TENSOR_BYTES,
        &admitted_resources(),
        |_admitted, _values| {
            runner_calls.set(runner_calls.get() + 1);
            Ok(())
        },
    )
    .expect_err("a hash-matching tensor with non-finite F32 data must fail");

    assert_eq!(runner_calls.get(), 0);
    assert_eq!(bounded_error_code(error), "invalid_dtype");
}

#[cfg(unix)]
#[test]
fn hard_link_and_symlink_mutations_cannot_bypass_range_identity_or_reach_runner() {
    use std::os::unix::fs::symlink;

    for alias_kind in ["hard-link", "symlink"] {
        let directory = IsolatedDirectory::new(alias_kind);
        let path = directory.path().join("synthetic-router.bin");
        let alias = directory.path().join("router-alias.bin");
        let bytes = vec![0_u8; ROUTER_TENSOR_BYTES as usize];
        fs::write(&path, &bytes).expect("write bounded synthetic router bytes");
        let descriptor = execution_descriptor_for_bytes(&bytes);
        let file = File::open(&path).expect("retain the original read-only file description");

        match alias_kind {
            "hard-link" => fs::hard_link(&path, &alias).expect("create hard-link alias"),
            "symlink" => symlink(&path, &alias).expect("create symbolic-link alias"),
            _ => unreachable!("bounded alias inventory"),
        }
        let mut alias_writer = OpenOptions::new()
            .write(true)
            .open(&alias)
            .expect("open alias for the synthetic mutation");
        alias_writer
            .write_all(&1.0_f32.to_le_bytes())
            .expect("mutate the admitted range through its alias");
        alias_writer
            .sync_all()
            .expect("synchronize the synthetic alias mutation");

        let runner_calls = Cell::new(0_u32);
        let error = with_admitted_router_tensor_f32(
            &file,
            &descriptor,
            ROUTER_TENSOR_BYTES,
            &admitted_resources(),
            |_admitted, _values| {
                runner_calls.set(runner_calls.get() + 1);
                Ok(())
            },
        )
        .expect_err("alias mutation must invalidate the frozen range identity");
        assert_eq!(runner_calls.get(), 0, "{alias_kind} reached the runner");
        assert_eq!(
            bounded_error_code(error),
            "model_checksum_mismatch",
            "{alias_kind} mutation"
        );
    }
}

#[cfg(unix)]
#[test]
fn exact_finite_range_reaches_the_test_runner_once_as_a_control() {
    let directory = IsolatedDirectory::new("valid-control");
    let path = directory.path().join("synthetic-router.bin");
    let bytes = vec![0_u8; ROUTER_TENSOR_BYTES as usize];
    fs::write(&path, &bytes).expect("write bounded finite router fixture");
    let descriptor = execution_descriptor_for_bytes(&bytes);
    let file = File::open(&path).expect("open synthetic router fixture read-only");
    let runner_calls = Cell::new(0_u32);
    with_admitted_router_tensor_f32(
        &file,
        &descriptor,
        ROUTER_TENSOR_BYTES,
        &admitted_resources(),
        |_admitted, values| {
            assert_eq!(values.len(), 262_144);
            runner_calls.set(runner_calls.get() + 1);
            Ok(())
        },
    )
    .expect("the exact finite range reaches the execution seam");
    assert_eq!(runner_calls.get(), 1);
}

#[test]
fn complete_outputs_preserve_all_128_values_and_ordered_top8_per_row() {
    let output = fixture_output();

    assert_eq!(output.case_id(), "synthetic-two-row-router-v1");
    assert_eq!(output.row_count(), 2);
    assert_eq!(output.logits_shape(), &[2, 128]);
    assert_eq!(output.full_probabilities_shape(), &[2, 128]);
    assert_eq!(output.logits().len(), 256);
    assert_eq!(output.full_probabilities().len(), 256);
    assert_eq!(output.selected_expert_ids().len(), 2);
    assert_eq!(output.selected_probabilities().len(), 2);
    assert_eq!(output.normalized_weights().len(), 2);

    assert_eq!(
        output.selected_expert_ids()[0],
        [127, 126, 125, 124, 123, 122, 121, 120]
    );
    assert_eq!(output.selected_expert_ids()[1], [0, 1, 2, 3, 4, 5, 6, 7]);

    for row_index in 0..2 {
        let probability_row = &output.full_probabilities()[row_index * 128..(row_index + 1) * 128];
        assert!((probability_row.iter().sum::<f32>() - 1.0).abs() <= 1.0e-6);
        assert_eq!(output.selected_expert_ids()[row_index].len(), 8);
        assert_eq!(output.selected_probabilities()[row_index].len(), 8);
        assert_eq!(output.normalized_weights()[row_index].len(), 8);

        for (selected_slot, expert_id) in output.selected_expert_ids()[row_index].iter().enumerate()
        {
            let expert_id = usize::try_from(*expert_id).expect("expert ID fits usize");
            assert_eq!(
                output.selected_probabilities()[row_index][selected_slot],
                probability_row[expert_id],
                "selected probabilities are the complete-softmax values before renormalization"
            );
        }

        assert!((output.normalized_weights()[row_index].iter().sum::<f32>() - 1.0).abs() <= 1.0e-6);
    }
}

#[test]
fn synthetic_exact_and_near_cutoff_fixtures_follow_normative_order() {
    let exact = output_from_synthetic_tie_case(
        synthetic_tie_case("exact_tie"),
        RouterCaseScope::SyntheticFixture,
    )
    .expect("the synthetic exact cutoff tie uses the deterministic lower-ID rule");
    assert_eq!(exact.case_scope(), RouterCaseScope::SyntheticFixture);
    assert_eq!(exact.selected_expert_ids(), &[vec![0, 1, 2, 3, 4, 5, 6, 7]]);
    let exact_probabilities = exact.full_probabilities();
    assert_eq!(exact_probabilities[7], exact_probabilities[8]);

    let near = output_from_synthetic_tie_case(
        synthetic_tie_case("near_tie"),
        RouterCaseScope::SyntheticFixture,
    )
    .expect("the synthetic representable near tie remains strictly ordered");
    assert_eq!(near.case_scope(), RouterCaseScope::SyntheticFixture);
    assert_eq!(near.selected_expert_ids(), &[vec![0, 1, 2, 3, 4, 5, 6, 8]]);
    let near_probabilities = near.full_probabilities();
    assert!(near_probabilities[8] > near_probabilities[7]);
}

#[test]
fn real_cutoff_scope_stops_exact_f32_tie_and_allows_near_tie() {
    let error = output_from_synthetic_tie_case(
        synthetic_tie_case("exact_tie"),
        RouterCaseScope::RealCheckpoint,
    )
    .expect_err("a real rank-8/rank-9 exact F32 probability tie must stop parity");
    assert_eq!(bounded_error_code(error), "comparison_failed");

    let near = output_from_synthetic_tie_case(
        synthetic_tie_case("near_tie"),
        RouterCaseScope::RealCheckpoint,
    )
    .expect("a representable real-policy near tie remains admissible");
    assert_eq!(near.case_scope(), RouterCaseScope::RealCheckpoint);
    assert_eq!(near.selected_expert_ids(), &[vec![0, 1, 2, 3, 4, 5, 6, 8]]);
}

#[test]
fn scope_is_part_of_comparison_and_repeat_identity() {
    let synthetic = output_from_synthetic_tie_case(
        synthetic_tie_case("near_tie"),
        RouterCaseScope::SyntheticFixture,
    )
    .expect("synthetic near-tie output");
    let real = output_from_synthetic_tie_case(
        synthetic_tie_case("near_tie"),
        RouterCaseScope::RealCheckpoint,
    )
    .expect("real-policy near-tie output");

    let comparison_error =
        compare_router_outputs(&synthetic, &real, &RouterTolerancePolicy::contract_v1())
            .expect_err("synthetic and real-checkpoint scopes must never compare as peers");
    assert_eq!(bounded_error_code(comparison_error), "comparison_failed");

    let synthetic_identity = synthetic.repeat_identity();
    let real_identity = real.repeat_identity();
    assert_ne!(synthetic_identity, real_identity);
    let mut identities = vec![synthetic_identity; 10];
    identities[9] = real_identity;
    let repeat_error = validate_repeat_identities(&identities)
        .expect_err("repeat identity must retain the synthetic-versus-real scope");
    assert_eq!(bounded_error_code(repeat_error), "comparison_failed");
}

#[test]
fn canonical_hashes_are_f32_little_endian_and_cover_each_complete_output() {
    let digest =
        canonical_f32le_sha256(&[0.0, 1.0, -2.5, -0.0]).expect("finite canonical F32 values hash");
    assert_eq!(
        digest,
        "39044cedea2113aea8f6396a56c4880474de6822b244c0bfe1a706d1228a7700"
    );

    let output = fixture_output();
    assert_eq!(
        output.logits_f32le_sha256(),
        canonical_f32le_sha256(output.logits()).expect("complete logits hash")
    );
    assert_eq!(
        output.full_probabilities_f32le_sha256(),
        canonical_f32le_sha256(output.full_probabilities()).expect("complete probabilities hash")
    );

    let selected: Vec<f32> = output
        .selected_probabilities()
        .iter()
        .flatten()
        .copied()
        .collect();
    let normalized: Vec<f32> = output
        .normalized_weights()
        .iter()
        .flatten()
        .copied()
        .collect();
    assert_eq!(
        output.selected_probabilities_f32le_sha256(),
        canonical_f32le_sha256(&selected).expect("complete selected-probability hash")
    );
    assert_eq!(
        output.normalized_weights_f32le_sha256(),
        canonical_f32le_sha256(&normalized).expect("complete normalized-weight hash")
    );
}

#[test]
fn full_output_comparisons_report_all_counts_and_bounded_error_metrics() {
    let reference = fixture_output();
    let exact = compare_router_outputs(
        &reference,
        &reference,
        &RouterTolerancePolicy::contract_v1(),
    )
    .expect("identical complete outputs compare");

    assert!(exact.passed());
    assert_eq!(exact.id_mismatch_count(), 0);
    assert_eq!(exact.order_mismatch_count(), 0);
    for comparison in [
        exact.logits(),
        exact.full_probabilities(),
        exact.selected_probabilities(),
        exact.normalized_weights(),
    ] {
        assert_eq!(comparison.mismatch_count(), 0);
        assert_eq!(comparison.maximum_absolute_error(), 0.0);
        assert_eq!(comparison.mean_absolute_error(), 0.0);
        assert_eq!(comparison.rmse(), 0.0);
        assert_eq!(comparison.maximum_relative_error(), Some(0.0));
        assert!(comparison.first_mismatch().is_none());
    }
    assert_eq!(exact.logits().compared_count(), 256);
    assert_eq!(exact.full_probabilities().compared_count(), 256);
    assert_eq!(exact.selected_probabilities().compared_count(), 16);
    assert_eq!(exact.normalized_weights().compared_count(), 16);

    let candidate = fixture_output_with_last_logit_delta(0.01);
    let mismatch = compare_router_outputs(
        &reference,
        &candidate,
        &RouterTolerancePolicy::contract_v1(),
    )
    .expect("complete mismatched outputs still produce comparison evidence");
    assert!(!mismatch.passed());
    assert_eq!(mismatch.logits().compared_count(), 256);
    assert_eq!(mismatch.logits().mismatch_count(), 1);
    assert!(mismatch.logits().maximum_absolute_error() > 0.009);
    assert!(mismatch.logits().mean_absolute_error() > 0.0);
    assert!(mismatch.logits().rmse() > 0.0);
    assert!(mismatch.logits().maximum_relative_error().is_some());

    let first = mismatch
        .logits()
        .first_mismatch()
        .expect("the first logit mismatch is retained");
    assert_eq!(first.row_index(), 1);
    assert_eq!(first.column_index(), 127);
    assert!(first.reference().is_finite());
    assert!(first.candidate().is_finite());
}

#[test]
fn ten_repetitions_require_identical_complete_hashes_and_route_order() {
    let output = fixture_output();
    let identity = output.repeat_identity();
    let ten_identical = vec![identity.clone(); 10];
    let summary = validate_repeat_identities(&ten_identical)
        .expect("ten bitwise-identical complete router outputs pass");

    assert_eq!(summary.repeat_count(), 10);
    assert_eq!(summary.unique_output_identity_count(), 1);
    assert!(summary.identical());

    let mut changed = ten_identical;
    changed[9] = fixture_output_with_last_logit_delta(0.01).repeat_identity();
    let error = validate_repeat_identities(&changed)
        .expect_err("one changed complete-output hash must fail repeat identity");
    assert_eq!(error.code(), "comparison_failed");
}
