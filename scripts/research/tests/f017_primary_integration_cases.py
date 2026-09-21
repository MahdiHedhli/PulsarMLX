"""Fixed primary relocation checks for the confined qualification loader only.

Not an unconfined discovery runner. All payload files are tiny synthetic files;
the admitted loader must seal and prove its fences before importing this module.
These checks do not qualify a production result, secondary path or native I/O.
"""
import hashlib
import io
import json
from pathlib import Path
import sys

HISTORICAL_SHA = "ceab082d593a22fc30f76e67947b1819809edf0be488476f7affa326f5e744f4"
OBSERVED_SHA = "752fd55ba1ad641e3ab26b545e983a6bf798032d75a916e83e6c8fc2f701d28b"
VALIDATOR_SHA = "dec34ba2157f04dcea6e64347bb96dc4288bfc8d676fdb1b10801c5146602253"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def rejects(operation):
    try:
        operation()
    except (AssertionError, ValueError, TypeError):
        return True
    return False


def historical_validator(view):
    import validate_f017_v11_execution_authority_v1 as validator
    path = Path(view) / "scripts/research/validate_f017_v11_execution_authority_v1.py"
    assert digest(path.read_bytes()) == VALIDATOR_SHA
    assert validator.ROOT == Path(view)
    saved = sys.stdout
    output = io.StringIO()
    try:
        sys.stdout = output
        status = validator.main()
    finally:
        sys.stdout = saved
    assert status == 0
    result = json.loads(output.getvalue())
    assert result["result"] == "PASS"
    return result


def active_wiring():
    import f017_corrected_oracle_primary_target_source_v11 as target
    import f017_corrected_oracle_primary_wrapper_v11 as wrapper
    import f017_primary_observed_descriptor_source_v1 as observed
    import f017_primary_read_observation_v1 as observer
    assert target.observed is observed
    assert target.PrimaryDescriptorSourceV11.__bases__ == (observed.PrimaryDescriptorSourceV10,)
    assert wrapper.source_from_inherited_descriptors is target.source_from_inherited_descriptors
    for name in ("_read_intent", "_read_enter", "_read_return", "_read_error"):
        assert getattr(observed, name) is getattr(observer, name)
    return True


def wiring_controls(area, view):
    import f017_corrected_oracle_primary_target_source_v10 as historical
    import f017_corrected_oracle_primary_target_source_v11 as target
    import f017_primary_observed_descriptor_source_v1 as observed
    import f017_primary_read_observation_v1 as observer
    import primary_suite54 as suite
    import observation_oracle54 as oracle
    results = []
    saved_class = target.PrimaryDescriptorSourceV11

    class UnobservedFixtureSource(historical.PrimaryDescriptorSourceV10):
        def __init__(self, candidate, identities, descriptors, *, _observation_owner=None):
            super().__init__(candidate, identities, descriptors)
            self.path_reopen_count = 0

    case = suite.Case(area, "UNINSTRUMENTED-ACTIVE", view, suite.basic_records())
    owner = None
    try:
        target.PrimaryDescriptorSourceV11 = UnobservedFixtureSource
        assert rejects(active_wiring)
        owner = observer._start_primary_observation(case.candidate, case.identities, case.observations, case.authority)
        source, _, _, _ = target.source_from_inherited_descriptors(
            case.candidate, case.identities, case.fds, _observation_owner=owner)
        assert source.vector("v", 4) == [1., 2., -3., 4.]
        attachment = observer._finish_primary_observation(owner, "RETURNED", "COMPLETE")
        assert len(case.transcript) == 3
        assert rejects(lambda: oracle.require_complete(attachment, case.transcript, case.ids))
        results.append(suite.bank_case(case, dict(case="UNINSTRUMENTED-ACTIVE", mode="SEPARATION_CONTROL",
            result="PASS", transcript=case.transcript, values=[1., 2., -3., 4.], stop=None,
            observation=attachment, mutant_rejected=True)))
    finally:
        target.PrimaryDescriptorSourceV11 = saved_class
        if owner is not None and not owner.finished:
            observer._finish_primary_observation(owner, "RAISED", "COMPLETE")
        case.close()

    case = suite.Case(area, "MISSING-ACTIVE-RETURN", view, suite.basic_records())
    owner = None
    saved_return = observed._read_return
    try:
        source, _, _, _, owner = suite.measured_source(case, target, observer)
        observed._read_return = lambda *args: None
        assert rejects(active_wiring)
        assert source.vector("v", 4) == [1., 2., -3., 4.]
        attachment = observer._finish_primary_observation(owner, "RETURNED", "COMPLETE")
        oracle.require_incomplete(attachment)
        oracle.verify_prefix(case.observations, attachment, case.transcript, case.expected, view)
        assert rejects(lambda: oracle.require_complete(attachment, case.transcript, case.ids))
        results.append(suite.bank_case(case, dict(case="MISSING-ACTIVE-RETURN", mode="SEPARATION_CONTROL",
            result="PASS", transcript=case.transcript, values=[1., 2., -3., 4.], stop=None,
            observation=attachment, mutant_rejected=True)))
    finally:
        observed._read_return = saved_return
        if owner is not None and not owner.finished:
            observer._finish_primary_observation(owner, "RAISED", "COMPLETE")
        case.close()
    assert active_wiring()
    return results


def run(case_id, work_dir, code_view):
    assert case_id in ("INTEGRATION", "HISTORICAL_DRIFT_CONTROL", "ACTIVE_CENSUS_CONTROL")
    view = Path(code_view)
    research = view / "scripts/research"
    historical = (research / "f017_corrected_oracle_primary_target_source_v10.py").read_bytes()
    observed = (research / "f017_primary_observed_descriptor_source_v1.py").read_bytes()
    if case_id == "HISTORICAL_DRIFT_CONTROL":
        assert digest(historical) != HISTORICAL_SHA
        try:
            historical_validator(view)
        except ValueError as error:
            assert str(error) == "historical V10 target-source drift: f017_corrected_oracle_primary_target_source_v10.py"
            return dict(result="PASS", case_id=case_id, validator_sha256=VALIDATOR_SHA,
                        actual_rejection=str(error), actual_api_calls=0)
        raise AssertionError("The unchanged historical validator accepted changed historical bytes")
    if case_id == "ACTIVE_CENSUS_CONTROL":
        import f017_primary_read_observation_v1 as observer
        import observation_oracle54 as oracle
        assert digest(historical) == HISTORICAL_SHA
        assert digest(observed) != OBSERVED_SHA
        mapping = {name: digest((research/name).read_bytes()) for name in oracle.FILES}
        assert observer._implementation_sha() == oracle.implementation_binding(view)
        changed_binding = observer._implementation_sha()
        mapping["f017_primary_observed_descriptor_source_v1.py"] = OBSERVED_SHA
        original_binding = digest(oracle.canon(mapping))
        assert changed_binding != original_binding
        return dict(result="PASS", case_id=case_id, actual_api_calls=0,
                    active_source_change_detected=True, original_binding=original_binding,
                    changed_binding=changed_binding)
    assert digest(historical) == HISTORICAL_SHA
    assert digest(observed) == OBSERVED_SHA
    assert digest(historical + b"\n") != HISTORICAL_SHA
    assert active_wiring()
    validation = historical_validator(view)
    import f017_primary_read_observation_v1 as observer
    import observation_oracle54 as oracle
    binding = oracle.implementation_binding(view)
    assert observer._implementation_sha() == binding
    assert "f017_primary_observed_descriptor_source_v1.py" in oracle.FILES
    assert "f017_corrected_oracle_primary_target_source_v10.py" not in oracle.FILES
    mapping = {name: digest((research/name).read_bytes()) for name in oracle.FILES}
    mapping["f017_primary_observed_descriptor_source_v1.py"] = digest(observed + b"\n")
    assert digest(oracle.canon(mapping)) != binding, "New active bytes escaped the measurement binding"
    area = Path(work_dir) / case_id
    area.mkdir(mode=0o700)
    controls = wiring_controls(area, view)
    import primary_suite54 as suite
    wrapper = suite.wrapper_case(area, "BANK-18101", view, "BANK", observer, 18101)
    summary = dict(result="PASS", case_id=case_id, historical_validator=validation,
        historical_sha256=digest(historical), active_sha256=digest(observed),
        measurement_implementation_sha256=binding, active_census_mutation_rejected=True,
        active_source_imports_historical=False, separation_controls=controls,
        wrapper_confirmation=wrapper,
        unexpected_passes=0, full_result_success="NOT_QUALIFIED", actual_api_calls=sum(x["actual_api_calls"] for x in controls)+wrapper["actual_api_calls"])
    h = suite.save_record(area / "integration-result.json", summary)
    return dict(result="PASS", case_id=case_id, artifact="INTEGRATION/integration-result.json",
        artifact_sha256=h, controls=len(controls), actual_api_calls=summary["actual_api_calls"])
