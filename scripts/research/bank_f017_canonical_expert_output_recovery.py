#!/usr/bin/env python3
"""Bank the completed F017 canonical expert-output recovery public evidence.

This closeout reads only the event's retained private package and durable event
records.  It has no checkpoint-path argument and performs no model or aggregate
computation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/architecture/reviews/evidence"
AUTHORIZATION = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-canonical-expert-output-recovery-v1.json"
PUBLIC_RESULT = EVIDENCE / "f017-canonical-expert-recovery-result-v1.json"
PUBLIC_REVIEW = EVIDENCE / "f017-canonical-expert-output-recovery-evidence-review-v1.json"
EVENT_ID = "F017-CANONICAL-EXPERT-OUTPUT-RECOVERY-1"
ATTEMPT_ID = f"{EVENT_ID}-ATTEMPT-1"
RELEASE_HEAD = "8233396c6aa07ef05474f37db470ff44044ed5cd"
CANONICAL_INPUT_SHA256 = "9c3a8821deda6a9983b49544d5726efad97b2e560f55a7eb0f182aaa128ceb11"
SHARD_SHA256 = "d94adaa58ddd5abbcf2514192958084416b1aa36bd4d21409028a164341bac36"


def load(path: Path) -> dict[str, Any]:
    def reject_duplicates(pairs):
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate JSON key: {key}")
            value[key] = item
        return value
    return json.loads(path.read_text(), object_pairs_hook=reject_duplicates)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def regular_read_only_single_link(path: Path) -> None:
    metadata = path.lstat()
    require(stat.S_ISREG(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode), f"artifact type: {path.name}")
    require(not metadata.st_mode & 0o222, f"artifact writable: {path.name}")
    require(metadata.st_nlink == 1, f"artifact alias count: {path.name}")


def build(private_root: Path) -> dict[str, Any]:
    state = private_root / "event-state"
    package = private_root / "recovery-package"
    required = {
        "attempt": state / "attempt.json",
        "execution_start": state / "execution-start.json",
        "terminal": state / "terminal.json",
        "private_ledger": state / "ledger.json",
        "private_manifest": package / "manifest.json",
    }
    for label, path in required.items():
        require(path.is_file(), f"missing {label}")

    authorization = load(AUTHORIZATION)
    public_result = load(PUBLIC_RESULT)
    attempt = load(required["attempt"])
    execution_start = load(required["execution_start"])
    terminal = load(required["terminal"])
    private_ledger = load(required["private_ledger"])
    manifest = load(required["private_manifest"])
    inventory = authorization["payload_inventory"]

    require(attempt["attempt_id"] == ATTEMPT_ID and attempt["automatic_retry"] is False, "attempt state")
    require(execution_start["attempt_id"] == ATTEMPT_ID, "execution-start attempt")
    require(execution_start["expected_reads"] == 24 and execution_start["expected_packed_bytes"] == 90_439_680, "execution-start budget")
    require(terminal["classification"] == "COMPLETE" and terminal["reason_code"] == "COMPLETE", "terminal classification")
    require(terminal["consumed_read_count"] == 24 and terminal["packed_bytes"] == 90_439_680, "terminal access totals")
    require(terminal["shard_open_count"] == 1 and terminal["decoder_agreement_count"] == 24, "terminal gates")
    require(terminal["two_process_exact_reproduction"] is True and terminal["two_process_reproduction_count"] == 2, "reproduction")
    require(private_ledger == {
        "schema": "pulsarmlx.f017.canonical-expert-recovery-private-ledger",
        "schema_version": "1.0.0", "event_id": EVENT_ID,
        "ledger_before": 139, "successful_consumptions": 24, "value": 163,
    }, "private ledger")
    for key in ("classification", "consumed_read_count", "packed_bytes", "ledger_before", "ledger_after",
                "shard_open_count", "journal_digest", "decoder_agreement_count",
                "output_sha256_by_expert", "two_process_exact_reproduction"):
        require(public_result.get(key) == terminal.get(key), f"public/terminal mismatch: {key}")

    journal_paths = sorted((state / "journal").glob("*.json"))
    decoder_paths = sorted((state / "decoder").glob("*.json"))
    receipt_paths = sorted((state / "consumption").glob("*.json"))
    require(len(journal_paths) == len(decoder_paths) == len(receipt_paths) == len(inventory) == 24, "record counts")
    payloads: list[dict[str, Any]] = []
    total = 0
    for index, (entry, journal_path, decoder_path, receipt_path) in enumerate(
        zip(inventory, journal_paths, decoder_paths, receipt_paths), start=1
    ):
        journal = load(journal_path)
        decoder = load(decoder_path)
        receipt = load(receipt_path)
        require(journal["sequence"] == decoder["sequence"] == receipt["sequence"] == index, "sequence")
        require(journal["expert_id"] == decoder["expert_id"] == receipt["expert_id"] == entry["expert_id"], "expert")
        require(journal["tensor_role"] == decoder["role"] == receipt["role"] == entry["role"], "role")
        require(journal["offset"] == receipt["offset"] == entry["offset"], "offset")
        require(journal["actual_byte_count"] == journal["requested_byte_count"] == receipt["actual_byte_count"] == entry["packed_length"], "byte count")
        require(journal["ledger_after"] == receipt["ledger_after"] == 139 + index, "per-read ledger")
        require(journal["shard_identity"] == SHARD_SHA256, "shard identity")
        require(journal["packed_sha256"] == decoder["packed_sha256"] == receipt["packed_sha256"], "packed identity records")
        require(decoder["exact_agreement"] is True and decoder["decoded_identity_a"] == decoder["decoded_identity_b"], "decoder agreement")
        retained = state / journal["retention_artifact_id"]
        require(retained.resolve().is_relative_to(state.resolve()), "retained path escape")
        regular_read_only_single_link(retained)
        require(retained.stat().st_size == entry["packed_length"] and sha256(retained) == journal["packed_sha256"], "retained identity")
        total += entry["packed_length"]
        payloads.append({
            "sequence": index,
            "checkpoint_key": entry["checkpoint_key"],
            "expert_id": entry["expert_id"],
            "role": entry["role"],
            "offset": entry["offset"],
            "packed_bytes": entry["packed_length"],
            "quantization": entry["quantization"],
            "logical_shape": entry["logical_decoded_shape"],
            "packed_sha256": journal["packed_sha256"],
            "decoded_sha256": decoder["decoded_identity_a"],
            "decoder_a_identity": decoder["decoder_a_identity"],
            "decoder_b_identity": decoder["decoder_b_identity"],
            "exact_agreement": True,
            "retained_immutable_read_only": True,
        })
    require(total == 90_439_680, "packed total")
    require(canonical_sha256([load(path) for path in journal_paths]) == terminal["journal_digest"], "journal digest")

    artifacts = manifest["artifacts"]
    require(len(artifacts) == 8, "output count")
    require([item["expert_id"] for item in artifacts] == authorization["selected_expert_ids"], "output expert ordering")
    outputs: list[dict[str, Any]] = []
    normalized = {item["normalized_input_sha256"] for item in artifacts}
    require(len(normalized) == 1, "normalized input identity")
    for item in artifacts:
        output_path = package / item["symbolic_path"]
        require(output_path.resolve().is_relative_to(package.resolve()), "output path escape")
        regular_read_only_single_link(output_path)
        require(output_path.stat().st_size == 24_576 and sha256(output_path) == item["sha256"], "output identity")
        require(item["canonical_input_sha256"] == CANONICAL_INPUT_SHA256, "canonical input")
        require(item["shape"] == [6144] and item["dtype"] == "f32", "output surface")
        outputs.append({
            "expert_id": item["expert_id"], "sha256": item["sha256"],
            "shape": [6144], "dtype": "f32", "byte_length": 24_576,
            "canonical_input_sha256": item["canonical_input_sha256"],
            "normalized_input_sha256": item["normalized_input_sha256"],
            "immutable": True, "read_only": True,
        })
    require({str(item["expert_id"]): item["sha256"] for item in artifacts} == public_result["output_sha256_by_expert"], "output/public mismatch")
    require(sha256(required["private_manifest"]) == public_result["private_manifest_sha256"], "manifest/public mismatch")

    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", execution_start["authoritative_commit"], RELEASE_HEAD],
        cwd=ROOT, check=False,
    ).returncode == 0
    require(ancestor, "execution substrate ancestry")
    return {
        "schema": "pulsarmlx.f017.canonical-expert-output-recovery-evidence-review",
        "schema_version": "1.0.0",
        "classification": "CANONICAL EXPERT OUTPUT RECOVERY COMPLETE",
        "event_id": EVENT_ID,
        "attempt_id": ATTEMPT_ID,
        "release_head": RELEASE_HEAD,
        "execution_start_bound_substrate_head": execution_start["authoritative_commit"],
        "execution_start_substrate_is_ancestor_of_release": True,
        "production_contract_sha256": "c921bca7f4d42a6e42ae1b4b337bf3baea7e7088d5e442d271ec9838665e19d8",
        "authorization_sha256": execution_start["authorization_contract_sha256"],
        "attempt_record_sha256": sha256(required["attempt"]),
        "execution_start_record_sha256": sha256(required["execution_start"]),
        "terminal_record_sha256": sha256(required["terminal"]),
        "private_ledger_record_sha256": sha256(required["private_ledger"]),
        "public_result": {"path": PUBLIC_RESULT.relative_to(ROOT).as_posix(), "sha256": sha256(PUBLIC_RESULT)},
        "checkpoint_access": {"shard_sha256": SHARD_SHA256, "shard_open_count": 1,
                              "payload_reads": 24, "packed_bytes": 90_439_680},
        "journal": {"entries": 24, "sha256": terminal["journal_digest"], "reconciled": True},
        "payloads": payloads,
        "dual_decoder": {"agreement_count": 24, "required_count": 24, "result": "PASS"},
        "canonical_expert_input": {"sha256": CANONICAL_INPUT_SHA256, "shape": [6144], "dtype": "f32"},
        "normalized_expert_input_sha256": next(iter(normalized)),
        "outputs": outputs,
        "reproduction": {"fresh_processes": 2, "exact_outputs": 8, "required_outputs": 8, "result": "PASS"},
        "private_package": {"manifest_sha256": sha256(required["private_manifest"]),
                            "packed_artifacts": 24, "output_artifacts": 8,
                            "private_bytes_committed": False, "machine_local_paths_published": False},
        "ledger": {"before": 139, "after": 163, "delta": 24, "reconciled": True},
        "historical_immutability": {
            "REAL_1": "REJECTED_UNCHANGED", "REAL_2": "REJECTED_UNCHANGED",
            "REAL_3": "REJECTED_UNCHANGED", "DPREFIX_EXACT_1": "CANONICAL_UNCHANGED",
            "membership": "1984_OF_1984_PASS_UNCHANGED",
            "coefficient_qualification": "0_OF_8_FAIL_UNCHANGED",
            "route_disposition": "ROUTE NOT PROVEN INVARIANT",
        },
        "aggregate_evaluation": False,
        "automatic_retry": False,
        "second_attempt_authorized": False,
        "next_action": "prepare cross-event reuse authorization for the eight canonical expert outputs; do not evaluate the aggregate theorem yet",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=PUBLIC_REVIEW)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    value = build(args.private_root)
    raw = canonical_bytes(value) + b"\n"
    if args.check:
        require(args.output.is_file() and args.output.read_bytes() == raw, "banked public evidence differs")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(raw)
    print(hashlib.sha256(raw).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
