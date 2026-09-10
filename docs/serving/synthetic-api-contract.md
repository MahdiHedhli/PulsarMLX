# Synthetic OpenAI-style API contract

Status: implemented and tested for the synthetic backend only. This server does
not load a checkpoint, use MLX or CUDA, perform inference, or advertise GLM
availability. It is a bounded protocol and client-integration fixture.

## Starting the server

Create a new bearer token containing 16 to 256 non-whitespace bytes in a regular
file with mode `0600`, then run the standalone crate:

```console
cargo run --manifest-path crates/serve-synthetic/Cargo.toml -- \
  --token-file /private/path/to/token --port 0
```

The server binds IPv4 loopback only. Port `0` selects an ephemeral port, which
is printed with the loopback listening address. Logs contain no bearer token,
request content, response content, or model identifier. The token file is
opened as a file handle and its identity is checked against the pre-open path
metadata to reject symlinks and path replacement during opening.

## Supported surface

| Route | Authentication | Behavior |
| --- | --- | --- |
| `GET /health` | None | Fixed `{"status":"ok","synthetic":true}` liveness payload. |
| `GET /v1/models` | Bearer | Lists only `pulsarmlx-synthetic-v1` and its synthetic capabilities. |
| `POST /v1/chat/completions` | Bearer | One text-only deterministic choice as JSON or SSE when `stream` is true. |

Chat requests accept `model`, `messages`, `stream`, `max_tokens`, `n`,
`temperature`, and `top_p`. Only `n=1`, `temperature=1`, and `top_p=1` are
accepted. Message objects accept only `role` and string `content`; roles are
`system`, `user`, and `assistant`. Every other field is rejected before the
synthetic backend starts. Tools, images, arbitrary model or backend paths,
embeddings, Responses API, response schemas, persistence, and cloud fallback
are unsupported.

The fixed success output is `SYNTHETIC_OK: café 🚀`, represented by three
synthetic vocabulary tokens. `max_tokens` truncates that synthetic sequence and
uses `finish_reason: length`; these counts are not estimates of model-token
usage. The empty fixture reports zero completion tokens because this backend
authoritatively produced an empty synthetic sequence. A future backend without
authoritative usage must omit usage.

SSE chunks retain one completion ID, model ID, and creation time, split content
on UTF-8 character boundaries, emit an explicit finish reason, and emit
`data: [DONE]` only after successful completion. Failure after streaming starts
uses a safe `event: error` payload and closes without a success terminal.

## Resource and time limits

| Limit | Value | Enforcement |
| --- | ---: | --- |
| Application header bytes | 8 KiB | Before route or backend work; parser buffer is capped at 32 KiB. |
| Request body | 16 KiB | From both declared length and accumulated body frames. |
| Messages | 16 | Before generation ownership is acquired. |
| Content per message | 2 KiB UTF-8 bytes | Before generation ownership is acquired. |
| Output | 16 synthetic tokens | Before generation; the fixture currently emits at most 3. |
| Connections | 32 | Immediate close when capacity is unavailable; no connection queue. |
| Generations | 1 | Immediate structured `429 server_busy`; no generation queue. |
| Header read | 5 seconds | Hyper HTTP/1 parser deadline. |
| Whole connection | 15 seconds | Bounds request read and response service lifetime. |
| Generation | 2 seconds | Cancels work and omits success terminal on expiry. |
| Stream channel send | 500 milliseconds | Cancels a producer stalled by downstream backpressure. |

Shutdown stops accepting connections, signals active stream producers, aborts
owned connection tasks, waits for those tasks to be reaped, and releases all
generation permits through owned guards. Each connection is HTTP/1.1 with
keep-alive disabled.

## Errors and destination boundary

Errors are JSON objects with a stable machine-readable `error.code` and a safe
message. Authentication, host/origin checks, malformed JSON/body/framing,
oversized inputs, unsupported parameters, unknown model/route/method, busy
capacity, generation timeout, and backend failure are distinguishable. Hyper
performs HTTP/1 framing validation, including rejection of conflicting content
lengths.

The official SDK test supplies an explicit literal-loopback base URL through a
transport that rejects every non-loopback destination before transmission. It
also disables redirects, retries, and environment proxy settings. This is an
application destination guard, not OS-wide network isolation.

## Future runtime attachment

The synthetic generation modes exercise ordered role/content events, stable
identifiers, explicit finish/error outcomes, cancellation, and authoritative
synthetic usage. A real runtime adapter requires separate implementation,
privacy review, model validation, and qualification. This contract does not
qualify full OpenAI compatibility, LM Studio integration, or real inference.
