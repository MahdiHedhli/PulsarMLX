# Quickstart: 016-glm52-full-execution

## Current optimization gate (checkpoint-free)

```sh
uv sync --frozen
uv run --frozen python -m unittest discover \
  -s scripts/research/tests -p 'test_iq2_xxs_numpy.py' -v
```

The real-matrix qualification is run only from a clean committed worktree,
after notifying `Mahdi-Dev` and confirming the admitted checkpoint, storage,
memory pressure, and competing load:

```sh
export PULSARMLX_GLM_GGUF=/path/to/final/GLM-5.2-UD-IQ2_XXS
uv run --frozen python scripts/research/qualify_iq2_xxs_numpy.py \
  --output docs/research/glm52/raw/f016-iq2-xxs-numpy-qualification-0001.json
```

P2 remains ineligible until exact-bit qualification and the bounded benchmark
ladder through P1 are committed.

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
