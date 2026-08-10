# Feature 018 exact P1 with direct IQ2/IQ3 experts

> One clean-source P1 execution on one M1 Ultra; not P2, golden-eight, steady-state throughput, or production evidence.

- Source: `8b7a1bfc3ef9fb44bf24911832af11d15e348f18` (clean)
- Raw SHA-256: `574c90898f1ca3569272757b8adefee953abb16f58ad3b2275698ed4f113392d`
- Exact sequence: `[9703, 21615]`; golden prefix: `true`
- Direct routed experts: `1136`; explicit references: `80`
- Direct GEMVs: `3408`; CPU fallbacks/direct errors: `0` / `0`

| Boundary/component | Seconds |
| --- | ---: |
| Complete evidence wall | 990.044242625 |
| Cold prompt stack | 833.188530042 |
| Full-vocabulary logits | 77.987068333 |
| Terminal warm stack | 78.446275458 |
| Direct packed storage | 3.410163118 |
| Direct kernel intervals | 2.743788668 |
| Direct synchronized calls | 5.215071666 |

For cross-commit context only, the prior IQ2-only direct P1 wall was `1043.247634125` s and its terminal warm stack was `127.009654625` s. The current wall difference is `53.203391500` s; this is not a controlled same-binary population.
