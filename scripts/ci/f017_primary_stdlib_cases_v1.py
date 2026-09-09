"""Closed primary-only dispatch, imported exclusively after actual fences.

Existing scalar/observer/oracle case bodies are used unchanged. The tiny wrapper
must retain its geometry refusal; it is not full-result or full-forward success.
"""

def run(mode, work, view):
    if mode == 'admission':
        import f017_primary_read_observation_v1 as observer
        import f017_primary_observed_descriptor_source_v1 as observed
        import f017_corrected_oracle_primary_target_source_v11 as target
        import f017_corrected_oracle_primary_wrapper_v11 as wrapper
        assert target.observed is observed
        assert wrapper.source_from_inherited_descriptors is target.source_from_inherited_descriptors
        for name in ('_read_intent', '_read_enter', '_read_return', '_read_error'):
            assert getattr(observed, name) is getattr(observer, name)
        return dict(result='PASS', scope='PRIMARY_STDLIB_IMPORT_ADMISSION',
                    fixture_numerical_operations=0, composition='NOT_RUN')
    cases = {'basic-baseline':'BASIC_BASELINE', 'basic':'BASIC_SUCCESSOR',
             'wrapper-baseline':'WRAPPER_BASELINE', 'wrapper':'WRAPPER_SUCCESSOR',
             'faults':'FAULTS_SUCCESSOR'}
    if mode in cases:
        import primary_suite54
        return primary_suite54.run(cases[mode], work, view)
    if mode == 'integration':
        import f017_primary_integration_cases
        return f017_primary_integration_cases.run('INTEGRATION', work, view)
    raise ValueError('FIXED_PRIMARY_MODE')
