"""Independent fixed-contract qualification for Flash linear-attention mutants."""
import ast
import copy
import difflib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import sysconfig
import time
import traceback
import unittest


SOURCE = Path(__file__).resolve().parents[3]
ORACLE = SOURCE / "scripts/research/glm53_flash/linear_attention/oracle.py"
RECURRENT = SOURCE / "scripts/research/glm53_flash/recurrent_dispatch/oracle.py"
FIXTURE = SOURCE / "fixtures/research/glm53-flash-linear-attention-v1/fixtures.json"
EVIDENCE = SOURCE.parent / "evidence"
TEMP = SOURCE.parent / "temp"
RESULT_MARKER = "PULSAR_FIXED_CONTRACT_RESULT="
STREAM_CAP = 1024 * 1024

ALLOWED_TOKENS = (
    "ORACLE_INITIAL_LENGTHS_MISSING",
    "ORACLE_INITIAL_LENGTHS_TYPE",
    "ORACLE_INITIAL_LENGTHS_SHAPE",
    "ORACLE_INITIAL_LENGTHS_RANGE",
    "ORACLE_INITIAL_PADDING_MISSING",
    "ORACLE_INITIAL_PADDING_TYPE",
    "ORACLE_INITIAL_PADDING_SHAPE",
    "ORACLE_INITIAL_PADDING_RANGE",
    "ORACLE_RECURRENCE_CROSSCHECK_OUTPUT",
    "ORACLE_RECURRENCE_CROSSCHECK_STATE",
)

METADATA_BLUEPRINTS = (
    ("initial_lengths", "MISSING", "DOMAIN", "ORACLE_INITIAL_LENGTHS_MISSING", "LENGTH_MISSING_GUARANTEE"),
    ("initial_lengths", "NULL", "DOMAIN", "ORACLE_INITIAL_LENGTHS_TYPE", "LENGTH_TYPE_GUARANTEE"),
    ("initial_lengths", "TUPLE", "DOMAIN", "ORACLE_INITIAL_LENGTHS_TYPE", "LENGTH_TYPE_GUARANTEE"),
    ("initial_lengths", "SCALAR_ZERO", "DOMAIN", "ORACLE_INITIAL_LENGTHS_TYPE", "LENGTH_TYPE_GUARANTEE"),
    ("initial_lengths", "EMPTY_LIST", "DOMAIN", "ORACLE_INITIAL_LENGTHS_SHAPE", "LENGTH_SHAPE_GUARANTEE"),
    ("initial_lengths", "SHORT_LIST", "DOMAIN", "ORACLE_INITIAL_LENGTHS_SHAPE", "LENGTH_SHAPE_GUARANTEE"),
    ("initial_lengths", "LONG_LIST", "DOMAIN", "ORACLE_INITIAL_LENGTHS_SHAPE", "LENGTH_SHAPE_GUARANTEE"),
    ("initial_lengths", "BOOL_TRUE", "DOMAIN", "ORACLE_INITIAL_LENGTHS_TYPE", "LENGTH_TYPE_GUARANTEE"),
    ("initial_lengths", "BOOL_FALSE", "DOMAIN", "ORACLE_INITIAL_LENGTHS_TYPE", "LENGTH_TYPE_GUARANTEE"),
    ("initial_lengths", "FRACTIONAL", "DOMAIN", "ORACLE_INITIAL_LENGTHS_TYPE", "LENGTH_TYPE_GUARANTEE"),
    ("initial_lengths", "POSITIVE_INFINITY", "DOMAIN", "ORACLE_INITIAL_LENGTHS_TYPE", "LENGTH_TYPE_GUARANTEE"),
    ("initial_lengths", "NAN", "DOMAIN", "ORACLE_INITIAL_LENGTHS_TYPE", "LENGTH_TYPE_GUARANTEE"),
    ("initial_lengths", "S_MINUS_1", "DOMAIN", "ORACLE_INITIAL_LENGTHS_RANGE", "LENGTH_RANGE_GUARANTEE"),
    ("initial_lengths", "S", "CLEAN", None, "LENGTH_VALID_S_GUARANTEE"),
    ("initial_lengths", "S_PLUS_1", "CLEAN", None, "LENGTH_VALID_ABOVE_S_GUARANTEE"),
    ("initial_padding", "MISSING", "DOMAIN", "ORACLE_INITIAL_PADDING_MISSING", "PADDING_MISSING_GUARANTEE"),
    ("initial_padding", "NULL", "DOMAIN", "ORACLE_INITIAL_PADDING_TYPE", "PADDING_TYPE_GUARANTEE"),
    ("initial_padding", "TUPLE", "DOMAIN", "ORACLE_INITIAL_PADDING_TYPE", "PADDING_TYPE_GUARANTEE"),
    ("initial_padding", "SCALAR_ZERO", "DOMAIN", "ORACLE_INITIAL_PADDING_TYPE", "PADDING_TYPE_GUARANTEE"),
    ("initial_padding", "EMPTY_LIST", "DOMAIN", "ORACLE_INITIAL_PADDING_SHAPE", "PADDING_SHAPE_GUARANTEE"),
    ("initial_padding", "SHORT_LIST", "DOMAIN", "ORACLE_INITIAL_PADDING_SHAPE", "PADDING_SHAPE_GUARANTEE"),
    ("initial_padding", "LONG_LIST", "DOMAIN", "ORACLE_INITIAL_PADDING_SHAPE", "PADDING_SHAPE_GUARANTEE"),
    ("initial_padding", "BOOL_TRUE", "DOMAIN", "ORACLE_INITIAL_PADDING_TYPE", "PADDING_TYPE_GUARANTEE"),
    ("initial_padding", "BOOL_FALSE", "DOMAIN", "ORACLE_INITIAL_PADDING_TYPE", "PADDING_TYPE_GUARANTEE"),
    ("initial_padding", "FRACTIONAL", "DOMAIN", "ORACLE_INITIAL_PADDING_TYPE", "PADDING_TYPE_GUARANTEE"),
    ("initial_padding", "POSITIVE_INFINITY", "DOMAIN", "ORACLE_INITIAL_PADDING_TYPE", "PADDING_TYPE_GUARANTEE"),
    ("initial_padding", "NAN", "DOMAIN", "ORACLE_INITIAL_PADDING_TYPE", "PADDING_TYPE_GUARANTEE"),
    ("initial_padding", "NEGATIVE_1", "DOMAIN", "ORACLE_INITIAL_PADDING_RANGE", "PADDING_RANGE_GUARANTEE"),
    ("initial_padding", "ZERO", "CLEAN", None, "PADDING_VALID_ZERO_GUARANTEE"),
    ("initial_padding", "S_MINUS_1", "CLEAN", None, "PADDING_VALID_BELOW_S_GUARANTEE"),
    ("initial_padding", "S", "CLEAN", None, "PADDING_VALID_S_GUARANTEE"),
    ("initial_padding", "S_PLUS_1", "CLEAN", None, "PADDING_VALID_ABOVE_S_GUARANTEE"),
)

CROSSCHECK_BLUEPRINTS = (
    ("both_true", True, True, "CLEAN", None, ("OUTPUT", "STATE"), "BOTH_TRUE_VISIT_GUARANTEE"),
    ("output_false", False, True, "DOMAIN", "ORACLE_RECURRENCE_CROSSCHECK_OUTPUT", ("OUTPUT",), "OUTPUT_CROSSCHECK_GUARANTEE"),
    ("state_false", True, False, "DOMAIN", "ORACLE_RECURRENCE_CROSSCHECK_STATE", ("OUTPUT", "STATE"), "STATE_CROSSCHECK_GUARANTEE"),
)

MUTANTS = {
    "range": ("value < minimum", "False", "LENGTH_RANGE_GUARANTEE"),
    "bool": ("type(value) is not int", "not isinstance(value, int)", "LENGTH_TYPE_GUARANTEE"),
    "wrong-field": (
        "('initial_lengths', S, 'ORACLE_INITIAL_LENGTHS')",
        "('initial_padding', S, 'ORACLE_INITIAL_LENGTHS')",
        "LENGTH_MISSING_GUARANTEE",
    ),
    "padding-bound": (
        "('initial_padding', 0, 'ORACLE_INITIAL_PADDING')",
        "('initial_padding', S, 'ORACLE_INITIAL_PADDING')",
        "PADDING_VALID_BELOW_S_GUARANTEE",
    ),
    "drop-output": (
        "if not close(mapping(recur_y, lambda x:x.v), accepted_y, 1e-14, 1e-13):",
        "if False and not close(mapping(recur_y, lambda x:x.v), accepted_y, 1e-14, 1e-13):",
        "OUTPUT_CROSSCHECK_GUARANTEE",
    ),
    "drop-state": (
        "if not close(mapping(state, lambda x:x.v), accepted_state, 1e-14, 1e-13):",
        "if False and not close(mapping(state, lambda x:x.v), accepted_state, 1e-14, 1e-13):",
        "STATE_CROSSCHECK_GUARANTEE",
    ),
}

PROTECTED = (
    "fixtures/research/glm53-flash-linear-attention-v1/fixtures.json",
    "scripts/research/glm53_flash/linear_attention/capsule.py",
    "scripts/research/glm53_flash/linear_attention/controls.py",
    "scripts/research/glm53_flash/linear_attention/edges.json",
    "scripts/research/glm53_flash/linear_attention/oracle.py",
    "scripts/research/glm53_flash/linear_attention/provenance.json",
    "scripts/research/glm53_flash/linear_attention/source.py",
    "scripts/research/glm53_flash/recurrent_dispatch/capsule.py",
    "scripts/research/glm53_flash/recurrent_dispatch/controls.py",
    "scripts/research/glm53_flash/recurrent_dispatch/oracle.py",
    "scripts/research/glm53_flash/recurrent_dispatch/provenance.json",
    "scripts/research/glm53_flash/recurrent_dispatch/source.py",
    "scripts/research/glm53_flash/recurrent_dispatch/upstream-gated-delta.txt",
    "scripts/research/glm53_flash/recurrent_dispatch/upstream-language.txt",
)


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def build_contract(fixture):
    metadata = []
    for base_index in (1, 4):
        base = fixture["cases"][base_index]
        B, S = base["B"], base["S"]
        dims = [B, S, base["config"]["hidden_size"], base["config"]["linear_num_heads"], 32,
                base["config"]["linear_conv_kernel_dim"]]
        for field, value_spec, kind, token, guarantee in METADATA_BLUEPRINTS:
            expected = {"classification": "SEMANTIC", "kind": kind}
            if kind == "DOMAIN":
                expected["token"] = token
            else:
                expected["value"] = dims
            metadata.append({
                "id": f"b{B}-s{S}-{field}-{value_spec.lower()}",
                "base_index": base_index,
                "field": field,
                "value_spec": value_spec,
                "expected": expected,
                "guarantee": guarantee,
            })
    crosschecks = []
    sentinel = "PASS; unchanged Dv8 interface, four independent value-row blocks"
    for name, output_ok, state_ok, kind, token, visits, guarantee in CROSSCHECK_BLUEPRINTS:
        expected = {"classification": "SEMANTIC", "kind": kind}
        if kind == "DOMAIN":
            expected["token"] = token
        else:
            expected.update(return_type="dict", accepted_crosscheck=sentinel)
        crosschecks.append({
            "id": name,
            "output_ok": output_ok,
            "state_ok": state_ok,
            "expected": expected,
            "expected_visits": list(visits),
            "guarantee": guarantee,
        })
    return {
        "schema": "glm53-flash-fixed-contract-v2",
        "allowed_tokens": list(ALLOWED_TOKENS),
        "metadata": metadata,
        "crosschecks": crosschecks,
    }


def materialize(spec, field, B, S):
    valid = S if field == "initial_lengths" else 0
    values = {
        "NULL": None,
        "TUPLE": tuple([valid] * B),
        "SCALAR_ZERO": 0,
        "EMPTY_LIST": [],
        "SHORT_LIST": [valid] * max(B - 1, 0),
        "LONG_LIST": [valid] * (B + 1),
        "BOOL_TRUE": [True] * B,
        "BOOL_FALSE": [False] * B,
        "FRACTIONAL": [0.5] * B,
        "POSITIVE_INFINITY": [float("inf")] * B,
        "NAN": [float("nan")] * B,
        "S_MINUS_1": [S - 1] * B,
        "NEGATIVE_1": [-1] * B,
        "ZERO": [0] * B,
        "S": [S] * B,
        "S_PLUS_1": [S + 1] * B,
    }
    return values[spec]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError("SPEC_OR_LOADER_UNAVAILABLE")
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    try:
        spec.loader.exec_module(value)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return value


def exception_record(exc):
    return {
        "classification": "INFRA",
        "kind": "SUBJECT_EXCEPTION",
        "exception_type": type(exc).__name__,
        "message": str(exc),
        "frames": [
            {"file": frame.filename, "line": frame.lineno, "name": frame.name}
            for frame in traceback.extract_tb(exc.__traceback__)
        ],
    }


def capture_validate(oracle, case):
    try:
        result = oracle.validate(case)
    except oracle.InputError as exc:
        token = str(exc)
        if token in ALLOWED_TOKENS:
            return {"classification": "SEMANTIC", "kind": "DOMAIN", "token": token}
        return exception_record(exc)
    except BaseException as exc:
        return exception_record(exc)
    if type(result) is tuple and len(result) == 6 and all(type(value) is int for value in result):
        return {"classification": "SEMANTIC", "kind": "CLEAN", "value": list(result)}
    return {"classification": "INFRA", "kind": "UNPERMITTED_VALIDATE_RETURN", "return_type": type(result).__name__}


class UnknownSignature(RuntimeError):
    pass


def capture_crosscheck(oracle, recurrent, case, output_ok, state_ok):
    visits = []
    original = oracle.close

    def controlled(actual, expected, atol=None, rtol=None):
        actual_shape = oracle.shape(actual)
        expected_shape = oracle.shape(expected)
        if actual_shape == (1, 1, 32) and expected_shape == (1, 1, 32):
            label, result = "OUTPUT", output_ok
        elif actual_shape == (1, 1, 32, 32) and expected_shape == (1, 1, 32, 32):
            label, result = "STATE", state_ok
        else:
            raise UnknownSignature(repr((actual_shape, expected_shape)))
        visits.append({
            "call_index": len(visits) + 1,
            "label": label,
            "actual_shape": list(actual_shape),
            "expected_shape": list(expected_shape),
        })
        return result

    oracle.close = controlled
    try:
        try:
            result = oracle.module_reference(case, recurrent)
        except oracle.InputError as exc:
            token = str(exc)
            outcome = ({"classification": "SEMANTIC", "kind": "DOMAIN", "token": token}
                       if token in ALLOWED_TOKENS else exception_record(exc))
        except BaseException as exc:
            outcome = exception_record(exc)
        else:
            if type(result) is dict:
                outcome = {
                    "classification": "SEMANTIC",
                    "kind": "CLEAN",
                    "return_type": "dict",
                    "accepted_crosscheck": result.get("accepted_recurrence_block_crosscheck"),
                }
            else:
                outcome = {
                    "classification": "INFRA",
                    "kind": "UNPERMITTED_MODULE_RETURN",
                    "return_type": type(result).__name__,
                }
    finally:
        oracle.close = original
    return outcome, visits


def module_inventory(baseline, allowed_files):
    stdlib = Path(sysconfig.get_path("stdlib")).resolve()
    entries, invalid = [], []
    for name in sorted(set(sys.modules) - baseline):
        module = sys.modules.get(name)
        spec = getattr(module, "__spec__", None)
        origin = getattr(spec, "origin", None) or getattr(module, "__file__", None)
        row = {"name": name, "origin": origin}
        permitted = False
        if origin in ("built-in", "frozen"):
            permitted = True
        elif type(origin) is str:
            path = Path(origin).resolve()
            row["resolved_origin"] = str(path)
            permitted = path in allowed_files or (
                path.is_relative_to(stdlib)
                and "site-packages" not in path.parts
                and "dist-packages" not in path.parts
            )
        row["permitted"] = permitted
        entries.append(row)
        if not permitted:
            invalid.append(row)
    forbidden = sorted(name for name in sys.modules
                       if name == "numpy" or name.startswith("numpy.")
                       or name == "mlx" or name.startswith("mlx.")
                       or "openblas" in name.lower())
    return {"entries": entries, "invalid": invalid, "forbidden_modules": forbidden}


def assertion_record(testcase, guarantee, facet, actual, expected):
    try:
        testcase.assertEqual(actual, expected, guarantee)
    except AssertionError as exc:
        return {"guarantee": guarantee, "facet": facet, "status": "FAIL", "detail": str(exc)}
    return {"guarantee": guarantee, "facet": facet, "status": "PASS"}


def comparable(value):
    if isinstance(value, dict):
        return {key: comparable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [comparable(item) for item in value]
    if isinstance(value, tuple):
        return {"tuple": [comparable(item) for item in value]}
    if isinstance(value, float):
        if value != value:
            return {"float": "nan"}
        if value == float("inf"):
            return {"float": "+inf"}
        if value == float("-inf"):
            return {"float": "-inf"}
    return value


def inner_contract():
    payload = {
        "schema": "glm53-flash-fixed-contract-result-v2",
        "status": "INFRA_INDETERMINATE",
        "assertions": [],
        "outcomes": [],
        "infra": [],
        "module_origins": {},
    }
    try:
        baseline = set(sys.modules)
        root = Path(os.environ["PULSAR_VARIANT_ROOT"]).resolve(strict=True)
        oracle_path = (root / "scripts/research/glm53_flash/linear_attention/oracle.py").resolve(strict=True)
        recurrent_path = (root / "scripts/research/glm53_flash/recurrent_dispatch/oracle.py").resolve(strict=True)
        oracle = load_module("pulsar_variant_oracle", oracle_path)
        recurrent = load_module("pulsar_pinned_recurrent", recurrent_path)
        allowed_files = {oracle_path, recurrent_path}
        payload["module_origins"]["after_import"] = module_inventory(baseline, allowed_files)
        fixture = json.loads(FIXTURE.read_bytes())
        contract = build_contract(fixture)
        contract_sha = sha256(encoded(contract))
        payload["contract_sha256"] = contract_sha
        payload["contract_file_sha256"] = sha256(Path(__file__).read_bytes())
        if contract_sha != os.environ["PULSAR_CONTRACT_SHA256"]:
            raise RuntimeError("FROZEN_CONTRACT_DIGEST_MISMATCH")
        testcase = unittest.TestCase()
        for row in contract["metadata"]:
            case = copy.deepcopy(fixture["cases"][row["base_index"]])
            B, S = case["B"], case["S"]
            if row["value_spec"] == "MISSING":
                del case[row["field"]]
            else:
                case[row["field"]] = materialize(row["value_spec"], row["field"], B, S)
            before = copy.deepcopy(case)
            outcome = capture_validate(oracle, case)
            payload["outcomes"].append({"id": row["id"], "outcome": outcome})
            if outcome.get("classification") == "INFRA":
                payload["infra"].append({"id": row["id"], "outcome": outcome})
                payload["assertions"].append({
                    "guarantee": row["guarantee"], "facet": "outcome", "status": "INDETERMINATE"
                })
            else:
                payload["assertions"].append(assertion_record(
                    testcase, row["guarantee"], "outcome", outcome, row["expected"]
                ))
            payload["assertions"].append(assertion_record(
                testcase, "CASE_IMMUTABILITY_GUARANTEE", row["id"], comparable(case), comparable(before)
            ))
        cross_case = fixture["cases"][0]
        for row in contract["crosschecks"]:
            outcome, visits = capture_crosscheck(
                oracle, recurrent, copy.deepcopy(cross_case), row["output_ok"], row["state_ok"]
            )
            payload["outcomes"].append({"id": row["id"], "outcome": outcome, "visits": visits})
            if outcome.get("classification") == "INFRA":
                payload["infra"].append({"id": row["id"], "outcome": outcome})
                payload["assertions"].append({
                    "guarantee": row["guarantee"], "facet": "outcome", "status": "INDETERMINATE"
                })
            else:
                payload["assertions"].append(assertion_record(
                    testcase, row["guarantee"], "outcome", outcome, row["expected"]
                ))
            payload["assertions"].append(assertion_record(
                testcase, row["guarantee"], "visits", [visit["label"] for visit in visits],
                row["expected_visits"]
            ))
        payload["module_origins"]["after_stimulus"] = module_inventory(baseline, allowed_files)
        for phase, inventory in payload["module_origins"].items():
            if inventory["invalid"] or inventory["forbidden_modules"]:
                payload["infra"].append({"id": "module_origins:" + phase, "inventory": inventory})
        if payload["infra"]:
            payload["status"] = "INFRA_INDETERMINATE"
            code = 20
        elif any(row["status"] == "FAIL" for row in payload["assertions"]):
            payload["status"] = "SEMANTIC_FAILURE"
            code = 10
        else:
            payload["status"] = "PASS"
            code = 0
    except BaseException as exc:
        payload["infra"].append({"id": "inner_harness", "outcome": exception_record(exc)})
        payload["status"] = "INFRA_INDETERMINATE"
        code = 20
    print(RESULT_MARKER + json.dumps(payload, sort_keys=True, allow_nan=False), flush=True)
    return code


def process_group_absent(pid):
    try:
        os.killpg(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    return False


def run_process(argv, seconds, env=None):
    started = time.monotonic()
    record = {
        "argv": argv,
        "timeout_seconds": seconds,
        "stream_cap_bytes": STREAM_CAP,
        "spawn_error": None,
        "stop_reason": None,
        "exit_code": None,
        "signal": None,
        "reaped": False,
        "process_group_absent": None,
        "capture_complete": True,
    }
    try:
        process = subprocess.Popen(
            argv, cwd=SOURCE, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except OSError as exc:
        record.update(spawn_error=type(exc).__name__, stop_reason="spawn_error",
                      elapsed_seconds=time.monotonic() - started)
        return record, b"", b""
    selector = selectors.DefaultSelector()
    streams = {process.stdout.fileno(): ("stdout", process.stdout),
               process.stderr.fileno(): ("stderr", process.stderr)}
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    for fd, (_, stream) in streams.items():
        os.set_blocking(fd, False)
        selector.register(stream, selectors.EVENT_READ, fd)
    deadline = started + seconds
    term_sent = None
    kill_sent = False
    while selector.get_map() or process.poll() is None:
        now = time.monotonic()
        if record["stop_reason"] is None and now >= deadline:
            record["stop_reason"] = "timeout"
        if record["stop_reason"] is not None and process.poll() is None:
            if term_sent is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                term_sent = now
            elif not kill_sent and now - term_sent >= 2:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                kill_sent = True
        for key, _ in selector.select(0.05):
            fd = key.data
            name, stream = streams[fd]
            try:
                chunk = os.read(fd, 65536)
            except BlockingIOError:
                continue
            if not chunk:
                selector.unregister(stream)
                continue
            room = STREAM_CAP - len(buffers[name])
            buffers[name].extend(chunk[:max(room, 0)])
            if len(chunk) > max(room, 0) and record["stop_reason"] is None:
                record["stop_reason"] = "capture_overflow:" + name
                record["capture_complete"] = False
        if process.poll() is not None and not selector.get_map():
            break
        if now - started > seconds + 5:
            record["stop_reason"] = record["stop_reason"] or "cleanup_timeout"
            record["capture_complete"] = False
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            break
    returncode = process.wait()
    record["reaped"] = True
    record["process_group_absent"] = process_group_absent(process.pid)
    if returncode < 0:
        record["signal"] = -returncode
    else:
        record["exit_code"] = returncode
    record["elapsed_seconds"] = time.monotonic() - started
    for name in ("stdout", "stderr"):
        raw = bytes(buffers[name])
        record[name + "_bytes"] = len(raw)
        record[name + "_sha256"] = sha256(raw)
    return record, bytes(buffers["stdout"]), bytes(buffers["stderr"])


def execute_and_store(argv, seconds, outdir, env=None):
    outdir.mkdir(parents=True)
    record, stdout, stderr = run_process(argv, seconds, env)
    (outdir / "stdout.bin").write_bytes(stdout)
    (outdir / "stderr.bin").write_bytes(stderr)
    (outdir / "capture.json").write_bytes(encoded(record))
    return record, stdout, stderr


def capture_ok(record):
    return (
        record["spawn_error"] is None
        and record["stop_reason"] is None
        and record["reaped"] is True
        and record["process_group_absent"] is True
        and record["capture_complete"] is True
        and record["signal"] is None
    )


def parse_payload(stdout):
    try:
        text = stdout.decode("utf-8")
        lines = [line for line in text.splitlines() if line.startswith(RESULT_MARKER)]
        if len(lines) != 1:
            return None
        return json.loads(lines[0][len(RESULT_MARKER):])
    except (UnicodeError, json.JSONDecodeError):
        return None


def imported_names(raw):
    tree = ast.parse(raw)
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module or "")
    return sorted(names)


def stage_variants(runroot):
    raw = ORACLE.read_text()
    recurrent_raw = RECURRENT.read_bytes()
    roots = {"canonical": SOURCE}
    staging = runroot / "staging"
    variant_parent = TEMP / runroot.name / "variants"
    variant_parent.mkdir(parents=True)
    permitted_imports = {"copy", "math", "struct"}
    for name, (before, after, guarantee) in MUTANTS.items():
        if raw.count(before) != 1:
            raise RuntimeError(name + ":SINGLE_REPLACEMENT_SITE")
        changed = raw.replace(before, after)
        compile(changed, name + "/oracle.py", "exec")
        imports = imported_names(changed)
        if set(imports) - permitted_imports:
            raise RuntimeError(name + ":IMPORT_CLOSURE")
        root = variant_parent / name
        oracle_dir = root / "scripts/research/glm53_flash/linear_attention"
        recurrent_dir = root / "scripts/research/glm53_flash/recurrent_dispatch"
        oracle_dir.mkdir(parents=True)
        recurrent_dir.mkdir(parents=True)
        (oracle_dir / "oracle.py").write_text(changed)
        (recurrent_dir / "oracle.py").write_bytes(recurrent_raw)
        diff = "".join(difflib.unified_diff(
            raw.splitlines(True), changed.splitlines(True),
            fromfile="canonical/oracle.py", tofile=name + "/oracle.py",
        ))
        out = staging / name
        out.mkdir(parents=True)
        (out / "mutation.patch").write_text(diff)
        verification = {
            "mutant": name,
            "named_guarantee": guarantee,
            "replacement_count": 1,
            "canonical_sha256": sha256(raw.encode()),
            "mutant_sha256": sha256(changed.encode()),
            "recurrent_sha256": sha256(recurrent_raw),
            "imports": imports,
            "metadata_call": "variant.oracle.validate direct",
            "crosscheck_call": "variant.oracle.module_reference with scalar/list accepted recurrent oracle",
            "controls_engine_used": False,
            "source_load_used": False,
        }
        (out / "verification.json").write_bytes(encoded(verification))
        roots[name] = root
    return roots


def protected_hashes():
    return {path: sha256((SOURCE / path).read_bytes()) for path in PROTECTED}


def score_cell(testcase, variant, mode, guarantee, record, payload, contract_sha, file_sha):
    checks = []

    def check(label, actual, expected):
        checks.append(assertion_record(testcase, label, variant + ":" + mode, actual, expected))

    check("CELL_CAPTURE_GUARANTEE", capture_ok(record), True)
    check("CELL_STRUCTURED_RESULT_GUARANTEE", payload is not None, True)
    if payload is None:
        return checks
    check("CELL_CONTRACT_DIGEST_GUARANTEE", payload.get("contract_sha256"), contract_sha)
    check("CELL_FILE_DIGEST_GUARANTEE", payload.get("contract_file_sha256"), file_sha)
    failed = sorted({row["guarantee"] for row in payload.get("assertions", []) if row.get("status") == "FAIL"})
    if variant == "canonical":
        check("CANONICAL_STATUS_GUARANTEE", payload.get("status"), "PASS")
        check("CANONICAL_EXIT_GUARANTEE", record.get("exit_code"), 0)
    else:
        check("MUTANT_SEMANTIC_STATUS_GUARANTEE", payload.get("status"), "SEMANTIC_FAILURE")
        check("MUTANT_SEMANTIC_EXIT_GUARANTEE", record.get("exit_code"), 10)
        check(guarantee, guarantee in failed, True)
        check("MUTANT_INFRA_ABSENCE_GUARANTEE", payload.get("infra"), [])
    return checks


def orchestrate():
    run_id = os.environ.get("PULSAR_RUN_ID", "qualification-v1")
    runroot = EVIDENCE / run_id
    if runroot.exists():
        raise RuntimeError("RUN_ROOT_ALREADY_EXISTS")
    runroot.mkdir()
    summary = {
        "schema": "glm53-flash-matrix-qualification-v2",
        "run_id": run_id,
        "terminal": "HARNESS_NOT_READY",
        "cells": [],
        "canaries": [],
        "outer_assertions": [],
        "correction_count": int(os.environ.get("PULSAR_CORRECTION_COUNT", "0")),
    }
    testcase = unittest.TestCase()
    try:
        fixture = json.loads(FIXTURE.read_bytes())
        contract = build_contract(fixture)
        contract_raw = encoded(contract)
        contract_sha = sha256(contract_raw)
        file_sha = sha256(Path(__file__).read_bytes())
        (runroot / "expected-table.json").write_bytes(contract_raw)
        (runroot / "expected-table.sha256").write_text(contract_sha + "  expected-table.json\n")
        (runroot / "harness.sha256").write_text(file_sha + "  " + Path(__file__).name + "\n")
        before = protected_hashes()
        (runroot / "protected-before.json").write_bytes(encoded(before))
        roots = stage_variants(runroot)

        focused_argv = [sys.executable, "-I", "-B", str(SOURCE / "scripts/research/tests/test_glm53_flash_linear_attention.py")]
        focused, _, _ = execute_and_store(focused_argv, 120, runroot / "focused-suite", dict(os.environ))
        focused_checks = [
            assertion_record(testcase, "FOCUSED_CAPTURE_GUARANTEE", "focused-suite", capture_ok(focused), True),
            assertion_record(testcase, "FOCUSED_EXIT_GUARANTEE", "focused-suite", focused.get("exit_code"), 0),
        ]
        summary["outer_assertions"].extend(focused_checks)

        canary_specs = (
            ("bare-normal", False, "assert False", False),
            ("bare-optimized", True, "assert False", True),
            ("unittest-normal", False, "import unittest;unittest.TestCase().fail('OPT_CANARY')", False),
            ("unittest-optimized", True, "import unittest;unittest.TestCase().fail('OPT_CANARY')", False),
        )
        for name, optimized, statement, expect_zero in canary_specs:
            argv = [sys.executable] + (["-O"] if optimized else []) + ["-c", statement]
            record, _, _ = execute_and_store(argv, 30, runroot / "canaries" / name, dict(os.environ))
            checks = [
                assertion_record(testcase, "CANARY_CAPTURE_GUARANTEE", name, capture_ok(record), True),
                assertion_record(testcase, "CANARY_MODE_GUARANTEE", name,
                                 record.get("exit_code") == 0, expect_zero),
            ]
            summary["canaries"].append({"name": name, "capture": record, "assertions": checks})
            summary["outer_assertions"].extend(checks)

        cell_order = [("canonical", mode) for mode in ("normal", "optimized")]
        cell_order += [(name, mode) for name in MUTANTS for mode in ("normal", "optimized")]
        for variant, mode in cell_order:
            argv = [sys.executable] + (["-O"] if mode == "optimized" else []) + [str(Path(__file__).resolve())]
            env = dict(os.environ)
            env.update(PULSAR_INNER="1", PULSAR_VARIANT_ROOT=str(roots[variant]),
                       PULSAR_CONTRACT_SHA256=contract_sha)
            record, stdout, _ = execute_and_store(
                argv, 30, runroot / "matrix" / variant / mode, env
            )
            payload = parse_payload(stdout)
            if payload is not None:
                (runroot / "matrix" / variant / mode / "semantic.json").write_bytes(encoded(payload))
            guarantee = MUTANTS[variant][2] if variant != "canonical" else "CANONICAL_STATUS_GUARANTEE"
            checks = score_cell(testcase, variant, mode, guarantee, record, payload, contract_sha, file_sha)
            summary["outer_assertions"].extend(checks)
            summary["cells"].append({
                "variant": variant, "mode": mode, "capture": record,
                "semantic_status": None if payload is None else payload.get("status"),
                "assertions": checks,
            })
            if variant == "canonical" and any(row["status"] != "PASS" for row in checks):
                break

        after = protected_hashes()
        (runroot / "protected-after.json").write_bytes(encoded(after))
        protected_check = assertion_record(
            testcase, "PROTECTED_BYTES_GUARANTEE", "before-after", after, before
        )
        summary["outer_assertions"].append(protected_check)
        expected_cells = 14
        complete = len(summary["cells"]) == expected_cells
        all_outer_pass = all(row["status"] == "PASS" for row in summary["outer_assertions"])
        no_inner_infra = all(cell["semantic_status"] != "INFRA_INDETERMINATE" for cell in summary["cells"])
        if complete and all_outer_pass and no_inner_infra:
            summary["terminal"] = "PASS_SCOPED_PENDING_REVIEW"
            code = 0
        elif any(row["guarantee"].startswith("CANARY_") and row["status"] != "PASS"
                 for row in summary["outer_assertions"]):
            summary["terminal"] = "HARNESS_NOT_READY"
            code = 2
        else:
            summary["terminal"] = "PARTIAL"
            code = 1
    except BaseException as exc:
        summary["orchestration_error"] = exception_record(exc)
        summary["terminal"] = "HARNESS_NOT_READY"
        code = 2
    summary["finished_unix"] = time.time()
    (runroot / "summary.json").write_bytes(encoded(summary))
    print(json.dumps({
        "terminal": summary["terminal"],
        "cells": len(summary["cells"]),
        "failed_outer_assertions": sum(row["status"] != "PASS" for row in summary["outer_assertions"]),
        "run_id": run_id,
    }, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(inner_contract() if os.environ.get("PULSAR_INNER") == "1" else orchestrate())
