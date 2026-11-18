"""Finite metadata and monotonic owner controls; never launches numerical work."""
import os
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest
import io
from contextlib import ExitStack
from unittest.mock import Mock, patch
from studio019_progress import Witnesses, ProgressDeadline, abort_channel, expected_sizes


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.out = Path(self.tmp.name)
        self.now = 10.; self.aborted = []
        self.guard = ProgressDeadline(7210., 300, lambda:self.now, lambda:self.aborted.append(True))
        self.guard.progress = 310.
        self.w = Witnesses(self.out, {'a.f32':4})

    def tearDown(self): self.tmp.cleanup()
    def write(self, name='a.f32', data=b'1234'):
        p=self.out/name; p.write_bytes(data); p.chmod(0o600); return p

    def test_authoritative_layout(self):
        from studio017_ref_grade import REAL, layout
        self.assertEqual(expected_sizes(), {k:v[2]*4 for k,v in layout(REAL).items()})
        self.assertEqual(len(expected_sizes()), 557)
        self.assertNotIn('report.json', expected_sizes())

    def test_stalled_healthy_heartbeat_and_boundary(self):
        for self.now in [20., 100., 309.999]:
            self.guard.observe(self.w)  # healthy polls do not renew
        self.now=310.
        with self.assertRaises(TimeoutError): self.guard.check()
        self.now=11.
        with self.assertRaises(TimeoutError): self.guard.check()
        self.assertTrue(self.guard.cancelled)

    def test_new_then_once_only(self):
        self.write(); self.now=100.
        self.assertEqual(self.guard.observe(self.w), [])
        self.now=101.; self.assertEqual(self.guard.observe(self.w), ['a.f32'])
        self.assertEqual(self.guard.progress,401.)
        self.now=200.; self.assertEqual(self.guard.observe(self.w), [])
        self.assertEqual(self.guard.progress,401.)

    def test_partial_unknown_and_mtime(self):
        p=self.write(data=b'1'); self.write('report.json'); self.write('unknown.f32')
        self.assertEqual(self.guard.observe(self.w), [])
        self.now=100.; os.utime(p,None)
        self.assertEqual(self.guard.observe(self.w), [])
        p.write_bytes(b'1234'); self.guard.observe(self.w)
        self.assertEqual(self.guard.observe(self.w), ['a.f32'])
        os.utime(p, ns=(p.stat().st_atime_ns,p.stat().st_mtime_ns+1))
        with self.assertRaises(RuntimeError): self.guard.observe(self.w)

    def test_replaced_partial_cannot_gain_credit(self):
        p=self.write(data=b'1'); self.w.observe()
        q=self.write('replacement'); os.replace(q,p)
        self.assertEqual(self.w.observe(),[]); self.assertEqual(self.w.observe(),[])

    def test_replayed_completed_name_refuses(self):
        p=self.write(); self.w.observe(); self.assertEqual(self.w.observe(),['a.f32'])
        replacement=self.write('replacement'); os.replace(replacement,p)
        with self.assertRaises(RuntimeError):self.w.observe()

    def test_symlink_preexisting_hardlink_and_mode(self):
        self.write('target'); (self.out/'a.f32').symlink_to(self.out/'target')
        self.assertEqual(self.w.observe(),[])
        with self.assertRaises(RuntimeError): Witnesses(self.out)
        (self.out/'a.f32').unlink(); os.link(self.out/'target',self.out/'a.f32')
        self.assertEqual(self.w.observe(),[])

    def test_wrong_mode_and_changed_full_metadata(self):
        p=self.write(); p.chmod(0o644)
        self.assertEqual(self.w.observe(),[])
        p.chmod(0o600)
        self.assertEqual(self.w.observe(),[])
        self.assertEqual(self.w.observe(),[])
        p.unlink()
        w=Witnesses(self.out,{'a.f32':4})
        p=self.write(); self.assertEqual(w.observe(),[])
        os.utime(p,ns=(p.stat().st_atime_ns,p.stat().st_mtime_ns+1))
        self.assertEqual(w.observe(),[])
        self.assertEqual(w.observe(),['a.f32'])

    def test_directory_replacement(self):
        alternate=self.out/'new'; alternate.mkdir()
        self.w.out=alternate
        with self.assertRaises(RuntimeError): self.w.observe()

    def test_commit_clock_boundary(self):
        samples=iter([309.999,310.001])
        guard=ProgressDeadline(7210.,300,lambda:next(samples))
        guard.progress=310.
        class Completed:
            def observe(self):return ['a.f32']
        with self.assertRaises(TimeoutError):guard.observe(Completed())
        self.assertEqual(guard.progress,310.)
        self.assertTrue(guard.cancelled)

    def test_slow_observation_and_total_precedence(self):
        guard=self.guard; test=self
        class Slow:
            def observe(self): test.now=310.; return ['a.f32']
        with self.assertRaises(TimeoutError): guard.observe(Slow())
        self.assertEqual(guard.progress,310.)
        guard=ProgressDeadline(20.,300,lambda:self.now)
        self.now=10.; guard.progress=310.; self.now=20.
        with self.assertRaises(TimeoutError): guard.check()

    def test_independent_thread_closes_channel_during_blocked_work(self):
        a,b=socket.socketpair()
        try:
            guard=ProgressDeadline(time.monotonic()+2,.06,abort=lambda:abort_channel(a))
            guard.release()
            # Represents main blocked in helper/source validation; no observe/check call.
            b.settimeout(1)
            self.assertEqual(b.recv(1),b'')
            self.assertTrue(guard.cancelled)
            with self.assertRaises(TimeoutError): guard.stop()
        finally:a.close();b.close()

    def test_thread_completion_cannot_erase_cancellation(self):
        self.guard.cancel('signal'); self.now=12.
        with self.assertRaises(TimeoutError):self.guard.observe(self.w)
        self.assertEqual(self.guard.reason,'signal')

    def test_monitor_source_or_ack_work_cannot_renew_after_expiry(self):
        import studio019_supervise as s
        for blocked in ('source','helper'):
            with self.subTest(blocked=blocked), ExitStack() as stack:
                self.now=10.; self.guard.cancelled=False; self.guard.reason=None
                cfg={'repo':'fixture','source':{'head':'head'},'checkpoint':str(self.out),'build_root':str(self.out)}
                limits={'swap_growth':1,'output_bytes':1024,'combined':1<<30,'job_rss':1<<30,'swap_samples':2}
                ph={'swap':0,'pressure':1,'headroom':32*s.GIB}
                begin=time.monotonic()
                mon=s.StageMonitor(cfg,self.out,self.out,io.BytesIO(),limits,ph,begin,begin+7200,self.guard,self.w)
                mon.last_source=begin-31 if blocked=='source' else begin
                def git(*args):
                    self.now=310.
                    return b'head' if 'rev-parse' in args else b''
                def ack():
                    if blocked=='helper':self.now=310.
                    return True
                stack.enter_context(patch.object(s,'git',side_effect=git))
                stack.enter_context(patch.object(s,'doc',return_value={}))
                stack.enter_context(patch.object(s,'pressure',return_value=ph))
                stack.enter_context(patch.object(s,'cohort',return_value=[]))
                stack.enter_context(patch.object(s,'census',return_value=(0,0)))
                stack.enter_context(patch.object(s,'path',side_effect=Path))
                with self.assertRaises(TimeoutError):mon.iteration(Mock(),Mock(pid=123),ack)
                self.assertTrue(self.guard.cancelled)
                self.assertEqual(self.guard.progress,310.)

if __name__ == '__main__': unittest.main()
