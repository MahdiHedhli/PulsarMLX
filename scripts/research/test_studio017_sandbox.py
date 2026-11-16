"""Bounded synthesized OS control only, no campaign config, claims, grants, model or numerical runtime."""
import os, pathlib, socket, subprocess, sys, tempfile
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from studio017_supervise import profile
def control():
 p=pathlib.Path;exe=p(sys.executable).resolve();folder=p(__file__).resolve().parent
 # Put mock secret alongside, outside allowed task/source and output roots.
 with tempfile.TemporaryDirectory() as temp:
  t=p(temp).resolve();out=t/'out';out.mkdir();secret=t/'forbidden-original';secret.write_text('secret')
  cap=t/'cap';cap.write_text('control');proof=out/'output';policy=t/'sb';role='native'
  c={'stages':{role:{'array_roots':['/opt/homebrew/Cellar','/opt/homebrew/opt','/opt/homebrew/lib','/opt/homebrew/bin'],'program':str(exe),'image':str(exe),'python':str(exe),'library_prefix':'/usr/lib'}},'repo':str(folder),'input':str(cap),'checkpoint':str(t/'unreadable-other')}
  policy.write_bytes(profile(c,role,cap,out,t/'fake-unused'));ps,cs=socket.socketpair(type=socket.SOCK_DGRAM);ps.settimeout(15)
  inner='''import os,sys,socket; from pathlib import Path
print('inner-start',file=sys.stderr,flush=True);fd=int(sys.argv[1]);s=socket.socket(fileno=fd)
try: Path(sys.argv[2]).read_bytes()
except PermissionError: pass
else: raise RuntimeError("sandbox allowed forbidden bytes")
print('inner-denied',file=sys.stderr,flush=True);Path(sys.argv[3]).write_text("control-ok");print('inner-ready',file=sys.stderr,flush=True);s.send(b"inner");assert s.recv(20)==b"ack"
'''
  script='''import os,sys,subprocess
print('outer-start',file=sys.stderr,flush=True);fd=int(sys.argv[1]);subprocess.run([sys.executable,"-I","-B","-c",sys.argv[2],str(fd),sys.argv[3],sys.argv[4]],pass_fds=(fd,),check=True,timeout=10)
'''
  proc=subprocess.Popen(['/usr/bin/sandbox-exec','-f',str(policy),str(exe),'-I','-B','-c',script,str(cs.fileno()),inner,str(secret),str(proof)],pass_fds=(cs.fileno(),),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True,env={'HOME':str(p.home()),'PATH':'/usr/bin:/bin'});cs.close()
  try:
   assert ps.recv(200)==b'inner';ps.send(b'ack');stdout,stderr=proc.communicate(timeout=10)
   assert proc.returncode==0 and proof.read_text()=='control-ok',(proc.returncode,stdout,stderr)
   print('PASS: sandbox blocked forbidden contents; allowed fresh role output and isolated child-helper acknowledgement on inherited local channel')
  finally:
   if proc.poll() is None:os.killpg(proc.pid,9)
   so,se=proc.communicate();ps.close()
   if proc.returncode!=0:print('child error:',proc.returncode,repr(so),repr(se),file=sys.stderr)
if __name__=='__main__':control()
