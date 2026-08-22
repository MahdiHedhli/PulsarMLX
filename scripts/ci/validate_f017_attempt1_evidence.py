#!/usr/bin/env python3
"""Retained-only validator for immutable F017 bounded-P1 attempt-1 evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Iterable


EXPECTED = {
    "docs/architecture/reviews/evidence/f017-native-bounded-p1-real-attempt-01-human-approval-v1.json": "3788fe3060f5d78002adc7f22f94e98c9163a09be1e71648bcade3bde65b3ec7",
    "docs/architecture/reviews/evidence/f017-native-bounded-p1-real-attempt-01-live-authorization-v1.json": "c1a81febcec0171a0aba63da44f645d630b7daca1b4031d52a4b3cecea6a42b7",
    "docs/architecture/reviews/evidence/f017-native-bounded-p1-real-attempt-01-owned-claim-v1.json": "35d95dacd3b0464c6f12d70adf318f60869b1d4366c04c8508be06948844b965",
    "docs/architecture/reviews/evidence/f017-native-bounded-p1-real-attempt-01-durable-start-v1.json": "35d95dacd3b0464c6f12d70adf318f60869b1d4366c04c8508be06948844b965",
    "docs/architecture/reviews/evidence/f017-native-bounded-p1-real-attempt-01-terminal-v1.json": "de5f918324048fec8e49d63a60d9db6ba536171f4e1ea0dae6f5e5ddfdf7a6ed",
    "docs/architecture/reviews/evidence/f017-native-bounded-p1-real-attempt-01-preauthorization-memory-v1.txt": "8bebdaef9e08ca12cdd4ecba3273cc964593974455cb2d1622ed7ec6d2d827f2",
    "docs/architecture/reviews/evidence/f017-native-bounded-p1-real-attempt-01-execution-evidence-v1.json": "c3dcc92cec8fde419bfdb437e0191a768fce8f48fc78b2e4b78171164caafb7b",
    "docs/architecture/reviews/evidence/f017-native-bounded-p1-native-event-ledger-v1.json": "24d8bd899cf6809387c40d6bd37d5b8f30a2056fa23a19e84bd4f2758305b5dd",
    "docs/architecture/reviews/evidence/f017-native-bounded-p1-real-attempt-01-banking-validation-v1.json": "384e468aec6c9a241db6417e49c80eb3a1251e28e6b7744ae2c60081bfb4c490",
    "docs/architecture/reviews/evidence/f017-native-bounded-p1-real-attempt-01-opus-review-request-v1.md": "12ff988feeaa7129b910154893907bd9a363ea0e942428333f4f0f57a0deba5c",
    "docs/architecture/reviews/evidence/f017-native-bounded-p1-real-attempt-01-opus-exact-response-v1.json": "b235bbb8145867fd606cc9e94fdf6fb8b6b5c2531ec466b1e17f11764d752a99",
    "docs/architecture/reviews/evidence/f017-native-bounded-p1-real-attempt-01-opus-normalized-result-v1.json": "b5259d3487c15a782f172e93b3bc92f2b0dc52fd7500313a4b4c75097a2df217",
}
HISTORICAL_COMMIT = "f2a7aa38c96b85cf7939c8ed653076732f066222"
HISTORICAL_PATH = "docs/architecture/reviews/evidence/f017-real-payload-access-ledger-v2.json"
HISTORICAL_SHA = "aa98f5cc7f1cfae1eb49a9bc64dbefec1d6ef9ccae1504a1aa8879a8edf22e3e"


class EvidenceError(RuntimeError):
    pass


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_pairs)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise EvidenceError(f"invalid JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise EvidenceError(f"top-level object required: {path}")
    return value


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def validate(repository: Path) -> dict[str, Any]:
    repository = repository.resolve(strict=True)
    documents: dict[str, dict[str, Any]] = {}
    for relative, expected in EXPECTED.items():
        path = repository / relative
        _require(path.is_file() and not path.is_symlink(), f"missing/non-regular {relative}")
        _require(sha256(path) == expected, f"immutable attempt-1 SHA mismatch: {relative}")
        if path.suffix == ".json":
            documents[relative] = load_json(path)

    approval = documents[next(path for path in EXPECTED if path.endswith("human-approval-v1.json"))]
    authorization = documents[next(path for path in EXPECTED if path.endswith("live-authorization-v1.json"))]
    claim = documents[next(path for path in EXPECTED if path.endswith("owned-claim-v1.json"))]
    start = documents[next(path for path in EXPECTED if path.endswith("durable-start-v1.json"))]
    terminal = documents[next(path for path in EXPECTED if path.endswith("terminal-v1.json"))]
    evidence = documents[next(path for path in EXPECTED if path.endswith("execution-evidence-v1.json"))]
    native_ledger = documents[next(path for path in EXPECTED if path.endswith("native-event-ledger-v1.json"))]
    review = documents[next(path for path in EXPECTED if path.endswith("opus-normalized-result-v1.json"))]

    auth_id = "F017-NATIVE-BOUNDED-P1-AUTHORIZATION-1"
    attempt_id = "F017-NATIVE-BOUNDED-P1-ATTEMPT-1"
    for label, document in (("approval", approval), ("authorization", authorization), ("claim", claim), ("start", start), ("terminal", terminal)):
        _require(document["authorization_id"] == auth_id, f"{label} authorization mismatch")
        _require(document["attempt_id"] == attempt_id, f"{label} attempt mismatch")
    _require(claim == start, "claim/start bytes or values diverge")
    _require(terminal["state"] == "TERMINAL_FAILURE_NO_RETRY", "terminal state")
    _require(terminal["receipt_count"] == 0 and terminal["receipt_sha256"] is None, "receipt absence")
    _require(terminal["retry_permitted"] is False, "retry must remain prohibited")
    _require(authorization["attempts"] == 1 and authorization["retries"] == 0 and authorization["resume"] is False, "one-shot authority")
    _require(authorization["prompt_token"] == 9703 and authorization["expected_token"] == 21615, "token authority")
    _require(evidence["execution"]["produced_token"] == 17351, "produced-token observation")
    _require(evidence["execution"]["expected_token"] == 21615, "expected-token observation")
    _require(evidence["execution"]["process_exit"] == 2, "process exit")
    _require(evidence["accounting"]["accounting_closure"] == "FAIL", "accounting closure")
    _require(evidence["terminal"]["second_token"] is False and evidence["terminal"]["further_real_inference"] is False, "mandatory stop")
    _require(native_ledger["native_event_count_before"] == 0 and native_ledger["native_event_count_after"] == 1, "native event count")
    _require(len(native_ledger["events"]) == 1, "native event census")
    _require(native_ledger["historical_master"]["before"] == 175 and native_ledger["historical_master"]["after"] == 175, "historical count")
    _require(review["verdict"] == "ACCEPT_POST_EXECUTION_FAILURE_EVIDENCE", "post review verdict")
    _require(review["blocking_count"] == 0 and review["non_blocking_required_count"] == 0, "review findings")

    historical = subprocess.run(
        ["git", "show", f"{HISTORICAL_COMMIT}:{HISTORICAL_PATH}"],
        cwd=repository,
        check=True,
        stdout=subprocess.PIPE,
    ).stdout
    _require(sha256_bytes(historical) == HISTORICAL_SHA, "historical ledger SHA")
    historical_json = json.loads(historical, object_pairs_hook=_pairs)
    _require(historical_json["receipt_chain"]["terminal_count"] == 175, "historical terminal count")
    _require(historical_json["receipt_chain"]["gaps"] == 0, "historical receipt gaps")

    return {
        "schema": "pulsarmlx.f017.attempt-1-evidence-validation/1.0.0",
        "result": "PASS_IMMUTABLE_TERMINAL_FAILURE",
        "artifact_count": len(EXPECTED),
        "authorization_id": auth_id,
        "attempt_id": attempt_id,
        "terminal": terminal["state"],
        "prompt_token": 9703,
        "produced_token": 17351,
        "expected_token": 21615,
        "receipt_count": 0,
        "accounting_closure": "FAIL",
        "historical_master_terminal": 175,
        "native_event_count": 1,
        "retry_permitted": False,
        "attempt_2_authorized": False,
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    result = validate(arguments.repository)
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if arguments.output:
        arguments.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (EvidenceError, KeyError, OSError, subprocess.CalledProcessError) as error:
        print(f"attempt-1 evidence validation failed closed: {error}")
        raise SystemExit(2)
