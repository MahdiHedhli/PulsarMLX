#!/usr/bin/env python3
"""Exact-schema authoritative-ledger adapter for representative M1-F0.

This adapter intentionally recognizes only the two committed representations
named by its contract.  It does not probe legacy or alternate field paths.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from f017_representative_m1f0_executor import EventError


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTRACT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-m1f0-ledger-adapter-v1.json"
EXPECTED_CONTRACT_SHA256 = "20a0719fd847254c1c7b9f053b9d9df0d0b380177f4914f62f826149fa91c87f"
CONTRACT_SCHEMA = "pulsarmlx.f017.representative-m1f0-authoritative-ledger-adapter"
CONTRACT_VERSION = "1.0.0"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EventError("LEDGER_DUPLICATE_KEY")
        result[key] = value
    return result


def load_json(path: Path, error_code: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates)
    except EventError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EventError(error_code) from exc
    if not isinstance(value, dict):
        raise EventError(error_code)
    return value


class CanonicalLedgerAdapter:
    """Normalize two exact committed ledger authorities to ``current_ledger``."""

    def __init__(
        self,
        root: Path = ROOT,
        contract_path: Path = DEFAULT_CONTRACT,
        expected_contract_sha256: str | None = EXPECTED_CONTRACT_SHA256,
    ) -> None:
        self.root = root.resolve()
        self.contract_path = contract_path.resolve()
        self.expected_contract_sha256 = expected_contract_sha256

    def _contract(self) -> dict[str, Any]:
        if not self.contract_path.is_file():
            raise EventError("LEDGER_CONTRACT_MISSING")
        if self.expected_contract_sha256 is not None and sha256(self.contract_path) != self.expected_contract_sha256:
            raise EventError("LEDGER_CONTRACT_IDENTITY")
        contract = load_json(self.contract_path, "LEDGER_CONTRACT_JSON")
        if contract.get("schema") != CONTRACT_SCHEMA or contract.get("schema_version") != CONTRACT_VERSION:
            raise EventError("LEDGER_CONTRACT_SCHEMA")
        if contract.get("normalized_field") != "current_ledger":
            raise EventError("LEDGER_CONTRACT_NORMALIZATION")
        expected = contract.get("expected_current_ledger")
        if isinstance(expected, bool) or not isinstance(expected, int):
            raise EventError("LEDGER_CONTRACT_EXPECTED_VALUE")
        normalization = contract.get("normalization")
        if normalization != {
            "authorized_source_representations": 2,
            "fallback_field_paths": False,
            "require_exact_artifact_sha256": True,
            "require_exact_schema_and_version": True,
            "require_integer_not_boolean": True,
            "require_source_agreement": True,
            "require_expected_value": True,
        }:
            raise EventError("LEDGER_CONTRACT_NORMALIZATION")
        if contract.get("failure_policy") != {
            "fail_before_attempt_start": True,
            "fail_before_shard_open": True,
            "checkpoint_reads": 0,
            "shard_opens": 0,
            "ledger_mutation": False,
        }:
            raise EventError("LEDGER_CONTRACT_FAILURE_POLICY")
        sources = contract.get("sources")
        if not isinstance(sources, list) or len(sources) != 2:
            raise EventError("LEDGER_CONTRACT_SOURCES")
        if [source.get("role") for source in sources if isinstance(source, dict)] != [
            "cumulative_real_payload_ledger",
            "canonical_shared_expert_terminal_recovery",
        ]:
            raise EventError("LEDGER_CONTRACT_SOURCES")
        return contract

    def read(self) -> tuple[int, list[dict[str, Any]]]:
        contract = self._contract()
        observations: list[dict[str, Any]] = []
        for source in contract["sources"]:
            if not isinstance(source, dict) or set(source) != {
                "role", "path", "sha256", "schema", "schema_version", "field", "required_equals"
            }:
                raise EventError("LEDGER_SOURCE_SPEC")
            relative = Path(str(source["path"]))
            if relative.is_absolute() or ".." in relative.parts:
                raise EventError("LEDGER_SOURCE_PATH")
            path = self.root / relative
            if not path.is_file() or sha256(path) != source["sha256"]:
                raise EventError("LEDGER_SOURCE_IDENTITY")
            document = load_json(path, "LEDGER_SOURCE_JSON")
            if document.get("schema") != source["schema"] or document.get("schema_version") != source["schema_version"]:
                raise EventError("LEDGER_SOURCE_SCHEMA")
            required_equals = source["required_equals"]
            if not isinstance(required_equals, dict) or any(document.get(key) != value for key, value in required_equals.items()):
                raise EventError("LEDGER_SOURCE_PROVENANCE")
            field = source["field"]
            if not isinstance(field, str) or "." in field or field not in document:
                raise EventError("LEDGER_SOURCE_FIELD")
            value = document[field]
            if isinstance(value, bool) or not isinstance(value, int):
                raise EventError("LEDGER_SOURCE_VALUE_TYPE")
            observations.append({
                "role": source["role"],
                "path": relative.as_posix(),
                "sha256": source["sha256"],
                "schema": source["schema"],
                "schema_version": source["schema_version"],
                "field": field,
                "value": value,
            })
        values = {observation["value"] for observation in observations}
        if len(values) != 1:
            raise EventError("LEDGER_SOURCE_DISAGREEMENT")
        current_ledger = values.pop()
        if current_ledger != contract["expected_current_ledger"]:
            raise EventError("LEDGER_UNEXPECTED_VALUE")
        return current_ledger, observations


def main() -> int:
    current_ledger, observations = CanonicalLedgerAdapter().read()
    print(json.dumps({
        "result": "PASS",
        "normalized_field": "current_ledger",
        "current_ledger": current_ledger,
        "sources": observations,
        "checkpoint_reads": 0,
        "shard_opens": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
