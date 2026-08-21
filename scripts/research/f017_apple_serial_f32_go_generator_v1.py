#!/usr/bin/env python3
"""Operator-only future GO generator; normal validation cannot mint a live GO."""

from __future__ import annotations
import argparse, hashlib, json, os
from pathlib import Path
from f017_apple_serial_f32_capture_wrapper_v2 import GateError, load_unique, sha

REPO = Path(__file__).resolve().parents[2]


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", required=True, type=Path)
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--operator-confirm-exactly-once", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--validate-inert-fixture", type=Path)
    args = parser.parse_args()
    release = load_unique(args.release)
    if args.validate_inert_fixture:
        fixture = load_unique(args.validate_inert_fixture)
        if fixture.get("inert") is not True or fixture.get("real_event_authorized") is not False or fixture.get("disposition") != "INERT_NOT_EXECUTABLE":
            raise GateError("INERT_FIXTURE")
        print("INERT_AUTHORIZATION_FIXTURE_REJECTED_AS_LIVE_PASS")
        return 0
    if not args.operator_confirm_exactly_once or args.approval is None or args.output is None:
        raise GateError("EXPLICIT_OPERATOR_ONLY_LIVE_ISSUANCE_REQUIRED")
    approval = load_unique(args.approval)
    if approval.get("verdict") != "ACCEPT" or approval.get("human_approval_identity") in (None, "", "INERT"):
        raise GateError("HUMAN_APPROVAL_REQUIRED")
    fields = release["go_token_schema_fields"]
    direct = ["event_id","release_id","attempt_id","execution_code_head","native_executable_sha256","package_root_sha256","stage_manifest_sha256","capture_manifest_sha256","comparison_contract_sha256","determinism_contract_sha256","wrapper_sha256","terminalizer_sha256"]
    token = {key: approval[key] for key in direct}
    token.update({
        "schema":"pulsarmlx.f017.apple-production-serial-f32-live-go",
        "schema_version":"1.0.0", "release_sha256":sha(args.release),
        "approval_sha256":sha(args.approval), "readiness_head":approval["readiness_head"],
        "code_manifest_sha256":release["code_manifest"]["sha256"],
        "runtime_binding_sha256":release["runtime_binding"]["sha256"],
        "package_manifest_sha256":release["package_census_sha256"],
        "expected_starting_ledger":175, "allowed_real_payload_consumption":0,
        "allowed_attempt_count":1, "retries":0, "resume":False,
        "checkpoint_reads":0, "checkpoint_fallback":"PROHIBITED",
        "allowed_stage_range":"input_hidden..production_s2",
        "allowed_output_root":release["machine_local_paths"]["capture_root"],
        "human_approval_identity":approval["human_approval_identity"],
        "disposition":"GO_EXECUTE_ONCE_NO_RETRY", "real_event_authorized":True,
    })
    if set(token) != set(fields):
        raise GateError("TOKEN_FIELD_CENSUS")
    data = canonical(token)
    descriptor = os.open(args.output, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o400)
    try:
        os.write(descriptor, data); os.fsync(descriptor)
    finally:
        os.close(descriptor)
    print(hashlib.sha256(data).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
