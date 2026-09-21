## Verdict

`ACCEPT_FOR_CORRECTED_FULL_CHECKPOINT_ORACLE_EXECUTION_AUTHORIZATION_PREPARATION`

No `BLOCKING` and no `NON_BLOCKING_REQUIRED` findings. Six `DEFENSE_IN_DEPTH` findings below.

Review worktree `/private/tmp/f017-instantiability-review.VcoeSP` at `a7a7b82`, clean and unmodified throughout (`git status --porcelain -uall` → 0 lines). All execution was done in `/tmp/f017-exec-c1`, extracted via `git archive a7a7b82 | tar -x` and proven byte-identical to the review worktree (`diff -r --brief` → only `.git`). No authorization minted, no Event 03 state, no original-checkpoint access, no P1 attempt 2.

---

## 1. Event 02 reconstruction — CONFIRMED

Mismatch is exact and one-directional: `f017_corrected_oracle_primary.py:24` and `f017_corrected_oracle_secondary.py:24` both pin `AUTH_SCHEMA = …access-authorization/1.0.0`; the banked live authorization (`…event-02-live-authorization-v1.json`, sha `553a4f31…`) carries `/2.0.0`. The v2 authorizer emitted v2; neither consumer could ever accept it.

Identity-read order reconstructed from the 30 banked identity events: contiguous sequences 0–29, monotonic timestamps, 6 shards × {OPEN_ATTEMPT, OPEN_RESULT, HASH_ATTEMPT, HASH_RESULT, CLOSE}, all PASS, single owner pid 97871, window `…185017334000 → …318078703000`, strictly inside package start (`…185016835000`) and terminal (`…318154227000`). Identity **preceded** the primary invocation — the v2 order the successor inverts.

Zero numerical consumer starts: `primary.numerical_execution_started=false`, `access_event_count=0`, `layers_completed=0`, `result_artifact=null`; `secondary.process_invoked=false`. Postmortem confirms `graph_mmaps=0`, `logical_tensors_resolved=0`, `logical_tensors_read=0`, no consumer receipts.

Receipt/terminal binding verified by hash: receipt `63cf8bf4…` → terminal `11a8cde6…`, ledger entry `f4877338…`, claim = durable-start = `ffd696e3…`. `retry_permitted=false`, `resume_permitted=false`; disposition consumed and non-retryable (`rerun_under_current_authorization: PROHIBITED`).

Immutability: every Event 02 artifact was written exactly once (`git log --follow` → single commit each: `f69b7e36` for summary/receipt/terminal, `4e53703b` for the live authorization) and all four re-hash to their manifest/postmortem values. Files are mode `0444` in dirs `0555`.

## 2. Schema v3 and both successor consumers — CONFIRMED

Exact key census cross-checked three ways — parser code vs. interface contract vs. committed inert fixture: top-level 43/43, consumer grant 11/11, event accounting 5/5, shard 4/4, all set-equal; fixture key sets identical; the fixture is exactly its canonical `sort_keys/(",",":")+\n` serialization.

Superseded-schema rejection executed directly: `capability` with the committed v1 **and** v2 scientific-access contracts → `ValueError: v3 scientific contract required` (both consumers); the v3 inert fixture against the v2 contract → `ValueError: authorization/contract schema`; `--require-live` on the inert fixture → `ValueError: live authority required`.

**Instantiability itself proven on committed bytes**: the committed production-scope inert authorization v3 validates `PASS` against the committed v3 contract through the *same* parser both real consumers import. Both consumers and the authorizer take `SCHEMA` from `f017_corrected_oracle_authorization_v3.py:20`; no consumer defines an independent schema constant. The Event 02 failure mode is now structurally unreachable.

Producer/decoder/catalog/contract/context/root/lifecycle/ledger bindings all attacked (see §3) and all rejected.

## 3. Identity and binding attacks — CONFIRMED

I ran a 51-case independent mutation matrix (distinct from the vendor's 25). All rejected except four, of which one was a control (a benign ID that merely *resembles* a marker — correctly accepted, proving the check isn't over-broad) and three are the `DEFENSE_IN_DEPTH` items in §Findings.

Rejected included: `SYNTHETIC`/`TEST` markers in live authorization **and** consumer event IDs; lowercase IDs; consumer order swap and triple; scope confusion; state/live desync; accounting deltas (mint→1, primary→2, secondary→0, package→2, unstarted→1); zeroed nonce; equal/outside/mismatched consumer roots; package state≠output; duplicate/5-count/extra-key/bad-role/path-traversal/zero-size shards; grant extra & missing keys; absolute producer path; attempts=2, consumer attempts=2, consumer resume=true; short impl head; branch mismatch; prompt-token and top_n drift; interface/coordinator/numerical-contract/qualification/ledger SHA drift; uppercase hex; zero operator-approval and zero preflight hash when live; zero memory bytes when live; `p1_authority: ALLOWED`; decoder-path swap; producer-path swap.

Live replay attacks, all fail-closed with no residue:
- rerun coordinator, same package root → `unused root required`
- rerun with a fresh handshake output → same
- handshake-only replay post-start → same
- second `two_phase_install` to the same output → `unused authorization/evidence outputs required`
- attacker pre-creates the package root, then runs `target` directly → `checkpoint identity evidence required`; with forged identity evidence → `checkpoint identity evidence mismatch`; and the pre-created root then permanently burns the authorization for the coordinator (`unused root required`) — denial, never silent execution.

Fixture-ID promotion is blocked: the mint takes IDs from the operator approval and re-validates the candidate with `live=True`, where `FORBIDDEN_LIVE_ID_PARTS = (INERT, FIXTURE, TEST, SYNTHETIC)` applies.

## 4. Shared parser — CONFIRMED strictly non-numerical

`f017_corrected_oracle_authorization_v3.py` imports only `hashlib, json, os, re, stat, dataclasses, pathlib, typing`. No numpy, no mlx, no tensor reader, no graph, no checkpoint payload path. Role validation is *not* weakened by sharing: `_grant` pins `role` per block, `validate_role` additionally binds the **executing script's resolved path and SHA** to the grant's `producer_path`/`producer_sha256` and re-checks the contract binding — so a role swap fails at three independent points. Numerical independence is intact: `f017_corrected_oracle_primary.py` (binary64, stdlib only) and `f017_corrected_oracle_secondary.py` (numpy + `mlx.core`) share no module, and both remain byte-identical to their manifest hashes.

## 5. Capability and validation-only modes — CONFIRMED zero, syscall-audited

I did not trust the reports' hardcoded zeros. I ran all four modes under an independent CPython audit-hook harness living outside the reviewed tree, recording `open`, `mmap.__new__`, `os.mkdir/rename/remove/rmdir/symlink/link/truncate/chmod`, `subprocess.Popen`, `os.exec*`.

| run | audited events | checkpoint touches | mmaps | subprocesses | files created |
|---|---|---|---|---|---|
| primary capability | 48 | **0** | **0** | **0** | 1 (the requested report) |
| primary validate-live | 55 | **0** | **0** | **0** | 1 |
| secondary capability | 137 | **0** | **0** | **0** | 1 |
| secondary validate-live | 144 | **0** | **0** | **0** | 1 |

The only `O_CREAT` open in each run is the requested output, `O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW` mode `0400`. A full before/after filesystem snapshot shows exactly four added files and nothing else — no package state, no consumer root, no authorization. Both generated capability reports hash **byte-exactly** to the committed capability contracts (`f90a85ac…`, `7b778766…`).

## 6. Two-phase mint byte flow — CONFIRMED, all three levers load-bearing

- **Identical candidate**: I patched the secondary to validate a *different but individually valid* candidate → `ValueError: consumer candidate SHA mismatch`, no install, no state. The equality check is genuinely load-bearing, not decorative.
- **Both consumers required**: primary rejection (vendor test, re-run) and secondary rejection (my run) each abort before `_bank`. Call order observed as exactly `[primary_v3.py, secondary_v3.py]`.
- **Byte mutation after install**: post-`_bank` corruption → detected, file `os.rename`d to `failed-installed-authorization.invalid`, `installed.exists()=False`, evidence `result=FAIL`, `candidate_installed_byte_identity=false`, `quarantined_install_sha256` recorded, `candidate.json` unlinked, package root never created.

Clean path: candidate → both PASS reports → `_bank` → readback SHA + full byte compare → strict re-validation of the *installed file*. Installed authorization SHA `aeaff94d…` = candidate SHA = handshake `authorization_sha256`.

## 7. Coordinator ordering and injected failure — CONFIRMED

Audit-hook event indices from my own `execute-synthetic` run:

```
84  handshake.json created (O_CREAT|O_EXCL)
89  mkdir package/
101 mkdir package/checkpoint-identity-events/
107 first open of checkpoint/qualification-00.gguf
```

Subprocess order: `cap:primary → validate:primary → cap:secondary → validate:secondary → target:primary → target:secondary`. All four reports precede the banked handshake; package state and start precede checkpoint identity. `checkpoint_shard_opens_before_handshake = 0` and `checkpoint_identity_hash_reads_before_handshake = 0` independently corroborated — zero events of any kind touch the checkpoint before index 107.

Injected failures: handshake exception → `verify_checkpoint_identity` never called, package root absent; capability SHA mismatch → raises before state and before identity, handshake file absent; identity failure (corrupted shard) → rc 2, `primary_event_delta=0`, `secondary_event_delta=0`, both `started=false`.

## 8. Synthetic file-backed chain — CONFIRMED

Executed end-to-end through both real target readers and the real successor coordinator, deliberately under a **contaminated** environment (`DYLD_LIBRARY_PATH`, `MLX_PREFIX`, `MLX_C_PREFIX`, `RUSTFLAGS` all set to bogus native paths). Exit 0.

Six synthetic shards, all `GRAPH_PAYLOAD`, all opened by both consumers; 34 tensors resolved by each, 0 unexpected accesses, 0 fallback attempts, 0 alternate-root attempts. Geometry: 2 layers with `dense_layers=1` → layer 0 dense (`selected_expert_ids=[]`, no shared/routed output), layer 1 MoE with `experts=4`, `top_k=2` → `selected_expert_ids=[2,0]` identical across both oracles, plus `shared_output_sha256`, `routed_aggregate_sha256`, `router_normalized_sha256`, `routing_weight_f64_bits`. Final projection present (`final_norm_sha256`, `full_logits` len 9, `top` len 9). Both selected token 8, matching the independent seed-18102/2-layer expectation banked in the unchanged checkpoint-free qualification.

Complete receipt/terminal chain verified by recomputation — 25/25 hash bindings hold (package claim=start, handshake, identity, census, comparison, ledger, terminal; both consumer start/result/receipt/terminal, both `classification=COMPLETE`, `event_delta=1`, `retry_permitted=false`, `resume_permitted=false`).

Original checkpoint unreachable: zero events matching `Models/PulsarMLX`, `GLM-5.2`, or `glm52/raw`; `execute-synthetic` additionally refuses any root not under `ROOT/.pulsarmlx-local`.

Secondary runtime isolation observed directly at the `subprocess.Popen` boundary: the secondary target env contains **none** of the four contaminating variables and carries `F017_ORACLE_SECONDARY_RUNTIME`; the primary target (pure binary64) inherits them harmlessly.

## 9. Fresh-process reruns — CONFIRMED

Independent 10 primary + 10 secondary validation-only processes: **1 distinct report hash each** (byte-exact), zero package state. Independent 10 complete package processes via CLI: **1 distinct outcome signature** —

```
rc=0, EXACT_EXPECTED_TOKEN_STABLE, pkg_delta=1, primary=1, secondary=1,
both started, opens_before_handshake=0, identity_events=30,
historical_master 175→175 delta 0, token 8 = 8, retry=false, resume=false
```

The committed suite also re-ran independently: **14 passed, 28 subtests passed in 11.45s** against test authority `164fd318…` — exactly the qualification's claimed 14/28/≈11.22s. Wrong schema, keys/types, role swaps, SHAs, roots, IDs, candidate/install mismatch, capability mismatch, skipped validation, hash-before-handshake, primary failure and unstarted-secondary accounting are each covered by a passing test plus my own independent attack.

## 10. Event accounting and Event 02 disposition — CONFIRMED

`accounting-v3` states `reservation_is_not_execution: true`, `event_counts_derived_from_durable_start_receipts: true`. Mint delta 0; package/primary/secondary each advance only at their own durable start; unstarted consumer contributes 0 — enforced in the parser (`event accounting semantics`) and demonstrated live (identity failure → 0/0; primary pre-completion failure → primary 1, secondary 0, `secondary.started=false`).

The v2 delta of 2 is dispositioned as `PACKAGE_RESERVATION_OF_TWO_AUTHORIZED_CONSUMER_SLOTS` with `v2_value_does_not_prove_consumer_start: true`, `primary_consumer_durable_start: false`, `secondary_consumer_durable_start: false`, `historical_value_reinterpreted: false`, `historical_artifact_rewritten: false`. Cross-checked against the postmortem (`retrospective_consumer_receipts_created/​numerical_event_created/​accounting_changed` all false) and against the untouched Event 02 artifacts. **No rewriting into a numerical-event claim.**

## 11. Unchanged-authority hashes — CONFIRMED, zero drift

All 12 successor and all 5 unchanged-numerical manifest bindings re-hash correctly at `a7a7b82` (numerical methodology `7c22507f…`, primary oracle `2041c033…`, secondary oracle `8c4f9fde…`, primary decoder `60a4b4e7…`, checkpoint-free qualification `b9c2f7dc…`).

Context is byte-identical v2→v3: `prompt_token 9703, position 0, kv_state EMPTY, mask ONE_VISIBLE_KEY_CAUSAL, sampling NONE_GREEDY_ARGMAX, top_n 32`. Production shard identity triples (filename/sha/size) identical v2→v3; v3 only *adds* the `access_role` discriminator. Checkpoint set SHA `d7d1e6a8…` unchanged.

Frozen thresholds **re-derived from scratch** using the unchanged numerical contract's formulas over the unchanged seed-18101–18112 corpus:

```
65536 × max(max_abs)        = 0.0065169706285814755  ✓
65536 × max(rmse)           = 0.003463567697419031   ✓
1 − 65536 × max(cos_dist)   = 0.9999999985448085     ✓
```

No plumbing drift to promote.

## 12. CI — CONFIRMED by direct inspection

Run `32624610787`: `headSha a7a7b82f…`, event `push`, conclusion `success`, `2026-08-23T07:04:49Z → 07:14:16Z`. Aggregate job env: `MODE: FULL_NATIVE`, `BASELINE_RESULT: success`, `NATIVE_RESULT: success`, `selected_mode=FULL_NATIVE`. The `Evidence/Documentation/Guard` jobs are `skipped` by mode routing, not by native gating.

I downloaded the native job log; it hashes to `09cda083…` — **exactly** the `log.sha256` declared in the review packet, so the declared source is genuine.

Workspace baseline: `rustc 1.97.1 (aarch64-apple-darwin)`, `cargo check`/`cargo test --workspace --exclude f017-native`, success. Pinned MLX: native MLX + `mlx-c 0.6.0` built from source into `$RUNNER_TEMP/pulsar-native-mlx`, `uv sync --frozen --python 3.13.13` asserting `mlx==0.32.0` and `mlx-metal==0.32.0`. `PULSAR_REQUIRE_NATIVE_MLX=1` throughout; the adapter matrix step is explicitly "no skip permitted"; **every** Rust test binary reports `0 ignored` — zero required native qualification skips. `56 passed, 28 subtests passed` for the corrected-oracle pre-access domain, matching the declared counts. All 14 instantiability tests, including `test_secondary_runtime_does_not_inherit_native_rust_mlx_linkage`, ran and passed.

Predecessor `32624054720` (head `66888e2`) reconstructed: `Apple MLX small-fixture validation` failed with

```
ImportError: dlopen(.venv/lib/python3.13/site-packages/mlx/core.cpython-313-darwin.so):
  Symbol not found: __ZN3mlx4core11logical_xorERKNS0_5arrayES3_…
  Expected in: /Users/runner/work/_temp/pulsar-native-mlx/lib/libmlx.dylib
```

— precisely the declared `SECONDARY_PYTHON_MLX_ABI_COLLISION_WITH_INHERITED_NATIVE_RUST_DYLD_LIBRARY_PATH`, in `test_full_successor_coordinator_runs_ten_fresh_synthetic_packages`, with `Ran 462 tests / FAILED (failures=1)`. Closed by subprocess-env isolation only; the diff `66888e2 → 546e7aa → a7a7b82` touches no numerical source (manifest numerical hashes unchanged, and `a7a7b82` is a pure four-file JSON rebind). The CI genuinely exports the contaminating `DYLD_LIBRARY_PATH` into the very step that runs the suite, so the isolation is load-bearing in the controlling run, not theoretical.

Later review-packet run `32625080456` (head `3390287`, banked after the reviewed head): `MODE: EVIDENCE_ONLY`, success, `NATIVE_RESULT: skipped`, `BASELINE_RESULT: skipped` — **zero native jobs**, as required.

## 13. Safety ledger — CONFIRMED

`event_03_authorization_created=false`, `event_03_executed=false`, `primary_real_oracle_executions=0`, `secondary_real_oracle_executions=0`, `new_original_checkpoint_shard_opens=0`, `new_original_checkpoint_payload_reads=0`, `p1_attempt_2_executed=false`. `~/.local/share/pulsarmlx/f017/` contains no Event 03 or v3 live-authorization state (only the closed Event 02 v2 state and P1 attempt 1). Every `event-03` string in the tree is a negative safety assertion.

Historical master ledger 175 verified at source: the bound `aa98f5cc…` resolves to `f017-real-payload-access-ledger-v2.json` on `origin/feat/017-real-checkpoint-runner@96503db7` (a documented cross-branch authority), which re-hashes exactly and records `cumulative_tensor_payloads: 175`, `authoritative: true`.

---

## Findings

**DEFENSE_IN_DEPTH — 1. Stale `research_unittest_count` in the review-packet CI descriptor.**
`docs/architecture/reviews/evidence/f017-corrected-oracle-instantiability-exact-head-ci-v1.json` claims `research_unittest_count: 462`. The controlling run `32624610787` actually ran **463** (`Ran 463 tests … OK`); 462 is the *predecessor* run `32624054720`'s count, which is 462 precisely because `546e7aa` added the 14th instantiability test. Not gating: this file postdates the reviewed head (commit `3390287`), is not bound by the authority manifest, and the run itself — which outranks the descriptor — is green and directly verified. Correct it before that file is itself promoted to bound authority.

**DEFENSE_IN_DEPTH — 2. `candidate_nonce` and approval/preflight hashes are produced but never re-derived.**
`validate_f017_corrected_oracle_access_v3.py:176` computes `candidate_nonce = sha256(approval_sha ‖ live_auth_id ‖ primary_event_id ‖ secondary_event_id)`, but nothing ever recomputes it. `f017_corrected_oracle_authorization_v3.py:255` only shape-checks it (64 lowercase hex, non-zero); likewise `operator_approval_sha256`/`memory_preflight_sha256` are only checked non-zero at lines 253–254. So at handshake time no component can confirm the authorization corresponds to a real approval or preflight document. Anti-replay rests entirely on `_require_unused_live_identities`, the unused-root checks, and `O_EXCL`. Unchanged from v1/v2 and unexploitable without write access to the authorization file (which already implies control of the producers), but re-deriving the nonce inside `validate_document` would be near-free.

**DEFENSE_IN_DEPTH — 3. Boolean-for-integer laxness on `position` and `historical_master_delta`.**
`f017_corrected_oracle_authorization_v3.py:238,256` use `!=` against `0`, and Python evaluates `False != 0` as `False`, so JSON `false` is accepted for both fields. `attempts`/`retries` — the only two the interface declares `INTEGER_NOT_BOOLEAN` — are correctly hardened via `_plain_int` (`type(value) is not int` rejects `bool`). Numerically inert (`False == 0`) and the committed inert fixture uses real integers, so no live path is affected. Routing both through `_plain_int` would close it.

**DEFENSE_IN_DEPTH — 4. `two_phase_install` does not check the consumer reports' `result`/`schema`.**
`validate_f017_corrected_oracle_access_v3.py:231–234` checks `authorization_sha256` and `consumer_role` only, relying on `check=True` for failure detection. Sound today because `validate_live` writes a report *only* on the success path, so `result` is invariably `"PASS"`. Worth noting as an asymmetry: the coordinator's `handshake()` *does* assert `validation["result"] != "PASS"` (line 149). Mirroring that assertion, plus a `VALIDATION_SCHEMA` check, would make the mint independent of that invariant.

**DEFENSE_IN_DEPTH — 5. Mutation-class naming drift between qualification evidence and the test.**
The qualification lists `SCHEMA_V2_MISMATCH`, `DUPLICATE_CONSUMER_EVENT_ID`, `WRONG_PRIMARY_PRODUCER_SHA`, `UNSTARTED_SECONDARY_DELTA_NONZERO`, `P1_AUTHORITY_ENABLED`; the test emits `SCHEMA_V2`, `SAME_EVENT_ID`, `WRONG_PRIMARY_SHA`, `ACCOUNT_SECONDARY_UNSTARTED`, `P1_AUTHORITY`. Count (25) and semantics map 1:1 — labels only. A future reviewer grepping by class name will get misses.

**DEFENSE_IN_DEPTH — 6. `_require_unused_live_identities` is production-scope-only and scans two roots.**
`validate_f017_corrected_oracle_access_v3.py:122–142` runs only when `scope == "PRODUCTION"` and searches `docs/architecture/reviews/evidence` plus `~/.local/share/pulsarmlx/f017`. Adequate for the declared banking locations, and its bypass in synthetic scope is deliberate (my two synthetic packages deliberately reused `…QUAL-0900` and both minted), but identity reuse recorded anywhere else would go undetected.
