# PulsarMLX F017 Post-M1-F0 Fix Remediation Report

## Verdict

`BLOCKED — POST-M1-F0 FIXES`

Primary blocker: `BLOCKED — M1-F0 ROUTER MARGIN NOT BANKED`

Blocker evidence:
`docs/architecture/reviews/evidence/f017-post-m1f0-router-margin-blocker-v1.json`
with SHA-256 `aede271f088d3cdc9cd6640dae07c03a8d3e06e981ec9972de23ca6de58fcca0`.

## Reconciliation

- Starting head: `df0f3a91244d944f0fe5a0f569b709ccfe631cc0`
- Accepted route evidence SHA-256: `980b6a78ae04b816e1f9e563790f5a2d123723292dd0432a0218972d0f80593e`
- Accepted attempt-2 evidence SHA-256: `0eb0030f0345b8b2cabca4b7e690177603ca29e21b0cfade3e0639e356d1b8f9`
- Accepted oracle package SHA-256: `ad4ab9d8f1c40e5bf8886ed404f1e07115560c10c53226dcc5497d8b6785388f`
- Accepted route: `[166, 78, 26, 186, 163, 199, 233, 177]`
- Router-score SHA-256: `3b4ff6cac287f53004c7cc6ceedb13f2403a6ce4426e30155005158e0e004dc4`
- Ranking SHA-256: `6a878c1db20997b16cff8efdb8659543c07974dcddd718957243c889d78a2ede`

The accepted route artifact, accepted attempt evidence, and surviving private oracle package retain only the score/ranking hashes, top-8 IDs, and selected routing weights. They do not retain the 256 router scores, complete ranking, or rank-9 score.

The routing weights cannot be substituted for scores. The frozen selection implementation ranks `sigmoid(logit) + bias`, while routing weights are reconstructed from the selected pre-bias sigmoid probabilities. They therefore cannot recover either rank-8 or rank-9 post-bias scores.

## Required margin fields

- Rank-8 expert: not recoverable from banked ranking values
- Rank-8 score: not banked
- Rank-9 expert: not banked
- Rank-9 score: not banked
- Exact margin: not evaluable
- Propagated perturbation bound: not evaluated because the required observed margin is absent
- Route-stability safety factor: not evaluable
- Route-stability verdict: blocked before evaluation

No score was invented, inferred from a cryptographic hash, or recomputed through an unbound path.

## Ordered downstream work

The prompt requires an immediate stop when the actual rank-9 score is not recoverable. Consequently the following were not reached:

- complete 39-payload quant-family table and qualification matrix;
- expert-166 manual slice derivation;
- all-eight generalized slice validation;
- accepted-validator amendment (the full historical commit resolves to `7ea94595f9003ed79ecdd188ad3cf643f530e089` but was not applied to immutable evidence in this blocked sprint);
- historical-route overlap amendment;
- source-backed dispatch derivation;
- next decoder-gate selection;
- Q6_K or multi-family decoder qualification handoff;
- internal GO review and adversarial delta packet.

## CI and access

- Accepted M1-F0 head CI: `31755118130`, green at `df0f3a91244d944f0fe5a0f569b709ccfe631cc0`
- New runtime/tooling changes: none
- Real checkpoint access during this sprint: `0`
- Q6_K qualification: not executed
- M1-F execution: false
- P1: blocked

## Exact next action

Operator review is required to define a separately authorized recovery gate that banks the complete canonical score vector, or to freeze a new input and repeat M1-F0 discovery. The existing hash alone cannot reveal rank 9, and the accepted normalized routing weights are not the ranked score representation.
