#!/usr/bin/env python3
"""Independent memory-pressure watchdog for a full-checkpoint run (unpruned-fidelity session, G35).

A separate lightweight process (stdlib only, no MLX) samples `vm_stat` and `sysctl vm.swapusage` every `--interval`
seconds and terminates ONE verified target process at the first of these triggers, all frozen before the model loads:
  * compressor growth: pages occupied by the compressor grew by more than --comp-gib over the rolling --window seconds;
  * swap growth: swap used grew by more than --swap-mib over the rolling window (macOS 26 swaps after compressing);
  * critical pressure: `memory_pressure` reports a free percentage below --min-free-pct (an earlier signal);
  * headroom: the host's projected headroom (memsize - anonymous/wired/compressed footprint of everything else -
    the admitted working-set ceiling) is checked ONCE at start and must be at least --headroom-gib.
Termination is graceful only: SIGTERM to the target, wait --grace seconds; if it is still alive the host is marked
NEEDS_OPERATOR in the status file and nothing else is done (never kill -9 a process wiring 100 GB - graph 27 lesson).
The status file is rewritten every sample; the trigger record is appended to the log. A synthetic feed (--synthetic
FILE: a JSON list of samples) drives the same decision path without touching the host, for validation before use.
"""
import argparse
import json
import os
import signal
import subprocess
import sys
import time

PAGE = 16384


def read_vm_stat():
    out = subprocess.check_output(["vm_stat"]).decode()
    stats = {}
    for line in out.splitlines()[1:]:
        if ":" in line:
            k, v = line.split(":", 1); stats[k.strip()] = int(v.strip().rstrip(".") or 0)
    swap = subprocess.check_output(["sysctl", "-n", "vm.swapusage"]).decode()
    used_mib = float(swap.split("used = ")[1].split("M")[0])
    try:
        mp = subprocess.check_output(["memory_pressure"], timeout=5).decode()
        free_pct = int(mp.strip().splitlines()[-1].split(":")[1].strip().rstrip("%"))
    except Exception:
        free_pct = None
    return {"t": time.time(), "compressor_gib": stats.get("Pages occupied by compressor", 0) * PAGE / 2**30, "swap_used_mib": used_mib,
            "free_pct": free_pct, "free_gib": stats.get("Pages free", 0) * PAGE / 2**30, "active_gib": stats.get("Pages active", 0) * PAGE / 2**30,
            "wired_gib": stats.get("Pages wired down", 0) * PAGE / 2**30, "swapouts": stats.get("Swapouts", 0)}


def host_footprint_gib():
    """Anonymous pageable + wired + compressor-occupied memory of the whole host (the model process included if running)."""
    def g(k):
        return int(subprocess.check_output(["sysctl", "-n", k]).decode().strip())
    anon = g("vm.page_pageable_internal_count") * PAGE / 2**30
    vs = read_vm_stat()
    return anon + vs["wired_gib"] + vs["compressor_gib"], g("hw.memsize") / 2**30


def alive(pid):
    try:
        os.kill(pid, 0); return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pid", type=int, required=True, help="the one process this watchdog may terminate (verified by the caller)")
    ap.add_argument("--status", required=True, help="status JSON rewritten every sample")
    ap.add_argument("--log", required=True, help="append-only event log (JSON lines)")
    ap.add_argument("--interval", type=float, default=5.0); ap.add_argument("--window", type=float, default=60.0)
    ap.add_argument("--comp-gib", type=float, default=1.0); ap.add_argument("--swap-mib", type=float, default=256.0)
    ap.add_argument("--min-free-pct", type=int, default=10)
    ap.add_argument("--headroom-gib", type=float, default=8.0); ap.add_argument("--ceiling-gib", type=float, default=None, help="admitted total working-set ceiling of the target (residents + expert cache + activations/allocator reserve)")
    ap.add_argument("--grace", type=float, default=30.0)
    ap.add_argument("--synthetic", default=None, help="JSON list of samples instead of the host (validation)")
    ap.add_argument("--max-seconds", type=float, default=12 * 3600)
    args = ap.parse_args(argv)
    feed = json.load(open(args.synthetic)) if args.synthetic else None

    def log(event, **kw):
        with open(args.log, "a") as fh:
            fh.write(json.dumps({"t": time.time(), "event": event, **kw}) + "\n")

    rolling = {}

    def write_status(state, sample, extra=None):
        json.dump({"state": state, "pid": args.pid, "sample": sample, "rolling": dict(rolling), "thresholds": {"comp_gib": args.comp_gib, "swap_mib": args.swap_mib, "min_free_pct": args.min_free_pct, "window_s": args.window, "headroom_gib": args.headroom_gib, "ceiling_gib": args.ceiling_gib},
                   **(extra or {})}, open(args.status + ".tmp", "w"), indent=1)
        os.replace(args.status + ".tmp", args.status)

    if args.ceiling_gib is not None and feed is None:
        footprint, memsize = host_footprint_gib()
        headroom = memsize - footprint - args.ceiling_gib
        log("headroom_check", footprint_gib=round(footprint, 1), memsize_gib=round(memsize, 1), ceiling_gib=args.ceiling_gib, projected_headroom_gib=round(headroom, 1), ok=headroom >= args.headroom_gib)
        if headroom < args.headroom_gib:
            write_status("HEADROOM_REFUSED", None, {"projected_headroom_gib": round(headroom, 1)})
            print(f"HEADROOM_REFUSED projected {headroom:.1f} GiB < {args.headroom_gib}", flush=True)
            return 3
    history = []; t_start = time.time(); state = "WATCHING"; log("start", pid=args.pid, synthetic=bool(feed))
    i = 0
    while True:
        sample = feed[i] if feed is not None else read_vm_stat()
        if feed is not None:
            sample = dict(sample); sample.setdefault("t", t_start + i * args.interval); i += 1
        history.append(sample); history = [s for s in history if sample["t"] - s["t"] <= args.window]
        base = history[0]
        d_comp = sample["compressor_gib"] - base["compressor_gib"]; d_swap = sample["swap_used_mib"] - base["swap_used_mib"]
        trigger = None
        if d_comp > args.comp_gib:
            trigger = f"compressor +{d_comp:.2f} GiB in {sample['t'] - base['t']:.0f}s"
        elif d_swap > args.swap_mib:
            trigger = f"swap +{d_swap:.0f} MiB in {sample['t'] - base['t']:.0f}s"
        elif sample.get("free_pct") is not None and sample["free_pct"] < args.min_free_pct:
            trigger = f"memory_pressure free {sample['free_pct']}% < {args.min_free_pct}%"
        target_alive = alive(args.pid)
        rolling.update({"d_comp_gib": round(d_comp, 3), "d_swap_mib": round(d_swap, 1), "window_s": round(sample["t"] - base["t"], 1)})
        write_status(state, sample, {"target_alive": target_alive})
        if not target_alive:
            log("target_exited"); write_status("TARGET_EXITED", sample); return 0
        if trigger:
            log("trigger", reason=trigger, sample=sample); state = "TERMINATING"
            try:
                os.kill(args.pid, signal.SIGTERM)
            except ProcessLookupError:
                write_status("TARGET_EXITED", sample); return 0
            deadline = time.time() + args.grace
            while time.time() < deadline and alive(args.pid):
                time.sleep(0.5 if feed is None else 0)
                if feed is not None:
                    break
            if alive(args.pid) and feed is None:
                log("needs_operator", reason="target survived SIGTERM within grace"); write_status("NEEDS_OPERATOR", sample, {"trigger": trigger})
                print(f"NEEDS_OPERATOR {trigger}", flush=True); return 2
            log("terminated", reason=trigger); write_status("TERMINATED", sample, {"trigger": trigger})
            print(f"TERMINATED {trigger}", flush=True); return 1
        if feed is not None and i >= len(feed):
            write_status("FEED_DONE", sample); return 0
        if time.time() - t_start > args.max_seconds:
            write_status("MAX_SECONDS", sample); return 0
        time.sleep(args.interval if feed is None else 0)


if __name__ == "__main__":
    sys.exit(main())
