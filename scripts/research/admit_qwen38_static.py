"""Read only pinned Qwen metadata, Safetensors headers, and small norm tensors.

No checkpoint-provided Python is imported, and no model computation occurs.
"""

from __future__ import annotations

import argparse
import ast
import collections
import json
import math
import os
import struct
from pathlib import Path


MANIFEST = Path(__file__).resolve().parents[2] / "specs/021-qwen38-io-prefetch-spike/checkpoint-manifest.json"
DTYPE_BYTES = {"BF16": 2, "F16": 2, "F32": 4, "F64": 8, "I64": 8, "U64": 8,
               "I32": 4, "U32": 4, "I16": 2, "U16": 2, "I8": 1, "U8": 1, "BOOL": 1}
CENTERED = ("hc_norm.weight", "q_norm.weight", "k_norm.weight",
            "indexer.q_layernorm.weight", "indexer.k_layernorm.weight",
            "ple.norm_key.weight", "ple.norm_query.weight", "ple.norm_conv.weight")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read_header(path: Path) -> tuple[int, dict]:
    with path.open("rb") as stream:
        raw = stream.read(8)
        require(len(raw) == 8, f"short Safetensors prefix: {path}")
        length = struct.unpack("<Q", raw)[0]
        require(0 < length <= 32 * 2**20, f"unreasonable Safetensors header: {path}")
        body = stream.read(length)
        require(len(body) == length, f"short Safetensors header: {path}")
    header = json.loads(body)
    require(isinstance(header, dict), f"invalid Safetensors header: {path}")
    return 8 + length, header


def inspect_shard(path: Path, expected_names: set[str]) -> tuple[dict, int]:
    data_start, header = read_header(path)
    metadata = header.pop("__metadata__", None)
    require(metadata is None or isinstance(metadata, dict), f"invalid header metadata: {path}")
    require(set(header) == expected_names, f"index/header tensor mismatch: {path.name}")
    spans = []
    for name, item in header.items():
        require(isinstance(item, dict) and item.get("dtype") in DTYPE_BYTES,
                f"unknown tensor dtype: {name}")
        shape, offsets = item.get("shape"), item.get("data_offsets")
        require(isinstance(shape, list) and all(type(d) is int and d >= 0 for d in shape),
                f"invalid tensor shape: {name}")
        require(isinstance(offsets, list) and len(offsets) == 2 and
                all(type(o) is int and o >= 0 for o in offsets), f"invalid tensor offsets: {name}")
        start, end = offsets
        require(start <= end and end - start == math.prod(shape) * DTYPE_BYTES[item["dtype"]],
                f"tensor byte count mismatch: {name}")
        spans.append((start, end, name))
    cursor = 0
    for start, end, name in sorted(spans):
        require(start == cursor, f"gap or overlap before tensor: {name}")
        cursor = end
    require(data_start + cursor == path.stat().st_size,
            f"unaccounted shard bytes: {path.name}")
    return header, data_start


def bf16_summary(path: Path, data_start: int, info: dict) -> dict:
    require(info["dtype"] == "BF16", f"expected BF16 norm in {path.name}")
    start, end = info["data_offsets"]
    require(end - start <= 2 * 2**20, "norm sample exceeds read limit")
    with path.open("rb") as stream:
        stream.seek(data_start + start)
        data = stream.read(end - start)
    values = [struct.unpack("<f", struct.pack("<I", word << 16))[0]
              for (word,) in struct.iter_unpack("<H", data)]
    require(values and all(math.isfinite(v) for v in values), "nonfinite or empty norm")
    return {"count": len(values), "mean": sum(values) / len(values), "min": min(values),
            "max": max(values), "negative_count": sum(v < 0 for v in values)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=Path, required=True)
    args = parser.parse_args()
    root = args.dest
    manifest = json.loads(MANIFEST.read_text())
    receipt = json.loads((root / "acquisition-receipt.json").read_text())
    require(receipt.get("complete") is True and receipt.get("revision") == manifest["revision"],
            "acquisition receipt is incomplete or mismatched")
    require(set(receipt["verified_files"]) == {f["path"] for f in manifest["files"]},
            "acquisition receipt omits files")
    for entry in manifest["files"]:
        require((root / entry["path"]).stat().st_size == entry["size_bytes"],
                f"file size changed after acquisition: {entry['path']}")

    config = json.loads((root / "config.json").read_text())
    text_config = config["text_config"]
    require(config["model_type"] == "qwen4_exp" and config["model_file"] == "qwen4_exp.py",
            "unexpected architecture or bundled runtime")
    require((text_config["num_hidden_layers"], text_config["num_experts"],
             text_config["num_experts_per_tok"], text_config["split_ngram_parts"]) == (48, 512, 10, 128),
            "unexpected Qwen topology")
    quant = config["quantization"]
    require((quant["bits"], quant["group_size"]) == (4, 64), "unexpected quantization default")
    overrides = collections.Counter((v["bits"], v["group_size"]) for v in quant.values()
                                    if isinstance(v, dict))
    require(overrides == {(8, 64): 498, (4, 32): 128}, "unexpected quantization overrides")
    generation = json.loads((root / "generation_config.json").read_text())
    require(generation["eos_token_id"] == [248046, 248044], "unexpected stop IDs")
    tokenizer = json.loads((root / "tokenizer_config.json").read_text())
    require(tokenizer["tokenizer_class"] == "Qwen2Tokenizer" and
            tokenizer["added_tokens_decoder"]["248046"]["content"] == "<|im_end|>",
            "unexpected tokenizer metadata")

    runtime_tree = ast.parse((root / "qwen4_exp.py").read_text())
    allowed_top_level = (ast.Import, ast.ImportFrom, ast.ClassDef, ast.FunctionDef, ast.Assign)
    require(all(isinstance(node, allowed_top_level) for node in runtime_tree.body),
            "bundled runtime has unexpected top-level statements")
    require(not any(isinstance(child, ast.Call) for node in runtime_tree.body
                    if isinstance(node, ast.Assign) for child in ast.walk(node)),
            "bundled runtime has top-level call in assignment")
    runtime_imports = []
    for node in runtime_tree.body:
        if isinstance(node, ast.Import):
            runtime_imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            runtime_imports.append(node.module or "")
    require(not any(name.split(".")[0] in {"os", "subprocess", "socket", "requests", "urllib", "importlib"}
                    for name in runtime_imports), "bundled runtime imports an unexpected I/O module")
    require(not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and
                    node.func.id in {"exec", "eval", "compile", "__import__"}
                    for node in ast.walk(runtime_tree)), "bundled runtime contains a direct dynamic-code call")

    index = json.loads((root / "model.safetensors.index.json").read_text())
    weight_map = index["weight_map"]
    shards = [f for f in manifest["files"] if f["path"].endswith(".safetensors")]
    require(index["metadata"]["total_size"] == sum(f["size_bytes"] for f in shards),
            "index total_size disagrees with shards")
    require(set(weight_map.values()) == {f["path"] for f in shards}, "unexpected index shard set")
    all_headers: dict[str, tuple[Path, int, dict]] = {}
    dtype_counts: collections.Counter[str] = collections.Counter()
    for shard in shards:
        path = root / shard["path"]
        expected = {name for name, filename in weight_map.items() if filename == shard["path"]}
        header, data_start = inspect_shard(path, expected)
        for name, info in header.items():
            require(name not in all_headers, f"duplicate tensor: {name}")
            all_headers[name] = (path, data_start, info)
            dtype_counts[info["dtype"]] += 1
    require(len(all_headers) == len(weight_map), "index tensor count mismatch")
    names = set(all_headers)
    require(not any(n.startswith("model.language_model.") or
                    n.endswith("mlp.experts.gate_up_proj") or n.startswith("mtp.") for n in names),
            "unexpected raw-HF or MTP tensor layout")
    require(any("switch_mlp.gate_proj.weight" in n for n in names), "split experts missing")
    require(all((name[:-len(".scales")] + ".weight") in names and
                (name[:-len(".scales")] + ".biases") in names
                for name in names if name.endswith(".scales")),
            "quantized tensor triple incomplete")
    require(all((name[:-len(".weight")] + ".scales") in names and
                (name[:-len(".weight")] + ".biases") in names
                for name, (_, _, info) in all_headers.items()
                if name.endswith(".weight") and info["dtype"] == "U32"),
            "packed weight missing affine metadata")

    norm_samples = {}
    norm_families = {}
    for suffix in CENTERED:
        choices = sorted(n for n in names if n.endswith(suffix))
        require(choices, f"centered norm family missing: {suffix}")
        summaries = []
        for name in choices:
            path, data_start, info = all_headers[name]
            summaries.append((name, bf16_summary(path, data_start, info)))
        sample_name, sample = next(((name, summary) for name, summary in summaries
                                    if ".layers." in name), summaries[0])
        norm_samples[suffix] = {"tensor": sample_name, **sample}
        means = [summary["mean"] for _, summary in summaries]
        norm_families[suffix] = {"tensor_count": len(summaries),
                                 "minimum_tensor_mean": min(means),
                                 "maximum_tensor_mean": max(means)}
        require(min(means) > 0.4, f"norm family does not support pre-folded layout: {suffix}")
    # The raw-HF centered weights are near zero, while the converted tensors
    # have +1 folded in. This is a sample-level admission gate, not a full
    # numerical parity test.
    result = {
        "schema": "pulsarmlx.qwen38.static-admission/1",
        "repo": manifest["repo"], "revision": manifest["revision"],
        "tensor_count": len(all_headers), "shard_count": len(shards),
        "dtype_counts": dict(dtype_counts), "quantization_override_counts":
            {f"{bits}-bit/group-{group}": count for (bits, group), count in overrides.items()},
        "raw_hf_layout_markers": 0, "mtp_tensor_count": 0,
        "norm_samples": norm_samples, "norm_families": norm_families,
        "centered_norm_tensor_count": sum(item["tensor_count"] for item in norm_families.values()),
        "runtime_static_review": {"imports": runtime_imports,
                                  "top_level_statements": len(runtime_tree.body),
                                  "checkpoint_code_executed": False},
        "verdict": "metadata/header admission; centered norm values support pre-folded layout; no model execution",
    }
    output = root / "static-admission.json"
    temporary = output.with_name(output.name + ".tmp")
    temporary.write_text(json.dumps(result, indent=2) + "\n")
    os.replace(temporary, output)
    print(json.dumps({k: v for k, v in result.items() if k != "norm_samples"}, indent=2))
    for suffix, sample in norm_samples.items():
        print(f"{suffix}: mean={sample['mean']:.4f} min={sample['min']:.4f} max={sample['max']:.4f}")


if __name__ == "__main__":
    main()
