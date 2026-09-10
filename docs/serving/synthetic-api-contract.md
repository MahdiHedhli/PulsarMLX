# Synthetic OpenAI-style API contract

Status: preparation only. This contract describes the first synthetic serving
slice. It does not attach an inference runtime, load a checkpoint, or advertise
GLM availability.

## Process boundary

The synthetic server binds only to `127.0.0.1` on an explicitly selected or
ephemeral port. `/health` is unauthenticated and returns only a fixed liveness
payload. Every `/v1` route requires a dedicated synthetic bearer token supplied
from an owner-only file; tokens, request bodies, response bodies, and model
identifiers are excluded from default logs.

The server must bound request headers, body bytes, message count, message byte
length, output tokens, queued work, and read/write/generation deadlines before
backend work starts. It accepts no model path, backend URL, tool call, MCP
configuration, persisted conversation, or cloud fallback.

## Supported subset

| Route | Supported behavior | Explicit rejections |
| --- | --- | --- |
| `GET /health` | Fixed liveness JSON without environment details | N/A |
| `GET /v1/models` | Lists only `pulsarmlx-synthetic-v1` and synthetic capabilities | Unknown route/method |
| `POST /v1/chat/completions` | One text-only choice; deterministic backend; `stream: false` JSON or `stream: true` SSE | Unknown model, multiple choices, tools, images, embeddings, Responses API, JSON-schema response formats, nondefault sampling semantics |

The synthetic backend owns the ordered role/content delta events, terminal
reason, error metadata, and synthetic token-vocabulary usage. A backend that
cannot provide usage leaves it absent; it must never estimate real-token usage
from characters or report unavailable usage as zero.

For streams, all chunks share a stable completion ID, model ID, and creation
time. Chunks use UTF-8-safe role/content deltas, end with a terminal finish
reason and normal SSE termination. A disconnect, cancellation, deadline,
backpressure failure, or backend error cancels and releases the owned work; it
does not fabricate a successful final completion or usage record.

## Error contract

Errors are structured JSON with a stable machine-readable `code` and a safe
message. Authentication, malformed or oversized requests, unsupported fields,
unknown model, busy capacity, deadline expiry, and backend failure must be
distinguishable. Invalid requests are rejected before the backend is invoked.

## Future runtime attachment

The eventual adapter may provide a real model descriptor, generation event
stream, cancellation handle, and terminal metadata through the same boundary.
That attachment requires its own runtime validation and does not follow from
this synthetic contract.
