"""Task-local custody for the explicitly selected Studio019 diagnostic."""
from studio017_guard import *

BASE = "140ee24d99a9a2183d65c841bdb198d4682f83f1"
STATE = USER_HOME / "LocalWorktrees/PulsarMLX-studio019-state"
REFERENCE_STATE = USER_HOME / "LocalWorktrees/PulsarMLX-studio017-state"
REFERENCE_CLAIM = ART / "studio017-full-flash-golden-token-reference-initial.claim.json"
ANCHORS = {"native": ART / "studio019-route-b-native-diagnostic-initial.claim.json"}
TASK = "studio019-route-b-native-diagnostic"
MODE = "operator-supervised-route-b"

def source(repo):
 repo=path(repo);need(git(repo,'remote','get-url','origin').strip()==b'https://github.com/MahdiHedhli/PulsarMLX.git','origin')
 head=git(repo,'rev-parse','HEAD').decode().strip();tree=git(repo,'rev-parse','HEAD^{tree}').decode().strip()
 need(git(repo,'symbolic-ref','HEAD').strip()==b'refs/heads/codex/studio019-route-b-native-diagnostic' and git(repo,'merge-base',BASE,head).decode().strip()==BASE,'source branch/parent')
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
