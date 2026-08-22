#!/usr/bin/env python3
"""Build the append-only D3.5 comparison-read grant from pinned authority.

This builder reads metadata documents only.  It deliberately does not open any
retained numerical payload or native capture file.  Payload reads are reserved
for the accepted Rust grading consumer and are receipted there.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HISTORICAL_BRANCH = "feat/017-real-checkpoint-runner"
HISTORICAL_HEAD = "f2a7aa38c96b85cf7939c8ed653076732f066222"
D0 = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-numeric-acceptance-contract-v2.json"
D35 = ROOT / "docs/architecture/reviews/evidence/f017-native-retained-qualification-execution-evidence-v1.json"
DISCLOSURE = ROOT / "docs/architecture/reviews/evidence/f017-native-d3-5-ungranted-diagnostic-read-disclosure-v1.json"
OLD_GRANT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-native-representative-retention-reuse-grant-v1.json"
SOURCE = ROOT / "crates/f017-native/src/bin/d35_grader.rs"
CAPTURE_MANIFEST = Path.home() / ".local/share/pulsarmlx/f017/native-representative-retained-qualification-1/captures/same-00/capture-manifest.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(), object_pairs_hook=_no_duplicates)


def _no_duplicates(pairs: list[tuple[str, object]]) -> dict:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=False) + "\n")


def expected_inventory(old_grant: dict, disclosure: dict) -> list[dict]:
    s0 = old_grant["allowed_reads"][0]
    rows = [{
        "role": "expected.input_hidden",
        "path": s0["path"], "sha256": s0["sha256"], "byte_count": s0["byte_count"],
        "dtype": "F32_LE", "shape": [6144], "serialization": "CANONICAL_LITTLE_ENDIAN_F32_CONTIGUOUS",
        "source_branch": s0["source_branch"], "source_commit": s0["source_commit"],
        "source_authority_path": s0["source_authority_path"], "source_authority_sha256": s0["source_authority_sha256"],
        "allowed_purpose": "D0_BYTE_EXACT_EXPECTED_INPUT_HIDDEN",
    }]
    details = {
        "representative-s1.f32le": ("expected.post_attention_residual", "F32_LE", [6144], "f017-representative-s1-output-reuse-authorization-v1.json", "5c6437f2ab6ae2d01acc765430880195211e892dfb612fbb3b4125d9038ffe13"),
        "router_normalized.f32le": ("expected.router_normalized", "F32_LE", [6144], "f017-representative-m1f0-router-reuse-authorization-v2.json", "c46b00cb263347e1a345b1766fd1e36d3758c6e21ae15674bfe8dfc8841f21a1"),
        "routed-aggregate.f64le": ("expected.routed_aggregate", "F64_LE", [6144], "f017-representative-routed-aggregate-reuse-authorization-v1.json", "f04a1eb901f4c738f421b34cc065e2ca20b8938ae00e49ee17e67aeffd99fdfb"),
        "representative-shared-expert-output.f32le": ("expected.shared_expert_output", "F32_LE", [6144], "f017-representative-shared-expert-output-reuse-authorization-v1.json", "3642200f50f2ed7140243cd885dfe8c3d8628f5605ab37467cc342ea6376019a"),
        "representative-ffn-output.f64le": ("expected.production_ffn", "F64_LE", [6144], "f017-representative-ffn-output-reuse-authorization-v1.json", "983b119970f8d60bddb887d4478455b4d9eb638c3dc90853319cc302f290cd06"),
        "representative-s2.f32le": ("expected.production_s2", "F32_LE", [6144], "f017-representative-s2-output-reuse-authorization-v1.json", "35b7c6232858577c6b523fd416820845255eb094ca8be8102d9dd01f2b1b77b5"),
    }
    expert_shas = ["1b8b053d60f87c9da8c8c81a41a3d82f7652859a2464941c39b5a1eab3d7c070"] * 8
    for index in range(8):
        name = f"{index:02d}-expert-"
        for item in disclosure["diagnostic_retained_artifact_reads"]:
            if name in Path(item["path"]).name:
                details[Path(item["path"]).name] = (f"expected.expert_down.{index}", "F32_LE", [6144], "f017-representative-expert-output-reuse-authorization-v1.json", expert_shas[index])
    for item in disclosure["diagnostic_retained_artifact_reads"]:
        name = Path(item["path"]).name
        if name not in details:
            continue
        role, dtype, shape, authority_name, authority_sha = details[name]
        rows.append({
            "role": role, "path": item["path"], "sha256": item["sha256"],
            "byte_count": (8 if dtype == "F64_LE" else 4) * _product(shape),
            "dtype": dtype, "shape": shape,
            "serialization": f"CANONICAL_LITTLE_ENDIAN_{dtype.split('_')[0]}_CONTIGUOUS",
            "source_branch": HISTORICAL_BRANCH, "source_commit": HISTORICAL_HEAD,
            "source_authority_path": f"specs/017-rust-native-inference-runtime/contracts/{authority_name}",
            "source_authority_sha256": authority_sha,
            "allowed_purpose": "D0_EXPECTED_ARTIFACT_OR_INDEPENDENT_REFERENCE_CROSSCHECK",
        })
    if len(rows) != 15:
        raise SystemExit(f"expected inventory must contain 15 rows, got {len(rows)}")
    return rows


def _product(values: list[int]) -> int:
    result = 1
    for value in values:
        result *= value
    return result


def portable(path: str | Path) -> str:
    resolved = str(Path(path).resolve())
    home = str(Path.home().resolve())
    root = str(ROOT.resolve())
    if resolved == home or resolved.startswith(home + "/"):
        return "${HOME}" + resolved[len(home):]
    if resolved == root or resolved.startswith(root + "/"):
        return "${REPOSITORY_ROOT}" + resolved[len(root):]
    raise ValueError(f"path is outside bound roots: {resolved}")


def operand_inventory(old_grant: dict) -> list[dict]:
    rows = []
    for source in old_grant["allowed_reads"]:
        rows.append({
            "role": f"operand.{source['role']}", "path": source["path"], "sha256": source["sha256"],
            "byte_count": source["byte_count"], "dtype": source["encoding"], "shape": source["shape"],
            "serialization": source["decoder_binding"], "source_branch": source["source_branch"],
            "source_commit": source["source_commit"], "source_authority_path": source["source_authority_path"],
            "source_authority_sha256": source["source_authority_sha256"],
            "allowed_purpose": "OPERAND_CONDITIONED_F64_ORACLE_AND_CAP_DERIVATION_ONLY",
        })
    if len(rows) != 40:
        raise SystemExit("operand census must be 40")
    return rows


def mapping_and_captures(manifest: dict) -> tuple[dict, list[dict]]:
    if len(manifest["stages"]) != 34:
        raise SystemExit("capture stage census must be 34")
    mapping = {
        "schema": "pulsarmlx.f017.native-d3-5-canonical-stage-mapping/1.0.0",
        "mapping_id": "F017-NATIVE-D3_5-CANONICAL-STAGE-MAPPING-1",
        "source_capture_manifest_sha256": digest(CAPTURE_MANIFEST),
        "stage_count": 34,
        "rows": [],
        "policy": {"producer_role_validated_before_alias": True, "implicit_mapping": False, "direct_production_copy_allowed_for_recomputed_stage": False},
    }
    captures = []
    root = CAPTURE_MANIFEST.parent
    for stage in manifest["stages"]:
        mapping["rows"].append({
            "ordinal": stage["ordinal"], "native_stage_id": stage["stage_id"], "canonical_stage_id": stage["stage_id"],
            "semantic_role": f"CANONICAL_F017_APPLE_SERIAL_F32_STAGE_{stage['stage_id'].upper()}",
            "dtype": stage["dtype"], "shape": stage["shape"],
            "serialization": "CANONICAL_LITTLE_ENDIAN_CONTIGUOUS_NO_METADATA",
            "comparison_profile": "RESOLVED_BY_D0_V2_STAGE_ROW",
            "oracle_authority": "RESOLVED_BY_D0_V2_STAGE_ROW",
            "production_method": "NATIVE_RECOMPUTATION" if stage["ordinal"] else "RETAINED_DIRECT_VALUE",
            "diagnostic_only": False,
        })
        captures.append({
            "role": f"capture.{stage['stage_id']}", "path": str(root / stage["path"]), "sha256": stage["sha256"],
            "byte_count": stage["byte_length"], "dtype": "U16_LE" if "u16" in stage["dtype"] else "F32_LE",
            "shape": stage["shape"], "serialization": "CANONICAL_LITTLE_ENDIAN_CONTIGUOUS_NO_METADATA",
            "source_branch": "feat/017-rust-native-inference-runtime", "source_commit": "f38dc2756bd4949e8883d6afc33b324fe264dd19",
            "source_authority_path": "docs/architecture/reviews/evidence/f017-native-retained-qualification-execution-evidence-v1.json",
            "source_authority_sha256": digest(D35), "allowed_purpose": "GRADE_EXISTING_IMMUTABLE_D3_5_CAPTURE_ONLY",
        })
    return mapping, captures


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--mapping-out", type=Path, required=True)
    parser.add_argument("--grant-out", type=Path, required=True)
    args = parser.parse_args()
    old_grant, disclosure, capture = load(OLD_GRANT), load(DISCLOSURE), load(CAPTURE_MANIFEST)
    mapping, captures = mapping_and_captures(capture)
    write(args.mapping_out, mapping)
    expected = expected_inventory(old_grant, disclosure)
    operands = operand_inventory(old_grant)
    all_rows = expected + operands + captures
    for ordinal, row in enumerate(all_rows):
        row["ordinal"] = ordinal
    grant = {
        "schema": "pulsarmlx.f017.native-d3-5-comparison-read-grant/1.0.0", "schema_version": "1.0.0",
        "grant_id": "F017-NATIVE-D3_5-COMPARISON-READ-GRANT-1", "status": "INDEPENDENT_REVIEW_ACCEPT_REQUIRED_BEFORE_USE",
        "consumer": {"id": "F017-NATIVE-D3_5-NUMERICAL-GRADER-1", "executable_path": portable(args.executable),
                     "executable_sha256": digest(args.executable), "source_path": str(SOURCE.relative_to(ROOT)), "source_sha256": digest(SOURCE)},
        "authority": {
            "d0_path": str(D0.relative_to(ROOT)), "d0_sha256": digest(D0),
            "d3_5_evidence_path": str(D35.relative_to(ROOT)), "d3_5_evidence_sha256": digest(D35),
            "stage_mapping_path": str(args.mapping_out.resolve().relative_to(ROOT)), "stage_mapping_sha256": digest(args.mapping_out),
            "historical_master_ledger_path": "docs/architecture/reviews/evidence/f017-real-payload-access-ledger-v2.json",
            "historical_master_ledger_sha256": "aa98f5cc7f1cfae1eb49a9bc64dbefec1d6ef9ccae1504a1aa8879a8edf22e3e",
            "historical_master_terminal": 175,
            "diagnostic_disclosure_path": str(DISCLOSURE.relative_to(ROOT)), "diagnostic_disclosure_sha256": digest(DISCLOSURE),
            "diagnostic_metrics_reusable": False,
        },
        "event": {"event_id": "F017-NATIVE-D3_5-NUMERICAL-GRADING-1", "attempt_id": "F017-NATIVE-D3_5-NUMERICAL-GRADING-1-ATTEMPT-1",
                  "attempts": 1, "retries": 0, "resume": False, "numerical_reexecution": False, "native_capture_regeneration": False,
                  "historical_payload_ledger_delta": 0, "original_checkpoint_reads": 0, "original_checkpoint_shard_opens": 0,
                  "terminal_semantics": "ONE_OWNED_ATTEMPT_COMPLETE_OR_TERMINAL_FAILURE_NO_RETRY_NO_RESUME"},
        "allowed_output_root": "${HOME}/.local/share/pulsarmlx/f017/native-d3-5-numerical-grading-1",
        "expected_read_count": len(expected), "operand_read_count": len(operands), "capture_read_count": len(captures), "total_read_count": len(all_rows),
        "route_authority": {"selected_ids_hex": "fa000a00ed003e004900b100da001c00", "selected_ids_sha256": "a0f2e2b59ebc606c43e17eab8f76a5b14c26b678bef2a9b0207c3f7dd15f164f",
                            "routing_weights_f64_hex": "f29dfce3c2f5e73ffe85c101646ed53f78f9fd32848bce3f202f8b7f5152ce3f2142671d6c18d03f0c8a3f6c4984cd3f24a20c24e654cd3f30a3e6ee4e64cd3f",
                            "routing_weights_sha256": "ff1a7127b418b80dce4e4361e314c16ad50e86484cb1861ad27f6f9ee70b8587",
                            "ranking_sha256": "b2de9d7a4fe2701f0cda51f6b95a5396195e0bf0c44924aa6d46b4a899af549d", "tie_semantics": "DESCENDING_SCORE_LOWER_EXPERT_ID"},
        "expected_reads": expected, "operand_reads": operands, "capture_reads": captures,
    }
    for row in grant["expected_reads"] + grant["operand_reads"] + grant["capture_reads"]:
        row["path"] = portable(row["path"])
    write(args.grant_out, grant)


if __name__ == "__main__":
    main()
