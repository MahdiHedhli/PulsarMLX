"""Export sanitized source-bound host/metadata evidence; never reads model files."""
import argparse, hashlib, json
from pathlib import Path

p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--audit',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
def load(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def canonical(d):return (json.dumps(d,sort_keys=True,indent=2)+'\n').encode()
f=load(a.audit/'frozen-source-v3.json');r=load(a.audit/'review-02/parsed-review.json');rp=load(a.audit/'review-02/process-receipt.json')
for name,digest in f['source_files'].items():
    if sha(a.repo/name)!=digest:raise RuntimeError('source drift: '+name)
if hashlib.sha256(canonical(f['source_files'])).hexdigest()!=f['package_sha256']:raise RuntimeError('package hash mismatch')
for k in ['commit','tree','package_sha256']:
    if r['assessed_'+k]!=f[k] or rp[k]!=f[k]:raise RuntimeError('review identity mismatch')
if r['decision']!='ACCEPT' or r['blocking_findings']!=0 or rp['exit_code']!=0:raise RuntimeError('review not accepted')
for file,key in [('claude-review.json','raw_review_sha256'),('review-capsule.json','capsule_sha256')]:
    if sha(a.audit/'review-02'/file)!=rp[key]:raise RuntimeError('review custody mismatch')
process=load(a.audit/'real-metadata-plan-01-process-receipt.json');raw=a.audit/'real-metadata-plan-01-stdout.json';meta=load(raw)
if process['exit_code']!=0 or process['source_commit']!=f['commit'] or process['package_sha256']!=f['package_sha256'] or sha(raw)!=process['stdout_sha256']:raise RuntimeError('metadata result custody/identity mismatch')
if meta['status']!='METADATA_ONLY_ADMITTED' or meta['requested_payload_bytes']!=0 or meta['payload_read_calls']!=0 or meta['native_calls']!=0:raise RuntimeError('metadata-only gate failed')
request=meta['plan']['request']
expected={'expert':0,'experts':288,'d':4096,'h':2048,'bits':[4,4,4],'group_size':64,'modules':['language_model.model.layers.3.mlp.switch_mlp.'+r for r in ['gate_proj','up_proj','down_proj']]}
if request!=expected or meta['plan']['selected_bytes']!=14155776:raise RuntimeError('unexpected real binding')
if len(meta['plan']['planes'])!=3:raise RuntimeError('plane count')
roles=[]
for i,plane in enumerate(meta['plan']['planes']):
    shape=[4096,2048] if i==2 else [2048,4096]
    if plane['module']!=expected['modules'][i] or plane['logical_shape']!=shape or plane['expert']!=0 or plane['bits']!=4 or plane['group_size']!=64 or plane['metadata_dtype']!='BF16' or plane['resolved_from']!='default' or len(plane['ranges'])!=3:raise RuntimeError('role geometry/recipe mismatch')
    roles.append({k:plane[k] for k in ['role','module','expert','bits','group_size','resolved_from','metadata_dtype','logical_shape']})
host=load(a.audit/'host-validation-summary.json');repair=load(a.audit/'review-repair-final-process-results.json');log=a.audit/'review-repair-final-2.log';text=log.read_text()
if len(host['checks'])!=4 or any(c['exit_code']!=0 for c in host['checks']) or any(c['exit_code']!=0 for c in repair) or '17 passed; 0 failed' not in text or 'SKIP' in text:raise RuntimeError('host validation failed or omitted sparse controls')
expected_sparse='sparse_case logical_file_bytes=8589956259 physical_bytes=40960 requested_payload_bytes=6912 read_calls=9'
if expected_sparse not in text:raise RuntimeError('sparse evidence changed')
for i in range(1,5):
    if sha(a.audit/f'validation-repair-{i}.log')!=host['raw_stdout_sha256'][str(i)]:raise RuntimeError('workspace stdout custody mismatch')
if host['workspace_failed']!=0:raise RuntimeError('workspace tests failed')
common={'qualified_source_commit':f['commit'],'qualified_source_tree':f['tree'],'package_sha256':f['package_sha256'],'exporter_sha256':sha(Path(__file__))}
summary={**common,'schema':'pulsarmlx.expert-range-admission-evidence/1','status':'HOST_STORAGE_AND_REAL_METADATA_ONLY_ADMITTED','host_tests':{'targeted_passed':17,'targeted_failed':0,'sparse_skips':0,'targeted_stdout_sha256':sha(log),'workspace_passed':host['workspace_passed'],'workspace_failed':0,'workspace_ignored':host['workspace_ignored'],'workspace_scope':'host workspace excluding f017-native; native prefixes unset; predecessor Rust/library source unchanged by final test/telemetry repair','scoped_format':'PASS','scoped_clippy':'PASS','workspace_check':'PASS','workspace_test':'PASS'},'sparse_case':{'logical_file_bytes':8589956259,'physical_bytes':40960,'requested_payload_bytes':6912,'payload_read_calls':9,'probe_max_bytes':16777216},'real_metadata':{'status':meta['status'],'request':request,'roles':roles,'metadata_bytes_read':meta['plan']['metadata_bytes_read'],'metadata_snapshot_sha256':meta['plan']['metadata_snapshot_sha256'],'selected_bytes_planned':14155776,'requested_payload_bytes':0,'payload_read_calls':0,'native_calls':0,'raw_private_receipt_sha256':process['stdout_sha256'],'metadata_binary_sha256':process['binary_sha256'],'native_linkage_absent':process['native_linkage_absent'],'identity_scope':meta['plan']['identity_scope']},'read_limits':{'config_bytes':4194304,'index_bytes':4194304,'individual_header_bytes':2097152,'aggregate_header_bytes':16777216,'shards':32,'selected_payload_bytes':33554432},'scope':'Synthetic owned-range fidelity and host storage tests plus real header/config/range planning only; no real payload, R1 or native numerical execution','limits':['stamp checks cover identity/length/timestamp-visible changes, not atomic snapshots or same-tick same-size rewrites','requested counters count attempts, including failed reads','READ-phase OS-failure injection untested; branch source-reviewed','inherited catalog device-width truncation remains a fail-closed follow-up','Linux/CUDA execution unverified'],'next_gate':'separately reviewed bounded selected load of at most14,155,776bytes; freeze nine owned range hashes; independent real packed R1/input/metadata/intermediate-domain admission and a reviewed geometry/MAC-domain extension before any native execution; current synthetic D/H64or128 and perQMM<=2^21 do not cover real D4096,H2048 (8,388,608MACs each at M1)'}
review={**common,'schema':'pulsarmlx.expert-range-review-receipt/1','decision':r['decision'],'blocking_findings':0,'actual_model':r['actual_model'],'raw_review_sha256':rp['raw_review_sha256'],'review_capsule_sha256':rp['capsule_sha256'],'scope':r['scope'],'nonblocking_findings':[x for x in r['findings'] if x['severity'] not in ['info']]}
a.out.mkdir(parents=True,exist_ok=True)
for name,d in [('expert-range-admission-studio-evidence-v1.json',summary),('expert-range-admission-review-receipt-v1.json',review),('expert-range-admission-source-freeze-v1.json',f)]:
    (a.out/name).write_bytes(canonical(d))
print(json.dumps({'status':summary['status'],'source':f['commit'],'metadata_bytes':summary['real_metadata']['metadata_bytes_read'],'real_payload_bytes':0,'workspace_passed':host['workspace_passed']}))
