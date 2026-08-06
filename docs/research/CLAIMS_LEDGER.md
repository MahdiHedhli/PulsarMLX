# Feature 002 Claims Ledger

**Status**: Two primary-batch and later-batch public Apple MLX router records
are append-only published under `raw/002-router-parity/`. Claims below are
`provisional` until a clean-checkout reproduction record is installed and
package verification promotes them. No expert, aggregation, full-layer,
generation, serving, or tokens-per-second claim is present.

Each row uses a stable `F002-CNN` identifier, links committed machine-readable
evidence by repository-relative path, names the full clean measured source
commit and exact checkpoint/tensor/case/depth scope, uses one of `verified`,
`provisional`, `rejected`, or `unsupported`, and includes a nonempty caveat.

Evidence links use `raw/002-router-parity/<experiment-id>.json` without parent
traversal. Scope is written as
`checkpoint=<repository>@<revision>;tensor=<name>;case=<id>;depth=<operation>`,
and the full commit must match the linked raw record.

| Claim | Evidence files | Commit | Scope | Status | Caveat |
| --- | --- | --- | --- | --- | --- |
| F002-C01 Exact Qwen3MoE layer-0 router top-8 expert IDs and order match the independent CPU oracle on Apple MLX GPU for the frozen single-row case | [raw batch-a](raw/002-router-parity/f002-router-real-b4262d84eef41665cf8306c352701a58838f5e5f0180c3342f3a6ab618a751d4-batch-a.json), [raw batch-b](raw/002-router-parity/f002-router-real-b4262d84eef41665cf8306c352701a58838f5e5f0180c3342f3a6ab618a751d4-batch-b.json) | 04b3502aa5cfbe48cda66d1a5b0b07a45902f762 | checkpoint=Qwen/Qwen3-30B-A3B-GGUF@e4d4bafdfb96a411a163846265362aceb0b9c63a;tensor=blk.0.ffn_gate_inp.weight;case=qwen3moe-layer0-router-token0-row0-v1;depth=layer_0_router_only | provisional | Zero ID and order mismatches; selected IDs [114, 45, 99, 46, 98, 74, 102, 65]. No expert MLP or routed aggregation is claimed. Clean-checkout reproduction not yet installed. |
| F002-C02 Exact Qwen3MoE layer-0 router top-8 expert IDs and order match the independent CPU oracle on Apple MLX GPU for the frozen two-row batch case | [raw batch-a](raw/002-router-parity/f002-router-real-b4262d84eef41665cf8306c352701a58838f5e5f0180c3342f3a6ab618a751d4-batch-a.json), [raw batch-b](raw/002-router-parity/f002-router-real-b4262d84eef41665cf8306c352701a58838f5e5f0180c3342f3a6ab618a751d4-batch-b.json) | 04b3502aa5cfbe48cda66d1a5b0b07a45902f762 | checkpoint=Qwen/Qwen3-30B-A3B-GGUF@e4d4bafdfb96a411a163846265362aceb0b9c63a;tensor=blk.0.ffn_gate_inp.weight;case=qwen3moe-layer0-router-token0-token1-batch-v1;depth=layer_0_router_only | provisional | Zero ID and order mismatches on the two-row case; second-row selected IDs [73, 95, 114, 99, 102, 46, 108, 106]. Not a complete MoE block. |
| F002-C03 Bounded layer-0 router logits, full-softmax probabilities, and selected-weight renormalization stay within frozen tolerances versus the independent CPU oracle on the single-row case | [raw batch-a](raw/002-router-parity/f002-router-real-b4262d84eef41665cf8306c352701a58838f5e5f0180c3342f3a6ab618a751d4-batch-a.json), [raw batch-b](raw/002-router-parity/f002-router-real-b4262d84eef41665cf8306c352701a58838f5e5f0180c3342f3a6ab618a751d4-batch-b.json) | 04b3502aa5cfbe48cda66d1a5b0b07a45902f762 | checkpoint=Qwen/Qwen3-30B-A3B-GGUF@e4d4bafdfb96a411a163846265362aceb0b9c63a;tensor=blk.0.ffn_gate_inp.weight;case=qwen3moe-layer0-router-token0-row0-v1;depth=layer_0_router_only | provisional | Observed max abs error 1.239776611328125e-05, MAE 2.8392920891443887e-06, RMSE 3.584568198272296e-06, zero numeric mismatches; twenty deterministic measured hashes with evaluated synchronized apple-mlx/gpu and no fallback. Not complete-model numerical parity. |
