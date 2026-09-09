"""Source-free bounded capture for fixed trusted-preparation children.

This is not OS confinement. CLI modes are closed source-free doctor probes;
there is no CLI that accepts a command, code body, module or output location.
"""
import hashlib
import json
import os
from pathlib import Path
import resource
import selectors
import signal
import subprocess
import sys
import time

LIMIT=32768
def need(value, label):
    if not value: raise ValueError(label)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(value):return (json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
def bank(path,raw):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        offset=0
        while offset<len(raw):n=os.write(fd,raw[offset:]);need(n>0,'SHORT_WRITE');offset+=n
        os.fsync(fd)
    finally:os.close(fd)
    return dict(path=str(path),bytes=len(raw),sha256=sha(raw))
def image(path):
    p=Path(path).resolve(strict=True);s=p.stat();raw=p.read_bytes();t=p.stat()
    need((s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns)==(t.st_dev,t.st_ino,t.st_size,t.st_mtime_ns),'EXECUTABLE_CHANGED')
    return dict(path=str(p),bytes=len(raw),sha256=sha(raw),device=s.st_dev,inode=s.st_ino)
def capture(argv,area,label,env,*,timeout=180,limit=LIMIT,missing_probe=False):
    """Internal reviewed-controller API; argv is formed by its closed callers."""
    need(type(argv)is list and argv and all(type(x)is str for x in argv),'ARGV_ARRAY')
    need(0<timeout<=180 and 0<limit<=12*1024**2 and '/'not in label,'CAPTURE_BOUNDS')
    area=Path(area);key=area/'captures'/label
    before=None if missing_probe else image(argv[0]);start=time.monotonic()
    bank(key/'attempt.json',canonical(dict(argv=argv,cwd=str(area),environment=env,requested_executable_before=before,timeout_seconds=timeout,limit=limit,stdin='DEVNULL',close_fds=True,start_new_session=True)))
    child=None;failed_spawn=None;timed_out=False;capture_error=None;streams={n:bytearray()for n in ('stdout','stderr')};counts={n:0 for n in streams};sel=selectors.DefaultSelector();status=None
    try:
        try:child=subprocess.Popen(argv,cwd=area,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,close_fds=True,start_new_session=True)
        except OSError as error:failed_spawn=dict(type=type(error).__name__,errno=error.errno)
        if child:
            bank(key/'spawn.json',canonical(dict(pid=child.pid,actual_target_start=True)))
            for name,pipe in [('stdout',child.stdout),('stderr',child.stderr)]:os.set_blocking(pipe.fileno(),False);sel.register(pipe,selectors.EVENT_READ,name)
            while sel.get_map() or child.poll()is None:
                if time.monotonic()-start>=timeout:
                    timed_out=True
                    if child.poll()is None:os.killpg(child.pid,signal.SIGKILL)
                    break
                for event,_ in sel.select(.02):
                    raw=os.read(event.fileobj.fileno(),4096)
                    if not raw:sel.unregister(event.fileobj);event.fileobj.close()
                    else:counts[event.data]+=len(raw);streams[event.data].extend(raw[:max(0,limit-len(streams[event.data]))])
            status=child.wait(timeout=30)
    except Exception as error:capture_error=dict(type=type(error).__name__,message=str(error)[:400])
    finally:
        if child and child.poll()is None:os.killpg(child.pid,signal.SIGKILL);status=child.wait(timeout=30)
        for event in list(sel.get_map().values()):event.fileobj.close()
        sel.close()
    raw={name:bytes(b)for name,b in streams.items()};records={n:bank(key/n,b)for n,b in raw.items()}
    after=None if missing_probe else image(argv[0]);stable=before==after
    result=dict(argv=argv,actual_target_start=child is not None,pid=child.pid if child else None,returncode=status,exit_code=status if status is not None and status>=0 else None,signal=-status if status is not None and status<0 else None,failed_spawn=failed_spawn,timed_out=timed_out,reaped=child is not None and child.returncode is not None,capture_error=capture_error,streams=records,stream_total_bytes=counts,truncated={n:counts[n]>len(raw[n])for n in raw},requested_executable_before=before,requested_executable_after=after,image_stable=stable,executing_image_independently_observed=False,elapsed_seconds=time.monotonic()-start,descendants='REQUIRES_FIXED_CALL_PATH_AND_GIT_TRACE_VALIDATION; UNKNOWN_ON_ABNORMAL_PARENT_TERMINATION')
    result['capture_integrity']='PASS'if stable and not timed_out and capture_error is None and not any(result['truncated'].values())else'FAIL'
    bank(key/'result.json',canonical(result));return result,raw['stdout'],raw['stderr']
def doctor_mode():
    resource.setrlimit(resource.RLIMIT_CORE,(0,0));need(sys.flags.isolated and sys.flags.no_site and sys.flags.optimize==0,'DOCTOR_ISOLATION')
    need(sys.argv[1:]in [['--doctor-io'],['--doctor-exit134'],['--doctor-signal6'],['--doctor-timeout']],'FIXED_DOCTOR_MODE')
    mode=sys.argv[1]
    if mode=='--doctor-signal6':os.abort()
    if mode=='--doctor-timeout':time.sleep(5);return
    if mode=='--doctor-exit134':print('SOURCE_FREE_STDOUT',flush=True);print('SOURCE_FREE_STDERR',file=sys.stderr,flush=True);raise SystemExit(134)
    bank(Path('fixed-doctor.txt'),b'F017_SOURCE_FREE_DOCTOR\n')
    need(Path('fixed-doctor.txt').read_bytes()==b'F017_SOURCE_FREE_DOCTOR\n','SOURCE_FREE_READBACK')
    print(json.dumps(dict(result='PASS',python=sys.version,project_modules_imported=0,fixed_write_read=True)))
if __name__=='__main__':doctor_mode()
