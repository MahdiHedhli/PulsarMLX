# Data Model: PulsarMLX Console Serving Parity

**Date**: 2026-11-14

**Status**: Planned. No entity below is implemented. Fields and invariants are taken from
the work-package records of 2026-11-14 (planning records that are not in the repository;
their content is restated per package in [tasks.md](tasks.md) and `tasks/`), which read
project-maya at commit `7e68a30f`; the package named in each section owns the final
definition and records it in its contract document. Where the donor's behavior and this
model differ, the difference is an approved deviation (named inline, including the `P-`
proposals the owner approved on 2026-11-14), a proposal still awaiting the owner (marked
"proposed"), or an open item. Open items are listed with stable `OPEN-`
ids in the register in [checklists/analysis.md](checklists/analysis.md). References such
as B3 or B10 are the binding cross-cutting decisions in
[tasks.md](tasks.md#binding-cross-cutting-decisions). Names on the wire
follow the donor except where [contracts/naming.md](contracts/naming.md) renames them.
The engine-facing entities (descriptor, generation request, engine events, event ledger,
terminal record, event level) are defined normatively in
[contracts/backend-seam.md](contracts/backend-seam.md); the sections below summarize them
with the same names, and the contract wins where they differ.

The feature has no database. Entities are Rust types, JSON documents on the wire, files in
a configuration directory outside the repository, and text files tracked in the
repository. Everything written as JSON goes through the one Python-compatible writer in
`console-pyjson` (B3).

## Relationships

```text
HTTP request (OpenAI | Anthropic | Responses | web)
      |
      v
RequestOptions --> ResolvedSampling --> Sampling --------+
      |                                                 |
      v                                                 v
prepared prompt ids ------------------------> GenerationRequest --> engine (EngineDescriptor)
                                                                 |
                              EngineEvent (Admitted, PromptProgress, Token, Sample, Note)
                                                                 |
                                         EventLedger (at least once, keyed by position)
                                                                 |
                                                                 v
                    Terminal (engine) --> output pipeline --> TurnEvent ... TurnTerminal
                                                                 |
                      +------------------------+-----------------+-----------------+
                      v                        v                 v                 v
                 Usage (per dialect)   ResponseObject   Monitor history row   SavingsLedger
                                         |      |
                                 StoreEntry   BackgroundJob

RunConfig ---> EngineDescriptor, McpServer list, SavingsLedger path, NoteFiles
ModelRegistryEntry <--- RunConfig files;  CatalogManifest ---> fetch ---> RunConfig
ParityLedgerRow ---> (Rust test | ConformanceScenario | web test | shim | vendor render
                      | DeviationEntry | N/A)
ConformanceScenario ---> RecordedReference (captured from the donor in the manual job)
```

## Persisted Files

No file below exists yet. "Runtime" files are written by `pulsar-console` into the
configuration directory (the directory of the run config passed with `--config`, as the
donor does; the default when no config is given is OPEN-06) or another location outside
the repository; none of them is tracked in Git. "Repository"
files are tracked text files.

| File | Kind | Location | Writer | Format and rules |
| --- | --- | --- | --- | --- |
| `pulsar-<NAME>.json` | Runtime | Configuration directory | API-15 (store), with edits from API-13, OPS-05, OPS-06, OPS-10 | Run config document. Python `indent=1`, `ensure_ascii`; written to `<name>.tmp` then renamed. |
| `pulsar-<NAME>.json.prev` (donor `CONFIG.prev`) | Runtime | Beside the run config | API-15 store, on saves from the Models page (OPS-05) | Previous whole document, written non-atomically as in the donor. |
| `<STEM>.shared-settings.json` | Runtime | Beside the run config | API-13 | Shared chat defaults; `indent=1`; deleted when empty. Excluded from run-config listing. |
| `.pulsar-switch.json` | Runtime | Configuration directory | OPS-10 | Note to the supervisor: config to start next. Compact JSON. |
| `.pulsar-delete.json` | Runtime | Configuration directory | OPS-09 | Note to the next process: delete this config. Compact JSON; honored only when under 900 s old. |
| `.pulsar-verified.json` | Runtime | Inside a model folder | OPS-16 (`fetch`) | Files whose SHA-256 matched, by size and modification time. |
| `answers/<id>.jsonl` | Runtime, **off by default** (PRIV-1) | Beside the run config | API-10 | Resumable web-chat answer, one wire chunk per line, last line a done marker. Written only if disk persistence is enabled; whether and how it can be enabled is OPEN-19. |
| `token-savings.json` | Runtime | Beside the run config, or the path in the savings variable | OPS-21 | Savings ledger; whole document rewritten through a temporary file and rename after each add. |
| Server log | Runtime | Path from the server-log variable | API-16 | Plain text with the `[console]` prefix. Never tracked (`*.log` is ignored). |
| `run-<STEM>.sh`, `run-<STEM>.bat` | Runtime | Beside the run config | API-13 (port route), OPS-09 (delete) | Donor launcher scripts that the donor's port route rewrites and delete removes; whether the console creates or only maintains them is OPEN-55, fixed by those packages. |
| Vision and picture files (SVE1, DSI1) | Runtime, transient | Temporary directory under a whitespace-free base; the server refuses to start if none exists (P-7, approved by the owner on 2026-11-14) | ENG-14, RSP-19 (the one fake vision encoder used in tests is in `console-fake-engines`, ENG-14) | Per-request embeddings and pixel files owned by the request task. |
| `console/parity/ledger.json` | Repository | `console/parity/` | GOV-06 (skeleton), every package | Parity ledger, one row per donor test method. |
| `specs/022-console-serving-parity/contracts/deviations.md` | Repository | Feature contracts | GOV-06, packages adding deviations | Deviation register. |
| Conformance scenarios | Repository | `console/conformance/` | CNF-02, CNF-18 to CNF-20 | Scenario JSON validated by a schema. |
| Recorded references | Repository | `console/conformance/` | CNF-09 (manual capture job) | Normalized donor observations with a provenance header; never edited by hand. |
| Oracle pin manifest | Repository | `console/conformance/` | CNF-08 | Donor commit SHA and file-hash manifest used by the manual job. |
| Catalog manifest | Repository | `console/crates/console-manage/catalog/` | OPS-14 | Production manifest with zero entries (B10); synthetic entries only in test data. |

Exact subdirectory and file names under `console/conformance/` are fixed by CNF-02 and
CNF-09. Every tracked path avoids the `.gitignore` traps and test data lives under
`testdata/` or `tests/data/` (B13).

## RequestOptions and ResolvedSampling

Owner: API-04 (validation and defaults), ENG-03 (typed parameters and key encoding). A
typed view over the request's order-preserving JSON map.

| Field | Type | Validation and rules |
| --- | --- | --- |
| `temperature`, `top_p`, `min_p` | number | Number, or a non-blank numeric string parsed with Python `float()` rules. NaN, infinity and booleans give 400 `<field>: a number`. |
| `presence_penalty`, `frequency_penalty`, `repetition_penalty` | number | As above. `repeat_penalty` is copied to `repetition_penalty` when that is absent. |
| `top_k`, `penalty_last_n`, `seed` | integer | Integer or integral numeric string; a JSON float such as `40.0` gives 400 `<field>: an integer`. `repeat_last_n` aliases `penalty_last_n`; below -1 is an error. |
| `stop` / `stop_sequences` | string or list | First 16 non-empty strings kept. |
| max tokens | integer | OpenAI: `max_completion_tokens`, else `max_tokens`; Anthropic: `max_tokens`. Zero or negative means the rest of the context. |
| `logit_bias` | object | Digit-string keys below the vocabulary size and at most 2^31-1; biases -100..100; cannot ban the whole vocabulary; needs the engine's logit-bias capability. |
| `logprobs`, `top_logprobs` | bool, 0..20 | `top_logprobs` only with `logprobs`; needs the engine's log-probability capacity. |
| `loop_guard`, `ignore_eos` | bool-like, bool | `ignore_eos` needs positive max tokens and the logit-bias capability. |
| `ablate` | bool | Recognized and refused unless an engine advertises the capability (POL-1); no config key is ported. |
| `strata_tune` | object | Tuning keys with ranges; out-of-range values are dropped silently, as in the donor. |

**Invariants**

- Every client key beginning with `_` is removed at the dialect boundary before any
  processing (SEC-6). Internal flags travel in a typed struct never filled from client
  JSON.
- Precedence: non-null request value, then shared settings, then the run config's
  `sampling` block (or built-in model defaults), then nothing.
- `ResolvedSampling` applies the semantic rules: temperature at or below 0 means greedy and
  suppresses `top_p`, `top_k`, `min_p` and `seed`; `top_p` only below 1; `top_k` of 0 or
  above 64 becomes 64; penalties only when non-neutral, with a window. It yields an ordered
  key list.
- `Sampling` (the engine-facing typed sampling of the generation request) is encoded to
  engine keys in a fixed order with Python `repr` float text by ENG-03; a default request
  encodes to an empty key string.
- Every validation failure is a 400 with the donor's message (rebranded where it names the
  donor), sent before the engine sees anything.

## Engine Events, Turn Events and the Terminal Records

Owner: [contracts/backend-seam.md](contracts/backend-seam.md) sections 7, 9 and 12;
ENG-01 (types), PRM-09 (parser events), PRM-12 (pipeline). Two levels.

**Token level: `EngineEvent`**, delivered by an engine to the server's sink, in this order
per `generate` call: `Admitted` exactly once (its `prompt_tokens` equals the prompt
length), then any number of `PromptProgress { read, total, reused, ms, tok_s }`,
`Sample` (telemetry such as statistics, VRAM and residency) and `Note` (bounded text,
logged and never shown), and `Token(CommittedToken)` events in index order from 0. A
`CommittedToken` has `index` (ordinal among this call's tokens), `position` (absolute
position in the engine's sequence), `id` and an optional `logprob` with its alternatives.
Keep-alives are not engine events; the server emits them after a quiet interval.

**Engine terminal: `Terminal`**, the return value of `generate`, so a second terminal is
impossible at this level.

| Field | Type | Notes |
| --- | --- | --- |
| `stop` | `EngineStop` | `Stop { token }`, `Length`, `Cancelled`, `Paused` |
| `counts` | optional `EngineCounts` | `generated`, `prompt_tokens`, optional `reused_tokens`, optional drafts (accepted, offered), optional hits and lookups; keeps the donor's 5-, 8- and 10-field `DONE` forms apart; none for an engine without a `DONE` line |
| `timings` | optional `EngineTimings` | `prompt_ms`, `decode_ms`; none for an engine without a clock |

**Event level: `TurnEvent`**: `Reasoning(text)`, `Content(text)`, `ToolCall(delta)` (index,
id, name, argument text), `Progress`, `Ping`, and `Terminal(TurnTerminal)` exactly once and
last. `TurnTerminal` carries `finish`, `usage`, optional llama.cpp-style `timings` and an
optional error.

**Parser events** (inside the output pipeline, PRM-09 and PRM-12): `kind` (`reasoning`,
`content`, `tool_start`, `tool_args`, `tool_call`, `tool_incomplete`), `text`, `call`
(`{ name, arguments (ordered object), id, namespace }`), `complete` (false for a
malformed or truncated call) and `logprobs` (entries that ride on the next text event).
The pipeline's done record carries `finish` (`stop`, `length`, `cancel`, `error`,
`disconnect`), `completion_tokens`, `reasoning_tokens`, `reused`, `timings` and
`stop_sequence` (only when `finish` is `stop` and a client string matched). MCP tool-loop
items (`strata_mcp`) ride on the same stream.

**Invariants**

- Exactly one terminal per turn on every path, including cancel, disconnect, failure and
  engine death; nothing follows it.
- Figures are returned per call, never left in shared mutable state.
- The concatenated `Content` text equals the non-streamed answer text; the same holds for
  `Reasoning`.
- For every split of the engine's text into chunks, the parser's event sequence (adjacent
  text merged) equals the whole-text parse, and a partial tag (`<tool_`, `</thi`) never
  leaks into emitted text.

## Usage

Owner: [contracts/backend-seam.md](contracts/backend-seam.md) section 9; API-08, API-09,
RSP-04. One source, three shapes. Usage comes only from what the backend committed and
reported, never estimated from text.

| Dialect | Shape |
| --- | --- |
| OpenAI Chat | `{ prompt_tokens, completion_tokens, total_tokens, prompt_tokens_details: { cached_tokens } }`, always on the final chunk, plus `timings` when present |
| Anthropic Messages | `message_start`: `{ input_tokens: prompt length, output_tokens: 0 }`; `message_delta`: `{ input_tokens: prompt minus reused, cache_read_input_tokens: reused, output_tokens }` |
| Responses | `{ input_tokens, output_tokens, total_tokens, input_tokens_details: { cached_tokens, cache_write_tokens: 0 }, output_tokens_details: { reasoning_tokens } }` |

**Invariants**: `prompt_tokens` on the wire is the length of the prompt ids sent; cached
tokens come from the engine's counts or progress and are never inferred; `reused` is
clamped to the prompt length; `total = input + output`; sums use checked arithmetic, and a
terminal whose counts contradict what the event ledger accepted is a protocol failure.
How `completion_tokens` relates to the engine's own `generated` figure is an open question
in the seam contract (Q4, part of OPEN-30).

## EngineDescriptor and Capabilities

Owner: [contracts/backend-seam.md](contracts/backend-seam.md) section 5; ENG-01 (types),
ENG-04 and ENG-06 (handshake), ENG-15 (launch specification).

**EngineDescriptor**

| Field | Notes |
| --- | --- |
| `seam` | Seam contract version |
| `kind` | `Scripted`, `LineProtocol`, `CoordinatorAdapter`, `RuntimeAdapter` |
| `provenance` | What the engine reports. The type can also express "not synthetic": an engine that declares another provenance, or declares none (lead decision LD28; ENG-01 settles the exact shape). `Synthetic` is the only value the server accepts in this increment |
| `version` | From the engine's `INFO`, else a build manifest |
| `max_context` | From `READY`; 0 means not ready (503 "the model is starting") |
| `vocab_size` | When known, the event ledger checks token ids against it |
| `caps` | `EngineCaps`, below |
| `info` | Every `INFO` fact in arrival order; a value that is an optional minus sign followed by digits is an integer, anything else stays a string |
| `facts` | `model_path`, `log_path`, `load_s`, for monitoring only |

**EngineCaps**: `stop`, `pause` (from `READY`); `multi` (present when `READY` carries
`multi`, including `multi=1`; `places() = max(1, multi)`); `logit_bias`; `logprobs_max`;
`vision` (`Absent`, `Off`, `Ds4`, `Mm3`; `Mm3` pictures get a clear error under LIC-2);
`ablate` (requests are refused without it, POL-1); `lifecycle` (`set_context`, `restart`,
`unload`, `lend`). A request that needs a capability the descriptor does not advertise is
refused with the donor's 400 before anything reaches the engine.

**Launch specification** (line-protocol engines): executable, arguments and child
environment built from the run config. Run-config `env` entries not named in the server's
own list pass to the child verbatim as opaque data (B2); the environment guard refuses
library- and executable-injection variables (SEC-7). An optional ready timeout bounds the
wait for `READY`; it is off by default, so by default the server waits as the donor does
(P-6, approved by the owner on 2026-11-14).

**Invariants**: no project-maya engine binary is ever launched (B10); in this increment
every engine is synthetic, and `/health` and the dashboard say so. The scripted engine's
default model name is exactly `pulsar-console-synthetic` (PLAN-2; the owner decided the
name on 2026-11-14, OPEN-03). The server refuses to start an engine that does not report
synthetic provenance (decided by the owner on 2026-11-14, OPEN-29): one guard function in
`console-core` decides, and every path that admits an engine (first start, restart, model
switch, context reload) calls it before the engine serves a request; no environment
variable, configuration key, command-line flag or Cargo feature bypasses it in this
increment (lead decision LD28). At process start a refusal makes `pulsar-console` exit
with a non-zero status after one line on standard error that names the engine kind, what
the engine reported, and the path `docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md`; at a
later restart, switch or reload the engine is closed, the operation fails with the same
message, and nothing is served from that engine. A line-protocol engine that does
not declare synthetic provenance in its start-up lines counts as not synthetic (the form
of the declaration is open item OPEN-58). What must be done before such an engine may be allowed is in
[ALLOWING_NON_SYNTHETIC_ENGINES.md](../../docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md).

## GenerationRequest, Committed Token and the Event Ledger

Owner: [contracts/backend-seam.md](contracts/backend-seam.md) sections 6, 7 and 7.1; ENG-01,
ENG-19 (runtime adapter and post-commit sink).

**GenerationRequest**: `rid` (assigned by the server, unique and increasing across engine
restarts), `prompt` (the whole prompt as token ids, every time), `max_new` (after the
context rule), `sampling`, `stop_ids` (an early-stop hint the server re-checks),
`logprobs`, `thinking` hints, `restore` hints, `tune` (validated `strata_tune` knobs),
`projection`, `ablate` (always false unless the engine advertises it), `embeddings`. No
field is filled from a client JSON key.

**Delivery**: the engine hands each `EngineEvent` to the server's sink, which answers
accepted, `Backpressure` (offer the same event again; never skip it) or `ConsumerGone`
(stop at the next step and return `Cancelled`).

**EventLedger** (one per call, shared logic for every engine kind): next index, last
accepted token, `position0` (fixed by the first accepted token; positions are assigned as
prompt length plus index for engines that do not track them).

**Invariants**

- Delivery is at least once and keyed by position. A token with `index == next` (and the
  matching position) is accepted. A token identical to the most recently accepted one is a
  replay and is dropped. Any other `index < next` (a rewind, or a changed id at a committed
  position) and any `index > next` (a gap) are protocol failures, as are tokens before
  `Admitted`, a second `Admitted`, an index at or beyond `max_new`, and log probabilities
  that were not asked for. An id beyond a known vocabulary is an invalid-token failure.
- A token is handed to the sink only after the engine has committed it and is never
  rewound or recomputed. A refused delivery never turns a committed step into a failure;
  this matches the engine track's post-commit `deliver` hook, which replays the retained
  step after a refused delivery.
- The scheduler place is released only after `generate` has returned on the driver thread.
- A runtime panic becomes an engine death, and the next request recreates the engine (the
  restart).

## RunConfig Document and Note Files

Owner: API-15 (store and environment settings), OPS-02 (sources and precedence), OPS-05 and
OPS-10 (edits), OPS-09 and OPS-10 (notes).

**RunConfig**: a JSON object loaded as UTF-8 with an optional byte-order mark, kept as an
order-preserving map so unknown keys survive every rewrite in their original order. Typed
accessors cover, among others: `exe`, `args`, `env`, `gpu`, `backend` (absent means the
donor's default), `installer.*`, `vision`, `vision_off`, `turbo`, `sampling`, `port`,
`host`, `api_key`, `model_management`, `cors_origins`, `fit_max_tokens`, `idle_unload_s`,
`mcp_servers` and `mcpServers`, plus the console's own optional `allowed_hosts` (SEC-1.1,
decided by the owner on 2026-11-14). The refusal-ablation keys are not ported (POL-1). The
full key table with old and new names is part of the naming contract.

**Invariants**

- An unreadable, invalid or non-object file reads as an empty map, never an error.
- Every edit goes through one writer: mutate, write `<name>.tmp` with Python `indent=1` and
  `ensure_ascii`, rename. An untouched document is rewritten byte-identical.
- Precedence: `api_key` from the command line, then environment, then config;
  `model_management` and `loop_guard` from a non-blank environment variable, else config;
  `host` from the command line, else config, else `127.0.0.1`.
- `cors_origins` is none, empty, or a list of non-blank strings with trailing `/` removed;
  anything else aborts start-up with the donor's message.
- `allowed_hosts` is absent by default. On a loopback bind a request passes only if its
  `Host` is a loopback name (`localhost`, `127.0.0.1`, `[::1]`, any port) or a listed
  name; on a non-loopback bind `Host` is not restricted unless the key is set, and then
  only the listed names and the loopback names pass. A refused request gets 403
  `permission_error`. Matching details (case, port, IPv6 forms, a missing `Host` header)
  follow the archived serving crate (B8) and are settled by API-03.
- Environment values whose name matches key, token, secret or password are returned as
  `***` in every outward copy; submitting `***` keeps the stored value.
- Server settings use the `PULSAR_CONSOLE_` prefix; legacy `MAYA_*` and `STRATA_*` names
  are not read (B2).

**Note files**

| File | Fields | Rules |
| --- | --- | --- |
| `.pulsar-switch.json` | `config` (path), `port`, `why` (`switch` or `settings`), `time` | Written before exit code 76; the supervisor starts that config next. |
| `.pulsar-delete.json` | `config`, `files`, `time`, `model`, `quant` | Honored at the next start only when under 900 s old, in this folder, and not the running model. |
| `.pulsar-verified.json` | per file name: `size`, `mtime_ns` | Files are not re-hashed while size and modification time are unchanged. |

## ResponseObject, StoreEntry and BackgroundJob

Owner: RSP-04 (object and events), RSP-01 (store), RSP-05 (jobs).

**ResponseObject**

| Field | Notes |
| --- | --- |
| `id` | `resp_` plus 24 hex characters |
| `object`, `created_at` | `response`; integer seconds |
| `status` | `queued`, `in_progress`, `completed`, `incomplete`, `failed`, `cancelled` |
| `error`, `incomplete_details` | Null, or `{ code: server_error, message }`; null, or `{ reason: max_output_tokens }` |
| `model`, `instructions`, `max_output_tokens`, `tools`, `tool_choice`, `parallel_tool_calls`, `reasoning` | Echoed; tools echoed unchanged, including types left out of the prompt |
| `output` | Items: reasoning (`rs_`), message (`msg_`), function call (`fc_`), one open at a time |
| `usage` | Responses usage shape |

Encrypted reasoning, when requested, is the product's sealed prefix plus base64 text: an
opaque wrapper, not encryption. Whether the donor's prefix is accepted on input is open
(OPEN-01).

**StoreEntry**: key `(owner, response_id)`, where `owner` is `public` with no API key
configured, otherwise the lowercase hex SHA-256 of the presented key. Items are canonical
JSON (sorted keys, compact separators, no NaN), stored once per owner under their SHA-256
with a reference count; a snapshot is the metadata bytes plus input and output block
references. TTL is fixed at write time.

**Invariants (store)**: another owner's id is indistinguishable from a missing one (404);
every eviction is planned before anything is mutated; an impossible write fails with the
donor's message and leaves existing snapshots intact; deleting an ancestor never breaks a
descendant; statistics are aggregate only, with no owner or content.

**BackgroundJob**

| Field | Notes |
| --- | --- |
| `owner`, `id` | As for the store |
| `state` | `queued`, then `in_progress`, then exactly one terminal state |
| `deadline` | One deadline from submission, queue time included |
| `events` | Ring bounded by event count and event bytes; renumbered per job |
| `snapshot` | Latest response object; keeps the original `created_at` |
| readers | Bounded overall and per owner |

**Invariants (jobs)**: exactly one terminal state, decided under one lock (completion,
cancel and deadline race; the first to commit wins). Cancel is idempotent; a queued job
cancelled never starts. A reader disconnect never cancels the job. A cursor that fell out
of the ring gives 410; one beyond the latest event gives 400. Preparation and generation
run in the same task, which owns any per-request files. Limits come from the environment
with the donor's defaults and bounds under the product prefix; a bad value aborts start-up
naming the variable.

## McpServer and McpTool

Owner: RSP-09 (configuration, transports, hub), RSP-10 (HTTP transport), RSP-11 (tool loop).

**McpServer**

| Field | Notes |
| --- | --- |
| `name` | From the config entry |
| `transport` | `stdio` (`command`, `args`, `env`, `cwd`) or HTTP (`url`, `headers`); `type: sse` is refused with the donor's message |
| `disabled` | Skips the entry |
| `status` | `idle`, `starting`, then `ready` or `failed`; `ready` becomes `stopped` when it ends |
| `info` | `name`, `title`, `version`, `protocol` from the handshake |
| stderr ring | Last 40 lines, for error messages |

Sources: the run config's `mcp_servers` and `mcpServers`, and a separate MCP config file
whose entries win a name clash. MCP config files in tests are never named `mcp.json`
(ignored by Git).

**McpTool**: routed name `clean(server) + "__" + clean(tool)` (characters outside
`A-Za-z0-9_-` become `_`, cut to 64 characters, collisions numbered), description,
parameters (the input schema if it is an object, otherwise an empty object schema).

**Invariants**: only ready or stopped servers route; a request's own tool of the same name
wins; a failed server is retried at most every 10 s; on timeout or cancel a cancellation
notification is sent; a stdio server runs in its own process group and is closed by stdin
close, then SIGTERM, then SIGKILL; result text longer than the limit is cut with the
donor's marker. Outbound HTTP uses the `curl` facade (B7) in `console-core` (module
`outbound`); HTTPS MCP through it is registered as PLAN-6.

## AttachmentResult

Owner: RSP-12 (readers), RSP-15 (PDF orchestrator), RSP-16 (file parts and routes).

Exactly one of:

| Variant | Fields |
| --- | --- |
| Text | `kind: text`, `text`, `format`, `truncated`, optional `note`, optional `pages` |
| Images | `kind: images`, `format`, `pages`, `images: [{ name, data }]`, optional `note` |
| Error | `error: { message }` |

**Invariants**: unreadable content never panics or propagates; detection is by content
(PDF header, ZIP member presence in the donor's order, text sniffing), not by file name
alone; ZIP inflation stops at a per-member and a cumulative cap; XML never resolves
external entities; text is cut at the model's text limit in code points with the donor's
note; message prefixes match the donor exactly; the detail text in parentheses comes from
the Rust reader (P-4, approved by the owner on 2026-11-14).

## ModelRegistryEntry and CatalogManifest

Owner: OPS-03 (classification), OPS-07 (listing), OPS-14 (catalog), OPS-16 (fetch).

**ModelRegistryEntry** (derived from each run config file in the configuration
directory, newest first)

| Field | Notes |
| --- | --- |
| `file` | `pulsar-<NAME>.json`; must match the prefix, must not be a shared-settings file, must exist |
| `family` | Donor families, plus `pulsar-mlx` for MLX safetensors checkpoints and `synthetic` for the synthetic backend |
| `quant_label` | From a data-driven table with neutral labels (BRAND-1) |
| `missing` | Reason the model cannot start, or none. An MLX backend config is listed with "no engine for this backend in this build" (P-15, approved by the owner on 2026-11-14) |
| `context_range` | `{ min, max, trained, tested }` |
| checkpoint descriptor | For MLX checkpoints: neutral quantization label, shard count, total bytes; payloads never opened |

**CatalogManifest entry**: `id`, `family`, `name`, `group` (`primary` or `other`), `by`,
`note`, license, `format` (`gguf`, `exl3`, `mlx-safetensors`, `synthetic`), `repo`,
`revision` (a 40-hex commit, never a branch name), `files` (path to size and SHA-256 or
list of accepted SHA-256 values), offer rules, `gated`. Exact key spelling is fixed by
OPS-14.

**Invariants**: the production manifest has zero entries (B10); synthetic entries exist
only in test data. Probes read bounded headers only; truncated or corrupt files give no
result rather than an error. A download is accepted only when every file's size and
SHA-256 match an accepted value.

## SavingsLedger

Owner: OPS-21.

| Field | Notes |
| --- | --- |
| per model | Token counts by band (`base`, `peak`): input, cached, output |
| prices | Built-in reference table with an as-of date, plus custom overrides (`input`, `cached`, `output` from 0 to 1000; `peak` 1 to 10 where the built-in has one; `api` up to 40 characters) |
| start | Totals at server start, for `start_usd` |

**Invariants**: `reused` is clamped to the prompt length and fresh input is
`prompt - reused`; cost is the sum over bands of factor times per-million prices, rounded to
6 decimals in reports; unknown models are counted in tokens only; a write failure is logged
once and counting continues in memory; the ledger is flushed before a restart exit.
Whether the built-in table ships populated is OPEN-08.

## TelemetrySample

Owner: OPS-17 (sampler core), OPS-18 (Apple Silicon reader, PLAT-2), OPS-19 and OPS-20
(ported readers, PLAT-1).

| Field | Notes |
| --- | --- |
| `cpu` | Percent from tick deltas |
| `ram_used`, `ram_total` | Bytes; used is total minus available |
| `disk_read_mb`, `disk_write_mb` | MiB/s from counter deltas |
| `gpu_*` | Absent when no reader applies. On Apple Silicon: name, count 1, utilization and in-use memory as experimental fields, total equal to unified memory; temperature, power and PCIe stay null |
| extras | `tok_s`, `tok_s_mean`, `prefill_tok_s_mean` from the monitor |
| static | `gpu_name`, `gpu_count`, `cpu_name`, `cores`, `threads`, `unified_memory` (Apple, additive), platform |
| storage | `path`, `free`, `total` for the models folder's disk |

**Invariants**: any reader failure yields a missing value, never an error; telemetry runs
on its own thread and never stops the server; history rings hold 60 samples with floats
rounded to 2 decimals; readers other than Apple Silicon are fixture-verified and labelled
unverified on real hardware; conformance scenarios use a null sampler.

## ParityLedgerRow

Owner: GOV-06 (schema and skeleton), every package (its rows), CNF-12 (checker and
inventories). Stored in `console/parity/ledger.json`.

| Field | Notes |
| --- | --- |
| `id` | `file::Class::method`, listed by a static reading of the pinned source (`console/tools/list_donor_tests.py`, which parses the files as text and never executes donor code) |
| `file`, `class`, `method` | Provenance of the row (`class` is null for a module-level function; the 2026-11-14 listing found none) |
| `subsystem` | Console crate or area expected to own the evidence |
| `disposition` | Exactly one of `rust-test`, `scenario`, `web-test`, `shim`, `vendor-render`, `deviation`, `not-applicable`, or `pending` until resolved, and none may remain pending at close-out (section 3.2 of [contracts/parity-ledger.md](contracts/parity-ledger.md)). `shim` and `vendor-render` rows run only in the manual reference job; blocking CI checks their committed records |
| references (planned) | Test paths, scenario ids or a deviation id, depending on the disposition |
| reason (planned) | For not applicable: one value from a closed list |
| upstream status (planned) | Whether the method passes or is skipped in the donor's own CI baseline |

The skeleton written in M0 carries the first six fields with every row `pending`; the
planned fields and their exact names are fixed by the ledger schema in the feature
contracts.

**Invariants**: exactly 913 rows, one per donor method, no duplicates; every reference
resolves (test paths against the test list, scenario ids against the corpus, deviation ids
against the register); a dangling reference fails the build; no `pending` row remains at
M10.

## DeviationEntry

Owner: GOV-06 (register), packages that rely on a deviation. Stored in
`specs/022-console-serving-parity/contracts/deviations.md`.

| Field | Notes |
| --- | --- |
| `id` | One of the approved ids (SEC-1 to SEC-7, PRIV-1, BRAND-1, BRAND-2, LIC-1, LIC-2, POL-1, PLAT-1 to PLAT-3, FIX-1), one of PLAN-1 to PLAN-6 for differences the approved plan decides outside its deviation table, or a `P-` id: an owner-approved proposal keeps its `P-` id as its deviation id, and a later owner-approved deviation that was never a listed proposal takes the next free `P-` number; ids are never reused (OPEN-39, settled by lead decision LD29 on 2026-11-14) |
| donor behavior | What project-maya does at the pin, with source lines |
| console behavior | What PulsarMLX Console does instead |
| reason | Why literal parity is not kept |
| approval | The owner's approval and its date; the approved plan of 2026-11-14 for the listed ids, with the deciding plan section for PLAN-1 to PLAN-6; the owner's decision of 2026-11-14 for the approved proposals P-1 to P-4, P-6 to P-11 and P-13 to P-16 |
| affected rows and scenarios | Ledger keys and scenario annotations that cite it |
| tests | The tests that pin the console behavior |

**Invariants**: no deviation without owner approval (a proposal with a `P-` id is not a
deviation until the owner approves it; a declined proposal, such as P-12 or P-17, keeps
its id marked declined, and a deferred one, such as P-5 or P-18, stays a proposal); every
comparator annotation and every rename-map entry cites a deviation id; an unused
deviation entry is flagged.

## ConformanceScenario and RecordedReference

Owner: CNF-02 (format and schema), CNF-03 and CNF-04 (client, normalizer, comparator),
CNF-08 and CNF-09 (oracle driver, capture and replay), CNF-18 to CNF-20 (corpora).

**ConformanceScenario**

| Field | Notes |
| --- | --- |
| `id` | Stable scenario id cited by ledger rows |
| engine spec | Scripted (tokenizer, script, maximum context, `info`, delay) or line-protocol fake (arguments, environment) |
| template | A PulsarMLX-authored synthetic template; vendor templates only by hash reference in the manual job |
| steps | Requests, gates, disconnects, concurrent groups (ungated concurrency is forbidden by the schema) |
| substitution tokens | `{{loopback}}`, `{{port}}`, `{{tmp}}`, `{{key_short}}`, expanded at run time |
| annotations | Deviation ids for allowed differences |

**RecordedReference**

| Field | Notes |
| --- | --- |
| header | Donor commit and scenario SHA-256, with the donor's MIT attribution |
| HTTP | Status, allowlisted headers, body (JSON structure, SSE or NDJSON sequence) |
| engine tape | Every generate call's prompt ids, `max_new` and sampling map, or every line written to the fake engine |
| files | Persisted files under the data directory |
| logs | The contracted log lines |
| exit code | Process exit code and signal behavior |

**Invariants**: references are captured only by the manual job from the donor at the
pinned commit and are never edited by hand; volatile fields (ids, timestamps) are
normalized by a declared list; comparisons are exact except for that list; committed
scenarios and references contain no loopback host values, UUID-shaped ids or key values of
16 or more characters; fake engines are deterministic functions of scenario, prompt and
call index.
