# Bounded host reproduction v1
From repository root, using existing Python 3 and no installs:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s scripts/research/tests -p test_glm53_native_preparation_model_state_v1.py -v
PYTHONDONTWRITEBYTECODE=1 python3 -O -m unittest discover -s scripts/research/tests -p test_glm53_native_preparation_model_state_v1.py -v
git diff --check
```
No imports of MLX, no checkpoints/GPU and no workspace Cargo tests. Test suite
imports only stdlib, this package and retained stdlib candidate.py. Exact logs,
source manifest, review capsule/response and handoff are in private audit.
