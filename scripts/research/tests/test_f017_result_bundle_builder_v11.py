from __future__ import annotations

import hashlib
from pathlib import Path
import struct
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/research"))

from f017_canonical_serialization_v10 import canonical_bytes
from f017_result_artifacts_v11 import require_primary_terminal
from f017_result_bundle_builder_v11 import bank_output_bundle
from f017_result_bundle_builder_v11 import validate_numerical_output_summary
from f017_result_envelope_v11 import ResultEnvelopeError, payload_spec
import f017_corrected_oracle_primary_wrapper_v11 as primary_wrapper
import f017_corrected_oracle_secondary_wrapper_v11 as secondary_wrapper
import f017_corrected_oracle_secondary_numerics_v3 as secondary_core
from generate_f017_corrected_oracle_fixtures import fixture


def output(role: str) -> SimpleNamespace:
    dtype = "f64le" if role == "PRIMARY" else "f32le"
    item = b"\0" * (8 if role == "PRIMARY" else 4)
    hidden = item * 6_144
    normalized = item * 6_144
    logits = item * 154_880
    bit_field = "logit_f64_bits" if role == "PRIMARY" else "logit_f32_bits"
    top = tuple(SimpleNamespace(**{"token_id": index, bit_field: item.hex()}) for index in range(32))
    captures = tuple(SimpleNamespace(layer=index, selected_expert_ids=tuple()) for index in range(79))
    return SimpleNamespace(
        role=role, dtype=dtype, core_execution_count=1,
        final_hidden_element_count=6_144, final_normalized_element_count=6_144,
        full_logits_element_count=154_880,
        final_hidden_payload=hidden, final_normalized_payload=normalized,
        full_logits_payload=logits,
        final_hidden_sha256=hashlib.sha256(hidden).hexdigest(),
        final_normalized_sha256=hashlib.sha256(normalized).hexdigest(),
        full_logits_sha256=hashlib.sha256(logits).hexdigest(),
        layer_captures=captures, selected_token=0, top_32=top,
        top_1_margin=0.0,
        tie_rule=f"LOWEST_TOKEN_ID_ON_EQUAL_BINARY{'64' if role == 'PRIMARY' else '32'}_LOGIT",
    )


class ResultBundleBuilderV11Tests(unittest.TestCase):
    def test_real_secondary_core_summary_couples_to_banking_semantics(self) -> None:
        numerical = secondary_core.execute_outputs(fixture(18101), use_mlx=False)
        result = validate_numerical_output_summary(numerical, "SECONDARY")
        self.assertEqual(result, {"result": "PASS", "role": "SECONDARY", "logit_count": 9})

    def test_secondary_binary32_margin_banks_at_full_geometry(self) -> None:
        candidate = output("SECONDARY")
        values = [0.0] * 154_880
        values[0] = 13.42855453491211
        values[1] = 0.6478179097175598
        logits = struct.pack(f"<{len(values)}f", *values)
        order = sorted(range(len(values)), key=lambda index: (-values[index], index))
        candidate.full_logits_payload = logits
        candidate.full_logits_sha256 = hashlib.sha256(logits).hexdigest()
        candidate.selected_token = order[0]
        candidate.top_32 = tuple(SimpleNamespace(
            token_id=index, logit_f32_bits=struct.pack("<f", values[index]).hex()
        ) for index in order[:32])
        candidate.top_1_margin = struct.unpack(
            "<f", struct.pack("<f", values[order[0]] - values[order[1]])
        )[0]
        digest = "1" * 64
        with tempfile.TemporaryDirectory() as temporary:
            result = bank_output_bundle(
                candidate, Path(temporary), authorization_id="AUTH",
                package_attempt_id="PKG", consumer_event_id="SECONDARY",
                producer_measurement_sha256=digest, durable_start_sha256=digest,
                access_census_sha256=digest,
            )
        self.assertEqual(result["result"], "PASS")

    def test_exact_successor_bytes_close_primary_and_secondary_bundles(self) -> None:
        digest = hashlib.sha256(b"authority").hexdigest()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            primary = bank_output_bundle(
                output("PRIMARY"), root / "primary", authorization_id="AUTH",
                package_attempt_id="PKG", consumer_event_id="PRIMARY",
                producer_measurement_sha256=digest, durable_start_sha256=digest,
                access_census_sha256=digest,
            )
            pa = primary["artifacts"]
            require_primary_terminal(
                pa["consumer_terminal"], hashlib.sha256(canonical_bytes(pa["result_terminal"])).hexdigest(),
                hashlib.sha256(canonical_bytes(pa["receipt"])).hexdigest(),
                hashlib.sha256(canonical_bytes(pa["manifest"])).hexdigest(),
            )
            secondary = bank_output_bundle(
                output("SECONDARY"), root / "secondary", authorization_id="AUTH",
                package_attempt_id="PKG", consumer_event_id="SECONDARY",
                producer_measurement_sha256=digest, durable_start_sha256=digest,
                access_census_sha256=digest,
            )
            self.assertEqual(primary["result"], "PASS")
            self.assertEqual(secondary["result"], "PASS")
            for role, bundle in (("PRIMARY", primary), ("SECONDARY", secondary)):
                records = bundle["artifacts"]["manifest"]["payloads"]
                self.assertEqual([record["observed_byte_count"] for record in records], [
                    payload_spec(role, "final_hidden").byte_count,
                    payload_spec(role, "final_normalized").byte_count,
                    payload_spec(role, "full_logits").byte_count,
                ])

    def test_mutable_or_wrong_geometry_output_rejects_before_banking(self) -> None:
        digest = "1" * 64
        for mutation in ("mutable", "short", "execution_count"):
            candidate = output("PRIMARY")
            if mutation == "mutable": candidate.final_hidden_payload = bytearray(candidate.final_hidden_payload)
            if mutation == "short": candidate.full_logits_payload = candidate.full_logits_payload[:-1]
            if mutation == "execution_count": candidate.core_execution_count = 2
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                with self.assertRaises(ResultEnvelopeError):
                    bank_output_bundle(candidate, Path(temporary), authorization_id="AUTH",
                        package_attempt_id="PKG", consumer_event_id="PRIMARY",
                        producer_measurement_sha256=digest, durable_start_sha256=digest,
                        access_census_sha256=digest)
                self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_primary_wrapper_calls_core_once(self) -> None:
        sentinel = object()
        with patch.object(primary_wrapper.primary_core, "execute_outputs", return_value=sentinel) as execute, \
                patch.object(primary_wrapper, "bank_output_bundle", return_value={"result":"PASS"}) as bank:
            result = primary_wrapper.execute_and_bank(object(), object(), 9703, Path("unused"),
                authorization_id="AUTH", package_attempt_id="PKG", consumer_event_id="PRIMARY",
                producer_measurement_sha256="1"*64, durable_start_sha256="2"*64,
                access_census_sha256="3"*64)
        self.assertEqual(result["result"], "PASS")
        execute.assert_called_once()
        bank.assert_called_once()
        self.assertIs(bank.call_args.args[0], sentinel)

    def test_secondary_gate_precedes_core_execution(self) -> None:
        with patch.object(secondary_wrapper.secondary_core, "execute_outputs") as execute:
            with self.assertRaises(ResultEnvelopeError):
                secondary_wrapper.execute_and_bank({}, Path("unused"), authorization_id="AUTH",
                    package_attempt_id="PKG", consumer_event_id="SECONDARY",
                    producer_measurement_sha256="1"*64, durable_start_sha256="2"*64,
                    access_census_sha256="3"*64, primary_terminal={},
                    primary_result_terminal_sha256="4"*64,
                    primary_receipt_sha256="5"*64, primary_manifest_sha256="6"*64)
        execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
