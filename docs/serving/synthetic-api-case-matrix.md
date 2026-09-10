# Synthetic API acceptance case matrix

Status: Terra-authored test scaffold. The implementation tests named here are
not present until the constrained implementation author is admitted.

| ID | Case | Independent assertion |
| --- | --- | --- |
| SAPI-01 | Protocol build | macOS builds fake-backend protocol without MLX, CUDA, model discovery, or inference dependencies. |
| SAPI-02 | Model listing | Raw HTTP sees only the synthetic model and its declared capabilities. |
| SAPI-03 | Non-stream completion | Fixed request yields the predeclared deterministic response and synthetic usage. |
| SAPI-04 | SSE reassembly | Raw HTTP reassembles UTF-8-safe chunks to the same predeclared response as SAPI-03. |
| SAPI-05 | SDK loopback | Pinned official OpenAI Python SDK talks only to loopback with retries disabled and `trust_env=False`. |
| SAPI-06 | Destination guard | An HTTPX transport guard rejects a non-loopback fake cloud URL before any transmission or redirect follow. |
| SAPI-07 | Validation | Missing/wrong auth, malformed/oversized bodies, unknown model, and unsupported fields fail before backend work. |
| SAPI-08 | Failure modes | Empty output, output limit, backend failure before/after first chunk, cancellation, disconnect, slow reader, deadline, and queue saturation release generation ownership. |
| SAPI-09 | Privacy boundaries | Default logs contain no token, request, response, or key contents; server has no HTTP-client or cloud-fallback path. |
| SAPI-10 | Fresh process | A newly started server passes health, model listing, one non-stream response, and clean shutdown. |

The guard in SAPI-06 demonstrates application destination rejection only. It is
not an OS-wide network isolation or full client-compatibility claim.
