# Bounded routed-expert lifecycle reuse

> One recurrent real expert (layer 64, expert 183); not a full MoE, layer, stack, or token benchmark.

All candidates retained the exact same f32 output hash across ten measured uses, with normal resource pressure.

| Candidate | Setup decode (s) | Setup MLX build (s) | Setup RSS delta (MiB) | Reuse decode (s) | Reuse MLX build (s) | Reuse matvec (s) | Cleanup (s) | Reuse total (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| transient | 0.000000 | 0.000000 | 0.0 | 0.211046 | 0.015782 | 0.010806 | 0.009364 | 0.248258 |
| decoded_host_rebuild | 0.218914 | 0.000000 | 155.0 | 0.000000 | 0.014355 | 0.008987 | 0.008400 | 0.032086 |
| mlx_ready_reuse | 0.220054 | 0.011996 | 251.0 | 0.000000 | 0.000000 | 0.002040 | 0.000000 | 0.002417 |

Transient-to-host-rebuild reuse ratio: **7.74x**. Transient-to-retained-MLX reuse ratio: **102.72x**.

Decode remains the largest transient stage. MLX build/import is measurable but not dominant; a safely retained evaluated matrix removes both decode and rebuild. The observed ~251 MiB MLX-ready setup RSS delta for one 144 MiB logical expert makes a 76-expert policy ineligible without a separate allocator-aware admission gate.
