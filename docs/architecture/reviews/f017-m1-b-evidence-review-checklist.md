# F017 M1-B Evidence Review Checklist

Status: **PREPARED / NOT AUTHORIZED**

## Source and environment

- [ ] Executed source is exactly
  `b29202171a279cd3bb2ac2cf4dc6b3be7486019e`; the M1-A evidence commit
  `91359dd59265de71fd25848142af23823e41e160` is provenance, not the runtime pin.
- [ ] Source worktree was clean.
- [ ] Environment kind is `production_reviewed` and the manifest hash is exact.
- [ ] Telemetry source is `measured_host`; all admission gates passed.
- [ ] Actual arm64 `libmlx.dylib` and `libmlxc.dylib` hashes match expected.

## Checkpoint identity

- [ ] Exactly six canonical shards are present.
- [ ] Private checkpoint manifest SHA-256 is exactly
  `208969118007ec0ae6e6b49f45f3d253b3bac7824b7f8f495a1fef1bcea844d4`.
- [ ] Every filename, byte size, and SHA-256 matches the reviewed manifest.
- [ ] Checkpoint-set SHA-256 and immutable revision match.
- [ ] Checkpoint-set SHA-256 is exactly
  `d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee`.
- [ ] Catalog SHA-256 is exactly
  `0f0425106a240c5062acab9fc41b1b2651680c6ad06fe476214f88a8d2a177f0`.
- [ ] GGUF architecture is `glm-dsa`.
- [ ] Tokenizer identity matches the reviewed exact-token contract.
- [ ] Catalog identity and tensor count match.
- [ ] `Glm52TensorMap` status is `validated`.
- [ ] Exactly 79 layers and 1,809 tensor contracts validate.
- [ ] Tensor names, shapes, quantizations, and required metadata are complete.

## Isolation

- [ ] No tensor decode occurred.
- [ ] No tensor execution range was read.
- [ ] No `MlxContext` compute state was created.
- [ ] No projection, expert, layer, logits, or token dispatch occurred.
- [ ] Layer list and generated token are empty.
- [ ] Native/direct/scaffold/reference/fallback/error dispatches are all zero.
- [ ] No residency or model state was created.

## Lifecycle and evidence

- [ ] Lifecycle domains are reconciled or explicitly `not_applicable`.
- [ ] Active context, singleton, registration, in-flight, owner-token, and
  stale-generation state is zero/not applicable as contracted.
- [ ] Evidence output was acquired exclusively and contains no local path.
- [ ] Duplicate-key, schema, privacy, and canonical PASS validation succeed.
- [ ] PASS was persisted only after final identity/map/evidence validation.

## Disposition

Return exactly one:

- `M1-B ACCEPTED`
- `M1-B REJECTED`

Even an accepted M1-B does not authorize M1-C. T017-140 and a separate M1-C
review remain mandatory.
