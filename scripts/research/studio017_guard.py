"""Private-run custody helpers, no numerical backend or checkpoint payload reads."""
from pathlib import Path
import base64,contextlib,ctypes,hashlib,json,math,os,pwd,re,stat,subprocess,sys,time
BASE='221651a8b8db8138f61e38825b74443071f3553b'
REPO='MahdiHedhli/PulsarMLX-Prompts'
STEM='Prompts/RUST-ENGINE/Mac-Studio-M1-Ultra/017__RUST-ENGINE__Mac-Studio-M1-Ultra__full-flash-golden-token'
MODEL='d43ea8b407ce4e9c25e6ac9baec3feab70d9f5f3'
USER_HOME=Path(pwd.getpwuid(os.getuid()).pw_dir)
ROOT=USER_HOME/'Models/PulsarMLX/GLM-5.3-Flash-MLX-mixed-4_8bit'
STATE=USER_HOME/'LocalWorktrees/PulsarMLX-studio017-state'
ART=USER_HOME/'.codex/artifacts'
ANCHORS={s:ART/('studio017-full-flash-golden-token-'+s+'-initial.claim.json') for s in ('reference','native')}
GIB=1<<30
CAP=16<<20
def need(v,why):
 if not v:raise ValueError(why)
def pairs(p):
 x={}
 for k,v in p:need(k not in x,'duplicate field '+k);x[k]=v
 return x
def finite_reject(x):raise ValueError('nonfinite JSON '+x)
def parse(b):return json.loads(b.decode(),object_pairs_hook=pairs,parse_constant=finite_reject)
def enc(v):return (json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def hexid(x,n):need(type(x)==str and re.fullmatch('[a-f0-9]{%d}'%n,x),'invalid hex id');return x
def path(x):
 p=Path(x);need(p.is_absolute() and str(p)==str(x) and p.resolve(strict=True)==p,'canonical path '+str(p));return p
def fdstamp(st):return [st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns]
@contextlib.contextmanager
def opened(p,max_size=CAP):
 p=path(p)
 # Component traversal via directory descriptors, nofollow on every named lookup.
 d=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
 try:
  for comp in p.parts[1:-1]:
   n=os.open(comp,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=d);os.close(d);d=n
  fd=os.open(p.name,os.O_RDONLY|os.O_NONBLOCK|os.O_NOFOLLOW,dir_fd=d)
  try:
   st=os.fstat(fd);need(stat.S_ISREG(st.st_mode) and st.st_size<=max_size,'bounded ordinary file '+p.name)
   yield fd,st
   need(fdstamp(st)==fdstamp(os.fstat(fd))==fdstamp(p.lstat())==fdstamp(os.stat(p.name,dir_fd=d,follow_symlinks=False)),'replaced file '+p.name)
  finally:os.close(fd)
 finally:os.close(d)
def read(p,cap=CAP):
 with opened(p,cap) as (f,st):
  b=bytearray()
  while len(b)<st.st_size:
   chunk=os.read(f,min(1<<20,st.st_size-len(b)));need(chunk,'unexpected EOF');b.extend(chunk)
  return bytes(b)
def doc(p):return parse(read(p))
def digest(p,cap=2<<30):
 with opened(p,cap) as (fd,st):
  h=hashlib.sha256();total=0
  while c:=os.read(fd,1<<20):h.update(c);total+=len(c)
  need(total==st.st_size,'hash short');return h.hexdigest()
def put(p,obj):
 p=Path(p);path(p.parent);b=enc(obj)
 fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
 with os.fdopen(fd,'wb') as f:f.write(b);f.flush();os.fsync(f.fileno())
 d=os.open(p.parent,os.O_RDONLY);os.fsync(d);os.close(d)
def cmd(args,*,env=None,cwd=None,timeout=25):return subprocess.check_output(args,env=env,cwd=cwd,timeout=timeout,stderr=subprocess.PIPE)
def git(repo,*args):
 return cmd(['/usr/bin/git','--no-replace-objects','--no-optional-locks',*args],cwd=repo,env={'HOME':str(Path.home()),'PATH':'/usr/bin:/bin','GIT_OPTIONAL_LOCKS':'0'})
def source(repo):
 repo=path(repo);need(git(repo,'remote','get-url','origin').strip()==b'https://github.com/MahdiHedhli/PulsarMLX.git','origin')
 head=git(repo,'rev-parse','HEAD').decode().strip();tree=git(repo,'rev-parse','HEAD^{tree}').decode().strip()
 need(git(repo,'symbolic-ref','HEAD').strip()==b'refs/heads/codex/studio017-full-flash-golden-token' and git(repo,'merge-base',BASE,head).decode().strip()==BASE and head!=BASE,'source branch/parent')
 need(not git(repo,'status','--porcelain=v1','--untracked-files=all','--ignore-submodules=none') and not git(repo,'ls-files','--others') and not git(repo,'submodule','status','--recursive'),'clean source/submodules')
 entries=git(repo,'ls-tree','-rz',head).split(b'\0');items=[];rawbytes=0
 for entry in filter(None,entries):
  cols,n=entry.split(b'\t',1);mode,typ,oid=cols.split();p=repo/os.fsdecode(n)
  need(typ==b'blob','submodule/candidate source object')
  if mode==b'120000':need(p.is_symlink(),'tracked link mode');b=os.fsencode(os.readlink(p))
  else:
   need(mode in (b'100644',b'100755') and bool(p.stat().st_mode&0o111)==(mode==b'100755'),'source mode')
   b=read(p,128<<20)
  rawbytes+=len(b);need(rawbytes<=1<<30,'source size')
  need(hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==oid.decode(),'dirty source blob '+str(n))
  items.append([os.fsdecode(n),mode.decode(),sha(b)])
 # Bind all effective config incl origins; do not publish values/paths.
 cg=git(repo,'config','--null','--show-origin','--list')
 for base in (repo,*repo.parents,Path.home()):
  for n in ('config','config.toml'):need(not os.path.lexists(base/'.cargo'/n),'unbound Cargo config')
 return dict(head=head,tree=tree,inventory_sha256=sha(enc(items)),files=len(items),git_config_sha256=sha(cg))
def checked(p,h):need(digest(p)==hexid(h,64),'artifact drift '+Path(p).name)
def checkpoint(dir):
 d=path(dir);q=doc(d/'receipt.json');need(q['all_shards_byte_verified'] is True and q['mode']=='full' and q['revision']==MODEL,'full custody receipt')
 for k,n in [('witnesses','witnesses'),('inventory','inventory'),('ledger','logical-ledger')]:checked(d/(n+'.json'),q[k+'_sha256'])
 checked(d/'publisher.json',q['publisher_response_sha256']);pub=doc(d/'publisher.json');need(pub['sha']==MODEL,'publisher revision')
 files={v['rfilename']:v for v in pub['siblings']};wit=doc(d/'witnesses.json')
 need(set(wit)==set(q['metadata'])|set(q['shards']) and set(q['shards'])=={'model-%05d.safetensors'%i for i in range(1,19)},'complete witnesses')
 for n,stamp in wit.items():
  need('/' not in n and n not in ('.','..'),'basename')
  with opened(ROOT/n,32<<30) as (_,st):need(fdstamp(st)==stamp,'checkpoint drift '+n)
  if n in q['shards']:
   row=q['shards'][n];need(row['checked_whole_sha256']==row['publisher_lfs_sha256']==files[n]['lfs']['sha256'] and row['bytes']==files[n]['size']==stamp[2],'unverified shard '+n)
  else:checked(ROOT/n,q['metadata'][n]['sha256'])
 return q
def pressure():
 def sc(k):return cmd(['/usr/sbin/sysctl','-n',k],timeout=5).decode().strip()
 total=int(sc('hw.memsize'));pct=int(sc('kern.memorystatus_level'));pages=os.sysconf('SC_PAGE_SIZE')
 need(total==137438953472 and pages==16384==int(sc('hw.pagesize')) and sc('hw.model')=='Mac13,2' and sc('machdep.cpu.brand_string')=='Apple M1 Ultra','host identity')
 free=int(sc('vm.page_free_count'));pg=int(sc('vm.page_pageable_external_count'));m=re.search(r'used\s*=\s*([\d.]+)([KMGT])',sc('vm.swapusage'))
 need(0<=pct<=100 and min(free,pg)>=0 and m,'memory sample')
 return dict(headroom=min(max(0,pct-1)*total//100,(free+pg//2)*pages),pressure=int(sc('kern.memorystatus_vm_pressure_level')),swap=int(float(m[1])*1024**('KMGT'.index(m[2])+1)),free_pages=free,pageable_external=pg,kernel_pct=pct)
def remote(c,p):
 # Verify actual published files; never pass resource URLs or shell snippets as commands.
 def gh(s):return parse(cmd(['/opt/homebrew/bin/gh','api','repos/'+REPO+s],timeout=40))
 need(gh('')['private'] and gh('/git/commits/'+c)['sha']==c,'private commit identity')
 def fetch(n):
  r=gh('/contents/'+n+'?ref='+c);need(r['path']==n and r['type']=='file' and r['encoding']=='base64' and r['size']<256<<10,'grant transport')
  b=base64.b64decode(r['content']);need(len(b)==r['size'] and r['sha']==hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest(),'Git blob readback');return b
 return fetch(p),fetch(p+'.sha256')
def procpath(pid):
 lib=ctypes.CDLL('/usr/lib/libproc.dylib',use_errno=True);buf=ctypes.create_string_buffer(4096)
 n=lib.proc_pidpath(pid,buf,len(buf));need(n>0,'unknown executable image');return str(Path(os.fsdecode(buf.value)).resolve(strict=True))
def cohort():
 raw=cmd(['/bin/ps','-axo','pid=,ppid=,pgid=,rss=,comm=']).decode()
 rows=[]
 for l in raw.splitlines():
  w=l.split(None,4)
  if len(w)==5:rows.append((*[int(i) for i in w[:4]],w[4]))
 return rows
def census(base,build):
 total=compiled=0
 for root,dirs,names in os.walk(base,followlinks=False):
  for n in names:
   f=Path(root)/n;size=f.lstat().st_size
   if f.is_relative_to(build):compiled+=size
   else:total+=size
 return total,compiled
