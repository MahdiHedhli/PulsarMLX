#!/usr/bin/env python3
"""Real launch-to-capture failure-diagnostic composition oracles."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
import ci_campaign as ci
import q_capture

SOURCE=Path(__file__).resolve().parents[1]

class FailureDiagnostic(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.graph=Path(self.tmp.name).resolve()
        (self.graph/'tmp').mkdir();(self.graph/'cache').mkdir()
        self.env=q_capture.clean_env(self.graph)
    def tearDown(self):self.tmp.cleanup()
    def child(self,body):return [sys.executable,'-I','-B','-c',body]
    def failure(self,name,body,**options):
        with self.assertRaisesRegex(RuntimeError,'^CAMPAIGN_FAILED: ') as caught:
            ci.launch(self.child(body),SOURCE,self.env,self.graph/name,options.pop('seconds',10),**options)
        return json.loads(str(caught.exception).split(': ',1)[1])
    def test_nonzero_real_capture_has_joined_bounded_diagnostic(self):
        body="import os;os.write(2,b'x'*5000+b'\\xff\\x00END');raise SystemExit(7)"
        row=self.failure('nonzero',body)
        expected=b'x'*5000+b'\xff\x00END'
        self.assertEqual(row['terminal']['code'],7);self.assertTrue(row['terminal']['reaped'])
        self.assertEqual(row['diagnostic']['status'],'AVAILABLE');self.assertEqual(row['diagnostic']['bytes'],len(expected))
        self.assertEqual(row['diagnostic']['sha256'],hashlib.sha256(expected).hexdigest())
        self.assertTrue(row['diagnostic']['excerpt_truncated']);self.assertNotIn('\ufffd',row['diagnostic']['excerpt'])
    def test_spawn_failures_keep_primary_terminal(self):
        cases=[('missing-command',['/definitely/absent/serving-aj']),('missing-cwd',self.child('pass'))]
        for name,command in cases:
            output=self.graph/name;cwd=SOURCE if name=='missing-command' else self.graph/'absent'
            with self.subTest(name=name),self.assertRaisesRegex(RuntimeError,'^CAMPAIGN_FAILED: ') as caught:
                ci.launch(command,cwd,self.env,output,10)
            row=json.loads(str(caught.exception).split(': ',1)[1])
            self.assertEqual(row['terminal']['status'],'SPAWN_ERROR');self.assertTrue(row['terminal']['reaped'])
            self.assertEqual(row['diagnostic']['status'],'AVAILABLE');self.assertEqual(row['diagnostic']['bytes'],0)
    def test_permission_error_cannot_mask_terminal(self):
        original_open=ci.os.open
        def denied(path,*args,**kwargs):
            if path=='stderr.raw':raise PermissionError('inert denied artifact')
            return original_open(path,*args,**kwargs)
        def provider(output,terminal):
            with patch.object(ci.os,'open',side_effect=denied):return ci.failure_diagnostic(output,terminal)
        row=self.failure('denied',"raise SystemExit(9)",diagnostic_provider=provider)
        self.assertEqual(row['terminal']['code'],9);self.assertTrue(row['terminal']['reaped'])
        self.assertEqual(row['diagnostic'],{'status':'UNAVAILABLE','error_type':'PermissionError'})
    def test_unexpected_diagnostic_provider_error_cannot_mask_terminal(self):
        def broken(*_):raise RuntimeError('inert provider defect')
        row=self.failure('provider-defect',"raise SystemExit(10)",diagnostic_provider=broken)
        self.assertEqual(row['terminal']['code'],10);self.assertTrue(row['terminal']['reaped'])
        self.assertEqual(row['diagnostic'],{'status':'UNAVAILABLE','error_type':'RuntimeError'})
    def test_missing_and_substituted_artifacts_are_refused(self):
        def provider(kind):
            def mutate(output,terminal):
                raw=Path(output)/'stderr.raw';raw.unlink()
                if kind=='symlink':raw.symlink_to(Path(output)/'stdout.raw')
                elif kind=='directory':raw.mkdir()
                return ci.failure_diagnostic(output,terminal)
            return mutate
        for kind,error in [('missing','FileNotFoundError'),('symlink','OSError'),('directory','ArtifactNotOwnedPrivateRegular')]:
            with self.subTest(kind=kind):
                row=self.failure(kind,"raise SystemExit(11)",diagnostic_provider=provider(kind))
                self.assertEqual(row['terminal']['code'],11);self.assertEqual(row['diagnostic']['status'],'UNAVAILABLE')
                self.assertEqual(row['diagnostic']['error_type'],error)
    def test_output_alias_escape_is_refused(self):
        alias=self.graph/'alias'
        def aliased(output,terminal):
            alias.symlink_to(output,target_is_directory=True)
            return ci.failure_diagnostic(alias,terminal)
        row=self.failure('canonical',"raise SystemExit(12)",diagnostic_provider=aliased)
        self.assertEqual(row['terminal']['code'],12);self.assertEqual(row['diagnostic']['error_type'],'OutputNotCanonical')
    def test_truncated_capture_marks_incomplete_digest_scope(self):
        row=self.failure('truncated',"import os;os.write(2,b'z'*4096);raise SystemExit(13)",capture_limit=32)
        self.assertEqual(row['terminal']['status'],'EVIDENCE_INCOMPLETE');self.assertTrue(row['terminal']['reaped'])
        self.assertEqual(row['diagnostic']['status'],'AVAILABLE');self.assertEqual(row['diagnostic']['bytes'],32)
        self.assertTrue(row['diagnostic']['digest_complete']);self.assertFalse(row['diagnostic']['capture_complete'])
    def test_timeout_keeps_reaped_terminal_and_partial_scope(self):
        row=self.failure('timeout',"import os,time;os.write(2,b'before-timeout');time.sleep(10)",seconds=0.15)
        self.assertTrue(row['terminal']['timeout']);self.assertTrue(row['terminal']['reaped'])
        self.assertEqual(row['diagnostic']['status'],'AVAILABLE');self.assertFalse(row['diagnostic']['capture_complete'])
    def test_capacity_and_terminal_mismatch_are_refused(self):
        output=self.graph/'direct';terminal=q_capture.capture(self.child("import os;os.write(2,b'abcd');raise SystemExit(14)"),str(SOURCE),self.env,output,timeout=10)
        self.assertEqual(ci.failure_diagnostic(output,terminal,capacity=3)['error_type'],'ArtifactCapacityExceeded')
        altered=dict(terminal);altered['stream_bytes']=dict(terminal['stream_bytes']);altered['stream_bytes']['stderr']=99
        self.assertEqual(ci.failure_diagnostic(output,altered)['error_type'],'TerminalEvidenceMismatch')

if __name__=='__main__':unittest.main()
