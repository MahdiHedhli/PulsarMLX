"""Prospective current-primary cases, executed only by the sealed fixed child.

Historical helpers are selected at current published bytes, not reconstructed
historical evidence. The production full-geometry refusal remains mandatory.
"""
import json
import os
from pathlib import Path

import primary_suite54 as suite
import primary_cases54 as current_cases
import observation_oracle54 as oracle
import f017_primary_integration_cases as integration
import f017_primary_stdlib_cases_v1 as prior


def exact_consumer(attachment, transcript, ids):
    """Independent, named edge refusals; no candidate reducer supplies expected rows."""
    if attachment['package_attempt_id'] != ids['package_attempt_id'] or attachment['consumer_event_id'] != ids['consumer_event_id']:
        raise ValueError('CROSS_ATTEMPT_BINDING')
    if attachment['last_durable_boundary'] is None:
        raise ValueError('LOST_DURABLE_PREFIX')
    if attachment['completeness'] != 'COMPLETE' or attachment['unknown_suffix'] is not False:
        raise ValueError('INCOMPLETE_NOT_TOTALS')
    expected = oracle.expected_rows(transcript)
    if suite.canonical(attachment['totals']) != suite.canonical(expected):
        raise ValueError('EXACT_REQUEST_COUNTER_MISMATCH')
    oracle.require_complete(attachment, transcript, ids)


def edge_cases(work, view):
    import f017_primary_read_observation_v1 as obs
    import f017_corrected_oracle_primary_target_source_v11 as target
    root = Path(work)/'EDGE_CASES'; root.mkdir(mode=0o700)
    rows = integration.wiring_controls(root, view)
    c = suite.Case(root, 'EXACT-CONSUMER-MUTATIONS', view, suite.basic_records())
    try:
        source, _, _, _, owner = suite.measured_source(c, target, obs)
        values = source.vector('v', 4)
        attachment = suite.completed(c, owner, obs)
        exact_consumer(attachment, c.transcript, c.ids)
        mutations = []
        for label in ('DROP', 'DOUBLE', 'WRONG_SHARD', 'CROSS_ATTEMPT', 'LOST_PREFIX'):
            changed = json.loads(json.dumps(attachment))
            expected = 'EXACT_REQUEST_COUNTER_MISMATCH'
            if label == 'DROP': changed['totals'][1]['attempts'] -= 1
            elif label == 'DOUBLE': changed['totals'][1]['attempts'] += 1
            elif label == 'WRONG_SHARD': changed['totals'][1]['shard_ordinal'] = 4
            elif label == 'CROSS_ATTEMPT':
                changed['consumer_event_id'] += '-OTHER'; expected = 'CROSS_ATTEMPT_BINDING'
            else:
                changed['last_durable_boundary'] = None; expected = 'LOST_DURABLE_PREFIX'
            try: exact_consumer(changed, c.transcript, c.ids)
            except ValueError as error:
                assert str(error) == expected
                mutations.append(dict(case=label, result='REJECTED', exact_reason=str(error)))
            else: raise AssertionError('MUTANT_SURVIVED:'+label)
        rows.append(suite.bank_case(c, dict(case='EXACT-CONSUMER-MUTATIONS', mode='ACTUAL_ATTACHMENT_EDGE',
            result='PASS', transcript=c.transcript, values=values, stop=None,
            observation=attachment, mutations=mutations)))
    finally: c.close()
    c = suite.Case(root, 'DIRECTORY-CLOSE-FAILURE', view, suite.basic_records())
    owner = None; original = os.close; calls = []
    try:
        source, _, _, _, owner = suite.measured_source(c, target, obs)
        values = source.vector('v', 4); selected = owner.directory_fd
        def fail_selected(fd):
            if fd == selected:
                calls.append(fd)
                # Inject a reported close failure after releasing this owned FD.
                # No leaked descriptor is presumed closed by the test.
                original(fd)
                raise OSError('fixed owned directory close failure')
            return original(fd)
        os.close = fail_selected
        attachment = obs._finish_primary_observation(owner, 'RETURNED', 'COMPLETE')
        os.close = original
        assert calls == [selected] and attachment['measurement_failure'] == 'OBSERVATION_DIRECTORY_CLOSE_FAILED'
        oracle.require_incomplete(attachment)
        oracle.verify_prefix(c.observations, attachment, c.transcript, c.expected, view)
        readback = obs._read_primary_observation(c.observations, c.expected)
        # Visible closure cannot reveal the injected post-close failure.
        oracle.verify_durable(c.observations, readback, c.transcript, c.expected, view)
        assert attachment['totals'] is None and attachment['unknown_suffix'] is True
        rows.append(suite.bank_case(c, dict(case='DIRECTORY-CLOSE-FAILURE', mode='ACTUAL_FINALIZATION_EDGE',
            result='PASS', transcript=c.transcript, values=values, stop=None,
            observation=attachment, readback=readback, original_owner_never_upgraded=True,
            injected_close_outcome='CLOSED_THEN_REPORTED_FAILURE')))
    finally:
        os.close = original
        if owner is not None and not owner.finished: obs._finish_primary_observation(owner, 'RAISED', 'COMPLETE')
        c.close()
    summary = dict(result='PASS', cases=rows, full_result_success='NOT_QUALIFIED',
                   actual_api_calls=sum(x['actual_api_calls'] for x in rows))
    digest = suite.save_record(root/'result.json', summary)
    return dict(result='PASS', artifact='EDGE_CASES/result.json', artifact_sha256=digest,
                actual_api_calls=summary['actual_api_calls'])


def run(mode, work, view):
    if mode == 'edges': return edge_cases(work, view)
    if mode in ('basic-baseline', 'basic'):
        return current_cases.run('BASIC_BASELINE' if mode=='basic-baseline' else 'BASIC_SUCCESSOR', work, view)
    if mode not in ('basic-baseline', 'basic', 'wrapper-baseline', 'wrapper', 'faults'):
        raise ValueError('FIXED_COMPOSITION_MODE')
    return prior.run(mode, work, view)
