#!/usr/bin/env python3
"""Append-only representative M1-F0 release wrapper with exact ledger adapter."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from f017_representative_m1f0_executor import EventError, ProductionComputationStage
from f017_representative_m1f0_executor_v3 import (
    ATTEMPT_ID,
    EVENT_ID,
    EagerDecoderRegistry,
    PreOpenPreflight,
    RepresentativeM1F0ExecutorV3,
)
from f017_representative_m1f0_ledger_adapter_v1 import (
    CanonicalLedgerAdapter,
    DEFAULT_CONTRACT as DEFAULT_LEDGER_CONTRACT,
    EXPECTED_CONTRACT_SHA256,
)
from f017_representative_m1f0_reproduce_from_retention_v1 import produce_bundle
from validate_f017_representative_m1f0_execution_authorization_v3 import validate_paths


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AUTHORIZATION = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-m1f0-execution-authorization-v3.json"
DEFAULT_RELEASE_CONTRACT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-m1f0-single-use-execution-release-v2.json"
LEDGER_ADAPTER = ROOT / "scripts/research/f017_representative_m1f0_ledger_adapter_v1.py"
LEDGER_ADAPTER_SHA256 = "ea0e54569499cd7b3fbd3d07ec107ee51c20a86327b9050ec7070b1218c03198"
RELEASE_ID = "F017-REPRESENTATIVE-M1F0-ATTENTION-ROUTE-RECOVERY-1-RELEASE-2"
OLD_RELEASE_APPROVAL_SHA256 = "4ea1d3eb5af5ac590173e911e62e22435852d9fbc1bf30fc0088cec3a664a9bf"
PRIVATE_ENV = {
    "canonical_s0": "PULSARMLX_F017_REPRESENTATIVE_S0_PATH",
    "ffn_norm": "PULSARMLX_F017_REPRESENTATIVE_FFN_NORM_PATH",
    "router_matrix": "PULSARMLX_F017_REPRESENTATIVE_ROUTER_MATRIX_PATH",
    "correction_bias": "PULSARMLX_F017_REPRESENTATIVE_CORRECTION_BIAS_PATH",
}


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EventError("CONTROL_PLANE_JSON") from exc
    if not isinstance(value, dict):
        raise EventError("CONTROL_PLANE_JSON")
    return value


def resolve_binding(binding: dict[str, Any]) -> Path:
    path = ROOT / binding["path"]
    if not path.is_file() or sha_file(path) != binding["sha256"]:
        raise EventError("PUBLIC_BINDING_IDENTITY")
    return path


def ledger_adapter() -> CanonicalLedgerAdapter:
    if not LEDGER_ADAPTER.is_file() or sha_file(LEDGER_ADAPTER) != LEDGER_ADAPTER_SHA256:
        raise EventError("LEDGER_ADAPTER_IDENTITY")
    if not DEFAULT_LEDGER_CONTRACT.is_file() or sha_file(DEFAULT_LEDGER_CONTRACT) != EXPECTED_CONTRACT_SHA256:
        raise EventError("LEDGER_CONTRACT_IDENTITY")
    return CanonicalLedgerAdapter(ROOT, DEFAULT_LEDGER_CONTRACT, EXPECTED_CONTRACT_SHA256)


def public_preflight(authorization_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    errors = validate_paths(ROOT, authorization_path)
    if errors:
        raise EventError("AUTHORIZATION_VALIDATOR:" + ",".join(errors))
    wrapper = load(authorization_path)
    if wrapper.get("status") != "PREPARED_REVIEW_REQUIRED":
        raise EventError("AUTHORIZATION_STATUS")
    if wrapper.get("authorization", {}).get("real_event_authorized") is not False:
        raise EventError("REAL_EVENT_GATE")
    candidate_path = resolve_binding(wrapper["authorization_candidate"])
    candidate = load(candidate_path)
    for key in (
        "executor", "preopen_preflight", "crash_terminalizer", "reproduction",
        "synthetic_rehearsal", "review_authority", "validator",
    ):
        resolve_binding(wrapper[key])
    if candidate.get("event", {}) != {"event_id": EVENT_ID, "attempt_id": ATTEMPT_ID}:
        raise EventError("EVENT_ID")
    ledger_adapter()
    return wrapper, candidate


def require_release(
    token_path: Path,
    authorization_sha256: str,
    release_contract_path: Path = DEFAULT_RELEASE_CONTRACT,
) -> dict[str, Any]:
    token = load(token_path)
    release_contract = load(release_contract_path)
    if release_contract.get("schema") != "pulsarmlx.f017.representative-m1f0-single-use-execution-release":
        raise EventError("INDEPENDENT_RELEASE_GATE")
    if release_contract.get("schema_version") != "2.0.0" or release_contract.get("status") != "PREPARED_FOR_INDEPENDENT_APPROVAL":
        raise EventError("INDEPENDENT_RELEASE_GATE")
    if release_contract.get("release_id") != RELEASE_ID:
        raise EventError("INDEPENDENT_RELEASE_GATE")
    if release_contract.get("event_id") != EVENT_ID or release_contract.get("attempt_id") != ATTEMPT_ID:
        raise EventError("INDEPENDENT_RELEASE_GATE")
    bindings = release_contract.get("accepted_bindings", {})
    if bindings.get("authorization_v3", {}).get("sha256") != authorization_sha256:
        raise EventError("INDEPENDENT_RELEASE_GATE")
    if bindings.get("ledger_adapter", {}).get("sha256") != LEDGER_ADAPTER_SHA256:
        raise EventError("INDEPENDENT_RELEASE_GATE")
    if bindings.get("ledger_adapter_contract", {}).get("sha256") != EXPECTED_CONTRACT_SHA256:
        raise EventError("INDEPENDENT_RELEASE_GATE")
    release_sha256 = sha_file(release_contract_path)
    expected = {
        "approval_sha256",
        "attempt_id",
        "authorization_sha256",
        "disposition",
        "event_id",
        "real_event_authorized",
        "release_id",
        "release_sha256",
    }
    if set(token) != expected:
        raise EventError("INDEPENDENT_RELEASE_GATE")
    if token != {
        "approval_sha256": token["approval_sha256"],
        "attempt_id": ATTEMPT_ID,
        "authorization_sha256": authorization_sha256,
        "disposition": "GO_EXECUTE_ONCE_NO_RETRY",
        "event_id": EVENT_ID,
        "real_event_authorized": True,
        "release_id": RELEASE_ID,
        "release_sha256": release_sha256,
    }:
        raise EventError("INDEPENDENT_RELEASE_GATE")
    approval = token["approval_sha256"]
    if not isinstance(approval, str) or len(approval) != 64 or any(c not in "0123456789abcdef" for c in approval):
        raise EventError("INDEPENDENT_RELEASE_GATE")
    if approval == OLD_RELEASE_APPROVAL_SHA256:
        raise EventError("INDEPENDENT_RELEASE_GATE")
    return token


def private_path(name: str) -> Path:
    value = os.environ.get(name)
    if not value:
        raise EventError("PRIVATE_BINDING_UNRESOLVED")
    return Path(value)


def build_executor(
    candidate: dict[str, Any],
    candidate_path: Path,
    candidate_sha256: str,
    authoritative_ledger: CanonicalLedgerAdapter,
) -> RepresentativeM1F0ExecutorV3:
    retained = {role: private_path(variable) for role, variable in PRIVATE_ENV.items()}
    preflight = PreOpenPreflight(
        ledger=authoritative_ledger,
        retained_paths=retained,
        manifest_paths={"canonical_s0": private_path("PULSARMLX_F017_REPRESENTATIVE_S0_MANIFEST_PATH")},
        shard_path=private_path("PULSARMLX_F017_REPRESENTATIVE_SHARD2_PATH"),
        state_root=private_path("PULSARMLX_F017_REPRESENTATIVE_ATTEMPT_STATE_ROOT"),
        retention_root=private_path("PULSARMLX_F017_REPRESENTATIVE_RETENTION_ROOT"),
        decoder_registry=EagerDecoderRegistry(),
    )

    def reproduce(stages: dict[str, str]) -> dict[str, Any]:
        del stages
        output = preflight.state_root / "reproduction.json"
        return produce_bundle(candidate_path, preflight.retention_root, retained, output)

    return RepresentativeM1F0ExecutorV3(
        authorization=candidate,
        authorization_sha256=candidate_sha256,
        preflight=preflight,
        computation=ProductionComputationStage(),
        state_root=preflight.state_root,
        retention_root=preflight.retention_root,
        synthetic=False,
        reproduction=reproduce,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authorization", type=Path, default=DEFAULT_AUTHORIZATION)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight-only", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--independent-release", type=Path)
    args = parser.parse_args()
    try:
        wrapper, candidate = public_preflight(args.authorization.resolve())
        del wrapper
        candidate_path = resolve_binding(load(args.authorization.resolve())["authorization_candidate"])
        adapter = ledger_adapter()
        current_ledger, observations = adapter.read()
        if args.preflight_only:
            print(json.dumps({
                "result": "PRODUCTION_BINDINGS_RESOLVED",
                "event_shape": "9_CHECKPOINT_READS+3_RETAINED_ROUTER_AUTHORITIES+1_RETAINED_S0",
                "checkpoint_reads": 0,
                "shard_opens": 0,
                "ledger": current_ledger,
                "ledger_adapter": "EXACT_COMMITTED_SCHEMA_V1",
                "ledger_source_count": len(observations),
                "real_event_authorized": False,
            }, sort_keys=True))
            return 0
        if args.independent_release is None:
            raise EventError("INDEPENDENT_RELEASE_REQUIRED")
        require_release(
            args.independent_release.resolve(),
            sha_file(args.authorization.resolve()),
        )
        result = build_executor(candidate, candidate_path, sha_file(candidate_path), adapter).execute()
        print(json.dumps(result, sort_keys=True))
        return 0
    except EventError as exc:
        print(json.dumps({"result": "REJECTED", "reason": exc.code}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
