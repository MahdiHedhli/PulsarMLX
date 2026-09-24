#!/usr/bin/env python3
"""Assemble one sanitized F020 Slice 2A metadata-census evidence record.

Inputs are the extractor's output directory for one checkpoint (header
sidecars, ``extract-log.json``, ``listing.json`` and the small JSON files), the
census report written by ``crates/mlx-affine/examples/header_census.rs``, and a
hand-written inferences file. The record keeps **observations** (machine
output, copied or summarized mechanically) apart from **inferences** (the
hand-written file, labelled as such), binds every tool file by path, sha256
and commit so ``scripts/ci/validate_evidence_change.py`` re-resolves them, and
refuses to write anything that names a local path, user or host.

It reads no shard and needs none: everything it touches is metadata the
extractor already copied. Standard library only.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

SCHEMA = "pulsarmlx.f020.slice2a-metadata-census/1.0.0"
LABEL = (
    "header-only metadata compatibility observation; NOT Q0 payload identity; "
    "NOT numerical qualification"
)
TOOL_FILES = (
    "scripts/research/extract_safetensors_headers_v1.py",
    "crates/mlx-affine/examples/header_census.rs",
    "crates/mlx-affine/examples/support/header_census_core.rs",
    "crates/mlx-affine/examples/support/header_census_source.rs",
    "crates/mlx-affine/tests/census_metadata_only.rs",
    "scripts/research/build_f020_slice2a_census_evidence_v1.py",
)
CONFIG_KEYS = (
    "architectures", "model_type", "dtype", "num_hidden_layers", "hidden_size",
    "intermediate_size", "moe_intermediate_size", "n_routed_experts",
    "n_shared_experts", "num_experts_per_tok", "first_k_dense_replace",
    "moe_layer_freq", "num_nextn_predict_layers", "num_attention_heads",
    "num_key_value_heads", "head_dim", "q_lora_rank", "kv_lora_rank",
    "qk_nope_head_dim", "qk_rope_head_dim", "qk_head_dim", "v_head_dim",
    "vocab_size", "max_position_embeddings", "tie_word_embeddings",
    "moe_router_dtype", "scoring_func", "topk_method", "routed_scaling_factor",
    "norm_topk_prob", "n_group", "topk_group", "index_n_heads",
    "index_head_dim", "index_topk", "index_topk_freq", "index_skip_topk_offset",
    "index_share_for_mtp_iteration", "index_kpool", "index_kpool_compress",
    "indexer_types", "mlp_layer_types", "layer_types", "linear_attn_config",
    "mhc", "hc_mult", "hc_sinkhorn_iters", "swiglu_limit", "mla_use_nope",
    "model_file",
)
# Nothing that names a machine, its disks, its user or its network may be
# published. The check runs on the serialized record, so no field escapes it.
# Generic local-path prefixes and private addresses are refused here; the
# names specific to the machine the census ran on (user, host, volume) are
# supplied at run time with --forbid, so they are never committed either.
FORBIDDEN = re.compile(
    r"/Users/|/Volumes/|/private/|/home/|/tmp/|"
    r"\b(?:10|127|172|192)\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
    re.IGNORECASE,
)


class EvidenceError(RuntimeError):
    pass


def _git_bytes(repository: Path, commit: str, path: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{commit}:{path}"], cwd=repository, check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _config_facts(config: dict) -> dict:
    def pick(block: dict) -> dict:
        picked = {}
        for key in CONFIG_KEYS:
            if key not in block:
                continue
            value = block[key]
            if isinstance(value, list) and value and all(isinstance(v, str) for v in value) \
                    and key.endswith("_types"):
                picked[key] = {
                    "length": len(value),
                    "counts": dict(sorted(Counter(value).items())),
                    "positions": {
                        kind: [i for i, v in enumerate(value) if v == kind]
                        for kind in sorted(set(value))
                    },
                }
            else:
                picked[key] = value
        return picked

    facts = {"label": "config-reported, not verified", "top_level": pick(config)}
    for nested in ("text_config", "vision_config"):
        if isinstance(config.get(nested), dict):
            facts[nested] = pick(config[nested])
    return facts


def _download_record(record: dict, extract_log: dict) -> dict:
    stat_len = {shard["file"]: shard["file_len"] for shard in extract_log["shards"]}
    summary = {
        "label": "as recorded at download time; NOT re-verified by this census",
        "members_present": sorted(record),
        "repo": record.get("repo"),
        "revision": record.get("revision"),
    }
    for key in ("verified_at", "authorization", "total_bytes", "seconds"):
        if key in record:
            summary[key] = record[key]
    if isinstance(record.get("tool"), dict):
        summary["tool"] = {k: v for k, v in record["tool"].items() if k != "interpreter"}
    files = record.get("files")
    if not isinstance(files, list):
        summary["per_file_records"] = None
        summary["statement"] = (
            "The record lists no files, sizes, hashes or verification flags; it "
            "names the repository, the revision, a local location (omitted here) "
            "and a duration only."
        )
        return summary
    shards = [f for f in files if f["name"].endswith(".safetensors")]
    summary["per_file_records"] = {
        "files": len(files),
        "verified_true": sum(1 for f in files if f.get("verified") is True),
        "with_sha256": sum(1 for f in files if f.get("sha256")),
        "shards": len(shards),
        "shards_with_sha256": sum(1 for f in shards if f.get("sha256")),
        "non_shard_files": sorted(f["name"] for f in files if not f["name"].endswith(".safetensors")),
    }
    rows = []
    for shard in sorted(shards, key=lambda f: f["name"]):
        rows.append({
            "file": shard["name"],
            "recorded_bytes": shard.get("bytes"),
            "recorded_sha256": shard.get("sha256"),
            "recorded_verified": shard.get("verified"),
            "stat_file_len_now": stat_len.get(shard["name"]),
            "recorded_bytes_equal_stat": shard.get("bytes") == stat_len.get(shard["name"]),
        })
    summary["shards"] = rows
    summary["shard_sizes_all_equal_stat"] = all(r["recorded_bytes_equal_stat"] for r in rows)
    summary["shards_recorded_equal_shards_extracted"] = (
        sorted(r["file"] for r in rows) == sorted(stat_len)
    )
    summary["statement"] = (
        "Each shard's sha256 here is the value the download record says was "
        "verified at download time. This census did not hash any shard and did "
        "not re-verify payload identity; the header sha256 values elsewhere in "
        "this record identify header bytes only."
    )
    return summary


def build(args) -> dict:
    repository = Path(args.repository).resolve()
    metadata = Path(args.metadata)
    extract_log = _load(metadata / "extract-log.json")
    listing = _load(metadata / "listing.json")
    census = _load(Path(args.census))
    inferences = _load(Path(args.inferences))
    config = _load(metadata / "config.json")
    record_path = metadata / "download-record.json"
    record = _load(record_path) if record_path.exists() else None

    if census.get("schema") != "pulsarmlx.f020.metadata-census/1.0.0":
        raise EvidenceError("unexpected census schema")
    tools = []
    for path in TOOL_FILES + (args.rules,):
        tools.append({"path": path, "sha256": _sha256(_git_bytes(repository, args.tool_commit, path)),
                      "commit": args.tool_commit})
    extractor_sha = tools[0]["sha256"]
    if args.extractor_run_sha256 != extractor_sha:
        raise EvidenceError("the extractor that ran is not the committed extractor")

    shards = extract_log["shards"]
    census_shas = {s["file"]: s["header_sha256"] for s in census["shards"]}
    for shard in shards:
        if census_shas.get(shard["file"]) != shard["header_sha256"]:
            raise EvidenceError(f"{shard['file']}: census and extractor header sha256 differ")
        if shard["max_read_offset_exclusive"] != 8 + shard["header_len"] or shard["payload_bytes_read"]:
            raise EvidenceError(f"{shard['file']}: read log exceeds the header")

    stray = [
        {"directory": entry["name"], "child": child["name"], "size": child["size"]}
        for entry in listing["entries"] if entry["type"] == "directory"
        for child in entry.get("children", [])
        if child["name"].endswith((".pyc", ".py"))
    ]
    evidence = {
        "schema": SCHEMA,
        "feature": "020-mlx-safetensors-affine",
        "slice": "2A",
        "recorded_on": args.recorded_on,
        "label": LABEL,
        "identity": {"repo": args.repo, "revision": args.revision},
        "not_claimed": [
            "not Q0: payload identity was not re-verified",
            "not numerical qualification",
            "header sha256 values identify header bytes only",
            "no model executed",
            "no quantized matmul, no residency, no performance",
        ],
        "tools": {
            "tool_commit": args.tool_commit,
            "bound_files": tools,
            "extractor_run_sha256": args.extractor_run_sha256,
            "extractor_run_equals_committed": True,
            "extractor_python": args.extractor_python,
            "rules_file": args.rules,
        },
        "access": {
            "payload_reads": 0,
            "payload_bytes_read": sum(s["payload_bytes_read"] for s in shards),
            "downloads": 0,
            "full_shard_hashes": 0,
            "network_calls": 0,
            "model_code_imported_or_executed": 0,
            "basis": (
                "the extractor's own read log, per shard: an 8-byte prefix read at "
                "offset 0 and an N-byte header read at offset 8, every read bounded "
                "before the system call, maximum read end exactly 8 + N, file "
                "position unchanged; the census then built its catalog with "
                "Checkpoint::from_headers from those bytes alone"
            ),
            "per_shard": [
                {k: s[k] for k in ("file", "file_len", "header_len", "reads",
                                   "max_read_offset_exclusive", "bytes_read",
                                   "file_position_after", "header_sha256")}
                for s in shards
            ],
            "header_bytes_read_total": extract_log["totals"]["header_bytes_read"],
            "shards_within_bound": extract_log["totals"]["shards_within_bound"],
            "small_json_read": {
                name: value for name, value in extract_log["small_json"].items()
            },
        },
        "provenance": (
            _download_record(record, extract_log) if record is not None
            else {"label": "no download record present"}
        ),
        "observations": {
            "label": "mechanical output of the census and the extractor",
            "directory_listing": listing["entries"],
            "stray_code_files_listed_not_read": stray,
            "config_reported": _config_facts(config),
            "census": census,
        },
        "inferences": {
            "label": "hand-written interpretation of the observations; not machine output",
            **inferences,
        },
    }
    text = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    match = FORBIDDEN.search(text)
    if match:
        raise EvidenceError(f"refusing to write private material: {match.group(0)!r}")
    for token in args.forbid or ():
        if token and token.lower() in text.lower():
            raise EvidenceError("refusing to write a caller-forbidden token")
    Path(args.output).write_text(text, encoding="utf-8")
    return evidence


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    for name in ("repository", "metadata", "census", "inferences", "rules", "repo",
                 "revision", "tool-commit", "extractor-run-sha256", "extractor-python",
                 "recorded-on", "output"):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--forbid", action="append", default=[],
                        help="a further token (user, host, volume) that must not appear")
    args = parser.parse_args(argv)
    try:
        build(args)
    except (EvidenceError, subprocess.CalledProcessError) as error:
        print(f"build_f020_slice2a_census_evidence_v1: refused: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
