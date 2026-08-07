# Data Model: 016-glm52-full-execution

## Entities

### CheckpointIdentity

- `repo`, `revision`, `quant`
- `files[]`: filename, size_bytes, sha256
- `total_bytes`, `architecture` (`glm-dsa`)
- `license`, `access_conditions`
- `local_env_var` (`PULSARMLX_GLM_GGUF` or shard dir)

### DiskAdmission

- free_before / free_after cleanup (bytes)
- required_before / required_after
- cleanup_actions[]
- admission_result: `passed` | `failed`
- blocker (optional)

### ArchitectureContract

- layer_count, hidden, vocab, rope, norms
- mla: dims, latent_kv, rope sections
- dsa: indexer, top_k rows, prefill/decode
- moe: n_experts, n_active, shared, score_fn, activation
- residual graph, embedding/output tying
- tolerances + unsupported bit-parity claims

### LayerBoundaryMetrics

- max_abs, mean_abs, rmse, cosine, norm_ratio
- first_max_error_index
- router_ids_agree
- deterministic_repeatability

### LogitsBoundaryMetrics

- max_abs, rmse
- top1 / top5 / top10 agreement
- rank_stability, greedy_token

### GenerationRecord

- prompt_text, prompt_token_ids
- generated_token_ids, decoded_text
- per_step routing snapshot (optional)
- cache stats, replay match

### PerformanceSample

- role: process_cold | warm | …
- ttft_s, prefill_tps, decode_tps
- bytes_read, cache_hits/misses/evictions
- rss_peak, swap, thermal

### Claim

- claim_id, statement, evidence_paths, commit, checkpoint_sha
- status: verified | provisional | rejected | unsupported
