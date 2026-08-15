# PulsarMLX F017 M1-F(-1) 40-Read Dense-Prefix Authorization Preparation Report

## Disposition

`READY FOR 40-READ DENSE-PREFIX EXECUTION REVIEW`

The obsolete 38-read reuse design is retired. `DPREFIX-REAL-1` is now born
machine-authorized, unconsumed, unexecuted, and pending independent review for
exactly 40 fresh reads. This preparation performed zero checkpoint reads and
left the cumulative real-payload ledger at 59.

## Lineage and preserved blocker

- Authoritative starting head: `cefb7302bc6a7982cfa7ae670669a02cd6652304`.
- The historical `NOT_READY — QUALIFIED_PAYLOAD_REUSE_INVALID` result remains
  immutable at SHA-256
  `63b9fa5c8d6960c787f9bebeb0c88db2e8796c944b3482cd588d2743da57137f`.
- Preparation-contract v2 is an append-only successor to v1
  (`64fee7f240aac25fded225c81a9c7696d74ec47df67d86d48e3912ebc2e6ae11`).
- Its only execution-strategy delta is removal of cross-event decoded reuse and
  promotion of the accepted Q4_K/Q6_K observations to hard identity gates.

## Frozen execution surface

- Boundary: `F017 M1-F(-1) REAL DENSE-PREFIX LAYER-3 ENTRY-STATE BOUNDARY`.
- Input: prompt `Hello`, prompt SHA
  `185f8db32271fe25f561a6fc938b2e264306ec304eda518007d1764826381969`,
  token `9703`, position `0`, DSA `range_fill([0])`, prompt-package SHA
  `c05ba1cba69535cd17daf9f4326e5e1db25ffafe504c53712aa548f251741dff`.
- Tokenizer: `glm52-gguf-tokenizer-v1:149e907384517d91d236a819835aa0dc97e6d4a3c512e6d5806d6b162ced1c6d`.
- Inventory: 40 tensors: F32 12, Q8_0 12, Q5_K 12, Q6_K 3,
  Q4_K 1.
- Packed bytes: `1,431,263,232`; aggregate decoded-f32 volume:
  `8,504,653,824`.
- Allowlist SHA: `c9c1540ea1cc9e69344ed9f3dcc4eb8ba1e5c15e3d55c1bccdec00eeb1db36aa`.

Every entry has one allowed read, exact catalog/map metadata, role, layer,
shard, offset, packed length and row width, quantization, shapes, catalog-entry
identity, and decoder lineage. Layer 3, router, expert, output-head, adjacent
layer, duplicate, and wildcard access are excluded.

## Hard identity confirmation

- Q4_K `token_embd.weight`: evidence
  `035ad4351406c24c65667a5322f1ffae71589f046a5ba3f591b8a4e3f6140994`,
  expected packed SHA
  `3e4c34141f918333883442b8ff44c78c9927295ae16378047a8a36edeb7ed5ef`,
  expected decoded SHA
  `e2cff562131674156704ca21b2b6e850337c2e5d8948b4dcc9f14676ecf8f2c1`.
- Q6_K `blk.0.ffn_down.weight`: evidence
  `375e6b852733e8ac885d53c3814a03deb3a80e639bf61d427f1e49f1aae57086`,
  expected packed SHA
  `845b4fd6b5d290506e576ca5099336bae7d28f3ebfcec964ed2136c3ea4a8ede`,
  expected decoded SHA
  `ff26151a7997379c1713b90852fdbfd8301b36d5d89a1c3bb623b9b8f273483a`.

A mismatch is terminal (`Q4_IDENTITY_CONFIRMATION` or
`Q6_IDENTITY_CONFIRMATION`) after the read, with no retry or alternate tensor.
The other 38 tensors bank first-observation packed and decoded identities.

## Oracle, numerical, repeat, dispatch, and lifecycle contracts

- Independent Python/NumPy oracle:
  `0a54aa957e8b768108e4d8bc8c6e2a84cb48fbb3e0c93414c308112e88b3e816`.
  It is finalized before candidate creation and rehashed afterward; Rust FFI,
  MLX, candidate output, and candidate hidden state are forbidden inputs.
- Real Tier-B:
  `9d1a6cc20ce8325fe8395334416f5ebcf980b72f02c6a0b44dc3240e0810024a`.
- Numerical/repeat contract:
  `4a9f2f29689b8c20259ebadd46a0038008895ea173bf024b2ab805d35b7aa488`;
  exactly ten complete candidate repeats are required.
- Dispatch contract:
  `d430b7dcc23d98d1b339315443f7868d6f8dd7e3e7c389ebae7d24ecae45e267`.
  The synthetic count 28 is not a real expectation; measured native dispatches
  require complete stage attribution and fallback/backend-error reconciliation.
- Lifecycle contract:
  `2b6fd4ac70ea83fb80bcfba98d36dd5685ebf324839cdabbb0c782edd6197771`.

No numerical threshold changed because of Q4/Q6 observation or reuse-plan
retirement. Post-observation retuning remains forbidden.

## Retention and downstream isolation

The retention-at-creation contract is
`89dd470bda3c9c312ca59d3d9b798016f83f1a810339840b427e7e6a16c679c1`.
Any reusable cross-event output must be created with immutable canonical bytes,
a manifest, a private package identity, repository-relative symbolic naming,
content/provenance identities, and read-only enforcement. Its two-phase
finalization binds the immutable bytes first, then adds the committed evidence
SHA and execution commit to the descriptor without mutating those bytes.
Hash-only evidence is
`CROSS_EVENT_REUSE_INELIGIBLE`.

The successful dense-prefix event must create and retain the canonical LE-f32
layer-3 entry state, not merely its hash. The representative M1-F0 handoff is
prepared but remains `PREPARED_NOT_AUTHORIZED_NOT_EXECUTED`; recomputation,
approximation, alternate prompt/token, state substitution, and automatic
continuation are forbidden.

## Residency and admission

The predecessor liveness model remains
`56ab1eae69b45f9ae97f98e1d36dfa124e080a6dc82573013cc57782bce1ac76`.
For the 40-read event, the conservative bound explicitly includes the complete
packed inventory, one oracle decoded upper bound, one separately identifiable
candidate decoded-equivalent upper bound, 4 GiB reserve, and a 1.25 engineering
multiplier. Rounding upward gives an unchanged 27 GiB free-memory floor.

Host admission binds the reviewed arm64/macOS/SDK and exact native MLX source
and loaded-library identities. It is non-consuming and also requires clean
local/remote state, ledger 59, acceptable pressure/thermal state, no competing
inference process, and clean context/stream/singleton state.

## Attempt and ledger semantics

`DPREFIX-REAL-1` is authorized, unconsumed, unexecuted, and has not accessed the
checkpoint. Preflight and host admission do not consume it. Consumption occurs
immediately before the first positional read, after a crash-safe execution-start
record. Automatic retry and automatic M1-F0 continuation are false.

The access ledger advances by actual reads: after `N` reads it must be `59+N`.
Only all 40 reads yield `59→99`; a partial terminal event may not be reported as
the full transition.

Canonical checkpoint-free preflight:

`READY_TO_EXECUTE_DENSE_PREFIX_REAL_CAPTURE`

## Validation and internal review

The package includes direct regressions for all 20 required negative mutations,
exact 40-entry regeneration, packed-byte arithmetic, identity gates,
retention-at-creation, partial-read accounting, born-authorized attempt state,
and generated-artifact equality. Broad workspace, research/evidence, Spec Kit,
privacy/path, duplicate-key, historical-immutability, and generated-artifact
validation are recorded in the final handoff after the preparation commit.

Internal verdict:

`GO FOR DENSE-PREFIX 40-READ AUTHORIZATION ADVERSARIAL REVIEW`

Final preparation and CI bindings: `PENDING_FINAL_HEAD_CI`.

## Exact next action

Independent adversarial review. A verdict of
`GO FOR ONE DENSE-PREFIX M1-F(-1) REAL CAPTURE` permits a fresh explicit
execution instruction for `DPREFIX-REAL-1`; that future event reads exactly 40
payloads once, creates the retained layer-3 state at execution time, banks and
pushes terminal evidence, and stops before representative M1-F0.
