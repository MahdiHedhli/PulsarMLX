#!/usr/bin/env python3
"""Static by default. Exact-review-bound Studio qualification; no real weights."""
import argparse, copy, hashlib, json, os, signal, struct, subprocess, sys, time
from pathlib import Path
from fractions import Fraction as F
import f020_expert_mlp_r1_v1 as R

ROOT=Path(__file__).resolve().parents[2]
FIXTURE=ROOT/'fixtures/expert-mlp-composition'
PINS={'libmlx':'c11a4d814042213b866ce66032107921857e4bbc8bfe0dd8150573a1ff9a8053',
      'libmlxc':'e523f544758f042f78aeacdbe646af9d966432605ad4cfe760609b4044c2ce27',
      'metallib':'5518fd265f31a8973732996d5eecc612301c94c1852156fb9ff30f6b708be365'}

def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(v):return (json.dumps(v,sort_keys=True,indent=2)+'\n').encode()
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
def package_files():
    names=['Cargo.toml','Cargo.lock','.github/workflows/macos.yml',
      'specs/020-mlx-safetensors-affine/contracts/expert-mlp-composition-v1.json',
      'specs/020-mlx-safetensors-affine/expert-mlp-composition-plan-v1.md',
      'specs/020-mlx-safetensors-affine/expert-mlp-composition-tasks-v1.md']
    names += [str(p.relative_to(ROOT)) for p in (ROOT/'crates/mlx-expert-mlp').rglob('*') if p.is_file()]
    names += [str(p.relative_to(ROOT)) for p in (ROOT/'scripts/research').glob('f020_expert_mlp_*v1.py')]
    names += ['scripts/research/f020_fused_swiglu_cpu_guard_v2_4.h']
    names += ['crates/mlx-native-affine/src/bin/qualify/'+s+'.rs' for s in ['ffi','native','bridge','provenance']]
    names += [str(p.relative_to(ROOT)) for p in (ROOT/'fixtures/expert-mlp-composition').rglob('*') if p.is_file()]
    return {s:sha((ROOT/s).read_bytes()) for s in sorted(set(names))}
def package_digest(files):return sha(canonical(files))
def input_rows(c):
    raw=(FIXTURE/c['input']).read_bytes()
    return [[R.f32(v) for v in struct.unpack_from('<'+'I'*c['D'],raw,row*c['D']*4)] for row in range(c['M'])]
def checkpoint(m,c):return FIXTURE/m['checkpoints'][c['checkpoint']]['path']/'model.safetensors'
def refs(m,c):return R.references(c,R.read_checkpoint(checkpoint(m,c)),input_rows(c))
def decoded_output(doc,shape):
    if doc.get('dtype')!='F32' or doc.get('shape')!=shape or len(doc.get('f32_bits',[]))!=shape[0]*shape[1]:
        raise ValueError('output shape/dtype/count')
    raw=struct.pack('<'+'I'*len(doc['f32_bits']),*doc['f32_bits'])
    if doc.get('sha256')!=sha(raw) or doc.get('bytes')!=len(raw):raise ValueError('output hash/bytes')
    v=[R.f32(w) for w in doc['f32_bits']]
    return [v[i*shape[1]:(i+1)*shape[1]] for i in range(shape[0])]

def clamp_bits(words,role):
    """Finite F32 exact clamps preserve the original signed-zero bits."""
    ten=0x41200000;neg_ten=0xc1200000
    result=[]
    for w in words:
        x=R.f32(w)
        result.append(ten if x>10 else neg_ten if role=='up' and x<-10 else w)
    return result

def control_detected(ident,doc,failures):
    expected={
      'gate-up-argument-swap':'stage packed recipe',
      'missing-upper-gate-clamp':'exact clamp semantics',
      'missing-up-upper-clamp':'exact clamp semantics',
      'missing-up-lower-clamp':'exact clamp semantics',
      'skip-down-admission':"'down_admission'",
      'candidate-fed-reference':'R1 authority binding'}
    if ident in expected:return expected[ident] in failures
    if ident in ['gate-down-role-swap','down-expert-swap','ignore-bit-override']:
        return 'positive incomplete' in failures and doc.get('phase')=='tuple' and 'MLP-R-TUPLE' in doc.get('detail','') and doc.get('final_counters')=={'numerical':0,'imports':0}
    return False

def verify_child(m,c,doc,reference):
    try:
        if doc['id']!=c['id']:raise ValueError('case identity')
        clean=doc['cleanup']
        if clean['live'] or clean['double_frees'] or clean['handler_messages'] or clean['errors']:raise ValueError('cleanup/handler')
        if c['kind']!='positive':
            if doc['outcome']!='refused-or-error' or c['expected_refusal'] not in doc.get('detail','') or doc['phase']!=c['phase']:raise ValueError('refusal identity/phase')
            if c['phase'] in ['preflight','tuple'] and doc['final_counters']!={'numerical':0,'imports':0}:raise ValueError('early refusal native counters')
            if c['phase']=='activation' and ('activation' in doc or 'down' in doc):raise ValueError('activation refusal executed a later stage')
            if c['phase']=='down-guard':
                if 'down' in doc or doc['down_admission']['decision']!='refused' or doc['down_admission']['before']!=doc['down_admission']['after']:raise ValueError('down guard refusal executed native work')
            return []
        if doc['outcome']!='executed' or doc['phase']!='complete':raise ValueError('positive incomplete')
        if doc['r1_authority']!={'kind':'original-fixture','source_sha256':sha(checkpoint(m,c).read_bytes()),'input_sha256':sha((FIXTURE/c['input']).read_bytes())}:raise ValueError('R1 authority binding')
        cp=m['checkpoints'][c['checkpoint']];raw=checkpoint(m,c).read_bytes();n=struct.unpack_from('<Q',raw)[0];header=json.loads(raw[8:8+n])
        if len(doc['selections'])!=3:raise ValueError('tuple count')
        for role,sel in zip(['gate','up','down'],doc['selections']):
            expected=cp['expected_planes'][f'{role}/{c["expert"]}'];identity=sel['identity']
            for key in ['module','bits','group_size','logical_shape','packed_shape','metadata_shape']:
                if identity[key]!=expected[key]:raise ValueError('selection '+key)
            if identity['index_path']!=[c['expert']] or identity['checkpoint']!=Path(cp['path']).name or identity['metadata_dtype']!='BF16' or not identity['transpose']:raise ValueError('selection binding')
            if identity['resolved_from']!=('override' if c['profile']=='mixed' and role!='up' else 'default'):raise ValueError('override binding')
            for ix,suffix in enumerate(['weight','scales','biases']):
                h=header['synthetic.experts.'+role+'.'+suffix];lo,hi=h['data_offsets'];size=(hi-lo)//3
                want={'shard':'model.safetensors','begin':8+n+lo+c['expert']*size,'len':size}
                if sel['ranges'][suffix]!=want or sel['sha256'][suffix]!=expected['sha256'][ix]:raise ValueError('independent selection range/hash')
        if len({s['identity']['source_identity'] for s in doc['selections']})!=1:raise ValueError('cross source')
        if doc['source_before']!=doc['source_after']:raise ValueError('source mutation')
        for rec in doc['source_before']:
            if rec['file_sha256_at_load']!=sha(raw) or rec['file_len']!=len(raw) or rec['window']:raise ValueError('source file binding')
        p=doc['provenance']
        for name,want in PINS.items():
            if p[name]['sha256']!=want:raise ValueError('native pin '+name)
        if p['mlx_commit_pinned']!='68cf2fddd8de5edd8ab3d926391772b2e2cedad8' or p['mlx_c_commit_pinned']!='0726ca922fc902c4c61ef9c27d94132be418e945':raise ValueError('native commits')
        for role,k,n in [('gate',c['D'],c['H']),('up',c['D'],c['H']),('down',c['H'],c['D'])]:
            s=doc[role]
            if s['bound_gamma_n']!=R.gamma_n(c['M'],n,k) or s['imports_before_decision'] or s['numerical_before_decision'] or not s['device_facts_gpu'] or s['cpu_guard_checks']!=2:raise ValueError('stage guard/family evidence')
            expected=cp['expected_planes'][f'{role}/{c["expert"]}']
            if s['packed_weight_sha256']!=expected['sha256'][0] or s['bits']!=expected['bits'] or s['group_size']!=64:raise ValueError('stage packed recipe')
        g=decoded_output(doc['gate']['output'],[c['M'],c['H']]);u=decoded_output(doc['up']['output'],[c['M'],c['H']])
        a=doc['activation'];hv=decoded_output(a['output'],[c['M'],c['H']]);y=decoded_output(doc['down']['output'],[c['M'],c['D']])
        if a['status'] or a['stats'][0]!=2 or a['stats'][2:]!=[9,4,13,1,9,0] or a['materializations']!=1:raise ValueError('activation ownership/order/materialization')
        if a['gate_clamp_bits']!=clamp_bits(doc['gate']['output']['f32_bits'],'gate') or a['up_clamp_bits']!=clamp_bits(doc['up']['output']['f32_bits'],'up'):raise ValueError('exact clamp semantics')
        if doc['down_admission']['decision']!='admitted' or doc['down_admission']['before']!=doc['down_admission']['after'] or doc['down_admission']['actual_input_sha256']!=a['output']['sha256']:raise ValueError('actual down admission')
        local,bd=R.qmm(hv,reference['down'])
        failures=[]
        for i in range(c['M']):
            for j in range(c['H']):
                if abs(g[i][j]-reference['g'][i][j])>reference['bg'][i][j]:failures.append(f'gate/{i}/{j}')
                if abs(u[i][j]-reference['u'][i][j])>reference['bu'][i][j]:failures.append(f'up/{i}/{j}')
                if not R.distance_pass(hv[i][j],reference['h'][i][j],reference['bh'][i][j]):failures.append(f'h/{i}/{j}')
            for j in range(c['D']):
                if abs(y[i][j]-local[i][j])>bd[i][j]:failures.append(f'down-local/{i}/{j}')
                if not R.distance_pass(y[i][j],reference['y'][i][j],bd[i][j]+reference['propagated'][i][j]):failures.append(f'y/{i}/{j}')
        return failures
    except (KeyError,ValueError,TypeError,IndexError) as e:return [str(e)]

def run_child(binary,c,mutation,out,cap,env):
    out.mkdir(parents=True,exist_ok=False)
    command=[str(binary),'--repo',str(ROOT),'--out',str(out),'--admission',str(cap),'--case',c['id']]
    if mutation:command+=['--mutation',mutation]
    with open(out/'stdout.txt','w') as stdout,open(out/'stderr.txt','w') as stderr:
        p=subprocess.Popen(command,env=env,stdout=stdout,stderr=stderr,start_new_session=True)
        try:rc=p.wait(timeout=45)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid,signal.SIGKILL);p.wait();raise RuntimeError('bounded child timeout; preserved '+c['id'])
    if rc:raise RuntimeError('child failed; preserved '+c['id'])
    return json.loads((out/'report.json').read_text())

def main():
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');p.add_argument('--binary',type=Path);p.add_argument('--review',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=True)
    files=package_files();digest=package_digest(files);m=json.loads((FIXTURE/'manifest.json').read_text())
    if m['population']!={'positives':48,'refusals':5,'guard_controls':1,'mutations':10,'total':64}:raise RuntimeError('population changed')
    all_ids=[c['id'] for c in m['cases']]+[c['id'] for c in m['controls']]
    if len(all_ids)!=64 or len(set(all_ids))!=64:raise RuntimeError('missing or duplicate population ID')
    subprocess.run([sys.executable,'-B',str(ROOT/'scripts/research/f020_expert_mlp_fixtures_v1.py'),'--out',str(FIXTURE),'--check'],check=True)
    references={c['id']:refs(m,c) for c in m['cases'] if c['kind']=='positive'}
    static={'status':'PASS','candidate_observations':0,'package_sha256':digest,'source_files':files,'manifest_sha256':sha((FIXTURE/'manifest.json').read_bytes()),'certified_ids':list(references)}
    (a.out/'static-result.json').write_bytes(canonical(static))
    print(json.dumps({'static':'PASS','certified_cases':len(references),'package_sha256':digest}),flush=True)
    if not a.execute:return
    if a.review is None or a.binary is None:raise RuntimeError('exact review and executable required')
    review=json.loads(a.review.read_text());commit=git('rev-parse','HEAD');tree=git('rev-parse','HEAD^{tree}')
    tracked=set(git('ls-files').splitlines())
    if set(files)-tracked:raise RuntimeError('every source/fixture package file must belong to the frozen commit')
    if git('status','--porcelain') or review.get('decision')!='ACCEPT' or review.get('blocking_findings')!=0 or review.get('commit')!=commit or review.get('tree')!=tree or review.get('package_sha256')!=digest:raise RuntimeError('exact clean accepted review required')
    for field,label in [('raw_review_file','raw_review_sha256'),('review_capsule_file','review_capsule_sha256')]:
        name=review.get(field,'')
        if not name or Path(name).is_absolute() or '..' in Path(name).parts:raise RuntimeError('confined independent review evidence required')
        if sha((a.review.parent/name).read_bytes())!=review.get(label):raise RuntimeError('independent review evidence hash mismatch')
    if not review.get('actual_model') or not review.get('reviewer'):raise RuntimeError('actual independent reviewer identity required')
    binary=a.binary.resolve();cap=a.out/'admission.json'
    if review.get('binary_sha256')!=sha(binary.read_bytes()):raise RuntimeError('executable is not the exact reviewed build')
    capability={'status':'ADMITTED','commit':commit,'tree':tree,'package_sha256':digest,'source_files':files,'review_sha256':sha(a.review.read_bytes()),'binary_sha256':sha(binary.read_bytes()),'manifest_sha256':static['manifest_sha256']}
    cap.write_bytes(canonical(capability));cap.chmod(0o600)
    env=dict(os.environ,MLX_ENABLE_TF32='0',PYTHONDONTWRITEBYTECODE='1',PYTHONINTMAXSTRDIGITS='0')
    for name in ['MLX_METAL_GPU_ARCH','MLX_MAX_OPS_PER_BUFFER','MLX_MAX_MB_PER_BUFFER','DYLD_INSERT_LIBRARIES']:env.pop(name,None)
    result={'status':'RUNNING','commit':commit,'tree':tree,'package_sha256':digest,'manifest_sha256':static['manifest_sha256'],'review_sha256':capability['review_sha256'],'cases':[],'controls':[]}
    save=lambda:(a.out/'qualification-result.json').write_bytes(canonical(result))
    save();reports={}
    try:
        for c in m['cases']:
            doc=run_child(binary,c,'',a.out/c['id'],cap,env)
            if c['kind']=='positive':doc['r1_authority']={'kind':'original-fixture','source_sha256':sha(checkpoint(m,c).read_bytes()),'input_sha256':sha((FIXTURE/c['input']).read_bytes())}
            failures=verify_child(m,c,doc,references.get(c['id']))
            raw_path=a.out/c['id']/'report.json'
            verified_path=a.out/c['id']/'verified-report.json';verified_path.write_bytes(canonical(doc))
            result['cases'].append({'id':c['id'],'status':'FAIL' if failures else 'PASS','failures':failures,'raw_report_sha256':sha(raw_path.read_bytes()),'verified_report_sha256':sha(verified_path.read_bytes())})
            reports[c['id']]=doc;save()
            if failures:raise RuntimeError('correctness gate failed: '+c['id']+' '+str(failures[:4]))
            print('PASS '+c['id'],flush=True)
        default=next(c for c in m['cases'] if c['kind']=='positive' and c['M']==1 and c['expert']==0 and c['profile']=='default')
        mixed=next(c for c in m['cases'] if c['kind']=='positive' and c['M']==1 and c['expert']==0 and c['profile']=='mixed')
        for control in m['controls']:
            ident=control['id'];c=mixed if ident=='ignore-bit-override' else default
            if ident=='lower-gate-clamp':
                doc=run_child(binary,{'id':'clamp-stage-probe'},'',a.out/ident,cap,env)
                runs=doc['runs'];want=struct.unpack('<I',struct.pack('<f',-15.))[0]
                detected=doc['kind']=='activation-stage-only' and runs[0]['gate_clamp_bits']==[want] and runs[1]['gate_clamp_bits']!=[want] and all(r['status']==0 and r['stats'][0]==2 and r['stats'][2:]==[9,4,13,1,9,0] for r in runs)
                failures=['exact clamp stage rejects illicit lower clamp'] if detected else []
            elif ident in ['skip-down-admission','candidate-fed-reference']:
                doc=copy.deepcopy(reports[c['id']])
                if ident=='skip-down-admission':doc.pop('down_admission')
                else:doc['r1_authority']={'kind':'candidate-hidden','source_sha256':doc['activation']['output']['sha256']}
                failures=verify_child(m,c,doc,references[c['id']])
            else:
                doc=run_child(binary,c,ident,a.out/ident,cap,env)
                doc['r1_authority']={'kind':'original-fixture','source_sha256':sha(checkpoint(m,c).read_bytes()),'input_sha256':sha((FIXTURE/c['input']).read_bytes())}
                failures=verify_child(m,c,doc,references[c['id']])
            detected=bool(failures) if ident=='lower-gate-clamp' else control_detected(ident,doc,failures)
            result['controls'].append({'id':ident,'status':'DETECTED' if detected else 'SURVIVED','detection':failures[:4],'expected_detection':control['expected_detection'],'scope':'host audit mutation' if ident in ['skip-down-admission','candidate-fed-reference'] else control['target']});save()
            if not detected:raise RuntimeError('mutation failed its frozen semantic detection predicate: '+ident)
            print('DETECTED '+ident,flush=True)
        if package_files()!=files or git('status','--porcelain'):raise RuntimeError('source/fixture changed during qualification')
        result['status']='PASS';save();print('COMPLETE_SYNTHETIC_EXPERT_MLP_PASS',flush=True)
    except Exception as e:
        result['status']='FAIL';result['error']=str(e);save();raise

if __name__=='__main__':main()
