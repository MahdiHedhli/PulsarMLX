# Feature 018 Post-Opus Three-Way Matrix Gate

| Variant | Samples | Median (s) | Mean (s) | Std dev (s) | Min (s) | Max (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A. optimized NumPy + MLX | 30 | 0.091565000 | 0.092062499 | 0.003104476 | 0.089110792 | 0.107949375 |
| B. historical default direct | 30 | 0.001387167 | 0.001397043 | 0.000045128 | 0.001320834 | 0.001495916 |
| C. strict direct Metal scaffold | 30 | 0.001352563 | 0.001463389 | 0.000364009 | 0.001252666 | 0.002702625 |

Strict direct/reference ratio: `67.70×`; absolute median recovered: `0.090212437` s.
Classification: `numerically_qualified_greedy_identical`; exact bits: `false`; bit mismatches: `2008`; tolerance mismatches: `0`; max abs: `2.30967999e-07`.

Final verdict: **GO**. IQ3-down is eligible only after final CI and review closeout; it was not started by this calculation.

One real IQ2_XXS gate matrix on one M1 Ultra. Historical/default compilation is contextual, not a controlled current-source population. No expert, layer, token, P2, or golden-eight result is inferred.
