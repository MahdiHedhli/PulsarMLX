# Synthetic runtime backend seam

The synthetic server selects its backend only when `AppState` is constructed.
HTTP request fields cannot select a provider, path, endpoint, credential, or
plugin. The shipped executable constructs the deterministic synthetic provider.

`CompletionBackend` receives an already validated `BackendRequest` and a
server-provided cancellation observation. It returns a semantic session; it
does not own HTTP, SSE framing, authentication, permits, metrics, or sockets.
The server continues to own request admission, completion IDs, bounded
backpressure, generation ownership, shutdown, and connection reaping.

The deterministic provider preserves `pulsarmlx-synthetic-v1`, its fixed output,
and its explicitly synthetic usage units. The two-second generation policy is a
synthetic qualification limit, not a real-runtime latency claim. No real model,
LM Studio integration, cloud destination, or tokenizer accounting is provided
by this seam.
