# Contract: Backend Selection and MLX Worker v1

**Status**: Proposed for implementation

**Protocol version**: `1`

**Transport**: one persistent child process; UTF-8 NDJSON control channel

## Backend boundary

Common Rust code selects a backend explicitly and receives a capability report
before creating tensor resources. The boundary exposes semantic operations and
owned handles; it does not expose Python objects, MLX arrays, CUDA pointers,
streams, graph-capture objects, or allocation mechanisms.

The minimum semantic surface for the bring-up is:

- report backend and device capabilities;
- create a typed tensor from bounded fixture data;
- execute a named deterministic tensor operation;
- force evaluation and synchronization;
- read back a bounded result for validation; and
- release resources and shut down deterministically.

Each operation is accepted only when its `TensorContract` declares shape,
layout, input/accumulation/output dtype, synchronization, and comparison policy.
Backend-specific optimized operations may be advertised separately and are not
required of other backends.

## Selection rules

1. `apple-mlx` is never selected implicitly for an inherited Linux invocation.
2. An explicit `apple-mlx` request fails as unsupported unless the host,
   package, Metal, and requested device prerequisites pass.
3. Validation and benchmark execution always sets `allow_fallback=false`.
4. The client reports `available_unevaluated` until an explicitly scheduled
   operation is evaluated, synchronized, and numerically checked.
5. A worker failure, timeout, malformed response, or parity failure does not
   cause CPU fallback or a successful capability claim.

## Process lifecycle

```text
Rust client       Python worker
    |--- spawn -------->|
    |<-- hello ---------|
    |--- health ------->|
    |<-- response ------|
    |--- tensor_probe ->|
    |<-- response ------|
    |      ...           |
    |--- shutdown ----->|
    |<-- response ------|
    |<-- exit 0 --------|
```

- One worker lives for one backend context; do not spawn per tensor operation.
- stdin carries requests; stdout carries protocol responses only; stderr carries
  human-readable diagnostics without secrets.
- Every request except the initial worker `hello` has an unsigned request ID.
- Responses preserve request IDs. v1 processes one request at a time, so
  response order is request order; later concurrency requires a new capability.
- EOF, a nonzero exit, or a malformed message invalidates the worker context.
- The client sends `shutdown`, closes stdin, and waits for a bounded interval.
  Forced termination is cleanup after a failed graceful shutdown and is
  recorded as an error.

## Framing and limits

- Encoding is UTF-8 JSON, exactly one object per line, terminated by LF.
- A request line is at most 64 KiB; a response line is at most 1 MiB.
- Nesting depth, list lengths, shapes, element counts, and byte counts are
  validated before allocation or execution.
- Unknown required protocol versions are rejected. Unknown fields may be
  ignored only when the message declares a compatible minor extension.
- stdout text that is not a valid response is a protocol violation.
- Large tensors, weights, and model files are not represented as numeric JSON
  lists or base64. The v1 control protocol returns only bounded probes, slices,
  summaries, and checksums.
- A later binary or file-backed payload mechanism must specify exact byte
  length, dtype, shape, ownership, allowed path root, cleanup, and checksum; it
  is not implied by v1.

## Message envelope

Request:

```json
{
  "protocol": 1,
  "request_id": 7,
  "op": "tensor_probe",
  "params": {}
}
```

Successful response:

```json
{
  "protocol": 1,
  "request_id": 7,
  "ok": true,
  "result": {}
}
```

Error response:

```json
{
  "protocol": 1,
  "request_id": 7,
  "ok": false,
  "error": {
    "code": "device_unavailable",
    "message": "bounded diagnostic without secrets",
    "retryable": false,
    "details": {}
  }
}
```

Stack traces are diagnostics on stderr or sanitized test artifacts, not public
protocol fields. Paths in errors are redacted to a configured model/fixture
identifier when evidence will be committed.

## Worker hello

The first stdout message is unsolicited and has `op="hello"`, no request ID,
and these fields:

| Field | Requirement |
| --- | --- |
| `protocol` | Exactly `1` |
| `worker_version` | Exact PulsarMLX worker version/commit |
| `python_version` | Full interpreter version |
| `python_arch` | Must be `arm64` for `apple-mlx` |
| `mlx_version` | Must equal the project pin |
| `macos_version` | Actual runtime version |
| `metal_available` | Boolean from the MLX API |
| `gpu_count` | Nonnegative integer |
| `devices` | Bounded sanitized device descriptors |
| `capabilities` | Explicit operation and dtype IDs |
| `limits` | Effective request/response and fixture limits |

A version mismatch, non-arm64 process, false Metal availability, or zero GPU
count prevents device evaluation and creates an unsupported capability report.

## Required v1 operations

### `health`

Returns worker readiness and repeats protocol/runtime identity. It performs no
device success claim.

### `tensor_probe`

Parameters include an exact fixture ID and explicit device `gpu`. The worker:

1. validates the pinned runtime and explicit device;
2. constructs a small nonsymmetric float32 fixture;
3. schedules a matrix multiplication on `mx.gpu`;
4. calls `mx.eval` and `mx.synchronize`;
5. compares a bounded output with independent expected values; and
6. returns input/output shapes and dtypes, selected device information, actual
   values or a small digest, error metrics, and `passed`.

The client may transition the report to `evaluated` only when `passed=true` and
the response identity matches the worker `hello`.

### `shutdown`

Rejects new work, releases backend-owned references, synchronizes any admitted
operation, returns success, and exits zero. If cleanup encounters an error, the
response and exit status must not claim a clean shutdown.

## Later operations under the same semantic contract

The implementation may add version-compatible operations for fixture tensor
creation, embedding, RMS norm, dense matmul, quantized reference execution,
routing, grouped expert execution, and bounded model slices. Each addition must
define its own exact parameter/result schema, resource limits, tensor contract,
and independent validation case before being listed as supported.

## Error codes

The initial stable classes are:

- `protocol_mismatch`
- `message_too_large`
- `malformed_request`
- `unsupported_operation`
- `invalid_shape`
- `invalid_dtype`
- `invalid_layout`
- `invalid_byte_count`
- `runtime_version_mismatch`
- `unsupported_host`
- `metal_unavailable`
- `device_unavailable`
- `evaluation_failed`
- `comparison_failed`
- `resource_limit`
- `internal_worker_error`

Errors include bounded structured context but never environment variables,
tokens, complete private paths, model contents, or arbitrary exception data.

## Contract validation

Required tests include:

- fragmented stdin delivery and multiple complete messages;
- oversized, non-UTF-8, invalid JSON, missing, duplicate, and unknown operation
  messages;
- protocol and pinned-runtime mismatch;
- stdout contamination detection;
- request-ID matching and sequential response order;
- graceful shutdown, crash, EOF, timeout, and nonzero exit;
- non-arm64, Metal unavailable, zero-GPU, and explicit-device rejection;
- successful evaluated probe with exact shape/dtype/value evidence; and
- a numerical mismatch that remains `available_unevaluated` and returns a
  failing validation record.

Tests must not depend on secrets or a downloaded model. Unit tests can use a
fake worker; the real device probe is a separate Apple Silicon integration
case.
