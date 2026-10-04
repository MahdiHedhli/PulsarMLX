"""No numerical child: watchdog lifecycle and refusal evidence controls."""
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from f020_selected_process_v2 import owned_child


class Process(unittest.TestCase):
    def test_success_and_nonzero_are_distinct(self):
        root=Path(tempfile.mkdtemp(prefix='f020-process-host-'))
        good=owned_child([sys.executable,'-c','import time; time.sleep(.2)'],root/'good',128*1024*1024)
        self.assertEqual(good['status'],'PASS')
        bad=owned_child([sys.executable,'-c','import time; time.sleep(.2); raise SystemExit(7)'],root/'bad',128*1024*1024)
        self.assertEqual(bad['status'],'FAIL');self.assertEqual(bad['returncode'],7)

    def test_timeout_kills_only_owned_child(self):
        root=Path(tempfile.mkdtemp(prefix='f020-watchdog-host-'))
        receipt=owned_child([sys.executable,'-c','import time; time.sleep(10)'],root/'timeout',128*1024*1024,deadline=.2)
        self.assertEqual(receipt['status'],'FAIL');self.assertEqual(receipt['failure'],'deadline')
        self.assertEqual(receipt['post_wait_group_pids'],[])

    def test_sampled_rss_refusal(self):
        root=Path(tempfile.mkdtemp(prefix='f020-rss-host-'))
        receipt=owned_child([sys.executable,'-c','import time; x=bytearray(2000000); time.sleep(10)'],root/'rss',1)
        self.assertEqual(receipt['status'],'FAIL');self.assertEqual(receipt['failure'],'sampled RSS cap')


if __name__=='__main__':unittest.main()
