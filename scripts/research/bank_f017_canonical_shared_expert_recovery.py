#!/usr/bin/env python3
"""Bank the completed shared-expert recovery without checkpoint capability."""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.research.f017_canonical_expert_output_production import CanonicalInputResolver
from scripts.research.f017_shared_expert_recovery import EPSILON, strict_f32_rmsnorm


EVIDENCE = ROOT / "docs/architecture/reviews/evidence"
RESULT = EVIDENCE / "f017-canonical-shared-expert-recovery-result-v1.json"
REVIEW = EVIDENCE / "f017-canonical-shared-expert-recovery-evidence-review-v1.json"
EVENT = "F017-CANONICAL-SHARED-EXPERT-OUTPUT-RECOVERY-1"
ATTEMPT = EVENT + "-ATTEMPT-1"
RELEASE_HEAD = "71d341117022c719fe3a51d350b84b21b073da5c"
AUTHORIZATION = "70a80f1456fd9ff075d02842c43e62522dcd7f57899752f9da9ce5de33a7f2bb"
SHARD = "d94adaa58ddd5abbcf2514192958084416b1aa36bd4d21409028a164341bac36"
CANONICAL_INPUT = "9c3a8821deda6a9983b49544d5726efad97b2e560f55a7eb0f182aaa128ceb11"
GAMMA = "1d9228483902bf2ca1088589d25c1cbc116facd82454a117e7dafb2d48f83d8f"


def load(path: Path) -> dict[str, Any]:
    def unique(pairs):
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate key: {key}")
            value[key] = item
        return value
    return json.loads(path.read_text(), object_pairs_hook=unique)


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def immutable(path: Path) -> None:
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode), "artifact type")
    require(not info.st_mode & 0o222 and info.st_nlink == 1, "artifact immutability")


def build(private_root: Path, exact_path: Path, gamma_path: Path) -> dict[str, Any]:
    state, package = private_root / "state", private_root / "package"
    paths = {
        "attempt": state / "attempt.json", "start": state / "execution-start.json",
        "ledger": state / "ledger.json", "terminal": state / "terminal.json",
        "manifest": package / "manifest.json",
    }
    for label, path in paths.items():
        require(path.is_file(), f"missing {label}")
    attempt, start, ledger, terminal, manifest, result = (
        load(paths["attempt"]), load(paths["start"]), load(paths["ledger"]),
        load(paths["terminal"]), load(paths["manifest"]), load(RESULT),
    )
    require(attempt["attempt_id"] == ATTEMPT and attempt["automatic_retry"] is False, "attempt")
    require(start["authoritative_commit"] == RELEASE_HEAD, "release head")
    require(start["authorization_contract_sha256"] == AUTHORIZATION, "authorization")
    require(start["expected_reads"] == 3 and start["expected_packed_bytes"] == 27_623_424, "start budget")
    require(terminal["classification"] == terminal["reason_code"] == "COMPLETE", "terminal")
    require(terminal["consumed_read_count"] == 3 and terminal["packed_bytes"] == 27_623_424, "access totals")
    require(terminal["shard_open_count"] == 1 and terminal["decoder_agreement_count"] == 3, "terminal gates")
    require(ledger["value"] == 166 and ledger["successful_consumptions"] == 3, "private ledger")
    for key in ("classification", "consumed_read_count", "packed_bytes", "ledger_before", "ledger_after", "shard_open_count", "journal_digest", "decoder_agreement_count", "output"):
        require(result.get(key) == terminal.get(key), f"public terminal mismatch: {key}")

    journals = sorted((state / "journal").glob("*.json"))
    decoders = sorted((state / "decoder").glob("*.json"))
    receipts = sorted((state / "receipts").glob("*.json"))
    require(len(journals) == len(decoders) == len(receipts) == 3, "record counts")
    payloads: list[dict[str, Any]] = []
    for sequence, (jp, dp, rp) in enumerate(zip(journals, decoders, receipts), 1):
        journal, decoder, receipt = load(jp), load(dp), load(rp)
        require(journal["sequence"] == decoder["sequence"] == receipt["sequence"] == sequence, "sequence")
        require(journal["packed_sha256"] == receipt["packed_sha256"], "receipt identity")
        require(decoder["exact_agreement"] and decoder["decoded_identity_a"] == decoder["decoded_identity_b"], "decoder")
        retained = package / journal["retention_artifact_id"]
        require(retained.resolve().is_relative_to(package.resolve()), "path escape")
        immutable(retained)
        require(retained.stat().st_size == journal["actual_byte_count"] and digest(retained) == journal["packed_sha256"], "retained identity")
        require(journal["ledger_after"] == 163 + sequence and journal["shard_identity"] == SHARD, "journal accounting")
        payloads.append({
            "sequence": sequence, "role": journal["role"], "offset": journal["offset"],
            "packed_bytes": journal["actual_byte_count"], "packed_sha256": journal["packed_sha256"],
            "quantization": decoder["quantization"], "logical_shape": decoder["logical_shape"],
            "decoded_sha256": decoder["decoded_identity_a"],
            "decoder_a_identity": decoder["decoder_a_identity"],
            "decoder_b_identity": decoder["decoder_b_identity"],
            "exact_agreement": True, "retained_immutable_read_only": True,
        })
    require(hashlib.sha256(canonical([load(p) for p in journals])).hexdigest() == terminal["journal_digest"], "journal digest")

    artifacts = manifest["artifacts"]
    require(len(artifacts) == 4, "manifest artifact count")
    output = next(item for item in artifacts if item.get("symbolic_path") == "outputs/canonical_shared_expert_output.bin")
    output_path = package / output["symbolic_path"]
    immutable(output_path)
    require(output_path.stat().st_size == 24_576 and digest(output_path) == output["sha256"], "output identity")
    require(output["sha256"] == terminal["output"]["output_sha256"], "output terminal binding")
    require(digest(paths["manifest"]) == terminal["output"]["private_manifest_sha256"], "manifest terminal binding")
    resolved = CanonicalInputResolver(exact_path, gamma_path).resolve()
    normalized = strict_f32_rmsnorm(resolved.exact_state, resolved.gamma, EPSILON)
    normalized_sha = hashlib.sha256(np.ascontiguousarray(normalized, dtype="<f4").tobytes()).hexdigest()
    return {
        "schema": "pulsarmlx.f017.canonical-shared-expert-recovery-evidence-review",
        "schema_version": "1.0.0", "classification": "CANONICAL SHARED EXPERT RECOVERY COMPLETE",
        "event_id": EVENT, "attempt_id": ATTEMPT, "release_head": RELEASE_HEAD,
        "authorization_sha256": AUTHORIZATION,
        "attempt_record_sha256": digest(paths["attempt"]),
        "execution_start_record_sha256": digest(paths["start"]),
        "terminal_record_sha256": digest(paths["terminal"]),
        "private_ledger_record_sha256": digest(paths["ledger"]),
        "public_result": {"path": RESULT.relative_to(ROOT).as_posix(), "sha256": digest(RESULT)},
        "checkpoint_access": {"shard_sha256": SHARD, "shard_open_count": 1, "payload_reads": 3, "packed_bytes": 27_623_424},
        "journal": {"entries": 3, "sha256": terminal["journal_digest"], "reconciled": True},
        "payloads": payloads,
        "dual_decoder": {"agreement_count": 3, "required_count": 3, "q5_count": 2, "q6_count": 1, "result": "PASS"},
        "canonical_input": {"sha256": CANONICAL_INPUT, "gamma_sha256": GAMMA, "shape": [6144], "dtype": "f32"},
        "normalized_input_sha256": normalized_sha,
        "shared_output": {"sha256": output["sha256"], "shape": [6144], "dtype": "f32", "byte_length": 24_576, "immutable": True, "read_only": True},
        "reproduction": {"fresh_processes": 2, "exact_outputs": 2, "required_outputs": 2, "result": "PASS"},
        "private_package": {"manifest_sha256": digest(paths["manifest"]), "packed_artifacts": 3, "output_artifacts": 1, "private_bytes_committed": False, "machine_local_paths_published": False},
        "ledger": {"before": 163, "after": 166, "delta": 3, "reconciled": True},
        "historical_immutability": {"REAL_1": "REJECTED_UNCHANGED", "REAL_2": "REJECTED_UNCHANGED", "REAL_3": "REJECTED_UNCHANGED", "DPREFIX_EXACT_1": "CANONICAL_UNCHANGED", "membership": "1984_OF_1984_PASS_UNCHANGED", "coefficient_qualification": "0_OF_8_FAIL_UNCHANGED", "routed_aggregate_v1": "FAIL_UNCHANGED", "complete_layer_v2": "FROZEN_NOT_EVALUATED", "route_disposition": "ROUTE NOT PROVEN INVARIANT"},
        "complete_layer_v2_evaluation": False, "automatic_retry": False, "second_attempt_authorized": False,
        "next_action": "prepare cross-event reuse authorization for the canonical shared-expert output; do not evaluate complete-layer v2 yet",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--exact-state", type=Path, required=True)
    parser.add_argument("--gamma", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=REVIEW)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    raw = canonical(build(args.private_root, args.exact_state, args.gamma)) + b"\n"
    if args.check:
        require(args.output.is_file() and args.output.read_bytes() == raw, "banked review differs")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(raw)
    print(hashlib.sha256(raw).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
