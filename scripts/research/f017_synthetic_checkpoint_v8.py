#!/usr/bin/env python3
"""Structurally isolated six-shard fixtures for V8 lifecycle qualification."""
from __future__ import annotations

import hashlib
from pathlib import Path

from f017_canonical_serialization_v8 import canonical_bytes
from generate_f017_corrected_oracle_fixtures import fixture
from validate_f017_corrected_oracle_access_v8 import install_rehearsal_candidate, render_rehearsal_candidate


FORMATS = ["F32", "F16", "Q4_0", "Q5_0", "Q8_0", "Q2_K", "Q3_K", "Q4_K", "Q5_K", "Q6_K", "IQ3_XXS"]


def prepare(root: Path, seed: int, suffix: str, mixed: bool = False) -> tuple[Path, Path, list[dict]]:
    checkpoint = root / "checkpoint"
    checkpoint.mkdir()
    document = fixture(seed)
    document["v8_format_coverage"] = FORMATS if mixed else ["F32"]
    payloads = [b"IDENTITY-ONLY", canonical_bytes(document)]
    labels = canonical_bytes({"formats": FORMATS if mixed else ["F32"]})
    payloads.extend([labels + bytes([index]) for index in range(4)])
    shards = []
    for ordinal, payload in enumerate(payloads, start=1):
        name = f"synthetic-{ordinal:05d}-of-00006.gguf"
        path = checkpoint / name
        path.write_bytes(payload)
        shards.append({
            "filename": name,
            "size_bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "role": "IDENTITY_ONLY" if ordinal == 1 else "GRAPH_PAYLOAD",
        })
    candidate = root / "candidate.json"
    render_rehearsal_candidate(checkpoint, shards, candidate, suffix)
    installed = root / "private-install" / "authorization.json"
    receipt = root / "installation-receipt.json"
    install_rehearsal_candidate(candidate, installed, receipt)
    return installed, receipt, shards
