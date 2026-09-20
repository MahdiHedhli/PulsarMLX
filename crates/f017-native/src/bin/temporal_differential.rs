//! Checkpoint-free production-backend probe for the stateful decoder.
//!
//! Runs the committed temporal fixture through `execute_position` on the MLX
//! GPU backend, one position at a time against one retained state, and emits
//! everything the independent reference can be compared against. Only the
//! tensor source is synthetic; the orchestration, state and attention are the
//! production ones.

use f017_native::model::NativeMlxBackend;
use f017_native::temporal::{
    execute_position, SequenceState, TemporalFixture, TemporalObserver, TemporalSource,
};
use serde::Serialize;
use std::fs;
use stream::{MlxContext, MlxDevice, MlxStreamMode};

#[derive(Default, Serialize)]
struct Step {
    position: usize,
    token: u32,
    selected_token: u32,
    visible_keys: usize,
    first_head_attention_weights: Vec<f32>,
    selected_expert_ids: Vec<Vec<usize>>,
    logits: Vec<f32>,
    state_bytes: usize,
}

#[derive(Default)]
struct Capture {
    steps: Vec<Step>,
    pending_weights: Vec<f32>,
    pending_visible: usize,
    pending_experts: Vec<Vec<usize>>,
}

impl TemporalObserver for Capture {
    fn attention(
        &mut self,
        layer: usize,
        _position: usize,
        visible_keys: usize,
        first_head_weights: &[f32],
    ) -> Result<(), String> {
        if layer == 0 {
            self.pending_weights = first_head_weights.to_vec();
            self.pending_visible = visible_keys;
        }
        Ok(())
    }
    fn routing(
        &mut self,
        _layer: usize,
        _position: usize,
        selected_expert_ids: &[usize],
        _routing_weights: &[f32],
    ) -> Result<(), String> {
        self.pending_experts.push(selected_expert_ids.to_vec());
        Ok(())
    }
    fn step(
        &mut self,
        position: usize,
        token: u32,
        logits: &[f32],
        selected: u32,
    ) -> Result<(), String> {
        self.steps.push(Step {
            position,
            token,
            selected_token: selected,
            visible_keys: self.pending_visible,
            first_head_attention_weights: std::mem::take(&mut self.pending_weights),
            selected_expert_ids: std::mem::take(&mut self.pending_experts),
            logits: logits.to_vec(),
            state_bytes: 0,
        });
        Ok(())
    }
}

#[derive(Serialize)]
struct Output {
    schema: &'static str,
    seed: u64,
    backend: &'static str,
    original_checkpoint_reads: u32,
    tokens: Vec<u32>,
    positions: usize,
    final_state_bytes: usize,
    steps: Vec<Step>,
}

fn main() -> Result<(), String> {
    let args = std::env::args().collect::<Vec<_>>();
    if args.len() != 2 || args[1].to_ascii_lowercase().contains("checkpoint") {
        return Err("usage: temporal-differential TEMPORAL_FIXTURE".into());
    }
    let raw = fs::read(&args[1]).map_err(|error| error.to_string())?;
    let fixture: TemporalFixture = f017_native::json::parse_json_no_duplicates(&raw)?;
    let seed = fixture.seed;
    let (mut source, config, tokens) = TemporalSource::from_fixture(fixture)?;
    let context = MlxContext::new(MlxDevice::Gpu, MlxStreamMode::Owned)?;
    let mut backend = NativeMlxBackend { context: &context };
    let mut state = SequenceState::new(&config);
    let mut capture = Capture::default();
    for token in &tokens {
        execute_position(
            &mut source,
            &mut backend,
            &config,
            &mut state,
            *token,
            &mut capture,
        )?;
        let index = capture.steps.len() - 1;
        capture.steps[index].state_bytes = state.state_bytes();
    }
    context.synchronize()?;
    if capture.steps.len() != tokens.len() || state.positions() != tokens.len() {
        return Err("temporal capture census".into());
    }
    let output = Output {
        schema: "pulsarmlx.f017.native-temporal-differential-result/1.0.0",
        seed,
        backend: "NATIVE_RUST_MLX_TEMPORAL_ORCHESTRATION_SYNTHETIC_SOURCE",
        original_checkpoint_reads: 0,
        tokens,
        positions: state.positions(),
        final_state_bytes: state.state_bytes(),
        steps: capture.steps,
    };
    println!(
        "{}",
        serde_json::to_string(&output).map_err(|error| error.to_string())?
    );
    Ok(())
}
