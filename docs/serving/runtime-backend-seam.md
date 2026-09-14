# Synthetic runtime backend seam

The synthetic server selects its backend only when `AppState` is constructed.
HTTP request fields cannot select a provider, path, endpoint, credential, or
plugin. The shipped executable constructs the deterministic synthetic provider.

`CompletionBackend` receives an already validated `BackendRequest`, a bounded
semantic-event sender, and a server-provided cancellation observation. The
request preserves roles, content, the validated model identity, and the
synthetic output limit. The owned provider future yields one assistant role,
UTF-8 text deltas, then either one finish carrying actual synthetic usage or a
safe typed failure. External providers can construct every public event without
access to synthetic internals. The provider does not own HTTP, SSE framing,
authentication, permits, metrics, or sockets.
The server continues to own request admission, completion IDs, bounded
backpressure, generation ownership, shutdown, and connection reaping.

The server validates ordering and rejects missing, duplicate, out-of-order, or
post-terminal output. It caps each run at 64 semantic events and 16 KiB of text.
Non-stream responses are buffered until the sequence is valid. Streaming sends
events as validated; a terminal already delivered cannot be retracted, so later
provider output is discarded and classified as a provider protocol failure.
Timeout, shutdown, downstream failure, and early drop signal cancellation and
keep the provider future inside the generation guard's owned lifetime.

The deterministic provider preserves `pulsarmlx-synthetic-v1`, its fixed output,
and its explicitly synthetic usage units. The two-second generation policy is a
synthetic qualification limit, not a real-runtime latency claim. No real model,
LM Studio integration, cloud destination, or tokenizer accounting is provided
by this seam.
