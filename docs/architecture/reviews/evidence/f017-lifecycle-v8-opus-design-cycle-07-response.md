All probes complete. Posture: reviewed worktree clean at `781ce3ef`, no `__pycache__` on tracked paths, all execution in throwaway `git archive` extractions proven byte-identical before and after, all forgeries in auto-cleaned temp dirs. `qualify_f017_lifecycle_v8_design.py` deliberately not run — it rewrites banked evidence.

---

# F017 Lifecycle V8 Causal Design — Opus Design Review, Cycle 07

**Posture.** Exact committed bytes at `781ce3ef90227c9abfb92c032a3fb5e460d43a13`, detached read-only worktree `/private/tmp/f017-v8-opus-c7.pcMR1E`. Execution in `/tmp/f017c7exec` and `/tmp/f017c7gen`, both `diff -r` byte-identical to the worktree. No original checkpoint shard opened, no Event-04 authority minted, no P1 attempt 2.

## Verdict

`REJECT`

Zero `BLOCKING`, two `NON_BLOCKING_REQUIRED`, eight `DEFENSE_IN_DEPTH`.

## Mechanical reproduction — all green

| component | result |
| --- | --- |
| `validate_f017_lifecycle_causal_design_v8.py` | `PASS` — 95 artifacts, 94 edges, 48 outcomes, 25 invariants |
| `construct_f017_lifecycle_v8_symbolically.py` | `PASS` — **48/48** outcomes, 1223 artifacts, max closure depth 48 |
| `test_f017_lifecycle_causal_design_v8.py` | **13/13 OK** (179 static + 37 runtime = **216** rejected mutations) |
| generator determinism | re-run into a fresh extraction reproduces every committed contract and doc **byte-identically** |
| banked qualification | matches my run exactly (95/94/48/1223/48/25/179/37/216/1175/238,458,632,928) |
| durable-prefix immutability | **1128** prefix artifacts over **47** failure outcomes — independently recomputed 1128, **0** byte mismatches |
| `strict_rank_edges_validated` | reports **1175**; independent recomputation over the 48 applicability sets is **1175** |
| `self_references` / `future_references` | now genuinely derived (`construct_…:166-167`); independently recomputed **0 / 0** |
| static mutations | all 179 re-executed under instrumentation: **0 vacuous, 0 passing, 0 non-`ValueError` escapes**, 26 distinct rules |
| runtime mutations | all 31 listed attacks: **0 passing, 0 non-`ValueError` escapes**, 13 distinct rules |

**Adversarial sweep: 187 probes.** Every probe drove the package to a coordinated fixed point — repairing all dependency SHAs *and* every `ARTIFACT_SHA256` / `ARTIFACT_SHA256_SEQUENCE` / `EQUAL_*` restatement, three rounds, while re-imposing the forgery each round — so each rule was isolated rather than shadowed by the digest chain. Positive controls (unmutated package; all 7 identity classes reset to fresh distinct values; honest one-device/distinct-inode descriptor set) all `PASS`.

## Cycle-06 finding: independently re-attacked

| # | status on `781ce3ef` |
| --- | --- |
| **N1** descriptor `mode` out-of-domain escapes the `ValueError` rejection contract | **NOT CLOSED** — the repair landed, but the bound it chose is wrong for this platform. See `NON_BLOCKING_REQUIRED` N1 below. |

**Cycle-05 findings re-attacked, all still closed.** `B1` (comparison ENUM conditioned on outcome): exhaustive 8 outcomes × 5 verdicts = 40 probes — `ORACLE_DISAGREEMENT` and `ORACLE_EXECUTION_FAILURE` accepted at all 7 failure outcomes that bank `comparison_receipt`, rejected only at `COMPLETE_SUCCESS`; the other three accepted everywhere. `N1` (lease accounting): 16-case sweep — `5/5/0/0`, `5/4/1/0`, `5/0/5/0`, `10/5/0/5`, `99/1/4/94`, zero-lease `0/0/0/0`, zero-lease `7 unknown` accepted; `5/0/0/5`, `6/5/1/0`, `4/4/0/0`, `0/0/0/0` on a 5-lease capsule, forged `live=1`, negative, bool-as-int, forged `expected` all rejected. `N2` (identifier distinctness): **all 21 pairwise aliasings rejected, every one by the intended rule** (`package identifier grammar or uniqueness mismatch`) at a verified fixed point.

**Adjacent closures verified.** `DEFENSE_IN_DEPTH` 7 and 8 from cycle 06 are genuinely closed: the package-identifier regex now applies to `lease_id` (13 malformed ids rejected — empty, single/double space, tab, lowercase, embedded space, leading/trailing hyphen, underscore, non-ASCII, newline, dot, 129 chars; `OK-1`/`A`/`0`/`A--B`/128-char accepted), and `len({device}) != 1` closes the multi-device hole (5 distinct devices sharing one inode now rejected, as is any 2-device split; 1 device with distinct inodes accepted). Descriptor hardening holds across 20 further probes: `IDENTITY_ONLY` role, extra/dropped fields, reversed order, permuted sizes, negative inode/size/ctime/device, shuffled ordinal, inflated `lease_count`, `lease_ids` desynced from descriptors. Consumer event chains bind end to end — detaching `event_id` at any of the 8 downstream links is rejected; only the two chain roots accept a fresh value, correctly. Execution/comparison digest binding holds under isolation: zeroing either output digest, swapping them, cross-assigning, forging the primary evidence digest against a frozen receipt, and swapping `consumer_role` all reject.

**No structural regression.** 22 re-attacks fail closed: terminal deletion, prefix deletion, stray file, noncanonical bytes, duplicate JSON keys, zeroed root-authority sha, dropped root authority, prefix relabelling in both directions, forged `creation_rank`, dropped dependency edge, self-dependency, cross-outcome capsule splice, capsule `outcome`/`result` downgrade to success, `event_04_executed: True`, `original_checkpoint_access: 1`, `active_generation: LIVE`, weakened atomicity, emptied and redirected `lease_evidence_artifact_ids`, `synthetic_only: False`, forged schema, extra payload key, `path_reopen_count`, `observed_total_bytes`, zeroed shard digest.

---

# BLOCKING

None. Nothing in this commit admits a forgery. Every probe that is not a crash either rejects or is an honest configuration.

---

# NON_BLOCKING_REQUIRED

## N1. The `mode` range check bounds the wrong domain — `[2**16, 2**32)` still escapes as `OverflowError`, and both new probes are placed outside the gap

`check_…:96` adds `item["mode"] < 0 or item["mode"] >= 2**32` before `stat.S_ISREG` at line 97. The lower bound is correct. The upper bound is not: `stat.S_ISREG` resolves to the C `_stat` builtin, whose argument is converted to `mode_t`, and on this host `mode_t` is 16-bit. I binary-searched the accepted domain directly:

```
largest accepted mode: 65535 (0xffff)  ->  first rejected: 65536 (0x10000)
```

So the guard admits `[0, 2**32)` while the callee accepts `[0, 2**16)`. The 4,294,901,760 values in between reach `S_ISREG` and raise `OverflowError`, exactly as in cycle 06:

| forged `mode` | inside new guard? | verifier |
| --- | --- | --- |
| `-1`, `-28672`, `-32768`, `-2**63` | no | `ValueError: descriptor identity array mismatch` ✔ |
| `2**32`, `2**32 + 0o100644`, `2**64 + …`, `2**128` | no | `ValueError: descriptor identity array mismatch` ✔ |
| **`0o1100644`** (one bit above the type field, `= 294820`) | **yes** | **`OverflowError: mode out of range`** |
| **`2**32 - 1`** (`= 4294967295`) | **yes** | **`OverflowError: mode out of range`** |

Confirmed through the CLI entry point: `check_f017_transitive_artifact_closure_v8.py --outcome COMPLETE_SUCCESS` on a fixed-point package with `"mode": 294820` exits `1` with a raw traceback terminating at `line 97, in <genexpr> / or not stat.S_ISREG(item["mode"])` and prints no result on stdout. Type confusions (`True`, `"33024"`, `33024.0`, `None`) and non-regular types (directory, symlink, socket, zero) all reject cleanly with `ValueError`.

The two probes this commit added cannot see the gap. `NEGATIVE_DESCRIPTOR_MODE` uses `-1` and `OVERSIZED_DESCRIPTOR_MODE` uses `2**32 + 0o100644` — both were chosen to match the bound the code implements rather than the domain the callee accepts, so they exercise the new clause and stop short of the region it fails to cover. The suite is green and stays green with the defect live. `0o1100644` is the natural probe here — it is the smallest single-bit corruption above the `S_IFMT` type field and it is precisely what the new clause misses.

There is a second-order consequence worth stating: `2**32` presumes a 32-bit `mode_t`. A reference conformance gate whose *rejection class* depends on the host's `mode_t` width is not a portable normative gate — the same banked package would classify differently on a platform with a wider `mode_t`. A POSIX mode has 16 meaningful bits; `0 <= mode < 2**16` is both the honest domain and the platform-independent one.

**Nothing is accepted** — this fails closed, and no honest package reaches it, since `os.fstat().st_mode` on this platform is a widened `mode_t` and is always below `2**16`. That is why it is not blocking. But `validate_package` is the design's normative bank-time gate and `ValueError` is de facto its rejection signal: `construct_outcome:149` and all 13 suite tests classify rejection by catching it.

**Failure scenario.** A banked evidence package is corrupted after the fact — bit rot flipping bit 18 of a stored mode, or an editor writing `"mode": 294820`. The reference gate is re-run to decide whether the package is still conformant. Instead of `descriptor identity array mismatch` it aborts with `OverflowError`. An implementer who mirrored this reference distinguishes "package rejected" from "verifier fault" by exception class, so a conformance rejection is reported as an internal error and the package falls to `UNBANKED_TERMINALIZATION_FAILURE_HUMAN_STOP_NO_RETRY` rather than being classified. Bounded — a human stop with no retry, and no forgery admitted.

**Repair.** Change `2**32` to `2**16` on `check_…:96`. Replace `OVERSIZED_DESCRIPTOR_MODE`'s value with `0o1100644` (or add a third probe at `2**16`) so the boundary the code enforces is the boundary the suite tests.

## N2. Two further un-typed inputs on the same descriptor path escape the `ValueError` contract as `AttributeError` and `TypeError`

N1's repair completed one of three domain gaps in the descriptor code path. The other two are structural, predate this commit, and behave identically at the CLI:

- **`check_…:91`** — `[item.get("shard_ordinal") for item in observed]` runs *before* the `type(item) is not dict` guard on line 93. A non-dict element in `descriptor_identities` raises `AttributeError: 'str' object has no attribute 'get'` (also confirmed for `int` and `list` elements). Only replacing the whole array with a non-list is caught cleanly, by line 90.
- **`check_…:144`** — `len(set(payload["lease_ids"]))` is evaluated with `lease_ids` constrained only by `ARRAY_EXACT_LENGTH` (type `list`, correct length). Unhashable elements raise `TypeError: cannot use 'list' as a set element` (also confirmed for `dict` elements). `lease_ids` of the right length holding ints is caught cleanly, by the manifest semantic check.

**Failure scenario.** Identical to N1 and reachable by the same route: post-bank corruption or a hand-edit replaces a descriptor object with a bare string, or a lease id with a one-element list. The gate crashes instead of returning `descriptor identity array mismatch` / `descriptor lease manifest semantic mismatch`, and a mirroring implementer routes a conformance rejection to the verifier-fault path.

**Repair.** Hoist the `type(item) is not dict or set(item) != fields` guard on line 93 ahead of the two `item.get(...)` comprehensions on lines 91-92; add `any(type(item) is not str for item in payload["lease_ids"])` ahead of the `set()` on line 144. Add `NON_DICT_DESCRIPTOR_ENTRY` and `UNHASHABLE_LEASE_ID` to the runtime attack list. `RUNTIME_CLOSURE_MUTATIONS` moves 37 → 39.

---

# DEFENSE_IN_DEPTH

1. **`self_references` / `future_references` are derived in the constructor but still literal in the banked qualification.** `construct_…:166-167` genuinely derives both from the DAG and `validate_…:488` checks the derived values — cycle-06 DiD 1 is closed at the design layer, and I independently recomputed `0/0`. But `qualify_…:36-37` writes `"self_references": 0, "future_references": 0` as hardcoded constants rather than reading `validation["symbolic"]["self_references"]`, so the banked evidence file still asserts what the constructor already proves. One-line fix, same shape as `strict_rank_edges_validated` on line 38. *(partial carry)*

2. **No test exercises an artifact cycle.** Cycles remain unreachable by construction via strict rank decrease; `test_cross_package_splice_and_dependency_census_fail_closed` plants a self-dependency caught by `dependency census mismatch`. Naming/coverage note only. *(carried, downgraded)*

3. **The `UNDECLARED_PAYLOAD_CONSTANT` census is still unreachable.** I re-probed all 11 payload keys of the 8 artifacts outside `constants_checked`: it fired **0/11** — every one is caught earlier by `PAYLOAD_CONSTANT_RULE_BINDING`. Future insurance; worth keeping, worth not crediting. *(carried, re-confirmed)*

4. **`layers_completed: 79` is still a restated literal** in `generate_…:223` and `validate_…:359`, though `TARGET_LAYERS_79` sits in the same sha-bound numerical contract. *(carried)*

5. **`RUNTIME_CLOSURE_MUTATIONS = len(attacks) + 6` where `6` is a magic literal** for mutations spread across four other tests (2 splice + 1 unknown-lease + 1 capsule-cleanup + 2 identifier-distinctness). I confirmed the arithmetic by hand; the suite does not. Separately, `v7_terminal_findings_reproduced: 16` in `qualify_…:27` remains hardcoded and never re-derived from its source. *(carried)*

6. **Descriptor-release failures are still classified as evidence-banking failures.** `failure_class_for_rank` returns `EVIDENCE_BANKING_FAILURE` for ranks 43–47, which covers `descriptor_release_start` (43), `descriptor_release_report` (44) and `descriptor_release_terminal` (45) — the three cuts where lease closure itself fails. *(carried)*

7. **The comparison verdict is still asserted, not discharged.** Both output digests are bound end to end, but nothing relates `classification` to whether they agree: `EXACT_EXPECTED_TOKEN_STABLE` with two *differing* digests is accepted, and `ORACLE_DISAGREEMENT` with two *identical* digests is accepted at `COMPARISON_FAILURE__AFTER_RANK_041`. Both re-confirmed at a fixed point. The lifecycle model delegates numerical semantics to the V3 contract, so this is arguably out of scope. *(carried)*

8. **`duplicate_closures` alone can fully discharge the expected-lease census.** `5/0/5/0` — zero successful closures, five duplicates — is accepted on a 5-lease capsule, including at prefix ranks that never banked `descriptor_release_start`. Defensible under a crash-restart reading, but the design does not state that reading anywhere and no probe pins it. *(carried)*

---

## Remediation order

1. **N1** — `2**32` → `2**16` on `check_…:96`; re-point `OVERSIZED_DESCRIPTOR_MODE` at `0o1100644`. *(required; one character-level edit plus one probe value)*
2. **N2** — hoist the dict guard ahead of the two `item.get` comprehensions; type-check `lease_ids` elements before `set()`; add two probes, `RUNTIME_CLOSURE_MUTATIONS` 37 → 39. *(required)*
3. **DiD 1 / 4 / 5** — read `self_references`/`future_references` through from the constructor result; resolve `layers_completed` through `resolve_pointer`; assert the runtime total from its constituents and re-derive the V7 reproduction count.
4. **DiD 3 / 8** — either delete the unreachable census or document it as dormant; state the duplicate-closure semantics and probe them.
5. **DiD 2 / 6 / 7** — V9 candidates: a `DESCRIPTOR_RELEASE_FAILURE` class (renames three outcomes, churns the census) and binding the classification to a digest of both outputs.

Steps 3–5 are independent of the gate. **Steps 1 and 2 are the gate.** Every cycle-05 and adjacent-control closure holds under independent re-attack: B1, cycle-05 N1 and N2 are genuinely closed, the lease-identifier grammar and single-device controls landed and are pinned in both directions, self/future reference counts are now derived, the generator is deterministic, the banked evidence matches my independent run digit for digit, and 187 adversarial probes produced no accepted forgery.

The one substantive regression from cycle 06 is that its sole required finding was repaired against the wrong bound and then probed at values that cannot detect the residue — a green suite over a live gap. The design direction remains sound; the verdict is `REJECT` because required findings exist.
