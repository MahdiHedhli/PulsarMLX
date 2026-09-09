"""Owned-child RSS budget observation around the unchanged capture utility.

Darwin RSS setrlimit is not presumed to be an effective hard cap. This wrapper
samples only the capture's recorded child PID and checks completed-child peak
RSS. It is a bounded sampled stop rule, not instantaneous physical accounting.
"""
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import threading
import time

import f017_preparation_capture_v1 as cap

def capture(argv, area, label, env, **kwargs):
    key = Path(area)/'captures'/label
    stop = threading.Event(); rows = []; faults = []; budget = 1024**3
    ps_before = cap.image('/bin/ps')
    def observe():
        spawn = key/'spawn.json'
        deadline = time.monotonic()+kwargs.get('timeout',180)+30
        while not stop.wait(.1) and time.monotonic()<deadline:
            if not spawn.is_file():
                continue
            try:
                raw=spawn.read_bytes()
                if len(raw)>1024:
                    faults.append('SPAWN_RECORD_BOUND');return
                pid=json.loads(raw)['pid']
                if type(pid)is not int or pid<=1:
                    faults.append('CHILD_PID');return
                start=time.monotonic()
                p=subprocess.run(['/bin/ps','-p',str(pid),'-o','rss='],
                    stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                    timeout=2,close_fds=True)
                row=dict(pid=pid,returncode=p.returncode,stdout=p.stdout.decode(errors='replace'),
                         stderr=p.stderr.decode(errors='replace'),elapsed_seconds=time.monotonic()-start,
                         helper_not_target=True,reaped=True)
                rows.append(row)
                if len(p.stdout)>128 or len(p.stderr)>1024:
                    faults.append('RESOURCE_CAPTURE_BOUND');return
                if p.returncode==1 and not p.stdout.strip():
                    continue  # Child can finish between its spawn receipt and ps.
                if p.returncode!=0 or not p.stdout.strip().isdigit():
                    faults.append('RESOURCE_OBSERVATION_UNAVAILABLE');return
                row['rss_bytes']=int(p.stdout.strip())*1024
                if row['rss_bytes']>budget:
                    row['budget_exceeded']=True
                    if os.getpgid(pid)==pid:
                        os.killpg(pid,signal.SIGKILL)
                    faults.append('OWNED_CHILD_RSS_BOUND');return
                if len(rows)>=2100:
                    faults.append('RESOURCE_SAMPLE_COUNT_BOUND');return
            except ProcessLookupError:
                continue
            except Exception as error:
                faults.append(type(error).__name__+':'+str(error)[:200]);return
    thread=threading.Thread(target=observe)
    thread.start()
    try:
        result,out,err=cap.capture(argv,area,label,env,**kwargs)
    finally:
        stop.set();thread.join(3)
    cap.need(not thread.is_alive(),'RESOURCE_MONITOR_JOIN')
    peak=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    record=dict(limit_bytes=budget,sampling_seconds=.1,completed_child_peak_bytes=peak,
                completed_peak_scope='DARWIN_RUSAGE_CHILDREN_COHORT_MAX_NOT_PHYSICAL_BYTES',
                samples=rows,metadata_helper_starts=len(rows),faults=faults,
                sampled_stop_not_instantaneous_kernel_cap=True,
                ps_image_before=ps_before,ps_image_after=cap.image('/bin/ps'))
    cap.bank(key/'rss-bound.json',cap.canonical(record))
    cap.need(record['ps_image_before']==record['ps_image_after'],'RESOURCE_TOOL_CHANGED')
    cap.need(not faults and peak<=budget,'RESOURCE_BUDGET_NOT_QUALIFIED')
    return result,out,err
