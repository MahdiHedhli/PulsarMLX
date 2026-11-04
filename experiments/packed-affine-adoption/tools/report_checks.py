"""Pure admission of saved evidence; no child launches or native imports."""
import hashlib
import json
from pathlib import Path
CONTRACT = '943e0a9e2358985038f2fba31831fa302d3aeae3dd8f50e85970a4760931a49b'
def sha(raw): return hashlib.sha256(raw).hexdigest()
def read(path): return json.loads(path.read_bytes())
def confined(root, name):
    p = Path(name)
    if p.is_absolute() or '..' in p.parts: raise ValueError('unconfined evidence path')
    resolved = (root / p).resolve(strict=True)
    if not resolved.is_relative_to(root.resolve(strict=True)): raise ValueError('evidence symlink escape')
    return resolved

def expected_population(manifest, inherited):
    groups = list(manifest['small_sequences']) + [[c['id']] for c in manifest['cases'] if c['population_id']=='representative-read-into-v1']
    positives = [c['id'] for c in inherited['cases'] if c['expected']['outcome']=='accept']
    if len(groups)!=12 or len(positives)!=14 or len(set(positives))!=14: raise ValueError('frozen population cardinality')
    return {f'{kind}-{i}-{arm}': (ids, arm, kind) for kind, population in [('group', groups), ('inherited', [[p] for p in positives])] for i, ids in enumerate(population) for arm in ('copied','adopted')}

def admit_entries(mechanism, expected):
    entries=mechanism['reports'];labels=[e['label'] for e in entries]
    if len(labels)!=len(set(labels)) or set(labels)!=set(expected): raise ValueError('missing, duplicate or extra report')
    for entry in entries:
        if entry['report']!=entry['label']+'/run.json': raise ValueError('crossed report path')
    return entries

def admit_report(freeze, expected, label, report, outcome, config_hash):
    ids, arm, kind=expected[label]
    if outcome['outcome']!='EXIT_STATUS 0': raise ValueError('child failure')
    if outcome['binary_sha256']!=freeze['binary_sha256'] or outcome['config_sha256']!=config_hash or report['config_sha256']!=config_hash: raise ValueError('executable/config binding')
    p=report['provenance']
    if p['loaded_images_verified'] is not True: raise ValueError('unverified native libraries')
    for key in ('source_commit','source_tree','binary_sha256','native_libraries'):
        if p[key]!=freeze[key]: raise ValueError('crossed native/source identity')
    life=report['lifetime']
    if life['live']!=0 or life['created']!=life['freed'] or life['early_free_count']!=0 or life['completed_callbacks']!=int(arm=='adopted') or life.get('quarantine',report.get('quarantine',True)) is not False: raise ValueError('unresolved ownership')
    for key in ('parent_counts','view_counts','output_counts'):
        if len(life[key])!=2 or life[key][0]!=life[key][1]: raise ValueError('unbalanced category')
    if kind=='inherited':
        if report['population']!='inherited_slice2c_changed_import' or [report['id']]!=ids: raise ValueError('inherited identity')
        return [report['output']]
    if report['identity']['contract_sha256']!=CONTRACT or report['identity']['fixture_manifest_sha256']!=freeze['fixture_manifest_sha256']: raise ValueError('fixture identity')
    if [o['id'] for o in report['outputs']]!=ids: raise ValueError('sequence identity')
    return report['outputs']

def admit_raw(root):
    events=[json.loads(s) for s in confined(root,'raw-probe/events.jsonl').read_text().splitlines()]
    if sum(e.get('phase')=='before-call' for e in events)!=1: raise ValueError('raw call not reached exactly once')
    outcome=read(confined(root,'raw-probe.outcome.json'))['outcome']
    summary=read(confined(root,'raw-probe-summary.json'))
    if outcome.startswith('TIMEOUT'):
        if not outcome.endswith('(SIGKILL sent; reaped with signal Some(9))') or summary.get('raw_probe')!='timeout-reaped': raise ValueError('raw timeout not reaped')
    elif outcome.startswith('SIGNAL '):
        if summary.get('raw_probe')!='signal' or summary.get('signal')!=int(outcome.split()[1]): raise ValueError('raw signal mismatch')
    elif outcome=='EXIT_STATUS 0':
        if summary.get('outcome') not in ('outside-contract-acceptance','copied-fallback','native-error') or summary.get('qmm_calls')!=0 or summary.get('quarantine') is not True: raise ValueError('raw return outcome')
    else: raise ValueError('raw launch failure')

def check_campaign(campaign):
    freeze=read(campaign/'freeze.json');root=campaign/'m1a';mechanism=read(root/'mechanism.json')
    if freeze['contract_sha256']!=CONTRACT or freeze['host_role'] not in ('native-ci','m1-ultra-studio'): raise ValueError('frozen host/contract')
    if mechanism['mechanism']!='PASS' or mechanism['M1b_released'] is not False: raise ValueError('mechanism receipt')
    for key in ('contract_sha256','source_commit','source_tree','binary_sha256','fixture_manifest_sha256','host_role'):
        if mechanism[key]!=freeze[key]: raise ValueError('mechanism binding')
    fixture=Path(freeze['fixture_root'])/'manifest.json'
    if sha(fixture.read_bytes())!=freeze['fixture_manifest_sha256']: raise ValueError('manifest tampering')
    inherited=Path(freeze['inherited_root'])/'manifest.json'
    if sha(inherited.read_bytes())!=freeze['inherited_manifest_sha256'] or freeze['inherited_manifest_sha256']!='6f0e39e6d2c705603f3f897133d42c31837c53348aba0f4b0389dca18018fc14': raise ValueError('inherited manifest tampering')
    expected=expected_population(read(fixture),read(inherited));entries=admit_entries(mechanism,expected)
    controls=read(root/'injected-controls.json')
    if controls!={'C-GEOMETRY':{'reached':True,'native_calls':0},'C-CALLBACK':{'reached':True,'injected':True,'native_fallback_claim':False}}: raise ValueError('unreached injected gate')
    if freeze.get('schema') == 'pulsarmlx.m1a-continuation/1':
        from m1a_continuation import validate_reports
        validate_reports(campaign,freeze,mechanism)
    elif freeze.get('schema') == 'pulsarmlx.adoption-host-freeze/1':
        admit_raw(root)
    else:
        raise ValueError('unknown campaign schema')
    pairs={}
    for entry in entries:
        label=entry['label'];path=confined(root,entry['report']);config_path=confined(root,label+'.config.json');config=read(config_path)
        ids,arm,kind=expected[label]
        if config['arm']!=arm or (config.get('sequence') if kind=='group' else [config.get('case_id')])!=ids: raise ValueError('crossed config')
        report=read(path);outcome=read(confined(root,label+'.outcome.json'))
        outputs=admit_report(freeze,expected,label,report,outcome,sha(config_path.read_bytes()))
        hashes=[]
        for o in outputs:
            if o['dtype']!='F32' or sha(confined(path.parent,o['file']).read_bytes())!=o['sha256']: raise ValueError('output tampering')
            hashes.append(o['sha256'])
        key=label.rsplit('-',1)[0]
        if key in pairs and hashes!=pairs[key]: raise ValueError('copied/adopted output mismatch')
        pairs[key]=hashes
    return freeze,mechanism,entries
