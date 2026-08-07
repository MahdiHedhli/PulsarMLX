# ssd-llm sync log

| Date (UTC-ish) | Action | SHA | Notes |
| --- | --- | --- | --- |
| 2026-08-07 | Initial clone + qualification | `d0afcf0f109a39b6aa04552cba123ccf58842333` | Depth-1 clone of quantumnic/ssd-llm; MIT Nicola Spieser; classified for selective design adaptation only |

## Policy

- Re-qualify before any code vendoring.
- Prefer reimplementation under PulsarMLX APIs over copy-paste of large trees.
- Never replace PulsarMLX’s MLX + architecture-oracle correctness chain with ssd-llm’s Metal path.
