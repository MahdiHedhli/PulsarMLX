# PulsarMLX F017 Dense-Prefix, Decoded-Reuse, and Colibrì Comparative Audit Report

## Result

`READY FOR DENSE-PREFIX PACKAGE ADVERSARIAL REVIEW`

- Reuse: `SEPARATE_PACKAGES_REQUIRED`
- Colibrì audit: `ACTIONABLE`
- Dense prefix: `READY_FOR_REVIEW`
- Q6_K: `PACKAGE_READY`
- Q4_K: `PACKAGE_READY`
- Downstream: `PREPARED`

## Provenance

- Reviewed baseline: `8031020f2e9480712ff185a53b2e565d25dc6a24`.
- Sprint implementation base: `554e34fdb3e08a656cce85cb485e7fe36893ad5e`,
  the carried-forward dense-prefix preparation descendant of that baseline.
- The unpublished `dd52d38` remains absent and non-authoritative.
- Existing reviewed hashes and historical v1/v2/v3 dispositions are unchanged.
- Reviewer heuristic disposition: central percent-range intuition was confirmed;
  eight-fixture viability was refuted by the frozen `n=8`/0.90 planning rule;
  the estimator correctly returned `NOT_VIABLE`.
- Operator-side reviewed CI was run `31851111967` at exact head `8031020f...`;
  both Apple jobs passed. This sprint's exact final-head run is recorded in the
  final operational handoff because a report cannot bind its own future commit.

## Decoded reuse

The predecessor v2 contract is
`3a947427cfc285119fe9b8bcc910e26fdde4cdd6599711fe3f6b5df14d95c71c`.
The use-case amendment is
`8ec7ab3c80c40797113ee4ef4306b5e84b35c3a2634a44ebf971690c40337da0`.
Overall disposition: `SEPARATE_PACKAGES_REQUIRED`.

| Use case | Policy |
|---|---|
| Multi-fixture oracle-only route analysis | `REUSE_SAFE_FOR_ORACLE_ONLY` |
| Multi-fixture candidate route analysis | `SEPARATE_ORACLE_AND_CANDIDATE_PACKAGES_REQUIRED` |
| Dense-prefix oracle | `REUSE_SAFE_FOR_ORACLE_ONLY` |
| Dense-prefix production candidate | `SEPARATE_ORACLE_AND_CANDIDATE_PACKAGES_REQUIRED` |
| Q4_K/Q6_K qualification | `REUSE_PROHIBITED` |
| M1-F expert execution | `SEPARATE_ORACLE_AND_CANDIDATE_PACKAGES_REQUIRED` |
| M1-G output-head work | `SEPARATE_ORACLE_AND_CANDIDATE_PACKAGES_REQUIRED` |

For the retired eight-fixture oracle family, immutable reuse would reduce 96
reads to 12, avoiding 84 reads (87.5%), 974,525,440 compressed bytes, and
4,665,013,248 decoded bytes. This does not resurrect either retired family.
Candidate decode/import coverage is not inferred from oracle reuse. Relocation,
copy, mutation, reorder, writable alias, symlink escape, identity drift,
before/after mismatch, and cross-fixture contamination tests fail closed.

## Pinned Colibrì audit

- Repository: `https://github.com/JustVugg/colibri`
- Commit: `6546cdde7296f28771e2ba1a1d7c1d4b0cb550aa`
- Tree: `bc52bec7cf224d641318c68e5ef7d6a5e3489ef0`
- Prompt-observed head differs: no.
- License: Apache-2.0; `LICENSE` SHA-256
  `c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4`.

Audited files include the Metal documentation/backend/header/tests, C runtime
and build, format documentation, resource planner, and M1 Ultra/M5 Max reports.
Issues 596, 622, 637, 706, 813, 826 and PRs 457, 587, 624 are identity-bound.
The machine audit SHA is
`9d102ebd6dad2036bd982bdfff15c41405c239d9d1f52e08d615ec4ea33c21d5`;
the risk register SHA is
`4ab9caa3db9e76c402027cec9028b954fb35747c83c90b176f3a818dd6751e33`;
the adoption list SHA is
`f960dddfd95242d8f38642b46f32373566adf08ddaf6b74710c0cfed4862e4e9`.

Immediate independent PulsarMLX actions are top-1/top-2 margin retention,
rows-15/16/17 transition falsification, f32 accumulation-order stress,
eligible/native/refusal/fallback reconciliation, zero-copy lifetime invariants,
and peak-not-aggregate memory checks. The near-tie report remains open at the
pin and is treated as a generic numerical risk, not evidence of an MLX defect.

Future Feature 018 candidates are fusion-aware command-buffer accounting,
batched routed-expert submission, explicit registration bridges, residency-set
experiments, and resident-compute/I/O overlap. Each requires separate review.
No performance claim transfers from the hardware reports.

Colibrì `fmt=2`/`fmt=4` are custom int4 layouts with different scale, block, and
container semantics. They are `FORMAT_INCOMPATIBLE` with GGUF Q4_K/Q6_K and
cannot qualify PulsarMLX decoders. No external code, dependency, or submodule
was introduced.

## Dense-prefix boundary and input

Boundary: `F017 M1-F(-1) REAL DENSE-PREFIX LAYER-3 ENTRY-STATE BOUNDARY`.
It executes token embedding and complete dense layers 0, 1, and 2 and emits the
layer-3 entry hidden state. Catalog/map/runtime inspection confirms no MoE
routing in those layers.

The pre-existing P-MIN lineage freezes prompt `Hello`, token `[9703]`, position
0, DSA `range_fill([0])`, empty initial cache, and no route-informed selection.
Prompt SHA is `185f8db3...61969`; token bytes SHA is `89b0cae4...59c0`; package
SHA is `c05ba1cba69535cd17daf9f4326e5e1db25ffafe504c53712aa548f251741dff`.
Prompt replacement, route inspection, and best-of-N search are forbidden.

## Inventory, quantization, and budgets

Independent catalog/map derivation yields 40 tensors, one shard, 40 positional
reads, 1,431,263,232 packed bytes, and 8,504,653,824 aggregate decoded-f32
bytes. Router/expert/shared-expert/layer-3/output-head tensors are absent.

| Family | Count | Packed bytes | Decoded bytes | Admission |
|---|---:|---:|---:|---|
| F32 | 12 | 178,176 | 178,176 | `REAL_BYTE_QUALIFIED_REUSABLE` |
| Q8_0 | 12 | 165,027,840 | 621,281,280 | `REAL_BYTE_QUALIFIED_REUSABLE` |
| Q5_K | 12 | 544,997,376 | 3,170,893,824 | `REAL_BYTE_QUALIFIED_REUSABLE` |
| Q6_K | 3 | 185,794,560 | 905,969,664 | `REQUIRES_REAL_BYTE_QUALIFICATION` |
| Q4_K | 1 | 535,265,280 | 3,806,330,880 | `REQUIRES_REAL_BYTE_QUALIFICATION` |

Inventory SHA: `eaf54506f5bd45ef41f223224096a253f6fa6c5e2ad3bf94971c18eb09f6b21b`.

## Residency and oracle

Aggregate decoded volume is not peak. The source-backed model tracks packed,
decoded CPU, MLX import/residency, activations, Q/K/V, attention, FFN, cache,
oracle, evidence, delayed release, and backend reserve lifetimes. The frozen
pre-observation admission floor is 27 GiB (28,991,029,248 bytes), derived from
the conservative double-residency envelope and reserve; current free memory
cannot lower it. Contract SHA:
`56ab1eae69b45f9ae97f98e1d36dfa124e080a6dc82573013cc57782bce1ac76`.

The oracle is independent Python/NumPy, source-hashed, completes before candidate
construction, and forbids Rust, MLX, candidate outputs/metrics, and Colibrì.
It covers embedding, RMSNorm, MLA/DSA, attention, residual, dense SwiGLU, and all
three transitions. Oracle contract:
`0a54aa957e8b768108e4d8bc8c6e2a84cb48fbb3e0c93414c308112e88b3e816`.
Real Tier-B thresholds remain checkpoint-free and pre-frozen at contract
`9d1a6cc20ce8325fe8395334416f5ebcf980b72f02c6a0b44dc3240e0810024a`.

## Decoder packages and sequence

Q4_K target: `token_embd.weight`, offset 535,316,320, packed 535,265,280.
Q6_K target: `blk.0.ffn_down.weight`, offset 1,203,482,464, packed 61,931,520.
Targets follow pre-frozen largest-decoded/largest-packed/lexicographic rules.
Each package requires one exact packed payload and exact A=B=C little-endian
f32 bytes, malformed/truncated negatives, and zero model compute. One payload is
sufficient for each exact format contract; tensor identities remain per-tensor.
Accepted Q4_K format lineage can support M1-G decoder admission but cannot prove
the output-head payload identity.

Sequence: Q4_K, Q6_K, dense prefix. Events remain separately authorized.

## Execution, evidence, retention, and handoff

Typed config binds runtime, tooling, executable, authorization, checkpoint,
catalog/map, input, allowlist, decoder lineage, oracle, numerical/residency,
attempt, dispatch, retention, and evidence. Loose overrides fail closed.
Preflight/admission are non-consuming; `EXECUTION_STARTED` occurs immediately
before the first authorized payload access; no retry follows consumption.

Dispatch evidence records conceptual operations, native/fused kernels, imports,
CPU/reference/scaffold, sync/readback, refusal/fallback, and backend errors.
Timing buckets are frozen before observation. Availability is never proof of
native work. No planning count such as 28 is a real dispatch budget.

The accepted final hidden state must be immutable private canonical LE f32 bytes
with public SHA, dtype, shape/count, full input/checkpoint/oracle/candidate
provenance, numerical status, creation ordinal, and read-only lifecycle. M1-F0
must consume that exact state under routing v3.0.1; H=2 failure stops without a
new prompt. Route-independent M1-F and M1-G/P1 scaffolds remain prepared and
non-authorizing; route-dependent fields are explicit and P1 command unpublished.

## Hypothetical ledger

- Current: 57.
- Q4_K: 57→58.
- Q6_K: 58→59.
- Dense prefix with separately reviewed retention of both qualified payloads:
  remaining 38 reads, 59→97.
- Without cross-event reuse: all 40 reads, 59→99.
- Any reuse-validation failure stops; it does not silently reread.

## Review and stop

- Internal verdict: `GO FOR DENSE-PREFIX PACKAGE ADVERSARIAL REVIEW`.
- Adversarial packet:
  `docs/architecture/reviews/f017-dense-prefix-decoded-reuse-colibri-adversarial-packet.md`
- Packet SHA-256:
  `5b419aa3dc990fac72993ac9906a92793145c821d4effa87d59258e6f4b14df1`.
- Final-head Apple CI run→SHA is recorded in the final operational handoff.

Real checkpoint access: 0. Ledger: 57. Q4_K/Q6_K qualification, dense prefix,
M1-F0, M1-F, M1-G, P1, and Feature 018 were not executed.

Exact next action: independent adversarial review. If it returns GO, the narrow
candidate next real event is one separately authorized Q4_K real-byte decoder
qualification (ledger 57→58), not dense-prefix execution.
