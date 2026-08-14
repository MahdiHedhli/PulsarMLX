# PulsarMLX F017 M1-F0 Analytical Recovery + Post-Route Report

## Outcome

`BLOCKED — M1-F INPUT ROUTE MARGIN`

Accepted M1-F0 analytical values were recovered byte-for-byte, but rank-8/rank-9 separation does not clear the pre-frozen route-stability contract. The accepted route remains valid oracle evidence; it is unsafe for production M1-F recomputation under the current contract.

## Source and evidence

- starting blocker head: `fe4d486f39099db3aa80b214e3434d1565cc50d9`
- recovery execution head: `c101328c0d21ae98f9e1bdfbf8fcc1b35188df0f`
- final package head: commit containing this report, bound by final Apple-native CI
- accepted route: `980b6a78ae04b816e1f9e563790f5a2d123723292dd0432a0218972d0f80593e`
- accepted attempt 2: `0eb0030f0345b8b2cabca4b7e690177603ca29e21b0cfade3e0639e356d1b8f9`
- blocker: `aede271f088d3cdc9cd6640dae07c03a8d3e06e981ec9972de23ca6de58fcca0`
- recovery config/authorization: `3d291a412ac218fa6840d865285b40bad4e5a74833985b993b1c7a0cdf9e78b8` / `cb48b0c1cdeae063fa408aad1aae1b1cb39918a66c519d0d32d2fd8e8378bbcd`
- recovery artifact: `1496b8a3ca26448145acbd107387aadbc11322fd93b71fcc5abd659d6e8e7686`
- private package: `10cb514b9cb5c8a5ba3c87e8aeea8357be9d5619f51100028757ba28d5bdca85`

## Recovery accounting

One shard open, 12 reads/payloads, 139,217,920 compressed bytes, and 666,430,464 decoded bytes. Expert payloads/computation, MLX candidate dispatches, and M1-F execution were all zero. The cumulative payload ledger is 25 before and 37 after recovery.

## Reproduced identities

- router scores: `3b4ff6cac287f53004c7cc6ceedb13f2403a6ce4426e30155005158e0e004dc4`
- ranking: `6a878c1db20997b16cff8efdb8659543c07974dcddd718957243c889d78a2ede`
- ID bytes: `44eb8597e56fe57ef3c045dfa979e80f76e85afd053c89b48653244525cf41ca`
- weights: `e1e419537136ffb660775732aa2bfb17a6b16a941b2fbacb775aff0d77d9fd18`
- attention output/residual: `9c7c150dfef3bf284e94fe1679844879bc1a9ec464c8161f9cb6ca71cc4f8911` / `1f5e2e469f5d118f8cf7fee7f4199b2912530823eb2d0a65cea53e9e77de0fc7`
- router-normalized input: `98275027e2427276822b84fc0c7747014b0f4d79b40c07e6d8267060db7762e1`
- selected IDs: `[166, 78, 26, 186, 163, 199, 233, 177]`

## Route stability

- contract: `da05364470f7fc5fbdc930441be1ea269af01b6a87173df34e467bcc0b0df9d7`
- condition: `m > B8+B9`, minimum safety factor `4.0`
- rank 8: expert 177 at `35.11137933207887`
- rank 9: expert 41 at `35.107621597983275`
- margin: `0.0037577340955934346`
- B8/B9/sum: `0.0033056307117125656` / `0.0033937161438668565` / `0.006699346855579422`
- safety factor: `0.5609105150995247`
- verdict: `ROUTE_STABILITY_NOT_QUALIFIED`

No post-observation retuning occurred.

## Retention, overlap, and validator amendment

Contract `3a218e0d32f30f61ab3850d6b5b8d6114b998729a1735486e27d8e352e9d2d63` now requires canonical values and hashes for selection-bearing PASS evidence. The backward audit marks R7-R12 sufficient, M1-D/M1-E hash-only with no future dependency, and recovered M1-F0 sufficient.

The historical and accepted routes overlap at 166, 26, 233, and 177; their bias ranks are 3, 2, 4, and 18. Exact hash reproduction and path isolation establish provenance. Input-independent bias plausibly explains recurrence but does not itself prove independence.

The validator amendment binds commit `7ea94595f9003ed79ecdd188ad3cf643f530e089`, tree `f38b98731ca2e6540a06e6c2e7d017b3f68dda19`, path `scripts/research/validate_f017_m1f0_package.py`, and file SHA `18757731da53b0e2dc8ec425ab02fdbcad8e108cc9d64f3b493b741ad4aeb9bf` without modifying accepted values.

## Mandatory stop

Because stability failed, the 39-payload table, decoder disposition, expert-slice proofs, shared-expert validation, dispatch contract, admission-ordering audit, Q6_K handoff, and M1-F package were not advanced. Q6_K qualification and M1-F execution are false. P1 remains blocked.

Internal verdict: `GO FOR ANALYTICAL-RECOVERY ADVERSARIAL REVIEW`.

Adversarial packet: `docs/architecture/reviews/f017-m1-f0-analytical-recovery-adversarial-packet.md`.

Exact next action: independent adversarial review of recovery and failed-stability disposition. Any later progression requires a separately reviewed new frozen input and fresh M1-F0 discovery; it must not weaken the contract or reuse this unstable route for M1-F.
