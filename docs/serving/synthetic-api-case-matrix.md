# Synthetic API acceptance case matrix

Status: implemented and measured on macOS for the standalone synthetic crate,
and qualified in CI by the `Serving synthetic qualification` workflow.

Independent review status: the source at commit `54e07b60` received an
independent ACCEPT with zero blocking findings. The changes recorded here were
made after that review and have **not** been independently reviewed.

| ID | Case | Result | Evidence |
| --- | --- | --- | --- |
| SAPI-01 | Protocol build | PASS | Standalone Cargo build and Clippy use only the pinned protocol/runtime dependencies in the crate-local lock; no MLX, CUDA, model discovery, or inference dependency. |
| SAPI-02 | Model listing | PASS | Raw HTTP checks the sole model ID, exact synthetic capabilities, authentication, and no-store response header. |
| SAPI-03 | Non-stream completion | PASS | Raw HTTP checks the predeclared UTF-8 output, finish reason, and authoritative synthetic usage. |
| SAPI-04 | SSE reassembly | PASS | Raw HTTP reassembles UTF-8-safe deltas, stable ID/time, finish reason, and final `[DONE]` to the same output. Each multibyte character is asserted to arrive as its own delta, so both `é` and the astral-plane `🚀` sit on real chunk boundaries. |
| SAPI-05 | SDK loopback | PASS | Official `openai==3.11.0` lists models and completes non-stream and stream requests through explicit loopback with retries and environment proxy use disabled. |
| SAPI-06 | Destination guard | PASS | The HTTPX2 transport rejects a fake cloud URL before its inner transport and does not follow a fake loopback-to-cloud redirect. |
| SAPI-07 | Validation | PASS | Raw HTTP covers missing/wrong auth, host/origin, duplicate `Host`, unsupported fields/sampling, message/body/header limits, malformed/truncated/framing input, model, route, and method before backend work. Malformed JSON, unsupported `Content-Type` (415), malformed declared length, and `max_tokens` outside the supported range each have their own assertions. The declared-length cap and the accumulated-frame cap are covered by separate tests: the chunked case declares no length, so only frame accumulation can reject it. |
| SAPI-08 | Failure modes | PASS | Tests cover empty and output-limit outcomes; failure before/after output; non-stream and stream deadlines; busy capacity; disconnect; shutdown cancellation; backpressure send timeout; and exact ownership release. A stream that exceeds its generation deadline is asserted to carry a bounded `generation_timeout` error event, to emit no success terminal, and to release the single generation permit for reuse. |
| SAPI-09 | Privacy boundaries | PASS | Fresh-process capture finds no fixture token, input, output, or model ID in stdout/stderr; source has no HTTP client or cloud fallback. |
| SAPI-10 | Fresh process | PASS | A newly spawned binary passes health, model listing, non-stream completion, SIGINT shutdown, and child reaping. |
| SAPI-11 | Error classification | PASS | `error.type` is asserted to follow the status: `authentication_error` for 401, `server_error` for 500 and 504, `invalid_request_error` for other 4xx. |
| SAPI-12 | Connection lifecycle | PASS | Completed connection tasks are asserted to be reaped while the accept loop is still running, and shutdown is asserted to drain in-flight connections with spawned and reaped counts balancing. |

Rust validation is `cargo test` and `cargo clippy --all-targets -- -D warnings`
from `crates/serve-synthetic`. The pinned Python environment is listed in
`crates/serve-synthetic/tests/sdk-requirements.txt`; `sdk_client.py` performs
the SDK checks and `tests/sdk_smoke.sh` runs it against a freshly started
loopback server.

`mutation_guards.py` creates isolated copies and proves eleven negative
variants are rejected: missing authentication; an accepted oversized declared
length; an accepted oversized accumulated body; missing ownership release;
fabricated success after stream failure; unreaped connection tasks; a silently
closed stream after a generation timeout; first-`Host`-wins; a flattened
`error.type`; an unguarded cloud destination; and redirect following.

The declared-length and accumulated-frame caps are mutated separately. A single
mutant covering both let either test conceal a missing check, because a request
that declares an oversized length and also sends one is still caught by frame
accumulation alone.

A mutant only counts as killed when the named test actually ran and reported
`FAILED`. Rust mutants are compiled first, so a mutant that fails to build is
reported as a setup error rather than a kill, and Python guard mutants must
fail an assertion rather than an import. Applying this check revealed that the
two Python guard mutants had previously been passing only because the pinned
SDK packages were absent, so the process exited non-zero on
`ModuleNotFoundError` without the guard ever running.

## Where these run

| Check | Local | CI |
| --- | --- | --- |
| `cargo fmt --check`, `cargo clippy -D warnings`, `cargo test` for the crate | yes | yes, `Serving synthetic qualification` |
| `sdk_smoke.sh` (pinned `openai==3.11.0` against a loopback server) | yes | yes, same workflow |
| `mutation_guards.py` (11 mutants) | yes | yes, same workflow |
| `cargo check/test --workspace` in `macOS baseline` | n/a | does **not** cover this crate |

`crates/serve-synthetic` declares its own `[workspace]`, so it is not a member
of the root workspace and `cargo test --workspace` never builds it. Before the
`Serving synthetic qualification` workflow existed, no CI job compiled or
tested this crate, and a green run on the repository said nothing about it. The
workflow carries no path filter, matching the existing workflows: a
path-filtered job reports success when skipped, which would make it a weaker
gate than the baseline beside it.

SAPI-05 qualifies only the tested OpenAI Python SDK version and supported route
subset. SAPI-06 demonstrates application destination rejection only. The
matrix makes no full OpenAI, real-model, LM Studio, or OS-wide isolation claim.
