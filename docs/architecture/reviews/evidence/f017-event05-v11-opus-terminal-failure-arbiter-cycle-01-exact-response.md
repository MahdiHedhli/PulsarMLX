I have completed the reconstruction without modifying any file or touching checkpoint shards. Findings below.

# F017 Event 05 V11 — Terminal-Failure ARBITER Verdict

**Head reviewed:** `176688006b8abb6fe77979fa66e272809e60b1c9` (detached, clean, read-only worktree `/private/tmp/f017-event05-opus-failure1`)
**Method:** committed bytes only; no execution rerun; no shard access.

## Global verdict

| | |
|---|---|
| **Global execution-evidence verdict** | **`REJECT`** |
| **Terminal-failure evidence truthful and complete** | **Yes — affirmatively corroborated** |
| Blocking findings | **0** |
| Non-blocking-required findings | **0** |
| Unresolved | **0** |
| ACCEPT / REJECT / UNRESOLVED | **19 / 11 / 0** (30 claims) |

`REJECT` is mandatory and independently correct: `E-IDENTITY-001` failed at the identity stage and no oracle — primary or secondary — ever ran. The evidence packet is honest about exactly that.

## Reconstruction results

**SHA closure — exact.** All 13 manifest-v3 bindings recompute to the declared digests. `binding_count` 13 = 13 files actually present in the package (no unbound artifact, no orphan binding). The manifest's own SHA recomputes to `763537f8…`, matching `terminal_authority_manifest_sha256` in CI v3; the failure declaration recomputes to `4fc30dd9…`, matching `terminal_failure_declaration_sha256`. Repo-banked copies of the approval, candidate, and readiness declaration hash identically to the package copies.

**Candidate/install — byte-identical.** `cmp` proves `candidate.json` and `authorization.json` are the same bytes; `candidate_sha256` = `installed_sha256` = `2876a557…`. No mismatch to exploit.

**Transition journal — chain verified.** Under the line+`\n` convention every `previous_record_sha256` recomputes exactly (seq 0→3), and `journal_last_record_sha256` (`3316d9b7…`) in both the capsule and package-terminal matches record 3. Each record's `artifact_sha256` matches the corresponding artifact file. The journal terminates at `CHECKPOINT_IDENTITY_START`, seq 3. Nothing was appended after.

**Accounting — derived, not fabricated.** `accounting_lower_bound()` observes durable-start artifacts and cross-checks the journal, taking `max()` and treating unreadable evidence as *not* evidence of absence. It is a conservative lower bound that can only over-report execution. `primary=0`/`secondary=0` therefore rest on two independent absences (no artifact, no journal record). `package=1`, `authorization=0`, `historical` 175→175 (delta 0).

**Root binding — no substitution.** E4 pre-declared `terminal_fallback` inode `324390078` and `package_evidence_root_absent: true`; E5's runtime `accounting-root-authority` records that same fallback inode and a freshly created primary root (`324390490`). `evidence_root.mkdir(exist_ok=False)` succeeding proves no pre-existing root. The capsule records `fallback_used_as_accounting_source: false`, so accounting came from the real journal in the primary root.

**The failure — exact, and structurally forced.** Measured producer `f017_checkpoint_identity_producer_v10.py` hashes to `d33fd067…` as declared. Its measured text admits only two scopes:

- `f017_checkpoint_identity_producer_v10.py:9` — `SYNTHETIC_QUALIFICATION`
- `f017_checkpoint_identity_producer_v10.py:11` — `PRODUCTION_EVENT_04`
- `f017_checkpoint_identity_producer_v10.py:14` — `else: raise ValueError("checkpoint identity producer authority")`

The V11 coordinator hard-requires the opposite scope at `execute_f017_corrected_oracle_event_v11.py:51` (`candidate["scope"] != "PRODUCTION_EVENT_05" → raise`), and the candidate carries `scope: PRODUCTION_EVENT_05`. The two are irreconcilable, exactly as claimed. `execute_f017_corrected_oracle_event_v11.py:90` sets `last = "CHECKPOINT_IDENTITY_START"`; line 101 calls `produce(...)`, which raises immediately.

**Zero shard access — proven, not merely asserted.** The only `os.open` of a shard in the measured code lives inside `acquire_synthetic_leases` (`f017_descriptor_lease_manager_v10.py:248`) and `acquire_production_leases` (line 311), and both are reachable only from the two admitted branches of `produce()`. Neither is entered. Defense in depth: `acquire_production_leases:288` would itself reject `PRODUCTION_EVENT_05`. Corroborating absence — the coordinator's `identity_progress` callback banks `checkpoint-access-event-N.json` and `checkpoint-shard-receipt-N.json` on any access; **no such file exists anywhere in committed bytes**, nor any `checkpoint-access-journal-terminal`, `descriptor-lease-manifest`, `primary-result`, `secondary-result`, or `comparison-*` artifact.

**No descriptor leakage.** `leases` stays `None`, so `inherited_fds()` is never called and no descriptor is ever created. `_terminalize` (`execute_f017_corrected_oracle_event_v10.py:135`) defaults release to `NOT_APPLICABLE`/0 when `leases is None` — matching the capsule exactly.

**Not a staged failure.** `modeled = None` because `ValueError` is not a `ModeledTransitionFailure`, yielding `generic_fallback: true` and `outcome_id: null`. A fabricated or injected fault would carry an `outcome_id`. This was a genuine unmodeled failure.

**No retry/resume authority.** `attempts: 1, retries: 0, resume: false` in both candidate and package-claim; the coordinator has a single non-looping `try` and no fault selector. Repo-wide census finds exactly one authorization ID and one package-attempt ID (`…-05-V11-2`); no `-1`/`-3` variant exists.

**CI — no mismatch.** CI v3 head `c116442d` and tree `a756aa0a…` match `git rev-parse c116442d^{tree}` exactly. That commit touches only `docs/architecture/reviews/evidence/`, and `classify_ci_change.py` is fail-closed (any non-evidence path, and even evidence *mixed with* docs, forces `FULL_NATIVE`). `EVIDENCE_ONLY` is the correct classification; `native_jobs_launched: 0` with `native_mlx`/`workspace_baseline` skipped is consistent, and the packet nowhere treats this CI as a substitute for oracle execution.

**No historical-ledger drift.** 175 appears uniformly across all 227 occurrences repo-wide; before == after.

**No hidden P1 authority.** All `p1_attempt_2_executed`, `live_p1_attempt_2_authorization_created`, and `ready_to_prepare_p1_attempt_2_authorization` flags are `false` everywhere; no attempt-2 authorization artifact exists.

**Ledger integrity.** Claim closure is strictly monotone and append-only across v2→v8 (4→6→9→12→14→17→19), each delta matching a node receipt (E0:4, E1:2, E2:3, E3:3, E4:2, E5:3, E9:2). **No invalidated or rejected claim was ever converted to supported.** Memory gates re-derive exactly: `(free+inactive+speculative+purgeable) × page_size` equals the declared `available_bytes` for both mint and package observations, both above the 16 GiB threshold.

## Per-claim verdicts (all 30)

| Claim | Verdict | Basis |
|---|---|---|
| E-REF-001 | ACCEPT | Authority bindings recompute exactly |
| E-REF-002 | ACCEPT | Single-ID census; `mkdir(exist_ok=False)` success |
| E-REF-003 | ACCEPT | Readiness/authorizer SHAs bind and match |
| E-TEMPLATE-001 | ACCEPT | Zero live-path template reads; no contrary artifact |
| E-APPROVAL-001 | ACCEPT | Fresh GO, V11/Event-05 IDs, 48 h window, SHA-bound |
| E-ACTIVATION-001 | ACCEPT | attempts 1 / retries 0 / resume false; no retry path in code |
| E-PREFLIGHT-001 | ACCEPT | Load-bearing SHAs match accepted bytes |
| E-PREFLIGHT-002 | ACCEPT | Memory gate re-derives; metadata census consistent |
| E-PREFLIGHT-003 | ACCEPT | Zero pre-mint access; structurally corroborated |
| E-CANDIDATE-001 | ACCEPT | Scope accepted by measured coordinator (line 51) |
| E-CANDIDATE-002 | ACCEPT | `live: false`, zero IDs consumed, zero side effects |
| E-CANDIDATE-003 | ACCEPT | Candidate re-derived before install; SHA matches repo copy |
| E-INSTALL-001 | ACCEPT | Byte-identical candidate ≡ installed authority |
| E-ROOT-001 | ACCEPT | E4↔E5 inode cross-binding; fallback not an accounting source |
| E-HANDSHAKE-001 | ACCEPT | Journal seq 0, precedes package state; opens/reads 0 |
| E-PACKAGE-001 | ACCEPT | Exactly one durable start, delta 1, one attempt ID |
| E-ACCOUNTING-001 | ACCEPT | Lower-bound derivation + verified journal chain |
| **E-IDENTITY-001** | **REJECT** | Producer rejects `PRODUCTION_EVENT_05` before any shard open |
| E-LEASE-001 | REJECT | Zero leases acquired — claim affirmatively false |
| E-PRIMARY-001 | REJECT | Primary never executed |
| E-PRIMARY-002 | REJECT | No shard consumed |
| E-PRIMARY-003 | REJECT | No primary output banked |
| E-SECONDARY-001 | REJECT | Secondary never executed |
| E-SECONDARY-002 | REJECT | No shard consumed |
| E-SECONDARY-003 | REJECT | No secondary output banked |
| E-COMPARE-001 | REJECT | No comparison performed |
| E-RELEASE-001 | REJECT | Release `NOT_APPLICABLE`; nothing acquired to release |
| E-TERMINAL-001 | REJECT | Failure terminal only; no result-closure chain |
| E-EVIDENCE-001 | ACCEPT | 13/13 bindings, chain intact, artifact set matches code path |
| E-CI-001 | ACCEPT | Head/tree exact; EVIDENCE_ONLY correct; zero native jobs |

The 10 invalidated claims are marked `REJECT` rather than `UNRESOLVED` deliberately: their evidence is not merely missing, it is affirmatively absent by structural proof of the unreached code path. None was converted to ACCEPT.

## Non-blocking observations (no finding, no action required)

1. `historical_before`/`historical_after` = 175 is a literal constant in `accounting_lower_bound()` (`f017_accounting_root_continuity_v1.py:426-427`), not a runtime measurement. Only the delta (0) is load-bearing here, and no drift exists repo-wide.
2. `stdout_sha256` of raw `vm_stat` output is not reconstructible from committed bytes; the committed canonical projection re-derives exactly, which is the bound quantity.
3. `package-ledger-entry.json` is manifest-bound but absent from the journal — correct by construction, banked with `transition_id=None` at `execute_f017_corrected_oracle_event_v11.py:85-86`.
4. Device/inode identities cannot be re-observed from committed bytes; anti-substitution rests on the E4-pre-declaration ↔ E5-runtime cross-binding, which is consistent.

No conditional acceptance was issued, no execution was rerun, no file was modified, and no checkpoint shard was accessed.
