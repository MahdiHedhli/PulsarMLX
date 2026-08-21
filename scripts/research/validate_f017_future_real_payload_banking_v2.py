#!/usr/bin/env python3
"""Schema-driven enforcement of future same-commit F017 payload banking."""

from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess

try:
    from scripts.research.f017_real_payload_event_detector_v2 import detect, EventDetectionError
except ModuleNotFoundError:
    from f017_real_payload_event_detector_v2 import detect, EventDetectionError

ROOT = Path(__file__).resolve().parents[2]
BASE = "039a43ba8f41b755214f69117b0fc8cd15c05ee5"
LEDGER = "docs/architecture/reviews/evidence/f017-real-payload-access-ledger-v2.json"


class BankingError(RuntimeError):
    pass


def git(root: Path, *args: str, binary: bool = False):
    value = subprocess.check_output(["git", *args], cwd=root)
    return value if binary else value.decode().strip()


def terminal_count(raw: bytes) -> int:
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise BankingError(f"duplicate ledger key: {key}")
            out[key] = value
        return out
    value = json.loads(raw, object_pairs_hook=unique)
    count = value.get("cumulative_tensor_payloads")
    if type(count) is not int:
        raise BankingError("ledger terminal count must be strict integer")
    return count


def validate(root: Path, head: str = "HEAD") -> dict:
    commits = git(root, "rev-list", f"{BASE}..{head}").splitlines()
    advancing_commits = 0
    for commit in commits:
        changed = git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", commit).splitlines()
        events = []
        for rel in changed:
            if not rel.startswith("docs/architecture/reviews/evidence/") or not rel.endswith(".json"):
                continue
            try:
                raw = git(root, "show", f"{commit}:{rel}", binary=True)
                event = detect(raw)
            except (subprocess.CalledProcessError, EventDetectionError) as exc:
                raise BankingError(f"event discovery failed at {commit}:{rel}: {exc}") from exc
            if event is not None:
                events.append((rel, event))
        if len(events) > 1:
            raise BankingError(f"ambiguous multiple advancing events in {commit}")
        if not events:
            continue
        advancing_commits += 1
        if LEDGER not in changed:
            raise BankingError(f"advancing event lacks same-commit ledger: {commit}")
        ledger_raw = git(root, "show", f"{commit}:{LEDGER}", binary=True)
        if terminal_count(ledger_raw) != events[0][1].ledger_after:
            raise BankingError(f"same-commit ledger not receipt-derived: {commit}")
    return {
        "result": "PASS",
        "head": git(root, "rev-parse", head),
        "detector": "SCHEMA_AND_SEMANTIC_TYPE_NOT_FILENAME",
        "advancing_commits": advancing_commits,
        "ledger": LEDGER,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--head", default="HEAD")
    args = parser.parse_args()
    print(json.dumps(validate(args.root.resolve(), args.head), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
