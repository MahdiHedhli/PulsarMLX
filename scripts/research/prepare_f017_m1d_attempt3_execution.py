#!/usr/bin/env python3
"""Render one immutable, non-consuming M1-D attempt-3 execution config."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import f017_m1d_execution_config as contract


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authorization-binding", type=Path, required=True)
    parser.add_argument("--local-inputs", type=Path, required=True)
    parser.add_argument("--output-config", type=Path, required=True)
    parser.add_argument("--output-render", type=Path, required=True)
    args = parser.parse_args()

    binding = contract.load_json_no_duplicates(args.authorization_binding)
    local = contract.load_json_no_duplicates(args.local_inputs)
    if binding.get("schema") != "pulsarmlx.f017.m1d-attempt-3-authorization-binding":
        raise SystemExit("wrong attempt-3 authorization binding schema")
    if binding.get("status") != "authorized_exactly_one_attempt_3_not_executed":
        raise SystemExit("attempt-3 authorization is not executable")
    if binding.get("attempt") != 3 or binding.get("attempt_consumed") is not False:
        raise SystemExit("attempt-3 authorization state mismatch")
    authorized_execution = binding.get("execution")
    expected_execution = {
        "conceptual_projection_count": 1,
        "production_repeat_count": 10,
        "native_dispatch_count": 10,
        "all_repeat_hashes_equal_required": True,
        "oracle_finalized_before_candidate_required": True,
        "preflight_consumes_attempt": False,
    }
    if authorized_execution != expected_execution:
        raise SystemExit("attempt-3 execution authorization mismatch")
    if set(local) != {"repository_root", "package_root", "environment_manifest", "checkpoint_manifest", "target_shard", "oracle_output", "package_output", "evidence_output"}:
        raise SystemExit("local input document has unbound fields")

    document = {
        "schema": contract.SCHEMA,
        "schema_version": contract.SCHEMA_VERSION,
        "status": contract.READY,
        "attempt": 3,
        "attempt_consumed": False,
        "runtime_sha": binding["runtime_sha"],
        "tooling_sha": binding["tooling_sha"],
        "repository_root": {
            "path_kind": "absolute_private_local",
            "path": local["repository_root"],
            "identity": binding["runtime_sha"],
        },
        "package_root": {
            "path_kind": "absolute_private_local",
            "path": local["package_root"],
            "identity": "m1d_attempt_3_private_package_root",
        },
        "activation_fixture": binding["activation_fixture"],
        "activation_payload_sha256": binding["activation_payload_sha256"],
        "provenance": binding["provenance"],
        "repository_artifacts": binding["repository_artifacts"],
        "local_artifacts": {
            "environment_manifest": local["environment_manifest"],
            "checkpoint_manifest": local["checkpoint_manifest"],
            "target_shard": local["target_shard"],
            "oracle_output": local["oracle_output"],
            "package_output": local["package_output"],
            "evidence_output": local["evidence_output"],
        },
        "prior_evidence": binding["prior_evidence"],
        "checkpoint_bindings": binding["checkpoint_bindings"],
        "runner": binding["runner"],
        "execution": {
            "conceptual_projection_count": authorized_execution["conceptual_projection_count"],
            "repeat_count": authorized_execution["production_repeat_count"],
            "native_dispatch_count": authorized_execution["native_dispatch_count"],
            "auto_retry": False,
            "stop_before_m1_e": True,
        },
    }
    contract.validate_execution_config(document, check_outputs_absent=True)
    config_bytes = contract.canonical_bytes(document)
    config_sha = contract.sha256(config_bytes)
    contract.exclusive_write(args.output_config, config_bytes)
    reparsed = contract.validate_config_file(args.output_config, config_sha, check_outputs_absent=True)
    if reparsed != document:
        raise SystemExit("rendered execution config does not round-trip to authorization")
    rendered = {
        "schema": "pulsarmlx.f017.m1d-attempt-3-preflight",
        "schema_version": "1.0.0",
        "status": contract.READY,
        "attempt": 3,
        "attempt_consumed": False,
        "execution_config_sha256": config_sha,
        "canonical_invocation": [
            "f017-glm52-runner",
            "--m1d-execution-config",
            args.output_config.name,
            "--execution-config-sha256",
            config_sha,
        ],
        "activation_symbolic_path": contract.ACTIVATION_PATH,
        "checkpoint_accessed": False,
    }
    contract.exclusive_write(args.output_render, contract.canonical_bytes(rendered))
    print(json.dumps(rendered, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
