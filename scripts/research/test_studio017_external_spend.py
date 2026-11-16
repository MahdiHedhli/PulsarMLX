"""Synthetic SSHSIG and issuer transaction controls. No checkpoint or real stage inputs."""
import base64
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest

import studio017_authority as auth
import studio017_issuer_spend as issuer
from studio017_guard import enc, sha


class ExternalSpend(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.key = self.root / "fixture-key"
        subprocess.run(["/usr/bin/ssh-keygen", "-t", "ed25519", "-N", "", "-C",
                        "synthetic-control-only", "-f", str(self.key)], check=True, capture_output=True)
        self.public = " ".join(self.key.with_suffix(".pub").read_text().split()[:2])
        self.assertNotEqual(self.public, auth.PUBLIC_KEY)
        self.grant, self.pointer = self.binding("reference")
        self.db = self.root / "custodian.sqlite"
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute(issuer.TABLE)
            conn.execute("INSERT INTO attempts VALUES (?, ?, NULL)",
                         (auth.slot("reference"), self.pointer["sha256"]))
            conn.commit()

    @staticmethod
    def binding(stage, source="b"*40, run="a"*64):
        grant = dict(schema=auth.GRANT_SCHEMA, attempt="initial", stage=stage,
                     authority=auth.authority_binding(stage), run=run,
                     source=dict(head=source, tree="d"*40), fixture=True)
        pointer = dict(commit="c"*40, path="test-control/"+stage, sha256=sha(enc(grant)))
        return grant, pointer

    def sign_fixture(self, message, namespace=auth.NAMESPACE):
        return subprocess.run(["/usr/bin/ssh-keygen", "-Y", "sign", "-f", str(self.key),
                               "-n", namespace], input=message, check=True,
                              capture_output=True).stdout

    def query(self, operation="1"*32):
        return auth.live_challenge(self.grant, self.pointer, operation)

    def consume(self, challenge):
        return issuer.commit_spend(self.db, self.grant, self.pointer, challenge)

    def test_pinned_identity_and_unsigned_or_worker_grants(self):
        wire_key = base64.b64decode(auth.PUBLIC_KEY.split()[1], validate=True)
        fingerprint = base64.b64encode(hashlib.sha256(wire_key).digest()).decode().rstrip("=")
        self.assertEqual("SHA256:"+fingerprint, auth.FINGERPRINT)
        message = enc(self.grant)
        signature = self.sign_fixture(message)
        auth._verify_ssh(message, signature, self.public)
        for invalid in (b"", b"unsigned", signature):
            with self.subTest(invalid=invalid[:8]), self.assertRaises(ValueError):
                auth.verify_supervisor(message, invalid)

    def test_wrong_signature_message_namespace_source_and_role(self):
        original = enc(self.grant)
        sig = self.sign_fixture(original)
        for message, signature in [(original, self.sign_fixture(original, "synthetic.other")),
                                   (original+b" ", sig), (enc(self.binding("native")[0]), sig),
                                   (enc(self.binding("reference", source="2"*40)[0]), sig)]:
            with self.assertRaisesRegex(ValueError, "signature"):
                auth._verify_ssh(message, signature, self.public)
        for field in ("slot", "source", "grant_sha256", "tree", "grant_commit", "run"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.consume(dict(self.query(), **{field:"x"}))
        self.consume(self.query())

    def test_lost_local_state_rejects_old_receipt_and_new_request(self):
        # The issuer DB lives outside both simulated worker lifetimes.
        with tempfile.TemporaryDirectory(dir=self.root) as first_worker:
            first = self.query()
            statement = self.consume(first)
            signature = self.sign_fixture(statement)
            auth._verify_ssh(auth.spend_statement(first), signature, self.public)
            (Path(first_worker)/"spent").write_bytes(signature)
        with tempfile.TemporaryDirectory(dir=self.root):
            second = self.query(operation=first["operation"])  # same run, source, role and operation
            self.assertNotEqual(first["nonce"], second["nonce"])
            with self.assertRaisesRegex(ValueError, "signature"):
                auth._verify_ssh(auth.spend_statement(second), signature, self.public)
            for request in (first, second):
                with self.assertRaisesRegex(ValueError, "already spent"):
                    self.consume(request)
            for args in [dict(run="0"*64), dict(source="9"*40)]:
                grant, pointer = self.binding("reference", **args)
                with self.assertRaisesRegex(ValueError,"already spent"):
                    issuer.commit_spend(self.db, grant, pointer, auth.live_challenge(grant,pointer,"4"*32))

    def test_concurrent_distinct_requests_consume_only_once(self):
        def arrive(_):
            try:
                return self.consume(self.query())
            except ValueError:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(arrive, range(2)))
        self.assertEqual(sum(r is not None for r in results), 1)

    def test_missing_store_unenrolled_stage_and_lost_reply(self):
        with self.assertRaises(FileNotFoundError):
            issuer.commit_spend(self.root/"missing", self.grant, self.pointer, self.query())
        native, pointer = self.binding("native")
        with self.assertRaisesRegex(ValueError,"attempt unavailable"):
            issuer.commit_spend(self.db,native,pointer,auth.live_challenge(native,pointer,"2"*32))
        self.consume(self.query())  # discard reply after commit
        with self.assertRaisesRegex(ValueError,"already spent"):
            self.consume(self.query())
        with self.assertRaisesRegex(TimeoutError,"unconfirmed remote spend"):
            auth.consume_before_launch(self.root,self.grant,self.pointer,"7"*32,timeout=0)
        self.assertTrue((self.root/"remote-spend-challenge.json").exists())
        self.assertFalse((self.root/"remote-spend-verified.json").exists())
