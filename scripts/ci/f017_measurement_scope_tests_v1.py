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
    def inventory(cur=None,base=None,nat=None):
        return scope.verify_workflow_inventory(base or before,cur or current_workflow,nat or native_workflow)
    assert inventory()['both_legs_required']
    rejection('missing old workflow source','WORKFLOW_ORIGINAL_IDENTITY',lambda:inventory(base=before+b'\n'))
    rejection('missing native workflow source','WORKFLOW_NATIVE_IDENTITY',lambda:inventory(nat=native_workflow+b'\n'))
    rejection('missing current primary leg','WORKFLOW_CHECK_INVENTORY_OR_CONTEXT',lambda:inventory(current_workflow.replace(scope.NEW_COMMANDS[1].encode(),b':')))
    rejection('missing unrelated mandatory check','WORKFLOW_CHECK_INVENTORY_OR_CONTEXT',lambda:inventory(current_workflow.replace(b'validate_f017_result_authority_v11.py',b'NOT_RUN.py')))
    rejection('current validators moved to historical context','WORKFLOW_CHECK_INVENTORY_OR_CONTEXT',lambda:inventory(current_workflow.replace(b'validate_f017_v11_execution_authority_v1.py',b'old/validate_f017_v11_execution_authority_v1.py')))
    rejection('masked command error','WORKFLOW_CHECK_INVENTORY_OR_CONTEXT',lambda:inventory(current_workflow.replace(scope.NEW_COMMANDS[0].encode(),scope.NEW_COMMANDS[0].encode()+b' || true')))

    # --- two-lineage construction: the lineages must themselves agree ---
    text=current_workflow.decode()
    steps={s['name']:s for s in scope._steps(text) if s['name']}
    native_steps={s['name']:s for s in scope._steps(native_workflow.decode()) if s['name']}
    expected_steps={s['name']:s for s in scope._steps(
        before.decode().replace(scope.OLD_COMMAND,('\n          ').join(scope.NEW_COMMANDS))) if s['name']}
    differing=[n for n,s in expected_steps.items()
               if scope._is_required('\n'.join(s['lines']))
               and [scope._normalise(l) for l in s['lines']]!=[scope._normalise(l) for l in steps[n]['lines']]]
    assert len(differing)==1,differing
    only=differing[0]
    # The two lineages must agree on everything except the sanctioned substitution
    # itself: NEW_COMMANDS exist only on the qualify side, because the native
    # workflow never carried OLD_COMMAND and so has neither form of it. Every
    # other expected line must still appear in the native block, in order.
    substituted={scope._normalise(c) for c in scope.NEW_COMMANDS}
    shared=[scope._normalise(l) for l in expected_steps[only]['lines']
            if scope._normalise(l) not in substituted]
    native_lines=[scope._normalise(l) for l in native_steps[only]['lines']]
    assert substituted.isdisjoint(native_lines),only
    assert scope._ordered_subset(shared,native_lines),only
    results.append(dict(case='two lineages agree on the one differing required step',
                        result='CONSTRUCTION_VERIFIED',
                        diagnostic=only+' (native adds only; shared lines in order)'))

    # --- Astra's demonstrated bypasses, now rejected ---
    required_name='Qualify corrected oracle historical and active authority split'
    marker='      - name: '+required_name+'\n        run: |\n'
    assert text.count(marker)==1
    def mutate(new_head):
        return text.replace(marker,new_head,1).encode()
    rejection('required step disabled with if: false','WORKFLOW_CHECK_INVENTORY_OR_CONTEXT',
              lambda:inventory(mutate('      - name: '+required_name+'\n        if: false\n        run: |\n')))
    rejection('required step made non-fatal','WORKFLOW_CHECK_INVENTORY_OR_CONTEXT',
              lambda:inventory(mutate('      - name: '+required_name+'\n        continue-on-error: true\n        run: |\n')))
    rejection('required step given a timeout','WORKFLOW_CHECK_INVENTORY_OR_CONTEXT',
              lambda:inventory(mutate('      - name: '+required_name+'\n        timeout-minutes: 1\n        run: |\n')))
    rejection('errexit disabled inside a required step','WORKFLOW_CHECK_INVENTORY_OR_CONTEXT',
              lambda:inventory(mutate(marker+'          set +e\n')))
    rejection('required step short-circuited with exit 0','WORKFLOW_CHECK_INVENTORY_OR_CONTEXT',
              lambda:inventory(mutate(marker+'          exit 0\n')))
    assertion=b'          assert qualification["unexpected_passes"] == 0\n'
    assert current_workflow.count(assertion)>=1
    rejection('result assertion deleted','WORKFLOW_CHECK_INVENTORY_OR_CONTEXT',
              lambda:inventory(current_workflow.replace(assertion,b'',1)))
    rejection('result assertion weakened','WORKFLOW_CHECK_INVENTORY_OR_CONTEXT',
              lambda:inventory(current_workflow.replace(assertion,assertion.replace(b'== 0',b'>= 0'),1)))
    continuation=b'            scripts/research/tests/test_f017_result_envelope_v11.py \\\n'
    assert current_workflow.count(continuation)==1
    rejection('continuation line masked','WORKFLOW_CHECK_INVENTORY_OR_CONTEXT',
              lambda:inventory(current_workflow.replace(continuation,continuation.rstrip(b'\\\n')+b' || true \\\n',1)))
    rejection('assertion reordered before its setup','WORKFLOW_CHECK_INVENTORY_OR_CONTEXT',
              lambda:inventory(current_workflow.replace(assertion,b'',1).replace(marker.encode(),marker.encode()+assertion,1)))

    # --- context and ordering ---
    required_names=[n for n,s in expected_steps.items() if scope._is_required('\n'.join(s['lines']))]
    first_block='\n'.join(steps[required_names[0]]['lines'])
    moved=(text.replace(first_block+'\n','',1).rstrip('\n')+'\n'
           +'  relocated-job:\n    runs-on: macos-15\n    steps:\n'+first_block+'\n')
    rejection('required step moved to another job','WORKFLOW_CHECK_INVENTORY_OR_CONTEXT',
              lambda:inventory(moved.encode()))
    a_block='\n'.join(steps[required_names[0]]['lines'])
    b_block='\n'.join(steps[required_names[1]]['lines'])
    swapped=text.replace(a_block,'\x00PLACEHOLDER\x00',1).replace(b_block,a_block,1).replace('\x00PLACEHOLDER\x00',b_block,1)
    rejection('required steps reordered','WORKFLOW_CHECK_INVENTORY_OR_CONTEXT',
              lambda:inventory(swapped.encode()))

    # --- still permitted: additive steps and non-required changes ---
    unrelated='      - name: Validate independent Feature 017 oracle\n'
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
