# R001 final adversarial acceptance

## Verdict

`ACCEPT`

Accepted implementation HEAD:
`4e9468d8c0d049e9ea6a70cbd056967187e62d1b`.

The independent reviewer did not author the implementation and performed two
bounded repair loops, the maximum allowed by the graph.

## Initial rejection

The first N9 review rejected runtime source admission that could accept a weak
historical manifest, an insufficiently constrained partial nonce, incomplete
manifest-stage resume handling, and ambient environment-controlled fault
injection.

Repair commit `8ae26a34275884cc886f4c0f5f58901afd715889`:

- Requires checkpoint admission v3.
- Pins ordered shard names, sizes, SHA-256 values, reconstructed set hash, live
  inventory SHA-256, and device/inode/size/nanosecond-mtime identities.
- Opens Rust source descriptors with `O_NOFOLLOW` and compares descriptor
  metadata.
- Binds lowercase hexadecimal partial nonces to their payload names.
- Repairs a missing detached manifest hash on resume.
- Replaces ambient fault injection with explicit debug-only CLI controls that
  release builds reject.
- Adds payload-stage and manifest-stage interruption/resume evidence.

## Repair-loop-one rejection

The second review found that Python checked path metadata rather than the
opened source descriptor, and that a pre-existing symlink at
`staging/abandoned` could escape the authorized hierarchy.

Repair commit `4e9468d8c0d049e9ea6a70cbd056967187e62d1b`:

- Carries admitted descriptor identity through every independently parsed
  tensor.
- Checks `fstat` before and after GGUF parsing and every source byte/sample
  read.
- Rejects a same-size source replacement regression.
- Rejects symlinked staging and abandoned roots.
- Requires the canonical abandoned root to be a direct child of the canonical
  staging root.
- Proves an abandoned-root symlink cannot write outside staging.

## Final reconstruction

The reviewer accepted:

- Six-shard size/hash/set identity and stable external-copy authority.
- GGUF v3 `glm-dsa` live metadata and expert-axis interpretation.
- 456 expert tensors, 19,532 objects, and 224,974,307,328 expert payload bytes.
- Zero out-of-bounds, overlap, missing, duplicate, block-split, or
  shard-spanning expert mappings.
- Exact v1 format implementation and independently reconstructed Python
  verification.
- Expert, component, and source-offset swap resistance.
- Two deterministic 269-object generations.
- Eleven corruption/truncation/identity negative cases.
- Payload and manifest interruption, stale-plan, changed-source, and
  unexpected-final rejection/recovery.
- Approximately 61-62 MB peak RSS while generating 3.13 GB.
- Qualified same-device benchmark claims.
- F017 isolation and no full-store repack.

The final independent v3 pass verified 269 objects, 807 components, and all
nine live quantization classes. No material N9 issue remains.
