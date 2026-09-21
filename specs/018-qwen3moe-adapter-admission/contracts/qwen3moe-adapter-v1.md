# Qwen3MoE adapter admission v1

Status: bounded metadata/tensor-catalog admission only.

Contract

- Contract ID: `qwen3moe-adapter-admission-v1`.
- Model repository: `Qwen/Qwen3-30B-A3B-GGUF`.
- Model revision: `e4d4bafdfb96a411a163846265362aceb0b9c63a`.
- Filename: `Qwen3-30B-A3B-Q8_0.gguf`.
- Size: `32483931648` bytes.
- Whole-file SHA-256: `4ad960d180b16f56024f5b704697e5dd5b0837167c2e515ef0569abfc599743c`.
- GGUF version: 3.
- GGUF data-section offset: `5969408`.
- Tensor catalog: 579 entries, 241 F32 and 338 Q8_0.
- Architecture: exact `qwen3moe`; aliases such as `qwen35` are rejected.

Typed model metadata

- Hidden width: 2048.
- Transformer layers: 48.
- Routed experts: 128.
- Selected experts: top-8.
- Expert FFN width: 768.
- Attention heads / KV heads: 32 / 4.
- Query/key/value lengths: 128 / 128.
- Dense FFN width: 6144.
- Context length: 40960.

Tensor map

GGUF shapes are fastest-axis-first. Q8_0 reader shapes reverse the logical axes and carry encoded row bytes as the last axis; F32 reader shapes reverse logical axes. Execution shapes restore logical model order.

| Scope | Exact name pattern | GGUF shape | Reader shape | Execution shape | Type / quantization | Orientation |
| --- | --- | --- | --- | --- | --- | --- |
| global | `output.weight` | `[2048,151936]` | `[151936,2176]` | `[151936,2048]` | Q8_0 / Q8_0 | vocab rows, hidden columns |
| global | `output_norm.weight` | `[2048]` | `[2048]` | `[2048]` | F32 / none_f32 | hidden vector |
| global | `token_embd.weight` | `[2048,151936]` | `[151936,2176]` | `[151936,2048]` | Q8_0 / Q8_0 | vocab rows, hidden columns |
| each layer 0..47 | `blk.{n}.attn_k.weight` | `[2048,512]` | `[512,2176]` | `[512,2048]` | Q8_0 / Q8_0 | projection rows, hidden columns |
| each layer 0..47 | `blk.{n}.attn_k_norm.weight` | `[128]` | `[128]` | `[128]` | F32 / none_f32 | head vector |
| each layer 0..47 | `blk.{n}.attn_norm.weight` | `[2048]` | `[2048]` | `[2048]` | F32 / none_f32 | hidden vector |
| each layer 0..47 | `blk.{n}.attn_output.weight` | `[4096,2048]` | `[2048,4352]` | `[2048,4096]` | Q8_0 / Q8_0 | projection rows, attention columns |
| each layer 0..47 | `blk.{n}.attn_q.weight` | `[2048,4096]` | `[4096,2176]` | `[4096,2048]` | Q8_0 / Q8_0 | projection rows, hidden columns |
| each layer 0..47 | `blk.{n}.attn_q_norm.weight` | `[128]` | `[128]` | `[128]` | F32 / none_f32 | head vector |
| each layer 0..47 | `blk.{n}.attn_v.weight` | `[2048,512]` | `[512,2176]` | `[512,2048]` | Q8_0 / Q8_0 | projection rows, hidden columns |
| each layer 0..47 | `blk.{n}.ffn_down_exps.weight` | `[768,2048,128]` | `[128,2048,816]` | `[128,2048,768]` | Q8_0 / Q8_0 | expert-major, output rows, hidden-input columns |
| each layer 0..47 | `blk.{n}.ffn_gate_exps.weight` | `[2048,768,128]` | `[128,768,2176]` | `[128,768,2048]` | Q8_0 / Q8_0 | expert-major, intermediate rows, hidden-input columns |
| each layer 0..47 | `blk.{n}.ffn_gate_inp.weight` | `[2048,128]` | `[128,2048]` | `[128,2048]` | F32 / none_f32 | expert-major rows, input columns |
| each layer 0..47 | `blk.{n}.ffn_norm.weight` | `[2048]` | `[2048]` | `[2048]` | F32 / none_f32 | hidden vector |
| each layer 0..47 | `blk.{n}.ffn_up_exps.weight` | `[2048,768,128]` | `[128,768,2176]` | `[128,768,2048]` | Q8_0 / Q8_0 | expert-major, intermediate rows, hidden-input columns |

Layer-0 observed ranges

These safe catalog ranges are retained as offsets and lengths, not payload bytes. Absolute offsets are relative to the start of the verified regular file.

- `blk.0.attn_k.weight`: offset `667203072`; Q8_0 encoded length `1114112`.
- `blk.0.attn_k_norm.weight`: offset `668317184`; F32 encoded length `512`.
- `blk.0.attn_norm.weight`: offset `668317696`; F32 encoded length `8192`.
- `blk.0.attn_output.weight`: offset `668325888`; Q8_0 encoded length `8912896`.
- `blk.0.attn_q.weight`: offset `677238784`; Q8_0 encoded length `8912896`.
- `blk.0.attn_q_norm.weight`: offset `686151680`; F32 encoded length `512`.
- `blk.0.attn_v.weight`: offset `686152192`; Q8_0 encoded length `1114112`.
- `blk.0.ffn_down_exps.weight`: offset `687266304`; Q8_0 encoded length `213909504`.
- `blk.0.ffn_gate_exps.weight`: offset `901175808`; Q8_0 encoded length `213909504`.
- `blk.0.ffn_gate_inp.weight`: offset `1115085312`; F32 encoded length `1048576`.
- `blk.0.ffn_norm.weight`: offset `1116133888`; F32 encoded length `8192`.
- `blk.0.ffn_up_exps.weight`: offset `1116142080`; Q8_0 encoded length `213909504`.

Admission behavior

`admit_qwen3moe_adapter` accepts only typed artifact identity, typed required metadata, and the complete typed catalog. It rejects missing or duplicate names, unexpected aliases, wrong architecture, missing or wrong-type metadata, wrong shape or orientation, unsupported quantization, invalid encoded sizes, and out-of-file ranges. The external inspection path computes and verifies the whole-file identity before constructing this catalog, and it never downloads or reads tensor payloads.

The model-free fixture `fixtures/mlx/qwen3moe-adapter-v1.json` checks the selected route shape against the existing backend `RoutingPlan` top-k/selected-score softmax contract and records the Q8_0 reader/execution shapes. It is synthetic fixture evidence only.

Explicit exclusions

This contract does not execute a transformer layer, decode Q8_0 payloads, perform a model forward, tokenize, produce logits, generate text, serve requests, benchmark performance, or establish production/dogfood readiness. The existing 16-value Q8_0 slice contract, frozen router contract, and synthetic generation contract remain separate and behaviorally unchanged.
