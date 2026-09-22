//! Temporal qualification for the stateful native decoder.
//!
//! Every fixture here is a tiny committed synthetic model; no checkpoint is
//! opened and no file is read. The point of these tests is that an
//! implementation which loops the position-zero producer, drops history,
//! attends to the current value only, or leaks one request's keys into the
//! next one must fail them.

use f017_native::model::{execute_one_token, Matrix, MatvecBackend, ModelConfig, ScalarBackend, TensorSource};
use f017_native::temporal::{
    execute_position, execute_prefix_no_cache, rope, RopePairing, SequenceState, TemporalConfig,
    TemporalObserver,
};
use std::collections::BTreeMap;

/// Deterministic value source: a small LCG, so fixtures are reproducible and
/// value-rich rather than identity matrices that hide ordering mistakes.
struct Lcg(u64);
impl Lcg {
    fn next(&mut self) -> f32 {
        self.0 = self.0.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
        ((self.0 >> 33) as f32 / (1u64 << 31) as f32) - 0.5
    }
    fn values(&mut self, count: usize) -> Vec<f32> {
        (0..count).map(|_| self.next()).collect()
    }
}

#[derive(Clone, Default)]
struct Store {
    vectors: BTreeMap<String, Vec<f32>>,
    matrices: BTreeMap<String, Matrix>,
    experts: BTreeMap<(String, usize), Matrix>,
    deny: Option<String>,
    short_read: Option<String>,
    lookups: usize,
}

impl Store {
    fn matrix(&mut self, name: &str, rows: usize, columns: usize, rng: &mut Lcg) {
        self.matrices.insert(
            name.to_owned(),
            Matrix { rows, columns, values: rng.values(rows * columns) },
        );
    }
    fn expert(&mut self, name: &str, id: usize, rows: usize, columns: usize, rng: &mut Lcg) {
        self.experts.insert(
            (name.to_owned(), id),
            Matrix { rows, columns, values: rng.values(rows * columns) },
        );
    }
}

impl TensorSource for Store {
    fn vector(&mut self, name: &str, length: usize) -> Result<Vec<f32>, String> {
        self.lookups += 1;
        if self.deny.as_deref() == Some(name) {
            return Err(format!("allocation denied for {name}"));
        }
        let value = self.vectors.get(name).ok_or_else(|| format!("missing {name}"))?.clone();
        if value.len() != length {
            return Err(format!("shape {name}"));
        }
        Ok(value)
    }
    fn matrix(&mut self, name: &str, rows: usize, columns: usize) -> Result<Matrix, String> {
        self.lookups += 1;
        if self.deny.as_deref() == Some(name) {
            return Err(format!("allocation denied for {name}"));
        }
        let mut value = self.matrices.get(name).ok_or_else(|| format!("missing {name}"))?.clone();
        if self.short_read.as_deref() == Some(name) {
            value.values.truncate(value.values.len().saturating_sub(1));
        }
        if value.rows != rows || value.columns != columns || value.values.len() != rows * columns {
            return Err(format!("shape {name}"));
        }
        Ok(value)
    }
    fn expert_matrix(&mut self, name: &str, expert: usize, rows: usize, columns: usize) -> Result<Matrix, String> {
        self.lookups += 1;
        if self.deny.as_deref() == Some(name) {
            return Err(format!("allocation denied for {name}"));
        }
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

fn tiny_config() -> ModelConfig {
    ModelConfig {
        layer_count: 3,
        hidden: 8,
        vocab: 16,
        leading_dense_layers: 1,
        expert_count: 4,
        expert_top_k: 2,
        dense_ffn: 6,
        expert_ffn: 6,
        heads: 2,
        q_rank: 6,
        kv_rank: 4,
        qk_nope: 4,
        qk_rope: 4,
        value_dim: 4,
        rms_epsilon: 1.0e-5,
        rope_base: 8_000_000.0,
        expert_weight_scale: 2.5,
    }
}

fn temporal(model: ModelConfig) -> TemporalConfig {
    TemporalConfig {
        attention_softmax_scale: TemporalConfig::softmax_scale_rule(&model),
        model,
        rope_pairing: RopePairing::NeoxHalfSplit,
        indexer_top_k: 32,
        max_positions: 16,
    }
}

fn store(seed: u64, model: &ModelConfig) -> Store {
    let mut rng = Lcg(seed);
    let mut store = Store::default();
    store.matrix("token_embd.weight", model.vocab, model.hidden, &mut rng);
    store.matrix("output.weight", model.vocab, model.hidden, &mut rng);
    store.vectors.insert("output_norm.weight".into(), rng.values(model.hidden));
    let qdim = model.qk_nope + model.qk_rope;
    for layer in 0..model.layer_count {
        store.matrix(&format!("blk.{layer}.attn_q_a.weight"), model.q_rank, model.hidden, &mut rng);
        store.matrix(&format!("blk.{layer}.attn_q_b.weight"), model.heads * qdim, model.q_rank, &mut rng);
        store.matrix(&format!("blk.{layer}.attn_kv_a_mqa.weight"), model.kv_rank + model.qk_rope, model.hidden, &mut rng);
        store.matrix(&format!("blk.{layer}.attn_output.weight"), model.hidden, model.heads * model.value_dim, &mut rng);
        for head in 0..model.heads {
            store.expert(&format!("blk.{layer}.attn_k_b.weight"), head, model.kv_rank, model.qk_nope, &mut rng);
            store.expert(&format!("blk.{layer}.attn_v_b.weight"), head, model.value_dim, model.kv_rank, &mut rng);
        }
        store.vectors.insert(format!("blk.{layer}.attn_norm.weight"), rng.values(model.hidden));
        store.vectors.insert(format!("blk.{layer}.attn_q_a_norm.weight"), rng.values(model.q_rank));
        store.vectors.insert(format!("blk.{layer}.attn_kv_a_norm.weight"), rng.values(model.kv_rank));
        store.vectors.insert(format!("blk.{layer}.ffn_norm.weight"), rng.values(model.hidden));
        if layer < model.leading_dense_layers {
            for part in ["gate", "up", "down"] {
                let (rows, columns) = if part == "down" { (model.hidden, model.dense_ffn) } else { (model.dense_ffn, model.hidden) };
                store.matrix(&format!("blk.{layer}.ffn_{part}.weight"), rows, columns, &mut rng);
            }
        } else {
            store.matrix(&format!("blk.{layer}.ffn_gate_inp.weight"), model.expert_count, model.hidden, &mut rng);
            store.vectors.insert(format!("blk.{layer}.exp_probs_b.bias"), rng.values(model.expert_count));
            for part in ["gate", "up", "down"] {
                let (rows, columns) = if part == "down" { (model.hidden, model.expert_ffn) } else { (model.expert_ffn, model.hidden) };
                for id in 0..model.expert_count {
                    store.expert(&format!("blk.{layer}.ffn_{part}_exps.weight"), id, rows, columns, &mut rng);
                }
                store.matrix(&format!("blk.{layer}.ffn_{part}_shexp.weight"), rows, columns, &mut rng);
            }
        }
    }
    store
}

#[derive(Default)]
struct Record {
    visible: Vec<(usize, usize, usize)>,
    weights: Vec<Vec<f32>>,
    experts: Vec<(usize, usize, Vec<usize>)>,
    steps: Vec<(usize, u32, u32)>,
    logits: Vec<Vec<f32>>,
}
impl TemporalObserver for Record {
    fn attention(&mut self, layer: usize, position: usize, visible_keys: usize, first_head_weights: &[f32]) -> Result<(), String> {
        self.visible.push((layer, position, visible_keys));
        if layer == 0 {
            self.weights.push(first_head_weights.to_vec());
        }
        Ok(())
    }
    fn routing(&mut self, layer: usize, position: usize, selected_expert_ids: &[usize], _routing_weights: &[f32]) -> Result<(), String> {
        self.experts.push((layer, position, selected_expert_ids.to_vec()));
        Ok(())
    }
    fn step(&mut self, position: usize, token: u32, logits: &[f32], selected: u32) -> Result<(), String> {
        self.steps.push((position, token, selected));
        self.logits.push(logits.to_vec());
        Ok(())
    }
}

fn run(store: &mut Store, config: &TemporalConfig, tokens: &[u32]) -> (Vec<u32>, Record, SequenceState) {
    let mut state = SequenceState::new(config);
    let mut record = Record::default();
    let mut produced = Vec::new();
    for token in tokens {
        let (selected, _) = execute_position(store, &mut ScalarBackend, config, &mut state, *token, &mut record).unwrap();
        produced.push(selected);
    }
    (produced, record, state)
}

// ---------------------------------------------------------------- positions

#[test]
fn position_zero_reproduces_the_one_token_producer_bit_for_bit() {
    let model = tiny_config();
    let config = temporal(model.clone());
    let mut a = store(1, &model);
    let mut b = a.clone();
    let expected = execute_one_token(&mut a, &mut ScalarBackend, &model, 5).unwrap();
    let (produced, record, state) = run(&mut b, &config, &[5]);
    assert_eq!(produced, vec![expected]);
    assert_eq!(state.positions(), 1);
    // One visible key at position zero, exactly as the frozen producer assumes.
    assert!(record.visible.iter().all(|(_, position, visible)| *position == 0 && *visible == 1));
    assert_eq!(record.weights[0], vec![1.0]);
}

#[test]
fn every_position_sees_exactly_its_causal_prefix_including_itself() {
    let model = tiny_config();
    let config = temporal(model.clone());
    let mut source = store(2, &model);
    let tokens = [3_u32, 9, 1, 3, 12, 7, 0, 15];
    let (_, record, state) = run(&mut source, &config, &tokens);
    assert_eq!(state.positions(), tokens.len());
    for (layer, position, visible) in &record.visible {
        assert!(*layer < model.layer_count);
        assert_eq!(*visible, position + 1, "position {position} must see itself and every earlier key");
    }
    // Positions 0, 1, 2 and 7 are all exercised with nontrivial history.
    for position in [0usize, 1, 2, 7] {
        assert!(record.visible.iter().any(|(_, seen, _)| *seen == position));
    }
}

#[test]
fn rope_is_identity_only_at_position_zero_and_rotates_afterwards() {
    let original = vec![0.25_f32, -0.5, 0.75, 1.0];
    for pairing in [RopePairing::NeoxHalfSplit, RopePairing::Interleaved] {
        let mut zero = original.clone();
        rope(&mut zero, 0, 8_000_000.0, pairing);
        assert_eq!(zero, original, "position zero must be the identity");
        for position in [1usize, 2, 7] {
            let mut rotated = original.clone();
            rope(&mut rotated, position, 8_000_000.0, pairing);
            assert_ne!(rotated, original, "position {position} must rotate");
            let before: f32 = original.iter().map(|v| v * v).sum();
            let after: f32 = rotated.iter().map(|v| v * v).sum();
            assert!((before - after).abs() < 1e-5, "rotation must preserve the norm");
        }
    }
    // The two conventions are genuinely different, so the choice is load-bearing.
    let (mut neox, mut interleaved) = (original.clone(), original.clone());
    rope(&mut neox, 3, 8_000_000.0, RopePairing::NeoxHalfSplit);
    rope(&mut interleaved, 3, 8_000_000.0, RopePairing::Interleaved);
    assert_ne!(neox, interleaved);
}

#[test]
fn attention_is_not_a_one_hot_distribution_once_history_exists() {
    let model = tiny_config();
    let config = temporal(model.clone());
    let mut source = store(3, &model);
    let (_, record, _) = run(&mut source, &config, &[2_u32, 11, 4, 8]);
    let last = record.weights.last().unwrap();
    assert_eq!(last.len(), 4);
    assert!((last.iter().sum::<f32>() - 1.0).abs() < 1e-5);
    assert!(last.iter().all(|w| *w > 0.0));
    assert!(last.iter().any(|w| *w < 0.99), "a one-hot softmax would mean history is ignored");
}

// ------------------------------------------------------------------ history

#[test]
fn distinct_histories_ending_in_the_same_token_produce_different_outputs() {
    let model = tiny_config();
    let config = temporal(model.clone());
    let mut first = store(4, &model);
    let mut second = first.clone();
    let (_, left, _) = run(&mut first, &config, &[1_u32, 2, 6]);
    let (_, right, _) = run(&mut second, &config, &[9_u32, 14, 6]);
    assert_ne!(left.logits.last().unwrap(), right.logits.last().unwrap(),
        "an implementation that only uses the current token would tie these");
}

#[test]
fn repeated_tokens_do_not_collapse_to_one_state() {
    let model = tiny_config();
    let config = temporal(model.clone());
    let mut source = store(5, &model);
    let (_, record, state) = run(&mut source, &config, &[7_u32, 7, 7, 7]);
    assert_eq!(state.positions(), 4);
    assert_ne!(record.logits[0], record.logits[3], "RoPE and the growing prefix must separate repeats");
    assert_eq!(record.weights[3].len(), 4);
}

#[test]
fn a_later_token_cannot_change_an_earlier_output() {
    let model = tiny_config();
    let config = temporal(model.clone());
    let mut short = store(6, &model);
    let mut long = short.clone();
    let (_, prefix, _) = run(&mut short, &config, &[5_u32, 10]);
    let (_, extended, _) = run(&mut long, &config, &[5_u32, 10, 13, 2]);
    assert_eq!(prefix.logits[0], extended.logits[0]);
    assert_eq!(prefix.logits[1], extended.logits[1]);
}

#[test]
fn incremental_state_matches_an_independently_recomputed_full_prefix() {
    let model = tiny_config();
    let config = temporal(model.clone());
    let tokens = [4_u32, 0, 12, 12, 6];
    let mut cached = store(7, &model);
    let (produced, record, _) = run(&mut cached, &config, &tokens);
    let mut fresh = store(7, &model);
    let (token, logits) = execute_prefix_no_cache(&mut fresh, &mut ScalarBackend, &config, &tokens).unwrap();
    assert_eq!(*produced.last().unwrap(), token);
    assert_eq!(record.logits.last().unwrap(), &logits);
}

#[test]
fn prefill_chunks_of_any_size_reach_the_same_state_as_one_token_at_a_time() {
    let model = tiny_config();
    let config = temporal(model.clone());
    let tokens = [3_u32, 8, 1, 15, 6];
    let mut single = store(8, &model);
    let (_, one_at_a_time, _) = run(&mut single, &config, &tokens);
    for chunk in [2usize, 3, 4] {
        let mut chunked = store(8, &model);
        let mut state = SequenceState::new(&config);
        let mut record = Record::default();
        for window in tokens.chunks(chunk) {
            for token in window {
                execute_position(&mut chunked, &mut ScalarBackend, &config, &mut state, *token, &mut record).unwrap();
            }
        }
        assert_eq!(state.positions(), tokens.len(), "chunk {chunk} with a one-token remainder");
        assert_eq!(record.logits.last().unwrap(), one_at_a_time.logits.last().unwrap());
    }
}

#[test]
fn reset_and_a_b_a_requests_are_independent() {
    let model = tiny_config();
    let config = temporal(model.clone());
    let mut source = store(9, &model);
    let mut state = SequenceState::new(&config);
    let mut record = Record::default();
    let a = [2_u32, 5, 9];
    for token in a { execute_position(&mut source, &mut ScalarBackend, &config, &mut state, token, &mut record).unwrap(); }
    let first_a = record.logits.last().unwrap().clone();
    assert!(state.state_bytes() > 0);
    state.reset();
    assert_eq!(state.positions(), 0);
    assert_eq!(state.state_bytes(), 0, "reset must release the retained causal state");
    for token in [14_u32, 1] { execute_position(&mut source, &mut ScalarBackend, &config, &mut state, token, &mut record).unwrap(); }
    state.reset();
    for token in a { execute_position(&mut source, &mut ScalarBackend, &config, &mut state, token, &mut record).unwrap(); }
    assert_eq!(record.logits.last().unwrap(), &first_a,
        "reused expert weights must not carry attention history between requests");
}

#[test]
fn a_shortened_or_edited_prompt_is_a_new_sequence_not_a_suffix() {
    let model = tiny_config();
    let config = temporal(model.clone());
    let mut source = store(10, &model);
    let mut state = SequenceState::new(&config);
    let mut record = Record::default();
    for token in [1_u32, 2, 3, 4] { execute_position(&mut source, &mut ScalarBackend, &config, &mut state, token, &mut record).unwrap(); }
    state.reset();
    for token in [1_u32, 2, 9] { execute_position(&mut source, &mut ScalarBackend, &config, &mut state, token, &mut record).unwrap(); }
    let edited = record.logits.last().unwrap().clone();
    let mut clean = store(10, &model);
    let (_, fresh, _) = run(&mut clean, &config, &[1_u32, 2, 9]);
    assert_eq!(fresh.logits.last().unwrap(), &edited);
}

#[test]
fn retained_state_grows_by_exactly_one_position_per_step() {
    let model = tiny_config();
    let config = temporal(model.clone());
    let mut source = store(11, &model);
    let mut state = SequenceState::new(&config);
    let mut record = Record::default();
    let per_position = model.layer_count * (model.kv_rank + model.qk_rope) * std::mem::size_of::<f32>();
    for (index, token) in [6_u32, 7, 8].iter().enumerate() {
        execute_position(&mut source, &mut ScalarBackend, &config, &mut state, *token, &mut record).unwrap();
        assert_eq!(state.state_bytes(), per_position * (index + 1));
    }
}

// ----------------------------------------------------------------- failures

#[test]
fn an_invalid_token_is_refused_without_touching_the_state() {
    let model = tiny_config();
    let config = temporal(model.clone());
    let mut source = store(12, &model);
    let mut state = SequenceState::new(&config);
    let mut record = Record::default();
    execute_position(&mut source, &mut ScalarBackend, &config, &mut state, 3, &mut record).unwrap();
    let error = execute_position(&mut source, &mut ScalarBackend, &config, &mut state, model.vocab as u32, &mut record).unwrap_err();
    assert!(error.contains("token out of range"));
    assert_eq!(state.positions(), 1);
}

#[test]
fn context_overflow_is_refused_at_the_declared_bound() {
    let model = tiny_config();
    let mut config = temporal(model.clone());
    config.max_positions = 3;
    let mut source = store(13, &model);
    let mut state = SequenceState::new(&config);
    let mut record = Record::default();
    for token in [1_u32, 2, 3] { execute_position(&mut source, &mut ScalarBackend, &config, &mut state, token, &mut record).unwrap(); }
    let error = execute_position(&mut source, &mut ScalarBackend, &config, &mut state, 4, &mut record).unwrap_err();
    assert!(error.contains("max_positions"), "{error}");
    assert_eq!(state.positions(), 3);
}

#[test]
fn a_context_beyond_the_indexer_budget_is_refused_rather_than_approximated() {
    let model = tiny_config();
    let mut config = temporal(model.clone());
    config.indexer_top_k = 2;
    config.max_positions = 8;
    assert!(config.validate().unwrap_err().contains("indexer top-k"));
    config.max_positions = 2;
    config.validate().unwrap();
}

#[test]
fn a_failed_step_rolls_the_state_back_to_its_previous_extent() {
    let model = tiny_config();
    let config = temporal(model.clone());
    let mut source = store(14, &model);
    let mut state = SequenceState::new(&config);
    let mut record = Record::default();
    for token in [2_u32, 4] { execute_position(&mut source, &mut ScalarBackend, &config, &mut state, token, &mut record).unwrap(); }
    let bytes = state.state_bytes();
    source.deny = Some("blk.2.ffn_norm.weight".into());
    let error = execute_position(&mut source, &mut ScalarBackend, &config, &mut state, 5, &mut record).unwrap_err();
    assert!(error.contains("allocation denied"), "{error}");
    assert_eq!(state.positions(), 2);
    assert_eq!(state.state_bytes(), bytes, "a partially written position must not survive");
    source.deny = None;
    let (_, _) = execute_position(&mut source, &mut ScalarBackend, &config, &mut state, 5, &mut record).unwrap();
    assert_eq!(state.positions(), 3);
}

#[test]
fn a_malformed_tensor_fails_closed() {
    let model = tiny_config();
    let config = temporal(model.clone());
    let mut source = store(15, &model);
    source.short_read = Some("blk.1.attn_q_a.weight".into());
    let mut state = SequenceState::new(&config);
    let mut record = Record::default();
    let error = execute_position(&mut source, &mut ScalarBackend, &config, &mut state, 1, &mut record).unwrap_err();
    assert!(error.contains("shape"), "{error}");
    assert_eq!(state.positions(), 0);
}

#[test]
fn a_state_from_another_configuration_is_refused() {
    let model = tiny_config();
    let config = temporal(model.clone());
    let mut other = model.clone();
    other.kv_rank = 8;
    other.qk_nope = 8;
    let mut state = SequenceState::new(&temporal(other));
    let mut source = store(16, &model);
    let mut record = Record::default();
    let error = execute_position(&mut source, &mut ScalarBackend, &config, &mut state, 1, &mut record).unwrap_err();
    assert!(error.contains("does not belong"), "{error}");
}

#[test]
fn the_configured_softmax_scale_is_the_one_actually_used() {
    let model = tiny_config();
    let mut config = temporal(model.clone());
    assert_eq!(config.attention_softmax_scale, 1.0 / 8.0_f32.sqrt());
    let mut source = store(17, &model);
    let (_, base, _) = run(&mut source, &config, &[3_u32, 9, 5]);
    config.attention_softmax_scale *= 4.0;
    let mut other = store(17, &model);
    let (_, scaled, _) = run(&mut other, &config, &[3_u32, 9, 5]);
    assert_ne!(base.weights.last().unwrap(), scaled.weights.last().unwrap(),
        "a hardcoded scale would ignore the configuration");
}

#[test]
fn expert_selection_is_recorded_per_layer_and_position() {
    let model = tiny_config();
    let config = temporal(model.clone());
    let mut source = store(18, &model);
    let (_, record, _) = run(&mut source, &config, &[4_u32, 11]);
    let routed: Vec<_> = record.experts.iter().filter(|(layer, _, _)| *layer >= model.leading_dense_layers).collect();
    assert_eq!(routed.len(), (model.layer_count - model.leading_dense_layers) * 2);
    for (_, _, ids) in routed {
        assert_eq!(ids.len(), model.expert_top_k);
        assert!(ids.iter().all(|id| *id < model.expert_count));
        assert!(ids[0] != ids[1], "top-k must not select the same expert twice");
    }
}
