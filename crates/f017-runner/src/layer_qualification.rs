//! Checkpoint-free Feature 017 MLA/DSA qualification boundary.
//!
//! The arithmetic helpers in this module are shared by the exact scaffold and
//! the production MLX candidate. Large projections are injected explicitly;
//! qualification mode supplies the strict-column-order matvec while production
//! mode supplies the fail-closed MLX matvec. CPU-side RMSNorm, RoPE, attention,
//! DSA selection, and residual ordering stay explicit and deterministic.

use crate::qualification::exact_swiglu_f32;
use crate::qualification::{exact_matvec_f32, QualificationError};

pub const R9_SCAFFOLD_VERSION: &str = "f017-r9-mla-dsa-exact-v1";

#[derive(Debug, Clone, PartialEq)]
pub struct R9Matrices {
    pub q_a: Vec<f32>,
    pub q_b: Vec<f32>,
    pub kv_a: Vec<f32>,
    pub k_b: Vec<f32>,
    pub v_b: Vec<f32>,
    pub output: Vec<f32>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct R9Inputs {
    pub residual: Vec<f32>,
    pub attn_norm_scale: Vec<f32>,
    pub q_norm_scale: Vec<f32>,
    pub kv_norm_scale: Vec<f32>,
    pub prior_cache_latents: Vec<f32>,
    pub prior_cache_ropes: Vec<f32>,
    pub q_rope_cosine: Vec<f32>,
    pub q_rope_sine: Vec<f32>,
    pub rms_epsilon: f32,
    pub attention_scale: f32,
    pub query_position: usize,
    pub visible_positions: usize,
}

#[derive(Debug, Clone, PartialEq)]
pub struct R9Output {
    pub x_norm: Vec<f32>,
    pub q_rank: Vec<f32>,
    pub q_rank_norm: Vec<f32>,
    pub q_flat: Vec<f32>,
    pub q_nope: Vec<f32>,
    pub q_rope: Vec<f32>,
    pub kv_raw: Vec<f32>,
    pub kv_norm: Vec<f32>,
    pub current_k_rope: Vec<f32>,
    pub qk_low: Vec<f32>,
    pub rotated_keys: Vec<f32>,
    pub attention_scores: Vec<f32>,
    pub attention_probabilities: Vec<f32>,
    pub latent_sum: Vec<f32>,
    pub value: Vec<f32>,
    pub projected: Vec<f32>,
    pub output: Vec<f32>,
    pub selected_positions: Vec<usize>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum R9Error {
    InvalidShape(&'static str),
    Matvec(QualificationError),
    CandidateMatvec(&'static str),
}

impl std::fmt::Display for R9Error {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::InvalidShape(field) => write!(formatter, "invalid R9 shape: {field}"),
            Self::Matvec(error) => write!(formatter, "R9 exact matvec failed: {error}"),
            Self::CandidateMatvec(role) => write!(formatter, "R9 candidate matvec failed: {role}"),
        }
    }
}

impl std::error::Error for R9Error {}

impl From<QualificationError> for R9Error {
    fn from(error: QualificationError) -> Self {
        Self::Matvec(error)
    }
}

pub fn run_r9_exact(matrices: &R9Matrices, inputs: &R9Inputs) -> Result<R9Output, R9Error> {
    run_r9_with_matvec(matrices, inputs, |matrix, rows, columns, vector, role| {
        let mut output = vec![0.0_f32; rows];
        exact_matvec_f32(matrix, rows, columns, vector, &mut output)
            .map_err(|_| R9Error::CandidateMatvec(role))?;
        Ok(output)
    })
}

pub fn run_r9_with_matvec<F>(
    matrices: &R9Matrices,
    inputs: &R9Inputs,
    mut matvec: F,
) -> Result<R9Output, R9Error>
where
    F: FnMut(&[f32], usize, usize, &[f32], &'static str) -> Result<Vec<f32>, R9Error>,
{
    let width = inputs.residual.len();
    if width == 0
        || inputs.attn_norm_scale.len() != width
        || inputs.q_norm_scale.len() != width
        || inputs.kv_norm_scale.len() != width
        || inputs.q_rope_cosine.len() * 2 != width
        || inputs.q_rope_sine.len() != inputs.q_rope_cosine.len()
        || inputs.query_position + 1 != inputs.visible_positions
        || inputs.visible_positions < 1
    {
        return Err(R9Error::InvalidShape("inputs"));
    }
    let prior_positions = inputs.visible_positions - 1;
    if inputs.prior_cache_latents.len() != prior_positions * width
        || inputs.prior_cache_ropes.len() != prior_positions * width
        || matrices.q_a.len() != width * width
        || matrices.q_b.len() != 2 * width * width
        || matrices.kv_a.len() != 2 * width * width
        || matrices.k_b.len() != width * width
        || matrices.v_b.len() != width * width
        || matrices.output.len() != width * width
    {
        return Err(R9Error::InvalidShape("matrices or cache"));
    }

    let x_norm = exact_rms_norm_f32(
        &inputs.residual,
        &inputs.attn_norm_scale,
        inputs.rms_epsilon,
    )?;
    let q_rank = matvec(&matrices.q_a, width, width, &x_norm, "attn_q_a")?;
    let q_rank_norm = exact_rms_norm_f32(&q_rank, &inputs.q_norm_scale, inputs.rms_epsilon)?;
    let q_flat = matvec(&matrices.q_b, 2 * width, width, &q_rank_norm, "attn_q_b")?;
    let q_nope = q_flat[..width].to_vec();
    let q_rope =
        exact_rope_pairs_f32(&q_flat[width..], &inputs.q_rope_cosine, &inputs.q_rope_sine)?;

    let kv_raw = matvec(&matrices.kv_a, 2 * width, width, &x_norm, "attn_kv_a_mqa")?;
    let kv_norm = exact_rms_norm_f32(&kv_raw[..width], &inputs.kv_norm_scale, inputs.rms_epsilon)?;
    let current_k_rope = kv_raw[width..].to_vec();
    let qk_low = matvec(&matrices.k_b, width, width, &q_nope, "attn_k_b")?;

    let selected_positions = dsa_range_fill(inputs.visible_positions, 2048);
    let mut cache_latents = inputs.prior_cache_latents.clone();
    cache_latents.extend_from_slice(&kv_norm);
    let mut cache_ropes = inputs.prior_cache_ropes.clone();
    cache_ropes.extend_from_slice(&current_k_rope);
    let mut rotated_keys = Vec::with_capacity(inputs.visible_positions * width);
    let mut attention_scores = Vec::with_capacity(inputs.visible_positions);
    for &position in &selected_positions {
        let (cosine, sine) = rope_constants_f32(position, width);
        let rotated = exact_rope_pairs_f32(
            &cache_ropes[position * width..(position + 1) * width],
            &cosine,
            &sine,
        )?;
        let latent_score = exact_dot_f32(
            &qk_low,
            &cache_latents[position * width..(position + 1) * width],
        )?;
        let rope_score = exact_dot_f32(&q_rope, &rotated)?;
        attention_scores.push(rounded_mul(
            rounded_add(latent_score, rope_score),
            inputs.attention_scale,
        ));
        rotated_keys.extend_from_slice(&rotated);
    }
    let attention_probabilities = exact_softmax_f32(&attention_scores)?;
    let mut latent_sum = vec![0.0_f32; width];
    for (&weight, &position) in attention_probabilities.iter().zip(&selected_positions) {
        for column in 0..width {
            latent_sum[column] = rounded_add(
                latent_sum[column],
                rounded_mul(weight, cache_latents[position * width + column]),
            );
        }
    }
    let value = matvec(&matrices.v_b, width, width, &latent_sum, "attn_v_b")?;
    let projected = matvec(&matrices.output, width, width, &value, "attn_output")?;
    let output = inputs
        .residual
        .iter()
        .zip(&projected)
        .map(|(&left, &right)| rounded_add(left, right))
        .collect();
    Ok(R9Output {
        x_norm,
        q_rank,
        q_rank_norm,
        q_flat,
        q_nope,
        q_rope,
        kv_raw,
        kv_norm,
        current_k_rope,
        qk_low,
        rotated_keys,
        attention_scores,
        attention_probabilities,
        latent_sum,
        value,
        projected,
        output,
        selected_positions,
    })
}

pub fn exact_rms_norm_f32(
    values: &[f32],
    scale: &[f32],
    epsilon: f32,
) -> Result<Vec<f32>, R9Error> {
    if values.is_empty() || values.len() != scale.len() || epsilon <= 0.0 {
        return Err(R9Error::InvalidShape("rms_norm"));
    }
    let mut total = 0.0_f32;
    for &value in values {
        total = rounded_add(total, rounded_mul(value, value));
    }
    let mean = rounded_div(total, values.len() as f32);
    let inverse = rounded_div(
        1.0,
        f32::from_bits(rounded_add(mean, epsilon).sqrt().to_bits()),
    );
    Ok(values
        .iter()
        .zip(scale)
        .map(|(&value, &weight)| rounded_mul(rounded_mul(value, inverse), weight))
        .collect())
}

pub fn exact_rope_pairs_f32(
    values: &[f32],
    cosine: &[f32],
    sine: &[f32],
) -> Result<Vec<f32>, R9Error> {
    if values.is_empty()
        || values.len() % 2 != 0
        || cosine.len() * 2 != values.len()
        || sine.len() != cosine.len()
    {
        return Err(R9Error::InvalidShape("rope"));
    }
    let mut output = values.to_vec();
    for pair in 0..cosine.len() {
        let left = values[2 * pair];
        let right = values[2 * pair + 1];
        output[2 * pair] = rounded_add(
            rounded_mul(left, cosine[pair]),
            -rounded_mul(right, sine[pair]),
        );
        output[2 * pair + 1] = rounded_add(
            rounded_mul(left, sine[pair]),
            rounded_mul(right, cosine[pair]),
        );
    }
    Ok(output)
}

pub fn exact_dot_f32(left: &[f32], right: &[f32]) -> Result<f32, R9Error> {
    if left.is_empty() || left.len() != right.len() {
        return Err(R9Error::InvalidShape("dot"));
    }
    let mut total = 0.0_f32;
    for (&left, &right) in left.iter().zip(right) {
        total = rounded_add(total, rounded_mul(left, right));
    }
    Ok(total)
}

pub fn exact_softmax_f32(values: &[f32]) -> Result<Vec<f32>, R9Error> {
    if values.is_empty() || values.iter().any(|value| !value.is_finite()) {
        return Err(R9Error::InvalidShape("softmax"));
    }
    let maximum = values.iter().copied().fold(f32::NEG_INFINITY, f32::max);
    let exponentials = values
        .iter()
        .map(|&value| f32::from_bits((value - maximum).exp().to_bits()))
        .collect::<Vec<_>>();
    let denominator = exponentials.iter().copied().fold(0.0_f32, rounded_add);
    Ok(exponentials
        .iter()
        .map(|&value| rounded_div(value, denominator))
        .collect())
}

pub fn dsa_range_fill(visible_positions: usize, top_k: usize) -> Vec<usize> {
    (0..visible_positions.min(top_k)).collect()
}

pub fn dsa_select_stable(
    scores: &[f32],
    visible_mask: &[bool],
    top_k: usize,
) -> Result<Vec<usize>, R9Error> {
    if scores.is_empty()
        || scores.len() != visible_mask.len()
        || top_k == 0
        || scores.iter().any(|value| !value.is_finite())
    {
        return Err(R9Error::InvalidShape("dsa indexer"));
    }
    let mut eligible = visible_mask
        .iter()
        .enumerate()
        .filter_map(|(index, &visible)| visible.then_some(index))
        .collect::<Vec<_>>();
    eligible.sort_by(|left, right| {
        scores[*right]
            .total_cmp(&scores[*left])
            .then_with(|| left.cmp(right))
    });
    eligible.truncate(top_k.min(eligible.len()));
    Ok(eligible)
}

fn rope_constants_f32(position: usize, width: usize) -> (Vec<f32>, Vec<f32>) {
    let mut cosine = Vec::with_capacity(width / 2);
    let mut sine = Vec::with_capacity(width / 2);
    for pair in 0..width / 2 {
        let index = pair * 2;
        // The independent oracle freezes the GLM RoPE constants in f64 and
        // converts each result once to f32 before pair arithmetic begins.
        let theta = position as f64 * 1_000_000.0_f64.powf(-(index as f64) / width as f64);
        cosine.push(theta.cos() as f32);
        sine.push(theta.sin() as f32);
    }
    (cosine, sine)
}

#[inline(never)]
fn rounded_mul(left: f32, right: f32) -> f32 {
    f32::from_bits((left * right).to_bits())
}

#[inline(never)]
fn rounded_add(left: f32, right: f32) -> f32 {
    f32::from_bits((left + right).to_bits())
}

#[inline(never)]
fn rounded_div(left: f32, right: f32) -> f32 {
    f32::from_bits((left / right).to_bits())
}

pub const R10_SCAFFOLD_VERSION: &str = "f017-r10-complete-layer-exact-v1";

#[derive(Debug, Clone, PartialEq)]
pub struct ExpertMatrices {
    pub expert_id: usize,
    pub gate: Vec<f32>,
    pub up: Vec<f32>,
    pub down: Vec<f32>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct R10Matrices {
    pub router: Vec<f32>,
    pub routed: Vec<ExpertMatrices>,
    pub shared: ExpertMatrices,
}

#[derive(Debug, Clone, PartialEq)]
pub struct R10Inputs {
    pub attention_residual: Vec<f32>,
    pub post_attention_norm_scale: Vec<f32>,
    pub router_bias: Vec<f64>,
    pub rms_epsilon: f32,
    pub top_k: usize,
    pub expert_weight_scale: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ExpertOutput {
    pub expert_id: usize,
    pub gate: Vec<f32>,
    pub up: Vec<f32>,
    pub hidden: Vec<f32>,
    pub down: Vec<f32>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct R10Output {
    pub normalized: Vec<f32>,
    pub router_logits: Vec<f32>,
    pub router_probabilities: Vec<f64>,
    pub router_scores: Vec<f64>,
    pub selected_ids: Vec<usize>,
    pub routing_weights: Vec<f64>,
    pub routed_experts: Vec<ExpertOutput>,
    pub shared_expert: ExpertOutput,
    pub routed_aggregate: Vec<f64>,
    pub combined_moe: Vec<f64>,
    pub output: Vec<f32>,
}

pub fn run_r10_exact(matrices: &R10Matrices, inputs: &R10Inputs) -> Result<R10Output, R9Error> {
    run_r10_with_matvec(matrices, inputs, |matrix, rows, columns, vector, role| {
        let mut output = vec![0.0_f32; rows];
        exact_matvec_f32(matrix, rows, columns, vector, &mut output)
            .map_err(|_| R9Error::CandidateMatvec(role))?;
        Ok(output)
    })
}

pub fn run_r10_with_matvec<F>(
    matrices: &R10Matrices,
    inputs: &R10Inputs,
    mut matvec: F,
) -> Result<R10Output, R9Error>
where
    F: FnMut(&[f32], usize, usize, &[f32], &'static str) -> Result<Vec<f32>, R9Error>,
{
    let width = inputs.attention_residual.len();
    let expert_count = inputs.router_bias.len();
    if width == 0
        || inputs.post_attention_norm_scale.len() != width
        || expert_count == 0
        || inputs.top_k == 0
        || inputs.top_k > expert_count
        || matrices.router.len() != expert_count * width
        || matrices.routed.len() != inputs.top_k
    {
        return Err(R9Error::InvalidShape("R10 inputs"));
    }
    for expert in matrices
        .routed
        .iter()
        .chain(std::iter::once(&matrices.shared))
    {
        if expert.gate.len() != width * width
            || expert.up.len() != width * width
            || expert.down.len() != width * width
        {
            return Err(R9Error::InvalidShape("R10 expert"));
        }
    }
    let normalized = exact_rms_norm_f32(
        &inputs.attention_residual,
        &inputs.post_attention_norm_scale,
        inputs.rms_epsilon,
    )?;
    let router_logits = matvec(
        &matrices.router,
        expert_count,
        width,
        &normalized,
        "ffn_gate_inp",
    )?;
    let router_probabilities = router_logits
        .iter()
        .map(|&value| stable_sigmoid_f64(f64::from(value)))
        .collect::<Vec<_>>();
    let router_scores = router_probabilities
        .iter()
        .zip(&inputs.router_bias)
        .map(|(&probability, &bias)| probability + bias)
        .collect::<Vec<_>>();
    let mut selected_ids = (0..expert_count).collect::<Vec<_>>();
    selected_ids.sort_by(|left, right| {
        router_scores[*right]
            .total_cmp(&router_scores[*left])
            .then_with(|| left.cmp(right))
    });
    selected_ids.truncate(inputs.top_k);
    if matrices
        .routed
        .iter()
        .map(|expert| expert.expert_id)
        .collect::<Vec<_>>()
        != selected_ids
    {
        return Err(R9Error::InvalidShape("R10 routed expert identity"));
    }
    let denominator = python_fsum(
        &selected_ids
            .iter()
            .map(|&index| router_probabilities[index])
            .collect::<Vec<_>>(),
    );
    let denominator = denominator.max(6.103_515_625e-5);
    let routing_weights = selected_ids
        .iter()
        .map(|&index| router_probabilities[index] / denominator * inputs.expert_weight_scale)
        .collect::<Vec<_>>();
    let mut routed_experts = Vec::with_capacity(inputs.top_k);
    for expert in &matrices.routed {
        routed_experts.push(run_exact_activation_expert(
            expert,
            &normalized,
            width,
            false,
            &mut matvec,
        )?);
    }
    let shared_expert =
        run_exact_activation_expert(&matrices.shared, &normalized, width, true, &mut matvec)?;
    let routed_aggregate = (0..width)
        .map(|column| {
            python_fsum(
                &(0..inputs.top_k)
                    .map(|route| {
                        routing_weights[route] * f64::from(routed_experts[route].down[column])
                    })
                    .collect::<Vec<_>>(),
            )
        })
        .collect::<Vec<_>>();
    let combined_moe = routed_aggregate
        .iter()
        .zip(&shared_expert.down)
        .map(|(&routed, &shared)| routed + f64::from(shared))
        .collect::<Vec<_>>();
    let output = inputs
        .attention_residual
        .iter()
        .zip(&combined_moe)
        .map(|(&residual, &moe)| (f64::from(residual) + moe) as f32)
        .collect();
    Ok(R10Output {
        normalized,
        router_logits,
        router_probabilities,
        router_scores,
        selected_ids,
        routing_weights,
        routed_experts,
        shared_expert,
        routed_aggregate,
        combined_moe,
        output,
    })
}

fn run_exact_activation_expert<F>(
    matrices: &ExpertMatrices,
    activation: &[f32],
    width: usize,
    shared: bool,
    matvec: &mut F,
) -> Result<ExpertOutput, R9Error>
where
    F: FnMut(&[f32], usize, usize, &[f32], &'static str) -> Result<Vec<f32>, R9Error>,
{
    let gate_role = if shared { "shared_gate" } else { "routed_gate" };
    let up_role = if shared { "shared_up" } else { "routed_up" };
    let down_role = if shared { "shared_down" } else { "routed_down" };
    let gate = matvec(&matrices.gate, width, width, activation, gate_role)?;
    let up = matvec(&matrices.up, width, width, activation, up_role)?;
    let mut hidden = vec![0.0_f32; width];
    exact_swiglu_f32(&gate, &up, &mut hidden).map_err(R9Error::Matvec)?;
    let down = matvec(&matrices.down, width, width, &hidden, down_role)?;
    Ok(ExpertOutput {
        expert_id: matrices.expert_id,
        gate,
        up,
        hidden,
        down,
    })
}

fn stable_sigmoid_f64(value: f64) -> f64 {
    if value >= 0.0 {
        let factor = (-value).exp();
        1.0 / (1.0 + factor)
    } else {
        let factor = value.exp();
        factor / (1.0 + factor)
    }
}

fn python_fsum(values: &[f64]) -> f64 {
    let mut partials: Vec<f64> = Vec::new();
    for &value in values {
        let mut x = value;
        let mut next = Vec::with_capacity(partials.len() + 1);
        for &partial in &partials {
            let (large, small) = if x.abs() < partial.abs() {
                (partial, x)
            } else {
                (x, partial)
            };
            let high = large + small;
            let low = small - (high - large);
            if low != 0.0 {
                next.push(low);
            }
            x = high;
        }
        next.push(x);
        partials = next;
    }
    let mut high = 0.0_f64;
    let mut low = 0.0_f64;
    let mut count = partials.len();
    while count > 0 {
        count -= 1;
        let x = high;
        let y = partials[count];
        high = x + y;
        let rounded_y = high - x;
        low = y - rounded_y;
        if low != 0.0 {
            break;
        }
    }
    // Match CPython math.fsum's final half-even correction when the remaining
    // partial has the same sign as the following partial.
    if count > 0
        && ((low < 0.0 && partials[count - 1] < 0.0) || (low > 0.0 && partials[count - 1] > 0.0))
    {
        let doubled = low * 2.0;
        let corrected = high + doubled;
        if doubled == corrected - high {
            high = corrected;
        }
    }
    high
}
