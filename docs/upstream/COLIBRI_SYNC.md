# Colibri selective review log

| Date | Action | Revision | Result |
| --- | --- | --- | --- |
| 2026-08-09 | Initial source and license qualification | `8f512fc8c2f48ffa18cd624cd4a5bcaae4a4abfc` | Design reference only; no code copied or adapted |

## Future review process

1. Review only when a measured PulsarMLX bottleneck maps to a relevant Colibri
   subsystem.
2. Pin the candidate upstream revision and inspect its license, implementation,
   tests, and call sites again.
3. Classify the idea as design-only, clean reimplementation, attributed
   adaptation, or not applicable.
4. Prefer clean implementation behind PulsarMLX contracts. If code adaptation
   is justified, preserve Apache-2.0 obligations and record exact provenance.
5. Add independent correctness, interruption, memory-pressure, and performance
   tests before enabling the path.
6. Compare only PulsarMLX measurements collected under its committed protocol.

There is no automatic sync, subtree, vendoring relationship, or promise to
track every Colibri change.
