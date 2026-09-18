"""Offline (stdlib) validation of the memory-pressure watchdog on synthetic samples and a harmless target: each trigger
(compressor growth, swap growth, critical pressure) fires at its frozen threshold inside the rolling window and not
below it; the target receives SIGTERM once; a target that exits on its own ends the watch; the status file records
the decision."""
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WD = ROOT / 'scripts/research/glm53_flash/dogfood/watchdog.py'


def samples(kind, n=14, step=5.0):
    out = []
    for i in range(n):
        s = {'t': 1000.0 + i * step, 'compressor_gib': 10.0, 'swap_used_mib': 500.0, 'free_pct': 60, 'free_gib': 2.0, 'active_gib': 40.0, 'wired_gib': 3.0, 'swapouts': 0}
        if kind == 'comp' and i >= 8:
            s['compressor_gib'] = 10.0 + 0.3 * (i - 7)          # +1.8 GiB by i=13 within 60 s -> trigger at i=11 (1.2 > 1.0)
        if kind == 'comp-slow' and i >= 1:
            s['compressor_gib'] = 10.0 + 0.05 * i                # +0.65 GiB over the window: no trigger
        if kind == 'swap' and i >= 6:
            s['swap_used_mib'] = 500.0 + 100.0 * (i - 5)         # +300 MiB at i=8 -> trigger
        if kind == 'pressure' and i == 5:
            s['free_pct'] = 4
        out.append(s)
    return out


class Watchdog(unittest.TestCase):
    def run_wd(self, kind, extra=()):
        d = tempfile.mkdtemp(); feed = os.path.join(d, 'feed.json'); json.dump(samples(kind), open(feed, 'w'))
        target = subprocess.Popen([sys.executable, '-c', 'import signal,time,sys\nsignal.signal(signal.SIGTERM, lambda *a: sys.exit(15))\ntime.sleep(60)'])
        try:
            p = subprocess.run([sys.executable, '-I', '-B', str(WD), '--pid', str(target.pid), '--status', os.path.join(d, 's.json'), '--log', os.path.join(d, 'l.jsonl'), '--synthetic', feed, *extra], capture_output=True, text=True, timeout=60)
            status = json.load(open(os.path.join(d, 's.json'))); log = [json.loads(l) for l in open(os.path.join(d, 'l.jsonl'))]
            return p.returncode, status, log, target
        finally:
            if target.poll() is None:
                target.send_signal(signal.SIGTERM)
            target.wait(10)

    def test_compressor_growth_triggers_within_window(self):
        rc, status, log, target = self.run_wd('comp')
        self.assertEqual(rc, 1); self.assertEqual(status['state'], 'TERMINATED'); self.assertIn('compressor', status['trigger'])
        self.assertEqual(target.returncode, 15, 'target did not get SIGTERM')
        self.assertEqual(sum(1 for e in log if e['event'] == 'trigger'), 1)
        self.assertAlmostEqual(status['rolling']['d_comp_gib'], 1.2, places=6)

    def test_slow_growth_does_not_trigger(self):
        rc, status, log, target = self.run_wd('comp-slow')
        self.assertEqual(rc, 0); self.assertEqual(status['state'], 'FEED_DONE'); self.assertLess(status['rolling']['d_comp_gib'], 1.0)
        self.assertFalse(any(e['event'] == 'trigger' for e in log))

    def test_swap_growth_triggers(self):
        rc, status, log, target = self.run_wd('swap')
        self.assertEqual(rc, 1); self.assertIn('swap', status['trigger']); self.assertEqual(target.returncode, 15)

    def test_pressure_signal_triggers(self):
        rc, status, log, target = self.run_wd('pressure')
        self.assertEqual(rc, 1); self.assertIn('memory_pressure', status['trigger'])

    def test_target_exit_ends_watch(self):
        d = tempfile.mkdtemp(); feed = os.path.join(d, 'feed.json'); json.dump(samples('comp'), open(feed, 'w'))
        target = subprocess.Popen([sys.executable, '-c', 'pass']); target.wait(10)
        p = subprocess.run([sys.executable, '-I', '-B', str(WD), '--pid', str(target.pid), '--status', os.path.join(d, 's.json'), '--log', os.path.join(d, 'l.jsonl'), '--synthetic', feed], capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0); self.assertEqual(json.load(open(os.path.join(d, 's.json')))['state'], 'TARGET_EXITED')

    def test_headroom_refusal_uses_real_host_numbers(self):
        """A ceiling larger than the machine is refused before any watch starts (the check runs on the live host)."""
        d = tempfile.mkdtemp()
        p = subprocess.run([sys.executable, '-I', '-B', str(WD), '--pid', str(os.getpid()), '--status', os.path.join(d, 's.json'), '--log', os.path.join(d, 'l.jsonl'), '--ceiling-gib', '100000'], capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 3); self.assertEqual(json.load(open(os.path.join(d, 's.json')))['state'], 'HEADROOM_REFUSED')


if __name__ == '__main__':
    unittest.main()
