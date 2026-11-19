"""Studio019 explicit operator Route B diagnostic, fresh nonrefundable native anchor.
CLI: describe|verify|launch CONFIG STAGE, or admit-child CAPABILITY. Seals and grade once on original outputs."""
from pathlib import Path
import contextlib,fcntl,socket,select,hashlib,json,math,os,re,resource,secrets,shutil,signal,stat,subprocess,sys,time
if str(Path(__file__).resolve().parent) not in sys.path:sys.path.insert(0,str(Path(__file__).resolve().parent))
import studio019_py_gate as pyg
import studio017_authority as authority
import studio019_operator as operator
from studio019_progress import Witnesses, ProgressDeadline, abort_channel
from studio017_image_receipt import checked_observations
from studio017_lease import Lease
from studio019_guard import *
SELF=Path(__file__).resolve()
ROLES={'reference','native'}
def layout(cfg,role):
 need(role in ROLES,'role')
 d=(REFERENCE_STATE if role=='reference' else STATE)/('campaign-'+role)
 return d,d/'output',d/'child-cap.json'
def local_mode(c):
 return c.get('schema')=='studio019-operator-config/1' and c.get('mode')==operator.MODE
def config_path(selected):
 need(selected,'explicit Studio019 diagnostic mode required')
 return STATE/'operator-campaign-config.json'
def load_cfg(conf,selected=False):
 need(selected,'explicit diagnostic selection');p=path(conf);need(Path.home()==USER_HOME,'physical account');need(p==config_path(selected),'original campaign-config for selected mode')
 c=doc(p)
 fields={'schema','run','repo','source','checkpoint','build_root','input','artifacts','runtime_files','stages','criteria','controls','review','ci','resource','prior_claims','controls_runtime_sha256','build'}
 need(set(c)==(fields|{'mode'} if selected else fields),'config fields')
 need((local_mode(c) if selected else c['schema']=='studio017-stage-config/1') and set(c['stages'])==ROLES,'config roles/mode')
 if selected:operator.validate_config(c)
 hexid(c['run'],64);need(path(c['repo'])!=STATE and not ROOT.is_relative_to(path(c['repo'])),'separate paths')
 need(path(c['build_root']).is_relative_to(STATE) and path(c['build_root'])!=STATE,'external build custody')
 for key in ('criteria','controls','review','ci','resource','input'):path(c[key])
 return c
def pinset(c):
 pins={};allpins={**c['artifacts'],**c['runtime_files']}
 need(len(allpins)==len(c['artifacts'])+len(c['runtime_files']) and 0<len(allpins)<=8192,'pins')
 for k,v in sorted(allpins.items()):
  need(type(k)==str and re.fullmatch('[a-zA-Z0-9._-]+',k) and set(v)=={'path','sha256'},'pin schema')
  checked(path(v['path']),v['sha256']);pins[k]=v['sha256']
 return pins
def valid_int(n,a,b):return type(n) is int and a<=n<=b
def python_policy(c,full=False):
 row=c['artifacts']['python-policy'];p=pyg.binding(row['path'],row['sha256']);pyg.validate(p,full)
 need(p['roots'][3]==str(SELF.parent) and p['interpreter']==c['stages']['reference']['python'] and p['task']==TASK and p['source']=={k:c['source'][k] for k in ('head','tree')},'physical runtime policy')
 return row,p
def python_originals(c,role,d,op):
 row,p=python_policy(c);active=doc(d/'active.json');ack=doc(d/'admitted.json')
 need(ack['worker']==active['child'] and ack['operation']==active['operation']==op,'Python receipt parent authority')
 roles={'lease-numeric':(active['guardian']['watcher_pid'],active['supervisor']),'bootstrap':(active['child'],active['supervisor']),'helper':(ack['helper'],active['child'])}
 if role=='reference':roles['reference']=(active['child'],active['supervisor'])
 return {n:pyg.checked_receipt(d,n,op,pid,row['sha256'],p,ppid) for n,(pid,ppid) in roles.items()}
def facts(c,role):
 need(source(c['repo'])==c['source'],'source closure drift');operator.validate_invariance(c);src=c['source'];pins=pinset(c);q=checkpoint(c['checkpoint']);policy_row,_=python_policy(c,True)
 fixed=doc(path(c['input']));need(fixed['id']==154820 and fixed['bytes_hex']=='c45c0200' and fixed['batch']==1 and fixed['position']==0 and fixed['empty_state'] is True and fixed['max_new_tokens']==1 and fixed['sampling'] is False and fixed['model']==MODEL,'frozen input')
 ci=doc(path(c['ci']));rev=doc(path(c['review']));control=doc(path(c['controls']))
 if local_mode(c):
  operator.validate_ci(c,ci)
  operator.validate_review(c,rev,control)
 else:
  need(ci['head_sha']==src['head'] and ci['event']=='push' and ci['conclusion']=='success' and ci['run_attempt']==1,'ordinary CI receipt')
  need(rev['head']==src['head'] and rev['tree']==src['tree'] and rev['verdict']=='ACCEPT_FULL_FLASH_GOLDEN_SOURCE_SCOPE' and rev['method_accepted'] is True and rev['unresolved_blockers']==[] and rev['missing_coverage']==[] and rev['actual_model'] in ('claude-fable-5-2','gemini-4-carbon','gemini-4-astra') and rev['request_id'],'source/method review')
 need(control['head']==src['head'] and control['passed'] is True and control['failed']==0 and control['skipped_changed_controls']==0 and control['sandbox_golden_read_denied'] is True and control['resource_guard_verified'] is True and control['stage_admit_before_payload_verified'] is True and control['numerical_source_closure_pinned'] is True and control['runtime_sha256']==c['controls_runtime_sha256'],'composed host controls');need(control['python_policy_sha256']==policy_row['sha256'] and control['python_runtime_observed_controls_verified'] is True,'original prospectively observed controls')
 resources=doc(path(c['resource']));r=resources[role];need(set(r)=={'allocator','stage_model_ledger','harness','job_rss','combined','output_bytes','timeout','swap_growth','swap_samples','progress_seconds','evidence_reserve','transport','receipts'},'resource schema')
 need(all(type(x)is int and x>0 for x in r.values()) and r['combined']<=96*GIB and r['job_rss']+r['harness']<=r['combined'] and r['stage_model_ledger']<=r['job_rss'] and r['allocator']<=r['stage_model_ledger'] and r['transport']<=33734653 and r['receipts']<=2073600 and r['timeout']<=({'reference':28800,'native':7200}[role]) and r['swap_samples']<=3 and r['swap_growth']<=256<<20 and r['progress_seconds']<=300 and r['output_bytes']<=r['evidence_reserve']<=8*GIB,'resource limits')
 need(resources['whole_seconds']<=36000 and resources['reference']['timeout']+resources['native']['timeout']+600<=resources['whole_seconds'],'whole numerical time')
 if role=='native':need(r==operator.NATIVE_LIMITS,'frozen Studio019 native ledger')
 # Bind original five M1-M4 family claims, other old original claims, and Studio016.
 expected={'f020-m1a-continuation.claim.json','f020-m2b-copied-resident-v1.claim.json','f020-m3b-copied-weighted-v1.claim.json','f020-m4b-staged-weighted-v1.claim.json','f020-m4c-staged-policy-native-v1.claim.json','f020-studio-m1a-numerical.claim.json','f020-studio-m1b-screen.claim.json','studio016-real-flash-expert-initial.claim.json'}
 need({Path(n).name for n in c['prior_claims']}==expected and len(c['prior_claims'])==len(expected),'historical population')
 original={'f020-m1a-continuation.claim.json': 'd9643b58a4c6687bee658e775f22ca12ba53e979026226a4fb305e05364e19bf', 'f020-m2b-copied-resident-v1.claim.json': 'fc6cb8558c56a237e4fc97dc42b87ff0426fb2e85718cb1759c7941fc9770456', 'f020-m3b-copied-weighted-v1.claim.json': '3d85b128040dbe9fa4f17642400dd6c5dc97a76372904c227e17872e79b58f6d', 'f020-m4b-staged-weighted-v1.claim.json': '61659d90c4731accbda8a566d18e4946fa478793843bb106bb1fc5e53408ba48', 'f020-m4c-staged-policy-native-v1.claim.json': '2460f6722c8432ef2d4e23ed750249d305f429c2fc56c51ba7748b717a5b7504', 'f020-studio-m1a-numerical.claim.json': 'c14a8d805ee34c00ecffd5c3adf8ced2b6e606f98bd89bb682afaabcdaa1893d', 'f020-studio-m1b-screen.claim.json': '93250c6d4da3f1a8167482c0c70f9f5e4a766e00caaab5a5860fd49e38f0d63b', 'studio016-real-flash-expert-initial.claim.json': 'a7dab9b37aaae361405018726da54e8b21ed19542f4d04178883ea6b60ab8315'}
 need({Path(n).name:h for n,h in c['prior_claims'].items()}==original,'historical identity')
 for n,h in c['prior_claims'].items():checked(path(n),h)
 rs=c['stages'][role];need(set(rs)=={'program','driver','image','python','array_roots','library_prefix'},'job execution schema')
 for n in ('program','image','python'):
  need(str(path(rs[n])) in {x['path'] for x in c['runtime_files'].values()},'unbound execution image '+n)
 need(str(SELF).startswith(c['repo']+'/') and str(SELF.relative_to(c['repo']))=='scripts/research/studio019_supervise.py','sealed physical entry')
 if role=='native':need(rs['driver'] is None and path(rs['program']).is_relative_to(c['build_root']) and rs['image']==rs['program'],'native original Cargo executable')
 else:need(path(rs['driver']).is_relative_to(c['repo']) and Path(rs['driver']).name=='studio017_ref_entry.py' and rs['program']==rs['python'],'reference entry')
 for p in rs['array_roots']:
  need(path(p).is_relative_to('/opt/homebrew') or path(p).is_relative_to('/Library/Frameworks') or (
       path(p).is_relative_to(Path.home()) and not path(p).is_relative_to(STATE) and not path(p).is_relative_to(ROOT) and not STATE.is_relative_to(path(p)) and not ROOT.is_relative_to(path(p))),'isolated runtime root')
 need(path(rs['library_prefix']).is_relative_to(Path.home()/'.local/pulsarmlx'),'native installation root')
 build=doc(path(c['build']));bdir=path(c['build_root']);artifact=path(c['stages']['native']['program'])
 need(build['source']==src['head'] and build['tree']==src['tree'] and build['exit']==0 and build['binary']==str(artifact) and build['binary_sha256']==digest(artifact) and build['ci_head']==src['head'],'original built source/binary')
 paths={v['path'] for v in c['artifacts'].values()}
 need(all(str(path(build[k])) in paths for k in ('cargo_stdout','intent','exit_record')),'original Cargo evidence pins')
 j=doc(path(build['intent']));ended=doc(path(build['exit_record']))
 need(j['op']==ended['op']==build['operation'] and ended['exit']==0 and j['cwd']==c['repo'] and j['timeout_s']<=1800 and j['env']['CARGO_TARGET_DIR']==str(bdir),'original cargo operation')
 av=j['argv'];need(av[0] in {v['path'] for v in c['runtime_files'].values()} and all(item in av for item in ('build','--offline','--locked','--release')) and (('-j' in av and av[av.index('-j')+1] in ('1','2')) or any(x in ('-j1','-j2','--jobs=1','--jobs=2') for x in av) or j['env'].get('CARGO_BUILD_JOBS') in ('1','2')),'bounded original Cargo build')
 messages=[parse(line) for line in read(path(build['cargo_stdout']),32<<20).splitlines()]
 arts=[v for v in messages if v.get('reason')=='compiler-artifact' and v.get('executable')==str(artifact)]
 need(len(arts)==1 and arts[0]['target']['kind']==['bin'] and arts[0]['profile']['test'] is False and messages[-1].get('reason')=='build-finished' and messages[-1].get('success') is True,'original Cargo artifact and success')
 need(build['original_artifact_sha256']==sha(enc(arts[0])),'original Cargo artifact sha')
 need(any(v['sha256']==rev['original_provider_stream_sha256'] for v in c['artifacts'].values()) and any(v['sha256']==rev['original_report_sha256'] for v in c['artifacts'].values()),'originating review records pinned')
 need(control['runtime_sha256']==sha(enc({k:v['sha256'] for k,v in sorted(c['runtime_files'].items())})),'control runtime closure')
 # Criteria, CI, resource and coverage originals must be among privately pinned artifacts.
 for k in ('input','criteria','review','ci','controls','resource','build'):
  need(str(path(c[k])) in {v['path'] for v in c['artifacts'].values()},'missing artifact '+k)
 common=dict(stage=role,run=c['run'],attempt='initial',source=src,revision=MODEL,source_custody_sha256=digest(Path(c['checkpoint'])/'receipt.json'),inventory_sha256=q['inventory_sha256'],input_sha256=digest(c['input']),criteria_sha256=digest(c['criteria']),review_sha256=digest(c['review']),ci_sha256=digest(c['ci']),controls_sha256=digest(c['controls']),resource_sha256=digest(c['resource']),config_sha256=digest(config_path(local_mode(c))),runtime_and_artifact_sha256=sha(enc(pins)),historical_claims_sha256=sha(enc(c['prior_claims'])),limits=r,one_cold_input=True,children=1)
 if local_mode(c):return common
 return dict(schema=authority.GRANT_SCHEMA,authority=authority.authority_binding(role),
             sshsig_verifier_sha256=digest(Path('/usr/bin/ssh-keygen')),**common)
def output_seal(out,cap,chmod=False,require_complete=True):
 out=path(out);m={};nb=0;need(stat.S_IMODE(out.stat().st_mode) in ((0o700,0o500) if chmod else (0o500,)) and len(list(out.iterdir()))<=1200,'output mode/count')
 for f in sorted(out.iterdir()):
  need(f.is_file() and not f.is_symlink() and (f.name in ('report.json','logits.f32') or re.fullmatch(r'[0-4][0-9]\.[a-z_]+(?:\.[a-z_]+)*\.f32',f.name)),'invalid output path')
  if chmod:
   before=f.lstat();need(stat.S_ISREG(before.st_mode) and before.st_nlink==1,'output hard link');os.chmod(f,0o400,follow_symlinks=False);need(os.path.samestat(before,f.lstat()),'output replaced while sealing')
  st=f.lstat();need(st.st_nlink==1 and stat.S_IMODE(st.st_mode)==0o400,'unsealed evidence')
  nb+=st.st_size;need(nb<=cap,'output limit');m[f.name]=dict(sha256=digest(f,cap),stamp=fdstamp(st))
 if chmod:os.chmod(out,0o500,follow_symlinks=False)
 if require_complete:need('report.json' in m and m.get('logits.f32',{}).get('stamp',[0,0,0])[2]==154880*4,'full logits')
 return m
def retained_result_source(files):
 # Same content projection as Sealed.finish(), independently derived from
 # authoritative supervisor file hashes/stamps (NOT the child's embedded report).
 projected={name:{'bytes':record['stamp'][2],'sha256':record['sha256']} for name,record in files.items()}
 return dict(files=len(projected),bytes=sum(v['bytes'] for v in projected.values()),
             manifest_sha256=sha(enc(projected)),report_sha256=projected.get('report.json',{}).get('sha256'))

def native_seal(d):
 complete=(d/'sealed.json').exists();partial=(d/'partial-sealed.json').exists()
 need(complete != partial,'exactly one original native seal')
 p=d/('sealed.json' if complete else 'partial-sealed.json')
 return p,doc(p),complete

def grading_inputs(c,role):
 need(role=='native','only diagnostic native pair grade')
 original_reference(c)
 d,out,_=layout(c,'native');seal_path,seal,complete=native_seal(d);numeric=doc(d/'numeric-exit.json');claim=doc(ANCHORS['native'])
 need(claim['stage']=='native' and claim['run']==c['run'] and claim['source']==c['source']['head']
      and claim['operation']==seal['operation']==numeric['operation'] and
      seal['claim_sha256']==digest(ANCHORS['native']) and numeric['clean_reap'] is True
      and seal['exit_sha256']==digest(d/'numeric-exit.json'),'original native process/claim')
 if complete:
  need(numeric['exit']==0 and numeric['completed'] and not numeric['residual_group_killed'],'complete native process')
  need(seal['native_images']==owner_native_images(c,d,ANCHORS['native']),'sealed native images')
 else:need(seal['complete'] is False,'partial is not a completed native stage')
 actual=output_seal(out,doc(c['resource'])['native']['output_bytes'],require_complete=complete);need(actual==seal['files'],'original native output')
 refdir,_,_=layout(c,'reference');refseal=doc(refdir/'sealed.json')
 return dict(reference=dict(seal_sha256=digest(refdir/'sealed.json'),claim_sha256=digest(REFERENCE_CLAIM),
                numeric_operation=refseal['operation'],content=retained_result_source(refseal['files'])),
             native=dict(seal_sha256=digest(seal_path),claim_sha256=digest(ANCHORS['native']),
                numeric_operation=seal['operation'],content=retained_result_source(actual)))

def grade_content_verified(c,role,before,result):
 now=grading_inputs(c,role)
 need(now==before,'grade inputs changed while reading')
 need(all(result[('source' if role=='reference' else target)]==v['content'] for target,v in now.items()),
      'grader read a different output population')
 return now

def audit_consumed_stage(c,role):
 d,_,cap=layout(c,role);claim=doc(ANCHORS[role])
 if local_mode(c):
  # After spend, re-read the actual admission and its original manifest. Do not create either again.
  bound=bound_envelope(c,role);ptr=operator.verified_manifest(c,role,bound)
  need(claim['schema']=='studio019-operator-local-claim/1' and claim['stage']==role and claim['authorization']==ptr
       and claim['run']==c['run'] and claim['source']==c['source']['head'] and claim['cap_sha256']==digest(cap)
       and claim['resource_sha256']==bound['resource_sha256'] and claim['operation']==doc(d/'intent.json')['operation']
       and doc(d/'intent.json')['authorization']==ptr,'original operator claim/manifest')
  return
 ptr=doc(STATE/(role+'-GRANT_POINTER'))
 raw=read(STATE/(role+'-grant-request.json'));pointer_matches_role(ptr,c['run'],role,raw)
 grant=parse(raw);remote_raw,side,sig=remote(ptr['commit'],ptr['path'])
 need(remote_raw==raw==enc(grant) and side==(sha(raw)+'  '+Path(ptr['path']).name+'\n').encode(),'original signed grant readback')
 need(grant['source']==c['source'] and grant['run']==c['run'] and grant['stage']==role,'original signed grant identity')
 authority.verify_supervisor(raw,sig)
 authority.original_spend(d,grant,ptr,claim)

def original_reference(c):
 expected=operator.original_reference_identity()
 d,out,_=layout(c,'reference')
 checked(d/'sealed.json',expected['seal_sha256'])
 checked(d/'eligibility.json',expected['eligibility_sha256'])
 checked(REFERENCE_CLAIM,expected['claim_sha256'])
 sealed=doc(d/'sealed.json');claim=doc(REFERENCE_CLAIM);end=doc(d/'numeric-exit.json')
 need(claim['stage']=='reference' and claim['run']=='6855f3a4414e4dc31a5bcd7dbbd5d173b4656ac6fdf9cf2fd00eaa2027124f98'
      and claim['source']=='12016240580488620d41f34141c1450353fe4f39'
      and claim['operation']==sealed['operation']==end['operation']=='84bca402c0066d03b211cf24f6259ef3'
      and end['exit']==0 and end['completed'] and end['clean_reap'] and not end['residual_group_killed']
      and sealed['exit_sha256']==digest(d/'numeric-exit.json')
      and sealed['claim_sha256']==digest(REFERENCE_CLAIM),'original reference execution')
 actual=output_seal(out,doc(c['resource'])['reference']['output_bytes'])
 need(actual==sealed['files'] and actual['logits.f32']['sha256']==expected['full_logits_sha256'],'original reference bytes')
 accepted=doc(d/'eligibility.json');result=accepted['result']
 need(accepted['eligible'] is False and result['eligible'] is False and result['token']['eligible'] is True
      and sorted(int(k) for k,v in result['route_gates'].items() if not v['eligible'])==[23,33,34]
      and len(result['route_gates'])==42 and accepted['operation']==claim['operation']
      and accepted['seal_sha256']==expected['seal_sha256'] and result['source']==retained_result_source(actual),
      'original negative eligibility preserved')
 need(result==doc(d/'eligibility.stdout'),'original eligibility stdout')
 return expected

def fixture_enter(role,args,operation,policy,digest,receipt):
 import studio019_ack_fixture
 return studio019_ack_fixture.enter(role,args,operation,policy,digest,receipt)

def bound_envelope(c,role):
 need(local_mode(c),'explicit diagnostic operator mode')
 x=facts(c,role)
 golden=original_reference(c) if role=='native' else None
 if local_mode(c):return operator.manifest(c,role,x,golden)
 if golden is not None:x['golden']=golden
 return x
def envelope(c,role):
 need(local_mode(c),'explicit diagnostic operator mode')
 need(role=='native' and not os.path.lexists(ANCHORS[role]),'spent claim; reconcile original, no retry')
 need(role=='native','reference executions unavailable')
 return bound_envelope(c,role)
def freeze_operator(c,role):
 need(local_mode(c),'explicit operator config required')
 # put uses O_EXCL, no-follow, fsync(file) and fsync(directory). An existing manifest is only read back.
 lifecycle_gate(c);x=envelope(c,role);operator.validate_ci(c,doc(c['ci']),live=True)
 f=operator.manifest_path(role)
 need(not os.path.lexists(layout(c,role)[0]),'stage directory already exists; reconcile')
 if not os.path.lexists(f):put(f,x)
 return operator.verified_manifest(c,role,x)
def request_name(run,role):return STEM+'__'+run+'__'+role+'-initial-grant.json'
def pointer_matches_role(ptr,run,role,raw):
 # Check field and role binding only. This helper never authorizes publication or spend.
 need(role in ROLES and set(ptr)=={'commit','path','sha256'} and hexid(ptr['commit'],40) and ptr['path']==request_name(run,role) and ptr['sha256']==sha(raw),'pointer fields/binding')

def verified(c,role):
 x=envelope(c,role);ci=doc(c['ci']);need(type(ci.get('id'))is int and ci['id']>0,'ordinary CI run ID')
 if local_mode(c):
  operator.validate_ci(c,ci,live=True)
  return x,operator.verified_manifest(c,role,x)
 live=parse(cmd(['/opt/homebrew/bin/gh','api','repos/MahdiHedhli/PulsarMLX/actions/runs/'+str(ci['id'])+'/attempts/1'],timeout=40))
 need(live['head_sha']==x['source']['head'] and live['id']==ci['id'] and live['run_attempt']==1 and live['event']=='push' and live['conclusion']=='success' and live['head_branch']=='codex/studio017-full-flash-golden-token','ordinary CI original API')
 local=STATE/(role+'-grant-request.json');raw=read(local);need(raw==enc(x),'changed original request')
 ptr=doc(STATE/(role+'-GRANT_POINTER'));pointer_matches_role(ptr,c['run'],role,raw)
 b,side,signature=remote(ptr['commit'],ptr['path'])
 need(b==raw and side==(sha(raw)+'  '+Path(ptr['path']).name+'\n').encode(),'immutable grant/sidecar')
 authority.grant_identity(x,ptr)
 authority.verify_supervisor(raw,signature)
 return x,ptr
def admission(c,role,r):
 ha=pressure();need(ha['pressure']==1 and ha['headroom']>=16*GIB+r['combined'],'host reserve')
 rows=cohort();names={Path(c['stages'][k]['program']).name for k in ROLES if k=='native'}|{'qualify-real-flash-expert','llama-server','mlx_lm.generate','llama-cli','mlx_lm.server'}
 need(not any(Path(q[4]).name in names|{'cargo','rustc','clang','clang++','llama-run','ollama_llama_server'} or Path(q[4]).name.startswith('qualify-') or (Path(q[4]).name.lower().startswith(('python','ollama','llama','mlx')) and q[3]*1024>=512<<20) for q in rows if q[0]!=os.getpid()),'other active or substantial unclassified numerical/build worker')
 ev,bu=census(STATE,path(c['build_root']));need(bu<=20*GIB and ev+r['evidence_reserve']<=8*GIB and shutil.disk_usage(STATE).free>=r['evidence_reserve']+GIB,'disk admission')
 return ha
def runtime_dirs(c,role,cap,out,claim):
 rs=c['stages'][role];r=c['repo']
 # Source, staged capability, and original checkpoint are the only task data visible to the job. No golden, no complete state or private supervisor grants.
 row,p=python_policy(c);rd=[r,str(ROOT),rs['library_prefix'],*p['roots'],str(cap.parent/'cache-bootstrap'),str(cap.parent/'cache-helper'),*([str(cap.parent/'cache-reference')] if role=='reference' else []),'/System/Library','/usr/lib','/usr/share','/Library/Apple','/usr/bin','/bin','/dev','/private/var/db/dyld']
 files=[row['path'],*p['images'],rs['program'],rs['python'],rs['image'],str(cap),str(cap.parent/'active.json'),str(claim),c['input'],str(SELF)]
 files += [str(Path(c['checkpoint'])/n) for n in ('inventory.json','witnesses.json','receipt.json')]
 return rd,files
def profile(c,role,cap,out,claim):
 rd,files=runtime_dirs(c,role,cap,out,claim)
 roles=('bootstrap','helper','reference') if role=='reference' else ('bootstrap','helper')
 return child_profile(rd,files,out,[pyg.rolepath(cap.parent,n) for n in roles])
def child_profile(rd,files,out,receipt_paths):
 def literal(x):return json.dumps(str(x),ensure_ascii=False)
 ancestors={str(y) for f in [*rd,*files,out] for y in Path(f).parents};allow=' '.join('(literal '+literal(y)+')' for y in sorted(ancestors))+' '+' '.join('(subpath '+literal(x)+')' for x in rd)+' '+' '.join('(literal '+literal(x)+')' for x in files)
 # Each dedicated original attestation is the only writable named path outside numerical outputs.
 writes=' '.join('(literal '+literal(p)+')' for p in receipt_paths)
 return ('(version 1)\n(allow default)\n(deny network*)\n(deny file-read*)\n(deny file-write*)\n(allow file-read-metadata)\n(import "dyld-support.sb")\n(allow file-read* '+allow+')\n(allow file-read* file-write* (subpath '+literal(out)+'))\n(allow file-read* file-write* '+writes+')\n(allow file-write-data (literal "/dev/null"))\n').encode()
def child(cap_path):
 cap=path(cap_path);v=doc(cap);role=v['stage'];need(role in ROLES and cap==STATE/('campaign-'+role)/'child-cap.json','stage cap location')
 need(role=='native' and v['schema']=='studio019-child-cap/1' and v['task']==TASK,
      'diagnostic task/role')
 claim=doc(ANCHORS[role])
 need(claim['schema']=='studio019-operator-local-claim/1' and
      claim['stage']=='native' and claim['cap_sha256']==digest(cap) and
      claim['source']==v['source']['head'] and claim['run']==v['run'] and
      v['native_image_source']==v['source'] and
      claim['binary_sha256']==digest(path(v['expected_image'])) and
      v['expected_image']==v['native_image_policy']['program'],
      'diagnostic source/binary/claim')
 acknowledge_child(cap,v,ANCHORS[role])
 result={k:v[k] for k in ('stage','operation','run','model_root','checkpoint_receipt','inventory','witnesses','input','pins','output','prefix','libs')}
 if role=='native':result['native_image_policy']=v['native_image_policy']
 return result
HELPER_REPLY_SECONDS=20
def acknowledge_child(cap,v,claim_path):
 claim=doc(claim_path);a=doc(cap.parent/'active.json');need(a['cap_sha256']==digest(cap) and claim['operation']==v['operation']==a['operation'] and claim['run']==v['run'] and a['claim_sha256']==digest(claim_path),'live cap/claim binding')
 pid=os.getppid();need(a['child']==pid==os.getpgid(pid) and os.getsid(pid)==os.getsid(claim['supervisor']) and os.getpid()!=pid,'direct active numerical parent')
 need(claim['supervisor']==a['supervisor'] and os.getpgid(claim['supervisor'])!=pid and procpath(pid)==v['expected_image'] and procpath(claim['supervisor'])==v['supervisor_image'],'process identity')
 # Full birth/ppid checked by external owner on acknowledgement (set-id ps is not executable under SBPL).
 need(not os.path.lexists(cap.parent/'numeric-exit.json'),'ended attempt')
 # Only authenticated original capability is consumed; no golden paths, logits, routes or token expectation.
 channel=socket.socket(fileno=int(os.environ['STUDIO017_ADMIT_CHANNEL']));channel.settimeout(HELPER_REPLY_SECONDS)
 challenge=enc(dict(helper=os.getpid(),worker=pid,operation=v['operation'],cap_sha256=digest(cap),nonce=secrets.token_hex(16)))
 sent=time.monotonic_ns();channel.sendall(challenge);reply=channel.recv(256);received=time.monotonic_ns()
 channel.close();need(reply==sha(challenge).encode(),'owner denied child admission')
 return sent,received
def startup_barrier(cap,fd):
 # Trusted tiny bootstrap waits for durable active child identity before exec; not a grant.
 need(os.read(fd,1)==b'G','missing startup authorization');os.close(fd)
 v=doc(path(cap));need(os.getpid()==os.getpgrp() and os.getsid(0)==os.getsid(v['supervisor']) and os.getpgid(v['supervisor'])!=os.getpgrp() and v['supervisor']==os.getppid(),'detached/stale worker')
 return v
def capsule_exec(cap,fd):
 return startup_barrier(cap,fd)['argv'] # py_gate writes the original bootstrap census immediately before exec.
def approved_libraries(c,rs):
 pref=path(rs['library_prefix']);w={v['path']:v['sha256'] for v in c['runtime_files'].values()};return {n:w[str(pref/'lib'/n)] for n in ['libmlx.dylib','libmlxc.dylib','libjaccl.dylib']}
def native_image_policy(c,rs,python_policy):
 program=str(path(rs['program']));lib=path(rs['library_prefix'])/'lib'
 paths=[program,*[str(lib/n) for n in approved_libraries(c,rs)]]
 pins={row['path']:row['sha256'] for row in c['runtime_files'].values()}
 return dict(program=program,platform_cache_uuid=python_policy['platform_cache_uuid'],noncache_images={p:pins[p] for p in paths})
def owner_native_images(c,d,claim_path):
 # The owner rederives the image policy from its admission inputs after reap.
 row,python=python_policy(c)
 expected=native_image_policy(c,c['stages']['native'],python)
 for filename,value in expected['noncache_images'].items():checked(path(filename),value)
 def evidence(file):
  raw=read(file);return parse(raw),sha(raw)
 claim,claim_hash=evidence(claim_path);cap,cap_hash=evidence(d/'child-cap.json')
 active,active_hash=evidence(d/'active.json');admitted,admitted_hash=evidence(d/'admitted.json')
 end,end_hash=evidence(d/'numeric-exit.json')
 op=hexid(claim['operation'],32);pid=end['pid']
 src={k:hexid(c['source'][k],40) for k in ('head','tree')}
 need(claim['stage']==cap['stage']==admitted['stage']=='native' and claim['run']==cap['run']==c['run']
      and claim['source']==src['head'] and cap['native_image_source']==src, 'native census source or run')
 need(op==cap['operation']==active['operation']==admitted['operation']==end['operation']
      and claim['supervisor']==active['supervisor']==cap['supervisor'] and pid==active['child']==admitted['worker']
      and end['child_admitted'] is True and end['completed'] is True and end['clean_reap'] is True
      and end['residual_group_killed'] is False and end['exit']==0, 'native census process custody')
 need(claim_hash==active['claim_sha256']==admitted['claim_sha256']==end['claim_sha256']
      and cap_hash==claim['cap_sha256']==active['cap_sha256']==admitted['cap_sha256'], 'native census capability custody')
 need(cap['expected_image']==expected['program'] and cap['native_image_policy']==expected
      and cap['python_gate']==dict(interpreter=python['interpreter'],policy=row['path'],sha256=row['sha256']),
      'native census differs from owner policy')
 observed=checked_observations(d/'stdout',active['native_stdout_inode'],expected,op,pid)
 return dict(schema='studio017-owner-native-images/1',source=src,run=c['run'],operation=op,pid=pid,
             claim_sha256=claim_hash,cap_sha256=cap_hash,policy_sha256=sha(enc(expected)),
             active_sha256=active_hash,admitted_sha256=admitted_hash,
             numeric_exit_sha256=end_hash,scope='dyld images at both snapshots',
             python_policy_sha256=row['sha256'],**observed)
def ref_entry(c,rs,role,cap,out,op,b):
 if role=='native':return [rs['program'],'--studio019-route-b',str(cap),str(out)]
 return pyg.cli(b['interpreter'],cap.parent/'cache-reference',pyg.SELF,'reference',b['policy'],b['sha256'],pyg.rolepath(cap.parent,'reference'),op,[cap,out])
def image_pin(c,p):return str(path(p)) in {v['path'] for v in c['runtime_files'].values()}
def cleanup(child):
 # A teardown failure cannot be a successful campaign. Retain original return code.
 try:os.killpg(child.pid,signal.SIGKILL);left=True
 except ProcessLookupError:left=False
 child.wait(timeout=10)
 stop=time.monotonic()+5
 while True:
  try:os.killpg(child.pid,0);exists=True
  except ProcessLookupError:exists=False
  if not exists or time.monotonic()>=stop:break
  time.sleep(.05)
 return left,not exists
def poll_ack(parent,p,c,role,cap):
 accept_ack(parent,p,c,role,cap,ANCHORS[role])
def accept_ack(parent,p,c,role,cap,claim_path):
 parent.settimeout(3);msg=parent.recv(4096);q=parse(msg);need(len(msg)<1024 and set(q)=={'helper','worker','operation','cap_sha256','nonce'} and hexid(q['nonce'],32) and q['worker']==p.pid and q['operation']==c['operation'] and q['cap_sha256']==digest(cap),'worker ack fields')
 helper=q['helper'];need(type(helper)is int and helper>1 and os.getpgid(helper)==p.pid and os.getsid(helper)==os.getsid(p.pid)==os.getsid(0) and int(cmd(['/bin/ps','-p',str(helper),'-o','ppid=']))==p.pid,'helper ancestry')
 need(procpath(p.pid)==c['expected_image'] and procpath(helper)==c['supervisor_image'],'live helper/worker executable')
 a=doc(cap.parent/'active.json')
 need(int(cmd(['/bin/ps','-p',str(p.pid),'-o','ppid=']))==os.getpid()==a['supervisor'] and cmd(['/bin/ps','-p',str(p.pid),'-o','lstart=']).decode().strip()==a['birth'],'actual worker ancestry/birth')
 put(cap.parent/'admitted.json',dict(stage=role,operation=c['operation'],worker=p.pid,helper=helper,challenge_sha256=sha(msg),cap_sha256=q['cap_sha256'],claim_sha256=digest(claim_path)))
 parent.sendall(sha(msg).encode());parent.close()
def physical_lease_hold():
 # No numerical admission via NEW code until combined BLK1 bootstraps, orphan/timeout,
 # stop and output-mutation controls are physically measured and independently reviewed.
 # This source revision cannot consume either role. This is not an external spend register.
 raise ValueError('physical lifecycle proof for this combined runtime not established')

def restricted_aux_profile(c,parent,role,read_dirs):
 row,pol=python_policy(c);rd=[*pol['roots'],str(parent/('cache-'+role)),*map(str,read_dirs),'/System/Library','/usr/lib','/usr/share','/Library/Apple','/usr/bin','/bin','/dev','/private/var/db/dyld']
 fs=[row['path'],*pol['images'],pol['interpreter'],str(pyg.SELF),str(pyg.rolepath(parent,role))]
 need(not any(ROOT.is_relative_to(Path(v)) or Path(v).is_relative_to(ROOT) for v in rd+fs),'aux cannot read payload root')
 ancestors={str(y) for v in rd+fs for y in Path(v).parents}
 filt=' '.join('(literal '+json.dumps(n)+')' for n in sorted(ancestors))+ ' '+' '.join('(subpath '+json.dumps(n)+')' for n in rd)+' '+' '.join('(literal '+json.dumps(n)+')' for n in fs)
 return ('(version 1)\n(allow default)\n(deny network*)\n(deny file-read*)\n(deny file-write*)\n(allow file-read-metadata)\n(import "dyld-support.sb")\n(allow file-read* '+filt+')\n(allow file-write* (literal '+json.dumps(str(pyg.rolepath(parent,role)))+'))\n(allow file-write-data (literal "/dev/null"))\n').encode()

def aux_profile_file(c,d,role,reads):
 p=d/(role+'.sb');fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_WRONLY,0o400)
 with os.fdopen(fd,'wb') as f:f.write(restricted_aux_profile(c,d,role,reads));f.flush();os.fsync(f.fileno())
 return p

def attach_guard(c,d,worker,deadline,op,name,stderr):
 row,pol=python_policy(c);pyg.fresh_cache(d/('cache-'+name));sb=aux_profile_file(c,d,name,[])
 def command(fd):
  # Same validated/pinned interpreter/image/import roots and prospective cache policy as the workers.
  return ['/usr/bin/sandbox-exec','-f',str(sb),*pyg.cli(pol['interpreter'],d/('cache-'+name),pyg.SELF,name,row['path'],row['sha256'],pyg.rolepath(d,name),op,[fd,worker.pid,os.getpid(),repr(deadline)])]
 return Lease.attach(worker,deadline,pol['interpreter'],SELF.with_name('studio017_lease.py'),
                     {'HOME':str(Path.home()),'PATH':'/usr/bin:/bin'},d,stderr,command)

def members(pg):return [p[0] for p in cohort() if p[2]==pg]

def end_owned(proc,lease,success):
 if lease is None:
  # Gate was never released. Signal only original direct unreaped worker, never an old PGID.
  if proc.poll() is None:proc.kill()
  proc.wait(8);return False,False
 # The lease is authority for this direct worker only. A mismatched or failed
 # lease cannot establish a reap fact for another process.
 if lease.group!=proc.pid:return False,False
 try:left,clean=lease.finish(proc,success,members)
 except Exception:return False,False
 if success or clean:return left,clean
 # Lease.finish deliberately reports abort as unclean. Observe its completed
 # cleanup here without adding signals or using a cached PGID as authority.
 try:
  worker_exit=proc.wait(0);watcher_exit=lease.guard.wait(0)
  if type(worker_exit) is not int or worker_exit!=proc.returncode or watcher_exit!=-signal.SIGKILL:return left,False
  until=time.monotonic()+2
  while members(lease.group) and time.monotonic()<until:time.sleep(.02)
  return left,not members(lease.group)
 except Exception:return left,False

def lifecycle_gate(c):
 if not local_mode(c):physical_lease_hold()
 else:
  operator.validate_config(c)
  operator.validate_lifecycle(c,doc(c['review']),doc(c['controls']))

def run_numeric(conf,stage,selected=False):
 need(selected and stage=='native','only explicit Studio019 native diagnostic')
 c=load_cfg(conf,selected);lifecycle_gate(c)
 g,ptr=verified(c,stage);limits=g['limits'];before=admission(c,stage,limits)
 d,out,cap=layout(c,stage);need(not os.path.lexists(d),'existing original operation directory; reconcile')
 if stage=='native':
  refx=doc(layout(c,'reference')[0]/'numeric-exit.json')
  available=doc(c['resource'])['whole_seconds']-refx['seconds'];need(available>=limits['timeout'],'remaining total numerical time')
 # Only one heavy owner: hold same physical lock through both admission and stage. The initial
 # remote slot is the irreversible allowance. The local anchor retains evidence.
 lock_path=STATE/'heavy.lock';lf=os.open(lock_path,os.O_CREAT|os.O_NOFOLLOW|os.O_RDWR,0o600)
 try:
  need(stat.S_ISREG(os.fstat(lf).st_mode) and os.fstat(lf).st_uid==os.getuid(),'lock role');fcntl.flock(lf,fcntl.LOCK_EX|fcntl.LOCK_NB)
  need(envelope(c,stage)==g,'admission changed while acquiring exclusive lock')
  before=admission(c,stage,limits)
  try:
   run_locked(c,stage,g,ptr,before,limits,d,out,cap)
  except BaseException as execution_error:
   if (os.path.lexists(ANCHORS['native']) and out.exists() and not (d/'sealed.json').exists()
       and (d/'numeric-exit.json').exists() and doc(d/'numeric-exit.json')['clean_reap'] is True):
    files=output_seal(out,limits['output_bytes'],True,False)
    put(d/'partial-sealed.json',dict(operation=doc(ANCHORS['native'])['operation'],claim_sha256=digest(ANCHORS['native']),
        exit_sha256=digest(d/'numeric-exit.json') if (d/'numeric-exit.json').exists() else None,
        files=files,complete=False))
    # A failed run is never relaunched. Compare available bytes only after positive
    # reaping; an uncertain process outcome remains held for reconciliation.
    if (d/'numeric-exit.json').exists() and doc(d/'numeric-exit.json')['clean_reap'] is True:
     try:grade_original(c,stage)
     except BaseException as grade_error:
      put(d/'partial-grade-failure.json',dict(execution_error=str(execution_error),grade_error=str(grade_error)))
   raise
 finally:os.close(lf)
def spend_operator(c,role,bound,identity,op,cap):
 need(local_mode(c) and operator.verified_manifest(c,role,bound)==identity,'operator manifest changed at spend')
 put(ANCHORS[role],dict(schema='studio019-operator-local-claim/1',stage=role,run=c['run'],
      source=c['source']['head'],operation=hexid(op,32),supervisor=os.getpid(),authorization=identity,
      cap_sha256=digest(cap),resource_sha256=bound['resource_sha256'],binary_sha256=digest(c['stages']['native']['program'])))
def run_locked(c,role,g,ptr,before,r,d,out,cap):
 rs=c['stages'][role];op=secrets.token_hex(16);d.mkdir(mode=0o700);out.mkdir(mode=0o700)
 exe=Path(sys.executable).resolve(strict=True);supimg=procpath(os.getpid());need(image_pin(c,exe) and image_pin(c,supimg),'supervisor interpreter and image bound');claim=ANCHORS[role]
 row,p=python_policy(c,True);pb=dict(interpreter=p['interpreter'],policy=row['path'],sha256=row['sha256']);pyroles=('bootstrap','helper','reference') if role=='reference' else ('bootstrap','helper')
 for n in pyroles:pyg.fresh_cache(d/('cache-'+n))
 profile_raw=profile(c,role,cap,out,claim)
 sp=d/'policy.sb';sp.write_bytes(profile_raw);sp.chmod(0o400)
 v=dict(schema='studio019-child-cap/1',task=TASK,source={k:c['source'][k] for k in ('head','tree')},stage=role,run=c['run'],operation=op,supervisor=os.getpid(),supervisor_image=supimg,expected_image=rs['image'],python_gate=pb,argv=ref_entry(c,rs,role,cap,out,op,pb),model_root=str(ROOT),checkpoint_receipt=str(Path(c['checkpoint'])/'receipt.json'),inventory=str(Path(c['checkpoint'])/'inventory.json'),witnesses=str(Path(c['checkpoint'])/'witnesses.json'),input=c['input'],pins=r,output=str(out),prefix=rs['library_prefix'],libs=approved_libraries(c,rs))
 if role=='native':
  v['native_image_policy']=native_image_policy(c,rs,p)
  v['native_image_source']={k:c['source'][k] for k in ('head','tree')}
 binding={'authorization':ptr} if local_mode(c) else {'grant':ptr}
 put(cap,v);put(d/'intent.json',dict(operation=op,run=c['run'],stage=role,supervisor=os.getpid(),
             config_sha256=g['config_sha256'],limits=r,profile_sha256=sha(profile_raw),**binding))
 # Recheck every mutable admission after readback, before spending attempt.
 need(envelope(c,role)==g,'final renewed admission');before=admission(c,role,r)
 if local_mode(c):
  # No network transaction or signature is represented. Recheck all inputs under the
  # owner's heavy lock; exclusive creation at the original fixed path spends the local attempt.
  need(verified(c,role)==(g,ptr),'direct authorization or admission drift')
  lifecycle_gate(c);before=admission(c,role,r)
  spend_operator(c,role,g,ptr,op,cap)
 else:
  # An ambiguous receipt or later admission failure may already have spent the remote slot.
  # Never submit a second challenge to recover this operation.
  remote_spend=authority.consume_before_launch(d,g,ptr,op)
  need(verified(c,role)==(g,ptr),'grant or admission drift after remote spend')
  before=admission(c,role,r)
  put(claim,dict(schema='studio017-initial-claim/2',stage=role,run=c['run'],source=c['source']['head'],operation=op,supervisor=os.getpid(),grant=ptr,remote_spend=remote_spend,cap_sha256=digest(cap),resource_sha256=g['resource_sha256']))
 started=time.monotonic();deadline=started+r['timeout'];gate_ro,gate_wr=os.pipe();parent,passed=socket.socketpair(type=socket.SOCK_DGRAM)
 env={'HOME':str(Path.home()),'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C','STUDIO017_ADMIT_CHANNEL':str(passed.fileno()),'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','VECLIB_MAXIMUM_THREADS':'1','TMPDIR':str(out)}
 # Binding relies on installed rpaths. Do not inject global DYLD_ overrides; original path must pass controlled host linkage tests.
 argv=['/usr/bin/sandbox-exec','-f',str(sp),*pyg.cli(exe,d/'cache-bootstrap',pyg.SELF,'bootstrap',pb['policy'],pb['sha256'],pyg.rolepath(d,'bootstrap'),op,[cap,gate_ro])]
 for n in ('stderr','stdout','monitor.jsonl'):
  fd=os.open(d/n,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
 o=(d/'stdout').open('ab',buffering=0);e=(d/'stderr').open('ab',buffering=0);m=(d/'monitor.jsonl').open('ab',buffering=0)
 def limit_output():
  resource.setrlimit(resource.RLIMIT_FSIZE,(r['output_bytes'],r['output_bytes']))
 proc=None;lease=None;monitor=None;success=False;ok_ack=False;old={};reason='unknown';clean=False;left=False;endcode=None
 cleaning=False
 watchdog=ProgressDeadline(deadline,r['progress_seconds'],abort=lambda:abort_channel(lease.channel) if lease is not None else None)
 witnesses=Witnesses(out)
 def rearm():
  # A stale earlier timer is harmless: the handler rechecks the latched deadline.
  signal.setitimer(signal.ITIMER_REAL,watchdog.remaining())
  watchdog.check()
 def cancel(sig,fr):
  if sig==signal.SIGALRM:
   try:watchdog.check()
   except TimeoutError:
    if not cleaning:raise
    return
   if not cleaning:rearm()
   return
  watchdog.cancel('termination signal '+str(sig))
  if not cleaning:raise TimeoutError('owned stage cancelled')
 try:
  for sig in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP,signal.SIGALRM):old[sig]=signal.signal(sig,cancel)
  signal.setitimer(signal.ITIMER_REAL,r['timeout'])
  proc=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=o,stderr=e,cwd=str(out),env=env,pass_fds=(gate_ro,passed.fileno()),preexec_fn=limit_output,process_group=0)
  os.close(gate_ro);gate_ro=-1;passed.close()
  lease=attach_guard(c,d,proc,deadline,op,'lease-numeric',e)
  born=cmd(['/bin/ps','-p',str(proc.pid),'-o','lstart=']).decode().strip()
  active=dict(guardian=lease.receipt(),operation=op,supervisor=os.getpid(),child=proc.pid,birth=born,cap_sha256=digest(cap),claim_sha256=digest(claim))
  if role=='native':
   stdout_stat=os.fstat(o.fileno());active['native_stdout_inode']=[stdout_stat.st_dev,stdout_stat.st_ino]
  put(d/'active.json',active)
  # Empty output and pinned directory are checked before controlled release.
  need(not any(out.iterdir()),'output populated before release')
  watchdog.release();rearm()
  os.write(gate_wr,b'G');os.close(gate_wr);gate_wr=-1
  monitor=StageMonitor(c,ROOT,out,m,r,before,started,deadline,watchdog,witnesses,rearm)
  def check_ack():
   return poll_ready_ack(parent,proc,v,role,cap,claim)
  while proc.poll() is None:
   monitor.iteration(lease,proc,check_ack)
   ok_ack=monitor.ack
  watchdog.check()
  endcode=proc.returncode;need(ok_ack and endcode==0 and time.monotonic()<deadline,'numerical process failed or timed out')
  watchdog.stop()
  success=True;reason='returned'
 except BaseException as err:
  watchdog.cancel(type(err).__name__+': '+str(err))
  reason=type(err).__name__+': '+str(err);raise
 finally:
  # Keep cleanup and positive-reap records even when cancellation was raised mid-helper.
  cleaning=True
  try:watchdog.stop()
  except TimeoutError:success=False
  if watchdog.cancelled:success=False
  signal.setitimer(signal.ITIMER_REAL,0)
  if proc is not None:left,clean=end_owned(proc,lease,success);endcode=proc.returncode
  for sig,prev in old.items():signal.signal(sig,prev)
  for f in (o,e,m):f.close()
  if gate_ro>=0:os.close(gate_ro)
  if gate_wr>=0:os.close(gate_wr)
  if monitor is not None:ok_ack=monitor.ack
  parent.close();passed.close();put(d/'numeric-exit.json',dict(operation=op,claim_sha256=digest(claim),pid=proc.pid if proc else None,exit=endcode,seconds=time.monotonic()-started,completed=success and clean and not left and not watchdog.cancelled,guardian_exit=(lease.guard.returncode if lease is not None else None),clean_reap=clean,residual_group_killed=left,child_admitted=ok_ack,reason=reason))
 need(success and clean and not left and not watchdog.cancelled,'unreaped group');need(source(c['repo'])==c['source'],'source drift after child');checkpoint(c['checkpoint']);pinset(c)
 # Reapply output budget to terminal samples including processes that exit between polls.
 ev,bu=census(STATE,path(c['build_root']));need(ev<=8*GIB and bu<=20*GIB,'terminal budgets')
 need(c['source']==source(c['repo']) and checkpoint(c['checkpoint'])['revision']==MODEL,'terminal source/checkpoint drift')
 seal=dict(operation=op,claim_sha256=digest(claim),runtime_receipts=python_originals(c,role,d,op),exit_sha256=digest(d/'numeric-exit.json'))
 if role=='native':seal['native_images']=owner_native_images(c,d,claim)
 seal['files']=output_seal(out,r['output_bytes'],True);put(d/'sealed.json',seal)
 grade_original(c,role)
def poll_ready_ack(parent,worker,payload,role,cap,claim):
 if not select.select([parent],[],[],.1)[0]:return False
 accept_ack(parent,worker,payload,role,cap,claim)
 return True

class StageMonitor:
 """One complete supervised iteration, from guardian heartbeat through the next poll delay."""
 def __init__(self,config,witness_root,out,stream,limits,before,started,deadline,watchdog=None,witnesses=None,rearm=lambda:None):
  self.config=config;self.witness_root=witness_root;self.out=out;self.stream=stream
  self.limits=limits;self.before=before;self.started=started;self.deadline=deadline
  self.last_source=started;self.ack=False;self.over=0
  self.watchdog=watchdog;self.witnesses=witnesses;self.rearm=rearm

 def iteration(self,lease,worker,check_ack):
  if self.watchdog is not None:self.watchdog.check()
  lease.pulse()
  c=self.config;r=self.limits
  if time.monotonic()-self.last_source>=30:
   need(git(c['repo'],'rev-parse','HEAD').decode().strip()==c['source']['head'] and
        not git(c['repo'],'status','--porcelain=v1','--untracked-files=all'),'source drift during numerical child')
   for name,stamp in doc(Path(c['checkpoint'])/'witnesses.json').items():
    need(fdstamp((self.witness_root/name).lstat())==stamp,'checkpoint drift during numerical child')
   self.last_source=time.monotonic()
  if not self.ack:self.ack=check_ack()
  ph=pressure();rows=cohort();group=[x for x in rows if x[2]==worker.pid]
  direct=sum(x[3]*1024 for x in group if x[0]==worker.pid)
  rss=sum(x[3]*1024 for x in group)+sum(x[3]*1024 for x in rows if x[0]==os.getpid())
  elapsed=time.monotonic()-self.started
  ev,bu=census(STATE,path(c['build_root']))
  progress=[f for f in self.out.iterdir() if f.is_file()]
  size=sum(f.lstat().st_size for f in progress)
  self.over=self.over+1 if ph['swap']-self.before['swap']>r['swap_growth'] else 0
  self.stream.write(enc(dict(seconds=elapsed,numeric_pid=worker.pid,rss_group_plus_supervisor=rss,
                 job_rss=direct,job_children=len(group),output_bytes=size,produced_files=len(progress),
                 latest_completed_file=max(progress,key=lambda f:f.lstat().st_mtime_ns).name if progress else None,
                 state_bytes=ev,build_bytes=bu,**ph)))
  need(ha_ok(ph,r,self.before,self.over,rss,direct) and ev<=8*GIB and bu<=20*GIB and
       size<=r['output_bytes'] and time.monotonic()<self.deadline and (self.ack or elapsed<60),
       'observed resource/timeout/admission')
  if self.watchdog is not None:
   self.watchdog.observe(self.witnesses);self.rearm()
  time.sleep(.5)
  if self.watchdog is not None:self.watchdog.check()

def ha_ok(ph,r,before,over,rss,direct):
 return ph['pressure']==1 and ph['headroom']>=16*GIB and over<r['swap_samples'] and rss<=r['combined'] and direct<=r['job_rss'] and rss-direct<=r['harness']
def grade_original(c,role):
 lifecycle_gate(c)
 audit_consumed_stage(c,role)
 d,out,_=layout(c,role);seal_path,seal,complete=native_seal(d)
 need(seal['files']==output_seal(out,doc(c['resource'])[role]['output_bytes'],require_complete=complete) and seal['claim_sha256']==digest(ANCHORS[role]),'sealed original')
 ex=doc(d/'numeric-exit.json');need(ex['clean_reap'] is True and ex['operation']==seal['operation'] and seal['exit_sha256']==digest(d/'numeric-exit.json'),'original numeric exit/seal')
 inputs_before=grading_inputs(c,role)
 if role=='native':golden=original_reference(c)
 rs=c['stages']['reference'];grade=Path(c['repo'])/'scripts/research/studio019_grade.py'
 need(path(grade).is_relative_to(c['repo']) and c['source']==source(c['repo']),'frozen grading code')
 # Child reads only two sealed roles (native grade) or original reference (eligibility),
 # has no need for checkpoint files and cannot generate model outputs.
 tag='eligibility' if role=='reference' else 'grade';identity=secrets.token_hex(16);row,pol=python_policy(c,True)
 limits=doc(c['resource'])['native'];baseline=pressure();need(baseline['pressure']==1 and baseline['headroom']>=16*GIB+limits['combined'],'grade admission headroom')
 pyg.fresh_cache(d/('cache-'+tag))
 args=pyg.cli(rs['python'],d/('cache-'+tag),pyg.SELF,tag,row['path'],row['sha256'],pyg.rolepath(d,tag),identity,[layout(c,'reference')[1]]+([out] if role=='native' else []))
 put(d/(tag+'-intent.json'),dict(operation=identity,numeric_operation=seal['operation'],seal_sha256=digest(seal_path),python_policy_sha256=row['sha256']))
 with (d/(tag+'.stdout')).open('xb') as so,(d/(tag+'.stderr')).open('xb') as se:
  r,w=os.pipe();proc=lease=None;success=False;deadline=time.monotonic()+300;bad=0
  try:
   # No grading imports or access to either role's outputs before this gate.
   sb=aux_profile_file(c,d,tag,[layout(c,'reference')[1]]+([out] if role=='native' else []))
   proc=subprocess.Popen(['/usr/bin/sandbox-exec','-f',str(sb),*args],stdin=subprocess.DEVNULL,stdout=so,stderr=se,process_group=0,pass_fds=(r,),env={'HOME':str(Path.home()),'PATH':'/usr/bin:/bin','STUDIO017_GRADE_GATE':str(r),'OMP_NUM_THREADS':'1','VECLIB_MAXIMUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'},cwd=c['repo'])
   os.close(r);r=-1;lease=attach_guard(c,d,proc,deadline,identity,'lease-grade',se)
   put(d/(tag+'-start.json'),dict(operation=identity,pid=proc.pid,supervisor=os.getpid(),guardian=lease.receipt()))
   os.write(w,b'G');os.close(w);w=-1
   while proc.poll() is None:
    lease.pulse();measured=pressure();bad=bad+1 if measured['swap']-baseline['swap']>limits['swap_growth'] else 0;rows=cohort()
    rss=sum(x[3]*1024 for x in rows if x[2]==proc.pid or x[0]==os.getpid())
    need(measured['pressure']==1 and measured['headroom']>=16*GIB and rss<=limits['combined'] and bad<limits['swap_samples'] and time.monotonic()<deadline,'grade resource/time')
    need(so.tell()<=8<<20 and se.tell()<=8<<20,'grading output');time.sleep(.25)
   need(time.monotonic()<=deadline,'grade duration');success=proc.returncode==0
  finally:
   if w>=0:os.close(w)
   if r>=0:os.close(r)
   left,clean=end_owned(proc,lease,success) if proc is not None else (False,False)
   put(d/(tag+'-exit.json'),dict(operation=identity,pid=(proc.pid if proc else None),exit=(proc.returncode if proc else None),guardian_exit=(lease.guard.returncode if lease is not None else None),clean_reap=clean,residual_group_killed=left))
  need(proc.returncode==0 and clean and not left,'original grade failed')
 watchdog_hash=pyg.checked_receipt(d,'lease-grade',identity,lease.guard.pid,row['sha256'],pol,os.getpid())
 gradehash=pyg.checked_receipt(d,tag,identity,proc.pid,row['sha256'],pol,os.getpid())
 result=parse(read(d/(tag+'.stdout'),8<<20));key='eligible' if role=='reference' else 'qualified';need(type(result.get(key)) is bool,'grader result grammar')
 graded_inputs=grade_content_verified(c,role,inputs_before,result)
 put(d/(tag+'.json'),dict(operation=seal['operation'],grading_operation=identity,graded_inputs=graded_inputs,guardian_runtime_sha256=watchdog_hash,grader_runtime_sha256=gradehash,seal_sha256=digest(seal_path),native_stage_complete=complete,result=result,**{key:result[key]}));return result
def main(args):
 selected=args[:1]==['--studio019-route-b']
 if selected:args=args[1:]
 need(len(args)==3,'command CONFIG STAGE required')
 mode=args[0]
 need(mode not in ('admit-child','stage-exec'),'only isolated attested child entry')
 need((mode in ('describe','verify','launch','reconcile-grade') or (selected and mode=='freeze-authorization'))
      and selected and args[2]=='native','explicit diagnostic mode/role')
 os.umask(0o077);cfg=load_cfg(args[1],selected);role=args[2]
 if mode=='freeze-authorization':print(enc(freeze_operator(cfg,role)).decode(),end='')
 elif mode=='describe':print(enc(envelope(cfg,role)).decode(),end='')
 elif mode=='verify':g,ptr=verified(cfg,role);admission(cfg,role,g['limits']);print(enc(ptr).decode(),end='')
 elif mode=='reconcile-grade':
  # No replacement grade after an uncertain grade submission. Recovery only if the initial stage
  # exited cleanly AND was sealed, but grading was never submitted. Never re-enter launch().
  with (STATE/'heavy.lock').open('ab') as lock:
   fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);grade_original(cfg,role)
 else:run_numeric(args[1],role,selected)
if __name__=='__main__':main(sys.argv[1:])
