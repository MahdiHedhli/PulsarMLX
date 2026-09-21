All probes complete. Posture verified: reviewed worktree clean at `f9224e3e`, no `__pycache__` on tracked paths, all execution in throwaway `git archive` extractions proven byte-identical, all forgeries in auto-cleaned temp dirs. `qualify_f017_lifecycle_v8_design.py` deliberately not run — it rewrites banked evidence.

---

# F017 Lifecycle V8 Causal Design — Opus Design Review, Cycle 06

**Posture.** Exact committed bytes at `f9224e3e138f675a4a41fffd8f96bb355c0f6d80`, detached read-only worktree `/private/tmp/f017-v8-opus-c6.cvdLfo`. Execution in `/tmp/f017c6exec` and `/tmp/f017c6gen`, both `diff -r` byte-identical to the worktree before and after. No original checkpoint shard opened, no Event-04 authority minted, no P1 attempt 2.

## Verdict

`REJECT`

Zero `BLOCKING`, one `NON_BLOCKING_REQUIRED`, ten `DEFENSE_IN_DEPTH`.

## Mechanical reproduction — all green

| component | result |
| --- | --- |
| `validate_f017_lifecycle_causal_design_v8.py` | `PASS` — 95 artifacts, 94 edges, 48 outcomes, 25 invariants |
| `construct_f017_lifecycle_v8_symbolically.py` | `PASS` — **48/48** outcomes, 1223 artifacts, max closure depth 48 |
| `test_f017_lifecycle_causal_design_v8.py` | **13/13 OK** (179 static + 32 runtime = **211** rejected mutations) |
| generator determinism | re-run into a fresh extraction reproduces every committed contract **byte-identically** |
| banked qualification | matches my run exactly (95/94/48/1223/48/25/179/32/211/1175/238,458,632,928) |
| durable-prefix immutability | **1128** prefix artifacts over 47 failure outcomes — independently recomputed 1128 |
| `strict_rank_edges_validated` | reports **1175**; my independent recomputation over the 48 applicability sets is **1175** |
| static mutations | all 179 re-executed: **0 vacuous, 0 passing**, spread across 26 distinct rejection rules |

**Adversarial sweep: 216 probes across 12 batches.** Every probe drove the package to a coordinated fixed point — repairing all dependency SHAs *and* every `ARTIFACT_SHA256` / `ARTIFACT_SHA256_SEQUENCE` / `EQUAL_*` restatement — while re-imposing the forgery each round, so each rule was isolated rather than shadowed by the digest chain. Where my first harness healed the field under test I re-ran with an isolating rehash; four apparent "UNCAUGHT" results (`primary_output_digest` unbound, `secondary_output_digest` unbound, digests swapped, digests cross-assigned) were harness artifacts and are in fact **rejected**.

## Cycle-05 findings: independently re-attacked

| # | status on `f9224e3e` | evidence |
| --- | --- | --- |
| **B1** comparison ENUM conditioned on artifact, not outcome | **CLOSED** | New `OUTCOME_CLASSIFICATION_ENUM` rule kind carries `success_values`/`failure_values`; `check_…:81-84` selects on `outcome == "COMPLETE_SUCCESS"`. Exhaustive 8 outcomes × 5 verdicts = 40 probes: **`ORACLE_DISAGREEMENT` and `ORACLE_EXECUTION_FAILURE` accepted at all 7 failure outcomes that bank `comparison_receipt`, rejected only at `COMPLETE_SUCCESS`**; the other three accepted everywhere. Both halves derived from `numerical_contract./future_p1_consequence` (`validate_…:284-288`, `generate_…:125-126`), sha-verified at line 241 before being read at 283. Six design-level re-widenings — restore 5 members to `success_values`, re-narrow `failure_values` to 3, revert to plain `ENUM`, swap the sets, pin to a constant, invent a sixth verdict — **all fail closed** on `PAYLOAD_RULE_EXACT_SEMANTICS`. The missing positive probe now exists: `test_oracle_disagreement_is_failure_outcome_compatible`. |
| **N1** `unknown_leases` hard-pinned to zero | **CLOSED** | The `unknown_leases != 0` clause and the dead zero-lease clause are gone. `check_…:130-131` now derives `live == expected − successful − duplicate` alongside `attempted == successful + duplicate + unknown`. 18-case sweep: `5/5/0/0`, `5/4/1/0`, `5/0/5/0`, `10/5/0/5`, `2/1/0/1`, `99/1/0/98`, zero-lease `0/0/0/0` and zero-lease `7 unknown` all **accepted**; `5/0/0/5` (unknown discharging an expected lease), `6/5/1/0`, `4/4/0/0`, `0/0/0/0` on a 5-lease capsule, forged `live=1`, negatives, bool-as-int, forged `expected` all **rejected**. Three new tests pin the chosen semantics in both directions. |
| **N2** shared `event_id` / aliased opaque identifiers | **CLOSED** | `check_…:163-176` collects the 7 identity classes and requires pairwise distinctness plus the strict grammar `[A-Z0-9](?:[A-Z0-9-]{0,126}[A-Z0-9])?`. **All 21 pairwise aliasings rejected, every one by the intended rule** (`package identifier grammar or uniqueness mismatch`) at a verified fixed point — no shadowing. Grammar sweep: empty, single/multiple space, tab, lowercase, embedded space, leading/trailing hyphen, underscore, non-ASCII, 129 chars all rejected; `OK-1`, `A`, `0`, `A--B`, 128 chars accepted. Positive control — all 7 classes set to distinct non-default values, and the whole *primary* chain aliased to one distinct value — still **PASS**. |

**No structural regression.** 15 re-attacks from cycle-05's confirmed-rejected list all still fail closed: terminal deletion, stray file, prefix deletion, prefix relabelling in both directions, `event_04_executed: True`, `mandatory_stop: False`, `original_checkpoint_access: 1`, forged `package_terminal.classification`, noncanonical bytes, duplicate JSON keys, zeroed root-authority sha, `layers_completed: 92`, `synthetic_only: False`, forged `creation_rank`, dropped dependency edge, planted `final_declaration` in a failure package. A further 15 capsule fixed-point forgeries (prefix relabelling both directions, class/classification downgrade to `COMPLETE_SUCCESS`, weakened atomicity, emptied and redirected `lease_evidence_artifact_ids`, inflated `expected_leases`, `active_generation: LIVE`, cross-outcome capsule splice) all reject.

**Adjacent controls verified.** Consumer event chains bind end to end: detaching `event_id` at any of the 8 downstream links, or re-pointing the whole secondary chain at the primary's event, is rejected. Execution evidence binds role (`consumer_role` `EXACT_CONSTANT` per role), event id, and a `SHA256` `numerical_output_digest`; comparison evidence binds both digests — zeroing either, cross-assigning, or fully swapping them is rejected by `EQUAL_ARTIFACT_PAYLOAD_FIELD`. Descriptor degeneracy is closed: shared `(device, inode)` across all five or any two, `IDENTITY_ONLY` role, extra/dropped fields, reversed order, permuted sizes, identical lease ids all reject. The symbolic exemplar now models one device with distinct inodes (`construct_…:38`), retiring cycle-05 DiD 7's second half.

---

# BLOCKING

None. The three cycle-05 findings are genuinely closed, each by the mechanism its repair proposed, and each is now pinned by a probe in the intended direction.

---

# NON_BLOCKING_REQUIRED

## N1. `mode` is the one descriptor identity integer left un-ranged, and out-of-domain values escape the checker's `ValueError` rejection contract as an uncaught `OverflowError`

`check_…:95` range-checks five of the six identity integers — `device`, `inode`, `size`, `mtime_ns`, `ctime_ns` — and then line 96 passes `item["mode"]` straight into `stat.S_ISREG` without one. `S_ISREG` is a C-level conversion to `unsigned`, so every out-of-domain mode raises `OverflowError`, not `ValueError`:

| forged `mode` | verifier |
| --- | --- |
| `-1`, `-28672`, `-32768` | `OverflowError: can't convert negative value to unsigned int` |
| `2**32 + 0o100644` | `OverflowError: mode out of range` |
| `2**64 + 0o100644` | `OverflowError: Python int too large to convert to C unsigned long` |
| `0o1100644` (bit above the type field) | `OverflowError: mode out of range` |

Confirmed through the CLI entry point as well: `check_f017_transitive_artifact_closure_v8.py --outcome COMPLETE_SUCCESS` exits `1` with a raw traceback and no result on stdout. The five other integers reject cleanly with `descriptor identity array mismatch`, as do `mode: True` and `mode: "33024"`.

**Nothing is accepted** — this fails closed, and no honest package can reach it, since a real `fstat` never yields a negative or ≥2³² mode. That is why it is not blocking. But `validate_package` is the design's normative bank-time gate, and `ValueError` is de facto its rejection signal: `construct_outcome:149` and all 13 suite tests classify rejection by catching it. The commit's own new control is that *"descriptor mode must identify a regular file"* and that *"identity integers are nonnegative"*; the type-bit half landed and the domain half did not, in the single field where the omission converts a typed rejection into an unclassified crash.

**Failure scenario.** An evidence package is corrupted after banking — bit rot, or an editor writing `"mode": -1`. The reference gate is re-run to decide whether the package is still conformant. Instead of `descriptor identity array mismatch` it aborts with `OverflowError`. An implementer who mirrored this reference distinguishes "package rejected" from "verifier fault" by exception class, so a conformance rejection is reported as an internal error and the package falls to `UNBANKED_TERMINALIZATION_FAILURE_HUMAN_STOP_NO_RETRY` rather than being classified. Bounded — the outcome is still a human stop with no retry, and no forgery is admitted.

**Repair.** One clause: add `mode` to the existing nonnegativity list and bound it above, `0 <= item["mode"] < 2**32`, evaluated before `stat.S_ISREG`. Add `NEGATIVE_DESCRIPTOR_MODE` and `OVERSIZED_DESCRIPTOR_MODE` to the runtime attack list beside the existing `DIRECTORY_DESCRIPTOR_MODE` and `NEGATIVE_DESCRIPTOR_TIMESTAMP` — both currently pass through the same code path and neither exercises the gap. `RUNTIME_CLOSURE_MUTATIONS` moves 32 → 34.

---

# DEFENSE_IN_DEPTH

1. **`self_references: 0` and `future_references: 0` are still bare literals.** `construct_…:173-174` reports both as constants that `validate_…:488` then checks as evidence, and the banked qualification records both. The cycle-05 `cycles: 0` literal *is* closed — `strict_rank_edges_validated` is genuinely derived (`check_…:155`), and I confirmed 1175 by independent recomputation — but its two siblings were not converted. *(partial carry of cycle-05 DiD 1)*

2. **No test exercises an artifact cycle.** `test_cross_package_splice_and_dependency_census_fail_closed` is now honestly named, and its second half plants a self-dependency caught by `dependency census mismatch`. Cycles remain unreachable by construction via strict rank decrease, so this is a naming/coverage note only. *(carried, downgraded)*

3. **The `UNDECLARED_PAYLOAD_CONSTANT` census is still unreachable.** I probed all 11 payload keys of the 8 artifacts outside `constants_checked`: it fired **0/11** — every one is caught earlier by the override ladder. The suite's `COORDINATED_OPAQUE_ID_CONSTANT` mutation is caught by `PAYLOAD_CONSTANT_RULE_BINDING`. The census is future insurance; worth keeping, worth not crediting. *(carried cycle-05 DiD 3)*

4. **`layers_completed: 79` is still a restated literal** in `generate_…:223` and `validate_…:359`, though `TARGET_LAYERS_79` sits in the same sha-bound numerical contract. The other half of cycle-05 DiD 4 *is* closed — the generator now derives the classification vocabulary through the contract rather than restating it. *(half carried)*

5. **`RUNTIME_CLOSURE_MUTATIONS = 32` reconciles as `len(attacks) + 6` where `6` is a magic literal** for mutations spread across four other tests (2 splice + 1 unknown-lease + 1 capsule-cleanup + 2 identifier-distinctness). I confirmed the arithmetic by hand; the suite does not. Separately, `v7_terminal_findings_reproduced: 16` in `qualify_…:24` remains hardcoded — an improvement on cycle-05's misleading `cycle_05_findings_reproduced: "ALL_16"`, but still never re-derived from its source. *(carried cycle-05 DiD 5)*

6. **Descriptor-release failures are still classified as evidence-banking failures.** `failure_class_for_rank` returns `EVIDENCE_BANKING_FAILURE` for ranks 43–47, covering the three cuts where lease closure itself fails. *(carried cycle-05 DiD 6)*

7. **Lease identifiers are held to a far weaker grammar than package identifiers.** `lease_id` inside `descriptor_identities` is checked only for `type is str` and truthiness, and `lease_ids` is only `ARRAY_EXACT_LENGTH`. Five whitespace-only lease ids (`" "`, `"  "`, …) and five lowercase-with-spaces ids are both **UNCAUGHT** — they are pairwise distinct and truthy, so the manifest semantic check passes. Aliasing all five to one value, or to the `owner_nonce`, is correctly rejected. The same one-line regex already applied to the 7 package identifier classes would close this.

8. **`DESCRIPTOR_IDENTITY_ARRAY` requires distinct `(device, inode)` pairs but not a single device.** Five *distinct* devices sharing one inode is **UNCAUGHT**. The rule is POSIX-correct — distinct pairs are distinct files — but six shards of one checkpoint directory cannot span five devices. The honest configuration (one device, distinct inodes) now passes and is what the exemplar models, so this is exemplar-realism hardening, not a live hole.

9. **The comparison verdict is still asserted, not discharged.** Both output digests are now bound end to end, but nothing relates the `classification` to whether they agree: `EXACT_EXPECTED_TOKEN_STABLE` with two *differing* digests is accepted, and `ORACLE_DISAGREEMENT` with two *identical* digests is accepted at `COMPARISON_FAILURE__AFTER_RANK_041`. The lifecycle model delegates numerical semantics to the V3 contract, so this is arguably out of scope — but it is the last step between "the comparator recorded a verdict" and "the evidence proves the verdict". *(cycle-05 DiD 8, substantially closed, residue only)*

10. **`duplicate_closures` alone can fully discharge the expected-lease census.** `5/0/5/0` — zero successful closures, five duplicates — is accepted on a 5-lease capsule, including at prefix ranks that never banked `descriptor_release_start`. Defensible under a crash-restart reading (a lease already closed by process exit is re-attempted and reports duplicate), but the design does not state that reading anywhere, and no probe pins it.

---

## Remediation order

1. **N1** — range-check `mode` before `stat.S_ISREG`; add the two negative probes. *(required; one clause, `RUNTIME_CLOSURE_MUTATIONS` 32 → 34)*
2. **DiD 1 / 4 / 5** — derive `self_references`/`future_references` the way `strict_rank_edges_validated` is now derived; resolve `layers_completed` through `resolve_pointer`; assert the runtime total from its constituents and re-derive the V7 reproduction count.
3. **DiD 7** — apply the package-identifier regex to `lease_id`; add the whitespace and lowercase rows as negative probes.
4. **DiD 3 / 10** — either delete the unreachable census or document it as dormant; state the duplicate-closure semantics and probe them.
5. **DiD 2 / 6 / 8 / 9** — V9 candidates: a `DESCRIPTOR_RELEASE_FAILURE` class (renames three outcomes, churns the census), single-device descriptor modelling, and binding the classification to a digest of both outputs.

Steps 2–5 are independent. **Step 1 is the only gate, and it is the only required finding** — a one-clause completion of a control this commit introduced. B1, N1 and N2 from cycle 05 are all genuinely closed, each by the mechanism its repair proposed; the generator is deterministic, the banked evidence matches my independent run digit for digit, and 216 adversarial probes produced no accepted forgery. The design direction is sound; the verdict is `REJECT` solely because a required finding exists.
