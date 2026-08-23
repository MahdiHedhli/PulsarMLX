from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
RESEARCH = ROOT / "scripts/research"
POLICY = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-numerical-capability-policy-v1.json"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_committed_pure_cores_pass_semantic_analysis() -> None:
    analyzer = load("f017_capability_test_analyzer", RESEARCH / "f017_numerical_capability_analysis_v1.py")
    for role in ("primary", "secondary"):
        path = RESEARCH / f"f017_corrected_oracle_{role}_numerics_v2.py"
        assert analyzer.analyze_path(path, POLICY, role).path == str(path)


@pytest.mark.parametrize("probe", [
    "_backend = np\ndef probe(): return _backend.memmap('x')",
    "_backend = np\n_other = _backend\ndef probe(): return _other.asarray([])",
    "_box = [np]\ndef probe(): return _box[0].memmap('x')",
    "def probe(_backend=np): return _backend.asarray([])",
    "_convert = np.asarray\ndef probe(x): return _convert(x)",
    "def probe(obj):\n    alias = obj\n    return alias.memmap('x')",
])
def test_representation_independent_escapes_fail(probe: str) -> None:
    analyzer = load(f"f017_capability_probe_{abs(hash(probe))}", RESEARCH / "f017_numerical_capability_analysis_v1.py")
    policy = json.loads(POLICY.read_text())
    baseline = (RESEARCH / "f017_corrected_oracle_secondary_numerics_v2.py").read_text()
    with pytest.raises(analyzer.CapabilityViolation):
        analyzer.CapabilityAnalyzer(policy, role="secondary", path="probe.py").analyze(baseline + "\n" + probe + "\n")


def test_independent_checker_does_not_import_primary_analyzer() -> None:
    text = (RESEARCH / "check_f017_numerical_capabilities_independent_v1.py").read_text()
    assert "f017_numerical_capability_analysis_v1" not in text


def test_mutation_census_is_substantive() -> None:
    qualifier = load("f017_capability_mutation_census", RESEARCH / "qualify_f017_numerical_capability_policy_v1.py")
    cases = qualifier.mutation_cases()
    assert len(cases) >= 120
    assert len({case["source"] for case in cases}) == len(cases)
