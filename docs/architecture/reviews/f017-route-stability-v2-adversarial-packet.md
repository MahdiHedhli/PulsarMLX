# F017 Route-Stability v2 Independent Adversarial Review Packet

## Requested verdict

Return exactly one:

- `GO FOR M1-F0 REPRESENTATIVE-FIXTURE PREPARATION`
- `GO WITH REQUIRED FIXES`
- `NO-GO`

A GO authorizes preparation only. It does not authorize checkpoint access.

## Bound package

- Starting SHA: `f70763efeabb38bfb9c1551d5a99470bc16a3466`
- Accepted M1-F0 route: `980b6a78ae04b816e1f9e563790f5a2d123723292dd0432a0218972d0f80593e`
- Analytical recovery: `1496b8a3ca26448145acbd107387aadbc11322fd93b71fcc5abd659d6e8e7686`
- v1 contract: `da05364470f7fc5fbdc930441be1ea269af01b6a87173df34e467bcc0b0df9d7`
- v2 candidate: `fd300f061307442c56af9ca3183f7485544ecb11752755074a330bb7b5f5f68c`
- Frozen ladder: `59c55a26d12ff9e0fdbe488608c4cb7ffb1a2082d322dec85ee5ef37719c3ed2`
- Ladder generator: `0097e78a55cf5d8911a2715cebf7e024606a69713d08d7f3bc07ac04864d60f0`
- Estimator contract: `440b5dd26d20753275db36159755e06b1fc20e740d1689d774fe90b1289e7954`
- Checkpoint access: `0`

## Central blocker

The v2 theorem and independent implementations are reviewable, but the accepted
real evidence omitted the antecedents needed to instantiate the tighter formula:
router row differences, RMSNorm radial/non-radial bounds, and separate reduction
terms. The retrospective therefore uses the exact fail-closed v1 fallback. It is
not evidence that fixture 1 passes v2, and it must not be used to execute the
frozen ladder.

## Reviewer attacks

Please answer:

1. Is the estimator cryptographically bound to the actual fixture family?
2. Is the random-normal support analysis correctly limited to Monte Carlo rather
   than presented as a theorem?
3. Does empirical reconciliation diagnose looseness without fitting v2?
4. Is the retained portion of the v1 term decomposition exact, and is the omitted
   portion identified honestly?
5. Is the RMSNorm radial decomposition rigorous?
6. Is direct `(w_i-w_j)` treatment rigorous under the stated componentwise bound?
7. Are interval-local sigmoid derivative bounds valid and outward rounded?
8. Is the pairwise bound conservative?
9. Does the full selected/unselected theorem guarantee exact top-8 set identity?
10. Are independent router reduction errors retained safely?
11. Is the candidate independent of fixture-1's observed margin?
12. Is the two-tier headroom policy justified, and which tier—if either—should a
    future M1-F admission require?
13. Do the deterministic and 100,000 randomized tests expose any under-bound?
14. Are the primary and independent scalar implementations genuinely independent
    enough for this phase?
15. Is the only legitimate fixture-1 conclusion still `UNSUITABLE UNDER V1`?
16. Does the fallback estimator establish anything beyond continued
    random-normal underpowering under v1-equivalent information?
17. Are correlated low-rank and block-AR(1) scientifically defensible research
    candidates without route-outcome leakage?
18. Is the representative-plus-stress policy appropriate?
19. Is route stability correctly classified as a cost-and-meaningfulness gate,
    while M1-F exact route equality remains the semantic gate?
20. Does the antecedent-retention blocker require NO-GO, or can a future
    checkpoint-free package be prepared without reclassifying historical data?

## Prohibited conclusions

This packet does not support replacing v1, reclassifying fixture 1, executing the
frozen ladder, qualifying Q6_K, authorizing M1-F, or advancing P1.
