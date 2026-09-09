"""Bounded external-environment supervisor for the explicitly issued slice."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import resource
import selectors
import signal
import subprocess
import sys
import time
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rc_guard as guard

MAX_RSS = 1024**3
OUTPUT_CAP = 16 * 1024**2

def dump(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")

def runtime(phase, backend):
    guard.verify_child_interpreter(phase)
    manifest = guard.verify_environment(phase)
    import mlx.core as mx
    import mlx.nn as nn
    import numpy
    import jinja2
    import markupsafe
    imports = [guard.verify_origin(m, phase, manifest) for m in (mx, nn, numpy, jinja2, markupsafe)]
    versions = {name: importlib.metadata.version(name) for name in ("mlx", "mlx-metal", "numpy", "Jinja2", "MarkupSafe")}
    if backend == "metal" and not mx.metal.is_available():
        return None, {"status": "UNAVAILABLE", "backend": backend, "imports": imports, "versions": versions}
    mx.set_default_device(mx.gpu if backend == "metal" else mx.cpu)
    limits = {}
    for name, value in (("set_memory_limit", 512 * 1024**2), ("set_cache_limit", 16 * 1024**2)):
        method = getattr(mx, name, None)
        if method is None:
            limits[name] = "UNSUPPORTED"
        else:
            limits[name] = {"requested_bytes": value, "previous_bytes": method(value)}
    return (mx, nn), {"backend": backend, "dtype": "float32", "imports": imports, "versions": versions, "mlx_limits": limits}

def child(args):
    phase = Path(args.phase).absolute()
    guard.verify_child_interpreter(phase)
    resource.setrlimit(resource.RLIMIT_CORE, (0,0))
    if args.ticket_fd is None:
        raise ValueError("parent admission pipe required")
    ticket = json.loads(os.read(args.ticket_fd, 65536))
    os.close(args.ticket_fd)
    if ticket["nonce"] != args.nonce or ticket["mode"] != args.mode or ticket["backend"] != args.backend:
        raise ValueError("child admission mismatch")
    rows = guard.input_manifest(phase)
    if guard.manifest_digest(rows) != ticket["input_digest"]:
        raise ValueError("child inputs changed before start")
    if Path(os.environ["TMPDIR"]).resolve() != phase / "scratch":
        raise ValueError("external temporary role required")
    print(json.dumps({"event": "started", "nonce": args.nonce}), flush=True)
    os.environ["FLASH_ADMITTED_PHASE"] = str(guard.OLD)
    os.environ["FLASH_ROUTER_CALLER_PHASE"] = str(phase)
    os.environ["FLASH_ADMITTED_BACKEND"] = args.backend
    if args.mode == "serializer":
        try:
            raise ValueError('synthetic serializer admission')
        except ValueError as exc:
            record={'numbers':[0,1.25,-2], 'exception':{'type':type(exc).__name__,'message':str(exc)}}
        if json.loads(json.dumps(record,allow_nan=False))!=record:
            raise AssertionError('serializer mismatch')
        print(json.dumps({'event':'result','status':'PASS','record':record,'core_limit':list(resource.getrlimit(resource.RLIMIT_CORE))}),flush=True)
        return 0
    os.environ["FLASH_ROUTER_CALLER_MODE"] = args.mode
    if args.mode == "archive":
        import rc_archive
        evidence=rc_archive.verify_archive(phase/'archives/single-case',ticket['archive_manifest_sha256'])
        try:
            rc_archive.check_part(b'changed',{'bytes':7,'sha256':'0'*64})
        except rc_archive.ArchiveError as exc:
            if str(exc)!='ARCHIVE_PART_DIGEST_SIZE':raise
        else:raise AssertionError('archive tamper probe survived')
        evidence['tampered_part_digest_probe']='EXPECTED_REJECTION'
        print(json.dumps({'event':'result','status':'PASS','archive':evidence,'core_limit':list(resource.getrlimit(resource.RLIMIT_CORE))}),flush=True)
        return 0
    loaded, info = runtime(phase, args.backend)
    print(json.dumps({"event":"runtime",**info}),flush=True)
    if loaded is None:
        print(json.dumps({'event':'result','status':'UNAVAILABLE','backend':args.backend}),flush=True)
        return 0
    if args.mode == "smoke":
        mx,_=loaded
        value=mx.array([1.,2.],dtype=mx.float32)+mx.array([3.,4.],dtype=mx.float32)
        mx.eval(value);mx.synchronize();actual=value.tolist()
        if actual != [4.,6.]:raise AssertionError('known-answer addition mismatch')
        print(json.dumps({'event':'result','status':'PASS','backend':args.backend,'value':actual,'peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}),flush=True)
        return 0
    pattern="test_glm53_flash_router_caller_numeric.py"
    test_root = phase.parent / "repos/PulsarMLX/scripts/research/tests"
    suite = unittest.defaultTestLoader.discover(str(test_root), pattern=pattern)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    after = guard.input_manifest(phase)
    if guard.manifest_digest(after) != ticket["input_digest"]:
        raise AssertionError("child input drift")
    print(json.dumps({"event": "result", "status": "PASS" if result.wasSuccessful() else "FAIL",
                      "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
                      "skips": len(result.skipped), "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}), flush=True)
    return 0 if result.wasSuccessful() else 1

def parent(args):
    phase = guard.admit_phase(args.phase)
    guard.verify_environment(phase)
    size = guard.phase_size(phase)
    free = os.statvfs(phase).f_bavail * os.statvfs(phase).f_frsize
    if size > guard.MAX_GROWTH - guard.RESERVE or free < guard.RESERVE:
        raise ValueError("phase growth/closeout headroom insufficient")
    public_fixtures = phase.parent / "repos/PulsarMLX/fixtures/research/glm53-flash-router-caller-v1"
    fixture_files = [f for d in (phase / "fixtures", public_fixtures) for f in d.rglob("*") if f.is_file()]
    if sum(f.stat().st_size for f in fixture_files) > 64 * 1024**2:
        raise ValueError("fixture content ceiling exceeded")
    if any(f.stat().st_size > 1024 * 1024 for f in public_fixtures.rglob("*") if f.is_file()):
        raise ValueError("public fixture per-file ceiling exceeded")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", args.run_name):
        raise ValueError("bounded unique run name required")
    run = guard.confined(phase, phase / "runs" / args.run_name)
    run.mkdir(exist_ok=False)
    ledger = phase / "runs/launches.json"
    launches = json.loads(ledger.read_text()) if ledger.exists() else []
    if len(launches) >= 80:
        raise ValueError("numerical child launch ceiling reached")
    rows = guard.input_manifest(phase)
    digest = guard.manifest_digest(rows)
    checkpoints=phase/'evidence/checkpoints'
    checkpoints.mkdir(exist_ok=True)
    checkpoint=checkpoints/(digest+'.json')
    if not checkpoint.exists():
        snapshot=phase/'evidence/generations'/digest
        snapshot.mkdir(parents=True)
        for row in rows:
            # Prior bodies remain retained and are bound by hashes; copy only new
            # phase/public sources, never the environment or predecessor tree.
            if row['path'].startswith('router-caller-v1/') or '/router_caller/' in row['path'] or '/router-caller-v1/' in row['path'] or 'glm53-flash-router-caller-v1/' in row['path'] or 'test_glm53_flash_router_caller_' in row['path']:
                raw=guard.resolve_input(row).read_bytes()
                if hashlib.sha256(raw).hexdigest()!=row['sha256']:raise ValueError('checkpoint input drift')
                target=snapshot/row['path'];target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        dump(checkpoint,{'generation':digest,'associated_candidate_outputs_observed':False,'files':rows,
                         'environment_manifest_sha256':guard.sha(guard.environment_manifest(phase)),
                         'wheel_lock_sha256':guard.sha(guard.wheel_lock(phase)),
                         'phase':'router-caller-v1','mode_first_admitted':args.mode,
                         'expected_control_mechanisms':json.loads((public_fixtures/'controls.json').read_text()) if (public_fixtures/'controls.json').exists() else None,
                         'numeric_criteria':json.loads((public_fixtures/'cases.json').read_text())['criteria'] if (public_fixtures/'cases.json').exists() else None})
    nonce = uuid.uuid4().hex
    ticket = {"nonce": nonce, "mode": args.mode, "backend": args.backend, "input_digest": digest}
    if args.mode=="archive":ticket["archive_manifest_sha256"]=guard.sha(phase/"archives/single-case/manifest.json")
    launches.append({"run": args.run_name, "mode": args.mode, "backend": args.backend, "nonce": nonce})
    dump(ledger, launches)
    deadline = 175.0
    command = [str(guard.env_python(phase)), "-I", "-B", str(Path(__file__).resolve()),
               "--phase", str(phase), "--mode", args.mode, "--backend", args.backend,
               "--run-name", args.run_name, "--internal-child", "--nonce", nonce]
    if args.admission_spawn_error:
        if args.mode!='serializer':raise ValueError('spawn-error probe is admission-only')
        command[0]=str(phase/'scratch/nonexistent-admission-python')
    reader, writer = os.pipe()
    os.write(writer, json.dumps(ticket).encode())
    os.close(writer)
    command += ["--ticket-fd", str(reader)]
    environment = dict(os.environ, TMPDIR=str(phase / "scratch"), TMP=str(phase / "scratch"),
                       TEMP=str(phase / "scratch"), XDG_CACHE_HOME=str(phase / "cache"),
                       PYTHONDONTWRITEBYTECODE="1")
    prefix = {"argv": command, "ticket": ticket, "source_inputs": rows,
              "environment_manifest_sha256": guard.sha(guard.environment_manifest(phase)),
              "wheel_lock_sha256": guard.sha(guard.wheel_lock(phase)),
              "timeout_seconds": 180, "maximum_termination_seconds": 210,
              "effective_deadline_seconds": deadline, "rss_limit_bytes": MAX_RSS,
              "output_cap_bytes": OUTPUT_CAP, "phase_logical_bytes_before": size,
              "cache_scope": "TMP/TEMP/TMPDIR/XDG_CACHE_HOME controlled; OS driver caches not claimed isolated"}
    dump(run / "prefix.json", prefix)
    start = time.monotonic()
    try:
        process = subprocess.Popen(command, cwd=phase / "scratch", env=environment,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True, pass_fds=(reader,),
                                   preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_CORE,(0,0)))
    except OSError as exc:
        os.close(reader)
        for label in ('stdout','stderr'):(run/(label+'.txt')).write_bytes(b'')
        expected=args.admission_spawn_error and type(exc) is FileNotFoundError
        receipt={'run':args.run_name,'mode':args.mode,'backend':args.backend,
                 'status':'EXPECTED_SPAWN_ERROR' if expected else 'FAIL','spawned_successfully':False,
                 'spawn_error':{'type':type(exc).__name__,'errno':exc.errno,'message':str(exc)},
                 'returncode':None,'signal':None,'reason':'SPAWN_ERROR','child_wall_seconds':None,
                 'termination':{'stop_confirmed':True,'scope':'Popen exec-failure child reaped before OSError'},
                 'input_manifest_sha256':digest,'environment_bytes_reverified':False,
                 'supervised_attempt_count':len(launches),'core_limit_bytes':0}
        guard.verify_environment(phase);receipt['environment_bytes_reverified']=True
        dump(run/'receipt.json',receipt);print(json.dumps(receipt,indent=2));return 0 if expected else 1
    os.close(reader)
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    selector.register(process.stderr, selectors.EVENT_READ, "stderr")
    files = {k: (run / (k + ".txt")).open("xb") for k in ("stdout", "stderr")}
    total = peak = 0
    reason = None
    termination = {"term_sent_seconds": None, "kill_sent_seconds": None, "stop_confirmed": False}
    last_rss = start
    try:
        while selector.get_map() or process.poll() is None:
            elapsed = time.monotonic() - start
            for key, _ in selector.select(0.025):
                block = os.read(key.fileobj.fileno(), 65536)
                if not block:
                    selector.unregister(key.fileobj)
                    continue
                remaining = max(0, OUTPUT_CAP - total)
                files[key.data].write(block[:remaining])
                total += len(block)
                if total > OUTPUT_CAP:
                    reason = reason or "OUTPUT_LIMIT"
            if process.poll() is None and time.monotonic() - last_rss > 0.075:
                sample = subprocess.run(["/bin/ps", "-o", "rss=", "-p", str(process.pid)],
                                        capture_output=True, text=True, timeout=2)
                if sample.stdout.strip().isdigit():
                    peak = max(peak, int(sample.stdout.strip()) * 1024)
                last_rss = time.monotonic()
            if elapsed > deadline:
                reason = reason or "TIMEOUT"
            if peak > MAX_RSS:
                reason = reason or "RSS_LIMIT"
            if reason:
                if termination["term_sent_seconds"] is None:
                    termination["term_sent_seconds"] = elapsed
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                elif elapsed - termination["term_sent_seconds"] > 0.5 and termination["kill_sent_seconds"] is None:
                    termination["kill_sent_seconds"] = elapsed
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                elif termination["kill_sent_seconds"] is not None and elapsed - termination["kill_sent_seconds"] > 0.5:
                    break
            if process.poll() is not None and not selector.get_map():
                break
    except BaseException as exc:
        reason = "SUPERVISOR_EXCEPTION:" + type(exc).__name__
        if process.poll() is None:
            termination["term_sent_seconds"] = time.monotonic() - start
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                termination["kill_sent_seconds"] = time.monotonic() - start
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    pass
    finally:
        for stream in files.values():
            stream.close()
        selector.close()
    direct_stop = process.poll() is not None
    try:
        os.killpg(process.pid,0)
        group_stop=False
    except ProcessLookupError:
        group_stop=True
    stop=direct_stop and group_stop
    termination['direct_child_stopped']=direct_stop
    termination['owned_process_group_stopped']=group_stop
    termination["stop_confirmed"] = stop
    elapsed = time.monotonic() - start
    if not stop:
        dump(phase / "runs/STOP_NUMERICAL.json", {"run": args.run_name, "reason": "CHILD_STOP_UNCONFIRMED", "pid": process.pid})
    events = []
    for line in (run / "stdout.txt").read_text(errors="replace").splitlines():
        try:
            event = json.loads(line)
            if isinstance(event, dict):
                events.append(event)
        except (json.JSONDecodeError, RecursionError):
            pass
    results = [x for x in events if x.get("event") == "result"]
    result = results[-1] if results else None
    if result:
        peak = max(peak, result.get("peak_rss_bytes", 0))
    drift = guard.manifest_digest(guard.input_manifest(phase)) != digest
    env_ok = False
    try:
        guard.verify_environment(phase)
        env_ok = True
    except (ValueError, OSError):
        reason = reason or "ENVIRONMENT_DRIFT"
    status = result["status"] if result else "FAIL"
    if reason or process.returncode != 0 or not stop or drift or not env_ok or peak > MAX_RSS:
        status = "FAIL"
    receipt = {"status": status, "run": args.run_name, "mode": args.mode, "backend": args.backend,
               "returncode": process.returncode, "reason": reason,
               "child_wall_seconds": elapsed if stop else None, "observation_seconds": elapsed,
               "termination": termination, "peak_rss_bytes": peak,
               "rss_scope": "DIRECT_CHILD_ONLY; sampled plus normal result self-reported getrusage; descendants not prevented or included in RSS; owned process group termination checked",
               "output_bytes_observed": total, "output_capture_cap_bytes": OUTPUT_CAP,
               "outputs": {k: {"bytes": (run / (k + ".txt")).stat().st_size, "sha256": guard.sha(run / (k + ".txt"))} for k in files},
               "source_drift": drift, "environment_bytes_reverified": env_ok,
               "input_manifest_sha256": digest, "child_result": result, "signal": -process.returncode if process.returncode is not None and process.returncode < 0 else None, "spawn_error": None, "core_limit_bytes": 0,
               "phase_logical_bytes_after": guard.phase_size(phase), "supervised_attempt_count": len(launches), "spawned_successfully": True}
    dump(run / "receipt.json", receipt)
    print(json.dumps(receipt, indent=2))
    return 0 if status in {"PASS", "UNAVAILABLE"} else 1

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", required=True)
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--mode", choices=("serializer", "smoke", "case", "matrix", "archive"), required=True)
    parser.add_argument("--backend", choices=("cpu", "metal"), default="cpu")
    parser.add_argument("--internal-child", action="store_true")
    parser.add_argument("--admission-spawn-error",action="store_true")
    parser.add_argument("--ticket-fd", type=int)
    parser.add_argument("--nonce")
    args = parser.parse_args()
    return child(args) if args.internal_child else parent(args)

if __name__ == "__main__":
    raise SystemExit(main())
