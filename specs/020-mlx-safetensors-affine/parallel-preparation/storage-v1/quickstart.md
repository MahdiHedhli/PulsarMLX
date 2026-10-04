# Quickstart
From assigned worktree, with existing Python 3 (no installs):

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s scripts/research/tests -p test_glm53_native_preparation_storage_v1.py -v
git diff --check
python3 -c "from pathlib import Path; d=Path('specs/020-mlx-safetensors-affine/parallel-preparation/storage-v1'); assert all((d/p).is_file() for p in ('spec.md','plan.md','tasks.md','contracts/interface.md'))"
```

Expected: all targeted synthetic tests pass; diff check passes; direct artifact
inspection proves required spec/plan/tasks/interface files exist. Tests create no on-disk payload, read no models,
import no MLX and call no native/GPU runtime. See validation.md for actual evidence
and handoff.md for open production dependencies and the private audit location
containing exact source/capsule hashes and review receipts.

Use direct inspection here: normal check-prerequisites.sh persists the shared
.specify/feature.json. Do not run it under this lane ownership. The earlier
incident was restored exactly and is retained in the private audit.
