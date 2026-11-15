# Feature Specification: PulsarMLX Console Serving Parity

**Feature Branch**: `feat/022-console-serving-parity`

**Created**: 2026-11-14

**Status**: Draft (milestone M0, awaiting the owner's review of the M0 documents; nothing
in this feature is implemented)

**Input**: The plan the owner approved on 2026-11-14, whose decisions are recorded in
[ADR 0008](../../docs/architecture/decisions/0008-console-serving-ahead-of-stage-f.md)
(the plan itself is not published): rebuild project-maya's serving layer
(`serve/`) and its Phase 1 dashboard in Rust inside PulsarMLX, as the product "PulsarMLX
Console", at behavioral parity with project-maya at the pinned commit `7e68a30f` (v1.1.63),
proven against synthetic backends only, with a backend seam that the PulsarMLX native
engine can attach to in a later, separately approved phase.

**Claim boundary**: Every capability in this document is planned. When built, it can at
most be described as "qualified on synthetic backends". No statement here means that a
real model is served, that any donor engine runs, or that a hardware reader is correct on
real hardware. The donor's observed behavior at `7e68a30f` is the reference; its benchmarks
are never PulsarMLX evidence.

**Terms used in this document**:

| Term | Meaning |
| --- | --- |
| Donor | project-maya (github.com/mw00/project-maya, MIT), pinned at commit `7e68a30f2f208056195352129188661fb6b94445` (v1.1.63). |
| Parity | Driven by equivalent fake engines, the same externally observable behavior as the donor's `serve/` at the pin for every route, stream format, error, configuration key, environment variable and persisted file. The donor is the reference even where it differs from the OpenAI or Anthropic specifications. |
| Synthetic backend | An engine that serves no model: the scripted in-process engine, the PulsarMLX fake engine binaries, or a test adapter. |
| Ledger | `console/parity/ledger.json`, one row per donor test method (913 rows). |
| Deviation register | `specs/022-console-serving-parity/contracts/deviations.md`, every intended difference from literal parity with its reason and its approval basis; proposed differences that await the owner's decision are kept in a separate section and are not approved. |
| Name table | `specs/022-console-serving-parity/contracts/naming.md`, the published old-to-new name table. |
| Reference corpus | Requests, responses, streams and rendered-prompt probes captured from the donor's own server in fake-engine mode at the pin, normalized and committed as text with a provenance header. |

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Stream an OpenAI-Style Chat Completion (Priority: P1)

As an API client developer, I can send an OpenAI-style chat completion request to
`pulsar-console` running the scripted engine and receive a correctly framed streamed
answer, with the same frames, finish reason and usage the donor produces, so that a client
written for the donor works unchanged against PulsarMLX Console.

**Why this priority**: It is the first end-to-end slice (milestone M1) and the foundation
every other story builds on: transport, request validation, the backend seam, the queue,
the turn driver, tokenization and the OpenAI dialect. Without it nothing else can be
demonstrated.

**Independent Test**: Start `pulsar-console` with the scripted engine and a configured
synthetic chat template on loopback, stream one chat completion with an HTTP client that
prints raw bytes, and compare the frame sequence, finish reason and usage with the
committed reference recording for the same scenario.

**Acceptance Scenarios**:

1. **Given** the server is running the scripted engine with a script that answers "hello",
   **When** a client posts a streamed chat completion, **Then** the response is a server-sent
   event stream whose first chunk carries the assistant role and empty content, whose
   content chunks concatenate to the scripted answer, whose final chunk carries the finish
   reason and usage, and which ends with the terminator frame, matching the reference
   recording after normalization of ids and timestamps.
2. **Given** the same server, **When** the client posts the same request without streaming,
   **Then** a single JSON completion object is returned with the same content, finish
   reason and usage as the streamed form.
3. **Given** a streamed answer is in progress and a second request is waiting in the queue,
   **When** the first client disconnects, **Then** the engine is told to stop, the first
   request's queue place is released after the engine has drained, and the second request
   starts.
4. **Given** the scripted engine reports an engine death mid-answer, **When** the stream is
   being written, **Then** the stream ends with the donor's error frame and terminator, and
   the next request restarts the engine.
5. **Given** a malformed body, a non-object body or an invalid sampling value, **When** the
   request is posted, **Then** the donor's status code and error body are returned before
   any stream begins.

---

### User Story 2 - Start and Stop the Server Safely on Loopback (Priority: P1)

As an operator, I can start `pulsar-console` on loopback, see a clear ready line, rely on
the approved security posture on every route, and stop
it cleanly with a signal, so that running it on my machine does not expose a cross-site,
DNS-rebinding or command-injection surface.

**Why this priority**: The security posture (SEC-1 to SEC-7) applies to every route from
the first HTTP package on. A server that streams but can be driven by any web page the
operator visits is not acceptable even for synthetic use.

**Independent Test**: Start the binary with the scripted engine; issue raw HTTP requests
with a foreign `Host`, a foreign `Origin`, `Origin: null`, a non-JSON content type on a
POST, and a mutating admin request from a non-loopback client without a key; then send a
termination signal during an answer and record the shutdown order and exit code.

**Acceptance Scenarios**:

1. **Given** no chat template is configured, **When** the server starts, **Then** start-up
   fails with a clear error that names the missing template, and no vendor template is
   used as a fallback.
2. **Given** a valid configuration on a loopback bind, **When** the server starts, **Then**
   the ready line names the address, the dialect routes and the context size in the donor's
   format and uses the `[console]` log prefix.
3. **Given** the server is bound to loopback, **When** a request arrives with a `Host`
   header that is not a loopback name or an allowlisted host, **Then** it is refused with
   403 before routing.
4. **Given** any route, **When** a request carries an `Origin` that is not the server's own
   page and not CORS-allowed, including `Origin: null`, **Then** the request is refused.
5. **Given** a POST with a non-JSON content type to a JSON route, **When** it is received,
   **Then** it is refused with the donor's 415 shape.
6. **Given** an answer is streaming, **When** the process receives a termination signal,
   **Then** the in-flight request is wrapped up within the configured wrap time, the engine
   receives its stop and quit commands in the donor's order, and the process exits 0; a
   second interrupt during shutdown exits 130.
7. **Given** a non-loopback bind without an API key, **When** the server starts, **Then** it
   prints the donor's no-key warning and the LAN addresses, and mutating admin routes are
   refused for non-loopback clients.

---

### User Story 3 - Chat in the Dashboard with the Synthetic Badge (Priority: P2)

As a person using the Phase 1 dashboard served by `pulsar-console`, I can open it in a
browser, send a message, watch the answer stream, stop it, reload mid-answer and resume,
and always see that no real model is behind it.

**Why this priority**: The dashboard is half of the increment's stated value, and the
permanent synthetic badge is the main safeguard against overclaiming. It depends on the
P1 stories.

**Independent Test**: Start the server with the scripted engine, open the dashboard in a
browser, send a prompt, stop one answer, reload during another, and confirm the badge, the
security headers and that a cross-origin POST is refused.

**Acceptance Scenarios**:

1. **Given** the dashboard is open, **When** any screen is shown, **Then** a permanent
   "Synthetic engine: no real model" badge is visible.
2. **Given** a prompt is typed, **When** the person presses Enter, **Then** the answer
   streams into the conversation with reasoning, content and tool blocks rendered as the
   donor renders them, through the hardened rendering path.
3. **Given** an answer is streaming, **When** the person reloads the page, **Then** the
   answer resumes from where the page left off, using the in-memory resumable stream.
4. **Given** the page is opened with `/?q=<text>`, **When** it loads, **Then** the text is
   placed in the composer and nothing is sent until the person presses a key to send.
5. **Given** model output contains HTML or script, **When** it is rendered or previewed,
   **Then** it passes the sanitizer, and a preview runs in its own sandboxed route with
   network access off unless the person allows it for that preview.
6. **Given** the dashboard's About page, **When** it is opened, **Then** the donor's MIT
   text and the bundled third-party license texts are shown, and the product identity is
   PulsarMLX Console with no donor name, logo or quant names presented as its own.

---

### User Story 4 - Anthropic-Style Clients and Tool-Calling Agents (Priority: P2)

As a developer of an Anthropic-style client or a tool-calling agent, I can send Messages
requests and tool definitions and receive reasoning blocks, text and tool calls in the
donor's exact event sequence, so that agents built against the donor work unchanged.

**Why this priority**: Tool calling and reasoning are what agent clients depend on, and
they exercise the prompt and output pipeline (templates, parsers, tool-call syntaxes,
thinking budget, stops and loop guards) that every dialect shares (milestone M2).

**Independent Test**: With the scripted engine emitting token ids that encode reasoning, a
tool call in each supported tool-call syntax and a final answer, send OpenAI and Anthropic
requests, streamed and not streamed, and compare event sequences, tool-call arguments,
stop reasons and usage with the reference corpus.

**Acceptance Scenarios**:

1. **Given** a Messages request, **When** it is streamed, **Then** the event sequence is
   message start, content blocks for thinking, text and tool use with their deltas and
   stops, message delta with stop reason and usage, and message stop, as the donor emits
   them.
2. **Given** an engine emits a tool call in any of the donor's tool-call syntaxes,
   **When** it is parsed at any chunking of the token stream, **Then** the same tool-call
   events and arguments are produced.
3. **Given** a thinking budget is set, **When** the reasoning reaches the budget, **Then**
   reasoning is closed at a sentence boundary the way the donor closes it and the answer
   continues.
4. **Given** an answer repeats itself or a tool call is repeated across turns, **When** the
   loop guards are on, **Then** they intervene with the donor's restarts and history
   handling.
5. **Given** a stop string in the request, **When** it appears in the output, **Then**
   generation stops at the same position and the stop sequence is reported as the donor
   reports it.
6. **Given** a client sends keys beginning with `_` in the request body, **When** the
   request is parsed, **Then** those keys are stripped and never reach internal parser
   state.

---

### User Story 5 - Responses API with Stored and Background Responses (Priority: P3)

As a client of the OpenAI-style Responses API, I can create responses in the foreground or
in the background, store and retrieve them, replay a background response's events, cancel
it, and use structured output validated before it is published.

**Why this priority**: It completes the third dialect (milestone M5) but is not needed for
the first two dialects or the dashboard.

**Independent Test**: Against the scripted engine, create foreground and background
responses, retrieve them, list their input items, replay a background stream from a
cursor, cancel a queued job and a running job, delete a stored response, and compare all
results with the reference corpus.

**Acceptance Scenarios**:

1. **Given** a stored response, **When** a later request names it as the previous
   response, **Then** the conversation continues from it.
2. **Given** a background request, **When** it is submitted, **Then** it returns at once in
   the queued state, and its events can be replayed from any retained cursor and then
   followed live.
3. **Given** a running background job, **When** it is cancelled, **Then** it reaches exactly
   one terminal state and releases its queue place.
4. **Given** a structured-output schema, **When** the answer does not validate, **Then** no
   unvalidated content is published.
5. **Given** a request carries a sealed-reasoning item, **When** the server emits sealed
   reasoning, **Then** it uses the product's own prefix.

---

### User Story 6 - MCP Tools and Attachments (Priority: P3)

As a dashboard user or API client, I can let the server call tools from configured MCP
servers during an answer, and I can attach Office, OpenDocument, EPUB, RTF, PDF and text
files whose text the model receives.

**Why this priority**: These broaden what a chat can do (milestone M6) but are optional
for every other story.

**Independent Test**: Configure the PulsarMLX fake MCP server over stdio and over
streamable HTTP, run a chat that triggers MCP calls, and attach documents generated in
test code in every supported format; compare the tool-loop events and extracted text with
the reference corpus and the re-expressed donor tests.

**Acceptance Scenarios**:

1. **Given** an MCP server is configured and the request opts in, **When** the model calls
   an MCP tool, **Then** the server runs it, reports progress to the dashboard in the
   donor's chunk format, and continues the answer with the result.
2. **Given** an MCP server fails to start, **When** the server starts, **Then** it fails fast
   with the donor's error.
3. **Given** a document in a supported format, **When** it is attached, **Then** the
   extracted text matches the donor's extraction, and oversized, encrypted or malicious
   containers are reported or capped as the donor reports or caps them.
4. **Given** an image source that is a remote URL or a local path, **When** that source
   type has not been enabled in settings, **Then** it is refused; a `data:` URL is always
   accepted.

---

### User Story 7 - Model Management, Monitoring and the Apple Silicon Monitor (Priority: P3)

As an operator, I can list installed run configs, edit engine settings, switch, delete and
fetch models, watch health, status and metrics, and on a Mac see an Apple Silicon monitor
view of unified memory, pressure, swap and disk, all against synthetic backends.

**Why this priority**: These complete the donor's management plane and monitor
(milestones M4, M7 and M8), but a chat works without them.

**Independent Test**: With fixture run configs and the scripted engine, exercise the model
routes, the switch and delete flows, `pulsar-console fetch` against a local fixture
catalog, and `pulsar-console supervise` restarts; read `/health`, `/status`, `/metrics` and
the Prometheus exposition; and render the Apple Silicon monitor view from recorded
telemetry fixtures.

**Acceptance Scenarios**:

1. **Given** run configs named with the `pulsar-` prefix, **When** the models routes are
   called, **Then** listings, settings profiles, switch, delete and leftover handling match
   the donor's behavior and error conventions.
2. **Given** a model switch is requested under `pulsar-console supervise`, **When** the
   server exits with the restart code, **Then** the supervisor restarts it with the
   configuration from the switch note, as the donor's launcher contract specifies.
3. **Given** `/health` is called, **When** it answers, **Then** it reports that the backend is
   synthetic.
4. **Given** the server runs on Apple Silicon, **When** the monitor view is opened, **Then**
   it shows unified memory, memory pressure, swap and disk figures, with GPU activity
   marked experimental.
5. **Given** the release check, **When** it has not been enabled, **Then** no network request
   is made, and when enabled it only notifies and never fetches or runs code.
6. **Given** the shipped model catalog, **When** it is listed, **Then** it is empty.

---

### User Story 8 - Plug an Engine into the Backend Seam (Priority: P3)

As an engine developer, I can attach an engine to PulsarMLX Console either as a child
process speaking the written line protocol or in process at the token level, and the
server's driver works with it unchanged.

**Why this priority**: The seam is what makes the later PulsarMLX engine attachment
possible (milestone M3), but no real engine is attached in this increment.

**Independent Test**: Run the engine conformance suite against the scripted engine, the
line-protocol engine driving the PulsarMLX fake engine binaries, and the
coordinator-shaped test adapter, with no change to the driver between them.

**Acceptance Scenarios**:

1. **Given** a fake engine binary speaking the line protocol, **When** it is started,
   **Then** the handshake, capability flags, generation lines, cancel, pause and wrap
   commands, telemetry side events and terminal lines behave as the protocol contract
   specifies, with the donor's protocol cited as prior art.
2. **Given** the fake engine is killed mid-answer, **When** the client is streaming, **Then**
   the client receives a 503 or the dialect's error tail and the next request restarts the
   engine.
3. **Given** an in-process engine at the token level, **When** it delivers a token again
   after a refused delivery, **Then** an exact replay is dropped and a gap is rejected.
4. **Given** multi-conversation mode, **When** several requests run, **Then** every control
   line, including stop, is tagged with its request, and writes to the engine pipe never
   interleave.

---

### User Story 9 - See Exactly How Close to Parity the Implementation Is (Priority: P3)

As a maintainer or reviewer, I can read the parity ledger and the deviation register and
know, for each of the 913 donor test methods, how it is satisfied, and for each
difference from the donor, why it exists and that the owner approved it.

**Why this priority**: It is the measurement behind the parity claim and must exist from
M0, but it delivers no user-facing behavior on its own.

**Independent Test**: Run the ledger checker on the committed ledger and confirm it fails
on a dangling or pending row (at close-out), on an unresolved test or scenario reference,
and on a deviation id that is not in the register.

**Acceptance Scenarios**:

1. **Given** the ledger, **When** the checker runs, **Then** every one of the 913 rows has
   exactly one disposition and every reference resolves.
2. **Given** a deviation entry, **When** it is read, **Then** it names its id, the donor
   behavior, the PulsarMLX behavior, the reason and the owner's approval, and at least one
   test or ledger row uses it.
3. **Given** a milestone ends, **When** its report is produced, **Then** it states ledger
   counts by disposition and the deviations added.

### Edge Cases

- A client disconnects while its request is still queued: the request leaves the queue
  promptly and never reaches the engine.
- A client disconnects mid-stream: the engine is stopped and drained, and the queue place
  is released only after the drain.
- A resumable web-chat stream is requested after the server restarted: because disk
  persistence is off by default, the donor's "no such answer" response is returned.
- An engine never completes its handshake, or dies during one.
- An engine dies mid-answer, before the first byte or after headers are written.
- A request arrives while a context reload or other exclusive operation is running: the
  donor's 503 with a retry hint is returned.
- A server that is stopping receives queued or new requests.
- A request line, header block or body exceeds the donor's limits; a body is chunked; a
  request carries both a length and chunked encoding; an unsupported method is used.
- The prompt plus requested output exceeds the context.
- Numbers in request JSON exceed 64-bit range or carry precision a binary float would
  lose.
- A chat template raises an error during rendering.
- A tool call is split across arbitrary token boundaries, is malformed, or names a tool
  that does not exist.
- A run config has a byte-order mark, unknown keys or non-ASCII text, and must be rewritten
  byte-identical to the donor's format when untouched.
- An environment variable with a legacy `MAYA_*` or `STRATA_*` name is set: it is not
  honored as an alias.
- A run config's engine `env` block contains variable names meant for the engine child:
  they pass through verbatim.
- A request asks for refusal ablation and the engine does not advertise it.
- A MiniMax-vision engine is configured: it gets a clear "not built" error.
- An attachment is a ZIP bomb, an encrypted PDF or a damaged container.
- A telemetry source lacks a figure on the current machine: the field is null, not
  invented.
- Two processes write the same persisted file, or a write fails: the donor's tolerance
  rules apply (logged, counting continues in memory).
- The port chosen in the dashboard is in use, out of range or equal to the current port.

## Requirements *(mandatory)*

### Functional Requirements

Requirements describe capabilities at the donor's granularity. The exact behavior of each
is the donor's observable behavior at `7e68a30f` unless a deviation id says otherwise; the
detailed behaviors, donor sources and tests are recorded per work package in `tasks.md`
and `contracts/`. "Open item" references point to the list under Scope Boundaries, which
repeats items from the consolidated register in
[`checklists/analysis.md`](checklists/analysis.md).

#### Parity, scope and claims

- **FR-001**: The feature MUST reproduce, against synthetic backends, the donor's
  externally observable behavior for every route, stream format, error, configuration key,
  environment variable and persisted file in `serve/` at `7e68a30f`, treating the donor as
  the reference even where it differs from the OpenAI or Anthropic specifications.
- **FR-002**: Every intended difference from literal parity MUST be an entry in the
  deviation register with its reason and the owner's approval before any test relies on it.
  The approved entries are SEC-1 to SEC-7, PRIV-1, BRAND-1, BRAND-2, LIC-1, LIC-2, POL-1,
  PLAT-1 to PLAT-3 and FIX-1 from the plan's deviation table (FR-090 to FR-106), and PLAN-1
  to PLAN-6 for differences the plan decides elsewhere. Any other difference stays under
  "Proposed, awaiting owner decision" in the register until the owner approves it.
- **FR-003**: The increment MUST NOT serve a real model, and every claim about what it does
  MUST state that its backends are synthetic.
- **FR-004 (PLAN-1)**: The dashboard MUST show a permanent "Synthetic engine: no real
  model" badge, and `/health` MUST report that the backend is synthetic.
- **FR-005 (PLAN-2)**: The scripted engine's default model name MUST contain the word
  "synthetic" (exact name: open item OI-2).
- **FR-006**: Hardware- and OS-specific readers MUST be labelled unverified on real
  hardware everywhere they are mentioned.

#### Transport and wire foundations

- **FR-007**: The server MUST speak HTTP/1.0 and close the connection after each response,
  reproducing the donor's status lines, request-line and header limits, body limits,
  chunked request bodies, unsupported-method answers, timeouts and client-disconnect
  detection.
- **FR-008**: Every wire body and persisted file MUST be written in the donor's
  Python-compatible JSON form (separators, key order, escaping, float formatting and
  exact numbers), using one writer for the whole server.
- **FR-009**: Error bodies MUST follow the donor's three error conventions with the
  donor's status codes and messages, rebranded where they name the donor.
- **FR-010**: The router MUST reproduce the donor's dispatch order for GET, POST, DELETE and
  OPTIONS, its API-key rules (bearer or key header, constant-time comparison, which routes
  are exempt), and its CORS rules, with the SEC-1 additions.

#### Request validation and sampling

- **FR-011**: The server MUST validate requests and normalize sampling parameters exactly
  as the donor does, including shared defaults that other applications can adopt from the
  dashboard settings.
- **FR-012**: The server MUST apply the donor's context rule, reject requests whose prompt
  and output cannot fit, and report the donor's overflow error.

#### OpenAI Chat Completions

- **FR-013**: `POST /v1/chat/completions` MUST produce the donor's streamed chunk sequence
  and non-streamed object, including reasoning content, tool-call deltas, prompt-progress
  chunks when requested, logprobs, JSON mode, finish reasons, usage with cached tokens,
  timings, keep-alives while queued or quiet, and mid-stream error frames.

#### Anthropic Messages

- **FR-014**: `POST /v1/messages` MUST produce the donor's event stream and collected message,
  including the thinking, text and tool-use block state machine, stop reasons, stop
  sequences, usage with cache-read tokens, keep-alives and error events, and the donor's
  error body shape for pre-stream failures.

#### Prompt construction

- **FR-015**: Chat templates MUST render byte-identical prompt text to the donor's for the
  same messages, tools and keyword arguments, under the donor's sandbox semantics.
- **FR-016**: When no chat template is configured, start-up MUST fail with a clear error;
  no vendor template is bundled or used as a fallback.
- **FR-017**: The tokenizer MUST encode rendered prompts to the same token ids as the
  donor's tokenizer for the same tokenizer files, protect quoted special literals as the
  donor does, and decode incrementally across split characters.
- **FR-018**: Request normalization MUST convert OpenAI, Anthropic and Responses inputs,
  including media parts and the DeepSeek path, into the donor's template message form.
- **FR-019**: The DeepSeek prompt encoder MUST reproduce the donor's encoder output.
- **FR-020**: Thinking levels and the GLM effort dialects MUST map to template keyword
  arguments as in the donor, and forced tool-call prefills, JSON mode and context-room
  handling MUST behave as in the donor.
- **FR-021**: The prompt memo and DeepSeek restore points MUST behave as in the donor.

#### Output processing

- **FR-022**: The streaming output parser MUST emit the donor's reasoning, content,
  tool-start, tool-arguments and tool-call events for every supported tool-call syntax at
  any chunking of the token stream, including both stream rewriters (DSML and MiniMax
  text forms).
- **FR-023**: Stop strings, quoted markers and thinking resume MUST behave as in the donor.
- **FR-024**: The thinking budget MUST compute limits, close reasoning softly at a sentence
  end and pass engine keys as the donor does, with the donor's settings route.
- **FR-025**: The in-answer loop guard and the cross-turn loop guard MUST detect and handle
  repetition, tool repeats, blocking and history collapse as the donor does, with their
  counters exposed in metrics.
- **FR-026**: Parser events MUST map to OpenAI and Anthropic response shapes, streamed and
  collected, exactly as in the donor.

#### Backend seam, scheduling and supervision

- **FR-027**: The server MUST provide a backend seam at two levels: a token level that an
  engine implements (token ids in and out, synchronous, owned by one driver thread and not
  required to be thread-transferable), and an event level of reasoning, content and tool
  events with exactly one terminal event. For more than one concurrent generation the token
  level MAY offer a submit-and-pump form with request-id-tagged events, as settled in
  `contracts/backend-seam.md` before the seam is frozen; the blocking generate form is the
  single-conversation case.
- **FR-028**: At the token level, capability flags MUST mirror the donor's engine handshake
  and information lines; requests MUST carry per-request sampling keys; cancel, pause and
  wrap MUST be supported; prompt progress, statistics and residency telemetry MUST arrive
  as side events; and usage MUST be reported by the backend.
- **FR-029**: Token delivery at the seam MUST be at-least-once and keyed by position, with a
  shared ledger that drops exact replays and rejects gaps.
- **FR-030**: The server MUST keep the responsibilities the donor's server keeps:
  tokenization, template rendering, detokenization, stop handling, tool-call parsing,
  thinking budget, loop guard, finish reason and usage.
- **FR-031**: The increment MUST provide a scripted in-process engine at parity with the
  donor's mock engine, a line-protocol child-process engine, fake engine binaries written
  for PulsarMLX, and a test adapter shaped like the engine track's coordinator.
- **FR-032**: The line protocol MUST be written down as a PulsarMLX contract that cites the
  donor's protocol as prior art, and the line-protocol client MUST produce byte-identical
  generation and control lines to the donor's for the same requests.
- **FR-033**: Multi-conversation mode MUST tag requests, route engine output, apply the quiet
  timeout and drain within bounds as the donor does, with the FIX-1 corrections.
- **FR-034**: The request queue MUST be first-in first-out with the donor's places,
  exclusive holders, fair-slice yields, queued keep-alives and queue watchdog, and a
  cancelled waiter or failed turn MUST never leak a place.
- **FR-035**: The turn driver MUST acquire a place, ensure the engine is running, call it,
  drain it, classify errors, retry non-finite results, and record figures as the donor
  does; a client disconnect MUST stop the engine and release the place only after the
  drain.
- **FR-036**: Server-side continuations (fair slices, soft thinking close at a boundary,
  loop-guard and penalty continuations) MUST behave as in the donor.
- **FR-037**: Engine supervision MUST restart a dead engine on the next request, close
  gracefully, kill on timeout, watch for stalls, record death notes, narrate start-up,
  and support unload, idle unload, context reload with fallback and atomic save, and
  shutdown wind-down, as in the donor with the FIX-1 corrections.
- **FR-038**: An engine conformance suite MUST check any engine against the protocol
  profile and the seam contract.
- **FR-039**: The backend seam contract MUST be offered to the engine track for review
  before it is frozen.

#### Monitoring, discovery, admin and lifecycle

- **FR-040**: `/health`, `/status`, `/v1/status`, `/metrics` and the Prometheus exposition
  MUST report the donor's fields, order, conditional fields and metric names, with the
  donor's product-named metric prefix renamed and the `llamacpp:` names kept.
- **FR-041**: The llama.cpp-compatible discovery and utility routes (`/v1/models`,
  `/models`, `/props`, `/slots`, `/tokenize`, `/detokenize`, `/api/tokens`) MUST behave as
  in the donor.
- **FR-042**: The dashboard admin routes for shared settings, thinking budget, port, report
  and context reload MUST behave as in the donor, including atomic run-config rewrites
  and secret masking in the report.
- **FR-043**: Resumable web-app streams (`strata_resume`, `GET /v1/strata/stream`,
  `POST /v1/strata/cancel`) MUST behave as in the donor, with answers kept in memory under
  the donor's retention rules and disk persistence governed by PRIV-1.
- **FR-044**: The run config MUST load with key order and unknown keys preserved, and every
  edit MUST be an atomic rewrite in the donor's file format through one writer.
- **FR-045**: Every server environment variable MUST use the `PULSAR_CONSOLE_` prefix with
  the donor's defaults, minimums and parsing rules, and the name table MUST list every
  donor name with its new name. Test-harness switches read by the product or its tests
  also use the `PULSAR_CONSOLE_` prefix; control variables of the fake engines and the
  fake MCP server keep the donor fakes' names, as a test-double interface.
- **FR-046**: Legacy `MAYA_*` and `STRATA_*` names MUST NOT be accepted as aliases.
- **FR-047**: Variable names inside a run config's engine `env` block that pass to engine
  child processes MUST pass through verbatim as opaque data.
- **FR-048**: The wire names `strata_resume`, `strata_mcp`, `strata_tune`,
  `strata_level_default`, `/v1/strata/stream` and `/v1/strata/cancel` MUST be kept
  unchanged.
- **FR-049**: Logging MUST use the `[console]` prefix with the donor's time stamping and log
  tee; signals, the parent-pipe watch, graceful shutdown, the double-interrupt exit 130 and
  the restart exit code 76 MUST behave as in the donor.
- **FR-050**: The `pulsar-console` command line MUST follow the donor's option conventions,
  start-up order, ready line and port-in-use error. A synthetic marker in the ready line
  is a proposal recorded with PLAN-1 in the deviation register and is not required unless
  the owner approves it.

#### Responses API

- **FR-051**: The Responses request normalizer, input items, tools and event serializer MUST
  match the donor's.
- **FR-052**: The credential-scoped in-memory response store MUST behave as in the donor,
  including retrieval, input items, deletion, previous-response continuation and limits.
- **FR-053**: Background responses MUST be queued, run, replayed from a cursor, cancelled and
  expired as in the donor, with exactly one terminal state, bounded event history and
  per-key admission limits.
- **FR-054 (PLAN-5)**: Structured output MUST be validated before publication by a
  restricted JSON Schema validator that reproduces the donor's keyword subset and verdicts.
- **FR-055**: Sealed reasoning MUST be emitted with the product's own prefix; whether the
  donor's prefix is accepted on input is open item OI-1.
- **FR-056**: The Responses limits MUST be configurable under the renamed environment
  names with the donor's defaults.

#### MCP

- **FR-057**: The MCP client MUST connect to servers over stdio and streamable HTTP, manage
  their lifecycle, and report hub status at `GET /mcp`, as the donor does.
- **FR-058**: The server-side MCP tool loop MUST run opted-in tools during a chat answer,
  emit the donor's `strata_mcp` chunks, and handle client-owned tools, cancellation and
  usage as the donor does.
- **FR-059**: The MCP listing command MUST behave as in the donor.
- **FR-060**: A fake MCP server written for PulsarMLX MUST be the test double for every MCP
  test.

#### Attachments and media

- **FR-061**: Attachment readers MUST extract text from Word, Excel, PowerPoint,
  OpenDocument, EPUB, RTF and text files, with the donor's encoding sniffing, ordering and
  ZIP safety limits.
- **FR-062**: The PDF reader MUST reproduce the donor's text extraction, font and encoding
  handling, page pictures and the optional external poppler adapter.
- **FR-063**: `POST /attach`, `POST /pdf` and inline file parts in all three dialects MUST
  behave as in the donor.
- **FR-064**: Media plumbing MUST load image and video sources under the SEC-4 policy,
  report capabilities, and expand prompt placeholders as the donor does.
- **FR-065**: The external vision encoder adapter, video guards and GPU memory lending MUST
  follow the donor's contracts and be exercised only against fakes.
- **FR-066**: The DeepSeek picture preprocessor MUST produce the donor's file format and
  geometry. Whether pixel values may differ from the donor's image library is proposal P-5
  in the deviation register and is not approved (open item OI-13); until the owner
  decides, the ledger rows it affects stay `pending`.

#### Model management and launch

- **FR-067**: Model classification, the installed-model registry (most recently modified
  config is the most recently used), engine-settings profiles and Turbo MUST behave as in
  the donor, with run-config files prefixed `pulsar-` and note files named `.pulsar-*`.
- **FR-068**: Model switch, the restart controller, delete planning, delete execution,
  leftovers and deferred delete of the running model MUST behave as in the donor.
- **FR-069**: The Ollama-shaped model API and the llama.cpp-style model management routes
  MUST behave as in the donor, including model-management gating.
- **FR-070**: The download catalog format and the one-slot pull driver MUST behave as in the
  donor; the shipped catalog MUST be empty.
- **FR-071**: `pulsar-console fetch` and `pulsar-console supervise` MUST keep the donor
  launcher's progress-line, exit-code and restart contracts (PLAT-3).
- **FR-072**: The savings ledger and its routes MUST behave as in the donor (content of the
  built-in price table: open item OI-7).
- **FR-073**: The update routes MUST keep their shapes and follow SEC-5.
- **FR-074 (PLAN-6)**: All outbound network access MUST go through one facade over the
  system `curl`, used only by model pulls, HTTPS MCP servers and the opt-in fetches.

#### Telemetry

- **FR-075**: A telemetry sampler MUST feed the monitor, `/metrics` hardware fields and
  the report, with a null sampler in scenarios.
- **FR-076**: An Apple Silicon reader MUST report unified memory, memory pressure, swap and
  disk figures, with GPU activity as an experimental field (PLAT-2).
- **FR-077**: The donor's NVIDIA, AMD and Windows readers, the GPU map and the multi-GPU
  helpers MUST be ported behind traits and verified with fixtures only (PLAT-1).

#### Dashboard, Phase 1

- **FR-078 (PLAN-3)**: The donor's dashboard MUST be adapted with upstream file names kept,
  carry a provenance header in every adapted file, and be served by the Rust server from a
  fixed compile-time table that never serves a filesystem path.
- **FR-079**: Every dashboard view (Chat, Models with the engine-settings editor, catalog,
  pull and leftovers, Monitor, Settings, Saved, MCP tools, Turbo, search and the phone
  layout) MUST behave as in the donor against the parity routes, except where a deviation
  applies.
- **FR-080**: Browser storage MUST use the `pulsar.` prefix and the IndexedDB database
  `pulsar-console`, with the donor's key suffixes and record schema.
- **FR-081**: A Monitor view for Apple Silicon MUST be added beside the donor's GPU view and
  chosen by an additive platform field.
- **FR-082**: The UI-to-server contract MUST be written down with schemas so that the Phase 2
  front end can target it.
- **FR-083**: The dashboard's page logic MUST be covered by tests that run without
  installing packages, and browser end-to-end scenarios MUST cover the chat core.

#### Conformance, governance and non-interference

- **FR-084**: The ledger MUST have exactly one row per donor test method (913 rows), each
  resolving to exactly one disposition from the closed set defined in
  `contracts/parity-ledger.md` section 3.2: `rust-test`, `scenario`, `web-test`, `shim`,
  `vendor-render`, `deviation` (an approved register entry), `not-applicable` (with a
  reason from a closed list) and `pending` (allowed only before close-out). `shim` and
  `vendor-render` rows are produced by the manual reference job, and the blocking checks
  verify their committed record. A checker MUST fail the build on a dangling reference.
- **FR-085**: The reference corpus MUST be captured from the donor's own server only in a
  manual job, and replayed against the Rust server offline in every blocking run.
- **FR-086**: Independent tests MUST be written from the contracts by a different author
  than the one that ported the behavior, and MUST include the security tests salvaged from
  PulsarMLX's archived serving crate.
- **FR-087**: Donor code MUST run only in the manual reference job; donor fakes are never
  executed locally, and no donor engine binary is launched.
- **FR-088**: The change set MUST touch only the allowlisted paths, MUST leave the root
  `Cargo.toml`, root `Cargo.lock` and `.github/workflows/macos.yml` byte-identical to
  their blobs at the merge base with `main`, MUST not place any tracked file under a path
  the repository's ignore rules silently drop, and MUST be checked mechanically before
  every commit and in automation.
- **FR-089**: Automation for this feature MUST be path-filtered, run on the pinned toolchain
  from the nested workspace, keep blocking jobs small (preflight, Rust on Linux, Rust on
  macOS arm64, web logic tests without packages), and keep reference capture, the live
  differential, the shim run of the two donor test files that run unchanged against the
  Rust artifacts, vendor-template checks, SDK client tests, the drift canary and browser
  end-to-end tests as manual jobs. The blocking checks verify the committed records of the
  shim run and the vendor-template checks; they do not run them.

#### Approved deviations from literal parity

- **FR-090 (SEC-1)**: On loopback binds the server MUST enforce a `Host` allowlist; MUST
  check `Origin` on every route, including `Origin: null`; MUST require a JSON content type
  on POST; and MUST require a loopback client or an API key for mutating admin routes.
  Behavior of the `Host` allowlist on non-loopback binds is open item OI-3.
- **FR-091 (SEC-2)**: The server MUST send a strict Content-Security-Policy and related
  security headers, MUST sanitize every HTML sink, and MUST run HTML previews in their own
  sandboxed route with network access off unless allowed for that preview.
- **FR-092 (SEC-3)**: Opening `/?q=<text>` MUST only prefill the composer; sending MUST need
  a keypress.
- **FR-093 (SEC-4)**: Image sources MUST accept `data:` URLs always, and remote URLs and local
  paths only when enabled in settings.
- **FR-094 (SEC-5)**: The update route shapes MUST be kept, the server MUST never fetch or run
  code to update itself, and the release check MUST be opt-in and only notify.
- **FR-095 (SEC-6)**: Client JSON keys beginning with `_` MUST be stripped at the API boundary,
  and internal flags MUST be typed and never read from client input.
- **FR-096 (SEC-7)**: The download command MUST NOT be overridable from the environment, and
  engine environment entries MUST pass a wider denylist for library and executable
  variables.
- **FR-097 (PRIV-1)**: Resumable answers MUST be kept in memory, disk persistence MUST be off
  by default, and the settings text MUST state what is stored.
- **FR-098 (BRAND-1)**: The product MUST be named "PulsarMLX Console", the binary
  `pulsar-console`, with the `PULSAR_CONSOLE_` prefix, neutral quant labels, no sponsor
  links and the published name table; legacy names MUST NOT be accepted.
- **FR-099 (BRAND-2)**: The dashboard MUST use letter tiles per model family, the system font
  stack and SVG icons only, with no vendor logos, font files or PNG icons committed;
  `/fonts/<name>` MUST answer 404, and the web manifest MUST list SVG icons only.
- **FR-100 (LIC-1)**: Vendor chat templates MUST load from the model directory at run time
  and never be committed; vendor-template checks MUST run only in the manual job and
  record hashes, not text.
- **FR-101 (LIC-2)**: The MiniMax picture preprocessor MUST NOT be built; its file format
  MUST be documented, and a MiniMax-vision engine MUST receive a clear error.
- **FR-102 (POL-1)**: The refusal-ablation capability flag MUST be recognized and refused
  unless an engine advertises it; the switch and its configuration keys MUST NOT be ported.
- **FR-103 (PLAT-1)**: NVIDIA, AMD and Windows readers and the multi-GPU helpers MUST be
  ported behind traits, tested with the donor's fixtures, type-checked for Linux and
  Windows in automation, labelled unverified on real hardware, and built last (M9).
- **FR-104 (PLAT-2)**: An Apple Silicon reader and a matching monitor view MUST be provided.
- **FR-105 (PLAT-3)**: `pulsar-console fetch` and `pulsar-console supervise` MUST replace the
  donor launcher's download and restart duties with the same progress, exit-code and
  restart contracts, and the catalog MUST ship empty.
- **FR-106 (FIX-1)**: The listed upstream defects MUST be fixed and each recorded in the
  register: context reload ends the engine by killing instead of quitting; concurrent
  writes to the engine pipe; an untagged stop in multi-conversation mode.
- **FR-107**: Any further difference found during implementation MUST be proposed as a new
  register entry and MUST NOT be relied on until the owner approves it.

#### Provenance and licensing

- **FR-108 (PLAN-4)**: Adapted and translated files MUST carry a provenance header naming
  the donor file and commit; the donor's full MIT text with both copyright lines, the
  Preact MIT and htm Apache-2.0 texts and the Lucide ISC notice MUST ship in
  `console/LICENSES/` and be served from the dashboard's About page; `NOTICE.md` MUST gain
  the matching section.
- **FR-109**: project-maya MUST be named as the donor wherever attribution or provenance
  requires it, and MUST NOT appear as product identity.
- **FR-110**: Every new third-party dependency MUST be pinned exactly and recorded with its
  license in `research.md`.

### Key Entities

- **Run Config**: A `pulsar-<name>.json` document describing one installed model setup:
  engine arguments, engine `env` block, sampling and thinking settings, port, API keys,
  CORS origins and installer state; its modification time decides recency.
- **Request and Turn**: One client request in one dialect, its normalized messages, typed
  run options, cancel signal, queue place and the turn that drives the engine.
- **Engine**: A backend behind the seam, with capability flags, facts (context size,
  information keys, statistics, version) and lifecycle operations.
- **Engine Event**: A token with optional logprobs, prompt progress, a heartbeat, or the
  single terminal record with figures and finish reason.
- **Queue Place**: A unit of engine capacity held by a request or by exclusive work in
  arrival order.
- **Resumable Answer**: A web-chat answer kept for replay by id and cursor, in memory by
  default.
- **Stored Response and Background Job**: A Responses API result scoped to a credential,
  and a queued or running job with a bounded event history and one terminal state.
- **MCP Server and Tool**: A configured tool server, its transport and status, and the tools
  it offers.
- **Attachment**: An uploaded or inline document with its extracted text and pictures.
- **Media Source**: An image or video given as a `data:` URL, remote URL or local path, with
  the policy that admits it.
- **Model Entry and Settings Profile**: An installed model's classification, quant label,
  context range and editable engine settings.
- **Switch and Delete Notes**: Short-lived `.pulsar-*` files through which the server and
  supervisor agree on restarts and deferred deletes.
- **Catalog Entry**: A downloadable model description with files, sizes and checksums (none
  ship in this increment).
- **Savings Ledger**: Token counts and reference costs per model.
- **Telemetry Snapshot**: Host figures for the monitor, with unavailable fields null.
- **Ledger Row**: One donor test method keyed by file, class and method, with exactly one
  disposition and its references.
- **Deviation Entry**: An id, the donor behavior, the PulsarMLX behavior, the reason and the
  owner's approval.
- **Reference Recording**: A normalized capture of the donor's behavior for one scenario,
  with a provenance header.
- **Name Mapping**: One row of the name table mapping a donor name to its PulsarMLX name.

## Scope Boundaries

### Out of Scope

- Serving any real model, and attaching any real engine (Phase 3, separately approved).
- Launching `maya-metal` or any other project-maya engine binary, which would need its own
  ADR 0004 qualification.
- The Phase 2 front end: the complete rewrite in Rust and WebAssembly. It is a roadmap
  item only.
- The donor's launcher and setup (setup, compile, calibration, report and bench duties);
  only the download and restart contracts are rebuilt (PLAT-3).
- The MiniMax picture preprocessor (LIC-2).
- The refusal-ablation switch and its configuration keys (POL-1).
- Self-update (SEC-5: route shapes only).
- Any real model catalog entry.
- Committing vendor chat templates, vendor logos, font files or any binary file.
- Any change to the root workspace, `crates/`, `experiments/`, `fixtures/`, `scripts/`,
  `docs/research/`, `.specify/`, `.gitignore`, the root Python project files or
  `.github/workflows/macos.yml`.
- Performance claims of any kind.

### Open Items

These are not decided by the plan recorded in ADR 0008. Each is recorded here so that no
requirement silently decides it; none blocks planning. The consolidated register of open
items, with stable ids and who decides each one, is
[`checklists/analysis.md`](checklists/analysis.md). This list repeats the items that bear on
this specification; the last column gives each item's register id.

| Id | Question | Affects | Register |
| --- | --- | --- | --- |
| OI-1 | Is the donor's sealed-reasoning prefix accepted on input? | FR-055, M5 | OPEN-01 |
| OI-2 | The exact default model name of the scripted engine (it must contain "synthetic"); until it is decided, the lead's working default is `pulsar-console-synthetic`. | FR-005, M1 | OPEN-03 |
| OI-3 | How the `Host` allowlist behaves when the server is bound to a non-loopback address. | FR-090, M1 | OPEN-04 |
| OI-4 | Whether `supervise` or plain serving is the documented default entry point. | FR-071, M7 | OPEN-05 |
| OI-5 | The default run-config directory when no configuration path is given, and whether an importer for project-maya run configs exists. When a configuration path is given, persisted files are resolved relative to its directory, as the donor does (a lead decision, applied in M1). | FR-044, M7 (before OPS-11) | OPEN-06 |
| OI-6 | Mapping of template rendering errors and DeepSeek encoder assertion failures to a status code, given the donor does not catch them. | FR-015, FR-019, M2 | OPEN-07 |
| OI-7 | Whether the donor's built-in savings price table ships verbatim or empty. | FR-072, M7 | OPEN-08 |
| OI-8 | Handling of an untagged engine error in multi-conversation mode, which the donor delivers to no request. | FR-033, M3 | OPEN-09 |
| OI-9 | Whether an engine start timeout is added; the donor waits indefinitely. | FR-037, M3 | OPEN-10 |
| OI-10 | Whether the GLM official chat template, which has no license text in the donor repository, may be fetched for vendor-template checks in the manual job. | FR-100, M10 | OPEN-11 |
| OI-11 | Whether small accessibility gaps the donor leaves open are fixed in Phase 1 or deferred to Phase 2. | FR-079, M8 | OPEN-12 |
| OI-12 | Whether this feature's summary check becomes a required check, and the merge order relative to engine branches; the plan defers both to the owner at merge time. | FR-089 | OPEN-13, OPEN-14 |
| OI-13 | Whether DeepSeek picture pixel values may differ from the donor's image library (proposal P-5 in the deviation register). | FR-066, M6 | OPEN-15 |

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every one of the 913 donor test methods has exactly one resolved ledger row,
  with zero dangling references at every milestone and zero pending rows at close-out.
- **SC-002**: Every route and method in the route inventory has at least one recorded
  scenario, and every stream format has both a streamed and a non-streamed scenario.
- **SC-003**: Replaying the committed reference corpus against the implementation yields
  equal normalized observations for 100% of scenarios, except differences annotated with
  an approved deviation id.
- **SC-004**: No file outside the allowlist changes, the three hash-bound root files are
  byte-identical to their blobs at the merge base with `main`, and the boundary check
  passes on every commit.
- **SC-005**: A streamed completion can be cancelled by disconnecting: the engine receives a
  stop, the queue place is freed after the drain, and a waiting request starts, with zero
  leaked places across the whole test suite.
- **SC-006**: 100% of routes refuse a foreign `Host` on a loopback bind, a foreign or `null`
  `Origin`, and a POST without the content type the route requires, as shown by a
  table-driven test over the full route inventory.
- **SC-007**: Every dashboard screen and the health response identify the backend as
  synthetic, and no committed document describes a real model as served.
- **SC-008**: Every entry outside the register's proposed section is approved, referenced
  by at least one test or ledger row, and every difference in the corpus maps to a register
  entry; unused entries are zero.
- **SC-009**: Killing a fake engine mid-answer produces the donor's 503 or error tail, and
  the next request succeeds after a restart.
- **SC-010**: A termination signal during an answer produces the donor's wrap, stop and quit
  order and exit code 0; a second interrupt exits 130.
- **SC-011**: The scripted engine, the line-protocol engine with the fake engine binaries,
  and the coordinator-shaped adapter all pass the engine conformance suite with no change
  to the driver.
- **SC-012**: Zero binary files, zero credential-shaped strings, zero silently ignored
  tracked paths and zero AI-attribution lines appear in the feature's change set.
- **SC-013**: The blocking automated checks pass on Linux and on macOS arm64 on the pinned
  toolchain, and none of them executes donor code or installs unpinned packages.
- **SC-014**: Every hardware-specific reader passes its fixtures, type-checks for Linux and
  Windows, and is labelled unverified on real hardware wherever it is mentioned.
- **SC-015**: The About page serves every required license text, and every adapted or
  translated file carries a provenance header.
- **SC-016**: When the manual SDK job is run, the official OpenAI and Anthropic Python
  clients parse 100% of the streamed and non-streamed outputs in its scenarios; until it is
  run, no such claim is made.
- **SC-017**: Every new third-party dependency is pinned exactly and recorded with its
  license.

## Assumptions

- The owner's decisions are those recorded in ADR 0008, which records the plan the owner
  approved on 2026-11-14 (that plan is not published); this specification restates them
  and adds none.
- The donor is pinned at `7e68a30f`; re-pinning is a separate decision. The donor's
  `serve/` is about 19,800 lines of Python with 44 test files and 913 test methods.
- The size estimate of about 125 work packages plus six for governance is soft and may be
  off by a wide margin.
- Apple Silicon on macOS is the primary platform; Linux is used for most automated checks;
  Windows is type-checked only.
- The pinned Rust toolchain is 1.97.1, in a standalone nested workspace under `console/`
  that does not depend on anything outside it.
- The system `curl` is available wherever outbound network access is used.
- Node.js is available as a test tool for the dashboard's page logic, with no packages
  installed.
- The manual reference job can fetch the donor at the pinned commit and verify it by SHA and
  a file-hash manifest.
- The archived PulsarMLX serving crate at tag `archive/2026-09-21/feat/openai-serving`
  (`crates/serve-synthetic`) is available as the reference for `Host`, `Origin`, content-type
  and token handling and its raw-HTTP tests; it is superseded as a merge candidate.
- The seam's at-least-once delivery rule reflects how the engine track's post-commit
  delivery hook behaves after a refused delivery; the seam contract is reviewed by the engine
  track before it is frozen.
- Generated test data is built in code, under directories named `testdata/` or `tests/data/`.

## Constitution Compliance

The full check, principle by principle, and the six recorded exceptions (E1 to E6) are in
[plan.md](plan.md), sections "Constitution Check" and "Constitution Exceptions". In short:

- I. Correctness before optimization: every behavior is checked against the pinned donor's
  recorded behavior and re-expressed tests; no performance work is in scope.
- II. Preserve upstream Linux and CUDA behavior: nothing under `crates/` changes, and the
  boundary check enforces the no-touch list (FR-088).
- III. Verified claims only: every capability is planned, backends are synthetic, and the
  strongest later claim is "qualified on synthetic backends" (FR-003, FR-004, FR-006).
- IV. Apple Silicon is a first-class backend: macOS arm64 is the primary platform, with an
  Apple Silicon reader and monitor view (FR-076, FR-104).
- V. Portable interfaces: the backend seam uses explicit capability flags, and unsupported
  operations fail clearly (FR-016, FR-027, FR-101, FR-102).
- VI. MLX reference before custom Metal: not engaged; this feature has no MLX or Metal code.
- VII. Reproducible benchmarks: no performance claim is made, and no donor benchmark is
  PulsarMLX evidence.
- VIII. Explicit model compatibility: no real model is served, and the catalog ships empty
  (FR-070).
- IX. Clean licensing and attribution: the donor is qualified under ADR 0004, with
  benefit recorded as a pre-adoption estimate and measured at close-out (exception E6,
  which awaits the owner's decision, OPEN-27),
  and provenance headers and license texts are required (FR-108, FR-109).
- X. Incremental, test-backed commits: one work package per commit series, each with its
  ledger rows resolved.
- XI. No secrets or model weights: the hygiene check runs before every commit and in
  automation (FR-088, SC-012).
- XII. Documentation is part of the implementation: contracts, ledger rows and the
  deviation register change in the same commit as the behavior they describe.

The spec, plan and tasks are written by hand from the templates (exception E4), and a
recorded cross-artifact analysis replaces the analyze command (exception E5).
