# Task detail: Responses API, MCP, attachments and media

Feature 022, PulsarMLX Console. This file gives the full specification of each work package
with the prefix `RSP-`. The task list, the milestone order and the binding cross-cutting
decisions are in [`../tasks.md`](../tasks.md); **a binding decision or a reconciliation
there overrides any conflicting sentence in this file**.

Provenance: rendered without paraphrase from the planning records of 2026-11-14 (one planning
agent per subsystem, reading the pinned donor source). Path shorthand: `MAYA` is the pinned
project-maya checkout (commit `7e68a30f`), `ORIGIN` is this repository at `main` when the plan
was written. Sizes are estimates. Donor names such as `MAYA_*` variables describe the donor;
the product names are in [`../contracts/naming.md`](../contracts/naming.md).

## Subsystem summary

This subsystem is everything in project-maya serve/ that sits on top of the generation loop and is not a chat dialect itself: the OpenAI Responses API (responses.py: strict request normalizer, Responses event serializer, five routes), its in-memory credential-scoped response store (response_store.py), bounded background jobs with resumable SSE replay (response_jobs.py), validate-before-publish structured output (response_schema.py), the 18 MAYA_GLM_RESPONSES_* limits (response_config.py), the hand-rolled MCP client hub over stdio and Streamable HTTP with its server-side tool loop and strata_mcp dashboard events (mcp.py plus the server.py glue), the fake MCP server used as the test double (mcp_fake_server.py), attachment reading for Office, OpenDocument, EPUB, RTF, text encodings and PDF (attach.py, pdf.py, the 805-line pure reader pdf_text.py, and the optional poppler programs) behind POST /attach, POST /pdf and inline file parts in all three dialects, and the image and video plumbing (class Vision for the external maya-vision encoder process with ffmpeg/ffprobe video guards and GPU memory lending, plus ds4_vision.py and mm3_vision.py, which build DSI1 and MMI1 pixel files for the engine-side vision towers). Full parity means a Rust server driven by the deterministic fake engine and fake child processes (fake MCP server, fake vision encoder, fake poppler scripts) shows the same routes, status codes, SSE event order and payloads, error envelopes and the substrings that tests assert, config keys, environment variables, persisted vision-memory.json cache and wire files (DSI1, MMI1, SVE1, encoder line protocol) as project-maya at 7e68a30f, as pinned down by the 164 GPU-free test methods in the ten owned test files plus the VideoGuards and media-ordering tests in test_tool_videos.py and test_tool_images.py. Three design decisions anchor the plan. First, JSON Schema is checked by a restricted in-house validator that copies python-jsonschema's semantics on Maya's 19-keyword subset, including its one-second cooperative deadline. Second, the MCP client is written directly against the protocol rather than with rmcp, so wire details and error texts match and the dependency tree stays small. Third, document extraction is ported in house over just three small crates (miniz_oxide, roxmltree, html-escape), with an in-house ZIP reader and a faithful port of pdf_text.py, so Maya's exact-string tests remain the oracle. Vision is built as a VisionBackend seam with Maya's three mechanisms implemented and exercised only against fakes. The geometry and file formats will be exact. Pixel output will not be bit-exact with Pillow, and GPU lending is unverified on real hardware; both are labelled. The pure parts (schema validator, attachment and PDF readers, ds4/mm3 geometry) are kept free of tokio and process spawning, so the Phase 2 Rust/WASM front end can reuse them.

## Build order proposed by the planner

- Wave A, no dependency on other subsystems beyond the workspace skeleton; run in parallel: RSP-01, RSP-02, RSP-08, RSP-12, RSP-13, RSP-19 (geometry and writers first; pixel prepare can follow in the same session)
- Wave B, in parallel once each package's Wave A predecessor is merged: RSP-14 (after RSP-13), RSP-09 (after RSP-08), RSP-05 (after RSP-01), RSP-03 (after RSP-02 and PROMPT's message model)
- Wave C, in parallel: RSP-15 (after RSP-14), RSP-04 (after RSP-03 and CORE's generation-event types), RSP-10 (after RSP-09 and the shared outbound HTTP client)
- Wave D, needs CORE's prepare hook, FIFO and fake engine, plus HTTP routing: RSP-17, then RSP-18; RSP-16 can run in parallel with RSP-17 (after RSP-12 and RSP-15)
- Wave E, in parallel: RSP-06 (after RSP-01..RSP-04, RSP-16, PROMPT parsers and templates), RSP-11 (after RSP-09 and API's chat-completions chunker)
- Wave F: RSP-07 (after RSP-05, RSP-06, RSP-17, RSP-19)

## Work packages

<a id="rsp-01"></a>
### RSP-01 Responses limits configuration and in-memory ResponseStore

- **Milestone:** M5
- **Rust target:** console-responses::{config, store}
- **Platform:** platform-neutral
- **Risk:** low. Byte thresholds depend on exact Python JSON encoding (float repr, key order, non-ASCII), hence the hard dependency on the shared pyjson encoder. The dead ResponseStore.expand() helper is not ported (see deviations).
- **Depends on:** CORE: shared pyjson encoder (Python json.dumps-compatible) and serde_json preserve_order; LAUNCH: config environment resolver (env block over process env, alias policy)
- **Estimated size:** 550 lines of code; 500 lines of tests
- **New dependencies:** sha2 =0.10.9 (already in root lock; shared)
- **Donor sources:** serve/response_config.py (all 32 lines); serve/response_store.py (all 201 lines; expand() at 182-195 is dead code in serve/); server.py owner derivation _response_owner and lookup used at 6476-6491

**Behaviors to reproduce**

- ResponsesLimits struct with the 18 integer keys and defaults: CACHE_ENTRIES 128, CACHE_BYTES 67108864, CACHE_TTL_S 3600, ENTRY_BYTES 67108864, OWNER_ENTRIES 0, OWNER_BYTES 0, ASSEMBLY_BYTES 67108864, JOB_WORKERS 2, JOB_ENTRIES 16, JOB_OWNER_ENTRIES 4, JOB_TIMEOUT_S 300, JOB_TTL_S 900, JOB_INPUT_BYTES 2097152, EVENT_BYTES 2097152, EVENT_COUNT 4096, STREAM_READERS 32, STREAM_OWNER_READERS 8, STREAM_TIMEOUT_S 5.
- Read from the environment at service creation through the shared config-environment resolver: run-config env block over process environment, canonical prefix over legacy aliases (alias policy per deviation list). Non-integers are an error. Values must be > 0 except OWNER_ENTRIES and OWNER_BYTES, where 0 disables the quota. JOB_WORKERS <= 32, JOB_ENTRIES <= 4096, EVENT_BYTES >= 4096. A violation aborts startup with a message naming the variable.
- Store key (owner, response_id). owner is 'public' with no API key configured, otherwise the lowercase hex SHA-256 of the presented key. Another owner's id is indistinguishable from a missing one (NotFound -> 404).
- Items are encoded as canonical JSON: sort_keys, separators (',', ':'), ensure_ascii false, NaN/Infinity rejected, UTF-8, byte-identical to Python json.dumps through the shared pyjson encoder. Each item is stored once per owner under its SHA-256 with a reference count. A snapshot is the metadata bytes (the response without output) plus two flat vectors of block refs, input and output. Deleting an ancestor never breaks a descendant.
- put() plans every eviction before mutating anything. LRU order, owner quotas evict only that owner's entries, and re-putting an id replaces it. An impossible write fails with exactly 'stored response exceeds the in-memory Responses cache capacity; use store=false' and leaves existing snapshots intact.
- The TTL is fixed at write time; get() moves the entry to most-recently-used without extending its deadline. Expired entries are dropped on every put/get/delete/stats.
- get() has an admission budget (ASSEMBLY_BYTES) for concurrent snapshot assembly. Over budget raises StoreBusy (HTTP 503). JSON decoding happens outside the lock and returns fresh copies.
- stats() keys: hits, misses, writes, expired, evicted, deleted, rejected, assembly_rejected, write_seconds, read_seconds, lock_wait_seconds, lock_hold_seconds, entries, blocks, bytes, inflight_bytes, peak_inflight_bytes, max_entries, max_bytes, ttl_s. Values are aggregate only, with no owner or content.
- Injectable clock for TTL tests; thread-safe under concurrent put/get/delete (std Mutex, short critical sections).

**Parity tests**

test_response_store.py, all 8 methods (SharedHistory: shared blocks survive ancestor deletion, owner quotas, failed planning evicts nothing, TTL not refreshed, concurrent readers, assembly limit plus configuration, two env-alias precedence tests), re-expressed as Rust unit tests. Assertions on private fields (store._bytes, max_bytes=180) are recomputed from the pyjson byte lengths of the same fixtures. Also test_responses.py StoreBounds: test_byte_limit_eviction_and_copy_isolation and test_concurrent_put_get_delete_and_expiry_do_not_corrupt_accounting (2 methods), as unit tests.

**Definition of done**

All 10 re-expressed tests pass under cargo test --locked in the console workspace. A table-driven test proves each of the 18 limits' default, bounds and error. A reviewer can check that canonical-encoding byte counts for the fixture items equal the Python-documented values listed in the test comments. clippy -D warnings is clean. The contract section 'Responses limits' is written in specs/022-*/contracts/responses.md.

<a id="rsp-02"></a>
### RSP-02 Structured output: restricted JSON Schema validator and validate-before-publish buffer

- **Milestone:** M5
- **Rust target:** console-responses::schema (pure module: no tokio and no I/O, so it can later build for wasm32)
- **Platform:** platform-neutral
- **Risk:** medium. Main risk is subtle divergence from python-jsonschema: first-error order, multipleOf float rounding, equality rules. The agent must read the python-jsonschema 4.18+ semantics from its documentation, since only Maya's source is available locally. Unknown edge cases are labelled in the contract. Rejected alternative: the jsonschema crate, which brings about 30 transitive packages (fancy-regex, url, reqwest optional, ahash), cannot express the cooperative one-second budget, and its error ordering and paths differ anyway.
- **Depends on:** CORE: generation stream item type (Ping | Event{kind, text, call{name, arguments, id}, complete, logprobs} | Done{finish, completion_tokens, reasoning_tokens, reused, ...}) and a cancellation token type; CORE: pyjson encoder
- **Estimated size:** 850 lines of code; 750 lines of tests
- **Donor sources:** serve/response_schema.py (all 204 lines); server.py 3500-3501 (/v1/status structured_outputs block); frontend.py 599-609 (Chat Completions reuses json_instruction without validation; owned by API, but the instruction text comes from here)

**Behaviors to reproduce**

- ResponseValidation::from_request(text, tools): text accepts only 'format' ('text accepts only format'). format.type is text | json_object | json_schema. text and json_object accept only the type key. json_schema needs a nonempty name and a schema, with an optional boolean strict. The other error strings are copied verbatim from the source.
- compile(schema, strict): the root must be an object with type 'object'. Allowed keywords are exactly type, properties, required, additionalProperties (boolean only), items, enum, const, anyOf, minItems, maxItems, minLength, maxLength, minimum, maximum, exclusiveMinimum, exclusiveMaximum, multipleOf, description, title. An unknown keyword gives 'unsupported schema keywords: a, b' (sorted). Limits are 512 nodes and depth 24, and every node must be an object. In strict mode, every node with type object or with properties needs additionalProperties false and required equal to the set of properties. The schema's pyjson encoding (default separators, ensure_ascii true) must be at most 65536 bytes. All failures map to HTTP 400 before generation.
- In-house meta-schema check equivalent to Draft202012Validator.check_schema restricted to the subset. type is a valid type name or an array of unique ones. required is an array of unique strings. min*/max* lengths are non-negative integers, where integer-valued floats such as 1.0 count. minimum/maximum/exclusive* are numbers. multipleOf is a number > 0. enum is an array. anyOf is a nonempty array. Messages are prefixed 'invalid JSON Schema: '.
- Instance validation copies python-jsonschema semantics. integer accepts ints and integral floats such as 3.0. Booleans are never numbers or integers. number covers int and float. enum and const use jsonschema's equal(): 1 == 1.0, but True != 1, with deep sequence and mapping equality. minLength/maxLength count Unicode code points. multipleOf follows jsonschema's algorithm: for a float divisor, a quotient check int(q) != q; for an int divisor, the remainder. Keywords are visited in the schema object's key order, properties in schema order and required in list order, so the first error matches. The error path is rendered as a Python list repr, as in 'text failed schema validation at ['a', 0]'.
- Instance limits: 65,536 nodes and depth 32. NaN and Infinity are rejected (numbers parsed from text such as 'NaN' must fail). A cooperative deadline (VALIDATION_SECONDS = 1, injectable for tests, 0 forces failure) and a cancel check run before every keyword application, with messages 'schema validation exceeded its one-second budget' and 'generation was cancelled'.
- Top-level function tools with strict true have their parameters compiled in strict mode and their arguments validated. strict omitted or false enforces nothing. Functions nested in namespace tools are never compiled (Maya behaviour, kept).
- prompt(): None for text. For json_object: 'Return only a valid JSON object, with no Markdown or surrounding text.'. For json_schema: 'Return only a JSON object matching this JSON Schema, with no Markdown or surrounding text:' + newline + pyjson.dumps(schema) with default separators. with_system_note appends '\n\n' + note to the leading system message (string content, or an extra text part when the content is a list) or inserts a new first system message.
- Buffering wrapper over the generation stream: active when format != text or any strict tool exists. Ping events pass through. Event payloads are held with a budget of utf8_len(text) + 256 per event, 4 MiB total (injectable). Over budget gives 'structured output buffer exceeds 4 MiB'. Finish 'length' or 'cancel' passes done through with nothing published. At finish 'stop', in order: every tool call must be complete; strict tool arguments are validated; content (joined content events) must parse as a JSON object and satisfy the schema, a check skipped only when there are calls and no content; then deadline and cancel are rechecked. Only then are the held events released followed by done. Any failure raises OutputValidationError(message, done), which keeps usage. Code-fenced JSON fails; there is no retry and no repair.
- Capability block for /v1/status: {mode:'validate-before-publish', schema_draft:'2020-12', constrained_decoding:false}.

**Parity tests**

test_responses_schema.py, all 10 methods. Eight (success, invalid output never leaks across 8 bad outputs, json_object plus output budget, instructions stay the system message, strict function arguments, schema subset rejections, nested nullable array boundaries, buffer and deadline limits) become HTTP-level tests in RSP-06. Their validator-level cores are also unit tests here. test_plain_chat_does_not_require_jsonschema_import is replaced by a test that structured output works with no optional component (see deviations). test_official_sdk_parses_structured_output becomes a structural assertion (SDK not used). Plus about 40 new table-driven unit tests pinning python-jsonschema edge semantics: integral floats, bool versus int, enum equality, multipleOf on floats, first-error order, path repr.

**Definition of done**

A unit-test suite covers every allowed keyword for valid and invalid cases, every compile error, the strict-mode rule, node/depth/byte limits, the deadline at 0 seconds and cancellation. The buffer wrapper is proven by a scripted event-stream test to release nothing on failure and to keep done/usage. The module has no tokio, std::process or filesystem use (checked by a reviewer grep), and cargo check --target wasm32-unknown-unknown is documented as expected to pass. The structured-output section of contracts/responses.md is written.

<a id="rsp-03"></a>
### RSP-03 Responses request normalizer, input items, tools and sealed reasoning

- **Milestone:** M5
- **Rust target:** console-responses::request
- **Platform:** platform-neutral
- **Risk:** medium. Python type-strictness traps. serde_json's Number keeps the int/float distinction by literal, which is needed; integers beyond i64/u64 differ unless arbitrary_precision is adopted workspace-wide. Error substrings are asserted by tests and must be copied.
- **Depends on:** PROMPT: the internal message/tool model consumed by openai_to_messages (the Responses path never passes the deepseek flag; glm_dsa only) and the names of the force-tool/prefill hints; RSP-02
- **Estimated size:** 800 lines of code; 650 lines of tests
- **New dependencies:** base64 =0.22.1 (in root lock; shared)
- **Donor sources:** serve/responses.py lines 1-352 (_string, _arguments, SEP, SEALED, seal/unseal, flat_tools, namespaced, _content, input_items, input_page, normalize_request including the assistant_turn/flush grouping logic); docs/RESPONSES.md for wording only (code and tests win where they disagree)

**Behaviors to reproduce**

- Allow-list of exactly 23 top-level keys: model, input, instructions, tools, tool_choice, parallel_tool_calls, reasoning, max_output_tokens, temperature, top_p, stream, store, metadata, previous_response_id, background, text, truncation, include, service_tier, prompt_cache_key, client_metadata, top_logprobs, ablate. Any other key gives 400 'unsupported Responses parameter: K' (copy the exact text from the source).
- Field validation with Python type strictness. A bool is never an int, and type(x) is int rejects 5.0. background requires store exactly true ('background=true requires explicit store=true'). truncation only 'disabled'. service_tier only 'auto'. include only reasoning.encrypted_content and/or message.output_text.logprobs. reasoning only {effort, summary in null|auto|concise|detailed}. metadata at most 16 string pairs, key <= 64 and value <= 512 code points. max_output_tokens is an int >= 1. top_logprobs is an int 0..20. prompt_cache_key is a string <= 256. client_metadata is a string-to-string object. model is a nonempty string.
- Input: a string becomes one user message. An array must be nonempty, and item.type defaults to 'message'. message roles are user|assistant|system|developer. content is a string or parts of input_text|output_text, with input_image ({image_url nonempty string, detail accepted and ignored}) only in user messages and function_call_output. reasoning items take reasoning_text/summary_text parts. When both are empty and encrypted_content is present, the blob is decoded only if it carries the accepted seal prefix, with strict base64; otherwise the item is dropped and the turn is kept. function_call has a unique call_id, name, optional namespace and arguments (a string holding a JSON object; '' means {}; non-finite numbers are rejected). function_call_output has the call_id of a pending call, and output is a string or a parts array. item_reference and all other types give 400.
- Grouping: consecutive assistant-side items (assistant message, reasoning, function_call) merge into one assistant turn. Duplicate call ids, unmatched outputs, missing outputs, or an assistant item arriving while a result group is partial give 400. A complete result group is reordered into its calls' order.
- Tools: function tools allow only type, name, description, parameters, strict (unique name, boolean strict, object parameters). namespace tools {type:'namespace', name without '::', description?, tools:[function]} are flattened to 'ns::name' with the namespace description prefixed. Every other tool type (web_search, local_shell, ...) is left out of the prompt but echoed unchanged in response.tools.
- tool_choice: auto | none | required (needs tools) | {type:'function', name[, namespace]} naming a declared function. Mapped to the prompt layer's force-tool and prefill hints.
- Output: the internal Chat-style sampling request (messages, tools, max_completion_tokens, temperature, top_p, reasoning effort -> thinking, parallel_tool_calls, top_logprobs/logprobs include, ablate, _responses:true marker) plus the compiled ResponseValidation from RSP-02. The input request is never mutated.
- input_items(history) normalizes stored items: type defaults to message and status to completed, string content becomes [{type input_text|output_text, text}], output_text parts get annotations:[], a missing id becomes 'item_' + 24 hex, and duplicate ids give 400.
- input_page(items, query): only order=asc|desc (default desc), limit 1..100 (default 20) and after=<item id>, each at most once, otherwise 400. Returns {object:'list', data, has_more, first_id, last_id}.
- seal(text) = SEAL_PREFIX + standard base64(utf-8 text); unseal accepts the prefixes allowed by the deviation decision.

**Parity tests**

test_responses.py: test_invalid_and_unsupported_requests_fail_before_generation (28 rejected shapes), HistoryValidation (2), test_duplicate_and_mismatched_call_results, test_request_is_not_mutated and the input_page half of test_input_item_pagination_and_invalid_options. They are re-expressed as normalizer unit tests here and again at HTTP level in RSP-06. test_responses_tools.py: the request-shape halves of test_codex_built_in_tools_are_left_out, test_codex_namespace_tools_round_trip, test_codex_encrypted_reasoning_round_trip, test_codex_hints_and_reasoning_disabled_projection and test_the_rejection_names_the_include.

**Definition of done**

All 28 rejected shapes, each with its asserted message substring, pass as unit tests. The grouping/reordering rules are covered by tests for each 400 condition. A seal/unseal round trip and a foreign-blob drop are tested. A reviewer can diff the allow-list and every error string against responses.py.

<a id="rsp-04"></a>
### RSP-04 Responses event serializer and response object

- **Milestone:** M5
- **Rust target:** console-responses::events
- **Platform:** platform-neutral
- **Risk:** medium. Snapshot key order and the item.added-before-content-part detail are asserted. A reviewer should compare event sequences to fixtures written from responses.py by hand. Tool-parser behaviour lives in PROMPT, so any failure must be attributed correctly.
- **Depends on:** RSP-02; RSP-03; CORE: generation stream and Done record (finish, completion_tokens, reasoning_tokens, reused), cancellation token; PROMPT: strict tool parsing for _responses requests and stop-at-first-complete-call when parallel_tool_calls is false (parser behaviour exercised through this package's tests)
- **Estimated size:** 700 lines of code; 600 lines of tests
- **Donor sources:** serve/responses.py lines 353-545 (new_response, response_usage, response_events with check_call/event/start/close, response_collect)

**Behaviors to reproduce**

- new_response(model, req, id, status): id 'resp_' + 24 hex. object 'response'. created_at in integer seconds. status queued|in_progress|completed|incomplete|failed|cancelled. error null or {code:'server_error', message}. incomplete_details null or {reason:'max_output_tokens'}. model echoes the server's loaded model. instructions and max_output_tokens. tools echoed unchanged. tool_choice default 'auto'. parallel_tool_calls default true. reasoning {effort:null, summary:null, ...request}. text default {format:{type:'text'}}. temperature/top_p carry the effective values after server defaults. metadata default {}. store default false. background default false. previous_response_id. truncation 'disabled'. usage. completed_at. prompt_cache_key and top_logprobs only when sent; client_metadata is never echoed. Key order follows Python insertion order.
- State machine over the (validation-wrapped) generation stream. One open item at a time: reasoning rs_, message msg_, function_call fc_, ids prefix + 24 hex. A change of kind closes the open item. response.created then response.in_progress. output_item.added is emitted before the content part exists (empty snapshot), then content_part.added for messages. Deltas are output_text.delta {item_id, output_index, content_index, delta, logprobs:[]}, reasoning_text.delta and function_call_arguments.delta. Closing: output_text.done + content_part.done; reasoning_text.done; function_call_arguments.done {arguments} only for completed calls; output_item.done. Every event carries a deep-copied snapshot and a sequence_number from 0. There is exactly one terminal event: response.completed | response.incomplete | response.failed.
- Function call arguments are serialized with pyjson default separators and ensure_ascii false. A truncated call is closed with status incomplete and never emits arguments.done.
- Generation-time tool checks: a call under tool_choice none, an undeclared name, a wrong forced name, a second call under parallel_tool_calls false, a missing required call, or an unfinished call at end of turn each fail the response (exact messages from the source).
- finish 'length' -> status incomplete with incomplete_details {reason:'max_output_tokens'}. Any error or OutputValidationError -> status failed, store false, error {code:'server_error', message}, output [] after validation failure, usage retained.
- Usage {input_tokens = prompt length, output_tokens, total_tokens, input_tokens_details {cached_tokens = engine prefix reuse, cache_write_tokens 0}, output_tokens_details {reasoning_tokens}}.
- include reasoning.encrypted_content adds the sealed blob to reasoning items. summary is always [].
- persist hook: when store is true, {response, input history} is saved before the terminal event. A failed save converts the response to failed (message from the store).
- response_collect(events) -> the final response object for non-stream use. Events are produced as an iterator/stream of (name, payload) or KeepAlive so that the first item can be pulled before HTTP headers are sent.

**Parity tests**

test_responses.py: test_stream_lifecycle_and_snapshots, test_reasoning_and_output_can_be_replayed, test_function_call_round_trip_whole_and_streamed, test_multiple_tool_results_follow_call_ids, test_output_budget_and_context_errors, test_engine_failure_has_a_terminal_error (6). test_responses_tools.py ToolContracts serializer-level checks (about 12 of 15). These are re-expressed as serializer unit tests over scripted event streams here, and as HTTP tests in RSP-06.

**Definition of done**

Scripted-stream unit tests reproduce, for text, reasoning plus text, single/multiple/truncated/malformed tool calls, length cut, engine error and validation failure, the exact event-name sequence, sequence numbers, terminal uniqueness and snapshot shapes. Golden JSON fixtures live under console/crates/console-responses/tests/data/ (never a directory named fixtures/ at root, models/ or logs/).

<a id="rsp-05"></a>
### RSP-05 Background job manager with bounded event history and replay

- **Milestone:** M5
- **Rust target:** console-responses::jobs (tokio)
- **Platform:** platform-neutral
- **Risk:** high. Concurrency is the hardest part of the subsystem: exactly one terminal state, cancel must not report cancelled while the worker still owns the engine, and timing-based tests must be deterministic. Use tokio::time::pause for deadline tests where possible. Repeat the race tests at least 100 times in CI-safe loops.
- **Depends on:** RSP-01; CORE: cancellation token, engine FIFO semantics (a job waiting for the engine can be cancelled without waiting for the holder)
- **Estimated size:** 800 lines of code; 700 lines of tests
- **New dependencies:** tokio-util =0.7.19 (in root lock; CancellationToken), unless CORE provides its own token type
- **Donor sources:** serve/response_jobs.py (all 273 lines)

**Behaviors to reproduce**

- submit(owner, initial, inputs, work): 413 if pyjson(ensure_ascii false) of {response, input} exceeds JOB_INPUT_BYTES. 503 after close. 429 when active jobs reach JOB_ENTRIES or the owner's active jobs reach JOB_OWNER_ENTRIES. Finished records are evicted to admit new ones. response.queued becomes event 0. JOB_WORKERS workers start lazily on the first submit (tokio tasks bounded by a semaphore). JobError carries the HTTP status and message.
- Lifecycle queued -> in_progress -> exactly one of completed | incomplete | failed | cancelled. A single JOB_TIMEOUT_S deadline is counted from submission, queue time included. Queued jobs past it fail on the next sweep without starting. Running jobs have their cancel token fired by a timer. Finishing past the deadline counts as failed even if generation completed ('background task exceeded its deadline').
- The worker renumbers events into a per-job ring bounded by EVENT_COUNT and EVENT_BYTES, measured as pyjson ensure_ascii-false bytes, oldest dropped. A single event larger than EVENT_BYTES fails the job. Events carrying a response update the job snapshot and keep the original created_at.
- On completed/incomplete the snapshot is written to the ResponseStore. A store capacity error or an oversized terminal event converts the result to failed with output cleared.
- cancel(owner, id, wait=5 s) is idempotent. Queued jobs finish at once as cancelled and never start. Running jobs are signalled and the caller waits up to 5 s for the worker to release the engine; otherwise the still in_progress snapshot is returned. Cancelled snapshots have store true. The stream ends with an 'error' event {type:'error', code:'response_cancelled', param:null, message}; response.cancelled is never emitted.
- events(owner, id, after): yields events with sequence_number > after, a keep-alive after each idle second, and ends after the terminal event. A cursor lost mid-stream ends with 'error' code 'event_history_unavailable'. check_cursor gives 410 when the cursor fell out of the ring and 400 when it is beyond the latest event.
- reader(): admission is limited to STREAM_READERS overall and STREAM_OWNER_READERS per owner (429), and the slot is released on drop. A reader disconnect never cancels the job.
- delete(): 409 'cancel the running response before deleting it' while active. Finished records are swept JOB_TTL_S after they end. close() stops admission, cancels everything, joins workers for up to 5 s and reports an error if one is still alive.
- stats(): submitted plus per-status counters, records, running, queued, readers, event_bytes.
- The single-terminal-state race between completion, cancel and deadline is resolved under one lock: whichever transition commits first wins, and the others become no-ops.
- Preparation (including image encoding) and generation run inside the same job task, so per-request embeddings or picture files are owned by that task.

**Parity tests**

test_response_jobs.py: manager-level halves of the 21 methods are re-expressed as unit tests with scripted work closures (completion replay, disconnect does not cancel, running cancel drains and is idempotent, queued cancel never starts, expired queued job never starts, single terminal state repeated 8 times, admission and input limits, deadline plus shutdown join, cursor retention plus event byte limits, reader admission bounded and released, metrics aggregate). The HTTP halves are in RSP-07.

**Definition of done**

All manager-level tests pass, including a 200-iteration stress of the completion/cancel/deadline race. The reviewer verifies no path emits two terminal events and that a 5 s cancel wait returns in_progress when the scripted worker holds the engine. Stats keys match the contract list.

<a id="rsp-06"></a>
### RSP-06 Responses HTTP routes (foreground, store, retrieve, input_items, delete) and status/metrics hooks

- **Milestone:** M5
- **Rust target:** console-responses::routes (handlers against console-http's handler API; mounted by pulsar-console)
- **Platform:** platform-neutral
- **Risk:** medium. Heavy reliance on other subsystems' prompt layer and fake engine. Schedule after PROMPT's parser and template packages and CORE's fake engine. test_responses_capabilities_keep_maya_ds4_diagnostics asserts service 'maya' and memory_note text owned by other subsystems; only its responses-block assertions belong here.
- **Depends on:** RSP-01; RSP-02; RSP-03; RSP-04; HTTP: router, auth, CORS incl. OPTIONS, 503 reload/update gate with Retry-After 30, error envelope helpers, SSE writer, disconnect-to-cancel, pull-first-event-before-headers support; CORE: Service prepare/run, check_request, with_shared, sampling defaults, scripted fake engine (RecordingEngine equivalent recording last prompt, sampling, max_new, cancel, embeddings bytes), ByteTokenizer with specials; PROMPT: openai_to_messages, GLM-style <tool_call>/<arg_key> parser with strict mode, DSML (DeepSeek) parser, a repo-owned ChatML-style test template producing '<|im_start|>user\nhi'; RSP-16 (file parts expanded before dispatch), RSP-17 (no-vision 400 and image path) for the image test
- **Estimated size:** 650 lines of code; 1300 lines of tests
- **Donor sources:** server.py: do_POST dispatch 6160-6297 (reload/update 503 gate, attach.expand_request before dialects, exception mapping BadBody/JobError/StoreBusy/ValueError/EngineDied/malformed), _responses 6476-6524, _response_work 6526-6564, GET/DELETE handlers and _response_lookup/_response_owner in the 5821-5921 region, /v1/status responses block around 3500, metrics/prometheus exporters for maya:responses_*

**Behaviors to reproduce**

- POST /v1/responses: previous_response_id must be a nonempty string. The lookup consults live background records first, then the cache. Unknown or another owner's id gives 404 'previous_response_id: stored response not found'. A status other than completed/incomplete gives 409 'previous response is not a completed or incomplete generation'. On success the input becomes stored input + stored output + new input; instructions and sampling are not inherited.
- Normalize (RSP-03), drop the validation into RSP-04, then apply with_shared defaults, _api openai, _responses true and check_request. Prepare messages via openai_to_messages(glm_dsa only) and apply with_system_note when the format requires JSON. Prepare the prompt with the cancel token, run, then serialize.
- Non-stream: 200 with the response object, or HTTP 500 with the same object when status is failed. Stream: the first event is pulled before SSE headers, so preflight errors (validation, context overflow with code context_length_exceeded, no vision) are plain 400 envelopes even with stream true. SSE framing: 'event: <type>\ndata: <json ensure_ascii false>\n\n'. Keep-alive is ': keep-alive\n\n'. There is no [DONE].
- A foreground client disconnect fires the cancel token and generation stops; the next request works. Per-request embeddings or picture files are deleted in all paths, including a disconnect before the generator starts.
- GET /v1/responses/{id}: background record first, then cache. 200 snapshot. The query must be empty or exactly stream=true with optional starting_after=<non-negative int>, each once, else 400 'retrieve accepts stream=true and optional starting_after'. stream=true on a cache-only snapshot gives 409 'background event history is no longer retained' (the stream itself is in RSP-07). Missing gives 404 {error:{type:'invalid_request_error', message:'stored response not found'}}. Assembly pressure gives 503. Paths with more than two segments or an unknown second segment give 404 {error:{message:'not found'}}.
- GET /v1/responses/{id}/input_items: input_page over the full history excluding the response's own output; query errors are 400.
- DELETE /v1/responses/{id}: no query (400 otherwise). 200 {id, object:'response.deleted', deleted:true}. 404 when neither record exists. 409 while a background job is active. OPTIONS preflight answers 204 with Access-Control-Allow-Methods 'GET, POST, DELETE, OPTIONS' for allowed origins, else 403.
- Owner derivation: SHA-256 hex of the key from 'Authorization: Bearer' or x-api-key (both forms share state), or 'public' when no key is configured.
- Error mapping: JobError/StoreBusy -> {error:{type:'server_error', message}} with their status. OSError during preparation -> 500 server_error 'could not prepare the response'.
- Contribute to GET /v1/status: dialects list including '/v1/responses' and responses {cache: store.stats(), jobs: jobs.stats(), structured_outputs}. Contribute to GET /metrics/prometheus one metric per stats key, named <prefix>responses_cache_<key> and <prefix>responses_jobs_<key>, with gauges entries, blocks, bytes, inflight_bytes, peak_inflight_bytes, max_entries, max_bytes, ttl_s, records, running, queued, event_bytes, readers and counters otherwise.

**Parity tests**

HTTP-level ports, driven by the fake engine, of: test_responses.py Responses class (all 21 except the 2 optional-SDK tests, which become structural assertions on the same event streams); test_responses_tools.py (15 ToolContracts plus 5 DeepSeekToolContracts, the latter needing PROMPT's DSML parser and an in-repo DSML test template); test_responses_schema.py (10). About 54 methods in total, all in console-responses/tests/http_*.rs.

**Definition of done**

All ported HTTP tests pass against pulsar-console's in-process server with the fake engine. A reviewer can map each Maya test method to a Rust test, named in a parity table at specs/022-*/parity/responses.md. /v1/status and /metrics/prometheus contain the responses blocks.

<a id="rsp-07"></a>
### RSP-07 Background Responses over HTTP: queued create, replay streams, cancel, and resource ownership

- **Milestone:** M5
- **Rust target:** console-responses::routes::background
- **Platform:** platform-neutral
- **Risk:** high. Cross-cutting with the engine FIFO and idle-unload logic owned by CORE. Timing-sensitive tests need deterministic hooks: a test-only FIFO handle that can be acquired from the test, mirroring svc.fifo.acquire().
- **Depends on:** RSP-05; RSP-06; RSP-17 (image path inside background jobs); CORE: engine FIFO with waiting()/cancel-while-waiting, idle unload and restart (LifecycleEngine equivalent in the fake engine)
- **Estimated size:** 450 lines of code; 950 lines of tests
- **Donor sources:** server.py: _responses background branch 6497-6505, _background_stream, _response_cancel (POST /v1/responses/{id}/cancel), GET ?stream=true&starting_after, STREAM_TIMEOUT_S socket write timeout; response_jobs.py integration with the store

**Behaviors to reproduce**

- background:true returns 200 at once with status 'queued' and the id the final response keeps. With stream:true the connection instead attaches to the job replay from sequence 0, which starts with response.queued and is renumbered.
- Admission errors are {error:{type:'server_error', message}}: 413 input snapshot too large, 429 queue or per-key capacity, 503 manager stopping.
- GET /v1/responses/{id}?stream=true[&starting_after=N]: retained events after N are replayed, then followed live, with ': keep-alive' after each idle second. 410 when the cursor is older than the ring, 400 when it is beyond the latest event, 429 when reader slots are exhausted. Each socket write times out after STREAM_TIMEOUT_S, which drops that reader only.
- POST /v1/responses/{id}/cancel: no query string, body ignored. 200 with the current snapshot: cancelled immediately for queued jobs, or after up to 5 s for running ones, otherwise in_progress. Idempotent. A cache-only snapshot gives 200 if it was a background response, else 400 'only background responses can be cancelled'. Unknown id gives 404 {error:{message:'background response not found'}}.
- Completed and incomplete background results are written to the cache and usable as previous_response_id. Queued, running, cancelled or failed ones answer 409 there.
- Background preparation, image encoding and generation hold the engine FIFO turn exactly as foreground. Cancelling a job that waits for the engine releases its FIFO place, does not restart an idle-unloaded engine and writes no prompt.
- Schema validation applies to background jobs. A cancel during buffered validation never publishes content.
- Delete and cache eviction never drop an active job. Auth scoping matches the foreground routes.

**Parity tests**

test_response_jobs.py, all 21 methods at HTTP level, except test_sdk_background_retrieve_stream_cancel_and_delete, which becomes a structural assertion. The image-related methods (test_background_image_preparation_and_generation_share_resource_ownership, test_ds4_images_reach_foreground_and_background_engines_and_are_cleaned, test_ds4_cancel_during_picture_preparation_stops_before_writing, test_cancelling_a_waiting_image_request_keeps_the_engine_unloaded, test_foreground_and_background_responses_resume_after_idle_unload) use RSP-17 and RSP-19 fakes. test_responses.py test_storage_limits_expiry_and_stream_commit and test_stored_history_is_isolated_by_api_key are also included.

**Definition of done**

All 23 ported methods pass. Stress loops of create, cancel and retrieve-stream show no leaked reader slots, FIFO places or temp files (asserted by stats, FIFO waiting() == 0 and directory listings). The parity table is updated.

<a id="rsp-08"></a>
### RSP-08 MCP JSON-RPC framing and the fake MCP server binary (stdio and Streamable HTTP)

- **Milestone:** M6
- **Rust target:** console-mcp::jsonrpc (message types, line framing, batch arrays) and console-mcp bin target fake-mcp-server (test support; test = false)
- **Platform:** platform-neutral
- **Risk:** low. It must misbehave exactly as the Python double does (die mid-call, suppressed cancelled answers). That is why an SDK-built server is not used.
- **Depends on:** HTTP: hyper server feature available in the workspace (reused for the fake HTTP mode)
- **Estimated size:** 550 lines of code; 200 lines of tests
- **Donor sources:** serve/mcp_fake_server.py (all 172 lines); JSON-RPC message handling shared with serve/mcp.py _dispatch 155-171

**Behaviors to reproduce**

- JSON-RPC 2.0 types: request (integer ids from 1 on the client side), response (result | error {code, message}), notification. A line holding a JSON array is a batch. Non-JSON stdout lines are treated as log text by the client.
- fake-mcp-server [--page N] [--crash-at-start] [--http PORT]. Six tools: echo{text} returns the text; fail{} gives an isError result 'it failed on purpose'; sleep{seconds} answers after the delay; big{n} returns n characters of 'y'; die{} writes 'dying on purpose' to stderr and exits with code 3 mid-call; add{a,b} returns the integer sum.
- tools/list pages two tools at a time (--page N); the cursor is the stringified start index.
- stdio mode: UTF-8 JSON-RPC lines. tools/call runs concurrently so a slow call does not block cancellation. Answers to cancelled ids are suppressed.
- --http PORT: Streamable HTTP on 127.0.0.1:PORT/mcp, printing 'listening on http://127.0.0.1:<port>/mcp'. initialize returns the Mcp-Session-Id 's-N'. Later requests without a known session get 400. Notifications get 202. tools/call answers as an event stream with a notifications/progress event before the result. DELETE drops the session.
- --crash-at-start writes 'cannot start: missing configuration' to stderr and exits with code 2.
- FAKE_MCP_LOG=<path> appends one JSON line per call ({call, arguments}) and per cancellation ({cancelled: requestId}). Tests write it to a temp dir with a .jsonl name, never *.log.

**Parity tests**

There are no direct Maya tests; all 24 test_mcp.py methods drive this binary. Add 6 smoke tests: paging, each tool, crash-at-start exit code, die exit code 3, HTTP session and 400 without a session, cancellation log line.

**Definition of done**

The binary builds in the console workspace, the smoke tests pass, and the CLI matches the 'Fake MCP server command line' contract. It is reachable from integration tests through env!("CARGO_BIN_EXE_fake-mcp-server").

<a id="rsp-09"></a>
### RSP-09 MCP client: configuration, stdio transport, server lifecycle and hub

- **Milestone:** M6
- **Rust target:** console-mcp::{config, stdio, server, hub, text}
- **Platform:** platform-neutral
- **Risk:** medium. Process-group kill and restart races. The cancel-reaches-the-server test depends on notifications/cancelled timing. Windows code compiles only on a Windows target and stays unverified. Rejected alternative: the rmcp crate (3.1.0 is in the root lock). It is an SDK abstraction over these exact wire details, so error texts, the restart policy, the 40-line stderr tail, batch handling and the -32601 fallback would have to be bent around it. It would also pull reqwest, tower, process-wrap, sse-stream and rmcp-macros into a workspace that aims for few dependencies.
- **Depends on:** RSP-08; LAUNCH: run-config loading and the --mcp-config flag plumbing; CORE: cancellation token type
- **Estimated size:** 1100 lines of code; 600 lines of tests
- **New dependencies:** libc =0.2.189 (in root lock; killpg/SIGTERM)
- **Donor sources:** serve/mcp.py lines 1-243 (constants, errors, _Slot/_wait, StdioTransport including the Windows branches), 373-460 (McpServer), 458-591 (result_text, _clean, McpHub), 594-660 (_check_server, servers_from, settings_from, hub_from_config)

**Behaviors to reproduce**

- Config: run-config 'mcp_servers' and 'mcpServers' (both read) plus the --mcp-config file, read as UTF-8 with an optional BOM, holding {mcpServers} or {mcp_servers}; the file wins a name clash. An entry with url is HTTP (optional headers object; 'type':'sse' is refused with the source's message). Otherwise a nonempty string command is required, with optional args (list), env (object) and cwd. 'disabled': true skips the entry. Any invalid entry or unreadable file aborts startup with a product-prefixed message before the model loads. Optional 'mcp' block: timeout_s (> 0, default 60), start_timeout_s (> 0, default 120), max_result_chars (positive int, default 20000), max_rounds (positive int, default 8); unknown keys are logged and ignored. No servers means no hub.
- stdio transport: tokio::process child with piped stdio, environment = server environment + cfg env, optional cwd, its own process group (setsid/process_group(0)). stderr is kept as a 40-line ring. Close sequence: close stdin, wait 2 s, SIGTERM the process group, wait 2 s, SIGKILL. When stdout closes, every pending request fails with 'the server stopped (exit code N): <last stderr line, 300 chars>'. Windows branches (CREATE_NO_WINDOW, taskkill /T /F tree kill, .cmd shim resolution) are ported behind cfg(windows) and labelled unverified.
- Handshake: initialize {protocolVersion '2025-06-18', capabilities {}, clientInfo {product name/title, version '1'}}. The server's protocolVersion is adopted. notifications/initialized. tools/list paged by cursor/nextCursor, at most 100 pages; error -32601 on the first page means a server without tools. Tools without a name are dropped.
- Server-to-client requests: ping -> {}; anything else -> error -32601 'method not supported: <method>'. Notifications are ignored. No sampling, roots or elicitation.
- Requests wait for the response, the deadline (timeout_s for calls, start_timeout_s for start) or the chat's cancel token. On timeout or cancel the pending slot is dropped and notifications/cancelled {requestId, reason} is sent. Only cancellation surfaces as Cancelled; everything else becomes McpError text.
- Server status machine: idle -> starting -> ready | failed; ready -> stopped when it ends. Each server starts on its own task (non-blocking start). hub.wait(timeout) waits for servers still starting. A server that stopped after being ready keeps its tools listed and is restarted by its next call. A server that failed to start is retried at most every 10 s ('the server is not running (...)'); a failed restart gives 'the server could not be started again: ...'.
- Names: clean(server) + '__' + clean(tool), where clean maps characters outside A-Za-z0-9_- to '_' (empty becomes 'x'). Cut to 64 characters; on collision cut to 60 and append '_2', '_3', .... Only ready/stopped servers route. template_tools(exclude) gives {name, description (description, else title, else ''), parameters (inputSchema if an object, else {type:'object', properties:{}})}. A request's own tool of the same name wins.
- call(name, args, cancel) -> {ok, text, chars, truncated, ms, server, tool}. isError results are prefixed 'error: ' ('error: the tool reported an error' when empty). Transport/protocol errors become 'error: <message>'. An unknown tool gives "error: there is no tool named '<name>'" using the Python str repr quoting rules via a shared py_repr helper. Text longer than max_result_chars (counted in code points) is cut and followed by '\n\n[... truncated: the tool returned N characters; only the first M are shown]' with thousands separators.
- result_text: text blocks verbatim; resource -> its text or '[resource <uri> (<mime>), not shown]'; resource_link -> '[resource link: <name> <uri>]'; image/audio -> '[<kind> (<mime>, <n> bytes): not shown to the model]'; other blocks as JSON; structuredContent JSON when there are no blocks; joined with newlines.
- status(): servers [{name, transport, status, error, info {name?, title?, version?, protocol}, tools [{name, tool, description cut to 300}]}], tools = routed count, settings {timeout_s, max_result_chars, max_rounds}. close() is best effort over all servers.
- Startup log lines (tool counts, failures) go through the console's logging facility in the same wording, with the product prefix.

**Parity tests**

test_mcp.py Client (9: initialize plus paging, namespaced tools, failed servers left out, call, errors become text, timeout, truncation, crash mid-call then restart, cancel reaches the server) and Config (2: both spellings plus file precedence, bad entries stop the start). All are ported as Rust integration tests spawning fake-mcp-server. MCP config fixtures must not be named mcp.json (gitignored); use names such as mcp_servers_case.json.

**Definition of done**

All 11 ported tests pass on macOS. A reviewer can confirm the close sequence timings with a test that measures the process group gone within about 4 s. GET /mcp status shape is snapshot-tested. contracts/mcp.md is written with config, stdio and naming/result-text sections.

<a id="rsp-10"></a>
### RSP-10 MCP Streamable HTTP transport and the MCP listing CLI

- **Milestone:** M6
- **Rust target:** console-mcp::http; pulsar-console subcommand 'mcp list <run-config.json> [<mcp-config.json>]'
- **Platform:** platform-neutral
- **Risk:** medium. The SSE parsing must be tolerant (CRLF, multi-line data). TLS depends on a cross-subsystem decision.
- **Depends on:** RSP-09; MODELS/HTTP: shared outbound HTTP(S) client facade (also needed by the model pull driver and by opt-in remote image fetch); LAUNCH: subcommand plumbing in pulsar-console
- **Estimated size:** 500 lines of code; 350 lines of tests
- **Donor sources:** serve/mcp.py lines 244-371 (HttpTransport: _headers, _post, _from_events, request, _quiet_notify, notify, close) and 662-669 (python -m serve.mcp)

**Behaviors to reproduce**

- Every message is a POST to the configured url with Content-Type application/json, Accept 'application/json, text/event-stream', User-Agent <product>, the configured headers, Mcp-Session-Id once issued (taken from any response header) and MCP-Protocol-Version once negotiated.
- A notification expects no body (202). A request's answer is either a JSON body (an object, or an array in which the element with the matching id and no method is taken) or an event stream in which data: lines are joined until a blank line and parsed until the matching id appears; earlier notifications are skipped. No standing GET stream is opened.
- HTTP errors become 'HTTP <code> <reason>: <first 300 chars>'. A 404 while a session exists marks the transport broken, so the next call re-initializes with a new session. The per-request timeout is the call timeout + 5 s. Notifications use 10 s. close sends DELETE with a 3 s timeout and ignores failures.
- Cancel and timeout send notifications/cancelled as in stdio.
- http:// is served by a hyper 1.x client connection per POST. https:// goes through the shared outbound TLS client; without it there is a clear error at startup (see deviations if TLS is not adopted).
- CLI: builds the hub from the config(s), starts every server and waits, prints status() as indented JSON, closes the servers, and exits with 'no MCP servers configured' when there are none.

**Parity tests**

test_mcp.py HttpClient (2: list and call with session id and event-stream answer; timeout and unreachable) against fake-mcp-server --http. Add 3 tests: 404-with-session re-initialize, DELETE on close, and the CLI output shape.

**Definition of done**

All 5 tests pass. The CLI is documented in contracts/mcp.md. A reviewer confirms that the header set and the timeout arithmetic match the contract.

<a id="rsp-11"></a>
### RSP-11 MCP tool loop, strata_mcp chunk events and the GET /mcp route

- **Milestone:** M6
- **Rust target:** console-mcp::tool_loop (stream adapter over the core generation stream) plus route handlers for GET /mcp
- **Platform:** platform-neutral
- **Risk:** medium. Ordering of start/call/result chunks relative to content chunks is asserted. Disconnect during a tool must propagate cancel to the MCP server.
- **Depends on:** RSP-09; API: chat-completions pipeline accepting an injected run stream that may carry Mcp(Value) items, and rendering them as strata_mcp chunks or a list; CORE: Service.prepare re-entry with the kw flags named above; HTTP: own-page check helper and the /health and /api/tokens composition hooks; WEB: the UI-to-server contract document where the strata_mcp event schema is recorded
- **Estimated size:** 500 lines of code; 700 lines of tests
- **Donor sources:** server.py run_with_mcp 4811-4887; _openai MCP opt-in 6572-6594; chunk rendering of ('mcp', {...}) in openai_chunks/openai_collect (4971-4974 region); GET /mcp handler and /health mcp_tools (6007-6011, 6327-6338); /api/tokens MCP tool counting; serve/web/chats.js 313, 357-369, 432, 483 and serve/web/server.js 115-129 (consumer side, for the contract)

**Behaviors to reproduce**

- Opt-in only on POST /v1/chat/completions (and /api/tokens). The body must carry strata_mcp === true (exact boolean) and a hub must exist. Own-page check: Content-Type application/json else 415 {error:{message:'send application/json'}}; Origin absent or equal to Host else 403. /v1/responses and /v1/messages never get MCP tools.
- hub.wait(10 s), then MCP template tools are appended after the request's own tools (own names win). If no MCP tools remain, the request is a plain chat.
- Loop: run generation. MCP calls are not streamed as tool_calls: tool_start for an MCP name emits {event:'start', id, name}; tool_args for MCP calls are suppressed. When the answer ends with finish 'stop', contains MCP calls and no call to a client-owned tool, and cancel is not set, each call is executed in order on a separate task. Keep-alive pings go out every 1 s, and a disconnect fires cancel, which sends notifications/cancelled. Each execution emits {event:'call', id, name, server, tool, arguments, round} and {event:'result', id, ok, text, chars, truncated, ms}. The assistant turn (content, reasoning_content when present; DeepSeek templates keep unstripped text) and the tool results are appended, then the prompt is prepared again with _force_tool/_prefill/_blocked dropped and _think_* carried. This repeats up to max_rounds; at the cap, {event:'limit', max_rounds} is emitted and pending calls are reported {event:'result', id, ok:false, skipped:true, text:'not run', chars:0, truncated:false, ms:0}.
- A call to a client-owned tool ends the turn as usual (finish tool_calls), and MCP calls in the same answer are reported as skipped. A cancel during a tool ends with finish 'cancel'.
- Usage: completion tokens summed over all rounds; prompt_tokens is the last round's prompt length.
- Chunk rendering: chat.completion.chunk with an empty delta and a strata_mcp object. Non-stream: choices[0].message.strata_mcp is a list. The final finish_reason is 'stop' when the loop ended normally.
- GET /mcp (API key applies): hub.status(), or {servers: [], tools: 0} without a hub. /health gets mcp_tools: bool. /api/tokens counts the MCP tools when strata_mcp is true.
- The dashboard contract (fetch at load, poll every 3 s while any server is 'starting', tolerate absence, tool cards keyed by id) is recorded in the UI-to-server contract document for Phase 2.

**Parity tests**

test_mcp.py ToolLoop (10: tool call then answer, non-stream, plain requests get no MCP tools, own tools still go to the client, tool error is a result, truncated for the model, max rounds, stop during a tool, only from the app's own page, GET /mcp) and NoServers (1), ported as HTTP-level tests with the fake engine and fake-mcp-server.

**Definition of done**

All 11 ported tests pass. The strata_mcp event schema is in the UI-to-server contract, with every field the dashboard reads. A reviewer checks that no MCP code path is reachable from /v1/responses or /v1/messages (grep plus a test).

<a id="rsp-12"></a>
### RSP-12 Attachment readers: text sniffing, ZIP container, Word, Excel, PowerPoint, OpenDocument, EPUB, RTF

- **Milestone:** M6
- **Rust target:** console-attach::{text, zip, ooxml, odf, epub, rtf, detect} (pure library: bytes in, AttachResult out; no tokio)
- **Platform:** platform-neutral
- **Risk:** medium. Several small formats, each with exact-string expectations. The ZIP reader is security-relevant and must enforce caps while inflating. html.unescape edge rules (legacy entities without a semicolon, numeric references in 0x80-0x9F remapped through cp1252, invalid code points to U+FFFD) need a wrapper around html-escape plus a test table. Rejected alternatives: the zip crate (more transitive packages, and caps still need to be enforced by hand), encoding_rs (its WHATWG windows-1252 and macintosh tables differ from Python's codecs), quick-xml (needs a hand-built tree to port ElementTree-walking code).
- **Depends on:** nothing
- **Estimated size:** 1300 lines of code; 750 lines of tests
- **New dependencies:** miniz_oxide (pin an exact version at least two weeks old; pure Rust; shared with RSP-13/RSP-14); roxmltree (pin exact; zero dependencies); html-escape (pin exact; HTML5 named entity table)
- **Donor sources:** serve/attach.py lines 1-503 (limits, Unreadable, as_text, _Zip, _local, _rels, _docx, _xlsx, _pptx, _odf, _Html/html_text, _epub, _rtf, ZIP_KINDS, NOT_READ, _result, extract, _extract)

**Behaviors to reproduce**

- extract(name, data, want_images, text_limit, text_only) returns exactly one of {kind:'text', text, format, truncated[, note][, pages]}, {kind:'images', format, pages, images:[{name, data}][, note]} or {error:{message}}. Unreadable content never panics or propagates.
- Detection by content: a '%PDF-' header (after leading whitespace, or within the first 1024 bytes for a .pdf name) goes to the PDF pipeline (RSP-15, format 'PDF'). ZIP magic picks the kind by member presence, in order: word/document.xml (Word document), xl/workbook.xml (Excel workbook), ppt/presentation.xml (PowerPoint presentation), content.xml plus an oasis mimetype (OpenDocument file), an EPUB mimetype or META-INF/container.xml (EPUB book); any other ZIP gives '<name> is a ZIP archive: attach the files inside it'. '{\rtf' -> RTF document. NOT_READ magics (OLE2, Rar!, 7z, gzip, MZ, ELF, ID3, fLaC, OggS, GGUF) give their 'is X: Y' messages. ftyp/EBML/RIFF give picture, video or audio messages (WEBP is a picture), with text_only wording variants. Everything else goes to text sniffing.
- as_text: '' for empty input. UTF-8 BOM stripped. A UTF-16 BOM decodes strictly. NULs in the first 64 KiB with more than 90% zero bytes at alternating positions -> UTF-16 LE/BE (even length). UTF-8 decode, tolerating a cut multi-byte character in the last 3 bytes. Otherwise cp1252 with replacement when control bytes (< 32 except 9, 10, 12, 13, plus 0x7F) are at most 0.2% of the head. Anything else gives the 'not a kind of file ... reads' error listing READS. cp1252 uses a hand table matching Python's codec: the five undefined bytes become U+FFFD.
- In-house ZIP reader over miniz_oxide: central directory with ZIP64, stored and deflate members, CRC-32 check, encrypted flag -> 'the document is encrypted (password-protected): save an unprotected copy and attach that'. Caps: MEMBER_MAX 64 MiB per member and TOTAL_MAX 256 MiB cumulative, enforced while inflating (an inflate bomb stops at cap + 1 bytes). Damaged archive -> 'the file is a damaged ZIP container (...)'.
- XML through roxmltree (no external entities; internal DTD entities bounded). Invalid XML -> '<member> inside the document is not valid XML (...)'. Elements are matched by local name.
- DOCX: paragraphs (text runs, tabs, breaks; deleted text w:del skipped), tables as 'a | b' rows. XLSX: per sheet '## Sheet: name' then CSV rows written by an in-house writer equal to Python csv.writer(lineterminator='\n') with minimal quoting (quote on delimiter, quote character, CR or LF; doubled quotes; a lone empty field written as '""'). Shared and inline strings, booleans as TRUE/FALSE, skipped cells keep their column. PPTX: slides in presentation order via relationships, under '## Slide N'. OpenDocument: paragraphs and headings, tables tab-separated under '## name', repeated columns capped at 64. EPUB: container -> OPF -> manifest, spine order with paths normalized relative to the OPF folder. XHTML reduced by an in-house tolerant tag scanner equivalent to the HTMLParser subclass: script/style/head skipped with a depth counter, newline on start and end of the BLOCK tag set, character references decoded like Python html.unescape, then whitespace runs collapsed to one space and 3+ newlines to 2, stripped.
- RTF: latin-1 view; control words dropped; par and line become newlines; \'hh decoded through the document code page as Maya does; \uN with skip count; font, colour, style tables and other destinations skipped. Exact port of _rtf.
- _result: strip; empty gives 'this <format> has no text in it'; cut at text_limit code points with truncated true and note 'cut at N characters - the text-file limit for this model's context'.
- Messages that name Maya in the source use the product name (deviation). Exception detail tails in parentheses carry Rust-side text (deviation).

**Parity tests**

test_attach.py Documents (7: Word, Excel, PowerPoint order, OpenDocument, EPUB spine order, RTF, cut at the limit) and Text (6: any-name UTF-8, UTF-16 with and without BOM, Latin-1, binary says what it is, empty document, zip bomb capped). Every fixture is generated in test code, so the Python builders are ported as Rust test helpers that build OOXML/ODF/EPUB zips. Add about 15 unit tests for CSV quoting, cp1252 table edges, ZIP64, CRC failure and a malformed XML message.

**Definition of done**

All 13 ported tests and the new unit tests pass. A fuzz-style test feeds 1,000 random and mutated zips without panics and within the caps. A reviewer can trace every Maya error string to the Rust source. The crate builds without tokio. The new dependencies are recorded with licences in the dependency ledger.

<a id="rsp-13"></a>
### RSP-13 PDF object layer: lexer, object scan, stream filters, page tree

- **Milestone:** M6
- **Rust target:** console-attach::pdf::{lexer, object, filters, document}
- **Platform:** platform-neutral
- **Risk:** medium. A tolerant parser over hostile input: no panics, no unbounded recursion, every allocation capped. The port should be line-by-line faithful, recorded as an adaptation of Maya MIT code in NOTICE.md provenance.
- **Depends on:** RSP-12 (shared miniz_oxide; crate scaffolding)
- **Estimated size:** 900 lines of code; 500 lines of tests
- **Donor sources:** serve/pdf_text.py lines 1-454 (MAX_STREAM, DEADLINE_S, MAX_FORM_DEPTH, PdfError, Ref/Name/Op/Stream, Lexer, _png_unpredict, _lzw, _inflate, _a85, _as_list, _OBJ regex, Document._scan/get/decode/pages/contents)

**Behaviors to reproduce**

- Lexer: whitespace and comments skipped, regular tokens, numbers (int vs real), literal strings with escapes, octal and line continuations, balanced parentheses, hex strings, names with #xx escapes, arrays, dictionaries, 'R' references, keywords as operators.
- Object discovery without the xref table: scan the whole file for (?<![0-9])(\d{1,10})\s+(\d{1,5})\s+obj\b with a hand-written byte scanner, no regex crate. Later definitions overwrite earlier ones (incremental updates). Trailer and XRef-stream dictionaries are collected only for /Root and /Encrypt. Object streams (/Type /ObjStm, /N, /First) are expanded.
- Filters: FlateDecode (zlib, with a raw-deflate fallback), LZWDecode (EarlyChange), ASCII85Decode, ASCIIHexDecode, RunLengthDecode, PNG predictors (columns, colors, bpc). Each decompressed stream is capped at 64 MiB.
- Page tree walked with inherited Resources (and MediaBox) to depth 64. contents(page) concatenates content streams.
- Encrypted documents (/Encrypt in a trailer) raise PdfError with the 'encrypted' message used by the orchestrator.
- Deadline: 20 s by default (injectable), checked per page, per object stream and every 4096 operators (the operator count is enforced in RSP-14). Returns PdfError('...') on expiry, worded as in the source.

**Parity tests**

There is no direct Maya test at this layer. test_attach.py PurePdf test_object_stream_and_differences and test_encrypted_says_so depend on it. Add about 25 unit tests: lexer tokens, each filter including predictors against inputs built in the test code, incremental-update overwrite, object stream expansion, a page tree with inheritance, the stream cap.

**Definition of done**

Unit tests pass. A 2,000-iteration mutation fuzz on generated PDFs produces no panic and respects caps and deadline. A reviewer can diff function by function against pdf_text.py lines 1-454, with mapping comments at module heads.

<a id="rsp-14"></a>
### RSP-14 PDF text interpreter, fonts and encodings, and page pictures

- **Milestone:** M6
- **Rust target:** console-attach::pdf::{fonts, glyphs, content, pictures}
- **Platform:** platform-neutral
- **Risk:** medium. Exact-string outputs. The glyph table must be transcribed exactly. PNG bytes need not be identical to zlib's, but the decompressed IDAT must match (that is what the test asserts).
- **Depends on:** RSP-13
- **Estimated size:** 950 lines of code; 500 lines of tests
- **Donor sources:** serve/pdf_text.py lines 455-805 (_GLYPHS, _ACCENTS, glyph_text, _BASE encodings, _cmap, Font, _ops, _Page.run/emit/newline/space, text_pages, _png, picture, page_pictures)

**Behaviors to reproduce**

- Content-stream interpreter for Tf, Tj, ' and ", TJ (kerning below -180 inserts a space), Td/TD, Tm, T*, ET and Do (form XObjects to depth 8). Inline images BI ... ID ... EI are skipped. Newline and space heuristics are exactly as _Page.emit/newline/space. text_pages(data) returns one string per page.
- Fonts: ToUnicode CMaps (bfchar, bfrange including array form; codespace widths). /Differences glyph names through the in-repo glyph-name subset table plus uniXXXX/uXXXX forms and accent composition (_ACCENTS). WinAnsi (cp1252), MacRoman (Python mac_roman table, hand-coded), Standard (latin-1 as in the source), and the predefined UCS2/UTF16 CMaps. Composite fonts without a map produce no text.
- Pictures: page_pictures(data, max_pages) returns the largest image XObject on each of the first max_pages pages. DCT passes through as image/jpeg. 8-bit or 1-bit Flate grey, RGB or indexed images are re-encoded as PNG by hand (signature, IHDR, optional PLTE, IDAT holding zlib of filter-0 rows, IEND, CRC-32). CCITT, JBIG2, JPX, CMYK, 16-bit and image masks are skipped, as are images over 40,000,000 pixels.
- Deadline checks every 4096 operators. Glyph table provenance is noted (an Adobe Glyph List subset).

**Parity tests**

test_attach.py PurePdf (5: identity font through ToUnicode, object stream plus Differences, scanned page pictures, which also exercises RSP-15 with poppler absent; encrypted says so; inline image skipped), ported with the _pdf/_stream builders as Rust helpers (zlib via miniz_oxide in tests). Add about 15 unit tests: TJ kerning threshold, T*/'/" operators, MacRoman and WinAnsi glyphs, bfrange arrays, 1-bit and indexed PNG output decoded back in the test.

**Definition of done**

All 5 PurePdf tests pass with identical strings. The new unit tests pass. The glyph-table provenance line is in NOTICE.md. A reviewer confirms there is no panic path, via a review of the fuzz harness from RSP-13 extended to content streams.

<a id="rsp-15"></a>
### RSP-15 PDF orchestrator and optional poppler adapter

- **Milestone:** M6
- **Rust target:** console-attach::pdf::extract (orchestrator, pure) plus console-attach::poppler behind cargo feature 'poppler' (native only: std::process)
- **Platform:** platform-neutral
- **Risk:** low. Behaviour differs depending on whether poppler is installed, exactly as in Maya; CI on macOS normally has no poppler. The fake scripts make the command-line contract testable everywhere POSIX. Poppler is GPL and stays an optional external program, never bundled.
- **Depends on:** RSP-14
- **Estimated size:** 450 lines of code; 500 lines of tests
- **Donor sources:** serve/pdf.py (all 184 lines)

**Behaviors to reproduce**

- extract(data, want_images, text_limit, text_only) requires the %PDF- header. The bytes are written to a private temp directory (0700, product prefix) only when a poppler tool is available. pdftotext and pdftoppm are looked up on PATH at every call through an injectable ToolLocator.
- Text: 'pdftotext -q -layout in.pdf in.txt' with a 30 s timeout, reading at most text_limit + 4096 bytes as UTF-8 with replacement. If that yields fewer than 200 characters after stripping (TEXT_FLOOR), the pure reader is tried and the longer text wins. 200 or more characters returns kind text, with the page count from pdfinfo's 'Pages:' line or else the parser's count.
- Scanned (want_images true): 'pdftoppm -png -r 100 -f 1 -l 6 in.pdf <dir>/page'. Pages are ordered by numeric suffix. Without poppler, page_pictures() is used. The result is {kind:'images', format:'PDF', pages:N, images:[{name:'page K', data:'data:image/png|jpeg;base64,...'}], note 'the first N of T pages'}.
- Fallbacks and errors as in the source: a little text beats an error. Messages distinguish an encrypted PDF, a text-only model (text_only wording), images switched off, and nothing readable, the last with the install hint when a tool is missing (apt/pacman/brew/scoop wording retained). A poppler timeout gives 'the PDF was dropped, try a smaller one'. A non-zero exit or missing tool falls through to the pure reader.
- With the 'poppler' feature off (e.g. a future wasm build) the pure reader alone is used and the install hint is still shown.

**Parity tests**

test_pdf.py: Extract (6) and RealPdfExtras (1) run when real poppler is on PATH, as in Maya; they are also run unconditionally against fake pdftotext/pdftoppm/pdfinfo shell scripts in tests/data/fake-poppler/ that record argv and emit canned output. MissingPoppler (3) uses ToolLocator returning none. Route (4) is in RSP-16. About 10 methods here plus 4 fake-poppler contract tests (argv exactness, timeout, page ordering, pdfinfo count).

**Definition of done**

All tests pass with and without real poppler. The fake-poppler tests assert exact argv. The temp directory is removed in all paths (asserted). Timeout is proven with a sleeping fake script and a shortened injected timeout.

<a id="rsp-16"></a>
### RSP-16 Inline file parts in the three dialects and the /attach and /pdf routes

- **Milestone:** M6
- **Rust target:** console-attach::parts (pure) plus route handlers in console-attach::routes mounted by pulsar-console
- **Platform:** platform-neutral
- **Risk:** low. The fence-length rule and dialect shapes are exact-string. The route tests need the fake engine and server, so this is scheduled after HTTP and CORE basics.
- **Depends on:** RSP-12; RSP-15; HTTP: route registration, body limit handling, API key, own-origin check; CORE: engine max_context accessor, vision capability flags (RSP-17)
- **Estimated size:** 450 lines of code; 600 lines of tests
- **Donor sources:** serve/attach.py lines 504-610 (FILE_PARTS, _data_url, _part_file, file_block, _image_part, expand_content, expand_request); server.py _attach 6434-6461, the do_POST expand_request call 6268-6274, text_file_limit and /health max_text_file (164-171)

**Behaviors to reproduce**

- expand_request(req, api in openai|responses|anthropic, want_images, text_limit, text_only) runs before any other processing on /v1/chat/completions, /v1/responses and /v1/messages. It rewrites content lists in place for messages (Chat Completions, Anthropic) or input items (Responses). Parts inside function_call_output are not expanded.
- Part types: 'file' {file:{filename, file_data}}; 'input_file' {filename, file_data}; 'document' {title, source {type:'base64', data} | {type:'text', data} | {type:'content', content: string or [{text}]}}. file_data is a data: URL (base64 or plain) or bare base64, decoded leniently like Python b64decode with validate false.
- Each part is replaced by a text part (type 'text', or 'input_text' for Responses) whose text is 'File: <name>' + newline + a backtick fence one longer than the longest backtick run inside (minimum 3) + text + the closing fence. A scanned PDF on a vision-capable server becomes 'File: <name> (its first N pages as pictures)' followed by image parts in the dialect's shape: {type:'image_url', image_url:{url}}, {type:'input_image', image_url} or {type:'image', source:{type:'base64', media_type, data}}.
- file_id, file_url, URL document sources and unreadable files give HTTP 400 with the source's messages (product name substituted).
- text_file_limit(max_context) = max(512 KiB, min(16 MiB, 4 x context tokens)), published as /health max_text_file.
- POST /attach and alias POST /pdf: the body is read first. Content-Type must be application/octet-stream or application/pdf, else 415 "send the file's bytes as application/octet-stream". An Origin other than the Host gives 403. The API key applies. Bodies over 64 MiB give 413. The name comes from X-File-Name, percent-decoded and cut to 255 characters, defaulting to 'file' or 'file.pdf'. Always 200 with the extract() result, error results included. want_images = the server has a vision path. text_only wording comes from the model capability.
- /health: images, videos and text_only come from RSP-17; max_text_file is reported here.

**Parity tests**

test_attach.py ApiParts (6: openai file part, responses input_file, anthropic documents, anthropic scanned PDF pages as image blocks, unreadable and by-reference errors, content without files untouched) and Route (6: /attach Word 200, foreign page 403, form types 415, health videos flag, chat completion with a file part, bad file part 400). test_pdf.py Route (4: text PDF round trip, wants PDF bytes not JSON, says what it cannot read, scanned PDF errors when the model reads no pictures). 16 methods.

**Definition of done**

All 16 ported tests pass. The attach result object and route are documented in the UI-to-server contract (Phase 2 target). A reviewer confirms expansion happens before dialect parsing on all three endpoints, with a test per dialect.

<a id="rsp-17"></a>
### RSP-17 Media plumbing and the vision seam: sources, capabilities, prompt placeholder expansion

- **Milestone:** M6
- **Rust target:** console-media::{source, seam, expand, capability}; a hook called from console-core's prepare
- **Platform:** platform-neutral
- **Risk:** medium. Tight coupling with CORE's prepare and FIFO. The hook interface must be agreed early. The test chat templates with media markers must be repo-owned (the glm_tool_images.jinja fixture and Qwen's template are vendor-derived and are not vendored).
- **Depends on:** CORE: prepare hook point, engine FIFO turn, ensure_engine, engine_for router hook, per-request embeddings path passed to the engine, engine INFO facts; PROMPT: media_of, deepseek_images, reads_images(template), template markers and the tokenizer's special-token encode (parse_special true/false); ENG: fake engine accepting and recording an embeddings/picture file path and its bytes; INFO keys vision, vision_*; MODELS/HTTP: outbound HTTP client for opt-in remote sources; LAUNCH: 'vision' config block and media-source policy setting
- **Estimated size:** 700 lines of code; 600 lines of tests
- **Donor sources:** server.py Service.prepare media section 3575-3679 (text-only tolerance for tool-result pictures, engine-tower dispatch, the template marker logic for GLM and Qwen, image pad and video frame expansion, literal pad handling, combined embeddings file), Vision.load 1820-1831, capability reporting (/health images, videos, text_only; /v1/models input_modalities; /v1/status vision error for engine INFO vision=off), startup selection 7217-7286; frontend.py media_of/deepseek_images (owned by PROMPT, consumed here)

**Behaviors to reproduce**

- trait VisionBackend with three implementations chosen at startup: ExternalEncoder (RSP-18), Ds4Tower and Mm3Tower (RSP-19); None means no vision. Selection mirrors main(): a configured 'vision' block -> ExternalEncoder (resident, or on demand when gpu is set, resident is false and the backend is not metal, with lending); otherwise engine INFO vision=ds4 -> Ds4Tower, vision=mm3 -> Mm3Tower, vision=off -> none, with the 'images: OFF' log and the /v1/status vision error 'vision tower did not load ...'.
- Source loading: data: URLs decoded (base64). http(s) URLs fetched with a 60 s timeout and User-Agent <product>, and file:// or bare local paths read from disk, both only when enabled by the media-source policy (see deviations); otherwise 400 'an image must be a data: URL ...' with the policy hint.
- prepare hook: if media appear only in role 'tool' messages and the model is text-only (glm_dsa without image markers), they are ignored. A video on a tower backend gives '<model> reads pictures, not videos'. Tower path: cancel is checked before and between pictures ('image preparation was cancelled'), then picture(), expand(), and a write to <dir>/req-<12 hex>.dsi. No vision with a glm_dsa template and no image markers gives '<model> reads text only, so it cannot read images: ...'. No vision otherwise gives 'this server was started without the vision encoder ...'.
- External path: marker tokens chosen by template (GLM <|begin_of_image|><|image|><|end_of_image|> and <|begin_of_video|><|video|><|end_of_video|>; Qwen <|vision_start|><|image_pad|><|vision_end|> and <|video_pad|>). Encoding happens inside the engine FIFO turn: ensure_engine, engine_for('has pictures') for the multi-GPU router hook, then vision.active(). Each pad that directly follows its start marker is expanded to that image's token count. A pad elsewhere is re-encoded as literal text. A count mismatch gives 'the prompt and its images do not match'. Each video marker becomes, per frame, start + pad x n + image end. A count mismatch gives 'the prompt and its videos do not match'. The encoded files are concatenated in media order into <dir>/req-<12 hex>.sve, which becomes the request's embeddings path.
- The embeddings or picture path is per request (not thread-local), handed to the engine call, and deleted after the request in all paths, including cancel, context overflow and disconnect.
- Capability data: images = vision present; videos = ExternalEncoder only; text_only = glm_dsa without vision; input_modalities for /v1/models.
- Test seam: the trait admits in-test fakes equivalent to Maya's ad-hoc Vision classes (encode -> (path, n), encode_video -> (path, [n...]), active guard, owed flag).

**Parity tests**

test_tool_videos.py ToolVideos.test_templates_render_and_prepare_in_media_order and test_tool_images.py test_templates_render_and_prepare_in_image_order, which are shared with PROMPT; this package owns the prepare-expansion assertions. test_responses.py test_images_reach_prompt_and_engine. Media halves of test_response_jobs image tests, with RSP-07. Add about 10 unit tests: literal pad kept as text, mismatch errors, tool-result-only pictures on text-only, source policy refusals, cleanup on every failure path.

**Definition of done**

The ported tests pass with fake backends. A reviewer verifies no temp file survives any failure path (directory-listing assertions). Capability flags appear in /health, /v1/models and /v1/status. The VisionBackend trait is documented in contracts/media.md.

<a id="rsp-18"></a>
### RSP-18 External vision encoder adapter (maya-vision line protocol), video guards and GPU memory lending

- **Milestone:** M6
- **Rust target:** console-media::external (implements VisionBackend) plus bin target fake-vision-encoder (test support)
- **Platform:** hardware-or-os-specific
- **Risk:** medium. No real encoder exists in this increment; everything is exercised against the fake binary. GPU lending, VRAM measurement and CUDA pinning are meaningful only on NVIDIA/AMD hosts and are labelled 'ported, fixture-verified, unverified on hardware'.
- **Depends on:** RSP-17; ENG: engine command channel for VLEND/VRECLAIM in the fake engine; TELEMETRY/HOST: GPU list accessor (gpu_list) for pinning (trait); LAUNCH: 'vision' config block (exe, mmproj, model, gpu, threads, max_tokens, no_flash_attn, resident), log path, run-config path for vision-memory.json
- **Estimated size:** 1000 lines of code; 650 lines of tests
- **New dependencies:** image (pin exact; default-features off; features png, jpeg, gif, bmp, webp; shared with RSP-19)
- **Donor sources:** server.py class Vision 1731-1958, vision_footprint 1961-2010, on-demand wiring 7217-7286 (VLEND/VRECLAIM, MAYA_GLM_VISION_LEND_MB, CUDA_VISIBLE_DEVICES pinning, Metal residency rule)

**Behaviors to reproduce**

- Child process argv: <exe> --mmproj <mmproj> --model <model> [--gpu] [--threads N] [--max-tokens N] [--no-flash-attn] [--no-warmup when on demand]. Stderr goes to the configured log, else is discarded. The first stdout line must start with READY, else 'the vision encoder did not start: <line>'.
- Protocol: 'ENC <image> <out>' and 'VID <video> <out>' lines answered by 'OK <tokens>' or 'ERR <message>'. 'QUIT' on stop, with a 10 s wait then kill. Error texts: 'the image could not be read: <msg>' / 'the vision encoder stopped' and the video equivalents.
- normalize(): JPEG, PNG, BMP and GIF pass through. Other formats are decoded and re-encoded as PNG with transparency flattened onto white; undecodable input gives 'the image could not be read (...)'. Uses the image crate (deviation: the format set differs from Pillow's).
- Cache keyed by the first 32 hex of SHA-256 of the normalized bytes (raw bytes for video), 64 entries, oldest evicted with its file deleted. Files live in a private temp dir (product prefix). The input temp file is deleted after the answer.
- Video: video_container(bytes) -> mp4 for ftyp/moov/mdat/wide/free/skip at offset 4, webm for EBML, avi for RIFF....AVI, otherwise none ('this video's format is not one ... reads: send MP4, MOV, WebM, MKV or AVI'), so playlists never reach ffmpeg. ffmpeg and ffprobe must be on PATH via the injectable ToolLocator ('videos need ffmpeg and ffprobe ...'). The duration comes from 'ffprobe -v error -protocol_whitelist file -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 <path>' with a 30 s timeout. Refused when seconds x 4 > MAX_FRAMES (env, default 240, minimum 1) with 'the video is N s long: M frames at 4 a second, more than the L ... reads (...)', and the temp file is removed. Frame token counts are read from SVE1 record headers (int32 magic 0x31455653, n_tokens, nx, ny, n_embd; skip n x n_embd x 4 bytes); a bad header gives 'not an SVE1 embeddings file'.
- On demand (lending): no process until a picture needs encoding. _start calls settle() then lend() (engine command VLEND -> VLENT). active() guard: when lending, the encoder is stopped at exit, then reclaim() (VRECLAIM -> VRECLAIMED) is retried 40 x 0.25 s; owed stays true while reclaim fails, with the log line about prompts being read token by token.
- vision_footprint(cfg, env, cache_file, gpu): for each cap in [configured] or [4096, 2048, 1024], key '<resolved mmproj>|<size>|<mtime int>|gpu<g>|cap<c>|fa<0|1>' in vision-memory.json, which sits beside the run config. A miss runs '<exe> ... --gpu --max-tokens <cap> --measure [--no-flash-attn]' with a 600 s timeout and parses 'MEM <a> <b> <total>' -> bytes = a + b + 256 MiB. The first cap whose bytes <= 15% of total is chosen (or the last). A damaged cache is re-measured. Write failures are ignored. None when there is no measurement, which falls back to CPU.
- Startup wiring: CUDA_VISIBLE_DEVICES pinning for gpu encoders on non-hip, non-metal backends; MAYA-equivalent LEND_MB environment for the engine (product-named). On Metal the encoder stays resident. These rules are implemented behind a GpuEnvironment trait and labelled unverified on real hardware.
- fake-vision-encoder: prints READY, answers ENC by writing a deterministic SVE1 file (token count from the file size or a directive in the image bytes), VID with N frame records, ERR on a magic 'bad' payload, MEM for --measure, and exits on QUIT.

**Parity tests**

test_tool_videos.py VideoGuards (4: containers, a playlist never reaches ffmpeg, no ffmpeg, too long), ported with ToolLocator and duration-probe injection. Add about 14 tests against fake-vision-encoder: READY handshake failure, ENC OK/ERR, cache hit and eviction at 65, VID frame counts from SVE1, normalize pass-through versus conversion, on-demand lend/stop/reclaim sequence with a fake engine command channel including reclaim failure leaving owed, vision_footprint cache hit/miss/damaged file/cap selection with fake MEM output.

**Definition of done**

All 18 tests pass on macOS with the fake encoder. vision-memory.json format and location are documented as a persisted file in contracts/media.md. A reviewer checks that every hardware-only branch sits behind the GpuEnvironment trait and carries the unverified label in docs.

<a id="rsp-19"></a>
### RSP-19 DeepSeek (DSI1) and MiniMax (MMI1) picture preprocessors

- **Milestone:** M6
- **Rust target:** console-media::{ds4, mm3} (geometry and file writers pure; pixel preparation uses the image crate)
- **Platform:** platform-neutral
- **Risk:** medium. Geometry and file layout are exact. Pixel values are not bit-exact with Pillow's resampling and are unverifiable without a real tower (labelled). Licence: the ds4 plan derives from DeepSeek MIT code, so the DeepSeek MIT notice is carried in NOTICE.md. The mm3 smart_resize may derive from MiniMax Community License code and needs an owner decision.
- **Depends on:** RSP-17; ENG: fake engine with INFO vision=ds4|mm3 and geometry keys, recording picture-file bytes
- **Estimated size:** 700 lines of code; 500 lines of tests
- **New dependencies:** image (shared with RSP-18)
- **Donor sources:** serve/ds4_vision.py (all 186 lines); serve/mm3_vision.py (all 175 lines); server.py tower dispatch 3586-3605 and selection 7255-7270

**Behaviors to reproduce**

- ds4 Geometry from engine INFO keys vision_patch, vision_merge, vision_min_pixels, vision_max_tokens, vision_max_wh_ratio, image_token, with defaults patch 14, merge 3, min_pixels 544*544, max_tokens 1024, no ratio cap, image_token 129264. plan(w, h): scale up below min_pixels, round sides up to multiples of 14, grid = ceil((side // 14) / 3). If n_h x (n_w + 1) + 2 > max_tokens, solve the largest aspect-preserving size that fits (exact integer/float steps from _solve_resize_ratio). span_tokens = n_h x (n_w + 1) + 2.
- ds4 prepare: decode, EXIF orientation applied, transparency flattened onto white, then padded to the planned size with grey (127,127,127) after an aspect-preserving resize (ImageOps.pad semantics: centred), or plainly resized when the ratio cap applies. Output is raw RGB rows. Undecodable input gives 'the image could not be read (...)'.
- mm3 Geometry: patch 14, merge 2 (factor 28), min_pixels 4*28*28, max_pixels 672*672, image_token 200025, image_start 200029, image_end 200030, overridable from INFO. smart_resize(h, w): refuse aspect ratios above 200:1; round each side to a multiple of 28 (at least 28); scale down to max_pixels or up to min_pixels keeping the ratio. Bicubic resize. tokens = (h/28) x (w/28) + 2.
- Picture caches of 32 keyed by the first 32 hex of SHA-256 of the source bytes, oldest evicted.
- expand: ds4 replaces every image-token id with span_tokens copies and returns the span starts. mm3 replaces each image token with image_start, n image tokens, image_end and returns the first image token position of each span. A placeholder/picture count mismatch raises ValueError-equivalent errors.
- write: little-endian magic 'DSI1' or 'MMI1', int32 count, then per picture int64 start, int32 width, int32 height and h x w x 3 RGB bytes. Both are written to req-<12 hex>.dsi (Maya writes the MiniMax file with .dsi too; kept) in a private temp dir and deleted after the request. Cancel is honoured before writing.
- The mm3 implementation is gated on the owner's licence decision (see open questions). If declined, Mm3Tower answers every picture with '<model> reads text only on this server: the MiniMax picture path is not included' and the MMI1 writer is omitted.

**Parity tests**

test_ds4_vision.py Plan (2: 8 reference plans; prepare with transparency, asserting dimensions and a white centre pixel) and Spans (1: expand plus DSI1 layout). The Template (2) tests need a local DeepSeek tokenizer pack and template and are recorded as not exercisable. test_mm3_vision.py SmartResize (3) and Spans (4: expand, mismatch, write, from_info). test_response_jobs.py ds4 image tests, with RSP-07. 10 runnable methods plus about 6 new pixel tests (EXIF orientation 6 and 8, palette transparency, grey padding placement).

**Definition of done**

All 10 runnable Maya methods pass with identical geometry numbers. DSI1/MMI1 byte layouts are verified by header parsing in tests. NOTICE.md carries the DeepSeek MIT line. The mm3 gate state is recorded in the spec. A reviewer checks the 8 ds4 reference plans and the mm3 reference cases verbatim.
