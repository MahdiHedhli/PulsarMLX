# Expert offload: cold experts on disk, hot experts in memory (Flash AN, Graph 18)

This is the path the project exists for. The retained mlx-vlm
`moe_offload.py` (pinned `8d79dbcf`, sha256 `1cfb0198…`) provides
`ExpertStore` — per-layer safetensors files served through `mx.load`'s mmap,
with a byte-budgeted LRU of resident experts that evicts the least recently
used expert (dropping its arrays so MLX can reclaim them) and refetches it
lazily from the same file on the next miss, and a bulk `get_all` path for
calls that touch most of a layer — and the retained `switch_layers.py`
provides `OffloadedSwitchGLU`, a drop-in for `SwitchGLU` that computes only
the router-selected experts through `quantized_matmul` with the module's own
activation object. Both are admitted by canonical-AST identity with global
censuses; the store's auto-budget helpers are refused stubs (every store here
carries an explicit byte budget).

Under the supervised successor harness (`successor.py offload`) the controls
write a store into the child's work directory from the graph-15 frozen
quantized arrays in the repack file format (`experts/layer_0000.safetensors`
with `e{j}.{gate,up,down}_proj.{weight,scales,biases}`, `offload_index.json`),
then drive a frozen schedule with a budget of exactly two experts: six
decode-like single-token calls (per-expert `get`, so eviction and refetch
happen at nearly every call), one three-token call that touches all four
experts (`get_all`, which by design does not enter the LRU accounting), and a
final single-token call. The reference is the graph-15 dequantization
reference for the values and an explicit stdlib LRU model for the policy
(sorted unique experts per call; bulk when `unique*2 > num_experts`; hit
moves to most-recent, miss evicts least-recent until the expert fits).

Observed on CPU and Metal, at 4-bit/g64 and 8-bit/g32: outputs within 4.4e-7
of the reference after every call including after evictions and refetches;
`store.stats()` (hits, misses, evictions, resident experts and bytes) and the
resident order equal the LRU model after every call (e.g. 4 hits, 10 misses,
8 evictions over the 4-bit schedule); the bulk call leaves the accounting
untouched; the offloaded output equals the resident quantized `SwitchGLU` of
graph 15 (bit-identical on CPU, ≤6e-7 on Metal). All twelve prospective
cells match: three store mutants (evicting the most-recent expert, not
touching on a hit, skipping the refetch after eviction) and three module
mutants (ignoring the slot in the scatter, gathering rows by slot, inverting
the bulk threshold). `lru-no-touch-on-hit` is inactive on the 4-bit schedule
by the frozen scope (the counts coincide there; the resident order differs
and is reported) and kills on the 8-bit schedule.

What this does not establish: `repack()` of a real checkpoint (it streams a
build's shards), `patch_model()` over the stack (quantization resolution per
path), the automatic budget from `device_info`, multi-layer stores, any
throughput figure (dogfood metric, measured on the target machine, not a
correctness claim), and any real-model claim.
