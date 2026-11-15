# Backend Seam Contract (draft 0.2)

- **Status**: Normative draft, version 0.2, dated 2026-11-14. Work package ENG-01 has
  implemented this draft in `console-core::engine`, where `SEAM_VERSION` is 0.2. It is
  frozen as version 1.0 only after the engine track's review is recorded (plan section 12,
  "The seam does not fit the real engine"; FR-039). Who on the engine track reviews it,
  and in what form, is not decided (Q12). Until then any section may change. Section 15
  lists what the engine track is asked to confirm.
- **Revised**: 2026-11-14, to record the owner's decision on Q9 (sections 5, 5.1, 13 and
  14): the server refuses to start an engine that does not report synthetic provenance.
  Revised again on 2026-11-14 by ENG-01 for version 0.2: the code's names and shapes in
  sections 4 to 11, the submit-and-pump form (section 4.1), the answers to Q1 to Q8
  (section 14) and the review request (section 15).
- **Feature**: `specs/022-console-serving-parity`
- **Written by**: GOV-06 (draft 0.1); ENG-01 (draft 0.2, and the freeze once the review
  is recorded); implemented by ENG-01, ENG-02, ENG-06, ENG-07, ENG-10, ENG-18 and ENG-19;
  the refusal at process start of section 5.1 by API-08.
- **Claims**: Every engine behind this seam is synthetic. The strongest claim any of them
  can earn in this increment is "qualified on synthetic backends". No real model, no
  project-maya engine binary and no engine-track crate is attached through this seam in
  this increment.

The word MUST marks a rule the implementation and its tests enforce. SHOULD marks a
default that an engine may depart from with a stated reason.

"Decision B1" to "decision B13" are the binding cross-cutting decisions restated in
[`../tasks.md`](../tasks.md), section "Binding cross-cutting decisions". A "planner record"
is one of the per-area design proposals written before the plan was approved, and the
"panel proposal" is one of the alternative overall approaches proposed before the plan;
neither is in the repository, and neither is approved by being cited here.

Every Rust name below is exported from `console_core::engine`. The code blocks show the
public shape; derives, documentation and private fields are left out.

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
| project-maya `serve/server.py:412-428` (`EngineDied`, `ContextOverflow`), `:532-568` (`LpToken`, `parse_lp`, `engine_token`) | `7e68a30f` | Failure classes, the logprob value shape and the negative-id message |
| project-maya `serve/server.py:2489-2530` (`Service.check_request`) | `7e68a30f` | How `INFO logit_bias=1`, `INFO logprobs=<n>` and `INFO ablate=1` gate requests |
| project-maya `serve/server.py:2620-2666` (`alone_reason`, `engine_for`, `ensure_engine`) | `7e68a30f` | Optional members found with `hasattr`; the reasons a request runs on one GPU alone; places after a restart |
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
owner (`crates/backend/src/step.rs:18-19`, `:199-221`). The token-level traits use no
async runtime.

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
   driver thread (or, in the submit-and-pump form, after the generation's `Finished` was
   returned by `pump`). This preserves the donor's guarantee that a stopped request is
   drained to its end before the next request starts (`serve/server.py:1453-1504`), and
   the archived adapter's rule that a lease is held until its worker has really returned.
5. The line-protocol engine owns the child's standard input through a single writer, so
   every line reaches the child whole. This is deviation FIX-1.2 in
   [deviations.md](deviations.md).

### 4.1 Engines with several places: submit and pump

Multi-conversation engines (`READY ... multi=<n>`, donor `_generate_multi`,
`serve/server.py:1557-1676`) run several requests at once. A blocking `generate` on a
single driver thread cannot express that, so the token level has a second form (Q1). The
instance stays owned by the driver thread; the driver submits generations and pumps the
engine, and events arrive tagged with the server's `RequestId`.

```rust
pub trait MultiEngine {
    fn submit(&mut self, req: &GenerationRequest, control: ControlProbe)
        -> Result<(), EngineFailure>;
    fn pump(&mut self, sink: &mut dyn TaggedSink, wait: Duration)
        -> Result<Vec<Finished>, EngineFailure>;
    fn running(&self) -> usize;
}

pub trait TaggedSink {
    fn deliver(&mut self, rid: RequestId, event: EngineEvent) -> Result<(), DeliveryRefused>;
}

pub struct Finished { pub rid: RequestId, pub outcome: Result<Terminal, EngineFailure> }

// On EngineInstance (section 11): None for a single-conversation engine.
fn multi(&mut self) -> Option<&mut dyn MultiEngine> { None }

/// The blocking form over the pump form: submit on an idle engine, pump until it ends.
pub fn generate_one(engine: &mut dyn MultiEngine, req: &GenerationRequest,
    control: &ControlProbe, sink: &mut dyn EventSink, wait: Duration)
    -> Result<Terminal, EngineFailure>;
```

Rules:

1. `submit` starts one generation. The server submits at most `caps.places()` at once and
   never reuses a request id. An engine MUST refuse a submission beyond its places, or with
   an id already running, with a failure, and start nothing.
2. `pump` waits at most `wait` for engine output, delivers what arrived tagged with its
   request id, and returns every generation that ended during the call. Per request id
   the order of section 7 holds: `Admitted` first, tokens in index order, then exactly one
   `Finished`, and no event for that id after it.
3. Each submission carries its own `ControlProbe`, read between steps. A cancel is sent
   for that request id only (deviation FIX-1.3).
4. `Backpressure` for one id holds that id's events, which are offered again; other ids go
   on. `ConsumerGone` for one id stops that id, which then finishes `Cancelled`. Tokens
   already in flight for that id may still be delivered; the ledger records them without
   forwarding them (section 7.1, rule 5). A generation cancelled before its `Admitted`
   was delivered (a cancel between `submit` and the first `pump`) also finishes
   `Cancelled`, and that is no engine fault.
5. An `Err` from `pump` is engine-wide (for example the engine died): every running
   generation ends with that failure, and the instance is poisoned.
6. The blocking `generate` is the single-conversation case. A multi-conversation engine
   MAY implement `generate` with `generate_one`, which refuses with `Unsupported` while
   other generations run, and returns a `Protocol` failure when the engine stops running
   the generation without returning its `Finished`.

The driver applies one ledger per generation (section 7.1) with `LedgerSet`:

```rust
impl LedgerSet {
    pub fn new(places: u32) -> Self;
    pub fn open(&mut self, req: &GenerationRequest, desc: &EngineDescriptor)
        -> Result<(), EngineFailure>;              // Protocol for a running id, Unsupported beyond places
    pub fn sink<'a>(&'a mut self, downstream: &'a mut dyn TaggedSink) -> LedgeredTaggedSink<'a>;
    pub fn finish(&mut self, finished: Finished)
        -> Result<(Terminal, LedgerCounts), EngineFailure>;   // Protocol for an id not open
    pub fn fail_all(&mut self, failure: &EngineFailure) -> Vec<(RequestId, EngineFailure)>;
}
```

An event for an id that is not open is dropped, as the donor drops lines of a request
already gone (`serve/server.py:1052`). A ledger failure in one generation stops only that
generation (its sink answers `ConsumerGone`), but a `Protocol` failure is poisoned, so
the driver treats it as engine-wide. A client that leaves is not a ledger failure: its
generation finishes `Cancelled` and no other generation is touched. ENG-07 implements the line-protocol engine over this
form; how the pump interleaves reading lines with routing, the quiet timeout and the
bounded drain are its details.

## 5. Engine descriptor and capabilities

```rust
pub struct SeamVersion { pub major: u16, pub minor: u16 }
pub const SEAM_VERSION: SeamVersion = SeamVersion { major: 0, minor: 2 };

#[non_exhaustive]
pub enum Provenance {
    Synthetic,                                           // the only value the guard admits
    NotSynthetic { declared: Option<DeclaredProvenance> }, // another declaration, or none
}
impl Provenance {
    pub fn not_synthetic(declared: Option<&str>) -> Self;  // never synthetic, whatever the text
}
pub struct DeclaredProvenance { /* at most 64 characters, displayed escaped */ }

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
impl EngineDescriptor {
    pub fn new(kind: EngineKind, provenance: Provenance) -> Self;  // not ready, no caps
    pub fn is_starting(&self) -> bool;     // max_context == 0
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
impl EngineCaps {
    pub fn places(&self) -> u32 { self.multi.unwrap_or(1).max(1) }
    pub fn apply_info(&mut self, info: &InfoMap);  // logit_bias, logprobs_max, vision, ablate
}

pub enum VisionCap { Absent, Off, Ds4, Mm3 }

pub struct LifecycleCaps {
    pub set_context: bool,                 // context reload by restart with a new context
    pub restart: bool,
    pub unload: bool,
    pub lend: bool,                        // VLEND / VRECLAIM control lines (PLAT-1)
}

pub enum InfoValue { Int(i64), Str(String) }   // an optional minus and ASCII digits is Int, else Str
impl InfoValue { pub fn parse(v: &str) -> Self; }
pub struct InfoMap(/* Vec<(String, InfoValue)> */);
impl InfoMap {
    pub fn try_insert(&mut self, key: &str, value: InfoValue) -> Result<(), InfoRejected>;
    pub fn absorb_fields<'a>(&mut self, fields: impl IntoIterator<Item = &'a str>) -> usize;
    pub fn get(&self, key: &str) -> Option<&InfoValue>;
}
pub enum InfoRejected { Full, TooLong }    // more than 256 keys; a key or value over 1024 bytes

pub struct EngineFacts {
    pub model_path: Option<String>,
    pub log_path: Option<String>,
    pub load_s: Option<f64>,
}
```

Rules:

1. The capability flags mirror what the donor reads from `READY` and `INFO`
   (`serve/server.py:925-939`, `:2495`, `:2527`, `:2502`, `:7255-7271`). The difference
   between "multi present with 1" and "multi absent" is kept, because the donor keeps it.
   `apply_info` follows the donor's tests exactly: `logit_bias` and `ablate` only for the
   integer 1; `logprobs_max` for a non-negative integer (capped at 255, which keeps the
   donor's `top >= n` test for every `n` the server accepts); `vision` for the exact
   strings `ds4`, `mm3` and `off`, and `Absent` for anything else.
2. `InfoValue` follows the donor's parse: a value that is an optional minus sign followed
   by digits becomes `Int`; anything else stays a string, so `vram_gb=60.0` stays a string
   (`serve/server.py:927-930`). Three edge cases differ, all on values the donor cannot
   use: more than one leading minus sign, non-ASCII digits, and integers beyond `i64` stay
   strings (the donor's `int()` raises on the first, reads the second, and keeps the third
   as a Python integer). `DoneFigures::parse` likewise refuses a negative count, or one
   above `u32`, that the donor's `int()` accepts (section 9). These four differences are
   proposal P-21 in [deviations.md](deviations.md) and await the owner's decision. `InfoMap` keeps a repeated key at its
   first position with the new value, as a Python dict does, and splits each field at its
   first `=`.
3. A request that needs a capability the descriptor does not advertise MUST be refused
   by the server before anything is sent to the engine, with the donor's 400 behavior
   (`serve/server.py:2494-2530`). The capabilities in question are a non-empty
   `logit_bias` (and `ignore_eos`, which is built on it), `logprobs` above
   `logprobs_max`, `ablate: true` without `caps.ablate`, and pictures for a vision kind
   this build cannot serve (deviation LIC-2 for `Mm3`). The refusal texts belong to the
   request checks (API-04, ENG-03).
4. `ablate` is recognized and refused unless an engine advertises it. No engine in this
   increment advertises it, and no switch or configuration key sets it (deviation POL-1).
5. `max_context == 0` means the engine is not ready; the server answers 503 "the model is
   starting" without calling `generate`. `generate_ledgered` (section 11) refuses with
   `EngineFailure::not_ready()` before calling the engine.
6. `Provenance` can express "not synthetic": an engine that declares another provenance
   reports `NotSynthetic { declared: Some(..) }`, and one that declares none reports
   `NotSynthetic { declared: None }`. `Provenance::not_synthetic` never yields
   `Synthetic`, whatever the text, even the word `synthetic`; an in-process engine
   constructs `Provenance::Synthetic` itself, and the line-protocol client does so only on
   the declaration form settled under OPEN-58. The declared text is kept to 64 characters
   and displayed escaped, so it can be named in a one-line refusal. `Synthetic` is the
   only value the server accepts in this increment (section 5.1).

### 5.1 The synthetic-only guard

Decided by the owner on 2026-11-14 (Q9, open item OPEN-29): the server refuses to start
an engine that does not report synthetic provenance. The mechanism is the lead's decision
LD28, stated here as rules.

```rust
pub struct ProvenanceRefused {
    pub kind: EngineKind,                  // the engine kind, named in the refusal line
    pub reported: Provenance,              // what the engine reported, named in the line
}
impl ProvenanceRefused {
    pub fn to_failure(&self) -> EngineFailure;  // StartFailed, poisoned, the same line
}
impl Display for ProvenanceRefused { /* the refusal line below */ }

pub const ALLOWING_NON_SYNTHETIC_ENGINES_PATH: &str =
    "docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md";

/// The single guard, in console-core. Ok(()) only for Provenance::Synthetic.
pub fn require_synthetic(d: &EngineDescriptor) -> Result<(), ProvenanceRefused>;
```

The guard is defined in `console/crates/console-core/src/engine/guard.rs`. It reads only
the descriptor's `kind` and `provenance`; capabilities, `INFO` facts, version, facts and
readiness do not change its answer.

Rules:

1. The provenance type in the engine descriptor MUST be able to express "not synthetic":
   an engine that declares another provenance, or declares none. `Synthetic` is the only
   value the server accepts in this increment. Its shape is settled in section 5.
2. Exactly one guard function in `console-core` decides: `require_synthetic`. Every path
   that admits an engine (first start, restart, model switch, context reload) MUST call it
   before the engine serves a request. No environment variable, configuration key,
   command-line flag or Cargo feature MAY bypass it in this increment.
3. At process start, a refusal MUST make `pulsar-console` exit with a non-zero status
   after one line on standard error. The line MUST name the engine kind, what the engine
   reported, and the path `docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md`. At a later
   restart, model switch or context reload, the engine MUST be closed, the operation MUST
   fail with the same message (`ProvenanceRefused::to_failure`), and the server MUST NOT
   serve anything from that engine.
4. A line-protocol engine MUST declare synthetic provenance in its start-up lines before
   it is admitted. An engine that declares another provenance, or none, MUST count as not
   synthetic (fail closed). The form of the declaration is settled by the line-protocol
   packages in M3 and is open item OPEN-58, a lead item; the lead's direction is a fact on
   an `INFO` line, so that the donor's `READY` grammar stays unchanged. This is not the
   synthetic marker proposed for the server's own ready line, which belongs to PLAN-1 and
   OPEN-35.
5. Tests pin the refusal: ENG-01 for the guard (`console-core` test file
   `tests/eng01_guard.rs`), ENG-10 for the turn driver and API-08 for process start. They
   MUST NOT be deleted or weakened to make a real engine start.
6. What must be done to allow a non-synthetic engine is written in
   [`ALLOWING_NON_SYNTHETIC_ENGINES.md`](../../../docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md),
   requested by the owner on 2026-11-14 so that whoever picks the work up next can act on
   it. A task that adds, moves or removes an enforcement point of the synthetic-only rule
   MUST update that note in the same change.

The refusal line of rule 3, as `ProvenanceRefused` displays it. `<kind>` is `scripted`,
`line-protocol`, `coordinator-adapter` or `runtime-adapter`; `<reported>` is `not
synthetic (declared "<text>")` or `not synthetic (no declaration)`.

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
impl GenerationRequest {
    pub fn new(rid: RequestId, prompt: impl Into<Arc<[u32]>>, max_new: u32) -> Self;
}

pub struct Sampling {
    pub temperature: Option<f64>,          // None keeps the engine default (greedy)
    pub top_p: Option<f64>,
    pub top_k: Option<u32>,
    pub min_p: Option<f64>,
    pub seed: Option<u64>,
    pub penalties: Penalties,
    pub logit_bias: Arc<[(u32, f64)]>,     // sorted by id; empty means none; the client's float
}
pub struct Penalties {
    pub repeat: Option<f64>, pub presence: Option<f64>, pub frequency: Option<f64>,
    pub last_n: Option<i64>,               // none: the last 64; 0: no penalties; -1: whole context
}

pub struct ThinkingHints { pub budget: u32, pub end_id: u32, pub soft: Option<SoftClose> }
pub struct SoftClose { pub at: u32, pub stops: String }
pub struct RestoreHints { pub marks: Vec<u64>, pub tail: Option<u64>, pub shared: Option<u64> }

pub enum TuneValue { Int(i64), Float(f64), Word(&'static str) }
pub struct TuneKnobs(/* Vec<(&'static str, TuneValue)>, at most 64 */);
impl TuneKnobs { pub fn set(&mut self, name: &'static str, value: TuneValue) -> bool; }

pub struct EmbeddingsRef { pub path: PathBuf, pub kind: EmbeddingsKind }
pub enum EmbeddingsKind { Embeddings, Pixels }
```

Rules:

1. Every field is typed. No field is filled from a client JSON key, and in particular no
   key beginning with `_` reaches this struct (deviation SEC-6). The donor carries these
   values as untyped keys of the request dictionary (`_think_budget`, `_think_end`,
   `_think_soft`, `_think_stops`, `_restore`; `serve/server.py:1218-1225`, `:1322-1336`,
   `:4424-4431`). Tune knob names and word values are `&'static str`, meant to come from
   ENG-03's compile-time table. The type makes accidental use of client text harder but
   does not prevent it (any caller can leak a `String` into a `&'static str`); ENG-03's
   validation is what keeps client keys out (SEC-6, Q8).
2. The wire encoding of these fields on a `GEN` line, including Python-compatible float
   text, belongs to ENG-03 and the line-protocol contract written by ENG-04. This
   contract fixes only their meaning. ENG-03 owns `console-core::engine::params` and may
   refine these types there.
3. The request does not carry a `keep` flag for pause; pause is a control request
   (section 8).
4. An engine that does not use a hint (`thinking`, `restore`, `projection`) ignores it. An
   engine MUST NOT ignore `max_new`, `stop` requests, `logprobs` within its advertised
   maximum, or `logit_bias` when it advertises `logit_bias`.
5. `logprobs: Some(0)` asks for each token's own logprob with no alternatives, as the
   scripted engine's `(0.0, [])` shape shows (`serve/server.py:236-239`).

## 7. Events, the sink and delivery

```rust
pub enum EngineEvent {
    Admitted { prompt_tokens: u32, reused_tokens: Option<u32> },
    PromptProgress(PromptProgress),
    Token(CommittedToken),
    Sample(EngineSample),                  // telemetry: STAT; any time
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

pub struct TokenLogprob { pub logprob: f64, pub top: Vec<(u32, f64)> }  // most likely first

#[non_exhaustive]
pub struct EngineSample { /* private: at most 64 entries, keys and texts at most 256 bytes */ }
pub enum StatValue { Num(f64), Text(String) }
impl EngineSample {
    pub fn new() -> Self;
    pub fn from_stat_fields<'a>(fields: impl IntoIterator<Item = &'a str>) -> Self;
    pub fn set(&mut self, key: &str, value: StatValue) -> bool;   // false when dropped
    pub fn get(&self, key: &str) -> Option<&StatValue>;
    pub fn iter(&self) -> impl Iterator<Item = (&str, &StatValue)>;
    pub fn len(&self) -> usize;
    pub fn is_empty(&self) -> bool;
}

pub enum DeliveryRefused { Backpressure, ConsumerGone }

pub trait EventSink {
    /// Called on the driver thread. Ok(()) means accepted (or an exact replay, dropped).
    fn deliver(&mut self, event: EngineEvent) -> Result<(), DeliveryRefused>;
}
```

Order, per `generate` call:

1. `Admitted` first among tokens, exactly once. `prompt_tokens` MUST equal
   `prompt.len()`. An engine that has no admission notion of its own (the scripted engine,
   the line-protocol engine) has `Admitted` emitted for it by its adapter when the request
   is sent.
2. Any number of `PromptProgress`, `Sample` and `Note` events, at any time, before
   `Admitted` too. The donor's `PP` line maps to `PromptProgress`
   (`serve/server.py:1426-1439`); `STAT` maps to `Sample` (`:1201-1215`, `:1440-1441`).
   `EngineSample::from_stat_fields` reads a `STAT` line's fields as the donor does: each
   value a number where Python's `float()` reads one, else text; the wall-clock time the
   donor adds is added by whoever records the sample. Its entries are reached only
   through `set`, so the limits always hold.
3. `Token` events in index order, starting at 0. Logprobs are `f64`, as the donor keeps
   the engine's figure as a Python float (`serve/server.py:539-548`), so a figure reaches
   the client unchanged.
4. Nothing after `generate` returns. The terminal record is the return value, so a second
   terminal, or an event after the terminal, is structurally impossible at this level.

Delivery is at least once and keyed by position:

- When `deliver` returns `Backpressure`, the event was not accepted. The engine SHOULD
  wait and offer the same event again; it MUST NOT skip it.
- When `deliver` returns `ConsumerGone`, nobody is reading. The engine SHOULD stop at its
  next step and return `Terminal { stop: Cancelled }`. A refused delivery never turns a
  committed step into a failure: events the engine still delivers before it stops are
  checked and recorded but not forwarded (section 7.1, rule 5), and a `Cancelled`
  terminal is accepted even when `Admitted` itself was refused.
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

pub struct EventLedger { /* next index, last accepted token, position0, failure, closed */ }

impl EventLedger {
    pub fn new(req: &GenerationRequest, desc: &EngineDescriptor) -> Self;
    pub fn check(&mut self, event: &EngineEvent) -> Result<Checked, EngineFailure>;
    pub fn commit(&mut self, checked: Checked) -> Result<(), EngineFailure>;
    pub fn observe(&mut self, event: &EngineEvent) -> Result<Verdict, EngineFailure>;
    pub fn close(&mut self, terminal: &Terminal) -> Result<LedgerCounts, EngineFailure>;
    pub fn accepted(&self) -> u32;         // the next expected index
    pub fn delivered(&self) -> u32;        // tokens accepted while the consumer was reading
    pub fn mark_consumer_gone(&mut self);  // sticky
    pub fn consumer_gone(&self) -> bool;
    pub fn failure(&self) -> Option<&EngineFailure>;
}

impl Checked {
    pub fn verdict(&self) -> Verdict;
    pub fn forwarded(&self, offered: EngineEvent) -> EngineEvent;  // a token as recorded
}

pub struct LedgerCounts {
    pub prompt_tokens: u32,                // prompt.len()
    pub completion_tokens: u32,            // accepted tokens the consumer took, a stop token included
    pub reused_tokens: Option<u32>,        // the terminal's counts only (DONE field 8)
    pub stop: EngineStop,
    pub engine: Option<EngineCounts>,      // passed through unchecked (Q4)
    pub timings: Option<EngineTimings>,
}

pub struct LedgeredSink<'a> { /* an EventLedger in front of &'a mut dyn EventSink */ }
impl<'a> LedgeredSink<'a> {
    pub fn new(req: &GenerationRequest, desc: &EngineDescriptor,
        downstream: &'a mut dyn EventSink) -> Self;
    pub fn finish(self, result: Result<Terminal, EngineFailure>)
        -> Result<(Terminal, LedgerCounts), EngineFailure>;
}
impl EventSink for LedgeredSink<'_> { /* check, forward, commit */ }
```

`observe` rules for a `Token`:

| Condition | Verdict |
| --- | --- |
| `index == next` and, once `position0` is fixed, `position == position0 + index` | `Accepted`; `next` advances |
| Identical to the most recently accepted token (logprobs compared bit for bit) | `Replay`: dropped |
| `index < next` and not identical to the most recently accepted token | `Protocol` failure (a rewind, or a changed id or logprob at a committed position) |
| `index > next` | `Protocol` failure (a gap) |
| A token before `Admitted`, or `Admitted` twice, or `Admitted.prompt_tokens != prompt.len()` | `Protocol` failure |
| `index >= max_new` | `Protocol` failure |
| `position0 + index` overflows, or `position` differs from it | `Protocol` failure |
| `id >= vocab_size` when `vocab_size` is known | `InvalidToken` failure |
| `logprob` present when `logprobs` was not asked | `Protocol` failure |
| `logprob` with more alternatives than the request's `logprobs = n` | Its alternatives are cut to the first `n`; then as above |

A token that asked for logprobs but carries none is accepted, as the donor passes such a
token on without figures (`serve/server.py:1383-1384`). A token with more alternatives
than asked is served with the first `n`, as the donor renders `lp[1][:n_top]`
(`serve/server.py:594`). The cut token is the one compared for a replay, recorded and
forwarded (`Checked::forwarded`), so an engine's replay of the uncut token is still a
replay. A consumer that drives the ledger with `observe` and forwards events itself
forwards the cut token too, by using `check`, `forwarded` and `commit` instead.

Further rules:

1. `position0` is fixed by the first accepted token. An engine that does not track
   absolute positions (the line-protocol engine) has positions assigned by its adapter as
   `prompt.len() + index`.
2. `check` decides without recording; `commit` records an accepted event; `observe` does
   both. The ledgered sinks check an event, forward it, and commit it only once the
   downstream sink accepted it, so an event refused with `Backpressure` and offered again
   is forwarded again, not dropped as a replay. A `Checked` from before the latest commit
   is refused as a `Protocol` failure.
3. Failures are sticky: after the first failure every call returns it. In a ledgered sink
   a failure is reported to the engine as `ConsumerGone`, so it stops, and `finish`
   returns the ledger's failure in place of whatever the engine returned. An engine
   failure is returned with `after_tokens` set to the accepted count.
4. `close` refuses a terminal after a failure, a second terminal, a `Stop` or `Length`
   terminal before `Admitted`, and a prompt whose length does not fit `u32`; after
   `close` every event is a `Protocol` failure. A `Cancelled` or `Paused` terminal before
   `Admitted` is accepted with no completion tokens: a generation cancelled before it
   started simply ends, as the donor's `generate` returns on a set cancel before any token
   (`serve/server.py:228-229`, `:1393-1394`), with no engine fault and no restart. `close`
   does not compare the engine's own figures with what it accepted (section 9, Q4).
5. `ConsumerGone` from the downstream sink is sticky. The ledgered sinks commit the
   refused event (the engine committed that step) and mark the ledger; every later event
   is still checked and committed, but not forwarded, and is answered `ConsumerGone`. A
   gap, rewind or other fault is still caught. Tokens committed after the mark are not
   counted in `completion_tokens`. `Backpressure` commits nothing, so the event is offered
   again.

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

#[derive(Clone)]
pub struct ControlHandle(Arc<ControlState>);  // the server side of the same state
impl ControlHandle {
    pub fn new() -> Self;
    pub fn probe(&self) -> ControlProbe;
    pub fn cancel(&self);                     // client gone, shutdown, server decision
    pub fn pause(&self, keep: bool);          // fair slices
    pub fn wrap(&self);                       // the server is stopping
}
```

Requests are sticky for the generation: once set they stay set. A later `pause(true)`
upgrades an earlier `pause(false)`; nothing downgrades it.

- **Cancel.** Set by the client-disconnect watcher, by shutdown, and by the server when it
  has decided the answer is finished (a stop id or stop string, the loop guard, the token
  limit it enforces). After the engine observes it, the engine MUST stop advancing and
  return `Terminal { stop: Cancelled }` or a failure. The line-protocol engine writes
  `STOP` (or `STOP <rid>` in multi mode) when the engine advertises `stop`, then drains to
  the request's `DONE` before returning. This is the donor's drain
  (`serve/server.py:1453-1504`). The FIFO place stays held until then. The deadline is
  Q6.
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
    pub reused_tokens: Option<u32>,       // DONE field 8
    pub drafts: Option<(u32, u32)>,       // accepted, offered (DONE fields 6-7)
    pub hits_lookups: Option<(u32, u32)>, // DONE fields 9-10
}

pub struct EngineTimings { pub prompt_ms: f64, pub decode_ms: f64 }

pub struct Terminal {
    pub stop: EngineStop,
    pub counts: Option<EngineCounts>,     // None for an engine without a DONE (the scripted engine)
    pub timings: Option<EngineTimings>,   // None for an engine without a clock
}

pub struct DoneFigures { pub counts: EngineCounts, pub timings: EngineTimings,
    pub finish: BoundedText }
impl DoneFigures {
    pub fn parse(fields: &[&str]) -> Result<Self, String>;  // the figures after the tag
    pub fn engine_stop(&self, pause_requested: bool) -> Option<EngineStop>;
    pub fn terminal(&self, stop: EngineStop) -> Terminal;
}
```

The 5, 8 and 10 field forms of the donor's `DONE` line stay distinguishable through the
`Option` fields (`serve/server.py:1192-1199`): `DoneFigures::parse` reads the drafts and
reuse fields only with at least 8 figures and the hit fields only with at least 10, and
ignores extra fields, as the donor does. Counts are read as Python's `int()` reads them
and must fit `u32` (a negative count is refused, where the donor's `int()` accepts it;
section 5, item 2); times as Python's `float()` reads them. `cancel` is `Paused` when the
adapter asked for a pause, else `Cancelled` (Q5). Figures are returned per call, never
left in shared mutable state on the engine object (the donor's `last` attribute).

Usage rules:

1. Usage comes only from what the backend committed and reported. It is never estimated
   from text, bytes, words or message counts (the archived contract's rule).
2. `prompt_tokens` on the wire is the length of the prompt ids sent, as the donor reports
   it (`serve/server.py:4712`, `:4905`); `LedgerCounts::prompt_tokens` carries it. Across
   several engine calls within one request (slices and continuations), the turn driver
   merges figures as ENG-10 specifies.
3. `completion_tokens` on the wire counts every token the server consumed from the
   ledger for the answer, including a stop token, because the donor increments its counter
   before its stop check (`serve/server.py:4507`). `LedgerCounts::completion_tokens` is
   the number of tokens the ledger accepted and the consumer took (tokens recorded after
   `ConsumerGone` are not counted); the turn driver may consume fewer of them when it
   stops early.
4. `reused_tokens` (reported as cached tokens) come from the terminal's `DONE` counts
   only, as the donor reads `reused` from the `DONE` line alone (`serve/server.py:1197`,
   `:4712`, `:5005`). Reuse reported in `Admitted` or in `PromptProgress` feeds the
   stream's prompt progress, not usage. An engine that reports none reports no cached
   tokens; the server does not infer them.
5. All sums use checked integer arithmetic. An overflow is a `Protocol` failure raised
   before any success terminal reaches the client.
6. `EventLedger::close` does not compare the engine's `generated` or `prompt_tokens` with
   what it accepted; they are passed through in `LedgerCounts::engine` (Q4).

## 10. Failures

```rust
pub struct EngineFailure {
    pub kind: FailureKind,
    pub message: BoundedText,             // the donor's text where it has one; at most 4096 bytes
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
    StartFailed,   // the engine exited before READY, or the guard refused it
}
```

| Kind | Constructor and text | Poisoned | Donor origin | Server mapping (rendered by console-http) |
| --- | --- | --- | --- | --- |
| `Died` | `stopped_unexpectedly(code)`: "the engine stopped unexpectedly (exit code N)", `None` for an unknown code; `died(reason)` | yes | `EngineDied`, `serve/server.py:412-413`, raised at `:1380`, `:1406` | 503 server_error, "<reason>; the next request restarts it"; the next turn restarts the engine |
| `Reported` | `reported(text)` | no | `ERR` line, `serve/server.py:1448-1452` | 400 invalid_request_error before the first byte; a stream error after it. The non-finite retry (an `ERR` containing "non-finite" before the first token is retried once) is a server rule applied to the message, as in the donor |
| `NotReady` | `not_ready()`: "the model is starting; try again in a moment" | no | `max_context <= 0`, `serve/server.py:3680-3681` | 503 |
| `NeverAnswered` | `never_answered(quiet_s)`: "the engine never answered this request (N s without a line of its own); it was stopped" | no | multi quiet timeout, `serve/server.py:1597-1610` | As the donor; detail in ENG-07 |
| `InvalidToken` | `negative_token(id)`: the donor's "the engine could not pick a token (it wrote the id N: its sampling failed - the engine's log says why)"; `out_of_vocabulary(id, n)`: the console's own text, with the id and size readable through `out_of_vocabulary_parts` | no | negative `T` id (`engine_token`, `serve/server.py:560-568`) | A negative id: as the donor's message. An id outside the vocabulary: the donor's tokenizer `IndexError`, "token id N is outside the vocabulary (V)", answered 400 `invalid_request_error` "malformed request (IndexError: ...)" before the first byte and only logged after it, with finish `length` (section 12.1, rule 10) |
| `Unsupported` | `unsupported(what)`: "unsupported: <what>" | no | `Service.check_request` refusals, missing optional members | 400 before anything is sent |
| `Protocol` | `protocol(detail)`: "engine protocol violation: <detail>" | yes | none: new, from the ledger | 500 before the first byte; a stream error after; the instance is poisoned |
| `StartFailed` | `exited_before_ready(log)`: "the engine exited before it was ready (see <log>)"; `ProvenanceRefused::to_failure` | yes | `serve/server.py:941-947`; section 5.1 | Start-up error; 503 for requests while no engine runs |

No text above carries a product name (BRAND-1). A `ContextOverflow` is not an engine
failure: the server's context rule raises it before any engine call.

## 11. Engine factory, instance and lifecycle

```rust
pub trait EngineFactory: Send + Sync + 'static {
    fn kind(&self) -> EngineKind;
    /// Called on the driver thread. The returned instance never leaves it.
    fn start(&self, cfg: &EngineStartConfig) -> Result<Box<dyn EngineInstance>, EngineFailure>;
}

#[non_exhaustive]
pub struct EngineStartConfig { pub context: Option<u32> }   // new(), with_context(n)

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

    /// The submit-and-pump form (section 4.1). None for a single-conversation engine.
    fn multi(&mut self) -> Option<&mut dyn MultiEngine> { None }

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

pub enum Health { Alive, Ended { exit_code: Option<i32>, note: Option<BoundedText> } }
pub struct ControlCommand { pub line: String, pub expect: String, pub timeout: Duration }
pub enum AloneReason { Pictures, Logprobs, Ablation }  // "has pictures", "asks for
                                                       // log-probabilities", "uses refusal ablation"
pub enum ShutdownOutcome { Graceful, Killed, AlreadyEnded }

/// NotReady when max_context is 0 (nothing sent); else generate behind a LedgeredSink.
pub fn generate_ledgered(engine: &mut dyn EngineInstance, req: &GenerationRequest,
    control: &ControlProbe, downstream: &mut dyn EventSink)
    -> Result<(Terminal, LedgerCounts), EngineFailure>;
```

Lifecycle operations of the donor map onto these as follows. A restart is `shutdown`
followed by `EngineFactory::start`. A context reload is `shutdown` followed by `start`
with the new context; it uses the graceful path, not a kill (deviation FIX-1.1). An idle
unload is `shutdown` with no immediate `start`. Every `start` is followed by
`require_synthetic` before the instance serves a request (section 5.1).

### 11.1 Mapping of the donor's optional engine members

The donor discovers optional members with `hasattr`. Each one has a named place here.

| Donor member | Seam element |
| --- | --- |
| `max_context` | `EngineDescriptor::max_context` |
| `generate(ids, max_new, sampling, cancel, embeddings)` | `EngineInstance::generate` with `GenerationRequest` and `ControlProbe` |
| `info` | `EngineDescriptor::info` and `EngineCaps` (`apply_info`) |
| `can_stop`, `can_pause`, `multi` | `EngineCaps::stop`, `pause`, `multi`; `multi` engines also offer `EngineInstance::multi` |
| `stop()` | `ControlHandle::cancel` |
| `pause(keep)` | `ControlHandle::pause` |
| `wrap()` | `ControlHandle::wrap` |
| `alive()`, `exit_code()`, `death_note()` | `EngineInstance::health` (`Health::Ended { exit_code, note }`) and `EngineFailure::message` |
| `restart()` | `shutdown` then `EngineFactory::start` |
| `close()` | `EngineInstance::shutdown` |
| kill | `EngineInstance::shutdown` at its deadline (`ShutdownOutcome::Killed`) |
| `set_context(n)` | `shutdown` then `start` with `EngineStartConfig::with_context(n)` (FIX-1.1) |
| `command(line, expect, timeout)` | `EngineInstance::command` with `ControlCommand` |
| `use(alone)` (mixed GPUs) | `EngineInstance::use_layout` with `AloneReason` |
| `last` | `Terminal::counts` and `Terminal::timings`, per call (`DoneFigures`) |
| `progress` | `EngineEvent::PromptProgress` |
| `prefill_tok_s_mean` | Computed by the server from `PromptProgress::tok_s` |
| `stat` | `EngineEvent::Sample`, `EngineInstance::sample` |
| `stat_history` | Kept by the server's recorder from `Sample` events (the donor keeps 120) |
| `vram` | `EngineSample`, extended with typed parts by the GPU-map package (Q7) |
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

These types are not part of `console_core::engine`; the parser packages define them over
the items of the turn driver (ENG-10, section 12.1), which supplies the timings.

Rules:

1. Every turn ends with exactly one `Terminal`, including a failed or cancelled turn. No
   event follows it.
2. The concatenation of the `Content` text equals the answer text of the non-streamed
   response; the same holds for `Reasoning`. Independent tests check this across
   dialects (CNF-14).
3. The event names and fields of the parser are defined by PRM-09 and PRM-12; this
   contract fixes only the ordering rules above.

### 12.1 The turn driver (ENG-10)

The turn driver, `console_core::turn`, sits between the token level and the event level.
It drives one request's turn on the engine and yields token-level items; the parser
packages build the `TurnEvent`s of section 12 over them. Every name below is exported from
`console_core::turn`.

```rust
pub struct TurnDriver { /* Clone; owns the driver thread through a job channel */ }
impl TurnDriver {
    pub async fn start(factory: Arc<dyn EngineFactory>, fifo: EngineFifo,
        settings: TurnSettings, observer: Arc<dyn TurnObserver>, log: FifoLog)
        -> Result<TurnDriver, EngineFailure>;           // the first start, through the guard
    pub fn context_budget(&self, prompt_tokens: usize, max_new: Option<&PyInt>)
        -> Result<u32, TurnError>;                      // the context rule
    pub fn turn(&self, req: TurnRequest) -> TurnStream; // spawns the turn's task
    pub async fn restart(&self) -> Result<(), TurnError>;
    pub async fn reload_context(&self, context: u32) -> Result<(), TurnError>;
    pub async fn switch_engine(&self, factory: Arc<dyn EngineFactory>,
        cfg: EngineStartConfig) -> Result<(), TurnError>;   // the model switch's entry point
    pub async fn unload(&self) -> Result<(), TurnError>;
    pub async fn close(&self);
    pub fn set_stopping(&self, stopping: bool);
    pub fn max_context(&self) -> u32;
    pub fn descriptor(&self) -> Option<EngineDescriptor>;
    pub fn fifo(&self) -> &EngineFifo;
}

pub struct TurnRequest {
    pub generation: GenerationRequest,     // the driver assigns rid and caps max_new per call
    pub units: Units,                      // Units::ONE for a request
    pub alone: Option<AloneReason>,        // passed to use_layout before the first call
    pub vocab_size: Option<u32>,           // the tokenizer's vocabulary
    pub continuation: Box<dyn ContinuationPolicy>,
}

pub struct TurnStream { /* the consumer's side */ }
impl TurnStream {
    pub async fn next(&mut self) -> Option<TurnItem>;
    pub fn finish(&mut self, why: CallerFinish);   // the server decided the answer is finished
    pub fn cancel(&self);                          // the client went away, or shutdown
    pub fn control(&self) -> &ControlHandle;       // pause and wrap
}

pub enum TurnItem { Ping(Option<PingProgress>), Token(CommittedToken), Done(Box<TurnOutcome>) }
pub struct PingProgress { pub total: u32, pub cache: u32, pub processed: u32, pub time_ms: i64 }
pub struct TurnOutcome {
    pub end: TurnEnd, pub finish: &'static str, pub prompt_tokens: u32,
    pub completion_tokens: u32, pub figures: Option<SegmentFigures>,
    pub timings: Option<RequestTimings>, pub cancelled: bool,
}
pub enum TurnEnd { Ended(EngineStop), NonFiniteCut, CancelledBeforeEngine, Failed(TurnError) }
pub enum TurnError { ContextOverflow { message: String }, Starting, Request(RequestError),
    Engine(EngineFailure) }

pub trait TurnObserver: Send + Sync + 'static {   // every method has an empty default
    fn queued(&self); fn dequeued(&self); fn active(&self, start: &TurnStart);
    fn generated(&self, tokens: u32); fn sample(&self, sample: &EngineSample);
    fn place_released(&self); fn inactive(&self); fn finished(&self, record: &TurnRecord);
}

pub trait ContinuationPolicy: Send + 'static {
    fn after_call(&mut self, call: &CallSummary<'_>) -> Continuation;
}
pub enum Continuation {
    Finish,
    Again { prompt: Arc<[u32]>, max_new: u32 },        // a fair slice: same attempt
    NextSegment { prompt: Arc<[u32]>, max_new: u32 },  // after a blocked loop-guard call
}
```

Rules:

1. **Threading.** The engine instance is created on the driver thread and never leaves
   it (section 4). Each turn runs in a spawned task that holds the FIFO place; the place
   travels with each job to the driver thread and comes back with the job's reply, so it
   is given back only after `generate` has returned (section 4, rule 4), even when the
   turn's task is gone. Engine events reach the task over a bounded channel; a full
   channel holds the engine (backpressure), a closed one answers `ConsumerGone`.
2. **The consumer.** Dropping a `TurnStream` sets the turn's cancel and nothing else. The
   task stops forwarding, the engine reads the cancel at its next step (STOP), the call
   returns (the drain), and then the place is given back, in that order.
   `TurnStream::finish` is the server's own cancel (a stop id or string, the loop guard):
   later tokens are not handed out and do not count. `completion_tokens` counts the tokens
   the consumer took, a stop token included, and an id outside the vocabulary that ended
   the turn (rule 10). A failure the engine call returns once the cancel is set, and a
   failure that reaches the stream after the server's finish or after the stream was
   dropped, is part of the drain (the donor's drain swallows an `ERR` or the engine's end
   read after STOP): the turn ends as a cancelled stop, and the server's finish, `cancel`
   or `disconnect` decides the word. A poisoned failure is still recorded, so the next
   turn restarts the engine (rule 6).
3. **Admission.** Every path that starts an engine (first start, `restart`,
   `reload_context`, `switch_engine`, and the start after an idle unload or a death that
   a turn makes) goes through one admission step on the driver thread, which calls
   `require_synthetic` before the instance is kept (section 5.1). A refused instance is
   shut down at once, the operation fails with `ProvenanceRefused::to_failure`, and
   nothing is served from it; the next turn tries the start again, through the guard.
   Exclusive operations hold every FIFO place, and never resize the FIFO: the FIFO follows
   the engine's places at the first start and in a turn's preparation (the donor's
   `ensure_engine`), where the turn holds one place. `max_context` reads 0 while a start
   runs; an idle unload leaves the last context, and a start that fails or is refused puts
   back the context from before it (the donor's #351), so the next request passes the
   context rule (rule 4) and reaches the turn that starts the engine again.
4. **Context rule.** `context_budget` applies the donor's rule before any engine call:
   `room = max_context - 8 - prompt_tokens`; an unset, zero or negative budget means the
   room; a budget over the room is `ContextOverflow` unless `fit_max_tokens` clamps it to
   `max(1, room)`; no room is `ContextOverflow`; `max_context == 0` is `Starting`. Each
   engine call's `max_new` is also capped by the room its own prompt leaves.
5. **Retry.** An attempt is the donor's `attempts`, run afresh for the request's first
   segment and for each `Continuation::NextSegment`; the calls of a
   `Continuation::Again` (fair slices) belong to the current attempt. An engine failure
   whose text contains `non-finite` (`Reported` or `InvalidToken`) before the attempt's
   first token runs the attempt once more from its own first prompt and budget (token 0 of
   that prompt); after tokens were sent the answer ends there (`NonFiniteCut`, finish
   `length`); a second one in the same attempt is the error. No other failure is retried.
6. **Restart.** A poisoned failure, or `health()` reporting `Ended`, makes the next turn
   restart the engine through the admission step before its call. A panic in engine code
   on the driver thread (start, `health`, `use_layout`, `generate`, `shutdown`) is caught:
   the operation fails with `Died` "the engine panicked" (poisoned), the instance is
   dropped without being called again, the place goes back once the call has unwound, and
   the next turn starts the engine again through the admission step.
7. **Keep-alives.** A `Ping(None)` while queued (the queue-ping interval); a
   `Ping(Some(..))` for each `PromptProgress`; and a `Ping` with the call's latest
   progress when the engine has been quiet for the heartbeat interval (10 s).
8. **Figures.** The figures of the calls of one attempt merge as the donor merges its
   slices (`merge_segments`); a new segment's figures replace the earlier segment's; then
   `own_prompt_figures` applies when the prompt they count is longer than the request's.
   `request_timings` gives llama.cpp's `timings`; an engine without a clock gives no
   timings and no cached tokens.
9. **Cancel deadline (Q6, the turn's half).** The turn sets no deadline on the drain: it
   waits for the engine call to return, holding the place, as the donor's
   single-conversation drain does. Only the stall watchdog (ENG-08) ends a stuck engine.
10. **An id outside the vocabulary.** The donor has no engine-side check: its tokenizer
    raises `IndexError("token id N is outside the vocabulary (V)")` when the server decodes
    the token, which its handler answers 400 `malformed request (IndexError: ...)` before
    the first byte and only logs after it, and its `run` leaves the finish at `length`. The
    driver checks each token against `TurnRequest::vocab_size` and ends the turn with that
    error (`TurnError::Request`, class `IndexError`), stopping and draining the engine; the
    token is counted, as the donor counts it (`n += 1`) before its tokenizer raises, but not
    handed out. The ledger's own failure for an id beyond `EngineDescriptor::vocab_size`
    (`EngineFailure::out_of_vocabulary`) is mapped to the same error. An id outside the
    vocabulary after the consumer's stop is never reached, as in the donor (rule 2).
11. **Not built in M1.** Several generations at once on an engine with more than one
    place (the driver thread runs one call at a time; ENG-07 builds the pump), and the
    continuations of ENG-11 beyond the `ContinuationPolicy` hook.

## 13. Implementations in this increment

| Implementation | Package | Notes |
| --- | --- | --- |
| Scripted in-process engine | ENG-02 | Reproduces `MockEngine`: script rotation, the `max_new` cut, cancel before each step, the logprob shape `(0.0, [(id, 0.0)])`, optional pacing and figures |
| Line-protocol child engine | ENG-06, ENG-07 | Speaks the line protocol written down by ENG-04; single writer for standard input; drains after STOP; multi mode over the submit-and-pump form |
| Rust fake engine binaries | ENG-05 (with CNF-05 merged into it) | Driven through the line-protocol engine; the donor's Python fakes are never run locally (decision B9) |
| Coordinator-shaped test adapter and blocking runtime adapter | ENG-19 | Models the engine track's `deliver` hook, replay after a refused delivery and the non-`Send` single owner; passes the seam battery |
| Seam conformance battery | ENG-18 | Runs every implementation above against sections 4 to 11 |

Each implementation above reports `Provenance::Synthetic`, and each passes the guard of
section 5.1. The in-process engines (the scripted engine and the ENG-19 adapters) construct
their descriptor with `Synthetic` themselves. The line-protocol client derives provenance
from the declaration in the child's start-up lines (section 5.1, rule 4): with a
declaration of synthetic provenance it reports `Synthetic`, and with any other
declaration, or none, it reports `NotSynthetic` through `Provenance::not_synthetic`. The
Rust fake engine binaries make the declaration.

The coordinator-shaped adapter shows the fit as follows. The engine track's
`StepCoordinator::execute` calls `deliver(&CommittedStep)` after its commit; the adapter's
hook calls `EventSink::deliver(Token(CommittedToken { index: position - position0,
position, id: token, .. }))`. A refused delivery becomes the hook's error, which
`HostGeneration::advance` records as a pending delivery; the next `advance` with the same
request replays the retained step and delivers the same position again, which the ledger
drops. Nothing in this increment calls `crates/backend`; the adapter mirrors the shape.

## 14. Open questions for ENG-01

These are answered, or explicitly deferred with a reason, below. They are also listed in
the register of open items, [`../checklists/analysis.md`](../checklists/analysis.md),
which says who decides each: Q1 to Q8 and Q12 are OPEN-30, Q10 is OPEN-21 and Q11 is
OPEN-01. Q9 was OPEN-29; the owner settled it on 2026-11-14. The answers to Q1 to Q8 are
ENG-01's, along the lead's guidance where the lead gave it; the engine track is asked to
confirm them (section 15), so they may change before the freeze.

| Id | Question | Answer |
| --- | --- | --- |
| Q1 | How does the synchronous, single-owner token level serve an engine with several places (`multi=<n>`)? | Answered (section 4.1), along the lead's direction (LD13). The instance stays owned by one driver thread. `MultiEngine` offers `submit`, `pump` and `running`; events are tagged with the server's `RequestId` through a `TaggedSink`; each generation ends with exactly one `Finished` returned by `pump`; an `Err` from `pump` ends every running generation; each submission carries its own `ControlProbe`, so control requests reach each generation separately. The blocking `generate` is the single-conversation case, and `generate_one` runs it over the pump form. `LedgerSet` applies one ledger per generation. Reason: it keeps the non-`Send` single owner of section 4 and needs no async runtime. The line-protocol details (line routing, quiet timeout, bounded drain) are ENG-07's. The planner record's async, `Send + Sync` trait is not available (tasks.md R27). |
| Q2 | Is `Admitted.reused_tokens` known at admission for any engine, or should reuse be reported only in progress and in the terminal? | Answered: the field stays, optional. No engine in this increment knows reuse at admission: the scripted engine has none, and the line-protocol engine learns it from `PP` and `DONE`, so their adapters send `None`. An in-process engine that decides its prefix reuse before computing (a coordinator-shaped adapter) may report it, for the stream's prompt progress. Usage does not use it: `EventLedger::close` takes reuse from the terminal's counts only, as the donor takes cached tokens from `DONE` alone (`serve/server.py:1197`, `:4712`, `:5005`); the ledger never checks the field. |
| Q3 | May an engine replay any exact earlier token, or only the most recently accepted one? | Answered: only the most recently accepted one. The engine track's coordinator retains only its latest step and answers an older position with an explicit already-committed error (`crates/backend/src/step.rs:8-9`). An exact repeat of an earlier token is a `Protocol` failure (a rewind). |
| Q4 | Does the engine's `generated` count include the stop token, and what must `EventLedger::close` require of it relative to the accepted token count? | Answered: the ledger requires nothing of it. `completion_tokens` is the count of accepted tokens the consumer took (`EventLedger::delivered()`; tokens committed after the consumer has gone are not counted), a stop token included, as the donor counts every token it takes before its stop check (`serve/server.py:4507`); `prompt_tokens` is `prompt.len()`. The engine's `generated` and `prompt_tokens` are passed through in `LedgerCounts::engine`, unchecked, because the donor's own test fixtures report figures that differ from the tokens taken: `DONE 2` after an invalid id and one good token (`serve/test_server.py:1047`), and `DONE 1 12000` for a one-token prompt with no `T` line at all (`serve/test_server.py:1325`). Whether `generated` includes a stop token is therefore engine-specific and not relied on. |
| Q5 | Is `Paused` a distinct terminal, or a `Cancelled` with a cause? | Answered: distinct. The donor's `DONE` reports `cancel` in both cases, so the line adapter maps it with `DoneFigures::engine_stop(pause_requested)`, knowing what it asked for. A distinct value lets the turn driver tell a fair-slice continuation from a stop without keeping its own flag. |
| Q6 | Which cancel deadline applies, and what happens to an in-process engine that ignores cancel beyond it? | Partly answered, the rest deferred to ENG-10 and ENG-08. The seam never abandons a running `generate`: an in-process synchronous engine cannot be destroyed, so the driver thread waits for it and the FIFO place stays held until it returns (section 4, rule 4), as the donor's drain holds it. The deadline's value, and what the server reports while it waits (a stalled turn, a watchdog note), are turn-driver and supervision policy: ENG-10 settles the turn's cancel deadline and ENG-08 the stall watchdog and the kill of a child process. The in-process engines of this increment check cancel before each step, as `MockEngine` does (`serve/server.py:228-229`). |
| Q7 | Should `Sample` carry a typed residency and memory record, or the donor's untyped `STAT` key-value map only? | Answered for M1, extension deferred. `EngineSample` carries the donor's `STAT` map (numbers where Python's `float()` reads them, else text), at most 64 entries, kept private behind `set`, `get` and `iter` so the limits hold. It is `#[non_exhaustive]`, so typed parts (residency, `VRAM` parts) are added without breaking engines when the packages that read them land: ENG-13 (GPU map) and ENG-08 (memory settle). Reason: no M1 consumer reads typed residency, and the donor's monitor reads the map. |
| Q8 | Are `TuneKnobs` a closed typed set or an opaque validated map? | Answered in shape, key set deferred to ENG-03. `TuneKnobs` is an ordered list of at most 64 knobs whose names and word values are `&'static str` and whose values are typed (`Int`, `Float`, `Word`). The names and words are meant to come from ENG-03's compile-time table; the type makes accidental use of client text harder but does not prevent it, and ENG-03's validation is what keeps client keys out (SEC-6). The table of names, ranges and words stays with ENG-03, which owns the `strata_tune` validation and the `GEN` keys, including the GLM knobs of `serve/glm_dsa_tune.py`. |
| Q9 | Decided by the owner on 2026-11-14 (OPEN-29, settled). | The server refuses to start an engine that does not report synthetic provenance, at process start and at every later restart, model switch or context reload. The mechanism (one guard function in `console-core`, no bypass, the refusal line, fail-closed handling of a line-protocol engine that does not declare synthetic provenance, the pinning tests and the note on allowing non-synthetic engines) is in section 5.1. |
| Q10 | May a later engine attach at the event level, and if so which of the duties in section 3 does it take over? | Open: an owner item (OPEN-21). It needs its own approval (Phase 3). |
| Q11 | Is the sealed-reasoning prefix accepted on input in the donor's form? | Open: an owner item of decision B2 ([naming.md](naming.md), item N1; OPEN-01), not of this seam, but it touches the event level. |
| Q12 | Which engine-track reviewer receives this draft, and what form does their acceptance take before ENG-01 freezes version 1.0? | Open (OPEN-30). Reaching the engine track goes through the owner, who has not yet said how the draft reaches it. Until the review is recorded the seam stays a draft and ENG-01 stays unticked. |

## 15. Review request to the engine track

This section is what the engine track is asked to confirm before version 1.0 is frozen
(FR-039). The review itself is not recorded here yet: who reviews, and in what form, is
Q12.

1. **Threading.** That a synchronous token level, with a `Send + Sync` factory and an
   instance owned by one driver thread that need not be `Send` (section 4), fits the
   coordinator's single owner with `Rc` and `Cell` state.
2. **Delivery.** That the post-commit `deliver` hook maps onto `EventSink::deliver` as
   section 13 describes, and that at-least-once delivery with only the most recent token
   replayable (Q3) matches the coordinator's retained step and its pending-delivery
   protocol.
3. **Positions.** That `CommittedToken::position` as the coordinator's absolute generation
   position, and `index = position - position0`, is the right key for the ledger.
4. **Several places.** That the submit-and-pump form (section 4.1, Q1) would serve a
   future engine that decodes several conversations at once, or what it would need
   instead.
5. **Control.** That cancel, pause and wrap read between steps through a `ControlProbe`
   (section 8), with no call into the instance from another thread, is something an
   engine-track runtime can honor.
6. **Usage.** That usage comes only from committed tokens and reported counts, and that
   the ledger does not rely on an engine's own `generated` figure (Q4).
7. **Failures.** That the failure classes of section 10, and which of them poison the
   instance, cover what an engine-track runtime can report.
8. **Provenance.** That the provenance type and the guard of section 5.1 leave room for
   the provenance value a later, approved engine would report (the note on allowing
   non-synthetic engines, step 1), without any change to the rule in this increment.
