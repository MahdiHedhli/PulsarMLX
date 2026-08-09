# Quickstart: 016-glm52-full-execution

## Current optimization gate

```sh
.venv/bin/python -m pytest -q \
  scripts/research/tests/test_glm52_checkpoint_free.py \
  scripts/research/tests/test_glm52_cache_simulator.py \
  scripts/research/tests/test_glm52_expert_cache_runtime.py
.venv/bin/python scripts/research/glm52_cache_simulator.py --check
```

P2 is permitted only from a clean committed worktree after notifying
`Mahdi-Dev` and passing live disk, memory-pressure, and competing-load checks.

## Tier-3 P2 command

```sh
export PULSARMLX_GLM_GGUF=/path/to/final/GLM-5.2-UD-IQ2_XXS  # file or shard dir
.venv/bin/python scripts/research/glm52_inference.py \
  --mode inference \
  --n-new 2 \
  --cache-gib 16 \
  --cache-policy decoded_shared_only \
  --out docs/research/glm52/raw/f016-inference-p2-token2.json
```

Pass requires exact IDs `[9703, 21615, 220]`, zero CPU fallbacks, MLX GPU
identity, a non-critical resource record at every completed stack, and at least
228 decoded shared-cache hits in the first generated-token stack. Do not run
the eight-token gate unless P2 passes.

## Qwen baseline (must remain green)

```sh
git rev-parse HEAD
git describe --tags --exact-match v0.2.0-qwen30b-e2e-research 2>/dev/null || true
# evidence under docs/research/raw/009…015 and claims ledgers CLAIMS_LEDGER_00x.md
```
