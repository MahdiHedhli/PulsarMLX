#!/usr/bin/env python3
"""Structurally isolated, descriptor-distributed V9 synthetic checkpoints."""
from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

from f017_canonical_serialization_v8 import canonical_bytes
from f017_oracle_primary_decoders import LAYOUT
from generate_f017_corrected_oracle_fixtures import fixture
from qualify_f017_quantization_matrix_v1 import synthetic_block


FORMATS = list(LAYOUT)


def _shape(name: str, values: list[float], geometry: dict) -> tuple[int, int, bool]:
    hidden = geometry["hidden"]
    if name.endswith(".bias") or name.endswith("_norm.weight") or name == "output_norm.weight": return 1, len(values), True
    if name in {"token_embd.weight", "output.weight"}: return geometry["vocab"], hidden, False
    if "attn_q_a.weight" in name: return geometry["q_rank"], hidden, False
    if "attn_q_b.weight" in name: return geometry["heads"] * (geometry["qk_nope"] + geometry["qk_rope"]), geometry["q_rank"], False
    if "attn_kv_a_mqa.weight" in name: return geometry["kv_rank"] + geometry["qk_rope"], hidden, False
    if "attn_k_b.weight" in name: return geometry["kv_rank"], geometry["qk_nope"], False
    if "attn_v_b.weight" in name: return geometry["value_dim"], geometry["kv_rank"], False
    if "attn_output.weight" in name: return hidden, geometry["heads"] * geometry["value_dim"], False
    if "ffn_gate_inp.weight" in name: return geometry["experts"], hidden, False
    if "_gate" in name or "_up" in name:
        return geometry["dense_ffn"] if "_exps." not in name and "_shexp." not in name else geometry["expert_ffn"], hidden, False
    if "_down" in name:
        return hidden, geometry["dense_ffn"] if "_exps." not in name and "_shexp." not in name else geometry["expert_ffn"], False
    raise ValueError(f"unclassified tensor: {name}")


def prepare(root: Path, seed: int, suffix: str, mixed: bool = False) -> tuple[Path, list[dict], Path, Path]:
    checkpoint = root / "checkpoint"; checkpoint.mkdir()
    document = fixture(seed); geometry = document["geometry"]
    shard_names = [f"synthetic-v9-{ordinal:05d}-of-00006.gguf" for ordinal in range(1, 7)]
    payloads = {name: bytearray() for name in shard_names}
    payloads[shard_names[0]].extend(b"F017-V9-IDENTITY-ONLY")
    grouped: dict[str, list[tuple[int, list[float]]]] = {}; plain: list[tuple[str, list[float]]] = []
    for name, values in document["tensors"].items():
        if "#" in name:
            base, expert = name.rsplit("#", 1); grouped.setdefault(base, []).append((int(expert), values))
        else: plain.append((name, values))
    entries: list[tuple[str, list[float], int | None]] = [(name, values, None) for name, values in plain]
    for base, experts in grouped.items():
        entries.append((base, [value for _, values in sorted(experts) for value in values], len(experts)))
    records: list[dict] = []
    for index, (name, values, experts) in enumerate(sorted(entries)):
        shard_ordinal = 2 + index % 5; shard = shard_names[shard_ordinal - 1]
        raw = b"".join(struct.pack("<f", float(value)) for value in values)
        offset = len(payloads[shard]); payloads[shard].extend(raw)
        sample = document["tensors"].get(name) or document["tensors"][f"{name}#0"]
        rows, columns, vector = _shape(name, sample, geometry)
        dims = [columns] if vector else [columns, rows] + ([experts] if experts is not None else [])
        records.append({"name": name, "purpose": "GRAPH", "format": "F32", "dims": dims,
                        "shard_ordinal": shard_ordinal, "byte_offset": offset, "byte_length": len(raw)})
    probe_formats = FORMATS if mixed else ["F32"]
    for index, fmt in enumerate(probe_formats):
        block_values, _ = LAYOUT[fmt]; raw = synthetic_block(fmt, "pattern", seed + 1000 + index)
        probe_values = len(raw) // 4 if fmt == "F32" else block_values
        shard_ordinal = 2 + index % 5; shard = shard_names[shard_ordinal - 1]
        offset = len(payloads[shard]); payloads[shard].extend(raw)
        records.append({"name": f"__format_probe__.{fmt}", "purpose": "FORMAT_PROBE", "format": fmt,
                        "dims": [probe_values], "shard_ordinal": shard_ordinal,
                        "byte_offset": offset, "byte_length": len(raw)})
    catalog = {"schema": "pulsarmlx.f017.synthetic-descriptor-catalog/9.0.0", "seed": seed,
               "geometry": geometry, "token": document["token"], "position": document["position"],
               "formats": probe_formats, "records": records}
    catalog_path = checkpoint / "synthetic-catalog.json"; catalog_path.write_bytes(canonical_bytes(catalog))
    catalog_sha = hashlib.sha256(catalog_path.read_bytes()).hexdigest()
    shards: list[dict] = []
    for ordinal, name in enumerate(shard_names, start=1):
        path = checkpoint / name; path.write_bytes(payloads[name])
        shards.append({"filename": name, "size_bytes": len(payloads[name]),
                       "sha256": hashlib.sha256(payloads[name]).hexdigest(),
                       "role": "IDENTITY_ONLY" if ordinal == 1 else "GRAPH_PAYLOAD"})
    manifest = {"schema": "pulsarmlx.f017.synthetic-root-manifest/9.0.0", "purpose": "SYNTHETIC_QUALIFICATION",
                "production_access": "PROHIBITED", "synthetic_package_id": f"F017-V9-SYNTH-{suffix}",
                "root_canonical_path": str(checkpoint.resolve()), "shards": shards, "catalog_sha256": catalog_sha}
    manifest_path = checkpoint / "synthetic-root-manifest.json"; manifest_path.write_bytes(canonical_bytes(manifest))
    return checkpoint, shards, catalog_path, manifest_path
