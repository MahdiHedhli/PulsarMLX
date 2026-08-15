# PulsarMLX F017 Dense-Prefix + Decoded-Reuse Preparation Report

## Outcome

`READY FOR DENSE-PREFIX PACKAGE ADVERSARIAL REVIEW`

- Reuse: `READY`
- Dense prefix: `READY_FOR_REVIEW`
- Q6_K: `PACKAGE_READY`
- Q4_K: `PACKAGE_READY`
- Downstream: `PREPARED`

## Provenance and phase boundary

- Starting reviewed SHA: `8031020f2e9480712ff185a53b2e565d25dc6a24`
- Final implementation SHA: resolved by the final-head CI run-to-SHA binding; this report
  intentionally does not attempt a self-referential commit identity.
- Stale packet head `dd52d38` was unpublished/unresolvable and is not an authority.
- Reviewed operator CI: run `31851111967` at exact SHA `8031020f2e9480712ff185a53b2e565d25dc6a24`, both Apple jobs successful.
- Estimator heuristic note: central percent-range intuition was `CONFIRMED`; the
  eight-fixture viability conclusion was `REFUTED`; the pre-frozen rule correctly returned
  `EXISTING_FROZEN_LADDER_NOT_VIABLE`.
- Routing-contract v3.0.1 remains
  `c5662a611abc000703606d799a7214ee27e39c556bc6595f217c86498e944a85`.
- Real checkpoint access: 0. Real-payload ledger: 57, unchanged.

## Decoded-tensor reuse

- Contract: `3a947427cfc285119fe9b8bcc910e26fdde4cdd6599711fe3f6b5df14d95c71c`
- Safety disposition: `DECODED_REUSE_READY_FOR_FUTURE_AUTHORIZATION`
- Independence disposition: `MIXED_POLICY`
- No-reuse economics for eight route inputs: 96 payload reads.
- Immutable reuse economics: 12 reads once; 84 reads, 974,525,440 compressed bytes,
  and 4,665,013,248 decoded bytes avoided (87.5%).

| Use case | Policy |
|---|---|
| Future multi-fixture oracle route discovery | Immutable canonical decoded package may be reused after separate authorization. |
| Dense-prefix candidate | Separate, hashed, read-only copy/import with lifecycle evidence; no shared writable alias. |
| Dense-prefix oracle | Immutable canonical source in an independent mapping/process; oracle package completes before candidate creation. |
| Quant decoder qualification | No decoded-truth reuse; A/B/C independently consume the exact packed payload. |

Mutation, descriptor drift, tensor reorder, relocation after start, symlink escape,
checkpoint/catalog/map drift, decoder substitution, and consumer mutation all fail closed.

## Dense-prefix boundary and input

Boundary name: `F017 M1-F(-1) REAL DENSE-PREFIX LAYER-3 ENTRY-STATE BOUNDARY`.
It performs token embedding and complete dense layers 0, 1, and 2, then retains the
layer-3 entry hidden state. It is not a fixture capture and contains no MoE routing.

The anti-cherry-picking policy freezes the pre-existing public-safe P-MIN input:

- prompt: `Hello`
- prompt SHA-256: `185f8db32271fe25f561a6fc938b2e264306ec304eda518007d1764826381969`
- tokenizer output: `[9703]`
- token-byte SHA-256: `89b0cae42bb0ca3f24f3715791b33ba058a10f3062f0c6c2a8d24b6fa3ec59c0`
- position: 0; DSA: `range_fill([0])`
- prompt/token package: `c05ba1cba69535cd17daf9f4326e5e1db25ffafe504c53712aa548f251741dff`

No best-of-N prompt search, route-margin inspection, hidden-state inspection, post-access
prompt replacement, or execution-time retokenization is permitted.

## Exact inventory and budgets

Independent catalog/map reconstruction yields 40 tensors, one shard open, and 40 logical
payload identities. It excludes expert, router, layer-3, shared-expert, output-head, and
position-0-unneeded indexer tensors.

| Family | Count | Packed bytes | Decoded f32 bytes | Status |
|---|---:|---:|---:|---|
| F32 | 12 | 178,176 | 178,176 | `REAL_BYTE_QUALIFIED_REUSABLE` |
| Q8_0 | 12 | 165,027,840 | 621,281,280 | `REAL_BYTE_QUALIFIED_REUSABLE` |
| Q5_K | 12 | 544,997,376 | 3,170,893,824 | `REAL_BYTE_QUALIFIED_REUSABLE` |
| Q6_K | 3 | 185,794,560 | 905,969,664 | `REQUIRES_REAL_BYTE_QUALIFICATION` |
| Q4_K | 1 | 535,265,280 | 3,806,330,880 | `REQUIRES_REAL_BYTE_QUALIFICATION` |
| **Total** | **40** | **1,431,263,232** | **8,504,653,824** | |

Inventory SHA-256:
`eaf54506f5bd45ef41f223224096a253f6fa6c5e2ad3bf94971c18eb09f6b21b`.

## Residency and admission

The aggregate decoded volume is not called peak residency. The pre-observation conservative
model separately bounds packed storage, a full CPU-decoded package, a full
decoded-equivalent MLX residency, activations/cache/native workspace, oracle phase, and
evidence retention. Its host floor is 27 GiB (28,991,029,248 bytes):

`ceil_GiB(1.25 × (packed + decoded_CPU + decoded_equivalent_MLX + 4 GiB reserve))`.

Runtime telemetry is still mandatory, must remain below the floor, and cannot be used to
lower it after observation. Contract SHA-256:
`56ab1eae69b45f9ae97f98e1d36dfa124e080a6dc82573013cc57782bce1ac76`.

## Oracle and numerical qualification

The future oracle is source-hashed independent Python/NumPy, consumes the frozen decoded
set, finishes before candidate creation, and forbids Rust, MLX, candidate output, and
candidate metrics. Oracle contract:
`0a54aa957e8b768108e4d8bc8c6e2a84cb48fbb3e0c93414c308112e88b3e816`.

The real Tier-B contract was frozen checkpoint-free from R9/R10 lineage, not future output:
per layer 0.0625 max absolute, 0.03125 RMSE, 0.999 cosine; three-layer final 0.1875,
0.09375, 0.997. Contract:
`9d1a6cc20ce8325fe8395334416f5ebcf980b72f02c6a0b44dc3240e0810024a`.

The real-shaped structured synthetic integration passes 10/10 with max absolute error
`4.7288928151090204e-7`, RMSE `8.430780681223996e-8`, and cosine
`0.9999999999999966`. It is scaffold evidence only, never a substitute for the real oracle.

## Decoder packages and sequence

Q4_K target: `token_embd.weight`, offset 535,316,320, packed length 535,265,280,
951,582,720 decoded elements.

Q6_K target: `blk.0.ffn_down.weight`, offset 1,203,482,464, packed length 61,931,520,
75,497,472 decoded elements. Equal-footprint candidates were resolved by the frozen
lexicographic tie-break.

Both packages require one exact real payload and exact A=B=C little-endian f32 bytes with
zero model compute. Each qualifies the format contract; every later tensor still requires
its own packed identity. Q4_K lineage can support M1-G format admission but cannot prove
the output-head tensor identity.

During preparation, a legacy Q6_K q2/q3 group-order defect was reproduced at 118/256
synthetic elements and minimally fixed. Its output now exactly matches the grouped spec,
independent indexed decoder, and Rust reference. Real-byte status remains unqualified.

Sequence: Q4_K, then Q6_K, then dense-prefix. No event auto-authorizes the next.

## Future ledger

- Current: 57.
- Q4_K qualification: 57→58.
- Q6_K qualification: 58→59.
- If both accepted qualification artifacts are separately approved as immutable dense-prefix
  components, the dense event reads the remaining 38: 59→97.
- Without cross-event reuse, the dense event reads all 40: 59→99.
- Failed reuse validation stops; it cannot silently fall back to rereading.

## Config, evidence, retention, attempt, and dispatch

The typed execution config requires immutable runtime/tooling/environment/authorization,
checkpoint/catalog/map, prompt, inventory, decoder, oracle, numerical, dispatch, hidden
retention, exact access, attempt, and evidence bindings. Authorized nulls and loose
overrides fail closed.

Attempt consumption is `EXECUTION_STARTED` immediately before the first authorized
checkpoint payload access. Preflight is non-consuming; there is no automatic retry.

The final layer-3 state is retained as immutable private canonical little-endian f32 bytes,
with public SHA, shape, count, provenance, candidate/oracle identities, numerical status,
read-only state, and creation ordinal.

Dispatch instrumentation records conceptual operations, imports, native/fused kernels,
normalizations, syncs, readbacks, fallback/reference/scaffold, and backend errors. The
synthetic observation of 28 per repeat is not frozen as the future native budget.

## Handoffs and downstream status

The representative M1-F0 handoff is `PREPARED_NOT_AUTHORIZED`. It consumes only the exact
accepted retained dense-prefix state, forbids prompt/state substitution, and requires v3
exact membership, H=2, ID-keyed weight qualification, full analytical retention, and rank
as diagnostic only. H=2 failure stops for review; there is no prompt search.

Route-independent M1-F schemas can consume the future route without redesign and retain
route-dependent fields explicitly unresolved. M1-G/P1 scaffolds advance final-hidden
provenance, output-head Q4_K lineage, memory admission, T017-141 dependencies, M1-H
authorization, and P1 ledger fields without publishing a command or authorizing execution.

## Review and CI

- Internal verdict: `GO FOR DENSE-PREFIX PACKAGE ADVERSARIAL REVIEW`.
- Adversarial packet:
  `docs/architecture/reviews/f017-dense-prefix-decoded-reuse-adversarial-packet.md`
- Packet SHA-256: `72ec4fc5b2477fb5928e4e7e25f5b22a39a76e37ccbba5b6fda9b5aa1ae3903b`
- Final-head Apple CI: exact run→SHA binding is recorded in the final operational handoff;
  no checkpoint access is performed in CI.

Real checkpoint access: 0. Ledger: 57. Q4_K/Q6_K real qualification: not executed.
Dense-prefix, M1-F0, M1-F, M1-G, P1, and Feature 018: not executed.

Exact next action: independent adversarial review of this package. The reviewer should
recommend the next single separately authorized real event; this report authorizes none.
