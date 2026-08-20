from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
VALIDATOR_PATH = ROOT / "scripts/research/validate_f017_representative_shared_expert_single_use_release_v1.py"
WRAPPER_PATH = ROOT / "scripts/research/f017_representative_shared_expert_release_wrapper_v1.py"
RELEASE_PATH = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-shared-expert-recovery-single-use-release-v1.json"


def module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


validator = module(VALIDATOR_PATH, "shared_release_validator")
wrapper = module(WRAPPER_PATH, "shared_release_wrapper")


class ReleaseContractTests(unittest.TestCase):
    def setUp(self):
        self.release = json.loads(RELEASE_PATH.read_text())

    def reject(self, mutate):
        candidate = copy.deepcopy(self.release)
        mutate(candidate)
        with self.assertRaises(Exception):
            validator.validate_release(candidate)

    def test_committed_release(self):
        validator.validate_release(self.release)

    def test_binding_mutations(self):
        mutations = [
            lambda d: d["bindings"]["authorization"].update(sha256="0" * 64),
            lambda d: d["bindings"]["authorization_review"].update(sha256="0" * 64),
            lambda d: d["bindings"]["executor"].update(sha256="0" * 64),
            lambda d: d["bindings"]["authorization_rehearsal"].update(sha256="0" * 64),
            lambda d: d.update(authoritative_execution_code_head="0" * 40),
            lambda d: d["representative_input"].update(sha256="0" * 64),
            lambda d: d["retained_parameters"][0].update(packed_sha256="0" * 64),
            lambda d: d["retained_parameters"][1].update(decoded_sha256="0" * 64),
            lambda d: d["retained_parameters"][2].update(quantization="Q5_K"),
            lambda d: d["retained_parameters"][2].update(packed_bytes=1),
        ]
        for mutation in mutations:
            self.reject(mutation)

    def test_output_and_one_shot_mutations(self):
        mutations = [
            lambda d: d["output_publication"].update(dtype="little-endian-f64"),
            lambda d: d["output_publication"].update(shape=[1]),
            lambda d: d["output_publication"].update(byte_length=1),
            lambda d: d["output_publication"].update(overwrite=True),
            lambda d: d["output_publication"].update(descriptor_readback=False),
            lambda d: d["single_use"].update(retry=True),
            lambda d: d["single_use"].update(resume=True),
            lambda d: d["single_use"].update(second_attempt=True),
            lambda d: d["single_use"].update(concurrent_invocation=True),
            lambda d: d["single_use"].update(attempts=2),
        ]
        for mutation in mutations:
            self.reject(mutation)

    def test_accounting_and_boundary_mutations(self):
        mutations = [
            lambda d: d["accounting"].update(starting_ledger=174),
            lambda d: d["accounting"].update(checkpoint_reads=1),
            lambda d: d["accounting"].update(shard_opens=1),
            lambda d: d["accounting"].update(future_shared_expert_executions=2),
            lambda d: d["accounting"].update(routed_aggregate_executions=1),
            lambda d: d["accounting"].update(ffn_completions=1),
            lambda d: d["accounting"].update(s2_constructions=1),
            lambda d: d.update(stop_boundary="AFTER_FFN"),
            lambda d: d["prohibitions"].update(historical_shared_output_substitution=False),
            lambda d: d["prohibitions"].update(checkpoint_access=False),
        ]
        for mutation in mutations:
            self.reject(mutation)

    def test_reproduction_and_path_mutations(self):
        mutations = [
            lambda d: d["reproduction"].update(runs=1),
            lambda d: d["reproduction"].update(fresh_processes=1),
            lambda d: d["reproduction"].update(exact_primary_output_identity="1_OF_2"),
            lambda d: d["reproduction"].update(checkpoint_reads=1),
            lambda d: d["machine_local_paths"].update(caller_selected_paths=True),
            lambda d: d["machine_local_paths"].update(attempt_state_root="/tmp/alternate"),
            lambda d: d["defense_in_depth_closeout"].update(D1="OPEN"),
            lambda d: d.update(real_event_authorized=True),
            lambda d: d.update(approval_asserted=True),
        ]
        for mutation in mutations:
            self.reject(mutation)

    def test_descriptor_relative_publication(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "output"
            root.mkdir(mode=0o700)
            os.chmod(root, 0o700)
            raw = (b"\x00\x00\x00\x00") * 6144
            identity = wrapper.publish_no_replace(raw, root)
            self.assertEqual(len(identity), 64)
            self.assertEqual((root / wrapper.OUTPUT_NAME).stat().st_mode & 0o777, 0o400)
            with self.assertRaises(Exception):
                wrapper.publish_no_replace(raw, root)


if __name__ == "__main__":
    unittest.main()
