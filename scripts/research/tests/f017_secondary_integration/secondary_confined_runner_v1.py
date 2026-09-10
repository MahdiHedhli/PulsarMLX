"""Fixed secondary descriptor qualification using the published unchanged fence.

This controller performs source-free setup only. Candidate modules are first
imported by the hash-bound child after actual read/write/network denials.
NumPy, numerical graph execution and the full wrapper are not admitted here.
The S54 selector names are compatibility identifiers, not a historical replay.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import sys
import tempfile
import threading

SOURCE = Path(__file__).resolve().parents[4]
CI = SOURCE / "scripts/ci"
PINNED = {
    "f017_primary_stdlib_doctor_v1.py": "3a3f48ad697d8142642bb9371ac83d7d45a5e58444a8bf8e19fea4321e14a979",
    "f017_preparation_capture_v1.py": "676374349ea53c2dfa0e505f8cbabdb0df0cf7281a5f0521b79e8fa3631cf80c",
}
for name, expected in PINNED.items():
    if hashlib.sha256((CI / name).read_bytes()).hexdigest() != expected:
        raise ValueError("TRUSTED_CAPTURE_BINDING")
sys.path.insert(0, str(CI))
import f017_primary_stdlib_doctor_v1 as doctor
import f017_primary_stdlib_resource_v1 as bounded
import f017_preparation_capture_v1 as cap

BOOTSTRAP = "scripts/research/tests/f017_primary_confined_bootstrap_v1.py"
BOOTSTRAP_SHA = "75af87090f866b59e5394817f616afdb4490e51d8d52cd911e8fac003d401c3e"
MODULE_NAMES = (
    "f017_secondary_descriptor_source_v1", "f017_secondary_read_observation_factory_v1",
    "f017_secondary_read_observation_v1", "f017_secondary_read_observation_prefix_v1",
    "f017_secondary_read_observation_inputs_v1", "f017_primary_read_observation_v1",
    "f017_descriptor_lease_manager_v10", "f017_bounded_artifact_decode_v1",
    "f017_accounting_root_continuity_v1", "f017_canonical_serialization_v10",
    "f017_oracle_primary_decoders", "iq2_xxs_tables", "iq3_xxs_tables", "iq_extra_tables",
)
TEST_NAMES = ("secondary_cases_v1", "secondary_oracle_v1")
DISPATCH = b"from secondary_cases_v1 import run\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--doctor-report", required=True)
    parser.add_argument("--doctor-sha256", required=True)
    args = parser.parse_args()
    cap.need(sys.platform == "darwin" and sys.flags.isolated and sys.flags.no_site
             and sys.flags.dont_write_bytecode and not sys.flags.optimize, "ISOLATED_ENTRY")
    raw = Path(args.doctor_report).read_bytes()
    cap.need(len(raw) <= 1048576 and cap.sha(raw) == args.doctor_sha256, "EXACT_DOCTOR_REPORT")
    admitted = json.loads(raw)
    python = str(Path(sys.executable).resolve())
    cap.need(admitted["result"] == "HARNESS_READY" and admitted["description"]["python"] == python,
             "SUCCESSFUL_CURRENT_DOCTOR")
    parent = Path(tempfile.mkdtemp(prefix="f017-secondary-prefix-")).resolve()
    (parent / "tmp").mkdir(mode=0o700)
    (parent / "cache").mkdir(mode=0o700)
    env = dict(PATH="/usr/bin:/bin", LANG="C", LC_ALL="C", TMPDIR=str(parent / "tmp"),
               XDG_CACHE_HOME=str(parent / "cache"), PYTHONDONTWRITEBYTECODE="1")
    captures = []
    reports = []
    cap.bank(parent / "doctor-binding.json", cap.canonical(dict(sha256=cap.sha(raw),
        result=admitted["result"], scope=admitted["scope"], python=python,
        source_root=str(SOURCE), qualification="STDLIB_DESCRIPTOR_PREFIX_ONLY")))

    def capture(argv, area, label):
        cap.need(shutil.disk_usage(parent).free >= 8 * 1024**3, "STORAGE_FLOOR")
        result, out, err = bounded.capture(argv, area, label, env, timeout=180, limit=12 * 1024**2)
        captures.append(result)
        cap.need(result["capture_integrity"] == "PASS" and result["reaped"], "BOUNDED_CAPTURE")
        return result, out, err

    try:
        bootstrap = (SOURCE / BOOTSTRAP).read_bytes()
        cap.need(cap.sha(bootstrap) == BOOTSTRAP_SHA, "UNCHANGED_TRUSTED_BOOTSTRAP")
        r, out, err = capture([python, "-I", "-S", "-B", str(SOURCE / BOOTSTRAP),
                               "--describe-source-free"], parent, "description")
        cap.need(r["exit_code"] == 0 and not err, "SOURCE_FREE_DESCRIPTION")
        description = json.loads(out)
        cap.need(description["python"] == python, "CURRENT_EXECUTABLE")
        modules = {name: "scripts/research/" + name + ".py" for name in MODULE_NAMES}
        modules.update({name: "scripts/research/tests/f017_secondary_integration/" + name + ".py"
                        for name in TEST_NAMES})
        files = set(modules.values())
        # Census is data only; its one fixed tuple includes the unimported full
        # wrapper. No arbitrary code or caller-provided import name is accepted.
        tree = ast.parse((SOURCE / modules["f017_secondary_read_observation_inputs_v1"]).read_bytes())
        assignments = [n for n in tree.body if isinstance(n, ast.Assign)
                       and any(isinstance(t, ast.Name) and t.id == "MEASUREMENT_FILES" for t in n.targets)]
        cap.need(len(assignments) == 1, "FIXED_MEASUREMENT_CENSUS")
        files.update("scripts/research/" + name for name in ast.literal_eval(assignments[0].value))
        bodies = {name: (SOURCE / name).read_bytes() for name in sorted(files)}
        hashes = {name: cap.sha(body) for name, body in bodies.items()}
        cap.need(all(len(body) <= 1048576 for body in bodies.values()), "SOURCE_BODY_BOUND")
        cap.bank(parent / "source-census.json", cap.canonical(dict(files=hashes, modules=modules,
            excluded_execution=["numpy", "numerical_core", "full_wrapper", "result_banking"])))
        for index in (1, 2):
            trial = parent / ("root-" + str(index))
            trial.mkdir(mode=0o700)
            area = trial / "sealed"
            denied = trial / "denied"
            for path in (area, denied, *(area / n for n in ("tooling", "work", "tmp", "cache"))):
                path.mkdir(mode=0o700)
            for relative, body in bodies.items():
                doctor.readonly(area / "tooling/codeviews/successor" / relative, body)
            doctor.readonly(area / "tooling/bootstrap.py", bootstrap)
            doctor.readonly(area / "tooling/primary_cases54.py", DISPATCH)
            profile = doctor.profile(area, trial, description["python_framework"])
            doctor.readonly(area / "tooling/baseline.sb", profile)
            public = b"SECONDARY_FIXED_PUBLIC_READ\n"
            cap.bank(denied / "read.txt", public)
            cap.bank(area / "work/read.txt", public)
            listener = socket.socket()
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            listener.settimeout(3)
            acknowledgements = []
            def serve():
                try:
                    connection, _ = listener.accept()
                    with connection:
                        connection.settimeout(2)
                        data = connection.recv(128)
                        connection.sendall(data)
                        acknowledgements.append(data.hex())
                except OSError as error:
                    acknowledgements.append(type(error).__name__)
            common = dict(nonce=os.urandom(16).hex(), read_path=str(denied / "read.txt"),
                write_path=str(denied / "write.txt"), allowed_read_path=str(area / "work/read.txt"),
                allowed_write_path=str(area / "work/write.txt"), endpoint=list(listener.getsockname()),
                public_nonce=os.urandom(16).hex(), fixture_expected=dict(read_hex=public.hex(),
                    write_hex=b"SECONDARY_FIXED_PUBLIC_WRITE\n".hex()), fixture_identity="SYNTHETIC_ONLY")
            rows = {"S54-B01-POSITIVE": dict(common, mode="positive", case_id=None, view=None),
                    "S54-B01-SUCCESSOR": dict(common, mode="successor", case_id="INTEGRATION", view="successor")}
            st = area.stat()
            catalogue = dict(schema="f017.sequence54.catalogue/1", sequence=54, root=str(area),
                root_identity=dict(dev=str(st.st_dev), inode=str(st.st_ino)), python=python,
                python_framework=description["python_framework"], bootstrap_sha256=cap.sha(bootstrap),
                profile_sha256=cap.sha(profile), module_closure_sha256=cap.sha(cap.canonical(description["module_closure"])),
                api_provenance=description["api_provenance"], rows=rows,
                code_manifests=dict(successor=dict(files=hashes, modules=modules)), dispatch_sha256=cap.sha(DISPATCH))
            catraw = cap.canonical(catalogue)
            cap.need(len(catraw) <= 32768, "CATALOGUE_BOUND")
            doctor.readonly(area / "tooling/catalogue54-B01.json", catraw)
            thread = threading.Thread(target=serve)
            thread.start()
            try:
                r, out, err = capture([python, "-I", "-S", "-B", str(area / "tooling/bootstrap.py"),
                                       "S54-B01-POSITIVE"], area, "positive")
                thread.join(4)
                cap.need(not thread.is_alive() and acknowledgements == [common["public_nonce"].encode().hex()], "POSITIVE_NETWORK")
                events = [json.loads(line) for line in out.splitlines()]
                cap.need(r["exit_code"] == 0 and not err and len(events) == 1
                         and events[0]["phase"] == "POSITIVE_COMPLETE", "POSITIVE_FIXTURE")
                cap.need(events[0]["detail"] == dict(read_hex=public.hex(),
                    write_hex=common["fixture_expected"]["write_hex"], ack_hex=common["public_nonce"].encode().hex()), "POSITIVE_VALUES")
                r, out, err = capture([python, "-I", "-S", "-B", str(area / "tooling/bootstrap.py"),
                                       "S54-B01-SUCCESSOR"], area, "secondary")
                events = [json.loads(line) for line in out.splitlines()]
                cap.need([e["phase"] for e in events[:3]] == ["PRE_SEAL", "SEAL_APPLIED", "FENCE_PASSED"], "FENCE_BEFORE_IMPORT")
                cap.need(all(events[2]["detail"][n]["errno"] in (1, 13) for n in ("read", "write", "network")), "ACTUAL_DENIALS")
                cap.need(r["exit_code"] == 0 and not err and len(events) == 4
                         and events[3]["phase"] == "FIXTURE_COMPLETE", "SECONDARY_CASE_COMPLETION")
                detail = events[3]["detail"]["case_result"]
                report_raw = (area / "work/S54-B01-SUCCESSOR/secondary-cases.json").read_bytes()
                cap.need(cap.sha(report_raw) == detail["report_sha256"] and len(report_raw) == detail["report_bytes"], "ALL_CASE_BINDING")
                reports.append(dict(root=index, detail=detail, profile_sha256=cap.sha(profile), events=events))
                cap.bank(parent / ("completed-root-" + str(index) + ".json"), cap.canonical(reports[-1]))
            finally:
                listener.close()
                thread.join(4)
                cap.need(not thread.is_alive(), "OWN_LISTENER_REAPED")
        cap.need(all(cap.sha((SOURCE / name).read_bytes()) == digest for name, digest in hashes.items()), "SOURCE_RECENSUS")
        outcome = dict(result="PASS", scope="STDLIB_SECONDARY_DESCRIPTOR_PREFIX_ONLY", roots=reports)
    except Exception as error:
        outcome = dict(result="PARTIAL_NOT_QUALIFIED", exception=type(error).__name__, message=str(error), roots=reports)
    outcome.update(root=str(parent), captures=captures,
        actual_nested_target_starts=sum(item["actual_target_start"] for item in captures),
        retained=True, numerical_decode="NOT_QUALIFIED", full_wrapper="NOT_QUALIFIED",
        baseline_numpy_equivalence="NOT_QUALIFIED", native_full_forward_P1="NOT_QUALIFIED")
    cap.bank(parent / "result.json", cap.canonical(outcome))
    print(json.dumps(dict(result=outcome["result"], root=str(parent), result_sha256=cap.sha(cap.canonical(outcome)),
        actual_nested_target_starts=outcome["actual_nested_target_starts"]), sort_keys=True))
    return 0 if outcome["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
