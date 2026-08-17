#!/usr/bin/env python3
"""Public validator for the F017 production recovery binding package."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-canonical-expert-recovery-production-binding-v1.json"
EVIDENCE = ROOT / "docs/architecture/reviews/evidence/f017-canonical-expert-recovery-production-binding-v1.json"


def load(path: Path) -> dict:
    def no_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate key: {key}")
            result[key] = value
        return result
    return json.loads(path.read_text(), object_pairs_hook=no_duplicates)


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha256(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate() -> str:
    contract = load(CONTRACT)
    evidence = load(EVIDENCE)
    require(contract["status"] == "PRODUCTION RECOVERY EXECUTION SURFACE READY FOR INDEPENDENT REVIEW", "status")
    require(len(contract["production_surfaces"]) == 14, "surface count")
    require(contract["budget"] == {"reads": 24, "packed_bytes": 90439680, "ledger_before": 139,
                                  "ledger_after_success": 163, "automatic_retry": False,
                                  "second_attempt": False}, "budget")
    for item in contract["source_files"].values():
        path = ROOT / item["path"]
        require(path.is_file() and sha256_path(path) == item["sha256"], f"source identity: {item['path']}")
    support = contract["supporting_production_bindings"]
    binary = ROOT / "target/debug/f017-canonical-decode"
    if binary.exists():
        require(binary.is_file() and sha256_path(binary) == support["rust_decoder_binary_sha256"], "Rust decoder binary identity")
    require(len(support["fresh_process_reproduction_runner"]) == 64, "reproduction runner identity")
    require(evidence["contract_sha256"] == canonical_sha256(contract), "contract canonical identity")
    require(evidence["preflight"]["surface_count"] == 14, "preflight surface count")
    require(evidence["preflight"]["result"] == "PRODUCTION_BINDINGS_RESOLVED", "preflight result")
    require(evidence["synthetic_integration"]["result"] == "PASS", "synthetic integration")
    require(evidence["decoder_independence"]["result"] == "PASS", "decoder independence")
    require(evidence["real_path_call_graph_audit"]["result"] == "PASS", "call graph")
    require(contract["loop_effects"] == {"checkpoint_reads": 0, "shard_opens": 0,
                                         "real_payload_ledger": 139, "attempt_record_created": False,
                                         "execution_start_created": False, "real_outputs_generated": False}, "loop effects")
    public = CONTRACT.read_text() + EVIDENCE.read_text()
    require(not re.search(r"(?:/Users/|/home/|file://|\.pulsarmlx-local)", public), "private path leak")
    return canonical_sha256(contract)


def main() -> int:
    print(validate())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
