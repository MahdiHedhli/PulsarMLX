# F017 attempt-1 offline forensics — cross-vendor disagreement review

Review committed repository bytes only. This is a checkpoint-free, advisory disagreement search. Do not open the original checkpoint, execute P1, create an authorization, mutate the repository, or treat attempt 1 as retryable.

## Reviewer

- Required mechanism: AGY CLI
- Required model: `gemini-3.1-pro-high`
- Required effort: high
- Fresh invocation at a clean detached worktree
- Finding severities: `BLOCKING`, `NON_BLOCKING_REQUIRED`, `DEFENSE_IN_DEPTH`
- Return exactly `ADVISORY_CONCUR` or `ADVISORY_DISAGREE`.

## Authority

- Branch: `feat/017-rust-native-inference-runtime`
- Program starting head: `1c231dbfc545af59a1e4e428db3c25b67ceb2697`
- Offline implementation head: `59538ccb15ae4d13e42e2ab91d790fbb295c5524`
- Attempt-1 implementation: `e3fd6ca64f299e3b2293e0522c46fa66ebe09b13`
- Attempt-1 execution-code head: `4faa404c4205d172251436781b6d54042e8409f6`
- Attempt-1 evidence SHA-256: `c3dcc92cec8fde419bfdb437e0191a768fce8f48fc78b2e4b78171164caafb7b`
- Attempt-1 terminal SHA-256: `de5f918324048fec8e49d63a60d9db6ba536171f4e1ea0dae6f5e5ddfdf7a6ed`
- Historical master ledger: 175, SHA-256 `aa98f5cc7f1cfae1eb49a9bc64dbefec1d6ef9ccae1504a1aa8879a8edf22e3e`
- Exact-head CI: run `32590049780`; independently require conclusion success at implementation head `59538ccb15ae4d13e42e2ab91d790fbb295c5524`.

Recompute these and every load-bearing artifact hash. Git and direct CI evidence outrank this request.

## Principal claims to attack

1. Attempt 1 is immutable, consumed, terminal, not retryable, and produced exactly one observed token `17351` rather than frozen expected token `21615`.
2. No receipt, durable pre/post snapshots, or durable access census exists for attempt 1; the package does not fabricate them.
3. Forward v3 execution persists pre/post 22-counter snapshots, incremental shard/map/tensor-use access events, production-buffer diagnostics, one truthful receipt, and receipt-bound terminal evidence on token mismatch and other safely receiptable post-start failures.
4. The expected-token authority is defective: the F016 provenance used Python decoder semantics with independently reproducible Q6_K lane-order and IQ3_XXS grid-order defects. This disproves `21615` as a valid oracle but does not establish `17351` as correct.
5. Native decoders agree with corrected independent semantics across 11 formats and 44 adversarial cases; native MLX matvec results satisfy pre-frozen OCB caps.
6. Metadata-only checkpoint planning validates 1,809 tensors, 79 layers, 256 experts, six shards, format/type-ID/decoder agreement, bounds, alignment, non-overlap, and graph constants without opening checkpoint payload.
7. Expanded independent synthetic full-graph qualification passes six predeclared seeds and 137 stage metrics using the production orchestration with only the tensor source substituted.
8. Static graph/context/tensor-orientation audit found no proven native topology defect. It records proof/reference-versus-native f64/f32 distinctions instead of conflating them.
9. Root cause is `ROOT_CAUSE_HIGH_CONFIDENCE_NOT_PROVEN`: affected decoder authority makes oracle defect likely, but missing attempt-1 layer fingerprints and lack of a corrected independent full-checkpoint oracle prevent exact causation.
10. Readiness for attempt-2 authorization preparation remains NO.

## Required attacks

- Trace expected token `21615` to its source, checkpoint, context, BOS/KV/RoPE, greedy policy, decoder family, and independence boundary.
- Reproduce or mechanically inspect Q6_K and IQ3_XXS old-versus-corrected decoder differences. Reject a conclusion inferred only from prose.
- Attack every 11-format case, type-ID dispatch, block geometry, signed/scaled edge, malformed length, and native matvec tolerance.
- Attack the 1,809-tensor metadata plan for duplicate names, out-of-bounds end offsets, overlap, bad alignment, shard mismatch, type-ID/format mismatch, unsupported fallback, missing layers/experts, and wrong architecture constants.
- Compare native and independent graph semantics through embedding, all 79 layers, MLA/RoPE/mask/softmax, routing, experts, residuals, final norm, output projection, logits, and argmax.
- Check that the synthetic oracle is non-Rust/non-MLX and that the production layer loop is used.
- Try the wrong-RoPE, projection transpose, route ordering, expert slot, normalization, layer-count, final norm, output orientation, decoder, and offset mutations; verify earliest divergence is detected.
- Inspect forward v3 failure injection for claim/start ordering, fsync/no-replace durability, token mismatch evidence, access census, receipt/terminal hashes, RN1 ownership, receipt-write and terminal-write faults, retry/resume absence, and attempt-1 non-retroactivity.
- Attack CI classification false negatives, mixed changes, unknown-default-full behavior, evidence validation, closed-branch guard, concurrency, and exact-head full-CI preservation.
- Verify no original shard open/mmap/payload read, new authorization, attempt 2, or further real inference occurred.

## Required response

Report reviewed branch/head, model/invocation, independently rerun tests, stable findings and severities, material disagreements, and exact verdict. A disagreement about exact causation is expected only if supported by stronger evidence; do not convert the defective expected-token oracle into proof that native output was correct.
