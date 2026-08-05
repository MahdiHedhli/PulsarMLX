"""Bounded UTF-8 NDJSON framing for the PulsarMLX worker protocol."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
import json
from typing import Any


PROTOCOL_VERSION = 1
MAX_REQUEST_ID = 2**64 - 1
MAX_ERROR_MESSAGE_CHARS = 512

STABLE_ERROR_CODES = frozenset(
    {
        "protocol_mismatch",
        "message_too_large",
        "malformed_request",
        "unsupported_operation",
        "invalid_shape",
        "invalid_dtype",
        "invalid_layout",
        "invalid_byte_count",
        "runtime_version_mismatch",
        "unsupported_host",
        "metal_unavailable",
        "device_unavailable",
        "evaluation_failed",
        "comparison_failed",
        "resource_limit",
        "internal_worker_error",
    }
)

REQUIRED_OPERATIONS = frozenset({"health", "tensor_probe", "shutdown"})
_SHAPE_KEYS = frozenset({"shape", "logical_shape", "storage_shape"})
_MAX_IDENTIFIER_CHARS = 128


@dataclass(frozen=True, slots=True)
class ProtocolLimits:
    """Effective bounds for one worker control channel."""

    max_request_bytes: int = 64 * 1024
    max_response_bytes: int = 1024 * 1024
    max_nesting_depth: int = 16
    max_list_items: int = 4096
    max_shape_rank: int = 16
    max_shape_elements: int = 1024 * 1024

    def __post_init__(self) -> None:
        for name, value in (
            ("max_request_bytes", self.max_request_bytes),
            ("max_response_bytes", self.max_response_bytes),
            ("max_nesting_depth", self.max_nesting_depth),
            ("max_list_items", self.max_list_items),
            ("max_shape_rank", self.max_shape_rank),
            ("max_shape_elements", self.max_shape_elements),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


DEFAULT_LIMITS = ProtocolLimits()


@dataclass(frozen=True, slots=True)
class RequestEnvelope:
    protocol: int
    request_id: int
    op: str
    params: dict[str, Any]


class ProtocolError(Exception):
    """A stable, bounded error suitable for a protocol error envelope."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        if code not in STABLE_ERROR_CODES:
            raise ValueError(f"unknown protocol error code: {code!r}")
        if not isinstance(retryable, bool):
            raise ValueError("retryable must be a boolean")
        if details is not None and not isinstance(details, Mapping):
            raise ValueError("error details must be a mapping")

        self.code = code
        self.message = _bounded_diagnostic(message)
        self.retryable = retryable
        self.details = {} if details is None else dict(details)
        super().__init__(f"{self.code}: {self.message}")


class RequestDecoder:
    """Incrementally decode strict protocol-v1 request lines."""

    def __init__(
        self,
        *,
        limits: ProtocolLimits = DEFAULT_LIMITS,
        allowed_operations: Collection[str] = REQUIRED_OPERATIONS,
    ) -> None:
        if not isinstance(limits, ProtocolLimits):
            raise TypeError("limits must be ProtocolLimits")
        operations = frozenset(allowed_operations)
        if not operations or any(not _valid_identifier(op) for op in operations):
            raise ValueError("allowed operations must be bounded stable identifiers")

        self._limits = limits
        self._allowed_operations = operations
        self._buffer = bytearray()

    def feed(self, data: bytes | bytearray | memoryview) -> list[RequestEnvelope]:
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise ProtocolError("malformed_request", "request data must be bytes")
        self._buffer.extend(data)

        requests: list[RequestEnvelope] = []
        while True:
            newline = self._buffer.find(b"\n")
            if newline < 0:
                if len(self._buffer) > self._limits.max_request_bytes:
                    self._buffer.clear()
                    raise ProtocolError(
                        "message_too_large",
                        "request line exceeds the configured byte limit",
                    )
                return requests

            line = bytes(self._buffer[:newline])
            del self._buffer[: newline + 1]
            if len(line) > self._limits.max_request_bytes:
                raise ProtocolError(
                    "message_too_large",
                    "request line exceeds the configured byte limit",
                )
            requests.append(self._decode_line(line))

    def finish(self) -> None:
        if self._buffer:
            self._buffer.clear()
            raise ProtocolError(
                "malformed_request",
                "input ended with an incomplete request line",
            )

    def _decode_line(self, line: bytes) -> RequestEnvelope:
        if not line:
            raise ProtocolError("malformed_request", "request line is empty")
        try:
            text = line.decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise ProtocolError(
                "malformed_request", "request line is not valid UTF-8"
            ) from error

        try:
            value = json.loads(
                text,
                object_pairs_hook=_object_without_duplicates,
                parse_constant=_reject_nonfinite,
            )
        except (_DuplicateKey, ValueError, RecursionError, json.JSONDecodeError) as error:
            raise ProtocolError(
                "malformed_request", "request line is not strict JSON"
            ) from error

        return self._validate_envelope(value)

    def _validate_envelope(self, value: Any) -> RequestEnvelope:
        if not isinstance(value, dict) or set(value) != {
            "protocol",
            "request_id",
            "op",
            "params",
        }:
            raise ProtocolError(
                "malformed_request",
                "request envelope must contain exactly protocol, request_id, op, and params",
            )

        protocol = value["protocol"]
        if isinstance(protocol, bool) or not isinstance(protocol, int):
            raise ProtocolError(
                "malformed_request", "protocol version must be an integer"
            )
        if protocol != PROTOCOL_VERSION:
            raise ProtocolError(
                "protocol_mismatch",
                "request uses an unsupported required protocol version",
            )

        request_id = value["request_id"]
        _validate_request_id(request_id)

        op = value["op"]
        if not isinstance(op, str) or not _valid_identifier(op):
            raise ProtocolError(
                "malformed_request", "operation must be a bounded stable identifier"
            )
        if op not in self._allowed_operations:
            raise ProtocolError(
                "unsupported_operation", "operation is not registered for this worker"
            )

        params = value["params"]
        if not isinstance(params, dict):
            raise ProtocolError("malformed_request", "params must be a JSON object")
        _validate_value(params, self._limits, depth=0)

        return RequestEnvelope(
            protocol=protocol,
            request_id=request_id,
            op=op,
            params=params,
        )


def encode_success(
    request_id: int,
    result: Mapping[str, Any],
    *,
    limits: ProtocolLimits = DEFAULT_LIMITS,
) -> bytes:
    """Encode one successful response and its terminating LF."""

    _validate_request_id(request_id)
    if not isinstance(result, Mapping):
        raise ProtocolError("internal_worker_error", "response result must be an object")
    envelope = {
        "protocol": PROTOCOL_VERSION,
        "request_id": request_id,
        "ok": True,
        "result": dict(result),
    }
    return _encode_response(envelope, limits)


def encode_error(
    request_id: int,
    error: ProtocolError,
    *,
    limits: ProtocolLimits = DEFAULT_LIMITS,
) -> bytes:
    """Encode one stable structured error response and its terminating LF."""

    _validate_request_id(request_id)
    if not isinstance(error, ProtocolError):
        raise TypeError("error must be ProtocolError")
    envelope = {
        "protocol": PROTOCOL_VERSION,
        "request_id": request_id,
        "ok": False,
        "error": {
            "code": error.code,
            "message": error.message,
            "retryable": error.retryable,
            "details": error.details,
        },
    }
    return _encode_response(envelope, limits)


def _encode_response(envelope: dict[str, Any], limits: ProtocolLimits) -> bytes:
    if not isinstance(limits, ProtocolLimits):
        raise TypeError("limits must be ProtocolLimits")
    _validate_value(envelope, limits, depth=0, validate_shapes=False)
    try:
        line = json.dumps(
            envelope,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as error:
        raise ProtocolError(
            "internal_worker_error", "response is not bounded strict JSON"
        ) from error
    if len(line) > limits.max_response_bytes:
        raise ProtocolError(
            "message_too_large", "response line exceeds the configured byte limit"
        )
    return line + b"\n"


def _validate_request_id(request_id: Any) -> None:
    if (
        isinstance(request_id, bool)
        or not isinstance(request_id, int)
        or request_id < 0
        or request_id > MAX_REQUEST_ID
    ):
        raise ProtocolError(
            "malformed_request", "request_id must be an unsigned 64-bit integer"
        )


def _validate_value(
    value: Any,
    limits: ProtocolLimits,
    *,
    depth: int,
    validate_shapes: bool = True,
) -> None:
    if isinstance(value, dict):
        if depth >= limits.max_nesting_depth:
            raise ProtocolError("resource_limit", "JSON nesting exceeds its limit")
        if len(value) > limits.max_list_items:
            raise ProtocolError("resource_limit", "JSON object exceeds its item limit")
        for key, child in value.items():
            if not isinstance(key, str):
                raise ProtocolError(
                    "malformed_request", "JSON object keys must be strings"
                )
            if validate_shapes and key in _SHAPE_KEYS:
                _validate_shape(child, limits)
            _validate_value(
                child,
                limits,
                depth=depth + 1,
                validate_shapes=validate_shapes,
            )
        return

    if isinstance(value, list):
        if depth >= limits.max_nesting_depth:
            raise ProtocolError("resource_limit", "JSON nesting exceeds its limit")
        if len(value) > limits.max_list_items:
            raise ProtocolError("resource_limit", "JSON list exceeds its item limit")
        for child in value:
            _validate_value(
                child,
                limits,
                depth=depth + 1,
                validate_shapes=validate_shapes,
            )
        return

    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float) and value == value and value not in (float("inf"), float("-inf")):
        return
    raise ProtocolError("malformed_request", "value is not strict bounded JSON")


def _validate_shape(value: Any, limits: ProtocolLimits) -> None:
    if not isinstance(value, list) or not value or len(value) > limits.max_shape_rank:
        raise ProtocolError("invalid_shape", "shape rank is outside its limit")

    elements = 1
    for dimension in value:
        if isinstance(dimension, bool) or not isinstance(dimension, int) or dimension <= 0:
            raise ProtocolError(
                "invalid_shape", "shape dimensions must be positive integers"
            )
        if elements > limits.max_shape_elements // dimension:
            raise ProtocolError(
                "invalid_shape", "shape element count exceeds its limit"
            )
        elements *= dimension


def _valid_identifier(value: Any) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= _MAX_IDENTIFIER_CHARS
        and value.strip() == value
        and all(character.isalnum() or character in "-_.:" for character in value)
    )


class _DuplicateKey(ValueError):
    pass


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey(key)
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    raise ValueError(f"non-finite JSON number is forbidden: {value}")


def _bounded_diagnostic(message: str) -> str:
    if not isinstance(message, str):
        message = str(message)
    tokens = []
    for token in message.split():
        if token.startswith(("/", "~/")) or "/Users/" in token or "/home/" in token:
            tokens.append("<redacted-path>")
        else:
            tokens.append(token)
    sanitized = " ".join(tokens) or "protocol operation failed"
    return sanitized[:MAX_ERROR_MESSAGE_CHARS]
