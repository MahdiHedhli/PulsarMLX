"""Host guard boundary tests. These do not invoke a campaign or access model files."""
import os, pathlib, subprocess, sys, unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from studio017_supervise import ha_ok,cleanup,pressure,GIB

class Resources(unittest.TestCase):
    def test_distinguish_reservation_pressure_swap_job_and_group(self):
        cap={'swap_samples':2,'combined':2*GIB,'job_rss':1664<<20};p={'pressure':1,'headroom':16*GIB}
        self.assertTrue(ha_ok(p,cap,p,1,2*GIB,cap['job_rss']))
        for ph,count,group,job in [(dict(p,pressure=2),0,12,1),(dict(p,headroom=16*GIB-1),0,12,1),(p,2,12,1),(p,0,2*GIB+1,1),(p,0,2*GIB,cap['job_rss']+1)]:
            self.assertFalse(ha_ok(ph,cap,p,count,group,job))

    def test_positive_owned_reap(self):
        proc=subprocess.Popen(['/bin/sleep','30'],start_new_session=True)
        left,clean=cleanup(proc)
        self.assertTrue(left and clean)
        self.assertLess(proc.returncode,0)
        with self.assertRaises(ProcessLookupError):os.killpg(proc.pid,0)

    def test_actual_host_sampling(self):
        facts=pressure()
        self.assertGreaterEqual(facts['headroom'],0)
        self.assertGreaterEqual(facts['swap'],0)
        self.assertIn(facts['pressure'],(1,2,4))

if __name__=='__main__':unittest.main()
