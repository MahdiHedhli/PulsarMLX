# GLM-5.2 Limitations

## Active

1. The frozen golden-eight result is one bounded M1 Ultra correctness/reuse run,
   not a steady-state throughput population or production-readiness claim.
2. Expert-cache nested quantization metrics do not instrument the dense trunk,
   including MLA/attention projections, embeddings, and the output projection.
3. The passively retained warm intervals leave roughly 87% of stack wall in an
   uninstrumented residual; expert-only quant rankings cannot select a first
   direct-Metal kernel without trunk-side fixture measurements.
4. The final recorded stack advances terminal model state after the eighth
   generated token was selected; it is not user-visible eighth-token latency.
5. The Python/MLX research streaming path is not an optimized production server.
6. OS page cache was not controlled, so storage observations are not controlled
   process-cold storage measurements.
7. The passive watcher began after the cold and first warm stacks. It preserved
   eight complete snapshots and seven valid warm intervals, but cannot provide
   cold per-quant deltas; no missing earlier snapshot was reconstructed.

## Policy

- No M2 Max full-checkpoint or external RAID run in this feature.
- No llama/CUDA bit-parity requirement.
- No silent CPU fallback in performance mode.
- No tolerance loosening after first real-weight measurement without versioned protocol change.

## Inherited

- Qwen baseline remains the verified end-to-end research path under
  `v0.2.0-qwen30b-e2e-research`.
