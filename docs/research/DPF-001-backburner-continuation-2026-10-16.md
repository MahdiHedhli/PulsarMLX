# DPF-001 — Backburner continuation checkpoint (2026-10-16)

This checkpoint coordinates the existing DPF-001 feasibility owner and transport/follow-up owner threads (links withheld from the repository). It does not authorize a PulsarMLX runtime change. No new device experiment was run for this checkpoint.

## Preserved source and evidence

- The only dirty file in the pinned Backburner `llama.cpp` checkout is `tools/split-prefill/tail-server.h`. Its current `git diff` exactly matches `DPF-002-tail-gate-fix-20261011/tail-server-fix.patch` on the external volume; both have SHA-256 `b181c9b05e10a9a6798e944ebfeb18232f0e54e94e2d861a5358a50d573e60b0`. `git diff --check` passed. The patch is an independent copy of this uncommitted change.
- The listener fix moves socket acceptance and the existing cable gate to a thread while retaining model and Metal work on the original app thread. It passed local security checks and two active physical-device exposure runs: each had 13 passes, no failures, one expected tunnel skip, four denied Wi-Fi probes, and an authorized 29-chunk request. See `DPF-002-tail-gate-fix-20261011/decision.md` on the external volume.
- A later paired Wi-Fi tunnel run passed 16/16 physical security checks, sent a 2,029-token request through seven iPad chunks with matching token IDs, then unpaired and revoked the key. It was a functional test, not a speed comparison. See `DPF-002-wifi-tunnel-20261011/decision.md` on the external volume.
- On the direct USB cable, the 15-minute split run completed 139 scored 4k requests with 15 remote chunks each. Late prefill median was 6,409 ms versus 8,402 ms for three Mac-only controls afterward. Changing Mac load and process history prevent attributing the difference to the cable. The earlier Hyper run won 23/24 short pairs but lost its sustained benefit under much higher late Mac load. See the direct retest and original DPF-002 decision notes on the external volume.

## Source review disposition

The change addresses the observed backlog failure: new sockets now reach the gate while a tail session computes. The filter itself uses C/C++ socket and interface calls, and its counters have locks or atomics. The retained caller thread is the one that runs model work. The saved physical tests support this narrow fix.

Before treating the patch as reusable component code, review its service lifecycle: `serve()` and the acceptor have no normal stop path, and a joinable acceptor is not joined. The current app process treats the service as long lived, but a component lifecycle needs explicit listener shutdown, thread join, and tests for reconnect and repeated accept errors. Keep the patch and its hash as the current tested revision; do not rebuild from a clean checkout and assume the fix is present.

## Next bounded experiment

When CoreDevice can list the connected iPad and the existing Backburner app and pinned model are confirmed, use the frozen DPF-002 Qwen3.5-4B model, layer-24 split, prompts, token IDs, server flags, and cable-only policy. Preserve one active server at a time and the existing loopback/API-key protections. Do not change the split, model, listener code, network settings, or PulsarMLX runtime during the comparison.

1. Record exact source and app identities, USB link, device state, Mac AC power, available memory, and Mac background load. If another inference worker is active or load is unstable, defer the timed comparison.
2. Alternate fresh-server Mac-only and Mac+iPad requests for the existing 2k, 4k, and cached-prefix append cases, retaining all pairs and their order. Record prefill, client TTFT, total wall time, cache count, token IDs/answers, remote chunk count, Mac load, iPad OS thermal state, and any error or fallback. Keep cold/conditioning requests separate from scored requests.
3. Recheck a continuous 4k split interval with Mac-only controls immediately before and after, using the same frozen request. Record every request and a time-window summary. Measure or instrument the actual persistent split socket's boundary, state, and return bytes and elapsed times separately from iPad compute and Mac tail wait; the prior 525 MB/s file transfer does not measure this socket.
4. Run the existing idle and active raw-port exposure checks on the exact installed listener revision. The paired Wi-Fi tunnel need not be enabled for a cable performance comparison. Restore temporary credentials and stop test services afterward.

Treat a run with materially different Mac background load as inconclusive for speed attribution. A useful result must retain the preselected paired samples, matching token IDs/answers for the tested prompts, observed remote work, and the prior 10% prefill/TTFT screening target through the sustained condition. Report cold-request regressions, numerical differences, and protocol overhead separately. The original DPF-002 targets and raw results are in `DPF-002-20261011/decision.md` on the external volume.

## Current execution blocker

The iPad appears in the Mac's USB registry, but `xcrun devicectl list devices` timed out twice while initializing CoreDeviceService. Device/app availability is therefore unverified and no experiment was started. The existing owner should resume from this checkpoint once that read-only device check succeeds. No device or security setting was changed here.
