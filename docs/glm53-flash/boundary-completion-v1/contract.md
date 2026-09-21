# Boundary completion contract

This successor leaves all 35 predecessor source files and their recorded results unchanged. It reuses the admitted CPython 3.14.6 arm64 environment: MLX/MLX-metal 0.32.2, NumPy 2.5.3, Jinja2 3.1.6 and MarkupSafe 3.0.3. Real operator claims remain wheel-observed, RELEASE_DECLARED_NOT_BUILD_VERIFIED. The exact upstream selector is an EXTRACTED_CAPSULE, not a full upstream import. GLM constructor/sanitize/cache, tokenizer, model and actual tools remain unexecuted.

## JSON contract and source correspondence

PipeNetwork a61a7c7d2fbdf3d218a9909365a24bd794f3a247 load.py lines 55–60 names mlx_vlm.utils.load_processor. At mlx-vlm 8d79dbcf82a7885ddfc56fb4a55440fa9c5dfb90, utils.py lines 23–24 and 1441–1444 name Transformers AutoProcessor. These files are read as text only; their model/processor loaders never execute.

Transformers cbc1651a032b923da7f4b44b3d0e6f68e6ba6b55 chat_template_utils.py lines 481–484 defines a tojson override using json.dumps with ensure_ascii=False, indent=None, separators=None and sort_keys=False; it returns ordinary str and avoids Jinja's extra HTML escaping. Exact source SHA is 3125114cf05646e7bc526ec30a6838da15bc9aa4591e42527e1012eaca3d276d. Existing CPython json.dumps/JSONEncoder source excerpts establish default comma-space/colon-space separators, insertion order, no indentation, JSON quote/backslash/control escapes, boolean/null literals and optional Unicode preservation. This pinned convention is not proof of the selected artifact's historical producer. Producer correspondence remains UNKNOWN.

The new research filter supports only ensure_ascii of exact bool type, default False. Other kwargs reject. Output is exact str; HTML characters are preserved as JSON permits. Finite JSON numbers only is a stricter research policy than json.dumps' permissive NaN default. Plain exact built-in dict/list/str/int/float/bool/None are admitted before serialization or rendering; subclasses and arbitrary objects/callables reject without invoking their methods. Depth<=16, nodes<=4096, each string<=32KiB, sum of string UTF-8 bytes<=64KiB, total serialized input<=64KiB, exact ints within +/-2^53-1, finite floats, messages<=16 and tools<=8. Cycles and invalid Unicode surrogate strings reject. Rendered output is counted during generation and capped at 16MiB by both adapter and supervisor. No filesystem loader or extra global is enabled. Only the existing loopcontrols and bounded range/namespace globals remain.

The declared renderer subset is text user/system/assistant messages, wrapped function declarations with safe fixed outer field names, and wrapped assistant function calls with mapping arguments. String argument values are emitted raw as the pinned template specifies; other JSON values use the filter. No tool result, media, arbitrary template, flattened tool-call form or string-encoded whole arguments object is promoted. Missing/malformed required fields reject by the research policy; StrictUndefined remains enabled. One standard-filter baseline error is banked separately before enabling the adapter. Literal JSON expectations and full template output expectations are banked independently of the candidate filter.

## New numerical domains and independent criteria

Normalization uses logits [-1,-0.5,0.5,1.5], bias [2,0,0,0], top_k=2, n_group=topk_group=1 and scale 2.5. Selected IDs are {0,3}, with sigmoid sum about 1.0865, measurably different from one. For each returned ID, unnormalized weight is 2.5*sigmoid(g_i), normalized weight divides by that selected sum. The kth selection margin exceeds 0.19. Require exact selected set, per-ID pairing, sum>1.08 and at least 0.01 maximum difference between normalization modes. This is generic evidence; the selected artifact remains norm=true.

Preserve predecessor tolerances: routing and SiLU atol4e-5/rtol4e-6, raw convolution atol2e-5/rtol2e-6. The predecessor 16u sigmoid engineering allowance (u=2^-24, not a library ULP promise) propagated through two positive scores with S>1.08 and scale2.5 stays below the routing budget. Kernel-one uses exact dyadic inputs |x|<=1.5 and weights |w|<=1: y[b,t,c]=x[b,t,c]*w[c,0,0], followed by independent scalar SiLU. Raw multiply error is bounded by u*1.5; the original broader raw/SiLU bounds are retained, not widened. All numeric inputs must be finite and FP32-representable in these explicit bounded domains.

Kernel-one input is [2,5,3], weights [3,1,1]; conceptual empty state is [B,0,C]. The successor state record carries that full shape plus empty values, preserving the otherwise missing channel dimension in empty Python lists. Test single token, prefix/chunks [2,1,2], interleaved streams and empty initial state. The predecessor research wrapper already uses :0 explicitly and is expected to match numeric/suffix-list values in a named diagnostic; no historical failure is invented. The deliberate -0 mutant retains the full input and must fail the exact state-shape/value comparison after a real operator evaluation. No production cache reset is claimed.

## Controls and changed edges

All eight accepted mechanisms are re-exercised through their real entries, plus forced normalization, wrong kernel-one suffix and a Unicode JSON semantic mutation. A frozen control table names the exact exception class, stable message predicate and whether numerical/render evaluation must occur. Numerical/byte mismatches use specific exception codes. Any other exception is HARNESS_FAILURE, never an intended detection. Test wrong-type and wrong-message classifiers explicitly. Every real control requires normal -> mutant -> restored with input/environment identity maintained. Code and criteria checkpoint before outputs; each repair creates a new checkpoint without altering historical results.

| Edge | Composition and scope |
| --- | --- |
| J1 | Typed inert data -> JSON filter -> exact JSON bytes/parser checks |
| J2 | Filter -> pinned template declarations/call arguments -> complete output/fragments |
| R1 | New non-symmetric logits -> exact selector -> per-ID scalar on/off weights |
| C1 | [B,T,C] + [B,0,C] -> real Conv1d -> raw/SiLU and explicit empty state |
| C2 | Returned state -> prefix/chunk/interleaved successor call |
| M1 | Real guard/operator/renderer error -> expected-mechanism classifier -> counted result |
| M2 | Preserved fictional expert values + source selector -> ID/weight association check |

All new code/fixtures use repository MIT terms. Upstream source remains external and attributed through exact locks/licenses. Shared source-map-tiny-parity stays DRAFT and unchanged. FLSH-PROTECTION-01 remains open: ownership ignored and no encryption; these checks are not an OS or confidentiality boundary.
