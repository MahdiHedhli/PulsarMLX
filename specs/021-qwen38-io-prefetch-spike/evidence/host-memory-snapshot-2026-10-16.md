# M2 Max host memory snapshot and next admission gate

Read-only observations on 2026-10-16; no worker, model or reviewer was run.
The existing Qwen branch remained at `d2d77047cef93095a251cf1378f4ec16b2fc4c6d`.
The process list showed no active Qwen or Agy process.

## Host observations

`memory_pressure -Q` reported 68,719,476,736 bytes (64 GiB) physical memory.
Across checks it reported 37–44% system-wide free. `top -l 1 -n 0` reported
63 GiB physically used, 119 MiB unused, 10 GiB wired, and 25 GiB occupied by
the compressor at its observation instant. These tools use different memory
accounting. In particular, the free percentage is **not** a reservation of
24–28 GiB available for a new process. `sysctl -n vm.swapusage` reported
27,037.31 MiB used out of 27,648 MiB then allocated; this is substantial
pre-existing swap. `df -g .` reported 295 GiB available on the Data volume.

Two separate cumulative VM-counter intervals were compared:

| Interval | Swap-ins | Swap-outs | Swap-used change | Page-ins / page-outs | Compressions / decompressions |
| --- | ---: | ---: | ---: | ---: | ---: |
| 12 seconds | 0 | 0 | 0.00 MiB | 2,111 / 37 | 181,055 / 138,724 |
| 30 seconds | 0 | 0 | 0.00 MiB | 20,036 / 316 | 428,947 / 317,471 |

The large allocated swap was **not actively read or written during those
intervals**. This does not establish when its pages were written, that they
will stay idle, or that the system has room for a full Qwen process. Memory
compression was active, and ordinary page-ins/page-outs are not equivalent
to swap-ins/swap-outs. No device-level SSD traffic attribution was attempted.

## Normal application quit, later the same day

The owner authorized a normal quit of two desktop applications to free host
memory. Read-only preflight found no automation, Qwen or Agy worker using
them. No worker was interrupted. One application exited on its first normal
quit request. The other did not: an open confirmation dialog cancelled the
request. That dialog was dismissed with its cancel option, nothing was
submitted or discarded, and a later normal quit request succeeded. No force
kill or app-data deletion was used.

| Observation | Before quit | After the first application exited |
| --- | ---: | ---: |
| `memory_pressure -Q` free | 45% | 54% |
| `top` physical used | 63 GiB | 60 GiB |
| `top` physical unused | 130 MiB | 3,537 MiB |
| `top` compressor | 24 GiB | 18 GiB |
| Swap used | 27,037.31 MiB | 26,973.25 MiB |

These are snapshots, not a causal decomposition of that application's private
memory. In a subsequent comparable 30-second interval, reported free memory
moved from 54% to 56%, swap used stayed 26,973.25 MiB, swap-outs were zero and
swap-ins were 56 pages (896 KiB with 16 KiB VM pages). There is no observed
new swap write in that interval, but the approximately 26.34 GiB swap
baseline and 18 GiB compressor remain substantial. The extra physical unused
memory is only about 3.45 GiB at the snapshot; reclaimable memory is not a
guaranteed model allocation. The second application remained open at this
intermediate point.

After both applications exited, `memory_pressure -Q` reported 57% free and
swap used 26,973.25 MiB. `top` reported 63 GiB physical used, 137 MiB unused,
10 GiB wired and 16 GiB compressor. The physically unused figure had
**fallen** from the 3,537 MiB intermediate reading despite the second
application exiting; concurrent system activity and different accounting
prevent attributing all changes to the quit. In the next 12 seconds, reported
free ranged 54–57%, swap used stayed unchanged, and swap-in and swap-out
counter deltas were zero. Compressions and decompressions still advanced by
88,907 and 112,607 pages. The system remains memory-active; the 57% reading is
not a model allocation.

Highest reported single-process RSS readings included `fseventsd` about
9.32 GiB and desktop application processes at about 1.45, 0.71 and 0.48 GiB.
RSS may include shared pages, so these figures cannot be added to obtain
total unique usage. They identify current resource consumers, not the cause
of the prior swap allocation. No user or system process was terminated.

## Next bounded model-data test, after source review and adapter gates

Do not interpret the original **48 GiB Qwen process / 40 GiB weights / 16 GiB
system reserve** split as currently available. With 63 GiB physical usage and
25 GiB compressed, an inference run has no demonstrated headroom. The
106,218,444,193-byte checkpoint cannot be fully resident. Offloading the
roughly 32 GB n-gram component alone still leaves roughly 74 GB before
runtime allocations, above 64 GiB. No full loader, model inference or
throughput test is admitted by this snapshot.

The next *model-data* exercise should be a single verified page I/O proof,
not model execution: bind the already pinned checkpoint by full-file digest
and identity, read at most one 2,764,800-byte expert page and one 819,200-byte
PLE page through the reviewed pager, authenticate touched chunks, and close
owners before the next page. Require a reviewed real-I/O/MLX ownership path;
the current synthetic fixture adapter is not that path. Cap logical page
payload under 4 MiB, all retained host staging under 16 MiB, the test process
RSS under 512 MiB, MLX peak/active under 16 MiB and cache under 8 MiB if any
Metal copy is included. Use a 30-second parent watchdog. Sample host memory,
process RSS, MLX counters and VM swap counters before admission, after each
read/copy/fence/release, and at exit; fail closed on missing samples, any
observed swap growth or swap-in/out increment, pressure/headroom violation,
or owner/fence uncertainty. A provisional tiny-test preflight should require
at least **50% free** reported by `memory_pressure -Q`, at least **2 GiB
physically unused** in `top`, no swap-outs in a preceding 30-second interval,
and the existing 16 GiB absolute reported-headroom floor; repeat these
observations during the test. Each is a separate stop, not a general model
readiness score. The latest 137 MiB physically unused reading **fails** this
tiny-test preflight even though `memory_pressure` reported 57% free. A failed
preflight means wait for a quieter host;
do not try to clear swap or terminate apps automatically.

This proposed proof only validates bounded authenticated bytes, I/O accounting
and ownership. Before any real Qwen inference, separately resolve upstream
checkpoint/runtime compatibility (including norm folding), independent
numerical parity and source review, a complete pinned runtime environment,
real expert/PLE paging and SSD traffic measurement, and enforceable observed
40/48/16 GiB stops. A 20+ token/s target remains an experimental criterion,
not a forecast from the tiny probe or this host snapshot.
