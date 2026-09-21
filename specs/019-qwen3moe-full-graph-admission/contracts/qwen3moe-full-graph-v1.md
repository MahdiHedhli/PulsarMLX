# Qwen3MoE full graph admission v1

Status: bounded metadata/catalog and graph-topology admission only.

Contract

- Contract ID: `qwen3moe-full-graph-admission-v1`.
- The contract is layered on `qwen3moe-adapter-admission-v1`; it does not replace
  the existing adapter, 16-value Q8_0 slice, router, or synthetic-generation
  contracts.
- Model identity remains `Qwen/Qwen3-30B-A3B-GGUF`, revision
  `e4d4bafdfb96a411a163846265362aceb0b9c63a`, filename
  `Qwen3-30B-A3B-Q8_0.gguf`, size `32483931648`, and SHA-256
  `4ad960d180b16f56024f5b704697e5dd5b0837167c2e515ef0569abfc599743c`.
- Exact architecture: `qwen3moe`.
- Tensor catalog: 579 typed entries: 3 global entries and 12 entries for each
  of 48 transformer layers.
- Catalog ranges must be checked, non-overlapping, and within the GGUF data
  section and pinned file size before the graph is admitted.

Typed graph

The graph descriptor has path-free bindings to the typed catalog for token
embedding, every layer tensor, final normalization, and output projection. Each
layer contains exactly this ordered sequence:

1. attention input RMSNorm (`attn_norm.weight`)
2. query projection (`attn_q.weight`)
3. query RMSNorm (`attn_q_norm.weight`)
4. key projection (`attn_k.weight`)
5. key RMSNorm (`attn_k_norm.weight`)
6. value projection (`attn_v.weight`)
7. NeoX rotary embedding
8. grouped-query attention
9. attention output projection (`attn_output.weight`)
10. attention residual add
11. FFN input RMSNorm (`ffn_norm.weight`)
12. router projection (`ffn_gate_inp.weight`)
13. full 128-way softmax followed by selected top-8 routing
14. expert gate projection (`ffn_gate_exps.weight`)
15. expert up projection (`ffn_up_exps.weight`)
16. SwiGLU activation
17. expert down projection (`ffn_down_exps.weight`)
18. routed-expert weighted aggregation
19. FFN residual add

The graph binds Qwen3MoE dimensions already admitted by the metadata contract:
2048 hidden values, 32 attention heads, 4 KV heads, 128 head dimension, 128
routed experts, top-8 selection, and the `neox` rotary family. Global graph
operations are token embedding, final RMSNorm, and output projection.

Admission behavior

`construct_qwen3moe_full_graph` revalidates the adapter, constructs the one
canonical 48-layer graph, and admits it through `admit_qwen3moe_full_graph`.
The latter revalidates the complete adapter, rejects out-of-data-section or
overlapping catalog ranges, and rejects any missing layer, reordered operation,
wrong tensor binding, or unexpected adapter contract. Graph operations are
closed Rust enum values; no caller-provided string is reinterpreted as an
operation.

The model-free reference at
`fixtures/mlx/qwen3moe-full-graph-v1.json` records the operation sequence,
layer/cardinality counts, dimensions, and routing normalization. It contains
no checkpoint bytes and does not establish real-checkpoint admission.

Explicit exclusions

This contract does not open, download, map, hash, decode, or execute tensor
payloads; perform a model forward; run attention or routing; tokenize; produce
logits; generate text; serve requests; benchmark; qualify; publish; or establish
production, dogfood, Event 06, or P1 authority. External inspection still uses
the existing read-only artifact verifier and memory/device/cancellation
boundaries unchanged.
