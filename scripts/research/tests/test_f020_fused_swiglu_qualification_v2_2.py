"""Fail-closed checks for the prospective F020 v2.3 qualification driver."""

import importlib.util
import math
import struct
from pathlib import Path
from types import SimpleNamespace

import pytest

DRIVER_PATH = Path(__file__).resolve().parents[1] / "f020_fused_swiglu_qualification_v2_2.py"
SPEC = importlib.util.spec_from_file_location("f020_v2_2_driver", DRIVER_PATH)
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
    return {"schema": "pulsarmlx.f020.native-bridge-v2-2-structured/1.0.0",
            "structured": True, "total_evaluated": 42, "anomaly_count": 0,
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
