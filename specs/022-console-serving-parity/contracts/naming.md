# Naming Contract and Old-to-New Name Table

- **Status**: Seed, dated 2026-11-14. The rules in section 1 are binding decision B2 of the
  approved plan (restated in [`../tasks.md`](../tasks.md), section "Binding cross-cutting
  decisions", with decisions B1 to B13) and deviation BRAND-1. The tables are seeded
  from the planning records and a static reading of the pinned donor source; nothing
  listed here is implemented yet, except the names that a row or an entry of section 3.11
  says a package has fixed.
- **Feature**: `specs/022-console-serving-parity`
- **Written by**: GOV-06 (this seed). Extended by every package that ports a setting,
  file, storage key, log line or wire identifier (section 4).
- **Donor**: project-maya at commit `7e68a30f2f208056195352129188661fb6b94445` (v1.1.63).
  Donor locations below are paths in that tree, such as `serve/server.py:6737`.

project-maya is named here because this table records provenance. None of the old names
is part of PulsarMLX Console's own identity, and none is accepted by it except where a
row says the name is kept or passed verbatim.

## 1. Rules (decision B2, deviation BRAND-1)

1. **Product identity.** The product is "PulsarMLX Console" and the binary is
   `pulsar-console`. No Maya name, logo or quant name appears in anything PulsarMLX
   Console presents as its own.
2. **Environment variables.** The canonical prefix is `PULSAR_CONSOLE_`. Legacy `MAYA_*`
   and `STRATA_*` names are **not** accepted as aliases: the server does not read them. The
   donor's alias mechanism (`tools/maya_names.py`, where `STRATA_X` is a fallback for
   `MAYA_X`) is not ported.
3. **Engine passthrough.** Variable names inside a run config's `env` block that are
   passed through to engine child processes are opaque data and pass through verbatim. The
   server neither renames them nor rejects them for their prefix, and passes each one to
   the child once: the donor's export of each engine setting under both a `MAYA_` and a
   `STRATA_` name is not reproduced (decided by the lead on 2026-11-14). (Which names may
   be passed at all is a security matter: see deviation SEC-7.)
4. **Wire names kept.** `strata_resume`, `strata_mcp`, `strata_tune`,
   `strata_level_default`, `/v1/strata/stream` and `/v1/strata/cancel` are kept unchanged.
   They are not Maya's name, and the adapted dashboard depends on them.
5. **Files.** The run-config file prefix is `pulsar-`; note files are `.pulsar-*`.
6. **Browser storage.** The `localStorage` prefix is `pulsar.` and the IndexedDB database
   is `pulsar-console`.
7. **Log prefix.** Server log lines use the prefix `[console]`.
8. **Sealed reasoning.** The sealed-reasoning prefix that PulsarMLX Console emits is the
   product's own. Whether the donor's prefix is accepted on input is an **open item**
   (section 5, N1).
9. **Mechanical rename for settings.** Unless a row says otherwise, a server setting
   `MAYA_<SUFFIX>` becomes `PULSAR_CONSOLE_<SUFFIX>` with the suffix unchanged. This is the
   seed's default; a package that wants a different suffix records it in the table as a
   proposal for review, never silently.

## 2. Status values used in the tables

| Status | Meaning |
| --- | --- |
| Decided | Fixed by decision B2, by an approved deviation, by another section of the approved plan, or by a lead decision, as cited |
| Mechanical | New name produced by rule 9; confirmed when the owning package ports the setting |
| Rename decided, value proposed | The old name must go (BRAND-1); the replacement string is a planner's proposal, fixed by the owning package and reviewed |
| Kept | The name is unchanged |
| Removed | The name has no counterpart, for the reason cited |
| Verbatim | An engine-interface name, passed through or read unchanged as engine data (rule 3) |
| Not ported | Belongs to the donor's launcher, engine builds or tests; PulsarMLX Console does not read it |
| Open | Not decided by the approved plan; listed in section 5 |

Source abbreviations: **API** `planners/api-transport-dialects.json`; **ENG**
`planners/engine-supervision-scheduling.json`; **PRM**
`planners/prompting-parsers-guards.json`;
**RSP** `planners/responses-mcp-attachments-media.json`; **OPS**
`planners/models-ops-telemetry.json`; **WEB** `planners/dashboard-phase1.json`; **CNF**
`planners/conformance-strategy.json`; **R-** the reader records `readers/maya/maya-*.json`
(R-api, R-engine, R-launch, R-ops, R-plat, R-prompt, R-resp, R-web). These are planning
records outside the repository: the `planners/` files are per-area design proposals
written before the plan was approved (their authors are "the planners" below), and the
reader records are notes from reading the donor source. The donor location column is the
checkable source.

## 3. Old-to-new tables

The tables in this section are the machine-read form of this contract (section 4). Each
row has one old name in backticks in the first column.

### 3.1 Server settings (environment variables the server itself reads)

| Old name | New name | Status | Donor location | Records | Package |
| --- | --- | --- | --- | --- | --- |
| `MAYA_API_KEY` | `PULSAR_CONSOLE_API_KEY` | Mechanical | `serve/server.py:7139` | API, OPS, R-api | API-03, API-15 |
| `MAYA_DEBUG` | `PULSAR_CONSOLE_DEBUG` | Mechanical | `serve/server.py:4747`, `serve/mcp.py:127` | PRM, R-api | API-16 |
| `MAYA_DRAIN_S` | `PULSAR_CONSOLE_DRAIN_S` | Mechanical | `serve/server.py:756` | ENG, R-engine | ENG-06 |
| `MAYA_DS4_KEEP_THINKING` | `PULSAR_CONSOLE_DS4_KEEP_THINKING` | Mechanical | `serve/frontend.py:284`, `serve/server.py:6738` | PRM, R-prompt | PRM-07 |
| `MAYA_DS4_RESTORE_POINTS` | `PULSAR_CONSOLE_DS4_RESTORE_POINTS` | Mechanical | `serve/server.py:783` | ENG, R-engine | ENG-17 |
| `MAYA_DS4_RESTORE_TAIL` | `PULSAR_CONSOLE_DS4_RESTORE_TAIL` | Mechanical | `serve/server.py:783` | ENG, R-engine | ENG-17 |
| `MAYA_ENGINE_QUIT_S` | `PULSAR_CONSOLE_ENGINE_QUIT_S` | Mechanical | `serve/server.py:1703-1705` | ENG, R-engine | ENG-08 |
| `MAYA_ENGINE_STALL_S` | `PULSAR_CONSOLE_ENGINE_STALL_S` | Mechanical | `serve/server.py:728` | ENG, R-engine | ENG-08 |
| `MAYA_ENGINE_WRAP_S` | `PULSAR_CONSOLE_ENGINE_WRAP_S` | Mechanical | `serve/server.py:7428` | ENG, R-engine | ENG-12 |
| `MAYA_FAIR_SLICE_S` | `PULSAR_CONSOLE_FAIR_SLICE_S` | Mechanical | `serve/server.py:404-407` | ENG, R-engine | ENG-11 |
| `MAYA_GLM_THINK_RESERVE` | `PULSAR_CONSOLE_GLM_THINK_RESERVE` | Mechanical | `serve/server.py:4402` | PRM, R-prompt | PRM-13 |
| `MAYA_HTTP_BACKLOG` | `PULSAR_CONSOLE_HTTP_BACKLOG` | Mechanical | `serve/server.py:5349` | R-api | API-02 |
| `MAYA_LOOP_GUARD` | `PULSAR_CONSOLE_LOOP_GUARD` | Mechanical | `serve/server.py:613-617` | PRM, R-prompt | PRM-14 |
| `MAYA_LOOP_GUARD_COLLAPSE_MAX` | `PULSAR_CONSOLE_LOOP_GUARD_COLLAPSE_MAX` | Mechanical | `serve/loop_guard.py:594` | PRM, R-prompt | PRM-15 |
| `MAYA_MAX_BODY_MIB` | `PULSAR_CONSOLE_MAX_BODY_MIB` | Mechanical | `serve/server.py:5366-5369` | CNF, R-api | API-02 |
| `MAYA_MOCK_RELOAD_S` | `PULSAR_CONSOLE_MOCK_RELOAD_S` | Mechanical | `serve/server.py:2771` | ENG, R-engine | ENG-02 |
| `MAYA_MOCK_TOK_S` | `PULSAR_CONSOLE_MOCK_TOK_S` | Mechanical | `serve/server.py:7290` | ENG, R-engine | ENG-02 |
| `MAYA_MODEL_MANAGEMENT` | `PULSAR_CONSOLE_MODEL_MANAGEMENT` | Mechanical | `serve/server.py:600-605` | OPS, R-ops | OPS-13 |
| `MAYA_PACK_TEMPLATE` | `PULSAR_CONSOLE_PACK_TEMPLATE` | Mechanical | `serve/server.py:6858-6867` | PRM, R-prompt | PRM-08 |
| `MAYA_PROMPT_MEMO` | `PULSAR_CONSOLE_PROMPT_MEMO` | Mechanical | `serve/server.py:2089`, `serve/frontend.py:477` | PRM, ENG, R-prompt | ENG-17, PRM-08 |
| `MAYA_QUEUE_PING_S` | `PULSAR_CONSOLE_QUEUE_PING_S` | Mechanical | `serve/server.py:396-398` | ENG, CNF, R-engine | ENG-09 |
| `MAYA_REQUEST_QUIET_S` | `PULSAR_CONSOLE_REQUEST_QUIET_S` | Mechanical | `serve/server.py:742` | ENG, R-engine | ENG-07 |
| `MAYA_REQUEST_TIMEOUT_S` | `PULSAR_CONSOLE_REQUEST_TIMEOUT_S` | Mechanical | `serve/server.py:5355-5359` | R-api | API-02 |
| `MAYA_RESTART_ON_UPDATE` | `PULSAR_CONSOLE_RESTART_ON_UPDATE` | Mechanical | `serve/update.py:21`, `serve/server.py:2873` | OPS, R-launch | OPS-11 |
| `MAYA_SAVINGS_PATH` | `PULSAR_CONSOLE_SAVINGS_PATH` | Mechanical | `serve/savings.py:28-30` | OPS, R-ops | OPS-21 |
| `MAYA_SERVER_LOG` | `PULSAR_CONSOLE_SERVER_LOG` | Mechanical | `serve/server.py:7101` | R-api | API-16 |
| `MAYA_TURN_TRACE` | `PULSAR_CONSOLE_TURN_TRACE` | Mechanical | `serve/server.py:2093` | API, ENG, R-api | API-16 |
| `MAYA_UPDATE_CHECK` | `PULSAR_CONSOLE_UPDATE_CHECK` | Mechanical; meaning changes to opt-in (SEC-5) | `serve/update.py:75` | OPS, CNF, R-ops | OPS-22 |
| `MAYA_VIDEO_MAX_FRAMES` | `PULSAR_CONSOLE_VIDEO_MAX_FRAMES` | Mechanical | `serve/server.py:1926-1931` | RSP, ENG, R-resp | RSP-18 |
| `MAYA_PULL_COMMAND` | none | Removed (SEC-7): the download command is not overridable from the environment | `serve/server.py:3115-3121` | OPS, R-ops | OPS-15 |

### 3.2 Responses limits

`serve/response_config.py:4-14` builds 18 names as `MAYA_GLM_RESPONSES_` plus a key. Under
rule 9 each becomes `PULSAR_CONSOLE_GLM_RESPONSES_<KEY>`. The Responses planner proposed
`PULSAR_CONSOLE_RESPONSES_<KEY>` instead, dropping `GLM_`; that is open item N2. Owner:
RSP-01. Records: RSP, R-resp.

| Old name | New name | Status |
| --- | --- | --- |
| `MAYA_GLM_RESPONSES_CACHE_ENTRIES` | `PULSAR_CONSOLE_GLM_RESPONSES_CACHE_ENTRIES` | Mechanical; suffix open (N2) |
| `MAYA_GLM_RESPONSES_CACHE_BYTES` | `PULSAR_CONSOLE_GLM_RESPONSES_CACHE_BYTES` | Mechanical; suffix open (N2) |
| `MAYA_GLM_RESPONSES_CACHE_TTL_S` | `PULSAR_CONSOLE_GLM_RESPONSES_CACHE_TTL_S` | Mechanical; suffix open (N2) |
| `MAYA_GLM_RESPONSES_ENTRY_BYTES` | `PULSAR_CONSOLE_GLM_RESPONSES_ENTRY_BYTES` | Mechanical; suffix open (N2) |
| `MAYA_GLM_RESPONSES_OWNER_ENTRIES` | `PULSAR_CONSOLE_GLM_RESPONSES_OWNER_ENTRIES` | Mechanical; suffix open (N2) |
| `MAYA_GLM_RESPONSES_OWNER_BYTES` | `PULSAR_CONSOLE_GLM_RESPONSES_OWNER_BYTES` | Mechanical; suffix open (N2) |
| `MAYA_GLM_RESPONSES_ASSEMBLY_BYTES` | `PULSAR_CONSOLE_GLM_RESPONSES_ASSEMBLY_BYTES` | Mechanical; suffix open (N2) |
| `MAYA_GLM_RESPONSES_JOB_WORKERS` | `PULSAR_CONSOLE_GLM_RESPONSES_JOB_WORKERS` | Mechanical; suffix open (N2) |
| `MAYA_GLM_RESPONSES_JOB_ENTRIES` | `PULSAR_CONSOLE_GLM_RESPONSES_JOB_ENTRIES` | Mechanical; suffix open (N2) |
| `MAYA_GLM_RESPONSES_JOB_OWNER_ENTRIES` | `PULSAR_CONSOLE_GLM_RESPONSES_JOB_OWNER_ENTRIES` | Mechanical; suffix open (N2) |
| `MAYA_GLM_RESPONSES_JOB_TIMEOUT_S` | `PULSAR_CONSOLE_GLM_RESPONSES_JOB_TIMEOUT_S` | Mechanical; suffix open (N2) |
| `MAYA_GLM_RESPONSES_JOB_TTL_S` | `PULSAR_CONSOLE_GLM_RESPONSES_JOB_TTL_S` | Mechanical; suffix open (N2) |
| `MAYA_GLM_RESPONSES_JOB_INPUT_BYTES` | `PULSAR_CONSOLE_GLM_RESPONSES_JOB_INPUT_BYTES` | Mechanical; suffix open (N2) |
| `MAYA_GLM_RESPONSES_EVENT_BYTES` | `PULSAR_CONSOLE_GLM_RESPONSES_EVENT_BYTES` | Mechanical; suffix open (N2) |
| `MAYA_GLM_RESPONSES_EVENT_COUNT` | `PULSAR_CONSOLE_GLM_RESPONSES_EVENT_COUNT` | Mechanical; suffix open (N2) |
| `MAYA_GLM_RESPONSES_STREAM_READERS` | `PULSAR_CONSOLE_GLM_RESPONSES_STREAM_READERS` | Mechanical; suffix open (N2) |
| `MAYA_GLM_RESPONSES_STREAM_OWNER_READERS` | `PULSAR_CONSOLE_GLM_RESPONSES_STREAM_OWNER_READERS` | Mechanical; suffix open (N2) |
| `MAYA_GLM_RESPONSES_STREAM_TIMEOUT_S` | `PULSAR_CONSOLE_GLM_RESPONSES_STREAM_TIMEOUT_S` | Mechanical; suffix open (N2) |

### 3.3 Legacy aliases

| Old name | New name | Status | Donor location | Records |
| --- | --- | --- | --- | --- |
| `STRATA_<X>` (every legacy fallback name) | none | Removed: not accepted (rule 2) | `tools/maya_names.py:1-40` | API, ENG, OPS, R-api |
| `MAYA_<X>` for any server setting | none | Removed: not accepted (rule 2) | `tools/maya_names.py:1-40` | API, OPS |

### 3.4 Engine-interface names (verbatim)

These names belong to project-maya's engines and to the fake engines that reproduce them.
When they appear in a run config's `env` block they pass to the engine child unchanged
(rule 3). Some are also read by the Models-page settings logic (OPS-05) as engine
settings; they are still engine data, not PulsarMLX Console settings. PulsarMLX Console
never launches a project-maya engine binary (decision B10), so in this increment these
names reach only the Rust fake engines or are unused.

| Old name | New name | Status | Donor location | Records |
| --- | --- | --- | --- | --- |
| `MAYA_GLM_SLOT_KEEP` | `MAYA_GLM_SLOT_KEEP` | Verbatim | `serve/glm_dsa_fake_engine.py:42`, `serve/server.py:1703` | ENG, CNF, R-engine |
| `STRATA_GLM_SLOT_KEEP` | `STRATA_GLM_SLOT_KEEP` | Verbatim if present in an `env` block; never synthesized (rule 3) | as cited by ENG | ENG |
| `MAYA_GLM_VISION_LEND_MB` | `MAYA_GLM_VISION_LEND_MB` | Verbatim | as cited by ENG and RSP | ENG, RSP, R-engine |
| `MAYA_EXPERT_RAM_GB` | `MAYA_EXPERT_RAM_GB` | Verbatim; display in the UI is open (N4) | `serve/models.py:350` | WEB, R-ops |
| `MAYA_DS4_DRAFT_DEV` | `MAYA_DS4_DRAFT_DEV` | Verbatim; display in the UI is open (N4) | as cited by WEB | WEB |
| `MAYA_DS4_DSPARK_CUM`, `MAYA_DS4_RAM_SKIP_W`, `MAYA_DS4_RESIDENT_TOPK` | unchanged | Verbatim | `serve/models.py:876` | R-ops |
| `MAYA_DS4_SLOT_KEEP` | unchanged | Verbatim | `serve/frontend.py:286` | R-ops |
| `MAYA_GLM_KV_INT8`, `MAYA_GLM_IDX_FP16`, `MAYA_GLM_KV_RESIDENT`, `MAYA_GLM_RESIDENT_TOPK`, `MAYA_GLM_ROUTE_AFFINITY`, `MAYA_GLM_MISS_SKIP_FROM`, `MAYA_GLM_MISS_SKIP_W` | unchanged | Verbatim | `serve/models.py:383-403`, `:875-882` | OPS, R-ops |
| `MAYA_GLM_EXPERT_CACHE`, `MAYA_GLM_PREFILL_CHUNK` | unchanged | Verbatim | engine documentation (`docs/SETTINGS.md`), not read by `serve/` | OPS, R-ops |
| `MAYA_GLM_HELPER_EXE`, `MAYA_GLM_EXPERT_HELPER`, `MAYA_GLM_SPLIT`, `MAYA_GLM_CPU_CAL`, `MAYA_GLM_MTP_FIXED`, `MAYA_GLM_MTP_ADAPT`, `MAYA_GLM_PREFILL_MB`, `MAYA_GLM_PREFILL_SUB`, `MAYA_HIPBLASLT_TUNING` | unchanged | Verbatim, subject to the SEC-7 denylist (names ending in `_EXE` are refused from the Models page) | `serve/glm_link.py:24`, `:98-105` | ENG, R-engine, R-ops |
| `MAYA_GLM_LOOP_ANSWER`, `MAYA_GLM_LOOP_THINK`, `MAYA_GLM_NO_REUSE`, `MAYA_GLM_SLOTS`, `MAYA_GLM_SLOT_DAYS`, `MAYA_GLM_SLOT_DIR`, `MAYA_GLM_SLOT_GB`, `MAYA_GLM_SLOT_MIN`, `MAYA_GLM_SLOT_RAM_GB`, `MAYA_GPU_RELEASE_S` | unchanged | Verbatim | engine documentation as read by R-engine | ENG, R-engine |
| `MAYA_GLM_CPU_SPLIT`, `MAYA_GLM_LANE_ROW4`, `MAYA_GLM_MTP_KEEP`, `MAYA_GLM_NGRAM_DRAFT`, `MAYA_GLM_PREFETCH_AT`, `MAYA_GLM_PREFETCH_BLOCKS`, `MAYA_GLM_PREFETCH_N`, `MAYA_GLM_PREFETCH_RANK`, `MAYA_GLM_PROMOTE_MIN`, `MAYA_GLM_VRAM_EVICT`, `MAYA_GLM_PREFILL_INTERLEAVE`, `MAYA_MIXED_FRONT` | unchanged | Verbatim | `serve/glm_dsa_tune.py:1`, `serve/fake_multi_engine.py:2`, `serve/mixed_gpus.py:266` (static scan; not named in the records) | none |
| `FAKE_ENGINE_*`, `FAKE_MULTI_INTERLEAVE`, `FAKE_MCP_LOG` | unchanged | Decided (lead decision of 2026-11-14): control variables of the fake engines and the fake MCP server keep the donor fakes' names, because they are a test-double interface, not product identity | `serve/glm_dsa_fake_engine.py`, `serve/fake_multi_engine.py`, `serve/mcp_fake_server.py` | CNF |

### 3.5 Launcher, engine-build and donor-test names (not ported)

| Old name | New name | Status | Records |
| --- | --- | --- | --- |
| `MAYA_SH`, `MAYA_GGUF_PY`, `MAYA_WATCHDOG_S` | none | Not ported: the donor launcher is outside this increment (PLAT-3) | R-launch |
| `MAYA_ENABLE_METAL`, `MAYA_GGML_DIR`, `STRATA_ENABLE_HIP`, `MAYA_METAL_ALLOW_ANY_GPU`, `MAYA_METAL_ATTN_CHUNK`, `MAYA_METAL_CPU`, `MAYA_METAL_KV_F32`, `MAYA_METAL_POOL_SLOTS`, `MAYA_METAL_PORTABLE`, `MAYA_METAL_TESTS`, `MAYA_METAL_UBATCH`, `MAYA_MM3_CPU`, `MAYA_GLM_MTP_DECODE`, `MAYA_GLM_MTP_DRAFT`, `MAYA_GLM_NO_MTP`, `MAYA_GLM_RAM_HEADROOM_GB`, `MAYA_GLM_RESERVE_MB` | none | Not ported: engine build or engine runtime settings of project-maya engines, which are out of scope (decision B10); verbatim if they appear in an `env` block | R-plat, R-launch, R-ops |
| `MAYA_TEST_ENGINE`, `MAYA_TEST_PACK`, `MAYA_TEST_ARGS`, `MAYA_TEST_CONTEXT`, `MAYA_TEST_EXPERTS`, `MAYA_TEST_LOG`, `MAYA_TEST_READY_S`, `MAYA_TEST_REQUIRE_A29`, `MAYA_TEST_SPLIT`, `MAYA_TEST_TEXT_ONLY` | none in the Rust tests | Not ported as Console settings. The donor's own `serve/test_engine_contract.py` reads them when it runs as a shim in the manual reference job, where they keep the donor's names because they are read by donor code | R-engine, CNF |
| `MAYA_TOKENIZER`, `MAYA_TEST_TOKENIZERS`, `MAYA_WRITE_FIXTURE`, `MAYA_MM3_TEMPLATE` | `PULSAR_CONSOLE_TOKENIZER`, `PULSAR_CONSOLE_TEST_TOKENIZERS`, `PULSAR_CONSOLE_WRITE_FIXTURE`, `PULSAR_CONSOLE_MM3_TEMPLATE` | Decided (lead decision of 2026-11-14): test-only settings take the mechanical name `PULSAR_CONSOLE_<old suffix>` | PRM, R-prompt |

### 3.6 Files and directories

| Old name | New name | Status | Donor location | Records | Package |
| --- | --- | --- | --- | --- | --- |
| `maya-<name>.json` (run configs) | `pulsar-<name>.json` | Decided (B2) | `serve/models.py:682`, `:724-727` | OPS, R-ops | API-15, OPS-07 |
| `maya-` stripped from public model names | `pulsar-` stripped | Decided (B2), follows the file prefix | `serve/model_api.py:45-52` | OPS | OPS-12 |
| `.maya-switch.json` | `.pulsar-switch.json` | Decided (B2) | `serve/models.py:32` | OPS, R-ops | OPS-10 |
| `.maya-delete.json` | `.pulsar-delete.json` | Decided (B2) | `serve/models.py:33` | OPS, R-ops | OPS-09 |
| `.maya-verified.json` | `.pulsar-verified.json` | Decided (B2) | as cited by R-ops and R-launch | OPS, R-ops | OPS-16 |
| `answers/` and `answers/<id>.jsonl` | unchanged | Kept; written to disk only when enabled (PRIV-1) | `serve/server.py:5130`, `:5140`, `:7348` | API, R-api | API-10 |
| `token-savings.json` | unchanged | Kept | as cited by OPS | OPS | OPS-21 |
| `kept-<pid>.json` (fake engine) | unchanged | Kept | as cited by CNF | CNF, ENG | ENG-05 |
| `maya-pdf-` temporary directory prefix | a `pulsar-` prefix | Rename decided, value proposed | as cited by RSP | RSP, R-resp | RSP-15 |
| `maya-vision-` temporary directory prefix | a `pulsar-` prefix | Rename decided, value proposed | as cited by ENG and RSP | ENG, RSP | ENG-14 |
| `maya-ds4-pictures-`, `maya-mm3-pictures-` | a `pulsar-` prefix | Rename decided, value proposed | as cited by RSP | RSP, R-resp | RSP-17 |
| `maya.py`, `maya.sh`, `START-MAYA.bat` (launchers) | `pulsar-console fetch`, `pulsar-console supervise` | Decided (PLAT-3) | `serve/model_pull.py:193-205` | OPS, R-launch | OPS-11, OPS-16 |

Any new tracked file or directory name is also checked against the repository's
`.gitignore` traps (directories such as `models`, `logs`, `dist`, `env`, `debug`,
`release`, `target`; files such as `*.log`, `*.key`, `secrets.*`, `mcp.json`). Runtime
file names written into a user's data directory are not tracked and are not affected.

### 3.7 Browser storage and dashboard identifiers

| Old name | New name | Status | Donor location | Records | Package |
| --- | --- | --- | --- | --- | --- |
| `maya.<key>` (`localStorage` prefix) | `pulsar.<key>` | Decided (B2); key suffixes and JSON shapes kept | `serve/web/lib.js:28-35` | WEB, R-web | WEB-01 |
| `maya.theme`, `maya.scheme`, `maya.chat`, `maya.chats-fallback`, `maya.current-chat`, `maya.deleted`, `maya.folders`, `maya.folders-open`, `maya.gpu-open`, `maya.model`, `maya.sampling`, `maya.sampling_<family>`, `maya.side-open`, `maya.turbo_<key>`, `maya.apikey` | `pulsar.` with the same suffix | Decided (B2) | `serve/web/state.js:107-124`, `:257`; `serve/web/chats.js:79`, `:106`; `serve/web/models.js:52` | R-web, R-plat | WEB-01 |
| `maya.ablate.scale` | none | Removed (POL-1: the switch is not ported) | as cited by R-ops | R-ops | WEB-09 |
| `strata.<key>` read fallback | none | Removed (rule 2) | `serve/web/lib.js:33` | WEB, R-web | WEB-01 |
| `maya.ui-theme` cleanup, `strata.chat` cleanup | none | Removed: there is no earlier PulsarMLX Console data to migrate (rule 2) | `serve/web/state.js:117`, `serve/web/chats.js:106` | WEB | WEB-01 |
| IndexedDB database `maya` | `pulsar-console` | Decided (B2); store `chats`, key path `id`, version 1 kept | `serve/web/lib.js:46-47` | WEB, R-web | WEB-01 |
| DOM event `maya:context` | proposed `console:context` | Rename decided, value proposed | `serve/web/server.js:235`, `serve/web/models.js:1033` | WEB, R-web | WEB-01 |
| CSS names `--maya-side`, `--maya-read`, `.maya-mark` | neutral names | Rename decided, value proposed | as cited by WEB | WEB, R-web | WEB-01 |
| Global `window.maya` | none under that name; `window.console_debug`, set only with `#debug` in the address | Decided (BRAND-1.9 removes the name; the debug-only replacement is approved deviation P-13, owner decision of 2026-11-14) | `serve/web/app.js:126` | WEB, R-web | WEB-01, WEB-03 |
| Download name `maya-code.<ext>` | proposed `pulsar-code.<ext>` | Rename decided, value proposed | `serve/web/md.js:237` | WEB, R-web | WEB-01 |
| Download name `maya-chat-<stamp>.md` | proposed `pulsar-chat-<stamp>.md` | Rename decided, value proposed | `serve/web/chats.js:734` | WEB, R-web | WEB-01 |
| Page title, manifest name, About text "Project Maya" | "PulsarMLX Console" | Decided (BRAND-1) | as cited by WEB and R-web | WEB, R-web | WEB-01 |

### 3.8 Log lines and user-facing text

| Old name | New name | Status | Donor location | Records | Package |
| --- | --- | --- | --- | --- | --- |
| `[maya] ` log prefix | `[console] ` | Decided (B2) | for example `serve/server.py:926`, `:6155` | API, ENG, RSP, CNF | API-16 and every package that logs |
| `[maya] request failed mid-answer: <message>` | `[console] request failed mid-answer: <message>` | Decided (B2, rule 7); fixed by API-01 (commit `c2392605`), which escapes control characters, U+2028 and U+2029 in the message so the line stays one line | `serve/server.py:6155` | API | API-01 |
| "... only from Maya's own page" | product wording, same status and type | Rename decided, value proposed | `serve/server.py:6336` | API | API-03 |
| "update Maya (./maya.sh --setup)" in request refusals | product wording | Rename decided, value proposed | `serve/server.py:2496`, `:2518`, `:2529-2530` | API | API-04 |
| Death notes pointing to the upstream issue tracker and naming quant names | same meaning, no upstream URL or quant name | Rename decided, value proposed | as cited by ENG | ENG | ENG-08 |
| `/api/report` "System: ..., Python ..." and "Project Maya <version>" | OS identification and `pulsar-console <version>` | Rename decided, value proposed | as cited by API | API | API-13 |
| "Support Maya" sponsor link | none | Removed (BRAND-1) | `serve/web/sidebar.js:280`, `serve/web/lib.js:6` | WEB | WEB-10 |
| Engine log phrases the server parses (for example "session is up", the VRAM-before-the-expert-pool line) | unchanged | Verbatim: engine output parsed as data (the ENG planner's proposal) | as cited by ENG | ENG | ENG-08 |

### 3.9 Wire identifiers

| Old name | New name | Status | Donor location | Records | Package |
| --- | --- | --- | --- | --- | --- |
| `strata_resume` | unchanged | Kept (B2) | `serve/web/chats.js:435`, `serve/server.py:6598-6603` | API, WEB, R-api | API-10 |
| `strata_mcp` | unchanged | Kept (B2) | as cited by RSP and R-resp | RSP, API, WEB | RSP-11 |
| `strata_tune` | unchanged | Kept (B2) | `serve/server.py:1227-1240` | API, ENG, OPS | ENG-03, OPS-04 |
| `strata_level_default` | unchanged | Kept (B2) | as cited by PRM and R-prompt | PRM, API, WEB | PRM-05 |
| `/v1/strata/stream` | unchanged | Kept (B2) | as cited by R-api | API, WEB, CNF | API-10 |
| `/v1/strata/cancel` | unchanged | Kept (B2) | as cited by R-api | API, WEB | API-10 |
| Sealed reasoning prefix `maya-r1:` (emitted) | the product's own prefix; the RSP planner proposed `pcr1:` | Decided that it changes (B2); value open (N1) | `serve/responses.py:29` | RSP, R-resp | RSP-03 |
| Sealed reasoning prefix `maya-r1:` (accepted on input) | undecided | Open (N1) | `serve/responses.py:29` | RSP | RSP-03 |
| `/v1/status` field `service: "maya"` | proposed `"pulsar-console"` | Rename decided, value proposed | as cited by API | API, RSP | API-06 |
| Prometheus prefix `maya:` (`maya:requests_total`, `maya:engine_alive`, `maya:decode_peak_tokens_seconds`, `maya:loop_guard_detected_total`, `maya:responses_cache_*`, `maya:responses_jobs_*`) | proposed `pulsar_console:` | Rename decided, value proposed | as cited by R-api | API, PRM, RSP, R-api | API-06 |
| Prometheus prefix `llamacpp:` | unchanged | Kept | as cited by API | API | API-06 |
| `/props` `build_info` "Strata <version>" | proposed "pulsar-console <version>" | Rename proposed (a product identity string, not a kept wire name) | as cited by API | API | API-11 |
| `/api/version` value | proposed `0.0.0-pulsar` | Rename decided, value proposed | as cited by OPS | OPS | OPS-13 |
| `maya` object in `/api/tags` and `/api/show` | proposed `pulsar` | Rename decided, value proposed | as cited by OPS | OPS | OPS-12 |
| MCP `clientInfo` `{name: "maya", title: "Maya"}` | product name | Rename decided, value proposed | as cited by RSP | RSP | RSP-09 |
| HTTP `User-Agent: maya` (MCP over HTTP, image fetch) | product name | Rename decided, value proposed | `serve/server.py:1824` | RSP | RSP-10, RSP-17 |
| CLI `--engine maya` | proposed `--engine line` | Rename decided, value proposed | as cited by API | API | API-17 |
| Quant labels `Maya-XS`, `Maya-S`, `Maya-M`, `Maya-L` and keys `maya-xs`, `maya-s`, `maya-m`, `maya-l` | neutral labels | Decided that they go (BRAND-1); labels proposed by OPS-03 | as cited by R-ops | OPS, PRM, WEB, R-ops | OPS-03 |
| Default scripted-engine model name `qwen3.8-flash-next` | `pulsar-console-synthetic` | Decided (plan section 12, deviation PLAN-2; the exact value by the owner on 2026-11-14, N6) | `serve/server.py:2383` | API | API-17 |
| `Server: BaseHTTP/0.6 Python/3.x` (HTTP response header value) | `pulsar-console/<version>` | Decided (approved deviation P-1, owner decision of 2026-11-14) | Python `http.server` default; no line in `serve/` | API | API-02 |
| `chatcmpl-`, `msg_`, `call_`, `resp_`, `item_`, `rs_`, `fc_` (id prefixes) | unchanged | Kept: wire identifiers; fixed by API-01 (commit `c2392605`) in `console_pyjson::ids` | `serve/server.py:4936`, `:5251`; `serve/frontend.py:805`; `serve/responses.py:133`, `:354`, `:412-418` | API, PRM, R-api | API-01 |

### 3.10 Test-harness switches

The lead decided on 2026-11-14 that test-harness switches read by the product or its tests
use the `PULSAR_CONSOLE_` prefix, like every other setting (rule 2). The detail files
under [`../tasks/`](../tasks/) use the `CONSOLE_` names listed in the first column; the
code never reads those names. The lead also decided on 2026-11-14 that each switch takes
the mechanical name `PULSAR_CONSOLE_<old suffix>` listed below. Control variables of the
fake engines and the fake MCP server are not test-harness switches in this sense and keep
the donor fakes' names (section 3.4). Workflow-only variables in
`.github/workflows/console.yml` are not read by the product or its tests and are not
listed.

| Old name | New name | Status | Donor location | Records | Package |
| --- | --- | --- | --- | --- | --- |
| `CONSOLE_MAYA_SRC` | `PULSAR_CONSOLE_MAYA_SRC` | Decided (lead decision of 2026-11-14) | none (planner name) | CNF | as named in `tasks/conformance.md` |
| `CONSOLE_VENDOR_DIR` | `PULSAR_CONSOLE_VENDOR_DIR` | Decided (lead decision of 2026-11-14) | none (planner name) | CNF | as named in `tasks/conformance.md` |
| `CONSOLE_VENDOR_SRC` | `PULSAR_CONSOLE_VENDOR_SRC` | Decided (lead decision of 2026-11-14); whether it and `CONSOLE_VENDOR_DIR` are one switch is settled by PRM-02 | none (planner name) | PRM | PRM-02 |
| `CONSOLE_REQUIRE_VENDOR` | `PULSAR_CONSOLE_REQUIRE_VENDOR` | Decided (lead decision of 2026-11-14) | none (planner name) | PRM | PRM-02 |
| `CONSOLE_PACK_TOKENIZER` | `PULSAR_CONSOLE_PACK_TOKENIZER` | Decided (lead decision of 2026-11-14) | none (planner name) | PRM | as named in `tasks/prompt.md` |
| `CONSOLE_TEST_TIME_SCALE` | `PULSAR_CONSOLE_TEST_TIME_SCALE` | Decided (lead decision of 2026-11-14) | none (planner name) | CNF | as named in `tasks/conformance.md` |
| `CONSOLE_REQUIRE_NODE` | `PULSAR_CONSOLE_REQUIRE_NODE` | Decided (lead decision of 2026-11-14) | none (planner name) | WEB | WEB-04 |
| `CONSOLE_E2E` | `PULSAR_CONSOLE_E2E` | Decided (lead decision of 2026-11-14) | none (planner name) | WEB | WEB-06 |

### 3.11 Names with no donor counterpart

These names are new in PulsarMLX Console and have no old name, so they are listed here in
prose, outside the machine-read tables.

- **Run-config key `allowed_hosts`.** Decided by the owner on 2026-11-14 (deviation
  SEC-1.1, open item OPEN-04): an optional list of further `Host` names. It is absent by
  default. Read from the run config by API-15; enforced by API-03.
- **Engine-seam names.** Fixed by ENG-01 (commit `6200f4ac`, 2026-11-14) in
  `console-core::engine`. The engine kinds, as written in logs and in the refusal line:
  `scripted`, `line-protocol`, `coordinator-adapter`, `runtime-adapter`
  (`EngineKind::as_str`). The refusal line starts with `[console] refusing to start: `,
  following rule 7. The failure kinds, as written in logs: `died`, `reported`,
  `not_ready`, `never_answered`, `invalid_token`, `unsupported`, `protocol`, `start_failed`
  (`FailureKind::as_str`). The guard function is `require_synthetic`.

## 4. Maintenance and checking

1. **Every package extends this table** when it ports a setting, file name, storage key,
   log prefix or wire identifier. The row is added in the same change as the code, with
   its donor location and its status. A package that finds a donor name not listed here
   adds it; it does not rename silently.
2. **A test checks the table against the code.** The check reads the tables in section 3,
   and fails when: a `PULSAR_CONSOLE_*` name read by the code has no row; a row marked
   Mechanical or Decided names a variable the code does not read, unless the row says
   the package has not landed yet; any `MAYA_*` or `STRATA_*` name is read by PulsarMLX
   Console code outside the verbatim rows of section 3.4; or a row marked Removed is still
   read. The inventory extracted from the pinned donor source (CNF-12) is compared with the
   old-name column, so a donor name that no row covers is reported. Which package
   implements the check is assigned in `tasks.md`; OPS-02 (settings naming and precedence)
   and CNF-12 (inventories) are the natural owners.
3. **Rows marked "Rename decided, value proposed"** are settled by the owning package and
   recorded in its change; the lead reviews the chosen string against rule 1 (OPEN-35;
   the Prometheus prefix is an owner decision, OPEN-22).
4. **Format.** Each table row starts with the old name in backticks. A row may group
   several names that share every other column, separated by commas. Columns are not
   reordered.

## 5. Open items

Each item is also listed in the register of open items,
[`../checklists/analysis.md`](../checklists/analysis.md), under the id in the last column,
which also says who decides it.

| Id | Item | Register |
| --- | --- | --- |
| N1 | The exact product prefix for sealed reasoning, and whether the donor prefix `maya-r1:` is accepted on input so that histories created against project-maya keep working. B2 leaves acceptance open. | OPEN-01 (input), OPEN-02 (prefix) |
| N2 | Whether the Responses limits keep `GLM_` in their suffix (rule 9) or drop it, as the RSP planner proposed. | OPEN-31 |
| N3 | Settled by the lead on 2026-11-14: the donor's export of each engine setting under both its `MAYA_` and `STRATA_` names is not reproduced; `env` names pass through verbatim, once (rule 3). | OPEN-32 (settled) |
| N4 | How the dashboard shows engine variable names such as `MAYA_EXPERT_RAM_GB` and `MAYA_DS4_DRAFT_DEV`: they are engine-interface names (verbatim), but BRAND-1 forbids Maya names in what the product presents as its own. | OPEN-25 |
| N5 | Settled by the lead on 2026-11-14: test-only settings (section 3.5) and test-harness switches (section 3.10) take the mechanical names `PULSAR_CONSOLE_<old suffix>` listed there. | OPEN-33 (settled) |
| N6 | Settled by the owner on 2026-11-14: the default model name of the scripted engine is exactly `pulsar-console-synthetic` (PLAN-2; section 3.9). | OPEN-03 (settled) |
| N7 | The value of `/props` `build_info`. "Strata" is not Maya's name, so B2 does not require the change; the API planner proposed it because the string presents a product identity. | OPEN-34 |
