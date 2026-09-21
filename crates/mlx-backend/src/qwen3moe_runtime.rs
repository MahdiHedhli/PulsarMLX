//! Model-free Qwen3MoE routed-FFN reference execution.
//!
//! This module consumes one bounded, committed f32 fixture. It has no model
//! path, payload buffer, device handle, decoder, tokenizer, or fallback path.
//! Its computed logits are passed to the backend-owned greedy loop.

use backend::{
    generate_greedy, CancellationToken, ContractError, ErrorCategory, GenerationRequest,
    GenerationResult, LogitsOutput, LogitsRuntime, TerminationReason, MAX_NEW_TOKENS,
    MAX_PROMPT_TOKENS, MAX_TOPK,
};
use serde::{Deserialize, Serialize};
use std::cmp::Ordering;
use std::collections::BTreeSet;

pub const QWEN3MOE_SYNTHETIC_FIXTURE_SCHEMA: &str = "pulsarmlx.fixture.qwen3moe-ffn-generation-v1";
pub const QWEN3MOE_SYNTHETIC_FIXTURE_ID: &str = "qwen3moe-ffn-generation-v1";
pub const QWEN3MOE_SYNTHETIC_OPERATION_COUNT: usize = 10;
pub const QWEN3MOE_SYNTHETIC_MAX_ELEMENTS: usize = 65_536;
const QWEN3MOE_SYNTHETIC_MAX_BYTES: usize = 1024 * 1024;
const EXCLUSIONS: [&str; 8] = [
    "checkpoint payload bytes",
    "Q8_0 decode",
    "external path/FD/range reads",
    "MLX execution",
    "attention/KV/full 48-layer forward",
    "tokenizer",
    "serving or benchmark",
    "checkpoint qualification or production readiness",
];
const OPERATION_ORDER: [&str; QWEN3MOE_SYNTHETIC_OPERATION_COUNT] = [
    "ffn_input_rms_norm",
    "router_projection",
    "full_softmax_top_k",
    "expert_gate_projection",
    "expert_up_projection",
    "swiglu_activation",
    "expert_down_projection",
    "routed_expert_weighted_aggregate",
    "ffn_residual_add",
    "output_projection",
];
const ROUTING_NORMALIZATION: &str = "full_softmax_then_selected_probability_renormalization";
const ROUTING_TIE_RULE: &str = "probability_descending_then_expert_id_ascending";

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Qwen3MoeSyntheticFixture {
    pub schema: String,
    pub schema_version: u32,
    pub fixture_id: String,
    pub fixture_kind: String,
    pub evidence_level: String,
    pub model_free: bool,
    pub uses_checkpoint_payload_bytes: bool,
    pub contract_id: String,
    pub architecture: String,
    pub target_dimensions: Qwen3MoeTargetDimensions,
    pub execution_dimensions: Qwen3MoeExecutionDimensions,
    pub operation_order: Vec<String>,
    pub routing: Qwen3MoeRoutingContract,
    pub tensors: Qwen3MoeSyntheticTensors,
    pub prompt_token_ids: Vec<u32>,
    pub max_new_tokens: u32,
    pub eos_token_id: u32,
    pub steps: Vec<Qwen3MoeSyntheticInputStep>,
    pub oracle: Qwen3MoeSyntheticOracle,
    pub exclusions: Vec<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Qwen3MoeTargetDimensions {
    pub hidden_width: u64,
    pub expert_count: u64,
    pub top_k: u64,
    pub expert_ffn_width: u64,
    pub layers: u64,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Qwen3MoeExecutionDimensions {
    pub hidden_width: usize,
    pub intermediate_width: usize,
    pub expert_count: usize,
    pub top_k: usize,
    pub dtype: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Qwen3MoeRoutingContract {
    pub normalization: String,
    pub tie_rule: String,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Qwen3MoeSyntheticTensors {
    pub rms_norm_weight: Vec<f32>,
    pub rms_norm_epsilon: f32,
    pub router_weight: Vec<Vec<f32>>,
    pub expert_gate_weight: Vec<Vec<Vec<f32>>>,
    pub expert_up_weight: Vec<Vec<Vec<f32>>>,
    pub expert_down_weight: Vec<Vec<Vec<f32>>>,
    pub output_token_ids: Vec<u32>,
    pub output_projection_weight: Vec<Vec<f32>>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Qwen3MoeSyntheticInputStep {
    pub position: u64,
    pub input: Vec<f32>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Qwen3MoeSyntheticOracle {
    pub independently_generated: bool,
    pub generator: String,
    pub tolerance: f32,
    pub steps: Vec<Qwen3MoeSyntheticOracleStep>,
    pub expected_generated_token_ids: Vec<u32>,
    pub expected_full_token_ids: Vec<u32>,
    pub termination_reason: String,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Qwen3MoeSyntheticOracleStep {
    pub normalized_input: Vec<f32>,
    pub router_logits: Vec<f32>,
    pub full_softmax_probabilities: Vec<f32>,
    pub selected_expert_ids: Vec<u32>,
    pub selected_probabilities: Vec<f32>,
    pub normalized_selected_probabilities: Vec<f32>,
    pub expert_outputs: Vec<Vec<f32>>,
    pub routed_aggregate: Vec<f32>,
    pub residual: Vec<f32>,
    pub logits: Vec<f32>,
    pub topk: Vec<Qwen3MoeOracleLogit>,
    pub argmax: u32,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Qwen3MoeOracleLogit {
    pub token_id: u32,
    pub score: f32,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Qwen3MoeStepEvidence {
    pub step: u32,
    pub position: u64,
    pub normalized_input: Vec<f32>,
    pub router_logits: Vec<f32>,
    pub full_softmax_probabilities: Vec<f32>,
    pub selected_expert_ids: Vec<u32>,
    pub selected_probabilities: Vec<f32>,
    pub normalized_selected_probabilities: Vec<f32>,
    pub expert_outputs: Vec<Vec<f32>>,
    pub routed_aggregate: Vec<f32>,
    pub residual: Vec<f32>,
    pub logits: Vec<f32>,
    pub topk: Vec<(u32, f32)>,
    pub argmax: u32,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Qwen3MoeSyntheticGenerationResult {
    pub fixture_id: String,
    pub contract_id: String,
    pub generation: GenerationResult,
    pub steps: Vec<Qwen3MoeStepEvidence>,
    pub evaluated: bool,
    pub fallback_used: bool,
}

impl Qwen3MoeSyntheticGenerationResult {
    pub fn generated_token_ids(&self) -> &[u32] {
        self.generation.generated_token_ids()
    }

    pub fn full_token_ids(&self) -> &[u32] {
        self.generation.full_token_ids()
    }

    pub fn prompt_token_ids(&self) -> &[u32] {
        self.generation.prompt_token_ids()
    }

    pub fn termination_reason(&self) -> TerminationReason {
        self.generation.termination_reason()
    }
}

/// Parse and validate a duplicate-free, closed Qwen synthetic fixture.
///
/// `deny_unknown_fields` on every object prevents model paths, payload bytes,
/// arbitrary tensor selectors, and other unreviewed fields from entering the
/// reference runtime.
pub fn parse_qwen3moe_synthetic_fixture(
    bytes: &[u8],
) -> Result<Qwen3MoeSyntheticFixture, ContractError> {
    if bytes.is_empty() || bytes.len() > QWEN3MOE_SYNTHETIC_MAX_BYTES {
        return Err(fixture_error(
            "fixture_byte_limit",
            "the Qwen synthetic fixture exceeds its bounded byte limit",
        ));
    }
    let fixture: Qwen3MoeSyntheticFixture = serde_json::from_slice(bytes).map_err(|_| {
        fixture_error(
            "fixture_parse_error",
            "the Qwen synthetic fixture is not strict bounded JSON",
        )
    })?;
    validate_qwen3moe_synthetic_fixture(&fixture)?;
    Ok(fixture)
}

/// Validate all fixture structure, shape, finite-value, routing, and oracle
/// invariants before any reference arithmetic is scheduled.
pub fn validate_qwen3moe_synthetic_fixture(
    fixture: &Qwen3MoeSyntheticFixture,
) -> Result<(), ContractError> {
    if fixture.schema != QWEN3MOE_SYNTHETIC_FIXTURE_SCHEMA
        || fixture.schema_version != 1
        || fixture.fixture_id != QWEN3MOE_SYNTHETIC_FIXTURE_ID
        || fixture.fixture_kind != "qwen3moe_synthetic_ffn_generation"
        || fixture.evidence_level != "synthetic_fixture_only"
        || !fixture.model_free
        || fixture.uses_checkpoint_payload_bytes
        || fixture.contract_id != "qwen3moe-full-graph-admission-v1"
        || fixture.architecture != "qwen3moe"
    {
        return Err(fixture_error(
            "fixture_identity_mismatch",
            "the Qwen synthetic fixture identity or model-free boundary is not admitted",
        ));
    }
    if fixture.target_dimensions.hidden_width != 2_048
        || fixture.target_dimensions.expert_count != 128
        || fixture.target_dimensions.top_k != 8
        || fixture.target_dimensions.expert_ffn_width != 768
        || fixture.target_dimensions.layers != 48
    {
        return Err(fixture_error(
            "target_dimensions_mismatch",
            "target dimensions do not match the admitted Qwen3MoE semantics",
        ));
    }
    let dimensions = &fixture.execution_dimensions;
    if dimensions.hidden_width != 4
        || dimensions.intermediate_width != 4
        || dimensions.expert_count != 4
        || dimensions.top_k != 2
        || dimensions.dtype != "f32"
    {
        return Err(fixture_error(
            "execution_shape_mismatch",
            "the fixture execution shape is outside the bounded f32 stand-in",
        ));
    }
    if fixture.operation_order != OPERATION_ORDER
        || fixture.routing.normalization != ROUTING_NORMALIZATION
        || fixture.routing.tie_rule != ROUTING_TIE_RULE
        || fixture.exclusions
            != EXCLUSIONS
                .iter()
                .map(|value| (*value).to_owned())
                .collect::<Vec<_>>()
    {
        return Err(fixture_error(
            "fixture_contract_mismatch",
            "the Qwen synthetic operation or exclusion contract differs",
        ));
    }
    validate_tensors(&fixture.tensors, dimensions)?;
    let request = GenerationRequest::try_new(
        fixture.prompt_token_ids.clone(),
        fixture.max_new_tokens,
        Some(fixture.eos_token_id),
    )?;
    if request.eos_token_id() != Some(0)
        || fixture.steps.len() != fixture.max_new_tokens as usize
        || fixture.oracle.steps.len() != fixture.steps.len()
        || fixture.oracle.expected_full_token_ids.len()
            != fixture.prompt_token_ids.len() + fixture.oracle.expected_generated_token_ids.len()
        || fixture.oracle.expected_full_token_ids[..fixture.prompt_token_ids.len()]
            != fixture.prompt_token_ids[..]
        || fixture.oracle.termination_reason != "eos_token"
        || fixture.oracle.expected_generated_token_ids.is_empty()
    {
        return Err(fixture_error(
            "fixture_generation_bounds",
            "the fixture generation sequence or oracle bounds are invalid",
        ));
    }
    if !fixture.oracle.independently_generated
        || fixture.oracle.generator != "standalone_f32_scalar_reference_v1"
        || !fixture.oracle.tolerance.is_finite()
        || fixture.oracle.tolerance <= 0.0
        || fixture.oracle.tolerance > 0.01
    {
        return Err(fixture_error(
            "oracle_contract_mismatch",
            "the fixture oracle is not an independently generated finite reference",
        ));
    }
    let prompt_length = fixture.prompt_token_ids.len() as u64;
    for (index, (input, oracle)) in fixture
        .steps
        .iter()
        .zip(fixture.oracle.steps.iter())
        .enumerate()
    {
        let expected_position = prompt_length + index as u64 + 1;
        if input.position != expected_position
            || input.input.len() != dimensions.hidden_width
            || oracle.selected_expert_ids.len() != dimensions.top_k
            || oracle.selected_probabilities.len() != dimensions.top_k
            || oracle.normalized_selected_probabilities.len() != dimensions.top_k
            || oracle.expert_outputs.len() != dimensions.top_k
            || oracle.normalized_input.len() != dimensions.hidden_width
            || oracle.router_logits.len() != dimensions.expert_count
            || oracle.full_softmax_probabilities.len() != dimensions.expert_count
            || oracle.routed_aggregate.len() != dimensions.hidden_width
            || oracle.residual.len() != dimensions.hidden_width
            || oracle.logits.len() != fixture.tensors.output_token_ids.len()
            || oracle.topk.len() != fixture.tensors.output_token_ids.len()
        {
            return Err(fixture_error(
                "oracle_shape_mismatch",
                "the Qwen synthetic oracle has an invalid bounded shape",
            ));
        }
        if oracle
            .expert_outputs
            .iter()
            .any(|output| output.len() != dimensions.hidden_width)
            || oracle
                .topk
                .iter()
                .any(|logit| !fixture.tensors.output_token_ids.contains(&logit.token_id))
        {
            return Err(fixture_error(
                "oracle_shape_mismatch",
                "the Qwen synthetic oracle has an invalid expert or output shape",
            ));
        }
        let mut selected = BTreeSet::new();
        for (&expert, &probability) in oracle
            .selected_expert_ids
            .iter()
            .zip(oracle.selected_probabilities.iter())
        {
            if usize::try_from(expert)
                .ok()
                .filter(|id| *id < dimensions.expert_count)
                .is_none()
                || !selected.insert(expert)
                || !probability.is_finite()
                || probability < 0.0
            {
                return Err(fixture_error(
                    "oracle_route_mismatch",
                    "the oracle contains an out-of-bounds, duplicate, or non-finite expert",
                ));
            }
        }
        let normalized_sum = sum_f32(&oracle.normalized_selected_probabilities);
        let full_softmax_sum = sum_f32(&oracle.full_softmax_probabilities);
        let selected_sum = sum_f32(&oracle.selected_probabilities);
        let expected_selected =
            deterministic_top_k(&oracle.full_softmax_probabilities, dimensions.top_k)?;
        let actual_selected = oracle
            .selected_expert_ids
            .iter()
            .map(|expert| usize::try_from(*expert).unwrap_or(usize::MAX))
            .collect::<Vec<_>>();
        let probabilities_match = oracle
            .selected_expert_ids
            .iter()
            .zip(oracle.selected_probabilities.iter())
            .all(|(expert, probability)| {
                usize::try_from(*expert)
                    .ok()
                    .and_then(|index| oracle.full_softmax_probabilities.get(index))
                    .is_some_and(|expected| close(*probability, *expected, 2.0e-4))
            });
        let normalized_probabilities_match = oracle
            .selected_probabilities
            .iter()
            .zip(oracle.normalized_selected_probabilities.iter())
            .all(|(probability, normalized)| {
                close(*normalized, f32_div(*probability, selected_sum), 2.0e-4)
            });
        let probabilities_are_bounded = oracle
            .full_softmax_probabilities
            .iter()
            .chain(oracle.selected_probabilities.iter())
            .chain(oracle.normalized_selected_probabilities.iter())
            .all(|probability| (0.0..=1.0).contains(probability));
        if !probabilities_are_bounded
            || !full_softmax_sum.is_finite()
            || (full_softmax_sum - 1.0).abs() > 2.0e-4
            || !selected_sum.is_finite()
            || selected_sum <= 0.0
            || actual_selected != expected_selected
            || !probabilities_match
            || !normalized_probabilities_match
            || !normalized_sum.is_finite()
            || (normalized_sum - 1.0).abs() > 2.0e-4
        {
            return Err(fixture_error(
                "oracle_normalization_mismatch",
                "oracle softmax or selected probabilities are not normalized",
            ));
        }
        let oracle_topk = oracle
            .topk
            .iter()
            .map(|logit| (logit.token_id, logit.score))
            .collect::<Vec<_>>();
        let expected_argmax = select_argmax(&oracle_topk)?;
        if oracle.argmax != expected_argmax
            || oracle.topk.len() != fixture.tensors.output_token_ids.len()
            || oracle_topk
                .iter()
                .map(|(token_id, _)| *token_id)
                .collect::<Vec<_>>()
                != fixture.tensors.output_token_ids
        {
            return Err(fixture_error(
                "oracle_logits_shape_mismatch",
                "oracle logits candidates do not match the synthetic output projection",
            ));
        }
        validate_finite_step(input, oracle)?;
    }
    if fixture.oracle.expected_generated_token_ids.len() != fixture.max_new_tokens as usize
        || fixture.oracle.expected_generated_token_ids.last().copied() != Some(fixture.eos_token_id)
        || fixture.oracle.expected_full_token_ids
            != fixture
                .prompt_token_ids
                .iter()
                .copied()
                .chain(fixture.oracle.expected_generated_token_ids.iter().copied())
                .collect::<Vec<_>>()
    {
        return Err(fixture_error(
            "oracle_generation_mismatch",
            "the oracle token sequence does not match the bounded fixture",
        ));
    }
    Ok(())
}

fn validate_tensors(
    tensors: &Qwen3MoeSyntheticTensors,
    dimensions: &Qwen3MoeExecutionDimensions,
) -> Result<(), ContractError> {
    if tensors.rms_norm_weight.len() != dimensions.hidden_width
        || tensors.router_weight.len() != dimensions.expert_count
        || tensors.expert_gate_weight.len() != dimensions.expert_count
        || tensors.expert_up_weight.len() != dimensions.expert_count
        || tensors.expert_down_weight.len() != dimensions.expert_count
        || tensors.output_token_ids.is_empty()
        || tensors.output_token_ids.len() > MAX_TOPK
        || tensors.output_projection_weight.len() != tensors.output_token_ids.len()
        || !tensors.rms_norm_epsilon.is_finite()
        || tensors.rms_norm_epsilon <= 0.0
    {
        return Err(fixture_error(
            "tensor_shape_mismatch",
            "the Qwen synthetic tensor cardinalities are not admitted",
        ));
    }
    let mut token_ids = BTreeSet::new();
    if tensors
        .output_token_ids
        .iter()
        .any(|token| !token_ids.insert(*token))
    {
        return Err(fixture_error(
            "duplicate_output_token",
            "synthetic output projection token IDs must be unique",
        ));
    }
    let mut elements = tensors.rms_norm_weight.len();
    elements = checked_add_elements(
        elements,
        tensors.router_weight.len() * dimensions.hidden_width,
    )?;
    elements = checked_add_elements(
        elements,
        dimensions.expert_count * dimensions.intermediate_width * dimensions.hidden_width * 3,
    )?;
    elements = checked_add_elements(
        elements,
        tensors.output_token_ids.len() * dimensions.hidden_width,
    )?;
    if elements > QWEN3MOE_SYNTHETIC_MAX_ELEMENTS {
        return Err(fixture_error(
            "fixture_element_limit",
            "synthetic tensor elements exceed the bounded reference limit",
        ));
    }
    if tensors
        .router_weight
        .iter()
        .any(|row| row.len() != dimensions.hidden_width)
        || tensors.expert_gate_weight.iter().any(|expert| {
            !matrix_shape(
                expert,
                dimensions.intermediate_width,
                dimensions.hidden_width,
            )
        })
        || tensors.expert_up_weight.iter().any(|expert| {
            !matrix_shape(
                expert,
                dimensions.intermediate_width,
                dimensions.hidden_width,
            )
        })
        || tensors.expert_down_weight.iter().any(|expert| {
            !matrix_shape(
                expert,
                dimensions.hidden_width,
                dimensions.intermediate_width,
            )
        })
        || tensors
            .output_projection_weight
            .iter()
            .any(|row| row.len() != dimensions.hidden_width)
    {
        return Err(fixture_error(
            "tensor_shape_mismatch",
            "a Qwen synthetic matrix has an invalid shape",
        ));
    }
    if !finite_slice(&tensors.rms_norm_weight)
        || !tensors.router_weight.iter().all(|row| finite_slice(row))
        || !tensors
            .expert_gate_weight
            .iter()
            .flatten()
            .all(|row| finite_slice(row))
        || !tensors
            .expert_up_weight
            .iter()
            .flatten()
            .all(|row| finite_slice(row))
        || !tensors
            .expert_down_weight
            .iter()
            .flatten()
            .all(|row| finite_slice(row))
        || !tensors
            .output_projection_weight
            .iter()
            .all(|row| finite_slice(row))
    {
        return Err(fixture_error(
            "non_finite_tensor",
            "synthetic f32 tensors must contain only finite values",
        ));
    }
    Ok(())
}

fn validate_finite_step(
    input: &Qwen3MoeSyntheticInputStep,
    oracle: &Qwen3MoeSyntheticOracleStep,
) -> Result<(), ContractError> {
    let finite = finite_slice(&input.input)
        && finite_slice(&oracle.normalized_input)
        && finite_slice(&oracle.router_logits)
        && finite_slice(&oracle.full_softmax_probabilities)
        && finite_slice(&oracle.selected_probabilities)
        && finite_slice(&oracle.normalized_selected_probabilities)
        && oracle.expert_outputs.iter().all(|row| finite_slice(row))
        && finite_slice(&oracle.routed_aggregate)
        && finite_slice(&oracle.residual)
        && finite_slice(&oracle.logits)
        && oracle.topk.iter().all(|logit| logit.score.is_finite());
    if !finite {
        return Err(fixture_error(
            "non_finite_oracle",
            "synthetic oracle values must contain only finite values",
        ));
    }
    Ok(())
}

fn matrix_shape(matrix: &[Vec<f32>], rows: usize, columns: usize) -> bool {
    matrix.len() == rows && matrix.iter().all(|row| row.len() == columns)
}

fn checked_add_elements(left: usize, right: usize) -> Result<usize, ContractError> {
    left.checked_add(right).ok_or_else(|| {
        fixture_error(
            "fixture_element_overflow",
            "synthetic tensor element count overflowed",
        )
    })
}

fn finite_slice(values: &[f32]) -> bool {
    values.iter().all(|value| value.is_finite())
}

/// Return the stable top-k indices without relying on input ordering.
pub fn deterministic_top_k(scores: &[f32], top_k: usize) -> Result<Vec<usize>, ContractError> {
    if scores.is_empty() || top_k == 0 || top_k > scores.len() || top_k > MAX_TOPK {
        return Err(fixture_error(
            "invalid_top_k",
            "top-k must be non-zero and within the bounded score list",
        ));
    }
    if !finite_slice(scores) {
        return Err(fixture_error(
            "non_finite_router_score",
            "router scores must contain only finite values",
        ));
    }
    let mut indices = (0..scores.len()).collect::<Vec<_>>();
    indices.sort_by(|left, right| {
        scores[*right]
            .partial_cmp(&scores[*left])
            .unwrap_or(Ordering::Equal)
            .then_with(|| left.cmp(right))
    });
    indices.truncate(top_k);
    Ok(indices)
}

/// A stateful reference logits runtime. The greedy loop remains in `backend`.
pub struct Qwen3MoeSyntheticRuntime {
    fixture: Qwen3MoeSyntheticFixture,
    next_step: usize,
    evidence: Vec<Qwen3MoeStepEvidence>,
    cancel_after_step: Option<u32>,
}

impl Qwen3MoeSyntheticRuntime {
    pub fn new(fixture: Qwen3MoeSyntheticFixture) -> Result<Self, ContractError> {
        validate_qwen3moe_synthetic_fixture(&fixture)?;
        Ok(Self {
            fixture,
            next_step: 0,
            evidence: Vec::new(),
            cancel_after_step: None,
        })
    }

    pub fn with_cancel_after_step(mut self, step: Option<u32>) -> Self {
        self.cancel_after_step = step;
        self
    }

    pub fn evidence(&self) -> &[Qwen3MoeStepEvidence] {
        &self.evidence
    }

    fn compute_step(
        &self,
        step_index: usize,
        cancellation: &CancellationToken,
    ) -> Result<Qwen3MoeStepEvidence, ContractError> {
        cancellation.check()?;
        let tensors = &self.fixture.tensors;
        let dimensions = &self.fixture.execution_dimensions;
        let input_step = self.fixture.steps.get(step_index).ok_or_else(|| {
            fixture_error(
                "missing_logits_step",
                "synthetic generation ran beyond the fixture step bound",
            )
        })?;
        let input = &input_step.input;
        let mut mean_square = 0.0_f32;
        for value in input {
            mean_square = f32_add(mean_square, f32_mul(*value, *value));
        }
        mean_square = f32_div(mean_square, dimensions.hidden_width as f32);
        let denominator = f32_sqrt(f32_add(mean_square, tensors.rms_norm_epsilon));
        let normalized_input = input
            .iter()
            .zip(tensors.rms_norm_weight.iter())
            .map(|(value, weight)| f32_mul(f32_div(*value, denominator), *weight))
            .collect::<Vec<_>>();

        cancellation.check()?;
        let router_logits = tensors
            .router_weight
            .iter()
            .map(|row| matvec(row, &normalized_input))
            .collect::<Vec<_>>();
        cancellation.check()?;
        let maximum = router_logits
            .iter()
            .copied()
            .fold(f32::NEG_INFINITY, f32::max);
        let exponentials = router_logits
            .iter()
            .map(|score| f32_exp(f32_sub(*score, maximum)))
            .collect::<Vec<_>>();
        let exponential_sum = sum_f32(&exponentials);
        let full_softmax_probabilities = exponentials
            .iter()
            .map(|value| f32_div(*value, exponential_sum))
            .collect::<Vec<_>>();
        let selected_indices = deterministic_top_k(&full_softmax_probabilities, dimensions.top_k)?;
        let selected_expert_ids = selected_indices
            .iter()
            .map(|index| *index as u32)
            .collect::<Vec<_>>();
        let selected_probabilities = selected_indices
            .iter()
            .map(|index| full_softmax_probabilities[*index])
            .collect::<Vec<_>>();
        let selected_sum = sum_f32(&selected_probabilities);
        let normalized_selected_probabilities = selected_probabilities
            .iter()
            .map(|value| f32_div(*value, selected_sum))
            .collect::<Vec<_>>();

        cancellation.check()?;
        let mut expert_outputs = Vec::with_capacity(selected_indices.len());
        for &expert_index in &selected_indices {
            cancellation.check()?;
            let gate = tensors.expert_gate_weight[expert_index]
                .iter()
                .map(|row| matvec(row, &normalized_input))
                .collect::<Vec<_>>();
            let up = tensors.expert_up_weight[expert_index]
                .iter()
                .map(|row| matvec(row, &normalized_input))
                .collect::<Vec<_>>();
            let swiglu = gate
                .iter()
                .zip(up.iter())
                .map(|(gate, up)| f32_mul(silu(*gate), *up))
                .collect::<Vec<_>>();
            let output = tensors.expert_down_weight[expert_index]
                .iter()
                .map(|row| matvec(row, &swiglu))
                .collect::<Vec<_>>();
            expert_outputs.push(output);
        }
        cancellation.check()?;
        let mut routed_aggregate = vec![0.0_f32; dimensions.hidden_width];
        for (expert_output, weight) in expert_outputs
            .iter()
            .zip(normalized_selected_probabilities.iter())
        {
            for (aggregate, output) in routed_aggregate.iter_mut().zip(expert_output.iter()) {
                *aggregate = f32_add(*aggregate, f32_mul(*weight, *output));
            }
        }
        let residual = input
            .iter()
            .zip(routed_aggregate.iter())
            .map(|(input, aggregate)| f32_add(*input, *aggregate))
            .collect::<Vec<_>>();
        cancellation.check()?;
        let logits = tensors
            .output_projection_weight
            .iter()
            .map(|row| matvec(row, &residual))
            .collect::<Vec<_>>();
        let topk = tensors
            .output_token_ids
            .iter()
            .copied()
            .zip(logits.iter().copied())
            .collect::<Vec<_>>();
        let argmax = select_argmax(&topk)?;
        Ok(Qwen3MoeStepEvidence {
            step: (step_index + 1) as u32,
            position: self.fixture.steps[step_index].position,
            normalized_input,
            router_logits,
            full_softmax_probabilities,
            selected_expert_ids,
            selected_probabilities,
            normalized_selected_probabilities,
            expert_outputs,
            routed_aggregate,
            residual,
            logits,
            topk,
            argmax,
        })
    }
}

impl LogitsRuntime for Qwen3MoeSyntheticRuntime {
    fn logits(&mut self, cancellation: &CancellationToken) -> Result<LogitsOutput, ContractError> {
        cancellation.check()?;
        let step = self.next_step;
        let evidence = self.compute_step(step, cancellation)?;
        let expected = self.fixture.oracle.steps.get(step).ok_or_else(|| {
            fixture_error(
                "missing_oracle_step",
                "synthetic generation ran beyond the oracle step bound",
            )
        })?;
        compare_step_with_oracle(&evidence, expected, self.fixture.oracle.tolerance)?;
        self.next_step = self.next_step.checked_add(1).ok_or_else(|| {
            fixture_error(
                "step_index_overflow",
                "synthetic generation step index overflowed",
            )
        })?;
        let output = LogitsOutput {
            topk: evidence.topk.clone(),
            argmax: evidence.argmax,
        };
        self.evidence.push(evidence);
        if self.cancel_after_step == Some(self.next_step as u32) {
            cancellation.cancel();
        }
        Ok(output)
    }
}

/// Execute the validated fixture through the existing backend greedy seam.
pub fn run_qwen3moe_synthetic_generation(
    fixture: &Qwen3MoeSyntheticFixture,
    request: &GenerationRequest,
    cancellation: &CancellationToken,
) -> Result<Qwen3MoeSyntheticGenerationResult, ContractError> {
    run_qwen3moe_synthetic_generation_with_cancel_after_step(fixture, request, cancellation, None)
}

pub fn run_qwen3moe_synthetic_generation_with_cancel_after_step(
    fixture: &Qwen3MoeSyntheticFixture,
    request: &GenerationRequest,
    cancellation: &CancellationToken,
    cancel_after_step: Option<u32>,
) -> Result<Qwen3MoeSyntheticGenerationResult, ContractError> {
    validate_qwen3moe_synthetic_fixture(fixture)?;
    if request.prompt_token_ids() != fixture.prompt_token_ids
        || request.eos_token_id() != Some(fixture.eos_token_id)
        || request.max_new_tokens() > fixture.max_new_tokens
    {
        return Err(fixture_error(
            "request_fixture_mismatch",
            "generation request does not match the bounded Qwen fixture",
        ));
    }
    if cancel_after_step == Some(0)
        || cancel_after_step.is_some_and(|step| step > request.max_new_tokens())
    {
        return Err(fixture_error(
            "invalid_cancellation_step",
            "cancellation step is outside the bounded request",
        ));
    }
    let mut runtime =
        Qwen3MoeSyntheticRuntime::new(fixture.clone())?.with_cancel_after_step(cancel_after_step);
    let generation = generate_greedy(&mut runtime, request, cancellation)?;
    compare_generation_with_oracle(fixture, request, &generation)?;
    Ok(Qwen3MoeSyntheticGenerationResult {
        fixture_id: fixture.fixture_id.clone(),
        contract_id: fixture.contract_id.clone(),
        generation,
        steps: runtime.evidence,
        evaluated: true,
        fallback_used: false,
    })
}

fn compare_step_with_oracle(
    actual: &Qwen3MoeStepEvidence,
    expected: &Qwen3MoeSyntheticOracleStep,
    tolerance: f32,
) -> Result<(), ContractError> {
    let matches = close_slice(
        &actual.normalized_input,
        &expected.normalized_input,
        tolerance,
    ) && close_slice(&actual.router_logits, &expected.router_logits, tolerance)
        && close_slice(
            &actual.full_softmax_probabilities,
            &expected.full_softmax_probabilities,
            tolerance,
        )
        && actual.selected_expert_ids == expected.selected_expert_ids
        && close_slice(
            &actual.selected_probabilities,
            &expected.selected_probabilities,
            tolerance,
        )
        && close_slice(
            &actual.normalized_selected_probabilities,
            &expected.normalized_selected_probabilities,
            tolerance,
        )
        && actual.expert_outputs.len() == expected.expert_outputs.len()
        && actual
            .expert_outputs
            .iter()
            .zip(expected.expert_outputs.iter())
            .all(|(actual, expected)| close_slice(actual, expected, tolerance))
        && close_slice(
            &actual.routed_aggregate,
            &expected.routed_aggregate,
            tolerance,
        )
        && close_slice(&actual.residual, &expected.residual, tolerance)
        && close_slice(&actual.logits, &expected.logits, tolerance)
        && actual.argmax == expected.argmax
        && actual.topk.len() == expected.topk.len()
        && actual.topk.iter().zip(expected.topk.iter()).all(
            |((actual_token, actual_score), expected)| {
                *actual_token == expected.token_id
                    && close(*actual_score, expected.score, tolerance)
            },
        );
    if !matches {
        return Err(fixture_error(
            "oracle_mismatch",
            "computed Qwen synthetic FFN evidence differs from its independent oracle",
        ));
    }
    Ok(())
}

fn compare_generation_with_oracle(
    fixture: &Qwen3MoeSyntheticFixture,
    request: &GenerationRequest,
    generation: &GenerationResult,
) -> Result<(), ContractError> {
    let expected_generated =
        &fixture.oracle.expected_generated_token_ids[..request.max_new_tokens() as usize];
    let expected_full = fixture
        .prompt_token_ids
        .iter()
        .copied()
        .chain(expected_generated.iter().copied())
        .collect::<Vec<_>>();
    let expected_termination = if expected_generated.last().copied() == Some(fixture.eos_token_id) {
        TerminationReason::EosToken
    } else {
        TerminationReason::MaxNewTokens
    };
    if generation.generated_token_ids() != expected_generated
        || generation.full_token_ids() != expected_full
        || generation.termination_reason() != expected_termination
    {
        return Err(fixture_error(
            "oracle_generation_mismatch",
            "generated token IDs or termination differ from the independent oracle",
        ));
    }
    Ok(())
}

fn close_slice(actual: &[f32], expected: &[f32], tolerance: f32) -> bool {
    actual.len() == expected.len()
        && actual
            .iter()
            .zip(expected.iter())
            .all(|(actual, expected)| close(*actual, *expected, tolerance))
}

fn close(actual: f32, expected: f32, tolerance: f32) -> bool {
    actual.is_finite()
        && expected.is_finite()
        && (actual - expected).abs() <= tolerance * (1.0 + expected.abs())
}

fn select_argmax(topk: &[(u32, f32)]) -> Result<u32, ContractError> {
    let mut selected = None;
    for &(token_id, score) in topk {
        if !score.is_finite() {
            return Err(fixture_error(
                "non_finite_logits",
                "computed synthetic logits must be finite",
            ));
        }
        if selected.is_none_or(|(best_token, best_score)| {
            score > best_score || (score == best_score && token_id < best_token)
        }) {
            selected = Some((token_id, score));
        }
    }
    selected.map(|(token_id, _)| token_id).ok_or_else(|| {
        fixture_error(
            "empty_logits",
            "computed synthetic output projection returned no candidates",
        )
    })
}

fn matvec(row: &[f32], input: &[f32]) -> f32 {
    row.iter()
        .zip(input.iter())
        .fold(0.0_f32, |sum, (weight, value)| {
            f32_add(sum, f32_mul(*weight, *value))
        })
}

fn sum_f32(values: &[f32]) -> f32 {
    values.iter().copied().fold(0.0_f32, f32_add)
}

fn silu(value: f32) -> f32 {
    f32_mul(value, f32_div(1.0, f32_add(1.0, f32_exp(-value))))
}

#[inline]
fn f32_add(left: f32, right: f32) -> f32 {
    left + right
}

#[inline]
fn f32_sub(left: f32, right: f32) -> f32 {
    left - right
}

#[inline]
fn f32_mul(left: f32, right: f32) -> f32 {
    left * right
}

#[inline]
fn f32_div(left: f32, right: f32) -> f32 {
    left / right
}

#[inline]
fn f32_sqrt(value: f32) -> f32 {
    value.sqrt()
}

#[inline]
fn f32_exp(value: f32) -> f32 {
    value.exp()
}

fn fixture_error(code: &'static str, message: &'static str) -> ContractError {
    ContractError::new(ErrorCategory::InvalidEvidence, code, message)
}

#[allow(dead_code)]
const _: () = {
    assert!(MAX_NEW_TOKENS > 0);
    assert!(MAX_PROMPT_TOKENS > 0);
};
