# F017 capability closure — Gemini cycle 03

Review exact committed bytes at `a49a906c9f0e29429cb6101c26b5b7f334fb14bd` on `feat/017-rust-native-inference-runtime`.

This is the repair for Opus cycle-02 finding `N6-R1`. Attack the semantic capability analyzers and determine whether ancestor-package imports or relative imports can still evade NumPy/MLX capability policy. Reproduce at minimum:

```python
import mlx
_f = mlx.core.savez
def probe(a):
    return _f("out.npz", a)
```

Also attack `import mlx as backend`, `from . import numpy`, `from .. import mlx`, and `from .backend import value`. Verify both the load-bearing value-flow analyzer and independent checker reject the relevant representations, and verify the 187-case mutation suite records intended rejection classes rather than accepting arbitrary exceptions.

Confirm that pure-core bytes, numerical formulas, methodology, thresholds, the 24 historical-equivalence cases, and target-adapter outputs remain unchanged; original-checkpoint access must remain zero. Inspect numerical contract v3 and exact-head FULL_NATIVE run `32676155739`.

Return a concise inline review with findings and exactly one advisory verdict: `ACCEPT` or `REJECT`. Do not write or modify repository files.
