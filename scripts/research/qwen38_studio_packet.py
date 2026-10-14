"""Offline Studio packet checks; no model, device, network or package imports.

Analytic probes qualify small scalar conventions only. They are not a Qwen
implementation, tokenizer, n-gram hash or independent upstream model oracle.
There is deliberately no runtime/installation/checkpoint command in this CLI.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import stat

ROOT = Path(__file__).resolve().parents[2]
PACKET = ROOT / "specs/021-qwen38-io-prefetch-spike/studio-packet"
MAX_BYTES = 1024 * 1024
STOP_IDS = (248046, 248044)
CENTERED = (
    "hc_norm.weight", "q_norm.weight", "k_norm.weight",
    "indexer.q_layernorm.weight", "indexer.k_layernorm.weight",
    "ple.norm_key.weight", "ple.norm_query.weight", "ple.norm_conv.weight",
)


class PacketError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise PacketError(message)


def bounded_bytes(path):
    """Read one small regular source artifact, rejecting symlinks/changed reads."""
    path = Path(path)
    require(path.is_absolute(), "absolute artifact path required")
    require(not any(p.is_symlink() for p in (path, *path.parents)), "symlink artifact")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_size <= MAX_BYTES,
                "nonregular or oversized artifact")
        chunks = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            require(bool(chunk), "short artifact")
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(fd)
        fields = ("st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns", "st_ctime_ns")
        require(all(getattr(before, f) == getattr(after, f) for f in fields),
                "changed artifact")
        require(not os.read(fd, 1), "grown artifact")
        named = path.lstat()
        require(not any(p.is_symlink() for p in (path, *path.parents)) and
                all(getattr(after, f) == getattr(named, f) for f in fields),
                "replaced artifact")
        return b"".join(chunks)
    finally:
        os.close(fd)


def load_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result
    def invalid(value):
        raise PacketError("nonfinite JSON constant: " + value)
    return json.loads(bounded_bytes(path), object_pairs_hook=pairs, parse_constant=invalid)


def finite_vector(values):
    require(type(values) is list and 0 < len(values) <= 4096, "bounded vector required")
    require(all(type(x) in (int, float) and math.isfinite(x) for x in values),
            "finite numeric vector required")


def compare(actual, expected, *, atol, rtol):
    finite_vector(actual)
    finite_vector(expected)
    require(len(actual) == len(expected), "shape mismatch")
    require(type(atol) in (int, float) and type(rtol) in (int, float) and
            math.isfinite(atol) and math.isfinite(rtol) and atol >= 0 and rtol >= 0,
            "invalid tolerance")
    require(all(abs(a - e) <= atol + rtol * abs(e) for a, e in zip(actual, expected)),
            "numerical mismatch")


def rms(values, weights, *, epsilon, layout, family):
    finite_vector(values)
    finite_vector(weights)
    require(len(values) == len(weights), "norm shape mismatch")
    require(type(epsilon) in (int, float) and math.isfinite(epsilon) and epsilon > 0,
            "positive epsilon required")
    require(layout in ("converted", "raw-hf"), "explicit norm layout required")
    require(family in CENTERED or family == "linear_attn.norm", "unknown norm family")
    shift = 1 if layout == "raw-hf" and family in CENTERED else 0
    scale = math.sqrt(math.fsum(x * x for x in values) / len(values) + epsilon)
    return [x / scale * (w + shift) for x, w in zip(values, weights)]


def l2(values, *, epsilon):
    finite_vector(values)
    require(type(epsilon) in (int, float) and math.isfinite(epsilon) and epsilon > 0,
            "positive epsilon required")
    # Analytic clamp convention only. Actual port/reference epsilon placement
    # must be pinned independently; nonzero probes below avoid that ambiguity.
    scale = max(math.sqrt(math.fsum(x * x for x in values)), epsilon)
    return [x / scale for x in values]


def histories(tokens):
    """Policy probe: stop tokens clear the two preceding PLE context tokens.

    The actual hash/conv/cache reset placement still requires upstream goldens.
    """
    require(type(tokens) is list and len(tokens) <= 4096 and
            all(type(t) is int and 0 <= t < 248320 for t in tokens), "invalid token IDs")
    history, result = [], []
    for token in tokens:
        if token in STOP_IDS:
            history = []
        else:
            history = (history + [token])[-2:]
        result.append(history.copy())
    return result


def causal_candidates(query, candidates):
    require(type(query) is int and 0 <= query < 2080, "invalid boundary query")
    require(type(candidates) is list and len(candidates) <= 2080 and
            all(type(k) is int and 0 <= k < 2080 for k in candidates) and
            len(set(candidates)) == len(candidates), "invalid candidate keys")
    return sorted(k for k in candidates if k <= query)


def boundary_attention(query, keys):
    """Uniform-score scalar oracle with position-derived values; O(2080)."""
    visible = causal_candidates(query, keys)
    require(bool(visible), "empty visible keys")
    return math.fsum(float(k % 17 - 8) for k in visible) / len(visible)


def generated_identity():
    # Explicit synthetic token-ID sequence, not checkpoint tokenization.
    tokens = [(17 * i + 3) % 127 for i in range(2080)]
    raw = json.dumps(tokens, separators=(",", ":")).encode("ascii")
    return {"length": len(tokens), "encoding": "compact-json-ascii",
            "size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def check_requirements():
    """Cross-file policy checks, never authority/lock/runtime qualification."""
    environment = load_json(PACKET / "environment-requirements.json")
    request = load_json(PACKET / "runtime-requests.json")
    require(environment["schema"] == "pulsarmlx.qwen38.environment-requirements/1" and
            environment["status"] == "BLOCKED_NOT_A_LOCK" and
            environment["target"]["python"] == "3.13.13" and
            environment["present_artifacts"] == [], "environment prerequisite drift")
    require(request["schema"] == "pulsarmlx.qwen38.studio-requests/1" and
            request["status"] == "BLOCKED_NO_RUNTIME_DRIVER" and
            type(request["seed"]) is int and request["seed"] == 1234 and
            request["stop_ids"] == list(STOP_IDS) and request["greedy"] is True and
            type(request["concurrency"]) is int and request["concurrency"] == 1,
            "runtime policy drift")
    require(request["gates_bytes"] == {
        "process_tree": 48 * 1024**3, "all_weight_owners": 40 * 1024**3,
        "other_owners": 8 * 1024**3, "system_reserve": 16 * 1024**3}, "memory gates drift")
    require(request["bounded_execution"] == {
        "wall_deadline_seconds_per_request": 120, "wait_deadline_ns": 5_000_000_000,
        "io_slots": 2, "staging_slot_bytes": 16 * 1024**2,
        "staging_total_bytes": 32 * 1024**2, "authenticated_read_chunk_bytes": 1024**2,
        "sampler_max_age_ns": 10_000_000, "sampler_cadence_candidate_ns": 5_000_000,
        "max_receipt_bytes": 1024**2, "max_fixture_total_bytes": 16 * 1024**2},
        "bounded contract drift")
    require([r["id"] for r in request["requests"]] == [
        "tiny-device-ownership", "tiny-reference-capture", "tiny-mlx-parity",
        "paged-short", "paged-eos", "paged-boundary", "io-hint-parity"],
        "request dependency order drift")
    for row, prompt, output in ((request["requests"][3], 64, 4),
                                (request["requests"][4], 64, 4),
                                (request["requests"][5], 2080, 2)):
        require(row["max_prompt_tokens"] == prompt and row["max_output_tokens"] == output and
                row["prefetch"] is False, "paged correctness bounds drift")


def selfcheck():
    check_requirements()
    fixture = load_json(PACKET / "analytic-fixtures.json")
    require(fixture["schema"] == "pulsarmlx.qwen38.analytic-probes/1", "fixture schema")
    require(fixture["seed"] == 1234 and fixture["stop_ids"] == list(STOP_IDS),
            "seed/stop policy differs")
    tol = fixture["analytic_tolerance"]
    require(tol == {"atol": 1e-12, "rtol": 1e-12}, "analytic tolerance changed")
    count = 0
    for family in CENTERED:
        n = fixture["norm"]
        converted = rms(n["x"], n["converted"], epsilon=n["epsilon"],
                        layout="converted", family=family)
        raw = rms(n["x"], n["raw_hf"], epsilon=n["epsilon"], layout="raw-hf", family=family)
        compare(converted, n["expected"], **tol)
        compare(raw, n["expected"], **tol)
        count += 2
    n = fixture["gated_norm"]
    compare(rms(n["x"], n["weights"], epsilon=n["epsilon"], layout="raw-hf",
                family="linear_attn.norm"), n["expected"], **tol)
    count += 1
    for probe in fixture["l2"]:
        compare(l2(probe["x"], epsilon=1e-12), probe["expected"], **tol)
        count += 1
    for probe in fixture["resets"]:
        require(histories(probe["tokens"]) == probe["expected"], "EOS policy differs")
        count += 1
    for probe in fixture["boundary"]:
        require(causal_candidates(probe["query"], probe["candidates"]) == probe["expected_keys"],
                "causal boundary keys differ")
        compare([boundary_attention(probe["query"], probe["candidates"])],
                [probe["expected_uniform_attention"]], **tol)
        count += 1
    identity = generated_identity()
    require(identity == fixture["generated_boundary_tokens"], "generated fixture identity differs")
    return {"status": "PASS_ANALYTIC_ONLY", "probes": count,
            "generated_boundary_tokens": identity, "upstream_parity": "BLOCKED",
            "runtime_executed": False}


def verify():
    manifest = load_json(PACKET / "frozen-files.json")
    require(manifest["schema"] == "pulsarmlx.qwen38.studio-packet-files/1", "manifest schema")
    entries = manifest["files"]
    require(type(entries) is list and 1 <= len(entries) <= 100, "bounded file list required")
    seen = set()
    for entry in entries:
        name = entry["path"]
        require(type(name) is str and len(name) <= 240 and
                not Path(name).is_absolute() and ".." not in Path(name).parts and
                str(Path(name)) == name and
                name.startswith(("scripts/research/", "specs/021-qwen38-io-prefetch-spike/")) and
                Path(name).suffix in (".py", ".md", ".json") and name not in seen,
                "unsafe or duplicate source artifact path")
        seen.add(name)
        raw = bounded_bytes(ROOT / name)
        require(len(raw) == entry["size_bytes"] and hashlib.sha256(raw).hexdigest() == entry["sha256"],
                "frozen source differs: " + name)
    return {"status": "PASS_IDENTITIES_ONLY", "files": len(entries), "runtime_authorized": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("selfcheck", "verify"))
    args = parser.parse_args()
    try:
        print(json.dumps(selfcheck() if args.action == "selfcheck" else verify(), indent=2))
    except (PacketError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        parser.exit(2, "packet STOP: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
