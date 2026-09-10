# Client integration against the synthetic server

This describes how to point an OpenAI-compatible client at the PulsarMLX
synthetic serving fixture, and exactly which client behaviours are qualified.

The server performs **no inference**. Everything below is synthetic. A passing
client integration here is not evidence that any real model backend works.

## Scope

Qualified against `openai==3.11.0` (Python) over IPv4 loopback. Other SDKs,
other versions and other transports are untested.

The server implements a deliberately small subset:

| Route | Method | Auth |
| --- | --- | --- |
| `/health` | GET | none |
| `/v1/models` | GET | bearer |
| `/v1/chat/completions` | POST | bearer |

Chat requests accept `model`, `messages`, `stream`, `max_tokens`, `n`,
`temperature` and `top_p`. Any other field is rejected as
`unsupported_parameter`; `n` must be 1 and the sampling controls must be left
at their defaults. There is no tool calling, no function calling, no
multi-modal content, no embeddings, no completions endpoint, and no
`response_format`. This is **not** full OpenAI compatibility and must not be
described as such.

## Setting up a client

Start the server with a disposable token file:

```console
openssl rand -hex 20 > /tmp/pulsar-token
chmod 600 /tmp/pulsar-token
cargo run --manifest-path crates/serve-synthetic/Cargo.toml \
  --bin pulsar-serve-synthetic -- --token-file /tmp/pulsar-token --port 0
```

The token file must be a regular, non-symlink file with mode `0600` containing
16-256 non-whitespace bytes. The server prints the bound loopback address on
stderr and binds IPv4 loopback only.

Point the SDK at it:

```python
import httpx2 as httpx
import openai

with httpx.Client(follow_redirects=False, trust_env=False,
                  timeout=httpx.Timeout(5.0)) as http_client:
    client = openai.OpenAI(
        api_key=open("/tmp/pulsar-token").read().strip(),
        base_url="http://127.0.0.1:PORT/v1",
        http_client=http_client,
        max_retries=0,
    )
```

Use a token generated for the run. Do not reuse an existing OpenAI key, and do
not let the client read ambient configuration: `trust_env=False` keeps proxy
environment variables out of the path, and `follow_redirects=False` prevents a
redirect from moving the request off loopback.

`Host` must be `127.0.0.1:PORT` or `localhost:PORT`, and exactly one `Host`
value is accepted. An `Origin`, if present, must match the `Host`.

## Qualified client behaviours

Each row is asserted by `crates/serve-synthetic/tests/sdk_client.py`, driven by
`tests/sdk_smoke.sh` against a freshly started server.

| Behaviour | What is asserted |
| --- | --- |
| Model listing | The sole model ID is returned. |
| Non-streaming chat | Exact content, `finish_reason`, and authoritative synthetic usage. |
| Streaming chat | Deltas reassemble byte-identically, with a stable ID and creation time and one finish reason. |
| Authentication | A wrong bearer token raises `AuthenticationError` with `code=invalid_api_key` and `type=authentication_error`. |
| Error handling | Unknown model, backend failure (500, `type=server_error`) and generation timeout (504, `type=server_error`) each surface as the matching SDK exception. |
| Rate limiting | With the single generation slot held, a second request raises `RateLimitError` with `code=server_busy` and `type=rate_limit_error`. |
| Client timeout | A client timeout shorter than the generation deadline raises `APITimeoutError`, and the server remains usable afterwards. |
| Mid-stream cancellation | Abandoning and closing a stream part-way releases the server's generation permit. |
| Streaming failure | A stream that times out or fails after headers raises `openai.APIError` instead of ending cleanly. It never reports `finish_reason: stop`. |
| Bounded requests | Message count, per-message size and `max_tokens` bounds surface as `BadRequestError` with distinct codes. |
| Response assembly | Truncated output assembles to `finish_reason: length` in both modes; an empty completion is well formed with zero completion tokens. |
| Resource release | After every failure path above, a normal request still succeeds, so the single generation slot was released. |
| Destination guard | A transport rejects any non-loopback destination before transmission and does not follow a loopback-to-cloud redirect. |
| No sensitive content in logs | With `openai`, `httpx2` and `httpcore2` at DEBUG, the captured output mentions the requests but never contains the bearer token. The capture is asserted non-empty so the check cannot pass vacuously. |

Server-side logging is separately asserted: `sdk_smoke.sh` fails if the server's
own output contains the bearer token, and SAPI-09 covers fixture token, input,
output and model ID absence from a fresh process.

## Known limits

- Only `openai==3.11.0` is qualified. The pinned set is in
  `tests/sdk-requirements.txt`.
- The streaming failure signal is best effort and bounded by the stream send
  deadline. A consumer that has already stalled or disconnected receives no
  error event, because delivery is no longer possible.
- `max_retries=0` is used throughout. SDK retry and backoff behaviour against
  this server is not qualified.
- No asynchronous client (`openai.AsyncOpenAI`) is exercised.
- The log assertion covers the SDK's own logging at DEBUG. It does not prove
  anything about application logging built on top of the client.
