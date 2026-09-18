"""Offline (stdlib) checks of the dogfood server's inference worker (graph 30): one generation at a time in FIFO order,
a hard queue bound, cancellation between yields that closes the generator, skip of jobs cancelled before they start,
and generator exceptions that reach only their own job while the worker keeps serving."""
import sys
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts/research/glm53_flash/dogfood'))
import serve_worker  # noqa: E402

BOUND = 10.0   # every wait in this file is bounded: a regression of the deadlock class fails instead of hanging


class Gen:
    """A generator factory that records its lifetime: started, items yielded, closed (GeneratorExit seen)."""
    def __init__(self, n, gate=None, fail_after=None, label='', delay=0.0):
        self.n, self.gate, self.fail_after, self.label, self.delay = n, gate, fail_after, label, delay
        self.started = threading.Event(); self.closed = threading.Event(); self.yielded = 0; self.active = threading.Event()

    def __call__(self):
        self.started.set()
        try:
            for i in range(self.n):
                if self.gate is not None:
                    self.gate.wait(BOUND)
                if self.delay:
                    time.sleep(self.delay)
                if self.fail_after is not None and i >= self.fail_after:
                    raise ValueError(f'{self.label}FAIL_AT_{i}')
                self.yielded += 1
                yield (self.label, i)
        finally:
            self.closed.set()
        return


class WorkerContract(unittest.TestCase):
    def setUp(self):
        self.worker = serve_worker.InferenceWorker(max_queue=3)

    def tearDown(self):
        self.worker.close()

    def test_mlx_not_imported(self):
        self.assertNotIn('mlx', sys.modules); self.assertNotIn('fastapi', sys.modules)

    def test_fifo_one_at_a_time(self):
        gate = threading.Event(); a, b = Gen(3, gate=gate, label='a'), Gen(2, label='b')
        ja, jb = self.worker.submit(a), self.worker.submit(b)
        self.assertTrue(a.started.wait(BOUND)); time.sleep(0.05)
        self.assertFalse(b.started.is_set(), 'second job started while the first owns the model')
        self.assertEqual(self.worker.stats()['pending'], 2); self.assertTrue(self.worker.stats()['busy'])
        gate.set()
        self.assertEqual(list(ja.results(timeout=BOUND)), [('a', 0), ('a', 1), ('a', 2)])
        self.assertEqual(list(jb.results(timeout=BOUND)), [('b', 0), ('b', 1)])
        self.assertTrue(ja.finished.wait(BOUND) and jb.finished.wait(BOUND))
        self.assertEqual((ja.outcome, jb.outcome), ('done', 'done'))
        self.assertTrue(a.closed.is_set() and b.closed.is_set())
        st = self.worker.stats(); self.assertEqual((st['completed'], st['pending'], st['busy']), (2, 0, False))

    def test_queue_bound_rejects_without_blocking(self):
        gate = threading.Event(); running = Gen(1, gate=gate)
        jobs = [self.worker.submit(running)] + [self.worker.submit(Gen(1)) for _ in range(2)]
        self.assertTrue(running.started.wait(BOUND))
        t0 = time.time()
        with self.assertRaises(serve_worker.QueueFull):
            self.worker.submit(Gen(1))
        self.assertLess(time.time() - t0, 1.0)
        self.assertEqual(self.worker.stats()['rejected'], 1)
        gate.set()
        for j in jobs:
            list(j.results(timeout=BOUND))
        self.assertEqual(self.worker.stats()['completed'], 3)
        self.worker.submit(Gen(1))    # room again after completion

    def test_cancel_mid_generation_closes_generator_and_frees_the_model(self):
        gate = threading.Event(); long = Gen(1000, gate=gate, label='long', delay=0.01); nxt = Gen(1, label='next')
        jl = self.worker.submit(long); jn = self.worker.submit(nxt)
        gate.set()
        first = next(jl.results(timeout=BOUND))
        self.assertEqual(first, ('long', 0))
        t0 = time.time(); jl.cancel()
        self.assertTrue(long.closed.wait(BOUND), 'generator not closed after cancel'); self.assertLess(time.time() - t0, 1.0)
        self.assertTrue(jl.finished.wait(BOUND)); self.assertEqual(jl.outcome, 'cancelled')
        self.assertLess(long.yielded, 1000)
        self.assertEqual(list(jn.results(timeout=BOUND)), [('next', 0)])
        st = self.worker.stats(); self.assertEqual((st['cancelled'], st['completed']), (1, 1))

    def test_cancel_before_start_skips_without_running(self):
        gate = threading.Event(); first = Gen(1, gate=gate); never = Gen(1, label='never')
        j1 = self.worker.submit(first); j2 = self.worker.submit(never)
        j2.cancel(); gate.set()
        list(j1.results(timeout=BOUND)); self.assertTrue(j2.finished.wait(BOUND))
        self.assertEqual(j2.outcome, 'skipped'); self.assertFalse(never.started.is_set())
        self.assertEqual(list(j2.results(timeout=BOUND)), [])
        self.assertEqual(self.worker.stats()['skipped'], 1)

    def test_generator_exception_reaches_its_job_only(self):
        bad = Gen(5, fail_after=2, label='bad'); good = Gen(2, label='good')
        jb = self.worker.submit(bad); jg = self.worker.submit(good)
        got = []
        with self.assertRaises(ValueError) as ctx:
            for item in jb.results(timeout=BOUND):
                got.append(item)
        self.assertEqual(got, [('bad', 0), ('bad', 1)]); self.assertIn('FAIL_AT_2', str(ctx.exception))
        self.assertTrue(bad.closed.is_set())
        self.assertEqual(list(jg.results(timeout=BOUND)), [('good', 0), ('good', 1)])
        st = self.worker.stats(); self.assertEqual((st['failed'], st['completed'], st['busy'], st['pending']), (1, 1, False, 0))

    def test_factory_exception_is_a_failed_job(self):
        def broken():
            raise RuntimeError('NO_GENERATOR')
        j = self.worker.submit(broken)
        with self.assertRaises(RuntimeError):
            list(j.results(timeout=BOUND))
        self.assertEqual(list(self.worker.submit(Gen(1)).results(timeout=BOUND)), [('', 0)])

    def test_custom_delivery_receives_terminal_marker(self):
        seen = []
        j = self.worker.submit(Gen(2, label='d'), deliver=seen.append)
        self.assertTrue(j.finished.wait(BOUND))
        self.assertEqual(seen, [('item', ('d', 0)), ('item', ('d', 1)), ('done', None)])
        with self.assertRaises(RuntimeError):
            list(j.results())


if __name__ == '__main__':
    unittest.main()
