//! Stateful multi-position execution: the explicit successor surface to the
//! bounded one-token producer in [`crate::model`].
//!
//! `execute_one_token` is position zero with a single visible key: its softmax
//! has one element, RoPE is the identity there, and no state survives the call.
//! Looping it is not autoregressive generation. This module adds what is
//! actually missing — rotary position embedding at nonzero positions, a causal
//! multi-key softmax, and a retained latent cache — without touching the
//! frozen one-token path or its admission behaviour.
//!
//! Attention follows the checkpoint's absorbed MLA form, the same one the
//! one-token producer already uses:
//!
//! * `attn_kv_a_mqa` produces `[c (kv_rank) | k_rope (qk_rope)]`; `c` is
//!   RMS-normalised by `attn_kv_a_norm` and `k_rope` is rotated at the key's
//!   own position. Both are what the cache retains, per layer, per position.
//! * `attn_k_b[h]` maps this head's `q_nope` into the latent space, so the
//!   no-position part of the score is `(W_kb_h q_nope) · c_j`.
//! * the positional part is `rope(q_rope, i) · k_rope_j`.
//! * `attn_v_b[h]` maps the attention-weighted latent back out, applied once
//!   to the aggregated latent rather than per key.
//!
//! The sparse indexer that `glm-dsa` carries (`blk.N.indexer.*`,
//! `attention.indexer.top_k`) is not implemented. It is provably inert only
//! while the whole sequence fits in its top-k budget, so this runtime refuses
//! sequences longer than [`TemporalConfig::indexer_top_k`] instead of
//! silently substituting dense attention beyond that bound.

use crate::model::{Matrix, MatvecBackend, ModelConfig, TensorSource};
use serde::{Deserialize, Serialize};

pub const TEMPORAL_SCHEMA: &str = "pulsarmlx.f017.native-temporal-runtime/1.0.0";

/// How the rotary pair is formed inside the `qk_rope` slice.
///
/// GGML's NEOX rope pairs element `i` with `i + n/2`; the alternative pairs
/// `2i` with `2i+1`. Which one a given GGUF conversion produced is a property
/// of the checkpoint, so it is declared and carried, never assumed silently.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RopePairing {
    NeoxHalfSplit,
    Interleaved,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TemporalConfig {
    pub model: ModelConfig,
    /// `1/sqrt(qk_nope + qk_rope)` for this checkpoint family; carried
    /// explicitly so a test can prove the runtime uses the configured value.
    pub attention_softmax_scale: f32,
    pub rope_pairing: RopePairing,
    /// `attention.indexer.top_k`. Sequences longer than this are refused.
    pub indexer_top_k: usize,
    /// Hard ceiling on retained positions for one session.
    pub max_positions: usize,
}

impl TemporalConfig {
    pub fn softmax_scale_rule(model: &ModelConfig) -> f32 {
        1.0_f32 / ((model.qk_nope + model.qk_rope) as f32).sqrt()
    }
    /// The GLM-5.2 temporal configuration. `indexer_top_k` is the
    /// checkpoint's `glm-dsa.attention.indexer.top_k`; `max_positions` may not
    /// exceed it while the indexer is unimplemented.
    pub fn glm52() -> Self {
        let model = ModelConfig::glm52();
        Self {
            attention_softmax_scale: Self::softmax_scale_rule(&model),
            model,
            rope_pairing: RopePairing::NeoxHalfSplit,
            indexer_top_k: 2048,
            max_positions: 2048,
        }
    }
    pub fn validate(&self) -> Result<(), String> {
        self.model.validate()?;
        if !self.attention_softmax_scale.is_finite() || self.attention_softmax_scale <= 0.0 {
            return Err("invalid attention_softmax_scale".into());
        }
        if self.indexer_top_k == 0 || self.max_positions == 0 {
            return Err("invalid position bounds".into());
        }
        if self.max_positions > self.indexer_top_k {
            return Err("max_positions exceeds the indexer top-k budget: the sparse indexer is not implemented and is only inert within it".into());
        }
        Ok(())
    }
}

/// Retained causal state: per layer, the normalised latent and the rotated
/// rope key of every accepted position, in append order.
#[derive(Clone, Debug)]
pub struct SequenceState {
    kv_rank: usize,
    qk_rope: usize,
    layer_count: usize,
    max_positions: usize,
    latent: Vec<Vec<f32>>,
    rope_key: Vec<Vec<f32>>,
    positions: usize,
    /// Positions fully committed across every layer. A partially written
    /// position (a failure mid-stack) is never visible to a later call.
    committed: usize,
}

impl SequenceState {
    pub fn new(config: &TemporalConfig) -> Self {
        let model = &config.model;
        Self {
            kv_rank: model.kv_rank,
            qk_rope: model.qk_rope,
            layer_count: model.layer_count,
            max_positions: config.max_positions,
            latent: vec![Vec::new(); model.layer_count],
            rope_key: vec![Vec::new(); model.layer_count],
            positions: 0,
            committed: 0,
        }
    }
    pub fn positions(&self) -> usize {
        self.committed
    }
    pub fn reset(&mut self) {
        for buffer in self.latent.iter_mut() {
            buffer.clear();
        }
        for buffer in self.rope_key.iter_mut() {
            buffer.clear();
        }
        self.positions = 0;
        self.committed = 0;
    }
    /// Bytes of retained causal state. Weights are not part of this.
    pub fn state_bytes(&self) -> usize {
        (self.latent.iter().map(Vec::len).sum::<usize>()
            + self.rope_key.iter().map(Vec::len).sum::<usize>())
            * std::mem::size_of::<f32>()
    }
    fn append(&mut self, layer: usize, latent: &[f32], rope_key: &[f32]) -> Result<(), String> {
        if layer >= self.layer_count {
            return Err("state layer out of range".into());
        }
        if latent.len() != self.kv_rank || rope_key.len() != self.qk_rope {
            return Err("state shape".into());
        }
        if self.latent[layer].len() / self.kv_rank != self.positions {
            return Err("state append order".into());
        }
        if self.positions >= self.max_positions {
            return Err("retained positions exceed max_positions".into());
        }
        self.latent[layer].extend_from_slice(latent);
        self.rope_key[layer].extend_from_slice(rope_key);
        Ok(())
    }
    fn commit(&mut self) -> Result<(), String> {
        for layer in 0..self.layer_count {
            if self.latent[layer].len() / self.kv_rank != self.positions + 1 {
                return Err("incomplete position across the layer stack".into());
            }
        }
        self.positions += 1;
        self.committed = self.positions;
        Ok(())
    }
    /// Drop a partially written position so a failed step leaves the state
    /// exactly as it was.
    fn rollback(&mut self) {
        for layer in 0..self.layer_count {
            self.latent[layer].truncate(self.committed * self.kv_rank);
            self.rope_key[layer].truncate(self.committed * self.qk_rope);
        }
        self.positions = self.committed;
    }
    fn latent_at(&self, layer: usize, position: usize) -> &[f32] {
        &self.latent[layer][position * self.kv_rank..(position + 1) * self.kv_rank]
    }
    fn rope_key_at(&self, layer: usize, position: usize) -> &[f32] {
        &self.rope_key[layer][position * self.qk_rope..(position + 1) * self.qk_rope]
    }
}


// The frozen one-token producer in `model` is sha-bound by the consumed
// attempt-2 admission contract, so this successor carries its own copies of
// the elementwise helpers instead of editing that file. They are held to the
// original by `position_zero_reproduces_the_one_token_producer`, which
// requires bit-identical logits from both paths.

fn rms_norm(x: &[f32], scale: &[f32], epsilon: f32) -> Result<Vec<f32>, String> {
    if x.len() != scale.len() || x.is_empty() {
        return Err("rms shape".into());
    }
    let mut sum = 0.0_f32;
    for v in x {
        sum = (sum + *v * *v) as f32;
    }
    let inv = (sum / x.len() as f32 + epsilon).sqrt().recip();
    Ok(x.iter()
        .zip(scale)
        .map(|(v, s)| (*v * inv * *s) as f32)
        .collect())
}

fn silu(v: f32) -> f32 {
    (v / (1.0 + (-v).exp())) as f32
}

fn residual(a: &[f32], b: &[f32]) -> Result<Vec<f32>, String> {
    if a.len() != b.len() {
        return Err("residual shape".into());
    }
    Ok(a.iter().zip(b).map(|(x, y)| (*x + *y) as f32).collect())
}

fn argmax(logits: &[f32]) -> Result<u32, String> {
    logits
        .iter()
        .enumerate()
        .max_by(|(ia, a), (ib, b)| a.total_cmp(b).then_with(|| ib.cmp(ia)))
        .map(|(index, _)| index as u32)
        .ok_or_else(|| "empty logits".to_string())
}

fn load_projection(
    source: &mut impl TensorSource,
    prefix: &str,
    suffix: &str,
    expert: Option<usize>,
    shared: bool,
    rows: usize,
    columns: usize,
) -> Result<Matrix, String> {
    match expert {
        Some(id) => {
            source.expert_matrix(&format!("{prefix}_{suffix}_exps.weight"), id, rows, columns)
        }
        None if shared => source.matrix(&format!("{prefix}_{suffix}_shexp.weight"), rows, columns),
        None => source.matrix(&format!("{prefix}_{suffix}.weight"), rows, columns),
    }
}

#[allow(clippy::too_many_arguments)]
fn swiglu(
    source: &mut impl TensorSource,
    backend: &mut impl MatvecBackend,
    prefix: &str,
    expert: Option<usize>,
    shared: bool,
    x: &[f32],
    inner: usize,
    hidden: usize,
    weight: f32,
) -> Result<Vec<f32>, String> {
    let gate = backend.matvec(
        "ffn_gate",
        &load_projection(source, prefix, "gate", expert, shared, inner, x.len())?,
        x,
    )?;
    let up = backend.matvec(
        "ffn_up",
        &load_projection(source, prefix, "up", expert, shared, inner, x.len())?,
        x,
    )?;
    let product = gate
        .iter()
        .zip(up)
        .map(|(g, u)| (silu(*g) * u * weight) as f32)
        .collect::<Vec<_>>();
    backend.matvec(
        "ffn_down",
        &load_projection(source, prefix, "down", expert, shared, hidden, inner)?,
        &product,
    )
}

fn route(
    logits: &[f32],
    bias: &[f32],
    k: usize,
    scale: f32,
) -> Result<(Vec<usize>, Vec<f32>), String> {
    if logits.len() != bias.len() || k > logits.len() {
        return Err("route shape".into());
    }
    let probabilities = logits
        .iter()
        .map(|v| 1.0_f32 / (1.0 + (-*v).exp()))
        .collect::<Vec<_>>();
    let scores = probabilities
        .iter()
        .zip(bias)
        .map(|(p, b)| (*p + *b) as f32)
        .collect::<Vec<_>>();
    let mut order = (0..scores.len()).collect::<Vec<_>>();
    order.sort_by(|a, b| scores[*b].total_cmp(&scores[*a]).then_with(|| a.cmp(b)));
    order.truncate(k);
    let denominator = order
        .iter()
        .map(|id| probabilities[*id])
        .sum::<f32>()
        .max(6.103515625e-5);
    let weights = order
        .iter()
        .map(|id| probabilities[*id] / denominator * scale)
        .collect();
    Ok((order, weights))
}

/// The layer feed-forward block: leading dense layers use the dense SwiGLU,
/// the rest route to `expert_top_k` experts and add the shared expert.
fn feed_forward(
    source: &mut impl TensorSource,
    backend: &mut impl MatvecBackend,
    model: &ModelConfig,
    layer: usize,
    fx: &[f32],
) -> Result<(Vec<f32>, Vec<usize>, Vec<f32>), String> {
    if layer < model.leading_dense_layers {
        let dense = swiglu(
            source,
            backend,
            &format!("blk.{layer}.ffn"),
            None,
            false,
            fx,
            model.dense_ffn,
            model.hidden,
            1.0,
        )?;
        return Ok((dense, Vec::new(), Vec::new()));
    }
    let logits = backend.matvec(
        "router",
        &source.matrix(
            &format!("blk.{layer}.ffn_gate_inp.weight"),
            model.expert_count,
            model.hidden,
        )?,
        fx,
    )?;
    let bias = source.vector(
        &format!("blk.{layer}.exp_probs_b.bias"),
        model.expert_count,
    )?;
    let (ids, weights) = route(&logits, &bias, model.expert_top_k, model.expert_weight_scale)?;
    let mut acc = vec![0.0_f32; model.hidden];
    for (&id, &weight) in ids.iter().zip(&weights) {
        let part = swiglu(
            source,
            backend,
            &format!("blk.{layer}.ffn"),
            Some(id),
            false,
            fx,
            model.expert_ffn,
            model.hidden,
            weight,
        )?;
        for (a, p) in acc.iter_mut().zip(part) {
            *a = (*a + p) as f32;
        }
    }
    let shared = swiglu(
        source,
        backend,
        &format!("blk.{layer}.ffn"),
        None,
        true,
        fx,
        model.expert_ffn,
        model.hidden,
        1.0,
    )?;
    for (a, p) in acc.iter_mut().zip(&shared) {
        *a = (*a + *p) as f32;
    }
    Ok((acc, ids, weights))
}

/// Rotate one `qk_rope`-sized slice in place at `position`.
pub fn rope(values: &mut [f32], position: usize, base: f32, pairing: RopePairing) {
    let n = values.len();
    let half = n / 2;
    for index in 0..half {
        let exponent = -2.0_f32 * index as f32 / n as f32;
        let theta = position as f32 * base.powf(exponent);
        let (sin, cos) = (theta.sin(), theta.cos());
        let (low, high) = match pairing {
            RopePairing::NeoxHalfSplit => (index, index + half),
            RopePairing::Interleaved => (2 * index, 2 * index + 1),
        };
        let (a, b) = (values[low], values[high]);
        values[low] = (a * cos - b * sin) as f32;
        values[high] = (a * sin + b * cos) as f32;
    }
}

fn softmax(scores: &[f32]) -> Result<Vec<f32>, String> {
    if scores.is_empty() {
        return Err("empty attention softmax".into());
    }
    let mut peak = f32::NEG_INFINITY;
    for value in scores {
        if !value.is_finite() {
            return Err("attention score nonfinite".into());
        }
        if *value > peak {
            peak = *value;
        }
    }
    let exponentials = scores
        .iter()
        .map(|value| (*value - peak).exp())
        .collect::<Vec<f32>>();
    let total = exponentials.iter().sum::<f32>();
    if !total.is_finite() || total <= 0.0 {
        return Err("attention softmax denominator".into());
    }
    Ok(exponentials
        .iter()
        .map(|value| (*value / total) as f32)
        .collect())
}

/// Per-step observation of the attention machinery this module owns.
pub trait TemporalObserver {
    fn attention(
        &mut self,
        _layer: usize,
        _position: usize,
        _visible_keys: usize,
        _first_head_weights: &[f32],
    ) -> Result<(), String> {
        Ok(())
    }
    fn routing(
        &mut self,
        _layer: usize,
        _position: usize,
        _selected_expert_ids: &[usize],
        _routing_weights: &[f32],
    ) -> Result<(), String> {
        Ok(())
    }
    fn step(
        &mut self,
        _position: usize,
        _token: u32,
        _logits: &[f32],
        _selected: u32,
    ) -> Result<(), String> {
        Ok(())
    }
}

pub struct NoopTemporalObserver;
impl TemporalObserver for NoopTemporalObserver {}

struct Attention {
    output: Vec<f32>,
}

#[allow(clippy::too_many_arguments)]
fn attention_for_layer(
    source: &mut impl TensorSource,
    backend: &mut impl MatvecBackend,
    config: &TemporalConfig,
    state: &SequenceState,
    observer: &mut impl TemporalObserver,
    layer: usize,
    position: usize,
    q: &[f32],
) -> Result<Attention, String> {
    let model = &config.model;
    let qdim = model.qk_nope + model.qk_rope;
    let visible = position + 1;
    let mut values = Vec::with_capacity(model.heads * model.value_dim);
    let mut first_head_weights = Vec::new();
    for head in 0..model.heads {
        let k_b = source.expert_matrix(
            &format!("blk.{layer}.attn_k_b.weight"),
            head,
            model.kv_rank,
            model.qk_nope,
        )?;
        let q_nope = &q[head * qdim..head * qdim + model.qk_nope];
        let latent_query = backend.matvec("attn_k_b", &k_b, q_nope)?;
        let mut rotated_query = q[head * qdim + model.qk_nope..(head + 1) * qdim].to_vec();
        rope(
            &mut rotated_query,
            position,
            model.rope_base,
            config.rope_pairing,
        );
        let mut scores = Vec::with_capacity(visible);
        for key in 0..visible {
            let latent = state.latent_at(layer, key);
            let rope_key = state.rope_key_at(layer, key);
            let mut score = 0.0_f32;
            for (a, b) in latent_query.iter().zip(latent) {
                score = (score + *a * *b) as f32;
            }
            for (a, b) in rotated_query.iter().zip(rope_key) {
                score = (score + *a * *b) as f32;
            }
            scores.push((score * config.attention_softmax_scale) as f32);
        }
        let weights = softmax(&scores)?;
        if head == 0 {
            first_head_weights = weights.clone();
        }
        // Absorbed form: weight the latents once, then project out.
        let mut aggregate = vec![0.0_f32; model.kv_rank];
        for (key, weight) in weights.iter().enumerate() {
            let latent = state.latent_at(layer, key);
            for (accumulator, value) in aggregate.iter_mut().zip(latent) {
                *accumulator = (*accumulator + *weight * *value) as f32;
            }
        }
        let v_b = source.expert_matrix(
            &format!("blk.{layer}.attn_v_b.weight"),
            head,
            model.value_dim,
            model.kv_rank,
        )?;
        values.extend(backend.matvec("attn_v_b", &v_b, &aggregate)?);
    }
    observer.attention(layer, position, visible, &first_head_weights)?;
    let output = backend.matvec(
        "attn_output",
        &source.matrix(
            &format!("blk.{layer}.attn_output.weight"),
            model.hidden,
            model.heads * model.value_dim,
        )?,
        &values,
    )?;
    Ok(Attention { output })
}

/// Execute one token at `position` against the retained state and append this
/// position's keys. On any failure the state is rolled back to its previous
/// committed extent.
pub fn execute_position(
    source: &mut impl TensorSource,
    backend: &mut impl MatvecBackend,
    config: &TemporalConfig,
    state: &mut SequenceState,
    token: u32,
    observer: &mut impl TemporalObserver,
) -> Result<(u32, Vec<f32>), String> {
    let outcome = execute_position_inner(source, backend, config, state, token, observer);
    if outcome.is_err() {
        state.rollback();
    }
    outcome
}

fn execute_position_inner(
    source: &mut impl TensorSource,
    backend: &mut impl MatvecBackend,
    config: &TemporalConfig,
    state: &mut SequenceState,
    token: u32,
    observer: &mut impl TemporalObserver,
) -> Result<(u32, Vec<f32>), String> {
    config.validate()?;
    let model = &config.model;
    if state.layer_count != model.layer_count
        || state.kv_rank != model.kv_rank
        || state.qk_rope != model.qk_rope
    {
        return Err("state does not belong to this configuration".into());
    }
    if token as usize >= model.vocab {
        return Err("token out of range".into());
    }
    let position = state.committed;
    if position >= config.max_positions {
        return Err("context overflow: max_positions reached".into());
    }
    if position >= config.indexer_top_k {
        return Err("context exceeds the indexer top-k budget".into());
    }
    let embedding = source.matrix("token_embd.weight", model.vocab, model.hidden)?;
    let mut x = embedding.values[token as usize * model.hidden..(token as usize + 1) * model.hidden]
        .to_vec();
    for layer in 0..model.layer_count {
        let attn_norm = source.vector(&format!("blk.{layer}.attn_norm.weight"), model.hidden)?;
        let xn = rms_norm(&x, &attn_norm, model.rms_epsilon)?;
        let qa = backend.matvec(
            "attn_q_a",
            &source.matrix(
                &format!("blk.{layer}.attn_q_a.weight"),
                model.q_rank,
                model.hidden,
            )?,
            &xn,
        )?;
        let qan = rms_norm(
            &qa,
            &source.vector(&format!("blk.{layer}.attn_q_a_norm.weight"), model.q_rank)?,
            model.rms_epsilon,
        )?;
        let qdim = model.qk_nope + model.qk_rope;
        let q = backend.matvec(
            "attn_q_b",
            &source.matrix(
                &format!("blk.{layer}.attn_q_b.weight"),
                model.heads * qdim,
                model.q_rank,
            )?,
            &qan,
        )?;
        let kv = backend.matvec(
            "attn_kv_a",
            &source.matrix(
                &format!("blk.{layer}.attn_kv_a_mqa.weight"),
                model.kv_rank + model.qk_rope,
                model.hidden,
            )?,
            &xn,
        )?;
        let kvn = rms_norm(
            &kv[..model.kv_rank],
            &source.vector(
                &format!("blk.{layer}.attn_kv_a_norm.weight"),
                model.kv_rank,
            )?,
            model.rms_epsilon,
        )?;
        let mut rope_key = kv[model.kv_rank..].to_vec();
        rope(
            &mut rope_key,
            position,
            model.rope_base,
            config.rope_pairing,
        );
        // The current token is visible to its own query: append before the
        // softmax, never after.
        state.append(layer, &kvn, &rope_key)?;
        let attention =
            attention_for_layer(source, backend, config, state, observer, layer, position, &q)?;
        x = residual(&x, &attention.output)?;
        let ffn_norm = source.vector(&format!("blk.{layer}.ffn_norm.weight"), model.hidden)?;
        let fx = rms_norm(&x, &ffn_norm, model.rms_epsilon)?;
        let (ffn, selected_ids, routing_weights) = feed_forward(source, backend, model, layer, &fx)?;
        observer.routing(layer, position, &selected_ids, &routing_weights)?;
        x = residual(&x, &ffn)?;
    }
    state.commit()?;
    let normalized = rms_norm(
        &x,
        &source.vector("output_norm.weight", model.hidden)?,
        model.rms_epsilon,
    )?;
    let logits = backend.matvec(
        "output",
        &source.matrix("output.weight", model.vocab, model.hidden)?,
        &normalized,
    )?;
    let selected = argmax(&logits)?;
    observer.step(position, token, &logits, selected)?;
    Ok((selected, logits))
}

/// Comparator: execute the whole prefix with no retained state, rebuilding
/// every key from the token history at each step. Slower by construction and
/// never the production path; it exists so the cached path can be checked
/// against an implementation that cannot carry a stale cache.
pub fn execute_prefix_no_cache(
    source: &mut impl TensorSource,
    backend: &mut impl MatvecBackend,
    config: &TemporalConfig,
    tokens: &[u32],
) -> Result<(u32, Vec<f32>), String> {
    if tokens.is_empty() {
        return Err("empty prefix".into());
    }
    let mut last = None;
    for length in 1..=tokens.len() {
        let mut state = SequenceState::new(config);
        let mut observer = NoopTemporalObserver;
        let mut step = None;
        for token in &tokens[..length] {
            step = Some(execute_position(
                source,
                backend,
                config,
                &mut state,
                *token,
                &mut observer,
            )?);
        }
        last = step;
    }
    last.ok_or_else(|| "no step executed".into())
}

/// Matrix helper kept next to the state so fixtures can build one.
pub fn matrix(rows: usize, columns: usize, values: Vec<f32>) -> Matrix {
    Matrix {
        rows,
        columns,
        values,
    }
}

// ----------------------------------------------------------------- fixtures

/// A committed tiny multi-position fixture. Like [`crate::synthetic`], it
/// carries only synthetic numbers and has no path, file, environment or
/// checkpoint API; unlike it, it names a whole token sequence.
#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TemporalFixture {
    pub schema: String,
    pub seed: u64,
    pub config: TemporalConfig,
    pub tokens: Vec<u32>,
    pub vectors: std::collections::BTreeMap<String, Vec<f32>>,
    pub matrices: std::collections::BTreeMap<String, crate::synthetic::MatrixFixture>,
    pub expert_matrices: Vec<crate::synthetic::ExpertFixture>,
}

pub const TEMPORAL_FIXTURE_SCHEMA: &str =
    "pulsarmlx.f017.native-temporal-differential-fixture/1.0.0";
pub const TEMPORAL_FIXTURE_SEEDS: std::ops::RangeInclusive<u64> = 17030..=17035;

pub struct TemporalSource {
    vectors: std::collections::BTreeMap<String, Vec<f32>>,
    matrices: std::collections::BTreeMap<String, Matrix>,
    experts: std::collections::BTreeMap<(String, usize), Matrix>,
}

impl TemporalSource {
    pub fn from_fixture(fixture: TemporalFixture) -> Result<(Self, TemporalConfig, Vec<u32>), String> {
        if fixture.schema != TEMPORAL_FIXTURE_SCHEMA
            || !TEMPORAL_FIXTURE_SEEDS.contains(&fixture.seed)
        {
            return Err("temporal fixture authority".into());
        }
        fixture.config.validate()?;
        if fixture.tokens.is_empty() || fixture.tokens.len() > fixture.config.max_positions {
            return Err("temporal fixture token count".into());
        }
        let matrices = fixture
            .matrices
            .into_iter()
            .map(|(name, m)| {
                (
                    name,
                    Matrix {
                        rows: m.rows,
                        columns: m.columns,
                        values: m.values,
                    },
                )
            })
            .collect();
        let experts = fixture
            .expert_matrices
            .into_iter()
            .map(|e| {
                (
                    (e.name, e.expert),
                    Matrix {
                        rows: e.matrix.rows,
                        columns: e.matrix.columns,
                        values: e.matrix.values,
                    },
                )
            })
            .collect();
        Ok((
            Self {
                vectors: fixture.vectors,
                matrices,
                experts,
            },
            fixture.config,
            fixture.tokens,
        ))
    }
}

impl TensorSource for TemporalSource {
    fn vector(&mut self, name: &str, length: usize) -> Result<Vec<f32>, String> {
        let value = self
            .vectors
            .get(name)
            .ok_or_else(|| format!("missing {name}"))?
            .clone();
        if value.len() != length {
            return Err(format!("shape {name}"));
        }
        Ok(value)
    }
    fn matrix(&mut self, name: &str, rows: usize, columns: usize) -> Result<Matrix, String> {
        let value = self
            .matrices
            .get(name)
            .ok_or_else(|| format!("missing {name}"))?
            .clone();
        if value.rows != rows || value.columns != columns {
            return Err(format!("shape {name}"));
        }
        Ok(value)
    }
    fn expert_matrix(
        &mut self,
        name: &str,
        expert: usize,
        rows: usize,
        columns: usize,
    ) -> Result<Matrix, String> {
        let value = self
            .experts
            .get(&(name.to_owned(), expert))
            .ok_or_else(|| format!("missing {name}[{expert}]"))?
            .clone();
        if value.rows != rows || value.columns != columns {
            return Err(format!("shape {name}"));
        }
        Ok(value)
    }
}
