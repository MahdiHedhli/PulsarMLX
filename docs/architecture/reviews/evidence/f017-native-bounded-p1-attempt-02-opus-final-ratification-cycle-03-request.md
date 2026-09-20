# F017 native bounded-P1 attempt 2 — operator-authorized final independent review request (cycle 03)

Nonce: 8d33e8b54314a26de9b96169add127b9 (echo it exactly). Readiness head to echo: 01d8565a68345aab256a857f62970dc2712c7655 (feat/017-rust-native-inference-runtime == work/glm52-weekend-20260920; this packet is generated from that exact tree and every inline file below is verbatim as committed there, with its full sha256).

You are the operator-authorized final reviewer (claude-opus-5, fresh session, no prior context). Review ONLY the material inline below. Question: is the prepared attempt-2 domain fit for ONE human GO decision for exactly one bounded Apple M1 Ultra native P1 (prompt 9703, position 0, empty KV, greedy, expected token 154820 from the accepted Event 06 corrected oracle), executed once through execute-evidenced-v4, mandatory stop, no retry, no resume?

Reply with ONE JSON object only, no prose, no fences:
{"nonce": string, "readiness_head": string, "verdict": "ACCEPT_FOR_SINGLE_BOUNDED_M1_ULTRA_P1" or "REJECT", "blocking_findings": [{"id","body","evidence","remedy"}], "non_blocking_required_findings": [...], "defense_in_depth_findings": [...], "adversarial_cases_considered": int, "rationale": string}
A non-blocking-REQUIRED finding is one the operator must satisfy before execution; use it only for genuinely required steps not already listed as done or as remaining below.

## Cycle-03 addendum — disposition of the cycle-02 REJECT (verbatim response inline further below)
- B-01: declaration v3 (new file, append-only; v2 left as committed) replaces the CI precondition with an explicit narrowed gate (classification + Apple Silicon workspace baseline SUCCESS at the exact head; the MLX small-fixture job recorded, not required, while it fails only at the pre-existing V11 measurement-drift check), records the failing step, cause (5b39a21a vs f35d3411), its ancestry to the Event 06 source, and why it is independent of the executor, contract validation and the differentials. The V11 measurement chain (30 references incl. the corrected-oracle authorization module and scientific-access contracts) is the F017 planner's; it was not modified.
- B-02: this packet inlines, verbatim from the readiness head, declaration v3, admission contract v3, the corrected-oracle binding, the inert approval template and the reconciliation record, each with its full 64-hex sha256; the readiness head is the commit containing exactly these files.
- R-01: numerical delta since the attempt-1 executor (4faa404c): crates/quant/src/extra_ref.rs decode_iq4_xs_matrix lane order corrected (e00811df, corrected-oracle cycle-2 finding) — affects the four IQ4_XS tensors blk.8/75/76/77.ffn_down_exps.weight; model.rs is an observer-plumbing refactor with the same operations; loader/executor/p1_domain changes are authority/evidence/lifecycle. Prior expectation, durable-start consumption rule and post-failure scope are stated in declaration v3.
- R-02: by inspection, crates/stream/src/p1_domain.rs compares the produced token with authority.expected_token (~line 1090) and classifies the receipt from produced_token != Some(authority.expected_token) (~lines 1304-1311); stream::EXPECTED_TOKEN (21615) appears only in #[cfg(test)] code (module from line 1372); bounded_p1.rs execute-evidenced-v4 requires authority.attempt_id == contract.one_shot.attempt_id and constructs the math with authority.expected_token; the authority is minted by f017_native_p1_authorization.py from the contract's one_shot fields (expected_token 154820 enforced by validate_static generation 3), so the tokens agree by construction.
- R-03: 5b39a21a is an ancestor of the Event 06 immutable source c3526d68 (Event 06 ran with the changed wrapper; the change is +53/-9 lines of the gate-path wrapper); f017_corrected_oracle_primary_numerics_v3.py and f017_oracle_primary_decoders.py are byte-identical at c3526d68 and at the readiness head (sha256 in declaration v3).
- D-01: the executor rebuilt on the M1 Ultra at readiness head 8456f206 is byte-identical (sha256 91e50a0bb84a30450f9189da2122b84e1790649c1361ed90cea001ca537f52f0); execution_code_head semantics documented. D-02: operator assertions recorded in declaration v3 (approval JSON outside the repo; HEAD == origin == readiness head; no push between authorize and execution). D-03: the legacy service is QUIT (SIGTERM, exit verified, memory release verified), not suspended; vm_stat sampled within 5 s of admission; caffeinate. D-04: MappedShard::open rehashes every shard against the manifest (SHARD_IDENTITY_REHASH) before use. D-05: cycle-02 request/response banked verbatim with the reviewer provenance; this cycle is again a fresh claude-opus-5 session reading only the packet file.
- CI at the lineage head d690a967 (run 35509978669, FULL_NATIVE): classification SUCCESS, Apple Silicon workspace baseline SUCCESS, MLX small-fixture job FAILURE only at generate_f017_v11_measurement_v1.py --check.

===== DOMAIN DECLARATION v3 (sha256 269babfb21e612a50a543bf92973c8d1ddc0643e5b4268cf91153636c3915a6d) =====
{
 "schema": "pulsarmlx.f017.native-bounded-p1-execution-domain-final-declaration/3.0.0",
 "declaration": "F017_NATIVE_BOUNDED_P1_ATTEMPT_2_DOMAIN: PREPARED_FOR_ONE_HUMAN_GO_DECISION",
 "status": "PREPARED_HUMAN_GATE_REQUIRED",
 "supersedes": {
  "path": "docs/architecture/reviews/evidence/f017-native-bounded-p1-execution-domain-final-declaration-v2.json",
  "sha256": "95211e29b95c026ac4cd637ee0259eb842a90c9eab10dcacc666c960f8d9226b",
  "reason": "cycle-02 final review REJECT findings B-01 (a stated CI precondition is known-failed for a pre-existing reason) and B-02 (v2 was re-bound in place after the cycle-01 packet); v2 is left as committed from here on; v3 is the version a human approval binds"
 },
 "scope": "Presentation of one separate human GO/no-GO decision for exactly one bounded Apple M1 Ultra native P1 (attempt 2, a new attempt under a new authorization; attempt 1 remains a banked terminal failure whose retry is permanently prohibited). This declaration neither issues authorization nor executes anything.",
 "authoritative_branch": "feat/017-rust-native-inference-runtime",
 "prepared_on_branch": "work/glm52-weekend-20260920 (kept equal to feat/017-rust-native-inference-runtime by non-force fast-forward)",
 "execution_code_head": "5e32d68faa7b10168b9bb7f5d4fce6ebf212b737",
 "execution_code_head_semantics": "the source head the committed executor was built from; the admission contract's code manifest binds the same runtime files at the readiness head (the only difference between the two trees under crates/ is a bin declaration in crates/f017-native/Cargo.toml)",
 "executor": {
  "path": "specs/017-rust-native-inference-runtime/bin/f017-native-bounded-p1-v2",
  "sha256": "91e50a0bb84a30450f9189da2122b84e1790649c1361ed90cea001ca537f52f0",
  "built_on": "Apple M1 Ultra, macOS 25A354, Homebrew rustc 1.97.1, pinned MLX 0.31.2 keg (libmlx ad9b597b08e28b43c9b9791d2948fea601c76fe0b4a06d08cceeb4ad7b15e20d, libmlxc 3401e4f91a1d3f9b02c9bd1e728a10753f256d90bb1b40aebcaf8225592bee1a), release, OMP/RAYON/VECLIB threads 1",
  "rebuild_at_readiness_head_8456f206": "byte-identical sha256 91e50a0bb84a30450f9189da2122b84e1790649c1361ed90cea001ca537f52f0 (D-01 closed)"
 },
 "admission_contract": {
  "path": "specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-admission-contract-v3.json",
  "sha256": "7f98404333b0661f42c0e44f0a6c6451282513531a978dd442a98dafbfe94af8",
  "generation": 3,
  "m1_ultra_checks_at_d690a967_and_later": "validate-contract PASS, machine-preflight PASS, plan-only PLAN_ONLY_PASS (0 checkpoint reads)",
  "negative_controls": {
   "path": "docs/architecture/reviews/evidence/f017-native-bounded-p1-contract-v3-static-validation-v1.json",
   "sha256": "35a4ac82872524c47e7369cae3b409e990d545cdc2950a506d114c0222bc4e70"
  }
 },
 "corrected_oracle_binding": {
  "path": "specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-attempt-02-corrected-oracle-binding-v1.json",
  "sha256": "c582e3b4ae924fcaafad67f4e997f5d5e6a8dba1320ef395f6ba6499dd5a3512",
  "expected_token": 154820,
  "acceptance_mode": "EXACT_EXPECTED_TOKEN_STABLE"
 },
 "checkpoint_free_reconciliation": {
  "path": "docs/architecture/reviews/evidence/f017-native-checkpoint-free-reconciliation-20260920-v1.json",
  "sha256": "7af5cd9da4d8625c8a890d4a67ad913d5166f0218c41ca80f06b34f4d2ac2c34",
  "m1_ultra_reports": [
   {
    "path": "docs/architecture/reviews/evidence/f017-native-decoder-differential-corrected-oracle-v1-m1ultra.json",
    "sha256": "750e292b642b863c267a1b2e1313954e7fb9dd18656031215266db6d1ac1a2b0"
   },
   {
    "path": "docs/architecture/reviews/evidence/f017-native-graph-vs-corrected-oracle-differential-v1-m1ultra.json",
    "sha256": "74e7a1593e2ba2f8b76ad8e9e755543f10fb5f303c125c9483a2dd74fccb0224"
   }
  ]
 },
 "ci_gate": {
  "rule": "exact-head CI at the readiness head must show classification SUCCESS and the Apple Silicon workspace baseline job (cargo build/test) SUCCESS; the MLX small-fixture job is recorded, not required, while it fails only at the pre-existing V11 measurement-drift check",
  "observed_at_8456f206_lineage": {
   "run": 35509978669,
   "head": "d690a9675ed6ded0f25dfd22adce32a0fc3fa064",
   "mode": "FULL_NATIVE",
   "classify": "success",
   "apple_silicon_workspace_baseline": "success",
   "apple_mlx_small_fixture_validation": "failure at scripts/research/generate_f017_v11_measurement_v1.py --check: working tree differs from measurement head: scripts/research/f017_corrected_oracle_primary_wrapper_v11.py (every earlier step of the job passed, including the corrected-oracle numerical requalification v3/v4, the native synthetic family and the plan audit)"
  },
  "cause": "measurement v8 binds the wrapper at f35d3411; commit 5b39a21a (2026-09-03, 'simplify Event 06 to minimum gate path') changed the wrapper (+53/-9 lines); 5b39a21a is an ancestor of the Event 06 immutable source c3526d68, i.e. Event 06 ran with the changed wrapper; no FULL_NATIVE run has passed on the branch since 2026-09-03",
  "independence": "the check measures the V11 result-envelope implementation of the corrected-oracle track; the native executor, its contract validation, the crate tests and the checkpoint-free differentials do not depend on it; repair (append-only v9 measurement) belongs to the F017 planner and was not attempted here"
 },
 "numerical_delta_since_attempt_1": {
  "attempt_1_executor_build_head": "4faa404c4205d172251436781b6d54042e8409f6",
  "runtime_files_changed": [
   "crates/quant/src/extra_ref.rs: decode_iq4_xs_matrix lane order corrected to ggml split low-then-high (e00811df, 2026-08-22, corrected-oracle cycle-2 finding) - a NUMERICAL change affecting the four IQ4_XS tensors blk.8/75/76/77.ffn_down_exps.weight",
   "crates/f017-native/src/model.rs: observer plumbing refactor (same operations and order)",
   "crates/f017-native/src/loader.rs, executor.rs, crates/stream/src/p1_domain.rs: six-shard authority, evidenced v4 lifecycle, receipts, diagnostics",
   "crates/f017-native/src/contract.rs: generation 3 (this round)"
  ],
  "prior_expectation": "attempt 2 is not a deterministic repeat of attempt 1: the IQ4_XS decode differs and the expected token is the corrected 154820; the checkpoint-free evidence removes decoder and graph defects as explanations, so the outcome is genuinely open (154820 = success; anything else = a banked terminal failure whose payoff is the evidenced-v4 diagnostics: 79-layer fingerprints and full logits)"
 },
 "verdict_logic_inspection": {
  "crates/stream/src/p1_domain.rs": "execution compares the produced token with authority.expected_token (line ~1090: 'bounded P1 token mismatch: expected {authority.expected_token}'); the receipt classification uses produced_token != Some(authority.expected_token) -> TOKEN_MISMATCH / TERMINAL_FAILURE_NO_RETRY else EXPECTED_TOKEN_MATCH / COMPLETE_MANDATORY_STOP (line ~1304-1311); the constant stream::EXPECTED_TOKEN (21615) is used only in #[cfg(test)] code (module starts at line 1372)",
  "crates/f017-native/src/bin/bounded_p1.rs": "execute-evidenced-v4 requires authority.attempt_id == contract.one_shot.attempt_id and validates authority/contract/executor/D0/D1/D2/D3.5/synthetic/ledger/manifest/catalog/set bindings; FullNativeP1MathV3 is constructed with authority.expected_token; the contract's one_shot.expected_token (154820) is enforced by validate_static generation 3; the human approval binds the contract sha, and the authority is minted from that contract's one_shot fields, so authority.expected_token == contract.one_shot.expected_token by construction of f017_native_p1_authorization.py authorize"
 },
 "corrected_oracle_provenance": {
  "event_06_source": "immutable c3526d68 (implementation 4b48167f)",
  "wrapper_change_5b39a21a_is_ancestor_of_c3526d68": true,
  "f017_corrected_oracle_primary_numerics_v3.py_sha256": {
   "at_c3526d68": "56f4179a58ff9558e143e79af73f9709e731ca74b6536f346b1a8e1b29e3f3a6",
   "at_readiness": "56f4179a58ff9558e143e79af73f9709e731ca74b6536f346b1a8e1b29e3f3a6"
  },
  "f017_oracle_primary_decoders.py_sha256": {
   "at_c3526d68": "60a4b4e7d973edc41383e20d6d3413d4f658bf4a34dc9132529a6c702b44e11e",
   "at_readiness": "60a4b4e7d973edc41383e20d6d3413d4f658bf4a34dc9132529a6c702b44e11e"
  }
 },
 "one_shot": {
  "attempt_id": "F017-NATIVE-BOUNDED-P1-ATTEMPT-2",
  "prompt_token": 9703,
  "expected_token": 154820,
  "attempts": 1,
  "retries": 0,
  "resume": false,
  "mandatory_stop": true,
  "receipt_schema": "pulsarmlx.f017.native-bounded-p1-execution-receipt/4.0.0",
  "command": "execute-evidenced-v4 MANIFEST CATALOG CHECKPOINT_ROOT AUTHORIZATION STATE_ROOT CONTRACT",
  "forward_evidence_contract": {
   "path": "specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-forward-failure-evidence-v4.json",
   "sha256": "41c46f55369a71a632e30669aa848e2b9ffcc24ff69a8e469e7f8f12d66bbf03"
  },
  "consumption_rule": "the one-shot authority is consumed at durable attempt start; a crash, memory kill or interruption after that point spends the attempt (interruption closeout only, no retry, no resume)",
  "post_failure_scope": "a token other than 154820 is a banked terminal failure under authorization 2; no retry under it; a further attempt would need a new diagnosis, a new contract generation and a new human GO",
  "shard_identity": "MappedShard::open rehashes every shard (SHARD_IDENTITY_REHASH) against the manifest before use; ~222 GB read from the internal SSD is part of the ~2-3 minute run",
  "expected_duration": "~2-3 minutes after durable start (attempt 1: 123.5 s)",
  "memory": ">= 17,179,869,184 bytes available (vm_stat free+inactive+speculative) sampled within 5 s of admission; the legacy resident service is QUIT (SIGTERM, verified exited and memory released), not suspended"
 },
 "operator_procedure_assertions": [
  "checkout of feat/017-rust-native-inference-runtime at the readiness head H* (contains the committed final review), clean, HEAD == origin",
  "the human approval JSON stays outside the repository during authorize (readiness_head = H*)",
  "authorize creates the fresh state root; execute-evidenced-v4 runs once from the same checkout with the pinned environment; no branch push between authorize and execution",
  "after the run: restore the legacy service; bank receipts/terminal and a sanitized public execution-evidence record; commit the approval as evidence"
 ],
 "reviewer_provenance": "final review cycles are performed by a fresh claude-opus-5 Claude Code session spawned as an independent agent with no prior context, instructed to read only the request packet file and use no other tools; the spawn prompt, packet sha256 and verbatim response are banked (D-05)",
 "safety": {
  "live_authorization_created": false,
  "checkpoint_reads_this_preparation": 0,
  "event_06_replayed": false,
  "attempt_1_retried": false,
  "tolerances_changed": false,
  "generation_2_rules_changed": false
 }
}
===== ADMISSION CONTRACT v3 (sha256 7f98404333b0661f42c0e44f0a6c6451282513531a978dd442a98dafbfe94af8) =====
{
  "authorities": {
    "comparison_read_grant": {
      "path": "specs/017-rust-native-inference-runtime/contracts/f017-native-d3-5-comparison-read-grant-v1.json",
      "sha256": "340e91aa3f00c91b0275c052307dba1ab0ebef091b3e07f99e4121a4bc1c788f"
    },
    "cross_branch_authority": {
      "path": "specs/017-rust-native-inference-runtime/contracts/f017-native-domain-cross-branch-authority-v1.json",
      "sha256": "dec44d48faf46d30f3cad6193442eac55a1bd978311d9daa9c1ac28f40308f90"
    },
    "d0": {
      "path": "specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-numeric-acceptance-contract-v2.json",
      "sha256": "cc62cdc7550e3a25f55de783e9eb7c68f6cf03d0eafb944a86dc8a2a60007fb9"
    },
    "d1": {
      "path": "specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-counter-semantics-v1.json",
      "sha256": "f3aab3b065628f96bfe1fab1a045a9af3d2261e2b5d7ef69c1528fb0a7d88246"
    },
    "d2": {
      "path": "specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-accounting-residency-v1.json",
      "sha256": "d2312004f05cafbfd1f1779ccfbbb9e1a0c8c5b4e916aa0601abb04dbefe9c84"
    },
    "d3_5_acceptance": {
      "path": "docs/architecture/reviews/evidence/f017-native-d3-5-numerical-qualification-acceptance-v1.json",
      "sha256": "9d4d29870e8aa67d9ca9ed2702bddd4b9248930204e4f03f05c5f05f2727b163"
    },
    "d3_5_result": {
      "path": "docs/architecture/reviews/evidence/f017-native-d3-5-numerical-grading-result-v1.json",
      "sha256": "472a3085111ed023c3fafafc97600edaba4e6b8dbc0f58d35020561b650fa7e4"
    },
    "execution_architecture": {
      "path": "specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-execution-architecture-v2.json",
      "sha256": "ccb01e8dfeb5432598ded15b99783f186ebb5a03a794f25b70660a202d7a6f39"
    },
    "historical_master_ledger_sha256": "aa98f5cc7f1cfae1eb49a9bc64dbefec1d6ef9ccae1504a1aa8879a8edf22e3e",
    "historical_master_terminal_value": 175,
    "retention_reuse_grant": {
      "path": "specs/017-rust-native-inference-runtime/contracts/f017-native-representative-retention-reuse-grant-v1.json",
      "sha256": "b22a11c829000fd9d333a62a662dd1b274a9a710aa4ccd6afb8f7df789dc9b28"
    },
    "runtime_provenance": {
      "path": "specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-runtime-provenance-v1.json",
      "sha256": "a614377d4faacd501f34ef8dedc1754e432f3ed13630233208f32b5e19819b6d"
    },
    "synthetic_full_graph_result": {
      "path": "docs/architecture/reviews/evidence/f017-native-full-model-synthetic-qualification-v3.json",
      "sha256": "c1b012a40a8ffecdb3912d343b193e30d7c47b130fc255496eb00a114af32360"
    }
  },
  "branch": "feat/017-rust-native-inference-runtime",
  "checkpoint": {
    "catalog": {
      "path": "docs/research/glm52/raw/f016-c01-catalog-0001.json",
      "sha256": "135500cc46b65a877027b597bf20e0c7bb613802e5137c48204e7ab6e7a7ff19"
    },
    "checkpoint_set_sha256": "d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee",
    "fallback": "PROHIBITED",
    "manifest": {
      "path": "docs/validation/glm52-checkpoint.json",
      "sha256": "34b65d586c86d24ee10f3a2ed55491fb3a5a6b9ddbaf893bf9e0ab962c96cf8f"
    },
    "root_environment": "PULSARMLX_GLM_GGUF",
    "shards": [
      {
        "filename": "GLM-5.2-UD-IQ2_XXS-00001-of-00006.gguf",
        "sha256": "7bf96eeabbe887e58b6c44364962731ddc9dc5bf46fec8d097c1dff64bea4a18",
        "size_bytes": 9423744
      },
      {
        "filename": "GLM-5.2-UD-IQ2_XXS-00002-of-00006.gguf",
        "sha256": "d94adaa58ddd5abbcf2514192958084416b1aa36bd4d21409028a164341bac36",
        "size_bytes": 49105028960
      },
      {
        "filename": "GLM-5.2-UD-IQ2_XXS-00003-of-00006.gguf",
        "sha256": "1cd0b1a3d9d939ce5a184c548f1b1c42edafaf1856cb0d7e586a2884a366256b",
        "size_bytes": 49143176640
      },
      {
        "filename": "GLM-5.2-UD-IQ2_XXS-00004-of-00006.gguf",
        "sha256": "10f3965db697a46ba66494475045af183c1bcaf639984160930c91a377816d3e",
        "size_bytes": 49143176640
      },
      {
        "filename": "GLM-5.2-UD-IQ2_XXS-00005-of-00006.gguf",
        "sha256": "40d7d4524ff07e0f9af494fb13130dc7090184800cc5af0a1563188b076af50d",
        "size_bytes": 49143176640
      },
      {
        "filename": "GLM-5.2-UD-IQ2_XXS-00006-of-00006.gguf",
        "sha256": "eeceb9084350e64be8eebcd1f19ab14bbbb6b40132c86d77ffc65e72f425044d",
        "size_bytes": 41914650304
      }
    ]
  },
  "code_manifest": [
    {
      "path": "Cargo.lock",
      "sha256": "0fc37aff9036a4c6a46ae396a1f9f0355412f3c447e44e0f070b5150c19c01ea"
    },
    {
      "path": "crates/f017-native/Cargo.toml",
      "sha256": "a164ecb0aeeb772be03968553359b1f86ed8041662a8620b92a8bd3764781adc"
    },
    {
      "path": "crates/f017-native/build.rs",
      "sha256": "992c2227dafe51466a4f40898f2138fe3c26101d219acaa122a5b68b97ef859a"
    },
    {
      "path": "crates/f017-native/src/lib.rs",
      "sha256": "042001c80c92946ec832b9c666e2aae5df8aefc66dc9a83645a3a54e451a8fa7"
    },
    {
      "path": "crates/f017-native/src/json.rs",
      "sha256": "99b3e6b447365bce16d750dfedfdc8fddb8f65782299e37e25fb9ec425fca57e"
    },
    {
      "path": "crates/f017-native/src/contract.rs",
      "sha256": "b3b18438427fecdd7cff86ae357475d2b06d00583ec4a9f0ac1e63279edda1f3"
    },
    {
      "path": "crates/f017-native/src/executor.rs",
      "sha256": "461c579c394c037897ff55817e269c12fa8cd06c665996c10f959b0e9ef69010"
    },
    {
      "path": "crates/f017-native/src/loader.rs",
      "sha256": "7de4127864435ff6b217a9556b5ac4f108cafa995f7b196337e2cc8f773bcbd7"
    },
    {
      "path": "crates/f017-native/src/model.rs",
      "sha256": "6dbd2b5a94107e6055c6143dc59c8af220980f98dfa43cb1fdc0bd91ff55b8ac"
    },
    {
      "path": "crates/f017-native/src/bin/bounded_p1.rs",
      "sha256": "3f8f11212f6b66d2af365b089708eb153d10cc3d6446ed9cebe02bec71617f74"
    },
    {
      "path": "crates/gguf/src/lib.rs",
      "sha256": "4567fd49bb39564b252547025f297ffe502325e7e74cbd79d9d42c328af0c2b9"
    },
    {
      "path": "crates/quant/build.rs",
      "sha256": "d3049253b6c16419468346d86ea1e0a3ace5bb3a1154f430a833c5300c3f60da"
    },
    {
      "path": "crates/quant/src/lib.rs",
      "sha256": "a582fc2b4fdfea1d54beb67937cecb13db55273d0bcede6a2d37272594fbe3ff"
    },
    {
      "path": "crates/quant/src/cpu_dot.rs",
      "sha256": "64e5385a9a6e0690ba6841809ea268b06ce9f52b1ad63b2dde50b066bdf81d7d"
    },
    {
      "path": "crates/quant/src/cpu_dot_tables.rs",
      "sha256": "8dc16e47d422a5bf52ba6efb3d754e70af6ae43c88179d59bf6977711003f85b"
    },
    {
      "path": "crates/quant/src/extra_ref.rs",
      "sha256": "2078e8dc61e538ceefa0ed470cf583da7ed4fc8c68466df2c7ebbe3a015165d2"
    },
    {
      "path": "crates/quant/src/iq.rs",
      "sha256": "43a79a985efb881a4a5b3caa918b554b37733c8ea15367b40283bcd33a16508c"
    },
    {
      "path": "crates/quant/src/iq_ref.rs",
      "sha256": "c1606b39afff3a56334c8f56358c711dcbcb5f2df904d4e86612fd2a09b19161"
    },
    {
      "path": "crates/quant/src/q6_k_ref.rs",
      "sha256": "a4d308ef1aa874865e668002a8911d8247247dd490e301018f730aeb06ab35fd"
    },
    {
      "path": "crates/stream/build.rs",
      "sha256": "f178e8615267322b3552226f06e28a61a4306c1c033768f9396662ce63280d2b"
    },
    {
      "path": "crates/stream/src/lib.rs",
      "sha256": "54124b640b8b650984a692a82c2ca521dd7962a484476d7fc78a41347f7565ac"
    },
    {
      "path": "crates/stream/src/p1_domain.rs",
      "sha256": "85e5254796a2ff52615a41fe57cf6023f536c5cbb09a45e802443c85a1bbe3c7"
    },
    {
      "path": "crates/stream/src/apple_mlx_bridge.rs",
      "sha256": "08ca3a7da61da41707d6cf5f50822432eae721ae2912730ef23fe9ddeeed358c"
    },
    {
      "path": "crates/stream/src/apple_mlx_bridge.mm",
      "sha256": "e68b1f1553903c6a06cba6f29947e275f3362d33beaa591326a3c2ccdeda6142"
    },
    {
      "path": "crates/stream/src/apple_mlx_deallocation_observer.mm",
      "sha256": "f0dab44abaf6897d7924149a17fb5e4f335f4f51ae945282e4081ef0b862663c"
    },
    {
      "path": "scripts/research/f017_native_p1_authorization.py",
      "sha256": "46bba0261ba6568ed76e0d8ffbd4c3061b95f3f411a41a7af85e58578b33af87"
    }
  ],
  "corrected_oracle_binding": {
    "path": "specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-attempt-02-corrected-oracle-binding-v1.json",
    "sha256": "c582e3b4ae924fcaafad67f4e997f5d5e6a8dba1320ef395f6ba6499dd5a3512"
  },
  "execution_code_head": "5e32d68faa7b10168b9bb7f5d4fce6ebf212b737",
  "executor": {
    "path": "specs/017-rust-native-inference-runtime/bin/f017-native-bounded-p1-v2",
    "sha256": "91e50a0bb84a30450f9189da2122b84e1790649c1361ed90cea001ca537f52f0"
  },
  "live_authorization_present": false,
  "normal_validation_can_authorize": false,
  "one_shot": {
    "attempt_id": "F017-NATIVE-BOUNDED-P1-ATTEMPT-2",
    "attempts": 1,
    "expected_token": 154820,
    "generated_token_limit": 1,
    "initial_kv_state": "EMPTY_CLEAN_PROCESS",
    "mandatory_stop": true,
    "prompt_token": 9703,
    "receipt_schema": "pulsarmlx.f017.native-bounded-p1-execution-receipt/4.0.0",
    "resume": false,
    "retries": 0,
    "sequence_position": 0
  },
  "runtime": {
    "architecture": "arm64",
    "build_profile": "release",
    "dylibs": [
      {
        "path": "/opt/homebrew/opt/pulsarmlx-f017-native-mlx-0.31.2/lib/libmlx.dylib",
        "sha256": "ad9b597b08e28b43c9b9791d2948fea601c76fe0b4a06d08cceeb4ad7b15e20d"
      },
      {
        "path": "/opt/homebrew/opt/pulsarmlx-f017-native-mlx-0.31.2/lib/libmlxc.dylib",
        "sha256": "3401e4f91a1d3f9b02c9bd1e728a10753f256d90bb1b40aebcaf8225592bee1a"
      }
    ],
    "environment": {
      "MLX_C_PREFIX": "/opt/homebrew/opt/pulsarmlx-f017-native-mlx-0.31.2",
      "MLX_PREFIX": "/opt/homebrew/opt/pulsarmlx-f017-native-mlx-0.31.2",
      "OMP_NUM_THREADS": "1",
      "PULSAR_REQUIRE_NATIVE_MLX": "1",
      "RAYON_NUM_THREADS": "1",
      "VECLIB_MAXIMUM_THREADS": "1"
    },
    "machine_brand": "Apple M1 Ultra",
    "macos_build": "25A354",
    "memory_sample_max_age_seconds": 5,
    "minimum_available_memory_bytes": 17179869184,
    "mlx_c_version": "0.6.0",
    "mlx_version": "0.31.2",
    "rustc_version": "rustc 1.97.1 (8bab26f4f 2026-07-14) (Homebrew)"
  },
  "schema": "pulsarmlx.f017.native-bounded-p1-admission-contract/3.0.0",
  "state_root": "/Users/mhedhli/.local/share/pulsarmlx/f017/native-bounded-p1-v2",
  "status": "PREPARED_HUMAN_GATE_REQUIRED"
}
===== CORRECTED-ORACLE BINDING (sha256 c582e3b4ae924fcaafad67f4e997f5d5e6a8dba1320ef395f6ba6499dd5a3512) =====
{
  "acceptance_mode": "EXACT_EXPECTED_TOKEN_STABLE",
  "attempt_1": {
    "disposition": "TERMINAL_FAILURE_BANKED (observed 17351 vs the defective expected 21615); retry PERMANENTLY_PROHIBITED; attempt 2 is a new attempt under a new authorization, not a retry"
  },
  "attempt_id": "F017-NATIVE-BOUNDED-P1-ATTEMPT-2",
  "checkpoint_free_reconciliation": {
    "m1_ultra_reproduction": [
      "docs/architecture/reviews/evidence/f017-native-decoder-differential-corrected-oracle-v1-m1ultra.json",
      "docs/architecture/reviews/evidence/f017-native-graph-vs-corrected-oracle-differential-v1-m1ultra.json"
    ],
    "path": "docs/architecture/reviews/evidence/f017-native-checkpoint-free-reconciliation-20260920-v1.json",
    "sha256": "f7193decd52081942a50c267754ce614699638c6773c0e818e3e22bf483d484e"
  },
  "corrected_oracle_event": {
    "comparison": {
      "classification": "EXACT_EXPECTED_TOKEN_STABLE",
      "cosine": 0.999999999999954,
      "max_abs": 2.4495741151042694e-06,
      "rmse": 4.947803155886533e-07
    },
    "context": {
      "kv_state": "EMPTY",
      "mask": "ONE_VISIBLE_KEY_CAUSAL",
      "position": 0,
      "prompt_token": 9703,
      "sampling": "NONE_GREEDY_ARGMAX"
    },
    "payload_sha256": {
      "primary_final_hidden_f64le_6144": "dfa83c58c0f2f1eb082f8f7e24ebeed439340e77ae9efc9ce3440a3a22968925",
      "primary_final_normalized_f64le_6144": "d84b16e217acbae8999b995e052d18430547468364db421e4b75e3bb6f2a9868",
      "primary_full_logits_f64le_154880": "cbdc84332715967761774bcf6788ed60c0a662254a4b2599608ab519b80094c8",
      "secondary_final_hidden_f32le_6144": "1ba0f332d4a70447912d70e7d00832aa891b5fc665261892f418b931fc47a882",
      "secondary_final_normalized_f32le_6144": "8ca9a7d33344e124f4e30e79da27301705b430f4ed2833554361cb4af5d5e787",
      "secondary_full_logits_f32le_154880": "3554c3cbed7221b261a685da5f16ffe227bec4582f28ca1ef5aadcfdf8e8edc2"
    },
    "primary_selected_token": 154820,
    "primary_top_1_margin": 3.530997059031304,
    "public_evidence": {
      "commit": "29c55d314a72747b44bd2c1ce93c71ba6ac157b6",
      "path": "docs/architecture/reviews/evidence/f017-event06-v12-sequence43-terminal-success-evidence-v1.json",
      "sha256": "88cedac341b0cc353d9307820aa61eaf6cc5443396477e3feb7da16d06750498"
    },
    "secondary_selected_token": 154820,
    "secondary_top_1_margin": 3.5309972763061523,
    "sequence": 43,
    "source": {
      "immutable_execution_source": "c3526d68b29535465e6117014234352945cdaacb",
      "implementation": "4b48167f9fd02b81ed1c5796022ad70b3c2a61b6"
    },
    "verdict": "EVENT06_SUCCESS_ACCEPTED (planner result acceptance sha256 ca963328dee51a527caeb4bac667819c693005030915918de27ecedfcfc1b601)"
  },
  "expected_token": 154820,
  "forward_evidence_contract": {
    "path": "specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-forward-failure-evidence-v4.json",
    "sha256": "41c46f55369a71a632e30669aa848e2b9ffcc24ff69a8e469e7f8f12d66bbf03"
  },
  "human_go_required": true,
  "live_authorization_created": false,
  "note": "the executor binds the authority's expected_token (154820) at execute-evidenced-v4; the contract's one_shot.expected_token carries the same value; this binding is source-only and mints nothing",
  "schema": "pulsarmlx.f017.native-bounded-p1-attempt-02-corrected-oracle-binding/1.0.0",
  "status": "PREPARED_NOT_AUTHORIZED",
  "template": {
    "path": "specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-attempt-02-template-v1.json",
    "sha256": "07fc9d55976f6d8dc32f547cb0049ba99403beb81c8a7348095f0f5a80d1475c"
  }
}
===== INERT HUMAN-APPROVAL TEMPLATE (sha256 bb70347dd6d44ab1483da08d58bdc968e6f109a946452886058bb40b7e4cb5b2) =====
{
  "attempt_id": "F017-NATIVE-BOUNDED-P1-ATTEMPT-2",
  "authorization_id": "FUTURE_HUMAN_ASSIGNED",
  "branch": "feat/017-rust-native-inference-runtime",
  "contract_sha256": "7f98404333b0661f42c0e44f0a6c6451282513531a978dd442a98dafbfe94af8",
  "decision": "NOT_AUTHORIZED_TEMPLATE",
  "domain_declaration": {
    "path": "docs/architecture/reviews/evidence/f017-native-bounded-p1-execution-domain-final-declaration-v3.json",
    "sha256": "269babfb21e612a50a543bf92973c8d1ddc0643e5b4268cf91153636c3915a6d"
  },
  "final_review": {
    "blocking_count": null,
    "non_blocking_required_count": null,
    "path": "FUTURE_COMMITTED_PATH (claude-opus-5 fresh-session normalized result for attempt 2)",
    "reviewer_model": "claude-opus-5",
    "sha256": "FUTURE_SHA256",
    "verdict": "FUTURE_ACCEPT_OR_REJECT"
  },
  "readiness_head": "FUTURE_ACCEPTED_HEAD (the feat/017-rust-native-inference-runtime head that contains the final review; must equal origin at authorize time)",
  "schema": "pulsarmlx.f017.native-bounded-p1-human-approval/1.0.0",
  "statement": "INERT TEMPLATE; DOES NOT AUTHORIZE EXECUTION"
}
===== CHECKPOINT-FREE RECONCILIATION (sha256 7af5cd9da4d8625c8a890d4a67ad913d5166f0218c41ca80f06b34f4d2ac2c34) =====
{
 "schema": "pulsarmlx.f017.native-checkpoint-free-reconciliation/1.0.0",
 "date": "2026-09-20",
 "work_order": "WK26-GLM52-20260920-v1 (W3)",
 "source_head_before": "c23e58ec87c7e73a23cf37ac64aa4dee6c45896f",
 "host": "MacBook Pro M2 Max (arm64), macOS, mlx-c 0.6.0_2 + mlx 0.31.2 (Homebrew), rustc 1.95.0",
 "producer_binaries_sha256": {
  "f017-native-decoder-differential": "29228130954fd47a585b4af8f27803a8e436d31faa45ca9385dcad093ca5c314",
  "synthetic_differential (built as f017-native-synthetic-differential during this session; same source)": "2696d37758c344b02faa5c016ffbecdd145cf18e13af92aeae5e358040bea84f"
 },
 "n1_decoder_differential": {
  "oracle": "scripts/research/f017_oracle_primary_decoders.py (Event 06 corrected oracle, independent scalar binary64 decoders)",
  "producer": "crates/f017-native loader decode_packed_matrix_for_qualification (exact P1 dispatch: quant::decode_*_matrix, cpu_dot::dequant_q4_k/q5_k)",
  "formats": [
   "F32",
   "Q8_0",
   "Q5_K",
   "IQ2_XXS",
   "Q6_K",
   "IQ3_XXS",
   "IQ4_XS",
   "Q4_K",
   "IQ2_S",
   "Q2_K",
   "Q3_K"
  ],
  "cases": "33 per seed (3 geometries per format), seeds 20260920 and 7",
  "result": "every value bit-identical after rounding the oracle's binary64 to f32 (0 ULP; 117,806 values per seed); harness negative control (two oracle lanes swapped) flagged",
  "evidence": [
   "docs/architecture/reviews/evidence/f017-native-decoder-differential-corrected-oracle-v1.json",
   "docs/architecture/reviews/evidence/f017-native-decoder-differential-corrected-oracle-v1-seed7.json"
  ]
 },
 "n3_graph_differential": {
  "oracle": "scripts/research/f017_corrected_oracle_primary_numerics_v3.py _execute_graph (binary64, fixed order)",
  "producer": "synthetic_differential (auto-discovered bin of crates/f017-native, the same producer CI qualifies) (production orchestration execute_one_token_observed through the MLX bridge, TENSOR_MATH_ONLY synthetic source)",
  "fixtures": "qualify_f017_native_synthetic_family_v1.build seeds 17018-17023",
  "result": "6/6 PASS: argmax equal, per-layer expert selection identical, logits max abs 1.6e-7..1.7e-6 (thresholds: max abs 6.5e-3, rmse 3.5e-3, cosine >= 1-1.9e-9)",
  "evidence": "docs/architecture/reviews/evidence/f017-native-graph-vs-corrected-oracle-differential-v1.json"
 },
 "loader_range_arithmetic": "by inspection identical between crates/f017-native loader encoded_range (row_bytes(columns) x rows, expert x matrix_bytes) and the oracle target source _raw (columns//block_values*block_bytes x dims[1], expert x full_matrix_bytes); per-format row sizes agree (N1 byte-length checks)",
 "conclusion": "checkpoint-free reconciliation of the native runtime with the corrected oracle PASSES on decoders and graph; the real-checkpoint divergence of native attempt 1 (observed 17351 vs corrected oracle 154820, attempt-1 expected 21615 from the defective F016 family) is NOT explained by decoder or graph defects reproducible without the checkpoint; discrimination requires native bounded P1 attempt 2 on the real checkpoint (human-gated), or a full-geometry synthetic checkpoint (not feasible: validate_plan binds the real 1809-tensor census and 6-shard geometry, ~222 GB)",
 "not_claimed": [
  "real-checkpoint agreement",
  "native P1 readiness beyond the checkpoint-free scope",
  "any change to frozen contracts or tolerances"
 ]
}
===== STATIC VALIDATION NEGATIVE CONTROLS =====
{
 "schema": "pulsarmlx.f017.native-bounded-p1-contract-v3-static-validation/1.0.0",
 "date": "2026-09-20",
 "executor": "f017-native-bounded-p1 built from 5e32d68f (MacBook build for the controls; the committed Studio-built binary is validated on the M1 Ultra separately)",
 "contract": "specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-admission-contract-v3.json",
 "v3_accepted": true,
 "v2_still_accepted": true,
 "negative_controls": [
  {
   "control": "v3 with attempt-1 token 21615",
   "rejected": true,
   "reason": "one-shot authority mismatch"
  },
  {
   "control": "v3 with attempt id 1",
   "rejected": true,
   "reason": "one-shot authority mismatch"
  },
  {
   "control": "v3 with v2 receipt schema",
   "rejected": true,
   "reason": "one-shot authority mismatch"
  },
  {
   "control": "v3 without binding",
   "rejected": true,
   "reason": "contract root authority mismatch"
  },
  {
   "control": "v2 schema carrying attempt-2 fields",
   "rejected": true,
   "reason": "contract root authority mismatch"
  },
  {
   "control": "v3 with wrong binding sha",
   "rejected": true,
   "reason": "repository binding mismatch specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-attempt-02-corrected-oracle-binding-v1.json"
  },
  {
   "control": "v3 claiming live authorization",
   "rejected": true,
   "reason": "contract root authority mismatch"
  }
 ],
 "all_rejected": true
}
===== CYCLE-02 REVIEW RESPONSE (verbatim) =====
{"nonce":"0092e4fb2b3ea0177c5b07e921b939ff","readiness_head":"8456f2060e60446a7411e255d062b0ebc1115087","verdict":"REJECT","blocking_findings":[{"id":"B-01","body":"The declaration the human approval will bind lists 'exact-head CI success for that head' as a precondition of GO, and at the readiness head that precondition is not pending but failed: FULL_NATIVE run 35509978669 fails the MLX small-fixture job at generate_f017_v11_measurement_v1.py --check because scripts/research/f017_corrected_oracle_primary_wrapper_v11.py drifted from the measurement-v8 binding (f35d3411) at commit 5b39a21a. Recording a GO against a declaration whose own stated precondition is known-failed is a governance contradiction regardless of whether the failing check touches the native executor. The addendum's argument that the drift is pre-existing and planner-owned may be correct, but that scoping decision has to live in the bound declaration, not in a review packet. The drifted file is also the corrected oracle's primary wrapper, i.e. the lineage of the expected token 154820 itself, so an unreconciled binding there cannot be waved through silently.","evidence":"Declaration v2 remaining_before_go[1] 'exact-head CI success for that head'; cycle-02 addendum: 'fails: working tree differs from measurement head: scripts/research/f017_corrected_oracle_primary_wrapper_v11.py ... no FULL_NATIVE run has passed on the branch since'.","remedy":"Either (a) re-bind the V11 measurement to the accepted Event 06 path so FULL_NATIVE passes at a new head, or (b) issue declaration v3 (new file, append-only) that replaces the CI precondition with an explicit, narrowed gate (classification + Apple Silicon workspace baseline SUCCESS at the exact head) and records the measurement-check failure, its cause (5b39a21a vs f35d3411), and why it is independent of the executor, contract validation and the differentials. In both cases the readiness head changes; re-run validate-contract and machine preflight there and submit a cycle-03 packet."},{"id":"B-02","body":"The material this review was told to review verbatim is not the material at the readiness head. After the cycle-01 packet was assembled, Cargo.toml changed (30ca81dc), contract v3 was re-bound to a new sha (7f984043..., given only as an 8-hex-character prefix), and 'declaration v2 and template carry the new contract sha', meaning a versioned declaration was mutated in place. The inline declaration v2 still shows contract sha 389580fa..., the inline contract shows the pre-30ca81dc Cargo.toml sha, and the inline diff shows a Cargo.toml that no longer matches the head. A banked 'final independent review with exact request/response' bound to a declaration and contract the reviewer never saw verbatim, with a truncated sha, does not close the binding chain the approval schema relies on.","evidence":"Cycle-02 addendum: 'd690a967 (contract v3 code-manifest re-bound after the Cargo.toml change; declaration v2 and template carry the new contract sha)'; 'Contract v3 sha256 7f984043...'; inline DOMAIN DECLARATION v2 admission_contract.sha256 = 389580fa7ba5ca0f8a8d531aa522431bae9b47db413a02fba69b15e2132356f4; inline SOURCE DIFF Cargo.toml declares f017-native-synthetic-differential, which 30ca81dc restored to the auto-discovered name.","remedy":"Cycle-03 packet must inline, verbatim, the declaration (as a new version, not an in-place edit of v2), the admission contract v3 as committed at the readiness head, the corrected-oracle binding, and the full 64-hex sha256 of each; the readiness head must be the commit that contains exactly those files; the review response is then bound to those shas."}],"non_blocking_required_findings":[{"id":"R-01","body":"The GO record must be an informed one. Nothing in the packet states what, if anything, changed in the native numerics path (loader, model, executor, quant, stream, MLX bridge) between the attempt-1 executor and f017-native-bounded-p1-v2; the visible source diff c23e58ec..50a66db0 touches only contract.rs and new differential bins. If the numerics are unchanged, the run is deterministic (greedy, empty KV, single-threaded env) and the most probable outcome is observed 17351 again, i.e. a banked terminal failure whose real payoff is the evidenced-v4 forward evidence, not a success. The human must also be told that the one-shot authority is consumed at durable start (a crash or jetsam after that point spends the attempt), and what a failure at 154820 permanently prohibits afterwards.","evidence":"H01 ledger: attempt 1 observed 17351 vs frozen 21615; corrected oracle 154820; reconciliation conclusion: the divergence 'is NOT explained by decoder or graph defects reproducible without the checkpoint'; declaration one_shot.expected_duration 'after durable start'; binding attempt_1.disposition 'retry PERMANENTLY_PROHIBITED'.","remedy":"Add to the readiness note (and the approval body) a short statement of the executor numerical delta since attempt 1 (or 'none'), the resulting prior expectation, the durable-start consumption rule, and the post-failure prohibition scope; the human's plain-words GO should be re-confirmed against that statement."},{"id":"R-02","body":"The stream crate still exports EXPECTED_TOKEN (21615); the packet asserts the executor binds the authority's expected_token at execute-evidenced-v4, but no inline material shows that the receipt's success/failure classification and the mandatory-stop verdict use the authority/contract token rather than stream::EXPECTED_TOKEN, nor that the executor cross-checks authority.expected_token == contract.one_shot.expected_token == 154820 and authority.attempt_id == contract.one_shot.attempt_id. The negative controls exercise validate_static only, not execution-time classification.","evidence":"contract.rs test 'assert_ne!(CORRECTED_EXPECTED_TOKEN, stream::EXPECTED_TOKEN)'; binding note 'the executor binds the authority's expected_token (154820) at execute-evidenced-v4'; STATIC VALIDATION NEGATIVE CONTROLS cover contract fields only.","remedy":"By inspection (no code change), enumerate every use of stream::EXPECTED_TOKEN and every comparison producing the receipt verdict in bounded_p1.rs / p1_domain.rs / executor.rs, confirm the verdict and stop logic use the authority-bound token and that the authority/contract cross-check exists, and record the finding with file:line in the readiness note. If any path uses 21615 or the cross-check is absent, that is a code change and a new head/review."},{"id":"R-03","body":"The provenance of 154820 relative to the wrapper drift is unstated: the packet gives Event 06 sequence 43 immutable_execution_source c3526d68 and implementation 4b48167f, but not whether those include 5b39a21a's change to f017_corrected_oracle_primary_wrapper_v11.py, nor whether f017_corrected_oracle_primary_numerics_v3._execute_graph used by the N3 graph differential is byte-identical to the module that produced the Event 06 payloads.","evidence":"Corrected-oracle binding source {c3526d68, 4b48167f}; addendum 'commit 5b39a21a (2026-09-03 ...) changed it'; reconciliation n3_graph_differential.oracle 'f017_corrected_oracle_primary_numerics_v3.py _execute_graph'.","remedy":"Record in the readiness note: the ancestry relation of c3526d68/4b48167f to 5b39a21a, that the wrapper change is gate-path only (or otherwise), and the sha256 of f017_corrected_oracle_primary_numerics_v3.py at Event 06 vs at the readiness head."}],"defense_in_depth_findings":[{"id":"D-01","body":"execution_code_head (5e32d68f, the executor's build source) and the code_manifest tree (re-bound at d690a967 after the Cargo.toml change) now differ; the difference is bin declarations only, but the executor-sha-to-manifest link is no longer exact by construction.","evidence":"Addendum: 'contract v3 code-manifest re-bound after the Cargo.toml change ... executor unchanged'; contract execution_code_head 5e32d68f.","remedy":"Rebuild f017-native-bounded-p1 in release on the M1 Ultra at the readiness head with the pinned keg and compare to 91e50a0b...; if identical, record it; if not, rebind. Document execution_code_head semantics as 'build-source head' distinct from the manifest tree."},{"id":"D-02","body":"Branch/head race: the approval commit will move HEAD past the readiness head, pushing it will re-trigger the failing FULL_NATIVE run, and the work branch remains a fast-forward source. Nothing inline shows the authorize step pins HEAD to 'approval commit whose parent is the readiness head'.","evidence":"Declaration prepared_on_branch; remaining_before_go[3] 'then ... authorize mints the one-shot authority'.","remedy":"Have the authorize step assert HEAD == approval commit, HEAD^ == readiness head, clean tree, equal to origin/feat/017-rust-native-inference-runtime; do not touch the branch between approval push and execution regardless of CI status."},{"id":"D-03","body":"'Pause' of the legacy resident service is ambiguous; a SIGSTOP'd process keeps its memory and any Metal/unified-memory allocations resident, which the vm_stat gate would reflect but which still competes with the native run.","evidence":"Declaration one_shot.memory; addendum 'legacy resident service idle and will be paused before execution'.","remedy":"Quit the service rather than stopping it, take the vm_stat sample within 5 s of admission, run under caffeinate, and record the sample."},{"id":"D-04","body":"Contract binds six shard sha256s but the ~2-3 minute duration and 0 checkpoint reads at plan-only imply shard hashes are not recomputed at execution; the hard-linked directory's integrity therefore rests on a prior census.","evidence":"Contract checkpoint.shards; declaration plan_only '0 checkpoint reads'; expected_duration '~2-3 minutes'.","remedy":"State whether execute-evidenced-v4 verifies shard sha256s; if not, record the last full hash census of the hard-linked directory and stat (inode, size, mtime) immediately before execution."},{"id":"D-05","body":"Reviewer provenance: this reviewer was spawned as a subagent by the preparing session after the headless CLI was found not logged in, and read the packet through a single file-read tool call rather than 'no tools'.","evidence":"Addendum 'Reviewer availability' paragraph; this review's own conduct.","remedy":"Bank the exact spawn prompt, the packet path and its sha256, and this response verbatim; note the single-file-read deviation from 'no tools' in the banked record."}],"adversarial_cases_considered":31,"rationale":"No blocking technical defect was found in the inline substance: generation-3 validation adds a closed schema map, keeps the generation-2 tuple (attempt 1, 21615, v2 receipt) intact, requires a sha-bound corrected-oracle document whose token, attempt id, mode and both selected tokens are checked against a compiled constant, and every negative control is rejected; the corrected token 154820 is well supported (primary/secondary agree, 3.53 top-1 margin, pinned payload hashes, public evidence commit) and attempt 2 is a legitimately new question, not a disguised retry; the checkpoint-free reconciliation removes cheap explanations for attempt 1 but proves nothing about real geometry, loader byte ranges (by inspection only) or MLX kernels at scale. The REJECT is on governance completeness, not on the executor: the declaration to be bound states a CI-success precondition that is failed at the readiness head, and the artifacts at that head (contract v3, declaration, Cargo.toml) differ from what this review was given verbatim, with the new contract sha truncated. Both are fixable in one further cycle at a new head; with B-01 and B-02 closed and R-01..R-03 satisfied, an ACCEPT_FOR_SINGLE_BOUNDED_M1_ULTRA_P1 verdict would be reachable. The human's already-expressed GO was not treated as evidence."}

===== crates/f017-native/src/contract.rs at the readiness head (the generation-3 validator) =====
//! Exact static and machine-local admission contract for one future P1.
//! Static validation never opens checkpoint shards and cannot mint authority.

use crate::loader::{load_plan_only, ShardIdentity};
use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fs::{self, File};
use std::io::Read;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::process::Command;

pub const CONTRACT_SCHEMA: &str = "pulsarmlx.f017.native-bounded-p1-admission-contract/2.0.0";
/// Generation 3 (attempt 2): identical census, machine, checkpoint and
/// authority rules as generation 2, with the one-shot bound to the corrected
/// oracle's expected token and the evidenced v4 receipt. Generation 2 stays
/// exactly as frozen for attempt 1; a generation-3 contract must additionally
/// bind the corrected-oracle binding document.
pub const CONTRACT_SCHEMA_V3: &str = "pulsarmlx.f017.native-bounded-p1-admission-contract/3.0.0";
pub const ATTEMPT_2_ID: &str = "F017-NATIVE-BOUNDED-P1-ATTEMPT-2";
/// Event 06 (sequence 43) corrected full-checkpoint oracle result for prompt
/// 9703 at position 0: primary and secondary both select 154820.
pub const CORRECTED_EXPECTED_TOKEN: u32 = 154_820;
pub const MINIMUM_AVAILABLE_MEMORY_BYTES: u64 = 17_179_869_184;

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FileBinding {
    pub path: String,
    pub sha256: String,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AuthorityBindings {
    pub cross_branch_authority: FileBinding,
    pub execution_architecture: FileBinding,
    pub runtime_provenance: FileBinding,
    pub d0: FileBinding,
    pub d1: FileBinding,
    pub d2: FileBinding,
    pub retention_reuse_grant: FileBinding,
    pub comparison_read_grant: FileBinding,
    pub d3_5_result: FileBinding,
    pub d3_5_acceptance: FileBinding,
    pub synthetic_full_graph_result: FileBinding,
    pub historical_master_ledger_sha256: String,
    pub historical_master_terminal_value: u64,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CheckpointBinding {
    pub root_environment: String,
    pub manifest: FileBinding,
    pub catalog: FileBinding,
    pub checkpoint_set_sha256: String,
    pub fallback: String,
    pub shards: Vec<ShardIdentity>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RuntimeBinding {
    pub machine_brand: String,
    pub architecture: String,
    pub macos_build: String,
    pub mlx_version: String,
    pub mlx_c_version: String,
    pub rustc_version: String,
    pub build_profile: String,
    pub minimum_available_memory_bytes: u64,
    pub memory_sample_max_age_seconds: u64,
    pub dylibs: Vec<FileBinding>,
    pub environment: BTreeMap<String, String>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct OneShotBinding {
    pub attempt_id: String,
    pub prompt_token: u32,
    pub expected_token: u32,
    pub attempts: u32,
    pub retries: u32,
    pub resume: bool,
    pub mandatory_stop: bool,
    pub generated_token_limit: u32,
    pub sequence_position: u32,
    pub initial_kv_state: String,
    pub receipt_schema: String,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RealP1Contract {
    pub schema: String,
    /// Generation 3 only: the corrected-oracle binding document (attempt 2).
    #[serde(default)]
    pub corrected_oracle_binding: Option<FileBinding>,
    pub status: String,
    pub branch: String,
    pub execution_code_head: String,
    pub executor: FileBinding,
    pub code_manifest: Vec<FileBinding>,
    pub authorities: AuthorityBindings,
    pub checkpoint: CheckpointBinding,
    pub runtime: RuntimeBinding,
    pub one_shot: OneShotBinding,
    pub state_root: String,
    pub live_authorization_present: bool,
    pub normal_validation_can_authorize: bool,
}

pub fn sha256(path: &Path) -> Result<String, String> {
    let mut file = File::open(path).map_err(|e| e.to_string())?;
    let mut digest = Sha256::new();
    let mut buffer = [0_u8; 1024 * 1024];
    loop {
        let count = file.read(&mut buffer).map_err(|e| e.to_string())?;
        if count == 0 {
            break;
        }
        digest.update(&buffer[..count]);
    }
    Ok(format!("{:x}", digest.finalize()))
}

pub fn load(path: &Path) -> Result<(RealP1Contract, String), String> {
    let raw = fs::read(path).map_err(|e| e.to_string())?;
    let contract = crate::json::parse_json_no_duplicates(&raw)?;
    Ok((contract, format!("{:x}", Sha256::digest(raw))))
}

fn repo_path(root: &Path, binding: &FileBinding) -> Result<PathBuf, String> {
    let relative = Path::new(&binding.path);
    if relative.is_absolute()
        || relative
            .components()
            .any(|part| matches!(part, std::path::Component::ParentDir))
    {
        return Err("unsafe repository binding path".into());
    }
    let path = root.join(relative);
    let canonical_root = root.canonicalize().map_err(|e| e.to_string())?;
    let canonical = path.canonicalize().map_err(|e| e.to_string())?;
    if !canonical.starts_with(&canonical_root)
        || fs::symlink_metadata(&path)
            .map_err(|e| e.to_string())?
            .file_type()
            .is_symlink()
        || sha256(&path)? != binding.sha256
    {
        return Err(format!("repository binding mismatch {}", binding.path));
    }
    Ok(path)
}

/// Contract generation by schema: 2 = attempt 1 (frozen), 3 = attempt 2.
pub fn contract_generation(schema: &str) -> Option<u8> {
    match schema {
        CONTRACT_SCHEMA => Some(2),
        CONTRACT_SCHEMA_V3 => Some(3),
        _ => None,
    }
}

pub fn validate_static(contract: &RealP1Contract, repo_root: &Path) -> Result<(), String> {
    let generation = contract_generation(&contract.schema).ok_or("contract root authority mismatch")?;
    if (generation == 2) != contract.corrected_oracle_binding.is_none()
        || contract.status != "PREPARED_HUMAN_GATE_REQUIRED"
        || contract.branch != "feat/017-rust-native-inference-runtime"
        || contract.execution_code_head.len() != 40
        || contract.live_authorization_present
        || contract.normal_validation_can_authorize
        || contract.authorities.historical_master_ledger_sha256
            != "aa98f5cc7f1cfae1eb49a9bc64dbefec1d6ef9ccae1504a1aa8879a8edf22e3e"
        || contract.authorities.historical_master_terminal_value != 175
    {
        return Err("contract root authority mismatch".into());
    }
    for binding in contract.code_manifest.iter().chain([
        &contract.executor,
        &contract.authorities.cross_branch_authority,
        &contract.authorities.execution_architecture,
        &contract.authorities.runtime_provenance,
        &contract.authorities.d0,
        &contract.authorities.d1,
        &contract.authorities.d2,
        &contract.authorities.retention_reuse_grant,
        &contract.authorities.comparison_read_grant,
        &contract.authorities.d3_5_result,
        &contract.authorities.d3_5_acceptance,
        &contract.authorities.synthetic_full_graph_result,
        &contract.checkpoint.manifest,
        &contract.checkpoint.catalog,
    ]) {
        repo_path(repo_root, binding)?;
    }
    let expected_code_manifest = [
        "Cargo.lock",
        "crates/f017-native/Cargo.toml",
        "crates/f017-native/build.rs",
        "crates/f017-native/src/lib.rs",
        "crates/f017-native/src/json.rs",
        "crates/f017-native/src/contract.rs",
        "crates/f017-native/src/executor.rs",
        "crates/f017-native/src/loader.rs",
        "crates/f017-native/src/model.rs",
        "crates/f017-native/src/bin/bounded_p1.rs",
        "crates/gguf/src/lib.rs",
        "crates/quant/build.rs",
        "crates/quant/src/lib.rs",
        "crates/quant/src/cpu_dot.rs",
        "crates/quant/src/cpu_dot_tables.rs",
        "crates/quant/src/extra_ref.rs",
        "crates/quant/src/iq.rs",
        "crates/quant/src/iq_ref.rs",
        "crates/quant/src/q6_k_ref.rs",
        "crates/stream/build.rs",
        "crates/stream/src/lib.rs",
        "crates/stream/src/p1_domain.rs",
        "crates/stream/src/apple_mlx_bridge.rs",
        "crates/stream/src/apple_mlx_bridge.mm",
        "crates/stream/src/apple_mlx_deallocation_observer.mm",
        "scripts/research/f017_native_p1_authorization.py",
    ]
    .into_iter()
    .map(str::to_owned)
    .collect::<BTreeSet<_>>();
    let actual_code_manifest = contract
        .code_manifest
        .iter()
        .map(|binding| binding.path.clone())
        .collect::<BTreeSet<_>>();
    if actual_code_manifest.len() != contract.code_manifest.len()
        || actual_code_manifest != expected_code_manifest
    {
        return Err("execution code manifest census mismatch".into());
    }
    let executor = repo_path(repo_root, &contract.executor)?;
    let executor_metadata = fs::metadata(&executor).map_err(|e| e.to_string())?;
    if !executor_metadata.is_file() || executor_metadata.permissions().mode() & 0o111 == 0 {
        return Err("bound executor is not a regular executable".into());
    }
    let (manifest, _catalog) = load_plan_only(
        &repo_root.join(&contract.checkpoint.manifest.path),
        &repo_root.join(&contract.checkpoint.catalog.path),
    )?;
    if contract.checkpoint.root_environment != "PULSARMLX_GLM_GGUF"
        || contract.checkpoint.fallback != "PROHIBITED"
        || contract.checkpoint.checkpoint_set_sha256 != manifest.checkpoint_set_sha256
        || contract.checkpoint.shards.len() != 6
        || contract
            .checkpoint
            .shards
            .iter()
            .zip(&manifest.files)
            .any(|(a, b)| {
                a.filename != b.filename || a.sha256 != b.sha256 || a.size_bytes != b.size_bytes
            })
    {
        return Err("checkpoint authority mismatch".into());
    }
    let one = &contract.one_shot;
    let (attempt_id, expected_token, receipt_schema) = if generation == 2 {
        ("F017-NATIVE-BOUNDED-P1-ATTEMPT-1", 21615_u32, stream::RECEIPT_SCHEMA)
    } else {
        (ATTEMPT_2_ID, CORRECTED_EXPECTED_TOKEN, stream::EVIDENCED_RECEIPT_SCHEMA)
    };
    if generation == 3 {
        let binding = contract
            .corrected_oracle_binding
            .as_ref()
            .ok_or("corrected oracle binding missing")?;
        let path = repo_path(repo_root, binding)?;
        let document: serde_json::Value = crate::json::parse_json_no_duplicates(
            &fs::read(&path).map_err(|e| e.to_string())?,
        )?;
        if document.get("attempt_id").and_then(|v| v.as_str()) != Some(ATTEMPT_2_ID)
            || document.get("expected_token").and_then(|v| v.as_u64())
                != Some(u64::from(CORRECTED_EXPECTED_TOKEN))
            || document.get("acceptance_mode").and_then(|v| v.as_str())
                != Some("EXACT_EXPECTED_TOKEN_STABLE")
            || document.get("live_authorization_created").and_then(|v| v.as_bool()) != Some(false)
            || document
                .pointer("/corrected_oracle_event/primary_selected_token")
                .and_then(|v| v.as_u64())
                != Some(u64::from(CORRECTED_EXPECTED_TOKEN))
            || document
                .pointer("/corrected_oracle_event/secondary_selected_token")
                .and_then(|v| v.as_u64())
                != Some(u64::from(CORRECTED_EXPECTED_TOKEN))
        {
            return Err("corrected oracle binding mismatch".into());
        }
    }
    if one.attempt_id != attempt_id
        || one.prompt_token != 9703
        || one.expected_token != expected_token
        || one.attempts != 1
        || one.retries != 0
        || one.resume
        || !one.mandatory_stop
        || one.generated_token_limit != 1
        || one.sequence_position != 0
        || one.initial_kv_state != "EMPTY_CLEAN_PROCESS"
        || one.receipt_schema != receipt_schema
    {
        return Err("one-shot authority mismatch".into());
    }
    let runtime = &contract.runtime;
    if runtime.machine_brand != "Apple M1 Ultra"
        || runtime.architecture != "arm64"
        || runtime.mlx_version != "0.31.2"
        || runtime.mlx_c_version != "0.6.0"
        || runtime.build_profile != "release"
        || runtime.minimum_available_memory_bytes != MINIMUM_AVAILABLE_MEMORY_BYTES
        || runtime.memory_sample_max_age_seconds != 5
        || runtime
            .environment
            .get("PULSAR_REQUIRE_NATIVE_MLX")
            .map(String::as_str)
            != Some("1")
    {
        return Err("runtime authority mismatch".into());
    }
    if !Path::new(&contract.state_root).is_absolute() {
        return Err("state root is not absolute".into());
    }
    validate_state_root(Path::new(&contract.state_root))?;
    Ok(())
}

fn validate_state_root(path: &Path) -> Result<(), String> {
    let parent = path.parent().ok_or("state root has no parent")?;
    let resolved_parent = parent.canonicalize().map_err(|e| e.to_string())?;
    if resolved_parent.join(path.file_name().ok_or("state root leaf")?) != path {
        return Err("state root contains an alternate or symlinked ancestor".into());
    }
    if path.exists() {
        let metadata = fs::symlink_metadata(path).map_err(|e| e.to_string())?;
        if metadata.file_type().is_symlink() || !metadata.is_dir() {
            return Err("state root is not a real directory".into());
        }
        if metadata.permissions().mode() & 0o077 != 0 {
            return Err("state root permissions are not private".into());
        }
    }
    Ok(())
}

fn command_stdout(program: &str, args: &[&str]) -> Result<String, String> {
    let output = Command::new(program)
        .args(args)
        .output()
        .map_err(|e| e.to_string())?;
    if !output.status.success() {
        return Err(format!("{program} failed"));
    }
    String::from_utf8(output.stdout)
        .map(|s| s.trim_end_matches(['\r', '\n']).to_owned())
        .map_err(|e| e.to_string())
}

pub fn available_memory_bytes_from_vm_stat(text: &str) -> Result<u64, String> {
    let page_size = text
        .lines()
        .next()
        .and_then(|line| line.split("page size of ").nth(1))
        .and_then(|tail| tail.split_whitespace().next())
        .and_then(|v| v.parse::<u64>().ok())
        .ok_or("vm_stat page size")?;
    let mut pages = BTreeMap::<&str, u64>::new();
    for line in text.lines().skip(1) {
        if let Some((name, value)) = line.split_once(':') {
            if let Ok(count) = value.trim().trim_end_matches('.').parse::<u64>() {
                pages.insert(name, count);
            }
        }
    }
    let count = ["Pages free", "Pages inactive", "Pages speculative"]
        .iter()
        .try_fold(0_u64, |sum, key| {
            pages
                .get(key)
                .and_then(|v| sum.checked_add(*v))
                .ok_or("vm_stat census")
        })?;
    count
        .checked_mul(page_size)
        .ok_or("vm_stat overflow".into())
}

pub fn validate_machine(contract: &RealP1Contract) -> Result<u64, String> {
    if command_stdout("/usr/sbin/sysctl", &["-n", "machdep.cpu.brand_string"])?
        != contract.runtime.machine_brand
        || std::env::consts::ARCH != "aarch64"
    {
        return Err("machine identity mismatch".into());
    }
    if command_stdout("/usr/bin/sw_vers", &["-buildVersion"])? != contract.runtime.macos_build {
        return Err("macOS build mismatch".into());
    }
    if command_stdout("/opt/homebrew/bin/rustc", &["--version"])? != contract.runtime.rustc_version
    {
        return Err("rustc identity mismatch".into());
    }
    for binding in &contract.runtime.dylibs {
        let path = Path::new(&binding.path);
        if !path.is_absolute()
            || fs::symlink_metadata(path)
                .map_err(|e| e.to_string())?
                .file_type()
                .is_symlink()
            || sha256(path)? != binding.sha256
        {
            return Err(format!("runtime dylib mismatch {}", binding.path));
        }
    }
    for (key, value) in &contract.runtime.environment {
        if std::env::var(key).ok().as_deref() != Some(value) {
            return Err(format!("runtime environment mismatch {key}"));
        }
    }
    let available = available_memory_bytes_from_vm_stat(&command_stdout("/usr/bin/vm_stat", &[])?)?;
    if available < contract.runtime.minimum_available_memory_bytes {
        return Err("available memory below 16 GiB".into());
    }
    Ok(available)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn contract_generations_are_closed_and_attempt_2_binds_the_corrected_token() {
        assert_eq!(contract_generation(CONTRACT_SCHEMA), Some(2));
        assert_eq!(contract_generation(CONTRACT_SCHEMA_V3), Some(3));
        assert_eq!(contract_generation("pulsarmlx.f017.native-bounded-p1-admission-contract/4.0.0"), None);
        assert_eq!(contract_generation(""), None);
        assert_eq!(CORRECTED_EXPECTED_TOKEN, 154_820);
        assert_ne!(CORRECTED_EXPECTED_TOKEN, stream::EXPECTED_TOKEN, "attempt 2 must not reuse the defective attempt-1 expected token");
        assert_eq!(ATTEMPT_2_ID, "F017-NATIVE-BOUNDED-P1-ATTEMPT-2");
    }
    #[test]
    fn generation_2_contract_without_binding_and_generation_3_with_binding_parse() {
        let base = serde_json::json!({"schema": CONTRACT_SCHEMA, "status": "x", "branch": "b", "execution_code_head": "h", "executor": {"path": "p", "sha256": "s"}, "code_manifest": [],
            "authorities": {"cross_branch_authority": {"path": "p", "sha256": "s"}, "execution_architecture": {"path": "p", "sha256": "s"}, "runtime_provenance": {"path": "p", "sha256": "s"}, "d0": {"path": "p", "sha256": "s"}, "d1": {"path": "p", "sha256": "s"}, "d2": {"path": "p", "sha256": "s"}, "retention_reuse_grant": {"path": "p", "sha256": "s"}, "comparison_read_grant": {"path": "p", "sha256": "s"}, "d3_5_result": {"path": "p", "sha256": "s"}, "d3_5_acceptance": {"path": "p", "sha256": "s"}, "synthetic_full_graph_result": {"path": "p", "sha256": "s"}, "historical_master_ledger_sha256": "s", "historical_master_terminal_value": 175},
            "checkpoint": {"root_environment": "E", "manifest": {"path": "p", "sha256": "s"}, "catalog": {"path": "p", "sha256": "s"}, "checkpoint_set_sha256": "s", "fallback": "PROHIBITED", "shards": []},
            "runtime": {"machine_brand": "m", "architecture": "arm64", "macos_build": "b", "mlx_version": "v", "mlx_c_version": "v", "rustc_version": "r", "build_profile": "release", "minimum_available_memory_bytes": 1, "memory_sample_max_age_seconds": 5, "dylibs": [], "environment": {}},
            "one_shot": {"attempt_id": "a", "prompt_token": 9703, "expected_token": 1, "attempts": 1, "retries": 0, "resume": false, "mandatory_stop": true, "generated_token_limit": 1, "sequence_position": 0, "initial_kv_state": "k", "receipt_schema": "r"},
            "state_root": "/x", "live_authorization_present": false, "normal_validation_can_authorize": false});
        let v2: RealP1Contract = serde_json::from_value(base.clone()).unwrap();
        assert!(v2.corrected_oracle_binding.is_none());
        let mut v3 = base;
        v3["schema"] = serde_json::Value::String(CONTRACT_SCHEMA_V3.into());
        v3["corrected_oracle_binding"] = serde_json::json!({"path": "p", "sha256": "s"});
        let v3: RealP1Contract = serde_json::from_value(v3).unwrap();
        assert_eq!(v3.corrected_oracle_binding.unwrap().path, "p");
    }
    #[test]
    fn vm_stat_parser_is_strict_and_includes_no_caller_claim() {
        let text="Mach Virtual Memory Statistics: (page size of 16384 bytes)\nPages free: 500000.\nPages inactive: 500000.\nPages speculative: 100000.\n";
        assert_eq!(
            available_memory_bytes_from_vm_stat(text).unwrap(),
            18_022_400_000
        );
        assert!(available_memory_bytes_from_vm_stat("caller says 999999999999").is_err());
        assert!(available_memory_bytes_from_vm_stat(
            "Mach Virtual Memory Statistics: (page size of 16384 bytes)\nPages free: 1.\n"
        )
        .is_err());
    }
}

===== crates/f017-native/src/bin/bounded_p1.rs (execute-evidenced-v4 arm) =====
//! Operator-only bounded-P1 entry. Normal validation exposes plan-only mode;
//! it cannot mint authorization. `execute` consumes an already-created exact
//! one-shot authority and immediately enters the shared RN1 lifecycle.

use f017_native::contract;
use f017_native::executor::FullNativeP1MathV3;
use f017_native::loader::{load_plan_only, plan_summary};
use f017_native::model::ModelConfig;
use sha2::{Digest, Sha256};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use stream::{
    execute_evidenced_bounded_p1_once, validate_real_p1_authority, P1AttemptAuthority,
    P1RuntimeIdentity, EVIDENCED_RECEIPT_SCHEMA,
};

fn sha(path: &Path) -> Result<String, String> {
    let bytes = fs::read(path).map_err(|e| e.to_string())?;
    Ok(format!("{:x}", Sha256::digest(bytes)))
}
fn write_exclusive(path: &Path, value: &serde_json::Value) -> Result<(), String> {
    use std::io::Write;
    use std::os::unix::fs::OpenOptionsExt;
    let mut f = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o400)
        .open(path)
        .map_err(|e| e.to_string())?;
    let mut b = serde_json::to_vec(value).map_err(|e| e.to_string())?;
    b.push(b'\n');
    f.write_all(&b).map_err(|e| e.to_string())?;
    f.sync_all().map_err(|e| e.to_string())?;
    Ok(())
}
fn git(repo: &Path, args: &[&str]) -> Result<String, String> {
    let output = Command::new("git")
        .current_dir(repo)
        .args(args)
        .output()
        .map_err(|e| e.to_string())?;
    if !output.status.success() {
        return Err("git authority command failed".into());
    }
    String::from_utf8(output.stdout)
        .map(|s| s.trim().to_owned())
        .map_err(|e| e.to_string())
}
fn repository_preflight(repo: &Path, branch: &str, authority_head: &str) -> Result<(), String> {
    if git(repo, &["branch", "--show-current"])? != branch
        || git(repo, &["rev-parse", "HEAD"])? != authority_head
        || git(repo, &["rev-parse", &format!("origin/{branch}")])? != authority_head
        || !git(repo, &["status", "--porcelain"])?.is_empty()
    {
        return Err("repository authority mismatch".into());
    }
    Ok(())
}

fn run() -> Result<(), String> {
    let a = std::env::args().collect::<Vec<_>>();
    match a.get(1).map(String::as_str){
        Some("plan-only") if a.len()==5=>{let(m,c)=load_plan_only(Path::new(&a[2]),Path::new(&a[3]))?;write_exclusive(Path::new(&a[4]),&plan_summary(&m,&c))},
        Some("validate-contract") if a.len()==4=>{let(contract,_)=contract::load(Path::new(&a[2]))?;contract::validate_static(&contract,Path::new(&a[3]))},
        Some("machine-preflight") if a.len()==4=>{let(contract,_)=contract::load(Path::new(&a[2]))?;contract::validate_static(&contract,Path::new(&a[3]))?;contract::validate_machine(&contract).map(|_|())},
        Some("execute-evidenced-v4") if a.len()==8=>{
            let manifest_path=PathBuf::from(&a[2]);let catalog_path=PathBuf::from(&a[3]);let root=PathBuf::from(&a[4]);let auth_path=PathBuf::from(&a[5]);let state=PathBuf::from(&a[6]);let contract=PathBuf::from(&a[7]);
            let repo=std::env::current_dir().map_err(|e|e.to_string())?;let(real_contract,contract_sha)=f017_native::contract::load(&contract)?;f017_native::contract::validate_static(&real_contract,&repo)?;
            let authority:P1AttemptAuthority=f017_native::json::parse_json_no_duplicates(&fs::read(&auth_path).map_err(|e|e.to_string())?)?;
            validate_real_p1_authority(&authority).map_err(|e|e.to_string())?;
            if real_contract.one_shot.receipt_schema != EVIDENCED_RECEIPT_SCHEMA
                || !authority.real_event_authorized
                || authority.attempt_id!=real_contract.one_shot.attempt_id
                || authority.checkpoint_manifest_sha256!=sha(&manifest_path)?
                || authority.checkpoint_catalog_sha256!=sha(&catalog_path)?
                || authority.contract_sha256!=contract_sha
                || authority.d0_sha256!=real_contract.authorities.d0.sha256
                || authority.d1_sha256!=real_contract.authorities.d1.sha256
                || authority.d2_sha256!=real_contract.authorities.d2.sha256
                || authority.d3_5_result_sha256!=real_contract.authorities.d3_5_result.sha256
                || authority.d3_5_acceptance_sha256!=real_contract.authorities.d3_5_acceptance.sha256
                || authority.synthetic_full_graph_result_sha256!=real_contract.authorities.synthetic_full_graph_result.sha256
                || authority.historical_master_ledger_sha256!=real_contract.authorities.historical_master_ledger_sha256
                || authority.historical_master_terminal_value!=real_contract.authorities.historical_master_terminal_value
            {return Err("authority binding mismatch".into())}
            let current=std::env::current_exe().map_err(|e|e.to_string())?;if authority.executor_sha256!=sha(&current)?||authority.executor_sha256!=real_contract.executor.sha256{return Err("executor identity mismatch".into())}
            repository_preflight(&repo,&real_contract.branch,&authority.git_head)?;f017_native::contract::validate_machine(&real_contract)?;
            if state!=PathBuf::from(&real_contract.state_root){return Err("state root mismatch".into())}
            let configured=std::env::var(&real_contract.checkpoint.root_environment).map_err(|_|"checkpoint root environment missing")?;if root.canonicalize().map_err(|e|e.to_string())?!=PathBuf::from(configured).canonicalize().map_err(|e|e.to_string())?{return Err("checkpoint root mismatch".into())}
            let(m,c)=load_plan_only(&manifest_path,&catalog_path)?;if authority.checkpoint_set_sha256!=m.checkpoint_set_sha256{return Err("checkpoint set mismatch".into())}
            let mut math=FullNativeP1MathV3::new(root,m,c,ModelConfig::glm52(),authority.expected_token);
            let runtime=P1RuntimeIdentity{mlx_version:real_contract.runtime.mlx_version,mlx_c_version:real_contract.runtime.mlx_c_version,architecture:real_contract.runtime.architecture,machine_brand:real_contract.runtime.machine_brand,stream_origin:"OWNED_DEVICE_GPU".into(),native_handle_owned:true,deallocation_responsibility:"THIS_INVOCATION".into()};
            execute_evidenced_bounded_p1_once(&state,&authority,runtime,&mut math,false).map(|_|()).map_err(|e|e.to_string())
        },
        Some("execute") | Some("execute-evidenced-v3") => Err("legacy real-execution arm is tombstoned; only execute-evidenced-v4 may be current authority".into()),
        _=>Err("usage: f017-native-bounded-p1 plan-only MANIFEST CATALOG OUT | validate-contract CONTRACT REPO_ROOT | machine-preflight CONTRACT REPO_ROOT | execute-evidenced-v4 MANIFEST CATALOG CHECKPOINT_ROOT AUTHORIZATION STATE_ROOT CONTRACT".into())
    }
}
fn main() {
    if let Err(e) = run() {
        eprintln!("{e}");
        std::process::exit(2)
    }
}

===== crates/stream/src/p1_domain.rs lines 1080-1100 and 1296-1315 =====
            let context = MlxContext::new(MlxDevice::Gpu, MlxStreamMode::Owned)
                .map_err(P1DomainError::Rejected)?;
            let token = math
                .execute_one(&context, authority.prompt_token)
                .map_err(P1DomainError::Rejected)?;
            context.synchronize().map_err(P1DomainError::Rejected)?;
            token
        };
        let after = P1AccountingSnapshot::capture().map_err(P1DomainError::Rejected)?;
        validate_accounting(&before, &after)?;
        if token != authority.expected_token {
            return Err(P1DomainError::Rejected(format!(
                "bounded P1 token mismatch: expected {}, got {token}",
                authority.expected_token
            )));
        }
        Ok(BoundedP1Receipt {
            schema: RECEIPT_SCHEMA.into(),
            event_class: if inert_test {
                "NATIVE_P1_INERT_MATH_BOUNDARY_REHEARSAL"
            } else {
...
            Some(format!("PRODUCER_FAILURE:{error}")),
        )
    } else if let Some(error) = accounting_error {
        (
            "ACCOUNTING_FAILURE",
            "TERMINAL_FAILURE_NO_RETRY",
            Some(format!("ACCOUNTING_FAILURE:{error}")),
        )
    } else if produced_token != Some(authority.expected_token) {
        (
            "TOKEN_MISMATCH",
            "TERMINAL_FAILURE_NO_RETRY",
            Some("TOKEN_MISMATCH".into()),
        )
    } else {
        ("EXPECTED_TOKEN_MATCH", "COMPLETE_MANDATORY_STOP", None)
    };
    let receipt = EvidencedBoundedP1Receipt {
        schema: EVIDENCED_RECEIPT_SCHEMA.into(),
        event_class: if inert_test {

===== crates diff 4faa404c..HEAD --stat =====
 crates/f017-native/Cargo.toml                      |    4 +
 crates/f017-native/src/bin/bounded_p1.rs           |   19 +-
 crates/f017-native/src/bin/decoder_differential.rs |   76 ++
 .../src/bin/quant_native_matvec_probe.rs           |  105 ++
 .../f017-native/src/bin/synthetic_differential.rs  |  129 +++
 crates/f017-native/src/contract.rs                 |   89 +-
 crates/f017-native/src/executor.rs                 |  231 +++-
 crates/f017-native/src/loader.rs                   |  312 +++++-
 crates/f017-native/src/model.rs                    |  197 +++-
 crates/f017-native/src/synthetic.rs                |    6 +-
 crates/quant/src/extra_ref.rs                      |   24 +-
 crates/stream/Cargo.toml                           |    2 +-
 crates/stream/src/lib.rs                           |   10 +-
 crates/stream/src/p1_domain.rs                     | 1133 +++++++++++++++++++-
 14 files changed, 2232 insertions(+), 105 deletions(-)

===== quant IQ4_XS change since attempt 1 =====
diff --git a/crates/quant/src/extra_ref.rs b/crates/quant/src/extra_ref.rs
index a7c55d3c..3fe97c7a 100644
--- a/crates/quant/src/extra_ref.rs
+++ b/crates/quant/src/extra_ref.rs
@@ -203,9 +203,12 @@ pub fn decode_iq4_xs_matrix(
             let low = (scales_l[group / 2] >> (4 * (group & 1))) & 15;
             let high = ((scales_h >> (2 * group)) & 3) as u8;
             let scale = d * f32::from((low | (high << 4)) as i8 - 32);
-            for byte in &qs[group * 16..group * 16 + 16] {
+            let group_bytes = &qs[group * 16..group * 16 + 16];
+            for byte in group_bytes {
                 out[at] = scale * f32::from(KVALUES_IQ4NL[usize::from(byte & 15)]);
                 at += 1;
+            }
+            for byte in group_bytes {
                 out[at] = scale * f32::from(KVALUES_IQ4NL[usize::from(byte >> 4)]);
                 at += 1;
             }
@@ -241,4 +244,23 @@ mod tests {
             assert!(decoder(&vec![0; bytes - 1], 1, QK_K, &mut out).is_err());
         }
     }
+
+    #[test]
+    fn iq4_xs_uses_ggml_split_low_then_high_lane_order() {
+        let mut block = vec![0_u8; IQ4_XS_BYTES];
+        block[..2].copy_from_slice(&0x3c00_u16.to_le_bytes());
+        block[2..4].copy_from_slice(&0xaaaa_u16.to_le_bytes());
+        block[4..8].fill(0x11);
+        for group in 0..8 {
+            for lane in 0..16 {
+                block[8 + group * 16 + lane] = ((15 - lane) as u8) << 4 | lane as u8;
+            }
+        }
+        let mut out = vec![0.0; QK_K];
+        decode_iq4_xs_matrix(&block, 1, QK_K, &mut out).unwrap();
+        let expected_low: Vec<f32> = KVALUES_IQ4NL.iter().map(|value| f32::from(*value)).collect();
+        let expected_high: Vec<f32> = KVALUES_IQ4NL.iter().rev().map(|value| f32::from(*value)).collect();
+        assert_eq!(&out[..16], expected_low.as_slice());
+        assert_eq!(&out[16..32], expected_high.as_slice());
+    }
 }

===== COMMITS c23e58ec..HEAD =====
01d8565a68345aab256a857f62970dc2712c7655 f017: attempt-2 final review cycle 02 (fresh claude-opus-5 session): REJECT on governance completeness (B-01 CI precondition known-failed, B-02 in-place re-binding) banked verbatim; domain declaration v3 (append-only) answers B-01/B-02, R-01..R-03 (numerical delta since attempt 1: IQ4_XS lane order; verdict logic uses the authority token; Event 06 ancestry and oracle module SHAs) and D-01..D-05 (executor rebuild byte-identical at the readiness head; quit-not-suspend; shard rehash); inert template rebound to v3
8456f2060e60446a7411e255d062b0ebc1115087 docs(f017): record the pre-existing V11 measurement-drift CI blocker for the attempt-2 readiness head
d690a9675ed6ded0f25dfd22adce32a0fc3fa064 f017: re-bind contract v3 code manifest after the Cargo.toml bin-name restoration; declaration v2 and inert template carry the new contract sha; executor unchanged
30ca81dc08d81f993abfa8f78524e46dbb6cba54 f017: keep the auto-discovered synthetic_differential bin name (CI qualifies it by that name); the decoder-differential bin stays declared; evidence wording updated
5b9b05f72122fa01896b7dab1077a45348de357e docs(f017): native bounded-P1 attempt-2 readiness status (2026-09-20)
1e66901aef13a59f845d0937c7fa0cbe332ceaed f017: attempt-2 final-review request packet, inert human-approval template (contract v3 / declaration v2), supporting adversarial review (gemini, ACCEPT, 0 blocking), and the failed not-logged-in CLI attempt record for the operator-authorized reviewer; nothing authorized
50a66db0d4fb8d80d9491e870dd2d3d8fa8e8ca6 f017: native bounded-P1 attempt-2 domain declaration v2 (PREPARED_HUMAN_GATE_REQUIRED): binds contract v3, the M1 Ultra-built executor, the corrected-oracle binding and the checkpoint-free reconciliation; lists the remaining pre-GO steps; no authorization
fec2f51666985deabf7a3791c45494ac0f8bad7d f017: admission contract v3 for native bounded-P1 attempt 2 (prepared, human gate required): executor f017-native-bounded-p1-v2 built on the M1 Ultra from 5e32d68f with the pinned MLX 0.31.2 keg and Homebrew rustc 1.97.1, corrected-oracle binding, evidenced v4 receipt; static validation negative controls recorded; no live authorization
5e32d68faa7b10168b9bb7f5d4fce6ebf212b737 f017: admission contract generation 3 for native bounded-P1 attempt 2 (weekend 2026-09-20 W3/N4): validate_static accepts schema 3.0.0 only with a bound corrected-oracle binding document (Event 06 token 154820, EXACT_EXPECTED_TOKEN_STABLE, evidenced v4 receipt); generation 2 rules unchanged; corrected-oracle binding document; M1 Ultra reproduction of the checkpoint-free differentials; no live authorization
63d56348551871a74a75c02178f2af29bd4a4d84 f017: checkpoint-free reconciliation of the native runtime with the corrected oracle (weekend 2026-09-20 W3): decoder differential producer over the exact loader dispatch vs the Event 06 independent scalar decoders (11 formats, 0 ULP, negative control flagged), native full-graph vs the corrected oracle binary64 numerics on the synthetic family (6/6), synthetic-differential bin declared; evidence banked append-only; no contract or tolerance changes
