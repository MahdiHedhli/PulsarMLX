from __future__ import annotations

import ast
import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RESEARCH = ROOT / "scripts/research"


def validator_module():
    path = RESEARCH / "validate_f017_corrected_oracle_numerical_authority_v2.py"
    spec = importlib.util.spec_from_file_location("f017_num_v2_validator", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_numerical_authority_bundle_passes() -> None:
    subprocess.run([sys.executable, str(RESEARCH / "validate_f017_corrected_oracle_numerical_authority_v2.py")], cwd=ROOT, check=True)


def test_pure_cores_have_no_checkpoint_capability() -> None:
    for name in ("f017_corrected_oracle_primary_numerics_v2.py", "f017_corrected_oracle_secondary_numerics_v2.py"):
        tree = ast.parse((RESEARCH / name).read_text())
        imported = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        assert not imported & {"os", "mmap", "pathlib", "argparse"}
        assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open" for node in ast.walk(tree))


def test_all_retired_surfaces_fail_closed() -> None:
    names = [
        "f017_corrected_oracle_primary.py", "f017_corrected_oracle_secondary.py",
        "validate_f017_corrected_oracle_access.py", "execute_f017_corrected_oracle_event.py",
        "validate_f017_corrected_oracle_access_v2.py", "execute_f017_corrected_oracle_event_v2.py",
        "validate_f017_corrected_oracle_access_v3.py", "execute_f017_corrected_oracle_event_v3.py",
        "f017_corrected_oracle_primary_v3.py", "f017_corrected_oracle_secondary_v3.py",
    ]
    for name in names:
        completed = subprocess.run([sys.executable, str(RESEARCH / name)], cwd=ROOT, text=True, capture_output=True)
        assert completed.returncode != 0
        assert "HISTORICAL_ONLY" in completed.stderr


def test_target_arithmetic_guard_includes_class_methods() -> None:
    module = validator_module()
    source = "class Target:\n    def matvec(self, value):\n        return value\n"
    assert "Target.matvec" in module.symbols(source)
    assert "matvec" in module.function_names(source)


def test_exact_file_binding_rejects_path_and_sha_mutations() -> None:
    module = validator_module()
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        path = root / "authority.json"
        path.write_bytes(b"{}\n")
        valid = {"path": "authority.json", "sha256": module.sha(path)}
        module.require_file_binding(valid, path, root)
        for mutation in (
            {**valid, "path": "other.json"},
            {**valid, "sha256": "0" * 64},
            {**valid, "extra": True},
        ):
            try:
                module.require_file_binding(mutation, path, root)
            except ValueError:
                pass
            else:
                raise AssertionError(f"binding mutation accepted: {mutation}")


def test_pure_core_import_policy_is_allowlist_not_denylist() -> None:
    module = validator_module()
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "core.py"
        accepted = "from __future__ import annotations\nimport math\ndef execute():\n    return math.sqrt(4.0)\n"
        path.write_text(accepted)
        module.validate_pure_core(path, "primary")
        escapes = (
            "import urllib.request\n",
            "import _ctypes\n",
            "import zipfile\n",
            "import runpy\n",
            "from . import os\n",
            "def f():\n    return builtins.__import__('os')\n",
            "def f():\n    return __builtins__['__import__']('os')\n",
        )
        for source in escapes:
            path.write_text(source)
            try:
                module.validate_pure_core(path, "primary")
            except ValueError:
                pass
            else:
                raise AssertionError(f"pure-core escape accepted: {source!r}")
