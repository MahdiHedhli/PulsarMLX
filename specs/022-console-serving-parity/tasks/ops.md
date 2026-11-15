# Task detail: Model management, operations and telemetry

Feature 022, PulsarMLX Console. This file gives the full specification of each work package
with the prefix `OPS-`. The task list, the milestone order and the binding cross-cutting
decisions are in [`../tasks.md`](../tasks.md); **a binding decision or a reconciliation
there overrides any conflicting sentence in this file**.

Provenance: rendered without paraphrase from the planning records of 2026-11-14 (one planning
agent per subsystem, reading the pinned donor source). Path shorthand: `MAYA` is the pinned
project-maya checkout (commit `7e68a30f`), `ORIGIN` is this repository at `main` when the plan
was written. Sizes are estimates. Donor names such as `MAYA_*` variables describe the donor;
the product names are in [`../contracts/naming.md`](../contracts/naming.md).

## Subsystem summary

This subsystem is project-maya's management plane: the installed-model registry (run configs maya-NAME.json, where file mtime decides which model is most recently used), engine-settings editing, Turbo, model switch and delete, the Ollama-shaped /api/* model API and llama.cpp-style /models/load|unload|sse, the download catalog and one-slot pull driver, hardware telemetry for the Monitor tab, the savings ledger, the self-update route, and the launcher contracts that serve/ relies on (run-config schema, the --parent-pipe lifetime, exit codes 75 and 76, the .maya-switch.json and .maya-delete.json notes). In MAYA that is models.py, model_api.py, model_pull.py, telemetry.py, savings.py, update.py, glm_dsa_product.py, glm_dsa_tune.py, plus the helpers they import (tools/maya_quants.py, maya_names.py, gguf_reader.py) and the matching server.py routes: about 4,000 Python lines, defined by about 178 GPU-free test methods. Full parity means the Rust server, driven by fake engines and fixture filesystems, gives the same answer as MAYA at 7e68a30f on every route, error body (all three error conventions), NDJSON or SSE stream, persisted file (run config, .prev, notes, ledger, verified-files record) and exit code. That includes Python's JSON formatting (indent=1, ensure_ascii) and the mtime-as-recency rule. Two pieces lived outside serve/ and are rebuilt as PulsarMLX-owned binaries in a new console-launch crate. The launcher's supervision becomes a `pulsar-console supervise` subcommand. Its download child (`maya.py --setup --download-model`) becomes `pulsar-console fetch`, which keeps the same progress-line contract, so model_pull's logic and tests carry over unchanged. The settings and Turbo tables for MAYA's four engine families are ported as data-driven 'line-protocol engine profiles', because the D3 line-protocol adapter targets exactly those engines. A new pulsar-mlx profile describes PulsarMLX's own MLX mixed-precision Safetensors checkpoints. In this increment those configs list correctly but can never start, because no MLX engine is attached. Telemetry ports the NVIDIA (crash-isolated NVML child), AMD sysfs and Windows DXGI/PDH readers behind traits, tested with the same fake children and fixture trees MAYA uses and labelled unverified on real hardware. It also adds the Apple Silicon reader that MAYA lacks. Self-update keeps the GET/POST /api/update shapes but becomes an opt-in, check-only notifier that never runs git or new code. That change, branding renames and a few security tightenings are listed as deviations for the owner to approve.

## Build order proposed by the planner

- OPS-01 first: everything persists through it.
- OPS-02 and OPS-03, in parallel.
- OPS-04, OPS-12, OPS-14 (pure), OPS-17, OPS-21, in parallel (OPS-17 needs only a stubbed busy/extras interface).
- OPS-05 (the largest; may be split into two sessions).
- OPS-08 and OPS-10, in parallel.
- OPS-06, OPS-07, OPS-15, in parallel; OPS-07 also needs OPS-08, and OPS-15 needs console-http streaming.
- OPS-09; OPS-16 in parallel with OPS-09.
- OPS-11 and OPS-22 (OPS-22 after OPS-16 for the shared curl helper).
- OPS-18, OPS-19, then OPS-20: telemetry readers, any time after OPS-17, in parallel with the management line; OPS-20 reuses OPS-19's detection order.
- OPS-13, after console-core streaming chat and engine lifecycle are merged.
- OPS-23 last.

## Work packages

<a id="ops-01"></a>
### OPS-01 Python-compatible JSON writer and run-config document store

- **Milestone:** merged into API-01 (JSON writer) and API-15 (run-config document store); kept here as input for the owning package
- **Rust target:** console-manage::registry::{doc, store, pyjson, names}
- **Platform:** platform-neutral
- **Risk:** medium. Float repr and ensure_ascii parity are easy to get subtly wrong. serde_json's PrettyFormatter does not match Python, so a custom Formatter plus a float formatter based on ryu shortest round-trip with Python exponent rules is needed. Other subsystems (Responses store, shared settings) may need the same writer, so it can move to console-core.
- **Depends on:** nothing
- **Estimated size:** 600-800 lines of code; 400-500 lines of tests
- **Donor sources:** serve/models.py L32-54 (constants, SECRET regex, file names), L662-700 (masking, config_paths, read, write), L804-840 (own_defaults .prev write, _commit backup and mtime restore); serve/server.py L2818, L2863, L2918 (other config rewrites), L3155-3158 (note write); maya.py L3895-4051 (config writer schema, for the schema doc only)

**Behaviors to reproduce**

- RunConfig is a serde_json::Map with preserve_order; unknown keys survive every rewrite in their original order; typed accessors for exe, args, env, gpu (list, int or comma string), backend (absent = 'cuda'), installer.*, vision, vision_off, ablate, turbo, sampling, port, host, api_key, model_management and the rest of the keys in the maya-launcher-setup run-config contract.
- Read: UTF-8 with an optional BOM; invalid JSON, a non-object or an IO error gives an empty map, never an error.
- Write: byte-identical to Python json.dumps(obj, indent=1). That means one-space indent, ', ' never used (item separator ',' plus newline, key separator ': '), ensure_ascii escapes (\uXXXX including surrogate pairs), Python float repr (1.0, 1e-05, 0.1) and integers unchanged. Written to NAME.tmp then renamed over NAME.
- Note files (.switch, .delete) are written with compact json.dumps(obj) (', ' and ': ' separators). A dedicated writer mode covers it.
- config_paths(dir): every '<prefix>*.json' whose name does not end with '.shared-settings.json', sorted by mtime newest first; any IO error gives an empty list.
- Backup and recency: CONFIG.prev holds the previous whole document (written non-atomically, as in MAYA). Saves from the page restore the file's previous atime and mtime with std::fs::File::set_times; a switch touches mtime to now.
- File-name validation for 'file' request values: '<prefix>[^/\\]+.json', must not end with .shared-settings.json, must exist in the config directory; otherwise a 400 invalid_request_error with MAYA's message text.
- Secrets: an env value whose NAME matches key|token|secret|password (case-insensitive) is returned as '***' in every outward copy; submitting '***' for such a name keeps the stored value.
- Config directory resolution: the directory of the --config file (MAYA: the launcher folder); the notes, ledger and siblings (.prev, STEM.shared-settings.json, run-STEM.sh/.bat, STEM.log) are resolved relative to it.

**Parity tests**

test_models.Page.test_secrets_in_the_environment_stay_on_this_pc, test_models.Page.test_another_models_settings_leave_which_one_starts_next, test_models.Settings.test_glm_written_back_with_the_rest_kept (preservation part); plus a new golden-file suite. Python json.dumps outputs for about 40 tricky documents are captured by hand from reading the Python semantics (non-ASCII, floats, nested empty containers) and committed as fixtures. They are never produced by running MAYA.

**Definition of done**

Golden fixtures round-trip byte-for-byte. A document with unknown nested keys survives read, modify and write with key order kept. mtime is unchanged after a page save and advanced after touch. config_paths order is verified with explicit mtimes set through set_times. The three listed MAYA tests are re-expressed in Rust and pass. No regex crate is used for the file-name rule. cargo clippy -D warnings is clean.

<a id="ops-02"></a>
### OPS-02 Settings sources, environment naming and precedence

- **Milestone:** M7
- **Rust target:** console-manage::settings_env
- **Platform:** platform-neutral
- **Risk:** low. Must agree with the HTTP and core planners on who parses the CLI. This package supplies the precedence resolver and the name table, and the binary's clap layer consumes them.
- **Depends on:** OPS-01
- **Estimated size:** 350-500 lines of code; 300-400 lines of tests
- **Donor sources:** tools/maya_names.py (78 lines); serve/server.py L599-609 (model_management_setting), L2036-2058 (child_env), L6737-6755 (SERVER_ENV copied from the config env block), L7115-7176, L7313, L7327 (CLI over config over default); docs/SETTINGS.md L6-7, 94, 165, 261-263

**Behaviors to reproduce**

- One table maps every server-level setting MAYA reads (MAYA_UPDATE_CHECK, MAYA_SAVINGS_PATH, MAYA_RESTART_ON_UPDATE, MAYA_MODEL_MANAGEMENT, MAYA_API_KEY, the SERVER_ENV list) to its PulsarMLX name (proposed prefix PULSAR_CONSOLE_; see deviations). The table is also emitted as a contract document.
- SERVER_ENV keys found in the config's env block are copied into the process settings at start and override the shell (MAYA order). MODEL_MANAGEMENT and SERVER_LOG are the exceptions where the environment wins over the config key.
- model_management_setting(cfg, env): on by default. Config model_management:false turns it off. The env value 0/off/false/no turns it off and 1/on/true/yes turns it on, and env wins (test_server.ModelManagement.test_on_unless_the_config_turns_it_off).
- host, api_key (comma-separated list allowed), idle_unload_s and gpu: command line over config over default. Default host 127.0.0.1, server default port 8095, the supervisor's default port 8080 (see OPS-11).
- child_env(cfg, base_env, backend) for the engine adapter: the base environment, then HIP_VISIBLE_DEVICES for hip, or CUDA_DEVICE_ORDER=PCI_BUS_ID plus CUDA_VISIBLE_DEVICES for any backend other than metal, mlx or synthetic, then the cfg.env entries (config wins), then DS4_YOCO_CONE=1|0 when cfg.fast_prefill is a bool, then cfg.lib_dirs prepended to LD_LIBRARY_PATH (PATH on Windows). Pure function, returns a map.
- Engine-passthrough variable names inside a config env block (MAYA_GLM_*, MAYA_DS4_*) are carried verbatim, because they are the line-protocol engines' interface (see open questions). The STRATA_ alias layer is dropped (deviation).

**Parity tests**

test_server.ModelManagement.test_on_unless_the_config_turns_it_off (precedence part), test_models.Settings.test_deepseek_fast_prompt_reading_is_an_opt_in_switch (child_env part); new unit tests for each precedence row of the 'Settings sources and precedence' contract.

**Definition of done**

Every precedence row from the contract has a passing unit test. The env-name mapping table exists as specs/022-*/contracts/ops-environment.md and is generated from or checked against the Rust table by a test. child_env output matches MAYA for cuda, hip, metal and synthetic fixtures.

<a id="ops-03"></a>
### OPS-03 Model classification: family, quant label, GGUF and MLX checkpoint probes, context range

- **Milestone:** M7
- **Rust target:** console-manage::registry::{classify, gguf_probe, mlx_probe, context}
- **Platform:** platform-neutral
- **Risk:** low. Uses no engine-track crate (crates/gguf and safetensors-catalog would couple the console build to hashed engine sources); the probes are small and bounded.
- **Depends on:** OPS-01
- **Estimated size:** 700-900 lines of code; 500-650 lines of tests
- **Donor sources:** tools/maya_quants.py L19-330 (QUANTS table, family_of L262-274, label logic); serve/models.py L34-46 (context presets), L129-188 (trained_context, context_range), L715-738 (quant_label, missing); tools/gguf_reader.py (146 lines); maya.py L1755-1765 (quick GGUF probe)

**Behaviors to reproduce**

- family_of(cfg): minimax when installer.family == minimax or the exe basename starts with the MiniMax engine prefix; qwen when installer.family == qwen or --ple-gguf is in args; deepseek when installer.family == deepseek, --pack is in args, or the exe starts with the DeepSeek engine prefixes; otherwise glm. New: pulsar-mlx when installer.format == 'mlx-safetensors', and synthetic when backend == 'synthetic'.
- quant_label(cfg): a data-driven quant table keyed by installer key gives the label. An EXL3 folder named '...-N.NNbpw' becomes 'EXL3 N.NN bpw'. Otherwise the installer key, otherwise the file stem without the prefix and without '-hip'. MAYA's own tier names are replaced by neutral labels (deviation).
- missing(cfg): 'its engine or pack is not set' when exe is absent or neither --glm-pack nor --pack is in args (line-protocol profiles), and 'its model files are not on this PC (DIR)' when the pack directory is absent. For pulsar-mlx: 'its checkpoint is not set' or the directory text when config.json or model.safetensors.index.json is absent. For backend mlx: 'no engine for this backend in this build' (D3).
- GGUF v3 header probe: magic, version, counts, key-value scan, general.architecture, ARCH.context_length. The first shard is *-00001-of-*.gguf, otherwise *.gguf. Strings over 1 MiB abort. Truncated or corrupt files give None. Bounded reads only.
- DeepSeek and MiniMax trained context comes from 'max_position_embeddings N' in pack/ds4.txt or pack/mm3.txt. pulsar-mlx comes from config.json max_position_embeddings (or text_config.max_position_embeddings). Results are cached only when found.
- context_range(trained, current, engine_kind) = {min:4096, max:max(trained or 262144, current), trained, tested: 1048576 for ds4 and 262144 otherwise}. Preset lists: GLM [8192,32768,65536,131072]; DeepSeek and MiniMax [32768..1048576]; Qwen [32768..262144].
- MLX checkpoint descriptor: reads config.json quantization {bits, group_size, per-module overrides} and reports a neutral label ('MLX 4-bit g64' or 'MLX mixed 4/8-bit'), shard count and total bytes from the index. Read-only; payloads are never opened.

**Parity tests**

test_models.Settings.test_context_range_per_model, test_listing (label parts), test_exl3_label_from_the_folder, test_the_qwen_models_label, test_installs_the_setup_no_longer_lists_are_still_listed; test_glm_dsa_models.Page.test_labels; re-expressed with neutral quant names and synthetic GGUF headers built in the test, plus MLX config.json fixtures.

**Definition of done**

All listed tests re-expressed and passing. The GGUF probe refuses malformed headers, tested with fuzz-style truncation over every prefix length. pulsar-mlx and synthetic configs classify correctly. An mlx-backend config reports ok:false with the D3 text.

<a id="ops-04"></a>
### OPS-04 GLM-DSA product facts and per-request tune knobs

- **Milestone:** M7
- **Rust target:** console-manage::registry::glm_dsa and console-manage::tune (engine_keys exported to console-engine)
- **Platform:** platform-neutral
- **Risk:** low. The float repr of share keys must match Python repr (0.5, 1.0); reuse the OPS-01 float formatter.
- **Depends on:** OPS-03; named capability from console-engine: a GEN-line extension hook (StrataEngine.sampling_keys equivalent)
- **Estimated size:** 350-450 lines of code; 300-400 lines of tests
- **Donor sources:** serve/glm_dsa_product.py (195 lines: pack_is_glm_dsa, config_pack, geometry, kv_bytes_per_token, kv_bytes_of, pack_headwise_q8, pack_bytes, drafting_estimate, constants); serve/glm_dsa_tune.py (59 lines: engine_keys); serve/models.py L382-392 (kv bytes with the MAYA_GLM_KV_INT8 override)

**Behaviors to reproduce**

- A pack is GLM-5.3 when index.txt has a comment header line matching '#\s*glm-dsa:'. geometry() parses trunk, mtp and 'indexer full I,J,...'.
- kv bytes per context token = layers*(latent + rope) + index layers * key bytes. That is 79*672 + 22*512 = 64,352 with the INT8 latent and 102,272 with FP16. The env MAYA_GLM_KV_INT8 in the config wins over --kv.
- Constants exported for the listing: label 'GLM-5.3 (744B)', MEMORY_GB 245, DENSE_GB 14.5, KV_BYTES 64352, RESERVE_MIB 700, KV_STREAMING false, and the rest. pack_bytes and drafting_estimate are ported pure, for parity.
- engine_keys(tune): for a strata_tune object, emits ' k=v' in KEYS order. Integer keys are range-checked (a JSON bool is not an integer). Word keys must be in their set. Switch keys accept bool or 0/1 and are written as 0/1. Share keys are floats in [0,1], written in Python repr. Anything else, or a non-object, gives ''.
- The vendor chat-template path (data/glm-dsa/templates/glm-5.3.official.jinja) is not vendored. The constant becomes a configurable path that is absent by default.

**Parity tests**

test_glm_dsa_models.CacheBytes (2), test_glm_dsa_tune.Whitelist (4) as pure unit tests; test_glm_dsa_tune.RequestBody.test_openai_and_anthropic and EngineLine.test_gen_line re-expressed against the fake line-protocol engine once console-engine and console-http exist.

**Definition of done**

All 8 tests listed are re-expressed and pass, the two integration ones behind the fake engine. engine_keys output matches the Python reading for a table of 30 inputs derived from the docstring ranges.

<a id="ops-05"></a>
### OPS-05 Engine-settings profiles: settings_of, choices, apply, commit, ablation, own defaults

- **Milestone:** M7
- **Rust target:** console-manage::profiles::{glm, glm_dsa, deepseek, minimax, qwen, pulsar_mlx, synthetic, env_guard, ablate}
- **Platform:** platform-neutral
- **Risk:** high. Largest table-driven surface; many small asymmetries per family. The reviewer must diff against models.py L191-659 line by line. Worth splitting into two sessions if a coder struggles: (a) glm, glm-dsa, qwen; (b) deepseek, minimax, ablation.
- **Depends on:** OPS-01; OPS-03; OPS-04
- **Estimated size:** 1200-1500 lines of code; 900-1100 lines of tests
- **Donor sources:** serve/models.py L49-61 (allowed keys per family), L191-659 (settings_of, choices, apply for glm, deepseek, minimax, qwen and glm-dsa; ablate_args L248-299), L804-840 (own_defaults, _commit); serve/server.py L2967-2991 (settings wrapper, dry run, restart), L6368-6390

**Behaviors to reproduce**

- Each family's allowed keys are exactly MAYA's tables. An unknown key gives 'not a setting of this model: K'. pulsar-mlx and synthetic allow {context, images, env}.
- apply() validates the whole patch, merged over settings_of, on a deep copy before anything changes; keys left out keep the config's value.
- Ranges and enums as in the reader contract: context 1024..1048576 (--max-context, default 32768 when absent); gpus a non-empty list of 0..63, sorted and unique, written to cfg.gpu only when changed; parallel 1..8; reserve_mib 0..65536; expert_cache and prefill accept an empty value meaning auto; DeepSeek tp 1..max(2, number of GPUs); MiniMax tp in {0,1,2,4} with 0 removing --tp; mmap auto|on|off; MiniMax kv_cache bf16|int8|fp8|fp4; Qwen kv fp16|int8|k8v4|q4_0; reserve_gb, cache_gb, dspark_conf, ram_gb, cpu_threads, prefill_chunk, kv_resident ranges as MAYA.
- Backward-compatible flag writing: a flag absent from an older config is written only when its value changes (test_an_older_glm_config_keeps_its_command).
- Images off moves vision to vision_off for GLM and Qwen; DeepSeek writes --vision off or drops the flag; MiniMax writes --vision on|off.
- Env guard: names must match [A-Za-z_][A-Za-z0-9_]*. The page cannot add or change LD_*, DYLD_*, PYTHON*, PATH, PATHEXT, BASH_ENV, ENV, IFS, COMSPEC, SYSTEMROOT (case-insensitive), plus the extended list in the deviations; values the config already has are kept.
- Ablation: offered only for deepseek, minimax and glm (not GLM on metal, not MiniMax with tp > 0) and only when the direction file exists. The default goes to cfg.ablate.default without a restart. Writes --ablate FILE --ablate-default off [--ablate-scale S].
- _commit: changed = any of args, env, gpu, vision or vision_off differ. Writes CONFIG.prev. Records installer.as_set_up = settings_of(old) the first time. Atomic write, mtime restored.
- own_defaults(cfg) writes the model's own sampling and reasoning effort when they differ (glm {1.0, 0.95}, max; deepseek {1.0, 1.0}, high; minimax {1.0, 0.95}, auto; qwen {1.0, 0.95, top_k 20}, xhigh; glm53 {1.0, 0.95}, max), with a .prev backup and mtime preserved.
- dry_run returns {command:{exe basename, args, env masked}, settings} and saves nothing.

**Parity tests**

test_models.Settings (19 settings tests: glm read and written, dflash2 gating, checked-before-change, older config, loader variables, deepseek x6, minimax x3) (count corrected against the donor source), test_models.Ablate (4), test_glm_dsa_models.Apply (2), Page.test_choices and test_settings, Defaults (2): about 29 methods, transliterated with temp directories.

**Definition of done**

All about 29 tests re-expressed and passing. A table in specs/022 lists every key, range and flag per family, cross-checked by a test that iterates the Rust tables. dry_run never touches the filesystem: the test checks directory mtime and listing are unchanged.

<a id="ops-06"></a>
### OPS-06 Turbo preset and /api/turbo

- **Milestone:** M7
- **Rust target:** console-manage::turbo
- **Platform:** platform-neutral
- **Risk:** medium. Snapshot and restore exactness across interleaved page edits is subtle.
- **Depends on:** OPS-05; OPS-10
- **Estimated size:** 400-550 lines of code; 450-550 lines of tests
- **Donor sources:** serve/models.py L852-979 (turbo_patch, turbo_enable, turbo_disable); serve/server.py L2993-3021, L6061-6064, L6392-6405

**Behaviors to reproduce**

- turbo_patch per family: context down to 32768 for glm and minimax (a smaller context is kept); parallel 1; draft dspark (deepseek, minimax) or mtp (qwen) when available; dspark_conf 0.3; DeepSeek prompt_lookup on. Env additions are the GLM, DeepSeek and GLM-5.3 sets from the reader contract, and the *_RESIDENT_TOPK cap is dropped for the smallest-quant ids (neutral id in place of maya-xs).
- turbo_enable stores cfg.turbo = {since, before, args, env, applied{args, env}}. turbo_disable restores args and env whole when nothing changed since, otherwise re-applies only 'before'. Turbo on, then off, is exact.
- GET /api/turbo without a run config: {on:false, engine:false, plan:{}, env:{}, restarts:false, family:null}. With a config: {on, family, since?, plan:{k:{from,to}}, env, engine:true, restarts, restarting}.
- POST {on:bool} with the own-page guards. A bad body gives 400 'send {"on": true} or {"on": false}'. 'Turbo is already on' and 'Turbo is not on' are 400. Answers 202 when the engine restarts now, else 200, with the GET shape plus {restarting_now, changed}.
- pulsar-mlx and synthetic profiles have an empty plan, so 'nothing to change needs no restart' applies.

**Parity tests**

test_turbo.ResidentSkip (5, of which test_the_engines_read_the_options_and_the_docs_name_them is re-expressed against the specs table instead of C++ sources), TurboMap (6), TurboSnapshot (7) (count corrected against the donor source), TurboServer (2); test_glm_dsa_models.Turbo (2). TurboPageSide (5) belongs to the web planner (JS).

**Definition of done**

22 tests re-expressed and passing. The GET shape without a config is verified through HTTP against a server started with no run config.

<a id="ops-07"></a>
### OPS-07 Model listing, machine GPU inventory and the GET /api/models and settings routes

- **Milestone:** M7
- **Rust target:** console-manage::listing and console-manage::gpu_inventory
- **Platform:** platform-neutral
- **Risk:** medium. Key order in describe() is asserted by MAYA tests. Serialise from an ordered map, not a struct with reordered fields.
- **Depends on:** OPS-05; OPS-08; OPS-10; named capability from console-http: router, API-key check, own-page guards, the three error-body conventions
- **Estimated size:** 600-800 lines of code; 500-650 lines of tests
- **Donor sources:** serve/models.py L741-801 (describe, listing, machine_gpus); serve/server.py L2931-2991, L6065-6068, L6368-6390; MAYA/setup.py gpus() (nvidia-smi CSV) and amd_gpus() (KFD topology), imported at runtime by models.py

**Behaviors to reproduce**

- describe() keys in this tested order: [shown, kv_bytes only for GLM-5.3], file, path, model, family, quant, backend, written, used, running, port, script, folder, size, ok, missing, settings, setup, choices, command{exe, args, env}, contexts, context_range.
- size = regular files one level deep in the pack parent plus the pack (null when 0). script = run-STEM.sh or .bat when present. running = the resolved path equals the server's config.
- GET /api/models = {models (most recently used first), gpus, contexts:[8192,32768,65536,131072], restarts, running, restarting, deleted, loaded, can_unload, pull, leftovers}. Folder sizes and leftovers are cached with an mtime-keyed invalidation, so listing does not walk on every 1 s poll (behaviour unchanged).
- GpuInventory trait: NvidiaSmiCsv (parses the CSV query output), AmdKfdTopology (parses a sysfs topology tree under a configurable root), and AppleUnified (one entry {index 0, name, vram_gb = unified memory GB}; deviation). Cached 60 s per backend; failure gives []. Indices named by a config but missing on the machine are added with name and vram_gb null, sorted by index.
- POST /api/models/settings: {file, settings, dry_run?}. dry_run answers 200 {command, settings}; a save answers 202 {changed, prev?, running, restarts}. For the running model with changed and supervised, it triggers the OPS-10 restart with why 'settings'.

**Parity tests**

test_models.Settings.test_listing; Page.test_listed, test_files_gone, test_dry_run_saves_nothing, test_saved_without_a_restart_here, test_running_one_starts_again_with_its_new_settings; test_glm_dsa_models.Page.test_describe, test_startable_as_released; nvidia-smi and KFD parsers get new fixture tests (the MAYA counterparts live in launcher tests that were not ported).

**Definition of done**

8 listed tests pass through HTTP against the fake engine. GPU parsers pass on fixture files. GET /api/models stays under 50 ms on a fixture models folder of 2,000 files after the first call.

<a id="ops-08"></a>
### OPS-08 Delete plan and reference graph (read-only)

- **Milestone:** M7
- **Rust target:** console-manage::delete::plan
- **Platform:** platform-neutral
- **Risk:** high. Wrong answers here delete shared data. Requires symlink and hard-link fixtures built with std::os::unix::fs. Must never follow a symlink out of a root during the walk.
- **Depends on:** OPS-01; OPS-03
- **Estimated size:** 900-1200 lines of code; 900-1100 lines of tests
- **Donor sources:** serve/models.py L982-1262 (runs_from, shared, linked-from walk, delete_plan safety rules)

**Behaviors to reproduce**

- delete_plan returns {ok, why, items:[{path, what: folder|pack|gguf|vision|drafter, bytes, linked}], bytes, folder, gguf, pack, vision, drafter, drafter_users, shared:[{path, what, users, files?}], linked, kept:[sentences]}.
- Safety: requires installer.models_dir and a pack (or, for pulsar-mlx, the checkpoint directory). The models folder must be a known one (some config's models_dir, or the default data folder), must exist, must not be a filesystem root and must not contain the home directory. Paths are compared after canonicalising. A candidate must be strictly inside a known models folder and must not contain the project or config folder.
- A path is kept when another config runs from it: its pack, shards from pack/sources.json or native_experts.txt, 'file I PATH' lines of tensors.txt resolved against model_dir from ds4.txt or mm3.txt, its drafter, tokenizer, vision files, or, for pulsar-mlx, its shard set from the index. A path is also kept when another model's folder holds a symlink into it (walk capped at 20,000 entries).
- Hard-linked files (nlink > 1) are not counted as freed bytes.
- The plan is pure and read-only and is recomputed immediately before any deletion (OPS-09).

**Parity tests**

test_models.Delete (10: its own folder and drafter, off the list only, a folder another model runs from, your own gguf stays, a drafter another model drafts with, what another model shares stays and is named, never outside the models folders, unknown models folder, hard links are counted, without the setup's record); test_model_api.Api.test_delete_keeps_what_another_model_runs_from and test_delete_with_files_linked_from_another_model (plan part).

**Definition of done**

12 tests re-expressed with tempfile trees and passing. A property test generates random trees containing symlinks and hard links and asserts no planned item lies outside known roots or is referenced by another config. The reviewer confirms that no function in this package can mutate the filesystem: the module never imports remove or rename.

<a id="ops-09"></a>
### OPS-09 Delete execution, leftovers and deferred delete of the running model

- **Milestone:** M7
- **Rust target:** console-manage::delete::{exec, leftovers, deferred}
- **Platform:** platform-neutral
- **Risk:** high. Two-process deferred deletion, so tests must simulate a restart by constructing a fresh service over the same directory.
- **Depends on:** OPS-08; OPS-10; OPS-15
- **Estimated size:** 500-700 lines of code; 700-850 lines of tests
- **Donor sources:** serve/models.py L1265-1389 (delete, leftovers, delete_leftover); serve/server.py L3045-3153 (routes, the .maya-delete.json note, startup consumption), L6141-6164, L6327-6338

**Behaviors to reproduce**

- delete(config, files): with files, deletes the plan's items (remove_dir_all for real directories, unlink otherwise). Any failure stops the operation, the config is kept and the error says 'the model stays on the list'. Then it always removes the config, run-STEM.sh/.bat, CONFIG.prev and STEM.shared-settings.json, and returns {deleted, freed, files, drafter_users: []}.
- leftovers: top-level non-hidden, non-symlink entries of the models folders of 100 MB or more that no config runs from, plus one level down any folder holding pack marker files. Items are {path, name, bytes, folder, pack, hub, modified}, largest first. delete_leftover recomputes the list and deletes only an exact match, else 400.
- Deleting the running model requires 'then' and supervised mode. It writes the delete note {config, files, time, model, quant}, triggers a switch, and the next process deletes at startup only when the note is under 900 s old, the config is in this folder and it is not the running model.
- POST /api/models/delete {file, files?, dry_run?, then?}: 200 plan, 200 result, or 202 {deleting, to, files, restarts:true}. 400 while a download runs (with files) or a restart is in progress. POST /api/models/leftovers {path}: 200 {deleted, freed}.
- DELETE or POST /api/delete {model|name}: API key or loopback required. Deletes the config and its files (MAYA default kept) and answers 200 {status:'success', freed}. 404 for an unknown model; 409 for the running model, an active download, a plan that is not ok, or an OS error.

**Parity tests**

test_models.Leftovers (4), test_models.DeletePage (6: delete, not while a model downloads, not the one running, the running one after a switch, a switch that did not happen deletes nothing, leftovers from the page only), test_model_api.Api delete tests (route part).

**Definition of done**

10 tests plus the two Api delete tests pass. Stale-note (over 900 s), foreign-folder and running-config notes delete nothing. Partial failure keeps the config, tested with a read-only directory fixture.

<a id="ops-10"></a>
### OPS-10 Restart controller and model switch (server side)

- **Milestone:** M7
- **Rust target:** console-manage::restart
- **Platform:** platform-neutral
- **Risk:** medium. Process exit must not lose state. Rust has no os._exit trap, but the controller must flush explicitly and must not rely on Drop after std::process::exit.
- **Depends on:** OPS-01; OPS-05; named capability from console-core: request FIFO lock, close_for_restart for engine, vision and MCP, busy and reload state
- **Estimated size:** 450-600 lines of code; 500-600 lines of tests
- **Donor sources:** serve/server.py L3023-3043 (switch_model), L3155-3168 (_restart_into, _restart_for_models), L5635-5668 (swap on request); serve/models.py L32-33, L804-821; serve/update.py L19-21 (exit codes)

**Behaviors to reproduce**

- RestartController: supervised = the supervision env flag is set (renamed MAYA_RESTART_ON_UPDATE). Every 'restarts' field in API answers equals this flag.
- request_restart(config, why): writes the switch note {config: absolute path, port, why:'switch'|'settings', time} compact in the config directory, sets model_restart = {to, why, started}, and after 0.5 s takes the request FIFO (the request in flight finishes). Then it flushes the savings ledger, closes the engine, vision and MCP through a close-for-restart callback, and exits with code 76 through an injectable Exit trait so tests observe the code and do not die.
- Port change (from /api/port, owned by the API planner) uses the same path with no note, so the supervisor applies the config's saved port.
- switch_model(file) refuses the running model, a config that cannot start (missing()), and anything while a restart, reload or update is in progress (400). It writes own_defaults (OPS-05) and touches mtime. Unsupervised it answers restarts:false and exits nothing.
- POST /api/models/switch {file}: 202 {to, model, restarts}.
- Swap-on-request: /api/chat, /api/generate or /models/load naming another installed model triggers the switch and answers 503 with Retry-After: 30 and {error, loading:'NAME:latest'}. Unsupervised it answers 409.
- While model_restart is set, further switch, delete and settings calls fail fast.

**Parity tests**

test_models.Page.test_switch, test_switch_writes_the_models_own_defaults, test_refused; test_model_api.Api.test_swap_on_request (exit 76 observed through the injected Exit).

**Definition of done**

4 tests pass. A test asserts the FIFO is held, the in-flight fake request completes, the note content is correct and the injected exit receives 76. Unsupervised paths produce no note.

<a id="ops-11"></a>
### OPS-11 Supervisor process and launcher-facing contracts (pulsar-console supervise)

- **Milestone:** M7
- **Rust target:** console-launch::supervise (new crate) plus the server-side parent-pipe watcher in console-launch::parent_pipe
- **Platform:** platform-neutral
- **Risk:** medium. execv in tests is awkward. Structure it as decide_next(exit_code, note, flags) -> Action (pure, fully tested) plus a thin exec layer tested once through a subprocess.
- **Depends on:** OPS-01; OPS-02; OPS-10; named capability from console-http or core: graceful shutdown entry point
- **Estimated size:** 600-800 lines of code; 500-650 lines of tests
- **Donor sources:** maya.py L5235-5413 (server launch, --parent-pipe, exit 75/76 handling, switch note consumption, re-exec argv), L97-99; serve/server.py --parent-pipe handling (EOF stops the server, POSIX parent-PID check, Windows PeekNamedPipe) and stop-signal semantics; maya-launcher-setup contracts: server command line, run-config discovery, restart protocol, parent-pipe lifetime, stop signals

**Behaviors to reproduce**

- `pulsar-console supervise [--config F] [--port N] [--host H] [--api-key K] [--gpu L]`: without --config it picks the newest config by mtime. It spawns `pulsar-console serve --config F --port N [--host] [--api-key] [--gpu] --parent-pipe` with the supervision env flag set, stdin a pipe it never writes, and stdout and stderr inherited.
- Exit 76: read and delete the switch note. Honour it only when the config exists and the note is under 600 s old; then the config, port and backend come from the note. With no valid note, the config's saved port applies (the supervisor drops its own --port). Then restart.
- Exit 75: restart with the same flags (kept for contract completeness; nothing in this build emits 75, see OPS-22). Any other exit code becomes the supervisor's own exit code.
- Re-exec: POSIX execv of std::env::current_exe() with the original flags (port and config replaced from the note), keeping the same PID. Windows: spawn-and-wait loop (compiled but unverified).
- Server side: EOF on stdin or a changed parent PID (POSIX) triggers a graceful stop, as for Ctrl+C: the in-flight request wraps up (wrap timeout) and the engine gets QUIT (quit timeout). On stop the supervisor closes the pipe, waits 150 s, then kills.
- SIGTERM and SIGHUP are treated as Ctrl+C. A second SIGTERM is ignored and a second Ctrl+C ends at once (coordinated with the core planner's shutdown).
- The launcher's setup, compile, calibration, report and bench duties are not reproduced (deviation).

**Parity tests**

There is no serve/ test for the launcher side (launcher tests under MAYA/tools are outside serve/). New tests: a fake server child binary (test-only, in console-launch/tests) exits 76 with and without notes (fresh, stale at 601 s, missing config), exits 75 and exits 3. The suite asserts the supervisor's restart argv and exit propagation and checks parent-pipe EOF shutdown of a real `serve` with the fake engine.

**Definition of done**

Pure decision table covered for all exit-code and note combinations. The subprocess test proves an end-to-end switch: the server answers 202, exits 76, the supervisor restarts with the new config, and GET /api/models then shows running = the new file. Parent-pipe EOF stops the server within the wrap and quit budget.

<a id="ops-12"></a>
### OPS-12 Ollama-shaped model API: pure translation layer

- **Milestone:** M7
- **Rust target:** console-manage::model_api
- **Platform:** platform-neutral
- **Risk:** low. Depends on the OpenAI chunk model from console-core; agree on the chunk type, or define a local mirror converted at the boundary.
- **Depends on:** OPS-01; OPS-03
- **Estimated size:** 600-750 lines of code; 450-550 lines of tests
- **Donor sources:** serve/model_api.py (265 lines: names L38-54, parse_keep_alive L17-35, option and message mapping L100-183, Translator L190-265, listing shapes L56-96)

**Behaviors to reproduce**

- Public name = config file name without .json. A request may name a model with or without ':latest', '.json' or the leading prefix. Names containing / or \ or starting with '.' are rejected.
- parse_keep_alive: None or '' gives None. Numbers are seconds and a negative number means forever (-1.0). A string is a plain number, anything starting with '-' (forever), or NUMBER+UNIT parts with ms, s, m, h, d ('1h30m' = 5400). Booleans and anything else are errors.
- Options: temperature, top_p, top_k, min_p, seed, presence_penalty and frequency_penalty pass through. repeat_penalty becomes repetition_penalty, repeat_last_n becomes penalty_last_n, num_predict > 0 becomes max_tokens, stop passes through, and top-level temperature and top_p are fallbacks. ablate is read at top level or in options. think:false becomes chat_template_kwargs {enable_thinking:false}. format 'json' becomes json_object; a schema object becomes json_schema named 'answer'.
- Messages: images become image_url parts with the data:image/png;base64 prefix; tool_calls arguments are JSON-encoded; role tool with tool_name sets name; stream defaults to true.
- Translator: ignores prompt_progress chunks; accumulates usage, finish reason and tool-call fragments by index; emits one line per content or reasoning delta. Tool calls are emitted whole with parsed arguments (or {_raw}). done() adds done:true, done_reason ('length' stays, everything else becomes 'stop'), and integer-nanosecond total_duration, load_duration, prompt_eval_count, prompt_eval_duration, eval_count and eval_duration.
- Listing builders for /api/tags, /api/ps and /api/show: RFC 3339 'Z' timestamps from mtime; expires_at sentinel '0001-01-01T00:00:00Z'; details.format 'gguf' (pulsar-mlx reports 'safetensors'; deviation); digest ''; size_vram 0; capabilities ['completion','tools'].

**Parity tests**

test_model_api.Pure (4: keep_alive, requests_translate, translator, names), transliterated one-to-one.

**Definition of done**

The 4 Pure tests pass with every assertion carried over. The duration parser is fuzzed so it never panics. RFC 3339 formatting is hand-written or comes from the core time utility (no new time crate unless core already has one).

<a id="ops-13"></a>
### OPS-13 Model API routes and llama.cpp-style model management routes

- **Milestone:** M7
- **Rust target:** console-http::routes::model_api (handlers calling console-manage::model_api)
- **Platform:** platform-neutral
- **Risk:** medium. Coupled to core's generation pipeline; schedule after core's streaming chat is merged. The server-wide keep_alive side effect needs a core setter.
- **Depends on:** OPS-10; OPS-12; named capability from console-core: OpenAI chat pipeline with streamed chunk events and usage, engine lifecycle (unload, ensure_engine, busy, idle limit setter); named capability from console-http: router, NDJSON and SSE writers, client-address access, API-key check
- **Estimated size:** 800-1100 lines of code; 800-950 lines of tests
- **Donor sources:** serve/server.py L5465-5754 (gates, /api/version, tags, ps, show, chat, generate, preload and unload, keep_alive, swap), L5756-5778 (/models/sse), L5923-5942 (DELETE dispatch), L6167-6173

**Behaviors to reproduce**

- Every /api/* model-API route answers 404 {error: text} when model management is off. Pull, delete and swap also require an API key or a loopback client (127.0.0.1, ::1, ::ffff:127.0.0.1), else 403 'set an API key to download, delete or switch models over the network'.
- /api/version answers {version:'0.0.0-pulsar'} (deviation from '0.0.0-maya'). /api/tags, /api/ps (with loading:{model, since} or unloaded: name) and /api/show (404 "model 'X' not found"; maya block renamed, see deviations) behave as in the contract.
- /api/chat and /api/generate run through the core OpenAI chat pipeline. They stream application/x-ndjson by default and give a single object when stream:false. Another model gives 404 'try pulling it first' or the swap. Empty messages or prompt is a preload: done_reason 'load'. keep_alive 0 unloads (done_reason 'unload', 409 if busy). Any keep_alive value becomes the server-wide idle limit. Bad keep_alive or options give 400. Engine death gives 503 or an {error} line mid-stream.
- /models/load and /models/unload answer {model, status:{value}}. Load starts an unloaded engine (503 if it fails), triggers the swap for another installed model, and answers 404 {error:{message:'model not found'}} for an unknown one. Unload answers 409 when a request is running or waiting and 400 when the engine cannot unload.
- /models/sse: text/event-stream that sends a 'data: {object:'list', data:[{id, status:{value}}]}' frame plus a blank line every 5 s, with TCP_NODELAY set. Requires the API key when one is set.

**Parity tests**

test_model_api.Api (9: tags_ps_show, chat_and_generate, think_false, keep_alive, swap_on_request, api_key, off_when_model_management_is_off, plus the 2 delete tests via OPS-09); test_server.ModelManagement (5).

**Definition of done**

14 tests pass as black-box HTTP tests against the in-process fake engine. The NDJSON line order for tool calls matches MAYA. The SSE frame format is checked byte-for-byte.

<a id="ops-14"></a>
### OPS-14 Download catalog and manifest schema

- **Milestone:** M7
- **Rust target:** console-manage::catalog
- **Platform:** platform-neutral
- **Risk:** low. Cross-checks that MAYA made against launcher tables become manifest self-consistency checks (documented re-expression).
- **Depends on:** OPS-01; OPS-03; OPS-07
- **Estimated size:** 450-600 lines of code; 400-500 lines of tests
- **Donor sources:** serve/model_pull.py L20-190 (PROGRESS regex, OTHER tables, _offered, _note, catalog(), installed, sizes), L193-211 (setup_command); maya.py L129-779 (catalog tables); tools/ds4|mm3|qwen/download*.json (manifest form); docs/MODELS.md (licence notes)

**Behaviors to reproduce**

- The catalog is data: a JSON manifest under console/crates/console-manage/catalog/ (not a gitignored name). Each entry is {id, family, name, group:'primary'|'other', by, note, licence, format:'gguf'|'exl3'|'mlx-safetensors'|'synthetic', repo, revision (must be a 40-hex commit, never 'main'), files {path: [size, sha256 or [sha256...]]}, offer rules {backends, min_cc}, gated, also_gb}. The schema is validated at load.
- catalog() returns {id, family, name, group, by, note, installed, size_gb} in manifest order. Offer rules reproduce MAYA's _offered semantics as data: 'other' entries hidden on metal; DeepSeek, MiniMax and Qwen 'other' entries need max compute capability >= 70 unless the backend is hip or no GPU is readable; GLM-5.3 entries hidden on metal and below 70.
- installed is true when some config's (family, installer key) matches.
- setup_command(id, running_cfg) builds the fetch argv: [pulsar-console, fetch, --model ID, --download-model, --yes, --plain, --no-start] plus --models-dir from the running config's installer and --backend.
- The production manifest ships with zero real entries (D3 and the branding rule). The test manifest carries synthetic entries mirroring MAYA's groups and gating cases. Licence text is shown per entry.

**Parity tests**

test_model_api.OtherQuantsTest (8) (count corrected against the donor source) re-expressed against the manifest instead of importing the launcher (groups, names and notes, backends, installed, setup commands, pull takes an other id); test_glm_dsa_models.Catalog (2) re-expressed the same way.

**Definition of done**

10 re-expressed tests pass (count corrected against the donor source). The manifest validator rejects a revision that is not a commit, a missing sha256, a duplicate id or a gitignored path. The empty production catalog yields {models:[], pull:null, restarts} without error.

<a id="ops-15"></a>
### OPS-15 One-slot pull driver and download routes

- **Milestone:** M7
- **Rust target:** console-manage::pull and console-http::routes::pull
- **Platform:** platform-neutral
- **Risk:** medium. Byte-wise CR splitting and decimal-unit arithmetic must match exactly. Child reaping on cancel must not leave zombies.
- **Depends on:** OPS-14; named capability from console-http: NDJSON streaming, loopback check, model-management gate
- **Estimated size:** 600-800 lines of code; 600-700 lines of tests
- **Donor sources:** serve/model_pull.py L214-340 (Pull, Puller, progress parsing, snapshot, cancel, NDJSON events); serve/server.py L5508-5633 (routes, gates, detach and stream modes), L3114-3124 (command and test hook); serve/web/models.js L876-923 (dashboard polling)

**Behaviors to reproduce**

- Puller: one slot under a lock. Ids are lower-cased and ':latest' stripped. An unknown id raises a message naming GET /api/catalog. A second start while one is active gives 'ID is downloading; wait for it or cancel it' (409). The same id attaches to the running pull.
- The child is spawned with stdin closed and stderr merged into stdout. Output is read byte by byte and split on CR or LF. A line matching 'A / B GB( (P%))?( · R MB/s)?' sets state downloading with completed = A*1e9, total = B*1e9, bytes_per_s = R*1e6 and percent recomputed. Other lines go to a 40-line log. Exit 0 is success; otherwise error = the last log line or 'the setup stopped (code N)'. cancel sets cancelled and terminates the child.
- Snapshot = {model, state, completed, total, percent, bytes_per_s, error, started, message, log (last 12)}.
- GET /api/catalog answers {models, pull, restarts}. GET /api/pull/status answers {pull}. POST /api/pull {model|name, stream?, detach?}: detach answers 202 {pull}; stream:false blocks and answers 200 with the last event or 500 {error}; the default is NDJSON polled every 1.0 s with consecutive duplicates suppressed, then a final completed=total line, {status:'verifying sha256 digest'} and {status:'success'}, or a single {error} line. A client disconnect does not stop the download. POST /api/pull/cancel answers {cancelled}.
- The command source is injected through the constructor. In release builds it is always setup_command (OPS-14). Tests inject fake child commands; there is no environment hook (deviation).

**Parity tests**

test_model_api.Pull (4: catalog_and_pull_stream, pull_not_in_catalog_and_failure, one_download_at_a_time_and_cancel, progress_line), using a test-only fake setup binary that prints scripted progress lines, sleeps and exits with chosen codes.

**Definition of done**

4 tests pass. Cancel leaves no live child (checked by PID). The NDJSON sequence matches the contract for success, failure and cancel. Detached pulls survive client disconnect.

<a id="ops-16"></a>
### OPS-16 Fetch tool: PulsarMLX replacement for the launcher's download child

- **Milestone:** M7
- **Rust target:** console-launch::fetch (subcommand `pulsar-console fetch`)
- **Platform:** platform-neutral
- **Risk:** high. Network and filesystem heavy, and the token-handling rules are security-relevant. Tests must never reach the internet: the base URL override exists only under cfg(test) or a test feature. The reviewer should grep for token leakage in argv and logs.
- **Depends on:** OPS-01; OPS-14
- **Estimated size:** 1000-1400 lines of code; 800-1000 lines of tests
- **Donor sources:** maya.py L2813-2843 (sha256 check, verified ledger), L2985-3210 (curl driver, concurrency, stall and retry rules, disk-space rule, gated token header file), L3895-4051 (writing the run config after download); setup.py L504-574 (Range downloader, for reference only); docs/MODELS.md

**Behaviors to reproduce**

- Arguments: --model ID [--models-dir DIR] [--backend B] --download-model --yes --plain --no-start (the exact argv setup_command builds). Exit 0 only when every file is downloaded and verified and the run config is written.
- Transfer through system curl (no TLS crate in the tree): curl -sS -L --fail -C - --speed-limit 1024 --speed-time 60 --connect-timeout 30 -o DEST URL, at most 4 at once. Each file is re-run with back-off min(60, 5*stuck) s and the tool gives up after 30 consecutive runs without progress. A file larger than its manifest size is deleted and restarted. URL template {base}/{repo}/resolve/{revision}/{path} with base fixed to https://huggingface.co in release builds.
- Free space must be at least remaining + also_gb + 3 GB, checked with statvfs on the target folder and on any disk reached through symlinked shards. A rotational disk only warns (no spinning disks on Apple Silicon: the check reports not-rotational).
- After download each file's size and sha256 (64 MiB reads) must equal an accepted value; a mismatch deletes the file and fails. Verified files are recorded in MODEL_FOLDER/.pulsar-verified.json {name:{size, mtime_ns}} and not re-hashed while size and mtime are unchanged.
- Gated repos: the token comes from HF_TOKEN, HUGGING_FACE_HUB_TOKEN or <HF_HOME or ~/.cache/huggingface>/token. It is passed only as -H @FILE (mode 0600, removed afterwards), requires curl >= 7.58 and never appears on a command line or in logs.
- Prints the progress line 'A / B GB (P%) · R MB/s[ · H h MM min left] · N files at once' with CR rewrites and decimal units.
- Writes the run config: synthetic entries produce backend 'synthetic'; mlx-safetensors entries produce a pulsar-mlx config with backend 'mlx' (listed, not startable in this increment); gguf and exl3 entries produce line-protocol-profile configs (test fixtures only).

**Parity tests**

There are no serve/ tests (the behaviour lived in the launcher, whose tests are outside serve/). New tests run against a loopback hyper fixture server (test-only) that serves files and supports Range, can stall, truncate, oversize or serve a wrong hash, and checks bearer-token handling. They cover the disk-space rule with an injected statvfs and the verified-ledger reuse.

**Definition of done**

Resume, stall abort, oversize restart, hash mismatch deletion, ledger reuse, disk-space refusal and gated-token header-file tests all pass on macOS against the loopback server. The emitted progress lines parse with the OPS-15 parser. An end-to-end test runs pull → fetch → a new config appears in GET /api/models with the synthetic catalog.

<a id="ops-17"></a>
### OPS-17 Telemetry sampler core and the /metrics hardware fields

- **Milestone:** M4
- **Rust target:** console-host::sampler
- **Platform:** platform-neutral
- **Risk:** low. Needs an injectable clock for deterministic pacing tests; avoid real sleeps over 0.1 s in tests.
- **Depends on:** named capability from console-core: busy() and the live token-rate extras
- **Estimated size:** 500-700 lines of code; 450-550 lines of tests
- **Donor sources:** serve/telemetry.py L33-35, L870-1116 (static facts, sample, aggregation, history ring, pacing, snapshot); serve/server.py L3219-3237, L3313-3374 (/metrics assembly of hardware, hardware_static, history, storage)

**Behaviors to reproduce**

- The GpuReader, CpuReader, MemReader and DiskReader traits produce Option values; any failure is None and a failing sample is an empty map. Telemetry never stops the server (it runs in its own thread with panics caught).
- Sample keys: the gpu_* keys (absent when no card is readable), cpu %, ram_used = total - available, ram_total in bytes, disk_read_mb and disk_write_mb in MiB/s from counter deltas, plus extras supplied by core: tok_s, tok_s_mean, prefill_tok_s_mean.
- Multi-GPU aggregation: memory, power, power limit and PCIe traffic are summed, utilisation averaged, temperature takes the maximum; a 'gpus' list carries per-card values and 'vram' carries per-card and per-process bytes for the GPU map.
- History: rings of 60 for gpu_util, gpu_mem_used, gpu_temp, gpu_power, gpu_pcie_rx_mb, cpu, ram_used, disk_read_mb, tok_s and prefill_tok_s_mean, with floats rounded to 2 decimals.
- Pacing: 1 s normally. When busy() is false and nobody has read for 15 s, every 3 s. snapshot() or touch() wakes it at once through a Condvar. A reading taken after a long pause is appended once per elapsed second, at most 4 times.
- static = {gpu_name (joined ' + '), gpu_count, cpu_name, cores, threads, psutil (reported true when native readers are active; see deviations)}. storage = {path, free, total} for the models folder's disk. Reader selection: NVML, then AMD sysfs, then Windows, then Apple, in MAYA order with Apple added.

**Parity tests**

test_telemetry.Sampler (5 of 6: sample_through_the_reader, without_nvml, idle pacing, series a second apart, this_machine as a shape-only check) (count corrected against the donor source), using a fake GpuReader and an injectable clock.

**Definition of done**

5 tests pass deterministically, with 50 repeated runs in CI without flakes. The /metrics hardware and history JSON shape is checked against a contract fixture with nulls in every position.

<a id="ops-18"></a>
### OPS-18 Apple Silicon host reader

- **Milestone:** M4
- **Rust target:** console-host::apple (cfg(target_os = "macos"); pure parsers platform-neutral)
- **Platform:** hardware-or-os-specific
- **Risk:** medium. AGXAccelerator PerformanceStatistics keys are undocumented and may change between macOS versions, so every value degrades to null. FFI needs libc (mach) and core-foundation-sys plus io-kit-sys, or hand-written extern blocks; prefer hand-written externs if the reviewer accepts the unsafe surface.
- **Depends on:** OPS-17
- **Estimated size:** 700-1000 lines of code; 400-500 lines of tests
- **Donor sources:** serve/telemetry.py L871-889 (macOS cpu_name via sysctl), L963-988 (CPU, RAM and disk via psutil); serve/server.py L85-119 (mac_free_bytes via vm_stat and the memory-settle wait after an engine stop); maya.py L873-878 (0.85 x RAM GPU budget, informational)

**Behaviors to reproduce**

- cpu % from host_processor_info tick deltas. cpu_name from sysctl machdep.cpu.brand_string; cores and threads from hw.physicalcpu and hw.logicalcpu.
- ram_total = hw.memsize. ram_used = total - available, where available = (free + inactive + purgeable + speculative) pages * page size from host_statistics64 (the same formula as MAYA's vm_stat path). free_unified_memory() and wait_for_memory_settle(step 1 GiB per 0.5 s, max 60 s) are exported for engine supervision.
- Disk read and write MiB/s from the IOKit IOBlockStorageDriver Statistics dictionaries (bytes read and written), summed.
- GPU: gpu_name from the IORegistry AGXAccelerator 'model' property (fallback: CPU brand string), gpu_count 1, gpu_util from PerformanceStatistics 'Device Utilization %', gpu_mem_used from 'In use system memory', gpu_mem_total = hw.memsize (unified). Any missing key gives null. gpu_temp, gpu_power and PCIe stay null or absent (no private IOReport or SMC access, no powermetrics).
- hardware_static adds unified_memory:true (additive).
- The IORegistry and IOKit dictionaries are converted to a plain Rust map, and the parsers are tested with recorded fixture maps; a live test on the macOS runner asserts shape only.

**Parity tests**

There is no MAYA equivalent (MAYA has no Apple reader). test_telemetry.Sampler.test_this_machine is re-expressed as a live shape test. New fixture tests cover the vm_statistics64, processor-tick and PerformanceStatistics parsers.

**Definition of done**

Fixture parsers pass on every platform. On the macOS CI runner a live sample has non-null cpu, ram_used, ram_total and gpu_name, and nulls are tolerated elsewhere. Unsafe blocks are confined to one module with SAFETY comments. Labelled 'measured on the CI runner only' in the docs.

<a id="ops-19"></a>
### OPS-19 NVIDIA reader: NVML in a crash-isolated child process

- **Milestone:** M9
- **Rust target:** console-host::nvidia (child entry: hidden subcommand `pulsar-console --nvml-child [--skip a,b]`)
- **Platform:** hardware-or-os-specific
- **Risk:** medium. The real FFI is unverifiable on a Mac and is labelled 'unverified on NVIDIA hardware'. Hang tests need shortened timeouts injected through the constructor. New dependency: libloading.
- **Depends on:** OPS-17
- **Estimated size:** 900-1200 lines of code; 600-750 lines of tests
- **Donor sources:** serve/telemetry.py L38-442 (NVML FFI, child main, the '@name' and '~' markers, parent _Reader with timeouts, skip list and restart policy), L823-867, L1119-1120; serve/server.py L120-135 (gpu_pids used after an engine stop)

**Behaviors to reproduce**

- Wire protocol, kept exactly: the parent sends one JSON line {op:'info'|'read'|'pids', idx}. The child prints '@FunctionName' before each NVML call, '~' after it, then one JSON answer line: {ok:false} when NVML is absent; info gives {ok, gpus:[{index, ok, pci, name}]}; read gives {ok, gpus:[{util, mem_used, mem_total, temp, power, power_limit, pcie_gen, pcie_gen_max, pcie_width, pcie_rx_mb, pcie_tx_mb, procs} | null]}; pids gives {ok, pids}.
- Units: power and power limit in W (mW / 1000), PCIe throughput in MB/s (KB/s / 1024), temperature in C, memory in bytes; process memory is null when NVML reports 'not available'.
- Parent: per-call timeout 20 s (120 s for nvmlInit*). A crash or timeout is attributed to the open call, the child is restarted with that call skipped (its reading becomes null), the request is retried once, and the reader gives up after 5 crashes.
- The NvmlApi trait has two implementations: a libloading binding of libnvidia-ml.so.1 or nvml.dll (Windows path under ProgramFiles) that compiles on macOS and reports absent there, and the test fake.
- A test-only fake child binary links the same child_main with FakeNvml driven by a JSON spec {crash:[...], hang:[...], slow:{...}, die, absent}. Crash uses abort, as MAYA's faulthandler SIGSEGV does.
- gpu_pids() is exported for engine supervision (waiting until no GPU lists the old process).

**Parity tests**

test_telemetry.ReaderProcess (8: readings, crashing call left out, hanging call left out, slow init and read waited for, crash in the process list falls back, crash in init turns readings off, no NVML, reader that keeps dying given up), Sampler.test_sample_through_the_reader and test_gpu_pids. All run on macOS through the fake child, as MAYA runs them without a GPU.

**Definition of done**

10 tests pass on macOS. Timeouts are injectable and tests finish in under 20 s total. `cargo check --target x86_64-unknown-linux-gnu` and `--target x86_64-pc-windows-msvc` succeed in CI for console-host (check only).

<a id="ops-20"></a>
### OPS-20 AMD readers: Linux amdgpu sysfs and Windows DXGI/PDH/D3DKMT

- **Milestone:** M9
- **Rust target:** console-host::amd::{sysfs, windows}
- **Platform:** hardware-or-os-specific
- **Risk:** medium. The Windows FFI cannot run here, so only the cross-target cargo check proves it compiles. The fixture trees must reproduce MAYA's test layout exactly.
- **Depends on:** OPS-17; OPS-19
- **Estimated size:** 800-1100 lines of code; 600-700 lines of tests
- **Donor sources:** serve/telemetry.py L445-820 (KFD topology to render node, gpu_busy_percent, mem_info_vram_*, hwmon, PCIe bottleneck over bridge hops, DXGI adapters, PDH GPU engine counters, D3DKMT, hipInfo.exe bus matching, auto-detection order)

**Behaviors to reproduce**

- The sysfs reader takes a configurable root (default /sys). It maps the KFD topology to the render node; reads gpu_busy_percent, mem_info_vram_used and mem_info_vram_total, and hwmon temp1_input and power1_average (or input) and power1_cap; and walks every PCIe bridge hop. It reports the slowest hop only when every hop is readable, plus pcie_path 'read/total' and pcie_own_gen.
- The Windows reader uses a WinGpuApi trait (adapters with LUID, name, dedicated memory and bus; PDH counter values) with the pure logic separated out. Utilisation is the busiest engine's summed share. There is no temperature, power or PCIe. HIP device numbers are matched to adapters through bus numbers parsed from hipInfo.exe output; without adapter buses DXGI order is kept.
- The real Windows binding is compiled under cfg(windows) with hand-written extern "system" declarations or windows-sys (target-gated) and is unverified.
- Auto-detection: when NVML finds no card, sysfs is tried and then Windows. Backend hip never asks NVML. An NVIDIA card keeps NVML.

**Parity tests**

test_telemetry.AmdSysfs (3: hip_backend, auto_detected_when_nvml_has_no_card, nvidia_card_keeps_nvml) on fixture sysfs trees built in tempdirs. test_telemetry.AmdWindows (6) use a FakePdh and fake adapters plus hipInfo text fixtures.

**Definition of done**

9 tests pass on macOS. A Windows cross-target cargo check passes. Docs label both readers 'fixture-verified, unverified on AMD hardware'.

<a id="ops-21"></a>
### OPS-21 Savings ledger and /api/savings

- **Milestone:** M7
- **Rust target:** console-manage::savings
- **Platform:** platform-neutral
- **Risk:** low. Uses regex-lite for the four case-insensitive patterns, or hand-written matchers verified against the same test strings.
- **Depends on:** OPS-01; named capability from console-core: finished-request hook carrying prompt token count, engine-reported reused prefix and generated count
- **Estimated size:** 450-600 lines of code; 450-550 lines of tests
- **Donor sources:** serve/savings.py (244 lines); serve/server.py L4729, L4755-4756 (finished-request hook), L7346, L6069-6072, L6212-6240 (routes), /metrics savings summary

**Behaviors to reproduce**

- add(prompt_tokens, reused, output): reused is clamped to 0..prompt_tokens and fresh = prompt - reused. A request lands in band 'peak' only when the running model's price has a peak factor and the finish time is Monday to Friday 01:00-04:00 or 06:00-10:00 UTC; otherwise 'base'.
- The built-in reference table is kept verbatim with PRICES_AS_OF '2026-10' (DeepSeek, GLM-5.3-Flash, GLM-5.3 and MiniMax patterns and prices), matched case-insensitively. Unknown models are counted in tokens only.
- cost = sum over bands of factor * (input*p_in + cached*p_cached + output*p_out) / 1e6. Report values are rounded to 6 decimals.
- Custom prices: input, cached and output are numbers (not booleans) from 0 to 1000. peak 1..10 only where the built-in has one. api is trimmed to 40 characters. The model name is 1..200 characters. null removes the override, and totals are recomputed.
- Ledger file token-savings.json beside the config, or the path named by the renamed SAVINGS_PATH variable (off, none or 0 keeps no file). The whole document is rewritten via tmp and rename after every add. A write failure is logged once and counting continues in memory. A file that does not parse is replaced.
- summary() for /metrics = {usd, start_usd, priced}. GET /api/savings is the full report, or {usd:null, models:[]} without a config. POST reset answers 200 with the report (400 'nothing is counted here' without a ledger). POST prices answers 200, or 400 invalid_request_error, or 403 for a foreign Origin.
- flush() is called by the restart controller before exit.

**Parity tests**

test_savings.Prices (3), Counting (4), LedgerPath (3), Page (3), with a fixed-clock injection for peak detection.

**Definition of done**

13 tests pass. The ledger JSON matches Python json.dumps(indent=1) through OPS-01. Peak detection is tested at band edges (00:59, 01:00, 03:59, 04:00, Saturday).

<a id="ops-22"></a>
### OPS-22 Update contract: opt-in, check-only release notifier

- **Milestone:** M7
- **Rust target:** console-manage::update
- **Platform:** platform-neutral
- **Risk:** low. The deliberate behaviour change needs owner sign-off (see deviations).
- **Depends on:** OPS-01; OPS-16
- **Estimated size:** 350-450 lines of code; 350-400 lines of tests
- **Donor sources:** serve/update.py (176 lines); serve/server.py L6027-6036 (/health status), L6073-6077, L6256-6259, L6407-6417; serve/web/server.js L340-398 (dashboard use)

**Behaviors to reproduce**

- GET /api/update keeps the exact shape {current, enabled, latest, newer, checked, error, can_update:false, blocker, state:null, by_hand}. current is the console package version.
- enabled is false by default. It is turned on only by config update_check:true or the renamed UPDATE_CHECK=1. When disabled, no network request is ever made (test equivalent of MAYA_UPDATE_CHECK=0).
- When enabled: GET <fixed PulsarMLX releases/latest URL> with Accept: application/vnd.github+json and a generic User-Agent 'pulsar-console/VERSION', 8 s timeout, through system curl (shared helper with OPS-16). The repository is a compile-time constant, never derived from a git remote. The tag must match ^v?N.N.N$. Results are cached 6 h, a failure retries after 10 min, and ?force=1 bypasses the cache. summary = the first non-heading line with * _ ` removed, at most 300 characters. newer is a numeric tuple comparison.
- blocker is always set when newer is true: "this build can't update itself: update by hand (git pull and rebuild, see by_hand)". POST /api/update always answers 400 invalid_request_error with 'this is the latest version' or the blocker text. No git command, no fetched code and no exit 75 (deviation).
- /health never reports 'updating' in this build (owned by the API planner; documented).

**Parity tests**

test_update.Pieces (5: versions, summary, newer, unreachable and retry pause, check off) against a fake release fetcher injected through a trait. test_update.Updating (5) is re-expressed as five 'always blocked' assertions: an unchanged checkout, local changes, unsupervised, not a checkout and diverged each give 400 with no git invocation (asserted through a command-spawn spy).

**Definition of done**

10 tests pass. A test proves that with default settings GET /api/update performs zero process spawns and zero network calls. The dashboard's About page renders with the disabled shape (checked by the web planner's smoke test).

<a id="ops-23"></a>
### OPS-23 Ops route integration, guards conformance and contract documents

- **Milestone:** M7
- **Rust target:** console-http::routes::ops (wiring) and specs/022-*/contracts/ops-*.md
- **Platform:** platform-neutral
- **Risk:** medium. Guard order differences show up as different status codes; the matrix catches them.
- **Depends on:** OPS-06; OPS-07; OPS-09; OPS-10; OPS-13; OPS-15; OPS-17; OPS-21; OPS-22; named capability from console-http: router, guard middleware
- **Estimated size:** 400-600 lines of code; 900-1100 lines of tests
- **Donor sources:** serve/server.py L5507-5520, L6141-6164, L6327-6338 (own-page guards, loopback gates, error conventions), the dispatch lines for every route in this subsystem; serve/web/app.js L116-117 (startup calls)

**Behaviors to reproduce**

- Every route in this subsystem is registered with MAYA's method, path, authentication and guard order: API key (401 authentication_error), then foreign Origin (403 permission_error), then Content-Type must start with application/json (415 'send application/json'), then body must be a JSON object (400).
- Error-body conventions per family: dashboard {error:{type, message}}, model API {error:'text'}, llama.cpp-style {error:{message}}.
- A black-box startup suite issues the dashboard's startup calls (GET /api/turbo, /api/update, /metrics, /api/models, /api/catalog, /api/savings) against a server with no config, a synthetic config and a line-protocol fake config, and checks the documented shapes, including the empty ones.
- Contract documents for every route, file and env var in this subsystem, written as the Phase 2 UI-to-server contract: JSON shapes, error codes and the Rust type each maps to.

**Parity tests**

test_savings.Page.test_reset_only_from_the_page (403 path), test_server.ModelManagement.test_the_api_key_guards_them_and_status, plus new matrix tests: every mutating ops route times {no key, wrong key, foreign Origin, wrong content type, non-object body}.

**Definition of done**

The guard matrix passes for all routes. The startup suite passes in all three configurations. The contract docs exist and a test asserts every registered ops route appears in them.
