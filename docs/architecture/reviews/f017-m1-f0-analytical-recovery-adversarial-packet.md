# F017 M1-F0 analytical recovery adversarial packet

## Requested verdict

Return exactly one:

- `GO FOR BOUNDED DECODER QUALIFICATION`
- `GO WITH REQUIRED FIXES`
- `NO-GO`

Route stability did not qualify, so a correct review should reject decoder progression while judging whether recovery and retention are trustworthy.

## Immutable bindings

- accepted route: `980b6a78ae04b816e1f9e563790f5a2d123723292dd0432a0218972d0f80593e`
- accepted attempt 2: `0eb0030f0345b8b2cabca4b7e690177603ca29e21b0cfade3e0639e356d1b8f9`
- recovery config: `3d291a412ac218fa6840d865285b40bad4e5a74833985b993b1c7a0cdf9e78b8`
- recovery authorization: `cb48b0c1cdeae063fa408aad1aae1b1cb39918a66c519d0d32d2fd8e8378bbcd`
- recovery tooling commit/tree: `4aa6e32df646d55e398c846dae566df4ceea9faf` / `8b77dc0d24fbb039b88e4125589062f54789f637`
- recovery artifact: `1496b8a3ca26448145acbd107387aadbc11322fd93b71fcc5abd659d6e8e7686`
- route-stability contract: `da05364470f7fc5fbdc930441be1ea269af01b6a87173df34e467bcc0b0df9d7`
- retention contract: `3a218e0d32f30f61ab3850d6b5b8d6114b998729a1735486e27d8e352e9d2d63`

## Recovery result

The sole recovery used one shard open and twelve positional reads. It reproduced exactly the router scores `3b4ff6cac287f53004c7cc6ceedb13f2403a6ce4426e30155005158e0e004dc4`, ranking `6a878c1db20997b16cff8efdb8659543c07974dcddd718957243c889d78a2ede`, ID bytes `44eb8597e56fe57ef3c045dfa979e80f76e85afd053c89b48653244525cf41ca`, weights `e1e419537136ffb660775732aa2bfb17a6b16a941b2fbacb775aff0d77d9fd18`, attention output `9c7c150dfef3bf284e94fe1679844879bc1a9ec464c8161f9cb6ca71cc4f8911`, residual `1f5e2e469f5d118f8cf7fee7f4199b2912530823eb2d0a65cea53e9e77de0fc7`, router-normalized input `98275027e2427276822b84fc0c7747014b0f4d79b40c07e6d8267060db7762e1`, and IDs `[166, 78, 26, 186, 163, 199, 233, 177]`.

It performed zero expert work, zero MLX candidate dispatches, and zero M1-F execution. The cumulative payload ledger moves from 25 to 37.

## Route stability

- rank 8: expert 177, score `35.11137933207887`
- rank 9: expert 41, score `35.107621597983275`
- margin: `0.0037577340955934346`
- B8/B9/sum: `0.0033056307117125656` / `0.0033937161438668565` / `0.006699346855579422`
- safety factor: `0.5609105150995247`
- result: `ROUTE_STABILITY_NOT_QUALIFIED`

No threshold was retuned. Downstream quantization, slice, shared-expert, dispatch, Q6_K, and M1-F work stopped.

## Reviewer attacks

1. Was recovery byte-identical to accepted M1-F0?
2. Did recovery add evidence without creating new route trust?
3. Are complete score/ranking values and canonical bytes retained?
4. Is the cutoff margin exact?
5. Was the rule frozen before observation?
6. Is the propagated bound sound?
7. Does failed stability correctly block M1-F?
8. Is overlap analysis appropriately limited?
9. Is executed-validator identity accurate?
10. Is the retention policy sufficient?
11. Is the payload ledger complete?
12. Did forbidden downstream work remain stopped?

M1-F remains `PREPARED / NOT AUTHORIZED`; Q6_K is unexecuted; P1 is blocked. The next technical phase is separately reviewed new-input/M1-F0 discovery, not decoder qualification on this route.
