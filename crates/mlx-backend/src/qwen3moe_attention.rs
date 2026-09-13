//! Bounded, model-free Qwen3MoE attention and transactional KV reference seam.
//!
//! This module is deliberately scalar and pure Rust. It consumes one strict
//! f32 fixture, performs one attention block, and keeps KV state in memory. It
//! never opens a path, reads a payload, invokes MLX/Metal, or falls back to
//! fixture-fed outputs.

use backend::{CancellationToken, ContractError, ErrorCategory};
use serde::Deserialize;

pub const QWEN3MOE_ATTENTION_KV_FIXTURE_SCHEMA: &str = "pulsarmlx.fixture.qwen3moe-attention-kv-v1";
pub const QWEN3MOE_ATTENTION_KV_FIXTURE_ID: &str = "qwen3moe-attention-kv-v1";
pub const QWEN3MOE_ATTENTION_KV_CONTRACT_ID: &str = "qwen3moe-attention-kv-v1";
pub const QWEN3MOE_ATTENTION_KV_OPERATION_COUNT: usize = 12;
pub const QWEN3MOE_ATTENTION_KV_MAX_ELEMENTS: usize = 65_536;

const MAX_FIXTURE_BYTES: usize = 1 << 20;
const MAX_STEPS: usize = 16;
const MAX_HIDDEN_WIDTH: usize = 16;
const MAX_QUERY_HEADS: usize = 4;
const MAX_KV_HEADS: usize = 4;
const MAX_HEAD_DIMENSION: usize = 8;
const OPERATION_ORDER: [&str; QWEN3MOE_ATTENTION_KV_OPERATION_COUNT] = [
    "input_rms_norm",
    "query_projection",
    "key_projection",
    "value_projection",
    "query_rms_norm",
    "key_rms_norm",
    "neox_rotary_embedding",
    "transactional_kv_append",
    "grouped_query_attention",
    "causal_softmax",
    "attention_output_projection",
    "attention_residual_add",
];
const EXCLUSIONS: [&str; 7] = [
    "checkpoint payload bytes",
    "external path/FD reads",
    "MLX or Metal execution",
    "full 48-layer forward",
    "tokenizer, logits, or generation",
    "serving or benchmark",
    "qualification or production readiness",
];

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Qwen3MoeAttentionKvFixture {
    pub schema: String,
    pub schema_version: u32,
    pub fixture_id: String,
    pub fixture_kind: String,
    pub evidence_level: String,
    pub model_free: bool,
    pub uses_checkpoint_payload_bytes: bool,
    pub contract_id: String,
    pub architecture: String,
    pub target_dimensions: Qwen3MoeAttentionTargetDimensions,
    pub execution_dimensions: Qwen3MoeAttentionExecutionDimensions,
    pub operation_order: Vec<String>,
    pub tensors: Qwen3MoeAttentionTensors,
    pub steps: Vec<Qwen3MoeAttentionInputStep>,
    pub oracle: Qwen3MoeAttentionOracle,
    pub exclusions: Vec<String>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Qwen3MoeAttentionTargetDimensions {
    pub hidden_width: u64,
    pub query_heads: u64,
    pub kv_heads: u64,
    pub head_dimension: u64,
    pub layers: u64,
    pub rope: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Qwen3MoeAttentionExecutionDimensions {
    pub hidden_width: usize,
    pub query_heads: usize,
    pub kv_heads: usize,
    pub head_dimension: usize,
    pub max_sequence_length: usize,
    pub dtype: String,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Qwen3MoeAttentionTensors {
    pub input_norm_weight: Vec<f32>,
    pub input_norm_epsilon: f32,
    pub query_weight: Vec<Vec<f32>>,
    pub key_weight: Vec<Vec<f32>>,
    pub value_weight: Vec<Vec<f32>>,
    pub query_norm_weight: Vec<f32>,
    pub key_norm_weight: Vec<f32>,
    pub rope_theta: f32,
    pub attention_output_weight: Vec<Vec<f32>>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Qwen3MoeAttentionInputStep {
    pub position: u64,
    pub input: Vec<f32>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Qwen3MoeAttentionOracle {
    pub independently_generated: bool,
    pub generator: String,
    pub tolerance: f32,
    pub steps: Vec<Qwen3MoeAttentionOracleStep>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Qwen3MoeAttentionOracleStep {
    pub position: u64,
    pub normalized_input: Vec<f32>,
    pub query_projected: Vec<f32>,
    pub key_projected: Vec<f32>,
    pub value_projected: Vec<f32>,
    pub query_normalized: Vec<f32>,
    pub key_normalized: Vec<f32>,
    pub query_rotated: Vec<f32>,
    pub key_rotated: Vec<f32>,
    pub attention_scores: Vec<Vec<f32>>,
    pub attention_probabilities: Vec<Vec<f32>>,
    pub attention_output: Vec<f32>,
    pub projected_output: Vec<f32>,
    pub residual: Vec<f32>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Qwen3MoeAttentionStepEvidence {
    pub step: u32,
    pub position: u64,
    pub normalized_input: Vec<f32>,
    pub query_projected: Vec<f32>,
    pub key_projected: Vec<f32>,
    pub value_projected: Vec<f32>,
    pub query_normalized: Vec<f32>,
    pub key_normalized: Vec<f32>,
    pub query_rotated: Vec<f32>,
    pub key_rotated: Vec<f32>,
    pub attention_scores: Vec<Vec<f32>>,
    pub attention_probabilities: Vec<Vec<f32>>,
    pub attention_output: Vec<f32>,
    pub projected_output: Vec<f32>,
    pub residual: Vec<f32>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Qwen3MoeKvCacheSnapshot {
    pub positions: Vec<u64>,
    pub keys: Vec<Vec<f32>>,
    pub values: Vec<Vec<f32>>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Qwen3MoeAttentionKvResult {
    pub fixture_id: String,
    pub contract_id: String,
    pub steps: Vec<Qwen3MoeAttentionStepEvidence>,
    pub cache: Qwen3MoeKvCacheSnapshot,
    pub evaluated: bool,
    pub fallback_used: bool,
}

#[derive(Debug, Clone, Default, PartialEq)]
struct Qwen3MoeKvCache {
    positions: Vec<u64>,
    keys: Vec<Vec<f32>>,
    values: Vec<Vec<f32>>,
}

impl Qwen3MoeKvCache {
    fn snapshot(&self) -> Qwen3MoeKvCacheSnapshot {
        Qwen3MoeKvCacheSnapshot {
            positions: self.positions.clone(),
            keys: self.keys.clone(),
            values: self.values.clone(),
        }
    }
}

#[derive(Debug, Clone)]
pub struct Qwen3MoeAttentionRuntime {
    dimensions: Qwen3MoeAttentionExecutionDimensions,
    cache: Qwen3MoeKvCache,
}

/// Parse and validate a strict, bounded JSON attention fixture.
pub fn parse_qwen3moe_attention_kv_fixture(
    bytes: &[u8],
) -> Result<Qwen3MoeAttentionKvFixture, ContractError> {
    if bytes.is_empty() || bytes.len() > MAX_FIXTURE_BYTES {
        return Err(attention_error(
            ErrorCategory::ResourceLimit,
            "fixture_byte_limit",
            "the Qwen attention fixture exceeds its bounded byte limit",
        ));
    }
    let fixture: Qwen3MoeAttentionKvFixture = serde_json::from_slice(bytes).map_err(|_| {
        attention_error(
            ErrorCategory::InvalidTensor,
            "fixture_parse_error",
            "the Qwen attention fixture is not strict bounded JSON",
        )
    })?;
    validate_qwen3moe_attention_kv_fixture(&fixture)?;
    Ok(fixture)
}

/// Validate identity, shapes, finite values, operation order, and oracle
/// structure before any reference arithmetic is performed.
pub fn validate_qwen3moe_attention_kv_fixture(
    fixture: &Qwen3MoeAttentionKvFixture,
) -> Result<(), ContractError> {
    if fixture.schema != QWEN3MOE_ATTENTION_KV_FIXTURE_SCHEMA
        || fixture.schema_version != 1
        || fixture.fixture_id != QWEN3MOE_ATTENTION_KV_FIXTURE_ID
        || fixture.fixture_kind != "qwen3moe_synthetic_attention_kv"
        || fixture.evidence_level != "synthetic_fixture_only"
        || !fixture.model_free
        || fixture.uses_checkpoint_payload_bytes
        || fixture.contract_id != QWEN3MOE_ATTENTION_KV_CONTRACT_ID
        || fixture.architecture != "qwen3moe"
    {
        return Err(attention_error(
            ErrorCategory::InvalidModel,
            "fixture_identity_mismatch",
            "the Qwen attention fixture identity or model-free boundary is not admitted",
        ));
    }
    if fixture.target_dimensions.hidden_width != 2_048
        || fixture.target_dimensions.query_heads != 32
        || fixture.target_dimensions.kv_heads != 4
        || fixture.target_dimensions.head_dimension != 128
        || fixture.target_dimensions.layers != 48
        || fixture.target_dimensions.rope != "neox"
    {
        return Err(attention_error(
            ErrorCategory::InvalidModel,
            "target_dimensions_mismatch",
            "target dimensions do not match the admitted Qwen3MoE attention semantics",
        ));
    }
    let dimensions = &fixture.execution_dimensions;
    if dimensions.hidden_width == 0
        || dimensions.hidden_width > MAX_HIDDEN_WIDTH
        || dimensions.query_heads == 0
        || dimensions.query_heads > MAX_QUERY_HEADS
        || dimensions.kv_heads == 0
        || dimensions.kv_heads > MAX_KV_HEADS
        || dimensions.head_dimension == 0
        || dimensions.head_dimension > MAX_HEAD_DIMENSION
        || dimensions.head_dimension % 2 != 0
        || dimensions.query_heads % dimensions.kv_heads != 0
        || dimensions.max_sequence_length == 0
        || dimensions.max_sequence_length > MAX_STEPS
        || dimensions.dtype != "f32"
    {
        return Err(attention_error(
            ErrorCategory::InvalidTensor,
            "execution_shape_mismatch",
            "the fixture execution shape is outside the bounded f32 attention seam",
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
        return Err(attention_error(
            ErrorCategory::InvalidModel,
            "fixture_contract_mismatch",
            "the Qwen attention operation or exclusion contract differs",
        ));
    }
    if fixture.steps.is_empty()
        || fixture.steps.len() > dimensions.max_sequence_length
        || fixture.steps.len() > MAX_STEPS
        || fixture.oracle.steps.len() != fixture.steps.len()
        || !fixture.oracle.independently_generated
        || fixture.oracle.generator != "standalone_f32_scalar_reference_v1"
        || !fixture.oracle.tolerance.is_finite()
        || fixture.oracle.tolerance <= 0.0
        || fixture.oracle.tolerance > 1.0e-2
    {
        return Err(attention_error(
            ErrorCategory::InvalidEvidence,
            "fixture_oracle_bounds",
            "the attention fixture oracle is missing, unbounded, or not independent",
        ));
    }
    validate_tensors(&fixture.tensors, dimensions)?;
    for (index, (step, oracle)) in fixture.steps.iter().zip(&fixture.oracle.steps).enumerate() {
        if step.position != index as u64
            || oracle.position != step.position
            || step.input.len() != dimensions.hidden_width
            || !step.input.iter().all(|value| value.is_finite())
        {
            return Err(attention_error(
                ErrorCategory::InvalidTensor,
                "input_step_mismatch",
                "attention input positions, shape, or finite-value rules are invalid",
            ));
        }
        validate_oracle_step(oracle, dimensions, index + 1, fixture.oracle.tolerance)?;
    }
    Ok(())
}

impl Qwen3MoeAttentionRuntime {
    /// Create an empty runtime after validating the complete fixture contract.
    pub fn try_new(fixture: &Qwen3MoeAttentionKvFixture) -> Result<Self, ContractError> {
        validate_qwen3moe_attention_kv_fixture(fixture)?;
        Ok(Self {
            dimensions: fixture.execution_dimensions.clone(),
            cache: Qwen3MoeKvCache::default(),
        })
    }

    pub fn position(&self) -> u64 {
        self.cache.positions.len() as u64
    }

    pub fn cache_len(&self) -> usize {
        self.cache.positions.len()
    }

    pub fn cache_snapshot(&self) -> Qwen3MoeKvCacheSnapshot {
        self.cache.snapshot()
    }

    /// Drop every cached key/value and return to position zero.
    pub fn reset(&mut self) {
        self.cache = Qwen3MoeKvCache::default();
    }

    /// Execute all fixture steps as one transaction. The runtime cache is
    /// published only after every step and oracle comparison succeeds.
    pub fn run_fixture(
        &mut self,
        fixture: &Qwen3MoeAttentionKvFixture,
        cancellation: &CancellationToken,
    ) -> Result<Qwen3MoeAttentionKvResult, ContractError> {
        self.run_fixture_internal(fixture, cancellation, None)
    }

    /// Deterministic cancellation hook used to prove that a cancelled batch
    /// does not publish an earlier staged KV prefix.
    pub fn run_fixture_with_cancel_after_step(
        &mut self,
        fixture: &Qwen3MoeAttentionKvFixture,
        cancellation: &CancellationToken,
        cancel_before_step: Option<usize>,
    ) -> Result<Qwen3MoeAttentionKvResult, ContractError> {
        self.run_fixture_internal(fixture, cancellation, cancel_before_step)
    }

    /// Evaluate one explicitly positioned step and publish its KV entry only
    /// after the operation and oracle checks complete.
    pub fn process_step(
        &mut self,
        fixture: &Qwen3MoeAttentionKvFixture,
        step_index: usize,
        position: u64,
        input: &[f32],
        cancellation: &CancellationToken,
    ) -> Result<Qwen3MoeAttentionStepEvidence, ContractError> {
        self.validate_runtime_fixture(fixture)?;
        let expected = fixture.steps.get(step_index).ok_or_else(|| {
            attention_error(
                ErrorCategory::InvalidSelection,
                "step_not_admitted",
                "the requested attention fixture step is not admitted",
            )
        })?;
        if expected.position != position || expected.input != input {
            return Err(attention_error(
                ErrorCategory::InvalidTensor,
                "input_step_mismatch",
                "the supplied attention step does not match its admitted fixture",
            ));
        }
        let (evidence, staged) = evaluate_step(
            &self.cache,
            &self.dimensions,
            &fixture.tensors,
            position,
            input,
            cancellation,
        )?;
        compare_step(
            &evidence,
            &fixture.oracle.steps[step_index],
            fixture.oracle.tolerance,
        )?;
        self.cache = staged;
        Ok(evidence)
    }

    fn run_fixture_internal(
        &mut self,
        fixture: &Qwen3MoeAttentionKvFixture,
        cancellation: &CancellationToken,
        cancel_before_step: Option<usize>,
    ) -> Result<Qwen3MoeAttentionKvResult, ContractError> {
        self.validate_runtime_fixture(fixture)?;
        let mut staged_cache = self.cache.clone();
        let mut evidence = Vec::with_capacity(fixture.steps.len());
        for (index, (step, oracle)) in fixture.steps.iter().zip(&fixture.oracle.steps).enumerate() {
            cancellation.check()?;
            if cancel_before_step == Some(index) {
                cancellation.cancel();
                cancellation.check()?;
            }
            let (actual, next_cache) = evaluate_step(
                &staged_cache,
                &self.dimensions,
                &fixture.tensors,
                step.position,
                &step.input,
                cancellation,
            )?;
            compare_step(&actual, oracle, fixture.oracle.tolerance)?;
            staged_cache = next_cache;
            evidence.push(actual);
        }
        cancellation.check()?;
        self.cache = staged_cache;
        Ok(Qwen3MoeAttentionKvResult {
            fixture_id: fixture.fixture_id.clone(),
            contract_id: fixture.contract_id.clone(),
            steps: evidence,
            cache: self.cache.snapshot(),
            evaluated: true,
            fallback_used: false,
        })
    }

    fn validate_runtime_fixture(
        &self,
        fixture: &Qwen3MoeAttentionKvFixture,
    ) -> Result<(), ContractError> {
        validate_qwen3moe_attention_kv_fixture(fixture)?;
        if self.dimensions != fixture.execution_dimensions {
            return Err(attention_error(
                ErrorCategory::InvalidStateTransition,
                "runtime_shape_mismatch",
                "the fixture shape differs from the initialized attention runtime",
            ));
        }
        if self.cache.positions.len() > self.dimensions.max_sequence_length {
            return Err(attention_error(
                ErrorCategory::ResourceLimit,
                "cache_bound_exceeded",
                "the attention KV cache exceeds its bounded sequence length",
            ));
        }
        Ok(())
    }
}

/// Execute a fresh empty runtime against the bounded fixture.
pub fn run_qwen3moe_attention_kv(
    fixture: &Qwen3MoeAttentionKvFixture,
    cancellation: &CancellationToken,
) -> Result<Qwen3MoeAttentionKvResult, ContractError> {
    Qwen3MoeAttentionRuntime::try_new(fixture)?.run_fixture(fixture, cancellation)
}

fn evaluate_step(
    cache: &Qwen3MoeKvCache,
    dimensions: &Qwen3MoeAttentionExecutionDimensions,
    tensors: &Qwen3MoeAttentionTensors,
    position: u64,
    input: &[f32],
    cancellation: &CancellationToken,
) -> Result<(Qwen3MoeAttentionStepEvidence, Qwen3MoeKvCache), ContractError> {
    cancellation.check()?;
    if position != cache.positions.len() as u64 {
        return Err(attention_error(
            ErrorCategory::InvalidStateTransition,
            "position_mismatch",
            "attention positions must append contiguously to the KV cache",
        ));
    }
    if cache.positions.len() >= dimensions.max_sequence_length {
        return Err(attention_error(
            ErrorCategory::ResourceLimit,
            "cache_capacity_exceeded",
            "the attention KV cache reached its bounded sequence capacity",
        ));
    }
    if input.len() != dimensions.hidden_width || !input.iter().all(|value| value.is_finite()) {
        return Err(attention_error(
            ErrorCategory::InvalidTensor,
            "input_shape_or_finite_mismatch",
            "attention input shape or finite-value policy was violated",
        ));
    }
    let normalized_input = rms_norm(
        input,
        &tensors.input_norm_weight,
        tensors.input_norm_epsilon,
    )?;
    cancellation.check()?;
    let query_projected = project(&tensors.query_weight, &normalized_input)?;
    let key_projected = project(&tensors.key_weight, &normalized_input)?;
    let value_projected = project(&tensors.value_weight, &normalized_input)?;
    cancellation.check()?;
    let query_normalized = per_head_rms_norm(
        &query_projected,
        &tensors.query_norm_weight,
        dimensions.query_heads,
        dimensions.head_dimension,
    )?;
    let key_normalized = per_head_rms_norm(
        &key_projected,
        &tensors.key_norm_weight,
        dimensions.kv_heads,
        dimensions.head_dimension,
    )?;
    let query_rotated = neox_rope(
        &query_normalized,
        position,
        dimensions.query_heads,
        dimensions.head_dimension,
        tensors.rope_theta,
    )?;
    let key_rotated = neox_rope(
        &key_normalized,
        position,
        dimensions.kv_heads,
        dimensions.head_dimension,
        tensors.rope_theta,
    )?;
    cancellation.check()?;

    let mut staged_cache = cache.clone();
    staged_cache.positions.push(position);
    staged_cache.keys.push(key_rotated.clone());
    staged_cache.values.push(value_projected.clone());
    cancellation.check()?;

    let (attention_scores, attention_probabilities, attention_output) = grouped_attention(
        &query_rotated,
        &staged_cache,
        dimensions.query_heads,
        dimensions.kv_heads,
        dimensions.head_dimension,
    )?;
    cancellation.check()?;
    let projected_output = project(&tensors.attention_output_weight, &attention_output)?;
    let residual = add(input, &projected_output)?;
    cancellation.check()?;
    Ok((
        Qwen3MoeAttentionStepEvidence {
            step: position as u32,
            position,
            normalized_input,
            query_projected,
            key_projected,
            value_projected,
            query_normalized,
            key_normalized,
            query_rotated,
            key_rotated,
            attention_scores,
            attention_probabilities,
            attention_output,
            projected_output,
            residual,
        },
        staged_cache,
    ))
}

fn rms_norm(input: &[f32], weight: &[f32], epsilon: f32) -> Result<Vec<f32>, ContractError> {
    let mean_square = input.iter().map(|value| value * value).sum::<f32>() / input.len() as f32;
    let scale = (mean_square + epsilon).sqrt();
    if !scale.is_finite() || scale <= 0.0 {
        return Err(attention_error(
            ErrorCategory::InvalidTensor,
            "rms_norm_non_finite",
            "RMSNorm produced a non-finite scale",
        ));
    }
    let output: Vec<f32> = input
        .iter()
        .zip(weight)
        .map(|(value, factor)| value / scale * factor)
        .collect();
    finite_vector(&output, "rms_norm_non_finite")?;
    Ok(output)
}

fn project(weight: &[Vec<f32>], input: &[f32]) -> Result<Vec<f32>, ContractError> {
    if weight.iter().any(|row| row.len() != input.len()) {
        return Err(attention_error(
            ErrorCategory::InvalidTensor,
            "tensor_shape_mismatch",
            "attention projection rows must match the input width",
        ));
    }
    let mut output = Vec::with_capacity(weight.len());
    for row in weight {
        let value = row
            .iter()
            .zip(input)
            .map(|(left, right)| left * right)
            .sum::<f32>();
        if !value.is_finite() {
            return Err(attention_error(
                ErrorCategory::InvalidTensor,
                "projection_non_finite",
                "attention projection produced a non-finite value",
            ));
        }
        output.push(value);
    }
    Ok(output)
}

fn per_head_rms_norm(
    input: &[f32],
    weight: &[f32],
    heads: usize,
    head_dimension: usize,
) -> Result<Vec<f32>, ContractError> {
    let mut output = Vec::with_capacity(input.len());
    for head in 0..heads {
        let start = head * head_dimension;
        let values = &input[start..start + head_dimension];
        let mean_square =
            values.iter().map(|value| value * value).sum::<f32>() / head_dimension as f32;
        let scale = (mean_square + 1.0e-5).sqrt();
        if !scale.is_finite() || scale <= 0.0 {
            return Err(attention_error(
                ErrorCategory::InvalidTensor,
                "head_norm_non_finite",
                "per-head RMSNorm produced a non-finite scale",
            ));
        }
        output.extend(
            values
                .iter()
                .zip(weight)
                .map(|(value, factor)| value / scale * factor),
        );
    }
    finite_vector(&output, "head_norm_non_finite")?;
    Ok(output)
}

fn neox_rope(
    input: &[f32],
    position: u64,
    heads: usize,
    head_dimension: usize,
    theta: f32,
) -> Result<Vec<f32>, ContractError> {
    let half = head_dimension / 2;
    let mut output = input.to_vec();
    for head in 0..heads {
        let start = head * head_dimension;
        for pair in 0..half {
            let frequency = theta.powf(-((2 * pair) as f32) / head_dimension as f32);
            let angle = position as f32 * frequency;
            let cosine = angle.cos();
            let sine = angle.sin();
            let first = input[start + pair];
            let second = input[start + half + pair];
            output[start + pair] = first * cosine - second * sine;
            output[start + half + pair] = first * sine + second * cosine;
        }
    }
    finite_vector(&output, "rope_non_finite")?;
    Ok(output)
}

fn grouped_attention(
    query: &[f32],
    cache: &Qwen3MoeKvCache,
    query_heads: usize,
    kv_heads: usize,
    head_dimension: usize,
) -> Result<(Vec<Vec<f32>>, Vec<Vec<f32>>, Vec<f32>), ContractError> {
    let group_size = query_heads / kv_heads;
    let scale = 1.0 / (head_dimension as f32).sqrt();
    let mut all_scores = Vec::with_capacity(query_heads);
    let mut all_probabilities = Vec::with_capacity(query_heads);
    let mut output = vec![0.0; query_heads * head_dimension];
    for query_head in 0..query_heads {
        let kv_head = query_head / group_size;
        let query_start = query_head * head_dimension;
        let mut scores = Vec::with_capacity(cache.keys.len());
        for key in &cache.keys {
            let key_start = kv_head * head_dimension;
            let score = query[query_start..query_start + head_dimension]
                .iter()
                .zip(&key[key_start..key_start + head_dimension])
                .map(|(left, right)| left * right)
                .sum::<f32>()
                * scale;
            if !score.is_finite() {
                return Err(attention_error(
                    ErrorCategory::InvalidTensor,
                    "attention_score_non_finite",
                    "attention score became non-finite",
                ));
            }
            scores.push(score);
        }
        let probabilities = causal_softmax(&scores)?;
        let output_start = query_start;
        for (time, probability) in probabilities.iter().enumerate() {
            let value_start = kv_head * head_dimension;
            for offset in 0..head_dimension {
                output[output_start + offset] +=
                    probability * cache.values[time][value_start + offset];
            }
        }
        all_scores.push(scores);
        all_probabilities.push(probabilities);
    }
    finite_vector(&output, "attention_output_non_finite")?;
    Ok((all_scores, all_probabilities, output))
}

fn causal_softmax(scores: &[f32]) -> Result<Vec<f32>, ContractError> {
    let maximum = scores.iter().copied().fold(f32::NEG_INFINITY, f32::max);
    let exponentials: Vec<f32> = scores
        .iter()
        .map(|score| (*score - maximum).exp())
        .collect();
    let total = exponentials.iter().sum::<f32>();
    if !total.is_finite() || total <= 0.0 {
        return Err(attention_error(
            ErrorCategory::InvalidTensor,
            "softmax_non_finite",
            "causal softmax produced a non-finite normalization",
        ));
    }
    let probabilities: Vec<f32> = exponentials.iter().map(|value| value / total).collect();
    finite_vector(&probabilities, "softmax_non_finite")?;
    Ok(probabilities)
}

fn add(left: &[f32], right: &[f32]) -> Result<Vec<f32>, ContractError> {
    let output: Vec<f32> = left
        .iter()
        .zip(right)
        .map(|(left, right)| left + right)
        .collect();
    finite_vector(&output, "residual_non_finite")?;
    Ok(output)
}

fn compare_step(
    actual: &Qwen3MoeAttentionStepEvidence,
    expected: &Qwen3MoeAttentionOracleStep,
    tolerance: f32,
) -> Result<(), ContractError> {
    if actual.position != expected.position
        || !compare_vector(
            &actual.normalized_input,
            &expected.normalized_input,
            tolerance,
        )
        || !compare_vector(
            &actual.query_projected,
            &expected.query_projected,
            tolerance,
        )
        || !compare_vector(&actual.key_projected, &expected.key_projected, tolerance)
        || !compare_vector(
            &actual.value_projected,
            &expected.value_projected,
            tolerance,
        )
        || !compare_vector(
            &actual.query_normalized,
            &expected.query_normalized,
            tolerance,
        )
        || !compare_vector(&actual.key_normalized, &expected.key_normalized, tolerance)
        || !compare_vector(&actual.query_rotated, &expected.query_rotated, tolerance)
        || !compare_vector(&actual.key_rotated, &expected.key_rotated, tolerance)
        || !compare_matrix(
            &actual.attention_scores,
            &expected.attention_scores,
            tolerance,
        )
        || !compare_matrix(
            &actual.attention_probabilities,
            &expected.attention_probabilities,
            tolerance,
        )
        || !compare_vector(
            &actual.attention_output,
            &expected.attention_output,
            tolerance,
        )
        || !compare_vector(
            &actual.projected_output,
            &expected.projected_output,
            tolerance,
        )
        || !compare_vector(&actual.residual, &expected.residual, tolerance)
    {
        return Err(attention_error(
            ErrorCategory::InvalidComparison,
            "oracle_mismatch",
            "computed attention output differs from the independent oracle",
        ));
    }
    Ok(())
}

fn compare_matrix(actual: &[Vec<f32>], expected: &[Vec<f32>], tolerance: f32) -> bool {
    actual.len() == expected.len()
        && actual
            .iter()
            .zip(expected)
            .all(|(actual, expected)| compare_vector(actual, expected, tolerance))
}

fn compare_vector(actual: &[f32], expected: &[f32], tolerance: f32) -> bool {
    actual.len() == expected.len()
        && actual.iter().zip(expected).all(|(actual, expected)| {
            actual.is_finite() && expected.is_finite() && (actual - expected).abs() <= tolerance
        })
}

fn validate_tensors(
    tensors: &Qwen3MoeAttentionTensors,
    dimensions: &Qwen3MoeAttentionExecutionDimensions,
) -> Result<(), ContractError> {
    if !tensors.input_norm_epsilon.is_finite()
        || tensors.input_norm_epsilon <= 0.0
        || !tensors.rope_theta.is_finite()
        || tensors.rope_theta <= 1.0
        || tensors.input_norm_weight.len() != dimensions.hidden_width
        || tensors.query_norm_weight.len() != dimensions.head_dimension
        || tensors.key_norm_weight.len() != dimensions.head_dimension
        || tensors.query_weight.len() != dimensions.query_heads * dimensions.head_dimension
        || tensors
            .query_weight
            .iter()
            .any(|row| row.len() != dimensions.hidden_width)
        || tensors.key_weight.len() != dimensions.kv_heads * dimensions.head_dimension
        || tensors
            .key_weight
            .iter()
            .any(|row| row.len() != dimensions.hidden_width)
        || tensors.value_weight.len() != dimensions.kv_heads * dimensions.head_dimension
        || tensors
            .value_weight
            .iter()
            .any(|row| row.len() != dimensions.hidden_width)
        || tensors.attention_output_weight.len() != dimensions.hidden_width
        || tensors
            .attention_output_weight
            .iter()
            .any(|row| row.len() != dimensions.query_heads * dimensions.head_dimension)
    {
        return Err(attention_error(
            ErrorCategory::InvalidTensor,
            "tensor_shape_mismatch",
            "attention tensor shapes do not match the bounded execution dimensions",
        ));
    }
    let mut elements = tensors.input_norm_weight.len()
        + tensors.query_norm_weight.len()
        + tensors.key_norm_weight.len();
    for matrix in [
        &tensors.query_weight,
        &tensors.key_weight,
        &tensors.value_weight,
        &tensors.attention_output_weight,
    ] {
        for row in matrix {
            elements = elements.checked_add(row.len()).ok_or_else(|| {
                attention_error(
                    ErrorCategory::ArithmeticOverflow,
                    "tensor_element_overflow",
                    "attention tensor element count overflowed",
                )
            })?;
        }
    }
    if elements > QWEN3MOE_ATTENTION_KV_MAX_ELEMENTS
        || !tensors
            .input_norm_weight
            .iter()
            .all(|value| value.is_finite())
        || !tensors
            .query_norm_weight
            .iter()
            .all(|value| value.is_finite())
        || !tensors
            .key_norm_weight
            .iter()
            .all(|value| value.is_finite())
        || !matrices_finite(&tensors.query_weight)
        || !matrices_finite(&tensors.key_weight)
        || !matrices_finite(&tensors.value_weight)
        || !matrices_finite(&tensors.attention_output_weight)
    {
        return Err(attention_error(
            ErrorCategory::InvalidTensor,
            "tensor_values_invalid",
            "attention tensors are non-finite or exceed the bounded element limit",
        ));
    }
    Ok(())
}

fn validate_oracle_step(
    oracle: &Qwen3MoeAttentionOracleStep,
    dimensions: &Qwen3MoeAttentionExecutionDimensions,
    sequence_length: usize,
    tolerance: f32,
) -> Result<(), ContractError> {
    let query_width = dimensions.query_heads * dimensions.head_dimension;
    let kv_width = dimensions.kv_heads * dimensions.head_dimension;
    let vector_shapes = [
        (&oracle.normalized_input, dimensions.hidden_width),
        (&oracle.query_projected, query_width),
        (&oracle.key_projected, kv_width),
        (&oracle.value_projected, kv_width),
        (&oracle.query_normalized, query_width),
        (&oracle.key_normalized, kv_width),
        (&oracle.query_rotated, query_width),
        (&oracle.key_rotated, kv_width),
        (&oracle.attention_output, query_width),
        (&oracle.projected_output, dimensions.hidden_width),
        (&oracle.residual, dimensions.hidden_width),
    ];
    if vector_shapes.iter().any(|(values, length)| {
        values.len() != *length || !values.iter().all(|value| value.is_finite())
    }) || oracle.attention_scores.len() != dimensions.query_heads
        || oracle.attention_probabilities.len() != dimensions.query_heads
        || oracle
            .attention_scores
            .iter()
            .any(|row| row.len() != sequence_length || !row.iter().all(|value| value.is_finite()))
        || oracle
            .attention_probabilities
            .iter()
            .any(|row| row.len() != sequence_length || !row.iter().all(|value| value.is_finite()))
        || !tolerance.is_finite()
    {
        return Err(attention_error(
            ErrorCategory::InvalidEvidence,
            "oracle_shape_mismatch",
            "attention oracle vectors or matrices have invalid bounded shapes",
        ));
    }
    Ok(())
}

fn matrices_finite(matrix: &[Vec<f32>]) -> bool {
    matrix
        .iter()
        .all(|row| row.iter().all(|value| value.is_finite()))
}

fn finite_vector(values: &[f32], code: &'static str) -> Result<(), ContractError> {
    if values.iter().all(|value| value.is_finite()) {
        Ok(())
    } else {
        Err(attention_error(
            ErrorCategory::InvalidTensor,
            code,
            "attention arithmetic produced a non-finite value",
        ))
    }
}

fn attention_error(
    category: ErrorCategory,
    code: &'static str,
    message: &'static str,
) -> ContractError {
    ContractError::new(category, code, message)
}
