# F017 Lifecycle V8 Causal Design — Opus Design Review, Cycle 03

Reviewed exact committed bytes at `559fec05e92749707780fad71df9d943eae6ffe9` in the detached read-only
worktree `/tmp/f017-v8-opus-c3.zhkxK6`. `git status --porcelain` empty before and after; HEAD unmoved. No
reviewed file modified (the `__pycache__` created by running the committed scripts in place was removed; it is
git-ignored either way). No original checkpoint shard opened, hashed, mmapped, or pread. No Event-04 authority
minted. No real oracle executed. No P1 attempt 2 executed. `qualify_f017_lifecycle_v8_design.py` was
deliberately **not** run — it rewrites banked qualification evidence. All attacks ran against throwaway
`git archive` extractions (`/tmp/f017c3exec`, `/tmp/f017c3g`, `/tmp/f017c3h`), proven byte-identical to the
worktree before use.

## Verdict

`REJECT`

Two `BLOCKING`, five `NON_BLOCKING_REQUIRED`, nine `DEFENSE_IN_DEPTH`.

---

## Context reconstructed

- **Opus cycle 01** (head `dcf032a5`): `REJECT` — B1 `EVIDENCE_BANKING_FAILURE` double release chain, B2
  identity failure over shards 2–6 unrepresentable; 5 `NON_BLOCKING_REQUIRED`; 11 `DEFENSE_IN_DEPTH`.
- **Opus cycle 02** (head `c6563e80`): `REJECT` — B1 `PAYLOAD_SEMANTICS_NOT_INDEPENDENTLY_OBLIGATED`,
  B2 `FAILURE_TAIL_DURABLE_PREFIX_RECURSION_UNBOUNDED` (227 unmatched intermediate prefixes, 57 lease-bearing);
  7 `NON_BLOCKING_REQUIRED`; 8 `DEFENSE_IN_DEPTH`.
- **Gemini cycle 04** (head `af782a4d`): `ACCEPT`, zero findings. Its counts are all correct on the committed
  bytes (95 artifacts / 94 edges / 48 outcomes / 1,223 constructed artifacts / 238,458,632,928 bytes /
  176 static + 11 runtime attacks). It cites an implementation-plan artifact `f017_lifecycle_v8_review.md`
  that exists nowhere in the tree or in any reachable commit — see DEFENSE_IN_DEPTH 9.
- Banked review-evidence integrity is intact: every `request_sha256` / `response_sha256` in the four
  normalized results matches the banked markdown byte-for-byte.

## Mechanical reproduction (all green on committed bytes)

| component | result |
| --- | --- |
| `validate_f017_lifecycle_causal_design_v8.py` | `PASS` — 95 artifacts, 94 edges, 48 outcomes, 25 invariants |
| `construct_f017_lifecycle_v8_symbolically.py` | `PASS` — 48/48 outcomes, 1223 real artifacts, max closure depth 48 |
| `test_f017_lifecycle_causal_design_v8.py` | 6/6 OK (176 static + 11 runtime; census matches the banked qualification exactly) |
| generator determinism | re-running `generate_f017_lifecycle_v8_design.py` into a fresh extraction reproduces all committed contracts **byte-identically** |

## Cycle-02 findings: independently re-attacked

| # | status on `559fec05` | evidence |
| --- | --- | --- |
| B1 payload semantics | **largely closed, residue in B2/N1/N3/N4/N5** | 888 `EXACT_CONSTANT`, 188 `NONNEGATIVE_INTEGER`, 12 `EQUAL_PAYLOAD_FIELD`, 5 `EQUAL_ARTIFACT_PAYLOAD_FIELD` rules, all enforced in `validate_package`; `critical_constants` pins `final_declaration`, shard receipts, handshake, release, terminal. 37 `TYPE`-only fields remain |
| B2 unbounded failure tail | **closed as scoped, relocated — see BLOCKING 1** | one capsule per outcome; 47 capsules, each 1 dependency; capsule deletion, second-capsule insertion, stray-file insertion, and cross-cut capsule splice all rejected |
| N1 retained-lease literals | **relocated, not closed — see NON_BLOCKING 2** | derivation is now from `checkpoint_access_event_k["creation_rank"]` on both sides, but the ordering premise it rests on is ungated |
| N2 release chain shape/counts | **partially closed — see NON_BLOCKING 1** | `attempted == successful + duplicate + unknown` and `expected_leases == len(lease_ordinals)` now enforced; nothing anchors the counts to `expected_leases` |
| N3 cleanup anomalies | **closed** | `duplicate_closures: 1, successful_closures: 0` accepted in a conforming capsule; negative values and `bool`-as-int both rejected |
| N4 pre-manifest correspondence / lease literals | **closed** | `LEASE-<ordinal>` literals gone; lease identity on cuts 14–24 derives from `checkpoint_access_event_*`, which are in the prefix |
| N5 lease inception | **closed** | `interface.lease_inception = SUCCESSFUL_GRAPH_PAYLOAD_CHECKPOINT_ACCESS_EVENT_OPEN`, gated exactly; flipping it is rejected |
| N6 shard receipt binding | **closed** | `expected_size`/`expected_checkpoint_digest` pinned from `glm52-checkpoint.json`; `observed_* == expected_*` enforced |
| N7 payload-key / root-authority censuses | **closed** | `expected_payload_keys` is independent; `ROOT_AUTHORITY_PATHS` is an exact census; removal and repointing both rejected |
| DiD 1 actor drift | **closed** | `expected_actor` is independently derived; `ALL_ACTORS_OPERATOR` and capsule-only actor drift both rejected |
| DiD 4 envelope `result` | **closed at envelope level, open at payload level — see NON_BLOCKING 4** | |
| DiD 5 mutation census | **closed** | suite asserts `assertEqual(len(mutations), 176)` |
| DiD 6 shared consumer pointer | **closed** | `/unstarted_primary_delta` and `/unstarted_secondary_delta` are now distinct |
| DiD 2 dead cycle detectors | **not closed** (third cycle) — see DEFENSE_IN_DEPTH 1 | |
| DiD 3 vacuous producer assertion | **not closed** — see DEFENSE_IN_DEPTH 6 | |

---

# BLOCKING

## B1. Every failure outcome retroactively rewrites and re-hashes its entire durable prefix — up to 47 immutable artifacts — so the "exactly one durable artifact" claim is false and the eliminated recursive multi-file tail reappears as a recursive multi-file head

`check_f017_transitive_artifact_closure_v8.validate_package` requires, for **every** artifact in a package:

```
if value["outcome"] != outcome:                       # line 56  (pre-existing)
if value["result"] != expected_result:                # line 87  (added by af782a4d)
```

where `expected_result` is `"PASS"` for `COMPLETE_SUCCESS` and `"FAILURE_EVIDENCE"` otherwise. Both fields are
part of the strict envelope census (`schemas.strict_key_census: true`, `unknown_fields: REJECT`), and every
artifact's bytes are bound into its successors through `dependencies` SHA-256.

The rank-1 artifact `operator_approval` is produced by `OPERATOR` at transition `T001`, before any of the 47
later transitions that determine the outcome. Reproduced on committed bytes — the same logical artifact across
three constructed packages:

| artifact | `COMPLETE_SUCCESS` | `…AFTER_RANK_022` | `…AFTER_RANK_047` |
| --- | --- | --- | --- |
| `operator_approval` | `b86a1fa0890f` / `PASS` | `1a8966f818c7` / `FAILURE_EVIDENCE` | `b05caf9a4a91` / `FAILURE_EVIDENCE` |
| `package_durable_start` | `45e170512fc2` / `PASS` | `92395d159b8c` / `FAILURE_EVIDENCE` | `afb181b82cd6` / `FAILURE_EVIDENCE` |
| `checkpoint_shard_receipt_2` | `547293c6067e` / `PASS` | `46c381ec422d` / `FAILURE_EVIDENCE` | `3489aa923974` / `FAILURE_EVIDENCE` |

Byte-differing prefix artifacts, measured against the `COMPLETE_SUCCESS` package:

- `CHECKPOINT_IDENTITY_FAILURE__AFTER_RANK_022`: **22 of 22** prefix artifacts differ, plus the capsule.
- `EVIDENCE_BANKING_FAILURE__AFTER_RANK_047`: **47 of 47** prefix artifacts differ, plus the capsule.

This is directly contradicted by four committed authorities:

- `path_timing.paths.operator_approval` = `{"producer_transition_id": "T001", "before": "MUST_NOT_EXIST",
  "after_successful_producer": "MUST_EXIST_REGULAR_FILE", "immutable_after_creation": true,
  "readback": "DESCRIPTOR_RELATIVE_EXACT_CANONICAL_BYTES_AND_SHA256",
  "terminal_retention": "RETAIN_AS_APPEND_ONLY_EVIDENCE"}` — the file must exist immediately after T001 and be
  immutable thereafter;
- safety invariant `EVIDENCE_APPEND_ONLY` = `true`;
- `interface` = `{"attempts": 1, "retries": 0, "resume": false}` — there is no second pass in which to relabel;
- `dag.future_references_permitted: false` — yet the rank-1 artifact's bytes are a function of which of the
  rank-2…rank-48 transitions fails.

There is no reading that reconciles these. If the prefix artifacts are durable when the capsule is written
(which the entire durable-prefix taxonomy, `package_durable_start`, the `package_delta`/`primary_delta`/
`secondary_delta` accounting, and `capsule.durable_prefix_id` all presuppose), then terminalization must
rewrite `k` immutable files and, because each artifact embeds its dependencies' digests, recursively re-hash
the whole chain from the mutation point forward. That rewrite is not atomic: an interruption mid-relabel leaves
a durable package mixing `PASS` and `FAILURE_EVIDENCE` artifacts with broken dependency digests, live
graph-payload leases, and no capsule — exactly the class cycle-02 B2 rejected, reintroduced at the head instead
of the tail. Conversely, if nothing is durable until terminalization, then `path_timing`'s per-transition
`MUST_NOT_EXIST` → `MUST_EXIST_REGULAR_FILE` obligations, the 47-way durable-prefix outcome census, and the
`package_delta = 1 iff cut ≥ 9` accounting are all unsatisfiable.

This falsifies the review request's central claim that "the repair replaces every failure tail with one atomic
terminal capsule … all 47 success-prefix failure variants now add exactly one durable artifact." They add one
durable artifact **and** mutate every artifact already durable.

**Repair:** remove the terminal-outcome labels from the durable prefix. Make `outcome` and `result` properties
of the terminal artifact only (`final_declaration` / `failure_terminal_capsule__*`), and have prefix artifacts
carry an outcome-independent discriminator — e.g. `package_attempt_id` plus `creation_rank`, which are already
gated. `validate_package` should then check the terminal's outcome against the required set and check prefix
artifacts for attempt identity and causal rank, not for a label they cannot know. Gate the new rule and add a
negative probe that a prefix artifact carrying any outcome label is rejected.

## B2. Descriptor-continuity evidence is satisfiable with zero descriptors — terminal V7 finding `SECONDARY_SUCCESS_CONTINUITY_ZERO_DESCRIPTOR_ALLOWED` recurs at the artifact-payload layer

`descriptor_lease_manifest.lease_ids` and `.descriptor_identities` carry rule `{"kind": "TYPE", "type":
"ARRAY"}`. `descriptor_count`, `lease_count`, and `ordinals: [2,3,4,5,6]` are pinned as `EXACT_CONSTANT`, but
nothing relates the pinned cardinality to the arrays, and nothing constrains array element shape. The
`EQUAL_ARTIFACT_PAYLOAD_FIELD` rules added by the repair are equalities, not cardinalities.

Reproduced on a constructed `COMPLETE_SUCCESS` package with all descendants consistently rehashed —
`validate_package` returns `PASS`, 48/48 artifacts reached:

```
descriptor_lease_manifest              {"lease_count": 5, "ordinals": [2,3,4,5,6],
                                        "lease_ids": [], "descriptor_identities": []}
primary_descriptor_continuity_report   {"consumer_role": "PRIMARY", "descriptor_count": 5,
                                        "ordinals": [2,3,4,5,6], "path_reopen_count": 0,
                                        "lease_ids": [], "descriptor_identities": []}
secondary_descriptor_continuity_report  (identical)
descriptor_release_report              {"attempted_closures": 5, "successful_closures": 5,
                                        "duplicate_closures": 0, "unknown_leases": 0,
                                        "live_leases_after_release": 0, "lease_ids": []}
```

`continuity.exact_comparison_to_lease_manifest: true` degenerates to `[] == []`. The invariants
`GRAPH_LEASE_COUNT`, `PRIMARY_DESCRIPTOR_COUNT`, and `SECONDARY_DESCRIPTOR_COUNT` are each satisfied by a
contract literal while the evidence that is supposed to discharge them names zero descriptors. Separately,
`continuity.descriptor_identity_fields` — the nine-field registry that was itself the repair for terminal V7
finding `DESCRIPTOR_IDENTITY_FIELD_RESTATEMENTS_UNCHECKED` — is referenced by no payload rule on any artifact,
so `descriptor_identities` elements have no required shape at all. The banked
`f017-corrected-oracle-v7-cycle05-findings-reproduction-v1.json` records the repair for
`SECONDARY_SUCCESS_CONTINUITY_ZERO_DESCRIPTOR_ALLOWED` as "exact count five and ordinals 2..6"; that repair
exists in the contract and is absent from the evidence obligation.

The design already invented three rule kinds beyond `EXACT_CONSTANT`/`TYPE` in this repair, so the fix is the
same move, not new machinery.

**Repair:** add `ARRAY_LENGTH_EQUALS_PAYLOAD_FIELD` (binding `lease_ids` → `lease_count`,
`descriptor_identities` → `descriptor_count`, `ordered_shard_receipt_digests` → shard count) and
`ARRAY_OF_OBJECT_WITH_EXACT_KEYS` (binding `descriptor_identities` elements to
`continuity.descriptor_identity_fields`, read from the contract rather than restated). Enforce both in
`validate_package`, gate the rule assignment in `validate_documents`, and add the empty-array package as a
negative probe.

---

# NON_BLOCKING_REQUIRED

## N1. Failure-capsule closure counts are anchored to nothing, so `NO_LIVE_LEASES_AT_TERMINAL` is unfalsifiable on all 29 lease-bearing failure outcomes

The repair added two real checks — `attempted_closures == successful_closures + duplicate_closures +
unknown_leases` and `expected_leases == len(lease_ordinals) == len(lease_evidence_artifact_ids)` — but never
relates the counts to `expected_leases`. `live_leases_after_release` is an `EXACT_CONSTANT 0`, i.e. a
self-assertion. Reproduced on `CHECKPOINT_IDENTITY_FAILURE__AFTER_RANK_022` (`expected_leases: 5`), both
`PASS`:

| forged capsule | result |
| --- | --- |
| `attempted=0, successful=0, duplicate=0, unknown=0`, `live_leases_after_release=0` | UNCAUGHT |
| `attempted=42, successful=42, duplicate=0, unknown=0` | UNCAUGHT |

The first says five graph-payload leases were retained, zero closures were attempted, and zero leases are live
— an internal contradiction that conforms. Real leakage is bounded by the declared recursion terminator
(`NO_NEW_DURABLE_PREFIX_AND_PROCESS_EXIT_DESCRIPTOR_CLOSE`), which is why this is not blocking; the evidence
value of the capsule is not.

**Repair:** add `successful_closures + duplicate_closures == expected_leases` and
`live_leases_after_release == expected_leases - successful_closures - duplicate_closures` as capsule rules in
`validate_package`, and derive rather than pin `live_leases_after_release`.

## N2. The access-event ordering premise underneath the retained-lease derivation is ungated; a drifted design passes the independent validator and is caught only by a rank literal in unit test 5

Cycle-02 N1 asked that retained leases be derived from node ranks. They now are, on both sides
(`generate_…:255-258`, `validate_…:390-391`). But nothing gates that `checkpoint_access_event_k` precedes
`checkpoint_shard_receipt_k`: `required_subsequence` (`validate_…:256-263`) covers 20 artifacts and omits all
twelve identity artifacts.

Reproduced by coordinated generator drift — swapping the emission order inside `build_nodes` so the receipt
precedes its access event, then regenerating all contracts:

```
generate_f017_lifecycle_v8_design.py  -> PASS  (95 artifacts, 48 outcomes)
validate_f017_lifecycle_causal_design_v8.py -> PASS
construct_f017_lifecycle_v8_symbolically.py -> PASS (48/48, 1223 artifacts)
test_f017_lifecycle_causal_design_v8.py -> FAILED (1) : test_identity_prefix_release_is_exact… 0 != 1
```

In the drifted design, cut 14 has durable prefix `checkpoint_shard_receipt_2` — which declares
`retain_disposition: RETAIN_AS_PACKAGE_OWNED_DESCRIPTOR_LEASE` — while its capsule declares
`expected_leases: 0, lease_ordinals: []`. A retained graph-payload lease exists with no release obligation.
The independent validator accepts it. The only thing that objects is the hardcoded tuple
`((13,0),(14,1),(16,2),(18,3),(20,4),(22,5))` at `test_…:214`, which is the V7
`BYTE_CENSUS_BARE_VALIDATOR_LITERAL` pattern relocated into the test suite, and which covers only ranks 13–22.

**Repair:** in `validate_documents`, require `rank(checkpoint_access_event_k) < rank(checkpoint_shard_receipt_k)
< rank(checkpoint_access_event_{k+1})` for k = 1…6, derived from `node_map`, and replace the tuple in test 5
with the same derivation.

## N3. `critical_constants` is an allowlist, not a census: coordinated design drift on any artifact outside it is ungated

`validate_documents` checks `payload_constants` exactly for the 23 artifacts named in `critical_constants`
(plus the twelve identity artifacts, checked in the loop at `validate_…:351-358`). For every other artifact it
checks only `set(payload_constants) - set(payload_keys) == ∅`, so constants may be **added** freely.

Reproduced by patching the generator to pin `comparison_terminal.classification = "NUMERICAL_MISMATCH"`,
`comparison_terminal.result = "FAIL"`, and `primary_terminal.result / secondary_terminal.result = "FAIL"`,
then regenerating:

```
validate_f017_lifecycle_causal_design_v8.py -> PASS
construct_f017_lifecycle_v8_symbolically.py -> PASS (48/48)
test_f017_lifecycle_causal_design_v8.py     -> Ran 6 tests ... OK
```

A frozen V8 design that *requires* every `COMPLETE_SUCCESS` package to declare a numerical mismatch and two
consumer failures — alongside the correctly pinned `package_terminal.classification: "COMPLETE_SUCCESS"` —
passes everything.

**Repair:** make `critical_constants` total. Assert `node_map[aid]["payload_constants"] == expected[aid]` for
all 95 artifacts, with `{}` as the expected value where no constant is intended.

## N4. Terminal `result` and `classification` payload fields are free on `COMPLETE_SUCCESS` evidence

Cycle-02 DiD 4 is closed at the envelope (`value["result"]` is gated, and forging a capsule's envelope result
to `PASS` is rejected). The payload-level fields are not. Reproduced on a `COMPLETE_SUCCESS` package with
consistent descendant rehashing — all `PASS`:

| forged success package | verifier result |
| --- | --- |
| `comparison_terminal.classification = "NUMERICAL_MISMATCH"`, `.result = "FAIL"` | UNCAUGHT |
| `primary_terminal.result = "FAIL"` | UNCAUGHT |
| `primary_execution_evidence.layers_completed = 92` | UNCAUGHT |

`comparison_receipt.frozen_thresholds` is pinned exactly, but `comparison_receipt.classification` and both
comparison-terminal fields — the artifacts that carry the numerical verdict this whole feature exists to
produce — carry rule `TYPE: STRING`.

**Repair:** pin `comparison_receipt.classification`, `comparison_terminal.classification`, and the four
consumer `result` fields to their success values as `EXACT_CONSTANT` on the `COMPLETE_SUCCESS`-applicable
nodes, and add them to the total census from N3.

## N5. Digest-chain restatements bind nothing

Reproduced on a `COMPLETE_SUCCESS` package, all `PASS`:

| forged success package | verifier result |
| --- | --- |
| `checkpoint_identity_manifest.ordered_shard_receipt_digests = []` | UNCAUGHT |
| `checkpoint_access_event_4.prior_event_digest = "0"*64` | UNCAUGHT |
| `installation_receipt.installed_digest = "a"*64` (≠ its own `candidate_digest`, ≠ `installed_authorization.candidate_digest`) | UNCAUGHT |

The transitive dependency-SHA closure does cover these artifacts structurally, so the impact is confined to the
payload restatements — but `ordered_shard_receipt_digests` is the field by which the identity manifest is
supposed to name the six receipts it summarises, `checkpoint_access_journal_terminal.event_count: 6` is pinned
against a chain whose links are free, and `installation_receipt` proving `installed_digest == candidate_digest`
is the only statement that the installed authorization is the one the consumers validated.

**Repair:** add `EQUAL_ARTIFACT_PAYLOAD_FIELD` for `installation_receipt.candidate_digest` →
`installed_authorization.candidate_digest`, `EQUAL_PAYLOAD_FIELD` for `installed_digest` → `candidate_digest`,
an `ARRAY_OF_DEPENDENCY_DIGESTS` rule binding `ordered_shard_receipt_digests` to the six
`checkpoint_shard_receipt_*` artifact SHAs, and an equivalent chain rule for `prior_event_digest` /
`terminal_event_digest`.

---

# DEFENSE_IN_DEPTH

1. **Both cycle detectors remain unreachable** — cycle-01 DiD 9, cycle-02 DiD 2, now carried a third time
   despite appearing on both explicit repair lists. In `validate_documents` the `FUTURE_REFERENCE` rank check
   (line 230) precedes the DFS (line 246); in `validate_package` the `noncausal dependency rank` check
   (line 112) precedes `walk`. Verified: a genuine two-node cycle raises `FUTURE_REFERENCE`, and the package
   equivalent raises `artifact sha mismatch`. `ARTIFACT_CYCLE`, `artifact cycle`, and the banked
   `artifact_cycles: 0` all rest on the rank check alone; the `TWO_NODE_CYCLE`/`THREE_NODE_CYCLE` mutations
   probe the rank check.
2. **The "causal DAG" is a path graph.** Out-degree histogram is `{0: 1, 1: 94}` — no artifact has more than
   one dependency. The three multi-dependency bindings the generator writes (`primary_durable_start`,
   `secondary_descriptor_continuity_report`, `secondary_durable_start`) each name the artifact that is already
   `previous` and are deduplicated to no-ops by `dict.fromkeys`. `CONTINUITY_DURABLE_START_BINDING` therefore
   asserts nothing beyond chain adjacency, and the cross-branch splicing machinery has no branch to attack.
   (Gemini cycle 03's premise, false at 322 nodes, is now accidentally true.)
3. **Zero-lease capsules can record closures.** `PRE_MINT_FAILURE__AFTER_RANK_001` with `expected_leases: 0`
   accepts `attempted_closures: 7, successful_closures: 7`. Same root cause as N1.
4. **A capsule-absent durable prefix is not a declared outcome.** If the exclusive rename never lands, the
   prefix has no terminal and matches none of the 48 outcomes. It fails closed (`package artifact census
   mismatch`) and leases close at process exit per the declared terminator, but no outcome class names the
   state.
5. **Descriptor-release failures are classified as evidence-banking failures.** `failure_class_for_rank`
   returns `EVIDENCE_BANKING_FAILURE` for ranks 43–47, which covers `descriptor_release_start`,
   `descriptor_release_report`, and `descriptor_release_terminal`. There is no
   `DESCRIPTOR_RELEASE_FAILURE` class, so the three cuts where lease closure itself fails are indistinguishable
   from banking failures.
6. **`construct_outcome`'s `actual != required` assertion remains vacuous in the producer** (cycle-02 DiD 3,
   carried); it is meaningful in `validate_package`, where planted and deleted artifacts are both rejected.
7. **`cleanup_anomaly` is dead vocabulary.** It appears in the boolean key set of both
   `generate_…:40` and `validate_…:93` but is a payload key of no artifact among the 63 distinct keys.
8. **`static_design_mutations_rejected: 176` is still a hardcoded literal** in
   `qualify_f017_lifecycle_v8_design.py`. The suite now asserts equality (`assertEqual(len(mutations), 176)`),
   so drift is caught, but the qualifier restates rather than reads the count.
9. **The cycle-04 acceptance cites an artifact that does not exist.** The banked Gemini cycle-04 response
   states "I've documented the implementation plan summarizing these findings in the
   `f017_lifecycle_v8_review.md` review artifact." No such file exists in the tree or in any commit reachable
   from HEAD. The normalized result records zero findings, so nothing material is lost, but the review record
   points at a non-existent deliverable.

---

## Required work before a V9 review cycle

1. Remove terminal-outcome labelling from the durable prefix; make `outcome`/`result` terminal-artifact
   properties and re-gate `validate_package` on attempt identity plus causal rank for prefix artifacts. *(B1)*
2. Add array-cardinality and element-shape rules binding `lease_ids`/`descriptor_identities`/
   `ordered_shard_receipt_digests` to their pinned counts and to
   `continuity.descriptor_identity_fields`. *(B2, N5)*
3. Anchor capsule closure counts to `expected_leases` and derive `live_leases_after_release`. *(N1)*
4. Gate the access-event / shard-receipt interleaving in `validate_documents` and replace the rank tuple in
   test 5 with the derivation. *(N2)*
5. Make `critical_constants` a total census over all 95 artifacts. *(N3)*
6. Pin the comparison and consumer `result`/`classification` fields on `COMPLETE_SUCCESS`. *(N4)*
7. Bind `installation_receipt` to `installed_authorization`, and the access-journal and shard-receipt digest
   chains to real artifact digests. *(N5)*
8. Close DEFENSE_IN_DEPTH 1, carried unrepaired from two explicit repair lists — either order the DFS before
   the rank check or delete the dead branches and the banked `artifact_cycles: 0` claim.

## Verification for a V9 design

From a clean detached worktree run `validate_f017_lifecycle_causal_design_v8.py` (expect `PASS` with the new
census), `construct_f017_lifecycle_v8_symbolically.py`, and the enlarged mutation suite. Then confirm each
repair with a targeted negative probe that must fail closed:

- two constructed packages for different outcomes whose shared prefix artifacts are **byte-identical**, and a
  package whose prefix artifact carries any outcome label, which must be rejected;
- a `COMPLETE_SUCCESS` package with `lease_ids: []` and `descriptor_identities: []` across the manifest, both
  continuity reports, and the release report;
- a `descriptor_identities` element missing one of the nine registry fields;
- a lease-bearing capsule with `attempted_closures: 0` and with `successful_closures: 42`;
- the regenerated design with `checkpoint_shard_receipt_k` emitted before `checkpoint_access_event_k`, which
  must be rejected by the **validator**, not only by the test suite;
- a regenerated design pinning `comparison_terminal.classification: "NUMERICAL_MISMATCH"` and
  `primary_terminal.result: "FAIL"`;
- a `COMPLETE_SUCCESS` package with `ordered_shard_receipt_digests: []` and with
  `installation_receipt.installed_digest != candidate_digest`;
- a genuine artifact cycle that reaches the DFS rather than the rank check.

Re-bank the mechanical qualification only after every probe fails closed.
