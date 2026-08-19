#!/usr/bin/env python3
"""Mutation tests for concrete representative M1-F0 route authority."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/research"))

from validate_f017_representative_m1f0_concrete_route_values_v1 import validate  # noqa: E402


EVIDENCE = ROOT / "docs/architecture/reviews/evidence/f017-representative-m1f0-concrete-route-values-v1.json"


class ConcreteRouteValuesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    def test_committed_evidence_passes(self) -> None:
        self.assertEqual(validate(copy.deepcopy(self.document)), [])

    def reject(self, mutate) -> None:
        document = copy.deepcopy(self.document)
        mutate(document)
        self.assertTrue(validate(document))

    def test_mutations_reject(self) -> None:
        mutations = [
            lambda d: d["authoritative_execution"].__setitem__("ledger", 166),
            lambda d: d["authoritative_execution"].__setitem__("checkpoint_rereads_after_event", 1),
            lambda d: d["reconstruction"].__setitem__("shard_opens", 1),
            lambda d: d["reconstruction"].__setitem__("producer_sha256", "0" * 64),
            lambda d: d["reconstruction"].__setitem__("direct_dprefix_route_used", True),
            lambda d: d["selected_ids"]["values"].__setitem__(0, 166),
            lambda d: d["selected_ids"].__setitem__("dtype", "uint32_le"),
            lambda d: d["routing_weights"]["values"].__setitem__(0, 0.0),
            lambda d: d["routing_weights"].__setitem__("bytes_hex", "00" * 64),
            lambda d: d["id_weight_pairs"][0].__setitem__("expert_id", 10),
            lambda d: d["id_weight_pairs"][0].__setitem__("ordinal", 1),
            lambda d: d["ranking_authority"].__setitem__("order", "expert id only"),
            lambda d: d["route_identity"].__setitem__("sha256", "0" * 64),
            lambda d: d["reproduction_linkage"].__setitem__("runs", 9),
            lambda d: d["surface_separation"].__setitem__("direct_dprefix_values_consumed", True),
            lambda d: d["future_use"].__setitem__("expert_execution_authorized", True),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.reject(mutation)


if __name__ == "__main__":
    unittest.main()
