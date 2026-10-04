# Reproducible host-only validation

Run from isolated repository root with system Python3, no installs. All inputs public synthetic, no MLX import. Standard unittest assertions remain active under -O. Frozen storage audit-based mutant requires normal mode only.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s scripts/research/tests -p test_glm53_native_preparation_model_state_v1.py -v
PYTHONDONTWRITEBYTECODE=1 python3 -O -m unittest discover -s scripts/research/tests -p test_glm53_native_preparation_model_state_v1.py -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s scripts/research/tests -p test_glm53_native_preparation_storage_v1.py -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s scripts/research/tests -p test_glm53_host_adapter_v1.py -v
PYTHONDONTWRITEBYTECODE=1 python3 -O -m unittest discover -s scripts/research/tests -p test_glm53_host_adapter_v1.py -v
python3 - <<'PYBUILD'
from pathlib import Path
paths = sorted(Path('scripts/research/glm53_flash/host_adapter_v1').glob('*.py'))
paths += [Path('scripts/research/tests/test_glm53_host_adapter_v1.py')]
if len(paths) < 3:
    raise RuntimeError('missing adapter/test/oracle source')
for path in paths:
    compile(path.read_bytes(), str(path), 'exec')
print('offline in-memory compile PASS', len(paths))
PYBUILD
```

The compile command parses/compiles but does not execute/import code and writes no bytecode. It is the appropriate build check for this Python-only slice, not a native build. Do not use py_compile/compileall. Capture exact commands/stdout/stderr/exit codes in owned attempt audit. All commands above are prospective until receipts exist. Retained counts model16+16/storage29; new population P01–P11 includes subcases/mutants listed in test-population and literal-fixtures.

Constitution-compliance check: PASS as prospective host recipe under Governance lines166–168, principles I/III/X/XII. No Rust changes, no workspace/GPU/MLX runs, no cross-platform/native claim.
