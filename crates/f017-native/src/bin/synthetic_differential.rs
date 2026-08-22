//! Checkpoint-free production-orchestration probe for the expanded synthetic
//! differential family. Only the tensor source is synthetic.

use f017_native::model::{execute_one_token_observed, ExecutionObserver, NativeMlxBackend};
use f017_native::synthetic::{SyntheticFixture, SyntheticSource};
use serde::Serialize;
use std::fs;
use stream::{MlxContext, MlxDevice, MlxStreamMode};

#[derive(Serialize)]
struct LayerCapture {
    layer: usize,
    layer_input: Vec<f32>,
    post_attention_residual: Vec<f32>,
    router_normalized_input: Vec<f32>,
    selected_expert_ids: Vec<usize>,
    routing_weights: Vec<f32>,
    routed_aggregate: Vec<f32>,
    shared_expert: Vec<f32>,
    layer_output: Vec<f32>,
}

#[derive(Default)]
struct Capture {
    layers: Vec<LayerCapture>,
    final_hidden: Vec<f32>,
    final_norm: Vec<f32>,
    logits: Vec<f32>,
    selected_token: Option<u32>,
}

impl ExecutionObserver for Capture {
    fn layer(
        &mut self,
        layer: usize,
        layer_input: &[f32],
        post_attention_residual: &[f32],
        router_normalized_input: &[f32],
        selected_expert_ids: &[usize],
        routing_weights: &[f32],
        routed_aggregate: &[f32],
        shared_expert: &[f32],
        layer_output: &[f32],
    ) -> Result<(), String> {
        self.layers.push(LayerCapture {
            layer,
            layer_input: layer_input.to_vec(),
            post_attention_residual: post_attention_residual.to_vec(),
            router_normalized_input: router_normalized_input.to_vec(),
            selected_expert_ids: selected_expert_ids.to_vec(),
            routing_weights: routing_weights.to_vec(),
            routed_aggregate: routed_aggregate.to_vec(),
            shared_expert: shared_expert.to_vec(),
            layer_output: layer_output.to_vec(),
        });
        Ok(())
    }

    fn final_output(
        &mut self,
        hidden: &[f32],
        normalized: &[f32],
        logits: &[f32],
        selected_token: u32,
    ) -> Result<(), String> {
        self.final_hidden = hidden.to_vec();
        self.final_norm = normalized.to_vec();
        self.logits = logits.to_vec();
        self.selected_token = Some(selected_token);
        Ok(())
    }
}

#[derive(Serialize)]
struct Output {
    schema: &'static str,
    seed: u64,
    prompt_token: u32,
    fixture_expected_token: u32,
    result_token: u32,
    backend: &'static str,
    original_checkpoint_reads: u32,
    layers: Vec<LayerCapture>,
    final_hidden: Vec<f32>,
    final_norm: Vec<f32>,
    logits: Vec<f32>,
}

fn main() -> Result<(), String> {
    let args = std::env::args().collect::<Vec<_>>();
    if args.len() != 2 || args[1].to_ascii_lowercase().contains("checkpoint") {
        return Err("usage: synthetic-differential SYNTHETIC_FIXTURE".into());
    }
    let raw = fs::read(&args[1]).map_err(|error| error.to_string())?;
    let fixture: SyntheticFixture = f017_native::json::parse_json_no_duplicates(&raw)?;
    let seed = fixture.seed;
    let (mut source, config, prompt, expected) = SyntheticSource::from_fixture(fixture)?;
    let context = MlxContext::new(MlxDevice::Gpu, MlxStreamMode::Owned)?;
    let mut capture = Capture::default();
    let result = execute_one_token_observed(
        &mut source,
        &mut NativeMlxBackend { context: &context },
        &config,
        prompt,
        &mut capture,
    )?;
    context.synchronize()?;
    if capture.layers.len() != config.layer_count || capture.selected_token != Some(result) {
        return Err("capture census".into());
    }
    let output = Output {
        schema: "pulsarmlx.f017.native-full-graph-differential-result/1.0.0",
        seed,
        prompt_token: prompt,
        fixture_expected_token: expected,
        result_token: result,
        backend: "NATIVE_RUST_MLX_PRODUCTION_ORCHESTRATION_SYNTHETIC_SOURCE",
        original_checkpoint_reads: 0,
        layers: capture.layers,
        final_hidden: capture.final_hidden,
        final_norm: capture.final_norm,
        logits: capture.logits,
    };
    println!(
        "{}",
        serde_json::to_string(&output).map_err(|error| error.to_string())?
    );
    Ok(())
}
