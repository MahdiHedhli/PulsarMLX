"""Fixed CI cases, imported exclusively after confinement fences pass."""
def run(case_id, work_dir, code_view):
    if case_id == 'CI_SCOPE_TESTS':
        import f017_measurement_scope_tests_v1
        return f017_measurement_scope_tests_v1.run(work_dir, code_view)
    if case_id in ('INTEGRATION','HISTORICAL_DRIFT_CONTROL','ACTIVE_CENSUS_CONTROL'):
        import f017_primary_integration_cases
        return f017_primary_integration_cases.run(case_id, work_dir, code_view)
    import primary_suite54
    return primary_suite54.run(case_id, work_dir, code_view)
