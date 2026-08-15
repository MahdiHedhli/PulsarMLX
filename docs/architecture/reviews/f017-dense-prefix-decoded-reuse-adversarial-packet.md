# PulsarMLX F017 Dense-Prefix and Decoded-Reuse Adversarial Packet

## Requested review boundary

Review the checkpoint-free preparation descended from reviewed head
`8031020f2e9480712ff185a53b2e565d25dc6a24`. No real checkpoint access, decoder
qualification, dense-prefix execution, route discovery, M1-F, M1-G, or P1 is authorized.
The real-payload ledger must remain 57.

The authoritative preparation surfaces are:

- routing-contract v3.0.1: `c5662a611abc000703606d799a7214ee27e39c556bc6595f217c86498e944a85`
- decoded-reuse v2 contract: `3a947427cfc285119fe9b8bcc910e26fdde4cdd6599711fe3f6b5df14d95c71c`
- dense-prefix inventory: `eaf54506f5bd45ef41f223224096a253f6fa6c5e2ad3bf94971c18eb09f6b21b`
- prompt/token package: `c05ba1cba69535cd17daf9f4326e5e1db25ffafe504c53712aa548f251741dff`
- residency contract: `56ab1eae69b45f9ae97f98e1d36dfa124e080a6dc82573013cc57782bce1ac76`
- real Tier-B contract: `9d1a6cc20ce8325fe8395334416f5ebcf980b72f02c6a0b44dc3240e0810024a`
- oracle-source contract: `0a54aa957e8b768108e4d8bc8c6e2a84cb48fbb3e0c93414c308112e88b3e816`

## Questions for independent attack

1. Is decoded reuse scientifically safe under the mixed oracle/candidate policy?
2. Does the immutable source plus separately hashed candidate import preserve meaningful oracle/candidate independence?
3. Is the dense-prefix boundary minimal and sufficient to produce layer-3 entry state?
4. Is P-MIN/token 9703 genuinely frozen without route-outcome cherry-picking?
5. Are all 40 tensors independently and completely derived with forbidden tensor families absent?
6. Are 1,431,263,232 packed bytes and 8,504,653,824 decoded-f32 bytes correct?
7. Does the 27-GiB double-residency admission floor conservatively bound all preparation categories without pretending to be measured telemetry?
8. Is the source-hashed Python/NumPy oracle credible and guaranteed to complete before candidate creation?
9. Is one mechanically selected Q6_K payload sufficient for format qualification?
10. Is one Q4_K payload sufficient?
11. Can accepted Q4_K format lineage be reused for M1-G while still requiring output-tensor packed identity?
12. Is Q4_K then Q6_K the correct separately authorized sequence?
13. Are preflight, `EXECUTION_STARTED`, no-retry, and failure-class semantics correct?
14. Does private canonical layer-3 state retention prevent another analytical recovery?
15. Does the representative M1-F0 handoff bind the exact accepted hidden state and fail closed on H=2 failure or substitution?
16. Can route-independent M1-F consume a future representative route without schema redesign or premature expert binding?
17. Are M1-G/P1 preparations non-authorizing and appropriately incomplete?
18. What exact single real-access event, if any, should be authorized next?

## Specific falsifiers

Try to cause stale package reuse, writable aliasing, partial package replacement,
checkpoint/catalog/map drift, decoder substitution, route-conditioned prompt changes,
expert/router tensor leakage, false one-payload format generalization, underestimated
residency, candidate-influenced oracle output, attempt non-consumption after payload access,
alternate hidden-state substitution, or Q4/Q6/dense auto-chaining.

## Requested verdict

Return one of:

- `GO FOR NEXT SEPARATELY AUTHORIZED REAL GATE`
- `GO WITH REQUIRED FIXES`
- `NO-GO`

A GO does not itself authorize checkpoint access.
