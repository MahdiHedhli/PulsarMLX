# F017 V8 Descriptor Type-Safety Design Closeout — Opus Cycle 01

Reviewed the exact committed bytes at `73cc8653` in the read-only detached worktree. All execution was done against a byte-identical `git archive` extraction in `/tmp` scratch (verified identical before and after, now removed); the review worktree is unmodified at `73cc8653`, working tree clean. No original checkpoint shard was accessed, no Event-04 authority minted, no Event 04 executed, no P1 attempt 2 executed.

## Independent reconstruction of C7-N1 and C7-N2

I built a coherent-forgery harness independently of the committed suite (full dependency rehash plus downstream restatement propagation, so the forged package is internally consistent and the descriptor path is genuinely reached — my first attempt without restatement propagation tripped a downstream equality check and masked the defect).

Against the **pre-repair** validator (`ab3eeb56`, `check_f017_transitive_artifact_closure_v8.py` sha256 `28a2a974f1eb…`, matching `validator_starting_sha256` in the banked reproduction):

- `mode = 0o1100644` and `mode = 65536` → `OverflowError: mode out of range`. Also 2^16, 2^17, 2^31. Values ≥ 2^32 already gave `ValueError`, confirming the banked `old_behavior` string exactly.
- Non-dict descriptor elements (`None`, int, bool, float, str, list, nested list — at both index 0 and index 4) → `AttributeError: '…' object has no attribute 'get'`.
- Unhashable lease IDs (list, dict, nested list, list-of-str) → `TypeError: cannot use 'list' as a set element`.

Both findings reproduce exactly as banked. The reproduction evidence is authentic, not asserted.

Against the **repaired** validator, 198 adversarial cases: **195 → stable `ValueError`**, 0 `OverflowError`/`AttributeError`/`TypeError`/`KeyError`/`OSError`. The 3 non-rejections are `inode`/`mtime_ns`/`ctime_ns` = 2^70, which the declared scalar contract explicitly permits (`minimum: 0`, no maximum) — contract-conformant, not a defect.

## Ordering — both preconditions proven, statically and dynamically

Instrumented `stat.S_ISREG` to abort if called outside the 16-bit domain:

- All 17 out-of-domain modes (`0o1100644`, `65536`, 2^16…10^40, negatives, bool, float, str, `None`, list, dict) → `ValueError` with **`S_ISREG_calls = 0`**.
- In-domain non-regular (`0o40755`) → `S_ISREG` reached, `ValueError: mode is not regular`. The guard is live, not dead code.

AST statement ranking confirms in both modules: list guard → dict guard → key census → int guard → 16-bit bound → `S_ISREG` → string guards → duplicate-detection set comprehensions.

For `set()`: hash-bomb objects (`__hash__` raising) placed in `lease_id`, `device`, and `inode` all yield `ValueError` and never reach set construction. `mode_semantic_precondition` and `lease_deduplication_precondition` both hold.

## Type-safety breadth

- **Mapping subclasses** — `dict` subclass, `OrderedDict`, `defaultdict`, `Counter`, `UserDict`, `ChainMap`, `MappingProxyType`, `collections.abc.Mapping`, a duck-typed `.get`/`__getitem__` decoy, `SimpleNamespace`: all `ValueError`. Exact-type discipline holds.
- **Non-list collections** — `list` subclass, tuple, generator, bytes, bytearray, range, dict: all `ValueError`.
- **Every unhashable/exotic lease-ID class** (23) — list, dict, set, frozenset, bytearray, bytes, memoryview, `__hash__ = None`, raising `__hash__`, hostile `__eq__`, `str` subclass, tuple, `None`, int, float, complex, bool, object, type, lambda, enum, generator: all `ValueError`.
- **Grammar and duplicates** — empty, whitespace, lowercase, slash, leading/trailing hyphen, 129 chars, NUL, newline, non-ASCII, underscore, all four forbidden markers, duplicate and desynced lease IDs: all `ValueError`.

## Independent checker and import separation

Genuine independence confirmed beyond the committed substring test: a fresh interpreter importing only the checker loads **zero** sibling modules; AST import set is stdlib-only (`argparse`, `json`, `re`, `stat`, `pathlib`); no `importlib`/`__import__`/`exec`/`eval`/`sys.path` escape hatches. Adversarially: 132 mutations plus 19 envelope attacks (non-dict envelope, non-dict payload, malformed JSON, BOM, UTF-16, NUL bytes, 200-deep nesting, duplicate keys) and 5 filesystem attacks (missing file, directory, dangling symlink, mode 000, missing root) — **all `ValueError`**, no raw OS errors leak.

## Committed suites and regression

All rerun and passing: 15 tests, **256 mutations** (179 static + 77 runtime), 48 symbolic outcomes, 95 artifacts, 94 DAG edges, closure depth 48, 1175 strict-rank edges, 25 safety invariants, path timing 95/95 = 100%, five-descriptor continuity and ordinals [2,3,4,5,6] on both consumers, `path_reopen_count = 0`, descriptor release closure enforced (deleting any release or continuity artifact → census `ValueError`; four descriptors → `ValueError`). Banked qualification is **byte-identical** to a fresh run. All 29 authority bindings verify; numerical authority SHAs unchanged (`numerical_contract 84ff9ba0…`, `numerical_requalification 5a025780…`).

Prior required findings re-probed directly, all still enforced: C5-B1 (success/failure classification enum), C5-N1 (unknown-lease counter cannot discharge live-lease obligation), C5-N2 (identifier classes pairwise distinct), C6-N1 (mode out-of-domain), C7-N1, C7-N2. No regression.

`active_live_generation = NONE`, `implementation_phase_entered = false`, `event_04_authorization_created = false`, `event_04_executed = false`, `p1_attempt_2_executed = false`. Audit-hook instrumentation over the full validate + 48-outcome symbolic construction: **0 opens of any GLM-5.2 shard**; all I/O confined to the repo tree and temp dirs. The design derives descriptor sizes from checkpoint *metadata*, never the shards — V8 implementation may proceed without original checkpoint access.

## Findings

No `BLOCKING`. No `NON_BLOCKING_REQUIRED`.

**`DEFENSE_IN_DEPTH`**

1. **Declared validation order contradicts both implementations.** The scalar contract lists `LEASE_ID_GRAMMAR` at index 5 and `MODE_REGULAR_FILE_SEMANTIC` at index 6; both checkers evaluate mode-regular first (verified: a descriptor violating both yields `descriptor mode is not regular`). Nothing compares `validation_order` against the implementation — the validator only diffs the contract document against a hardcoded dict. No safety impact: both paths raise `ValueError`, and both declared *preconditions* hold.

2. **`EXACT_CONSTANT` conflates `False`↔`0` and `True`↔`1`** across 372 fields (`payload_constants` and the `EXACT_CONSTANT` rule both use `!=`). A forged package may bank JSON `false` where the schema says integer `0`. No escalation is possible — substitution is meaning-preserving in both directions (`original_checkpoint_access` cannot be made nonzero; `True` = 1 ≠ 0 is rejected), the capsule's `event_04_executed` check uses strict `is not False`, and `NONNEGATIVE_INTEGER`/`TYPE` correctly reject bools. Pre-existing, byte-identical in `ab3eeb56`; outside the descriptor scalar contract's declared scope, whose 7 integer fields I confirmed do enforce `EXACT_INT_NOT_BOOL`.

3. **13 new C7 qualifier fields are bare literals**, gated only indirectly by `check=True` on the test subprocess. `c7_n1_reproduced`/`c7_n2_reproduced` assert *pre-repair* behavior that nothing in the suite can re-derive. I verified both true independently against `ab3eeb56`. Same class as the already-accepted `CYCLE_CLAIMS_LITERAL` / `MUTATION_ACCOUNTING_PARTIALLY_LITERAL`.

4. **Independent checker replicates the same grammar regex string** (CPython's `re` cache even returns the same compiled object). Module-level independence is real; a defect in the grammar itself would replicate across both.

5. **`inode`/`mtime_ns`/`ctime_ns` are unbounded above** (2^70 accepted) while `mode` is domain-bounded. Contract-conformant, but the asymmetry is a hardening opportunity.

6. **Import-separation test is a source substring scan** and would not catch a dynamically constructed import. I verified actual runtime independence separately.

## Verdict

`ACCEPT_CHECKPOINT_IDENTITY_CAUSAL_DESIGN_V8_FOR_IMPLEMENTATION`
