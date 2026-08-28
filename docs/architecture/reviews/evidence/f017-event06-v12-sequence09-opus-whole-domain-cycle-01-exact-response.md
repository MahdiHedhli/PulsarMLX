Working tree clean, no production side effects. Here is my arbitration.

```json
{
  "verdict": "REJECT",
  "claim_verdicts": [
    {
      "claim_id": "C-PREQUAL-001",
      "verdict": "ACCEPT",
      "evidence": "Both dispositions reproduced at HEAD. PREQUAL-001 (version-forward successor chain + domain-correct measurement): readiness V3, authorization v12_v3 adapter and production v2 exist, import cleanly and are exercised; implementation-measurement binds 9 paths at head 80d9c39f/tree ba8783c2 and every measured sha reproduces via git_sha. PREQUAL-002 (real producer/checker/success-capable transaction, zero live invocations): producer, checker and _commit_bound_production_transaction are genuinely implemented (not stubs), and production_capability_instances=0 / production_commit_success_calls=0 reproduce. validate --profile final passes 10/10 predicates and 12/12 mutations at 695494ae.",
      "invalidation_disposition": "Not invalidated. The capability-forgery defect (F-OPUS-S9-001) is a new finding about gate strength, not a failure to close either prequalification finding as worded."
    },
    {
      "claim_id": "C-CAPABILITY-001",
      "verdict": "REJECT",
      "evidence": "Second half holds (0 capability instances in Sequence 9, reproduced). First half is false. FutureGoCapabilityV2 seals only its own __new__; object.__new__(FutureGoCapabilityV2) returns a type-exact instance, and object.__setattr__ populates every __slots__ field despite the __setattr__ block (same primitive the class uses internally). I constructed such a token with attacker-chosen target_parent/target_leaf/nonce and no GO document of any kind; validate_future_go_capability ACCEPTED it and returned it unchanged. That checker is the sole gate in commit_production_installation_v2, which then passes validated.target_parent/target_leaf straight to _commit_bound_production_transaction. The producer-consumer matrix names produce_future_go_capability as the only producer for this authority; that binding is unenforced.",
      "invalidation_disposition": "Invalidating for this claim. Fix is well-defined: have produce_future_go_capability register issued instances (id-keyed WeakSet) and have validate_future_go_capability require membership, and/or re-verify source_sha256 against retained raw GO bytes. Requires re-qualification of the capability gate."
    },
    {
      "claim_id": "C-TRANSACTION-001",
      "verdict": "REJECT",
      "evidence": "Success-capable: confirmed, 10/10 synthetic non-authority commits succeed with real O_CREAT|O_EXCL|O_NOFOLLOW writes, fsync, descriptor-relative readback and dev/ino stability. Exact: receipt binds parent/target device+inode, per-payload leaf/bytes/sha256, and reserves transaction-receipt.json. Uninvoked: confirmed, 0 production success calls, no F017-CONSUMED-* marker exists anywhere on the host. Fail-closed FAILS on two counts: (1) the capability gate accepts forged tokens (F-OPUS-S9-001), so the production writer is reachable without a GO; (2) fault_stage='capability_expiry' is accepted by _commit_no_replace as a member of RACE_FAMILIES but is never tested anywhere in the function body, so a caller requesting that injected fault receives a successful commit instead of a failure. I reproduced this directly: all 9 other families raise, capability_expiry returns NO-RAISE.",
      "invalidation_disposition": "Invalidating. Both defects are in the production-facing path. capability_expiry must either raise in the engine or be removed from RACE_FAMILIES; the policy declares synthetic_fault_injection CLOSED_ENUMERATION_ONLY, which an inert member violates."
    },
    {
      "claim_id": "C-READINESS-001",
      "verdict": "ACCEPT",
      "evidence": "Census exact: readiness interface v11 and v12 each declare field_count=86; required_fields length 86; the flattened exact_types lists are 86 unique names and set-equal to required_fields; exact_predicates pin opus_verdict, original_checkpoint_shard_opens=0, event_06_executed=false. Reconstruction exact: 20 independent fixture reconstructions yield readiness_unique_digest_count=1 (reproduced by me, not read from evidence). Consumer instantiable: validate_event06_readiness_declaration_v3 returns a sealed value consumed by build_identity_candidate_from_readiness_v3 and prepare_production_installation_v2. Attacks rejected: stale role sha (numerical_contract_sha256 repointed) -> Event06ReadinessError; manifest role deletion with declaration repointed to the new manifest hash -> Event06ReadinessError 'authority manifest census'; alias/type/schema mutations -> 326 rejections, 0 unexpected passes.",
      "invalidation_disposition": "Not invalidated. F-OPUS-S9-008 (module default interface is the candidate v11, not final v12) is advisory only: v11 and v12 are identical over the 86-field census, and both in-repo call sites pass contract_path explicitly."
    },
    {
      "claim_id": "C-INSTALL-001",
      "verdict": "ACCEPT",
      "evidence": "Causally ordered: prepare_production_installation requires sealed readiness/GO/plan/identity/census/integration, then binds approval.human_go_sha256 -> human_go.sha256, approval.execution_plan_sha256 -> plan.sha256, approval.event_identity_plan_sha256 -> event_identity.sha256, approval.candidate_sha256 -> canonical candidate digest, and cross-checks authorization_id/package_attempt_id and event_identity.execution_plan_sha256. Deterministic: 20 reconstructions give installation_unique_identity_set_count=1 over the (candidate, receipt, installed) sha triple, reproduced by me. Non-live: gate terminal is PACKAGE_START_ELIGIBLE_DRY_STOP, live_installations=0, package_starts=0, identities_consumed=0, checkpoint_root is the /NONEXISTENT sentinel and checkpoint_root_resolved=false.",
      "invalidation_disposition": "Not invalidated."
    },
    {
      "claim_id": "C-PROVENANCE-001",
      "verdict": "ACCEPT",
      "evidence": "All 12 CURRENT_DESIGN_AUTHORITY manifest bindings rehashed against on-disk bytes: 12/12 exact, 0 problems. roles list equals bindings keys; binding_count=role_count=len(bindings)=21. All 11 freeze-receipt corrected_artifacts rehashed: 11/11 exact. Candidate identity derives from canonical_bytes(candidate.as_dict()) and is bound into approval, integration and the prepared triple; the durable receipt binds parent/target device+inode plus per-payload role/leaf/bytes/sha256. Implementation measurement head/tree verified via git rev-parse and every measured path via git show.",
      "invalidation_disposition": "Not invalidated. Capability-authority provenance is unenforced, but that is scored under C-CAPABILITY-001 rather than double-counted here."
    },
    {
      "claim_id": "C-MUTATION-001",
      "verdict": "REJECT",
      "evidence": "Readiness mutation coverage is genuinely substantive: 326 rejections >= frozen floor 324, 0 unexpected passes, covering delete/null per required field, per-category type substitution, predicate inversion, container substitution, unknown alias, duplicate semantic key, leading-whitespace and scalar coercion. Sealed-capability coverage is NOT substantive. test_caller_copy_pickle_and_constructor_attacks_fail is vacuous: it evaluates operation(cls()) and cls() itself raises TypeError, so copy/deepcopy/pickle are never applied to any instance. I instrumented it and confirmed 'copy reached: False' for both classes. No test attempts the direct-construction bypass that actually works. assert_capability_sealed is dead code, never called from any harness. assert_readiness_v3_copy_pickle_closed exercises only copy.copy/copy.deepcopy despite its name. Race coverage declares 10 families but exercises 9: the qualifier 'continue's past capability_expiry and credits failures+=1 without calling anything, and the expiry branch in validate_future_go_capability is also never reached (the Sequence 9 GO fixtures expire at t=2 and are rejected earlier on posture/freshness via FAILURE_OUTCOMES['go']).",
      "invalidation_disposition": "Invalidating. The precise coverage that should have caught F-OPUS-S9-001 is the coverage that is vacuous. Requires a real sealed-instance copy/pickle/direct-construction suite and a genuinely exercised expiry family."
    },
    {
      "claim_id": "C-OUTCOME-001",
      "verdict": "REJECT",
      "evidence": "Maximal-prefix truth is real and I verified it directly by inspecting on-disk residue after each injected fault: exclusive_create -> no target dir; target_identity -> empty dir; write_short/write_error/file_fsync -> candidate.json only; readback_identity and concurrent_replacement -> 3 payloads, no receipt; directory_fsync -> 3 payloads + transaction-receipt.json; candidate_replay -> no target dir. Every residue is exactly the prefix of completed work, and every outcome_id matches FAILURE_OUTCOMES. That is 9 of 10 families. The claim still fails: capability_expiry is inert, so a requested fault yields a successful commit and no failure outcome at all, which is a side-effect-truth violation rather than merely absent coverage. Separately, the '16 installation outcomes' are validated only as a lookup table (installation_failure(category).outcome_id == expected); no harness exercises the 16 outcomes' side effects, and capability_expired is unreachable throughout Sequence 9.",
      "invalidation_disposition": "Invalidating on the inert family. The verified 9-family prefix behaviour is sound and should be retained; only capability_expiry and the unexercised capability outcomes need remediation."
    },
    {
      "claim_id": "C-NOACCESS-001",
      "verdict": "ACCEPT",
      "evidence": "Interposition-before-import verified by executing their subprocess test: guards are installed on os.open, builtins.open, Path.stat, Path.resolve and mmap.mmap before f017_event06_production_installation_v2 and the qualifier are imported, and the 4-key census is 0. Census substance verified independently rather than read from evidence: I installed my own interposition over the FULL qualify() run and measured 0 checkpoint-pattern opens, 0 stats, 0 resolves, 0 mmap, 0 mlx imports, 0 torch imports, 0 socket imports. AST guard confirms no mmap/socket/ctypes/importlib/multiprocessing imports and no eval/exec/compile/globals/locals/vars/__import__ calls in the four successor modules, and no 'GLM-5.2' literal. The only third-party numerics touched is numpy, reached transitively at module load from historical f017_corrected_oracle_secondary_target_source_v10.py; no Sequence 9 source imports it and no numerical operation is performed.",
      "invalidation_disposition": "Not invalidated. F-OPUS-S9-004 and F-OPUS-S9-005 are recorded as non-blocking required: the claim is true, but the shipped evidence for it is not self-producing."
    },
    {
      "claim_id": "C-CORPUS-001",
      "verdict": "UNRESOLVED",
      "evidence": "The evidence asserts historical_evidence_path_census=599 with census sha256 8f159df5..., ignored_failure_keys=0 and unexplained_failures=0. No producer exists: grep across all Python sources finds no emitter for historical_evidence_path_census, and the two acceptance fields appear only in Sequence 5 generator role-requirement literals. I could not reproduce 599 under any plausible definition (recursive evidence tree 2124, f017-* 1903, .json 1577, f017-event06* 603 at HEAD / 596 at 5fb579b3 / 602 at 8804b6b9 / 594 at cd4bbb19, *v12* 577, *sequence* 291), and the declared census sha does not match a canonical or newline-joined listing of any of these. No enumerated failure list is banked, so 'no ignored or unexplained failures' has nothing to check against.",
      "invalidation_disposition": "Unresolved for environmental/artifact reasons, not adjudicated against. Resolvable in-repo by shipping the corpus enumerator and the failure list it consumes."
    },
    {
      "claim_id": "C-CI-001",
      "verdict": "UNRESOLVED",
      "evidence": "Locally verifiable parts check out: .github/workflows/macos.yml exposes workflow_dispatch mode=full, scripts/ci/classify_ci_change.py returns FULL_NATIVE unconditionally for requested_mode=='full' (line 107-108), and the four jobs named in the evidence correspond exactly to the FULL_NATIVE-gated jobs (Classify committed change, Apple Silicon workspace baseline, Apple MLX small-fixture validation, CI aggregate status). ci_head 8804b6b9 resolves and its tree is e8b095f8, matching ci_tree; the only commit after it (695494ae) adds solely the CI evidence file, so CI at the parent covers all source. NOT verifiable: run 33193441295's existence, its four job IDs, their conclusions, required_native_skips=0 and unexpected_skips=0. Those live only behind the GitHub API, and contacting external systems is prohibited by this arbitration's terms. The required 'altered CI identity' attack therefore cannot be performed.",
      "invalidation_disposition": "Unresolved by environment. Resolvable by banking the raw `gh run view 33193441295 ... --json` envelope alongside the receipt, as is already done for the Antigravity transport."
    },
    {
      "claim_id": "C-REVIEW-001",
      "verdict": "ACCEPT",
      "evidence": "Full byte-level chain reproduced. All three supplied inputs hash exactly to the stated digests: envelope c749a95b..., exact response 4c613698..., provenance 5269b816.... envelope['response'] encodes to bytes byte-identical to the exact-response file (not off by a trailing newline), and sha256 of that field equals the declared response_sha256 4c613698.... conversation_id ad867c3d-f9fd-408f-9b2b-3a808d0370bb, status SUCCESS, num_turns 1 and duration 300.712733 all match the provenance record. reviewed_commit/reviewed_tree equal the arbitration commit 695494ae / tree 94ae1a5f. Forgery of the response while preserving the digest would require a SHA-256 collision. provider_reported_model is honestly declared UNAVAILABLE_FROM_PROVIDER_ENVELOPE rather than fabricated.",
      "invalidation_disposition": "Not invalidated. F-OPUS-S9-010 advisory: request bytes and normalized result are referenced by digest but were not supplied, so only the response side of the transport is byte-verifiable here."
    },
    {
      "claim_id": "C-FREEZE-001",
      "verdict": "UNRESOLVED",
      "evidence": "The two governing documents are absent from the supplied checkout and unreachable. Prompts/F017/Mac-Studio-M1-Ultra/009__...__freeze-transition-table.json and Prompts/F017/AUTHORITY-FREEZING-POLICY-v1.md do not exist in the working tree, have never existed at any commit in this repository's 1243-commit history (git log --all over both paths returns nothing), and their declared commits e5ff7286 and 0abe6601 are not present objects. I therefore cannot compare the implementation against the predeclared table, and the required 'transition-table drift' attack is impossible. Internally consistent parts do hold: node Q2_PREOBSERVATION_FREEZE, label TEMPORALLY_FROZEN_NOT_OPERATIONALLY_RATIFIED, operationally_ratified=false, unchanged predicates (86 fields, floor 324, 16 outcomes, 10 families, zero_access_required) all match the contracts, and non-ratification is corroborated by the prepared manifest (final_acceptance_eligible=false, result PREPARED_INCOMPLETE, 9 roles UNBOUND_FUTURE).",
      "invalidation_disposition": "Unresolved by environment. Note the independent Antigravity challenge also reached its Point 11/12 conclusion 'Based on the freeze-transition-receipt', i.e. from the same receipt rather than from the table, so its zero-finding verdict does not close this."
    },
    {
      "claim_id": "C-HISTORY-001",
      "verdict": "ACCEPT",
      "evidence": "git diff --diff-filter=DMRT --name-only 23c4c415..695494ae returns 0 paths: the entire range is 36 files, 2949 insertions, 0 deletions, pure additions. No path matching event05/-v11/-v4/result-authority was touched. The validator's HISTORICAL_SHA predicate independently rehashes 8 pinned artifacts (readiness consumer v10, live installation v10, sequence05 role requirements v8, sequence05 schema authority v4, manifest v9, future-go capability v1, readiness_authority_v2.py, production_installation_v1.py) and all match; the test suite re-pins the latter two at 86796c3f... and 13579b0d.... V4 numerical contract and V11 result authority are bound by digest in the prepared manifest and rehash exactly.",
      "invalidation_disposition": "Not invalidated."
    },
    {
      "claim_id": "C-SAFETY-001",
      "verdict": "ACCEPT",
      "evidence": "Event 06 unexecuted: event_06_executed=false across the qualification output, rehearsal, measurement and prepared manifest. No live authority: live_authority=false, final_acceptance_eligible=false, result PREPARED_INCOMPLETE. No package/checkpoint/numerical/P1 state: package_starts=0, identities_consumed=0, checkpoint_root_resolved=false, checkpoint_shard_opens=0, checkpoint_identity_hash_reads=0, checkpoint_payload_reads=0, checkpoint_mmaps_or_tensor_reads=0, numerical_operations=0, p1_attempt_2_executed=false; corroborated by my own interposition measurement over the full run. Ledger preserved: historical_master_ledger=175 in the Sequence 9 CI evidence, consistent with the continuity graph state series. My arbitration created no live state: working tree clean at 695494ae, no F017-CONSUMED-* marker exists on the host, and I never invoked commit_production_installation_v2.",
      "invalidation_disposition": "Not invalidated. The capability-forgery probe was confined to the checker and to temporary directories; no production transaction was executed."
    },
    {
      "claim_id": "C-LAYERING-001",
      "verdict": "ACCEPT",
      "evidence": "Manifest contract v11 declares exactly 21 required_roles and the prepared instance realises them: role_count=21, binding_count=21, roles set-equal to bindings keys, 12 bound CURRENT_DESIGN_AUTHORITY (all rehashed exact) and 9 UNBOUND_FUTURE whose required_schema values each match the schema of the corresponding banked artifact. Acyclicity is contract-enforced: manifest_may_bind_itself=false, manifest_may_bind_final_declaration=false, final_declaration_binds_manifest=true, terminal_index_is_readiness_input=false. The finalisation order is therefore role artifacts -> manifest -> declaration, with the terminal/ratification index consuming manifest and declaration without feeding back. My own result (opus_result) is an UNBOUND_FUTURE role hashed into the manifest, which is consistent and introduces no cycle. I attempted a declaration/manifest hash cycle by deleting a role, recomputing the manifest digest and repointing the declaration: rejected with 'authority manifest census'.",
      "invalidation_disposition": "Not invalidated. F-OPUS-S9-009 advisory: the claim phrases the order as 'declaration above manifest above ratification record', whereas the contract places the terminal index above the declaration. Under either reading the graph is acyclic and the declaration-above-manifest relation holds, so the mechanically checkable content is satisfied."
    }
  ],
  "findings": [
    {
      "id": "F-OPUS-S9-001",
      "severity": "BLOCKING",
      "title": "Future-GO capability is forgeable without any GO document; the production checker accepts it",
      "location": "scripts/research/f017_event06_production_installation_v2.py:67-140, 295-313",
      "detail": "FutureGoCapabilityV2 guards only its own __new__ against a module-private sentinel. object.__new__(FutureGoCapabilityV2) bypasses that guard and yields an instance for which type(x) is FutureGoCapabilityV2 holds, and object.__setattr__ populates every __slots__ field notwithstanding the __setattr__ block. Reproduced: a token with authorization_id ATTACKER-AUTH, attacker-chosen target_parent and target_leaf, arbitrary nonce and a far-future expiry, whose prepared_installation_sha256 is copied from the real prepared object, is ACCEPTED by validate_future_go_capability and returned unchanged. That function is the only gate in commit_production_installation_v2, which forwards validated.target_parent and validated.target_leaf directly to _commit_bound_production_transaction. Notably the class does defend the weaker copy and pickle vectors while leaving the standard direct-construction bypass open.",
      "affected_claims": ["C-CAPABILITY-001", "C-TRANSACTION-001", "C-MUTATION-001"],
      "remediation": "Maintain a producer-side registry of issued capabilities (id-keyed WeakSet populated in produce_future_go_capability) and require membership in validate_future_go_capability, and/or re-derive and re-verify source_sha256 against retained raw GO bytes at check time."
    },
    {
      "id": "F-OPUS-S9-002",
      "severity": "BLOCKING",
      "title": "capability_expiry is a declared race family that the transaction engine silently ignores",
      "location": "scripts/research/f017_event06_durable_installation_transaction_v1.py:22-35, 192-368; qualify_...:299-303",
      "detail": "capability_expiry is a member of FAILURE_OUTCOMES and therefore of RACE_FAMILIES, so _commit_no_replace accepts it as a valid fault_stage, but no branch in the function body ever tests for it. Reproduced: passing fault_stage='capability_expiry' to commit_synthetic_non_authority_transaction returns a SUCCESSFUL commit while the other 9 families all raise with the correct outcome_id. The qualifier conceals this by 'continue'-ing past the family and crediting transaction_failures += 1 without calling anything, so the banked transaction_failures=10 and race_families=10 overstate exercised coverage by one. The corresponding checker branch (FAILURE_OUTCOMES['capability_expired']) is also unreachable in Sequence 9, since the GO fixtures expire at t=2 and are rejected earlier on posture/freshness.",
      "affected_claims": ["C-TRANSACTION-001", "C-OUTCOME-001", "C-MUTATION-001"],
      "remediation": "Either raise _fail('capability_expiry', ...) at a defined stage in _commit_no_replace, or remove capability_expiry from the engine's FAILURE_OUTCOMES and exercise the expiry outcome in the capability checker with a genuinely non-expired-then-expired capability. The policy's CLOSED_ENUMERATION_ONLY guarantee requires one or the other."
    },
    {
      "id": "F-OPUS-S9-003",
      "severity": "BLOCKING",
      "title": "The sealed-capability copy/pickle/constructor test is vacuous",
      "location": "scripts/research/tests/test_f017_event06_sequence09_authority_v1.py:181-186",
      "detail": "The test body is `with pytest.raises(TypeError): operation(cls())`. cls() raises TypeError inside the argument expression, so copy.copy, copy.deepcopy and pickle.dumps are never applied to anything. Instrumented and confirmed: the operation is reached 0 times for both FutureGoCapabilityV2 and DurableTransactionResult; the test merely re-asserts constructor rejection three times, duplicating test_successor_seals_are_repository_only. Consequently the class named in the test title has no real copy/pickle coverage and no direct-construction coverage at all, which is exactly the gap F-OPUS-S9-001 exploits. qualify() does cover real instances for readiness and prepared (6 sealed_object_attacks), and assert_transaction_result_sealed covers real DurableTransactionResult instances for copy only, not pickle.",
      "affected_claims": ["C-MUTATION-001"],
      "remediation": "Bind a real instance first (obj = ...; then assert each operation raises), and add explicit object.__new__ + object.__setattr__ fabrication cases asserting the checker rejects them."
    },
    {
      "id": "F-OPUS-S9-004",
      "severity": "NON_BLOCKING_REQUIRED",
      "title": "No-access counters in the qualification output are hardcoded literals, not measurements",
      "location": "scripts/research/qualify_f017_event06_sequence09_no_access_v1.py:431-444",
      "detail": "checkpoint_access, checkpoint_shard_opens, checkpoint_identity_hash_reads, checkpoint_payload_reads, checkpoint_mmaps_or_tensor_reads, numerical_operations, package_starts, identities_consumed, live_installations, production_capability_instances and production_commit_success_calls are emitted as constant 0/false in the returned dict. Nothing in the run observes them, so the banked zero census is an assertion by construction. The underlying property is nonetheless true: I measured it independently with my own interposition over the full run and obtained 0 for every forbidden operation.",
      "affected_claims": ["C-NOACCESS-001", "C-SAFETY-001"],
      "remediation": "Install the interposition inside qualify() and emit observed counters."
    },
    {
      "id": "F-OPUS-S9-005",
      "severity": "NON_BLOCKING_REQUIRED",
      "title": "The 12-key interposition census and clean_clone_result_sha256 have no in-tree producer",
      "location": "docs/architecture/reviews/evidence/f017-event06-v12-sequence09-authoritative-qualification-reproduction-v1.json; ...-no-access-rehearsal-v1.json",
      "detail": "The keys interposition_census (hash_stream, id_consumption, lease_creation, live_commit, mmap, numerical_execute, open, package_start, path_stat, pread, root_resolve, tensor_source) and interposition_installed_before_execution_facing_imports appear only in banked JSON; no Python source in the repository emits them. clean_clone_result_sha256=4136d83e... does not match canonical_bytes(qualify()), json.dumps(qualify()), any Sequence 9 evidence file, or the reproduction document minus its self-referential fields.",
      "affected_claims": ["C-NOACCESS-001"],
      "remediation": "Ship the clean-clone reproduction harness and state precisely which document clean_clone_result_sha256 digests."
    },
    {
      "id": "F-OPUS-S9-006",
      "severity": "NON_BLOCKING_REQUIRED",
      "title": "Full-corpus census is unreproducible and no failure enumeration is banked",
      "location": "docs/architecture/reviews/evidence/f017-event06-v12-sequence09-full-corpus-validation-v1.json",
      "detail": "historical_evidence_path_census=599 and its sha256 8f159df5... cannot be reproduced under any plausible path set I tried, and no emitter exists. Without the enumerated failure list, ignored_failure_keys=0 and unexplained_failures=0 are unfalsifiable.",
      "affected_claims": ["C-CORPUS-001"],
      "remediation": "Ship the enumerator and the failure corpus it consumes."
    },
    {
      "id": "F-OPUS-S9-007",
      "severity": "NON_BLOCKING_REQUIRED",
      "title": "Dead and mislabelled seal assertions",
      "location": "f017_event06_production_installation_v2.py:343-349; f017_event06_readiness_authority_v3.py:95-103",
      "detail": "assert_capability_sealed is never called from any harness or test. assert_readiness_v3_copy_pickle_closed exercises only copy.copy and copy.deepcopy despite naming pickle; pickle coverage for readiness exists only incidentally in qualify()'s separate sealed-object loop. Neither helper covers direct construction.",
      "affected_claims": ["C-MUTATION-001"],
      "remediation": "Call assert_capability_sealed on a producer-issued instance in a dedicated future-GO test, add pickle to the readiness helper, and add fabrication cases to both."
    },
    {
      "id": "F-OPUS-S9-008",
      "severity": "ADVISORY",
      "title": "Readiness consumer module defaults to the candidate interface v11 rather than the final v12",
      "location": "scripts/research/f017_event06_readiness_authority_v3.py:18-21",
      "detail": "INTERFACE points at f017-corrected-oracle-event06-readiness-consumer-interface-v11.json while the FINAL profile, the prepared manifest and the producer-consumer matrix all bind v12. The two interfaces are identical over the 86-field census and differ only in schema version and in pointing at manifest v10 vs v11 and role requirements v1 vs v2, and both in-repo call sites pass contract_path explicitly, so the default is never exercised today. It would matter to a future Q8 producer relying on the default, which would resolve manifest_schema 1.9.0 instead of 2.0.0.",
      "affected_claims": ["C-READINESS-001"],
      "remediation": "Point the default at v12, or make contract_path required."
    },
    {
      "id": "F-OPUS-S9-009",
      "severity": "ADVISORY",
      "title": "Layering claim phrasing does not match the contract's terminal-index position",
      "location": "specs/.../f017-corrected-oracle-event06-readiness-authority-manifest-v11.json",
      "detail": "C-LAYERING-001 states 'declaration above manifest above ratification record', but terminal_index_may_bind_manifest_and_declaration=true with terminal_index_is_readiness_input=false places the ratification record above the declaration. Acyclicity and the declaration-above-manifest relation hold under either reading.",
      "affected_claims": ["C-LAYERING-001"],
      "remediation": "State the intended ordering explicitly in the contract to remove the ambiguity."
    },
    {
      "id": "F-OPUS-S9-010",
      "severity": "ADVISORY",
      "title": "Review request bytes and normalized result not supplied for independent verification",
      "location": "f017-...-agy-whole-domain-cycle-01-provenance-v1.json",
      "detail": "request_sha256 1021bd12... and normalized_result_sha256 b04e3b70... are declared but the referenced artifacts were not provided, so only the response side of the transport is byte-verifiable in this arbitration.",
      "affected_claims": ["C-REVIEW-001"],
      "remediation": "Supply the request and normalized-result bytes alongside the envelope."
    }
  ],
  "counts": {
    "blocking_findings": 3,
    "non_blocking_required_findings": 4,
    "advisory_findings": 3,
    "unresolved_claims": 3
  }
}
```

## Evidence notes

**Reproduction baseline.** Confirmed HEAD `695494ae`, tree `94ae1a5f`, clean tree. All three supplied challenge inputs hash exactly to the stated digests. The diff from `23c4c415` is 36 files / 2949 insertions / **0 deletions** — `--diff-filter=DMRT` returns zero paths, so historical immutability is structural. I re-ran `qualify()` (PASS, 326 mutations) and the validator in both profiles (10/10 predicates, 12/12 mutations); the banked validator evidence differs from mine only in `validated_head`/`validated_tree`, which are inherently commit-stamped, and every other field is identical. Nothing after `cd4bbb19` touches source or contracts.

**What the implementation genuinely gets right.** The durable transaction engine is real, not a mock, and its maximal-prefix behaviour is the strongest result in this submission — I injected each fault and listed the target directory, and the residue is exactly the completed prefix in all nine working cases. Readiness mutation coverage is substantive (326 rejections, 0 unexpected passes), and my own stale-role-binding and manifest-role-deletion attacks were both correctly rejected. The Antigravity transport is byte-exact: `envelope['response']` is byte-identical to the exact-response file and hashes to the declared digest.

**Why this is REJECT.** The decisive finding is that the future-GO capability is forgeable. `object.__new__` plus `object.__setattr__` — stdlib primitives only, no monkeypatching of the module under test — produces a type-exact, fully-populated token that `validate_future_go_capability` accepts, carrying attacker-chosen `target_parent` and `target_leaf` that flow straight into the production writer. Sequence 9's own claim of zero capability instances remains true, so nothing unsafe has happened; but Sequence 9 exists to qualify the gate a *future* real GO will pass through, and that gate does not hold. The test that should have caught it is vacuous — `operation(cls())` raises in the argument, so copy/pickle is never applied — which I verified by instrumentation rather than inference.

Separately, `capability_expiry` is a declared race family the engine silently ignores: requesting it as a fault returns a successful commit. The qualifier `continue`s past it and credits a failure anyway, so `transaction_failures: 10` overstates exercised coverage.

**Two claims I could not adjudicate, and one caution.** The Freeze Transition Table and Authority-Freezing Policy are absent from the checkout and have never existed at any commit in this repository's 1243-commit history; their declared commits are unreachable objects. The required transition-table-drift attack is therefore impossible. Likewise, verifying CI run `33193441295` requires the GitHub API, which this arbitration prohibits — though I did confirm locally that the classifier honours `mode=full` and that the four named jobs match the `FULL_NATIVE`-gated jobs. Worth flagging: the independent Antigravity challenge reached its zero-finding verdict on both of these points "Based on the ... receipt," i.e. by restating the artifact rather than reproducing its binding, so its verdict does not close them.

On no-access I declined to simply mirror the evidence in either direction. The shipped counters are hardcoded literals, so I installed my own interposition across the full run and measured zero checkpoint opens, stats, resolves, mmaps, and zero MLX/torch/socket imports. The property is true; only its evidence is not self-producing. That is why C-NOACCESS-001 is ACCEPT with the evidence defect recorded separately.

I performed no production commit, created no live authority, opened no checkpoint, and left the working tree clean; no `F017-CONSUMED-*` marker exists on the host.