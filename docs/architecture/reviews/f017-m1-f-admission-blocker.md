# PulsarMLX F017 M1-F Admission Blocker

## Verdict

`BLOCKED — M1-F ADMISSION PACKAGE`

Layer 3 is the correct boundary candidate, but the package cannot truthfully
freeze both a newly independent input and an exact eight-expert tensor
allowlist without a new bounded real oracle-admission decision.

## Reconciled accepted state

- accepted evidence-banking head:
  `283ba594cca002a003f43ec172a3af2af9e59295`
- M1-E evidence SHA-256:
  `0f85ee81205836a492a9dd44d71e56dc6ce46b22a5064f51c5f37dd561f292a9`
- M1-E attempts 1 and 2 remain immutable rejected records; attempt 3 remains
  the one accepted real expert record.
- final-head CI `31722980091` is green at the exact accepted head.
- worktree and local/remote parity were clean/exact at sprint entry.
- no real M1-F payload was read and no M1-F candidate or oracle was executed.

The post-runtime commits are evidence, review, validator-test, task-ledger, and
handoff changes. They introduce no unexplained production compute, decoder,
lifecycle, path resolver, or runner drift.

## Frozen boundary choice

The selected boundary is `blk.3`, position 0, hidden width 6,144, one complete
GLM-DSA MoE transformer layer. Layer 3 is representative and includes the
accepted M1-E expert 15. Its historical route is
`[15, 177, 233, 41, 166, 26, 10, 152]`.

That route is not a free-standing architecture constant. It was observed for
the historical Feature 016 input `token_embedding[9703]`, residual SHA-256
`5c3e4ebc2d5909c5e6f556bdc00f50130b705a3fb3fe7150f4f24bf7c81bbb80`,
and attention midpoint SHA-256
`7a19b425ae8bdf0009c84daa61c80fb054bffdf5fa0f3f2291d5af87cc7832aa`.

## Exact conflict

For a new independently generated input, routed expert identity is:

```text
top8(sigmoid(router_matrix × rms_norm(attention_residual(input))) + router_bias)
```

The GGUF catalog contains shapes, quantizations, shards, offsets, and tensor
names, but not the values needed to evaluate this function. Therefore:

1. a newly generated input does not inherit the historical route;
2. freezing the old IDs would create a potentially false allowlist;
3. allowing all 256 experts or a wildcard prefix violates the requested access
   boundary;
4. learning the new route requires reading and computing the real layer-3
   attention/router oracle boundary, which is outside this prompt.

The conflict occurs before decoder, numerical-tolerance, dispatch, lifecycle,
or CI qualification. No mechanical implementation can remove it without
changing authority or a stated requirement.

## Operator decision required

Choose one separately reviewed path:

1. Authorize an oracle-only attention/router admission stage. It reads only the
   exact layer-3 attention/norm/router/bias payloads, performs no MLX candidate
   compute, banks the exact top-8 for the frozen new input, and stops. Package
   preparation can then bind only those eight experts.
2. Authorize recovery of the exact historical `token_embedding[9703]` bytes and
   explicitly permit that hash-bound input instead of a newly generated input.
   The old route must still be independently revalidated.
3. Review a two-stage contract: router-only selection first, followed by a new
   immutable eight-expert allowlist and separate real-layer authorization.

No option authorizes M1-F execution by itself.

## Mandatory exclusions

M1-F remains not authorized. No complete layer, second layer, logits, P1/P2,
golden-eight, or Feature 018 work was executed. M1-E and M1-D evidence remains
unchanged.

## Resolution amendment: M1-F0 protocol

The operator selected the separately reviewed two-stage path. The ordering
question is therefore closed at the architecture level:

1. M1-F0 freezes a new independent layer-3 input and performs only a bounded
   real attention/router oracle discovery.
2. Its accepted route artifact becomes the sole source of the exact eight
   routed experts.
3. M1-F admission then derives its expert tensor, access, and dispatch budgets
   from that immutable route.

This amendment does not supply a route, authorize M1-F0, or authorize M1-F.
T017-179 remains open until accepted M1-F0 evidence exists.
