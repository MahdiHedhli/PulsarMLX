# R001 Live Source Inventory

## Authority

- Host: ColPanicM2, Apple M2 Max, 64 GiB.
- R001 starting HEAD: `1c820d518643c602bdeb1c14f2d9765820aedcb3`.
- Checkpoint set: GLM-5.2 UD-IQ2_XXS.
- Set SHA-256: `d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee`.
- Six destination shards matched authoritative sizes and SHA-256 values.
- Source pre/post stats remained stable during every copy.
- No checkpoint byte was downloaded, transformed, or written back to SMB.

## Live metadata

- GGUF version: 3.
- Architecture: `glm-dsa`.
- General alignment: 32 bytes.
- Tensor count: 1,809.
- Expert tensors: 456.
- Layers: 79 total; MoE layers 3 through 78.
- Routed experts: 256 per MoE layer.
- Shared experts: one per MoE layer.
- Logical objects: 19,532.
- Canonical expert payload: 224,974,307,328 bytes.

## Layout proof

GGUF dimensions are fastest-varying first. Every routed expert tensor has
dimensions `[cols, rows, 256]`; live `glm-dsa.expert_count` is 256. Therefore
dimension 2 is the expert axis and one plane is exactly
`row_bytes * dims[1]`. The 256 adjacent planes exactly cover each routed
tensor. Shared-expert tensors are complete two-dimensional matrices.

Checked arithmetic established:

- zero out-of-bounds ranges;
- zero expert-range overlaps;
- zero missing or multiply assigned objects;
- zero shard-spanning objects;
- zero split quantization blocks;
- exactly one gate, up, and down component for every logical object;
- exact reconciliation to 224,974,307,328 payload bytes.

The 15 observed component layout classes cover IQ2_XXS, IQ3_XXS, IQ2_S,
IQ4_XS, Q2_K, Q3_K, Q5_K, Q6_K, and Q8_0. Layer 8 contains the IQ2_S,
IQ4_XS, shared Q6_K, and shared Q8_0 exceptions. Layer 78 contains Q2_K and
Q3_K. Layer 40 is a representative standard IQ2_XXS/IQ3_XXS plus Q5_K/Q6_K
layer.

The machine-readable inventory is
`docs/research/r001/raw/r001-live-inventory-public-0001.json`.

## Claim boundary

This inventory proves checkpoint byte layout only. It does not prove model
output correctness, F017 readiness, inference performance, or a completed
expert store.
