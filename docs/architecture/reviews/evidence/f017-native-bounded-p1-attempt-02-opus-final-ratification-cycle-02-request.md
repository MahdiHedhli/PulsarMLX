# F017 native bounded-P1 attempt 2 — operator-authorized final independent review request (cycle 02)

Nonce: 0092e4fb2b3ea0177c5b07e921b939ff (echo it exactly). Readiness head to echo: 8456f2060e60446a7411e255d062b0ebc1115087 (feat/017-rust-native-inference-runtime == work/glm52-weekend-20260920).

You are the operator-authorized final reviewer (claude-opus-5, fresh session, no tools, no prior context). Review ONLY the material inline below. Question: is the prepared attempt-2 domain fit for ONE human GO decision (already expressed by the human in plain words and about to be recorded through the frozen approval mechanism) for exactly one bounded Apple M1 Ultra native P1: prompt 9703, position 0, empty KV, greedy, expected token 154820 from the accepted Event 06 corrected oracle, executed once through execute-evidenced-v4, mandatory stop, no retry, no resume?

Reply with ONE JSON object only, no prose, no fences:
{"nonce": string, "readiness_head": string, "verdict": "ACCEPT_FOR_SINGLE_BOUNDED_M1_ULTRA_P1" or "REJECT", "blocking_findings": [{"id","body","evidence","remedy"}], "non_blocking_required_findings": [...], "defense_in_depth_findings": [...], "adversarial_cases_considered": int, "rationale": string}
A non-blocking-REQUIRED finding is one the operator must satisfy before execution; use it only for genuinely required steps not already listed as done or as remaining below.

## Cycle-02 addendum (state after the cycle-01 packet was assembled)
- Commits after 50a66db0: 1e66901a (final-review request packet, inert approval template, supporting Gemini review ACCEPT/0 blocking, failed not-logged-in CLI record), 5b9b05f7 (readiness note), 30ca81dc (restored the auto-discovered `synthetic_differential` bin name that a CI step builds; the decoder-differential bin stays declared), d690a967 (contract v3 code-manifest re-bound after the Cargo.toml change; declaration v2 and template carry the new contract sha; executor unchanged), 8456f206 (readiness note records the CI blocker). Contract v3 sha256 7f984043…; validate-contract and machine-preflight re-run PASS on the M1 Ultra at d690a967.
- Exact-head CI (run 35509978669, FULL_NATIVE): classification and Apple Silicon workspace baseline (cargo build/test) SUCCESS; the MLX small-fixture job passes every step until `generate_f017_v11_measurement_v1.py --check`, which fails: "working tree differs from measurement head: scripts/research/f017_corrected_oracle_primary_wrapper_v11.py". This drift is pre-existing: measurement v8 binds that file at f35d3411; commit 5b39a21a (2026-09-03, "simplify Event 06 to minimum gate path", the accepted Event 06 path) changed it; no FULL_NATIVE run has passed on the branch since (2026-09-05 runs were evidence-only). The V11 measurement/authority chain (30 references incl. the corrected-oracle authorization module and scientific-access contracts) is the F017 planner's; it was not modified. The native executor, contract validation and the checkpoint-free differentials are independent of that check.
- Checkpoint root for execution: the same accepted directory attempt 1 used (six hard-linked shard files only; census exact), on the Studio internal SSD; state root absent; legacy resident service idle and will be paused before execution; available memory will be re-measured (>= 16 GiB required by the executor).
- Reviewer availability: the headless `claude` CLI on the operator's machine was not logged in; this review is performed by a fresh claude-opus-5 session spawned as an independent agent with no tools and no access to the preparing session's context.

===== CYCLE-01 PACKET (verbatim) =====
# F017 native bounded-P1 attempt 2 — operator-authorized final independent review request (cycle 01)

Nonce: 8eefafceb2d99f49ab0ad14dc99bd5bf (echo it exactly in the response).

You are the operator-authorized final reviewer (claude-opus-5, fresh session) for the F017 native bounded-P1 execution domain. Review ONLY the material inline below. Do not use tools. The question is narrow: is the prepared attempt-2 domain fit for presentation of ONE human GO/no-GO decision for exactly one bounded Apple M1 Ultra native P1 (prompt token 9703, position 0, empty KV, greedy, expected token 154820 from the accepted Event 06 corrected oracle), executed once through execute-evidenced-v4 with mandatory stop, no retry, no resume?

Reply with ONE JSON object only, no prose, no fences:
{"nonce": string, "readiness_head": "50a66db0d4fb8d80d9491e870dd2d3d8fa8e8ca6", "verdict": "ACCEPT_FOR_SINGLE_BOUNDED_M1_ULTRA_P1" or "REJECT", "blocking_findings": [{"id": string, "body": string, "evidence": string, "remedy": string}], "non_blocking_required_findings": [...same shape...], "defense_in_depth_findings": [...same shape...], "adversarial_cases_considered": int, "rationale": string}

Be adversarial. In particular: (1) Attempt 1 failed (observed 17351 vs expected 21615); the expected token was proven to come from a defective decoder family and the corrected oracle now says 154820. Is binding 154820 as EXACT_EXPECTED_TOKEN_STABLE for attempt 2 sound, and is attempt 2 a genuinely new attempt rather than a disguised retry? (2) The contract validator gained a generation 3 (schema 3.0.0) accepting attempt id 2 / token 154820 / evidenced v4 receipt only with a bound corrected-oracle document; are generation-2 rules unchanged and is anything weakened? Note the pre-existing contradiction: generation 2 required the v2 receipt schema while execute-evidenced-v4 requires the v4 schema, so no v2 contract could execute. (3) The checkpoint-free reconciliation shows the native decoders bit-identical to the corrected oracle's independent decoders (11 formats) and the native full graph within thresholds on 6 synthetic cases — does this justify presenting attempt 2, and what does it NOT show? (4) The executor binary was built on the M1 Ultra from head 5e32d68f with the pinned MLX keg and committed; contract v3 binds its SHA; static validation and machine preflight passed on the M1 Ultra with zero checkpoint reads; negative controls rejected. Any gap in the binding chain (executor built one commit before the contract that binds it; execution_code_head semantics)? (5) The frozen branch name forces execution from feat/017-rust-native-inference-runtime at a clean head equal to origin; the work was prepared on a fast-forward branch. Any risk? (6) Memory/one-heavy-workload: the executor requires >= 16 GiB available; a legacy resident service must be paused first. (7) Anything that must happen before a human can responsibly say GO, beyond the listed remaining steps?

===== DOMAIN DECLARATION v2 =====
{
 "schema": "pulsarmlx.f017.native-bounded-p1-execution-domain-final-declaration/2.0.0",
 "declaration": "F017_NATIVE_BOUNDED_P1_ATTEMPT_2_DOMAIN: PREPARED_FOR_ONE_HUMAN_GO_DECISION",
 "status": "PREPARED_HUMAN_GATE_REQUIRED",
 "scope": "Presentation of one separate human GO/no-GO decision for exactly one bounded Apple M1 Ultra native P1 (attempt 2, a new attempt under a new authorization; attempt 1 remains a banked terminal failure whose retry is permanently prohibited). This declaration neither issues authorization nor executes anything.",
 "supersedes_for_attempt_2": {
  "path": "docs/architecture/reviews/evidence/f017-native-bounded-p1-execution-domain-final-declaration-v1.json",
  "sha256": "64af7842c7ba7fccfface96ab59249302cdfb2938847973202c984cdfcdeff99",
  "v1_attempt_1_artifacts_modified": false
 },
 "authoritative_branch": "feat/017-rust-native-inference-runtime",
 "prepared_on_branch": "work/glm52-weekend-20260920 (fast-forward of feat/017-rust-native-inference-runtime @ c23e58ec87c7e73a23cf37ac64aa4dee6c45896f; the frozen contract binds the feature branch name, so execution requires the feature branch to be fast-forwarded to the readiness head before the approval is committed)",
 "execution_code_head": "5e32d68faa7b10168b9bb7f5d4fce6ebf212b737",
 "executor": {
  "path": "specs/017-rust-native-inference-runtime/bin/f017-native-bounded-p1-v2",
  "sha256": "91e50a0bb84a30450f9189da2122b84e1790649c1361ed90cea001ca537f52f0",
  "built_on": "Apple M1 Ultra, macOS build 25A354, Homebrew rustc 1.97.1, pinned MLX 0.31.2 keg (libmlx ad9b597b08e28b43..., libmlxc 3401e4f91a1d3f9b...), release profile, from 5e32d68f"
 },
 "admission_contract": {
  "path": "specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-admission-contract-v3.json",
  "sha256": "389580fa7ba5ca0f8a8d531aa522431bae9b47db413a02fba69b15e2132356f4",
  "generation": 3,
  "static_validation_m1_ultra": "PASS (validate-contract) 2026-09-20",
  "machine_preflight_m1_ultra": "PASS 2026-09-20 (brand, macOS build, rustc, dylib SHAs, environment)",
  "plan_only_m1_ultra": "PLAN_ONLY_PASS (1809 tensors, 6 shards, 238,458,632,928 bytes, 0 checkpoint reads)",
  "negative_controls": {
   "path": "docs/architecture/reviews/evidence/f017-native-bounded-p1-contract-v3-static-validation-v1.json",
   "sha256": "35a4ac82872524c47e7369cae3b409e990d545cdc2950a506d114c0222bc4e70",
   "all_rejected": true
  }
 },
 "corrected_oracle_binding": {
  "path": "specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-attempt-02-corrected-oracle-binding-v1.json",
  "sha256": "c582e3b4ae924fcaafad67f4e997f5d5e6a8dba1320ef395f6ba6499dd5a3512",
  "expected_token": 154820,
  "acceptance_mode": "EXACT_EXPECTED_TOKEN_STABLE",
  "event": "Event 06 / sequence 43 (EVENT06_SUCCESS_ACCEPTED), prompt 9703, position 0"
 },
 "checkpoint_free_reconciliation": {
  "path": "docs/architecture/reviews/evidence/f017-native-checkpoint-free-reconciliation-20260920-v1.json",
  "sha256": "f7193decd52081942a50c267754ce614699638c6773c0e818e3e22bf483d484e",
  "decoders": "11 formats bit-identical to the corrected oracle's independent decoders (MacBook and M1 Ultra)",
  "graph": "6/6 synthetic full-graph cases within the frozen thresholds against the corrected oracle binary64 numerics (MacBook and M1 Ultra)",
  "limit": "synthetic; real-checkpoint agreement is exactly what attempt 2 decides"
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
  "expected_duration": "~2-3 minutes after durable start (attempt 1: 123.5 s)",
  "memory": "the executor requires >= 17,179,869,184 bytes available (vm_stat free+inactive+speculative) at admission; the legacy resident service on the host must be paused first"
 },
 "remaining_before_go": [
  "fast-forward feat/017-rust-native-inference-runtime to the readiness head (non-force)",
  "exact-head CI success for that head",
  "final independent review by the operator-authorized reviewer (claude-opus-5, fresh session) with verdict ACCEPT_FOR_SINGLE_BOUNDED_M1_ULTRA_P1 and 0 blocking findings, banked with exact request/response",
  "a committed human approval (schema pulsarmlx.f017.native-bounded-p1-human-approval/1.0.0, decision AUTHORIZE_EXACTLY_ONE_BOUNDED_M1_ULTRA_P1) binding this declaration, the final review, the readiness head and the contract v3 sha; then scripts/research/f017_native_p1_authorization.py authorize mints the one-shot authority in a fresh private state root"
 ],
 "safety": {
  "live_authorization_created": false,
  "checkpoint_reads_this_preparation": 0,
  "event_06_replayed": false,
  "attempt_1_retried": false,
  "tolerances_changed": false,
  "generation_2_rules_changed": false
 }
}
===== ADMISSION CONTRACT v3 =====
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
      "sha256": "5d80f28957e19a33108dce4ec8573f4a780977f78e0ff3497070320b4d3fa13c"
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
===== CORRECTED-ORACLE BINDING =====
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
===== CHECKPOINT-FREE RECONCILIATION =====
{
 "schema": "pulsarmlx.f017.native-checkpoint-free-reconciliation/1.0.0",
 "date": "2026-09-20",
 "work_order": "WK26-GLM52-20260920-v1 (W3)",
 "source_head_before": "c23e58ec87c7e73a23cf37ac64aa4dee6c45896f",
 "host": "MacBook Pro M2 Max (arm64), macOS, mlx-c 0.6.0_2 + mlx 0.31.2 (Homebrew), rustc 1.95.0",
 "producer_binaries_sha256": {
  "f017-native-decoder-differential": "29228130954fd47a585b4af8f27803a8e436d31faa45ca9385dcad093ca5c314",
  "f017-native-synthetic-differential": "2696d37758c344b02faa5c016ffbecdd145cf18e13af92aeae5e358040bea84f"
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
  "producer": "f017-native-synthetic-differential (production orchestration execute_one_token_observed through the MLX bridge, TENSOR_MATH_ONLY synthetic source)",
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
===== ATTEMPT-1 ROOT-CAUSE LEDGER (H01) =====
{
 "status": "ROOT_CAUSE_HIGH_CONFIDENCE_NOT_PROVEN",
 "observation": {
  "attempt_id": "F017-NATIVE-BOUNDED-P1-ATTEMPT-1",
  "prompt_token": 9703,
  "frozen_expected_token": 21615,
  "observed_token": 17351,
  "attempts": 1,
  "retries": 0
 },
 "H01": {
  "id": "H01",
  "hypothesis": "expected-token authority mismatch",
  "priority": "HIGHEST",
  "support": [
   "Q6_K expected-path lane permutation proven",
   "IQ3_XXS expected-path lane permutation proven",
   "21615 derives from the affected F016 source family"
  ],
  "contradiction": [],
  "tests": [
   "11-format independent synthetic block matrix",
   "source dependency trace"
  ],
  "disposition": "PROVEN_AUTHORITY_DEFECT; sufficient to invalidate 21615, not sufficient to derive the corrected token"
 }
}

===== SOURCE DIFF c23e58ec..50a66db0 (code only) =====
diff --git a/crates/f017-native/Cargo.toml b/crates/f017-native/Cargo.toml
index 4f9b141c..f590d01c 100644
--- a/crates/f017-native/Cargo.toml
+++ b/crates/f017-native/Cargo.toml
@@ -31,3 +31,11 @@ path = "src/bin/bounded_p1.rs"
 [[bin]]
 name = "f017-native-synthetic-p1"
 path = "src/bin/synthetic_p1.rs"
+
+[[bin]]
+name = "f017-native-decoder-differential"
+path = "src/bin/decoder_differential.rs"
+
+[[bin]]
+name = "f017-native-synthetic-differential"
+path = "src/bin/synthetic_differential.rs"
diff --git a/crates/f017-native/src/bin/decoder_differential.rs b/crates/f017-native/src/bin/decoder_differential.rs
new file mode 100644
index 00000000..840098f5
--- /dev/null
+++ b/crates/f017-native/src/bin/decoder_differential.rs
@@ -0,0 +1,76 @@
+//! Checkpoint-free decoder differential producer (glm52-weekend W3). Reads a
+//! JSON case file, decodes every case through the secure loader's exact
+//! qualification dispatch (`decode_packed_matrix_for_qualification`, the same
+//! `decode` the real P1 path uses), and writes the decoded f32 values as
+//! little-endian hex so an independent Python driver can compare them against
+//! the corrected oracle's scalar decoders. No filesystem or checkpoint
+//! capability beyond the two operand paths; no numerical reference here.
+
+use f017_native::loader::decode_packed_matrix_for_qualification;
+use serde::{Deserialize, Serialize};
+use std::fs;
+
+#[derive(Deserialize)]
+struct Case {
+    id: String,
+    format: String,
+    type_id: u32,
+    rows: usize,
+    columns: usize,
+    bytes_hex: String,
+}
+
+#[derive(Deserialize)]
+struct Cases {
+    cases: Vec<Case>,
+}
+
+#[derive(Serialize)]
+struct Decoded {
+    id: String,
+    format: String,
+    rows: usize,
+    columns: usize,
+    result: String,
+    values_f32le_hex: Option<String>,
+    error: Option<String>,
+}
+
+fn unhex(s: &str) -> Result<Vec<u8>, String> {
+    if s.len() % 2 != 0 {
+        return Err("odd hex".into());
+    }
+    (0..s.len())
+        .step_by(2)
+        .map(|i| u8::from_str_radix(&s[i..i + 2], 16).map_err(|e| e.to_string()))
+        .collect()
+}
+
+fn main() -> Result<(), String> {
+    let args: Vec<String> = std::env::args().collect();
+    if args.len() != 3 {
+        return Err("usage: f017-native-decoder-differential CASES_JSON OUT_JSON".into());
+    }
+    let cases: Cases =
+        serde_json::from_slice(&fs::read(&args[1]).map_err(|e| e.to_string())?).map_err(|e| e.to_string())?;
+    let mut out = Vec::with_capacity(cases.cases.len());
+    for c in cases.cases {
+        let bytes = unhex(&c.bytes_hex)?;
+        let decoded = decode_packed_matrix_for_qualification(&c.format, c.type_id, &bytes, c.rows, c.columns);
+        out.push(match decoded {
+            Ok(values) => {
+                let mut hex = String::with_capacity(values.len() * 8);
+                for v in &values {
+                    for b in v.to_le_bytes() {
+                        hex.push_str(&format!("{b:02x}"));
+                    }
+                }
+                Decoded { id: c.id, format: c.format, rows: c.rows, columns: c.columns, result: "OK".into(), values_f32le_hex: Some(hex), error: None }
+            }
+            Err(e) => Decoded { id: c.id, format: c.format, rows: c.rows, columns: c.columns, result: "ERROR".into(), values_f32le_hex: None, error: Some(e) },
+        });
+    }
+    let body = serde_json::json!({"schema": "pulsarmlx.f017.decoder-differential-producer/1.0.0", "producer": "f017-native decode_packed_matrix_for_qualification", "decoded": out});
+    fs::write(&args[2], serde_json::to_vec_pretty(&body).map_err(|e| e.to_string())?).map_err(|e| e.to_string())?;
+    Ok(())
+}
diff --git a/crates/f017-native/src/contract.rs b/crates/f017-native/src/contract.rs
index c57173df..6faa76ae 100644
--- a/crates/f017-native/src/contract.rs
+++ b/crates/f017-native/src/contract.rs
@@ -12,6 +12,16 @@ use std::path::{Path, PathBuf};
 use std::process::Command;
 
 pub const CONTRACT_SCHEMA: &str = "pulsarmlx.f017.native-bounded-p1-admission-contract/2.0.0";
+/// Generation 3 (attempt 2): identical census, machine, checkpoint and
+/// authority rules as generation 2, with the one-shot bound to the corrected
+/// oracle's expected token and the evidenced v4 receipt. Generation 2 stays
+/// exactly as frozen for attempt 1; a generation-3 contract must additionally
+/// bind the corrected-oracle binding document.
+pub const CONTRACT_SCHEMA_V3: &str = "pulsarmlx.f017.native-bounded-p1-admission-contract/3.0.0";
+pub const ATTEMPT_2_ID: &str = "F017-NATIVE-BOUNDED-P1-ATTEMPT-2";
+/// Event 06 (sequence 43) corrected full-checkpoint oracle result for prompt
+/// 9703 at position 0: primary and secondary both select 154820.
+pub const CORRECTED_EXPECTED_TOKEN: u32 = 154_820;
 pub const MINIMUM_AVAILABLE_MEMORY_BYTES: u64 = 17_179_869_184;
 
 #[derive(Clone, Debug, Deserialize)]
@@ -86,6 +96,9 @@ pub struct OneShotBinding {
 #[serde(deny_unknown_fields)]
 pub struct RealP1Contract {
     pub schema: String,
+    /// Generation 3 only: the corrected-oracle binding document (attempt 2).
+    #[serde(default)]
+    pub corrected_oracle_binding: Option<FileBinding>,
     pub status: String,
     pub branch: String,
     pub execution_code_head: String,
@@ -144,8 +157,18 @@ fn repo_path(root: &Path, binding: &FileBinding) -> Result<PathBuf, String> {
     Ok(path)
 }
 
+/// Contract generation by schema: 2 = attempt 1 (frozen), 3 = attempt 2.
+pub fn contract_generation(schema: &str) -> Option<u8> {
+    match schema {
+        CONTRACT_SCHEMA => Some(2),
+        CONTRACT_SCHEMA_V3 => Some(3),
+        _ => None,
+    }
+}
+
 pub fn validate_static(contract: &RealP1Contract, repo_root: &Path) -> Result<(), String> {
-    if contract.schema != CONTRACT_SCHEMA
+    let generation = contract_generation(&contract.schema).ok_or("contract root authority mismatch")?;
+    if (generation == 2) != contract.corrected_oracle_binding.is_none()
         || contract.status != "PREPARED_HUMAN_GATE_REQUIRED"
         || contract.branch != "feat/017-rust-native-inference-runtime"
         || contract.execution_code_head.len() != 40
@@ -241,9 +264,41 @@ pub fn validate_static(contract: &RealP1Contract, repo_root: &Path) -> Result<()
         return Err("checkpoint authority mismatch".into());
     }
     let one = &contract.one_shot;
-    if one.attempt_id != "F017-NATIVE-BOUNDED-P1-ATTEMPT-1"
+    let (attempt_id, expected_token, receipt_schema) = if generation == 2 {
+        ("F017-NATIVE-BOUNDED-P1-ATTEMPT-1", 21615_u32, stream::RECEIPT_SCHEMA)
+    } else {
+        (ATTEMPT_2_ID, CORRECTED_EXPECTED_TOKEN, stream::EVIDENCED_RECEIPT_SCHEMA)
+    };
+    if generation == 3 {
+        let binding = contract
+            .corrected_oracle_binding
+            .as_ref()
+            .ok_or("corrected oracle binding missing")?;
+        let path = repo_path(repo_root, binding)?;
+        let document: serde_json::Value = crate::json::parse_json_no_duplicates(
+            &fs::read(&path).map_err(|e| e.to_string())?,
+        )?;
+        if document.get("attempt_id").and_then(|v| v.as_str()) != Some(ATTEMPT_2_ID)
+            || document.get("expected_token").and_then(|v| v.as_u64())
+                != Some(u64::from(CORRECTED_EXPECTED_TOKEN))
+            || document.get("acceptance_mode").and_then(|v| v.as_str())
+                != Some("EXACT_EXPECTED_TOKEN_STABLE")
+            || document.get("live_authorization_created").and_then(|v| v.as_bool()) != Some(false)
+            || document
+                .pointer("/corrected_oracle_event/primary_selected_token")
+                .and_then(|v| v.as_u64())
+                != Some(u64::from(CORRECTED_EXPECTED_TOKEN))
+            || document
+                .pointer("/corrected_oracle_event/secondary_selected_token")
+                .and_then(|v| v.as_u64())
+                != Some(u64::from(CORRECTED_EXPECTED_TOKEN))
+        {
+            return Err("corrected oracle binding mismatch".into());
+        }
+    }
+    if one.attempt_id != attempt_id
         || one.prompt_token != 9703
-        || one.expected_token != 21615
+        || one.expected_token != expected_token
         || one.attempts != 1
         || one.retries != 0
         || one.resume
@@ -251,7 +306,7 @@ pub fn validate_static(contract: &RealP1Contract, repo_root: &Path) -> Result<()
         || one.generated_token_limit != 1
         || one.sequence_position != 0
         || one.initial_kv_state != "EMPTY_CLEAN_PROCESS"
-        || one.receipt_schema != stream::RECEIPT_SCHEMA
+        || one.receipt_schema != receipt_schema
     {
         return Err("one-shot authority mismatch".into());
     }
@@ -380,6 +435,32 @@ pub fn validate_machine(contract: &RealP1Contract) -> Result<u64, String> {
 mod tests {
     use super::*;
     #[test]
+    fn contract_generations_are_closed_and_attempt_2_binds_the_corrected_token() {
+        assert_eq!(contract_generation(CONTRACT_SCHEMA), Some(2));
+        assert_eq!(contract_generation(CONTRACT_SCHEMA_V3), Some(3));
+        assert_eq!(contract_generation("pulsarmlx.f017.native-bounded-p1-admission-contract/4.0.0"), None);
+        assert_eq!(contract_generation(""), None);
+        assert_eq!(CORRECTED_EXPECTED_TOKEN, 154_820);
+        assert_ne!(CORRECTED_EXPECTED_TOKEN, stream::EXPECTED_TOKEN, "attempt 2 must not reuse the defective attempt-1 expected token");
+        assert_eq!(ATTEMPT_2_ID, "F017-NATIVE-BOUNDED-P1-ATTEMPT-2");
+    }
+    #[test]
+    fn generation_2_contract_without_binding_and_generation_3_with_binding_parse() {
+        let base = serde_json::json!({"schema": CONTRACT_SCHEMA, "status": "x", "branch": "b", "execution_code_head": "h", "executor": {"path": "p", "sha256": "s"}, "code_manifest": [],
+            "authorities": {"cross_branch_authority": {"path": "p", "sha256": "s"}, "execution_architecture": {"path": "p", "sha256": "s"}, "runtime_provenance": {"path": "p", "sha256": "s"}, "d0": {"path": "p", "sha256": "s"}, "d1": {"path": "p", "sha256": "s"}, "d2": {"path": "p", "sha256": "s"}, "retention_reuse_grant": {"path": "p", "sha256": "s"}, "comparison_read_grant": {"path": "p", "sha256": "s"}, "d3_5_result": {"path": "p", "sha256": "s"}, "d3_5_acceptance": {"path": "p", "sha256": "s"}, "synthetic_full_graph_result": {"path": "p", "sha256": "s"}, "historical_master_ledger_sha256": "s", "historical_master_terminal_value": 175},
+            "checkpoint": {"root_environment": "E", "manifest": {"path": "p", "sha256": "s"}, "catalog": {"path": "p", "sha256": "s"}, "checkpoint_set_sha256": "s", "fallback": "PROHIBITED", "shards": []},
+            "runtime": {"machine_brand": "m", "architecture": "arm64", "macos_build": "b", "mlx_version": "v", "mlx_c_version": "v", "rustc_version": "r", "build_profile": "release", "minimum_available_memory_bytes": 1, "memory_sample_max_age_seconds": 5, "dylibs": [], "environment": {}},
+            "one_shot": {"attempt_id": "a", "prompt_token": 9703, "expected_token": 1, "attempts": 1, "retries": 0, "resume": false, "mandatory_stop": true, "generated_token_limit": 1, "sequence_position": 0, "initial_kv_state": "k", "receipt_schema": "r"},
+            "state_root": "/x", "live_authorization_present": false, "normal_validation_can_authorize": false});
+        let v2: RealP1Contract = serde_json::from_value(base.clone()).unwrap();
+        assert!(v2.corrected_oracle_binding.is_none());
+        let mut v3 = base;
+        v3["schema"] = serde_json::Value::String(CONTRACT_SCHEMA_V3.into());
+        v3["corrected_oracle_binding"] = serde_json::json!({"path": "p", "sha256": "s"});
+        let v3: RealP1Contract = serde_json::from_value(v3).unwrap();
+        assert_eq!(v3.corrected_oracle_binding.unwrap().path, "p");
+    }
+    #[test]
     fn vm_stat_parser_is_strict_and_includes_no_caller_claim() {
         let text="Mach Virtual Memory Statistics: (page size of 16384 bytes)\nPages free: 500000.\nPages inactive: 500000.\nPages speculative: 100000.\n";
         assert_eq!(
diff --git a/scripts/research/f017_decoder_differential_v1.py b/scripts/research/f017_decoder_differential_v1.py
new file mode 100644
index 00000000..9f50597f
--- /dev/null
+++ b/scripts/research/f017_decoder_differential_v1.py
@@ -0,0 +1,115 @@
+#!/usr/bin/env python3
+"""Checkpoint-free decoder differential driver (glm52-weekend W3).
+
+Generates synthetic random blocks for every quantization format the GLM-5.2
+UD-IQ2_XXS checkpoint uses (validated through the corrected oracle's
+independent scalar decoders: non-finite scales are rejected and regenerated),
+writes them as a case file for the Rust producer
+(`f017-native-decoder-differential`, which runs the secure loader's exact
+decode dispatch), then compares the producer's f32 values with the oracle's
+binary64 values: exact-after-rounding count, max ULP distance, max absolute
+and relative error, and a permutation check. A harness negative control
+permutes two lanes of one oracle block and must be flagged.
+
+Usage: f017_decoder_differential_v1.py generate CASES_JSON [--seed N]
+       f017_decoder_differential_v1.py compare CASES_JSON PRODUCED_JSON REPORT_JSON
+"""
+from __future__ import annotations
+
+import json
+import math
+import os
+import random
+import struct
+import sys
+
+sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
+import f017_oracle_primary_decoders as oracle  # noqa: E402
+
+TYPE_IDS = {"F32": 0, "Q8_0": 8, "Q2_K": 10, "Q3_K": 11, "Q4_K": 12, "Q5_K": 13, "Q6_K": 14, "IQ2_XXS": 16, "IQ3_XXS": 18, "IQ2_S": 22, "IQ4_XS": 23}
+# checkpoint census (docs/research/glm52/raw/f016-c01-catalog-0001.json)
+FORMATS = ["F32", "Q8_0", "Q5_K", "IQ2_XXS", "Q6_K", "IQ3_XXS", "IQ4_XS", "Q4_K", "IQ2_S", "Q2_K", "Q3_K"]
+
+
+def valid_block(fmt: str, rng: random.Random) -> bytes:
+    values, nbytes = oracle.LAYOUT[fmt]
+    while True:
+        if fmt == "F32":
+            block = struct.pack("<f", rng.uniform(-4.0, 4.0))
+        else:
+            block = bytes(rng.getrandbits(8) for _ in range(nbytes))
+        try:
+            out = oracle._decode_block(fmt, block)
+        except (ValueError, IndexError):
+            continue
+        if len(out) == values and all(math.isfinite(v) and abs(v) < 1e4 for v in out):
+            return block
+
+
+def generate(path: str, seed: int) -> None:
+    rng = random.Random(seed)
+    cases = []
+    for fmt in FORMATS:
+        values, nbytes = oracle.LAYOUT[fmt]
+        for k, (rows, columns) in enumerate([(1, values * 2), (3, values * 4), (4, values * 8)]):
+            blocks = b"".join(valid_block(fmt, rng) for _ in range(rows * columns // values))
+            cases.append({"id": f"{fmt}-r{rows}-c{columns}-{k}", "format": fmt, "type_id": TYPE_IDS[fmt], "rows": rows, "columns": columns, "bytes_hex": blocks.hex()})
+    json.dump({"schema": "pulsarmlx.f017.decoder-differential-cases/1.0.0", "seed": seed, "formats": FORMATS, "cases": cases}, open(path, "w"), indent=1)
+    print(f"generated {len(cases)} cases for {len(FORMATS)} formats (seed {seed})")
+
+
+def ulp_distance(a: float, b32: float) -> int:
+    """ULP distance between the oracle value rounded to f32 and the produced f32."""
+    ra = struct.unpack("<f", struct.pack("<f", a))[0]
+    ia = struct.unpack("<i", struct.pack("<f", ra))[0]
+    ib = struct.unpack("<i", struct.pack("<f", b32))[0]
+    return abs(ia - ib)
+
+
+def compare(cases_path: str, produced_path: str, report_path: str) -> int:
+    cases = {c["id"]: c for c in json.load(open(cases_path))["cases"]}
+    produced = {d["id"]: d for d in json.load(open(produced_path))["decoded"]}
+    rows_out = []
+    worst = {}
+    for cid, c in cases.items():
+        p = produced.get(cid)
+        fmt = c["format"]; n = c["rows"] * c["columns"]
+        ref = oracle.decode(fmt, bytes.fromhex(c["bytes_hex"]), n)
+        row = {"id": cid, "format": fmt, "n": n}
+        if p is None or p["result"] != "OK":
+            row.update(status="PRODUCER_ERROR", error=(p or {}).get("error")); rows_out.append(row); continue
+        got = list(struct.unpack(f"<{n}f", bytes.fromhex(p["values_f32le_hex"])))
+        ulps = [ulp_distance(a, b) for a, b in zip(ref, got)]
+        abs_err = [abs(a - b) for a, b in zip(ref, got)]
+        rel = [abs(a - b) / abs(a) for a, b in zip(ref, got) if abs(a) > 1e-30]
+        exact = sum(1 for u in ulps if u == 0)
+        # permutation check: same multiset (rounded to f32) but different order -> lane permutation signature
+        same_multiset = sorted(struct.unpack("<f", struct.pack("<f", a))[0] for a in ref) == sorted(got)
+        row.update(status="MATCH" if max(ulps) <= 1 else "DIVERGENT", exact_f32=exact, max_ulp=max(ulps), max_abs=max(abs_err), max_rel=max(rel) if rel else 0.0, permutation_signature=(max(ulps) > 1 and same_multiset))
+        rows_out.append(row)
+        w = worst.setdefault(fmt, {"max_ulp": 0, "cases": 0, "divergent": 0, "exact_f32": 0, "n": 0})
+        w["max_ulp"] = max(w["max_ulp"], row["max_ulp"]); w["cases"] += 1; w["divergent"] += row["status"] == "DIVERGENT"; w["exact_f32"] += exact; w["n"] += n
+    # harness negative control: permute two lanes of the oracle output of one IQ3_XXS case; the comparison must flag it
+    ctrl_id = next(i for i in cases if cases[i]["format"] == "IQ3_XXS")
+    c = cases[ctrl_id]; n = c["rows"] * c["columns"]
+    ref = oracle.decode("IQ3_XXS", bytes.fromhex(c["bytes_hex"]), n)
+    got = list(struct.unpack(f"<{n}f", bytes.fromhex(produced[ctrl_id]["values_f32le_hex"])))
+    perm = got[:]
+    i, j = next(((a, b) for a in range(n) for b in range(a + 1, n) if perm[a] != perm[b]))
+    perm[i], perm[j] = perm[j], perm[i]
+    ctrl_flagged = max(ulp_distance(a, b) for a, b in zip(ref, perm)) > 1
+    verdict = "PASS" if all(r["status"] == "MATCH" for r in rows_out) and ctrl_flagged else "FAIL"
+    report = {"schema": "pulsarmlx.f017.decoder-differential-report/1.0.0", "oracle": "scripts/research/f017_oracle_primary_decoders.py (corrected oracle independent scalar decoders, binary64)", "producer": "f017-native decode_packed_matrix_for_qualification (secure loader dispatch)", "rule": "MATCH = every value within 1 ULP of the oracle value rounded to f32; DIVERGENT otherwise; permutation_signature = divergent with identical multiset", "per_format": worst, "cases": rows_out, "negative_control": {"case": ctrl_id, "mutation": f"oracle lanes {i} and {j} swapped in the comparison", "flagged": ctrl_flagged}, "verdict": verdict}
+    json.dump(report, open(report_path, "w"), indent=1)
+    print(json.dumps({"verdict": verdict, "per_format": worst, "negative_control_flagged": ctrl_flagged}, indent=1))
+    return 0 if verdict == "PASS" else 1
+
+
+if __name__ == "__main__":
+    if sys.argv[1] == "generate":
+        seed = int(sys.argv[sys.argv.index("--seed") + 1]) if "--seed" in sys.argv else 20260920
+        generate(sys.argv[2], seed)
+    elif sys.argv[1] == "compare":
+        sys.exit(compare(sys.argv[2], sys.argv[3], sys.argv[4]))
+    else:
+        raise SystemExit(__doc__)
diff --git a/scripts/research/f017_native_vs_corrected_oracle_v1.py b/scripts/research/f017_native_vs_corrected_oracle_v1.py
new file mode 100644
index 00000000..b26220e6
--- /dev/null
+++ b/scripts/research/f017_native_vs_corrected_oracle_v1.py
@@ -0,0 +1,82 @@
+#!/usr/bin/env python3
+"""Native full graph vs the corrected oracle's binary64 numerics (glm52-weekend W3, N3).
+
+Reuses the checkpoint-free full-graph differential fixture family (seeds
+17018-17023, `qualify_f017_native_synthetic_family_v1.build`), runs the native
+production orchestration on each fixture through the MLX bridge
+(`f017-native-synthetic-differential`, TENSOR_MATH_ONLY synthetic source), and
+compares its final hidden / final norm / logits / selected token and per-layer
+expert selection against `f017_corrected_oracle_primary_numerics_v3` (the
+Event 06 primary reference) fed the same tensors through its JsonSource. This
+is the first differential between the native graph and the CORRECTED oracle;
+the family's own local oracle is binary32 and was not the Event 06 authority.
+
+Usage: f017_native_vs_corrected_oracle_v1.py NATIVE_BIN WORK_DIR REPORT_JSON
+"""
+from __future__ import annotations
+
+import json
+import math
+import os
+import subprocess
+import sys
+
+sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
+import f017_corrected_oracle_primary_numerics_v3 as oracle  # noqa: E402
+import qualify_f017_native_synthetic_family_v1 as family  # noqa: E402
+
+# frozen thresholds of the corrected-oracle scientific-access contract (hex floats)
+MAX_ABS = float.fromhex("0x1.ab189fb800000p-8")
+RMSE = float.fromhex("0x1.c5fa0bf9cd9abp-9")
+COSINE_MIN = float.fromhex("0x1.fffffff380000p-1")
+
+
+def geometry_of(config: dict) -> oracle.Geometry:
+    return oracle.Geometry(layers=config["layer_count"], hidden=config["hidden"], vocab=config["vocab"], dense_layers=config["leading_dense_layers"], experts=config["expert_count"], top_k=config["expert_top_k"], dense_ffn=config["dense_ffn"], expert_ffn=config["expert_ffn"], heads=config["heads"], q_rank=config["q_rank"], kv_rank=config["kv_rank"], qk_nope=config["qk_nope"], qk_rope=config["qk_rope"], value_dim=config["value_dim"], rms_epsilon=config["rms_epsilon"], rope_base=config["rope_base"], route_scale=config["expert_weight_scale"])
+
+
+def json_source(fixture: dict) -> oracle.JsonSource:
+    tensors = dict(fixture["vectors"])
+    for name, m in fixture["matrices"].items():
+        tensors[name] = m["values"]
+    for e in fixture["expert_matrices"]:
+        tensors[f"{e['name']}#{e['expert']}"] = e["matrix"]["values"]
+    return oracle.JsonSource(tensors)
+
+
+def metrics(a: list[float], b: list[float]) -> dict:
+    n = len(a)
+    diff = [x - y for x, y in zip(a, b)]
+    dot = sum(x * y for x, y in zip(a, b)); na = math.sqrt(sum(x * x for x in a)); nb = math.sqrt(sum(y * y for y in b))
+    return {"max_abs": max(abs(d) for d in diff), "rmse": math.sqrt(sum(d * d for d in diff) / n), "cosine": dot / (na * nb) if na and nb else None}
+
+
+def main(native_bin: str, work: str, report_path: str) -> int:
+    os.makedirs(work, exist_ok=True)
+    rows = []
+    for seed in family.SEEDS:
+        fixture, _local, meta = family.build(seed)
+        fpath = os.path.join(work, f"fixture-{seed}.json")
+        json.dump(fixture, open(fpath, "w"))
+        p = subprocess.run([native_bin, fpath], capture_output=True, text=True, timeout=600)
+        if p.returncode != 0:
+            rows.append({"seed": seed, "status": "NATIVE_ERROR", "stderr": p.stderr[-500:]}); continue
+        native = json.loads(p.stdout)
+        json.dump(native, open(os.path.join(work, f"native-{seed}.json"), "w"))
+        state = oracle._execute_graph(json_source(fixture), geometry_of(fixture["config"]), fixture["prompt_token"], 0)
+        row = {"seed": seed, "case": meta, "native_token": native["result_token"], "oracle_token": state.selected, "fixture_expected_token": fixture["expected_token"],
+               "logits": metrics(state.logits, native["logits"]), "final_hidden": metrics(state.hidden, native["final_hidden"]), "final_norm": metrics(state.final_normalized, native["final_norm"]),
+               "expert_selection_identical": [c["selected_expert_ids"] for c in state.captures] == [l["selected_expert_ids"] for l in native["layers"]],
+               "oracle_top1_margin": state.logits[state.order[0]] - state.logits[state.order[1]]}
+        ok = row["native_token"] == row["oracle_token"] and row["expert_selection_identical"] and row["logits"]["max_abs"] <= MAX_ABS and row["logits"]["rmse"] <= RMSE and (row["logits"]["cosine"] or 0) >= COSINE_MIN
+        row["status"] = "PASS" if ok else "FAIL"
+        rows.append(row)
+    verdict = "PASS" if rows and all(r["status"] == "PASS" for r in rows) else "FAIL"
+    report = {"schema": "pulsarmlx.f017.native-vs-corrected-oracle-differential/1.0.0", "native_bin": os.path.basename(native_bin), "oracle": "scripts/research/f017_corrected_oracle_primary_numerics_v3.py (_execute_graph, binary64)", "fixture_family": "qualify_f017_native_synthetic_family_v1.build seeds 17018-17023 (hidden 4, vocab 16, 1-4 layers, 2-4 experts, tie and near-tie routing cases)", "thresholds": {"max_abs": MAX_ABS, "rmse": RMSE, "cosine_min": COSINE_MIN, "rule": "argmax equal AND expert selection identical per layer AND logits within the frozen thresholds"}, "rows": rows, "verdict": verdict, "scope": "synthetic f32 tensors (TENSOR_MATH_ONLY); no checkpoint; establishes graph agreement with the corrected oracle, not real-checkpoint agreement"}
+    json.dump(report, open(report_path, "w"), indent=1)
+    print(json.dumps({"verdict": verdict, "rows": [{k: r.get(k) for k in ("seed", "status", "native_token", "oracle_token", "expert_selection_identical")} | {"logits_max_abs": r.get("logits", {}).get("max_abs")} for r in rows]}, indent=1))
+    return 0 if verdict == "PASS" else 1
+
+
+if __name__ == "__main__":
+    sys.exit(main(*sys.argv[1:4]))
diff --git a/scripts/research/tests/test_f017_decoder_differential.py b/scripts/research/tests/test_f017_decoder_differential.py
new file mode 100644
index 00000000..08847382
--- /dev/null
+++ b/scripts/research/tests/test_f017_decoder_differential.py
@@ -0,0 +1,39 @@
+"""glm52-weekend W3: the decoder-differential driver generates valid synthetic blocks for every checkpoint format under the
+corrected oracle's independent decoders, and - when the Rust producer is built - the exact loader dispatch matches them
+bit-for-bit; the harness negative control (a lane swap) is flagged. Producer-dependent parts skip when the binary is absent."""
+import json
+import os
+import shutil
+import subprocess
+import sys
+import tempfile
+import unittest
+from pathlib import Path
+
+ROOT = Path(__file__).resolve().parents[3]
+DRIVER = ROOT / 'scripts/research/f017_decoder_differential_v1.py'
+BIN = os.environ.get('F017_DECODER_DIFFERENTIAL_BIN') or shutil.which('f017-native-decoder-differential')
+
+
+class DecoderDifferential(unittest.TestCase):
+    def test_generate_valid_cases_for_every_format(self):
+        d = tempfile.mkdtemp(); cases = Path(d) / 'cases.json'
+        p = subprocess.run([sys.executable, '-I', '-B', str(DRIVER), 'generate', str(cases), '--seed', '3'], capture_output=True, text=True, timeout=600)
+        self.assertEqual(p.returncode, 0, p.stderr[-500:])
+        c = json.load(open(cases)); self.assertEqual(len(c['formats']), 11); self.assertEqual(len(c['cases']), 33)
+        sys.path.insert(0, str(ROOT / 'scripts/research')); import f017_oracle_primary_decoders as oracle
+        for case in c['cases']:
+            vals = oracle.decode(case['format'], bytes.fromhex(case['bytes_hex']), case['rows'] * case['columns'])
+            self.assertEqual(len(vals), case['rows'] * case['columns'])
+
+    @unittest.skipUnless(BIN, 'f017-native-decoder-differential binary not available')
+    def test_producer_matches_oracle(self):
+        d = tempfile.mkdtemp(); cases, produced, report = (Path(d) / n for n in ('cases.json', 'produced.json', 'report.json'))
+        subprocess.run([sys.executable, '-I', '-B', str(DRIVER), 'generate', str(cases), '--seed', '11'], check=True, timeout=600)
+        subprocess.run([BIN, str(cases), str(produced)], check=True, timeout=600)
+        p = subprocess.run([sys.executable, '-I', '-B', str(DRIVER), 'compare', str(cases), str(produced), str(report)], capture_output=True, text=True, timeout=600)
+        self.assertEqual(p.returncode, 0, p.stdout[-800:]); r = json.load(open(report)); self.assertEqual(r['verdict'], 'PASS'); self.assertTrue(r['negative_control']['flagged'])
+
+
+if __name__ == '__main__':
+    unittest.main()

===== COMMITS =====
50a66db0d4fb8d80d9491e870dd2d3d8fa8e8ca6 f017: native bounded-P1 attempt-2 domain declaration v2 (PREPARED_HUMAN_GATE_REQUIRED): binds contract v3, the M1 Ultra-built executor, the corrected-oracle binding and the checkpoint-free reconciliation; lists the remaining pre-GO steps; no authorization
fec2f51666985deabf7a3791c45494ac0f8bad7d f017: admission contract v3 for native bounded-P1 attempt 2 (prepared, human gate required): executor f017-native-bounded-p1-v2 built on the M1 Ultra from 5e32d68f with the pinned MLX 0.31.2 keg and Homebrew rustc 1.97.1, corrected-oracle binding, evidenced v4 receipt; static validation negative controls recorded; no live authorization
5e32d68faa7b10168b9bb7f5d4fce6ebf212b737 f017: admission contract generation 3 for native bounded-P1 attempt 2 (weekend 2026-09-20 W3/N4): validate_static accepts schema 3.0.0 only with a bound corrected-oracle binding document (Event 06 token 154820, EXACT_EXPECTED_TOKEN_STABLE, evidenced v4 receipt); generation 2 rules unchanged; corrected-oracle binding document; M1 Ultra reproduction of the checkpoint-free differentials; no live authorization
63d56348551871a74a75c02178f2af29bd4a4d84 f017: checkpoint-free reconciliation of the native runtime with the corrected oracle (weekend 2026-09-20 W3): decoder differential producer over the exact loader dispatch vs the Event 06 independent scalar decoders (11 formats, 0 ULP, negative control flagged), native full-graph vs the corrected oracle binary64 numerics on the synthetic family (6/6), synthetic-differential bin declared; evidence banked append-only; no contract or tolerance changes
