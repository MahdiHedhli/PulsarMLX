# ACCEPT_FOR_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_04_AUTHORIZATION_PREPARATION

**BLOCKING: 0 · NON_BLOCKING_REQUIRED: 0 · DEFENSE_IN_DEPTH: 3**

Repository unmodified (`git status` clean before and after). No Event-04 authority minted, no real oracle run, no P1 attempt 2, no original checkpoint shard touched. All mutation testing ran in a `git archive` extraction proven byte-identical to the reviewed worktree, with every mutated file restored byte-identically.

## Both Cycle-01 findings reproduced, then broken as repairs

**`C1-B-1`** reproduced exactly at `008b41cc`: the pin was measurement **v1** attesting `10ebfcb1`, with **6 of 61** entries stale against that tree — including `validate_f017_corrected_oracle_access_v6.py` *without* `validate_operator_approval`. Cycle 01's count is exact.

Manifest v3's SHA-256 matches the request, attests `12d2b916`, and its `git_tree_sha` equals that commit's tree. I **reconstructed the entire manifest byte-for-byte from Git objects at the implementation head** — it is a truthful, reproducible measurement. All 61 entries match current bytes under both SHA-256 and Git-blob identity; the model's required-entry census is the identical 61-path set.

**38 attacks on the validator + 13 on the path pin, all as required.** Stale v1/v2 (even with the head declared truthfully), arbitrary head, missing/changed/duplicate entries, forged blobs, `..`/absolute/symlink escape, key-census violations, non-canonical bytes, duplicate JSON keys, and a self-consistent source forgery vs the committed manifest — all rejected. Critically, **a future production authority binding v3 is accepted**, v1/v2 are refused, and the check can't be skipped by dropping or renaming the interface pair.

**`C1-D-1`** — `require_active` is now unconditional and second in `execute_synthetic`. The committed regression is only a source-text assertion, so I proved it behaviorally: with the synthetic generation disabled, **0 mkdir calls, 0 checkpoint opens, 0 roots created**; control run completes.

## CI and whole-domain re-audit

`32689603653` @ `12d2b916`: FULL_NATIVE success, **both** native jobs success (not skipped), required skips 0. `32690346149` @ `0c09e8ec`: EVIDENCE_ONLY success, native jobs 0. Rehearsal v5 bound to the new head with state created false, opens 0, reads 0, numerical ops 0, no Event-04 authority.

Every Cycle-01 number reproduced: 187 mutations byte-identical, 10 tombstones, 24 equivalence cases, 16 oracle mutations, unchanged formulas/thresholds, 163 identities / 26 states / 36 transitions / 3918 cells / 56 mutations rejected, independent validator agreeing without importing the generator, **33/33 tests**, ledger 175 delta 0, Event 02/03 untouched, P1 attempt 2 `PASS_BLOCKED`, zero original checkpoint access.

## Three new defense-in-depth findings

1. **The manifest is anchored to disk, never to Git.** `git_blob_sha` is recomputed from the bytes already SHA-256'd, and `git_tree_sha` is regex-checked but never used — so a consistent rewrite of a measured source plus v3 validates. Not live (v3 reproduces from Git), and anyone with that write access can delete the check.

2. **Three shared quantization tables sit outside every live authority.** `iq2_xxs_tables.py`, `iq3_xxs_tables.py`, `iq_extra_tables.py` are the exact intersection of both "independent" decode closures, are in neither the 61-entry census nor any v6/v3 binding, and — because the synthetic fixtures are **F32 only** — I emptied the IQ2_XXS grid entirely with measurement validation still ACCEPTED and dual-oracle qualification still PASS. The Event-04 target is IQ2_XXS, so they first execute during the real run. Capped by CI's Rust cross-language exact-bits differential, which passed at the implementation head.

3. **The rehearsal can't exercise the new gate.** It runs at `PRODUCTION_SHAPED_REHEARSAL` scope, and CI invokes it with no `--measurement-manifest`, so it uses a stub. Rehearsal v5 records no manifest identity — "uses manifest v3" is not established by committed evidence. Fail-closed; my synthesized production-document test supplies the missing positive proof.

Full record, including the attack tables and suggested closes, is in `/Users/mhedhli/.claude/plans/f017-event-04-readiness-vectorized-cat.md`.
