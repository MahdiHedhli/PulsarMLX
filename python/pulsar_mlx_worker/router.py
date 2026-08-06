"""Bounded Feature 002 complete-router execution.

The public worker operation resolves committed synthetic cases or the two
frozen real-input cases.  It never accepts a model path through the control
protocol, never imports MLX before host validation completes, and reads only
the input-object byte range of the public oracle publication--never the
independent outputs used to judge the implementation.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
import errno
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import struct
import threading
import time
from types import MappingProxyType
from typing import Any

from .protocol import STABLE_ERROR_CODES, is_stable_identifier
from .runtime import (
    GPU_DEVICE_ID,
    MemoryGauges,
    RuntimeContractError,
    collect_memory_gauges,
    sanitize_gpu_descriptor,
)


ROUTER_CONTRACT_ID = "qwen3moe-layer0-router-parity-v1"
ROUTER_OPERATION_ID = "complete_router_projection_topk"
SINGLE_ROW_CASE_ID = "generated-qwen3moe-router-single-row-v1"
BOUNDED_BATCH_CASE_ID = "generated-qwen3moe-router-two-row-v1"
REAL_SINGLE_ROW_CASE_ID = "qwen3moe-layer0-router-token0-row0-v1"
REAL_BATCH_CASE_ID = "qwen3moe-layer0-router-token0-token1-batch-v1"
HIDDEN_WIDTH = 2_048
EXPERT_COUNT = 128
TOP_K = 8
MAXIMUM_ROWS = 2
OUTPUT_DTYPE = "float32"
TIE_RULE = "probability_descending_then_expert_id_ascending"
NORMALIZATION_RULE = (
    "full_128_way_softmax_then_selected_probability_renormalization"
)

_FIXTURE_ID = "generated-qwen3moe-router-v1"
_HIDDEN_FIXTURE_ID = "generated-qwen3moe-router-hidden-states-v1"
_WEIGHT_FIXTURE_ID = "generated-qwen3moe-router-weights-v1"
_PROVENANCE = "synthetic_generated_model_free"
_FIXTURE_ROOT = (
    Path(__file__).resolve().parents[2] / "fixtures" / "research" / "router-v1"
)
_REAL_FIXTURE_PATH = (
    _FIXTURE_ROOT / "real" / "f002-router-oracle-freeze-0001.json"
)
_MANIFEST_PATH = _FIXTURE_ROOT / "manifest.json"
_HIDDEN_PATH = _FIXTURE_ROOT / "golden" / "hidden_states.json"
_WEIGHT_RECIPE_PATH = _FIXTURE_ROOT / "golden" / "weight_recipe.json"
_MAX_MANIFEST_BYTES = 64 * 1024
_MAX_HIDDEN_DOCUMENT_BYTES = 128 * 1024
_MAX_RECIPE_BYTES = 16 * 1024
_WEIGHT_ELEMENT_COUNT = EXPERT_COUNT * HIDDEN_WIDTH
_WEIGHT_BYTES = _WEIGHT_ELEMENT_COUNT * 4
_MODEL_FILE_FD = 198
_MODEL_FILE_BYTES = 32_483_931_648
_ROUTER_TENSOR_OFFSET = 1_115_085_312
_ROUTER_TENSOR_BYTES = 1_048_576
_ROUTER_TENSOR_END = 1_116_133_888
_ROUTER_TENSOR_SHA256 = (
    "98d82da676c9c2df99badbc8b05912471417ad60cc63ce719a25b54dca1d531c"
)
_REAL_FIXTURE_BYTES = 148_909
_REAL_INPUT_FRAGMENT_OFFSET = 6_669
_REAL_INPUT_FRAGMENT_BYTES = 121_540
_REAL_INPUT_FRAGMENT_END = 128_209
_REAL_INPUT_FRAGMENT_SHA256 = (
    "8d16f0839248c8579d3307cdb43be95d144b2af7f6e6e71f23faaf6610af9a1a"
)
_REAL_INPUT_SHA256 = (
    "978205a61fb31d03a8627fd5b9c9319e4c32ef7af0d3d934ccaddda9defc68a7"
)
_REAL_INPUT_ROW_SHA256 = (
    "062e42f277e26af0042d52e5e30f895523c7f26cffb866b970dc0ae1c1dbe296",
    "278810be1143949ef019448e352c8bf74c7ab0c1c7bb8dd7b526dbafbacf0eaf",
)
_TIMING_PROFILE_ENV = "PULSARMLX_ROUTER_TIMING_PROFILE"
_TIMING_PROFILE_MINIMAL = "minimal"
_TIMING_PROFILE_COSTLY = "costly"
_TIMING_PROFILE_STAGE = "stage"
_TIMING_PROFILES = frozenset(
    {_TIMING_PROFILE_MINIMAL, _TIMING_PROFILE_COSTLY, _TIMING_PROFILE_STAGE}
)
_PROBABILITY_SUM_TOLERANCE = 1.0e-6
_PROBABILITY_RELATIVE_TOLERANCE = 1.0e-6
_MAX_U64 = (1 << 64) - 1
_MAX_TIMING_OBSERVATIONS = 1_024
_MAX_TIMING_REASON_CHARS = 512
_TIMING_STAGES = frozenset(
    {
        "setup_admission",
        "file_io",
        "storage_validation_f32_decode",
        "dequantization",
        "host_to_device",
        "graph_construction",
        "compilation",
        "router_projection",
        "top_k",
        "normalization",
        "total_evaluated_router",
        "synchronized_readback",
        "end_to_end_router_command",
    }
)
_TIMING_STAGE_STATUSES = frozenset(
    {"observed", "unavailable", "not_applicable"}
)
_EVALUATED_TIMING_STAGES = frozenset(
    {
        "host_to_device",
        "graph_construction",
        "compilation",
        "router_projection",
        "top_k",
        "normalization",
        "total_evaluated_router",
    }
)
_OBSERVATION_KINDS = frozenset(
    {"warmup", "measurement", "clean_process_replication"}
)
_PROCESS_STATES = frozenset({"fresh_process", "reused_process"})
_TIMING_CONDITIONS = frozenset(
    {"warm", "first_read_new_process_os_cache_uncontrolled", "controlled_cold"}
)
_INSTRUMENTATION_MODES = frozenset(
    {"minimally_instrumented", "stage_instrumented"}
)
_OBSERVATION_STATUSES = frozenset({"passed", "failed", "aborted"})
_F32_DEQUANTIZATION_REASON = "f32_router_requires_no_dequantization"
_CACHE_FILE_IO_REASON = "validated_router_tensor_cache_hit_no_file_read"
_CACHE_DECODE_REASON = "validated_router_tensor_cache_hit_no_decode"
_ROUTER_TENSOR_CACHE_HIT = "cache_hit"
_ROUTER_TENSOR_READ_AND_CACHED = "read_and_cached"
_ROUTER_TENSOR_NOT_APPLICABLE = "not_applicable"
_INSEPARABLE_TRANSFER_REASON = "host_to_device_not_separable_from_evaluated_total"
_LAZY_GRAPH_REASON = "lazy_graph_construction_not_separable_from_evaluation"
_COMPILATION_REASON = "mlx_compilation_not_independently_observable"
_SETUP_REASON = "host_admission_completed_outside_router_timing"

_SYNTHETIC_CASE_ROWS = {
    SINGLE_ROW_CASE_ID: 1,
    BOUNDED_BATCH_CASE_ID: 2,
}
_CASE_ROWS = {
    **_SYNTHETIC_CASE_ROWS,
    REAL_SINGLE_ROW_CASE_ID: 1,
    REAL_BATCH_CASE_ID: 2,
}
_ROW_IDS = (
    "generated-qwen3moe-router-one-hot-column-0-v1",
    "generated-qwen3moe-router-one-hot-column-1-v1",
)
_EXPECTED_TOP8_IDS = (
    (83, 38, 121, 76, 31, 114, 69, 24),
    (24, 123, 94, 65, 36, 7, 106, 77),
)

_MINIMAL_TIMING_STAGES = frozenset(
    {"dequantization", "total_evaluated_router"}
)
_COSTLY_TIMING_STAGES = frozenset(
    {
        "file_io",
        "storage_validation_f32_decode",
        "dequantization",
        "host_to_device",
        "total_evaluated_router",
        "end_to_end_router_command",
    }
)
_STAGE_TIMING_STAGES = _TIMING_STAGES


class RouterCaseScope(Enum):
    """Internal provenance boundary controlling the cutoff-tie policy."""

    SYNTHETIC_FIXTURE = "synthetic_fixture"
    REAL_CHECKPOINT = "real_checkpoint"


class RouterError(RuntimeContractError):
    """Stable bounded failure at the Feature 002 router boundary."""


@dataclass(frozen=True, slots=True)
class _ModelFileSnapshot:
    device: int
    inode: int
    mode: int
    size: int
    modified_ns: int
    changed_ns: int


@dataclass(frozen=True, slots=True)
class _CachedRouterTensor:
    snapshot: _ModelFileSnapshot
    weights: tuple[tuple[float, ...], ...]


_REAL_ROUTER_CACHE_LOCK = threading.Lock()
_REAL_ROUTER_CACHE: _CachedRouterTensor | None = None


@dataclass(frozen=True, slots=True)
class RouterTimingStage:
    """One observed or explicitly unavailable router timing boundary."""

    status: str
    duration_ns: int | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.status, str)
            or self.status not in _TIMING_STAGE_STATUSES
        ):
            raise _timing_contract_error("router timing stage status is invalid")
        if self.status == "observed":
            _validate_positive_nanoseconds(
                self.duration_ns,
                "router timing duration",
            )
            if self.reason is not None:
                raise _timing_contract_error(
                    "an observed router timing stage cannot have a reason"
                )
            return
        if self.duration_ns is not None:
            raise _timing_contract_error(
                "an unavailable router timing stage cannot have a duration"
            )
        sanitized_reason = _sanitize_timing_text(
            self.reason,
            "router timing stage reason",
        )
        object.__setattr__(self, "reason", sanitized_reason)

    def to_protocol_result(self) -> dict[str, object]:
        if self.status == "observed":
            return {"status": self.status, "duration_ns": self.duration_ns}
        return {"status": self.status, "reason": self.reason}


@dataclass(frozen=True, slots=True)
class RouterExecutionTiming:
    """One worker-owned evaluated timing envelope without host-owned labels."""

    instrumentation_mode: str
    evaluated: bool
    synchronized: bool
    stages: Mapping[str, RouterTimingStage]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.instrumentation_mode, str)
            or self.instrumentation_mode not in _INSTRUMENTATION_MODES
        ):
            raise _timing_contract_error("router execution timing mode is invalid")
        if self.evaluated is not True or self.synchronized is not True:
            raise _timing_contract_error(
                "router execution timing lacks its evaluated synchronization barrier"
            )
        if not isinstance(self.stages, Mapping):
            raise _timing_contract_error("router execution timing stages are invalid")
        frozen_stages = dict(self.stages)
        if not frozen_stages or len(frozen_stages) > len(_TIMING_STAGES):
            raise _timing_contract_error("router execution timing stages are invalid")
        for stage, value in frozen_stages.items():
            _validate_timing_stage_name(stage)
            if not isinstance(value, RouterTimingStage):
                raise _timing_contract_error("router execution timing stage is invalid")
            if stage != "dequantization" and value.status == "not_applicable":
                raise _timing_contract_error(
                    "only F32 dequantization can be marked not applicable"
                )
        dequantization = frozen_stages.get("dequantization")
        if (
            dequantization is None
            or dequantization.status != "not_applicable"
            or dequantization.reason != _F32_DEQUANTIZATION_REASON
        ):
            raise _timing_contract_error(
                "router execution timing lacks F32 dequantization evidence"
            )
        if self.instrumentation_mode == "minimally_instrumented":
            stage_names = frozenset(frozen_stages)
            if stage_names not in {
                _MINIMAL_TIMING_STAGES,
                _COSTLY_TIMING_STAGES,
            }:
                raise _timing_contract_error(
                    "minimal router execution timing has an invalid stage profile"
                )
            if frozen_stages["total_evaluated_router"].status != "observed":
                raise _timing_contract_error(
                    "minimal router execution timing lacks its observed total"
                )
            if stage_names == _COSTLY_TIMING_STAGES:
                _validate_costly_execution_stages(frozen_stages)
        else:
            if frozenset(frozen_stages) != _STAGE_TIMING_STAGES:
                raise _timing_contract_error(
                    "stage router execution timing lacks its exact stage inventory"
                )
            if not any(
                stage in _EVALUATED_TIMING_STAGES
                and stage != "total_evaluated_router"
                and value.status == "observed"
                for stage, value in frozen_stages.items()
            ):
                raise _timing_contract_error(
                    "stage router execution timing lacks an evaluated diagnostic"
                )
            _validate_stage_execution_stages(frozen_stages)
        object.__setattr__(self, "stages", MappingProxyType(frozen_stages))

    def to_protocol_result(self) -> dict[str, object]:
        return {
            "monotonic_clock": "perf_counter_ns",
            "instrumentation_mode": self.instrumentation_mode,
            "evaluated": self.evaluated,
            "synchronized": self.synchronized,
            "stages": {
                stage: value.to_protocol_result()
                for stage, value in self.stages.items()
            },
        }


@dataclass(frozen=True, slots=True)
class RouterTimingObservation:
    """Immutable raw timing evidence for one attempted router execution."""

    observation_id: str
    run_index: int
    observation_kind: str
    process_state: str
    condition: str
    instrumentation_mode: str
    status: str
    requested_device: str
    selected_device: str
    fallback_used: bool
    evaluated: bool
    synchronized: bool
    output_sha256: str | None
    correctness_passed: bool | None
    stages: Mapping[str, RouterTimingStage]
    failure: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        if not is_stable_identifier(self.observation_id):
            raise _timing_contract_error("router timing observation ID is invalid")
        if (
            isinstance(self.run_index, bool)
            or not isinstance(self.run_index, int)
            or not 0 <= self.run_index <= _MAX_U64
        ):
            raise _timing_contract_error("router timing run index is invalid")
        if (
            not isinstance(self.observation_kind, str)
            or self.observation_kind not in _OBSERVATION_KINDS
        ):
            raise _timing_contract_error("router timing observation kind is invalid")
        if (
            not isinstance(self.process_state, str)
            or self.process_state not in _PROCESS_STATES
        ):
            raise _timing_contract_error("router timing process state is invalid")
        if (
            not isinstance(self.condition, str)
            or self.condition not in _TIMING_CONDITIONS
        ):
            raise _timing_contract_error("router timing condition is invalid")
        if (
            not isinstance(self.instrumentation_mode, str)
            or self.instrumentation_mode not in _INSTRUMENTATION_MODES
        ):
            raise _timing_contract_error("router timing instrumentation mode is invalid")
        if (
            not isinstance(self.status, str)
            or self.status not in _OBSERVATION_STATUSES
        ):
            raise _timing_contract_error("router timing observation status is invalid")
        if self.requested_device != GPU_DEVICE_ID:
            raise _timing_contract_error("router timing requested device is invalid")
        if (
            not isinstance(self.selected_device, str)
            or self.selected_device not in {GPU_DEVICE_ID, "not_available"}
        ):
            raise _timing_contract_error("router timing selected device is invalid")
        if not isinstance(self.fallback_used, bool) or self.fallback_used:
            raise _timing_contract_error("router timing fallback state is invalid")
        if not isinstance(self.evaluated, bool) or not isinstance(
            self.synchronized, bool
        ):
            raise _timing_contract_error("router timing barrier flags are invalid")
        if self.synchronized and not self.evaluated:
            raise _timing_contract_error(
                "router timing cannot synchronize unevaluated work"
            )
        if self.selected_device == "not_available" and (
            self.evaluated or self.synchronized
        ):
            raise _timing_contract_error(
                "unavailable router timing device contradicts completed work"
            )
        if self.output_sha256 is not None and not _is_lowercase_sha256(
            self.output_sha256
        ):
            raise _timing_contract_error("router timing output hash is invalid")
        if self.correctness_passed is not None and not isinstance(
            self.correctness_passed, bool
        ):
            raise _timing_contract_error("router timing correctness state is invalid")

        if not isinstance(self.stages, Mapping):
            raise _timing_contract_error("router timing stage set is invalid")
        frozen_stages = dict(self.stages)
        if not frozen_stages or len(frozen_stages) > len(_TIMING_STAGES):
            raise _timing_contract_error("router timing stage set is invalid")
        for stage, value in frozen_stages.items():
            _validate_timing_stage_name(stage)
            if not isinstance(value, RouterTimingStage):
                raise _timing_contract_error("router timing stage value is invalid")
            if stage != "dequantization" and value.status == "not_applicable":
                raise _timing_contract_error(
                    "only F32 dequantization can be marked not applicable"
                )
        dequantization = frozen_stages.get("dequantization")
        if (
            dequantization is None
            or dequantization.status != "not_applicable"
            or dequantization.reason != _F32_DEQUANTIZATION_REASON
        ):
            raise _timing_contract_error(
                "F32 router dequantization must be explicitly not applicable"
            )
        object.__setattr__(self, "stages", MappingProxyType(frozen_stages))

        frozen_failure = _freeze_timing_failure(self.failure)
        object.__setattr__(self, "failure", frozen_failure)
        if self.status == "passed":
            if (
                self.selected_device != GPU_DEVICE_ID
                or not self.evaluated
                or not self.synchronized
                or self.output_sha256 is None
                or self.correctness_passed is not True
                or frozen_failure is not None
            ):
                raise _timing_contract_error(
                    "passing router timing observation contradicts its evidence"
                )
        elif self.status in {"failed", "aborted"}:
            if frozen_failure is None:
                raise _timing_contract_error(
                    "failed router timing observation lacks bounded failure evidence"
                )
            if self.correctness_passed is True:
                raise _timing_contract_error(
                    "unsuccessful router timing cannot claim correctness"
                )
            if self.output_sha256 is None:
                if self.correctness_passed is not None:
                    raise _timing_contract_error(
                        "unsuccessful router timing has incomplete output evidence"
                    )
            elif (
                self.status != "failed"
                or self.selected_device != GPU_DEVICE_ID
                or not self.evaluated
                or not self.synchronized
                or self.correctness_passed is not False
            ):
                raise _timing_contract_error(
                    "unsuccessful router timing output evidence is inconsistent"
                )

        if self.instrumentation_mode == "minimally_instrumented":
            total = frozen_stages.get("total_evaluated_router")
            if self.status == "passed" and (
                total is None or total.status != "observed"
            ):
                raise _timing_contract_error(
                    "passing minimal router timing lacks its evaluated total"
                )
            if self.status == "passed" and frozenset(frozen_stages) not in {
                _MINIMAL_TIMING_STAGES,
                _COSTLY_TIMING_STAGES,
            }:
                raise _timing_contract_error(
                    "passing minimal router timing has an invalid stage profile"
                )
        elif self.status == "passed" and not any(
            stage in _EVALUATED_TIMING_STAGES
            and stage != "total_evaluated_router"
            and value.status == "observed"
            for stage, value in frozen_stages.items()
        ):
            raise _timing_contract_error(
                "passing stage timing lacks an evaluated diagnostic stage"
            )

    def to_protocol_result(self) -> dict[str, object]:
        result: dict[str, object] = {
            "observation_id": self.observation_id,
            "run_index": self.run_index,
            "observation_kind": self.observation_kind,
            "process_state": self.process_state,
            "condition": self.condition,
            "instrumentation_mode": self.instrumentation_mode,
            "monotonic_clock": "perf_counter_ns",
            "stages": {
                stage: value.to_protocol_result()
                for stage, value in self.stages.items()
            },
            "status": self.status,
            "requested_device": self.requested_device,
            "selected_device": self.selected_device,
            "fallback_used": self.fallback_used,
            "evaluated": self.evaluated,
            "synchronized": self.synchronized,
            "output_sha256": self.output_sha256,
            "correctness_passed": self.correctness_passed,
        }
        if self.failure is not None:
            result["failure"] = dict(self.failure)
        return result


class RouterTimingRecorder:
    """Collect one fail-closed timing observation using an injected clock."""

    def __init__(self, *, clock_ns: Callable[[], int] = time.perf_counter_ns) -> None:
        if not callable(clock_ns):
            raise _timing_contract_error("router timing clock is not callable")
        self._clock_ns = clock_ns
        self._stages: dict[str, RouterTimingStage] = {}
        self._evaluated = False
        self._synchronized = False
        self._finished = False
        self._failed_stage: str | None = None

    def measure_evaluated(
        self,
        *,
        stage: str,
        mx_module: Any,
        gpu: Any,
        operation: Callable[[], object],
    ) -> tuple[object, ...]:
        """Run one operation and stop its clock only after eval then sync."""

        self._require_open()
        _validate_timing_stage_name(stage)
        if stage not in _EVALUATED_TIMING_STAGES:
            raise _timing_contract_error(
                "router timing stage is not an evaluated device boundary"
            )
        self._require_new_stage(stage)
        if self._failed_stage is not None:
            raise _timing_contract_error(
                "router timing cannot continue after an evaluated stage failure"
            )
        if not callable(operation):
            raise _timing_contract_error("router timing operation is not callable")
        self._evaluated = False
        self._synchronized = False
        try:
            started_ns = self._read_clock()
            outputs_value = operation()
            if (
                not isinstance(outputs_value, Sequence)
                or isinstance(outputs_value, (str, bytes, bytearray, memoryview))
                or not outputs_value
            ):
                raise _timing_contract_error(
                    "evaluated router timing operation returned invalid outputs"
                )
            outputs = tuple(outputs_value)
            mx_module.eval(*outputs)
            self._evaluated = True
            mx_module.synchronize(gpu)
            self._synchronized = True
            completed_ns = self._read_clock()
            if completed_ns <= started_ns:
                raise _timing_contract_error(
                    "router timing clock did not advance monotonically"
                )
        except RouterError as error:
            self._failed_stage = stage
            self._stages[stage] = RouterTimingStage(
                status="unavailable",
                reason=error.message,
            )
            raise
        except RuntimeContractError as error:
            self._failed_stage = stage
            self._stages[stage] = RouterTimingStage(
                status="unavailable",
                reason=error.message,
            )
            raise RouterError(error.code, error.message) from error
        except Exception as error:
            self._failed_stage = stage
            self._stages[stage] = RouterTimingStage(
                status="unavailable",
                reason="the evaluated router timing stage did not complete",
            )
            raise RouterError(
                "evaluation_failed",
                "the evaluated router timing stage did not complete",
            ) from error
        self._stages[stage] = RouterTimingStage(
            status="observed",
            duration_ns=completed_ns - started_ns,
        )
        return outputs

    def measure_host(
        self,
        *,
        stage: str,
        operation: Callable[[], object],
    ) -> object:
        """Measure one host-only stage with the same monotonic clock."""

        self._require_open()
        _validate_timing_stage_name(stage)
        if stage in _EVALUATED_TIMING_STAGES or stage == "dequantization":
            raise _timing_contract_error(
                "router host timing stage requires an unevaluated boundary"
            )
        self._require_new_stage(stage)
        if self._failed_stage is not None:
            raise _timing_contract_error(
                "router timing cannot continue after a stage failure"
            )
        if not callable(operation):
            raise _timing_contract_error("router timing operation is not callable")
        try:
            started_ns = self._read_clock()
            result = operation()
            completed_ns = self._read_clock()
            if completed_ns <= started_ns:
                raise _timing_contract_error(
                    "router timing clock did not advance monotonically"
                )
        except RouterError as error:
            self._failed_stage = stage
            self._stages[stage] = RouterTimingStage(
                status="unavailable",
                reason=error.message,
            )
            raise
        except RuntimeContractError as error:
            self._failed_stage = stage
            self._stages[stage] = RouterTimingStage(
                status="unavailable",
                reason=error.message,
            )
            raise RouterError(error.code, error.message) from error
        except Exception as error:
            self._failed_stage = stage
            self._stages[stage] = RouterTimingStage(
                status="unavailable",
                reason="the host router timing stage did not complete",
            )
            raise RouterError(
                "internal_worker_error",
                "the host router timing stage did not complete",
            ) from error
        self._stages[stage] = RouterTimingStage(
            status="observed",
            duration_ns=completed_ns - started_ns,
        )
        return result

    def record_observed(self, *, stage: str, duration_ns: int) -> None:
        """Retain a positive duration measured around a composite boundary."""

        self._require_open()
        _validate_timing_stage_name(stage)
        self._require_new_stage(stage)
        self._stages[stage] = RouterTimingStage(
            status="observed",
            duration_ns=duration_ns,
        )

    def record_not_applicable(self, *, stage: str, reason: str) -> None:
        if stage != "dequantization" or reason != _F32_DEQUANTIZATION_REASON:
            raise _timing_contract_error(
                "only F32 dequantization has a frozen not-applicable state"
            )
        self._record_unobserved(stage, status="not_applicable", reason=reason)

    def record_unavailable(self, *, stage: str, reason: str) -> None:
        if stage == "dequantization":
            raise _timing_contract_error(
                "F32 router dequantization is not applicable, not unavailable"
            )
        self._record_unobserved(stage, status="unavailable", reason=reason)

    def finish(
        self,
        *,
        observation_id: str,
        run_index: int,
        observation_kind: str,
        process_state: str,
        condition: str,
        instrumentation_mode: str,
        status: str,
        requested_device: str,
        selected_device: str,
        fallback_used: bool,
        output_sha256: str | None,
        correctness_passed: bool | None,
        failure: Mapping[str, str] | None = None,
    ) -> RouterTimingObservation:
        self._require_open()
        if self._failed_stage is not None:
            if status not in {"failed", "aborted"}:
                raise _timing_contract_error(
                    "a failed evaluated timing stage cannot produce a passing observation"
                )
            if not isinstance(failure, Mapping) or failure.get("stage") != self._failed_stage:
                raise _timing_contract_error(
                    "router timing failure does not identify its failed stage"
                )
            failed_stage = self._stages.get(self._failed_stage)
            if failed_stage is None or failed_stage.status != "unavailable":
                raise _timing_contract_error(
                    "router timing failure lacks its unavailable stage record"
                )
        observation = RouterTimingObservation(
            observation_id=observation_id,
            run_index=run_index,
            observation_kind=observation_kind,
            process_state=process_state,
            condition=condition,
            instrumentation_mode=instrumentation_mode,
            status=status,
            requested_device=requested_device,
            selected_device=selected_device,
            fallback_used=fallback_used,
            evaluated=self._evaluated,
            synchronized=self._synchronized,
            output_sha256=output_sha256,
            correctness_passed=correctness_passed,
            stages=MappingProxyType(dict(self._stages)),
            failure=failure,
        )
        self._finished = True
        return observation

    def execution_timing(
        self,
        *,
        instrumentation_mode: str,
    ) -> RouterExecutionTiming:
        """Freeze worker-owned timing before host orchestration adds labels."""

        self._require_open()
        if self._failed_stage is not None:
            raise _timing_contract_error(
                "failed router timing cannot become a successful execution envelope"
            )
        return RouterExecutionTiming(
            instrumentation_mode=instrumentation_mode,
            evaluated=self._evaluated,
            synchronized=self._synchronized,
            stages=MappingProxyType(dict(self._stages)),
        )

    def _record_unobserved(self, stage: str, *, status: str, reason: str) -> None:
        self._require_open()
        _validate_timing_stage_name(stage)
        self._require_new_stage(stage)
        self._stages[stage] = RouterTimingStage(status=status, reason=reason)

    def _read_clock(self) -> int:
        value = self._clock_ns()
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= _MAX_U64:
            raise _timing_contract_error(
                "router timing clock did not return unsigned integer nanoseconds"
            )
        return value

    def _require_open(self) -> None:
        if self._finished:
            raise _timing_contract_error("router timing recorder is already finished")

    def _require_new_stage(self, stage: str) -> None:
        if stage in self._stages:
            raise _timing_contract_error("router timing stage is duplicated")


class RouterTimingSeries:
    """Append-only ordered retention for every attempted timing observation."""

    def __init__(self) -> None:
        self._observations: list[RouterTimingObservation] = []
        self._observation_ids: set[str] = set()
        self._series_indices: set[tuple[str, str, str, str, int]] = set()
        self._next_indices: dict[tuple[str, str, str, str], int] = {}
        self._passed_output_sha256: str | None = None
        self._process_replication_id: str | None = None

    @property
    def raw_timing_observations(self) -> tuple[RouterTimingObservation, ...]:
        return tuple(self._observations)

    def retain(self, observation: RouterTimingObservation) -> None:
        if not isinstance(observation, RouterTimingObservation):
            raise _timing_contract_error("router timing series value is invalid")
        if len(self._observations) >= _MAX_TIMING_OBSERVATIONS:
            raise RouterError(
                "resource_limit",
                "router timing observation count exceeds its bound",
            )
        series_key = (
            observation.observation_kind,
            observation.process_state,
            observation.condition,
            observation.instrumentation_mode,
        )
        series_index = (*series_key, observation.run_index)
        if observation.observation_id in self._observation_ids:
            raise _timing_contract_error("router timing observation ID is duplicated")
        if series_index in self._series_indices:
            raise _timing_contract_error(
                "router timing compatible-series index is duplicated"
            )
        if observation.run_index != self._next_indices.get(series_key, 0):
            raise _timing_contract_error(
                "router timing observation indices are not contiguous"
            )
        if (
            observation.status == "passed"
            and self._passed_output_sha256 is not None
            and observation.output_sha256 != self._passed_output_sha256
        ):
            raise _timing_contract_error(
                "passing router timing output hashes are inconsistent"
            )
        self._observations.append(observation)
        self._observation_ids.add(observation.observation_id)
        self._series_indices.add(series_index)
        self._next_indices[series_key] = observation.run_index + 1
        if observation.status == "passed" and self._passed_output_sha256 is None:
            self._passed_output_sha256 = observation.output_sha256

    def to_protocol_result(self, *, process_replication_id: str) -> list[dict[str, object]]:
        if not is_stable_identifier(process_replication_id):
            raise _timing_contract_error(
                "router timing process replication ID is invalid"
            )
        if (
            self._process_replication_id is not None
            and process_replication_id != self._process_replication_id
        ):
            raise _timing_contract_error(
                "router timing series process replication ID cannot be relabeled"
            )
        self._process_replication_id = process_replication_id
        result: list[dict[str, object]] = []
        for observation in self._observations:
            payload = observation.to_protocol_result()
            payload["process_replication_id"] = process_replication_id
            result.append(payload)
        return result


def _timing_contract_error(message: str) -> RouterError:
    return RouterError("internal_worker_error", message)


def _validate_costly_execution_stages(
    stages: Mapping[str, RouterTimingStage],
) -> None:
    if any(
        stages[name].status != "observed"
        for name in (
            "file_io",
            "storage_validation_f32_decode",
            "total_evaluated_router",
            "end_to_end_router_command",
        )
    ):
        raise _timing_contract_error(
            "costly router execution lacks an observed measured boundary"
        )
    transfer = stages["host_to_device"]
    if (
        transfer.status != "unavailable"
        or transfer.reason != _INSEPARABLE_TRANSFER_REASON
    ):
        raise _timing_contract_error(
            "costly router execution has invalid transfer evidence"
        )


def _validate_stage_execution_stages(
    stages: Mapping[str, RouterTimingStage],
) -> None:
    setup = stages["setup_admission"]
    graph = stages["graph_construction"]
    compilation = stages["compilation"]
    if setup.status != "unavailable" or setup.reason != _SETUP_REASON:
        raise _timing_contract_error(
            "stage router execution has invalid setup evidence"
        )
    if graph.status != "unavailable" or graph.reason != _LAZY_GRAPH_REASON:
        raise _timing_contract_error(
            "stage router execution has invalid graph-construction evidence"
        )
    if (
        compilation.status != "unavailable"
        or compilation.reason != _COMPILATION_REASON
    ):
        raise _timing_contract_error(
            "stage router execution has invalid compilation evidence"
        )
    file_io = stages["file_io"]
    decode = stages["storage_validation_f32_decode"]
    file_cache_hit = (
        file_io.status == "unavailable" and file_io.reason == _CACHE_FILE_IO_REASON
    )
    decode_cache_hit = (
        decode.status == "unavailable" and decode.reason == _CACHE_DECODE_REASON
    )
    if (file_io.status == "observed") != (decode.status == "observed"):
        raise _timing_contract_error(
            "stage router file and decode evidence disagree"
        )
    if file_io.status != "observed" and not (file_cache_hit and decode_cache_hit):
        raise _timing_contract_error(
            "stage router execution has invalid cache evidence"
        )
    if any(
        stages[name].status != "observed"
        for name in (
            "host_to_device",
            "router_projection",
            "top_k",
            "normalization",
            "total_evaluated_router",
            "synchronized_readback",
            "end_to_end_router_command",
        )
    ):
        raise _timing_contract_error(
            "stage router execution lacks an observed evaluated boundary"
        )


def _validate_positive_nanoseconds(value: object, label: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 1 <= value <= _MAX_U64
    ):
        raise _timing_contract_error(f"{label} is not a positive u64")


def _validate_timing_text(value: object, label: str) -> None:
    normalized = " ".join(value.split()) if isinstance(value, str) else ""
    if (
        not isinstance(value, str)
        or not normalized
        or len(normalized) > _MAX_TIMING_REASON_CHARS
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
    ):
        raise _timing_contract_error(f"{label} is invalid")


def _sanitize_timing_text(value: object, label: str) -> str:
    _validate_timing_text(value, label)
    return RuntimeContractError("internal_worker_error", str(value)).message


def _validate_timing_stage_name(stage: object) -> None:
    if not isinstance(stage, str) or stage not in _TIMING_STAGES:
        raise _timing_contract_error("router timing stage name is invalid")


def _is_lowercase_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _freeze_timing_failure(
    failure: Mapping[str, str] | None,
) -> Mapping[str, str] | None:
    if failure is None:
        return None
    if not isinstance(failure, Mapping) or set(failure) != {
        "code",
        "message",
        "stage",
    }:
        raise _timing_contract_error("router timing failure evidence is invalid")
    code = failure.get("code")
    message = failure.get("message")
    stage = failure.get("stage")
    if not isinstance(code, str) or code not in STABLE_ERROR_CODES:
        raise _timing_contract_error("router timing failure code is invalid")
    if not is_stable_identifier(stage):
        raise _timing_contract_error("router timing failure stage is invalid")
    sanitized_message = _sanitize_timing_text(
        message,
        "router timing failure message",
    )
    return MappingProxyType(
        {"code": code, "message": sanitized_message, "stage": stage}
    )


@dataclass(frozen=True, slots=True)
class RouterResult:
    """One complete evaluated and synchronized bounded router result."""

    router_case_id: str
    operation: str
    requested_device: str
    selected_device: str
    fallback_used: bool
    evaluated: bool
    synchronized: bool
    batch_size: int
    hidden_width: int
    expert_count: int
    top_k: int
    output_dtype: str
    logits: tuple[tuple[float, ...], ...]
    full_probabilities: tuple[tuple[float, ...], ...]
    selected_expert_ids: tuple[tuple[int, ...], ...]
    selected_probabilities: tuple[tuple[float, ...], ...]
    normalized_weights: tuple[tuple[float, ...], ...]
    logits_f32le_sha256: str
    full_probabilities_f32le_sha256: str
    selected_probabilities_f32le_sha256: str
    normalized_weights_f32le_sha256: str
    router_tensor_bytes_read: int
    router_tensor_cache_status: str
    memory_gauges: MemoryGauges
    timing: RouterExecutionTiming

    def __post_init__(self) -> None:
        permitted_access = (
            {(0, _ROUTER_TENSOR_NOT_APPLICABLE)}
            if self.router_case_id in _SYNTHETIC_CASE_ROWS
            else {
                (0, _ROUTER_TENSOR_CACHE_HIT),
                (_ROUTER_TENSOR_BYTES, _ROUTER_TENSOR_READ_AND_CACHED),
            }
        )
        if (
            self.router_tensor_bytes_read,
            self.router_tensor_cache_status,
        ) not in permitted_access:
            raise _timing_contract_error(
                "router tensor application-read evidence is invalid"
            )
        if not isinstance(self.timing, RouterExecutionTiming):
            raise _timing_contract_error("router result timing envelope is invalid")
        if (
            self.evaluated != self.timing.evaluated
            or self.synchronized != self.timing.synchronized
        ):
            raise _timing_contract_error(
                "router result timing contradicts its execution envelope"
            )

    @property
    def passed(self) -> bool:
        """Report only the raw evaluated GPU execution-envelope status."""

        return (
            self.requested_device == GPU_DEVICE_ID
            and self.selected_device == GPU_DEVICE_ID
            and not self.fallback_used
            and self.evaluated
            and self.synchronized
        )

    def to_protocol_result(self) -> dict[str, object]:
        """Return the strict control-response schema consumed by Rust."""

        return {
            "router_case_id": self.router_case_id,
            "operation": self.operation,
            "requested_device": self.requested_device,
            "selected_device": self.selected_device,
            "fallback_used": self.fallback_used,
            "evaluated": self.evaluated,
            "synchronized": self.synchronized,
            "batch_size": self.batch_size,
            "hidden_width": self.hidden_width,
            "expert_count": self.expert_count,
            "top_k": self.top_k,
            "output_dtype": self.output_dtype,
            "logits": [list(row) for row in self.logits],
            "full_probabilities": [list(row) for row in self.full_probabilities],
            "selected_expert_ids": [list(row) for row in self.selected_expert_ids],
            "selected_probabilities": [
                list(row) for row in self.selected_probabilities
            ],
            "normalized_weights": [list(row) for row in self.normalized_weights],
            "logits_f32le_sha256": self.logits_f32le_sha256,
            "full_probabilities_f32le_sha256": (
                self.full_probabilities_f32le_sha256
            ),
            "selected_probabilities_f32le_sha256": (
                self.selected_probabilities_f32le_sha256
            ),
            "normalized_weights_f32le_sha256": (
                self.normalized_weights_f32le_sha256
            ),
            # This is the exact inherited positional-read byte count performed
            # by this application, not a claim about physical disk I/O.
            "router_tensor_bytes_read": self.router_tensor_bytes_read,
            "router_tensor_cache_status": self.router_tensor_cache_status,
            "memory_gauges": self.memory_gauges.to_protocol_result(),
            "timing": self.timing.to_protocol_result(),
            "passed": self.passed,
        }


@dataclass(frozen=True, slots=True)
class _CommittedRouterCase:
    router_case_id: str
    hidden_states: tuple[tuple[float, ...], ...]
    router_weights: tuple[tuple[float, ...], ...]


RouterCoreRunner = Callable[..., RouterResult]


def run_router(
    *,
    router_case_id: object,
    hidden_states: object,
    router_weights: object,
    requested_device: object,
    allow_fallback: object,
    case_scope: RouterCaseScope,
    mx_module: Any | None = None,
) -> RouterResult:
    """Validate and evaluate one complete in-memory router case on MLX GPU."""

    return _run_router_with_profile(
        router_case_id=router_case_id,
        hidden_states=hidden_states,
        router_weights=router_weights,
        requested_device=requested_device,
        allow_fallback=allow_fallback,
        case_scope=case_scope,
        timing_profile=_TIMING_PROFILE_MINIMAL,
        mx_module=mx_module,
    )


def _run_router_with_profile(
    *,
    router_case_id: object,
    hidden_states: object,
    router_weights: object,
    requested_device: object,
    allow_fallback: object,
    case_scope: RouterCaseScope,
    timing_profile: str,
    router_tensor_bytes_read: int = 0,
    router_tensor_cache_status: str = _ROUTER_TENSOR_NOT_APPLICABLE,
    mx_module: Any | None = None,
    timing_recorder: RouterTimingRecorder | None = None,
    end_to_end_started_ns: int | None = None,
    clock_ns: Callable[[], int] = time.perf_counter_ns,
) -> RouterResult:
    """Internal execution seam for exact minimal, costly, and stage profiles."""

    if not isinstance(case_scope, RouterCaseScope):
        raise RouterError(
            "internal_worker_error",
            "router execution requires an explicit internal case scope",
        )
    if timing_profile not in _TIMING_PROFILES:
        raise RouterError(
            "internal_worker_error",
            "router execution timing profile is invalid",
        )
    permitted_access = (
        {(0, _ROUTER_TENSOR_NOT_APPLICABLE)}
        if case_scope is RouterCaseScope.SYNTHETIC_FIXTURE
        else {
            (0, _ROUTER_TENSOR_CACHE_HIT),
            (_ROUTER_TENSOR_BYTES, _ROUTER_TENSOR_READ_AND_CACHED),
        }
    )
    if (router_tensor_bytes_read, router_tensor_cache_status) not in permitted_access:
        raise RouterError(
            "internal_worker_error",
            "router tensor application-read evidence contradicts the case scope",
        )
    if timing_profile == _TIMING_PROFILE_MINIMAL and (
        timing_recorder is not None or end_to_end_started_ns is not None
    ):
        raise RouterError(
            "internal_worker_error",
            "minimal router execution received external timing state",
        )
    if timing_profile != _TIMING_PROFILE_MINIMAL and (
        not isinstance(timing_recorder, RouterTimingRecorder)
        or isinstance(end_to_end_started_ns, bool)
        or not isinstance(end_to_end_started_ns, int)
        or not 0 <= end_to_end_started_ns <= _MAX_U64
        or not callable(clock_ns)
    ):
        raise RouterError(
            "internal_worker_error",
            "real router execution lacks its timing state",
        )
    _validate_control_scalars(
        router_case_id=router_case_id,
        requested_device=requested_device,
        allow_fallback=allow_fallback,
    )
    expected_rows = _expected_case_rows(router_case_id)
    if requested_device != GPU_DEVICE_ID or allow_fallback:
        raise RouterError(
            "device_unavailable",
            "router execution requires explicit GPU selection without fallback",
        )

    # All shape, type, cardinality, and finite-value checks finish before the
    # MLX module is imported, dereferenced, or used to construct an array.
    admitted_hidden = _validate_float32_matrix(
        hidden_states,
        expected_rows=expected_rows,
        expected_columns=HIDDEN_WIDTH,
        label="router hidden states",
    )
    admitted_weights = _validate_float32_matrix(
        router_weights,
        expected_rows=EXPERT_COUNT,
        expected_columns=HIDDEN_WIDTH,
        label="router weights",
    )

    mx = mx_module if mx_module is not None else _import_mlx()
    try:
        selected_device, fallback_used, gpu = _validate_explicit_gpu_selection(
            mx,
            requested_device=requested_device,
        )
        recorder = timing_recorder or RouterTimingRecorder()
        if timing_profile == _TIMING_PROFILE_MINIMAL:
            recorder.record_not_applicable(
                stage="dequantization",
                reason=_F32_DEQUANTIZATION_REASON,
            )

        with mx.stream(gpu):
            if timing_profile == _TIMING_PROFILE_STAGE:
                (
                    hidden_array,
                    weight_array,
                    transposed_weights,
                ) = recorder.measure_evaluated(
                    stage="host_to_device",
                    mx_module=mx,
                    gpu=gpu,
                    operation=lambda: _construct_router_arrays(
                        mx,
                        gpu,
                        admitted_hidden,
                        admitted_weights,
                    ),
                )
                recorder.record_unavailable(
                    stage="graph_construction",
                    reason=_LAZY_GRAPH_REASON,
                )
                recorder.record_unavailable(
                    stage="compilation",
                    reason=_COMPILATION_REASON,
                )
                (diagnostic_logits,) = recorder.measure_evaluated(
                    stage="router_projection",
                    mx_module=mx,
                    gpu=gpu,
                    operation=lambda: (
                        mx.matmul(
                            hidden_array,
                            transposed_weights,
                            stream=gpu,
                        ),
                    ),
                )
                (
                    diagnostic_probabilities,
                    diagnostic_ids,
                    diagnostic_selected,
                ) = recorder.measure_evaluated(
                    stage="top_k",
                    mx_module=mx,
                    gpu=gpu,
                    operation=lambda: _build_router_selection(
                        mx,
                        gpu,
                        diagnostic_logits,
                    ),
                )
                (diagnostic_normalized,) = recorder.measure_evaluated(
                    stage="normalization",
                    mx_module=mx,
                    gpu=gpu,
                    operation=lambda: (
                        _normalize_selected_probabilities(
                            mx,
                            gpu,
                            diagnostic_selected,
                        ),
                    ),
                )
                # Retain references until after all diagnostic barriers.  This
                # prevents an optimizer from treating a diagnostic stage as
                # dead work, while the final minimally synchronized graph
                # below remains the output used for correctness comparison.
                _ = (
                    weight_array,
                    diagnostic_probabilities,
                    diagnostic_ids,
                    diagnostic_normalized,
                )
            else:
                hidden_array, _, transposed_weights = _construct_router_arrays(
                    mx,
                    gpu,
                    admitted_hidden,
                    admitted_weights,
                )

            (
                logits_array,
                probability_array,
                selected_id_array,
                selected_probability_array,
                normalized_weight_array,
            ) = recorder.measure_evaluated(
                stage="total_evaluated_router",
                mx_module=mx,
                gpu=gpu,
                operation=lambda: _build_complete_router_outputs(
                    mx,
                    gpu,
                    hidden_array,
                    transposed_weights,
                ),
            )

        _require_array_metadata(
            mx,
            logits_array,
            (expected_rows, EXPERT_COUNT),
            require_float32=True,
        )
        _require_array_metadata(
            mx,
            probability_array,
            (expected_rows, EXPERT_COUNT),
            require_float32=True,
        )
        _require_array_metadata(
            mx,
            selected_id_array,
            (expected_rows, TOP_K),
            require_float32=False,
        )
        _require_array_metadata(
            mx,
            selected_probability_array,
            (expected_rows, TOP_K),
            require_float32=True,
        )
        _require_array_metadata(
            mx,
            normalized_weight_array,
            (expected_rows, TOP_K),
            require_float32=True,
        )

        def readback() -> tuple[tuple[tuple, ...], ...]:
            return (
                _float_matrix_readback(
                    logits_array.tolist(),
                    expected_rows=expected_rows,
                    expected_columns=EXPERT_COUNT,
                ),
                _float_matrix_readback(
                    probability_array.tolist(),
                    expected_rows=expected_rows,
                    expected_columns=EXPERT_COUNT,
                ),
                _integer_matrix_readback(
                    selected_id_array.tolist(),
                    expected_rows=expected_rows,
                    expected_columns=TOP_K,
                ),
                _float_matrix_readback(
                    selected_probability_array.tolist(),
                    expected_rows=expected_rows,
                    expected_columns=TOP_K,
                ),
                _float_matrix_readback(
                    normalized_weight_array.tolist(),
                    expected_rows=expected_rows,
                    expected_columns=TOP_K,
                ),
            )

        if timing_profile == _TIMING_PROFILE_STAGE:
            readback_result = recorder.measure_host(
                stage="synchronized_readback",
                operation=readback,
            )
        else:
            readback_result = readback()
        (
            logits,
            full_probabilities,
            selected_expert_ids,
            selected_probabilities,
            normalized_weights,
        ) = readback_result

        if timing_profile != _TIMING_PROFILE_MINIMAL:
            completed_ns = _read_external_clock(clock_ns)
            if end_to_end_started_ns is None:
                raise RouterError(
                    "internal_worker_error",
                    "real router execution lost its timing boundary",
                )
            recorder.record_observed(
                stage="end_to_end_router_command",
                duration_ns=completed_ns - end_to_end_started_ns,
            )
        timing = recorder.execution_timing(
            instrumentation_mode=(
                "stage_instrumented"
                if timing_profile == _TIMING_PROFILE_STAGE
                else "minimally_instrumented"
            )
        )
        evaluated = timing.evaluated
        synchronized = timing.synchronized
        memory_gauges = collect_memory_gauges(mx)
    except RouterError:
        raise
    except RuntimeContractError as error:
        raise RouterError(error.code, error.message) from error
    except Exception as error:
        raise RouterError(
            "evaluation_failed",
            "the complete MLX router operation did not complete",
        ) from error

    _validate_complete_result(
        logits,
        full_probabilities,
        selected_expert_ids,
        selected_probabilities,
        normalized_weights,
        case_scope=case_scope,
    )
    return RouterResult(
        router_case_id=router_case_id,
        operation=ROUTER_OPERATION_ID,
        requested_device=requested_device,
        selected_device=selected_device,
        fallback_used=fallback_used,
        evaluated=evaluated,
        synchronized=synchronized,
        batch_size=expected_rows,
        hidden_width=HIDDEN_WIDTH,
        expert_count=EXPERT_COUNT,
        top_k=TOP_K,
        output_dtype=OUTPUT_DTYPE,
        logits=logits,
        full_probabilities=full_probabilities,
        selected_expert_ids=selected_expert_ids,
        selected_probabilities=selected_probabilities,
        normalized_weights=normalized_weights,
        logits_f32le_sha256=_canonical_f32le_sha256(logits),
        full_probabilities_f32le_sha256=_canonical_f32le_sha256(
            full_probabilities
        ),
        selected_probabilities_f32le_sha256=_canonical_f32le_sha256(
            selected_probabilities
        ),
        normalized_weights_f32le_sha256=_canonical_f32le_sha256(
            normalized_weights
        ),
        router_tensor_bytes_read=router_tensor_bytes_read,
        router_tensor_cache_status=router_tensor_cache_status,
        memory_gauges=memory_gauges,
        timing=timing,
    )


def _construct_router_arrays(
    mx: Any,
    gpu: Any,
    hidden_states: tuple[tuple[float, ...], ...],
    router_weights: tuple[tuple[float, ...], ...],
) -> tuple[object, object, object]:
    hidden_array = mx.array(hidden_states, dtype=mx.float32)
    weight_array = mx.array(router_weights, dtype=mx.float32)
    transposed_weights = mx.transpose(weight_array, (1, 0), stream=gpu)
    return hidden_array, weight_array, transposed_weights


def _build_router_selection(
    mx: Any,
    gpu: Any,
    logits_array: object,
) -> tuple[object, object, object]:
    probability_array = mx.softmax(logits_array, axis=1, stream=gpu)
    # Assign each expert its exact lexicographic rank under probability
    # descending, then expert ID ascending.  The ranks are unique even for
    # ties, so argsort need not rely on implementation-specific stability.
    expert_ids = mx.arange(EXPERT_COUNT, dtype=mx.uint32, stream=gpu)
    candidate_probabilities = probability_array[:, :, None]
    competing_probabilities = probability_array[:, None, :]
    strictly_better = competing_probabilities > candidate_probabilities
    equal_with_lower_id = (
        competing_probabilities == candidate_probabilities
    ) & (expert_ids[None, None, :] < expert_ids[None, :, None])
    lexicographic_rank = mx.sum(
        strictly_better | equal_with_lower_id,
        axis=2,
        stream=gpu,
    )
    order_array = mx.argsort(lexicographic_rank, axis=1, stream=gpu)
    selected_id_array = order_array[:, :TOP_K]
    selected_probability_array = mx.take_along_axis(
        probability_array,
        selected_id_array,
        axis=1,
        stream=gpu,
    )
    return probability_array, selected_id_array, selected_probability_array


def _normalize_selected_probabilities(
    mx: Any,
    gpu: Any,
    selected_probability_array: object,
) -> object:
    selected_sum_array = mx.sum(
        selected_probability_array,
        axis=1,
        keepdims=True,
        stream=gpu,
    )
    return selected_probability_array / selected_sum_array


def _build_complete_router_outputs(
    mx: Any,
    gpu: Any,
    hidden_array: object,
    transposed_weights: object,
) -> tuple[object, ...]:
    logits_array = mx.matmul(hidden_array, transposed_weights, stream=gpu)
    (
        probability_array,
        selected_id_array,
        selected_probability_array,
    ) = _build_router_selection(mx, gpu, logits_array)
    normalized_weight_array = _normalize_selected_probabilities(
        mx,
        gpu,
        selected_probability_array,
    )
    return (
        logits_array,
        probability_array,
        selected_id_array,
        selected_probability_array,
        normalized_weight_array,
    )


def _read_external_clock(clock_ns: Callable[[], int]) -> int:
    try:
        value = clock_ns()
    except Exception as error:
        raise RouterError(
            "internal_worker_error",
            "router timing clock could not be read",
        ) from error
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= _MAX_U64:
        raise RouterError(
            "internal_worker_error",
            "router timing clock returned invalid nanoseconds",
        )
    return value


def _validate_explicit_gpu_selection(
    mx: Any,
    *,
    requested_device: str,
) -> tuple[str, bool, Any]:
    """Resolve and validate the exact MLX GPU target without fallback."""

    try:
        gpu = mx.gpu
        selected_device = gpu.name
        metal_available = bool(mx.metal.is_available())
        descriptor = sanitize_gpu_descriptor(mx.device_info(gpu))
    except RuntimeContractError as error:
        raise RouterError(error.code, error.message) from error
    except Exception as error:
        raise RouterError(
            "device_unavailable",
            "MLX could not validate the explicitly selected GPU",
        ) from error

    if (
        selected_device != GPU_DEVICE_ID
        or descriptor.device_id != selected_device
        or not metal_available
    ):
        raise RouterError(
            "device_unavailable",
            "MLX could not validate the explicitly selected GPU",
        )

    fallback_used = selected_device != requested_device
    if fallback_used:
        raise RouterError(
            "device_unavailable",
            "router execution cannot fall back from the requested GPU",
        )
    return selected_device, fallback_used, gpu


def run_committed_router(
    *,
    router_case_id: object,
    requested_device: object,
    allow_fallback: object,
    router_runner: RouterCoreRunner | None = None,
    model_fd: int = _MODEL_FILE_FD,
    fstat_func: Callable[[int], Any] = os.fstat,
    pread_func: Callable[[int, int, int], bytes] = os.pread,
    getfl_func: Callable[[int, int], int] = fcntl.fcntl,
    clock_ns: Callable[[], int] = time.perf_counter_ns,
    environ: Mapping[str, str] | None = None,
) -> RouterResult:
    """Resolve one committed case and execute no caller-supplied tensor data."""

    _validate_control_scalars(
        router_case_id=router_case_id,
        requested_device=requested_device,
        allow_fallback=allow_fallback,
    )
    expected_rows = _expected_case_rows(router_case_id)
    if requested_device != GPU_DEVICE_ID or allow_fallback:
        raise RouterError(
            "device_unavailable",
            "router execution requires explicit GPU selection without fallback",
        )
    if router_case_id in {REAL_SINGLE_ROW_CASE_ID, REAL_BATCH_CASE_ID}:
        return _run_inherited_real_router(
            router_case_id=router_case_id,
            expected_rows=expected_rows,
            model_fd=model_fd,
            fstat_func=fstat_func,
            pread_func=pread_func,
            getfl_func=getfl_func,
            clock_ns=clock_ns,
            environ=os.environ if environ is None else environ,
            router_runner=router_runner,
        )
    committed = _load_committed_router_case(router_case_id, expected_rows)
    runner = run_router if router_runner is None else router_runner
    return runner(
        router_case_id=committed.router_case_id,
        hidden_states=committed.hidden_states,
        router_weights=committed.router_weights,
        requested_device=GPU_DEVICE_ID,
        allow_fallback=False,
        case_scope=RouterCaseScope.SYNTHETIC_FIXTURE,
    )


def _run_inherited_real_router(
    *,
    router_case_id: str,
    expected_rows: int,
    model_fd: int,
    fstat_func: Callable[[int], Any],
    pread_func: Callable[[int, int, int], bytes],
    getfl_func: Callable[[int, int], int],
    clock_ns: Callable[[], int],
    environ: Mapping[str, str],
    router_runner: RouterCoreRunner | None,
) -> RouterResult:
    """Load the exact inherited F32 range and committed real hidden input."""

    if isinstance(model_fd, bool) or not isinstance(model_fd, int) or model_fd < 0:
        raise RouterError(
            "internal_worker_error",
            "the inherited router model descriptor is invalid",
        )
    if not all(callable(value) for value in (fstat_func, pread_func, getfl_func, clock_ns)):
        raise RouterError(
            "internal_worker_error",
            "the inherited router I/O adapter is invalid",
        )
    if not isinstance(environ, Mapping):
        raise RouterError(
            "internal_worker_error",
            "the router timing environment is invalid",
        )

    timing_profile = _timing_profile_from_environment(environ)
    end_to_end_started_ns = (
        None
        if timing_profile == _TIMING_PROFILE_MINIMAL
        else _read_external_clock(clock_ns)
    )
    recorder = (
        None
        if timing_profile == _TIMING_PROFILE_MINIMAL
        else RouterTimingRecorder(clock_ns=clock_ns)
    )
    if timing_profile == _TIMING_PROFILE_STAGE:
        if recorder is None:
            raise RouterError(
                "internal_worker_error",
                "stage router execution lacks its timing recorder",
            )
        recorder.record_unavailable(
            stage="setup_admission",
            reason=_SETUP_REASON,
        )

    (
        snapshot,
        router_weights,
        router_tensor_bytes_read,
        router_tensor_cache_status,
    ) = _resolve_real_router_weights(
        model_fd=model_fd,
        force_read=timing_profile == _TIMING_PROFILE_COSTLY,
        timing_profile=timing_profile,
        recorder=recorder,
        fstat_func=fstat_func,
        pread_func=pread_func,
        getfl_func=getfl_func,
    )
    hidden_states = _load_real_hidden_case(router_case_id, expected_rows)

    if recorder is not None:
        recorder.record_not_applicable(
            stage="dequantization",
            reason=_F32_DEQUANTIZATION_REASON,
        )
        if timing_profile == _TIMING_PROFILE_COSTLY:
            recorder.record_unavailable(
                stage="host_to_device",
                reason=_INSEPARABLE_TRANSFER_REASON,
            )

    runner = _run_router_with_profile if router_runner is None else router_runner
    result = runner(
        router_case_id=router_case_id,
        hidden_states=hidden_states,
        router_weights=router_weights,
        requested_device=GPU_DEVICE_ID,
        allow_fallback=False,
        case_scope=RouterCaseScope.REAL_CHECKPOINT,
        timing_profile=timing_profile,
        router_tensor_bytes_read=router_tensor_bytes_read,
        router_tensor_cache_status=router_tensor_cache_status,
        timing_recorder=recorder,
        end_to_end_started_ns=end_to_end_started_ns,
        clock_ns=clock_ns,
    )
    after_execution = _snapshot_model_file(
        model_fd,
        fstat_func=fstat_func,
        getfl_func=getfl_func,
    )
    if after_execution != snapshot:
        raise RouterError(
            "invalid_byte_count",
            "the inherited model file changed during router execution",
        )
    return result


def _timing_profile_from_environment(environ: Mapping[str, str]) -> str:
    value = environ.get(_TIMING_PROFILE_ENV, _TIMING_PROFILE_MINIMAL)
    if not isinstance(value, str) or value not in _TIMING_PROFILES:
        raise RouterError(
            "malformed_request",
            "the router timing profile is not one of the committed modes",
        )
    return value


def _resolve_real_router_weights(
    *,
    model_fd: int,
    force_read: bool,
    timing_profile: str,
    recorder: RouterTimingRecorder | None,
    fstat_func: Callable[[int], Any],
    pread_func: Callable[[int, int, int], bytes],
    getfl_func: Callable[[int, int], int],
) -> tuple[
    _ModelFileSnapshot,
    tuple[tuple[float, ...], ...],
    int,
    str,
]:
    """Return an identity-bound cache hit or one exact positional read."""

    global _REAL_ROUTER_CACHE
    snapshot = _snapshot_model_file(
        model_fd,
        fstat_func=fstat_func,
        getfl_func=getfl_func,
    )
    with _REAL_ROUTER_CACHE_LOCK:
        cached = _REAL_ROUTER_CACHE
        if not force_read and cached is not None and cached.snapshot == snapshot:
            if timing_profile == _TIMING_PROFILE_STAGE:
                if recorder is None:
                    raise RouterError(
                        "internal_worker_error",
                        "stage router cache evidence lacks its timing recorder",
                    )
                recorder.record_unavailable(
                    stage="file_io",
                    reason=_CACHE_FILE_IO_REASON,
                )
                recorder.record_unavailable(
                    stage="storage_validation_f32_decode",
                    reason=_CACHE_DECODE_REASON,
                )
            return snapshot, cached.weights, 0, _ROUTER_TENSOR_CACHE_HIT

        if recorder is None:
            payload = _pread_exact_router_tensor(model_fd, pread_func)
        else:
            payload_value = recorder.measure_host(
                stage="file_io",
                operation=lambda: _pread_exact_router_tensor(model_fd, pread_func),
            )
            if not isinstance(payload_value, bytes):
                raise RouterError(
                    "internal_worker_error",
                    "the timed router tensor read returned invalid data",
                )
            payload = payload_value
        after_read = _snapshot_model_file(
            model_fd,
            fstat_func=fstat_func,
            getfl_func=getfl_func,
        )
        if after_read != snapshot:
            raise RouterError(
                "invalid_byte_count",
                "the inherited model file changed while its router tensor was read",
            )

        if recorder is None:
            weights = _decode_real_router_tensor(payload)
        else:
            weights_value = recorder.measure_host(
                stage="storage_validation_f32_decode",
                operation=lambda: _decode_real_router_tensor(payload),
            )
            if not isinstance(weights_value, tuple):
                raise RouterError(
                    "internal_worker_error",
                    "the timed router tensor decode returned invalid data",
                )
            weights = weights_value

        _REAL_ROUTER_CACHE = _CachedRouterTensor(snapshot=snapshot, weights=weights)
        return (
            snapshot,
            weights,
            _ROUTER_TENSOR_BYTES,
            _ROUTER_TENSOR_READ_AND_CACHED,
        )


def _snapshot_model_file(
    model_fd: int,
    *,
    fstat_func: Callable[[int], Any],
    getfl_func: Callable[[int, int], int],
) -> _ModelFileSnapshot:
    try:
        observed = fstat_func(model_fd)
        flags = getfl_func(model_fd, fcntl.F_GETFL)
    except (OSError, TypeError, ValueError) as error:
        raise RouterError(
            "internal_worker_error",
            "the inherited router model descriptor could not be inspected",
        ) from error
    fields = (
        getattr(observed, "st_dev", None),
        getattr(observed, "st_ino", None),
        getattr(observed, "st_mode", None),
        getattr(observed, "st_size", None),
        getattr(observed, "st_mtime_ns", None),
        getattr(observed, "st_ctime_ns", None),
    )
    if any(isinstance(value, bool) or not isinstance(value, int) for value in fields):
        raise RouterError(
            "internal_worker_error",
            "the inherited router model descriptor returned invalid metadata",
        )
    if isinstance(flags, bool) or not isinstance(flags, int):
        raise RouterError(
            "internal_worker_error",
            "the inherited router model descriptor returned invalid flags",
        )
    device, inode, mode, size, modified_ns, changed_ns = fields
    if not stat.S_ISREG(mode):
        raise RouterError(
            "invalid_byte_count",
            "the inherited router model descriptor is not a regular file",
        )
    if size != _MODEL_FILE_BYTES:
        raise RouterError(
            "invalid_byte_count",
            "the inherited router model file byte size does not match admission",
        )
    if flags & os.O_ACCMODE != os.O_RDONLY:
        raise RouterError(
            "invalid_byte_count",
            "the inherited router model descriptor is not read only",
        )
    if (
        _ROUTER_TENSOR_OFFSET < 0
        or _ROUTER_TENSOR_BYTES != _WEIGHT_BYTES
        or _ROUTER_TENSOR_END != _ROUTER_TENSOR_OFFSET + _ROUTER_TENSOR_BYTES
        or _ROUTER_TENSOR_END > size
    ):
        raise RouterError(
            "invalid_byte_count",
            "the frozen router tensor range is outside the inherited model file",
        )
    return _ModelFileSnapshot(
        device=device,
        inode=inode,
        mode=mode,
        size=size,
        modified_ns=modified_ns,
        changed_ns=changed_ns,
    )


def _pread_exact_router_tensor(
    model_fd: int,
    pread_func: Callable[[int, int, int], bytes],
) -> bytes:
    payload = bytearray(_ROUTER_TENSOR_BYTES)
    actual = 0
    interrupted_retries = 0
    while actual < _ROUTER_TENSOR_BYTES:
        remaining = _ROUTER_TENSOR_BYTES - actual
        try:
            chunk = pread_func(
                model_fd,
                remaining,
                _ROUTER_TENSOR_OFFSET + actual,
            )
        except InterruptedError:
            interrupted_retries += 1
            if interrupted_retries > 64:
                raise RouterError(
                    "resource_limit",
                    "the inherited router tensor read exceeded its retry bound",
                )
            continue
        except OSError as error:
            if error.errno == errno.EINTR:
                interrupted_retries += 1
                if interrupted_retries <= 64:
                    continue
            raise RouterError(
                "internal_worker_error",
                "the inherited router tensor could not be read",
            ) from error
        if not isinstance(chunk, bytes):
            raise RouterError(
                "internal_worker_error",
                "the inherited positional router reader returned invalid data",
            )
        if not chunk:
            raise RouterError(
                "invalid_byte_count",
                "the inherited router tensor ended before its exact byte count",
            )
        if len(chunk) > remaining:
            raise RouterError(
                "invalid_byte_count",
                "the inherited positional router reader exceeded its range",
            )
        payload[actual : actual + len(chunk)] = chunk
        actual += len(chunk)
    return bytes(payload)


def _decode_real_router_tensor(
    payload: bytes,
) -> tuple[tuple[float, ...], ...]:
    if not isinstance(payload, bytes) or len(payload) != _ROUTER_TENSOR_BYTES:
        raise RouterError(
            "invalid_byte_count",
            "the inherited router tensor has an invalid byte count",
        )
    if hashlib.sha256(payload).hexdigest() != _ROUTER_TENSOR_SHA256:
        raise RouterError(
            "invalid_byte_count",
            "the inherited router tensor differs from its frozen hash",
        )
    try:
        flat = tuple(value[0] for value in struct.iter_unpack("<f", payload))
    except struct.error as error:
        raise RouterError(
            "invalid_dtype",
            "the inherited router tensor is not exact little-endian F32",
        ) from error
    if len(flat) != _WEIGHT_ELEMENT_COUNT:
        raise RouterError(
            "invalid_shape",
            "the decoded router tensor has an invalid element count",
        )
    if any(not math.isfinite(value) for value in flat):
        raise RouterError(
            "invalid_dtype",
            "the decoded router tensor contains a non-finite F32 value",
        )
    return tuple(
        flat[start : start + HIDDEN_WIDTH]
        for start in range(0, len(flat), HIDDEN_WIDTH)
    )


def _load_real_hidden_case(
    router_case_id: str,
    expected_rows: int,
    *,
    fixture_path: Path = _REAL_FIXTURE_PATH,
    open_func: Callable[[str, int], int] = os.open,
    fstat_func: Callable[[int], Any] = os.fstat,
    pread_func: Callable[[int, int, int], bytes] = os.pread,
    close_func: Callable[[int], None] = os.close,
) -> tuple[tuple[float, ...], ...]:
    """Read only the committed input-object byte range, never oracle output."""

    if router_case_id not in {REAL_SINGLE_ROW_CASE_ID, REAL_BATCH_CASE_ID}:
        raise RouterError(
            "unsupported_operation",
            "the real router hidden-state case identity is invalid",
        )
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = open_func(os.fspath(fixture_path), flags)
    except (OSError, TypeError, ValueError) as error:
        raise RouterError(
            "internal_worker_error",
            "the committed real router input could not be opened",
        ) from error
    try:
        try:
            observed = fstat_func(descriptor)
        except (OSError, TypeError, ValueError) as error:
            raise RouterError(
                "internal_worker_error",
                "the committed real router input could not be inspected",
            ) from error
        mode = getattr(observed, "st_mode", None)
        size = getattr(observed, "st_size", None)
        if (
            isinstance(mode, bool)
            or not isinstance(mode, int)
            or isinstance(size, bool)
            or not isinstance(size, int)
            or not stat.S_ISREG(mode)
            or size != _REAL_FIXTURE_BYTES
            or _REAL_INPUT_FRAGMENT_END
            != _REAL_INPUT_FRAGMENT_OFFSET + _REAL_INPUT_FRAGMENT_BYTES
            or _REAL_INPUT_FRAGMENT_END >= size
        ):
            raise RouterError(
                "invalid_byte_count",
                "the committed real router input container is invalid",
            )
        payload = _pread_exact_range(
            descriptor,
            offset=_REAL_INPUT_FRAGMENT_OFFSET,
            length=_REAL_INPUT_FRAGMENT_BYTES,
            pread_func=pread_func,
            label="committed real router input",
        )
    finally:
        try:
            close_func(descriptor)
        except OSError:
            pass
    if hashlib.sha256(payload).hexdigest() != _REAL_INPUT_FRAGMENT_SHA256:
        raise RouterError(
            "invalid_byte_count",
            "the committed real router input fragment differs from its hash",
        )
    if b'"result"' in payload or b'"oracle"' in payload:
        raise RouterError(
            "internal_worker_error",
            "the committed router input projection crossed its data boundary",
        )
    try:
        document = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_object_without_duplicates,
            parse_constant=_reject_nonfinite,
        )
    except (UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError) as error:
        raise RouterError(
            "invalid_dtype",
            "the committed real router input fragment is invalid JSON",
        ) from error
    if not isinstance(document, Mapping) or set(document) != {
        "byte_order",
        "canonical_f32le_sha256",
        "case_ids",
        "dtype",
        "row_sha256",
        "shape",
        "values",
    }:
        raise RouterError(
            "invalid_shape",
            "the committed real router input contract is invalid",
        )
    if (
        document.get("byte_order") != "little"
        or document.get("canonical_f32le_sha256") != _REAL_INPUT_SHA256
        or document.get("case_ids")
        != [REAL_SINGLE_ROW_CASE_ID, REAL_BATCH_CASE_ID]
        or document.get("dtype") != "float32"
        or document.get("row_sha256") != list(_REAL_INPUT_ROW_SHA256)
        or document.get("shape") != [MAXIMUM_ROWS, HIDDEN_WIDTH]
    ):
        raise RouterError(
            "invalid_shape",
            "the committed real router input identity is invalid",
        )
    rows = _validate_float32_matrix(
        document.get("values"),
        expected_rows=MAXIMUM_ROWS,
        expected_columns=HIDDEN_WIDTH,
        label="committed real router hidden states",
    )
    for row, expected_sha256 in zip(rows, _REAL_INPUT_ROW_SHA256):
        if _canonical_f32le_sha256((row,)) != expected_sha256:
            raise RouterError(
                "invalid_byte_count",
                "a committed real router input row differs from its hash",
            )
    if _canonical_f32le_sha256(rows) != _REAL_INPUT_SHA256 or rows[0] == rows[1]:
        raise RouterError(
            "invalid_byte_count",
            "the committed real router input tensor differs from its contract",
        )
    selected = rows[:expected_rows]
    if len(selected) != expected_rows:
        raise RouterError(
            "invalid_shape",
            "the committed real router row selection is invalid",
        )
    return selected


def _pread_exact_range(
    descriptor: int,
    *,
    offset: int,
    length: int,
    pread_func: Callable[[int, int, int], bytes],
    label: str,
) -> bytes:
    payload = bytearray(length)
    actual = 0
    retries = 0
    while actual < length:
        remaining = length - actual
        try:
            chunk = pread_func(descriptor, remaining, offset + actual)
        except InterruptedError:
            retries += 1
            if retries > 64:
                raise RouterError(
                    "resource_limit",
                    f"the {label} read exceeded its retry bound",
                )
            continue
        except OSError as error:
            if error.errno == errno.EINTR:
                retries += 1
                if retries <= 64:
                    continue
            raise RouterError(
                "internal_worker_error",
                f"the {label} could not be read",
            ) from error
        if not isinstance(chunk, bytes):
            raise RouterError(
                "internal_worker_error",
                f"the {label} reader returned invalid data",
            )
        if not chunk:
            raise RouterError(
                "invalid_byte_count",
                f"the {label} ended before its exact byte count",
            )
        if len(chunk) > remaining:
            raise RouterError(
                "invalid_byte_count",
                f"the {label} reader exceeded its range",
            )
        payload[actual : actual + len(chunk)] = chunk
        actual += len(chunk)
    return bytes(payload)


def _validate_control_scalars(
    *,
    router_case_id: object,
    requested_device: object,
    allow_fallback: object,
) -> None:
    if (
        not is_stable_identifier(router_case_id)
        or not is_stable_identifier(requested_device)
        or not isinstance(allow_fallback, bool)
    ):
        raise RouterError(
            "malformed_request",
            "router control fields must be bounded scalar values",
        )


def _expected_case_rows(router_case_id: object) -> int:
    expected_rows = _CASE_ROWS.get(router_case_id)
    if expected_rows is None:
        raise RouterError(
            "unsupported_operation",
            "router case identity is not a committed bounded case",
        )
    return expected_rows


def _validate_float32_matrix(
    value: object,
    *,
    expected_rows: int,
    expected_columns: int,
    label: str,
) -> tuple[tuple[float, ...], ...]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray, memoryview))
        or len(value) != expected_rows
    ):
        raise RouterError(
            "invalid_shape",
            f"{label} has an invalid row count",
        )
    result: list[tuple[float, ...]] = []
    for row in value:
        if (
            not isinstance(row, Sequence)
            or isinstance(row, (str, bytes, bytearray, memoryview))
            or len(row) != expected_columns
        ):
            raise RouterError(
                "invalid_shape",
                f"{label} has an invalid column count",
            )
        converted: list[float] = []
        for element in row:
            if isinstance(element, bool) or not isinstance(element, (int, float)):
                raise RouterError(
                    "invalid_dtype",
                    f"{label} contains a nonnumeric value",
                )
            try:
                number = float(element)
                canonical = struct.unpack("<f", struct.pack("<f", number))[0]
            except (OverflowError, struct.error, ValueError) as error:
                raise RouterError(
                    "invalid_dtype",
                    f"{label} contains a value outside float32 range",
                ) from error
            if not math.isfinite(number) or not math.isfinite(canonical):
                raise RouterError(
                    "invalid_dtype",
                    f"{label} contains a non-finite value",
                )
            converted.append(canonical)
        result.append(tuple(converted))
    return tuple(result)


def _import_mlx() -> Any:
    try:
        import mlx.core as mx
    except Exception as error:
        raise RouterError(
            "device_unavailable",
            "the pinned MLX runtime could not be imported for router execution",
        ) from error
    return mx


def _require_array_metadata(
    mx: Any,
    array: Any,
    expected_shape: tuple[int, int],
    *,
    require_float32: bool,
) -> None:
    try:
        shape = tuple(array.shape)
        dtype = array.dtype
    except Exception as error:
        raise RouterError(
            "evaluation_failed",
            "an evaluated router array lacks bounded metadata",
        ) from error
    if shape != expected_shape:
        raise RouterError(
            "invalid_shape",
            "an evaluated router array has an invalid shape",
        )
    if require_float32 and dtype != mx.float32:
        raise RouterError(
            "invalid_dtype",
            "an evaluated router array is not float32",
        )


def _float_matrix_readback(
    value: object,
    *,
    expected_rows: int,
    expected_columns: int,
) -> tuple[tuple[float, ...], ...]:
    if not isinstance(value, (list, tuple)) or len(value) != expected_rows:
        raise RouterError(
            "invalid_shape",
            "router float readback has an invalid row count",
        )
    result: list[tuple[float, ...]] = []
    for row in value:
        if not isinstance(row, (list, tuple)) or len(row) != expected_columns:
            raise RouterError(
                "invalid_shape",
                "router float readback has an invalid column count",
            )
        converted: list[float] = []
        for element in row:
            if isinstance(element, bool) or not isinstance(element, (int, float)):
                raise RouterError(
                    "evaluation_failed",
                    "router float readback contains a nonnumeric value",
                )
            number = float(element)
            if not math.isfinite(number):
                raise RouterError(
                    "evaluation_failed",
                    "router float readback contains a non-finite value",
                )
            converted.append(number)
        result.append(tuple(converted))
    return tuple(result)


def _integer_matrix_readback(
    value: object,
    *,
    expected_rows: int,
    expected_columns: int,
) -> tuple[tuple[int, ...], ...]:
    if not isinstance(value, (list, tuple)) or len(value) != expected_rows:
        raise RouterError(
            "invalid_shape",
            "router ID readback has an invalid row count",
        )
    result: list[tuple[int, ...]] = []
    for row in value:
        if not isinstance(row, (list, tuple)) or len(row) != expected_columns:
            raise RouterError(
                "invalid_shape",
                "router ID readback has an invalid column count",
            )
        converted: list[int] = []
        for element in row:
            if isinstance(element, bool) or not isinstance(element, int):
                raise RouterError(
                    "evaluation_failed",
                    "router ID readback contains a non-integer value",
                )
            converted.append(element)
        result.append(tuple(converted))
    return tuple(result)


def _validate_complete_result(
    logits: tuple[tuple[float, ...], ...],
    probabilities: tuple[tuple[float, ...], ...],
    selected_ids: tuple[tuple[int, ...], ...],
    selected_probabilities: tuple[tuple[float, ...], ...],
    normalized_weights: tuple[tuple[float, ...], ...],
    *,
    case_scope: RouterCaseScope,
) -> None:
    if not isinstance(case_scope, RouterCaseScope):
        raise RouterError(
            "internal_worker_error",
            "router result validation requires an explicit internal case scope",
        )
    for row_index, probability_row in enumerate(probabilities):
        logit_row = logits[row_index]
        selected_id_row = selected_ids[row_index]
        selected_row = selected_probabilities[row_index]
        normalized_row = normalized_weights[row_index]
        if any(value < 0.0 for value in probability_row):
            raise RouterError(
                "evaluation_failed",
                "complete router probabilities contain a negative value",
            )
        if abs(sum(probability_row) - 1.0) > _PROBABILITY_SUM_TOLERANCE:
            raise RouterError(
                "evaluation_failed",
                "complete router probabilities do not sum to one",
            )
        maximum = max(logit_row)
        exponentials = tuple(math.exp(value - maximum) for value in logit_row)
        denominator = sum(exponentials)
        if not math.isfinite(denominator) or denominator <= 0.0:
            raise RouterError(
                "evaluation_failed",
                "complete router logits do not define a finite softmax",
            )
        for candidate, exponential in zip(probability_row, exponentials):
            expected = exponential / denominator
            admitted_error = _PROBABILITY_SUM_TOLERANCE + (
                _PROBABILITY_RELATIVE_TOLERANCE * abs(expected)
            )
            if abs(candidate - expected) > admitted_error:
                raise RouterError(
                    "evaluation_failed",
                    "complete router probabilities are not the full softmax of logits",
                )
        ranked_ids = tuple(
            sorted(
                range(EXPERT_COUNT),
                key=lambda expert_id: (
                    -probability_row[expert_id],
                    expert_id,
                ),
            )
        )
        if (
            case_scope is RouterCaseScope.REAL_CHECKPOINT
            and probability_row[ranked_ids[TOP_K - 1]]
            == probability_row[ranked_ids[TOP_K]]
        ):
            raise RouterError(
                "comparison_failed",
                "an exact float32 probability tie crosses real router ranks eight and nine",
            )
        expected_ids = ranked_ids[:TOP_K]
        if selected_id_row != expected_ids or len(set(selected_id_row)) != TOP_K:
            raise RouterError(
                "evaluation_failed",
                "router expert IDs do not follow the deterministic top-k rule",
            )
        selected_sum = sum(selected_row)
        if not math.isfinite(selected_sum) or selected_sum <= 0.0:
            raise RouterError(
                "evaluation_failed",
                "selected router probabilities have an invalid denominator",
            )
        if abs(sum(normalized_row) - 1.0) > _PROBABILITY_SUM_TOLERANCE:
            raise RouterError(
                "evaluation_failed",
                "normalized router weights do not sum to one",
            )
        for rank, expert_id in enumerate(selected_id_row):
            if not 0 <= expert_id < EXPERT_COUNT:
                raise RouterError(
                    "evaluation_failed",
                    "router result contains an out-of-range expert ID",
                )
            if _f32_bits(selected_row[rank]) != _f32_bits(
                probability_row[expert_id]
            ):
                raise RouterError(
                    "evaluation_failed",
                    "selected probability differs from complete softmax output",
                )
            expected_weight = selected_row[rank] / selected_sum
            if abs(normalized_row[rank] - expected_weight) > _PROBABILITY_SUM_TOLERANCE:
                raise RouterError(
                    "evaluation_failed",
                    "router weight differs from selected-probability normalization",
                )


def _canonical_f32le_sha256(rows: Sequence[Sequence[float]]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        for value in row:
            try:
                digest.update(struct.pack("<f", value))
            except (OverflowError, struct.error) as error:
                raise RouterError(
                    "internal_worker_error",
                    "router result could not be canonically hashed",
                ) from error
    return digest.hexdigest()


def _canonical_f32le_bytes(rows: Sequence[Sequence[float]]) -> bytes:
    output = bytearray()
    for row in rows:
        for value in row:
            output.extend(struct.pack("<f", value))
    return bytes(output)


def _f32_bits(value: float) -> bytes:
    return struct.pack("<f", value)


def _load_committed_router_case(
    router_case_id: object,
    expected_rows: int,
) -> _CommittedRouterCase:
    manifest, _ = _read_strict_json(
        _MANIFEST_PATH,
        maximum_bytes=_MAX_MANIFEST_BYTES,
        label="router fixture manifest",
    )
    _validate_manifest(manifest)

    hidden_document, hidden_payload = _read_strict_json(
        _HIDDEN_PATH,
        maximum_bytes=_MAX_HIDDEN_DOCUMENT_BYTES,
        label="router hidden-state fixture",
    )
    recipe, recipe_payload = _read_strict_json(
        _WEIGHT_RECIPE_PATH,
        maximum_bytes=_MAX_RECIPE_BYTES,
        label="router weight recipe",
    )
    _validate_manifest_file(
        manifest,
        relative_path="golden/hidden_states.json",
        payload=hidden_payload,
    )
    _validate_manifest_file(
        manifest,
        relative_path="golden/weight_recipe.json",
        payload=recipe_payload,
    )

    hidden_rows = _validate_hidden_document(hidden_document)
    router_weights = _build_weights_from_recipe(recipe)
    selected_hidden = hidden_rows[:expected_rows]
    case = _manifest_case(manifest, router_case_id)
    if (
        case.get("expected_result_key") != router_case_id
        or case.get("hidden_shape") != [expected_rows, HIDDEN_WIDTH]
        or case.get("hidden_row_ids") != list(_ROW_IDS[:expected_rows])
        or case.get("hidden_f32le_sha256")
        != hashlib.sha256(_canonical_f32le_bytes(selected_hidden)).hexdigest()
    ):
        raise RouterError(
            "internal_worker_error",
            "the committed router case contradicts its generated inputs",
        )
    return _CommittedRouterCase(
        router_case_id=router_case_id,
        hidden_states=selected_hidden,
        router_weights=router_weights,
    )


def _read_strict_json(
    path: Path,
    *,
    maximum_bytes: int,
    label: str,
) -> tuple[dict[str, object], bytes]:
    try:
        observed = path.lstat()
        if not stat.S_ISREG(observed.st_mode):
            raise OSError("not a regular file")
        payload = path.read_bytes()
    except OSError as error:
        raise RouterError(
            "internal_worker_error",
            f"the committed {label} is unavailable",
        ) from error
    if not payload or len(payload) > maximum_bytes:
        raise RouterError(
            "resource_limit",
            f"the committed {label} violates its byte bound",
        )
    try:
        document = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_object_without_duplicates,
            parse_constant=_reject_nonfinite,
        )
    except (UnicodeDecodeError, ValueError, RecursionError, json.JSONDecodeError) as error:
        raise RouterError(
            "internal_worker_error",
            f"the committed {label} is not strict JSON",
        ) from error
    if not isinstance(document, dict):
        raise RouterError(
            "internal_worker_error",
            f"the committed {label} root is not an object",
        )
    return document, payload


def _validate_manifest(manifest: Mapping[str, object]) -> None:
    _require_exact_keys(
        manifest,
        {
            "schema",
            "schema_version",
            "fixture_id",
            "provenance",
            "contract",
            "hidden_state_fixture",
            "weight_fixture",
            "cases",
            "expected_results",
            "files",
            "scope",
        },
        "router fixture manifest",
    )
    if (
        manifest.get("schema") != "pulsarmlx.fixture.router-manifest"
        or manifest.get("schema_version") != "1.0.0"
        or manifest.get("fixture_id") != _FIXTURE_ID
    ):
        raise RouterError(
            "internal_worker_error",
            "the committed router fixture identity is invalid",
        )
    provenance = manifest.get("provenance")
    if not isinstance(provenance, Mapping) or (
        provenance.get("model_free") is not True
        or provenance.get("external_checkpoint_access_required") is not False
        or provenance.get("kind") != "synthetic_generated"
    ):
        raise RouterError(
            "internal_worker_error",
            "the committed router fixture provenance is invalid",
        )
    contract = manifest.get("contract")
    expected_contract = {
        "contract_id": ROUTER_CONTRACT_ID,
        "expert_count": EXPERT_COUNT,
        "hidden_width": HIDDEN_WIDTH,
        "normalization": NORMALIZATION_RULE,
        "tie_rule": TIE_RULE,
        "top_k": TOP_K,
        "weight_byte_order": "little",
        "weight_dtype": OUTPUT_DTYPE,
        "weight_layout": "expert_major_rows_input_columns",
    }
    if contract != expected_contract:
        raise RouterError(
            "internal_worker_error",
            "the committed router fixture contract is invalid",
        )
    hidden_state_fixture = manifest.get("hidden_state_fixture")
    if not isinstance(hidden_state_fixture, Mapping):
        raise RouterError(
            "internal_worker_error",
            "the committed router hidden-state manifest is invalid",
        )
    _require_byte_count(
        hidden_state_fixture.get("canonical_byte_length"),
        MAXIMUM_ROWS * HIDDEN_WIDTH * 4,
        "router hidden-state manifest canonical range",
    )
    if dict(hidden_state_fixture) != {
        "canonical_byte_length": MAXIMUM_ROWS * HIDDEN_WIDTH * 4,
        "canonical_f32le_sha256": (
            "c2237ebd53872efd59a481129db6ce422a3af96193eeba65c834af6ebfb314e8"
        ),
        "complete_shape": [MAXIMUM_ROWS, HIDDEN_WIDTH],
        "finite": True,
        "path": "golden/hidden_states.json",
        "rows_distinct": True,
    }:
        raise RouterError(
            "internal_worker_error",
            "the committed router hidden-state manifest is invalid",
        )
    weight_fixture = manifest.get("weight_fixture")
    if not isinstance(weight_fixture, Mapping):
        raise RouterError(
            "internal_worker_error",
            "the committed router weight manifest is invalid",
        )
    _require_byte_count(
        weight_fixture.get("canonical_byte_length"),
        _WEIGHT_BYTES,
        "router weight manifest canonical range",
    )
    if dict(weight_fixture) != {
        "canonical_byte_length": _WEIGHT_BYTES,
        "canonical_f32le_sha256": (
            "b625762a76a6dab4df249cc56a97946847710e59155585329c7dfa350c8c294f"
        ),
        "raw_weight_bytes_committed": False,
        "recipe_path": "golden/weight_recipe.json",
        "shape": [EXPERT_COUNT, HIDDEN_WIDTH],
    }:
        raise RouterError(
            "internal_worker_error",
            "the committed router weight manifest is invalid",
        )
    cases = manifest.get("cases")
    if (
        not isinstance(cases, list)
        or len(cases) != len(_SYNTHETIC_CASE_ROWS)
        or {
            case.get("case_id")
            for case in cases
            if isinstance(case, Mapping)
        }
        != set(_SYNTHETIC_CASE_ROWS)
    ):
        raise RouterError(
            "internal_worker_error",
            "the committed router case inventory is invalid",
        )


def _manifest_file(
    manifest: Mapping[str, object],
    relative_path: str,
) -> Mapping[str, object]:
    files = manifest.get("files")
    if not isinstance(files, list):
        raise RouterError(
            "internal_worker_error",
            "the committed router manifest file inventory is invalid",
        )
    matches = [
        entry
        for entry in files
        if isinstance(entry, Mapping) and entry.get("path") == relative_path
    ]
    if len(matches) != 1:
        raise RouterError(
            "internal_worker_error",
            "the committed router manifest file identity is ambiguous",
        )
    return matches[0]


def _validate_manifest_file(
    manifest: Mapping[str, object],
    *,
    relative_path: str,
    payload: bytes,
) -> None:
    entry = _manifest_file(manifest, relative_path)
    _require_byte_count(
        len(payload),
        entry.get("byte_length"),
        "router fixture encoded file",
    )
    if entry.get("sha256") != hashlib.sha256(payload).hexdigest():
        raise RouterError(
            "internal_worker_error",
            "a committed router fixture file differs from its manifest",
        )


def _manifest_case(
    manifest: Mapping[str, object],
    router_case_id: object,
) -> Mapping[str, object]:
    cases = manifest.get("cases")
    if not isinstance(cases, list):
        raise RouterError(
            "internal_worker_error",
            "the committed router case inventory is invalid",
        )
    matches = [
        case
        for case in cases
        if isinstance(case, Mapping) and case.get("case_id") == router_case_id
    ]
    if len(matches) != 1:
        raise RouterError(
            "internal_worker_error",
            "the committed router case identity is missing or duplicated",
        )
    _require_exact_keys(
        matches[0],
        {
            "case_id",
            "expected_result_key",
            "hidden_f32le_sha256",
            "hidden_row_ids",
            "hidden_shape",
        },
        "router case",
    )
    return matches[0]


def _validate_hidden_document(
    document: Mapping[str, object],
) -> tuple[tuple[float, ...], ...]:
    _require_exact_keys(
        document,
        {
            "schema",
            "schema_version",
            "fixture_id",
            "provenance",
            "shape",
            "dtype",
            "byte_order",
            "canonical_byte_length",
            "canonical_f32le_sha256",
            "rows",
        },
        "router hidden-state fixture",
    )
    _require_byte_count(
        document.get("canonical_byte_length"),
        MAXIMUM_ROWS * HIDDEN_WIDTH * 4,
        "router hidden-state canonical tensor",
    )
    if (
        document.get("schema") != "pulsarmlx.fixture.router-hidden-states"
        or document.get("schema_version") != "1.0.0"
        or document.get("fixture_id") != _HIDDEN_FIXTURE_ID
        or document.get("provenance") != _PROVENANCE
        or document.get("shape") != [MAXIMUM_ROWS, HIDDEN_WIDTH]
        or document.get("dtype") != OUTPUT_DTYPE
        or document.get("byte_order") != "little"
    ):
        raise RouterError(
            "internal_worker_error",
            "the committed router hidden-state contract is invalid",
        )
    rows = document.get("rows")
    if not isinstance(rows, list) or len(rows) != MAXIMUM_ROWS:
        raise RouterError(
            "internal_worker_error",
            "the committed router hidden-state rows are invalid",
        )
    raw_values: list[object] = []
    for row_index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise RouterError(
                "internal_worker_error",
                "a committed router hidden-state row is invalid",
            )
        _require_exact_keys(
            row,
            {"row_id", "one_hot_column", "values", "canonical_f32le_sha256"},
            "router hidden-state row",
        )
        if (
            row.get("row_id") != _ROW_IDS[row_index]
            or row.get("one_hot_column") != row_index
        ):
            raise RouterError(
                "internal_worker_error",
                "a committed router hidden-state row identity is invalid",
            )
        raw_values.append(row.get("values"))
    admitted = _validate_float32_matrix(
        raw_values,
        expected_rows=MAXIMUM_ROWS,
        expected_columns=HIDDEN_WIDTH,
        label="committed router hidden states",
    )
    for row_index, row in enumerate(admitted):
        if any(
            value != (1.0 if column == row_index else 0.0)
            for column, value in enumerate(row)
        ):
            raise RouterError(
                "internal_worker_error",
                "a committed router hidden-state row is not its frozen one-hot input",
            )
        if rows[row_index].get("canonical_f32le_sha256") != hashlib.sha256(
            _canonical_f32le_bytes((row,))
        ).hexdigest():
            raise RouterError(
                "internal_worker_error",
                "a committed router hidden-state row hash is invalid",
            )
    canonical = _canonical_f32le_bytes(admitted)
    _require_byte_count(
        len(canonical),
        document.get("canonical_byte_length"),
        "router hidden-state canonical tensor",
    )
    if (
        hashlib.sha256(canonical).hexdigest()
        != document.get("canonical_f32le_sha256")
    ):
        raise RouterError(
            "internal_worker_error",
            "the committed router hidden-state hash is invalid",
        )
    return admitted


def _build_weights_from_recipe(
    recipe: Mapping[str, object],
) -> tuple[tuple[float, ...], ...]:
    _require_exact_keys(
        recipe,
        {
            "schema",
            "schema_version",
            "fixture_id",
            "provenance",
            "shape",
            "dtype",
            "byte_order",
            "layout",
            "logical_element_count",
            "canonical_byte_length",
            "canonical_encoding",
            "canonical_f32le_sha256",
            "raw_weight_bytes_committed",
            "columns",
            "remaining_columns",
        },
        "router weight recipe",
    )
    _require_byte_count(
        recipe.get("canonical_byte_length"),
        _WEIGHT_BYTES,
        "router weight canonical tensor",
    )
    if (
        recipe.get("schema") != "pulsarmlx.fixture.router-weight-recipe"
        or recipe.get("schema_version") != "1.0.0"
        or recipe.get("fixture_id") != _WEIGHT_FIXTURE_ID
        or recipe.get("provenance") != _PROVENANCE
        or recipe.get("shape") != [EXPERT_COUNT, HIDDEN_WIDTH]
        or recipe.get("dtype") != OUTPUT_DTYPE
        or recipe.get("byte_order") != "little"
        or recipe.get("layout") != "expert_major_rows_input_columns"
        or recipe.get("logical_element_count") != _WEIGHT_ELEMENT_COUNT
        or recipe.get("raw_weight_bytes_committed") is not False
    ):
        raise RouterError(
            "internal_worker_error",
            "the committed router weight recipe contract is invalid",
        )
    columns = recipe.get("columns")
    expected_columns = (
        {
            "center": 64,
            "divisor": 16,
            "formula": "f32((((expert_id * 37) % 128) - 64) / 16.0)",
            "input_column": 0,
            "modulus": 128,
            "multiplier": 37,
            "offset": 0,
        },
        {
            "center": 64,
            "divisor": 16,
            "formula": "f32((((expert_id * 53 + 7) % 128) - 64) / 16.0)",
            "input_column": 1,
            "modulus": 128,
            "multiplier": 53,
            "offset": 7,
        },
    )
    if columns != list(expected_columns) or recipe.get("remaining_columns") != {
        "end_exclusive": HIDDEN_WIDTH,
        "start_inclusive": 2,
        "value": 0.0,
    }:
        raise RouterError(
            "internal_worker_error",
            "the committed router weight formula is invalid",
        )

    zero_tail = (0.0,) * (HIDDEN_WIDTH - 2)
    weights = tuple(
        (
            _canonical_float32((((expert_id * 37) % EXPERT_COUNT) - 64) / 16.0),
            _canonical_float32(
                (((expert_id * 53 + 7) % EXPERT_COUNT) - 64) / 16.0
            ),
            *zero_tail,
        )
        for expert_id in range(EXPERT_COUNT)
    )
    canonical = _canonical_f32le_bytes(weights)
    _require_byte_count(
        len(canonical),
        _WEIGHT_BYTES,
        "reconstructed router weight tensor",
    )
    if (
        hashlib.sha256(canonical).hexdigest()
        != recipe.get("canonical_f32le_sha256")
    ):
        raise RouterError(
            "internal_worker_error",
            "the reconstructed router weight hash is invalid",
        )
    return weights


def _canonical_float32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def _require_exact_keys(
    value: Mapping[str, object],
    expected: set[str],
    label: str,
) -> None:
    if set(value) != expected:
        raise RouterError(
            "internal_worker_error",
            f"the committed {label} fields are invalid",
        )


def _require_byte_count(
    actual: object,
    expected: object,
    label: str,
) -> None:
    if (
        isinstance(actual, bool)
        or not isinstance(actual, int)
        or isinstance(expected, bool)
        or not isinstance(expected, int)
        or actual != expected
    ):
        bounded_actual = (
            actual
            if isinstance(actual, int)
            and not isinstance(actual, bool)
            and -(1 << 63) <= actual < 1 << 64
            else None
        )
        bounded_expected = (
            expected
            if isinstance(expected, int)
            and not isinstance(expected, bool)
            and -(1 << 63) <= expected < 1 << 64
            else None
        )
        raise RouterError(
            "invalid_byte_count",
            f"{label} has an invalid byte count",
            details={
                "expected_bytes": bounded_expected,
                "actual_bytes": bounded_actual,
            },
        )


def _object_without_duplicates(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    raise ValueError(f"non-finite JSON number is forbidden: {value}")
