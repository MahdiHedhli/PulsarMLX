# Claims ledger — Feature 014 short-prompt generation

| Claim ID | Claim | Evidence | source_commit | Scope | Status | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| F014-C01 | Bounded greedy extension of 2 tokens from prompt `[0,1]` under full 48-layer architecture path; per-step MLX logits agree with independent CPU head; dual residual check on final sequence | [generation](raw/014-short-prompt-gen/f014-short-prompt-gen-0001.json) | b3ee76a0abc4e7dcfca8acb2ba6384a651f6209f | layers=48; argmax; new_tokens=2 | verified | Generated `[320, 16]`; full sequence `[0,1,320,16]`; dual residual passed; first-token repeatability ok. Not tok/s; not sampling. |
