#!/usr/bin/env python3
"""Checkpoint-free, fail-closed Q4K-REAL-1 authorization preflight."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


READY_STATUS = "READY_TO_EXECUTE_Q4_K_REAL_BYTE_QUALIFICATION"
ATTEMPT_ID = "Q4K-REAL-1"
AUTHORIZATION_HEAD = "aaf84218b51f9174590c2842c6b76f57cc02158e"

PATHS = {
    "amendment": "docs/architecture/reviews/evidence/f017-q4-k-authorization-state-amendment-v1.json",
    "config": "docs/architecture/reviews/evidence/f017-q4-k-execution-config-v2.json",
    "binding": "docs/architecture/reviews/evidence/f017-q4-k-authorization-binding-v2.json",
    "attempt": "docs/architecture/reviews/evidence/f017-q4-k-attempt-ledger-v1.json",
    "ledger": "docs/architecture/reviews/evidence/f017-real-payload-access-ledger-v1.json",
    "v1_config": "docs/architecture/reviews/evidence/f017-q4-k-execution-config-v1.json",
    "v1_binding": "docs/architecture/reviews/evidence/f017-q4-k-authorization-binding-v1.json",
    "handoff": "docs/architecture/reviews/evidence/f017-q4-k-real-byte-qualification-handoff-v1.json",
}


class AuthorizationError(ValueError):
    pass


def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, child in pairs:
        if key in value:
            raise AuthorizationError(f"duplicate key: {key}")
        value[key] = child
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(), object_pairs_hook=reject_duplicates)


def load_package(root: Path) -> dict[str, Any]:
    docs = {name: load_json(root / rel) for name, rel in PATHS.items()}
    docs["_root"] = root
    return docs


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AuthorizationError(message)


def validate_documents(docs: dict[str, Any]) -> str:
    root = docs["_root"]
    amendment = docs["amendment"]
    config = docs["config"]
    binding = docs["binding"]
    attempt_ledger = docs["attempt"]
    real_ledger = docs["ledger"]
    v1 = docs["v1_config"]

    # The prior non-execution and all predecessor controls are immutable.
    fixed_hashes = {
        "docs/architecture/reviews/evidence/f017-q4-k-real-byte-qualification-attempt-1-not-executed-v1.json": "c29feb1479771bd8353d8382429dca656657f9cb18b51a53a4c1ad4eab9b678b",
        "docs/architecture/reviews/f017-q4-k-real-byte-qualification-not-executed-review.md": "087b1a2fa652fadaa8e35c802030293bb00c7bd1d79c7d365a89cb2149260f59",
        PATHS["v1_config"]: "bcb3bc2b7fca752d17555fd1c1efe8d77691102f742e66483b8f42a81a35b27b",
        PATHS["v1_binding"]: "c3eea6693831c7821ae5973890754543b1be8e8f79a85674d3439c176c41ebb9",
        PATHS["handoff"]: "d4c069b4afba82715d3351b87a459345dd89e25566cba73f42c1fc75c6118e51",
        "specs/017-rust-native-inference-runtime/contracts/f017-q4-k-evidence-v1.schema.json": "c78736cba193e82fb5110cad4e636f909d0ef4c0ece70726d601c6c033835034",
        "docs/architecture/reviews/evidence/f017-m1f-minus1-boundary-v1.json": "7a9fd397f45b1b2e472ea0d4d10d6046ef9838730ad0c2bcf66380ce173c585d",
        "docs/architecture/reviews/evidence/f017-q6-k-future-package-v2.json": "f6f18044d146d251b290af1fce93e9b4a3cf54c605e98815679c386f64b04da8",
        "docs/architecture/reviews/evidence/f017-routing-contract-v3-source-trace-v1.json": "356ffad4e72d6950605a0c0afb7cef3b549000a7de15c8b61f8216370fad3832",
    }
    for rel, expected in fixed_hashes.items():
        require(sha256(root / rel) == expected, f"immutable artifact drift: {rel}")

    amendment_sha = sha256(root / PATHS["amendment"])
    config_sha = sha256(root / PATHS["config"])
    binding_sha = sha256(root / PATHS["binding"])
    require(amendment_sha == "62bb1f429fc7c1b0acc2ed7cc88391491758a9e09f62d5745fc991c67e0e502c", "amendment hash")
    require(config_sha == "fddffb9359b2cac545afe969d90211f77ca5ef2547057949f75db118522d22da", "config hash")
    require(binding_sha == "0a58ca7b1ba3b16c29e7f657b29f48cb9a6ffb4d65377d108a0b20df98dfb865", "binding hash")

    require(amendment["authorization_head"] == AUTHORIZATION_HEAD, "authorization head")
    require(config["authorization_head"] == AUTHORIZATION_HEAD, "config head")
    require(binding["authorization_head"] == AUTHORIZATION_HEAD, "binding head")
    require(amendment["attempt_id"] == ATTEMPT_ID, "amendment attempt")
    require(config["attempt"]["attempt_id"] == ATTEMPT_ID, "config attempt")
    require(binding["attempt_id"] == ATTEMPT_ID, "binding attempt")
    require(config["authorization_amendment_sha256"] == amendment_sha, "config amendment mismatch")
    require(binding["authorization_amendment_sha256"] == amendment_sha, "binding amendment mismatch")
    require(binding["execution_config_sha256"] == config_sha, "binding config mismatch")

    records = [record for record in attempt_ledger["attempts"] if record.get("attempt_id") == ATTEMPT_ID]
    require(attempt_ledger["predecessor_sha256"] == "31cd084e744a8cd33a58948cd08b61ca87446d972303ada1ed9d9ce87286578e", "attempt ledger predecessor")
    require(attempt_ledger["status"] == "AUTHORIZED_UNCONSUMED_NOT_EXECUTED", "attempt ledger status")
    require(len(records) == 1, "exact authorized attempt record required")
    record = records[0]
    require(record["gate"] == "Q4_K_REAL_BYTE_QUALIFICATION", "wrong gate")
    require(record["authorized"] is True, "attempt unauthorized")
    require(record["consumed"] is False, "attempt consumed")
    require(record["executed"] is False, "attempt executed")
    require(record["checkpoint_accessed"] is False, "checkpoint accessed")
    require(record["authorization_head"] == AUTHORIZATION_HEAD, "attempt authorization head")
    require(record["authorization_artifact_sha256"] == amendment_sha, "attempt amendment mismatch")
    require(record["execution_config_sha256"] == config_sha, "attempt config mismatch")
    require(record["authorization_binding_sha256"] == binding_sha, "attempt binding mismatch")
    require(record["handoff_sha256"] == "d4c069b4afba82715d3351b87a459345dd89e25566cba73f42c1fc75c6118e51", "attempt handoff")
    require(record["ledger_before"] == 57, "ledger-before mismatch")
    require(record["expected_success_ledger_after"] == 58, "success-ledger mismatch")

    for source in (record, config["attempt"], binding["attempt"], amendment["controls"]):
        require(source["automatic_retry"] is False, "automatic retry enabled")
    for source in (record, config["continuation"], binding, amendment["controls"]):
        require(source["automatic_q6_continuation"] is False, "Q6 continuation enabled")
        require(source["automatic_dense_prefix_continuation"] is False, "dense-prefix continuation enabled")
    require(config["execution_authorized"] is True and binding["execution_authorized"] is True, "execution not authorized")
    require(binding["wildcard_authorization"] is False and amendment["controls"]["wildcard_authorization"] is False, "wildcard authorization")

    # Numerical and target semantics are copied exactly from the immutable v1 control.
    require(config["checkpoint_bindings"] == v1["checkpoint_bindings"], "checkpoint binding drift")
    require(config["target"] == v1["target"], "target drift")
    require(config["access_budget"]["shard_opens"] == v1["access_budget"]["shard_opens"], "shard budget drift")
    require(config["access_budget"]["positional_reads"] == v1["access_budget"]["positional_reads"], "read budget drift")
    require(config["access_budget"]["tensor_payloads"] == v1["access_budget"]["tensor_payloads"], "payload budget drift")
    require(config["access_budget"]["candidate_model_compute"] == 0, "model compute authorized")
    require(config["access_budget"]["mlx_candidate_dispatches"] == 0, "MLX compute authorized")
    require(config["decoder_contract"]["comparison"] == v1["decoder_contract"]["comparison"], "comparison drift")
    require(config["decoder_contract"]["contract_id"] == v1["decoder_contract"]["contract_id"], "format contract drift")
    require(config["decoder_contract"]["format_contract_sha256"] == "bbdb296744910dbec5e95496d73df62b1e1b5cae4a9438b41de9962385399305", "format contract hash drift")
    require(binding["format_contract_sha256"] == config["decoder_contract"]["format_contract_sha256"], "binding format contract drift")
    require(config["decoder_contract"]["format"] == v1["decoder_contract"]["format"], "format semantics drift")
    require(config["access_budget"]["packed_bytes"] == config["target"]["packed_length"], "packed-byte budget drift")
    for new, old in zip(config["decoder_contract"]["implementations"], v1["decoder_contract"]["implementations"], strict=True):
        for field in ("name", "language", "source_file", "source_sha256", "symbol", "implementation_sha256", "classification"):
            require(new[field] == old[field], f"decoder identity drift: {field}")

    require(real_ledger["cumulative_tensor_payloads"] == 57, "real ledger changed")
    require(amendment["real_checkpoint_access"] == 0, "amendment accessed checkpoint")
    require(attempt_ledger["real_checkpoint_access"] == 0, "attempt ledger accessed checkpoint")
    require(amendment["preflight_ready_status"] == READY_STATUS, "READY status drift")
    return READY_STATUS


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    print(validate_documents(load_package(args.repository_root.resolve())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
