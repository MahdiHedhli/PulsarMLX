"""Darwin-only, no numerical imports/data. Run ONLY under the owned controls runner.
Ancestry registration uses EVFILT_PROC/NOTE_EXIT, not an unguarded PID poll.
This test deliberately kills only its own supervisor fixture after readiness.
"""
from pathlib import Path
import json
import os
import select
import signal
import subprocess
import sys
import tempfile
import time

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from studio017_lease import Lease


def owner(d):
    # Worker initially accepts exactly one byte from this owner, then only sleeps.
    r,w=os.pipe()
    code="import os,sys,time;fd=int(sys.argv[1]);assert os.read(fd,1)==b'G';os.close(fd);print('released',flush=True);time.sleep(30)"
    with (d/'worker.log').open('xb') as log:
        worker=subprocess.Popen([sys.executable,'-I','-S','-B','-c',code,str(r)],
            process_group=0,stdin=subprocess.DEVNULL,stdout=log,stderr=log,pass_fds=(r,))
        os.close(r)
        lease=Lease.attach(worker,time.monotonic()+12,sys.executable,HERE/'studio017_lease.py',
            {'PATH':'/usr/bin:/bin'},d,log)
        try:
            os.write(w,b'G');os.close(w)
            # Pins origin, readiness and inherited group before the test driver can kill owner.
            print(json.dumps(lease.receipt()),flush=True)
            while True:
                lease.pulse();time.sleep(.05)
        finally:
            # Explicit failure after the driver has received ready; never normal-disarm.
            lease.finish(worker,False,lambda pg:[])


def parent_death():
    if sys.platform!='darwin':
        raise RuntimeError('Darwin ownership control required')
    with tempfile.TemporaryDirectory() as tmp:
        outer=subprocess.Popen([sys.executable,'-I','-S','-B',str(Path(__file__).resolve()),'owner',tmp],
             stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
        try:
            assert select.select([outer.stdout],[],[],8)[0]
            rec=json.loads(outer.stdout.readline());pids={rec['worker_pgid'],rec['watcher_pid']}
            assert len(pids)==2 and rec['owner_pid']==outer.pid
            assert all(os.getpgid(p)==rec['worker_pgid'] and os.getsid(p)==outer.pid for p in pids)
            with select.kqueue() as queue:
                queue.control([select.kevent(p,filter=select.KQ_FILTER_PROC,flags=select.KQ_EV_ADD|select.KQ_EV_ONESHOT,
                                fflags=select.KQ_NOTE_EXIT) for p in pids],0,0)
                outer.kill();assert outer.wait(2)==-signal.SIGKILL
                end=time.monotonic()+4;seen=set()
                while seen!=pids and time.monotonic()<end:
                    for ev in queue.control([],2,max(0,end-time.monotonic())):
                        assert ev.ident in pids and ev.fflags & select.KQ_NOTE_EXIT;seen.add(ev.ident)
                assert seen==pids, 'watchdog and worker failed to exit promptly on supervisor SIGKILL'
        finally:
            if outer.poll() is None:outer.kill()
            outer.wait(2)
            # Absolute watcher deadline 12s and synthetic sleep 30s bound even a failed test.
            # Do not use killpg on stale helper PID(s) from a failed control.


if __name__=='__main__':
    owner(Path(sys.argv[2])) if sys.argv[1:2]==['owner'] else parent_death()
