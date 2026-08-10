#!/usr/bin/env python3
"""Checkpoint-free tests for compact, fail-closed GLM expert residency."""

from __future__ import annotations

import json
import importlib.util
import math
import struct
import sys
import tempfile
import unittest
from contextlib import ExitStack, nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from glm52_expert_cache_runtime import (  # noqa: E402
    DecodedMatrix,
    ExpertSlabCache,
    LoadMetrics,
    MlxMatrixBackend,
    expert_matvec_cached,
    matvec_cached_rows,
    run_routed_expert_direct_iq2,
)
from glm52_dense_primitives import (  # noqa: E402
    matvec_weight,
    mlx_backend_required,
    require_mlx_backend,
)
from glm52_inference import _checkpoint_identity, _stats_delta  # noqa: E402


class FakeBackend:
    def __init__(self, *, fail_load: bool = False, decoded_bytes: int = 8) -> None:
        self.fail_load = fail_load
        self.decoded_bytes = decoded_bytes
        self.load_calls: list[tuple[str, int]] = []
        self.matvec_calls = 0
        self.release_calls = 0

    def load(self, store: object, name: str, expert: int) -> tuple[DecodedMatrix, LoadMetrics]:
        del store
        if self.fail_load:
            raise RuntimeError("synthetic MLX load failure")
        self.load_calls.append((name, expert))
        matrix = DecodedMatrix(
            value=[[1.0, 0.0], [0.0, 2.0]],
            rows=2,
            cols=2,
            decoded_bytes=self.decoded_bytes,
            compressed_bytes=2,
            quantization="TEST",
            decoder_mode="scalar_reference",
        )
        metrics = LoadMetrics(
            storage_bytes_read=2,
            storage_read_count=1,
            storage_read_seconds=0.25,
            dequant_seconds=0.5,
            contiguous_buffer_seconds=0.03125,
            matrix_build_seconds=0.125,
        )
        return matrix, metrics

    def matvec(self, matrix: DecodedMatrix, x: list[float]) -> tuple[list[float], float]:
        self.matvec_calls += 1
        return matvec_cached_rows(matrix.value, x), 0.0625

    def identity(self) -> dict[str, str]:
        return {"backend": "fake_mlx", "device": "fake_gpu"}

    def release_transient(self) -> None:
        self.release_calls += 1


def test_shared_only_policy_bypasses_routed_and_reuses_shared() -> None:
    backend = FakeBackend()
    cache = ExpertSlabCache(max_bytes=16, backend=backend, policy="decoded_shared_only")

    routed = "blk.3.ffn_gate_exps.weight"
    shared = "blk.3.ffn_gate_shexp.weight"
    assert expert_matvec_cached(object(), cache, routed, 7, [3.0, 4.0]) == [3.0, 8.0]
    assert expert_matvec_cached(object(), cache, routed, 7, [3.0, 4.0]) == [3.0, 8.0]
    assert expert_matvec_cached(object(), cache, shared, 0, [3.0, 4.0]) == [3.0, 8.0]
    assert expert_matvec_cached(object(), cache, shared, 0, [3.0, 4.0]) == [3.0, 8.0]

    stats = cache.stats.to_dict()
    assert backend.load_calls == [(routed, 7), (routed, 7), (shared, 0)]
    assert backend.release_calls == 2
    assert stats["hits"] == 1
    assert stats["misses"] == 3
    assert stats["decoded_cache_hits"] == 1
    assert stats["decoded_cache_misses"] == 3
    assert stats["storage_cache_hits"] == 1
    assert stats["storage_cache_misses"] == 3
    assert stats["storage_bytes_read"] == 6
    assert stats["storage_bytes_avoided"] == 2
    assert stats["expert_redecode_count"] == 3
    assert stats["policy_bypasses"] == 2
    assert stats["resident_entries"] == 1
    assert stats["bytes_resident"] == 8
    assert stats["peak_bytes_resident"] == 8
    assert stats["mlx_matvec_count"] == 4
    assert stats["mlx_matvec_seconds"] == 0.25
    assert stats["transient_releases"] == 2
    assert stats["backend"] == "fake_mlx"
    assert stats["device"] == "fake_gpu"


def test_opt_in_events_retain_projection_identity_and_cleanup() -> None:
    backend = FakeBackend()
    cache = ExpertSlabCache(
        max_bytes=16,
        backend=backend,
        policy="decoded_shared_only",
        capture_events=True,
    )
    matrix = cache.get_or_load_matrix(
        object(), "blk.3.ffn_gate_exps.weight", 7
    )
    cache.matvec(matrix, [3.0, 4.0])
    cache.release_transient()
    events = cache.event_snapshot()
    assert len(events) == 1
    assert events[0]["projection"] == "gate"
    assert events[0]["expert_id"] == 7
    assert events[0]["shared"] is False
    assert events[0]["cache_hit"] is False
    assert events[0]["mlx_matvec_seconds"] == 0.0625
    assert events[0]["cleanup_seconds"] >= 0.0
    assert cache.stats.to_dict()["mlx_matvec_count"] == 1


def test_shared_admission_is_protected_and_bounded_without_eviction() -> None:
    backend = FakeBackend(decoded_bytes=8)
    cache = ExpertSlabCache(max_bytes=16, backend=backend, policy="decoded_shared_only")
    for layer in range(3):
        expert_matvec_cached(
            object(), cache, f"blk.{layer}.ffn_gate_shexp.weight", 0, [1.0, 1.0]
        )
    stats = cache.stats.to_dict()
    assert stats["resident_entries"] == 2
    assert stats["bytes_resident"] == 16
    assert stats["admission_rejections"] == 1
    assert stats["evictions"] == 0


def test_clear_drops_residency_but_resets_all_counters() -> None:
    backend = FakeBackend()
    cache = ExpertSlabCache(max_bytes=16, backend=backend)
    expert_matvec_cached(
        object(), cache, "blk.3.ffn_gate_shexp.weight", 0, [1.0, 1.0]
    )
    cache.clear()
    assert cache.stats.to_dict()["resident_entries"] == 0
    assert cache.stats.to_dict()["misses"] == 0


def test_backend_failure_propagates_without_cpu_fallback() -> None:
    cache = ExpertSlabCache(max_bytes=16, backend=FakeBackend(fail_load=True))
    with unittest.TestCase().assertRaisesRegex(
        RuntimeError, "synthetic MLX load failure"
    ):
        expert_matvec_cached(
            object(), cache, "blk.3.ffn_gate_shexp.weight", 0, [1.0, 1.0]
        )
    assert cache.stats.cpu_fallbacks == 0


def test_matvec_cached_rows_reference() -> None:
    rows = [[1.0, 0.0], [0.0, 2.0]]
    assert matvec_cached_rows(rows, [3.0, 4.0]) == [3.0, 8.0]


def test_direct_iq2_routed_expert_keeps_down_on_reference_backend() -> None:
    class FakeWorker:
        def __init__(self) -> None:
            self.calls: list[tuple[str, int]] = []

        def gemv(
            self, store: object, name: str, expert: int, activation: list[float]
        ) -> tuple[list[float], dict[str, object]]:
            del store, activation
            self.calls.append((name, expert))
            output = [1.0, 2.0] if "_gate_" in name else [3.0, 4.0]
            return output, {
                "tensor_name": name,
                "expert_id": expert,
                "cache_hit": False,
                "cpu_fallback_count": 0,
                "complete_f32_weight_materialized_bytes": 0,
            }

    backend = FakeBackend()
    cache = ExpertSlabCache(
        max_bytes=0,
        backend=backend,
        policy="decoded_shared_only",
        capture_events=True,
    )
    worker = FakeWorker()
    output, detail = run_routed_expert_direct_iq2(
        object(),
        cache,
        worker,
        layer=3,
        expert=15,
        activation=[0.25, -0.5],
        weight=0.5,
    )
    hidden = [
        (1.0 / (1.0 + math.exp(-1.0))) * 3.0,
        (2.0 / (1.0 + math.exp(-2.0))) * 4.0,
    ]
    assert output == [hidden[0] * 0.5, hidden[1]]
    assert worker.calls == [
        ("blk.3.ffn_gate_exps.weight", 15),
        ("blk.3.ffn_up_exps.weight", 15),
    ]
    assert backend.load_calls == [("blk.3.ffn_down_exps.weight", 15)]
    assert len(detail["down_reference_events"]) == 1
    assert detail["down_reference_events"][0]["projection"] == "down"


def test_inference_rejects_direct_mode_without_worker() -> None:
    import glm52_inference as inference

    with unittest.TestCase().assertRaisesRegex(ValueError, "requires a direct Metal worker"):
        inference.generate(
            object(),
            [9703],
            1,
            expert_execution_mode="direct_iq2_gate_up",
        )


def test_moe_direct_selection_is_explicit_and_format_gated() -> None:
    import glm52_inference as inference

    store = SimpleNamespace(
        tensors={
            "blk.3.ffn_gate_exps.weight": SimpleNamespace(
                type_id=16, type_name="IQ2_XXS"
            ),
            "blk.3.ffn_up_exps.weight": SimpleNamespace(
                type_id=16, type_name="IQ2_XXS"
            ),
        }
    )
    route = {"expert_ids": list(range(8)), "weights": [0.125] * 8}
    direct_calls: list[int] = []
    reference_calls: list[tuple[int, bool]] = []

    def fake_direct(*args: object, **kwargs: object) -> tuple[list[float], dict]:
        del args
        expert = int(kwargs["expert"])
        direct_calls.append(expert)
        return [0.125, 0.125], {}

    def fake_reference(
        store: object,
        cache: object,
        layer: int,
        expert: int,
        x: list[float],
        weight: float,
        *,
        shared: bool,
        timing_sink: dict | None,
    ) -> list[float]:
        del store, cache, layer, x, weight, timing_sink
        reference_calls.append((expert, shared))
        return [1.0, 1.0]

    direct_stats = {
        "direct_routed_expert_count": 0,
        "explicit_reference_routed_expert_count": 0,
    }
    with ExitStack() as patches:
        patches.enter_context(patch.object(inference, "rms_norm", lambda *args: [1.0, 1.0]))
        patches.enter_context(
            patch.object(inference, "load_f32_vector", lambda *args: [0.0, 0.0])
        )
        patches.enter_context(patch.object(inference, "matvec_weight", lambda *args: [0.0]))
        patches.enter_context(patch("glm52_router.glm_route_real", return_value=route))
        patches.enter_context(
            patch.object(inference, "run_routed_expert_direct_iq2", fake_direct)
        )
        patches.enter_context(
            patch.object(inference, "run_expert_swiglu_cached", fake_reference)
        )
        output = inference.moe_ffn_cached(
            store,
            object(),
            3,
            [1.0, 1.0],
            direct_worker=object(),
            direct_stats=direct_stats,
        )

    assert output == [3.0, 3.0]
    assert direct_calls == list(range(8))
    assert reference_calls == [(0, True)]
    assert direct_stats == {
        "direct_routed_expert_count": 8,
        "explicit_reference_routed_expert_count": 0,
    }


def test_moe_out_of_scope_quantization_is_explicit_reference_not_fallback() -> None:
    import glm52_inference as inference

    store = SimpleNamespace(
        tensors={
            "blk.8.ffn_gate_exps.weight": SimpleNamespace(
                type_id=10, type_name="IQ2_S", dims=[6144, 2048, 256]
            ),
            "blk.8.ffn_up_exps.weight": SimpleNamespace(
                type_id=10, type_name="IQ2_S", dims=[6144, 2048, 256]
            ),
        }
    )
    route = {"expert_ids": list(range(8)), "weights": [0.125] * 8}
    stats = {
        "direct_routed_expert_count": 0,
        "explicit_reference_routed_expert_count": 0,
        "direct_error_count": 0,
        "fallback_count": 0,
        "reference_dispatches": [],
    }

    def fake_reference(*args: object, shared: bool, **kwargs: object) -> list[float]:
        del args, kwargs
        return [0.0, 0.0] if not shared else [1.0, 1.0]

    with ExitStack() as patches:
        patches.enter_context(patch.object(inference, "rms_norm", lambda *args: [1.0, 1.0]))
        patches.enter_context(
            patch.object(inference, "load_f32_vector", lambda *args: [0.0, 0.0])
        )
        patches.enter_context(patch.object(inference, "matvec_weight", lambda *args: [0.0]))
        patches.enter_context(patch("glm52_router.glm_route_real", return_value=route))
        patches.enter_context(
            patch.object(inference, "run_expert_swiglu_cached", fake_reference)
        )
        inference.moe_ffn_cached(
            store,
            object(),
            8,
            [1.0, 1.0],
            direct_worker=object(),
            direct_stats=stats,
        )

    assert stats["direct_routed_expert_count"] == 0
    assert stats["explicit_reference_routed_expert_count"] == 8
    assert stats["direct_error_count"] == 0
    assert stats["fallback_count"] == 0
    assert len(stats["reference_dispatches"]) == 8
    assert all(
        event["dispatch"] == "explicit_reference"
        and event["reason_code"] == "intentional_out_of_scope_quantization"
        and event["layer"] == 8
        and event["fallback"] is False
        for event in stats["reference_dispatches"]
    )


def test_selected_direct_failure_stops_without_reference_recovery() -> None:
    import glm52_inference as inference

    store = SimpleNamespace(
        tensors={
            "blk.3.ffn_gate_exps.weight": SimpleNamespace(
                type_id=16, type_name="IQ2_XXS", dims=[6144, 2048, 256]
            ),
            "blk.3.ffn_up_exps.weight": SimpleNamespace(
                type_id=16, type_name="IQ2_XXS", dims=[6144, 2048, 256]
            ),
        }
    )
    route = {"expert_ids": list(range(8)), "weights": [0.125] * 8}
    reference_calls = 0
    stats = {
        "direct_routed_expert_count": 0,
        "explicit_reference_routed_expert_count": 0,
        "direct_error_count": 0,
        "fallback_count": 0,
        "reference_dispatches": [],
    }

    def fail_direct(*args: object, **kwargs: object) -> tuple[list[float], dict]:
        del args, kwargs
        raise RuntimeError("synthetic direct failure")

    def fake_reference(*args: object, **kwargs: object) -> list[float]:
        nonlocal reference_calls
        del args, kwargs
        reference_calls += 1
        return [0.0, 0.0]

    with ExitStack() as patches:
        patches.enter_context(patch.object(inference, "rms_norm", lambda *args: [1.0, 1.0]))
        patches.enter_context(
            patch.object(inference, "load_f32_vector", lambda *args: [0.0, 0.0])
        )
        patches.enter_context(patch.object(inference, "matvec_weight", lambda *args: [0.0]))
        patches.enter_context(patch("glm52_router.glm_route_real", return_value=route))
        patches.enter_context(
            patch.object(inference, "run_routed_expert_direct_iq2", fail_direct)
        )
        patches.enter_context(
            patch.object(inference, "run_expert_swiglu_cached", fake_reference)
        )
        with unittest.TestCase().assertRaisesRegex(
            RuntimeError, "failed closed; reference recovery is forbidden"
        ):
            inference.moe_ffn_cached(
                store,
                object(),
                3,
                [1.0, 1.0],
                direct_worker=object(),
                direct_stats=stats,
            )

    assert stats["direct_error_count"] == 1
    assert stats["fallback_count"] == 0
    assert reference_calls == 0


class _FakeMlxArray:
    def __init__(self, value: object) -> None:
        self.value = value
        self.shape: tuple[int, ...] | None = None

    def reshape(self, shape: tuple[int, ...]) -> "_FakeMlxArray":
        self.shape = shape
        return self


class _FakeMlx:
    float32 = "float32"

    def __init__(self) -> None:
        self.arrays: list[_FakeMlxArray] = []

    def array(self, value: object, dtype: object) -> _FakeMlxArray:
        assert dtype == self.float32
        result = _FakeMlxArray(value)
        self.arrays.append(result)
        return result

    def eval(self, value: object) -> None:
        assert isinstance(value, _FakeMlxArray)


class _MatrixStore:
    def __init__(
        self,
        encoded: bytes,
        *,
        type_id: int = 16,
        type_name: str = "IQ2_XXS",
    ) -> None:
        self.encoded = encoded
        self.calls: list[tuple[str, int, int]] = []
        self.tensors = {
            "toy.weight": SimpleNamespace(
                name="toy.weight",
                dims=[256, 2, 1],
                type_id=type_id,
                type_name=type_name,
            )
        }

    def pread(self, name: str, rel: int, n: int) -> bytes:
        self.calls.append((name, rel, n))
        return self.encoded[rel : rel + n]


def _backend_without_mlx_import(mode: str) -> MlxMatrixBackend:
    backend = object.__new__(MlxMatrixBackend)
    backend.decoder_mode = mode
    backend.mx = _FakeMlx()
    return backend


@unittest.skipUnless(importlib.util.find_spec("numpy"), "NumPy is lockfile-backed")
def test_numpy_mode_reads_and_decodes_complete_iq2_matrix_once() -> None:
    encoded = (struct.pack("<e", 1.0) + bytes(64)) * 2
    store = _MatrixStore(encoded)
    backend = _backend_without_mlx_import("numpy_vectorized")
    matrix, metrics = backend.load(store, "toy.weight", 0)

    assert store.calls == [("toy.weight", 0, len(encoded))]
    assert matrix.rows == 2
    assert matrix.cols == 256
    assert matrix.decoded_bytes == 2 * 256 * 4
    assert matrix.compressed_bytes == len(encoded)
    assert matrix.quantization == "IQ2_XXS"
    assert matrix.decoder_mode == "numpy_vectorized"
    assert matrix.value.shape == (2, 256)
    assert metrics.storage_bytes_read == len(encoded)
    assert metrics.storage_read_count == 1
    assert metrics.storage_read_seconds >= 0
    assert metrics.dequant_seconds >= 0
    assert metrics.contiguous_buffer_seconds >= 0
    assert metrics.matrix_build_seconds >= 0


@unittest.skipUnless(importlib.util.find_spec("numpy"), "NumPy is lockfile-backed")
def test_numpy_mode_reads_and_decodes_complete_iq3_matrix_once() -> None:
    encoded = (struct.pack("<e", 1.0) + bytes(96)) * 2
    store = _MatrixStore(encoded, type_id=18, type_name="IQ3_XXS")
    backend = _backend_without_mlx_import("numpy_vectorized")
    matrix, metrics = backend.load(store, "toy.weight", 0)

    assert store.calls == [("toy.weight", 0, len(encoded))]
    assert matrix.rows == 2
    assert matrix.cols == 256
    assert matrix.decoded_bytes == 2 * 256 * 4
    assert matrix.compressed_bytes == len(encoded)
    assert matrix.quantization == "IQ3_XXS"
    assert matrix.decoder_mode == "numpy_vectorized"
    assert matrix.value.shape == (2, 256)
    assert metrics.storage_bytes_read == len(encoded)
    assert metrics.storage_read_count == 1


def test_scalar_mode_retains_row_reads_as_the_reference_path() -> None:
    encoded = (struct.pack("<e", 1.0) + bytes(64)) * 2
    store = _MatrixStore(encoded)
    backend = _backend_without_mlx_import("scalar_reference")
    matrix, metrics = backend.load(store, "toy.weight", 0)

    assert store.calls == [
        ("toy.weight", 0, len(encoded) // 2),
        ("toy.weight", len(encoded) // 2, len(encoded) // 2),
    ]
    assert matrix.decoder_mode == "scalar_reference"
    assert metrics.storage_bytes_read == len(encoded)
    assert metrics.storage_read_count == 2


@unittest.skipUnless(importlib.util.find_spec("numpy"), "NumPy is lockfile-backed")
def test_numpy_mode_fails_closed_on_truncated_complete_matrix() -> None:
    encoded = (struct.pack("<e", 1.0) + bytes(64)) * 2
    store = _MatrixStore(encoded[:-1])
    backend = _backend_without_mlx_import("numpy_vectorized")
    with unittest.TestCase().assertRaisesRegex(OSError, "truncated complete"):
        backend.load(store, "toy.weight", 0)
    assert len(store.calls) == 1


def test_unknown_decoder_mode_fails_before_mlx_import() -> None:
    with unittest.TestCase().assertRaisesRegex(ValueError, "unsupported decoder mode"):
        MlxMatrixBackend("invented")


def test_inference_context_forbids_auto_cpu_fallback() -> None:
    class Store:
        tensors = {
            "toy.weight": SimpleNamespace(
                name="toy.weight", dims=[2, 2], type_id=0, type_name="F32"
            )
        }

        def pread(self, name: str, rel: int, n: int) -> bytes:
            import struct

            del name
            raw = struct.pack("<4f", 1.0, 0.0, 0.0, 2.0)
            return raw[rel : rel + n]

    def fail_mlx(*args: object, **kwargs: object) -> list[float]:
        del args, kwargs
        raise RuntimeError("synthetic MLX failure")

    with patch("glm52_dense_primitives._matvec_mlx", fail_mlx):
        assert not mlx_backend_required()
        assert matvec_weight(Store(), "toy.weight", [3.0, 4.0]) == [3.0, 8.0]
        with require_mlx_backend():
            assert mlx_backend_required()
            with unittest.TestCase().assertRaisesRegex(
                RuntimeError, "synthetic MLX failure"
            ):
                matvec_weight(Store(), "toy.weight", [3.0, 4.0])
    assert not mlx_backend_required()


def test_inference_stats_delta_keeps_split_cache_metrics() -> None:
    before = {
        "storage_cache_hits": 2,
        "decoded_cache_hits": 1,
        "storage_bytes_read": 100,
        "expert_redecode_count": 4,
        "dequant_seconds": 1.25,
        "mlx_matvec_seconds": 0.5,
        "bytes_resident": 8,
        "resident_entries": 1,
        "backend": "mlx",
    }
    after = {
        "storage_cache_hits": 5,
        "decoded_cache_hits": 4,
        "storage_bytes_read": 180,
        "expert_redecode_count": 6,
        "dequant_seconds": 2.0,
        "mlx_matvec_seconds": 0.75,
        "bytes_resident": 24,
        "resident_entries": 3,
        "backend": "mlx",
    }
    delta = _stats_delta(before, after)
    assert delta["storage_cache_hits"] == 3
    assert delta["decoded_cache_hits"] == 3
    assert delta["storage_bytes_read"] == 80
    assert delta["expert_redecode_count"] == 2
    assert delta["dequant_seconds"] == 0.75
    assert delta["mlx_matvec_seconds"] == 0.25
    assert delta["bytes_resident_end"] == 24
    assert delta["resident_entries_end"] == 3
    assert "backend" not in delta


def test_checkpoint_revision_binding_matches_every_acquired_file() -> None:
    identity = _checkpoint_identity()
    assert identity["revision"] == "abc55e72527792c6e77069c99b4cb7de16fa9f23"
    assert identity["revision_status"] == "post_acquisition_content_binding"
    assert identity["file_count"] == 6
    assert len(identity["files"]) == 6


def test_inference_progress_is_atomic_identity_bound_and_route_complete() -> None:
    import glm52_inference as inference

    class FakeStats:
        def __init__(self) -> None:
            self.hits = 0
            self.misses = 0

        def to_dict(self) -> dict[str, object]:
            return {
                "hits": self.hits,
                "misses": self.misses,
                "evictions": 0,
                "admissions": 1,
                "admission_rejections": 0,
                "policy_bypasses": 0,
                "bytes_resident": 16,
                "peak_bytes_resident": 16,
                "resident_entries": 1,
                "storage_cache_hits": self.hits,
                "storage_cache_misses": self.misses,
                "decoded_cache_hits": self.hits,
                "decoded_cache_misses": self.misses,
                "storage_bytes_read": 2 * self.misses,
                "storage_bytes_avoided": 2 * self.hits,
                "decoded_bytes_materialized": 16 * self.misses,
                "decoded_bytes_avoided": 16 * self.hits,
                "expert_redecode_count": self.misses,
                "storage_read_seconds": 0.0,
                "dequant_seconds": 0.0,
                "mlx_matrix_build_seconds": 0.0,
                "mlx_matvec_count": self.hits + self.misses,
                "mlx_matvec_seconds": 0.0,
                "transient_releases": 0,
                "cpu_fallbacks": 0,
                "backend": "fake_mlx",
                "device": "fake_gpu",
                "mlx_version": "test",
            }

    class FakeCache:
        def __init__(
            self, max_bytes: int, policy: str, decoder_mode: str = "scalar_reference"
        ) -> None:
            assert max_bytes == 16
            assert policy == "decoded_shared_only"
            assert decoder_mode == "scalar_reference"
            self.stats = FakeStats()

    class Pressure:
        def to_public_dict(self) -> dict[str, object]:
            return {"level": "normal", "rss_bytes": 1234}

    def fake_layer(
        store: object,
        cache: FakeCache,
        layer: int,
        residual: list[float],
        kv: object,
        pos: int,
        route_sink: list[dict[str, object]],
    ) -> list[float]:
        del store, kv
        if pos == 0:
            cache.stats.misses += 1
        else:
            cache.stats.hits += 1
        route_sink.append(
            {"layer": layer, "expert_ids": list(range(8)), "weights": [0.125] * 8}
        )
        return residual

    def fake_logits(store: object, hidden: list[float]) -> list[float]:
        del store, hidden
        logits = [0.0] * 21616
        logits[21615] = 1.0
        return logits

    with ExitStack() as patches:
        patches.enter_context(patch.object(inference, "N_LAYER", 1))
        patches.enter_context(patch.object(inference, "ExpertSlabCache", FakeCache))
        patches.enter_context(
            patch.object(
                inference, "embed_token", lambda store, token: [float(token)]
            )
        )
        patches.enter_context(
            patch.object(inference, "layer_forward_inference", fake_layer)
        )
        patches.enter_context(patch.object(inference, "logits_from_hidden", fake_logits))
        patches.enter_context(
            patch.object(inference, "sample_pressure", lambda: Pressure())
        )

        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "candidate.json"
            result = inference.generate(
                object(),
                [9703],
                1,
                mode="inference",
                cache_bytes=16,
                dense_mode="whole_matrix_numpy_q5_q8_q6_head_numpy",
                progress_path=output,
                evidence_context={
                    "source_commit": "a" * 40,
                    "checkpoint": {"checkpoint_set_sha256": "b" * 64},
                },
            )
            assert json.loads(output.read_text()) == result
            assert not (output.parent / f".{output.name}.tmp").exists()

    assert result["schema"] == "pulsarmlx.research.glm52-inference"
    assert result["schema_version"] == "2.0.0"
    assert result["actual_status"] == "passed"
    assert result["source_commit"] == "a" * 40
    assert result["generated_token_ids"] == [9703, 21615]
    assert result["dense_read_mode"] == "whole_matrix_numpy_q5_q8_q6_head_numpy"
    assert result["matches_golden_prefix"] is True
    assert len(result["routing"]) == 2
    assert result["routing"][0]["layers"][0]["expert_ids"] == list(range(8))
    assert result["timings"][1]["cache_delta"]["decoded_cache_hits"] == 1
    assert result["expert_cache"]["cpu_fallbacks"] == 0


def test_inference_stops_before_executing_a_divergent_token_stack() -> None:
    import glm52_inference as inference

    class FakeStats:
        def to_dict(self) -> dict[str, object]:
            return {
                "bytes_resident": 0,
                "resident_entries": 0,
                "cpu_fallbacks": 0,
            }

    class FakeCache:
        def __init__(self, **kwargs: object) -> None:
            del kwargs
            self.stats = FakeStats()

    completed_tokens: list[int] = []

    def fake_stack(
        store: object,
        *,
        token_id: int,
        position: int,
        mode: str,
        cache: FakeCache,
        kvs: list[object],
        direct_worker: object = None,
        direct_stats: object = None,
    ) -> tuple[list[float], dict[str, object]]:
        del store, position, mode, cache, kvs, direct_worker, direct_stats
        completed_tokens.append(token_id)
        return [0.0], {
            "stack_seconds": 1.0,
            "layers": [],
            "routes": [],
            "resource_after": {"level": "normal"},
        }

    with ExitStack() as patches:
        patches.enter_context(patch.object(inference, "ExpertSlabCache", FakeCache))
        patches.enter_context(patch.object(inference, "_run_stack", fake_stack))
        patches.enter_context(
            patch.object(inference, "require_mlx_backend", lambda: nullcontext())
        )
        patches.enter_context(
            patch.object(inference, "logits_from_hidden", lambda store, hidden: [0.0, 1.0])
        )
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "divergent.json"
            result = inference.generate(
                object(),
                [9703],
                8,
                mode="inference",
                cache_bytes=16,
                progress_path=output,
            )
            assert json.loads(output.read_text()) == result

    assert result["actual_status"] == "failed"
    assert result["generated_token_ids"] == [9703, 1]
    assert result["matches_golden_prefix"] is False
    assert result["timings"][0]["token"] == 9703
    assert len(result["timings"]) == 1
    assert completed_tokens == [9703]


def load_tests(
    loader: unittest.TestLoader,
    tests: unittest.TestSuite,
    pattern: str | None,
) -> unittest.TestSuite:
    """Expose the same function tests to the repository's unittest CI runner."""

    del loader, tests, pattern
    suite = unittest.TestSuite()
    for function in (
        test_shared_only_policy_bypasses_routed_and_reuses_shared,
        test_shared_admission_is_protected_and_bounded_without_eviction,
        test_clear_drops_residency_but_resets_all_counters,
        test_backend_failure_propagates_without_cpu_fallback,
        test_matvec_cached_rows_reference,
        test_direct_iq2_routed_expert_keeps_down_on_reference_backend,
        test_inference_rejects_direct_mode_without_worker,
        test_moe_direct_selection_is_explicit_and_format_gated,
        test_moe_out_of_scope_quantization_is_explicit_reference_not_fallback,
        test_selected_direct_failure_stops_without_reference_recovery,
        test_numpy_mode_reads_and_decodes_complete_iq2_matrix_once,
        test_numpy_mode_reads_and_decodes_complete_iq3_matrix_once,
        test_scalar_mode_retains_row_reads_as_the_reference_path,
        test_numpy_mode_fails_closed_on_truncated_complete_matrix,
        test_unknown_decoder_mode_fails_before_mlx_import,
        test_inference_context_forbids_auto_cpu_fallback,
        test_inference_stats_delta_keeps_split_cache_metrics,
        test_checkpoint_revision_binding_matches_every_acquired_file,
        test_inference_progress_is_atomic_identity_bound_and_route_complete,
        test_inference_stops_before_executing_a_divergent_token_stack,
    ):
        suite.addTest(unittest.FunctionTestCase(function))
    return suite
