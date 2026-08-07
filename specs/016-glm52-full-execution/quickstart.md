# Quickstart: 016-glm52-full-execution

## When disk-blocked (current)

```sh
# Inspect formal admission result
python3 -c "import json;print(json.load(open('docs/validation/glm52-disk-admission.json'))['admission_result'])"

# Free space (internal only)
python3 -c "import shutil;u=shutil.disk_usage('/');print(f'free_GiB={u.free/1024**3:.2f}')"
```

Do **not** start download until admission is `passed`.

## When unblocked

```sh
export PULSARMLX_GLM_GGUF=/path/to/final/GLM-5.2-UD-IQ2_XXS  # file or shard dir
# atomic download → validate size/hash → set env → run correctness ladder
# (commands will be filled as implementation lands)
```

## Qwen baseline (must remain green)

```sh
git rev-parse HEAD
git describe --tags --exact-match v0.2.0-qwen30b-e2e-research 2>/dev/null || true
# evidence under docs/research/raw/009…015 and claims ledgers CLAIMS_LEDGER_00x.md
```
