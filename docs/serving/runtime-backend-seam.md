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

Closing the semantic-event channel is not provider completion. The consumer
tracks the owned future as polling, returned, or dropped at the cleanup bound;
only polling the future to `Ready` records a return. EOF while it is still
polling signals cancellation and waits cooperatively. If the future does not
return within `STREAM_SEND_DEADLINE` (500 ms), the consumer destroys that owned
in-process future before releasing the generation permit and increments
`backend_cleanup_bound_drops`. The same constant also bounds stream-channel
sends; those two uses have different meanings even though they currently share
one fixed value. This contract covers cooperative inline futures only, not
blocking or escaped native work.

`backend_finished` counts released admitted-request ownership in every wire
outcome; it is not proof that the provider future returned. A cleanup-bound drop
is tracked separately and is never described as a successful return or reaping.
Valid non-stream output whose cleanup expires becomes the existing HTTP 504
`generation_timeout`. A stream terminal already sent is retained without a
second terminal; the body closes only after cleanup returns or the owned future
is destroyed at the bound. Missing terminals remain provider protocol failures.

Provider usage is admitted only when prompt and completion counts add exactly
with checked integer arithmetic. Overflow is a safe provider protocol failure
before any success terminal. The server preserves representable counts exactly
and does not estimate usage from content, messages, words, or byte length.

The deterministic provider preserves `pulsarmlx-synthetic-v1`, its fixed output,
and its explicitly synthetic usage units. The two-second generation policy is a
synthetic qualification limit, not a real-runtime latency claim. No real model,
LM Studio integration, cloud destination, or tokenizer accounting is provided
by this seam.

## Injected synchronous fixture sessions

`runtime_adapter::RuntimeBackend` is a model-free injected provider selected at
`AppState` construction. It is not a real engine or GLM template. Each request
creates one exclusive `RuntimeSession`, renders explicit fixture prompt IDs
(capped at 4096), and runs that session on an actual owned synchronous thread.
Generated callback ordinals must be contiguous; vocabulary IDs may repeat.
The adapter derives usage from rendered prompt-ID length and accepted non-stop
generated IDs, never text length, words, messages, or producer-authored totals.
A stopping ID has no visible bytes and is excluded from completion usage. Text
bytes are buffered across token fragments until a valid UTF-8 prefix exists;
invalid or incomplete UTF-8 cannot produce a successful finish.

The worker's raw-output EOF, successful terminal, cancellation flag and async
wrapper destruction are not join acknowledgements. The actual thread handle
is joined only after `is_finished`; running workers are never blocking-joined
on an async executor thread. If the existing 500 ms inline cleanup expires,
the async future is destroyed but the generation lease moves into AppState's
owned cleanup registry. Admission and active ownership remain occupied until
the worker really exits, is joined and its session is destroyed. The existing
cleanup-bound-drop metric describes the wrapper, not native worker reaping.

Stream producer tasks now belong to AppState's JoinSet. Shutdown still has a
250 ms wire grace, shorter than the 500 ms producer cleanup bound; it does not
promise a shutdown terminal for uncooperative producers. `serve` returns a
`TimedOut` I/O error when generations or owned stream tasks remain; it does not
claim complete shutdown or zero resources. The caller must retain AppState and
use its finite `drain_cleanup` after its independent controlled-worker supervisor
releases the fixture barrier. Pending leases retain the cleanup owner until
join; no detached reaper or timeout-and-forget path is added.

This qualifies only controlled in-process synthetic workers with a retained
cleanup owner. Abandonment of the last externally reachable owner during an
uncooperative worker can retain an unreachable cleanup cycle. It is an unresolved
resource-lifetime blocker for real runtime installation, not a bounded native
shutdown guarantee. Real engine binding, real tokenizer/GLM history rendering,
native cancellation and real client dogfood remain unqualified.
