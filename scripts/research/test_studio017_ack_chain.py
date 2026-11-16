"""Physical sandboxed control, with a private synthetic grant and no admission to either model stage.

Invoke with the pinned Python and arguments POLICY SHA256 EXISTING_PRIVATE_PARENT OPERATION32.
The fresh directory synthetic-admission-OPERATION retains every original receipt on success or refusal.
"""
import os
from pathlib import Path
import select
import socket
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import studio017_ack_fixture as fixture
import studio017_py_gate as pyg
import studio017_supervise as sup


def exercise(policy_path, sha, parent, op):
    policy = pyg.binding(policy_path, sha)
    pyg.validate(policy, True)
    parent = pyg.real(parent)
    sup.need(parent.is_relative_to(sup.STATE) and parent != sup.STATE and
             not any(parent.is_relative_to(sup.STATE / ("campaign-" + r)) for r in sup.ROLES),
             "private fixture root")
    sup.hexid(op, 32)
    d = parent / ("synthetic-admission-" + op)
    d.mkdir(mode=0o700)
    out = d / "out"
    out.mkdir(mode=0o700)
    for role in fixture.ROLES:
        pyg.fresh_cache(d / ("cache-" + role))
    sup.put(d / "denied-marker", {"requires": "sandbox refusal"})
    cap = d / "fixture-cap.json"
    grant = d / "fixture-grant.json"
    spent = d / "fixture-spend.json"
    sup.put(grant, dict(schema="studio017-synthetic-ack-only/1", stage=fixture.STAGE, operation=op))
    exe = policy["interpreter"]
    sup.need(str(Path(sys.executable).resolve()) == exe, "control interpreter")
    binding = dict(policy=policy_path, sha256=sha, interpreter=exe)
    image = sup.procpath(os.getpid())
    data = dict(schema="studio017-fixture-cap/1", stage=fixture.STAGE, run=op,
                operation=op, grant_sha256=sup.digest(grant), supervisor=os.getpid(),
                expected_image=image, supervisor_image=image, python_gate=binding)
    sup.put(cap, data)
    # Production requires its own fixed role and cap location, before any claim access.
    try:
        sup.child(cap)
    except ValueError as e:
        sup.need(str(e) == "stage cap location", "wrong negative-control rejection")
    else:
        raise ValueError("production child accepted a fixture capability")

    cfg = dict(artifacts={"python-policy": {"path": policy_path, "sha256": sha}},
               stages={"reference": {"python": exe}})
    read_dirs = [*policy["roots"], *[str(d / ("cache-" + n)) for n in fixture.ROLES],
                 "/System/Library", "/usr/lib", "/usr/share", "/Library/Apple", "/usr/bin",
                 "/bin", "/dev", "/private/var/db/dyld"]
    files = [policy_path, *policy["images"], exe, image, str(cap), str(grant),
             str(spent), str(d / "active.json")]
    sup.need(not any(sup.ROOT.is_relative_to(Path(n)) or Path(n).is_relative_to(sup.ROOT)
                     for n in read_dirs + files), "synthetic profile overlaps checkpoint")
    sb = d / "fixture.sb"
    profile = sup.child_profile(read_dirs, files, out, [pyg.rolepath(d, n) for n in fixture.ROLES])
    with sb.open("xb") as f:
        f.write(profile)
    sb.chmod(0o400)
    sup.put(d / "timing-intent.json", dict(
        operation=op, python_policy_sha256=sha, profile_sha256=sup.sha(profile), limit_seconds=60,
        start="before durable exclusive local synthetic spend", end="owner validated and replied to ACK",
        excludes=["production remote spend, grant readback and renewed host/source/checkpoint admission",
                  "reference NumPy or native MLX startup; worker is an isolated CPython fixture"]))
    worker = lease = None
    owner, peer = socket.socketpair(type=socket.SOCK_DGRAM)
    rd, wr = os.pipe()
    success = False
    clock = time.monotonic
    timestamps = {}
    try:
        env = {"HOME": str(Path.home()), "PATH": "/usr/bin:/bin", "LC_ALL": "C",
               "STUDIO017_ADMIT_CHANNEL": str(peer.fileno())}
        argv = ["/usr/bin/sandbox-exec", "-f", str(sb), *fixture.arguments(cap, "fixture-bootstrap", [rd])]
        with (d / "stdout").open("xb") as so, (d / "stderr").open("xb") as se:
            timestamps["start"] = clock()
            sup.put(spent, dict(schema="studio017-synthetic-spend-only/1", stage=fixture.STAGE,
                                run=op, operation=op, supervisor=os.getpid(),
                                grant_sha256=sup.digest(grant), cap_sha256=sup.digest(cap)))
            timestamps["spent"] = clock()
            worker = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=so, stderr=se,
                                      env=env, cwd=out, process_group=0, pass_fds=(rd, peer.fileno()))
            os.close(rd)
            rd = -1
            peer.close()
            lease = sup.attach_guard(cfg, d, worker, timestamps["start"] + 90, op, "lease-numeric", se)
            timestamps["guardian_ready"] = clock()
            guard = lease.receipt()
            birth = sup.cmd(["/bin/ps", "-p", str(worker.pid), "-o", "lstart="]).decode().strip()
            sup.put(d / "active.json", dict(guardian=guard, operation=op, supervisor=os.getpid(),
                                           child=worker.pid, birth=birth, cap_sha256=sup.digest(cap),
                                           claim_sha256=sup.digest(spent)))
            os.write(wr, b"G")
            os.close(wr)
            wr = -1
            timestamps["barrier_released"] = clock()
            while not select.select([owner], [], [], .1)[0]:
                sup.need(worker.poll() is None and clock() - timestamps["start"] < 60,
                         "fixture exited or exceeded ACK window")
                lease.pulse()
            sup.accept_ack(owner, worker, data, fixture.STAGE, cap, spent)
            timestamps["ack"] = clock()
            sup.need(timestamps["ack"] - timestamps["start"] < 60, "ACK exceeded window")
            while worker.poll() is None:
                lease.pulse()
                time.sleep(.05)
            success = worker.returncode == 0
    finally:
        for fd in (wr, rd):
            if fd >= 0:
                os.close(fd)
        owner.close()
        peer.close()
        if worker is not None:
            residual, clean = sup.end_owned(worker, lease, success)
        else:
            residual, clean = False, True
        sup.put(d / "observed.json", dict(operation=op, timestamps_monotonic=timestamps,
                worker_pid=worker.pid if worker else None, exit=worker.returncode if worker else None,
                guardian_pid=lease.guard.pid if lease else None, clean_reap=clean, residual=residual))
    sup.need(success and clean and not residual, "fixture or cleanup failed")
    ack = sup.doc(d / "admitted.json")
    parent_pid = os.getpid()
    pids = {"fixture-bootstrap": (worker.pid, parent_pid), "fixture-worker": (worker.pid, parent_pid),
            "fixture-helper": (ack["helper"], worker.pid), "lease-numeric": (guard["watcher_pid"], parent_pid)}
    proofs = {role: pyg.checked_receipt(d, role, op, pid, sha, policy, ppid)
              for role, (pid, ppid) in pids.items()}
    sup.need(sup.doc(d / "stdout") == dict(operation=op, stage=fixture.STAGE,
             helper_acknowledged=True, sandbox_denied_marker=True), "worker result")
    sup.put(d / "result.json", dict(operation=op, status="passed", role_receipts=proofs,
            seconds_local_synthetic_spend_to_ack=timestamps["ack"]-timestamps["start"],
            production_stage_rejected_fixture=True, real_grant=False))
    print(d)


if __name__ == "__main__":
    exercise(*sys.argv[1:])
