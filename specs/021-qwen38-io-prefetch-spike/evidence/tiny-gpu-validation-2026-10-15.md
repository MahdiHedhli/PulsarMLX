# Tiny Metal affine probe: local evidence and review hold

**Publication status: unpublished.** This is a synthetic arithmetic and sampled
memory observation, with no checkpoint payload or checkpoint Python access.
The separate full Qwen runtime environment remains unresolved.

## Reproducible fixture environment

The project-local environment is at `../.qwen38-cp313/venv` relative to this
worktree (outside Git). It uses pre-existing uv-managed Python 3.13.13 with
interpreter SHA-256 `d22a09ce45166ee066022909e071bba239c263ba090ed8f0884f7f21ae922ac3`.
MLX and MLX-Metal 0.32.0 were selected against the actual macOS 26 arm64 host,
downloaded as official PyPI wheels, checked against their recorded SHA-256 and
sizes, then installed offline with `pip --no-index --only-binary=:all:
--require-hashes --force-reinstall`. `pip check` passed. The exact two-wheel
[lock](tiny-gpu-macos26-cp313.lock.txt) and [environment receipt](tiny-gpu-environment-2026-10-15.json)
record the identities. The Python installer signature was not separately
verified. This lock contains only the two packages needed by the fixture,
not mlx-lm or a full model runtime.

The [literal reference](tiny-affine-reference-v1.json) uses the installed
MLX 0.32.0 affine formula `weight = scale * unsigned_code + bias` and independently
calculated Decimal samples/products; it was not copied from an MLX result.
It checks 4-bit/group-32 and 8-bit/group-64, including first and last group
values, sparse endpoint matmul and a dense power-of-two activation vector.
It is not an upstream Qwen golden and says nothing about norm folding or
checkpoint numerical parity.

## Bounded run and actual observation

The revised command was run on MacBook Pro Mac14,5, Apple M2 Max, 64 GiB
physical memory. The Data volume had approximately 261 GiB available at the
earlier host check; disk availability is dynamic. The command was invoked as
a 30-second-limited child:

```text
../.qwen38-cp313/venv/bin/python -B scripts/research/qwen38_tiny_gpu_probe.py --run-tiny-gpu
```

The command exited 0. The [raw JSON result](tiny-gpu-run-2026-10-15.json)
contains nine host/MLX observation points. Its sparse and dense products
match the independent literals exactly for both modes; maximum dense product
error is zero on these values. Peak reported MLX allocation was 2,912 bytes;
active MLX allocation returned to zero after each case. Maximum sampled RSS
was 42,663,936 bytes. System-wide memory free was 43% at all samples, and
reported swap used remained 26,999.75 MiB at the tool's 0.01 MiB resolution.
That pre-existing swap is substantial, so the gate checks observed growth,
not absence of swap. Fixture logical bytes were 1,120 and 2,336, below the
16 KiB per-case stop. The revised 147-test Qwen stdlib suite passes:

```text
../.qwen38-cp313/venv/bin/python -I -B -m unittest discover -s scripts/research/tests -p 'test_qwen38_*.py' -q
Ran 147 tests; OK.
```

The host stops are physical memory exactly 64 GiB, at least 16 GiB free by
the percentage report, RSS at most 512 MiB, and no *observed* system swap
growth. The MLX stops are active/peak at most 16 MiB and cache at most 8 MiB.
MLX settings are advisory. RSS, free percentage and swap are snapshots that
can miss excursions between samples; system-wide swap can be affected by
other processes. The MLX peak counter covers MLX allocation between samples,
but neither it nor RSS proves total process or Metal driver footprint. The
explicit stream `synchronize` returned; this does not establish a production
completion callback or prove that synchronization was necessary on tiny ops.

## Independent review and disposition

Claude Opus reviewed the earlier draft as pasted text only. It found no false
pass within that draft's narrow stated scope, then identified four material
claim/coverage limits:

1. Sparse endpoint matmul did not cover interior codes. A dense power-of-two
   matmul and independently calculated products were added and passed.
2. `stream_fenced` overstated a constant success flag. The output now says
   `synchronize_returned`, with `production_fence_qualified: false`.
3. Error/cleanup paths lacked tests. Fake-MLX tests now check original-stream
   synchronization, quarantine on fence error, and preservation of primary
   and cleanup errors. This is source-contract testing, not a real failure
   injected into Metal.
4. Host memory claims were only sampled. This document and the result limit
   them explicitly to observation points. The MLX peak is separately named.

The draft review also noted wheel metadata does not prove the imported module
origin, host RSS is incomplete, and small kernels may differ from production.
The configured MLX cache limit and observed stop are now both 8 MiB; each
case requires active memory to return to zero. The 25% free-memory boundary
is tested. The raw first review remains local and is not part of this
repository.

A follow-up review packet contained exactly five project-owned source, test,
reference, lock and receipt files, 20,050 bytes, SHA-256
`04c7e8fd7193a77a45089f9bb5c2a8815af2cbaf9dd2ac52839eb05bf3e6dff7`.
Automatic approval review **rejected transmission to Claude** because the
trusted user text available to this task did not explicitly authorize that
specific private-file payload and destination. It warned against any indirect
retry. No follow-up packet was sent and there is no independent verdict on
the revised source. The revised code and evidence remain uncommitted until
that gap is resolved. This is a source disclosure risk, not a failed GPU run.

This fixture does not access the 106,218,444,193-byte checkpoint, prove Qwen
norm folding or n-gram/expert routing, measure SSD paging traffic, demonstrate
48/40/16 GiB full-process gates, or support a 20+ token/s claim.
