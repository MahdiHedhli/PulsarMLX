#!/usr/bin/env python3
"""Generate the Sequence 11 live-GO constants from frozen requirements."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS = (
    ROOT
    / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event06-live-go-call-path-requirements-v1.json"
)
OUTPUT = ROOT / "scripts/research/f017_event06_live_go_contract_v3.py"


def render() -> str:
    value = json.loads(REQUIREMENTS.read_text(encoding="utf-8"))
    live = value["live_go"]
    approval = value["operator_approval"]
    identity = value["event_identity_plan"]
    return """\"\"\"Generated constants for the Event 06 V12 live-GO call path.\"\"\"

from __future__ import annotations

from typing import Final

# This block is emitted directly from canonical JSON. Keeping each authority
# value on one line makes generator drift a plain byte comparison.
# fmt: off
REQUIREMENTS_RELATIVE: Final = {requirements!r}
LIVE_GO_SCHEMA: Final = {live_schema!r}
LIVE_GO_DECISION: Final = {decision!r}
LIVE_GO_SCOPE: Final = {scope!r}
LIVE_GO_FIELDS: Final = {live_fields!r}
LIVE_GO_TYPES: Final = {live_types!r}
APPROVAL_SCHEMA: Final = {approval_schema!r}
APPROVAL_FIELDS: Final = {approval_fields!r}
APPROVAL_TYPES: Final = {approval_types!r}
EVENT_IDENTITY_SCHEMA: Final = {identity_schema!r}
EVENT_IDENTITY_FIELDS: Final = {identity_fields!r}
EVENT_IDENTITY_TYPES: Final = {identity_types!r}
AUTHORITY_DAG: Final = {dag!r}
# fmt: on
""".format(
        requirements=REQUIREMENTS.relative_to(ROOT).as_posix(),
        live_schema=live["schema"],
        decision=live["decision"],
        scope=value["scope"],
        live_fields=tuple(live["required_fields"]),
        live_types=live["exact_types"],
        approval_schema=approval["schema"],
        approval_fields=tuple(approval["required_fields"]),
        approval_types=approval["exact_types"],
        identity_schema=identity["schema"],
        identity_fields=tuple(identity["required_fields"]),
        identity_types=identity["exact_types"],
        dag=tuple(value["authority_dag"]),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = render()
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_text(encoding="utf-8") != expected:
            raise SystemExit("generated live-GO constants are stale")
        print("live-GO constants: PASS")
        return 0
    OUTPUT.write_text(expected, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
