# F017 Attempt‑1 Offline Forensics — Independent Review

## Reviewer and session

| Field | Value |
|---|---|
| Model | `claude-opus-5` |
| Effort | high |
| Session | fresh CLI, no continuation |
| Worktree | `/private/tmp/pulsarmlx-f017-offline-review-c749`, detached, `git status --porcelain` empty at start and end |
| Reviewed head | `c749f2a85c7aefe2d1f8a73567c6dcb05d68eefb` |
| Reviewed implementation head | `59538ccb15ae4d13e42e2ab91d790fbb295c5524` |
| Branch | `feat/017-rust-native-inference-runtime` |

**Tests rerun: 0.** `python3`, `pytest`, `cargo`, `gh`, `shasum`, `openssl` are all denied by this session's permission mode. `sha256sum`, `git` (read-only subcommands), `grep`, `ls`, `find` are permitted. This review is therefore a byte-level and source-level audit, not a re-execution. Three disclosed gaps follow at the end.

## Authority recomputation

`59538ccb..c749f2a8` is **6 files, 384 insertions, 0 deletions**, all under `docs/architecture/reviews/evidence/` — append-only review packaging, no implementation change. Confirmed.

Every pinned digest recomputed independently with `sha256sum`. **All match:**

- All 12 load-bearing package files (postmortem `cc12c072…`, provenance `87711d80…`, static differential `8c499644…`, plan audit `92124280…`, quant matrix `73ce2bf3…`, synthetic `776fe48c…`, inventory `18a514ff…`, hypothesis ledger `ed733659…`, injection `029afd80…`, corrected Q‑quant `af51990d…`, corrected IQ3 `93e97954…`)
- Admission `91248295…`, execution evidence `c3dcc92c…`, terminal `de5f9183…`
- All 4 Gemini artifacts (`57d55eba…`, `eb2bf610…`, `bc9fa509…`, `3fad33c6…`)
- Historical ledger `aa98f5cc…` verified **cross-branch** at `feat/017-real-checkpoint-runner@f2a7aa38c96b85cf7939c8ed653076732f066222`; `receipt_chain.terminal_count` read from those bytes = **175**, gaps 0

## Attempt‑1 immutability

All 12 authority-inventory artifacts recompute byte-exact. Owned claim and durable start are genuinely the same bytes (`35d95dac…`). Terminal is `TERMINAL_FAILURE_NO_RETRY`, `receipt_count: 0`, `receipt_sha256: null`, `retry_permitted: false`. No attempt‑2 or retry artifact exists anywhere in the tree.

**Independent corroboration, not just self-report:** the banked terminal's exact shape — v1 schema, `receipt_count: 0`, `receipt_sha256: null`, owner-pid-and-nonce binding — is precisely what `execute_bounded_p1_impl`'s failure arm (`p1_domain.rs:952-955`) emits. And `validate_accounting` runs at `p1_domain.rs:892`, *before* the token comparison at `:893`. Since the recorded stderr is the token-mismatch message, control flow provably passed accounting validation. The postmortem's `MECHANICALLY_IMPLIED_PASS_BY_CONTROL_FLOW` is a sound inference, correctly separated from the `accounting_closure: FAIL` (durable) verdict.

Facts vs. inference are cleanly separated throughout; the 8 `unknown_facts` and 7 `contract_nonconformities` are accurate and self-incriminating rather than minimising.

## Expected token and root cause

I inspected the pre-repair decoders at `e329c54d~1` and at the F016 authority commit `99751b9c`; both hash to `1e578385…`/`316ab363…`, exactly as the provenance claims. The historical source surface is truthfully stated.

**Q6_K defect — real.** Upstream ggml pairs `ql[l]`-low↔qh[0:2]→y[l], `ql[l+32]`-low↔qh[2:4]→y[l+32], `ql[l]`-high↔qh[4:6]→y[l+64], `ql[l+32]`-high↔qh[6:8]→y[l+96]. The old code paired `ql[l]`-high with qh[2:4] and `ql[l+32]`-low with qh[4:6]. The repaired code reproduces upstream exactly, including the scale index (`scales[index//16]` = `sc[8·half + 2·quarter + lane//16]`). Verified by hand.

**IQ3_XXS defect — real.** Old code interleaved `b1[j], b2[j]`; ggml emits four from grid1 then four from grid2. Repair restores this, and the numpy path's two compensating transposes are correctly removed.

**Dependency proven, not asserted.** `glm52_dense_primitives.py:103` and `glm52_expert.py:40,52` dispatch to these decoders, and the catalog shows `blk.0.ffn_down.weight`, `blk.1.ffn_down.weight`, `blk.2.ffn_down.weight` are **Q6_K** — the leading-dense-layer FFN down projections, unavoidably on the single-token forward path. Token 21615 was therefore computed through a mis-decode. `EXPECTED_TOKEN_AUTHORITY_DEFECT_PROVEN` is **upheld**.

**Causation is not proven, and the package is right not to claim it.** The quant matrix shows native Rust decoders bit-exact against the *repaired* oracle across 44 cases, which points at the oracle — but `model.rs:265` applies the route weight *before* the down projection while F016 applies it after (`route_weight_application`, self-reported as needing a dedicated mutation test that does not yet exist), and 79 layers of serial-binary32 composition is unquantified (H13). Candidate defects exist on both sides. `ROOT_CAUSE_HIGH_CONFIDENCE_NOT_PROVEN` is **upheld**. `17351` is not promoted anywhere. The 15-hypothesis ledger is genuinely comprehensive and its dispositions are supported.

I also confirmed a fact that *narrows* causation and is honestly disclosed but under-emphasised: with one visible key the attention softmax is 1, `values` bypasses any weighting, and the computed score is discarded after a finiteness check (`model.rs:392-408`). The entire Q chain, `k_b`, and RoPE are therefore output-irrelevant for attempt 1 — matching the static audit's `OUTPUT_IRRELEVANT_FOR_ONE_VISIBLE_KEY` and `POSITION_ZERO_IDENTITY_ONLY` rows.

## Full graph, plan, quantization, synthetic

- 79 layers (`0..layer_count`), 256 experts, top‑k 8, `expert_weight_scale` 2.5, route floor 2⁻¹⁴, lower-ID tie in both routing and argmax (`max_by` with reversed index comparator correctly returns the lowest index).
- Plan audit: quant format counts sum to **exactly 1809**; Q6_K = 82 and IQ3_XXS = 71 match the provenance's affected-tensor counts. `audit_f017_native_checkpoint_plan.py` accepts only `manifest`, `catalog`, `--output` — no checkpoint root argument exists.
- Quantization: 11 formats × 4 case modes = **44**, all `decoder_max_abs_error 0.0` / exact f32 bits, all native matvecs within frozen OCB. The oracle imports only pure-Python decoders; the Rust binary is invoked as the *comparand*, never as the oracle.
- Synthetic: 6 predeclared seeds, stage metrics 10+17+24+31+24+31 = **137**, with route/tie/near-tie variation and mutation localization that includes both real defects.

## Forward failure evidence (v3)

Audited the producer, not just the validator. Durability order in `execute_evidenced_bounded_p1_once` is correct: claim → pre-snapshot → recorder → math+sync → post-snapshot → census → diagnostic manifest → accounting → classification → one receipt → receipt-bound terminal → *then* return `Err`. `write_exclusive` uses `create_new(true)` + `sync_all` + parent fsync; `terminalize_evidenced` re-hashes all five artifacts from disk and rejects any mismatch; `still_owns()` binds pid, nonce, and both IDs. Receipt-write failure propagates before terminalization (no fabricated receipt); terminal-write failure leaves the receipt durable. The four named tests exist and do what they claim, including path-escape rejection with `!root.exists()`. Diagnostics are direct production-buffer hashes, banked per layer with a genuine byte-comparison readback. Attempt 1 is explicitly nonconforming, never retroactively repaired.

## CI adjudication

`gh` is denied, so **I could not directly verify run `32590049780` or the other six runs.** I audited the routing logic from committed bytes instead, and verified the four CI tooling digests recorded in the routing-acceptance file (`7aa2b4ef…`, `9b740464…`, `db886bf4…`, `a58c4a71…`) all match the actual files.

What holds up: unknown/mixed/evidence+docs → `FULL_NATIVE`; manual `evidence` override raises rather than downgrading a code classification; renames feed both sides into classification and are outright rejected by the evidence validator; evidence must be `100644` (symlinks and executables rejected); append-only is enforced by status code, which also closes the `ATTEMPT_FLAG` deletion path I probed; duplicate JSON keys rejected; aggregate runs `if: always()` and asserts both macOS jobs are `skipped` in `EVIDENCE_ONLY` — so **evidence mode provably starts no Apple native/MLX/research job**. `branch_protection_detected: false` is honestly disclosed: the aggregate is not a required check.

One caveat on the exact-head claim, stated without overreach: `cancel-in-progress: true` on a `workflow/ref` group, with pushes at 14:12:19, 14:22:12 and 14:29:56, creates a plausible cancellation window for a `FULL_NATIVE` run that builds MLX from source. A GitHub re-run preserves the SHA, so this does not imply different bytes were tested — but the committed record carries no run attempt, timestamps, or event provenance to settle it, and it was written in a commit *after* the head it attests to.

## Findings

All findings are **DEFENSE_IN_DEPTH**. No `BLOCKING` or `NON_BLOCKING_REQUIRED` finding survived verification.

| # | Path | Failure mode | Repair |
|---|---|---|---|
| 1 | `.github/workflows/macos.yml:213` | `scripts/ci/tests/` (18+5 tests) is invoked by **no** CI mode; `discover` targets only `scripts/research/tests`. The fail-closed gate is itself unqualified. | Add `scripts/ci/tests` to a job that runs in `FULL_NATIVE`. |
| 2 | `.github/workflows/macos.yml:66-94` | `validate_f017_attempt1_evidence` runs only in `EVIDENCE_ONLY`. A commit touching `crates/**` *and* attempt‑1 evidence routes `FULL_NATIVE`, which never checks immutability. | Run the attempt‑1 validator unconditionally in the classify job. |
| 3 | `.github/workflows/macos.yml:112` | `--diff-filter=AM` excludes type-change `T`, and `grep 'mode 120000'` misses `mode change 100644 => 120000`. A docs file can become a symlink. Bounded: evidence root is excluded from `DOCS_ONLY`. | Use `git ls-tree` mode inspection, as the evidence validator already does. |
| 4 | `.github/workflows/macos.yml:52-54` | On a new-branch first push `BASE_SHA` falls back to `HEAD^`, so a multi-commit push classifies only the tip. | Fall back to merge-base against the default branch. |
| 5 | `scripts/ci/validate_evidence_change.py:117-127, 78-80` | `_walk_bindings` only resolves nested `{path,sha256}` objects. Sibling-prefixed pairs (`terminal_path`/`terminal_sha256`, used throughout the native event ledger) are never validated; a malformed sha silently returns `False` instead of failing. | Resolve `<prefix>_path`/`<prefix>_sha256` pairs; fail on malformed sha rather than skipping. |
| 6 | `crates/stream/src/p1_domain.rs:373,420,962` | The advertised "SHA readback" is `sha256(path).len() != 64` — always true. It never compares to the intended content. `DiagnosticObserver::bank_layer` does compare bytes; the generic path does not. | Compare re-read bytes to the serialized buffer, as `executor.rs:131` does. |
| 7 | `crates/stream/src/p1_domain.rs:388-400,439-451` | `FALLBACK_ATTEMPT`, `ALTERNATE_ROOT_ATTEMPT`, `PAGE_RESIDENCY_OBSERVATION`, `HISTORICAL_EXPLICIT_PAYLOAD_EXTRACTION` are declared but emitted nowhere in `crates/`. Their `0` counts read as "detected none" when no detector exists. | Emit them, or annotate the census that these counters have no producer. |
| 8 | `bin/bounded_p1.rs:67-93` + contract `:217` | The contract declares `receipt_schema 2.0.0`, so `execute-evidenced-v3` is gated off and the legacy receipt-less-on-failure `execute` is the only runnable real-event path. `NEW_EXECUTOR_GENERATION_EMITS_FAILURE_RECEIPTS` is not mechanically enforced at the entry point. | Delete the `execute` real-event arm when the contract moves to 3.0.0. |
| 9 | `…forward-failure-injection-v3.json:57-66` | `RECEIPT_WRITE_PHYSICAL_FAILURE` and `TERMINAL_WRITE_PHYSICAL_FAILURE` are argued by mechanism with no test. I verified both by inspection; they hold. | Add fault-injection tests, or label these two as inspection-only. |
| 10 | `…expected-token-provenance-v1.json:91` | "swapped logical coordinate groups 32..63 and 64..95" understates the Q6_K defect — it was not a clean swap; the old values mixed ql nibbles with mismatched qh bit-fields *and* wrong scale indices, so they correspond to no correct coordinate. | Correct the wording; the defect is real and larger than described. |

## Cross-vendor disagreement search

Recomputed, not inherited. All four Gemini artifacts hash to their pins; the committed report is internally consistent with the exact CLI response and the normalized result. The envelope is genuinely `status: ERROR` / `error: "context canceled"` with a complete response body, and this is disclosed rather than normalized away.

The scope disposition is **sound**. Gemini's two `BLOCKING` items (defective 21615; attempt 1 terminal / attempt 2 unauthorized) and its `NON_BLOCKING_REQUIRED` item (causation unproven) are restatements of the package's own conclusions, not defects *in* the package. Routing them to `FUTURE_ATTEMPT_2` is correct, not evasive. I found **no material disagreement** with Gemini, and no finding Gemini raised that the package fails to already state itself.

## Safety counters

```
P1_ATTEMPT_1_RETRY: NO
P1_ATTEMPT_2_EXECUTED: NO
LIVE_P1_ATTEMPT_2_AUTHORIZATION_CREATED: NO
NEW_ORIGINAL_CHECKPOINT_SHARD_OPENS: 0
NEW_ORIGINAL_CHECKPOINT_PAYLOAD_READS: 0
FURTHER_REAL_INFERENCE_EXECUTED: NO
HISTORICAL_MASTER_LEDGER: 175
```

No P1 execution, no checkpoint shard opened or mapped, no authorization minted, no evidence mutated. Worktree clean and HEAD unchanged at exit.

## Disclosed verification gaps

1. **CI not directly verified.** `gh` denied. Run `32590049780` and the six other runs are unconfirmed by me; I audited the workflow logic and tooling digests instead. If your charter requires direct CI confirmation, this single item must be closed by someone with CI access.
2. **Zero tests rerun.** `python3`/`pytest`/`cargo` denied.
3. **Machine-local state not inspected.** Reads outside the worktree denied. Attempt‑2 absence is established from committed bytes and from the fact that I created nothing.

## Readiness

`READY_TO_PREPARE_P1_ATTEMPT_2_AUTHORIZATION: NO` — **upheld, independently.** The smallest blocker asserted is correct: there is no corrected independent full-checkpoint expected-token authority, and attempt 1 retained no per-layer fingerprints. A source difference is not exact causation, and finding #8 shows the corrected-executor criterion is not yet mechanically enforced. Usefully, this is also enforced by construction: `stream::EXPECTED_TOKEN` is hard-coded to `21615` and `validate_authority` rejects anything else, so no attempt 2 can run against a corrected token without new code, new CI, and new human authorization.

## Verdict

The three challenged classifications all survive independent attack. Every recomputable pin matches. The ten findings are hardening items against future control surfaces; none contradicts a committed claim, and none prevents acceptance.

**ACCEPT_F017_ATTEMPT_1_OFFLINE_FORENSICS**
