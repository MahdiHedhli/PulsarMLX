"""Host-only admission controls using genuine local history and synthetic mutations."""

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from scripts.research.tests import test_validate_evidence as fixtures

validator = fixtures.validator
ROOT = fixtures.REPOSITORY_ROOT


class ProtocolPublicViewTests(unittest.TestCase):
    def assert_rejected(self, operation, message):
        with self.assertRaises(validator.EvidenceValidationError) as caught:
            operation()
        self.assertEqual(caught.exception.code, "semantic_relationship")
        self.assertIn(message, str(caught.exception))

    @contextmanager
    def view_root(self, *, with_history=True):
        with tempfile.TemporaryDirectory(prefix="f002-public-view-test-") as temp:
            root = Path(temp).resolve()
            for name in [validator.FROZEN_PROTOCOL_PATH, validator.PROTOCOL_VIEW_ADMISSION_PATH]:
                destination = root / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, destination)
            if with_history:
                git_dir = subprocess.check_output(
                    ["git", "rev-parse", "--absolute-git-dir"], cwd=ROOT, text=True
                ).strip()
                # Read-only access to the existing objects, no new Git worktree/ref.
                (root / ".git").write_text("gitdir: " + git_dir + "\n")
                self.assertEqual(validator.frozen_protocol_digest(root), validator.FROZEN_PROTOCOL_SHA256)
            else:
                subprocess.run(["git", "init", "--quiet", str(root)], check=True)
            yield root

    def test_original_bytes_and_current_view_are_distinct_and_genuine(self):
        original = subprocess.check_output(
            ["git", "show", validator.FROZEN_PROTOCOL_SOURCE_COMMIT + ":" + validator.FROZEN_PROTOCOL_PATH],
            cwd=ROOT,
        )
        current = (ROOT / validator.FROZEN_PROTOCOL_PATH).read_bytes()
        self.assertNotEqual(original, current)
        self.assertEqual(hashlib.sha256(original).hexdigest(), validator.frozen_protocol_digest(ROOT))
        self.assertEqual(hashlib.sha256(current).hexdigest(), validator.PROTOCOL_VIEW_SHA256)
        self.assertNotEqual(validator.FROZEN_PROTOCOL_SHA256, validator.PROTOCOL_VIEW_SHA256)

    def test_historical_fixture_records_validate_without_any_relabeling(self):
        directory = ROOT / "fixtures/research/router-v1/evidence"
        for path in sorted(directory.glob("*.json")):
            with self.subTest(record=path.name):
                before = path.read_bytes()
                record = json.loads(before)
                original = deepcopy(record)
                self.assertNotIn("public_view", record["protocol"])
                validator.validate_record(record)
                self.assertEqual(record, original)
                self.assertEqual(path.read_bytes(), before)

    def test_retained_real_protocol_and_artifact_identities_remain_original(self):
        paths = sorted((ROOT / "docs/research/raw/002-router-parity").glob("f002-router-real-*.json"))
        self.assertEqual(len(paths), 4)
        for path in paths:
            before = path.read_bytes()
            record = json.loads(before)
            self.assertEqual(record["protocol"]["sha256"], validator.frozen_protocol_digest(ROOT))
            self.assertNotIn("public_view", record["protocol"])
            links = [a for a in record["artifacts"] if a["kind"] == "frozen_protocol"]
            self.assertEqual(len(links), 1)
            self.assertEqual(links[0]["sha256"], record["protocol"]["sha256"])
            validator._validate_artifacts(record, ROOT)
            self.assertEqual(before, path.read_bytes())

    def test_fresh_fixture_producer_declares_both_verified_representations(self):
        record = fixtures.valid_evidence("f002-public-view-fresh")
        protocol = record["protocol"]
        self.assertEqual(protocol, validator.fresh_protocol(ROOT))
        view = protocol["public_view"]
        self.assertEqual(view["sha256"], hashlib.sha256((ROOT / view["path"]).read_bytes()).hexdigest())
        self.assertEqual(view["source_commit"], validator.PROTOCOL_VIEW_SOURCE_COMMIT)
        self.assertEqual(view["original_source_commit"], validator.FROZEN_PROTOCOL_SOURCE_COMMIT)
        self.assertEqual(view["admission_sha256"], hashlib.sha256((ROOT / view["admission_path"]).read_bytes()).hexdigest())
        self.assertNotEqual(view["sha256"], protocol["sha256"])
        self.assertEqual(record["artifacts"][0]["sha256"], protocol["sha256"])
        validator.validate_record(record)

    def test_one_byte_current_view_tampering_refuses_despite_valid_history(self):
        with self.view_root() as root:
            path = root / validator.FROZEN_PROTOCOL_PATH
            before = path.read_bytes()
            changed = before + b" "
            self.assertNotEqual(changed, before)
            path.write_bytes(changed)
            self.assertEqual(validator._hash_historical_protocol(root, validator.FROZEN_PROTOCOL_SOURCE_COMMIT), validator.FROZEN_PROTOCOL_SHA256)
            self.assert_rejected(lambda: validator.frozen_protocol_digest(root), "public-view content identity")
            self.assert_rejected(lambda: validator.fresh_protocol(root), "public-view content identity")

    def test_production_sanitizer_emits_distinct_verified_public_view(self):
        from scripts.research.tests import test_sanitize_router_candidate as inputs

        candidate = inputs._abort_candidate()
        environment = inputs._combined_environment(candidate)
        records = inputs.sanitizer.build_public_records(
            candidate, environment,
            source_candidate_sha256="1" * 64,
            repository_root=ROOT,
        )
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["actual_status"], "aborted")
        self.assertEqual(record["protocol"], validator.fresh_protocol(ROOT))
        self.assertEqual(record["protocol"]["public_view"]["sha256"], validator.PROTOCOL_VIEW_SHA256)
        link = next(a for a in record["artifacts"] if a["kind"] == "frozen_protocol")
        self.assertEqual(link["sha256"], validator.FROZEN_PROTOCOL_SHA256)
        self.assertNotEqual(link["sha256"], record["protocol"]["public_view"]["sha256"])
        validator.validate_record(record)

    def test_scientific_text_changes_do_not_inherit_privacy_admission(self):
        with self.view_root() as root:
            path = root / validator.FROZEN_PROTOCOL_PATH
            before = path.read_bytes()
            self.assertIn(b"22002", before)
            changed = before.replace(b"22002", b"22003", 1)
            self.assertNotEqual(before, changed)
            path.write_bytes(changed)
            self.assert_rejected(lambda: validator.frozen_protocol_digest(root), "public-view content identity")

    def test_admission_source_path_disposition_and_hash_mutations_refuse(self):
        mutations = [
            ("original_method", "source_commit", "f" * 40),
            ("original_method", "path", "docs/research/MODEL_MANIFEST.json"),
            ("original_method", "sha256", validator.PROTOCOL_VIEW_SHA256),
            ("public_view", "sha256", validator.FROZEN_PROTOCOL_SHA256),
            ("privacy_relation", "disposition", "SCIENTIFIC_CHANGE"),
        ]
        for section, field, value in mutations:
            with self.subTest(section=section, field=field), self.view_root() as root:
                path = root / validator.PROTOCOL_VIEW_ADMISSION_PATH
                before = path.read_bytes()
                relation = json.loads(before)
                self.assertNotEqual(relation[section][field], value)
                relation[section][field] = value
                path.write_text(json.dumps(relation) + "\n")
                self.assertNotEqual(before, path.read_bytes())
                self.assert_rejected(lambda: validator.frozen_protocol_digest(root), "public-view admission identity")

    def test_missing_original_object_refuses_without_fetch_or_substitute(self):
        with self.view_root(with_history=False) as root:
            self.assertEqual(validator._admit_protocol_public_view(root)["sha256"], validator.PROTOCOL_VIEW_SHA256)
            probe = subprocess.run(["git", "cat-file", "-e", validator.FROZEN_PROTOCOL_SOURCE_COMMIT], cwd=root, capture_output=True)
            self.assertNotEqual(probe.returncode, 0)
            self.assert_rejected(lambda: validator.frozen_protocol_digest(root), "historical protocol bytes are unavailable")
            self.assert_rejected(lambda: validator.fresh_protocol(root), "historical protocol bytes are unavailable")

    def test_unknown_view_and_crossed_declarations_refuse(self):
        base = fixtures.valid_evidence()
        validator.validate_record(base)
        mutations = {
            "view_id": "unsupported-view",
            "sha256": validator.FROZEN_PROTOCOL_SHA256,
            "path": "docs/research/MODEL_MANIFEST.json",
            "source_commit": validator.FROZEN_PROTOCOL_SOURCE_COMMIT,
            "original_source_commit": validator.PROTOCOL_VIEW_SOURCE_COMMIT,
            "admission_sha256": "0" * 64,
            "admission_path": validator.FROZEN_PROTOCOL_PATH,
        }
        for field, value in mutations.items():
            with self.subTest(field=field):
                record = deepcopy(base)
                self.assertNotEqual(record["protocol"]["public_view"][field], value)
                record["protocol"]["public_view"][field] = value
                self.assert_rejected(lambda: validator.validate_record(record), "public-view declaration")

    def test_current_digest_cannot_be_relabelled_as_original_method(self):
        base = fixtures.valid_evidence()
        validator.validate_record(base)
        for field, value in [("sha256", validator.PROTOCOL_VIEW_SHA256), ("protocol_version", "1.3.0"), ("path", "docs/research/MODEL_MANIFEST.json")]:
            with self.subTest(field=field):
                record = deepcopy(base)
                self.assertNotEqual(record["protocol"][field], value)
                record["protocol"][field] = value
                self.assert_rejected(lambda: validator.validate_record(record), "protocol identity is invalid")

    def test_protocol_artifact_and_metadata_cross_bindings_refuse(self):
        base = fixtures.valid_evidence()
        validator.validate_record(base)
        for field, value in [("sha256", validator.PROTOCOL_VIEW_SHA256), ("path", "docs/research/MODEL_MANIFEST.json")]:
            with self.subTest(field=field):
                record = deepcopy(base)
                self.assertNotEqual(record["artifacts"][0][field], value)
                record["artifacts"][0][field] = value
                self.assert_rejected(lambda: validator._validate_artifacts(record, ROOT), "artifact content identity" if field == "sha256" else "protocol artifact identity")
                self.assert_rejected(lambda: validator.validate_record(record), "artifact content identity" if field == "sha256" else "protocol artifact identity")

    def test_non_protocol_artifact_corruption_keeps_original_exact_byte_check(self):
        record = fixtures.valid_evidence()
        validator.validate_record(record)
        before = deepcopy(record)
        record["artifacts"][1]["sha256"] = "0" * 64
        self.assertNotEqual(before, record)
        self.assert_rejected(lambda: validator.validate_record(record), "artifact content identity")

    def test_legacy_support_keeps_declared_source_and_refuses_new_annotation(self):
        record = fixtures.valid_evidence("f002-public-view-legacy")
        fresh_annotation = deepcopy(record["protocol"]["public_view"])
        record["evidence_schema_version"] = "1.1.0"
        record["payload_schema_version"] = "1.0.0"
        record["source_commit"] = fixtures.LEGACY_PROTOCOL_COMMIT
        record["protocol"] = {"protocol_id": validator.LEGACY_PROTOCOL_ID, "protocol_version": validator.LEGACY_PROTOCOL_VERSION, "path": validator.FROZEN_PROTOCOL_PATH, "sha256": validator.LEGACY_PROTOCOL_SHA256, "order_seed": validator.FROZEN_PROTOCOL_ORDER_SEED}
        record["artifacts"][0]["sha256"] = validator.LEGACY_PROTOCOL_SHA256
        validator.validate_record(record)
        record["protocol"]["public_view"] = fresh_annotation
        self.assert_rejected(lambda: validator.validate_record(record), "public-view declaration")


if __name__ == "__main__":
    unittest.main()
