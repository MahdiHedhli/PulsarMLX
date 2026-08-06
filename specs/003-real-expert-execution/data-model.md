# Data Model: Real Expert Execution

## Entities

### ExpertAdmission

| Field | Description |
| --- | --- |
| expert_index | Integer 0..127; Feature 003 default 114 |
| gate_tensor | Name, offset, length, shape, type, encoded_sha256 |
| up_tensor | Same structure |
| down_tensor | Same structure |
| intermediate_width | 768 |
| hidden_width | 2048 |
| activation | `swiglu_silu` |

### ExpertOracleFreeze

| Field | Description |
| --- | --- |
| input_sha256 | Feature 002 row-0 f32le hash |
| expert_index | 114 |
| routing_weight | Feature 002 normalized weight for (row0, expert 114) |
| gate_out_sha256 | Full intermediate gate vector hash |
| up_out_sha256 | Full intermediate up vector hash |
| act_out_sha256 | Activated intermediate hash |
| down_out_sha256 | Unweighted down output hash |
| weighted_out_sha256 | Weighted contribution hash |
| values | Full f32 vectors or approved stable representation |

### ExpertParityCandidate

| Field | Description |
| --- | --- |
| backend / device | apple-mlx / gpu |
| fallback_used | false |
| evaluated / synchronized | true |
| comparison | abs+rel metrics vs oracle |
| memory_gauges | public-safe |
| source_commit | clean HEAD |

## Relationships

```text
Feature002RouterFreeze --selects--> ExpertAdmission
Feature002InputRow --feeds--> ExpertOracleFreeze
ExpertAdmission --weights--> ExpertOracleFreeze
ExpertOracleFreeze --compares--> ExpertParityCandidate
ExpertParityCandidate --publishes--> RawEvidence003
```

## Validation rules

- expert_index ∈ Feature 002 top-8 for the case  
- tensor occurrence_count == 1 per required name  
- no non-finite values  
- weighted_out length == 2048  
- claim depth == `layer_0_single_expert_mlp_weighted` only
