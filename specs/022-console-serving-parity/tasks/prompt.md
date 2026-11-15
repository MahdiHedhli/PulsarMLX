# Task detail: Prompt construction, tokenizer, output parsers, thinking budget and loop guards

Feature 022, PulsarMLX Console. This file gives the full specification of each work package
with the prefix `PRM-`. The task list, the milestone order and the binding cross-cutting
decisions are in [`../tasks.md`](../tasks.md); **a binding decision or a reconciliation
there overrides any conflicting sentence in this file**.

Provenance: rendered without paraphrase from the planning records of 2026-11-14 (one planning
agent per subsystem, reading the pinned donor source). Path shorthand: `MAYA` is the pinned
project-maya checkout (commit `7e68a30f`), `ORIGIN` is this repository at `main` when the plan
was written. Sizes are estimates. Donor names such as `MAYA_*` variables describe the donor;
the product names are in [`../contracts/naming.md`](../contracts/naming.md).

## Subsystem summary

PRM is the text half of project-maya's serving stack. It covers serve/frontend.py, ds41_encoding.py, glm_dsa_template.py and loop_guard.py, plus the prompt and output parts of server.py (Service.prepare, render_ids, chat_prompt, tokenize/detokenize/count_tokens, run, _sliced's soft-close and loop-guard hooks, the stop sets, and openai_chunks/openai_collect/anthropic_events/anthropic_collect/json_from_text). It also covers tools/strata_tokenizer.py with ByteTokenizer and the Detokenizer, the chat templates and the golden fixtures. Full parity means the following, given the same request JSON, pack tokenizer directory, template file, run config and environment. The Rust code must build the same template message form and kwargs. It must render byte-identical prompt text, tokenize it to identical ids, and protect quoted special literals the same way. Fed the same token ids by a fake engine, it must emit the same reasoning/content/tool_start/tool_args/tool_call events at any chunking, and map them to the same OpenAI and Anthropic shapes, finish reasons and stop_sequence. It must apply the same stops, thinking budget, forced-call prefills, JSON-mode handling, in-answer loop guard and cross-turn loop guard, asking the generation loop for the same restarts (same appended ids, same sampling overrides). Decision on Jinja: render with the minijinja crate, configured as a transformers-style ImmutableSandboxedEnvironment (trim_blocks, lstrip_blocks, loop controls, preserve_order). Our own code supplies the parts minijinja does not provide with Python semantics: tojson as Python json.dumps, Python str() output formatting, the string/trim filters, a pycompat method callback (items/keys/values/get/split/strip/startswith/endswith/replace and friends), raise_exception, and, if needed, unique and the boolean/true/false tests. I inventoried every feature the 10 templates use (macros defined inside if blocks, a recursive macro, namespace lists, list+list, dict literals, sort(attribute, case_sensitive), unique(case_sensitive), range, break, x.0 subscripts, [::-1], loop.previtem/nextitem, for-if filters). Each one becomes a mandatory conformance case in a spike that runs first; the one unverified parser feature (x.0) has a deterministic source-rewrite fallback. Decision on the tokenizer: reimplement strata_tokenizer in a new console crate rather than reuse crates/tokenizer, which inherits root-workspace fields, lacks special-literal and plain-span encoding, and reads a different input format. Use fancy-regex for the four transcribed pre-tokenizers, plus rank-ordered BPE, ignore_merges, NFC and the type-3/type-4 literal rules. Decision on vendor-licensed templates (Qwen, GLM-5.3, MiniMax): they are never committed. At run time they come from the pack or an explicit path. Tests that need them read a pinned project-maya checkout through a sha256-verified provider; CI fetches that checkout at 7e68a30f, and everything else runs against clean-room synthetic templates written in the repo. Every package is pure, platform-neutral logic driven by synthetic tokenizers and fake engines. Real-pack tokenization and real-model behaviour stay labelled unverified.

## Build order proposed by the planner

- PRM-01 (foundation; first, alone)
- PRM-02, PRM-06, PRM-07 and PRM-09 in parallel once PRM-01 lands (testkit, normalization, DeepSeek encoder and output parser do not depend on each other; PRM-06 uses PRM-05's effort functions, so either start PRM-05's effort module first inside PRM-06's session or stub it)
- PRM-03 and PRM-04 in parallel once PRM-02 lands (Jinja spike-first, tokenizer)
- PRM-05 after PRM-03 and PRM-07; PRM-10 after PRM-09 and PRM-07 (these two can run in parallel)
- PRM-08 after PRM-04, PRM-05 and PRM-06
- PRM-15's pure functions (texts, repeat, collapse, units) can start right after PRM-05 and PRM-08; its run-time wiring lands with PRM-12
- PRM-11 after PRM-08 and PRM-07 (with PRM-15 stubs behind a trait if PRM-15 is not done)
- PRM-12 after PRM-09, PRM-10, PRM-04 and PRM-11, and only once the Directive contract with console-core is agreed
- PRM-13 and PRM-14 in parallel after PRM-12; PRM-16 can run any time after PRM-09 and PRM-12 (parallel with PRM-13/PRM-14)
- PRM-15 finalized (keep-going and blocked-call branches) after PRM-12
- PRM-17 last, after console-http chat routes, the console-core loop and the console-engine fakes exist

## Work packages

<a id="prm-01"></a>
### PRM-01 Python-compatible JSON and string semantics foundation

- **Milestone:** merged into API-01; kept here as input for the owning package
- **Rust target:** new crate console/crates/console-pyjson (lib), module layout: dumps.rs, loads.rs, float_repr.rs, pystr.rs, ids.rs
- **Platform:** platform-neutral
- **Risk:** medium. Every tool-bearing prompt depends on this, so a wrong separator or float format silently breaks all goldens. arbitrary_precision changes serde_json Number behaviour across the whole console workspace (feature unification), so the lead must approve it workspace-wide. Float repr edge cases (5e-324, 1e16, 0.1+0.2) need explicit cases.
- **Depends on:** nothing
- **Estimated size:** 600-800 lines of code; 400-600 lines of tests
- **New dependencies:** serde =1.0.229 (derive); serde_json =1.0.151 with features preserve_order, arbitrary_precision; uuid (exact pin; features v4)
- **Donor sources:** Implicit throughout serve/frontend.py (json.dumps/json.loads at 599-797, 853-936, 958-1060, 1221-1261), serve/ds41_encoding.py (to_json helpers), serve/loop_guard.py args_key 314-326 (sort_keys, default=str), serve/response_schema.py json_instruction 14-21, serve/server.py json_from_text 4909-4930; Python json module semantics (separators ', ' ': ', ensure_ascii, allow_nan, float repr), str.strip/split/isspace, code-point slicing.

**Behaviors to reproduce**

- dumps(value, ensure_ascii, indent, separators, sort_keys, allow_nan=true) reproduces CPython json.dumps byte for byte: default separators ', ' and ': ' (',' and ': ' when indent is set), insertion-ordered keys unless sort_keys, ensure_ascii=true escapes every non-ASCII code point as \uXXXX using surrogate pairs above U+FFFF, the short escapes \n \r \t \b \f \" \\, other control chars as \u00XX, no HTML escaping, NaN/Infinity/-Infinity written bare.
- Python float repr: shortest round-trip digits; scientific notation when the exponent is below -4 or at least 16, written as 1e+16 / 1e-05; integral floats keep '.0'; -0.0 preserved; integers of any size are emitted exactly.
- loads accepts what CPython json.loads accepts: NaN, Infinity, -Infinity, integers of any size, duplicate keys (last one wins, first position kept), and rejects trailing garbage. Number classification is int vs float as in Python ('1.0' is float, '10' is int).
- raw_decode(text, start) for json_from_text (first object or array in a text).
- Order-preserving Value: serde_json with preserve_order and arbitrary_precision, plus helpers that normalize arbitrary-precision numbers into Python's int/float semantics before dumping.
- pystr: code-point-indexed slicing and offset conversion (char index to and from byte index); Python str.isspace (including U+001C..U+001F and U+0085), strip/lstrip/rstrip with and without an argument, split() with no separator and split(sep, maxsplit), str.capitalize, isdigit for think_stop_tables.
- Python truthiness helper for JSON values (empty string/list/object, 0, 0.0, null, false are falsy).
- ids: hex24() = the first 24 lowercase hex characters of a v4 UUID; call_id() = 'call_' + hex24, plus chatcmpl-/msg_ prefixes for PRM-16.

**Parity tests**

No dedicated Maya test file. The behaviour is exercised indirectly by serve/chat_golden.json (tool schemas through tojson), serve/fixtures/deepseek_v41/test_output_1.txt (json.dumps of tool schemas), test_tools.py GlmCalls (streamed argument JSON) and test_loop_guard.py ToolRepeat (args_key). New Rust unit tests carry a table of at least 120 input/expected pairs whose expected strings come from Python's documented algorithm (repr rules, escape table). The test files cite the CPython rules, and optional owner-generated Python outputs can extend the table.

**Definition of done**

console-pyjson builds standalone with the pinned toolchain. The table-driven tests cover every escape class, float exponent boundary, big integers, NaN/Infinity, indent/separators/sort_keys combinations, surrogate pairs and the Python whitespace set, and all pass. A reviewer can check any row against CPython's documented rules. No other crate's behaviour changes except through the shared serde_json features, which are recorded in console/Cargo.toml with a comment.

<a id="prm-02"></a>
### PRM-02 Parity test kit: vendor-template provider, synthetic templates, MT19937 and synthetic BPE trainer

- **Milestone:** M2
- **Rust target:** new dev-only crate console/crates/console-testkit (publish=false), plus console/crates/console-prompt/testdata/ and console/.gitattributes
- **Platform:** platform-neutral
- **Risk:** medium. Licence hygiene is the point of this package. The reviewer must check that no vendor template text, and no render of one, is committed (chat_golden.json contains Qwen template text in its renders, so it is loaded from the vendor checkout and not vendored). The MT19937 port must match CPython's seeding exactly or the loop-guard corpora differ.
- **Depends on:** PRM-01
- **Estimated size:** 500-700 (plus about 250 lines of synthetic Jinja) lines of code; 250-350 lines of tests
- **New dependencies:** sha2 (exact pin, dev)
- **Donor sources:** serve/test_prompt_memo.py 37-130 (MODELS table, CORPUS, train_merges, make_tokenizer, histories, fuzz_histories); serve/test_render_other_models.py 1-113; data/glm-dsa/templates/README.md (sha256 table); serve/fixtures/minimax_m31/README.md; serve/fixtures/deepseek_v41/README.md; serve/fixtures/glm_tool_images.jinja; .gitattributes 1-25; Python random.Random (seed, random, randint, randrange, choice, choices, shuffle) as used by test_loop_guard.py and test_tools.py chunking tests.

**Behaviors to reproduce**

- VendorTemplates provider: resolves logical names (qwen38.chat_template, glm53.official, glm53.gguf_ud_iq2_m, glm52, glm53_flash.maya_swap, glm.tools_flash, mm3.maya, minimax_m31.official, ds4.legacy_export, chat_golden.json) to files under a pinned project-maya checkout named by env CONSOLE_VENDOR_SRC. It verifies every file against a committed sha256 manifest (the six hashes already recorded in the reader notes, plus the rest computed when the manifest is created) and refuses on mismatch.
- Tests that need a vendor file call require_vendor!(name). Without CONSOLE_VENDOR_SRC they are reported as skipped with a clear message, and a CI mode (CONSOLE_REQUIRE_VENDOR=1) turns a skip into a failure.
- Clean-room synthetic templates committed under console/crates/console-prompt/templates/synthetic/, written from the format descriptions and not copied from vendor files: chatml-think (Qwen-shaped: <|im_start|> turns, <tools> with tool|tojson lines, function/parameter calls, think block, enable_thinking), glm-arg (GLM-shaped: [gMASK]<sop>, Reasoning Effort line driven by reasoning_effort in ['low', 'high'], arg_key/arg_value calls, <|observation|>), glm-dialect-52 (== 'high' style plus enable_thinking), minimax-ns (]~b] turns with the ]<]minimax[>[ namespace and <mm:think>), dsml-probe (contains ｜DSML｜ so DeepSeek detection fires), forced-thinking (set enable_thinking = true, CYBER-FROST-style) and media variants. Each carries a header saying it is original to PulsarMLX, MIT.
- Maya's 22-line serve/fixtures/glm_tool_images.jinja (Maya-authored, MIT) is vendored with provenance under testdata/maya/.
- The DeepSeek fixture pairs (MIT, DeepSeek) are vendored byte for byte under testdata/deepseek_v41/ with LICENSE text and README provenance. serve/fixtures/render_ids_other_models.json (Maya MIT, hashes only) is vendored under testdata/maya/.
- console/.gitattributes marks crates/console-prompt/testdata/** -text so byte comparisons survive checkout.
- Mt19937 reproduces CPython random.Random(seed) for integer seeds (init_by_array), random(), getrandbits(k), randbelow-based randint/randrange, choice, choices (floor(random()*n), and the cum_weights path where used) and shuffle, checked against published MT19937 reference vectors.
- train_merges and make_tokenizer port test_prompt_memo's deterministic synthetic BPE trainer (Counter max with the (count, pair) tie-break) and the MODELS table of literals per family, so the render_ids fixture can be reproduced.
- Chunking helpers: split a text at sizes 1, 2, 3, 5, 7, 11 and 64, and at seeded random sizes 1..7 using Mt19937 so the random cases match Maya's own.

**Parity tests**

Defines the harness that later packages use. Its own tests: sha256 manifest verification against the scratch clone (vendor-gated); MT19937 reference vectors (first outputs for seed 5489, plus random() values); train_merges, which must produce merges whose downstream use reproduces serve/fixtures/render_ids_other_models.json, verified end to end in PRM-08.

**Definition of done**

With CONSOLE_VENDOR_SRC pointing at the 7e68a30f clone, every manifest entry verifies. Without it, vendor-gated tests skip, and fail under CONSOLE_REQUIRE_VENDOR=1. The MT19937 vectors pass. git check-attr shows -text on testdata. A grep of console/ for distinctive vendor template phrases (for example 'Reasoning Effort: Max' outside synthetic headers, or the MiniMax identity sentence) finds nothing. NOTICE entries for the DeepSeek fixtures and the Maya fixtures are drafted.

<a id="prm-03"></a>
### PRM-03 Jinja runtime with transformers/Jinja2 sandbox semantics on minijinja

- **Milestone:** M2
- **Rust target:** console-prompt::jinja (console/crates/console-prompt/src/jinja/{env.rs,filters.rs,pycompat.rs,format.rs,rewrite.rs})
- **Platform:** platform-neutral
- **Risk:** high. This is the main technical risk of the subsystem. The minijinja features I believe exist (previtem/nextitem, recursive macros, unique with case_sensitive, boolean/true/false tests, the x.0 parser path, lstrip_blocks edge cases) are recollection, not verified, which is why this package starts with a spike that fixes the exact pinned minijinja version. Only Qwen has committed text goldens. GLM and MiniMax parity rests on the render_ids hash fixture (PRM-08), the MiniMax differential test and any goldens the owner chooses to generate (see open questions).
- **Depends on:** PRM-01; PRM-02
- **Estimated size:** 600-850 lines of code; 600-800 lines of tests
- **New dependencies:** minijinja (exact pin chosen in the spike; features: builtins, macros, loop_controls, preserve_order, serde; no minijinja-contrib)
- **Donor sources:** serve/frontend.py 37-51 (ImmutableSandboxedEnvironment, trim_blocks, lstrip_blocks, loopcontrols, tojson, raise_exception); feature inventory of serve/chat_template.jinja (183 lines), serve/glm5_chat_template.jinja (257), data/glm-dsa/templates/glm-5.3.official.jinja (251), glm-5.3.gguf-ud-iq2_m.jinja (251), glm-5.2.jinja (119), tools/glm_chat_template.jinja (257), tools/mm3/chat_template.jinja (265), serve/fixtures/minimax_m31/chat_template.jinja (248), tools/ds4/chat_template.jinja (96), serve/fixtures/glm_tool_images.jinja (22).

**Behaviors to reproduce**

- Environment: trim_blocks=true, lstrip_blocks=true, keep_trailing_newline=false, no autoescape, loop controls (break/continue) enabled, Undefined behaviour lenient as in Jinja2's default Undefined: a missing key or attribute is undefined and falsy, prints as empty, iterates as empty, and an attribute of undefined is an error. Map values preserve insertion order.
- Render call takes messages, tools, add_generation_prompt plus arbitrary kwargs (enable_thinking, reasoning_effort, clear_thinking, thinking_mode, template_model_id, effort, preserve_thinking, add_vision_id and whatever a caller passes). strftime_now and the generation tag are not defined, matching Maya.
- tojson(x, ensure_ascii=False, indent=None, separators=None, sort_keys=False) emits PRM-01 dumps output and is marked safe.
- The output formatter for non-string values follows Python str(): True/False/None, Python float repr, Python repr of lists and dicts. A string filter with the same semantics; trim uses Python strip().
- pycompat method callback with Python semantics (own code, not minijinja-contrib): dict.items/keys/values/get; str.split/strip/lstrip/rstrip (with and without argument), startswith/endswith (including tuple argument), replace, upper/lower/title/capitalize, count, find. Mutating methods (append, update, pop) are unknown-method errors, as Jinja2's immutable sandbox refuses them.
- Filters, each verified (or supplied by us where minijinja differs): capitalize, replace, length (code points), list, items, default, safe, sort(attribute=..., case_sensitive=...) with a stable sort, unique(case_sensitive=...) with first-occurrence order, string, trim, tojson. Tests: defined, undefined, none, string, mapping, iterable, number, boolean, true, false, in / not in over list and tuple literals.
- Language features, each with a conformance case: macros with default arguments; macros defined inside an if block and used later; macros calling macros, with results used as truthy strings and compared with ==; a recursive macro (MiniMax to_xml); namespace() with attribute assignment holding lists; list + list; dict literals inside lists; ~ and + string concatenation; inline if-else; range(a, b); nested for with break; for ... if loop filters over items(); loop.index0/first/last/previtem/nextitem; slices [1:], [::-1], negative indexes; integer dot-subscript x.0 / x.1 on sequences and strings.
- Fallback if the pinned minijinja parser rejects x.N: a load-time rewrite of .N subscripts to [N] outside string literals and comments, with its own unit tests showing Jinja2-equivalent results. It is used only when the spike proves it necessary.
- raise_exception(msg) aborts rendering with a TemplateError carrying msg. Template syntax errors are reported at load with file and line.
- The value bridge converts PRM-01 Values to minijinja Values with order preserved and big integers kept, and passes Python-style ints and floats through.

**Parity tests**

serve/test_qwen_template.py Golden (2 methods: the 10 chat_golden.json cases must equal hf byte for byte; vendor-gated) is the primary oracle. test_minimax_frontend.py Template.test_shared_part_is_official and test_off (differential render of the official vs Maya MiniMax templates over 4 conversations × 6 efforts; vendor-gated). A new feature-conformance suite of about 45 cases, one per inventory row, run on synthetic snippets with hand-derived expected output. Every vendor template must load and render the PRM-08 conversations without error (vendor-gated).

**Definition of done**

A written spike note in specs/022-*/research/jinja-coverage.md lists each inventory feature with supported/overridden/rewritten status at the pinned version. All conformance cases pass. With CONSOLE_VENDOR_SRC set, the 10 Qwen goldens match exactly, the MiniMax differential test passes, and all 10 template files load and render. tojson, string and trim are proven to use PRM-01 semantics.

<a id="prm-04"></a>
### PRM-04 Byte-level BPE tokenizer, ByteTokenizer and incremental detokenizer

- **Milestone:** M1
- **Rust target:** new crate console/crates/console-tokenizer (lib): byte_map.rs, pretok.rs, bpe.rs, special.rs, detok.rs, byte_tok.rs, pack_dir.rs
- **Platform:** platform-neutral
- **Risk:** medium. Unicode property tables differ between Python's regex module and Rust regex-syntax versions, and Python \s/isspace includes U+001C..U+001F where Unicode White_Space does not. Both need explicit tests, with any residual difference recorded. fancy-regex backtracking performance on long whitespace runs needs a bounded-time test (5,000-char inputs).
- **Depends on:** PRM-01; PRM-02
- **Estimated size:** 1000-1300 lines of code; 600-800 lines of tests
- **New dependencies:** fancy-regex (exact pin); regex (exact pin; literal alternation and Unicode classes); unicode-normalization (exact pin; NFC for minimax)
- **Donor sources:** tools/strata_tokenizer.py 1-451 (bytes_to_unicode, QWEN35/GLM/DEEPSEEK3/MINIMAX patterns 47-111, _IsolatedSplits, Tokenizer.__init__/from_dir/from_gguf, _bpe, _encode_plain, _encode_segment, _encode_matching, encode, token_bytes, decode); serve/server.py ByteTokenizer 2061-2084, Detokenizer 2294-2313, tokenizer load 7178-7184; tools/test_tokenizer_glm.py.

**Behaviors to reproduce**

- The GPT-2 byte-to-unicode table, exactly in Maya's order.
- Pre-tokenizers: qwen35 (with the [\p{L}\p{M}] letter class), glm4/glm5 (\p{N}{1,3}, no \p{M}, ignore_merges=true so a pre-token that is itself a vocabulary entry is emitted whole), deepseek3 (three isolated split stages, with the text between matches kept as its own piece), minimax (NFC per plain segment, then the o200k-style pattern including (?i:'s|...) and [\r\n/]*). Any other pre name is refused with Maya's message.
- BPE always merges the lowest-ranked pair first. The constructor refuses duplicate tokens, merges that are not pairs, and merges naming tokens outside the vocabulary, with Maya's messages. A KeyError-equivalent fires if BPE yields an out-of-vocabulary piece.
- Special literals: token types 3 (CONTROL) and 4 (USER_DEFINED) become special_tokens. Type-4 literals match with or without parse_special; type-3 only with parse_special. Matching is leftmost, longest literal first. A match that starts inside a plain span (byte offsets in Rust) is left to ordinary BPE; plain spans are consumed in order.
- from_dir reads vocab.json, merges.txt (split on \n), token_type.json (optional) and tokenizer.json (optional; pre defaults to qwen35; special_ids). from_gguf_metadata(map) builds from tokenizer.ggml.* keys with special ids taken from *_token_id keys, and requires model gpt2.
- token_bytes: type 3/4 tokens are their UTF-8 text; others map back through the byte alphabet (an error outside it). decode joins bytes and replaces invalid UTF-8 with U+FFFD.
- Detokenizer: incremental UTF-8 decoder over token_bytes that holds an incomplete multi-byte character and emits U+FFFD where Python's errors='replace' would. ByteTokenizer falls back to whole re-decode with the trailing-U+FFFD hold, exactly as Maya does.
- ByteTokenizer: one id per UTF-8 byte, the six SPECIALS from id 256 in Maya's order, special_ids {eos: 257}, the same parse_special and plain behaviour, and the same decode.
- Piece memo and long-segment LRU (2048-char threshold, about 1M tokens) as pure optimizations that cannot change ids; thread-safe.
- Exposes special_tokens, token_types, special_ids and n_vocab for stop sets, literal tags and think tables.

**Parity tests**

tools/test_tokenizer_glm.py: 11 methods (GlmPatternTest 6, FromDir 2, PlainSpans 1, PreSchemeGuard 2), re-expressed with synthetic vocabularies. serve/test_detok.py: 3 methods (OldDetokenizer, Detok); Maya skips them without a real pack, and they are re-expressed on the PRM-02 synthetic tokenizer. The decode(encode(s)) == s round trip over Maya's boundary corpus (multi-byte, emoji, combining marks, whitespace runs, C0 controls) for all four pre families. A real-pack parity test is optional and gated by CONSOLE_PACK_TOKENIZER (labelled unverified when absent). End-to-end id parity comes through PRM-08's render_ids fixture.

**Definition of done**

All re-expressed tokenizer and detok tests pass. Round trips hold for every family. Plain-span and type-3/4 behaviour is covered, including a literal match straddling a span boundary. The ByteTokenizer matches Maya ids on hand-computed cases. The crate has no dependency on minijinja, and console-engine can depend on it alone.

<a id="prm-05"></a>
### PRM-05 Thinking-level vocabulary, GLM effort dialects and ChatTemplate family rendering

- **Milestone:** M2
- **Rust target:** console-prompt::effort (effort.rs, dialect.rs) and console-prompt::template (chat_template.rs)
- **Platform:** platform-neutral
- **Risk:** medium. Family detection by magic substrings is brittle but is the parity target. Keep it, and add an optional explicit family override in config as an additive feature. The forced_thinking (CYBER-FROST) template is not in the repository and is tested only with a synthetic template.
- **Depends on:** PRM-03; PRM-07
- **Estimated size:** 750-950 lines of code; 600-750 lines of tests
- **New dependencies:** regex (already pinned in PRM-04); sha2 (exact pin)
- **Donor sources:** serve/frontend.py 37-172 (ChatTemplate: family flags 56-81, render 83-157, think_level 159-172) and 188-296 (EFFORT, QWEN_EFFORT, EFFORT_NAMES, effort_level, effort_name, effort_kwargs, TOKEN_CAP_HINT, deepseek_effort_kwargs, config_budget, config_effort, deepseek_keep_thinking, budget_effort); serve/glm_dsa_template.py 1-97 (effort_dialect, EffortDialect.nearest/template_kwargs/describe, reads_images, GLM53_TEMPLATE_SHA256); serve/server.py checked_config_effort 6874-6886.

**Behaviors to reproduce**

- Effort table, case-insensitive and trimmed: none/off/minimal/disabled/false map to off; low to low; medium and high to high; xhigh/max/maximum to max; auto/default to auto (the template is told nothing); boolean false is off; None or '' is nothing. Any other word is a ValueError (HTTP 400) whose text names EFFORT_WORDS exactly.
- effort_kwargs returns {}, {enable_thinking:false} or {reasoning_effort}, plus effort_name when the client's word is one of low/medium/high/xhigh/max and differs from the level.
- deepseek_effort_kwargs: an exact int (not bool) in 1..100 is a level; above 100 the error carries TOKEN_CAP_HINT; other non-string types are rejected. config_effort validates the run config (DeepSeek accepts a decimal string; other families reject numbers with the hint). config_budget, and budget_effort (budget_tokens under 2048 is low, under 8192 is high, otherwise max).
- effort_dialect(source): kind glm, qwen or none, using the _LIST/_EQ/_ELSE regexes. Levels are sorted by ORDER, the default is the first fallback word, the enable_thinking flag is recorded, and sha256 is compared with GLM53_TEMPLATE_SHA256. nearest() picks the next known level upward; template_kwargs(level, off) behaves as Maya's; describe() returns the startup log line.
- ChatTemplate::load(path, glm_dsa) sets these flags by the exact substring tests: glm_effort (the 'reasoning_effort in [\'low\', \'high\']' phrase), deepseek (｜DSML｜), minimax (]<]minimax[>[), forced_thinking (regex set\s+enable_thinking\s*=\s*true), qwen (none of those three and all of <|im_start|>, <function=, 'tool | tojson'), keeps_thinking. reads_images comes from <|begin_of_image|> or <|vision_start|>.
- render per family: DeepSeek routes to the PRM-07 encoder (tools attached to the first system message, which is inserted if missing; thinking_mode; drop_thinking = !CONSOLE_DS4_KEEP_THINKING; add_generation_prompt=false strips the trailing '<｜Assistant｜>' and think token unless a task ends the prompt). MiniMax: thinking_mode='disabled' when thinking is off, otherwise reasoning_effort is the client's own word from low..max, and tools are re-wrapped as {type:function, function}. GLM-effort templates: reasoning_effort is 'low' when off, the level if low/high, else 'max', with no enable_thinking. glm_dsa with another dialect uses the dialect's template_kwargs. Qwen and unknown templates: low/high/max become low/medium/xhigh, enable_thinking is always passed as a boolean when add_generation_prompt is true, qwen templates get tools re-wrapped into OpenAI form, and forced_thinking templates with thinking off get '\n</think>\n\n' appended when the output ends with '<think>\n'. GLM-effort templates with thinking off get '</think>' appended after a trailing '<think>'.
- effort_name is popped and reasoning_effort 'auto' removed before rendering. think_level(kwargs) returns low/high/max for glm_dsa templates and None otherwise.
- checked_config_effort: when the config has no level it falls back to the model's own default level (supplied by the model registry, not a quant table), and a bad value aborts startup with Maya's message shape.

**Parity tests**

test_minimax_frontend.py EffortNames (2), Effort (1), Template (5; vendor-gated). test_qwen_template.py Family (2; vendor-gated plus synthetic probes). test_glm_dsa_serve.py EffortDialect (7; exact GLM prefixes and suffixes, glm-5.3 official, gguf and glm-5.2 files, vendor-gated, with dialect detection also covered on synthetic glm templates). test_glm_dsa_think_budget.py Level (2, including the LEVELS table at lines 62-63). test_server.py GlmThinkingLevels (3). test_tools.py ConditionalThinkingTools (2). test_ds41_conformance.py Rendering effort cases (about 4: test_all_numeric_budgets_and_aliases, test_invalid_budgets_are_rejected, test_config_numeric_string_is_an_effort_level, test_config_effort_by_family).

**Definition of done**

Every listed Maya test is re-expressed and passes. Vendor-gated tests pass with CONSOLE_VENDOR_SRC set. Error texts for invalid efforts match Maya's strings exactly, modulo approved branding changes. A table test covers every spelling × family combination (GLM, GLM-dialect-5.2, Qwen, MiniMax, DeepSeek) against the expected kwargs.

<a id="prm-06"></a>
### PRM-06 Request normalization for OpenAI Chat Completions and Anthropic Messages (including the DeepSeek path and media parts)

- **Milestone:** M2
- **Rust target:** console-prompt::normalize (openai.rs, anthropic.rs, deepseek.rs, media.rs, tool_order.rs, json_note.rs) producing a typed NormalizedRequest {messages: Vec<Value>, tools: Option<Vec<Value>>, kwargs: TemplateKwargs, flags: InternalFlags}
- **Platform:** platform-neutral
- **Risk:** medium. Python truthiness and key order are load-bearing. The asymmetric treatment of explicit false between the DeepSeek and other paths must be reproduced on purpose, with a test that names it.
- **Depends on:** PRM-01; PRM-05
- **Estimated size:** 900-1200 lines of code; 700-900 lines of tests
- **Donor sources:** serve/frontend.py 176-186 (_text_of, IMAGE_PARTS, VIDEO_PARTS), 299-398 (_has_media, _image_source, _video_source, _parts_of, images_of, media_of, deepseek_images), 561-797 (_late_system_to_user, stable_tool_order, _json_format_note, _clear_thinking, openai_to_messages, anthropic_to_messages); serve/response_schema.py 14-36 (json_instruction, with_system_note).

**Behaviors to reproduce**

- OpenAI path for families other than DeepSeek: developer becomes system; user/tool/assistant content goes through _parts_of (a plain string unless an image or video part is present, then an ordered list of text/image/video items); system content goes through _text_of (text parts of type text, input_text or none, joined with no separator); truthy reasoning_content is kept.
- Assistant tool_calls become [{function:{name, arguments}}]; string arguments are JSON-decoded, blank becomes {}; id and type are kept only when glm_dsa is set. An assistant message with no content, calls or reasoning is dropped.
- Tools are flattened from {type:function, function} to the inner object. tool_choice 'none' removes tools; 'required' sets force_tool to ''; a named choice sets force_tool to the name (only when tools exist).
- Thinking kwargs come from effort_kwargs(reasoning_effort or reasoning.effort), so an explicit top-level false is ignored on this path, as in Maya. A falsy chat_template_kwargs.enable_thinking replaces everything with {enable_thinking:false}. chat_template_kwargs.reasoning_effort applies only when thinking is not disabled. A boolean clear_thinking passes through only for glm_dsa.
- response_format json_object/json_schema (also llama.cpp's response_format.schema) adds json_instruction (with json.dumps(schema) using Python's default ensure_ascii=True) via with_system_note: appended after a blank line to a leading system message (or as a text part for list content), or inserted as a new first system message.
- Late system messages (index > 0) become user messages for every family except DeepSeek.
- stable_tool_order: a process-wide LRU of at most 64 tool-name sets returns a known set in first-seen order. Fewer than two tools, duplicate names or nameless tools pass through. It lives in a per-Service store with a test reset hook.
- DeepSeek path: deep copies that keep ids, namespaces, content_blocks, task and latest_reminder; arguments decoded up to twice, with a non-object becoming {arguments: original}; namespace-qualified tool names 'ns::name' with the namespace description prepended; effort read with req.get so an explicit false turns thinking off.
- Anthropic path: system as a string or block list (joined with '', or with two newlines for DeepSeek); text blocks joined the same way; thinking blocks go to reasoning_content; tool_use becomes tool_calls; every tool_result becomes its own tool message emitted in place, so [tool_result, text] yields a tool message then a user message; media turns without tool_result use list content; DeepSeek user turns become {role:user, content_blocks}. Tools {name, description, input_schema} become {name, description, parameters}. tool_choice none/any/tool map as in Maya. thinking disabled turns thinking off, otherwise output_config.effort, otherwise budget_tokens via budget_effort.
- Media normalization: image_url/input_image/image and video_url/input_video/video; sources may be data: URLs, http(s) URLs or local paths; Anthropic base64 sources become data: URLs. Tool results may carry media. images_of, media_of and deepseek_images (the reference encoder's order after tool results are re-ordered by call id) are provided.
- Internal flags (force_tool, prefill, blocked, think_max, think_resume, keep) live in a typed struct and are never read from client JSON (see deviations).
- Error semantics: malformed shapes that make Python raise KeyError/TypeError/AttributeError/IndexError produce a typed MalformedRequest error (mapped to HTTP 400 'malformed request' by console-http); ValueError cases produce a 400 with Maya's text.

**Parity tests**

test_tools.py ClientStops.test_empty_assistant_turns_are_dropped and test_tool_choice_none (2 of 5), JsonMode prompt-side assertions (4). test_server.py StableToolOrder (4), ClientShapes (4). test_ds41_conformance.py Rendering adapter, separator and argument-tolerance cases (about 8). test_glm_dsa_serve.py ToolPassThrough (3, id and clear_thinking pass-through). test_tool_images.py (4) and test_tool_videos.py (9), normalization assertions only (expansion goes to PRM-11).

**Definition of done**

Every listed test is re-expressed and passes. A golden table of at least 40 request bodies (both dialects, all families) maps to expected NormalizedRequest JSON, checked in as hand-derived expectations with comments citing frontend.py lines. Client JSON key order is preserved through to the output. Underscore-prefixed client fields never reach internal flags.

<a id="prm-07"></a>
### PRM-07 DeepSeek-V4.1 prompt encoder and reference decoder port

- **Milestone:** M2
- **Rust target:** console-prompt::deepseek (encoder.rs, decoder.rs), with DeepSeek's MIT notice kept in the module header
- **Platform:** platform-neutral
- **Risk:** low. Mechanical port. json.dumps formatting comes from PRM-01. The MIT notice must be preserved (DeepSeek copyright) with provenance in NOTICE.md.
- **Depends on:** PRM-01; PRM-02
- **Estimated size:** 750-950 lines of code; 500-650 lines of tests
- **New dependencies:** regex (already pinned)
- **Donor sources:** serve/ds41_encoding.py 1-995 (special strings 34-56, 431; merge_tool_messages; sort_tool_results_by_call_order; process_image_messages; render of system/user/latest_reminder/assistant/tasks; reasoning effort 448-479; encode_messages 815-849; parse_tool_calls and parse_message_from_completion_text 895-995); docs/deepseek-prompt-format.md; serve/fixtures/deepseek_v41/*.

**Behaviors to reproduce**

- Byte-exact port of encode_messages: rejects the image placeholder inside text; merges tool messages into tool_result blocks of a user message, merging adjacent user/tool messages unless one carries a task; re-orders tool_result positions by call order while interleaved text keeps its place; turns image blocks into placeholder text blocks with blank-line joins.
- Layout: bos; <｜System｜> when the first message is a system message or an effort line exists; the effort line only in thinking mode at index 0; tools block after a blank line with one json.dumps(tool, ensure_ascii=False) line per tool; optional response-format block; <｜User｜> blocks joined by blank lines with <tool_result> wrapping; <｜latest_reminder｜>; assistant = [reasoning + </think>] + content + [blank line + DSML calls block] + eos; mid-conversation system turns; assistant header rules with <think> or </think>; wo_eos.
- drop_thinking defaults to true but is disabled when any message declares tools; reasoning before the last real user message is dropped. Client history objects are never mutated.
- DSML calls block: invoke and parameter lines with string=true|false; values may be a dict, a JSON string or a twice-encoded JSON string, and anything else becomes {arguments: raw}; namespaced names are supported.
- Task tokens (action/query/authority/domain/title/read_url) with Maya's placement rules.
- Reasoning effort: int 1..100 or low/high/max = 50/75/100, default high.
- Assertion failures in the reference become a typed EncodeError carrying the same message (see deviations for the HTTP mapping).
- Strict reference decoder (parse_tool_calls, parse_message_from_completion_text), used as the test oracle for PRM-10.

**Parity tests**

test_ds41_conformance.py Rendering (19 methods, of which the 5 official fixture pairs compare as UTF-8 bytes; effort cases are shared with PRM-05) and Images (4, placeholder ordering). The decoder is exercised by the Parsing oracle in PRM-10. The fixtures are vendored and need no vendor gate.

**Definition of done**

All 5 fixture pairs match byte for byte (no trailing newline). The Rendering and Images tests are re-expressed and pass. Deep-copy immutability is tested. The module header and NOTICE.md carry DeepSeek's MIT notice and the source revision 1bae0e10.

<a id="prm-08"></a>
### PRM-08 Special-literal protection, render_ids, startup template selection and prompt-measurement operations

- **Milestone:** M2
- **Rust target:** console-prompt::literals, console-prompt::render (render_ids.rs, memo.rs), console-prompt::select (template selection), console-prompt::measure
- **Platform:** platform-neutral
- **Risk:** medium. render_ids_other_models.json is the only committed oracle for GLM and MiniMax prompts plus the tokenizer plus literal protection, so this package is where Jinja/tokenizer mismatches surface. Python code-point spans must be translated to byte spans consistently.
- **Depends on:** PRM-04; PRM-05; PRM-06; PRM-07
- **Estimated size:** 800-1000 lines of code; 650-850 lines of tests
- **New dependencies:** sha2 (dev; already pinned)
- **Donor sources:** serve/frontend.py 401-558 (KEPT_LITERALS, CALL_TAGS, literal_tags, _mark, _mark_deep, _has_tag, mark_literals, LiteralMemo, unmark_literals); serve/server.py render_ids 2532-2569, PromptMemo 2128-2240, prompt_memo_on 2088, literal setup 2478-2479, chat_template_path 6855-6871, chat_prompt 3704-3715, tokenize 3717-3733, detokenize 3735-3741, count_tokens 3743-3763 (text-side), _special_ids 3922-3928.

**Behaviors to reproduce**

- literal_tags: every special literal (types 3 and 4) except '/nothink' maps to chr(0xF0E00 + k), with literals sorted longest first, then alphabetically.
- mark_literals replaces literals in every string of every message field except role, and in tools, returning changed=false when nothing matched. Assistant messages keep the six GLM call tags real in non-tool_calls fields. Structured tool_calls are fully marked. Assistant content that starts (after left-strip) with <think> and contains </think> keeps only the first pair real.
- unmark_literals restores the text and returns the spans as byte offsets. The tokenizer encodes with parse_special=true and those plain spans.
- render_ids: mark, render, append '</think>' when enable_thinking is false and the prompt ends with '<think>', append the server suffix, then tokenize (the unmarked path when nothing changed).
- Memo: the segment cache and literal memo produce ids identical to the plain path. The env switch (renamed from MAYA_PROMPT_MEMO, see deviations): '0' disables caching; 'verify' encodes both ways, raises a RuntimeError-equivalent with Maya's message on mismatch and logs the verified line.
- Template selection at startup: the pack's tokenizer/chat_template.jinja; a glm-dsa pack uses its own template or a configured default path (not vendored); a GLM-5 pack whose template starts with '[gMASK]<sop>' and contains the effort phrase is swapped for a configured swap template unless the renamed MAYA_PACK_TEMPLATE=1 equivalent is set; when no template exists, an explicit startup error replaces Maya's Qwen fallback (see deviations).
- chat_prompt merges the run-config default effort when the request names none; strata_mcp merging of hub tools is a hook supplied by console-mcp.
- tokenize: messages, or content/prompt with parse_special (default true) and add_special/add_special_tokens adding bos; returns {tokens, count, max_model_len}. detokenize validates a list of non-negative non-bool ints and returns {content, prompt}. count_tokens returns {tokens, images, approximate, max_context}, with media counted as markers and a vision-count hook from console-media for DeepSeek/MiniMax pictures.

**Parity tests**

test_server.py LiteralSpecials (6), ImageMarkers (1). test_ds41_conformance.py ServiceIntegration: test_literal_role_thinking_and_dsml_tokens_stay_plain_text, test_literal_tokens_in_schema_arguments_and_tool_results_are_data, test_quoted_image_placeholders_are_text_in_prepare_and_token_count (3). test_prompt_memo.py SameIds (9; the history and fuzz sequences via PRM-02 MT19937), SameIdsRealTokenizers (1, pack-gated), LiteralMemoSame (2). test_render_other_models.py (2): all 72 [count, sha256] entries of render_ids_other_models.json for deepseek, glm, glm5 and minimax, using the PRM-02 synthetic tokenizer (vendor-gated templates). test_glm_dsa_serve.py TemplateAtStart (2).

**Definition of done**

All 72 render_ids entries match with CONSOLE_VENDOR_SRC set. LiteralSpecials, the memo and selection tests pass. The verify mode and its failure path are tested. The startup error for a missing template is tested and documented in the spec.

<a id="prm-09"></a>
### PRM-09 Streaming OutputParser and parse_tool_call (GLM and Qwen call forms)

- **Milestone:** M2
- **Rust target:** console-prompt::parse (events.rs, tool_call.rs, parser.rs, scan.rs)
- **Platform:** platform-neutral
- **Risk:** medium. Code-point vs byte slicing: deltas from the detokenizer are whole characters, so hold-back lengths must be computed on chars. Python's ensure_ascii=True escaping in streamed fragments matters for byte parity with Maya's SSE output.
- **Depends on:** PRM-01; PRM-02
- **Estimated size:** 1100-1400 lines of code; 800-1100 lines of tests
- **Donor sources:** serve/frontend.py 800-936 (ToolCall, to_openai, Event, THINK_END/CALL_START/CALL_END/FUNC_START, _declared_type, _arg_value, call_name, MalformedToolCall, parse_tool_call) and 1264-1689 (OutputParser: _track, _in_code, in_code_after, call_opened, _reset_scan, _start_call, _scan, _close_scan, _hold, close_reasoning, feed, _feed, finish).

**Behaviors to reproduce**

- Event {kind: reasoning|content|tool_start|tool_args|tool_call|tool_incomplete, text, call, complete, logprobs}. ToolCall {name, arguments (ordered object), id, namespace}.
- There are three states (reasoning, content, call), and the parser starts in reasoning when the thinking flag is set. Reasoning ends at '</think>' text unless token_only_end, in which case only close_reasoning() ends it. A suffix that could grow into a tag is held back, so no partial '<tool_' or '</thi' ever leaks.
- After reasoning ends and after each call, leading newlines are dropped when no rewriter is attached (GLM/Qwen) and kept for DeepSeek/MiniMax.
- Content: emitted up to a possible partial '<tool_call>'. Trailing newlines are withheld, then dropped if a call follows and flushed at finish. Before a call, GLM/Qwen emit the preceding text right-stripped and only if non-blank; DeepSeek/MiniMax drop exactly one trailing blank line.
- A '<tool_call>' inside a fenced block (``` or ~~~, tracked line by line over already-emitted answer text) or inside inline code (odd backtick count in the current paragraph) is text. in_code_after(text) and call_opened are exposed for PRM-12.
- Call state: the end-tag search resumes from where it stopped and stays linear (5,000-char body). Lookalikes '</tool_cal', '</tool_callx' and '</tool_call\n' do not close a call. With stream_tools, tool_start fires once the name is known, then tool_args fragments concatenate to one JSON object: string parameters stream as JSON string content (ensure_ascii=True escapes, as Python), other values are emitted whole. The final tool_call reuses the tool_start id.
- parse_tool_call GLM form: name before the first '<', trimmed; the rest is empty or starts with <arg_key>; only whitespace between </arg_key> and <arg_value>; a missing </arg_value> is tolerated; keys are trimmed, values are not.
- parse_tool_call Qwen form: <function=NAME> with <parameter=P> items; exactly one leading and one trailing newline removed; an unclosed parameter tag is malformed.
- Value typing: schema type string gives raw text; otherwise JSON if it parses, else raw text; with no schema, JSON if it parses; unions=true (glm_dsa) keeps strings for type lists or anyOf/oneOf that admit string.
- Malformed bodies never fail: the text goes to the malformed log; an announced call ends as tool_call(complete=false) with JSON-closable arguments, otherwise '<tool_call>'+body+'</tool_call>' is replayed as content.
- finish(): an announced unterminated call ends complete = !strict_tools, with an empty arguments map (the fragments carry them); strict_tools with an unannounced unterminated call yields tool_incomplete; otherwise leftovers are flushed as reasoning or content. single_tool stops after the first complete call. The THINK_AGAIN sentinel (NUL think NUL) re-enters reasoning.
- Invariant: for every split of the input (sizes 1, 2, 3, 5, 7, 11, 64 and seeded random 1..7), the event sequence (with adjacent text events merged) equals the whole-text parse.

**Parity tests**

test_tools.py GlmCalls (8), QuotedCalls (3), CallEndRescan (2). test_server.py MalformedToolCallAnswers (2, parser half). test_glm_dsa_serve.py ToolPassThrough.test_string_in_union_stays_a_string (1). The generic parser parts of test_ds41_conformance.py Parsing and test_minimax_frontend.py Parser are shared with PRM-10. Chunking-invariance property tests use PRM-02's Mt19937 so the random splits match Maya's seeds.

**Definition of done**

All listed tests are re-expressed and pass. The chunking-invariance property holds over every vector in the Maya tests plus a seeded fuzz corpus of at least 500 outputs. A linear-time test on a 5,000-char body runs in bounded time. The event contract is documented in specs/022-*/contracts/parser-events.md for console-responses, console-mcp and the Phase 2 front end.

<a id="prm-10"></a>
### PRM-10 DSML and MiniMax stream rewriters

- **Milestone:** M2
- **Rust target:** console-prompt::parse::rewrite (dsml.rs, minimax.rs)
- **Platform:** platform-neutral
- **Risk:** low. Small state machines. The chunking-invariance property must also hold through the rewriter plus parser composition.
- **Depends on:** PRM-09; PRM-07
- **Estimated size:** 600-800 lines of code; 500-650 lines of tests
- **Donor sources:** serve/frontend.py 939-1261 (DSML, _DSML_ATTR, DsmlRewriter feed/finish/_close/_plain/_tag/_esc; MINIMAX_NS, THINK_AGAIN, may_be_string, MinimaxRewriter feed/finish/_plain/_tag/_close_value/_scalar/_parse) and the OutputParser wiring at 1264-1297.

**Behaviors to reproduce**

- DsmlRewriter: the calls open/close tags disappear; invoke open becomes '<tool_call>'+name; invoke close becomes '</tool_call>'; parameter open becomes key tags plus value open (plus an opening JSON quote for string=true). Inside a value only the exact '</｜DSML｜ parameter>' is structural, and other DSML tags, legacy '</arg_value><tool_call>' text and partial closers are data. A suffix that may grow into the closer is held. Whitespace between tags of a calls block is dropped.
- string=true values stream incrementally as JSON string content with '<' escaped as <; string=false values are buffered and emitted whole at the closer. The model's string flag decides the type even against the schema (the parser carries no schemas for DeepSeek). '::' names set namespace.
- MinimaxRewriter: <mm:think> becomes THINK_AGAIN and </mm:think> becomes </think> (both literal inside a value). NS<tool_call>/NS</tool_call> toggle the calls block, dropping text between tags. NS<invoke name=N> becomes '<tool_call>N'; NS</invoke> becomes '</tool_call>'. NS<K> opens parameter K until its own NS</K> at depth 0.
- may_be_string: type string or a list holding it, anyOf/oneOf alternatives, allOf where every non-empty part admits string, string enum/const, $ref into definitions/$defs with cycle protection (cycles count as false). A string-admitting parameter streams as a JSON string. Nested NS<k> elements become an object, or an array when every element is named item. A plain value becomes true/false/null or a number when it matches -?\d+(\.\d+)?([eE][-+]?\d+)?, otherwise a string.
- finish() closes an open value and an open invoke so truncated output stays parseable. MiniMax may think again after answer text or between calls, and that text is reasoning.

**Parity tests**

test_ds41_conformance.py Parsing (10): string flags, literal DSML tags in values, partial closers, early streaming of long strings, namespaces, and re-parsing every assistant completion in the 5 fixture outputs at chunk sizes 1, 7 and whole against the PRM-07 reference decoder. test_minimax_frontend.py Parser (5): interleaved thinking, nested values, string unions, no schema, seeded random chunking. test_deepseek_tool_block.py (6): parser parts here, loop-guard parts in PRM-15.

**Definition of done**

Parsing and Parser tests are re-expressed and pass. The fixture-completion re-parse matches the reference decoder at every chunk size. Composition fuzzing with Mt19937 seeds passes.

<a id="prm-11"></a>
### PRM-11 Prompt-side orchestration: prepare(), forced tool-call prefills, JSON mode, context room and media pad expansion

- **Milestone:** M2
- **Rust target:** console-prompt::prepare (prepare.rs, prefill.rs, media_expand.rs)
- **Platform:** platform-neutral
- **Risk:** medium. PRM-11 and PRM-15 depend on each other (prepare calls the cross-turn guard). Build PRM-15's pure functions first or stub them behind a trait and finish the wiring in PRM-15. The real vision encoders are out of scope, so media is verified only with fakes.
- **Depends on:** PRM-08; PRM-07; PRM-15
- **Estimated size:** 700-900 lines of code; 650-850 lines of tests
- **Donor sources:** serve/server.py Service.prepare 3526-3702 (loop-guard hooks, force_tool, default effort, _think_max, prefill per family 3557-3567, _blocked/_keep wiring, _as_written call, media handling 3574-3679, context room 3680-3694, thinking flag and _think_resume 3695-3701), ContextOverflow 416, BadBody 503 'model is starting'; serve/frontend.py 599-609; serve/response_schema.py 14-36.

**Behaviors to reproduce**

- prepare(normalized, max_new, ctx, guard_on) returns PreparedPrompt {ids, thinking, max_new, flags{prefill, blocked, keep, think_max, think_resume}, embeddings_ref}.
- A forced call (force_tool set and tools present) turns thinking off and builds the prefill from the explicit family: DeepSeek '\n\n<｜DSML｜ calls>\n' + optional invoke line; MiniMax NS+'<tool_call>\n' + optional NS invoke; GLM form ('<arg_key>' in the template source) '<tool_call>'+name; otherwise the Qwen form '<tool_call>\n' + optional '<function=NAME>\n'. The prefill is tokenized as the render suffix and fed to the parser first (PRM-12). The tool name is not validated, matching Maya.
- Default effort from the run config is merged only when the request has neither reasoning_effort nor enable_thinking (the DeepSeek variant for DeepSeek). think_max = true only when the request's own level is max and think_level(kwargs) is max (glm_dsa).
- The loop-guard wiring calls PRM-15: tool-repeat notes, the 'continue' blocked note, collapse, block suffixes (only without force) and the keep suffix when looping with tools and the request does not answer the user.
- The Qwen history-own-ids substitution (_as_written over the last 4 noted answers, from PRM-13) is applied to the rendered ids.
- Media: GLM-5.3 text-only templates allow pictures only in tool results and reject user pictures with Maya's 400 text. DeepSeek/MiniMax reject videos ('reads pictures, not videos'). Pad expansion is a pure function: only a pad immediately after its start marker is an image; the same marker text elsewhere is re-encoded as plain text; a video becomes a row of frame spans (start, pads, end); count mismatches give 'the prompt and its images do not match' (and the videos variant). Encoder counts and files come from console-media through a trait.
- Context room = max_context - CTX_SLACK - len(ids). An unset or non-positive max_new means room. max_new > room is a ContextOverflow with Maya's exact message unless fit_max_tokens, which clamps to max(1, room). room < 1 always overflows. max_context <= 0 gives 503 'the model is starting'.
- thinking = enable_thinking is not false. When thinking and a think-end id exists, think_resume = keep_suffix(THINK_NOTE) if its opening thinks.
- JSON mode: json_instruction/with_system_note (shared with console-responses) and post-hoc json_from_text in PRM-16.

**Parity tests**

test_tools.py ForcedToolCalls (3), ConditionalThinkingTools.test_required_call_keeps_thinking_off (1), JsonMode (4, prompt side). test_ds41_conformance.py ServiceIntegration.test_forced_deepseek_tools_prefill_and_parse_real_continuation (1). test_server.py MaxTokens (5), FitMaxTokens (3), NoRoomOrNoToken (3, prompt-side). test_tool_images.py (4), test_tool_videos.py ToolVideos and VideoGuards (9), test_glm_dsa_serve.py TextOnlyImages (4), test_ds41_conformance.py Images (4, expansion half), each with a fake vision trait returning fixed counts.

**Definition of done**

The listed tests are re-expressed and pass, with a fake engine (max_context) and a fake vision trait. All overflow and media error texts match. Prefill strings for the four families are table-tested. The PreparedPrompt contract is documented for console-core.

<a id="prm-12"></a>
### PRM-12 Output pipeline: detokenize, stops, quoted markers, thinking resume and the run() event logic as a pure state machine

- **Milestone:** M2
- **Rust target:** console-prompt::pipeline (stops.rs, output.rs, directives.rs)
- **Platform:** platform-neutral
- **Risk:** high. run() interleaves output logic with queueing, status and engine attempts. The split into a pure pipeline plus console-core executor must keep exactly Maya's ordering of checks (stop id, then keep, then blocked, then held scan, then parser). Interface drift with console-core is the main risk, so the Directive contract must be agreed before both packages start.
- **Depends on:** PRM-09; PRM-10; PRM-04; PRM-11
- **Estimated size:** 900-1200 lines of code; 800-1000 lines of tests
- **Donor sources:** serve/server.py Service.__init__ stop sets 2439-2479; client_stop_strings 624-632; run 4273-4763 (parser construction 4279-4290, prefill events 4305-4306, stop_ids/eos handling in reasoning 4521-4541, quoted markers 4544-4546, keep and blocked branches 4546-4585 delegating to PRM-15, held-tail stop scan 4593-4617, event loop 4618-4650, finish/done 4757-4763, LOOP_STOP 4497-4506, with_lp 4324-4338, logprob drop rules 4317-4321); THINK_RESTARTS 456, THINK_NOTE 457; Detokenizer 2294-2313; _say_malformed 3766-3773.

**Behaviors to reproduce**

- StopSets from the tokenizer: stop_ids are the single-token encodings of <|im_end|>, <|endoftext|>, <|user|>, <|observation|>, <｜end▁of▁sentence｜>, <｜User｜>, [e~[, ]~b]; stop_texts are the same minus <|im_end|>, only where special; think_end_id is </mm:think> for MiniMax templates, else </think>, else none; eos_ids = {special_ids.eos} if named, else stop_ids. The ignore_eos bias set (stop|eos) is exposed for console-http checks.
- OutputPipeline::new(prepared, sampling, template flags) builds the parser (thinking, tools, stream_tools=true, dsml/token_only_end per DeepSeek, minimax, strict_tools/single_tool for Responses, unions for glm_dsa) and emits prefill events first.
- on_token(id, logprob_entry?) returns Vec<Output> where Output is Event(Event) | Directive. Directives for console-core: Restart{append_ids, sampling (full replacement), new_parser_thinking} and End{finish}.
- Inside reasoning with nothing answered, no call and nothing pending: a non-EOS stop id is skipped. At an EOS id with think_resume available and fewer than THINK_RESTARTS (2) restarts, it restarts with prompt+seg_ids+resume_ids+steer (the steer only when the opening thinks); otherwise it ends with finish stop.
- Quoted marker: a stop id that is not EOS while a call is open, or with '<tool_call>' in held+text, or inside code per in_code_after, is text. An unquoted stop id ends with finish stop, after the PRM-15 keep and blocked checks.
- Held-tail scan, outside reasoning only, over stop_texts plus client stops (first 16 non-empty): the earliest hit wins. A server marker inside code or a call is text and scanning continues. A client stop stops anywhere. Text before the match is delivered, the match is not. stop_sequence is reported only for client strings that are not server markers. The longest tail that could grow into a marker is held. The held text is flushed at the end.
- token_only_end: the end-think token's text is dropped and close_reasoning() is called. reasoning_tokens counts tokens produced while the parser is in reasoning. single_tool ends after the first complete call.
- LOOP_STOP from the slice controller: flush held text and, if nothing was answered, emit content LOOP_STOP_NOTE verbatim.
- Logprob attachment (with_lp): waiting entries ride on the next content or reasoning text event; they are dropped when crossing from reasoning into content and for tool events, and cleared for a stop string with no text before it. Entries themselves are produced by the logprobs owner (console-http/API).
- At the end: parser.finish() events, malformed bodies logged in full, done {finish (stop|length|cancel|error|disconnect), completion_tokens, reasoning_tokens, reused, timings, stop_sequence (only when finish is stop)}.

**Parity tests**

test_tools.py ClientStops (5). test_server.py SpelledStopMarker (2), EngineEndTests (4, stop/eos parts). test_loop_guard.py ThinkingMarkers (8). test_logprobs.py OneConversation (3) and Fields (4), attachment-rule assertions only, shared with the API owner. Each runs the pipeline against a scripted token-id fake engine (PRM-02 ByteTokenizer or synthetic BPE) without HTTP; HTTP-level variants are in PRM-17.

**Definition of done**

The listed tests pass against scripted token streams. A property test checks that the pipeline's events equal OutputParser events for inputs without stops or markers. The directive sequence for every resume path is asserted by recorded prompts (ids appended plus sampling). The Directive and Output contract is published in specs/022-*/contracts/output-pipeline.md and accepted by console-core's planner.

<a id="prm-13"></a>
### PRM-13 Thinking budget: arithmetic, soft close at a sentence end, engine keys, Qwen close-as-rendered and settings

- **Milestone:** M2
- **Rust target:** console-prompt::budget (budget.rs, boundary.rs, close.rs, written.rs) plus a SoftCloseController used by console-core's slice loop
- **Platform:** platform-neutral
- **Risk:** medium. The soft close needs the generation loop to stop and restart from prompt+produced, so the controller interface with console-core must be fixed early. The GEN-line formatting itself belongs to console-engine.
- **Depends on:** PRM-12; PRM-05; PRM-04
- **Estimated size:** 700-900 lines of code; 700-900 lines of tests
- **Donor sources:** serve/server.py THINK_TINY_LIMIT/THINK_GRACE/THINK_LONG_RESERVE 438-456, _THINK_BOUNDARY/_WEAK_BOUNDARY 460-463, think_stop_tables 466-489, think_boundary 491-500, sampling_keys 1217-1226 (GEN keys), think_budget_info/asked_max/set_think_budget 2831-2867, _resumed_sampling 3862-3879, _closed_as_rendered 3881-3920, _note_written/_as_written/_as_written_ids 3930-3975, _sliced soft-close parts 4116-4199, run budget computation 4383-4421, think_budget_at_max 6889-6896, main 7311-7320; tools/maya_quants.py 106-165 (defaults).

**Behaviors to reproduce**

- The budget exists only when think_end_id exists. Default 32768 unless the run config sets thinking_budget (0 = none). A per-model default can come from the model registry, replacing the quant-named 8192 case (see deviations). Live setting: 0 or 256..262144 (integer-valued); invalid values give a 400 and change nothing; a model without an end-think token reports supported=false and refuses the POST; saved into the run config with installer.thinking_budget_set=true through console-manage.
- Per request: if max_new <= 1024, reserve = max(max_new//4, min(RESERVE_ENV (default 1024), max(1, max_new//2))) and budget = max(1, min(budget, max_new - reserve - 1)). Otherwise grace = max(0, min(512, (max_new - budget - 1)//2)), and when grace > 0, soft = budget and hard = budget + grace. Examples: max_tokens 1000 gives 499; limits 1..3 give at least 1.
- GLM-5.3 long budget: when think_budget_max (65536) > budget > 0, max_new is set and the request itself asked for max (think_max flag, not the config level, the shared settings or the web chat's untouched default), budget = min(65536, max(budget, max_new - 32768)). think_budget_at_max is 0 unless the template is glm_dsa and the budget is the config default.
- Sampling keys passed to the engine adapter: _think_budget, _think_end, _think_soft, and _think_stops for DeepSeek (think_stop/think_weak/think_dig id tables computed by decoding every token with Maya's rules).
- think_boundary over the last 16 characters: a newline; or . ! ? not preceded by a digit or dot, optionally followed by closing quotes or brackets, then spaces or tabs; or a CJK full stop. Hand-written in place of the lookbehind. No close after '0.' or '...'.
- SoftCloseController: after soft tokens, at the first token whose 16-char tail ends at a boundary and while len(produced) < max_new - 1, ask console-core to stop the engine call, append think_end (or the Qwen close-as-rendered rewrite), yield think_end, and resume with _resumed_sampling (budget keys reduced by produced, or removed once think_end was produced).
- _closed_as_rendered (qwen templates): replace the trailing whitespace of the reasoning so the continuation is '<think>\n' + reasoning.strip() + '\n</think>\n\n'. Returns None on special tokens, leading whitespace or a non-matching prompt tail.
- _note_written/_as_written: remember the last 4 (prompt+answer) id sequences that ended at a stop id (qwen templates, text prompts) and substitute the engine's own ids where a new prompt contains the same bytes and the same special tokens. Any error falls back to the rendered ids with a log line.
- /health fields supplied: thinking_budget_max (GLM-5.3 with default budget), history_thinking (keeps_thinking), text_only.

**Parity tests**

test_think_budget.py Default (3), Field (3), GlmMayaXS (2, re-expressed as a per-model default). test_glm_dsa_think_budget.py EngineBudget (12), EngineBudgetGgufTemplate (with EngineBudget), ContextLeft (1), OtherModels (1), FlashServer (1), Start (2), MainStart (3), WebChat (3, budget assertions; HTTP parts in PRM-17). test_server.py ThinkingBudget (6), ThinkingBudgetAtASentenceEnd (5), BudgetEngine and ThinkTok scaffolding. test_qwen_template.py ServerClose (3, vendor-gated plus a synthetic chatml-think variant).

**Definition of done**

Every arithmetic case from the Maya tests is table-tested. Soft-close behaviour is verified with a scripted engine that records each generate() call's prompt and sampling keys. Close-as-rendered and as-written substitution are covered. Settings validation matches Maya's error texts.

<a id="prm-14"></a>
### PRM-14 Loop guard inside one answer (LoopDetector, LoopGuard policy, ToolSafeGuard) and its slice-controller integration

- **Milestone:** M2
- **Rust target:** console-prompt::loopguard::answer (detector.rs, policy.rs, toolsafe.rs, controller.rs)
- **Platform:** platform-neutral
- **Risk:** medium. It depends on console-core honouring bounded-length sampling overrides and restarting from kept ids. The Python test engines (LoopingEngine, SeqEngine, DeepTok) must be re-created as fake-engine scripts.
- **Depends on:** PRM-12; PRM-13
- **Estimated size:** 750-950 lines of code; 800-1000 lines of tests
- **New dependencies:** regex (already pinned)
- **Donor sources:** serve/loop_guard.py 1-296 (constants 52-69, Loop, Action, LoopDetector 99-157, penalty_window 159-161, LoopGuard 163-240, _TOOL_OPEN/_TOOL_CLOSE/_TAIL 242-244, ToolSafeGuard 247-296); serve/server.py loop_guard_setting 612-621, LOOP_STOP/LOOP_STOP_NOTE 435-437, _loop_guard_on 3977-3980, _guard_piece 3982-3986, _loop_noted 4087-4095, _sliced guard parts 4113-4271, run attempts 4433-4454.

**Behaviors to reproduce**

- Detector: for each token and each earlier position of the same id within P_MAX=2048 (period p >= 8), extend the run length; report the shortest period whose run reaches need[p] = max((reps-1)*p, min_span - p), with reps 4 (p<32) / 3 and min_span 96, or 5 / 4 / 192 while thinking. hold = longest current run. It fires on the last token of the required copies, not earlier.
- The stream is delayed by min(hold, 64) tokens. On a loop, only unsent repeats are dropped.
- Policy: in thinking, loops 1 and 2 get PENALTY and loop 3 gets CLOSE_THINKING (append the think-end token), never STOP. In the answer, the first loop gets PENALTY if fewer than 4 loops were seen in total, otherwise STOP. Before any answer text, STOP yields LOOP_STOP_NOTE (PRM-12).
- PENALTY: restart from prompt + kept ids with repetition_penalty = max(request, 1.15) and penalty_last_n = min(4096, max(128, 2*period)) (keeping a request's -1 or larger window) for 2*period + 128 tokens, then the request's own sampling in a further call (resumed via PRM-13 _resumed_sampling).
- ToolSafeGuard follows token text for tool-call markers (the _TOOL_OPEN/_TOOL_CLOSE patterns, DSML calls blocks) with a 48-char tail. A loop whose repeats touch a call is neither counted nor cut. A loop wholly inside one call gets only the penalty (no drop), once per call, and only when the call is long enough. A fresh guard is used for the non-finite retry.
- Settings: on by default. Off with the renamed MAYA_LOOP_GUARD values 0/off/false/no/none (env beats config), run config loop_guard false, or request loop_guard false; a request true turns it on when the server has it off; loop_guard strings like on/off are accepted and unknown strings are a 400.
- Counters detected, penalised, thinking_closed and stopped, plus a per-request summary row for the Monitor/history (summary() format as Maya).

**Parity tests**

test_loop_guard.py Detection (4), Policy (8), ToolCalls (9), Settings (2), Server (10, against a LoopingEngine-equivalent scripted fake), Http (1, in PRM-17), GuardedUsage (1). Corpora built with random.Random(seed).choices are reproduced with PRM-02 Mt19937. The legitimate-repetition cases (60-row table, 300-number JSON array, 80 near-identical code lines, a 600-token block written twice, three identical calls in one reply) must not fire.

**Definition of done**

All listed tests pass with Mt19937-reproduced corpora. Each restart's ids and sampling are asserted through a recording fake engine. Counter names are documented for the telemetry owner.

<a id="prm-15"></a>
### PRM-15 Loop guard across turns: tool repeats, blocking, history collapse and keep-going

- **Milestone:** M2
- **Rust target:** console-prompt::loopguard::turns (repeat.rs, block.rs, collapse.rs, keep.rs, texts.rs)
- **Platform:** platform-neutral
- **Risk:** high. This is the most policy-dense package, and its prefix-stability and _units splitting must match Python's re.split exactly or collapse changes prompts. It is also the package that injects server-authored text into prompts, which is a product-trust decision the owner already took under D1. Size is near the upper bound. If review finds it too large, split collapse (collapse.rs plus _units) into PRM-15b.
- **Depends on:** PRM-05; PRM-08; PRM-12
- **Estimated size:** 1200-1450 lines of code; 900-1100 lines of tests
- **New dependencies:** regex (already pinned)
- **Donor sources:** serve/loop_guard.py 299-701 (TOOL_* constants, ToolRepeat, _same, args_key, GO_ON, _text, go_on, _gist/_gist_memo, _tool_calls, _times, tool_repeat, tool_blocked, blocked_note, _short, block_result, block_note, STEERS, block_steer, block_sampling, NOTES, tool_note, ECHO_*, Collapse, _units, _key, _round_keys, echoes, COLLAPSE_MAX_CHARS, conv_chars, collapse, TALK, KEEP_MAX, talk, said_before, answers_user, stops_short, KEEP_NOTE, KEEP_STEERS, keep_steer); serve/server.py prepare 3534-3572, _block_suffixes 3988-4019, _keep_suffix 4021-4044, _collapse 4046-4057, _kept_going 4059-4063, _tool_blocked 4065-4070, _tool_repeat 4072-4085, run blocked/keep branches 4291-4303, 4475-4482, 4546-4585, 4625-4644.

**Behaviors to reproduce**

- Window: tool calls since the last user message that says more than a 'continue'-style word (GO_ON, whole message, case-insensitive), last 12 calls. A call is a repeat when name, canonical args (json.dumps sort_keys, ensure_ascii False, default=str) and result are equal, or, for consecutive calls, when the results' gist (digits and non-printable/non-ASCII removed) is equal. Commands containing 'sleep' count only exact results.
- At 3 repeats, a user message with tool_note() (worded for the 3rd, 4th and 5th repeats, the last announcing blocking) is appended after the result, only in the rendered prompt.
- At 5 repeats, (name, args) is blocked. If the model's turn is exactly that one complete call with no text, the call is withheld, and the generation restarts with the block suffix (the template's own rendering of turn end, block_result, block_note and the next opening, computed by double-rendering a dummy conversation and requiring prefix-stability) plus block_steer when the opening thinks. block_sampling raises temperature by 0.15 per attempt from the 2nd, up to 1.5. Mixed batches or calls with trailing text are not intercepted. DeepSeek slices after the outer DSML calls close.
- Collapse: a paragraph (at least 12 normalized chars of content, or 6 of reasoning) in 3 assistant messages, or one call+result 3 times, leaves repeated paragraphs and repeated tool rounds out of the rendered prompt. It is skipped above 32000 chars (renamed env override; 0 = no limit; non-numeric falls back). The collapse of a prefix is a prefix of the collapse of the whole. _units is a hand-written splitter reproducing re.split with capture groups, zero-width lookbehind/lookahead and code-fence segmentation exactly.
- Keep-going: in a looping conversation with tools, when the request does not end with a user message being answered, an answer that would end with nothing new (stops_short: empty, only loop talk per TALK, or text said before) is continued with KEEP_NOTE and keep_steer, at most 3 times. The continuation is joined with a paragraph break computed from the preceding tail. When already answered and thinking, the think-end token is appended and budget keys removed.
- A user's 'continue' while calls are blocked appends blocked_note listing the blocked calls.
- All server-authored texts (NOTES, STEERS, KEEP_NOTE, KEEP_STEERS, block_result, block_note, blocked_note, THINK_NOTE) are reproduced verbatim (Maya MIT, with provenance). The client's own conversation is never edited.
- Counters tool_repeats, tool_blocked, collapsed and kept_going, with log lines.

**Parity tests**

test_loop_guard.py ToolRepeat (2), ToolBlock (9, ScriptEngine-driven), Collapse (7). test_deepseek_tool_block.py DeepSeekToolBlock (6, with DsmlEngine re-created as a fake script). test_prompt_memo.py GistByText (1). Suffix computations run against synthetic templates always and against vendor templates when CONSOLE_VENDOR_SRC is set.

**Definition of done**

All listed tests pass. A property test checks collapse prefix-stability over Mt19937-generated conversations. The block and keep suffixes for every synthetic family are asserted byte for byte. The verbatim texts are checked against the Maya source strings by a test that reads the vendor checkout when available.

<a id="prm-16"></a>
### PRM-16 Parser events to OpenAI and Anthropic response shapes (streamed and collected)

- **Milestone:** M2
- **Rust target:** console-prompt::shapes (openai.rs, anthropic.rs) producing serde_json Values; console-http frames them as SSE or JSON
- **Platform:** platform-neutral
- **Risk:** low. There is an ownership boundary with console-http and console-responses. This package owns the value shapes; HTTP owns framing, headers and error bodies.
- **Depends on:** PRM-09; PRM-12
- **Estimated size:** 600-800 lines of code; 500-650 lines of tests
- **Donor sources:** serve/server.py json_from_text 4909-4930, openai_chunks 4933-5008, openai_collect 5204-5246, anthropic_events 5250-5314, anthropic_collect 5317-5343; serve/frontend.py ToolCall.to_openai 808-816.

**Behaviors to reproduce**

- OpenAI stream: first chunk delta {role:assistant, content:''}; reasoning goes to delta.reasoning_content; content to delta.content; tool_start produces tool_calls [{index, id, type:function, function:{name, arguments:''}}] (with namespace plus bare name for namespaced DeepSeek calls); tool_args produces [{index, function:{arguments}}]; a final tool_call already streamed is skipped, otherwise sent whole with the next index. Chunk envelope {id: 'chatcmpl-'+hex24, object:'chat.completion.chunk', created, model, choices:[{index:0, delta, finish_reason}]}.
- finish_reason is 'tool_calls' when at least one call was sent and finish is stop; cancel becomes stop; others pass through. The last chunk carries usage {prompt_tokens, completion_tokens, total_tokens, prompt_tokens_details.cached_tokens} and optional timings.
- JSON mode (response_format json_object/json_schema): content is held and one chunk with json_from_text(all) is sent at the end (the whole text if it parses, else the first ```json fence, else the first object/array via raw_decode, else the text unchanged).
- Pings become None (an SSE comment ': keep-alive' in console-http) or, with return_progress and stream, a chunk with prompt_progress. MCP items become chunks with an empty delta and the web-app field (named per the open question). Logprobs are carried per chunk when asked.
- openai_collect folds chunks: message {role, content or null, reasoning_content when non-empty, tool_calls merged by index}, with the same usage. Non-streaming is always built by folding the stream.
- Anthropic stream: message_start ('msg_'+hex24); one content block per run of the same kind (thinking with thinking_delta and an empty signature; text with text_delta; tool_use per call with id, qualified name and input_json_delta fragments); message_delta with stop_reason tool_use / stop_sequence / end_turn (stop or cancel) / max_tokens (length), stop_sequence and usage {input_tokens minus cached, cache_read_input_tokens, output_tokens}; message_stop. anthropic_collect folds to the Messages response.

**Parity tests**

test_tools.py HttpToolCalls (2, shape assertions; transport in PRM-17), ClientStops (stop_sequence/stop_reason shape), JsonMode (json_from_text cases). test_ds41_conformance.py ResponseSerialization (2). test_server.py ClientShapes (4, Anthropic shape assertions). Golden JSON of event sequence to chunk list for at least 20 scripted runs.

**Definition of done**

All shape tests pass. Fold-equals-collect is property-tested. The documented chunk and event schemas are published in specs/022-*/contracts/ as part of the UI-to-server contract the Phase 2 front end will target.

<a id="prm-17"></a>
### PRM-17 End-to-end prompt and output parity suite on the fake backend, plus the PRM test map and contracts

- **Milestone:** M10
- **Rust target:** console/crates/pulsar-console/tests/prm_e2e_*.rs (integration tests) plus specs/022-*/parity/prm-test-map.md and specs/022-*/contracts/{prompting.md, parser-events.md, output-pipeline.md, thinking-and-loop-guard.md}
- **Platform:** platform-neutral
- **Risk:** medium. Timing depends on the other subsystems landing their HTTP and core pieces. Keep it as the last PRM package and let the lead schedule it after console-http's chat routes exist.
- **Depends on:** PRM-16; PRM-15; PRM-14; PRM-13; capability: console-http routes for /v1/chat/completions, /v1/messages, /tokenize, /detokenize, /api/tokens, /api/thinking-budget, /health; capability: console-core generation loop executing PRM-12 Directives and the PRM-13/PRM-14 slice controllers; capability: console-engine fake backend and line-protocol fake engine process
- **Estimated size:** 250-400 (test support) lines of code; 1200-1600 lines of tests
- **Donor sources:** All PRM sources; HTTP-level tests in serve/test_tools.py (HttpToolCalls, ClientStops over HTTP), serve/test_loop_guard.py Http, serve/test_glm_dsa_serve.py HistoryReuse/WebAppHistory/ContractTestOnTheFake, serve/test_glm_dsa_think_budget.py WebChat/McpLoop, serve/test_server.py PromptProgressStream (shape part), serve/test_deepseek_tool_block.py (HTTP parts).

**Behaviors to reproduce**

- Drives the real HTTP server (console-http) with the deterministic fake engine (console-engine) and synthetic tokenizers for every family, for both dialects, streaming and non-streaming, checking that recorded engine prompts (ids), engine sampling keys and client-visible chunks match the expectations derived in PRM-05 through PRM-16.
- Also drives the line-protocol adapter against a fake engine process for at least one budget and one loop-guard scenario, so the GEN keys (think_budget, think_end, think_soft, think tables, penalty overrides) reach the wire.
- prm-test-map.md lists every test method of the Maya files cited by PRM-01 to PRM-16 (about 330 methods) with the Rust test that re-expresses it, or a reason (another subsystem's ownership, hardware, or an approved deviation).
- Contracts document the normalized message form, the template-kwargs contract, the parser event stream, the Directive interface, the thinking-budget settings API and the loop-guard switches, for the Phase 2 Rust/WASM front end and the other console crates.

**Parity tests**

test_tools.py HttpToolCalls (2). test_loop_guard.py Http (1). test_glm_dsa_serve.py HistoryReuse (2), WebAppHistory (4), ContractTestOnTheFake (1). test_glm_dsa_think_budget.py WebChat (3) and McpLoop (1, shared with console-mcp). test_deepseek_tool_block.py (HTTP parts). Plus the cross-check of the full map.

**Definition of done**

The e2e suite passes in CI with CONSOLE_REQUIRE_VENDOR=1 and the pinned project-maya checkout. The test map accounts for every cited Maya test method with no unexplained gaps. The contracts are reviewed and linked from specs/022-*/spec.md. Every claim is labelled synthetic-backend only.
