# Claims ledger — Feature 010 complete layer-0

| Claim ID | Claim | Evidence | source_commit | Scope | Status | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| F010-C01 | Complete layer-0 architecture path `l_out = ffn_inp + MoE(RMSNorm(ffn_inp))` with architecture attention residual reaches MLX≈CPU parity | [complete](raw/010-011-layer-stack/f010-complete-layer0-0001.json), [depth-1 stack](raw/010-011-layer-stack/f011-stack-depth-01-0001.json) | b3ee76a0abc4e7dcfca8acb2ba6384a651f6209f | layer 0; tokens=[0,1]; Q8_0 weight × f32 act | verified | max_abs MLX vs CPU ≈ 1.13e-7; attention + MoE both pass; expert top-8 row0 matches F004/F005 ids [114,45,99,46,98,74,102,65]. |
