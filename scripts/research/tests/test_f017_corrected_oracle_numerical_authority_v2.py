from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RESEARCH = ROOT / "scripts/research"


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
