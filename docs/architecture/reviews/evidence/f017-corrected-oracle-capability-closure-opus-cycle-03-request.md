# F017 capability closure — Opus cycle 03

Review exact committed bytes at `a49a906c9f0e29429cb6101c26b5b7f334fb14bd` in a detached read-only worktree. This is a fresh numerical capability review after cycle-02 finding `N6-R1`.

Independently rerun the exact ancestor-package bypass:

```python
import mlx
_f = mlx.core.savez
def probe(a):
    return _f("out.npz", a)
```

Attack alternate package aliases, descendant imports, all relative-import shapes, module/member transport, containers, closures/defaults, receiver provenance, dynamic reflection, and mutation-oracle quality. Verify both independent analyzers reject the ancestor/relative representations and that generated authorities are exact and CI-enforced. Inspect all 187 mutations and their expected rejection classes.

Confirm no numerical formula, methodology, threshold, pure-core byte, historical-equivalence output, or target-adapter output changed; original-checkpoint access remains zero. Inspect numerical contract v3 and exact-head FULL_NATIVE run `32676155739`.

Classify findings as `BLOCKING`, `NON_BLOCKING_REQUIRED`, or `DEFENSE_IN_DEPTH`. Both BLOCKING and NON_BLOCKING_REQUIRED prevent acceptance. Return exactly one final verdict: `ACCEPT_CORRECTED_ORACLE_NUMERICAL_AUTHORITY_SUPERSESSION` or `REJECT`. No conditional acceptance. Do not write or modify repository files.
