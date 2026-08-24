# F017 Lifecycle V8 Causal Design — Opus Design Review, Cycle 02

Reviewed exact committed bytes at `c6563e809910ec1af4fc6e0937b18e26ab46a6d0` in the detached read-only
worktree `/tmp/f017-v8-opus-c2.RAt4Oi`. `git status` empty and HEAD unmoved before and after. No reviewed
file modified. No original checkpoint shard opened, hashed, mmapped, or pread. No Event-04 authority minted.
No real oracle executed. No P1 attempt 2 executed. `qualify_f017_lifecycle_v8_design.py` was deliberately
**not** run — it rewrites banked qualification evidence. All attacks were executed against throwaway
`tempfile` copies of the tree, which were removed.

## Verdict

`REJECT`

Two `BLOCKING`, seven `NON_BLOCKING_REQUIRED`, eight `DEFENSE_IN_DEPTH`.

---

## Context reconstructed

- **Opus cycle 01** (`f017-lifecycle-v8-opus-design-cycle-01-response.md`, reviewed head `dcf032a5`):
  `REJECT` with 2 `BLOCKING` (B1 `EVIDENCE_BANKING_FAILURE` double release chain; B2 identity failure over
  shards 2–6 unrepresentable), 5 `NON_BLOCKING_REQUIRED` (N1 ungated `processing` + mirror-only safety
  projection; N2 shard digests/filenames unbound to `checkpoint_metadata`; N3 ungated, incomplete lifecycle
  state machine; N4 failure release reports cannot record duplicate/unknown closures; N5 closure validator
  enforces no authority conformance), and 11 `DEFENSE_IN_DEPTH`.
- **Gemini cycle 03** (reviewed head `82dcc4cf`): `ACCEPT`, zero findings, `material_disagreement: none`.
  Its stated basis — "the DAG fundamentally permits at most 1 predecessor edge per artifact" — is false on
  the committed bytes (322 nodes, 321 edges, but `primary_durable_start`, `secondary_durable_start`, and
  `secondary_descriptor_continuity_report` each carry two dependencies). The claim is harmless to its
  conclusion but shows the acceptance did not rest on an independent traversal.

## Mechanical reproduction (all green on committed bytes)

| component | result |
| --- | --- |
| `validate_f017_lifecycle_causal_design_v8.py` | `PASS` — 322 artifacts, 321 edges, 48 outcomes, 25 invariants |
| `construct_f017_lifecycle_v8_symbolically.py` | `PASS` — 48/48 outcomes, 1450 real artifacts, max closure depth 51 |
| `test_f017_lifecycle_causal_design_v8.py` | 5/5 OK (171 static + 6 runtime mutations, census matches the banked qualification exactly) |
| generator determinism | re-running `generate_f017_lifecycle_v8_design.py` into a copy reproduces all 12 committed contracts **byte-identically** |

## Cycle-01 findings: independently re-attacked

| # | status on `c6563e80` | evidence |
| --- | --- | --- |
| B1 double release chain | **closed** | cut 43 gets report+terminal only (no duplicate start); cuts 44–47 get no release chain; validator `DUPLICATE_RELEASE_CHAIN` fires for cut ≥ 45; suppressing the chain raises `MISSING_RELEASE_CHAIN` |
| B2 identity failure 2–6 | **closed as scoped, relocated** — see BLOCKING #2 | 47 variants now cover every success-prefix rank 1–47; identity cuts 15/17/19/21/23 retain 1/2/3/4/5 leases and each gets exactly one release chain |
| N1 ungated `processing` | **closed** | `processing` compared exactly (line 216); `safety_projection` mirror removed; `PREFIX_ONLY` and dropped `durable_shard_receipt_before_next` both rejected |
| N2 shard binding | **closed at contract level, open at artifact level** — see NON_BLOCKING #6 | `glm52-checkpoint.json` re-read and shard records compared exactly; forged digest/filename rejected |
| N3 lifecycle model | **closed** | `transitions`/`states`/`unconditional_invariants` compared to values derived from all 322 nodes |
| N4 duplicate/unknown closures | **nominally closed only** — see NON_BLOCKING #3 | keys restored, but pinned to `0` by `payload_constants`; the validator checks key presence only |
| N5 closure validator | **structurally closed, semantically open** — see BLOCKING #1 | forged schema/outcome/extra payload key/dropped root/forged root sha/forged rank/forged artifact id/forbidden artifact present/missing required all rejected on a **failure** package after consistent descendant rehashing |
| DiD 1 (vacuous forbidden assert) | closed — the check now also lives in the verifier and fires |
| DiD 4 (actor ungated) | **not closed** — see DEFENSE_IN_DEPTH 1 |
| DiD 9 (dead cycle detector) | **not closed** — see DEFENSE_IN_DEPTH 2 |

---

# BLOCKING

## B1. `payload_constants` are validated against nothing, and every other payload field carries no obligation at all — a conforming `COMPLETE_SUCCESS` package can contradict six declared unconditional invariants

`payload_constants` is the design's only mechanism for pinning artifact payload semantics, and
`check_f017_transitive_artifact_closure_v8.validate_package` faithfully enforces it
(`payload constant mismatch` fires correctly). But `validate_documents` never checks the constants' *values*:
`generate_f017_lifecycle_v8_design.py:161` only asserts
`set(payload_constants) - set(payload_keys)` is empty. Reproduced against committed bytes, regenerating with

```
final_declaration constants -> {"active_generation": "V8_LIVE",
                                "event_04_executed": True,
                                "original_checkpoint_access": 42}
```

on **all 48 outcomes** yields validator `PASS`, symbolic constructor `PASS` (48/48), and 5-test suite `PASS`.
`event_04_executed` and `original_checkpoint_access` are the two most safety-critical declarations in the
feature and they are enforced against no authority. `package_receipt` deltas forged to `9`, and failure-path
deltas inverted to `1` on `PRE_MINT_FAILURE`, are likewise uncaught by all three components — while the
*obligation*-level `package_delta`/`primary_delta`/`secondary_delta` are correctly gated against node ranks.
Two parallel accounting statements exist; one is gated, one is not.

Below the constants, only 3 of the 48 success artifacts carry any payload constraint at all
(`package_receipt`, `package_terminal`, `final_declaration`). Every other payload field is free. Reproduced on
a constructed `COMPLETE_SUCCESS` package with all descendants consistently rehashed — `validate_package`
accepts all of the following:

| forged success package | verifier result |
| --- | --- |
| `descriptor_release_report.live_leases_after_release = 5`, `successful_closures = 0`, `duplicate_closures = 9`, `unknown_leases = 7` | UNCAUGHT |
| `descriptor_release_terminal.live_leases_after_release = 5`, `result = "FAIL"` | UNCAUGHT |
| `checkpoint_identity_manifest.observed_total_bytes = 1` (against `expected_total_bytes = 238458632928`) | UNCAUGHT |
| `checkpoint_shard_receipt_4.observed_checkpoint_digest = "0"*64` (≠ its own `expected_checkpoint_digest`) | UNCAUGHT |
| `checkpoint_shard_receipt_4.expected_checkpoint_digest = "f"*64` (unbound to `glm52-checkpoint.json`) | UNCAUGHT |
| `checkpoint_identity_receipt.retained_lease_count = 0`, `identity_only_retained_count = 9` | UNCAUGHT |
| `descriptor_lease_manifest.lease_count = 99` | UNCAUGHT |
| `primary_descriptor_continuity_report.path_reopen_count = 7` | UNCAUGHT |
| `primary_execution_evidence.synthetic_only = False`, `layers_completed = 92` | UNCAUGHT |
| `coordinator_handshake.checkpoint_opens = 3`, `checkpoint_reads = 9` | UNCAUGHT |

`NO_LIVE_LEASES_AT_TERMINAL`, `PATH_REOPEN_COUNT`, `GRAPH_LEASE_COUNT`, `PRIMARY_DESCRIPTOR_COUNT`,
`SECONDARY_DESCRIPTOR_COUNT`, and `NO_ORIGINAL_CHECKPOINT_ACCESS` are therefore statements inside contract
JSON only — no package obligation makes any of them checkable on evidence. There is no artifact anywhere in
the design requiring `observed_* == expected_*`, which is the entire purpose of the checkpoint-identity
lifecycle. "Conforming" and "safe" are disjoint.

The corresponding semantic checks *do* exist — in `construct_f017_lifecycle_v8_symbolically.py:103-120`
(continuity census, lease-manifest correspondence, release closure census). They live in the **producer**,
never in the verifier. This is the exact shape cycle 01 named in N5: "the wrong side of the trust boundary
for a design whose purpose is detecting forged evidence." The N5 repair moved structural conformance across
the boundary and left semantic conformance behind.

This falsifies the review request's own criterion that recursive validation "independently enforces full
schema, **payload**, outcome, root-authority, dependency, causal-rank, and package-identity conformance."

**Repair:** give every payload field a declared obligation (constant, cross-field equality such as
`observed_* == expected_*`, or root-authority derivation); gate `payload_constants` values in
`validate_documents` against the authority each restates; move the constructor's semantic cross-checks into
`validate_package`.

## B2. The 47 failure tails create 227 durable prefixes that match no outcome; 57 of them terminate holding live graph-payload leases with no release evidence

V8 closes cycle-01 B2 exactly as scoped — every durable **success** prefix (ranks 1–47) maps to one of 47
terminal variants. But each variant appends a 4-, 6-, or 7-artifact failure tail, and the same treatment was
not extended to it. Enumerated from the committed obligations:

- **227** strictly-intermediate failure-tail durable prefixes match no outcome in the 48-outcome census.
- **29** of the 47 failure outcomes are lease-bearing (cuts 15–43).
- **57** of those intermediate prefixes sit between the tail's `failure_evidence__*` and its
  `descriptor_release_report__*` — i.e. 1–5 graph-payload leases live, no release evidence, no matching
  outcome, and no obligation to satisfy.

Cycle-01 B2 verbatim: "That prefix matches no outcome … any such termination violates the design's own
`NO_LIVE_LEASES_AT_TERMINAL` invariant and `live_leases_at_terminal: 0`, with no release obligation to
satisfy." Every word applies unchanged to
`{success prefix ≤ 43} + failure_evidence__checkpoint_identity_failure__after_rank_019`.

Nothing in the frozen design bounds this. `interface` declares `attempts: 1, retries: 0, resume: false`, so
there is no re-entry; no authority declares the failure tail atomic, idempotent, or out of scope; and
`outcome_obligations` asserts `live_leases_at_terminal: 0` for all 48 outcomes while the model admits 57
durable states that contradict it. An implementation has undefined behaviour on tail failure and the
resulting package is unclassifiable.

**Repair:** either declare the failure tail atomic with a stated recursion terminator (and gate that
declaration), or classify tail prefixes the same way success prefixes are now classified, deriving the
release obligation from live-lease count at the tail cut.

---

# NON_BLOCKING_REQUIRED

## N1. The retained-lease derivation — the load-bearing B2 repair — is a bare rank literal duplicated in generator and validator, not derived from the DAG

`generate_f017_lifecycle_v8_design.py:189` and `validate_f017_lifecycle_causal_design_v8.py:273` both
hardcode `(15, 17, 19, 21, 23)`. Neither resolves `checkpoint_shard_receipt_2..6` to its actual
`creation_rank`. The two literals agree with each other, so the "independent" validator confirms nothing.

Reproduced: swapping the emission order of `checkpoint_access_event_k` and `checkpoint_shard_receipt_k` moves
graph-payload receipts to ranks 14/16/18/20/22 and passes the validator, the 48-outcome symbolic
constructor, and the 5-test suite — while `CHECKPOINT_IDENTITY_FAILURE__AFTER_RANK_014` now terminates with
lease 2 live, zero release artifacts, and `live_leases_at_terminal: 0`. This is V7
`BYTE_CENSUS_BARE_VALIDATOR_LITERAL` recurring on the leases. Note the contrast: the same validator derives
`package_delta`/`primary_delta`/`secondary_delta` thresholds from `node_map[...]["creation_rank"]` (line 259)
and correctly rejects forged start ranks — the correct pattern already exists two lines away.

## N2. Failure-tail release *chain shape* and closure counts are ungated

`validate_documents` requires only `len(release_reports) == 1`. Reproduced, all uncaught by validator +
constructor + 5-test suite:

- dropping `descriptor_release_start__*` **and** `descriptor_release_terminal__*` from every failure tail
  design-wide (322 → 265 artifacts) — leases close with a bare report, no start, no terminal;
- `descriptor_release_start__*.expected_leases = 99` on every lease-bearing failure;
- `attempted_closures`/`successful_closures` inflated to `42` on all non-identity lease-bearing failures
  (the 5-test suite probes only `CHECKPOINT_IDENTITY_FAILURE` ranks, so ranks 24–43 are unprobed).

## N3. `duplicate_closures` / `unknown_leases` are still unrecordable — cycle-01 N4 is closed in name only

The repair restored the two keys but pinned both to `0` via `payload_constants`, which `validate_package`
enforces exactly. The validator's `RELEASE_OBSERVABILITY` check (line 279-282) tests key *presence* only.
Net observability on the 29 lease-bearing failure paths is unchanged from cycle 01: an implementation that
observes a duplicate or unknown close cannot bank a conforming report, so the incident becomes
unclassifiable (feeding B2). Reproduced: declaring `duplicate_closures: 3, unknown_leases: 2,
live_leases_after_release: 4` design-wide passes the validator; it is caught only by a hardcoded literal in
the 5th unit test, and only inside the identity window.

## N4. Lease-manifest correspondence is absent on the 10 pre-manifest outcomes, and lease IDs are pinned to synthetic literals

`descriptor_lease_manifest` has rank 25, but leases are retained from rank 15. On cuts 15–24 the manifest is
**forbidden** while a release report closing 1–5 leases is **required**. The constructor's correspondence
check is guarded by `if "descriptor_lease_manifest" in created`, so it never runs there. Reproduced:
replacing those reports' `lease_ids` with `["ATTACKER-LEASE", ...]` passes the validator, the constructor,
and the 5-test suite. `continuity.exact_comparison_to_lease_manifest: true` is unsatisfiable on these ten
outcomes — there is nothing to compare against.

Separately, `generate_f017_lifecycle_v8_design.py:209` pins `lease_ids` to the literal strings
`["LEASE-2" … "LEASE-6"]` as a **payload constant** on all 29 lease-bearing failure outcomes, and
`validate_package` enforces it. Constructor placeholders have been promoted into a normative design
authority: a conforming implementation must name its leases `LEASE-<ordinal>` on failure paths while the
success-path report's `lease_ids` are entirely free.

## N5. Lease inception is undeclared, so "exactly the retained leases" is not well defined for five cuts

`graph_payload_disposition: RETAIN_AS_PACKAGE_OWNED_DESCRIPTOR_LEASE` never says whether a lease begins at
`checkpoint_access_event_k` (the open) or at `checkpoint_shard_receipt_k` (the durable receipt). The
derivation silently chooses the receipt. On cuts 14, 16, 18, 20, 22 the durable prefix contains
`checkpoint_access_event_k` without its receipt: an open graph-payload descriptor exists, `retained` computes
to one less than the descriptors actually open, and the outcome carries no release obligation for it.
`CHECKPOINT_IDENTITY_FAILURE__AFTER_RANK_014` has a tail of `[failure_evidence, package_receipt,
package_terminal, final_declaration]` — no release chain at all.

## N6. Shard-receipt payload semantics are unbound to the checkpoint metadata authority

The N2 repair binds the *contract*'s six shard records to `docs/validation/glm52-checkpoint.json` (forged
digest and forged filename are both rejected, verified). It does not bind the *artifacts*: nothing requires
`checkpoint_shard_receipt_k.expected_size` to equal `shards[k].size_bytes` or `expected_checkpoint_digest`
to equal `shards[k].sha256`. Combined with B1's missing `observed == expected` obligation, the six receipts
that constitute the identity proof prove nothing. See the B1 table rows `SHARD_DIGEST_MISMATCH` and
`SHARD_EXPECTED_DIGEST_UNBOUND`.

## N7. Artifact payload key census and DAG root-authority census are ungated

`validate_documents` compares `schemas.artifacts[*].payload_keys` to `dag.nodes[*].payload_keys` — one
generated mirror against another — and pins no artifact's key set to an independent expectation. Reproduced:
dropping `observed_checkpoint_digest` and `retain_disposition` from all six shard receipts passes validator,
constructor, and 5-test suite. Likewise, deleting `v7_budget_closeout` from `dag.root_authorities` (and thus
from every artifact's `root_authorities` census and the manifest) passes everything; only `checkpoint_metadata`
and `numerical_contract` have any presence gate.

---

# DEFENSE_IN_DEPTH

1. **Actor assignment is still ungated** (cycle-01 DiD 4, explicitly listed for repair). `model.transitions`
   mirrors `dag.nodes`, so a change to both passes. Reproduced: forcing `actor = "OPERATOR"` on all 322
   nodes passes validator, constructor, and 5-test suite. Producer separation (identity producer vs.
   consumers vs. coordinator) is declared but unenforced. The `DAG_NODE_ACTOR` mutation in the suite only
   probes one-sided drift.
2. **Both cycle detectors are unreachable** (cycle-01 DiD 9, listed for repair). In `validate_documents` the
   `FUTURE_REFERENCE` rank check precedes the DFS; in `validate_package` the `noncausal dependency rank`
   check precedes `walk`. Strict rank monotonicity makes a cycle impossible, so `ARTIFACT_CYCLE` /
   `artifact cycle` and the banked `artifact_cycles: 0` rest on the rank check alone. The
   `TWO_NODE_CYCLE` / `THREE_NODE_CYCLE` mutations are rejected as future references.
3. `construct_outcome`'s `actual != required` assertion remains vacuous in the producer (the loop creates
   only `required`). It is now meaningful in `validate_package`, where a planted forbidden artifact and a
   deleted required artifact are both correctly rejected.
4. The envelope `result` field is never validated. Forging a failure package's `final_declaration__*.result`
   from `FAILURE_EVIDENCE` to `PASS` is uncaught (`outcome` is gated, limiting impact).
5. `static_design_mutations_rejected: 171` is a hardcoded literal in `qualify_f017_lifecycle_v8_design.py`
   while the suite asserts only `assertGreaterEqual(len(mutations), 170)`. Dropping a mutation silently
   staleness the banked census. (The census is currently accurate: 30+25+20+48+10+15+10+13 = 171, plus 6
   runtime.)
6. `UNSTARTED_PRIMARY_DELTA_ZERO` and `UNSTARTED_SECONDARY_DELTA_ZERO` resolve to the identical pointer
   `accounting:/unstarted_consumer_delta`. 25 invariants, 24 distinct sources; the secondary consumer has no
   separate accounting surface.
7. `model.success_artifact_order`, `model.states`, and `model.transitions` are generated mirrors of
   `dag.nodes`. They catch one-sided drift only and add no independent constraint (cycle-01 N3's structural
   point is closed; its duplication point is not).
8. `outcome_obligations[*].live_leases_at_terminal` is a generator literal `0` that the validator re-checks
   against the literal `0`. It is bound to no release artifact — which is why the `live_leases_after_release:
   4` forgery in N3 passes.

---

## Required work before a V9 review cycle

1. Give every payload field a declared obligation; add `observed_* == expected_*` equalities; derive shard
   receipt `expected_*` from `glm52-checkpoint.json`; gate `payload_constants` values against the authority
   each restates; move the constructor's semantic cross-checks into `validate_package`. *(B1, N6)*
2. Bound the failure tail — declare it atomic with a stated recursion terminator, or classify its 227 durable
   prefixes and derive the release obligation from live-lease count at the tail cut. *(B2)*
3. Derive retained leases from `checkpoint_shard_receipt_*` node ranks, not from `(15, 17, 19, 21, 23)`.
   *(N1)*
4. Gate the failure release chain shape (start, report, terminal) and its closure counts against the
   derived retained-lease count, over all lease-bearing cuts, not just the identity window. *(N2)*
5. Make `duplicate_closures` and `unknown_leases` genuinely recordable, with a declared outcome for a
   nonzero observation. *(N3)*
6. Give the pre-manifest window (cuts 15–24) a lease authority to compare against, or move
   `descriptor_lease_manifest` to first-lease rank; remove the `LEASE-<ordinal>` literals from
   `payload_constants`. *(N4)*
7. Declare lease inception (open vs. durable receipt) and re-derive the five affected cuts. *(N5)*
8. Gate artifact payload key censuses and the DAG root-authority census against independent expectations.
   *(N7)*
9. Close DEFENSE_IN_DEPTH 1 and 2, both carried unrepaired from cycle 01's explicit repair list.

## Verification for a V9 design

From a clean detached worktree run `validate_f017_lifecycle_causal_design_v8.py` (expect `PASS` with the new
census), `construct_f017_lifecycle_v8_symbolically.py`, and the enlarged mutation suite. Then confirm each
repair with a targeted negative probe that must fail closed:

- `final_declaration` constants flipped to `event_04_executed: true` / `original_checkpoint_access: 42`;
- a `COMPLETE_SUCCESS` package declaring `live_leases_after_release: 5`, `path_reopen_count: 7`,
  `synthetic_only: false`, `observed_total_bytes: 1`, and a shard `observed_checkpoint_digest` that differs
  from its `expected_checkpoint_digest`;
- a shard-receipt `expected_checkpoint_digest` that differs from `glm52-checkpoint.json`;
- the access-event / shard-receipt rank swap;
- failure tails with `descriptor_release_start` and `descriptor_release_terminal` removed;
- `expected_leases: 99` and inflated closure counts on a non-identity lease-bearing failure;
- forged `lease_ids` on a cut-19 identity failure;
- all actors reassigned to `OPERATOR`;
- `v7_budget_closeout` removed from `dag.root_authorities`;
- a durable prefix ending at `failure_evidence__*` with live leases, which must resolve to a declared
  outcome or a declared terminator.

Re-bank the mechanical qualification only after every probe fails closed.
