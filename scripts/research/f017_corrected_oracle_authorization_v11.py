#!/usr/bin/env python3
"""Strict V11/Event-05 authorization document model."""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path

from f017_bounded_artifact_decode_v1 import parse_artifact_bytes
from f017_canonical_serialization_v10 import sha256_bytes
import f017_corrected_oracle_authorization_v10 as v10

SCHEMA = "pulsarmlx.f017.corrected-full-checkpoint-oracle-access-authorization/11.0.0"
KEYS = v10.KEYS | {"result_authority_sha256", "implementation_measurement_sha256"}
LIVE_KEYS = v10.LIVE_KEYS | {"result_authority_sha256", "implementation_measurement_sha256"}
ROOT = Path(__file__).resolve().parents[2]
NUMERICAL_V4 = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-numerical-contract-v4.json"
PRIMARY_V3 = ROOT / "scripts/research/f017_corrected_oracle_primary_numerics_v3.py"
SECONDARY_V3 = ROOT / "scripts/research/f017_corrected_oracle_secondary_numerics_v3.py"
RESULT_AUTHORITY = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-result-authority-v11-v2.json"
IMPLEMENTATION_MEASUREMENT = ROOT / "docs/architecture/reviews/evidence/f017-v11-result-envelope-implementation-measurement-v7.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_candidate_bytes(raw: bytes) -> dict:
    value = parse_artifact_bytes(raw)
    if type(value) is not dict or set(value) not in (KEYS, LIVE_KEYS):
        raise ValueError("V11 authorization key census")
    historical = copy.deepcopy(value)
    historical.pop("result_authority_sha256")
    historical.pop("implementation_measurement_sha256")
    historical["schema"] = v10.SCHEMA
    historical["authority_generation"] = 9
    historical["active_generation"] = "V10"
    if historical["scope"] == "PRODUCTION_EVENT_05":
        historical["scope"] = "PRODUCTION_EVENT_04"
    v10.parse_candidate_bytes(__import__("f017_canonical_serialization_v10").canonical_bytes(historical))
    if (value["schema"] != SCHEMA or value["authority_generation"] != 11
            or value["active_generation"] != "V11"
            or value["scope"] not in {"SYNTHETIC_QUALIFICATION", "PRODUCTION_SHADOW_NO_ACCESS", "PRODUCTION_EVENT_05"}
            or value["numerical_contract_sha256"] != _sha(NUMERICAL_V4)
            or value["primary_numerical_sha256"] != _sha(PRIMARY_V3)
            or value["secondary_numerical_sha256"] != _sha(SECONDARY_V3)
            or value["result_authority_sha256"] != _sha(RESULT_AUTHORITY)
            or value["implementation_measurement_sha256"] != _sha(IMPLEMENTATION_MEASUREMENT)):
        raise ValueError("V11 execution authority binding")
    if set(value) == LIVE_KEYS and value["scope"] != "PRODUCTION_EVENT_05":
        raise ValueError("V11 live scope")
    return value


def parse_candidate(path: Path) -> tuple[dict, str]:
    raw = path.read_bytes()
    return parse_candidate_bytes(raw), sha256_bytes(raw)


def production_shards() -> list[dict]:
    return v10.production_shards()
