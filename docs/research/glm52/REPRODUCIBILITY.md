# GLM-5.2 Reproducibility

## Machine class

- Apple Silicon M1 Ultra
- 128 GB unified memory
- Internal SSD only (no external RAID for this feature)

## Software pin

- Repository commit: see claim / evidence `source_commit`
- Python: project `.venv`
- MLX: version recorded in environment snapshots when available
- Upstream Pulsar research clone pin: `17dac547898e0e65bb073f13444708daf68edc3d` (architecture donor only)

## Checkpoint

```sh
export PULSARMLX_GLM_GGUF="$HOME/Models/PulsarMLX/GLM-5.2-UD-IQ2_XXS"
# verify docs/validation/glm52-checkpoint.json after acquisition
```

Do not commit weights. Do not publish private absolute paths in evidence.

## Clean-checkout (methodology / CI-safe)

```sh
git clone https://github.com/MahdiHedhli/PulsarMLX.git
cd PulsarMLX
git checkout main
# create venv, install deps per README
python -m pytest scripts/research/tests/ -q
# GLM checkpoint-free suite (when present):
python -m pytest scripts/research/tests/test_glm52_*.py -q
```

## Real-model Tier-3

```sh
export PULSARMLX_GLM_GGUF=/path/to/GLM-5.2-UD-IQ2_XXS
# Must fail clearly if unset or incomplete — never skip-pass
python scripts/research/glm52_gguf_catalog.py \
  --model "$PULSARMLX_GLM_GGUF" \
  --out /tmp/glm-c01.json \
  --source-commit "$(git rev-parse HEAD)"
```

### Exact-bit IQ2_XXS matrix qualification

```sh
export PULSARMLX_GLM_GGUF=/path/to/GLM-5.2-UD-IQ2_XXS
uv sync --frozen
uv run --frozen python scripts/research/qualify_iq2_xxs_numpy.py \
  --output docs/research/glm52/raw/f016-iq2-xxs-numpy-qualification-0001.json
python3 -m unittest discover -s scripts/research/tests \
  -p 'test_iq2_xxs_qualification_record.py' -v
```

The command requires a clean worktree and fails closed when the checkpoint
environment variable, complete matrix bytes, IQ2_XXS type, or exact-bit gate
is unavailable.

### Real MLX matrix boundary

```sh
export PULSARMLX_GLM_GGUF=/path/to/GLM-5.2-UD-IQ2_XXS
uv run --frozen python scripts/research/benchmark_glm52_matrix_boundary.py \
  --output docs/research/glm52/raw/f016-matrix-boundary-0001.json
python3 -m unittest discover -s scripts/research/tests \
  -p 'test_glm52_matrix_boundary_record.py' -v
```

### Complete routed expert

```sh
export PULSARMLX_GLM_GGUF=/path/to/GLM-5.2-UD-IQ2_XXS
uv run --frozen python scripts/research/benchmark_glm52_routed_expert.py \
  --output docs/research/glm52/raw/f016-routed-expert-0001.json
python3 -m unittest discover -s scripts/research/tests \
  -p 'test_glm52_routed_expert_record.py' -v
```

## Protocol freeze

Numerical tolerances and stop conditions live in
`docs/research/glm52/EXPERIMENT_PROTOCOL.md` and must match the version
cited by evidence records.
