"""Fail-closed checks for the prospective F020 v2.4 qualification driver."""

import importlib.util
import math
import struct
from pathlib import Path
from types import SimpleNamespace

import pytest

DRIVER_PATH = Path(__file__).resolve().parents[1] / "f020_fused_swiglu_qualification_v2_3.py"
SPEC = importlib.util.spec_from_file_location("f020_v2_3_driver", DRIVER_PATH)
assert SPEC is not None and SPEC.loader is not None
driver = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(driver)
HEAD = "f" * 40


def mock_git(monkeypatch, status_code=0, status_output=""):
    def command(args, *, cwd=None):
        if args[1:3] == ["branch", "--show-current"]:
            return driver.BRANCH + "\n"
        if args[1:3] == ["rev-parse", "HEAD"]:
            return HEAD + "\n"
        if args[1:3] == ["ls-remote", "origin"]:
            return HEAD + "\trefs/heads/" + driver.BRANCH + "\n"
        raise AssertionError(args)
    monkeypatch.setattr(driver, "run", command)
    monkeypatch.setattr(driver.subprocess, "run", lambda *a, **k: SimpleNamespace(
        returncode=status_code, stdout=status_output, stderr="injected failure"))


def test_git_status_failure_without_stdout_is_rejected(monkeypatch):
    mock_git(monkeypatch, status_code=1)
    with pytest.raises(SystemExit, match="Git status failed"):
        driver.git_authority(HEAD)


def test_git_status_os_error_is_rejected(monkeypatch):
    mock_git(monkeypatch)
    def unavailable(*args, **kwargs):
        raise OSError("injected status failure")
    monkeypatch.setattr(driver.subprocess, "run", unavailable)
    with pytest.raises(SystemExit, match="Git status failed"):
        driver.git_authority(HEAD)


def test_git_status_dirty_output_is_rejected(monkeypatch):
    mock_git(monkeypatch, status_output=" M Cargo.toml\n")
    with pytest.raises(SystemExit, match="Git authority mismatch"):
        driver.git_authority(HEAD)


def test_git_clean_parity_is_accepted(monkeypatch):
    mock_git(monkeypatch)
    assert driver.git_authority(HEAD) == HEAD


def structured_report():
    delta = struct.unpack(">Q", struct.pack(">d", math.nextafter(0.0, math.inf)))[0]
    controls = [
        {"gate_f32_bits": driver.f32_bits(gate), "up_f32_bits": driver.f32_bits(up),
         "candidate_n_output_f32_bits": "0x00000000",
         "candidate_b_output_f32_bits": "0x00000000",
         "upward_rounded_abs_delta_bits": f"0x{delta:016x}"}
        for gate, up in driver.fixed_controls()
    ]
    return {"schema": "pulsarmlx.f020.native-bridge-v2-3-structured/1.1.0",
            "structured": True, "total_evaluated": 42, "anomaly_count": 0,
            "cpu_fpcr": 0, "cpu_guard_checks": 4,
            "controls": controls}


def test_exact_frozen_control_grid_and_deltas_are_accepted():
    assert len(driver.validate_structured_controls(structured_report())) == 42


def test_signed_zero_control_identity_is_enforced():
    report = structured_report()
    report["controls"][14]["gate_f32_bits"] = driver.f32_bits(0.0)
    with pytest.raises(SystemExit, match="frozen gate/up grid"):
        driver.validate_structured_controls(report)


def test_nonzero_upward_delta_is_accepted():
    report = structured_report()
    report["controls"][0]["candidate_n_output_f32_bits"] = driver.f32_bits(1.0)
    delta = math.nextafter(1.0, math.inf)
    report["controls"][0]["upward_rounded_abs_delta_bits"] = (
        f"0x{struct.unpack('>Q', struct.pack('>d', delta))[0]:016x}")
    assert len(driver.validate_structured_controls(report)) == 42


def test_reordered_or_replaced_control_is_rejected():
    report = structured_report()
    report["controls"][1]["gate_f32_bits"] = report["controls"][7]["gate_f32_bits"]
    with pytest.raises(SystemExit, match="frozen gate/up grid"):
        driver.validate_structured_controls(report)


def test_missing_delta_bits_are_rejected():
    report = structured_report()
    del report["controls"][0]["upward_rounded_abs_delta_bits"]
    with pytest.raises(SystemExit, match="lacks candidate/delta bit evidence"):
        driver.validate_structured_controls(report)


def test_incorrect_delta_bits_are_rejected():
    report = structured_report()
    report["controls"][0]["upward_rounded_abs_delta_bits"] = "0x0000000000000000"
    with pytest.raises(SystemExit, match="delta does not match"):
        driver.validate_structured_controls(report)


def test_claimed_count_without_42_controls_is_rejected():
    report = structured_report()
    report["controls"].pop()
    with pytest.raises(SystemExit, match="incomplete or anomalous"):
        driver.validate_structured_controls(report)


def test_published_source_pins_are_in_privacy_set():
    assert driver.PINS in driver.PUBLIC_FILES


def test_privacy_scan_rejects_prohibited_text(monkeypatch, tmp_path):
    published = tmp_path / "source-pins.json"
    published.write_text("m" + "hedhli")
    monkeypatch.setattr(driver, "ROOT", tmp_path)
    monkeypatch.setattr(driver, "PUBLIC_FILES", (published,))
    with pytest.raises(SystemExit, match="privacy scan matched"):
        driver.privacy_scan()



def sweep_report():
    delta = math.nextafter(1.0, math.inf)
    delta_bits = f"0x{struct.unpack('>Q', struct.pack('>d', delta))[0]:016x}"
    return {"schema": "pulsarmlx.f020.native-bridge-v2-result/1.2.0",
            "candidate_observations": 1, "anomaly_count": 0,
            "cpu_fpcr": 0, "cpu_guard_checks": 6295, "batch_count": 2098,
            "gate_count_exhaustive": True, "total_evaluated": driver.EXPECTED_TOTAL,
            "range_counts": {"positive": 1098907649, "negative": 1098907649},
            "range_endpoints": {"positive_start": "0x00000000", "positive_end": "0x41800000",
                                "negative_start": "0x80000000", "negative_end": "0xc1800000"},
            "input_gate_f32_bits": driver.f32_bits(0.0),
            "candidate_n_output_f32_bits": driver.f32_bits(1.0),
            "candidate_b_output_f32_bits": driver.f32_bits(0.0),
            "upward_rounded_abs_delta_bits": delta_bits, "max_delta_f64_bits": delta_bits}


def test_exhaustive_delta_bound_to_witness():
    assert driver.validate_sweep_result(sweep_report()) > 1


@pytest.mark.parametrize("field,value", [
    ("max_delta_f64_bits", "0x0000000000000001"),
    ("upward_rounded_abs_delta_bits", "0x0000000000000001"),
    ("candidate_n_output_f32_bits", "0x40000000"),
    ("total_evaluated", 42),
    ("gate_count_exhaustive", False),
])
def test_exhaustive_result_mismatch_is_rejected(field, value):
    report = sweep_report()
    report[field] = value
    with pytest.raises(SystemExit):
        driver.validate_sweep_result(report)


def test_execution_requires_new_report_before_other_work(tmp_path):
    with pytest.raises(SystemExit, match="--report"):
        driver.require_execution_report(SimpleNamespace(execute=True, report=None))
    existing = tmp_path / "existing.json"
    existing.write_text("do not replace")
    with pytest.raises(SystemExit, match="refusing overwrite"):
        driver.require_execution_report(SimpleNamespace(execute=True, report=existing))
    driver.require_execution_report(SimpleNamespace(execute=True, report=tmp_path / "new.json"))


def test_capability_uses_canonical_execution_root(tmp_path):
    alias = tmp_path / "alias"
    actual = tmp_path / "actual"
    actual.mkdir()
    alias.symlink_to(actual, target_is_directory=True)
    assert driver.canonical_execution_root(str(alias)) == actual.resolve()


@pytest.mark.parametrize("field,value", [
    ("cpu_fpcr", 1 << 24), ("cpu_fpcr", 1 << 22), ("cpu_fpcr", 1),
    ("cpu_fpcr", 2), ("cpu_fpcr", None), ("cpu_guard_checks", 6294),
    ("batch_count", 2097),
])
def test_sweep_cpu_guard_or_batch_evidence_mismatch_rejected(field, value):
    report = sweep_report()
    report[field] = value
    with pytest.raises(SystemExit):
        driver.validate_sweep_result(report)


def test_structured_cpu_guard_missing_rejected():
    report = structured_report()
    del report["cpu_guard_checks"]
    with pytest.raises(SystemExit, match="CPU arithmetic guard"):
        driver.validate_structured_controls(report)


# Static proof/model tests; these never invoke a candidate evaluator.
import json
from fractions import Fraction

PROOF_PATH = DRIVER_PATH.parent / "f020_fused_swiglu_proof_v2_4.py"
PROOF_SPEC = importlib.util.spec_from_file_location("f020_static_proof", PROOF_PATH)
assert PROOF_SPEC is not None and PROOF_SPEC.loader is not None
proof = importlib.util.module_from_spec(PROOF_SPEC)
PROOF_SPEC.loader.exec_module(proof)


def contract_inputs():
    return [json.loads(path.read_text()) for path in (proof.SWEEP, proof.B_CONTRACT, proof.DOWN)]


def test_exact_proof_ledger_and_index_boundaries_pass():
    proof.certify_ln2()
    assert proof.certify_ledger()["beta_B"] == "5201/4194304"
    assert proof.certify_indices()["full_domain_total"] == 2197815298
    proof.certify_contracts(*contract_inputs())


@pytest.mark.parametrize("field,value", [
    ("positive_range", ["0x00000001", "0x41800000"]),
    ("negative_range", ["0x80000001", "0xc1800000"]),
    ("expected_positive_count", 1098907648),
    ("expected_negative_count", 1098907648),
    ("expected_total_evaluated", 2197815296),
    ("batch_elements", 2048),
])
def test_narrowed_domain_or_dropped_cases_rejected(field, value):
    sweep, candidate, down = contract_inputs()
    sweep["enumeration"][field] = value
    with pytest.raises(proof.ProofError, match="domain/count/batch"):
        proof.certify_contracts(sweep, candidate, down)


def test_budget_change_and_down_admission_weakening_rejected():
    sweep, candidate, down = contract_inputs()
    sweep["budgets"]["beta_B"] = "1/128"
    with pytest.raises(proof.ProofError, match="budgets drift"):
        proof.certify_contracts(sweep, candidate, down)
    sweep, candidate, down = contract_inputs()
    down["admission"]["reject"].remove("subnormal")
    with pytest.raises(proof.ProofError, match="admission"):
        proof.certify_contracts(sweep, candidate, down)


def test_subnormal_model_keeps_bits_and_ties_even():
    assert proof.rn32_bits(Fraction(1, 2**149) * 32) == 32
    assert proof.rn32_bits(Fraction(1, 2**126) / 2) == 0x00400000
    assert proof.rn32_bits(Fraction(1, 2**150)) == 0
    assert proof.rn32_bits(Fraction(3, 2**150)) == 2
    assert proof.rn32_bits(-Fraction(1, 2**150)) == 0x80000000
    assert proof.rn32_bits(1 + Fraction(1, 2**24)) == 0x3f800000
    assert proof.rn32_bits(1 + Fraction(3, 2**24)) == 0x3f800002


def test_perturbed_table_coefficient_rejected_against_independent_r1():
    table = json.loads(proof.TABLE.read_text())
    table["nodes"][0]["silu_f32_bits"] = "0x3f800000"
    with pytest.raises(proof.ProofError, match="correctly rounded"):
        proof.certify_table(table)


def test_table_population_and_grid_mutations_rejected():
    table = json.loads(proof.TABLE.read_text())
    table["nodes"].pop()
    with pytest.raises(proof.ProofError, match="833-node"):
        proof.certify_table(table)
    table = json.loads(proof.TABLE.read_text())
    table["nodes"][0]["x_num"] += 1
    with pytest.raises(proof.ProofError, match="grid/index"):
        proof.certify_table(table)


def test_proof_checker_and_guard_are_package_privacy_inputs():
    assert driver.PROOF_CHECK in driver.PUBLIC_FILES
    assert driver.GUARD in driver.PUBLIC_FILES
    assert driver.KERNEL in driver.PUBLIC_FILES
    assert driver.B_PROOF in driver.PUBLIC_FILES
    assert driver.B_CONTRACT in driver.PUBLIC_FILES
    assert driver.DOWN_CONTRACT in driver.PUBLIC_FILES


def test_r1_wide_scalar_enclosure_rejected():
    interval = SimpleNamespace(lo=Fraction(-1), hi=Fraction(1),
                               width=Fraction(2))
    reference = SimpleNamespace(evaluate=lambda gate, up: interval)
    with pytest.raises(SystemExit, match="frozen width"):
        driver.r1_check(reference, 0.0, 1.0, "0x00000000", "0x00000000")
