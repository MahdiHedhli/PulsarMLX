# GLM-5.3-Flash tiny research slice

This is a checkpoint-free, standard-library Python research harness. It contains
an independently authored scalar oracle, a separate candidate, strict scoped
metadata validation, fictional mixed 4/8-bit bundles, and a synchronous store.
It does not establish model support or real-checkpoint parity. Python remains a
reference tool; the shipping runtime strategy remains Rust with native backends.

The exact equations, source identities and exclusions are in
[oracle-equations.md](oracle-equations.md), [mini-contract.md](mini-contract.md)
and [store-contract.md](store-contract.md). Arithmetic inputs are fixed in
[fixtures-and-criteria.md](fixtures-and-criteria.md). Floating-point gates are
f64 atol `1e-12`, rtol `1e-10`; structural identities are exact.

From the isolated source checkout, with the task's already-bound external
workspace path supplied as `FLASH_WORKSPACE`, run a new uniquely named receipt:

```sh
python3 -B scripts/research/glm53_flash/supervise.py \
  --workspace "$FLASH_WORKSPACE" --run-name arithmetic-01 \
  --pattern test_glm53_flash_arithmetic.py
python3 -B scripts/research/glm53_flash/supervise.py \
  --workspace "$FLASH_WORKSPACE" --run-name store-01 \
  --pattern test_glm53_flash_store.py
python3 -B scripts/research/glm53_flash/supervise.py \
  --workspace "$FLASH_WORKSPACE" --run-name contract-01 \
  --pattern test_glm53_flash_contract.py
```

The runner requires the existing local machine binding outside Git, verifies
the external volume, confines temporary files, records durable invocation
prefixes, samples RSS, and retains normal-exit child peak RSS. Time and RSS
ceilings are 120 seconds and 256 MiB per child. It is a controlled research
supervisor, not an operating-system security boundary. A cancelled child's
sampled RSS is a lower bound; it is not fabricated into a final peak measurement.
No test command downloads data, invokes a model loader, or builds native code.
Tests reject unknown metadata and use injected storage failures only.
The store tests require a symlink-free `TMPDIR`, which the supervisor supplies
inside the bound external workspace. A platform default such as macOS `/var`
may have a symlink ancestor and will be rejected by the store's path checks.

The oracle was written without reading the candidate. Candidate KDA uses
value-major internal state and transposes at its public boundary; its dot
accumulation uses `math.fsum`. The oracle uses independent scalar loops.
Store tests contain a separately implemented unpack/dequantizer and literal
word fixtures. Neither arithmetic path imports the other's helpers. This
establishes implementation separation, not independence from shared equations.

All newly authored code and fictional fixtures use the repository MIT license.
Design equations are attributed to PipeNetwork's Apache-2.0 runtime, the pinned
MLX reference, and the retained observed mlx-vlm sources in the contracts.
No upstream source file is executed or vendored by this slice. PulsarMLX is an
independent derivative of [Pulsar](https://github.com/giannisanni/pulsar); upstream
maintainers do not endorse or maintain these additions.

No public push is part of this phase because the existing workflow triggers
native/MLX work on push. Local source commits and complete patches can be
reviewed before any separately authorized publication. Shared-method acceptance
and cross-track coordination remain with the parent planner.
