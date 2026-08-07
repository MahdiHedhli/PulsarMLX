# GLM-5.2 Limitations

## Active (methodology phase)

1. Full multi-shard checkpoint may still be downloading; **no full-model claim**.
2. Architecture residual op order partially confirmed from upstream source + KV; tensor-name walk pending complete catalog.
3. Mixed quant inventory incomplete until C01 full catalog.
4. Research streaming path is not an optimized production server.
5. OS page cache not controlled unless a run explicitly documents scrubbing.

## Policy

- No M2 Max / external RAID in this feature.
- No llama/CUDA bit-parity requirement.
- No silent CPU fallback in performance mode.
- No tolerance loosening after first real-weight measurement without versioned protocol change.

## Inherited

- Qwen baseline remains the verified end-to-end research path under
  `v0.2.0-qwen30b-e2e-research`.
