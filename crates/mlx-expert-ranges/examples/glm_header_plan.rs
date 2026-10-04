//! Metadata-only model binder: never calls ExpertPlan::load.
use mlx_expert_ranges::{BoundedSource, ExpertRequest};
use serde_json::json;
use std::path::Path;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = std::env::args_os().collect();
    if args.len() != 2 {
        return Err("usage: glm_header_plan CHECKPOINT_ROOT".into());
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
    assert_eq!(source.requested_payload_bytes(), 0);
    assert_eq!(source.payload_read_calls(), 0);
    println!(
        "{}",
        serde_json::to_string_pretty(&json!({"schema":"pulsarmlx.glm-expert-header-plan/1",
        "status":"METADATA_ONLY_ADMITTED","plan":plan.record(),"payload_read_calls":source.payload_read_calls(),
        "requested_payload_bytes":source.requested_payload_bytes(),"native_calls":0,"scope":"real header/config/role/range binding only; no payload or numerical qualification"}))?
    );
    Ok(())
}
