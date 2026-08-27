# R001 expert-store repack foundation closeout

## State

`R001_FOUNDATION_ACCEPTED`

This state accepts the bounded storage-layout foundation only. It does not
claim F017 correctness, production inference readiness, or a completed expert
store.

## Host and storage

- Host: ColPanicM2, Apple M2 Max, 64 GiB unified memory.
- External device: ADATA SX8100NP in OWC Envoy Express.
- Transport: Thunderbolt 3, reported 40 Gb/s; NVMe PCIe 8.0 GT/s x2.
- Filesystem: writable APFS, 4,096-byte filesystem block, 16,384-byte VM page.
- Volume UUID: `FFB3C9A5-84BD-4076-89A0-ACE3BCEC6DD4`.
- TRIM: reported Yes. SMART: reported Verified.
- Temperature: unavailable through installed macOS tools.
- Final observed container free space before disposable cleanup:
  1,751,729,115,136 bytes.

SMB and removable-volume permission probes passed without expanding to Full
Disk Access. The checkpoint was copied once from SMB into the graph-owned
external source hierarchy. No checkpoint was downloaded or copied to internal
storage.

## Source identity

| Shard | Bytes | SHA-256 | Copy | Average MiB/s |
|---:|---:|---|---:|---:|
| 1 | 9,423,744 | `7bf96eeabbe887e58b6c44364962731ddc9dc5bf46fec8d097c1dff64bea4a18` | 0.106 s | 84.951 |
| 2 | 49,105,028,960 | `d94adaa58ddd5abbcf2514192958084416b1aa36bd4d21409028a164341bac36` | 998.582 s | 46.897 |
| 3 | 49,143,176,640 | `1cd0b1a3d9d939ce5a184c548f1b1c42edafaf1856cb0d7e586a2884a366256b` | 990.424 s | 47.320 |
| 4 | 49,143,176,640 | `10f3965db697a46ba66494475045af183c1bcaf639984160930c91a377816d3e` | 1,013.246 s | 46.254 |
| 5 | 49,143,176,640 | `40d7d4524ff07e0f9af494fb13130dc7090184800cc5af0a1563188b076af50d` | 1,061.365 s | 44.157 |
| 6 | 41,914,650,304 | `eeceb9084350e64be8eebcd1f19ab14bbbb6b40132c86d77ffc65e72f425044d` | 900.209 s | 44.404 |

Total: 238,458,632,928 bytes. The ordered no-separator set hash is
`d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee`.
Source pre/post metadata was stable for every copy. Sustained SMB throughput was
network-limited at approximately 44-47 MiB/s. No thermal attribution is
possible because temperature telemetry was unavailable.

Admission v3 SHA-256 is
`22d658e67286aca79f9fdd76e44de6d93b82f79e32f29121b71ce32cedd82ec7`.
It reuses the previously verified shard hashes and pins the ordered shard set,
inventory, and local descriptor identities without another 238 GB hash pass.

## Live layout

- GGUF version 3; architecture `glm-dsa`; 79 layers.
- MoE layers 3 through 78.
- 256 routed and one shared expert per MoE layer.
- 456 expert tensors; 19,532 routed/shared objects.
- Expert payload: 224,974,307,328 bytes.
- Routed expert axis: source dimension 2.
- 15 component layout classes and nine quantization types.
- Every expert plane is contiguous and quantization-block aligned.
- No expert plane crosses a shard boundary.
- Coverage proof found zero out-of-bounds ranges, unintended overlaps, missing
  assignments, or duplicate assignments.

## Bundle and implementation

The v1 `.pmlxexp` object has a 16 KiB canonical header, 16 KiB-aligned
gate/up/down payloads, and a 16 KiB footer. Identity binds checkpoint, manifest
plan, architecture, layer, class, expert, role, original tensor, shard,
source offset/length/hash, full source dimensions, quantization geometry,
component hash, canonical unpadded payload hash, physical region hash, and
object hash. Paths are relocatable and do not contain drive identity.

Rust performs bounded 8 MiB positioned reads and exact byte copies with no
dequantization or numerical transformation. Objects use adjacent partials,
exclusive publication, explicit ownership, source-identity validation,
fail-closed reuse, and safe manifest completion. Python independently parses
GGUF and the wire format.

## Accepted fixture

Complete layer 40 plus early/middle/late boundary and exceptional samples:
269 objects, 807 components, 3,130,097,664 payload bytes, and 3,138,912,256
stored bytes. Clean run manifests and all generated-file hashes were identical.
Manifest SHA-256:
`22a8edaedf87f8c9d08dd4b99e4d92a17afa5899936c11cfc49b64a955be0e0d`.

Independent verification passed all objects/components and all nine live
quantization classes. Eleven negative cases and all source/resume failures were
rejected. Peak production RSS was 62,226,432 bytes.

## Benchmark qualification

For 64 layer-40 experts under successful `F_NOCACHE`:

- Sequential native: 192 calls, 0.2577 s median.
- Sequential combined bundle: 64 calls, 0.1517 s median.
- Randomized native: 192 calls, 0.2537 s median.
- Randomized combined bundle: 64 calls, 0.1499 s median.

All modes requested 723,517,440 bytes with read amplification 1.0 and matching
CRC32 streams. Bundle storage amplification was 1.00289855. These are
cache-minimized same-device read-pattern results, not cold-cache, inference, or
production-speedup claims.

## Capacity and next graph

The full v1 store estimate before manifest growth is 225,614,331,904 bytes:
224,974,307,328 payload bytes plus 640,024,576 bytes of per-object
header/footer overhead. Source plus full store would leave approximately
1,536,215,672,096 bytes, 76.8% of the APFS container, free before optional
fixture cleanup.

The recommended next graph is a deterministic full-store production run using
the frozen v3 admission and accepted code, with a fresh exclusive store root,
preflight volume-UUID/free-space checks, one ordered pass over all 19,532
objects, periodic machine-readable progress, post-run independent structural
and sampled byte verification, manifest/detached-hash reconciliation, and a
separate acceptance review. It must not add cache policy, placement,
replication, inference integration, or numerical transformation.

## Validation limitations

All R001 checks executed. The workspace test run retained two unrelated ignored
native-MLX tests whose pinned runtime was unavailable; they are not part of the
R001 storage graph. No full expert-store repack and no inference ran.
