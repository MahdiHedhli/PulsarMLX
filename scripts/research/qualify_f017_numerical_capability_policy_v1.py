#!/usr/bin/env python3
"""Adversarial qualification of the F017 numerical capability policy."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RESEARCH = ROOT / "scripts/research"
CONTRACTS = ROOT / "specs/017-rust-native-inference-runtime/contracts"
POLICY = CONTRACTS / "f017-corrected-oracle-numerical-capability-policy-v1.json"
PRIMARY = RESEARCH / "f017_corrected_oracle_primary_numerics_v2.py"
SECONDARY = RESEARCH / "f017_corrected_oracle_secondary_numerics_v2.py"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def mutation_cases() -> list[dict]:
    cases: list[dict] = []

    expected_by_category = {
        "F5_R4": ["CAPABILITY_ASSIGNMENT_ESCAPE"],
        "MODULE_ESCAPE": ["CAPABILITY_ASSIGNMENT_ESCAPE", "CAPABILITY_ANNOTATED_ASSIGNMENT_ESCAPE", "CAPABILITY_NAMED_EXPRESSION_ESCAPE", "CAPABILITY_RETURN_ESCAPE", "CAPABILITY_DEFAULT_CAPTURE", "MODULE_CAPABILITY_ESCAPE"],
        "MEMBER_ESCAPE": ["CAPABILITY_ASSIGNMENT_ESCAPE", "CAPABILITY_ANNOTATED_ASSIGNMENT_ESCAPE", "CAPABILITY_NAMED_EXPRESSION_ESCAPE", "CAPABILITY_RETURN_ESCAPE", "CAPABILITY_DEFAULT_CAPTURE", "CAPABILITY_ARGUMENT_ESCAPE"],
        "DYNAMIC_ACCESS": ["DYNAMIC_CAPABILITY_SURFACE", "META_CAPABILITY_SURFACE", "CAPABILITY_ARGUMENT_ESCAPE", "CAPABILITY_RETURN_ESCAPE", "CAPABILITY_ATTRIBUTE_CHAIN"],
        "UNKNOWN_RECEIVER": ["UNAPPROVED_RECEIVER_METHOD", "DYNAMIC_CAPABILITY_SURFACE", "META_CAPABILITY_SURFACE"],
        "CONTAINER_RECEIVER": ["UNAPPROVED_RECEIVER_METHOD", "DYNAMIC_CAPABILITY_SURFACE"],
        "IMPORT_REPRESENTATION": ["CAPABILITY_IMPORT_CENSUS", "CAPABILITY_IMPORT_FROM_PROHIBITED", "CAPABILITY_STAR_IMPORT_PROHIBITED", "CAPABILITY_RETURN_ESCAPE"],
        "SUBMODULE_IDENTITY": ["CAPABILITY_IMPORT_CENSUS", "CAPABILITY_IMPORT_FROM_PROHIBITED"],
        "RECEIVER_SHADOWING": ["UNAPPROVED_RECEIVER_METHOD"],
        "DECLARED_BINDING_FORM": ["CAPABILITY_DECORATOR_ESCAPE", "CAPABILITY_AUGMENTED_ASSIGNMENT_ESCAPE", "UNAPPROVED_RECEIVER_METHOD"],
    }

    def add(category: str, source: str) -> None:
        cases.append({
            "id": f"CAP-{len(cases) + 1:03d}",
            "category": category,
            "source": source,
            "expected_rejection_classes": expected_by_category[category],
        })

    add("F5_R4", "_backend = np\ndef probe():\n    return _backend.memmap('x')")

    module_templates = [
        "_alias = {v}", "_a = _alias = {v}", "_alias: object = {v}", "(_alias := {v})",
        "_alias, _x = {v}, 1", "[_alias] = [{v}]", "*_alias, = [{v}]",
        "class Probe:\n    backend = {v}", "_box = [{v}]", "_box = ({v},)",
        "_box = {{{v}}}", "_box = {{'backend': {v}}}",
        "def probe(value={v}):\n    return value", "def probe(*, value={v}):\n    return value",
        "def probe():\n    return {v}", "def probe():\n    yield {v}",
        "def probe():\n    return lambda: {v}",
        "def outer():\n    value = {v}\n    def inner():\n        return value\n    return inner",
        "def probe():\n    return [{v} for _ in range(1)]",
        "def probe():\n    return {v} if True else None",
    ]
    for semantic in ("np", "mx"):
        for template in module_templates:
            add("MODULE_ESCAPE", template.format(v=semantic))

    member_templates = [
        "_alias = {v}", "_a = _alias = {v}", "_alias: object = {v}", "(_alias := {v})",
        "_alias, _x = {v}, 1", "_box = [{v}]", "_box = ({v},)", "_box = {{'member': {v}}}",
        "def probe(value={v}):\n    return value", "def probe(*, value={v}):\n    return value",
        "def probe():\n    return {v}", "def probe():\n    yield {v}",
        "def probe():\n    return lambda: {v}",
        "def outer():\n    value = {v}\n    def inner():\n        return value\n    return inner",
        "def sink(value):\n    return value\ndef probe():\n    return sink({v})",
    ]
    for member in ("np.asarray", "np.float32", "np.memmap", "mx.array"):
        for template in member_templates:
            add("MEMBER_ESCAPE", template.format(v=member))

    dynamic = [
        "getattr(np, 'memmap')", "np.__dict__['memmap']", "np.__getattribute__('memmap')",
        "type(np).__getattribute__(np, 'memmap')", "getattr(np, 'mem' + 'map')",
        "__import__('numpy').memmap", "globals()['np'].memmap", "locals()['np'].memmap",
        "vars(np)['memmap']", "hasattr(np, 'memmap')", "setattr(np, 'x', 1)",
        "np.lib.format.open_memmap", "np.core", "np.__class__", "mx.__dict__",
        "getattr(mx, 'array')", "__import__('mlx.core').array", "globals().get('mx')",
        "vars(mx)", "np.__loader__",
    ]
    for expression in dynamic:
        add("DYNAMIC_ACCESS", f"def probe():\n    return {expression}")

    receiver_methods = [
        "open", "read", "write", "pread", "mmap", "load", "save", "memmap", "fromfile", "tofile",
        "__getattribute__", "__reduce__", "__reduce_ex__", "exec_module", "load_module",
        "matrix", "vector", "expert", "row", "astype", "reshape", "copy", "tobytes", "append",
        "extend", "get", "all", "hexdigest", "update",
    ]
    for method in receiver_methods:
        add("UNKNOWN_RECEIVER", f"def probe(injected):\n    alias = injected\n    return alias.{method}()")
    for method in ("open", "memmap", "matrix", "row", "astype", "copy", "get", "update", "load", "save"):
        add("CONTAINER_RECEIVER", f"def probe(injected):\n    box = [injected]\n    return box[0].{method}()")
    for source in (
        "import numpy", "import numpy as backend", "from numpy import asarray", "from numpy import *",
        "import mlx.core", "import mlx.core as backend", "from mlx.core import array", "from mlx.core import *",
        "def probe():\n    import numpy as inner\n    return inner.memmap('x')",
        "class Probe:\n    import numpy as inner\n    value = inner.memmap('x')",
    ):
        add("IMPORT_REPRESENTATION", source)
    for source in (
        "import numpy.lib\ndef probe():\n    return numpy.memmap('x')",
        "import numpy.ctypeslib as _n\ndef probe():\n    return _n.load_library('x', '.')",
        "from numpy.lib import format as _format",
        "import mlx.core.fast as _fast",
    ):
        add("SUBMODULE_IDENTITY", source)
    for source in (
        "_scratch = np.zeros(4)\ndef probe(_scratch):\n    return _scratch.tobytes()",
        "class Probe:\n    tensors = np.zeros(2)\n    def method(self, tensors):\n        return tensors.tobytes()",
        "_scratch = np.zeros(4)\ndef probe(value):\n    alias = value\n    return alias.tobytes()",
    ):
        add("RECEIVER_SHADOWING", source)
    for source in (
        "@np.asarray\ndef probe():\n    return None",
        "value = np.zeros(1)\nvalue += np",
        "value = np.zeros(1)\ntry:\n    raise ValueError()\nexcept Exception as value:\n    value.tobytes()",
        "value = np.zeros(1)\nmatch object():\n    case value:\n        value.tobytes()",
    ):
        add("DECLARED_BINDING_FORM", source)
    if len(cases) < 120:
        raise AssertionError("mutation census")
    if len({case["source"] for case in cases}) != len(cases):
        raise AssertionError("duplicate/no-op mutation")
    return cases


class ModuleProxy(types.ModuleType):
    def __init__(self, name: str, target, allowed: set[str], observed: set[str]):
        super().__init__(name)
        self._target = target
        self._allowed = allowed
        self._observed = observed

    def __getattr__(self, name: str):
        if name not in self._allowed:
            raise RuntimeError(f"runtime capability outside policy: {name}")
        self._observed.add(name)
        return getattr(self._target, name)


def runtime_proxy_qualification(policy: dict, work: Path) -> dict:
    fixtures = work / "fixtures"
    subprocess.run([sys.executable, str(RESEARCH / "generate_f017_corrected_oracle_fixtures.py"), str(fixtures)], check=True)
    fixture = json.loads((fixtures / "fixture-18106.json").read_text())
    secondary = load("f017_secondary_capability_proxy", SECONDARY)
    observed_numpy: set[str] = set()
    numpy_allowed = set(policy["semantic_modules"]["PYTHON_MODULE_NUMPY"]["direct_callable_members"]) | set(
        policy["semantic_modules"]["PYTHON_MODULE_NUMPY"]["type_dtype_members"]
    )
    secondary.np = ModuleProxy("numpy-capability-proxy", secondary.np, numpy_allowed, observed_numpy)
    result = secondary.execute(fixture, use_mlx=False)
    if result["layer_count"] != fixture["geometry"]["layers"]:
        raise ValueError("runtime proxy incomplete graph")
    observed_mlx: set[str] = set()
    mlx_allowed = set(policy["semantic_modules"]["PYTHON_MODULE_MLX_CORE"]["direct_callable_members"])
    # Exercise the pure core's real ``import mlx.core`` and member-use surface
    # without loading the platform MLX extension.  CI also links pinned native
    # MLX libraries for Rust/C qualification; those libraries need not be ABI
    # compatible with the separately locked Python wheel.  A tiny semantic
    # target keeps this control a capability census (not an MLX correctness
    # test) and makes it deterministic on every qualification host.
    fake_mx = types.SimpleNamespace(
        array=lambda value: secondary.np.asarray(value),
        eval=lambda value: None,
        transpose=lambda value: secondary.np.asarray(value).T,
    )
    mlx_proxy = ModuleProxy("mlx.core", fake_mx, mlx_allowed, observed_mlx)
    mlx_package = types.ModuleType("mlx")
    mlx_package.__path__ = []
    mlx_package.core = mlx_proxy
    previous_package = sys.modules.get("mlx")
    previous_module = sys.modules.get("mlx.core")
    try:
        sys.modules["mlx"] = mlx_package
        sys.modules["mlx.core"] = mlx_proxy
        vector = secondary.np.asarray([1.0, -2.0], dtype=secondary.np.float32)
        matrix = secondary.np.asarray([[1.0, 0.5], [-0.25, 2.0]], dtype=secondary.np.float32)
        secondary.mv(matrix, vector, use_mlx=True)
        secondary.transpose_mv(matrix, vector, use_mlx=True)
    finally:
        if previous_module is not None:
            sys.modules["mlx.core"] = previous_module
        else:
            sys.modules.pop("mlx.core", None)
        if previous_package is not None:
            sys.modules["mlx"] = previous_package
        else:
            sys.modules.pop("mlx", None)
    numpy_subset = observed_numpy <= numpy_allowed
    mlx_subset = observed_mlx <= mlx_allowed
    if not numpy_subset:
        raise ValueError(f"runtime NumPy capability outside contract: {sorted(observed_numpy - numpy_allowed)}")
    if not mlx_subset:
        raise ValueError(f"runtime MLX capability outside contract: {sorted(observed_mlx - mlx_allowed)}")
    if observed_mlx != mlx_allowed:
        raise ValueError(f"runtime MLX capability census: {sorted(observed_mlx)}")
    return {
        "result": "PASS",
        "numpy_members_observed": sorted(observed_numpy),
        "mlx_members_observed": sorted(observed_mlx),
        "numpy_subset_of_contract": numpy_subset,
        "mlx_subset_of_contract": mlx_subset,
        "subset_of_contract": numpy_subset and mlx_subset,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    analyzer = load("f017_capability_analysis_qualification", RESEARCH / "f017_numerical_capability_analysis_v1.py")
    checker = load("f017_capability_checker_qualification", RESEARCH / "check_f017_numerical_capabilities_independent_v1.py")
    policy = json.loads(POLICY.read_text())
    source_paths = {
        "primary": PRIMARY.relative_to(ROOT),
        "secondary": SECONDARY.relative_to(ROOT),
    }
    accepted = {
        role: analyzer.CapabilityAnalyzer(policy, role=role, path=relative.as_posix())
        .analyze((ROOT / relative).read_text())
        .as_json()
        for role, relative in source_paths.items()
    }
    independent = {}
    for role, relative in source_paths.items():
        report = checker.check(ROOT / relative, policy)
        report["path"] = relative.as_posix()
        independent[role] = report
    cases = mutation_cases()
    baseline = SECONDARY.read_text()
    observed = []
    for case in cases:
        try:
            analyzer.CapabilityAnalyzer(policy, role="secondary", path=f"mutation:{case['id']}").analyze(baseline + "\n" + case["source"] + "\n")
        except Exception as exc:
            rejection = str(exc).split(":", 1)[0]
            if rejection not in case["expected_rejection_classes"]:
                raise ValueError(
                    f"capability mutation rejected by wrong control: {case['id']} {rejection} "
                    f"not in {case['expected_rejection_classes']}"
                ) from exc
            observed.append({
                "id": case["id"],
                "category": case["category"],
                "expected_rejection_classes": case["expected_rejection_classes"],
                "result": "REJECTED",
                "rejection": rejection,
                "validator": "scripts/research/f017_numerical_capability_analysis_v1.py",
            })
        else:
            raise ValueError(f"capability mutation unexpectedly passed: {case['id']} {case['source']}")
    with tempfile.TemporaryDirectory(prefix="f017-capability-v1-") as directory:
        runtime = runtime_proxy_qualification(policy, Path(directory))
    result = {
        "schema": "pulsarmlx.f017.numerical-capability-qualification/1.0.0",
        "result": "PASS",
        "exact_f5_r4_rejected": any(item["category"] == "F5_R4" and item["result"] == "REJECTED" for item in observed),
        "mutation_count": len(cases),
        "unexpected_pass_count": 0,
        "category_census": {category: sum(item["category"] == category for item in observed) for category in sorted({item["category"] for item in observed})},
        "rejection_control_census": {
            rejection: sum(item["rejection"] == rejection for item in observed)
            for rejection in sorted({item["rejection"] for item in observed})
        },
        "transport_rejection_count": sum(
            item["rejection"].startswith("CAPABILITY_") and item["rejection"] != "CAPABILITY_IMPORT_CENSUS"
            for item in observed
        ),
        "mutations": observed,
        "accepted_current_sources": accepted,
        "independent_checker": independent,
        "runtime_proxy": runtime,
        "policy_sha256": sha(POLICY),
        "analyzer_sha256": sha(RESEARCH / "f017_numerical_capability_analysis_v1.py"),
        "independent_checker_sha256": sha(RESEARCH / "check_f017_numerical_capabilities_independent_v1.py"),
        "primary_pure_core_sha256": sha(PRIMARY),
        "secondary_pure_core_sha256": sha(SECONDARY),
        "original_checkpoint_shard_opens": 0,
        "original_checkpoint_payload_reads": 0,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"result": "PASS", "mutations": len(cases), "runtime_numpy_members": runtime["numpy_members_observed"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
