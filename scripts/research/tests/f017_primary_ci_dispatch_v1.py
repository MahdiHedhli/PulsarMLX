"""Fixed CI cases, imported exclusively after confinement fences pass."""
def run(case_id, work_dir, code_view):
    if case_id in ('CI_ORIGINAL_CURRENT','CI_ORIGINAL_HISTORICAL'):
        import sys
        import generate_f017_v11_measurement_v1 as original
        import f017_measurement_scope_v1 as scope
        from pathlib import Path
        assert scope.digest((Path(code_view)/scope.GENERATOR).read_bytes()) == scope.GENERATOR_SHA
        assert original.ROOT == Path(code_view)
        saved = sys.argv
        sys.argv = [str(Path(code_view)/scope.GENERATOR),'--check']
        try:
            try:
                status = original.main()
            except ValueError as error:
                assert case_id == 'CI_ORIGINAL_CURRENT'
                expected = 'working tree differs from measurement head: scripts/research/f017_corrected_oracle_primary_wrapper_v11.py'
                assert str(error) == expected
                return dict(result='PASS', original_check_result='EXPECTED_FAILURE', diagnostic='ValueError: '+str(error), numerical_executions=0)
            assert case_id == 'CI_ORIGINAL_HISTORICAL' and status == 0
            return dict(result='PASS', original_check_result='PASS_HISTORICAL_COMPOSITE_ONLY', numerical_executions=0)
        finally:
            sys.argv = saved
    if case_id == 'CI_SCOPE_TESTS':
        import f017_measurement_scope_tests_v1
        return f017_measurement_scope_tests_v1.run(work_dir, code_view)
    if case_id in ('INTEGRATION','HISTORICAL_DRIFT_CONTROL','ACTIVE_CENSUS_CONTROL'):
        import f017_primary_integration_cases
        return f017_primary_integration_cases.run(case_id, work_dir, code_view)
    import primary_suite54
    return primary_suite54.run(case_id, work_dir, code_view)
