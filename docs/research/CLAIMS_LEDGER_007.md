# Claims ledger — Feature 007 pre-FFN residual capture

| Claim ID | Claim | Evidence | source_commit | Scope | Status | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| F007-C01 | Genuine layer-0 `ffn_inp-0` residual stream captured from pinned llama.cpp; independent CPU RMSNorm reproduces frozen Feature 002 `ffn_norm-0` | [validation](raw/007-pre-ffn-residual/f007-pre-ffn-residual-validate-0001.json), [residual](raw/007-pre-ffn-residual/ffn_inp-0.f32le) | (see commit stamp) | checkpoint=Qwen3-30B-A3B-Q8_0; node=ffn_inp-0; eps=1e-6; weight=blk.0.ffn_norm.weight | verified | residual sha `673441ded7…832d`; max abs vs F002 freeze ≈8.5e-8 / 9.5e-8; 0 mismatches; F002 fixture not regenerated. |
