#!/usr/bin/env python3
import argparse,json
from pathlib import Path
def main():
 p=argparse.ArgumentParser();p.add_argument("template",type=Path);p.add_argument("--expect-blocked",action="store_true");a=p.parse_args();d=json.loads(a.template.read_text())
 blocked=(d.get("executable_authority") is False and d.get("corrected_oracle_result") is None and d.get("acceptance_mode") is None and d.get("attempts")==1 and d.get("retries")==0 and d.get("resume") is False and d.get("mandatory_stop") is True and d.get("live_authorization_created") is False)
 if a.expect_blocked and not blocked: raise SystemExit("attempt-2 template did not fail closed")
 if not a.expect_blocked: raise SystemExit("template cannot instantiate before corrected oracle acceptance")
 print("PASS_BLOCKED");return 0
if __name__=="__main__": raise SystemExit(main())
