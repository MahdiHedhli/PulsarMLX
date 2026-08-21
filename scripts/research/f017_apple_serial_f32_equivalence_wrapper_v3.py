#!/usr/bin/env python3
"""Execution-readiness wrapper for one future Apple serial-f32 equivalence run.

Preflight performs all retained-package and runtime rehashes before RN1 attempt
ownership can be established.  This phase invokes only --preflight-only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

try:
    from .f017_apple_serial_f32_capture_wrapper_v2 import (
        GateError, durable_create, fsync_dir, load_unique, owner_matches, sha,
        terminalize_owned_failure, terminalize_owned_success,
    )
    from .f017_apple_serial_f32_execution_readiness_v1 import (
        ATTEMPT_ROOT, CAPTURE_ROOT, PACKAGE_CENSUS, PACKAGE_JSON,
        ReadinessError, derive_descriptors, validate_destination,
    )
except ImportError:
    from f017_apple_serial_f32_capture_wrapper_v2 import (
        GateError, durable_create, fsync_dir, load_unique, owner_matches, sha,
        terminalize_owned_failure, terminalize_owned_success,
    )
    from f017_apple_serial_f32_execution_readiness_v1 import (
        ATTEMPT_ROOT, CAPTURE_ROOT, PACKAGE_CENSUS, PACKAGE_JSON,
        ReadinessError, derive_descriptors, validate_destination,
    )

REPO = Path(__file__).resolve().parents[2]
THREADS = {"OPENBLAS_NUM_THREADS":"1", "OMP_NUM_THREADS":"1", "VECLIB_MAXIMUM_THREADS":"1", "MKL_NUM_THREADS":"1", "NUMEXPR_NUM_THREADS":"1"}


def verify_binding(binding: dict) -> Path:
    path = REPO / binding["path"]
    if not path.is_file() or sha(path) != binding["sha256"]:
        raise GateError(f"BINDING:{binding.get('path')}")
    return path


def validate_release(path: Path) -> dict:
    release = load_unique(path)
    if release.get("schema") != "pulsarmlx.f017.apple-production-serial-f32-equivalence-release" or release.get("schema_version") != "3.0.0":
        raise GateError("RELEASE_SCHEMA")
    if release.get("real_event_authorized") is not False or release.get("live_go_token_created") is not False:
        raise GateError("PREMATURE_AUTHORITY")
    if release.get("ledger") != {"start":175,"terminal":175,"classification":"RETAINED_ONLY_REAL_EXECUTION_EVENT_ZERO_PAYLOAD_DELTA"}:
        raise GateError("LEDGER")
    budgets = release.get("execution_budgets", {})
    for key in ("checkpoint_reads","shard_opens","attention_executions","expert_executions","aggregate_executions","shared_expert_executions","ffn_compositions","s1_materializations","s2_constructions"):
        if budgets.get(key) != 0:
            raise GateError(f"BUDGET:{key}")
    if budgets.get("production_equivalence_executions") != 1 or budgets.get("attempts") != 1 or budgets.get("retries") != 0:
        raise GateError("ONE_SHOT_BUDGET")
    for binding in release["bound_contracts"]:
        verify_binding(binding)
    manifest = load_unique(verify_binding(release["code_manifest"]))
    for binding in manifest["artifacts"]:
        verify_binding(binding)
    runtime = load_unique(verify_binding(release["runtime_binding"]))
    for family in ("mlx", "mlx_c"):
        for key in ("library", "version_header"):
            value = runtime[family][key]
            if sha(Path(value["path"])) != value["sha256"]:
                raise GateError(f"RUNTIME:{family}:{key}")
    umbrella = runtime["mlx_c"]["umbrella_header"]
    if sha(Path(umbrella["path"])) != umbrella["sha256"]:
        raise GateError("RUNTIME:umbrella")
    for key, value in THREADS.items():
        if release["environment"]["thread_limits"].get(key) != value:
            raise GateError(f"THREAD_CONTRACT:{key}")
    runner = REPO / release["runner_path"]
    if not runner.is_file() or runner.is_symlink() or sha(runner) != release["native_executable_sha256"]:
        raise GateError("EXECUTOR_SHA")
    paths = release["machine_local_paths"]
    if Path(paths["package_manifest"]) != PACKAGE_JSON or Path(paths["package_census"]) != PACKAGE_CENSUS:
        raise GateError("PACKAGE_PATH_BINDING")
    if Path(paths["attempt_root"]) != ATTEMPT_ROOT or Path(paths["capture_root"]) != CAPTURE_ROOT:
        raise GateError("STATE_PATH_BINDING")
    result = validate_destination(derive_descriptors())
    if result["package_root_sha256"] != release["package_root_sha256"]:
        raise GateError("PACKAGE_ROOT")
    if sha(PACKAGE_CENSUS) != release["package_census_sha256"] or sha(PACKAGE_JSON) != release["runner_package_sha256"]:
        raise GateError("PACKAGE_MANIFEST_SHA")
    if ATTEMPT_ROOT.exists() or CAPTURE_ROOT.exists():
        raise GateError("EXECUTION_STATE_PRESENT")
    go = Path(paths["go_token"])
    if go.exists():
        raise GateError("LIVE_GO_TOKEN_PRESENT")
    if release.get("checkpoint_paths") != [] or release.get("checkpoint_fallback") is not False:
        raise GateError("CHECKPOINT_INTERFACE")
    return release


def validate_authority(release_path: Path, release: dict, approval_path: Path, token_path: Path) -> tuple[dict, dict]:
    approval = load_unique(approval_path); token = load_unique(token_path)
    if set(approval) != set(release["approval_schema_fields"]) or set(token) != set(release["go_token_schema_fields"]):
        raise GateError("AUTHORITY_FIELD_CENSUS")
    release_sha = sha(release_path)
    required = {
        "release_sha256": release_sha,
        "execution_code_head": release["execution_code_head"],
        "native_executable_sha256": release["native_executable_sha256"],
        "code_manifest_sha256": release["code_manifest"]["sha256"],
        "runtime_binding_sha256": release["runtime_binding"]["sha256"],
        "package_root_sha256": release["package_root_sha256"],
        "package_manifest_sha256": release["package_census_sha256"],
        "stage_manifest_sha256": release["stage_manifest_sha256"],
        "capture_manifest_sha256": release["capture_manifest_sha256"],
        "comparison_contract_sha256": release["comparison_contract_sha256"],
        "determinism_contract_sha256": release["determinism_contract_sha256"],
        "wrapper_sha256": release["wrapper_sha256"],
        "terminalizer_sha256": release["terminalizer_sha256"],
    }
    for field in ("event_id", "release_id", "attempt_id"):
        required[field] = release[field]
    for field, expected in required.items():
        if approval.get(field) != expected or token.get(field) != expected:
            raise GateError(f"AUTHORITY_BINDING:{field}")
    if token.get("approval_sha256") != sha(approval_path):
        raise GateError("APPROVAL_SHA")
    if approval.get("verdict") != "ACCEPT" or approval.get("human_approval_identity") in (None, "", "INERT"):
        raise GateError("HUMAN_APPROVAL")
    if approval.get("approval_does_not_execute") is not True or approval.get("approval_is_not_token") is not True:
        raise GateError("APPROVAL_SEPARATION")
    if token.get("disposition") != "GO_EXECUTE_ONCE_NO_RETRY" or token.get("real_event_authorized") is not True:
        raise GateError("TOKEN_DISPOSITION")
    if token.get("allowed_attempt_count") != 1 or token.get("retries") != 0 or token.get("resume") is not False:
        raise GateError("TOKEN_ONE_SHOT")
    return approval, token


def execute(release_path: Path, release: dict, approval_path: Path, token_path: Path) -> int:
    validate_authority(release_path, release, approval_path, token_path)
    invocation_id = secrets.token_hex(24)
    ATTEMPT_ROOT.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.mkdir(ATTEMPT_ROOT, 0o700)
    except FileExistsError as exc:
        raise GateError("ATTEMPT_ALREADY_EXISTS_NO_RETRY") from exc
    fsync_dir(ATTEMPT_ROOT.parent)
    owner = {"schema":"pulsarmlx.f017.apple-production-serial-f32-owned-lock","schema_version":"3.0.0","event_id":release["event_id"],"release_id":release["release_id"],"attempt_id":release["attempt_id"],"invocation_id":invocation_id,"pid":os.getpid(),"ownership":"EXCLUSIVE_DURABLE_UNTIL_TERMINAL"}
    owner_sha = durable_create(ATTEMPT_ROOT / "owner.json", owner)
    try:
        durable_create(ATTEMPT_ROOT / "attempt-start.json", {"schema":"pulsarmlx.f017.apple-production-serial-f32-attempt-start","schema_version":"3.0.0","attempt_id":release["attempt_id"],"invocation_id":invocation_id,"owner_sha256":owner_sha,"wrapper_sha256":release["wrapper_sha256"],"executor_sha256":release["native_executable_sha256"],"release_sha256":sha(release_path),"expected_starting_ledger":175,"approval_sha256":sha(approval_path),"go_token_sha256":sha(token_path),"git_head":release["execution_code_head"],"package_root_sha256":release["package_root_sha256"]})
        (ATTEMPT_ROOT / "payload-receipts").mkdir(mode=0o700); fsync_dir(ATTEMPT_ROOT)
        durable_create(ATTEMPT_ROOT / "comparison-start.json", {"schema":"pulsarmlx.f017.apple-production-serial-f32-comparison-start","attempt_id":release["attempt_id"],"invocation_id":invocation_id,"owner_sha256":owner_sha,"production_equivalence_executions":1,"real_payload_consumption":0})
        env = dict(os.environ); env.update(THREADS); env["PULSARMLX_F017_OWNED_ATTEMPT_SHA256"] = owner_sha
        command = [str(REPO / release["runner_path"]), "--package", str(PACKAGE_JSON), "--execute"]
        completed = subprocess.run(command, cwd=REPO, env=env, check=False)
        if completed.returncode:
            terminalize_owned_failure(ATTEMPT_ROOT, invocation_id, owner_sha, "RUNNER_EXIT", completed.returncode)
            return completed.returncode
        terminalize_owned_success(ATTEMPT_ROOT, CAPTURE_ROOT, invocation_id, owner_sha)
        return 0
    except BaseException as exc:
        if owner_matches(ATTEMPT_ROOT, invocation_id, owner_sha) and not (ATTEMPT_ROOT / "terminal.json").exists():
            terminalize_owned_failure(ATTEMPT_ROOT, invocation_id, owner_sha, type(exc).__name__, None)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", required=True, type=Path)
    parser.add_argument("--approval", type=Path); parser.add_argument("--go-token", type=Path)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--preflight-only", action="store_true"); modes.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    try:
        release = validate_release(args.release)
        if args.preflight_only:
            print("PRODUCTION_BINDINGS_RESOLVED_NO_ATTEMPT_NO_ARITHMETIC")
            return 0
        if args.approval is None or args.go_token is None:
            raise GateError("SEPARATE_HUMAN_APPROVAL_AND_LIVE_GO_REQUIRED")
        return execute(args.release, release, args.approval, args.go_token)
    except (GateError, ReadinessError) as exc:
        print(f"FAIL:{exc}", file=sys.stderr); return 2


if __name__ == "__main__":
    raise SystemExit(main())
