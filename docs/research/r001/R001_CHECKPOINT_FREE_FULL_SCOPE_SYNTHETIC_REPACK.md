# R001 checkpoint-free full-scope synthetic repack qualification

## Result

`D6_FULL_SCOPE_SYNTHETIC_REPACK_QUALIFIED_PENDING_REVIEW`

This evidence qualifies the complete logical R001 object topology using tiny,
checkpoint-free synthetic source bytes. It does not qualify checkpoint access,
real model bytes, inference, model-output correctness, Event 05, Event 06, P1,
or a production full-store repack.

## Authority

- R001 implementation commit: `c17cc493babd4c929d9e39224973870694bd13cf`.
- Pinned R001 starting commit: `0fed99446e67b00b5b0af4bb63c5df856176228f`.
- Pinned R001 starting tree: `1f995004a00a1c67a9e9fea0be114bbdedccdbe7`.
- D6 policy ID: `f017-m2-d6-checkpoint-free-synthetic-repack-round-trip-v1`.
- D6 policy digest: `4f8e4e2c982dc71c477da455dc0029db73d813d60d60490f9690385fbdd39bcc`.
- Host class: MacBook Pro M2 Max, 64 GiB unified memory.
- Execution date: 2026-08-28.

The production prefix of `crates/repack/src/lib.rs` remained byte-identical to
the pinned starting authority. Both prefixes have SHA-256
`6da28077a6d82df1c5fba5cf81cdde992445fc3e03b3a94cc9637c41b9fcffc3`.
All D6 implementation changes are confined to the existing Rust test module.

## Complete synthetic scope

- Logical expert objects: 19,532.
- Components: 58,596, exactly gate/up/down for every object.
- Synthetic shards: 6.
- Bytes per component: 66.
- Synthetic source bytes: 3,867,336.
- Stored bytes per clean replay: 1,600,061,440.
- Temporary peak owned bytes: 3,203,990,216.
- Peak resident memory: 747,749,376 bytes.
- Plan identity: `350ee7d581b425658f800c96cc877abdebd56e945a560d615ddfb38091b8f75a`.

Checked source-window arithmetic proved every component in bounds. For each of
the six synthetic shards, sorted source windows began at byte zero, were exactly
adjacent without overlap or gap, and ended at the admitted shard length.

## Round-trip and determinism

The qualification performed:

1. One complete write and per-object source-mapping verification.
2. Manifest publication and independent test-path manifest audit.
3. One complete reuse pass requiring stable device, inode, size, and stored
   hash for every existing object.
4. One fresh complete replay into a separate output root.
5. Cross-run manifest, object-identity, and stored-representation comparison.
6. Exact removal of the graph-owned task root after all assertions passed.

The manifest auditor parsed canonical JSONL independently of manifest
publication. It reconciled every row against the corresponding bundle bytes,
verified the bundle wire format, recomputed stored hashes, checked canonical
payload and object identities, compared component descriptors, reconciled
header/footer totals, and verified the detached manifest hash.

Deterministic identities:

- Manifest SHA-256: `434fc5050c2fe65c19f776d72de61a6223ea46b85afb37e72f427a8484d1f164`.
- Object-identity aggregate SHA-256: `8a4056b62dd96ad56e604cca65e4132ae0d57dcff03e044fd2528d25a733d753`.
- Stored-identity aggregate SHA-256: `5352ef3c5e32eaf7d997e1031f7c91057ac6cde1bead671e1665a8437089bb72`.

These three identities matched the earlier qualification run exactly. Timing
and RSS were intentionally excluded from deterministic identity.

## Timing

| Phase | Seconds |
|---|---:|
| Plan and synthetic source construction | 4.555 |
| First complete write and verification | 1,057.905 |
| Existing-object reuse | 171.212 |
| Fresh complete replay and verification | 1,186.885 |
| First manifest audit | 172.012 |
| Final cleanup | 2.852 |
| Total | 2,595.717 |

These are checkpoint-free test-harness timings, not checkpoint repack,
storage, inference, or production performance claims.

## Safety and negative coverage

- The task root was a unique, empty, mode-0700 directory outside the repository.
- Admission rejected symlinked, non-empty, and repository-nested task roots.
- Cleanup was pinned to the admitted directory identity and refused identity
  substitution.
- Output and staging roots were created exclusively beneath that task root.
- The test rejected unexpected symlinks and non-file output entries.
- No checkpoint alias, checkpoint path, external volume, network volume, or
  inference entry point was accessed.
- No full repack or production CLI invocation occurred.
- The final task root did not exist after successful cleanup.

A non-ignored falsification test rejects truncated manifests, extra or duplicate
rows, detached-hash mutation, and bundle/manifest disagreement. Existing R001
tests continue to reject overflow, out-of-bounds components, duplicate roles,
unsafe paths, stale identities, unexplained partials, interrupted publication,
corruption, and unsafe reuse.

## Validation

- Full-scope ignored qualification: 1 passed in 2,596.06 seconds.
- Normal Rust library suite: 31 passed, 1 expected ignored.
- Independent Python verifier contract: 6 passed.
- Rust clippy with warnings denied: passed.
- Rust formatting check for the touched file: passed.
- Git diff whitespace check: passed.
- Repair loops consumed: 2 of 5 authorized; one syntax repair and one audit
  hardening repair.

Sanitized invocation:

```sh
PULSARMLX_D6_TASK_ROOT="$D6_TASK_ROOT" \
PULSARMLX_D6_RESULT_PATH="$GRAPH_STATE/full-scope-result.json" \
cargo test -p repack --lib \
  d6_full_scope_checkpoint_free_synthetic_repack -- --ignored --nocapture
```

## Limitation and next gate

This test exercises all 19,532 logical objects and 58,596 component mappings,
but each component contains only 66 deterministic synthetic bytes. It proves
complete-scope planning, object publication, manifest accounting, deterministic
replay, bounded temporary storage, source-window coverage, reuse, and cleanup.
It does not prove behavior against the original checkpoint or authorize a
checkpoint-bearing full repack. The next gate is an independent review of this
D6 evidence and policy-governed admission of any later checkpoint-bearing work.
