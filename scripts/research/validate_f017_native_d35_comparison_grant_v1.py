#!/usr/bin/env python3
"""Retained-payload-free validator for the D3.5 comparison-read grant."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-native-d3-5-comparison-read-grant-v1.json"
EXPECTED_TOP = {"schema","schema_version","grant_id","status","consumer","authority","event","allowed_output_root","expected_read_count","operand_read_count","capture_read_count","total_read_count","route_authority","expected_reads","operand_reads","capture_reads"}
READ_KEYS = {"ordinal","role","path","sha256","byte_count","dtype","shape","serialization","source_branch","source_commit","source_authority_path","source_authority_sha256","allowed_purpose"}


def no_duplicates(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate key {key}")
        value[key] = item
    return value


def load(path: Path):
    return json.loads(path.read_text(), object_pairs_hook=no_duplicates)


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def resolve_bound_path(text: str) -> Path:
    if text.startswith("${HOME}/"):
        return Path.home() / text.removeprefix("${HOME}/")
    if text.startswith("${REPOSITORY_ROOT}/"):
        return ROOT / text.removeprefix("${REPOSITORY_ROOT}/")
    raise ValueError("unbound path prefix")


def authority_path(text: str) -> Path:
    """Resolve symbolic HOME for cross-host authority comparison, not file I/O."""
    if text.startswith("${HOME}/"):
        return Path("/Users/mhedhli") / text.removeprefix("${HOME}/")
    return Path(text)


def committed_bytes(commit: str, path: str) -> bytes:
    return subprocess.check_output(["git", "show", f"{commit}:{path}"], cwd=ROOT)


def validate(
    path: Path = DEFAULT,
    *,
    resolve_executable: bool = True,
    resolve_machine_local: bool = True,
    require_pre_event_root_absent: bool = True,
) -> dict:
    doc = load(path)
    if set(doc) != EXPECTED_TOP:
        raise ValueError("top-level key census")
    if doc["schema"] != "pulsarmlx.f017.native-d3-5-comparison-read-grant/1.0.0" or doc["schema_version"] != "1.0.0":
        raise ValueError("schema")
    if doc["status"] != "INDEPENDENT_REVIEW_ACCEPT_REQUIRED_BEFORE_USE" or doc["consumer"]["id"] != "F017-NATIVE-D3_5-NUMERICAL-GRADER-1":
        raise ValueError("consumer/status")
    authority = doc["authority"]
    bindings = [(authority["d0_path"], authority["d0_sha256"]), (authority["d3_5_evidence_path"], authority["d3_5_evidence_sha256"]),
                (authority["stage_mapping_path"], authority["stage_mapping_sha256"]), (authority["diagnostic_disclosure_path"], authority["diagnostic_disclosure_sha256"])]
    for relative, expected in bindings:
        if sha(ROOT / relative) != expected:
            raise ValueError(f"bound local SHA: {relative}")
    if authority["diagnostic_metrics_reusable"] or authority["historical_master_terminal"] != 175 or authority["historical_master_ledger_sha256"] != "aa98f5cc7f1cfae1eb49a9bc64dbefec1d6ef9ccae1504a1aa8879a8edf22e3e":
        raise ValueError("authority policy")
    historical = committed_bytes("f2a7aa38c96b85cf7939c8ed653076732f066222", authority["historical_master_ledger_path"])
    if sha_bytes(historical) != authority["historical_master_ledger_sha256"]:
        raise ValueError("historical ledger binding")
    consumer = doc["consumer"]
    if sha(ROOT / consumer["source_path"]) != consumer["source_sha256"]:
        raise ValueError("consumer source binding")
    if resolve_executable and sha(resolve_bound_path(consumer["executable_path"])) != consumer["executable_sha256"]:
        raise ValueError("consumer executable binding")
    event = doc["event"]
    if event != {"event_id":"F017-NATIVE-D3_5-NUMERICAL-GRADING-1","attempt_id":"F017-NATIVE-D3_5-NUMERICAL-GRADING-1-ATTEMPT-1","attempts":1,"retries":0,"resume":False,"numerical_reexecution":False,"native_capture_regeneration":False,"historical_payload_ledger_delta":0,"original_checkpoint_reads":0,"original_checkpoint_shard_opens":0,"terminal_semantics":"ONE_OWNED_ATTEMPT_COMPLETE_OR_TERMINAL_FAILURE_NO_RETRY_NO_RESUME"}:
        raise ValueError("event policy")
    groups = [doc["expected_reads"], doc["operand_reads"], doc["capture_reads"]]
    if [len(x) for x in groups] != [15,40,34] or [doc["expected_read_count"],doc["operand_read_count"],doc["capture_read_count"],doc["total_read_count"]] != [15,40,34,89]:
        raise ValueError("read census")
    roles = set()
    for ordinal, row in enumerate(sum(groups, [])):
        if set(row) != READ_KEYS or row["ordinal"] != ordinal or row["role"] in roles:
            raise ValueError("read row census/order")
        roles.add(row["role"])
        resolved=resolve_bound_path(row["path"])
        if not resolved.is_absolute() or "checkpoint" in row["path"].lower() or len(row["sha256"]) != 64 or row["byte_count"] <= 0:
            raise ValueError("read row path/hash/size")
        if row["source_branch"] not in {"feat/017-real-checkpoint-runner","feat/017-rust-native-inference-runtime"} or len(row["source_commit"]) != 40 or len(row["source_authority_sha256"]) != 64:
            raise ValueError("read row provenance")
    old_grant_path=ROOT/"specs/017-rust-native-inference-runtime/contracts/f017-native-representative-retention-reuse-grant-v1.json"
    if sha(old_grant_path)!="b22a11c829000fd9d333a62a662dd1b274a9a710aa4ccd6afb8f7df789dc9b28":
        raise ValueError("retention reuse grant binding")
    old_grant=load(old_grant_path)
    operand_by_role={f"operand.{row['role']}":row for row in old_grant["allowed_reads"]}
    for row in doc["operand_reads"]:
        source=operand_by_role.get(row["role"])
        if source is None or (authority_path(row["path"]),row["sha256"],row["byte_count"],row["dtype"],row["shape"]) != (authority_path(source["path"]),source["sha256"],source["byte_count"],source["encoding"],source["shape"]):
            raise ValueError("operand authority mismatch")
    evidence=load(ROOT/authority["d3_5_evidence_path"]); mapping=load(ROOT/authority["stage_mapping_path"])
    pinned_manifest_sha=evidence["machine_local_authority"]["representative_manifest_sha256"]
    if mapping["source_capture_manifest_sha256"]!=pinned_manifest_sha:
        raise ValueError("capture manifest committed pin")
    dtype_map={"little-endian-u16":"U16_LE","little-endian-f32":"F32_LE"}
    for row, stage in zip(doc["capture_reads"], mapping["rows"]):
        if (
            row["role"] != f"capture.{stage['native_stage_id']}"
            or row["dtype"] != dtype_map.get(stage["dtype"])
            or row["shape"] != stage["shape"]
            or row["serialization"] != "CANONICAL_LITTLE_ENDIAN_CONTIGUOUS_NO_METADATA"
        ):
            raise ValueError("capture mapping vocabulary")
    if resolve_machine_local:
        capture_manifest_path=Path.home()/".local/share/pulsarmlx/f017/native-representative-retained-qualification-1/captures/same-00/capture-manifest.json"
        if sha(capture_manifest_path)!=pinned_manifest_sha:
            raise ValueError("capture manifest committed pin")
        capture_manifest=load(capture_manifest_path)
        capture_by_role={f"capture.{row['stage_id']}":row for row in capture_manifest["stages"]}
        for row in doc["capture_reads"]:
            source=capture_by_role.get(row["role"])
            if source is None:
                raise ValueError("capture authority role")
            if source["dtype"] not in dtype_map:
                raise ValueError("capture dtype vocabulary")
            expected_dtype=dtype_map[source["dtype"]]
            if (row["sha256"],row["byte_count"],row["shape"],row["dtype"]) != (source["sha256"],source["byte_length"],source["shape"],expected_dtype):
                raise ValueError("capture authority mismatch")
    disclosure=load(ROOT/authority["diagnostic_disclosure_path"])
    disclosed={str(authority_path(row["path"])):row["sha256"] for row in disclosure["diagnostic_retained_artifact_reads"]}
    for row in doc["expected_reads"][1:]:
        if disclosed.get(str(authority_path(row["path"]))) != row["sha256"]:
            raise ValueError("expected authority mismatch")
    s0=old_grant["allowed_reads"][0]
    if (authority_path(doc["expected_reads"][0]["path"]),doc["expected_reads"][0]["sha256"]) != (authority_path(s0["path"]),s0["sha256"]):
        raise ValueError("S0 expected authority mismatch")
    if mapping["stage_count"] != 34 or len(mapping["rows"]) != 34 or mapping["policy"] != {"producer_role_validated_before_alias":True,"implicit_mapping":False,"direct_production_copy_allowed_for_recomputed_stage":False}:
        raise ValueError("mapping policy")
    if any(row["production_method"] == "RETAINED_DIRECT_VALUE" for row in mapping["rows"][1:]):
        raise ValueError("recomputation vocabulary")
    authority_cache={}
    for row in sum(groups,[]):
        key=(row["source_commit"],row["source_authority_path"])
        if key not in authority_cache:
            try: authority_cache[key]=sha_bytes(committed_bytes(*key))
            except subprocess.CalledProcessError as error: raise ValueError(f"unresolved source authority: {key}") from error
        if authority_cache[key]!=row["source_authority_sha256"]:
            raise ValueError(f"source authority hash mismatch: {key}")
    route = doc["route_authority"]
    if sha_bytes(bytes.fromhex(route["selected_ids_hex"])) != route["selected_ids_sha256"] or sha_bytes(bytes.fromhex(route["routing_weights_f64_hex"])) != route["routing_weights_sha256"]:
        raise ValueError("route byte binding")
    if route["ranking_sha256"]!="b2de9d7a4fe2701f0cda51f6b95a5396195e0bf0c44924aa6d46b4a899af549d":
        raise ValueError("route ranking authority")
    if doc["operand_reads"][0]["serialization"]!="CANONICAL_LITTLE_ENDIAN_F32_CONTIGUOUS":
        raise ValueError("S0 serialization vocabulary")
    if doc["allowed_output_root"]!="${HOME}/.local/share/pulsarmlx/f017/native-d3-5-numerical-grading-1":
        raise ValueError("output root binding")
    if require_pre_event_root_absent and resolve_bound_path(doc["allowed_output_root"]).exists():
        raise ValueError("grading output root must be absent before event")
    full_pre_event = resolve_executable and resolve_machine_local and require_pre_event_root_absent
    return {
        "result": "PASS" if full_pre_event else "PASS_COMMITTED_STRUCTURE_ONLY",
        "validation_scope": "FULL_PRE_EVENT" if full_pre_event else "COMMITTED_STRUCTURE_ONLY_NOT_EXECUTION_AUTHORITY",
        "machine_local_bytes_rehashed": resolve_machine_local,
        "grant_sha256": sha(path),
        "read_census": 89,
        "expected_reads": 15,
        "operand_reads": 40,
        "capture_reads": 34,
        "payload_reads_during_validation": 0,
        "original_checkpoint_reads": 0,
    }


def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("path",nargs="?",type=Path,default=DEFAULT); args=parser.parse_args()
    print(json.dumps(validate(args.path),sort_keys=True))


if __name__ == "__main__":
    main()
