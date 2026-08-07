# Weekend optimization sprint status

**Started**: 2026-08-07  
**Golden tag**: `v0.3.0-glm52-e2e-research` @ `07dc9fc` (tag object; tip may advance)

## Completed

| Phase | Deliverable | Commit |
| --- | --- | --- |
| 0 | Golden baseline doc + annotated tag `v0.3.0-glm52-e2e-research` | `07dc9fc` + tag |
| 1 | ssd-llm qualification (no runtime dep; design borrow) | `a23b4d0` |
| 1 | Tests: 472 pass / 1 Metal compile fail on host | report |
| 2 | Hotspot profile layer 3 | `0126ef1` |
| 3 | Inference mode scaffold + expert slab cache | `a23b4d0` |
| 3 | Public-safe memory pressure helper | `0126ef1` |
| 4 design | MLA compact-KV incremental design doc | `a23b4d0` |

## In flight

| Item | Notes |
| --- | --- |
| P1 golden first new token | `glm52_inference.py --n-new 1 --cache-gib 8` background |

## Next (autonomous continuation)

1. Finish P1; confirm first new token == **21615**
2. Run full 8-token golden with cache (expect << 13.5 h if cache warm helps multi-step; prefill still heavy)
3. Expert prefetch after correct P1
4. Wire `pulsar-mlx` CLI subcommand when path stable
5. Update `PULSARMLX_GLM52_PERFORMANCE_REPORT.md` with measured P1 numbers

## Non-goals this weekend (unless free)

- Custom Metal kernels
- Server
- M2 / RAID
