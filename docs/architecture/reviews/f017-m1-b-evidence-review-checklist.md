# F017 M1-B Evidence Review Checklist

Status: **PREPARED / NOT AUTHORIZED**

## Source and environment

- [ ] Executed source is the exact separately authorized commit descended from
  M1-A evidence commit `91359dd59265de71fd25848142af23823e41e160`.
- [ ] Source worktree was clean.
- [ ] Environment kind is `production_reviewed` and the manifest hash is exact.
- [ ] Telemetry source is `measured_host`; all admission gates passed.
- [ ] Actual arm64 `libmlx.dylib` and `libmlxc.dylib` hashes match expected.

## Checkpoint identity

- [ ] Exactly six canonical shards are present.
- [ ] Every filename, byte size, and SHA-256 matches the reviewed manifest.
- [ ] Checkpoint-set SHA-256 and immutable revision match.
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
