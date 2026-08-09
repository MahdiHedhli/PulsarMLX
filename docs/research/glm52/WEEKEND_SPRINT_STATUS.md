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
| 5 | P1 inference golden first-token match recovered after reboot | this focused recovery commit |

## Recovered P1 evidence

- Generated sequence: `[9703, 21615]`
- Expected prefix: `[9703, 21615]`
- Wall time: 15146.448245750013 seconds (~4.2 hours)
- Decoded cache: 0 hits, 4104 misses, 3934 evictions
- Original evidence SHA-256:
  `b62c3062adc21498e1af19111202ac4a976aaa48106e7de7852f78280b8b2bfb`
- Limitation: the recovered legacy output does not embed its schema,
  checkpoint set hash, or execution commit; it is a valid golden-prefix
  observation but not yet a self-contained publication record

## Next (autonomous continuation)

1. Bank the unchanged P1 evidence and report updates
2. Explain the 0% cache-hit result quantitatively from exact tensor sizes and
   deterministic reuse-distance simulation
3. Select the simplest promising cache policy and add storage/dequant/cache
   metrics before another real run
4. Run exactly two new tokens; require `[9703, 21615, 220]` plus meaningful
   cross-token reuse
5. Run the full eight-token golden only after P2 passes correctness and reuse
6. Evaluate prefetch only after useful cache residency is demonstrated

## Non-goals this weekend (unless free)

- Custom Metal kernels
- Server
- M2 / RAID
