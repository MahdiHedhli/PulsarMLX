All validation complete. A decisive positive result along the way: a fresh release build of the committed grader source reproduces the grant's pinned executable hash `8cb0d125…` exactly, closing the executable-substitution attack. But the review found one blocking defect and two required repairs. Final report:

```json
{
  "reviewer_model": "claude-fable-5",
  "reviewer_track": "INDEPENDENT_ADVERSARIAL_COMPARISON_AUTHORITY_REVIEWER",
  "reviewed_branch": "feat/017-rust-native-inference-runtime",
  "reviewed_head": "3b83ef6a4bfbd6b6282bcfe1a13fc02dd59cc8e3",
  "detached_read_only_worktree": "/private/tmp/f017-grant-review.s3VDxR/repo (detached HEAD, clean; no repository bytes modified; cargo target redirected outside the worktree)",
  "reviewed_artifact_hashes": {
    "grant": {"path": "specs/017-rust-native-inference-runtime/contracts/f017-native-d3-5-comparison-read-grant-v1.json", "sha256": "ed745c5bd5cba73808550f0d53cf0b0dd35f0365e97f090c310da1ba80bc1920", "recomputed_match": true},
    "stage_mapping": {"path": "specs/017-rust-native-inference-runtime/contracts/f017-native-d3-5-canonical-stage-mapping-v1.json", "sha256": "9f8bb8b0b65188fd2377521c79655c82842063f870a30aeeaea97e0483cd74c5", "recomputed_match": true},
    "consumer": {"path": "crates/f017-native/src/bin/d35_grader.rs", "sha256": "35650d198a3f8a3bd28986e43186e8cdfeb20d66b1e4dc2d91454c3f8249ac82", "recomputed_match": true},
    "builder": {"path": "scripts/research/build_f017_native_d35_comparison_grant_v1.py", "sha256": "3b5343f0465d9ccb80eb6e855d52b3d0158a8c5f533c548fccc7bc0c33b97ebf", "recomputed_match": true},
    "validator": {"path": "scripts/research/validate_f017_native_d35_comparison_grant_v1.py", "sha256": "f240268b92ae4bbe78d02352db726154b7aa5782f882ade2c1cb2d66bc5da810", "recomputed_match": true},
    "mutation_tests": {"path": "scripts/research/tests/test_f017_native_d35_comparison_grant_v1.py", "sha256": "d1ee29957f1366fdf042d3f48e3af3b37059005c4f9facaeadc78ef6baeb1024", "recomputed_match": true},
    "d0": {"path": "specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-numeric-acceptance-contract-v2.json", "sha256": "cc62cdc7550e3a25f55de783e9eb7c68f6cf03d0eafb944a86dc8a2a60007fb9", "recomputed_match": true},
    "d3_5_evidence": {"path": "docs/architecture/reviews/evidence/f017-native-retained-qualification-execution-evidence-v1.json", "sha256": "13b1a3a653cf0325f59b0b3b035b7804439a19c000ef8ddf19dad9ecb8316ac8", "recomputed_match": true},
    "diagnostic_disclosure": {"path": "docs/architecture/reviews/evidence/f017-native-d3-5-ungranted-diagnostic-read-disclosure-v1.json", "sha256": "a1daa331ce641b7e34459de1f7a5584632c8cb5bce82862a66e93b330e9aa03b", "recomputed_match": true}
  },
  "tests_performed": [
    "Recomputed SHA-256 of all 9 listed artifacts at HEAD; all match the request.",
    "Structural audit of the grant: 15+40+34=89 reads, contiguous ordinals 0..88, unique roles, no duplicate paths (the s0 file legitimately appears once as expected.input_hidden and once as operand.s0, both receipted), all paths under ${HOME}/.local/share/pulsarmlx/f017/, zero paths containing 'checkpoint', counts fields exact.",
    "Stage-mapping audit: 34 rows aligned 1:1 with the 34 capture reads; only ordinal 0 is RETAINED_DIRECT_VALUE; direct_production_copy_allowed_for_recomputed_stage=false; source_capture_manifest_sha256 equals the D3.5 evidence representative_manifest_sha256 (5ad1e8f4...).",
    "Consumer implementation review (d35_grader.rs) against D0 v1 (sha verified equal to the v2 base_contract pin e30b8647...) plus the v2 ordinal-13 override: the grader's required ordinal set {0,12,13,17,18,19,20,21,25,26,27,28,31,32,33} exactly equals the effective BYTE_EXACT_REQUIRED / NUMERICALLY_BOUNDED_REQUIRED / STRUCTURAL_EXACT_NUMERIC_BOUNDED / INTENTIONALLY_DISTINCT rows; the 19 ungraded capture stages are all IMPLEMENTATION_SPECIFIC_REPRODUCIBILITY (pinned-environment reproduction, covered by the banked D3.5 determinism evidence, 20/20 byte-identical runs), so no required comparison is missing.",
    "Tolerance/class audit: grader hardcodes native_intermediate_tier_b (0.015625/0.0078125/0.9999), native_final_tier_b (0.0625/0.03125/0.999), routing_weight max_abs 1e-5, and the operand-conditioned cap 2*gamma(2n)*sum|f64(w)*f64(x)| + 4n*2^-149 — all exactly equal to the frozen D0 metric profiles; per-coordinate enforcement mathematically implies the profile's RMSE and cosine gates; caps are derived from operands only, never from native output or observed error.",
    "secure_read audit: lstat regular-file/non-symlink/nlink==1/read-only/size gate, O_NOFOLLOW open, dev/ino identity across lstat->open->after, EXPECTED=BEFORE=CONSUMED=AFTER same-descriptor sha equality, per-read receipt; single pass over exactly the 89 grant rows (exact budget); output confined to allowed_output_root with create_dir + O_CREAT|O_EXCL 0400 giving one-attempt no-retry/no-resume semantics; no ledger writes; no checkpoint path reachable.",
    "parse_json_no_duplicates review: rejects duplicate keys at any depth, trailing data, and non-finite numbers.",
    "Route authority: decoded selected_ids_hex -> (250,10,237,62,73,177,218,28) matching the expert_down expected artifacts; sha256 of decoded ids and weights match selected_ids_sha256/routing_weights_sha256, and all three route hashes equal the D0-v2 ACCEPTED_ROUTE_AUTHORITY registry entry; weights all in (0,1).",
    "Cross-branch authority verification via git show at pinned commits: all expected/operand source_authority files at 54e0ea92/c1cdb079/be26de43/f6634374/f2a7aa38 hash-match their source_authority_sha256; historical master ledger at f2a7aa38 hash-matches aa98f5cc... and its receipt_chain.terminal_count is exactly 175; retention-reuse grant at HEAD hashes to the evidence-pinned b22a11c8...; the Fable adjudication result file hashes to the disclosure-pinned 7108cd54....",
    "Diagnostic-disclosure audit: disclosure contains artifact identities only (no metric values), is marked non-authority, diagnostic_metrics_reusable=false is enforced by both grader and validator, and the grant's 15 expected reads are exactly the 14 disclosed paths plus the previously granted s0 — no ungranted expansion and no metric reuse.",
    "Independently hashed the machine-local capture-manifest.json (metadata only, no payload): 5ad1e8f4... — equal to both committed pins (evidence and stage mapping).",
    "python3 scripts/research/validate_f017_native_d35_comparison_grant_v1.py with resolve_executable=False => PASS {read_census:89, payload_reads_during_validation:0, original_checkpoint_reads:0}; the full default run fails only on the absent machine-local target/release binary in this worktree; the output-root-absence gate passed, confirming the grading event has not been executed.",
    "python3 -m unittest scripts.research.tests.test_f017_native_d35_comparison_grant_v1 -v: test_mutations (all 17 mutation classes rejected) => ok; test_baseline errors only on the absent built binary (environmental).",
    "CARGO_TARGET_DIR=/tmp cargo test -p f017-native --no-run => compiles; cargo test -p f017-native --lib => 3/3 pass (including the retained enforcer duplicate-read/readback tests).",
    "Reproducible-build check: cargo build --release of the committed source produced a binary with SHA-256 8cb0d125d0db2b825ba4c516088d998fc4db279534b9efe60ba9c1772c60b77f — byte-identical to the grant's executable_sha256, closing the executable/source substitution attack.",
    "Execution prohibitions honored: 0 comparison payload reads, 0 D3.5 numerical executions, 0 checkpoint reads, 0 real/live P1 executions or authorizations, no grader invocation, no repository byte modification."
  ],
  "findings": [
    {
      "id": "F017-D35-GRANT-001",
      "severity": "BLOCKING",
      "path": "specs/017-rust-native-inference-runtime/contracts/f017-native-d3-5-comparison-read-grant-v1.json",
      "evidence": "All 34 capture_reads rows record source_commit f38dc2756bd4949e8883d6afc33b324fe264dd19, which does not exist in the repository (git cat-file fails; absent from all refs). The actual banking commit for the D3.5 evidence is f38dc275b86799712725765cec489089a4a4db50 (same 8-hex prefix, different suffix). Root cause: the wrong 40-char hash is hardcoded at scripts/research/build_f017_native_d35_comparison_grant_v1.py:156. The validator only checks len(source_commit)==40 and never resolves it, so this 'wrong source commit' defect passed validation. The source_authority_path/sha256 on those rows do verify against the real commit, so content binding survives, but the recorded provenance commit is fictitious.",
      "failure_mode": "The capture rows' commit-level provenance chain — the chain that defends against native capture regeneration / second-D3.5 substitution — cites a nonexistent commit, and the committed validator cannot detect this class of mutation at all. This is a direct hit on the required attack 'wrong path, SHA, size, dtype, shape, serialization, source commit, or authority'.",
      "required_repair": "Correct the builder constant to f38dc275b86799712725765cec489089a4a4db50, regenerate the grant (its hash will change), extend the validator to resolve every source_commit via git and verify source_authority bytes at that commit (as it already does for the historical ledger), and submit the regenerated grant for a fresh independent review cycle."
    },
    {
      "id": "F017-D35-VALIDATOR-002",
      "severity": "NON_BLOCKING_REQUIRED",
      "path": "scripts/research/validate_f017_native_d35_comparison_grant_v1.py:97-102",
      "evidence": "The validator loads ${HOME}/.../same-00/capture-manifest.json and treats it as the authority for the 34 capture sha256/byte/shape values, but never verifies the manifest's own SHA-256 against the committed pins (evidence.representative_manifest_sha256 == stage_mapping.source_capture_manifest_sha256 == 5ad1e8f4...). It also does not check the capture rows' dtype against the manifest. I independently hashed the local manifest and it does match 5ad1e8f4..., so the committed state is consistent, but the check is missing from the machine-verifiable suite.",
      "failure_mode": "A regenerated or tampered local capture set with a rewritten manifest plus a regenerated grant would PASS the committed validator — the 'checkpoint or shard fallback unreachable' guarantee holds, but the 'native capture regeneration' attack is only prevented by unverified builder honesty rather than by a hash chain enforced at validation time.",
      "required_repair": "Before using the manifest as capture authority, recompute sha256 of its bytes and require equality with the D3.5 evidence pin (5ad1e8f4...), and compare per-row dtype as well; add a mutation-test class for a manifest-hash mismatch."
    },
    {
      "id": "F017-D35-GRADER-003",
      "severity": "NON_BLOCKING_REQUIRED",
      "path": "crates/f017-native/src/bin/d35_grader.rs:341,364,365,373,375",
      "evidence": "The grading result emits oracle label \"RETAINED_CANONICAL\" for required ordinals 12 and 13, but the D0-v2 oracle registry defines RETAINED_CANONICAL_S1 (ordinal 12) and RETAINED_CANONICAL_ROUTER_NORMALIZED (ordinal 13); for required ordinals 20/21/25/27/28 it emits \"OPERAND_CONDITIONED_F64\"/\"OPERAND_CONDITIONED_F64_REFERENCE_CHAIN\", which are not registry labels. The bound data is correct (expected-artifact sha256s in the grant equal the registry expected_sha256 entries, and the numeric method matches the operand_conditioned_matvec profile exactly), so this is a vocabulary defect, not a data substitution — but D0-v2 finding-repair F2 states 'all effective stage oracle labels resolve through exact registry entries', and the consumer's output violates that on 7 of the 15 required ordinals.",
      "failure_mode": "The grading result — the future acceptance artifact — carries oracle attributions that cannot be mechanically resolved against the frozen D0-v2 registry, weakening post-hoc audit of oracle binding and contradicting a declared D0 repair mechanism.",
      "required_repair": "Emit the exact registry label for each effective stage row (RETAINED_CANONICAL_S1, RETAINED_CANONICAL_ROUTER_NORMALIZED, INDEPENDENT_COMPLETE_EXPERT with the operand_conditioned_matvec metric, etc.), rebuild, update the grant's source/executable hashes, and re-review."
    },
    {
      "id": "F017-D35-GRADER-004",
      "severity": "DEFENSE_IN_DEPTH",
      "path": "crates/f017-native/src/bin/d35_grader.rs:348-349",
      "evidence": "The routing_weight profile pass rule is MEMBERSHIP_THEN_ORDER_THEN_TIE_THEN_INTERVAL_THEN_MAX_ABS with mathematical_interval_required=true; the grader implements membership/order/tie (via byte-exact selected_ids and ranking hashes) and max_abs<=1e-5, but no explicit interval gate on the captured weights. With the frozen authority weights all in (0.229, 0.749) and a 1e-5 cap, the omission cannot change this event's outcome.",
      "failure_mode": "A frozen-profile gate is silently unimplemented; in a future reuse of this consumer with different route authority the interval requirement would not be enforced.",
      "required_repair": "Add an explicit interval check on captured routing weights per the profile."
    },
    {
      "id": "F017-D35-GRADER-005",
      "severity": "DEFENSE_IN_DEPTH",
      "path": "crates/f017-native/src/bin/d35_grader.rs:285-297",
      "evidence": "In f64_matvec_and_caps the term `tail*0.0` is dead code (computed 4n*2^-1074 multiplied by zero) with a comment implying intent; the effective cap 2*gamma(2n)*sum_abs + 4n*2^-149 nonetheless matches the frozen D0 formula exactly. Separately, the tier_b structural gates signed_zero=EXACT_WHEN_BOTH_VALUES_ARE_ZERO is not implemented (a +0.0 vs -0.0 pair passes via |a-e|=0).",
      "failure_mode": "Confusing dead arithmetic invites future mis-edit of the cap; the signed-zero structural gate of the frozen profile is unenforced (no practical effect on magnitude-based pass/fail).",
      "required_repair": "Delete the dead term and its misleading comment; implement the signed-zero bit check for tier_b rows."
    },
    {
      "id": "F017-D35-GRADER-006",
      "severity": "DEFENSE_IN_DEPTH",
      "path": "crates/f017-native/src/bin/d35_grader.rs:155-164,311-330",
      "evidence": "The grader pins D0 sha, D3.5 evidence sha, consumer id, and ledger terminal 175 as compile-time constants, but not the grant_id, the stage-mapping sha, the route-authority constants, or the allowed_output_root value; any grant satisfying the policy predicate would be consumed, with detection only post-hoc via the recorded grant_sha256 (pinning the grant hash in the binary is circular since the grant pins the executable hash, but the route authority and output root are not circular and could be constants). Additionally ${REPOSITORY_ROOT} is resolved as the current working directory rather than a discovered repository root — fail-closed given the executable-path and hash equality checks, but the 'bind grader to repository root' commit actually binds to invocation cwd.",
      "failure_mode": "A policy-conforming substitute grant (e.g., weakened route authority or relocated output root) would execute and be caught only by downstream comparison of the recorded grant_sha256 against the accepted grant.",
      "required_repair": "Pin route-authority hex/sha constants and the allowed_output_root value in the consumer, and resolve the repository root structurally (e.g., ancestor containing .git) rather than trusting cwd."
    },
    {
      "id": "F017-D35-VALIDATOR-007",
      "severity": "DEFENSE_IN_DEPTH",
      "path": "scripts/research/validate_f017_native_d35_comparison_grant_v1.py:91,119; specs/.../f017-native-d3-5-comparison-read-grant-v1.json",
      "evidence": "The validator loads the retention-reuse grant as operand authority without pinning its sha256 (I verified it hashes to the evidence-pinned b22a11c8...), checks allowed_output_root for absence but not for its exact required value, and does not verify per-row source_authority_sha256 for expected/operand rows against committed bytes (I did so via git show; all match). Cosmetic: the same s0 bytes carry serialization 'CANONICAL_LITTLE_ENDIAN_F32_CONTIGUOUS' as expected.input_hidden but 'CANONICAL_F32_LE' as operand.s0.",
      "failure_mode": "Several bindings that the review had to establish manually are not machine-enforced, so future regenerated grants lean on reviewer diligence instead of the validator.",
      "required_repair": "Pin the retention-reuse grant sha, exact-value check allowed_output_root, verify source authorities via git show, and normalize the serialization vocabulary."
    }
  ],
  "counts": {"BLOCKING": 1, "NON_BLOCKING_REQUIRED": 2, "DEFENSE_IN_DEPTH": 4},
  "verdict": "REJECT",
  "statement": "All nine artifact hashes recomputed and matched, and most of the requested attack surface is genuinely closed: the release build of the committed grader source reproduces the pinned executable hash exactly (no consumer substitution); reads are receipted EXPECTED=BEFORE=CONSUMED=AFTER on a single descriptor with an exact 89-read budget and no checkpoint path reachable; the required grading set exactly matches the effective D0 (v1 + ordinal-13 override) required rows with byte-identical frozen tolerances and operand-only cap derivation; route authority equals the D0-v2 registry and decodes self-consistently; cross-branch authorities, the historical ledger (terminal exactly 175, no advance), and the disclosure (identities only, metrics unusable and unused) all verify; the output root is absent, confirming no premature grading. The verdict is nonetheless REJECT under the acceptance rule: the grant's 34 capture rows cite a nonexistent source commit (f38dc2756bd4...) hardcoded in the builder — a direct instance of the 'wrong source commit' attack that the committed validator cannot detect (BLOCKING); the validator uses the machine-local capture manifest as capture authority without hash-pinning it to the committed 5ad1e8f4... evidence pin, leaving the capture-regeneration attack machine-unchecked (NON_BLOCKING_REQUIRED); and the grader emits oracle labels on 7 required ordinals that do not resolve through the D0-v2 oracle registry, contradicting the declared F2 repair (NON_BLOCKING_REQUIRED). After these repairs the grant must be regenerated (its hash and the consumer hashes will change) and resubmitted for a fresh independent review cycle before any grading read."
}
```

The decisive defect: every capture row's `source_commit` is `f38dc2756bd4949e8883d6afc33b324fe264dd19`, a hash that exists nowhere in the repository — the real banking commit is `f38dc275b86799712725765cec489089a4a4db50`, and the wrong value is hardcoded at `scripts/research/build_f017_native_d35_comparison_grant_v1.py:156`. Content bindings still verify by SHA-256, but this is exactly the "wrong source commit" attack the review was required to run, the validator cannot catch it, and repairing it changes the grant bytes — so the grant must be rebuilt and re-reviewed. The two required (non-blocking) repairs are the unpinned capture manifest in the validator and the non-registry oracle labels in the grader output. Everything else I attacked — executable reproducibility, read receipts and budget, tolerance/class fidelity, route authority, cross-branch authorities, ledger terminal, disclosure containment, one-attempt output semantics — held up.
