#!/usr/bin/env python3
"""Complete independent gates after M1a; never launches a native artifact."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import reference_budget
from reference import sha, canonical, grade, REPO
from mlx_affine_qmm_reference_v1 import exact_case
from exact_gates_v1 import decide_qmm
from report_checks import check_campaign

def qualify(campaign, rust_grader):
    freeze,mechanism,entries=check_campaign(campaign);root=campaign/'m1a'
    if sha(rust_grader.read_bytes())!=freeze['rust_grader_sha256']:raise ValueError('grader identity')
    if mechanism['mechanism']!='PASS' or mechanism['M1b_released'] is not False:raise ValueError('mechanism receipt')
    reference=Path(freeze['reference']);portable=Path(freeze['portable_report']);inherited=Path(freeze['inherited_root'])
    if sha(reference.read_bytes())!=freeze['reference_sha256'] or sha(portable.read_bytes())!=freeze['portable_report_sha256']:raise ValueError('frozen reference identity')
    original=json.loads((inherited/'manifest.json').read_text());original_cases={c['id']:c for c in original['cases'] if c['expected']['outcome']=='accept'}
    rows=[]
    if len(mechanism['reports'])!=52:raise ValueError('complete changed-boundary population')
    for entry in mechanism['reports']:
        reference_budget.check()
        report=root/entry['report'];r=json.loads(report.read_text());rust_path=report.parent/'rust-gates.json'
        attempt=report.parent/'rust-gates.attempt.json'
        with attempt.open('xb') as f:f.write(canonical({'grader_sha256':sha(rust_grader.read_bytes()),'report_sha256':sha(report.read_bytes())}))
        result=subprocess.run([str(rust_grader),str(portable),str(inherited),str(report),str(rust_path)],capture_output=True,text=True,timeout=900)
        with (report.parent/'rust-gates.stdout').open('x') as f:f.write(result.stdout)
        with (report.parent/'rust-gates.stderr').open('x') as f:f.write(result.stderr)
        if result.returncode:raise ValueError('Rust reference gate failed; preserved attempt')
        rust=json.loads(rust_path.read_text())
        if r.get('population')=='inherited_slice2c_changed_import':
            c=original_cases[r['id']];exact=exact_case(c,inherited);g=decide_qmm(c,exact,rust['cases'][0]['rust'],r,report.parent)
            if any(v is not None and not v['pass'] for v in g.values()):raise ValueError('original Slice2C mathematical gate')
        else:g=grade(reference,report)
        rows.append({'report':entry['report'],'report_sha256':sha(report.read_bytes()),'rust_gates_sha256':sha(rust_path.read_bytes()),'exact_gates':g})
    result={'contract_sha256':freeze['contract_sha256'],'source_commit':freeze['source_commit'],'source_tree':freeze['source_tree'],'native_libraries':freeze['native_libraries'],'mechanism_sha256':sha((root/'mechanism.json').read_bytes()),'binary_sha256':freeze['binary_sha256'],'fixture_manifest_sha256':freeze['fixture_manifest_sha256'],'host_role':freeze['host_role'],'reference_envelope':reference_budget.check(),'mechanism':'PASS','correctness':'PASS','reports':rows,'M1b_released':False,'note':'Both required host acceptances must bind identical source and fixture identities before Studio timing release.'}
    with (campaign/'m1a-acceptance.json').open('xb') as f:f.write(canonical(result))
    return {'host_role':freeze['host_role'],'correctness':'PASS','reports':len(rows)}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('campaign',type=Path);p.add_argument('--rust-grader',type=Path,required=True);a=p.parse_args();reference_budget.start();print(json.dumps(qualify(a.campaign,a.rust_grader),indent=2))
