# Feature 017 MLX GPU teardown forensics

## Environment

- Host: Apple M2 Max, 64 GB unified memory
- macOS: 26.4.1, build 25E253
- Xcode: 26.6, build 17F113
- Compiler: Apple clang 21.0.0, arm64
- MLX C: Homebrew `mlx-c` 0.6.0_2
- MLX native library: 0.31.2
- GPU: 38-core Apple GPU, Metal 4

The standalone reproducer is
`scripts/research/f017_mlx_c_teardown_matrix.cpp`. It has no PulsarMLX
runtime, model, fixture, residency, or decoder dependency. The parent forks a
fresh child for every variant, captures flushed stage markers, and preserves
exit status or signal information.

## Initial failure and correction

The original probe passed an uninitialized `mlx_stream` output object to
`mlx_get_default_stream`. The locally installed MLX C example initializes
output handles before getter calls, such as `mlx_device_new()` before
`mlx_get_default_device`. The minimized uninitialized-stream child failed
30/30 with `EXC_BAD_ACCESS`/SIGBUS at:

```text
libmlxc.dylib`mlx_get_default_stream + 52
```

The failure occurred immediately after `stream_create_begin`, before host
allocation, managed import, evaluation, synchronization, or teardown. It was
probe misuse, not evidence of a managed-array destruction defect.

After initializing the output with `mlx_stream_new()`, the same API path
passed. The corrected source is the authoritative reproducer.

## Lifecycle matrix

| Variant | Repeats | Passed | Exit 134 | Other/signaled | Result |
| --- | ---: | ---: | ---: | ---: | --- |
| CPU managed, sync, array-first | 30 | 30 | 0 | 0 | pass |
| GPU managed, default GPU stream | 30 | 30 | 0 | 0 | pass |
| GPU managed, initialized `get_default_stream` | 30 | 30 | 0 | 0 | pass |
| GPU managed, owned stream + operation | 30 | 30 | 0 | 0 | pass |
| GPU managed, explicit sync + operation | 30 | 30 | 0 | 0 | pass |
| GPU managed, stream-first teardown | 30 | 30 | 0 | 0 | pass |
| GPU managed, owner-first probe | 30 | 30 | 0 | 0 | pass |
| GPU managed, array-first teardown | 30 | 30 | 0 | 0 | pass |
| GPU managed, same-process reuse, 10 cycles | 30 | 30 | 0 | 0 | pass |
| GPU copy-backed, operation | 100 | 100 | 0 | 0 | pass |
| GPU copy-backed, owned stream | 30 | 30 | 0 | 0 | pass |

The important managed GPU data-access control reported source/result pointer
identity, completed evaluation and synchronization, released the array and
stream, and invoked the ownership callback exactly once. The same-process
reuse case recorded 10 callbacks over 10 create/evaluate/synchronize/release
cycles per child.

## Ownership and synchronization

For passing managed variants:

- callback entry and exit occurred inside input-array release;
- callback count was exactly one per imported buffer;
- synchronization completed before array release;
- host ownership was retained until object teardown in the accepted contract;
- no callback raced host release in the owner-last variants;
- no separate global/device synchronization API is exposed by the installed
  MLX C stream headers; `mlx_synchronize(stream)` is the available explicit
  completion primitive.

The owner-first variant was retained as a negative audit case after explicit
sync, but it is not the shipping ownership rule. Rust-owned buffers must remain
alive until the MLX array and all dependent stream work are released.

## Classification

**B. GPU managed import qualified with required order/sync contract.**

The required contract is:

1. Initialize output handles before MLX getter APIs.
2. Use `mlx_default_gpu_stream_new`, an initialized
   `mlx_get_default_stream` output, or an explicitly owned stream.
3. Evaluate and call `mlx_synchronize` on the submission stream.
4. Retain the host owner through array and dependent stream teardown.
5. Require exactly-once ownership callback behavior.

This qualifies the minimal official MLX C managed-array path. It does not by
itself qualify importing a Rust-owned Metal buffer into MLX without a copy.
The Rust slab to Metal `newBufferWithBytesNoCopy` bridge remains a separate,
already-qualified direct path for Feature 018 integration.

## F017/F018 consequence

F017 may retain the official MLX C API behind the narrow native adapter, with
the initialization, synchronization, and lifetime rules above encoded as
fail-closed invariants. F018 direct Metal need not depend on MLX managed-array
import and remains responsible for its own native buffer/fence contract.

No model inference or quantized Metal kernel work was performed.
