#!/usr/bin/env python3
"""C09: single-token depth ladder through all 79 GLM-5.2 layers."""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from glm52_dense_primitives import embed_token
from glm52_layer import layer_forward_token
from glm52_mla import CompactKVCache
from glm52_tensor_store import Glm52TensorStore


def main() -> int:
    root = Path.home() / "Models/PulsarMLX/GLM-5.2-UD-IQ2_XXS"
    out_dir = Path("docs/research/glm52/raw")
    out_dir.mkdir(parents=True, exist_ok=True)

    store = Glm52TensorStore(root)
    n_layer = 79
    t0 = time.time()
    x = embed_token(store, 0)
    caches = [CompactKVCache() for _ in range(n_layer)]
    layer_l2: list[float] = []
    layer_meta: list[dict] = []

    for layer in range(n_layer):
        t1 = time.time()
        try:
            x, diag = layer_forward_token(store, layer, x, caches[layer], pos=0)
        except Exception as exc:  # noqa: BLE001
            (out_dir / "f016-c09-depth-progress.json").write_text(
                json.dumps(
                    {
                        "last_layer": layer - 1,
                        "failed_layer": layer,
                        "error": repr(exc),
                        "layer_l2": layer_l2,
                        "meta": layer_meta,
                        "elapsed": time.time() - t0,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            )
            # keep residual for resume debugging
            (out_dir / "f016-c09-resume-hidden.json").write_text(
                json.dumps({"layer_completed": layer - 1, "hidden": x}, sort_keys=True) + "\n"
            )
            raise
        if not diag["finite"]:
            raise RuntimeError(f"non-finite residual at layer {layer}")
        sec = time.time() - t1
        layer_l2.append(float(diag["out_l2"]))
        route = diag.get("route") or {}
        layer_meta.append(
            {
                "layer": layer,
                "ffn": diag.get("ffn"),
                "out_l2": diag["out_l2"],
                "seconds": sec,
                "expert_ids": route.get("expert_ids"),
            }
        )
        print(
            f"L{layer:02d} {diag.get('ffn')} l2={diag['out_l2']:.6f} sec={sec:.1f}",
            flush=True,
        )
        # persist residual every layer for resume
        (out_dir / "f016-c09-resume-hidden.json").write_text(
            json.dumps({"layer_completed": layer, "hidden": x}, sort_keys=True) + "\n"
        )
        if layer % 5 == 0 or layer == n_layer - 1:
            (out_dir / "f016-c09-depth-progress.json").write_text(
                json.dumps(
                    {
                        "last_layer": layer,
                        "layer_l2": layer_l2,
                        "meta": layer_meta,
                        "elapsed": time.time() - t0,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            )

    evidence = {
        "schema": "pulsarmlx.research.glm52-c09-depth-ladder",
        "boundary": "GLM-C09",
        "actual_status": "passed",
        "n_layers": n_layer,
        "token_id": 0,
        "final_hidden_l2": math.sqrt(sum(v * v for v in x)),
        "layer_l2": layer_l2,
        "layer_meta": layer_meta,
        "seconds": time.time() - t0,
        "note": (
            "Single-token depth ladder through all 79 layers (MLA + dense/MoE). "
            "Finite residual stream on architecture CPU/MLX path."
        ),
    }
    # keep hidden state for C10
    (out_dir / "f016-c09-final-hidden.json").write_text(
        json.dumps({"hidden": x, "l2": evidence["final_hidden_l2"]}, sort_keys=True) + "\n"
    )
    (out_dir / "f016-c09-depth-0001.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    )
    print(
        "C09 PASSED",
        evidence["seconds"],
        "final_l2",
        evidence["final_hidden_l2"],
        flush=True,
    )
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
