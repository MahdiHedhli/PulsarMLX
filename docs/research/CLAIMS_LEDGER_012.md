# Claims ledger — Feature 012 full logits

| Claim ID | Claim | Evidence | source_commit | Scope | Status | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| F012-C01 | Full-model (48-layer) architecture residual + `output_norm` + `output.weight` logits: MLX ≈ CPU with top-1 and top-5 agreement | [logits](raw/012-013-logits-greedy/f012-full-logits-0001.json), [stack prep](raw/012-013-logits-greedy/f012-full-stack-depth-48-0001.json) | cca6b99 (runtime; re-stamp on commit) | tokens=[0,1]; row=1 (last); vocab=151936 | verified | logits max_abs ≈7.6e-6; RMSE ≈9.7e-7; cos ≈1.0; residual max_abs ≈1.9e-5; top-k ids match. |
