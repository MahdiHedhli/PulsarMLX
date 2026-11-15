# Backend Seam Contract (draft 0.1)

- **Status**: Normative draft, version 0.1, dated 2026-11-14. Nothing described here is
  implemented. Work package ENG-01 turns this draft into code and freezes it as version
  1.0, after the draft has been offered to the engine track for review (plan section 12,
  "The seam does not fit the real engine"). Until then any section may change.
- **Revised**: 2026-11-14, to record the owner's decision on Q9 (sections 5, 5.1, 13 and
  14): the server refuses to start an engine that does not report synthetic provenance.
- **Feature**: `specs/022-console-serving-parity`
- **Written by**: GOV-06 (this draft); frozen by ENG-01; implemented by ENG-01, ENG-02,
  ENG-06, ENG-07, ENG-10, ENG-18 and ENG-19; the refusal at process start of section 5.1
  by API-08.
- **Claims**: When built, every engine behind this seam is synthetic. The strongest claim
  any of them can earn in this increment is "qualified on synthetic backends". No real
  model, no project-maya engine binary and no engine-track crate is attached through this
  seam in this increment.

The word MUST marks a rule the implementation and its tests enforce. SHOULD marks a
default that an engine may depart from with a stated reason.

"Decision B1" to "decision B13" are the binding cross-cutting decisions restated in
[`../tasks.md`](../tasks.md), section "Binding cross-cutting decisions". A "planner record"
is one of the per-area design proposals written before the plan was approved, and the
"panel proposal" is one of the alternative overall approaches proposed before the plan;
neither is in the repository, and neither is approved by being cited here.

## 1. Purpose and the two levels

The seam separates PulsarMLX Console's server from whatever produces tokens. It has two
levels, so that a future PulsarMLX engine can attach at whichever level it owns (plan
section 6):

| Level | What crosses it | Who implements it in this increment |
| --- | --- | --- |
| Token level | Token ids in, committed token ids out, plus side events, one terminal record or one failure | Every engine: the scripted in-process engine, the line-protocol child engine, the Rust fake engine binaries (through the line-protocol engine), and a test adapter shaped like the engine track's coordinator |
| Event level | Reasoning, content and tool events, and exactly one terminal event | Only the server's own output pipeline, built over the token level |

The token level is the level an engine implements. The event level is what the dialect
serializers (OpenAI, Anthropic, Responses, Ollama-shaped and llama.cpp-shaped routes)
consume. In this increment the event level is produced only by the server; it is named as
a seam so that a later engine which owns tokenization and parsing could attach there.
Whether such an engine may do so, and which server duties it would then take over, is a
Phase 3 question that needs its own approval (see open question Q10).

## 2. Primary sources

The draft is grounded in these sources. Line numbers refer to the stated revision.

| Source | Revision | What it contributes |
| --- | --- | --- |
| project-maya `serve/server.py:191-193` (class `Engine`, a `Protocol`) | `7e68a30f` | The donor's declared engine contract: `max_context` and `generate(ids, max_new, sampling, cancel)` yielding token ids |
| project-maya `serve/server.py:199-240` (class `MockEngine`) | `7e68a30f` | The scripted engine: one scripted token per step, the end-of-turn id appended, cancel checked before each step, `info = {"logit_bias": 1, "logprobs": TOP_LOGPROBS_MAX}` |
| project-maya `serve/server.py:881-1729` (class `StrataEngine`) | `7e68a30f` | The line-protocol engine: `READY <ctx> [stop] [pause] [multi=<n>]` and `INFO key=value` at start (`:925-939`); `GEN`/`GENI` request lines; `T`, `LP`, `PP`, `STAT`, `NOTE`, `DONE`, `ERR` reply lines (`:1358-1504`); `STOP`, `PAUSE [keep]`, `WRAP` control lines (`:1549-1555`, `:1678-1700`); the 5, 8 and 10 field `DONE` forms (`:1192-1199`) |
| project-maya `serve/server.py:412-428` (`EngineDied`, `ContextOverflow`), `:532-568` (`LpToken`, `parse_lp`) | `7e68a30f` | Failure classes and the logprob value shape |
| project-maya `serve/server.py:2489-2530` (`Service.check_request`) | `7e68a30f` | How `INFO logit_bias=1`, `INFO logprobs=<n>` and `INFO ablate=1` gate requests |
| project-maya `serve/server.py:4490-4510`, `:4712`, `:4905` | `7e68a30f` | Usage counting: every token taken from the engine is counted before the stop check; the prompt count is the length of the prompt ids |
| Planner record `engine-supervision-scheduling.json`, packages ENG-01 and ENG-19 | planning, 2026-11-14 | The trait, capability, facts and failure inventory, and the blocking runtime adapter |
| Panel proposal `engine-attachment-first.json`, section `backend_seam` | planning, 2026-11-14 | Descriptor, committed tokens with index and position, the event sink, the event ledger, the non-`Send` engine instance owned by a driver thread |
| `crates/backend/src/step.rs:1-11`, `:164-171`, `:273-303`, `:355-371` | `main` at `aaf076f1` | The engine track's post-commit `deliver` hook: delivery happens after the commit, a delivery error never undoes the commit, and repeating the same request replays the retained step instead of recomputing it |
| `crates/backend/src/host_generation.rs:64-79`, `:107-132` | `main` at `aaf076f1` | A refused delivery leaves a pending request that must be resolved, by replaying it, before the generation can advance |
| `crates/backend/src/step.rs:18-19`, `:199-221` | `main` at `aaf076f1` | The coordinator uses `Rc` and `Cell`, so it is not `Send`: a single owner drives it |
| Archived `crates/serve-synthetic/src/backend.rs:13-151` (`CompletionBackend`) | tag `archive/2026-09-21/feat/openai-serving` | Server-owned admission, ordering checks, bounded events, provider-reported usage admitted only with a checked sum |
| Archived `crates/serve-synthetic/src/runtime_adapter.rs:15-54` (`RuntimeSession`) | same tag | A synchronous session on an owned thread, an `emit` callback, a cancel probe, a stopping token excluded from completion usage, and the lease held until the thread is joined |

The `crates/backend` files are read only. This seam mirrors their shape; it never depends
on them (decision B5: no path dependency on any crate outside `console/`).

## 3. Division of responsibilities

The server keeps everything project-maya's server keeps (plan section 6). An engine MUST
NOT be required to do any of the following, and the server MUST NOT delegate them:

| Duty | Owner | Donor reference |
| --- | --- | --- |
| Tokenization of the rendered prompt | Server (console-tokenizer, console-prompt) | `Service.render_ids`, `serve/server.py:2532` |
| Chat template rendering | Server | `serve/frontend.py` `ChatTemplate` |
| Detokenization, including split UTF-8 sequences | Server | `Detokenizer`, `serve/server.py:2294` |
| Stop handling: stop strings and stop ids, re-checked even when the engine was told the stop ids | Server | `serve/server.py:4518-4525` |
| Tool-call parsing for every syntax | Server | `serve/frontend.py` (as read by the planner record for prompting and parsers) |
| Thinking budget policy | Server; the engine may receive budget keys as hints | `StrataEngine.sampling_keys`, `serve/server.py:1218-1225` |
| Loop guard within and across turns | Server | `serve/loop_guard.py` |
| Finish reason on the wire | Server | `Service.run`, `serve/server.py:4761` |
| Usage on the wire | Server, computed from counts the backend reports (section 9) | `serve/server.py:4507`, `:4712`, `:4905` |
| FIFO places, queue keep-alives, heartbeats on a quiet engine | Server | `FairLock`, `serve/server.py:243-401` |
| Context rule: a request too long for the context is rejected, never truncated | Server | `serve/server.py:3680-3694` (as cited by ENG-10) |
| Restart after an engine died, retry rules (the non-finite retry) | Server | `Service.ensure_engine`, `serve/server.py:2639-2661` |

The engine owns: computing and committing tokens, its own prefix reuse, applying the
sampling parameters it advertises, honoring cancel, pause and wrap requests at its next
step, and reporting counts and timings.

## 4. Threading model

The token level is synchronous. An engine instance is created on, and owned by, one
dedicated driver thread, and it need not be `Send` or `Sync`. This is the shape of the
engine track's coordinator, which holds `Rc` and `Cell` state and is driven by a single
owner (`crates/backend/src/step.rs:18-19`, `:199-221`).

Rules:

1. The factory is `Send + Sync`. Its `start` method MUST be called on the driver thread,
   and the instance it returns MUST never leave that thread.
2. All calls on an instance happen on the driver thread, one at a time. The server talks to
   the driver thread through a job channel; the async request tasks never touch the
   instance.
3. Requests to cancel, pause or wrap a generation arrive while `generate` is running.
   They reach the engine through a `ControlProbe`, which is `Send + Sync` and is read by
   the engine between steps. No method on the instance is called from another thread to
   deliver them.
4. The FIFO place held by a request is released only after `generate` has returned on the
   driver thread. This preserves the donor's guarantee that a stopped request is drained
   to its end before the next request starts (`serve/server.py:1453-1504`), and the
   archived adapter's rule that a lease is held until its worker has really returned.
5. The line-protocol engine owns the child's standard input through a single writer, so
   every line reaches the child whole. This is deviation FIX-1.2 in
   [deviations.md](deviations.md).

Multi-conversation engines (`READY ... multi=<n>`, donor `_generate_multi`,
`serve/server.py:1557-1676`) run several requests at once. A blocking `generate` on a
single driver thread cannot express that directly. ENG-01 MUST settle the design before
freezing, along the lines of the lead's guidance of 2026-11-14: the instance stays owned by
one driver thread; for more than one concurrent generation the token-level trait offers a
submit-and-pump form whose events are tagged with the `RequestId` (section 6); and the
blocking `generate` form is the single-conversation case. The details are open question
Q1.

## 5. Engine descriptor and capabilities

```rust
pub struct SeamVersion { pub major: u16, pub minor: u16 }
pub const SEAM_VERSION: SeamVersion = SeamVersion { major: 0, minor: 1 };

#[non_exhaustive]
pub enum Provenance {
    Synthetic,                                  // the only value the server accepts in this increment
    NotSynthetic { declared: Option<String> },  // anything else an engine declares, or no declaration
}

pub enum EngineKind { Scripted, LineProtocol, CoordinatorAdapter, RuntimeAdapter }

pub struct EngineDescriptor {
    pub seam: SeamVersion,
    pub kind: EngineKind,
    pub provenance: Provenance,
    pub version: Option<String>,           // INFO engine=<v>, else a build manifest (donor :913-942)
    pub max_context: u32,                  // READY <ctx>; 0 means not ready
    pub vocab_size: Option<u32>,           // when known, the ledger checks ids against it
    pub caps: EngineCaps,
    pub info: InfoMap,                     // every INFO key=value fact, in arrival order
    pub facts: EngineFacts,                // model_path, log_path, load_s: monitoring only
}

pub struct EngineCaps {
    pub stop: bool,                        // READY ... stop      honors a STOP mid-request
    pub pause: bool,                       // READY ... pause     a STOP that keeps the state
    pub multi: Option<u32>,                // READY ... multi=<n> Some(1) is not None
    pub logit_bias: bool,                  // INFO logit_bias=1
    pub logprobs_max: Option<u8>,          // INFO logprobs=<n>
    pub vision: VisionCap,                 // INFO vision=ds4|mm3|off, or absent
    pub ablate: bool,                      // INFO ablate=1 (deviation POL-1)
    pub lifecycle: LifecycleCaps,
}

pub enum VisionCap { Absent, Off, Ds4, Mm3 }

pub struct LifecycleCaps {
    pub set_context: bool,                 // context reload by restart with a new context
    pub restart: bool,
    pub unload: bool,
    pub lend: bool,                        // VLEND / VRECLAIM control lines (PLAT-1)
}

impl EngineCaps {
    pub fn places(&self) -> u32 { self.multi.unwrap_or(1).max(1) }
}

pub enum InfoValue { Int(i64), Str(String) }   // an optional minus and digits is Int, else Str
pub struct InfoMap(Vec<(String, InfoValue)>);
```

Rules:

1. The capability flags mirror what the donor reads from `READY` and `INFO`
   (`serve/server.py:925-939`, `:2495`, `:2527`, `:2502`, `:7255-7271`). The difference
   between "multi present with 1" and "multi absent" is kept, because the donor keeps it.
2. `InfoValue` follows the donor's parse exactly: a value that is an optional minus sign
   followed by digits becomes `Int`; anything else stays a string, so `vram_gb=60.0`
   stays a string (`serve/server.py:927-930`).
3. A request that needs a capability the descriptor does not advertise MUST be refused
   by the server before anything is sent to the engine, with the donor's 400 behavior
   (`serve/server.py:2494-2530`). The capabilities in question are a non-empty
   `logit_bias` (and `ignore_eos`, which is built on it), `logprobs` above
   `logprobs_max`, `ablate: true` without `caps.ablate`, and pictures for a vision kind
   this build cannot serve (deviation LIC-2 for `Mm3`).
4. `ablate` is recognized and refused unless an engine advertises it. No engine in this
   increment advertises it, and no switch or configuration key sets it (deviation POL-1).
5. `max_context == 0` means the engine is not ready; the server answers 503 "the model is
   starting" without calling `generate`.
6. `Provenance` can express "not synthetic": an engine that declares another provenance,
   or declares none, reports `NotSynthetic`. `Synthetic` is the only value the server
   accepts in this increment (section 5.1). The enum above is a draft; ENG-01 settles the
   exact shape of the type.

### 5.1 The synthetic-only guard

Decided by the owner on 2026-11-14 (Q9, open item OPEN-29): the server refuses to start
an engine that does not report synthetic provenance. The mechanism is the lead's decision
LD28, stated here as rules.

```rust
pub struct ProvenanceRefused {
    pub kind: EngineKind,                  // the engine kind, named in the refusal line
    pub reported: Provenance,              // what the engine reported, named in the line
}

/// The single guard, in console-core. Ok(()) only for Provenance::Synthetic.
pub fn require_synthetic(d: &EngineDescriptor) -> Result<(), ProvenanceRefused>;
```

Rules:

1. The provenance type in the engine descriptor MUST be able to express "not synthetic":
   an engine that declares another provenance, or declares none. `Synthetic` is the only
   value the server accepts in this increment. ENG-01 settles the exact shape of the type.
2. Exactly one guard function in `console-core` decides (drafted above as
   `require_synthetic`). Every path that admits an engine (first start, restart, model
   switch, context reload) MUST call it before the engine serves a request. No
   environment variable, configuration key, command-line flag or Cargo feature MAY bypass
   it in this increment.
3. At process start, a refusal MUST make `pulsar-console` exit with a non-zero status
   after one line on standard error. The line MUST name the engine kind, what the engine
   reported, and the path `docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md`. At a later
   restart, model switch or context reload, the engine MUST be closed, the operation MUST
   fail with the same message, and the server MUST NOT serve anything from that engine.
4. A line-protocol engine MUST declare synthetic provenance in its start-up lines before
   it is admitted. An engine that declares another provenance, or none, MUST count as not
   synthetic (fail closed). The form of the declaration is settled by the line-protocol
   packages in M3 and is open item OPEN-58, a lead item; the lead's direction is a fact on
   an `INFO` line, so that the donor's `READY` grammar stays unchanged. This is not the
   synthetic marker proposed for the server's own ready line, which belongs to PLAN-1 and
   OPEN-35.
5. Tests pin the refusal: ENG-01 for the guard, ENG-10 for the turn driver and API-08 for
   process start. They MUST NOT be deleted or weakened to make a real engine start.
6. What must be done to allow a non-synthetic engine is written in
   [`ALLOWING_NON_SYNTHETIC_ENGINES.md`](../../../docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md),
   requested by the owner on 2026-11-14 so that whoever picks the work up next can act on
   it. A task that adds, moves or removes an enforcement point of the synthetic-only rule
   MUST update that note in the same change.

A draft of the refusal line of rule 3 follows. The three named parts are required; the
rest of the wording is a draft.

```text
[console] refusing to start: engine <kind> reports provenance <reported>; this build serves synthetic engines only. See docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md
```

## 6. Generation request

```rust
pub struct RequestId(pub u64);             // assigned by the server; unique and increasing
                                           // across engine restarts

pub struct GenerationRequest {
    pub rid: RequestId,
    pub prompt: Arc<[u32]>,                // always the whole prompt, already tokenized
    pub max_new: u32,                      // after the server's context rule
    pub sampling: Sampling,
    pub stop_ids: Arc<[u32]>,              // an early-stop hint; the server re-checks
    pub logprobs: Option<u8>,              // top alternatives per token, <= caps.logprobs_max
    pub thinking: Option<ThinkingHints>,   // budget keys an engine may enforce itself
    pub restore: Option<RestoreHints>,     // restore points for engines that use them
    pub tune: TuneKnobs,                   // validated per-request engine settings (strata_tune)
    pub projection: Option<bool>,          // cvec=0|1 for an engine started with a vector
    pub ablate: bool,                      // always false unless caps.ablate (POL-1)
    pub embeddings: Option<EmbeddingsRef>, // picture data for GENI; carried with the request
}

pub struct Sampling {
    pub temperature: Option<f64>,          // None keeps the engine default (greedy)
    pub top_p: Option<f64>,
    pub top_k: Option<u32>,
    pub min_p: Option<f64>,
    pub seed: Option<u64>,
    pub penalties: Penalties,              // repeat, presence, frequency, last_n
    pub logit_bias: Arc<[(u32, f32)]>,     // sorted by id; empty means none
}

pub struct ThinkingHints { pub budget: u32, pub end_id: u32, pub soft: Option<SoftClose> }
pub struct RestoreHints { pub marks: Vec<u64>, pub tail: Option<u64>, pub shared: Option<u64> }
```

Rules:

1. Every field is typed. No field is filled from a client JSON key, and in particular no
   key beginning with `_` reaches this struct (deviation SEC-6). The donor carries these
   values as untyped keys of the request dictionary (`_think_budget`, `_think_end`,
   `_think_soft`, `_think_stops`, `_restore`; `serve/server.py:1218-1225`, `:1322-1336`,
   `:4424-4431`).
2. The wire encoding of these fields on a `GEN` line, including Python-compatible float
   text, belongs to ENG-03 and the line-protocol contract written by ENG-04. This
   contract fixes only their meaning.
3. The request does not carry a `keep` flag for pause; pause is a control request
   (section 8).
4. An engine that does not use a hint (`thinking`, `restore`, `projection`) ignores it. An
   engine MUST NOT ignore `max_new`, `stop` requests, `logprobs` within its advertised
   maximum, or `logit_bias` when it advertises `logit_bias`.

## 7. Events, the sink and delivery

```rust
pub enum EngineEvent {
    Admitted { prompt_tokens: u32, reused_tokens: Option<u32> },
    PromptProgress(PromptProgress),
    Token(CommittedToken),
    Sample(EngineSample),                  // telemetry: STAT, VRAM, residency; any time
    Note(BoundedText),                     // at most 512 bytes; logged, never shown as output
}

pub struct PromptProgress {
    pub read: u32, pub total: u32, pub reused: u32, pub ms: f64, pub tok_s: Option<f64>,
}

pub struct CommittedToken {
    pub index: u32,                        // 0-based ordinal among this call's generated tokens
    pub position: u64,                     // absolute position in the engine's sequence
    pub id: u32,
    pub logprob: Option<TokenLogprob>,
}

pub struct TokenLogprob { pub logprob: f32, pub top: Vec<(u32, f32)> }  // most likely first

pub enum DeliveryRefused { Backpressure, ConsumerGone }

pub trait EventSink {
    /// Called on the driver thread. Ok(()) means accepted (or an exact replay, dropped).
    fn deliver(&mut self, event: EngineEvent) -> Result<(), DeliveryRefused>;
}
```

Order, per `generate` call:

1. `Admitted` first, exactly once. `prompt_tokens` MUST equal `prompt.len()`. An engine
   that has no admission notion of its own (the scripted engine, the line-protocol engine)
   has `Admitted` emitted for it by its adapter when the request is sent.
2. Any number of `PromptProgress`, `Sample` and `Note` events, at any time. The donor's
   `PP` line maps to `PromptProgress` (`serve/server.py:1426-1439`); `STAT` maps to
   `Sample` (`:1201-1215`, `:1440-1441`).
3. `Token` events in index order, starting at 0.
4. Nothing after `generate` returns. The terminal record is the return value, so a second
   terminal, or an event after the terminal, is structurally impossible at this level.

Delivery is at least once and keyed by position:

- When `deliver` returns `Backpressure`, the event was not accepted. The engine SHOULD
  wait and offer the same event again; it MUST NOT skip it.
- When `deliver` returns `ConsumerGone`, nobody is reading. The engine SHOULD stop at its
  next step and return `Terminal { stop: Cancelled }`. A refused delivery never turns a
  committed step into a failure.
- An engine MAY deliver the most recently accepted token again (same index, position, id
  and logprob). The ledger drops it and `deliver` returns `Ok(())`. This is exactly what
  the engine track's coordinator does after a refused delivery: the next `advance` with the
  same pending request replays the retained step and calls `deliver` again for the same
  position, without recomputing it (`crates/backend/src/step.rs:288-303`,
  `crates/backend/src/host_generation.rs:116-130`).

Heartbeats are not engine events. When no event has arrived for the heartbeat interval
(10 seconds in the donor, `serve/server.py:1387-1403`), the server emits its own
keep-alive. A `PromptProgress` event also counts as activity.

### 7.1 The event ledger

The server applies one shared ledger to every engine, whatever its kind. The ledger runs
inside the sink, before an event is forwarded downstream.

```rust
pub enum Verdict { Accepted, Replay }

pub struct EventLedger { /* next index, last accepted token, position0, limits */ }

impl EventLedger {
    pub fn new(req: &GenerationRequest, desc: &EngineDescriptor) -> Self;
    pub fn observe(&mut self, event: &EngineEvent) -> Result<Verdict, EngineFailure>;
    pub fn close(&mut self, terminal: &Terminal) -> Result<Counts, EngineFailure>;
}
```

`observe` rules for a `Token`:

| Condition | Verdict |
| --- | --- |
| `index == next` and, once `position0` is fixed, `position == position0 + index` | `Accepted`; `next` advances |
| Identical to the most recently accepted token | `Replay`: dropped |
| `index < next` and not identical to the most recently accepted token | `Protocol` failure (a rewind, or a changed id at a committed position) |
| `index > next` | `Protocol` failure (a gap) |
| A token before `Admitted`, or `Admitted` twice, or `Admitted.prompt_tokens != prompt.len()` | `Protocol` failure |
| `index >= max_new` | `Protocol` failure |
| `id >= vocab_size` when `vocab_size` is known | `InvalidToken` failure |
| `logprob` present when `logprobs` was not asked, or with more alternatives than asked | `Protocol` failure |

`position0` is fixed by the first accepted token. An engine that does not track absolute
positions (the line-protocol engine) has positions assigned by its adapter as
`prompt.len() + index`.

`close` checks the terminal record against what was accepted (section 9) and returns the
counts the server uses for usage.

## 8. Cancellation, pause and wrap

```rust
#[derive(Clone)]
pub struct ControlProbe(Arc<ControlState>);   // Send + Sync; atomics only

impl ControlProbe {
    pub fn is_cancelled(&self) -> bool;
    pub fn pause_requested(&self) -> Option<PauseRequest>;
    pub fn wrap_requested(&self) -> bool;
}

pub struct PauseRequest { pub keep: bool }

pub struct ControlHandle { /* server side of the same state */ }
impl ControlHandle {
    pub fn cancel(&self);                     // client gone, shutdown, server decision
    pub fn pause(&self, keep: bool);          // fair slices
    pub fn wrap(&self);                       // the server is stopping
}
```

- **Cancel.** Set by the client-disconnect watcher, by shutdown, and by the server when it
  has decided the answer is finished (a stop id or stop string, the loop guard, the token
  limit it enforces). After the engine observes it, the engine MUST stop advancing and
  return `Terminal { stop: Cancelled }` or a failure, within the cancel deadline the server
  sets. The line-protocol engine writes `STOP` (or `STOP <rid>` in multi mode) when the
  engine advertises `stop`, then drains to the request's `DONE` before returning. This is
  the donor's drain (`serve/server.py:1453-1504`). The FIFO place stays held until then.
- **Pause.** Ends the generation at its next step and keeps the engine's state with what
  it wrote, so that a continuation with the prompt plus the written tokens needs one token
  to read (`serve/server.py:1678-1691`). Tokens the engine still writes before it stops
  are delivered as usual. The terminal is `Paused`. `keep` asks the engine first to set the
  prompt's state aside for the conversation's next turn. Only engines with `caps.pause`
  receive pause requests.
- **Wrap.** The server is stopping. A generation that is still reasoning closes its
  reasoning at the next token and answers (`serve/server.py:1549-1555`). Wrap does not end
  the generation by itself; shutdown follows it with cancel after the wrap window. In
  multi mode the cancel is sent per request id (deviation FIX-1.3).

## 9. Terminal record and usage accounting

```rust
pub enum EngineStop {
    Stop { token: Option<u32> },          // the engine itself reached an end token
    Length,                               // max_new reached
    Cancelled,                            // after a cancel request or ConsumerGone
    Paused,                               // after a pause request
}

pub struct EngineCounts {
    pub generated: u32,                   // as the engine counts them (DONE field 1)
    pub prompt_tokens: u32,               // DONE field 2
    pub reused_tokens: Option<u32>,       // DONE field 8, or PP
    pub drafts: Option<(u32, u32)>,       // accepted, offered (DONE fields 6-7)
    pub hits_lookups: Option<(u32, u32)>, // DONE fields 9-10
}

pub struct EngineTimings { pub prompt_ms: f64, pub decode_ms: f64 }

pub struct Terminal {
    pub stop: EngineStop,
    pub counts: Option<EngineCounts>,     // None for an engine without a DONE (the scripted engine)
    pub timings: Option<EngineTimings>,   // None for an engine without a clock
}
```

The 5, 8 and 10 field forms of the donor's `DONE` line stay distinguishable through the
`Option` fields (`serve/server.py:1192-1199`). Figures are returned per call, never left in
shared mutable state on the engine object (the donor's `last` attribute).

Usage rules:

1. Usage comes only from what the backend committed and reported. It is never estimated
   from text, bytes, words or message counts (the archived contract's rule).
2. `prompt_tokens` on the wire is the length of the prompt ids sent, as the donor reports
   it (`serve/server.py:4712`, `:4905`). Across several engine calls within one request
   (slices and continuations), the turn driver merges figures as ENG-10 specifies.
3. `completion_tokens` on the wire counts every token the server consumed from the
   ledger for the answer, including a stop token, because the donor increments its counter
   before its stop check (`serve/server.py:4507`). Whether this matches the engine's own
   `generated` figure is open question Q4.
4. `reused_tokens` (reported as cached tokens) come from the engine's counts or progress.
   An engine that reports none reports no cached tokens; the server does not infer them.
5. All sums use checked integer arithmetic. An overflow is a `Protocol` failure raised
   before any success terminal reaches the client.
6. `EventLedger::close` refuses a terminal whose counts contradict what the ledger
   accepted (for example `prompt_tokens != prompt.len()`) with a `Protocol` failure. The
   exact tolerance for `generated` is part of Q4.

## 10. Failures

```rust
pub struct EngineFailure {
    pub kind: FailureKind,
    pub message: BoundedText,             // the donor's text, with branding neutralized (BRAND-1)
    pub poisoned: bool,                   // the instance must not be used again
    pub after_tokens: u32,                // tokens accepted before the failure
}

pub enum FailureKind {
    Died,          // the process ended, the pipe closed, or the runtime panicked
    Reported,      // the engine's ERR text
    NotReady,      // max_context == 0
    NeverAnswered, // a multi-mode request heard nothing for the quiet limit
    InvalidToken,  // a negative or out-of-vocabulary id
    Unsupported,   // the request needs a capability the descriptor lacks
    Protocol,      // a ledger violation
    StartFailed,   // the engine exited before READY
}
```

| Kind | Donor origin | Server mapping (rendered by console-http) |
| --- | --- | --- |
| `Died` | `EngineDied`, `serve/server.py:412-413`, raised at `:1380`, `:1406` | 503 server_error, "<reason>; the next request restarts it"; the next turn restarts the engine |
| `Reported` | `ERR` line, `serve/server.py:1448-1452` | 400 invalid_request_error before the first byte; a stream error after it. The non-finite retry (an `ERR` containing "non-finite" before the first token is retried once) is a server rule applied to the message, as in the donor |
| `NotReady` | `max_context <= 0`, `serve/server.py:3680-3681` | 503 "the model is starting; try again in a moment" |
| `NeverAnswered` | multi quiet timeout, `serve/server.py:1597-1600` | As the donor; detail in ENG-07 |
| `InvalidToken` | negative `T` id (`engine_token`, `serve/server.py:560-568`) | As the donor's message, detail in ENG-01 |
| `Unsupported` | `Service.check_request` refusals | 400 before anything is sent |
| `Protocol` | none: new, from the ledger | 500 before the first byte; a stream error after; the instance is poisoned |
| `StartFailed` | `serve/server.py:941-947` | Start-up error; 503 for requests while no engine runs |

A `ContextOverflow` is not an engine failure: the server's context rule raises it before
any engine call.

## 11. Engine factory, instance and lifecycle

```rust
pub trait EngineFactory: Send + Sync + 'static {
    fn kind(&self) -> EngineKind;
    /// Called on the driver thread. The returned instance never leaves it.
    fn start(&self, cfg: &EngineStartConfig) -> Result<Box<dyn EngineInstance>, EngineFailure>;
}

/// Deliberately neither Send nor Sync.
pub trait EngineInstance {
    fn descriptor(&self) -> &EngineDescriptor;

    /// Blocks until the generation ends. Delivers Admitted, then tokens in index order
    /// (an exact repeat of the last one is allowed), then returns exactly one Terminal
    /// or one EngineFailure.
    fn generate(
        &mut self,
        req: &GenerationRequest,
        control: &ControlProbe,
        sink: &mut dyn EventSink,
    ) -> Result<Terminal, EngineFailure>;

    /// Polled by the driver between generations.
    fn sample(&mut self) -> Option<EngineSample> { None }

    /// alive(), exit_code() and death_note() in the donor.
    fn health(&mut self) -> Health { Health::Alive }

    /// A control line between generations (VLEND / VRECLAIM). Needs caps.lifecycle.lend.
    fn command(&mut self, _cmd: &ControlCommand) -> Result<String, EngineFailure> {
        Err(EngineFailure::unsupported("command"))
    }

    /// Mixed-GPU layout before a call (pictures, logprobs). Default: nothing to do.
    fn use_layout(&mut self, _alone: Option<AloneReason>) -> Result<(), EngineFailure> { Ok(()) }

    /// Graceful end: STOP if a generation runs, QUIT, wait up to the deadline, then kill.
    fn shutdown(self: Box<Self>, deadline: Instant) -> ShutdownOutcome;
}
```

Lifecycle operations of the donor map onto these as follows. A restart is `shutdown`
followed by `EngineFactory::start`. A context reload is `shutdown` followed by `start`
with the new context; it uses the graceful path, not a kill (deviation FIX-1.1). An idle
unload is `shutdown` with no immediate `start`.

### 11.1 Mapping of the donor's optional engine members

The donor discovers optional members with `hasattr`. Each one has a named place here.

| Donor member | Seam element |
| --- | --- |
| `max_context` | `EngineDescriptor::max_context` |
| `generate(ids, max_new, sampling, cancel, embeddings)` | `EngineInstance::generate` with `GenerationRequest` and `ControlProbe` |
| `info` | `EngineDescriptor::info` and `EngineCaps` |
| `can_stop`, `can_pause`, `multi` | `EngineCaps::stop`, `pause`, `multi` |
| `stop()` | `ControlHandle::cancel` |
| `pause(keep)` | `ControlHandle::pause` |
| `wrap()` | `ControlHandle::wrap` |
| `alive()`, `exit_code()`, `death_note()` | `EngineInstance::health` and `EngineFailure::message` |
| `restart()` | `shutdown` then `EngineFactory::start` |
| `close()` | `EngineInstance::shutdown` |
| `set_context(n)` | `shutdown` then `start` with the new context (FIX-1.1) |
| `command(line, expect, timeout)` | `EngineInstance::command` |
| `use(...)` (mixed GPUs) | `EngineInstance::use_layout` |
| `last` | `Terminal::counts` and `Terminal::timings`, per call |
| `progress`, `prefill_tok_s_mean` | `EngineEvent::PromptProgress` |
| `stat`, `stat_history`, `vram` | `EngineEvent::Sample`, `EngineInstance::sample` |
| `log_path`, `model_path`, `load_s`, `version` | `EngineDescriptor::facts`, `version` |

## 12. Event level

```rust
pub enum TurnEvent {
    Reasoning(String),
    Content(String),
    ToolCall(ToolCallDelta),               // index, id, name, argument text as parsed
    Progress(PromptProgress),              // for prompt_progress chunks and pings
    Ping,                                  // a keep-alive while queued or while the engine is quiet
    Terminal(TurnTerminal),                // exactly once, last
}

pub struct TurnTerminal {
    pub finish: Finish,                    // stop, length, tool_calls, cancelled, error
    pub usage: Usage,                      // section 9
    pub timings: Option<TurnTimings>,      // llama.cpp-style figures (ENG-10)
    pub error: Option<TurnError>,
}
```

Rules:

1. Every turn ends with exactly one `Terminal`, including a failed or cancelled turn. No
   event follows it.
2. The concatenation of the `Content` text equals the answer text of the non-streamed
   response; the same holds for `Reasoning`. Independent tests check this across
   dialects (CNF-14).
3. The event names and fields of the parser are defined by PRM-09 and PRM-12; this
   contract fixes only the ordering rules above.

## 13. Implementations in this increment

| Implementation | Package | Notes |
| --- | --- | --- |
| Scripted in-process engine | ENG-02 | Reproduces `MockEngine`: script rotation, the `max_new` cut, cancel before each step, the logprob shape `(0.0, [(id, 0.0)])`, optional pacing and figures |
| Line-protocol child engine | ENG-06, ENG-07 | Speaks the line protocol written down by ENG-04; single writer for standard input; drains after STOP |
| Rust fake engine binaries | ENG-05 (with CNF-05 merged into it) | Driven through the line-protocol engine; the donor's Python fakes are never run locally (decision B9) |
| Coordinator-shaped test adapter and blocking runtime adapter | ENG-19 | Models the engine track's `deliver` hook, replay after a refused delivery and the non-`Send` single owner; passes the seam battery |
| Seam conformance battery | ENG-18 | Runs every implementation above against sections 5 to 11 |

Each implementation above reports `Provenance::Synthetic`, and each passes the guard of
section 5.1. The in-process engines (the scripted engine and the ENG-19 adapters) construct
their descriptor with `Synthetic` themselves. The line-protocol client derives provenance
from the declaration in the child's start-up lines (section 5.1, rule 4): with a
declaration of synthetic provenance it reports `Synthetic`, and with any other
declaration, or none, it reports `NotSynthetic`. The Rust fake engine binaries make the
declaration.

The coordinator-shaped adapter shows the fit as follows. The engine track's
`StepCoordinator::execute` calls `deliver(&CommittedStep)` after its commit; the adapter's
hook calls `EventSink::deliver(Token(CommittedToken { index: position - position0,
position, id: token, .. }))`. A refused delivery becomes the hook's error, which
`HostGeneration::advance` records as a pending delivery; the next `advance` with the same
request replays the retained step and delivers the same position again, which the ledger
drops. Nothing in this increment calls `crates/backend`; the adapter mirrors the shape.

## 14. Open questions for ENG-01

These MUST be answered, or explicitly deferred with a reason, before the seam is frozen.
They are also listed in the register of open items,
[`../checklists/analysis.md`](../checklists/analysis.md), which says who decides each: Q1
to Q8 and Q12 are OPEN-30, Q10 is OPEN-21 and Q11 is OPEN-01. Q9 was OPEN-29; the owner
settled it on 2026-11-14, and its row below records the decision.

| Id | Question |
| --- | --- |
| Q1 | How does the synchronous, single-owner token level serve an engine with several places (`multi=<n>`)? The lead's direction for ENG-01 (section 4): a submit-and-pump form, pumped by the driver thread across several generations, with events tagged by `RequestId`; the blocking `generate` form is the single-conversation case. Open are only the details: the method set, how the pump interleaves events and terminals, and how control requests reach each generation. The engine planner record's ENG-01 text proposed an async, `Send + Sync` engine trait instead; the approved plan requires the synchronous single-owner shape, so that proposal is not available. |
| Q2 | Is `Admitted.reused_tokens` known at admission for any engine, or should reuse be reported only in progress and in the terminal? |
| Q3 | May an engine replay any exact earlier token, or only the most recently accepted one, as drafted here (the engine track retains only the latest step)? |
| Q4 | Does the engine's `generated` count include the stop token, and what must `EventLedger::close` require of it relative to the accepted token count? |
| Q5 | Is `Paused` a distinct terminal, or a `Cancelled` with a cause? The donor's `DONE` reports `cancel` in both cases and the server knows which it asked for. |
| Q6 | Which cancel deadline applies, and what happens to an in-process engine that ignores cancel beyond it? The archived crate destroyed in-process futures at a bound; an in-process synchronous engine cannot be destroyed, only waited for. |
| Q7 | Should `Sample` carry a typed residency and memory record (the panel proposal's `EngineSample`), or the donor's untyped `STAT` key-value map only? |
| Q8 | Are `TuneKnobs` a closed typed set (the donor's `pcie_frac`, `spec_min_p`, `spec_cum`, `suffix_draft`, `lookup_trust`, `cpu_threads`) or an opaque validated map? |
| Q9 | Decided by the owner on 2026-11-14 (OPEN-29, settled): the server refuses to start an engine that does not report synthetic provenance, at process start and at every later restart, model switch or context reload. The mechanism (one guard function in `console-core`, no bypass, the refusal line, fail-closed handling of a line-protocol engine that does not declare synthetic provenance, the pinning tests and the note on allowing non-synthetic engines) is in section 5.1. |
| Q10 | May a later engine attach at the event level, and if so which of the duties in section 3 does it take over? This needs its own approval (Phase 3). |
| Q11 | Is the sealed-reasoning prefix accepted on input in the donor's form? This is an open item of decision B2 ([naming.md](naming.md), item N1), not of this seam, but it touches the event level. |
| Q12 | Which engine-track reviewer receives this draft, and what form does their acceptance take before ENG-01 freezes version 1.0? |
