"""Contract tests for the bounded protocol-v1 NDJSON control channel."""

from __future__ import annotations

from dataclasses import replace
import json
import unittest

from pulsar_mlx_worker.protocol import (
    DEFAULT_LIMITS,
    PROTOCOL_VERSION,
    ProtocolError,
    RequestDecoder,
    encode_error,
    encode_success,
)


def request_bytes(
    request_id: int = 7,
    op: str = "health",
    params: dict[str, object] | None = None,
) -> bytes:
    envelope = {
        "protocol": PROTOCOL_VERSION,
        "request_id": request_id,
        "op": op,
        "params": {} if params is None else params,
    }
    return (
        json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        + b"\n"
    )


class ProtocolContractTests(unittest.TestCase):
    def assert_protocol_error(self, expected_code: str, callable_, /, *args, **kwargs):
        with self.assertRaises(ProtocolError) as caught:
            callable_(*args, **kwargs)
        self.assertEqual(caught.exception.code, expected_code)
        return caught.exception

    def test_fragmented_utf8_delivery_waits_for_a_complete_line(self) -> None:
        decoder = RequestDecoder()
        encoded = request_bytes(params={"label": "gpu-π"})
        split = encoded.index("π".encode("utf-8")) + 1

        self.assertEqual(decoder.feed(encoded[:split]), [])
        self.assertEqual(decoder.feed(encoded[split:-1]), [])
        requests = decoder.feed(encoded[-1:])

        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].protocol, PROTOCOL_VERSION)
        self.assertEqual(requests[0].request_id, 7)
        self.assertEqual(requests[0].op, "health")
        self.assertEqual(requests[0].params, {"label": "gpu-π"})
        decoder.finish()

    def test_multiple_complete_messages_preserve_request_order(self) -> None:
        decoder = RequestDecoder()
        requests = decoder.feed(
            request_bytes(3, "health") + request_bytes(4, "shutdown")
        )

        self.assertEqual([request.request_id for request in requests], [3, 4])
        self.assertEqual([request.op for request in requests], ["health", "shutdown"])

    def test_finish_rejects_an_incomplete_frame(self) -> None:
        decoder = RequestDecoder()
        decoder.feed(request_bytes()[:-1])
        self.assert_protocol_error("malformed_request", decoder.finish)

    def test_request_limit_is_enforced_incrementally_and_at_the_boundary(self) -> None:
        encoded = request_bytes(params={"fixture_id": "probe-a"})
        line_size = len(encoded) - 1

        exact_limits = replace(DEFAULT_LIMITS, max_request_bytes=line_size)
        self.assertEqual(
            RequestDecoder(limits=exact_limits).feed(encoded)[0].request_id,
            7,
        )

        smaller_limits = replace(DEFAULT_LIMITS, max_request_bytes=line_size - 1)
        self.assert_protocol_error(
            "message_too_large",
            RequestDecoder(limits=smaller_limits).feed,
            encoded[:-1],
        )

    def test_response_limit_is_enforced_at_the_encoded_line_boundary(self) -> None:
        encoded = encode_success(7, {"status": "ready"})
        line_size = len(encoded) - 1

        exact_limits = replace(DEFAULT_LIMITS, max_response_bytes=line_size)
        self.assertEqual(
            encode_success(7, {"status": "ready"}, limits=exact_limits),
            encoded,
        )

        smaller_limits = replace(DEFAULT_LIMITS, max_response_bytes=line_size - 1)
        self.assert_protocol_error(
            "message_too_large",
            encode_success,
            7,
            {"status": "ready"},
            limits=smaller_limits,
        )

    def test_nesting_and_general_list_limits_are_checked_before_dispatch(self) -> None:
        nesting_limits = replace(DEFAULT_LIMITS, max_nesting_depth=3)
        deeply_nested = request_bytes(params={"a": {"b": {"c": {"d": 1}}}})
        self.assert_protocol_error(
            "resource_limit",
            RequestDecoder(limits=nesting_limits).feed,
            deeply_nested,
        )

        list_limits = replace(DEFAULT_LIMITS, max_list_items=3)
        oversized_list = request_bytes(params={"values": [0, 1, 2, 3]})
        self.assert_protocol_error(
            "resource_limit",
            RequestDecoder(limits=list_limits).feed,
            oversized_list,
        )

    def test_shape_rank_and_element_count_limits_are_checked_before_dispatch(self) -> None:
        limits = replace(
            DEFAULT_LIMITS,
            max_shape_rank=3,
            max_shape_elements=16,
        )
        decoder = RequestDecoder(limits=limits)

        self.assert_protocol_error(
            "invalid_shape",
            decoder.feed,
            request_bytes(params={"shape": [1, 1, 1, 1]}),
        )
        self.assert_protocol_error(
            "invalid_shape",
            RequestDecoder(limits=limits).feed,
            request_bytes(params={"shape": [8, 8]}),
        )
        for invalid_shape in ([0, 2], [-1, 2], [True, 2], [1.5, 2]):
            with self.subTest(shape=invalid_shape):
                self.assert_protocol_error(
                    "invalid_shape",
                    RequestDecoder(limits=limits).feed,
                    request_bytes(params={"shape": invalid_shape}),
                )

    def test_invalid_utf8_json_and_duplicate_keys_are_malformed(self) -> None:
        for encoded in (
            b"\xff\n",
            b'{"protocol":1,]\n',
            b'{"protocol":1,"protocol":1,"request_id":7,"op":"health","params":{}}\n',
        ):
            with self.subTest(encoded=encoded):
                self.assert_protocol_error(
                    "malformed_request", RequestDecoder().feed, encoded
                )

    def test_invalid_envelopes_and_unsigned_request_ids_are_rejected(self) -> None:
        valid = {
            "protocol": PROTOCOL_VERSION,
            "request_id": 7,
            "op": "health",
            "params": {},
        }
        invalid_envelopes = [
            {key: value for key, value in valid.items() if key != "protocol"},
            {key: value for key, value in valid.items() if key != "request_id"},
            {key: value for key, value in valid.items() if key != "op"},
            {key: value for key, value in valid.items() if key != "params"},
            {**valid, "request_id": -1},
            {**valid, "request_id": True},
            {**valid, "request_id": 2**64},
            {**valid, "op": 3},
            {**valid, "params": []},
            {**valid, "unexpected": True},
        ]

        for envelope in invalid_envelopes:
            with self.subTest(envelope=envelope):
                encoded = json.dumps(envelope, separators=(",", ":")).encode() + b"\n"
                self.assert_protocol_error(
                    "malformed_request", RequestDecoder().feed, encoded
                )

    def test_protocol_mismatch_and_unknown_operation_have_stable_codes(self) -> None:
        wrong_protocol = request_bytes().replace(b'"protocol":1', b'"protocol":2')
        self.assert_protocol_error(
            "protocol_mismatch", RequestDecoder().feed, wrong_protocol
        )

        self.assert_protocol_error(
            "unsupported_operation",
            RequestDecoder().feed,
            request_bytes(op="not_registered"),
        )

    def test_success_encoding_is_one_utf8_json_line_with_no_stdout_diagnostics(self) -> None:
        encoded = encode_success(
            7,
            {"message": "scheduled\nand synchronized", "value": 1.25},
        )

        self.assertTrue(encoded.endswith(b"\n"))
        self.assertEqual(encoded.count(b"\n"), 1)
        payload = json.loads(encoded.decode("utf-8"))
        self.assertEqual(
            payload,
            {
                "protocol": PROTOCOL_VERSION,
                "request_id": 7,
                "ok": True,
                "result": {
                    "message": "scheduled\nand synchronized",
                    "value": 1.25,
                },
            },
        )

    def test_structured_error_encoding_uses_a_stable_bounded_envelope(self) -> None:
        error = ProtocolError(
            "device_unavailable",
            "the selected GPU is unavailable",
            retryable=False,
            details={"device": "gpu"},
        )
        encoded = encode_error(9, error)
        payload = json.loads(encoded.decode("utf-8"))

        self.assertEqual(
            payload,
            {
                "protocol": PROTOCOL_VERSION,
                "request_id": 9,
                "ok": False,
                "error": {
                    "code": "device_unavailable",
                    "message": "the selected GPU is unavailable",
                    "retryable": False,
                    "details": {"device": "gpu"},
                },
            },
        )
        with self.assertRaises(ValueError):
            ProtocolError("invented_error", "not a stable protocol error")

    def test_shutdown_request_and_success_envelopes_are_explicit(self) -> None:
        request = RequestDecoder().feed(request_bytes(11, "shutdown"))[0]
        self.assertEqual(request.request_id, 11)
        self.assertEqual(request.op, "shutdown")
        self.assertEqual(request.params, {})

        encoded = encode_success(11, {"shutdown": True})
        self.assertEqual(
            json.loads(encoded.decode("utf-8")),
            {
                "protocol": PROTOCOL_VERSION,
                "request_id": 11,
                "ok": True,
                "result": {"shutdown": True},
            },
        )


if __name__ == "__main__":
    unittest.main()
