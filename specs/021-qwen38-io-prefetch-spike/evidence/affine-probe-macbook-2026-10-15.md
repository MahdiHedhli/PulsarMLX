# MacBook tiny affine probe, 2026-10-15

Scope: an additive, checkpoint-free Qwen research probe on the existing owner
branch. No GLM worktree, model file, checkpoint payload, checkpoint Python,
package install, download, full-model loader, inference, throughput benchmark,
or GPU allocation was used.

## Host and feasibility

`system_profiler SPHardwareDataType` reported MacBook Pro Mac14,5, Apple M2 Max,
64 GB memory. `df -h .` reported 261 GiB available on the Data volume.
`memory_pressure -Q` reported 68,719,476,736 physical bytes and 45% system-wide
free memory at the sampling instant. These observations are dynamic and are not
a process reservation or runtime memory gate. The pinned 98.924 GiB checkpoint
cannot be fully resident on this host. Python 3.13.13 is present without MLX;
the installed exploratory MLX is 0.31.2 under Python 3.14.6, rather than the
proposed Python 3.13/MLX 0.32.0 target. No target lock is resolved.

## Source and validation

`scripts/research/qwen38_affine_probe.py` constructs two-row, two-group
4-bit/group-32 and 8-bit/group-64 unsigned packed matrices and BF16 affine
scale/bias arrays. A separate Python integer decoder computes the expected
dequantized values; known packed words, row polarity, group transition, and
last-column orientation are asserted by unit tests. The optional MLX command
uses `dequantize` and `quantized_matmul` with explicit affine metadata on tiny
CPU arrays. Its mathematical contract matches the [official MLX dequantize
API](https://ml-explore.github.io/mlx/build/html/python/_autosummary/mlx.core.dequantize.html)
and [quantized matmul API](https://ml-explore.github.io/mlx/build/html/python/_autosummary/mlx.core.quantized_matmul.html).
Those live documentation pages were checked for API shape, not treated as a
version-pinned MLX 0.31.2 reference.

Local command and result:

```text
/Users/mhedhli/.local/bin/python3.13 -I -S -B -m unittest discover -s scripts/research/tests -p 'test_qwen38_*.py' -q
Ran 141 tests in 0.186s; OK (stdlib-only, including 3 new scalar tests).

python3 -B scripts/research/qwen38_affine_probe.py --run-tiny-mlx
Python 3.14.6 / MLX 0.31.2 / macOS 26.6.2 / CPU:
4-bit, group 32, 2x64: 128 dequantized values exact; quantized matmul exact.
8-bit, group 64, 2x128: 256 dequantized values exact; quantized matmul exact.
```

The first MLX attempt inside the filesystem sandbox stopped at MLX device
initialization (`No Metal device available`), before array evaluation. A CPU
selection alone did not fix sandbox initialization. The successful bounded run
used the approved unsandboxed execution route and allocated only these fixture
arrays. No GPU/Metal result or actual device fence was observed. The initial
unit test also caught one incorrect literal packed-word expectation; it was
fixed before the passing run.

Local review checked bounds, explicit quantization parameters and transpose,
that MLX import occurs only on the opt-in path, source/test diff, and the absence
of credential patterns or large files. The probe cannot read checkpoint paths.
The test is independent of MLX in its scalar arithmetic, but shares the fixture
generator and is not an independently produced upstream Qwen golden.

An attempted no-tools Gemini source review of exactly the two new project-owned
files was rejected by automatic approval review before transmission. Its reason
was missing trusted end-user authorization to disclose these files to Gemini.
No payload was sent and no alternate route was attempted. This slice therefore
has local review only; it is not the independent backend/source review required
for the future production adapter gate.

## Next acceptance boundary

Freeze a Python 3.13 environment and independent upstream source/goldens, then
repeat small affine and model-specific probes on the intended MLX version.
Implement and review real device completion/fence ownership and independent
process/MLX/system sampling before bounded checkpoint inference. The
48/40/8/16 GiB gates and numerical parity stop rules remain unchanged. This
CPU fixture result does not qualify checkpoint compatibility, routing, n-gram
hashing, SSD traffic, Metal residency or a tokens-per-second target.
