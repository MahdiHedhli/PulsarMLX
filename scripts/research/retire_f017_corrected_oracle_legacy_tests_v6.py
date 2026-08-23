#!/usr/bin/env python3
"""Replace current-tree legacy execution tests with immutable-Git tests."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TESTS = (
    "scripts/research/tests/test_f017_corrected_oracle_preaccess.py",
    "scripts/research/tests/test_f017_corrected_oracle_memory_preflight_v2.py",
    "scripts/research/tests/test_f017_corrected_oracle_instantiability_v3.py",
)
TEMPLATE = '''from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_historical_corrected_oracle_authority_is_validated_from_git() -> None:
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/research/validate_f017_historical_corrected_oracle_authorities_v6.py")],
        cwd=ROOT,
        check=True,
    )


def test_legacy_surface_is_not_current_execution_authority() -> None:
    validator = (ROOT / "scripts/research/validate_f017_corrected_oracle_access_v2.py").read_text()
    assert "HISTORICAL_ONLY" in validator
    assert "os.pread" not in validator
'''


def main() -> int:
    for relative in TESTS:
        path = ROOT / relative; temporary = path.with_name(path.name + ".retiring")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(TEMPLATE.encode()); output.flush(); os.fsync(output.fileno())
        os.replace(temporary, path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
