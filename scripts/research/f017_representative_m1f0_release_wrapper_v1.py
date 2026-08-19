#!/usr/bin/env python3
"""Narrow release wrapper for the representative M1-F0 v3 event.

Preparation mode validates every committed public binding without resolving or
opening the private shard. Execution mode instantiates only the frozen event
after a separately committed GO release. It offers no generic inventory,
layer, event, or expert-selection controls.
"""

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
    LedgerAuthority,
    PreOpenPreflight,
    RepresentativeM1F0ExecutorV3,
)
from f017_representative_m1f0_reproduce_from_retention_v1 import produce_bundle
from validate_f017_representative_m1f0_execution_authorization_v3 import validate_paths


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AUTHORIZATION = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-m1f0-execution-authorization-v3.json"
LEDGER_SOURCES = (
    (ROOT / "docs/architecture/reviews/evidence/f017-real-payload-access-ledger-v1.json", ("cumulative_tensor_payloads",)),
    (ROOT / "docs/architecture/reviews/evidence/f017-canonical-shared-expert-recovery-result-v1.json", ("ledger", "after")),
)
PRIVATE_ENV = {
    "canonical_s0": "PULSARMLX_F017_REPRESENTATIVE_S0_PATH",
    "ffn_norm": "PULSARMLX_F017_REPRESENTATIVE_FFN_NORM_PATH",
    "router_matrix": "PULSARMLX_F017_REPRESENTATIVE_ROUTER_MATRIX_PATH",
    "correction_bias": "PULSARMLX_F017_REPRESENTATIVE_CORRECTION_BIAS_PATH",
}


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_binding(binding: dict[str, Any]) -> Path:
    path = ROOT / binding["path"]
    if not path.is_file() or sha_file(path) != binding["sha256"]:
        raise EventError("PUBLIC_BINDING_IDENTITY")
    return path


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
    for key in ("executor", "preopen_preflight", "crash_terminalizer", "reproduction",
                "synthetic_rehearsal", "review_authority", "validator"):
        resolve_binding(wrapper[key])
    if candidate.get("event", {}) != {"event_id": EVENT_ID, "attempt_id": ATTEMPT_ID}:
        raise EventError("EVENT_ID")
    return wrapper, candidate


def require_release(release_path: Path, authorization_sha256: str) -> dict[str, Any]:
    release = load(release_path)
    expected = {
        "event_id": EVENT_ID,
        "attempt_id": ATTEMPT_ID,
        "authorization_sha256": authorization_sha256,
        "disposition": "GO_EXECUTE_ONCE_NO_RETRY",
    }
    if any(release.get(key) != value for key, value in expected.items()):
        raise EventError("INDEPENDENT_RELEASE_GATE")
    if release.get("real_event_authorized") is not True:
        raise EventError("INDEPENDENT_RELEASE_GATE")
    return release


def private_path(name: str) -> Path:
    value = os.environ.get(name)
    if not value:
        raise EventError("PRIVATE_BINDING_UNRESOLVED")
    return Path(value)


def build_executor(candidate: dict[str, Any], candidate_path: Path,
                   candidate_sha256: str) -> RepresentativeM1F0ExecutorV3:
    retained = {role: private_path(variable) for role, variable in PRIVATE_ENV.items()}
    preflight = PreOpenPreflight(
        ledger=LedgerAuthority(list(LEDGER_SOURCES)),
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
        candidate_path = resolve_binding(wrapper["authorization_candidate"])
        if args.preflight_only:
            print(json.dumps({
                "result": "PRODUCTION_BINDINGS_RESOLVED",
                "event_shape": "9_CHECKPOINT_READS+3_RETAINED_ROUTER_AUTHORITIES+1_RETAINED_S0",
                "checkpoint_reads": 0,
                "shard_opens": 0,
                "ledger": 166,
                "real_event_authorized": False,
            }, sort_keys=True))
            return 0
        if args.independent_release is None:
            raise EventError("INDEPENDENT_RELEASE_REQUIRED")
        require_release(args.independent_release.resolve(), sha_file(args.authorization.resolve()))
        result = build_executor(candidate, candidate_path, sha_file(candidate_path)).execute()
        print(json.dumps(result, sort_keys=True))
        return 0
    except EventError as exc:
        print(json.dumps({"result": "REJECTED", "reason": exc.code}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
