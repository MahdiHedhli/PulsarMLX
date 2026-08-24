Review complete. Repository files unmodified; both scratch worktrees removed; no Event 04 minted or executed; no oracle run; no P1 attempt 2; no original checkpoint shard payload accessed.

# F017 Event-04 Authority Reconciliation — Opus Review Cycle 01

Evidence head `a71d23f2` (detached read-only worktree). Measurement head `418a4121`, tree `eb337433`. Authority bundle head `d5d4c412`.

## 1–3. Original mismatch and exact measured SHAs

The stale `f017-corrected-full-checkpoint-oracle-scientific-access-v6.json` carried internal bindings generated before the reviewed parser/coordinator repairs and never regenerated:

| role | stale contract | exact Git bytes @ `418a4121` | Git blob |
|---|---|---|---|
| parser | `be4a52a0…2981a` | `3bf8fad9ec3ae1a02f1281acdd53b870160b384532315d0152604695864e0d8d` | `741eb18c…` |
| coordinator | `5c80525f…4f673` | `89a1881e992d8b6364dc80fc621bc54c97c874f32542f83d004f493d74203744` | `823b5646…` |

I recomputed both from `git show <head>:<path>`. Measurement manifest and lifecycle declaration always agreed with Git; only the scientific-access internal bindings diverged. `conflict-v1.json` states this accurately, including the real root cause (`validator_gap`: the authorizer checked the contract's *outer* file SHA and never loaded its internal bindings).

## 4–7. Measurement V4, append-only successor, path/SHA equalities

All **64** V4 entries independently verified: SHA-256 of exact Git bytes, `git ls-tree` blob identity, and working-tree byte identity — zero discrepancies, zero duplicate paths, all `semantic_role: LOAD_BEARING_ACTIVE_OR_RETIREMENT_AUTHORITY`. V4 = V3's 61 entries + the 3 new reconciliation scripts, with `.github/workflows/macos.yml` remeasured; `parent_measurement_manifest_sha256` matches V3's bytes. No measured path changed between `418a4121` and `a71d23f2`, so the evidence-descendant rule holds.

Append-only discipline confirmed: the stale V6 contract and the original lifecycle declaration are **byte-identical** to their pre-conflict state; the correction is a separate appended document. The V2 diff against stale V6 touches only `bindings` (parser/coordinator corrected, 6 bindings added), `source_of_truth` (new), `measurement` (two anti-excuse rules), `schema` 6.0.0→6.0.1, `status`, `supersedes` — `accounting`, `frozen_thresholds`, `production_checkpoint`, `context`, `execution`, `safety` unchanged, substantiating `numerical_authority_changed: false` / `lifecycle_semantics_changed: false`.

Every declared path/SHA pair I could cross-check (12 spot checks across Git, measurement, scientific access, correction, conflict, manifest, inert, validator, rehearsal, generator, CI workflow) matched exactly.

## 8–11. Mutations

`validate_f017_event04_authority_reconciliation_v1.py` against the corrected V2 bundle with `--run-mutations`: **PASS**, `mutation_count: 18`, `rejected_count: 18`. I instrumented the harness to capture each rejection *reason* — all 18 fail at the intended control point, not incidentally. `M05`/`M06` (outer SHA recomputed and propagated) and `M15`/`M16` (exact stale V6 SHAs) all die at `SHA does not equal measured Git bytes` / `measurement entry SHA`.

I then ran seven of my own **on-disk** mutations in a separate scratch worktree, each closing a fixed point over every outer SHA (measurement → scientific → inert → manifest → correction) so no document was internally inconsistent:

| case | result |
|---|---|
| X01 parser binding → stale | FAIL `parser: SHA does not equal measured Git bytes` |
| X02 coordinator binding → stale | FAIL `coordinator: SHA…` |
| X03 measurement head rebound consistently | FAIL `Git measurement tree` |
| X04 tree rebound consistently | FAIL `Git measurement tree` |
| X05 stale parser+coordinator everywhere, fully coordinated | FAIL `measurement entry SHA: …event_v6.py` |
| X06 real parser bytes substituted in working tree + all docs rebound | FAIL `measurement entry SHA: …authorization_v6.py` |

**A valid outer scientific-access SHA cannot excuse stale internal parser/coordinator bindings** — confirmed independently. Exact Git bytes at the measurement head control.

## 12–14. Inert fixture, manifest, rehearsal

The corrected inert fixture refuses live authority at two independent layers: `state`/`live` gate (`authorized document required`) and the INERT id-grammar gate (`$.authorization_id inert/test identity`) when I forced `state=AUTHORIZED, live=true`.

Rehearsal reran in metadata-only mode: **PASS**, `checkpoint_shard_opens: 0`, `checkpoint_payload_reads: 0`, `numerical_operations: 0`, `state_created: false`, `event_04_authorization_created/executed/operator_go: false`, `candidate_installed_at_canonical_production_path: false`, and `parser_measured == parser_contract`, `coordinator_measured == coordinator_contract`. Against the banked rehearsal, the only diffs are `implementation_head` (current HEAD), the memory observation, and the four hashes derived from them — every safety and binding field is identical.

## 15–18. CI, safety, and P1

Banked census verified, and I confirmed both runs live via `gh`:

- FULL_NATIVE `32726480096` @ `d5d4c412` — success; `Apple MLX small-fixture validation` and `Apple Silicon workspace baseline` both **success** ⇒ required native skips **0**. Job map matches the census exactly. Run log confirms `"mutation_count": 18`, `"rejected_count": 18`, `SCIENTIFIC_ACCESS_INTERNAL_BINDINGS_RECONCILED`, and zero shard opens/payload reads.
- EVIDENCE_ONLY `32727677562` @ `c442e54e` — success; both native jobs **skipped** ⇒ native MLX jobs launched **0**.

No Event-04 operator approval exists (only events 02 and 03); no live authorization artifact; only the inert operator-go *template* with `operator_go: false`, `event_04_authorization_permitted: false`, `p1_attempt_2_permitted: false`. Only P1 attempt-01 artifacts exist. `historical_master_ledger: 175` consistent across census, manifest, scientific access, and inert fixture. Change scope `5eb7b1b2..a71d23f2` is confined to reconciliation artifacts plus `macos.yml`.

---

## Findings

**BLOCKING: 0 · NON_BLOCKING_REQUIRED: 0 · DEFENSE_IN_DEPTH: 6**

**D1 — Runtime authorization parser is not rebound to the reconciled authorities.** `f017_corrected_oracle_authorization_v6.py` still hardcodes `implementation_measurement_manifest_path` = measurement **V3** and `scientific_access_contract_path` = the **stale** V6 contract. I exercised its `validate_implementation_measurement` directly: it rejects **V4** (`implementation measurement manifest census` — V4 carries schema `…measurement/4.0.0` plus `parent_measurement_manifest_*`) and now also rejects **V3** (`byte substitution: .github/workflows/macos.yml`, since `418a4121` remeasured that file). `lifecycle-semantic-model-v6.required_entries` is likewise still the 61-entry V3 set. A PRODUCTION Event-04 mint is therefore impossible at this head — fail-closed, which is why this is not blocking — but the reconciliation does not reach the runtime path, and the correction declaration discloses only `implementation_runtime_bytes_changed: false`. A runtime rebind plus re-measurement and re-review is required before any mint. (The analogous inert-fixture/parser production-path divergence predates this work — original inert V6 already named measurement v1 against the parser's v3.)

**D2 — The reconciliation validator Git-byte-anchors 17 of 20 scientific bindings.** `path_timing`, `serialization`, and `lifecycle_manifest` are outside both `MEASURED_BINDINGS` and measurement V4, so they are only checked against working-tree file SHAs. I drifted all three on disk with a fully closed outer-SHA fixed point and the validator returned **PASS / `SCIENTIFIC_ACCESS_INTERNAL_BINDINGS_RECONCILED`**. Pipeline coverage holds: `validate_f017_lifecycle_semantic_authority_v6.py` (which runs immediately before it in CI) fails with `byte-anchored lifecycle authority drift: ['paths','serialization']` and `lifecycle authority manifest exact-byte binding drift`. Worth closing, since the manifest names this validator as `pre_mint_required_validator`.

**D3 — Authority manifest V2 is not complete against its own scientific binding census.** Four measured load-bearing implementation authorities — `primary_numerical`, `secondary_numerical`, `primary_target_source`, `secondary_target_source` — appear in the V2 contract's bindings and in measurement V4 but not in `f017-event04-load-bearing-authority-manifest-v2.json`. No verification hole (both other authorities cover them), but the manifest under-states its scope.

**D4 — CI census banks no EVIDENCE_ONLY record.** `f017-event04-authority-reconciliation-ci-census-v1.json` contains only `full_native`. Run `32727677562` appears solely in review prose, so "evidence-only native jobs are zero" is not verifiable from committed bytes — I had to confirm it off-repo. Prior declarations banked this as `ci.final_review_banking` with `native_mlx_jobs_launched: 0`; that pattern was dropped here (the run postdates the census commit, so an appended census entry is the fix).

**D5 — Two verifiable inaccuracies in the banked Gemini cycle-01 acceptance.** It states the EVIDENCE_ONLY run was "verified within the banked CI census evidence" (the census has no evidence-only section), and cites "Handshake bindings verified (`655212eb…`)" — that digest appears nowhere in the repository at any head; the banked `installed_handshake_sha256` is `7c939e35…`. Its substantive claims that I could check independently (parser/coordinator digests, V3 macos.yml drift, append-only correction treatment, 18/18 mutations) are correct, and the normalized `0/0` counts match its own text — but these two unsupported assertions reduce the weight that acceptance should carry as independent corroboration.

**D6 — Stale defaults.** `DEFAULT_SCIENTIFIC`, `DEFAULT_INERT`, `DEFAULT_MANIFEST`, `DEFAULT_MEASUREMENT` still name the superseded V1 bundle and measurement V3. CI passes V2 paths explicitly, and a no-argument invocation fails closed (`measured working-tree drift: .github/workflows/macos.yml`) rather than silently validating the superseded bundle — hygiene only.

---

## Verdict

`ACCEPT_FOR_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_04_AUTHORIZATION_PREPARATION`