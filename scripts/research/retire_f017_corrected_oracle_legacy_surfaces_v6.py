#!/usr/bin/env python3
"""Mechanically replace superseded live surfaces with fail-closed tombstones."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HISTORICAL_COMMIT = "84f0d1dc3e60a4151329ed82773880951ee3e618"
SURFACES = {
    "scripts/research/validate_f017_corrected_oracle_access.py": "V1_LIVE_MINT",
    "scripts/research/execute_f017_corrected_oracle_event.py": "V1_COORDINATOR",
    "scripts/research/validate_f017_corrected_oracle_access_v2.py": "V2_LIVE_MINT",
    "scripts/research/execute_f017_corrected_oracle_event_v2.py": "V2_COORDINATOR",
    "scripts/research/validate_f017_corrected_oracle_access_v3.py": "V3_LIVE_MINT",
    "scripts/research/execute_f017_corrected_oracle_event_v3.py": "V3_COORDINATOR",
    "scripts/research/f017_corrected_oracle_primary_v3.py": "V3_PRIMARY_TARGET",
    "scripts/research/f017_corrected_oracle_secondary_v3.py": "V3_SECONDARY_TARGET",
}

TEMPLATE = '''#!/usr/bin/env python3
"""Historical-only tombstone installed by the F017 v6 supersession."""
from __future__ import annotations

HISTORICAL_COMMIT = {commit!r}
HISTORICAL_SURFACE = {surface!r}


def main() -> int:
    raise SystemExit(
        f"HISTORICAL_ONLY: {{HISTORICAL_SURFACE}} is retired; "
        f"reconstruct exact bytes from {{HISTORICAL_COMMIT}}; "
        "current live authority, target execution, checkpoint access, and state creation are prohibited"
    )


if __name__ == "__main__":
    raise SystemExit(main())
'''


def main() -> int:
    for relative, surface in SURFACES.items():
        path = ROOT / relative
        data = TEMPLATE.format(commit=HISTORICAL_COMMIT, surface=surface).encode()
        temporary = path.with_name(path.name + ".retiring")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
