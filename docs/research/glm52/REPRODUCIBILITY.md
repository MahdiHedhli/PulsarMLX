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

## Protocol freeze

Numerical tolerances and stop conditions live in
`docs/research/glm52/EXPERIMENT_PROTOCOL.md` and must match the version
cited by evidence records.
