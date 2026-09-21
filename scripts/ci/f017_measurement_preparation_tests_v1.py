"""Closed prelaunch mutations over owned data; never imports numerical code.

Actual original checks run separately. Mutant capture/trace copies below are
labelled test data, never substituted for observations or used as a Git answer.
"""
import ast
import copy
import json
from pathlib import Path
import f017_measurement_preparation_v1 as prep

SEALED=('CI_SCOPE_TESTS','BASIC_SUCCESSOR','WRAPPER_SUCCESSOR','FAULTS_SUCCESSOR','INTEGRATION','HISTORICAL_DRIFT_CONTROL','ACTIVE_CENSUS_CONTROL','INTEGRATION')

def gates(supervisor, dispatcher, bootstrap, preparation):
    tree=ast.parse(supervisor);pt=ast.parse(preparation)
    main=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='main')
    cases=next(ast.literal_eval(n.value)for n in ast.walk(main)if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='cases'for t in n.targets))
    prep.need(cases==SEALED,'SEALED_CASE_BIJECTION')
    roles=next(ast.literal_eval(n.value)for n in pt.body if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='ROLES'for t in n.targets))
    prep.need(roles==('CURRENT_ORIGINAL_CHECK','HISTORICAL_ORIGINAL_CHECK'),'ORIGINAL_ROLE_BIJECTION')
    prep.need('CI_ORIGINAL_'not in dispatcher+bootstrap,'DEAD_ORIGINAL_CALLER')
    direct=[n.value for n in main.body if isinstance(n,ast.Assign)]
    calls=[n.func.attr for n in direct if isinstance(n,ast.Call)and isinstance(n.func,ast.Attribute)and isinstance(n.func.value,ast.Name)and n.func.value.id=='preparation']
    prep.need(calls==['doctor','prepare'],'MANDATORY_PREPARATION_CALLS')
    prep.need(not any(isinstance(n,ast.Try)and any(isinstance(c,ast.Call)and isinstance(c.func,ast.Attribute)and c.func.attr=='prepare'for c in ast.walk(n))for n in ast.walk(main)),'NO_MASKED_PREPARATION')
    text=supervisor.decode()if isinstance(supervisor,bytes)else supervisor
    prep.need(text.index('preparation.prepare(root)')<text.index("capture(root,'source-free-prefix'"),'PREPARATION_BEFORE_FIXTURES')
    profile=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='profile')
    constants=[n.value for n in ast.walk(profile)if isinstance(n,ast.Constant)and isinstance(n.value,str)]
    prep.need('(deny process-exec)'in constants and not any('allow process-exec'in x for x in constants),'FIXTURE_EXEC_DENY')

def run(root,report):
    root=Path(root);dest=root/'preparation-mutations';dest.mkdir(mode=0o700)
    raw=(prep.SOURCE/prep.GENERATOR).read_bytes();record=(prep.SOURCE/prep.RECORD).read_bytes();paths,_=prep.safe_source(raw,record)
    identity=(report['current_head'],report['current_tree']);rows=[]
    def reject(label, operation, expected):
        try:operation()
        except ValueError as error:
            prep.need(str(error).startswith(expected),'WRONG_MUTATION_GUARD:'+label+':'+str(error))
            rows.append(dict(case=label,result='REJECTED_AT_INTENDED_GUARD',guard=str(error),evidence_role='DELIBERATELY_INVALID_DATA',target_starts=0))
        else:raise ValueError('UNEXPECTED_MUTATION_PASS:'+label)
    reject('generator-bytes',lambda:prep.safe_source(raw+b'\n',record),'GENERATOR_IDENTITY')
    reject('extra-project-import',lambda:prep.safe_source(raw+b'\nimport numerical_runtime\n',record),'GENERATOR_IMPORT_CLOSURE')
    reject('record-bytes',lambda:prep.safe_source(raw,record+b'\n'),'RECORD_IDENTITY')
    for role in prep.ROLES:
        base=root/'source-preparation'/role.lower();view=base/'view'
        manifest=json.loads((base/'source-role-manifest.json').read_bytes())
        prep.validate_view(view,role,manifest,paths,raw,record,identity)
        for field,value,guard in [('role','OTHER','VIEW_ROLE'),('generator_sha256','0'*64,'VIEW_CONTROL_ROLES'),('record_sha256','0'*64,'VIEW_CONTROL_ROLES'),('current_head_under_test','0'*40,'CURRENT_BINDING_CONTEXT'),('source_tree','0'*40,'HISTORICAL_VIEW_IDENTITY'if role.startswith('HISTORICAL')else'CURRENT_VIEW_NOT_HISTORICAL')]:
            altered=copy.deepcopy(manifest);altered[field]=value
            reject(role+'-'+field,lambda a=altered:prep.validate_view(view,role,a,paths,raw,record,identity),guard)
        for kind in ('missing','extra','modified','writable'):
            bad=dest/(role+'-'+kind);bad.mkdir(mode=0o700);mm=copy.deepcopy(manifest)
            for path in manifest['files']:
                if kind=='missing'and path==paths[0]:continue
                body=(view/path).read_bytes()
                if kind=='modified'and path==paths[0]:body+=b'\n'
                prep.readonly(bad/path,body)
            if kind=='extra':prep.readonly(bad/'unexpected.py',b'')
            if kind=='writable':(bad/paths[0]).chmod(0o644)
            reject(role+'-view-'+kind,lambda:prep.validate_view(bad,role,mm,paths,raw,record,identity),'VIEW_EXACT_PATH_CENSUS'if kind in ('missing','extra')else'VIEW_SOURCE_BINDING'if kind=='modified'else'VIEW_READONLY_REGULAR')
    current=root/'source-preparation/current_original_check';view=current/'view'
    cm=json.loads((current/'source-role-manifest.json').read_bytes());fake=copy.deepcopy(cm)
    fake.update(role='HISTORICAL_ORIGINAL_CHECK',source_head=prep.HISTORICAL,source_tree=prep.HISTORICAL_TREE)
    reject('current-masquerades-historical',lambda:prep.validate_view(view,'HISTORICAL_ORIGINAL_CHECK',fake,paths,raw,record,identity),'HISTORICAL_ROLE_BODY')
    hist=root/'source-preparation/historical_original_check';hm=json.loads((hist/'source-role-manifest.json').read_bytes());fake=copy.deepcopy(hm)
    fake.update(role='CURRENT_ORIGINAL_CHECK',source_head=identity[0],source_tree=identity[1])
    reject('historical-masquerades-current',lambda:prep.validate_view(hist/'view','CURRENT_ORIGINAL_CHECK',fake,paths,raw,record,identity),'CURRENT_ROLE_BODY')
    capture=json.loads((current/'captures/original/result.json').read_bytes());out=(current/'captures/original/stdout').read_bytes();err=(current/'captures/original/stderr').read_bytes()
    for field,value,guard in [('exit_code',0,'CURRENT_ORIGINAL_UNEXPECTED_PASS'),('exit_code',134,'CURRENT_EXACT_EXPECTED_EXCEPTION'),('signal',6,'ORIGINAL_CHECK_TOOLING_FAILURE'),('timed_out',True,'ORIGINAL_CHECK_TOOLING_FAILURE'),('failed_spawn',{'errno':2},'ORIGINAL_CHECK_TOOLING_FAILURE'),('capture_integrity','FAIL','ORIGINAL_CHECK_CAPTURE'),('reaped',False,'ORIGINAL_CHECK_CAPTURE')]:
        mutant=copy.deepcopy(capture);mutant[field]=value
        reject('status-'+field+'-'+str(value),lambda m=mutant:prep.classify('CURRENT_ORIGINAL_CHECK',m,out,err,view),guard)
    reject('wrong-exception',lambda:prep.classify('CURRENT_ORIGINAL_CHECK',capture,out,err.replace(prep.EXPECTED.encode(),b'ValueError: other'),view),'CURRENT_EXACT_EXPECTED_EXCEPTION')
    reject('wrong-raise-site',lambda:prep.classify('CURRENT_ORIGINAL_CHECK',capture,out,err.replace(str(view/prep.GENERATOR).encode(),b'other.py'),view),'CURRENT_EXPECTED_RAISE_SITE')
    python=capture['argv'][0]
    for argv in ([python,'-c','print(1)'],[python,'-I','-S','-B',str(view/prep.GENERATOR)],[python,'-I','-S','-B',str(view/prep.GENERATOR),'--check','--extra']):
        reject('closed-check-argv-'+str(len(rows)),lambda:prep.validate_original_argv(argv,python,view),'LITERAL_CHECK_ONLY')
    for args in (['fetch'],['status'],['show','--ext-diff'],['rev-parse','HEAD','--anything'],['show',prep.HISTORICAL+':unrelated.py']):
        reject('closed-git-argv-'+str(len(rows)),lambda:prep.validate_setup_command(args,dest),'DATA_GIT_COMMAND')
    trace=(current/'git-trace2.jsonl').read_bytes();expected=prep.original_queries(paths,'CURRENT_ORIGINAL_CHECK')
    altered=copy.deepcopy(expected);altered.reverse()
    reject('git-query-order',lambda:prep.parse_trace(trace,altered),'ACTUAL_GIT_QUERY_ORDER')
    reject('git-query-missing',lambda:prep.parse_trace(trace,expected[:-1]),'ACTUAL_GIT_QUERY_CENSUS')
    reject('extra-git-descendant',lambda:prep.parse_trace(trace+b'{"event":"exec"}\n',expected),'UNEXPECTED_GIT_DESCENDANT_COMMAND')
    supervisor=(prep.SOURCE/'scripts/research/tests/f017_primary_confined_ci_v1.py').read_text();dispatcher=(prep.SOURCE/'scripts/research/tests/f017_primary_ci_dispatch_v1.py').read_text();bootstrap=(prep.SOURCE/'scripts/research/tests/f017_primary_confined_bootstrap_v1.py').read_text();preparation=(prep.SOURCE/'scripts/ci/f017_measurement_preparation_v1.py').read_text()
    gates(supervisor,dispatcher,bootstrap,preparation)
    reject('removed-sealed-case',lambda:gates(supervisor.replace("'WRAPPER_SUCCESSOR',",''),dispatcher,bootstrap,preparation),'SEALED_CASE_BIJECTION')
    reject('removed-original-role',lambda:gates(supervisor,dispatcher,bootstrap,preparation.replace("ROLES=('CURRENT_ORIGINAL_CHECK','HISTORICAL_ORIGINAL_CHECK')","ROLES=('CURRENT_ORIGINAL_CHECK',)")),'ORIGINAL_ROLE_BIJECTION')
    reject('masked-preparation',lambda:gates(supervisor.replace('preparation_report=preparation.prepare(root)','preparation_report=dict(result="PASS")'),dispatcher,bootstrap,preparation),'MANDATORY_PREPARATION_CALLS')
    reject('dead-original-caller',lambda:gates(supervisor,dispatcher+'\n# CI_ORIGINAL_CURRENT\n',bootstrap,preparation),'DEAD_ORIGINAL_CALLER')
    reject('fixture-exec-expanded',lambda:gates(supervisor.replace('(deny process-exec)','(allow process-exec)'),dispatcher,bootstrap,preparation),'FIXTURE_EXEC_DENY')
    result=dict(result='PASS',cases=rows,count=len(rows),unexpected_passes=0,target_starts=0,unconfined_numerical_imports=0,gate_bijection='TWO_MANDATORY_ORIGINAL_PREPARATIONS_PLUS_UNCHANGED_EIGHT_SEALED_GROUPS',scope='DATA_MUTATIONS_NOT_EXECUTION_OBSERVATIONS')
    prep.cap.bank(dest/'result.json',prep.cap.canonical(result));return result
