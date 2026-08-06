# Claims ledger — Feature 008 F006 root cause

| Claim ID | Claim | Evidence | source_commit | Scope | Status | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| F008-C01 | F006 gap is llama Q8_0×Q8_0 activation-requant matmul vs architecture f32-dequant path; A≈B (~1e-7), B≠C (~3.4e-3); first diverge at expert gate/up | [decision](raw/008-f006-root-cause/f008-f006-root-cause-0001.json), [summary](raw/008-f006-root-cause/f006-rootcause-summary.json) | d039b000123c342deed2b9dc6522f74b20af0f73 | checkpoint=Qwen3-30B-A3B-Q8_0; layer0; experts top-8 | verified | Contract B. F003–F005 unchanged. Llama bit-parity not claimed. |
