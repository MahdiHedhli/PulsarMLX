## Scope and provenance

Reviewed in a detached read-only worktree at `22b50693`. I verified blob identity between the measurement head and the reviewed bytes: `f017_descriptor_lease_manager_v8.py` = `e17fbf4e`, `execute_f017_corrected_oracle_event_v8.py` = `0f3e4d29`, `.github/workflows/macos.yml` = `1faf63d9` at both `a740687e` and `HEAD`, matching `f017-corrected-oracle-lifecycle-v8-implementation-measurement-v2.json`. Tree `b9fd57f0` confirmed. The three commits after the measurement head are docs/evidence only, so the `FULL_NATIVE` PASS at run `32795502069` covers the implementation I read. I did not execute anything, mint authority, touch checkpoint shards, or run P1.

## Independent reconstruction of C7-N1 / C7-N2

**C7-N1** (mode values below 2³² reaching `stat.S_ISREG` before the portable `mode_t` bound; Darwin `OverflowError`). Repaired in all three descriptor validators, with the bound strictly ordered before `S_ISREG`: `check_f017_transitive_artifact_closure_v8.py:59` before `:63`; `check_f017_descriptor_type_safety_v8.py:56` before `:58`; `f017_descriptor_lease_manager_v8.py:29` before `:31`. I confirmed the probe is load-bearing: `0o1100644 & S_IFMT == S_IFREG`, so `S_ISREG` alone passes it. Both regression values (`65536`, `0o1100644`) are exercised — `V8-RT-MODE-BOUND` / `V8-RT-MODE-PROBE-1100644` at runtime, and against the import-separated checker at `test_f017_lifecycle_causal_design_v8.py:305`.

**C7-N2** (`.get()` and lease-set construction preceding exact type guards; `AttributeError` on `None` entries, `TypeError` on unhashable lease IDs). Repaired: every validator establishes `type(item) is dict` for all entries, then key census, then per-field `type(...) is int`, then `type(lease_id) is str` — before any `set(...)` is built. `LEASE_PATTERN.fullmatch` is short-circuited behind the `str` check, so a `list` lease ID never reaches the regex or a set. `{(device, inode)}` is built only after integer typing. `set(item)` is safe by dict-key invariant.

Critically, the closure checker's `descriptor_lease_manifest` block (`:195–205`) dereferences `item["lease_id"]` on raw payload bytes. I traced that this is reached only after the `payload_rules` loop; the schema contract binds `descriptor_lease_manifest.descriptor_identities` to `DESCRIPTOR_IDENTITY_ARRAY` (the sole occurrence in the schemas file), with the two continuity reports bound by `EQUAL_ARTIFACT_PAYLOAD_FIELD` to it (`generate_f017_lifecycle_v8_design.py:351,353`; independently re-asserted at `validate_f017_lifecycle_causal_design_v8.py:418`). The dereference is therefore type-safe by construction, not by luck.

## Other reconstructed properties

- **Checker separation**: `check_f017_descriptor_type_safety_v8.py` imports only stdlib; the textual forbidden-import assertion holds.
- **Causal creation / transitive SHA closure**: strictly decreasing `creation_rank` on every edge (`:215`) makes cycles unreachable; `self_references`/`future_references` are counted to zero; required-set conformance to DAG outcome applicability and file census are both enforced.
- **48 outcomes**: 48 `"required"` blocks; 47 distinct `failure_terminal_capsule__*` nodes + `COMPLETE_SUCCESS`; single-terminal census enforced per outcome; 5 fresh-process repetitions.
- **Five descriptors at ordinals 2..6, zero reopens**: ordinal census `[2,3,4,5,6]` in all three validators; `path_reopen_count` is `EXACT_CONSTANT 0`; consumers use only `os.fstat`/`os.pread` on inherited fds — no `open()` on a path exists in either target source.
- **Release / identity-only disposition**: ordinal 1's fd is closed in the per-shard `finally`; graph fds are transferred by `fd = -1` before the finally; `package_terminal` follows `release`.
- **Serialization**: `strict_bytes` rejects duplicate keys, `NaN`/`Infinity`, and non-canonical bytes; `bank_exclusive` is `O_EXCL` + fsync(file) + fsync(dir) + readback.
- **Activation without GO**: `event_04_operator_go_present: false`, `live_authority_without_fresh_operator_go: false`, template `purpose: INERT_TEMPLATE_REQUIRING_SEPARATE_HUMAN_GO`. The inert fixture's IDs contain `INERT`, which `_live_id` forbids — it can never parse as a candidate.
- **Historical V6**: validated from `ccf76d95` via `git worktree add --detach`, i.e. exact Git objects, not the current tree.
- **CI**: fail-closed routing; `UNKNOWN_DEFAULT_FULL` demands full native; `EVIDENCE_ONLY`/`DOCS_ONLY` require the native jobs `skipped`; unknown mode exits 1.

## BLOCKING

None.

## NON_BLOCKING_REQUIRED

None.

## DEFENSE_IN_DEPTH

- **DID-01-RELEASE-NOT-IDEMPOTENT** — `LeaseSet.release` (`f017_descriptor_lease_manager_v8.py:62`) closes fds unguarded. A mid-loop `OSError` leaves `closed=False` with fds open; the coordinator's handler (`execute_..._v8.py:79`) then calls `release()` again, double-closing and raising uncaught — no failure capsule banked. `attempted_closures`/`duplicate_closures`/`unknown_leases` are hardcoded, so the runtime cannot express the cleanup anomaly the design explicitly models.
- **DID-02-FAILURE-ACCOUNTING-FIXED** — The handler always returns `deltas(package_started=True, primary_started=False, secondary_started=False)` and classification `DESCRIPTOR_LEASE_ACTIVATION_FAILURE`. A failure after the primary durable start (`:49`) would under-report the primary delta and mislabel the class. Unreachable in every qualified path (all exercised failures are pre-primary), so no banked claim is falsified.
- **DID-03-PRE-TRY-BANKING-UNCAPSULED** — `:27–31` (evidence `mkdir`, handshake, package claim, durable start, ledger entry) run outside the `try`. A failure there leaves a durable package start with no terminal.
- **DID-04-STALE-AUTHORIZER-DOCSTRING** — `install_rehearsal_candidate`'s docstring states the parser requires active generation `NONE`; since `8aac94a1` it requires `V8`. No enforced guard is weakened (`live=False`, `synthetic_only=True`, `state=REHEARSAL_CANDIDATE` are intact and sufficient), but this misstates the mechanism inside the manifest-bound `authorizer`. Worth correcting in the commit that carries the GO packet, since a human reads this text.
- **DID-05-SYNTHETIC-GATE-IS-DECLARATIVE** — `acquire_synthetic_leases` gates on candidate-declared `synthetic_only`/`live`, not on the checkpoint root's identity. The production-shaped rehearsal renders exactly such a candidate whose `checkpoint_root` is the real GLM-5.2 directory. Committed code never routes it to the coordinator and the install is ephemeral, so access stays 0 — but the property rests on call-graph discipline rather than a root check.
- **DID-06-ONE-DESCRIPTOR-CONSUMED** — Five fds are inherited and censused, but both target sources read only `file_descriptors[0]`. Ordinals 3–6 are never read, and the numerics cores are JSON-shaped, so no real multi-shard read path is qualified at V8.
- **DID-07-GENERATOR-HAS-NO-CHECK-MODE** — `generate_f017_lifecycle_v8_implementation_authorities.py` unconditionally rewrites six authority files; V6's generator had `--check`. Drift detection depends solely on CI's `git diff --exit-code`.
- **DID-08-QUALIFICATION-NOT-BYTE-REPRODUCIBLE** — Synthetic qualification and rehearsal evidence embed tempdir-derived digests, HEAD, and `vm_stat`, so CI asserts fields rather than `cmp`-ing against the banked v3 artifacts (unlike the numerical requalification).
- **DID-09-MEMORY-GATE-ADVISORY** — `future_live_memory_gate` can read `FAIL_CLOSED` while `result` stays `PASS`; nothing asserts it. Acceptable as a forward-looking observation; it should become an assertion at Event-04.
- **DID-10-INDEPENDENT-CHECKER-C7-N2-UNTESTED** — The import-separated checker is probed only with C7-N1's mode value. Its C7-N2 ordering is structurally correct but has no direct regression.
- **DID-11-V6-WORKTREE-NOT-REMOVED** — CI adds the detached V6 worktree and never removes it.
- **DID-12-RUNTIME-REALIZES-ONE-FAILURE-TERMINAL** — The 47 modeled failure terminals are realized symbolically only; the runtime emits one generic capsule at a fixed path. This is correctly scoped — the invariants declare `V8_DESIGN_AND_SYNTHETIC` / `DESIGN_FROZEN_NOT_LIVE` — so no banked claim is false, but it is the gating work for any Event-04 coordinator, and DID-01/02/03 must be closed as part of it.

## Does anything prevent requesting the Event-04 human GO?

No. No blocking or non-blocking-required finding survives verification. The safety posture is enforced, not merely asserted: no Event-04 authorization exists, no live authority can be minted from committed bytes, original checkpoint access is zero, and the exact-head `FULL_NATIVE` run covers the reviewed implementation byte-for-byte. C7-N1 and C7-N2 are genuinely repaired at all three validators, with the ordering that makes them repairs rather than coincidences. The twelve defense-in-depth items are forward work for the Event-04 execution implementation, not defects against any claim this milestone makes.

`ACCEPT_FOR_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_04_AUTHORIZATION_PREPARATION`
