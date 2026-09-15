"""Immediate, evidence-first campaign children with immutable fault contracts."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
from q_capture import capture, clean_env
from q_matrix import inventory
from q_result_validator import read_capture, validate_identity, validate_python, validate_rust

executed_cases = set()
qualified_cases = set()


def write_original(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def configure(pristine, root, evidence, matrix, campaign_seconds=2700):
    global owned_root, evidence_root, matrix_rows, deadline
    if not 120 <= campaign_seconds <= 2700:
        raise RuntimeError("PARTIAL: campaign limit is outside the admitted bound")
    frozen = json.loads(matrix.read_bytes())
    if frozen != inventory(pristine):
        raise RuntimeError("PROPERTY_UNCOVERED: frozen matrix no longer matches source")
    owned_root, evidence_root = root, evidence
    matrix_rows = {row["id"]: row for row in frozen["properties"]}
    evidence_root.mkdir(mode=0o700, parents=True, exist_ok=False)
    deadline = time.monotonic() + campaign_seconds
    write_original(evidence_root / "campaign-source.json", {"harness_sha256": frozen["harness_sha256"], "matrix_sha256": hashlib.sha256(matrix.read_bytes()).hexdigest(), "python": sys.executable, "properties": 20, "aggregate_limit_seconds": campaign_seconds})


def recorded(command, cwd, env, path):
    if time.monotonic() + 120 > deadline:
        raise RuntimeError("PARTIAL: insufficient campaign time for bounded child")
    executable_sha256 = hashlib.sha256(Path(command[0]).resolve().read_bytes()).hexdigest()
    scripts = []
    for arg in command[1:]:
        candidate = Path(arg)
        if not candidate.is_absolute(): candidate = Path(cwd) / candidate
        if candidate.suffix in {".py", ".rs", ".sh"} and candidate.is_file():
            scripts.append((candidate, hashlib.sha256(candidate.read_bytes()).hexdigest()))
    terminal = capture(command, cwd, env, path, timeout=120)
    verified, output, files = read_capture(path)
    if terminal != verified:
        raise RuntimeError("EVIDENCE_INCOMPLETE: reread terminal mismatch")
    validate_identity(path, command[0], executable_sha256, scripts)
    return verified, output, files


def compiled_binary(output, test_target, target_root):
    artifacts = []
    for line in output.splitlines():
        try: record = json.loads(line)
        except ValueError: continue
        if record.get("reason") == "compiler-artifact" and record.get("target", {}).get("name") == test_target and record.get("executable"):
            artifacts.append(record["executable"])
    if len(artifacts) != 1:
        raise RuntimeError("EVIDENCE_INCOMPLETE: compiled binary is not unique")
    binary = Path(artifacts[0]).resolve()
    if not binary.is_relative_to(target_root.resolve()) or binary.is_symlink() or not binary.is_file():
        raise RuntimeError("EVIDENCE_INCOMPLETE: compiled binary outside owned target")
    return str(binary), hashlib.sha256(binary.read_bytes()).hexdigest()


def result(name, case, outcome, details):
    write_original(case / "result.json", {"id": name, "outcome": outcome, **details})
    executed_cases.add(name)
    if outcome == "SEMANTIC_KILL": qualified_cases.add(name)
    print("MUTANT_NEW_R_" + outcome + " " + name, flush=True)
    if outcome != "SEMANTIC_KILL":
        row=matrix_rows[name]
        if name == "declared-length-cap" or not row["independence"]["independent"] or row["independence"]["dependency_ids"]:
            raise RuntimeError("MUTATION_REJECTED: targeted gate or dependent non-kill " + name)


def rust_env(root, target):
    env = clean_env(root)
    cargo = Path(os.environ["CI_SELECTED_CARGO"])
    rustc = Path(os.environ["CI_SELECTED_RUSTC"])
    if not cargo.is_file() or not rustc.is_file():
        raise RuntimeError("TOOLING_NOT_READY: selected installed Rust tools missing")
    env.update({"PATH": str(cargo.parent) + os.pathsep + env["PATH"], "RUSTC": str(rustc), "CARGO_TARGET_DIR": str(target), "CARGO_NET_OFFLINE": "true", "RUSTUP_AUTO_INSTALL": "0"})
    for key in ("CARGO_HOME", "RUSTUP_HOME"):
        if key in os.environ:
            env[key] = os.environ[key]
    return env


def replace_exact(path, old, new, cardinality):
    source = path.read_text()
    if source.count(old) != cardinality:
        raise RuntimeError("PROPERTY_UNCOVERED: changed replacement anchor")
    path.write_text(source.replace(old, new))


def begin(name):
    if name not in matrix_rows or name in executed_cases:
        raise RuntimeError("PROPERTY_UNCOVERED: invalid or duplicate ID")
    case = evidence_root / name
    case.mkdir(mode=0o700)
    return matrix_rows[name], case


def rust_mutation(pristine, scratch, target, name, old, new, test_name, count=1, source_path="src/lib.rs", test_target="raw_http"):
    row, case = begin(name)
    if (old, new, count, source_path, test_name, test_target) != (row["anchor"], row["replacement"], row["expected_cardinality"], row["source_path"], row["pristine_named_test"], row["test_target"]):
        raise RuntimeError("PROPERTY_UNCOVERED: fault differs from frozen matrix")
    pristine_env = rust_env(owned_root, target / "pristine")
    mutant_target = target / "mutants" / name
    if mutant_target.exists():
        raise RuntimeError("MUTATION_REJECTED: mutant target was not fresh")
    env = rust_env(owned_root, mutant_target)
    cargo = os.environ["CI_SELECTED_CARGO"]
    terminal, output, _ = recorded([cargo, "test", "--offline", "--locked", "--test", test_target, "--no-run", "--message-format=json"], pristine, pristine_env, case / "pristine-compile")
    if terminal["code"] != 0:
        raise RuntimeError("TOOLING_NOT_READY: pristine did not compile")
    pristine_binary, pristine_binary_sha = compiled_binary(output, test_target, target / "pristine")
    terminal, output, _ = recorded([pristine_binary, "--exact", test_name, "--nocapture"], pristine, pristine_env, case / "pristine-test")
    validate_rust(terminal, output, test_name)
    mutant = scratch / name
    shutil.copytree(pristine, mutant, ignore=shutil.ignore_patterns("target", "__pycache__"))
    source = mutant / source_path
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    if before != row["source_sha256"]:
        raise RuntimeError("PROPERTY_UNCOVERED: pristine source identity differs")
    replace_exact(source, old, new, count)
    after = hashlib.sha256(source.read_bytes()).hexdigest()
    write_original(case / "source-identities.json", {"id": name, "pristine_sha256": before, "mutant_sha256": after, "source_path": source_path, "fault": row})
    # Retain the actual original mutant bytes before its compiler child runs.
    fd=os.open(case / "original-mutant-source",os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,"wb") as f: f.write(source.read_bytes()); f.flush(); os.fsync(f.fileno())
    terminal, output, _ = recorded([cargo, "test", "--offline", "--locked", "--test", test_target, "--no-run", "--message-format=json"], mutant, env, case / "mutant-compile")
    if terminal["code"] != 0:
        raise RuntimeError("TOOLING_NOT_READY: mutant did not compile")
    binary, binary_sha = compiled_binary(output, test_target, mutant_target)
    if hashlib.sha256(source.read_bytes()).hexdigest() != after:
        raise RuntimeError("EVIDENCE_INCOMPLETE: source changed during compile")
    write_original(case / "binary-identities.json", {"pristine_binary":pristine_binary,"pristine_binary_sha256":pristine_binary_sha,"mutant_binary":binary,"mutant_binary_sha256":binary_sha,"test_source_sha256":row["test_source_sha256"]})
    terminal, output, files = recorded([binary, "--exact", test_name, "--nocapture"], mutant, env, case / "mutant-test")
    try:
        outcome = validate_rust(terminal, output, test_name, row["intended_failing_assertion"])
    except RuntimeError as exc:
        if str(exc) not in {"WRONG_ASSERTION_FAILURE", "NON_SEMANTIC_TEST_FAILURE"}: raise
        outcome="NON_KILL_"+str(exc)
    if hashlib.sha256(source.read_bytes()).hexdigest() != after or hashlib.sha256(Path(binary).read_bytes()).hexdigest()!=binary_sha:
        raise RuntimeError("EVIDENCE_INCOMPLETE: test/source identity changed")
    test_source=mutant / ('tests/'+test_target+'.rs')
    if hashlib.sha256(test_source.read_bytes()).hexdigest()!=row["test_source_sha256"]:
        raise RuntimeError("EVIDENCE_INCOMPLETE: test source changed")
    result(name,case,outcome,{"pristine_pass":True,"compile_pass":True,"exact_assertion":row["intended_failing_assertion"],"mutant_source_sha256":after,"raw_test_files":files,"pristine_binary_sha256":pristine_binary_sha,"mutant_binary_sha256":binary_sha,"internal_teardown":"UNKNOWN at assertion panic unless test explicitly drains before assertion; process group capture reaping is separate"})


def python_mutation(pristine, scratch, python, name, old, new):
    if Path(python).absolute() != Path(sys.executable).absolute():
        raise RuntimeError("SDK_NOT_ADMITTED: selected interpreter differs")
    row, case = begin(name)
    if (old, new) != (row["anchor"], row["replacement"]):
        raise RuntimeError("PROPERTY_UNCOVERED: SDK fault differs from frozen matrix")
    env = clean_env(owned_root)
    oracle = str(pristine / "tests/q_sdk_guard_oracle.py")
    source = pristine / "tests/sdk_client.py"
    terminal, output, _ = recorded([python, "-I", "-B", oracle, "--client", str(source), "--case", name], pristine, env, case / "pristine-test")
    validate_python(terminal, output)
    mutant = scratch / (name + ".py")
    shutil.copy2(source, mutant)
    before = hashlib.sha256(mutant.read_bytes()).hexdigest()
    if before != row["source_sha256"]:
        raise RuntimeError("PROPERTY_UNCOVERED: SDK source identity differs")
    replace_exact(mutant, old, new, 1)
    after = hashlib.sha256(mutant.read_bytes()).hexdigest()
    write_original(case / "source-identities.json", {"id": name, "pristine_sha256": before, "mutant_sha256": after, "fault": row})
    fd=os.open(case / "original-mutant-source",os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,"wb") as f: f.write(mutant.read_bytes()); f.flush(); os.fsync(f.fileno())
    terminal, output, files = recorded([python, "-I", "-B", oracle, "--client", str(mutant), "--case", name], pristine, env, case / "mutant-test")
    outcome = validate_python(terminal, output, row["intended_failing_assertion"])
    if hashlib.sha256(mutant.read_bytes()).hexdigest() != after:
        raise RuntimeError("MUTATION_REJECTED: SDK " + name + " " + outcome)
    result(name,case,outcome,{"pristine_pass":True,"exact_assertion":row["intended_failing_assertion"],"mutant_source_sha256":after,"raw_test_files":files})
