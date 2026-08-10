#!/usr/bin/env python3
"""Bounded persistent Rust direct-IQ2_XXS Metal worker adapter."""

from __future__ import annotations

import json
import struct
import subprocess
from pathlib import Path
from typing import Any

import numpy as np

from glm52_tensor_store import Glm52TensorStore, nbytes_for_tensor


class DirectIq2MetalWorker:
    """Two-slot research worker; never silently falls back to CPU or MLX."""

    def __init__(self, executable: Path, source_commit: str) -> None:
        if not executable.is_file():
            raise FileNotFoundError(executable)
        self._process = subprocess.Popen(
            [str(executable)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._request_id = 0
        ready = self._read_response()
        if ready.get("status") != "ready":
            raise RuntimeError("direct Metal worker did not become ready")
        if ready.get("source_commit") != source_commit:
            raise RuntimeError("direct Metal worker source identity mismatch")
        if ready.get("max_resident_matrices") != 2:
            raise RuntimeError("direct Metal worker residency bound changed")
        self.identity = ready

    def _read_response(self) -> dict[str, Any]:
        assert self._process.stdout is not None
        line = self._process.stdout.readline()
        if not line:
            assert self._process.stderr is not None
            error = self._process.stderr.read().strip()
            raise RuntimeError(f"direct Metal worker exited unexpectedly: {error}")
        response = json.loads(line)
        if not isinstance(response, dict):
            raise RuntimeError("direct Metal worker response must be an object")
        return response

    def _request(self, request: dict[str, Any]) -> dict[str, Any]:
        if self._process.poll() is not None:
            raise RuntimeError("direct Metal worker is not running")
        self._request_id += 1
        request = {**request, "request_id": self._request_id}
        assert self._process.stdin is not None
        self._process.stdin.write(json.dumps(request, separators=(",", ":")) + "\n")
        self._process.stdin.flush()
        response = self._read_response()
        if response.get("request_id") != self._request_id:
            raise RuntimeError("direct Metal worker response ID mismatch")
        if response.get("status") != "ok":
            raise RuntimeError(
                f"direct Metal worker rejected request: {response.get('error', 'unknown error')}"
            )
        if response.get("cpu_fallback_count") != 0:
            raise RuntimeError("direct Metal worker used a CPU fallback")
        if response.get("complete_f32_weight_materialized_bytes") != 0:
            raise RuntimeError("direct Metal worker materialized a complete f32 matrix")
        return response

    def gemv(
        self,
        store: Glm52TensorStore,
        tensor_name: str,
        expert_id: int,
        activation: list[float],
    ) -> tuple[list[float], dict[str, Any]]:
        location = store.tensors[tensor_name]
        if location.type_id != 16 or location.type_name != "IQ2_XXS":
            raise ValueError(f"{tensor_name}: direct worker supports IQ2_XXS only")
        if len(location.dims) != 3:
            raise ValueError(f"{tensor_name}: direct worker requires a routed-expert tensor")
        columns, rows, experts = map(int, location.dims)
        if not 0 <= expert_id < experts:
            raise IndexError(expert_id)
        if len(activation) != columns:
            raise ValueError(f"{tensor_name}: activation length mismatch")
        packed_bytes = nbytes_for_tensor(location.type_id, rows * columns)
        activation_bits = (
            np.asarray(activation, dtype="<f4").view(np.uint32).astype(np.uint64).tolist()
        )
        response = self._request(
            {
                "command": "gemv",
                "shard_path": str(location.file),
                "offset": location.offset + expert_id * packed_bytes,
                "rows": rows,
                "columns": columns,
                "activation_f32_bits": activation_bits,
            }
        )
        bits = response.pop("output_f32_bits", None)
        if not isinstance(bits, list) or len(bits) != rows:
            raise RuntimeError("direct Metal worker output shape mismatch")
        output = [struct.unpack("<f", struct.pack("<I", int(value)))[0] for value in bits]
        output_sha256 = __import__("hashlib").sha256(
            np.asarray(output, dtype="<f4").tobytes()
        ).hexdigest()
        if output_sha256 != response["output_sha256"]:
            raise RuntimeError("direct Metal worker output hash mismatch")
        event = {
            **response,
            "tensor_name": tensor_name,
            "expert_id": expert_id,
            "quantization": location.type_name,
            "rows": rows,
            "columns": columns,
            "packed_bytes": packed_bytes,
        }
        return output, event

    def close(self) -> None:
        if self._process.poll() is not None:
            return
        self._request_id += 1
        assert self._process.stdin is not None
        self._process.stdin.write(
            json.dumps({"command": "shutdown", "request_id": self._request_id}) + "\n"
        )
        self._process.stdin.flush()
        response = self._read_response()
        if response.get("status") != "shutdown":
            raise RuntimeError("direct Metal worker shutdown was not acknowledged")
        self._process.wait(timeout=5)

    def __enter__(self) -> "DirectIq2MetalWorker":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        try:
            self.close()
        except Exception:
            if exc is None:
                raise
            self._process.kill()
