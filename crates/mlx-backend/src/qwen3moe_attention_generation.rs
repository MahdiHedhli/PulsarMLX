//! Bounded, model-free composition of Qwen3MoE attention residuals and greedy logits.
//!
//! This module stages the existing attention/KV runtime for each logits call and
//! applies only a tiny validated output projection. It never performs model,
//! checkpoint, path, MLX, or fallback work; backend owns greedy decoding.

use backend::{
    generate_greedy, CancellationToken, ContractError, ErrorCategory, GenerationRequest,
    GenerationResult, LogitsOutput, LogitsRuntime, TerminationReason, MAX_TOPK,
};
use serde::Deserialize;
use std::collections::BTreeSet;

pub const QWEN3MOE_ATTENTION_GREEDY_FIXTURE_SCHEMA: &str =
    "pulsarmlx.fixture.qwen3moe-attention-greedy-v1";
pub const QWEN3MOE_ATTENTION_GREEDY_FIXTURE_ID: &str = "qwen3moe-attention-greedy-v1";
pub const QWEN3MOE_ATTENTION_GREEDY_CONTRACT_ID: &str = "qwen3moe-synthetic-attention-greedy-v1";
pub const QWEN3MOE_ATTENTION_GREEDY_MAX_ELEMENTS: usize = 65_536;

const MAX_FIXTURE_BYTES: usize = 1 << 20;
const OPERATION_ORDER: [&str; 4] = [
    "attention_kv_stage",
    "attention_residual",
    "output_projection",
    "greedy_generation",
];
const EXCLUSIONS: [&str; 7] = [
    "checkpoint payload bytes",
    "external path/FD/range reads",
    "MLX or Metal execution",
    "full transformer-layer forward",
    "tokenizer",
    "serving or benchmark",
    "qualification or production readiness",
];

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Qwen3MoeAttentionGreedyFixture {
    pub schema: String,
    pub schema_version: u32,
    pub fixture_id: String,
    pub fixture_kind: String,
    pub evidence_level: String,
    pub model_free: bool,
    pub uses_checkpoint_payload_bytes: bool,
    pub contract_id: String,
    pub architecture: String,
    pub operation_order: Vec<String>,
    pub attention: super::qwen3moe_attention::Qwen3MoeAttentionKvFixture,
    pub output_projection: Qwen3MoeAttentionGreedyOutputProjection,
    pub prompt_token_ids: Vec<u32>,
    pub max_new_tokens: u32,
    pub eos_token_id: u32,
    pub oracle: Qwen3MoeAttentionGreedyOracle,
    pub exclusions: Vec<String>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Qwen3MoeAttentionGreedyOutputProjection {
    pub output_token_ids: Vec<u32>,
    pub output_projection_weight: Vec<Vec<f32>>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Qwen3MoeAttentionGreedyOracle {
    pub independently_generated: bool,
    pub generator: String,
    pub tolerance: f32,
    pub steps: Vec<Qwen3MoeAttentionGreedyOracleStep>,
    pub expected_generated_token_ids: Vec<u32>,
    pub expected_full_token_ids: Vec<u32>,
    pub termination_reason: String,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Qwen3MoeAttentionGreedyOracleStep {
    pub position: u64,
    pub residual: Vec<f32>,
    pub logits: Vec<f32>,
    pub topk: Vec<Qwen3MoeAttentionGreedyOracleLogit>,
    pub argmax: u32,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Qwen3MoeAttentionGreedyOracleLogit {
    pub token_id: u32,
    pub score: f32,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Qwen3MoeAttentionGreedyStepEvidence {
    pub step: u32,
    pub position: u64,
    pub residual: Vec<f32>,
    pub logits: Vec<f32>,
    pub topk: Vec<(u32, f32)>,
    pub argmax: u32,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Qwen3MoeAttentionGreedyGenerationResult {
    pub fixture_id: String,
    pub contract_id: String,
    pub generation: GenerationResult,
    pub steps: Vec<Qwen3MoeAttentionGreedyStepEvidence>,
    pub evaluated: bool,
    pub fallback_used: bool,
}

impl Qwen3MoeAttentionGreedyGenerationResult {
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

/// Parse and validate the closed, bounded JSON composition fixture.
pub fn parse_qwen3moe_attention_greedy_fixture(
    bytes: &[u8],
) -> Result<Qwen3MoeAttentionGreedyFixture, ContractError> {
    if bytes.is_empty() || bytes.len() > MAX_FIXTURE_BYTES {
        return Err(generation_error(
            ErrorCategory::ResourceLimit,
            "fixture_byte_limit",
            "the Qwen attention-to-greedy fixture exceeds its bounded byte limit",
        ));
    }
    let fixture: Qwen3MoeAttentionGreedyFixture = serde_json::from_slice(bytes).map_err(|_| {
        generation_error(
            ErrorCategory::InvalidTensor,
            "fixture_parse_error",
            "the Qwen attention-to-greedy fixture is not strict bounded JSON",
        )
    })?;
    validate_qwen3moe_attention_greedy_fixture(&fixture)?;
    Ok(fixture)
}

/// Validate fixture identity, nested attention admission, projection shape,
/// finite values, generation bounds, and the independent output oracle.
pub fn validate_qwen3moe_attention_greedy_fixture(
    fixture: &Qwen3MoeAttentionGreedyFixture,
) -> Result<(), ContractError> {
    if fixture.schema != QWEN3MOE_ATTENTION_GREEDY_FIXTURE_SCHEMA
        || fixture.schema_version != 1
        || fixture.fixture_id != QWEN3MOE_ATTENTION_GREEDY_FIXTURE_ID
        || fixture.fixture_kind != "qwen3moe_synthetic_attention_greedy"
        || fixture.evidence_level != "synthetic_fixture_only"
        || !fixture.model_free
        || fixture.uses_checkpoint_payload_bytes
        || fixture.contract_id != QWEN3MOE_ATTENTION_GREEDY_CONTRACT_ID
        || fixture.architecture != "qwen3moe"
    {
        return Err(generation_error(
            ErrorCategory::InvalidModel,
            "fixture_identity_mismatch",
            "the Qwen attention-to-greedy identity or model-free boundary is not admitted",
        ));
    }
    if fixture.operation_order
        != OPERATION_ORDER
            .iter()
            .map(|value| (*value).to_owned())
            .collect::<Vec<_>>()
        || fixture.exclusions
            != EXCLUSIONS
                .iter()
                .map(|value| (*value).to_owned())
                .collect::<Vec<_>>()
    {
        return Err(generation_error(
            ErrorCategory::InvalidModel,
            "fixture_contract_mismatch",
            "the Qwen attention-to-greedy operation or exclusion contract differs",
        ));
    }
    super::qwen3moe_attention::validate_qwen3moe_attention_kv_fixture(&fixture.attention)?;
    validate_projection(
        &fixture.output_projection,
        fixture.attention.execution_dimensions.hidden_width,
    )?;

    GenerationRequest::try_new(
        fixture.prompt_token_ids.clone(),
        fixture.max_new_tokens,
        Some(fixture.eos_token_id),
    )?;
    if fixture.max_new_tokens as usize > fixture.attention.steps.len()
        || fixture.oracle.steps.len() != fixture.attention.steps.len()
        || fixture.oracle.steps.len() != fixture.max_new_tokens as usize
        || !fixture.oracle.independently_generated
        || fixture.oracle.generator != "standalone_f32_scalar_reference_v1"
        || !fixture.oracle.tolerance.is_finite()
        || fixture.oracle.tolerance <= 0.0
        || fixture.oracle.tolerance > 1.0e-2
        || fixture.oracle.expected_generated_token_ids.len() != fixture.max_new_tokens as usize
        || fixture.oracle.expected_generated_token_ids.last().copied() != Some(fixture.eos_token_id)
        || fixture.oracle.termination_reason != "eos_token"
        || fixture.oracle.expected_full_token_ids
            != fixture
                .prompt_token_ids
                .iter()
                .copied()
                .chain(fixture.oracle.expected_generated_token_ids.iter().copied())
                .collect::<Vec<_>>()
    {
        return Err(generation_error(
            ErrorCategory::InvalidEvidence,
            "fixture_generation_bounds",
            "the Qwen attention-to-greedy sequence or oracle bounds are invalid",
        ));
    }
    let hidden_width = fixture.attention.execution_dimensions.hidden_width;
    let output_len = fixture.output_projection.output_token_ids.len();
    for (index, (attention_step, oracle)) in fixture
        .attention
        .steps
        .iter()
        .zip(fixture.oracle.steps.iter())
        .enumerate()
    {
        if oracle.position != attention_step.position
            || oracle.residual.len() != hidden_width
            || oracle.logits.len() != output_len
            || oracle.topk.len() != output_len
            || oracle
                .topk
                .iter()
                .map(|logit| logit.token_id)
                .collect::<Vec<_>>()
                != fixture.output_projection.output_token_ids
            || !finite_slice(&oracle.residual)
            || !finite_slice(&oracle.logits)
            || !oracle.topk.iter().all(|logit| logit.score.is_finite())
        {
            return Err(generation_error(
                ErrorCategory::InvalidEvidence,
                "oracle_shape_mismatch",
                "the output oracle has an invalid bounded shape or token order",
            ));
        }
        if oracle.argmax != fixture.oracle.expected_generated_token_ids[index]
            || select_argmax(
                &oracle
                    .topk
                    .iter()
                    .map(|logit| (logit.token_id, logit.score))
                    .collect::<Vec<_>>(),
            )? != oracle.argmax
        {
            return Err(generation_error(
                ErrorCategory::InvalidEvidence,
                "oracle_argmax_mismatch",
                "the output oracle argmax does not follow deterministic greedy ordering",
            ));
        }
    }
    Ok(())
}

fn validate_projection(
    projection: &Qwen3MoeAttentionGreedyOutputProjection,
    hidden_width: usize,
) -> Result<(), ContractError> {
    if projection.output_token_ids.is_empty()
        || projection.output_token_ids.len() > MAX_TOPK
        || projection.output_projection_weight.len() != projection.output_token_ids.len()
        || projection
            .output_projection_weight
            .iter()
            .any(|row| row.len() != hidden_width)
    {
        return Err(generation_error(
            ErrorCategory::InvalidTensor,
            "tensor_shape_mismatch",
            "the output projection shape is outside the bounded attention-to-greedy seam",
        ));
    }
    let mut token_ids = BTreeSet::new();
    if projection
        .output_token_ids
        .iter()
        .any(|token_id| !token_ids.insert(*token_id))
    {
        return Err(generation_error(
            ErrorCategory::InvalidTensor,
            "duplicate_output_token",
            "output projection token IDs must be unique",
        ));
    }
    let elements = projection
        .output_token_ids
        .len()
        .checked_mul(hidden_width)
        .ok_or_else(|| {
            generation_error(
                ErrorCategory::ArithmeticOverflow,
                "tensor_element_overflow",
                "output projection element count overflowed",
            )
        })?;
    if elements > QWEN3MOE_ATTENTION_GREEDY_MAX_ELEMENTS
        || !projection
            .output_projection_weight
            .iter()
            .all(|row| finite_slice(row))
    {
        return Err(generation_error(
            ErrorCategory::InvalidTensor,
            "non_finite_tensor",
            "output projection f32 values must be finite and bounded",
        ));
    }
    Ok(())
}

#[derive(Debug, Clone)]
pub struct Qwen3MoeAttentionGreedyRuntime {
    fixture: Qwen3MoeAttentionGreedyFixture,
    attention: super::qwen3moe_attention::Qwen3MoeAttentionRuntime,
    next_step: usize,
    evidence: Vec<Qwen3MoeAttentionGreedyStepEvidence>,
    cancel_after_logits: Option<u32>,
}

impl Qwen3MoeAttentionGreedyRuntime {
    pub fn new(fixture: Qwen3MoeAttentionGreedyFixture) -> Result<Self, ContractError> {
        validate_qwen3moe_attention_greedy_fixture(&fixture)?;
        let attention =
            super::qwen3moe_attention::Qwen3MoeAttentionRuntime::try_new(&fixture.attention)?;
        Ok(Self {
            fixture,
            attention,
            next_step: 0,
            evidence: Vec::new(),
            cancel_after_logits: None,
        })
    }

    pub fn with_cancel_after_logits(mut self, step: Option<u32>) -> Self {
        self.cancel_after_logits = step;
        self
    }

    pub fn evidence(&self) -> &[Qwen3MoeAttentionGreedyStepEvidence] {
        &self.evidence
    }

    pub fn attention_position(&self) -> u64 {
        self.attention.position()
    }

    pub fn attention_cache_len(&self) -> usize {
        self.attention.cache_len()
    }

    fn compute_logits(&self, residual: &[f32]) -> Result<Vec<f32>, ContractError> {
        let projection = &self.fixture.output_projection.output_projection_weight;
        if residual.len() != self.fixture.attention.execution_dimensions.hidden_width {
            return Err(generation_error(
                ErrorCategory::InvalidTensor,
                "residual_shape_mismatch",
                "computed attention residual has an invalid output width",
            ));
        }
        let mut logits = Vec::with_capacity(projection.len());
        for row in projection {
            let score = row
                .iter()
                .zip(residual.iter())
                .map(|(weight, value)| weight * value)
                .sum::<f32>();
            if !score.is_finite() {
                return Err(generation_error(
                    ErrorCategory::InvalidTensor,
                    "logits_non_finite",
                    "the output projection produced a non-finite score",
                ));
            }
            logits.push(score);
        }
        Ok(logits)
    }
}

impl LogitsRuntime for Qwen3MoeAttentionGreedyRuntime {
    fn logits(&mut self, cancellation: &CancellationToken) -> Result<LogitsOutput, ContractError> {
        cancellation.check()?;
        let step_index = self.next_step;
        let input_step = self
            .fixture
            .attention
            .steps
            .get(step_index)
            .ok_or_else(|| {
                generation_error(
                    ErrorCategory::InvalidStateTransition,
                    "missing_logits_step",
                    "attention-to-greedy generation exceeded its bounded fixture steps",
                )
            })?;
        let mut staged_attention = self.attention.clone();
        let attention_evidence = staged_attention.process_step(
            &self.fixture.attention,
            step_index,
            input_step.position,
            &input_step.input,
            cancellation,
        )?;
        cancellation.check()?;
        let logits = self.compute_logits(&attention_evidence.residual)?;
        let topk = self
            .fixture
            .output_projection
            .output_token_ids
            .iter()
            .copied()
            .zip(logits.iter().copied())
            .collect::<Vec<_>>();
        let argmax = select_argmax(&topk)?;
        let expected = self.fixture.oracle.steps.get(step_index).ok_or_else(|| {
            generation_error(
                ErrorCategory::InvalidEvidence,
                "missing_oracle_step",
                "attention-to-greedy generation exceeded its bounded oracle steps",
            )
        })?;
        compare_step(
            &attention_evidence.residual,
            &logits,
            &topk,
            argmax,
            expected,
            self.fixture.oracle.tolerance,
        )?;
        if self.cancel_after_logits == Some((step_index + 1) as u32) {
            cancellation.cancel();
        }
        cancellation.check()?;

        self.attention = staged_attention;
        self.next_step = self.next_step.checked_add(1).ok_or_else(|| {
            generation_error(
                ErrorCategory::ArithmeticOverflow,
                "step_index_overflow",
                "attention-to-greedy step index overflowed",
            )
        })?;
        self.evidence.push(Qwen3MoeAttentionGreedyStepEvidence {
            step: (step_index + 1) as u32,
            position: input_step.position,
            residual: attention_evidence.residual,
            logits,
            topk: topk.clone(),
            argmax,
        });
        Ok(LogitsOutput { topk, argmax })
    }
}

/// Execute the fixture through the existing backend-owned greedy loop.
pub fn run_qwen3moe_attention_greedy_generation(
    fixture: &Qwen3MoeAttentionGreedyFixture,
    request: &GenerationRequest,
    cancellation: &CancellationToken,
) -> Result<Qwen3MoeAttentionGreedyGenerationResult, ContractError> {
    run_qwen3moe_attention_greedy_generation_with_cancel_after_logits(
        fixture,
        request,
        cancellation,
        None,
    )
}

pub fn run_qwen3moe_attention_greedy_generation_with_cancel_after_logits(
    fixture: &Qwen3MoeAttentionGreedyFixture,
    request: &GenerationRequest,
    cancellation: &CancellationToken,
    cancel_after_logits: Option<u32>,
) -> Result<Qwen3MoeAttentionGreedyGenerationResult, ContractError> {
    validate_qwen3moe_attention_greedy_fixture(fixture)?;
    if request.prompt_token_ids() != fixture.prompt_token_ids
        || request.eos_token_id() != Some(fixture.eos_token_id)
        || request.max_new_tokens() > fixture.max_new_tokens
    {
        return Err(generation_error(
            ErrorCategory::InvalidSelection,
            "request_fixture_mismatch",
            "generation request does not match the bounded attention-to-greedy fixture",
        ));
    }
    if cancel_after_logits == Some(0)
        || cancel_after_logits.is_some_and(|step| step > request.max_new_tokens())
    {
        return Err(generation_error(
            ErrorCategory::InvalidSelection,
            "invalid_cancellation_step",
            "cancellation step is outside the bounded request",
        ));
    }
    let mut runtime = Qwen3MoeAttentionGreedyRuntime::new(fixture.clone())?
        .with_cancel_after_logits(cancel_after_logits);
    let generation = generate_greedy(&mut runtime, request, cancellation)?;
    compare_generation_with_oracle(fixture, request, &generation)?;
    Ok(Qwen3MoeAttentionGreedyGenerationResult {
        fixture_id: fixture.fixture_id.clone(),
        contract_id: fixture.contract_id.clone(),
        generation,
        steps: runtime.evidence,
        evaluated: true,
        fallback_used: false,
    })
}

fn compare_step(
    residual: &[f32],
    logits: &[f32],
    topk: &[(u32, f32)],
    argmax: u32,
    expected: &Qwen3MoeAttentionGreedyOracleStep,
    tolerance: f32,
) -> Result<(), ContractError> {
    let residual_match = close_slice(residual, &expected.residual, tolerance);
    let logits_match = close_slice(logits, &expected.logits, tolerance);
    let topk_match = topk.len() == expected.topk.len()
        && topk
            .iter()
            .zip(expected.topk.iter())
            .all(|((actual_token, actual_score), expected)| {
                *actual_token == expected.token_id
                    && close(*actual_score, expected.score, tolerance)
            });
    if !residual_match || !logits_match || !topk_match || argmax != expected.argmax {
        return Err(generation_error(
            ErrorCategory::InvalidEvidence,
            "oracle_mismatch",
            "computed attention residual or logits differ from the independent oracle",
        ));
    }
    Ok(())
}

fn compare_generation_with_oracle(
    fixture: &Qwen3MoeAttentionGreedyFixture,
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
        return Err(generation_error(
            ErrorCategory::InvalidEvidence,
            "generation_oracle_mismatch",
            "greedy generation differs from the independent token oracle",
        ));
    }
    Ok(())
}

fn select_argmax(topk: &[(u32, f32)]) -> Result<u32, ContractError> {
    if topk.is_empty() || topk.len() > MAX_TOPK {
        return Err(generation_error(
            ErrorCategory::InvalidTensor,
            "invalid_logits_candidates",
            "output logits candidates are empty or exceed the bounded limit",
        ));
    }
    let mut seen = BTreeSet::new();
    let mut selected = None;
    for &(token_id, score) in topk {
        if !score.is_finite() {
            return Err(generation_error(
                ErrorCategory::InvalidTensor,
                "non_finite_logits",
                "output logits candidates must be finite",
            ));
        }
        if !seen.insert(token_id) {
            return Err(generation_error(
                ErrorCategory::InvalidTensor,
                "duplicate_logits_token",
                "output logits candidates must have unique token IDs",
            ));
        }
        if selected.is_none_or(|(best_token, best_score)| {
            score > best_score || (score == best_score && token_id < best_token)
        }) {
            selected = Some((token_id, score));
        }
    }
    Ok(selected
        .expect("non-empty logits candidates were checked")
        .0)
}

fn close_slice(actual: &[f32], expected: &[f32], tolerance: f32) -> bool {
    actual.len() == expected.len()
        && actual
            .iter()
            .zip(expected.iter())
            .all(|(actual, expected)| close(*actual, *expected, tolerance))
}

fn close(actual: f32, expected: f32, tolerance: f32) -> bool {
    actual.is_finite() && expected.is_finite() && (actual - expected).abs() <= tolerance
}

fn finite_slice(values: &[f32]) -> bool {
    values.iter().all(|value| value.is_finite())
}

fn generation_error(
    category: ErrorCategory,
    code: &'static str,
    message: &'static str,
) -> ContractError {
    ContractError::new(category, code, message)
}
