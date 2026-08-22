#!/usr/bin/env python3
"""Validate the F017 native-domain cross-branch and master-ledger authority."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


class AuthorityError(ValueError):
    pass


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise AuthorityError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _load_json_bytes(data: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(data, object_pairs_hook=_strict_object)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise AuthorityError(f"{label} is not strict JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise AuthorityError(f"{label} is not a JSON object")
    return value


def _git(repo: Path, *args: str) -> bytes:
    try:
        return subprocess.run(
            ["git", *args], cwd=repo, check=True, capture_output=True
        ).stdout
    except subprocess.CalledProcessError as exc:
        raise AuthorityError(f"git {' '.join(args)} failed") from exc


def _resolve(document: Any, dotted: str) -> Any:
    current = document
    for component in dotted.split("."):
        if not isinstance(current, dict) or component not in current:
            raise AuthorityError(f"unresolved bound field: {dotted}")
        current = current[component]
    return current


def validate(contract_path: Path, repo: Path) -> dict[str, Any]:
    contract_bytes = contract_path.read_bytes()
    contract = _load_json_bytes(contract_bytes, str(contract_path))
    if contract.get("schema") != "pulsarmlx.f017.native-domain-cross-branch-authority":
        raise AuthorityError("cross-branch authority schema mismatch")
    if contract.get("schema_version") != "1.0.0":
        raise AuthorityError("cross-branch authority version mismatch")
    native = contract["native_domain"]
    if native["branch"] != "feat/017-rust-native-inference-runtime":
        raise AuthorityError("native branch mismatch")
    if native["base_head"] != "8027b4cfc08866dc841c80363e4bdc4663318b4a":
        raise AuthorityError("native base head mismatch")
    if len(native["owns"]) != 5:
        raise AuthorityError("native authority inventory mismatch")
    historical = contract["historical_domain"]
    remote_ref = f"origin/{historical['branch']}"
    if _git(repo, "rev-parse", remote_ref).decode().strip() != historical["head"]:
        raise AuthorityError("historical branch head mismatch")
    required = {
        "branch", "commit", "path", "sha256", "schema", "schema_version", "semantic_role"
    }
    resolved: dict[str, dict[str, Any]] = {}
    for binding in contract["historical_authorities"]:
        if set(binding) != required:
            raise AuthorityError("historical authority field census mismatch")
        if binding["branch"] != historical["branch"] or binding["commit"] != historical["head"]:
            raise AuthorityError("historical authority branch/commit mismatch")
        data = _git(repo, "show", f"{binding['commit']}:{binding['path']}")
        digest = hashlib.sha256(data).hexdigest()
        if digest != binding["sha256"]:
            raise AuthorityError(f"historical authority SHA mismatch: {binding['path']}")
        parsed = _load_json_bytes(data, binding["path"])
        if parsed.get("schema") != binding["schema"] or parsed.get("schema_version") != binding["schema_version"]:
            raise AuthorityError(f"historical schema mismatch: {binding['path']}")
        resolved[binding["semantic_role"]] = parsed
    ledger = resolved["AUTHORITATIVE_HISTORICAL_MASTER_REAL_PAYLOAD_LEDGER"]
    expected_chain = contract["master_ledger_precondition"]
    checks = {
        "prefix_terminal_count": _resolve(ledger, "receipt_chain.prefix_terminal_count"),
        "appended_receipt_counts": _resolve(ledger, "receipt_chain.appended_receipt_counts"),
        "terminal_count": _resolve(ledger, "receipt_chain.terminal_count"),
        "gaps": _resolve(ledger, "receipt_chain.gaps"),
        "overlaps": _resolve(ledger, "receipt_chain.overlaps"),
        "duplicate_receipts": _resolve(ledger, "receipt_chain.duplicate_receipts"),
        "unexplained_increments": _resolve(ledger, "receipt_chain.unexplained_increments"),
    }
    for key, actual in checks.items():
        if type(actual) is not type(expected_chain[key]) or actual != expected_chain[key]:
            raise AuthorityError(f"receipt-chain mismatch: {key}")
    if ledger.get("cumulative_tensor_payloads") != 175:
        raise AuthorityError("historical master terminal count is not 175")
    chaining = contract["native_ledger_chaining"]
    if chaining.get("competing_master_count_permitted") is not False:
        raise AuthorityError("native domain permits a competing master")
    if chaining["historical_master_sha256"] != contract["historical_authorities"][0]["sha256"]:
        raise AuthorityError("native ledger chain does not bind the historical master")
    required_true = {
        "future_native_events_must_bind_historical_master",
        "zero_payload_native_event_must_still_bind_historical_master",
        "post_event_count_must_be_receipt_derived",
        "event_result_and_ledger_update_same_commit_if_count_advances",
    }
    if any(chaining.get(key) is not True for key in required_true):
        raise AuthorityError("native ledger chaining rule weakened")
    if contract["phase_accounting"] != {
        "historical_master_before": 175,
        "historical_master_after": 175,
        "checkpoint_reads": 0,
        "shard_opens": 0,
        "real_m1_ultra_p1_executions": 0,
        "live_p1_authorizations": 0,
    }:
        raise AuthorityError("authority-precondition phase accounting mismatch")
    return {
        "result": "PASS",
        "contract_sha256": hashlib.sha256(contract_bytes).hexdigest(),
        "historical_head": historical["head"],
        "master_sha256": contract["historical_authorities"][0]["sha256"],
        "terminal_count": 175,
        "receipt_continuity": "PASS",
        "contradictory_authority": "NONE",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--contract",
        type=Path,
        default=Path("specs/017-rust-native-inference-runtime/contracts/f017-native-domain-cross-branch-authority-v1.json"),
    )
    args = parser.parse_args()
    root = args.root.resolve()
    contract = args.contract if args.contract.is_absolute() else root / args.contract
    print(json.dumps(validate(contract, root), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
