# F017 attempt-1 offline forensics — final independent review

Perform a fresh, high-effort review of committed bytes at a clean detached worktree. Do not execute P1, open or map original checkpoint shards, create a live authorization, mutate evidence, or infer retry authority.

## Reviewer and decision

- Required model: `claude-opus-5`
- Effort: high
- Fresh CLI session, no continuation
- Severities: `BLOCKING`, `NON_BLOCKING_REQUIRED`, `DEFENSE_IN_DEPTH`
- `BLOCKING` and `NON_BLOCKING_REQUIRED` prevent acceptance.
- Return exactly `ACCEPT_F017_ATTEMPT_1_OFFLINE_FORENSICS` or `REJECT`.
- Acceptance of this offline phase does not require attempt-2 readiness. Independently decide readiness and require it to remain NO unless the exact root cause and corrected expected-token authority are proven.

## Pinned authority

- Branch: `feat/017-rust-native-inference-runtime`
- Program start: `1c231dbfc545af59a1e4e428db3c25b67ceb2697`
- Offline implementation head: `59538ccb15ae4d13e42e2ab91d790fbb295c5524`
- Attempt-1 implementation: `e3fd6ca64f299e3b2293e0522c46fa66ebe09b13`
- Attempt-1 execution code: `4faa404c4205d172251436781b6d54042e8409f6`
- Admission SHA-256: `91248295cac2f078e47576e5f22b4f7d0457bf9b3b11645c8e46406b8b1a2e03`
- Execution evidence SHA-256: `c3dcc92cec8fde419bfdb437e0191a768fce8f48fc78b2e4b78171164caafb7b`
- Terminal SHA-256: `de5f918324048fec8e49d63a60d9db6ba536171f4e1ea0dae6f5e5ddfdf7a6ed`
- Historical ledger SHA-256: `aa98f5cc7f1cfae1eb49a9bc64dbefec1d6ef9ccae1504a1aa8879a8edf22e3e`, terminal 175
- Exact-head full CI: `32590049780`; verify directly that it succeeded at `59538ccb15ae4d13e42e2ab91d790fbb295c5524`.

Recompute all values from Git and direct CI evidence. Treat later evidence commits as append-only review packaging, not implementation changes.

## Cross-vendor disagreement search

Gemini 3.1 Pro High was invoked through AGY against the same implementation. Recompute rather than inherit its conclusion:

- request SHA-256 `57d55ebab972157b0f70a77c6a4acb5ee44771ed7697fd5d26ca760465fae479`;
- exact CLI response SHA-256 `eb2bf610d3ec4ee18b8f08705edd4e77e3b94d20f12849eb8bc581003077cd7e`;
- detailed report SHA-256 `bc9fa5096275eb520c955536eb7077cb56ad9ff8457410aa651775b6fee20caa`;
- normalized result SHA-256 `3fad33c6f2e7c3c1a8e55f8f81d3a067d5a98174bb76864ad980d8390440584e`;
- advisory verdict `ADVISORY_CONCUR`.

The AGY CLI envelope ended `ERROR_CONTEXT_CANCELED_AFTER_COMPLETE_RESPONSE`; this is disclosed, not normalized away. Gemini labeled the defective expected oracle, immutable attempt status, and unresolved causation as blocking/required for a future attempt 2 while expressly reporting no material disagreement with this offline package. Decide independently whether that scope disposition is sound.

## Load-bearing package

Recompute and review at least:

- canonical postmortem SHA `cc12c072d5de45347c855bf316eb407d852ee4622874d0b762baedeead312d18`;
- expected-token provenance SHA `87711d80ebdea2a875b8d45e49a34cbffb97ce285d129cbd9db7658228f44aa2`;
- static differential audit SHA `8c49964454cfdd0bb59f33cd15772ebcddb19a7ab6d85c01f6bb603cc0ba10d6`;
- checkpoint-plan audit SHA `92124280fe47e877619204b1956c565c915288797c19b2345f50e30300134b6f`;
- quantization matrix SHA `73ce2bf3ed6b9fc927c45413da0c51a321e92e6cec4815bd31cedd4bec9e480e`;
- expanded synthetic differential SHA `776fe48c60eb3e9b14702f2b1e5d088078a7576b1c61df0fbc11d63eff935fc7`;
- retained inventory SHA `18a514ffd5d1209a1a06c83e10ab6580cf6e3812333a4a244cb89d00719dae5e`;
- hypothesis ledger SHA `ed7336598296fd2ced46c6c3fb0abd62d4eacbaf50d8f86fb5a183349237267a`;
- forward failure injection SHA `029afd80895f3891fdcac98378b00d3bd86c0c5910ffcab48fed504c35243e7e`;
- corrected Q-quant oracle source SHA `af51990d2605e604b4c81b6d49d7efc8f213f5315489c0d31d5128dbf113e236`;
- corrected IQ3 source SHA `93e979548ba6e973f504643715708f6cfcb528f777a338d41e8b3c4e2bf78de5`.

## Mandatory attacks

### Attempt-1 immutability

Verify authorization, owned claim/start, terminal, execution evidence, event ledger, Opus post-execution review, consumed root, no retry, no attempt 2, and no fabricated receipt/snapshots/access census. Separate facts from inferences.

### Evidence-aware CI

Inspect incident run `32448819034`, classifier/workflow/evidence validator/tests, active full run `32586197701`, active evidence run `32586691805`, historical guard run `32586291587`, historical evidence run `32586543464`, and final exact implementation run `32590049780`. Attack evidence/docs false negatives, mixed and unknown paths, workflow dispatch overrides, changed symlinks, duplicate JSON keys, immutable-artifact edits, branch/head binding, closed historical branch behavior, required aggregate status, and concurrency cancellation. Verify evidence mode starts no Apple native/MLX/research job.

### Forward failure evidence

Inspect the real producer path and schemas, not only validators. Attack every failure-injection boundary. Require no-replace/fsync/readback for pre/post snapshots; incremental shard-open, mmap, logical lookup/first/repeat use and unauthorized/fallback events; direct production-buffer diagnostics; one truthful receipt; terminal receipt/snapshot/access/diagnostic SHA binding; receipt-derived accounting; RN1 owned terminalization; and token-mismatch durability before comparison. Confirm physical receipt-write failure is represented without inventing a receipt, terminal-write failure preserves the receipt for reconciliation, and attempt 1 is explicitly nonconforming rather than retroactively repaired.

### Expected token and root cause

Reconstruct `21615` including checkpoint/context/BOS/KV/RoPE/argmax and oracle independence. Independently inspect the old F016 Q6_K and IQ3_XXS decoders and corrected semantics. Determine whether the evidence proves only an oracle defect or also proves exact causation. Do not promote `17351` absent independent authority.

### Full graph and plan

Audit embedding through all 79 native layers, attention/MLA/RoPE, routing, 256 experts, residuals, final norm, output projection, logits, argmax, and mandatory stop. Audit metadata-only six-shard/1,809-tensor census for names, roles, shapes, formats/type IDs, offsets, byte counts, alignment, overlap, bounds, decoder and consumer coverage without opening checkpoint payload.

### Quantization and synthetic qualification

Attack all 11 formats (`F32`, `Q2_K`, `Q3_K`, `Q4_K`, `Q5_K`, `Q6_K`, `Q8_0`, `IQ2_S`, `IQ2_XXS`, `IQ3_XXS`, `IQ4_XS`), 44 adversarial blocks, malformed sizes, signed/scaled boundaries, decoder dispatch and native MLX matvec OCB. Verify the independent oracle does not call Rust/MLX/checkpoint code. Verify six predeclared full-graph seeds, 137 metrics, route/context/format variation, production orchestration, and mutation localization.

### Retained evidence and safety

Confirm no useful additional retained artifact was read without a consumer grant, that existing layer-3 D3.5 evidence cannot establish full-forward correctness, and that no original checkpoint shard was opened/mapped/read. Confirm no new live authorization, P1 attempt 2, or further real inference.

### Classifications

Challenge these exact conclusions:

- `EXPECTED_TOKEN_AUTHORITY_DEFECT_PROVEN`
- `ROOT_CAUSE_HIGH_CONFIDENCE_NOT_PROVEN`
- `READY_TO_PREPARE_P1_ATTEMPT_2_AUTHORIZATION: NO`

The smallest blocker asserted is the absence of a corrected independent full-checkpoint expected-token authority and attempt-1 localization evidence. A source difference alone is not exact causation.

## Required response

Report reviewer identity/session, reviewed branch/head, tests rerun, stable findings with severity/path/evidence/failure mode/required repair, CI adjudication, expected-token disposition, root-cause classification, safety counters, readiness, and exact verdict. Explicitly state:

- `P1_ATTEMPT_1_RETRY: NO`
- `P1_ATTEMPT_2_EXECUTED: NO`
- `LIVE_P1_ATTEMPT_2_AUTHORIZATION_CREATED: NO`
- `NEW_ORIGINAL_CHECKPOINT_SHARD_OPENS: 0`
- `NEW_ORIGINAL_CHECKPOINT_PAYLOAD_READS: 0`
- `FURTHER_REAL_INFERENCE_EXECUTED: NO`
- `HISTORICAL_MASTER_LEDGER: 175`
