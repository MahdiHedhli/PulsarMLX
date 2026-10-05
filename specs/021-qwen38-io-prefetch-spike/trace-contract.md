# Synthetic prefetch trace contract v0.3

This contract describes evidence a future MLX pager must emit. The current Python validator is model-free; passing it proves trace consistency, **not** asynchronous runtime safety, numerical parity, or speed.

Each trace is a JSON object with `schema`, `base_commit`, `model_revision`, `tokenizer_revision`, `runtime_revision`, `prompt_digest`, `decode_settings_digest`, `output_token_ids`, `logits_digest`, `arm`, `warmth`, positive `max_prefetch_requests` and `max_prefetch_bytes`, `events`, and `metrics`. Events have nonnegative monotonic integer `t_ns`. Digests here bind outputs and identity; they are not a substitute for inspecting numerical error against the upstream reference. Valid event forms:

| Event | Required fields | Meaning |
| --- | --- | --- |
| `route` | `step`, `layer`, `selected`, `executed`, `weights_digest` | Execution IDs equal actual router IDs for one step and layer; digest binds actual weights. |
| `ple_lookup` | `step`, `global_row`, `key` | Declares the PLE lookup that authorizes a PLE demand. The producer must derive the key from the admitted catalog geometry. |
| `demand_queued`, `demand_start`, `demand_finish` | `key`; `demand_queued` also has `step` | An expert demand key must match a route at the same step and layer; a PLE key must match a declared lookup at the same step. A demand starts after queueing and finishes after page use. Repeated demand is allowed after finish. |
| `demand_io_start`, `demand_io_done` | `key` | Records a demand-path read. An unserved started demand blocks speculative reads until this read completes or its in-flight prefetch completes. |
| `hint`, `hint_invalidate` | `key` | Hints may be invalidated when the route/window changes. |
| `cancel` | none | Invalidates all hints. In-flight reads must complete and release buffers before the request ends. |
| `prefetch_start` | `key`, positive `bytes` | Requires a live hint, no queued demand or demand waiting on an in-flight hint, and room under both caps. |
| `prefetch_io_done` | `key` | The read has completed, including failure/cancellation handling. |
| `prefetch_use`, `prefetch_gpu_done` | `key` | Optional GPU use; only completed, valid hints with a real started demand may be used. |
| `buffer_release` | `key` | Allowed only after I/O and any GPU use complete. This releases reserved capacity. |

Each `metrics` object records `physical_ssd_read_bytes` or null with an explicit measurement state, `logical_expert_read_bytes`, `prefetch_useful_bytes_before_demand`, `prefetch_late_bytes`, `prefetch_wasted_bytes`, `peak_footprint_bytes`, `swap_delta_bytes`, `ttft_ns`, `request_end_ns`, `decode_p50_ns`, `decode_p95_ns`, `decode_p99_ns`, and `max_intertoken_stall_ns`. Useful bytes completed I/O before the actual demand start and were used; late bytes completed after demand start and were used; wasted bytes were never used. These three categories must sum to all admitted prefetch bytes. A successful trace requires zero swap growth and a reported peak footprint at least as large as the maximum declared live prefetch buffers. These counters are measured per request, not inferred from a predictor accuracy score. Physical I/O may be null only when state is `unavailable`; such a run cannot support an SSD traffic claim. The producer must state whether bytes include page-cache reads and distinguish OS-cache warmth from logical-cache state.

`compare_pair` requires a valid baseline and candidate with identical identity fields, warmth, route IDs and weight digests, output token IDs, and final logits digest. This exact-output gate is appropriate for the proposed I/O-only change. A real reference admission still needs layerwise and logits numerical tolerances with independently computed values. The production pager must maintain buffer ownership across actual I/O and GPU completion events, including cancellation, not merely emit a plausible trace.

The validator checks internal consistency of self-reported events. It cannot prove that the model really emitted a route or PLE lookup, that a PLE global row maps to the declared page, that byte counts match the header catalog, or that host memory measurements came from macOS. Those bindings require an instrumented adapter and independent review before a real-model claim.
