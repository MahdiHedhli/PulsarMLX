# F017 numerical capability closure — Gemini cycle 1

Use a fresh `gemini-3.1-pro-high` session at high effort. Review exact committed bytes at `4f84232c65c047d3da4d3337d071d28ef59ffc30` on branch `feat/017-rust-native-inference-runtime`. Repository evidence outranks this request. Work read-only. Do not access original checkpoint shards, mint Event 04 authority, create Event 04 state, execute a real oracle, or execute P1 attempt 2.

Independently attack:

1. Reproduce F5-R4: `_backend = np; _backend.memmap(...)`, and confirm the old v2 policy accepted it while the new semantic policy rejects it.
2. Attack alternate NumPy and MLX import aliases, module aliases, chained aliases, destructuring, containers, class attributes, closures, defaults, lambdas, comprehensions, returns, yields, and member aliases.
3. Attack `getattr`, module `__dict__`, `__getattribute__`, `globals`, `locals`, `vars`, `__import__`, importlib-style surfaces, and multi-depth attribute chains.
4. Verify semantic module identity comes from imports rather than local spellings, and exact import census is only defense in depth.
5. Verify approved NumPy/MLX members and context classes match actual committed uses and reject member transport.
6. Attack receiver provenance through direct parameters, aliases, containers, closures, unknown objects, and prohibited protocol methods.
7. Verify the primary analyzer is fixed-point, conservative, fail-closed, scope-aware, and covers all stated binding forms.
8. Verify the independent structural checker does not import the primary analyzer.
9. Verify runtime NumPy/MLX proxies and recursive bytecode audit corroborate the static policy.
10. Inspect all 170 mutations for substantive coverage and no unexpected passes.
11. Verify numerical contract v3 binds the exact capability authorities and pure-core bytes remain unchanged.
12. Verify requalification v3 reruns 24 historical-equivalence cases, seeds 18101–18112, expanded seeds 17018–17023, all 11 formats, 44 decoder cases, 16 numerical mutations, target-adapter repetitions, and capability mutations without original-checkpoint access.
13. Verify FULL_NATIVE run `32673073054` is exact-head, passes required native jobs, and has zero required native skips.

Classify findings as `MATERIAL`, `NON_MATERIAL_REQUIRED`, or `DEFENSE_IN_DEPTH`. State whether any finding requires formula, threshold, methodology, original-checkpoint, or independence changes.

Required advisory verdict, exactly one:

- `ACCEPT`
- `REJECT`

Confirm: formulas unchanged; thresholds unchanged; original checkpoint access zero; Event 04 authorization absent; Event 04 unexecuted; real primary/secondary executions zero; P1 attempt 2 absent; historical ledger 175.
