# Claims ledger — Feature 013 first greedy token

| Claim ID | Claim | Evidence | source_commit | Scope | Status | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| F013-C01 | First deterministic greedy token after full 48-layer architecture forward agrees CPU↔MLX | [greedy](raw/012-013-logits-greedy/f013-greedy-token-0001.json) | cca6b99 (runtime; re-stamp on commit) | prompt tokens=[0,1]; argmax decoding | verified | greedy token id **320** on both backends; top-5 [320, 220, 4710, 374, 1115]; deterministic. Not multi-token generation; not tok/s. |
