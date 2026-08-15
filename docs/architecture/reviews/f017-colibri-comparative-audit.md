# PulsarMLX F017 Colibrì Comparative Source Audit

## Scope and provenance

This is a checkpoint-free, source-only comparison. Colibrì was fetched from
`https://github.com/JustVugg/colibri`, then pinned before inspection at commit
`6546cdde7296f28771e2ba1a1d7c1d4b0cb550aa` and tree
`bc52bec7cf224d641318c68e5ef7d6a5e3489ef0`. The pinned head equals the value
observed in the sprint prompt. The repository declares Apache-2.0 in `LICENSE`
(SHA-256 `c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4`).

No Colibrì source was copied, generated into PulsarMLX, added as a dependency,
or added as a submodule. Public failure reports inspired independent PulsarMLX
tests; Colibrì output is never an oracle.

The audited surface and every file hash are banked in
`docs/architecture/reviews/evidence/f017-colibri-comparative-audit-v1.json`.
It includes `docs/metal.md`, both Metal backend files, `c/colibri.c`, the C
Makefile, Metal correctness and large-grid tests, both requested hardware
reports, `docs/FORMATS.md`, and `c/resource_plan.py`. Issues 596, 622, 637,
706, 813, and 826 and merged PRs 457, 587, and 624 are bound by immutable
metadata/body/comment hashes.

## Comparative conclusions

| Surface | Colibrì mechanism | PulsarMLX disposition |
|---|---|---|
| Dense GEMM | Metal path switches at a row threshold | Add independent near-tie, threshold-transition, and accumulation-order falsifiers. |
| Attention | Fused decode/prefill command buffers | Separate review only; do not infer MLX behavior. |
| Routed experts | Batched resident-expert submission | Feature 018 candidate only; current F017 records fusion-aware dispatch evidence. |
| Zero-copy | Page-aligned stable host slabs registered as Metal buffers | Adopt lifetime/read-only/hash/synchronization invariants, not the backend. |
| Residency | Dense/runtime/expert tiers and optional residency sets | Inform the existing liveness model; never replace MLX-specific measurement or proof. |
| Diagnostics | GPU/fallback/expert counters | Require eligible operations to reconcile to native work, explicit refusal, or fallback. |
| Quantization | Custom `fmt=2`/`fmt=4` int4 layouts | Format-incompatible with GGUF Q4_K/Q6_K; algorithmic lessons only. |

The complete subsystem matrix is machine-readable in the comparative evidence.

## Near-tie Metal forensic result

Issue 622 is open at the pin. The report attributes a teacher-forced prefill
token mismatch to the large-batch Metal GEMM path selected at rows `>=16` by
the documented default. Raising `COLI_METAL_GEMM_MIN` kept that GEMM on CPU and
removed the mismatch in the cited fixture. Decode with one row did not cross
the threshold; short prefill also did not. The report identifies a CPU/Metal
accumulation-order difference and later notes that downstream logit drift may
exceed the isolated-kernel error.

This does not prove an MLX defect or transfer any Colibrì tolerance. It does
justify generic PulsarMLX regressions that retain top-1/top-2 values and margins,
exercise rows 15/16/17, compare f32 reduction orders, and fail closed when a
summary hides divergence. Fused attention was not implicated by that specific
discriminator; it is not globally exonerated.

Issue 813 exposes a second generic risk: backend availability can be announced
while an unsupported format produces no native work. PulsarMLX now tests the
invariant `eligible = native + refusal + fallback`; backend errors and
unclassified no-dispatch events are fatal.

## Hardware reports and residency

The pinned M1 Ultra report is external, single-run-per-configuration context.
Its reproducible lesson is to separate storage wait, compute, attention,
orchestration, resident bytes, and cache behavior. Its throughput is not a
PulsarMLX claim. The M5 Max report similarly supports tracking dispatch overhead
and CPU competition, not projecting performance.

Colibrì's no-copy path reinforces four transferable invariants: source memory
must have stable identity, remain read-only and alive through GPU completion,
be synchronized before teardown, and reconcile registration/unregistration and
byte accounting. PulsarMLX retains separate oracle and candidate packages where
candidate import/decode behavior is load-bearing.

## Adoption boundary

Immediate actions are limited to independent tests, stricter instrumentation,
and residency-risk controls. Fusion, batched expert submission, explicit Metal
registration, residency sets, and I/O overlap remain future Feature 018 or
separate-review candidates. Direct code reuse requires a distinct license and
provenance review and is not proposed here.

Real checkpoint access: 0. Real-payload ledger: 57.
