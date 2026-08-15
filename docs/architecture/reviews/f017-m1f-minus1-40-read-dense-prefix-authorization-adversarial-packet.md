# F017 M1-F(-1) 40-Read Dense-Prefix Authorization Adversarial Packet

## Requested decision

Decide only whether `DPREFIX-REAL-1` is ready for exactly one 40-read real
dense-prefix execution.

Required verdict:

- `GO FOR ONE DENSE-PREFIX M1-F(-1) REAL CAPTURE`
- `GO WITH REQUIRED FIXES`
- `NO-GO`

This packet performs and authorizes no checkpoint access by itself. The attempt
is machine-authorized but remains unconsumed, unexecuted, and pending this
independent review. Representative M1-F0 cannot auto-chain.

## Review boundary

The event consumes frozen prompt `Hello` / token 9703 at position 0, executes
embedding plus complete dense layers 0–2, retains the exact layer-3 entry hidden
state, and stops. It excludes layer-3 attention/routing, experts, logits, output
head, token generation, M1-F0, M1-F, M1-G, and P1.

## Load-bearing artifacts

| Artifact | SHA-256 |
|---|---|
| Preparation-contract v2 | `32eeb9e7a90dd45abcedc0014d4c6bb533f8caec4613e962817b1e2b44303ac4` |
| 40-read allowlist | `c9c1540ea1cc9e69344ed9f3dcc4eb8ba1e5c15e3d55c1bccdec00eeb1db36aa` |
| Q4/Q6 identity gates | `08ef8e534136b2e0f50429d1301462b5fa295cbe9bdf941ba4180846237852db` |
| Retention-at-creation | `89dd470bda3c9c312ca59d3d9b798016f83f1a810339840b427e7e6a16c679c1` |
| Independent oracle | `0a54aa957e8b768108e4d8bc8c6e2a84cb48fbb3e0c93414c308112e88b3e816` |
| Real Tier-B | `9d1a6cc20ce8325fe8395334416f5ebcf980b72f02c6a0b44dc3240e0810024a` |
| Numerical/repeat | `4a9f2f29689b8c20259ebadd46a0038008895ea173bf024b2ab805d35b7aa488` |
| Dispatch | `d430b7dcc23d98d1b339315443f7868d6f8dd7e3e7c389ebae7d24ecae45e267` |
| Lifecycle | `2b6fd4ac70ea83fb80bcfba98d36dd5685ebf324839cdabbb0c782edd6197771` |
| Host admission | `66b23ee64dca045a90b1611b58aa2eba4ac9981c28b0e32dfe142e4bf95fa289` |
| Execution evidence schema | `68345be6a83b0c92371c36f3150f5442e036fe8c993c6a5097c9aefb4951d737` |
| Cross-artifact consistency | `5e169c810a010fc7064f92328d708be7a64608bd69657c65adbe5c9f9577c965` |
| Execution config v2 | `1335ebb3e617ad1ca9e2c39cf10f3286c9be8acfc99c2aa834c0a8bbbe0878e7` |
| Authorization binding | `47efe5f2ac4d4c31443077a7cc8ffdc6618926a6c0e656d6aee7a74a5ea69956` |
| Attempt ledger | `6f436cb859a80807afa261413f1f467e6492fd2744efbfda96a03901235a71ca` |
| Preflight evidence | `33b522ebd0df6be86c2cfd224e71edbbb72ea1b06a68d3e953910e1428ec5fb7` |

The predecessor blocker remains immutable at
`63b9fa5c8d6960c787f9bebeb0c88db2e8796c944b3482cd588d2743da57137f`.
The v2 contract does not infer reuse from hashes; it reads all 40 tensors fresh.

## Independent checks requested

1. Confirm the previous reuse blocker is preserved, not bypassed or relabeled.
2. Independently regenerate all 40 catalog/map entries and the family census
   F32 12, Q8_0 12, Q5_K 12, Q6_K 3, Q4_K 1.
3. Recompute packed bytes `1,431,263,232` and aggregate decoded-f32 volume
   `8,504,653,824`.
4. Confirm no layer-3, router, expert, output-head, duplicate, adjacent-layer,
   or wildcard tensor can be read.
5. Confirm Q4 `token_embd.weight` must match packed
   `3e4c34141f918333883442b8ff44c78c9927295ae16378047a8a36edeb7ed5ef`
   and decoded
   `e2cff562131674156704ca21b2b6e850337c2e5d8948b4dcc9f14676ecf8f2c1`.
6. Confirm Q6 `blk.0.ffn_down.weight` must match packed
   `845b4fd6b5d290506e576ca5099336bae7d28f3ebfcec964ed2136c3ea4a8ede`
   and decoded
   `ff26151a7997379c1713b90852fdbfd8301b36d5d89a1c3bb623b9b8f273483a`.
7. Verify these are terminal identity-confirmation gates, not repeat decoder
   qualifications, and a mismatch cannot trigger retry or substitution.
8. Verify ledger arithmetic is actual-read based: `59+N`, with `59→99` only
   after all 40 payloads.
9. Verify the 27 GiB floor follows the conservative 40-read double-residency
   liveness bound and has not been lowered to fit a host.
10. Verify the independent oracle is Python/NumPy-only, finalized before
    candidate construction, and rehashed after candidate teardown.
11. Verify Tier-B and repeat thresholds predate the real event and were not
    tuned from Q4/Q6 observations.
12. Verify exactly ten complete candidate repeats and full load-bearing stage
    surfaces are required.
13. Verify native dispatch is measured and attributed; synthetic 28 is not
    frozen as a real expected count.
14. Verify runtime ownership, streams, registrations, in-flight work, stale
    generations, and singleton state fail closed unless reconciled.
15. Verify successful execution must create immutable canonical hidden-state
    bytes and manifest at execution time; a hash alone is ineligible for reuse.
16. Verify `DPREFIX-REAL-1` is authorized/unconsumed/unexecuted and review
    releases execution without mutating authorization state.
17. Verify attempt consumption occurs immediately before the first positional
    read and no automatic retry or representative M1-F0 continuation exists.
18. Verify all terminal classes and cross-artifact consistency rules prevent a
    stale attempt ledger or a partial-read event from false-PASSing.

## Expected checkpoint-free state

- Canonical preflight: `READY_TO_EXECUTE_DENSE_PREFIX_REAL_CAPTURE`.
- Real checkpoint access in preparation: 0.
- Current cumulative real-payload ledger: 59.
- Dense-prefix execution: false.
- Representative M1-F0: blocked.
- Final-head Apple CI binding: `PENDING_FINAL_HEAD_CI`.
