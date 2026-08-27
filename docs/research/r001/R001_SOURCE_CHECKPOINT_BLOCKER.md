# R001 source-checkpoint preflight

## Result

`R001_FOUNDATION_BLOCKED_SOURCE_CHECKPOINT`

R001 was admitted into an isolated standalone clone, but N1 cannot prove the
actual expert layout because the live GLM checkpoint is absent on ColPanicM2.
The graph stopped before format design, implementation, fixtures, or benchmark.

## Isolation

- Authority checkout: `<f017-authority-checkout>` (read-only).
- R001 checkout: `<r001-checkout>`, standalone `.git`, not a linked worktree.
- Artifact root: `<r001-artifact-root>`, outside both repositories and iCloud.
- R001 base: `a948b68d9868a34b0cc9b00aacaa4ad2330b0f55`, equal to freshly fetched `origin/main`.
- Host: ColPanicM2, MacBookPro14,5, Apple M2 Max, 64 GiB, macOS 26.4.1 (25E253).

The authority checkout changed independently during preflight from
`7597730c8aecae8fb283b2352e9ee06639b171d1` to
`c1ad4c673b1ce03d49f158e044e69f649e717dfa` while remaining on
`feat/017-rust-native-inference-runtime`. R001 did not write to it. Its status
query did not complete within 30 seconds and was not forced or repaired.

## Source identity and availability

- Expected source: six-shard `unsloth/GLM-5.2-GGUF` `UD-IQ2_XXS` checkpoint.
- Checkpoint-set SHA-256: `d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee`.
- Expected bytes: `238,458,632,928`.
- Checkpoint manifest SHA-256: `34b65d586c86d24ee10f3a2ed55491fb3a5a6b9ddbaf893bf9e0ab962c96cf8f`.
- `PULSARMLX_GLM_GGUF` was unset.
- The documented local source directory was absent.
- No GLM storage volume was mounted.
- No filesystem crawl, checkpoint download, or remote-host access occurred.

## Metadata-derived facts, not live-byte proof

Committed catalog `docs/research/glm52/raw/f016-c01-catalog-0001.json`
(SHA-256 `135500cc46b65a877027b597bf20e0c7bb613802e5137c48204e7ab6e7a7ff19`)
reports GGUF v3, `glm-dsa`, 1,809 tensors, 456 expert tensors, 76 MoE layers,
256 routed experts, and one shared expert per MoE layer. This implies 19,532
logical routed/shared objects and a metadata-derived canonical expert payload
lower bound of `224,974,307,328` bytes.

These are catalog facts or mathematical derivations. They do **not** confirm
live header alignment, shard hashes, source bytes, tensor bounds, gaps,
overlaps, aliases, per-expert plane hashes, or block-boundary reads. The
existing catalog parser hard-codes 32-byte data alignment, so R001 must parse
`general.alignment` from live headers rather than inherit that assumption.

## Capacity

The artifact APFS volume reported `274,693,607,424` free bytes, 4 KiB device
and allocation blocks, and 16 KiB VM pages. A standard routed layer's derived
payload is approximately `2,894,069,760` bytes, so a bounded layer fixture is
admissible. The source checkpoint plus canonical expert payload alone would be
`463,432,940,256` bytes on one volume, before headers, padding, temporary
files, evidence, or safety reserve. A full local repack is not admitted.

## Required recovery

Make the already-authorized six source shards locally readable and set
`PULSARMLX_GLM_GGUF` to their directory. Do not download another checkpoint
without explicit authorization. Resume at N1 and first:

1. Recompute all six shard sizes and SHA-256 values.
2. Parse live GGUF metadata, including `general.alignment`.
3. Compute checked tensor and expert-plane ranges.
4. Prove no overlap, gap, out-of-bounds range, duplicate assignment, or
   quantization-block split.
5. Hash bounded first/last blocks and representative expert planes.

Only then may N2 design begin.

## Evidence

- Local exact-path evidence: `<r001-artifact-root>/r001-preflight-local-0001.json`.
- Local evidence SHA-256: `dfd718fb9feeb0d3e940d939ae182332850964c99afa492d0f9ff703daaae663`.
- Started: `2026-08-27T02:08:23Z`.
- Completed: `2026-08-27T02:16:34Z`.
- Required checks executed: host/path isolation and source-presence checks.
- Required checks unexecuted: live layout, byte/semantic/coverage verification,
  design/final review, fixtures, determinism, corruption/resume, and benchmark.
