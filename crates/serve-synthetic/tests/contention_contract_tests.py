#!/usr/bin/env python3
"""Execute independent adverse cases against actual SDK callables."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from aa_behavior_oracle import execute,load
HERE=Path(__file__).resolve().parent
CASES=['omitted_admission','swallowed_failure','premature_release','weakened_busy','lost_finally','metadata_failure_absence','genuine_busy','success_while_held','early_release','wrong_status','wrong_code','wrong_class','failure_before_admission','failure_after_admission','delayed_admission','cancellation','close_error']
class Contract(unittest.TestCase):
    def test_behavioral_cases(self):
        for case in CASES:
            with self.subTest(case=case):execute(case,load('sdk_'+case,HERE/'sdk_client.py'),load('member_'+case,HERE/'test_ci_campaign.py'))
if __name__=='__main__':unittest.main()
