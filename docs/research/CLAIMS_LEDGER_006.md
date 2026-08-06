# Claims ledger — Feature 006 complete transformer layer

| Claim ID | Claim | Evidence | source_commit | Scope | Status | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| F006-C01 | Layer-0 output bit-identical to llama fused `l_out-0` / `ffn_moe_out-0` | [parity](raw/006-layer-out/f006-layer-out-parity-0001.json), [l_out](raw/006-layer-out/l_out-0.f32le), [ffn_moe_out](raw/006-layer-out/ffn_moe_out-0.f32le) | 1b1dca2 | checkpoint=Qwen3-30B-A3B-Q8_0; depth=layer_0_output | **rejected** (preserved) | max_abs≈3.43e-3; not ordinary fp drift. See F008 root cause. |
| F006-C02 | Layer-0 MoE residual block is verified under architecture-level independent oracle (F005); llama fused path uses Q8_0×Q8_0 activation requant | [F005](CLAIMS_LEDGER_005.md), [F008](CLAIMS_LEDGER_008.md), [root cause](raw/008-f006-root-cause/f008-f006-root-cause-0001.json) | d039b000123c342deed2b9dc6522f74b20af0f73 | architecture oracle = f32 dequant weights × f32 act | verified | Contract B. Bit-identical llama MoE **not** claimed. |
