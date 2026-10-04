# Tensor-role and operation coverage v1
Logical dimensions below come from pinned source/config, NOT checkpoint headers.
D=4096, H=64, K=128 (KDA), R=512 (KV latent), Q=1536 (query rank),
A=256 (NoPE attention head), I=128 (index head), N=32 (index heads), V=154880.
Storage physical packing/quant companions must be admitted independently.

| Role / source suffix | Logical axes | Preparation coverage / production gap |
|---|---|---|
| embed_tokens.weight | [V,D] | Tiny lookup/broadcast probe; loading, token semantics open |
| input_layernorm, post_attention_layernorm weights | [D] | Weighted RMS contract; real dtype/weights open |
| attn_hc / ffn_hc fn, base, scale | [24,4D], [24], [3] | Independent collapse/Sinkhorn/expand; comb[input,output] |
| KDA q_proj/k_proj/v_proj | [HK,D] each | Preprojected fixture boundary; native matmul open |
| conv1d.weight | [3HK,4,1] | Tiny kernel=3, seven unequal-axis channels; raw suffix chronological |
| forget_gate f_a/f_b | [K,D], [HK,K] | Gate input fixture only; full projection open |
| forget_gate A_log/dt_bias | [H], [HK] | Decay equation tested; protected FP32 source policy |
| b_proj | [H,D] | Beta equation tested; projection open |
| g_a/g_b, o_norm, o_proj | [K,D], [HK,K], [K], [D,HK] | Gated output norm/projection specified; numerical production open |
| KDA recurrence state | native [B,H,Dv,Dk] | Mini boundary [Dk,Dv]; unequal 2/3 axes detect transpose |
| KDA conv suffix | [B,3,3HK] | Tiny [2,7], stored BEFORE SiLU; separate owner per layer/request/epoch |
| sparse q_a/q_a_norm/q_b | [Q,D], [Q], [HA,Q] | NoPE source contract; projection not executed here |
| sparse kv_a/kv_a_norm | [R,D], [R] | Latent cache must retain absolute position; production cache open |
| sparse embed_q/unembed_out/o_proj | [H,R,A], [H,A,R], [D,HA] | Latent orientation source contract; preprojected key/value tiny fixture |
| indexer wq_b/wk/k_norm | [NI,Q], [I,D], [I] weight+bias | Per-feature normalization/projection open |
| indexer weights_proj | [N,D] | Tiny one-head score weight, not full indexer parity |
| index_kpool_compress_gate / APE | [I,D], [4,I] | Tiny per-feature pooled softmax and absolute pool/tail visibility |
| sparse state | positioned latent/index key/gate and completed pools/tail | Tiny separate index K/gate and attention K/V; no persisted queries; no eviction/padding/quantized cache claim |
| dense gate/up/down (layers 0..2) | [12288,D], [12288,D], [D,12288] | Tiny clamped SwiGLU MLP compared independently |
| router gate.weight / correction_bias | [288,D], [288] | Corrected ranking; original sigmoid mix, toy tie rule |
| routed switch_mlp gate/up/down | [288,2048,D] twice, [288,D,2048] | Tiny selected-expert computation; packed numerical path independent dependency |
| shared_experts gate/up/down | [2048,D] twice, [D,2048] | Add shared once; never route-normalize shared branch |
| final norm.weight / lm_head.weight | [D], [V,D] | Tiny stream mean -> weighted norm -> untied projection probe |
| tokenizer / EOS / masks | token IDs / 154820,154827,154829 | Boundary documented; files and stop semantics unqualified |
| vision/projector and nextn/MTP | deliberately unresolved | Outside text preparation, no invented weights or source completion claim |

Tiny calculations use binary64, not BF16/FP32 native rounding equivalence.
Candidate and oracle share only fixture inputs, never numerical helpers. Source
hashes pin the exact evidence and capsules without executing backend loaders.
