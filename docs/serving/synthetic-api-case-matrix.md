# Synthetic API acceptance case matrix

Status: implemented and measured on macOS for the standalone synthetic crate.

| ID | Case | Result | Evidence |
| --- | --- | --- | --- |
| SAPI-01 | Protocol build | PASS | Standalone Cargo build and Clippy use only the pinned protocol/runtime dependencies in the crate-local lock; no MLX, CUDA, model discovery, or inference dependency. |
| SAPI-02 | Model listing | PASS | Raw HTTP checks the sole model ID, exact synthetic capabilities, authentication, and no-store response header. |
| SAPI-03 | Non-stream completion | PASS | Raw HTTP checks the predeclared UTF-8 output, finish reason, and authoritative synthetic usage. |
| SAPI-04 | SSE reassembly | PASS | Raw HTTP reassembles UTF-8-safe deltas, stable ID/time, finish reason, and final `[DONE]` to the same output. |
| SAPI-05 | SDK loopback | PASS | Official `openai==3.11.0` lists models and completes non-stream and stream requests through explicit loopback with retries and environment proxy use disabled. |
| SAPI-06 | Destination guard | PASS | The HTTPX2 transport rejects a fake cloud URL before its inner transport and does not follow a fake loopback-to-cloud redirect. |
| SAPI-07 | Validation | PASS | Raw HTTP covers missing/wrong auth, host/origin, unsupported fields/sampling, message/body/header limits, malformed/truncated/framing input, model, route, and method before backend work. |
| SAPI-08 | Failure modes | PASS | Tests cover empty and output-limit outcomes; failure before/after output; non-stream and stream deadlines; busy capacity; disconnect; shutdown cancellation; backpressure send timeout; and exact ownership release. |
| SAPI-09 | Privacy boundaries | PASS | Fresh-process capture finds no fixture token, input, output, or model ID in stdout/stderr; source has no HTTP client or cloud fallback. |
| SAPI-10 | Fresh process | PASS | A newly spawned binary passes health, model listing, non-stream completion, SIGINT shutdown, and child reaping. |

Rust validation is `cargo test` and `cargo clippy --all-targets -- -D warnings`
from `crates/serve-synthetic`. The pinned Python environment is listed in
`crates/serve-synthetic/tests/sdk-requirements.txt`; `sdk_client.py` performs
the SDK checks. `mutation_guards.py` creates isolated copies and proves six
negative variants are rejected: missing authentication, acceptance of an
oversized body, missing ownership release, fabricated success after stream
failure, an unguarded cloud destination, and redirect following.

SAPI-05 qualifies only the tested OpenAI Python SDK version and supported route
subset. SAPI-06 demonstrates application destination rejection only. The
matrix makes no full OpenAI, real-model, LM Studio, or OS-wide isolation claim.
