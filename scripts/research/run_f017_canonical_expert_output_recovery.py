#!/usr/bin/env python3
"""Single fixed production entrypoint for the reviewed F017 recovery event."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.research.f017_canonical_expert_output_production import main


if __name__ == "__main__":
    raise SystemExit(main())
