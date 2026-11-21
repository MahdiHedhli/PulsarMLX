"""Task-local custody for the explicitly selected Studio020 diagnostic."""
from studio017_guard import *

BASE = "a23c893ef6567a8e0062e2dc8f386970603215f6"
STATE = USER_HOME / "LocalWorktrees/PulsarMLX-studio020-state"
REFERENCE_STATE = USER_HOME / "LocalWorktrees/PulsarMLX-studio017-state"
REFERENCE_CLAIM = ART / "studio017-full-flash-golden-token-reference-initial.claim.json"
ANCHORS = {"native": ART / "studio020-stream-reuse-native-diagnostic-initial.claim.json",
           "grade": ART / "studio020-stream-reuse-native-diagnostic-grade.claim.json"}
STEM = "Prompts/RUST-ENGINE/Mac-Studio-M1-Ultra/020__RUST-ENGINE__Mac-Studio-M1-Ultra__stream-reuse-native-diagnostic"
TASK = "studio020-stream-reuse-native-diagnostic"
MODE = "operator-supervised-stream-reuse"

def source(repo):
 repo=path(repo);need(git(repo,'remote','get-url','origin').strip()==b'https://github.com/MahdiHedhli/PulsarMLX.git','origin')
 head=git(repo,'rev-parse','HEAD').decode().strip();tree=git(repo,'rev-parse','HEAD^{tree}').decode().strip()
 need(git(repo,'symbolic-ref','HEAD').strip()==b'refs/heads/codex/studio020-stream-reuse-native-diagnostic' and git(repo,'merge-base',BASE,head).decode().strip()==BASE,'source branch/parent')
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

RUN = "76eb44a3be4af9645d43ad54289eaaaac5f35008c48cfcde8ac39a77c1a667de"
OPERATIONS = {"native": "2226fb011b19434ba3cf9bb24016cd11", "grade": "01b93c5a646c41ed82bae0d39086a7ca"}
GRADE_STATE = STATE / "pairwise-grade"
HISTORICAL_OPERATIONS = {"e407d5354a445be64811725c4320e656", "2716258e1e096dbcda22f898828fdbe4", "84bca402c0066d03b211cf24f6259ef3"}
COMPARISON_LIMITS = dict(timeout=300, combined=2147483648, launch_headroom=19327352832,
                         headroom=17179869184, swap_growth=67108864, swap_samples=2,
                         log_bytes=8388608, claims=1)

def operation_bindings(c):
 need(c['run']==RUN and c['operations']==OPERATIONS and set(c['operations'])=={'native','grade'},'reserved run/operations')
 values=[hexid(c['operations'][key],32) for key in ('native','grade')]
 need(len(set(values))==2 and not set(values)&HISTORICAL_OPERATIONS,'disjoint numerical operations')
 return dict(operations=dict(c['operations']),claims={k:str(v) for k,v in ANCHORS.items()},
             outputs=dict(native=str(STATE/'campaign-native/output'),grade=str(GRADE_STATE)))

def comparison_limits(c):
 row=c['artifacts']['comparison-resource'];checked(path(row['path']),row['sha256'])
 value=doc(path(row['path']));need(value==COMPARISON_LIMITS,'frozen comparison ledger')
 return value

def historical_diagnostic():
 old=USER_HOME/'LocalWorktrees/PulsarMLX-studio019-state/campaign-native'
 native=ART/'studio019-route-b-native-diagnostic-initial.claim.json'
 checked(native,'d2dedbf552f5fcc2e5ec6e6aba9e8a7658cda4b035573b711c9e3e36ccaf0769')
 checked(old/'grade-intent.json','65bf95d58bc02bdd4a7810e602172807023f4d1624f69e31bc00e3428ffc1394')
 checked(old/'grade-exit.json','b6c2db4608975cf84ab4461a357076115e5184002d5ab3d957b447774dab292b')
 n=doc(native);g=doc(old/'grade-intent.json');end=doc(old/'grade-exit.json')
 need(n['run']=='887d9f85fadaebb634af04039815dabc8fb5b91a05febab2b398d13393d294d1' and
      n['source']=='a1343f3532bbbe0153de0a553ede960309ebe98b' and
      n['operation']=='e407d5354a445be64811725c4320e656' and
      g['operation']==end['operation']=='2716258e1e096dbcda22f898828fdbe4' and
      g['numeric_operation']==n['operation'] and end['exit']==end['guardian_exit']==0 and
      end['clean_reap'] is True and end['residual_group_killed'] is False,'original spent Studio019 diagnostic')
