"""Persistent bounded protocol loop for the PulsarMLX MLX worker.

The worker reserves its original stdout descriptor for protocol frames before
runtime discovery.  Python-level and native-library stdout therefore cannot
contaminate the NDJSON channel; human-readable diagnostics use stderr only.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
import json
import os
from pathlib import Path
import sys
from typing import Any, BinaryIO

from .moe import RoutedMoeError, run_routed_moe_fixture
from .protocol import (
    DEFAULT_LIMITS,
    MAX_REQUEST_ID,
    PROTOCOL_VERSION,
    ProtocolError,
    RequestDecoder,
    RequestEnvelope,
    encode_error,
    encode_success,
)
from .runtime import (
    GPU_DEVICE_ID,
    PROBE_FIXTURE_ID,
    RuntimeContractError,
    RuntimeIdentity,
    TensorProbeResult,
    discover_runtime,
    run_tensor_probe,
)
from .tensor_ops import load_fixture_manifest, run_fixture_operation


WORKER_VERSION = "0.1.0"
_SYNTHETIC_MOE_FIXTURE_ID = "synthetic-routed-moe-v1"
_SYNTHETIC_MOE_FIXTURE_PATH = Path("fixtures/mlx/routed-moe-v1.json")
_MAX_SYNTHETIC_MOE_FIXTURE_BYTES = 1024 * 1024
_READ_LIMIT = DEFAULT_LIMITS.max_request_bytes + 2
_EXIT_PROTOCOL_ERROR = 2
_EXIT_RUNTIME_ERROR = 3
_EXIT_INTERNAL_ERROR = 70

ProbeRunner = Callable[..., TensorProbeResult]


def main() -> int:
    """Discover the runtime and serve one persistent protocol session."""

    try:
        protocol_stdout = _reserve_protocol_stdout()
    except (OSError, ValueError):
        _diagnostic("internal_worker_error", "protocol stdout could not be reserved")
        return _EXIT_INTERNAL_ERROR

    try:
        try:
            identity = discover_runtime()
        except RuntimeContractError as error:
            _diagnostic(error.code, error.message)
            return _EXIT_RUNTIME_ERROR
        except Exception:
            _diagnostic(
                "internal_worker_error",
                "runtime discovery failed before protocol negotiation",
            )
            return _EXIT_INTERNAL_ERROR

        return _serve(identity, sys.stdin.buffer, protocol_stdout)
    except BrokenPipeError:
        return 0
    except Exception:
        _diagnostic("internal_worker_error", "the worker protocol loop failed")
        return _EXIT_INTERNAL_ERROR
    finally:
        protocol_stdout.close()


def _serve(
    identity: RuntimeIdentity,
    stdin: BinaryIO,
    protocol_stdout: BinaryIO,
    *,
    probe_runner: ProbeRunner = run_tensor_probe,
) -> int:
    """Serve requests sequentially until shutdown or clean stdin EOF.

    This helper accepts streams and a probe callable so the process contract
    can be checked without scheduling native MLX work.
    """

    _write_protocol_line(protocol_stdout, _encode_hello(identity))

    while True:
        raw_line = stdin.readline(_READ_LIMIT)
        if raw_line == b"":
            return 0

        request_id = _request_id_hint(raw_line)
        if not raw_line.endswith(b"\n"):
            code = (
                "message_too_large"
                if len(raw_line) > DEFAULT_LIMITS.max_request_bytes
                else "malformed_request"
            )
            error = ProtocolError(
                code,
                "request line is oversized or ended before its terminating LF",
            )
            _write_protocol_error(protocol_stdout, request_id, error)
            return _EXIT_PROTOCOL_ERROR

        if len(raw_line) - 1 > DEFAULT_LIMITS.max_request_bytes:
            error = ProtocolError(
                "message_too_large",
                "request line exceeds the configured byte limit",
            )
            _write_protocol_error(protocol_stdout, request_id, error)
            continue

        decoder = RequestDecoder()
        try:
            requests = decoder.feed(raw_line)
            decoder.finish()
            if len(requests) != 1:
                raise ProtocolError(
                    "malformed_request",
                    "each worker dispatch must contain exactly one request line",
                )
            request = requests[0]
        except ProtocolError as error:
            _write_protocol_error(protocol_stdout, request_id, error)
            continue

        try:
            result, should_shutdown = _dispatch(
                request,
                identity,
                probe_runner=probe_runner,
            )
        except ProtocolError as error:
            _write_protocol_error(protocol_stdout, request.request_id, error)
            continue
        except RuntimeContractError as error:
            protocol_error = _runtime_protocol_error(error)
            _diagnostic(protocol_error.code, protocol_error.message)
            _write_protocol_error(
                protocol_stdout,
                request.request_id,
                protocol_error,
            )
            continue
        except Exception:
            error = ProtocolError(
                "internal_worker_error",
                "the requested worker operation failed internally",
            )
            _diagnostic(error.code, error.message)
            _write_protocol_error(protocol_stdout, request.request_id, error)
            return _EXIT_INTERNAL_ERROR

        _write_protocol_line(
            protocol_stdout,
            encode_success(request.request_id, result),
        )
        if should_shutdown:
            return 0


def _dispatch(
    request: RequestEnvelope,
    identity: RuntimeIdentity,
    *,
    probe_runner: ProbeRunner,
) -> tuple[dict[str, object], bool]:
    if request.op == "health":
        _require_exact_params(request.params, frozenset())
        result = {
            "ready": True,
            "device_state": "available_unevaluated",
            "protocol": PROTOCOL_VERSION,
            "worker_version": WORKER_VERSION,
            **identity.to_protocol_result(),
        }
        return result, False

    if request.op == "tensor_probe":
        _require_exact_params(request.params, frozenset({"fixture_id", "device"}))
        fixture_id = request.params["fixture_id"]
        requested_device = request.params["device"]
        if fixture_id != PROBE_FIXTURE_ID:
            raise ProtocolError(
                "malformed_request",
                "tensor_probe fixture_id is not the admitted bounded fixture",
            )
        if not isinstance(requested_device, str):
            raise ProtocolError(
                "malformed_request",
                "tensor_probe device must be a stable string identifier",
            )
        probe = probe_runner(identity, requested_device=requested_device)
        return probe.to_protocol_result(), False

    if request.op == "run_fixture":
        _require_exact_params(
            request.params,
            frozenset(
                {"fixture_set_id", "case_id", "device", "allow_fallback"}
            ),
        )
        fixture_set_id = request.params["fixture_set_id"]
        case_id = request.params["case_id"]
        requested_device = request.params["device"]
        allow_fallback = request.params["allow_fallback"]
        if not isinstance(fixture_set_id, str) or not isinstance(case_id, str):
            raise ProtocolError(
                "malformed_request",
                "run_fixture identities must be stable strings",
            )
        if not isinstance(requested_device, str) or not isinstance(
            allow_fallback, bool
        ):
            raise ProtocolError(
                "malformed_request",
                "run_fixture device and fallback fields have invalid types",
            )

        manifest = load_fixture_manifest(
            Path("fixtures/mlx/manifest.json"),
            expected_fixture_set_id=fixture_set_id,
        )
        case = next(
            (
                candidate
                for candidate in manifest.operations
                if candidate.get("case_id") == case_id
            ),
            None,
        )
        if case is None:
            raise ProtocolError(
                "malformed_request",
                "run_fixture case_id is not present in the admitted fixture set",
            )
        result = run_fixture_operation(
            case,
            fixture_set_id=manifest.fixture_set_id,
            synchronization_rule=manifest.synchronization_rule,
            maximum_fixture_elements=manifest.maximum_fixture_elements,
            requested_device=requested_device,
            allow_fallback=allow_fallback,
        )
        return result.to_protocol_result(), False

    if request.op == "run_synthetic_moe":
        _require_exact_params(
            request.params,
            frozenset({"fixture_id", "device", "allow_fallback"}),
        )
        fixture_id = request.params["fixture_id"]
        requested_device = request.params["device"]
        allow_fallback = request.params["allow_fallback"]
        if fixture_id != _SYNTHETIC_MOE_FIXTURE_ID:
            raise ProtocolError(
                "malformed_request",
                "run_synthetic_moe fixture_id is not the admitted fixture",
            )
        if not isinstance(requested_device, str) or not isinstance(
            allow_fallback, bool
        ):
            raise ProtocolError(
                "malformed_request",
                "run_synthetic_moe device and fallback fields have invalid types",
            )
        fixture = _load_synthetic_moe_fixture()
        try:
            result = run_routed_moe_fixture(
                fixture,
                expected_fixture_id=fixture_id,
                requested_device=requested_device,
                allow_fallback=allow_fallback,
            )
        except RoutedMoeError as error:
            raise ProtocolError(error.code, error.message) from error
        return result.to_protocol_result(), False

    if request.op == "shutdown":
        _require_exact_params(request.params, frozenset())
        return {"shutdown": True, "cleanup": "graceful"}, True

    raise ProtocolError(
        "unsupported_operation",
        "operation is not registered for this worker",
    )


def _require_exact_params(
    params: Mapping[str, Any],
    expected: frozenset[str],
) -> None:
    if set(params) != expected:
        raise ProtocolError(
            "malformed_request",
            "operation parameters do not match the required schema",
        )


def _load_synthetic_moe_fixture() -> dict[str, object]:
    try:
        payload = _SYNTHETIC_MOE_FIXTURE_PATH.read_bytes()
    except OSError as error:
        raise ProtocolError(
            "internal_worker_error",
            "the committed synthetic MoE fixture is unavailable",
        ) from error
    if not payload or len(payload) > _MAX_SYNTHETIC_MOE_FIXTURE_BYTES:
        raise ProtocolError(
            "resource_limit",
            "the committed synthetic MoE fixture violates its byte bound",
        )
    try:
        fixture = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_object_without_duplicates,
            parse_constant=_reject_nonfinite,
        )
    except (UnicodeDecodeError, ValueError, RecursionError, json.JSONDecodeError) as error:
        raise ProtocolError(
            "internal_worker_error",
            "the committed synthetic MoE fixture is not strict JSON",
        ) from error
    if not isinstance(fixture, dict):
        raise ProtocolError(
            "internal_worker_error",
            "the committed synthetic MoE fixture root is not an object",
        )
    return fixture


def _encode_hello(identity: RuntimeIdentity) -> bytes:
    hello = {
        "protocol": PROTOCOL_VERSION,
        "op": "hello",
        "worker_version": WORKER_VERSION,
        "python_version": identity.python_version,
        "python_arch": identity.python_arch,
        "mlx_version": identity.mlx_version,
        "macos_version": identity.macos_version,
        "metal_available": identity.metal_available,
        "gpu_count": identity.gpu_count,
        "devices": [
            {"id": device.device_id, "kind": GPU_DEVICE_ID}
            for device in identity.devices
        ],
        "capabilities": {
            "operations": list(identity.capabilities),
            "dtypes": list(identity.supported_dtypes),
        },
        "limits": {
            "max_request_bytes": DEFAULT_LIMITS.max_request_bytes,
            "max_response_bytes": DEFAULT_LIMITS.max_response_bytes,
            "max_fixture_elements": DEFAULT_LIMITS.max_shape_elements,
        },
    }
    try:
        encoded = json.dumps(
            hello,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as error:
        raise ProtocolError(
            "internal_worker_error",
            "worker hello could not be encoded as strict JSON",
        ) from error
    if len(encoded) > DEFAULT_LIMITS.max_response_bytes:
        raise ProtocolError(
            "message_too_large",
            "worker hello exceeds the configured response limit",
        )
    return encoded + b"\n"


def _runtime_protocol_error(error: RuntimeContractError) -> ProtocolError:
    try:
        return ProtocolError(
            error.code,
            error.message,
            retryable=error.retryable,
            details=error.details,
        )
    except (TypeError, ValueError):
        return ProtocolError(
            "internal_worker_error",
            "runtime failure did not satisfy the stable worker error contract",
        )


def _write_protocol_error(
    protocol_stdout: BinaryIO,
    request_id: int | None,
    error: ProtocolError,
) -> None:
    response_id = 0 if request_id is None else request_id
    try:
        encoded = encode_error(response_id, error)
    except (ProtocolError, TypeError, ValueError):
        encoded = encode_error(
            response_id,
            ProtocolError(
                "internal_worker_error",
                "worker error response could not be encoded safely",
            ),
        )
    _write_protocol_line(protocol_stdout, encoded)


def _write_protocol_line(protocol_stdout: BinaryIO, encoded: bytes) -> None:
    protocol_stdout.write(encoded)
    protocol_stdout.flush()


def _request_id_hint(raw_line: bytes) -> int | None:
    """Recover a valid ID only when strict bounded JSON makes it unambiguous."""

    if len(raw_line) > _READ_LIMIT:
        return None
    try:
        value = json.loads(
            raw_line.decode("utf-8", errors="strict"),
            object_pairs_hook=_object_without_duplicates,
            parse_constant=_reject_nonfinite,
        )
    except (UnicodeDecodeError, ValueError, RecursionError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    request_id = value.get("request_id")
    if (
        isinstance(request_id, bool)
        or not isinstance(request_id, int)
        or request_id < 0
        or request_id > MAX_REQUEST_ID
    ):
        return None
    return request_id


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    raise ValueError(f"non-finite JSON number is forbidden: {value}")


def _reserve_protocol_stdout() -> BinaryIO:
    """Duplicate stdout for protocol use, then route incidental output away."""

    sys.stdout.flush()
    protocol_fd = os.dup(sys.stdout.fileno())
    try:
        os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    except Exception:
        os.close(protocol_fd)
        raise
    return os.fdopen(protocol_fd, "wb", buffering=0)


def _diagnostic(code: str, message: str) -> None:
    bounded_code = code if code.replace("_", "").isalnum() else "worker_error"
    bounded_message = " ".join(str(message).split())[:512]
    if not bounded_message:
        bounded_message = "worker operation failed"
    sys.stderr.write(f"pulsar-mlx-worker[{bounded_code}]: {bounded_message}\n")
    sys.stderr.flush()


if __name__ == "__main__":
    raise SystemExit(main())
