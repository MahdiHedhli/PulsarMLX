"""Synthetic lifecycle composition; never opens campaign claims or model payloads.

Process/channel/census doubles exercise the real Lease.finish and end_owned.
The grade composition mocks admission, policy, sandbox launch and runtime receipts;
sealing, hashes, grade-intent exclusivity, grade_original and the 45-layer grader
run on temporary synthetic bytes. Physical watchdog/gate evidence is separate.
"""
from contextlib import ExitStack
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

import studio019_supervise as s
import studio019_grade as grade
from test_studio019_grade import synthetic, GEOMETRY


class Process:
    def __init__(self, pid, code=None):
        self.pid, self.returncode = pid, code
        self.waited = False
    def poll(self): return self.returncode
    def wait(self, timeout=None):
        if self.returncode is None: raise subprocess.TimeoutExpired('fixture', timeout)
        self.waited = True
        return self.returncode
    def kill(self): self.returncode = -signal.SIGKILL


class AbortReap(unittest.TestCase):
    def abort(self, code=7, survivors=False, unreaped=False):
        worker, watcher = Process(101, code), Process(102)
        channel = Mock()
        def abort(message):
            self.assertEqual(message, b'X')
            worker.returncode = code if code is not None else -signal.SIGKILL
            watcher.returncode = -signal.SIGKILL
        channel.sendall.side_effect = abort
        lease = s.Lease(channel, watcher, worker.pid, 100)
        if unreaped:
            watcher.wait = Mock(side_effect=subprocess.TimeoutExpired('fixture', 0))
        with patch.object(s, 'members', return_value=[999] if survivors else []), \
             patch.object(s.time, 'monotonic', side_effect=[0, 3] if survivors else None):
            result = s.end_owned(worker, lease, False)
        return result, worker, watcher

    def test_nonzero_exit_positive_waits(self):
        result, worker, watcher = self.abort()
        self.assertEqual(result, (False, True))
        self.assertTrue(worker.waited and watcher.waited)
        self.assertEqual((worker.returncode, watcher.returncode), (7, -9))

    def test_monitor_or_timeout_abort_positive_waits(self):
        result, worker, watcher = self.abort(None)
        self.assertEqual(result, (False, True))
        self.assertEqual((worker.returncode, watcher.returncode), (-9, -9))
        self.assertTrue(worker.waited and watcher.waited)

    def test_survivor_or_unreaped_watcher_stays_false(self):
        self.assertEqual(self.abort(survivors=True)[0], (False, False))
        self.assertEqual(self.abort(unreaped=True)[0], (False, False))

    def test_mismatched_and_failed_lease_stay_false(self):
        worker = Process(101, 7)
        lease = Mock(group=202)
        self.assertEqual(s.end_owned(worker, lease, False), (False, False))
        lease.finish.assert_not_called()
        lease.group = 101
        lease.finish.side_effect = RuntimeError('failed lease')
        self.assertEqual(s.end_owned(worker, lease, False), (False, False))

    def test_success_keeps_existing_finish_result(self):
        worker = Process(101, 0)
        lease = Mock(group=101)
        lease.finish.return_value = (False, True)
        self.assertEqual(s.end_owned(worker, lease, True), (False, True))
        lease.finish.assert_called_once_with(worker, True, s.members)


class GradeComposition(unittest.TestCase):
    def test_failed_run_handler_seals_and_requests_grade_only_after_positive_reap(self):
        for clean in (False, True):
            with self.subTest(clean=clean), tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
                root = Path(tmp).resolve(); d = root/'native'; out = d/'output'
                ref = root/'reference'; ref.mkdir()
                s.put(ref/'numeric-exit.json', {'seconds':1})
                resource = root/'resource.json'; s.put(resource, {'whole_seconds':100})
                claim = root/'synthetic-claim.json'; s.put(claim, {'operation':'op'})
                config = {'resource':str(resource)}; envelope = {'limits':{'timeout':10,'output_bytes':1024}}
                for name, value in [('load_cfg',config),('verified',(envelope,{})),('envelope',envelope),('admission',{})]:
                    stack.enter_context(patch.object(s, name, return_value=value))
                stack.enter_context(patch.object(s, 'lifecycle_gate'))
                stack.enter_context(patch.object(s, 'STATE', root))
                stack.enter_context(patch.object(s, 'ANCHORS', {'native':claim}))
                stack.enter_context(patch.object(s, 'layout', side_effect=lambda c,r: (d,out,d/'cap') if r=='native' else (ref,ref/'output',ref/'cap')))
                def fail(*args):
                    d.mkdir(); out.mkdir(mode=0o700); (out/'00.state.offset.f32').write_bytes(b'\0'*4)
                    s.put(d/'numeric-exit.json', {'clean_reap':clean})
                    raise RuntimeError('fixture native failed')
                stack.enter_context(patch.object(s, 'run_locked', side_effect=fail))
                request = stack.enter_context(patch.object(s, 'grade_original'))
                with self.assertRaisesRegex(RuntimeError, 'fixture native failed'):
                    s.run_numeric('synthetic', 'native', True)
                self.assertEqual((d/'partial-sealed.json').exists(), clean)
                self.assertEqual(request.call_count, int(clean))
                if clean:
                    self.assertFalse(s.doc(d/'partial-sealed.json')['complete'])
                    out.chmod(0o700)

    def test_partial_seal_grade_and_exclusive_replay_and_headroom(self):
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            root = Path(tmp).resolve(); native = root/'native'; native.mkdir(mode=0o700)
            out = native/'output'; refdir = root/'reference'; refdir.mkdir(mode=0o700)
            reference = refdir/'output'
            synthetic(reference, 'reference'); synthetic(out, 'native')
            stack.callback(reference.chmod, 0o700); stack.callback(out.chmod, 0o700)
            out.chmod(0o700); (out/'00.state.offset.f32').unlink()
            claim = root/'synthetic-claim.json'; s.put(claim, {'synthetic': True})
            s.put(native/'numeric-exit.json', dict(operation='op', clean_reap=True, exit=7, completed=False))
            seal = dict(operation='op', claim_sha256=s.digest(claim),
                        exit_sha256=s.digest(native/'numeric-exit.json'), complete=False,
                        files=s.output_seal(out, 1<<20, True, False))
            s.put(native/'partial-sealed.json', seal)
            resource = root/'resource.json'; s.put(resource, {'native': {'output_bytes':1<<20,'combined':2*s.GIB}})
            config = dict(repo=str(s.SELF.parents[2]), source={'head':'synthetic'}, resource=str(resource),
                          stages={'reference':{'python':'synthetic-python'}})
            def layout(c, role):
                d = native if role=='native' else refdir
                return d, d/'output', d/'cap'
            # Custody/admission boundaries are replaced; no real anchor is read.
            for name in ('lifecycle_gate','audit_consumed_stage','original_reference'):
                stack.enter_context(patch.object(s, name))
            stack.enter_context(patch.object(s, 'layout', side_effect=layout))
            stack.enter_context(patch.object(s, 'ANCHORS', {'native':claim}))
            stack.enter_context(patch.object(s, 'source', return_value=config['source']))
            stack.enter_context(patch.object(s, 'grading_inputs', return_value={'synthetic':True}))
            stack.enter_context(patch.object(s, 'grade_content_verified', return_value={'synthetic':True}))
            stack.enter_context(patch.object(s, 'python_policy', return_value=({'path':'policy','sha256':'hash'}, {'interpreter':'python'})))
            cache = stack.enter_context(patch.object(s.pyg, 'fresh_cache'))
            stack.enter_context(patch.object(s.pyg, 'cli', return_value=['synthetic']))
            stack.enter_context(patch.object(s.pyg, 'checked_receipt', return_value='synthetic-runtime'))
            stack.enter_context(patch.object(s, 'aux_profile_file', return_value=root/'sandbox'))
            stack.enter_context(patch.object(s, 'pressure', return_value={'pressure':1,'headroom':18*s.GIB-1}))
            with self.assertRaisesRegex(ValueError, 'grade admission headroom'):
                s.grade_original(config, 'native')
            cache.assert_not_called()
            self.assertFalse((native/'grade-intent.json').exists())
            stack.enter_context(patch.object(s, 'pressure', return_value={'pressure':1,'headroom':18*s.GIB}))
            worker = Process(101, 0); watcher = Process(102, 0)
            stack.enter_context(patch.object(s, 'attach_guard', return_value=Mock(guard=watcher, receipt=lambda: {})))
            stack.enter_context(patch.object(s, 'end_owned', return_value=(False,True)))
            def launch(*args, **kwargs):
                stack.callback(os.close, os.dup(kwargs['pass_fds'][0]))
                with patch.object(grade.original, 'REAL', GEOMETRY):
                    result = grade.grade_pair(reference, out)
                kwargs['stdout'].write(s.enc(result)); kwargs['stdout'].flush()
                return worker
            stack.enter_context(patch.object(s.subprocess, 'Popen', side_effect=launch))
            result = s.grade_original(config, 'native')
            self.assertFalse(result['complete']); self.assertFalse(result['qualified'])
            self.assertIsNone(result['stages']['00.state.offset.f32'])
            self.assertEqual(result['stages']['logits.f32']['outside'], 0)
            self.assertFalse(s.doc(native/'grade.json')['native_stage_complete'])
            with self.assertRaises(FileExistsError): s.grade_original(config, 'native')


if __name__ == '__main__': unittest.main()
