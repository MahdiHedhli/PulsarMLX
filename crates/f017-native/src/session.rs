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
