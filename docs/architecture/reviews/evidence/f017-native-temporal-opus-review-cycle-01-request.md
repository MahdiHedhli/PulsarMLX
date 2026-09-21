# Independent review request — F017 native temporal runtime, text CLI, and the V11 active-measurement repair

You are an independent reviewer. You have no tools: judge only from the text below.
Return a single JSON object and nothing else:

{"verdict":"ACCEPT|REJECT","blocking":[{"claim":"...","problem":"...","evidence":"..."}],
 "non_blocking":[{"observation":"...","why_it_matters":"..."}],
 "claims_checked":N,"claims_refuted":N}

REJECT if any load-bearing claim below is false, overstated, or unsupported by
the source shown. Non-blocking observations do not force REJECT.

## Context you must hold

- A previous, human-gated one-shot executed the real GLM-5.2 checkpoint and produced
  token 154820 == the expected token. That authorization is CONSUMED; nothing here
  replays it. The frozen one-token producer `execute_one_token` in `model.rs` is
  sha-bound by that consumed contract and MUST remain byte-identical.
- `execute_one_token` is position zero with a SINGLE visible attention key: its
  softmax has one element and RoPE is the identity at position 0. Looping it is
  NOT autoregressive generation. The work under review adds the missing machinery.
- The checkpoint is `glm-dsa`: MLA (absorbed form) plus a DeepSeek-style sparse
  indexer. Metadata: heads 64, qk_nope 192, qk_rope 64, v_dim 256, kv_lora 512,
  q_lora 2048, 79 layers, 256 experts top-8 + 1 shared, 3 leading dense layers,
  rope base 8e6, vocab 154880, attention.indexer.top_k 2048.

## The claims to check

C1. The temporal module implements absorbed-MLA causal attention correctly:
    score_j = (W_kb[h] q_nope) . c_j + rope(q_rope, i) . k_rope_j, scaled by
    attention_softmax_scale; softmax over j = 0..i; the value path aggregates the
    weighted latent ONCE and then applies W_vb[h].
C2. The current token is visible to its own query (appended before the softmax).
C3. At position 0 the temporal path reduces EXACTLY to the frozen one-token
    producer (RoPE identity, softmax of one element = 1, aggregate = c_0).
C4. Retained state is per layer, per position: (normalised latent, rotated rope key).
    A failed step rolls back to the last committed position.
C5. The sparse indexer is NOT implemented, and the runtime REFUSES sequences longer
    than indexer_top_k rather than silently substituting dense attention.
C6. The softmax scale is 1/sqrt(qk_nope + qk_rope) and is taken from the
    configuration, not hardcoded.
C7. The rope pairing is a DECLARED parameter (NeoxHalfSplit default, Interleaved
    alternative), not a validated fact about the checkpoint, and the code says so.
C8. The Python reference is INDEPENDENT: it does not call the Rust code and does not
    delegate its attention or state computation to the code under test.
C9. The V11 repair separates historical verification of the frozen v8 record
    (against its own head) from current-worktree verification, never rewrites v8,
    cannot silently widen its measured path set, and does not use any skip,
    path removal, swallowed exception or evidence-only reclassification.
C10. The session layer counts a terminal stop token as generated but never writes it
    to the answer stream, and reports no decode rate below two generated tokens.
C11. Nothing here mints authority, replays the consumed one-shot, or claims a
    real-checkpoint multi-token result.

## Source under review


### crates/f017-native/src/temporal.rs
```
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
```

### crates/f017-native/src/session.rs
```
//! Bounded generation session: prefill, decode, stop semantics, incremental
//! detokenisation and phase timing, over any [`TensorSource`].
//!
//! The session owns no files and no tokenizer. The CLI supplies a real
//! checkpoint and a real GGUF tokenizer; the tests supply a tiny synthetic
//! model and a toy vocabulary, so the generation contract is exercised
//! without a checkpoint. Checkpoint verification is deliberately outside:
//! it happens once per session, before any of this runs, and is timed and
//! reported separately.

use crate::model::{MatvecBackend, TensorSource};
use crate::temporal::{execute_position, SequenceState, TemporalConfig, TemporalObserver};
use serde::Serialize;
use sha2::{Digest, Sha256};
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::Instant;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum FinishReason {
    /// The model emitted a token in the stop set.
    Stop,
    /// `max_output_tokens` was reached first.
    Length,
    /// The caller cancelled between positions.
    Cancelled,
}

#[derive(Clone, Copy, Debug)]
pub struct Limits {
    pub max_prompt_tokens: usize,
    pub max_output_tokens: usize,
}

impl Limits {
    pub fn validate(&self, config: &TemporalConfig) -> Result<(), String> {
        if self.max_prompt_tokens == 0 || self.max_output_tokens == 0 {
            return Err("limits must be positive".into());
        }
        if self
            .max_prompt_tokens
            .checked_add(self.max_output_tokens)
            .ok_or("limit overflow")?
            > config.max_positions
        {
            return Err(
                "max_prompt_tokens + max_output_tokens exceeds the runtime's max_positions".into(),
            );
        }
        Ok(())
    }
}

/// Everything the caller needs to report the run honestly.
#[derive(Clone, Debug, Serialize)]
pub struct Outcome {
    pub prompt_tokens: usize,
    pub generated_tokens: Vec<u32>,
    pub generated_token_count: usize,
    pub finish_reason: FinishReason,
    pub stop_token: Option<u32>,
    /// Seconds to process the prompt, excluding checkpoint verification.
    pub prefill_seconds: f64,
    /// Seconds from the end of prefill to the first generated token.
    pub first_token_seconds: f64,
    /// Seconds spent producing generated tokens after the first.
    pub decode_seconds: f64,
    /// One entry per executed position, prompt positions first.
    pub position_seconds: Vec<f64>,
    /// The argmax at each executed position. Prompt positions are teacher
    /// forced, so only the last one's entry becomes a generated token; the
    /// earlier entries are what the model would have continued with.
    pub position_selected_tokens: Vec<u32>,
    /// SHA-256 of each position's full f32 logit vector, little-endian, so a
    /// run can be compared with banked evidence without shipping the vector.
    pub position_logits_sha256: Vec<String>,
    pub peak_state_bytes: usize,
    pub positions_executed: usize,
}

impl Outcome {
    /// Tokens per second over the declared decode interval, or `None` when
    /// fewer than two tokens were generated: one token has no interval and
    /// its reciprocal is not a decode rate.
    pub fn decode_tokens_per_second(&self) -> Option<f64> {
        if self.generated_token_count < 2 || self.decode_seconds <= 0.0 {
            return None;
        }
        Some((self.generated_token_count - 1) as f64 / self.decode_seconds)
    }
}

pub trait StopSet {
    fn is_stop(&self, token: u32) -> bool;
}

impl StopSet for Vec<u32> {
    fn is_stop(&self, token: u32) -> bool {
        self.contains(&token)
    }
}

/// Emits only complete UTF-8, so a multi-byte character split across two
/// tokens is never written as replacement bytes.
pub struct IncrementalText<F: FnMut(&[u32]) -> Vec<u8>> {
    decode_all: F,
    tokens: Vec<u32>,
    emitted: usize,
}

impl<F: FnMut(&[u32]) -> Vec<u8>> IncrementalText<F> {
    pub fn new(decode_all: F) -> Self {
        Self {
            decode_all,
            tokens: Vec::new(),
            emitted: 0,
        }
    }
    /// Append one token and return the bytes that are now safe to show.
    pub fn push(&mut self, token: u32) -> Vec<u8> {
        self.tokens.push(token);
        let bytes = (self.decode_all)(&self.tokens);
        let complete = complete_utf8_prefix(&bytes);
        if complete <= self.emitted {
            return Vec::new();
        }
        let chunk = bytes[self.emitted..complete].to_vec();
        self.emitted = complete;
        chunk
    }
    /// Bytes still held back because they are an incomplete character.
    pub fn flush(&mut self) -> Vec<u8> {
        let bytes = (self.decode_all)(&self.tokens);
        let chunk = bytes[self.emitted.min(bytes.len())..].to_vec();
        self.emitted = bytes.len();
        chunk
    }
}

/// Length of the longest prefix of `bytes` that is valid UTF-8 ending on a
/// character boundary.
pub fn complete_utf8_prefix(bytes: &[u8]) -> usize {
    match std::str::from_utf8(bytes) {
        Ok(_) => bytes.len(),
        Err(error) => {
            if error.error_len().is_some() {
                // A genuine encoding error, not a truncation: everything up to
                // it is complete and the invalid byte is the caller's problem.
                error.valid_up_to()
            } else {
                error.valid_up_to()
            }
        }
    }
}

struct PeakState {
    peak: usize,
}
impl TemporalObserver for PeakState {}

fn logits_sha256(logits: &[f32]) -> String {
    let mut digest = Sha256::new();
    for value in logits {
        digest.update(value.to_bits().to_le_bytes());
    }
    format!("{:x}", digest.finalize())
}

/// Run one bounded generation. `sink` receives decoded bytes as they become
/// safe to show; it is never called for prompt tokens.
#[allow(clippy::too_many_arguments)]
pub fn generate<F: FnMut(&[u32]) -> Vec<u8>>(
    source: &mut impl TensorSource,
    backend: &mut impl MatvecBackend,
    config: &TemporalConfig,
    state: &mut SequenceState,
    prompt: &[u32],
    limits: Limits,
    stops: &impl StopSet,
    text: &mut IncrementalText<F>,
    sink: &mut impl FnMut(&[u8]),
    cancel: &AtomicBool,
) -> Result<Outcome, String> {
    limits.validate(config)?;
    if prompt.is_empty() {
        return Err("empty prompt".into());
    }
    if prompt.len() > limits.max_prompt_tokens {
        return Err(format!(
            "prompt of {} tokens exceeds max_prompt_tokens {}",
            prompt.len(),
            limits.max_prompt_tokens
        ));
    }
    if state.positions() != 0 {
        return Err("generation requires a fresh state".into());
    }
    let mut observer = PeakState { peak: 0 };
    let mut position_seconds = Vec::new();
    let mut position_selected_tokens = Vec::new();
    let mut position_logits_sha256 = Vec::new();
    let mut next = None;

    let prefill_start = Instant::now();
    for token in prompt {
        if cancel.load(Ordering::Relaxed) {
            return Ok(Outcome {
                prompt_tokens: prompt.len(),
                generated_tokens: Vec::new(),
                generated_token_count: 0,
                finish_reason: FinishReason::Cancelled,
                stop_token: None,
                prefill_seconds: prefill_start.elapsed().as_secs_f64(),
                first_token_seconds: 0.0,
                decode_seconds: 0.0,
                position_seconds,
                position_selected_tokens,
                position_logits_sha256,
                peak_state_bytes: state.state_bytes(),
                positions_executed: state.positions(),
            });
        }
        let step = Instant::now();
        let (selected, logits) =
            execute_position(source, backend, config, state, *token, &mut observer)?;
        position_seconds.push(step.elapsed().as_secs_f64());
        position_selected_tokens.push(selected);
        position_logits_sha256.push(logits_sha256(&logits));
        observer.peak = observer.peak.max(state.state_bytes());
        next = Some(selected);
    }
    let prefill_seconds = prefill_start.elapsed().as_secs_f64();

    let mut generated = Vec::new();
    let mut finish = FinishReason::Length;
    let mut stop_token = None;
    let mut first_token_seconds = 0.0;
    let decode_start = Instant::now();
    let mut after_first = Instant::now();
    while generated.len() < limits.max_output_tokens {
        let token = next.ok_or("no continuation token")?;
        if generated.is_empty() {
            first_token_seconds = decode_start.elapsed().as_secs_f64();
        }
        generated.push(token);
        if stops.is_stop(token) {
            finish = FinishReason::Stop;
            stop_token = Some(token);
            break;
        }
        sink(&text.push(token));
        if generated.len() == limits.max_output_tokens {
            break;
        }
        if cancel.load(Ordering::Relaxed) {
            finish = FinishReason::Cancelled;
            break;
        }
        if generated.len() == 1 {
            after_first = Instant::now();
        }
        let step = Instant::now();
        let (selected, logits) =
            execute_position(source, backend, config, state, token, &mut observer)?;
        position_seconds.push(step.elapsed().as_secs_f64());
        position_selected_tokens.push(selected);
        position_logits_sha256.push(logits_sha256(&logits));
        observer.peak = observer.peak.max(state.state_bytes());
        next = Some(selected);
    }
    let decode_seconds = if generated.len() > 1 {
        after_first.elapsed().as_secs_f64()
    } else {
        0.0
    };
    sink(&text.flush());
    Ok(Outcome {
        prompt_tokens: prompt.len(),
        generated_token_count: generated.len(),
        generated_tokens: generated,
        finish_reason: finish,
        stop_token,
        prefill_seconds,
        first_token_seconds,
        decode_seconds,
        position_seconds,
        position_selected_tokens,
        position_logits_sha256,
        peak_state_bytes: observer.peak,
        positions_executed: state.positions(),
    })
}
```

### scripts/research/f017_temporal_reference_v1.py
```
#!/usr/bin/env python3
"""Independent multi-position reference for the native stateful decoder.

This is a second implementation, not a wrapper: it builds its own key/value
history, its own rotary embedding and its own causal softmax in binary64 and
never calls the Rust runtime. The only things it shares with the producer are
the fixture bytes and the declared semantics:

* absorbed MLA -- `attn_k_b[h]` maps this head's `q_nope` into the latent
  space, `attn_v_b[h]` maps the attention-weighted latent back out;
* the score of key `j` for query position `i` is
  `(W_kb q_nope) . c_j + rope(q_rope, i) . rope(k_rope_j, j)`, scaled by
  `attention_softmax_scale`;
* every key `j <= i` is visible and the current key is included;
* sigmoid routing with an additive bias, top-k by score with a low-id tie
  break, weights renormalised over the selected probabilities and scaled.

It deliberately keeps the whole prefix and recomputes the attention over it
from the stored keys at every position, so a producer bug that drops, reuses
or misorders history cannot be reproduced here by construction.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def rms_norm(x, scale, epsilon):
    total = sum(value * value for value in x)
    inverse = 1.0 / math.sqrt(total / len(x) + epsilon)
    return [value * inverse * weight for value, weight in zip(x, scale)]


def matvec(matrix, vector):
    rows, columns, values = matrix["rows"], matrix["columns"], matrix["values"]
    if len(vector) != columns:
        raise ValueError("matvec shape")
    return [sum(values[row * columns + column] * vector[column] for column in range(columns))
            for row in range(rows)]


def silu(value):
    return value / (1.0 + math.exp(-value))


def rope(values, position, base, pairing):
    n = len(values)
    half = n // 2
    out = list(values)
    for index in range(half):
        theta = position * base ** (-2.0 * index / n)
        sin, cos = math.sin(theta), math.cos(theta)
        low, high = (index, index + half) if pairing == "neox_half_split" else (2 * index, 2 * index + 1)
        a, b = values[low], values[high]
        out[low] = a * cos - b * sin
        out[high] = a * sin + b * cos
    return out


def softmax(scores):
    peak = max(scores)
    exponentials = [math.exp(score - peak) for score in scores]
    total = sum(exponentials)
    return [value / total for value in exponentials]


class Fixture:
    def __init__(self, document: dict):
        self.config = document["config"]
        self.model = self.config["model"]
        self.tokens = document["tokens"]
        self.seed = document["seed"]
        self.vectors = document["vectors"]
        self.matrices = document["matrices"]
        self.experts = {(item["name"], item["expert"]): item["matrix"] for item in document["expert_matrices"]}

    def vector(self, name, length):
        value = self.vectors[name]
        if len(value) != length:
            raise ValueError(f"shape {name}")
        return value

    def matrix(self, name, rows, columns):
        value = self.matrices[name]
        if value["rows"] != rows or value["columns"] != columns:
            raise ValueError(f"shape {name}")
        return value

    def expert(self, name, expert, rows, columns):
        value = self.experts[(name, expert)]
        if value["rows"] != rows or value["columns"] != columns:
            raise ValueError(f"shape {name}")
        return value


def swiglu(fixture, prefix, expert, shared, x, inner, hidden, weight):
    def projection(suffix, rows, columns):
        if expert is not None:
            return fixture.expert(f"{prefix}_{suffix}_exps.weight", expert, rows, columns)
        if shared:
            return fixture.matrix(f"{prefix}_{suffix}_shexp.weight", rows, columns)
        return fixture.matrix(f"{prefix}_{suffix}.weight", rows, columns)

    gate = matvec(projection("gate", inner, len(x)), x)
    up = matvec(projection("up", inner, len(x)), x)
    product = [silu(g) * u * weight for g, u in zip(gate, up)]
    return matvec(projection("down", hidden, inner), product)


def route(logits, bias, k, scale):
    probabilities = [1.0 / (1.0 + math.exp(-value)) for value in logits]
    scores = [p + b for p, b in zip(probabilities, bias)]
    order = sorted(range(len(scores)), key=lambda index: (-scores[index], index))[:k]
    denominator = max(sum(probabilities[index] for index in order), 6.103515625e-5)
    return order, [probabilities[index] / denominator * scale for index in order]


def feed_forward(fixture, model, layer, fx):
    if layer < model["leading_dense_layers"]:
        return swiglu(fixture, f"blk.{layer}.ffn", None, False, fx, model["dense_ffn"], model["hidden"], 1.0), []
    logits = matvec(fixture.matrix(f"blk.{layer}.ffn_gate_inp.weight", model["expert_count"], model["hidden"]), fx)
    bias = fixture.vector(f"blk.{layer}.exp_probs_b.bias", model["expert_count"])
    ids, weights = route(logits, bias, model["expert_top_k"], model["expert_weight_scale"])
    accumulator = [0.0] * model["hidden"]
    for identifier, weight in zip(ids, weights):
        part = swiglu(fixture, f"blk.{layer}.ffn", identifier, False, fx, model["expert_ffn"], model["hidden"], weight)
        accumulator = [a + p for a, p in zip(accumulator, part)]
    shared = swiglu(fixture, f"blk.{layer}.ffn", None, True, fx, model["expert_ffn"], model["hidden"], 1.0)
    return [a + s for a, s in zip(accumulator, shared)], ids


def execute(fixture: Fixture) -> list[dict]:
    model = fixture.model
    scale = fixture.config["attention_softmax_scale"]
    pairing = fixture.config["rope_pairing"]
    qdim = model["qk_nope"] + model["qk_rope"]
    # This reference keeps the entire history explicitly and never mutates a
    # previous entry: history[layer] is a list of (latent, rotated rope key).
    history: list[list[tuple[list[float], list[float]]]] = [[] for _ in range(model["layer_count"])]
    embedding = fixture.matrix("token_embd.weight", model["vocab"], model["hidden"])
    steps = []
    for position, token in enumerate(fixture.tokens):
        if token >= model["vocab"]:
            raise ValueError("token out of range")
        x = embedding["values"][token * model["hidden"]:(token + 1) * model["hidden"]]
        first_head_weights: list[float] = []
        selected_expert_ids = []
        for layer in range(model["layer_count"]):
            xn = rms_norm(x, fixture.vector(f"blk.{layer}.attn_norm.weight", model["hidden"]), model["rms_epsilon"])
            qa = matvec(fixture.matrix(f"blk.{layer}.attn_q_a.weight", model["q_rank"], model["hidden"]), xn)
            qan = rms_norm(qa, fixture.vector(f"blk.{layer}.attn_q_a_norm.weight", model["q_rank"]), model["rms_epsilon"])
            q = matvec(fixture.matrix(f"blk.{layer}.attn_q_b.weight", model["heads"] * qdim, model["q_rank"]), qan)
            kv = matvec(fixture.matrix(f"blk.{layer}.attn_kv_a_mqa.weight", model["kv_rank"] + model["qk_rope"], model["hidden"]), xn)
            latent = rms_norm(kv[:model["kv_rank"]], fixture.vector(f"blk.{layer}.attn_kv_a_norm.weight", model["kv_rank"]), model["rms_epsilon"])
            rope_key = rope(kv[model["kv_rank"]:], position, model["rope_base"], pairing)
            history[layer].append((latent, rope_key))
            if len(history[layer]) != position + 1:
                raise ValueError("history append order")
            values = []
            for head in range(model["heads"]):
                k_b = fixture.expert(f"blk.{layer}.attn_k_b.weight", head, model["kv_rank"], model["qk_nope"])
                q_nope = q[head * qdim:head * qdim + model["qk_nope"]]
                latent_query = matvec(k_b, q_nope)
                rotated_query = rope(q[head * qdim + model["qk_nope"]:(head + 1) * qdim], position, model["rope_base"], pairing)
                scores = []
                for key_latent, key_rope in history[layer]:
                    score = sum(a * b for a, b in zip(latent_query, key_latent))
                    score += sum(a * b for a, b in zip(rotated_query, key_rope))
                    scores.append(score * scale)
                weights = softmax(scores)
                if head == 0 and layer == 0:
                    first_head_weights = weights
                aggregate = [0.0] * model["kv_rank"]
                for weight, (key_latent, _) in zip(weights, history[layer]):
                    aggregate = [a + weight * value for a, value in zip(aggregate, key_latent)]
                v_b = fixture.expert(f"blk.{layer}.attn_v_b.weight", head, model["value_dim"], model["kv_rank"])
                values.extend(matvec(v_b, aggregate))
            attention = matvec(fixture.matrix(f"blk.{layer}.attn_output.weight", model["hidden"], model["heads"] * model["value_dim"]), values)
            x = [a + b for a, b in zip(x, attention)]
            fx = rms_norm(x, fixture.vector(f"blk.{layer}.ffn_norm.weight", model["hidden"]), model["rms_epsilon"])
            ffn, ids = feed_forward(fixture, model, layer, fx)
            # Dense layers contribute an empty selection, so the per-layer
            # list stays aligned with the layer index in both implementations.
            selected_expert_ids.append(ids)
            x = [a + b for a, b in zip(x, ffn)]
        normalized = rms_norm(x, fixture.vector("output_norm.weight", model["hidden"]), model["rms_epsilon"])
        logits = matvec(fixture.matrix("output.weight", model["vocab"], model["hidden"]), normalized)
        selected = max(range(len(logits)), key=lambda index: (logits[index], -index))
        steps.append({
            "position": position,
            "token": token,
            "selected_token": selected,
            "visible_keys": position + 1,
            "first_head_attention_weights": first_head_weights,
            "selected_expert_ids": selected_expert_ids,
            "logits": logits,
        })
    return steps


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args(argv)
    document = json.loads(arguments.fixture.read_text())
    fixture = Fixture(document)
    result = {
        "schema": "pulsarmlx.f017.native-temporal-reference-result/1.0.0",
        "seed": fixture.seed,
        "implementation": "independent binary64 python reference",
        "original_checkpoint_reads": 0,
        "tokens": fixture.tokens,
        "steps": execute(fixture),
    }
    raw = json.dumps(result)
    if arguments.output:
        arguments.output.write_text(raw + "\n")
    else:
        print(raw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

### scripts/research/generate_f017_v11_measurement_v2.py
```
#!/usr/bin/env python3
"""Active V11 implementation measurement (v9).

Two verifications that the v1 generator conflated into one:

* HISTORICAL — the frozen v8 record still describes its own head exactly.
  Every measured path's Git blob at ``implementation_head`` must carry the
  blob id and SHA-256 that v8 recorded, and the head's tree must be the tree
  v8 recorded. This keeps v8's meaning verifiable forever without pinning the
  working tree to a September 3 state.
* CURRENT — the checked-out working tree equals the Git objects at the head
  being measured, and the resulting v9 record inventories those bytes.

The measured path set is taken from the predecessor rather than restated
here, so the active measurement cannot silently widen its own scope; a set
digest is asserted against the constant below.

A v9 record inventories bytes. It does not ratify the behaviour of any body
that changed since v8: the reviewed change set is bound by ``review``.
No checkpoint is opened and no authority is minted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "docs/architecture/reviews/evidence/f017-v11-result-envelope-implementation-measurement-v9.json"
PREDECESSOR = ROOT / "docs/architecture/reviews/evidence/f017-v11-result-envelope-implementation-measurement-v8.json"
REVIEW = ROOT / "docs/architecture/reviews/f017-v11-active-measurement-repair-20260920.md"

SCHEMA = "pulsarmlx.f017.v11-result-envelope-implementation-measurement/9.0.0"
PREDECESSOR_SCHEMA = "pulsarmlx.f017.v11-result-envelope-implementation-measurement/8.0.0"
PREDECESSOR_SHA256 = "c529221a53a338dfe57d65f855f1b9d9b11e0b0251562f84067a65a0538a6414"
PREDECESSOR_HEAD = "f35d341110c67377200ad353ab56a3cf38615a73"
PREDECESSOR_TREE = "08864e7d529c91c0ec8f4bf9661006503e6d7dc9"
# sha256 of "\n".join(sorted(paths)) + "\n" over v8's 36 measured paths.
MEASURED_PATH_SET_SHA256 = "6ddd0dcc0f410e982525d84dc88bbf6c43a6ee5343f92bb65c5b34c553d8b951"
MEASURED_PATH_COUNT = 36
# The scientific numerical authority. These bodies must never drift under a
# measurement refresh; a v9 that reports them as changed is a stop, not a
# re-baseline.
NUMERICAL_CORE_PATHS = (
    "scripts/research/f017_corrected_oracle_primary_numerics_v3.py",
    "scripts/research/f017_corrected_oracle_secondary_numerics_v3.py",
)
BRANCH = "feat/017-rust-native-inference-runtime"


class MeasurementError(RuntimeError):
    """Raised after the complete report has been emitted."""


def path_set_sha256(paths) -> str:
    return hashlib.sha256(("\n".join(sorted(paths)) + "\n").encode()).hexdigest()


class GitReader:
    """The only process boundary; tests substitute a fake."""

    def __init__(self, root: Path = ROOT):
        self.root = root

    def text(self, *arguments: str) -> str:
        return subprocess.check_output(["git", *arguments], cwd=self.root, text=True).strip()

    def blob(self, head: str, path: str) -> bytes:
        return subprocess.check_output(["git", "show", f"{head}:{path}"], cwd=self.root)

    def blob_id(self, head: str, path: str) -> str:
        return self.text("rev-parse", f"{head}:{path}")

    def tree(self, head: str) -> str:
        return self.text("rev-parse", f"{head}^{{tree}}")

    def head(self) -> str:
        return self.text("rev-parse", "HEAD")

    def commits_touching(self, since: str, until: str, path: str):
        raw = subprocess.check_output(
            ["git", "log", "--reverse", "--format=%H%x00%s", f"{since}..{until}", "--", path],
            cwd=self.root, text=True,
        ).strip()
        out = []
        for line in raw.splitlines():
            if not line:
                continue
            commit, _, subject = line.partition("\x00")
            out.append({"commit": commit, "subject": subject})
        return out


def read_file(path: str) -> bytes:
    return (ROOT / path).read_bytes()


def load_predecessor(raw: bytes) -> dict:
    """Parse and structurally bind v8. Never mutated, never regenerated."""
    findings = []
    if hashlib.sha256(raw).hexdigest() != PREDECESSOR_SHA256:
        findings.append({"control": "PREDECESSOR_BYTES", "detail": "v8 sha256 does not match the bound constant"})
    record = json.loads(raw)
    if record.get("schema") != PREDECESSOR_SCHEMA:
        findings.append({"control": "PREDECESSOR_SCHEMA", "detail": f"schema {record.get('schema')!r}"})
    if record.get("implementation_head") != PREDECESSOR_HEAD:
        findings.append({"control": "PREDECESSOR_HEAD", "detail": f"head {record.get('implementation_head')!r}"})
    if record.get("implementation_tree") != PREDECESSOR_TREE:
        findings.append({"control": "PREDECESSOR_TREE", "detail": f"tree {record.get('implementation_tree')!r}"})
    paths = [item["path"] for item in record.get("measured_paths", [])]
    if len(paths) != MEASURED_PATH_COUNT or record.get("measured_path_count") != MEASURED_PATH_COUNT:
        findings.append({"control": "MEASURED_PATH_COUNT", "detail": f"{len(paths)} paths"})
    if len(set(paths)) != len(paths):
        findings.append({"control": "MEASURED_PATH_SET", "detail": "duplicate measured path"})
    if path_set_sha256(paths) != MEASURED_PATH_SET_SHA256:
        findings.append({"control": "SOURCE_SET_WIDENED_WITHOUT_APPROVAL",
                         "detail": f"path-set digest {path_set_sha256(paths)}"})
    if record.get("original_checkpoint_access") != 0:
        findings.append({"control": "PREDECESSOR_CHECKPOINT_ACCESS", "detail": "non-zero"})
    return {"record": record, "paths": paths, "findings": findings}


def measure(git: GitReader, reader, head: str, predecessor: dict) -> dict:
    """Produce the complete report. Assertions belong to verify()."""
    record = predecessor["record"]
    paths = predecessor["paths"]
    findings = list(predecessor["findings"])
    predecessor_by_path = {item["path"]: item for item in record["measured_paths"]}

    historical = []
    for path in paths:
        expected = predecessor_by_path[path]
        entry = {"path": path}
        try:
            blob_id = git.blob_id(PREDECESSOR_HEAD, path)
            raw = git.blob(PREDECESSOR_HEAD, path)
        except Exception as error:  # missing object at the frozen head
            entry.update(result="UNREADABLE", detail=str(error))
            findings.append({"control": "HISTORICAL_OBJECT_MISSING", "detail": path})
            historical.append(entry)
            continue
        digest = hashlib.sha256(raw).hexdigest()
        entry.update(git_blob_sha=blob_id, sha256=digest,
                     result="MATCH" if (blob_id == expected["git_blob_sha"] and digest == expected["sha256"]) else "MISMATCH")
        if entry["result"] == "MISMATCH":
            findings.append({"control": "HISTORICAL_DRIFT", "detail":
                             f"{path}: v8 recorded {expected['sha256'][:12]}, head {PREDECESSOR_HEAD[:8]} now carries {digest[:12]}"})
        historical.append(entry)
    historical_tree = None
    try:
        historical_tree = git.tree(PREDECESSOR_HEAD)
    except Exception as error:
        findings.append({"control": "HISTORICAL_HEAD_MISSING", "detail": str(error)})
    if historical_tree is not None and historical_tree != PREDECESSOR_TREE:
        findings.append({"control": "HISTORICAL_TREE", "detail": f"{PREDECESSOR_HEAD} tree is {historical_tree}"})

    current = []
    drift = []
    for path in paths:
        entry = {"path": path}
        try:
            blob_id = git.blob_id(head, path)
            raw = git.blob(head, path)
        except Exception as error:
            entry.update(result="MISSING_AT_HEAD", detail=str(error))
            findings.append({"control": "CURRENT_OBJECT_MISSING", "detail": path})
            current.append(entry)
            continue
        try:
            worktree = reader(path)
        except Exception as error:
            entry.update(result="MISSING_IN_WORKTREE", detail=str(error))
            findings.append({"control": "WORKTREE_FILE_MISSING", "detail": path})
            current.append(entry)
            continue
        digest = hashlib.sha256(raw).hexdigest()
        if worktree != raw:
            entry.update(git_blob_sha=blob_id, sha256=digest, result="WORKTREE_DIFFERS",
                         worktree_sha256=hashlib.sha256(worktree).hexdigest())
            findings.append({"control": "WORKTREE_DIFFERS_FROM_HEAD", "detail":
                             f"{path}: commit the change or check out {head[:8]}"})
            current.append(entry)
            continue
        entry.update(git_blob_sha=blob_id, sha256=digest, result="MATCH")
        current.append(entry)
        expected = predecessor_by_path[path]
        if digest != expected["sha256"]:
            drift.append({
                "path": path,
                "predecessor_git_blob_sha": expected["git_blob_sha"],
                "predecessor_sha256": expected["sha256"],
                "current_git_blob_sha": blob_id,
                "current_sha256": digest,
                "accepted_commits": git.commits_touching(PREDECESSOR_HEAD, head, path),
            })
    for item in drift:
        if not item["accepted_commits"]:
            findings.append({"control": "DRIFT_WITHOUT_LINEAGE", "detail":
                             f"{item['path']} differs from v8 but no commit between {PREDECESSOR_HEAD[:8]} and {head[:8]} touches it"})
        if item["path"] in NUMERICAL_CORE_PATHS:
            findings.append({"control": "NUMERICAL_AUTHORITY_DRIFT", "detail": item["path"]})

    return {
        "head": head,
        "historical": historical,
        "historical_tree": historical_tree,
        "current": current,
        "drift": drift,
        "findings": findings,
    }


def verify(report: dict, stream=None) -> None:
    """Emit the complete report, then fail."""
    if not report["findings"]:
        return
    stream = stream or sys.stderr
    print(json.dumps({
        "result": "FAIL",
        "schema": SCHEMA,
        "head": report["head"],
        "predecessor": str(PREDECESSOR.relative_to(ROOT)),
        "findings": report["findings"],
        "historical": [item for item in report["historical"] if item.get("result") != "MATCH"],
        "current": [item for item in report["current"] if item.get("result") != "MATCH"],
    }, indent=1, sort_keys=True), file=stream)
    controls = sorted({finding["control"] for finding in report["findings"]})
    raise MeasurementError("V11 active measurement failed: " + ", ".join(controls))


def build_record(report: dict, review_sha256: str, predecessor: dict) -> dict:
    record = predecessor["record"]
    drift_paths = {item["path"] for item in report["drift"]}
    return {
        "schema": SCHEMA,
        "purpose": "active-source verification of the measured V11 implementation set at the current head",
        "scope": "source-only byte inventory; it does not ratify the behaviour of any body that changed since the predecessor",
        "predecessor": {
            "path": str(PREDECESSOR.relative_to(ROOT)),
            "sha256": PREDECESSOR_SHA256,
            "schema": PREDECESSOR_SCHEMA,
            "implementation_head": PREDECESSOR_HEAD,
            "implementation_tree": PREDECESSOR_TREE,
            "status": "FROZEN_HISTORICAL_MEASUREMENT_NOT_REGENERATED",
        },
        "predecessor_historical_verification": {
            "verified_paths": len(report["historical"]),
            "blob_mismatches": 0,
            "tree": report["historical_tree"],
            "result": "PASS",
        },
        "branch": BRANCH,
        "head_binding": ("NONE_BY_DESIGN: the record pins each measured body by Git blob id and SHA-256, so it "
                         "verifies at any head that has not changed them and never has to name the commit that "
                         "carries it"),
        "measured_path_count": len(report["current"]),
        "measured_path_set_sha256": MEASURED_PATH_SET_SHA256,
        "measured_paths": [{"path": item["path"], "git_blob_sha": item["git_blob_sha"], "sha256": item["sha256"]}
                           for item in report["current"]],
        "unchanged_since_predecessor": len(report["current"]) - len(drift_paths),
        "drift_from_predecessor": report["drift"],
        "review": {"path": str(REVIEW.relative_to(ROOT)), "sha256": review_sha256},
        "numerical_authority_unchanged": sorted(NUMERICAL_CORE_PATHS),
        "historical_primary_v2_sha256": record["historical_primary_v2_sha256"],
        "historical_secondary_v2_sha256": record["historical_secondary_v2_sha256"],
        "event_04_retry": False,
        "event_05_executed": False,
        "live_event_05_authorization_created": False,
        "original_checkpoint_access": 0,
        "historical_master_ledger": record["historical_master_ledger"],
        "result": "PASS",
    }


def generate(git: GitReader | None = None, head: str | None = None) -> dict:
    git = git or GitReader()
    predecessor = load_predecessor(PREDECESSOR.read_bytes())
    head = head or git.head()
    report = measure(git, read_file, head, predecessor)
    verify(report)
    return build_record(report, hashlib.sha256(REVIEW.read_bytes()).hexdigest(), predecessor)


def serialize(record: dict) -> str:
    return json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="verify the committed v9 record reproduces at the current head")
    arguments = parser.parse_args(argv)
    raw = serialize(generate())
    if arguments.check:
        if not OUTPUT.is_file():
            raise MeasurementError(f"missing active measurement {OUTPUT.relative_to(ROOT)}")
        if OUTPUT.read_text() != raw:
            print(json.dumps({"result": "FAIL", "control": "ACTIVE_MEASUREMENT_DRIFT",
                              "detail": "the committed v9 record does not reproduce at this head; regenerate it in the same commit as the source change"},
                             indent=1), file=sys.stderr)
            raise MeasurementError("V11 active measurement drift")
    else:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(raw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```
