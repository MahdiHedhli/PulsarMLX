//! Generation-contract tests for the native CLI's session layer.
//!
//! These run the real `generate` loop over a tiny committed synthetic model
//! and a toy vocabulary: stop semantics, bounded output, cancellation,
//! admission refusals, incremental UTF-8 and the counting rules, none of
//! which need a checkpoint.

use f017_native::model::{Matrix, ModelConfig, ScalarBackend, TensorSource};
use f017_native::session::{complete_utf8_prefix, generate, FinishReason, IncrementalText, Limits};
use f017_native::temporal::{RopePairing, SequenceState, TemporalConfig};
use std::collections::BTreeMap;
use std::sync::atomic::{AtomicBool, Ordering};

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

#[derive(Default)]
struct Store {
    vectors: BTreeMap<String, Vec<f32>>,
    matrices: BTreeMap<String, Matrix>,
    experts: BTreeMap<(String, usize), Matrix>,
}
impl TensorSource for Store {
    fn vector(&mut self, name: &str, length: usize) -> Result<Vec<f32>, String> {
        let v = self.vectors.get(name).ok_or_else(|| format!("missing {name}"))?.clone();
        if v.len() != length { return Err(format!("shape {name}")); }
        Ok(v)
    }
    fn matrix(&mut self, name: &str, rows: usize, columns: usize) -> Result<Matrix, String> {
        let m = self.matrices.get(name).ok_or_else(|| format!("missing {name}"))?.clone();
        if m.rows != rows || m.columns != columns { return Err(format!("shape {name}")); }
        Ok(m)
    }
    fn expert_matrix(&mut self, name: &str, expert: usize, rows: usize, columns: usize) -> Result<Matrix, String> {
        let m = self.experts.get(&(name.to_owned(), expert)).ok_or_else(|| format!("missing {name}"))?.clone();
        if m.rows != rows || m.columns != columns { return Err(format!("shape {name}")); }
        Ok(m)
    }
}

fn model() -> ModelConfig {
    ModelConfig {
        layer_count: 2, hidden: 8, vocab: 16, leading_dense_layers: 1, expert_count: 4,
        expert_top_k: 2, dense_ffn: 6, expert_ffn: 6, heads: 2, q_rank: 6, kv_rank: 4,
        qk_nope: 4, qk_rope: 4, value_dim: 4, rms_epsilon: 1e-5, rope_base: 8_000_000.0,
        expert_weight_scale: 2.5,
    }
}

fn config() -> TemporalConfig {
    let m = model();
    TemporalConfig {
        attention_softmax_scale: TemporalConfig::softmax_scale_rule(&m),
        model: m, rope_pairing: RopePairing::NeoxHalfSplit, indexer_top_k: 64, max_positions: 64,
    }
}

fn store(seed: u64) -> Store {
    let m = model();
    let mut rng = Lcg(seed);
    let mut s = Store::default();
    let mut matrix = |s: &mut Store, name: String, rows: usize, columns: usize, rng: &mut Lcg| {
        s.matrices.insert(name, Matrix { rows, columns, values: rng.values(rows * columns) });
    };
    matrix(&mut s, "token_embd.weight".into(), m.vocab, m.hidden, &mut rng);
    matrix(&mut s, "output.weight".into(), m.vocab, m.hidden, &mut rng);
    s.vectors.insert("output_norm.weight".into(), rng.values(m.hidden));
    let qdim = m.qk_nope + m.qk_rope;
    for layer in 0..m.layer_count {
        matrix(&mut s, format!("blk.{layer}.attn_q_a.weight"), m.q_rank, m.hidden, &mut rng);
        matrix(&mut s, format!("blk.{layer}.attn_q_b.weight"), m.heads * qdim, m.q_rank, &mut rng);
        matrix(&mut s, format!("blk.{layer}.attn_kv_a_mqa.weight"), m.kv_rank + m.qk_rope, m.hidden, &mut rng);
        matrix(&mut s, format!("blk.{layer}.attn_output.weight"), m.hidden, m.heads * m.value_dim, &mut rng);
        for head in 0..m.heads {
            s.experts.insert((format!("blk.{layer}.attn_k_b.weight"), head), Matrix { rows: m.kv_rank, columns: m.qk_nope, values: rng.values(m.kv_rank * m.qk_nope) });
            s.experts.insert((format!("blk.{layer}.attn_v_b.weight"), head), Matrix { rows: m.value_dim, columns: m.kv_rank, values: rng.values(m.value_dim * m.kv_rank) });
        }
        s.vectors.insert(format!("blk.{layer}.attn_norm.weight"), rng.values(m.hidden));
        s.vectors.insert(format!("blk.{layer}.attn_q_a_norm.weight"), rng.values(m.q_rank));
        s.vectors.insert(format!("blk.{layer}.attn_kv_a_norm.weight"), rng.values(m.kv_rank));
        s.vectors.insert(format!("blk.{layer}.ffn_norm.weight"), rng.values(m.hidden));
        if layer < m.leading_dense_layers {
            for part in ["gate", "up", "down"] {
                let (r, c) = if part == "down" { (m.hidden, m.dense_ffn) } else { (m.dense_ffn, m.hidden) };
                matrix(&mut s, format!("blk.{layer}.ffn_{part}.weight"), r, c, &mut rng);
            }
        } else {
            matrix(&mut s, format!("blk.{layer}.ffn_gate_inp.weight"), m.expert_count, m.hidden, &mut rng);
            s.vectors.insert(format!("blk.{layer}.exp_probs_b.bias"), rng.values(m.expert_count));
            for part in ["gate", "up", "down"] {
                let (r, c) = if part == "down" { (m.hidden, m.expert_ffn) } else { (m.expert_ffn, m.hidden) };
                for id in 0..m.expert_count {
                    s.experts.insert((format!("blk.{layer}.ffn_{part}_exps.weight"), id), Matrix { rows: r, columns: c, values: rng.values(r * c) });
                }
                matrix(&mut s, format!("blk.{layer}.ffn_{part}_shexp.weight"), r, c, &mut rng);
            }
        }
    }
    s
}

/// A toy vocabulary: each id decodes to a distinct ASCII word.
fn decode_all(ids: &[u32]) -> Vec<u8> {
    let mut out = Vec::new();
    for id in ids {
        out.extend_from_slice(format!("<{id}>").as_bytes());
    }
    out
}

fn run(
    seed: u64,
    prompt: &[u32],
    limits: Limits,
    stops: Vec<u32>,
    cancel_after: Option<usize>,
) -> Result<(f017_native::session::Outcome, String), String> {
    let config = config();
    let mut source = store(seed);
    let mut state = SequenceState::new(&config);
    let mut text = IncrementalText::new(|ids: &[u32]| decode_all(ids));
    let mut emitted = Vec::new();
    let cancel = AtomicBool::new(false);
    let mut seen = 0usize;
    let mut sink = |bytes: &[u8]| {
        emitted.extend_from_slice(bytes);
        seen += 1;
        if Some(seen) == cancel_after {
            cancel.store(true, Ordering::Relaxed);
        }
    };
    let outcome = generate(&mut source, &mut ScalarBackend, &config, &mut state, prompt, limits, &stops, &mut text, &mut sink, &cancel)?;
    Ok((outcome, String::from_utf8(emitted).unwrap()))
}

#[test]
fn a_bounded_run_stops_at_max_output_tokens() {
    let (outcome, text) = run(21, &[3, 7], Limits { max_prompt_tokens: 8, max_output_tokens: 4 }, vec![], None).unwrap();
    assert_eq!(outcome.finish_reason, FinishReason::Length);
    assert_eq!(outcome.generated_token_count, 4);
    assert_eq!(outcome.generated_tokens.len(), 4);
    assert_eq!(outcome.prompt_tokens, 2);
    // Two prompt positions plus three continuation positions: the fourth
    // generated token needs no further forward pass.
    assert_eq!(outcome.positions_executed, 5);
    assert_eq!(outcome.position_seconds.len(), 5);
    assert_eq!(outcome.position_selected_tokens.len(), 5);
    assert_eq!(outcome.position_logits_sha256.len(), 5);
    assert!(outcome.position_logits_sha256.iter().all(|sha| sha.len() == 64));
    // The last prompt position's argmax is the first generated token.
    assert_eq!(outcome.position_selected_tokens[1], outcome.generated_tokens[0]);
    assert_eq!(text.matches('<').count(), 4);
}

#[test]
fn a_stop_token_ends_the_run_is_counted_and_is_not_written_to_the_answer() {
    let (open, _) = run(22, &[1], Limits { max_prompt_tokens: 8, max_output_tokens: 6 }, vec![], None).unwrap();
    let first = open.generated_tokens[0];
    let (outcome, text) = run(22, &[1], Limits { max_prompt_tokens: 8, max_output_tokens: 6 }, vec![first], None).unwrap();
    assert_eq!(outcome.finish_reason, FinishReason::Stop);
    assert_eq!(outcome.stop_token, Some(first));
    assert_eq!(outcome.generated_token_count, 1, "the terminal token is counted");
    assert_eq!(text, "", "the terminal token is not part of the answer");
}

#[test]
fn cancellation_between_positions_is_reported_as_cancelled() {
    let (outcome, _) = run(23, &[2, 5], Limits { max_prompt_tokens: 8, max_output_tokens: 6 }, vec![], Some(1)).unwrap();
    assert_eq!(outcome.finish_reason, FinishReason::Cancelled);
    assert!(outcome.generated_token_count >= 1);
    assert!(outcome.generated_token_count < 6);
}

#[test]
fn an_over_long_prompt_is_refused_before_any_forward_pass() {
    let error = run(24, &[1, 2, 3, 4], Limits { max_prompt_tokens: 3, max_output_tokens: 2 }, vec![], None).unwrap_err();
    assert!(error.contains("exceeds max_prompt_tokens"), "{error}");
}

#[test]
fn an_empty_prompt_is_refused() {
    let error = run(25, &[], Limits { max_prompt_tokens: 3, max_output_tokens: 2 }, vec![], None).unwrap_err();
    assert!(error.contains("empty prompt"), "{error}");
}

#[test]
fn limits_that_cannot_fit_the_context_are_refused() {
    let mut config = config();
    config.max_positions = 4;
    let error = Limits { max_prompt_tokens: 3, max_output_tokens: 3 }.validate(&config).unwrap_err();
    assert!(error.contains("max_positions"), "{error}");
    Limits { max_prompt_tokens: 2, max_output_tokens: 2 }.validate(&config).unwrap();
}

#[test]
fn generation_requires_a_fresh_state() {
    let config = config();
    let mut source = store(26);
    let mut state = SequenceState::new(&config);
    let mut text = IncrementalText::new(|ids: &[u32]| decode_all(ids));
    let cancel = AtomicBool::new(false);
    let limits = Limits { max_prompt_tokens: 4, max_output_tokens: 2 };
    let stops: Vec<u32> = Vec::new();
    let mut sink = |_: &[u8]| {};
    generate(&mut source, &mut ScalarBackend, &config, &mut state, &[1], limits, &stops, &mut text, &mut sink, &cancel).unwrap();
    let error = generate(&mut source, &mut ScalarBackend, &config, &mut state, &[1], limits, &stops, &mut text, &mut sink, &cancel).unwrap_err();
    assert!(error.contains("fresh state"), "{error}");
}

#[test]
fn one_generated_token_has_no_decode_rate() {
    let (outcome, _) = run(27, &[4], Limits { max_prompt_tokens: 4, max_output_tokens: 1 }, vec![], None).unwrap();
    assert_eq!(outcome.generated_token_count, 1);
    assert_eq!(outcome.decode_tokens_per_second(), None,
        "one cold token's reciprocal is not a sustained decode rate");
}

// ------------------------------------------------------------- utf-8 stream

#[test]
fn incremental_text_holds_back_incomplete_characters() {
    let table: Vec<&[u8]> = vec![b"\xc3", b"\xc3\xa9", b"\xc3\xa9 ok"];
    let mut index = 0usize;
    let mut text = IncrementalText::new(move |ids: &[u32]| {
        let _ = ids;
        let bytes = table[index.min(table.len() - 1)].to_vec();
        index += 1;
        bytes
    });
    assert_eq!(text.push(1), Vec::<u8>::new(), "half of a two-byte character must be held back");
    assert_eq!(text.push(2), "é".as_bytes().to_vec());
    assert_eq!(text.push(3), " ok".as_bytes().to_vec());
    assert_eq!(text.flush(), Vec::<u8>::new());
}

#[test]
fn complete_utf8_prefix_stops_at_a_character_boundary() {
    assert_eq!(complete_utf8_prefix("héllo".as_bytes()), "héllo".len());
    assert_eq!(complete_utf8_prefix(b"ab\xc3"), 2);
    assert_eq!(complete_utf8_prefix(b"\xe2\x82"), 0);
    assert_eq!(complete_utf8_prefix("€".as_bytes()), 3);
}

#[test]
fn the_emitted_answer_is_exactly_the_generated_tokens() {
    let (outcome, text) = run(28, &[6], Limits { max_prompt_tokens: 4, max_output_tokens: 3 }, vec![], None).unwrap();
    let expected = String::from_utf8(decode_all(&outcome.generated_tokens)).unwrap();
    assert_eq!(text, expected, "no end summary and no diagnostic may reach the answer stream");
}
