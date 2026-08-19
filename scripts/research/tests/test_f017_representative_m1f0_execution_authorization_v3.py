from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
VALIDATOR = ROOT / "scripts/research/validate_f017_representative_m1f0_execution_authorization_v3.py"
SPEC = importlib.util.spec_from_file_location("f017_auth_v3", VALIDATOR)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RepresentativeM1F0AuthorizationV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.wrapper = MODULE.load(MODULE.AUTH)
        cls.candidate = MODULE.load(ROOT / cls.wrapper["authorization_candidate"]["path"])
        cls.reuse = MODULE.load(ROOT / cls.candidate["router_reuse_authorization"]["path"])
        cls.preopen = MODULE.load(ROOT / cls.candidate["preopen_preflight"]["path"])
        cls.reproduction = MODULE.load(ROOT / cls.candidate["reproduction_contract"]["path"])
        cls.rehearsal = MODULE.load(ROOT / cls.wrapper["synthetic_rehearsal"]["path"])
        cls.review = MODULE.load(ROOT / cls.wrapper["review_authority"]["path"])
        cls.stage = MODULE.load(ROOT / cls.candidate["stage_vocabulary"]["path"])
        cls.historical = MODULE.load(ROOT / cls.candidate["historical_hash_anchor"]["path"])

    def errors(self, mutate) -> list[str]:
        values = [copy.deepcopy(value) for value in (
            self.wrapper, self.candidate, self.reuse, self.preopen, self.reproduction,
            self.rehearsal, self.review, self.stage, self.historical,
        )]
        mutate(*values)
        return MODULE.validate_document(*values)

    def rejected(self, mutate, code: str | None = None) -> None:
        errors = self.errors(mutate)
        self.assertTrue(errors, "mutation unexpectedly accepted")
        if code is not None:
            self.assertIn(code, errors)

    def test_bound_package_passes(self) -> None:
        self.assertEqual([], MODULE.validate_paths())

    def test_wrong_authoritative_head(self) -> None:
        self.rejected(lambda w,c,*_: c["authoritative_repository"].update(commit_sha256="0"*40), "CANDIDATE_HEAD")

    def test_wrong_semantic_authorities(self) -> None:
        for key, code in (("representative_boundary_v3","BOUNDARY_HASH"),("semantic_graph_v2","SEMANTIC_GRAPH_HASH"),("epsilon_adjudication","EPSILON_AUTHORITY")):
            with self.subTest(key=key):
                self.rejected(lambda w,c,*_, key=key: c["semantic_authority"][key].update(sha256="0"*64), code)

    def test_router_consumer_mismatch(self) -> None:
        self.rejected(lambda w,c,r,*_: r["consumer"].update(consumer_id="legacy"), "REUSE_CONSUMER_MISMATCH")

    def test_reproduction_contract_mutations(self) -> None:
        cases = (
            (lambda r: r.update(reproduction_runs=9), "REPRODUCTION_COUNT"),
            (lambda r: r.update(checkpoint_rereads=1), "REPRODUCTION_ACCESS"),
            (lambda r: r.update(finite_checks_all_required_numeric_outputs=False), "REPRODUCTION_FINITE"),
            (lambda r: r.update(retained_authority_rehash_before_after=False), "REPRODUCTION_REHASH"),
            (lambda r: r.pop("producer"), "REPRODUCTION_PRODUCER"),
        )
        for mutate, code in cases:
            with self.subTest(code=code):
                self.rejected(lambda w,c,u,p,r,*_, mutate=mutate: mutate(r), code)

    def test_preopen_mutations(self) -> None:
        cases = (
            (lambda p: p["retained_authorities"].update(rule="REOPEN_BY_PATH"), "RETAINED_DESCRIPTOR"),
            (lambda p: p["decoder_gate"].update(eager_import_before_shard_open=False), "DECODER_EAGER_IMPORT"),
            (lambda p: p["ledger_authorities"][0].update(expected=165), "LEDGER_AUTHORITY"),
            (lambda p: p["storage"].update(required_free_bytes=1), "STORAGE_PREFLIGHT"),
            (lambda p: p["environment"].update(numpy="unbound"), "ENVIRONMENT_PIN"),
            (lambda p: p["shard"].update(opened_descriptor="REOPEN"), "SHARD_DESCRIPTOR"),
        )
        for mutate, code in cases:
            with self.subTest(code=code):
                self.rejected(lambda w,c,u,p,*_, mutate=mutate: mutate(p), code)

    def test_retain_before_receipt_and_terminalizer(self) -> None:
        self.rejected(lambda w,c,*_: c["read_contract"].update(durably_retain_before_receipt=False), "RETAIN_BEFORE_RECEIPT")
        self.rejected(lambda w,c,*_: c["crash_terminalizer"].pop("sha256"), "CRASH_TERMINALIZER")

    def test_hash_anchors_and_f32_identity(self) -> None:
        self.rejected(lambda w,c,*_: c["attention_payload_inventory"][1].update(packed_sha256="0"*64), "PACKED_SHA:blk.3.attn_q_a.weight")
        self.rejected(lambda w,c,*_: c["attention_payload_inventory"][3].update(decoded_sha256="0"*64), "DECODED_SHA:blk.3.attn_q_b.weight")
        self.rejected(lambda w,c,*_: c["attention_payload_inventory"][0].update(decoded_sha256="f"*64), "F32_IDENTITY:blk.3.attn_norm.weight")

    def test_s0_manifest_and_fallback(self) -> None:
        self.rejected(lambda w,c,*_: c["retained_inputs"][0].pop("private_manifest_sha256"), "S0_MANIFEST")
        self.rejected(lambda w,c,*_: c["retained_inputs"][2].update(checkpoint_fallback=True), "RETAINED_FALLBACK")

    def test_exact_failure_count_and_required_cases(self) -> None:
        self.rejected(lambda w,c,u,p,r,h,*_: h.update(failure_count=28), "FAILURE_COUNT")
        self.rejected(lambda w,c,u,p,r,h,*_: h["failure_rehearsals"].pop("restart_terminalizer"), "FAILURE_RESULTS")

    def test_review_binding(self) -> None:
        self.rejected(lambda w,*_: w["review_authority"].update(sha256="0"*64), "REVIEW_AUTHORITY")

    def test_wrong_stage_vocabulary(self) -> None:
        self.rejected(lambda w,c,u,p,r,h,v,s,*_: s["stages"][12].update(name="attention_residual"), "STAGE_VOCABULARY")

    def test_wrong_epsilon_and_expert_authority(self) -> None:
        self.rejected(lambda w,c,*_: c["execution_semantics"]["rmsnorm"].update(epsilon_source="f32(1e-6)"), "RMSNORM")
        self.rejected(lambda w,*_: w["authorization"].update(expert_execution_authorized=True), "EXPERT_AUTHORIZED")


if __name__ == "__main__":
    unittest.main()
