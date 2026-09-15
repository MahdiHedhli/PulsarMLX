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
the async future is destroyed but the designated supervisor's registry keeps
its generation lease. Admission and active ownership remain occupied until
the worker really exits, is joined and its session is destroyed. The existing
cleanup-bound-drop metric describes the wrapper, not native worker reaping.

## Caller-owned cleanup supervisor

Every `AppState::new(token, &owner)` or `AppState::with_backend(token, backend,
&owner)` requires a caller-owned `CleanupOwner`. Keep this owner separate from
the spawned `serve` future. Request state, registration tickets, semantic
futures and tracked tasks carry only weak cleanup capabilities and leaf metrics
or semaphore resources. The supervisor alone owns the canonical permit entries
and connection/stream task sets. Neither pending leases nor tracked tasks retain
the full supervisor/state graph. An unregistered RuntimeBackend session cannot
launch a synchronous worker; missing-owner admission is refused.

```rust,ignore
let owner = CleanupOwner::new();
let state = AppState::with_backend(token, backend, &owner)?;
let outcome = serve(listener, state, shutdown_signal).await?;
match outcome {
    ShutdownOutcome::Complete(snapshot) => { /* actual joins, empty tasks */ }
    ShutdownOutcome::Incomplete(pending) => {
        // Keep owner reachable. Cancellation is only a request.
        let recovered = pending.drain.drain(recovery_budget).await;
        // recovered can still be INCOMPLETE; no thread is forcibly killed.
    }
}
```

Shutdown retains the 250 ms wire grace, shorter than the 500 ms inline producer
cleanup bound; uncooperative producers have no promised shutdown wire terminal.
`serve` then cancels subordinate tasks and performs a finite supervisor drain.
Its typed COMPLETE result requires no running serve, no active leases, no join
in progress and empty owned connection/stream task state. INCOMPLETE carries a
truthful snapshot and a weak drain capability to the same designated owner; it
does not duplicate ownership. Actual joins and unique permit releases happen
once, and repeated/concurrent drain callers cannot report COMPLETE early.
`AppState::drain_cleanup` is only a request-resource snapshot, not a complete
server-shutdown result.

Aborting serve, connection, stream or request futures requests cancellation and
preserves the caller's designated owner and registered capacity. No registry or
worker-handle mutex is held across joins or user session destruction. Reentrant
reaping returns without stealing an in-progress join. Even cancellation before
generation launch destroys its session on an actual owned cleanup thread, so a
blocking native destructor cannot block the async reaper. Thread spawn refusal
retains session/capacity and cannot establish COMPLETE.

Keep the designated supervisor until typed COMPLETE. Arbitrarily forgetting it
or terminating the process remains unqualified. Its bounded abandonment path
aborts tasks and warns INCOMPLETE, deliberately retaining outstanding handles,
task sets and permits rather than releasing live capacity or blocking forever.
This is an explicit resource leak under supervisor abandonment, not a cycle or
a successful cleanup guarantee. Reclaiming arbitrary uncooperative work would
require a separate process-supervision boundary. No detached reaper, background
service, process killing or successful native shutdown bound is supplied.

This qualifies only controlled synthetic workers while the designated supervisor
is retained. Real engine binding, tokenizer/GLM history rendering, native
cancellation, real client dogfood and arbitrary final-supervisor reclamation
remain unqualified.
