# Portable Fixture Contract: glm52-runtime-fixture-v1

## Mandatory identity and provenance

- `feature_id`: `017`
- `spec_version`: semver-like string
- `source_commit`: immutable source commit that produced fixture
- `source_catalog`: path to catalog provenance
- `source_catalog_sha256`: catalog identity hash
- `checkpoint_set_sha256`: immutable checkpoint set hash
- `checkpoint_revision`: revision string
- `trunk_inventory_reference`: path + SHA-256 to the authoritative trunk inventory
- `tensor_name`, `tensor_shard`, `tensor_range`, `tensor_shape`, `quantization`, `dtype`
- `payload_sha256`: artifact bytes hash

## Required fixture fields

- `input_residual`
- `normalized_activation`
- `attention_or_mla_output`
- `router_logits`
- `routed_expert_ids`
- `routed_weights`
- `selected_expert_output`
- `shared_expert_output`
- `moe_aggregate`
- `residual_output`
- `final_hidden_state`
- `final_norm_output`
- `topk_logits`
- `topk_argmax`
- `margins`
- `generation_position`
- `layer`

## Validation rules

- Must reject missing required fields or missing checksums.
- Must reject fixture payload without source catalog linkage.
- Must reject missing `trunk_inventory_reference` and hash.
- Public-safe fixtures are synthetic/tiny unless explicitly documented for local-only use.
- Do not embed full checkpoint bytes in the repository.
