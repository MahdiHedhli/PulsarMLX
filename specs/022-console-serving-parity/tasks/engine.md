# Task detail: Backend seam, engines, supervision and scheduling

Feature 022, PulsarMLX Console. This file gives the full specification of each work package
with the prefix `ENG-`. The task list, the milestone order and the binding cross-cutting
decisions are in [`../tasks.md`](../tasks.md); **a binding decision or a reconciliation
there overrides any conflicting sentence in this file**.

Provenance: rendered without paraphrase from the planning records of 2026-11-14 (one planning
agent per subsystem, reading the pinned donor source). Path shorthand: `MAYA` is the pinned
project-maya checkout (commit `7e68a30f`), `ORIGIN` is this repository at `main` when the plan
was written. Sizes are estimates. Donor names such as `MAYA_*` variables describe the donor;
the product names are in [`../contracts/naming.md`](../contracts/naming.md).

## Subsystem summary

The ENG subsystem is the backend seam and everything behind it in project-maya serve/ at 7e68a30f. That covers the in-process Engine interface and MockEngine; the StrataEngine child-process supervisor and line-protocol client, in single and rid-tagged multi-conversation modes; the FairLock FIFO with keep-alives, the queue watchdog and fair slices; and the engine lifecycle (start before the listener, ensure_engine restart after a death, unload and idle unload, context reload with fallback and atomic save, shutdown wind-down). It also covers the engine half of Service.prepare, run and _sliced (context rule, GEN/GENI encoding, slices and continuations, drain, segment merging, non-finite retry, death and error classification, timings), the prompt memo, DeepSeek restore points, the maya-vision helper process with SVE1 files and VLEND/VRECLAIM memory lending, gpu_map, glm_link and mixed_gpus, the fake engines, and the engine conformance suite. Full parity means the following. Driven by equivalent fake engines, the Rust seam produces byte-identical GEN and control lines. It reacts identically to every engine line, timeout, EOF, ERR, END and exit code. Requests go through the FIFO in the same order and hold the same places. Every documented setting, file and log-phrase dependency behaves identically, as pinned by the GPU-free tests that exercise these paths: about 200 test methods across test_multi, test_fair, test_engine_contract, test_logprobs, test_stop, test_server (engine classes), test_dashboard GpuMap, test_glm_dsa_*, test_ds4_restore_points, test_prompt_memo, test_glm_link and test_mixed_gpus, re-expressed in Rust. The seam must take three implementations without changes to the driver: a deterministic in-process fake, a line-protocol child-process adapter run against Rust fake engine binaries, and a future in-process PulsarMLX engine. The future engine plugs in through a blocking runtime adapter whose token sink matches the engine track's post-commit delivery hook: a committed token is delivered once, never rewound, and a delivery failure means the consumer has gone, not that the step failed. The NVIDIA/AMD parts (VRAM map, NVML waits, CUDA/HIP environment, GLM link mode, DeepSeek mixed GPUs, on-demand vision lending) are ported behind traits and runtime checks, verified with fixtures and fake processes, and labelled unverified on real hardware. Nothing in this increment serves a real model.

## Build order proposed by the planner

- ENG-01 first: every other package depends on the seam types.
- Then in parallel: ENG-03 (encoder), ENG-04 (codec), ENG-05 (fake binaries, no dependencies, independent oracle), ENG-09 (FIFO), ENG-15 (launch spec and GLM link), ENG-19 (runtime adapter).
- Then in parallel: ENG-02 (in-process fake; after ENG-01), ENG-13 (GPU map; after ENG-04), ENG-17 (prompt memo; after ENG-03 and console-prompt's tokenizer trait).
- ENG-06 (line engine, single mode; needs ENG-03, ENG-04 and ENG-05).
- Then in parallel: ENG-07 (multi mode) and ENG-08 (supervision), both after ENG-06; ENG-10 (turn driver; after ENG-02 and ENG-09) can run alongside them.
- Then in parallel: ENG-11 (continuations; after ENG-10 and the agreed ContinuationPolicy trait) and ENG-12 (EngineHost; after ENG-08 and ENG-10).
- Then in parallel: ENG-14 (vision; after ENG-06, ENG-09 and ENG-10) and ENG-16 (mixed GPUs; after ENG-08 and ENG-15).
- ENG-18 last (conformance suite and seam battery; after ENG-05, ENG-06, ENG-07 and ENG-19), although its protocol-profile half can start once ENG-05 and ENG-06 land.

## Work packages

<a id="eng-01"></a>
### ENG-01 Backend seam: engine trait, event model, capabilities, facts and contract document

- **Milestone:** M1
- **Rust target:** console-core::engine (mod.rs, types.rs, error.rs, caps.rs, facts.rs); specs/022-*/contracts/backend-seam.md
- **Platform:** platform-neutral
- **Risk:** medium. Every later package builds on this, so a wrong shape is expensive. The main trap is cancellation: Python relies on generator finally blocks to STOP and drain while the FIFO place is held. In Rust, `finish()` must be an explicit awaited step owned by a spawned turn task, because Drop cannot await. The trait must stay dyn-compatible because the engine kind is chosen at run time (mock, line, mixed).
- **Depends on:** nothing
- **Estimated size:** 600-800 lines of code; 250-400 lines of tests
- **Donor sources:** serve/server.py:19-21 and 191-193 (Engine Protocol), 412-428 (EngineDied, ContextOverflow, error_body), 532-568 (LpToken, parse_lp, lp_attach, engine_token: value types only), 1173-1215 (last/DONE figures, STAT parse shapes), 2643-2666, 4123-4126, 4340-4342, 4698-4701 (optional members discovered with hasattr); READERS maya-engine-contract.json contract 'In-process Engine interface'

**Behaviors to reproduce**

- Defines a dyn-compatible `Engine` trait (Send + Sync, boxed futures, no async-trait crate). It has `caps()`, `facts()` (a snapshot), `generate(GenRequest, CancelToken) -> GenerationHandle`, and optional lifecycle operations returning `Unsupported` by default: alive, restart, close (graceful QUIT), kill, set_context, exit_code, death_note, wrap, pause(keep), command(line, expect, timeout) and use_layout(alone_reason). Every optional member that upstream finds by hasattr becomes an explicit capability flag or default method.
- `GenRequest` = { prompt: Arc<[u32]> (always the whole prompt), max_new: u32, params: GenParams (typed; defined here, encoded in ENG-03), embeddings: Option<EmbeddingsRef> (GENI file path or pixels file), image: bool }. The rid is never part of the request: implementations assign it.
- `GenerationHandle` gives `next() -> Option<Result<EngineEvent, EngineError>>` with EngineEvent = Token { id: u32, lp: Option<TokenLogprobs{logprob, top: Vec<(u32, f32)>}> } | Progress(PromptProgress{read, total, reused, ms, tok_s: Option<f64>}) | Heartbeat | Done(DoneFigures). It also gives `finish(EndReason) -> Finished { figures: Option<DoneFigures> }`, which performs STOP plus drain when the stream has not ended, and `pause(keep)`. The handle borrows nothing from the HTTP connection, so a turn task can always drain.
- `DoneFigures` = { generated, prompt_tokens, prompt_ms, decode_ms, finish: Stop|Length|Cancel, drafts_accepted, drafts_offered, reused, hits, lookups } with Option for the 8-field and 10-field extensions (the 5, 8 and 10-field forms are kept apart). Figures are returned per request, never through shared mutable `last` state (upstream issue #310 class).
- `EngineError` = Died { reason: String } (maps to 503 '<reason>; the next request restarts it'), Reported { message } (engine ERR text, maps to 400 before the first byte and to a stream error after), NeverAnswered { quiet_s }, NotReady (max_context <= 0: 503 'the model is starting'), Unsupported, InvalidToken { id } (negative T id, with upstream's exact message 'the engine could not pick a token (it wrote the id N: ...)'). Each carries its upstream message text with branding neutralised.
- `EngineCaps` = { stop, pause, multi: Option<u32> (READY multi present, including multi=1), places() = max(1, multi), logit_bias, logprobs_max: Option<u8>, ablate, cvec, vision: Off|Ds4|Mm3|None, vision_lend_bytes, can_unload, can_restart, can_set_context, can_lend }. The difference between 'multi present' and 'capacity above 1' is kept.
- `EngineFacts` = { max_context, info: ordered map key -> InfoValue::Int(i64)|Str(String) (the rule: an optional minus followed by digits becomes Int, anything else stays a string, so vram_gb=60.0 stays a string), vram: Vec<VramPart>, stat: Option<Stat> plus a 120-sample history (values parsed as f64 where possible, plus a wall-clock time), progress: Option<(read, total, reused, ms)>, prefill_tok_s_mean, version: Option<String>, log_path, model_path, load_s }.
- A `CancelToken` that can be cheaply cloned (it is set by the client-disconnect watcher, by shutdown, and by the driver itself).
- The contract document specifies the seam, the three intended implementations (in-process fake, line-protocol child, blocking runtime adapter for a future PulsarMLX engine) and how each upstream duck-typed member maps to the trait. This is the document the Phase 2 and engine-attachment work targets.

**Parity tests**

No upstream test exercises the seam on its own. Its shape is pinned by the consumers' tests listed in ENG-02, ENG-06 and ENG-10. In this package: unit tests for InfoValue parsing (the vram_gb=60.0 string case from server.py:927-930), DoneFigures 5/8/10-field construction, error message texts, caps.places(). About 15 Rust tests.

**Definition of done**

The crate compiles with no dependency on console-http or console-prompt. Unit tests pass. backend-seam.md exists, and a reviewer can check every optional upstream member (alive, restart, close, exit_code, death_note, set_context, stop, pause, can_pause, wrap, multi, info, vram, stat, stat_history, progress, prefill_tok_s_mean, last, log_path, model_path, load_s, use) against a named trait method or capability. A compile-only test shows that `Box<dyn Engine>` works and that a `GenerationHandle` is `Send + 'static`.

<a id="eng-02"></a>
### ENG-02 In-process fake engine (MockEngine parity) and scriptable test engines

- **Milestone:** M1
- **Rust target:** console-engine::fake (FakeEngine plus a FakeScript builder); test-support module console-engine::fake::doubles behind the cfg(test) or test-support feature
- **Platform:** platform-neutral
- **Risk:** low. Must stay deterministic (no wall-clock-dependent token choice). Pacing tests must use small values and tolerant assertions to avoid CI flakiness.
- **Depends on:** ENG-01
- **Estimated size:** 600-800 lines of code; 400-600 lines of tests
- **Donor sources:** serve/server.py:198-240 (MockEngine), 2765-2772 (_restart_with mock branch, MAYA_MOCK_RELOAD_S), 7117, 7287-7290 (--engine mock default script, MAYA_MOCK_TOK_S); test doubles in serve/test_server.py:32 (RecordingEngine), 906-934 (RecordingPrompt, DyingEngine, NonFiniteEngine), 1099 (ErrEngine), 1150 (Paced), 1387 (HalfDead), 1869-1880 (ClockedEngine), 2166 (LifecycleEngine), HeldEngine, BudgetEngine; serve/test_fair.py:24-92 (ResumingEngine, PausingEngine); serve/test_logprobs.py:35 (LpEngine); serve/test_ds4_restore_points.py:48 (Recording)

**Behaviors to reproduce**

- Takes scripts that are already encoded (Vec<Vec<u32>>). The pulsar-console wiring encodes each script text with the tokenizer and appends the end-of-turn id, which keeps console-engine independent of console-prompt. With several scripts, each request takes the next and the last repeats. The output is cut to max_new.
- Records last_prompt and last_embeddings (and last_params, for RecordingEngine-style tests).
- caps: logit_bias = true, logprobs_max = 20; when logprobs are asked, each token carries lp = (0.0, [(id, 0.0)]) if top > 0, else (0.0, []).
- Cancellation is checked before each token, and the fake stops at once without producing a DONE.
- Pacing: delay_s per token; or tok_s with upstream's deterministic jitter, sleep = (0.8 + 0.4 * ((t*7919 + runs*104729) % 101) / 100) / tok_s. With tok_s set, it publishes DoneFigures { generated, decode_ms, prompt_ms = 0.5 * prompt_len, reused 0 } just before the last token.
- Default script when the binary runs with the mock engine: 'Thinking about it.</think>\n\nHello from the mock engine.' (the text is configurable by --script, given more than once).
- set_context on the mock sleeps MAYA_MOCK_RELOAD_S (default 2 s, read under the settings alias policy) and then sets max_context.
- Test doubles with injectable behaviour: Dying (EngineError::Died after k tokens), NonFinite (Reported('... non-finite ...') before or after the first token, once or always), ErrMidStream, Clocked (10-field DoneFigures with reused = common prefix with the previous prompt plus written tokens, as the GLM fake does), Lifecycle (counters for alive/close/restart, can_unload), Held (blocks until released, for queue tests), Pausing and Resuming (pause() lets in-flight tokens arrive, then finish=Cancel; a continuation with prompt plus written tokens reuses all but one token), Budget (honours think_budget/think_end).

**Parity tests**

This is the engine behind most upstream HTTP-level tests. Directly defining: test_fair.py ResumingEngine/PausingEngine semantics (used by FairSlices, 5 tests); test_server.py ClockedEngine and UsageAndStatus (5), TimingsDrafts (1), StatsAfterConsumerStops (1), NonFiniteRetry (4, uses NonFinite), EngineDeath (2); test_logprobs OneConversation (3, LpEngine shape). In this package: unit tests of script rotation, the max_new cut, the jitter formula, lp shape, the reload sleep and each double. About 25 Rust tests. The HTTP-level uses are re-expressed by the consumers' packages.

**Definition of done**

FakeEngine implements the ENG-01 trait. Each double listed in maya_sources has a Rust counterpart, with a doc comment naming the upstream class it reproduces. Unit tests show rotation, cut, cancel, lp shape, tok_s figures and reload. A reviewer can run `cargo test -p console-engine fake` offline with --locked.

<a id="eng-03"></a>
### ENG-03 Typed sampling parameters, request validation and the GEN-line key encoder

- **Milestone:** M3
- **Rust target:** console-core::engine::params (GenParams, validation) and console-engine::line::keys (encoder, py_repr_f64, c_g_format)
- **Platform:** platform-neutral
- **Risk:** medium. Byte parity of float formatting is the trap: Rust's {} never uses an exponent and {:?} writes '1e-5'. The strata_tune and glm_dsa_tune knobs mean nothing to an MLX engine but are kept for parity with project-maya engines. The validation half overlaps with the API planner's request-validation component; the lead should assign it once.
- **Depends on:** ENG-01
- **Estimated size:** 700-900 lines of code; 500-700 lines of tests
- **Donor sources:** serve/server.py:466-495 (DeepSeek think_soft tables), 624-718 (client_stop_strings neighbours, sampling validation, aliases), 1217-1356 (sampling_keys, penalty_keys, tune keys, logit_bias, restore keys, logprobs), 2489-2530 (check_request capability gates, ignore_eos), 4275-4278 (default merge order); serve/glm_dsa_tune.py:1-59

**Behaviors to reproduce**

- Validates request sampling fields before anything reaches an engine. Numbers given as strings are accepted. A wrong type is a 400 naming the field. The llama.cpp aliases repeat_penalty and repeat_last_n map to repetition_penalty and penalty_last_n. logit_bias ids must lie in [0, vocab) and biases in -100..100. logit_bias and ignore_eos require caps.logit_bias, ablate requires caps.ablate, and logprobs require logprobs_max >= the requested top_logprobs. Each failure is a 400 with upstream's message, sent before the engine sees anything.
- Merges defaults in upstream order: run-config sampling, then the shared Chat settings, then the request's non-null fields.
- Emits keys in exactly this order: temperature <= 0 gives ' temperature=0' and suppresses top_p, top_k, min_p and seed; no temperature gives no key (the engine default, greedy). top_p only when below 1. top_k only for a non-negative int, with 0 or more than 64 sent as 64. min_p only in (0, 1]. Penalties: penalty_repeat when != 1, penalty_freq when != 0, penalty_present when != 0, then a window when any is on (the given positive penalty_last_n, 4096 for -1, else 64); penalty_last_n == 0 suppresses every penalty key. seed only for a positive int on sampled requests.
- Thinking keys: ' think_budget=<n> think_end=<id>' only when both are ints and n > 0. For DeepSeek only, ' think_soft=<n> think_stop=<ids> think_weak=<ids> think_dig=<ids>', with the id tables supplied by console-prompt.
- Tuning keys (strata_tune object): pcie_frac, spec_min_p, spec_cum in 0..1; suffix_draft and lookup_trust in 0|1; cpu_threads > 0; read_chunks 1..16; miss_skip_w 0..1; miss_skip_from 0..1000; spec 1..16; spec_n_min 0..15. Then the glm_dsa_tune engine_keys whitelist (promote_min, prefetch_n, prefetch_rank, prefetch_blocks, mtp_keep, cpu_split, prefetch_at, vram_evict, ngram, lane_row4, graphs, pcie_frac_head) with its ranges. Values out of range or of the wrong type are dropped silently.
- ' cvec=0|1' when experimental_speed_projection is a bool; ' ablate=1' when ablate is true; ' logit_bias=<id>:<bias>,...' sorted by ascending id, with biases in C %g format; ignore_eos becomes logit_bias -100 on each end id (the id set is supplied by console-prompt).
- Restore keys ' marks=<p,...>', ' tail=<p>', ' shared=<p>' in that order, positive ints only; any `_restore` field from the client is always stripped. Then ' logprobs=<n>'. ' rid=<n>' is appended last by the multi-mode client (ENG-07), never here.
- Floats are written exactly as Python repr writes them: the shortest round-trip digits, with exponent form for exp < -4 or >= 16 ('1e-05', '1e+16'), and '1.0' rather than '1'. Pure-Rust implementation, no crate.
- A default request produces the shortest possible line (no keys).

**Parity tests**

test_server.py SamplingKeys (9 methods, including oracle strings such as ' temperature=0.7 penalty_repeat=1.1 penalty_last_n=64 seed=5') and RequestChecks (7; the engine-capability parts); test_glm_dsa_tune.py Whitelist (4), RequestBody (1), EngineLine (1); test_ds4_restore_points.py test_the_engine_line; test_logprobs.py Fields (4, the logprobs key and gate); test_server.py lines 810-829 (ablate, ignore_eos as logit_bias). Each is transcribed as a table-driven Rust test with the same oracle strings. Added: property tests that py_repr_f64 round-trips and matches a fixed table of 200 Python repr outputs (generated once and committed as a fixture; Python is not run in CI).

**Definition of done**

Every SamplingKeys, tune and restore oracle string reproduces byte for byte. The py_repr fixture table passes. Validation errors carry upstream's field names and messages. A default GenParams encodes to an empty key string.

<a id="eng-04"></a>
### ENG-04 Line-protocol codec and handshake state machine (pure, no I/O)

- **Milestone:** M3
- **Rust target:** console-engine::line::codec (EngineLine enum, ServerLine encoder, Handshake), console-engine::line::vram (VRAM line parse)
- **Platform:** platform-neutral
- **Risk:** low. Must never panic on malformed engine output. Must not reuse code from the fake engines (ENG-05), so the fakes stay an independent oracle.
- **Depends on:** ENG-01
- **Estimated size:** 500-700 lines of code; 400-600 lines of tests
- **Donor sources:** serve/server.py:924-951 (handshake), 1001-1060 (pump and routing rules), 1192-1215 (DONE, STAT parse), 1356-1451 (generate line handling), 1504-1526 (ERR then DONE), 1528-1555 (command), 532-568 (parse_lp, lp_attach, engine_token), 2242-2262 (join_ids_memo); serve/gpu_map.py:15-30 (parse); READERS contracts 'Startup handshake', 'GEN / GENI request line', 'Per-request response lines', 'Control lines', 'Several conversations at once'

**Behaviors to reproduce**

- Parses each engine stdout line into a typed enum: Info(Vec<(k, InfoValue)>), Vram(VramPart), Note(text), Ready{ctx, stop, pause, multi: Option<u32>}, Pp{rid?, read, total, ms?, tok_s?, reused?}, T{rid?, id: i64}, Lp{rid?, id, logprob, top}, Stat(map), Done{rid?, figures}, Err{rid?, message}, End(text), Vlent(bytes), Vreclaimed, Unknown (ignored, as upstream ignores it).
- rid tagging: when multi is active, T/LP/PP/DONE/ERR lines whose second field is all digits are tagged. ERR with a non-numeric second field is untagged. STAT and NOTE are never tagged.
- Handshake: fed lines until READY. Before READY, INFO pairs merge into info, VRAM lines append, NOTE lines are surfaced, other lines are ignored. READY field 1 must be a positive int; flags are 'stop', 'pause' and 'multi=<digits>' (others ignored). EOF before READY is a failed start with the message 'the engine exited before it was ready (see <log>)'. INFO engine=<v> overrides the BUILD.json version.
- DONE accepts 5, 8 or 10 fields after the tag (and rid). PP accepts 2 to 5 numeric fields. A T id below 0 maps to EngineError::InvalidToken. An LP line attaches only when its id equals the held token's id. An unreadable LP line is dropped and the token is delivered without logprobs.
- VRAM parse (gpu_map.parse): integer key=value pairs, pci normalised to dddd:bb:dd, layers 'a-b' to [a, b]; a line without dev is rejected.
- Encodes server-to-engine lines: 'GEN <max_new><keys> <ids>' and 'GENI <max_new><keys> <file> <ids>' (ids comma-joined, decimal, as the last field; the GENI file must contain no whitespace, otherwise EncodeError), 'STOP', 'STOP <rid>', 'PAUSE', 'PAUSE keep', 'PAUSE <rid>', 'PAUSE <rid> keep', 'WRAP', 'QUIT', 'VLEND', 'VRECLAIM', and optionally 'LOGP <n_ctx> <ids>' for the conformance tool only.
- join_ids_memo: reuses the previous prompt's comma-joined string in 4096-id blocks. The output must be byte-identical to a plain join, and it is used only on the single-conversation path when the prompt memo is on.
- A line of several megabytes (a million-token prompt) is handled without fixed buffers.

**Parity tests**

test_logprobs.py Fields (parse_lp/lp_attach cases); test_prompt_memo.py JoinIdsMemo (2); test_dashboard.py GpuMap.test_parse; test_server.py lines 1011-1019 and 1318-1345 (generate on a hand-built engine: empty answer, negative id), StaleDoneAfterErr (2, codec half); test_engine_contract test_01_ready flag rules. Plus new table tests over every line form from the contract (about 60 cases) and a seeded fuzz-style test (random splits, unknown lines, truncated fields: no panics, unknown lines ignored).

**Definition of done**

Every line form in the four wire contracts round-trips (encode, or parse into the enum) under table tests. Fuzz tests run with no panic. engine-wire.md in specs/022-*/contracts restates the grammar and cites the upstream line ranges. join_ids_memo equals a plain join on a randomised corpus.

<a id="eng-05"></a>
### ENG-05 Fake engine binaries speaking the line protocol (GLM fake, multi fake, silent, slow-stop)

- **Milestone:** M3
- **Rust target:** new crate console/crates/console-fake-engines (std plus serde_json only), binaries console-fake-engine, console-fake-multi-engine, console-fake-silent-engine, console-fake-slow-stop-engine
- **Platform:** platform-neutral
- **Risk:** medium. The fakes are an independent oracle for the client. They must be written from the Python fakes and the contract, not from the Rust client's codec, otherwise one bug would hide in both. Timing-based behaviour (3 ms round robin, 1.5 s slow stop) needs scaling to keep CI quick and stable. The Windows .bat wrapper for the fakes is not reproduced. The env names FAKE_ENGINE_*, FAKE_MULTI_INTERLEAVE and MAYA_GLM_SLOT_KEEP are kept because they are the fixture and engine interface.
- **Depends on:** nothing
- **Estimated size:** 800-1000 lines of code; 300-500 lines of tests
- **Donor sources:** serve/glm_dsa_fake_engine.py:1-177; serve/fake_multi_engine.py:1-111; inline engines in serve/test_multi.py:236-259 (SILENT_ENGINE) and 303-333 (SLOW_STOP_ENGINE); tools/maya_names.py:1-78 (MAYA_X / STRATA_X aliasing the GLM fake imports); READERS contract 'Fake-engine control environment'

**Behaviors to reproduce**

- All the fakes are started exactly like an engine: `<exe> --serve <args>`. stdin is read on its own thread so that STOP, PAUSE and WRAP reach a running request. QUIT and stdin EOF end the process with exit code 0. Nothing but protocol goes to stdout.
- GLM fake: --max-context N (default 32768). stderr prints 'glm fast: CUDA0 VRAM before the expert pool: ... state/KV (<ctx> ctx) 1.50' and the 'session is up' banner. stdout prints the full GLM INFO line (context, kv, expert_slots, expert_cache_mib, engine_kind=glm-fast, experts, vram_slots, vram_gb, ram_slots, ram_gb from FAKE_ENGINE_RAM_GB default 170.0, mtp, vision_lend, cpu_threads, pcie_share) and then 'READY <ctx> stop pause'.
- GLM fake, per GEN/GENI: one 'PP n n 1.0 1000.0', then 'T <id>' per token with a 1 ms sleep, a 'STAT ...' line with the 12 named keys every 8 tokens, and 'DONE n prompt 1.0 ms finish 0 0 reused n n', where reused is the common prefix with the held conversation (prompt plus what it wrote).
- GLM fake, answer source: FAKE_ENGINE_IDS (default the bytes of 'hello') repeated up to max_new, or FAKE_ENGINE_SCRIPT (a JSON list of id lists, re-read at every GEN; the k-th GEN since the file last changed gets the k-th list, and the last repeats). finish is 'stop' when the answer runs out with max_new still larger, unless FAKE_ENGINE_REPEAT=1.
- GLM fake, controls: think_budget/think_end or WRAP force think_end as the next token and skip the scripted thinking; STOP, PAUSE and PAUSE keep end the request with 'cancel'; a stray STOP between requests is discarded; VLEND/VRECLAIM answer ERR; an unknown command answers "ERR unsupported command '<cmd>'"; FAKE_ENGINE_GEN_LOG appends every GEN line to a file; with MAYA_GLM_SLOT_KEEP=1 (or STRATA_GLM_SLOT_KEEP), QUIT first writes <FAKE_ENGINE_DIR>/kept-<pid>.json and prints 'NOTE sessions: kept the conversation (N tokens)'; FAKE_ENGINE_IGNORE_QUIT=1 ignores QUIT and stdin EOF.
- Multi fake: n comes from the last argv item (default 2). It prints 'INFO engine=fake-multi', 'INFO logprobs=20', 'READY 4096 stop pause multi=<n>'. 'GEN <max_new> ... rid=<id> <ids>' answers each prompt id plus 1000, cut to max_new, one token per running request in turn every 3 ms. 'STOP <rid>' ends that request alone with 'cancel'. A GEN beyond n answers 'ERR <rid> all <n> conversation states are busy'. With logprobs=<k>, an 'LP <rid> <id> <lp> <id>:<lp>...' line follows each T. FAKE_MULTI_INTERLEAVE=<p> reads prompts p ids at a time, with one PP per piece, while running requests decode. A GEN without rid gets an untagged ERR.
- Silent fake: prints one PP and then nothing (for the quiet timeout and the bounded drain). Slow-stop fake: looks at STOP only after a 1.5 s chunk (shows the next request never reads the stopped one's tokens). Both keep upstream timing values but take an env scale factor so tests can run faster.

**Parity tests**

These fakes are the fixtures behind test_multi.py (15), test_stop.py ServerStops (the engine half), test_logprobs SeveralConversations (1), test_glm_dsa_serve ContractTestOnTheFake, HistoryReuse (2) and WebAppHistory (4), test_glm_dsa_api (23, HTTP-level, re-expressed by the API planner against these fakes), and test_glm_dsa_tune EngineLine. In this package: black-box tests that spawn each binary and check its transcript against the upstream docstring behaviour (READY line, DONE field count, reused prefix, the SCRIPT k-th rule, kept file, IGNORE_QUIT, busy ERR, interleave PP). About 25 tests.

**Definition of done**

Four binaries build with no dependency on any other console crate. The transcript tests pass. Each binary's --help or doc comment lists its env controls. The binaries never read from or write to the network. A reviewer can compare each documented control with glm_dsa_fake_engine.py and fake_multi_engine.py line by line.

<a id="eng-06"></a>
### ENG-06 Line-protocol child engine: spawn, handshake, pump, single-conversation generate and drain

- **Milestone:** M3
- **Rust target:** console-engine::line::engine (LineEngine), console-engine::line::io (writer task, reader task)
- **Platform:** platform-neutral
- **Risk:** high. This is where correctness bugs would leak one request's tokens into the next. The unbounded single-mode drain is required for correctness, so the FIFO place must stay held until finish() returns. Process tests must be robust on a loaded macOS CI runner (generous timeouts, scaled fakes).
- **Depends on:** ENG-01; ENG-03; ENG-04; ENG-05
- **Estimated size:** 900-1200 lines of code; 500-700 lines of tests
- **Donor sources:** serve/server.py:881-1060 (StrataEngine __init__, _pump, _vram_line), 1173-1199 (last), 1356-1526 (generate, _done_after_err, command), 1549-1555 (wrap), 1678-1700 (pause, stop), 2093-2104 (MAYA_TURN_TRACE marks); READERS StrataEngine key_behaviors 1-6 and 11

**Behaviors to reproduce**

- Spawns [exe, '--serve', *args] with cwd and env from the launch spec (ENG-15). stdin and stdout are pipes; stderr is appended to the log file or discarded. The spawn tuple is kept so the same command can run again.
- Version: read from BUILD.json beside the exe ({'version': ...}), overridden by INFO engine=<v>. Blocks until READY with no timeout by default (an optional ready timeout, default 0 = off, is a listed deviation).
- One reader task per start turns stdout lines into the shared channel. A later VRAM line replaces that device's entry. 'END <text>' marks the engine ended at once while the request still receives its DONE. EOF marks it ended and wakes every waiter with Died. Output from a process already replaced by a restart is dropped, so a late EOF cannot mark the new engine dead.
- One writer task owns stdin. Every line goes through it as a whole, which replaces upstream's unsynchronised writes. A failed write maps to Died('the engine stopped unexpectedly (exit code N)').
- generate (single mode) writes the GEN/GENI line (using join_ids_memo when the memo is on) and then reads lines with a 10 s quiet timeout. A timeout or a PP line yields Heartbeat. A PP line also updates progress (read, total, reused, ms) and prefill_tok_s_mean. A T line yields a token, held until its LP line when logprobs were asked; the hold is released at the next non-LP line or at a quiet timeout. STAT and NOTE are side effects. DONE ends the stream with its figures. 'ERR <msg>' yields Reported(msg) after waiting up to 0.5 s for a trailing DONE, which is swallowed; any other line during that wait ends the wait and is dropped, as upstream does.
- Cancellation is checked on every T and PP line and at every quiet timeout.
- Early end (finish() before DONE: the consumer stopped at a stop token, the client is gone, or cancel was set): writes STOP only if READY advertised stop, then drains to this request's DONE, ERR or EOF with NO upper bound. After MAYA_DRAIN_S (default 60, minimum 1) it logs once that it is still waiting; the drain ends only through DONE/ERR/EOF or the stall watchdog (ENG-08). STAT lines during the drain are parsed. EOF during the drain is pushed back so the next reader sees it.
- command(line, expect, 60 s): only between requests (the caller holds every FIFO place); returns the expected answer line; ERR becomes Reported; no answer becomes Reported('the engine did not answer <CMD>'); EOF becomes Died.
- wrap() writes WRAP. pause(keep) writes 'PAUSE' or 'PAUSE keep'. stop() writes STOP only if can_stop and never carries a rid.
- MAYA_TURN_TRACE: monotonic marks gen_start, gen_written, gen_flushed, first_t and a trace line at the first token, behind the setting.

**Parity tests**

test_multi.py AStoppedLongPrompt (2; with fake_multi_engine argument 1 and the slow-stop fake) and Engine (the single-path assertions); test_server.py StaleDoneAfterErr (2), EngineDeath (2), PromptProgressStream (3, the progress values), StatsAfterConsumerStops (1), EngineEndTests.test_end_ahead_of_done... and test_a_replaced_engines_late_end... (2), lines 1318-1345; test_engine_contract test_04_gen_done, test_06_stop and test_08_wrap from the client side. Re-expressed as Rust integration tests that drive console-fake-engine and console-fake-slow-stop-engine. About 22 tests.

**Definition of done**

All listed tests pass against the Rust fakes on macOS. A test shows that a request cancelled during a slow prompt chunk never hands its T/DONE lines to the next request. A test shows that a late EOF from a replaced process does not mark the new process dead. Under a stress test (100 requests, random cancels) stdin lines are never interleaved.

<a id="eng-07"></a>
### ENG-07 Multi-conversation mode: rid tagging, routing, quiet timeout and bounded drain

- **Milestone:** M3
- **Rust target:** console-engine::line::multi
- **Platform:** platform-neutral
- **Risk:** medium. Timing-sensitive tests (interleaving, quiet timeout) need scaled timeouts and assertions on order rather than exact times. Upstream's untagged ERR is not delivered to any request and leaves it waiting out the quiet timeout; parity reproduces that (see open questions).
- **Depends on:** ENG-06
- **Estimated size:** 500-700 lines of code; 400-600 lines of tests
- **Donor sources:** serve/server.py:1039-1060 (_route), 1139-1171 (rid counter and routes across restarts), 1557-1676 (_generate_multi), 1678-1691 (pause with rid), 7297-7299 (FIFO capacity from multi); serve/fake_multi_engine.py; READERS contract 'Several conversations at once'

**Behaviors to reproduce**

- Active whenever READY carried multi=<n>, including n=1 (the protocol is tagged while the FIFO stays at 1 place).
- Each request takes its rid from a counter that starts at 1 and lives across engine restarts. ' rid=<n>' is appended after all other keys. GEN/GENI lines are not passed through join_ids_memo in multi mode.
- The router sends T/LP/PP/DONE/ERR lines with a numeric second field to that rid's channel. Lines for an unknown rid are dropped, except an ERR whose rid is unknown, which falls into the shared channel, as do untagged ERRs. STAT and NOTE are handled centrally.
- Per-request poll period: 10 s, or min(10, max(0.2, MAYA_REQUEST_QUIET_S / 2)) when the quiet limit is set. After MAYA_REQUEST_QUIET_S (default 900, 0 = off) without a line of its own, the request writes 'STOP <rid>', logs, and fails with Reported('the engine never answered this request (N s without a line of its own); it was stopped'). Nothing is drained after that.
- Early end writes 'STOP <rid>' and drains this rid's channel for at most MAYA_DRAIN_S. Past that it logs and continues. The route entry is removed only if it still belongs to this request.
- pause(keep) writes 'PAUSE <rid>[ keep]' for the calling request (taken from the request handle, not thread-local state).
- DONE figures are returned per request (fix for upstream issue #310 kept: requests decoded together never report each other's figures).
- After a restart, every channel still waiting on the dead process receives Died. Routes and the counter survive, so a new request never takes the number of a request that is still unwinding.

**Parity tests**

test_multi.py Engine (6: ready_says_how_many, concurrent_requests_each_get_their_own_tokens, each_request_reads_its_own_done_figures, a_restart_does_not_hand_out_a_number..., a_consumer_that_stops_ends_only_its_request, an_engine_error_reaches_its_request), Interleaved (3), AWedgedRequest (2: never answers, bounded drain; with the silent fake); test_logprobs SeveralConversations (1); test_stop.py runs with fake multi argument 1. Re-expressed against console-fake-multi-engine and console-fake-silent-engine with scaled timeouts. About 13 tests.

**Definition of done**

Every listed test passes. A test reproduces the rid-reuse-after-restart scenario upstream fixed and shows it cannot recur. A stress test with 4 places and random cancels ends with an empty routing table and every FIFO place returned.

<a id="eng-08"></a>
### ENG-08 Engine supervision: restart, graceful close, kill, stall watchdog, death notes, start narration, context cost and memory settle

- **Milestone:** M3
- **Rust target:** console-engine::supervise (restart, close, kill, death_note, narrate, context_cost), console-engine::activity (ProcessActivity trait plus macOS and Linux samplers), console-engine::settle (MemorySettle trait plus macOS vm_stat and NVML-pid variants)
- **Platform:** hardware-or-os-specific
- **Risk:** medium. The watchdog decision is injected with fake samples, so it is fully testable. Real sampling on macOS and Linux is OS-specific: unit-test it on its own process, and mark the NVML path unverified on hardware. The Python class defines stop() twice; the shadowed QUIT variant is dead code and is not reproduced. The context-reload use of STOP plus kill is handled in ENG-12 under a listed deviation.
- **Depends on:** ENG-06
- **Estimated size:** 800-1100 lines of code; 500-700 lines of tests
- **Donor sources:** serve/server.py:85-151 (mac_free_bytes, wait_gpu_release, nvml_pids), 721-770 (stall, quiet and drain settings, engine_frozen), 828-878 (narrate_start), 958-983 (_context_cost, set_context), 985-999 (dead QUIT variant of stop), 1062-1171 (death_note, alive, _activity, _stall_check, _end, exit_code, restart), 1702-1728 (close); READERS contracts 'Engine stderr log phrases', 'Process exit codes', 'Timeouts and watchdog settings'

**Behaviors to reproduce**

- restart(): kill, wait up to 20 s, run the memory settle, wake every waiter with Died, run the stored command again. The rid counter, routes and previous info survive. A failed start keeps the previous max_context, so later size checks do not see 0, merges the old info with the new and returns the error.
- close(): writes STOP if can_stop, then QUIT. Waits up to MAYA_ENGINE_QUIT_S (default 50) while surfacing NOTE lines from the reader channel, then kills, logging 'the engine did not end within N s'.
- set_context(n): rewrites '--max-context n' in the stored args, or appends it, for the next start.
- Stall watchdog (MAYA_ENGINE_STALL_S, default 90, 0 = off): while the engine is silent, take a baseline soon after its last line. At the window, end the engine only if it used CPU <= max(0.5 s, 2 percent of the window), read and wrote <= 1 MiB of disk, and no GPU was busier than 5 percent (from a GpuBusy hook). Otherwise re-baseline and look again one window later. Ending prints the upstream reason and maps to Died(reason) with no STOP and no drain. With no activity sampler, nothing is ended.
- ProcessActivity: CPU seconds and disk bytes for a pid. Linux reads /proc/<pid>/stat and /proc/<pid>/io; macOS uses proc_pid_rusage through libc. Selection is at run time, so the code compiles on every target. When to fire on macOS is a listed deviation.
- death_note(): reads the last 4096 bytes of the log; 'issue #29' gives the engine-watchdog text and "a GPU's state is unknown" gives the GPU-fault text; return code -2 or -15 (SIGINT or SIGTERM) gives the outside-signal text; otherwise the out-of-RAM text. All texts keep their meaning with upstream branding, URLs and quant names removed.
- exit_code(): waits up to 5 s.
- narrate_start: polls the log every 0.5 s from the start offset until READY, prints the upstream progress lines for the phrases 'PLE on', 'expert arena:', ' loaded ' with 'GiB at', 'expert cache ' with ' slots, ' and without 'auto', 'session is up' and 'WARNING - <text>', plus 'still starting (N s)' every 20 s.
- _context_cost: after READY, scans at most 8 MiB of the log from the start offset for '(CUDA|HIP)N VRAM before the expert pool: ... state/KV (N ctx) X' and sets info.kv_ctx (max) and info.kv_gb (sum, rounded to 3 decimals).
- Memory settle between engine runs: on macOS, parse `vm_stat` (free + inactive + purgeable + speculative pages times the page size) every 0.5 s until the rise is under 1 GiB, capped at 60 s. Elsewhere, wait until the NVML pid list (from console-host) no longer contains the pid or its descendants, or 5 s when NVML cannot say, with upstream's log lines. The settle is injectable so tests can skip it (upstream tests set MAYA_GPU_RELEASE_S, which no code reads).
- Exposes the REPORT_LINES phrase set as a constant for the report feature (owned elsewhere).

**Parity tests**

test_server.py StallWatchdog (4: stuck, working, without_psutil_nothing_is_ended re-expressed as 'without a sampler', the_config_env_reaches_the_server), EngineEndTests (test_a_gpu_fault... and test_the_watchdog_and_ram_notes_are_unchanged: 2), FailedRestartKeepsContext (1); test_multi test_a_restart_does_not_hand_out_a_number (restart half); test_engine_contract test_99_quit (exit 0, from the client side); test_glm_dsa_serve Released (3, kept-<pid>.json written on close with MAYA_GLM_SLOT_KEEP). Plus new tests: the vm_stat parser on captured fixture text, the /proc parser on fixture files, context-cost regex fixtures, narration phrase fixtures. About 25 tests.

**Definition of done**

Every listed test passes on macOS. The vm_stat and /proc parsers have fixture tests. A test shows that a failed restart keeps max_context and the rid counter. A test with FAKE_ENGINE_IGNORE_QUIT=1 shows close() kills after the configured quit wait (scaled). death_note texts are covered by snapshot tests and contain no upstream URL or product name.

<a id="eng-09"></a>
### ENG-09 EngineFifo: FairLock parity with places, exclusive holders, yields, queue keep-alives and queue watchdog

- **Milestone:** M1
- **Rust target:** console-core::fifo (EngineFifo, Place, PlaceGuard)
- **Platform:** platform-neutral
- **Risk:** medium. tokio's Semaphore cannot express claim_yield, yield_place or capacity shrink under an exclusive holder, so this is a custom Mutex plus Notify structure, and fairness bugs are subtle. Tests use tokio paused time to be deterministic.
- **Depends on:** ENG-01
- **Estimated size:** 500-700 lines of code; 500-700 lines of tests
- **Donor sources:** serve/server.py:172-187 (QUEUE_* constants), 243-401 (FairLock, queue_ping_seconds, fair_slice_seconds), 3239-3270 (queue watchdog), 3813-3860 (_turn, _queue_wait), 4346-4378 (queued, active and busy counters around a turn)

**Behaviors to reproduce**

- Capacity = max(1, n), FIFO in arrival order. A request takes 1 unit; exclusive work (image encode, context reload, unload, restart for a switch, shutdown) takes every unit. A waiter for every unit holds back the waiters behind it. When the queue is empty and units are free, acquisition takes the fast path. Units are clamped to the capacity.
- enqueue / wait_turn(timeout) / leave: a waiter that wakes to send a heartbeat keeps its place. wait_turn returns false at once if the entry was removed. When the head of the queue is granted, the next waiters are notified, since one may fit in what is left.
- set_capacity(n) follows the engine's places after a restart or reload, logs the change and clamps the units in use. release() tolerates an over-release with a log line and no error.
- claim_yield(slice_s), unclaim_yield() and yield_place(units) reproduce upstream exactly. need = the units of waiters that never ran, plus those requeued by a slice that have waited at least slice_s. A runner yields only while need - free - yields_in_progress > 0, so exactly as many runners yield as there are waiters. yield_place frees the units and requeues behind the current waiters in one step.
- Introspection: waiting() (queue length), oldest_wait() (0 when nobody waits), held_by() ('<used> of <cap> place(s) in use'), locked().
- Queued keep-alive: while queued, a request emits Ping every MAYA_QUEUE_PING_S (default 2, minimum 0.01; written by HTTP as ': keep-alive') and leaves the line promptly when its cancel token is set.
- A request that waited 5 s or more logs a line when its turn comes. The watchdog looks every 15 s and warns, at most every 60 s, when the first waiter is older than 120 s, naming held_by().
- PlaceGuard releases synchronously on drop (no await), so a cancelled waiter or a panicking turn can never leak a place.

**Parity tests**

test_fair.py FairLockOrder (3: arrival order, a timeout gives up its place, a place survives its wake-ups), FairLockYields (5: one waiter one place, two take two, nobody waiting nobody yields, yielding frees the place and ends the claim, a request for all places takes all); test_multi.py Places (2: n requests hold n places and a whole waits for all; a waiter for all holds back later ones); test_server.py GoneClients (1) and QueuedKeepAlives (1). Re-expressed as tokio tests with paused time where possible. About 14 tests.

**Definition of done**

Every listed test passes deterministically under paused time (run 50 times in CI with no flake). A loom-free stress test (1,000 random acquire, leave and yield operations with capacity changes) never leaves units used above capacity and ends with zero units used. Watchdog and queue-log lines are covered by captured-log tests.

<a id="eng-10"></a>
### ENG-10 Engine turn driver: place, ensure_engine, engine calls, drain, context rule, error classification, non-finite retry and figures

- **Milestone:** M1
- **Rust target:** console-core::turn (EngineTurn, TurnOutcome, TurnFigures, request_timings)
- **Platform:** platform-neutral
- **Risk:** high. This is the most entangled port: nested generators with finally blocks and shared mutable request state become an explicit async state machine. The boundary with console-prompt (stop detection, parser, loop guard) and console-http (event rendering) must be fixed in the contract before coding starts. The API planner's 'Generation loop' component overlaps; the lead must assign the engine half here and the event half there.
- **Depends on:** ENG-01; ENG-02; ENG-09
- **Estimated size:** 900-1200 lines of code; 600-800 lines of tests
- **Donor sources:** serve/server.py:163 (CTX_SLACK), 431-432 (NONFINITE), 2639-2661 (ensure_engine), 3680-3694 (context rule in prepare), 4097-4126 and 4256-4271 (_sliced skeleton, segment merge, own_prompt_figures), 4273-4307, 4340-4378, 4433-4454, 4491-4496, 4657-4793 (the engine half of run: sampling merge, place and status, non-finite retry, heartbeat to ping with progress, finish bookkeeping, timings, request_timings), 5011-5016 (carry_embeddings)

**Behaviors to reproduce**

- Context rule before any engine call: room = max_context - 8 - prompt_tokens. A max_new that is unset, 0 or negative means room. room < 1, or max_new > room without fit_max_tokens, is ContextOverflow (400, code context_length_exceeded, with upstream's 'maximum context length is N tokens; ...' wording). With fit_max_tokens, the limit is clamped to max(1, room). max_context <= 0 gives NotReady (503 'the model is starting'). Requests are never truncated.
- Each turn runs in a spawned task that owns its PlaceGuard and its GenerationHandle. The HTTP side receives events over a bounded channel. A dropped consumer only sets the cancel token, so STOP plus drain always completes before the place is released.
- Acquires one place (or every place for exclusive work), emitting Ping while queued. Then calls ensure_engine: one start at a time under a start lock; if the engine is not alive, restart it, clear the unloaded flag and resize the FIFO to the new caps.places(); log 'loading the model again after an idle unload' or 'the engine had stopped (exit code N); starting it again'. A request that reaches its turn while the server is stopping fails with 'the server is stopping: send the request again once the model is back'.
- Heartbeat events become Ping { total, cache, processed, time_ms } taken from the last progress (for SSE comments and llama.cpp prompt_progress chunks).
- An engine ERR containing 'non-finite' before the first token is retried once from token 0. After tokens were sent, the answer ends there with finish 'length'. A second non-finite error is an error. Other errors are never retried.
- Died maps to 503 server_error ('<reason>; the next request restarts it'), and the next turn's ensure_engine restarts the engine. Reported maps to 400 invalid_request_error before the first byte and to a stream error after (the shapes are rendered by console-http).
- Several engine calls within one request (slices and continuations, ENG-11) are merged: prompt_tokens and reused come from the first call; generated, prompt_ms, decode_ms, drafts and hits/lookups are summed when every segment has them. own_prompt_figures corrects prompt figures when the first DONE was not seen.
- finish is computed by the driver's caller (stop detection belongs to console-prompt). The engine's DONE finish is used only to detect a pause cut.
- Produces TurnFigures for monitoring and llama.cpp-style timings: cache_n, prompt_n, prompt_ms, prompt_per_token_ms, prompt_per_second, predicted_n, predicted_ms, predicted_per_token_ms, predicted_per_second, draft_n, draft_n_accepted, exactly as request_timings computes them. Engines without a clock (the mock) produce no timings and nothing cached.
- The embeddings reference travels in the GenRequest, so a resumed stream job keeps its image embeddings. This structurally replaces upstream's thread-local carry_embeddings.
- Status hooks (queued, active, busy, phase, generated) go through a TurnObserver trait implemented by the monitoring owner.
- Mixed-GPU hook: before a call, `use_layout(alone_reason)` is invoked when the engine supports it (pictures, logprobs or ablation force the single-GPU layout); otherwise it does nothing.

**Parity tests**

test_server.py MaxTokens (5), FitMaxTokens (3), NoRoomOrNoToken (3), NonFiniteRetry (4), EngineDeath (2), UsageAndStatus (5), TimingsDrafts (1), StatsAfterConsumerStops (1), PromptProgressStream (3, the ping payload), TestCarryEmbeddings (1); test_glm_dsa_serve HistoryReuse (2, reused figures through slices). Re-expressed at the driver level with the in-process fake. HTTP-shape assertions stay with console-http. About 30 tests.

**Definition of done**

Every listed test passes. A test shows that dropping the consumer mid-stream still produces STOP, drain and place release, in that order (verified with a recording fake). A test shows the non-finite retry rules. Timings match upstream's formula on fixed DoneFigures fixtures. The turn API is documented in backend-seam.md with the ContinuationPolicy and TurnObserver hooks.

<a id="eng-11"></a>
### ENG-11 Server-side continuations: fair slices, soft thinking close at a boundary, loop-guard and penalty-call continuation hooks

- **Milestone:** M3
- **Rust target:** console-core::turn::continuations (ContinuationPolicy trait, FairSlicer, SoftCloser)
- **Platform:** platform-neutral
- **Risk:** high. Correctness depends on exact accounting of produced, sent and held tokens across several engine calls. The fair-slice tests are timing-based and must use paused time or scaled slices. The policy trait must be agreed with the console-prompt planner before either side starts coding.
- **Depends on:** ENG-09; ENG-10
- **Estimated size:** 700-1000 lines of code; 600-800 lines of tests
- **Donor sources:** serve/server.py:296-327 and 403-409 (claim_yield, fair_slice_seconds), 438-495 (THINK_GRACE, _THINK_BOUNDARY, think_boundary), 3881-3975 (_closed_as_rendered and _as_written hooks), 4097-4271 (_sliced: slices, pause vs cut, requeue, soft close, guard actions, penalty end), 4383-4421 (where _think_soft and _think_end enter the sampling)

**Behaviors to reproduce**

- Every server-side interruption is STOP (or PAUSE) plus drain, followed by a new GEN whose prompt is the original prompt plus everything produced so far (an implicit prefix reuse in the engine). max_new is reduced by the produced count, and the sampling is re-derived through a hook (upstream _resumed_sampling, so the thinking budget counts from where it reached).
- Fair slices (MAYA_FAIR_SLICE_S, default 0 = off). Once a request has decoded for slice seconds, while waiters exist, it has produced fewer than max_new tokens, it is not an image prompt, the server is not stopping, and claim_yield grants: with a pause-capable engine it sends PAUSE (keep on its first slice, i.e. when the current prompt equals the original), lets in-flight tokens arrive, and counts it as a cut if produced < max_new and (no DONE arrived or finish == cancel); without pause it cuts the stream. It then yield_place()s, pings every 0.1 s while requeued (leaving the line if cancelled or stopping), restarts the engine if it died meanwhile, and continues. Status counters move from active to queued and back. unclaim_yield is called whenever a claim did not end in a yield.
- Soft close: when _think_soft and _think_end are set, the driver keeps the last 16 characters of decoded text (decoder supplied by console-prompt). Past soft tokens of reasoning, the first token that ends a sentence or line (a hand-written matcher equal to the regex (?:\n|(?<![\d.])[.!?]["')\]]*|[。！？])[ \t]*$, since Rust's regex has no lookbehind) closes the thinking, provided produced < max_new - 1. Closing stops the call, appends think_end (or the canonical rendering from the console-prompt hook _closed_as_rendered), yields think_end, logs 'thinking reached its budget (N tokens): closed at the end of a sentence or line, K tokens later; answering', and continues. The model writing think_end itself disables the soft close.
- ContinuationPolicy hook (implemented by console-prompt's loop guard): sampling(smp, produced, left) -> (smp_call, n_call); push(token, produced) -> Option<Action{kind: Stop|CloseThinking|Resume, drop}>; hold (tokens held back from the caller); resume(produced, action); thinking_closed(produced); events. On an action the driver deletes the held tail beyond what was already sent, appends think_end for CloseThinking, and continues or ends (LOOP_STOP becomes finish 'stop'). The final held tokens are flushed at the end unless the request was cancelled.
- Penalty-call continuation: when the guard's shortened call (n_call < left) ended by length without a stop id, continue with the request's own sampling while still holding the place.
- Stop ids pass through so the caller can stop reading at one. The note hook (_note_written, the Qwen history in model ids) is called when a stop id is seen.
- Never slices image prompts. Every continuation keeps holding the FIFO place, except the fair-slice requeue.

**Parity tests**

test_fair.py FairSlices (5: off_by_default_the_short_one_waits, the_short_one_goes_first_and_the_long_one_continues, pause_keeps_the_tokens_still_on_their_way, alone_it_is_never_cut, a_client_gone_while_queued_again_leaves_the_line) and FairSlicesParallel (1: one_short_request_cuts_one_long_answer); test_server.py ThinkingBudgetAtASentenceEnd (5) and ThinkingBudget (6, driver half); test_glm_dsa_think_budget EngineBudget (12, the soft-close continuation half; budget numbers come from console-prompt); test_loop_guard continuation tests are owned by console-prompt but run through this hook. About 30 tests at driver level, with stub ContinuationPolicy implementations and the Pausing/Resuming fakes.

**Definition of done**

Every listed test passes with stub policies. A property test (random guard actions, slices and soft closes against a deterministic fake) shows the client receives exactly prompt-independent produced tokens in order, with no duplicates and no losses, and that DoneFigures segments merge as specified. The ContinuationPolicy trait is documented and signed off in the contract by the console-prompt owner.

<a id="eng-12"></a>
### ENG-12 EngineHost lifecycle: start, unload and idle unload, model load and unload, context reload, slots and props facts, shutdown wind-down

- **Milestone:** M3
- **Rust target:** console-core::host (EngineHost)
- **Platform:** platform-neutral
- **Risk:** medium. Writing back to the run config touches a file owned by console-manage's schema; the field set must be agreed. Signal handling itself is owned by the process-lifecycle planner; this package exposes shutdown() only.
- **Depends on:** ENG-08; ENG-10
- **Estimated size:** 800-1100 lines of code; 600-800 lines of tests
- **Donor sources:** serve/server.py:2639-2821 (ensure_engine, unload, idle_limit, start_idle_unload, reloading, context_limits, set_context, _restart_with, _reload, _save_context), 5465-5505 (/models/load and /models/unload semantics), 6027-6036 and 6101-6131 (health, slots and props facts), 6256-6267 (503 Retry-After 30 while reloading), 6963-7041 and 7409-7452 (shutdown wind-down), 7164-7299 (start order); READERS contract 'Engine state exposed over HTTP'

**Behaviors to reproduce**

- start(): builds the engine (mock or line or mixed, chosen by configuration) and blocks until READY, records load_s, and sets the FIFO capacity when places > 1, logging 'N conversations at once'. The binary calls it before binding the listener (upstream order: the engine first, the listener second).
- unload(idle_for: Option<secs>) -> Unloaded | NotLoaded | Busy | Unsupported. It needs every FIFO place without waiting (otherwise Busy) and returns Busy if a request is running or queued, a reload is waiting or running, or (with idle_for) a request ran more recently. Otherwise it calls close() (STOP plus QUIT), marks the engine ended, runs the memory settle, sets unloaded, and logs.
- Idle unload loop: limit = the last request's keep_alive (a negative value means never) or idle_unload_s (0 = never). It wakes every max(1, min(30, (limit or 120) / 4)) s and survives errors.
- load(): Loaded at once if alive. Otherwise it takes the FIFO and restarts, returning Failed('the engine did not start: <reason>'). Model management being off and unknown models are handled by console-http.
- Context reload set_context(n): range check against context_range (supplied by console-manage) with the error 'the context must be between A and B tokens'; 'the model is already reloading' while one is active; state {state: waiting|running|done|failed, from, to, started, error, ended, context}. A worker takes every place, then stops the request in flight, sets the new size and restarts (graceful close: a listed deviation from upstream's STOP plus kill). On failure it restarts with the old size and composes upstream's error text; it resizes the FIFO either way. On success it saves '--max-context n' into the run config's args (keeping other keys, adding installer.as_set_up through a console-manage hook on the first change), writing a temp file and renaming it. The mock engine instead sleeps MAYA_MOCK_RELOAD_S.
- reloading() is the signal console-http uses to answer chat routes with 503 type overloaded_error and Retry-After: 30.
- Facts for routes: slots() returns [] when not loaded, else max(1, multi) entries {id, n_ctx, is_processing}. props facts: total_slots, model_path (upstream rule: --native, else --pack, else 'pack/full'), build version, dead-and-not-unloaded flag. models status: loaded, unloaded or loading, with n_ctx. health: updating, reloading or ok, max_context, unloaded. context_limits(): {context, min, max, trained, tested, kv_gb, kv_ctx, kv_resident, kv_ram_gb, vram_gb, vram_slots, reload, load_s} plus ram figures from console-host when kv_ram is present.
- Shutdown wind-down: set stopping; queued requests are refused; a busy engine receives WRAP and gets up to MAYA_ENGINE_WRAP_S (default 40, 0 = skip) to release the FIFO, else STOP and a wait for the request to end; then close the engine, the vision encoder and the registered extra closers (MCP).

**Parity tests**

test_server.py IdleUnload (4), ModelManagement (5, host half; route shapes re-expressed by console-http), FailedRestartKeepsContext (1), EngineDeath.test_error_then_restart; test_stop.py ServerStops (the engine wind-down: SIGTERM and SIGHUP leave no engine process, using the fake multi engine with argument 1); test_glm_dsa_serve Released (3) for close semantics. Plus new tests: the reload state machine with an engine that fails then succeeds, the atomic config save (temp file plus rename, other keys preserved), WRAP-then-STOP shutdown ordering with the GLM fake (think_end forced after WRAP). About 22 tests.

**Definition of done**

Every listed test passes. unload() return values match upstream strings. A test shows a failed reload restores the old size and reports 'failed'. A test shows the config write is atomic and preserves unknown keys. A test shows shutdown sends WRAP before STOP and that no fake engine process survives shutdown.

<a id="eng-13"></a>
### ENG-13 GPU map: VRAM parts joined with per-card readings (NVIDIA/AMD, fixture-driven)

- **Milestone:** M9
- **Rust target:** console-engine::gpu_map
- **Platform:** hardware-or-os-specific
- **Risk:** low. Pure functions, fully fixture-testable. Labelled unverified on real NVIDIA/AMD hardware. Card readings come from console-host's NVML and sysfs readers through a plain struct defined here.
- **Depends on:** ENG-04
- **Estimated size:** 300-450 lines of code; 350-500 lines of tests
- **Donor sources:** serve/gpu_map.py:1-147 (parse, merge, view, tp_rooms); serve/server.py:931-934, 1032-1037 (VRAM state), 3376-3388 (metrics gpu_map, None without VRAM lines)

**Behaviors to reproduce**

- merge(): two parts of a split on one card add up.
- view(parts, cards, engine_pids, encoder_pids): cards are matched by normalised PCI address, not by position. NVML process lists tell the engine's and the encoder's pids from other programs (including an engine started through a launcher, via descendants supplied by console-host). The driver's reserve is not counted as another program. 'other' and 'rest' are trimmed so the parts never exceed the card. When NVML or the engine pid is unavailable, the start measurement is used. The parts are weights, kv, act, prompt, tp, drafter, pool, helper, vision, rest, other and free.
- tp_rooms(): tensor-parallel group members share the group's least free room.
- Later VRAM lines replace that device's entry (a picture's room taken and given back).
- metrics gpu_map = None when the engine printed no VRAM line (always the case on Apple Silicon engines).

**Parity tests**

test_dashboard.py GpuMap (17 methods, including test_parse, helper_pool..., nvml_tells_the_engine_from_other_programs, found_by_pci_not_by_place, never_more_than_the_card, tensor_parallel_room_is_the_groups_least_free, two_parts_on_one_card_add_up, metrics_carry_it, later_lines_follow_a_picture); test_glm_dsa_api.py MonitorFigures (4; the VRAM and STAT key lists re-expressed as a committed key-list fixture, instead of grepping engine C++ sources). Transcribed with the same fixture lines.

**Definition of done**

All 17 GpuMap tests and the MonitorFigures key-list tests pass. The CardReading input struct is documented for console-host. A test shows gpu_map is None for an engine with no VRAM lines.

<a id="eng-14"></a>
### ENG-14 Vision helper process, SVE1 embeddings files and engine memory lending

- **Milestone:** M6
- **Rust target:** console-engine::vision (VisionEncoder, SveFile, footprint); fake binary console-fake-vision-encoder in console-fake-engines
- **Platform:** hardware-or-os-specific
- **Risk:** medium. Lending is meaningful only on discrete GPUs and is unverified on hardware; on Apple Silicon the encoder stays resident. Image loading (data:, http(s), file) and normalisation belong to console-media, and fetching http(s) image URLs is a security question for that planner. No real maya-vision binary is ever run.
- **Depends on:** ENG-06; ENG-09; ENG-10
- **Estimated size:** 900-1200 lines of code; 500-700 lines of tests
- **Donor sources:** serve/server.py:1731-1955 (Vision: start, stop, settle, active, encode, encode_video cache and protocol parts), 1957-2003 (vision_footprint), 3574-3679 (where prepare calls the encoder: exclusive FIFO around encodes, GENI file assembly), 4693-4694 (temp file removal), 7217-7286 (vision mode selection in main); READERS contract 'GENI embeddings file (SVE1) and the maya-vision helper protocol'

**Behaviors to reproduce**

- Encoder process: [exe, --mmproj f, --model f, (--gpu), (--threads n), (--max-tokens n), (--no-flash-attn), (--no-warmup when on demand)]. The first stdout line must start with READY, otherwise the error is 'the vision encoder did not start: <line>'. 'ENC <image> <out>' and 'VID <video> <out>' answer 'OK <n>' or 'ERR <msg>'. 'QUIT' with a 10 s wait, then kill.
- Cache keyed by the first 32 hex characters of the sha256 of the normalised bytes, at most 64 entries, evicting the oldest and deleting its file. A temp directory holds <key>.img, <key>.vid and <key>.sve; input files are deleted after each command. The same picture across turns is encoded once.
- Video: the SVE1 record headers give per-frame token counts. The frame limit check (MAYA_VIDEO_MAX_FRAMES, default 240, at 4 fps) runs through a duration probe supplied by console-media before the encoder is called.
- SVE1 reader and writer: records of 5 little-endian int32 {magic 0x31455653, n_tokens, nx, ny, n_embd} followed by n_tokens x n_embd f32; bad magic or n_embd <= 0 is an error. The per-request file req-<12 hex>.sve concatenates the cached records in prompt order, is passed as the GENI file argument, and is deleted after the request. The temp directory path is guaranteed whitespace-free (a listed deviation).
- On-demand mode (discrete GPU only): lend runs engine.command('VLEND', 'VLENT') and reclaim runs engine.command('VRECLAIM', 'VRECLAIMED'), with every FIFO place held around the request's encodes. The encoder starts after lend and ends when the encodes finish. settle() retries the reclaim up to 40 times at 0.25 s, and an owed flag logs that prompts are read token by token until the memory is back.
- Footprint: `--gpu --max-tokens N --measure` prints 'MEM a b total'. The result is cached in vision-memory.json beside the run config, keyed by '<mmproj resolved>|<size>|<mtime>|gpu<g>|cap<c>|fa<0|1>'. Caps tried are [max_tokens] or [4096, 2048, 1024]; the largest whose bytes (a + b + 256 MiB) stay within 15 percent of the card is chosen. A damaged cache file is re-measured. A failed measurement means the encoder runs on the CPU.
- Mode selection, as in main: on demand when the vision config has gpu, is not resident and the backend is not metal; then the engine env gains MAYA_GLM_VISION_LEND_MB = (bytes >> 20) + 1, and on demand is used only if INFO vision_lend > 0, otherwise the encoder runs on the CPU. Metal or resident keeps it running. INFO vision=ds4|mm3|off selects the in-engine tower path (pixels files from console-media). Text-only engines give the 400 'started without the vision encoder' path, with glm-dsa's text-only wording supplied by console-prompt.

**Parity tests**

test_server.py VisionFootprint (3) and TestCarryEmbeddings (1); test_engine_contract test_09_vlend_on_a_text_only_model; test_glm_dsa_serve TextOnlyImages (4, the engine half); test_tool_images (4) and test_tool_videos ToolVideos (5) and VideoGuards (4) are owned jointly with console-media and run against console-fake-vision-encoder (which writes valid SVE1 records sized by env, supports --measure with env-controlled MEM values, and can be told to fail READY, ENC or VID). Plus new tests: SVE1 round trip, cache eviction at 65 entries, lend and reclaim ordering with every place held (recording fake engine). About 25 tests.

**Definition of done**

Every listed test passes with the fake encoder. vision-memory.json key format and selection rule match upstream on fixtures. A test shows every FIFO place is held from VLEND to VRECLAIM. Per-request .sve files are removed after success, error and cancellation.

<a id="eng-15"></a>
### ENG-15 Engine launch specification from the run config, and GLM link mode (AMD APU plus NVIDIA card)

- **Milestone:** M3
- **Rust target:** console-engine::launch (LaunchSpec, child_env, engine_args), console-engine::multigpu::glm_link
- **Platform:** hardware-or-os-specific
- **Risk:** low. Pure configuration transforms plus one probe trait. Words such as CUDA and NVIDIA are unavoidable in this code, so the lead must confirm the repository's staged-content scanner does not cover console/ (see open questions). Unverified on real hardware.
- **Depends on:** ENG-01
- **Estimated size:** 450-650 lines of code; 350-450 lines of tests
- **Donor sources:** serve/server.py:2006-2058 (gpu_list, engine_args, child_env), 893-897 (model_path rule), 920-923 (BUILD.json), 7197-7203 and 7246-7252 (link mode and construction in main); serve/glm_link.py:1-124; tools/maya_names.py:50-57 (export_env); READERS contracts 'Engine process launch' and 'Run-config keys the server reads to launch and supervise the engine'

**Behaviors to reproduce**

- gpu_list: an int, a list or a comma string becomes Vec<i32>, and an empty value gives []. engine_args: the config's args plus ['--layer-split', layer_split or 'auto'] when more than one GPU is named and the args lack it.
- child_env: a copy of the server environment. backend 'hip' with GPUs sets HIP_VISIBLE_DEVICES; any other non-metal backend with GPUs sets CUDA_DEVICE_ORDER=PCI_BUS_ID and CUDA_VISIBLE_DEVICES. Every cfg.env entry is exported under both its MAYA_X and its STRATA_X name (the engine-facing interface). fast_prefill as a bool sets DS4_YOCO_CONE=1|0. lib_dirs that exist are prepended to LD_LIBRARY_PATH (PATH on Windows). The vision-lend MB is added by ENG-14.
- LaunchSpec { exe, args, cwd, log, env } with the model_path rule (--native, else --pack, else 'pack/full') and the version from BUILD.json beside the exe.
- glm_link.at_start(cfg): returns the config unchanged unless mixed_gpus is true and the args contain --glm-pack. why_not: Linux only (a runtime OS check, compiled everywhere), a HIP GLM config, not with --parallel, an NVIDIA card must answer nvidia-smi (through a GpuProbe trait), both builds must exist. link_config: exe becomes build-cuda/<name>, backend 'cuda', gpu = the first NVIDIA card, env gains MAYA_GLM_EXPERT_HELPER=link, MAYA_GLM_SPLIT=0, MAYA_GLM_HELPER_EXE, HIP_VISIBLE_DEVICES and optionally MAYA_GLM_MTP_FIXED and MAYA_GLM_CPU_CAL (from installer.mixed_gpus_calibration); AMD-only tuning env is dropped; vision becomes resident. It returns the start log line.

**Parity tests**

test_server.py GpuChoice (1); test_glm_link.py GlmLinkTest (4: no_key_unchanged, on_is_link, falls_back, draft_length_kept), with nvidia_cards mocked through the GpuProbe trait. Plus table tests for child_env over backend, gpu and lib_dirs combinations and for engine_args. About 15 tests.

**Definition of done**

Every listed test passes on macOS with a mocked probe. The child_env table covers all branches. No cfg(target_os) gates: OS checks happen at run time.

<a id="eng-16"></a>
### ENG-16 Mixed GPUs: DeepSeek on two GPUs of different makers (config, two-process supervisor, per-request layout swap)

- **Milestone:** M9
- **Rust target:** console-engine::multigpu::mixed (MixedConfig, MixedEngine wrapping LineEngine); fake binary console-fake-mixed-engine in console-fake-engines
- **Platform:** hardware-or-os-specific
- **Risk:** medium. It has no meaning on Apple Silicon and is unverified on hardware. Only the supervision logic is exercised, with fakes. The engines' real cross-process transport (TCP part, shared-memory helper) is engine-internal and not reproduced.
- **Depends on:** ENG-08; ENG-15
- **Estimated size:** 900-1200 lines of code; 400-600 lines of tests
- **Donor sources:** serve/mixed_gpus.py:1-442 (Unavailable, nvidia_listed, cuda_exe, auto_found, why_not, config_of, strip_flags, set_flag, free_port, end_with_parent, plan, engine_class with _start_mixed, _start_helper, use, _use, _end_engine, _watch_load, _part_alive, _stop_part, death_note, alive, restart, close); serve/server.py:2620-2637 (alone_reason and engine_for hooks), 7239-7245 (construction)

**Behaviors to reproduce**

- config_of(cfg): turns on by itself for a HIP DeepSeek config where an NVIDIA card and a CUDA build of the DeepSeek engine are found. mixed_gpus false turns it off; a number sets the layer count; mixed_mode is 'helper' (default) or 'split'. why_not reasons: no CUDA build, --parallel present, not HIP DeepSeek, Windows. strip_flags and set_flag edit args exactly as upstream does.
- Split mode: runs `<engine> --pack P --mixed-plan` and expects 'MIXED_PLAN <k> <text>'. It starts the part with `--part-from k --part-serve <free port>` and the front with `--remote-part 127.0.0.1:<port>`. Both are watched, and when either ends the engine falls back to one GPU with the reason kept (mixed_off).
- Helper mode: starts `<cuda exe> --pack P --serve` with fixed args and DS4_RHELPER_SERVE=<name>; the lead gets DS4_RHELPER=<name>.
- Children are tied to the parent's life (PR_SET_PDEATHSIG through libc at run time on Linux; elsewhere a best-effort kill on drop).
- use(alone_reason): before a request, swap to the HIP engine alone (pictures, logprobs, ablation) or back to both, keeping the rid counter. _end_engine is a real QUIT, a 60 s wait, a kill and the memory settle (distinct from a request STOP).
- death_note, alive, restart and close cover both processes. A part that dies triggers the single-GPU fallback on the next request.

**Parity tests**

test_mixed_gpus.py TestMixedGpus (8: auto_where_found, off_when_not_found, on_and_layers, mode, only_hip_deepseek, flags, no_cuda_build_runs_one_gpu, parallel_runs_one_gpu), with probes mocked. Plus new process-level tests with console-fake-mixed-engine: answers --mixed-plan, serves --part-serve by listening on the port and printing READY, exits on QUIT, and can be told to die. These cover split start, helper start, fallback when the part dies, use() swaps preserving the rid counter, and _end_engine timing. About 16 tests.

**Definition of done**

The 8 upstream tests and the fake-process tests pass on macOS. The fallback and swap paths are each covered. A reviewer can map every function in mixed_gpus.py to a Rust item or a recorded omission (none expected).

<a id="eng-17"></a>
### ENG-17 Prompt memo (MAYA_PROMPT_MEMO) and DeepSeek restore points

- **Milestone:** M3
- **Rust target:** console-prompt::memo (PromptMemo, restore points); join_ids_memo lives in ENG-04
- **Platform:** platform-neutral
- **Risk:** medium. It depends on console-prompt's tokenizer exposing special-token segmentation. It is a pure optimisation and may be unnecessary with a fast Rust tokenizer, but full parity keeps the setting and its verify mode. Tests must not depend on vendor templates.
- **Depends on:** ENG-03
- **Estimated size:** 500-700 lines of code; 400-600 lines of tests
- **Donor sources:** serve/server.py:773-825 (RESTORE_LEAST, deepseek_restore_points), 2088-2090 and 2128-2239 (PromptMemo), 2265-2291 (deepseek_restore_points_fast), 2532-2569 (render_ids with memo and verify), 4422-4431 (restore points on the request path)

**Behaviors to reproduce**

- The memo is on unless MAYA_PROMPT_MEMO=0. 'verify' also encodes the whole prompt, fails with "MAYA_PROMPT_MEMO: the ids differ from the whole prompt's" on any difference, and logs 'prompt memo verified: N ids'. It never changes ids, the GEN line or any API output.
- It keeps the last 4 marked prompts (text, mark positions, special-token cut points, ids). A new prompt reuses the ids up to the last special token that ends at least 'longest special token' characters before the first difference, and encodes only the tail. It is not used when a suffix is appended, or when the tokenizer cannot expose special segments.
- Restore points only for DeepSeek templates, text prompts and MAYA_DS4_RESTORE_POINTS > 0 (default 4); MAYA_DS4_RESTORE_TAIL defaults to 512. shared = the position of the first user-turn token; marks = [the position of the last user or later system-turn token] when it differs from the first; tail = len - tail when beyond the last turn start. Positions under 1024 are left out. A client `_restore` is always stripped. The fast variant equals the reference on all inputs.

**Parity tests**

test_prompt_memo.py SameIds (10), LiteralMemoSame (2; owned by console-prompt but run here), RestorePointsFast (2), JoinIdsMemo (2; in ENG-04), GistByText (1; console-prompt); test_ds4_restore_points.py RestorePoints (8). The template-based cases are re-expressed with synthetic templates that carry each family's special-literal sets: vendor templates are not vendored, but the literal strings themselves are facts. SameIdsRealTokenizers stays opt-in behind an env var naming local tokenizer folders. About 22 tests.

**Definition of done**

Randomised multi-turn histories give equal ids with the memo on and off for every synthetic family template. verify mode raises on an injected difference. The restore-points reference and fast variants agree on 10,000 random id sequences. All 8 RestorePoints tests pass.

<a id="eng-18"></a>
### ENG-18 Engine conformance suite (protocol profile plus GLM family profile) and seam conformance harness

- **Milestone:** M3
- **Rust target:** console-engine::conformance (library behind feature 'conformance'), binary console-engine-check, integration tests console-engine/tests/conformance_*.rs
- **Platform:** platform-neutral
- **Risk:** low. Runs against a real engine are not exercisable with synthetic backends and stay opt-in. The GLM ids and INFO keys are confined to the GLM profile so an MLX engine is not blocked.
- **Depends on:** ENG-05; ENG-06; ENG-07; ENG-19
- **Estimated size:** 700-1000 lines of code; 200-400 lines of tests
- **Donor sources:** serve/test_engine_contract.py:1-289; tools/test_metal_serve.py:1-75 (Apple Silicon engine oracle: PAUSE reuse, seeded repeat, spec=1); serve/test_glm_dsa_serve.py:530-542 (ContractTestOnTheFake expects 'Ran 10 tests', 'OK (skipped=1)')

**Behaviors to reproduce**

- Wire conformance against any engine executable: start [ENGINE, --serve, <model flag>, PACK, --max-context, CTX, --prefill, auto, *extra] with env-driven settings mirroring MAYA_TEST_ENGINE, PACK, CONTEXT (8192), ARGS, READY_S (900), LOG, TEXT_ONLY (1), REQUIRE_A29, EXPERTS and SPLIT, under a new namespace with the upstream names accepted.
- Protocol profile (every engine): test_01 READY (field 1 = the context, flags only stop, pause or multi=<digits>, stop required, pause required if the profile says so); test_04 GEN/DONE (exactly 10 fields, generated = the number of T lines, prompt = the prompt length, finish stop or length, drafts accepted <= offered, hits <= lookups, reused <= prompt, a PP whose total is the prompt, a 'stop' ends with an end-of-turn id as the last T); test_05 reuse > 0 for the same prompt again; test_06 STOP after 3 tokens gives cancel with fewer than 64 tokens; test_07 think_budget=4 puts think_end within the first 6 tokens; test_08 WRAP after 2 tokens closes thinking within tokens 2..6; test_09 VLEND on a text-only model answers ERR; test_99 QUIT gives exit code 0. The end-of-turn and think-end ids are profile parameters.
- GLM family profile: test_02 INFO keys and types; test_03 start-log phrases (the VRAM-before-the-expert-pool line for the context, the serve banner, a REPORT_LINES match); STAT with 12 named keys after 8 tokens.
- Metal-style oracle profile (optional): PAUSE after 6 tokens gives cancel, and a follow-up GEN with prompt plus written tokens reuses len-1 and reproduces the uninterrupted answer; a seeded sampled request repeats; spec=1 does not change tokens.
- Against console-fake-engine with FAKE_ENGINE_REPEAT=1 and FAKE_ENGINE_IDS=104,101,108,108,111,154827, the suite reports 10 checks and 1 skipped, matching ContractTestOnTheFake.
- Seam conformance: one behavioural test battery parameterised over `Box<dyn Engine>` (cancel then drain, figures per request, heartbeat on quiet, error mapping, pause semantics when advertised, restart keeps context). It runs against FakeEngine, LineEngine over each fake binary, and the ENG-19 runtime adapter over its synthetic runtime, so a future PulsarMLX engine is checked by the same battery.

**Parity tests**

test_engine_contract.py (10 methods) re-expressed one-to-one and split into profiles; test_glm_dsa_serve.ContractTestOnTheFake (1) becomes the integration test against the fake; tools/test_metal_serve.py (3 checks) becomes the optional oracle profile, skipped in CI because no real engine runs. The seam battery adds about 12 tests run against each of the 4 implementations.

**Definition of done**

`cargo test -p console-engine --features conformance` runs the protocol and GLM profiles against console-fake-engine, with 10 run and 1 skipped. The seam battery passes for all four implementations. console-engine-check prints a pass, fail or skip table and exits non-zero on failure. Each Rust check's doc comment names its upstream test method.

<a id="eng-19"></a>
### ENG-19 Blocking runtime adapter: the in-process seam a future PulsarMLX engine plugs into (post-commit token sink)

- **Milestone:** M3
- **Rust target:** console-engine::runtime (RuntimeEngine trait, RuntimeAdapter implementing the ENG-01 Engine trait, SyntheticRuntime fixture)
- **Platform:** platform-neutral
- **Risk:** medium. It must not depend on any engine-track crate (crates/backend is hash-bound and edited by the engine track), so the step.rs shape is mirrored, not imported. Actually attaching PulsarMLX is a later, separately approved step and is not exercisable now.
- **Depends on:** ENG-01
- **Estimated size:** 500-700 lines of code; 400-500 lines of tests
- **Donor sources:** No project-maya source: this package is the PulsarMLX side of the seam. Shape references: ORIGIN crates/backend/src/step.rs:59-78 and 273-300 (post-commit deliver hook, replay, never rewound) and git -C ORIGIN show archive/2026-09-21/feat/openai-serving:crates/serve-synthetic/src/runtime_adapter.rs (RuntimeSession, GeneratedToken, CancelProbe, owned worker thread, lease held until the thread is joined). Upstream semantics reproduced: the Engine contract in serve/server.py:191-240 and metal/serve.cpp's behaviour as described by the reader.

**Behaviors to reproduce**

- `RuntimeEngine: Send + 'static` with `generate(&mut self, req: &GenRequest, cancel: &CancelProbe, sink: &mut dyn FnMut(Committed) -> Delivery) -> Result<DoneFigures, RuntimeError>`, plus optional `pause(keep)`, `caps()`, `facts()` and `max_context()`. Committed carries either Token { id, lp } or Progress.
- Post-commit semantics as in step.rs: a token is handed to the sink only after the runtime has committed it and is never rewound or recomputed. A sink returning Delivery::Closed (the consumer has gone) never turns the committed step into a failure; the runtime stops at its next step and still returns DoneFigures with finish=Cancel.
- The adapter runs the runtime on one owned OS thread per engine (one conversation at a time unless the runtime advertises places) and bridges to async through a bounded channel, so backpressure reaches the runtime. It emits Heartbeat on 10 s quiet. finish() sets the cancel probe and waits for DoneFigures, which is the drain. The FIFO place is released only after the runtime thread has returned from generate, matching the archived CleanupOwner rule.
- A runtime panic is converted to Died('the engine stopped unexpectedly (panic: ...)'). The next ensure_engine recreates the runtime through a factory (the restart).
- SyntheticRuntime: a deterministic fixture with configurable pace, prefix reuse, pause support and failure injection, labelled as serving no model.

**Parity tests**

There is no upstream test, because this seam does not exist in project-maya. It passes the ENG-18 seam battery and has adapter-specific tests: Delivery::Closed stops at the next step with figures; the place is held until the thread joins; a panic becomes Died; backpressure (a slow consumer blocks the runtime, no unbounded buffering). About 12 tests.

**Definition of done**

The adapter passes the ENG-18 seam battery with SyntheticRuntime. No dependency on any crate outside console/. backend-seam.md documents how an engine-track `deliver` hook maps onto the sink, including replay of an already committed step.
