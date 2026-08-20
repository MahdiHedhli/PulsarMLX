from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
VALIDATOR_PATH = ROOT / "scripts/research/validate_f017_representative_routed_aggregate_single_use_release_v1.py"
RELEASE_PATH = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-routed-aggregate-single-use-release-v1.json"
spec = importlib.util.spec_from_file_location("release_validator", VALIDATOR_PATH)
validator = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(validator)


class RoutedAggregateReleaseValidatorTests(unittest.TestCase):
    def setUp(self):
        self.release = validator.load(RELEASE_PATH)

    def reject(self, mutation):
        candidate = copy.deepcopy(self.release)
        mutation(candidate)
        with self.assertRaises((validator.ValidationError, KeyError, TypeError)):
            validator.validate(candidate, repo=False)

    def test_repository_release_passes(self):
        validator.validate(copy.deepcopy(self.release), repo=True)

    def test_load_bearing_mutations_reject(self):
        mutations = [
            lambda d: d.__setitem__("authoritative_execution_code_head", "0" * 40),
            lambda d: d["bindings"]["authorization"].__setitem__("sha256", "0" * 64),
            lambda d: d["bindings"]["arithmetic_contract"].__setitem__("sha256", "0" * 64),
            lambda d: d["bindings"]["executor"].__setitem__("sha256", "0" * 64),
            lambda d: d["bindings"]["final_independent_review"].__setitem__("sha256", "0" * 64),
            lambda d: d["bindings"]["expert_output_reuse_authorization"].__setitem__("sha256", "0" * 64),
            lambda d: d["bindings"]["path_contract"].__setitem__("sha256", "0" * 64),
            lambda d: d["bindings"]["publication_contract"].__setitem__("sha256", "0" * 64),
            lambda d: d["bindings"]["release_wrapper"].__setitem__("sha256", "0" * 64),
            lambda d: d["bindings"]["terminalizer"].__setitem__("sha256", "0" * 64),
            lambda d: d["bindings"]["release_rehearsal"].__setitem__("sha256", "0" * 64),
            lambda d: d.__setitem__("private_manifest_sha256", "0" * 64),
            lambda d: d["atomic_id_weight_output_triples"][3].__setitem__("expert_id", 73),
            lambda d: d["atomic_id_weight_output_triples"][3].__setitem__("routing_weight", d["atomic_id_weight_output_triples"][4]["routing_weight"]),
            lambda d: d["atomic_id_weight_output_triples"][3].__setitem__("output_sha256", d["atomic_id_weight_output_triples"][4]["output_sha256"]),
            lambda d: d["atomic_id_weight_output_triples"].reverse(),
            lambda d: d["machine_local_paths"].__setitem__("state_root", "/tmp/alternate"),
            lambda d: d["machine_local_paths"].__setitem__("output", "/tmp/output"),
            lambda d: d["machine_local_paths"].__setitem__("approval", "/tmp/approval"),
            lambda d: d["single_use"].__setitem__("retry", True),
            lambda d: d["single_use"].__setitem__("resume", True),
            lambda d: d["single_use"].__setitem__("second_attempt", True),
            lambda d: d["single_use"].__setitem__("exclusive_attempt_creation", False),
            lambda d: d["single_use"].__setitem__("aggregate_execution_counted_at", "OUTPUT_PUBLICATION"),
            lambda d: d["output_publication"].__setitem__("overwrite", True),
            lambda d: d["output_publication"].__setitem__("no_replace_hard_link_publish", False),
            lambda d: d["output_publication"].__setitem__("descriptor_relative_temp_creation", False),
            lambda d: d["output_publication"].__setitem__("authority_requires_matching_complete_terminal", False),
            lambda d: d["output_publication"].__setitem__("byte_length", 49151),
            lambda d: d["output_publication"].__setitem__("dtype", "little-endian-f32"),
            lambda d: d["reproduction"].__setitem__("synthetic_fresh_processes", 1),
            lambda d: d["accounting"].__setitem__("starting_ledger", 174),
            lambda d: d["accounting"].__setitem__("checkpoint_reads", 1),
            lambda d: d["accounting"].__setitem__("shard_opens", 1),
            lambda d: d["accounting"].__setitem__("expert_executions", 1),
            lambda d: d["accounting"].__setitem__("future_aggregate_executions", 2),
            lambda d: d["prohibitions"].__setitem__("shared_expert", False),
            lambda d: d["prohibitions"].__setitem__("ffn_completion", False),
            lambda d: d["prohibitions"].__setitem__("s2_construction", False),
            lambda d: d.__setitem__("stop_boundary", "AFTER_S2"),
            lambda d: d.__setitem__("approval_asserted", True),
            lambda d: d.__setitem__("real_event_authorized", True),
        ]
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index):
                self.reject(mutation)


if __name__ == "__main__":
    unittest.main()
