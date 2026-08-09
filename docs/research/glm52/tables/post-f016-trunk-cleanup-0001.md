# Post-Feature-016 cleanup cadence study

> One changed variable: cleanup cadence. A decoded Q6_K MLX matrix, activation, matvec, and synchronized output remained fixed.

- Evidence source: `919d575e7b2ec5d5b6cc0a6d5ac04a36d5990ebb` (clean: `true`)
- Checkpoint set SHA-256: `d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee`
- Protocol: 5 warm-ups and 30 measured matvecs; batch interval 5.

| Mode | Matvec median (s) | Cleanup median/event (s) | Amortized cleanup/op (s) | Operation total median (s) |
| --- | ---: | ---: | ---: | ---: |
| cleanup only | n/a | 0.001804 | 0.001801 | n/a |
| cleanup every operation | 0.002715 | 0.003173 | 0.003162 | 0.005945 |
| cleanup every five operations | 0.002649 | 0.003276 | 0.000729 | 0.002736 |

Both matvec modes produced the same exact deterministic output and retained normal memory pressure. Batching reduced cleanup frequency in this retained-matrix fixture; it does not authorize cleanup removal or establish that a layer-wide lifetime is safe.

Per-operation totals exclude the subsequent resource-sampling call. The separately retained batch population wall includes that instrumentation and is not used as an optimization result.

This is a cleanup microbenchmark, not complete-layer, P1, token, production cadence, Rust, or Metal evidence.
