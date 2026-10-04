#!/usr/bin/env python3
"""Owned child watchdog; explicit sampled enforcement, not an OS hard RAM cap."""
import json
import os
from pathlib import Path
import signal
import subprocess
import time


def private_json(path,value):
    raw=(json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as f:
        f.write(raw);f.flush();os.fsync(f.fileno())


def group_pids(group):
    raw=subprocess.check_output(['/bin/ps','-axo','pgid=,pid='],text=True)
    result=[]
    for line in raw.splitlines():
        pg,pid=map(int,line.split())
        if pg==group:result.append(pid)
    return result


def owned_child(command,out,rss_limit,deadline=900,poll_seconds=0.1,env=None):
    """Only start after exact review validation; never restart a failed child."""
    out=Path(out);out.mkdir(mode=0o700,parents=False,exist_ok=False)
    def log(name):return os.fdopen(os.open(out/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb')
    maximum=0;samples=0;reason=None;started=time.monotonic();code=None
    with log('stdout.log') as stdout,log('stderr.log') as stderr:
        process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,
                                 start_new_session=True,env=env)
        try:
            while process.poll() is None:
                elapsed=time.monotonic()-started
                if elapsed>deadline:
                    reason='deadline';break
                sampled=subprocess.run(['/bin/ps','-o','rss=','-p',str(process.pid)],
                                       capture_output=True,text=True)
                if sampled.returncode==0 and sampled.stdout.strip():
                    rss=int(sampled.stdout.strip())*1024
                    maximum=max(maximum,rss);samples+=1
                    if rss>rss_limit:reason='sampled RSS cap';break
                elif process.poll() is None:
                    reason='RSS measurement unavailable';break
                time.sleep(poll_seconds)
            if reason:
                try: os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError: pass
            code=process.wait(timeout=10)
        except BaseException as error:
            reason=reason or ('supervisor error: '+type(error).__name__)
            if process.poll() is None:
                try: os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError: pass
            code=process.wait(timeout=10)
        finally:
            try:
                leftovers=group_pids(process.pid)
            except (OSError,subprocess.SubprocessError,ValueError):
                leftovers=None
                reason=reason or 'process census unavailable'
            if leftovers or leftovers is None:
                try: os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError: pass
                reason=reason or 'owned process-group leak'
            receipt={'schema':'pulsarmlx.selected-owned-child/2','pid':process.pid,
                'returncode':code,'failure':reason,'elapsed_seconds':time.monotonic()-started,
                'sampled_max_rss_bytes':maximum,'rss_cap_bytes':rss_limit,'samples':samples,
                'poll_seconds':poll_seconds,'deadline_seconds':deadline,
                'post_wait_group_pids':leftovers,'instantaneous_os_ram_cap':False,
                'status':'PASS' if code==0 and reason is None and not leftovers and samples>0 else 'FAIL'}
            private_json(out/'watchdog.json',receipt)
    return receipt
