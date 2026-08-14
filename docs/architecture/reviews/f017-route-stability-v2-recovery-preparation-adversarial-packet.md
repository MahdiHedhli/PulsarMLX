# F017 Route-Stability v2 Recovery-Preparation Adversarial Packet

## Requested verdict

Return exactly one:

- `GO FOR ONE V2 ANTECEDENT RECOVERY`
- `GO WITH REQUIRED FIXES`
- `NO-GO`

A GO reviews this preparation package only. It does not itself authorize or
execute checkpoint access.

## Bound package

- Preparation base: `ab3d991260d9f262430731e762282a7b9cd8995b`
- Tooling commit: `6b56dc88f89b92ebaeb525a35e48b3c2c1bc8fec`
- Tooling tree: `61eda4e19c57b0ddeea92a73468cbb5edff6019e`
- v2 candidate: `fd300f061307442c56af9ca3183f7485544ecb11752755074a330bb7b5f5f68c`
- final v2: `36adbdcffeeb361638ec80258b912711b17a671276d68cf0129826e1ae042ac7`
- predecessor adversarial packet: `cd16683a35bfcaa388840b139e3dac1b265476991f98c4f9e3343b43aaf4dc9e`
- accepted route: `980b6a78ae04b816e1f9e563790f5a2d123723292dd0432a0218972d0f80593e`
- accepted analytical recovery: `1496b8a3ca26448145acbd107387aadbc11322fd93b71fcc5abd659d6e8e7686`
- historical v1: `da05364470f7fc5fbdc930441be1ea269af01b6a87173df34e467bcc0b0df9d7`
- retention manifest: `bd3cc6c10faee0d8c8072000403bbef68354286515482a6b78869ab02be81e13`
- execution config: `649a53630be246af11270f1cad19bdb8a7ccabf06e928febfe6cbc282dd4c7e2`
- current/future ledger: `45 -> 57` only after one successful authorized recovery
- checkpoint access during preparation: `0`
- authorization issued: `false`

## Narrow reviewer attacks

Please answer:

1. Did clarification 1 correctly account for bias-addition rounding?
2. Is ordered top-8 stability now mandatory and sufficient?
3. Did any unrelated v2 mathematics change?
4. Is final v2 still conservative?
5. Is `H = 2` still clearly engineering rather than mathematical?
6. Is the support-ceiling artifact appropriately labeled?
7. Is the expert-slice cross-check sound?
8. Is the retention manifest sufficient to prevent another recovery?
9. Are direct pre-sigmoid logits retained or rigorously recoverable?
10. Are exactly 12 payloads necessary and sufficient?
11. Are every accepted identity and route hash bound?
12. Can recovery accidentally choose a new route?
13. Does recovery consume an attempt?
14. Is `45 -> 57` ledger arithmetic correct?
15. Does synthetic recovery prove package semantics?
16. Does the result schema preserve historical v1 immutability?
17. Is the package ready for one separately authorized 12-payload analytical
    recovery?

## Required falsification targets

Try config, tensor, input, stage, score, ranking, route-order, retention,
private-artifact, authorization, ledger, and tooling/tree substitutions. Confirm
that preflight remains checkpoint-free and that the execution entry point cannot
run without a distinct immutable authorization matching this exact config.

## Explicit exclusions

This packet does not authorize a payload read, route discovery, route attempt,
frozen-ladder execution, Q6_K qualification, M1-F, P1/P2, golden-eight, or
Feature 018.
