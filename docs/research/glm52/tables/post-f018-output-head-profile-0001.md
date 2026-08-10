# Post-IQ3 full-vocabulary output-head profile

> One real Q4_K matrix with a deterministic normalized activation; not a greedy-token or complete-stack result.

- Source: `0585112ebc025d6e22f3e91e0ab4fb54355bf8d2` (clean)
- Tensor: `output.weight`; shape: `[6144, 154880]`
- Compressed/decoded bytes: `535265280` / `3806330880`
- Samples: `10` after `3` warmups
- Deterministic output hashes: `1`

| Component | Median (s) | Mean (s) | Stddev (s) | Min (s) | Max (s) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Storage read | 0.059747 | 0.060538 | 0.002544 | 0.057697 | 0.065259 |
| Scalar Q4_K decode/materialization | 59.195961 | 59.190658 | 0.503222 | 58.299099 | 60.121683 |
| Contiguous buffer | 1.692246 | 1.696658 | 0.033213 | 1.635104 | 1.751592 |
| MLX build/eval | 11.387966 | 11.349942 | 0.242110 | 10.774111 | 11.653625 |
| MLX matvec | 0.153218 | 0.156988 | 0.018158 | 0.136230 | 0.187331 |
| Synchronized boundary total | 72.534284 | 72.558886 | 0.656590 | 71.437668 | 73.894288 |
| Cleanup | 0.070039 | 0.070744 | 0.003706 | 0.065843 | 0.075919 |

The current mode still uses scalar Q4_K decode and complete f32 materialization before MLX import. The profile measures that path; it does not qualify a replacement.
