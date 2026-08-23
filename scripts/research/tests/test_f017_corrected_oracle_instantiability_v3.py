from __future__ import annotations

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
