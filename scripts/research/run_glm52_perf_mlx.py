#!/usr/bin/env python3
"""MLX-only GLM-5.2 performance harness (M1 Ultra internal SSD).

Run only after C11 green. Records public-safe telemetry; never invents tok/s.
Fail-closed if MLX device unavailable or silent CPU fallback detected.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from glm52_fail_closed import ExecutionGuard, FailClosedError
from glm52_telemetry import RuntimeObservation


def main() -> int:
    guard = ExecutionGuard()
    try:
        import mlx.core as mx

        mlx_ok = True
        _ = mx.array([1.0])
        mx.eval(_)
        guard.record_mlx()
    except Exception as exc:  # noqa: BLE001
        mlx_ok = False
        try:
            guard.check_mlx_available(False)
        except FailClosedError as e:
            print(f"{e}", file=sys.stderr)
            return 2
        print(f"mlx import failed: {exc}", file=sys.stderr)
        return 2
    root = os.environ.get("PULSARMLX_GLM_GGUF")
    if not root or not Path(root).exists():
        print("PULSARMLX_GLM_GGUF missing or invalid", file=sys.stderr)
        return 2
    # Placeholder: full timed prefill/decode uses the C11 forward path once
    # it is promoted to a reusable module. This entry point freezes the
    # invocation contract and telemetry envelope.
    obs = RuntimeObservation(host_class="apple_silicon_m1_ultra", storage_class="internal_ssd")
    out = {
        "schema": "pulsarmlx.research.glm52-perf-mlx",
        "status": "harness_ready_not_measured",
        "device": "mlx" if mlx_ok else "none",
        "checkpoint_env": "PULSARMLX_GLM_GGUF",
        "observation": obs.to_public_dict(),
        "note": "Do not publish tok/s until timed runs complete under EXPERIMENT_PROTOCOL.",
    }
    Path("docs/research/glm52/raw/f016-perf-shell-0001.json").write_text(
        json.dumps(out, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps({"status": out["status"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
