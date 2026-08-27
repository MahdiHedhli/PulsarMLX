# R001 representative fixture results

## Claim

The bounded R001 v1 fixture passed production-copy, independent mapping,
determinism, corruption, interruption, and resume checks. This is storage-layout
evidence only. It does not establish inference or model-output correctness.

## Authority

- Host: ColPanicM2, Apple M2 Max, 64 GiB.
- Production implementation commit: `d7837a9ba383056b9fc4b421e7cb6d186d592c18`.
- Independent-verifier hardening commit: `03c53a73`.
- Checkpoint set SHA-256: `d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee`.
- Live inventory SHA-256: `ca23db7459219acd39cd047eb6490c814ab40d472dd081424624ac8bf8fc5c9b`.
- Manifest plan identity: `2f5948bfc9d52cbf72d02af9a6ab6f7b07da4a35b2c87bbd237dd2e609ff62a6`.
- Manifest SHA-256: `22a8edaedf87f8c9d08dd4b99e4d92a17afa5899936c11cfc49b64a955be0e0d`.

The production command used `pulsar-repack repack` with the admitted external
checkpoint, frozen live inventory, graph-owned output and staging roots, and
scope `3:0,37,255;8:0,37,255;40:*;78:0,37,255 --shared`.

## Fixture scope

- Complete representative MoE layer: layer 40, selected because it uses the
  dominant routed and shared layouts and includes all 256 routed experts.
- Early exceptional coverage: layer 3, routed experts 0, 37, 255 and shared.
- Middle exceptional coverage: layer 8, routed experts 0, 37, 255 and shared.
- Late exceptional coverage: layer 78, routed experts 0, 37, 255 and shared.
- Total: 269 objects, 807 gate/up/down components.
- Quantization types: Q8_0, Q2_K, Q3_K, Q5_K, Q6_K, IQ2_XXS, IQ3_XXS,
  IQ2_S, and IQ4_XS.
- Canonical payload: 3,130,097,664 bytes.
- Stored representation: 3,138,912,256 bytes.

## Production runs

| Run | UTC interval | Duration | Peak RSS | Result |
|---|---:|---:|---:|---|
| v1-a | 2026-08-27T16:41:05Z to 2026-08-27T16:42:16Z | 71 s | 61,358,080 B | passed |
| v1-b | 2026-08-27T16:42:46Z to 2026-08-27T16:43:55Z | 70 s | 62,226,432 B | passed |

Both clean runs produced identical manifests and identical SHA-256 lists for
all generated files. No full expert store was generated.

## Independent verification

The Python verifier parses GGUF v3 metadata independently and reconstructs
tensor byte lengths, expert axes, plane offsets, component roles, and bundle
identity without importing the Rust repacker or its range calculations.

- 269/269 objects passed.
- 807/807 components matched exact independently reconstructed source bytes.
- 3,130,097,664/3,130,097,664 payload bytes matched.
- All nine live quantization classes received source-versus-bundle decoded
  block sanity samples.
- Semantic samples establish mapping identity, not decoder qualification.

## Negative and resume evidence

Eleven negative cases were rejected: bad header, nonzero header padding,
payload corruption, bad footer, nonzero footer padding, truncation, trailing
bytes, wrong expert, component permutation, wrong source offset, and an
interrupted partial.

A deterministic test interruption after 1 MiB left an owned partial and
sidecar. Without admission it was not complete. An explicit `--resume`
quarantined both files, generated eight clean all-format objects, left zero
live partials, and passed independent verification. Changed source identity,
stale plan reuse, and an unexplained existing final each exited nonzero.

## Local evidence

Exact local paths are intentionally not committed. The graph-local evidence
root contains:

- `r001-repack-v1-a-local-0001.json`, SHA-256
  `d20e2feb5d9453878350cc2e886f6c34433ea5b9aa2b0205b49e0049b06c8e24`.
- `r001-independent-verification-v1-a-local-0001.json`, SHA-256
  `c385d1108d3822a75c942f63e3917471929ecd50c06c1d650af2498c0ae06659`.
- `r001-negative-v1-local-0002.json`, SHA-256
  `c0094d3aa9e8b77555b4a4944dde8a94d2af433f80c3ed48dd13d16a579383f6`.
- `r001-resume-v1-local-0001.json`, SHA-256
  `5c0c24cdbfbdeea7f91772811901dbd39178a2c84e4d38dc2552d26c71a8b611`.

## Limitations

- Generated bundles remain external and are not committed.
- The provisional pre-contract run is superseded and is not acceptance
  evidence.
- Temperature telemetry was unavailable through installed macOS tools.
- The complete approximately 225.6 GB expert store was not generated.
