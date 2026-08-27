# R001 same-device read-pattern benchmark

## Method

The original admitted GGUF and the accepted v1 bundles were both read from the
same ADATA SX8100NP APFS volume through an OWC Envoy Express Thunderbolt 3
enclosure. The NVMe link reported PCIe 8.0 GT/s x2 and the Thunderbolt link
reported 40 Gb/s.

Reads used Darwin `F_NOCACHE` successfully for every opened file. This is a
cache-minimized experiment, not a controlled cold-cache result. No destructive
cache operation was used. CRC32 values reconcile across native, component, and
combined bundle paths for each access order.

The sustained trial read 64 layer-40 experts, 723,517,440 logical bytes, five
times per mode. The burst trial read one expert 30 times per mode. Temperature
and SMART thermal telemetry were unavailable, so no thermal-throttling claim is
made.

## Sustained medians

| Pattern | Layout | Calls | Wall | Per expert | GiB/s |
|---|---|---:|---:|---:|---:|
| sequential | native components | 192 | 0.2577 s | 4.027 ms | 2.614 |
| sequential | bundle components | 192 | 0.2581 s | 4.033 ms | 2.611 |
| sequential | bundle combined | 64 | 0.1517 s | 2.371 ms | 4.441 |
| randomized | native components | 192 | 0.2537 s | 3.965 ms | 2.656 |
| randomized | bundle components | 192 | 0.2200 s | 3.437 ms | 3.063 |
| randomized | bundle combined | 64 | 0.1499 s | 2.341 ms | 4.497 |

Read amplification was 1.0 in every mode. The bundle object storage
amplification for this standard working set was 1.00289855. Combining each
expert's gate/up/down components reduced positioned read calls from three to
one without changing the byte stream.

## Single-expert medians

| Pattern | Layout | Calls | Latency | GiB/s |
|---|---|---:|---:|---:|
| sequential | native components | 3 | 2.288 ms | 4.602 |
| sequential | bundle components | 3 | 2.176 ms | 4.840 |
| sequential | bundle combined | 1 | 2.385 ms | 4.415 |
| randomized | native components | 3 | 4.109 ms | 2.562 |
| randomized | bundle components | 3 | 2.131 ms | 4.940 |
| randomized | bundle combined | 1 | 2.451 ms | 4.296 |

## Interpretation

The sustained result is directional evidence that one contiguous expert-object
read can reduce request count and elapsed read time on this device. The
single-expert result is noisy and does not show a universal latency win for a
combined read. These numbers are not inference throughput, do not isolate every
APFS or controller cache, and do not prove a production speedup.

The evidence was produced by `scripts/research/r001_benchmark.py` at commit
`7532daff`. Local sustained evidence SHA-256 is
`edea4b69dc3e5483520dbca42e3ece784edc49699e1360e94ba7433deb2ae1a7`;
local burst evidence SHA-256 is
`6d6a99ddd539637be4385add34dd34c502a4367713ac5c1af9519fcdc479387f`.
