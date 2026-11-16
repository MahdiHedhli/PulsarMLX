//! Native-only source admission for the exact Studio017 public text architecture.
use super::{refusal, BoundedSource, Result};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::os::unix::fs::FileExt;

pub(super) fn admit(src: &BoundedSource) -> Result<()> {
    let cfg = src
        .held
        .get("config.json")
        .ok_or_else(|| refusal("CONFIG", "missing original fd"))?;
    if cfg.stamp.len != 124_463 {
        return Err(refusal("CONFIG", "size"));
    }
    cfg.check()?;
    let mut bytes = vec![0; 124_463];
    cfg.file
        .read_exact_at(&mut bytes, 0)
        .map_err(|e| refusal("CONFIG", e))?;
    cfg.check()?;
    if format!("{:x}", Sha256::digest(&bytes))
        != "3ed164a8f60c96dc81d5742b952b7823335fa7656fe0bbcf69c7ea05a4179d1d"
    {
        return Err(refusal("CONFIG", "digest"));
    }
    // config_document was parsed from these exact witnessed bytes. Explicit
    // duplicate-key refusal ensures neither parser depends on last-value wins.
    safetensors_catalog::reject_duplicate_keys(&bytes, "Studio017 config")
        .map_err(|e| refusal("CONFIG", e))?;
    validate(&src.config_document).map_err(|e| refusal("CONFIG", e))
}

fn validate(document: &Value) -> std::result::Result<(), String> {
    if document["model_type"] != "glm5_next"
        || document["architectures"] != json!(["Glm5NextForConditionalGeneration"])
        || document["tie_word_embeddings"] != false
    {
        return Err("outer text-model identity".into());
    }
    let t = document["text_config"]
        .as_object()
        .ok_or("missing text_config")?;
    if t.len() != 58 {
        return Err("text_config exact explicit field population".into());
    }
    let get = |k: &str| t.get(k).ok_or_else(|| format!("text_config.{k} missing"));
    for (k, v) in [
        ("vocab_size", 154880),
        ("n_routed_experts", 288),
        ("num_experts_per_tok", 8),
        ("n_shared_experts", 1),
        ("first_k_dense_replace", 3),
        ("hidden_size", 4096),
        ("intermediate_size", 12288),
        ("moe_intermediate_size", 2048),
        ("num_hidden_layers", 45),
        ("hc_mult", 4),
        ("hc_sinkhorn_iters", 20),
        ("num_attention_heads", 64),
        ("num_key_value_heads", 64),
        ("q_lora_rank", 1536),
        ("kv_lora_rank", 512),
        ("v_head_dim", 256),
        ("qk_head_dim", 256),
        ("qk_nope_head_dim", 256),
        ("qk_rope_head_dim", 0),
        ("head_dim", 0),
        ("index_head_dim", 128),
        ("index_kpool", 4),
        ("index_n_heads", 32),
        ("index_topk", 2048),
        ("n_group", 1),
        ("topk_group", 1),
        ("num_nextn_predict_layers", 1),
        ("pad_token_id", 154820),
        ("max_position_embeddings", 1048576),
    ] {
        if get(k)?.as_u64() != Some(v) {
            return Err(format!("text_config.{k}"));
        }
    }
    for (k, v) in [
        ("rms_norm_eps", 1e-5),
        ("hc_eps", 1e-6),
        ("swiglu_limit", 10.0),
        ("routed_scaling_factor", 2.5),
        ("attention_dropout", 0.0),
        ("initializer_range", 0.02),
        ("router_aux_loss_coef", 0.001),
    ] {
        let a = get(k)?;
        if !a.is_f64() || a.as_f64() != Some(v) {
            return Err(format!("text_config.{k}"));
        }
    }
    for (k, v) in [
        ("mhc", true),
        ("mla_use_nope", true),
        ("indexer_rope_interleave", true),
        ("index_kpool_compress", true),
        ("index_kpool_always_select_tail", true),
        ("index_share_for_mtp_iteration", true),
        ("norm_topk_prob", true),
        ("use_cache", true),
        ("attention_bias", false),
        ("tie_word_embeddings", false),
        ("output_router_logits", false),
    ] {
        if get(k)?.as_bool() != Some(v) {
            return Err(format!("text_config.{k}"));
        }
    }
    for (k, v) in [
        ("model_type", "glm5_next_text"),
        ("dtype", "bfloat16"),
        ("hidden_act", "silu"),
        ("scoring_func", "sigmoid"),
        ("topk_method", "noaux_tc"),
        ("moe_router_dtype", "float32"),
    ] {
        if get(k)?.as_str() != Some(v) {
            return Err(format!("text_config.{k}"));
        }
    }
    let mut full = vec![];
    let mut kda = vec![];
    for k in ["layer_types", "mlp_layer_types", "indexer_types"] {
        if get(k)?.as_array().map(Vec::len) != Some(45) {
            return Err(format!("text_config.{k}"));
        }
    }
    for i in 0..45usize {
        let is_sparse = (i + 1) % 4 == 0;
        if is_sparse {
            full.push(i)
        } else {
            kda.push(i)
        }
        if get("layer_types")?[i]
            != if is_sparse {
                "deepseek_sparse_attention"
            } else {
                "linear_attention"
            }
            || get("mlp_layer_types")?[i] != if i < 3 { "dense" } else { "sparse" }
            || get("indexer_types")?[i] != "full"
        {
            return Err(format!("text layer role {i}"));
        }
    }
    if get("eos_token_id")? != &json!([154820, 154827, 154829]) {
        return Err("eos_token_id".into());
    }
    if get("linear_attn_config")?
        != &json!({"num_heads":64,"head_dim":128,"short_conv_kernel_size":4,"gate_lower_bound":-5.0,
                                          "kda_layers":kda,"full_attn_layers":full})
    {
        return Err("effective linear-attention configuration".into());
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn validated_public_profile_rejects_changed_science_and_layer_roles() {
        let d: Value = serde_json::from_str(include_str!("studio017-text-profile.json")).unwrap();
        validate(&d).unwrap();
        for (ptr, v) in [
            ("/text_config/rms_norm_eps", json!(1e-6)),
            ("/text_config/hc_sinkhorn_iters", json!(19)),
            (
                "/text_config/linear_attn_config/gate_lower_bound",
                json!(-4.0),
            ),
            ("/text_config/layer_types/3", json!("linear_attention")),
            ("/text_config/attention_bias", json!(0)),
            ("/text_config/linear_attn_config/kda_layers/0", json!(3)),
            ("/text_config/n_group", json!(true)),
            ("/tie_word_embeddings", json!(true)),
        ] {
            let mut bad = d.clone();
            *bad.pointer_mut(ptr).unwrap() = v;
            assert!(validate(&bad).is_err(), "{ptr}");
        }
        let mut missing = d.clone();
        missing["text_config"]
            .as_object_mut()
            .unwrap()
            .remove("hc_eps");
        assert!(validate(&missing).is_err());
    }
}
