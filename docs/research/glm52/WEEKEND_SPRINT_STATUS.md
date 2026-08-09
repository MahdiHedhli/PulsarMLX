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
| 6 | Exact cache working-set diagnosis + deterministic simulator | this focused simulator commit |
| 7 | Compact fail-closed shared-expert MLX residency + split evidence fields | pending focused runtime commit |
| 8 | First P2 attempt stopped in stack 1 and retained as superseded | pending decoder-priority commit |

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

1. Qualify a whole-matrix NumPy IQ2_XXS decoder against exact scalar f32 bits
2. Integrate one-read/one-decode matrix execution behind explicit decoder modes
3. Run the bounded ladder through a P1 full stack and re-profile hotspots
4. Re-evaluate shared-cache value, then retry P2
5. Run the full eight-token golden only after P2 passes correctness and reuse

## Cache diagnosis result

- P1's 8-GiB decoded LRU held 170 of 2052 per-stack tensor slabs.
- One decoded stack is 96.1875 GiB; identical sequential replay has an LRU
  stack distance of 2051, so decoded LRU remains 0-hit through 48 GiB.
- One compressed stack is ~8.4475 GiB. At 16 GiB it can avoid storage reads on
  identical replay, but it still redequantizes all 2052 slabs.
- All shared experts occupy 10.6875 GiB decoded and are guaranteed to repeat.
  A protected shared tier at a 16-GiB logical cap predicts 228 decoded hits on
  the next stack.
- P1 did not record routed IDs, so the committed C09 trace is explicitly a
  policy-mechanics proxy rather than a P1-to-P2 overlap measurement.
- Implemented next step: compact evaluated MLX/f32 shared-expert residency with
  fail-closed MLX, transient routed-matrix release, and current/peak
  RSS/storage/dequant/MLX counters. Real-checkpoint reuse remains pending P2.

## Non-goals this weekend (unless free)

- Custom Metal kernels
- Server
- M2 / RAID
