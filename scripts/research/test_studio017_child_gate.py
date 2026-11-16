"""Synthetic control of admit-child lineage and ack, using only temporary fixture data and anchors.
Never monkeypatch/replace the real worker's files. Do not give the fixture a checkpoint or launch grant."""
import os,select,socket,subprocess,sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import studio017_supervise as sup
from studio017_guard import digest,enc,procpath,put,sha
def test():
 exe=Path(sys.executable).resolve();image=procpath(os.getpid());source=Path(__file__).resolve().parent
 with tempfile.TemporaryDirectory() as tmp:
  t=Path(tmp).resolve();s=t/'synthetic';s.mkdir();d=s/'campaign-native';d.mkdir();out=d/'output';out.mkdir();cap=d/'child-cap.json';claim=t/'fixture-claim';forbidden=t/'denied';forbidden.write_text('forbidden')
  # Numerical surrogate cannot read forbidden bytes, and a manually launched helper cannot authorize it.
  helper="import sys,os;from pathlib import Path;sys.path.insert(0,sys.argv[1]);import studio017_supervise as m;m.STATE=Path(sys.argv[2]);m.ANCHORS={'native':Path(sys.argv[3])};d=m.child(sys.argv[4]);assert d['stage']=='native' and 'golden' not in d and d['model_root']=='denied-fixture'"
  host='''import os,sys,subprocess
from pathlib import Path
fd=int(os.environ['STUDIO017_ADMIT_CHANNEL'])
# Parent's empty bootstrap grants are not needed and cannot authorize arbitrary use.
try: Path(sys.argv[1]).read_bytes()
except PermissionError: pass
else: raise RuntimeError("unexpected read")
subprocess.run([sys.executable,"-I","-B","-c",*sys.argv[2:]],pass_fds=(fd,),check=True,timeout=12)
'''
  argv=[str(exe),'-I','-B','-c',host,str(forbidden),helper,str(source),str(s),str(claim),str(cap)]
  v=dict(stage='native',operation='synthetic-only',run='unit',supervisor=os.getpid(),supervisor_image=image,expected_image=image,argv=argv,model_root='denied-fixture',checkpoint_receipt='fixture',inventory='fixture',witnesses='fixture',input='fixture',pins={},output=str(out),prefix='fixture',libs={})
  put(claim,dict(stage='native',run='unit',operation=v['operation'],supervisor=os.getpid()));put(cap,v)
  rs=dict(array_roots=['/opt/homebrew/Cellar','/opt/homebrew/opt','/opt/homebrew/lib','/opt/homebrew/bin'],program=str(exe),image=image,python=str(exe),library_prefix='/usr/lib')
  policy=t/'sb';policy.write_bytes(sup.profile(dict(stages={'native':rs},repo=str(source),input=str(cap),checkpoint=str(t/'unused')),'native',cap,out,claim))
  reader,writer=os.pipe();ps,cs=socket.socketpair(type=socket.SOCK_DGRAM);ps.settimeout(10);prior=sup.ANCHORS
  proc=subprocess.Popen(['/usr/bin/sandbox-exec','-f',str(policy),str(exe),'-I','-B',str(source/'studio017_supervise.py'),'stage-exec',str(cap),str(reader)],pass_fds=(reader,cs.fileno()),start_new_session=True,env={'HOME':str(Path.home()),'PATH':'/usr/bin:/bin','STUDIO017_ADMIT_CHANNEL':str(cs.fileno())},stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  os.close(reader);cs.close()
  try:
   sup.ANCHORS={'native':claim};birth=subprocess.check_output(['/bin/ps','-p',str(proc.pid),'-o','lstart=']).decode().strip()
   put(d/'active.json',dict(operation=v['operation'],supervisor=os.getpid(),child=proc.pid,birth=birth,cap_sha256=digest(cap),claim_sha256=digest(claim)))
   os.write(writer,b'G');os.close(writer);writer=-1
   deadline=time.monotonic()+12
   while not select.select([ps],[],[],.1)[0]:
    if proc.poll() is not None:raise RuntimeError('fixture failed: '+proc.communicate()[1].decode().split('Traceback (most recent call last):')[-2][-1600:])
    assert time.monotonic()<deadline,'missing admission request'
   sup.poll_ack(ps,proc,v,'native',cap)
   a,b=proc.communicate(timeout=5);assert proc.returncode==0,(a,b)
   assert (d/'admitted.json').is_file()
   try:sup.child(cap)
   except (FileNotFoundError,ValueError):pass
   else:raise RuntimeError('manual stale helper accepted')
   print('PASS: barrier, actual child->helper ancestry/image, offline claim/cap hash, received one-shot ack; secret read denied; stale admission refused')
  finally:
   sup.ANCHORS=prior
   if writer>=0:os.close(writer)
   if proc.poll() is None:os.killpg(proc.pid,9)
   proc.communicate();ps.close()
if __name__=='__main__':test()
