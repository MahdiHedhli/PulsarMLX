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
    assert scope.verify_workflow_inventory(before,current_workflow)['both_legs_required']
    rejection('missing old workflow source','WORKFLOW_ORIGINAL_IDENTITY',lambda:scope.verify_workflow_inventory(before+b'\n',current_workflow))
    rejection('missing current primary leg','WORKFLOW_CHECK_INVENTORY_OR_CONTEXT',lambda:scope.verify_workflow_inventory(before,current_workflow.replace(scope.NEW_COMMANDS[1].encode(),b':')))
    rejection('missing unrelated mandatory check','WORKFLOW_CHECK_INVENTORY_OR_CONTEXT',lambda:scope.verify_workflow_inventory(before,current_workflow.replace(b'validate_f017_result_authority_v11.py',b'NOT_RUN.py')))
    rejection('current validators moved to historical context','WORKFLOW_CHECK_INVENTORY_OR_CONTEXT',lambda:scope.verify_workflow_inventory(before,current_workflow.replace(b'validate_f017_v11_execution_authority_v1.py',b'old/validate_f017_v11_execution_authority_v1.py')))
    rejection('masked command error','WORKFLOW_CHECK_INVENTORY_OR_CONTEXT',lambda:scope.verify_workflow_inventory(before,current_workflow.replace(scope.NEW_COMMANDS[0].encode(),scope.NEW_COMMANDS[0].encode()+b' || true')))
    # --- narrowed inventory: additive CI is allowed, dropped/edited/moved is not ---
    inventory=scope.verify_workflow_inventory(before,current_workflow)
    assert inventory['required_invocations']>0
    baseline_additive=inventory['additive_invocations']

    def step(job_marker, body):
        """An extra step appended to the job that already carries the checks."""
        return body

    # (b) an unrelated added step with a new check is additive, not a rejection.
    text=current_workflow.decode()
    marker='      - name: Validate independent Feature 017 oracle\n'
    assert text.count(marker)==1
    added=('      - name: Unrelated added step\n'
           '        run: |\n'
           '          .venv/bin/python scripts/ci/some_other_check.py --check\n')
    augmented=text.replace(marker, added+marker, 1).encode()
    result=scope.verify_workflow_inventory(before,augmented)
    assert result['result']=='PASS', result
    assert result['additive_invocations']==baseline_additive+1, result
    results.append(dict(case='additive unrelated check',result='ACCEPTED_AS_ADDITIVE',
                        diagnostic='additive_invocations=%d'%result['additive_invocations']))

    # (d1) duplicating an expected invocation elsewhere stays a PASS.
    duplicated=text.replace(marker, added.replace('scripts/ci/some_other_check.py --check',
                                                  scope.NEW_COMMANDS[0])+marker, 1).encode()
    assert scope.verify_workflow_inventory(before,duplicated)['result']=='PASS'
    results.append(dict(case='duplicated expected invocation',result='ACCEPTED_AS_ADDITIVE',diagnostic='duplicate permitted'))

    # (c) an expected invocation moved into a different job is rejected.
    moved_line='          .venv/bin/python scripts/research/validate_f017_result_authority_v11.py\n'
    assert text.count(moved_line)==1
    other_job=('  relocated-job:\n'
               '    runs-on: macos-15\n'
               '    steps:\n'
               '      - name: Relocated check\n'
               '        run: |\n'
               +moved_line)
    relocated=(text.replace(moved_line,'',1).rstrip('\n')+'\n'+other_job).encode()
    rejection('expected invocation relocated to another job','WORKFLOW_CHECK_INVENTORY_OR_CONTEXT',
              lambda:scope.verify_workflow_inventory(before,relocated))

    # (d2) reordering two expected invocations relative to each other is rejected.
    first='          .venv/bin/python scripts/research/validate_f017_result_envelope_design_v11.py\n'
    second='          .venv/bin/python scripts/research/validate_f017_result_authority_v11.py\n'
    assert text.count(first)==1 and text.count(second)==1 and text.index(first)<text.index(second)
    swapped=text.replace(first,'\x00',1).replace(second,first,1).replace('\x00',second,1).encode()
    rejection('expected invocations reordered','WORKFLOW_CHECK_INVENTORY_OR_CONTEXT',
              lambda:scope.verify_workflow_inventory(before,swapped))

    # Expectations use independently read recorded rows, not adapter results.
    assert len(objects)==36 and declared['implementation_head']=='f35d341110c67377200ad353ab56a3cf38615a73'
    return dict(result='PASS',historical_controls=len(results),mutations=results,
                historical_record_sha256=scope.digest(record),generator_sha256=scope.digest(generator),
                historical_current_context_separation=True,unexpected_passes=0)
