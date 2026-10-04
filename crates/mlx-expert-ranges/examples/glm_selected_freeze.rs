//! Bound one selected expert and capture its packed bytes; no native execution.
use mlx_expert_ranges::{BoundedSource, ExpertRequest};
use serde_json::json;
use std::path::Path;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = std::env::args_os().collect();
    if args.len() != 4 {
        return Err("usage: glm_selected_freeze CHECKPOINT_ROOT EXPECTED_METADATA_SHA256 PRIVATE_OUTPUT.snapshot".into());
    }
    let source = BoundedSource::open(Path::new(&args[1]))?;
    let config = source.config_document();
    let text = &config["text_config"];
    let admitted = config["model_type"] == "glm5_next"
        && config["architectures"] == json!(["Glm5NextForConditionalGeneration"])
        && text["model_type"] == "glm5_next_text"
        && text["n_routed_experts"] == 288
        && text["hidden_size"] == 4096
        && text["moe_intermediate_size"] == 2048
        && text["swiglu_limit"] == 10.0
        && text["mlp_layer_types"][3] == "sparse";
    if !admitted {
        return Err("GLM layer-3 binding: model/config geometry mismatch".into());
    }
    let prefix = "language_model.model.layers.3.mlp.switch_mlp";
    let request = ExpertRequest {
        modules: ["gate_proj", "up_proj", "down_proj"].map(|r| format!("{prefix}.{r}")),
        expert: 0,
        experts: 288,
        d: 4096,
        h: 2048,
        bits: [4, 4, 4],
        group_size: 64,
    };
    let plan = source.plan(request)?;
    if plan.record().selected_bytes != 14_155_776 {
        return Err("selected GLM payload byte count mismatch".into());
    }
    let expected = args[2].to_str().ok_or("metadata SHA must be UTF-8")?;
    let receipt =
        mlx_expert_ranges::snapshot::freeze_selected(&plan, expected, Path::new(&args[3]))?;
    assert_eq!(receipt.requested_payload_bytes, 14_155_776);
    assert_eq!(receipt.payload_read_calls, 9);
    assert_eq!(receipt.snapshot_payload_bytes_written, 14_155_776);
    println!("{}", serde_json::to_string_pretty(&receipt)?);
    Ok(())
}
