//! Apple production serial-f32 layer-3 capture graph.
//!
//! This module intentionally does not call the R9/R10 qualification helpers.
//! Matrix projections are delegated to the Apple MLX backend; every scalar
//! reduction and composition point is an explicit binary32 left fold. Capture
//! observes each value after it is produced and never recomputes a stage.

use std::collections::BTreeSet;

pub const APPLE_SERIAL_F32_GRAPH_VERSION: &str = "f017-apple-serial-f32-s0-s2-v1";
pub const RMS_EPSILON: f32 = 0.00001_f32;
pub const ROUTER_TOP_K: usize = 8;
pub const ROUTER_DENOMINATOR_FLOOR: f32 = 6.103_515_625e-5_f32;

pub const STAGE_IDS: &[&str] = &[
    "input_hidden",
    "attention_normalized",
    "query_rank",
    "query_rank_normalized",
    "query_heads",
    "kv_raw",
    "kv_normalized",
    "key_nope",
    "attention_scores",
    "attention_weights",
    "value_heads",
    "attention_output",
    "post_attention_residual",
    "router_normalized",
    "router_logits",
    "router_probabilities",
    "router_scores",
    "ranking",
    "selected_ids",
    "routing_weights",
    "routed_gate",
    "routed_up",
    "routed_silu",
    "routed_gate_up_product",
    "routed_weighted_hidden",
    "routed_down_outputs",
    "routed_aggregate",
    "shared_gate",
    "shared_up",
    "shared_silu",
    "shared_gate_up_product",
    "shared_expert_output",
    "production_ffn",
    "production_s2",
];

#[derive(Clone, Debug, PartialEq)]
pub struct DenseMatrix {
    pub rows: usize,
    pub columns: usize,
    pub values: Vec<f32>,
}

impl DenseMatrix {
    pub fn validate(&self, name: &'static str) -> Result<(), AppleGraphError> {
        if self.rows == 0
            || self.columns == 0
            || self.values.len() != self.rows.saturating_mul(self.columns)
            || self.values.iter().any(|v| !v.is_finite())
        {
            return Err(AppleGraphError::InvalidShape(name));
        }
        Ok(())
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct ExpertMatrices {
    pub expert_id: usize,
    pub gate: DenseMatrix,
    pub up: DenseMatrix,
    pub down: DenseMatrix,
}

#[derive(Clone, Debug, PartialEq)]
pub struct AppleLayerMatrices {
    pub q_a: DenseMatrix,
    pub q_b: DenseMatrix,
    pub kv_a: DenseMatrix,
    pub k_b: DenseMatrix,
    pub v_b: DenseMatrix,
    pub attention_output: DenseMatrix,
    pub router: DenseMatrix,
    pub routed: Vec<ExpertMatrices>,
    pub shared: ExpertMatrices,
}

#[derive(Clone, Debug, PartialEq)]
pub struct AppleLayerInputs {
    pub s0: Vec<f32>,
    pub attention_norm_scale: Vec<f32>,
    pub q_rank_norm_scale: Vec<f32>,
    pub kv_norm_scale: Vec<f32>,
    pub ffn_norm_scale: Vec<f32>,
    pub correction_bias: Vec<f32>,
    pub position: usize,
    pub rope_base: f32,
    pub attention_scale: f32,
    pub expert_weight_scale: f32,
    pub heads: usize,
    pub qk_nope: usize,
    pub qk_rope: usize,
    pub kv_lora: usize,
    pub value_dim: usize,
}

#[derive(Clone, Debug, PartialEq)]
pub struct AppleLayerOutput {
    pub selected_ids: Vec<usize>,
    pub routing_weights: Vec<f32>,
    pub s2: Vec<f32>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum AppleGraphError {
    InvalidShape(&'static str),
    Backend(&'static str),
    Capture(&'static str),
    NonFinite(&'static str),
    StageCensus,
}

impl std::fmt::Display for AppleGraphError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::InvalidShape(v) => write!(f, "invalid Apple production shape: {v}"),
            Self::Backend(v) => write!(f, "Apple production backend failed: {v}"),
            Self::Capture(v) => write!(f, "Apple production capture failed: {v}"),
            Self::NonFinite(v) => write!(f, "non-finite Apple production stage: {v}"),
            Self::StageCensus => write!(f, "Apple production capture stage census mismatch"),
        }
    }
}

impl std::error::Error for AppleGraphError {}

/// Implemented by the pinned MLX f32 matvec adapter in the production binary.
pub trait ProjectionBackend {
    fn matvec(
        &mut self,
        role: &'static str,
        matrix: &DenseMatrix,
        vector: &[f32],
    ) -> Result<Vec<f32>, AppleGraphError>;
}

/// A capture sink receives the exact already-produced host values.
pub trait CaptureSink {
    fn capture(
        &mut self,
        stage_id: &'static str,
        shape: &[usize],
        values: &[f32],
    ) -> Result<(), AppleGraphError>;

    fn capture_u16(
        &mut self,
        stage_id: &'static str,
        shape: &[usize],
        values: &[u16],
    ) -> Result<(), AppleGraphError>;
}

#[inline(never)]
fn add_f32(a: f32, b: f32) -> f32 {
    f32::from_bits((a + b).to_bits())
}

#[inline(never)]
fn mul_f32(a: f32, b: f32) -> f32 {
    f32::from_bits((a * b).to_bits())
}

#[inline(never)]
fn div_f32(a: f32, b: f32) -> f32 {
    f32::from_bits((a / b).to_bits())
}

fn finite(stage: &'static str, values: &[f32]) -> Result<(), AppleGraphError> {
    if values.iter().all(|v| v.is_finite()) {
        Ok(())
    } else {
        Err(AppleGraphError::NonFinite(stage))
    }
}

pub fn rms_norm_serial_f32(
    values: &[f32],
    scale: &[f32],
    epsilon: f32,
) -> Result<Vec<f32>, AppleGraphError> {
    if values.is_empty()
        || values.len() != scale.len()
        || epsilon.to_bits() != RMS_EPSILON.to_bits()
    {
        return Err(AppleGraphError::InvalidShape("rms_norm"));
    }
    let mut sum = 0.0_f32;
    for &value in values {
        sum = add_f32(sum, mul_f32(value, value));
    }
    let mean = div_f32(sum, values.len() as f32);
    let inverse = f32::from_bits((add_f32(mean, epsilon).sqrt().recip()).to_bits());
    let output = values
        .iter()
        .zip(scale)
        .map(|(&value, &weight)| mul_f32(mul_f32(value, inverse), weight))
        .collect::<Vec<_>>();
    finite("rms_norm", &output)?;
    Ok(output)
}

fn rope_tail_serial_f32(
    query: &mut [f32],
    heads: usize,
    qk_dim: usize,
    rope_dim: usize,
    position: usize,
    base: f32,
) -> Result<(), AppleGraphError> {
    if rope_dim == 0
        || rope_dim % 2 != 0
        || qk_dim < rope_dim
        || query.len() != heads * qk_dim
        || base <= 0.0
    {
        return Err(AppleGraphError::InvalidShape("rope"));
    }
    let offset = qk_dim - rope_dim;
    for head in 0..heads {
        for pair in 0..rope_dim / 2 {
            let index = pair * 2;
            let exponent = div_f32(-(index as f32), rope_dim as f32);
            let frequency = f32::from_bits(base.powf(exponent).to_bits());
            let theta = mul_f32(position as f32, frequency);
            let cosine = f32::from_bits(theta.cos().to_bits());
            let sine = f32::from_bits(theta.sin().to_bits());
            let at = head * qk_dim + offset + index;
            let x0 = query[at];
            let x1 = query[at + 1];
            query[at] = add_f32(mul_f32(x0, cosine), -mul_f32(x1, sine));
            query[at + 1] = add_f32(mul_f32(x0, sine), mul_f32(x1, cosine));
        }
    }
    finite("rope", query)
}

pub fn softmax_serial_f32(values: &[f32]) -> Result<Vec<f32>, AppleGraphError> {
    if values.is_empty() || values.iter().any(|v| !v.is_finite()) {
        return Err(AppleGraphError::InvalidShape("softmax"));
    }
    let mut maximum = f32::NEG_INFINITY;
    for &value in values {
        if value > maximum {
            maximum = value;
        }
    }
    let mut output = Vec::with_capacity(values.len());
    let mut sum = 0.0_f32;
    for &value in values {
        let exponential = f32::from_bits((value - maximum).exp().to_bits());
        output.push(exponential);
        sum = add_f32(sum, exponential);
    }
    for value in &mut output {
        *value = div_f32(*value, sum);
    }
    finite("softmax", &output)?;
    Ok(output)
}

fn sigmoid_f32(value: f32) -> f32 {
    if value >= 0.0 {
        let factor = f32::from_bits((-value).exp().to_bits());
        div_f32(1.0, add_f32(1.0, factor))
    } else {
        let factor = f32::from_bits(value.exp().to_bits());
        div_f32(factor, add_f32(1.0, factor))
    }
}

fn silu_f32(value: f32) -> f32 {
    mul_f32(value, sigmoid_f32(value))
}

fn capture(
    sink: &mut impl CaptureSink,
    seen: &mut BTreeSet<&'static str>,
    id: &'static str,
    shape: &[usize],
    values: &[f32],
) -> Result<(), AppleGraphError> {
    if !seen.insert(id)
        || !STAGE_IDS.contains(&id)
        || shape.iter().product::<usize>() != values.len()
    {
        return Err(AppleGraphError::Capture(id));
    }
    finite(id, values)?;
    sink.capture(id, shape, values)
}

fn capture_indices(
    sink: &mut impl CaptureSink,
    seen: &mut BTreeSet<&'static str>,
    id: &'static str,
    shape: &[usize],
    values: &[u16],
) -> Result<(), AppleGraphError> {
    if !seen.insert(id)
        || !STAGE_IDS.contains(&id)
        || shape.iter().product::<usize>() != values.len()
    {
        return Err(AppleGraphError::Capture(id));
    }
    sink.capture_u16(id, shape, values)
}

struct ExpertTrace {
    gate: Vec<f32>,
    up: Vec<f32>,
    silu: Vec<f32>,
    product: Vec<f32>,
    weighted_hidden: Vec<f32>,
    down: Vec<f32>,
}

fn expert(
    backend: &mut impl ProjectionBackend,
    input: &[f32],
    matrices: &ExpertMatrices,
    weight: f32,
    role: &'static str,
) -> Result<ExpertTrace, AppleGraphError> {
    let gate = backend.matvec(role, &matrices.gate, input)?;
    let up = backend.matvec(role, &matrices.up, input)?;
    if gate.len() != up.len()
        || matrices.down.columns != gate.len()
        || matrices.down.rows != input.len()
    {
        return Err(AppleGraphError::InvalidShape("expert"));
    }
    let mut silu = Vec::with_capacity(gate.len());
    let mut product = Vec::with_capacity(gate.len());
    let mut hidden = Vec::with_capacity(gate.len());
    for (&g, &u) in gate.iter().zip(&up) {
        let activated = silu_f32(g);
        let multiplied = mul_f32(activated, u);
        silu.push(activated);
        product.push(multiplied);
        hidden.push(mul_f32(multiplied, weight));
    }
    let down = backend.matvec(role, &matrices.down, &hidden)?;
    Ok(ExpertTrace {
        gate,
        up,
        silu,
        product,
        weighted_hidden: hidden,
        down,
    })
}

/// Execute the Apple production graph for the accepted representative
/// one-token M1-F0 surface. The function owns no checkpoint or fallback path.
pub fn run_apple_serial_f32(
    backend: &mut impl ProjectionBackend,
    sink: &mut impl CaptureSink,
    matrices: &AppleLayerMatrices,
    inputs: &AppleLayerInputs,
) -> Result<AppleLayerOutput, AppleGraphError> {
    let width = inputs.s0.len();
    let qk_dim = inputs.qk_nope + inputs.qk_rope;
    if width == 0
        || inputs.heads == 0
        || inputs.correction_bias.len() != matrices.router.rows
        || inputs.attention_norm_scale.len() != width
        || inputs.ffn_norm_scale.len() != width
        || matrices.q_a.columns != width
        || matrices.q_a.rows != inputs.q_rank_norm_scale.len()
        || matrices.q_b.columns != matrices.q_a.rows
        || matrices.q_b.rows != inputs.heads * qk_dim
        || matrices.kv_a.columns != width
        || matrices.kv_a.rows != inputs.kv_lora + inputs.qk_rope
        || inputs.kv_norm_scale.len() != inputs.kv_lora
        || matrices.k_b.columns != inputs.qk_nope
        || matrices.k_b.rows != inputs.heads * inputs.kv_lora
        || matrices.v_b.columns != inputs.kv_lora
        || matrices.v_b.rows != inputs.heads * inputs.value_dim
        || matrices.attention_output.columns != inputs.heads * inputs.value_dim
        || matrices.attention_output.rows != width
        || matrices.router.columns != width
        || matrices.routed.len() != ROUTER_TOP_K
        || matrices.router.rows < ROUTER_TOP_K
        || inputs.rope_base <= 0.0
        || inputs.attention_scale <= 0.0
    {
        return Err(AppleGraphError::InvalidShape("graph"));
    }
    for (name, matrix) in [
        ("q_a", &matrices.q_a),
        ("q_b", &matrices.q_b),
        ("kv_a", &matrices.kv_a),
        ("k_b", &matrices.k_b),
        ("v_b", &matrices.v_b),
        ("attention_output", &matrices.attention_output),
        ("router", &matrices.router),
    ] {
        matrix.validate(name)?;
    }
    let mut seen = BTreeSet::new();
    capture(sink, &mut seen, "input_hidden", &[width], &inputs.s0)?;

    let attention_normalized =
        rms_norm_serial_f32(&inputs.s0, &inputs.attention_norm_scale, RMS_EPSILON)?;
    capture(
        sink,
        &mut seen,
        "attention_normalized",
        &[width],
        &attention_normalized,
    )?;
    let query_rank = backend.matvec("attn_q_a", &matrices.q_a, &attention_normalized)?;
    capture(
        sink,
        &mut seen,
        "query_rank",
        &[matrices.q_a.rows],
        &query_rank,
    )?;
    let query_rank_normalized =
        rms_norm_serial_f32(&query_rank, &inputs.q_rank_norm_scale, RMS_EPSILON)?;
    capture(
        sink,
        &mut seen,
        "query_rank_normalized",
        &[matrices.q_a.rows],
        &query_rank_normalized,
    )?;
    let mut query_heads = backend.matvec("attn_q_b", &matrices.q_b, &query_rank_normalized)?;
    rope_tail_serial_f32(
        &mut query_heads,
        inputs.heads,
        qk_dim,
        inputs.qk_rope,
        inputs.position,
        inputs.rope_base,
    )?;
    capture(
        sink,
        &mut seen,
        "query_heads",
        &[inputs.heads, qk_dim],
        &query_heads,
    )?;

    let kv_raw = backend.matvec("attn_kv_a_mqa", &matrices.kv_a, &attention_normalized)?;
    capture(
        sink,
        &mut seen,
        "kv_raw",
        &[inputs.kv_lora + inputs.qk_rope],
        &kv_raw,
    )?;
    let kv_normalized = rms_norm_serial_f32(
        &kv_raw[..inputs.kv_lora],
        &inputs.kv_norm_scale,
        RMS_EPSILON,
    )?;
    capture(
        sink,
        &mut seen,
        "kv_normalized",
        &[inputs.kv_lora],
        &kv_normalized,
    )?;
    let mut current_key_rope = kv_raw[inputs.kv_lora..].to_vec();
    rope_tail_serial_f32(
        &mut current_key_rope,
        1,
        inputs.qk_rope,
        inputs.qk_rope,
        inputs.position,
        inputs.rope_base,
    )?;
    let mut q_nope = Vec::with_capacity(inputs.heads * inputs.qk_nope);
    for head in 0..inputs.heads {
        q_nope.extend_from_slice(&query_heads[head * qk_dim..head * qk_dim + inputs.qk_nope]);
    }
    let mut key_nope = Vec::with_capacity(inputs.heads * inputs.kv_lora);
    for head in 0..inputs.heads {
        let start = head * inputs.kv_lora * inputs.qk_nope;
        let end = start + inputs.kv_lora * inputs.qk_nope;
        let head_matrix = DenseMatrix {
            rows: inputs.kv_lora,
            columns: inputs.qk_nope,
            values: matrices.k_b.values[start..end].to_vec(),
        };
        let head_values = backend.matvec(
            "attn_k_b",
            &head_matrix,
            &q_nope[head * inputs.qk_nope..(head + 1) * inputs.qk_nope],
        )?;
        key_nope.extend_from_slice(&head_values);
    }
    capture(
        sink,
        &mut seen,
        "key_nope",
        &[inputs.heads, inputs.kv_lora],
        &key_nope,
    )?;

    let mut scores = Vec::with_capacity(inputs.heads);
    for head in 0..inputs.heads {
        let mut score = 0.0_f32;
        for column in 0..inputs.kv_lora {
            score = add_f32(
                score,
                mul_f32(
                    key_nope[head * inputs.kv_lora + column],
                    kv_normalized[column],
                ),
            );
        }
        let q_rope = &query_heads[head * qk_dim + inputs.qk_nope..(head + 1) * qk_dim];
        for column in 0..inputs.qk_rope {
            score = add_f32(score, mul_f32(q_rope[column], current_key_rope[column]));
        }
        scores.push(mul_f32(score, inputs.attention_scale));
    }
    capture(
        sink,
        &mut seen,
        "attention_scores",
        &[inputs.heads],
        &scores,
    )?;
    let mut attention_weights = Vec::with_capacity(inputs.heads);
    for &score in &scores {
        attention_weights.push(softmax_serial_f32(&[score])?[0]);
    }
    capture(
        sink,
        &mut seen,
        "attention_weights",
        &[inputs.heads],
        &attention_weights,
    )?;
    let mut value_heads = backend.matvec("attn_v_b", &matrices.v_b, &kv_normalized)?;
    for head in 0..inputs.heads {
        for column in 0..inputs.value_dim {
            let at = head * inputs.value_dim + column;
            value_heads[at] = mul_f32(value_heads[at], attention_weights[head]);
        }
    }
    capture(
        sink,
        &mut seen,
        "value_heads",
        &[inputs.heads, inputs.value_dim],
        &value_heads,
    )?;
    let attention_output =
        backend.matvec("attn_output", &matrices.attention_output, &value_heads)?;
    capture(
        sink,
        &mut seen,
        "attention_output",
        &[width],
        &attention_output,
    )?;
    let s1 = inputs
        .s0
        .iter()
        .zip(&attention_output)
        .map(|(&a, &b)| add_f32(a, b))
        .collect::<Vec<_>>();
    capture(sink, &mut seen, "post_attention_residual", &[width], &s1)?;

    let normalized = rms_norm_serial_f32(&s1, &inputs.ffn_norm_scale, RMS_EPSILON)?;
    capture(sink, &mut seen, "router_normalized", &[width], &normalized)?;
    let logits = backend.matvec("ffn_gate_inp", &matrices.router, &normalized)?;
    capture(
        sink,
        &mut seen,
        "router_logits",
        &[matrices.router.rows],
        &logits,
    )?;
    let probabilities = logits.iter().map(|&v| sigmoid_f32(v)).collect::<Vec<_>>();
    capture(
        sink,
        &mut seen,
        "router_probabilities",
        &[matrices.router.rows],
        &probabilities,
    )?;
    let scores = probabilities
        .iter()
        .zip(&inputs.correction_bias)
        .map(|(&p, &b)| add_f32(p, b))
        .collect::<Vec<_>>();
    capture(
        sink,
        &mut seen,
        "router_scores",
        &[matrices.router.rows],
        &scores,
    )?;
    let mut ranking = (0..scores.len()).collect::<Vec<_>>();
    ranking.sort_by(|&a, &b| scores[b].total_cmp(&scores[a]).then_with(|| a.cmp(&b)));
    let ranking_u16 = ranking
        .iter()
        .map(|&v| u16::try_from(v).unwrap())
        .collect::<Vec<_>>();
    capture_indices(
        sink,
        &mut seen,
        "ranking",
        &[matrices.router.rows],
        &ranking_u16,
    )?;
    let selected_ids = ranking[..ROUTER_TOP_K].to_vec();
    let selected_u16 = selected_ids
        .iter()
        .map(|&v| u16::try_from(v).unwrap())
        .collect::<Vec<_>>();
    capture_indices(
        sink,
        &mut seen,
        "selected_ids",
        &[ROUTER_TOP_K],
        &selected_u16,
    )?;
    if matrices
        .routed
        .iter()
        .map(|e| e.expert_id)
        .collect::<Vec<_>>()
        != selected_ids
    {
        return Err(AppleGraphError::InvalidShape("selected expert bindings"));
    }
    let mut denominator = 0.0_f32;
    for &id in &selected_ids {
        denominator = add_f32(denominator, probabilities[id]);
    }
    denominator = denominator.max(ROUTER_DENOMINATOR_FLOOR);
    let weights = selected_ids
        .iter()
        .map(|&id| {
            mul_f32(
                div_f32(probabilities[id], denominator),
                inputs.expert_weight_scale,
            )
        })
        .collect::<Vec<_>>();
    capture(
        sink,
        &mut seen,
        "routing_weights",
        &[ROUTER_TOP_K],
        &weights,
    )?;

    let mut routed_outputs = Vec::with_capacity(ROUTER_TOP_K);
    for (slot, matrices) in matrices.routed.iter().enumerate() {
        routed_outputs.push(expert(
            backend,
            &normalized,
            matrices,
            weights[slot],
            "routed_expert",
        )?);
    }
    let hidden = routed_outputs[0].gate.len();
    let routed_gate = routed_outputs
        .iter()
        .flat_map(|v| v.gate.iter().copied())
        .collect::<Vec<_>>();
    let routed_up = routed_outputs
        .iter()
        .flat_map(|v| v.up.iter().copied())
        .collect::<Vec<_>>();
    let routed_silu = routed_outputs
        .iter()
        .flat_map(|v| v.silu.iter().copied())
        .collect::<Vec<_>>();
    let routed_product = routed_outputs
        .iter()
        .flat_map(|v| v.product.iter().copied())
        .collect::<Vec<_>>();
    let routed_hidden = routed_outputs
        .iter()
        .flat_map(|v| v.weighted_hidden.iter().copied())
        .collect::<Vec<_>>();
    let flattened = routed_outputs
        .iter()
        .flat_map(|v| v.down.iter().copied())
        .collect::<Vec<_>>();
    capture(
        sink,
        &mut seen,
        "routed_gate",
        &[ROUTER_TOP_K, hidden],
        &routed_gate,
    )?;
    capture(
        sink,
        &mut seen,
        "routed_up",
        &[ROUTER_TOP_K, hidden],
        &routed_up,
    )?;
    capture(
        sink,
        &mut seen,
        "routed_silu",
        &[ROUTER_TOP_K, hidden],
        &routed_silu,
    )?;
    capture(
        sink,
        &mut seen,
        "routed_gate_up_product",
        &[ROUTER_TOP_K, hidden],
        &routed_product,
    )?;
    capture(
        sink,
        &mut seen,
        "routed_weighted_hidden",
        &[ROUTER_TOP_K, hidden],
        &routed_hidden,
    )?;
    capture(
        sink,
        &mut seen,
        "routed_down_outputs",
        &[ROUTER_TOP_K, width],
        &flattened,
    )?;
    let mut aggregate = vec![0.0_f32; width];
    for slot in 0..ROUTER_TOP_K {
        for column in 0..width {
            aggregate[column] = add_f32(aggregate[column], routed_outputs[slot].down[column]);
        }
    }
    capture(sink, &mut seen, "routed_aggregate", &[width], &aggregate)?;
    let shared = expert(backend, &normalized, &matrices.shared, 1.0, "shared_expert")?;
    capture(
        sink,
        &mut seen,
        "shared_gate",
        &[shared.gate.len()],
        &shared.gate,
    )?;
    capture(sink, &mut seen, "shared_up", &[shared.up.len()], &shared.up)?;
    capture(
        sink,
        &mut seen,
        "shared_silu",
        &[shared.silu.len()],
        &shared.silu,
    )?;
    capture(
        sink,
        &mut seen,
        "shared_gate_up_product",
        &[shared.product.len()],
        &shared.product,
    )?;
    capture(
        sink,
        &mut seen,
        "shared_expert_output",
        &[width],
        &shared.down,
    )?;
    let ffn = aggregate
        .iter()
        .zip(&shared.down)
        .map(|(&a, &b)| add_f32(a, b))
        .collect::<Vec<_>>();
    capture(sink, &mut seen, "production_ffn", &[width], &ffn)?;
    let s2 = s1
        .iter()
        .zip(&ffn)
        .map(|(&a, &b)| add_f32(a, b))
        .collect::<Vec<_>>();
    capture(sink, &mut seen, "production_s2", &[width], &s2)?;
    if seen.len() != STAGE_IDS.len() {
        return Err(AppleGraphError::StageCensus);
    }
    Ok(AppleLayerOutput {
        selected_ids,
        routing_weights: weights,
        s2,
    })
}
