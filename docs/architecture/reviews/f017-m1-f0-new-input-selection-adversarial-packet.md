# F017 M1-F0 New-Input Selection Adversarial Packet

## Requested review

Please review the negative admission conclusion. This packet does not request
authorization for real checkpoint access. Requested verdicts are:

- `CONFIRM FIXTURE FAMILY UNSUITABLE`
- `GO WITH REQUIRED FIXES`
- `NO-GO — EVIDENCE DEFECT`

## Immutable inputs

- accepted route: `980b6a78ae04b816e1f9e563790f5a2d123723292dd0432a0218972d0f80593e`
- analytical recovery: `1496b8a3ca26448145acbd107387aadbc11322fd93b71fcc5abd659d6e8e7686`
- stability contract: `da05364470f7fc5fbdc930441be1ea269af01b6a87173df34e467bcc0b0df9d7`
- corrected payload ledger: `4c18419f4fdffce931ddf8bfab6a15164cce65578ad830290ed0c1d636f152a5`
- precommitted ladder: `59c55a26d12ff9e0fdbe488608c4cb7ffb1a2082d322dec85ee5ef37719c3ed2`
- estimator contract: `440b5dd26d20753275db36159755e06b1fc20e740d1689d774fe90b1289e7954`
- estimator result: `91a80f4634e6fedf6d3a26a91d7576e0f411e110b13dd282b6633d873c6f517d`
- blocker record: `b0671f308586c1f6f9296b4b045d3bcb7c7764e04f555f096db5a3f2085d1839`
- analytical retention v2: `d80260e9c146dca4fa10987b12f681655c1d476d1b9b2a91ca16479ec97e8c21`
- decoded reuse contract: `e061bb16af5bda05c39fd439c76c17447e2af0093369bb00fb14062425cead16`

## Frozen ladder

The family preserves the independently chosen fixture-1 semantics: layer 3,
position 0, DSA range-fill, PCG64 normal f32 body, and a fixed stress prefix.
The complete ordered seeds are 17017007 through 17017014. Every fixture and
component hash is retained in the ladder artifact. No real route outcome was
observed.

Selection is the first qualifying ordinal. Any future execution would still
evaluate and bank every ordinal. The stability rule remains `margin > B8+B9`
and `S >= 4.0`.

## Planning result

The frozen model resamples the already-banked pre-bias probability distribution,
keeps the complete banked expert-bias vector fixed, stable-ranks the 256 scores,
and divides the cutoff margin by conservative banked score-error bounds. In
1,000,000 PCG64 samples:

- qualifiers: 0
- predicted per-fixture rate: 0
- Wilson 95% upper rate: 0.000003841444063944942
- 99th-percentile S: 1.0438002749662738
- maximum sampled S: 3.129417274314236
- optimistic eight-fixture success probability from the upper rate: 0.00003073113932738902
- pre-frozen adequacy threshold: 0.9

The estimator is deliberately labeled planning-only. Its most important
limitation is that one banked fixture cannot identify expert-specific
input/router correlations. That uncertainty does not support spending a real
ladder whose optimistic modeled success probability is orders of magnitude
below the threshold.

## Attack questions

1. Does the 45-payload ledger correctly distinguish tensor payloads from M1-B
   identity/catalog/header reads and include repeated qualification/recovery?
2. Was fixture 1 retired without invalidating its accepted oracle route?
3. Were the family, seeds, bytes, selection rule, and stopping rule frozen
   without route-outcome leakage?
4. Is the bootstrap-with-fixed-bias estimator defensible as conservative
   planning evidence, and are its limitations stated strongly enough?
5. Does the zero-success Wilson bound support the hard stop?
6. Could positive fixture correlation make the independent ladder calculation
   optimistic rather than conservative?
7. Is the 0.9 ladder-adequacy threshold demonstrably pre-frozen?
8. Does analytical-retention v2 really allow future phases to declare new
   load-bearing quantities and fail PASS when omitted?
9. Is the proposed one-read immutable decoded package sufficiently bounded for
   a future, separately reviewed ladder?
10. Should the next work redesign the checkpoint-independent fixture family,
    or research a mathematically tighter pre-candidate error bound without
    weakening the frozen contract?

## Stop state

Real checkpoint access in this phase is zero. No ladder was executed. Q6_K,
M1-F, and P1 remain blocked.
