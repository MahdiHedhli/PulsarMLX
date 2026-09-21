"""Independent historical/current context mutations; confined dispatch only."""
import json
from pathlib import Path
import f017_measurement_scope_v1 as scope

def run(work_dir, code_view):
    view = Path(code_view)
    record = (view/scope.MEASUREMENT).read_bytes()
    generator = (view/scope.GENERATOR).read_bytes()
    declared = json.loads(record)
    objects = {r['path']:(r['git_blob_sha'],(view/'historical-inputs'/r['path']).read_bytes()) for r in declared['measured_paths']}
    def check(**changes):
        values = dict(record_raw=record,generator_raw=generator,head=scope.HISTORICAL_HEAD,tree=scope.HISTORICAL_TREE,objects=objects)
        values.update(changes)
        return scope.verify_historical(**values)
    assert check()['source_rows'] == 36
    results=[]
    def rejection(name, expected, operation):
        try:operation()
        except ValueError as error:
            assert str(error) == expected, (name,str(error),expected)
            results.append(dict(case=name,result='REJECTED_AT_INTENDED_GUARD',diagnostic=str(error)))
        else:raise AssertionError('unexpected mutation pass: '+name)
    rejection('wrong historical head','HISTORICAL_HEAD',lambda:check(head=scope.SOURCE_BASE))
    rejection('wrong historical tree','HISTORICAL_TREE',lambda:check(tree='0'*40))
    rejection('altered historical record','RECORD_IDENTITY',lambda:check(record_raw=record+b' '))
    rejection('altered generator','GENERATOR_IDENTITY',lambda:check(generator_raw=generator+b'\n'))
    p=next(iter(objects));changed=dict(objects);changed.pop(p)
    rejection('missing declared source','HISTORICAL_COMPLETE_CLOSURE',lambda:check(objects=changed))
    changed=dict(objects);changed[p]=('0'*40,objects[p][1])
    rejection('wrong Git blob identity','HISTORICAL_BLOB:'+p,lambda:check(objects=changed))
    changed=dict(objects);raw=objects[p][1]+b'\n';changed[p]=(scope.blob_id(raw),raw)
    rejection('changed actual Git source','HISTORICAL_BLOB:'+p,lambda:check(objects=changed))
    p='scripts/research/f017_corrected_oracle_primary_wrapper_v11.py'
    current=(view/p).read_bytes();assert current!=objects[p][1]
    changed=dict(objects);changed[p]=(scope.blob_id(current),current)
    rejection('current bytes substituted into history','HISTORICAL_BLOB:'+p,lambda:check(objects=changed))
    before=(view/'scope-inputs/workflow-before.yml').read_bytes()
    current_workflow=(view/'scope-inputs/workflow-current.yml').read_bytes()
    native_workflow=(view/'scope-inputs/workflow-native.yml').read_bytes()
    resolution_workflow=(view/'scope-inputs/workflow-resolution.yml').read_bytes()
    def inventory(cur=None,base=None,nat=None,res=None):
        return scope.verify_workflow_inventory(base or before,cur or current_workflow,
                                               nat or native_workflow,res or resolution_workflow)
    def canonical(problem_text):
        return problem_text.encode()
    assert inventory()['both_legs_required']
    rejection('missing old workflow source','WORKFLOW_ORIGINAL_IDENTITY',lambda:inventory(base=before+b'\n'))
    rejection('missing native workflow source','WORKFLOW_NATIVE_IDENTITY',lambda:inventory(nat=native_workflow+b'\n'))
    rejection('missing resolution workflow source','WORKFLOW_RESOLUTION_IDENTITY',lambda:inventory(res=resolution_workflow+b'\n'))

    text=current_workflow.decode()
    res_text=resolution_workflow.decode()
    unrelated_marker='      - name: Validate independent Feature 017 oracle\n'
    jobs_head='jobs:\n'
    required=[s for s in scope._steps(res_text) if scope._is_required('\n'.join(s['lines']))]
    assert len(required)==10,len(required)
    target=[s for s in required if s['name']=='Qualify corrected oracle historical and active authority split'][0]
    block='\n'.join(target['lines'])
    assert text.count(block)==1
    def swap(new_block):
        return text.replace(block,new_block,1).encode()

    # --- lineage construction: the resolution contains the qualify lineage in order ---
    expected_steps={s['name']:s for s in scope._steps(
        before.decode().replace(scope.OLD_COMMAND,('\n          ').join(scope.NEW_COMMANDS))) if s['name']}
    substituted={scope._normalise(c) for c in scope.NEW_COMMANDS}
    for s in required:
        e=expected_steps.get(s['name'])
        if e is None: continue
        assert scope._ordered_subset([scope._normalise(l) for l in e['lines']],
                                     [scope._normalise(l) for l in s['lines']]),s['name']
    results.append(dict(case='resolution contains the qualify lineage in order',
                        result='CONSTRUCTION_VERIFIED',diagnostic='%d required steps'%len(required)))

    # --- Astra round 2: composing allowed lines no longer helps ---
    wrapper_open='          cleanup_v6_historical_worktree() {'
    wrapper_close='          }'
    assert wrapper_open in block and wrapper_close in block
    lines=target['lines']
    head=lines[:2]; body=lines[2:]
    wrapped='\n'.join(head+[wrapper_open]+body+[wrapper_close])
    rejection('required step body wrapped in an uncalled function','WORKFLOW_CHECK_INVENTORY_OR_CONTEXT',
              lambda:inventory(swap(wrapped)))
    rejection('trailing backslash changed on a set line','WORKFLOW_CHECK_INVENTORY_OR_CONTEXT',
              lambda:inventory(swap('\n'.join(l+' \\' if l.strip().startswith('set ') else l for l in lines))))

    # --- execution redirected from outside the step ---
    job_head='  apple-mlx-small-fixtures:\n'
    assert text.count(job_head)==1
    def job_insert(extra):
        return text.replace(job_head,job_head+extra,1).encode()
    rejection('job-level defaults.run.shell replaces execution','WORKFLOW_CHECK_INVENTORY_OR_CONTEXT',
              lambda:inventory(job_insert('    defaults:\n      run:\n        shell: /usr/bin/true {0}\n')))
    # The job already carries an `if:`, so a second one is a duplicate key and
    # the canonical gate rejects it before the residual comparison runs.
    rejection('job disabled with if: false','WORKFLOW_NONCANONICAL',
              lambda:inventory(job_insert('    if: false\n')))
    rejection('job made non-fatal','WORKFLOW_CHECK_INVENTORY_OR_CONTEXT',
              lambda:inventory(job_insert('    continue-on-error: true\n')))
    rejection('job given a timeout','WORKFLOW_CHECK_INVENTORY_OR_CONTEXT',
              lambda:inventory(job_insert('    timeout-minutes: 1\n')))
    jobs_head='jobs:\n'
    assert text.count(jobs_head)==1
    rejection('workflow-level defaults.run.shell replaces execution','WORKFLOW_CHECK_INVENTORY_OR_CONTEXT',
              lambda:inventory(text.replace(jobs_head,'defaults:\n  run:\n    shell: /usr/bin/true {0}\n'+jobs_head,1).encode()))
    rejection('workflow-level env injected','WORKFLOW_CHECK_INVENTORY_OR_CONTEXT',
              lambda:inventory(text.replace(jobs_head,'env:\n  PYTHONOPTIMIZE: "1"\n'+jobs_head,1).encode()))

    # --- the round-5 bypasses stay rejected ---
    name_line=lines[0]
    rejection('required step disabled with if: false','WORKFLOW_CHECK_INVENTORY_OR_CONTEXT',
              lambda:inventory(swap('\n'.join([name_line,'        if: false']+lines[1:]))))
    rejection('required step made non-fatal','WORKFLOW_CHECK_INVENTORY_OR_CONTEXT',
              lambda:inventory(swap('\n'.join([name_line,'        continue-on-error: true']+lines[1:]))))
    rejection('required step given a timeout','WORKFLOW_CHECK_INVENTORY_OR_CONTEXT',
              lambda:inventory(swap('\n'.join([name_line,'        timeout-minutes: 1']+lines[1:]))))
    rejection('errexit disabled inside a required step','WORKFLOW_CHECK_INVENTORY_OR_CONTEXT',
              lambda:inventory(swap('\n'.join(lines[:2]+['          set +e']+lines[2:]))))
    rejection('required step short-circuited with exit 0','WORKFLOW_CHECK_INVENTORY_OR_CONTEXT',
              lambda:inventory(swap('\n'.join(lines[:2]+['          exit 0']+lines[2:]))))
    assertion='          assert qualification["unexpected_passes"] == 0'
    holder=[s for s in required if assertion in '\n'.join(s['lines'])][0]
    hblock='\n'.join(holder['lines'])
    assert text.count(hblock)==1
    def hswap(new_block):
        return text.replace(hblock,new_block,1).encode()
    rejection('result assertion deleted','WORKFLOW_CHECK_INVENTORY_OR_CONTEXT',
              lambda:inventory(hswap(hblock.replace(assertion+'\n','',1))))
    rejection('result assertion weakened','WORKFLOW_CHECK_INVENTORY_OR_CONTEXT',
              lambda:inventory(hswap(hblock.replace(assertion,assertion.replace('== 0','>= 0'),1))))
    rejection('assertion commented out','WORKFLOW_CHECK_INVENTORY_OR_CONTEXT',
              lambda:inventory(hswap(hblock.replace(assertion,'          # '+assertion.strip(),1))))
    continuation='            scripts/research/tests/test_f017_result_envelope_v11.py \\'
    assert continuation in block
    rejection('continuation line masked','WORKFLOW_CHECK_INVENTORY_OR_CONTEXT',
              lambda:inventory(swap(block.replace(continuation,continuation[:-2]+' || true \\',1))))
    rejection('missing current primary leg','WORKFLOW_CHECK_INVENTORY_OR_CONTEXT',
              lambda:inventory(current_workflow.replace(scope.NEW_COMMANDS[1].encode(),b':')))
    rejection('missing unrelated mandatory check','WORKFLOW_CHECK_INVENTORY_OR_CONTEXT',
              lambda:inventory(current_workflow.replace(b'validate_f017_result_authority_v11.py',b'NOT_RUN.py')))
    rejection('current validators moved to historical context','WORKFLOW_CHECK_INVENTORY_OR_CONTEXT',
              lambda:inventory(current_workflow.replace(b'validate_f017_v11_execution_authority_v1.py',b'old/validate_f017_v11_execution_authority_v1.py')))
    rejection('masked command error','WORKFLOW_CHECK_INVENTORY_OR_CONTEXT',
              lambda:inventory(current_workflow.replace(scope.NEW_COMMANDS[0].encode(),scope.NEW_COMMANDS[0].encode()+b' || true')))

    # --- context, ordering and decoys ---
    moved=(text.replace(block+'\n','',1).rstrip('\n')+'\n'
           +'  relocated-job:\n    runs-on: macos-15\n    steps:\n'+block+'\n')
    rejection('required step moved to another job','WORKFLOW_CHECK_INVENTORY_OR_CONTEXT',
              lambda:inventory(moved.encode()))
    second=[s for s in required if s['name']!=target['name']][0]
    b2='\n'.join(second['lines']); assert text.count(b2)==1
    swapped=text.replace(block,'\x00P\x00',1).replace(b2,block,1).replace('\x00P\x00',b2,1)
    rejection('required steps reordered','WORKFLOW_CHECK_INVENTORY_OR_CONTEXT',
              lambda:inventory(swapped.encode()))
    duplicate=(text.rstrip('\n')+'\n  decoy-job:\n    runs-on: macos-15\n    steps:\n'+block+'\n')
    rejection('required step name duplicated in a second job','WORKFLOW_CHECK_INVENTORY_OR_CONTEXT',
              lambda:inventory(duplicate.encode()))

    # --- Astra round 3: spellings that keep YAML meaning but change the bytes ---
    job_head='  apple-mlx-small-fixtures:\n'
    assert text.count(job_head)==1
    noop='      run:\n        shell: /usr/bin/true {0}\n'
    def job_insert(extra): return text.replace(job_head,job_head+extra,1).encode()
    rejection('quoted job-level "defaults" installs a no-op shell','WORKFLOW_NONCANONICAL',
              lambda:inventory(job_insert('    "defaults":\n'+noop)))
    rejection('anchored quoted defaults reused through an alias','WORKFLOW_NONCANONICAL',
              lambda:inventory(job_insert('    "defaults": &noop\n'+noop)))
    rejection('explicit complex key ? defaults','WORKFLOW_NONCANONICAL',
              lambda:inventory(job_insert('    ? defaults\n    :\n'+noop)))
    rejection('tab after defaults:','WORKFLOW_NONCANONICAL',
              lambda:inventory(job_insert('    defaults:\t\n'+noop)))
    rejection('quoted "continue-on-error"','WORKFLOW_NONCANONICAL',
              lambda:inventory(job_insert('    "continue-on-error": true\n')))
    rejection('quoted "strategy"','WORKFLOW_NONCANONICAL',
              lambda:inventory(job_insert('    "strategy":\n      fail-fast: false\n')))
    rejection('flow-style needs list','WORKFLOW_NONCANONICAL',
              lambda:inventory(job_insert('    needs: [classify, documentation]\n')))
    rejection('duplicate jobs: key shadowing the required job','WORKFLOW_NONCANONICAL',
              lambda:inventory(text.replace('jobs:\n','jobs:\n  decoy:\n    runs-on: macos-15\n    steps:\n      - name: decoy\n        run: |\n          true\njobs:\n',1).encode()))
    rejection('second job with the same id','WORKFLOW_NONCANONICAL',
              lambda:inventory((text.rstrip('\n')+'\n'+job_head+'    runs-on: macos-15\n    steps:\n      - name: shadow\n        run: |\n          true\n').encode()))
    rejection('step item without a name','WORKFLOW_NONCANONICAL',
              lambda:inventory(text.replace(unrelated_marker,'      - run: |\n          true\n'+unrelated_marker,1).encode()))
    rejection('alias-only merge into a required step','WORKFLOW_NONCANONICAL',
              lambda:inventory(swap('\n'.join([lines[0],'        <<: *noop']+lines[1:]))))

    # --- workflow-level content is frozen by the residual comparison ---
    rejection('workflow-level quoted "defaults"','WORKFLOW_NONCANONICAL',
              lambda:inventory(text.replace(jobs_head,'"defaults":\n  run:\n    shell: /usr/bin/true {0}\n'+jobs_head,1).encode()))
    rejection('concurrency changed','WORKFLOW_NONCANONICAL',
              lambda:inventory(text.replace('concurrency:\n','concurrency:\n  cancel-in-progress: true\n',1).encode()))
    rejection('permissions changed','WORKFLOW_CHECK_INVENTORY_OR_CONTEXT',
              lambda:inventory(text.replace('permissions:\n','permissions:\n  actions: write\n',1).encode()))
    # The job already sets `env:`, so a second one is a duplicate key.
    rejection('job env added','WORKFLOW_NONCANONICAL',
              lambda:inventory(job_insert('    env:\n      PYTHONOPTIMIZE: "1"\n')))
    rejection('a job with no required steps changed','WORKFLOW_CHECK_INVENTORY_OR_CONTEXT',
              lambda:inventory(text.replace('  aggregate:\n','  aggregate:\n    continue-on-error: true\n',1).encode()))

    # --- still permitted ---
    unrelated=unrelated_marker
    assert text.count(unrelated)==1
    added=('      - name: Unrelated added step\n        run: |\n'
           '          .venv/bin/python scripts/ci/some_other_check.py --check\n')
    assert inventory(text.replace(unrelated,added+unrelated,1).encode())['result']=='PASS'
    results.append(dict(case='additive unrelated step',result='ACCEPTED_AS_ADDITIVE',diagnostic='outside every required step'))
    discovery=b"          .venv/bin/python scripts/ci/run_research_tests.py \\\n"
    assert current_workflow.count(discovery)==1
    assert inventory(current_workflow.replace(discovery,b"          .venv/bin/python -m unittest discover \\\n",1))['result']=='PASS'
    results.append(dict(case='modified non-required step',result='ACCEPTED_AS_UNCONSTRAINED',diagnostic='Feature-002 discovery line'))

    # Expectations use independently read recorded rows, not adapter results.
    assert len(objects)==36 and declared['implementation_head']=='f35d341110c67377200ad353ab56a3cf38615a73'
    return dict(result='PASS',historical_controls=len(results),mutations=results,
                historical_record_sha256=scope.digest(record),generator_sha256=scope.digest(generator),
                historical_current_context_separation=True,unexpected_passes=0)
