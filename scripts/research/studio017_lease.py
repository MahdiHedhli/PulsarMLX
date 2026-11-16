"""A monitor-only sibling for one gated, dedicated Darwin process group.

No model/runtime imports, weights, grants, grader or execution API. The owner
must start its *direct* worker with process_group=0 behind a separate
EOF-refusing start gate. Keep that gate closed until Lease.attach returns.
Run helper with the pinned isolated interpreter and source.
"""
import math
import os
import select
import signal
import socket
import subprocess
import sys
import time

START_SECONDS = 35
HEARTBEAT_SECONDS = 45


def require(value, text):
    if not value:
        raise RuntimeError(text)


def read_one(channel, seconds):
    require(seconds > 0 and select.select([channel], [], [], seconds)[0],
            "lease deadline")
    return channel.recv(1)


def watch(fd, group, owner, deadline):
    # Before handshake, never signal anything. If the owner dies before ready,
    # the separately held worker start gate fails closed on kernel-generated EOF.
    require(fd >= 3 and group > 1 and os.getpgrp() == group != os.getpid()
            and os.getppid() == owner and os.getpgid(owner) != group
            and os.getsid(0) == os.getsid(owner), "unexpected guardian topology")
    require(math.isfinite(deadline) and time.monotonic() < deadline <= time.monotonic()+28801,
            "unguarded duration")
    with socket.socket(fileno=fd) as ch:
        require(ch.family == socket.AF_UNIX and ch.type == socket.SOCK_STREAM,
                "wrong lease channel")
        require(read_one(ch, START_SECONDS) == b'A', "missing arming request")
        # Own membership pins the *group*, even if the original worker dies and
        # its PID is recycled. kill(0, ...) targets THIS group, never a stored PID.
        disarmed = False
        try:
            ch.sendall(b'R')
            while True:
                b = read_one(ch, min(HEARTBEAT_SECONDS, deadline-time.monotonic()))
                if b == b'H':
                    continue
                if b == b'D':
                    disarmed = True
                    return
                break  # EOF, explicit X or malformed message
        finally:
            if not disarmed:
                os.kill(0, signal.SIGKILL)


class Lease:
    def __init__(self, channel, guard, group, deadline):
        self.channel, self.guard = channel, guard
        self.group, self.deadline = group, deadline

    @classmethod
    def attach(cls, worker, deadline, python, script, env, cwd, stderr, command=None):
        """Called by the actual supervisor, strictly before releasing worker gate."""
        group = worker.pid
        require(worker.poll() is None and os.getpgid(group) == group != os.getpgrp()
                and os.getsid(group) == os.getsid(0), "worker missing private group")
        ch, child = socket.socketpair()
        guard = None
        try:
            argv = [str(python), '-I', '-S', '-B', str(script), 'watch',
                    str(child.fileno()), str(group), str(os.getpid()), repr(deadline)]
            if command is not None: argv=command(child.fileno())
            guard = subprocess.Popen(argv, process_group=group, close_fds=True,
                                     pass_fds=(child.fileno(),), env=env, cwd=cwd,
                                     stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=stderr)
            child.close()
            ch.settimeout(START_SECONDS)
            ch.sendall(b'A')
            require(read_one(ch, START_SECONDS) == b'R' and guard.poll() is None,
                    "guardian did not arm")
            return cls(ch, guard, group, deadline)
        except BaseException:
            # EOF aborts a guard that was armed. Otherwise the not-yet-released
            # worker must be killed/reaped by the launcher (no model/grader ran).
            ch.close()
            if guard is not None:
                try: guard.wait(START_SECONDS)
                except subprocess.TimeoutExpired:
                    guard.kill();guard.wait(START_SECONDS)
            raise
        finally:
            child.close()

    def pulse(self):
        require(self.guard.poll() is None and time.monotonic() < self.deadline,
                "guardian lost or hard deadline")
        self.channel.sendall(b'H')

    def receipt(self):
        return dict(worker_pgid=self.group, watcher_pid=self.guard.pid,
                    owner_pid=os.getpid(), deadline_monotonic=self.deadline,
                    heartbeat_seconds=HEARTBEAT_SECONDS)

    def finish(self, worker, success, members):
        """Return (residual group killed, clean reap). members() is owner census.
        Only send normal disarm after original worker exited, was reaped, and
        the sole remaining group member is this watcher. Never signal a cached
        group ID. Caller may seal only after success *and* clean, no residual.
        """
        departed = worker.poll() is not None
        residual = False
        inspected = False
        trusted = self.guard.poll() is None
        disarm = False
        try:
            if trusted and success and departed and worker.returncode == 0:
                rows = set(members(self.group))
                residual = bool(rows - {self.guard.pid})
                inspected = self.guard.pid in rows
                disarm = inspected and not residual
            if trusted:
                self.channel.sendall(b'D' if disarm else b'X')
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            disarm = False
        finally:
            # EOF is an abort; watcher reaps no grandchildren. Both direct
            # children are reaped here; orphaned grandchildren belong to launchd.
            self.channel.close()
            try:
                if self.guard.poll() is None:
                    self.guard.wait(START_SECONDS)
            except subprocess.TimeoutExpired:
                disarm = False
                # Keep the sentinel alive while aborting; never target a reused
                # numeric group if an externally killed sentinel has disappeared.
            try:
                if worker.poll() is None:
                    worker.kill()   # direct, unreaped child
                worker.wait(START_SECONDS)
            except subprocess.TimeoutExpired:
                disarm = False
            if self.guard.poll() is None:
                self.guard.kill()
                self.guard.wait(START_SECONDS)
                disarm = False
        if not (trusted and disarm and self.guard.returncode == 0):
            return residual, False
        # Observation only: a recycled PGID can cause a conservative refusal,
        # never a signal to a replacement. No live writer may precede sealing.
        until = time.monotonic() + 2
        while members(self.group) and time.monotonic() < until:
            time.sleep(.02)
        return residual, inspected and not members(self.group)


if __name__ == '__main__':
    require(len(sys.argv) == 6 and sys.argv[1] == 'watch', 'guardian-only executable')
    watch(int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), float(sys.argv[5]))
