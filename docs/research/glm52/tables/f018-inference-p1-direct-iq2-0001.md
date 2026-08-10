# Feature 018 exact P1 gate

> One M1 Ultra P1 execution at a clean source commit; not P2, golden-eight, steady-state throughput, or production evidence.

- Source: `2f51333e2e393f8db8e62e2f794afc393775b92d` (clean)
- Raw SHA-256: `08672b9edf976710cca973068234eedfdbeca27b5172fbe5dbfec992e7f9f07a`
- Checkpoint set: `d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee` at immutable revision `abc55e72527792c6e77069c99b4cb7de16fa9f23`
- Exact sequence: `[9703, 21615]`; golden prefix: `true`
- Metal device: `Apple M1 Ultra`; zero fallback: `True`; complete f32 Metal weight materialization: `0` bytes

| Boundary/component | Seconds |
| --- | ---: |
| Complete evidence wall | 1043.247634125 |
| Cold prompt stack | 838.497529709 |
| Full-vocabulary logits | 77.573811083 |
| Terminal warm stack | 127.009654625 |
| Direct IQ2 storage | 1.518706108 |
| Direct IQ2 registration | 0.088088967 |
| Direct IQ2 GPU command intervals | 2.427512166 |
| Direct IQ2 synchronized calls | 4.286872794 |

Direct IQ2 gate/up handled `1184` routed experts (`2368` GEMVs). `32` routed experts used the explicit non-IQ2 reference path. The two-slot worker retained `0` hits and `2366` bounded slot evictions.

The protected shared cache finished with `228` entries, `228` decoded hits, `0` evictions, and `0` CPU fallbacks.

For context only, the committed post-trunk P1 wall was `1425.756124916` s; this Feature 018 wall is `1043.247634125` s (cross-commit difference `382.508490791` s). This is not a controlled same-binary benchmark population.
