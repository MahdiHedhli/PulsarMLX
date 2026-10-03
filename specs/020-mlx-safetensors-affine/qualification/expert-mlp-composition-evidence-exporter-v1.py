"""Read-only redecision and exact worst-stage metrics; run after qualification PASS."""
import argparse, json, sys, struct
from pathlib import Path
from fractions import Fraction as F

p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--attempt',type=Path,required=True);p.add_argument('--frozen',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
sys.path.insert(0,str(a.repo/'scripts/research'))
import f020_expert_mlp_qualify_v1 as Q
import f020_expert_mlp_r1_v1 as R

frozen=json.loads(a.frozen.read_text());qualified=json.loads((a.attempt/'qualification-result.json').read_text())
for k in ['commit','tree','package_sha256']:
    if qualified[k]!=frozen[k]:raise RuntimeError('qualification identity mismatch')
if qualified['status']!='PASS' or len(qualified['cases'])!=54 or len(qualified['controls'])!=10 or any(c['status']!='DETECTED' for c in qualified['controls']):raise RuntimeError('qualification not terminal PASS')
if Q.package_files()!=frozen['source_files']:raise RuntimeError('frozen source/fixture drift')
m=json.loads((Q.FIXTURE/'manifest.json').read_text());receipts={c['id']:c for c in qualified['cases']}
stages={k:{'checks':0,'exact_zero_checks':0,'worst_ratio':F(0),'worst':None} for k in ['gate','up','hidden','down_local','output']}

def add(name,distance,budget,ident,row,col):
    if distance>budget:raise RuntimeError('failed numerical redecision')
    s=stages[name];s['checks']+=1
    if budget==0:
        if distance:raise RuntimeError('nonzero error at zero budget')
        s['exact_zero_checks']+=1;ratio=F(0)
    else:ratio=distance/budget
    if s['worst'] is None or ratio>s['worst_ratio']:
        s['worst_ratio']=ratio;s['worst']={'id':ident,'row':row,'column':col,'distance_exact':str(distance),'budget_exact':str(budget),'ratio_exact':str(ratio)}

for c in m['cases']:
    raw=a.attempt/c['id']/'report.json';verified=a.attempt/c['id']/'verified-report.json'
    if Q.sha(raw.read_bytes())!=receipts[c['id']]['raw_report_sha256'] or Q.sha(verified.read_bytes())!=receipts[c['id']]['verified_report_sha256']:raise RuntimeError('report custody mismatch')
    doc=json.loads(verified.read_text());ref=Q.refs(m,c) if c['kind']=='positive' else None
    failures=Q.verify_child(m,c,doc,ref)
    if failures:raise RuntimeError(str(failures))
    if c['kind']!='positive':continue
    g=Q.decoded_output(doc['gate']['output'],[c['M'],c['H']]);u=Q.decoded_output(doc['up']['output'],[c['M'],c['H']])
    h=Q.decoded_output(doc['activation']['output'],[c['M'],c['H']]);y=Q.decoded_output(doc['down']['output'],[c['M'],c['D']])
    local,bd=R.qmm(h,ref['down'])
    for i in range(c['M']):
        for j in range(c['H']):
            add('gate',abs(g[i][j]-ref['g'][i][j]),ref['bg'][i][j],c['id'],i,j)
            add('up',abs(u[i][j]-ref['u'][i][j]),ref['bu'][i][j],c['id'],i,j)
            add('hidden',max(abs(h[i][j]-v) for v in ref['h'][i][j]),ref['bh'][i][j],c['id'],i,j)
        for j in range(c['D']):
            add('down_local',abs(y[i][j]-local[i][j]),bd[i][j],c['id'],i,j)
            add('output',max(abs(y[i][j]-v) for v in ref['y'][i][j]),bd[i][j]+ref['propagated'][i][j],c['id'],i,j)
controls={c['id']:c for c in qualified['controls']}
default=next(c for c in m['cases'] if c['kind']=='positive' and c['D']==64 and c['H']==64 and c['M']==1 and c['expert']==0 and c['profile']=='default')
mixed=next(c for c in m['cases'] if c['kind']=='positive' and c['D']==64 and c['H']==64 and c['M']==1 and c['expert']==0 and c['profile']=='mixed')
for control in m['controls']:
    ident=control['id'];receipt=controls[ident];folder=a.attempt/ident
    verified=folder/'verified-report.json';doc=json.loads(verified.read_text())
    if Q.sha(verified.read_bytes())!=receipt['verified_report_sha256']:raise RuntimeError('control verified custody mismatch')
    c=mixed if ident=='ignore-bit-override' else default
    raw=folder/'report.json'
    if 'raw_report_sha256' in receipt:
        if Q.sha(raw.read_bytes())!=receipt['raw_report_sha256']:raise RuntimeError('control raw custody mismatch')
    elif Q.sha((a.attempt/c['id']/'report.json').read_bytes())!=receipt['source_case_raw_report_sha256']:raise RuntimeError('control source-case custody mismatch')
    if ident=='lower-gate-clamp':
        runs=doc['runs'];want=struct.unpack('<I',struct.pack('<f',-15.))[0]
        detected=doc['kind']=='activation-stage-only' and runs[0]['gate_clamp_bits']==[want] and runs[1]['gate_clamp_bits']!=[want] and all(r['status']==0 and r['stats'][0]==2 and r['stats'][2:]==[9,4,13,1,9,0] for r in runs)
    else:
        failures=Q.verify_child(m,c,doc,Q.refs(m,c))
        detected=Q.control_detected(ident,doc,failures)
    if not detected:raise RuntimeError('control semantic redecision failed: '+ident)
for s in stages.values():
    s['worst_ratio_display']=float(s.pop('worst_ratio'))
summary={'schema':'pulsarmlx.f020.expert-mlp-studio-summary/1','status':'QUALIFIED_SYNTHETIC_ONLY','source_commit':qualified['commit'],'source_tree':qualified['tree'],'package_sha256':qualified['package_sha256'],'manifest_sha256':qualified['manifest_sha256'],'qualification_result_sha256':Q.sha((a.attempt/'qualification-result.json').read_bytes()),'fixed_budgets':{'E_act':'1/128','beta_B':'5201/4194304'},'population':m['population'],'cases':qualified['cases'],'controls':qualified['controls'],'stage_metrics':stages,'metrics_definition':'max distance to independent interval endpoints / unchanged budget; exact rational gates; floats only display ratios','exporter_sha256':Q.sha(Path(__file__).read_bytes()),'scope':'single complete synthetic expert MLP with explicitly counted host copies; no performance or real-payload claim','next_real_payload_gate':'read-only header/config census and exact real gate/up/down expert identity/recipe/geometry binding; separately qualify bounded expert-only range/lifetime backing before real execution, since current synthetic Source::open hashes and loads the whole checkpoint; demonstrate actual intermediate domains, or separately review an extension, before one bounded real expert case; no whole-model scan/copy/download or performance claim'}
a.output.write_bytes(Q.canonical(summary));print(json.dumps({'status':summary['status'],'checks':sum(s['checks'] for s in stages.values()),'stage_worst_ratio':{k:v['worst_ratio_display'] for k,v in stages.items()}}))
