# Local bound file admission, 2026-10-05

Mahdi authorized one local, read-only digest verification and a normal non-force push of `research/qwen38-strata-pager-m2-20261003` to `MahdiHedhli/PulsarMLX`. The source worktree was clean at `f2705d30b2288dec9c314bc6803ca64a28864766` before the evidence runner was added. The checkpoint remained outside Git in its existing directory.

The [exact runner](bound-admission-local-runner-2026-10-05.py.txt) was executed once with system Python and isolated standard-library imports:

```sh
python3 -I -S -B specs/021-qwen38-io-prefetch-spike/evidence/bound-admission-local-runner-2026-10-05.py.txt
```

It called the public `admit_checkpoint_bound` entry point, parsed metadata through the retained verified handles, checked all identities again, and closed the bound set. It did not materialize a page, execute checkpoint Python, import MLX, load a model, install a package, run inference, or benchmark. Full-file streaming necessarily read checkpoint payload bytes for hashing. The catalog's `scope` field describes its header-derived spans, not the whole admission's read extent.

The process exited 0. The [raw result](bound-admission-local-result-2026-10-05.json) records source/manifest/runner identity, Python version, start and end timestamps, each file's size, matched digest, retained identity and chunk count, catalog geometry, cleanup and verifier peak RSS. A separate evidence-only check matched every recorded file to the project manifest, recomputed the runner and manifest SHA-256 hashes, reconciled chunk counts and identity sizes, and checked all exclusion flags and descriptor cleanup.

| Requirement | Observed result |
| --- | --- |
| All pinned files and full-file digests | 25/25; 106,218,444,193 bytes; passed |
| Bound catalog metadata | 3,215 tensors; 48 layers; 512 experts/layer |
| Expert and PLE catalog | 24,576 expert pages; 39,168 PLE pages; PLE layer 1 |
| Fixed text / excluded vision tensor spans | 5,348,837,400 / 897,862,112 bytes |
| Post-admission file identity | Every retained file checked successfully |
| Cleanup | 26 descriptors (25 files and directory) confirmed closed |
| Verifier peak RSS on macOS | 34,062,336 bytes, approximately 32.5 MiB |

The peak RSS is an observation of this standard-library verifier only. It is not a production MLX sampler, a process footprint bound, or a memory-pressure/swap qualification. The 48 GiB process stop, 40 GiB all-weight cap and 16 GiB OS reserve remain planning requirements. No throughput or latency claim follows from the timestamps.

The saved admission result is historical evidence: the bound object was closed. A later authorized session must repeat admission and keep the resulting handles alive. Real per-page reads, affine geometry/numerical semantics, residency, fences and independent memory instrumentation remain unqualified. Small metadata files retain their manifest's Git-blob SHA-1 pins; the source manifest remains the trust root. The [next-gate contract](../production-adapter-next-gate.md) records the remaining work without expanding this run's authorization.

Before commit/push, the outgoing branch history relative to `origin/main` was checked for model/large blobs and common private-key, GitHub-token, provider-key and AWS-access-key patterns: 74 new blob versions, maximum 90,497 bytes, no findings. The final staged content receives the same bounded review plus whitespace and scope inspection. Pattern checks do not establish absence of every possible secret. Existing independent reviews and their frozen packets remain unchanged; this evidence adds no runtime implementation requiring another external review.

Constitution check: exact command and observed evidence are retained; no weights, credentials or third-party code are added; no shared runtime behavior is changed; memory and correctness gates are preserved.
