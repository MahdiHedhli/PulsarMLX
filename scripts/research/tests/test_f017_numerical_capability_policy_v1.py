from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
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


def test_qualification_bytes_are_cwd_independent() -> None:
    qualifier = RESEARCH / "qualify_f017_numerical_capability_policy_v1.py"
    with tempfile.TemporaryDirectory(prefix="f017-capability-cwd-") as directory:
        scratch = Path(directory)
        first = scratch / "first.json"
        second = scratch / "second.json"
        subprocess.run([sys.executable, str(qualifier), "--output", str(first)], cwd=ROOT, check=True)
        subprocess.run([sys.executable, str(qualifier), "--output", str(second)], cwd=scratch, check=True)
        assert first.read_bytes() == second.read_bytes()
        text = first.read_text()
        assert str(ROOT) not in text


@pytest.mark.parametrize("probe", [
    "import numpy.lib\ndef probe(): return numpy.memmap('x')",
    "import numpy.ctypeslib as backend\ndef probe(): return backend.load_library('x', '.')",
    "import mlx.core.fast as backend",
])
def test_capability_submodule_identity_is_semantic(probe: str) -> None:
    analyzer = load(f"f017_capability_submodule_{abs(hash(probe))}", RESEARCH / "f017_numerical_capability_analysis_v1.py")
    checker = load(f"f017_capability_submodule_checker_{abs(hash(probe))}", RESEARCH / "check_f017_numerical_capabilities_independent_v1.py")
    policy = json.loads(POLICY.read_text())
    baseline = (RESEARCH / "f017_corrected_oracle_secondary_numerics_v2.py").read_text()
    with pytest.raises(analyzer.CapabilityViolation):
        analyzer.CapabilityAnalyzer(policy, role="secondary", path="probe.py").analyze(baseline + "\n" + probe)
    with tempfile.TemporaryDirectory(prefix="f017-capability-submodule-") as directory:
        path = Path(directory) / "probe.py"
        path.write_text(baseline + "\n" + probe)
        with pytest.raises(ValueError):
            checker.check(path, policy)


@pytest.mark.parametrize("probe", [
    "_scratch=np.zeros(4)\ndef probe(_scratch): return _scratch.tobytes()",
    "class Probe:\n    tensors=np.zeros(2)\n    def method(self, tensors): return tensors.tobytes()",
])
def test_parameter_shadowing_never_inherits_receiver_provenance(probe: str) -> None:
    analyzer = load(f"f017_capability_shadow_{abs(hash(probe))}", RESEARCH / "f017_numerical_capability_analysis_v1.py")
    policy = json.loads(POLICY.read_text())
    baseline = (RESEARCH / "f017_corrected_oracle_secondary_numerics_v2.py").read_text()
    with pytest.raises(analyzer.CapabilityViolation, match="UNAPPROVED_RECEIVER_METHOD"):
        analyzer.CapabilityAnalyzer(policy, role="secondary", path="probe.py").analyze(baseline + "\n" + probe)


@pytest.mark.parametrize("probe", [
    "import mlx\n_f = mlx.core.savez\ndef probe(a): return _f('out.npz', a)",
    "import mlx\n_m = mlx.core\ndef probe(): return _m.import_function",
    "import mlx as package\ndef probe(): return package.core.savez",
    "from . import numpy",
    "from .. import mlx",
])
def test_capability_ancestor_and_relative_imports_fail_closed(probe: str) -> None:
    analyzer = load(f"f017_capability_ancestor_{abs(hash(probe))}", RESEARCH / "f017_numerical_capability_analysis_v1.py")
    checker = load(f"f017_capability_ancestor_checker_{abs(hash(probe))}", RESEARCH / "check_f017_numerical_capabilities_independent_v1.py")
    policy = json.loads(POLICY.read_text())
    baseline = (RESEARCH / "f017_corrected_oracle_secondary_numerics_v2.py").read_text()
    source = baseline + "\n" + probe
    with pytest.raises(analyzer.CapabilityViolation):
        analyzer.CapabilityAnalyzer(policy, role="secondary", path="probe.py").analyze(source)
    with tempfile.TemporaryDirectory(prefix="f017-capability-ancestor-") as directory:
        path = Path(directory) / "probe.py"
        path.write_text(source)
        with pytest.raises(ValueError):
            checker.check(path, policy)
