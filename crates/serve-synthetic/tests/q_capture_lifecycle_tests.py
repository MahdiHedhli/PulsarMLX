#!/usr/bin/env python3
"""Independent ownership oracle; lifecycle mutants use only fake OS/children."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import types

SOURCE=Path(__file__).with_name('q_capture.py')
def require(value, message):
    if not value: raise RuntimeError(message)
def load(source=None):
    module=types.ModuleType('capture_under_test');module.__file__=str(SOURCE)
    exec(compile(SOURCE.read_text() if source is None else source,str(SOURCE),'exec'),module.__dict__)
    return module

class Child:
    pid=42424242
    def __init__(self, code=None, waits=None): self.returncode=code;self.waits=list(waits or [0]);self.calls=[]
    def poll(self): return self.returncode
    def wait(self,timeout):
        self.calls.append(('wait',timeout))
        result=self.waits.pop(0) if self.waits else self.returncode
        if result=='timeout': raise subprocess.TimeoutExpired('fake',timeout)
        self.returncode=result;return result

def owner_oracle(q):
    sends=[]
    owner=q.CaptureOwner(signal_group=lambda p,s:sends.append((p,s)))
    owner.stop(.1);owner.stop(.1)
    require(not sends and owner.state==owner.NEVER_STARTED,'never-started signaled')
    child=Child(0);owner=q.CaptureOwner(child,lambda p,s:sends.append((p,s)))
    owner.poll();owner.stop(.1);owner._send(signal.SIGKILL);owner.stop(.1)
    require(owner.retired and not sends,'reaped child admitted a late signal')
    sends=[];child=Child(waits=[0]);owner=q.CaptureOwner(child,lambda p,s:sends.append((p,s)))
    owner.stop(.1);owner._send(signal.SIGKILL);owner.stop(.1)
    require(sends==[(child.pid,signal.SIGTERM)],'grace exit admitted KILL')
    require(owner.retired and owner.history[-1]['event']=='EXIT_OBSERVED','grace retirement order')
    sends=[];child=Child(waits=['timeout',-9]);owner=q.CaptureOwner(child,lambda p,s:sends.append((p,s)))
    owner.stop(.1);owner.stop(.1)
    require(sends==[(child.pid,signal.SIGTERM),(child.pid,signal.SIGKILL)],'live escalation disabled or repeated')
    require([h['event'] for h in owner.history]==['SIGNAL_REQUEST','SIGNAL_REQUEST','EXIT_OBSERVED'],'escalation ordering')
    child=Child(waits=[0]);owner=q.CaptureOwner(child,lambda *_:None)
    require(owner.pipe_eof() is False and owner.state==owner.LIVE_OWNED,'EOF falsely retired live child')
    owner.wait(.1);require(owner.retired,'wait failed retirement')

def fake_capture(q,root,kind):
    sends=[];child=Child(0 if kind!='eof-live' else None)
    class Stream:
        def __init__(self,fd):self.fd=fd
        def fileno(self):return self.fd
        def close(self):pass
    child.stdout=Stream(100001);child.stderr=Stream(100002)
    class Selector:
        def __init__(self):self.items={}
        def register(self,s,event,name):self.items[s.fd]=types.SimpleNamespace(fileobj=s,data=name)
        def unregister(self,s):del self.items[s.fd]
        def get_map(self):return self.items
        def select(self,timeout):return [] if kind=='inherited-drain' else [(v,1) for v in list(self.items.values())]
        def close(self):pass
    chunks={100001:[b'prefix\n',b'late-failure\n',b''],100002:[b'']}
    if kind=='eof-live':chunks={100001:[b''],100002:[b'']}
    clock=[0]
    def monotonic():clock[0]+=.25;return clock[0]
    def popen(*a,**k):
        if kind=='spawn-error':raise OSError('fake spawn failure')
        return child
    old=(q.subprocess.Popen,q.selectors.DefaultSelector,q.os.read,q.os.set_blocking,q.os.killpg,q.time.monotonic,q.write_all)
    q.subprocess.Popen=popen;q.selectors.DefaultSelector=Selector;q.os.read=lambda fd,n:chunks[fd].pop(0);q.os.set_blocking=lambda *_:None;q.os.killpg=lambda p,s:sends.append((p,s));q.time.monotonic=monotonic
    if kind=='close-failure':
        def fail_close(fd,data):
            if b'"event": "CLOSE"' in data:raise OSError('fake close persistence failure')
            old[-1](fd,data)
        q.write_all=fail_close
    try:
        result=q.capture([sys.executable,'-I','-B','-c','fake-only'],str(root),q.clean_env(root),root/kind,timeout=10,limit=3 if kind=='late-cap' else q.STREAM_LIMIT,inject_failure=kind=='late-failure')
    finally:
        q.subprocess.Popen,q.selectors.DefaultSelector,q.os.read,q.os.set_blocking,q.os.killpg,q.time.monotonic,q.write_all=old
    require(not sends,kind+': post-exit signal request')
    if kind=='close-failure':
        require(result['status']=='EVIDENCE_INCOMPLETE' and not (root/kind/'terminal.json').exists(),'close failure fabricated complete terminal')
        return {'case':kind,'terminal':result,'mock_signals':sends}
    require(json.loads((root/kind/'terminal.json').read_bytes())==result,kind+': returned/durable terminal differs')
    if kind=='late-failure':
        require(result['status']=='EVIDENCE_INCOMPLETE' and result['code']==0,'late failure overwritten')
        require((root/kind/'stdout.raw').read_bytes()==b'prefix\n','late failure lost original prefix')
    elif kind=='inherited-drain':require(result['status']=='EVIDENCE_INCOMPLETE' and 'post-exit' in result['capture_error'],'inherited drain falsely qualified')
    elif kind=='late-cap':require(result['status']=='EVIDENCE_INCOMPLETE' and result['code']==0 and (root/kind/'stdout.raw').read_bytes()==b'pre','post-exit cap lost bounded prefix')
    elif kind=='spawn-error':require(result['status']=='SPAWN_ERROR' and result['child_pid'] is None,'spawn failure fabricated child')
    else:require(result['status']=='CLOSED' and len(child.calls)==1,'EOF substituted for wait/exit')
    return {'case':kind,'terminal':result,'mock_signals':sends}

def fake_suite(q,root):
    owner_oracle(q)
    calls=[];old_popen=q.subprocess.Popen;old_exclusive=q.exclusive
    q.subprocess.Popen=lambda *a,**k:calls.append('unexpected spawn')
    def fail_open(path):
        if str(path).endswith('stderr.raw'):raise OSError('fake pre-spawn persistence failure')
        return old_exclusive(path)
    q.exclusive=fail_open
    try:result=q.capture([sys.executable],str(root),q.clean_env(root),root/'pre-spawn-failure')
    finally:q.subprocess.Popen=old_popen;q.exclusive=old_exclusive
    require(not calls and result['status']=='EVIDENCE_INCOMPLETE' and result['child_pid'] is None,'pre-spawn failure admitted child')
    return [{'case':'pre-spawn-failure','terminal':result}]+[fake_capture(q,root,n) for n in ['spawn-error','late-failure','late-cap','close-failure','inherited-drain','eof-live']]

def fake_mode(out):
    q=load();baseline=out/'pristine';baseline.mkdir(mode=0o700)
    cases=fake_suite(q,baseline)
    text=SOURCE.read_text()
    edits={
      'remove-exit-retirement':('self.state = self.EXIT_OBSERVED','self.state = self.LIVE_OWNED'),
      'signal-after-grace-return':('self.wait(grace)\n                return','self.wait(grace)\n                self.signal_group(self.child.pid, signal.SIGKILL)\n                return'),
      'conflate-eof-exit':('self.poll()\n        return self.retired','self._retire(0)\n        return True')}
    mutants=[]
    for name,(old,new) in edits.items():
        require(text.count(old)==1,name+': anchor cardinality')
        source=text.replace(old,new);folder=out/name;folder.mkdir(mode=0o700)
        (folder/'original-mutant-source').write_text(source)
        try:fake_suite(load(source),folder)
        except RuntimeError as exc:mutants.append({'id':name,'status':'LIFECYCLE_ORACLE_REJECTED','error':str(exc),'source_sha256':hashlib.sha256(source.encode()).hexdigest()})
        else:raise RuntimeError(name+': lifecycle mutant survived')
    return {'status':'FAKE_LIFECYCLE_QUALIFIED','pristine':cases,'lifecycle_mutants':mutants,'actual_children':0,'actual_os_signals':0}

def real_mode(out):
    q=load();cases=[]
    core='import resource;resource.setrlimit(resource.RLIMIT_CORE,(0,0));'
    fixtures=[
      ('exit0',core+"import os;os.write(1,b'out\\n');os.write(2,b'err\\n')",'CLOSED',0,None,{}),
      ('exit134',core+"import os;os.write(1,b'134-out\\n');os.write(2,b'134-err\\n');raise SystemExit(134)",'CLOSED',134,None,{}),
      ('self-signal6',core+"import os,signal;os.write(1,b'signal\\n');os.kill(os.getpid(),signal.SIGABRT)",'CLOSED',None,6,{}),
      ('live-timeout',core+"import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(5)",'TIMEOUT',None,9,{'timeout':.3,'termination_grace':.1}),
      ('output-cap',core+"import os,time;os.write(1,b'x'*4096);time.sleep(1)",'EVIDENCE_INCOMPLETE',None,None,{'limit':16}),
      ('persistence-failure',core+"import os,time;os.write(1,b'prefix\\n');time.sleep(.1);os.write(1,b'fail\\n');time.sleep(1)",'EVIDENCE_INCOMPLETE',None,15,{'inject_failure':True})]
    start=time.monotonic()
    for name,code,status,exit_code,native_signal,options in fixtures:
        terminal=q.capture([sys.executable,'-I','-B','-c',code],str(out),q.clean_env(out),out/name,timeout=options.pop('timeout',2),**options)
        require(terminal['status']==status and terminal['reaped'] and terminal['signaling_authority_retired'],name+': status/reap/retirement')
        require(json.loads((out/name/'terminal.json').read_bytes())==terminal,name+': durable terminal mismatch')
        if name!='output-cap':require(terminal['code']==exit_code and terminal['native_signal']==native_signal,name+': ordinary exit/native signal mismatch')
        history=terminal['ownership_history'];retired=False
        for event in history:
            if event['event']=='EXIT_OBSERVED':retired=True
            if event['event']=='SIGNAL_REQUEST':require(not retired and event['state']=='LIVE_OWNED',name+': retired signal')
        if name=='persistence-failure':require((out/name/'stdout.raw').read_bytes()==b'prefix\n','incomplete prefix')
        if name=='output-cap':require((out/name/'stdout.raw').read_bytes()==b'x'*16,'bounded original prefix')
        if name=='exit0':require((out/name/'stdout.raw').read_bytes()==b'out\n' and (out/name/'stderr.raw').read_bytes()==b'err\n','distinct streams')
        cases.append({'case':name,'terminal':terminal})
    require(time.monotonic()-start<=30,'real controller exceeded 30 seconds')
    return {'status':'HARMLESS_REAL_LIFECYCLE_QUALIFIED','actual_fixture_children':len(cases),'cases':cases,'descendant_containment':'NOT_TESTED'}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--mode',choices=['fake','real'],required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    args.output.mkdir(mode=0o700,parents=True,exist_ok=False)
    result=fake_mode(args.output) if args.mode=='fake' else real_mode(args.output)
    result['implementation_sha256']=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    (args.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
