#!/usr/bin/env python3
"""Replay an expert-request trace through a fresh PulsarSlotStore without the model (unpruned-fidelity G37/G39).

A trace (run_offload.py --trace) is the exact sequence of (phase, layer, wave) the store saw during one generation,
with the store's configuration in its header and its policy counters at the phase boundaries in its footer. Replaying
it with `store.fill(lid, store.touch_wave(lid, wave))` reproduces the same policy (same slot assignment, hits, misses,
evictions - asserted against the footer) while the ONLY thing that changes between conditions is how the cold bytes
are requested (--coalesce-gap, --read-chunk-mib): the read/fill latency and the byte counters per phase are what a
replay measures. It is not an end-to-end speedup (no compute, no activations): the best replay condition goes to a
real-model A/B. Every condition runs in its own fresh process and a fresh store (warm_start False): no cache state is
carried from one condition to the next. --force-cold routes every read through the cold path regardless of page-cache
residency; that is NOT a cold OS cache (F_NOCACHE reads still hit cached pages) and the record says so.
"""
import argparse
import json
import os
import sys
import time


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--trace', required=True); ap.add_argument('--offload', default=None, help='repack directory (default: the trace header)')
    ap.add_argument('--coalesce-gap', type=int, required=True); ap.add_argument('--read-chunk-mib', type=int, default=64); ap.add_argument('--read-chunk-bytes', type=int, default=None, help='overrides --read-chunk-mib (tiny controls)'); ap.add_argument('--read-workers', type=int, default=8)
    ap.add_argument('--expert-cache-bytes', type=int, default=None, help='default: the trace header budget'); ap.add_argument('--force-cold', action='store_true')
    ap.add_argument('--log', required=True); ap.add_argument('--label', default=None); ap.add_argument('--wire', action='store_true', help='wire the MLX buffers (as the admitted runner does)')
    args = ap.parse_args()
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import mlx.core as mx
    from pulsar_slot_store import PulsarSlotStore
    if args.wire:
        mx.set_wired_limit(int(mx.device_info()['max_recommended_working_set_size']))

    with open(args.trace) as fh:
        header = json.loads(fh.readline())
        records, footer = [], None
        for line in fh:
            d = json.loads(line)
            if d.get('footer'):
                footer = d
            else:
                records.append((d['p'], d['l'], d['w']))
    offload = args.offload or header['offload']
    budget = args.expert_cache_bytes or header['budget_bytes']
    t0 = time.time()
    chunk = args.read_chunk_bytes if args.read_chunk_bytes else (args.read_chunk_mib << 20)
    store = PulsarSlotStore(offload, budget, 0, decay=float(header.get('decay', 0.5)), decay_every=int(header.get('decay_every', 4096)), warm_start=False, read_workers=args.read_workers,
                            coalesce_gap_experts=args.coalesce_gap, read_chunk_bytes=chunk)
    store.force_cold = bool(args.force_cold)
    if store.capacity != header['capacity_per_layer'] or store.expert_bytes != header['expert_bytes']:
        raise SystemExit(f"GEOMETRY_MISMATCH capacity {store.capacity} vs {header['capacity_per_layer']}, expert bytes {store.expert_bytes} vs {header['expert_bytes']}")
    t_init = time.time() - t0
    phases = {}
    cur = None; t_phase = None; n_waves = 0
    vm0 = _vm()
    for ph, lid, wave in records:
        if ph != cur:
            if cur is not None:
                phases[cur] = {'seconds': round(time.time() - t_phase, 3), 'waves': n_waves, 'stats': store.stats(), 'vm': _vm()}
            cur, t_phase, n_waves = ph, time.time(), 0
        store.fill(lid, store.touch_wave(lid, wave)); n_waves += 1
    if cur is not None:
        phases[cur] = {'seconds': round(time.time() - t_phase, 3), 'waves': n_waves, 'stats': store.stats(), 'vm': _vm()}
    # policy reproduction: the footer's phase stats (captured with the model) must match the replay's
    checks = {}
    keys = ('hits', 'misses', 'evictions', 'waves', 'resident_experts', 'logical_admitted_bytes')
    if footer:
        for name, fs in footer['phase_stats'].items():
            rp = phases.get('prefill' if name == 'prefill' else list(phases)[-1])
            if rp is None:
                continue
            checks[name] = {k: (rp['stats'][k], fs[k], rp['stats'][k] == fs[k]) for k in keys if k in fs}
    policy_reproduced = all(v[2] for c in checks.values() for v in c.values()) if checks else None
    final = store.stats()
    rec = {'label': args.label, 'trace': args.trace, 'header': header, 'coalesce_gap': args.coalesce_gap, 'read_chunk_bytes': chunk, 'read_workers': args.read_workers, 'force_cold': bool(args.force_cold), 'wired': bool(args.wire),
           'os_cache_state': 'OBSERVED (not controlled); force_cold selects the cold reader only', 'init_seconds': round(t_init, 2), 'phases': phases, 'policy_reproduced': policy_reproduced, 'policy_checks': checks,
           'final_stats': final, 'peak_memory_bytes': int(mx.get_peak_memory()), 'vm_before': vm0, 'vm_after': _vm(),
           'derived': {'requested_over_logical': (final['requested_read_bytes'] / final['logical_admitted_bytes']) if final['logical_admitted_bytes'] else None,
                       'overread_fraction_of_requested': (final['overread_bytes'] / final['requested_read_bytes']) if final['requested_read_bytes'] else None,
                       'read_seconds_total': round(sum(p['seconds'] for p in phases.values()), 3), 'cold_gbps': None}}
    secs = rec['derived']['read_seconds_total']
    if secs:
        rec['derived']['cold_gbps'] = round(final['requested_read_bytes'] / secs / 1e9, 3)
    json.dump(rec, open(args.log, 'w'), indent=1)
    print(json.dumps({k: rec[k] for k in ('label', 'coalesce_gap', 'force_cold', 'policy_reproduced', 'derived')}, indent=1))
    print(json.dumps({ph: {'seconds': p['seconds'], 'waves': p['waves'], 'misses': p['stats']['misses'], 'requested_MB': round(p['stats']['requested_read_bytes'] / 1e6), 'overread_MB': round(p['stats']['overread_bytes'] / 1e6), 'ranges': p['stats']['coalesced_ranges'], 'chunks': p['stats']['chunks_read'], 'hot': p['stats']['hot_reads'], 'cold': p['stats']['cold_reads']} for ph, p in phases.items()}, indent=1))
    return 0


def _vm():
    import subprocess
    try:
        out = subprocess.check_output(['vm_stat']).decode(); stats = {}
        for line in out.splitlines()[1:]:
            if ':' in line:
                k, v = line.split(':', 1); stats[k.strip()] = int(v.strip().rstrip('.') or 0)
        swap = subprocess.check_output(['sysctl', '-n', 'vm.swapusage']).decode()
        return {'compressor_pages': stats.get('Pages occupied by compressor'), 'swapouts': stats.get('Swapouts'), 'file_backed_pages': stats.get('File-backed pages'), 'swap_used_mib': float(swap.split('used = ')[1].split('M')[0])}
    except Exception:
        return None


if __name__ == '__main__':
    sys.exit(main())
